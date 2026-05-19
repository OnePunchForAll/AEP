"""test_autonomous_task_queue_lock.py - 5-test harness for BP-C-AN1
file-lock closure in autonomous_task_queue.py (forge Wave-D 2026-05-16).

Closes:
  - BP-C-AN1 (autonomous-task-queue append-race via concurrent processes)

Tests:
  1. single write -> file ends with exactly 1 valid JSON line
  2. lock context-manager releases on exception
  3. lock context-manager releases on normal exit
  4. parallel two-process write smoke -> no interleaved bytes; both rows valid
  5. lock release survives second acquire-in-same-process (no permanent hold)

Each test monkey-patches autonomous_task_queue.QUEUE_PATH to a tempdir; the
parallel test (#4) spawns child processes via subprocess that import the
module fresh per process (real concurrency, not threaded).

Cites: adversary BP-C-AN1 attack class (adversary wave-C verdict),
forge wave-B B-ERR-2/3 substrate (autonomous_task_queue.recover_pending).
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _import_queue(queue_path: Path):
    """Import autonomous_task_queue fresh; monkey-patch QUEUE_PATH."""
    sys.path.insert(0, str(Path(__file__).parent))
    import autonomous_task_queue  # type: ignore
    importlib.reload(autonomous_task_queue)
    autonomous_task_queue.QUEUE_PATH = queue_path
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if not queue_path.exists():
        queue_path.write_text("", encoding="utf-8")
    return autonomous_task_queue


def _count_valid_rows(queue_path: Path) -> tuple[int, int, list[str]]:
    """Return (valid_rows, invalid_rows, list_of_invalid_line_excerpts)."""
    valid, invalid = 0, 0
    bad: list[str] = []
    for ln in queue_path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s:
            continue
        try:
            json.loads(s)
            valid += 1
        except json.JSONDecodeError:
            invalid += 1
            bad.append(s[:200])
    return valid, invalid, bad


def test_1_single_write() -> tuple[str, bool, str]:
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "q.jsonl"
        mod = _import_queue(qp)
        row = {"wave_id": "test", "task_id": "t1", "agent": "forge",
               "mission": "test-1", "status": "dispatched",
               "dispatched_at": "2026-05-16T00:00:00Z",
               "completed_at": None, "duration_ms": None,
               "operator_huddle_visible": True, "notes": "", "superseding_task_id": None,
               "is_status_update": False}
        mod.write_row(row)
        v, i, _ = _count_valid_rows(qp)
        ok = (v == 1 and i == 0)
        return ("test_1_single_write", ok, f"valid={v} invalid={i}")


def test_2_lock_releases_on_exception() -> tuple[str, bool, str]:
    """Open file, acquire lock via context-manager, raise inside -> lock released."""
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "q.jsonl"
        mod = _import_queue(qp)
        qp.write_text("", encoding="utf-8")
        try:
            with qp.open("a", encoding="utf-8") as f:
                with mod._file_lock(f):
                    raise RuntimeError("simulated mid-lock failure")
        except RuntimeError:
            pass
        # If lock not released, second acquire would hang or fail.
        # Test by doing a normal write_row.
        row = {"wave_id": "test", "task_id": "t2", "agent": "forge",
               "mission": "test-2", "status": "dispatched",
               "dispatched_at": "2026-05-16T00:00:00Z",
               "completed_at": None, "duration_ms": None,
               "operator_huddle_visible": True, "notes": "", "superseding_task_id": None,
               "is_status_update": False}
        mod.write_row(row)
        v, i, _ = _count_valid_rows(qp)
        ok = (v == 1 and i == 0)
        return ("test_2_lock_releases_on_exception", ok, f"valid={v} invalid={i}")


def test_3_lock_releases_on_normal_exit() -> tuple[str, bool, str]:
    """Sequential write_row calls succeed (would fail if first didn't release)."""
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "q.jsonl"
        mod = _import_queue(qp)
        for i in range(5):
            row = {"wave_id": "test", "task_id": f"t-{i}", "agent": "forge",
                   "mission": f"test-3-{i}", "status": "dispatched",
                   "dispatched_at": "2026-05-16T00:00:00Z",
                   "completed_at": None, "duration_ms": None,
                   "operator_huddle_visible": True, "notes": "", "superseding_task_id": None,
                   "is_status_update": False}
            mod.write_row(row)
        v, inv, _ = _count_valid_rows(qp)
        ok = (v == 5 and inv == 0)
        return ("test_3_lock_releases_on_normal_exit", ok, f"valid={v} invalid={inv}")


def test_4_parallel_two_process_write() -> tuple[str, bool, str]:
    """Spawn 2 child processes, each writes 50 rows; assert 100 valid rows in
    file. This catches the bytes-interleave bug the lock was meant to prevent.
    """
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "q.jsonl"
        # Initialize file
        _import_queue(qp)
        worker_script = Path(td) / "worker.py"
        worker_script.write_text(
            "import sys, json\n"
            f"sys.path.insert(0, r'{Path(__file__).parent}')\n"
            "import autonomous_task_queue as q\n"
            "from pathlib import Path\n"
            f"q.QUEUE_PATH = Path(r'{qp}')\n"
            "for i in range(50):\n"
            "    row = {'wave_id': 'p' + sys.argv[1], 'task_id': sys.argv[1] + '-' + str(i),\n"
            "           'agent': 'forge', 'mission': 'parallel-' + str(i),\n"
            "           'status': 'dispatched', 'dispatched_at': '2026-05-16T00:00:00Z',\n"
            "           'completed_at': None, 'duration_ms': None,\n"
            "           'operator_huddle_visible': True, 'notes': '', 'superseding_task_id': None,\n"
            "           'is_status_update': False}\n"
            "    q.write_row(row)\n",
            encoding="utf-8"
        )
        # Spawn both, wait for both
        p1 = subprocess.Popen([sys.executable, str(worker_script), "A"])
        p2 = subprocess.Popen([sys.executable, str(worker_script), "B"])
        rc1 = p1.wait(timeout=60)
        rc2 = p2.wait(timeout=60)
        v, inv, bad = _count_valid_rows(qp)
        ok = (rc1 == 0 and rc2 == 0 and v == 100 and inv == 0)
        return ("test_4_parallel_two_process_write", ok,
                f"rc1={rc1} rc2={rc2} valid={v} invalid={inv} bad_sample={bad[:1]}")


def test_5_second_acquire_same_process() -> tuple[str, bool, str]:
    """After write_row releases the lock, a second open+lock in same process
    must NOT deadlock. (Catches the bug where Windows msvcrt LK_LOCK is
    re-entrancy-free; we ensure clean release.)"""
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "q.jsonl"
        mod = _import_queue(qp)
        row = {"wave_id": "test", "task_id": "t-r1", "agent": "forge",
               "mission": "reacquire", "status": "dispatched",
               "dispatched_at": "2026-05-16T00:00:00Z",
               "completed_at": None, "duration_ms": None,
               "operator_huddle_visible": True, "notes": "", "superseding_task_id": None,
               "is_status_update": False}
        mod.write_row(row)
        # Second acquire — same process, separate open
        with qp.open("a", encoding="utf-8") as f:
            t0 = time.monotonic()
            with mod._file_lock(f):
                elapsed = time.monotonic() - t0
        ok = (elapsed < 1.0)  # If first lock leaked, this would hang ~10s+
        return ("test_5_second_acquire_same_process", ok,
                f"reacquire_elapsed={elapsed:.3f}s")


def main() -> int:
    tests = [
        test_1_single_write,
        test_2_lock_releases_on_exception,
        test_3_lock_releases_on_normal_exit,
        test_4_parallel_two_process_write,
        test_5_second_acquire_same_process,
    ]
    pass_count = 0
    fail_count = 0
    for t in tests:
        try:
            name, ok, detail = t()
        except Exception as exc:
            name, ok, detail = (t.__name__, False, f"EXCEPTION: {exc!r}")
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name} -- {detail}")
        if ok:
            pass_count += 1
        else:
            fail_count += 1
    print(f"\nSUMMARY: {pass_count}/{len(tests)} PASS, {fail_count}/{len(tests)} FAIL")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
