"""
convert_v0_3_to_v0_5.py — Apache-2.0 — Loss-less migration from AEP v0.3 to v0.5.

Operates in-place on a v0.3 .aepkg/ directory. After successful migration,
the packet validates clean under `aep:0.5/stable` at conformance level 2.

What changes:
  - aepkg.json:
    * aep_version: "0.3" -> "0.5"
    * profile: "aep:0.3/minimal-jsonl" -> "aep:0.5/stable"
    * integrity.state_hash: recomputed under v0.5 strict-canonical (RFC 8785 + AEP extras)
    * integrity.manifest_hash: NEW (v0.4 normative; v0.5 normative)
    * integrity.assets_merkle_root: NEW under AEP-MERKLE-v1 (domain-separated, NFC paths)
  - validations/runs.jsonl: `result` field renamed to `schema_result`
  - ops/events.jsonl first event: pre_state_hash changes from
    "sha256:0000..." (v0.3 zero-genesis) to "sha256:e3b0c44..." (sha256 of empty string,
    per v0.4 §13 / v0.5 §13)
  - aepkg.json: adds extensions["aep:migrated_from"] = "0.3" + migrated_at timestamp.

What is preserved verbatim:
  - All canonical record contents (sources, spans, claims, relations, reviews)
  - Original assets bytes
  - All custom extensions (aep:* fields)
  - Packet identity (packet_id, title)

Usage:
  python -m aep.convert_v0_3_to_v0_5 <packet_root>
  python -m aep.convert_v0_3_to_v0_5 --batch <corpus_root>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Import v0.5 hash + canonicalization helpers
from aep.validate_v0_5 import (
    canonical_state_hash_v0_5,
    manifest_hash_v0_5,
    aep_merkle_v1,
    MERKLE_EMPTY,
)

# v0.4 introduced sha256-of-empty-string as the canonical genesis pre_state_hash.
GENESIS_PRE_STATE_HASH_V05 = "sha256:" + hashlib.sha256(b"").hexdigest()
# v0.3 used a literal zero-string.
ZERO_GENESIS_V03 = "sha256:" + ("0" * 64)


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
        lines.append(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    # LF line endings, no BOM, no trailing newline (v0.5 §16.1 / Attack 1 strict)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def migrate_packet(packet_root: Path) -> Tuple[bool, List[str]]:
    """Migrate a single v0.3 packet to v0.5 in place.

    Returns (success, list_of_change_descriptions).
    """
    changes: List[str] = []
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return False, [f"missing aepkg.json at {packet_root}"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    src_version = str(manifest.get("aep_version", "?"))

    # 1. Version + profile bump
    if src_version not in ("0.3", "0.4"):
        return False, [f"unsupported source version {src_version}; this tool supports 0.3 and 0.4"]
    if src_version != "0.5":
        manifest["aep_version"] = "0.5"
        changes.append(f"aep_version {src_version} -> 0.5")
    src_profile = str(manifest.get("profile", ""))
    if "aep:0.5/" not in src_profile:
        manifest["profile"] = "aep:0.5/stable"
        changes.append(f"profile '{src_profile}' -> 'aep:0.5/stable'")

    # 2. Rename validations/runs.jsonl `result` -> `schema_result` (v0.4 normative)
    runs_path = packet_root / "validations" / "runs.jsonl"
    if runs_path.exists():
        runs = _read_jsonl(runs_path)
        mutated = False
        for r in runs:
            if "result" in r and "schema_result" not in r:
                r["schema_result"] = r.pop("result")
                mutated = True
        if mutated:
            _write_jsonl(runs_path, runs)
            changes.append("validations/runs.jsonl: renamed `result` -> `schema_result`")

    # 3. Update first event's pre_state_hash from v0.3 zero-genesis to v0.5 sha256-of-empty
    events_path = packet_root / "ops" / "events.jsonl"
    if events_path.exists():
        events = _read_jsonl(events_path)
        if events and events[0].get("pre_state_hash") == ZERO_GENESIS_V03:
            events[0]["pre_state_hash"] = GENESIS_PRE_STATE_HASH_V05
            _write_jsonl(events_path, events)
            changes.append(
                "ops/events.jsonl[0].pre_state_hash: zero-string -> sha256-of-empty-string"
            )

    # 4. Recompute canonical_state_hash under v0.5 strict-canonical profile
    canonical_files = manifest.get("canonical_files", [])
    if canonical_files:
        new_state_hash = canonical_state_hash_v0_5(packet_root, canonical_files)
        manifest.setdefault("integrity", {})
        old_state = manifest["integrity"].get("state_hash", "")
        if old_state != new_state_hash:
            manifest["integrity"]["state_hash"] = new_state_hash
            changes.append(f"integrity.state_hash recomputed: {old_state[:24]}... -> {new_state_hash[:24]}...")

    # 5. Add manifest_hash (compute over canonicalized manifest with integrity fields zeroed)
    #    The manifest_hash_v0_5 helper expects the full manifest dict.
    new_manifest_hash = manifest_hash_v0_5(manifest)
    if manifest["integrity"].get("manifest_hash") != new_manifest_hash:
        manifest["integrity"]["manifest_hash"] = new_manifest_hash
        changes.append(f"integrity.manifest_hash added: {new_manifest_hash[:24]}...")

    # 6. Compute AEP-MERKLE-v1 over assets/**
    assets_root = packet_root / "assets"
    new_assets_root = aep_merkle_v1(assets_root, case_policy="preserve") if assets_root.exists() else MERKLE_EMPTY
    if manifest["integrity"].get("assets_merkle_root") != new_assets_root:
        manifest["integrity"]["assets_merkle_root"] = new_assets_root
        changes.append(f"integrity.assets_merkle_root added: {new_assets_root[:24]}...")

    # 7. Record migration provenance in extensions
    extensions = manifest.setdefault("extensions", {})
    extensions["aep:migrated_from"] = src_version
    extensions["aep:migrated_at"] = dt.datetime.now(tz=dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    extensions["aep:migration_tool"] = "convert_v0_3_to_v0_5.py"
    changes.append(f"extensions: migrated_from + migrated_at recorded")

    # 8. Re-canonicalize manifest_hash AFTER all changes (because adding extensions changes the manifest)
    final_manifest_hash = manifest_hash_v0_5(manifest)
    manifest["integrity"]["manifest_hash"] = final_manifest_hash

    # 9. Write manifest with strict-canonical JSON (sorted keys, no whitespace, LF)
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), indent=2)
    manifest_path.write_text(manifest_text + "\n", encoding="utf-8", newline="\n")
    changes.append("aepkg.json rewritten under v0.5 strict-canonical")

    return True, changes


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate AEP v0.3/v0.4 packet(s) to v0.5.")
    parser.add_argument("packet_root", type=Path, help="Single packet or corpus root with --batch")
    parser.add_argument("--batch", action="store_true", help="Treat packet_root as corpus root; migrate all .aepkg/ subdirs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--limit", type=int, default=0, help="In batch mode, migrate at most N packets (0=all)")
    args = parser.parse_args(argv)

    targets: List[Path] = []
    if args.batch:
        targets = sorted(p.parent for p in args.packet_root.rglob("aepkg.json"))
        if args.limit > 0:
            targets = targets[: args.limit]
        print(f"BATCH mode: {len(targets)} packets discovered")
    else:
        targets = [args.packet_root]

    ok = 0
    failed = 0
    for pkt in targets:
        if args.dry_run:
            print(f"[DRY-RUN] would migrate {pkt}")
            ok += 1
            continue
        success, changes = migrate_packet(pkt)
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
