"""test_agent_yield_check.py - 5-test smoke harness (forge Wave-C 2026-05-16).

Closes judge WARN on agent_yield_check.py (no unit tests at Wave-B time).

Tests (per task spec):
  1. empty marker + 0 messages              -> exit 0 (proceed, no drift)
  2. empty marker + N messages              -> exit 1 (yield)
  3. matched marker + 0 new                 -> exit 0
  4. matched marker + 1 new                 -> exit 1 (yield)
  5. matched marker + stale heartbeat >60s  -> exit 0 + emit advisory defect

Each test runs in an isolated temp dir; the script is imported as a module so
we can monkey-patch its REPO_ROOT / DUMP_GLOB / MARKER_PATH / HEARTBEAT_PATH /
DEFECT_LOG_PATH module-level constants per test.

Cites: forge.lamport-228 (wave-B D-NEW-1 build) + judge.lamport-215 (wave-B
WARN no-unit-tests) + adversary.lamport-62 (BP-D1-1 attack class).
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path


def _import_yield_check():
    """Import agent_yield_check fresh; reload to pick up monkey-patches."""
    sys.path.insert(0, str(Path(__file__).parent))
    import agent_yield_check  # type: ignore
    importlib.reload(agent_yield_check)
    return agent_yield_check


def _set_paths(mod, tmpdir: Path) -> None:
    mod.REPO_ROOT = tmpdir
    mod.DUMP_GLOB = tmpdir / ".claude" / "diana" / "operator-messages"
    mod.MARKER_PATH = tmpdir / ".claude" / "diana" / "last_wakeup_yield_at.json"
    mod.HEARTBEAT_PATH = tmpdir / ".claude" / "diana" / "capture-hook-heartbeat.txt"
    mod.DEFECT_LOG_PATH = tmpdir / ".claude" / "diana" / "defects.jsonl"


def _stamp_heartbeat(path: Path, age_seconds: int) -> None:
    """Stamp a heartbeat file `age_seconds` in the past."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(stamp, encoding="utf-8")


def _make_messages(dump_glob: Path, n: int) -> None:
    """Create n empty dump-NNN/message-NNNN.aepkg dirs."""
    dump_glob.mkdir(parents=True, exist_ok=True)
    dump = dump_glob / "dump-0001"
    dump.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (dump / f"message-{i:04d}.aepkg").mkdir(exist_ok=True)


def _run(mod, args_list: list[str]) -> tuple[int, dict]:
    """Run main() with given argv; capture stdout JSON + exit code."""
    saved_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        sys.argv = ["agent_yield_check.py", *args_list]
        rc = mod.main()
        out = sys.stdout.getvalue()
    finally:
        sys.stdout = saved_stdout
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        parsed = {"_raw_stdout": out}
    return rc, parsed


def test_1_empty_marker_zero_messages() -> tuple[str, bool, str]:
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check()
        _set_paths(mod, Path(td))
        # No messages, no marker, no heartbeat. Defaults marker->{0, None}.
        # scan_messages returns (0, None); marker counts equal -> no drift.
        rc, payload = _run(mod, [])
        ok = (rc == 0) and (payload.get("decision") == "proceed") and (not payload.get("drift_detected"))
        return ("test_1_empty_marker_zero_messages", ok,
                f"rc={rc} decision={payload.get('decision')} drift={payload.get('drift_detected')}")


def test_2_empty_marker_n_messages() -> tuple[str, bool, str]:
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check()
        _set_paths(mod, Path(td))
        _make_messages(mod.DUMP_GLOB, n=3)
        # marker is default {0, None}; current count is 3 -> drift -> yield
        rc, payload = _run(mod, [])
        ok = (rc == 1) and (payload.get("decision") == "yield") and payload.get("drift_detected")
        return ("test_2_empty_marker_n_messages", ok,
                f"rc={rc} decision={payload.get('decision')} count={payload.get('current_count')}")


def test_3_matched_marker_zero_new() -> tuple[str, bool, str]:
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check()
        _set_paths(mod, Path(td))
        _make_messages(mod.DUMP_GLOB, n=2)
        # Pre-stamp marker to match current state
        mod.write_marker(2, "message-0001.aepkg")
        rc, payload = _run(mod, [])
        ok = (rc == 0) and (payload.get("decision") == "proceed") and (not payload.get("drift_detected"))
        return ("test_3_matched_marker_zero_new", ok,
                f"rc={rc} decision={payload.get('decision')}")


def test_4_matched_marker_one_new() -> tuple[str, bool, str]:
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check()
        _set_paths(mod, Path(td))
        _make_messages(mod.DUMP_GLOB, n=2)
        mod.write_marker(2, "message-0001.aepkg")
        # Now add a 3rd message
        (mod.DUMP_GLOB / "dump-0001" / "message-0002.aepkg").mkdir(exist_ok=True)
        rc, payload = _run(mod, [])
        ok = (rc == 1) and (payload.get("decision") == "yield") and payload.get("drift_detected")
        return ("test_4_matched_marker_one_new", ok,
                f"rc={rc} decision={payload.get('decision')} count={payload.get('current_count')}")


def test_5_matched_marker_stale_heartbeat() -> tuple[str, bool, str]:
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check()
        _set_paths(mod, Path(td))
        _make_messages(mod.DUMP_GLOB, n=2)
        mod.write_marker(2, "message-0001.aepkg")
        # Stamp heartbeat 120s in the past -> stale (>60s threshold)
        _stamp_heartbeat(mod.HEARTBEAT_PATH, age_seconds=120)
        rc, payload = _run(mod, [])
        # Decision: proceed (heartbeat is advisory). Defect should be logged.
        defect_log_exists = mod.DEFECT_LOG_PATH.exists()
        defect_rows = []
        if defect_log_exists:
            for line in mod.DEFECT_LOG_PATH.read_text(encoding="utf-8").splitlines():
                try:
                    defect_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        advisory_emitted = any(r.get("kind") == "capture-hook-stale-heartbeat" for r in defect_rows)
        ok = (rc == 0) and (payload.get("decision") == "proceed") and payload.get("heartbeat_stale") and advisory_emitted
        return ("test_5_matched_marker_stale_heartbeat", ok,
                f"rc={rc} decision={payload.get('decision')} stale={payload.get('heartbeat_stale')} advisory={advisory_emitted}")


def main() -> int:
    tests = [
        test_1_empty_marker_zero_messages,
        test_2_empty_marker_n_messages,
        test_3_matched_marker_zero_new,
        test_4_matched_marker_one_new,
        test_5_matched_marker_stale_heartbeat,
    ]
    pass_count = 0
    fail_count = 0
    results = []
    for t in tests:
        try:
            name, ok, detail = t()
        except Exception as exc:
            name, ok, detail = (t.__name__, False, f"EXCEPTION: {exc}")
        status = "PASS" if ok else "FAIL"
        results.append({"name": name, "status": status, "detail": detail})
        print(f"[{status}] {name} -- {detail}")
        if ok:
            pass_count += 1
        else:
            fail_count += 1
    print(f"\nSUMMARY: {pass_count}/{len(tests)} PASS, {fail_count}/{len(tests)} FAIL")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
