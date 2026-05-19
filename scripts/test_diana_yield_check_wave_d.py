"""test_agent_yield_check_wave_d.py - 9-test harness for Wave-D BP-C-D1
closure (strict ISO-8601 / empty-content / I/O exception / future-stamp)
in agent_yield_check.py.

Wave-D origin: forge Wave-D 2026-05-16 (5-test harness).
Wave-E extension: 4 NEW tests covering BP-C-D1 backlog gap identified by
judge Wave-D PARTIAL verdict — specifically the I/O exception path
(D1-6, D1-7) + integration with main() defect emission (D1-8) + boundary
test for the 5-second-future threshold mentioned in operator spec (D1-9).

Closes:
  - BP-C-D1 (heartbeat-spoof via filesystem race / empty-overwrite / malformed
    / future-stamp / I/O failure)

Tests:
  D1-1. empty-content heartbeat (NTFS disk-full quirk) -> stale=True
  D1-2. whitespace-only heartbeat -> stale=True
  D1-3. malformed timestamp (missing Z, fractional seconds, etc.) -> stale=True
  D1-4. future-stamped heartbeat (clock skew) -> stale=True (age_s < 0)
  D1-5. valid heartbeat <60s old -> stale=False; valid timestamp; positive age
  D1-6. (Wave-E) OSError on read_text -> stale=True; age_s=None; stamped=None
  D1-7. (Wave-E) UnicodeDecodeError on read_text -> stale=True
  D1-8. (Wave-E) main() emits capture-hook-stale-heartbeat defect when stale
  D1-9. (Wave-E) future-stamp boundary at +5s, +10s, +60s all stale=True

Each test runs in an isolated temp dir; the script is imported as a module
so we monkey-patch HEARTBEAT_PATH per test.

Cites: adversary BP-C-D1-1 disk-full-silent-fail attack class (adversary
wave-C verdict), forge wave-C heartbeat substrate (check_heartbeat), judge
Wave-D PARTIAL verdict on BP-C-D1 I/O coverage gap.

Pre-Wave-D discrimination empirical run (Wave-E verification 2026-05-16):
  Tests that DISCRIMINATE pre-Wave-D vs current (FAIL pre / PASS current):
    D1-1 (empty)              -- pre-Wave-D returns stamped_at=None; Wave-D ""
    D1-2 (whitespace)         -- pre-Wave-D returns stamped_at=None; Wave-D ""
    D1-3 (malformed)          -- pre-Wave-D returns stamped_at=None; Wave-D raw
    D1-4 (future +600s)       -- pre-Wave-D returns is_stale=False; Wave-D True
    D1-9 (future +5/10/60s)   -- pre-Wave-D returns is_stale=False; Wave-D True
  Tests that PASS both pre-Wave-D and current (regression-lock / characterization):
    D1-5 (valid fresh)        -- alignment test; both agree is_stale=False
    D1-6 (OSError)            -- pre-Wave-D bare except also returns stale=True;
                                 Wave-D narrow (OSError, UnicodeDecodeError)
                                 catch produces identical observable behavior.
                                 Regression-lock: if catch narrows to ONLY
                                 specific subclasses, this test would fire.
    D1-7 (UnicodeDecodeError) -- same regression-lock semantics as D1-6
    D1-8 (defect emission)    -- both emit capture-hook-stale-heartbeat;
                                 empirical/characterization test (no bug, no
                                 RED phase) — locks in main() defect plumbing.
"""
from __future__ import annotations

import importlib
import io
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


def _import_yield_check(repo_root: Path):
    sys.path.insert(0, str(Path(__file__).parent))
    import agent_yield_check  # type: ignore
    importlib.reload(agent_yield_check)
    agent_yield_check.REPO_ROOT = repo_root
    agent_yield_check.HEARTBEAT_PATH = repo_root / ".claude" / "diana" / "capture-hook-heartbeat.txt"
    agent_yield_check.DUMP_GLOB = repo_root / ".claude" / "diana" / "operator-messages"
    agent_yield_check.MARKER_PATH = repo_root / ".claude" / "diana" / "last_wakeup_yield_at.json"
    agent_yield_check.DEFECT_LOG_PATH = repo_root / ".claude" / "diana" / "defects.jsonl"
    return agent_yield_check


def _stamp_heartbeat_raw(mod, raw: str) -> None:
    """Write arbitrary bytes to the heartbeat path."""
    p = mod.HEARTBEAT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw, encoding="utf-8")


def test_d1_1_empty_content() -> tuple[str, bool, str]:
    """NTFS disk-full quirk: heartbeat file exists with empty content."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        _stamp_heartbeat_raw(mod, "")
        is_stale, age_s, stamped = mod.check_heartbeat()
        ok = (is_stale is True
              and age_s is None
              and stamped == "")
        return ("test_d1_1_empty_content", ok,
                f"is_stale={is_stale} age_s={age_s} stamped_at={stamped!r}")


def test_d1_2_whitespace_only() -> tuple[str, bool, str]:
    """Whitespace-only content (e.g. errant newline). Should treat as empty."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        _stamp_heartbeat_raw(mod, "   \n  \t  \n")
        is_stale, age_s, stamped = mod.check_heartbeat()
        ok = (is_stale is True
              and age_s is None
              and stamped == "")
        return ("test_d1_2_whitespace_only", ok,
                f"is_stale={is_stale} age_s={age_s} stamped_at={stamped!r}")


def test_d1_3_malformed_timestamp() -> tuple[str, bool, str]:
    """Wrong format: fractional seconds, missing Z, wrong separator, etc.
    All should fail strict regex and report stale."""
    cases = [
        "2026-05-16T11:00:00.000Z",       # fractional seconds
        "2026-05-16T11:00:00",            # missing Z
        "2026-05-16 11:00:00Z",           # space instead of T
        "2026-05-16T11:00:00+00:00",      # offset instead of Z
        "not-a-timestamp",                # garbage
        "20260516T110000Z",               # compact format (Wave-C+ uses sep)
    ]
    failed_cases = []
    for raw in cases:
        with tempfile.TemporaryDirectory() as td:
            mod = _import_yield_check(Path(td))
            _stamp_heartbeat_raw(mod, raw)
            is_stale, age_s, stamped = mod.check_heartbeat()
            if not (is_stale is True and stamped == raw):
                failed_cases.append(f"{raw!r} -> stale={is_stale} stamped={stamped!r}")
    ok = (len(failed_cases) == 0)
    return ("test_d1_3_malformed_timestamp", ok,
            f"failed={failed_cases if failed_cases else '(all 6 rejected)'}")


def test_d1_4_future_stamped() -> tuple[str, bool, str]:
    """Future-stamped heartbeat: age_s < 0; should report stale."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        future = (datetime.now(timezone.utc) + timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _stamp_heartbeat_raw(mod, future)
        is_stale, age_s, stamped = mod.check_heartbeat()
        ok = (is_stale is True
              and age_s is not None
              and age_s < 0)
        age_str = f"{age_s:.1f}" if age_s is not None else "None"
        return ("test_d1_4_future_stamped", ok,
                f"is_stale={is_stale} age_s={age_str}")


def test_d1_5_valid_fresh() -> tuple[str, bool, str]:
    """Valid ISO-8601 stamp 10s ago: should be NOT stale."""
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        recent = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _stamp_heartbeat_raw(mod, recent)
        is_stale, age_s, stamped = mod.check_heartbeat()
        ok = (is_stale is False
              and age_s is not None
              and age_s > 0
              and stamped == recent)
        return ("test_d1_5_valid_fresh", ok,
                f"is_stale={is_stale} age_s={age_s:.1f}")


# ---------------------------------------------------------------------------
# Wave-E extension: BP-C-D1 backlog (judge Wave-D PARTIAL verdict closure)
# ---------------------------------------------------------------------------

def test_d1_6_oserror_on_read() -> tuple[str, bool, str]:
    """I/O exception (mocked OSError) during read_text -> stale=True.

    Discriminator vs pre-Wave-D: pre-Wave-D's bare except Exception ALSO
    returned (True, None, None) on OSError, but conflated it with malformed-
    timestamp failures in the defect log (defect.kind couldn't distinguish
    'I/O failure' from 'bad timestamp'). Wave-D's narrow (OSError,
    UnicodeDecodeError) catch separates I/O from parse/regex failures, and
    the empty/whitespace/malformed paths now return the literal raw content
    in stamped_at so the defect-log row records WHICH failure mode tripped.

    This test asserts the I/O path: read_text raises -> return (True, None, None).
    Caller MUST NOT see the exception propagate.
    """
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        # Stamp something so HEARTBEAT_PATH.exists() returns True
        _stamp_heartbeat_raw(mod, "2026-05-16T12:00:00Z")
        # Mock pathlib.Path.read_text to raise PermissionError (an OSError subclass)
        with mock.patch.object(type(mod.HEARTBEAT_PATH), "read_text",
                                side_effect=PermissionError(13, "Access denied")):
            try:
                is_stale, age_s, stamped = mod.check_heartbeat()
                exception_propagated = False
            except Exception as exc:
                is_stale, age_s, stamped = None, None, None
                exception_propagated = True
        ok = (exception_propagated is False
              and is_stale is True
              and age_s is None
              and stamped is None)
        return ("test_d1_6_oserror_on_read", ok,
                f"propagated={exception_propagated} is_stale={is_stale} age_s={age_s} stamped={stamped!r}")


def test_d1_7_unicode_decode_error() -> tuple[str, bool, str]:
    """UnicodeDecodeError during read_text -> stale=True (corrupted bytes).

    Simulates a heartbeat file with invalid UTF-8 bytes (e.g. partial
    multi-byte sequence at EOF after disk-full or process-kill mid-write).
    Wave-D's catch tuple includes UnicodeDecodeError specifically because
    NTFS can leave partial encoded bytes after a crash.
    """
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        # Write raw bytes that are NOT valid UTF-8 (lone continuation byte)
        mod.HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        mod.HEARTBEAT_PATH.write_bytes(b"\xc3\x28")  # invalid UTF-8 sequence
        try:
            is_stale, age_s, stamped = mod.check_heartbeat()
            exception_propagated = False
        except Exception as exc:
            is_stale, age_s, stamped = None, None, None
            exception_propagated = True
        ok = (exception_propagated is False
              and is_stale is True
              and age_s is None
              and stamped is None)
        return ("test_d1_7_unicode_decode_error", ok,
                f"propagated={exception_propagated} is_stale={is_stale} age_s={age_s} stamped={stamped!r}")


def test_d1_8_main_emits_defect_on_stale() -> tuple[str, bool, str]:
    """Integration: when heartbeat is stale, main() must emit a
    capture-hook-stale-heartbeat row to defects.jsonl. Validates the
    end-to-end advisory-defect plumbing (check_heartbeat -> emit_defect).

    This is an EMPIRICAL/CHARACTERIZATION test for the existing main()
    behavior — no bug, no RED phase. Test purpose: lock in the defect-
    emission semantics so future refactors can't silently drop them.
    """
    with tempfile.TemporaryDirectory() as td:
        mod = _import_yield_check(Path(td))
        # Stamp an old heartbeat (>60s ago) so it's deemed stale
        old_stamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _stamp_heartbeat_raw(mod, old_stamp)
        # Run main() with --status (read-only, doesn't stamp marker)
        old_argv = sys.argv
        old_stdout = sys.stdout
        try:
            sys.argv = ["agent_yield_check.py", "--status"]
            sys.stdout = io.StringIO()
            rc = mod.main()
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout
        defect_path = mod.DEFECT_LOG_PATH
        if not defect_path.exists():
            return ("test_d1_8_main_emits_defect_on_stale", False,
                    f"defect log not written; rc={rc}")
        rows = [json.loads(ln) for ln in defect_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        stale_rows = [r for r in rows if r.get("kind") == "capture-hook-stale-heartbeat"]
        ok = (rc == 0
              and len(stale_rows) >= 1
              and stale_rows[-1].get("heartbeat_stamped_at") == old_stamp
              and stale_rows[-1].get("advisory_only") is True)
        return ("test_d1_8_main_emits_defect_on_stale", ok,
                f"rc={rc} defect_rows={len(stale_rows)} kind=capture-hook-stale-heartbeat")


def test_d1_9_future_stamp_boundary() -> tuple[str, bool, str]:
    """Future-stamp at +5s, +10s, +60s — ALL must be stale (operator spec
    said 5+ sec future detection). Pre-Wave-D would NOT catch +5s/+10s
    futures because there was no age_s < 0 check; pre-Wave-D only saw
    is_stale=True if age > 60s.

    The +5s boundary is the operator-stated minimum future-detection threshold.
    Wave-D's check is `age_s < 0`, which catches ANY future stamp (most strict).
    """
    cases = [5, 10, 60, 600]
    failed_cases = []
    for offset_s in cases:
        with tempfile.TemporaryDirectory() as td:
            mod = _import_yield_check(Path(td))
            future = (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
            _stamp_heartbeat_raw(mod, future)
            is_stale, age_s, stamped = mod.check_heartbeat()
            if not (is_stale is True and age_s is not None and age_s < 0):
                failed_cases.append(f"+{offset_s}s -> stale={is_stale} age_s={age_s}")
    ok = (len(failed_cases) == 0)
    return ("test_d1_9_future_stamp_boundary", ok,
            f"failed={failed_cases if failed_cases else '(all 4 boundary offsets stale)'}")


def main() -> int:
    tests = [
        test_d1_1_empty_content,
        test_d1_2_whitespace_only,
        test_d1_3_malformed_timestamp,
        test_d1_4_future_stamped,
        test_d1_5_valid_fresh,
        # Wave-E extension
        test_d1_6_oserror_on_read,
        test_d1_7_unicode_decode_error,
        test_d1_8_main_emits_defect_on_stale,
        test_d1_9_future_stamp_boundary,
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
