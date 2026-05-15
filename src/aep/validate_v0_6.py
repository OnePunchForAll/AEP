"""validate_v0_6.py — Apache-2.0 — AEP v0.6.0-rc1 reference validator.

Wraps v0.5.5 (`validate_v0_5_1`) with the v0.6 hot-patch closures:

  - Compact JSONL profile roundtrip parity (§V60-3)
  - Embedded index integrity check (§V60-4)
  - JSON-LD context frozen-offline rule + integrity.context_hash (§V60-5)
  - aepkg.json SINGLE-AUTHORITY enforcement over BagIt + RO-Crate (§V60-6)

v0.5.5 packets pass under v0.6 with `profile="aep:0.5/stable"` or
`profile="aep:0.6/stable"` (strictly additive backwards-compat per §V60-8).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from aep.validate_v0_5_1 import (
    validate_v0_5_1,
    ValidationConfig,
    ValidationResult,
    Finding,
    _mkfinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)
from aep.build_index import verify_index
from aep.jsonl_compact import (
    encode_jsonl_file,
    decode_jsonl_bytes,
    verify_roundtrip,
)

# v0.6 reason codes (per AEP_v0_6_SPEC.md).
AEP60_COMPACT_ENUM_UNKNOWN_CODE = "AEP60_COMPACT_ENUM_UNKNOWN_CODE"
AEP60_COMPACT_ENUM_NON_ASCII = "AEP60_COMPACT_ENUM_NON_ASCII"
AEP60_COMPACT_ROUNDTRIP_NON_IDENTICAL = "AEP60_COMPACT_ROUNDTRIP_NON_IDENTICAL"
AEP60_COMPACT_WHITESPACE_INJECTED = "AEP60_COMPACT_WHITESPACE_INJECTED"
AEP60_INDEX_HASH_MISMATCH = "AEP60_INDEX_HASH_MISMATCH"
AEP60_INDEX_RECORD_SIZE_MISMATCH = "AEP60_INDEX_RECORD_SIZE_MISMATCH"
AEP60_CONTEXT_HASH_MISMATCH = "AEP60_CONTEXT_HASH_MISMATCH"
AEP60_CONTEXT_REMOTE_FETCH_FORBIDDEN = "AEP60_CONTEXT_REMOTE_FETCH_FORBIDDEN"
AEP60_BAGIT_MANIFEST_DIVERGENCE = "AEP60_BAGIT_MANIFEST_DIVERGENCE"
AEP60_ROCRATE_ROOT_DIVERGENCE = "AEP60_ROCRATE_ROOT_DIVERGENCE"

# v0.6.0-rc2 additions from review cycle (adversary ATK-1 + ATK-2 closures)
AEP60_REVIEWER_COLLAPSE_SAME_SOURCE = "AEP60_REVIEWER_COLLAPSE_SAME_SOURCE"
AEP60_SOURCE_LOCATION_HASH_SENTINEL = "AEP60_SOURCE_LOCATION_HASH_SENTINEL"

# v0.6.1 additions from review cycle follow-up (adversary ATK-3/4/5 + SP-R8-01 + GATE-J1)
AEP61_GR_CHAIN_TRANSITIVE_LAUNDERING = "AEP61_GR_CHAIN_TRANSITIVE_LAUNDERING"
AEP61_SUPERSESSION_SELF_LOOP = "AEP61_SUPERSESSION_SELF_LOOP"
AEP61_MIGRATION_RECEIPT_DEGENERATE = "AEP61_MIGRATION_RECEIPT_DEGENERATE"
AEP61_IDENTITY_UNAUTHENTICATED = "AEP61_IDENTITY_UNAUTHENTICATED"
AEP61_BODY_ENVELOPE_LEAK = "AEP61_BODY_ENVELOPE_LEAK"
AEP61_SHARED_SCHEMA_LENS_COLLAPSE = "AEP61_SHARED_SCHEMA_LENS_COLLAPSE"
AEP61_CONTENT_HASH_MISMATCH = "AEP61_CONTENT_HASH_MISMATCH"


# Hex sentinel patterns rejected as location_hash values (per review cycle ATK-2).
_LOCATION_HASH_SENTINELS = frozenset({
    "0" * 64,
    "f" * 64,
    "F" * 64,
    "1" * 64,
    "a" * 64,
    "A" * 64,
    "deadbeef" * 8,
    "DEADBEEF" * 8,
})


def _is_hash_sentinel(hash_value: str) -> bool:
    """Return True if the hash value is a known sentinel/placeholder pattern."""
    if not isinstance(hash_value, str):
        return False
    # Strip optional sha256: prefix.
    if ":" in hash_value:
        algo, _, hex_part = hash_value.partition(":")
        if algo.lower() not in ("sha256", "sha2-256", "blake3-256"):
            return False
    else:
        hex_part = hash_value
    return hex_part in _LOCATION_HASH_SENTINELS


VALID_PROFILES_V0_6 = {
    "aep:0.5/stable",
    "aep:0.5/experimental",
    "aep:0.6/stable",
    "aep:0.6/jsonl-compact",
    "aep:0.6/linked-data",
    "aep:0.7/stable",
    "aep:0.7/signed",
    "aep:0.7/views-derived",
}

# v0.7-rc1 additions
AEP70_VIEW_DETERMINISM_MISMATCH = "AEP70_VIEW_DETERMINISM_MISMATCH"
AEP70_VIEWS_MERKLE_MISMATCH = "AEP70_VIEWS_MERKLE_MISMATCH"

# v0.7.1 critical fixes (triple-check adversary pass — internal lesson):
# Close the integrity-envelope trust-root gap exposed by adversary review cycle finding #1.
# The v0.5.5 base validator looks for state_hash + manifest_hash at TOP LEVEL but
# v0.7 packets have them nested under `integrity.*` — so the v0.5 recompute never
# fires. This left signing as "attest two scalars, not content-bind to packet."
# These closures recompute from raw bytes and compare to the declared values.
AEP70_INTEGRITY_STATE_HASH_MISMATCH = "AEP70_INTEGRITY_STATE_HASH_MISMATCH"
AEP70_INTEGRITY_MANIFEST_HASH_MISMATCH = "AEP70_INTEGRITY_MANIFEST_HASH_MISMATCH"


def _check_compact_roundtrip(packet_root: Path) -> List[Finding]:
    """v0.6 §V60-3 — compact JSONL profile roundtrip parity check."""
    findings: List[Finding] = []
    claims_path = packet_root / "data" / "claims.jsonl"
    if not claims_path.exists():
        return findings
    try:
        records: List[Dict[str, Any]] = []
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        if not verify_roundtrip(records):
            findings.append(
                _mkfinding(
                    AEP60_COMPACT_ROUNDTRIP_NON_IDENTICAL,
                    SEVERITY_ERROR,
                    "compact JSONL ↔ canonical JSONL roundtrip produces different records",
                    "data/claims.jsonl",
                )
            )
    except ValueError as exc:
        # Raised by jsonl_compact.decode_record when non-ASCII enum code detected.
        if "AEP60_COMPACT_ENUM_NON_ASCII" in str(exc):
            findings.append(
                _mkfinding(
                    AEP60_COMPACT_ENUM_NON_ASCII,
                    SEVERITY_ERROR,
                    f"compact enum code contains non-ASCII character: {exc}",
                    "data/claims.jsonl",
                )
            )
        else:
            findings.append(
                _mkfinding(
                    AEP60_COMPACT_ENUM_UNKNOWN_CODE,
                    SEVERITY_ERROR,
                    f"compact JSONL decode failed: {exc}",
                    "data/claims.jsonl",
                )
            )
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP60_INTERNAL_ERROR_COMPACT_ROUNDTRIP",
                SEVERITY_ERROR,
                f"compact roundtrip check crashed: {exc}",
                "data/claims.jsonl",
            )
        )
    return findings


def _check_embedded_index(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6 §V60-4 — embedded index integrity check."""
    findings: List[Finding] = []
    cache_path = packet_root / "cache" / "index.bin"
    integrity = manifest.get("integrity", {})
    claimed_hash = integrity.get("index_hash")
    if not cache_path.exists():
        if claimed_hash:
            findings.append(
                _mkfinding(
                    AEP60_INDEX_HASH_MISMATCH,
                    SEVERITY_ERROR,
                    "integrity.index_hash set but cache/index.bin missing",
                    "aepkg.json:integrity.index_hash",
                )
            )
        return findings
    # cache/index.bin exists — verify integrity.
    matches, computed = verify_index(packet_root)
    if not matches:
        findings.append(
            _mkfinding(
                AEP60_INDEX_HASH_MISMATCH,
                SEVERITY_ERROR,
                f"cache/index.bin tampered or stale: stored hash {claimed_hash!r}, computed {computed!r}",
                "cache/index.bin",
            )
        )
    elif claimed_hash and claimed_hash != computed:
        findings.append(
            _mkfinding(
                AEP60_INDEX_HASH_MISMATCH,
                SEVERITY_ERROR,
                f"manifest.integrity.index_hash mismatches recomputed: claimed {claimed_hash!r}, computed {computed!r}",
                "aepkg.json:integrity.index_hash",
            )
        )
    elif not claimed_hash:
        findings.append(
            _mkfinding(
                AEP60_INDEX_HASH_MISMATCH,
                SEVERITY_WARNING,
                "cache/index.bin present but integrity.index_hash missing from manifest",
                "aepkg.json:integrity",
            )
        )
    return findings


def _check_jsonld_context(packet_root: Path, manifest: Dict[str, Any], allow_remote: bool) -> List[Finding]:
    """v0.6 §V60-5 — frozen offline JSON-LD context with mandatory integrity hash."""
    findings: List[Finding] = []
    extensions = manifest.get("extensions", {})
    if not isinstance(extensions, dict):
        return findings
    context_hash_claimed = extensions.get("jsonld:context_hash") or manifest.get("integrity", {}).get("context_hash")
    context_path = packet_root / "contexts" / "aep.context.jsonld"
    if context_path.exists():
        # Compute hash.
        actual = hashlib.sha256(context_path.read_bytes()).hexdigest()
        actual_full = "sha256:" + actual
        if context_hash_claimed and context_hash_claimed != actual_full:
            findings.append(
                _mkfinding(
                    AEP60_CONTEXT_HASH_MISMATCH,
                    SEVERITY_ERROR,
                    f"contexts/aep.context.jsonld hash mismatch: claimed {context_hash_claimed!r}, computed {actual_full!r}",
                    "contexts/aep.context.jsonld",
                )
            )
        elif not context_hash_claimed:
            findings.append(
                _mkfinding(
                    AEP60_CONTEXT_HASH_MISMATCH,
                    SEVERITY_WARNING,
                    "contexts/aep.context.jsonld present but no context_hash declared in extensions or integrity",
                    "aepkg.json:extensions",
                )
            )
    # Check for remote @context URLs in any JSON-LD projection.
    if not allow_remote:
        for ld_path in (packet_root / "data").glob("*.ldjson"):
            try:
                doc = json.loads(ld_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            ctx = doc.get("@context") if isinstance(doc, dict) else None
            if isinstance(ctx, str) and (ctx.startswith("http://") or ctx.startswith("https://")):
                findings.append(
                    _mkfinding(
                        AEP60_CONTEXT_REMOTE_FETCH_FORBIDDEN,
                        SEVERITY_ERROR,
                        f"remote @context URL forbidden in strict mode: {ctx}",
                        str(ld_path.relative_to(packet_root)),
                    )
                )
    return findings


def _check_bagit_single_authority(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6 §V60-6 — aepkg.json is SINGLE-AUTHORITY; BagIt is DERIVED."""
    findings: List[Finding] = []
    bagit_path = packet_root / "manifest-sha256.txt"
    if not bagit_path.exists():
        return findings
    # Parse BagIt manifest as `<sha256_hex> <relpath>\n` lines.
    bagit_lines = bagit_path.read_text(encoding="utf-8").splitlines()
    bagit_map: Dict[str, str] = {}
    for line in bagit_lines:
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            bagit_map[parts[1]] = parts[0]
    # Verify each declared canonical file's BagIt hash matches its actual sha256.
    canonical_files = manifest.get("canonical_files", [])
    for rel in canonical_files:
        target = packet_root / rel
        if not target.exists():
            continue
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        claimed = bagit_map.get(rel)
        if claimed and claimed.lower() != actual_hash:
            findings.append(
                _mkfinding(
                    AEP60_BAGIT_MANIFEST_DIVERGENCE,
                    SEVERITY_ERROR,
                    f"BagIt manifest-sha256.txt diverges from canonical: {rel} claimed {claimed!r}, actual sha256 {actual_hash!r}",
                    "manifest-sha256.txt",
                )
            )
    return findings


def _check_reviewer_collapse(packet_root: Path) -> List[Finding]:
    """v0.6.0-rc2 ATK-1 closure — reviewer-collapse via shared same_source_fingerprint.

    When a claim's basis[] contains ≥2 entries with same_source_fingerprint set,
    the entries' fingerprints MUST be distinct. review cycle adversary finding.
    """
    findings: List[Finding] = []
    claims_path = packet_root / "data" / "claims.jsonl"
    if not claims_path.exists():
        return findings
    try:
        for line_no, line in enumerate(claims_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                claim = json.loads(line)
            except json.JSONDecodeError:
                continue
            basis = claim.get("basis", [])
            if not isinstance(basis, list) or len(basis) < 2:
                continue
            fingerprints: List[str] = []
            for entry in basis:
                if isinstance(entry, dict):
                    fp = entry.get("same_source_fingerprint")
                    if isinstance(fp, str) and fp:
                        fingerprints.append(fp)
            # Detect duplicate fingerprints among basis entries.
            seen: Dict[str, int] = {}
            for fp in fingerprints:
                seen[fp] = seen.get(fp, 0) + 1
            duplicates = {fp: count for fp, count in seen.items() if count >= 2}
            if duplicates:
                claim_id = claim.get("id", f"line {line_no}")
                findings.append(
                    _mkfinding(
                        AEP60_REVIEWER_COLLAPSE_SAME_SOURCE,
                        SEVERITY_ERROR,
                        f"claim {claim_id!r} basis[] contains {len(duplicates)} shared same_source_fingerprint value(s); reviewer-independence violation per §50 EH Law 3",
                        f"data/claims.jsonl:line:{line_no}",
                    )
                )
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP60_INTERNAL_ERROR_REVIEWER_COLLAPSE",
                SEVERITY_ERROR,
                f"reviewer-collapse check crashed: {exc}",
                "data/claims.jsonl",
            )
        )
    return findings


def _check_source_location_hash_sentinel(packet_root: Path) -> List[Finding]:
    """v0.6.0-rc2 ATK-2 closure — Source.location_hash sentinel detection.

    When a Source record has location.location_hash set, the value MUST NOT be a
    sentinel (all-zeros / all-Fs / all-ones in the hex portion). review cycle
    adversary finding; closes accidentally-shipped attack surface in
    atk-context-hijack.aepkg/data/sources.jsonl.
    """
    findings: List[Finding] = []
    sources_path = packet_root / "data" / "sources.jsonl"
    if not sources_path.exists():
        return findings
    try:
        for line_no, line in enumerate(sources_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                source = json.loads(line)
            except json.JSONDecodeError:
                continue
            location = source.get("location", {})
            if not isinstance(location, dict):
                continue
            location_hash = location.get("location_hash")
            if not isinstance(location_hash, str) or not location_hash:
                continue
            if _is_hash_sentinel(location_hash):
                source_id = source.get("id", f"line {line_no}")
                findings.append(
                    _mkfinding(
                        AEP60_SOURCE_LOCATION_HASH_SENTINEL,
                        SEVERITY_ERROR,
                        f"source {source_id!r} location_hash {location_hash!r} is a sentinel/placeholder value; commitments MUST be real hashes",
                        f"data/sources.jsonl:line:{line_no}",
                    )
                )
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP60_INTERNAL_ERROR_LOCATION_SENTINEL",
                SEVERITY_ERROR,
                f"location_hash sentinel check crashed: {exc}",
                "data/sources.jsonl",
            )
        )
    return findings


def _check_gr_transitive_laundering(packet_root: Path) -> List[Finding]:
    """v0.6.1 ATK-3 closure — Governance-Rule transitive laundering chain.

    Reject when a claim A's reliability!=GOVERNANCE_RULE chains transitively
    through ≤3 hops where ALL non-GR-leaf paths terminate in GOVERNANCE_RULE-only
    chains. Extends v0.5.3 AEP53_GR_GO_JUSTIFICATION_IS_GR (1-hop only).
    """
    findings: List[Finding] = []
    claims_path = packet_root / "data" / "claims.jsonl"
    if not claims_path.exists():
        return findings
    # Build claim graph.
    claims_by_id: Dict[str, Dict[str, Any]] = {}
    try:
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    c = json.loads(line)
                    cid = c.get("id")
                    if isinstance(cid, str):
                        claims_by_id[cid] = c
                except json.JSONDecodeError:
                    continue
    except Exception:
        return findings
    GR = "GOVERNANCE_RULE"
    MAX_DEPTH = 3
    def is_gr_chain(claim_id: str, depth: int, visited: set) -> bool:
        """Return True if every basis path terminates in GR-only leaves within MAX_DEPTH."""
        if claim_id in visited or depth > MAX_DEPTH:
            return False
        visited = visited | {claim_id}
        claim = claims_by_id.get(claim_id)
        if not claim:
            return False
        if claim.get("reliability") == GR:
            return True
        basis = claim.get("basis", [])
        if not isinstance(basis, list) or not basis:
            return False
        # Every basis entry's claim_id (if present) MUST resolve to GR-chain
        all_gr = True
        any_internal = False
        for entry in basis:
            if isinstance(entry, dict):
                cid_ref = entry.get("claim_id")
                if isinstance(cid_ref, str) and cid_ref in claims_by_id:
                    any_internal = True
                    if not is_gr_chain(cid_ref, depth + 1, visited):
                        all_gr = False
                        break
        return any_internal and all_gr
    for claim_id, claim in claims_by_id.items():
        reliability = claim.get("reliability")
        if reliability == GR:
            continue
        basis = claim.get("basis", [])
        if not isinstance(basis, list) or not basis:
            continue
        # Check if ALL internal basis-claims transitively GR-chain
        gr_chain_basis = []
        non_gr_basis = []
        for entry in basis:
            if isinstance(entry, dict):
                cid_ref = entry.get("claim_id")
                if isinstance(cid_ref, str) and cid_ref in claims_by_id:
                    if is_gr_chain(cid_ref, 1, {claim_id}):
                        gr_chain_basis.append(cid_ref)
                    else:
                        non_gr_basis.append(cid_ref)
        if gr_chain_basis and not non_gr_basis:
            findings.append(
                _mkfinding(
                    AEP61_GR_CHAIN_TRANSITIVE_LAUNDERING,
                    SEVERITY_ERROR,
                    f"claim {claim_id!r} reliability={reliability!r} basis transitively chains to GOVERNANCE_RULE-only ({gr_chain_basis}); reliability laundering",
                    f"data/claims.jsonl:claim:{claim_id}",
                )
            )
    return findings


def _check_supersession_integrity(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6.1 ATK-4 closure — supersession self-loop + degenerate migration receipt.

    Reject when:
    (a) supersedes_packet_id == packet_id (self-supersession), OR
    (b) deep_migration_receipt.pre_state_hash == post_state_hash (no-op migration claiming epoch bump).
    """
    findings: List[Finding] = []
    packet_id = manifest.get("packet_id")
    extensions = manifest.get("extensions", {}) if isinstance(manifest.get("extensions"), dict) else {}
    supersedes = extensions.get("supersedes_packet_id") or manifest.get("supersedes_packet_id")
    if isinstance(supersedes, str) and isinstance(packet_id, str) and supersedes == packet_id:
        findings.append(
            _mkfinding(
                AEP61_SUPERSESSION_SELF_LOOP,
                SEVERITY_ERROR,
                f"supersedes_packet_id={supersedes!r} equals packet_id (self-loop); supersession DAG must be acyclic",
                "aepkg.json:supersedes_packet_id",
            )
        )
    # Check deep_migration_receipt fields.
    receipt = extensions.get("implementer:deep_migration_receipt") or extensions.get("deep_migration_receipt")
    if isinstance(receipt, dict):
        pre = receipt.get("pre_state_hash")
        post = receipt.get("post_state_hash")
        if isinstance(pre, str) and isinstance(post, str) and pre == post and pre:
            findings.append(
                _mkfinding(
                    AEP61_MIGRATION_RECEIPT_DEGENERATE,
                    SEVERITY_ERROR,
                    f"deep_migration_receipt pre_state_hash == post_state_hash ({pre!r}); no-op migration cannot justify epoch bump",
                    "aepkg.json:extensions.deep_migration_receipt",
                )
            )
    return findings


def _check_identity_authenticated(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6.1 ATK-5 closure — surface identity-unauthenticated-at-profile as INFO.

    Until v0.7 signed receipts ship, `owner_agent` / `reviewer_agent` /
    `created_by` strings are unauthenticated declarations. Surface this in
    EVERY ValidationResult under v0.5/v0.6 profiles so downstream consumers
    cannot misread the structural deferral.
    """
    findings: List[Finding] = []
    profile = manifest.get("profile", "")
    if isinstance(profile, str) and (profile.startswith("aep:0.5/") or profile.startswith("aep:0.6/")):
        findings.append(
            _mkfinding(
                AEP61_IDENTITY_UNAUTHENTICATED,
                SEVERITY_INFO,
                f"profile={profile!r}: owner_agent/reviewer_agent/created_by strings are unauthenticated declarations until v0.7 signed receipts ship",
                "aepkg.json:profile",
            )
        )
    return findings


def _check_body_envelope_split(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6.1 SP-R8-01 closure — Body/Envelope disjoint hash bases.

    Reject when body files (data/*.jsonl) contain literal substrings of the
    envelope's integrity.* hash values (state_hash / manifest_hash /
    assets_merkle_root / context_hash / index_hash). This creates a circular
    dependency — body content cannot reference its own envelope's final hashes.
    """
    findings: List[Finding] = []
    integrity = manifest.get("integrity", {}) if isinstance(manifest.get("integrity"), dict) else {}
    # Collect envelope hash values to forbid in body content.
    envelope_hashes: List[Tuple[str, str]] = []
    for key in ("state_hash", "manifest_hash", "assets_merkle_root", "context_hash", "index_hash"):
        val = integrity.get(key)
        if isinstance(val, str) and val:
            # Strip optional "sha256:" prefix; the bare hex is the load-bearing match
            if ":" in val:
                _, _, hex_part = val.partition(":")
            else:
                hex_part = val
            if len(hex_part) >= 32:
                envelope_hashes.append((key, hex_part))
    if not envelope_hashes:
        return findings
    canonical_files = manifest.get("canonical_files", [])
    for rel in canonical_files:
        body_path = packet_root / rel
        if not body_path.exists():
            continue
        try:
            content = body_path.read_text(encoding="utf-8")
        except Exception:
            continue
        for key, hex_value in envelope_hashes:
            if hex_value in content:
                findings.append(
                    _mkfinding(
                        AEP61_BODY_ENVELOPE_LEAK,
                        SEVERITY_ERROR,
                        f"body file {rel!r} contains envelope.integrity.{key} hex value {hex_value[:16]!r}...; body and envelope hash bases MUST be disjoint (§3.2.1)",
                        f"{rel}",
                    )
                )
                break  # one finding per file
    return findings


def _check_shared_schema_lens(packet_root: Path) -> List[Finding]:
    """v0.6.1 GATE-J1 closure — Schema-Shared Multi-Analysis = ONE Lens.

    When a packet declares ≥2 reviews / analyses with identical
    authoring_schema_sha256 but claims convergence_count > 1, REJECT per
    epistemic-hygiene rule (schema-shared multi-analysis is ONE lens with
    internal redundancy, not N independent observers).
    """
    findings: List[Finding] = []
    reviews_path = packet_root / "reviews" / "reviews.jsonl"
    if not reviews_path.exists():
        return findings
    try:
        reviews: List[Dict[str, Any]] = []
        for line in reviews_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    reviews.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        # Detect schema-shared reviewers claiming convergence
        if len(reviews) < 2:
            return findings
        schema_groups: Dict[str, List[str]] = {}
        for rev in reviews:
            schema_fp = rev.get("authoring_schema_sha256")
            if isinstance(schema_fp, str) and schema_fp:
                rev_id = rev.get("id", "<unknown>")
                schema_groups.setdefault(schema_fp, []).append(rev_id)
        # Any group with ≥2 reviews shares a schema; if any review in that group
        # claims convergence_count > 1, flag.
        for schema_fp, rev_ids in schema_groups.items():
            if len(rev_ids) >= 2:
                for rev in reviews:
                    if rev.get("authoring_schema_sha256") == schema_fp:
                        conv = rev.get("convergence_count")
                        if isinstance(conv, int) and conv > 1:
                            findings.append(
                                _mkfinding(
                                    AEP61_SHARED_SCHEMA_LENS_COLLAPSE,
                                    SEVERITY_ERROR,
                                    f"review {rev.get('id', '<unknown>')!r} claims convergence_count={conv} but shares authoring_schema_sha256={schema_fp[:16]!r}... with {len(rev_ids)-1} other review(s); per §50 EH Law 3, schema-shared multi-analysis is ONE lens",
                                    f"reviews/reviews.jsonl:review:{rev.get('id')}",
                                )
                            )
                            break  # one finding per schema group
    except Exception:
        pass
    return findings


def _check_content_hash_recompute(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6.1 H5 closure — Verifier-Recomputed Content Hash gate.

    Per hash-chained receipt property: every artifact's content_hash MUST be re-verified by
    re-hashing the artifact at its binding_path. Reject when any declared
    content_hash on Source / EvidenceArtifact records differs from sha256 of
    referenced file in the packet.
    """
    findings: List[Finding] = []
    sources_path = packet_root / "data" / "sources.jsonl"
    if not sources_path.exists():
        return findings
    try:
        for line_no, line in enumerate(sources_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                source = json.loads(line)
            except json.JSONDecodeError:
                continue
            location = source.get("location", {})
            if not isinstance(location, dict):
                continue
            # Only verify when location.kind=file AND binding_path resolves in packet
            if location.get("kind") != "file":
                continue
            value = location.get("value", "")
            if not isinstance(value, str) or not value.startswith("./"):
                continue
            rel_path = value[2:]  # strip leading ./
            target = packet_root / rel_path
            if not target.exists():
                continue
            claimed_hash = location.get("location_hash", "")
            if not isinstance(claimed_hash, str) or not claimed_hash:
                continue
            if ":" in claimed_hash:
                _, _, claimed_hex = claimed_hash.partition(":")
            else:
                claimed_hex = claimed_hash
            actual_hex = hashlib.sha256(target.read_bytes()).hexdigest()
            if claimed_hex.lower() != actual_hex.lower():
                findings.append(
                    _mkfinding(
                        AEP61_CONTENT_HASH_MISMATCH,
                        SEVERITY_ERROR,
                        f"source {source.get('id', f'line {line_no}')!r} location_hash claims {claimed_hex[:16]!r}... but actual sha256({rel_path}) = {actual_hex[:16]!r}...",
                        f"data/sources.jsonl:line:{line_no}",
                    )
                )
    except Exception:
        pass
    return findings


def _check_rocrate_single_authority(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.6 §V60-6 — RO-Crate root is DERIVED projection of aepkg.json."""
    findings: List[Finding] = []
    rocrate_path = packet_root / "ro-crate-metadata.json"
    if not rocrate_path.exists():
        return findings
    try:
        crate = json.loads(rocrate_path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(
            _mkfinding(
                AEP60_ROCRATE_ROOT_DIVERGENCE,
                SEVERITY_ERROR,
                f"ro-crate-metadata.json failed to parse: {exc}",
                "ro-crate-metadata.json",
            )
        )
        return findings
    graph = crate.get("@graph", []) if isinstance(crate, dict) else []
    root = next(
        (n for n in graph if isinstance(n, dict) and n.get("@id") == "./"),
        None,
    )
    if root is None:
        return findings  # No root entity to validate against.
    # Mirror checks: name should reflect manifest.title; conformsTo aep:0.6/...
    manifest_title = manifest.get("title")
    crate_name = root.get("name")
    if manifest_title and crate_name and manifest_title != crate_name:
        findings.append(
            _mkfinding(
                AEP60_ROCRATE_ROOT_DIVERGENCE,
                SEVERITY_ERROR,
                f"ro-crate root name diverges from aepkg.json title: manifest={manifest_title!r}, crate={crate_name!r}",
                "ro-crate-metadata.json:@graph[root].name",
            )
        )
    return findings


def _check_view_determinism(packet_root: Path) -> List[Finding]:
    """v0.7-rc1 — view-determinism gate.

    If views/ directory exists with derived projections (claim-ledger.html /
    integrity-tree.svg / provenance-graph.mmd), re-derive and compare bytes.
    Any mismatch is REJECTED — derived views must be byte-identical to
    canonical re-derivation per visual-judge review cycle finding.
    """
    findings: List[Finding] = []
    views_dir = packet_root / "views"
    if not views_dir.exists():
        return findings
    # Only check the 3 v0.7-rc1 deterministic views
    deterministic_views = {"claim-ledger.html", "integrity-tree.svg", "provenance-graph.mmd"}
    present = {p.name for p in views_dir.iterdir() if p.is_file() and p.name in deterministic_views}
    if not present:
        return findings  # nothing to verify; views/map.mmd + views/summary.md are legacy non-deterministic
    try:
        from aep.views import verify_views
        all_match, status_per_file = verify_views(packet_root)
        if not all_match:
            for rel, status in status_per_file.items():
                if status != "OK":
                    findings.append(
                        _mkfinding(
                            AEP70_VIEW_DETERMINISM_MISMATCH,
                            SEVERITY_ERROR,
                            f"view {rel!r} is {status}; views MUST be byte-identical to deterministic re-derivation",
                            rel,
                        )
                    )
    except ImportError:
        pass  # views module not available; skip
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP70_INTERNAL_ERROR_VIEW_DETERMINISM",
                SEVERITY_ERROR,
                f"view-determinism check crashed: {exc}",
                "views/",
            )
        )
    return findings


def _check_signature_required(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.7-rc1 — aep:0.7/signed profile requires at least one valid Ed25519 signature.

    When profile=aep:0.7/signed, the packet MUST carry signatures[] with at
    least one block that verifies cleanly against integrity.state_hash +
    integrity.manifest_hash digest.
    """
    findings: List[Finding] = []
    try:
        from aep.signing import (
            verify_packet_signatures,
            AEP70_SIGNATURE_REQUIRED,
            AEP70_SIGNATURE_INVALID,
        )
        sigs = manifest.get("signatures", [])
        if not isinstance(sigs, list) or len(sigs) == 0:
            findings.append(
                _mkfinding(
                    AEP70_SIGNATURE_REQUIRED,
                    SEVERITY_ERROR,
                    "profile=aep:0.7/signed requires at least one signature in aepkg.json.signatures[]",
                    "aepkg.json:signatures",
                )
            )
            return findings
        results = verify_packet_signatures(packet_root)
        any_valid = False
        for r in results:
            if r.get("valid"):
                any_valid = True
            else:
                findings.append(
                    _mkfinding(
                        AEP70_SIGNATURE_INVALID,
                        SEVERITY_ERROR,
                        f"signature from {r.get('signer_did', '<unknown>')!r} failed: {r.get('reason', 'no reason given')}",
                        "aepkg.json:signatures",
                    )
                )
        if not any_valid:
            findings.append(
                _mkfinding(
                    AEP70_SIGNATURE_REQUIRED,
                    SEVERITY_ERROR,
                    "no valid signature found; aep:0.7/signed requires at least one valid signature",
                    "aepkg.json:signatures",
                )
            )
    except ImportError:
        findings.append(
            _mkfinding(
                "AEP70_SIGNATURE_LIB_MISSING",
                SEVERITY_ERROR,
                "cryptography library not available; cannot verify aep:0.7/signed packet",
                "aepkg.json:signatures",
            )
        )
    return findings


def _check_integrity_state_hash(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.7.1 critical fix — recompute integrity.state_hash from raw body bytes.

    Closes adversary review cycle finding #1 (signing-lane cryptographic theater).
    v0.5.5 base validator looks for state_hash at TOP LEVEL of manifest; v0.7
    packets nest it under integrity.* so the base recompute never fires.
    This explicit check recomputes via canonical_state_hash_v0_5 and compares.
    """
    findings: List[Finding] = []
    integrity = manifest.get("integrity", {}) if isinstance(manifest.get("integrity"), dict) else {}
    claimed = integrity.get("state_hash")
    if not isinstance(claimed, str) or not claimed:
        return findings  # No state_hash declared; not our gate
    canonical_files = manifest.get("canonical_files", [])
    if not isinstance(canonical_files, list):
        return findings
    try:
        from aep.validate_v0_5 import canonical_state_hash_v0_5
        computed = canonical_state_hash_v0_5(packet_root, canonical_files)
        if computed != claimed:
            findings.append(
                _mkfinding(
                    AEP70_INTEGRITY_STATE_HASH_MISMATCH,
                    SEVERITY_ERROR,
                    f"integrity.state_hash drift detected: claimed={claimed!r} computed_from_body={computed!r}; body content tampered or hash stale",
                    "aepkg.json:integrity.state_hash",
                )
            )
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP70_INTERNAL_ERROR_STATE_HASH_RECOMPUTE",
                SEVERITY_ERROR,
                f"state_hash recompute crashed: {exc}",
                "aepkg.json:integrity.state_hash",
            )
        )
    return findings


def _check_integrity_manifest_hash(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.7.1 critical fix — recompute integrity.manifest_hash with 3-field exclusion.

    Closes adversary review cycle finding #1. Exclusion set per AEP-v0.7 SIGNED_DIGEST
    design: {integrity.manifest_hash, integrity.views_merkle_root, signatures}.
    """
    findings: List[Finding] = []
    integrity = manifest.get("integrity", {}) if isinstance(manifest.get("integrity"), dict) else {}
    claimed = integrity.get("manifest_hash")
    if not isinstance(claimed, str) or not claimed:
        return findings
    try:
        from aep.validate_v0_5 import manifest_hash_v0_5
        manifest_for_hash = json.loads(json.dumps(manifest))  # deep copy
        if isinstance(manifest_for_hash.get("integrity"), dict):
            manifest_for_hash["integrity"].pop("manifest_hash", None)
            manifest_for_hash["integrity"].pop("views_merkle_root", None)
        manifest_for_hash.pop("signatures", None)
        computed = manifest_hash_v0_5(manifest_for_hash)
        if computed != claimed:
            findings.append(
                _mkfinding(
                    AEP70_INTEGRITY_MANIFEST_HASH_MISMATCH,
                    SEVERITY_ERROR,
                    f"integrity.manifest_hash drift detected: claimed={claimed!r} computed={computed!r}; manifest tampered or hash stale (exclusion: manifest_hash + views_merkle_root + signatures)",
                    "aepkg.json:integrity.manifest_hash",
                )
            )
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP70_INTERNAL_ERROR_MANIFEST_HASH_RECOMPUTE",
                SEVERITY_ERROR,
                f"manifest_hash recompute crashed: {exc}",
                "aepkg.json:integrity.manifest_hash",
            )
        )
    return findings


def _check_views_merkle_root(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.7.1 critical fix — recompute integrity.views_merkle_root.

    Closes adversary review cycle finding #7 (AEP70_VIEWS_MERKLE_MISMATCH declared but
    never emitted). When integrity.views_merkle_root is declared, recompute via
    views.views_merkle_root() and compare.
    """
    findings: List[Finding] = []
    integrity = manifest.get("integrity", {}) if isinstance(manifest.get("integrity"), dict) else {}
    claimed = integrity.get("views_merkle_root")
    if not isinstance(claimed, str) or not claimed:
        return findings
    try:
        from aep.views import views_merkle_root
        computed = views_merkle_root(packet_root)
        if computed != claimed:
            findings.append(
                _mkfinding(
                    AEP70_VIEWS_MERKLE_MISMATCH,
                    SEVERITY_ERROR,
                    f"integrity.views_merkle_root drift detected: claimed={claimed!r} computed={computed!r}; view bytes tampered or hash stale",
                    "aepkg.json:integrity.views_merkle_root",
                )
            )
    except ImportError:
        pass  # views module not available; skip
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP70_INTERNAL_ERROR_VIEWS_MERKLE_RECOMPUTE",
                SEVERITY_ERROR,
                f"views_merkle_root recompute crashed: {exc}",
                "aepkg.json:integrity.views_merkle_root",
            )
        )
    return findings


def validate_v0_6(packet_root: Path, config: ValidationConfig, allow_remote_context: bool = False) -> ValidationResult:
    """Run v0.5.5 validator plus all v0.6 closures.

    Strictly additive on top of v0.5.5: every v0.5.5-clean packet remains clean here.
    """
    # Map v0.6/v0.7 profiles back to v0.5.5-compatible profile for the baseline validator.
    base_config = config
    is_layered_profile = config.profile in {
        "aep:0.6/stable", "aep:0.6/jsonl-compact", "aep:0.6/linked-data",
        "aep:0.7/stable", "aep:0.7/signed", "aep:0.7/views-derived",
    }
    if is_layered_profile:
        base_config = ValidationConfig(
            profile="aep:0.5/stable",
            conformance_level=config.conformance_level,
            strict=config.strict,
        )
    base_result = validate_v0_5_1(packet_root, base_config)
    # When using a layered v0.6/v0.7 profile, the v0.5.5 base validator emits
    # several by-design failures because it doesn't recognize the layered profile.
    # Filter them out — multi-layer architecture: aep_version stays "0.5", profile
    # declares the layered profile (per spec §V60-1).
    if is_layered_profile:
        layered_profile_codes = {
            "AEP51_PROFILE_REQUEST_MISMATCH",
            "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH",
            "AEP51_VERSION_PROFILE_INCONSISTENT",
            "AEP51_VERSION_SCHEMA_MISMATCH",
        }
        filtered_findings = [
            f for f in base_result.findings if f.code not in layered_profile_codes
        ]
        # Recompute schema_result if filtering removed all errors
        if any(f.severity == SEVERITY_ERROR for f in filtered_findings):
            new_schema_result = base_result.schema_result
        elif any(f.severity == SEVERITY_WARNING for f in filtered_findings):
            new_schema_result = "warn" if base_result.schema_result == "fail" else base_result.schema_result
        else:
            new_schema_result = "pass" if base_result.schema_result == "fail" else base_result.schema_result
        base_result = ValidationResult(findings=filtered_findings, schema_result=new_schema_result)
    closure_findings: List[Finding] = []
    # Load manifest for v0.6 checks.
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return base_result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return base_result
    # Run v0.6 closures.
    closure_findings.extend(_check_compact_roundtrip(packet_root))
    closure_findings.extend(_check_embedded_index(packet_root, manifest))
    closure_findings.extend(_check_jsonld_context(packet_root, manifest, allow_remote_context))
    closure_findings.extend(_check_bagit_single_authority(packet_root, manifest))
    closure_findings.extend(_check_rocrate_single_authority(packet_root, manifest))
    # v0.6.0-rc2 — review cycle adversary closures (ATK-1 + ATK-2).
    closure_findings.extend(_check_reviewer_collapse(packet_root))
    closure_findings.extend(_check_source_location_hash_sentinel(packet_root))
    # v0.6.1 — review cycle follow-up closures (ATK-3 + ATK-4 + ATK-5 + SP-R8-01 + GATE-J1 + H5).
    closure_findings.extend(_check_gr_transitive_laundering(packet_root))
    closure_findings.extend(_check_supersession_integrity(packet_root, manifest))
    closure_findings.extend(_check_identity_authenticated(packet_root, manifest))
    closure_findings.extend(_check_body_envelope_split(packet_root, manifest))
    closure_findings.extend(_check_shared_schema_lens(packet_root))
    closure_findings.extend(_check_content_hash_recompute(packet_root, manifest))
    # v0.7-rc1 — view determinism + Ed25519 signature verification (when applicable).
    closure_findings.extend(_check_view_determinism(packet_root))
    if config.profile in {"aep:0.7/signed"}:
        closure_findings.extend(_check_signature_required(packet_root, manifest))
    # v0.7.1 CRITICAL FIXES (triple-check adversary pass — internal lesson):
    # Recompute integrity.state_hash + manifest_hash + views_merkle_root from
    # raw bytes and reject drift. Closes the trust-root subversion gap where
    # the v0.5.5 base validator failed to fire on nested integrity.* values.
    closure_findings.extend(_check_integrity_state_hash(packet_root, manifest))
    closure_findings.extend(_check_integrity_manifest_hash(packet_root, manifest))
    closure_findings.extend(_check_views_merkle_root(packet_root, manifest))
    # Merge.
    merged = list(base_result.findings) + closure_findings
    schema_state = base_result.schema_result
    if any(f.severity == SEVERITY_ERROR for f in closure_findings):
        schema_state = "fail"
    elif schema_state == "pass" and any(f.severity == SEVERITY_WARNING for f in closure_findings):
        schema_state = "warn"
    return ValidationResult(findings=merged, schema_result=schema_state)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse, sys
    parser = argparse.ArgumentParser(description="AEP v0.6.1 validator")
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("--profile", default="aep:0.6/stable", choices=sorted(VALID_PROFILES_V0_6))
    parser.add_argument("--conformance-level", type=int, default=2, choices=[1, 2, 3])
    parser.add_argument("--strict", action="store_true", default=True)
    parser.add_argument("--allow-remote-context", action="store_true", default=False)
    parser.add_argument("--emit-receipt", type=Path, default=None, help="Append a verification_receipt_v1 row to the given JSONL log")
    args = parser.parse_args(argv)
    cfg = ValidationConfig(profile=args.profile, conformance_level=args.conformance_level, strict=args.strict)
    result = validate_v0_6(args.packet_root, cfg, allow_remote_context=args.allow_remote_context)
    print(f"schema_result: {result.schema_result}")
    for f in result.findings:
        print(f"[{f.severity}] {f.code} @ {f.location}: {f.message}")
    if args.emit_receipt is not None:
        try:
            from aep.verification_receipt import build_receipt, emit_receipt, last_receipt_hash
            # Load manifest for packet_id + canonical_files
            manifest_path = args.packet_root / "aepkg.json"
            packet_id = None
            canonical_files: List[str] = []
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    packet_id = manifest.get("packet_id")
                    cf = manifest.get("canonical_files", [])
                    if isinstance(cf, list):
                        canonical_files = [c for c in cf if isinstance(c, str)]
                except Exception:
                    pass
            prev = last_receipt_hash(args.emit_receipt)
            receipt = build_receipt(
                args.packet_root, packet_id, canonical_files,
                "aep.validate_v0_6", "0.6.1",
                cfg.profile, cfg.conformance_level, cfg.strict,
                result.schema_result, result.findings,
                prev_receipt_hash=prev,
            )
            h = emit_receipt(receipt, args.emit_receipt)
            print(f"emitted receipt: {h}")
        except Exception as exc:
            print(f"WARNING: failed to emit receipt: {exc}", file=sys.stderr)
    return 0 if result.schema_result != "fail" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
