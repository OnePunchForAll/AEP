"""verification_receipt.py — Apache-2.0 — AEP v0.6.1 verification_receipt_v1.

Implements SP-R8-03 (verification receipt schema) from knowledge-run-1.

Every call to validate_v0_6 can optionally emit a structured receipt to an
append-only JSONL log per §41 HCRL discipline. Receipts are:

  - append-only (no row mutation)
  - hash-chained (prev_receipt_hash links each receipt to the prior one)
  - cross-runtime-portable (canonical sorted-keys JSON)
  - queryable by packet_sha256 + verifier_id + timestamp

Schema fields (all required unless marked optional):
  schema: "aep.verification_receipt.v1"
  receipt_id: UUIDv7 string
  packet_id: aepkg: URN string
  packet_sha256: 64-hex string (sha256 over canonical packet bytes)
  verifier_id: FQN string ("aep.validate_v0_6")
  verifier_version: semver string
  profile: enum (one of VALID_PROFILES_V0_6)
  conformance_level: integer 1|2|3
  strict: boolean
  schema_result: enum pass|warn|fail
  finding_codes: array of AEPxx_* reason codes (may be empty)
  finding_severities: array of {code, severity, location} objects
  timestamp: RFC 3339 UTC string
  runtime: {language, version, os} object — optional
  prev_receipt_hash: sha256 of prior receipt in this log — optional
  signer: signing block — optional v0.8+
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "aep.verification_receipt.v1"


def _uuidv7() -> str:
    """Generate a UUIDv7 (time-ordered). Falls back to UUIDv4 if stdlib lacks v7."""
    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())
    # Manual UUIDv7: 48 bits unix-ms timestamp + 12 bits random + 4 bits version + 62 bits random
    ts_ms = int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF  # 12 bits
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFF_FFFF_FFFF_FFFF  # 62 bits
    # Layout: ts_ms (48b) | ver=0111 (4b) | rand_a (12b) | var=10 (2b) | rand_b (62b)
    u128 = (ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    hex_str = f"{u128:032x}"
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"


def compute_packet_sha256(packet_root: Path, canonical_files: List[str]) -> str:
    """Compute deterministic packet content hash.

    Concatenates aepkg.json + sorted canonical_files in order, separated by
    newlines, then sha256. Streaming-safe; suitable for large packets.
    """
    h = hashlib.sha256()
    aepkg = packet_root / "aepkg.json"
    if aepkg.exists():
        with open(aepkg, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        h.update(b"\n")
    for rel in sorted(canonical_files):
        target = packet_root / rel
        if target.exists():
            with open(target, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            h.update(b"\n")
    return "sha256:" + h.hexdigest()


def build_receipt(
    packet_root: Path,
    packet_id: Optional[str],
    canonical_files: List[str],
    verifier_id: str,
    verifier_version: str,
    profile: str,
    conformance_level: int,
    strict: bool,
    schema_result: str,
    findings: List[Any],
    prev_receipt_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a verification_receipt_v1 dict."""
    finding_codes: List[str] = []
    finding_details: List[Dict[str, str]] = []
    for f in findings:
        code = getattr(f, "code", "")
        sev = getattr(f, "severity", "")
        loc = getattr(f, "location", "")
        if code:
            finding_codes.append(code)
            finding_details.append({"code": code, "severity": sev, "location": loc})
    packet_sha256 = compute_packet_sha256(packet_root, canonical_files)
    receipt: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "receipt_id": _uuidv7(),
        "packet_id": packet_id or "<unknown>",
        "packet_sha256": packet_sha256,
        "verifier_id": verifier_id,
        "verifier_version": verifier_version,
        "profile": profile,
        "conformance_level": conformance_level,
        "strict": strict,
        "schema_result": schema_result,
        "finding_codes": finding_codes,
        "finding_severities": finding_details,
        "timestamp": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "runtime": {
            "language": "python",
            "version": platform.python_version(),
            "os": platform.system(),
        },
    }
    if prev_receipt_hash:
        receipt["prev_receipt_hash"] = prev_receipt_hash
    return receipt


def receipt_sha256(receipt: Dict[str, Any]) -> str:
    """Compute canonical sha256 of a receipt for chaining."""
    canonical = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def emit_receipt(receipt: Dict[str, Any], log_path: Path) -> str:
    """Append-only emit a receipt to the JSONL log. Returns receipt's own sha256."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    canonical = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # O_APPEND + fsync for crash-safety
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(str(log_path), flags, 0o644)
    try:
        os.write(fd, (canonical + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return receipt_sha256(receipt)


def last_receipt_hash(log_path: Path) -> Optional[str]:
    """Return sha256 of the most recent receipt in the log, or None if empty."""
    if not log_path.exists():
        return None
    last_line: Optional[str] = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line.strip()
    if not last_line:
        return None
    try:
        receipt = json.loads(last_line)
        return receipt_sha256(receipt)
    except Exception:
        return None


def verify_chain(log_path: Path) -> bool:
    """Verify the prev_receipt_hash chain is intact."""
    if not log_path.exists():
        return True
    prev_hash: Optional[str] = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                receipt = json.loads(line)
            except json.JSONDecodeError:
                return False
            claimed_prev = receipt.get("prev_receipt_hash")
            if prev_hash is not None:
                if claimed_prev != prev_hash:
                    return False
            else:
                if claimed_prev is not None:
                    # First receipt should not claim a prev_receipt_hash
                    return False
            prev_hash = receipt_sha256(receipt)
    return True
