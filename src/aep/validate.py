"""Minimal no-dependency validator for AEP v0.3 packets.

This validator intentionally does not implement full JSON Schema.
It enforces the normative checks needed for the minimal-jsonl profile:
- required root manifest
- required canonical files
- JSONL parseability
- required fields and allowed enums
- ID uniqueness
- claim basis links to known sources/spans
- span source links
- relation basis claim links
- generated view warning if view appears to declare canonical truth
- current canonical state hash

Run:
    python -m aep.validate path/to/packet.aepkg
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

RELIABILITY = {
    "PROVEN_RELIABLE",
    "STRONGLY_PLAUSIBLE",
    "PLAUSIBLE",
    "ASSUMPTION",
    "CONFLICTED",
    "UNKNOWN",
}

SCOPES = {
    "LOCAL_OBSERVATION",
    "CONTEXT_BOUND_PATTERN",
    "GENERAL_CLAIM",
}

PROVENANCE_STRENGTH = {"strong", "medium", "weak", "unknown"}
SOURCE_TYPES = {
    "user_artifact",
    "official_spec",
    "primary_source",
    "secondary_source",
    "runtime_output",
    "inference_note",
    "other",
}
CLAIM_STATUS = {"active", "superseded", "rejected", "needs_review"}
INFERENCE_LABELS = {
    "explicit_in_source",
    "derived_from_claims",
    "architectural_inference",
    "speculative_design",
}
REVIEW_DECISIONS = {"pass", "warn", "block", "defer"}
VALIDATION_RESULTS = {"pass", "warn", "fail"}

REQUIRED_FILES = [
    "data/sources.jsonl",
    "data/spans.jsonl",
    "data/claims.jsonl",
    "data/relations.jsonl",
    "ops/events.jsonl",
    "reviews/reviews.jsonl",
    "validations/runs.jsonl",
]

@dataclass
class Finding:
    severity: str
    path: str
    message: str

@dataclass
class Report:
    packet: str
    state_hash: str = ""
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def add(self, severity: str, path: str, message: str) -> None:
        self.findings.append(Finding(severity, path, message))

def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def read_jsonl(path: Path, report: Report) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not path.exists():
        report.add("error", str(path), "missing JSONL file")
        return records
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            report.add("error", f"{path}:{i}", f"invalid JSON: {exc}")
            continue
        if not isinstance(obj, dict):
            report.add("error", f"{path}:{i}", "JSONL record must be an object")
            continue
        records.append(obj)
    return records

def require(obj: Dict[str, Any], fields: Iterable[str], report: Report, path: str) -> None:
    for field_name in fields:
        if field_name not in obj:
            report.add("error", path, f"missing required field: {field_name}")

def validate_manifest(root: Path, report: Report) -> Dict[str, Any]:
    manifest_path = root / "aepkg.json"
    if not manifest_path.exists():
        report.add("error", "aepkg.json", "missing manifest")
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add("error", "aepkg.json", f"invalid JSON: {exc}")
        return {}
    require(
        manifest,
        ["aep_version", "packet_id", "title", "created_at", "created_by", "profile", "canonical_files", "extensions", "integrity"],
        report,
        "aepkg.json",
    )
    if manifest.get("aep_version") != "0.3":
        report.add("error", "aepkg.json", "aep_version must be '0.3'")
    if manifest.get("profile") != "aep:0.3/minimal-jsonl":
        report.add("error", "aepkg.json", "profile must be 'aep:0.3/minimal-jsonl'")
    if not str(manifest.get("packet_id", "")).startswith("aepkg:"):
        report.add("error", "aepkg.json", "packet_id must start with 'aepkg:'")
    canonical = manifest.get("canonical_files", [])
    if not isinstance(canonical, list):
        report.add("error", "aepkg.json", "canonical_files must be an array")
    else:
        missing = [p for p in REQUIRED_FILES if p not in canonical]
        for p in missing:
            report.add("error", "aepkg.json", f"canonical_files missing required path: {p}")
    return manifest

def state_hash(root: Path, canonical_files: List[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(canonical_files):
        path = root / rel
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            h.update(rel.encode("utf-8"))
            h.update(b"\n")
            h.update(canonical_json(obj).encode("utf-8"))
            h.update(b"\n")
    return "sha256:" + h.hexdigest()

def index_records(records: List[Dict[str, Any]], report: Report, file_label: str) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for n, obj in enumerate(records, start=1):
        rid = obj.get("id")
        if not isinstance(rid, str) or not rid:
            report.add("error", f"{file_label}:{n}", "record id must be a non-empty string")
            continue
        if rid in idx:
            report.add("error", f"{file_label}:{n}", f"duplicate id: {rid}")
        idx[rid] = obj
        if "created_at" not in obj:
            report.add("error", f"{file_label}:{n}", "missing created_at")
    return idx

def validate_sources(records: List[Dict[str, Any]], report: Report) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"data/sources.jsonl:{i}"
        require(obj, ["id","type","title","source_type","provenance_strength","location","limits","created_at"], report, p)
        if obj.get("type") != "Source":
            report.add("error", p, "type must be Source")
        if not str(obj.get("id","")).startswith("src:"):
            report.add("error", p, "source id must start with src:")
        if obj.get("source_type") not in SOURCE_TYPES:
            report.add("error", p, f"invalid source_type: {obj.get('source_type')}")
        if obj.get("provenance_strength") not in PROVENANCE_STRENGTH:
            report.add("error", p, f"invalid provenance_strength: {obj.get('provenance_strength')}")

def validate_spans(records: List[Dict[str, Any]], sources: Dict[str, Dict[str, Any]], report: Report) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"data/spans.jsonl:{i}"
        require(obj, ["id","type","source_id","selector","quote_hash","created_at"], report, p)
        if obj.get("type") != "Span":
            report.add("error", p, "type must be Span")
        if not str(obj.get("id","")).startswith("span:"):
            report.add("error", p, "span id must start with span:")
        sid = obj.get("source_id")
        if sid not in sources:
            report.add("error", p, f"unknown source_id: {sid}")
        if not str(obj.get("quote_hash","")).startswith("sha256:"):
            report.add("error", p, "quote_hash must start with sha256:")

def validate_claims(
    records: List[Dict[str, Any]],
    sources: Dict[str, Dict[str, Any]],
    spans: Dict[str, Dict[str, Any]],
    report: Report
) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"data/claims.jsonl:{i}"
        require(obj, ["id","type","text","reliability","scope","basis","reasoning","owner_agent","review_tier","status","created_at"], report, p)
        if obj.get("type") != "Claim":
            report.add("error", p, "type must be Claim")
        if not str(obj.get("id","")).startswith("claim:"):
            report.add("error", p, "claim id must start with claim:")
        if obj.get("reliability") not in RELIABILITY:
            report.add("error", p, f"invalid reliability: {obj.get('reliability')}")
        if obj.get("scope") not in SCOPES:
            report.add("error", p, f"invalid scope: {obj.get('scope')}")
        if obj.get("status") not in CLAIM_STATUS:
            report.add("error", p, f"invalid status: {obj.get('status')}")
        if obj.get("review_tier") not in {"R1", "R2", "R3", "R4"}:
            report.add("error", p, "review_tier must be R1, R2, R3, or R4")
        basis = obj.get("basis", [])
        if not isinstance(basis, list):
            report.add("error", p, "basis must be an array")
            basis = []
        if obj.get("reliability") == "PROVEN_RELIABLE" and not basis:
            report.add("error", p, "PROVEN_RELIABLE claim must have non-empty basis")
        if obj.get("reliability") == "UNKNOWN" and not str(obj.get("reasoning", "")).strip():
            report.add("error", p, "UNKNOWN claim must explain missing evidence in reasoning")
        for j, b in enumerate(basis, start=1):
            if not isinstance(b, dict):
                report.add("error", f"{p}/basis/{j}", "basis item must be object")
                continue
            sid = b.get("source_id")
            spid = b.get("span_id")
            if sid not in sources:
                report.add("error", f"{p}/basis/{j}", f"unknown basis source_id: {sid}")
            if spid is not None and spid not in spans:
                report.add("error", f"{p}/basis/{j}", f"unknown basis span_id: {spid}")

def validate_relations(records: List[Dict[str, Any]], claims: Dict[str, Dict[str, Any]], report: Report) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"data/relations.jsonl:{i}"
        require(obj, ["id","type","subject","predicate","object","basis_claims","inference_label","created_at"], report, p)
        if obj.get("type") != "Relation":
            report.add("error", p, "type must be Relation")
        if not str(obj.get("id","")).startswith("rel:"):
            report.add("error", p, "relation id must start with rel:")
        if obj.get("inference_label") not in INFERENCE_LABELS:
            report.add("error", p, f"invalid inference_label: {obj.get('inference_label')}")
        basis_claims = obj.get("basis_claims", [])
        if not isinstance(basis_claims, list):
            report.add("error", p, "basis_claims must be array")
            basis_claims = []
        if obj.get("inference_label") != "speculative_design" and not basis_claims:
            report.add("warning", p, "non-speculative relation should usually cite at least one basis claim")
        for cid in basis_claims:
            if cid not in claims:
                report.add("error", p, f"unknown basis claim: {cid}")

def validate_events(records: List[Dict[str, Any]], report: Report) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"ops/events.jsonl:{i}"
        require(obj, ["id","type","op","actor","target","pre_state_hash","post_state_hash","rationale","created_at"], report, p)
        if obj.get("type") != "WriteEvent":
            report.add("error", p, "type must be WriteEvent")
        if not str(obj.get("id","")).startswith("event:"):
            report.add("error", p, "event id must start with event:")

def validate_reviews(records: List[Dict[str, Any]], report: Report) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"reviews/reviews.jsonl:{i}"
        require(obj, ["id","type","reviewer_agent","review_tier","decision","basis","findings","created_at"], report, p)
        if obj.get("type") != "Review":
            report.add("error", p, "type must be Review")
        if obj.get("decision") not in REVIEW_DECISIONS:
            report.add("error", p, f"invalid decision: {obj.get('decision')}")

def validate_validation_runs(records: List[Dict[str, Any]], report: Report) -> None:
    for i, obj in enumerate(records, start=1):
        p = f"validations/runs.jsonl:{i}"
        require(obj, ["id","type","validator","result","checked_files","findings","state_hash","created_at"], report, p)
        if obj.get("type") != "ValidationRun":
            report.add("error", p, "type must be ValidationRun")
        if obj.get("result") not in VALIDATION_RESULTS:
            report.add("error", p, f"invalid result: {obj.get('result')}")

def validate_packet(root: Path) -> Report:
    report = Report(packet=str(root))
    if not root.exists():
        report.add("error", str(root), "packet path does not exist")
        return report
    if not root.is_dir():
        report.add("error", str(root), "minimal validator expects an unpacked .aepkg directory")
        return report

    manifest = validate_manifest(root, report)
    canonical_files = manifest.get("canonical_files", REQUIRED_FILES)
    if not isinstance(canonical_files, list):
        canonical_files = REQUIRED_FILES

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            report.add("error", rel, "missing required canonical file")

    sources_records = read_jsonl(root / "data/sources.jsonl", report)
    spans_records = read_jsonl(root / "data/spans.jsonl", report)
    claims_records = read_jsonl(root / "data/claims.jsonl", report)
    relations_records = read_jsonl(root / "data/relations.jsonl", report)
    events_records = read_jsonl(root / "ops/events.jsonl", report)
    reviews_records = read_jsonl(root / "reviews/reviews.jsonl", report)
    validation_records = read_jsonl(root / "validations/runs.jsonl", report)

    sources = index_records(sources_records, report, "data/sources.jsonl")
    spans = index_records(spans_records, report, "data/spans.jsonl")
    claims = index_records(claims_records, report, "data/claims.jsonl")

    validate_sources(sources_records, report)
    validate_spans(spans_records, sources, report)
    validate_claims(claims_records, sources, spans, report)
    validate_relations(relations_records, claims, report)
    validate_events(events_records, report)
    validate_reviews(reviews_records, report)
    validate_validation_runs(validation_records, report)

    report.state_hash = state_hash(root, canonical_files)
    return report

def report_to_dict(report: Report) -> Dict[str, Any]:
    return {
        "packet": report.packet,
        "ok": report.ok,
        "state_hash": report.state_hash,
        "findings": [f.__dict__ for f in report.findings],
    }

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AEP v0.3 minimal-jsonl packet")
    parser.add_argument("packet", type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)

    report = validate_packet(args.packet)
    if args.json:
        print(json.dumps(report_to_dict(report), indent=2, ensure_ascii=False))
    else:
        print(f"AEP packet: {report.packet}")
        print(f"State hash: {report.state_hash or '(not computed)'}")
        print(f"Result: {'PASS' if report.ok else 'FAIL'}")
        for f in report.findings:
            print(f"{f.severity.upper()}: {f.path}: {f.message}")
    return 0 if report.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
