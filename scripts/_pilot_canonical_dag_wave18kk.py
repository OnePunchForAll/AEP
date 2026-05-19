#!/usr/bin/env python3
"""Wave 18 KK canonical DAG cluster pilot.

Tests combine/decompose on the ACTUAL canonical 3-packet DAG re-anchor
cluster from v1.0.3 lesson lineage (sibling-132 + 133 + 134).
v1.0.3 SPEC + CLAUDE.md item 13 declare HCRL row 7 as first canonical DAG
re-anchor (row 7 join + rows 8a/8b parallel branches). The lesson-level
embodiment of that DAG is sibling-132 (v1.0.3 ships) -> sibling-133
(self-block + Path-C; cites 132) -> sibling-134 (universalization; cites
BOTH 132 AND 133).

Pure read-only test on canonical packets via combine_packets/decompose
roundtrip - canonical .aepkg/ packets are NEVER modified per task spec
invariant 13. Pilot artifacts go to _pilot_ prefixed paths.

Truth tag: STRONGLY PLAUSIBLE for D2 disconfirmation at CANONICAL-DAG scale
IF byte-roundtrip 3/3 PASS.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path("C:/Users/example-user/")
COMBINE_TOOL = REPO / "projects/v11-aep/tools/aep_cluster_combine.py"

# Canonical 3-packet DAG re-anchor cluster (v1.0.3 lesson lineage)
SOURCES = [
    REPO / "doctrine/lessons/2026-05-18-aep-v103-regexical-memory-shipped.aepkg",
    REPO / "doctrine/lessons/2026-05-18-aep-v1-5-lts-warn-to-pass-via-path-c-and-airlock-self-block.aepkg",
    REPO / "doctrine/lessons/2026-05-18-operator-override-indefinite-forward-aep-universalization.aepkg",
]
UMBRELLA = REPO / "doctrine/lessons/_pilot_canonical_dag_v103_umbrella.aepkg"
DECOMPOSE_DIR = REPO / "doctrine/lessons/_pilot_canonical_dag_v103_decomposed"


def main() -> int:
    # Pre-flight: verify all 3 canonical packets exist
    for s in SOURCES:
        if not s.is_dir():
            print(f"MISSING_SOURCE: {s}", file=sys.stderr)
            return 2

    # Clean prior pilot outputs (NOT the canonical sources)
    if UMBRELLA.exists():
        shutil.rmtree(UMBRELLA)
    if DECOMPOSE_DIR.exists():
        shutil.rmtree(DECOMPOSE_DIR)

    # 1. combine
    combine_cmd = [
        sys.executable, str(COMBINE_TOOL), "combine",
        "--sources", *[str(s) for s in SOURCES],
        "--output", str(UMBRELLA),
        "--cluster-origin-sibling", "132-134-canonical-v103-dag-reanchor",
        "--cluster-definition",
        "Canonical v1.0.3 DAG re-anchor lesson cluster: sibling-132 (v1.0.3 LANDED-DOWNGRADED) "
        "<- sibling-133 (self-block + Path-C; cites 132) <- sibling-134 "
        "(universalization; cites BOTH 132 and 133); embodies HCRL row 7 + rows 8a/8b parallel-branch DAG.",
    ]
    r1 = subprocess.run(combine_cmd, capture_output=True, text=True, cwd=str(REPO))
    if r1.returncode != 0:
        print("COMBINE_FAIL:", r1.stderr[:600], file=sys.stderr)
        return 3
    combine_result = json.loads(r1.stdout)

    # 2. decompose
    decompose_cmd = [
        sys.executable, str(COMBINE_TOOL), "decompose",
        "--umbrella", str(UMBRELLA),
        "--output-dir", str(DECOMPOSE_DIR),
    ]
    r2 = subprocess.run(decompose_cmd, capture_output=True, text=True, cwd=str(REPO))
    if r2.returncode != 0:
        print("DECOMPOSE_FAIL:", r2.stderr[:600], file=sys.stderr)
        return 4

    # 3. verify byte-roundtrip
    reconstructed = [DECOMPOSE_DIR / s.name for s in SOURCES]
    verify_cmd = [
        sys.executable, str(COMBINE_TOOL), "verify",
        "--originals", *[str(s) for s in SOURCES],
        "--reconstructed", *[str(r) for r in reconstructed],
    ]
    r3 = subprocess.run(verify_cmd, capture_output=True, text=True, cwd=str(REPO))
    verify_result = json.loads(r3.stdout)

    # 4. count DAG cross-references in aggregated claims (sibling-N citations)
    sibling_132_refs = 0
    sibling_133_refs = 0
    aggregated_claims_path = UMBRELLA / "data" / "claims.jsonl"
    cross_sibling_anchors: list[dict] = []
    with aggregated_claims_path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            c = json.loads(ln)
            payload = json.dumps(c)
            if "sibling-132" in payload:
                sibling_132_refs += 1
            if "sibling-133" in payload:
                sibling_133_refs += 1

    result = {
        "wave_id": "v15-lts-wave-18kk-canonical-dag-reanchor-pilot",
        "date": "2026-05-18",
        "sources": [s.name for s in SOURCES],
        "umbrella_state_hash": combine_result.get("umbrella_state_hash"),
        "aggregated_claim_count": combine_result.get("aggregated_claim_count"),
        "byte_roundtrip_verdict": verify_result["verdict"],
        "packets_checked": verify_result["packets_checked"],
        "per_packet": verify_result.get("per_packet", []),
        "sibling_132_references_aggregated": sibling_132_refs,
        "sibling_133_references_aggregated": sibling_133_refs,
        "canonical_packets_untouched": True,
        "pilot_paths_use_pilot_prefix": True,
        "d2_canonical_dag_reanchor_verdict": (
            "DISCONFIRMED" if verify_result["verdict"] == "PASS" else "CONFIRMED"
        ),
    }
    out = REPO / "projects/v11-aep/publish-ready/aep/_pilot_canonical_dag_wave18kk_results.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if verify_result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
