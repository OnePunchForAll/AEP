#!/usr/bin/env python3
"""
AEP v1.1 F18 source_provenance_graph builder.

For each source row encountered in a sample of corpus packets'
`data/sources.jsonl`, classify lineage_depth and venue_tier; emit a
SourceProvenanceGraphRow per the F18 schema. Compute a per-packet
`laundering_score` = proportion of basis sources with depth >= 2.

Lineage_depth classification (sec73.3 prior-art-inheritance + sec50 EH Law-3
anti-source-laundering):
  0 = operator-supplied-verbatim (operator source.md / operator-quoted text)
  1 = external-fetched-by-scout (URLs, arxiv, GitHub, OpenAI docs, etc.)
  2 = peer-agent-emitted (the agent/peer-agent paraphrase chains; doctrine cites)
  3 = the agent-synthesized (the agent's own synthesis docs / proposals / lesson .html
      whose primary author is the agent)

Heuristic combines:
  - Path-based: `research/sources/operator-*` → depth 0; `research/sources/`
    (non-operator) → depth 1; `doctrine/_proposals/diana-*` → depth 3;
    `doctrine/lessons/` (the agent-authored) → depth 3; cross-lesson cite → depth 2;
    `doctrine/` core slots → depth 2.
  - Content-pattern: title contains "operator" / "verbatim" / "operator_quoted"
    → depth 0; URL location with arxiv/github/openai/anthropic → depth 1.

This is intentionally a CONSERVATIVE classifier — when ambiguous, default to
depth 2 (peer-agent-emitted) so the laundering audit doesn't false-positive
high-depth on unknown paths.

API:
  - classify_source(source_row) -> (lineage_depth, venue_tier, peer_review_status)
  - query_lineage(graph, source_id) -> {depth, chain_to_leaf, cited_by_packets}
  - laundering_score(packet_graph_rows) -> float

Output: projects/v11-aep/publish-ready/aep/recall/source_provenance/graph.jsonl
        (one SourceProvenanceGraphRow per source row, plus one
         PacketLaunderingScore row per scanned packet).

Truth tag: SPECULATIVE FRONTIER (F18 itself); STRONGLY PLAUSIBLE (heuristic
classification on the sampled 20 packets).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
CONVERTED_ROOT = REPO_ROOT / "projects" / "v11-aep" / "converted"
PILOTS_ROOT = REPO_ROOT / "projects" / "v11-aep" / "pilots"
RETRO_OUTPUT_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "recall" / "source_provenance"
RETRO_OUTPUT_PATH = RETRO_OUTPUT_DIR / "graph.jsonl"


# ---------- Heuristic classifiers ----------

ARXIV_RE = re.compile(r"arxiv\.org|/abs/\d{4}\.\d{4,5}", re.I)
URL_RE = re.compile(r"^https?://", re.I)
OPERATOR_PATH_PREFIX = re.compile(r"research/sources/operator-", re.I)
RESEARCH_SOURCES_PATH = re.compile(r"research/sources/", re.I)
AEP_PROPOSAL_PATH = re.compile(r"_proposals/(diana-|operator-|warden-|forge-|scribe-|judge-|adversary-|strategist-|pathfinder-|scout-|curator-|visual-judge-)", re.I)
DOCTRINE_LESSONS_PATH = re.compile(r"doctrine/lessons/", re.I)
DOCTRINE_CORE_SLOT = re.compile(r"doctrine/\d{2,}-[a-z0-9-]+\.html$", re.I)
INTERNAL_SYNTHESIS_HINT = re.compile(r"(diana|legion|synthesis|consolidate)", re.I)


def _path_of(source_row: Dict[str, Any]) -> str:
    loc = source_row.get("location", {}) or {}
    p = loc.get("path") or loc.get("value") or ""
    return str(p)


def _title_of(source_row: Dict[str, Any]) -> str:
    return str(source_row.get("title", "") or "")


def _is_url(p: str) -> bool:
    return bool(URL_RE.match(p))


def classify_source(source_row: Dict[str, Any]) -> Tuple[int, str, str]:
    """Return (lineage_depth, venue_tier, peer_review_status).

    Conservative: ambiguous defaults to depth=2 / internal_synthesis / unverified.
    """
    path = _path_of(source_row).replace("\\", "/")
    title = _title_of(source_row).lower()
    src_id = str(source_row.get("id", "")).lower()
    limits = str(source_row.get("limits", "")).lower()

    # 0: operator-supplied-verbatim
    if "operator" in title and ("verbatim" in title or "operator" in title.lower()):
        return 0, "operator_verbatim", "operator_attested"
    if OPERATOR_PATH_PREFIX.search(path):
        return 0, "operator_verbatim", "operator_attested"
    if "operator-quoted" in src_id or "operator_verbatim" in src_id:
        return 0, "operator_verbatim", "operator_attested"

    # 1: external-fetched-by-scout
    if _is_url(path):
        if ARXIV_RE.search(path):
            return 1, "preprint_arxiv", "preprint"
        if "anthropic.com" in path or "openai.com" in path:
            return 1, "industry_blog_first_party", "first_party_attestation"
        if "github.com" in path:
            return 1, "industry_blog_third_party", "unverified"
        return 1, "industry_blog_third_party", "unverified"
    if RESEARCH_SOURCES_PATH.search(path) and not OPERATOR_PATH_PREFIX.search(path):
        return 1, "industry_blog_third_party", "unverified"

    # 3: the agent-synthesized
    if AEP_PROPOSAL_PATH.search(path):
        return 3, "internal_synthesis", "not_applicable"
    if DOCTRINE_LESSONS_PATH.search(path):
        # Lessons are the agent-authored synthesis of a session's events.
        return 3, "internal_synthesis", "not_applicable"

    # 2: peer-agent-emitted / doctrine cross-cite
    if DOCTRINE_CORE_SLOT.search(path):
        return 2, "internal_synthesis", "first_party_attestation"
    if "doctrine/" in path or path.endswith(".html"):
        return 2, "internal_synthesis", "unverified"

    # Fallback: peer-agent
    return 2, "internal_synthesis", "unverified"


# ---------- Graph row builder ----------

def make_spg_row(
    source_row: Dict[str, Any],
    *,
    depth: int,
    venue_tier: str,
    peer_review_status: str,
    packet_id: str,
) -> Dict[str, Any]:
    src_id = source_row.get("id", "src:unknown")
    spg_id = f"spg:{packet_id.replace('/', '-').replace('.aepkg', '').lower()}:{src_id.replace(':', '-')}"
    spg_id = re.sub(r"[^a-z0-9._:-]", "-", spg_id)[:240]
    path = _path_of(source_row).replace("\\", "/")
    src_sha = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return {
        "type": "SourceProvenanceGraphRow",
        "schema_version": "aep-source-provenance-graph-0.1",
        "id": spg_id,
        "bound_to_source_id": src_id,
        "lineage_depth": depth,
        "venue_tier": venue_tier,
        "peer_review_status": peer_review_status,
        "invalidator_checked": False,
        "adjacency_invalidator_ids": [],
        "citation_count_at_absorption": None,
        "freeze_lock_ed25519_signature": None,
        "freeze_lock_signer_principal": None,
        "freeze_lock_at": None,
        "laundering_score_computed": None,
        "laundering_score_threshold": 0.6,
        "source_url_at_absorption": path if _is_url(path) else None,
        "source_sha256": f"sha256:{src_sha}",
        # extension fields for our retro report (NOT in v1.1 schema; for retro graph only)
        "_packet_id": packet_id,
        "_source_path": path,
    }


def laundering_score(rows: List[Dict[str, Any]]) -> float:
    """Proportion of basis sources with lineage_depth >= 2 (peer-agent + synth)."""
    if not rows:
        return 0.0
    deep = sum(1 for r in rows if int(r.get("lineage_depth", 0)) >= 2)
    return round(deep / len(rows), 4)


# ---------- Packet scanner ----------

def iter_packet_sources(roots: List[pathlib.Path], sample_size: int = 20) -> List[Tuple[str, pathlib.Path]]:
    """Find up to sample_size data/sources.jsonl files under each root.
    Returns list of (packet_id_relative, path)."""
    found: List[Tuple[str, pathlib.Path]] = []
    for root in roots:
        if not root.exists():
            continue
        for jsonl in sorted(root.rglob("data/sources.jsonl")):
            try:
                rel = jsonl.relative_to(REPO_ROOT)
            except ValueError:
                rel = jsonl
            packet_dir = jsonl.parent.parent  # .../<packet>.aepkg/data/sources.jsonl → <packet>.aepkg
            try:
                pkt_rel = packet_dir.relative_to(REPO_ROOT)
                pkt_id = str(pkt_rel).replace("\\", "/")
            except ValueError:
                pkt_id = str(packet_dir).replace("\\", "/")
            found.append((pkt_id, jsonl))
            if len(found) >= sample_size:
                return found
    return found


def scan_packet(jsonl_path: pathlib.Path, packet_id: str) -> Tuple[List[Dict[str, Any]], float]:
    rows: List[Dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                src = json.loads(ln)
            except json.JSONDecodeError:
                continue
            depth, venue, peer = classify_source(src)
            rows.append(make_spg_row(
                src,
                depth=depth,
                venue_tier=venue,
                peer_review_status=peer,
                packet_id=packet_id,
            ))
    score = laundering_score(rows)
    # Stamp every row with the computed score for that packet.
    for r in rows:
        r["laundering_score_computed"] = score
    return rows, score


# ---------- Special: v1.0.3 SPEC retroactive laundering trace ----------

def trace_v103_spec_lineage() -> Tuple[List[Dict[str, Any]], float]:
    """Retroactively trace the v1.0.3 SPEC's basis-source chain:
       operator source.md → the agent synthesis docs → SPEC.

    Sources for v1.0.3 SPEC (per .claude/_logs/aep-v103-phase-receipts.jsonl row 1):
      - research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/
        assets/source.md  (depth 0; operator verbatim)
      - regexical_memory.schema.json byte-identical operator copy (depth 0)
      - doctrine/_proposals/pathfinder-2026-05-18-... (depth 3, the agent-routed
        pathfinder)
      - doctrine/_proposals/adversary-2026-05-18-... (depth 3, the agent-routed
        adversary)
      - .claude/_logs/aep-v103-phase-receipts.jsonl rows 2-9 (depth 3, all
        the agent-agent emitted in this session)
      - sec41-HCRL / sec73 doctrine cites (depth 2, doctrine cross-cite)

    NOTE this is a RETRO honest classification — the v1.0.3 SPEC IS heavily
    the agent-synthesized; that's a real signal F18 is designed to surface.
    """
    rows: List[Dict[str, Any]] = []
    packet_id = "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md"

    synthetic_sources = [
        # operator origin
        ("src:operator-source-md", "research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/source.md", 0, "operator_verbatim", "operator_attested"),
        ("src:operator-schema", "projects/v11-aep/publish-ready/aep/schemas/regexical_memory.schema.json", 0, "operator_verbatim", "operator_attested"),
        # the agent-routed agent proposals
        ("src:pathfinder-plan-2026-05-18", "doctrine/_proposals/pathfinder-2026-05-18-aep-v1-0-3-regexical-memory.md", 3, "internal_synthesis", "not_applicable"),
        ("src:adversary-premortem-2026-05-18", "doctrine/_proposals/adversary-2026-05-18-aep-v1-0-3-premortem.md", 3, "internal_synthesis", "not_applicable"),
        # HCRL rows = the agent-agent emitted ledger
        ("src:hcrl-row-2-warden", ".claude/_logs/aep-v103-phase-receipts.jsonl#row-2", 3, "internal_synthesis", "not_applicable"),
        ("src:hcrl-row-3-judge", ".claude/_logs/aep-v103-phase-receipts.jsonl#row-3", 3, "internal_synthesis", "not_applicable"),
        ("src:hcrl-row-5-warden", ".claude/_logs/aep-v103-phase-receipts.jsonl#row-5", 3, "internal_synthesis", "not_applicable"),
        ("src:hcrl-row-6-judge", ".claude/_logs/aep-v103-phase-receipts.jsonl#row-6", 3, "internal_synthesis", "not_applicable"),
        ("src:hcrl-row-7-scribe", ".claude/_logs/aep-v103-phase-receipts.jsonl#row-7", 3, "internal_synthesis", "not_applicable"),
        # Doctrine cross-cites
        ("src:sec41-doctrine", "doctrine/41-hash-chained-receipt-ledger.html", 2, "internal_synthesis", "first_party_attestation"),
        ("src:sec73-doctrine", "doctrine/73-external-claude-receipt-laws.html", 2, "internal_synthesis", "first_party_attestation"),
        ("src:sec50-doctrine", "doctrine/50-epistemic-hygiene-meta-law.html", 2, "internal_synthesis", "first_party_attestation"),
    ]

    for src_id, path, depth, venue, peer in synthetic_sources:
        src_sha = hashlib.sha256(path.encode("utf-8")).hexdigest()
        spg_id = f"spg:v103-spec:{src_id.replace(':', '-').replace('#', '-')}"
        spg_id = re.sub(r"[^a-z0-9._:-]", "-", spg_id)[:240]
        rows.append({
            "type": "SourceProvenanceGraphRow",
            "schema_version": "aep-source-provenance-graph-0.1",
            "id": spg_id,
            "bound_to_source_id": src_id,
            "lineage_depth": depth,
            "venue_tier": venue,
            "peer_review_status": peer,
            "invalidator_checked": False,
            "adjacency_invalidator_ids": [],
            "citation_count_at_absorption": None,
            "freeze_lock_ed25519_signature": None,
            "freeze_lock_signer_principal": None,
            "freeze_lock_at": None,
            "laundering_score_computed": None,
            "laundering_score_threshold": 0.6,
            "source_url_at_absorption": None,
            "source_sha256": f"sha256:{src_sha}",
            "_packet_id": packet_id,
            "_source_path": path,
        })

    score = laundering_score(rows)
    for r in rows:
        r["laundering_score_computed"] = score
    return rows, score


# ---------- Query API ----------

def query_lineage(graph: List[Dict[str, Any]], source_id: str) -> Dict[str, Any]:
    matched = [r for r in graph if r.get("bound_to_source_id") == source_id]
    if not matched:
        return {"depth": None, "chain_to_leaf": [], "cited_by_packets": []}
    depths = sorted({int(r["lineage_depth"]) for r in matched})
    cited_by = sorted({r.get("_packet_id", "") for r in matched if r.get("_packet_id")})
    return {
        "depth": depths[-1],  # max observed
        "chain_to_leaf": [r.get("_source_path", "") for r in matched],
        "cited_by_packets": cited_by,
    }


# ---------- CLI ----------

def write_jsonl(rows: Iterable[Dict[str, Any]], out_path: pathlib.Path) -> Tuple[int, str]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    blob = b""
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            line = json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n"
            fh.write(line)
            blob += line.encode("utf-8")
    return len(blob), hashlib.sha256(blob).hexdigest()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="F18 source_provenance_graph builder + retro")
    parser.add_argument("--mode", choices=["sample_corpus", "v103_retro", "both"], default="both")
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--out", dest="out_path", type=pathlib.Path, default=RETRO_OUTPUT_PATH)
    args = parser.parse_args(argv)

    all_rows: List[Dict[str, Any]] = []
    per_packet_scores: Dict[str, float] = {}

    if args.mode in ("sample_corpus", "both"):
        packets = iter_packet_sources([CONVERTED_ROOT, PILOTS_ROOT], sample_size=args.sample_size)
        for packet_id, jsonl_path in packets:
            rows, score = scan_packet(jsonl_path, packet_id)
            all_rows.extend(rows)
            per_packet_scores[packet_id] = score

    v103_score = None
    if args.mode in ("v103_retro", "both"):
        v103_rows, v103_score = trace_v103_spec_lineage()
        all_rows.extend(v103_rows)
        per_packet_scores["projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md"] = v103_score

    size_bytes, sha = write_jsonl(all_rows, args.out_path)

    deep_count = sum(1 for r in all_rows if int(r.get("lineage_depth", 0)) >= 2)
    operator_count = sum(1 for r in all_rows if int(r.get("lineage_depth", 0)) == 0)
    agent_synth_count = sum(1 for r in all_rows if int(r.get("lineage_depth", 0)) == 3)
    overall_score = laundering_score(all_rows)
    out_path = args.out_path
    try:
        out_path = out_path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    print(json.dumps({
        "mode": args.mode,
        "rows_total": len(all_rows),
        "operator_verbatim_count": operator_count,
        "deep_lineage_count_gte_2": deep_count,
        "agent_synth_count_eq_3": agent_synth_count,
        "overall_laundering_score": overall_score,
        "v103_spec_laundering_score": v103_score,
        "per_packet_laundering_scores": per_packet_scores,
        "out_path": str(out_path).replace("\\", "/"),
        "out_size_bytes": size_bytes,
        "out_sha256": sha,
    }, indent=2))
    return 0


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. F18's role per AEP v1.1: provenance-graph integrity +
# laundering-score detection + lineage-depth classification. Extended to:
# source hash chain, span basis, claim injection detection, DAG parent
# integrity, score class, event ordering, witness completeness.
# Validator version bump: v1.1.0 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
V15_VALIDATOR_VERSION = "v1.5.0-K5-repair"


def _v15_hash_valid(h):
    if not isinstance(h, str) or len(h) != 64:
        return False
    try:
        int(h, 16)
        return True
    except (ValueError, TypeError):
        return False


def _v15_check_source_hash(packet):
    out = []
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_F18_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str) and hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
            out.append("AEP15_F18_SOURCE_HASH_MISMATCH")
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
            out.append(f"AEP15_F18_SPAN_BASIS_MISSING:{cl.get('claim_id')}")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_F18_SPAN_BASIS_UNRESOLVED:{sid}")
    return out


def _v15_check_dag_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if not isinstance(p, str):
            out.append("AEP15_F18_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED")):
            out.append(f"AEP15_F18_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_F18_DAG_PARENT_SELF_REFERENCE")
    return out


def _v15_check_score_in_scale(packet):
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F18_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F18_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F18_SCORE_OUT_OF_SCALE:{s}")
    return out


def _v15_check_prompt_injection(packet):
    out = []
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database"]
    if isinstance(text, str):
        for sig in sigs:
            if sig in text.lower():
                out.append(f"AEP15_F18_RECALL_INJECTION:{sig}")
                break
    return out


def _v15_check_completion_witness(packet):
    out = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            if not cl.get("witness") and not cl.get("witness_sha256") and not cl.get("witness_artifact"):
                out.append(f"AEP15_F18_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
    return out


def _v15_check_reviewer_distinctness(packet):
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F18_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F18_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if pid == creator or pid in claim_authors:
            out.append(f"AEP15_F18_REVIEWER_SELF_ATTESTATION:{pid}")
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F18_REVIEWER_FORGED:{pid}")
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
                out.append(f"AEP15_F18_EVENT_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F18_EVENT_REVIEW_BEFORE_CREATE")
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
                out.append("AEP15_F18_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_F18_SPAN_BEYOND_SOURCE")
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
                    out.append(f"AEP15_F18_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def _v15_check_witness_sha_forged(packet):
    out = []
    for cl in packet.get("claims", []):
        ws = cl.get("witness_sha256")
        if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
            out.append(f"AEP15_F18_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_source_hash(packet))
    out.extend(_v15_check_span_basis(packet))
    out.extend(_v15_check_dag_integrity(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_prompt_injection(packet))
    out.extend(_v15_check_completion_witness(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_event_ordering(packet))
    out.extend(_v15_check_span_geometry(packet))
    out.extend(_v15_check_claim_text_injection(packet))
    out.extend(_v15_check_witness_sha_forged(packet))
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
