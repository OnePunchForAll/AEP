"""
validate_v0_5.py — Apache-2.0 — AEP v0.5 reference validator.

Copyright 2026 AEP Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Extends validate_v0_4.py with mechanical closure for all Round-2 attacks (10) and
cycle-2 P0 amendments (3). Single-file, stdlib + jsonschema only.

Conformance levels:
  - LEVEL_1: v0.4 axioms 1-8 + v0.4 fail-closed list (backward compat)
  - LEVEL_2: LEVEL_1 + axiom 9 (anchor diversity) + axiom 10 (time-validated evidence)
              + all 10 Round-2 mitigations active
  - LEVEL_3: LEVEL_2 + experimental features + execution_inputs_manifest

Usage:
  python -m aep.validate_v0_5 <packet_root> [--profile stable|experimental] [--level 1|2|3]
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import decimal
import hashlib
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from jsonschema import ValidationError

try:
    # v0.4 exports (actual names, post-publish-ready 2026-05-14)
    from aep.validate_v0_4 import (
        compute_state_hash as canonical_state_hash_v0_4,
        compute_manifest_hash as manifest_hash_v0_4,
        compute_assets_merkle_root as assets_merkle_root_v0_4,
        validate_packet_v04 as validate_v0_4,
        Report as _ReportV04,
    )
except Exception as exc:  # pragma: no cover - import path differences across deployments.
    raise RuntimeError(
        "validate_v0_5 requires validate_v0_4 to be importable from aep.validate_v0_4"
    ) from exc


# --- v0.5 surface types (codex authored with these fields; v0.4 Report has a leaner shape) ---
@dataclasses.dataclass
class Finding:
    """v0.5 Finding with explicit reason code + location.
    v0.4 had a simpler (severity, path, message) shape — v0.5 extends it for machine-readable
    disposition per AEP_v0_5_SPEC.md §23 (Validator obligations).
    """
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    location: str


@dataclasses.dataclass
class ValidationResult:
    """v0.5 ValidationResult. findings: list of Findings; schema_result: 'pass'|'warn'|'fail'."""
    findings: List[Finding] = dataclasses.field(default_factory=list)
    schema_result: str = "pass"

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


# === Constants ===
MERKLE_LEAF_DOMAIN = b"AEP_LEAF\n"
MERKLE_NODE_DOMAIN = b"AEP_NODE\n"
MERKLE_EMPTY = "sha256:" + hashlib.sha256(b"AEP_EMPTY").hexdigest()

CONFORMANCE_LEVEL_1 = 1
CONFORMANCE_LEVEL_2 = 2
CONFORMANCE_LEVEL_3 = 3
DEFAULT_CONFORMANCE_LEVEL = CONFORMANCE_LEVEL_2

VALID_PROFILES = {"aep:0.5/stable", "aep:0.5/experimental"}
VALID_CHANNELS = {"stable", "experimental"}

INFERENCE_ONLY_LABELS = {
    "architectural_inference",
    "analogical_transfer",
    "cross_packet_synthesis",
    "speculative_design",
}
ANCHORED_LABELS = {"explicit_in_source", "derived_from_claims"}

GOVERNANCE_RULE = "GOVERNANCE_RULE"
RELIABILITY_TIERS = [
    "UNKNOWN",
    "CONFLICTED",
    "ASSUMPTION",
    "PLAUSIBLE",
    "STRONGLY_PLAUSIBLE",
    "PROVEN_RELIABLE",
]
RELIABILITY_TO_INDEX = {name: i for i, name in enumerate(RELIABILITY_TIERS)}

SUPPORTED_AEP_VERSIONS = {"aep:0.5/stable", "aep:0.5/experimental"}

DEFAULT_CANONICAL_FILES = [
    "aepkg.json",
    "claims/claims.jsonl",
    "claims/relations.jsonl",
    "sources/sources.jsonl",
    "reviews/reviews.jsonl",
    "ops/events.jsonl",
    "ops/packet_lineage.json",
]

UTC = dt.timezone.utc

CANONICAL_NUMBER_RE = re.compile(
    r"""
    ^
    -?
    (?:
        0
        |
        [1-9][0-9]*
    )
    (?:
        \.[0-9]+
    )?
    (?:
        [e][+-]?[0-9]+
    )?
    $
    """,
    re.VERBOSE,
)

JSON_NUMBER_TOKEN_RE = re.compile(
    r"""
    -?
    (?:
        0
        |
        [1-9][0-9]*
    )
    (?:
        \.[0-9]+
    )?
    (?:
        [eE][+-]?[0-9]+
    )?
    """,
    re.VERBOSE,
)

JSON_NUMBER_CANONICAL_RE = re.compile(
    r"""
    ^
    -?
    (?:
        0
        |
        [1-9][0-9]*
    )
    (?:
        \.[0-9]+
    )?
    (?:
        e[+-]?[0-9]+
    )?
    $
    """,
    re.VERBOSE,
)

ISO_8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)

REASON_CODES = {
    "AEP5_JSON_DUP_KEY": "Duplicate key in strict canonical JSON parse.",
    "AEP5_JSON_NON_FINITE": "Non-finite number (NaN/Infinity) disallowed.",
    "AEP5_JSON_NON_CANONICAL_NUMBER": "Number token is not canonical RFC 8785 form.",
    "AEP5_JSON_INVALID": "JSON parsing failed under strict profile.",
    "AEP5_HASH_STATE_MISMATCH": "Computed strict state hash does not match manifest.",
    "AEP5_HASH_MANIFEST_MISMATCH": "Computed strict manifest hash does not match manifest.",
    "AEP5_MERKLE_MISMATCH": "Computed AEP-MERKLE-v1 root does not match manifest.",
    "AEP5_MERKLE_INVALID_FORMAT": "Merkle hash format is invalid.",
    "AEP5_FRESHNESS_INVALID_TIME": "Invalid claim time field format.",
    "AEP5_FRESHNESS_NOT_YET_VALID": "Claim valid_from is in the future.",
    "AEP5_FRESHNESS_EXPIRED": "Claim valid_until has passed.",
    "AEP5_FRESHNESS_STALE_GO": "GO claim is stale and requires revalidation.",
    "AEP5_PACKET_EPOCH_NON_MONOTONIC": "packet_epoch is not monotonic over supersedes link.",
    "AEP5_ANCHOR_URL_TRUST_MISSING": "URL anchor missing trust context fields.",
    "AEP5_ANCHOR_GIT_TRUST_MISSING": "Git anchor missing trust context fields.",
    "AEP5_ANCHOR_TRUST_EMPTY": "Anchor present but trust context empty.",
    "AEP5_POLICY_ONLY_GO": "GO/GOVERNANCE_RULE claim lacks non-policy justification.",
    "AEP5_GOV_OVERRIDE_INVALID_TIER": "governance_override requires R4 tier.",
    "AEP5_GOV_OVERRIDE_INSUFFICIENT_R4": "governance_override requires >=2 R4 receipts.",
    "AEP5_INFERENCE_ESCALATION_NO_ANCHOR": "Inference chain reaches PROVEN_RELIABLE without anchor.",
    "AEP5_INFERENCE_HOP_DECAY_WARN": "Reliability escalation exceeds allowed upstream decay.",
    "AEP5_SCHEMA_VERSION_INVALID": "Manifest aep_version is outside supported channels.",
    "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH": "Requested profile does not match manifest channel.",
    "AEP5_EXTENSION_STABILITY_MISSING": "Extension missing semantic_stability.",
    "AEP5_EXTENSION_EXPERIMENTAL_FORBIDDEN": "Experimental extension forbidden in stable profile.",
    "AEP5_VERSION_CONSUMER_MIN_UNSUPPORTED": "Record consumer_min_version exceeds validator version.",
    "AEP5_VERSION_PRODUCER_NEWER": "Record producer_version newer than validator.",
    "AEP5_SYBIL_THRESHOLD_NOT_MET": "Weighted reviewer consensus threshold not met.",
    "AEP5_SYBIL_UNVERIFIED_ONLY": "Consensus achieved only through unverified reviewers.",
    "AEP5_TOCTOU_STALE_AT_DECISION": "Decision-time revalidation stale with no recent event.",
    "AEP5_EXEC_INPUT_HASH_MISMATCH": "Execution input hash mismatch.",
    "AEP5_EXEC_INPUT_MISSING": "Declared execution input file missing.",
    "AEP5_EXEC_INPUT_SIDE_REFERENCE_UNDECLARED": "GO claim references undeclared execution input.",
    "AEP5_CHANNEL_INFO": "Manifest channel/profile summary.",
    "AEP5_INTERNAL_ERROR": "Internal validator error.",
}

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

CURRENT_VALIDATOR_VERSION = "0.5.0"


@dataclasses.dataclass
class ValidationConfig:
    """
    Runtime configuration for validate_v0_5.

    profile:
      Full profile identifier. Supported values:
        - aep:0.5/stable
        - aep:0.5/experimental

    conformance_level:
      1, 2, or 3. Higher levels add stricter checks and optional features.

    strict:
      If true, fail-closed checks emit errors. If false, strict-only gates degrade
      selected outcomes to warnings for exploratory runs.

    now:
      Optional clock override. Must be timezone-aware UTC datetime if provided.

    fingerprint_db:
      Optional mapping reviewer_agent -> known_stable_fingerprint.
      Used for attack-8 interim sybil hardening.
    """

    profile: str = "aep:0.5/stable"
    conformance_level: int = DEFAULT_CONFORMANCE_LEVEL
    strict: bool = True
    now: Optional[dt.datetime] = None
    fingerprint_db: Optional[Dict[str, str]] = None


@dataclasses.dataclass
class V05Context:
    """
    Internal context object for sharing parsed packet state across checks.
    """

    packet_root: Path
    manifest: Dict[str, Any]
    claims: Dict[str, Dict[str, Any]]
    claim_list: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    reviews: List[Dict[str, Any]]
    ops_events: List[Dict[str, Any]]
    packet_lineage: Dict[str, Any]
    config: ValidationConfig
    channel: str


def _mkfinding(code: str, severity: str, message: str, location: str) -> Finding:
    """
    Build a Finding from v0.4 dataclass type with standardized fields.
    """
    return Finding(code=code, severity=severity, message=message, location=location)


def _ensure_utc(ts: Optional[dt.datetime]) -> dt.datetime:
    """
    Ensure an aware UTC timestamp.
    """
    if ts is None:
        return dt.datetime.now(tz=UTC)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _read_text(path: Path) -> str:
    """
    Read UTF-8 text, preserving exact bytes for JSON parser pre-checks.
    """
    return path.read_text(encoding="utf-8")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """
    Read JSONL file into list of objects using strict canonical parse.
    Blank lines are ignored.
    """
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        parsed = parse_strict_canonical(stripped)
        if not isinstance(parsed, dict):
            raise ValueError(f"AEP5_JSON_INVALID at {path}:{line_no}: expected object line")
        rows.append(parsed)
    return rows


def _read_json(path: Path) -> Dict[str, Any]:
    """
    Read JSON object using strict canonical parse.
    """
    text = _read_text(path)
    parsed = parse_strict_canonical(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"AEP5_JSON_INVALID at {path}: expected JSON object")
    return parsed


def _is_sha256_prefixed(value: Any) -> bool:
    """
    Check whether value is of form sha256:<64 lowercase hex>.
    """
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _strip_sha256_prefix(value: str) -> bytes:
    """
    Convert sha256:<hex> into raw 32-byte digest. Raises ValueError on format issues.
    """
    if not _is_sha256_prefixed(value):
        raise ValueError("AEP5_MERKLE_INVALID_FORMAT")
    return bytes.fromhex(value.split(":", 1)[1])


def _version_tuple(v: str) -> Tuple[int, int, int]:
    """
    Parse semantic version 'X.Y.Z' into tuple for comparisons.
    Non-conforming versions are treated as very high to force conservative warnings/errors.
    """
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(v).strip())
    if not m:
        return (999999, 999999, 999999)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _safe_get(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Retrieve dictionary key safely.
    """
    return d[key] if isinstance(d, dict) and key in d else default


def _claim_id(claim: Dict[str, Any], idx: int) -> str:
    """
    Return claim id fallback.
    """
    cid = _safe_get(claim, "claim_id")
    if isinstance(cid, str) and cid:
        return cid
    cid = _safe_get(claim, "id")
    if isinstance(cid, str) and cid:
        return cid
    return f"claim[{idx}]"


def _event_time(event: Dict[str, Any]) -> Optional[dt.datetime]:
    """
    Parse event timestamp from known fields.
    """
    for key in ("event_time", "timestamp", "created_at", "time"):
        val = _safe_get(event, key)
        ts = _parse_iso8601_utc(val)
        if ts is not None:
            return ts
    return None


def _parse_iso8601_utc(value: Any) -> Optional[dt.datetime]:
    """
    Parse RFC3339/ISO8601 timestamp to aware UTC datetime.
    Returns None on missing or invalid values.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if not ISO_8601_RE.fullmatch(text):
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


# === Strict JSON canonical profile (Attack 1) ===
def _reject_constant(value: str) -> None:
    """
    parse_constant hook for json.loads.
    Rejects NaN and Infinity family tokens.
    """
    raise ValueError("AEP5_JSON_NON_FINITE")


def _reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """
    object_pairs_hook for json.loads to reject duplicate keys at parse-time.
    """
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"AEP5_JSON_DUP_KEY:{key}")
        out[key] = value
    return out


def _scan_for_noncanonical_numbers(text: str) -> List[str]:
    """
    Scan raw JSON text for clearly non-canonical numeric forms.

    RFC 8785 alignment:
      - Number syntax and normalization follow JSON Canonicalization Scheme (JCS).
      - This scanner enforces lowercase 'e', no leading plus, no leading zeros,
        and no unnecessary trailing zeros in decimal forms.

    Deviation note:
      - RFC 8785 canonicalization relies on ECMAScript Number serialization.
        This reference implementation uses Python Decimal-driven canonical output
        plus lexical checks to fail closed on ambiguous source encodings.
    """
    violations: List[str] = []

    def is_number_start(ch: str) -> bool:
        return ch == "-" or ("0" <= ch <= "9")

    i = 0
    n = len(text)
    in_string = False
    escaped = False
    while i < n:
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if is_number_start(ch):
            j = i + 1
            while j < n:
                cj = text[j]
                if cj in "0123456789.+-eE":
                    j += 1
                    continue
                break
            token = text[i:j]
            if JSON_NUMBER_TOKEN_RE.fullmatch(token):
                if not JSON_NUMBER_CANONICAL_RE.fullmatch(token):
                    violations.append(token)
                else:
                    # Canonical additional checks:
                    # disallow decimal trailing zeros and exponent leading zeros.
                    core = token[1:] if token.startswith("-") else token
                    if "." in core:
                        frac = core.split(".", 1)[1]
                        exp_split = re.split(r"[eE]", frac, maxsplit=1)
                        frac_only = exp_split[0]
                        if len(frac_only) > 1 and frac_only.endswith("0"):
                            violations.append(token)
                    if "e" in token:
                        exp = token.split("e", 1)[1]
                        if exp.startswith(("+", "-")):
                            exp_digits = exp[1:]
                        else:
                            exp_digits = exp
                        if len(exp_digits) > 1 and exp_digits.startswith("0"):
                            violations.append(token)
            i = j
            continue

        i += 1

    # Deduplicate preserving order.
    deduped: List[str] = []
    seen: Set[str] = set()
    for item in violations:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _canonicalize_string(text: str) -> str:
    """
    Normalize text to NFC for deterministic hashing and re-serialization.
    """
    return unicodedata.normalize("NFC", text)


def _canonicalize_number(value: Any) -> str:
    """
    Canonicalize a numeric value to strict textual representation.

    RFC 8785 reference:
      - JCS requires deterministic number serialization.
      - This implementation uses Decimal normalization and canonical exponent style
        with lowercase 'e'. The representation intentionally avoids trailing zeros,
        leading plus, uppercase exponent, and non-finite values.
    """
    if isinstance(value, bool):  # bool is int subclass in Python; guard first.
        raise ValueError("AEP5_JSON_NON_CANONICAL_NUMBER")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("AEP5_JSON_NON_FINITE")
        # Use repr as starting point for float round-trippable text.
        text = repr(value)
        dec = decimal.Decimal(text)
        return _canonicalize_decimal(dec)
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError("AEP5_JSON_NON_FINITE")
        return _canonicalize_decimal(value)
    raise ValueError("AEP5_JSON_NON_CANONICAL_NUMBER")


def _canonicalize_decimal(dec: decimal.Decimal) -> str:
    """
    Canonicalize Decimal per strict profile.
    """
    # Normalize removes trailing zeros in coefficient.
    dec = dec.normalize()
    if dec == dec.to_integral():
        as_int = format(dec.quantize(decimal.Decimal(1)), "f")
        if as_int == "-0":
            as_int = "0"
        if not CANONICAL_NUMBER_RE.fullmatch(as_int):
            raise ValueError(f"AEP5_JSON_NON_CANONICAL_NUMBER:{as_int}")
        return as_int

    sign, digits, exponent = dec.as_tuple()
    # Convert to plain scientific form where needed.
    # We favor plain decimal unless exponent is large magnitude.
    txt = format(dec, "f")
    if "E" in txt or "e" in txt:
        txt = format(dec, "f")

    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")

    if txt == "-0":
        txt = "0"
    if not CANONICAL_NUMBER_RE.fullmatch(txt):
        # Fallback to explicit scientific with lowercase e.
        txt = format(dec.normalize(), "e").replace("E", "e")
        mant, exp = txt.split("e", 1)
        mant = mant.rstrip("0").rstrip(".")
        exp_sign = "+" if exp.startswith("+") else "-" if exp.startswith("-") else ""
        exp_num = exp[1:] if exp_sign else exp
        exp_num = exp_num.lstrip("0") or "0"
        txt = f"{mant}e{exp_sign}{exp_num}" if exp_sign else f"{mant}e{exp_num}"
        if txt.endswith("e+0"):
            txt = txt[:-3]
        if txt.endswith("e0"):
            txt = txt[:-2]
    if not CANONICAL_NUMBER_RE.fullmatch(txt):
        raise ValueError(f"AEP5_JSON_NON_CANONICAL_NUMBER:{txt}")
    return txt


def _canonicalize_obj(value: Any) -> Any:
    """
    Recursively canonicalize an arbitrary JSON-compatible object.

    Returns a structure where:
      - strings are NFC normalized
      - numbers are wrapped in CanonicalNumber instances for direct emission
      - object keys are NFC normalized and uniqueness re-checked after normalization
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _canonicalize_string(value)
    if isinstance(value, (int, float, decimal.Decimal)):
        return CanonicalNumber(_canonicalize_number(value))
    if isinstance(value, list):
        return [_canonicalize_obj(v) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError("AEP5_JSON_INVALID")
            nk = _canonicalize_string(k)
            if nk in out:
                raise ValueError(f"AEP5_JSON_DUP_KEY:{nk}")
            out[nk] = _canonicalize_obj(v)
        return out
    raise ValueError("AEP5_JSON_INVALID")


@dataclasses.dataclass(frozen=True)
class CanonicalNumber:
    """
    Wrapper to ensure canonical numbers are emitted as raw JSON numbers
    instead of strings when serializing strict canonical JSON.
    """

    text: str


def parse_strict_canonical(text: str) -> Any:
    """
    Parse JSON enforcing strict-canonical profile (Attack 1).

    Rejects:
      - Duplicate object keys
      - NaN / Infinity / -Infinity
      - Non-canonical number forms (leading +, leading zeros, trailing zeros,
        uppercase exponent form)

    RFC 8785 reference:
      - Parsing then re-serializing under a deterministic profile prevents hashing
        disagreement across permissive parsers.

    AEP strict extension:
      - Fails closed on lexical non-canonical number tokens rather than silently
        normalizing producer-side ambiguity.
    """
    if not isinstance(text, str):
        raise ValueError("AEP5_JSON_INVALID")

    violations = _scan_for_noncanonical_numbers(text)
    if violations:
        raise ValueError(f"AEP5_JSON_NON_CANONICAL_NUMBER:{violations[0]}")

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=decimal.Decimal,
            parse_int=decimal.Decimal,
        )
    except ValueError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"AEP5_JSON_INVALID:{exc.msg}") from exc

    # Post parse finite check and canonicalization viability.
    _walk_reject_nonfinite(parsed)
    return parsed


def _walk_reject_nonfinite(value: Any) -> None:
    """
    Deep check for non-finite numeric objects.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("AEP5_JSON_NON_FINITE")
        return
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError("AEP5_JSON_NON_FINITE")
        return
    if isinstance(value, list):
        for item in value:
            _walk_reject_nonfinite(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _walk_reject_nonfinite(item)
        return


def serialize_strict_canonical(obj: Any) -> str:
    """
    Serialize obj to strict canonical JSON (RFC 8785 JCS + AEP extras).

    Guarantees:
      - object keys sorted lexicographically by Unicode codepoint
      - no insignificant whitespace
      - strings NFC normalized and escaped via JSON standard escapes
      - numbers emitted in canonical textual form from _canonicalize_number
      - booleans/null lowercase
    """
    canon = _canonicalize_obj(obj)
    return _emit_json(canon)


def _emit_json(value: Any) -> str:
    """
    Emit canonical JSON string from canonicalized object.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, CanonicalNumber):
        return value.text
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_emit_json(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return "{" + ",".join(f"{_emit_json(k)}:{_emit_json(v)}" for k, v in items) + "}"
    raise ValueError("AEP5_JSON_INVALID")


def canonical_state_hash_v0_5(packet_root: Path, canonical_files: List[str]) -> str:
    """
    v0.5 state hash with strict canonical parsing and serialization.

    Closes Attack 1 by hashing strict AST representation rather than permissive parse.
    For each canonical JSON/JSONL file:
      - parse_strict_canonical
      - serialize_strict_canonical
      - hash deterministic bytes
    Aggregate:
      sha256 over newline-separated '<relpath>\\t<sha256hex>' entries sorted by path.
    """
    entries: List[str] = []
    for rel in sorted(canonical_files):
        p = packet_root / rel
        if not p.exists():
            entries.append(f"{rel}\tMISSING")
            continue
        if p.suffix.lower() == ".jsonl":
            lines = p.read_text(encoding="utf-8").splitlines()
            canonical_lines: List[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                parsed_line = parse_strict_canonical(stripped)
                canonical_lines.append(serialize_strict_canonical(parsed_line))
            normalized_bytes = ("\n".join(canonical_lines) + ("\n" if canonical_lines else "")).encode(
                "utf-8"
            )
        else:
            parsed = parse_strict_canonical(_read_text(p))
            normalized_bytes = (serialize_strict_canonical(parsed) + "\n").encode("utf-8")
        digest = hashlib.sha256(normalized_bytes).hexdigest()
        entries.append(f"{rel}\t{digest}")
    aggregate = "\n".join(entries).encode("utf-8")
    return "sha256:" + hashlib.sha256(aggregate).hexdigest()


def manifest_hash_v0_5(manifest_obj: Dict[str, Any]) -> str:
    """
    Canonical manifest hash for v0.5 from strict canonical serializer.
    """
    ser = serialize_strict_canonical(manifest_obj).encode("utf-8")
    return "sha256:" + hashlib.sha256(ser).hexdigest()


# === AEP-MERKLE-v1 (Attack 2) ===
def merkle_leaf_hash(normalized_path: str, file_bytes: bytes) -> str:
    """
    Compute AEP-MERKLE-v1 leaf hash.

    Formula:
      leaf = sha256(
        b"AEP_LEAF\\n" + normalized_path.encode("utf-8") + b"\\n" + sha256(file_bytes).digest()
      )

    Returns:
      sha256:<hex>
    """
    file_hash = hashlib.sha256(file_bytes).digest()
    digest = hashlib.sha256(
        MERKLE_LEAF_DOMAIN + normalized_path.encode("utf-8") + b"\n" + file_hash
    ).hexdigest()
    return "sha256:" + digest


def merkle_internal_hash(left: str, right: str) -> str:
    """
    Compute AEP-MERKLE-v1 internal node hash.

    Internal formula:
      node = sha256(b"AEP_NODE\\n" + left_digest + right_digest)

    Inputs must be sha256:<hex> strings.
    """
    left_raw = _strip_sha256_prefix(left)
    right_raw = _strip_sha256_prefix(right)
    digest = hashlib.sha256(MERKLE_NODE_DOMAIN + left_raw + right_raw).hexdigest()
    return "sha256:" + digest


def normalize_path(path: str, case_policy: str = "preserve") -> str:
    """
    Normalize asset path for Merkle leaves.

    Operations:
      - Convert path separators to '/'
      - Remove leading './'
      - Apply NFC Unicode normalization
      - Apply case policy:
          - preserve (default)
          - lower
          - upper
    """
    if not isinstance(path, str):
        raise ValueError("AEP5_MERKLE_INVALID_FORMAT")
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.strip("/")
    normalized = unicodedata.normalize("NFC", normalized)
    if case_policy == "lower":
        normalized = normalized.lower()
    elif case_policy == "upper":
        normalized = normalized.upper()
    elif case_policy == "preserve":
        pass
    else:
        raise ValueError(f"AEP5_MERKLE_INVALID_FORMAT:unknown-case-policy:{case_policy}")
    return normalized


def _iter_asset_files(assets_root: Path) -> Iterator[Path]:
    """
    Iterate regular files under assets_root recursively, sorted deterministically by path.
    """
    if not assets_root.exists() or not assets_root.is_dir():
        return iter(())
    # Build list first for deterministic order.
    files: List[Path] = [p for p in assets_root.rglob("*") if p.is_file()]
    files.sort(key=lambda p: normalize_path(str(p.relative_to(assets_root))))
    return iter(files)


def aep_merkle_v1(assets_root: Path, case_policy: str = "preserve") -> str:
    """
    Compute AEP-MERKLE-v1 over assets/**.

    Rules:
      - Leaf:
          sha256(b"AEP_LEAF\\n" + normalized_path + b"\\n" + sha256(file_bytes))
      - Internal:
          sha256(b"AEP_NODE\\n" + left_digest + right_digest)
      - Odd node duplication:
          duplicate last digest when layer count is odd
      - Empty tree:
          sha256(b"AEP_EMPTY")

    Two-asset example (worked formula vector):
      Let:
        p1 = "a.txt", b1 = b"hello"
        p2 = "b.txt", b2 = b"world"
      Then:
        l1 = sha256("AEP_LEAF\\na.txt\\n" + sha256(b"hello"))
        l2 = sha256("AEP_LEAF\\nb.txt\\n" + sha256(b"world"))
        root = sha256("AEP_NODE\\n" + l1 + l2)

    The exact hex output depends on byte-level inputs and path normalization.
    """
    files = list(_iter_asset_files(assets_root))
    if not files:
        return MERKLE_EMPTY

    leaves: List[str] = []
    for path in files:
        rel = normalize_path(str(path.relative_to(assets_root)), case_policy=case_policy)
        data = path.read_bytes()
        leaves.append(merkle_leaf_hash(rel, data))

    layer = leaves
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer = layer + [layer[-1]]
        next_layer: List[str] = []
        for i in range(0, len(layer), 2):
            next_layer.append(merkle_internal_hash(layer[i], layer[i + 1]))
        layer = next_layer
    return layer[0]


# === Cross-Packet Freshness Policy (Attack 3) ===
def check_freshness(claim: dict, ops_events: List[dict], now: dt.datetime, strict: bool) -> List[Finding]:
    """
    Reason code family: AEP5_FRESHNESS_*

    Check valid_from / valid_until / revalidate_after with explicit UTC arithmetic.
    Fail-closed behavior:
      - If axis_b_action == GO and decision_time_revalidation_required is true and
        now > revalidate_after, emit error in strict mode.
    """
    findings: List[Finding] = []
    cid = str(_safe_get(claim, "claim_id", _safe_get(claim, "id", "unknown")))
    location = f"claims/{cid}"

    valid_from = _parse_iso8601_utc(_safe_get(claim, "valid_from"))
    valid_until = _parse_iso8601_utc(_safe_get(claim, "valid_until"))
    revalidate_after = _parse_iso8601_utc(_safe_get(claim, "revalidate_after"))

    for field, parsed in (
        ("valid_from", valid_from if "valid_from" in claim else True),
        ("valid_until", valid_until if "valid_until" in claim else True),
        ("revalidate_after", revalidate_after if "revalidate_after" in claim else True),
    ):
        if parsed is None and field in claim:
            findings.append(
                _mkfinding(
                    "AEP5_FRESHNESS_INVALID_TIME",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_FRESHNESS_INVALID_TIME']} field={field}",
                    location,
                )
            )

    if valid_from is not None and now < valid_from:
        findings.append(
            _mkfinding(
                "AEP5_FRESHNESS_NOT_YET_VALID",
                SEVERITY_ERROR if strict else SEVERITY_WARNING,
                f"{REASON_CODES['AEP5_FRESHNESS_NOT_YET_VALID']} now={now.isoformat()} valid_from={valid_from.isoformat()}",
                location,
            )
        )

    if valid_until is not None and now > valid_until:
        findings.append(
            _mkfinding(
                "AEP5_FRESHNESS_EXPIRED",
                SEVERITY_ERROR if strict else SEVERITY_WARNING,
                f"{REASON_CODES['AEP5_FRESHNESS_EXPIRED']} now={now.isoformat()} valid_until={valid_until.isoformat()}",
                location,
            )
        )

    axis_b_action = str(_safe_get(claim, "axis_b_action", _safe_get(claim, "axis_b", "")))
    needs_revalidation = bool(_safe_get(claim, "decision_time_revalidation_required", False))
    if axis_b_action == "GO" and needs_revalidation and revalidate_after is not None and now > revalidate_after:
        findings.append(
            _mkfinding(
                "AEP5_FRESHNESS_STALE_GO",
                SEVERITY_ERROR if strict else SEVERITY_WARNING,
                f"{REASON_CODES['AEP5_FRESHNESS_STALE_GO']} now={now.isoformat()} revalidate_after={revalidate_after.isoformat()}",
                location,
            )
        )
    return findings


def check_packet_epoch_monotonicity(
    manifest: Dict[str, Any], packet_lineage: Dict[str, Any], strict: bool
) -> List[Finding]:
    """
    Reason code: AEP5_PACKET_EPOCH_NON_MONOTONIC

    Verifies packet_epoch monotonicity against supersedes_packet_id link where
    lineage payload includes superseded packet metadata.
    """
    findings: List[Finding] = []
    location = "ops/packet_lineage.json"
    current_epoch = _safe_get(manifest, "packet_epoch")
    supersedes_id = _safe_get(manifest, "supersedes_packet_id")
    if supersedes_id is None:
        return findings

    superseded_records = _safe_get(packet_lineage, "superseded_packets", [])
    if not isinstance(superseded_records, list):
        superseded_records = []
    previous_epoch: Optional[int] = None
    for row in superseded_records:
        if not isinstance(row, dict):
            continue
        if _safe_get(row, "packet_id") == supersedes_id:
            ep = _safe_get(row, "packet_epoch")
            if isinstance(ep, int):
                previous_epoch = ep
                break
    if isinstance(current_epoch, int) and previous_epoch is not None:
        if current_epoch <= previous_epoch:
            findings.append(
                _mkfinding(
                    "AEP5_PACKET_EPOCH_NON_MONOTONIC",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_PACKET_EPOCH_NON_MONOTONIC']} current={current_epoch} previous={previous_epoch}",
                    location,
                )
            )
    return findings


# === Anchor Trust Context (Attack 4) ===
def _claim_has_proven_reliable(claim: Dict[str, Any]) -> bool:
    """
    Determine if claim reliability tier is PROVEN_RELIABLE.
    """
    rel = _safe_get(claim, "reliability")
    return isinstance(rel, str) and rel == "PROVEN_RELIABLE"


def check_anchor_trust_context(source: dict, strict: bool) -> List[Finding]:
    """
    Reason codes:
      - AEP5_ANCHOR_URL_TRUST_MISSING
      - AEP5_ANCHOR_GIT_TRUST_MISSING
      - AEP5_ANCHOR_TRUST_EMPTY

    Enforces trust-context fields for anchored sources:
      - URL anchors require scheme + host; tls_fingerprint optional
      - Git anchors require remote_url; signed_tag + trusted_root_policy optional
    """
    findings: List[Finding] = []
    sid = str(_safe_get(source, "source_id", _safe_get(source, "id", "unknown")))
    location = f"sources/{sid}"

    anchor = _safe_get(source, "anchor", {})
    if not isinstance(anchor, dict) or not anchor:
        return findings

    kind = str(_safe_get(_safe_get(anchor, "location", {}), "kind", _safe_get(anchor, "kind", "")))
    trust = _safe_get(anchor, "trust_context", {})
    if not isinstance(trust, dict):
        trust = {}

    if not trust:
        findings.append(
            _mkfinding(
                "AEP5_ANCHOR_TRUST_EMPTY",
                SEVERITY_ERROR if strict else SEVERITY_WARNING,
                REASON_CODES["AEP5_ANCHOR_TRUST_EMPTY"],
                location,
            )
        )
        if strict:
            return findings

    if kind in {"url", "http", "https"}:
        scheme = _safe_get(trust, "scheme")
        host = _safe_get(trust, "host")
        if not (isinstance(scheme, str) and scheme) or not (isinstance(host, str) and host):
            findings.append(
                _mkfinding(
                    "AEP5_ANCHOR_URL_TRUST_MISSING",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    REASON_CODES["AEP5_ANCHOR_URL_TRUST_MISSING"],
                    location,
                )
            )
    elif kind in {"git", "repo", "repository"}:
        remote = _safe_get(trust, "remote_url")
        if not (isinstance(remote, str) and remote):
            findings.append(
                _mkfinding(
                    "AEP5_ANCHOR_GIT_TRUST_MISSING",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    REASON_CODES["AEP5_ANCHOR_GIT_TRUST_MISSING"],
                    location,
                )
            )
    return findings


def check_claim_anchor_requirements(
    claim: Dict[str, Any], source_index: Dict[str, Dict[str, Any]], strict: bool
) -> List[Finding]:
    """
    Require trust-context checks for PROVEN_RELIABLE claims with URL or git anchors.
    """
    findings: List[Finding] = []
    if not _claim_has_proven_reliable(claim):
        return findings
    source_ids = _safe_get(claim, "source_ids", [])
    if not isinstance(source_ids, list):
        return findings
    for sid in source_ids:
        src = source_index.get(str(sid))
        if src is None:
            continue
        findings.extend(check_anchor_trust_context(src, strict=strict))
    return findings


# === GO/GOVERNANCE_RULE coupling (Attack 5) ===
def _count_r4_receipts(reviews: List[dict], claim_id: str) -> int:
    """
    Count review receipts with review_tier R4 for claim_id.
    """
    count = 0
    for rev in reviews:
        if _safe_get(rev, "claim_id") != claim_id:
            continue
        tier = _safe_get(rev, "review_tier", _safe_get(rev, "tier"))
        if tier == "R4":
            count += 1
    return count


def check_go_disposition_coupling(claim: dict, all_claims: Dict[str, dict], reviews: List[dict]) -> List[Finding]:
    """
    Reason codes:
      - AEP5_POLICY_ONLY_GO
      - AEP5_GOV_OVERRIDE_INVALID_TIER
      - AEP5_GOV_OVERRIDE_INSUFFICIENT_R4

    Enforces GO + GOVERNANCE_RULE coupling:
      - go_justification_claim_ids must be non-empty
      - at least one referenced claim must have reliability != GOVERNANCE_RULE
      - governance_override=true valid only with review_tier=R4 and >=2 R4 receipts
    """
    findings: List[Finding] = []
    cid = str(_safe_get(claim, "claim_id", _safe_get(claim, "id", "unknown")))
    location = f"claims/{cid}"

    axis_b_action = _safe_get(claim, "axis_b_action", _safe_get(claim, "axis_b"))
    reliability = _safe_get(claim, "reliability")
    if axis_b_action != "GO" or reliability != GOVERNANCE_RULE:
        return findings

    refs = _safe_get(claim, "go_justification_claim_ids", [])
    if not isinstance(refs, list) or len(refs) == 0:
        findings.append(
            _mkfinding(
                "AEP5_POLICY_ONLY_GO",
                SEVERITY_ERROR,
                "go_justification_claim_ids must be non-empty for GO/GOVERNANCE_RULE",
                location,
            )
        )
        refs = []

    has_non_policy = False
    for ref in refs:
        c = all_claims.get(str(ref))
        if c is None:
            continue
        rel = _safe_get(c, "reliability")
        if rel != GOVERNANCE_RULE:
            has_non_policy = True
            break
    if not has_non_policy:
        findings.append(
            _mkfinding(
                "AEP5_POLICY_ONLY_GO",
                SEVERITY_ERROR,
                REASON_CODES["AEP5_POLICY_ONLY_GO"],
                location,
            )
        )

    if bool(_safe_get(claim, "governance_override", False)):
        tier = _safe_get(claim, "review_tier", _safe_get(claim, "required_review_tier"))
        if tier != "R4":
            findings.append(
                _mkfinding(
                    "AEP5_GOV_OVERRIDE_INVALID_TIER",
                    SEVERITY_ERROR,
                    REASON_CODES["AEP5_GOV_OVERRIDE_INVALID_TIER"],
                    location,
                )
            )
        r4_count = _count_r4_receipts(reviews, cid)
        if r4_count < 2:
            findings.append(
                _mkfinding(
                    "AEP5_GOV_OVERRIDE_INSUFFICIENT_R4",
                    SEVERITY_ERROR,
                    f"{REASON_CODES['AEP5_GOV_OVERRIDE_INSUFFICIENT_R4']} count={r4_count}",
                    location,
                )
            )
    return findings


# === Inference Hop Decay (Attack 6) ===
def _relation_is_inference_only(rel: Dict[str, Any]) -> bool:
    """
    Return True if relation is inference-only by label/type.
    """
    label = _safe_get(rel, "label", _safe_get(rel, "relation_type", _safe_get(rel, "type", "")))
    return isinstance(label, str) and label in INFERENCE_ONLY_LABELS


def _relation_is_anchored(rel: Dict[str, Any]) -> bool:
    """
    Return True if relation indicates direct anchor semantics.
    """
    label = _safe_get(rel, "label", _safe_get(rel, "relation_type", _safe_get(rel, "type", "")))
    return isinstance(label, str) and label in ANCHORED_LABELS


def _build_parent_map(relations: List[dict]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build child->incoming relation list map.
    """
    parent_map: Dict[str, List[Dict[str, Any]]] = {}
    for rel in relations:
        child = _safe_get(rel, "to_claim_id", _safe_get(rel, "child_claim_id"))
        parent = _safe_get(rel, "from_claim_id", _safe_get(rel, "parent_claim_id"))
        if not isinstance(child, str) or not isinstance(parent, str):
            continue
        parent_map.setdefault(child, []).append(rel)
    return parent_map


def compute_inference_lineage(
    claim_id: str, claims: Dict[str, dict], relations: List[dict]
) -> Tuple[List[str], int]:
    """
    Walk the basis DAG and return a representative upstream chain and inference hop count.

    Requirements satisfied:
      - recursive traversal
      - cycle detection

    Returns:
      (path_claim_ids, inference_hops_on_path)
    """
    parent_map = _build_parent_map(relations)
    best_chain: List[str] = [claim_id]
    best_hops = 0

    def dfs(node: str, seen: Set[str], chain: List[str], hops: int) -> None:
        nonlocal best_chain, best_hops
        if node in seen:
            # cycle detected; prefer reporting the deepest traversed path so far.
            if len(chain) > len(best_chain):
                best_chain = list(chain)
                best_hops = hops
            return

        parents = parent_map.get(node, [])
        if not parents:
            if len(chain) > len(best_chain):
                best_chain = list(chain)
                best_hops = hops
            return

        local_seen = set(seen)
        local_seen.add(node)
        traversed = False
        for rel in parents:
            parent_id = _safe_get(rel, "from_claim_id", _safe_get(rel, "parent_claim_id"))
            if not isinstance(parent_id, str):
                continue
            traversed = True
            extra = 1 if _relation_is_inference_only(rel) else 0
            dfs(parent_id, local_seen, chain + [parent_id], hops + extra)

        if not traversed:
            if len(chain) > len(best_chain):
                best_chain = list(chain)
                best_hops = hops

    dfs(claim_id, set(), [claim_id], 0)
    return best_chain, best_hops


def _min_upstream_reliability(
    claim_id: str, claims: Dict[str, Dict[str, Any]], relations: List[Dict[str, Any]]
) -> Optional[int]:
    """
    Compute minimum reliability tier index among upstream basis claims.
    GOVERNANCE_RULE and unknown values are ignored for this decay check.
    """
    parent_map = _build_parent_map(relations)
    min_idx: Optional[int] = None
    visited: Set[str] = set()

    def walk(node: str) -> None:
        nonlocal min_idx
        if node in visited:
            return
        visited.add(node)
        for rel in parent_map.get(node, []):
            parent = _safe_get(rel, "from_claim_id", _safe_get(rel, "parent_claim_id"))
            if not isinstance(parent, str):
                continue
            c = claims.get(parent)
            if c is not None:
                rel_name = _safe_get(c, "reliability")
                if isinstance(rel_name, str) and rel_name in RELIABILITY_TO_INDEX:
                    idx = RELIABILITY_TO_INDEX[rel_name]
                    min_idx = idx if min_idx is None else min(min_idx, idx)
            walk(parent)

    walk(claim_id)
    return min_idx


def _has_direct_anchor_basis(
    claim_id: str, claims: Dict[str, Dict[str, Any]], relations: List[Dict[str, Any]]
) -> bool:
    """
    True if at least one upstream relation/claim path includes anchored basis evidence.
    """
    parent_map = _build_parent_map(relations)
    visited: Set[str] = set()

    def walk(node: str) -> bool:
        if node in visited:
            return False
        visited.add(node)
        # Claim-local marker for anchored evidence.
        c = claims.get(node, {})
        basis_type = _safe_get(c, "basis_type", _safe_get(c, "evidence_mode"))
        if isinstance(basis_type, str) and basis_type in ANCHORED_LABELS:
            return True

        for rel in parent_map.get(node, []):
            if _relation_is_anchored(rel):
                return True
            parent = _safe_get(rel, "from_claim_id", _safe_get(rel, "parent_claim_id"))
            if isinstance(parent, str) and walk(parent):
                return True
        return False

    return walk(claim_id)


def _has_unanchored_inference_chain(
    claim_id: str, claims: Dict[str, Dict[str, Any]], relations: List[Dict[str, Any]]
) -> bool:
    """
    True if there exists at least one upstream chain that contains >=1 inference-only hop
    and never encounters anchored basis evidence.

    This is stricter than checking for absence of any anchor globally; it detects mixed
    lineage where one branch is well-anchored but another branch is inference-only drift.
    """
    parent_map = _build_parent_map(relations)

    def dfs(node: str, seen: Set[str], inference_hops: int, anchored_seen: bool) -> bool:
        if node in seen:
            return False
        local_seen = set(seen)
        local_seen.add(node)

        claim_obj = claims.get(node, {})
        basis_type = _safe_get(claim_obj, "basis_type", _safe_get(claim_obj, "evidence_mode"))
        if isinstance(basis_type, str) and basis_type in ANCHORED_LABELS:
            anchored_seen = True

        incoming = parent_map.get(node, [])
        if not incoming:
            return inference_hops >= 1 and not anchored_seen

        for rel in incoming:
            parent = _safe_get(rel, "from_claim_id", _safe_get(rel, "parent_claim_id"))
            if not isinstance(parent, str):
                continue
            hop_add = 1 if _relation_is_inference_only(rel) else 0
            child_anchored = anchored_seen or _relation_is_anchored(rel)
            if dfs(parent, local_seen, inference_hops + hop_add, child_anchored):
                return True
        return False

    return dfs(claim_id, set(), 0, False)


def check_inference_escalation(
    claim: dict, claims: Dict[str, dict], relations: List[dict]
) -> List[Finding]:
    """
    Reason codes:
      - AEP5_INFERENCE_ESCALATION_NO_ANCHOR
      - AEP5_INFERENCE_HOP_DECAY_WARN

    For PROVEN_RELIABLE claims:
      - fail closed if lineage has inference-only chain and no directly anchored basis
      - warn if terminal reliability exceeds (min upstream + 1 tier)
    """
    findings: List[Finding] = []
    cid = str(_safe_get(claim, "claim_id", _safe_get(claim, "id", "unknown")))
    location = f"claims/{cid}"

    rel = _safe_get(claim, "reliability")
    if rel != "PROVEN_RELIABLE":
        return findings

    chain, hops = compute_inference_lineage(cid, claims, relations)
    has_anchor = _has_direct_anchor_basis(cid, claims, relations)
    has_unanchored_inference_path = _has_unanchored_inference_chain(cid, claims, relations)
    if has_unanchored_inference_path:
        findings.append(
            _mkfinding(
                "AEP5_INFERENCE_ESCALATION_NO_ANCHOR",
                SEVERITY_ERROR,
                f"{REASON_CODES['AEP5_INFERENCE_ESCALATION_NO_ANCHOR']} chain={chain} inference_hops={hops} has_any_anchor={has_anchor}",
                location,
            )
        )

    min_upstream = _min_upstream_reliability(cid, claims, relations)
    terminal_idx = RELIABILITY_TO_INDEX.get("PROVEN_RELIABLE")
    if min_upstream is not None and terminal_idx is not None:
        if terminal_idx > (min_upstream + 1):
            findings.append(
                _mkfinding(
                    "AEP5_INFERENCE_HOP_DECAY_WARN",
                    SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_INFERENCE_HOP_DECAY_WARN']} terminal=PROVEN_RELIABLE min_upstream={min_upstream} inference_hops={hops}",
                    location,
                )
            )
    return findings


# === Schema-Version Polyglot (Attack 7) ===
def _extract_channel(aep_version: str) -> Optional[str]:
    """
    Extract channel token from aep_version string.

    Accepts either the canonical bare semver "0.5" (channel lives in `profile`)
    OR the legacy combined form "aep:0.5/stable" / "aep:0.5/experimental".
    """
    s = str(aep_version).strip()
    if s == "0.5":
        return "stable"  # default channel; profile field disambiguates further
    m = re.fullmatch(r"aep:0\.5/(stable|experimental)", s)
    if m:
        return m.group(1)
    return None


def _extension_affects_reliability(extension: Dict[str, Any]) -> bool:
    """
    Heuristic check for extensions that affect reliability/disposition semantics.
    """
    name = str(_safe_get(extension, "name", "")).lower()
    domain = str(_safe_get(extension, "domain", "")).lower()
    target = str(_safe_get(extension, "target", "")).lower()
    blob = " ".join([name, domain, target])
    return any(token in blob for token in ("reliability", "disposition", "axis_b", "governance", "review"))


def check_schema_version(manifest: dict, profile: str, strict: bool) -> List[Finding]:
    """
    Reason codes:
      - AEP5_SCHEMA_VERSION_INVALID
      - AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH
      - AEP5_EXTENSION_STABILITY_MISSING
      - AEP5_EXTENSION_EXPERIMENTAL_FORBIDDEN

    Rules:
      - aep_version must be one of allowed v0.5 channels
      - requested profile must match manifest channel
      - each extension must declare semantic_stability in {experimental, stable, deprecated}
      - strict stable profile forbids experimental extensions affecting reliability/disposition
    """
    findings: List[Finding] = []
    location = "aepkg.json"
    aep_version = _safe_get(manifest, "aep_version")
    channel = _extract_channel(aep_version if isinstance(aep_version, str) else "")
    if channel is None:
        findings.append(
            _mkfinding(
                "AEP5_SCHEMA_VERSION_INVALID",
                SEVERITY_ERROR,
                f"{REASON_CODES['AEP5_SCHEMA_VERSION_INVALID']} got={aep_version!r}",
                location,
            )
        )
        return findings

    if profile not in VALID_PROFILES:
        findings.append(
            _mkfinding(
                "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH",
                SEVERITY_ERROR if strict else SEVERITY_WARNING,
                f"unknown requested profile={profile}",
                location,
            )
        )
    else:
        # Compare REQUESTED profile against MANIFEST profile (both are full "aep:0.5/<channel>" strings).
        # aep_version is the bare semver "0.5" — channel lives in the profile field.
        manifest_profile = _safe_get(manifest, "profile", "")
        if profile != manifest_profile:
            findings.append(
                _mkfinding(
                    "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH']} requested_profile={profile} manifest_profile={manifest_profile} aep_version={aep_version}",
                    location,
                )
            )

    exts = _safe_get(manifest, "extensions", [])
    # Backward-compatibility note: v0.3/v0.4 used `extensions` as a flat dict of namespaced
    # metadata fields (e.g., implementer:original_sha256, implementer:source_lesson). Those are NOT
    # "extensions" in the v0.5 sense (= structured extension entries with semantic_stability).
    # Skip semantic_stability enforcement for legacy dict-form extensions.
    if isinstance(exts, dict):
        exts = []  # legacy metadata; not subject to v0.5 extension policy
    if not isinstance(exts, list):
        exts = []
    for idx, ext in enumerate(exts):
        if not isinstance(ext, dict):
            continue
        stability = _safe_get(ext, "semantic_stability")
        if stability not in {"experimental", "stable", "deprecated"}:
            findings.append(
                _mkfinding(
                    "AEP5_EXTENSION_STABILITY_MISSING",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_EXTENSION_STABILITY_MISSING']} index={idx}",
                    f"aepkg.json:extensions[{idx}]",
                )
            )
            continue
        if profile == "aep:0.5/stable" and stability == "experimental":
            if _extension_affects_reliability(ext):
                findings.append(
                    _mkfinding(
                        "AEP5_EXTENSION_EXPERIMENTAL_FORBIDDEN",
                        SEVERITY_ERROR if strict else SEVERITY_WARNING,
                        REASON_CODES["AEP5_EXTENSION_EXPERIMENTAL_FORBIDDEN"],
                        f"aepkg.json:extensions[{idx}]",
                    )
                )
    return findings


# === Schema compatibility matrix (Cycle-2 amendment) ===
def check_version_compatibility_records(
    records: Sequence[Dict[str, Any]], location_prefix: str
) -> List[Finding]:
    """
    Reason codes:
      - AEP5_VERSION_CONSUMER_MIN_UNSUPPORTED
      - AEP5_VERSION_PRODUCER_NEWER

    For each record carrying producer_version and/or consumer_min_version:
      - error if validator version < consumer_min_version
      - warning if producer_version > validator version
    """
    findings: List[Finding] = []
    current = _version_tuple(CURRENT_VALIDATOR_VERSION)
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        loc = f"{location_prefix}[{idx}]"
        consumer_min = _safe_get(rec, "consumer_min_version")
        if isinstance(consumer_min, str):
            if current < _version_tuple(consumer_min):
                findings.append(
                    _mkfinding(
                        "AEP5_VERSION_CONSUMER_MIN_UNSUPPORTED",
                        SEVERITY_ERROR,
                        f"{REASON_CODES['AEP5_VERSION_CONSUMER_MIN_UNSUPPORTED']} consumer_min={consumer_min} current={CURRENT_VALIDATOR_VERSION}",
                        loc,
                    )
                )
        producer = _safe_get(rec, "producer_version")
        if isinstance(producer, str):
            if _version_tuple(producer) > current:
                findings.append(
                    _mkfinding(
                        "AEP5_VERSION_PRODUCER_NEWER",
                        SEVERITY_WARNING,
                        f"{REASON_CODES['AEP5_VERSION_PRODUCER_NEWER']} producer={producer} current={CURRENT_VALIDATOR_VERSION}",
                        loc,
                    )
                )
    return findings


# === Sybil Interim Hardening (Attack 8) ===
def compute_reviewer_weights(
    reviews: List[dict], fingerprint_db: Optional[Dict[str, str]] = None
) -> Dict[str, float]:
    """
    Compute per-reviewer weights with interim sybil hardening.

    Base rule:
      verified_identity -> 1.0
      unverified -> 0.5

    Stability rule (if fingerprint_db provided):
      if reviewer fingerprint conflicts with known stable fingerprint, cap weight at 0.25.
      this discourages identity churn across packets.
    """
    weights: Dict[str, float] = {}
    for rev in reviews:
        agent = _safe_get(rev, "reviewer_agent")
        if not isinstance(agent, str) or not agent:
            continue
        verified = bool(_safe_get(rev, "verified_identity", False))
        base = 1.0 if verified else 0.5
        fp = _safe_get(rev, "reviewer_fingerprint")
        if fingerprint_db and isinstance(fp, str) and fp:
            known = fingerprint_db.get(agent)
            if known is not None and known != fp:
                base = min(base, 0.25)
        if agent not in weights:
            weights[agent] = base
        else:
            # Cap per reviewer to avoid duplicate inflation across repeated receipts.
            weights[agent] = max(weights[agent], base)
    return weights


def _claim_reviews(reviews: List[dict], claim_id: str) -> List[dict]:
    """
    Filter reviews associated with claim_id.
    """
    out: List[dict] = []
    for r in reviews:
        if _safe_get(r, "claim_id") == claim_id:
            out.append(r)
    return out


def check_consensus_sybil_resistant(
    claim_id: str, reviews: List[dict], weights: Dict[str, float], strict: bool
) -> List[Finding]:
    """
    Reason codes:
      - AEP5_SYBIL_THRESHOLD_NOT_MET
      - AEP5_SYBIL_UNVERIFIED_ONLY

    For GO consensus:
      - Sum unique reviewer weights.
      - Default threshold is 2.0 weighted units.
      - In strict mode, if threshold can be met only via unverified reviewers, fail closed.
    """
    findings: List[Finding] = []
    claim_revs = _claim_reviews(reviews, claim_id)
    if not claim_revs:
        return findings
    location = f"reviews/{claim_id}"

    threshold = 2.0
    unique_agents: Set[str] = set()
    score = 0.0
    verified_score = 0.0
    for rev in claim_revs:
        agent = _safe_get(rev, "reviewer_agent")
        if not isinstance(agent, str) or not agent:
            continue
        if agent in unique_agents:
            continue
        unique_agents.add(agent)
        w = weights.get(agent, 0.5 if not _safe_get(rev, "verified_identity", False) else 1.0)
        score += w
        if bool(_safe_get(rev, "verified_identity", False)):
            verified_score += w

    only_unverified = verified_score <= 0.0

    if score < threshold:
        sev = SEVERITY_ERROR if (strict and only_unverified) else SEVERITY_WARNING
        findings.append(
            _mkfinding(
                "AEP5_SYBIL_THRESHOLD_NOT_MET",
                sev,
                f"{REASON_CODES['AEP5_SYBIL_THRESHOLD_NOT_MET']} claim={claim_id} score={score:.2f} threshold={threshold:.2f}",
                location,
            )
        )

    if only_unverified:
        sev = SEVERITY_ERROR if (strict and score < threshold) else SEVERITY_WARNING
        findings.append(
            _mkfinding(
                "AEP5_SYBIL_UNVERIFIED_ONLY",
                sev,
                f"{REASON_CODES['AEP5_SYBIL_UNVERIFIED_ONLY']} claim={claim_id} score={score:.2f}",
                location,
            )
        )
    return findings


# === TOCTOU Decision-Time Anchors (Attack 9) ===
def _recent_revalidation_exists(
    claim_id: str, ops_events: List[Dict[str, Any]], now: dt.datetime, max_age_hours: int = 24
) -> bool:
    """
    Returns true if a recent revalidation event exists for claim_id.
    """
    cutoff = now - dt.timedelta(hours=max_age_hours)
    for ev in ops_events:
        if _safe_get(ev, "claim_id") != claim_id:
            continue
        event_type = str(_safe_get(ev, "event_type", _safe_get(ev, "kind", "")))
        if event_type not in {"revalidation_event", "decision_time_revalidation", "revalidated"}:
            continue
        ts = _event_time(ev)
        if ts is not None and ts >= cutoff:
            return True
    return False


def check_decision_time_revalidation(
    claim: dict, ops_events: List[dict], now: dt.datetime, strict: bool
) -> List[Finding]:
    """
    Reason code: AEP5_TOCTOU_STALE_AT_DECISION

    If claim is GO, requires decision-time revalidation, and now > revalidate_after:
      - fail closed if no recent revalidation_event in ops/events
    """
    findings: List[Finding] = []
    cid = str(_safe_get(claim, "claim_id", _safe_get(claim, "id", "unknown")))
    axis_b_action = _safe_get(claim, "axis_b_action", _safe_get(claim, "axis_b"))
    needs = bool(_safe_get(claim, "decision_time_revalidation_required", False))
    revalidate_after = _parse_iso8601_utc(_safe_get(claim, "revalidate_after"))
    if axis_b_action != "GO" or not needs or revalidate_after is None:
        return findings
    if now <= revalidate_after:
        return findings
    if not _recent_revalidation_exists(cid, ops_events, now):
        findings.append(
            _mkfinding(
                "AEP5_TOCTOU_STALE_AT_DECISION",
                SEVERITY_ERROR if strict else SEVERITY_WARNING,
                f"{REASON_CODES['AEP5_TOCTOU_STALE_AT_DECISION']} now={now.isoformat()} revalidate_after={revalidate_after.isoformat()}",
                f"claims/{cid}",
            )
        )
    return findings


# === Execution Inputs Manifest (Attack 10, optional) ===
def _iter_go_claim_input_refs(claim: Dict[str, Any]) -> List[str]:
    """
    Extract side-input references from GO claims using common key conventions.
    """
    refs: List[str] = []
    if _safe_get(claim, "axis_b_action", _safe_get(claim, "axis_b")) != "GO":
        return refs
    for key in ("execution_input_refs", "side_input_refs", "input_refs"):
        val = _safe_get(claim, key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    refs.append(item)
    return refs


def check_execution_inputs(manifest: dict, claims: Dict[str, dict], strict: bool) -> List[Finding]:
    """
    Reason codes:
      - AEP5_EXEC_INPUT_MISSING
      - AEP5_EXEC_INPUT_HASH_MISMATCH
      - AEP5_EXEC_INPUT_SIDE_REFERENCE_UNDECLARED

    Optional check for attack-10 state hash coverage evasion.
    """
    findings: List[Finding] = []
    exec_manifest = _safe_get(manifest, "execution_inputs_manifest")
    if exec_manifest is None:
        return findings

    packet_root = Path(_safe_get(manifest, "_packet_root_hint", "."))
    declared: Dict[str, str] = {}
    if isinstance(exec_manifest, list):
        rows = exec_manifest
    elif isinstance(exec_manifest, dict):
        rows = _safe_get(exec_manifest, "inputs", [])
        if not isinstance(rows, list):
            rows = []
    else:
        rows = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        path = _safe_get(row, "path")
        expected_hash = _safe_get(row, "sha256", _safe_get(row, "hash"))
        if not isinstance(path, str) or not isinstance(expected_hash, str):
            continue
        declared[path] = expected_hash
        abs_path = packet_root / path
        if not abs_path.exists():
            findings.append(
                _mkfinding(
                    "AEP5_EXEC_INPUT_MISSING",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_EXEC_INPUT_MISSING']} path={path}",
                    f"aepkg.json:execution_inputs_manifest[{idx}]",
                )
            )
            continue
        actual = "sha256:" + hashlib.sha256(abs_path.read_bytes()).hexdigest()
        if expected_hash.startswith("sha256:"):
            normalized_expected = expected_hash
        else:
            normalized_expected = "sha256:" + expected_hash
        if actual != normalized_expected:
            findings.append(
                _mkfinding(
                    "AEP5_EXEC_INPUT_HASH_MISMATCH",
                    SEVERITY_ERROR if strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_EXEC_INPUT_HASH_MISMATCH']} path={path} expected={normalized_expected} actual={actual}",
                    f"aepkg.json:execution_inputs_manifest[{idx}]",
                )
            )

    # Heuristic undeclared side-input detection for GO claims.
    for cid, claim in claims.items():
        for ref in _iter_go_claim_input_refs(claim):
            if ref not in declared:
                findings.append(
                    _mkfinding(
                        "AEP5_EXEC_INPUT_SIDE_REFERENCE_UNDECLARED",
                        SEVERITY_WARNING,
                        f"{REASON_CODES['AEP5_EXEC_INPUT_SIDE_REFERENCE_UNDECLARED']} claim={cid} ref={ref}",
                        f"claims/{cid}",
                    )
                )
    return findings


# === Validation orchestration ===
def _load_packet_context(packet_root: Path, config: ValidationConfig) -> V05Context:
    """
    Load all required packet files with strict canonical JSON handling.
    """
    manifest_path = packet_root / "aepkg.json"
    claims_path = packet_root / "claims" / "claims.jsonl"
    relations_path = packet_root / "claims" / "relations.jsonl"
    sources_path = packet_root / "sources" / "sources.jsonl"
    reviews_path = packet_root / "reviews" / "reviews.jsonl"
    events_path = packet_root / "ops" / "events.jsonl"
    lineage_path = packet_root / "ops" / "packet_lineage.json"

    manifest = _read_json(manifest_path)
    claims_list = _read_jsonl(claims_path)
    relations = _read_jsonl(relations_path)
    sources = _read_jsonl(sources_path)
    reviews = _read_jsonl(reviews_path)
    ops_events = _read_jsonl(events_path)
    packet_lineage = _read_json(lineage_path) if lineage_path.exists() else {}

    claims: Dict[str, Dict[str, Any]] = {}
    for idx, claim in enumerate(claims_list):
        cid = _claim_id(claim, idx)
        claims[cid] = claim

    aep_version = _safe_get(manifest, "aep_version", "")
    channel = _extract_channel(aep_version) or "unknown"

    # hint for execution input resolution
    manifest["_packet_root_hint"] = str(packet_root)

    return V05Context(
        packet_root=packet_root,
        manifest=manifest,
        claims=claims,
        claim_list=claims_list,
        relations=relations,
        sources=sources,
        reviews=reviews,
        ops_events=ops_events,
        packet_lineage=packet_lineage,
        config=config,
        channel=channel,
    )


def _severity_rank(severity: str) -> int:
    """
    Sorting severity helper.
    """
    if severity == SEVERITY_ERROR:
        return 0
    if severity == SEVERITY_WARNING:
        return 1
    return 2


def _schema_result_from_findings(findings: List[Finding]) -> str:
    """
    Convert findings to schema_result string.
    """
    for f in findings:
        if getattr(f, "severity", "") == SEVERITY_ERROR:
            return "fail"
    return "pass"


def _validate_profile_and_level(config: ValidationConfig) -> List[Finding]:
    """
    Validate config-level profile/level settings.
    """
    findings: List[Finding] = []
    if config.profile not in VALID_PROFILES:
        findings.append(
            _mkfinding(
                "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH",
                SEVERITY_ERROR,
                f"unsupported profile: {config.profile}",
                "config.profile",
            )
        )
    if config.conformance_level not in {1, 2, 3}:
        findings.append(
            _mkfinding(
                "AEP5_INTERNAL_ERROR",
                SEVERITY_ERROR,
                f"invalid conformance_level: {config.conformance_level}",
                "config.conformance_level",
            )
        )
    return findings


def _collect_manifest_hash_findings(ctx: V05Context) -> List[Finding]:
    """
    Compare strict recomputed manifest hash with declared manifest hash fields.
    """
    findings: List[Finding] = []
    location = "aepkg.json"

    manifest = dict(ctx.manifest)
    # Avoid self-referential field drift if these hashes are embedded.
    declared_manifest_hash = _safe_get(manifest, "manifest_hash")
    declared_state_hash = _safe_get(manifest, "state_hash")
    declared_assets_root = _safe_get(manifest, "assets_merkle_root")

    for transient in ("manifest_hash", "state_hash", "assets_merkle_root", "_packet_root_hint"):
        if transient in manifest:
            manifest.pop(transient, None)

    computed_manifest_hash = manifest_hash_v0_5(manifest)
    if isinstance(declared_manifest_hash, str) and declared_manifest_hash:
        if computed_manifest_hash != declared_manifest_hash:
            findings.append(
                _mkfinding(
                    "AEP5_HASH_MANIFEST_MISMATCH",
                    SEVERITY_ERROR if ctx.config.strict else SEVERITY_WARNING,
                    f"{REASON_CODES['AEP5_HASH_MANIFEST_MISMATCH']} expected={declared_manifest_hash} actual={computed_manifest_hash}",
                    location,
                )
            )

    # Keep values for next checks by reattaching.
    if declared_manifest_hash is not None:
        ctx.manifest["manifest_hash"] = declared_manifest_hash
    if declared_state_hash is not None:
        ctx.manifest["state_hash"] = declared_state_hash
    if declared_assets_root is not None:
        ctx.manifest["assets_merkle_root"] = declared_assets_root
    ctx.manifest["_packet_root_hint"] = str(ctx.packet_root)
    return findings


def _collect_state_hash_findings(ctx: V05Context) -> List[Finding]:
    """
    Compare strict recomputed state hash with declared state hash.
    """
    findings: List[Finding] = []
    declared = _safe_get(ctx.manifest, "state_hash")
    if not isinstance(declared, str) or not declared:
        return findings
    computed = canonical_state_hash_v0_5(ctx.packet_root, DEFAULT_CANONICAL_FILES)
    if computed != declared:
        findings.append(
            _mkfinding(
                "AEP5_HASH_STATE_MISMATCH",
                SEVERITY_ERROR if ctx.config.strict else SEVERITY_WARNING,
                f"{REASON_CODES['AEP5_HASH_STATE_MISMATCH']} expected={declared} actual={computed}",
                "aepkg.json:state_hash",
            )
        )
    return findings


def _collect_merkle_findings(ctx: V05Context) -> List[Finding]:
    """
    Compare AEP-MERKLE-v1 root with declared assets_merkle_root.
    """
    findings: List[Finding] = []
    declared = _safe_get(ctx.manifest, "assets_merkle_root")
    if declared is None:
        return findings
    if not isinstance(declared, str) or not _is_sha256_prefixed(declared):
        findings.append(
            _mkfinding(
                "AEP5_MERKLE_INVALID_FORMAT",
                SEVERITY_ERROR if ctx.config.strict else SEVERITY_WARNING,
                REASON_CODES["AEP5_MERKLE_INVALID_FORMAT"],
                "aepkg.json:assets_merkle_root",
            )
        )
        return findings

    case_policy = _safe_get(ctx.manifest, "path_case_policy", "preserve")
    computed = aep_merkle_v1(ctx.packet_root / "assets", case_policy=case_policy)
    if computed != declared:
        findings.append(
            _mkfinding(
                "AEP5_MERKLE_MISMATCH",
                SEVERITY_ERROR if ctx.config.strict else SEVERITY_WARNING,
                f"{REASON_CODES['AEP5_MERKLE_MISMATCH']} expected={declared} actual={computed}",
                "aepkg.json:assets_merkle_root",
            )
        )
    return findings


def _build_source_index(sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build source_id -> source map.
    """
    idx: Dict[str, Dict[str, Any]] = {}
    for i, src in enumerate(sources):
        sid = _safe_get(src, "source_id", _safe_get(src, "id", f"source[{i}]"))
        if isinstance(sid, str):
            idx[sid] = src
    return idx


def _apply_cycle2_channel_discipline(ctx: V05Context) -> List[Finding]:
    """
    Enforce cycle-2 channel discipline:
      - stable profile: no active experimental features
      - experimental profile: features allowed with warning
    """
    findings: List[Finding] = []
    exts = _safe_get(ctx.manifest, "extensions", [])
    if not isinstance(exts, list):
        return findings
    for idx, ext in enumerate(exts):
        if not isinstance(ext, dict):
            continue
        stability = _safe_get(ext, "semantic_stability")
        active = bool(_safe_get(ext, "active", True))
        if not active:
            continue
        if stability == "experimental":
            if ctx.config.profile == "aep:0.5/stable":
                findings.append(
                    _mkfinding(
                        "AEP5_EXTENSION_EXPERIMENTAL_FORBIDDEN",
                        SEVERITY_ERROR if ctx.config.strict else SEVERITY_WARNING,
                        "stable profile cannot activate experimental extension",
                        f"aepkg.json:extensions[{idx}]",
                    )
                )
            else:
                findings.append(
                    _mkfinding(
                        "AEP5_EXTENSION_EXPERIMENTAL_FORBIDDEN",
                        SEVERITY_WARNING,
                        "experimental profile active; experimental extension enabled",
                        f"aepkg.json:extensions[{idx}]",
                    )
                )
    return findings


def _run_v04_baseline(packet_root: Path) -> List[Finding]:
    """
    Execute v0.4 baseline validator and convert its Findings to v0.5 shape.

    v0.4 Finding(severity, path, message) -> v0.5 Finding(code, severity, message, location).
    """
    try:
        base = validate_v0_4(packet_root)
    except Exception as exc:
        return [
            _mkfinding(
                "AEP5_INTERNAL_ERROR",
                SEVERITY_ERROR,
                f"v0.4 baseline failed: {exc}",
                "validate_v0_4",
            )
        ]
    out: List[Finding] = []
    for item in getattr(base, "findings", []):
        # Translate v0.4 finding shape -> v0.5 shape.
        # v0.4 has (severity, path, message); v0.5 needs (code, severity, message, location).
        # Synthesize a stable code prefix so downstream dedup + sort works.
        sev = getattr(item, "severity", SEVERITY_ERROR)
        path_or_loc = getattr(item, "path", None) or getattr(item, "location", "") or "v0.4"
        msg = getattr(item, "message", str(item))
        code = getattr(item, "code", None) or f"AEP4_BASELINE_{sev.upper()}"
        out.append(_mkfinding(code, sev, msg, path_or_loc))
    return out


def _collect_attack3_findings(ctx: V05Context, now: dt.datetime) -> List[Finding]:
    """
    Cross-packet freshness and packet epoch checks.
    """
    findings: List[Finding] = []
    for claim in ctx.claim_list:
        findings.extend(check_freshness(claim, ctx.ops_events, now, strict=ctx.config.strict))
    findings.extend(
        check_packet_epoch_monotonicity(ctx.manifest, ctx.packet_lineage, strict=ctx.config.strict)
    )
    return findings


def _collect_attack4_findings(ctx: V05Context) -> List[Finding]:
    """
    Anchor trust-context checks.
    """
    findings: List[Finding] = []
    src_idx = _build_source_index(ctx.sources)
    for src in ctx.sources:
        findings.extend(check_anchor_trust_context(src, strict=ctx.config.strict))
    for claim in ctx.claim_list:
        findings.extend(check_claim_anchor_requirements(claim, src_idx, strict=ctx.config.strict))
    return findings


def _collect_attack5_findings(ctx: V05Context) -> List[Finding]:
    """
    GO/GOVERNANCE_RULE coupling checks.
    """
    findings: List[Finding] = []
    for claim in ctx.claim_list:
        findings.extend(check_go_disposition_coupling(claim, ctx.claims, ctx.reviews))
    return findings


def _collect_attack6_findings(ctx: V05Context) -> List[Finding]:
    """
    Inference hop decay checks.
    """
    findings: List[Finding] = []
    for claim in ctx.claim_list:
        findings.extend(check_inference_escalation(claim, ctx.claims, ctx.relations))
    return findings


def _collect_attack8_findings(ctx: V05Context) -> List[Finding]:
    """
    Sybil interim hardening checks.
    """
    findings: List[Finding] = []
    weights = compute_reviewer_weights(ctx.reviews, fingerprint_db=ctx.config.fingerprint_db)
    for claim in ctx.claim_list:
        axis_b_action = _safe_get(claim, "axis_b_action", _safe_get(claim, "axis_b"))
        if axis_b_action != "GO":
            continue
        cid = str(_safe_get(claim, "claim_id", _safe_get(claim, "id", "unknown")))
        findings.extend(
            check_consensus_sybil_resistant(
                cid, ctx.reviews, weights=weights, strict=ctx.config.strict
            )
        )
    return findings


def _collect_attack9_findings(ctx: V05Context, now: dt.datetime) -> List[Finding]:
    """
    TOCTOU decision-time revalidation checks.
    """
    findings: List[Finding] = []
    for claim in ctx.claim_list:
        findings.extend(
            check_decision_time_revalidation(
                claim, ctx.ops_events, now=now, strict=ctx.config.strict
            )
        )
    return findings


def _collect_attack10_findings(ctx: V05Context) -> List[Finding]:
    """
    Optional execution input coverage checks.
    """
    if ctx.config.conformance_level < CONFORMANCE_LEVEL_3:
        return []
    return check_execution_inputs(ctx.manifest, ctx.claims, strict=ctx.config.strict)


def _collect_version_matrix_findings(ctx: V05Context) -> List[Finding]:
    """
    Run schema compatibility matrix checks across manifest + records.
    """
    findings: List[Finding] = []
    findings.extend(check_version_compatibility_records([ctx.manifest], "aepkg.json"))
    findings.extend(check_version_compatibility_records(ctx.claim_list, "claims/claims.jsonl"))
    findings.extend(check_version_compatibility_records(ctx.relations, "claims/relations.jsonl"))
    findings.extend(check_version_compatibility_records(ctx.sources, "sources/sources.jsonl"))
    findings.extend(check_version_compatibility_records(ctx.reviews, "reviews/reviews.jsonl"))
    findings.extend(check_version_compatibility_records(ctx.ops_events, "ops/events.jsonl"))
    return findings


def _dedupe_findings(findings: List[Finding]) -> List[Finding]:
    """
    Remove exact duplicate findings while preserving deterministic order.
    """
    seen: Set[Tuple[str, str, str, str]] = set()
    out: List[Finding] = []
    for f in findings:
        key = (
            str(getattr(f, "code", "")),
            str(getattr(f, "severity", "")),
            str(getattr(f, "location", "")),
            str(getattr(f, "message", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    out.sort(key=lambda x: (_severity_rank(x.severity), x.code, x.location, x.message))
    return out


def _guard_jsonschema_presence(findings: List[Finding]) -> None:
    """
    Touch jsonschema import so runtime packaging failures are surfaced as findings.
    """
    try:
        _ = ValidationError
    except Exception as exc:  # pragma: no cover
        findings.append(
            _mkfinding(
                "AEP5_INTERNAL_ERROR",
                SEVERITY_ERROR,
                f"jsonschema import failure: {exc}",
                "module-import",
            )
        )


def validate_v0_5(packet_root: Path, config: Optional[ValidationConfig] = None) -> ValidationResult:
    """
    Main entrypoint.

    Execution pipeline:
      1. Run v0.4 baseline validator (backward compatibility)
      2. Load strict-canonical packet objects
      3. Enforce schema-version profile/channel and cycle-2 discipline
      4. Recompute strict state/manifest hashes (Attack 1 closure)
      5. Recompute AEP-MERKLE-v1 assets root (Attack 2 closure)
      6. Run per-claim and packet checks for attacks 3..10
      7. Aggregate findings and compute pass/fail
    """
    config = config or ValidationConfig()
    now = _ensure_utc(config.now)
    findings: List[Finding] = []

    # Validate runtime config early.
    findings.extend(_validate_profile_and_level(config))
    if _schema_result_from_findings(findings) == "fail":
        return ValidationResult(findings=_dedupe_findings(findings), schema_result="fail")

    # Baseline v0.4 checks — ONLY run if packet declares v0.3/v0.4 (compat mode).
    # v0.5 packets use v0.5-specific algorithms (strict-canonical state_hash, AEP-MERKLE-v1)
    # which v0.4 baseline would incorrectly flag as mismatches.
    try:
        _peek_manifest_text = (packet_root / "aepkg.json").read_text(encoding="utf-8")
        _peek_manifest = json.loads(_peek_manifest_text)
        _peek_version = str(_peek_manifest.get("aep_version", ""))
    except Exception:
        _peek_version = ""
    if _peek_version in {"", "0.3", "0.4"}:
        findings.extend(_run_v04_baseline(packet_root))

    # Ensure jsonschema import works in runtime environment.
    _guard_jsonschema_presence(findings)

    # Load packet context with strict parsing.
    try:
        ctx = _load_packet_context(packet_root, config)
    except Exception as exc:
        findings.append(
            _mkfinding(
                "AEP5_JSON_INVALID",
                SEVERITY_ERROR,
                f"strict packet parse failed: {exc}",
                str(packet_root),
            )
        )
        return ValidationResult(findings=_dedupe_findings(findings), schema_result="fail")

    # Attack 7 + channel discipline.
    findings.extend(check_schema_version(ctx.manifest, config.profile, strict=config.strict))
    findings.extend(_apply_cycle2_channel_discipline(ctx))

    # Compatibility matrix.
    findings.extend(_collect_version_matrix_findings(ctx))

    # Attack 1 hashes.
    findings.extend(_collect_manifest_hash_findings(ctx))
    findings.extend(_collect_state_hash_findings(ctx))

    # Attack 2 Merkle replacement.
    findings.extend(_collect_merkle_findings(ctx))

    # Attack 3 freshness + epoch.
    if config.conformance_level >= CONFORMANCE_LEVEL_2:
        findings.extend(_collect_attack3_findings(ctx, now))

    # Attack 4 anchor trust context.
    if config.conformance_level >= CONFORMANCE_LEVEL_2:
        findings.extend(_collect_attack4_findings(ctx))

    # Attack 5 GO/governance coupling.
    if config.conformance_level >= CONFORMANCE_LEVEL_2:
        findings.extend(_collect_attack5_findings(ctx))

    # Attack 6 inference hop decay.
    if config.conformance_level >= CONFORMANCE_LEVEL_2:
        findings.extend(_collect_attack6_findings(ctx))

    # Attack 8 sybil interim hardening.
    if config.conformance_level >= CONFORMANCE_LEVEL_2:
        findings.extend(_collect_attack8_findings(ctx))

    # Attack 9 decision-time TOCTOU.
    if config.conformance_level >= CONFORMANCE_LEVEL_2:
        findings.extend(_collect_attack9_findings(ctx, now))

    # Attack 10 optional manifest coverage.
    findings.extend(_collect_attack10_findings(ctx))

    # Additional informational channel finding for visibility.
    findings.append(
        _mkfinding(
            "AEP5_SCHEMA_PROFILE_CHANNEL_MISMATCH" if ctx.channel == "unknown" else "AEP5_CHANNEL_INFO",
            SEVERITY_INFO,
            f"{REASON_CODES['AEP5_CHANNEL_INFO']} validator_channel={ctx.channel} profile={config.profile} conformance_level={config.conformance_level}",
            "aepkg.json:aep_version",
        )
    )

    findings = _dedupe_findings(findings)
    schema_result = _schema_result_from_findings(findings)
    return ValidationResult(findings=findings, schema_result=schema_result)


def _format_finding_for_cli(f: Finding) -> str:
    """
    Render finding as tab-separated single line.
    """
    return f"{f.severity}\t{f.code}\t{f.location}\t{f.message}"


def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI entrypoint for standalone invocation.
    """
    parser = argparse.ArgumentParser(
        prog="aep.validate_v0_5",
        description="AEP v0.5 reference validator (strict fail-closed profile).",
    )
    parser.add_argument("packet_root", type=Path)
    parser.add_argument(
        "--profile",
        default="aep:0.5/stable",
        choices=sorted(VALID_PROFILES),
        help="Validation profile channel.",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=DEFAULT_CONFORMANCE_LEVEL,
        choices=[1, 2, 3],
        help="Conformance level.",
    )
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        default=True,
        help="Enable strict fail-closed behavior (default).",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Disable strict fail-closed behavior for exploratory validation.",
    )
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="Override current UTC time in ISO8601 format.",
    )
    args = parser.parse_args(argv)

    now_override = _parse_iso8601_utc(args.now) if args.now else None
    if args.now and now_override is None:
        print("error\tAEP5_FRESHNESS_INVALID_TIME\tconfig.now\tInvalid --now timestamp", file=sys.stderr)
        return 2

    config = ValidationConfig(
        profile=args.profile,
        conformance_level=args.level,
        strict=args.strict,
        now=now_override,
    )
    result = validate_v0_5(args.packet_root, config=config)
    for finding in result.findings:
        print(_format_finding_for_cli(finding))
    return 0 if result.schema_result == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

# <END_OF_VALIDATE_V0_5_PY>
