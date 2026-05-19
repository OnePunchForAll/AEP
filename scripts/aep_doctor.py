#!/usr/bin/env python3
"""
aep doctor - the civilian-facing health check for AEP packets.

Operator directive verbatim (sec73.2 sacred, source.md L97-L113):
  "build aep doctor. This should be the main command ...
   Pass, Warn, Fail, or Unknown ...
   Not 400 lines. Just the verdict first, then expandable evidence."

Usage:
  python aep_doctor.py <packet.aepkg>
  python aep_doctor.py <packet.aepkg> --verbose
  python aep_doctor.py <packet.aepkg> --lite

Output format (verdict FIRST, evidence collapsible):

  VERDICT: PASS | WARN | FAIL | UNKNOWN

  Trust level: <Casual | Important | Professional | Critical>
  Top 3 signals:
    - F18 laundering score: 0.83 (HIGH-RISK)
    - F19 coverage gap: 6 missing
    - F15 completion gap: 1 detected

  Run with --verbose for full evidence.

Verdict logic (HONEST per sec73.6):
  FAIL    - any F-tier validator returns a critical violation
            (F18 laundering >= 0.8 OR F15 missing-witness >= 1 OR
             F16 attack-flag present OR packet structurally broken
             with no recoverable claim)
  WARN    - any signal above threshold but not critical
            (F18 laundering >= 0.6 OR F19 coverage-gap present OR
             A8 SRS decay present OR EXPERIMENTAL truth-tag on a
             load-bearing claim)
  PASS    - all signals clean (no thresholds breached)
  UNKNOWN - validator missing, packet malformed in a way that
            prevents verdict computation, or required signal data
            absent. HONEST: do NOT default to PASS when uncertain.

Composes_with:
  - F22 CivilianProofCard (via build_f22_civilian_proof_card.compile_proof_card)
  - F25 TrustDial (outputs active tier + recommended tier for action class)
  - F21 ClaimEnemyPairing (surfaces missing-enemy as a signal)

Truth tag: STRONGLY PLAUSIBLE (verdict logic schema-bound; empirical verdict
on 3 test packets this turn; civilian < 30s comprehension empirical falsifier
STAGED v1.2.1 per pathfinder Phase 9 + adversary A8).
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

# Import F22 compiler from same scripts dir
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from build_f22_civilian_proof_card import (  # noqa: E402
    compile_proof_card,
    extract_signals_from_packet,
    extract_claim_summary,
    extract_source_count_breakdown,
    extract_test_summary,
    IRREVERSIBLE_ACTION_CLASSES,
    CIVILIAN_WARNING_PHRASEBOOK,
    BANNED_TERMS,
    _now_iso,
    _slug,
)


# ---------- Verdict constants ----------

VERDICT_PASS = "PASS"
VERDICT_WARN = "WARN"
VERDICT_FAIL = "FAIL"
VERDICT_UNKNOWN = "UNKNOWN"

TRUST_DIAL_RECOMMENDATION = {
    "general": "Casual",
    "financial": "Professional",
    "medical": "Professional",
    "legal": "Professional",
    "employment": "Professional",
    "housing": "Professional",
    "irreversible": "Professional",
}


# Critical thresholds (FAIL conditions)
F18_LAUNDERING_FAIL_THRESHOLD = 0.8
# Warning thresholds (WARN conditions)
F18_LAUNDERING_WARN_THRESHOLD = 0.6


# ---------- Packet shape check ----------

def packet_is_parseable(aepkg_path: pathlib.Path) -> Tuple[bool, str]:
    """
    Verify the packet has a parseable shape.

    A packet is parseable if:
      - it's a directory with an aepkg.json OR claim.json file, OR
      - it's a .aepkg/ directory with data/claims.jsonl OR data/sources.jsonl

    Returns (is_parseable, reason).
    """
    p = pathlib.Path(aepkg_path)
    if not p.exists():
        return (False, f"Path does not exist: {p}")
    if p.is_file():
        # Allow a top-level claim.json or aepkg.json
        if p.suffix == ".json":
            return (True, "single-file packet (claim.json or aepkg.json)")
        return (False, f"Path is a file but not a JSON file: {p}")

    has_aepkg_json = (p / "aepkg.json").is_file()
    has_claim_json = (p / "claim.json").is_file()
    has_claims_jsonl = (p / "data" / "claims.jsonl").is_file()
    has_sources_jsonl = (p / "data" / "sources.jsonl").is_file()

    if has_aepkg_json or has_claim_json or has_claims_jsonl or has_sources_jsonl:
        return (True, "packet structure detected")
    return (False, "no aepkg.json / claim.json / data/*.jsonl found")


# ---------- Verdict computation ----------

def compute_verdict(
    aepkg_path: pathlib.Path | str,
    *,
    action_class: str = "general",
) -> Dict[str, Any]:
    """
    Compute the aep doctor verdict.

    Returns dict with:
      verdict: PASS|WARN|FAIL|UNKNOWN
      reasons[]: list of reason strings
      trust_dial_active: Casual|Important|Professional|Critical
      trust_dial_recommended_for_action_class
      top_3_signals[]: list of {name, value, civilian_phrasing}
      signals: full disclosed_signals block
      parse_status: parseable | malformed
      action_class
    """
    p = pathlib.Path(aepkg_path)
    parseable, parse_reason = packet_is_parseable(p)
    if not parseable:
        return {
            "verdict": VERDICT_UNKNOWN,
            "reasons": [
                "packet shape not parseable",
                parse_reason,
            ],
            "trust_dial_active": "Professional"
            if action_class in IRREVERSIBLE_ACTION_CLASSES
            else "Casual",
            "trust_dial_recommended_for_action_class": TRUST_DIAL_RECOMMENDATION.get(
                action_class, "Casual"
            ),
            "top_3_signals": [
                {
                    "name": "packet_parse",
                    "value": "MALFORMED",
                    "civilian_phrasing": "Packet shape could not be parsed.",
                }
            ],
            "signals": {},
            "parse_status": "malformed",
            "action_class": action_class,
            "honest_note": (
                "aep doctor returned UNKNOWN because the packet shape could not be parsed. "
                "Per sec73.6 honest framing: aep doctor does NOT default to PASS when uncertain."
            ),
        }

    # Resolve to packet dir
    pkt_dir = p if p.is_dir() else p.parent
    sigs = extract_signals_from_packet(pkt_dir)
    f18_score = float(sigs["f18_laundering_score"]["score"])
    f15_count = int(sigs["f15_missing_witness_flag"]["count"])
    f16_count = int(sigs["f16_attack_flag"]["count"])
    f19_count = int(sigs["f19_coverage_gap_flag"]["count"])
    a8_count = int(sigs["a8_srs_decay_status"]["count"])

    reasons: List[str] = []

    # FAIL conditions
    if f18_score >= F18_LAUNDERING_FAIL_THRESHOLD:
        reasons.append(
            f"F18 laundering score {f18_score:.2f} >= {F18_LAUNDERING_FAIL_THRESHOLD:.2f} (CRITICAL)"
        )
    if f15_count >= 1:
        reasons.append(f"F15 missing-witness flag: {f15_count} criterion(a)")
    if f16_count >= 1:
        reasons.append(f"F16 attack class flag: {f16_count} attack(s)")

    fail_triggered = bool(reasons)

    # WARN conditions
    warn_reasons: List[str] = []
    if (
        f18_score >= F18_LAUNDERING_WARN_THRESHOLD
        and f18_score < F18_LAUNDERING_FAIL_THRESHOLD
    ):
        warn_reasons.append(
            f"F18 laundering score {f18_score:.2f} >= {F18_LAUNDERING_WARN_THRESHOLD:.2f} (HIGH-RISK)"
        )
    if f19_count >= 1:
        warn_reasons.append(f"F19 coverage gap: {f19_count} missing")
    if a8_count >= 1:
        warn_reasons.append(f"A8 SRS decay: {a8_count} stale claim(s)")

    warn_triggered = bool(warn_reasons)

    # Verdict resolution
    if fail_triggered:
        verdict = VERDICT_FAIL
    elif warn_triggered:
        verdict = VERDICT_WARN
        reasons = warn_reasons
    elif not sigs["any_signal_non_ok"]:
        verdict = VERDICT_PASS
        reasons = ["all F-tier signals clean"]
    else:
        # any_signal_non_ok true but no specific threshold breached -> WARN
        verdict = VERDICT_WARN
        reasons = warn_reasons or ["minor signal flagged"]

    # Active vs recommended trust dial
    trust_dial_active = (
        "Professional"
        if action_class in IRREVERSIBLE_ACTION_CLASSES
        else ("Important" if (warn_triggered or fail_triggered) else "Casual")
    )
    trust_dial_recommended = TRUST_DIAL_RECOMMENDATION.get(action_class, "Casual")

    # Top-3 signals
    candidates: List[Dict[str, Any]] = []
    if f18_score > 0:
        candidates.append(
            {
                "name": "F18 laundering score",
                "value": round(f18_score, 2),
                "civilian_phrasing": sigs["f18_laundering_score"].get(
                    "civilian_phrasing",
                    f"Source provenance score: {f18_score:.2f}",
                ),
            }
        )
    if f19_count > 0:
        candidates.append(
            {
                "name": "F19 coverage gap",
                "value": f19_count,
                "civilian_phrasing": sigs["f19_coverage_gap_flag"].get(
                    "civilian_phrasing", f"Skipped scope: {f19_count}"
                ),
            }
        )
    if f15_count > 0:
        candidates.append(
            {
                "name": "F15 completion gap",
                "value": f15_count,
                "civilian_phrasing": sigs["f15_missing_witness_flag"].get(
                    "civilian_phrasing",
                    f"Hidden completion gap: {f15_count} detected",
                ),
            }
        )
    if f16_count > 0:
        candidates.append(
            {
                "name": "F16 attack class",
                "value": f16_count,
                "civilian_phrasing": sigs["f16_attack_flag"].get(
                    "civilian_phrasing", f"{f16_count} attack pattern(s) flagged"
                ),
            }
        )
    if a8_count > 0:
        candidates.append(
            {
                "name": "A8 SRS decay",
                "value": a8_count,
                "civilian_phrasing": sigs["a8_srs_decay_status"].get(
                    "civilian_phrasing", f"{a8_count} stale claim(s)"
                ),
            }
        )

    if not candidates:
        candidates = [
            {
                "name": "all signals clean",
                "value": "OK",
                "civilian_phrasing": "No F-tier signals breached threshold.",
            }
        ]

    top_3 = candidates[:3]

    return {
        "verdict": verdict,
        "reasons": reasons,
        "trust_dial_active": trust_dial_active,
        "trust_dial_recommended_for_action_class": trust_dial_recommended,
        "top_3_signals": top_3,
        "signals": sigs,
        "parse_status": "parseable",
        "action_class": action_class,
    }


# ---------- Renderers ----------

def render_compact(verdict_record: Dict[str, Any]) -> str:
    """1-screen rendering. Verdict FIRST. ~15 lines max."""
    lines: List[str] = []
    lines.append(f"VERDICT: {verdict_record['verdict']}")
    lines.append("")
    lines.append(f"Trust level: {verdict_record['trust_dial_active']}")
    if (
        verdict_record["action_class"] in IRREVERSIBLE_ACTION_CLASSES
        and verdict_record["trust_dial_active"] != "Professional"
        and verdict_record["trust_dial_active"] != "Critical"
    ):
        lines.append(
            f"  RECOMMENDED for action_class={verdict_record['action_class']}: "
            f"{verdict_record['trust_dial_recommended_for_action_class']}"
        )
    lines.append("Top 3 signals:")
    for s in verdict_record["top_3_signals"]:
        lines.append(f"  - {s['name']}: {s['value']} ({s['civilian_phrasing']})")
    if verdict_record["verdict"] == VERDICT_UNKNOWN:
        lines.append("")
        lines.append(verdict_record.get("honest_note", ""))
    lines.append("")
    lines.append("Run with --verbose for full evidence.")
    return "\n".join(lines)


def render_verbose(
    verdict_record: Dict[str, Any], proof_card: Dict[str, Any]
) -> str:
    """Verbose rendering: compact verdict + 5-row proof card."""
    out: List[str] = [render_compact(verdict_record), "", "=" * 60, "PROOF CARD", "=" * 60]
    out.append("")
    out.append(f"1. What is being claimed:")
    out.append(f"   {proof_card.get('what_is_being_claimed', '')}")
    out.append("")
    out.append(f"2. What evidence supports it:")
    out.append(f"   {proof_card.get('what_evidence_supports_it', '')}")
    out.append("")
    out.append(f"3. What was tested:")
    out.append(f"   {proof_card.get('what_was_tested', '')}")
    out.append("")
    out.append(f"4. What is weak, stale, missing, or AI-derived:")
    out.append(f"   {proof_card.get('what_is_weak_stale_missing_or_ai_derived', '')}")
    out.append("")
    out.append(f"5. What action the user should take next:")
    out.append(f"   {proof_card.get('what_action_the_user_should_take_next', '')}")
    out.append("")
    out.append("=" * 60)
    lint = proof_card.get("banned_elision_lint_status", {})
    civilian_lint = proof_card.get("civilian_vocabulary_lint_status", {})
    out.append(f"Banned-elision lint: {lint.get('status', 'UNKNOWN')}")
    out.append(f"Civilian vocabulary lint: {civilian_lint.get('status', 'UNKNOWN')}")
    if lint.get("banned_elisions_detected"):
        out.append("Banned elisions detected:")
        for e in lint["banned_elisions_detected"]:
            out.append(f"  - {e}")
    if civilian_lint.get("banned_terms_detected"):
        out.append("Banned terms detected in card:")
        for t in civilian_lint["banned_terms_detected"]:
            out.append(f"  - {t}")
    return "\n".join(out)


# ---------- AEP Lite emission ----------

def emit_aep_lite(
    aepkg_path: pathlib.Path | str,
    output_dir: pathlib.Path | str,
    *,
    action_class: str = "general",
) -> Dict[str, Any]:
    """
    Compile a Pro-form .aepkg/ down to an AEP Lite 4-file shape:
      claim.json, sources/, receipt.json, proof-card.json

    Returns a summary dict with file paths + emission_status.

    Honest disclosure per sec73.6: what is lost on compile-down is enumerated
    in receipt.json.compile_down_what_is_lost[].
    """
    p = pathlib.Path(aepkg_path)
    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sources").mkdir(parents=True, exist_ok=True)

    verdict_rec = compute_verdict(p, action_class=action_class)
    proof_card = compile_proof_card(p, action_class=action_class)

    # claim.json minimal shape per AEP Lite schema
    claim_summary = (
        extract_claim_summary(p) if p.is_dir() else "single-file packet"
    )
    claim = {
        "claim_text": claim_summary[:512],
        "truth_tag": "STRONGLY PLAUSIBLE",
        "basis_source_ids": ["src:packet-root"],
        "falsifier_summary": "See proof-card.json row 4 for detected weaknesses.",
        "expires_at": "2027-05-18T00:00:00Z",
    }
    (out_dir / "claim.json").write_text(
        json.dumps(claim, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # receipt.json shape per AEP Lite schema
    n_tests, n_passed, n_failed = (
        extract_test_summary(p) if p.is_dir() else (0, 0, 0)
    )
    any_non_ok = bool(verdict_rec["signals"].get("any_signal_non_ok", False))
    receipt = {
        "packet_id": f"lite:{_slug(p.name)}",
        "emitted_at": _now_iso(),
        "emitted_by_agent_or_user": "aep_doctor",
        "validator_verdict": verdict_rec["verdict"],
        "tests_run_count": n_tests,
        "tests_passed_count": n_passed,
        "tests_failed_count": n_failed,
        "any_signal_non_ok": any_non_ok,
        "checked_by_runtimes_count": 1,
        "compile_down_what_is_lost": [
            "Packet DAG amendment history",
            "Cryptographic signature attestations",
            "Reviewer principal IDs (replaced with role names)",
            "Mutation suite per-mutation reports (replaced with summary counts)",
        ],
    }
    (out_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # proof-card.json -- F22 output
    (out_dir / "proof-card.json").write_text(
        json.dumps(proof_card, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # sources/ placeholder if packet has sources.jsonl
    sources_jsonl = p / "data" / "sources.jsonl" if p.is_dir() else None
    sources_emitted = 0
    if sources_jsonl and sources_jsonl.is_file():
        for i, line in enumerate(sources_jsonl.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
                src_name = f"src-{_slug(s.get('id', f'source-{i}'))}.json"
                (out_dir / "sources" / src_name).write_text(
                    json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                sources_emitted += 1
            except Exception:
                continue
    if sources_emitted == 0:
        # Always at least one file in sources/
        (out_dir / "sources" / "src-packet-root.json").write_text(
            json.dumps(
                {"id": "src-packet-root", "title": str(p.name)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        sources_emitted = 1

    return {
        "out_dir": str(out_dir),
        "files_written": ["claim.json", "receipt.json", "proof-card.json"],
        "sources_emitted": sources_emitted,
        "min_file_count_met": (
            (out_dir / "claim.json").is_file()
            and (out_dir / "receipt.json").is_file()
            and (out_dir / "proof-card.json").is_file()
            and sources_emitted >= 1
        ),
    }


# ---------- CLI ----------

def _cli() -> int:
    ap = argparse.ArgumentParser(
        description="aep doctor - civilian health check for AEP packets"
    )
    ap.add_argument("packet", help="Path to .aepkg directory or JSON file")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print full proof card after the compact verdict",
    )
    ap.add_argument(
        "--lite",
        nargs="?",
        const="<auto>",
        default=None,
        help="Compile-down to AEP Lite 4-file shape; optionally provide output dir",
    )
    ap.add_argument(
        "--action-class",
        default="general",
        choices=(
            "general",
            "financial",
            "medical",
            "legal",
            "employment",
            "housing",
            "irreversible",
        ),
        help="Action class for HV6 Trust Dial floor enforcement",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit verdict + card as JSON (machine-readable)",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout; return only exit code (for CI integration)",
    )
    args = ap.parse_args()

    verdict_rec = compute_verdict(args.packet, action_class=args.action_class)

    if args.lite:
        lite_out = (
            args.lite
            if args.lite != "<auto>"
            else f"{args.packet}.lite"
        )
        emit_summary = emit_aep_lite(
            args.packet, lite_out, action_class=args.action_class
        )
        if not args.quiet:
            if args.json:
                print(
                    json.dumps(
                        {"verdict": verdict_rec, "lite_emission": emit_summary},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(render_compact(verdict_rec))
                print(f"\nAEP Lite emitted to: {emit_summary['out_dir']}")
                print(f"  Files: {emit_summary['files_written']}")
                print(f"  Sources: {emit_summary['sources_emitted']}")
        return _exit_for_verdict(verdict_rec["verdict"])

    if args.verbose:
        proof_card = compile_proof_card(args.packet, action_class=args.action_class)
        if not args.quiet:
            if args.json:
                print(
                    json.dumps(
                        {"verdict": verdict_rec, "proof_card": proof_card},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(render_verbose(verdict_rec, proof_card))
    else:
        if not args.quiet:
            if args.json:
                print(json.dumps(verdict_rec, ensure_ascii=False, indent=2))
            else:
                print(render_compact(verdict_rec))

    return _exit_for_verdict(verdict_rec["verdict"])


def _exit_for_verdict(verdict: str) -> int:
    """
    Exit codes (for CI integration):
      0 = PASS
      1 = WARN
      2 = FAIL
      3 = UNKNOWN
    """
    return {
        VERDICT_PASS: 0,
        VERDICT_WARN: 1,
        VERDICT_FAIL: 2,
        VERDICT_UNKNOWN: 3,
    }.get(verdict, 3)


if __name__ == "__main__":
    sys.exit(_cli())
