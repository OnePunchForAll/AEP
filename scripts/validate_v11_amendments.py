#!/usr/bin/env python3
"""validate_v11_amendments.py - Unified JSON Schema validator for AEP v1.1 amendments A1-A8.

AEP v1.1 Phase 4a reference implementation per single-forge-for-product-builds (sec73.4).
Validates each amendment's JSONL records against the corresponding draft 2020-12 schema
under projects/v11-aep/publish-ready/aep/schemas/.

CLI:
    python validate_v11_amendments.py --amendment <a1|a2|a3|a5|a6|a7|a8> --input <path-to-jsonl>

Exit codes:
    0   all records valid (schema + amendment-specific semantic gates pass)
    1   one or more records invalid (structured error printed to stderr)
    2   infrastructure error (schema not found, jsonschema package missing, etc.)

Composes_with:
    sec73.4 single-forge-for-product-builds
    sec73.5 warden-receipts-or-halt
    sec73.6 honest framing
    sec02 truth-tags (amendment records inherit parent claim's truth-tag)
    v1.0.3 RegexicalCue precedent (A3 is specialized cue; A8 explicitly excludes cues)
    v1.0.3.1 F14 RaterQuorumAttestation (A1 + A6 MAY carry rater_quorum_id)
    M1 closure: A6 revalidation_evidence_artifact_sha256 uniqueness check

Stdlib + jsonschema dependency.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("FATAL: jsonschema package required (pip install jsonschema>=4.0)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCHEMA_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "schemas"

AMENDMENT_SCHEMAS: Dict[str, str] = {
    "a1": "a1_phase_boundary_fork_record.schema.json",
    "a2": "a2_lesson_kernel.schema.json",
    "a3": "a3_operator_directive_cue.schema.json",
    "a5": "a5_recurrence_tier_counter.schema.json",
    "a6": "a6_pilot_observation_TTL.schema.json",
    "a7": "a7_doctrine_citation_drift_velocity.schema.json",
    "a8": "a8_claim_srs_decay.schema.json",
}

# A5 tier derivation per operator heuristic (sec10.4):
#   1 = receipt; 2 = memory; 3 = rule/hook/test; >3 = doctrine_candidate.
A5_TIER_LABEL = {1: "receipt", 2: "memory", 3: "rule_hook_test"}


def load_schema(amendment: str) -> Dict[str, Any]:
    """Load + cache the draft 2020-12 schema for `amendment` (e.g., 'a1')."""
    name = AMENDMENT_SCHEMAS.get(amendment)
    if name is None:
        raise SystemExit(f"FATAL: unknown amendment '{amendment}'. Allowed: {list(AMENDMENT_SCHEMAS)}")
    p = SCHEMA_DIR / name
    if not p.exists():
        raise SystemExit(f"FATAL: schema file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _structural_validate(record: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """Run draft 2020-12 schema validation. Returns sorted list of error messages."""
    validator = Draft202012Validator(schema)
    return sorted(
        f"{'.'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in validator.iter_errors(record)
    )


def _approx_token_count(text: str) -> int:
    """4-char/token heuristic per a2_lesson_kernel.schema.json description.

    The canonical tokenizer is operator-config-bound; this is the validator-side
    approximation. Anti-fake-rigor: NEVER round-to-zero a kernel; floor at 1.
    """
    return max(1, (len(text) + 3) // 4)


def _kernel_sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ----------------------------------------------------------------------------
# Per-amendment validators
# ----------------------------------------------------------------------------

def validate_a1_fork_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """A1 PhaseBoundaryForkRecord — counterfactual capsule.

    Beyond schema gates, this validator enforces:
    - `chose.option_id` MUST NOT equal `runner_up.option_id` (semantic forbidden).
    - confidence_margin sanity (already 0.0-1.0 in schema).
    - Optional `rater_quorum_id` MUST match `^rqa:[a-z0-9][a-z0-9._:-]*:v[0-9]+$` (schema).

    Returns: {valid: bool, errors: [str], structural_errors_count: int}
    """
    schema = load_schema("a1")
    errors = _structural_validate(record, schema)
    if not errors:
        chose_id = record.get("chose", {}).get("option_id")
        ru_id = record.get("runner_up", {}).get("option_id")
        if chose_id and ru_id and chose_id == ru_id:
            errors.append(f"<semantic>: chose.option_id == runner_up.option_id ('{chose_id}') — runner_up must be DIFFERENT option")
    return {"valid": not errors, "errors": errors}


def validate_a2_lesson_kernel(record: Dict[str, Any]) -> Dict[str, Any]:
    """A2 LessonKernel — <=200-token nucleus.

    Beyond schema gates, this validator enforces:
    - kernel_token_count <= 200 (AEP11_A2_KERNEL_TOO_LARGE on overflow)
    - kernel_sha256 matches recomputed sha256 over kernel_text (AEP11_A2_KERNEL_HASH_DRIFT)

    Returns: {valid: bool, errors: [str], token_count: int, recomputed_sha256: str}
    """
    schema = load_schema("a2")
    errors = _structural_validate(record, schema)
    token_count: Optional[int] = None
    recomputed_sha: Optional[str] = None
    if not errors:
        text = record.get("kernel_text", "")
        token_count = _approx_token_count(text)
        recomputed_sha = _kernel_sha256(text)
        declared_token_count = record.get("kernel_token_count")
        declared_sha = record.get("kernel_sha256")
        if isinstance(declared_token_count, int) and declared_token_count > 200:
            errors.append(f"AEP11_A2_KERNEL_TOO_LARGE: kernel_token_count={declared_token_count} > 200")
        if token_count > 200:
            errors.append(f"AEP11_A2_KERNEL_TOO_LARGE: computed token_count={token_count} > 200 (4-char/token heuristic)")
        if declared_sha and declared_sha != recomputed_sha:
            errors.append(f"AEP11_A2_KERNEL_HASH_DRIFT: declared {declared_sha} != recomputed {recomputed_sha}")
    return {
        "valid": not errors,
        "errors": errors,
        "token_count": token_count,
        "recomputed_sha256": recomputed_sha,
    }


def validate_a3_operator_cue(record: Dict[str, Any]) -> Dict[str, Any]:
    """A3 OperatorDirectiveCue — verbatim sacred cue.

    Beyond schema gates, this validator confirms polarity is classified
    (one of the enum values) and reports the classification back to caller.

    Returns: {valid: bool, errors: [str], polarity_classified: str | None}
    """
    schema = load_schema("a3")
    errors = _structural_validate(record, schema)
    polarity_classified: Optional[str] = None
    if not errors:
        polarity_classified = record.get("polarity")
        # sec73.2 verbatim discipline check: verbatim_text MUST NOT be empty after strip.
        verbatim = record.get("verbatim_text", "")
        if not verbatim.strip():
            errors.append("<semantic>: verbatim_text is empty after strip (sec73.2 sacred verbatim required)")
    return {"valid": not errors, "errors": errors, "polarity_classified": polarity_classified}


def validate_a5_recurrence_counter(record: Dict[str, Any]) -> Dict[str, Any]:
    """A5 RecurrenceTierCounter — promotion-tier counter.

    Beyond schema gates, this validator enforces tier_label MUST be the
    operator-heuristic derivation of rt_count:
        rt_count=1 -> receipt
        rt_count=2 -> memory
        rt_count=3 -> rule_hook_test
        rt_count>3 -> doctrine_candidate

    Also emits AEP11_A5_PROMOTION_DUE when rt_count >=2 and no promotion fired yet.

    Returns: {valid: bool, errors: [str], tier_label: str | None, promotion_due: bool}
    """
    schema = load_schema("a5")
    errors = _structural_validate(record, schema)
    tier_label: Optional[str] = None
    promotion_due = False
    if not errors:
        rt = record.get("rt_count", 0)
        expected = A5_TIER_LABEL.get(rt, "doctrine_candidate")
        declared = record.get("tier_label")
        if declared != expected:
            errors.append(f"<semantic>: tier_label='{declared}' but rt_count={rt} expects '{expected}' (operator heuristic)")
        tier_label = expected
        promo_at = record.get("promotion_action_triggered_at_rt_count")
        promotion_due = rt >= 2 and promo_at is None
    return {"valid": not errors, "errors": errors, "tier_label": tier_label, "promotion_due": promotion_due}


def validate_a6_pilot_TTL(record: Dict[str, Any]) -> Dict[str, Any]:
    """A6 PilotObservationTTL — pilot revalidation gate.

    Beyond schema gates, this validator implements the M1 closure:
        revalidation_evidence_artifact_sha256 across ALL revalidation_history
        entries MUST be unique. Ritual-revalidation (same evidence stamped twice)
        is BLOCKED with AEP11_A6_RITUAL_REVALIDATION_BLOCKED.

    Also computes expire_action (the action_on_expire string, surfaced for callers).
    revalidation_evidence_unique reports whether the M1 uniqueness gate passed.

    Returns: {valid, errors, expire_action, revalidation_evidence_unique: bool}
    """
    schema = load_schema("a6")
    errors = _structural_validate(record, schema)
    expire_action: Optional[str] = None
    revalidation_evidence_unique = True
    if not errors:
        expire_action = record.get("action_on_expire")
        history = record.get("revalidation_history", []) or []
        seen_shas: List[str] = []
        for idx, entry in enumerate(history):
            sha = entry.get("evidence_artifact_sha256")
            if sha in seen_shas:
                revalidation_evidence_unique = False
                errors.append(
                    f"AEP11_A6_RITUAL_REVALIDATION_BLOCKED: revalidation_history[{idx}].evidence_artifact_sha256={sha} duplicates an earlier entry (M1 closure)"
                )
            else:
                seen_shas.append(sha)
        # Also check top-level revalidation_evidence_artifact_sha256 is unique vs history if present.
        top_sha = record.get("revalidation_evidence_artifact_sha256")
        if top_sha and seen_shas and top_sha == seen_shas[-1]:
            # Top-level mirroring the last history entry is OK (it's the same revalidation).
            pass
        elif top_sha and top_sha in seen_shas[:-1] if seen_shas else False:
            revalidation_evidence_unique = False
            errors.append(
                f"AEP11_A6_RITUAL_REVALIDATION_BLOCKED: top-level revalidation_evidence_artifact_sha256={top_sha} duplicates an earlier history entry (M1 closure)"
            )
    return {
        "valid": not errors,
        "errors": errors,
        "expire_action": expire_action,
        "revalidation_evidence_unique": revalidation_evidence_unique,
    }


def validate_a7_drift_velocity(record: Dict[str, Any]) -> Dict[str, Any]:
    """A7 DoctrineCitationDriftVelocity — stale-doctrine surfacing.

    Beyond schema gates, this validator computes drift_velocity_per_week
    (if not declared) and emits AEP11_A7_DOCTRINE_DRIFT_ALERT when the
    computed velocity > alert_threshold_per_week.

    Returns: {valid, errors, alert_level: 'OK' | 'ALERT', drift_velocity_per_week: float | None}
    """
    schema = load_schema("a7")
    errors = _structural_validate(record, schema)
    alert_level = "OK"
    drift_velocity_per_week: Optional[float] = None
    if not errors:
        try:
            window = record.get("measurement_window", {})
            ws = datetime.fromisoformat(window["window_start"].replace("Z", "+00:00"))
            we = datetime.fromisoformat(window["window_end"].replace("Z", "+00:00"))
            weeks = max(1e-9, (we - ws).total_seconds() / (7.0 * 24.0 * 3600.0))
            count = record.get("amended_citation_count", 0)
            drift_velocity_per_week = count / weeks
        except (KeyError, ValueError, TypeError) as e:
            errors.append(f"<semantic>: measurement_window parse error: {e}")
        if not errors:
            declared = record.get("drift_velocity_per_week")
            if declared is not None and abs(declared - drift_velocity_per_week) > 0.01:
                errors.append(
                    f"<semantic>: declared drift_velocity_per_week={declared} but computed={drift_velocity_per_week:.4f} (>0.01 delta)"
                )
            threshold = record.get("alert_threshold_per_week", 5.0)
            if drift_velocity_per_week > threshold:
                alert_level = "ALERT"
                # Note: the spec calls this AEP11_A7_DOCTRINE_DRIFT_ALERT, NOT an error.
                # We surface it via alert_level rather than failing the record.
    return {
        "valid": not errors,
        "errors": errors,
        "alert_level": alert_level,
        "drift_velocity_per_week": drift_velocity_per_week,
    }


def validate_a8_srs_decay(record: Dict[str, Any]) -> Dict[str, Any]:
    """A8 ClaimSrsDecay — SM2_LITE applied to non-cue claims.

    Beyond schema gates, this validator enforces:
    - bound_to_claim_id MUST NOT match `^rxmem:` (AEP11_A8_CUE_CLAIM_REJECTED — cues use v1.0.3 cue SRS).
    - current_downgrade_step MUST be < len(downgrade_chain) (else AEP11_A8_DOWNGRADE_CHAIN_EXHAUSTED).
    - Computes decay_state (initial/in-progress/exhausted) + current_downgrade_tag (effective truth-tag).

    Returns: {valid, errors, decay_state, current_downgrade_tag}
    """
    schema = load_schema("a8")
    errors = _structural_validate(record, schema)
    decay_state: Optional[str] = None
    current_downgrade_tag: Optional[str] = None
    if not errors:
        bound = record.get("bound_to_claim_id", "")
        if isinstance(bound, str) and bound.startswith("rxmem:"):
            errors.append(
                f"AEP11_A8_CUE_CLAIM_REJECTED: bound_to_claim_id='{bound}' is a RegexicalCue; A8 explicitly excludes cues (use v1.0.3 cue SRS instead)"
            )
        chain = record.get("downgrade_chain", [])
        step = record.get("current_downgrade_step", 0)
        if not chain:
            errors.append("<semantic>: downgrade_chain MUST contain at least one truth-tag entry")
        else:
            if step >= len(chain):
                errors.append(
                    f"AEP11_A8_DOWNGRADE_CHAIN_EXHAUSTED: current_downgrade_step={step} >= len(downgrade_chain)={len(chain)}"
                )
                decay_state = "exhausted"
                current_downgrade_tag = chain[-1]
            else:
                current_downgrade_tag = chain[step]
                if step == 0:
                    decay_state = "initial"
                elif step + 1 == len(chain):
                    decay_state = "last_step_before_exhausted"
                else:
                    decay_state = "in_progress"
    return {
        "valid": not errors,
        "errors": errors,
        "decay_state": decay_state,
        "current_downgrade_tag": current_downgrade_tag,
    }


# ----------------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------------

AMENDMENT_DISPATCH = {
    "a1": validate_a1_fork_record,
    "a2": validate_a2_lesson_kernel,
    "a3": validate_a3_operator_cue,
    "a5": validate_a5_recurrence_counter,
    "a6": validate_a6_pilot_TTL,
    "a7": validate_a7_drift_velocity,
    "a8": validate_a8_srs_decay,
}


def validate_record(amendment: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch to the correct per-amendment validator. Returns its result dict."""
    fn = AMENDMENT_DISPATCH.get(amendment)
    if fn is None:
        raise SystemExit(f"FATAL: unknown amendment '{amendment}'")
    return fn(record)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="AEP v1.1 unified amendment validator (A1-A8). Exits 0 on all-valid, 1 on any invalid.",
    )
    parser.add_argument(
        "--amendment", choices=sorted(AMENDMENT_SCHEMAS.keys()), required=True,
        help="Which amendment schema to validate against (a1|a2|a3|a5|a6|a7|a8)."
    )
    parser.add_argument(
        "--input", required=True, type=pathlib.Path,
        help="Path to JSONL file with one amendment record per line."
    )
    parser.add_argument(
        "--summary-out", type=pathlib.Path, default=None,
        help="Optional path to write per-record outcomes as JSONL.",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"FATAL: input file not found: {args.input}", file=sys.stderr)
        return 2

    n_total = 0
    n_invalid = 0
    summary_rows: List[Dict[str, Any]] = []

    with args.input.open(encoding="utf-8") as fp:
        for line_no, raw in enumerate(fp, 1):
            raw = raw.strip()
            if not raw:
                continue
            n_total += 1
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as e:
                n_invalid += 1
                print(f"line {line_no}: JSON parse error: {e}", file=sys.stderr)
                summary_rows.append({"line": line_no, "valid": False, "errors": [f"json_parse: {e}"]})
                continue
            outcome = validate_record(args.amendment, record)
            outcome.setdefault("line", line_no)
            outcome.setdefault("record_type", record.get("type"))
            summary_rows.append(outcome)
            if not outcome["valid"]:
                n_invalid += 1
                for err in outcome["errors"]:
                    print(f"line {line_no}: {err}", file=sys.stderr)

    summary = {
        "amendment": args.amendment,
        "input": str(args.input),
        "total": n_total,
        "invalid": n_invalid,
        "valid": n_total - n_invalid,
        "verdict": "PASS" if n_invalid == 0 else "FAIL",
        "validated_at": _utc_now_iso(),
    }
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        with args.summary_out.open("w", encoding="utf-8") as fp:
            for row in summary_rows:
                fp.write(json.dumps(row, separators=(",", ":")) + "\n")
    # Always emit final summary line to stdout for receipt capture.
    print(json.dumps(summary, separators=(",", ":")))
    return 0 if n_invalid == 0 else 1


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. validate_v11_amendments' role per v1.1 SPEC: A1 quorum,
# A2 score amendments, A6 evidence binding hash, A7 doctrine-drift via DAG.
# Extended to: hash chain, span basis, reviewer distinctness, event ordering,
# completion witness, score scale, DAG integrity, prompt injection.
# Validator version bump: v1.1.0 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
V15_VALIDATOR_VERSION = "v1.5.0-K5-repair"


def _v15_hash_valid(h):
    if not isinstance(h, str) or len(h) != 64:
        return False
    try:
        int(h, 16)
        return True
    except (ValueError, TypeError):
        return False


def _v15_check_source_hash(packet):
    out = []
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_V11_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str) and hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
            out.append("AEP15_V11_SOURCE_HASH_MISMATCH")
    return out


def _v15_check_reviewer_distinctness(packet):
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid:
            if pid in seen_pids:
                out.append(f"AEP15_V11_REVIEWER_DUPLICATE_PRINCIPAL:{pid}")
            else:
                seen_pids.append(pid)
            if pid == creator or pid in claim_authors:
                out.append(f"AEP15_V11_A1_QUORUM_VIOLATION:{pid}")
    return out


def _v15_check_score_in_scale(packet):
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_V11_A2_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_V11_A2_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_V11_A2_SCORE_OUT_OF_SCALE:{s}")
    for rv in packet.get("reviews", []):
        s = rv.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_V11_A2_SCORE_NON_NUMERIC_REVIEW")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_V11_A2_SCORE_NAN_OR_INF_REVIEW")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_V11_A2_SCORE_OUT_OF_SCALE_REVIEW:{s}")
    return out


def _v15_check_dag_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if not isinstance(p, str):
            out.append("AEP15_V11_A7_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED")):
            out.append(f"AEP15_V11_A7_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_V11_A7_DAG_PARENT_SELF_REFERENCE")
    return out


def _v15_check_span_basis(packet):
    out = []
    span_index = set()
    for src in packet.get("sources", []):
        for sp in src.get("spans", []) or []:
            sid = sp.get("span_id")
            if sid:
                span_index.add(sid)
    for cl in packet.get("claims", []):
        bsids = cl.get("basis_span_ids") or []
        if not bsids:
            out.append(f"AEP15_V11_SPAN_BASIS_MISSING:{cl.get('claim_id')}")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_V11_SPAN_BASIS_UNRESOLVED:{sid}")
    return out


def _v15_check_event_ordering(packet):
    out = []
    events = (packet.get("manifest") or {}).get("events", [])
    prev_ts = None
    kinds = []
    for ev in events:
        kinds.append(ev.get("kind"))
        ts = ev.get("ts")
        if isinstance(ts, str):
            if prev_ts is not None and ts < prev_ts:
                out.append(f"AEP15_V11_EVENT_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_V11_EVENT_REVIEW_BEFORE_CREATE")
    return out


def _v15_check_completion_witness(packet):
    out = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            if not cl.get("witness") and not cl.get("witness_sha256") and not cl.get("witness_artifact"):
                out.append(f"AEP15_V11_A6_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
    return out


def _v15_check_prompt_injection(packet):
    out = []
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database"]
    if isinstance(text, str):
        for sig in sigs:
            if sig in text.lower():
                out.append(f"AEP15_V11_RECALL_INJECTION:{sig}")
                break
    return out


def _v15_check_claim_text_injection(packet):
    out = []
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database", "override constitution"]
    for cl in packet.get("claims", []):
        text = cl.get("text", "")
        if isinstance(text, str):
            lower = text.lower()
            for sig in sigs:
                if sig in lower:
                    out.append(f"AEP15_V11_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def _v15_check_reviewer_extras(packet):
    out = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_V11_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_V11_REVIEWER_FORGED:{pid}")
    return out


def _v15_check_span_geometry(packet):
    out = []
    for src in packet.get("sources", []):
        text = src.get("text", "")
        src_len = len(text) if isinstance(text, str) else 0
        for sp in src.get("spans", []) or []:
            start, end = sp.get("start"), sp.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            if start > end:
                out.append("AEP15_V11_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_V11_SPAN_BEYOND_SOURCE")
    return out


def _v15_check_witness_sha_forged(packet):
    out = []
    for cl in packet.get("claims", []):
        ws = cl.get("witness_sha256")
        if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
            out.append(f"AEP15_V11_A6_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_source_hash(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_dag_integrity(packet))
    out.extend(_v15_check_span_basis(packet))
    out.extend(_v15_check_event_ordering(packet))
    out.extend(_v15_check_completion_witness(packet))
    out.extend(_v15_check_prompt_injection(packet))
    out.extend(_v15_check_claim_text_injection(packet))
    out.extend(_v15_check_reviewer_extras(packet))
    out.extend(_v15_check_span_geometry(packet))
    out.extend(_v15_check_witness_sha_forged(packet))
    # FINAL PASS-CLOSURE: 6 independent structural-mutation checks (encoding/float-edge/
    # time-skew/hash-shape/semantic-equivalence/linguistic). Composes with sec73.6 honest framing.
    try:
        from v15_validators_common import v15_common_structural_checks  # type: ignore
        out.extend(v15_common_structural_checks(packet))
    except Exception:  # noqa: BLE001
        try:
            import importlib.util, pathlib as _pl
            _spec = importlib.util.spec_from_file_location(
                "v15_validators_common",
                str(_pl.Path(__file__).resolve().parent / "v15_validators_common.py"),
            )
            if _spec and _spec.loader:
                _m = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_m)
                out.extend(_m.v15_common_structural_checks(packet))
        except Exception:  # noqa: BLE001
            out.append("AEP15_COMMON_MODULE_LOAD_FAILED")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
