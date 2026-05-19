#!/usr/bin/env python3
"""test_v15_phase_A_integration.py - v1.5 LTS Phase A integration tests.

Tests the cross-runtime byte-parity + production-N benchmark outputs end-to-end.

T1: Node validator emits SAME verdict as Python on 10 fixtures
T2: Perl validator emits SAME verdict as Python on 10 fixtures
T3: All 3 runtimes produce byte-identical canonical JSON (sha256 match)
T4: PreToolUse N=500 honest measurement reported (no shaping)
T5: PostToolUse N=500 p95 <= 150ms target met
T6: Viewer load p95 <= 2s target met
T7: Cross-config 60/60 same verdict
T8: Token-efficiency reduction >= 60%
T9: Token-efficiency first-turn measurement reported (honest disclosure)

Per sec73.6: HONEST measurements are the pass criterion. If a benchmark
fails its constitution target, the test PASSES (the measurement was taken
honestly); a separate scoreboard then reports the gap.

Stdlib only. Standalone (no pytest dependency).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPTS_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "scripts"
PERF_DIR = REPO_ROOT / ".claude" / "aep" / "perf"
LOGS_DIR = REPO_ROOT / ".claude" / "_logs"

BYTE_PARITY_LOG = LOGS_DIR / "aep-v15-lts-cross-runtime-byte-parity.jsonl"
SUMMARY_JSON = PERF_DIR / "v15_production_n_summary.json"
OUTCOMES_LOG = LOGS_DIR / "aep-v15-lts-phase-A-test-outcomes.jsonl"


def _read_json(path: pathlib.Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def t1_node_matches_python() -> Tuple[bool, str]:
    """Node validator emits same verdict as Python on the 10 fixtures."""
    summary = _read_json(BYTE_PARITY_LOG)
    if not summary or not isinstance(summary, dict):
        return (False, f"byte-parity log missing or unreadable at {BYTE_PARITY_LOG}")
    results = summary.get("all_results", [])
    matches = 0
    total = len(results)
    for r in results:
        py = r.get("python_canonical_sha256")
        node = r.get("node_canonical_sha256")
        if py and node and py == node:
            matches += 1
    return (matches == total and total >= 10,
            f"node_matches_python: {matches}/{total}")


def t2_perl_matches_python() -> Tuple[bool, str]:
    """Perl validator emits same verdict as Python on the 10 fixtures."""
    summary = _read_json(BYTE_PARITY_LOG)
    if not summary or not isinstance(summary, dict):
        return (False, f"byte-parity log missing or unreadable")
    results = summary.get("all_results", [])
    matches = 0
    total = len(results)
    for r in results:
        py = r.get("python_canonical_sha256")
        perl = r.get("perl_canonical_sha256")
        if py and perl and py == perl:
            matches += 1
    return (matches == total and total >= 10,
            f"perl_matches_python: {matches}/{total}")


def t3_byte_identical_across_all_three() -> Tuple[bool, str]:
    """All 3 runtimes produce byte-identical canonical JSON + sha256."""
    summary = _read_json(BYTE_PARITY_LOG)
    if not summary or not isinstance(summary, dict):
        return (False, "byte-parity log missing")
    pass_count = summary.get("pass_count", 0)
    total = summary.get("total_fixtures", 0)
    return (pass_count == total and total >= 10,
            f"byte_parity_pass: {pass_count}/{total}")


def t4_pretooluse_n_500_honest_measurement() -> Tuple[bool, str]:
    """PreToolUse N=500 honest measurement taken (no shaping). Per sec73.6 the
    HONEST measurement is what we ship; constitution target adherence is
    reported separately in the summary, not the test.
    """
    summary = _read_json(SUMMARY_JSON)
    if not summary or not isinstance(summary, dict):
        return (False, "summary JSON missing")
    pre = summary.get("pretooluse_n_500", {})
    n_collected = pre.get("n_collected", 0)
    return (n_collected >= 500,
            f"pre_n_collected={n_collected} p95={pre.get('p95_ms')}ms target={pre.get('target_ms')}ms target_met={pre.get('target_met')}")


def t5_posttooluse_n_500_target_met() -> Tuple[bool, str]:
    """PostToolUse N=500 p95 <= 150ms."""
    summary = _read_json(SUMMARY_JSON)
    if not summary or not isinstance(summary, dict):
        return (False, "summary JSON missing")
    post = summary.get("posttooluse_n_500", {})
    return (post.get("target_met", False) and post.get("n_collected", 0) >= 500,
            f"post_p95={post.get('p95_ms')}ms target={post.get('target_ms')}ms met={post.get('target_met')} n={post.get('n_collected')}")


def t6_viewer_load_target_met() -> Tuple[bool, str]:
    """Viewer load p95 <= 2s synthetic."""
    summary = _read_json(SUMMARY_JSON)
    if not summary or not isinstance(summary, dict):
        return (False, "summary JSON missing")
    viewer = summary.get("viewer_load_n_20", {})
    return (viewer.get("target_met", False),
            f"viewer_p95={viewer.get('p95_ms')}ms target={viewer.get('target_ms')}ms met={viewer.get('target_met')}")


def t7_cross_config_60_60_same_verdict() -> Tuple[bool, str]:
    """Cross-config 60/60 cells same verdict."""
    summary = _read_json(SUMMARY_JSON)
    if not summary or not isinstance(summary, dict):
        return (False, "summary JSON missing")
    cross = summary.get("cross_config_60_cells", {})
    return (cross.get("target_met", False) and cross.get("total_cells", 0) == 60,
            f"cross_config={cross.get('same_verdict_count')}/{cross.get('total_cells')} met={cross.get('target_met')}")


def t8_token_reduction_60pct() -> Tuple[bool, str]:
    """Token-efficiency reduction >= 60%."""
    summary = _read_json(SUMMARY_JSON)
    if not summary or not isinstance(summary, dict):
        return (False, "summary JSON missing")
    tokens = summary.get("token_efficiency_n_10", {})
    return (tokens.get("reduction_met", False),
            f"reduction={tokens.get('reduction_pct')}% target>={tokens.get('reduction_target_pct')}% met={tokens.get('reduction_met')}")


def t9_token_first_turn_steady_honest() -> Tuple[bool, str]:
    """Token first-turn + steady-state HONEST measurements reported.

    Per sec73.6: this test passes if the measurements WERE TAKEN (not whether
    they hit constitution target). Target adherence is reported separately.
    """
    summary = _read_json(SUMMARY_JSON)
    if not summary or not isinstance(summary, dict):
        return (False, "summary JSON missing")
    tokens = summary.get("token_efficiency_n_10", {})
    has_first = tokens.get("first_turn_tokens") is not None
    has_steady = tokens.get("steady_state_tokens") is not None
    return (has_first and has_steady,
            f"first_turn={tokens.get('first_turn_tokens')} (target<={tokens.get('first_turn_target')} met={tokens.get('first_turn_met')}) "
            f"steady={tokens.get('steady_state_tokens')} (target<={tokens.get('steady_state_target')} met={tokens.get('steady_state_met')})")


TESTS = [
    ("T1", "node_matches_python_on_10_fixtures", t1_node_matches_python),
    ("T2", "perl_matches_python_on_10_fixtures", t2_perl_matches_python),
    ("T3", "byte_identical_across_all_three", t3_byte_identical_across_all_three),
    ("T4", "pretooluse_n_500_honest_measurement", t4_pretooluse_n_500_honest_measurement),
    ("T5", "posttooluse_n_500_target_met", t5_posttooluse_n_500_target_met),
    ("T6", "viewer_load_target_met", t6_viewer_load_target_met),
    ("T7", "cross_config_60_60_same_verdict", t7_cross_config_60_60_same_verdict),
    ("T8", "token_reduction_60_pct", t8_token_reduction_60pct),
    ("T9", "token_first_turn_steady_honest_measurement", t9_token_first_turn_steady_honest),
]


def main() -> int:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    outcomes: List[Dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    for test_id, test_name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"exception: {type(e).__name__}: {e}"
        outcome = "PASS" if ok else "FAIL"
        outcomes.append({
            "test_id": test_id,
            "test_name": test_name,
            "outcome": outcome,
            "detail": detail,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        sys.stderr.write(f"[{outcome}] {test_id} {test_name}: {detail}\n")

    summary_row = {
        "schema": "aep-v15-lts-phase-A-test-summary-v1",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_tests": len(TESTS),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": pass_count / max(len(TESTS), 1),
        "all_outcomes": outcomes,
    }

    with OUTCOMES_LOG.open("w", encoding="utf-8") as f:
        f.write(json.dumps(summary_row, ensure_ascii=False, indent=2) + "\n")

    sys.stderr.write(f"\nSummary: {pass_count}/{len(TESTS)} PASS\n")
    sys.stderr.write(f"Log written to {OUTCOMES_LOG}\n")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
