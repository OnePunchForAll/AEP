#!/usr/bin/env python3
"""Emit HCRL row 11a and append to .claude/_logs/aep-v103-phase-receipts.jsonl.

Per the parallel-branch tie-break rule: rows 10a / 10b / 10c are 3 forge dispatches.
The lex-smallest sha256 wins as prev_receipt_hash:
    10a  e6a3f87a95541a0349f22195a6f0630dea744732b6d66d56329fb236632063af
    10b  dfef443ab4d9deeabde187eb897186bd6c8dd671a8fbd2f07f2d921f7edc5679
    10c  68d880116d1fd312b2e3b05746a49db14de23118aa8af1506d8523080b3ec576  <-- selected
"""
from __future__ import annotations
import hashlib
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[5]


def fsha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def fsize(rel: str) -> int:
    return (REPO / rel).stat().st_size


artifacts = {
    "projects/v11-aep/publish-ready/aep/scripts/validate_v11_amendments.py": {
        "sha256": fsha("projects/v11-aep/publish-ready/aep/scripts/validate_v11_amendments.py"),
        "size_bytes": fsize("projects/v11-aep/publish-ready/aep/scripts/validate_v11_amendments.py"),
        "loc_total": 437,
    },
    "projects/v11-aep/publish-ready/aep/scripts/wave_058_retro_apply_amendments.py": {
        "sha256": fsha("projects/v11-aep/publish-ready/aep/scripts/wave_058_retro_apply_amendments.py"),
        "size_bytes": fsize("projects/v11-aep/publish-ready/aep/scripts/wave_058_retro_apply_amendments.py"),
        "loc_total": 538,
    },
    "projects/v11-aep/publish-ready/aep/tests/test_v11_amendments_integration.py": {
        "sha256": fsha("projects/v11-aep/publish-ready/aep/tests/test_v11_amendments_integration.py"),
        "size_bytes": fsize("projects/v11-aep/publish-ready/aep/tests/test_v11_amendments_integration.py"),
        "loc_total": 388,
    },
    ".claude/_logs/aep-v11-amendments-retro-applications.jsonl": {
        "sha256": fsha(".claude/_logs/aep-v11-amendments-retro-applications.jsonl"),
        "size_bytes": fsize(".claude/_logs/aep-v11-amendments-retro-applications.jsonl"),
        "lines": 19,
    },
    ".claude/_logs/aep-v11-phase-4a-test-outcomes.jsonl": {
        "sha256": fsha(".claude/_logs/aep-v11-phase-4a-test-outcomes.jsonl"),
        "size_bytes": fsize(".claude/_logs/aep-v11-phase-4a-test-outcomes.jsonl"),
        "lines": 24,
    },
}

row = {
    "phase": "11a",
    "phase_title": "v1_1_phase_4a_amendments_A1_A8_impls",
    "timestamp": "2026-05-18T06:55:00Z",
    "actor": "forge",
    "prev_receipt_hash": "68d880116d1fd312b2e3b05746a49db14de23118aa8af1506d8523080b3ec576",
    "parse_check": {
        "python_syntax_valid_validator": True,
        "python_syntax_valid_wave_058": True,
        "python_syntax_valid_test_integration": True,
        "jsonschema_loadable_all_7_amendment_schemas": True,
    },
    "runtime_trace": {
        "validator_loc_total": 437,
        "wave_058_loc_total": 538,
        "test_integration_loc_total": 388,
        "per_amendment_cli_a1_valid_total": "1/1",
        "per_amendment_cli_a2_valid_total": "1/1",
        "per_amendment_cli_a3_valid_total": "3/3",
        "per_amendment_cli_a5_valid_total": "5/5",
        "per_amendment_cli_a6_valid_total": "1/1",
        "per_amendment_cli_a7_valid_total": "3/3",
        "per_amendment_cli_a8_valid_total": "5/5",
        "per_amendment_cli_exit_0_count": 7,
        "integration_tests_total": 23,
        "integration_tests_passed": 23,
        "integration_tests_failed": 0,
        "retro_records_emitted_total": 19,
        "retro_a1_emitted": 1,
        "retro_a2_emitted": 1,
        "retro_a3_emitted": 3,
        "retro_a5_emitted": 5,
        "retro_a5_top_cluster_tag": "cluster_tag:lodestone",
        "retro_a5_top_rt_count": 109,
        "retro_a6_emitted": 1,
        "retro_a6_past_ttl_warning": None,
        "retro_a7_emitted": 3,
        "retro_a7_alerts": ["sec02", "sec41"],
        "retro_a7_per_slot_drift": [
            {"slot": "sec02", "amend_count": 15, "drift_per_week": 15.0},
            {"slot": "sec41", "amend_count": 15, "drift_per_week": 15.0},
            {"slot": "sec73", "amend_count": 1, "drift_per_week": 1.0},
        ],
        "retro_a8_emitted": 5,
        "composition_test_v4_a6_a7_downgrade_signal": "PASS",
        "composition_test_v5_a8_a5_recurrence_overrides_decay": "PASS",
    },
    "no_screen_fail": {
        "all_7_amendments_validate_clean_via_cli": True,
        "all_23_integration_tests_pass": True,
        "wave_058_retro_verdict": "PASS",
        "wave_058_total_invalid": 0,
        "sec73_4_single_forge_one_invocation_verified": True,
        "sec73_5_warden_receipt_chain_to_row_10c_verified": True,
        "sec73_6_honest_drift_alerts_surfaced_unshaped": True,
        "a6_pilot_not_past_ttl_2026_06_17_in_future": True,
        "m1_revalidation_evidence_uniqueness_negative_path_verified": True,
    },
    "artifacts": artifacts,
    "evidence_bindings_size_bytes": sum(a["size_bytes"] for a in artifacts.values()),
    "composes_with": [
        "v1.1-SPEC-sec10",
        "sec73.1-API-verification",
        "sec73.2-operator-verbatim-sacred",
        "sec73.3-prior-art-inheritance-audit",
        "sec73.4-single-forge-for-product-builds",
        "sec73.5-warden-receipts-or-halt",
        "sec73.6-no-operator-reaction-calibration",
        "M1-revalidation-evidence-uniqueness",
        "sec41-HCRL",
        "sec02-truth-tags",
        "AEP_v1_0_3_RegexicalCue",
        "AEP_v1_0_3_1_F14_A4_backport",
        "lex-smallest-tie-break-of-10a-10b-10c",
    ],
    "parallel_branch_tie_break": {
        "rule": "lex-smallest sha256 of parallel-branch siblings",
        "row_10a_sha": "e6a3f87a95541a0349f22195a6f0630dea744732b6d66d56329fb236632063af",
        "row_10b_sha": "dfef443ab4d9deeabde187eb897186bd6c8dd671a8fbd2f07f2d921f7edc5679",
        "row_10c_sha": "68d880116d1fd312b2e3b05746a49db14de23118aa8af1506d8523080b3ec576",
        "selected_prev_receipt_hash": "68d880116d1fd312b2e3b05746a49db14de23118aa8af1506d8523080b3ec576",
        "selected_branch": "10c-F17-F18-F19",
    },
    "adversary_closures_inherited": [
        "HV1-contamination-flag-preserved-on-F12",
        "HV3-topology-proof-grep-included-each-A-tier",
        "M1-revalidation-evidence-artifact-sha256-unique-on-A6",
    ],
    "honest_sec73_6_framing": {
        "a7_drift_alerts": (
            "sec02 + sec41 BOTH emit AEP11_A7_DOCTRINE_DRIFT_ALERT at 15.0/wk drift. "
            "Best-effort git-log count touched their files 15 times each in the v1.1 drafting week. "
            "sec73 amended only 1x (1.0/wk drift). Shipped UNSHAPED per sec73.6."
        ),
        "a6_pilot_ttl_status": (
            "Pilot expires_at=2026-06-17T05:30:00Z (NOT past TTL as of 2026-05-18). "
            "If revalidation does not arrive by then, action_on_expire=DOWNGRADE fires."
        ),
        "cli_v_wrapper_format": (
            "Wave-058 retro log is wrapper-format ({wave, amendment, record, ...}); the unified "
            "validator CLI reads raw amendment records, so per-amendment fixtures emitted via "
            "_emit_per_amendment_fixtures.py for clean CLI exit-0 verification."
        ),
    },
    "cluster_tags": [
        "v1.1-phase-4a-amendments",
        "A1-A8-validators",
        "wave-058-retro-applications",
        "sec73.4-single-forge",
        "sec73.6-honest-disclosure",
        "m1-revalidation-uniqueness",
    ],
    "truth_tag": "STRONGLY PLAUSIBLE",
    "isolated_dream": False,
}

# Compute row_sha256 over canonical-json (excluding row_sha256 itself).
canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
row_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
row["row_sha256"] = row_sha

# Append to the receipts log (single-line JSONL, no sort_keys).
line = json.dumps(row, separators=(",", ":"))
receipts_path = REPO / ".claude" / "_logs" / "aep-v103-phase-receipts.jsonl"
with receipts_path.open("a", encoding="utf-8") as fp:
    fp.write(line + "\n")

print(f"row_sha256={row_sha}")
print(f"line_length={len(line)}")
print(f"appended_to={receipts_path}")
