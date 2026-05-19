"""aep_search.py — TF-IDF cosine search over the AEP semantic index.

Loads index.jsonl + vocabulary.jsonl produced by build_semantic_index.py and
returns top-K cosine matches for a free-form query.

Usage:
    python aep_search.py "<query>" \
        [--index projects/v11-aep/publish-ready/aep/embeddings/v1] \
        [--scope all|dump-entry|claim] \
        [--top-k 10] [--min-cos 0.0] \
        [--reliability PROVEN_RELIABLE,STRONGLY_PLAUSIBLE,...] \
        [--show-contradictions] \
        [--format human|jsonl]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


STOPWORDS_RAW = """
a an the of and or but not for to in on at by from with as is are was were be been being have has had
do does did this that these those it its their there here we us our you your they them he she his her him
will would should could may might must can shall about above after again against all am any aren't because
been before below between both can't cannot couldn't did didn't doesn't doing don't down during each
few further haven't hasn't hadn't her here's hers herself himself his how i'd i'll i'm i've if into
let's me more most mustn't my myself nor of off on once only other ought our ours ourselves out over own
same shan't she'd she'll she's so some such than that's then theirs themselves there's they'd they'll
they're they've through too under until up very wasn't we'd we'll we're we've weren't what what's
when when's where where's which while who who's whom why why's won't wouldn't yours yourself yourselves
"""
STOPWORDS = frozenset(w for w in STOPWORDS_RAW.split() if w)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_]{2,}")


def tokenize(text: str) -> List[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def load_index(index_dir: Path):
    """Return (vocab_idx: {term: int}, idf_arr: {int: float}, rows: list of dict)."""
    vocab_idx = {}
    idf_arr = {}
    with open(index_dir / "vocabulary.jsonl", "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            vocab_idx[row["term"]] = i
            idf_arr[i] = row["idf"]
    rows = []
    with open(index_dir / "index.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return vocab_idx, idf_arr, rows


def vectorize_query(query: str, vocab_idx, idf_arr):
    toks = tokenize(query)
    tc = Counter(toks)
    vec = {}
    for t, c in tc.items():
        if t not in vocab_idx:
            continue
        idx = vocab_idx[t]
        tf = 1.0 + math.log(c)
        vec[idx] = tf * idf_arr[idx]
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def cosine_sparse(a: Dict[int, float], b_sparse_list: List[Dict[str, Any]]) -> float:
    s = 0.0
    for tw in b_sparse_list:
        t = tw["t"]
        if t in a:
            s += a[t] * tw["w"]
    return s


def load_contradictions(path: Path):
    if not path.exists():
        return {}
    by_vec = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            for vid in (row.get("a", {}).get("vec_id"), row.get("b", {}).get("vec_id")):
                if vid:
                    by_vec.setdefault(vid, []).append(row)
    return by_vec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("--index", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings/v1"))
    ap.add_argument("--scope", default="all",
                    help="all|dump-entry|claim|<source_kind>")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--min-cos", type=float, default=0.0)
    ap.add_argument("--reliability", default=None,
                    help="comma-separated list, e.g. PROVEN_RELIABLE,STRONGLY_PLAUSIBLE")
    ap.add_argument("--show-contradictions", action="store_true")
    ap.add_argument("--contradictions-path", type=Path,
                    default=Path(".claude/_logs/contradiction-candidates.jsonl"))
    ap.add_argument("--format", choices=["human", "jsonl"], default="human")
    args = ap.parse_args(argv)

    t0 = time.time()
    vocab_idx, idf_arr, rows = load_index(args.index)

    relset = None
    if args.reliability:
        relset = set(r.strip().upper() for r in args.reliability.split(","))

    qvec = vectorize_query(args.query, vocab_idx, idf_arr)
    if not qvec:
        print(canonical("empty query vector (no in-vocabulary tokens)", args.format))
        return 0

    # Optional: build inverted index for the query vector to skip full N scan
    # For ≤20k rows this is fast enough without it
    scored = []
    for r in rows:
        if args.scope != "all" and r.get("source_kind") != args.scope:
            continue
        if relset and r.get("reliability") not in relset:
            continue
        cos = cosine_sparse(qvec, r.get("sparse_vec", []))
        if cos < args.min_cos:
            continue
        scored.append((cos, r))

    scored.sort(key=lambda kv: -kv[0])
    hits = scored[:args.top_k]
    elapsed_ms = round((time.time() - t0) * 1000)

    contradictions_by_vec = (
        load_contradictions(args.contradictions_path)
        if args.show_contradictions else {}
    )

    if args.format == "jsonl":
        for rank, (cos, r) in enumerate(hits, 1):
            out = {
                "rank": rank,
                "cos": round(cos, 4),
                "vec_id": r["vec_id"],
                "source_kind": r["source_kind"],
                "source_path": r["source_path"],
                "claim_id": r["claim_id"],
                "reliability": r["reliability"],
                "axis_b": r["axis_b"],
                "shard_id": r.get("shard_id"),
                "text_sha256": r["text_sha256"],
            }
            if args.show_contradictions:
                out["contradictions"] = contradictions_by_vec.get(r["vec_id"], [])
            print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        print(json.dumps({"_summary": {
            "query": args.query, "n_hits": len(hits),
            "n_total_searched": len(rows), "ms_elapsed": elapsed_ms,
        }}, sort_keys=True, separators=(",", ":")))
        return 0

    # Human format
    print(f"aep-search \"{args.query}\" --top-k {args.top_k} --scope {args.scope}")
    print()
    if not hits:
        print("(no hits above threshold)")
    for rank, (cos, r) in enumerate(hits, 1):
        rel = r.get("reliability") or "—"
        ax = r.get("axis_b") or "—"
        src = r.get("source_path") or "(no path)"
        cid = r.get("claim_id") or "—"
        print(f"[{rank}] {cos:.3f}  {r['vec_id']}  {rel}  {ax}")
        print(f"    {src}    claim={cid}")
        print(f"    text_sha={r['text_sha256'][:32]}...")
        if args.show_contradictions:
            conflicts = contradictions_by_vec.get(r["vec_id"], [])
            for c in conflicts[:3]:
                print(f"    ⚠ {c.get('class','?')}  pair={c.get('pair_id','?')}  cos={c.get('cos',0):.3f}")
    print()
    print(f"{len(hits)} hits · scope={args.scope} · {elapsed_ms}ms · index={args.index}")
    return 0


def canonical(msg, fmt):
    if fmt == "jsonl":
        return json.dumps({"error": msg}, sort_keys=True, separators=(",", ":"))
    return f"# {msg}"


if __name__ == "__main__":
    sys.exit(main())
