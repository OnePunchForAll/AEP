"""test_agent_huddle_runner_wave_d.py - 11-test harness for Wave-D + Wave-E
closures in agent_huddle_runner.py.

Wave-D: forge Wave-D 2026-05-16 (8-test harness).
Wave-E extension: forge 2026-05-16 — 3 NEW tests covering the
elapsed_skew_safe flag added to semaphore_yield_check() to surface whether
the elapsed-since-arm signal was computed from monotonic_ns (skew-safe) or
fell back to wall-clock (not skew-safe).

Closes:
  - BP-C-A1 (semaphore-bypass via clock-skew/set-rotation)
  - BP-C-TH (huddle-thrash via rapid-arm-cycle)
  - Wave-E monotonic-clock visibility (scout Wave-C+D prior-art recommendation:
    callers need to see whether elapsed-time signal is trustworthy)

Tests:
  A1-1. stamp + check matched set/count -> no yield
  A1-2. stamp + add message -> yield (set-equality fires)
  A1-3. stamp + rotate (delete one, add one) -> count unchanged but set changed
        -> yield (set-equality fires; count-only check would miss)
  A1-4. tamper with marker after stamp (mutate set_hash) -> yield
        (hash-tamper fires)
  A1-5. legacy v1 marker (no message_set_at_arm) -> count-only fallback works;
        should_upgrade_marker=True
  TH-1. two arms <60s apart -> second refused (rate-limited)
  TH-2. two arms <60s apart with --force -> second succeeds
  TH-3. two arms >60s apart -> second succeeds
  E1.   (Wave-E) v2 marker -> elapsed_skew_safe=True; monotonic delta computed
  E2.   (Wave-E) v1 marker (no monotonic_ns) -> elapsed_skew_safe=False;
        elapsed_since_arm_monotonic_seconds=None
  E3.   (Wave-E) no marker -> elapsed_skew_safe=False (no signal at all)

Each test runs in an isolated temp dir; the script is imported as a module so
we monkey-patch the REPO_ROOT_DEFAULT path and pass repo_root explicitly.

Cites: adversary BP-C-A1 + BP-C-TH attack classes (adversary wave-C verdict),
forge.lamport-228 wave-B semaphore substrate, forge wave-C semaphore_yield_check,
scout Wave-C+D monotonic-prior-art recommendation (closes Wave-E task A.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import time
from pathlib import Path


def _import_huddle_runner():
    """Import agent_huddle_runner fresh; reload to pick up monkey-patches."""
    sys.path.insert(0, str(Path(__file__).parent))
    import agent_huddle_runner  # type: ignore
    importlib.reload(agent_huddle_runner)
    return agent_huddle_runner


def _make_messages(repo_root: Path, dump_name: str, n: int,
                    start_idx: int = 0) -> list[str]:
    """Create n message-NNNN.aepkg dirs under .claude/diana/operator-messages/<dump>/.
    Returns the message names created."""
    dump = repo_root / ".claude" / "diana" / "operator-messages" / dump_name
    dump.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for i in range(start_idx, start_idx + n):
        name = f"message-{i:04d}.aepkg"
        (dump / name).mkdir(exist_ok=True)
        names.append(name)
    return names


def _read_marker(repo_root: Path) -> dict:
    p = repo_root / ".claude" / "diana" / "wakeup_arm_marker.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _write_marker(repo_root: Path, payload: dict) -> None:
    p = repo_root / ".claude" / "diana" / "wakeup_arm_marker.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# BP-C-A1 tests
# ---------------------------------------------------------------------------

def test_a1_1_stamp_and_check_matched_no_yield() -> tuple[str, bool, str]:
    """Baseline: stamp marker, immediately check, no new messages -> no yield."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=3)
        cnt = mod.count_operator_messages(repo_root)
        stamp_result = mod.stamp_arm_marker(repo_root, cnt)
        if stamp_result.get("action") != "stamped":
            return ("test_a1_1_stamp_and_check_matched_no_yield",
                    False, f"stamp failed: {stamp_result}")
        check = mod.semaphore_yield_check(repo_root)
        ok = (check["should_yield"] is False
              and check["delta"] == 0
              and check["yield_triggers"] == []
              and check["schema_version_at_arm"] == 2)
        return ("test_a1_1_stamp_and_check_matched_no_yield", ok,
                f"should_yield={check['should_yield']} triggers={check['yield_triggers']}")


def test_a1_2_added_message_triggers_yield() -> tuple[str, bool, str]:
    """Stamp at count=2; add a 3rd message; check triggers yield."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=2)
        mod.stamp_arm_marker(repo_root, 2)
        _make_messages(repo_root, "dump-0001", n=1, start_idx=2)
        check = mod.semaphore_yield_check(repo_root)
        # delta>0 AND set-equality fires
        ok = (check["should_yield"] is True
              and check["delta"] == 1
              and "delta-count-positive" in check["yield_triggers"]
              and "set-equality-changed" in check["yield_triggers"])
        return ("test_a1_2_added_message_triggers_yield", ok,
                f"should_yield={check['should_yield']} delta={check['delta']} triggers={check['yield_triggers']}")


def test_a1_3_rotation_count_unchanged_set_changed() -> tuple[str, bool, str]:
    """BP-C-A1 CORE: delete one message, add one new one — count unchanged
    but SET changed. Pre-Wave-D code would NOT yield; Wave-D MUST yield."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        names = _make_messages(repo_root, "dump-0001", n=2)
        mod.stamp_arm_marker(repo_root, 2)
        # Delete message-0000 and add message-0099 → count still 2 but set changed
        dump = repo_root / ".claude" / "diana" / "operator-messages" / "dump-0001"
        (dump / names[0]).rmdir()
        (dump / "message-0099.aepkg").mkdir()
        check = mod.semaphore_yield_check(repo_root)
        # delta = 0 BUT set changed → yield via set-equality trigger
        ok = (check["should_yield"] is True
              and check["delta"] == 0
              and "set-equality-changed" in check["yield_triggers"]
              and "delta-count-positive" not in check["yield_triggers"])
        return ("test_a1_3_rotation_count_unchanged_set_changed", ok,
                f"should_yield={check['should_yield']} delta={check['delta']} triggers={check['yield_triggers']}")


def test_a1_4_marker_tamper_triggers_yield() -> tuple[str, bool, str]:
    """Post-stamp tampering with set_hash inside marker file -> yield via
    'arm-marker-hash-tampered' trigger (the recomputed hash from
    message_set_at_arm doesn't match the stored message_set_hash_at_arm)."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=3)
        mod.stamp_arm_marker(repo_root, 3)
        marker = _read_marker(repo_root)
        # Tamper: corrupt the stored hash
        marker["message_set_hash_at_arm"] = "0" * 64
        _write_marker(repo_root, marker)
        check = mod.semaphore_yield_check(repo_root)
        ok = (check["should_yield"] is True
              and "arm-marker-hash-tampered" in check["yield_triggers"])
        return ("test_a1_4_marker_tamper_triggers_yield", ok,
                f"should_yield={check['should_yield']} triggers={check['yield_triggers']}")


def test_a1_5_legacy_v1_marker_fallback() -> tuple[str, bool, str]:
    """Legacy v1 marker (count-only, no message_set_at_arm) → fallback to
    count-only delta check; should_upgrade_marker=True."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=2)
        # Write a v1-style marker manually (no message_set_at_arm field)
        marker_v1 = {
            "armed_at": "2026-05-16T11:00:00Z",
            "message_count_at_arm": 2,
        }
        _write_marker(repo_root, marker_v1)
        check = mod.semaphore_yield_check(repo_root)
        # delta=0, set-equality skipped (no armed_set), hash skipped → no yield
        ok = (check["should_yield"] is False
              and check["delta"] == 0
              and check.get("should_upgrade_marker") is True
              and check["schema_version_at_arm"] == 1)
        return ("test_a1_5_legacy_v1_marker_fallback", ok,
                f"should_yield={check['should_yield']} upgrade={check.get('should_upgrade_marker')}")


# ---------------------------------------------------------------------------
# BP-C-TH tests (rate-limit / huddle-thrash)
# ---------------------------------------------------------------------------

def test_th_1_rapid_rearm_refused() -> tuple[str, bool, str]:
    """Two arm calls <60s apart -> second is rate-limited."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=1)
        first = mod.stamp_arm_marker(repo_root, 1)
        second = mod.stamp_arm_marker(repo_root, 1)
        ok = (first.get("action") == "stamped"
              and second.get("action") == "rate-limited"
              and second.get("elapsed_since_prior_arm_seconds") is not None
              and second["elapsed_since_prior_arm_seconds"] < 60.0
              and second.get("skew_safe") is True)
        return ("test_th_1_rapid_rearm_refused", ok,
                f"first={first.get('action')} second={second.get('action')} elapsed={second.get('elapsed_since_prior_arm_seconds')}")


def test_th_2_force_arm_bypasses_rate_limit() -> tuple[str, bool, str]:
    """Two arm calls <60s apart with force=True -> second succeeds."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=1)
        first = mod.stamp_arm_marker(repo_root, 1)
        second = mod.stamp_arm_marker(repo_root, 1, force=True)
        ok = (first.get("action") == "stamped"
              and second.get("action") == "stamped")
        return ("test_th_2_force_arm_bypasses_rate_limit", ok,
                f"first={first.get('action')} second(force)={second.get('action')}")


def test_th_3_arms_60s_apart_both_succeed() -> tuple[str, bool, str]:
    """Two arm calls >60s apart (simulated via direct wall-clock + monotonic
    write to legacy v1 marker so we test the wall-clock fallback path; then
    overlay v2 stamp). For the monotonic-path test, we'd need real sleep; we
    SIMULATE the elapsed time by writing the marker with a back-dated
    armed_at and NO armed_at_monotonic_ns (triggers wall-clock fallback)."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=1)
        # Write a marker back-dated 120s with no monotonic_ns (forces
        # wall-clock fallback path)
        back_dated = {
            "armed_at": "2026-01-01T00:00:00Z",  # far in the past
            "message_count_at_arm": 1,
        }
        _write_marker(repo_root, back_dated)
        second = mod.stamp_arm_marker(repo_root, 1)
        ok = (second.get("action") == "stamped")
        return ("test_th_3_arms_60s_apart_both_succeed", ok,
                f"second={second.get('action')}")


# ---------------------------------------------------------------------------
# Wave-E extension: elapsed_skew_safe flag visibility
# ---------------------------------------------------------------------------

def test_e1_v2_marker_skew_safe_true() -> tuple[str, bool, str]:
    """v2 marker stamped via stamp_arm_marker -> semaphore_yield_check reports
    elapsed_skew_safe=True. The monotonic_ns delta is the trustworthy signal."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=2)
        stamp_result = mod.stamp_arm_marker(repo_root, 2)
        if stamp_result.get("action") != "stamped":
            return ("test_e1_v2_marker_skew_safe_true", False,
                    f"setup-stamp-failed: {stamp_result}")
        check = mod.semaphore_yield_check(repo_root)
        ok = (check.get("elapsed_skew_safe") is True
              and check.get("elapsed_since_arm_monotonic_seconds") is not None
              and check.get("schema_version_at_arm") == 2)
        return ("test_e1_v2_marker_skew_safe_true", ok,
                f"skew_safe={check.get('elapsed_skew_safe')} "
                f"elapsed={check.get('elapsed_since_arm_monotonic_seconds')} "
                f"schema_v={check.get('schema_version_at_arm')}")


def test_e2_v1_marker_skew_safe_false() -> tuple[str, bool, str]:
    """Legacy v1 marker (no armed_at_monotonic_ns) ->
    elapsed_skew_safe=False; elapsed_since_arm_monotonic_seconds=None.
    Wall-clock fallback is NOT skew-safe; caller can detect this."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        _make_messages(repo_root, "dump-0001", n=2)
        # Write a v1-style marker manually (no message_set_at_arm field)
        marker_v1 = {
            "armed_at": "2026-05-16T11:00:00Z",
            "message_count_at_arm": 2,
            # Notably absent: armed_at_monotonic_ns
        }
        _write_marker(repo_root, marker_v1)
        check = mod.semaphore_yield_check(repo_root)
        ok = (check.get("elapsed_skew_safe") is False
              and check.get("elapsed_since_arm_monotonic_seconds") is None
              and check.get("should_upgrade_marker") is True)
        return ("test_e2_v1_marker_skew_safe_false", ok,
                f"skew_safe={check.get('elapsed_skew_safe')} "
                f"elapsed={check.get('elapsed_since_arm_monotonic_seconds')} "
                f"upgrade={check.get('should_upgrade_marker')}")


def test_e3_no_marker_skew_safe_false() -> tuple[str, bool, str]:
    """No marker on disk -> elapsed_skew_safe=False (no signal to be safe
    about). marker_present=False; should_yield=False (first-ever wave)."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_huddle_runner()
        repo_root = Path(td)
        # No marker file; no messages
        check = mod.semaphore_yield_check(repo_root)
        ok = (check.get("elapsed_skew_safe") is False
              and check.get("marker_present") is False
              and check.get("should_yield") is False)
        return ("test_e3_no_marker_skew_safe_false", ok,
                f"skew_safe={check.get('elapsed_skew_safe')} "
                f"marker_present={check.get('marker_present')} "
                f"should_yield={check.get('should_yield')}")


def main() -> int:
    tests = [
        test_a1_1_stamp_and_check_matched_no_yield,
        test_a1_2_added_message_triggers_yield,
        test_a1_3_rotation_count_unchanged_set_changed,
        test_a1_4_marker_tamper_triggers_yield,
        test_a1_5_legacy_v1_marker_fallback,
        test_th_1_rapid_rearm_refused,
        test_th_2_force_arm_bypasses_rate_limit,
        test_th_3_arms_60s_apart_both_succeed,
        # Wave-E extension
        test_e1_v2_marker_skew_safe_true,
        test_e2_v1_marker_skew_safe_false,
        test_e3_no_marker_skew_safe_false,
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
