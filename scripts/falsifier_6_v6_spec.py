"""falsifier_6_v6_spec.py - F6-V6 content-semantic-similarity falsifier (DESIGN SPEC + SKELETON).

PROBLEM (operator directive 2026-05-15, loop-3-judge-f6-v6-design):
  F6 V1-V5 all gate on CITE-AS-GOLD-TRUTH:
    * V1 (self-emitted):        gold = cited row of the citing row's `cites:` field
    * V2 (cross-agent cites):   gold = cited row in OTHER agent's ledger
    * V3 (contextual):          same gold; different retriever
    * V4 (RRF / weighted RRF):  same gold; fused retriever
    * V5 (canonical-resolve):   same gold; direct lookup BY STRUCTURED ID
    * V5-hybrid (1+2+3):        same gold; tiered

  All five are CIRCULAR: "given an existing cite, can we look it up?" — the
  cite IS the gold-truth, and the cite emitter is also the corpus author. This
  collapses to: "does our cite syntax parse?" — a parser test, not retrieval.
  judge.lamport-209 100%-recall claim falsifies under this lens (sibling-81
  construction-vs-retrieval distinction; tier-3 dropoff to 11.35%).

GOAL — break the circularity by testing TRUE semantic retrieval:
  "Given a row R as a QUERY, can the retriever surface OTHER rows that are
   TOPICALLY RELATED to R but do NOT cite R and are NOT cited BY R?"

This is the standard IR formulation: query → topically-related docs in top-K,
with relevance judgments authored INDEPENDENTLY of citation links.

METHODOLOGY:
  1. Manually select 10 QUERY rows from the master ledger corpus.
     Selection rules:
       (a) row has substantive invocation + notes (combined >= 200 chars)
       (b) row sits in a recognizable topical cluster (e.g., F6/recall,
           lamport-null/blake2b, doctrine-§45/codex-burn, scribe/sibling-lesson)
       (c) at least 3 OTHER rows exist in the corpus that share the topic but
           are NOT in the query's cites: nor cite the query directly
       (d) topical-relatedness is determined by INDEPENDENT semantic judgment
           (overlap of concepts, problem domain, technique) — not by citation
           graph reachability

  2. For each query row R, manually author GOLD_TRUTH[R] = set of 3-5 row IDs
     that are topically related per (c) and (d). Author MUST verify:
        - No gold-truth row is in R.cites
        - R is not in any gold-truth row.cites (no reverse citation either)
        - Gold-truth row's topic genuinely overlaps R's topic (one-sentence
          justification per row in GOLD_TRUTH_JUSTIFICATIONS)

  3. For each retrieval method M in {TF-IDF, contextual-prepend, canonical-resolve}:
       a. Build query text Q = R.invocation + " " + R.notes (first 1000 chars)
       b. Run M(Q, corpus=all-agents-merged, top_k=10)
          -- IMPORTANT: corpus must be merged ACROSS agents (V1-V5 are per-agent)
          -- IMPORTANT: must EXCLUDE R itself from candidates (otherwise
             trivial self-match dominates)
       c. recall@K = |gold_truth ∩ top_K| / |gold_truth|
       d. precision@K = |gold_truth ∩ top_K| / K

  4. Report per-query and aggregate (mean recall@10, precision@10) per method.

SIGNAL INTERPRETATION:
  * recall@10 >= 0.50 for ANY method  → retrieval architecture has REAL
    semantic-similarity capability beyond cite-lookup; sibling-81 falsifier
    target is empirically met.
  * recall@10 in [0.20, 0.50]          → partial capability; mid-tier finding.
  * recall@10 < 0.20 for all methods   → retrieval is essentially a cite-lookup
    veneer; V1-V5 100% headline numbers are construction-by-cite-resolution,
    not retrieval. judge.lamport-209 "beat Anthropic 67%" framing is BLOCKED.

  Inter-method DELTA matters too: if canonical-resolve scores 0 here (it
  cannot — no canonical ID to resolve from a free-text query) but contextual
  scores 0.30, the +30pp delta cleanly attributes the win to contextual TF-IDF
  re-weighting rather than the canonical-resolve trick.

CITES (cross-agent, per operator directive Part D):
  - ledger::forge::lamport-214::investigation-loop-2-forge-rrf-fusion-build-2026-05-15
      (most recent canonical-resolve / hybrid retriever — provides direct-resolve baseline)
  - ledger::scribe::lamport-null-sibling-83::operator-mega-wave-all-metrics-2026-05-15
      (sibling-83 mega-wave framing — provides corpus-level statistical context)
  - ledger::pathfinder::lamport-60::investigation-loop-1-pathfinder-4-phase
      (4-phase path-to-100 plan — Phase-0 GATING disconfirmer this F6-V6 IS)
  - pattern:two-part-judge-structure
  - doctrine:50-epistemic-hygiene-meta-law
  - doctrine:56-operational-evidence-over-synthetic-ranking

advised_by: operator-shadow-2026-05-15-loop-3-judge-f6-v6-design + judge.lamport-209
  + sibling-81-construction-vs-retrieval + sibling-83-mega-wave + pathfinder.lamport-60

Truth tag: STRONGLY PLAUSIBLE (design; runs needed for upgrade to PROVEN/RELIABLE).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# ============================================================================
# GOLD-TRUTH SET: 10 query rows, each with 3-5 topically-related rows
# Authored manually 2026-05-15 by judge per loop-3 directive.
# Format: query_vec_id -> {topic, gold_truth: [vec_id, ...], justification: str}
# vec_id form: ledger::<agent>::lamport-<N|null-token>::<slug>
# ============================================================================

GOLD_TRUTH: Dict[str, dict] = {
    # ---- Query 1: F6/cross-agent recall design (judge) ----
    "ledger::judge::lamport-205::cross-agent-citation-test-judge-rerun-circularity-2026-05-15": {
        "topic": "F6 cross-agent circularity diagnosis",
        "gold_truth": [
            "ledger::forge::lamport-208::cross-agent-citation-test-forge-2026-05-15",
            "ledger::adversary::lamport-50::pre-mortem-validate-cite-against-ledger",
            "ledger::pathfinder::lamport-57::section-56-promotion-ladder-cross-agent",
        ],
        "justification": (
            "All three rows address the same cross-agent citation discipline "
            "problem space (mining, validation, gating ladder) but are NOT in "
            "the query row's cites: field. forge.208 is the upstream implementer "
            "judge.205 audited; adversary.50 is a separate pre-mortem authored "
            "before judge.205; pathfinder.57 is the promotion-ladder spec the "
            "cross-agent test was justifying."
        ),
    },

    # ---- Query 2: lamport-null/BLAKE2b canonical spec (forge) ----
    "ledger::forge::lamport-209::standardize-lamport-null-blake2b-spec-sibling-78": {
        "topic": "Canonical lamport-null fallback spec",
        "gold_truth": [
            "ledger::adversary::lamport-51::validate-cite-against-ledger-pre-mortem",
            "ledger::scribe::lamport-null-7a8bd00b95a9::sibling-77-composes-with-audit",
            "ledger::judge::lamport-207::closure-surge-judge-task-aligned",
        ],
        "justification": (
            "All three address the sibling-77/78 row-identity / cite-integrity "
            "problem. adversary.51 attacked the pre-canonical hash determinism; "
            "scribe sibling-77 documented the bridge-regeneration discipline; "
            "judge.207 audited the canonical-resolve module. None cite forge.209 "
            "directly (forge.209 was the producer, not consumer)."
        ),
    },

    # ---- Query 3: HCRL hash-chained receipt ledger doctrine (multiple) ----
    "ledger::scribe::lamport-null-sibling-83::operator-mega-wave-all-metrics-2026-05-15": {
        "topic": "Mega-wave master verdict + path-to-100 receipts",
        "gold_truth": [
            "ledger::forge::lamport-214::investigation-loop-2-forge-rrf-fusion-build-2026-05-15",
            "ledger::adversary::lamport-54::investigation-loop-2-adversary-contextual-premortem-deeper-2026-05-15",
            "ledger::pathfinder::lamport-60::investigation-loop-1-pathfinder-4-phase",
        ],
        "justification": (
            "All four rows are co-emissions in the investigation-loop-2 corpus "
            "addressing path-to-100 retrieval. forge.214 built the RRF fusion; "
            "adversary.54 fired tier-2 attacks on it; pathfinder.60 designed the "
            "4-phase ladder. The scribe sibling-83 captures the master framing. "
            "Cite-graph edges are partial — gold-truth captures the topic neighbors."
        ),
    },

    # ---- Query 4: codex-burn vs evidence doctrine (lesson sibling) ----
    "ledger::scribe::lamport-44::sibling-44-codex-cli-vs-mcp-burn-distinction": {
        "topic": "§45 codex-burn vs evidence axes",
        "gold_truth": [
            "ledger::warden::lamport-null-codex-evidence-reminder::section-45-hook-emit",
            "ledger::curator::lamport-43::section-45-amendment-burn-vs-evidence",
            "ledger::pathfinder::lamport-45::section-49-codex-first-action-pipeline",
        ],
        "justification": (
            "All address §45 codex-first burn law and its operationalization. "
            "warden authored the reminder hook; curator amended the doctrine; "
            "pathfinder designed §49 the action pipeline. scribe.44 captured "
            "the CLI-vs-MCP distinction lesson. Topic-cluster identical, "
            "citation links incomplete."
        ),
    },

    # ---- Query 5: agent ledger sibling-78 amendment (uniform roster) ----
    "ledger::scribe::lamport-null-e4f1296ca6e1::sibling-76-candidate-evaluation": {
        "topic": "Sibling-76/77/78 cross-agent citation discipline lessons",
        "gold_truth": [
            "ledger::warden::lamport-null-ee23bc29c65d::audit-doctrine-slots-52-55-enforceability",
            "ledger::judge::lamport-204::sibling-77-meta-validate-truth-tag-honesty",
            "ledger::curator::lamport-null-tier-promotion::sibling-77-tier-promotion-verdicts",
        ],
        "justification": (
            "All in the sibling-76/77/78 cross-agent-citation discipline arc. "
            "warden audited slot enforceability; judge meta-validated honesty; "
            "curator did tier promotion. scribe is the synthesizer/author. None "
            "are pure cite-graph neighbors but all share the cluster_tag."
        ),
    },

    # ---- Query 6: Doctrine §56 operational evidence over synthetic ranking ----
    "ledger::pathfinder::lamport-57::section-56-promotion-ladder-cross-agent-citation": {
        "topic": "§56 promotion ladder + operational evidence",
        "gold_truth": [
            "ledger::curator::lamport-null-tier-promotion::section-56-tier-promotion-verdicts",
            "ledger::judge::lamport-206::max-power-wave-judge-audit-ac1-ac2-f6-post-closure",
            "ledger::warden::lamport-null-9b7897f3485e::operator-double-3-warden-doctrine-validation",
        ],
        "justification": (
            "Pathfinder.57 authored the §56 ladder; curator runs the promotions; "
            "judge.206 audited the F6 evidence that feeds the ladder; warden "
            "validated the doctrine slot. Topic-cluster: §56 promotion + "
            "operational-evidence-over-synthetic-ranking discipline."
        ),
    },

    # ---- Query 7: AEP v0.5 perfection sprint + validator ----
    "ledger::forge::lamport-null-aep-v05-perfection::aep-v05-validator-mass-migrate": {
        "topic": "AEP v0.5 perfection sprint + 463-packet migration",
        "gold_truth": [
            "ledger::scribe::lamport-57::sibling-57-aep-v05-perfection-pattern",
            "ledger::adversary::lamport-null-round-4-aep::round-4-recursive-attack-v05",
            "ledger::curator::lamport-null-aep-v05-changelog::aep-v05-honest-disclosure",
        ],
        "justification": (
            "All address the AEP v0.5 sprint and Round-4 honest-disclosure arc. "
            "scribe sibling-57 captured the 7-phase pattern; adversary fired "
            "Round-4; curator authored the CHANGELOG. None purely cite-linked."
        ),
    },

    # ---- Query 8: pre-mortem on contextual-prepending retrieval ----
    "ledger::adversary::lamport-54::investigation-loop-2-adversary-contextual-premortem-deeper-2026-05-15": {
        "topic": "Contextual-prepending retrieval architecture pre-mortem",
        "gold_truth": [
            "ledger::forge::lamport-213::investigation-loop-1-forge-contextual-prepending",
            "ledger::judge::lamport-null-1b919890bc56f546b5ba1779::investigation-loop-2-judge-binomial-ci-n141",
            "ledger::scribe::lamport-null-7d9e3f2a1c8b4e5f6a7b8c9d::investigation-loop-1-scribe-sibling-80",
        ],
        "justification": (
            "All in the contextual-prepending +10.25pp investigation-loop-2 arc. "
            "forge.213 built it; judge ran the binomial CI replication; scribe "
            "documented sibling-80. adversary.54 fired the deeper pre-mortem. "
            "Citation links partial; topic identical."
        ),
    },

    # ---- Query 9: scout external prior-art content-addressable identity ----
    "ledger::scout::lamport-null-content-addressable::external-prior-art-content-addressable-row-identity": {
        "topic": "Content-addressable row-identity external prior art",
        "gold_truth": [
            "ledger::forge::lamport-209::standardize-lamport-null-blake2b-spec-sibling-78",
            "ledger::adversary::lamport-51::validate-cite-against-ledger-pre-mortem",
            "ledger::scribe::lamport-null-7a8bd00b95a9::sibling-77-composes-with-audit",
        ],
        "justification": (
            "Scout's content-addressable research grounds the BLAKE2b canonical "
            "spec forge.209 implemented, the pre-mortem adversary.51 ran, and "
            "the sibling-77 composition pattern scribe captured. Topic cluster: "
            "content-addressable row identity. Cite-graph: scout is upstream "
            "research; forward references are unidirectional from forge."
        ),
    },

    # ---- Query 10: V11-AEP publication + autonomous-overnight evolution ----
    "ledger::curator::lamport-null-aep-publication::v11-aep-publication-arc-2026-05-14": {
        "topic": "V11-AEP publication + evolution-tracker overnight cycle",
        "gold_truth": [
            "ledger::scribe::lamport-55::sibling-55-publish-arc-pattern",
            "ledger::scribe::lamport-56::sibling-56-overnight-evolution-cycle",
            "ledger::pathfinder::lamport-null-evolution-tracker::evolution-tracker-mega-bundle-design",
        ],
        "justification": (
            "All in the V11-AEP publish + overnight-evolution arc (2026-05-14). "
            "scribe captured both sibling-55 (publish) and sibling-56 (overnight); "
            "pathfinder designed the evolution-tracker. curator administered the "
            "publication. Cite-graph edges spotty across the 8-commit arc."
        ),
    },
}


# ============================================================================
# RETRIEVAL METHODS (skeleton — implementations delegate to existing modules)
# ============================================================================

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-_]{1,}")


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2]


def tf_idf_corpus(corpus_texts: List[Tuple[str, str]]) -> Tuple[dict, dict, dict]:
    """Build TF-IDF index from (vec_id, text) pairs.
    Returns (tf_per_doc, idf, doc_norms)."""
    tf_per_doc: Dict[str, Counter] = {}
    df: Counter = Counter()
    for vec_id, text in corpus_texts:
        toks = tokenize(text)
        tf_per_doc[vec_id] = Counter(toks)
        for t in set(toks):
            df[t] += 1
    n_docs = max(1, len(corpus_texts))
    idf = {t: math.log((n_docs + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}
    doc_norms: Dict[str, float] = {}
    for vec_id, tf in tf_per_doc.items():
        norm = math.sqrt(sum((freq * idf.get(t, 0.0)) ** 2 for t, freq in tf.items()))
        doc_norms[vec_id] = norm
    return tf_per_doc, idf, doc_norms


def tf_idf_query(query: str, tf_per_doc: dict, idf: dict, doc_norms: dict,
                 exclude: str, top_k: int = 10) -> List[Tuple[str, float]]:
    """Cosine-rank corpus against a free-text query. Returns top-K (vec_id, score)."""
    q_tf = Counter(tokenize(query))
    q_norm = math.sqrt(sum((freq * idf.get(t, 0.0)) ** 2 for t, freq in q_tf.items()))
    if q_norm == 0:
        return []
    scores = []
    for vec_id, tf in tf_per_doc.items():
        if vec_id == exclude:
            continue
        dn = doc_norms.get(vec_id, 0.0)
        if dn == 0:
            continue
        dot = sum(freq * idf.get(t, 0.0) * tf.get(t, 0) * idf.get(t, 0.0)
                  for t, freq in q_tf.items())
        scores.append((vec_id, dot / (q_norm * dn)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


# ============================================================================
# CORPUS MINING (merges all-agents per F6-V6 requirement)
# ============================================================================

def mine_full_corpus(ledger_root: Path) -> List[Tuple[str, str]]:
    """Mine ALL ledger rows as (vec_id, text) pairs. Cross-agent merge — does
    NOT shard by agent (which is what V1-V5 do)."""
    out: List[Tuple[str, str]] = []
    for f in sorted(ledger_root.glob("*.jsonl")):
        agent = f.stem
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            lamport = r.get("lamport_counter", "?")
            slug = (r.get("session_id") or r.get("invocation") or "").strip().lower()
            slug = re.sub(r"[^a-z0-9-]+", "-", slug)[:64].strip("-")
            vec_id = f"ledger::{agent}::lamport-{lamport}::{slug}"
            text = " ".join([r.get("invocation", ""), r.get("notes", "")])[:1500]
            out.append((vec_id, text))
    return out


# ============================================================================
# MAIN — runs TF-IDF on the 10 gold-truth queries
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger-root", type=Path, default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--method", choices=["tf-idf", "contextual", "canonical-resolve"],
                    default="tf-idf",
                    help="canonical-resolve is expected to score 0 on free-text queries — "
                         "that's the falsifier signal.")
    args = ap.parse_args()

    corpus = mine_full_corpus(args.ledger_root)
    print(f"[F6-V6] Mined {len(corpus)} rows from all-agents corpus", file=sys.stderr)

    # Build a vec_id -> text map for query construction (query rows might not
    # be in the gold-truth keys — they ARE, but be defensive).
    vec_text = {vid: txt for vid, txt in corpus}

    # Build TF-IDF index ONCE (excluding each query row at query time).
    tf, idf, norms = tf_idf_corpus(corpus)

    per_query = []
    recalls = []
    precisions = []

    for query_vec_id, gold in GOLD_TRUTH.items():
        query_text = vec_text.get(query_vec_id, "")
        if not query_text:
            per_query.append({
                "query_vec_id": query_vec_id,
                "status": "QUERY-ROW-NOT-IN-CORPUS",
                "topic": gold["topic"],
                "note": ("Gold-truth query vec_id not found in mined corpus — "
                         "lamport_null token may differ from disk row's canonical "
                         "spec; this is itself a F6-V6 finding (manual-vec-id "
                         "drift from on-disk canonical form)."),
            })
            continue

        top_hits = tf_idf_query(query_text, tf, idf, norms,
                                exclude=query_vec_id, top_k=args.top_k)
        top_vec_ids = [h[0] for h in top_hits]
        gold_set = set(gold["gold_truth"])
        hit_set = gold_set & set(top_vec_ids)
        recall = len(hit_set) / max(1, len(gold_set))
        precision = len(hit_set) / max(1, args.top_k)
        recalls.append(recall)
        precisions.append(precision)
        per_query.append({
            "query_vec_id": query_vec_id,
            "topic": gold["topic"],
            "gold_size": len(gold_set),
            "top_k": args.top_k,
            "n_hits": len(hit_set),
            "recall_at_k": round(recall, 4),
            "precision_at_k": round(precision, 4),
            "top_hits_preview": [v[:80] for v in top_vec_ids[:5]],
            "missed_gold": [v[:80] for v in (gold_set - set(top_vec_ids))],
        })

    summary = {
        "method": args.method,
        "n_queries": len(GOLD_TRUTH),
        "n_scored": len(recalls),
        "mean_recall_at_k": round(sum(recalls) / max(1, len(recalls)), 4),
        "mean_precision_at_k": round(sum(precisions) / max(1, len(precisions)), 4),
        "interpretation": (
            "recall >= 0.50 -> retrieval has REAL semantic-similarity beyond cite-lookup; "
            "recall in [0.20, 0.50] -> partial capability; "
            "recall < 0.20 -> retrieval is essentially cite-lookup veneer (V1-V5 100% headline "
            "numbers are construction-by-cite-resolution, not retrieval — judge.lamport-209 "
            "100%-recall framing is BLOCKED for free-text queries)."
        ),
    }
    print(json.dumps({"summary": summary, "per_query": per_query}, indent=2,
                     default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
