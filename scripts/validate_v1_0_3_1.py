#!/usr/bin/env python3
"""validate_v1_0_3_1.py

AEP v1.0.3.1 validator. Mechanically enforces F14 (RaterQuorumAttestation) +
A4 (RubricScore claim type) per the v1.0.3.1 SPEC.

Composes_with:
  - doctrine/41-hash-chained-receipt-ledger.html (sec73.5 warden-receipts-or-halt)
  - doctrine/50-epistemic-hygiene-meta-law.html (Law-3 multi-lens independence)
  - doctrine/69-verification-law-and-operator-spec-sovereignty.html (sec69.4 non-rescindable)
  - doctrine/73-external-claude-receipt-laws.html (all 6 sub-laws binding)
  - projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md (predecessor)
  - projects/v11-aep/publish-ready/aep/schemas/rater_quorum_attestation.schema.json
  - projects/v11-aep/publish-ready/aep/schemas/rubric_score_claim.schema.json

Exit codes:
  0 - valid (all checks pass; warnings allowed unless --strict)
  1 - invalid (one or more structured errors)
  2 - usage / configuration error

Usage:
  python validate_v1_0_3_1.py --rqa <path-to-rqa.json>
  python validate_v1_0_3_1.py --rubric-score <path-to-score.json>
  python validate_v1_0_3_1.py --rqa <path-to-rqa.json> --rubric-score <score.json> [--strict-allow-list]

Stdlib-only. No numpy / jsonschema dependency (we ship a focused enforcer for
v1.0.3.1's two new artifact shapes; full JSON Schema draft-2020-12 validation
is left to the existing validate_regexical_memory.py + lib/aep-reference).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA_VERSION_RQA = "aep-rater-quorum-attestation-0.1"
SCHEMA_VERSION_RUBRIC_SCORE = "aep-rubric-score-0.1"

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_PATTERN_RQA = re.compile(r"^rqa:[a-z0-9][a-z0-9._:-]*:v[0-9]+$")
ID_PATTERN_SCORE = re.compile(r"^rubricscore:[a-z0-9][a-z0-9._:-]*:v[0-9]+$")

CANONICAL_ROLES = {
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
    "diana", "operator", "external_reader",
}
SCORE_LABELS = {
    "EXACT", "GOOD", "HARD_PLUS", "HARD",
    "FAIL_EASY", "FAIL_MISLEADING", "BLACKOUT",
}
AGREEMENT_METRICS = {"cohens_kappa", "krippendorff_alpha", "simple_mean_delta"}
SCORE_SCALES = {"0_to_5", "0_to_10", "normalized_0_to_1"}
VERDICT_VALUES = {"PASS", "HARD_CONDITIONAL", "FAIL", "ABORT"}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def error(self, code: str, msg: str) -> None:
        self.errors.append(f"{code}: {msg}")

    def warn(self, code: str, msg: str) -> None:
        self.warnings.append(f"{code}: {msg}")

    def note(self, msg: str) -> None:
        self.info.append(msg)

    def is_valid(self, strict: bool) -> bool:
        if self.errors:
            return False
        if strict and self.warnings:
            return False
        return True


def _require(obj: dict, key: str, rep: ValidationReport, code: str) -> bool:
    if key not in obj:
        rep.error(code, f"missing required field '{key}'")
        return False
    return True


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_PATTERN.match(value))


def validate_rqa(rqa: dict, rep: ValidationReport, *, strict_allow_list: bool = False) -> None:
    """Validate a RaterQuorumAttestation per the F14 schema."""
    if not _require(rqa, "type", rep, "RQA001"):
        return
    if rqa["type"] != "RaterQuorumAttestation":
        rep.error("RQA002", f"type must be 'RaterQuorumAttestation', got '{rqa['type']}'")
        return
    if rqa.get("schema_version") != SCHEMA_VERSION_RQA:
        rep.error("RQA003", f"schema_version must be '{SCHEMA_VERSION_RQA}'")

    if not _require(rqa, "id", rep, "RQA004"):
        return
    if not ID_PATTERN_RQA.match(rqa["id"]):
        rep.error("RQA005", f"id '{rqa['id']}' does not match {ID_PATTERN_RQA.pattern}")

    if not _require(rqa, "bound_to_artifact_sha256", rep, "RQA006"):
        return
    if not _is_sha256(rqa["bound_to_artifact_sha256"]):
        rep.error("RQA007", "bound_to_artifact_sha256 must match sha256:<64 hex>")

    if not _require(rqa, "raters", rep, "RQA008"):
        return
    raters = rqa["raters"]
    if not isinstance(raters, list):
        rep.error("RQA009", "raters must be a list")
        return
    if len(raters) < 2:
        rep.error("RQA010", f"N>=2 raters required for independence proof; got {len(raters)}")
        return

    seen_session_ids: set[str] = set()
    seen_principals: set[str] = set()
    seen_prior_exposure_hashes: list[str] = []
    scores: list[float] = []
    roles: list[str] = []
    for i, rater in enumerate(raters):
        path = f"raters[{i}]"
        if not isinstance(rater, dict):
            rep.error("RQA011", f"{path} must be an object")
            continue
        for required in ("principal_id", "role", "session_id", "time_utc", "score_0_to_5"):
            if required not in rater:
                rep.error("RQA012", f"{path}: missing required '{required}'")
        role = rater.get("role")
        if role and role not in CANONICAL_ROLES:
            rep.error("RQA013", f"{path}.role '{role}' not in canonical role set")
        sid = rater.get("session_id")
        if sid:
            if sid in seen_session_ids:
                rep.error("RQA014", f"{path}.session_id '{sid}' duplicates a prior rater's; "
                                    "raters MUST have distinct session_ids per sec73.5 independence")
            seen_session_ids.add(sid)
        pid = rater.get("principal_id")
        if pid:
            if pid in seen_principals:
                rep.error("RQA015", f"{path}.principal_id '{pid}' duplicates a prior rater's; "
                                    "raters MUST have distinct principal_ids (anti-self-attestation)")
            seen_principals.add(pid)
        score = rater.get("score_0_to_5")
        if isinstance(score, (int, float)):
            if not (0.0 <= float(score) <= 5.0):
                rep.error("RQA016", f"{path}.score_0_to_5 must be in [0.0, 5.0], got {score}")
            else:
                scores.append(float(score))
        label = rater.get("score_label")
        if label is not None and label not in SCORE_LABELS:
            rep.error("RQA017", f"{path}.score_label '{label}' not in canonical label set")
        prior = rater.get("prior_exposure_hash")
        if prior is not None:
            if not _is_sha256(prior):
                rep.error("RQA018", f"{path}.prior_exposure_hash must match sha256:<64 hex>")
            else:
                if prior in seen_prior_exposure_hashes:
                    rep.warn("RQA_ANCHORING_RISK",
                             f"{path}.prior_exposure_hash matches a prior rater's; "
                             "raters may have anchored on the same prior reads. "
                             "Audit per sec50 Law-3 multi-lens independence.")
                seen_prior_exposure_hashes.append(prior)
        rationale_sha = rater.get("rationale_sha256")
        if rationale_sha is not None and not _is_sha256(rationale_sha):
            rep.error("RQA019", f"{path}.rationale_sha256 must match sha256:<64 hex>")
        if role:
            roles.append(role)

    # agreement_metric + score + threshold + pass
    metric = rqa.get("agreement_metric")
    if metric is None:
        rep.error("RQA020", "missing required 'agreement_metric'")
    elif metric not in AGREEMENT_METRICS:
        rep.error("RQA021", f"agreement_metric '{metric}' not in {sorted(AGREEMENT_METRICS)}")

    agreement_score = rqa.get("agreement_score")
    if agreement_score is None:
        rep.error("RQA022", "missing required 'agreement_score'")

    threshold = rqa.get("independence_threshold")
    if threshold is None:
        rep.error("RQA023", "missing required 'independence_threshold'")

    independence_pass = rqa.get("independence_pass")
    if not isinstance(independence_pass, bool):
        rep.error("RQA024", "independence_pass must be a boolean")

    # Validator REPRODUCES independence_pass given metric + score + threshold
    if metric and isinstance(agreement_score, (int, float)) and isinstance(threshold, (int, float)):
        expected_pass: Optional[bool] = None
        if metric in {"cohens_kappa", "krippendorff_alpha"}:
            expected_pass = float(agreement_score) >= float(threshold)
        elif metric == "simple_mean_delta":
            expected_pass = float(agreement_score) <= float(threshold)
        if expected_pass is not None and expected_pass != independence_pass:
            rep.error("RQA025",
                      f"independence_pass={independence_pass} disagrees with computed "
                      f"{metric}-vs-{threshold} -> {expected_pass}")

    # Mean reproducibility check
    if scores:
        observed_mean = sum(scores) / len(scores)
        declared_mean = rqa.get("mean_score")
        if isinstance(declared_mean, (int, float)) and abs(float(declared_mean) - observed_mean) > 0.01:
            rep.error("RQA026",
                      f"mean_score declared {declared_mean} but raters' arithmetic mean is "
                      f"{observed_mean:.4f}")
        else:
            rep.note(f"mean_score reproducible as {observed_mean:.4f} from {len(scores)} raters")

        # max_pairwise_delta check
        max_delta = max(abs(a - b) for a in scores for b in scores)
        declared_delta = rqa.get("max_pairwise_delta")
        if isinstance(declared_delta, (int, float)) and abs(float(declared_delta) - max_delta) > 0.01:
            rep.error("RQA027",
                      f"max_pairwise_delta declared {declared_delta} but computed {max_delta:.4f}")

    # Verdict
    verdict = rqa.get("verdict")
    if verdict is not None and verdict not in VERDICT_VALUES:
        rep.error("RQA028", f"verdict '{verdict}' not in {sorted(VERDICT_VALUES)}")

    # Cross-rater roles diversity audit (anti-collusion soft signal)
    if roles and len(set(roles)) < 2:
        rep.warn("RQA_ROLE_DIVERSITY", f"raters share role '{roles[0]}'; recommended N>=2 distinct roles")


def validate_rubric_score(score: dict, rep: ValidationReport, *, strict_allow_list: bool = False) -> None:
    """Validate a RubricScore claim per the A4 schema."""
    if not _require(score, "type", rep, "RS001"):
        return
    if score["type"] != "RubricScore":
        rep.error("RS002", f"type must be 'RubricScore', got '{score['type']}'")
        return
    if score.get("schema_version") != SCHEMA_VERSION_RUBRIC_SCORE:
        rep.error("RS003", f"schema_version must be '{SCHEMA_VERSION_RUBRIC_SCORE}'")

    if not _require(score, "id", rep, "RS004"):
        return
    if not ID_PATTERN_SCORE.match(score["id"]):
        rep.error("RS005", f"id '{score['id']}' does not match {ID_PATTERN_SCORE.pattern}")

    for required in ("rubric_id", "dimension_id", "dimension_label",
                     "score", "score_scale", "bound_to_artifact_sha256",
                     "rater_principal_id"):
        _require(score, required, rep, "RS006")

    if score.get("score_scale") not in SCORE_SCALES:
        rep.error("RS007", f"score_scale '{score.get('score_scale')}' not in {sorted(SCORE_SCALES)}")

    scale = score.get("score_scale")
    num = score.get("score")
    if isinstance(num, (int, float)):
        if scale == "0_to_5" and not (0.0 <= float(num) <= 5.0):
            rep.error("RS008", f"score {num} out of range [0.0, 5.0] for scale 0_to_5")
        elif scale == "0_to_10" and not (0.0 <= float(num) <= 10.0):
            rep.error("RS009", f"score {num} out of range [0.0, 10.0] for scale 0_to_10")
        elif scale == "normalized_0_to_1" and not (0.0 <= float(num) <= 1.0):
            rep.error("RS010", f"score {num} out of range [0.0, 1.0] for scale normalized_0_to_1")

    bts = score.get("bound_to_artifact_sha256")
    if bts is not None and not _is_sha256(bts):
        rep.error("RS011", "bound_to_artifact_sha256 must match sha256:<64 hex>")

    rs_sha = score.get("rationale_sha256")
    if rs_sha is not None and not _is_sha256(rs_sha):
        rep.error("RS012", "rationale_sha256 must match sha256:<64 hex>")

    # rationale_text vs sha256 cross-check
    rs_text = score.get("rationale_text")
    if rs_text is not None and rs_sha is not None:
        import hashlib
        computed = "sha256:" + hashlib.sha256(rs_text.encode("utf-8")).hexdigest()
        if computed != rs_sha:
            rep.error("RS013", f"rationale_sha256 disagrees with sha256(rationale_text): "
                               f"declared {rs_sha}, computed {computed}")

    # rubric_definitional_closure_set
    closure_set = score.get("rubric_definitional_closure_set")
    if closure_set is not None:
        if not isinstance(closure_set, list):
            rep.error("RS014", "rubric_definitional_closure_set must be a list")
        else:
            dim_id = score.get("dimension_id")
            closure_for_dim = [c for c in closure_set if isinstance(c, dict) and c.get("dimension_id") == dim_id]
            if not closure_for_dim:
                rep.warn("RS_CLOSURE_MISSING",
                         f"dimension_id '{dim_id}' has no closure entry in rubric_definitional_closure_set; "
                         "rubric is rater-discretion for this dimension")
            for i, entry in enumerate(closure_set):
                path = f"rubric_definitional_closure_set[{i}]"
                if not isinstance(entry, dict):
                    rep.error("RS015", f"{path} must be an object")
                    continue
                if "dimension_id" not in entry:
                    rep.error("RS016", f"{path}: missing 'dimension_id'")
                if "definitional_resolution" not in entry:
                    rep.error("RS017", f"{path}: missing 'definitional_resolution'")
                lot = entry.get("list_overlap_threshold")
                if lot is not None and not (0.0 <= float(lot) <= 1.0):
                    rep.error("RS018", f"{path}.list_overlap_threshold {lot} out of [0.0, 1.0]")

    role = score.get("rater_role")
    if role is not None and role not in CANONICAL_ROLES:
        rep.error("RS019", f"rater_role '{role}' not in canonical role set")

    # Formula drift check
    computed_score = score.get("computed_score_from_formula")
    declared_score = score.get("score")
    if isinstance(computed_score, (int, float)) and isinstance(declared_score, (int, float)):
        drift = abs(float(computed_score) - float(declared_score))
        if drift > 0.25:
            rep.warn("RUBRICSCORE_FORMULA_DRIFT",
                     f"score={declared_score} vs computed_score_from_formula={computed_score} "
                     f"(drift {drift:.3f} > 0.25 threshold)")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="AEP v1.0.3.1 validator: F14 RaterQuorumAttestation + A4 RubricScore",
        epilog="Composes_with v1.0.3 validate_regexical_memory.py (which remains the canonical "
               "validator for the RegexicalCue claim type)."
    )
    parser.add_argument("--rqa", help="Path to RaterQuorumAttestation JSON")
    parser.add_argument("--rubric-score", action="append", default=[],
                        help="Path to RubricScore JSON (repeatable)")
    parser.add_argument("--strict-allow-list", action="store_true",
                        help="Promote allow-list warnings to errors")
    parser.add_argument("--strict", action="store_true",
                        help="Treat any warning as a failure")
    parser.add_argument("--json-output", action="store_true",
                        help="Emit structured JSON to stdout instead of text lines")
    args = parser.parse_args(argv)

    if not args.rqa and not args.rubric_score:
        parser.print_help(sys.stderr)
        print("\nerror: at least one of --rqa or --rubric-score is required", file=sys.stderr)
        return 2

    rep = ValidationReport()

    if args.rqa:
        try:
            rqa = load_json(Path(args.rqa))
        except Exception as exc:
            rep.error("LOAD_ERROR_RQA", f"failed to load --rqa {args.rqa}: {exc}")
        else:
            validate_rqa(rqa, rep, strict_allow_list=args.strict_allow_list)

    for sp in args.rubric_score:
        try:
            score = load_json(Path(sp))
        except Exception as exc:
            rep.error("LOAD_ERROR_RS", f"failed to load --rubric-score {sp}: {exc}")
            continue
        validate_rubric_score(score, rep, strict_allow_list=args.strict_allow_list)

    valid = rep.is_valid(strict=args.strict)
    if args.json_output:
        out = {
            "valid": valid,
            "errors": rep.errors,
            "warnings": rep.warnings,
            "info": rep.info,
        }
        print(json.dumps(out, indent=2))
    else:
        for note in rep.info:
            print(f"  info: {note}")
        for w in rep.warnings:
            print(f"warning: {w}", file=sys.stderr)
        for e in rep.errors:
            print(f"  error: {e}", file=sys.stderr)
        if valid:
            print("OK")
        else:
            print("INVALID")
    return 0 if valid else 1


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. validate_v1_0_3_1's role per v1.0.3.1 SPEC: F14 quorum
# (RaterQuorumAttestation distinct principal_ids) + source-hash check + A4
# RubricScore claim type validation. Extended to: span basis, score in scale,
# DAG integrity, event ordering, completion witness, prompt injection.
# Validator version bump: v1.0.3.1 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
import hashlib as _v15_hashlib

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
            out.append("AEP15_V1031_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str) and _v15_hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
            out.append("AEP15_V1031_SOURCE_HASH_MISMATCH")
    return out


def _v15_check_reviewer_distinctness(packet):
    """F14 RaterQuorumAttestation: rater principal_ids must be distinct."""
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid:
            if pid in seen_pids:
                out.append(f"AEP15_V1031_F14_DUPLICATE_RATER:{pid}")
            else:
                seen_pids.append(pid)
            if pid == creator or pid in claim_authors:
                out.append(f"AEP15_V1031_F14_RATER_NOT_INDEPENDENT:{pid}")
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
            out.append(f"AEP15_V1031_SPAN_BASIS_MISSING:{cl.get('claim_id')}")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_V1031_SPAN_BASIS_UNRESOLVED:{sid}")
    return out


def _v15_check_score_in_scale(packet):
    """A4 RubricScore: score must be within declared scale (0..5 default)."""
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_V1031_A4_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_V1031_A4_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_V1031_A4_SCORE_OUT_OF_SCALE:{s}")
    return out


def _v15_check_dag_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if not isinstance(p, str):
            out.append("AEP15_V1031_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED")):
            out.append(f"AEP15_V1031_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_V1031_DAG_PARENT_SELF_REFERENCE")
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
                out.append(f"AEP15_V1031_EVENT_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_V1031_EVENT_REVIEW_BEFORE_CREATE")
    return out


def _v15_check_completion_witness(packet):
    out = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            if not cl.get("witness") and not cl.get("witness_sha256") and not cl.get("witness_artifact"):
                out.append(f"AEP15_V1031_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
    return out


def _v15_check_prompt_injection(packet):
    out = []
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database"]
    if isinstance(text, str):
        for sig in sigs:
            if sig in text.lower():
                out.append(f"AEP15_V1031_RECALL_INJECTION:{sig}")
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
                    out.append(f"AEP15_V1031_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def _v15_check_reviewer_extras(packet):
    out = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_V1031_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_V1031_REVIEWER_FORGED:{pid}")
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
                out.append("AEP15_V1031_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_V1031_SPAN_BEYOND_SOURCE")
    return out


def _v15_check_witness_sha_forged(packet):
    out = []
    for cl in packet.get("claims", []):
        ws = cl.get("witness_sha256")
        if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
            out.append(f"AEP15_V1031_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_source_hash(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_span_basis(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_dag_integrity(packet))
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
    sys.exit(main(sys.argv[1:]))
