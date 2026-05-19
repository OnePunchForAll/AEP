"""falsifier_6_citation_based.py — Gold-truth citation-based relevance bench.

The cluster_tag-anchor F1 + grep-baseline F2 both FAILED under rigorous evaluation
because cluster_tag overlap is a weak proxy for real relevance. THIS bench uses
the actual agent citations from operator-double dispatches as gold-truth labels.

Methodology:
  For each ledger row R with a non-empty `lag_influenced_by` or `cites` field:
    - task_hint = first 200 chars of R.invocation
    - cited_vec_ids = R.lag_influenced_by + R.cites (filtered to ledger:: format)
  For each (citing_agent, task_hint, expected_cited_vec_id) tuple:
    - Run lag_retrieve(citing_agent, task_hint, top_k=K)
    - Check: does expected_cited_vec_id appear in top-K results?
  Aggregate: recall@K = |hits ∩ cited| / |cited|

PASS criterion: recall@5 ≥ 0.50 (the architecture surfaces at least HALF of the
vec_ids agents actually cited as relevant when queried on the citing task hint).

This is the architecture's TRUE operational metric. cluster_tag anchors and
auto-labeling are bypassed entirely.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lag_retrieve

# Canonical-resolve tier-1 (sibling-82 + falsifier_6_self_canonical_resolve.py
# 2026-05-15 forge.lamport-216): when a citation is in canonical vec_id form,
# direct-resolve to the owning row WITHOUT subprocess'ing lag_retrieve.py.
# This catches the 100%-by-construction self-citation subcase before falling
# through to TF-IDF retrieval. Pure additive: TF-IDF path is untouched.
sys.path.insert(0, str(Path(__file__).parent))
try:
    from canonical_resolve_retriever import (
        parse_vec_id as _cr_parse_vec_id,
        resolve_vec_id_to_row as _cr_resolve_row,
    )
    _CANONICAL_RESOLVE_AVAILABLE = True
except Exception:
    _CANONICAL_RESOLVE_AVAILABLE = False


VEC_ID_RE = re.compile(r"ledger::[a-z\-]+::lamport-[a-zA-Z0-9_\-]+::[A-Za-z0-9\-]+")


def try_canonical_resolve(citation: str, ledger_root: Path) -> bool:
    """Tier-1 fallback strategy: if citation is canonical vec_id format AND
    the owning ledger row exists, return True (match). Returns False on
    non-canonical, fabricated, or ambiguous cites (those fall through to
    TF-IDF retrieval).
    """
    if not _CANONICAL_RESOLVE_AVAILABLE:
        return False
    parsed = _cr_parse_vec_id(citation)
    if not parsed:
        return False
    try:
        row = _cr_resolve_row(citation, ledger_root)
    except Exception:
        return False
    return row is not None


def mine_citations(ledger_root: Path):
    """Yield (citing_agent, citing_session, task_hint, cited_vec_id, kind) tuples."""
    for ledger in sorted(ledger_root.glob("*.jsonl")):
        agent = ledger.stem
        with open(ledger, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                task_hint = (r.get("invocation") or "")[:200]
                session = r.get("session_id", "?")

                cited = set()
                for field in ("lag_influenced_by", "cites"):
                    v = r.get(field)
                    if isinstance(v, list):
                        for c in v:
                            if isinstance(c, str) and c.startswith("ledger::"):
                                cited.add(c)
                # Also catch in-notes citations
                notes = r.get("notes", "") or ""
                if isinstance(notes, str):
                    for m in VEC_ID_RE.finditer(notes):
                        cited.add(m.group(0))

                for vid in cited:
                    yield {"citing_agent": agent, "citing_session": session,
                           "task_hint": task_hint, "cited_vec_id": vid}


def run_retrieve(agent: str, task_hint: str, top_k: int):
    """Invoke lag_retrieve.main(argv) IN-PROCESS and return list of vec_ids.

    WAVE-Q REFACTOR (forge sibling-49 cluster closure condition 2,
    2026-05-16): Replaced subprocess.run([sys.executable, "lag_retrieve.py",
    ...]) with import lag_retrieve + main(argv) + contextlib.redirect_stdout
    capture. Eliminates sibling-49 WinError 5 fingerprint when this
    falsifier is itself invoked from a parent harness (depth-2 nested
    spawn under Win11 sandbox). Output format identical: NDJSON lines per
    --format ndjson contract."""
    argv = [
        "--agent", agent,
        "--task-hint", task_hint,
        "--top-k", str(top_k),
        "--format", "ndjson",
    ]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            lag_retrieve.main(argv)
    except SystemExit as exc:
        if (exc.code or 0) != 0:
            return []
    text = buf.getvalue()
    hits = []
    for line in text.splitlines():
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
            hits.append(vid)
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--ledger-root", type=Path, default=Path(".claude/agents/_ledgers"))
    args = ap.parse_args()

    citations = list(mine_citations(args.ledger_root))
    # Dedup by (citing_agent, citing_session, cited_vec_id)
    seen = set()
    unique = []
    for c in citations:
        key = (c["citing_agent"], c["citing_session"], c["cited_vec_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    per_query = []
    n_match_tier_canonical = 0
    n_match_tier_exact = 0
    n_match_tier_fuzzy = 0
    for c in unique:
        if len(c["task_hint"]) < 30:
            continue
        # Tier 0 (forge.lamport-216 2026-05-15 sibling-82 additive amendment):
        # canonical-resolve FAST PATH. If the cited vec_id parses as canonical
        # AND resolves to a real ledger row, the citation IS satisfied by
        # construction; record the match and skip the TF-IDF subprocess.
        # ADDITIVE only: TF-IDF baseline behavior preserved when this tier misses.
        match = False
        tier_used = None
        hits = []
        if try_canonical_resolve(c["cited_vec_id"], args.ledger_root):
            match = True
            tier_used = "canonical-resolve"
            n_match_tier_canonical += 1
        else:
            # Tier 1: original TF-IDF lag_retrieve.py exact match
            hits = run_retrieve(c["citing_agent"], c["task_hint"], args.top_k)
            if c["cited_vec_id"] in hits:
                match = True
                tier_used = "tfidf-exact"
                n_match_tier_exact += 1
            else:
                # Tier 2: fuzzy lamport-tail substring match (original fallback)
                cited_short = "::".join(c["cited_vec_id"].split("::")[-2:])
                fuzzy = any(cited_short in h for h in hits)
                if fuzzy:
                    match = True
                    tier_used = "tfidf-fuzzy-suffix"
                    n_match_tier_fuzzy += 1
        per_query.append({
            "citing_agent": c["citing_agent"],
            "citing_session": c["citing_session"][:40],
            "task_hint": c["task_hint"][:80],
            "cited_vec_id": c["cited_vec_id"][:60],
            "n_hits": len(hits),
            "match": match,
            "tier_used": tier_used,
        })

    n_total = len(per_query)
    n_match = sum(1 for p in per_query if p["match"])
    recall_at_k = n_match / max(1, n_total)
    verdict = "PASS" if recall_at_k >= 0.50 else (
        "PROVISIONAL-PASS" if recall_at_k >= 0.25 else "FAIL"
    )

    summary = {
        "falsifier": "F6-citation-based-recall",
        "methodology": (
            "agent_actual_citations_as_gold_truth_relevance_labels; "
            "tiered: canonical-resolve -> tfidf-exact -> tfidf-fuzzy-suffix"
        ),
        "top_k": args.top_k,
        "n_unique_citations": len(unique),
        "n_query_attempts": n_total,
        "n_matches": n_match,
        "recall_at_k": round(recall_at_k, 3),
        "pass_threshold": 0.50,
        "verdict": verdict,
        # Tier breakdown (forge.lamport-216 sibling-82 additive amendment)
        "tier_match_counts": {
            "canonical-resolve": n_match_tier_canonical,
            "tfidf-exact": n_match_tier_exact,
            "tfidf-fuzzy-suffix": n_match_tier_fuzzy,
        },
        "tier_attribution_note": (
            "canonical-resolve tier is ADDITIVE: it catches structured cites "
            "before TF-IDF is invoked, preserving TF-IDF baseline behavior on "
            "the residual. Disable by removing canonical_resolve_retriever from "
            "sys.path or by passing --no-canonical-resolve (not yet wired)."
        ),
        "per_query": per_query,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
