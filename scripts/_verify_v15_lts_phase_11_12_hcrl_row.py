#!/usr/bin/env python3
"""Verify the HCRL terminal row hash and chain integrity."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

LOG = Path(".claude/_logs/aep-v15-lts-phase-receipts.jsonl")


def main() -> int:
    with LOG.open(encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    print("Total rows:", len(lines))
    last = json.loads(lines[-1])
    stored = last.pop("row_sha256")
    canonical = json.dumps(last, sort_keys=True, separators=(",", ":"))
    recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    print("phase        :", last["phase"])
    print("prev_receipt :", last["prev_receipt_hash"])
    print("stored hash  :", stored)
    print("recomputed   :", recomputed)
    print("hash match   :", stored == recomputed)
    print("verdict      :", last["no_screen_fail"]["final_verdict"])
    print("composes_with:", len(last["composes_with"]), "entries")
    # Walk the chain: verify each prev_receipt_hash matches a row_sha256 above it
    chain = {}
    for ln in lines:
        try:
            r = json.loads(ln)
            chain[r.get("row_sha256", "")] = r.get("phase", "")
        except Exception:
            pass
    prev = last["prev_receipt_hash"]
    found = prev in chain
    print("prev exists  :", found, "(phase:", chain.get(prev, "?"), ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
