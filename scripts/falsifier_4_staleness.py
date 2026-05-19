"""falsifier_4_staleness.py — Index-vs-canonical-source drift gate.

Per judge's KR-4 falsifier-4 addition: every session-start should warn if
stale_pct > 0.02 and HALT if > 0.05. An index that fell behind canonical
content is worse than no index — it gaslights agents into citing dead claims.

Methodology:
  For each row in the semantic index, the row carries text_sha256 of the
  text that was indexed. Re-walk the canonical source (the same source the
  build script extracted from), find the SAME claim, re-compute sha256, and
  compare.

  Match: row's text_sha256 == current text_sha256 → fresh
  Mismatch: text content changed since indexing → stale
  Missing: source claim no longer exists → stale (counts as drift)

Usage:
    python falsifier_4_staleness.py \
        --index projects/v11-aep/publish-ready/aep/embeddings/v1 \
        [--repo-root .] \
        [--halt-threshold 0.05] \
        [--warn-threshold 0.02]
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple


def blake2b256_str(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=32).hexdigest()


def safe_read_jsonl(p: Path):
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def extract_dump_entry_text(entry: Dict) -> str:
    b64 = entry.get("first_text_4kb")
    if not b64:
        return ""
    try:
        raw = base64.b64decode(b64)
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
        return text
    except (OSError, ValueError):
        return ""


def find_canonical_text(row: Dict, repo_root: Path) -> Optional[str]:
    """Given an index row, locate the current canonical text for that vec_id.

    For aepkg::<dirname>::<claim_id> rows: find data/claims.jsonl, lookup id, return text.
    For dump-entry::<id>::<shard>: find data/dump-entries.jsonl, lookup id, decode first_text_4kb.
    """
    vec_id = row.get("vec_id", "")
    source_path = row.get("source_path", "")
    if not source_path:
        return None

    if vec_id.startswith("aepkg::"):
        parts = vec_id.split("::")
        if len(parts) < 3:
            return None
        claim_id = parts[2]
        # source_path may be the .aepkg dir directly OR a path within it
        candidate_dirs = []
        sp_path = (repo_root / source_path).resolve()
        # If source_path is already an .aepkg or contains one, walk up to find it
        if sp_path.suffix == ".aepkg" or sp_path.name.endswith(".aepkg"):
            candidate_dirs.append(sp_path)
        else:
            # search parents for *.aepkg
            cur = sp_path
            while cur != cur.parent:
                if cur.suffix == ".aepkg":
                    candidate_dirs.append(cur)
                    break
                cur = cur.parent
            if not candidate_dirs:
                # try finding by aepkg name in row's source_path string
                for part in source_path.replace("\\", "/").split("/"):
                    if part.endswith(".aepkg"):
                        candidate_dirs.append(repo_root / part)
                        break
        for cdir in candidate_dirs:
            claims_path = cdir / "data" / "claims.jsonl"
            if claims_path.exists():
                for c in safe_read_jsonl(claims_path):
                    if c.get("id") == claim_id:
                        return c.get("text") or c.get("claim_text") or ""
        return None

    if vec_id.startswith("dump-entry::"):
        parts = vec_id.split("::")
        if len(parts) < 3:
            return None
        entry_id = parts[1]
        shard_name = parts[2]
        shard_path = repo_root / "Singular-AEP-Dump-Files" / shard_name
        entries_path = shard_path / "data" / "dump-entries.jsonl"
        if not entries_path.exists():
            return None
        for e in safe_read_jsonl(entries_path):
            if e.get("id") == entry_id:
                return extract_dump_entry_text(e)
        return None

    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings/v1"))
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--halt-threshold", type=float, default=0.05)
    ap.add_argument("--warn-threshold", type=float, default=0.02)
    ap.add_argument("--sample-size", type=int, default=0,
                    help="0 = check all rows; >0 = stratified sample (deterministic)")
    args = ap.parse_args(argv)

    repo_root = args.repo_root.resolve()
    rows_path = args.index / "index.jsonl"
    if not rows_path.exists():
        raise SystemExit(f"index not found: {rows_path}")

    rows = []
    with open(rows_path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    if args.sample_size > 0 and args.sample_size < len(rows):
        # deterministic stride sampling
        stride = len(rows) // args.sample_size
        rows = rows[::stride][:args.sample_size]

    n_total = len(rows)
    n_fresh = 0
    n_stale = 0
    n_missing = 0
    stale_examples = []

    for r in rows:
        try:
            current_text = find_canonical_text(r, repo_root)
        except Exception:
            current_text = None

        if current_text is None:
            n_missing += 1
            if len(stale_examples) < 5:
                stale_examples.append({"vec_id": r["vec_id"], "reason": "source_not_found",
                                       "indexed_sha": r.get("text_sha256", "?")})
            continue

        current_sha = "blake2b-256:" + blake2b256_str(current_text)
        indexed_sha = r.get("text_sha256", "")
        if current_sha == indexed_sha:
            n_fresh += 1
        else:
            n_stale += 1
            if len(stale_examples) < 5:
                stale_examples.append({"vec_id": r["vec_id"], "reason": "content_changed",
                                       "indexed_sha": indexed_sha[:32],
                                       "current_sha": current_sha[:32]})

    n_drift = n_stale + n_missing
    drift_pct = n_drift / n_total if n_total else 0.0

    if drift_pct >= args.halt_threshold:
        verdict = "HALT"
    elif drift_pct >= args.warn_threshold:
        verdict = "WARN"
    else:
        verdict = "PASS"

    summary = {
        "falsifier": "F4-index-staleness-drift",
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "n_total_rows": n_total,
        "n_fresh": n_fresh,
        "n_stale_content_changed": n_stale,
        "n_missing_source": n_missing,
        "n_drift_total": n_drift,
        "drift_pct": round(drift_pct, 4),
        "warn_threshold": args.warn_threshold,
        "halt_threshold": args.halt_threshold,
        "verdict": verdict,
        "stale_examples": stale_examples,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if verdict != "HALT" else 1


if __name__ == "__main__":
    sys.exit(main())
