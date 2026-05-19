#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emit the AEP v1.5 LTS Phase 11+12 release-gate HCRL terminal row.

Per sec73.5 (WARDEN-RECEIPTS-OR-HALT): chains to prev_receipt_hash =
lex-smallest of the 4 prior Phase outcomes (Phase 6 K5 RELIABLE row).

Outputs the row to .claude/_logs/aep-v15-lts-phase-receipts.jsonl (append).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


ROOT = Path("C:/Users/example-user/")
LOG = ROOT / ".claude" / "_logs" / "aep-v15-lts-phase-receipts.jsonl"
OUTCOMES = ROOT / ".claude" / "_logs" / "aep-v15-lts-25-test-matrix-outcomes.jsonl"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    summary = None
    with OUTCOMES.open() as f:
        for ln in f:
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if obj.get("summary"):
                summary = obj
                break
    assert summary is not None, "no summary in outcomes log"

    scoreboard = ROOT / "projects/v11-aep/publish-ready/aep/reports/v15_lts_release_gate_scoreboard.md"
    release_report = ROOT / "projects/v11-aep/publish-ready/aep/reports/v15_lts_final_release_report.md"
    matrix_script = ROOT / "projects/v11-aep/publish-ready/aep/scripts/v15_lts_25_test_matrix.py"

    ts = time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + \
         ("%06dZ" % (int((time.time() * 1_000_000) % 1_000_000)))

    row = {
        "phase": "v1_5_lts_phase_11_12_release_gate",
        "phase_title": "25_test_matrix_consolidation_plus_release_verdict",
        "timestamp": ts,
        "actor": "forge",
        "prev_receipt_hash": "4464374edf1e4fa90385ae915ab501f6bd009ce5466faccc06f9e497ea67ce04",
        "operator_authority_verbatim_quoted": (
            "complete authority for all decisions ... regardless of what adversary says ... "
            "iterate until there's nothing left to do because it just works for everyone "
            "involved ... Do not self-certify from vibes. Only certify from test evidence."
        ),
        "artifacts": [
            {
                "name": "v15_lts_25_test_matrix.py",
                "path": "projects/v11-aep/publish-ready/aep/scripts/v15_lts_25_test_matrix.py",
                "role": "25-test matrix runner + lightweight validator + fixture writer",
                "bytes": matrix_script.stat().st_size,
                "sha256": sha256_file(matrix_script),
            },
            {
                "name": "v15_lts_release_gate_scoreboard.md",
                "path": "projects/v11-aep/publish-ready/aep/reports/v15_lts_release_gate_scoreboard.md",
                "role": "32-hard-gate release scoreboard",
                "bytes": scoreboard.stat().st_size,
                "sha256": sha256_file(scoreboard),
            },
            {
                "name": "v15_lts_final_release_report.md",
                "path": "projects/v11-aep/publish-ready/aep/reports/v15_lts_final_release_report.md",
                "role": "operator's 10-item final release output spec",
                "bytes": release_report.stat().st_size,
                "sha256": sha256_file(release_report),
            },
            {
                "name": "aep-v15-lts-25-test-matrix-outcomes.jsonl",
                "path": ".claude/_logs/aep-v15-lts-25-test-matrix-outcomes.jsonl",
                "role": "25 outcome rows + 1 summary row",
                "bytes": OUTCOMES.stat().st_size,
                "sha256": sha256_file(OUTCOMES),
            },
        ],
        "runtime_trace": {
            "25_test_matrix_pass_count": summary["pass_count"],
            "25_test_matrix_fail_count": summary["fail_count"],
            "25_test_matrix_staged_count": summary["staged_count"],
            "25_test_matrix_total": summary["total_categories"],
            "release_gate_pass_count": 24,
            "release_gate_partial_count": 5,
            "release_gate_staged_count": 3,
            "release_gate_fail_count": 0,
            "release_gate_total": 32,
            "aepfs_perf_p95_ms": {
                "begin": 13.446, "write": 14.905,
                "commit": 19.322, "rollback": 17.890,
            },
            "hook_perf_p95_ms": {
                "pre_tool_use": 0.678,
                "post_tool_use": 12.160,
            },
            "doctor_perf_p95_ms": {"cached": 8.3, "normal": 5.07},
            "validator_reliable_count": 9,
            "validator_total_count": 9,
            "validator_mutations_evaluated": 4050,
            "validator_critical_catch": 1.0,
            "validator_clean_fp_rate": 0.0,
            "k3_airlock_block_rate": 1.0,
            "k6_rollback_success_rate": 1.0,
            "supply_chain_zero_cdn_in_viewer": True,
            "supply_chain_hook_hashes_match_count": 5,
            "supply_chain_hook_hashes_total": 5,
            "accessibility_a11y_signals_pass": 1,
            "accessibility_a11y_signals_total": 5,
        },
        "no_screen_fail": {
            "final_verdict": "WARN",
            "verdict_basis": (
                "0 critical FAILs; 90.6 percent effective pass below 95 percent PASS "
                "threshold; 8 PARTIAL or STAGED items honestly disclosed"
            ),
            "honest_framing_applied": True,
            "registry_vs_registry_parity_disclosed": True,
            "f23_simulation_coverage_gap_inherited": True,
            "comprehension_test_n20_staged_for_operator": True,
            "accessibility_wcag_partial_staged": True,
            "no_vibes_certification": True,
        },
        "composes_with": [
            "operator-v15-LTS-directive",
            "all-prior-v1.5-phase-receipts",
            "all-prior-v1.2-phases",
            "sec68-defender-inheritance",
            "sec69.4-non-rescindable-adversary-vetoes",
            "sec69.5-operator-spec-sovereignty",
            "sec70-surface-mirror-discipline",
            "sec71-operator-sustainability",
            "sec72-canonical-order-of-operations",
            "sec73.1-API-VERIFICATION-LAW",
            "sec73.2-OPERATOR-VERBATIM-SACRED",
            "sec73.3-PRIOR-ART-INHERITANCE-AUDIT",
            "sec73.4-SINGLE-FORGE-FOR-PRODUCT-BUILDS",
            "sec73.5-WARDEN-RECEIPTS-OR-HALT",
            "sec73.6-NO-OPERATOR-REACTION-CALIBRATION",
            "phase-6-k5-receipt-4464374edf1e4fa9",
            "phase-7-10-receipt-8c102d655128c7c0",
            "phase-4-5-receipt-5c7b94a98e4fc865",
            "phase-2-3-receipt-e56a57d8bd6cfde9",
            "phase-0-receipt-290dc72b6a07888a",
        ],
    }

    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
    row["row_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    print("ROW APPENDED")
    print("phase:", row["phase"])
    print("final_verdict:", row["no_screen_fail"]["final_verdict"])
    print("prev_receipt_hash:", row["prev_receipt_hash"])
    print("row_sha256:", row["row_sha256"])
    print("matrix pass/fail/staged: %d/%d/%d of %d" % (
        row["runtime_trace"]["25_test_matrix_pass_count"],
        row["runtime_trace"]["25_test_matrix_fail_count"],
        row["runtime_trace"]["25_test_matrix_staged_count"],
        row["runtime_trace"]["25_test_matrix_total"],
    ))
    print("gate pass/partial/staged/fail: %d/%d/%d/%d of %d" % (
        row["runtime_trace"]["release_gate_pass_count"],
        row["runtime_trace"]["release_gate_partial_count"],
        row["runtime_trace"]["release_gate_staged_count"],
        row["runtime_trace"]["release_gate_fail_count"],
        row["runtime_trace"]["release_gate_total"],
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
