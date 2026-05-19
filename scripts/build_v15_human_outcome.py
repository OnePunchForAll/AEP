#!/usr/bin/env python3
"""
build_v15_human_outcome.py - K10 Human Outcome Contract (AEP v1.5 LTS)

Operator directive (sec73.2 sacred): K10 Human Outcome Contract.

Every proof card emission MUST optimize for:
  - human_autonomy
  - truthfulness
  - low_cognitive_load
  - clear_next_action
  - no_hidden_uncertainty
  - no_manipulative_confidence
  - no_completion_theater
  - no_over_personalization
  - user_future_self_care

Linter checks:
  - Every proof card MUST end with a concrete `safe_next_action` field.
  - Every blocked action MUST include `block_reason_plain_language` field
    (no jargon, no shame, no confusion).
  - Presence of any FAIL/WARN MUST surface in card section 4 with plain
    framing (composes with F22 banned-elision).

API:
  - lint_proof_card(card) -> {passes_human_outcome: bool, violations[]}
  - apply_outcome_contract(card) -> card  # mutates card to add safe_next_action
    if missing, fills block_reason_plain_language if blocked, etc.

Composes with:
  - F22 CivilianProofCard (5-row format)
  - F25 TrustDial (block-reason plain language)
  - K12 Doctor Supreme (every verdict surfaces through outcome linter)

Truth tag: STRONGLY PLAUSIBLE (linter rules schema-bound; T4+T5+T12 empirical
this turn; production rollout STAGED v1.5.1 with civilian-vocabulary expansion).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


# ---------- Outcome optimization targets ----------

OUTCOME_TARGETS = [
    "human_autonomy",
    "truthfulness",
    "low_cognitive_load",
    "clear_next_action",
    "no_hidden_uncertainty",
    "no_manipulative_confidence",
    "no_completion_theater",
    "no_over_personalization",
    "user_future_self_care",
]


# ---------- Banned jargon (civilian-facing block reasons) ----------

JARGON_TERMS = [
    # Technical jargon that fails plain-language test
    "regex",
    "sha256",
    "blake2b",
    "hash collision",
    "monomorphic",
    "polymorphic",
    "idempotent",
    "AST",
    "DAG",
    "JSON-LD",
    "schema-bound",
    "p95",
    "p99",
    "mutation testing",
    "fuzzer",
    "TTL",
    "namespace",
    "vec_id",
    "lamport",
    "sigma",
    "telemetry",
    "promotion gate",
    "validator",
    "F-tier",
    "K-tier",
    "axis A",
    "axis B",
    "BLAKE2b",
    "subprocess",
    "stdin",
    "stdout",
    # Shame-inducing or confusing
    "you failed",
    "your mistake",
    "user error",
    "wrong",
    "stupid",
    "obvious",
    # Confidence-manipulating
    "trust me",
    "obviously",
    "clearly correct",
    "100% safe",
    "no risk",
    "guaranteed",
    "perfect",
]


# Maximum acceptable cognitive load (line count in safe_next_action)
MAX_NEXT_ACTION_LINES = 5
MAX_NEXT_ACTION_CHARS = 400

# Maximum acceptable block reason length
MAX_BLOCK_REASON_CHARS = 600


# ---------- Lint ----------

def _detect_jargon(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    low = text.lower()
    found = []
    for j in JARGON_TERMS:
        if j.lower() in low:
            found.append(j)
    return found


def _detect_completion_theater(card: Dict[str, Any]) -> List[str]:
    """Detect phrases that claim completion without evidence."""
    flags = []
    theater_phrases = [
        "done!",
        "all good",
        "perfect",
        "everything is fine",
        "no issues",
        "100% complete",
        "completed successfully",
        "no further action",
    ]
    sections = (
        card.get("what_action_the_user_should_take_next", ""),
        card.get("what_is_being_claimed", ""),
        card.get("what_was_tested", ""),
    )
    for section in sections:
        if not isinstance(section, str):
            continue
        low = section.lower()
        for tp in theater_phrases:
            if tp.lower() in low:
                flags.append(f"completion_theater_phrase: {tp!r}")
    return flags


def _detect_manipulative_confidence(card: Dict[str, Any]) -> List[str]:
    flags = []
    manip = [
        "absolutely",
        "without doubt",
        "no question",
        "definitely safe",
        "100% guaranteed",
        "completely verified",
    ]
    for k, v in card.items():
        if not isinstance(v, str):
            continue
        low = v.lower()
        for m in manip:
            if m in low:
                flags.append(f"manipulative_confidence: {m!r} in field {k!r}")
    return flags


def _is_blocked_action(card: Dict[str, Any]) -> bool:
    """A card represents a blocked action when verdict is FAIL or BLOCKED, or
    explicit block_reason / blocked field set."""
    if card.get("blocked") is True:
        return True
    verdict = (card.get("verdict") or "").upper()
    if verdict in {"FAIL", "BLOCKED", "QUARANTINED", "FORBIDDEN"}:
        return True
    return False


def _has_warn_or_fail(card: Dict[str, Any]) -> bool:
    """Detect WARN/FAIL anywhere in signals or verdict."""
    if (card.get("verdict") or "").upper() in {"WARN", "FAIL", "QUARANTINED"}:
        return True
    sigs = card.get("signals") or {}
    for k, v in sigs.items():
        if not isinstance(v, dict):
            continue
        status = (v.get("status") or "").upper()
        if status in {"WARN", "FAIL", "HIGH-RISK", "BREACH"}:
            return True
    # Check row 4
    row4 = (card.get("what_is_weak_stale_missing_or_ai_derived") or "").lower()
    if any(t in row4 for t in ("warn", "fail", "missing", "stale", "weak")):
        return True
    return False


def lint_proof_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lint a proof card for human-outcome contract violations.

    Returns:
      {
        "passes_human_outcome": bool,
        "violations": [{"rule": str, "detail": str, "severity": str}],
        "checks_performed": [str],
        "outcome_targets_covered": [str]
      }
    """
    violations: List[Dict[str, Any]] = []
    checks: List[str] = []

    # Rule 1: every card has safe_next_action
    checks.append("safe_next_action_present")
    nxt = card.get("safe_next_action") or card.get("what_action_the_user_should_take_next")
    if not nxt or not isinstance(nxt, str) or not nxt.strip():
        violations.append({
            "rule": "K10.1-safe_next_action_required",
            "detail": "card missing safe_next_action / what_action_the_user_should_take_next",
            "severity": "CRITICAL",
        })

    # Rule 2: blocked action requires block_reason_plain_language (no jargon)
    checks.append("blocked_action_plain_language")
    if _is_blocked_action(card):
        br = card.get("block_reason_plain_language") or card.get("block_reason")
        if not br or not isinstance(br, str) or not br.strip():
            violations.append({
                "rule": "K10.2-block_reason_plain_language_required",
                "detail": "blocked action missing block_reason_plain_language field",
                "severity": "CRITICAL",
            })
        else:
            jargon = _detect_jargon(br)
            if jargon:
                violations.append({
                    "rule": "K10.2-block_reason_no_jargon",
                    "detail": f"block_reason contains jargon: {jargon}",
                    "severity": "FAIL",
                })
            if len(br) > MAX_BLOCK_REASON_CHARS:
                violations.append({
                    "rule": "K10.3-block_reason_low_cognitive_load",
                    "detail": f"block_reason length {len(br)} > {MAX_BLOCK_REASON_CHARS}",
                    "severity": "WARN",
                })

    # Rule 3: WARN/FAIL must surface in row 4 with plain framing
    checks.append("warn_fail_surfaces_in_row_4")
    if _has_warn_or_fail(card):
        row4 = card.get("what_is_weak_stale_missing_or_ai_derived")
        if not row4 or not isinstance(row4, str) or not row4.strip():
            violations.append({
                "rule": "K10.4-warn_fail_must_surface_row_4",
                "detail": "WARN/FAIL signal present but row 4 (weak/stale/missing) is empty",
                "severity": "CRITICAL",
            })
        else:
            jargon = _detect_jargon(row4)
            if jargon:
                violations.append({
                    "rule": "K10.4-row_4_no_jargon",
                    "detail": f"row 4 contains jargon: {jargon}",
                    "severity": "WARN",
                })

    # Rule 4: no completion theater
    checks.append("no_completion_theater")
    theater_flags = _detect_completion_theater(card)
    for t in theater_flags:
        violations.append({
            "rule": "K10.5-no_completion_theater",
            "detail": t,
            "severity": "WARN",
        })

    # Rule 5: no manipulative confidence
    checks.append("no_manipulative_confidence")
    manip_flags = _detect_manipulative_confidence(card)
    for m in manip_flags:
        violations.append({
            "rule": "K10.6-no_manipulative_confidence",
            "detail": m,
            "severity": "WARN",
        })

    # Rule 6: low cognitive load on next action
    checks.append("low_cognitive_load_next_action")
    if isinstance(nxt, str):
        if len(nxt) > MAX_NEXT_ACTION_CHARS:
            violations.append({
                "rule": "K10.7-low_cognitive_load",
                "detail": f"safe_next_action length {len(nxt)} > {MAX_NEXT_ACTION_CHARS}",
                "severity": "WARN",
            })
        if nxt.count("\n") > MAX_NEXT_ACTION_LINES:
            violations.append({
                "rule": "K10.7-low_cognitive_load_lines",
                "detail": f"safe_next_action lines {nxt.count(chr(10))} > {MAX_NEXT_ACTION_LINES}",
                "severity": "WARN",
            })

    # Outcome targets covered (heuristic; presence of each addressed)
    targets_covered = []
    text_blob = json.dumps(card, ensure_ascii=False).lower()
    target_signals = {
        "clear_next_action": bool(nxt and nxt.strip()),
        "truthfulness": "honest" in text_blob or "honest_note" in card,
        "low_cognitive_load": (
            isinstance(nxt, str) and len(nxt) <= MAX_NEXT_ACTION_CHARS
        ),
        "no_hidden_uncertainty": (
            "uncertainty" in text_blob or "unknown" in text_blob or
            "honest_note" in card
        ),
        "no_manipulative_confidence": not manip_flags,
        "no_completion_theater": not theater_flags,
        "human_autonomy": "you can" in text_blob or "you may" in text_blob or "consider" in text_blob,
        "no_over_personalization": "you specifically" not in text_blob,
        "user_future_self_care": (
            "later" in text_blob or "revisit" in text_blob or
            "future" in text_blob or "ttl" not in text_blob
        ),
    }
    for t, met in target_signals.items():
        if met:
            targets_covered.append(t)

    critical_count = sum(1 for v in violations if v["severity"] == "CRITICAL")
    passes = critical_count == 0 and len([v for v in violations if v["severity"] == "FAIL"]) == 0

    return {
        "passes_human_outcome": passes,
        "violations": violations,
        "violation_counts": {
            "CRITICAL": sum(1 for v in violations if v["severity"] == "CRITICAL"),
            "FAIL": sum(1 for v in violations if v["severity"] == "FAIL"),
            "WARN": sum(1 for v in violations if v["severity"] == "WARN"),
        },
        "checks_performed": checks,
        "outcome_targets_covered": targets_covered,
        "outcome_targets_total": OUTCOME_TARGETS,
    }


# ---------- Apply (auto-fix) ----------

def apply_outcome_contract(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply K10 contract to a card: add safe_next_action if missing, fill
    block_reason_plain_language if blocked but missing, normalize.
    Returns a NEW dict; does not mutate input.
    """
    out = dict(card)

    # Ensure safe_next_action
    if not out.get("safe_next_action"):
        existing = out.get("what_action_the_user_should_take_next")
        if existing:
            out["safe_next_action"] = existing
        else:
            # Honest minimal fallback
            out["safe_next_action"] = (
                "Read row 4 (weak/stale/missing) before relying on this output. "
                "Consider revalidating with fresh evidence before acting."
            )

    # If blocked but no plain reason, synthesize a minimal one
    if _is_blocked_action(out) and not out.get("block_reason_plain_language"):
        verdict = (out.get("verdict") or "BLOCKED").upper()
        out["block_reason_plain_language"] = (
            f"This action was blocked because the system returned {verdict}. "
            "The evidence did not pass one or more safety checks. "
            "See row 4 below for what is missing or stale."
        )

    # Optional: stamp outcome contract version
    out["k10_outcome_contract_applied"] = "v1.5-lts"
    return out


# ---------- CLI ----------

def _cli() -> int:
    ap = argparse.ArgumentParser(description="K10 Human Outcome Contract linter")
    ap.add_argument("card_path", help="Path to proof card JSON")
    ap.add_argument("--apply", action="store_true", help="Apply contract and emit fixed card")
    ap.add_argument("--out", help="Output path for fixed card (with --apply)")
    args = ap.parse_args()

    p = pathlib.Path(args.card_path)
    if not p.is_file():
        print(f"ERROR: card file not found: {p}", file=sys.stderr)
        return 3
    try:
        card = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: cannot parse card JSON: {e}", file=sys.stderr)
        return 3

    lint = lint_proof_card(card)
    print(json.dumps(lint, ensure_ascii=False, indent=2))

    if args.apply:
        fixed = apply_outcome_contract(card)
        out_path = pathlib.Path(args.out) if args.out else p.with_suffix(".k10.json")
        out_path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFixed card written to: {out_path}", file=sys.stderr)

    return 0 if lint["passes_human_outcome"] else 1


if __name__ == "__main__":
    sys.exit(_cli())
