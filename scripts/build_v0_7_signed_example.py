"""v0.7-rc1: build signed example packet at examples/minimal-v0_7-signed.aepkg.

Steps:
  1. Copy minimal.aepkg -> minimal-v0_7-signed.aepkg
  2. Generate v0.7 deterministic views into views/
  3. Recompute state_hash + manifest_hash (since views changed; views are not in
     canonical_files but views_merkle_root is added to integrity)
  4. Bump profile to aep:0.7/signed
  5. Generate Ed25519 keypair and sign the packet
  6. Verify the signed packet validates clean under aep:0.7/signed

Also drops the keypair into examples/keys/v0_7-test/ for reproducibility.
"""
import json
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aep.signing import generate_keypair, sign_packet, verify_packet_signatures
from aep.views import write_all_views, views_merkle_root
from aep.validate_v0_5 import canonical_state_hash_v0_5, manifest_hash_v0_5, aep_merkle_v1
from aep.build_index import write_index


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "examples" / "minimal.aepkg"
DST = ROOT / "examples" / "minimal-v0_7-signed.aepkg"
KEYS = ROOT / "examples" / "keys" / "v0_7-test"


def main():
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    print(f"Copied {SRC.name} -> {DST.name}")

    # 1. Bump profile FIRST so views read the final profile string.
    # Note: aep_version stays "0.5" (base record schema unchanged); profile declares
    # the layered v0.7 profile per multi-layer architecture.
    manifest = json.loads((DST / "aepkg.json").read_text(encoding="utf-8"))
    manifest["profile"] = "aep:0.7/signed"
    # aep_version intentionally kept at "0.5" — v0.7 is a profile layer, not a new base schema

    # 2. Recompute state_hash + assets_merkle_root (depends on data/* only).
    state_hash = canonical_state_hash_v0_5(DST, manifest["canonical_files"])
    assets_dir = DST / "assets"
    if assets_dir.exists() and any(assets_dir.iterdir()):
        assets_merkle = aep_merkle_v1(assets_dir)
    else:
        assets_merkle = manifest["integrity"].get("assets_merkle_root", "")
    manifest["integrity"]["state_hash"] = state_hash
    manifest["integrity"]["assets_merkle_root"] = assets_merkle
    print(f"  state_hash: {state_hash}")
    print(f"  assets_merkle_root: {assets_merkle}")

    # 3. Regenerate cache/index.bin and compute index_hash + context_hash
    #    (these enter the integrity envelope BEFORE manifest_hash so the manifest
    #    is fully populated when manifest_hash is computed).
    ihash = write_index(DST)
    import hashlib
    ctx_path = DST / "contexts" / "aep.context.jsonld"
    if ctx_path.exists():
        ctx_hash = "sha256:" + hashlib.sha256(ctx_path.read_bytes()).hexdigest()
    else:
        ctx_hash = None
    manifest["integrity"]["index_hash"] = ihash
    if ctx_hash:
        manifest["extensions"] = manifest.get("extensions", {}) or {}
        manifest["extensions"]["jsonld:context_hash"] = ctx_hash
    print(f"  index_hash: {ihash}")
    if ctx_hash:
        print(f"  context_hash: {ctx_hash}")

    # 4. Compute manifest_hash with 3-field exclusion: manifest_hash,
    #    views_merkle_root, signatures. This is the AEP-v0.7 SIGNED_DIGEST basis
    #    (and the verifier's basis for byte-parity re-verification).
    manifest_for_hash = dict(manifest)
    manifest_for_hash["integrity"] = dict(manifest["integrity"])
    manifest_for_hash["integrity"].pop("manifest_hash", None)
    manifest_for_hash["integrity"].pop("views_merkle_root", None)
    manifest_for_hash.pop("signatures", None)
    mhash = manifest_hash_v0_5(manifest_for_hash)
    manifest["integrity"]["manifest_hash"] = mhash
    print(f"  manifest_hash: {mhash}")

    # 5. Write aepkg.json with finalized state_hash + manifest_hash + integrity
    #    extensions BEFORE deriving views (views read FINAL integrity envelope).
    (DST / "aepkg.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )

    # 6. Derive views (read FINAL integrity envelope from aepkg.json).
    view_hashes = write_all_views(DST)
    for rel, h in view_hashes.items():
        print(f"  view: {rel}: {h}")
    vmerkle = views_merkle_root(DST)
    print(f"  views_merkle_root: {vmerkle}")

    # 7. Append views_merkle_root to integrity (excluded from manifest_hash basis
    #    so this doesn't invalidate the finalized manifest_hash).
    manifest["integrity"]["views_merkle_root"] = vmerkle
    (DST / "aepkg.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )

    # 4. Generate keypair + sign
    KEYS.mkdir(parents=True, exist_ok=True)
    priv_pem, pub_pem = generate_keypair()
    (KEYS / "ed25519-priv.pem").write_bytes(priv_pem)
    (KEYS / "ed25519-pub.pem").write_bytes(pub_pem)
    print(f"  keypair saved to {KEYS}")
    block = sign_packet(DST, priv_pem, signer_did="did:key:test-v0_7-example")
    print(f"  signed_at: {block['signed_at']}")
    print(f"  signed_digest: {block['signed_digest_sha256']}")

    # 5. Verify
    results = verify_packet_signatures(DST)
    for r in results:
        ok = "OK" if r["valid"] else "FAIL"
        print(f"  signature [{ok}] {r['signer_did']}: {r['reason'] or 'verified'}")

    print(f"\nv0.7-rc1 signed example built at {DST}")


if __name__ == "__main__":
    main()
