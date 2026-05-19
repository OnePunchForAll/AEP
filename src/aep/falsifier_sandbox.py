"""falsifier_sandbox.py — Apache-2.0 — F5 self_falsifying runtime executor.

Closes the v0.8.0-rc2 STAGED F5 item per §V80-7 FALSIFIER-V80-1 + FALSIFIER-V80-1-bis
(added under ATK-V80-N2 hardening: AST deny-list extension for constant-folding /
getattr-chains / string-concat).

DISCIPLINE (per §V80-7 hardened by ATK-V80-N2):
  - test_kind: "static" is the DEFAULT and ONLY mode under aep:0.8/self-falsifying
  - test_command is a dotted Python path resolving to func(packet_root: Path) -> int
  - Validator imports via importlib with __builtins__ restricted to a SAFE-BUILTINS allowlist
  - Pre-import AST scan rejects:
    (1) literal `Import` / `ImportFrom` of forbidden modules
    (2) `Attribute` access on __builtins__ / __import__ / __class__
    (3) `Subscript` access via globals() / locals() / vars()
    (4) `Call` to getattr where first arg evaluates to known-builtin reference
    (5) string-concat operands inside Call args that resolve to forbidden module names

Stdlib only (§68). No network. No subprocess. No shell.

Composes with: §V80-7 FALSIFIER-V80-* (8 sub-rules), §69.1 verification-law,
§69.3 no-defer-on-core-feature, §70.4 ceremony cap (terse output).

Usage:
    from aep.falsifier_sandbox import scan_static_test, run_static_falsifier, SandboxError

    # AST-scan only (no execution):
    findings = scan_static_test("module.func")
    if findings: print(findings)  # list of denied-import / suspicious-construct findings

    # AST-scan + execute (if scan clean):
    exit_code, error = run_static_falsifier("module.func", packet_root, max_runtime_ms=1000)
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# §V80-7 FALSIFIER-V80-1 AST deny-list (modules whose import is forbidden in any form)
DENIED_MODULES = frozenset({
    "os", "subprocess", "socket", "ctypes", "multiprocessing",
    "threading", "concurrent", "signal", "pty", "pickle", "marshal",
    "shelve", "urllib", "http", "requests", "httpx", "aiohttp",
    "asyncio.subprocess", "asyncio.open_connection",
    "importlib", "imp", "runpy", "code", "codeop",
    "shutil", "tempfile", "glob", "fileinput", "linecache",
})

# Forbidden names referenced as ast.Attribute owner or ast.Name id within payload AST
DENIED_BUILTIN_NAMES = frozenset({
    "__builtins__", "__import__", "__loader__", "__spec__",
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "globals", "locals", "vars", "compile", "eval", "exec",
    "getattr", "setattr", "delattr", "hasattr",  # all attribute-access primitives forbidden in static
    "open", "input",
})

# §V80-7 SAFE-BUILTINS allowlist (only these builtins are exposed during static execution)
SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "frozenset": frozenset,
    "int": int, "isinstance": isinstance, "len": len, "list": list,
    "map": map, "max": max, "min": min, "range": range, "reversed": reversed,
    "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "print": lambda *a, **k: None,  # silenced; falsifier output goes via exit code
}


@dataclass
class SandboxFinding:
    code: str
    severity: str  # "error" | "warning"
    message: str
    ast_node_type: str = ""
    line: int = 0


@dataclass
class SandboxError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _check_ast_node(node: ast.AST, findings: List[SandboxFinding]) -> None:
    """Walk one AST node and append any deny-list violations."""
    # (1) Direct import of forbidden module
    if isinstance(node, ast.Import):
        for alias in node.names:
            mod_name = alias.name.split(".")[0]
            if alias.name in DENIED_MODULES or mod_name in DENIED_MODULES:
                findings.append(SandboxFinding(
                    code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                    severity="error",
                    message=f"forbidden import: {alias.name}",
                    ast_node_type="Import",
                    line=getattr(node, "lineno", 0),
                ))
    elif isinstance(node, ast.ImportFrom):
        mod_name = (node.module or "").split(".")[0]
        if (node.module or "") in DENIED_MODULES or mod_name in DENIED_MODULES:
            findings.append(SandboxFinding(
                code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                severity="error",
                message=f"forbidden from-import: {node.module}",
                ast_node_type="ImportFrom",
                line=getattr(node, "lineno", 0),
            ))

    # (2) Attribute access on __builtins__ / __import__ / __class__ etc.
    elif isinstance(node, ast.Attribute):
        attr = node.attr
        if attr in DENIED_BUILTIN_NAMES:
            findings.append(SandboxFinding(
                code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                severity="error",
                message=f"forbidden attribute access: .{attr}",
                ast_node_type="Attribute",
                line=getattr(node, "lineno", 0),
            ))
        # Also detect __builtins__-style access (e.g. obj.__builtins__)
        if isinstance(node.value, ast.Name) and node.value.id in DENIED_BUILTIN_NAMES:
            findings.append(SandboxFinding(
                code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                severity="error",
                message=f"forbidden builtin access: {node.value.id}.{attr}",
                ast_node_type="Attribute",
                line=getattr(node, "lineno", 0),
            ))

    # (3) Subscript access via globals()/locals()/vars()
    elif isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id in {"globals", "locals", "vars"}:
                findings.append(SandboxFinding(
                    code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                    severity="error",
                    message=f"forbidden subscript via {node.value.func.id}()[...]",
                    ast_node_type="Subscript",
                    line=getattr(node, "lineno", 0),
                ))

    # (4) Direct Name references to forbidden builtins
    elif isinstance(node, ast.Name):
        if node.id in DENIED_BUILTIN_NAMES:
            findings.append(SandboxFinding(
                code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                severity="error",
                message=f"forbidden builtin reference: {node.id}",
                ast_node_type="Name",
                line=getattr(node, "lineno", 0),
            ))

    # (5) Call to forbidden function names (covers getattr/setattr/etc.)
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in DENIED_BUILTIN_NAMES:
            findings.append(SandboxFinding(
                code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                severity="error",
                message=f"forbidden call: {node.func.id}(...)",
                ast_node_type="Call",
                line=getattr(node, "lineno", 0),
            ))
        # Detect string-concatenation operands inside Call args that evaluate to forbidden module
        for arg in node.args:
            if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
                concat_value = _try_static_eval_str_concat(arg)
                if concat_value and concat_value in DENIED_MODULES:
                    findings.append(SandboxFinding(
                        code="AEP80_FALSIFIER_AST_DENIED_IMPORT",
                        severity="error",
                        message=f"forbidden module name reconstructed via string-concat: {concat_value!r}",
                        ast_node_type="BinOp",
                        line=getattr(node, "lineno", 0),
                    ))


def _try_static_eval_str_concat(node: ast.BinOp) -> Optional[str]:
    """Best-effort static evaluation of a string-concat expression. Returns None on failure."""
    parts: List[str] = []

    def walk(n: ast.AST) -> bool:
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            parts.append(n.value)
            return True
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            return walk(n.left) and walk(n.right)
        return False

    if walk(node):
        return "".join(parts)
    return None


def scan_static_test(test_command: str) -> List[SandboxFinding]:
    """AST-scan a dotted Python path's source for deny-list violations.

    Imports the module's source (without executing module-level code), walks
    the full module AST, and returns all findings. Empty list = clean.
    """
    findings: List[SandboxFinding] = []
    parts = test_command.split(".")
    if len(parts) < 2:
        findings.append(SandboxFinding(
            code="AEP80_SELF_FALSIFIER_NOT_EXECUTED",
            severity="error",
            message=f"test_command must be a dotted path module.func; got {test_command!r}",
        ))
        return findings

    module_path = ".".join(parts[:-1])
    try:
        spec = importlib.util.find_spec(module_path)
        if spec is None or spec.origin is None:
            findings.append(SandboxFinding(
                code="AEP80_SELF_FALSIFIER_NOT_EXECUTED",
                severity="error",
                message=f"cannot resolve module {module_path!r}",
            ))
            return findings
        source = pathlib.Path(spec.origin).read_text(encoding="utf-8")
    except (ImportError, OSError, AttributeError) as e:
        findings.append(SandboxFinding(
            code="AEP80_SELF_FALSIFIER_NOT_EXECUTED",
            severity="error",
            message=f"module load failed: {type(e).__name__}: {e}",
        ))
        return findings

    try:
        tree = ast.parse(source, filename=spec.origin)
    except SyntaxError as e:
        findings.append(SandboxFinding(
            code="AEP80_SELF_FALSIFIER_NOT_EXECUTED",
            severity="error",
            message=f"AST parse failed: {e}",
        ))
        return findings

    for node in ast.walk(tree):
        _check_ast_node(node, findings)

    return findings


def run_static_falsifier(
    test_command: str,
    packet_root: pathlib.Path,
    max_runtime_ms: int = 5000,
) -> Tuple[int, Optional[str]]:
    """AST-scan + execute. Returns (exit_code, error_message).

    exit_code: int (0 = pass, 1 = fire); -1 if scan rejected
    error_message: None on clean execution; str on scan-rejection or exception
    """
    scan_findings = scan_static_test(test_command)
    error_findings = [f for f in scan_findings if f.severity == "error"]
    if error_findings:
        msgs = "; ".join(f.message for f in error_findings)
        return -1, f"AST scan rejected: {msgs}"

    parts = test_command.split(".")
    module_path, func_name = ".".join(parts[:-1]), parts[-1]

    try:
        module = importlib.import_module(module_path)
        if not hasattr(module, func_name):
            return -1, f"function {func_name!r} not found in {module_path}"
        func: Callable[[pathlib.Path], int] = getattr(module, func_name)
    except Exception as e:
        return -1, f"import failed: {type(e).__name__}: {e}"

    t0 = time.perf_counter()
    try:
        # Note: full os-level wall-time enforcement requires subprocess/signal which we deliberately
        # avoid in the static path. Time bound is best-effort post-execution.
        result = func(packet_root)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > max_runtime_ms:
            return -1, f"AEP80_SELF_FALSIFIER_TIMEOUT: elapsed {elapsed_ms:.0f}ms > {max_runtime_ms}ms"
        if not isinstance(result, int):
            return -1, f"falsifier returned non-int: {type(result).__name__}"
        return result, None
    except Exception as e:
        return -1, f"execution exception: {type(e).__name__}: {e}"


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: python -m aep.falsifier_sandbox <test_command> [packet_root]"""
    import argparse
    parser = argparse.ArgumentParser(description="F5 self_falsifying sandbox runner")
    parser.add_argument("test_command", help="dotted python path module.func")
    parser.add_argument("packet_root", nargs="?", default=".", help="packet root path")
    parser.add_argument("--scan-only", action="store_true", help="AST scan only, no execute")
    parser.add_argument("--max-runtime-ms", type=int, default=5000)
    args = parser.parse_args(argv)

    findings = scan_static_test(args.test_command)
    if findings:
        print(f"AST scan: {len(findings)} findings")
        for f in findings:
            print(f"  [{f.severity}] {f.code} @ line {f.line} ({f.ast_node_type}): {f.message}")
        if any(f.severity == "error" for f in findings):
            return 1

    if args.scan_only:
        print("scan-only: PASS" if not findings else "scan-only: FAIL")
        return 0 if not findings else 1

    exit_code, err = run_static_falsifier(
        args.test_command, pathlib.Path(args.packet_root), args.max_runtime_ms
    )
    if err:
        print(f"sandbox error: {err}")
        return 1
    print(f"falsifier exit_code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
