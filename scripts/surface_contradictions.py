"""surface_contradictions.py — PROPOSE contradiction candidates from the semantic index.

Walks the precomputed top-K nearest-neighbor pairs in index.jsonl and applies the
contradiction-detection rule. Writes APPEND-ONLY to
`.claude/_logs/contradiction-candidates.jsonl` (per warden's §50 PROPOSE-not-MUTATE rule).

§50 Law-3 operationalization: a high-cosine pair where the two sides disagree on
reliability tier or Axis-B action is a CANDIDATE — operator + warden review queue.

Scout's "Negation is Not Semantic" caveat is closed by REQUIRING structural conflict
(reliability gap >= 2 tiers OR Axis-B GO/HALT) in addition to cosine >= threshold.
Cosine alone is NEVER sufficient to emit a candidate.

Usage:
    python surface_contradictions.py \
        [--index projects/v11-aep/publish-ready/aep/embeddings/v1] \
        [--out .claude/_logs/contradiction-candidates.jsonl] \
        [--min-cos 0.85] [--max-candidates 50]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# Reliability tier ranking — higher = stronger evidence claim
RELIABILITY_TIER = {
    "PROVEN_RELIABLE": 5,
    "PROVEN/RELIABLE": 5,
    "STRONGLY_PLAUSIBLE": 4,
    "STRONGLY PLAUSIBLE": 4,
    "PLAUSIBLE": 3,
    "EXPERIMENTAL": 3,
    "ASSUMPTION": 2,
    "SPECULATIVE FRONTIER": 1,
    "SPECULATIVE_FRONTIER": 1,
    "CONFLICTED": 0,
    "IMPOSSIBLE": -1,
    "IMPOSSIBLE/UNSUPPORTED": -1,
    "DANGEROUS/NOT WORTH DOING": -2,
}


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha_short(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=8).hexdigest()


def tier(rel) -> int:
    if not rel:
        return None
    return RELIABILITY_TIER.get(rel.upper() if isinstance(rel, str) else rel, None)


def is_stage_evolution_pair(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Detect promotion-timeline pairs (NOT contradictions).

    A pair is stage-evolution if:
    - One side is in an agent ledger (`.claude/agents/_ledgers/`) AND
      that side is SPECULATIVE_FRONTIER or EXPERIMENTAL/PLAUSIBLE/ASSUMPTION
    - The OTHER side is in canonical doctrine (`doctrine/` excluding `_proposals/`)
      OR a promoted proposal AND
      that side is STRONGLY_PLAUSIBLE or PROVEN_RELIABLE

    Such pairs represent: "a scout/forge speculated, doctrine subsequently
    confirmed/promoted." Not a contradiction — just timeline.

    Per sibling-73 F3 falsification (5/6 candidates were stage-evolution).
    """
    def is_ledger(r):
        sp = (r.get("source_path") or "").replace("\\", "/")
        return "_ledgers/" in sp or sp.startswith(".claude/agents/_ledgers/")

    def is_canonical_doctrine(r):
        sp = (r.get("source_path") or "").replace("\\", "/")
        return sp.startswith("doctrine/") and "/_proposals/" not in sp

    def is_promoted_proposal(r):
        sp = (r.get("source_path") or "").replace("\\", "/")
        return "/_proposals/" in sp and (
            (r.get("reliability") or "").upper() in {"PROVEN_RELIABLE", "STRONGLY_PLAUSIBLE", "PROVEN/RELIABLE", "STRONGLY PLAUSIBLE"}
        )

    def is_speculation(r):
        rel = (r.get("reliability") or "").upper()
        return rel in {"SPECULATIVE_FRONTIER", "SPECULATIVE FRONTIER", "EXPERIMENTAL", "ASSUMPTION", "PLAUSIBLE"}

    def is_promoted(r):
        rel = (r.get("reliability") or "").upper()
        return rel in {"STRONGLY_PLAUSIBLE", "STRONGLY PLAUSIBLE", "PROVEN_RELIABLE", "PROVEN/RELIABLE"}

    # Symmetric check: either (a is speculation-in-ledger, b is promoted-in-doctrine)
    # or vice versa
    for side_lo, side_hi in ((a, b), (b, a)):
        if is_ledger(side_lo) and is_speculation(side_lo):
            if (is_canonical_doctrine(side_hi) or is_promoted_proposal(side_hi)) and is_promoted(side_hi):
                return True
    return False


def detect_conflict(a: Dict[str, Any], b: Dict[str, Any], exclude_stage_evolution: bool = True) -> List[str]:
    """Return list of conflict-class labels. Empty list = no contradiction.

    v2 (sibling-73 follow-up): Structural filter + timeline-exclusion.

    Structural disagreement required (cosine alone is NEVER sufficient — scout's
    "Negation is Not Semantic"). v2 additionally excludes stage-evolution pairs
    (predecessor speculation → successor promotion is NOT a contradiction).
    """
    if exclude_stage_evolution and is_stage_evolution_pair(a, b):
        return []

    classes = []

    ta, tb = tier(a.get("reliability")), tier(b.get("reliability"))
    if ta is not None and tb is not None:
        # 2+ tier reliability gap = AEP-XX-RELIABILITY-CONTRADICTION-CANDIDATE
        if abs(ta - tb) >= 2 and (ta >= 4 or tb >= 4):
            # One side must be at least STRONGLY_PLAUSIBLE; the other is materially weaker
            classes.append("AEP-XX-RELIABILITY-CONTRADICTION-CANDIDATE")

    ax_a, ax_b = a.get("axis_b"), b.get("axis_b")
    if ax_a and ax_b:
        if {str(ax_a).upper(), str(ax_b).upper()} == {"GO", "HALT"}:
            classes.append("AEP-XX-AXIS-B-CONTRADICTION-CANDIDATE")
        if {str(ax_a).upper(), str(ax_b).upper()} == {"GO", "FORBIDDEN"}:
            classes.append("AEP-XX-AXIS-B-FORBIDDEN-VS-GO-CANDIDATE")

    return classes


def load_index_rows(index_dir: Path):
    rows = []
    with open(index_dir / "index.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_seen_pairs(out_path: Path):
    seen = set()
    if not out_path.exists():
        return seen
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    seen.add(row.get("pair_id"))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return seen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings/v1"))
    ap.add_argument("--out", type=Path,
                    default=Path(".claude/_logs/contradiction-candidates.jsonl"))
    ap.add_argument("--min-cos", type=float, default=0.85)
    ap.add_argument("--max-candidates", type=int, default=50)
    ap.add_argument("--include-stage-evolution", action="store_true",
                    help="DON'T filter out promotion-timeline pairs (debug only)")
    args = ap.parse_args(argv)

    t0 = time.time()
    rows = load_index_rows(args.index)
    rows_by_idx = {r["vec_idx"]: r for r in rows}
    seen = load_seen_pairs(args.out)

    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    candidates = []
    pairs_checked = 0
    pairs_above_cos = 0

    for r in rows:
        nn = r.get("top_k_nn", [])
        for nb in nn:
            cos = nb.get("cos", 0)
            if cos < args.min_cos:
                continue
            i, j = r["vec_idx"], nb["vec_idx"]
            if i >= j:  # only emit each pair once (use lower-idx as first side)
                continue
            pairs_above_cos += 1
            pairs_checked += 1
            b = rows_by_idx.get(j)
            if not b:
                continue
            classes = detect_conflict(r, b, exclude_stage_evolution=not args.include_stage_evolution)
            for cls in classes:
                pair_id = sha_short(f"{r['vec_id']}|{b['vec_id']}|{cls}")
                if pair_id in seen:
                    continue
                seen.add(pair_id)
                candidates.append({
                    "pair_id": pair_id,
                    "class": cls,
                    "cos": round(cos, 4),
                    "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "a": {
                        "vec_id": r["vec_id"], "source_path": r["source_path"],
                        "claim_id": r["claim_id"], "reliability": r["reliability"],
                        "axis_b": r["axis_b"], "source_kind": r["source_kind"],
                    },
                    "b": {
                        "vec_id": b["vec_id"], "source_path": b["source_path"],
                        "claim_id": b["claim_id"], "reliability": b["reliability"],
                        "axis_b": b["axis_b"], "source_kind": b["source_kind"],
                    },
                    "status": "unreviewed",
                })

    candidates.sort(key=lambda c: (-c["cos"], c["pair_id"]))
    new_candidates = candidates[:args.max_candidates]

    with open(out_path, "a", encoding="utf-8") as f:
        for c in new_candidates:
            f.write(canonical_json(c) + "\n")

    elapsed_ms = round((time.time() - t0) * 1000)
    by_class = Counter(c["class"] for c in new_candidates)

    summary = {
        "scan_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "n_rows_indexed": len(rows),
        "n_pairs_checked": pairs_checked,
        "n_pairs_above_cos": pairs_above_cos,
        "n_candidates_emitted": len(new_candidates),
        "by_class": dict(by_class),
        "min_cos_threshold": args.min_cos,
        "out_path": str(out_path),
        "ms_elapsed": elapsed_ms,
    }
    print(canonical_json(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
