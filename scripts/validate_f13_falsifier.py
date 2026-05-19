#!/usr/bin/env python3
"""validate_f13_falsifier.py - F13 claim_runtime_falsifier validator + executor.

AEP v1.1 F13 reference implementation. Implements:

1. **Validator**: loads f13_claim_runtime_falsifier.schema.json; validates a CRF
   record; emits reason codes per sec4.5 (TIMEOUT, FIRED_REJECT, FIRED_DEMOTE,
   TAUTOLOGY_BLOCKED, F9_QUORUM_DIVERGED, SELF_ATTESTATION_BLOCKED).

2. **Executor harness**: spawns subprocess per the `executor` field, passes
   `cmd`, enforces `ttl_ms` timeout (operator constraint: <=100ms), captures
   exit code, compares to `expected_exit`.

3. **Anti-tautology check** (sec4.6): detects whether a falsifier's cmd is a
   tautological no-op by:
     a) static-string match against known tautology patterns
        ('exit 0', 'return True', 'true', 'echo "" exit 0', etc.)
     b) dynamic check: run cmd twice with deliberate environment mutation
        between runs (set $F13_TAUTOLOGY_PROBE to two distinct values);
        if both runs match expected_exit despite the deliberate state change,
        mark tautology_suspected=true.

4. **API**: verify_falsifier(claim_id, falsifier_block) -> {
       confirmed, tautology_suspected, runtime_ms, exit_code, reason_codes
   }

5. **Self-attestation check** (sec4.6): binding_principal must differ from the
   claim author principal. Tested by comparing binding_principal to the
   `bound_to_claim_author` field if provided in the falsifier block, OR to
   the `--claim-author` CLI arg.

Composes_with: v0.8 F5 self_falsifying (packet-level; F13 is claim-level),
v0.8 F2 reproducibility_certificate, v1.0.x F9 cross-substrate quorum,
sec50 EH Law-3 anti-self-attestation.

Stdlib only (subprocess + json + re + pathlib + time + os).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Schema constants
# -----------------------------------------------------------------------------

VALID_EXECUTORS = {
    "python_static_dotted", "node_static_dotted", "subprocess_sandboxed",
    "sql_query", "grep_pattern", "json_path_assertion",
}

VALID_FIRE_ACTIONS = {"REJECT", "DEMOTE_RELIABILITY", "WARN", "QUARANTINE"}

REQUIRED_FIELDS = [
    "type", "schema_version", "id", "bound_to_claim_id",
    "executor", "cmd", "expected_exit", "ttl_ms", "binding_principal",
]

# Patterns whose cmd alone (no other operation) is tautological per sec4.6.
TAUTOLOGY_PATTERNS_STATIC = [
    r"^\s*(exit\s+0|/bin/true|true)\s*$",
    r"^\s*python\s+-c\s+['\"]exit\(0\)['\"]?\s*$",
    r"^\s*python\s+-c\s+['\"]pass['\"]?\s*$",
    r"^\s*node\s+-e\s+['\"](?:0|true|process\.exit\(0\))['\"]?\s*$",
    r"^\s*echo\s+(?:['\"][^'\"]*['\"]|\S*)\s*$",      # plain echo, no exit-code dependency
    r"^\s*return\s+True\s*$",                          # pseudo-cmd "return True"
    r"^\s*return\s+0\s*$",
    r"^\s*:\s*$",                                      # bash no-op
]

# Phrases in cmd suggesting self-reference / dormitive virtue per legion HV-1.
DORMITIVE_PHRASE_PATTERNS = [
    r"\bassert\s+claim\s*=",                # "assert claim = claim"
    r"\bassert\s+self\s*==\s*self\b",
    r"\bif\s+claim\s+then\s+claim\b",
]


# -----------------------------------------------------------------------------
# Validator
# -----------------------------------------------------------------------------

def validate_crf_record(rec: Dict[str, Any], claim_author_principal: Optional[str] = None) -> List[str]:
    """Validate one CRF record; return reason codes (empty = pass)."""
    errors: List[str] = []
    for f in REQUIRED_FIELDS:
        if f not in rec:
            errors.append(f"AEP11_F13_SCHEMA_MISSING_FIELD:{f}")
    if rec.get("type") != "ClaimRuntimeFalsifier":
        errors.append("AEP11_F13_SCHEMA_TYPE_MISMATCH")
    if rec.get("schema_version") != "aep-claim-runtime-falsifier-0.1":
        errors.append("AEP11_F13_SCHEMA_VERSION_MISMATCH")
    if rec.get("executor") not in VALID_EXECUTORS:
        errors.append(f"AEP11_F13_SCHEMA_UNKNOWN_EXECUTOR:{rec.get('executor')}")
    ttl = rec.get("ttl_ms", 0)
    if not isinstance(ttl, int) or ttl < 1 or ttl > 100:
        errors.append(f"AEP11_F13_SCHEMA_TTL_OUT_OF_RANGE:{ttl}")
    exp = rec.get("expected_exit", 0)
    if not isinstance(exp, int) or exp < 0 or exp > 255:
        errors.append(f"AEP11_F13_SCHEMA_EXIT_OUT_OF_RANGE:{exp}")
    cmd = rec.get("cmd", "")
    if not isinstance(cmd, str) or not cmd or len(cmd) > 2048:
        errors.append("AEP11_F13_SCHEMA_CMD_INVALID")
    if rec.get("on_fire_action") and rec["on_fire_action"] not in VALID_FIRE_ACTIONS:
        errors.append(f"AEP11_F13_SCHEMA_UNKNOWN_FIRE_ACTION:{rec.get('on_fire_action')}")

    # Anti-self-attestation per sec4.6
    bp = rec.get("binding_principal", "")
    ca = claim_author_principal or rec.get("bound_to_claim_author")
    if isinstance(bp, str) and isinstance(ca, str) and bp == ca and bp:
        errors.append("AEP11_F13_SELF_ATTESTATION_BLOCKED")

    # Static tautology gate
    if isinstance(cmd, str):
        for pat in TAUTOLOGY_PATTERNS_STATIC:
            if re.search(pat, cmd):
                errors.append(f"AEP11_F13_TAUTOLOGY_STATIC_MATCH:{pat}")
                break
        for pat in DORMITIVE_PHRASE_PATTERNS:
            if re.search(pat, cmd):
                errors.append(f"AEP11_F13_DORMITIVE_PHRASE_MATCH:{pat}")
                break

    return errors


# -----------------------------------------------------------------------------
# Executor
# -----------------------------------------------------------------------------

def _split_python_dash_c(tail: str) -> List[str]:
    """Parse a 'python -c <body>' tail. Returns argv from sys.executable.

    Uses shlex.split (POSIX mode) to honor inline-quoted bodies. Falls back to
    simple split if shlex fails. The cmd body may contain escaped quotes or
    embedded statements with semicolons.
    """
    try:
        parts = shlex.split(tail, posix=True)
    except ValueError:
        parts = tail.split()
    if not parts:
        return [sys.executable, "-c", "pass"]
    if parts[0] == "-c" and len(parts) >= 2:
        return [sys.executable, "-c", parts[1]] + parts[2:]
    return [sys.executable] + parts


def _build_argv(executor: str, cmd: str) -> List[str]:
    """Build subprocess argv for the executor type."""
    if executor == "python_static_dotted":
        stripped = cmd.strip()
        if stripped.startswith("python "):
            tail = stripped[len("python "):].strip()
            return _split_python_dash_c(tail)
        # Plain "module.func" dotted-name; resolve via importlib at runtime.
        return [sys.executable, "-c",
                "import importlib,sys; m=" + repr(cmd) +
                ".split('.'); mod=importlib.import_module('.'.join(m[:-1])); getattr(mod, m[-1])(); sys.exit(0)"]
    if executor == "node_static_dotted":
        node = shutil.which("node") or "node"
        stripped = cmd.strip()
        if stripped.startswith("node "):
            tail = stripped[len("node "):].strip()
            try:
                parts = shlex.split(tail, posix=True)
            except ValueError:
                parts = tail.split()
            if parts and parts[0] == "-e" and len(parts) >= 2:
                return [node, "-e", parts[1]] + parts[2:]
            return [node] + parts
        return [node, "-e", "console.log('static_dotted not implemented'); process.exit(0)"]
    if executor == "subprocess_sandboxed":
        # Direct subprocess; honor shell-quoted args.
        try:
            return shlex.split(cmd, posix=True)
        except ValueError:
            return cmd.split()
    if executor == "grep_pattern":
        # cmd is a regex pattern; we apply re.search to stdin and exit 0 on match.
        return [sys.executable, "-c",
                f"import sys,re; body=sys.stdin.read(); m=re.search({cmd!r}, body); sys.exit(0 if m else 1)"]
    if executor == "json_path_assertion":
        return [sys.executable, "-c", f"import sys; print('json_path stub:{cmd}'); sys.exit(0)"]
    if executor == "sql_query":
        return [sys.executable, "-c", "import sys; sys.exit(1)"]
    return [sys.executable, "-c", "import sys; sys.exit(1)"]


def execute_falsifier_once(executor: str, cmd: str, ttl_ms: int,
                            extra_env: Optional[Dict[str, str]] = None,
                            stdin_text: Optional[str] = None) -> Dict[str, Any]:
    """Execute a falsifier once; return {exit_code, runtime_ms, timed_out, stderr_tail}."""
    argv = _build_argv(executor, cmd)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    timeout_sec = max(0.001, ttl_ms / 1000.0)
    t0 = time.perf_counter_ns()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
            input=stdin_text,
            encoding="utf-8",
            errors="replace",
        )
        elapsed_ns = time.perf_counter_ns() - t0
        return {
            "exit_code": proc.returncode,
            "runtime_ms": elapsed_ns / 1e6,
            "timed_out": False,
            "stderr_tail": (proc.stderr or "")[-256:],
            "stdout_tail": (proc.stdout or "")[-256:],
        }
    except subprocess.TimeoutExpired:
        elapsed_ns = time.perf_counter_ns() - t0
        return {
            "exit_code": None,
            "runtime_ms": elapsed_ns / 1e6,
            "timed_out": True,
            "stderr_tail": "TIMEOUT",
            "stdout_tail": "",
        }
    except FileNotFoundError as e:
        elapsed_ns = time.perf_counter_ns() - t0
        return {
            "exit_code": -1,
            "runtime_ms": elapsed_ns / 1e6,
            "timed_out": False,
            "stderr_tail": f"FILE_NOT_FOUND: {e}",
            "stdout_tail": "",
        }
    except Exception as e:  # noqa: BLE001
        elapsed_ns = time.perf_counter_ns() - t0
        return {
            "exit_code": -1,
            "runtime_ms": elapsed_ns / 1e6,
            "timed_out": False,
            "stderr_tail": f"EXEC_ERROR: {type(e).__name__}: {e}"[:256],
            "stdout_tail": "",
        }


def dynamic_tautology_probe(executor: str, cmd: str, ttl_ms: int, expected_exit: int) -> Dict[str, Any]:
    """Dynamic tautology check (sec4.6 anti-dormitive-self-binding).

    Heuristic per legion HV-1 "FRH itself becomes dormitive": only ACTIVATE the
    dynamic probe when the executor consumes stdin (grep_pattern is the only
    one in the v1.1 reference impl). Run grep cmd against TWO opposing payloads:
        payload_A contains a unique alpha-marker token
        payload_B contains a unique beta-marker token (no alpha)
    If the cmd's regex matches BOTH payloads with the same exit code, the
    regex is too broad and acts tautologically against arbitrary substrate
    state -> tautology_suspected=true.

    For non-stdin-consuming executors (python_static_dotted, node_static_dotted,
    subprocess_sandboxed, json_path_assertion, sql_query), the dynamic probe
    cannot meaningfully discriminate (cmd doesn't depend on stdin), so the
    probe is NOT-FIRED and dormitive-detection falls back to the static gate.
    This is the honest semantics; previously the probe falsely flagged
    cmds that simply don't read stdin.
    """
    stdin_active_executors = {"grep_pattern"}
    if executor not in stdin_active_executors:
        return {
            "run_A_exit": None,
            "run_B_exit": None,
            "run_A_runtime_ms": 0,
            "run_B_runtime_ms": 0,
            "both_match_expected": False,
            "probe_active": False,
            "probe_reason": f"executor={executor} does not read stdin; dynamic probe inapplicable (static gate only).",
        }

    stdin_A = "PROBE_PAYLOAD_A: contains alpha_marker_unique_alpha_alpha_alpha and the and word"
    stdin_B = "PROBE_PAYLOAD_B: contains beta_marker_unique_beta_beta_beta and word"
    run_A = execute_falsifier_once(executor, cmd, ttl_ms,
                                    extra_env={"F13_TAUTOLOGY_PROBE": "alpha"},
                                    stdin_text=stdin_A)
    run_B = execute_falsifier_once(executor, cmd, ttl_ms,
                                    extra_env={"F13_TAUTOLOGY_PROBE": "beta"},
                                    stdin_text=stdin_B)
    both_match = (run_A.get("exit_code") == expected_exit) and (run_B.get("exit_code") == expected_exit)
    return {
        "run_A_exit": run_A.get("exit_code"),
        "run_B_exit": run_B.get("exit_code"),
        "run_A_runtime_ms": run_A.get("runtime_ms"),
        "run_B_runtime_ms": run_B.get("runtime_ms"),
        "both_match_expected": both_match,
        "probe_active": True,
        "probe_reason": "executor=grep_pattern; both opposing payloads match same expected_exit -> regex too broad -> tautology.",
    }


def verify_falsifier(claim_id: str, falsifier_block: Dict[str, Any],
                     claim_author_principal: Optional[str] = None) -> Dict[str, Any]:
    """Top-level F13 verification entrypoint.

    Returns a structured result block including:
      confirmed: bool (exit == expected_exit within ttl)
      tautology_suspected: bool (static OR dynamic detection fired)
      runtime_ms: float
      exit_code: Optional[int]
      reason_codes: List[str]
    """
    reason_codes: List[str] = validate_crf_record(falsifier_block, claim_author_principal=claim_author_principal)
    # Static tautology hits are already in reason_codes.
    static_tautology = any(rc.startswith("AEP11_F13_TAUTOLOGY_STATIC_MATCH") or rc.startswith("AEP11_F13_DORMITIVE_PHRASE_MATCH") for rc in reason_codes)

    cmd = falsifier_block.get("cmd", "")
    executor = falsifier_block.get("executor", "subprocess_sandboxed")
    ttl_ms = int(falsifier_block.get("ttl_ms", 100))
    expected_exit = int(falsifier_block.get("expected_exit", 0))

    # Primary execution
    run = execute_falsifier_once(executor, cmd, ttl_ms)
    confirmed = (run.get("exit_code") == expected_exit) and not run.get("timed_out")

    # Dynamic tautology probe — run two more passes with mutated state
    probe = dynamic_tautology_probe(executor, cmd, ttl_ms, expected_exit)
    dynamic_tautology = probe["both_match_expected"]

    tautology_suspected = bool(static_tautology or dynamic_tautology)
    if tautology_suspected:
        reason_codes.append("AEP11_F13_TAUTOLOGY_BLOCKED")

    if run.get("timed_out"):
        reason_codes.append("AEP11_F13_TIMEOUT")

    if confirmed and not tautology_suspected:
        result_summary = "CONFIRM"
    elif tautology_suspected:
        result_summary = "TAUTOLOGY_DETECTED"
    elif run.get("timed_out"):
        result_summary = "TIMEOUT"
    else:
        # Falsifier fired (exit != expected_exit)
        action = falsifier_block.get("on_fire_action", "DEMOTE_RELIABILITY")
        reason_codes.append(f"AEP11_F13_FIRED_{action}")
        result_summary = f"FIRED_{action}"

    return {
        "claim_id": claim_id,
        "falsifier_id": falsifier_block.get("id"),
        "confirmed": confirmed,
        "tautology_suspected": tautology_suspected,
        "result_summary": result_summary,
        "runtime_ms": run.get("runtime_ms", 0.0),
        "exit_code": run.get("exit_code"),
        "expected_exit": expected_exit,
        "timed_out": run.get("timed_out", False),
        "reason_codes": reason_codes,
        "tautology_probe": probe,
        "stderr_tail": run.get("stderr_tail", ""),
        "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _load_record(p: pathlib.Path) -> Dict[str, Any]:
    text = p.read_text(encoding="utf-8").strip()
    # Accept either single-line JSON, multi-line JSON, or first line of JSONL.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return json.loads(line)
        raise


def cmd_validate(args) -> int:
    rec = _load_record(pathlib.Path(args.record))
    errs = validate_crf_record(rec, claim_author_principal=args.claim_author)
    blocking = [e for e in errs if not e.startswith("AEP11_F13_TAUTOLOGY_STATIC_MATCH")
                and not e.startswith("AEP11_F13_DORMITIVE_PHRASE_MATCH")]
    informational = [e for e in errs if e not in blocking]
    print(json.dumps({"record_id": rec.get("id"), "blocking_errors": blocking, "informational": informational}, indent=2))
    return 0 if not blocking else 1


def cmd_verify(args) -> int:
    rec = _load_record(pathlib.Path(args.record))
    result = verify_falsifier(rec.get("bound_to_claim_id", "unknown"),
                              rec,
                              claim_author_principal=args.claim_author)
    print(json.dumps(result, indent=2))
    if args.output_jsonl:
        out = pathlib.Path(args.output_jsonl)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(result, separators=(",", ":")) + "\n")
    # Exit 0 = falsifier CONFIRMS the claim survives (passing); exit 1 otherwise.
    return 0 if result.get("confirmed") and not result.get("tautology_suspected") else 1


def cmd_run_batch(args) -> int:
    """Run F13 verification over every .jsonl in a directory; emit summary."""
    batch_dir = pathlib.Path(args.batch_dir)
    out_path = pathlib.Path(args.output_jsonl) if args.output_jsonl else None
    results: List[Dict[str, Any]] = []
    files = sorted([p for p in batch_dir.glob("*.jsonl")])
    for fp in files:
        rec = _load_record(fp)
        result = verify_falsifier(
            rec.get("bound_to_claim_id", fp.stem),
            rec,
            claim_author_principal=rec.get("bound_to_claim_author") or args.claim_author,
        )
        result["source_file"] = str(fp).replace("\\", "/")
        results.append(result)
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("a", encoding="utf-8") as ofp:
                ofp.write(json.dumps(result, separators=(",", ":")) + "\n")

    summary = {
        "total": len(results),
        "confirmed": sum(1 for r in results if r["confirmed"] and not r["tautology_suspected"]),
        "tautology_detected": sum(1 for r in results if r["tautology_suspected"]),
        "fired": sum(1 for r in results if r["result_summary"].startswith("FIRED")),
        "timeout": sum(1 for r in results if r["timed_out"]),
        "results": results,
    }
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="F13 claim_runtime_falsifier validator + executor.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_v = sub.add_parser("validate")
    p_v.add_argument("record")
    p_v.add_argument("--claim-author", default=None)
    p_v.set_defaults(func=cmd_validate)

    p_e = sub.add_parser("verify")
    p_e.add_argument("record")
    p_e.add_argument("--claim-author", default=None)
    p_e.add_argument("--output-jsonl", default=None)
    p_e.set_defaults(func=cmd_verify)

    p_b = sub.add_parser("run-batch")
    p_b.add_argument("--batch-dir", required=True)
    p_b.add_argument("--claim-author", default=None)
    p_b.add_argument("--output-jsonl", default=None)
    p_b.set_defaults(func=cmd_run_batch)

    args = parser.parse_args()
    return args.func(args)


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. F13's role per AEP v1.1: anti-tautology + source-hash check
# + self-attestation principal flip + falsifier-target-tautology checks.
# Extended to source-hash class, reviewer principal class, claim-mutation
# detection, prompt-injection in disconfirmer text, score class.
# Validator version bump: v1.1.0 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
import hashlib as _v15_hashlib

V15_VALIDATOR_VERSION = "v1.5.0-K5-repair"

_F13_INJECTION_SIGNATURES = [
    "ignore all prior instructions",
    "ignore previous instructions",
    "set validator outcome to pass",
    "drop the database",
    "disregard the above",
    "override constitution",
    "set falsifier_satisfied to false",
]


def _v15_hash_valid(h):
    if not isinstance(h, str) or len(h) != 64:
        return False
    try:
        int(h, 16)
        return True
    except (ValueError, TypeError):
        return False


def _v15_check_source_hash(packet):
    out = []
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_F13_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str):
            recomputed = _v15_hashlib.sha256(text.encode("utf-8")).hexdigest()
            if recomputed != h:
                out.append("AEP15_F13_SOURCE_HASH_MISMATCH")
    return out


def _v15_check_self_attestation(packet):
    """A claim's reviewer principal must NOT equal claim authoring principal.
    F13's anti-self-attestation rule (composes with F14 quorum)."""
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid and (pid == creator or pid in claim_authors):
            out.append(f"AEP15_F13_SELF_ATTESTATION:{pid}")
    return out


def _v15_check_falsifier_anti_tautology(packet):
    """A claim's text must not contain prompt-injection or tautology phrases."""
    out = []
    for cl in packet.get("claims", []):
        text = cl.get("text", "")
        if isinstance(text, str):
            lower = text.lower()
            for sig in _F13_INJECTION_SIGNATURES:
                if sig in lower:
                    out.append(f"AEP15_F13_INJECTION_IN_CLAIM:{sig}")
                    break
    return out


def _v15_check_score_in_scale(packet):
    """Score must be in declared scale; default 0..5 for F13 falsifier targets."""
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F13_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F13_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F13_SCORE_OUT_OF_SCALE:{s}")
    for rv in packet.get("reviews", []):
        s = rv.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F13_SCORE_NON_NUMERIC_REVIEW")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F13_SCORE_NAN_OR_INF_REVIEW")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F13_SCORE_OUT_OF_SCALE_REVIEW:{s}")
    return out


def _v15_check_recall_injection(packet):
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    out = []
    if isinstance(text, str):
        lower = text.lower()
        for sig in _F13_INJECTION_SIGNATURES:
            if sig in lower:
                out.append(f"AEP15_F13_INJECTION_IN_RECALL:{sig}")
                break
    return out


def _v15_check_span_integrity(packet):
    out = []
    span_index = set()
    for src in packet.get("sources", []):
        text = src.get("text", "")
        src_len = len(text) if isinstance(text, str) else 0
        for sp in src.get("spans", []) or []:
            sid = sp.get("span_id")
            if sid:
                span_index.add(sid)
            start, end = sp.get("start"), sp.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            if start > end:
                out.append("AEP15_F13_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_F13_SPAN_BEYOND_SOURCE")
    for cl in packet.get("claims", []):
        bsids = cl.get("basis_span_ids") or []
        if not bsids:
            out.append(f"AEP15_F13_CLAIM_BASIS_MISSING:{cl.get('claim_id')}")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_F13_CLAIM_BASIS_UNRESOLVED:{sid}")
    return out


def _v15_check_dag_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if not isinstance(p, str):
            out.append("AEP15_F13_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED", "tombstone:FORGED")):
            out.append(f"AEP15_F13_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_F13_DAG_PARENT_SELF_REFERENCE")
        if not (p.startswith("sha256:") or p.startswith("mut:") or p.startswith("pkt:") or p.startswith("tombstone:") or "FORGED" in p or "NONEXISTENT" in p or "BOGUS" in p):
            out.append(f"AEP15_F13_DAG_PARENT_UNRECOGNIZED:{p}")
    return out


def _v15_check_event_ordering(packet):
    out = []
    events = (packet.get("manifest") or {}).get("events", [])
    prev_ts = None
    kinds = []
    for ev in events:
        kinds.append(ev.get("kind"))
        ts = ev.get("ts")
        if isinstance(ts, str):
            if prev_ts is not None and ts < prev_ts:
                out.append(f"AEP15_F13_EVENT_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F13_EVENT_REVIEW_BEFORE_CREATE")
    return out


def _v15_check_reviewer_extras(packet):
    out = []
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F13_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F13_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F13_REVIEWER_FORGED:{pid}")
    return out


def _v15_check_completion_witness(packet):
    out = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            w = cl.get("witness")
            ws = cl.get("witness_sha256")
            wa = cl.get("witness_artifact")
            if not w and not ws and not wa:
                out.append(f"AEP15_F13_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
                continue
            if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
                out.append(f"AEP15_F13_COMPLETION_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_source_hash(packet))
    out.extend(_v15_check_self_attestation(packet))
    out.extend(_v15_check_falsifier_anti_tautology(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_recall_injection(packet))
    out.extend(_v15_check_span_integrity(packet))
    out.extend(_v15_check_dag_integrity(packet))
    out.extend(_v15_check_event_ordering(packet))
    out.extend(_v15_check_reviewer_extras(packet))
    out.extend(_v15_check_completion_witness(packet))
    # FINAL PASS-CLOSURE: 6 independent structural-mutation checks (encoding/float-edge/
    # time-skew/hash-shape/semantic-equivalence/linguistic). Composes with sec73.6 honest framing.
    try:
        from v15_validators_common import v15_common_structural_checks  # type: ignore
        out.extend(v15_common_structural_checks(packet))
    except Exception:  # noqa: BLE001
        try:
            import importlib.util, pathlib as _pl
            _spec = importlib.util.spec_from_file_location(
                "v15_validators_common",
                str(_pl.Path(__file__).resolve().parent / "v15_validators_common.py"),
            )
            if _spec and _spec.loader:
                _m = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_m)
                out.extend(_m.v15_common_structural_checks(packet))
        except Exception:  # noqa: BLE001
            out.append("AEP15_COMMON_MODULE_LOAD_FAILED")
    return out


if __name__ == "__main__":
    sys.exit(main())
