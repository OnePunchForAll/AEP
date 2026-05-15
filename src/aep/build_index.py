"""build_index.py — Apache-2.0 — AEP v0.6 embedded index builder.

Implements `cache/index.bin` per AEP_v0_6_SPEC.md §V60-4.

Format: 48-byte fixed-width records, sorted by claim_id_sha256 ascending.
  0-31  : claim_id_sha256 (32 bytes, raw sha256 of canonical claim_id string)
  32-39 : byte_offset (u64 LE) — offset in data/claims.jsonl
  40-43 : byte_length (u32 LE) — record byte length
  44-47 : enum_bitfield (u32 LE) — reliability/scope/axis_b/status packed

Companion metadata at cache/index.meta.json.
Integrity: aepkg.json.integrity.index_hash = sha256(cache/index.bin).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import struct
from pathlib import Path
from typing import Dict, List, Tuple


from aep.jsonl_compact import (
    RELIABILITY_TO_CODE,
    SCOPE_TO_CODE,
    AXIS_B_TO_CODE,
    STATUS_TO_CODE,
)


# Enum → bitfield encoding (per spec §V60-4).
RELIABILITY_BITS = {
    "PROVEN_RELIABLE": 0b0001,
    "STRONGLY_PLAUSIBLE": 0b0010,
    "PLAUSIBLE": 0b0011,
    "EXPERIMENTAL": 0b0100,
    "ASSUMPTION": 0b0101,
    "SPECULATIVE_FRONTIER": 0b0110,
    "CONFLICTED": 0b0111,
    "GOVERNANCE_RULE": 0b1000,
    "DANGEROUS_NOT_WORTH_DOING": 0b1001,
    "UNKNOWN": 0b1010,
}
SCOPE_BITS = {
    "LOCAL_OBSERVATION": 0b01,
    "CONTEXT_BOUND_PATTERN": 0b10,
    "GENERAL_CLAIM": 0b11,
}
AXIS_B_BITS = {
    "GO": 0b001,
    "EXPERIMENT": 0b010,
    "EXPLORE": 0b011,
    "HALT": 0b100,
    "FORBIDDEN": 0b101,
}
STATUS_BITS = {
    "active": 0b01,
    "superseded": 0b10,
    "rejected": 0b11,
    "needs_review": 0b00,
}


def _enum_bitfield(reliability: str, scope: str, axis_b: str, status: str) -> int:
    """Pack enum values into a u32 bitfield.

    Layout (LSB → MSB):
      bits 0-3:   reliability (4 bits)
      bits 4-5:   scope (2 bits)
      bits 6-8:   axis_b_action (3 bits)
      bits 9-10:  status (2 bits)
      bits 11-31: reserved (zero)
    """
    return (
        (RELIABILITY_BITS.get(reliability, 0) & 0b1111)
        | ((SCOPE_BITS.get(scope, 0) & 0b11) << 4)
        | ((AXIS_B_BITS.get(axis_b, 0) & 0b111) << 6)
        | ((STATUS_BITS.get(status, 0) & 0b11) << 9)
    )


def build_index(packet_root: Path) -> Tuple[bytes, Dict, str]:
    """Build the binary index for an AEP packet.

    Returns (index_bytes, index_meta_dict, sha256_hex_of_index_bytes).
    """
    claims_path = packet_root / "data" / "claims.jsonl"
    if not claims_path.exists():
        # Empty index for zero-claim packets.
        empty_meta = {
            "index_version": "v0.6.0",
            "record_size_bytes": 48,
            "claim_count": 0,
            "sort_order": "claim_id_sha256_ascending",
            "built_at": (
                dt.datetime.now(tz=dt.timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
            "builder": "aep.build_index v0.6.0",
        }
        empty_hash = "sha256:" + hashlib.sha256(b"").hexdigest()
        return b"", empty_meta, empty_hash

    raw = claims_path.read_bytes()
    records: List[Tuple[bytes, int, int, int]] = []
    offset = 0
    for line in raw.split(b"\n"):
        if not line.strip():
            offset += len(line) + 1  # account for newline
            continue
        try:
            claim = json.loads(line)
        except json.JSONDecodeError:
            offset += len(line) + 1
            continue
        claim_id = claim.get("id", "")
        if not isinstance(claim_id, str):
            offset += len(line) + 1
            continue
        claim_id_hash = hashlib.sha256(claim_id.encode("utf-8")).digest()
        record_bytes = len(line)
        bitfield = _enum_bitfield(
            claim.get("reliability", ""),
            claim.get("scope", ""),
            claim.get("axis_b_action", ""),
            claim.get("status", ""),
        )
        records.append((claim_id_hash, offset, record_bytes, bitfield))
        offset += len(line) + 1  # +1 for the newline

    # Sort by claim_id_sha256 ascending for binary search.
    records.sort(key=lambda r: r[0])

    # Serialize.
    buf = bytearray()
    for claim_id_hash, byte_offset, byte_length, bitfield in records:
        buf.extend(claim_id_hash)  # 32 bytes
        buf.extend(struct.pack("<Q", byte_offset))  # 8 bytes LE u64
        buf.extend(struct.pack("<I", byte_length))  # 4 bytes LE u32
        buf.extend(struct.pack("<I", bitfield))  # 4 bytes LE u32

    index_bytes = bytes(buf)
    index_hash = "sha256:" + hashlib.sha256(index_bytes).hexdigest()
    meta = {
        "index_version": "v0.6.0",
        "record_size_bytes": 48,
        "claim_count": len(records),
        "sort_order": "claim_id_sha256_ascending",
        "enum_bitfield_layout": {
            "reliability_bits": [0, 4],
            "scope_bits": [4, 6],
            "axis_b_action_bits": [6, 9],
            "status_bits": [9, 11],
        },
        "built_at": (
            dt.datetime.now(tz=dt.timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        ),
        "builder": "aep.build_index v0.6.0",
    }
    return index_bytes, meta, index_hash


def write_index(packet_root: Path) -> str:
    """Build and write the index files into the packet. Returns the index_hash."""
    cache_dir = packet_root / "cache"
    cache_dir.mkdir(exist_ok=True)
    index_bytes, meta, index_hash = build_index(packet_root)
    (cache_dir / "index.bin").write_bytes(index_bytes)
    (cache_dir / "index.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return index_hash


def verify_index(packet_root: Path) -> Tuple[bool, str]:
    """Recompute the index and verify against stored cache/index.bin.

    Returns (matches, computed_hash).
    """
    cache_path = packet_root / "cache" / "index.bin"
    if not cache_path.exists():
        return True, "sha256:" + hashlib.sha256(b"").hexdigest()
    stored = cache_path.read_bytes()
    stored_hash = "sha256:" + hashlib.sha256(stored).hexdigest()
    rebuilt_bytes, _, rebuilt_hash = build_index(packet_root)
    return (stored_hash == rebuilt_hash and stored == rebuilt_bytes), stored_hash


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m aep.build_index <packet_root>")
        sys.exit(2)
    root = Path(sys.argv[1])
    h = write_index(root)
    print(f"Index built: {h}")
