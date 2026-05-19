"""smoke_contextual_vs_raw_tfidf.py - 5-hint rank-delta smoke test.

Same 5 cross-agent cite task hints as the BM25 sibling smoke test. Compares
rank-of-cited in CONTEXTUAL-TF-IDF (build_contextual_index.py output) vs
RAW-TF-IDF (build_lag_indices.py output). Reports rank delta per hint.

Methodology (mirrors falsifier_6_cross_agent_cites.py mining pattern):
  1. Pick 5 cross-agent (citing_agent, cited_agent, task_hint, citation) tuples
     from real ledger evidence (these are the ground-truth labels).
  2. For each (cited_agent, task_hint), retrieve top-K from BOTH indexes.
  3. Find the rank of citation in each result list (1-indexed; null if absent
     from top-K).
  4. Report (rank_raw, rank_contextual, delta = rank_raw - rank_contextual).
     Positive delta = contextual is BETTER (lower rank = higher position).
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path


# Five hand-picked cross-agent cite tuples (from real ledger entries).
# Hint text deliberately approximates the citing-row's invocation; rank
# is the position of `citation` in the top-K results (1 = best).
HINTS = [
    {
        "id": "H1",
        "citing_agent": "scout",
        "cited_agent": "forge",
        "task_hint": "external prior-art retrieval architectures beyond TF-IDF "
                     "BM25 sentence-bert ColBERT SPLADE hybrid retrieval RRF "
                     "Anthropic Contextual Retrieval",
        # vec_id session-suffix is truncated to 24 chars per build_lag_indices.
        "citation": "ledger::forge::lamport-210::closure-surge-forge-clos",
    },
    {
        "id": "H2",
        "citing_agent": "judge",
        "cited_agent": "forge",
        "task_hint": "F6 4-variant battery cross-agent citation recall denominator "
                     "top-k sweep canonical metric task-aligned harness",
        "citation": "ledger::forge::lamport-211::final-round-forge-task-aligned-",
    },
    {
        "id": "H3",
        "citing_agent": "scout",
        "cited_agent": "judge",
        "task_hint": "audit F6-cross-agent stale-baseline circularity diagnosis "
                     "live-derive default self-baseline override",
        "citation": "ledger::judge::lamport-205::cross-agent-citation-test-judge",
    },
    {
        "id": "H4",
        "citing_agent": "judge",
        "cited_agent": "forge",
        "task_hint": "standardize lamport-null BLAKE2b spec canonical refactor F6 "
                     "validator delegate sibling-78 ensure_ascii fix",
        "citation": "ledger::forge::lamport-209::max-power-wave-forge",
    },
    {
        "id": "H5",
        "citing_agent": "forge",
        "cited_agent": "scout",
        "task_hint": "external prior-art content-addressable row identity 12 "
                     "precedents 8 domains BLAKE2b CID merkle SRI RFC6920 JCS",
        # vec_id session-suffix is truncated to 24 chars; lamport-null fallback
        # uses the row-content-hash branch in build_lag_indices when lamport_id
        # is set (no lamport_counter), yielding lamport-null-<8byte-hex>.
        "citation": "ledger::scout::lamport-null-",
    },
]


# --- Tokenizer + TF-IDF (same algorithm as build_lag_indices / contextual) ---

STOPWORDS = frozenset(
    "a an the of and or but not for to in on at by from with as is are was were be been being "
    "have has had do does did this that these those it its their there here we us our you your "
    "they them he she his her him will would should could may might must can shall about above "
    "after again against all am any aren't because been before below between both can't cannot "
    "couldn't did didn't doesn't doing don't down during each few further haven't hasn't hadn't "
    "her here's hers herself himself his how if into let's me more most mustn't my myself nor "
    "off once only other ought our ours ourselves out over own same shan't she'd she'll she's so "
    "some such than that's then theirs themselves there's they'd they'll they're they've through "
    "too under until up very wasn't we'd we'll we're we've weren't what what's when when's where "
    "where's which while who who's whom why why's won't wouldn't yours yourself yourselves".split()
)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_]{2,}")


def tokenize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def vectorize_query(query, vocab_idx, idf_arr):
    tc = Counter(tokenize(query))
    vec = {}
    for t, c in tc.items():
        if t not in vocab_idx:
            continue
        idx = vocab_idx[t]
        vec[idx] = (1.0 + math.log(c)) * idf_arr[idx]
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def cosine(qvec, row_sparse):
    s = 0.0
    for tw in row_sparse:
        if tw["t"] in qvec:
            s += qvec[tw["t"]] * tw["w"]
    return s


def load_raw_index(agent):
    """Load RAW (non-contextual) per-agent index from build_lag_indices output."""
    root = Path("projects/v11-aep/publish-ready/aep/embeddings") / f"agent-{agent}"
    vocab_idx = {}
    idf_arr = {}
    with open(root / "vocabulary.jsonl", "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            vocab_idx[row["term"]] = i
            idf_arr[i] = row["idf"]
    rows = []
    with open(root / "index.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return vocab_idx, idf_arr, rows


def load_contextual_index(agent):
    """Load CONTEXTUAL per-agent index from build_contextual_index output."""
    root = Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes")
    vocab_idx = {}
    idf_arr = {}
    with open(root / f"{agent}.vocab.jsonl", "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            vocab_idx[row["term"]] = i
            idf_arr[i] = row["idf"]
    rows = []
    with open(root / f"{agent}.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return vocab_idx, idf_arr, rows


def rank_of_cite(vocab_idx, idf_arr, rows, task_hint, citation, top_k=20):
    """Compute rank (1-indexed) of citation in top_k retrieval, or None.

    Match-rule mirrors falsifier_6 match_citation: substring match, lamport-tail
    match, and slug-agnostic (agent, lamport-N) prefix match. We use the LIBERAL
    matcher because raw vs contextual indexes both use the same vec_id format,
    so any matcher behaves identically across the two -- only the cosine
    ranking differs.
    """
    qvec = vectorize_query(task_hint, vocab_idx, idf_arr)
    if not qvec:
        return None, "empty-query-vector"
    scored = []
    for r in rows:
        cos = cosine(qvec, r.get("sparse_vec", []))
        if cos > 0:
            scored.append((cos, r["vec_id"]))
    scored.sort(key=lambda x: -x[0])
    top = scored[:top_k]

    # Liberal match: prefix (citation[:N]) substring of vec_id
    cite_prefix = citation
    for rank, (cos, vid) in enumerate(top, 1):
        if cite_prefix in vid:
            return rank, f"cos={cos:.4f}"
        # Also try lamport-NN match
        lamport_idx = citation.find("lamport-")
        if lamport_idx >= 0:
            # Find next ::
            slug_start = citation.find("::", lamport_idx)
            if slug_start >= 0:
                identity_prefix = citation[:slug_start]
                if vid.startswith(identity_prefix):
                    return rank, f"cos={cos:.4f}"
    # Not in top-K
    return None, f"absent-from-top-{top_k}"


def main():
    results = []
    for hint in HINTS:
        agent = hint["cited_agent"]
        try:
            v_raw, idf_raw, rows_raw = load_raw_index(agent)
        except FileNotFoundError as e:
            results.append({**hint, "raw_status": f"missing-raw-index: {e}"})
            continue
        try:
            v_ctx, idf_ctx, rows_ctx = load_contextual_index(agent)
        except FileNotFoundError as e:
            results.append({**hint, "ctx_status": f"missing-contextual-index: {e}"})
            continue

        rank_raw, raw_meta = rank_of_cite(v_raw, idf_raw, rows_raw,
                                          hint["task_hint"], hint["citation"])
        rank_ctx, ctx_meta = rank_of_cite(v_ctx, idf_ctx, rows_ctx,
                                          hint["task_hint"], hint["citation"])

        # Delta semantics: positive = contextual better (lower rank).
        # Treat "absent" as rank=999 for delta arithmetic so we still rank moves.
        rr = rank_raw if rank_raw is not None else 999
        rc = rank_ctx if rank_ctx is not None else 999
        delta = rr - rc

        results.append({
            "id": hint["id"],
            "citing_agent": hint["citing_agent"],
            "cited_agent": agent,
            "task_hint_preview": hint["task_hint"][:80] + "...",
            "citation_preview": hint["citation"],
            "rank_raw_tfidf": rank_raw,
            "rank_contextual_tfidf": rank_ctx,
            "delta_raw_minus_ctx": delta,
            "raw_meta": raw_meta,
            "ctx_meta": ctx_meta,
            "verdict_per_hint": (
                "CONTEXTUAL-WINS" if delta > 0
                else "RAW-WINS" if delta < 0
                else "TIE"
            ),
        })

    # Aggregate
    n = len(results)
    n_wins = sum(1 for r in results if r.get("verdict_per_hint") == "CONTEXTUAL-WINS")
    n_losses = sum(1 for r in results if r.get("verdict_per_hint") == "RAW-WINS")
    n_ties = sum(1 for r in results if r.get("verdict_per_hint") == "TIE")
    deltas = [r["delta_raw_minus_ctx"] for r in results
              if "delta_raw_minus_ctx" in r]
    avg_delta = (sum(deltas) / len(deltas)) if deltas else 0.0

    summary = {
        "smoke_test": "contextual-vs-raw-tfidf-rank-of-cited",
        "n_hints": n,
        "n_contextual_wins": n_wins,
        "n_raw_wins": n_losses,
        "n_ties": n_ties,
        "avg_delta_raw_minus_ctx": round(avg_delta, 2),
        "interpretation": (
            "delta > 0 = contextual ranks the cited row HIGHER (closer to top); "
            "delta < 0 = raw wins; absent-from-top-K treated as rank 999"
        ),
        "per_hint_results": results,
    }
    print(json.dumps(summary, indent=2, sort_keys=False))


if __name__ == "__main__":
    sys.exit(main() or 0)
