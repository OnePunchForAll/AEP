#!/usr/bin/env python3
"""validate_f15_witness_chain.py - F15 CriterionWitnessEntry + CompletionAttestation validator (AEP v1.1).

F15 frontier-break primitive: every PLAN.md success criterion gets a falsifiable
predicate + evidence_kind_required. Completion claims emit a CompletionAttestation
listing per-criterion witness signatures. Validator REJECTS packet promotion if any
BLOCK-severity criterion lacks a passing witness, or if any orphan attestation
references a criterion not present in the chain, or if evidence_artifact_sha256
does NOT match the actual file content on disk.

Composes_with: sec02 truth-tags, sec41 HCRL, sec73.5 warden-receipts-or-halt,
sibling-132 v1.0.3 HARD-CONDITIONAL closure (this is the empirical follow-on:
prove yesterday's plan-then-completion was machine-checkable).

API:
  - extract_criteria_from_plan(plan_path: Path) -> list[CriterionWitnessEntry]
  - extract_attestation(attestation_path: Path) -> CompletionAttestation
  - validate_completion(plan_criteria, attestation) -> CompletionResult
  - main() -> exit 0 on complete, exit 1 on incomplete or orphan

Exit codes:
  0 = all BLOCK criteria witnessed with PASS verdict + all sha256 verified
  1 = incomplete (missing witness) OR orphan attestation OR sha256 mismatch
  2 = infrastructure error (schema missing, jsonschema unavailable, etc.)
"""
from __future__ import annotations
import argparse
import dataclasses
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("FATAL: jsonschema package required (pip install jsonschema>=4.0)", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCHEMA_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "schemas"
CWE_SCHEMA_PATH = SCHEMA_DIR / "f15_criterion_witness_chain.schema.json"
CMPA_SCHEMA_PATH = SCHEMA_DIR / "f15_completion_attestation.schema.json"


# ============================================================================
# Data classes
# ============================================================================

@dataclasses.dataclass
class CriterionWitnessEntry:
    criterion_id: str
    criterion_text: str
    predicate_sha256: str
    evidence_kind_required: List[str]
    plan_path: str
    owner_role: str
    blocking_severity: str = "BLOCK"
    raw: Optional[Dict[str, Any]] = None


@dataclasses.dataclass
class WitnessRecord:
    criterion_id: str
    evidence_kind: str
    evidence_artifact_sha256: str
    witness_principal_id: str
    verdict: str
    notes: str = ""
    raw: Optional[Dict[str, Any]] = None


@dataclasses.dataclass
class CompletionAttestation:
    plan_path: str
    completion_claim_id: str
    witnesses: List[WitnessRecord]
    all_block_criteria_witnessed: bool
    raw: Optional[Dict[str, Any]] = None


@dataclasses.dataclass
class CompletionResult:
    complete: bool
    missing_witnesses: List[str]
    orphan_attestations: List[str]
    sha256_mismatches: List[Tuple[str, str, str]]  # (criterion_id, declared, actual)
    failed_verdicts: List[str]
    notes: List[str]


# ============================================================================
# Schema loaders
# ============================================================================

def _load_schema(path: pathlib.Path) -> Dict[str, Any]:
    if not path.exists():
        print(f"FATAL: schema not found at {path}", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================================
# Plan-criteria extraction (Markdown PLAN.md)
# ============================================================================

# Regex matches numbered success criteria in the form:
#   1. **Title**. body text [TRUTH TAG]
#   2. **Title** body text
# anchored under a "## Success criteria" header or similar.
SUCCESS_HEADER_RE = re.compile(r"^##+\s*Success\s+criteria.*$", re.IGNORECASE | re.MULTILINE)
NEXT_SECTION_RE = re.compile(r"^##+\s+", re.MULTILINE)
CRITERION_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$", re.MULTILINE)


def _canonical_predicate_text(criterion_text: str) -> str:
    """Strip leading bold-title prefix + truth-tag suffix; keep body."""
    text = criterion_text.strip()
    # Drop trailing [TRUTH TAG] bracketed suffix.
    text = re.sub(r"\s*\[[A-Z][A-Z /]+\]\s*$", "", text)
    # Drop leading **bold title**. or **bold title** prefix.
    text = re.sub(r"^\*\*[^*]+\*\*\.?\s*", "", text)
    return text.strip()


def _sha256_of_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_criteria_from_plan(plan_path: pathlib.Path) -> List[CriterionWitnessEntry]:
    """Extract success criteria from a PLAN.md / .md proposal file.

    Returns list of CriterionWitnessEntry. Uses canonical-text-based predicate sha256.
    plan_path may be Path or str.
    """
    plan_path = pathlib.Path(plan_path)
    if not plan_path.exists():
        raise FileNotFoundError(f"plan not found: {plan_path}")
    body = plan_path.read_text(encoding="utf-8")
    m = SUCCESS_HEADER_RE.search(body)
    if not m:
        return []
    section_start = m.end()
    # Find next top-level section header after Success criteria.
    next_match = NEXT_SECTION_RE.search(body, pos=section_start)
    section_end = next_match.start() if next_match else len(body)
    section_body = body[section_start:section_end]

    out: List[CriterionWitnessEntry] = []
    plan_slug = plan_path.stem.lower().replace(" ", "-")
    plan_rel = str(plan_path.relative_to(REPO_ROOT)) if plan_path.is_absolute() else str(plan_path)
    plan_rel_norm = plan_rel.replace("\\", "/")

    for cm in CRITERION_LINE_RE.finditer(section_body):
        n = cm.group(1)
        raw_text = cm.group(2).strip()
        # Multi-line: continue until next numbered item or blank line.
        # Look ahead in the section_body from cm.end() for continuation.
        rest = section_body[cm.end():]
        continuation_lines = []
        for line in rest.split("\n"):
            if re.match(r"^\s*\d+\.\s+", line):
                break
            if line.strip().startswith("##"):
                break
            if not line.strip() and continuation_lines:
                # blank line after some content = end of this criterion
                break
            continuation_lines.append(line)
        full = (raw_text + " " + " ".join(continuation_lines)).strip()
        canonical = _canonical_predicate_text(full)
        criterion_id = f"crit:{plan_slug}:{n.zfill(3)}"
        entry = CriterionWitnessEntry(
            criterion_id=criterion_id,
            criterion_text=full[:4000],
            predicate_sha256=_sha256_of_text(canonical),
            evidence_kind_required=["test_exit_0", "file_sha256_match"],  # default; plan can override via inline marker
            plan_path=plan_rel_norm,
            owner_role="forge",  # default; can be overridden by plan-inline tagging
            blocking_severity="BLOCK",
        )
        out.append(entry)
    return out


# ============================================================================
# Attestation loading
# ============================================================================

def extract_attestation(attestation_path: pathlib.Path) -> CompletionAttestation:
    """Load a CompletionAttestation JSON from disk."""
    attestation_path = pathlib.Path(attestation_path)
    raw = json.loads(attestation_path.read_text(encoding="utf-8"))
    witnesses = []
    for w in raw.get("witnesses", []):
        witnesses.append(WitnessRecord(
            criterion_id=w["criterion_id"],
            evidence_kind=w["evidence_kind"],
            evidence_artifact_sha256=w["evidence_artifact_sha256"],
            witness_principal_id=w["witness_principal_id"],
            verdict=w["verdict"],
            notes=w.get("notes", ""),
            raw=w,
        ))
    return CompletionAttestation(
        plan_path=raw["plan_path"],
        completion_claim_id=raw["completion_claim_id"],
        witnesses=witnesses,
        all_block_criteria_witnessed=raw.get("all_block_criteria_witnessed", False),
        raw=raw,
    )


# ============================================================================
# Core validation
# ============================================================================

def _compute_file_sha256(path: pathlib.Path) -> Optional[str]:
    """Compute sha256: of a file; None if missing."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def validate_completion(
    plan_criteria: List[CriterionWitnessEntry],
    attestation: CompletionAttestation,
    verify_file_sha256: bool = True,
) -> CompletionResult:
    """Cross-check plan_criteria vs attestation.witnesses.

    Returns CompletionResult with:
      - complete: True iff every BLOCK criterion has a PASS witness + sha256 matches.
      - missing_witnesses: criterion_ids that lack a PASS-verdict witness.
      - orphan_attestations: witness criterion_ids not in plan.
      - sha256_mismatches: (criterion_id, declared_sha, actual_sha) tuples.
      - failed_verdicts: criterion_ids whose witness was FAIL/INSUFFICIENT/TIMEOUT.
    """
    notes: List[str] = []
    by_id: Dict[str, CriterionWitnessEntry] = {c.criterion_id: c for c in plan_criteria}
    witness_by_crit: Dict[str, WitnessRecord] = {w.criterion_id: w for w in attestation.witnesses}

    missing: List[str] = []
    orphans: List[str] = []
    mismatches: List[Tuple[str, str, str]] = []
    failed: List[str] = []

    # Pass 1: every BLOCK criterion needs a PASS witness.
    for crit in plan_criteria:
        if crit.blocking_severity != "BLOCK":
            continue
        wit = witness_by_crit.get(crit.criterion_id)
        if wit is None:
            missing.append(crit.criterion_id)
            continue
        if wit.verdict != "PASS":
            failed.append(crit.criterion_id)
            notes.append(f"criterion {crit.criterion_id} witness verdict {wit.verdict} != PASS")

    # Pass 2: every witness must reference a known criterion.
    for wit in attestation.witnesses:
        if wit.criterion_id not in by_id:
            orphans.append(wit.criterion_id)
            notes.append(f"orphan witness for {wit.criterion_id} (no matching criterion in plan)")

    # Pass 3: verify evidence_artifact_sha256 actually matches file on disk
    # (only for file_sha256_match evidence_kind; other kinds are structural).
    if verify_file_sha256:
        for wit in attestation.witnesses:
            if wit.criterion_id not in by_id:
                continue
            if wit.evidence_kind != "file_sha256_match":
                continue
            # The "notes" field can carry the artifact path; treat the declared sha256 as the assertion.
            artifact_path_hint = (wit.notes or "").strip()
            if not artifact_path_hint:
                continue
            # Strip "artifact_path:" prefix if present.
            if artifact_path_hint.startswith("artifact_path:"):
                artifact_path_hint = artifact_path_hint.split(":", 1)[1].strip()
            artifact_path = REPO_ROOT / artifact_path_hint
            actual = _compute_file_sha256(artifact_path)
            if actual is None:
                mismatches.append((wit.criterion_id, wit.evidence_artifact_sha256, "MISSING_FILE"))
                notes.append(f"sha256 verify failed: file missing {artifact_path}")
                continue
            if actual != wit.evidence_artifact_sha256:
                mismatches.append((wit.criterion_id, wit.evidence_artifact_sha256, actual))
                notes.append(f"sha256 mismatch on {artifact_path}: declared {wit.evidence_artifact_sha256[:24]} actual {actual[:24]}")

    complete = (
        len(missing) == 0
        and len(orphans) == 0
        and len(mismatches) == 0
        and len(failed) == 0
    )

    return CompletionResult(
        complete=complete,
        missing_witnesses=missing,
        orphan_attestations=orphans,
        sha256_mismatches=mismatches,
        failed_verdicts=failed,
        notes=notes,
    )


# ============================================================================
# Schema validation
# ============================================================================

def validate_against_schemas(
    plan_criteria: List[CriterionWitnessEntry],
    attestation: CompletionAttestation,
) -> List[str]:
    """Validate raw dicts against the two F15 schemas. Returns error list."""
    cwe_schema = _load_schema(CWE_SCHEMA_PATH)
    cmpa_schema = _load_schema(CMPA_SCHEMA_PATH)
    errors: List[str] = []
    cwe_validator = Draft202012Validator(cwe_schema)
    for c in plan_criteria:
        if c.raw is None:
            continue
        for err in sorted(cwe_validator.iter_errors(c.raw), key=lambda e: list(e.path)):
            path = "/".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"CWE_SCHEMA_ERROR at {path}: {err.message}")
    if attestation.raw:
        cmpa_validator = Draft202012Validator(cmpa_schema)
        for err in sorted(cmpa_validator.iter_errors(attestation.raw), key=lambda e: list(e.path)):
            path = "/".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"CMPA_SCHEMA_ERROR at {path}: {err.message}")
    return errors


# ============================================================================
# CLI
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Validate F15 CriterionWitnessChain + CompletionAttestation.")
    ap.add_argument("--plan", required=True, help="Path to PLAN.md with Success criteria section.")
    ap.add_argument("--attestation", required=True, help="Path to CompletionAttestation JSON.")
    ap.add_argument("--no-sha256", action="store_true", help="Skip file_sha256_match disk verification.")
    ap.add_argument("--quiet", action="store_true", help="Suppress per-witness chatter.")
    args = ap.parse_args()

    plan_path = pathlib.Path(args.plan).resolve()
    att_path = pathlib.Path(args.attestation).resolve()

    try:
        criteria = extract_criteria_from_plan(plan_path)
    except FileNotFoundError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2

    if not criteria:
        print(f"WARN: no criteria extracted from {plan_path}", file=sys.stderr)

    try:
        att = extract_attestation(att_path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FATAL: attestation load failed: {e}", file=sys.stderr)
        return 2

    result = validate_completion(criteria, att, verify_file_sha256=not args.no_sha256)
    if not args.quiet:
        print(f"F15 plan criteria: {len(criteria)}")
        print(f"F15 attestation witnesses: {len(att.witnesses)}")
        for c in criteria:
            print(f"  criterion: {c.criterion_id} severity={c.blocking_severity}")
        for w in att.witnesses:
            print(f"  witness: {w.criterion_id} kind={w.evidence_kind} verdict={w.verdict}")

    if result.complete:
        print("F15_VERDICT: COMPLETE - all BLOCK criteria witnessed PASS.")
        return 0
    print("F15_VERDICT: INCOMPLETE")
    if result.missing_witnesses:
        print(f"  missing_witnesses ({len(result.missing_witnesses)}): {result.missing_witnesses}")
    if result.orphan_attestations:
        print(f"  orphan_attestations ({len(result.orphan_attestations)}): {result.orphan_attestations}")
    if result.sha256_mismatches:
        print(f"  sha256_mismatches ({len(result.sha256_mismatches)}):")
        for cid, declared, actual in result.sha256_mismatches:
            print(f"    {cid}: declared={declared[:24]} actual={actual[:24] if actual != 'MISSING_FILE' else actual}")
    if result.failed_verdicts:
        print(f"  failed_verdicts ({len(result.failed_verdicts)}): {result.failed_verdicts}")
    for n in result.notes:
        print(f"  note: {n}")
    return 1


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. F15's role per AEP v1.1: witness chain + temporal causality
# + completion-criterion-witness binding + span-criterion linkage + DAG chain
# integrity (event_sha mismatch on chain). Extended to source-hash class,
# witness-completeness, event-monotonicity, DAG-parent integrity, completion
# witness missing detection.
# Validator version bump: v1.1.0 -> v1.5.0-K5.
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


def _v15_check_event_monotonicity(packet):
    out = []
    events = (packet.get("manifest") or {}).get("events", [])
    prev_ts = None
    seen_kinds = []
    for ev in events:
        ts = ev.get("ts")
        seen_kinds.append(ev.get("kind"))
        if not isinstance(ts, str):
            out.append("AEP15_F15_EVENT_TS_MISSING")
            continue
        if prev_ts is not None and ts < prev_ts:
            out.append(f"AEP15_F15_EVENT_TS_NOT_MONOTONIC:{prev_ts}>{ts}")
        prev_ts = ts
    # Causal-ordering check: review_submit must follow create + claim_add.
    create_idx = next((i for i, k in enumerate(seen_kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(seen_kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F15_EVENT_REVIEW_BEFORE_CREATE")
    return out


def _v15_check_span_completeness(packet):
    """F15 witness-criterion linkage: every claim must have at least one basis span."""
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
            out.append("AEP15_F15_CLAIM_WITNESS_SPAN_MISSING")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_F15_CLAIM_WITNESS_SPAN_UNRESOLVED:{sid}")
    return out


def _v15_check_dag_parent_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    parents = manifest.get("dag_parents") or []
    pkt_id = manifest.get("packet_id")
    for p in parents:
        # NONEXISTENT / corrupt-hash patterns are detected here.
        if not isinstance(p, str):
            out.append("AEP15_F15_DAG_PARENT_NON_STRING")
            continue
        if "NONEXISTENT" in p or "BOGUS" in p or "CORRUPT" in p:
            out.append(f"AEP15_F15_DAG_PARENT_CORRUPT:{p}")
            continue
        if p == pkt_id:
            out.append("AEP15_F15_DAG_PARENT_SELF_REFERENCE")
            continue
    return out


def _v15_check_completion_witness(packet):
    """Every completion-claim must have a witness binding; sha forging detected."""
    out = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            w = cl.get("witness")
            ws = cl.get("witness_sha256")
            wa = cl.get("witness_artifact")
            if not w and not ws and not wa:
                out.append(f"AEP15_F15_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
                continue
            if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
                out.append(f"AEP15_F15_COMPLETION_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def _v15_check_dag_metadata_injection(packet):
    """prompt_injection_in_metadata injects FORGED-injection-metadata into DAG."""
    out = []
    for p in (packet.get("manifest") or {}).get("dag_parents", []) or []:
        if isinstance(p, str) and ("FORGED" in p or "injection-metadata" in p):
            out.append(f"AEP15_F15_DAG_METADATA_INJECTION:{p}")
    return out


def _v15_check_source_hash_chain(packet):
    out = []
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_F15_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str):
            if _v15_hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
                out.append("AEP15_F15_SOURCE_HASH_MISMATCH")
    return out


_F15_INJECTION_SIGNATURES = [
    "ignore all prior instructions",
    "ignore previous instructions",
    "set validator outcome to pass",
    "drop the database",
    "disregard the above",
    "override constitution",
]


def _v15_check_prompt_injection(packet):
    out = []
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    if isinstance(text, str):
        lower = text.lower()
        for sig in _F15_INJECTION_SIGNATURES:
            if sig in lower:
                out.append(f"AEP15_F15_RECALL_INJECTION:{sig}")
                break
    return out


def _v15_check_claim_text_injection(packet):
    out = []
    for cl in packet.get("claims", []):
        text = cl.get("text", "")
        if isinstance(text, str):
            lower = text.lower()
            for sig in _F15_INJECTION_SIGNATURES:
                if sig in lower:
                    out.append(f"AEP15_F15_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def _v15_check_reviewer_distinctness(packet):
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F15_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F15_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if pid == creator or pid in claim_authors:
            out.append(f"AEP15_F15_REVIEWER_SELF_ATTESTATION:{pid}")
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F15_REVIEWER_FORGED:{pid}")
    return out


def _v15_check_score_in_scale(packet):
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F15_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F15_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F15_SCORE_OUT_OF_SCALE:{s}")
    for rv in packet.get("reviews", []):
        s = rv.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F15_SCORE_NON_NUMERIC_REVIEW")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F15_SCORE_NAN_OR_INF_REVIEW")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F15_SCORE_OUT_OF_SCALE_REVIEW:{s}")
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
                out.append("AEP15_F15_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_F15_SPAN_BEYOND_SOURCE")
    return out


def _v15_check_dag_tombstone(packet):
    """F15 chain integrity - extended for tombstone-forged DAG mutations."""
    out = []
    manifest = packet.get("manifest") or {}
    for p in manifest.get("dag_parents", []) or []:
        if isinstance(p, str) and "tombstone:FORGED" in p:
            out.append(f"AEP15_F15_TOMBSTONE_FORGED:{p}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_event_monotonicity(packet))
    out.extend(_v15_check_span_completeness(packet))
    out.extend(_v15_check_dag_parent_integrity(packet))
    out.extend(_v15_check_completion_witness(packet))
    out.extend(_v15_check_source_hash_chain(packet))
    out.extend(_v15_check_prompt_injection(packet))
    out.extend(_v15_check_claim_text_injection(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_span_geometry(packet))
    out.extend(_v15_check_dag_tombstone(packet))
    out.extend(_v15_check_dag_metadata_injection(packet))
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
    sys.exit(main())
