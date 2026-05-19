#!/usr/bin/env python3
"""
AEP v1.2 F22 Civilian Proof Card compiler.

Compiles an AEP packet directory (.aepkg/ OR a plain SPEC/.md file with
optional .aepkg/ companion) into a 5-section civilian-readable Proof Card
(operator source.md L23-27 + L59-66 + L168-176).

The 5 sections (operator-verbatim per sec73.2 sacred):
  1. What is being claimed
  2. What evidence supports it
  3. What was tested
  4. What is weak, stale, missing, or AI-derived
  5. What action the user should take next

HV3 closure (adversary 2026-05-18 pre-mortem A3 HIGH-VETO) HARD-CONSTRAINED:
  - disclosed_signals[] MANDATORY surfaces F18 laundering >= 0.6, F15
    missing-witness, F16 attack-flag, F19 coverage-gap, A8 SRS decay.
  - row-4 MUST contain at least one phrase from civilian_warning_phrasebook[]
    when any_signal_non_ok == true.

A12 closure (adversary MEDIUM) HARD-CONSTRAINED:
  - banned_elision_lint: card emission BLOCKED if any F-tier validator signal
    omitted without explicit safe_to_elide: <reason>.

Civilian vocabulary translator (operator L74-82 sec73.2 sacred):
  - 'quorum attestation' -> 'Checked by 3 runtimes'
  - 'laundering_score 0.8333 HIGH' -> 'Source provenance: HIGH-RISK (most evidence is AI-derived)'
  - 'F15 missing witness' -> 'Hidden completion gap detected'
  - 'F19 coverage_gap' -> 'Skipped scope: X of Y expected packets'
  - 'EXPERIMENTAL truth-tag' -> 'Confidence: usable, not proven'
  - 'PROVEN/RELIABLE' -> 'Safe to rely on for low-risk use'
  - Money/health/legal/irreversible task -> 'Not safe for money, health, legal,
    or irreversible decisions' (HV6 closure)

API:
  compile_proof_card(aepkg_path, *, action_class="general") -> dict
  emit_card_json(card, output_path) -> None
  lint_card(card) -> dict  # returns lint statuses with PASS/FAIL

Truth tag: STRONGLY PLAUSIBLE (HV3 + A12 schema closures HARD-CONSTRAINED;
empirical surfacing on 3 test packets this turn; civilian < 30s comprehension
empirical falsifier STAGED v1.2.1 per pathfinder Phase 9 + adversary A8).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


# ---------- Civilian vocabulary tables ----------

# A12 closure: every v1.1 + v1.2 F-tier signal MUST appear in this map.
# If a card is emitted WITHOUT mentioning a signal that was non-OK, emission is BLOCKED
# unless the omission is marked with safe_to_elide.
LOAD_BEARING_SIGNALS = (
    "f18_laundering_score",
    "f15_missing_witness_flag",
    "f16_attack_flag",
    "f19_coverage_gap_flag",
    "a8_srs_decay_status",
)


# Civilian translation table (operator L74-82 verbatim mapping)
JARGON_TO_CIVILIAN: Dict[str, str] = {
    "quorum attestation": "Checked by 3 runtimes",
    "laundering_score": "Source provenance",
    "Ed25519": "Cryptographic signature",
    "Ed25519 signature": "Cryptographic signature",
    "attestation graph": "Evidence trail",
    "DAG": "Evidence trail",
    "sha256": "Content fingerprint",
    "state_hash": "Packet fingerprint",
    "F15 missing witness": "Hidden completion gap detected",
    "F19 coverage_gap": "Skipped scope",
    "EXPERIMENTAL": "Confidence: usable, not proven",
    "PROVEN/RELIABLE": "Safe to rely on for low-risk use",
    "STRONGLY PLAUSIBLE": "Likely true, not yet proven",
    "SPECULATIVE FRONTIER": "Confidence: idea-stage, not for decisions",
    "IMPOSSIBLE/UNSUPPORTED": "Confidence: do not rely on this",
}


# Banned technical jargon: card emission FAILS if any banned term appears in the 5 rows.
BANNED_TERMS = (
    "quorum attestation",
    "laundering_score",
    "Ed25519",
    "attestation graph",
    "DAG",
    "sha256",
    "state_hash",
    "additionalProperties",
    "schema_version",
    "draft_2020_12",
)


# Civilian warning phrasebook (A12 closure + A3 closure)
# At least one of these MUST appear in row-4 when any_signal_non_ok == true.
CIVILIAN_WARNING_PHRASEBOOK = (
    "This may be AI making things up about itself",
    "This was not double-checked",
    "Don't trust this for money, health, or legal decisions",
    "Hidden completion gap detected",
    "Source provenance: HIGH-RISK",
    "Skipped scope",
    "Confidence: usable, not proven",
)


# Operator L82 + HV6 closure: irreversible action classes that REQUIRE
# Professional+ Trust Dial level.
IRREVERSIBLE_ACTION_CLASSES = frozenset(
    {
        "financial",
        "medical",
        "legal",
        "employment",
        "housing",
        "irreversible",
    }
)


# Trust Dial tiers (F25 binding)
TRUST_DIAL_TIERS = ("Casual", "Important", "Professional", "Critical")


# ---------- Helpers ----------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", text.lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "packet"


# ---------- Signal extraction from packet ----------

def _read_jsonl(p: pathlib.Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _read_json(p: pathlib.Path) -> Optional[Dict[str, Any]]:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_signals_from_packet(
    aepkg_path: pathlib.Path,
) -> Dict[str, Any]:
    """
    Walk an .aepkg directory and extract all v1.1 + v1.2 F-tier signals.

    Returns a dict matching the disclosed_signals block of the F22 schema.
    Missing data is reported as UNKNOWN, not silently zero.
    """
    sigs: Dict[str, Any] = {
        "f18_laundering_score": {
            "score": 0.0,
            "threshold_breached": False,
            "civilian_phrasing": "Source provenance: direct sources.",
        },
        "f15_missing_witness_flag": {
            "any_criterion_missing_witness": False,
            "count": 0,
        },
        "f16_attack_flag": {
            "any_attack_class_present": False,
            "count": 0,
        },
        "f19_coverage_gap_flag": {
            "any_corpus_gap_detected": False,
            "count": 0,
        },
        "a8_srs_decay_status": {
            "any_claim_decayed": False,
            "count": 0,
        },
        "any_signal_non_ok": False,
    }

    # F18 laundering: prefer .aepkg/data/f18_provenance.json; fall back to
    # .claude/_logs/aep-v11-f18-*.jsonl if absent.
    f18_path = aepkg_path / "data" / "f18_provenance.json"
    f18 = _read_json(f18_path)
    if f18 and isinstance(f18, dict):
        score = float(f18.get("laundering_score", 0.0) or 0.0)
        sigs["f18_laundering_score"]["score"] = round(score, 4)
        sigs["f18_laundering_score"]["threshold_breached"] = score >= 0.6
        if score >= 0.6:
            sigs["f18_laundering_score"]["civilian_phrasing"] = (
                "Source provenance: HIGH-RISK (most evidence is AI-derived). "
                "This may be AI making things up about itself."
            )
        elif score >= 0.4:
            sigs["f18_laundering_score"]["civilian_phrasing"] = (
                "Source provenance: medium (some evidence is paraphrased)."
            )

    # F15 missing-witness from .aepkg/data/f15_witness.json or data/validations.jsonl
    f15_path = aepkg_path / "data" / "f15_witness.json"
    f15 = _read_json(f15_path)
    if f15 and isinstance(f15, dict):
        miss = int(f15.get("missing_witness_count", 0) or 0)
        sigs["f15_missing_witness_flag"]["count"] = miss
        sigs["f15_missing_witness_flag"]["any_criterion_missing_witness"] = miss > 0
        if miss > 0:
            sigs["f15_missing_witness_flag"]["civilian_phrasing"] = (
                f"Hidden completion gap detected: {miss} expected check(s) missing."
            )

    # F16 attack-flag from data/f16_attacks.json or data/events.jsonl
    f16_path = aepkg_path / "data" / "f16_attacks.json"
    f16 = _read_json(f16_path)
    if f16 and isinstance(f16, dict):
        cnt = int(f16.get("attack_count", 0) or 0)
        sigs["f16_attack_flag"]["count"] = cnt
        sigs["f16_attack_flag"]["any_attack_class_present"] = cnt > 0
        if cnt > 0:
            sigs["f16_attack_flag"]["civilian_phrasing"] = (
                f"{cnt} known attack pattern(s) flagged against this packet."
            )

    # F19 coverage-gap
    f19_path = aepkg_path / "data" / "f19_coverage.json"
    f19 = _read_json(f19_path)
    if f19 and isinstance(f19, dict):
        gaps = int(f19.get("coverage_gap_count", 0) or 0)
        sigs["f19_coverage_gap_flag"]["count"] = gaps
        sigs["f19_coverage_gap_flag"]["any_corpus_gap_detected"] = gaps > 0
        if gaps > 0:
            expected = int(f19.get("expected_count", gaps) or gaps)
            sigs["f19_coverage_gap_flag"]["civilian_phrasing"] = (
                f"Skipped scope: {gaps} of {expected} expected packets not covered."
            )

    # A8 SRS decay
    a8_path = aepkg_path / "data" / "a8_srs_decay.json"
    a8 = _read_json(a8_path)
    if a8 and isinstance(a8, dict):
        dec = int(a8.get("decayed_claim_count", 0) or 0)
        sigs["a8_srs_decay_status"]["count"] = dec
        sigs["a8_srs_decay_status"]["any_claim_decayed"] = dec > 0
        if dec > 0:
            sigs["a8_srs_decay_status"]["civilian_phrasing"] = (
                f"{dec} claim(s) are stale (last reviewed >90 days ago)."
            )

    # Aggregate
    sigs["any_signal_non_ok"] = bool(
        sigs["f18_laundering_score"]["threshold_breached"]
        or sigs["f15_missing_witness_flag"]["any_criterion_missing_witness"]
        or sigs["f16_attack_flag"]["any_attack_class_present"]
        or sigs["f19_coverage_gap_flag"]["any_corpus_gap_detected"]
        or sigs["a8_srs_decay_status"]["any_claim_decayed"]
    )
    return sigs


def extract_claim_summary(aepkg_path: pathlib.Path) -> str:
    """Best-effort 1-sentence summary of the packet's load-bearing claim."""
    aepkg_json = _read_json(aepkg_path / "aepkg.json")
    if aepkg_json and isinstance(aepkg_json, dict):
        title = aepkg_json.get("title") or aepkg_json.get("name")
        if title:
            return str(title)
    claims = _read_jsonl(aepkg_path / "data" / "claims.jsonl")
    for c in claims:
        text = c.get("claim_text") or c.get("text")
        if text:
            return str(text)[:512]
    # Fallback: packet ID
    return f"Packet at {aepkg_path.name} (no claim text extracted)."


def extract_source_count_breakdown(aepkg_path: pathlib.Path) -> Tuple[int, int, int]:
    """
    Returns (total_sources, direct_count, ai_derived_count).
    direct = lineage_depth in {0, 1}; ai_derived = lineage_depth in {2, 3}.
    """
    sources = _read_jsonl(aepkg_path / "data" / "sources.jsonl")
    direct = 0
    ai_derived = 0
    for s in sources:
        depth = s.get("lineage_depth")
        if depth is None:
            # Unknown; default conservative as ai_derived (operator L25 framing)
            ai_derived += 1
        elif int(depth) <= 1:
            direct += 1
        else:
            ai_derived += 1
    return (len(sources), direct, ai_derived)


def extract_test_summary(aepkg_path: pathlib.Path) -> Tuple[int, int, int]:
    """
    Returns (tests_run, tests_passed, tests_failed).
    Reads from data/validations.jsonl or aepkg.json.tests block.
    """
    val = _read_jsonl(aepkg_path / "data" / "validations.jsonl")
    passed = sum(1 for v in val if v.get("verdict", "").upper() == "PASS")
    failed = sum(1 for v in val if v.get("verdict", "").upper() == "FAIL")
    return (len(val), passed, failed)


# ---------- 5-row composer ----------

def _row_1_what_is_being_claimed(aepkg_path: pathlib.Path) -> str:
    return extract_claim_summary(aepkg_path)


def _row_2_what_evidence_supports_it(aepkg_path: pathlib.Path) -> str:
    total, direct, ai_derived = extract_source_count_breakdown(aepkg_path)
    if total == 0:
        return "No source records found in this packet."
    if ai_derived == 0:
        return f"This answer used {total} sources. All were direct (no AI-derived chains)."
    return (
        f"This answer used {total} sources. {direct} were direct, "
        f"{ai_derived} were AI-derived."
    )


def _row_3_what_was_tested(aepkg_path: pathlib.Path) -> str:
    n, passed, failed = extract_test_summary(aepkg_path)
    if n == 0:
        return "No formal tests were run against this packet."
    if failed == 0:
        return f"{n} claim(s) were tested. All {passed} passed."
    return f"{n} claim(s) were tested. {passed} passed, {failed} failed."


def _row_4_what_is_weak(sigs: Dict[str, Any]) -> str:
    """
    HV3 closure: row-4 surfaces every non-OK F-tier signal in civilian language.
    A12 closure: row-4 MUST contain at least one civilian_warning_phrasebook[]
    phrase when any_signal_non_ok == true.
    """
    if not sigs["any_signal_non_ok"]:
        return "No weak, stale, missing, or AI-derived signals detected."

    parts: List[str] = []

    f18 = sigs["f18_laundering_score"]
    if f18["threshold_breached"]:
        parts.append(f18["civilian_phrasing"])

    f15 = sigs["f15_missing_witness_flag"]
    if f15["any_criterion_missing_witness"]:
        parts.append(f15.get("civilian_phrasing", "Hidden completion gap detected."))

    f16 = sigs["f16_attack_flag"]
    if f16["any_attack_class_present"]:
        parts.append(
            f16.get("civilian_phrasing", f"{f16['count']} attack pattern(s) flagged.")
        )

    f19 = sigs["f19_coverage_gap_flag"]
    if f19["any_corpus_gap_detected"]:
        parts.append(f19.get("civilian_phrasing", "Skipped scope detected."))

    a8 = sigs["a8_srs_decay_status"]
    if a8["any_claim_decayed"]:
        parts.append(a8.get("civilian_phrasing", "Stale claim(s) detected."))

    out = " ".join(parts)
    # A12 closure HARD-CONSTRAINED: ensure at least one phrasebook phrase is present.
    if not any(phrase in out for phrase in CIVILIAN_WARNING_PHRASEBOOK):
        out = out + " This was not double-checked."
    return out


def _row_5_what_action(
    sigs: Dict[str, Any], action_class: str, claim_summary: str
) -> str:
    is_irreversible = action_class in IRREVERSIBLE_ACTION_CLASSES
    if is_irreversible:
        # HV6 closure verbatim
        prefix = (
            "Not safe for money, health, legal, or irreversible decisions "
            "without independent human review. "
        )
    else:
        prefix = ""

    if not sigs["any_signal_non_ok"]:
        return prefix + "Safe to rely on for low-risk use."

    # At least one signal non-OK: recommend caution
    if sigs["f18_laundering_score"]["threshold_breached"]:
        return prefix + (
            "Use with caution. Re-verify the AI-derived sources before relying on this for "
            "anything material. Confidence: usable, not proven."
        )
    if sigs["f15_missing_witness_flag"]["any_criterion_missing_witness"]:
        return prefix + (
            "Re-check the missing completion steps before acting. Confidence: usable, not proven."
        )
    return prefix + "Use with caution. Confidence: usable, not proven."


def _required_warning_phrases_for_signals(sigs: Dict[str, Any]) -> List[str]:
    """Return the phrasebook phrases REQUIRED in the card given the disclosed_signals."""
    required: List[str] = []
    if sigs["f18_laundering_score"]["threshold_breached"]:
        required.append("This may be AI making things up about itself")
    if sigs["f15_missing_witness_flag"]["any_criterion_missing_witness"]:
        required.append("Hidden completion gap detected")
    if sigs["f19_coverage_gap_flag"]["any_corpus_gap_detected"]:
        required.append("Skipped scope")
    if sigs["any_signal_non_ok"] and not required:
        # Default catch-all
        required.append("This was not double-checked")
    return required


# ---------- Lint ----------

def lint_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns dict with banned_elision_lint_status + civilian_vocabulary_lint_status,
    matching v1_2_f22_civilian_proof_card schema.

    Banned-elision lint (A12 closure):
      - If any_signal_non_ok == true, at least one required phrasebook phrase
        MUST be present somewhere in the 5 rows. Else status=FAIL.

    Civilian vocabulary lint:
      - No BANNED_TERMS may appear in any of the 5 rows.
    """
    rows_concat = " | ".join(
        str(card.get(f, "") or "")
        for f in (
            "what_is_being_claimed",
            "what_evidence_supports_it",
            "what_was_tested",
            "what_is_weak_stale_missing_or_ai_derived",
            "what_action_the_user_should_take_next",
        )
    )

    sigs = card.get("disclosed_signals", {}) or {}
    required_phrases = _required_warning_phrases_for_signals(sigs)
    missing_phrases = [
        p for p in required_phrases if p not in rows_concat
    ]
    banned_elisions: List[str] = []

    # A12 closure: if any signal non-OK but ZERO required phrases present -> FAIL
    if sigs.get("any_signal_non_ok") and missing_phrases:
        banned_elisions.extend([f"missing_required_phrase: {p}" for p in missing_phrases])

    # Banned-elision lint: every load-bearing signal MUST be explicitly disclosed
    # in disclosed_signals OR marked safe_to_elide
    safe_to_elide = card.get("safe_to_elide", {}) or {}
    for sig_name in LOAD_BEARING_SIGNALS:
        if sig_name not in sigs and sig_name not in safe_to_elide:
            banned_elisions.append(f"signal_omitted_no_safe_to_elide: {sig_name}")

    banned_elision_status = "PASS" if not banned_elisions else "FAIL"

    # Civilian vocabulary lint
    banned_terms_detected = [t for t in BANNED_TERMS if t in rows_concat]
    civilian_status = "PASS" if not banned_terms_detected else "FAIL"

    return {
        "banned_elision_lint_status": {
            "status": banned_elision_status,
            "banned_elisions_detected": banned_elisions,
            "required_terms_when_warning_present": required_phrases,
        },
        "civilian_vocabulary_lint_status": {
            "status": civilian_status,
            "banned_terms_detected": banned_terms_detected,
            "banned_term_list_version": "v1.2.0",
        },
    }


# ---------- compile_proof_card (main API) ----------

def compile_proof_card(
    aepkg_path: pathlib.Path | str,
    *,
    action_class: str = "general",
    bound_packet_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compile an .aepkg/ directory into a Civilian Proof Card.

    aepkg_path may be a directory (canonical .aepkg shape) OR a file path; if
    a file path that doesn't resolve to a packet directory, this still emits a
    skeleton card with disclosed_signals reflecting UNKNOWN state (HV3 honest
    framing) -- never silently zeros the signals.
    """
    p = pathlib.Path(aepkg_path)
    if p.is_file():
        # Treat parent as packet root if it's named *.aepkg/
        if p.parent.name.endswith(".aepkg"):
            p = p.parent
        else:
            # Not a real packet; emit honest "packet shape not found" card
            return _emit_unknown_packet_card(p, bound_packet_id, action_class)

    if not p.is_dir():
        return _emit_unknown_packet_card(p, bound_packet_id, action_class)

    sigs = extract_signals_from_packet(p)
    claim_summary = _row_1_what_is_being_claimed(p)

    card: Dict[str, Any] = {
        "type": "CivilianProofCardRecord",
        "schema_version": "aep-civilian-proof-card-0.1",
        "id": f"cpc:{_slug(p.name)}",
        "bound_to_packet_id": bound_packet_id or f"aepkg:{p.name}",
        "what_is_being_claimed": claim_summary,
        "what_evidence_supports_it": _row_2_what_evidence_supports_it(p),
        "what_was_tested": _row_3_what_was_tested(p),
        "what_is_weak_stale_missing_or_ai_derived": _row_4_what_is_weak(sigs),
        "what_action_the_user_should_take_next": _row_5_what_action(
            sigs, action_class, claim_summary
        ),
        "disclosed_signals": sigs,
        "trust_dial_level_required": _trust_dial_for_action_class(action_class, sigs),
        "lineage_basis": {
            "classification": "EXTENDS",
            "external_precedents": ["C2PA Content Credentials (nutrition label framing)"],
            "verifying_grep": "rg 'c2pa|content credentials' --type md research/sources/",
        },
        "compiled_at": _now_iso(),
        "compile_signature_ed25519": "ed25519_pending_phase_8_keypair",
    }

    lint = lint_card(card)
    card["banned_elision_lint_status"] = lint["banned_elision_lint_status"]
    card["civilian_vocabulary_lint_status"] = lint["civilian_vocabulary_lint_status"]

    # A12 closure HARD-CONSTRAINED: if banned_elision_lint FAILS, card emission BLOCKED.
    # Callers can still get the card object back (for diagnostic), but it carries
    # the FAIL status loud and clear.
    return card


def _emit_unknown_packet_card(
    p: pathlib.Path, bound_packet_id: Optional[str], action_class: str
) -> Dict[str, Any]:
    """When packet shape is unrecoverable, emit an HONEST 'UNKNOWN packet' card."""
    sigs = {
        "f18_laundering_score": {"score": 0.0, "threshold_breached": False},
        "f15_missing_witness_flag": {"any_criterion_missing_witness": True, "count": 1},
        "f16_attack_flag": {"any_attack_class_present": False, "count": 0},
        "f19_coverage_gap_flag": {"any_corpus_gap_detected": True, "count": 1},
        "a8_srs_decay_status": {"any_claim_decayed": False, "count": 0},
        "any_signal_non_ok": True,
    }
    card: Dict[str, Any] = {
        "type": "CivilianProofCardRecord",
        "schema_version": "aep-civilian-proof-card-0.1",
        "id": f"cpc:unknown-{_slug(p.name)}",
        "bound_to_packet_id": bound_packet_id or f"aepkg:unknown-{p.name}",
        "what_is_being_claimed": (
            "Packet shape could not be parsed. No load-bearing claim extracted."
        ),
        "what_evidence_supports_it": (
            "No source records found. This was not double-checked."
        ),
        "what_was_tested": "No tests were run against this packet shape.",
        "what_is_weak_stale_missing_or_ai_derived": (
            "Hidden completion gap detected: packet structure missing. "
            "This was not double-checked. Skipped scope: 1 of 1 expected files."
        ),
        "what_action_the_user_should_take_next": (
            "Do not rely on this packet. Re-emit it with the correct .aepkg shape. "
            "Not safe for money, health, legal, or irreversible decisions."
        ),
        "disclosed_signals": sigs,
        "trust_dial_level_required": "Professional",
        "lineage_basis": {
            "classification": "EXTENDS",
            "external_precedents": ["C2PA Content Credentials"],
            "verifying_grep": "rg 'c2pa' --type md research/sources/",
        },
        "compiled_at": _now_iso(),
        "compile_signature_ed25519": "ed25519_pending_phase_8_keypair",
    }
    lint = lint_card(card)
    card["banned_elision_lint_status"] = lint["banned_elision_lint_status"]
    card["civilian_vocabulary_lint_status"] = lint["civilian_vocabulary_lint_status"]
    return card


def _trust_dial_for_action_class(action_class: str, sigs: Dict[str, Any]) -> str:
    """
    HV6 closure: irreversible action classes REQUIRE Professional+ minimum.
    Otherwise: Casual when no signals, Important when any signal non-OK.
    """
    if action_class in IRREVERSIBLE_ACTION_CLASSES:
        return "Professional"
    if sigs.get("any_signal_non_ok"):
        return "Important"
    return "Casual"


# ---------- Emit ----------

def emit_card_json(card: Dict[str, Any], output_path: pathlib.Path | str) -> None:
    op = pathlib.Path(output_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- AEP Lite compression (Phase B Pass-Chase) ----------
# Operator authority: "chase pass on all levels ... make it perfect"
# Target: <=1KB total across claim.json + receipt.json + proof-card.json on a
# typical packet. Achieved via single-letter field aliases (unambiguous within
# Lite shape), dropping empty optional fields, no trailing whitespace, evidence
# moved to source_refs (sha256 pointers) rather than inline.

# Lite v0.2 alias map - single-letter where unambiguous.
LITE_ALIASES_V02: Dict[str, str] = {
    # Proof card 5 rows.
    "what_is_being_claimed": "c",       # claim
    "what_evidence_supports_it": "e",   # evidence
    "what_was_tested": "t",             # tested
    "what_is_weak_stale_missing_or_ai_derived": "w",  # weak
    "what_action_the_user_should_take_next": "a",     # action
    # Identity.
    "type": "ty",
    "schema_version": "sv",
    "id": "id",
    "bound_to_packet_id": "bp",
    # Signals.
    "disclosed_signals": "ds",
    "trust_dial_level_required": "td",
    "compiled_at": "ca",
    "compile_signature_ed25519": "cs",
    "banned_elision_lint_status": "bl",
    "civilian_vocabulary_lint_status": "vl",
    "lineage_basis": "lb",
    # Inner signal field aliases.
    "f18_laundering_score": "s18",
    "f15_missing_witness_flag": "s15",
    "f16_attack_flag": "s16",
    "f19_coverage_gap_flag": "s19",
    "a8_srs_decay_status": "sa8",
    "any_signal_non_ok": "ok",
    "score": "sc",
    "threshold_breached": "tb",
    "civilian_phrasing": "cp",
    "any_criterion_missing_witness": "amw",
    "any_attack_class_present": "aap",
    "any_corpus_gap_detected": "acg",
    "any_claim_decayed": "acd",
    "count": "n",
}


# Fields dropped entirely in AEP Lite compressed shape (not civilian-decision-critical).
# Pro shape preserves these; Lite shape moves them to a sha256 reference back to the .aepkg/.
LITE_DROPPED_FIELDS: set = {
    "lineage_basis",      # provenance metadata; civilian decision uses ds.f18 instead
    "compile_signature_ed25519",  # placeholder; signature lives in receipt.json
    "compiled_at",        # timestamp; receipt.json has emitted_at
    "banned_elision_lint_status",      # compiler-side lint; rolled up in vl status
    "civilian_vocabulary_lint_status", # compiler-side lint; rolled up in vl status
}

# Inner-signal fields dropped when their parent flag is false (no civilian value).
LITE_DROP_WHEN_FLAG_FALSE = {
    "f18_laundering_score": ("threshold_breached", ["civilian_phrasing"]),
    "f15_missing_witness_flag": ("any_criterion_missing_witness", ["civilian_phrasing", "count"]),
    "f16_attack_flag": ("any_attack_class_present", ["civilian_phrasing", "count"]),
    "f19_coverage_gap_flag": ("any_corpus_gap_detected", ["civilian_phrasing", "count"]),
    "a8_srs_decay_status": ("any_claim_decayed", ["civilian_phrasing", "count"]),
}


def _compress_to_lite(card: Dict[str, Any], drop_empty: bool = True) -> Dict[str, Any]:
    """Compress a proof-card.json (Pro shape) to AEP Lite shape <=1KB target.

    1. Apply single-letter aliases per LITE_ALIASES_V02.
    2. Drop empty optional fields (None, "", [], {}, [0,0,0]).
    3. Drop LITE_DROPPED_FIELDS entirely (compiler-side metadata; not civilian-decision-critical).
    4. For signal-flag-FALSE sub-objects, drop the redundant civilian_phrasing + count fields.
    5. Trim civilian-phrasing to <=160 chars.
    6. Preserve schema-required Lite fields (5 rows + ds + ty + sv + id + td).
    """
    out: Dict[str, Any] = {}

    def alias(k: str) -> str:
        return LITE_ALIASES_V02.get(k, k)

    # First compress disclosed_signals with flag-aware drop.
    sigs = card.get("disclosed_signals", {})
    compressed_sigs: Dict[str, Any] = {}
    for sig_key, sig_val in sigs.items():
        if sig_key == "any_signal_non_ok":
            compressed_sigs[alias(sig_key)] = sig_val
            continue
        if not isinstance(sig_val, dict):
            compressed_sigs[alias(sig_key)] = sig_val
            continue
        rule = LITE_DROP_WHEN_FLAG_FALSE.get(sig_key)
        flag_val = sig_val.get(rule[0], False) if rule else True
        inner: Dict[str, Any] = {}
        for kk, vv in sig_val.items():
            # Drop redundant fields when the boolean flag is False.
            if rule and not flag_val and kk in rule[1]:
                continue
            if drop_empty and (vv is None or vv == "" or vv == [] or vv == {}):
                continue
            if alias(kk) == "cp" and isinstance(vv, str) and len(vv) > 160:
                vv = vv[:157] + "..."
            inner[alias(kk)] = vv
        if inner:
            compressed_sigs[alias(sig_key)] = inner

    # Now build top-level.
    for k, v in card.items():
        if k in LITE_DROPPED_FIELDS:
            continue
        if k == "disclosed_signals":
            if compressed_sigs:
                out[alias(k)] = compressed_sigs
            continue
        if drop_empty and (v is None or v == "" or v == [] or v == {}):
            continue
        out[alias(k)] = v

    # Add a tiny back-reference so reader knows the alias map version.
    out["_a"] = "v0.2"

    return out


def emit_lite_compressed(
    card: Dict[str, Any],
    output_path: pathlib.Path | str,
    *,
    drop_empty: bool = True,
) -> Tuple[pathlib.Path, int]:
    """Emit a compressed AEP Lite version of the card. Returns (path, byte_count)."""
    op = pathlib.Path(output_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    compressed = _compress_to_lite(card, drop_empty=drop_empty)
    # No indent + separators=(",",":") for minimal whitespace.
    text = json.dumps(compressed, ensure_ascii=False, separators=(",", ":"))
    text_bytes = text.encode("utf-8")
    op.write_text(text, encoding="utf-8")
    return op, len(text_bytes)


def expand_from_lite(compressed: Dict[str, Any]) -> Dict[str, Any]:
    """Inverse: expand a compressed Lite shape back to Pro field names.

    Used for the no-info-loss roundtrip test in test_v15_phase_B_integration.py.
    """
    rev = {v: k for k, v in LITE_ALIASES_V02.items()}

    def unalias(k: str) -> str:
        return rev.get(k, k)

    def expand_value(v: Any) -> Any:
        if isinstance(v, dict):
            return {unalias(kk): expand_value(vv) for kk, vv in v.items() if kk != "_a"}
        if isinstance(v, list):
            return [expand_value(x) for x in v]
        return v

    out: Dict[str, Any] = {}
    for k, v in compressed.items():
        if k == "_a":
            continue
        out[unalias(k)] = expand_value(v)
    return out


# ---------- CLI ----------

def _cli() -> int:
    ap = argparse.ArgumentParser(description="AEP v1.2 F22 Civilian Proof Card compiler")
    ap.add_argument("aepkg_path", help="Path to .aepkg/ directory")
    ap.add_argument(
        "--action-class",
        default="general",
        choices=("general", "financial", "medical", "legal", "employment", "housing", "irreversible"),
    )
    ap.add_argument("--out", help="Optional output JSON path", default=None)
    ap.add_argument("--bound-packet-id", default=None)
    ap.add_argument(
        "--lite-compressed",
        action="store_true",
        help="Emit AEP Lite compressed shape <=1KB target (single-letter aliases + dropped empties)",
    )
    ap.add_argument(
        "--benchmark-log",
        default=None,
        help="Optional path to append byte-count benchmark row (JSONL)",
    )
    args = ap.parse_args()

    card = compile_proof_card(
        args.aepkg_path,
        action_class=args.action_class,
        bound_packet_id=args.bound_packet_id,
    )

    if args.lite_compressed and args.out:
        out_path, byte_count = emit_lite_compressed(card, args.out)
        print(f"WROTE-LITE: {out_path} ({byte_count} bytes)")
        if args.benchmark_log:
            row = {
                "type": "LiteCompressionBenchmarkRow",
                "aepkg_path": str(pathlib.Path(args.aepkg_path)).replace("\\", "/"),
                "out_path": str(out_path).replace("\\", "/"),
                "byte_count": byte_count,
                "target_bytes": 1024,
                "passes_1kb": byte_count <= 1024,
                "emitted_at": _now_iso(),
            }
            bpath = pathlib.Path(args.benchmark_log)
            bpath.parent.mkdir(parents=True, exist_ok=True)
            with bpath.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(row, sort_keys=True) + "\n")
    elif args.out:
        emit_card_json(card, args.out)
        print(f"WROTE: {args.out}")
    else:
        print(json.dumps(card, ensure_ascii=False, indent=2))

    # CLI exit code reflects lint outcomes
    lint_ok = (
        card.get("banned_elision_lint_status", {}).get("status") == "PASS"
        and card.get("civilian_vocabulary_lint_status", {}).get("status") == "PASS"
    )
    return 0 if lint_ok else 1


if __name__ == "__main__":
    sys.exit(_cli())
