#!/usr/bin/env python3
"""Emit per-amendment JSONL fixtures by extracting `record` from the Wave-058 retro log.

This produces 7 small JSONL files, one per amendment, that the unified CLI can
validate. Used post-Wave-058 to verify the 7-of-7 per-amendment CLI exit code.
"""
from __future__ import annotations
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
RETRO_LOG = REPO_ROOT / ".claude" / "_logs" / "aep-v11-amendments-retro-applications.jsonl"
OUT_DIR = REPO_ROOT / ".claude" / "_logs"

per: dict[str, list[dict]] = {}
with RETRO_LOG.open(encoding="utf-8") as fp:
    for raw in fp:
        raw = raw.strip()
        if not raw:
            continue
        wrapper = json.loads(raw)
        if wrapper.get("wave") != "058":
            continue
        per.setdefault(wrapper["amendment"], []).append(wrapper["record"])

for amendment, records in per.items():
    out = OUT_DIR / f"aep-v11-amendments-retro-applications.{amendment}.jsonl"
    with out.open("w", encoding="utf-8") as fp:
        for r in records:
            fp.write(json.dumps(r, separators=(",", ":")) + "\n")
    print(f"emitted {len(records)} records to {out}")
