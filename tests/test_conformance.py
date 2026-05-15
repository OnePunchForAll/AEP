"""AEP v0.5.5 conformance test suite.

Tests:
  - Lane A: the canonical example packet validates clean under strict L2.
  - Lane B: every regression fixture under tests/lane_b/ is REJECTED with the
    expected reason code.
  - AEP-NUMERIC-v1: the cross-runtime test vectors corpus passes 100%.

Run with:
    PYTHONPATH=src python -m pytest tests/v0_5/

Or directly:
    PYTHONPATH=src python tests/v0_5/test_conformance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# pytest is optional — when not installed, the standalone runner at the bottom
# of this file still works via plain assertions.
try:
    import pytest  # type: ignore[import-untyped]
    _HAS_PYTEST = True
except ImportError:
    _HAS_PYTEST = False

    class _PytestStub:
        @staticmethod
        def mark_parametrize(*_args, **_kw):
            def _wrap(fn):
                return fn
            return _wrap

        class mark:  # noqa: D401
            @staticmethod
            def parametrize(*_args, **_kw):  # type: ignore[no-redef]
                def _wrap(fn):
                    return fn
                return _wrap

        @staticmethod
        def skip(msg: str) -> None:
            print(f"SKIP {msg}")
            return None

    pytest = _PytestStub()  # type: ignore[assignment]

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from aep import validate_v0_5_1, ValidationConfig  # noqa: E402
from aep.run_numeric_vectors import run_vectors  # noqa: E402


EXAMPLE_PACKET = REPO_ROOT / "examples" / "minimal.aepkg"
LANE_B_DIR = REPO_ROOT / "tests" / "lane_b"
NUMERIC_VECTORS = REPO_ROOT / "test_vectors" / "v0_5" / "A.10-numeric-canonicalization" / "vectors.json"


def _validate(pkt: Path) -> "ValidationResult":  # noqa: F821
    return validate_v0_5_1(
        pkt,
        ValidationConfig(profile="aep:0.5/stable", conformance_level=2, strict=True),
    )


# ============ Lane A: canonical example must validate clean ============


def test_lane_a_minimal_example_passes_strict_l2() -> None:
    result = _validate(EXAMPLE_PACKET)
    errors = [f for f in result.findings if f.severity == "error"]
    assert errors == [], (
        f"examples/minimal.aepkg/ must validate clean under v0.5.5 strict L2; "
        f"got {len(errors)} error(s): {[f.code for f in errors]}"
    )
    assert result.schema_result in {"pass", "warn"}, (
        f"schema_result={result.schema_result!r} (expected pass or warn)"
    )


# ============ Lane B: every fixture must REJECT with expected code ============

LANE_B_EXPECTATIONS = {
    "atk-gr-go-empty.aepkg": {"AEP53_GR_GO_EMPTY_JUSTIFICATION"},
    "atk-path-traversal.aepkg": {"AEP53_PATH_TRAVERSAL_REJECTED"},
    "atk-manifest-only-shape.aepkg": {"AEP53_MANIFEST_EPOCH_INSUFFICIENT_SHAPE"},
    "atk-provenance-forgery.aepkg": {"AEP54_DEEP_MIGRATION_RECEIPT_MISSING"},
    "atk-reliability-axis-b-contradiction.aepkg": {"AEP54_RELIABILITY_AXIS_B_CONTRADICTION"},
    "atk-epoch-replay.aepkg": {"AEP54_EPOCH_NON_MONOTONIC"},
}


@pytest.mark.parametrize(
    "fixture_name,expected_codes",
    sorted(LANE_B_EXPECTATIONS.items()),
)
def test_lane_b_attack_rejected(fixture_name: str, expected_codes: set) -> None:
    pkt = LANE_B_DIR / fixture_name
    assert pkt.exists(), f"Lane B fixture missing: {pkt}"
    result = _validate(pkt)
    seen_codes = {f.code for f in result.findings}
    intersection = expected_codes & seen_codes
    assert intersection, (
        f"Lane B fixture {fixture_name} must trigger one of {expected_codes}; "
        f"got codes: {sorted(seen_codes)}"
    )


# ============ AEP-NUMERIC-v1 cross-runtime vectors ============


def test_aep_numeric_v1_vectors_pass() -> None:
    if not NUMERIC_VECTORS.exists():
        pytest.skip(f"vectors corpus not present at {NUMERIC_VECTORS}")
    rc = run_vectors(NUMERIC_VECTORS)
    assert rc == 0, "AEP-NUMERIC-v1 vectors did not pass cleanly"


# ============ Standalone runner ============


def _run_standalone() -> int:
    """Run all tests in process (without pytest)."""
    failures = 0
    try:
        test_lane_a_minimal_example_passes_strict_l2()
        print("OK  Lane A minimal example PASS")
    except AssertionError as exc:
        print(f"FAIL Lane A minimal: {exc}")
        failures += 1
    for fixture_name, expected_codes in sorted(LANE_B_EXPECTATIONS.items()):
        try:
            test_lane_b_attack_rejected(fixture_name, expected_codes)
            print(f"OK  Lane B {fixture_name}")
        except AssertionError as exc:
            print(f"FAIL Lane B {fixture_name}: {exc}")
            failures += 1
    try:
        test_aep_numeric_v1_vectors_pass()
        print("OK  AEP-NUMERIC-v1 vectors PASS")
    except AssertionError as exc:
        print(f"FAIL AEP-NUMERIC-v1: {exc}")
        failures += 1
    print(f"\nTotal failures: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_standalone())
