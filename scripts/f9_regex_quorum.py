#!/usr/bin/env python3
"""f9_regex_quorum.py - F9 cross-substrate portable-regex quorum runner (AEP v1.0.3).

For each regex pattern in a RegexicalCue, spawns:
 - Python: re.compile + re.search
 - Node:   node -e "new RegExp(<pat>).test(<text>)"
 - Perl:   perl -e 'print(<text> =~ m{<pat>} ? "1" : "0")'

Emits per-runtime {compile: bool, match: bool} matrix.

L7 closure: if Perl absent at C:\\Program Files\\Git\\usr\\bin\\perl.exe, emit `runtime_unavailable: perl`
row + degrade to N=2 (python + node only) with `quorum_degraded: true` flag.

Operator's 3 patterns expected to all return 9/9 (or 6/6 with degraded N=2 if Perl absent):
 - \\bpre[- ]?mortem\\b
 - \\bweakest[- ]assumption\\b
 - \\bpreflight\\b

Output is a `validations/runs.jsonl`-compatible row written to stdout (also captured by caller).

Composes with AEP_v1_0_3_SPEC.md sec73.5 + L7 closure binding under sec69.4.

Stdlib only (subprocess + json + re + pathlib).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re as _re
import shutil
import subprocess
import sys
from typing import Any, Dict, List

PERL_PATH_DEFAULT = pathlib.Path(r"C:\Program Files\Git\usr\bin\perl.exe")
NODE_BIN = "node"
TIMEOUT_SEC = 5

# Reference test text for compile+match validation. Real-world cue activation
# would pass the actual source.md text; for F9 verification we use operator's
# example seed text known to contain the 3 patterns.
DEFAULT_TEST_TEXT = (
    "The adversary performs pre-mortem review on plans to surface the weakest assumption "
    "before forge implementation. Preflight scans guard against premortem fabrication. "
    "Weakest-assumption attacks fire when the pre-mortem detects a load-bearing claim "
    "without falsifier. Pre-Mortem is the canonical adversary mode."
)


def find_perl() -> pathlib.Path | None:
    if PERL_PATH_DEFAULT.exists():
        return PERL_PATH_DEFAULT
    which = shutil.which("perl")
    return pathlib.Path(which) if which else None


def find_node() -> str | None:
    return shutil.which(NODE_BIN)


def run_python_check(pattern: str, text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"runtime": "python", "compile": False, "match": False, "error": None}
    try:
        # Use case_insensitive to match operator's example flags.
        compiled = _re.compile(pattern, flags=_re.IGNORECASE)
        out["compile"] = True
        m = compiled.search(text)
        out["match"] = m is not None
    except _re.error as e:
        out["error"] = f"python re.error: {e}"
    except Exception as e:
        out["error"] = f"python exception: {type(e).__name__}: {e}"
    return out


def run_node_check(node_path: str, pattern: str, text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"runtime": "node", "compile": False, "match": False, "error": None}
    # Build a tiny Node script: try {compile} then {match}; print JSON.
    # Escape backslashes + quotes for JS string literal.
    pat_js = pattern.replace("\\", "\\\\").replace("'", "\\'")
    text_js = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    js = (
        "let out={compile:false,match:false,error:null};"
        f"try{{const r=new RegExp('{pat_js}','i');out.compile=true;"
        f"out.match=r.test('{text_js}');}}"
        "catch(e){out.error='node:'+e.message;}"
        "console.log(JSON.stringify(out));"
    )
    try:
        proc = subprocess.run(
            [node_path, "-e", js],
            capture_output=True, text=True, timeout=TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
        )
        stdout = (proc.stdout or "").strip().splitlines()
        if proc.returncode != 0:
            out["error"] = f"node exit {proc.returncode}: {proc.stderr.strip()[:200]}"
            return out
        if not stdout:
            out["error"] = "node: empty stdout"
            return out
        parsed = json.loads(stdout[-1])
        out["compile"] = bool(parsed.get("compile"))
        out["match"] = bool(parsed.get("match"))
        if parsed.get("error"):
            out["error"] = parsed["error"]
    except subprocess.TimeoutExpired:
        out["error"] = f"node: timed_out after {TIMEOUT_SEC}s"
    except FileNotFoundError:
        out["error"] = "node: binary not found"
    except json.JSONDecodeError as e:
        out["error"] = f"node: stdout parse error: {e}"
    except Exception as e:
        out["error"] = f"node: {type(e).__name__}: {e}"
    return out


def run_perl_check(perl_path: pathlib.Path, pattern: str, text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"runtime": "perl", "compile": False, "match": False, "error": None}
    # Use Perl's m{...}i to match operator's case_insensitive flag.
    # Escape backslashes + braces + the closing }i delimiter.
    pat_perl = pattern.replace("\\", "\\\\").replace("}", "\\}")
    text_perl = text.replace("\\", "\\\\").replace("'", "\\'")
    perl_script = (
        f"my $text='{text_perl}'; "
        f"eval {{ qr/{pat_perl}/i; }}; "
        f"if ($@) {{ print 'COMPILE_FAIL:'.$@; exit 0; }} "
        f"print 'COMPILE_OK'; "
        f"if ($text =~ m/{pat_perl}/i) {{ print '|MATCH_OK'; }} "
        f"else {{ print '|MATCH_FAIL'; }}"
    )
    try:
        proc = subprocess.run(
            [str(perl_path), "-e", perl_script],
            capture_output=True, text=True, timeout=TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
        )
        stdout = (proc.stdout or "").strip()
        if proc.returncode != 0:
            out["error"] = f"perl exit {proc.returncode}: {proc.stderr.strip()[:200]}"
            return out
        if stdout.startswith("COMPILE_FAIL:"):
            out["error"] = f"perl compile fail: {stdout[len('COMPILE_FAIL:'):][:200]}"
            return out
        if "COMPILE_OK" in stdout:
            out["compile"] = True
        if "MATCH_OK" in stdout:
            out["match"] = True
        elif "MATCH_FAIL" in stdout:
            out["match"] = False
    except subprocess.TimeoutExpired:
        out["error"] = f"perl: timed_out after {TIMEOUT_SEC}s"
    except FileNotFoundError:
        out["error"] = f"perl: binary not found at {perl_path}"
    except Exception as e:
        out["error"] = f"perl: {type(e).__name__}: {e}"
    return out


def run_quorum_for_pattern(pattern: str, text: str, perl_path: pathlib.Path | None, node_path: str | None) -> Dict[str, Any]:
    matrix: Dict[str, Any] = {}
    matrix["python"] = run_python_check(pattern, text)
    if node_path:
        matrix["node"] = run_node_check(node_path, pattern, text)
    else:
        matrix["node"] = {"runtime": "node", "compile": False, "match": False, "error": "runtime_unavailable: node"}
    if perl_path:
        matrix["perl"] = run_perl_check(perl_path, pattern, text)
    else:
        matrix["perl"] = {"runtime": "perl", "compile": False, "match": False, "error": "runtime_unavailable: perl"}
    return matrix


def emit_quorum_row(cue: Dict[str, Any], text: str, perl_path: pathlib.Path | None, node_path: str | None) -> Dict[str, Any]:
    patterns = cue.get("regex", {}).get("patterns", []) or []
    perl_ok = perl_path is not None
    node_ok = node_path is not None
    quorum_degraded = not (perl_ok and node_ok)
    runtime_unavailable: List[str] = []
    if not perl_ok:
        runtime_unavailable.append("perl")
    if not node_ok:
        runtime_unavailable.append("node")

    per_pattern: Dict[str, Dict[str, Any]] = {}
    total_cells = 0
    true_cells = 0
    for pat in patterns:
        matrix = run_quorum_for_pattern(pat, text, perl_path, node_path)
        per_pattern[pat] = matrix
        for rt_name, rt_result in matrix.items():
            if rt_result.get("error") and rt_result.get("error", "").startswith("runtime_unavailable"):
                continue  # don't count unavailable runtimes
            total_cells += 2  # compile + match
            if rt_result.get("compile"):
                true_cells += 1
            if rt_result.get("match"):
                true_cells += 1

    row = {
        "type": "F9_quorum_run",
        "schema_version": "aep-regexical-memory-0.1",
        "cue_id": cue.get("id"),
        "packet_id": cue.get("packet_id"),
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "quorum_target": "F9_cross_substrate_quorum_default_N3_python_node_perl",
        "quorum_degraded": quorum_degraded,
        "runtime_unavailable": runtime_unavailable,
        "n_runtimes_active": 3 - len(runtime_unavailable),
        "test_text_sha256_prefix": "default_seed_text_v0",
        "patterns": list(patterns),
        "per_pattern": per_pattern,
        "cells_true": true_cells,
        "cells_total": total_cells,
        "quorum_pass": total_cells > 0 and true_cells == total_cells,
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="F9 cross-substrate portable-regex quorum runner.")
    parser.add_argument("input_path", help="Path to JSONL file with RegexicalCue rows.")
    parser.add_argument("--test-text-path", default=None, help="Path to text file to match against (default: built-in seed text).")
    parser.add_argument("--output-jsonl", default=None, help="Append output rows to this JSONL (default: stdout).")
    parser.add_argument("--no-perl", action="store_true", help="Skip Perl even if present (force degraded N=2).")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input_path)
    if not input_path.exists():
        print(f"FATAL: input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.test_text_path:
        test_text = pathlib.Path(args.test_text_path).read_text(encoding="utf-8")
    else:
        test_text = DEFAULT_TEST_TEXT

    perl_path = None if args.no_perl else find_perl()
    node_path = find_node()

    if not perl_path:
        print(f"INFO: perl not found at {PERL_PATH_DEFAULT}; degrading to N=2 (python + node)", file=sys.stderr)
    if not node_path:
        print(f"WARN: node not found in PATH; degrading further", file=sys.stderr)

    out_fp = None
    if args.output_jsonl:
        out_fp = pathlib.Path(args.output_jsonl).open("a", encoding="utf-8")

    rows_processed = 0
    any_fail = False
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            cue = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"PARSE_ERROR: {e}", file=sys.stderr)
            any_fail = True
            continue
        row = emit_quorum_row(cue, test_text, perl_path, node_path)
        rows_processed += 1
        out_line = json.dumps(row, separators=(",", ":"))
        if out_fp:
            out_fp.write(out_line + "\n")
        else:
            print(out_line)
        if not row["quorum_pass"]:
            any_fail = True
            print(
                f"QUORUM_FAIL cue={row['cue_id']} cells {row['cells_true']}/{row['cells_total']} degraded={row['quorum_degraded']}",
                file=sys.stderr,
            )
        else:
            print(
                f"QUORUM_PASS cue={row['cue_id']} cells {row['cells_true']}/{row['cells_total']} degraded={row['quorum_degraded']}",
                file=sys.stderr,
            )

    if out_fp:
        out_fp.close()

    print(f"\nSummary: {rows_processed} rows processed, any_fail={any_fail}", file=sys.stderr)
    return 0 if not any_fail and rows_processed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
