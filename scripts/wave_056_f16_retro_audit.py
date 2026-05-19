#!/usr/bin/env python3
"""wave_056_f16_retro_audit.py - F16 retro audit on a 50-claim corpus sample.

Per sec73.6 honest disconfirmer: scan a deterministic 50-claim sample from the
corpus, run match_claim_against_registry() on each, and report:
  - How many of 50 claims matched at least 1 attack signature?
  - Top-5 matched attack classes by frequency
  - Any claim flagged for MORE than 2 attack signatures (suspicious cluster)

Output: .claude/_logs/aep-v11-f16-retro-audit.jsonl (one row per claim audited
plus a summary row).

Composes_with: F16 registry (build_f16_attack_registry.py),
sibling-132 HV closures, sec73.5 warden-receipts-or-halt.

Sampling strategy (deterministic, NO randomness — same input -> same sample):
  - Walk .claude/agents/*.aepkg/data/claims.jsonl + projects/v11-aep/pilots/*/data/claims.jsonl
  - Concatenate all rows in stable filesystem order
  - Take first 50 with non-empty 'body' field

Exit codes:
  0 = audit completes; results written
  1 = audit completes but >5% claims matched >=2 attack signatures (suspicious cluster threshold)
  2 = infrastructure error
"""
from __future__ import annotations
import collections
import datetime
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from build_f16_attack_registry import (  # type: ignore
        load_registry,
        match_claim_against_registry,
        seed_registry,
    )
except ImportError as e:
    print(f"FATAL: cannot import build_f16_attack_registry: {e}", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
OUTPUT_LOG = REPO_ROOT / ".claude" / "_logs" / "aep-v11-f16-retro-audit.jsonl"

SAMPLE_SIZE = 50


# Candidate claim-source roots, in deterministic order.
SAMPLE_ROOTS = [
    REPO_ROOT / ".claude" / "agents",
    REPO_ROOT / "projects" / "v11-aep" / "pilots",
]


def _extract_claim_body(claim_row: Dict[str, Any]) -> Optional[str]:
    """Pull text body from a claim row. Tries multiple field names because
    different .aepkg dialects use different keys.
    """
    # Most common keys.
    for k in ("body", "text", "statement", "claim_text", "narrative", "summary", "criterion_text", "title"):
        v = claim_row.get(k)
        if isinstance(v, str) and v.strip():
            return v
    # Fallback: stringify the whole row.
    return json.dumps(claim_row, ensure_ascii=False)


def _gather_claims_in_order() -> List[Dict[str, Any]]:
    """Walk SAMPLE_ROOTS, find every *.aepkg/data/claims.jsonl, read in stable order.
    Return list of {packet_path, line_no, body, raw}.
    """
    out: List[Dict[str, Any]] = []
    for root in SAMPLE_ROOTS:
        if not root.exists():
            continue
        # Find all claims.jsonl under this root, sorted.
        for claims_path in sorted(root.rglob("*.aepkg/data/claims.jsonl"), key=lambda p: str(p)):
            packet_rel = str(claims_path.parent.parent.relative_to(REPO_ROOT)).replace("\\", "/")
            try:
                with claims_path.open("r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        body = _extract_claim_body(d)
                        if not body:
                            continue
                        out.append({
                            "packet": packet_rel,
                            "line_no": i + 1,
                            "body": body,
                            "claim_id": d.get("id") or d.get("claim_id") or f"{packet_rel}#L{i+1}",
                        })
            except (OSError, UnicodeDecodeError):
                continue
    return out


def main() -> int:
    # Ensure registry is seeded.
    registry = load_registry()
    if not registry:
        print("F16 registry empty - seeding now.")
        registry = seed_registry(force=False)
    print(f"F16 registry: {len(registry)} entries loaded")

    all_claims = _gather_claims_in_order()
    sample = all_claims[:SAMPLE_SIZE]
    print(f"F16 retro audit: sampled {len(sample)} of {len(all_claims)} total claims")

    if not sample:
        print("FATAL: zero claims found in sample roots", file=sys.stderr)
        return 2

    OUTPUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    audit_ts = datetime.datetime.utcnow().isoformat() + "Z"
    matched_count = 0
    multi_match_claims: List[Dict[str, Any]] = []
    attack_freq: collections.Counter = collections.Counter()

    with OUTPUT_LOG.open("a", encoding="utf-8") as f:
        for c in sample:
            matches = match_claim_against_registry(c["body"], registry=registry)
            row = {
                "type": "F16RetroAuditRow",
                "wave": "wave_056_f16_retro_audit",
                "ts": audit_ts,
                "packet": c["packet"],
                "line_no": c["line_no"],
                "claim_id": c["claim_id"],
                "body_excerpt": c["body"][:240],
                "matched_attack_classes": matches,
            }
            f.write(json.dumps(row) + "\n")
            if matches:
                matched_count += 1
                attack_freq.update(matches)
                if len(matches) >= 2:
                    multi_match_claims.append({
                        "packet": c["packet"],
                        "line_no": c["line_no"],
                        "claim_id": c["claim_id"],
                        "matched": matches,
                    })

        top_5 = attack_freq.most_common(5)
        match_rate = matched_count / len(sample) if sample else 0.0
        summary = {
            "type": "F16RetroAuditSummary",
            "wave": "wave_056_f16_retro_audit",
            "ts": audit_ts,
            "actor": "forge",
            "sample_size": len(sample),
            "claims_with_any_match": matched_count,
            "match_rate": round(match_rate, 4),
            "top_5_matched_attack_classes": top_5,
            "multi_match_claim_count": len(multi_match_claims),
            "multi_match_claims": multi_match_claims[:10],  # cap report at 10
            "registry_size": len(registry),
        }
        f.write(json.dumps(summary) + "\n")

    print()
    print("=" * 70)
    print("F16 RETRO AUDIT SUMMARY")
    print("=" * 70)
    print(f"  sample_size: {len(sample)}")
    print(f"  claims with >=1 match: {matched_count} ({match_rate:.2%})")
    print(f"  multi-match (>=2 atks) claims: {len(multi_match_claims)}")
    print(f"  top-5 attack classes by frequency:")
    for atk_id, cnt in top_5:
        print(f"    {atk_id}: {cnt}")
    print(f"  log written to: {OUTPUT_LOG.relative_to(REPO_ROOT)}")
    print()

    # Suspicious-cluster threshold: >5% claims with >=2 matches.
    multi_rate = len(multi_match_claims) / len(sample)
    if multi_rate > 0.05:
        print(f"WARN: multi-match rate {multi_rate:.2%} > 5% threshold (suspicious cluster).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
