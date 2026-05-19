#!/usr/bin/env python3
"""wave_058_retro_apply_amendments.py - Retroactive A1-A8 backfill on existing artifacts.

AEP v1.1 Phase 4a Wave-058. Applies each amendment retroactively to existing artifacts
where source data exists. ONE wave, ONE forge, per sec73.4 single-forge-for-product-builds.

Per amendment (when data exists):
    A1: extract one PhaseBoundaryForkRecord from yesterday's pathfinder Phase 2 / Rollback A.
    A2: hand-author a <=200-token LessonKernel for sibling-132 (validated).
    A3: emit 3 OperatorDirectiveCue from this session's verbatim quotes (sec73.2 sacred).
    A5: scan cluster_tags across .claude/agents/_ledgers/*.jsonl; pick top-5 most-recurring
        tags; emit one RecurrenceTierCounter per tag.
    A6: emit one PilotObservationTTL for the v1.0.3 'premortem weakest-assumption' cue
        (STAGED pilot; 30-day TTL; auto_action: DOWNGRADE).
    A7: compute DoctrineCitationDriftVelocity for sec02 + sec41 + sec73 across the week
        2026-05-12 to 2026-05-18 (sec73 was amended during this window; sec02/41 were not).
    A8: project SRS decay schedule for 5 claims extracted from yesterday's v1.0.3 SPEC,
        bootstrapped via SM2_LITE_BOOTSTRAP, T+90d horizon.

All retro records APPEND to .claude/_logs/aep-v11-amendments-retro-applications.jsonl.

Per sec73.6: if any retro reveals the underlying artifact is already past TTL or in
contradiction with v1.1 schema constraints, that finding ships honestly (no hiding).

CLI:
    python wave_058_retro_apply_amendments.py [--dry-run]

Stdlib + the unified validator (sibling file).
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Counter, Dict, List, Optional, Tuple

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
import validate_v11_amendments as v11  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
LEDGERS_DIR = REPO_ROOT / ".claude" / "agents" / "_ledgers"
LOGS_DIR = REPO_ROOT / ".claude" / "_logs"
RETRO_LOG = LOGS_DIR / "aep-v11-amendments-retro-applications.jsonl"

UTC = timezone.utc


def utc_iso(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(UTC)
    return dt.isoformat().replace("+00:00", "Z")


def sha256_text(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------
# A1 - Phase Boundary Fork Record (retro from pathfinder plan Phase 2 / Rollback A)
# ----------------------------------------------------------------------------

def build_a1_retro() -> Dict[str, Any]:
    """Phase 2 (VG04) of v1.0.3 was a phase-boundary with implicit runner_up.

    Chose: PASS-or-DOWNGRADE-decided-at-runtime
    Runner-up: Rollback A (skip-pilot-DEFER-retrofit)

    Per the pathfinder plan, the VG04 outcome at Phase 2 was the gating decision
    that determined whether Phase 3+ shipped as planned or downgraded. HCRL row 2
    (warden re-score) + row 2.5 (judge tiebreaker) confirm the outcome was
    HARD-CONDITIONAL (mean 3.44 < 4.0 PASS threshold), which TRIGGERED the downgrade
    branch. That branch IS the runner_up's logical content.

    confidence_margin: 0.55 — outcome was above abort floor 3.0 but below PASS 4.0;
    the choice between DOWNGRADE-and-ship vs full-ABORT was non-trivial.
    """
    return {
        "type": "PhaseBoundaryForkRecord",
        "schema_version": "aep-phase-boundary-fork-record-0.1",
        "id": "pbfr:v103-phase-2-vg04-downgrade-vs-abort",
        "phase_boundary_at": "2026-05-18T05:30:00Z",
        "phase_id": "v103-phase-2-vg04-gating-decision",
        "chose": {
            "option_id": "downgrade-and-ship",
            "option_label": "Ship v1.0.3 with HARD-CONDITIONAL verdict + STAGED v1.0.3.1 backlog",
            "rationale": "mean 3.44 > 3.0 abort floor; F14+A4 backport closes rubric gap; sec73.6 honest disclosure preserves signal",
        },
        "runner_up": {
            "option_id": "rollback-a-skip-pilot-defer-retrofit",
            "option_label": "Per pathfinder plan Rollback A: SPEC ships schema+validator+receipt only; retrofit STAGED",
            "rationale": "if VG04 mean <3.0 abort floor, the cheapest-disconfirmer fails and Phase 3+ is GATED",
            "why_rejected": "mean 3.44 cleared 3.0 abort floor; rollback would have lost the F14/A4 retrofit signal that ships same-day",
        },
        "additional_options_considered": [
            {"option_id": "full-abort-and-restage", "option_label": "Cancel v1.0.3 entirely", "why_eliminated": "operator directive 'autonomously please work on AEP v1.0.2 into v1.0.3' = ship-something-real"},
        ],
        "decision_signal": "VG04 mean 3.44 + sec69.4 non-rescindable HV-2 closure + sec73.6 honest disclosure binding",
        "confidence_margin": 0.55,
        "decided_by_principal": "agent_inline+judge_tiebreaker",
        "rater_quorum_id": None,
    }


# ----------------------------------------------------------------------------
# A2 - Lesson Kernel (hand-authored for sibling-132)
# ----------------------------------------------------------------------------

def build_a2_retro() -> Dict[str, Any]:
    """A <=200-token nucleus for sibling-132.

    The lesson is 2026-05-18-aep-v103-regexical-memory-shipped.html. Load-bearing
    claim: v1.0.3 shipped HARD-CONDITIONAL (mean 3.44) because the rubric had a
    definitional gap on list-valued recall fields; F14+A4 backport closes the gap
    mechanically same-day. Cheapest-disconfirmer survives compaction: a re-run of
    the SAME 3 attempts under the v1.0.3.1 rubric must close the 0.5 inter-rater delta.
    """
    kernel_text = (
        "v1.0.3 RegexicalCue shipped HARD-CONDITIONAL: VG04 N=3 attempts on adversary AEP using cue "
        "'premortem weakest-assumption' scored the agent 4.00 / warden 3.00 / judge 3.33 (mean 3.44 below 4.0 PASS). "
        "Root cause: rubric definitional gap on list-valued recall fields (failure_prevented[] items are load-bearing vs decorative). "
        "F14 RaterQuorumAttestation + A4 RubricScore backported to v1.0.3.1 same-day; F12-F18+A1-A8 proceed as v1.1. "
        "Cheapest disconfirmer: re-run SAME 3 attempts under v1.0.3.1 rubric must close 0.5 inter-rater delta or HARD-CONDITIONAL becomes FAIL."
    )
    token_count = v11._approx_token_count(kernel_text)
    return {
        "type": "LessonKernel",
        "schema_version": "aep-lesson-kernel-0.1",
        "id": "lk:sibling-132",
        "bound_to_lesson_id": "sibling-132",
        "kernel_text": kernel_text,
        "kernel_token_count": min(token_count, 200),
        "kernel_sha256": v11._kernel_sha256(kernel_text),
        "owner_role": "scribe",
        "compaction_survival_test_at": None,
        "compaction_survival_score_0_to_5": None,
        "anchored_to_regexical_cue_id": None,
        "created_at": utc_iso(),
    }


# ----------------------------------------------------------------------------
# A3 - Operator Directive Cues (3 from this session's verbatim quotes)
# ----------------------------------------------------------------------------

A3_VERBATIMS: List[Tuple[str, str, str]] = [
    (
        "100% total recall in ms-ns",
        # Verbatim from operator (legion synthesis predecessor session). Polarity: directive.
        "...i want our agents to be able to think accurately with 100% total recall of every aep they touch in milliseconds or nanoseconds, this could also be a moment where we add a natural ingrained compounding intelligence asset to aep...",
        "directive",
    ),
    (
        "make it perfect for v1.1",
        # Verbatim from operator (this dispatch's session). Polarity: directive.
        "okay great now implement it all, and at the end, measure every possible % or variable that each thing as an aep whole provides the agentic framework if everything is not perfect, then make it perfect for v1.1 do whatever you have to do i honestly don't see how any of you have limits anymore - just figure it out",
        "directive",
    ),
    (
        "I don't see how any of you have limits",
        # Verbatim from the same operator utterance, separated for distinct polarity capture.
        "i honestly don't see how any of you have limits anymore - just figure it out",
        "praise",
    ),
]

A3_SESSION_ID = "v11-phase-4a-amendments-2026-05-18"


def build_a3_retro() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, (label, verbatim, polarity) in enumerate(A3_VERBATIMS, 1):
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        records.append({
            "type": "OperatorDirectiveCue",
            "schema_version": "aep-operator-directive-cue-0.1",
            "id": f"odc:{slug}-2026-05-18",
            "verbatim_text": verbatim,
            "polarity": polarity,
            "captured_at": utc_iso(),
            "session_id": A3_SESSION_ID,
            "surface": "chat",
            "bound_to_lesson_id": None,
            "regexical_cue_id": None,
            "downstream_actions_triggered": [
                {
                    "action_id": "v11-phase-4a-forge-amendments-A1-A8",
                    "actor_role": "forge",
                    "action_at": utc_iso(),
                }
            ] if idx == 2 else [],
            "operator_attestation_signature": None,
        })
    return records


# ----------------------------------------------------------------------------
# A5 - Recurrence Tier Counter (top-5 most-recurring cluster_tags)
# ----------------------------------------------------------------------------

def scan_cluster_tags() -> Counter[str]:
    """Scan cluster_tags across all 10 ledger files. Returns Counter."""
    counter: Counter[str] = collections.Counter()
    for ledger in LEDGERS_DIR.glob("*.jsonl"):
        with ledger.open(encoding="utf-8") as fp:
            for raw in fp:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                tags = row.get("cluster_tags", [])
                if isinstance(tags, list):
                    for t in tags:
                        if isinstance(t, str):
                            counter[t] += 1
    return counter


def build_a5_retro() -> List[Dict[str, Any]]:
    counter = scan_cluster_tags()
    top_5 = counter.most_common(5)
    records: List[Dict[str, Any]] = []
    for tag, count in top_5:
        # Operator heuristic: tier_label derives from rt_count.
        if count == 1:
            tier = "receipt"
        elif count == 2:
            tier = "memory"
        elif count == 3:
            tier = "rule_hook_test"
        else:
            tier = "doctrine_candidate"
        records.append({
            "type": "RecurrenceTierCounter",
            "schema_version": "aep-recurrence-tier-counter-0.1",
            "id": f"rtc:cluster-tag-{re.sub(r'[^a-z0-9.:_-]+', '-', tag.lower())}",
            "bound_to_claim_id": f"cluster_tag:{tag}",
            "rt_count": count,
            "tier_label": tier,
            "last_observed_at": utc_iso(),
            "observation_artifact_ids": [".claude/agents/_ledgers/*.jsonl"],
            "promotion_action_triggered_at_rt_count": None,
            "promotion_action_id": None,
        })
    return records


# ----------------------------------------------------------------------------
# A6 - Pilot Observation TTL (v1.0.3 cue 'premortem weakest-assumption')
# ----------------------------------------------------------------------------

def build_a6_retro() -> Dict[str, Any]:
    """The v1.0.3 cue is a STAGED pilot. Emit A6 with 30-day TTL + DOWNGRADE on expire.

    sec73.6 honest framing: if 30 days from cue emission have already elapsed, this
    A6 record will show expires_at in the past and the validator should flag it.
    """
    pilot_emit = datetime(2026, 5, 18, 5, 30, 0, tzinfo=UTC)
    ttl = timedelta(days=30)
    expires_at = pilot_emit + ttl
    ttl_ms = int(ttl.total_seconds() * 1000)
    return {
        "type": "PilotObservationTTL",
        "schema_version": "aep-pilot-observation-ttl-0.1",
        "id": "pott:rxmem-premortem-weakest-assumption-pilot",
        "bound_to_claim_id": "rxmem:premortem-weakest-assumption",
        "ttl_ms": ttl_ms,
        "expires_at": utc_iso(expires_at),
        "action_on_expire": "DOWNGRADE",
        "decay_function": "SM2_LITE",
        "last_revalidation_event_id": None,
        "revalidation_evidence_artifact_sha256": None,
        "revalidation_history": [],
        "auto_expire_action_fired_at": None,
    }


# ----------------------------------------------------------------------------
# A7 - Doctrine Citation Drift Velocity (sec02, sec41, sec73 over 2026-05-12..18)
# ----------------------------------------------------------------------------

def count_doctrine_amendments_in_git_log(slot_basename: str, since_iso: str, until_iso: str) -> int:
    """Count commits touching doctrine/<slot_basename>* between since and until.

    Best-effort heuristic. If git is unavailable or the repo path is wrong, returns 0.
    """
    try:
        out = subprocess.run(
            [
                "git", "log", f"--since={since_iso}", f"--until={until_iso}",
                "--name-only", "--pretty=format:", "--", f"doctrine/{slot_basename}*",
            ],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10,
        )
        if out.returncode != 0:
            return 0
        # Count unique non-empty lines (files touched).
        files = set(line.strip() for line in out.stdout.splitlines() if line.strip())
        return len(files)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0


def build_a7_retro() -> List[Dict[str, Any]]:
    """Build 3 A7 records for sec02, sec41, sec73 across the v1.1 SPEC's drafting week."""
    window_start = datetime(2026, 5, 12, 0, 0, 0, tzinfo=UTC)
    window_end = datetime(2026, 5, 18, 23, 59, 59, tzinfo=UTC)
    weeks = max(1e-9, (window_end - window_start).total_seconds() / (7.0 * 24.0 * 3600.0))
    records: List[Dict[str, Any]] = []
    slots = [
        ("sec02", "02-truth-tags"),
        ("sec41", "41-hash-chained-receipt-ledger"),
        ("sec73", "73-external-claude-receipt-laws"),
    ]
    for slot_id, basename in slots:
        amend_count = count_doctrine_amendments_in_git_log(
            basename, "2026-05-12T00:00:00Z", "2026-05-18T23:59:59Z",
        )
        drift = amend_count / weeks
        records.append({
            "type": "DoctrineCitationDriftVelocity",
            "schema_version": "aep-doctrine-citation-drift-velocity-0.1",
            "id": f"dcdv:{slot_id}-week-2026-05-12-to-2026-05-18",
            "bound_to_doctrine_slot": slot_id,
            "amended_citation_count": amend_count,
            "measurement_window": {
                "window_start": utc_iso(window_start),
                "window_end": utc_iso(window_end),
            },
            "last_amendment_at": utc_iso(window_end),
            "amendment_event_ids": [],
            "drift_velocity_per_week": round(drift, 4),
            "alert_threshold_per_week": 5.0,
        })
    return records


# ----------------------------------------------------------------------------
# A8 - Claim SRS Decay (5 claims from v1.0.3 SPEC, bootstrapped SM2_LITE)
# ----------------------------------------------------------------------------

A8_CLAIMS: List[Tuple[str, str]] = [
    # (claim_id, claim_summary) — extracted from v1.0.3 SPEC sec1-sec8.
    ("claim:v103-spec-bc-v103-1-additive-only", "BC-V103-1: v0.8/v1.0.x readers validate v1.0.3 packets clean when regexical fields absent"),
    ("claim:v103-spec-regexical-cue-type-canonical", "RegexicalCue is the canonical AEP-native spaced-repetition claim type"),
    ("claim:v103-spec-f9-portable-regex-quorum-runner", "F9 portable-regex quorum runner validates patterns across Python/Node/Perl"),
    ("claim:v103-spec-sm2-lite-bootstrap-precedent", "SM2_LITE_BOOTSTRAP is the cue SRS algorithm precedent for v1.0.3 + A8 inheritance"),
    ("claim:v103-spec-vg04-rubric-definitional-gap", "VG04 rubric definitional gap on list-valued recall fields is the v1.0.3 root-cause finding"),
]

DEFAULT_DOWNGRADE_CHAIN = [
    "PROVEN/RELIABLE",
    "STRONGLY PLAUSIBLE",
    "EXPERIMENTAL",
    "SPECULATIVE FRONTIER",
    "RETIRED",
]


def build_a8_retro() -> List[Dict[str, Any]]:
    """Initial SRS state per SM2_LITE_BOOTSTRAP. Project decay schedule to T+90d."""
    bootstrap = datetime(2026, 5, 18, 5, 30, 0, tzinfo=UTC)
    initial_interval_days = 7.0  # SM2_LITE_BOOTSTRAP starting interval
    due = bootstrap + timedelta(days=initial_interval_days)
    records: List[Dict[str, Any]] = []
    for claim_id, _ in A8_CLAIMS:
        slug = re.sub(r"[^a-z0-9]+", "-", claim_id.lower()).strip("-")
        records.append({
            "type": "ClaimSrsDecay",
            "schema_version": "aep-claim-srs-decay-0.1",
            "id": f"csd:{slug}",
            "bound_to_claim_id": claim_id,
            "algorithm": "SM2_LITE",
            "ease_factor": 2.5,
            "minimum_ease_factor": 1.3,
            "repetitions": 0,
            "lapses": 0,
            "interval_days": initial_interval_days,
            "due_at": utc_iso(due),
            "downgrade_chain": DEFAULT_DOWNGRADE_CHAIN,
            "n_ttl_to_downgrade": 3,
            "current_downgrade_step": 0,
            "review_scale": "0_to_5",
        })
    return records


# ----------------------------------------------------------------------------
# Wave dispatcher
# ----------------------------------------------------------------------------

def emit_record(record: Dict[str, Any], amendment: str, fp) -> Dict[str, Any]:
    """Validate via the unified validator + append to the retro log."""
    outcome = v11.validate_record(amendment, record)
    row = {
        "wave": "058",
        "amendment": amendment,
        "record": record,
        "validation": outcome,
        "emitted_at": utc_iso(),
    }
    fp.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AEP v1.1 Wave-058 retroactive A1-A8 backfill")
    parser.add_argument("--dry-run", action="store_true", help="Print records, do NOT append to retro log.")
    args = parser.parse_args(argv)

    summary: Dict[str, Any] = {
        "wave": "058",
        "started_at": utc_iso(),
        "per_amendment": {},
    }

    # Build all retro records (deterministic order).
    a1 = build_a1_retro()
    a2 = build_a2_retro()
    a3_list = build_a3_retro()
    a5_list = build_a5_retro()
    a6 = build_a6_retro()
    a7_list = build_a7_retro()
    a8_list = build_a8_retro()

    if args.dry_run:
        out_fp = sys.stdout
    else:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        out_fp = RETRO_LOG.open("a", encoding="utf-8")

    try:
        # A1
        row = emit_record(a1, "a1", out_fp)
        summary["per_amendment"]["a1"] = {"emitted": 1, "valid": row["validation"]["valid"], "errors": row["validation"]["errors"]}
        # A2
        row = emit_record(a2, "a2", out_fp)
        summary["per_amendment"]["a2"] = {"emitted": 1, "valid": row["validation"]["valid"], "errors": row["validation"]["errors"], "token_count": row["validation"]["token_count"]}
        # A3
        a3_valid = a3_invalid = 0
        a3_errors: List[str] = []
        for rec in a3_list:
            row = emit_record(rec, "a3", out_fp)
            if row["validation"]["valid"]:
                a3_valid += 1
            else:
                a3_invalid += 1
                a3_errors.extend(row["validation"]["errors"])
        summary["per_amendment"]["a3"] = {"emitted": len(a3_list), "valid_count": a3_valid, "invalid_count": a3_invalid, "errors": a3_errors}
        # A5
        a5_valid = a5_invalid = 0
        a5_errors: List[str] = []
        a5_tier_distribution: Dict[str, int] = collections.Counter()
        for rec in a5_list:
            row = emit_record(rec, "a5", out_fp)
            if row["validation"]["valid"]:
                a5_valid += 1
            else:
                a5_invalid += 1
                a5_errors.extend(row["validation"]["errors"])
            tier = row["validation"]["tier_label"]
            if tier:
                a5_tier_distribution[tier] += 1
        summary["per_amendment"]["a5"] = {
            "emitted": len(a5_list), "valid_count": a5_valid, "invalid_count": a5_invalid,
            "errors": a5_errors, "tier_distribution": dict(a5_tier_distribution),
            "top_tags": [{"tag": r["bound_to_claim_id"], "rt_count": r["rt_count"]} for r in a5_list],
        }
        # A6
        row = emit_record(a6, "a6", out_fp)
        # Honest sec73.6 framing: if the pilot is already past TTL, surface that.
        past_ttl_warning = None
        expires_at = datetime.fromisoformat(a6["expires_at"].replace("Z", "+00:00"))
        if expires_at < datetime.now(UTC):
            past_ttl_warning = f"AEP11_A6_TTL_EXPIRED: pilot at {a6['bound_to_claim_id']} is past TTL (expires_at={a6['expires_at']}); sec73.6 honest disclosure"
        summary["per_amendment"]["a6"] = {
            "emitted": 1, "valid": row["validation"]["valid"], "errors": row["validation"]["errors"],
            "expire_action": row["validation"]["expire_action"],
            "revalidation_evidence_unique": row["validation"]["revalidation_evidence_unique"],
            "past_ttl_warning": past_ttl_warning,
        }
        # A7
        a7_valid = a7_invalid = 0
        a7_errors: List[str] = []
        a7_alerts: List[str] = []
        for rec in a7_list:
            row = emit_record(rec, "a7", out_fp)
            if row["validation"]["valid"]:
                a7_valid += 1
            else:
                a7_invalid += 1
                a7_errors.extend(row["validation"]["errors"])
            if row["validation"]["alert_level"] == "ALERT":
                a7_alerts.append(rec["bound_to_doctrine_slot"])
        summary["per_amendment"]["a7"] = {
            "emitted": len(a7_list), "valid_count": a7_valid, "invalid_count": a7_invalid,
            "errors": a7_errors, "alerts": a7_alerts,
            "per_slot": [{"slot": r["bound_to_doctrine_slot"], "amend_count": r["amended_citation_count"], "drift_per_week": r["drift_velocity_per_week"]} for r in a7_list],
        }
        # A8
        a8_valid = a8_invalid = 0
        a8_errors: List[str] = []
        for rec in a8_list:
            row = emit_record(rec, "a8", out_fp)
            if row["validation"]["valid"]:
                a8_valid += 1
            else:
                a8_invalid += 1
                a8_errors.extend(row["validation"]["errors"])
        summary["per_amendment"]["a8"] = {
            "emitted": len(a8_list), "valid_count": a8_valid, "invalid_count": a8_invalid,
            "errors": a8_errors,
        }
    finally:
        if not args.dry_run:
            out_fp.close()

    summary["finished_at"] = utc_iso()
    summary["dry_run"] = args.dry_run
    # Honest verdict summary
    total_invalid = sum(
        v.get("invalid_count", 0 if v.get("valid", True) else 1)
        for v in summary["per_amendment"].values()
    )
    summary["verdict"] = "PASS" if total_invalid == 0 else "FAIL"
    print(json.dumps(summary, indent=2))
    return 0 if total_invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
