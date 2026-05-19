"""falsifier_6_cross_agent_weighted_rrf.py - F6 cross-agent against
WEIGHTED RRF fusion + CONDITIONAL FALLBACK over (BM25, contextual, TF-IDF).

Loop-2 hypothesis (operator + investigation-loop-1 finding):
    Equal-weight RRF over the 3 rankers gave recall=0.0567, BELOW
    contextual-only baseline 0.1135. Contextual is the dominant ranker;
    BM25/TF-IDF inject rank-1 noise that displaces correct contextual hits
    in the fused top-K.

Two improvements tested:
    --mode weighted   : rrf_fuse_weighted with weights {contextual=2.0,
                        bm25=1.0, tfidf=0.5}. Contextual votes count 2x
                        BM25, 4x TF-IDF.
    --mode conditional: only fuse secondaries (BM25, TF-IDF) when
                        contextual returns N < top_k hits. If contextual
                        already returned >= top_k, use it alone.

Same denominator/numerator semantics as falsifier_6_cross_agent_contextual
and falsifier_6_cross_agent_rrf (single-writer reuse via import).

Cited:
    - judge.lamport-208 F6 4-variant battery (canonical V2 metric)
    - pathfinder.lamport-60 4-phase retrieval-arch ladder (P3 RRF gate)
    - scout.lamport-null-0f4c5c5e1c30 retrieval-architectures-beyond-tfidf
      (RRF + Anthropic contextual external prior art)
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
from rrf_fuse import (
    fuse_conditional_fallback,
    rrf_fuse_weighted,
    run_retriever,
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=20,
                    help="per-ranker depth before fusion")
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--mode", choices=["weighted", "conditional"],
                    required=True,
                    help="weighted = full weighted RRF; "
                         "conditional = only fuse when contextual<top_k")
    ap.add_argument("--w-contextual", type=float, default=2.0)
    ap.add_argument("--w-bm25", type=float, default=1.0)
    ap.add_argument("--w-tfidf", type=float, default=0.5)
    ap.add_argument("--k", type=int, default=60)
    args = ap.parse_args()

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
    n_fallback_fired = 0
    for c in unique:
        validation = validate_cite_against_ledger(c["citation"], args.ledger_root)
        if validation["status"] == "verified":
            n_verified += 1

        # Always retrieve from contextual (primary).
        ctx = run_retriever("lag_retrieve_contextual.py",
                            c["cited_agent"], c["task_hint"], args.depth)

        if args.mode == "weighted":
            bm = run_retriever("lag_retrieve_bm25.py",
                               c["cited_agent"], c["task_hint"], args.depth)
            tf = run_retriever("lag_retrieve.py",
                               c["cited_agent"], c["task_hint"], args.depth)
            fused = rrf_fuse_weighted(
                [(ctx, args.w_contextual),
                 (bm, args.w_bm25),
                 (tf, args.w_tfidf)],
                k=args.k,
            )[:args.top_k]
            fallback_fired = None  # not applicable
        else:  # conditional
            if len(ctx) < args.top_k:
                # Fallback fires; query secondaries and weighted-fuse.
                bm = run_retriever("lag_retrieve_bm25.py",
                                   c["cited_agent"], c["task_hint"], args.depth)
                tf = run_retriever("lag_retrieve.py",
                                   c["cited_agent"], c["task_hint"], args.depth)
                fused = fuse_conditional_fallback(
                    primary=ctx,
                    secondaries=[(bm, args.w_bm25), (tf, args.w_tfidf)],
                    top_k=args.top_k,
                    k=args.k,
                    primary_weight=args.w_contextual,
                )
                fallback_fired = True
                n_fallback_fired += 1
            else:
                # Contextual found enough on its own; no fallback.
                fused = fuse_conditional_fallback(
                    primary=ctx,
                    secondaries=[],
                    top_k=args.top_k,
                    k=args.k,
                    primary_weight=args.w_contextual,
                )
                fallback_fired = False

        hits_cited = [vid for vid, _score in fused]
        match_cited = (
            match_citation(c["citation"], hits_cited)
            and validation["status"] == "verified"
        )
        if match_cited:
            n_match_cited += 1
        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "task_hint": c["task_hint"][:80],
            "citation": c["citation"][:80],
            "match_in_cited_index_fused": match_cited,
            "ledger_validation_status": validation["status"],
            "fallback_fired": fallback_fired,
            "primary_hit_count": len(ctx),
        })

    n_total = len(per_query)
    recall_full = n_match_cited / n_total
    recall_verified = n_match_cited / n_verified if n_verified else 0.0

    method_tag = (
        f"weighted-rrf-ctx{args.w_contextual}-bm{args.w_bm25}-tf{args.w_tfidf}-k{args.k}"
        if args.mode == "weighted"
        else f"conditional-fallback-primary=contextual-ctx{args.w_contextual}-bm{args.w_bm25}-tf{args.w_tfidf}-k{args.k}"
    )

    summary = {
        "falsifier": f"F6-cross-agent-cites-recall-{args.mode.upper()}",
        "methodology": method_tag,
        "top_k": args.top_k,
        "n_cross_agent_citations": n_total,
        "n_verified": n_verified,
        "n_match_in_cited_index_fused": n_match_cited,
        "recall_full_denominator": round(recall_full, 4),
        "recall_verified_only": round(recall_verified, 4),
        "n_fallback_fired": n_fallback_fired if args.mode == "conditional" else None,
        "baseline_contextual_only_recall": 0.1135,
        "baseline_equal_rrf_recall": 0.0567,
        "delta_vs_contextual_only": round(recall_full - 0.1135, 4),
        "delta_vs_equal_rrf": round(recall_full - 0.0567, 4),
        "pass_threshold_provisional": 0.10,
        "pass_threshold_full": 0.50,
        "verdict": ("PASS" if recall_full >= 0.50
                    else "PROVISIONAL-PASS" if recall_full >= 0.10
                    else "FAIL"),
        "per_query": per_query[:30],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main() or 0)
