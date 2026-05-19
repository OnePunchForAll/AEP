#!/usr/bin/env python3
"""aep_stop_doctor.py - AEP v1.5 LTS Stop hook (K12 AEP Doctor Supreme).

Per operator v1.5 LTS Phase 2+3 directive: at session/turn end, run a
lightweight doctor check across recent ledger rows + prompt contracts +
completion claims. Emit one of seven verdicts to a receipts ledger.

Verdicts:
  PASS         - all transactions complete + all completion claims have
                 witnesses + no airlock violations
  WARN         - some open transactions or weak completion signals
  FAIL         - any airlock violation or completion claim without witness
  UNKNOWN      - insufficient data
  EXPIRED      - claims past TTL not revalidated
  CONTESTED    - concurrent edits detected (same path written twice with
                 no intervening read - heuristic only)
  QUARANTINED  - any explicit policy violation surfaced (e.g. powershell
                 invocation block + retry attempted)

Per sec68 - Python only.
Per sec73.5 - WARDEN RECEIPTS - every verdict creates audit row.
Per K12 - doctor verdict is informational; never fail-block.

Performance target: p95 <= 500ms (cached: 300ms; normal: 1500ms per
constitution.performance_gates.normal_doctor_p95_ms).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_VERDICT_LOG = _REPO_ROOT / ".claude" / "aep" / "receipts" / "stop_doctor_verdicts.jsonl"
_PERF_LOG = _REPO_ROOT / ".claude" / "aep" / "perf" / "stop_doctor_latency.jsonl"

_LEDGER_PATH = _REPO_ROOT / ".claude" / "aep" / "transactions" / "post_tool_ledger.jsonl"
_PRE_TXN_PATH = _REPO_ROOT / ".claude" / "aep" / "transactions" / "pre_tool_begin.jsonl"
_CONTRACT_PATH = _REPO_ROOT / ".claude" / "aep" / "transactions" / "prompt_contracts.jsonl"
_BLOCK_PATH = _REPO_ROOT / ".claude" / "_logs" / "aep-v15-lts-pre-tool-blocks.jsonl"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _sha256_canonical(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _append_jsonl(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _read_jsonl_tail(path: Path, max_lines: int = 200) -> list[dict]:
    """Read last N JSONL rows from a file. Returns oldest-first."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    tail = [ln for ln in lines[-max_lines:] if ln.strip()]
    rows = []
    for ln in tail:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def _parse_ts(s: str):
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _within_window(row_ts_str: str, window_seconds: int) -> bool:
    ts = _parse_ts(row_ts_str)
    if ts is None:
        return False
    return (_utc_now() - ts).total_seconds() <= window_seconds


# ---------------------------------------------------------------------------
# Doctor checks
# ---------------------------------------------------------------------------
def check_airlock_blocks(session_id: str) -> dict:
    """Count recent airlock blocks. Any in the session window = FAIL signal."""
    rows = _read_jsonl_tail(_BLOCK_PATH, 500)
    recent = [r for r in rows if _within_window(r.get("ts", ""), 3600)]
    session_rows = [r for r in recent if r.get("session_id") in ("", session_id)]
    critical = [r for r in recent if "secret" in (r.get("reason") or "").lower() or "powershell" in (r.get("reason") or "").lower()]
    return {
        "recent_block_count": len(recent),
        "critical_block_count": len(critical),
        "any_block_in_window": len(recent) > 0,
        "any_critical_block": len(critical) > 0,
    }


def check_open_transactions(session_id: str) -> dict:
    """Compare pre_tool_begin against post_tool_ledger to find unclosed transactions."""
    pre_rows = _read_jsonl_tail(_PRE_TXN_PATH, 500)
    post_rows = _read_jsonl_tail(_LEDGER_PATH, 500)
    pre_recent = [r for r in pre_rows if _within_window(r.get("ts", ""), 3600)]
    post_hashes = set(r.get("tool_input_sha256") for r in post_rows if _within_window(r.get("ts", ""), 7200))
    unclosed = [r for r in pre_recent if r.get("tool_input_sha256") not in post_hashes]
    return {
        "pre_count": len(pre_recent),
        "open_count": len(unclosed),
        "any_open": len(unclosed) > 0,
    }


def check_completion_signals(session_id: str) -> dict:
    """Inspect recent prompt contracts. For each contract with success_criteria,
    check whether the recent post-tool ledger contains corresponding witnesses
    (file_hashes_after non-empty for at least one criterion path)."""
    contracts = _read_jsonl_tail(_CONTRACT_PATH, 100)
    contracts = [c for c in contracts if _within_window(c.get("ts", ""), 7200)]
    if not contracts:
        return {"contract_count": 0, "weak_completion_count": 0, "missing_witness_count": 0}
    post_rows = _read_jsonl_tail(_LEDGER_PATH, 500)
    post_recent = [r for r in post_rows if _within_window(r.get("ts", ""), 7200)]
    # Build set of paths written
    paths_witnessed = set()
    for r in post_recent:
        for p in (r.get("target_paths") or []):
            if (r.get("file_hashes_after") or {}).get(p):
                paths_witnessed.add(p.replace("\\", "/"))

    weak = 0
    missing_witness = 0
    for c in contracts:
        scope_paths = (c.get("scope") or {}).get("paths") or []
        if not scope_paths:
            continue
        scope_paths_norm = [p.replace("\\", "/") for p in scope_paths]
        any_witness = any(p in paths_witnessed for p in scope_paths_norm)
        if c.get("risk_tier") in ("Professional", "Critical") and not any_witness:
            missing_witness += 1
        elif not any_witness:
            weak += 1
    return {
        "contract_count": len(contracts),
        "weak_completion_count": weak,
        "missing_witness_count": missing_witness,
    }


def check_concurrent_edits(session_id: str) -> dict:
    """Detect same-path writes within 60s with no intervening read.
    Heuristic only - true concurrency requires a richer model."""
    post_rows = _read_jsonl_tail(_LEDGER_PATH, 200)
    post_recent = [r for r in post_rows if _within_window(r.get("ts", ""), 3600)]
    by_path = {}
    for r in post_recent:
        if r.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
            continue
        for p in (r.get("target_paths") or []):
            by_path.setdefault(p, []).append(r)
    contested = 0
    for p, rs in by_path.items():
        if len(rs) < 2:
            continue
        ts_list = sorted((_parse_ts(r.get("ts", "")) for r in rs if _parse_ts(r.get("ts", ""))))
        for i in range(1, len(ts_list)):
            if (ts_list[i] - ts_list[i - 1]).total_seconds() < 60:
                contested += 1
                break
    return {"contested_path_count": contested, "any_contested": contested > 0}


def check_powershell_in_session(session_id: str) -> dict:
    """Check if any QUARANTINE-class block fired (e.g. powershell attempt)."""
    rows = _read_jsonl_tail(_BLOCK_PATH, 200)
    recent = [r for r in rows if _within_window(r.get("ts", ""), 3600)]
    quarantine = [r for r in recent if r.get("rule_id", "").startswith("AEP-1.5-BASH-POWERSHELL")
                  or r.get("rule_id", "").startswith("AEP-1.5-BASH-DISABLE-HOOKS")]
    return {"quarantine_block_count": len(quarantine), "any_quarantine": len(quarantine) > 0}


def synthesize_verdict(checks: dict) -> tuple[str, list]:
    """Synthesize a single verdict from the checks dict.

    Order of evaluation (highest severity first):
      QUARANTINED > FAIL > CONTESTED > EXPIRED > WARN > PASS > UNKNOWN
    """
    risks = []

    if checks["powershell"]["any_quarantine"]:
        risks.append("quarantine_class_block_in_session")
        return "QUARANTINED", risks

    if checks["airlock"]["any_critical_block"]:
        risks.append("critical_airlock_block_in_window")
        return "FAIL", risks

    if checks["completion"]["missing_witness_count"] > 0:
        risks.append(f"professional_or_critical_contracts_without_witness={checks['completion']['missing_witness_count']}")
        return "FAIL", risks

    if checks["concurrent"]["any_contested"]:
        risks.append(f"contested_paths={checks['concurrent']['contested_path_count']}")
        return "CONTESTED", risks

    # No EXPIRED detection yet (would need TTL field in contracts) - reserved.

    if checks["transactions"]["any_open"]:
        risks.append(f"open_transactions={checks['transactions']['open_count']}")
        return "WARN", risks

    if checks["airlock"]["any_block_in_window"]:
        risks.append(f"non_critical_airlock_blocks={checks['airlock']['recent_block_count']}")
        return "WARN", risks

    if checks["completion"]["weak_completion_count"] > 0:
        risks.append(f"weak_completion_signals={checks['completion']['weak_completion_count']}")
        return "WARN", risks

    if checks["completion"]["contract_count"] == 0 and checks["transactions"]["pre_count"] == 0:
        return "UNKNOWN", ["no_session_signal"]

    return "PASS", []


def next_action(verdict: str, risks: list) -> str:
    if verdict == "QUARANTINED":
        return "operator_review_required_dot_no_autonomous_recovery_dot_sec68_path"
    if verdict == "FAIL":
        return "halt_autonomous_work_dot_emit_lesson_dot_request_operator_review"
    if verdict == "CONTESTED":
        return "reconcile_concurrent_edits_via_diff_review"
    if verdict == "EXPIRED":
        return "revalidate_or_drop_stale_claims"
    if verdict == "WARN":
        return "close_open_transactions_and_witness_completions"
    if verdict == "PASS":
        return "proceed_dot_session_clean"
    return "gather_more_signal_before_proceed"


def main() -> int:
    t0 = time.perf_counter()
    try:
        raw = sys.stdin.read()
        event = {}
        if raw.strip():
            try:
                event = json.loads(raw)
            except Exception:
                event = {}
        session_id = event.get("session_id") or event.get("sessionId") or ""

        checks = {
            "airlock": check_airlock_blocks(session_id),
            "transactions": check_open_transactions(session_id),
            "completion": check_completion_signals(session_id),
            "concurrent": check_concurrent_edits(session_id),
            "powershell": check_powershell_in_session(session_id),
        }
        verdict, risks = synthesize_verdict(checks)

        row = {
            "ts": _utc_now_iso(),
            "session_id": session_id,
            "verdict": verdict,
            "open_risks": risks,
            "next_action": next_action(verdict, risks),
            "checks": checks,
            "schema_version": "v1.5.0-lts",
        }
        row["row_sha256"] = _sha256_canonical(row)

        _append_jsonl(_VERDICT_LOG, row)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "decision": f"verdict_{verdict.lower()}",
            "latency_ms": round(latency_ms, 3),
        })
        return 0
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "decision": "internal_error",
            "latency_ms": round(latency_ms, 3),
            "error_type": type(e).__name__,
        })
        sys.stderr.write(f"[aep_stop_doctor:INTERNAL_ERROR] {type(e).__name__}: {e}\n")
        # Stop hook is informational - exit 0 on any error.
        return 0


if __name__ == "__main__":
    sys.exit(main())
