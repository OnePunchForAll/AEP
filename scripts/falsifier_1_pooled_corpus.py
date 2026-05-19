"""falsifier_1_pooled_corpus.py - F1 LAG-relevance ATTACK variant via cross-agent pooling.

Sibling-85 H1 (structural-bound-attack-discipline) attack on F1's per-agent corpus
~0.30 P@5 structural bound (sibling-83 declaration).

REFRAME-THE-QUESTION: per-agent recall on tiny corpus (5-21 rows) -> cross-agent
recall on pooled corpus (50-210+ rows). The bound declared per-agent-corpus is
that the denominator is too small for TF-IDF cosine signal. Pooling ALL 10 agent
contextual indexes into one unified retrieval pool changes the denominator; this
script measures whether P@5 lifts above the prior 0.30 floor under the reframed
question.

PROTOCOL (mirrors falsifier_1_lag_relevance.py probe selection deterministically):
1. Sample 2 deterministic probes per agent (first + middle row of agent's contextual
   index) -> max 20 probes (matches per-agent baseline harness exactly).
2. Build the UNIFIED POOL = concatenation of all 10 agent contextual-index rows
   (cross_corpus_pool_retriever's load_aepkit_pool shape).
3. For each probe row: build probe_query from raw_invocation_excerpt + cluster_tags.
4. Anchors (truth set) = ALL pool rows whose cluster_tags intersect the probe's
   cluster_tags AND are NOT the probe itself. NOTE: under the reframed question
   anchors come from the POOLED corpus (cross-agent), not the per-agent subset.
   Drop probes with <3 anchors (matches per-agent baseline).
5. Apply identical BP-3 anchor-downsample cap at 5 anchors (deterministic hash
   selection) so P@5 measures discrimination not random-retrieval baseline.
6. Retrieve top-5 from UNIFIED POOL using cross_corpus_pool_retriever.score_row
   (Tier-3 contextual TF-IDF-light + Tier-2 cluster_tag boost over the pool).
   Exclude probe row from pool for leave-one-out integrity.
7. Compute per-probe P@5 + rank_margin_ratio + max_score.
8. Compare to per-agent baseline (mean P@5 ~0.30 per sibling-83).

VERDICT:
- PASS: mean P@5 > 0.50 -> bound POROUS for the reframed question
- PROVISIONAL: 0.30 < mean P@5 <= 0.50 -> bound partially porous
- FAIL: mean P@5 <= 0.30 -> bound GENUINE for the cross-corpus reframing too

HONEST DISCLOSURE BUILT IN (sibling-85 AP6):
- Reports anchor pool size per probe + a "random-baseline P@5" estimate (the
  probability of hitting an anchor by chance given pool_size and anchor_count).
  If P@5 only beats the per-agent floor because more candidate rows = more chances
  to hit by accident, the random baseline will be elevated AND the lift over the
  random baseline will be small. We explicitly compute this and surface it.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


# Same STOPWORDS / TOKEN_RE as falsifier_1_lag_relevance.py for protocol-fidelity
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

CANONICAL_AGENTS = [
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
]


def tokenize(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def build_df(pool):
    """Pool-wide document-frequency for IDF-light."""
    df = Counter()
    for row in pool:
        seen = set(tokenize(row["text"]))
        for tag in row["cluster_tags"]:
            seen.add(tag.lower())
        for t in seen:
            df[t] += 1
    return df, len(pool)


def score_row(query_tokens, row, df, N):
    """Tier-2 cluster_tag boost + Tier-3 TF-IDF-light overlap.
    Matches cross_corpus_pool_retriever.score_row semantics exactly."""
    if not query_tokens:
        return 0.0
    row_tokens = Counter(tokenize(row["text"]))
    row_tags = {t.lower() for t in row["cluster_tags"]}
    score = 0.0
    for qt in query_tokens:
        idf = math.log((N + 1) / (df.get(qt, 0) + 1)) + 1.0
        if qt in row_tags:
            score += 1.5 * idf
        tf = row_tokens.get(qt, 0)
        if tf > 0:
            score += (1.0 + math.log(1 + tf)) * idf
    return score


def main():
    repo = Path.cwd()
    # Use the SAME index source as the per-agent baseline (embeddings/) so the
    # probe set is byte-identical to falsifier_1_lag_relevance.py for fair compare.
    # Then we ALSO load the contextual-indexes pool (with context_prefix) which is
    # what the cross_corpus_pool_retriever uses operationally.
    embed_root = repo / "projects/v11-aep/publish-ready/aep/embeddings"
    pool_root = repo / "projects/v11-aep/publish-ready/aep/data/contextual-indexes"

    # ---- Step 1+2: Build probe set deterministically from per-agent embeddings ----
    probes = []  # list of (agent, probe_row_from_embed, agent_rows_for_anchor_calc)
    per_agent_rows = {}
    for agent in CANONICAL_AGENTS:
        idx_path = embed_root / f"agent-{agent}" / "index.jsonl"
        if not idx_path.exists():
            continue
        rows = []
        with open(idx_path, "r", encoding="utf-8") as f:
            for line in f:
                rows.append(json.loads(line))
        per_agent_rows[agent] = rows
        if not rows:
            continue
        picks = [rows[0]]
        if len(rows) >= 4:
            picks.append(rows[len(rows) // 2])
        for p in picks:
            probes.append((agent, p))
        if len(probes) >= 20:
            break
    probes = probes[:20]

    # ---- Step 2 continued: Build UNIFIED CROSS-AGENT POOL ----
    # Use contextual-indexes (carries context_prefix + cluster_tags + vec_id)
    # to match cross_corpus_pool_retriever shape exactly.
    pool = []
    for agent in CANONICAL_AGENTS:
        p = pool_root / f"{agent}.jsonl"
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
                "pool_id": row.get("vec_id") or f"ledger::{agent}::idx-{row.get('vec_idx', '?')}",
                "agent": agent,
                "text": text,
                "cluster_tags": row.get("cluster_tags", []) or [],
            })

    df, N_pool = build_df(pool)
    pool_id_to_idx = {row["pool_id"]: i for i, row in enumerate(pool)}

    # ---- Step 3-7: Score each probe ----
    per_probe = []
    for agent, probe_row in probes:
        probe_query = (probe_row.get("raw_invocation_excerpt", "") + " " +
                       " ".join(probe_row.get("cluster_tags") or []))
        probe_tags = set(probe_row.get("cluster_tags") or [])
        probe_vec_id = probe_row["vec_id"]

        # Anchors over POOLED corpus (cross-agent), NOT just probe's own agent
        anchors_full = set()
        for row in pool:
            if row["pool_id"] == probe_vec_id:
                continue
            if probe_tags & set(row["cluster_tags"]):
                anchors_full.add(row["pool_id"])

        if len(anchors_full) < 3:
            per_probe.append({
                "agent": agent, "vec_id": probe_vec_id,
                "skipped": "insufficient_anchors_in_pool",
                "n_anchors_in_pool": len(anchors_full),
            })
            continue

        # BP-3 anchor cap (same as per-agent baseline)
        anchors_sorted = sorted(anchors_full, key=lambda v: hash((probe_vec_id, v)))
        anchors = set(anchors_sorted[:5])
        anchor_downsample_applied = len(anchors_full) > 5

        # Retrieve top-5 from UNIFIED POOL (exclude probe for leave-one-out)
        qtoks = tokenize(probe_query)
        scored = []
        for row in pool:
            if row["pool_id"] == probe_vec_id:
                continue
            s = score_row(qtoks, row, df, N_pool)
            if s > 0:
                scored.append((s, row))
        scored.sort(key=lambda x: (-x[0], x[1]["pool_id"]))
        top5 = scored[:5]

        n_relevant = sum(1 for s, row in top5 if row["pool_id"] in anchors)
        p5 = n_relevant / 5.0
        max_score = top5[0][0] if top5 else 0.0
        rank_margin = (top5[0][0] - top5[-1][0]) if len(top5) >= 2 else 0.0
        rank_margin_ratio = (rank_margin / top5[0][0]) if top5 and top5[0][0] > 0 else 0.0

        # Random-baseline P@5 (anti-self-deception per sibling-85 AP6 disclosure):
        # If we picked 5 rows uniformly at random from the pool (minus probe),
        # expected hits = 5 * (n_anchors / (pool_size - 1)). This is the floor
        # that any naive retriever beats trivially.
        eff_pool_size = max(1, N_pool - 1)
        random_baseline_p5 = min(1.0, 5.0 * len(anchors) / eff_pool_size) / 5.0
        lift_over_random = round(p5 - random_baseline_p5, 3)

        # Track top-5 source distribution: were any cross-agent? (the whole point)
        top5_agents = [row["agent"] for s, row in top5]
        cross_agent_in_top5 = sum(1 for a in top5_agents if a != agent)

        per_probe.append({
            "agent": agent, "vec_id": probe_vec_id,
            "n_anchors_capped": len(anchors),
            "n_anchors_full_pool": len(anchors_full),
            "anchor_downsample_applied": anchor_downsample_applied,
            "p_at_5": round(p5, 3),
            "n_relevant": n_relevant,
            "max_score": round(max_score, 4),
            "rank_margin_ratio": round(rank_margin_ratio, 3),
            "random_baseline_p5": round(random_baseline_p5, 3),
            "lift_over_random": lift_over_random,
            "top5_agents": top5_agents,
            "cross_agent_in_top5": cross_agent_in_top5,
        })

    scored_probes = [p for p in per_probe if "p_at_5" in p]
    mean_p5 = sum(p["p_at_5"] for p in scored_probes) / max(1, len(scored_probes))
    mean_rank_margin_ratio = (
        sum(p.get("rank_margin_ratio", 0) for p in scored_probes) /
        max(1, len(scored_probes))
    )
    mean_random_baseline_p5 = (
        sum(p.get("random_baseline_p5", 0) for p in scored_probes) /
        max(1, len(scored_probes))
    )
    mean_lift_over_random = (
        sum(p.get("lift_over_random", 0) for p in scored_probes) /
        max(1, len(scored_probes))
    )
    mean_cross_agent_in_top5 = (
        sum(p.get("cross_agent_in_top5", 0) for p in scored_probes) /
        max(1, len(scored_probes))
    )

    # Per-agent baseline reference (from sibling-83 declaration; canonical floor)
    per_agent_baseline_p5 = 0.30

    # Sibling-85 H1 verdict thresholds
    if mean_p5 > 0.50:
        verdict = "PASS-BOUND-POROUS"
    elif mean_p5 > per_agent_baseline_p5:
        verdict = "PROVISIONAL-PARTIALLY-POROUS"
    else:
        verdict = "FAIL-BOUND-GENUINE"

    # Honest-disclosure verdict: if mean_lift_over_random is NOT meaningfully
    # positive, pool-attack only "worked" because random-hit rate went up too.
    if mean_lift_over_random < 0.10:
        honest_caveat = (
            "WARNING: mean lift over random baseline < 0.10. The pool-attack's "
            "raw P@5 increase may largely reflect a higher random-hit rate "
            "(more candidate rows = more accidental anchor hits). The retriever "
            "is barely outperforming uniform-random retrieval on the pooled corpus."
        )
    else:
        honest_caveat = (
            "Pool-attack mean lift over random baseline is meaningful (>= 0.10); "
            "the retriever discriminates beyond mere pool-size inflation."
        )

    summary = {
        "falsifier": "F1-pooled-corpus-attack (sibling-85 H1)",
        "session_id": "f1-corpus-pool-attack-sibling-85-h1-2026-05-15",
        "mission": "AEP-V11-AEP-LOOP-9-F1-F2-STRUCTURAL-BOUND-ATTACKS-2026-05-15",
        "pool_size": N_pool,
        "n_probes_total": len(per_probe),
        "n_probes_scored": len(scored_probes),
        "per_agent_baseline_p5_reference": per_agent_baseline_p5,
        "per_agent_baseline_source": "sibling-83 STRUCTURALLY BOUNDED declaration",
        "mean_p_at_5_pooled": round(mean_p5, 3),
        "delta_vs_per_agent_baseline": round(mean_p5 - per_agent_baseline_p5, 3),
        "mean_rank_margin_ratio": round(mean_rank_margin_ratio, 3),
        "mean_random_baseline_p5": round(mean_random_baseline_p5, 3),
        "mean_lift_over_random": round(mean_lift_over_random, 3),
        "mean_cross_agent_in_top5": round(mean_cross_agent_in_top5, 2),
        "verdict": verdict,
        "honest_caveat": honest_caveat,
        "thresholds": {
            "PASS_p5": 0.50,
            "PROVISIONAL_p5_lower": per_agent_baseline_p5,
            "honest_lift_floor": 0.10,
        },
        "cites": [
            "scribe::sibling-85::structural-bound-attack-discipline-2026-05-15",
            "forge::lamport-null-ab8d5507c11a::loops-5-8-forge-cross-corpus-pool-2026-05-15",
            "judge::lamport-210::loops-5-8-judge-master-verdict-2026-05-15",
        ],
        "per_probe": per_probe,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
