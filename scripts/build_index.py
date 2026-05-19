"""build_index.py — regenerate Singular-AEP-Dump-Files/INDEX.md from shard manifests.

Reads MANIFEST.jsonl + each shard's data/dump-entries.jsonl tail, writes a human-
readable inventory at INDEX.md. Idempotent.

Usage:
    python build_index.py --folder Singular-AEP-Dump-Files
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def read_jsonl(p: Path):
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def fmt_bytes(n):
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024 / 1024 / 1024:.2f} GB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, type=Path)
    args = ap.parse_args()

    folder = args.folder.resolve()
    manifest = read_jsonl(folder / "MANIFEST.jsonl")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    active = [r for r in manifest if r.get("shard_status") == "active"]
    sealed = [r for r in manifest if r.get("shard_status") == "sealed"]

    total_entries = sum(r.get("n_entries") or 0 for r in manifest)
    total_bytes = sum(r.get("total_bytes") or 0 for r in manifest)

    last_entries = []
    for r in manifest:
        shard_path = folder / r["aepkg_path"]
        entries = read_jsonl(shard_path / "data" / "dump-entries.jsonl")
        for e in entries[-10:]:
            last_entries.append((r["shard_id"], e))
    last_entries = sorted(last_entries, key=lambda x: x[1].get("deprecated_at", ""))[-10:]

    lines = []
    lines.append("# Singular AEP Dump — Shard Index")
    lines.append("")
    lines.append(f"**Auto-generated** by `projects/v11-aep/publish-ready/aep/scripts/build_index.py` after each cleanup cycle.")
    lines.append("")
    lines.append(f"**Last regenerated**: {now}")
    lines.append("")

    lines.append("## Active shard")
    lines.append("")
    if active:
        lines.append("| Shard | Sequence | Status | Entries | Size | Max | Created |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in active:
            lines.append(f"| `{r['aepkg_path']}` | {r['shard_sequence']} | active | {r.get('n_entries', 0)} | {fmt_bytes(r.get('total_bytes'))} | {fmt_bytes(r.get('shard_max_bytes'))} | {r.get('created_at', 'n/a')} |")
    else:
        lines.append("*(none — next archive cycle will create a new active shard)*")
    lines.append("")

    lines.append("## Sealed shards")
    lines.append("")
    if sealed:
        lines.append("| Shard | Sequence | Entries | Size | Sealed | Reason |")
        lines.append("|---|---|---|---|---|---|")
        for r in sealed:
            lines.append(f"| `{r['aepkg_path']}` | {r['shard_sequence']} | {r.get('n_entries', 0)} | {fmt_bytes(r.get('total_bytes'))} | {r.get('sealed_at', 'n/a')} | {r.get('sealed_reason', 'n/a')} |")
    else:
        lines.append("*(none yet)*")
    lines.append("")

    lines.append("## Total")
    lines.append("")
    lines.append(f"- **Shards**: {len(manifest)} ({len(active)} active, {len(sealed)} sealed)")
    lines.append(f"- **Entries**: {total_entries}")
    lines.append(f"- **Total dump size**: {fmt_bytes(total_bytes)}")
    lines.append("")

    lines.append("## Last 10 entries (across all shards)")
    lines.append("")
    if last_entries:
        lines.append("| Shard | Entry ID | Original Path | Size | Cluster | Deprecated At |")
        lines.append("|---|---|---|---|---|---|")
        for shard_id, e in last_entries:
            lines.append(f"| `{shard_id}` | `{e.get('id')}` | `{e.get('original_path')}` | {fmt_bytes(e.get('size_bytes'))} | {e.get('cluster_tag')} | {e.get('deprecated_at')} |")
    else:
        lines.append("*(no entries yet — scaffold pre-cycle)*")
    lines.append("")

    lines.append("## Searching the dump")
    lines.append("")
    lines.append("See parent `README.md` for the agent search protocol. Recommended:")
    lines.append("1. Read `MANIFEST.jsonl` for shard inventory.")
    lines.append("2. Each shard's `data/dump-entries.jsonl` is line-oriented (≈1KB per row).")
    lines.append("3. `first_text_4kb` field gives grep-without-restore access (gzip+b64).")
    lines.append("4. Full restore: `restore_from_dump.py --folder . --entry-id <id>`.")

    out = folder / "INDEX.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
