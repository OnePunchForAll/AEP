"""falsifier_6_self_canonical_resolve.py — F6 SELF-emitted recall using
canonical-resolve retriever (direct vec_id -> row lookup; mirror of
sibling-82's hybrid tier-1 applied to the self-citation subcorpus).

Self-emitted = citation in agent A's ledger row points to a vec_id ALSO
owned by agent A (citing_agent == cited_agent). This is the original F6
"self-signal-circularity-risk" corpus per scout op-double-evolution.

Predicted result:
  recall_self_verified_only    = 1.0  (by construction; canonical-resolve
                                       parses agent + lamport_token and
                                       direct-looks-up the owning ledger row;
                                       every verified canonical cite resolves
                                       to the exact row it points to.)
  recall_self_full_denominator = n_verified / n_total
                                 (fraction of self-cites that pass AC1+AC2
                                  closure; fabricated and ambiguous cites
                                  cannot resolve and correctly fail.)

Composes with:
  - sibling-78 (AC1+AC2 + H1..H5 + AC3..AC7 ledger-validation closure)
  - sibling-82 (3-tier hybrid: canonical-resolve + slug-soft + contextual)
  - falsifier_6_cross_agent_canonical_resolve.py (cross-agent twin)

Honest framing: 100% recall on verified canonical self-citations is BY
CONSTRUCTION; we bypass retrieval and exploit canonical-vec-id structure.
This is the SAME structurally-different-problem framing as sibling-82
applied to the self subcorpus: not "retrieval beats baseline" but
"structured citation IDs make recall a closed-form lookup."
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from canonical_resolve_retriever import (
    CANONICAL_VEC_ID_RE,
    parse_vec_id,
    resolve_vec_id_to_row,
)


# Reuse cross-agent F6's hardened validator for AC1+AC2+H1..H5+AC3..AC7
# closure. validate_cite_against_ledger covers all sibling-78 attack surface.
from falsifier_6_cross_agent_cites import (
    validate_cite_against_ledger,
    INFORMAL_PATTERNS,
    CANONICAL_10,
    MAX_NOTES_SCAN_BYTES,
    MAX_INFORMAL_CITES_PER_ROW,
    MAX_CANONICAL_CITES_PER_ROW,
    _load_ledger_cached,
)


def mine_self_emitted_citations(ledger_root: Path):
    """Yield self-emitted citation tuples: agent A cites a vec_id owned by A.

    Mirrors mine_cross_agent_citations but keeps ONLY rows where citing_agent
    == cited_agent. Same H1+H2 cached-load + AC5 per-row caps.
    """
    for ledger in sorted(ledger_root.glob("*.jsonl")):
        citing_agent = ledger.stem
        cached = _load_ledger_cached(ledger)
        if cached["read_error"]:
            sys.stderr.write(
                f"WARN: skipping {ledger.name} in self-mining due to H2 "
                f"strict-decode failure: {cached['read_error']}\n"
            )
            continue
        for r in cached["rows"]:
            task_hint = (r.get("invocation") or "")[:200]

            cite_strs = []
            for field in ("lag_influenced_by", "cites"):
                v = r.get(field)
                if isinstance(v, list):
                    for c in v:
                        if isinstance(c, str):
                            cite_strs.append(("field", field, c))
            notes = r.get("notes", "") or ""
            if isinstance(notes, str):
                notes_scan = notes[:MAX_NOTES_SCAN_BYTES]
                canonical_hits = 0
                for m in CANONICAL_VEC_ID_RE.finditer(notes_scan):
                    if canonical_hits >= MAX_CANONICAL_CITES_PER_ROW:
                        break
                    cite_strs.append(("note", "canonical", m.group(0)))
                    canonical_hits += 1
                informal_hits = 0
                for pat in INFORMAL_PATTERNS:
                    for m in pat.finditer(notes_scan):
                        if informal_hits >= MAX_INFORMAL_CITES_PER_ROW:
                            break
                        cite_strs.append(("note", "informal", m.group(0)))
                        informal_hits += 1
                    if informal_hits >= MAX_INFORMAL_CITES_PER_ROW:
                        break

            for kind, field_name, c in cite_strs:
                # Self-emitted gate: the cited agent must equal the citing
                # agent (the row's owning ledger).
                m_canon = CANONICAL_VEC_ID_RE.search(c)
                if not m_canon:
                    continue
                cited_agent = m_canon.group(1)
                if cited_agent != citing_agent:
                    continue  # cross-agent — handled by F6-cross
                if cited_agent not in CANONICAL_10:
                    continue  # non-canonical agent name; not self in our gate
                yield {
                    "citing_agent": citing_agent,
                    "cited_agent": cited_agent,
                    "task_hint": task_hint,
                    "citation": c,
                    "kind": kind,
                    "field": field_name,
                    "owning_row_lamport": r.get("lamport_counter"),
                }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    args = ap.parse_args()

    raw = list(mine_self_emitted_citations(args.ledger_root))

    # AC7 dedup parity with cross-agent F6: collapse to (citing, cited,
    # lamport-identity) ignoring slug. Self-emitted with two slugs to the
    # same row counts once.
    seen = set()
    unique = []
    n_recycled = 0
    for c in raw:
        cite = c["citation"]
        lamport_start = cite.find("lamport-")
        slug_start = cite.find("::", lamport_start) if lamport_start >= 0 else -1
        if lamport_start >= 0 and slug_start >= 0:
            identity = cite[: slug_start]
        else:
            identity = cite
        key = (c["citing_agent"], c["cited_agent"], identity)
        if key in seen:
            n_recycled += 1
            continue
        seen.add(key)
        unique.append(c)

    pair_counts = Counter((c["citing_agent"], c["cited_agent"]) for c in unique)

    if not unique:
        summary = {
            "falsifier": "F6-SELF-canonical-resolve",
            "methodology": "self-emitted-canonical-cites-direct-lookup",
            "top_k": args.top_k,
            "n_self_emitted_citations": 0,
            "verdict": "INSUFFICIENT-DATA",
            "finding": (
                "Zero self-emitted canonical citations detected across all "
                "canonical agent ledgers. Self-citation discipline has not "
                "yet emerged in vec_id format."
            ),
            "pair_counts": {},
            "scanned_at_utc_iso": datetime.now(timezone.utc).isoformat(),
            "ledger_root": str(args.ledger_root),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    per_query = []
    n_verified = n_fabricated = n_ambiguous = n_malformed = 0
    n_match_cited = 0

    for c in unique:
        validation = validate_cite_against_ledger(c["citation"], args.ledger_root)
        status = validation["status"]
        if status == "verified":
            n_verified += 1
        elif status == "fabricated":
            n_fabricated += 1
        elif status == "ambiguous":
            n_ambiguous += 1
        else:
            n_malformed += 1

        # Canonical-resolve: parse + direct row lookup. By construction,
        # any verified canonical citation resolves to the owning row.
        parsed = parse_vec_id(c["citation"])
        if parsed and status == "verified":
            row = resolve_vec_id_to_row(c["citation"], args.ledger_root)
            match = (row is not None)
        else:
            match = False
        if match:
            n_match_cited += 1

        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "task_hint": c["task_hint"][:80],
            "citation": c["citation"][:80],
            "kind": c["kind"],
            "field": c["field"],
            "match": match,
            "ledger_validation_status": status,
            "ledger_validation_reason": validation.get("reason"),
        })

    n_total = len(per_query)
    recall_full = n_match_cited / n_total if n_total else 0.0
    recall_verified_only = n_match_cited / n_verified if n_verified else 0.0

    verdict = (
        "PASS" if recall_verified_only >= 0.99 else
        "PROVISIONAL-PASS" if recall_verified_only >= 0.50 else
        "FAIL"
    )

    summary = {
        "falsifier": "F6-SELF-canonical-resolve",
        "methodology": (
            "self-emitted-canonical-cites-direct-lookup; "
            "mirror sibling-82 tier-1 applied to self-citation subcorpus"
        ),
        "top_k": args.top_k,
        "n_self_emitted_citations": n_total,
        "n_verified": n_verified,
        "n_fabricated": n_fabricated,
        "n_ambiguous": n_ambiguous,
        "n_malformed": n_malformed,
        "n_recycled_collapsed_dedup": n_recycled,
        "n_match": n_match_cited,
        "recall_self_verified_only": round(recall_verified_only, 4),
        "recall_self_full_denominator": round(recall_full, 4),
        "verdict": verdict,
        "honest_framing": (
            "100% recall on verified canonical self-citations is BY "
            "CONSTRUCTION; canonical-resolve bypasses retrieval entirely. "
            "Fabricated and ambiguous cites correctly fail (AC1+AC2 closure "
            "preserved). recall_full_denominator < 1.0 reflects the "
            "fraction of self-cites that survive ledger validation, NOT "
            "a retrieval failure."
        ),
        "pair_counts": {f"{a}->{b}": n for (a, b), n in pair_counts.most_common()},
        "per_query": per_query[:50],
        "ledger_validation_counts": {
            "verified": n_verified,
            "fabricated": n_fabricated,
            "ambiguous": n_ambiguous,
            "malformed": n_malformed,
            "total": n_total,
        },
        "scanned_at_utc_iso": datetime.now(timezone.utc).isoformat(),
        "ledger_root": str(args.ledger_root),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
