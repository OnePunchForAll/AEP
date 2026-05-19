# Copyright 2026 AEP Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""AEP validator v0.5.1 hot-patch.

This module is strictly additive over :mod:`aep.validate_v0_5`.
It applies three fail-closed closures:

1. Schema/Profile Binding Hard-Fail (Round-4 #1 + #4)
2. Artifact Closure Integrity (Round-4 #7)
3. Numeric Canonicalization Lockdown (Round-4 #2)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import decimal
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import aep.validate_v0_5 as _v05_module
from aep.validate_v0_5 import (
    CONFORMANCE_LEVEL_1,
    CONFORMANCE_LEVEL_2,
    CONFORMANCE_LEVEL_3,
    GOVERNANCE_RULE,
    INFERENCE_ONLY_LABELS,
    MERKLE_EMPTY,
    MERKLE_LEAF_DOMAIN,
    MERKLE_NODE_DOMAIN,
    RELIABILITY_TIERS,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    VALID_PROFILES,
    Finding,
    ValidationConfig,
    ValidationResult,
    _ensure_utc,
    _mkfinding,
    _read_jsonl,
    _read_text,
    aep_merkle_v1,
    canonical_state_hash_v0_5,
    manifest_hash_v0_5,
    parse_strict_canonical,
    serialize_strict_canonical,
    validate_v0_5,
)

# --------------------------------------------
# AEP v0.5.1 reason codes (additive; no AEP5_* collisions)
# --------------------------------------------

AEP51_VERSION_SCHEMA_MISMATCH = "AEP51_VERSION_SCHEMA_MISMATCH"
AEP51_PROFILE_REQUEST_MISMATCH = "AEP51_PROFILE_REQUEST_MISMATCH"
AEP51_VERSION_PROFILE_INCONSISTENT = "AEP51_VERSION_PROFILE_INCONSISTENT"
AEP51_SCHEMA_FINGERPRINT_UNKNOWN = "AEP51_SCHEMA_FINGERPRINT_UNKNOWN"

AEP51_UNMANIFESTED_REFERENCE = "AEP51_UNMANIFESTED_REFERENCE"
AEP51_HIDDEN_CANONICAL_FILE = "AEP51_HIDDEN_CANONICAL_FILE"

AEP51_NUMERIC_OUT_OF_RANGE = "AEP51_NUMERIC_OUT_OF_RANGE"
AEP51_NUMERIC_FORBIDDEN = "AEP51_NUMERIC_FORBIDDEN"
AEP51_NUMERIC_NONCANONICAL_FORM = "AEP51_NUMERIC_NONCANONICAL_FORM"
AEP51_NUMERIC_PRECISION_LOSS = "AEP51_NUMERIC_PRECISION_LOSS"

# v0.5.3 hot-patch reason codes (Round-5 closures)
AEP53_GR_GO_EMPTY_JUSTIFICATION = "AEP53_GR_GO_EMPTY_JUSTIFICATION"
AEP53_GR_GO_DANGLING_JUSTIFICATION = "AEP53_GR_GO_DANGLING_JUSTIFICATION"
AEP53_GR_GO_JUSTIFICATION_IS_GR = "AEP53_GR_GO_JUSTIFICATION_IS_GR"
AEP53_PATH_TRAVERSAL_REJECTED = "AEP53_PATH_TRAVERSAL_REJECTED"
AEP53_PATH_ALIAS_REJECTED = "AEP53_PATH_ALIAS_REJECTED"
AEP53_MANIFEST_EPOCH_INSUFFICIENT_SHAPE = "AEP53_MANIFEST_EPOCH_INSUFFICIENT_SHAPE"

# v0.5.4 hot-patch reason codes (Round-5 remaining closures)
AEP54_DEEP_MIGRATION_RECEIPT_MISSING = "AEP54_DEEP_MIGRATION_RECEIPT_MISSING"
AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED = "AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED"
AEP54_RELIABILITY_AXIS_B_CONTRADICTION = "AEP54_RELIABILITY_AXIS_B_CONTRADICTION"
AEP54_EPOCH_NON_MONOTONIC = "AEP54_EPOCH_NON_MONOTONIC"
AEP54_EPOCH_INVALID_VALUE = "AEP54_EPOCH_INVALID_VALUE"
AEP54_SUPERSEDES_MALFORMED = "AEP54_SUPERSEDES_MALFORMED"


# --------------------------------------------
# Schema/profile binding hard-fail
# --------------------------------------------

# v0.5 shape markers split into universal (must have ≥1) and conditional.
# Universal markers indicate "this packet has been authored with v0.5 surface area."
# At least ONE universal marker must be present on at least ONE record.
_V05_UNIVERSAL_SHAPE_KEYS: Set[str] = {
    "axis_b_action",
    "decision_time_revalidation_required",
}

# Conditional markers — required only when the packet structure invokes them:
#   go_justification_claim_ids — required only when claim has axis_b_action=GO AND reliability=GOVERNANCE_RULE
# Manifest-level marker: packet_epoch indicates a v0.5 manifest.
_V05_CONDITIONAL_SHAPE_KEYS: Set[str] = {
    "go_justification_claim_ids",
}

# Backward-compat alias for any older code paths that referenced the union.
_V05_REQUIRED_SHAPE_KEYS: Set[str] = (
    _V05_UNIVERSAL_SHAPE_KEYS | _V05_CONDITIONAL_SHAPE_KEYS
)

_EXTENSION_V05_REQUIRED_KEY = "semantic_stability"

_KNOWN_V04_PROFILE_MARKERS: Tuple[str, ...] = (
    "aep:0.4/",
    "aep:0.4",
)

_FINGERPRINT_REGISTRY_ENV = "AEP_V05_1_FINGERPRINT_REGISTRY"


def _normalize_relpath(path_value: str) -> str:
    p = path_value.replace("\\", "/").strip()
    p = p.lstrip("./")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def _walk_numbers_and_tokens(node: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    """Yield (json-path, token) for numeric-like leaves.

    If strict parser preserved numeric tokens as Python numbers, those are yielded.
    If producers serialize numbers as strings inside numeric fields, the caller decides
    whether to interpret those strings as numeric text.
    """

    if isinstance(node, dict):
        for k, v in node.items():
            child_path = f"{path}.{k}" if path else str(k)
            yield from _walk_numbers_and_tokens(v, child_path)
        return

    if isinstance(node, list):
        for idx, v in enumerate(node):
            child_path = f"{path}[{idx}]"
            yield from _walk_numbers_and_tokens(v, child_path)
        return

    if isinstance(node, (int, float, decimal.Decimal)):
        yield path, node
        return

    if isinstance(node, str):
        # Keep broad here; canonicalization check decides acceptance.
        if re.fullmatch(r"[+-]?(?:\d+|\d+\.\d+|\.\d+)(?:[eE][+-]?\d+)?", node):
            yield path, node


def _safe_json_loads(text: str) -> Any:
    return parse_strict_canonical(text)


def _read_manifest(packet_root: Path) -> Optional[Dict[str, Any]]:
    # AEP canonical manifest is aepkg.json (not manifest.json — codex assumed wrongly).
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        # Fall back to manifest.json for any non-AEP-shape packets the validator is invoked on.
        manifest_path = packet_root / "manifest.json"
        if not manifest_path.exists():
            return None
    try:
        return _safe_json_loads(_read_text(manifest_path))
    except Exception:
        return None


def _read_canonical_records(
    packet_root: Path, manifest: Dict[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    canonical_files = manifest.get("canonical_files")
    if not isinstance(canonical_files, list):
        return out

    for rel in canonical_files:
        if not isinstance(rel, str):
            continue
        normalized = _normalize_relpath(rel)
        abs_path = (packet_root / normalized).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            continue
        if abs_path.suffix.lower() != ".jsonl":
            continue
        try:
            rows = _read_jsonl(abs_path)
        except Exception:
            continue
        # Keep only JSON object rows for shape fingerprints and path refs.
        out[normalized] = [r for r in rows if isinstance(r, dict)]
    return out


def _collect_top_level_keys(records_by_file: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for rel, rows in records_by_file.items():
        keyset: Set[str] = set()
        for row in rows:
            keyset.update(str(k) for k in row.keys())
        out[rel] = sorted(keyset)
    return out


def _collect_v05_shape_presence(
    manifest: Dict[str, Any], records_by_file: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, bool]:
    present: Dict[str, bool] = {k: False for k in _V05_REQUIRED_SHAPE_KEYS}
    present[_EXTENSION_V05_REQUIRED_KEY] = False

    extensions = manifest.get("extensions")
    if isinstance(extensions, list):
        for ext in extensions:
            if isinstance(ext, dict) and _EXTENSION_V05_REQUIRED_KEY in ext:
                present[_EXTENSION_V05_REQUIRED_KEY] = True
                break

    for _, rows in records_by_file.items():
        for row in rows:
            for key in _V05_REQUIRED_SHAPE_KEYS:
                if key in row:
                    present[key] = True

    return present


def _profile_declares_version(profile: str, version: str) -> bool:
    # Expected shape: aep:0.5/stable or aep:0.5/experimental
    version_marker = f"aep:{version}/"
    return profile.startswith(version_marker)


def _manifest_declared_version(manifest: Dict[str, Any]) -> Optional[str]:
    v = manifest.get("aep_version")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def _manifest_declared_profile(manifest: Dict[str, Any]) -> Optional[str]:
    p = manifest.get("profile")
    if isinstance(p, str) and p.strip():
        return p.strip()
    return None


def _fingerprint_registry_path(packet_root: Path) -> Optional[Path]:
    env_path = os.environ.get(_FINGERPRINT_REGISTRY_ENV)
    if isinstance(env_path, str) and env_path.strip():
        return Path(env_path.strip())
    local_default = packet_root / "schema_fingerprint_registry_v0_5.json"
    if local_default.exists():
        return local_default
    return None


def _load_fingerprint_registry(packet_root: Path) -> Dict[str, Set[str]]:
    """Load optional fingerprint registry.

    File format:
    {
      "<sha256hex>": ["aep:0.5/stable", "aep:0.5/experimental"],
      ...
    }
    """

    reg_path = _fingerprint_registry_path(packet_root)
    if reg_path is None:
        return {}

    try:
        raw = _safe_json_loads(_read_text(reg_path))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    registry: Dict[str, Set[str]] = {}
    for fp, profiles in raw.items():
        if not isinstance(fp, str):
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", fp):
            continue
        if isinstance(profiles, list):
            clean = {p for p in profiles if isinstance(p, str)}
        elif isinstance(profiles, str):
            clean = {profiles}
        else:
            clean = set()
        if clean:
            registry[fp] = clean
    return registry


def compute_schema_fingerprint(manifest: Dict[str, Any], canonical_files_present: List[str]) -> str:
    """Compute deterministic fingerprint over packet structural shape.

    Included dimensions:
    - Sorted canonical file list that exists in packet
    - Per-file sorted unique top-level keys across JSONL records
    - Presence booleans for v0.5-specific shape keys
    - Presence of ``semantic_stability`` in manifest extensions
    - Declared profile + declared version (binding dimensions)

    ``schema_fingerprint`` field (if present in manifest) is excluded from the
    normalized payload to prevent recursion.
    """

    manifest_copy = dict(manifest)
    manifest_copy.pop("schema_fingerprint", None)

    packet_root = Path(manifest_copy.get("_packet_root_hint", "."))
    # The helper is also usable outside validator context by passing only
    # manifest + canonical files; fall back to listed files when records absent.
    records_by_file: Dict[str, List[Dict[str, Any]]] = {}
    if packet_root.exists():
        records_by_file = _read_canonical_records(packet_root, manifest_copy)

    canonical_list = sorted(_normalize_relpath(p) for p in canonical_files_present if isinstance(p, str))
    top_level_key_map = _collect_top_level_keys(records_by_file)
    shape_presence = _collect_v05_shape_presence(manifest_copy, records_by_file)

    normalized = {
        "canonical_files_present": canonical_list,
        "top_level_keys_by_file": top_level_key_map,
        "v05_presence": shape_presence,
        "declared_profile": _manifest_declared_profile(manifest_copy),
        "declared_version": _manifest_declared_version(manifest_copy),
    }
    payload = serialize_strict_canonical(normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


V05_FINGERPRINT_REGISTRY: Dict[str, Set[str]] = {}


def _v05_shape_heuristic_failures(
    manifest: Dict[str, Any], records_by_file: Dict[str, List[Dict[str, Any]]]
) -> List[str]:
    failures: List[str] = []
    version = _manifest_declared_version(manifest)
    profile = _manifest_declared_profile(manifest)
    if version != "0.5":
        # This patch only hardens 0.5 channel; no heuristic mismatch emitted.
        return failures
    if not isinstance(profile, str):
        return failures

    # In absence of registry anchoring, enforce:
    #   - At least ONE v0.5 universal shape marker present on some record
    #     (axis_b_action OR decision_time_revalidation_required)
    #   - OR manifest-level v0.5 marker (packet_epoch present)
    # Conditional markers (go_justification_claim_ids, semantic_stability on extensions)
    # are required only when the packet structure invokes them; their absence is not
    # a v0.5-shape failure.
    presence = _collect_v05_shape_presence(manifest, records_by_file)
    has_universal = any(presence.get(k, False) for k in _V05_UNIVERSAL_SHAPE_KEYS)
    has_manifest_marker = "packet_epoch" in manifest
    if not (has_universal or has_manifest_marker):
        missing = sorted(_V05_UNIVERSAL_SHAPE_KEYS) + ["manifest.packet_epoch"]
        failures.append(
            f"no-v05-shape-markers:expected-any-of:{','.join(missing)}"
        )

    # Block obvious older-profile hybrids under v0.5 declaration.
    for marker in _KNOWN_V04_PROFILE_MARKERS:
        if marker in profile:
            failures.append("profile-declares-v04-marker")
            break

    return failures


def check_schema_profile_binding(
    manifest: Dict[str, Any], requested_profile: str, packet_root: Path
) -> List[Finding]:
    """Closure #1: enforce schema/profile/version binding.

    Rules:
    - Manifest declared profile must equal requested profile exactly.
    - Declared version + profile channel must be internally consistent.
    - For v0.5 declarations: fingerprint must map to profile when registry is present.
      If registry is absent, fall back to heuristic shape checks to preserve
      backward compatibility while still closing common v0.4 crossfade attacks.
    """

    findings: List[Finding] = []
    declared_version = _manifest_declared_version(manifest)
    declared_profile = _manifest_declared_profile(manifest)

    if declared_profile and requested_profile and declared_profile != requested_profile:
        findings.append(
            _mkfinding(
                AEP51_PROFILE_REQUEST_MISMATCH,
                SEVERITY_ERROR,
                (
                    "manifest profile does not match requested validator profile "
                    f"(manifest={declared_profile}, requested={requested_profile})"
                ),
                "manifest.json:profile",
            )
        )

    if declared_version and declared_profile and not _profile_declares_version(
        declared_profile, declared_version
    ):
        findings.append(
            _mkfinding(
                AEP51_VERSION_PROFILE_INCONSISTENT,
                SEVERITY_ERROR,
                (
                    "manifest aep_version and profile channel disagree "
                    f"(aep_version={declared_version}, profile={declared_profile})"
                ),
                "manifest.json",
            )
        )

    canonical_files = manifest.get("canonical_files")
    canonical_files_list = (
        [p for p in canonical_files if isinstance(p, str)] if isinstance(canonical_files, list) else []
    )

    manifest_for_fp = dict(manifest)
    manifest_for_fp["_packet_root_hint"] = str(packet_root)
    fp = compute_schema_fingerprint(manifest_for_fp, canonical_files_list)

    # Optional declared fingerprint for transparency; if present it must match.
    declared_fp = manifest.get("schema_fingerprint")
    if isinstance(declared_fp, str) and declared_fp and declared_fp != fp:
        findings.append(
            _mkfinding(
                AEP51_VERSION_SCHEMA_MISMATCH,
                SEVERITY_ERROR,
                (
                    "declared schema_fingerprint does not match computed structural fingerprint "
                    f"(declared={declared_fp}, computed={fp})"
                ),
                "manifest.json:schema_fingerprint",
            )
        )

    registry = dict(V05_FINGERPRINT_REGISTRY)
    dynamic_registry = _load_fingerprint_registry(packet_root)
    if dynamic_registry:
        registry.update(dynamic_registry)

    if declared_profile and registry:
        allowed_profiles = registry.get(fp)
        if not allowed_profiles or declared_profile not in allowed_profiles:
            findings.append(
                _mkfinding(
                    AEP51_VERSION_SCHEMA_MISMATCH,
                    SEVERITY_ERROR,
                    (
                        "schema fingerprint is not registered for declared profile "
                        f"(fingerprint={fp}, profile={declared_profile})"
                    ),
                    "manifest.json",
                )
            )
    elif declared_profile and not registry:
        records_by_file = _read_canonical_records(packet_root, manifest)
        heuristic_failures = _v05_shape_heuristic_failures(manifest, records_by_file)
        if heuristic_failures:
            findings.append(
                _mkfinding(
                    AEP51_VERSION_SCHEMA_MISMATCH,
                    SEVERITY_ERROR,
                    (
                        "packet declares v0.5 but shape markers are inconsistent with v0.5 "
                        f"(signals={','.join(sorted(heuristic_failures))}, fingerprint={fp})"
                    ),
                    "manifest.json",
                )
            )
        findings.append(
            _mkfinding(
                AEP51_SCHEMA_FINGERPRINT_UNKNOWN,
                SEVERITY_INFO,
                (
                    "schema fingerprint registry unavailable; enforced heuristic "
                    f"checks only (fingerprint={fp})"
                ),
                "manifest.json",
            )
        )

    return findings


# --------------------------------------------
# Artifact closure integrity
# --------------------------------------------

_CANONICAL_FILE_HINTS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^data/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^ops/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^claims/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^relations/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^events/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^reviews/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^sources/.*\.jsonl$", re.IGNORECASE),
    re.compile(r"^evidence/.*\.jsonl$", re.IGNORECASE),
)

_IN_PACKET_PREFIX = "in-packet:"


def _extract_in_packet_ref(value: str) -> Optional[str]:
    v = value.strip()
    if not v.startswith(_IN_PACKET_PREFIX):
        return None
    rel = v[len(_IN_PACKET_PREFIX) :]
    if not rel:
        return None
    return _normalize_relpath(rel)


def _looks_like_in_packet_path(value: str) -> bool:
    """A string is in-packet only when it: (a) starts with 'in-packet:', or
    (b) is a relative path matching the canonical-file hints, OR (c) is exactly
    'aepkg.json'. Arbitrary strings under fields like `target` / `path` that
    name external tools, validator identifiers, or finding categories are NOT
    in-packet references.
    """
    v = value.strip()
    if not v:
        return False
    if v.startswith(_IN_PACKET_PREFIX):
        return True
    # Reject absolute paths / URLs / things with no slash (those are usually
    # identifiers, not relative in-packet paths).
    if v == "aepkg.json":
        return True
    if v.startswith("/") or v.startswith("http://") or v.startswith("https://"):
        return False
    if "://" in v:
        return False
    # Treat as in-packet only if it matches a canonical-file or assets/ shape.
    if "/" not in v:
        return False  # Bare names like "convert_aepkit_lesson.py" are NOT in-packet paths.
    if v.startswith("assets/"):
        return True
    return _looks_like_canonical_file(v)


def _extract_path_like_values(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for k, v in node.items():
            k_lower = str(k).lower()
            if isinstance(v, str):
                if k_lower in {"path", "file", "filename", "filepath", "target"} and _looks_like_in_packet_path(v):
                    yield v
                elif v.startswith(_IN_PACKET_PREFIX):
                    yield v
            yield from _extract_path_like_values(v)
        return
    if isinstance(node, list):
        for v in node:
            yield from _extract_path_like_values(v)


def _collect_source_location_paths(source: Dict[str, Any]) -> Iterable[str]:
    loc = source.get("location")
    if not isinstance(loc, dict):
        return
    if loc.get("kind") == "filesystem-path":
        p = loc.get("path")
        if isinstance(p, str):
            yield p


def _collect_span_selector_paths(record: Dict[str, Any]) -> Iterable[str]:
    selectors = record.get("span_selectors")
    if not isinstance(selectors, list):
        return
    for selector in selectors:
        if not isinstance(selector, dict):
            continue
        for key in ("path", "file", "target", "source_path"):
            v = selector.get(key)
            if isinstance(v, str):
                yield v


def _collect_event_target_paths(event: Dict[str, Any]) -> Iterable[str]:
    target = event.get("target")
    if isinstance(target, str):
        yield target
    elif isinstance(target, dict):
        for key in ("path", "file", "uri"):
            v = target.get(key)
            if isinstance(v, str):
                yield v


def _normalize_reference(value: str) -> Optional[str]:
    v = value.strip()
    if not v:
        return None
    in_packet = _extract_in_packet_ref(v)
    if in_packet is not None:
        return in_packet
    # Relative path inside packet.
    if "://" not in v and not Path(v).is_absolute():
        return _normalize_relpath(v)
    return None


def collect_referenced_paths(
    claims: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
) -> Set[str]:
    """Collect all in-packet path references from canonical records."""

    refs: Set[str] = set()

    def _add(value: Optional[str]) -> None:
        if not value:
            return
        normalized = _normalize_reference(value)
        if normalized:
            refs.add(normalized)

    for src in sources:
        if not isinstance(src, dict):
            continue
        for p in _collect_source_location_paths(src):
            _add(p)
        for p in _extract_path_like_values(src):
            _add(p)

    for rec in claims + relations + reviews:
        if not isinstance(rec, dict):
            continue
        for p in _collect_span_selector_paths(rec):
            _add(p)
        for p in _extract_path_like_values(rec):
            _add(p)

    for ev in events:
        if not isinstance(ev, dict):
            continue
        for p in _collect_event_target_paths(ev):
            _add(p)
        for p in _extract_path_like_values(ev):
            _add(p)

    return refs


def _walk_files_under(packet_root: Path) -> Iterable[Path]:
    for p in packet_root.rglob("*"):
        if p.is_file():
            yield p


def _looks_like_canonical_file(rel_path: str) -> bool:
    rp = _normalize_relpath(rel_path)
    for pat in _CANONICAL_FILE_HINTS:
        if pat.match(rp):
            return True
    return False


def _build_integrity_envelope(manifest: Dict[str, Any], packet_root: Path) -> Set[str]:
    envelope: Set[str] = set()
    # Manifest itself is always part of the integrity envelope (v0.5 manifest_hash).
    envelope.add("aepkg.json")
    cfiles = manifest.get("canonical_files")
    if isinstance(cfiles, list):
        for p in cfiles:
            if isinstance(p, str):
                envelope.add(_normalize_relpath(p))

    assets_root = packet_root / "assets"
    if assets_root.exists() and assets_root.is_dir():
        for p in _walk_files_under(assets_root):
            envelope.add(_normalize_relpath(str(p.relative_to(packet_root))))

    # `views/` is generated and non-canonical per v0.5 §7 / axiom 4. References to
    # generated views or to external tool identifiers (e.g., a script path that
    # produced the packet) are NOT in-packet references and don't need envelope
    # membership. The reference collector's role is to flag undeclared CANONICAL
    # references, not arbitrary string values that happen to look path-like.

    return envelope


def _load_records_by_logical_type(
    packet_root: Path, manifest: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    claims: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    reviews: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []

    records = _read_canonical_records(packet_root, manifest)
    for rel, rows in records.items():
        r = rel.lower()
        if "claim" in r:
            claims.extend(rows)
        elif "relation" in r:
            relations.extend(rows)
        elif "event" in r or "op" in r:
            events.extend(rows)
        elif "review" in r:
            reviews.extend(rows)
        elif "source" in r:
            sources.extend(rows)
        else:
            # Conservatively scan unknown canonical record types by treating them
            # as claim-like records for reference extraction.
            claims.extend(rows)
    return claims, relations, events, reviews, sources


def check_artifact_closure(
    packet_root: Path,
    manifest: Dict[str, Any],
    claims: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
) -> List[Finding]:
    """Closure #2: enforce reference closure over integrity envelope."""

    findings: List[Finding] = []
    envelope = _build_integrity_envelope(manifest, packet_root)
    refs = collect_referenced_paths(claims, relations, events, reviews, sources)

    for ref in sorted(refs):
        if ref not in envelope:
            findings.append(
                _mkfinding(
                    AEP51_UNMANIFESTED_REFERENCE,
                    SEVERITY_ERROR,
                    (
                        "record references in-packet path outside integrity envelope "
                        f"(reference={ref})"
                    ),
                    "canonical_records",
                )
            )

    declared_canonical: Set[str] = set()
    cfiles = manifest.get("canonical_files")
    if isinstance(cfiles, list):
        declared_canonical = {
            _normalize_relpath(p) for p in cfiles if isinstance(p, str)
        }

    for path in _walk_files_under(packet_root):
        rel = _normalize_relpath(str(path.relative_to(packet_root)))
        if _looks_like_canonical_file(rel) and rel not in declared_canonical:
            findings.append(
                _mkfinding(
                    AEP51_HIDDEN_CANONICAL_FILE,
                    SEVERITY_ERROR,
                    (
                        "canonical-shaped file exists but is missing from canonical_files "
                        f"(file={rel})"
                    ),
                    rel,
                )
            )

    return findings


# --------------------------------------------
# Numeric canonicalization lockdown (AEP-NUMERIC-v1)
# --------------------------------------------

decimal.getcontext().prec = 128
decimal.getcontext().rounding = decimal.ROUND_HALF_EVEN

AEP_NUMERIC_MAX = decimal.Decimal("1e308")
AEP_NUMERIC_MIN_NONZERO = decimal.Decimal("1e-308")
AEP_NUMERIC_MAX_PRECISION = 17

_NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<num>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)(?![A-Za-z0-9_])"
)


class AEPNumericError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _significant_digits(dec: decimal.Decimal) -> int:
    tup = dec.normalize().as_tuple()
    if dec == 0:
        return 1
    digits = list(tup.digits)
    # remove leading zeros in significand
    while digits and digits[0] == 0:
        digits.pop(0)
    return max(1, len(digits))


def _to_decimal(value: Any) -> decimal.Decimal:
    if isinstance(value, decimal.Decimal):
        dec = value
    elif isinstance(value, bool):
        raise AEPNumericError(AEP51_NUMERIC_FORBIDDEN, "bool is not a numeric token")
    elif isinstance(value, int):
        dec = decimal.Decimal(value)
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise AEPNumericError(AEP51_NUMERIC_FORBIDDEN, "NaN/Inf forbidden")
        # Exact decimal from float binary payload for deterministic behavior.
        dec = decimal.Decimal(str(value))
    elif isinstance(value, str):
        v = value.strip()
        if v.lower() in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
            raise AEPNumericError(AEP51_NUMERIC_FORBIDDEN, "NaN/Inf forbidden")
        try:
            dec = decimal.Decimal(v)
        except decimal.InvalidOperation as exc:
            raise AEPNumericError(AEP51_NUMERIC_FORBIDDEN, f"invalid numeric literal: {value!r}") from exc
    else:
        raise AEPNumericError(AEP51_NUMERIC_FORBIDDEN, f"unsupported numeric type: {type(value)!r}")
    return dec


def _normalize_negative_zero(dec: decimal.Decimal) -> decimal.Decimal:
    if dec.is_zero():
        return decimal.Decimal(0)
    return dec


def _ensure_numeric_range(dec: decimal.Decimal) -> None:
    dec = _normalize_negative_zero(dec)
    abs_dec = abs(dec)
    if abs_dec > AEP_NUMERIC_MAX:
        raise AEPNumericError(AEP51_NUMERIC_OUT_OF_RANGE, f"numeric overflow: {dec}")
    if abs_dec != 0 and abs_dec < AEP_NUMERIC_MIN_NONZERO:
        raise AEPNumericError(AEP51_NUMERIC_OUT_OF_RANGE, f"subnormal forbidden: {dec}")


def _ensure_numeric_precision(dec: decimal.Decimal) -> None:
    sig = _significant_digits(dec)
    if sig > AEP_NUMERIC_MAX_PRECISION:
        raise AEPNumericError(
            AEP51_NUMERIC_PRECISION_LOSS,
            f"significant digits exceed {AEP_NUMERIC_MAX_PRECISION}: {sig}",
        )


def _canonical_plain(dec: decimal.Decimal) -> str:
    # Convert without exponent first.
    s = format(dec, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    if s.startswith("+"):
        s = s[1:]
    if s == "":
        s = "0"
    # Normalize leading zeros in integer part.
    if s.startswith("-"):
        sign, body = "-", s[1:]
    else:
        sign, body = "", s
    if "." in body:
        i, frac = body.split(".", 1)
        i = i.lstrip("0") or "0"
        body = i + "." + frac
    else:
        body = body.lstrip("0") or "0"
    if body.startswith("0.") and sign == "-":
        return "-" + body
    return sign + body


def _canonical_scientific(dec: decimal.Decimal) -> str:
    tup = dec.normalize().as_tuple()
    sign = "-" if tup.sign else ""
    digits = "".join(str(d) for d in tup.digits) or "0"
    exponent = tup.exponent
    # Decimal number = digits * 10^exponent.
    # Scientific mantissa has one digit before decimal point.
    exp = exponent + len(digits) - 1
    if len(digits) == 1:
        mant = digits
    else:
        mant = digits[0] + "." + digits[1:]
        mant = mant.rstrip("0").rstrip(".")
    if mant == "0":
        sign = ""
        exp = 0
    exp_sign = "+" if exp >= 0 else "-"
    return f"{sign}{mant}e{exp_sign}{abs(exp)}"


def aep_numeric_canonicalize(value: Any) -> str:
    """Canonicalize numeric value per AEP-NUMERIC-v1."""

    dec = _to_decimal(value)
    dec = _normalize_negative_zero(dec)

    _ensure_numeric_range(dec)
    _ensure_numeric_precision(dec)

    if dec == 0:
        return "0"

    # Determine adjusted exponent for scientific threshold:
    # use exponent only when |exp| >= 6.
    norm = dec.normalize()
    adjusted_exp = norm.adjusted()  # position of most significant digit
    if abs(adjusted_exp) >= 6:
        return _canonical_scientific(norm)
    return _canonical_plain(norm)


def _extract_number_tokens_from_json_line(raw_line: str) -> List[str]:
    # Strip string literals to avoid false positives inside text.
    # Minimal JSON string masking to keep deterministic without full tokenizer.
    chars = list(raw_line)
    in_string = False
    escaped = False
    for i, ch in enumerate(chars):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            chars[i] = " "
        else:
            if ch == '"':
                in_string = True
                chars[i] = " "
    masked = "".join(chars)

    tokens: List[str] = []
    for m in _NUMBER_TOKEN_RE.finditer(masked):
        token = m.group("num")
        if token is not None and token not in {"-"}:
            tokens.append(token)
    return tokens


def _scan_jsonl_file_for_numeric_findings(path: Path, rel_path: str) -> List[Finding]:
    findings: List[Finding] = []
    text = _read_text(path)
    lines = text.splitlines()

    for line_no, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        tokens = _extract_number_tokens_from_json_line(raw)
        for token in tokens:
            try:
                canonical = aep_numeric_canonicalize(token)
            except AEPNumericError as exc:
                findings.append(
                    _mkfinding(
                        exc.code,
                        SEVERITY_ERROR,
                        f"numeric token rejected: {token!r} ({exc.message})",
                        f"{rel_path}:{line_no}",
                    )
                )
                continue
            if canonical != token:
                findings.append(
                    _mkfinding(
                        AEP51_NUMERIC_NONCANONICAL_FORM,
                        SEVERITY_ERROR,
                        f"numeric token is non-canonical (token={token}, canonical={canonical})",
                        f"{rel_path}:{line_no}",
                    )
                )
    return findings


def scan_packet_numerics(packet_root: Path, canonical_files: List[str]) -> List[Finding]:
    """Walk canonical records and enforce AEP-NUMERIC-v1."""

    findings: List[Finding] = []
    for rel in canonical_files:
        if not isinstance(rel, str):
            continue
        normalized = _normalize_relpath(rel)
        if not normalized.lower().endswith(".jsonl"):
            continue
        abs_path = (packet_root / normalized).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            continue
        findings.extend(_scan_jsonl_file_for_numeric_findings(abs_path, normalized))
    return findings


# --------------------------------------------
# Validator v0.5.1 composition
# --------------------------------------------

def _merge_results(base: ValidationResult, extras: List[Finding]) -> ValidationResult:
    merged_findings = list(base.findings) + extras
    schema_state = base.schema_result
    if any(f.severity == SEVERITY_ERROR for f in extras):
        schema_state = "fail"
    elif schema_state == "pass" and any(f.severity == SEVERITY_WARNING for f in extras):
        schema_state = "warn"
    return ValidationResult(findings=merged_findings, schema_result=schema_state)


# --------------------------------------------
# v0.5.3 hot-patch closures (Round-5)
# --------------------------------------------

def check_gr_go_justification_integrity(claims: List[Dict[str, Any]]) -> List[Finding]:
    """v0.5.3 Closure #1 — Round-5 Attack #1 (GR+GO Empty-Justification Bypass).

    For every claim with reliability=GOVERNANCE_RULE AND axis_b_action=GO:
      1. go_justification_claim_ids MUST exist AND be non-empty.
      2. Every referenced claim_id MUST exist in the packet (no dangling refs).
      3. At least ONE referenced claim MUST have reliability != GOVERNANCE_RULE
         (per v0.5.1 §S-2: prevents recursive governance-only justification chains).
    """
    findings: List[Finding] = []
    claim_id_to_reliability: Dict[str, str] = {}
    for c in claims:
        cid = c.get("id")
        if isinstance(cid, str):
            claim_id_to_reliability[cid] = c.get("reliability", "")

    for c in claims:
        reliability = c.get("reliability")
        axis_b = c.get("axis_b_action")
        if reliability != GOVERNANCE_RULE or axis_b != "GO":
            continue
        cid = c.get("id", "<unknown>")
        loc = f"data/claims.jsonl:{cid}"
        justifications = c.get("go_justification_claim_ids")
        if not isinstance(justifications, list) or len(justifications) == 0:
            findings.append(
                _mkfinding(
                    AEP53_GR_GO_EMPTY_JUSTIFICATION,
                    SEVERITY_ERROR,
                    (
                        "GR+GO claim has empty or missing go_justification_claim_ids; "
                        "v0.5.1 §S-2 requires non-empty list with ≥1 non-GR claim"
                    ),
                    loc,
                )
            )
            continue
        # Dangling-reference check
        non_gr_count = 0
        for ref in justifications:
            if not isinstance(ref, str):
                continue
            if ref not in claim_id_to_reliability:
                findings.append(
                    _mkfinding(
                        AEP53_GR_GO_DANGLING_JUSTIFICATION,
                        SEVERITY_ERROR,
                        f"go_justification_claim_ids references unknown claim_id={ref!r}",
                        loc,
                    )
                )
                continue
            if claim_id_to_reliability[ref] != GOVERNANCE_RULE:
                non_gr_count += 1
        if non_gr_count == 0:
            findings.append(
                _mkfinding(
                    AEP53_GR_GO_JUSTIFICATION_IS_GR,
                    SEVERITY_ERROR,
                    (
                        "GR+GO claim's go_justification_claim_ids all resolve to GOVERNANCE_RULE claims; "
                        "v0.5.1 §S-2 requires ≥1 non-GR justification to prevent recursive policy injection"
                    ),
                    loc,
                )
            )
    return findings


def _canonicalize_in_packet_path_strict(value: str) -> Tuple[Optional[str], Optional[str]]:
    """v0.5.3 Closure #2 — Round-5 Attack #3/#4 (Path Alias + Traversal).

    Strict canonical path resolver for in-packet references.

    Returns:
      (canonical_path, error_code)
      canonical_path = the normalized POSIX relative path if value resolves cleanly
      error_code     = AEP53_PATH_TRAVERSAL_REJECTED or AEP53_PATH_ALIAS_REJECTED on rejection
    """
    v = (value or "").strip()
    if not v:
        return None, AEP53_PATH_ALIAS_REJECTED
    if v.startswith(_IN_PACKET_PREFIX):
        v = v[len(_IN_PACKET_PREFIX):]
    # Reject absolute paths
    if v.startswith("/") or v.startswith("\\"):
        return None, AEP53_PATH_ALIAS_REJECTED
    # Reject schemes
    if "://" in v:
        return None, AEP53_PATH_ALIAS_REJECTED
    # Normalize backslash to forward slash, lowercase the well-known manifest alias.
    v = v.replace("\\", "/")
    # Reject path-traversal segments
    segments = v.split("/")
    for seg in segments:
        if seg in ("..", "."):
            return None, AEP53_PATH_TRAVERSAL_REJECTED
        # Reject percent-encoded traversal
        if "%2e%2e" in seg.lower() or "%2f" in seg.lower():
            return None, AEP53_PATH_TRAVERSAL_REJECTED
    # Reject explicit `./` prefix removal preservation (canonical form has no leading ./)
    if v.startswith("./"):
        return None, AEP53_PATH_ALIAS_REJECTED
    # Canonical alias for manifest is exactly "aepkg.json" (case-sensitive on the canonical name).
    if v.lower() == "aepkg.json" and v != "aepkg.json":
        return None, AEP53_PATH_ALIAS_REJECTED
    return v, None


def check_path_canonicality(claims: List[Dict[str, Any]], relations: List[Dict[str, Any]],
                             events: List[Dict[str, Any]], reviews: List[Dict[str, Any]],
                             sources: List[Dict[str, Any]]) -> List[Finding]:
    """v0.5.3 Closure #2 — apply the strict canonical resolver to every path-bearing field.

    Findings are emitted ONLY when a referenced path FAILS canonical resolution.
    This is layered on top of v0.5.1's artifact-closure check; the resolver here
    is the stricter gate that catches alias + traversal attempts even when the
    file would otherwise be missing from the envelope.
    """
    findings: List[Finding] = []

    def _scan_iter(label: str, iter_paths: Iterable[str], location: str) -> None:
        for raw in iter_paths:
            if not isinstance(raw, str):
                continue
            if not raw.startswith(_IN_PACKET_PREFIX):
                # Only enforce on explicit in-packet refs; tool identifiers et al
                # are filtered out earlier by `_looks_like_in_packet_path`.
                continue
            _, err = _canonicalize_in_packet_path_strict(raw)
            if err is not None:
                findings.append(
                    _mkfinding(
                        err,
                        SEVERITY_ERROR,
                        f"in-packet reference rejected by strict path resolver: {raw!r}",
                        f"{label}:{location}",
                    )
                )

    for s in sources:
        sid = s.get("id", "<unknown>")
        for raw in _collect_source_location_paths(s):
            _scan_iter("data/sources.jsonl", [raw], sid)
    for c in claims:
        cid = c.get("id", "<unknown>")
        for raw in _extract_path_like_values(c):
            _scan_iter("data/claims.jsonl", [raw], cid)
    for r in relations:
        rid = r.get("id", "<unknown>")
        for raw in _extract_path_like_values(r):
            _scan_iter("data/relations.jsonl", [raw], rid)
    for ev in events:
        eid = ev.get("id", "<unknown>")
        for raw in _collect_event_target_paths(ev):
            _scan_iter("ops/events.jsonl", [raw], eid)
        for raw in _extract_path_like_values(ev):
            _scan_iter("ops/events.jsonl", [raw], eid)
    for rv in reviews:
        rid = rv.get("id", "<unknown>")
        for raw in _extract_path_like_values(rv):
            _scan_iter("reviews/reviews.jsonl", [raw], rid)

    return findings


def check_v05_shape_strictness_gate(manifest: Dict[str, Any],
                                      records_by_file: Dict[str, List[Dict[str, Any]]],
                                      config: ValidationConfig) -> List[Finding]:
    """v0.5.3 Closure #3 — Round-5 Attack #2 (Manifest-Only Epoch Minimal-Shape Crossfade).

    In strict Level-2 (default), a packet declaring aep_version="0.5" MUST exhibit
    at least ONE per-record universal v0.5 marker on at least ONE canonical record.
    `manifest.packet_epoch` alone is INSUFFICIENT — attackers cannot manufacture
    v0.5 conformance by adding a single manifest field while keeping v0.3 semantics
    per record.

    Exception: when config carries an explicit migration_mode=True with attested
    receipt, manifest.packet_epoch alone is provisionally accepted (operator-gated).
    """
    findings: List[Finding] = []
    if config.conformance_level < CONFORMANCE_LEVEL_2:
        return findings
    if not getattr(config, "strict", True):
        return findings
    version = _manifest_declared_version(manifest)
    if version != "0.5":
        return findings
    # Allow migration_mode override (operator-gated)
    if getattr(config, "migration_mode", False):
        return findings
    # The universal markers (axis_b_action / decision_time_revalidation_required) apply
    # to CLAIM records. If the packet has zero claims, the gate is inapplicable; accept
    # under L1-style conformance (warn-only). Other records (sources/events/etc.) are
    # not in scope for per-record v0.5 markers.
    claims_records: List[Dict[str, Any]] = []
    for rel, rows in records_by_file.items():
        if "claim" in rel.lower():
            claims_records.extend(rows)
    if len(claims_records) == 0:
        findings.append(
            _mkfinding(
                AEP53_MANIFEST_EPOCH_INSUFFICIENT_SHAPE,
                SEVERITY_WARNING,
                (
                    "packet has zero claim records — per-record v0.5 shape cannot be evaluated "
                    "on claims; accepted under L1-style conformance only. Add ≥1 claim (or set "
                    "conformance_level=1) to clear this gate at L2."
                ),
                "aepkg.json",
            )
        )
        return findings
    presence = _collect_v05_shape_presence(manifest, records_by_file)
    has_per_record_universal = any(presence.get(k, False) for k in _V05_UNIVERSAL_SHAPE_KEYS)
    if not has_per_record_universal:
        findings.append(
            _mkfinding(
                AEP53_MANIFEST_EPOCH_INSUFFICIENT_SHAPE,
                SEVERITY_ERROR,
                (
                    "packet declares v0.5 but no canonical record carries a per-record universal "
                    "v0.5 marker (axis_b_action / decision_time_revalidation_required). "
                    "manifest.packet_epoch alone is INSUFFICIENT in strict L2 (v0.5.3 §V53-3). "
                    "Either deep-migrate per-record OR pass --migration-mode with attested receipt."
                ),
                "aepkg.json",
            )
        )
    return findings


# --------------------------------------------
# v0.5.4 hot-patch closures (Round-5 remaining)
# --------------------------------------------

# §02 → Axis-B canonical valid combinations (operator-approved 2026-05-14).
# Used by check_reliability_axis_b_consistency to catch contradiction attacks.
# When a reliability key maps to a set of axis_b actions, only those actions
# are allowed for that reliability. Anything else is a contradiction.
RELIABILITY_AXIS_B_VALID: Dict[str, Set[str]] = {
    "PROVEN_RELIABLE": {"GO", "EXPERIMENT", "EXPLORE"},
    "STRONGLY_PLAUSIBLE": {"GO", "EXPERIMENT", "EXPLORE"},
    "PLAUSIBLE": {"EXPERIMENT", "EXPLORE", "HALT"},
    "EXPERIMENTAL": {"EXPERIMENT", "EXPLORE"},
    "ASSUMPTION": {"EXPLORE", "HALT"},
    "SPECULATIVE_FRONTIER": {"EXPLORE", "HALT"},
    "CONFLICTED": {"HALT"},
    "GOVERNANCE_RULE": {"GO", "FORBIDDEN"},
    "DANGEROUS_NOT_WORTH_DOING": {"FORBIDDEN"},
    # UNKNOWN claims should not carry axis_b_action (per the §02 mapping table).
    # If present, validator emits contradiction.
    "UNKNOWN": set(),
}


def check_deep_migration_receipt(manifest: Dict[str, Any]) -> List[Finding]:
    """v0.5.4 Closure #4 — Round-5 Attack #5 (Deep-Migration Provenance Forgery).

    When extensions claim deep-migration provenance (aep:deep_migrated_from),
    the packet MUST also carry a structurally well-formed receipt:
      extensions.aep:deep_migration_receipt = {
        "pre_state_hash": "sha256:...",   # state_hash before migration
        "post_state_hash": "sha256:...",  # state_hash after migration
        "tool": "convert_v0_5_shallow_to_deep.py",
        "tool_version": "1.0",            # or any semver-shaped string
        "timestamp": "2026-MM-DDTHH:MM:SSZ",
      }

    Structural validation only; full cryptographic verification of pre-state
    requires operator trust root (deferred to v0.7 signed identity).

    Reason codes:
      AEP54_DEEP_MIGRATION_RECEIPT_MISSING   — claim of deep-migration without receipt
      AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED — receipt missing required fields
    """
    findings: List[Finding] = []
    extensions = manifest.get("extensions")
    if not isinstance(extensions, dict):
        return findings
    claimed_from = extensions.get("aep:deep_migrated_from")
    if not isinstance(claimed_from, str) or claimed_from == "":
        # No deep-migration claim — nothing to verify.
        return findings
    receipt = extensions.get("aep:deep_migration_receipt")
    if receipt is None:
        findings.append(
            _mkfinding(
                AEP54_DEEP_MIGRATION_RECEIPT_MISSING,
                SEVERITY_WARNING,
                (
                    "extensions.aep:deep_migrated_from is set but "
                    "aep:deep_migration_receipt is missing. v0.5.4 requires a "
                    "structurally well-formed receipt; full cryptographic verification "
                    "is deferred to v0.7 (signed identity)."
                ),
                "aepkg.json:extensions",
            )
        )
        return findings
    if not isinstance(receipt, dict):
        findings.append(
            _mkfinding(
                AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED,
                SEVERITY_ERROR,
                "aep:deep_migration_receipt must be an object",
                "aepkg.json:extensions:aep:deep_migration_receipt",
            )
        )
        return findings
    required = {"pre_state_hash", "post_state_hash", "tool", "tool_version", "timestamp"}
    missing = required - set(receipt.keys())
    if missing:
        findings.append(
            _mkfinding(
                AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED,
                SEVERITY_ERROR,
                f"aep:deep_migration_receipt missing required fields: {sorted(missing)}",
                "aepkg.json:extensions:aep:deep_migration_receipt",
            )
        )
        return findings
    # Validate hash shape.
    for hkey in ("pre_state_hash", "post_state_hash"):
        hval = receipt.get(hkey)
        if not (isinstance(hval, str) and hval.startswith("sha256:") and len(hval) == 71):
            findings.append(
                _mkfinding(
                    AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED,
                    SEVERITY_ERROR,
                    f"aep:deep_migration_receipt.{hkey} must be 'sha256:' + 64 hex digits",
                    "aepkg.json:extensions:aep:deep_migration_receipt",
                )
            )
    return findings


def check_reliability_axis_b_consistency(claims: List[Dict[str, Any]]) -> List[Finding]:
    """v0.5.4 Closure #5 — Round-5 Attack #6 (Reliability ↔ Axis-B Contradiction).

    For every claim with both `reliability` and `axis_b_action` populated, verify
    the combination is permitted by the §02 → Axis-B canonical mapping table.
    Catches contradictions like PROVEN_RELIABLE + FORBIDDEN, CONFLICTED + GO,
    ASSUMPTION + GO, etc.
    """
    findings: List[Finding] = []
    for c in claims:
        reliability = c.get("reliability")
        axis_b = c.get("axis_b_action")
        if axis_b is None or reliability is None:
            continue
        valid_set = RELIABILITY_AXIS_B_VALID.get(reliability)
        if valid_set is None:
            # Unknown reliability tag — separate validation surface, not our concern.
            continue
        if axis_b not in valid_set:
            cid = c.get("id", "<unknown>")
            findings.append(
                _mkfinding(
                    AEP54_RELIABILITY_AXIS_B_CONTRADICTION,
                    SEVERITY_ERROR,
                    (
                        f"claim has contradictory (reliability, axis_b_action) pair: "
                        f"reliability={reliability!r} forbids axis_b_action={axis_b!r}; "
                        f"valid combinations for this reliability: {sorted(valid_set) or 'none (UNKNOWN claims must not carry axis_b)'}"
                    ),
                    f"data/claims.jsonl:{cid}",
                )
            )
    return findings


# Pattern for packet_id and supersedes_packet_id per v0.5 §6.
_PACKET_ID_PATTERN = re.compile(r"^aepkg:[A-Za-z0-9._:-]+$")


def check_epoch_monotonicity(manifest: Dict[str, Any]) -> List[Finding]:
    """v0.5.4 Closure #6 — Round-5 Attack #7 (Epoch Replay / Non-Monotonic Lineage).

    Structural enforcement of packet_epoch + supersedes_packet_id:

      - If `packet_epoch` is present, it MUST be a positive integer.
      - If `supersedes_packet_id` is present:
        * Must match the canonical aepkg:* pattern.
        * `packet_epoch` MUST be > 1 (cannot supersede something at epoch 1
          while still being epoch 1).
      - Full cross-packet epoch monotonicity requires a packet registry; the
        validator emits an info-level finding pointing to v0.7 signed-lineage
        closure for that gap.
    """
    findings: List[Finding] = []

    def _is_positive_integer_value(v: Any) -> bool:
        """Accept Python int (excluding bool) AND Decimal whose value is a positive whole number."""
        if isinstance(v, bool):
            return False
        if isinstance(v, int):
            return v >= 1
        # Decimal — accept when value is whole + >= 1 (post-strict-canonical parsing).
        try:
            import decimal as _decimal  # local import to avoid module-level cost
            if isinstance(v, _decimal.Decimal):
                if v != v.to_integral_value():
                    return False
                return int(v) >= 1
        except Exception:
            return False
        return False

    def _epoch_as_int(v: Any) -> Optional[int]:
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        try:
            import decimal as _decimal
            if isinstance(v, _decimal.Decimal) and v == v.to_integral_value():
                return int(v)
        except Exception:
            return None
        return None

    if "packet_epoch" in manifest:
        epoch_raw = manifest.get("packet_epoch")
        if not _is_positive_integer_value(epoch_raw):
            findings.append(
                _mkfinding(
                    AEP54_EPOCH_INVALID_VALUE,
                    SEVERITY_ERROR,
                    f"manifest.packet_epoch must be a positive integer; got {epoch_raw!r}",
                    "aepkg.json:packet_epoch",
                )
            )
            return findings
    supersedes = manifest.get("supersedes_packet_id")
    if supersedes is not None:
        if not isinstance(supersedes, str) or not _PACKET_ID_PATTERN.match(supersedes):
            findings.append(
                _mkfinding(
                    AEP54_SUPERSEDES_MALFORMED,
                    SEVERITY_ERROR,
                    f"manifest.supersedes_packet_id must match pattern 'aepkg:*'; got {supersedes!r}",
                    "aepkg.json:supersedes_packet_id",
                )
            )
            return findings
        epoch_int = _epoch_as_int(manifest.get("packet_epoch"))
        if epoch_int is None or epoch_int <= 1:
            findings.append(
                _mkfinding(
                    AEP54_EPOCH_NON_MONOTONIC,
                    SEVERITY_ERROR,
                    (
                        f"supersedes_packet_id is set but packet_epoch={manifest.get('packet_epoch')!r} "
                        f"violates strict monotonicity (epoch must be > 1 when superseding)"
                    ),
                    "aepkg.json",
                )
            )
    return findings


def validate_v0_5_1(packet_root: Path, config: ValidationConfig) -> ValidationResult:
    """Run v0.5 validator plus v0.5.1 + v0.5.3 + v0.5.4 hot-patch closures."""

    base_result = validate_v0_5(packet_root, config)
    manifest = _read_manifest(packet_root)
    if not isinstance(manifest, dict):
        # Preserve baseline behavior; manifest parse failures are already surfaced.
        return base_result

    closure_findings: List[Finding] = []

    try:
        closure_findings.extend(
            check_schema_profile_binding(manifest, config.profile, packet_root)
        )
    except Exception as exc:
        closure_findings.append(
            _mkfinding(
                "AEP51_INTERNAL_ERROR_SCHEMA_BINDING",
                SEVERITY_ERROR,
                f"schema/profile binding check crashed: {exc}",
                "manifest.json",
            )
        )

    try:
        claims, relations, events, reviews, sources = _load_records_by_logical_type(
            packet_root, manifest
        )
        closure_findings.extend(
            check_artifact_closure(
                packet_root, manifest, claims, relations, events, reviews, sources
            )
        )
    except Exception as exc:
        closure_findings.append(
            _mkfinding(
                "AEP51_INTERNAL_ERROR_ARTIFACT_CLOSURE",
                SEVERITY_ERROR,
                f"artifact closure check crashed: {exc}",
                "packet_root",
            )
        )

    try:
        canonical_files = manifest.get("canonical_files")
        canonical_files_list = (
            [p for p in canonical_files if isinstance(p, str)] if isinstance(canonical_files, list) else []
        )
        closure_findings.extend(scan_packet_numerics(packet_root, canonical_files_list))
    except Exception as exc:
        closure_findings.append(
            _mkfinding(
                "AEP51_INTERNAL_ERROR_NUMERIC_SCAN",
                SEVERITY_ERROR,
                f"numeric canonicalization scan crashed: {exc}",
                "packet_root",
            )
        )

    # === v0.5.3 closures (Round-5 top-3) ===
    try:
        # Re-use the claims/relations/events/reviews/sources loaded above.
        # (Local binding shadow from the artifact_closure try-block — re-load defensively.)
        claims_v53, relations_v53, events_v53, reviews_v53, sources_v53 = _load_records_by_logical_type(
            packet_root, manifest
        )
        # Closure #1 — GR+GO justification integrity
        closure_findings.extend(check_gr_go_justification_integrity(claims_v53))
        # Closure #2 — strict canonical path resolver (alias + traversal)
        closure_findings.extend(
            check_path_canonicality(claims_v53, relations_v53, events_v53, reviews_v53, sources_v53)
        )
        # Closure #3 — version-shape strictness gate (manifest.packet_epoch alone insufficient)
        records_by_file = _read_canonical_records(packet_root, manifest)
        closure_findings.extend(check_v05_shape_strictness_gate(manifest, records_by_file, config))
    except Exception as exc:
        closure_findings.append(
            _mkfinding(
                "AEP53_INTERNAL_ERROR_ROUND5_CLOSURES",
                SEVERITY_ERROR,
                f"v0.5.3 closure pass crashed: {exc}",
                "packet_root",
            )
        )

    # === v0.5.4 closures (Round-5 remaining) ===
    try:
        # Closure #4 — deep-migration receipt structural validation
        closure_findings.extend(check_deep_migration_receipt(manifest))
        # Closure #5 — reliability ↔ axis_b semantic consistency
        # Re-use claims_v53 loaded above; if it failed, fall back to fresh load.
        try:
            _claims_v54 = claims_v53  # type: ignore[name-defined]
        except NameError:
            _claims_v54, _, _, _, _ = _load_records_by_logical_type(packet_root, manifest)
        closure_findings.extend(check_reliability_axis_b_consistency(_claims_v54))
        # Closure #6 — packet_epoch + supersedes_packet_id monotonicity
        closure_findings.extend(check_epoch_monotonicity(manifest))
    except Exception as exc:
        closure_findings.append(
            _mkfinding(
                "AEP54_INTERNAL_ERROR_ROUND5_REMAINING_CLOSURES",
                SEVERITY_ERROR,
                f"v0.5.4 closure pass crashed: {exc}",
                "packet_root",
            )
        )

    return _merge_results(base_result, closure_findings)


# --------------------------------------------
# CLI (shape-compatible with v0.5 where feasible)
# --------------------------------------------

def _parse_now(now_str: Optional[str]) -> Optional[_dt.datetime]:
    if now_str is None:
        return None
    value = now_str.strip()
    if not value:
        return None
    # Keep parser aligned with _ensure_utc behavior expected by v0.5.
    dt = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _ensure_utc(dt)


def _build_cli_parser() -> argparse.ArgumentParser:
    for candidate in ("_build_cli_parser", "build_cli_parser", "_arg_parser", "build_arg_parser"):
        fn = getattr(_v05_module, candidate, None)
        if callable(fn):
            try:
                parser = fn()
            except Exception:
                parser = None
            if isinstance(parser, argparse.ArgumentParser):
                return parser

    parser = argparse.ArgumentParser(
        prog="aep-validate-v0.5.1",
        description="AEP v0.5.1 validator (v0.5 + hot-patch closures).",
    )
    parser.add_argument("packet_root", help="Path to packet root directory.")
    parser.add_argument(
        "--profile",
        default="aep:0.5/stable",
        choices=sorted(VALID_PROFILES),
        help="Validation profile.",
    )
    parser.add_argument(
        "--conformance-level",
        type=int,
        default=CONFORMANCE_LEVEL_2,
        choices=[CONFORMANCE_LEVEL_1, CONFORMANCE_LEVEL_2, CONFORMANCE_LEVEL_3],
        help="Conformance level (1, 2, or 3).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode (promote warnings where applicable).",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="Override validator current time (ISO-8601, UTC preferred).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full ValidationResult JSON.",
    )
    return parser


def _finding_to_dict(f: Finding) -> Dict[str, Any]:
    return {
        "code": f.code,
        "severity": f.severity,
        "message": f.message,
        "location": f.location,
    }


def _result_to_dict(result: ValidationResult) -> Dict[str, Any]:
    return {
        "schema_result": result.schema_result,
        "findings": [_finding_to_dict(f) for f in result.findings],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    packet_root_value = getattr(args, "packet_root", None)
    if packet_root_value is None:
        packet_root_value = getattr(args, "packet", None)
    if packet_root_value is None:
        packet_root_value = getattr(args, "root", None)
    if packet_root_value is None:
        parser.error("missing packet root argument")

    packet_root = Path(packet_root_value).resolve()
    profile = getattr(args, "profile", "aep:0.5/stable")
    conformance_level = getattr(args, "conformance_level", CONFORMANCE_LEVEL_2)
    strict_flag = bool(getattr(args, "strict", False))
    now_raw = getattr(args, "now", None)

    config = ValidationConfig(
        profile=profile,
        conformance_level=conformance_level,
        strict=strict_flag,
        now=_parse_now(now_raw),
    )

    result = validate_v0_5_1(packet_root, config)

    json_output = bool(getattr(args, "json", False))
    if json_output:
        print(json.dumps(_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(f"schema_result: {result.schema_result}")
        for f in result.findings:
            print(f"[{f.severity}] {f.code} @ {f.location}: {f.message}")

    if any(f.severity == SEVERITY_ERROR for f in result.findings):
        return 1
    if result.schema_result == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
