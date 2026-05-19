"""5-FP rejection test for llm_judge_semantic_layer.py.

Replicates adversary.lamport-55 (2026-05-15) 5 hand-crafted vocabulary
attacks from doctrine/_proposals/adversary-2026-05-15-100pct-recall-tier2-
soft-match-attack.html lines 79-167. Each attack's slug looked superficially
relevant but the cited cited row was an UNRELATED real ledger row from a
different mission with overlapping vocabulary.

EXPECTED OUTCOME with stub: 5/5 FAIL to reject (stub IS keyword-overlap;
load-bearing finding is that the WIRING works — cache + tier-4 integration —
not that the stub defeats adversary). Once stub is replaced with a real LLM
(Haiku at ~$0.0001/call per codex burn 15 spec), rerun this script and the
rejection rate should approach 5/5 PASS.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm_judge_semantic_layer import llm_judge_pair

# 5 hand-crafted vocab attacks lifted verbatim from adversary's evidence.
# Each entry: (query, fake_cite_id, false_positive_row_text).
# The false_positive_row_text is the actual row tier-2 maps the attack onto.
TEST_CASES = [
    {
        "name": "FP-1 verify-tc-d-re-run-independent",
        "query": "verify tc d re run independent",
        "fake_cite": "ledger::judge::lamport-null-e7a02fd1c3b5::verify-tc-d-re-run-independent",
        "fp_row_id": "judge.lamport-25",
        "fp_row_text": ("verify TC-D re-run independent isolation 1/1 PASS verbatim "
                        "redirect note: shared-log race observed first run "
                        "(LogDelta=3); clean re-run delta=1"),
        # Adversary's example: cite is fabricated; tier-2 returns judge.lamport-25 (marathon 9d earlier)
        "ground_truth": "FAIL",  # The cite is fabricated; this row is NOT the intended evidence.
    },
    {
        "name": "FP-2 the-audit-doctrine-slot-promotion-verdict",
        "query": "audit doctrine slot promotion verdict",
        "fake_cite": "ledger::forge::lamport-99999::the-audit-doctrine-slot-promotion-verdict",
        "fp_row_id": "forge.v4-tooling-phase-0",
        "fp_row_text": ("v4 tooling phase-0 forge implementation audit-doctrine-slot "
                        "promotion verdict pending; cross-agent allowlist updated"),
        "ground_truth": "FAIL",  # lamport-99999 doesn't exist; fabrication.
    },
    {
        "name": "FP-3 lesson-capture-sibling-cross-agent",
        "query": "lesson capture sibling cross agent",
        "fake_cite": "ledger::scribe::lamport-99999::lesson-capture-sibling-cross-agent",
        "fp_row_id": "scribe.lamport-11",
        "fp_row_text": ("scribe marathon-2026-05-06 captured sibling lesson cross-agent "
                        "citation discipline; doctrine/lessons/_index.html row 24"),
        "ground_truth": "FAIL",  # lamport-99999 fabricated.
    },
    {
        "name": "FP-4 doctrine-validation-2026-05-15",
        "query": "doctrine validation 2026 05 15",
        "fake_cite": "ledger::warden::lamport-99999::doctrine-validation-2026-05-15",
        "fp_row_id": "warden.operator-double-3",
        "fp_row_text": ("operator-double-3-warden doctrine validation 2026-05-15 audit "
                        "5/5 PASS append-only invariant green"),
        "ground_truth": "FAIL",  # lamport-99999 fabricated.
    },
    {
        "name": "FP-5 retrieval-architecture-pattern-pagerank",
        "query": "retrieval architecture pattern pagerank",
        "fake_cite": "ledger::pathfinder::lamport-99999::retrieval-architecture-pattern-pagerank",
        "fp_row_id": "pathfinder.lamport-60",
        "fp_row_text": ("retrieval architecture 4-phase ladder pagerank pattern "
                        "investigation loop 1 disconfirmer-first ordering"),
        "ground_truth": "FAIL",  # lamport-99999 fabricated.
    },
]


def main() -> int:
    results = []
    n_reject = 0
    n_total = len(TEST_CASES)
    for case in TEST_CASES:
        verdict = llm_judge_pair(
            query=case["query"],
            row_id=case["fp_row_id"],
            row_text=case["fp_row_text"],
        )
        rejected = (verdict["verdict"] == "FAIL")  # FAIL = correctly rejected
        if rejected:
            n_reject += 1
        results.append({
            "case": case["name"],
            "ground_truth_expected": case["ground_truth"],
            "stub_verdict": verdict["verdict"],
            "stub_reason": verdict["reason"],
            "correctly_rejected": rejected,
            "cache_key": verdict["cache_key"],
            "cache_hit": verdict.get("cache_hit", False),
        })

    summary = {
        "test": "5-FP-rejection-stub-llm-judge",
        "n_total": n_total,
        "n_correctly_rejected_stub": n_reject,
        "rejection_rate_stub": round(n_reject / n_total, 4),
        "expected_stub_rejection_rate": 0.0,  # stub is keyword-overlap = adversary's exact attack surface
        "expected_real_llm_rejection_rate": 1.0,  # real LLM should reject all 5 fabrications
        "load_bearing_finding": ("Stub mechanically wired (cache + tier-4); stub CANNOT "
                                  "reject vocab-overlap FPs because the stub IS a vocab-"
                                  "overlap classifier. Rerun after Haiku integration."),
        "results": results,
    }
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
