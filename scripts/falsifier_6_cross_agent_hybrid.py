"""falsifier_6_cross_agent_hybrid.py — Hybrid retrieval combining canonical-
resolve (strict) + slug/session-id soft-match fallback + contextual retrieval.

Tiers (in order of attempt):
1. **CANONICAL RESOLVE** — strict vec_id → row lookup via forge's lamport_null
   spec. 100% precision on verified canonical cites.
2. **SLUG / SESSION SOFT-MATCH** — for cites that "fabricate" only because of
   spec-drift (pre-canonical-spec emission), recover by matching on the slug
   component against session_id or invocation substring.
3. **CONTEXTUAL RETRIEVAL** — final fallback for non-canonical or malformed
   cites; uses lag_retrieve_contextual.py output.

Goal per operator directive (2026-05-15): push full-denominator recall toward
1.0 (100%) by recovering spec-drift fabrications without losing AC1+AC2
integrity gates (truly fabricated rows still fail).

WAVE-Q REFACTOR (forge sibling-49 cluster closure condition 2, 2026-05-16):
The tier-3 contextual fallback no longer subprocess.runs
lag_retrieve_contextual.py; it imports + calls main(argv) with stdout
capture. Eliminates sibling-49 WinError 5 fingerprint when this falsifier
itself is invoked from a parent harness (depth-2 nested-spawn).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from falsifier_6_cross_agent_cites import (
    mine_cross_agent_citations,
    validate_cite_against_ledger,
    match_citation,
)
from canonical_resolve_retriever import (
    resolve_vec_id_to_row,
    parse_vec_id,
)
import lag_retrieve_contextual


def soft_match_by_slug(citation: str, ledger_root: Path) -> dict | None:
    """Recover spec-drift cites: cite points to real row but hash differs.
    Match by (agent, slug) against (session_id, invocation_substring)."""
    parsed = parse_vec_id(citation)
    if not parsed:
        return None
    agent, _lamport_token, slug = parsed
    ledger_path = ledger_root / f"{agent}.jsonl"
    if not ledger_path.exists():
        return None
    slug_lower = slug.lower()
    # Normalize slug separators
    slug_words = set(re.split(r"[-_:]+", slug_lower))
    slug_words.discard("")
    best_row = None
    best_score = 0
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        session = (r.get("session_id") or "").lower()
        invocation = (r.get("invocation") or "").lower()
        notes = (r.get("notes") or "").lower()
        haystack = " ".join([session, invocation, notes])
        haystack_words = set(re.split(r"[-_:\s,.;()\[\]{}]+", haystack))
        haystack_words.discard("")
        common = slug_words & haystack_words
        # Score = fraction of slug words found in row's text fields
        score = len(common) / max(1, len(slug_words))
        if score > best_score and score >= 0.5:
            best_score = score
            best_row = r
    return best_row


def run_contextual_retrieve(agent: str, task_hint: str, top_k: int):
    """Wave-Q in-process replacement for prior subprocess.run shell-out.

    Captures stdout from lag_retrieve_contextual.main(argv) via
    contextlib.redirect_stdout. Eliminates sibling-49 WinError 5 fingerprint
    at depth-2 nested-spawn under Win11 sandbox. NDJSON parse identical to
    subprocess path (--format ndjson contract preserved)."""
    argv = [
        "--agent", agent,
        "--task-hint", task_hint,
        "--top-k", str(top_k),
        "--format", "ndjson",
    ]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            lag_retrieve_contextual.main(argv)
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


def hybrid_resolve(citation: str, task_hint: str, ledger_root: Path,
                   top_k: int = 5) -> tuple[bool, str]:
    """Returns (matched, tier) where tier names the recovery method.

    Adversary AC-tier2-soft-match-inflation closure (sibling-82 amendment):
    Tier 2 ONLY counts when validate_cite_against_ledger returns 'verified'
    or 'ambiguous'. Fabricated cites are NOT eligible for tier-2 rescue
    because adversary demonstrated tier-2 reassigns fabricated cites to
    unrelated rows sharing vocabulary (metric game)."""
    # Tier 1: strict canonical resolve
    parsed = parse_vec_id(citation)
    if parsed:
        row = resolve_vec_id_to_row(citation, ledger_root)
        if row is not None:
            return (True, "tier1-canonical-resolve")
    # Tier 2: slug/session soft-match (ONLY for VERIFIED cites with spec-drift)
    if parsed:
        validation = validate_cite_against_ledger(citation, ledger_root)
        if validation["status"] == "verified":
            row = soft_match_by_slug(citation, ledger_root)
            if row is not None:
                return (True, "tier2-slug-session-soft-match-verified-only")
    # Tier 3: contextual retrieval (final fallback)
    if parsed:
        agent = parsed[0]
        hits = run_contextual_retrieve(agent, task_hint, top_k)
        if match_citation(citation, hits):
            return (True, "tier3-contextual-retrieval")
    return (False, "miss-all-tiers")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
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

    tier_counts = {"tier1-canonical-resolve": 0,
                   "tier2-slug-session-soft-match-verified-only": 0,
                   "tier3-contextual-retrieval": 0,
                   "miss-all-tiers": 0}
    per_query = []
    n_match = 0
    for c in unique:
        matched, tier = hybrid_resolve(c["citation"], c["task_hint"],
                                        args.ledger_root, args.top_k)
        tier_counts[tier] += 1
        if matched:
            n_match += 1
        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "citation": c["citation"][:80],
            "match": matched,
            "tier": tier,
        })

    n_total = len(per_query)
    recall_hybrid = n_match / n_total

    summary = {
        "falsifier": "F6-cross-agent-cites-recall-HYBRID-3-TIER",
        "methodology": "tier1-canonical-resolve + tier2-slug-soft-match + tier3-contextual-retrieval",
        "top_k": args.top_k,
        "n_cross_agent_citations": n_total,
        "n_match_hybrid": n_match,
        "recall_hybrid_full_denominator": round(recall_hybrid, 4),
        "tier_counts": tier_counts,
        "pass_threshold_full": 0.50,
        "verdict": "PASS" if recall_hybrid >= 0.50 else (
                   "PROVISIONAL-PASS" if recall_hybrid >= 0.10 else "FAIL"),
        "per_query": per_query[:30],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main() or 0)
