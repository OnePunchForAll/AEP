#!/usr/bin/env python3
"""aep_precompact_kernel.py - AEP v1.5 LTS PreCompact hook (K4/K5 Compaction Survival Kernel).

Per operator v1.5 LTS Phase 2+3 directive: when the session approaches
compaction (Claude Code's PreCompact event), distill the load-bearing
state into a <=200-token kernel and persist it so the post-compaction
continuation can replay context without re-deriving everything.

Payload preserved:
  - constitution pointer (path + sha256 of constitution file)
  - active task contract (from last UserPromptSubmit row in this session)
  - success criteria (from contract)
  - forbidden actions (from constitution + contract)
  - source scope (file paths touched this session, from post-tool ledger)
  - unresolved risks (open FAIL/WARN signals from doctor's last verdict)
  - current evidence refs (recent transaction IDs)
  - next action (recommended by doctor)

Output: append a compact JSON-line row to .claude/aep/cache/compaction_kernels.jsonl.

Per sec68 - Python only.
Per K5 - kernel <=200 tokens (~800 chars). Compactness is the design.

Performance target: p95 <= 200ms.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONSTITUTION_PATH = _REPO_ROOT / ".claude" / "aep" / "constitution" / "aep_constitution_v1_5_lts.json"
_KERNEL_OUT = _REPO_ROOT / ".claude" / "aep" / "cache" / "compaction_kernels.jsonl"
_PERF_LOG = _REPO_ROOT / ".claude" / "aep" / "perf" / "precompact_latency.jsonl"

_LEDGER_PATH = _REPO_ROOT / ".claude" / "aep" / "transactions" / "post_tool_ledger.jsonl"
_CONTRACT_PATH = _REPO_ROOT / ".claude" / "aep" / "transactions" / "prompt_contracts.jsonl"
_VERDICT_PATH = _REPO_ROOT / ".claude" / "aep" / "receipts" / "stop_doctor_verdicts.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_canonical(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256_file(p: Path) -> str:
    try:
        if p.is_file():
            return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        pass
    return ""


def _append_jsonl(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _read_jsonl_tail(path: Path, n: int = 100) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    rows = []
    for ln in lines[-n:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def _latest_for_session(rows: list[dict], session_id: str) -> dict:
    if not rows:
        return {}
    if session_id:
        sess = [r for r in rows if r.get("session_id") == session_id]
        if sess:
            return sess[-1]
    return rows[-1]


def _token_estimate(s: str) -> int:
    return max(1, len(s) // 4)


def _truncate_list(xs, max_items, max_chars_each):
    if not isinstance(xs, list):
        return []
    return [str(x)[:max_chars_each] for x in xs[:max_items]]


def build_kernel(session_id: str, trigger: str) -> dict:
    constitution_sha = _sha256_file(_CONSTITUTION_PATH)
    contract = _latest_for_session(_read_jsonl_tail(_CONTRACT_PATH, 50), session_id)
    verdict = _latest_for_session(_read_jsonl_tail(_VERDICT_PATH, 20), session_id)

    # Collect source scope from recent ledger writes
    ledger_rows = _read_jsonl_tail(_LEDGER_PATH, 100)
    if session_id:
        sess_rows = [r for r in ledger_rows if r.get("session_id") == session_id]
        if sess_rows:
            ledger_rows = sess_rows
    source_paths = []
    seen = set()
    for r in ledger_rows:
        for p in (r.get("target_paths") or []):
            p_norm = p.replace("\\", "/")
            if p_norm not in seen:
                seen.add(p_norm)
                source_paths.append(p_norm)
    source_paths = source_paths[-16:]  # last 16 only

    evidence_refs = []
    for r in ledger_rows[-8:]:
        if r.get("row_sha256"):
            evidence_refs.append(r["row_sha256"][:12])

    kernel = {
        "ts": _utc_now_iso(),
        "session_id": session_id,
        "trigger": trigger,
        "schema_version": "v1.5.0-lts",
        "constitution_ptr": {
            "path": ".claude/aep/constitution/aep_constitution_v1_5_lts.json",
            "sha256": constitution_sha,
        },
        "active_task": {
            "intent": (contract.get("intent") or "")[:200],
            "risk_tier": contract.get("risk_tier", ""),
            "output_format": contract.get("output_format", ""),
            "stop_condition": (contract.get("stop_condition") or "")[:160],
            "operator_authority_invoked": bool(contract.get("operator_authority_invoked")),
            "burn_required": bool(contract.get("burn_required")),
        },
        "success_criteria": _truncate_list(contract.get("success_criteria"), 8, 140),
        "forbidden_actions_head": _truncate_list(contract.get("forbidden_actions"), 10, 120),
        "source_scope": source_paths,
        "evidence_refs": evidence_refs,
        "unresolved_risks": _truncate_list(verdict.get("open_risks"), 6, 100),
        "next_action": (verdict.get("next_action") or "")[:120],
        "last_verdict": verdict.get("verdict", ""),
    }
    # Compute final token estimate
    kernel_str = json.dumps(kernel, separators=(",", ":"))
    kernel["token_estimate"] = _token_estimate(kernel_str)
    kernel["row_sha256"] = _sha256_canonical({k: v for k, v in kernel.items() if k != "row_sha256"})
    return kernel


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
        trigger = event.get("trigger") or event.get("reason") or "precompact"
        custom_instructions = event.get("custom_instructions") or ""

        kernel = build_kernel(session_id, str(trigger))
        if custom_instructions:
            kernel["operator_custom_instructions_first_200"] = str(custom_instructions)[:200]

        _append_jsonl(_KERNEL_OUT, kernel)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "decision": "kernel_persisted",
            "latency_ms": round(latency_ms, 3),
            "token_estimate": kernel.get("token_estimate"),
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
        sys.stderr.write(f"[aep_precompact_kernel:INTERNAL_ERROR] {type(e).__name__}: {e}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
