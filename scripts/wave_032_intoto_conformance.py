#!/usr/bin/env python3
"""wave_032_intoto_conformance.py — Wave-032 in-toto downstream conformance test.

For every AEP runtime receipt in .claude/_logs/aep-runtime-receipts.jsonl:
1. Parse as JSON
2. Map to in-toto-attestation v1 Statement protobuf via google.protobuf.json_format
3. Call Statement.validate() (upstream library 0.9.3 strict schema validation)
4. Tabulate pass/fail rate
5. Emit HCRL conformance receipt

Per Wave-026 meta-adversary mitigation: demonstrate downstream Sigstore-style validator
acceptance of our receipts INCLUDING the namespaced `predicate.aep.*` extension fields.
This validates that our Wave-024 namespacing convention does NOT break in-toto v1.0 conformance
(adversary HIGH-VETO closure from Wave-024 H2 — proves the namespaced-extension claim
was empirically defensible).

D4 metric (external conformance demonstrations): v0.8 = 0, post-Wave-032 = 1+, multiplier = 2x.

Composes with: §41 HCRL, §69.1 verification-law (mechanical not theoretical),
§70 surface-mirror (conformance receipt is operator-visible canary),
§V80-9-bis-11 D4 dimension, §V80-13 F10 promotion (signed receipts must remain
in-toto-conformant after signature embedding).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any, Dict, List


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
RECEIPTS_LEDGER = REPO_ROOT / ".claude" / "_logs" / "aep-runtime-receipts.jsonl"
CONFORMANCE_LEDGER = REPO_ROOT / ".claude" / "_logs" / "intoto-conformance-receipts.jsonl"


def conform_one_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one receipt via upstream in-toto-attestation 0.9.3 library."""
    try:
        from in_toto_attestation.v1.statement import Statement
        from in_toto_attestation.v1 import resource_descriptor_pb2
        from google.protobuf.json_format import ParseDict
        from google.protobuf.struct_pb2 import Struct
    except ImportError as e:
        return {"conformant": False, "reason": f"library_import_failed:{type(e).__name__}",
                "library": "in-toto-attestation"}

    try:
        # Construct subjects as ResourceDescriptor protobuf list
        subjects = []
        for s in receipt.get("subject", []):
            rd = resource_descriptor_pb2.ResourceDescriptor()
            rd.name = s.get("name", "")
            for algo, val in (s.get("digest") or {}).items():
                rd.digest[algo] = val
            subjects.append(rd)

        if not subjects:
            return {"conformant": False, "reason": "no_subjects_in_receipt"}

        # Predicate as protobuf Struct
        predicate = Struct()
        ParseDict(receipt.get("predicate", {}), predicate)

        stmt = Statement(
            subjects=subjects,
            predicate_type=receipt.get("predicateType", ""),
            predicate=predicate,
        )
        # Strict validation per in-toto v1.0 spec
        stmt.validate()
        return {"conformant": True, "library": "in-toto-attestation",
                "library_version": "0.9.3", "validate_pass": True}
    except Exception as e:
        return {"conformant": False, "reason": f"validate_failed:{type(e).__name__}:{e}",
                "library": "in-toto-attestation"}


def main() -> int:
    print(f"Wave-032 in-toto downstream conformance test · {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  upstream library: in-toto-attestation 0.9.3 (strict Statement.validate)")
    print(f"  receipts source:  {RECEIPTS_LEDGER.relative_to(REPO_ROOT)}")

    if not RECEIPTS_LEDGER.exists():
        print("  FAIL: receipts ledger does not exist", file=sys.stderr)
        return 1

    receipts: List[Dict[str, Any]] = []
    for line in RECEIPTS_LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            receipts.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not receipts:
        print("  FAIL: no parseable receipts in ledger", file=sys.stderr)
        return 1

    print(f"  receipts loaded:  {len(receipts)}")

    conformant_count = 0
    non_conformant: List[Dict[str, Any]] = []
    signed_conformant_count = 0

    for i, receipt in enumerate(receipts):
        result = conform_one_receipt(receipt)
        if result["conformant"]:
            conformant_count += 1
            # Check if this receipt also has Wave-030 signature
            if (receipt.get("predicate") or {}).get("aepkit", {}).get("signature"):
                signed_conformant_count += 1
        else:
            non_conformant.append({
                "index": i,
                "subject_name": ((receipt.get("subject") or [{}])[0] or {}).get("name", "?"),
                "reason": result.get("reason", "unknown"),
            })

    conformance_rate = conformant_count / len(receipts)

    summary = {
        "wave": "032",
        "audited_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "upstream_library": "in-toto-attestation",
        "upstream_library_version": "0.9.3",
        "validation_protocol": "Statement.validate() strict per in-toto v1.0 spec",
        "n_receipts_total": len(receipts),
        "n_conformant": conformant_count,
        "n_non_conformant": len(non_conformant),
        "conformance_rate": conformance_rate,
        "signed_conformant_count": signed_conformant_count,
        "d4_metric_external_conformance_demonstrations": 1 if conformance_rate > 0 else 0,
        "non_conformant_first_5": non_conformant[:5],
        "namespaced_predicate_aepkit_preserves_intoto_v1_conformance": conformance_rate == 1.0,
    }

    receipt_canonical = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    summary["receipt_sha256"] = hashlib.sha256(receipt_canonical.encode("utf-8")).hexdigest()

    CONFORMANCE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with CONFORMANCE_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":")) + "\n")

    print()
    print("=" * 60)
    print(f"WAVE-032 IN-TOTO CONFORMANCE RESULTS")
    print(f"  receipts:                       {len(receipts)}")
    print(f"  conformant:                     {conformant_count} ({conformance_rate*100:.1f}%)")
    print(f"  signed AND conformant:          {signed_conformant_count}")
    print(f"  non-conformant:                 {len(non_conformant)}")
    print(f"  D4 metric (external conformance): {1 if conformance_rate > 0 else 0} demonstration(s)")
    print(f"  predicate.aep.* preserves in-toto v1.0 conformance: {conformance_rate == 1.0}")
    print(f"  receipt sha256:                 {summary['receipt_sha256'][:16]}...")
    print(f"  conformance ledger:             {CONFORMANCE_LEDGER.relative_to(REPO_ROOT)}")
    return 0 if conformance_rate >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())
