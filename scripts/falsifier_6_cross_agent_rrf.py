"""falsifier_6_cross_agent_rrf.py — F6 cross-agent against RRF-fused retrieval
(BM25 + contextual + raw TF-IDF) per scout's swap-in recommendation +
codex burn 3 RRF k=60 default.

Same denominator/numerator semantics as falsifier_6_cross_agent_contextual.py,
but the cited-index retrieval uses rrf_fuse.fuse_3_retrievers().
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from falsifier_6_cross_agent_cites import (
    mine_cross_agent_citations,
    match_citation,
    validate_cite_against_ledger,
)
from rrf_fuse import rrf_fuse, run_retriever


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=20,
                    help="per-ranker depth before fusion")
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--rankers", default="bm25,contextual,tfidf",
                    help="Comma-separated subset to fuse: bm25/contextual/tfidf")
    args = ap.parse_args()
    selected = set(args.rankers.split(","))

    raw = list(mine_cross_agent_citations(args.ledger_root))
    seen = set()
    unique = []
    for c in raw:
        key = (c["citing_agent"], c["cited_agent"], c["citation"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    if not unique:
        print(json.dumps({"verdict": "INSUFFICIENT-DATA",
                         "n_cross_agent_citations": 0}, indent=2))
        return 0

    per_query = []
    n_verified = n_match_cited = 0
    for c in unique:
        validation = validate_cite_against_ledger(c["citation"], args.ledger_root)
        if validation["status"] == "verified":
            n_verified += 1
        rankings = []
        if "bm25" in selected:
            rankings.append(run_retriever("lag_retrieve_bm25.py", c["cited_agent"], c["task_hint"], args.depth))
        if "contextual" in selected:
            rankings.append(run_retriever("lag_retrieve_contextual.py", c["cited_agent"], c["task_hint"], args.depth))
        if "tfidf" in selected:
            rankings.append(run_retriever("lag_retrieve.py", c["cited_agent"], c["task_hint"], args.depth))
        fused = rrf_fuse(rankings, k=60)[:args.top_k]
        hits_cited = [vid for vid, _score in fused]
        match_cited = match_citation(c["citation"], hits_cited) and validation["status"] == "verified"
        if match_cited:
            n_match_cited += 1
        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "task_hint": c["task_hint"][:80],
            "citation": c["citation"][:80],
            "match_in_cited_index_rrf": match_cited,
            "ledger_validation_status": validation["status"],
        })

    n_total = len(per_query)
    recall_full = n_match_cited / n_total
    recall_verified = n_match_cited / n_verified if n_verified else 0.0

    summary = {
        "falsifier": "F6-cross-agent-cites-recall-RRF-3-RANKER",
        "methodology": "rrf-fused-bm25-contextual-tfidf-k60-depth20",
        "top_k": args.top_k,
        "n_cross_agent_citations": n_total,
        "n_verified": n_verified,
        "n_match_in_cited_index_rrf": n_match_cited,
        "recall_rrf_full_denominator": round(recall_full, 4),
        "recall_rrf_verified_only": round(recall_verified, 4),
        "pass_threshold_provisional": 0.10,
        "pass_threshold_full": 0.50,
        "verdict": ("PASS" if recall_full >= 0.50 else
                    "PROVISIONAL-PASS" if recall_full >= 0.10 else "FAIL"),
        "per_query": per_query[:30],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main() or 0)
