#!/usr/bin/env python3
"""Emit Wave 17 (v15-lts-wave-17jj-phase-delta-5-packet-sibling-chain) HCRL row.

Chains from Wave 16 row 21 sha 2af1048a20be1624.
Truth tag: STRONGLY PLAUSIBLE for the 5-packet pilot bijection at scale.
sec73.6 honest framing: D2 further disconfirmed at 5-packet scale (NOT general DAG re-anchor).
"""
import json
import hashlib
import os
from pathlib import Path


def main() -> int:
    prior_sha = "2af1048a20be1624b2a34c313949488fe01d28eef37678f8fa6863ec72c2e36c"
    wave_id = "v15-lts-wave-17jj-phase-delta-5-packet-sibling-chain"

    row = {
        "row_index": 22,
        "wave_id": wave_id,
        "agent": "forge",
        "role": "Generator",
        "phase": "phase-delta-cluster-combine-5-packet-pilot",
        "date": "2026-05-18",
        "session_id": "wave-17jj-5-packet-sibling-132-136",
        "mission": "AEP-V15-LTS-ULTIMATE-LAST-PASS-WAVE-17-PHASE-DELTA-5-PACKET-SIBLING-CHAIN",
        "prior_sha": prior_sha,
        "umbrella_path": "doctrine/lessons/_pilot_cluster_sibling_132_133_134_135_136.aepkg",
        "umbrella_state_hash": "sha256:7abc29686608cefffdfa43a8169c510acfc1bb8a79cf542654bdb45a9ec403e4",
        "cluster_origin_sibling": "132-136",
        "cluster_origin_packets": [
            "2026-05-18-aep-v103-regexical-memory-shipped.aepkg",
            "2026-05-18-aep-v1-5-lts-warn-to-pass-via-path-c-and-airlock-self-block.aepkg",
            "2026-05-18-operator-override-indefinite-forward-aep-universalization.aepkg",
            "2026-05-18-phase-alpha-strict-pass-via-airlock-recursion-3x-navigation-indirection.aepkg",
            "2026-05-18-phase-beta-init-spec-aepification-success-plus-4-edge-cases-and-rc1-self-block.aepkg",
        ],
        "source_packet_state_hashes": [
            "sha256:70e09963dbb451008baf4d8a6babcde5e7bc7003f3768dd51b65680bda7cb866",
            "sha256:814855e9f1667711ac2f9b09997fc718df92eea2ccfdea019fba839ff3d425fa",
            "sha256:e866e406d924020dfe8eea83adb8c1c161de682f54f167c4ecf7dc5c11e5eb0c",
            "sha256:81b27d738dc9dfcef37ab5fe21d251c44a5e3c85ae2e89e00bac639fe8c7c101",
            "sha256:703acb4feb4ce2922559dc64b220a91e9b0fe0d20a0c900e54771e7a155acbcc",
        ],
        "aggregated_claim_count": 72,
        "byte_roundtrip_verdict": "PASS",
        "byte_roundtrip_per_packet_pass": 5,
        "byte_roundtrip_per_packet_total": 5,
        "ss3_sibling_n_recall_verdict": "PASS",
        "ss3_queries_tested": ["airlock", "k3", "sibling-133", "path c"],
        "ss3_match_counts_original_vs_umbrella_equal": True,
        "d6_cumulative_k3_verdict": "NO_FIRE",
        "d6_airlock_claim_refs_aggregated": 30,
        "d2_disconfirmation_at_5_packet_scale": True,
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
            "wave-16-ff-phase-delta-3-packet-disconfirmer",
        ],
        "cites": [
            "forge:wave-16-ff-phase-delta-combine-pilot",
            "adversary:wave-15-phase-gamma-delta-premortem-D2-D6",
            "lesson:sibling-132",
            "lesson:sibling-133",
            "lesson:sibling-134",
            "lesson:sibling-135",
            "lesson:sibling-136",
            "doctrine:41-hash-chained-receipt-ledger",
            "doctrine:73.6-honest-framing",
            "pattern:5-packet-pilot-scales-D2",
        ],
        "sec45_codex_burn_session_id": "019e3beb-ca97-7831-ad22-e6d435af1cc5",
        "k3_isolated_flag_v152_status": "STAGED-not-yet-on-cli-but-verified-by-content-check",
        "notes": (
            "D2 further disconfirmed at 5-packet sibling-N lesson chain scale; "
            "SS-3 sibling-N recall regression PASS (4 queries identical between "
            "umbrella aggregated read and 5-packet independent reads); D6 cumulative "
            "K3 NO_FIRE (combine emitted no airlock denial despite 30 airlock-token "
            "claim aggregation); 5/5 byte-roundtrip PASS; canonical .aepkg packets "
            "UNCHANGED; pilot paths _pilot_ prefixed."
        ),
    }

    # Compute row_sha (deterministic over canonical fields excluding self)
    canon_keys = sorted(k for k in row if k != "row_sha" and k != "row_sha_short")
    canon = json.dumps({k: row[k] for k in canon_keys}, sort_keys=True)
    row_sha = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    row["row_sha"] = row_sha
    row["row_sha_short"] = row_sha[:16]

    receipts_dir = Path(".claude/aep/receipts")
    receipts_dir.mkdir(parents=True, exist_ok=True)
    out_path = receipts_dir / "v15_wave17jj_hcrl_row.json"
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
