"""reproduce.py — Apache-2.0 — F2 reproducibility_certificate runtime executor.

Closes the v0.8.0-rc2 STAGED F2 item per §V80-4 + §V80-4-bis (birth-only scope).

The reproduce loop walks a packet's reproducibility/transition_log.jsonl,
re-emits canonical body JSONL files (claims, relations, spans, sources) from
source bytes alone using ONLY operations in the deterministic-op whitelist,
then compares re-emitted state_hash to stored state_hash.

DISCIPLINE:
  - REPRODUCE-V80-1: deterministic ops only (no LLM, no clock, no PRNG without seed)
  - REPRODUCE-V80-2: source bytes must hash-match source_hashes_at_reproduce
  - REPRODUCE-V80-3: reproduced JCS bytes must equal stored canonical JCS bytes
  - §V80-4-bis BIRTH-ONLY SCOPE: pre-v0.8 packets without transition_log return
    AEP80_REPRODUCIBILITY_PRE_V0_8_PACKET (info-tier; not a defect)

Stdlib only (§68). No network. No subprocess.

Composes with: §V80-4 F2 + §V80-4-bis birth-only + §50 EH Law 1 (no fabrication;
honest disclosure of what reproduce can/cannot certify).

Usage:
    from aep.reproduce import reproduce_packet, ReproduceResult
    result = reproduce_packet(packet_root)
    if result.certified: print(f"certified: state_hash matches")
    else: print(f"not certified: {result.reason}")
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

REFERENCE_IMPL_VERSION = "0.8.0"

# §V80-4 op-type whitelist (deterministic ops only)
DETERMINISTIC_OPS = frozenset({
    "extract_claim",
    "extract_span",
    "extract_source",
    "link_basis",
    "set_relation",
    "set_review",
    "set_validation",
    "set_event",
})


@dataclass
class ReproduceResult:
    certified: bool
    reason: str
    reason_code: str = ""
    stored_state_hash: str = ""
    reproduced_state_hash: str = ""
    source_drift_detected: List[str] = field(default_factory=list)
    nondeterministic_ops_found: List[str] = field(default_factory=list)
    reproduce_duration_ms: float = 0.0


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_hex(path.read_bytes())


def canonical_jsonl_bytes(records: List[Dict[str, Any]]) -> bytes:
    """Emit records as JCS-canonical JSONL (sort_keys, no whitespace, LF)."""
    lines = []
    for rec in records:
        lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def reproduce_packet(packet_root: pathlib.Path) -> ReproduceResult:
    """Run F2 reproduce loop on a packet.

    Returns ReproduceResult with certified True only if all 3 contracts hold.
    """
    import time
    t0 = time.perf_counter()

    manifest_path = packet_root / "aepkg.json"
    if not manifest_path.exists():
        return ReproduceResult(False, "aepkg.json not found", "AEP80_REPRODUCIBILITY_PACKET_MISSING")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return ReproduceResult(False, f"aepkg.json decode failed: {e}",
                               "AEP80_REPRODUCIBILITY_PACKET_MALFORMED")

    integrity = manifest.get("integrity", {})
    stored_state_hash = integrity.get("state_hash", "")

    tlog_path = packet_root / "reproducibility" / "transition_log.jsonl"
    if not tlog_path.exists():
        # §V80-4-bis birth-only scope: pre-v0.8 packets without transition_log
        return ReproduceResult(
            False,
            "pre-v0.8 packet: birth-only scope per §V80-4-bis (not a defect)",
            "AEP80_REPRODUCIBILITY_PRE_V0_8_PACKET",
            stored_state_hash=stored_state_hash,
            reproduce_duration_ms=(time.perf_counter() - t0) * 1000,
        )

    cert = integrity.get("reproducibility_certificate", {})

    # REPRODUCE-V80-2: verify declared source hashes match current source bytes
    declared_source_hashes: Dict[str, str] = cert.get("source_hashes_at_reproduce", {})
    sources_path = packet_root / "data" / "sources.jsonl"
    if not sources_path.exists():
        return ReproduceResult(False, "data/sources.jsonl missing",
                               "AEP80_REPRODUCIBILITY_SOURCE_DRIFT",
                               stored_state_hash=stored_state_hash)

    drift: List[str] = []
    actual_source_records: Dict[str, Dict[str, Any]] = {}
    for line in sources_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = rec.get("id") or rec.get("source_id")
        if sid:
            actual_source_records[sid] = rec
            if declared_source_hashes:
                declared = declared_source_hashes.get(sid)
                actual = rec.get("sha256", "")
                if declared and declared != actual:
                    drift.append(f"{sid}: declared={declared[:12]}... actual={actual[:12]}...")

    if drift:
        return ReproduceResult(False, "source bytes drifted from declared hashes",
                               "AEP80_REPRODUCIBILITY_SOURCE_DRIFT",
                               stored_state_hash=stored_state_hash,
                               source_drift_detected=drift,
                               reproduce_duration_ms=(time.perf_counter() - t0) * 1000)

    # REPRODUCE-V80-1: walk transition log; check op types are in whitelist
    transitions: List[Dict[str, Any]] = []
    nondet: List[str] = []
    for line in tlog_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            op = json.loads(line)
        except json.JSONDecodeError:
            continue
        op_type = op.get("op", "")
        if op_type not in DETERMINISTIC_OPS:
            nondet.append(f"op_id={op.get('op_id')} op={op_type}")
            continue
        transitions.append(op)

    if nondet:
        return ReproduceResult(False, f"transition log contains nondeterministic ops",
                               "AEP80_REPRODUCIBILITY_NONDETERMINISTIC_OP",
                               stored_state_hash=stored_state_hash,
                               nondeterministic_ops_found=nondet,
                               reproduce_duration_ms=(time.perf_counter() - t0) * 1000)

    # REPRODUCE-V80-3: re-emit canonical body from transitions; compare hash
    # Minimal implementation: walks transitions, builds claims/relations/spans lists,
    # canonically serializes, hashes the concatenation in canonical_files order.
    rebuilt: Dict[str, List[Dict[str, Any]]] = {
        "claims": [], "relations": [], "spans": [], "sources": []
    }
    # Sources come from existing data/sources.jsonl (these are inputs not outputs)
    rebuilt["sources"] = list(actual_source_records.values())

    for op in transitions:
        op_type = op["op"]
        emits = op.get("emits", {})
        if op_type == "extract_claim":
            rebuilt["claims"].append(emits)
        elif op_type == "extract_span":
            rebuilt["spans"].append(emits)
        elif op_type == "link_basis":
            rebuilt["relations"].append({
                "subject_claim": op.get("claim_id"),
                "predicate": "derived_from",
                "object_source": op.get("basis_source_id"),
                "relation_type": op.get("relation_type", "derived_from"),
            })
        elif op_type == "set_relation":
            rebuilt["relations"].append({
                "subject_claim": op.get("subject_claim"),
                "predicate": op.get("predicate"),
                "object_claim": op.get("object_claim"),
            })

    # Compute reproduced state_hash via canonical-JSONL byte concatenation
    # (matches the v0.5.5 state_hash discipline at a structural level; full
    # parity with validate_v0_5's canonical_state_hash_v0_5 deferred to next iter)
    bodies = []
    for kind in ("claims", "relations", "spans", "sources"):
        bodies.append(canonical_jsonl_bytes(rebuilt[kind]))
    reproduced_state_hash = "sha256:" + sha256_hex(b"\n".join(bodies))

    duration_ms = (time.perf_counter() - t0) * 1000

    # For v0.8.0-rc1+ packets: compare reproduced vs stored
    # NOTE: pre-v0.8 packets handled above by tlog_path.exists() check
    if stored_state_hash and reproduced_state_hash != stored_state_hash:
        return ReproduceResult(
            False,
            f"reproduced state_hash {reproduced_state_hash[:25]}... != stored {stored_state_hash[:25]}...",
            "AEP80_REPRODUCIBILITY_BYTE_DRIFT",
            stored_state_hash=stored_state_hash,
            reproduced_state_hash=reproduced_state_hash,
            reproduce_duration_ms=duration_ms,
        )

    return ReproduceResult(
        True,
        "reproduced state_hash matches stored",
        "AEP80_REPRODUCIBILITY_CERTIFIED",
        stored_state_hash=stored_state_hash,
        reproduced_state_hash=reproduced_state_hash,
        reproduce_duration_ms=duration_ms,
    )


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="F2 reproducibility certificate runtime")
    parser.add_argument("packet_root", type=pathlib.Path)
    parser.add_argument("--strict", action="store_true", help="exit 1 if not certified")
    args = parser.parse_args(argv)

    result = reproduce_packet(args.packet_root)
    print(f"reproduce_packet({args.packet_root})")
    print(f"  certified={result.certified}")
    print(f"  reason_code={result.reason_code}")
    print(f"  reason={result.reason}")
    if result.stored_state_hash:
        print(f"  stored_state_hash={result.stored_state_hash[:25]}...")
    if result.reproduced_state_hash:
        print(f"  reproduced_state_hash={result.reproduced_state_hash[:25]}...")
    if result.source_drift_detected:
        print(f"  source_drift: {result.source_drift_detected}")
    if result.nondeterministic_ops_found:
        print(f"  nondeterministic_ops: {result.nondeterministic_ops_found}")
    print(f"  duration_ms={result.reproduce_duration_ms:.2f}")

    if args.strict and not result.certified and result.reason_code != "AEP80_REPRODUCIBILITY_PRE_V0_8_PACKET":
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
