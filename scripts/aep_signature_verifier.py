#!/usr/bin/env python3
"""aep_signature_verifier.py — Wave-030 standalone Ed25519 receipt verifier.

Reads a receipt line (or the latest from .claude/_logs/aep-runtime-receipts.jsonl)
and verifies its `predicate.aep.signature.ed25519_b64` against the public key
at `doctrine/_anchors/agent-signing-public.pem`.

Usage:
  python aep_signature_verifier.py                       # verify LAST receipt in ledger
  python aep_signature_verifier.py --line N              # verify receipt N (1-indexed)
  python aep_signature_verifier.py --stdin               # read receipt JSON from stdin
  python aep_signature_verifier.py --pubkey-info         # print pubkey sha256 + exit

Exit codes:
  0  signature VALID
  1  signature INVALID (verification failed)
  2  receipt MISSING signature field (unsigned)
  3  infrastructure error (key file missing, cryptography import fail, etc.)

Per Wave-030 sibling-126 — this CLI verifier IS the v1.0.0-rc1 "demonstrated" path
for D5 metric (signed-receipt presence). Demonstrates that a signed receipt CAN BE
verified standalone, not just by the producing process.

Composes with: §41 HCRL (chain extends to signed envelopes), §69.1 verification-law,
§70 surface-mirror, §V80-9-bis-11 1000x metric D5.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any, Dict, Optional


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
RECEIPTS_LEDGER = REPO_ROOT / ".claude" / "_logs" / "aep-runtime-receipts.jsonl"
PUBKEY_PATH = REPO_ROOT / "doctrine" / "_anchors" / "agent-signing-public.pem"


def load_pubkey():
    """Load Ed25519 pubkey from doctrine/_anchors/agent-signing-public.pem."""
    if not PUBKEY_PATH.exists():
        return None
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        return load_pem_public_key(PUBKEY_PATH.read_bytes())
    except Exception:
        return None


def pubkey_sha256(pub_key) -> Optional[str]:
    try:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        raw = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        return None


def verify_receipt(receipt: Dict[str, Any], pub_key) -> Dict[str, Any]:
    """Verify Ed25519 signature on receipt. Returns {verified, reason, fingerprint_match, ...}"""
    sig_info = (receipt.get("predicate") or {}).get("aepkit", {}).get("signature")
    if sig_info is None:
        return {"verified": False, "reason": "unsigned_receipt_no_signature_field", "exit_code": 2}
    sig_b64 = sig_info.get("ed25519_b64")
    if not sig_b64:
        return {"verified": False, "reason": "signature_field_missing_ed25519_b64", "exit_code": 2}

    # Reconstruct canonical envelope-minus-signature
    stmt_copy = copy.deepcopy(receipt)
    del stmt_copy["predicate"]["aepkit"]["signature"]
    # Wave-038: dispatch on canonical_protocol field to support both legacy json.dumps
    # (spec_version 1.0) AND new JCS RFC 8785 (spec_version 1.1)
    protocol = sig_info.get("canonical_protocol", "")
    if "jcs" in protocol.lower():
        try:
            import jcs as jcs_lib
            canonical_bytes = jcs_lib.canonicalize(stmt_copy)
        except ImportError:
            return {"verified": False, "reason": "jcs_library_missing_for_protocol_jcs_rfc8785",
                    "exit_code": 3}
    else:
        canonical_bytes = json.dumps(stmt_copy, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode("utf-8")

    try:
        sig_bytes = base64.b64decode(sig_b64)
        pub_key.verify(sig_bytes, canonical_bytes)
        # Verify pubkey fingerprint matches
        declared_fp = sig_info.get("pubkey_sha256")
        actual_fp = pubkey_sha256(pub_key)
        fp_match = (declared_fp == actual_fp)
        return {
            "verified": True,
            "reason": "ed25519_signature_valid",
            "fingerprint_declared": declared_fp,
            "fingerprint_actual": actual_fp,
            "fingerprint_match": fp_match,
            "signed_at": sig_info.get("signed_at"),
            "canonical_protocol": sig_info.get("canonical_protocol"),
            "canonical_bytes_signed": len(canonical_bytes),
            "exit_code": 0 if fp_match else 1,
        }
    except Exception as e:
        from cryptography.exceptions import InvalidSignature
        if isinstance(e, InvalidSignature):
            return {"verified": False, "reason": "ed25519_signature_INVALID_does_not_match_canonical_envelope",
                    "fingerprint_declared": sig_info.get("pubkey_sha256"), "exit_code": 1}
        return {"verified": False, "reason": f"verification_exception_{type(e).__name__}", "exit_code": 3}


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave-030 standalone Ed25519 receipt verifier")
    parser.add_argument("--line", type=int, help="Receipt line number to verify (1-indexed)")
    parser.add_argument("--stdin", action="store_true", help="Read receipt JSON from stdin")
    parser.add_argument("--pubkey-info", action="store_true", help="Print pubkey sha256 + exit")
    args = parser.parse_args()

    pub = load_pubkey()
    if pub is None:
        print("aep_signature_verifier: cannot load pubkey from "
              + str(PUBKEY_PATH.relative_to(REPO_ROOT)), file=sys.stderr)
        return 3

    if args.pubkey_info:
        print(f"pubkey_path:    {PUBKEY_PATH.relative_to(REPO_ROOT)}")
        print(f"pubkey_sha256:  {pubkey_sha256(pub)}")
        return 0

    if args.stdin:
        receipt = json.loads(sys.stdin.read())
    else:
        if not RECEIPTS_LEDGER.exists():
            print("aep_signature_verifier: receipts ledger does not exist", file=sys.stderr)
            return 3
        lines = [ln for ln in RECEIPTS_LEDGER.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            print("aep_signature_verifier: receipts ledger is empty", file=sys.stderr)
            return 3
        idx = args.line if args.line else len(lines)
        if idx < 1 or idx > len(lines):
            print(f"aep_signature_verifier: line {idx} out of range (1..{len(lines)})", file=sys.stderr)
            return 3
        receipt = json.loads(lines[idx - 1])

    result = verify_receipt(receipt, pub)
    subj_name = ((receipt.get("subject") or [{}])[0] or {}).get("name", "?")
    print(f"=== Wave-030 Ed25519 receipt verification ===")
    print(f"  subject:               {subj_name}")
    print(f"  verified:              {result['verified']}")
    print(f"  reason:                {result['reason']}")
    if result.get("fingerprint_declared"):
        print(f"  fingerprint_declared:  {result['fingerprint_declared']}")
        print(f"  fingerprint_actual:    {result.get('fingerprint_actual', 'N/A')}")
        print(f"  fingerprint_match:     {result.get('fingerprint_match', False)}")
    if result.get("canonical_protocol"):
        print(f"  canonical_protocol:    {result['canonical_protocol']}")
        print(f"  canonical_bytes:       {result.get('canonical_bytes_signed', 0)}")
    print(f"  exit_code:             {result['exit_code']}")
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
