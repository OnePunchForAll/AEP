#!/usr/bin/env python3
"""Wave 18 KK Phase delta DAG re-anchor synthetic 3-packet pilot.

Tests adversary D2 byte-roundtrip assumption on the load-bearing remaining
case: DAG re-anchor (packet C cites BOTH packet A AND packet B).

Composes with:
- doctrine/41 HCRL (first canonical DAG re-anchor row 7 in v1.0.3 SPEC)
- doctrine/73.6 honest framing
- sec45 codex-first burn law (parent the agent fired codex 019e3bf3 at wave start)
- sec68 defender-alert-stops-burn (pure Python; no PowerShell)
- aep_cluster_combine.py contract (byte-identical-views-under-views/<basename>/)

Truth-tag: STRONGLY PLAUSIBLE for D2 disconfirmation at DAG-shape topology
IF byte-roundtrip 3/3 PASS; SPECULATIVE FRONTIER otherwise.

Anti-patterns explicitly avoided per Codex 019e3bf3 advisory:
- target_packet preserved on every anchor (not claim_id alone) -> overlap-ids safe
- cycle detection via visited set (no recursive walk -> infinite loop)
- views directory keyed by source_packet_basename (collision-safe for self-ref)
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO = Path("C:/Users/example-user/")
COMBINE_TOOL = REPO / "projects/v11-aep/tools/aep_cluster_combine.py"
PILOT_ROOT = REPO / "_pilot_dag_anchor_wave18kk"
RESULTS_PATH = REPO / "projects/v11-aep/publish-ready/aep/_pilot_dag_anchor_wave18kk_results.json"


def _canon_json(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def _write_aepkg(pkg: Path, packet_id: str, claims: list[dict], parent_packets: list[str]) -> str:
    """Write 1 .aepkg/ with meta + claims + integrity. Returns state_hash."""
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "data").mkdir(parents=True)
    (pkg / "views").mkdir()

    meta = {
        "aep_version": "0.6",
        "packet_id": packet_id,
        "parent_packets": parent_packets,
        "synthetic": True,
        "pilot": "wave-18kk-dag-reanchor",
        "schema_version": "phase-delta-pilot-dag-anchor-v1",
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "EXPERIMENT",
    }
    (pkg / "meta.json").write_text(_canon_json(meta), encoding="utf-8")

    with (pkg / "data" / "claims.jsonl").open("w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c, sort_keys=True) + "\n")

    (pkg / "views" / "source.md").write_text(
        f"# {packet_id}\nSynthetic DAG re-anchor pilot packet.\n", encoding="utf-8"
    )

    # Compute state_hash deterministically (same algorithm as aep_cluster_combine)
    import os as _os
    rel_to_hash: dict[str, str] = {}
    for root, _dirs, files in _os.walk(pkg):
        for fn in files:
            ap = Path(root) / fn
            rel = ap.relative_to(pkg).as_posix()
            h = hashlib.sha256()
            with ap.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            rel_to_hash[rel] = h.hexdigest()
    # Write integrity AFTER tree-hash committed
    state = hashlib.sha256()
    for rel in sorted(rel_to_hash):
        state.update(rel.encode("utf-8"))
        state.update(b"\n")
        state.update(rel_to_hash[rel].encode("ascii"))
        state.update(b"\n")
    integrity = {
        "algorithm": "sha256-of-aepkg-tree-deterministic-rel-path-sha256",
        "state_hash": "sha256:" + state.hexdigest(),
        "synthetic_pilot": True,
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "EXPERIMENT",
    }
    (pkg / "integrity.json").write_text(_canon_json(integrity), encoding="utf-8")

    # Re-compute state hash to include integrity.json itself
    rel_to_hash = {}
    for root, _dirs, files in _os.walk(pkg):
        for fn in files:
            ap = Path(root) / fn
            rel = ap.relative_to(pkg).as_posix()
            h = hashlib.sha256()
            with ap.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            rel_to_hash[rel] = h.hexdigest()
    state = hashlib.sha256()
    for rel in sorted(rel_to_hash):
        state.update(rel.encode("utf-8"))
        state.update(b"\n")
        state.update(rel_to_hash[rel].encode("ascii"))
        state.update(b"\n")
    return "sha256:" + state.hexdigest()


def build_base_dag_cluster(out_root: Path) -> dict[str, Path]:
    """Base DAG: A holds c1, B holds c2 (cites A:c1), C holds c3 (cites BOTH A:c1 AND B:c2)."""
    out_root.mkdir(parents=True, exist_ok=True)
    a = out_root / "_pilot_dag_anchor_A.aepkg"
    b = out_root / "_pilot_dag_anchor_B.aepkg"
    c = out_root / "_pilot_dag_anchor_C.aepkg"

    claims_a = [{
        "claim_id": "c1",
        "text": "A root claim (linear; no parents).",
        "anchors": [],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    claims_b = [{
        "claim_id": "c2",
        "text": "B linear claim citing A.",
        "anchors": [{"target_packet": "_pilot_dag_anchor_A", "target_claim": "c1"}],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    claims_c = [{
        "claim_id": "c3",
        "text": "C DAG re-anchor claim citing BOTH A AND B (multi-parent).",
        "anchors": [
            {"target_packet": "_pilot_dag_anchor_A", "target_claim": "c1"},
            {"target_packet": "_pilot_dag_anchor_B", "target_claim": "c2"},
        ],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]

    sh_a = _write_aepkg(a, "_pilot_dag_anchor_A", claims_a, [])
    sh_b = _write_aepkg(b, "_pilot_dag_anchor_B", claims_b, ["_pilot_dag_anchor_A"])
    sh_c = _write_aepkg(c, "_pilot_dag_anchor_C", claims_c,
                        ["_pilot_dag_anchor_A", "_pilot_dag_anchor_B"])
    return {"A": a, "B": b, "C": c, "sh_A": sh_a, "sh_B": sh_b, "sh_C": sh_c}


def build_overlap_ids_cluster(out_root: Path) -> dict[str, Path]:
    """Edge case (a): A and B both have claim_id 'c1'; C cites BOTH."""
    out_root.mkdir(parents=True, exist_ok=True)
    a = out_root / "_pilot_dag_overlap_A.aepkg"
    b = out_root / "_pilot_dag_overlap_B.aepkg"
    c = out_root / "_pilot_dag_overlap_C.aepkg"

    # Same claim_id 'c1' in BOTH A and B -- source_packet_id tag must disambiguate
    claims_a = [{"claim_id": "c1", "text": "A claim with overlapping id.", "anchors": [],
                 "axis_a": "STRONGLY_PLAUSIBLE", "axis_b": "EXPERIMENT"}]
    claims_b = [{"claim_id": "c1", "text": "B claim with SAME id as A.", "anchors": [],
                 "axis_a": "STRONGLY_PLAUSIBLE", "axis_b": "EXPERIMENT"}]
    claims_c = [{
        "claim_id": "c3",
        "text": "C cites c1 from A AND c1 from B (overlapping; resolved by target_packet).",
        "anchors": [
            {"target_packet": "_pilot_dag_overlap_A", "target_claim": "c1"},
            {"target_packet": "_pilot_dag_overlap_B", "target_claim": "c1"},
        ],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    sh_a = _write_aepkg(a, "_pilot_dag_overlap_A", claims_a, [])
    sh_b = _write_aepkg(b, "_pilot_dag_overlap_B", claims_b, [])
    sh_c = _write_aepkg(c, "_pilot_dag_overlap_C", claims_c,
                        ["_pilot_dag_overlap_A", "_pilot_dag_overlap_B"])
    return {"A": a, "B": b, "C": c, "sh_A": sh_a, "sh_B": sh_b, "sh_C": sh_c}


def build_cycle_cluster(out_root: Path) -> dict[str, Path]:
    """Edge case (b): c1->c2->c3->c1 cycle. Combine should still succeed (byte-copy)."""
    out_root.mkdir(parents=True, exist_ok=True)
    a = out_root / "_pilot_dag_cycle_A.aepkg"
    b = out_root / "_pilot_dag_cycle_B.aepkg"
    c = out_root / "_pilot_dag_cycle_C.aepkg"

    claims_a = [{
        "claim_id": "c1",
        "text": "A in cycle: anchors to C:c3 (closes cycle).",
        "anchors": [{"target_packet": "_pilot_dag_cycle_C", "target_claim": "c3"}],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    claims_b = [{
        "claim_id": "c2",
        "text": "B in cycle: anchors to A:c1.",
        "anchors": [{"target_packet": "_pilot_dag_cycle_A", "target_claim": "c1"}],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    claims_c = [{
        "claim_id": "c3",
        "text": "C in cycle: anchors to B:c2.",
        "anchors": [{"target_packet": "_pilot_dag_cycle_B", "target_claim": "c2"}],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    sh_a = _write_aepkg(a, "_pilot_dag_cycle_A", claims_a, ["_pilot_dag_cycle_C"])
    sh_b = _write_aepkg(b, "_pilot_dag_cycle_B", claims_b, ["_pilot_dag_cycle_A"])
    sh_c = _write_aepkg(c, "_pilot_dag_cycle_C", claims_c, ["_pilot_dag_cycle_B"])
    return {"A": a, "B": b, "C": c, "sh_A": sh_a, "sh_B": sh_b, "sh_C": sh_c}


def build_self_ref_cluster(out_root: Path) -> dict[str, Path]:
    """Edge case (c): c3 in packet C cites itself (own claim_id in own packet)."""
    out_root.mkdir(parents=True, exist_ok=True)
    a = out_root / "_pilot_dag_self_A.aepkg"
    b = out_root / "_pilot_dag_self_B.aepkg"
    c = out_root / "_pilot_dag_self_C.aepkg"

    claims_a = [{"claim_id": "c1", "text": "A root.", "anchors": [],
                 "axis_a": "STRONGLY_PLAUSIBLE", "axis_b": "EXPERIMENT"}]
    claims_b = [{"claim_id": "c2", "text": "B linear citing A.",
                 "anchors": [{"target_packet": "_pilot_dag_self_A", "target_claim": "c1"}],
                 "axis_a": "STRONGLY_PLAUSIBLE", "axis_b": "EXPERIMENT"}]
    claims_c = [{
        "claim_id": "c3",
        "text": "C DAG re-anchor + SELF-REFERENCE (c3->c3 own packet).",
        "anchors": [
            {"target_packet": "_pilot_dag_self_A", "target_claim": "c1"},
            {"target_packet": "_pilot_dag_self_B", "target_claim": "c2"},
            {"target_packet": "_pilot_dag_self_C", "target_claim": "c3"},  # SELF
        ],
        "axis_a": "STRONGLY_PLAUSIBLE",
        "axis_b": "EXPERIMENT",
    }]
    sh_a = _write_aepkg(a, "_pilot_dag_self_A", claims_a, [])
    sh_b = _write_aepkg(b, "_pilot_dag_self_B", claims_b, ["_pilot_dag_self_A"])
    sh_c = _write_aepkg(c, "_pilot_dag_self_C", claims_c,
                        ["_pilot_dag_self_A", "_pilot_dag_self_B"])
    return {"A": a, "B": b, "C": c, "sh_A": sh_a, "sh_B": sh_b, "sh_C": sh_c}


def _aepkg_state_hash(pkg: Path) -> str:
    """Re-implementation matching aep_cluster_combine.aepkg_state_hash()."""
    import os as _os
    rel_to_hash: dict[str, str] = {}
    for root, _dirs, files in _os.walk(pkg):
        for fn in files:
            ap = Path(root) / fn
            rel = ap.relative_to(pkg).as_posix()
            h = hashlib.sha256()
            with ap.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            rel_to_hash[rel] = h.hexdigest()
    state = hashlib.sha256()
    for rel in sorted(rel_to_hash):
        state.update(rel.encode("utf-8"))
        state.update(b"\n")
        state.update(rel_to_hash[rel].encode("ascii"))
        state.update(b"\n")
    return "sha256:" + state.hexdigest()


def run_combine_decompose_verify(
    sources: list[Path],
    umbrella: Path,
    decompose_dir: Path,
    cluster_origin_sibling: str,
    cluster_definition: str,
) -> dict:
    """Run combine + decompose + verify via the existing aep_cluster_combine.py."""
    if umbrella.exists():
        shutil.rmtree(umbrella)
    if decompose_dir.exists():
        shutil.rmtree(decompose_dir)

    # 1. combine
    combine_cmd = [
        sys.executable, str(COMBINE_TOOL), "combine",
        "--sources", *[str(s) for s in sources],
        "--output", str(umbrella),
        "--cluster-origin-sibling", cluster_origin_sibling,
        "--cluster-definition", cluster_definition,
    ]
    r1 = subprocess.run(combine_cmd, capture_output=True, text=True, cwd=str(REPO))
    if r1.returncode != 0:
        return {"verdict": "FAIL", "phase": "combine", "stderr": r1.stderr[:500]}

    # 2. decompose
    decompose_cmd = [
        sys.executable, str(COMBINE_TOOL), "decompose",
        "--umbrella", str(umbrella),
        "--output-dir", str(decompose_dir),
    ]
    r2 = subprocess.run(decompose_cmd, capture_output=True, text=True, cwd=str(REPO))
    if r2.returncode != 0:
        return {"verdict": "FAIL", "phase": "decompose", "stderr": r2.stderr[:500]}

    # 3. verify
    reconstructed = [decompose_dir / s.name for s in sources]
    verify_cmd = [
        sys.executable, str(COMBINE_TOOL), "verify",
        "--originals", *[str(s) for s in sources],
        "--reconstructed", *[str(r) for r in reconstructed],
    ]
    r3 = subprocess.run(verify_cmd, capture_output=True, text=True, cwd=str(REPO))
    try:
        verify_result = json.loads(r3.stdout)
    except Exception:
        verify_result = {"verdict": "FAIL", "phase": "verify-json-parse", "stdout": r3.stdout[:500]}

    return {
        "verdict": verify_result.get("verdict", "UNKNOWN"),
        "packets_checked": verify_result.get("packets_checked", 0),
        "per_packet": verify_result.get("per_packet", []),
        "phase": "verify",
        "umbrella_path": str(umbrella),
    }


def cluster_dag_check(claims_files: list[Path], cluster_label: str) -> dict:
    """Verify DAG references survive aggregation (per-claim anchor preservation).

    For BASE DAG: c3 in C must have BOTH anchors target_packet pointing at A and B.
    Read aggregated umbrella claims.jsonl AND original claim files; count anchors.
    """
    total_anchors = 0
    c3_anchors: list[dict] = []
    for cf in claims_files:
        with cf.open("r", encoding="utf-8") as fh:
            for ln in fh:
                if not ln.strip():
                    continue
                claim = json.loads(ln)
                total_anchors += len(claim.get("anchors", []))
                if claim.get("claim_id") == "c3":
                    c3_anchors = claim.get("anchors", [])
    return {
        "cluster": cluster_label,
        "total_anchors": total_anchors,
        "c3_anchor_count": len(c3_anchors),
        "c3_anchors": c3_anchors,
    }


def run_pilot() -> dict:
    """Run all 4 pilot variants and return consolidated results."""
    PILOT_ROOT.mkdir(parents=True, exist_ok=True)
    results: dict = {
        "wave_id": "v15-lts-wave-18kk-phase-delta-dag-reanchor-pilot",
        "date": "2026-05-18",
        "variants": {},
    }

    # ------------------------------------------------------------------
    # Variant 1: BASE DAG (canonical 3-packet multi-parent)
    # ------------------------------------------------------------------
    base_root = PILOT_ROOT / "base"
    base = build_base_dag_cluster(base_root)
    base_umb = PILOT_ROOT / "base_umbrella.aepkg"
    base_dec = PILOT_ROOT / "base_decomposed"
    base_result = run_combine_decompose_verify(
        sources=[base["A"], base["B"], base["C"]],
        umbrella=base_umb,
        decompose_dir=base_dec,
        cluster_origin_sibling="wave-18kk-base-dag",
        cluster_definition="Synthetic 3-packet DAG re-anchor: A linear, B cites A, C cites BOTH A and B.",
    )
    base_dag_check_pre = cluster_dag_check(
        [base["A"] / "data/claims.jsonl",
         base["B"] / "data/claims.jsonl",
         base["C"] / "data/claims.jsonl"],
        "base-pre-combine",
    )
    base_dag_check_post = cluster_dag_check(
        [base_umb / "data/claims.jsonl"],
        "base-post-combine",
    )
    results["variants"]["base"] = {
        "byte_roundtrip": base_result,
        "dag_preserved_pre": base_dag_check_pre,
        "dag_preserved_post": base_dag_check_post,
        "dag_c3_parent_count_pre": base_dag_check_pre["c3_anchor_count"],
        "dag_c3_parent_count_post": base_dag_check_post["c3_anchor_count"],
        "dag_preserved": base_dag_check_pre["c3_anchor_count"]
                         == base_dag_check_post["c3_anchor_count"]
                         == 2,
    }

    # ------------------------------------------------------------------
    # Variant 2: OVERLAP IDS (edge case a)
    # ------------------------------------------------------------------
    overlap_root = PILOT_ROOT / "overlap"
    overlap = build_overlap_ids_cluster(overlap_root)
    overlap_umb = PILOT_ROOT / "overlap_umbrella.aepkg"
    overlap_dec = PILOT_ROOT / "overlap_decomposed"
    overlap_result = run_combine_decompose_verify(
        sources=[overlap["A"], overlap["B"], overlap["C"]],
        umbrella=overlap_umb,
        decompose_dir=overlap_dec,
        cluster_origin_sibling="wave-18kk-overlap",
        cluster_definition="3-packet DAG with overlapping claim_id 'c1' across A and B; C cites both.",
    )
    # Count distinct (source_packet_basename, claim_id) tuples in umbrella aggregated
    distinct_tuples: set = set()
    with (overlap_umb / "data/claims.jsonl").open("r", encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            c = json.loads(ln)
            distinct_tuples.add((c.get("source_packet_basename"), c.get("claim_id")))
    results["variants"]["overlap_ids"] = {
        "byte_roundtrip": overlap_result,
        "distinct_packet_claim_tuples": len(distinct_tuples),
        "overlap_disambiguated": len(distinct_tuples) == 3,
        "tuples_seen": [list(t) for t in sorted(distinct_tuples, key=str)],
    }

    # ------------------------------------------------------------------
    # Variant 3: CYCLE (edge case b)
    # ------------------------------------------------------------------
    cycle_root = PILOT_ROOT / "cycle"
    cycle = build_cycle_cluster(cycle_root)
    cycle_umb = PILOT_ROOT / "cycle_umbrella.aepkg"
    cycle_dec = PILOT_ROOT / "cycle_decomposed"
    cycle_result = run_combine_decompose_verify(
        sources=[cycle["A"], cycle["B"], cycle["C"]],
        umbrella=cycle_umb,
        decompose_dir=cycle_dec,
        cluster_origin_sibling="wave-18kk-cycle",
        cluster_definition="3-packet DAG with cycle c1->c2->c3->c1 across A/B/C.",
    )
    # Combine tool is byte-copy; cycle should not cause infinite loop because
    # tool does not traverse anchor graph. Verify by checking combine succeeded.
    results["variants"]["cycle"] = {
        "byte_roundtrip": cycle_result,
        "cycle_caused_hang_or_crash": cycle_result.get("verdict") not in ("PASS", "FAIL"),
        "tool_treats_anchors_as_data_not_traversal": cycle_result.get("verdict") == "PASS",
    }

    # ------------------------------------------------------------------
    # Variant 4: SELF-REFERENCE (edge case c)
    # ------------------------------------------------------------------
    self_root = PILOT_ROOT / "self"
    self_ref = build_self_ref_cluster(self_root)
    self_umb = PILOT_ROOT / "self_umbrella.aepkg"
    self_dec = PILOT_ROOT / "self_decomposed"
    self_result = run_combine_decompose_verify(
        sources=[self_ref["A"], self_ref["B"], self_ref["C"]],
        umbrella=self_umb,
        decompose_dir=self_dec,
        cluster_origin_sibling="wave-18kk-self-ref",
        cluster_definition="3-packet DAG where c3 in C self-references its own packet.",
    )
    # Count c3 anchors post-combine (should be 3: A:c1 + B:c2 + C:c3)
    self_c3_anchors_post: list[dict] = []
    with (self_umb / "data/claims.jsonl").open("r", encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            c = json.loads(ln)
            if c.get("claim_id") == "c3":
                self_c3_anchors_post = c.get("anchors", [])
    results["variants"]["self_ref"] = {
        "byte_roundtrip": self_result,
        "self_ref_c3_anchor_count_post": len(self_c3_anchors_post),
        "self_ref_preserved": len(self_c3_anchors_post) == 3,
        "anchors_post": self_c3_anchors_post,
    }

    # ------------------------------------------------------------------
    # CONSOLIDATED VERDICT
    # ------------------------------------------------------------------
    all_pass = all(
        v["byte_roundtrip"].get("verdict") == "PASS"
        for v in results["variants"].values()
    )
    dag_preserved = results["variants"]["base"]["dag_preserved"]
    overlap_disambig = results["variants"]["overlap_ids"]["overlap_disambiguated"]
    cycle_safe = results["variants"]["cycle"]["tool_treats_anchors_as_data_not_traversal"]
    self_ref_safe = results["variants"]["self_ref"]["self_ref_preserved"]

    results["consolidated_verdict"] = {
        "byte_roundtrip_all_4_variants_pass": all_pass,
        "dag_re_anchor_2_parents_preserved_in_base": dag_preserved,
        "overlap_ids_disambiguated_via_source_packet_basename": overlap_disambig,
        "cycle_does_not_hang_or_crash_combine": cycle_safe,
        "self_ref_preserved_3_anchors_post_combine": self_ref_safe,
        "d2_disconfirmed_at_dag_reanchor_topology": all_pass and dag_preserved
                                                    and overlap_disambig and cycle_safe
                                                    and self_ref_safe,
    }

    return results


def main() -> int:
    results = run_pilot()
    RESULTS_PATH.write_text(_canon_json(results), encoding="utf-8")
    print(json.dumps(results["consolidated_verdict"], indent=2, sort_keys=True))
    print("\nFULL_RESULTS:", str(RESULTS_PATH))
    return 0 if results["consolidated_verdict"]["d2_disconfirmed_at_dag_reanchor_topology"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
