"""jsonl_compact.py — Apache-2.0 — AEP v0.6 compact JSONL encoder/decoder.

Implements `aep:0.6/jsonl-compact` profile per AEP_v0_6_SPEC.md §V60-3.

Roundtrip invariant: `pretty_canonicalize(decode(encode(record)))` MUST equal
`pretty_canonicalize(record)` for every valid AEP record.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

# Dictionary tables per spec §V60-3.

RELIABILITY_TO_CODE: Dict[str, str] = {
    "PROVEN_RELIABLE": "R",
    "STRONGLY_PLAUSIBLE": "S",
    "PLAUSIBLE": "P",
    "EXPERIMENTAL": "E",
    "ASSUMPTION": "A",
    "SPECULATIVE_FRONTIER": "F",
    "CONFLICTED": "C",
    "GOVERNANCE_RULE": "G",
    "DANGEROUS_NOT_WORTH_DOING": "D",
    "UNKNOWN": "U",
}
RELIABILITY_FROM_CODE: Dict[str, str] = {v: k for k, v in RELIABILITY_TO_CODE.items()}

SCOPE_TO_CODE: Dict[str, str] = {
    "LOCAL_OBSERVATION": "L",
    "CONTEXT_BOUND_PATTERN": "B",
    "GENERAL_CLAIM": "G",
}
SCOPE_FROM_CODE: Dict[str, str] = {v: k for k, v in SCOPE_TO_CODE.items()}

AXIS_B_TO_CODE: Dict[str, str] = {
    "GO": "O",
    "EXPERIMENT": "X",
    "EXPLORE": "E",
    "HALT": "H",
    "FORBIDDEN": "F",
}
AXIS_B_FROM_CODE: Dict[str, str] = {v: k for k, v in AXIS_B_TO_CODE.items()}

STATUS_TO_CODE: Dict[str, str] = {
    "active": "a",
    "superseded": "s",
    "rejected": "r",
    "needs_review": "n",
}
STATUS_FROM_CODE: Dict[str, str] = {v: k for k, v in STATUS_TO_CODE.items()}

# Field-encoded mapping: top-level field name → (encoder, decoder)
_FIELD_ENCODERS: Dict[str, Tuple[Dict[str, str], Dict[str, str]]] = {
    "reliability": (RELIABILITY_TO_CODE, RELIABILITY_FROM_CODE),
    "scope": (SCOPE_TO_CODE, SCOPE_FROM_CODE),
    "axis_b_action": (AXIS_B_TO_CODE, AXIS_B_FROM_CODE),
    "status": (STATUS_TO_CODE, STATUS_FROM_CODE),
}


# ============ Encode (canonical → compact) ============


def encode_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Encode one canonical record into compact form (in place rewrite of mutable copy)."""
    out: Dict[str, Any] = {}
    for k, v in record.items():
        if k in _FIELD_ENCODERS and isinstance(v, str):
            encode_map = _FIELD_ENCODERS[k][0]
            out[k] = encode_map.get(v, v)
        else:
            out[k] = v
    return out


def encode_jsonl_line(record: Dict[str, Any]) -> str:
    """Encode a canonical record to one compact JSONL line (sorted keys, no whitespace)."""
    encoded = encode_record(record)
    return json.dumps(encoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encode_jsonl_file(records: List[Dict[str, Any]]) -> bytes:
    """Encode a list of records into a complete compact JSONL byte string (LF terminated)."""
    lines = [encode_jsonl_line(r) for r in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


# ============ Decode (compact → canonical) ============


def decode_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Decode one compact record into canonical form."""
    out: Dict[str, Any] = {}
    for k, v in record.items():
        if k in _FIELD_ENCODERS and isinstance(v, str):
            decode_map = _FIELD_ENCODERS[k][1]
            # Reject non-ASCII characters in code position (Unicode lookalike defense).
            if not v.isascii():
                raise ValueError(
                    f"AEP60_COMPACT_ENUM_NON_ASCII: field {k!r} code {v!r} contains non-ASCII"
                )
            if v in decode_map:
                out[k] = decode_map[v]
            elif v in (_FIELD_ENCODERS[k][0]):
                # already canonical form; leave as-is (pretty mode)
                out[k] = v
            else:
                # Unknown code: pass through (preserve forward-compat) but flag-able.
                out[k] = v
        else:
            out[k] = v
    return out


def decode_jsonl_line(line: str) -> Dict[str, Any]:
    """Decode one compact JSONL line into canonical record dict."""
    obj = json.loads(line)
    return decode_record(obj)


def decode_jsonl_bytes(payload: bytes) -> List[Dict[str, Any]]:
    """Decode a complete compact JSONL byte string into a list of canonical records."""
    text = payload.decode("utf-8")
    out: List[Dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        out.append(decode_jsonl_line(line))
    return out


# ============ Roundtrip verification ============


def verify_roundtrip(records: List[Dict[str, Any]]) -> bool:
    """Encode records → decode → compare. MUST be byte-identical to canonical pretty form."""
    encoded = encode_jsonl_file(records)
    decoded = decode_jsonl_bytes(encoded)
    if len(decoded) != len(records):
        return False
    for orig, rt in zip(records, decoded):
        # Compare canonical-JSON sorted-key form.
        a = json.dumps(orig, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        b = json.dumps(rt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if a != b:
            return False
    return True
