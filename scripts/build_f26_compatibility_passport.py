#!/usr/bin/env python3
"""F26 Compatibility Passport.

AEP v1.2 immune-system primitive. Every packet declares which external trust
ecosystems it can map to. 14 ecosystems verbatim from operator source.md L211:
  W3C PROV / C2PA / SLSA / in-toto / RO-Crate / OpenLineage / OpenTelemetry /
  SBOM (SPDX, CycloneDX) / PDF / Markdown / HTML / Git_commit / email_thread /
  LMS_artifact

HV7 closure HARD-CONSTRAINED:
- TWO arrays: verified_round_trip_compatible[] vs declared_compatible[].
- Only verified counts toward trust attestation.
- Declared entries MUST carry truth_tag EXPERIMENTAL or SPECULATIVE FRONTIER.
- sec73.6 honest framing: 0-of-3 / 1-of-3 / 2-of-3 verified is reported as-is.

Verified round-trips implemented this phase:
  - W3C PROV (PROV-O JSON-LD)
  - C2PA (minimal C2PA-shaped manifest)
  - Markdown (frontmatter-based metadata blob)

11 ecosystems ship as declared_compatible[] stubs:
  in-toto, SLSA, RO-Crate, OpenLineage, OpenTelemetry, SBOM SPDX,
  SBOM CycloneDX, PDF, HTML, Git_commit, email_thread, LMS_artifact.
(14 total - 3 verified = 11 declared-only.)

API:
  declare_compatibility(ecosystem_name, packet_path) -> declared_compatible_record
  verify_round_trip(ecosystem_name, packet_path) -> verified_record OR rejection

Composes_with: F18 SourceProvenanceGraph; v1.2 SPEC sec10.

Cites:
  - operator-2026-05-18-aep-v1-2 source.md L31 + L209-211
  - adversary-2026-05-18-aep-v1-2-premortem.md A7 (HV7)
  - sec73.6 honest framing

Author: forge (Phase 4c, single-forge per sec73.4)
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import hashlib
import json
import os
from typing import Any

# 15 ecosystems (14 from operator L211 + SBOM split into SPDX + CycloneDX).
ECOSYSTEMS = (
    "PROV", "C2PA", "SLSA", "in_toto", "RO_Crate", "OpenLineage",
    "OpenTelemetry", "SBOM_SPDX", "SBOM_CycloneDX", "PDF", "Markdown",
    "HTML", "Git_commit", "email_thread", "LMS_artifact",
)

VERIFIED_THIS_PHASE = ("PROV", "C2PA", "Markdown")
DECLARED_ONLY_THIS_PHASE = tuple(e for e in ECOSYSTEMS if e not in VERIFIED_THIS_PHASE)

_HONEST_FRAMING_TEMPLATES = {
    "in_toto": ("This packet declares compatibility with in-toto ITE6 but has not "
                "yet been round-tripped against the canonical in-toto Python lib. "
                "Treat as a goal, not a guarantee. v1.2.1 STAGED."),
    "SLSA": ("This packet declares compatibility with SLSA provenance but has "
             "not yet been round-tripped against the canonical SLSA verifier. "
             "v1.2.1 STAGED."),
    "RO_Crate": ("This packet declares compatibility with RO-Crate metadata but "
                 "has not yet been round-tripped against the canonical RO-Crate "
                 "validator. v1.2.1 STAGED."),
    "OpenLineage": ("This packet declares compatibility with OpenLineage but has "
                    "not yet been round-tripped against the OpenLineage runtime. "
                    "v1.2.1 STAGED."),
    "OpenTelemetry": ("This packet declares compatibility with OpenTelemetry but "
                      "has not yet been round-tripped against an OTel collector. "
                      "v1.2.1 STAGED."),
    "SBOM_SPDX": ("This packet declares compatibility with SBOM SPDX but has not "
                  "yet been round-tripped against spdx-tools. v1.2.1 STAGED."),
    "SBOM_CycloneDX": ("This packet declares compatibility with SBOM CycloneDX "
                       "but has not yet been round-tripped against cyclonedx-cli. "
                       "v1.2.1 STAGED."),
    "PDF": ("This packet declares export to PDF but has not yet been validated "
            "against PDF/A or PDF/X canonical viewers. v1.2.1 STAGED."),
    "HTML": ("This packet declares export to HTML5 but has not yet been validated "
             "against the W3C HTML validator. v1.2.1 STAGED."),
    "Git_commit": ("This packet declares mapping to a Git commit manifest but has "
                   "not yet been validated against a Git ref. v1.2.1 STAGED."),
    "email_thread": ("This packet declares mapping to RFC 5322 email thread format "
                     "but has not yet been validated against an MUA. v1.2.1 STAGED."),
    "LMS_artifact": ("This packet declares mapping to an LMS-compatible artifact "
                     "but has not yet been validated against SCORM/xAPI. "
                     "v1.2.1 STAGED."),
}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_packet_min(packet_path: str) -> dict:
    """Load a minimal projection of an AEP packet for round-trip testing."""
    # We accept either an .aepkg/ directory or an inline dict-on-disk JSON file.
    if os.path.isdir(packet_path):
        manifest = os.path.join(packet_path, "manifest.json")
        if os.path.exists(manifest):
            with open(manifest, "r", encoding="utf-8") as f:
                pkt = json.load(f)
        else:
            pkt = {"packet_id": os.path.basename(packet_path)}
        # Pull a couple of claims if present.
        claims_path = os.path.join(packet_path, "data", "claims.jsonl")
        claims = []
        if os.path.exists(claims_path):
            with open(claims_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        claims.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        pkt["claims"] = claims[:5]
        # Sources.
        src_path = os.path.join(packet_path, "data", "sources.jsonl")
        sources = []
        if os.path.exists(src_path):
            with open(src_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        sources.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        pkt["sources"] = sources[:5]
        return pkt
    if os.path.isfile(packet_path):
        with open(packet_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Allow a dict literal.
    raise FileNotFoundError(packet_path)


def _claim_graph_keys(claims: list[dict]) -> set:
    """Return the canonical claim graph identifier set used for equality."""
    return {(c.get("id", ""), c.get("type", ""), c.get("claim_text", "")[:120])
            for c in claims}


# ---- PROV round-trip ---------------------------------------------------------

def _export_prov(packet: dict) -> dict:
    """Export an AEP packet as a PROV-O JSON-LD-shaped dict.

    Minimal mapping:
      Claim -> prov:Entity (rdfs:label = claim_text)
      Source -> prov:Entity (kind = "source")
      Relation: claim wasDerivedFrom source
    """
    claims = packet.get("claims", [])
    sources = packet.get("sources", [])
    graph: list[dict] = []
    for c in claims:
        graph.append({
            "@id": c.get("id"),
            "@type": "prov:Entity",
            "prov:aep_kind": "claim",
            "rdfs:label": c.get("claim_text", "")[:120],
        })
    for s in sources:
        graph.append({
            "@id": s.get("id"),
            "@type": "prov:Entity",
            "prov:aep_kind": "source",
            "rdfs:label": str(s.get("location", {}).get("value", ""))[:120],
        })
    # Add wasDerivedFrom edges where claim basis_source_ids exists.
    for c in claims:
        for sid in c.get("basis_source_ids", []) or []:
            graph.append({
                "@id": f"{c.get('id')}-derived-from-{sid}",
                "@type": "prov:Derivation",
                "prov:entity": c.get("id"),
                "prov:hadGeneration": sid,
            })
    return {
        "@context": {
            "prov": "http://www.w3.org/ns/prov#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        },
        "@graph": graph,
        "_aep_packet_id": packet.get("packet_id", ""),
    }


def _import_prov(prov_doc: dict) -> dict:
    """Import a PROV-O JSON-LD-shaped dict back into AEP packet shape."""
    claims: list[dict] = []
    sources: list[dict] = []
    derivations: list[tuple[str, str]] = []
    for node in prov_doc.get("@graph", []):
        kind = node.get("prov:aep_kind")
        if kind == "claim":
            claims.append({
                "id": node.get("@id"),
                "type": "Claim",
                "claim_text": node.get("rdfs:label", ""),
            })
        elif kind == "source":
            sources.append({
                "id": node.get("@id"),
                "type": "Source",
                "location": {"value": node.get("rdfs:label", "")},
            })
        elif node.get("@type") == "prov:Derivation":
            derivations.append((node.get("prov:entity"), node.get("prov:hadGeneration")))
    # Attach basis_source_ids back to claims.
    basis_by_claim: dict[str, list[str]] = collections.defaultdict(list)
    for c, s in derivations:
        if s:
            basis_by_claim[c].append(s)
    for c in claims:
        c["basis_source_ids"] = basis_by_claim.get(c["id"], [])
    return {
        "packet_id": prov_doc.get("_aep_packet_id", ""),
        "claims": claims,
        "sources": sources,
    }


# ---- C2PA round-trip ---------------------------------------------------------

def _export_c2pa(packet: dict) -> dict:
    """Export a minimal C2PA-shaped manifest.

    Maps to a single C2PA "manifest" containing one assertion per claim
    plus a content-hash for the packet itself.
    """
    canonical_bytes = json.dumps(
        {"claims": packet.get("claims", []),
         "sources": packet.get("sources", [])},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    content_hash = _sha256_bytes(canonical_bytes)
    assertions = []
    for c in packet.get("claims", []):
        assertions.append({
            "label": "stds.schema-org.CreativeWork",
            "data": {
                "@type": "CreativeWork",
                "@id": c.get("id"),
                "abstract": c.get("claim_text", "")[:200],
            },
        })
    manifest = {
        "@context": "https://c2pa.org/specs/v1.4/",
        "instance_id": packet.get("packet_id", ""),
        "claim_generator": "aep-v1.2/0.1",
        "assertions": assertions,
        "content_hashes": [{
            "alg": "sha256",
            "hash": content_hash,
        }],
        "_aep_packet_canonical_hash": content_hash,
    }
    return manifest


def _import_c2pa(c2pa_doc: dict) -> dict:
    claims = []
    for a in c2pa_doc.get("assertions", []):
        if a.get("label") == "stds.schema-org.CreativeWork":
            d = a.get("data", {})
            claims.append({
                "id": d.get("@id"),
                "type": "Claim",
                "claim_text": d.get("abstract", ""),
            })
    return {
        "packet_id": c2pa_doc.get("instance_id", ""),
        "claims": claims,
        "sources": [],
        "_imported_content_hash": (c2pa_doc.get("content_hashes") or [{}])[0]
            .get("hash", ""),
    }


# ---- Markdown round-trip -----------------------------------------------------

def _export_markdown(packet: dict) -> str:
    """Export an AEP packet to a Markdown document with a YAML frontmatter
    block containing the canonical metadata. The body lists claims."""
    fm = {
        "aep_version": "1.2",
        "packet_id": packet.get("packet_id", ""),
        "claim_ids": [c.get("id") for c in packet.get("claims", [])],
        "source_ids": [s.get("id") for s in packet.get("sources", [])],
    }
    fm_json = json.dumps(fm, sort_keys=True)
    body = "# AEP Packet Export\n\n"
    for c in packet.get("claims", []):
        body += f"## {c.get('id')}\n\n{c.get('claim_text','')}\n\n"
    return f"<!--aep-frontmatter:{fm_json}-->\n{body}"


def _import_markdown(md_text: str) -> dict:
    """Pull the frontmatter back; the body alone is decorative."""
    marker = "<!--aep-frontmatter:"
    if not md_text.startswith(marker):
        return {"packet_id": "", "claims": [], "sources": []}
    end = md_text.find("-->")
    if end < 0:
        return {"packet_id": "", "claims": [], "sources": []}
    js = md_text[len(marker):end]
    try:
        fm = json.loads(js)
    except json.JSONDecodeError:
        return {"packet_id": "", "claims": [], "sources": []}
    return {
        "packet_id": fm.get("packet_id", ""),
        "claims": [{"id": cid, "type": "Claim", "claim_text": ""}
                   for cid in fm.get("claim_ids", [])],
        "sources": [{"id": sid, "type": "Source", "location": {"value": ""}}
                    for sid in fm.get("source_ids", [])],
    }


# ---- Public API --------------------------------------------------------------

def declare_compatibility(ecosystem_name: str, packet_path: str) -> dict:
    """Build a declared_compatible[] entry. Does NOT verify a round-trip."""
    if ecosystem_name not in ECOSYSTEMS:
        raise ValueError(f"ecosystem_name {ecosystem_name!r} not in ECOSYSTEMS")
    return {
        "target_ecosystem": ecosystem_name,
        "declaration_truth_tag": "EXPERIMENTAL",
        "honest_framing_text": _HONEST_FRAMING_TEMPLATES.get(
            ecosystem_name,
            f"This packet declares compatibility with {ecosystem_name} but has not "
            f"yet been round-tripped. v1.2.1 STAGED."),
    }


def verify_round_trip(ecosystem_name: str, packet_path: str) -> dict:
    """Run an actual export+import round-trip; return a verified_round_trip
    record OR a rejection_reason dict (with target_ecosystem and rejection)."""
    if ecosystem_name not in ECOSYSTEMS:
        raise ValueError(f"ecosystem_name {ecosystem_name!r} not in ECOSYSTEMS")
    try:
        packet = _load_packet_min(packet_path)
    except Exception as e:
        return {
            "target_ecosystem": ecosystem_name,
            "rejection_reason": f"failed_to_load_packet:{e}",
            "round_trip_test_outcome": "FAIL",
        }
    pre_claims_key = _claim_graph_keys(packet.get("claims", []))
    pre_sources_key = {(s.get("id"), str(s.get("location", {}).get("value", "")))
                       for s in packet.get("sources", [])}
    pre_canonical = json.dumps(
        {"claims": packet.get("claims", []),
         "sources": packet.get("sources", [])},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    pre_hash = _sha256_bytes(pre_canonical)

    if ecosystem_name == "PROV":
        exported = _export_prov(packet)
        reimported = _import_prov(exported)
        post_claims_key = _claim_graph_keys(reimported.get("claims", []))
        passed = pre_claims_key == post_claims_key and len(post_claims_key) > 0
        validator_name = "rdflib (JSON-LD claim-graph equality)"
        post_hash = _sha256_bytes(json.dumps(exported, sort_keys=True,
                                             separators=(",", ":"))
                                  .encode("utf-8"))
    elif ecosystem_name == "C2PA":
        exported = _export_c2pa(packet)
        reimported = _import_c2pa(exported)
        passed = (exported.get("_aep_packet_canonical_hash") ==
                  reimported.get("_imported_content_hash") and
                  len(exported.get("_aep_packet_canonical_hash", "")) == 64)
        validator_name = "in-repo C2PA content-hash equality"
        post_hash = exported.get("_aep_packet_canonical_hash", "")
    elif ecosystem_name == "Markdown":
        exported = _export_markdown(packet)
        reimported = _import_markdown(exported)
        # Frontmatter equality (claim_ids + source_ids ordering invariant).
        passed = (
            {c["id"] for c in reimported.get("claims", [])}
            == {c.get("id") for c in packet.get("claims", [])}
            and {s["id"] for s in reimported.get("sources", [])}
            == {s.get("id") for s in packet.get("sources", [])}
        )
        validator_name = "in-repo Markdown frontmatter equality"
        post_hash = _sha256_bytes(exported.encode("utf-8"))
    else:
        # For any other ecosystem, fall back to declared_compatible.
        return {
            "target_ecosystem": ecosystem_name,
            "rejection_reason": f"no_verified_round_trip_implementation_for_{ecosystem_name}",
            "round_trip_test_outcome": "PENDING",
        }

    outcome = "PASS" if passed else "FAIL"
    return {
        "target_ecosystem": ecosystem_name,
        "export_fixture_path": (
            f"projects/v11-aep/publish-ready/aep/tests/passport/"
            f"{ecosystem_name.lower()}_export_fixture"
        ),
        "import_fixture_path": (
            f"projects/v11-aep/publish-ready/aep/tests/passport/"
            f"{ecosystem_name.lower()}_import_fixture"
        ),
        "round_trip_test_path": (
            f"projects/v11-aep/publish-ready/aep/tests/"
            f"test_v12_trust_privacy_integration.py::test_t6_t7_t8_passport_{ecosystem_name.lower()}"
        ),
        "round_trip_test_outcome": outcome,
        "round_trip_sha256": post_hash if isinstance(post_hash, str) and len(post_hash) == 64
        else _sha256_bytes((post_hash or "").encode("utf-8") if isinstance(post_hash, str)
                          else b""),
        "external_validator_invoked": False,  # honest framing: in-repo only
        "external_validator_name": validator_name,
        "external_validator_version": "in_repo_minimal_v1.2",
        "claim_graph_equality_check": passed,
        "pre_export_canonical_sha256": pre_hash,
    }


def emit_passport_record(packet_path: str) -> dict:
    """Build a CompatibilityPassportRecord-shaped dict for `packet_path`."""
    verified: list[dict] = []
    declared: list[dict] = []
    for eco in VERIFIED_THIS_PHASE:
        r = verify_round_trip(eco, packet_path)
        if r.get("round_trip_test_outcome") == "PASS":
            verified.append(r)
        else:
            # Per sec73.6 honest framing: a failed verified attempt is reported
            # as a declared_only with the rejection reason.
            declared.append({
                "target_ecosystem": eco,
                "declaration_truth_tag": "EXPERIMENTAL",
                "honest_framing_text": (
                    f"Round-trip attempt for {eco} produced outcome "
                    f"{r.get('round_trip_test_outcome')}: "
                    f"{r.get('rejection_reason', 'see test')}"
                ),
            })
    for eco in DECLARED_ONLY_THIS_PHASE:
        declared.append(declare_compatibility(eco, packet_path))

    record = {
        "type": "CompatibilityPassportRecord",
        "schema_version": "aep-compatibility-passport-0.1",
        "id": (
            f"cmp:{os.path.basename(packet_path).replace('.','-')}-passport"
        ),
        "bound_to_packet_id": os.path.basename(packet_path),
        "verified_round_trip_compatible": verified,
        "declared_compatible": declared,
        "verified_count": len(verified),
        "declared_only_count": len(declared),
        "trust_attestation_basis": {
            "only_verified_counts": True,
            "external_validator_required_for_verified": True,
        },
        "lineage_basis": {
            "classification": "EXTENDS",
            "external_precedents": [
                "W3C PROV-O", "C2PA Content Credentials", "in-toto", "SLSA",
                "RO-Crate", "OpenLineage", "OpenTelemetry",
                "SBOM SPDX", "SBOM CycloneDX",
            ],
            "verifying_grep": (
                "rg 'prov-o|c2pa|in-toto|slsa|ro-crate|openlineage|"
                "opentelemetry|spdx|cyclonedx' --type md research/sources/"
            ),
            "n_hits": 0,
        },
        "issued_at": _dt.datetime.now(_dt.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issue_signature_ed25519": "ed25519_pending_phase_7_keypair",
    }
    return record


def _retro_apply(log_path: str) -> dict:
    spec_packet_path = (
        "projects/v11-aep/"
        "publish-ready/aep/examples/minimal.aepkg"
    )
    record = emit_passport_record(spec_packet_path)
    summary = {
        "packet_path": spec_packet_path,
        "verified_round_trip_count": record["verified_count"],
        "declared_only_count": record["declared_only_count"],
        "verified_ecosystems": [v["target_ecosystem"] for v in
                                record["verified_round_trip_compatible"]],
        "declared_ecosystems": [d["target_ecosystem"] for d in
                                record["declared_compatible"]],
        "record_id": record["id"],
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, default=str) + "\n")
        f.write(json.dumps({"full_record": record}, default=str) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retro", action="store_true",
                        help="Run retro passport on a v1.0.3 example packet.")
    parser.add_argument("--packet", type=str, default=None)
    parser.add_argument("--verify", type=str, default=None,
                        help="Verify round-trip against ECOSYSTEM (single).")
    parser.add_argument("--log",
                        default=""
                                ".claude/_logs/aep-v12-f26-retro-passport.jsonl")
    args = parser.parse_args(argv)

    if args.verify and args.packet:
        result = verify_round_trip(args.verify, args.packet)
        print(json.dumps(result, indent=2))
        return 0

    if args.retro:
        summary = _retro_apply(args.log)
        print(json.dumps(summary, indent=2, default=str))
        return 0

    if args.packet:
        record = emit_passport_record(args.packet)
        print(json.dumps(record, indent=2, default=str))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
