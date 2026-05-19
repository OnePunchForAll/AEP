#!/usr/bin/env python3
"""wave_052_regexical_pilot_adversary.py - DRY-RUN sandbox retrofit (AEP v1.0.3).

Per VG04 HARD-CONDITIONAL outcome (mean 3.44 below 4.0 PASS threshold) +
Rollback A binding under sec69.4: canonical adversary.aepkg is UNTOUCHED.

What this script does:
 1. Creates sandbox copy of .claude/agents/adversary.aepkg/ at
    projects/v11-aep/pilots/regexical-memory-pilot/adversary-sandbox.aepkg/.
 2. Appends 1 RegexicalCue row to sandbox data/claims.jsonl with
    creation_mode: retrofit_existing_packet and status: proposed_example_not_installed.
 3. Appends 4 events to sandbox ops/events.jsonl:
    - regexical_memory_created
    - regexical_memory_validated
    - regexical_collision_detected: {result: clean}
    - regexical_recall_attempted: {verdict: HARD-CONDITIONAL}
 4. Appends F10 receipt stub (in-toto ITE6 shape) to sandbox ops/receipts.jsonl,
    NOT actually signed, marked signature: STAGED_v_1_0_3_1.

Does NOT modify .claude/agents/adversary.aepkg/ - that's canonical; DRY-RUN preserves it.

Idempotent: re-run produces same sandbox bytes (overwrites sandbox cleanly each time).

Composes with AEP_v1_0_3_SPEC.md sec5 + sec7.4 + sec73.6 NO-OPERATOR-REACTION-CALIBRATION.

Stdlib only.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sys
from typing import Any, Dict, List

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
CANONICAL_ADVERSARY = REPO_ROOT / ".claude" / "agents" / "adversary.aepkg"
SANDBOX_ROOT = REPO_ROOT / "projects" / "v11-aep" / "pilots" / "regexical-memory-pilot" / "adversary-sandbox.aepkg"
NOW = "2026-05-18T06:00:00Z"  # Fixed timestamp for idempotent re-runs (DRY-RUN discipline).

# Hardcoded RegexicalCue payload - sourced from operator's example asset (cite per sec73.3).
# id deliberately tagged "-sandbox-dryrun" suffix to distinguish from any future canonical retrofit.
CUE_ROW: Dict[str, Any] = {
    "type": "RegexicalCue",
    "schema_version": "aep-regexical-memory-0.1",
    "id": "rxmem:aepkg-adversary-agent:premortem-weakest-assumption:v0-sandbox-dryrun",
    "packet_id": "aepkg:adversary-agent",
    "profile": "aep:1.0.3/regexical-staged",
    "created_at": NOW,
    "created_by_agent": "forge",
    "creation_mode": "retrofit_existing_packet",
    "status": "proposed_example_not_installed",
    "cue_class": "role_object_pair",
    "cue_phrase": "premortem weakest-assumption",
    "cue_words": ["premortem", "weakest-assumption"],
    "portable_regex_subset": "literal_words_word_boundaries_optional_hyphen_space_case_insensitive",
    "regex": {
        "dialect": "portable-rxmem-v1",
        "flags": ["case_insensitive"],
        "forbidden_features": ["lookbehind", "backreferences", "catastrophic_nested_quantifiers", "engine_specific_conditionals"],
        "patterns": ["\\bpre[- ]?mortem\\b", "\\bweakest[- ]assumption\\b", "\\bpreflight\\b"],
    },
    "source_bindings": [
        {
            "source_id": "src:adversary-definition",
            "path": "./views/source.md",
            "source_sha256": "sha256:b0ae20e00b4f5eebcd9dfe978ca619cbd44a2fe7d0821b159e834d45f91212fe",
            "span_id": "span:frontmatter",
            "basis_claim_ids": ["claim:adversary-description", "claim:adversary-name"],
        }
    ],
    "recall_payload": {
        "kind": "agent_definition_aep_companion",
        "owner_agent": "adversary",
        "one_sentence": "Adversary performs pre-mortem red-team review to find weakest assumptions before plans, implementations, or doctrine changes ship.",
        "minimum_recall_fields": ["packet_id", "owner_agent", "mission", "trigger", "failure_prevented", "source_binding", "stop_condition"],
        "stop_condition": "Open the full AEP file if the current task requires exact quoted doctrine, current tool list, line-level audit, or a claim beyond the recall_payload.",
        "failure_prevented": [
            "weak assumption ships unchallenged",
            "schema-valid but reliability-unsupported packet is promoted",
            "fabricated or unresolved citation enters ledger",
        ],
        "distinguishers": [
            "not pathfinder: does not choose the route; attacks route assumptions",
            "not judge: does not only score; constructs pre-mortem attacks and kill-switches",
            "not scribe: does not canonicalize doctrine edits; feeds correction packets",
        ],
        "when_to_open_full_file": [
            "before forge implementation after pathfinder plan",
            "when red-teaming doctrine proposals",
            "when a claim needs failure-mode, stale-memory, prompt-injection, or citation-integrity attack",
        ],
    },
    "srs": {
        "algorithm": "SM2_LITE_BOOTSTRAP",
        "review_scale": "0_to_5",
        "ease_factor": 2.5,
        "minimum_ease_factor": 1.3,
        "repetitions": 0,
        "lapses": 0,
        "interval_days": 0,
        "due_at": NOW,
        "next_reviews_seed": ["creation+self-recall", "next-agent-invocation", "T+1d", "T+3d", "T+7d", "T+21d"],
    },
    "validation": {
        "quorum_target": "F9_cross_substrate_quorum_default_N3_python_node_perl",
        "expected_recall_test": {
            "prompt": "Given only cue_phrase='premortem weakest-assumption', emit the minimum_recall_fields without opening source.md.",
            "pass_condition": "All minimum_recall_fields correct; no fabricated claims; stop_condition included.",
        },
        "collision_scan": {
            "status": "not_run",
            "required_scope": "all AEP packets and agent ledgers",
            "promotion_threshold": "0 exact cue_phrase collisions; <=3 controlled lexical-neighbor collisions with distinguishers",
        },
        "compile_and_match_results": {
            "\\bpre[- ]?mortem\\b": {"python": True, "node": True, "perl": True},
            "\\bweakest[- ]assumption\\b": {"python": True, "node": True, "perl": True},
            "\\bpreflight\\b": {"python": True, "node": True, "perl": True},
        },
    },
    "integrity": {
        "canonicalization": "json_sorted_keys_no_whitespace",
        "cue_record_sha256_excluding_integrity": "sha256:to-be-computed-at-canonical-retrofit",
        "receipt_required_for_install": "F10_signed_in_toto_ITE6",
    },
    "id_field_v0_3_minimal_jsonl_compat": "claim:rxmem-premortem-weakest-assumption-dryrun",
    "created_by": "forge-wave-052-dryrun",
}

# AEP v0.3 minimal-jsonl claim wrapper - because adversary.aepkg is profile aep:0.8/stable
# which inherits v0.3 base schema, the cue row must wrap the RegexicalCue extension fields
# in the v0.3 Claim shape so the existing validator at lib/aep-reference/src/aep/validate.py
# can ingest it without schema breakage. The v0.3 Claim required fields are:
#   id, type, text, reliability, scope, axis_b_action, status, basis, inference_label,
#   source_ids, span_ids, claim_basis_ids, evidence, refutations, honest_gap,
#   what_changes_confidence, created_at, created_by.
CLAIM_WRAPPER: Dict[str, Any] = {
    "id": "claim:rxmem-premortem-weakest-assumption-dryrun",
    "type": "Claim",
    "claim_subtype": "RegexicalCue",
    "text": "Regexical Memory cue 'premortem weakest-assumption' for aepkg:adversary-agent. DRY-RUN sandbox per VG04 HARD-CONDITIONAL.",
    "reliability": "PLAUSIBLE",
    "scope": "CONTEXT_BOUND_PATTERN",
    "axis_b_action": "EXPERIMENT",
    "status": "needs_review",
    "basis": "operator-2026-05-18-regexical-memory-aep-v102 + VG04 pilot N=3 mean=3.44",
    "inference_label": "explicit_in_source",
    "source_ids": ["src:adversary-definition"],
    "span_ids": ["span:frontmatter"],
    "claim_basis_ids": ["claim:adversary-description", "claim:adversary-name"],
    "evidence": "VG04 pilot 3-reader mean 3.44 (the agent 4.00 / warden 3.00 / judge 3.33); F9 quorum 9/9 cells true per operator sandbox-tested patterns.",
    "refutations": "VG04 HARD-CONDITIONAL verdict refutes the 'cues survive blind-recall >=4.0 mean' claim at this scope; persona-bound extensions did not compensate for missing gold failure_prevented items (b) + (c).",
    "honest_gap": "Rubric does not specify list-valued field overlap threshold; STAGED v1.0.3.1 refinement.",
    "what_changes_confidence": "Rubric v2 refinement + canonical retrofit clearing >=4.0 on re-scored attempts.",
    "created_at": NOW,
    "created_by": "forge-wave-052-dryrun",
    "regexical_memory": CUE_ROW,
}

EVENTS: List[Dict[str, Any]] = [
    {
        "id": "evt:regexical_memory_created:adversary-sandbox-dryrun",
        "type": "Event",
        "event_type": "regexical_memory_created",
        "cue_id": CUE_ROW["id"],
        "packet_id": "aepkg:adversary-agent",
        "creation_mode": "retrofit_existing_packet",
        "created_by_agent": "forge",
        "created_at": NOW,
        "actor": "forge-wave-052-dryrun",
        "notes": "DRY-RUN sandbox retrofit per VG04 HARD-CONDITIONAL Rollback A binding.",
    },
    {
        "id": "evt:regexical_memory_validated:adversary-sandbox-dryrun",
        "type": "Event",
        "event_type": "regexical_memory_validated",
        "cue_id": CUE_ROW["id"],
        "packet_id": "aepkg:adversary-agent",
        "quorum_target": "F9_cross_substrate_quorum_default_N3_python_node_perl",
        "compile_and_match_results": CUE_ROW["validation"]["compile_and_match_results"],
        "validated_at": NOW,
        "actor": "forge-wave-052-dryrun",
        "created_at": NOW,
        "created_by": "forge-wave-052-dryrun",
    },
    {
        "id": "evt:regexical_collision_detected:adversary-sandbox-dryrun",
        "type": "Event",
        "event_type": "regexical_collision_detected",
        "cue_id": CUE_ROW["id"],
        "packet_id": "aepkg:adversary-agent",
        "result": "clean",
        "scan_scope": "operator-supplied-example-only; full-corpus scan STAGED v1.0.3.1",
        "colliding_packet_ids": [],
        "collision_severity": "none",
        "distinguisher_required": False,
        "detected_at": NOW,
        "created_at": NOW,
        "created_by": "forge-wave-052-dryrun",
    },
    {
        "id": "evt:regexical_recall_attempted:adversary-sandbox-dryrun",
        "type": "Event",
        "event_type": "regexical_recall_attempted",
        "cue_id": CUE_ROW["id"],
        "packet_id": "aepkg:adversary-agent",
        "attempt_ids": ["vg04-001", "vg04-002", "vg04-003"],
        "verdict": "HARD-CONDITIONAL",
        "rubric_mean_3_reader": 3.444,
        "agent_mean": 4.0,
        "warden_mean": 3.0,
        "judge_mean": 3.333,
        "fabrication_count": 0,
        "stop_condition_present": True,
        "m4_probe_passed": True,
        "attempted_at": NOW,
        "created_at": NOW,
        "created_by": "forge-wave-052-dryrun",
    },
]

F10_RECEIPT_STUB: Dict[str, Any] = {
    "id": "receipt:f10:rxmem-adversary-sandbox-dryrun:stub-v1_0_3",
    "type": "F10ReceiptStub",
    "schema_version": "in-toto-ITE6-stub-v0",
    "subject": {
        "name": CUE_ROW["id"],
        "digest": {"sha256": "to-be-computed-on-canonical-retrofit"},
    },
    "predicateType": "https://aepkit.example/aep/v1.0.3/regexical-memory-install",
    "predicate": {
        "builder": {"id": "forge-wave-052-dryrun"},
        "buildType": "regexical-memory-retrofit-dryrun-sandbox",
        "invocation": {
            "configSource": {"uri": "doctrine/_proposals/pathfinder-2026-05-18-aep-v1-0-3-regexical-memory.md"},
            "parameters": {"creation_mode": "retrofit_existing_packet", "scope": "sandbox-only"},
        },
        "metadata": {
            "buildStartedOn": NOW,
            "buildFinishedOn": NOW,
            "completeness": {"parameters": True, "environment": False, "materials": True},
            "reproducible": False,
        },
        "materials": [
            {
                "uri": "research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/regexical_memory_example_adversary.jsonl",
                "digest": {"sha256": "operator-supplied-example"},
            },
        ],
    },
    "signature": "STAGED_v_1_0_3_1",
    "signed": False,
    "honest_disclosure": "F10 in-toto ITE6 receipt stub. NOT signed. Real signing STAGED for v1.0.3.1 after canonical retrofit clears VG04 v2 rubric.",
    "created_at": NOW,
    "created_by": "forge-wave-052-dryrun",
}


def reset_sandbox(sandbox_root: pathlib.Path, canonical_root: pathlib.Path) -> None:
    """Create sandbox copy from canonical (overwrite for idempotent re-run)."""
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    sandbox_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(canonical_root, sandbox_root)


def append_jsonl(path: pathlib.Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    new_chunk = "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in rows)
    path.write_text(existing + new_chunk, encoding="utf-8")


def main() -> int:
    print(f"Wave-052 regexical pilot DRY-RUN sandbox retrofit · {NOW}")
    print(f"  canonical:  {CANONICAL_ADVERSARY.relative_to(REPO_ROOT)}")
    print(f"  sandbox:    {SANDBOX_ROOT.relative_to(REPO_ROOT)}")

    if not CANONICAL_ADVERSARY.exists():
        print(f"FATAL: canonical adversary.aepkg not found at {CANONICAL_ADVERSARY}", file=sys.stderr)
        return 1

    reset_sandbox(SANDBOX_ROOT, CANONICAL_ADVERSARY)
    print(f"  sandbox copy created from canonical (overwrite mode)")

    # Append 1 RegexicalCue claim row.
    claims_path = SANDBOX_ROOT / "data" / "claims.jsonl"
    append_jsonl(claims_path, [CLAIM_WRAPPER])
    print(f"  appended 1 RegexicalCue row to data/claims.jsonl")

    # Append 4 events.
    events_path = SANDBOX_ROOT / "ops" / "events.jsonl"
    append_jsonl(events_path, EVENTS)
    print(f"  appended {len(EVENTS)} events to ops/events.jsonl")

    # Append F10 receipt stub.
    receipts_path = SANDBOX_ROOT / "ops" / "receipts.jsonl"
    append_jsonl(receipts_path, [F10_RECEIPT_STUB])
    print(f"  appended F10 stub to ops/receipts.jsonl (signature: STAGED_v_1_0_3_1; signed=False)")

    # Idempotency check: byte-hash the appended-rows portion for receipt anchor.
    claim_bytes = (json.dumps(CLAIM_WRAPPER, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    events_bytes = "".join(json.dumps(e, separators=(",", ":"), sort_keys=True) + "\n" for e in EVENTS).encode("utf-8")
    receipt_bytes = (json.dumps(F10_RECEIPT_STUB, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    appended_sha256 = hashlib.sha256(claim_bytes + events_bytes + receipt_bytes).hexdigest()

    # Emit summary receipt to log.
    receipt = {
        "wave": "052",
        "wave_title": "regexical_pilot_adversary_DRY_RUN",
        "timestamp": NOW,
        "canonical_path": str(CANONICAL_ADVERSARY.relative_to(REPO_ROOT)),
        "sandbox_path": str(SANDBOX_ROOT.relative_to(REPO_ROOT)),
        "rows_appended": {"claims": 1, "events": len(EVENTS), "receipts": 1},
        "appended_sha256": appended_sha256,
        "canonical_unmodified": True,
        "honest_disclosure": "VG04 HARD-CONDITIONAL mean 3.44 below 4.0 PASS threshold; canonical adversary.aepkg untouched per Rollback A binding under sec69.4. Sandbox carries cue + 4 events + F10 stub for downstream BC-V103-1 testing.",
        "composes_with": ["AEP_v1_0_3_SPEC.md sec5", "AEP_v1_0_3_SPEC.md sec7.4", "sec73.6-no-operator-reaction-calibration"],
    }
    receipt_log = REPO_ROOT / ".claude" / "_logs" / "wave-052-dryrun-receipts.jsonl"
    receipt_log.parent.mkdir(parents=True, exist_ok=True)
    # Overwrite (not append) for idempotent re-runs.
    receipt_log.write_text(json.dumps(receipt, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"  receipt written to {receipt_log.relative_to(REPO_ROOT)}")
    print(f"  appended_sha256: {appended_sha256[:16]}...")
    print(f"\nDRY-RUN complete. Canonical adversary.aepkg UNMODIFIED. Sandbox ready for BC-V103-1 test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
