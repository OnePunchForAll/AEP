"""falsifier_6_cross_agent_contextual.py — F6 cross-agent variant using
Anthropic Contextual Retrieval (deterministic prefix) instead of raw TF-IDF.

Purpose: measure the recall delta of contextual prepending vs TF-IDF baseline
on the same cross-agent canonical citation corpus that F6 cross-agent measures.
This is the load-bearing instrument for §57 P4 promotion gate.

Methodology: identical to falsifier_6_cross_agent_cites EXCEPT calls
lag_retrieve_contextual.main(argv) IN-PROCESS instead of subprocess.run of
lag_retrieve_contextual.py for the cited-agent retrieval test. Reuses
validate_cite_against_ledger + match_citation + mining functions from the
canonical falsifier.

WAVE-Q REFACTOR (forge sibling-49 cluster closure condition 2, 2026-05-16):
Replaced subprocess.run([sys.executable, "lag_retrieve_contextual.py", ...])
with `import lag_retrieve_contextual; lag_retrieve_contextual.main(argv)` +
`contextlib.redirect_stdout` capture. Eliminates the WinError 5 depth-2
nested-spawn failure (sibling-49 fingerprint) without changing output
semantics; downstream parsing of NDJSON lines is byte-identical to the
subprocess path. Composes with f6_cross_agent_inproc_quickfire (Wave-N
exemplar) and Wave-O cosmetic sys.executable baseline.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from falsifier_6_cross_agent_cites import (
    mine_cross_agent_citations,
    match_citation,
    validate_cite_against_ledger,
)
import lag_retrieve_contextual


def run_contextual_retrieve(agent: str, task_hint: str, top_k: int):
    """Wave-Q inline replacement for the prior subprocess.run shell-out.

    Captures stdout from lag_retrieve_contextual.main(argv) using
    contextlib.redirect_stdout; parses NDJSON identically to the subprocess
    path. Honors the --format ndjson contract."""
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
        # main() may sys.exit(0) on benign no-index / empty-query branches;
        # treat non-zero exits as empty result rather than raising (matches
        # the subprocess returncode behavior — caller only consumes stdout).
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
        print(json.dumps({
            "verdict": "INSUFFICIENT-DATA",
            "n_cross_agent_citations": 0,
        }, indent=2))
        return 0

    per_query = []
    n_verified = n_match_cited = 0
    for c in unique:
        validation = validate_cite_against_ledger(c["citation"], args.ledger_root)
        if validation["status"] == "verified":
            n_verified += 1
        hits_cited = run_contextual_retrieve(c["cited_agent"], c["task_hint"], args.top_k)
        match_cited = match_citation(c["citation"], hits_cited) and validation["status"] == "verified"
        if match_cited:
            n_match_cited += 1
        per_query.append({
            "citing_agent": c["citing_agent"],
            "cited_agent": c["cited_agent"],
            "task_hint": c["task_hint"][:80],
            "citation": c["citation"][:80],
            "match_in_cited_index_contextual": match_cited,
            "ledger_validation_status": validation["status"],
        })

    n_total = len(per_query)
    recall_contextual = n_match_cited / n_total
    recall_verified_only = n_match_cited / n_verified if n_verified else 0.0

    summary = {
        "falsifier": "F6-cross-agent-cites-recall-CONTEXTUAL",
        "methodology": "anthropic-contextual-retrieval-deterministic-prefix",
        "top_k": args.top_k,
        "n_cross_agent_citations": n_total,
        "n_verified": n_verified,
        "n_match_in_cited_index_contextual": n_match_cited,
        "recall_contextual_full_denominator": round(recall_contextual, 4),
        "recall_contextual_verified_only": round(recall_verified_only, 4),
        "pass_threshold_provisional": 0.10,
        "pass_threshold_full": 0.50,
        "verdict": ("PASS" if recall_contextual >= 0.50 else
                    "PROVISIONAL-PASS" if recall_contextual >= 0.10 else "FAIL"),
        "per_query": per_query[:30],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main() or 0)
