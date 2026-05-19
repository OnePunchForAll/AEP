#!/usr/bin/env python3
"""Emit Wave 18kk (Phase delta DAG re-anchor pilot) HCRL row.

Chains from Wave 17jj row 22 sha 604f62da299961b0ee5f874fd97bbd9018163c99e69bd8174daff0df8a5c5816.
Truth tag: STRONGLY PLAUSIBLE for D2 disconfirmation at DAG re-anchor topology.
sec73.6 honest framing: D2 disconfirmed across synthetic + canonical DAG; NOT yet
at 10+ packet scale or cross-cohort cluster shape (STAGED next phase).
"""
import json
import hashlib
from pathlib import Path


def main() -> int:
    prior_sha = "604f62da299961b0ee5f874fd97bbd9018163c99e69bd8174daff0df8a5c5816"
    wave_id = "v15-lts-wave-18kk-phase-delta-dag-reanchor-pilot"

    # Load synthetic pilot results
    synth_results = json.loads(
        Path("projects/v11-aep/publish-ready/aep/_pilot_dag_anchor_wave18kk_results.json")
        .read_text(encoding="utf-8")
    )
    # Load canonical pilot results
    canon_results = json.loads(
        Path("projects/v11-aep/publish-ready/aep/_pilot_canonical_dag_wave18kk_results.json")
        .read_text(encoding="utf-8")
    )

    row = {
        "row_index": 23,
        "wave_id": wave_id,
        "agent": "forge",
        "role": "Generator",
        "phase": "phase-delta-dag-reanchor-3-packet-pilot",
        "date": "2026-05-18",
        "session_id": "wave-18kk-dag-reanchor-pilot",
        "mission": "AEP-V15-LTS-ULTIMATE-LAST-PASS-WAVE-18-PHASE-DELTA-DAG-REANCHOR",
        "prior_sha": prior_sha,
        # Synthetic pilot summary (4 variants: base + overlap_ids + cycle + self_ref)
        "synthetic_base_dag_byte_roundtrip": synth_results["variants"]["base"]["byte_roundtrip"]["verdict"],
        "synthetic_base_dag_2_parents_preserved": synth_results["variants"]["base"]["dag_preserved"],
        "synthetic_overlap_ids_byte_roundtrip": synth_results["variants"]["overlap_ids"]["byte_roundtrip"]["verdict"],
        "synthetic_overlap_ids_disambiguated": synth_results["variants"]["overlap_ids"]["overlap_disambiguated"],
        "synthetic_cycle_byte_roundtrip": synth_results["variants"]["cycle"]["byte_roundtrip"]["verdict"],
        "synthetic_cycle_no_hang_no_crash": synth_results["variants"]["cycle"]["tool_treats_anchors_as_data_not_traversal"],
        "synthetic_self_ref_byte_roundtrip": synth_results["variants"]["self_ref"]["byte_roundtrip"]["verdict"],
        "synthetic_self_ref_preserved_3_anchors": synth_results["variants"]["self_ref"]["self_ref_preserved"],
        # Canonical v1.0.3 DAG cluster summary
        "canonical_v103_dag_cluster_packets": canon_results["sources"],
        "canonical_v103_dag_byte_roundtrip_verdict": canon_results["byte_roundtrip_verdict"],
        "canonical_v103_dag_packets_checked": canon_results["packets_checked"],
        "canonical_v103_dag_aggregated_claim_count": canon_results["aggregated_claim_count"],
        "canonical_v103_dag_umbrella_state_hash": canon_results["umbrella_state_hash"],
        # CONSOLIDATED D2 verdict at DAG re-anchor topology
        "d2_disconfirmed_synthetic_dag": synth_results["consolidated_verdict"]["d2_disconfirmed_at_dag_reanchor_topology"],
        "d2_disconfirmed_canonical_dag": canon_results["d2_canonical_dag_reanchor_verdict"] == "DISCONFIRMED",
        "d2_general_case_disconfirmed_at_dag_reanchor": (
            synth_results["consolidated_verdict"]["d2_disconfirmed_at_dag_reanchor_topology"]
            and canon_results["d2_canonical_dag_reanchor_verdict"] == "DISCONFIRMED"
        ),
        "phase_delta_broad_launch_readiness": "READY",
        "phase_delta_residuals_staged_for_next_phase": [
            "10+ packet scaling pilot (Wave 17 sibling-N at 10x scale)",
            "Cross-cohort cluster (lesson + doctrine slot + research) heterogeneous shape",
            "Production-N corpus-wide 1112+ packets pilot",
        ],
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "EXPERIMENT",
        "composes_with": [
            "sec02",
            "sec41",
            "sec45",
            "sec50",
            "sec68",
            "sec69",
            "sec70",
            "sec71",
            "sec72",
            "sec73",
            "wave-16-ff-3-packet-bijective-disconfirmer",
            "wave-17-jj-5-packet-sibling-chain-disconfirmer",
            "v103-spec-hcrl-row-7-first-canonical-dag-reanchor",
        ],
        "cites": [
            "forge:wave-17-jj-phase-delta-5-packet-sibling-chain",
            "forge:wave-16-ff-phase-delta-combine-pilot",
            "judge:wave-17-d2-verification",
            "adversary:wave-15-phase-gamma-delta-premortem-D2-section-8-residual",
            "doctrine:41-hash-chained-receipt-ledger",
            "doctrine:73.6-honest-framing",
            "spec:AEP_v1_0_3_SPEC-hcrl-row-7-canonical-dag-reanchor",
            "pattern:dag-reanchor-bijection-via-byte-identical-views",
        ],
        "sec45_codex_burn_session_ids": [
            "019e3bf3-9ffa-7d70-b5e5-9401c882de33",  # design-skeleton burn at wave start
        ],
        "notes": (
            "D2 disconfirmed at DAG re-anchor topology on both synthetic (3-packet base + "
            "3 edge cases: overlap_ids/cycle/self_ref) AND canonical v1.0.3 3-packet "
            "DAG cluster (siblings 132/133/134). 4/4 synthetic variants byte-roundtrip "
            "PASS; canonical 3/3 byte-roundtrip PASS. Tool treats anchors as DATA (not "
            "traversal target) so cycle/self-ref naturally safe. Overlap claim_ids "
            "disambiguated via additive source_packet_basename tag (3 distinct "
            "(packet, claim_id) tuples preserved). Phase delta READY for broad launch; "
            "STAGED residuals: 10+ packet scale, cross-cohort heterogeneous, corpus-wide 1112+."
        ),
    }

    # Compute deterministic row_sha
    canon_keys = sorted(k for k in row if k not in ("row_sha", "row_sha_short"))
    canon = json.dumps({k: row[k] for k in canon_keys}, sort_keys=True)
    row_sha = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    row["row_sha"] = row_sha
    row["row_sha_short"] = row_sha[:16]

    receipts_dir = Path(".claude/aep/receipts")
    receipts_dir.mkdir(parents=True, exist_ok=True)
    out_path = receipts_dir / "v15_wave18kk_hcrl_row.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(row, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print("HCRL_ROW_SHA:", row_sha)
    print("HCRL_ROW_SHA_SHORT:", row_sha[:16])
    print("PRIOR_SHA:", prior_sha)
    print("WRITTEN:", str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
