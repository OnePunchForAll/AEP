"""falsifier_6_task_aligned.py — Task-alignment-filtered F6 cross-agent recall.

Purpose (final-round-forge-task-aligned-harness-2026-05-15):
  Pathfinder G2 Steps 2+3 collapsed into a single immediate execution. Address
  the closure-surge prior finding (recall ≈ 0 on raw cross-agent cites): is the
  bottleneck CITATION DISCIPLINE (citing rows whose task_hint has nothing to do
  with the cited row), or RETRIEVAL ARCHITECTURE (LAG fails even when there IS
  task-alignment between citing context and cited content)?

Methodology:
  1. Mine cross-agent cites via mine_cross_agent_citations() (reused from
     falsifier_6_cross_agent_cites — same H1+H2 cached strict-UTF-8 reads).
  2. For each (citing, cited, task_hint, citation):
       a. Locate the cited row in the cited agent's ledger (by lamport token,
          including the canonical lamport-null-<blake2b-prefix> form via
          compute_null_lamport_token — eat-own-dogfood per sibling-78).
       b. cited_text = invocation + " " + notes  (first 1000 chars combined)
       c. cosine = TF-IDF cosine(task_hint, cited_text) using a hand-rolled
          TF-IDF over the union vocabulary of the two strings (sklearn-free
          so no extra dependency burden on the harness).
  3. Filter: keep only cites with cosine ≥ 0.30 → the task-aligned subset.
  4. Run the same F6 retrieval test (lag_retrieve from the CITED agent's index
     with the citing task_hint, top_k=5) on BOTH the full set AND the filtered
     subset.
  5. Compare recall_full vs recall_task_aligned; report recall_lift.

Signal interpretation (operator directive):
  * N_task_aligned ≥ 4 AND recall_lift ≥ 0.10  → STRONG: retrieval architecture
    IS task-alignment-sensitive. Citation discipline is the dominant lever.
  * N_task_aligned < 4                          → INSUFFICIENT-DATA. Need more
    task-aligned cross-agent cites to discriminate the two hypotheses.
  * N_task_aligned ≥ 4 AND recall_lift ≤ 0     → bottleneck IS retrieval
    architecture (per closure-surge prior finding); citation discipline is NOT
    the dominant lever — improving cite quality won't move recall numbers.

Cites:
  - pathfinder.lamport-45 — V7 mega-html plan, G2 detailed ladder author.
  - judge.lamport-206     — F6 post-AC1+AC2 audit; verified-cite gating.
  - adversary.lamport-51  — H1+H2 pre-mortem on validate_cite_against_ledger.

Truth tag: STRONGLY PLAUSIBLE (forge.lamport-211 2026-05-15;
sibling-78-aligned, schema-additive).
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

# Eat-own-dogfood: canonical null-lamport spec from sibling-78.
from lamport_null_fallback import compute_null_lamport_token

# Reuse mining + retrieval helpers from the cross-agent F6 (single-writer
# discipline: do NOT re-implement; delegate via import per §50 EH meta-law).
from falsifier_6_cross_agent_cites import (
    CANONICAL_VEC_ID_RE,
    _load_ledger_cached,
    mine_cross_agent_citations,
    run_retrieve,
    match_citation,
)


# ----------------------------------------------------------------------------
# TF-IDF cosine (hand-rolled — sklearn-free)
# ----------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


def tokenize(text: str) -> list[str]:
    """Lower-case alpha-leading tokens of length >= 2; preserves intra-token
    hyphens (so 'cross-agent' is one token, not two)."""
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 2]


def tfidf_cosine(text_a: str, text_b: str) -> float:
    """Compute TF-IDF cosine between two strings using a 2-document corpus.

    Procedure:
      * tokenize both strings
      * vocab = union of tokens
      * tf(t, d)  = count(t in d) / |d|
      * df(t)     = number of docs containing t (∈ {1, 2})
      * idf(t)    = ln((1 + N) / (1 + df)) + 1  (smoothed; N=2)
      * tfidf(t,d)= tf(t,d) * idf(t)
      * cosine    = (a·b) / (|a| * |b|)

    Returns 0.0 on empty input or zero-norm vector.
    """
    toks_a = tokenize(text_a)
    toks_b = tokenize(text_b)
    if not toks_a or not toks_b:
        return 0.0

    counts_a = Counter(toks_a)
    counts_b = Counter(toks_b)
    n_a = len(toks_a)
    n_b = len(toks_b)
    vocab = set(counts_a) | set(counts_b)
    n_docs = 2

    vec_a: dict[str, float] = {}
    vec_b: dict[str, float] = {}
    for term in vocab:
        df = (1 if term in counts_a else 0) + (1 if term in counts_b else 0)
        idf = math.log((1 + n_docs) / (1 + df)) + 1.0
        if term in counts_a:
            vec_a[term] = (counts_a[term] / n_a) * idf
        if term in counts_b:
            vec_b[term] = (counts_b[term] / n_b) * idf

    dot = sum(vec_a.get(t, 0.0) * vec_b.get(t, 0.0) for t in vocab)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ----------------------------------------------------------------------------
# Cited-row lookup (locate the row in the cited agent's ledger)
# ----------------------------------------------------------------------------

def find_cited_row(citation: str, ledger_root: Path) -> dict | None:
    """Return the cited ledger row dict, or None if not locatable.

    Supports both numeric lamport-N and the canonical lamport-null-<prefix>
    fallback per sibling-78 (delegates to compute_null_lamport_token).
    """
    m = CANONICAL_VEC_ID_RE.search(citation)
    if not m:
        return None
    agent_name = m.group(1)
    lamport_start = citation.find("lamport-")
    if lamport_start < 0:
        return None
    slug_start = citation.find("::", lamport_start)
    if slug_start < 0:
        return None
    lamport_token = citation[lamport_start:slug_start]

    ledger_path = ledger_root / f"{agent_name}.jsonl"
    cached = _load_ledger_cached(ledger_path)
    if not cached["exists"] or cached["read_error"]:
        return None
    rows = cached["rows"]

    if lamport_token.startswith("lamport-null-"):
        for r in rows:
            if r.get("lamport_counter") is not None:
                continue
            if compute_null_lamport_token(r) == lamport_token:
                return r
        return None

    try:
        target = int(lamport_token[len("lamport-"):])
    except ValueError:
        return None
    matches = [r for r in rows if r.get("lamport_counter") == target]
    if len(matches) == 1:
        return matches[0]
    # Ambiguous (>1) or absent (0) — return None; gate excludes these
    return None


def cited_row_text(row: dict) -> str:
    """Compose the cited row's text basis for cosine: invocation + ' ' + notes,
    truncated to 1000 chars to bound the TF-IDF cost on degenerate-long rows."""
    inv = (row.get("invocation") or "")
    notes = (row.get("notes") or "")
    return (inv + " " + notes)[:1000]


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--cosine-threshold", type=float, default=0.30,
                    help="Min TF-IDF cosine(task_hint, cited.invocation+notes) "
                         "to qualify as task-aligned (default 0.30).")
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    args = ap.parse_args()

    raw = list(mine_cross_agent_citations(args.ledger_root))
    # Dedup by (citing_agent, cited_agent, citation) — same as cross-agent F6
    seen = set()
    unique = []
    for c in raw:
        key = (c["citing_agent"], c["cited_agent"], c["citation"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    n_total = len(unique)
    if n_total == 0:
        out = {
            "falsifier": "F6-task-aligned",
            "methodology": "tfidf-cosine-filter-on-cross-agent-cites",
            "top_k": args.top_k,
            "cosine_threshold": args.cosine_threshold,
            "n_cross_agent_total": 0,
            "n_task_aligned": 0,
            "verdict": "INSUFFICIENT-DATA",
            "finding": "Zero cross-agent cites in vec_id form; task-alignment "
                       "filter cannot be applied. See F6-cross-agent-cites for "
                       "the upstream remediation.",
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    per_query = []
    for c in unique:
        cited_row = find_cited_row(c["citation"], args.ledger_root)
        if cited_row is None:
            # Cannot align if we cannot locate the cited row — exclude from the
            # task-aligned subset, but record it for transparency.
            per_query.append({
                "citing_agent": c["citing_agent"],
                "cited_agent": c["cited_agent"],
                "task_hint": c["task_hint"][:80],
                "citation": c["citation"][:80],
                "cosine": None,
                "task_aligned": False,
                "match_in_cited_index": None,
                "alignment_status": "cited-row-unresolvable",
            })
            continue

        cited_text = cited_row_text(cited_row)
        cos = tfidf_cosine(c["task_hint"], cited_text)
        is_aligned = cos >= args.cosine_threshold

        # F6 retrieval test (only on resolvable rows — needed for a fair
        # full-vs-aligned recall comparison).
        hits = run_retrieve(c["cited_agent"], c["task_hint"], args.top_k)
        match_cited = match_citation(c["citation"], hits)

        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "task_hint": c["task_hint"][:80],
            "citation": c["citation"][:80],
            "cited_lamport": cited_row.get("lamport_counter"),
            "cosine": round(cos, 4),
            "task_aligned": is_aligned,
            "match_in_cited_index": match_cited,
            "alignment_status": "resolved",
        })

    # Recall on full resolvable set + on task-aligned subset
    resolvable = [p for p in per_query if p["alignment_status"] == "resolved"]
    n_resolvable = len(resolvable)
    n_match_full = sum(1 for p in resolvable if p["match_in_cited_index"])
    recall_full = (n_match_full / n_resolvable) if n_resolvable else 0.0

    aligned = [p for p in resolvable if p["task_aligned"]]
    n_task_aligned = len(aligned)
    n_match_aligned = sum(1 for p in aligned if p["match_in_cited_index"])
    recall_task_aligned = (n_match_aligned / n_task_aligned) if n_task_aligned else 0.0
    recall_lift = recall_task_aligned - recall_full

    if n_task_aligned < 4:
        verdict = "INSUFFICIENT-DATA"
        finding = (
            f"n_task_aligned={n_task_aligned} (<4 floor). Cannot discriminate "
            f"between citation-discipline-bottleneck and retrieval-architecture-"
            f"bottleneck hypotheses. Surface ≥4 cross-agent cites whose "
            f"task_hint TF-IDF-correlates ≥{args.cosine_threshold} with cited "
            f"row text, then re-run."
        )
        signal = "INSUFFICIENT-DATA"
    elif recall_lift >= 0.10:
        verdict = "STRONG-SIGNAL"
        finding = (
            f"recall_lift={recall_lift:+.3f} on n_task_aligned={n_task_aligned} "
            f"(threshold ≥+0.10): retrieval architecture IS task-alignment-"
            f"sensitive. Citation discipline is the dominant lever for the "
            f"closure-surge bottleneck. Improving cite quality (task_hint that "
            f"semantically resembles the cited row) will move recall numbers."
        )
        signal = "RETRIEVAL-IS-TASK-ALIGNMENT-SENSITIVE"
    elif recall_lift <= 0.0:
        verdict = "ARCHITECTURE-BOTTLENECK"
        finding = (
            f"recall_lift={recall_lift:+.3f} on n_task_aligned={n_task_aligned}: "
            f"task-aligned cites do NOT outperform unaligned ones. The "
            f"closure-surge bottleneck IS retrieval architecture, not citation "
            f"discipline. Improving cite quality will NOT move recall numbers; "
            f"the lever is the retrieval index itself."
        )
        signal = "RETRIEVAL-ARCHITECTURE-BOTTLENECK"
    else:
        verdict = "WEAK-SIGNAL"
        finding = (
            f"recall_lift={recall_lift:+.3f} on n_task_aligned={n_task_aligned}: "
            f"directional but below ≥+0.10 STRONG threshold. Retrieval may be "
            f"weakly task-alignment-sensitive; gather more aligned cites "
            f"before declaring direction."
        )
        signal = "WEAK-DIRECTIONAL"

    cosines_only = [p["cosine"] for p in resolvable if p["cosine"] is not None]
    summary = {
        "falsifier": "F6-task-aligned",
        "methodology": "tfidf-cosine-filter-on-cross-agent-cites",
        "top_k": args.top_k,
        "cosine_threshold": args.cosine_threshold,
        "n_cross_agent_total": n_total,
        "n_resolvable": n_resolvable,
        "n_unresolvable": n_total - n_resolvable,
        "n_task_aligned": n_task_aligned,
        "n_match_full": n_match_full,
        "n_match_task_aligned": n_match_aligned,
        "recall_full": round(recall_full, 4),
        "recall_task_aligned": round(recall_task_aligned, 4),
        "recall_lift": round(recall_lift, 4),
        "cosine_distribution": {
            "min": round(min(cosines_only), 4) if cosines_only else None,
            "median": round(sorted(cosines_only)[len(cosines_only) // 2], 4)
                      if cosines_only else None,
            "max": round(max(cosines_only), 4) if cosines_only else None,
            "n_above_threshold": n_task_aligned,
        },
        "verdict": verdict,
        "signal": signal,
        "finding": finding,
        "per_query": per_query[:50],
        "cites": [
            "ledger::pathfinder::lamport-45::v7-mega-html-plan-decomposed-15-tasks",
            "ledger::judge::lamport-206::f6-post-ac1-ac2-audit",
            "ledger::adversary::lamport-51::validate-cite-against-ledger-premortem",
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
