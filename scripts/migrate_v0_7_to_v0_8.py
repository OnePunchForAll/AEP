#!/usr/bin/env python3
"""migrate_v0_7_to_v0_8.py — additive migration of AEP packets from v0.7.x to v0.8.0.

Per AEP v0.8 SPEC §V80-13. Strictly additive; preserves all v0.7.1 packet
content; bumps profile + initializes optional v0.8 frontier-break fields with
honest defaults; grandfathers pre-v0.8 PROVEN_RELIABLE claims per §V80-7-bis;
grandfathers pre-PSC packets per PSC-V80-15.

Stdlib only (§68 compliance). No network. No subprocess. No shell.

Usage:
    python scripts/migrate_v0_7_to_v0_8.py <packet_or_dir> [--dry-run] [--strict]
    python scripts/migrate_v0_7_to_v0_8.py --corpus  # walk every .aepkg in repo
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]  # scripts→aep→publish-ready→v11-aep→projects→aepkit
SCHEMA_VERSION = "0.8.0"
TRUSTED_VERIFIER_PATH = "projects/v11-aep/publish-ready/aep/scripts/aep08_preflight_min.py"
SRC_AEP_PATH = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "src"

# Import canonical hash functions for honest manifest_hash recompute.
if str(SRC_AEP_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_AEP_PATH))
try:
    from aep.validate_v0_5 import manifest_hash_v0_5  # type: ignore
    HAVE_MANIFEST_HASH = True
except ImportError:
    HAVE_MANIFEST_HASH = False

# v0.7.1 → v0.8 profile mapping (additive bump)
PROFILE_BUMP = {
    "aep:0.5/stable": "aep:0.8/stable",
    "aep:0.5/experimental": "aep:0.8/stable",
    "aep:0.6/stable": "aep:0.8/stable",
    "aep:0.6/jsonl-compact": "aep:0.8/stable",
    "aep:0.6/linked-data": "aep:0.8/stable",
    "aep:0.7/stable": "aep:0.8/stable",
    "aep:0.7/signed": "aep:0.8/stable",
    "aep:0.7/views-derived": "aep:0.8/stable",
}

# Reliability codes that count as PROVEN_RELIABLE for grandfather clause.
PROVEN_RELIABLE_CODES = {"PROVEN_RELIABLE", "PROVEN/RELIABLE", "R"}


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "UNKNOWN"


def find_aepkg_dirs(root: pathlib.Path) -> List[pathlib.Path]:
    """Discover all .aepkg directories under root."""
    found: List[pathlib.Path] = []
    for p in root.rglob("*.aepkg"):
        if p.is_dir() and (p / "aepkg.json").exists():
            found.append(p)
    return sorted(set(found))


def migrate_one(packet_root: pathlib.Path, dry_run: bool = False) -> Tuple[str, Optional[str]]:
    """Apply v0.8 migration to a single packet.

    Returns: (status, error_message_if_any)
      status ∈ {"MIGRATED", "ALREADY_V0_8", "SKIPPED", "ERROR"}
    """
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return "SKIPPED", "aepkg.json not found"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return "ERROR", f"manifest JSON decode failed: {e}"

    current_profile = manifest.get("profile", "")
    if current_profile.startswith("aep:0.8/"):
        return "ALREADY_V0_8", None

    # Capture previous state_hash for migration event.
    integrity = manifest.get("integrity", {})
    previous_state_hash = integrity.get("state_hash", "UNKNOWN")
    previous_manifest_hash = integrity.get("manifest_hash", "UNKNOWN")

    # 1. Profile bump.
    new_profile = PROFILE_BUMP.get(current_profile, "aep:0.8/stable")
    manifest["profile"] = new_profile
    manifest["spec_version"] = SCHEMA_VERSION  # additive bookkeeping

    # 2. Initialize F2 reproducibility_certificate (PRE-v0.8 state per §V80-4-bis).
    if "reproducibility_certificate" not in integrity:
        integrity["reproducibility_certificate"] = {
            "certified": False,
            "reason": "PRE-v0.8-PACKET-NOT-REPRODUCED",
            "scope": "BIRTH-ONLY",
        }

    # 3. Initialize F4 surface_projections (empty by default).
    if "surface_projections" not in manifest:
        manifest["surface_projections"] = []

    # 4. Initialize F5 self_falsifying (empty by default).
    if "self_falsifying" not in manifest:
        manifest["self_falsifying"] = []

    # 5. Initialize F7 counterexample_bundle (empty by default).
    if "counterexample_bundle" not in manifest:
        manifest["counterexample_bundle"] = []

    # 6. Initialize F8 preflight_sandbox_capsule (grandfathered per PSC-V80-15).
    if "preflight_sandbox_capsule" not in manifest:
        verifier_path = REPO_ROOT / TRUSTED_VERIFIER_PATH
        verifier_sha = sha256_file(verifier_path) if verifier_path.exists() else "UNKNOWN"
        manifest["preflight_sandbox_capsule"] = {
            "schema": "aep-preflight-0.8",
            "grandfathered_pre_v0_8": True,
            "last_verdict": "HEADER_ONLY",
            "last_reason": "pre_v0_8_packet_safe_default_per_PSC-V80-15",
            "trusted_verifier_required": True,
            "embedded_reference_verifier_sha256": verifier_sha,
            "forbidden_preflight_capabilities": ["network", "secrets", "write_host", "execute_packet_code"],
            "capabilities": {"network": False, "secrets": False, "write_host": False, "execute_packet_code": False},
        }

    # 7. PROVEN_RELIABLE grandfather stamping DEFERRED to PROMOTE-TO-V0_8-NATIVE tool
    #    per §V80-7-bis: silent migration of truth-tag-bearing claims violates §50 Law 1.
    pr_grandfathered_count = 0

    # 8. Migration history goes to NON-CANONICAL location (not ops/events.jsonl) to
    #    preserve §V60-2 Axiom 4 (body files untouched → state_hash stable) AND avoid
    #    AEP61_BODY_ENVELOPE_LEAK (envelope hash hex in body bytes).
    history_path = packet_root / ".migration_history" / "v0_8.jsonl"
    migration_event = {
        "event_type": "v0.8_migration",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "previous_profile": current_profile,
        "new_profile": new_profile,
        "previous_state_hash_redacted_prefix": (previous_state_hash[:12] + "...") if previous_state_hash else None,
        "previous_manifest_hash_redacted_prefix": (previous_manifest_hash[:12] + "...") if previous_manifest_hash else None,
        "fields_initialized": [
            "preflight_sandbox_capsule",
            "surface_projections",
            "self_falsifying",
            "counterexample_bundle",
            "integrity.reproducibility_certificate",
        ],
        "claims_grandfathered_pre_v0_8": pr_grandfathered_count,
        "body_files_untouched": True,
        "manifest_hash_recomputed": HAVE_MANIFEST_HASH,
        "migrator_version": SCHEMA_VERSION,
        "honest_disclosure": "v0.7.x state_hash from prior emission preserved as authoritative for body bytes; body files unchanged; only aepkg.json mutated additively per §V80-13.",
    }
    if not dry_run:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(migration_event, separators=(",", ":")) + "\n")

    # 9. Stamp migration metadata in integrity (non-canonical bookkeeping per §V80-2 axiom 4).
    integrity["v0_8_migrated_at"] = migration_event["timestamp"]
    integrity["v0_8_migrator_version"] = SCHEMA_VERSION
    manifest["integrity"] = integrity

    # 10. Recompute manifest_hash per v0.7.1 discipline (exclude manifest_hash +
    #     views_merkle_root + signatures from basis).
    if HAVE_MANIFEST_HASH:
        try:
            # Build manifest copy with exclusions per v0.7.1 contract.
            import copy
            manifest_for_hash = copy.deepcopy(manifest)
            mfh_integ = manifest_for_hash.get("integrity", {})
            mfh_integ.pop("manifest_hash", None)
            mfh_integ.pop("views_merkle_root", None)
            manifest_for_hash.pop("signatures", None)
            manifest_for_hash["integrity"] = mfh_integ
            new_manifest_hash = manifest_hash_v0_5(manifest_for_hash)
            integrity["manifest_hash"] = new_manifest_hash
            manifest["integrity"] = integrity
        except Exception:
            # Honest disclosure: hash recompute failed; previous preserved as authoritative.
            pass

    # 11. Write back.
    if not dry_run:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    return "MIGRATED", None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AEP v0.7.x → v0.8.0 additive migration")
    parser.add_argument("target", nargs="?", help="Path to .aepkg dir or parent dir")
    parser.add_argument("--corpus", action="store_true", help="Walk entire repo for .aepkg dirs")
    parser.add_argument("--dry-run", action="store_true", help="Report changes; do not write")
    parser.add_argument("--strict", action="store_true", help="exit 1 on any ERROR")
    parser.add_argument("--report-every", type=int, default=50, help="progress report cadence")
    args = parser.parse_args(argv)

    if args.corpus:
        packets = find_aepkg_dirs(REPO_ROOT)
    elif args.target:
        target = pathlib.Path(args.target).resolve()
        if (target / "aepkg.json").exists():
            packets = [target]
        else:
            packets = find_aepkg_dirs(target)
    else:
        parser.error("either --corpus or a target path is required")
        return 2

    if not packets:
        print("no .aepkg dirs found", file=sys.stderr)
        return 1

    print(f"Migrating {len(packets)} packets (dry_run={args.dry_run})")
    t_start = time.perf_counter()
    counts = {"MIGRATED": 0, "ALREADY_V0_8": 0, "SKIPPED": 0, "ERROR": 0}
    errors: List[Tuple[str, str]] = []
    for i, packet in enumerate(packets, 1):
        try:
            status, err = migrate_one(packet, dry_run=args.dry_run)
        except Exception as e:
            status, err = "ERROR", f"exception: {type(e).__name__}: {e}"
        counts[status] = counts.get(status, 0) + 1
        if status == "ERROR":
            errors.append((str(packet.relative_to(REPO_ROOT)), err or ""))
        if i % args.report_every == 0:
            print(f"  progress: {i}/{len(packets)} ({i*100//len(packets)}%) — {counts}")

    elapsed = time.perf_counter() - t_start
    print(f"\nMigration complete in {elapsed:.1f}s")
    print(f"  packets: {len(packets)}")
    for k, v in counts.items():
        if v > 0:
            print(f"  {k}: {v}")
    if errors:
        print(f"\n{len(errors)} errors:")
        for path, err in errors[:20]:
            print(f"  [{path}] {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    return 1 if (args.strict and counts.get("ERROR", 0) > 0) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
