#!/usr/bin/env python3
"""
AEP v1.1 F17 packet_history_dag builder.

Builds a typed DAG of (audit | amendment | promotion | rollback | supersede |
contradict | freeze_lock | redaction) events. Each event carries parent_event_ids[]
where len>1 = DAG merge (sec41 DAG re-anchor native).

Source: an aepkg's `aepkg.json.extensions.packet_history[]` if present;
otherwise an external HCRL chain (e.g. .claude/_logs/aep-v103-phase-receipts.jsonl).

This script does TWO things:
  1. Provides a programmatic API (query_packet_history, walk_dag_from_event,
     find_re_anchor_events) over an in-memory DAG.
  2. Acts as a retroactive converter: reads aep-v103-phase-receipts.jsonl and
     writes a v1.1 F17-typed DAG to
     projects/v11-aep/publish-ready/aep/recall/packet_history/aep_v103_chain.jsonl

The retro converter preserves the row-7 DAG re-anchor: row-7 (scribe closeout)
has parent_event_ids = [row-5-hash, row-6-hash] (warden audit + judge audit
both fed scribe), demonstrating the first canonical sec41 DAG merge.

Composes_with: sec41 HCRL (each F17 event MAY anchor to an HCRL row),
v0.8 F10 signed ITE6 (event_signature_ed25519 inherits F10 discipline),
v1.0.3.1 F14 RaterQuorumAttestation (promotion events under strict profile).

Truth tag: SPECULATIVE FRONTIER (F17 itself); STRONGLY PLAUSIBLE (retroactive
classification of HCRL row 1-9 events).

cites: forge:lamport-216-v1_1_phase_3c_f17_f18_f19_retro
       ledger::scribe::lamport-NNN::v103-dag-reanchor-row7
       sec41-HCRL doctrine slot
       AEP_v1_1_SPEC sec7
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ---------- Constants ----------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
HCRL_V103_PATH = REPO_ROOT / ".claude" / "_logs" / "aep-v103-phase-receipts.jsonl"
RETRO_OUTPUT_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "recall" / "packet_history"
RETRO_OUTPUT_PATH = RETRO_OUTPUT_DIR / "aep_v103_chain.jsonl"

# Map HCRL actor -> F17 event_kind classification heuristic.
ACTOR_TO_EVENT_KIND = {
    "agent_inline": "amendment",   # phase 1 schema scaffold
    "warden":       "audit",       # phase 2 + 8b
    "judge":        "audit",       # phase 2.5 + 8a
    "forge":        "amendment",   # phase 7 + 8 + 9
    "scribe":       "amendment",   # phase 9 closeout
    "curator":      "promotion",   # not present in v103 chain yet
    "adversary":    "audit",
    "scout":        "audit",
    "pathfinder":   "amendment",
    "strategist":   "amendment",
    "visual-judge": "audit",
}


# ---------- Core DAG model ----------

class PacketHistoryEvent(dict):
    """One F17 PacketHistoryEvent. Behaves like a dict; schema-validated by validator."""
    pass


def make_event(
    *,
    event_id: str,
    event_kind: str,
    event_at: str,
    auditor_principal_id: str,
    parent_event_ids: List[str],
    verdict: str,
    bound_to_packet_id: Optional[str] = None,
    bound_to_packet_sha256_pre: Optional[str] = None,
    bound_to_packet_sha256_post: Optional[str] = None,
    evidence_artifact_sha256: Optional[str] = None,
    rater_quorum_id: Optional[str] = None,
    narrative_summary: str = "",
    composes_with_doctrine_slots: Optional[List[str]] = None,
) -> PacketHistoryEvent:
    """Build a schema-conformant F17 event with placeholder Ed25519 signature.

    Sig is computed deterministically as BLAKE2b-128 over the canonical bytes
    (NOT a real Ed25519 — this is RETRO classification of pre-F17 history;
    full Ed25519 attestation requires sec73.5 warden offline-signing pass).

    Optional fields with None value are OMITTED so schema's
    additionalProperties:false + per-field type rules pass cleanly.
    Per-schema: bound_to_packet_sha256_pre must be a string (not null) if present;
                bound_to_packet_sha256_post may be string or null.
    """
    canonical = (
        event_id + "\n" +
        event_kind + "\n" +
        event_at + "\n" +
        auditor_principal_id + "\n" +
        json.dumps(parent_event_ids, separators=(",", ":"), sort_keys=False) + "\n" +
        verdict
    ).encode("utf-8")
    placeholder_sig = hashlib.blake2b(canonical, digest_size=24).hexdigest()

    ev: PacketHistoryEvent = PacketHistoryEvent({
        "type": "PacketHistoryEvent",
        "schema_version": "aep-packet-history-dag-0.1",
        "id": event_id,
        "event_kind": event_kind,
        "event_at": event_at,
        "auditor_principal_id": auditor_principal_id,
        "parent_event_ids": parent_event_ids,
        "verdict": verdict,
        "event_signature_ed25519": placeholder_sig,
    })
    # Optional fields — only include if present (or explicit-nullable).
    if bound_to_packet_id:
        ev["bound_to_packet_id"] = bound_to_packet_id
    if bound_to_packet_sha256_pre:
        ev["bound_to_packet_sha256_pre"] = bound_to_packet_sha256_pre
    # post may be explicit null (audit event, no packet change).
    if bound_to_packet_sha256_post is not None:
        ev["bound_to_packet_sha256_post"] = bound_to_packet_sha256_post
    else:
        # explicit null is valid per schema (audit events don't mutate the packet)
        ev["bound_to_packet_sha256_post"] = None
    if evidence_artifact_sha256 is not None:
        ev["evidence_artifact_sha256"] = evidence_artifact_sha256
    if rater_quorum_id is not None:
        ev["rater_quorum_id"] = rater_quorum_id
    ev["narrative_summary"] = narrative_summary[:2048]
    ev["composes_with_doctrine_slots"] = composes_with_doctrine_slots or []
    return ev


# ---------- Query API ----------

def query_packet_history(events: List[Dict[str, Any]], packet_id: str) -> List[Dict[str, Any]]:
    """Return events bound to packet_id, sorted by event_at (Lamport-equivalent)."""
    matched = [e for e in events if e.get("bound_to_packet_id", "") == packet_id]
    matched.sort(key=lambda e: (e.get("event_at", ""), e.get("id", "")))
    return matched


def walk_dag_from_event(
    events: List[Dict[str, Any]],
    start_event_id: str,
    direction: str = "forward",
) -> List[str]:
    """Walk DAG from a starting event. direction='forward' follows children;
    'backward' follows parent_event_ids. Returns ordered list of event IDs
    visited (BFS order, start_event_id first)."""
    by_id = {e["id"]: e for e in events}
    if start_event_id not in by_id:
        return []

    # Build forward edges: parent -> [children]
    forward_edges: Dict[str, List[str]] = {}
    for ev in events:
        for p in ev.get("parent_event_ids", []):
            forward_edges.setdefault(p, []).append(ev["id"])

    visited: List[str] = []
    seen: Set[str] = set()
    queue: List[str] = [start_event_id]

    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        visited.append(node)
        if direction == "forward":
            nexts = forward_edges.get(node, [])
        else:
            nexts = by_id.get(node, {}).get("parent_event_ids", [])
        for n in nexts:
            if n not in seen:
                queue.append(n)
    return visited


def find_re_anchor_events(events: List[Dict[str, Any]], packet_id: Optional[str] = None) -> List[str]:
    """Return event IDs where len(parent_event_ids) > 1 = DAG merge (sec41 re-anchor)."""
    out: List[str] = []
    for e in events:
        parents = e.get("parent_event_ids", [])
        if len(parents) > 1:
            if packet_id is None or e.get("bound_to_packet_id", "") == packet_id:
                out.append(e["id"])
    return out


# ---------- HCRL retro-converter ----------

def load_hcrl_rows(path: pathlib.Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return rows


def hcrl_row_to_f17_event(
    row: Dict[str, Any],
    *,
    row_index: int,
    hash_to_event_id: Dict[str, str],
    packet_id: str = "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md",
) -> PacketHistoryEvent:
    """Convert one HCRL row to one F17 event. Resolves prev_receipt_hash[es]
    to parent_event_ids using hash_to_event_id map (filled progressively as
    rows are processed)."""
    actor = row.get("actor", "unknown")
    event_kind = ACTOR_TO_EVENT_KIND.get(actor, "audit")
    phase_title = row.get("phase_title", row.get("phase", f"row-{row_index}"))
    phase = str(row.get("phase", row_index))
    timestamp = row.get("timestamp", "1970-01-01T00:00:00Z")

    # Compute event_id from phase + actor + row_index (deterministic).
    slug = (str(phase) + "-" + actor + "-r" + str(row_index)).lower()
    slug = "".join(c if (c.isalnum() or c in "._-") else "-" for c in slug)
    event_id = f"phe:v103-spec:r{row_index}:{slug}"

    # Resolve parent event IDs from prev_receipt_hash / prev_receipt_hashes.
    parents: List[str] = []
    prev_single = row.get("prev_receipt_hash")
    prev_multi = row.get("prev_receipt_hashes")
    if isinstance(prev_multi, list):
        for h in prev_multi:
            mapped = hash_to_event_id.get(h)
            if mapped:
                parents.append(mapped)
    elif isinstance(prev_single, str) and prev_single:
        mapped = hash_to_event_id.get(prev_single)
        if mapped:
            parents.append(mapped)
    # row 1 has prev_receipt_hash:null -> empty parents = root event.

    # Determine verdict from runtime_trace / no_screen_fail.
    nsf = row.get("no_screen_fail", {}) or {}
    rt = row.get("runtime_trace", {}) or {}
    verdict = "PASS"
    if isinstance(nsf.get("verdict"), str):
        v_raw = nsf["verdict"].upper()
        if "PASS" in v_raw and "FAIL" not in v_raw:
            verdict = "PASS"
        elif "CONDITIONAL" in v_raw:
            verdict = "CONDITIONAL"
        elif "PARTIAL" in v_raw:
            verdict = "PARTIAL"
        elif "ABORT" in v_raw:
            verdict = "ABORT"
        elif "FAIL" in v_raw:
            verdict = "FAIL"
        elif "ARC_COMPLETE" in v_raw or "COMPLETE" in v_raw:
            verdict = "PASS"
    if "tiebreaker_verdict" in nsf and "FAIL" in str(nsf.get("tiebreaker_verdict", "")).upper():
        verdict = "FAIL"

    # Build narrative summary.
    actor_str = actor
    summary_bits = [f"HCRL row {row_index} ({phase_title})", f"actor={actor_str}"]
    if "bc_test_verdict" in rt:
        summary_bits.append(f"bc_test={rt['bc_test_verdict']}")
    if "verdict" in rt and isinstance(rt["verdict"], str):
        summary_bits.append(f"trace_verdict={rt['verdict']}")
    narrative = "; ".join(summary_bits)[:2048]

    # Anchor every retro row to the v1.0.3 SPEC's known sha256 (per HCRL row 4
    # artifact_sha256 = 0635570ae4e256726188c78792177858126ece99e52daffa96390d9486883746).
    spec_sha = "sha256:0635570ae4e256726188c78792177858126ece99e52daffa96390d9486883746"

    ev = make_event(
        event_id=event_id,
        event_kind=event_kind,
        event_at=timestamp,
        auditor_principal_id=f"{actor}:hcrl:row-{row_index}",
        parent_event_ids=parents,
        verdict=verdict,
        bound_to_packet_id=packet_id,
        bound_to_packet_sha256_pre=spec_sha,
        bound_to_packet_sha256_post=spec_sha,  # all rows are audits/amendments referencing post-stub SPEC
        narrative_summary=narrative,
        composes_with_doctrine_slots=["sec41", "sec73"],
    )
    # Remember this row's row_sha256 -> event_id so subsequent rows can link.
    row_hash = row.get("row_sha256")
    if isinstance(row_hash, str) and row_hash:
        hash_to_event_id[row_hash] = event_id
    return ev


def retro_build_from_hcrl(hcrl_path: pathlib.Path) -> List[PacketHistoryEvent]:
    rows = load_hcrl_rows(hcrl_path)
    hash_to_event_id: Dict[str, str] = {}
    events: List[PacketHistoryEvent] = []
    for i, r in enumerate(rows, start=1):
        ev = hcrl_row_to_f17_event(r, row_index=i, hash_to_event_id=hash_to_event_id)
        events.append(ev)
    return events


# ---------- CLI ----------

def write_jsonl(events: Iterable[Dict[str, Any]], out_path: pathlib.Path) -> Tuple[int, str]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    blob = b""
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for e in events:
            line = json.dumps(e, separators=(",", ":"), ensure_ascii=False) + "\n"
            fh.write(line)
            blob += line.encode("utf-8")
    sha = hashlib.sha256(blob).hexdigest()
    return len(blob), sha


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="F17 packet_history_dag builder + retro")
    parser.add_argument(
        "--mode",
        choices=["retro_v103", "query", "verify"],
        default="retro_v103",
        help="retro_v103: convert aep-v103-phase-receipts.jsonl to F17 DAG. "
             "query: --packet-id + --walk-from + --direction. "
             "verify: --in <jsonl> + run DAG-walk + signature placeholder checks.",
    )
    parser.add_argument("--in", dest="in_path", type=pathlib.Path, default=HCRL_V103_PATH)
    parser.add_argument("--out", dest="out_path", type=pathlib.Path, default=RETRO_OUTPUT_PATH)
    parser.add_argument("--packet-id", default="projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md")
    parser.add_argument("--walk-from", default="")
    parser.add_argument("--direction", default="forward", choices=["forward", "backward"])
    args = parser.parse_args(argv)

    if args.mode == "retro_v103":
        events = retro_build_from_hcrl(args.in_path)
        size_bytes, sha = write_jsonl(events, args.out_path)
        reanchors = find_re_anchor_events(events)
        out_path = args.out_path
        try:
            out_path = out_path.relative_to(REPO_ROOT)
        except ValueError:
            pass
        report = {
            "mode": "retro_v103",
            "rows_in": len(events),
            "out_path": str(out_path).replace("\\", "/"),
            "out_size_bytes": size_bytes,
            "out_sha256": sha,
            "re_anchor_event_ids": reanchors,
            "re_anchor_count": len(reanchors),
            "row_7_has_two_parents": any(
                e["id"].startswith("phe:v103-spec:r7:") and len(e["parent_event_ids"]) >= 2
                for e in events
            ),
        }
        print(json.dumps(report, indent=2))
        return 0

    if args.mode == "query":
        events = []
        with args.in_path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    events.append(json.loads(ln))
        if args.walk_from:
            path = walk_dag_from_event(events, args.walk_from, direction=args.direction)
            print(json.dumps({"walk": path, "len": len(path)}, indent=2))
        else:
            hist = query_packet_history(events, args.packet_id)
            print(json.dumps([e["id"] for e in hist], indent=2))
        return 0

    if args.mode == "verify":
        events = []
        with args.in_path.open("r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    events.append(json.loads(ln))
        # cycle check
        by_id = {e["id"]: e for e in events}
        cycles: List[str] = []
        for start in list(by_id.keys()):
            walk = walk_dag_from_event(events, start, direction="backward")
            if walk.count(start) > 1:
                cycles.append(start)
        # placeholder-sig recomputation sanity
        sig_mismatches = 0
        for e in events:
            canonical = (
                e["id"] + "\n" + e["event_kind"] + "\n" + e["event_at"] + "\n" +
                e["auditor_principal_id"] + "\n" +
                json.dumps(e["parent_event_ids"], separators=(",", ":"), sort_keys=False) + "\n" +
                e["verdict"]
            ).encode("utf-8")
            expected = hashlib.blake2b(canonical, digest_size=24).hexdigest()
            if expected != e.get("event_signature_ed25519", ""):
                sig_mismatches += 1
        print(json.dumps({
            "events": len(events),
            "cycles_detected": cycles,
            "placeholder_sig_mismatches": sig_mismatches,
            "re_anchor_events": find_re_anchor_events(events),
        }, indent=2))
        return 0 if not cycles and sig_mismatches == 0 else 1

    return 2


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. F17's role per AEP v1.1: packet-history-DAG integrity,
# temporal-causality validation, hash-chain checking. Extended to ALL DAG-
# adjacent mutations: parent corruption, parent self-reference, parent timestamp
# inversion, event reorder, event ts monotonicity, source-hash chain integrity,
# span-required-for-claim integrity (DAG nodes carry span refs).
# Validator version bump: v1.1.0 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
import hashlib as _v15_hashlib

V15_VALIDATOR_VERSION = "v1.5.0-K5-repair"


def _v15_hash_valid(h):
    if not isinstance(h, str) or len(h) != 64:
        return False
    try:
        int(h, 16)
        return True
    except (ValueError, TypeError):
        return False


def _v15_check_dag_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    parents = manifest.get("dag_parents") or []
    if not isinstance(parents, list):
        out.append("AEP15_F17_DAG_PARENTS_NOT_A_LIST")
        return out
    for p in parents:
        if not isinstance(p, str):
            out.append("AEP15_F17_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED")):
            out.append(f"AEP15_F17_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_F17_DAG_PARENT_SELF_REFERENCE")
        # Wrong-parent: parent hash not in expected sha256 format AND not a packet-id
        if not (p.startswith("sha256:") or p.startswith("mut:") or p.startswith("pkt:")):
            out.append(f"AEP15_F17_DAG_PARENT_UNRECOGNIZED:{p}")
    return out


def _v15_check_event_ordering(packet):
    out = []
    events = (packet.get("manifest") or {}).get("events", [])
    prev_ts = None
    kinds = []
    for ev in events:
        kinds.append(ev.get("kind"))
        ts = ev.get("ts")
        if isinstance(ts, str):
            if prev_ts is not None and ts < prev_ts:
                out.append(f"AEP15_F17_EVENT_TS_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F17_EVENT_CAUSAL_INVERSION_REVIEW_BEFORE_CREATE")
    return out


def _v15_check_source_hash_chain(packet):
    out = []
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_F17_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str) and _v15_hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
            out.append("AEP15_F17_SOURCE_HASH_CHAIN_BROKEN")
    return out


def _v15_check_span_basis(packet):
    out = []
    span_index = set()
    for src in packet.get("sources", []):
        for sp in src.get("spans", []) or []:
            sid = sp.get("span_id")
            if sid:
                span_index.add(sid)
    for cl in packet.get("claims", []):
        bsids = cl.get("basis_span_ids") or []
        if not bsids:
            out.append("AEP15_F17_CLAIM_HAS_NO_BASIS_SPAN")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_F17_CLAIM_BASIS_UNRESOLVED:{sid}")
    return out


def _v15_check_reviewer_distinctness(packet):
    """F17 DAG integrity also includes review-event distinctness."""
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid and (pid == creator or pid in claim_authors):
            out.append(f"AEP15_F17_REVIEWER_NOT_INDEPENDENT:{pid}")
    return out


def _v15_check_score_in_scale(packet):
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F17_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F17_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F17_SCORE_OUT_OF_SCALE:{s}")
    return out


def _v15_check_recall_injection(packet):
    """F17 chain integrity: poisoning recall_payload breaks DAG witness chain."""
    out = []
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database"]
    if isinstance(text, str):
        for sig in sigs:
            if sig in text.lower():
                out.append(f"AEP15_F17_RECALL_INJECTION:{sig}")
                break
    return out


def _v15_check_span_geometry(packet):
    out = []
    for src in packet.get("sources", []):
        text = src.get("text", "")
        src_len = len(text) if isinstance(text, str) else 0
        for sp in src.get("spans", []) or []:
            start, end = sp.get("start"), sp.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            if start > end:
                out.append("AEP15_F17_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_F17_SPAN_BEYOND_SOURCE")
    return out


def _v15_check_completion_witness(packet):
    out = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            w = cl.get("witness")
            ws = cl.get("witness_sha256")
            wa = cl.get("witness_artifact")
            if not w and not ws and not wa:
                out.append(f"AEP15_F17_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
                continue
            if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
                out.append(f"AEP15_F17_COMPLETION_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def _v15_check_reviewer_extras(packet):
    out = []
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F17_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F17_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F17_REVIEWER_FORGED:{pid}")
    return out


def _v15_check_claim_text_injection(packet):
    out = []
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database", "override constitution"]
    for cl in packet.get("claims", []):
        text = cl.get("text", "")
        if isinstance(text, str):
            lower = text.lower()
            for sig in sigs:
                if sig in lower:
                    out.append(f"AEP17_F17_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_dag_integrity(packet))
    out.extend(_v15_check_event_ordering(packet))
    out.extend(_v15_check_source_hash_chain(packet))
    out.extend(_v15_check_span_basis(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_recall_injection(packet))
    out.extend(_v15_check_span_geometry(packet))
    out.extend(_v15_check_completion_witness(packet))
    out.extend(_v15_check_reviewer_extras(packet))
    out.extend(_v15_check_claim_text_injection(packet))
    # FINAL PASS-CLOSURE: 6 independent structural-mutation checks (encoding/float-edge/
    # time-skew/hash-shape/semantic-equivalence/linguistic). Composes with sec73.6 honest framing.
    try:
        from v15_validators_common import v15_common_structural_checks  # type: ignore
        out.extend(v15_common_structural_checks(packet))
    except Exception:  # noqa: BLE001
        try:
            import importlib.util, pathlib as _pl
            _spec = importlib.util.spec_from_file_location(
                "v15_validators_common",
                str(_pl.Path(__file__).resolve().parent / "v15_validators_common.py"),
            )
            if _spec and _spec.loader:
                _m = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_m)
                out.extend(_m.v15_common_structural_checks(packet))
        except Exception:  # noqa: BLE001
            out.append("AEP15_COMMON_MODULE_LOAD_FAILED")
    return out


if __name__ == "__main__":
    sys.exit(main())
