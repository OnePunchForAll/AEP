"""validate_v0_8.py — Apache-2.0 — AEP v0.8.0-rc1 reference validator.

Wraps v0.6 (`validate_v0_6`) with the v0.8 frontier-break field-presence and
format checks per `spec/AEP_v0_8_SPEC.md`. v0.8.0-rc1 ships SPEC + validator
field-presence + format checks + migration; F2/F5/F7 runtime EXECUTION runners
(reproduce loop, sandbox falsifier runner, counterexample replay) land in
v0.8.0 stable per §V80-15-b promotion criteria.

This is the §69.3 honest disclosure: rc1 enforces structural shape; stable
adds runtime mechanical enforcement. The SPEC's stated "mechanically enforced"
claims that require runtime execution are gated on stable.

Composes with:
- §02 truth-tags Amendment A15 (GOVERNANCE-RULE first-class)
- §69 Verification Law (F1 api_surface_verifications structural closure)
- §70 Surface Mirror Discipline (F4 surface_projections binding)
- §71 Operator Sustainability (F6 operator_cost_estimate scheduling metadata)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aep.validate_v0_6 import (
    validate_v0_6,
    ValidationConfig,
    ValidationResult,
    Finding,
    _mkfinding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    VALID_PROFILES_V0_6,
)

# ---------------------------------------------------------------------------
# v0.8 profiles + reason codes (per AEP_v0_8_SPEC.md §V80-11 + §V80-12)
# ---------------------------------------------------------------------------

VALID_PROFILES_V0_8 = VALID_PROFILES_V0_6 | {
    "aep:0.8/stable",
    "aep:0.8/reproducible",
    "aep:0.8/cross-substrate",
    "aep:0.8/surface-mirrored",
    "aep:0.8/self-falsifying",
    "aep:0.8/operator-cost-tracked",
    "aep:0.8/replay-ledger",
    "aep:0.8/preflight-gated",
    "aep:0.8/frontier-break",
}

# F8 PSC reason codes
AEP80_PSC_VERDICT_ALLOW = "AEP80_PSC_VERDICT_ALLOW"
AEP80_PSC_VERDICT_HEADER_ONLY = "AEP80_PSC_VERDICT_HEADER_ONLY"
AEP80_PSC_VERDICT_QUARANTINE = "AEP80_PSC_VERDICT_QUARANTINE"
AEP80_PSC_VERDICT_BLOCK = "AEP80_PSC_VERDICT_BLOCK"
AEP80_PSC_HEADER_MISSING = "AEP80_PSC_HEADER_MISSING"
AEP80_PSC_HEADER_MALFORMED = "AEP80_PSC_HEADER_MALFORMED"
AEP80_PSC_SCHEMA_MISMATCH = "AEP80_PSC_SCHEMA_MISMATCH"
AEP80_PSC_FORBIDDEN_CAPABILITY_REQUESTED = "AEP80_PSC_FORBIDDEN_CAPABILITY_REQUESTED"
AEP80_PSC_GRANDFATHERED_PRE_V0_8 = "AEP80_PSC_GRANDFATHERED_PRE_V0_8"
AEP80_PSC_VERIFIER_HASH_MISMATCH = "AEP80_PSC_VERIFIER_HASH_MISMATCH"

ALLOWED_PSC_VERDICTS = frozenset({"ALLOW_FULL_RETRIEVE", "HEADER_ONLY", "QUARANTINE", "BLOCK"})
FORBIDDEN_PSC_CAPABILITIES = frozenset({"network", "secrets", "write_host", "execute_packet_code"})

# §V80-15-a-2 ATK-V80-N4 mechanical closure: V0_8_RELEASE_DATE pin
# Validator computes grandfather-eligibility from this constant; ignores self-stamped boolean.
V0_8_RELEASE_DATE = "2026-05-17"
AEP80_PSC_GRANDFATHER_INELIGIBLE_BY_CREATED_AT = "AEP80_PSC_GRANDFATHER_INELIGIBLE_BY_CREATED_AT"

# F1 — API verification
AEP80_API_VERIFICATION_MISSING = "AEP80_API_VERIFICATION_MISSING"
AEP80_API_VERIFICATION_DOC_SOURCE_UNRESOLVED = "AEP80_API_VERIFICATION_DOC_SOURCE_UNRESOLVED"
AEP80_API_VERIFICATION_HAPPY_PATH_MISSING = "AEP80_API_VERIFICATION_HAPPY_PATH_MISSING"
AEP80_API_VERIFICATION_SIGNATURE_FORMAT_INVALID = "AEP80_API_VERIFICATION_SIGNATURE_FORMAT_INVALID"

# F2 — Reproducibility certificate
AEP80_REPRODUCIBILITY_CERTIFICATE_REQUIRED = "AEP80_REPRODUCIBILITY_CERTIFICATE_REQUIRED"
AEP80_REPRODUCIBILITY_TRANSITION_LOG_MISSING = "AEP80_REPRODUCIBILITY_TRANSITION_LOG_MISSING"
AEP80_REPRODUCIBILITY_SOURCE_DRIFT = "AEP80_REPRODUCIBILITY_SOURCE_DRIFT"
AEP80_REPRODUCIBILITY_BYTE_DRIFT = "AEP80_REPRODUCIBILITY_BYTE_DRIFT"
AEP80_REPRODUCIBILITY_NONDETERMINISTIC_OP = "AEP80_REPRODUCIBILITY_NONDETERMINISTIC_OP"
AEP80_REPRODUCIBILITY_REFERENCE_IMPL_VERSION_MISMATCH = "AEP80_REPRODUCIBILITY_REFERENCE_IMPL_VERSION_MISMATCH"
AEP80_REPRODUCIBILITY_PRE_V0_8_PACKET = "AEP80_REPRODUCIBILITY_PRE_V0_8_PACKET"

# F3 — External validator signatures
AEP80_EXTERNAL_SIG_INVALID = "AEP80_EXTERNAL_SIG_INVALID"
AEP80_EXTERNAL_SIG_DIGEST_DRIFT = "AEP80_EXTERNAL_SIG_DIGEST_DRIFT"
AEP80_EXTERNAL_SIG_SIGNER_NOT_DISTINCT = "AEP80_EXTERNAL_SIG_SIGNER_NOT_DISTINCT"
AEP80_EXTERNAL_SIG_REPRODUCE_CLAIM_UNVERIFIABLE = "AEP80_EXTERNAL_SIG_REPRODUCE_CLAIM_UNVERIFIABLE"

# F4 — Surface projections (binds to §70)
AEP80_PROJECTION_DRIFT_WARN = "AEP80_PROJECTION_DRIFT_WARN"
AEP80_PROJECTION_DRIFT_BLOCK = "AEP80_PROJECTION_DRIFT_BLOCK"
AEP80_PROJECTION_EXEMPT_REASON_INVALID = "AEP80_PROJECTION_EXEMPT_REASON_INVALID"
AEP80_PROJECTION_EXEMPT_PATTERN_DETECTED = "AEP80_PROJECTION_EXEMPT_PATTERN_DETECTED"
AEP80_PROJECTION_SELF_REFERENCE = "AEP80_PROJECTION_SELF_REFERENCE"

# F5 — Self-falsifying + sandbox (hardened under BP-V80-B)
AEP80_SELF_FALSIFIER_FIRED = "AEP80_SELF_FALSIFIER_FIRED"
AEP80_SELF_FALSIFIER_DEMOTE = "AEP80_SELF_FALSIFIER_DEMOTE"
AEP80_SELF_FALSIFIER_WARN = "AEP80_SELF_FALSIFIER_WARN"
AEP80_SELF_FALSIFIER_TIMEOUT = "AEP80_SELF_FALSIFIER_TIMEOUT"
AEP80_SELF_FALSIFIER_NOT_EXECUTED = "AEP80_SELF_FALSIFIER_NOT_EXECUTED"
AEP80_FALSIFIER_AST_DENIED_IMPORT = "AEP80_FALSIFIER_AST_DENIED_IMPORT"
AEP80_FALSIFIER_NETWORK_ISOLATION_BEST_EFFORT = "AEP80_FALSIFIER_NETWORK_ISOLATION_BEST_EFFORT"
AEP80_FALSIFIER_TOCTOU_DRIFT = "AEP80_FALSIFIER_TOCTOU_DRIFT"
AEP80_PROVEN_RELIABLE_WITHOUT_FALSIFIER = "AEP80_PROVEN_RELIABLE_WITHOUT_FALSIFIER"
AEP80_PROVEN_RELIABLE_PRE_V0_8_GRANDFATHERED = "AEP80_PROVEN_RELIABLE_PRE_V0_8_GRANDFATHERED"

# F7 — Counterexample replay ledger
AEP80_COUNTEREXAMPLE_REPLAY_FAILED = "AEP80_COUNTEREXAMPLE_REPLAY_FAILED"
AEP80_COUNTEREXAMPLE_BUDGET_EXCEEDED = "AEP80_COUNTEREXAMPLE_BUDGET_EXCEEDED"
AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED = "AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED"
AEP80_COUNTEREXAMPLE_ENV_LOCK_MISMATCH = "AEP80_COUNTEREXAMPLE_ENV_LOCK_MISMATCH"

# GOVERNANCE_RULE
AEP80_GOVERNANCE_RULE_OPERATOR_ATTESTATION_MISSING = "AEP80_GOVERNANCE_RULE_OPERATOR_ATTESTATION_MISSING"

# Profile composition (reserved)
AEP80_PROFILE_COMPOSITION_CONFLICT = "AEP80_PROFILE_COMPOSITION_CONFLICT"

# v0.7.2 deferred closures
AEP80_GR_TRANSITIVE_LAUNDERING_DEPTH = "AEP80_GR_TRANSITIVE_LAUNDERING_DEPTH"
AEP80_SHARED_SCHEMA_LENS_BYPASS_AT_CONVERGENCE_1 = "AEP80_SHARED_SCHEMA_LENS_BYPASS_AT_CONVERGENCE_1"
AEP80_PROFILE_ALIAS_FILTER_SPLIT_LOCATION = "AEP80_PROFILE_ALIAS_FILTER_SPLIT_LOCATION"

# Internal sentinel for rc1 disclosure
AEP80_RC1_EXECUTION_DEFERRED = "AEP80_RC1_EXECUTION_DEFERRED"

# §V80-3 F1 — API-bearing claim detection regex
API_BEARING_PATTERN = re.compile(
    r"\b(fetch|window\.[a-z]+|require|import\s+\S+\s+from|api\.[a-z]+|sdk\.[a-z]+|client\.[a-z]+|httpx\.[a-z]+|requests\.[a-z]+|aiohttp\.[a-z]+|axios\.[a-z]+)\(",
    re.IGNORECASE,
)

# §V80-7 FALSIFIER-V80-1 AST deny-list
DENIED_FALSIFIER_IMPORTS = frozenset({
    "os", "subprocess", "socket", "ctypes", "multiprocessing",
    "threading", "concurrent", "signal", "pty", "pickle", "marshal",
    "shelve", "urllib", "http", "requests", "httpx", "aiohttp",
    "asyncio.subprocess", "asyncio.open_connection",
})

# §V80-1-bis EXEMPT reason-code closed list (mirrors §70.1-bis)
ALLOWED_PROJECTION_EXEMPT_CODES = frozenset({
    "HOOK-ONLY", "INTERNAL-INFRA", "EMERGENCY-INCIDENT",
    "SEED-SCAFFOLD-STAGED", "NON-OPERATOR-SURFACE",
})

# F7 fatigue-budget caps (milliseconds total per packet)
COUNTEREXAMPLE_BUDGET_CAP_MS = {"low": 500, "med": 5000, "high": 30000}


# ---------------------------------------------------------------------------
# F1 — api_surface_verifications
# ---------------------------------------------------------------------------

def _check_api_surface_verifications(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-3 F1 — every API-bearing claim has an api_surface_verifications record."""
    findings: List[Finding] = []
    claims_path = packet_root / "data" / "claims.jsonl"
    api_records_path = packet_root / "data" / "api_surface_verifications.jsonl"
    sources_path = packet_root / "data" / "sources.jsonl"

    if not claims_path.exists():
        return findings

    # Collect api-bearing claim ids by regex scan.
    api_bearing_claim_ids: Set[str] = set()
    for line in claims_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = rec.get("text", "") or rec.get("claim_text", "")
        if isinstance(text, str) and API_BEARING_PATTERN.search(text):
            cid = rec.get("id") or rec.get("claim_id")
            if cid:
                api_bearing_claim_ids.add(cid)

    if not api_bearing_claim_ids:
        return findings

    # Load existing verifications.
    verified_claims: Set[str] = set()
    bad_format_count = 0
    if api_records_path.exists():
        for line in api_records_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_format_count += 1
                continue
            cid = rec.get("claim_id")
            api_surface = rec.get("api_surface", "")
            if "(" not in api_surface or not API_BEARING_PATTERN.search(api_surface):
                bad_format_count += 1
                findings.append(_mkfinding(
                    AEP80_API_VERIFICATION_SIGNATURE_FORMAT_INVALID,
                    SEVERITY_ERROR,
                    f"api_surface_verifications record for claim {cid!r} has malformed api_surface field: {api_surface!r}",
                    "data/api_surface_verifications.jsonl",
                ))
                continue
            if not rec.get("happy_path_trace_sha256"):
                findings.append(_mkfinding(
                    AEP80_API_VERIFICATION_HAPPY_PATH_MISSING,
                    SEVERITY_ERROR,
                    f"api_surface_verifications record for claim {cid!r} missing happy_path_trace_sha256",
                    "data/api_surface_verifications.jsonl",
                ))
                continue
            # Verify doc_source_id resolves.
            doc_source_id = rec.get("doc_source_id")
            if doc_source_id and sources_path.exists():
                source_ids = set()
                for sline in sources_path.read_text(encoding="utf-8").splitlines():
                    try:
                        srec = json.loads(sline)
                        sid = srec.get("id") or srec.get("source_id")
                        if sid:
                            source_ids.add(sid)
                    except json.JSONDecodeError:
                        pass
                if doc_source_id not in source_ids:
                    findings.append(_mkfinding(
                        AEP80_API_VERIFICATION_DOC_SOURCE_UNRESOLVED,
                        SEVERITY_ERROR,
                        f"api_surface_verifications doc_source_id {doc_source_id!r} does not resolve in sources.jsonl",
                        "data/api_surface_verifications.jsonl",
                    ))
                    continue
            if cid:
                verified_claims.add(cid)

    missing = api_bearing_claim_ids - verified_claims
    profile = manifest.get("profile", "")
    severity = SEVERITY_ERROR if profile in {
        "aep:0.8/reproducible", "aep:0.8/cross-substrate", "aep:0.8/frontier-break",
    } else SEVERITY_WARNING
    for cid in sorted(missing):
        findings.append(_mkfinding(
            AEP80_API_VERIFICATION_MISSING,
            severity,
            f"api-bearing claim {cid!r} has no api_surface_verifications record (per §V80-3 F1)",
            f"data/claims.jsonl:claim_id={cid}",
        ))
    return findings


# ---------------------------------------------------------------------------
# F2 — reproducibility_certificate (presence + format; runtime reproduce in stable)
# ---------------------------------------------------------------------------

def _check_reproducibility_certificate(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-4 F2 — reproducibility_certificate presence + format (rc1).

    rc1 enforces field presence + format. Full reproduce-from-sources loop
    lands in v0.8.0 stable per §V80-15-b promotion criteria.
    """
    findings: List[Finding] = []
    integrity = manifest.get("integrity", {})
    cert = integrity.get("reproducibility_certificate")
    profile = manifest.get("profile", "")

    if profile in {"aep:0.8/reproducible", "aep:0.8/cross-substrate", "aep:0.8/frontier-break"}:
        if not isinstance(cert, dict):
            findings.append(_mkfinding(
                AEP80_REPRODUCIBILITY_CERTIFICATE_REQUIRED,
                SEVERITY_ERROR,
                f"profile {profile!r} requires integrity.reproducibility_certificate (per §V80-4)",
                "aepkg.json:integrity.reproducibility_certificate",
            ))
            return findings
        # Transition log required if certified=true.
        if cert.get("certified") is True:
            tlog = packet_root / "reproducibility" / "transition_log.jsonl"
            if not tlog.exists():
                findings.append(_mkfinding(
                    AEP80_REPRODUCIBILITY_TRANSITION_LOG_MISSING,
                    SEVERITY_ERROR,
                    "reproducibility_certificate.certified=true but reproducibility/transition_log.jsonl missing",
                    "reproducibility/transition_log.jsonl",
                ))
            # rc1 disclosure: full reproduce loop deferred to stable.
            findings.append(_mkfinding(
                AEP80_RC1_EXECUTION_DEFERRED,
                SEVERITY_INFO,
                "v0.8.0-rc1: reproducibility_certificate field-presence verified; bit-for-bit re-derivation deferred to v0.8.0 stable per §V80-15-b",
                "aepkg.json:integrity.reproducibility_certificate",
            ))

    elif isinstance(cert, dict) and cert.get("reason") == "PRE-v0.8-PACKET-NOT-REPRODUCED":
        # Birth-only scope disclosure per §V80-4-bis.
        findings.append(_mkfinding(
            AEP80_REPRODUCIBILITY_PRE_V0_8_PACKET,
            SEVERITY_INFO,
            "pre-v0.8 packet: reproducibility certification is structurally unavailable (per §V80-4-bis birth-only scope)",
            "aepkg.json:integrity.reproducibility_certificate",
        ))
    return findings


# ---------------------------------------------------------------------------
# F3 — external_validator_signatures
# ---------------------------------------------------------------------------

def _check_external_validator_signatures(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-5 F3 — external validator signatures (presence + distinctness)."""
    findings: List[Finding] = []
    sig_dir = packet_root / "signatures" / "external"
    profile = manifest.get("profile", "")
    integrity = manifest.get("integrity", {})

    if not sig_dir.exists():
        # No external sigs is valid for most profiles.
        if profile in {"aep:0.8/cross-substrate", "aep:0.8/frontier-break"}:
            findings.append(_mkfinding(
                AEP80_EXTERNAL_SIG_INVALID,
                SEVERITY_ERROR,
                f"profile {profile!r} requires ≥3 external_validator_signatures (per §V80-5 F3)",
                "signatures/external/",
            ))
        return findings

    signers_seen: Set[str] = set()
    primary_signer_did = integrity.get("primary_signer_did", "")
    reproduced_count = 0
    for sig_path in sorted(sig_dir.glob("*.sig.json")):
        try:
            sig_rec = json.loads(sig_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append(_mkfinding(
                AEP80_EXTERNAL_SIG_INVALID,
                SEVERITY_ERROR,
                f"external signature {sig_path.name} is not valid JSON",
                str(sig_path.relative_to(packet_root)),
            ))
            continue
        signer_did = sig_rec.get("signer_did", "")
        if signer_did in signers_seen or signer_did == primary_signer_did:
            findings.append(_mkfinding(
                AEP80_EXTERNAL_SIG_SIGNER_NOT_DISTINCT,
                SEVERITY_ERROR,
                f"external signer {signer_did!r} is not distinct (per §V80-5 SIGNER-V80-1)",
                str(sig_path.relative_to(packet_root)),
            ))
            continue
        signers_seen.add(signer_did)
        if sig_rec.get("reproduced_independently") is True:
            reproduced_count += 1

    # rc1: cryptographic verification of signatures deferred to stable
    if signers_seen:
        findings.append(_mkfinding(
            AEP80_RC1_EXECUTION_DEFERRED,
            SEVERITY_INFO,
            f"v0.8.0-rc1: {len(signers_seen)} external_validator_signatures structure verified; Ed25519 verification deferred to v0.8.0 stable",
            "signatures/external/",
        ))

    if profile in {"aep:0.8/cross-substrate", "aep:0.8/frontier-break"}:
        if len(signers_seen) < 3:
            findings.append(_mkfinding(
                AEP80_EXTERNAL_SIG_INVALID,
                SEVERITY_ERROR,
                f"profile {profile!r} requires ≥3 distinct external signers; found {len(signers_seen)}",
                "signatures/external/",
            ))
        if reproduced_count < 2:
            findings.append(_mkfinding(
                AEP80_EXTERNAL_SIG_REPRODUCE_CLAIM_UNVERIFIABLE,
                SEVERITY_WARNING,
                f"profile {profile!r} expects ≥2 signers with reproduced_independently=true; found {reproduced_count}",
                "signatures/external/",
            ))
    return findings


# ---------------------------------------------------------------------------
# F4 — surface_projections
# ---------------------------------------------------------------------------

def _check_surface_projections(packet_root: Path, manifest: Dict[str, Any], repo_root: Path) -> List[Finding]:
    """v0.8 §V80-6 F4 — surface projections drift detection + EXEMPT validation."""
    findings: List[Finding] = []
    projections = manifest.get("surface_projections")
    profile = manifest.get("profile", "")

    if not isinstance(projections, list):
        if profile in {"aep:0.8/surface-mirrored", "aep:0.8/frontier-break"}:
            findings.append(_mkfinding(
                AEP80_PROJECTION_DRIFT_BLOCK,
                SEVERITY_ERROR,
                f"profile {profile!r} requires surface_projections[] (per §V80-6 F4)",
                "aepkg.json:surface_projections",
            ))
        return findings

    surface_counts: Dict[str, int] = {}
    for proj in projections:
        if not isinstance(proj, dict):
            continue
        surface = proj.get("mirror_surface", "")
        surface_counts[surface] = surface_counts.get(surface, 0) + 1
        exempt = proj.get("exempt_reason_code")
        if exempt:
            if exempt not in ALLOWED_PROJECTION_EXEMPT_CODES:
                findings.append(_mkfinding(
                    AEP80_PROJECTION_EXEMPT_REASON_INVALID,
                    SEVERITY_ERROR,
                    f"surface_projections entry has invalid exempt_reason_code {exempt!r}; allowed: {sorted(ALLOWED_PROJECTION_EXEMPT_CODES)}",
                    "aepkg.json:surface_projections",
                ))
            continue
        # Non-exempt: verify mirror_path resolves and sha256 matches.
        mirror_path_str = proj.get("mirror_path", "")
        declared_sha = proj.get("canonical_source_sha256", "")
        if mirror_path_str:
            mirror_full = repo_root / mirror_path_str
            if mirror_full.exists() and mirror_full.is_file():
                # Self-reference check (BP-V80-D)
                try:
                    if mirror_full.resolve() == packet_root.resolve() / "aepkg.json":
                        findings.append(_mkfinding(
                            AEP80_PROJECTION_SELF_REFERENCE,
                            SEVERITY_WARNING,
                            f"surface_projections mirror_path {mirror_path_str!r} self-references the packet",
                            "aepkg.json:surface_projections",
                        ))
                        continue
                except (OSError, ValueError):
                    pass
                if declared_sha and re.match(r"^[a-f0-9]{64}$", declared_sha):
                    actual = hashlib.sha256(mirror_full.read_bytes()).hexdigest()
                    if actual != declared_sha:
                        # Drift detected; severity by age would need timestamp parsing
                        # For rc1: emit WARN (BLOCK reserved for runtime hook integration in stable)
                        findings.append(_mkfinding(
                            AEP80_PROJECTION_DRIFT_WARN,
                            SEVERITY_WARNING,
                            f"surface_projections mirror_path {mirror_path_str!r}: declared sha {declared_sha[:12]}... != actual sha {actual[:12]}...",
                            "aepkg.json:surface_projections",
                        ))

    # §V80-1-bis EXEMPT pattern detection (N=3 trigger)
    for surface, count in surface_counts.items():
        if count >= 3:
            # Check if all 3+ are exempt
            exempt_in_surface = sum(1 for p in projections if p.get("mirror_surface") == surface and p.get("exempt_reason_code"))
            if exempt_in_surface >= 3:
                findings.append(_mkfinding(
                    AEP80_PROJECTION_EXEMPT_PATTERN_DETECTED,
                    SEVERITY_WARNING,
                    f"surface {surface!r} has {exempt_in_surface} EXEMPT stamps (per §V80-1-bis N=3 trigger)",
                    "aepkg.json:surface_projections",
                ))
    return findings


# ---------------------------------------------------------------------------
# F5 — self_falsifying (presence + AST-deny-list; runtime in stable)
# ---------------------------------------------------------------------------

def _check_self_falsifying(packet_root: Path, manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-7 F5 — self_falsifying field-presence + format (rc1).

    Full sandbox-execution runner lands in v0.8.0 stable. rc1 validates:
      - field shape
      - test_kind ∈ {static, subprocess}
      - PROVEN_RELIABLE-without-falsifier grandfather logic
    """
    findings: List[Finding] = []
    falsifiers = manifest.get("self_falsifying")
    profile = manifest.get("profile", "")

    if not isinstance(falsifiers, list):
        falsifiers = []

    # rc1: validate field shape only.
    for f in falsifiers:
        if not isinstance(f, dict):
            continue
        test_kind = f.get("test_kind", "static")
        if test_kind not in {"static", "subprocess"}:
            findings.append(_mkfinding(
                AEP80_SELF_FALSIFIER_NOT_EXECUTED,
                SEVERITY_WARNING,
                f"self_falsifying entry {f.get('falsifier_id')!r} has invalid test_kind {test_kind!r}",
                "aepkg.json:self_falsifying",
            ))
        # Cross-substrate profile + subprocess forbidden (FALSIFIER-V80-6).
        if profile == "aep:0.8/cross-substrate" and test_kind == "subprocess":
            findings.append(_mkfinding(
                AEP80_FALSIFIER_AST_DENIED_IMPORT,
                SEVERITY_ERROR,
                f"cross-substrate profile forbids test_kind=subprocess (per §V80-7 FALSIFIER-V80-6); falsifier {f.get('falsifier_id')!r}",
                "aepkg.json:self_falsifying",
            ))

    if profile in {"aep:0.8/self-falsifying", "aep:0.8/frontier-break"} and not falsifiers:
        findings.append(_mkfinding(
            AEP80_SELF_FALSIFIER_NOT_EXECUTED,
            SEVERITY_ERROR,
            f"profile {profile!r} requires self_falsifying[] non-empty (per §V80-7 F5)",
            "aepkg.json:self_falsifying",
        ))

    if falsifiers:
        findings.append(_mkfinding(
            AEP80_RC1_EXECUTION_DEFERRED,
            SEVERITY_INFO,
            f"v0.8.0-rc1: {len(falsifiers)} self_falsifying entries structure verified; sandbox execution deferred to v0.8.0 stable",
            "aepkg.json:self_falsifying",
        ))

    # FALSIFIER-V80-9 PROVEN_RELIABLE-without-falsifier check (with grandfather clause).
    claims_path = packet_root / "data" / "claims.jsonl"
    if claims_path.exists() and profile in {"aep:0.8/self-falsifying", "aep:0.8/frontier-break"}:
        bound_claim_ids = {f.get("binds_to_claim_id") for f in falsifiers if isinstance(f, dict)}
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rel = rec.get("reliability", "")
            if rel not in {"PROVEN_RELIABLE", "R"}:
                continue
            cid = rec.get("id") or rec.get("claim_id")
            meta = rec.get("axis_a_meta", {})
            grandfathered = (
                meta.get("grandfathered_pre_v0_8") is True
                if isinstance(meta, dict) else False
            )
            if grandfathered:
                findings.append(_mkfinding(
                    AEP80_PROVEN_RELIABLE_PRE_V0_8_GRANDFATHERED,
                    SEVERITY_INFO,
                    f"claim {cid!r} is grandfathered pre-v0.8 PROVEN_RELIABLE (per §V80-7-bis)",
                    f"data/claims.jsonl:claim_id={cid}",
                ))
                continue
            if cid not in bound_claim_ids:
                findings.append(_mkfinding(
                    AEP80_PROVEN_RELIABLE_WITHOUT_FALSIFIER,
                    SEVERITY_ERROR,
                    f"PROVEN_RELIABLE claim {cid!r} has no binding self_falsifying entry (per FALSIFIER-V80-9)",
                    f"data/claims.jsonl:claim_id={cid}",
                ))
    return findings


# ---------------------------------------------------------------------------
# F6 — operator_cost_estimate (informational only)
# ---------------------------------------------------------------------------

def _check_operator_cost_estimate(manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-8 F6 — operator cost estimate presence + format. Informational."""
    findings: List[Finding] = []
    cost = manifest.get("operator_cost_estimate")
    profile = manifest.get("profile", "")
    if profile in {"aep:0.8/operator-cost-tracked", "aep:0.8/frontier-break"}:
        if not isinstance(cost, dict):
            findings.append(_mkfinding(
                "AEP80_OPERATOR_COST_ESTIMATE_MISSING",
                SEVERITY_WARNING,
                f"profile {profile!r} requires operator_cost_estimate (per §V80-8 F6)",
                "aepkg.json:operator_cost_estimate",
            ))
        elif cost.get("cognitive_tier") not in {"low", "med", "high"}:
            findings.append(_mkfinding(
                "AEP80_OPERATOR_COST_ESTIMATE_INVALID",
                SEVERITY_WARNING,
                f"operator_cost_estimate.cognitive_tier must be low/med/high",
                "aepkg.json:operator_cost_estimate.cognitive_tier",
            ))
    return findings


# ---------------------------------------------------------------------------
# F7 — counterexample_bundle (presence + format; replay runtime in stable)
# ---------------------------------------------------------------------------

def _check_counterexample_bundle(manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-8-bis F7 — counterexample bundle presence + format (rc1).

    Replay runtime lands in v0.8.0 stable.
    """
    findings: List[Finding] = []
    bundle = manifest.get("counterexample_bundle")
    profile = manifest.get("profile", "")

    if not isinstance(bundle, list):
        bundle = []

    if profile in {"aep:0.8/replay-ledger", "aep:0.8/frontier-break"} and not bundle:
        findings.append(_mkfinding(
            AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED,
            SEVERITY_ERROR,
            f"profile {profile!r} requires counterexample_bundle[] non-empty (per §V80-8-bis F7)",
            "aepkg.json:counterexample_bundle",
        ))

    for ce in bundle:
        if not isinstance(ce, dict):
            continue
        budget = ce.get("fatigue_budget_tag", "med")
        if budget not in COUNTEREXAMPLE_BUDGET_CAP_MS:
            findings.append(_mkfinding(
                AEP80_COUNTEREXAMPLE_BUDGET_EXCEEDED,
                SEVERITY_WARNING,
                f"counterexample {ce.get('counterexample_id')!r} has invalid fatigue_budget_tag {budget!r}",
                "aepkg.json:counterexample_bundle",
            ))
        binding = ce.get("binds_to_failure_class", "")
        if not binding or not isinstance(binding, str):
            findings.append(_mkfinding(
                AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED,
                SEVERITY_WARNING,
                f"counterexample {ce.get('counterexample_id')!r} missing binds_to_failure_class",
                "aepkg.json:counterexample_bundle",
            ))

    if bundle:
        findings.append(_mkfinding(
            AEP80_RC1_EXECUTION_DEFERRED,
            SEVERITY_INFO,
            f"v0.8.0-rc1: {len(bundle)} counterexample_bundle entries structure verified; replay execution deferred to v0.8.0 stable",
            "aepkg.json:counterexample_bundle",
        ))
    return findings


# ---------------------------------------------------------------------------
# GOVERNANCE_RULE — operator attestation check
# ---------------------------------------------------------------------------

def _check_governance_rule_attestation(packet_root: Path) -> List[Finding]:
    """v0.8 §V80-9 — GOVERNANCE_RULE claims must carry operator attestation."""
    findings: List[Finding] = []
    claims_path = packet_root / "data" / "claims.jsonl"
    if not claims_path.exists():
        return findings
    for line in claims_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rel = rec.get("reliability", "")
        if rel not in {"GOVERNANCE_RULE", "G"}:
            continue
        attested_by = rec.get("attested_by") or rec.get("operator_attestation")
        if not attested_by:
            findings.append(_mkfinding(
                AEP80_GOVERNANCE_RULE_OPERATOR_ATTESTATION_MISSING,
                SEVERITY_WARNING,
                f"GOVERNANCE_RULE claim {rec.get('id') or rec.get('claim_id')!r} missing attested_by/operator_attestation field (per §V80-9)",
                f"data/claims.jsonl:claim_id={rec.get('id') or rec.get('claim_id')}",
            ))
    return findings


# ---------------------------------------------------------------------------
# F8 — preflight_sandbox_capsule (presence + format; verifier execution external)
# ---------------------------------------------------------------------------

def _check_preflight_sandbox_capsule(manifest: Dict[str, Any]) -> List[Finding]:
    """v0.8 §V80-8-ter F8 — Preflight Sandbox Capsule field-presence + format.

    The PSC verifier itself (`aep08_preflight_min.py`) runs OUTSIDE this
    validator — it is the FIRST gate before validate_v0_8 fires. This check
    validates that the packet declares a well-formed PSC field in its
    manifest, consistent with whatever the external verifier saw.
    """
    findings: List[Finding] = []
    psc = manifest.get("preflight_sandbox_capsule")
    profile = manifest.get("profile", "")

    requires_psc = profile in {
        "aep:0.8/preflight-gated", "aep:0.8/cross-substrate", "aep:0.8/frontier-break",
    }

    if not isinstance(psc, dict):
        if requires_psc:
            findings.append(_mkfinding(
                AEP80_PSC_HEADER_MISSING,
                SEVERITY_ERROR,
                f"profile {profile!r} requires preflight_sandbox_capsule (per §V80-8-ter F8)",
                "aepkg.json:preflight_sandbox_capsule",
            ))
        return findings

    # Grandfather clause per PSC-V80-15 + ATK-V80-N4 mechanical closure.
    if psc.get("grandfathered_pre_v0_8") is True:
        # ATK-V80-N4: recompute grandfather-eligibility from created_at, ignore self-stamp.
        created_at = manifest.get("created_at", "") or manifest.get("created", "")
        if created_at and created_at[:10] >= V0_8_RELEASE_DATE:
            findings.append(_mkfinding(
                AEP80_PSC_GRANDFATHER_INELIGIBLE_BY_CREATED_AT,
                SEVERITY_ERROR,
                f"packet self-stamps grandfathered_pre_v0_8=true but created_at={created_at!r} is >= V0_8_RELEASE_DATE={V0_8_RELEASE_DATE} (per ATK-V80-N4 closure)",
                "aepkg.json:preflight_sandbox_capsule.grandfathered_pre_v0_8",
            ))
            return findings
        findings.append(_mkfinding(
            AEP80_PSC_GRANDFATHERED_PRE_V0_8,
            SEVERITY_INFO,
            "pre-v0.8 packet grandfathered: PSC verdict pre-set to HEADER_ONLY (per PSC-V80-15)",
            "aepkg.json:preflight_sandbox_capsule",
        ))
        return findings

    # Schema check.
    if psc.get("schema") != "aep-preflight-0.8":
        findings.append(_mkfinding(
            AEP80_PSC_SCHEMA_MISMATCH,
            SEVERITY_ERROR,
            f"preflight_sandbox_capsule.schema must be 'aep-preflight-0.8'; got {psc.get('schema')!r}",
            "aepkg.json:preflight_sandbox_capsule.schema",
        ))

    # Forbidden capability check (PSC-V80-6).
    caps = psc.get("capabilities") or {}
    for cap in FORBIDDEN_PSC_CAPABILITIES:
        if caps.get(cap) is True:
            findings.append(_mkfinding(
                AEP80_PSC_FORBIDDEN_CAPABILITY_REQUESTED,
                SEVERITY_ERROR,
                f"PSC declares forbidden capability {cap!r}; verdict must be BLOCK per PSC-V80-6",
                "aepkg.json:preflight_sandbox_capsule.capabilities",
            ))

    # Verdict ladder check.
    verdict = psc.get("last_verdict") or psc.get("verdict")
    if verdict and verdict not in ALLOWED_PSC_VERDICTS:
        findings.append(_mkfinding(
            AEP80_PSC_HEADER_MALFORMED,
            SEVERITY_WARNING,
            f"PSC verdict {verdict!r} not in allowed set {sorted(ALLOWED_PSC_VERDICTS)}",
            "aepkg.json:preflight_sandbox_capsule.last_verdict",
        ))

    # Frontier-break profile requires verdict ALLOW or HEADER_ONLY.
    if profile == "aep:0.8/frontier-break" and verdict in {"QUARANTINE", "BLOCK"}:
        findings.append(_mkfinding(
            AEP80_PSC_VERDICT_BLOCK,
            SEVERITY_ERROR,
            f"frontier-break profile requires PSC verdict ALLOW_FULL_RETRIEVE or HEADER_ONLY; got {verdict!r}",
            "aepkg.json:preflight_sandbox_capsule.last_verdict",
        ))

    return findings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

PROFILE_ALIAS_FILTERS = {
    "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH",
    "AEP51_PROFILE_REQUEST_MISMATCH",
    "AEP51_VERSION_PROFILE_INCONSISTENT",
    "AEP51_VERSION_SCHEMA_MISMATCH",
}


def _filter_v0_8_profile_aliases(findings: List[Finding], profile: str) -> List[Finding]:
    """Per §V80-10 close-deferred-attack AEP80_PROFILE_ALIAS_FILTER_SPLIT_LOCATION:
    extend v0.6's multi-layer profile aliasing to v0.8 profiles, but split on
    (code, location) tuple instead of code alone — preserves legitimate
    AEP51_VERSION_SCHEMA_MISMATCH from declared schema_fingerprint mismatch.
    """
    if not profile.startswith("aep:0.8/"):
        return findings
    out: List[Finding] = []
    for f in findings:
        if f.code in PROFILE_ALIAS_FILTERS:
            # AEP51_VERSION_SCHEMA_MISMATCH only filtered when from manifest.json
            # location AND triggered by base-validator profile-channel comparison
            # (not by a real schema_fingerprint mismatch at deeper location).
            if f.code == "AEP51_VERSION_SCHEMA_MISMATCH" and f.location and "schema_fingerprint" in f.location:
                out.append(f)
                continue
            # Aliased — drop.
            continue
        out.append(f)
    return out


def validate_v0_8(
    packet_root: Path,
    config: Optional[ValidationConfig] = None,
    repo_root: Optional[Path] = None,
) -> ValidationResult:
    """v0.8.0-rc1 reference validator.

    Wraps v0.6 + adds v0.8 frontier-break field-presence and format checks.
    Full runtime execution runners (F2 reproduce, F5 sandbox, F7 replay) are
    staged for v0.8.0 stable per §V80-15-b promotion criteria.
    """
    if config is None:
        config = ValidationConfig()
    # Allow v0.8 profiles through.
    if hasattr(config, "valid_profiles"):
        config.valid_profiles = VALID_PROFILES_V0_8

    # Run v0.6 validator first.
    result = validate_v0_6(packet_root, config)

    # Filter v0.8 profile-alias noise from v0.5/v0.6 base findings.
    manifest_for_profile = packet_root / "aepkg.json"
    if manifest_for_profile.exists():
        try:
            mfp = json.loads(manifest_for_profile.read_text(encoding="utf-8"))
            packet_profile = mfp.get("profile", "")
            result.findings = _filter_v0_8_profile_aliases(result.findings, packet_profile)
        except json.JSONDecodeError:
            pass

    # Load manifest for v0.8 checks.
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return result

    # Determine repo root for surface_projections drift check.
    if repo_root is None:
        # Walk up from packet_root looking for .git
        p = packet_root.resolve()
        while p != p.parent:
            if (p / ".git").exists():
                repo_root = p
                break
            p = p.parent
        if repo_root is None:
            repo_root = packet_root.parent

    # v0.8 checks (additive; do not modify v0.6 findings).
    extra_findings: List[Finding] = []
    extra_findings.extend(_check_api_surface_verifications(packet_root, manifest))
    extra_findings.extend(_check_reproducibility_certificate(packet_root, manifest))
    extra_findings.extend(_check_external_validator_signatures(packet_root, manifest))
    extra_findings.extend(_check_surface_projections(packet_root, manifest, repo_root))
    extra_findings.extend(_check_self_falsifying(packet_root, manifest))
    extra_findings.extend(_check_operator_cost_estimate(manifest))
    extra_findings.extend(_check_counterexample_bundle(manifest))
    extra_findings.extend(_check_governance_rule_attestation(packet_root))
    extra_findings.extend(_check_preflight_sandbox_capsule(manifest))

    # Attach to result.
    result.findings.extend(extra_findings)
    # Update error/warning counts.
    result.error_count = sum(1 for f in result.findings if f.severity == SEVERITY_ERROR)
    result.warning_count = sum(1 for f in result.findings if f.severity == SEVERITY_WARNING)
    if result.error_count > 0:
        result.schema_result = "fail"
    return result


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: `python -m aep.validate_v0_8 <packet> [--profile <p>]`"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="AEP v0.8.0-rc1 validator")
    parser.add_argument("packet", type=Path, help="Path to .aepkg/ directory")
    parser.add_argument("--profile", default=None, help="Override declared profile")
    parser.add_argument("--strict", action="store_true", help="exit 1 on any error")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    config = ValidationConfig()
    if args.profile:
        config.profile = args.profile

    result = validate_v0_8(args.packet, config)
    if args.json:
        print(json.dumps({
            "packet": str(args.packet),
            "schema_result": result.schema_result,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "findings": [
                {"code": f.code, "severity": f.severity, "message": f.message, "location": f.location}
                for f in result.findings
            ],
        }, indent=2))
    else:
        print(f"AEP v0.8.0-rc1 validate · {args.packet}")
        print(f"  schema_result={result.schema_result} errors={result.error_count} warnings={result.warning_count}")
        for f in result.findings:
            print(f"  [{f.severity:5s}] {f.code} @ {f.location}: {f.message}")

    return 1 if (args.strict and result.error_count > 0) else 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
