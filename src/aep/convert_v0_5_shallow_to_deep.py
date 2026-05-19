"""
convert_v0_5_shallow_to_deep.py — Apache-2.0 — Deep migration v0.5 (shallow) → v0.5 (deep).

Closes the critical discovery from sibling-58: the v0.3 → v0.5 migration tool added
v0.5 hashes + manifest fields but did NOT add v0.5-specific per-record fields. The
resulting "shallow v0.5" packets declare aep_version="0.5" but carry only v0.3
record shape, which v0.5.1 correctly fail-closes with AEP51_VERSION_SCHEMA_MISMATCH.

This deep migration adds v0.5-specific per-record fields where defaults are
unambiguous, derived from the existing reliability tags + AEP project §02 → Axis-B
mapping table (operator-approved 2026-05-14, see projects/v11-aep/CLAUDE.md).

After deep migration, packets should validate clean at v0.5.1 strict Level-2.

Field-level changes applied:

Per claim:
  - axis_b_action: derived from reliability + claim status:
    * PROVEN_RELIABLE     → GO
    * STRONGLY_PLAUSIBLE  → GO  (operator-supplied default per the mapping table)
    * PLAUSIBLE           → EXPERIMENT
    * EXPERIMENTAL        → EXPERIMENT (legacy mapping)
    * ASSUMPTION          → EXPLORE
    * SPECULATIVE_FRONTIER→ EXPLORE
    * CONFLICTED          → HALT
    * UNKNOWN             → omit (UNKNOWN claims keep no axis_b_action)
    * GOVERNANCE_RULE     → GO
    * DANGEROUS_NOT_WORTH_DOING → FORBIDDEN
    * Anything else       → omit
  - decision_time_revalidation_required: default False (operator can opt-in per claim).
  - go_justification_claim_ids: for claims with axis_b_action=GO AND reliability=GOVERNANCE_RULE,
    emit a stub empty list — operator/agent fills in real claim_ids on next packet write.

Per manifest:
  - integrity already includes state_hash + manifest_hash + assets_merkle_root from
    the shallow migration. After field additions, we MUST recompute state_hash because
    the per-record content changed. manifest_hash also recomputes (covers integrity
    fields).

Per extensions:
  - Legacy `aep:*` dict-form extensions are left as-is. v0.5.1's validator
    recognizes the dict-form as legacy metadata and skips semantic_stability
    enforcement on them. No re-shaping needed.

Provenance:
  - extensions.aep:deep_migrated_from: previous aep_version
  - extensions.aep:deep_migrated_at: timestamp
  - extensions.aep:deep_migration_tool: convert_v0_5_shallow_to_deep.py

Usage:
  python -m aep.convert_v0_5_shallow_to_deep <packet_root>
  python -m aep.convert_v0_5_shallow_to_deep --batch <corpus_root>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from aep.validate_v0_5 import (
    canonical_state_hash_v0_5,
    manifest_hash_v0_5,
)

# AEP project §02 → Axis-B mapping (operator-approved 2026-05-14)
RELIABILITY_TO_AXIS_B: Dict[str, str] = {
    "PROVEN_RELIABLE": "GO",
    "STRONGLY_PLAUSIBLE": "GO",
    "PLAUSIBLE": "EXPERIMENT",
    "EXPERIMENTAL": "EXPERIMENT",
    "ASSUMPTION": "EXPLORE",
    "SPECULATIVE_FRONTIER": "EXPLORE",
    "CONFLICTED": "HALT",
    "GOVERNANCE_RULE": "GO",
    "DANGEROUS_NOT_WORTH_DOING": "FORBIDDEN",
}
# UNKNOWN intentionally omitted — claims with UNKNOWN reliability stay without axis_b_action.

VALID_AXIS_B = {"GO", "EXPERIMENT", "EXPLORE", "HALT", "FORBIDDEN"}


def _read_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def _write_jsonl(path: Path, records: List[Dict]) -> None:
    lines = []
    for r in records:
        lines.append(
            json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    path.write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def deep_migrate_packet(packet_root: Path) -> Tuple[bool, List[str]]:
    """Deep-migrate a single shallow-v0.5 packet to deep-v0.5 in place."""
    changes: List[str] = []
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return False, [f"missing aepkg.json at {packet_root}"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    src_version = str(manifest.get("aep_version", "?"))
    if src_version != "0.5":
        return False, [
            f"deep migration applies only to shallow v0.5 packets; got aep_version={src_version!r}"
        ]

    # 1. Add packet_epoch to manifest (default = 1 for first deep-migration)
    if "packet_epoch" not in manifest:
        manifest["packet_epoch"] = 1
        changes.append("manifest.packet_epoch added (=1)")

    # 2. Per-claim field additions
    claims_path = packet_root / "data" / "claims.jsonl"
    claims_modified = False
    if claims_path.exists():
        claims = _read_jsonl(claims_path)
        for c in claims:
            reliability = c.get("reliability")
            if reliability is None:
                continue
            if "axis_b_action" not in c:
                axis_b = RELIABILITY_TO_AXIS_B.get(reliability)
                if axis_b is not None:
                    c["axis_b_action"] = axis_b
                    claims_modified = True
            # decision_time_revalidation_required: default False (operator opt-in)
            if "decision_time_revalidation_required" not in c:
                c["decision_time_revalidation_required"] = False
                claims_modified = True
            # go_justification_claim_ids: only for GO + GOVERNANCE_RULE
            if c.get("axis_b_action") == "GO" and c.get("reliability") == "GOVERNANCE_RULE":
                if "go_justification_claim_ids" not in c:
                    c["go_justification_claim_ids"] = []
                    claims_modified = True
        if claims_modified:
            _write_jsonl(claims_path, claims)
            changes.append(f"data/claims.jsonl: added v0.5 per-claim fields ({len(claims)} claims processed)")

    # 3. Provenance fields in extensions
    extensions = manifest.setdefault("extensions", {})
    if isinstance(extensions, dict):
        extensions["aep:deep_migrated_from"] = "0.5-shallow"
        migrated_at = (
            dt.datetime.now(tz=dt.timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        extensions["aep:deep_migrated_at"] = migrated_at
        extensions["aep:deep_migration_tool"] = "convert_v0_5_shallow_to_deep.py"
        # v0.5.4 structural receipt — pre-migration state_hash captured BEFORE state_hash
        # recomputation below (see step 4). post_state_hash is filled in after.
        # Full cryptographic verification is deferred to v0.7 signed identity per spec.
        pre_state_hash = manifest.get("integrity", {}).get("state_hash", "sha256:" + ("0" * 64))
        extensions["aep:deep_migration_receipt"] = {
            "pre_state_hash": pre_state_hash,
            # post_state_hash filled in below after canonical_state_hash_v0_5 recompute.
            "post_state_hash": "",
            "tool": "convert_v0_5_shallow_to_deep.py",
            "tool_version": "1.0",
            "timestamp": migrated_at,
        }
        changes.append("extensions: deep_migrated_from + deep_migrated_at + deep_migration_receipt recorded")

    # 4. Recompute integrity (state_hash + manifest_hash) since records changed.
    canonical_files = manifest.get("canonical_files", [])
    if canonical_files:
        new_state_hash = canonical_state_hash_v0_5(packet_root, canonical_files)
        manifest.setdefault("integrity", {})
        old_state = manifest["integrity"].get("state_hash", "")
        if old_state != new_state_hash:
            manifest["integrity"]["state_hash"] = new_state_hash
            changes.append(
                f"integrity.state_hash recomputed: {old_state[:24]}... -> {new_state_hash[:24]}..."
            )

    # 5b. Update the receipt's post_state_hash now that the new state_hash has been computed.
    if isinstance(extensions, dict) and "aep:deep_migration_receipt" in extensions:
        receipt = extensions["aep:deep_migration_receipt"]
        if isinstance(receipt, dict):
            receipt["post_state_hash"] = manifest["integrity"].get("state_hash", "")
            changes.append("deep_migration_receipt.post_state_hash populated")

    # manifest_hash recomputes over canonicalized manifest with integrity fields zeroed.
    new_manifest_hash = manifest_hash_v0_5(manifest)
    manifest["integrity"]["manifest_hash"] = new_manifest_hash
    changes.append(f"integrity.manifest_hash recomputed: {new_manifest_hash[:24]}...")

    # 5. Write manifest canonical-form.
    manifest_text = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        indent=2,
    )
    manifest_path.write_text(manifest_text + "\n", encoding="utf-8", newline="\n")
    changes.append("aepkg.json rewritten under v0.5 strict-canonical")

    return True, changes


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deep-migrate shallow-v0.5 packets to deep-v0.5 (adds per-record fields + recomputes integrity)."
    )
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("--batch", action="store_true", help="Treat packet_root as corpus root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    targets: List[Path] = []
    if args.batch:
        targets = sorted(p.parent for p in args.packet_root.rglob("aepkg.json"))
        if args.limit > 0:
            targets = targets[: args.limit]
        print(f"BATCH mode: {len(targets)} packets discovered")
    else:
        targets = [args.packet_root]

    ok, failed = 0, 0
    for pkt in targets:
        if args.dry_run:
            print(f"[DRY-RUN] would deep-migrate {pkt}")
            ok += 1
            continue
        success, changes = deep_migrate_packet(pkt)
        if success:
            ok += 1
            if not args.batch:
                for c in changes:
                    print(f"  • {c}")
                print(f"OK: {pkt}")
            else:
                print(f"OK\t{pkt}\t{len(changes)} changes")
        else:
            failed += 1
            print(f"FAIL\t{pkt}\t{'; '.join(changes)}", file=sys.stderr)
    print(f"\nSummary: ok={ok} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
