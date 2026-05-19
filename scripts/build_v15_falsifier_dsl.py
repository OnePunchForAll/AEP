#!/usr/bin/env python3
"""
build_v15_falsifier_dsl.py - K7 Deterministic Falsifier DSL (AEP v1.5 LTS)

Operator directive (sec73.2 sacred): K7 Deterministic Meaning Compiler.
Falsifier scripts have been a back-door for arbitrary-cmd execution. K7 closes that:

  - NO arbitrary cmd. NO subprocess. NO network. NO writes.
  - ONLY declared-source reads + declared-op computes.
  - Compile-time forbid list rejects subprocess / socket / os.environ / writes /
    unbounded loops / unseeded random / hidden state.

Schema (FDL v1):
{
  "dsl_version": "aep-fdl-v1",
  "falsifier_id": "fdl:<claim>:<test_name>",
  "kind": "literal_check | regex_match | hash_compare | json_path_assert |
           length_compare | enum_membership | numeric_bound",
  "input_source": {"type": "declared_source_id | declared_oracle_id",
                   "id": "src:..."},
  "expected": {"type": "literal", "value": "..."},
  "actual_compute": {"op": "hash | length | regex_extract | json_path |
                            bytes_at_offset"},
  "forbidden_features": ["shell", "network", "writes", "env_reads",
                         "unbounded_loops", "unseeded_random", "hidden_state"]
}

API:
  - compile_falsifier(dsl_json) -> CompiledFalsifier
  - execute_falsifier(compiled, packet) -> {result, expected, actual, reason}
  - counterfactual_fuzz(falsifier, packet) -> {survived_corrupted_evidence: bool}

Composes with:
  - K9 Adversarial-Resistance (forbidden-features compile-time deny)
  - F22 CivilianProofCard (falsifier outputs feed proof card row 3)
  - F23 mutation-testing (counterfactual fuzz IS a mutation class)

Truth tag: STRONGLY PLAUSIBLE (schema-bound; T1+T2+T10 empirical this turn;
production rollout STAGED v1.5.1 with full kind-matrix).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------- DSL constants ----------

DSL_VERSION = "aep-fdl-v1"

VALID_KINDS = {
    "literal_check",
    "regex_match",
    "hash_compare",
    "json_path_assert",
    "length_compare",
    "enum_membership",
    "numeric_bound",
}

VALID_INPUT_TYPES = {"declared_source_id", "declared_oracle_id"}

VALID_COMPUTE_OPS = {
    "hash",
    "length",
    "regex_extract",
    "json_path",
    "bytes_at_offset",
    "identity",  # raw value
}

# Forbidden compile-time markers in any DSL field (string scan)
FORBIDDEN_TOKENS = (
    "subprocess",
    "socket",
    "os.environ",
    "os.system",
    "exec(",
    "eval(",
    "__import__",
    "open(",
    "file(",
    "compile(",
    "shell=true",
    "popen",
    "shutil.",
    "requests.",
    "urllib.",
    "http.client",
    "ftplib",
    "telnetlib",
)

# Forbidden_features list per schema
SCHEMA_FORBIDDEN_FEATURES = [
    "shell",
    "network",
    "writes",
    "env_reads",
    "unbounded_loops",
    "unseeded_random",
    "hidden_state",
]


# ---------- Compiled falsifier dataclass ----------

@dataclass
class CompiledFalsifier:
    falsifier_id: str
    kind: str
    input_type: str
    input_id: str
    expected_type: str
    expected_value: Any
    compute_op: str
    compute_args: Dict[str, Any] = field(default_factory=dict)
    forbidden_features: List[str] = field(default_factory=list)
    compile_warnings: List[str] = field(default_factory=list)
    dsl_source: Dict[str, Any] = field(default_factory=dict)


# ---------- Compile errors ----------

class CompileError(ValueError):
    """Raised when a falsifier DSL fails compile-time validation."""


# ---------- Compile ----------

def _scan_for_forbidden_tokens(dsl_json: Dict[str, Any]) -> List[str]:
    """
    Walk the DSL JSON tree and reject any string containing forbidden tokens.
    Returns list of violation strings; empty if clean.
    """
    violations: List[str] = []

    def walk(node: Any, path: str = "$") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(k, f"{path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
        elif isinstance(node, str):
            low = node.lower()
            for tok in FORBIDDEN_TOKENS:
                if tok in low:
                    violations.append(f"forbidden_token '{tok}' at {path}")

    walk(dsl_json, "$")
    return violations


def compile_falsifier(dsl_json: Union[Dict[str, Any], str]) -> CompiledFalsifier:
    """
    Compile a falsifier DSL spec into a CompiledFalsifier object.

    Raises CompileError on:
      - missing required fields
      - invalid kind / input_type / compute_op
      - forbidden tokens in any string field
      - wrong dsl_version
    """
    if isinstance(dsl_json, str):
        try:
            dsl = json.loads(dsl_json)
        except json.JSONDecodeError as e:
            raise CompileError(f"DSL is not valid JSON: {e}")
    else:
        dsl = dsl_json

    if not isinstance(dsl, dict):
        raise CompileError(f"DSL must be a dict, got {type(dsl).__name__}")

    # dsl_version
    dsl_version = dsl.get("dsl_version")
    if dsl_version != DSL_VERSION:
        raise CompileError(
            f"dsl_version mismatch: expected {DSL_VERSION!r}, got {dsl_version!r}"
        )

    # falsifier_id
    fid = dsl.get("falsifier_id")
    if not isinstance(fid, str) or not fid.startswith("fdl:"):
        raise CompileError(f"falsifier_id must start with 'fdl:', got {fid!r}")

    # kind
    kind = dsl.get("kind")
    if kind not in VALID_KINDS:
        raise CompileError(
            f"invalid kind {kind!r}; must be one of {sorted(VALID_KINDS)}"
        )

    # input_source
    inp = dsl.get("input_source", {})
    if not isinstance(inp, dict):
        raise CompileError("input_source must be an object")
    inp_type = inp.get("type")
    inp_id = inp.get("id")
    if inp_type not in VALID_INPUT_TYPES:
        raise CompileError(
            f"input_source.type must be one of {sorted(VALID_INPUT_TYPES)}, got {inp_type!r}"
        )
    if not isinstance(inp_id, str) or not inp_id:
        raise CompileError(f"input_source.id must be a non-empty string, got {inp_id!r}")

    # expected
    exp = dsl.get("expected", {})
    if not isinstance(exp, dict):
        raise CompileError("expected must be an object")
    exp_type = exp.get("type", "literal")
    exp_value = exp.get("value")
    if exp_type != "literal":
        raise CompileError(f"expected.type must be 'literal' in FDL v1, got {exp_type!r}")

    # actual_compute
    ac = dsl.get("actual_compute", {})
    if not isinstance(ac, dict):
        raise CompileError("actual_compute must be an object")
    op = ac.get("op")
    if op not in VALID_COMPUTE_OPS:
        raise CompileError(
            f"actual_compute.op must be one of {sorted(VALID_COMPUTE_OPS)}, got {op!r}"
        )
    compute_args = {k: v for k, v in ac.items() if k != "op"}

    # forbidden_features (schema declaration; we cross-check below)
    declared_forbidden = dsl.get("forbidden_features", [])
    if not isinstance(declared_forbidden, list):
        raise CompileError("forbidden_features must be a list")

    # Token scan
    violations = _scan_for_forbidden_tokens(dsl)
    if violations:
        raise CompileError(
            "forbidden tokens in DSL (sec73.5 / K9 deny):\n  - "
            + "\n  - ".join(violations)
        )

    warnings: List[str] = []
    missing = [f for f in SCHEMA_FORBIDDEN_FEATURES if f not in declared_forbidden]
    if missing:
        warnings.append(
            f"forbidden_features does not enumerate {missing}; "
            "all 7 standard features are deny-by-default regardless"
        )

    return CompiledFalsifier(
        falsifier_id=fid,
        kind=kind,
        input_type=inp_type,
        input_id=inp_id,
        expected_type=exp_type,
        expected_value=exp_value,
        compute_op=op,
        compute_args=compute_args,
        forbidden_features=SCHEMA_FORBIDDEN_FEATURES.copy(),
        compile_warnings=warnings,
        dsl_source=dsl,
    )


# ---------- Execute ----------

def _resolve_input(
    compiled: CompiledFalsifier, packet: Dict[str, Any]
) -> Tuple[Any, str]:
    """
    Resolve declared input source from the packet.

    Returns (resolved_value, resolution_path).
    Raises ValueError if input id not present in packet.
    """
    if compiled.input_type == "declared_source_id":
        sources = packet.get("sources", {})
        if compiled.input_id in sources:
            return sources[compiled.input_id], f"sources/{compiled.input_id}"
        raise ValueError(
            f"declared_source_id {compiled.input_id!r} not present in packet.sources"
        )
    elif compiled.input_type == "declared_oracle_id":
        oracles = packet.get("oracles", {})
        if compiled.input_id in oracles:
            return oracles[compiled.input_id], f"oracles/{compiled.input_id}"
        raise ValueError(
            f"declared_oracle_id {compiled.input_id!r} not present in packet.oracles"
        )
    raise ValueError(f"unknown input_type {compiled.input_type}")


def _apply_compute(op: str, value: Any, args: Dict[str, Any]) -> Any:
    """
    Apply the declared compute op to the input value.

    Pure-function: no network, no shell, no writes. Deterministic on inputs.
    """
    if op == "identity":
        return value
    if op == "hash":
        algo = args.get("algo", "sha256")
        if algo not in ("sha256", "sha1", "md5", "blake2b"):
            raise ValueError(f"unsupported hash algo {algo!r}")
        data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
        h = hashlib.new(algo)
        h.update(data)
        return h.hexdigest()
    if op == "length":
        return len(value) if value is not None else 0
    if op == "regex_extract":
        pattern = args.get("pattern", "")
        group = int(args.get("group", 0))
        if not isinstance(value, str):
            return ""
        m = re.search(pattern, value)
        if not m:
            return ""
        try:
            return m.group(group)
        except (IndexError, re.error):
            return ""
    if op == "json_path":
        path = args.get("path", "$")
        # tiny JSON path: $.a.b.c [no wildcards, no filters]
        if not path.startswith("$"):
            raise ValueError(f"json_path must start with $; got {path!r}")
        parts = [p for p in path[1:].split(".") if p]
        cur: Any = value
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return None
        return cur
    if op == "bytes_at_offset":
        offset = int(args.get("offset", 0))
        length = int(args.get("length", 1))
        if isinstance(value, str):
            value = value.encode("utf-8")
        return value[offset:offset + length].hex() if isinstance(value, (bytes, bytearray)) else None
    raise ValueError(f"unsupported compute op {op!r}")


def _compare_kind(
    kind: str, expected: Any, actual: Any
) -> Tuple[bool, str]:
    """
    Apply the kind comparator. Returns (result_bool, reason_string).
    """
    if kind == "literal_check":
        ok = (expected == actual)
        return (ok, f"literal_check: expected={expected!r} actual={actual!r}")
    if kind == "regex_match":
        if not isinstance(actual, str):
            actual = str(actual) if actual is not None else ""
        try:
            ok = bool(re.fullmatch(str(expected), actual))
        except re.error as e:
            return (False, f"regex_match: invalid pattern: {e}")
        return (ok, f"regex_match: pattern={expected!r} subject={actual!r}")
    if kind == "hash_compare":
        ok = (str(expected).lower() == str(actual).lower())
        return (ok, f"hash_compare: expected={expected} actual={actual}")
    if kind == "json_path_assert":
        ok = (expected == actual)
        return (ok, f"json_path_assert: expected={expected!r} actual={actual!r}")
    if kind == "length_compare":
        # expected: {"op": "==|>=|<=|>|<", "value": int}
        if isinstance(expected, dict):
            op = expected.get("op", "==")
            val = int(expected.get("value", 0))
        else:
            op, val = "==", int(expected)
        a = int(actual or 0)
        ok = {
            "==": a == val,
            ">=": a >= val,
            "<=": a <= val,
            ">": a > val,
            "<": a < val,
        }.get(op, False)
        return (ok, f"length_compare: actual_len={a} {op} {val}")
    if kind == "enum_membership":
        if not isinstance(expected, list):
            return (False, "enum_membership: expected must be a list")
        ok = (actual in expected)
        return (ok, f"enum_membership: actual={actual!r} in {expected!r}")
    if kind == "numeric_bound":
        if not isinstance(expected, dict):
            return (False, "numeric_bound: expected must be a dict {min,max}")
        mn = expected.get("min")
        mx = expected.get("max")
        try:
            a = float(actual)
        except (TypeError, ValueError):
            return (False, f"numeric_bound: actual {actual!r} not numeric")
        ok = True
        if mn is not None and a < float(mn):
            ok = False
        if mx is not None and a > float(mx):
            ok = False
        return (ok, f"numeric_bound: {mn} <= {a} <= {mx}")
    return (False, f"unknown kind {kind}")


def execute_falsifier(
    compiled: CompiledFalsifier, packet: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute a compiled falsifier against a packet dict.

    Returns:
      {
        "result": bool,
        "expected": ...,
        "actual": ...,
        "reason": str,
        "input_resolution": str,
        "compute_op": str,
        "falsifier_id": str
      }
    """
    try:
        raw_input, resolution = _resolve_input(compiled, packet)
    except ValueError as e:
        return {
            "result": False,
            "expected": compiled.expected_value,
            "actual": None,
            "reason": f"input_resolution_failed: {e}",
            "input_resolution": "MISSING",
            "compute_op": compiled.compute_op,
            "falsifier_id": compiled.falsifier_id,
        }

    try:
        actual = _apply_compute(compiled.compute_op, raw_input, compiled.compute_args)
    except Exception as e:
        return {
            "result": False,
            "expected": compiled.expected_value,
            "actual": None,
            "reason": f"compute_failed: {e}",
            "input_resolution": resolution,
            "compute_op": compiled.compute_op,
            "falsifier_id": compiled.falsifier_id,
        }

    ok, reason = _compare_kind(compiled.kind, compiled.expected_value, actual)
    return {
        "result": ok,
        "expected": compiled.expected_value,
        "actual": actual,
        "reason": reason,
        "input_resolution": resolution,
        "compute_op": compiled.compute_op,
        "falsifier_id": compiled.falsifier_id,
    }


# ---------- Counterfactual fuzz ----------

def _corrupt_value(v: Any) -> Any:
    """
    Deterministic single-bit corruption of a packet value.

    Strings: flip first char (or append byte if empty).
    Numbers: add 1.
    Bool: invert.
    Dict/list: clear.
    None: return "x".
    """
    if isinstance(v, str):
        if not v:
            return "x"
        first = v[0]
        flipped = chr((ord(first) ^ 1) % 0x10FFFF)
        return flipped + v[1:]
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v + 1
    if isinstance(v, dict):
        return {}
    if isinstance(v, list):
        return []
    return "x"


def counterfactual_fuzz(
    compiled: CompiledFalsifier,
    packet: Dict[str, Any],
    *,
    rounds: int = 4,
) -> Dict[str, Any]:
    """
    Counterfactual fuzz a falsifier against corrupted evidence.

    For each round: corrupt the input_id value in packet; re-run falsifier.

    A genuine falsifier SHOULD fail (return False) on corrupted evidence,
    because the falsifier's expected value no longer matches.

    A theatrical falsifier (e.g. one that always returns True regardless of
    input -- "exit 0 always") will STILL pass on corrupted evidence, which
    is the rejection signal.

    Returns:
      {
        "survived_corrupted_evidence": bool,
                # True = THEATRICAL (REJECT this falsifier)
                # False = GENUINE (falsifier responds to evidence)
        "rounds": int,
        "rounds_passed_on_corruption": int,
        "first_pass_on_corruption_reason": str,
        "theater_verdict": "REJECT_THEATER" | "ACCEPT_GENUINE",
        "details_per_round": [...]
      }
    """
    if compiled.input_type == "declared_source_id":
        container_key = "sources"
    elif compiled.input_type == "declared_oracle_id":
        container_key = "oracles"
    else:
        return {
            "survived_corrupted_evidence": False,
            "rounds": 0,
            "rounds_passed_on_corruption": 0,
            "first_pass_on_corruption_reason": "",
            "theater_verdict": "ACCEPT_GENUINE",
            "details_per_round": [],
            "honest_note": "unknown input_type; counterfactual_fuzz not applicable",
        }

    details: List[Dict[str, Any]] = []
    rounds_passed = 0
    first_pass_reason = ""

    for r in range(rounds):
        # Deep-ish copy: rebuild containers with corruption applied
        corrupted_packet = {
            **packet,
            container_key: {
                **packet.get(container_key, {}),
            },
        }
        original_val = corrupted_packet[container_key].get(compiled.input_id)
        # Corrupt iteratively so each round is distinct
        for _ in range(r + 1):
            original_val = _corrupt_value(original_val)
        corrupted_packet[container_key][compiled.input_id] = original_val

        result = execute_falsifier(compiled, corrupted_packet)
        details.append({"round": r, "result": result["result"], "reason": result["reason"]})
        if result["result"]:
            rounds_passed += 1
            if not first_pass_reason:
                first_pass_reason = result["reason"]

    # If ANY round still passes on corrupted evidence, the falsifier is
    # not responding to its declared input -> theatrical.
    theatrical = rounds_passed > 0

    return {
        "survived_corrupted_evidence": theatrical,
        "rounds": rounds,
        "rounds_passed_on_corruption": rounds_passed,
        "first_pass_on_corruption_reason": first_pass_reason,
        "theater_verdict": "REJECT_THEATER" if theatrical else "ACCEPT_GENUINE",
        "details_per_round": details,
    }


# ---------- CLI ----------

def _cli() -> int:
    ap = argparse.ArgumentParser(
        description="K7 Falsifier DSL compiler + executor"
    )
    ap.add_argument("dsl_path", help="Path to falsifier DSL JSON file")
    ap.add_argument("--packet", help="Path to packet JSON for execution")
    ap.add_argument(
        "--fuzz", action="store_true", help="Run counterfactual fuzz on packet"
    )
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    dsl_path = pathlib.Path(args.dsl_path)
    if not dsl_path.is_file():
        print(f"ERROR: DSL file not found: {dsl_path}", file=sys.stderr)
        return 3
    try:
        dsl = json.loads(dsl_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot parse DSL JSON: {e}", file=sys.stderr)
        return 3

    try:
        compiled = compile_falsifier(dsl)
    except CompileError as e:
        print(f"COMPILE_ERROR: {e}", file=sys.stderr)
        return 2

    out: Dict[str, Any] = {
        "falsifier_id": compiled.falsifier_id,
        "kind": compiled.kind,
        "compile_status": "OK",
        "compile_warnings": compiled.compile_warnings,
    }

    if args.packet:
        try:
            packet = json.loads(pathlib.Path(args.packet).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERROR: cannot parse packet JSON: {e}", file=sys.stderr)
            return 3
        exec_result = execute_falsifier(compiled, packet)
        out["execution"] = exec_result
        if args.fuzz:
            fuzz = counterfactual_fuzz(compiled, packet)
            out["counterfactual_fuzz"] = fuzz

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"FALSIFIER: {compiled.falsifier_id}")
        print(f"  kind: {compiled.kind}")
        print(f"  compile: OK ({len(compiled.compile_warnings)} warnings)")
        if "execution" in out:
            er = out["execution"]
            print(f"  execute: {'PASS' if er['result'] else 'FAIL'}")
            print(f"    reason: {er['reason']}")
        if "counterfactual_fuzz" in out:
            cf = out["counterfactual_fuzz"]
            print(f"  fuzz: {cf['theater_verdict']} "
                  f"({cf['rounds_passed_on_corruption']}/{cf['rounds']} rounds passed on corruption)")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
