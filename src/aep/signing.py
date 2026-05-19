"""signing.py — Apache-2.0 — AEP v0.7-rc1 Ed25519 signing lane.

Implements `aep:0.7/signed` profile per SP-R8-02 + warden H1+H2 + curator
LAW-V1-C from knowledge-run-1. Signing is OPTIONAL — packets without
signature still validate under non-signed profiles. Identity gap surfaced
in v0.6.1 via AEP61_IDENTITY_UNAUTHENTICATED INFO finding is closed when a
v0.7-signed packet is verified.

Signature design (closes operator-bundle TRIPLE-converged "No Self-Signature
in Signed Bytes" law):

  1. BODY (data/* + canonical_files) is hashed → state_hash (already in v0.6).
  2. ENVELOPE (aepkg.json with manifest_hash AND signatures field both
     EXCLUDED from manifest_hash basis) is hashed → manifest_hash.
  3. SIGNATURE is over the canonical bytes of integrity.state_hash +
     integrity.manifest_hash concatenated with newline separator. This is
     the SIGNED_DIGEST — a 96-byte string (sha256:64hex + "\\n" +
     sha256:64hex). NEVER includes the signature value itself in the signed
     bytes.
  4. signatures[] list contains one or more {signer_did, sig_alg, pubkey_format,
     pubkey, signature, signed_at} objects, appended to aepkg.json after
     manifest_hash computation. signatures[] is EXCLUDED from manifest_hash
     basis (same exclusion as manifest_hash itself).

This avoids the self-reference circularity warned about in operator-bundle
Analysis 3 ("CID verification gap") and Analysis 5 ("No Self-Including
Signature").

Uses Python stdlib `cryptography` library (already installed; no PyNaCl
dependency added). Ed25519 chosen for: deterministic signature, 32-byte
public keys, no parameter choice surface, broad cross-language support.

CLI:
    python -m aep.signing keygen <out_priv.pem> <out_pub.pem>
    python -m aep.signing sign <packet_root> <priv_key.pem> --signer-did did:key:z6Mk...
    python -m aep.signing verify <packet_root> [--require-signed]
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Reason codes for v0.7 signed-profile validation.
AEP70_SIGNATURE_REQUIRED = "AEP70_SIGNATURE_REQUIRED"
AEP70_SIGNATURE_INVALID = "AEP70_SIGNATURE_INVALID"
AEP70_SIGNATURE_PUBKEY_FORMAT = "AEP70_SIGNATURE_PUBKEY_FORMAT"
AEP70_SIGNATURE_ALG_UNSUPPORTED = "AEP70_SIGNATURE_ALG_UNSUPPORTED"
AEP70_SIGNATURE_DIGEST_DRIFT = "AEP70_SIGNATURE_DIGEST_DRIFT"


def _have_crypto() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        _ = Ed25519PrivateKey, Ed25519PublicKey
        return True
    except ImportError:
        return False


def signed_digest(state_hash: str, manifest_hash: str) -> bytes:
    """Compute the SIGNED_DIGEST (96-byte bytes object).

    SIGNED_DIGEST = state_hash (with sha256: prefix) + LF + manifest_hash + LF.
    This is the canonical sequence of bytes signed by Ed25519. NEVER includes
    the signature value itself.
    """
    if not state_hash.startswith("sha256:") or not manifest_hash.startswith("sha256:"):
        raise ValueError("signed_digest requires sha256:-prefixed hashes")
    return (state_hash + "\n" + manifest_hash + "\n").encode("utf-8")


def generate_keypair() -> Tuple[bytes, bytes]:
    """Generate Ed25519 (private_pem, public_pem) bytes."""
    if not _have_crypto():
        raise RuntimeError("cryptography library not available; cannot generate Ed25519 keypair")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


def pubkey_raw32(public_pem: bytes) -> bytes:
    """Extract 32-byte raw Ed25519 public key from PEM."""
    if not _have_crypto():
        raise RuntimeError("cryptography library not available")
    from cryptography.hazmat.primitives import serialization
    pub = serialization.load_pem_public_key(public_pem)
    return pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def sign_digest(private_pem: bytes, digest_bytes: bytes) -> bytes:
    """Sign SIGNED_DIGEST bytes with Ed25519 private key. Returns 64-byte signature."""
    if not _have_crypto():
        raise RuntimeError("cryptography library not available")
    from cryptography.hazmat.primitives import serialization
    priv = serialization.load_pem_private_key(private_pem, password=None)
    return priv.sign(digest_bytes)


def verify_signature(public_pem_or_raw32: bytes, digest_bytes: bytes, signature: bytes, fmt: str = "spki_pem") -> bool:
    """Verify Ed25519 signature over SIGNED_DIGEST. Returns True if valid."""
    if not _have_crypto():
        raise RuntimeError("cryptography library not available")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if fmt == "spki_pem":
        pub = serialization.load_pem_public_key(public_pem_or_raw32)
    elif fmt == "raw32":
        pub = Ed25519PublicKey.from_public_bytes(public_pem_or_raw32)
    else:
        raise ValueError(f"unknown pubkey format: {fmt}")
    try:
        pub.verify(signature, digest_bytes)
        return True
    except InvalidSignature:
        return False


def did_key_from_pubkey_raw32(pubkey_raw: bytes) -> str:
    """Compute did:key identifier from 32-byte raw Ed25519 public key.

    Format: did:key:z<multibase-base58btc(0xed 0x01 || pubkey)>.
    Simplified: just base64url(pubkey) for now since did:key parser is
    out-of-scope for v0.7-rc1; full multibase encoding deferred.
    """
    encoded = base64.urlsafe_b64encode(pubkey_raw).rstrip(b"=").decode("ascii")
    return f"did:key:ed25519:{encoded}"


def sign_packet(
    packet_root: Path,
    private_pem: bytes,
    signer_did: Optional[str] = None,
) -> Dict[str, Any]:
    """Sign an AEP packet and append signature block to aepkg.json.

    Reads integrity.state_hash + integrity.manifest_hash; signs the SIGNED_DIGEST;
    appends a signature object to aepkg.json.signatures[].
    """
    if not _have_crypto():
        raise RuntimeError("cryptography library not available")
    from cryptography.hazmat.primitives import serialization
    priv = serialization.load_pem_private_key(private_pem, password=None)
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if signer_did is None:
        signer_did = did_key_from_pubkey_raw32(pub_raw)

    manifest_path = packet_root / "aepkg.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    integrity = manifest.get("integrity", {})
    state_hash = integrity.get("state_hash")
    manifest_hash = integrity.get("manifest_hash")
    if not state_hash or not manifest_hash:
        raise ValueError("packet missing integrity.state_hash or integrity.manifest_hash; cannot sign")
    digest = signed_digest(state_hash, manifest_hash)
    sig = priv.sign(digest)
    sig_b64 = base64.b64encode(sig).decode("ascii")
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")

    signature_block: Dict[str, Any] = {
        "signer_did": signer_did,
        "sig_alg": "ed25519",
        "pubkey_format": "raw32_base64",
        "pubkey": pub_b64,
        "signature": sig_b64,
        "signed_at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "signed_digest_sha256": "sha256:" + hashlib.sha256(digest).hexdigest(),
    }
    sigs = manifest.get("signatures", [])
    if not isinstance(sigs, list):
        sigs = []
    sigs.append(signature_block)
    manifest["signatures"] = sigs
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return signature_block


def verify_packet_signatures(packet_root: Path) -> List[Dict[str, Any]]:
    """Verify all signatures attached to an AEP packet.

    Returns a list of {signer_did, valid, reason} dicts. Empty list if no
    signatures present.
    """
    if not _have_crypto():
        return [{"signer_did": "<all>", "valid": False, "reason": "cryptography library not available"}]
    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return [{"signer_did": "<missing>", "valid": False, "reason": "aepkg.json not found"}]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sigs = manifest.get("signatures", [])
    if not isinstance(sigs, list):
        return []
    integrity = manifest.get("integrity", {})
    state_hash = integrity.get("state_hash", "")
    manifest_hash = integrity.get("manifest_hash", "")
    if not state_hash or not manifest_hash:
        return [{"signer_did": "<missing>", "valid": False, "reason": "integrity hashes missing"}]
    digest = signed_digest(state_hash, manifest_hash)
    out: List[Dict[str, Any]] = []
    for sig_block in sigs:
        if not isinstance(sig_block, dict):
            out.append({"signer_did": "<malformed>", "valid": False, "reason": "signature block is not an object"})
            continue
        signer = sig_block.get("signer_did", "<unknown>")
        alg = sig_block.get("sig_alg", "")
        fmt = sig_block.get("pubkey_format", "raw32_base64")
        if alg != "ed25519":
            out.append({"signer_did": signer, "valid": False, "reason": f"unsupported sig_alg: {alg}"})
            continue
        try:
            pub_b64 = sig_block.get("pubkey", "")
            sig_b64 = sig_block.get("signature", "")
            pub_bytes = base64.b64decode(pub_b64)
            sig_bytes = base64.b64decode(sig_b64)
            if fmt == "raw32_base64":
                valid = verify_signature(pub_bytes, digest, sig_bytes, fmt="raw32")
            elif fmt == "spki_pem_base64":
                valid = verify_signature(pub_bytes, digest, sig_bytes, fmt="spki_pem")
            else:
                out.append({"signer_did": signer, "valid": False, "reason": f"unknown pubkey_format: {fmt}"})
                continue
            out.append({"signer_did": signer, "valid": valid, "reason": "" if valid else "signature verification failed"})
        except Exception as exc:
            out.append({"signer_did": signer, "valid": False, "reason": str(exc)})
    return out


def _cli_main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="AEP v0.7-rc1 Ed25519 signing lane")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_keygen = sub.add_parser("keygen", help="Generate Ed25519 keypair")
    p_keygen.add_argument("priv_out", type=Path)
    p_keygen.add_argument("pub_out", type=Path)
    p_sign = sub.add_parser("sign", help="Sign an AEP packet")
    p_sign.add_argument("packet_root", type=Path)
    p_sign.add_argument("priv_key", type=Path)
    p_sign.add_argument("--signer-did", type=str, default=None)
    p_verify = sub.add_parser("verify", help="Verify packet signatures")
    p_verify.add_argument("packet_root", type=Path)
    p_verify.add_argument("--require-signed", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "keygen":
        if not _have_crypto():
            print("ERROR: cryptography library not available", file=sys.stderr)
            return 2
        priv_pem, pub_pem = generate_keypair()
        args.priv_out.write_bytes(priv_pem)
        args.pub_out.write_bytes(pub_pem)
        print(f"private key: {args.priv_out}")
        print(f"public key:  {args.pub_out}")
        return 0
    elif args.cmd == "sign":
        priv = args.priv_key.read_bytes()
        block = sign_packet(args.packet_root, priv, signer_did=args.signer_did)
        print(f"signed by {block['signer_did']}")
        print(f"signed_digest: {block['signed_digest_sha256']}")
        return 0
    elif args.cmd == "verify":
        results = verify_packet_signatures(args.packet_root)
        if not results:
            if args.require_signed:
                print("FAIL: packet has no signatures (--require-signed)")
                return 1
            print("INFO: packet has no signatures")
            return 0
        all_valid = all(r["valid"] for r in results)
        for r in results:
            mark = "OK" if r["valid"] else "FAIL"
            extra = f" — {r['reason']}" if r["reason"] else ""
            print(f"  [{mark}] {r['signer_did']}{extra}")
        return 0 if all_valid else 1
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_cli_main())
