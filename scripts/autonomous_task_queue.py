"""autonomous_task_queue.py — operator directive 2026-05-16.

Persistent task queue for the agent's autonomous takeover loop. the agent reads this
file in the HUDDLE step to identify stopped/failed tasks from prior waves
(MUST carry forward into next wave per operator's explicit rule).

Schema (append-only JSONL):
  {
    wave_id: str,                 # YYYY-MM-DDTHH-MM-SS-wave-NNN
    task_id: str,                 # <wave_id>-task-<NN>
    agent: str,                   # canonical agent name (1 of 10)
    mission: str,                 # task description
    status: str,                  # pending|dispatched|completed|failed|stopped|carry-forward
    dispatched_at: str|null,
    completed_at: str|null,
    duration_ms: int|null,
    operator_huddle_visible: bool,# true if surfaced in transcript huddle
    notes: str,
    superseding_task_id: str|null,# if carry-forward, links to next-wave task
  }

CLI:
  --append-task       Record a newly-dispatched task
  --mark-completed    Mark task as completed (with duration)
  --mark-failed       Mark task as failed (with reason)
  --mark-stopped      Mark task as stopped (operator-cancel)
  --recover-pending   Print all carry-forward-eligible tasks for next huddle
  --huddle-summary    Print summary of recent wave for transcript
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


# BP-C-AN1 closure (forge Wave-D 2026-05-16): OS-portable advisory file-lock.
# Wraps every write_row append. Two concurrent dispatchers can no longer
# interleave bytes in the middle of a JSON line.
#
# Lock implementation per platform:
#   - Windows: msvcrt.locking(fd, msvcrt.LK_LOCK, ...) (blocks; LK_RLCK is
#     equivalent for our exclusive-append use). LK_LOCK has a 10-retry default;
#     we wrap in an explicit retry loop to extend that to ~30 attempts.
#   - POSIX:   fcntl.flock(fd, fcntl.LOCK_EX). Blocking; release on close.
#
# This is an ADVISORY lock — cooperating processes that call _locked_append()
# are serialized; a non-cooperating writer (e.g. hand-edit) can still corrupt.
# That's acceptable because the queue is only written by this script.
if sys.platform == "win32":
    import msvcrt as _msvcrt  # type: ignore[import-not-found]
    _fcntl = None  # type: ignore[assignment]
else:
    _msvcrt = None  # type: ignore[assignment]
    import fcntl as _fcntl  # type: ignore[import-not-found]


REPO_ROOT = Path("C:/Users/example-user/")
QUEUE_PATH = REPO_ROOT / ".claude" / "diana" / "autonomous-task-queue.jsonl"
QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
if not QUEUE_PATH.exists():
    QUEUE_PATH.write_text("", encoding="utf-8")

# Lock-acquire retry budget (Windows msvcrt.LK_LOCK retries 10x at 1s each =
# 10s; we wrap to extend to ~30s total via explicit re-attempts on LockError).
_LOCK_MAX_ATTEMPTS = 3
_LOCK_RETRY_DELAY_S = 0.05  # initial; doubles per attempt (max ~0.4s)


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_all() -> list[dict]:
    rows = []
    for line in QUEUE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


@contextmanager
def _file_lock(file_handle):
    """BP-C-AN1 closure (forge Wave-D 2026-05-16): OS-portable advisory lock.

    On Windows uses msvcrt.locking on the first byte (LK_LOCK = blocking +
    10-retry-1s default). On POSIX uses fcntl.flock LOCK_EX (blocking).

    Releases unconditionally in finally; even if the caller raises.

    The lock is held over the file_handle for the duration of the with-block.
    Wraps in a retry loop because Windows LK_LOCK can raise OSError on
    contention after its internal retries are exhausted; we get up to
    _LOCK_MAX_ATTEMPTS chances to land the lock.
    """
    last_err: Exception | None = None
    delay = _LOCK_RETRY_DELAY_S
    locked = False
    for attempt in range(1, _LOCK_MAX_ATTEMPTS + 1):
        try:
            if _msvcrt is not None:
                # Windows: lock 1 byte at current offset (file is just-opened
                # for append; offset = end of file). LK_LOCK = blocking;
                # internally retries 10x at 1s each before raising OSError.
                # Seek to 0 to lock the same byte regardless of file size.
                file_handle.seek(0, 0)
                _msvcrt.locking(file_handle.fileno(), _msvcrt.LK_LOCK, 1)
                # Restore seek to end for append
                file_handle.seek(0, 2)
            else:
                assert _fcntl is not None
                _fcntl.flock(file_handle.fileno(), _fcntl.LOCK_EX)
            locked = True
            break
        except OSError as exc:
            last_err = exc
            if attempt < _LOCK_MAX_ATTEMPTS:
                time.sleep(delay)
                delay = min(delay * 2, 0.4)
                continue
            # exhausted; re-raise wrapped
            raise OSError(
                f"file lock contention after {_LOCK_MAX_ATTEMPTS} attempts: "
                f"{exc!r}"
            ) from exc
    try:
        yield
    finally:
        if locked:
            try:
                if _msvcrt is not None:
                    file_handle.seek(0, 0)
                    _msvcrt.locking(file_handle.fileno(), _msvcrt.LK_UNLCK, 1)
                else:
                    assert _fcntl is not None
                    _fcntl.flock(file_handle.fileno(), _fcntl.LOCK_UN)
            except OSError:
                # Best-effort unlock; OS will release on close anyway
                pass


def write_row(row: dict):
    """Append-only write.

    BP-C-AN1 closure (forge Wave-D 2026-05-16): wrapped in _file_lock() so
    concurrent writers cannot interleave bytes in the middle of a row.
    """
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    with QUEUE_PATH.open("a", encoding="utf-8", newline="\n") as f:
        with _file_lock(f):
            f.write(canonical + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync may fail on network drives / weird FS; best-effort
                pass


def update_status(task_id: str, new_status: str, notes: str = "",
                   duration_ms: int | None = None) -> bool:
    """Append-only update: write a new row marking status change."""
    update_row = {
        "wave_id": "status-update",
        "task_id": task_id,
        "agent": "",
        "mission": "status-update",
        "status": new_status,
        "dispatched_at": None,
        "completed_at": utc_now() if new_status in ("completed", "failed", "stopped") else None,
        "duration_ms": duration_ms,
        "operator_huddle_visible": False,
        "notes": notes,
        "superseding_task_id": None,
        "is_status_update": True,
    }
    write_row(update_row)
    return True


def append_task(wave_id: str, task_id: str, agent: str, mission: str,
                 notes: str = "", operator_huddle_visible: bool = True) -> dict:
    row = {
        "wave_id": wave_id,
        "task_id": task_id,
        "agent": agent,
        "mission": mission,
        "status": "dispatched",
        "dispatched_at": utc_now(),
        "completed_at": None,
        "duration_ms": None,
        "operator_huddle_visible": operator_huddle_visible,
        "notes": notes,
        "superseding_task_id": None,
        "is_status_update": False,
    }
    write_row(row)
    return row


def recover_pending(timeout_seconds: int = 1800,
                     emit_defects: bool = True) -> list[dict]:
    """Find tasks that should carry forward into the next huddle.

    Walks the append-only log + resolves latest status per task_id.
    Returns tasks with status in {failed, stopped, dispatched-and-timed-out}.

    Judge B-ERR fixes (huddle-wave-3, 2026-05-16):
    - B-ERR-1: timeout_seconds gates `dispatched` carry-forward — only tasks
      whose dispatched_at is older than `timeout_seconds` ago are pulled in.
      Fresh dispatches (operator-driven this very turn) are NOT carry-forward
      candidates; they're work-in-flight.
    - B-ERR-2: null/empty task_id rows emit a LOUD WARNING to stderr +
      .claude/diana/autonomous-task-queue-defects.jsonl (instead of silent
      skip per prior `if not tid: continue`).
    - B-ERR-3: orphan status_update (status_update arrives before parent
      dispatched-row) emits a LOUD WARNING + defect entry; status preserved
      in queue as `status=orphaned-update` with placeholder so reconciliation
      next wave is possible.
    """
    import sys
    from datetime import datetime, timezone, timedelta

    DEFECTS_LOG = REPO_ROOT / ".claude" / "diana" / "autonomous-task-queue-defects.jsonl"

    def emit_defect(defect_type: str, row: dict, reason: str):
        """Write a defect entry + emit stderr warning."""
        if not emit_defects:
            return
        entry = {
            "defect_type": defect_type,
            "detected_at": utc_now(),
            "offending_row": row,
            "reason": reason,
        }
        DEFECTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DEFECTS_LOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
        sys.stderr.write(f"# autonomous_task_queue defect: {defect_type} | {reason}\n")

    rows = read_all()
    latest: dict[str, dict] = {}
    for r in rows:
        tid = r.get("task_id")
        if not tid:
            # B-ERR-2 fix: loud-fail on null/empty task_id (was silent skip)
            emit_defect("null-or-empty-task-id", r,
                         "task_id missing or empty; row dropped from recover-pending")
            continue
        # Last write wins
        if r.get("is_status_update"):
            # Merge status update into latest record
            if tid in latest:
                latest[tid]["status"] = r["status"]
                latest[tid]["completed_at"] = r["completed_at"]
                latest[tid]["duration_ms"] = r["duration_ms"]
                latest[tid].setdefault("notes_history", []).append(r["notes"])
            else:
                # B-ERR-3 fix: orphan status_update (no parent dispatched-row yet)
                emit_defect("orphan-status-update", r,
                             f"status_update for task_id={tid} arrived before "
                             "parent dispatched-row; held as orphaned-update placeholder")
                latest[tid] = {
                    "wave_id": r.get("wave_id", "unknown"),
                    "task_id": tid,
                    "agent": "",
                    "mission": "(orphan-status-update; parent dispatched-row missing)",
                    "status": "orphaned-update",
                    "dispatched_at": None,
                    "completed_at": r.get("completed_at"),
                    "duration_ms": r.get("duration_ms"),
                    "operator_huddle_visible": True,
                    "notes": f"orphan: {r.get('notes', '')}",
                    "superseding_task_id": None,
                    "is_status_update": False,
                    "_orphan_origin": r,
                }
        else:
            latest[tid] = r

    # B-ERR-1 fix: timeout gate for `dispatched` status carry-forward
    now = datetime.now(tz=timezone.utc)
    timeout_threshold = now - timedelta(seconds=timeout_seconds)

    def dispatched_timed_out(r: dict) -> bool:
        if r["status"] != "dispatched":
            return False
        dispatched_at = r.get("dispatched_at")
        if not dispatched_at:
            return False  # no timestamp = can't decide; conservative skip
        try:
            d = datetime.fromisoformat(dispatched_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return False
        return d < timeout_threshold

    carry_forward = [
        r for r in latest.values()
        if r["status"] in ("failed", "stopped", "orphaned-update")
        or dispatched_timed_out(r)
    ]
    # Sort by dispatched_at descending
    carry_forward.sort(key=lambda r: r.get("dispatched_at") or "", reverse=True)
    return carry_forward


def huddle_summary(wave_id: str | None = None) -> dict:
    """Summary of the most recent wave (or specified wave_id)."""
    rows = read_all()
    latest: dict[str, dict] = {}
    for r in rows:
        tid = r.get("task_id")
        if not tid:
            continue
        if r.get("is_status_update"):
            if tid in latest:
                latest[tid]["status"] = r["status"]
                latest[tid]["completed_at"] = r["completed_at"]
                latest[tid]["duration_ms"] = r["duration_ms"]
        else:
            latest[tid] = r
    if wave_id:
        wave_rows = [r for r in latest.values() if r["wave_id"] == wave_id]
    else:
        # most recent wave
        all_waves = sorted({r["wave_id"] for r in latest.values()
                            if not r.get("is_status_update")}, reverse=True)
        if not all_waves:
            return {"wave_id": None, "tasks": [], "summary": "empty queue"}
        wave_id = all_waves[0]
        wave_rows = [r for r in latest.values() if r["wave_id"] == wave_id]
    by_status = {}
    for r in wave_rows:
        by_status.setdefault(r["status"], 0)
        by_status[r["status"]] += 1
    return {
        "wave_id": wave_id,
        "tasks": wave_rows,
        "n_total": len(wave_rows),
        "by_status": by_status,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_app = sub.add_parser("append-task")
    ap_app.add_argument("--wave-id", required=True)
    ap_app.add_argument("--task-id", required=True)
    ap_app.add_argument("--agent", required=True)
    ap_app.add_argument("--mission", required=True)
    ap_app.add_argument("--notes", default="")

    ap_upd = sub.add_parser("update-status")
    ap_upd.add_argument("--task-id", required=True)
    ap_upd.add_argument("--status", required=True,
                          choices=["pending", "dispatched", "completed", "failed", "stopped", "carry-forward"])
    ap_upd.add_argument("--notes", default="")
    ap_upd.add_argument("--duration-ms", type=int, default=None)

    sub.add_parser("recover-pending")

    ap_sum = sub.add_parser("huddle-summary")
    ap_sum.add_argument("--wave-id", default=None)

    args = ap.parse_args()

    if args.cmd == "append-task":
        row = append_task(args.wave_id, args.task_id, args.agent,
                          args.mission, notes=args.notes)
        print(json.dumps(row, indent=2, sort_keys=True))
    elif args.cmd == "update-status":
        ok = update_status(args.task_id, args.status, notes=args.notes,
                            duration_ms=args.duration_ms)
        print(f"updated: {ok}")
    elif args.cmd == "recover-pending":
        carry = recover_pending()
        print(f"# Carry-forward tasks ({len(carry)}):")
        for r in carry:
            print(f"  - {r['task_id']:<60} status={r['status']:<10} agent={r['agent']:<14} mission={r['mission'][:80]}")
    elif args.cmd == "huddle-summary":
        s = huddle_summary(args.wave_id)
        print(json.dumps(s, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
