"""AEP v0.4 validator — STRICT external-anchor + NFC + manifest+assets in integrity.

v0.4 mandatory amendments enforced (per AEP_v0_4_SPEC.md):
  1. aep_version must be "0.4"
  2. profile must be "aep:0.4/minimal-jsonl" or "aep:0.4/jsonld"
  3. Canonical files reject BOM, CRLF
  4. State-hash NFC-normalized before sha256
  5. manifest_hash + assets_merkle_root present in integrity envelope
  6. WriteEvent chain: pre_state_hash == previous event's post_state_hash
  7. PROVEN_RELIABLE claims require >=2 distinct basis source_ids
  8. PROVEN_RELIABLE claims require >=1 external-anchor source
       (source_type in {primary_source, official_spec, user_artifact, external_research, human_testimony}
        AND location.kind in {url with location_hash, git-ref with immutable ref, in-packet with assets reference})
  9. validation.result renamed to schema_result
 10. Extended enums (source_type, provenance_strength, inference_label, reliability) accepted

Co-author: the agentic substrate (Claude Opus 4.7) inside AEP project V11-AEP project.
License: Apache-2.0.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

# --- v0.4 enums (additive on v0.3) ---
RELIABILITY_V04 = {
    "PROVEN_RELIABLE", "STRONGLY_PLAUSIBLE", "PLAUSIBLE",
    "ASSUMPTION", "CONFLICTED", "UNKNOWN",
    "GOVERNANCE_RULE",  # v0.4 added per AEP project §02 Amendment A15
}

SCOPES_V04 = {"LOCAL_OBSERVATION", "CONTEXT_BOUND_PATTERN", "GENERAL_CLAIM"}

PROVENANCE_V04 = {
    "independent_convergent",  # v0.4 added — operationalizes axiom 8
    "strong", "medium", "weak", "unknown",
}

SOURCE_TYPES_V04 = {
    "user_artifact", "official_spec", "primary_source", "secondary_source",
    "runtime_output", "inference_note",
    "llm_output", "tool_output", "external_research",  # v0.4 added
    "human_testimony", "derivation",  # v0.4 added
    "other",
}

# External-anchor eligibility — sources of these types CAN satisfy the external-anchor rule
# IF their location.kind also satisfies the immutability/verifiability check.
EXTERNAL_ANCHOR_SOURCE_TYPES = {
    "primary_source", "official_spec", "user_artifact",
    "external_research", "human_testimony",
}

CLAIM_STATUS_V04 = {"active", "superseded", "rejected", "needs_review"}

INFERENCE_V04 = {
    "explicit_in_source", "derived_from_claims", "architectural_inference",
    "analogical_transfer", "cross_packet_synthesis",  # v0.4 added
    "speculative_design",
}

REVIEW_DECISIONS_V04 = {"pass", "warn", "block", "defer"}
SCHEMA_RESULTS_V04 = {"pass", "warn", "fail"}

REQUIRED_FILES = [
    "data/sources.jsonl",
    "data/spans.jsonl",
    "data/claims.jsonl",
    "data/relations.jsonl",
    "ops/events.jsonl",
    "reviews/reviews.jsonl",
    "validations/runs.jsonl",
]

GENESIS_PRE_STATE_HASH = "sha256:" + hashlib.sha256(b"").hexdigest()
EMPTY_SHA256 = GENESIS_PRE_STATE_HASH


@dataclass
class Finding:
    severity: str  # "error" | "warning" | "info"
    path: str
    message: str


@dataclass
class Report:
    packet: str
    state_hash: str = ""
    manifest_hash: str = ""
    assets_merkle_root: str = ""
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def add(self, severity: str, path: str, message: str) -> None:
        self.findings.append(Finding(severity, path, message))


# --- Canonicalization helpers (v0.4 NFC + canonical-JSON-sorted) ---
def nfc(obj: Any) -> Any:
    """Recursively NFC-normalize all strings in a JSON-compatible object."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, dict):
        return {nfc(k): nfc(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [nfc(x) for x in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Canonical-JSON encoding identical to v0.3 spec §15 BUT applied AFTER NFC normalization."""
    return json.dumps(nfc(obj), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- v0.4 state-hash algorithm (NFC + BOM-reject + CRLF-reject) ---
def compute_state_hash(packet_root: Path, canonical_files: List[str], report: Report) -> str:
    """v0.4 canonical state-hash. Rejects BOM and CRLF. NFC-normalizes before hashing."""
    h = hashlib.sha256()
    for rel in sorted(canonical_files):
        path = packet_root / rel
        if not path.exists():
            continue
        raw_bytes = path.read_bytes()
        # BOM rejection
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            report.add("error", rel, "canonical file has UTF-8 BOM (rejected by v0.4)")
            continue
        # CRLF rejection
        if b"\r\n" in raw_bytes or (b"\r" in raw_bytes and b"\n" not in raw_bytes):
            report.add("error", rel, "canonical file has CR/CRLF line endings (rejected by v0.4)")
            continue
        text = raw_bytes.decode("utf-8")
        for line in text.split("\n"):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                report.add("error", rel, f"invalid JSON line: {e}")
                continue
            canonical = canonical_json(obj)
            h.update(rel.encode("utf-8"))
            h.update(b"\n")
            h.update(canonical.encode("utf-8"))
            h.update(b"\n")
    return "sha256:" + h.hexdigest()


def compute_manifest_hash(packet_root: Path) -> str:
    """sha256 over manifest with integrity.{state_hash,manifest_hash,assets_merkle_root} set to empty
    (prevents recursive self-reference)."""
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return EMPTY_SHA256
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "integrity" in m and isinstance(m["integrity"], dict):
        m["integrity"] = {**m["integrity"], "state_hash": "", "manifest_hash": "", "assets_merkle_root": ""}
    return "sha256:" + sha256_hex(canonical_json(m).encode("utf-8"))


def compute_assets_merkle_root(packet_root: Path) -> str:
    """Merkle tree over assets/** files (sorted by path).
    Leaf:     sha256(path + "\n" + sha256(file_bytes))
    Internal: sha256(left || right)
    Empty:    sha256("") (genesis)
    Per RFC 6962 conventions, odd-count level promotes the last hash unchanged.
    """
    assets_dir = packet_root / "assets"
    if not assets_dir.exists():
        return EMPTY_SHA256
    leaves: List[bytes] = []
    for f in sorted(assets_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = str(f.relative_to(assets_dir)).replace("\\", "/")
        file_sha = sha256_hex(f.read_bytes())
        leaf_input = rel.encode("utf-8") + b"\n" + file_sha.encode("utf-8")
        leaves.append(hashlib.sha256(leaf_input).digest())
    if not leaves:
        return EMPTY_SHA256
    level = leaves
    while len(level) > 1:
        next_level: List[bytes] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                next_level.append(hashlib.sha256(level[i] + level[i + 1]).digest())
            else:
                next_level.append(level[i])  # RFC 6962: promote unchanged
        level = next_level
    return "sha256:" + level[0].hex()


# --- Record validators ---
def read_jsonl(path: Path, report: Report) -> List[Dict[str, Any]]:
    if not path.exists():
        report.add("error", str(path), "missing required canonical file")
        return []
    records: List[Dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            report.add("error", f"{path}:{i}", f"invalid JSON: {e}")
            continue
        if not isinstance(obj, dict):
            report.add("error", f"{path}:{i}", "record must be JSON object")
            continue
        records.append(obj)
    return records


def require_fields(obj: Dict[str, Any], required: Iterable[str], report: Report, where: str) -> None:
    for f in required:
        if f not in obj:
            report.add("error", where, f"missing required field: {f}")


def validate_manifest_v04(packet_root: Path, report: Report) -> Dict[str, Any]:
    mp = packet_root / "aepkg.json"
    if not mp.exists():
        report.add("error", "aepkg.json", "missing manifest")
        return {}
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        report.add("error", "aepkg.json", f"invalid JSON: {e}")
        return {}
    require_fields(m, ["aep_version", "packet_id", "title", "created_at", "created_by",
                       "profile", "canonical_files", "extensions", "integrity"],
                   report, "aepkg.json")
    if m.get("aep_version") != "0.4":
        report.add("error", "aepkg.json", f"v0.4 validator requires aep_version='0.4'; got {m.get('aep_version')!r}")
    if m.get("profile") not in {"aep:0.4/minimal-jsonl", "aep:0.4/jsonld"}:
        report.add("error", "aepkg.json", f"invalid profile for v0.4: {m.get('profile')!r}")
    if not str(m.get("packet_id", "")).startswith("aepkg:"):
        report.add("error", "aepkg.json", "packet_id must start with 'aepkg:'")
    integ = m.get("integrity") or {}
    if not isinstance(integ, dict):
        report.add("error", "aepkg.json", "integrity must be object")
    else:
        for k in ("state_hash", "manifest_hash", "assets_merkle_root"):
            if not str(integ.get(k, "")).startswith("sha256:"):
                report.add("error", "aepkg.json", f"integrity.{k} must be 'sha256:...' (v0.4 normative)")
    return m


def is_external_anchor(source: Dict[str, Any]) -> bool:
    """True if this source satisfies v0.4 §9 external-anchor rule.

    Source must:
      - have source_type in the EXTERNAL_ANCHOR_SOURCE_TYPES set, AND
      - have a location object satisfying one of:
          - kind=url AND location_hash is sha256-prefixed, OR
          - kind=git-ref AND ref looks like a commit sha (40-hex or 7+ hex), OR
          - kind=in-packet AND value points to assets/** (committed to assets_merkle_root)
    """
    st = source.get("source_type")
    if st not in EXTERNAL_ANCHOR_SOURCE_TYPES:
        return False
    loc = source.get("location") or {}
    if not isinstance(loc, dict):
        return False
    kind = loc.get("kind")
    if kind == "url":
        lh = loc.get("location_hash") or ""
        return lh.startswith("sha256:")
    if kind == "git-ref":
        ref = loc.get("ref") or ""
        # commit sha looks like 7+ hex chars (short) or 40 hex chars (full)
        return all(c in "0123456789abcdefABCDEF" for c in ref) and 7 <= len(ref) <= 64
    if kind == "in-packet":
        v = loc.get("value") or loc.get("path") or ""
        return v.startswith("assets/")
    return False


def validate_sources_v04(records: List[Dict[str, Any]], report: Report) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for i, s in enumerate(records, 1):
        where = f"data/sources.jsonl:{i}"
        require_fields(s, ["id", "type", "title", "source_type", "provenance_strength",
                           "location", "limits", "created_at"], report, where)
        if s.get("type") != "Source":
            report.add("error", where, "type must be 'Source'")
        if s.get("source_type") not in SOURCE_TYPES_V04:
            report.add("error", where, f"invalid source_type for v0.4: {s.get('source_type')!r}")
        if s.get("provenance_strength") not in PROVENANCE_V04:
            report.add("error", where, f"invalid provenance_strength for v0.4: {s.get('provenance_strength')!r}")
        loc = s.get("location")
        if not isinstance(loc, dict):
            report.add("error", where, "location must be object with 'kind' field (v0.4)")
        elif not loc.get("kind"):
            report.add("error", where, "location.kind required (v0.4)")
        sid = s.get("id", "")
        if sid in idx:
            report.add("error", where, f"duplicate source id: {sid}")
        idx[sid] = s
    return idx


def validate_claims_v04(records: List[Dict[str, Any]],
                         sources: Dict[str, Dict[str, Any]],
                         spans: Dict[str, Dict[str, Any]],
                         report: Report) -> None:
    for i, c in enumerate(records, 1):
        where = f"data/claims.jsonl:{i}"
        require_fields(c, ["id", "type", "text", "reliability", "scope", "basis",
                           "reasoning", "owner_agent", "review_tier", "status", "created_at"],
                       report, where)
        if c.get("type") != "Claim":
            report.add("error", where, "type must be 'Claim'")
        rel_lbl = c.get("reliability")
        if rel_lbl not in RELIABILITY_V04:
            report.add("error", where, f"invalid reliability for v0.4: {rel_lbl!r}")
        if c.get("scope") not in SCOPES_V04:
            report.add("error", where, f"invalid scope: {c.get('scope')!r}")
        if c.get("status") not in CLAIM_STATUS_V04:
            report.add("error", where, f"invalid status: {c.get('status')!r}")
        rt = c.get("review_tier", "")
        if not (isinstance(rt, str) and len(rt) == 2 and rt.startswith("R") and rt[1] in "1234"):
            report.add("error", where, f"review_tier must match ^R[1-4]$; got {rt!r}")

        basis = c.get("basis") or []
        if not isinstance(basis, list):
            report.add("error", where, "basis must be array")
            basis = []

        # --- v0.4 PROVEN_RELIABLE strictness ---
        if rel_lbl == "PROVEN_RELIABLE":
            distinct_sources: Set[str] = set()
            external_anchor_count = 0
            for b in basis:
                if not isinstance(b, dict):
                    continue
                sid = b.get("source_id", "")
                distinct_sources.add(sid)
                src = sources.get(sid)
                if src and is_external_anchor(src):
                    external_anchor_count += 1
            if len(distinct_sources) < 2:
                report.add("error", where,
                           f"PROVEN_RELIABLE claim requires >=2 distinct source_ids in basis; got {len(distinct_sources)} "
                           "(closes closed-loop fabricated-provenance attack)")
            if external_anchor_count < 1:
                report.add("error", where,
                           "PROVEN_RELIABLE claim requires >=1 external-anchor basis source "
                           "(source_type in {primary_source, official_spec, user_artifact, external_research, "
                           "human_testimony} AND location.kind in {url+location_hash, git-ref with commit sha, "
                           "in-packet under assets/})")

        if rel_lbl == "UNKNOWN" and not str(c.get("reasoning", "")).strip():
            report.add("error", where, "UNKNOWN claim must explain missing-evidence state in reasoning")

        # Basis source/span references must resolve
        for j, b in enumerate(basis, 1):
            if not isinstance(b, dict):
                report.add("error", f"{where}.basis[{j}]", "basis item must be object")
                continue
            sid = b.get("source_id")
            if sid is not None and sid not in sources:
                report.add("error", f"{where}.basis[{j}]", f"unknown basis source_id: {sid!r}")
            sp = b.get("span_id")
            if sp is not None and sp not in spans:
                report.add("error", f"{where}.basis[{j}]", f"unknown basis span_id: {sp!r}")


def validate_events_v04(records: List[Dict[str, Any]], report: Report) -> None:
    """v0.4 WriteEvent chain integrity: pre_state_hash MUST equal previous event's post_state_hash."""
    prev_post: str = GENESIS_PRE_STATE_HASH
    for i, e in enumerate(records, 1):
        where = f"ops/events.jsonl:{i}"
        require_fields(e, ["id", "type", "op", "actor", "target",
                           "pre_state_hash", "post_state_hash", "rationale", "created_at"],
                       report, where)
        if e.get("type") != "WriteEvent":
            report.add("error", where, "type must be 'WriteEvent'")
        pre = e.get("pre_state_hash", "")
        if pre != prev_post:
            # Phase-2 packets used placeholder genesis; allow on first event with explicit zero-genesis
            if i == 1 and pre == "sha256:" + "0" * 64:
                report.add("warning", where, "first event uses zero-genesis (v0.3 convention); v0.4 expects sha256-of-empty-string")
            else:
                report.add("error", where,
                           f"WriteEvent chain broken: expected pre_state_hash={prev_post[:23]}..., got {pre[:23]}...")
        prev_post = e.get("post_state_hash", prev_post)


def validate_reviews_v04(records: List[Dict[str, Any]], claims: Dict[str, Dict[str, Any]],
                          sources: Dict[str, Dict[str, Any]], report: Report) -> None:
    """v0.4 LAW-05 heuristic: warn if N>=2 reviews on the same claim collapse to one source-lineage."""
    by_claim_target: Dict[str, List[Dict[str, Any]]] = {}
    for i, r in enumerate(records, 1):
        where = f"reviews/reviews.jsonl:{i}"
        require_fields(r, ["id", "type", "reviewer_agent", "review_tier", "decision",
                           "basis", "findings", "created_at"], report, where)
        if r.get("type") != "Review":
            report.add("error", where, "type must be 'Review'")
        if r.get("decision") not in REVIEW_DECISIONS_V04:
            report.add("error", where, f"invalid decision: {r.get('decision')!r}")
        # Heuristic same-source detection: collect by target claim
        for b in r.get("basis") or []:
            if isinstance(b, dict) and "claim_id" in b:
                by_claim_target.setdefault(b["claim_id"], []).append(r)
    for claim_id, revs in by_claim_target.items():
        if len(revs) < 2:
            continue
        # Collapse basis source_ids across reviews; if all reviews cite same single source, warn
        all_source_ids: Set[str] = set()
        for r in revs:
            for b in r.get("basis") or []:
                if isinstance(b, dict) and "source_id" in b:
                    all_source_ids.add(b["source_id"])
        if len(all_source_ids) <= 1:
            report.add("warning", f"reviews(claim={claim_id})",
                       f"{len(revs)} reviews on this claim collapse to <=1 source-lineage; possible same-source convergence (LAW-05); v0.8 review-mesh will harden this to 'block'")


def validate_validations_v04(records: List[Dict[str, Any]], report: Report) -> None:
    for i, v in enumerate(records, 1):
        where = f"validations/runs.jsonl:{i}"
        # v0.4 renames result -> schema_result
        require_fields(v, ["id", "type", "validator", "schema_result", "checked_files",
                           "findings", "state_hash", "created_at"], report, where)
        if v.get("type") != "ValidationRun":
            report.add("error", where, "type must be 'ValidationRun'")
        sr = v.get("schema_result")
        if sr not in SCHEMA_RESULTS_V04:
            report.add("error", where, f"invalid schema_result for v0.4: {sr!r}")


# --- Top-level entry point ---
def validate_packet_v04(root: Path) -> Report:
    root = Path(root)
    report = Report(packet=str(root))
    if not root.exists():
        report.add("error", str(root), "packet path does not exist")
        return report
    if not root.is_dir():
        report.add("error", str(root), "v0.4 expects unpacked .aepkg directory")
        return report

    m = validate_manifest_v04(root, report)

    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            report.add("error", rel, "missing required canonical file")

    sources_records = read_jsonl(root / "data/sources.jsonl", report)
    spans_records = read_jsonl(root / "data/spans.jsonl", report)
    claims_records = read_jsonl(root / "data/claims.jsonl", report)
    events_records = read_jsonl(root / "ops/events.jsonl", report)
    reviews_records = read_jsonl(root / "reviews/reviews.jsonl", report)
    validations_records = read_jsonl(root / "validations/runs.jsonl", report)

    sources = validate_sources_v04(sources_records, report)
    spans = {s.get("id"): s for s in spans_records if isinstance(s, dict) and "id" in s}
    claims = {c.get("id"): c for c in claims_records if isinstance(c, dict) and "id" in c}

    validate_claims_v04(claims_records, sources, spans, report)
    validate_events_v04(events_records, report)
    validate_reviews_v04(reviews_records, claims, sources, report)
    validate_validations_v04(validations_records, report)

    # Compute integrity envelope (v0.4 three-component)
    cf = m.get("canonical_files", REQUIRED_FILES) if m else REQUIRED_FILES
    if not isinstance(cf, list):
        cf = REQUIRED_FILES
    report.state_hash = compute_state_hash(root, cf, report)
    report.manifest_hash = compute_manifest_hash(root)
    report.assets_merkle_root = compute_assets_merkle_root(root)

    # Cross-check claimed vs computed integrity values
    if m:
        integ = m.get("integrity") or {}
        for label, computed in (("state_hash", report.state_hash),
                                ("manifest_hash", report.manifest_hash),
                                ("assets_merkle_root", report.assets_merkle_root)):
            claimed = integ.get(label, "")
            if claimed and claimed != computed:
                report.add("error", "aepkg.json",
                           f"integrity.{label} mismatch: claimed {claimed[:23]}..., computed {computed[:23]}...")

    return report


def report_to_dict(r: Report) -> Dict[str, Any]:
    return {
        "packet": r.packet,
        "ok": r.ok,
        "state_hash": r.state_hash,
        "manifest_hash": r.manifest_hash,
        "assets_merkle_root": r.assets_merkle_root,
        "findings": [f.__dict__ for f in r.findings],
    }


def main(argv: List[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="AEP v0.4 validator (STRICT)")
    p.add_argument("packet", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    r = validate_packet_v04(args.packet)
    if args.json:
        print(json.dumps(report_to_dict(r), indent=2, ensure_ascii=False))
    else:
        print(f"AEP v0.4 packet: {r.packet}")
        print(f"State hash:        {r.state_hash}")
        print(f"Manifest hash:     {r.manifest_hash}")
        print(f"Assets Merkle:     {r.assets_merkle_root}")
        print(f"Result:            {'PASS' if r.ok else 'FAIL'}")
        for f in r.findings:
            print(f"  [{f.severity.upper()}] {f.path}: {f.message}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
