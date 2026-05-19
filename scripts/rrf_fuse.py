"""rrf_fuse.py — Reciprocal Rank Fusion (Cormack/Clarke/Buttcher SIGIR 2009).

Fuses N ranked lists into one. Score: sum over rankers of 1/(k + rank_i(d)).
Default k=60 per literature. Docs absent from a ranker contribute 0.

Used by falsifier_6_cross_agent_rrf.py to fuse BM25 + contextual + raw TF-IDF.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path("C:/Users/example-user/")


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Fuse N ranked lists of doc_ids into a single RRF-scored ranking."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank_minus_1, doc_id in enumerate(ranking):
            rank = rank_minus_1 + 1  # 1-indexed
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def rrf_fuse_weighted(
    rankings: list[tuple[list[str], float]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Weighted RRF: score(d) = sum_i w_i / (k + rank_i(d)).

    Loop-1 (investigation-loop-1) finding: equal-weight RRF over
    (BM25, contextual, TF-IDF) gave recall=0.0567 vs contextual-only 0.1135 -
    equal weights HURT because contextual is dominant and BM25/TF-IDF inject
    rank-1 noise that displaces correct contextual hits in the fused top-K.
    Weighted RRF lets the dominant ranker keep its near-top hits while still
    permitting secondary rankers to break ties / lift partial matches.

    Equivalent to standard Cormack/Clarke/Buttcher RRF when all weights == 1.

    Args:
        rankings: list of (ranked_doc_ids, weight) pairs. Higher weight = the
            ranker's votes count more in the fused score. Weights need not sum
            to 1 (RRF is rank-not-score based; absolute weight magnitude is
            what matters for relative contribution).
        k: standard RRF k parameter (60 per literature default).

    Returns:
        Sorted (doc_id, weighted_score) descending by score.
    """
    scores: dict[str, float] = {}
    for ranking, weight in rankings:
        for rank_minus_1, doc_id in enumerate(ranking):
            rank = rank_minus_1 + 1  # 1-indexed
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def fuse_conditional_fallback(
    primary: list[str],
    secondaries: list[tuple[list[str], float]],
    top_k: int,
    k: int = 60,
    primary_weight: float = 2.0,
) -> list[tuple[str, float]]:
    """Conditional-fallback fusion: only fuse with secondaries when primary
    returns fewer than top_k hits (i.e., didn't find enough on its own).

    Loop-2 hypothesis: if the primary (contextual) found >=top_k hits, it
    already knows what it's doing - fusion adds noise. If it returned <top_k,
    secondaries (BM25, TF-IDF) are evidence of last resort.

    Args:
        primary: dominant retriever's ranked doc_ids (e.g., contextual).
        secondaries: list of (ranking, weight) for fallback rankers.
        top_k: cutoff that defines "enough hits".
        k: RRF k parameter.
        primary_weight: primary's weight inside the weighted fusion if
            fallback fires.

    Returns:
        If len(primary) >= top_k: primary's first top_k entries with synthetic
        RRF scores (so callers can treat output uniformly).
        Else: weighted-RRF over [(primary, primary_weight)] + secondaries.
    """
    if len(primary) >= top_k:
        # Primary alone is sufficient; synthesize RRF-shaped scores for
        # downstream callers that expect (doc_id, score) tuples.
        return [(doc_id, 1.0 / (k + i + 1)) for i, doc_id in enumerate(primary[:top_k])]
    return rrf_fuse_weighted([(primary, primary_weight)] + secondaries, k=k)


def run_retriever(script_name: str, agent: str, task_hint: str, top_k: int) -> list[str]:
    """Shell out to a retriever script (lag_retrieve / _bm25 / _contextual)."""
    res = subprocess.run(
        [sys.executable, f"projects/v11-aep/publish-ready/aep/scripts/{script_name}",
         "--agent", agent, "--task-hint", task_hint,
         "--top-k", str(top_k), "--format", "ndjson"],
        capture_output=True, text=True, timeout=30,
    )
    out = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_summary" in j:
            continue
        vid = j.get("vec_id")
        if vid:
            out.append(vid)
    return out


def fuse_3_retrievers(agent: str, task_hint: str, top_k: int = 5,
                      depth: int = 20, k: int = 60) -> list[tuple[str, float]]:
    """Run 3 retrievers at depth=20 each, RRF-fuse, return top-K."""
    a = run_retriever("lag_retrieve.py", agent, task_hint, depth)
    b = run_retriever("lag_retrieve_bm25.py", agent, task_hint, depth)
    c = run_retriever("lag_retrieve_contextual.py", agent, task_hint, depth)
    fused = rrf_fuse([a, b, c], k=k)
    return fused[:top_k]


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--task-hint", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=20,
                    help="depth fetched from each ranker before RRF fusion")
    ap.add_argument("--k", type=int, default=60, help="RRF k parameter")
    args = ap.parse_args()

    fused = fuse_3_retrievers(args.agent, args.task_hint, args.top_k,
                              args.depth, args.k)
    for rank, (vid, score) in enumerate(fused, 1):
        print(json.dumps({
            "rank": rank, "vec_id": vid, "rrf_score": round(score, 6),
            "fused_from": ["lag_retrieve", "bm25", "contextual"], "k": args.k,
        }))
    print(json.dumps({"_summary": {
        "agent": args.agent, "n_hits": len(fused),
        "method": "rrf-3-ranker-bm25-contextual-tfidf",
    }}))


if __name__ == "__main__":
    main()
