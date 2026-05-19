"""cross_corpus_pool_retriever.py - AEP project-ledger + PDF-AEP UNIFIED retrieval.

THE "IMPOSSIBLE" AXIS (operator directive 2026-05-15):
Cross-corpus retrieval that POOLS AEP project ledger rows + ingested PDF chunks into
a single unified retrieval space. Treats PDF chunks as "agent=pdf-source" rows so
the same scoring pipeline that handles 10-canonical-agent ledger rows also
ranks unstructured PDF content with no schema branching.

Architectural insight:
  - AEP project contextual indexes carry context_prefix + raw text + cluster_tags
    (structured semantic anchors).
  - PDF AEP companions carry `text` (claim text) + chunk metadata (page, span).
  - Both surfaces are bags-of-tokens in the end. Normalize to a common
    {pool_id, source_kind, agent, text, cluster_tags, ...} schema, then run
    a single TF-style scorer over the unified pool.

Three-tier resolution (mirrors canonical_resolve_retriever's spirit):
  Tier 1 - canonical-vec_id fast-path: if the query is or contains a canonical
           citation `ledger::<agent>::lamport-...::<slug>`, resolve directly via
           canonical_resolve_retriever's resolve_vec_id_to_row (recall=1.0 by
           construction).
  Tier 2 - cluster_tag exact-match boost: any pool row whose cluster_tags
           intersect the query's tokenized terms gets +1.5 score (AEP project rows
           dominate here; PDF chunks have cluster_tags from extraction).
  Tier 3 - contextual TF-overlap: tokenize query and pool-row text+context_prefix,
           score by overlap-count + IDF-light weighting (rare term = higher).

CLI:
  python cross_corpus_pool_retriever.py \\
      --query "canonical citation discipline" --top-k 3 --format ndjson

Output: ndjson rows with rank/pool_id/source_kind/agent/score/excerpt + summary.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

# Reuse canonical-resolve fast-path
sys.path.insert(0, str(Path(__file__).parent))
from canonical_resolve_retriever import (  # noqa: E402
    extract_canonical_cites,
    resolve_vec_id_to_row,
    row_to_vec_id,
)


CANONICAL_AGENTS = [
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
]

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "have",
    "has", "are", "was", "were", "but", "not", "all", "any", "can", "its",
    "their", "they", "them", "our", "out", "via", "per", "such", "than",
}


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in TOKEN_RE.findall(text) if t.lower() not in STOPWORDS]


def load_aepkit_pool(idx_root: Path) -> list[dict]:
    """Load all 10 canonical-agent contextual indexes into the unified pool."""
    pool = []
    for agent in CANONICAL_AGENTS:
        p = idx_root / f"{agent}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = " ".join([
                row.get("context_prefix") or "",
                row.get("raw_invocation_excerpt") or "",
                row.get("raw_notes_excerpt") or "",
            ]).strip()
            pool.append({
                "pool_id": row.get("vec_id") or f"ledger::{agent}::idx-{row.get('vec_idx','?')}",
                "source_kind": "aepkit-ledger",
                "agent": agent,
                "text": text,
                "cluster_tags": row.get("cluster_tags", []) or [],
                "date": row.get("date", "?"),
                "session_id": row.get("session_id", "?"),
                "lamport_counter": row.get("lamport_counter"),
                "reliability": row.get("reliability", "?"),
                "outcome": row.get("outcome", "?"),
            })
    return pool


def load_pdf_pool(aep_claims_path: Path | None, jsonl_path: Path | None) -> list[dict]:
    """Load synthetic-PDF AEP companion data (preferred) with fallback to the
    raw extraction jsonl. PDF chunks become `agent=pdf-source` rows in the pool."""
    pool = []
    if aep_claims_path and aep_claims_path.exists():
        for line in aep_claims_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                claim = json.loads(line)
            except json.JSONDecodeError:
                continue
            pool.append({
                "pool_id": claim.get("id") or f"pdf:claim:{len(pool)}",
                "source_kind": "pdf-aep-claim",
                "agent": "pdf-source",
                "text": claim.get("text") or "",
                "cluster_tags": [],
                "date": (claim.get("created_at") or "")[:10] or "?",
                "session_id": "synthetic_test_2026-05-15",
                "lamport_counter": None,
                "reliability": claim.get("reliability", "?"),
                "outcome": "n/a",
                "basis": claim.get("basis", []),
                "axis_b_action": claim.get("axis_b_action", "?"),
            })
        return pool
    # Fallback: raw extraction jsonl (chunk-level)
    if jsonl_path and jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            pool.append({
                "pool_id": row.get("chunk_id") or f"pdf:chunk:{len(pool)}",
                "source_kind": "pdf-chunk-fallback",
                "agent": "pdf-source",
                "text": row.get("notes") or row.get("invocation") or "",
                "cluster_tags": row.get("cluster_tags", []) or [],
                "date": "?",
                "session_id": row.get("session_id", "?"),
                "lamport_counter": row.get("lamport_counter"),
                "reliability": "?",
                "outcome": "n/a",
            })
    return pool


def build_df(pool: list[dict]) -> tuple[Counter, int]:
    """Document-frequency over the unified pool for IDF-light weighting."""
    df: Counter = Counter()
    for row in pool:
        seen = set(tokenize(row["text"]))
        for tok in row["cluster_tags"]:
            seen.add(tok.lower())
        for t in seen:
            df[t] += 1
    return df, len(pool)


def score_row(query_tokens: list[str], row: dict, df: Counter, N: int) -> float:
    """Tier-2 cluster_tag boost + Tier-3 TF-IDF-light overlap."""
    if not query_tokens:
        return 0.0
    row_text = row["text"]
    row_tokens = Counter(tokenize(row_text))
    row_tags = {t.lower() for t in row["cluster_tags"]}
    score = 0.0
    for qt in query_tokens:
        idf = math.log((N + 1) / (df.get(qt, 0) + 1)) + 1.0
        if qt in row_tags:
            score += 1.5 * idf  # Tier-2 cluster_tag exact-match boost
        tf = row_tokens.get(qt, 0)
        if tf > 0:
            # Sublinear TF to prevent long-text dominance
            score += (1.0 + math.log(1 + tf)) * idf
    return score


def retrieve(query: str, pool: list[dict], top_k: int,
             ledger_root: Path) -> tuple[list[dict], dict]:
    """Three-tier retrieval over the unified pool."""
    hits: list[dict] = []
    summary = {
        "query": query, "top_k": top_k,
        "pool_size": len(pool),
        "tier1_canonical_hits": 0, "tier3_contextual_hits": 0,
        "aepkit_in_top_k": 0, "pdf_in_top_k": 0,
    }

    # Tier 1 - canonical fast-path
    cites = extract_canonical_cites(query)
    for c in cites:
        row = resolve_vec_id_to_row(c, ledger_root)
        if row is None:
            continue
        agent = c.split("::")[1]
        hits.append({
            "rank": len(hits) + 1,
            "pool_id": c,
            "source_kind": "aepkit-ledger",
            "agent": agent,
            "tier": "1-canonical-resolve",
            "score": float("inf"),
            "excerpt": (row.get("invocation") or "")[:200],
            "cluster_tags": row.get("cluster_tags", []),
            "date": row.get("date", "?"),
            "session_id": row.get("session_id", "?"),
        })
        summary["tier1_canonical_hits"] += 1
        if len(hits) >= top_k:
            summary["aepkit_in_top_k"] = sum(
                1 for h in hits if h["source_kind"].startswith("aepkit"))
            summary["pdf_in_top_k"] = sum(
                1 for h in hits if h["source_kind"].startswith("pdf"))
            return hits, summary

    # Tier 3 - contextual TF-IDF-light over remaining pool
    qtoks = tokenize(query)
    df, N = build_df(pool)
    scored = []
    for row in pool:
        s = score_row(qtoks, row, df, N)
        if s > 0:
            scored.append((s, row))
    scored.sort(key=lambda x: (-x[0], x[1]["pool_id"]))
    for s, row in scored:
        if len(hits) >= top_k:
            break
        hits.append({
            "rank": len(hits) + 1,
            "pool_id": row["pool_id"],
            "source_kind": row["source_kind"],
            "agent": row["agent"],
            "tier": "3-contextual-tfidf-light",
            "score": round(s, 4),
            "excerpt": row["text"][:200],
            "cluster_tags": row["cluster_tags"],
            "date": row["date"],
            "session_id": row["session_id"],
        })
        summary["tier3_contextual_hits"] += 1

    summary["aepkit_in_top_k"] = sum(
        1 for h in hits if h["source_kind"].startswith("aepkit"))
    summary["pdf_in_top_k"] = sum(
        1 for h in hits if h["source_kind"].startswith("pdf"))
    return hits, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--format", default="ndjson", choices=["ndjson"])
    ap.add_argument("--idx-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes"))
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--pdf-aep-claims", type=Path,
                    default=Path("tmp/pdf_test_output_2026-05-15/synthetic_test_2026-05-15.aepkg/data/claims.jsonl"))
    ap.add_argument("--pdf-fallback-jsonl", type=Path,
                    default=Path("tmp/pdf_test_output_2026-05-15/synthetic_test_2026-05-15.jsonl"))
    args = ap.parse_args()

    aepkit_pool = load_aepkit_pool(args.idx_root)
    pdf_pool = load_pdf_pool(args.pdf_aep_claims, args.pdf_fallback_jsonl)
    unified_pool = aepkit_pool + pdf_pool

    hits, summary = retrieve(args.query, unified_pool, args.top_k, args.ledger_root)
    summary["aepkit_pool_size"] = len(aepkit_pool)
    summary["pdf_pool_size"] = len(pdf_pool)

    for h in hits:
        if h["score"] == float("inf"):
            h["score"] = "canonical-exact"
        print(json.dumps(h, ensure_ascii=False))
    print(json.dumps({"_summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
