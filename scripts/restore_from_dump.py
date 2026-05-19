"""restore_from_dump.py — un-deprecate a file from a Singular-AEP-Dump shard.

Reversibility invariant: for any dump-entry E archived from path P with hash H,
running `restore_from_dump.py --folder Singular-AEP-Dump-Files --entry-id E
--to /tmp/restore-target` produces a file whose sha256 equals H.

Cross-shard: by default, --folder points to the parent Singular-AEP-Dump-Files/;
the script auto-discovers shards via MANIFEST.jsonl. --packet still supported for
single-shard mode (back-compat).

Closes adversary KR-3 finding H4 (must-close blocker #3 before LIVE self-clean).

Usage:
    python restore_from_dump.py --folder Singular-AEP-Dump-Files \
        (--entry-id dump-entry:NNNN | --sha256 sha256:<64hex>) \
        [--to <override-path>] [--force] [--dry-run]

Self-test invocation:
    python restore_from_dump.py --folder Singular-AEP-Dump-Files --self-test
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


EMPTY_SHA256 = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_row_hash(row: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()


def read_jsonl(p: Path):
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def discover_shards(folder_or_packet: Path):
    """Yield (shard_path, manifest_row | None) tuples.

    If folder_or_packet contains MANIFEST.jsonl, treat as parent folder + discover all shards.
    Otherwise treat as a single shard (back-compat).
    """
    manifest = folder_or_packet / "MANIFEST.jsonl"
    if manifest.exists():
        for row in read_jsonl(manifest):
            yield folder_or_packet / row["aepkg_path"], row
    elif (folder_or_packet / "aepkg.json").exists():
        yield folder_or_packet, None


def append_event(shard: Path, event: dict) -> None:
    events_path = shard / "ops" / "events.jsonl"
    events = read_jsonl(events_path)
    prev = events[-1] if events else None
    event["hash_chain_prev"] = canonical_row_hash(prev) if prev else EMPTY_SHA256
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(canonical_json(event) + "\n")


def find_entry_across_shards(folder_or_packet: Path, entry_id: Optional[str], sha256: Optional[str]):
    for shard, _row in discover_shards(folder_or_packet):
        entries = read_jsonl(shard / "data" / "dump-entries.jsonl")
        for e in entries:
            if entry_id and e.get("id") == entry_id:
                return shard, e
            if sha256 and e.get("sha256") == sha256:
                return shard, e
    raise SystemExit(f"no entry found matching entry_id={entry_id} sha256={sha256}")


def restore_one(shard: Path, entry: dict, to_path: Path, force: bool, dry_run: bool) -> dict:
    asset_path = shard / entry["asset_ref"]
    if not asset_path.exists():
        raise SystemExit(f"asset missing: {asset_path}")

    if to_path.exists() and not force:
        existing_mtime = datetime.fromtimestamp(to_path.stat().st_mtime, tz=timezone.utc)
        archive_mtime = datetime.fromisoformat(entry["original_mtime"].replace("Z", "+00:00"))
        if existing_mtime > archive_mtime:
            raise SystemExit(
                f"target {to_path} is newer ({existing_mtime}) than archive ({archive_mtime}); "
                f"pass --force to overwrite"
            )

    if dry_run:
        return {
            "would_write_to": str(to_path),
            "would_extract_from": str(asset_path),
            "would_match_sha256": entry["sha256"],
            "shard": shard.name,
        }

    to_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(asset_path, "rb") as fin, open(to_path, "wb") as fout:
        shutil.copyfileobj(fin, fout)

    restored_hash = sha256_file(to_path)
    if restored_hash != entry["sha256"]:
        raise SystemExit(
            f"INTEGRITY VIOLATION: restored {to_path} hash {restored_hash} != claimed {entry['sha256']}"
        )

    append_event(
        shard,
        {
            "id": f"evt:{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            "event_time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_type": "un-deprecate",
            "actor": "restore_from_dump.py",
            "actor_agent": os.environ.get("AEP_AGENT", "operator"),
            "dump_entry_id": entry["id"],
            "restored_to_path": str(to_path),
            "shard_id": shard.name.replace(".aepkg", ""),
            "type": "WriteEvent",
        },
    )
    return {
        "wrote_to": str(to_path),
        "verified_sha256": restored_hash,
        "entry_id": entry["id"],
        "shard": shard.name,
    }


def self_test(folder_or_packet: Path) -> int:
    """Round-trip the first entry of each shard through extract → hash-verify → discard."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    fails = 0
    total = 0
    n_shards = 0

    for shard, _row in discover_shards(folder_or_packet):
        n_shards += 1
        entries = read_jsonl(shard / "data" / "dump-entries.jsonl")
        validations_path = shard / "validations" / "restore-self-tests.jsonl"
        validations_path.parent.mkdir(parents=True, exist_ok=True)

        if not entries:
            with open(validations_path, "a", encoding="utf-8") as f:
                f.write(canonical_json({
                    "self_test_at": now,
                    "result": "PASS-VACUOUS",
                    "n_entries": 0,
                    "shard": shard.name,
                }) + "\n")
            continue

        shard_fails = 0
        for e in entries:
            total += 1
            asset_path = shard / e["asset_ref"]
            if not asset_path.exists():
                fails += 1
                shard_fails += 1
                continue
            try:
                with gzip.open(asset_path, "rb") as fin:
                    data = fin.read()
                h = "sha256:" + hashlib.sha256(data).hexdigest()
                if h != e["sha256"]:
                    fails += 1
                    shard_fails += 1
            except (OSError, gzip.BadGzipFile):
                fails += 1
                shard_fails += 1

        result = "PASS" if shard_fails == 0 else f"FAIL ({shard_fails} mismatched)"
        with open(validations_path, "a", encoding="utf-8") as f:
            f.write(canonical_json({
                "self_test_at": now,
                "result": result,
                "n_entries": len(entries),
                "n_failed": shard_fails,
                "shard": shard.name,
            }) + "\n")

    if total == 0:
        print(f"self-test PASS (vacuous — {n_shards} shards, 0 entries)")
        return 0
    print(f"self-test {'PASS' if fails == 0 else 'FAIL'} ({total - fails}/{total} entries verified across {n_shards} shards)")
    return 0 if fails == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--folder", type=Path, help="parent Singular-AEP-Dump-Files/ folder (auto-discovers shards)")
    g.add_argument("--packet", type=Path, help="single .aepkg/ directory (back-compat)")
    ap.add_argument("--entry-id", help="dump-entry:NNNN")
    ap.add_argument("--sha256", help="sha256:<64hex>")
    ap.add_argument("--to", type=Path, help="override restore target path")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    target = (args.folder or args.packet).resolve()
    if not target.exists():
        raise SystemExit(f"target not found: {target}")

    if args.self_test:
        return self_test(target)

    if not (args.entry_id or args.sha256):
        ap.error("--entry-id or --sha256 required")

    shard, entry = find_entry_across_shards(target, args.entry_id, args.sha256)
    to_path = args.to if args.to else Path(entry["original_path"]).resolve()
    result = restore_one(shard, entry, to_path, force=args.force, dry_run=args.dry_run)
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
