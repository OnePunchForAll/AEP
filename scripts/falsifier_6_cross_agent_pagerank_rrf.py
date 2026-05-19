"""falsifier_6_cross_agent_pagerank_rrf.py — Loop-4 F6 cross-agent recall when
PageRank ranking is RRF-fused with contextual + BM25 + raw TF-IDF.

Same denominator/numerator semantics as falsifier_6_cross_agent_rrf.py, but
adds a fourth ranker: a global PageRank-induced ranking over the per-query
candidate pool (union of all rankers' depth-D hits). RRF k=60.

Reports BOTH recall_4_ranker (with PageRank fold) and recall_3_ranker
(without) so the PageRank delta is isolated as the load-bearing finding.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from falsifier_6_cross_agent_cites import (  # noqa: E402
    mine_cross_agent_citations,
    match_citation,
    validate_cite_against_ledger,
)
from rrf_fuse import rrf_fuse, run_retriever  # noqa: E402


def load_pagerank(path: Path) -> dict[str, float]:
    if not path.exists():
        sys.stderr.write(f"WARN: PageRank map missing at {path}\n")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pagerank_ranking_over_pool(candidate_pool: list[str],
                               pr_map: dict[str, float]) -> list[str]:
    """Return the candidate pool ordered by PageRank descending."""
    scored = [(c, pr_map.get(c, 0.0)) for c in candidate_pool]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return [c for c, _ in scored]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--pagerank-json", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/data/citegraph-pagerank.json"))
    args = ap.parse_args()

    pr_map = load_pagerank(args.pagerank_json)
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
    n_verified = 0
    n_match_3 = 0
    n_match_4 = 0
    for c in unique:
        validation = validate_cite_against_ledger(c["citation"], args.ledger_root)
        if validation["status"] == "verified":
            n_verified += 1
        a = run_retriever("lag_retrieve.py", c["cited_agent"], c["task_hint"], args.depth)
        b = run_retriever("lag_retrieve_bm25.py", c["cited_agent"], c["task_hint"], args.depth)
        d = run_retriever("lag_retrieve_contextual.py", c["cited_agent"], c["task_hint"], args.depth)
        # Candidate pool = union of all rankers' results
        pool = list(dict.fromkeys(a + b + d))
        pr_rank = pagerank_ranking_over_pool(pool, pr_map)

        fused_3 = rrf_fuse([a, b, d], k=60)[:args.top_k]
        fused_4 = rrf_fuse([a, b, d, pr_rank], k=60)[:args.top_k]
        hits_3 = [vid for vid, _ in fused_3]
        hits_4 = [vid for vid, _ in fused_4]

        m3 = match_citation(c["citation"], hits_3) and validation["status"] == "verified"
        m4 = match_citation(c["citation"], hits_4) and validation["status"] == "verified"
        if m3:
            n_match_3 += 1
        if m4:
            n_match_4 += 1
        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "citation": c["citation"][:80],
            "match_3_ranker": m3,
            "match_4_ranker_with_pagerank": m4,
            "pool_size": len(pool),
            "validation": validation["status"],
        })

    n_total = len(per_query)
    recall_3 = n_match_3 / n_total
    recall_4 = n_match_4 / n_total
    recall_3_verified = (n_match_3 / n_verified) if n_verified else 0.0
    recall_4_verified = (n_match_4 / n_verified) if n_verified else 0.0
    delta_full = recall_4 - recall_3
    delta_verified = recall_4_verified - recall_3_verified

    summary = {
        "falsifier": "F6-cross-agent-cites-recall-PAGERANK-RRF-4-RANKER",
        "methodology": "rrf-fuse(bm25,contextual,tfidf,pagerank)-k60-depth20",
        "top_k": args.top_k,
        "depth": args.depth,
        "n_cross_agent_citations": n_total,
        "n_verified": n_verified,
        "n_match_3_ranker": n_match_3,
        "n_match_4_ranker_with_pagerank": n_match_4,
        "recall_3_ranker_full": round(recall_3, 4),
        "recall_4_ranker_full": round(recall_4, 4),
        "recall_3_ranker_verified": round(recall_3_verified, 4),
        "recall_4_ranker_verified": round(recall_4_verified, 4),
        "pagerank_delta_full": round(delta_full, 4),
        "pagerank_delta_verified": round(delta_verified, 4),
        "pagerank_nodes_loaded": len(pr_map),
        "per_query": per_query[:30],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main() or 0)
