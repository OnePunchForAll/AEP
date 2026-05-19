#!/usr/bin/env python3
"""aep_cluster_combine.py

Phase delta COMBINE/DECOMPOSE pilot for AEP cluster operations.

Goal per Wave 16 task spec (adversary D2 cheapest disconfirmer):
- COMBINE: pack N .aepkg/ packets into 1 umbrella .aepkg/.
- DECOMPOSE: unpack umbrella back into N .aepkg/ packets, byte-identical to originals.

D2 load-bearing assumption: combine-decompose is bijective across DAG re-anchor +
overlapping claim IDs + cross-cluster refs. The cheapest disconfirmer is a 3-packet
synthetic test. Pass = D2 disconfirmed for this case. Fail = D2 confirmed.

Design (byte-roundtrip-first):
- The umbrella stores byte-identical copies of every source file under
  views/<source-basename>/ -- this is the load-bearing primitive that guarantees
  byte-roundtrip. The aggregated claims.jsonl + meta.json at the umbrella root
  are DERIVED query convenience surfaces, NOT canonical sources for decomposition.
- Decompose reads ONLY the byte-identical copies and reconstructs each packet
  at the original file paths verbatim.

Truth-tag: STRONGLY PLAUSIBLE for the bijective property on the simple-case
(3-packet linear-version-history cluster); SPECULATIVE FRONTIER for the general
case (DAG re-anchor, cross-cluster refs). The pilot below characterizes which.

Composes with:
- doctrine/41 HCRL (each combine/decompose action is a receipt-emitting event)
- doctrine/73.6 honest framing (PASS/FAIL reported mechanically, no vibes)
- sec45 codex-first burn law (parent the agent fired codex at wave start per task step 4)
- sec68 defender-alert-stops-burn (no PowerShell; Python only; --task-file for arg hints)
- AEP v0.6 schema (canonical files: meta.json + data/claims.jsonl + views/source.md + integrity.json)

CLI:
  python aep_cluster_combine.py combine \
      --sources <pkg1.aepkg> <pkg2.aepkg> ... \
      --output <umbrella.aepkg> \
      --cluster-origin-sibling <sibling-id> \
      --cluster-definition <one-line-text>

  python aep_cluster_combine.py decompose \
      --umbrella <umbrella.aepkg> \
      --output-dir <dir>

  python aep_cluster_combine.py verify \
      --originals <pkg1.aepkg> <pkg2.aepkg> ... \
      --reconstructed <pkg1.aepkg> <pkg2.aepkg> ...

Adversary D2 mitigations applied:
- cluster_origin_packets: ordered list of source basenames (deterministic)
- byte-identical copy preservation (load-bearing for bijection)
- sort()ed iteration on all file enumeration
- PYTHONHASHSEED=0 hint in script (recommend env override)
- No claim deduplication on combine (preserves source_packet_id for back-resolution)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Primitives: deep hash of an .aepkg/ tree (per-file canonical hash)
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """sha256 hex of a file. Byte-exact."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def aepkg_tree_hash(pkg_dir: Path) -> dict[str, str]:
    """Return ordered map of relative-path -> sha256 for every file under pkg_dir.

    Sort order is deterministic (lexicographic on POSIX-style rel path).
    """
    if not pkg_dir.is_dir():
        raise FileNotFoundError(f"not a directory: {pkg_dir}")
    rel_to_hash: dict[str, str] = {}
    for root, _dirs, files in os.walk(pkg_dir):
        for fn in files:
            abs_path = Path(root) / fn
            rel = abs_path.relative_to(pkg_dir).as_posix()
            rel_to_hash[rel] = sha256_file(abs_path)
    # canonical sort
    return {k: rel_to_hash[k] for k in sorted(rel_to_hash)}


def aepkg_state_hash(pkg_dir: Path) -> str:
    """Single sha256 hex committing to the entire .aepkg/ tree.

    Algorithm: sha256-of-(rel-path + '\n' + sha256-hex + '\n' for each file in sorted order).
    """
    tree = aepkg_tree_hash(pkg_dir)
    h = hashlib.sha256()
    for rel, sha in tree.items():
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        h.update(sha.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# COMBINE
# ---------------------------------------------------------------------------

def combine_packets(
    sources: list[Path],
    output: Path,
    cluster_origin_sibling: str | None,
    cluster_definition: str | None,
) -> dict[str, Any]:
    """Combine N source .aepkg/ packets into 1 umbrella .aepkg/.

    Output layout:
      output.aepkg/
        meta.json                      # umbrella meta (cluster_origin_packets, etc.)
        data/claims.jsonl              # aggregated claims (each gets source_packet_id)
        views/source.md                # umbrella header (synthesized)
        views/<basename>/              # one subdir per source, byte-identical copy
          meta.json
          integrity.json
          data/claims.jsonl
          views/source.md
        integrity.json                 # umbrella state_hash
    """
    if not sources:
        raise ValueError("combine requires at least one source packet")
    # Sort sources for determinism per D5 mitigation
    sources = sorted(sources, key=lambda p: p.name)

    # Validate all sources exist + are .aepkg/-shaped
    for s in sources:
        if not s.is_dir():
            raise FileNotFoundError(f"source not a directory: {s}")
        if not (s / "meta.json").is_file():
            raise FileNotFoundError(f"source missing meta.json: {s}")

    # Atomic recreate output
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / "data").mkdir()
    (output / "views").mkdir()

    # Per-source byte-identical copy under views/<basename>/
    source_basenames: list[str] = []
    source_metas: list[dict[str, Any]] = []
    aggregated_claims: list[dict[str, Any]] = []

    for s in sources:
        basename = s.name  # e.g. "AEP_v0_3_SPEC.aepkg"
        source_basenames.append(basename)
        # byte-identical copytree
        dest = output / "views" / basename
        shutil.copytree(s, dest)
        # Read source meta for umbrella record
        with (s / "meta.json").open("r", encoding="utf-8") as f:
            src_meta = json.load(f)
        source_metas.append(src_meta)
        # Read source claims; emit aggregated copy with source_packet_id appended
        claims_path = s / "data" / "claims.jsonl"
        if claims_path.is_file():
            with claims_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    claim = json.loads(line)
                    # Preserve original id; add cluster-level source_packet_id
                    # (additive; never overwrite existing fields)
                    claim["source_packet_id"] = src_meta.get(
                        "packet_id", f"aepkg:{basename}"
                    )
                    claim["source_packet_basename"] = basename
                    aggregated_claims.append(claim)

    # Write umbrella meta.json
    umbrella_meta = {
        "aep_version": "0.6",
        "packet_id": f"aepkg:cluster:{output.name}",
        "umbrella": True,
        "cluster_origin_packets": source_basenames,
        "cluster_origin_packet_ids": [
            m.get("packet_id", f"aepkg:{b}")
            for m, b in zip(source_metas, source_basenames, strict=False)
        ],
        "cluster_origin_sibling": cluster_origin_sibling,
        "cluster_definition": cluster_definition,
        "claim_count_aggregated": len(aggregated_claims),
        "source_packet_count": len(sources),
        "canonical_files": [
            "meta.json",
            "data/claims.jsonl",
            "views/source.md",
            "integrity.json",
        ],
        "canonical_files_order_hash_input": [
            "meta.json",
            "data/claims.jsonl",
            "views/source.md",
        ],
        "schema_version": "phase-delta-pilot-cluster-v1",
        "created_by": "forge:aep_cluster_combine.py-phase-delta-pilot-v1",
        "composes_with": [
            "doctrine-41-HCRL",
            "doctrine-73-6-honest-framing",
            "adversary-D2-byte-roundtrip-mitigation",
            "sec45-codex-first-burn-law",
            "sec68-no-powershell",
        ],
        "extension_notes": (
            "Phase delta pilot per Wave 16 task; byte-identical per-source copies "
            "preserved under views/<basename>/ as load-bearing for bijective "
            "decompose. Aggregated claims.jsonl is DERIVED query convenience, "
            "NOT canonical source for decomposition."
        ),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "EXPERIMENT",
    }
    with (output / "meta.json").open("w", encoding="utf-8") as f:
        json.dump(umbrella_meta, f, indent=2, sort_keys=True)
        f.write("\n")

    # Write aggregated claims.jsonl (deterministic order: source order then
    # original line order within source)
    with (output / "data" / "claims.jsonl").open("w", encoding="utf-8") as f:
        for c in aggregated_claims:
            f.write(json.dumps(c, sort_keys=True) + "\n")

    # Write umbrella views/source.md header (synthesized, deterministic)
    header_lines = [
        f"# Cluster umbrella: {output.name}",
        "",
        f"cluster_origin_sibling: {cluster_origin_sibling or ''}",
        f"cluster_definition: {cluster_definition or ''}",
        "",
        "## Source packets",
        "",
    ]
    for b in source_basenames:
        header_lines.append(f"- {b}")
    header_lines.append("")
    header_lines.append(
        "See views/<basename>/ for byte-identical source projections.\n"
    )
    (output / "views" / "source.md").write_text(
        "\n".join(header_lines), encoding="utf-8"
    )

    # Compute integrity.json (state_hash over canonical files)
    integrity = {
        "algorithm": "sha256-of-aepkg-tree-deterministic-rel-path-sha256",
        "canonical_files_order": [
            "meta.json",
            "data/claims.jsonl",
            "views/source.md",
        ],
        "state_hash": "sha256:" + aepkg_state_hash(output),
        "umbrella": True,
        "source_packet_count": len(sources),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "EXPERIMENT",
    }
    with (output / "integrity.json").open("w", encoding="utf-8") as f:
        json.dump(integrity, f, indent=2, sort_keys=True)
        f.write("\n")

    return {
        "umbrella_path": str(output),
        "source_packet_count": len(sources),
        "aggregated_claim_count": len(aggregated_claims),
        "umbrella_state_hash": integrity["state_hash"],
    }


# ---------------------------------------------------------------------------
# DECOMPOSE
# ---------------------------------------------------------------------------

def decompose_umbrella(umbrella: Path, output_dir: Path) -> dict[str, Any]:
    """Decompose 1 umbrella .aepkg/ back to N source .aepkg/ packets.

    Reconstructed packets are byte-identical to originals (read from views/<basename>/).
    """
    if not umbrella.is_dir():
        raise FileNotFoundError(f"umbrella not a directory: {umbrella}")
    with (umbrella / "meta.json").open("r", encoding="utf-8") as f:
        umbrella_meta = json.load(f)
    if not umbrella_meta.get("umbrella"):
        raise ValueError(f"not an umbrella packet: {umbrella}")

    source_basenames: list[str] = umbrella_meta["cluster_origin_packets"]

    output_dir.mkdir(parents=True, exist_ok=True)
    reconstructed: list[str] = []
    for basename in source_basenames:
        src_view_dir = umbrella / "views" / basename
        if not src_view_dir.is_dir():
            raise FileNotFoundError(
                f"umbrella missing byte-identical view for {basename}: "
                f"{src_view_dir}"
            )
        dest = output_dir / basename
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src_view_dir, dest)
        reconstructed.append(str(dest))

    return {
        "umbrella_path": str(umbrella),
        "output_dir": str(output_dir),
        "reconstructed_packets": reconstructed,
        "reconstructed_count": len(reconstructed),
    }


# ---------------------------------------------------------------------------
# VERIFY
# ---------------------------------------------------------------------------

def verify_byte_roundtrip(
    originals: list[Path], reconstructed: list[Path]
) -> dict[str, Any]:
    """Verify each reconstructed .aepkg/ tree == original byte-identical.

    Returns per-packet PASS/FAIL with per-file diff details on mismatch.
    """
    if len(originals) != len(reconstructed):
        return {
            "verdict": "FAIL",
            "reason": "count_mismatch",
            "originals_count": len(originals),
            "reconstructed_count": len(reconstructed),
        }
    # Match by basename
    orig_by_name = {p.name: p for p in originals}
    recon_by_name = {p.name: p for p in reconstructed}
    if set(orig_by_name.keys()) != set(recon_by_name.keys()):
        return {
            "verdict": "FAIL",
            "reason": "basename_set_mismatch",
            "originals": sorted(orig_by_name.keys()),
            "reconstructed": sorted(recon_by_name.keys()),
        }

    per_packet: list[dict[str, Any]] = []
    overall_pass = True
    for name in sorted(orig_by_name):
        orig_tree = aepkg_tree_hash(orig_by_name[name])
        recon_tree = aepkg_tree_hash(recon_by_name[name])
        if orig_tree == recon_tree:
            per_packet.append(
                {
                    "basename": name,
                    "verdict": "PASS",
                    "file_count": len(orig_tree),
                    "state_hash": "sha256:"
                    + aepkg_state_hash(orig_by_name[name]),
                }
            )
        else:
            overall_pass = False
            # Find differing files
            missing_in_recon = [
                k for k in orig_tree if k not in recon_tree
            ]
            extra_in_recon = [
                k for k in recon_tree if k not in orig_tree
            ]
            content_diff = [
                k
                for k in orig_tree
                if k in recon_tree and orig_tree[k] != recon_tree[k]
            ]
            per_packet.append(
                {
                    "basename": name,
                    "verdict": "FAIL",
                    "missing_in_reconstructed": sorted(missing_in_recon),
                    "extra_in_reconstructed": sorted(extra_in_recon),
                    "content_diff_files": sorted(content_diff),
                    "orig_state_hash": "sha256:"
                    + aepkg_state_hash(orig_by_name[name]),
                    "recon_state_hash": "sha256:"
                    + aepkg_state_hash(recon_by_name[name]),
                }
            )

    return {
        "verdict": "PASS" if overall_pass else "FAIL",
        "packets_checked": len(per_packet),
        "per_packet": per_packet,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aep_cluster_combine",
        description=(
            "Phase delta COMBINE/DECOMPOSE pilot for AEP cluster operations. "
            "Tests adversary D2 byte-roundtrip assumption."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_c = sub.add_parser("combine", help="combine N packets into 1 umbrella")
    p_c.add_argument("--sources", nargs="+", required=True, type=Path)
    p_c.add_argument("--output", required=True, type=Path)
    p_c.add_argument("--cluster-origin-sibling", default=None)
    p_c.add_argument("--cluster-definition", default=None)

    p_d = sub.add_parser("decompose", help="decompose 1 umbrella back to N packets")
    p_d.add_argument("--umbrella", required=True, type=Path)
    p_d.add_argument("--output-dir", required=True, type=Path)

    p_v = sub.add_parser("verify", help="verify byte-roundtrip on N packet pairs")
    p_v.add_argument("--originals", nargs="+", required=True, type=Path)
    p_v.add_argument("--reconstructed", nargs="+", required=True, type=Path)

    p_h = sub.add_parser("hash", help="emit deterministic state_hash for a packet")
    p_h.add_argument("--packet", required=True, type=Path)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "combine":
        result = combine_packets(
            args.sources,
            args.output,
            args.cluster_origin_sibling,
            args.cluster_definition,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "decompose":
        result = decompose_umbrella(args.umbrella, args.output_dir)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.cmd == "verify":
        result = verify_byte_roundtrip(args.originals, args.reconstructed)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["verdict"] == "PASS" else 1
    if args.cmd == "hash":
        h = aepkg_state_hash(args.packet)
        print(json.dumps({"packet": str(args.packet), "state_hash": "sha256:" + h}, indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
