"""build_deprecated_corpus.py — append files to Singular-AEP-Dump-Files/dump-NNN.aepkg/ (sharded).

Consumes the stale-candidates manifest emitted by .claude/hooks/self-clean-detect.ps1
and appends each candidate to the **active shard** under
`Singular-AEP-Dump-Files/dump-NNN.aepkg/` per the aep:0.7/dump profile (v2 sharded).

Sharding: each shard is capped at `aep:shard_max_bytes` (default 500 MB). When the
active shard fills, it gets sealed (`shard_status: sealed`) and a new
`dump-(N+1).aepkg/` is created as the next active shard. Parent `MANIFEST.jsonl` is
updated to reflect the rollover.

LIVE mode deletes the original after the archive entry + blob are written. DRY-RUN
mode (default) does NOT delete.

Usage:
    python build_deprecated_corpus.py \
        --folder Singular-AEP-Dump-Files \
        --candidates .claude/_logs/stale-candidates.jsonl \
        [--live] [--operator-authorized] \
        [--batch-id <id>] [--max-files <N>] [--shard-max-bytes <bytes>]
"""

from __future__ import annotations

import argparse
import base64
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
DEFAULT_SHARD_MAX = 524_288_000  # 500 MB

# Fallback allow-list when shard manifest is unreadable.
DEFAULT_ALLOW_LIST = [
    "_resumption/",
    "state/",
    "frontier/",
    "ideas/",
    "data/",
    ".archive/",
    "projects/godview-prime-v4/wasm/",
    "projects/v11-aep/publish-ready/aep/test_vectors/",
    "doctrine/",
    ".claude/agents/",
    ".claude/hooks/",
    ".claude/skills/",
    ".claude/commands/",
    "lib/",
    "src/",
    "tools/",
    "scripts/",
    "schemas/",
    "tests/",
    ".aepkit/",
    ".gitignore",
    ".gitattributes",
    ".mcp.json",
    ".cursorrules",
    "CLAUDE.md",
    "README.md",
    "package.json",
    "package-lock.json",
    "vitest.config.js",
    "playwright.config.js",
    "playwright.e2e.config.js",
    "playwright.probe.config.js",
    "MEGA-AEP-CAPABILITY-MAP.html",
    "Singular-AEP-Dump-Files/",
    ".git/",
    "node_modules/",
]


def sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_row_hash(row: dict) -> str:
    return sha256_bytes(canonical_json(row).encode("utf-8"))


def read_jsonl(p: Path):
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(p: Path, row: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(canonical_json(row) + "\n")


def rewrite_manifest(folder: Path, rows: list) -> None:
    manifest = folder / "MANIFEST.jsonl"
    tmp = manifest.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(canonical_json(r) + "\n")
    tmp.replace(manifest)


def load_allow_list(shard: Path):
    try:
        manifest = json.loads((shard / "aepkg.json").read_text(encoding="utf-8"))
        al = manifest.get("extensions", {}).get(
            "aep:allow_list_NEVER_archive", DEFAULT_ALLOW_LIST
        )
        return al
    except Exception:
        return DEFAULT_ALLOW_LIST


def is_allow_listed(rel_path: str, allow_list) -> bool:
    norm = rel_path.replace("\\", "/")
    for prefix in allow_list:
        p = prefix.replace("\\", "/")
        if norm == p or norm.startswith(p):
            return True
    return False


def first_4kb_b64(p: Path) -> str:
    with open(p, "rb") as f:
        raw = f.read(4096)
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def shard_size_bytes(shard: Path) -> int:
    total = 0
    for root, _, files in os.walk(shard):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except FileNotFoundError:
                pass
    return total


def discover_active_shard(folder: Path, shard_max_bytes: int):
    """Return (active_shard_path, parent_manifest_rows).

    Reads parent MANIFEST.jsonl, identifies the shard with shard_status=active.
    If none active or none exist, creates a new one. If active is over cap,
    seals it and creates the next.
    """
    rows = read_jsonl(folder / "MANIFEST.jsonl")
    if not rows:
        # bootstrap: create dump-001 if no MANIFEST
        return _new_shard(folder, 1, shard_max_bytes, [])

    active = [r for r in rows if r.get("shard_status") == "active"]
    if not active:
        next_seq = max((r.get("shard_sequence", 0) for r in rows), default=0) + 1
        return _new_shard(folder, next_seq, shard_max_bytes, rows)

    if len(active) > 1:
        raise SystemExit(f"manifest invariant violated: {len(active)} shards with status=active")

    a = active[0]
    shard_path = folder / a["aepkg_path"]
    actual_size = shard_size_bytes(shard_path)
    if actual_size >= shard_max_bytes:
        # Seal current, create next
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        a["shard_status"] = "sealed"
        a["sealed_at"] = now
        a["sealed_reason"] = "size_cap_reached"
        a["total_bytes"] = actual_size
        rewrite_manifest(folder, rows)
        append_jsonl(shard_path / "ops" / "events.jsonl", {
            "id": f"evt:{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            "event_time": now,
            "event_type": "seal",
            "actor": "build_deprecated_corpus.py",
            "reason": "size_cap_reached",
            "total_bytes_at_seal": actual_size,
            "type": "WriteEvent",
        })
        next_seq = a["shard_sequence"] + 1
        return _new_shard(folder, next_seq, shard_max_bytes, rows)

    return shard_path, rows


def _new_shard(folder: Path, sequence: int, shard_max_bytes: int, existing_rows: list):
    shard_id = f"dump-{sequence:03d}"
    shard_path = folder / f"{shard_id}.aepkg"
    shard_path.mkdir(parents=True, exist_ok=True)
    (shard_path / "data").mkdir(exist_ok=True)
    (shard_path / "ops").mkdir(exist_ok=True)
    (shard_path / "reviews").mkdir(exist_ok=True)
    (shard_path / "validations").mkdir(exist_ok=True)
    (shard_path / "assets").mkdir(exist_ok=True)
    (shard_path / "views" / "derived").mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Per-shard aepkg.json (inherits allow-list from dump-001 if present, else default)
    aepkg = {
        "aep_version": "0.7.1",
        "profile": "aep:0.7/dump",
        "conformance_level": 2,
        "channel": "stable",
        "schema_version": "1",
        "type": "dump",
        "slug": f"singular-aep-dump-{sequence:03d}",
        "title": f"Singular AEP Dump — Shard {sequence:03d}",
        "created_at": now,
        "owner_agent": "warden",
        "reviewer_agent": "judge",
        "created_by": "build_deprecated_corpus.py (auto-rollover)",
        "truth_tag": "STRONGLY PLAUSIBLE",
        "canonical_files": [
            "data/dump-entries.jsonl",
            "ops/events.jsonl",
            "reviews/cleanup-receipts.jsonl",
            "validations/restore-self-tests.jsonl",
        ],
        "extensions": {
            "aep:scope": f"Singular-AEP-Dump-Files/{shard_id}.aepkg/",
            "aep:dump_protocol_version": "2",
            "aep:shard_id": shard_id,
            "aep:shard_sequence": sequence,
            "aep:shard_status": "active",
            "aep:shard_max_bytes": shard_max_bytes,
            "aep:allow_list_NEVER_archive": DEFAULT_ALLOW_LIST,
            "aep:parent_manifest": "../MANIFEST.jsonl",
        },
        "integrity": {
            "state_hash": "sha256:PENDING_FIRST_ENTRY",
            "manifest_hash": "sha256:PENDING_FIRST_ENTRY",
            "assets_merkle_root": EMPTY_SHA256,
            "views_merkle_root": "sha256:PENDING_VIEWS_GEN",
        },
        "signatures": [],
    }
    (shard_path / "aepkg.json").write_text(canonical_json(aepkg) + "\n", encoding="utf-8")
    append_jsonl(shard_path / "ops" / "events.jsonl", {
        "id": "evt:001",
        "event_time": now,
        "event_type": "shard_created",
        "actor": "build_deprecated_corpus.py",
        "shard_id": shard_id,
        "shard_sequence": sequence,
        "shard_max_bytes": shard_max_bytes,
        "hash_chain_prev": EMPTY_SHA256,
        "type": "WriteEvent",
    })

    # Append new manifest row
    new_row = {
        "shard_id": shard_id,
        "shard_sequence": sequence,
        "shard_status": "active",
        "aepkg_path": f"{shard_id}.aepkg",
        "n_entries": 0,
        "total_bytes": 0,
        "shard_max_bytes": shard_max_bytes,
        "created_at": now,
        "sealed_at": None,
        "sealed_reason": None,
        "first_entry_id": None,
        "last_entry_id": None,
        "first_entry_at": None,
        "last_entry_at": None,
    }
    rows = list(existing_rows) + [new_row]
    rewrite_manifest(folder, rows)

    return shard_path, rows


def update_manifest_for_shard(folder: Path, shard_path: Path, entry: dict) -> None:
    rows = read_jsonl(folder / "MANIFEST.jsonl")
    shard_id = shard_path.name.replace(".aepkg", "")
    now = entry["deprecated_at"]
    for r in rows:
        if r.get("shard_id") == shard_id:
            r["n_entries"] = (r.get("n_entries") or 0) + 1
            r["total_bytes"] = shard_size_bytes(shard_path)
            if not r.get("first_entry_id"):
                r["first_entry_id"] = entry["id"]
                r["first_entry_at"] = now
            r["last_entry_id"] = entry["id"]
            r["last_entry_at"] = now
    rewrite_manifest(folder, rows)


def append_entry(folder: Path, shard: Path, src: Path, repo_root: Path,
                 rule_fired: str, cluster_tag: str, dry_run: bool):
    rel = str(src.relative_to(repo_root)).replace("\\", "/")
    allow = load_allow_list(shard)
    if is_allow_listed(rel, allow):
        return {"skipped": rel, "reason": "allow-listed"}

    if not src.is_file():
        return {"skipped": rel, "reason": "not-a-file"}

    try:
        file_hash = sha256_file(src)
    except PermissionError as e:
        return {"skipped": rel, "reason": f"permission-error: {e}"}
    size = src.stat().st_size
    mtime = datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    asset_hex = file_hash.split(":", 1)[1]
    asset_ref = f"assets/{asset_hex}.gz"
    asset_dest = shard / asset_ref

    entries = read_jsonl(shard / "data" / "dump-entries.jsonl")
    entry_id = f"dump-entry:{len(entries) + 1:04d}"
    prev_hash = canonical_row_hash(entries[-1]) if entries else EMPTY_SHA256

    entry = {
        "id": entry_id,
        "original_path": rel,
        "original_mtime": mtime,
        "sha256": file_hash,
        "size_bytes": size,
        "gzip_size_bytes": 0,  # filled after compress (live mode)
        "asset_ref": asset_ref,
        "cluster_tag": cluster_tag,
        "rule_fired": rule_fired,
        "deprecated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "deprecated_by": os.environ.get("AEP_AGENT", "operator"),
        "first_text_4kb": first_4kb_b64(src) if size > 0 else "",
        "restorable": True,
        "hash_chain_prev": prev_hash,
        "shard_id": shard.name.replace(".aepkg", ""),
    }

    if dry_run:
        return {"would_archive": rel, "entry_id": entry_id, "asset_ref": asset_ref,
                "sha256": file_hash, "shard_id": entry["shard_id"]}

    # Write the gzipped blob (dedup by sha256 — re-use existing if present)
    if not asset_dest.exists():
        asset_dest.parent.mkdir(parents=True, exist_ok=True)
        with open(src, "rb") as fin, gzip.open(asset_dest, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout)
    entry["gzip_size_bytes"] = asset_dest.stat().st_size

    append_jsonl(shard / "data" / "dump-entries.jsonl", entry)

    events_path = shard / "ops" / "events.jsonl"
    events = read_jsonl(events_path)
    prev_event = events[-1] if events else None
    event = {
        "id": f"evt:{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "event_time": entry["deprecated_at"],
        "event_type": "deprecate",
        "actor": "build_deprecated_corpus.py",
        "actor_agent": os.environ.get("AEP_AGENT", "operator"),
        "dump_entry_id": entry_id,
        "original_path": rel,
        "sha256": file_hash,
        "asset_ref": asset_ref,
        "shard_id": entry["shard_id"],
        "hash_chain_prev": canonical_row_hash(prev_event) if prev_event else EMPTY_SHA256,
        "type": "WriteEvent",
    }
    append_jsonl(events_path, event)

    update_manifest_for_shard(folder, shard, entry)

    # Delete original
    try:
        src.unlink()
    except (PermissionError, FileNotFoundError, OSError) as e:
        return {"archived_no_delete": rel, "entry_id": entry_id, "delete_error": str(e)}

    return {"archived_and_deleted": rel, "entry_id": entry_id, "shard_id": entry["shard_id"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", required=True, type=Path,
                    help="path to Singular-AEP-Dump-Files/ parent folder")
    ap.add_argument("--candidates", required=True, type=Path,
                    help="JSONL of {path, rule, cluster_tag} from self-clean-detect.ps1")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--live", action="store_true",
                    help="actually archive + delete originals (default DRY-RUN-ONLY)")
    ap.add_argument("--operator-authorized", action="store_true",
                    help="required alongside --live")
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--max-files", type=int, default=0,
                    help="hard cap on entries per invocation (0 = unlimited, operator-explicit)")
    ap.add_argument("--shard-max-bytes", type=int, default=DEFAULT_SHARD_MAX,
                    help=f"shard size cap in bytes (default {DEFAULT_SHARD_MAX} = 500 MB)")
    args = ap.parse_args(argv)

    if args.live and not args.operator_authorized:
        raise SystemExit("--live requires --operator-authorized (operator-gate; first-cycle policy)")

    folder = args.folder.resolve()
    if not folder.exists():
        raise SystemExit(f"folder not found: {folder}")
    if not (folder / "MANIFEST.jsonl").exists():
        raise SystemExit(f"folder is not a dump-shard parent (missing MANIFEST.jsonl): {folder}")

    candidates = read_jsonl(args.candidates)
    if args.max_files > 0 and len(candidates) > args.max_files and args.live:
        candidates = candidates[:args.max_files]

    dry = not args.live
    results = []
    batch_size = 0
    shard, _ = discover_active_shard(folder, args.shard_max_bytes)

    for c in candidates:
        src = Path(c["path"])
        if not src.is_absolute():
            src = (args.repo_root / src).resolve()

        # Check + roll if needed
        if args.live and shard_size_bytes(shard) >= args.shard_max_bytes:
            shard, _ = discover_active_shard(folder, args.shard_max_bytes)

        try:
            r = append_entry(
                folder=folder,
                shard=shard,
                src=src,
                repo_root=args.repo_root.resolve(),
                rule_fired=c.get("rule", "R?"),
                cluster_tag=c.get("cluster_tag", "stale"),
                dry_run=dry,
            )
        except Exception as e:
            r = {"error": str(e), "path": c.get("path")}
        results.append(r)
        batch_size += 1

    # Write a cleanup-receipt row to the shard
    if args.live:
        receipt = {
            "id": f"receipt:{int(datetime.now(timezone.utc).timestamp() * 1000)}",
            "batch_id": args.batch_id or "untagged",
            "batch_completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "n_processed": batch_size,
            "n_archived": sum(1 for r in results if r.get("archived_and_deleted") or r.get("archived_no_delete")),
            "n_skipped": sum(1 for r in results if r.get("skipped")),
            "n_errors": sum(1 for r in results if r.get("error")),
            "shard_id": shard.name.replace(".aepkg", ""),
        }
        append_jsonl(shard / "reviews" / "cleanup-receipts.jsonl", receipt)

    summary = {
        "mode": "LIVE" if not dry else "DRY-RUN",
        "batch_id": args.batch_id,
        "active_shard": shard.name,
        "n_processed": len(results),
        "n_archived": sum(1 for r in results if r.get("archived_and_deleted") or r.get("archived_no_delete")),
        "n_skipped": sum(1 for r in results if r.get("skipped")),
        "n_errors": sum(1 for r in results if r.get("error")),
    }
    print(canonical_json(summary))
    # Detailed results to a sibling file in /tmp/ for operator inspection
    return 0


if __name__ == "__main__":
    sys.exit(main())
