#!/usr/bin/env python3
"""aep_post_tool_ledger.py - AEP v1.5 LTS PostToolUse hook (K6 Evidence Transaction Journal).

Per operator v1.5 LTS Phase 2+3 directive: this hook captures EVERY tool
execution outcome as an append-only HCRL-chained ledger row.

Behaviors:
  - Record tool name, input hash, target paths, exit status
  - Compute file diff sha256 if Edit/Write target known
  - Bind to PreToolUse begin row via transaction_id if available
  - Log latency to .claude/aep/perf/post_tool_use_latency.jsonl
  - Append ledger row to .claude/aep/transactions/post_tool_ledger.jsonl

Per sec68 - Python only.
Per sec73.5 - WARDEN RECEIPTS - every action emits chained receipt.
Per K6 - append-only journal; no row mutation.

Performance target: p95 <= 150ms.
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
_PERF_LOG = _REPO_ROOT / ".claude" / "aep" / "perf" / "post_tool_use_latency.jsonl"
_LEDGER_LOG = _REPO_ROOT / ".claude" / "aep" / "transactions" / "post_tool_ledger.jsonl"
_PRE_TXN_LOG = _REPO_ROOT / ".claude" / "aep" / "transactions" / "pre_tool_begin.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_canonical(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_file(p: Path) -> str:
    try:
        if p.is_file() and p.stat().st_size < 50 * 1024 * 1024:
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


def _last_ledger_row_sha() -> str:
    """Return the row_sha256 of the last row in the ledger, or empty string."""
    try:
        if not _LEDGER_LOG.exists():
            return ""
        # Read last non-empty line (small ledger - safe to scan tail; for very large
        # ledgers a tail-seek implementation would replace this).
        last = ""
        with _LEDGER_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line.strip()
        if not last:
            return ""
        row = json.loads(last)
        return row.get("row_sha256", "")
    except Exception:
        return ""


def _find_matching_pre_txn(tool_input_sha: str) -> str:
    """Find a PreToolUse begin row that matches this tool_input_sha256.

    Returns txn_id or empty string. Best-effort; reads the recent tail only.
    """
    try:
        if not _PRE_TXN_LOG.exists():
            return ""
        # Reverse scan - last 200 lines is plenty
        lines = _PRE_TXN_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-200:]):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("tool_input_sha256") == tool_input_sha:
                return row.get("txn_id", "")
        return ""
    except Exception:
        return ""


def _extract_paths(tool_name: str, tool_input: dict) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    paths = []
    for key in ("file_path", "path", "notebook_path"):
        v = tool_input.get(key)
        if isinstance(v, str):
            paths.append(v)
    if isinstance(tool_input.get("edits"), list):
        for e in tool_input["edits"]:
            if isinstance(e, dict) and isinstance(e.get("file_path"), str):
                paths.append(e["file_path"])
    return paths


def _extract_status(event: dict) -> dict:
    """Extract tool-response status from the PostToolUse event."""
    response = event.get("tool_response") or event.get("toolResponse") or {}
    if not isinstance(response, dict):
        response = {"raw": str(response)[:200]}
    status = {
        "is_error": bool(response.get("is_error") or response.get("isError")),
        "interrupted": bool(response.get("interrupted")),
    }
    # Extract exit code if Bash
    if "exit_code" in response:
        status["exit_code"] = response.get("exit_code")
    elif "exitCode" in response:
        status["exit_code"] = response.get("exitCode")
    return status


def main() -> int:
    t0 = time.perf_counter()
    tool_name = ""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            _append_jsonl(_PERF_LOG, {
                "ts": _utc_now_iso(),
                "decision": "skip_no_event",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            })
            return 0

        event = json.loads(raw)
        tool_name = event.get("tool_name") or event.get("toolName") or ""
        tool_input = event.get("tool_input") or event.get("toolInput") or {}
        session_id = event.get("session_id") or event.get("sessionId") or ""
        cwd = event.get("cwd") or os.getcwd()

        tool_input_sha = _sha256_canonical(tool_input if isinstance(tool_input, dict) else {})
        paths = _extract_paths(tool_name, tool_input if isinstance(tool_input, dict) else {})
        status = _extract_status(event)
        pre_txn_id = _find_matching_pre_txn(tool_input_sha)

        # Compute post-write file hash for Edit/Write/MultiEdit targets
        file_hashes_after = {}
        if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            for p in paths[:8]:  # cap at 8 to bound latency
                try:
                    pp = Path(p)
                    if pp.is_file():
                        file_hashes_after[p] = _sha256_file(pp)
                except Exception:
                    pass

        # Build receipt row
        prev_hash = _last_ledger_row_sha()
        row = {
            "ts": _utc_now_iso(),
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input_sha256": tool_input_sha,
            "target_paths": paths,
            "status": status,
            "pre_txn_id": pre_txn_id,
            "file_hashes_after": file_hashes_after,
            "prev_row_sha256": prev_hash,
            "actor": "aep_post_tool_ledger",
            "schema_version": "v1.5.0-lts",
        }
        row["row_sha256"] = _sha256_canonical(row)

        _append_jsonl(_LEDGER_LOG, row)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "tool_name": tool_name,
            "decision": "ledger_recorded",
            "latency_ms": round(latency_ms, 3),
        })
        return 0
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "tool_name": tool_name,
            "decision": "internal_error",
            "latency_ms": round(latency_ms, 3),
            "error_type": type(e).__name__,
        })
        # Fail-OPEN on PostToolUse - this is an audit hook, not a gate.
        sys.stderr.write(f"[aep_post_tool_ledger:INTERNAL_ERROR] {type(e).__name__}: {e}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
