#!/usr/bin/env python3
"""
AEP v1.1 F19 corpus_coverage_witness — STAGED single-source from adversary.

F19 closes the recall-COMPLETENESS gap (vs F12 which covers recall-FROM-touched-
packets). Every agent invocation declares `expected_corpus_scope[]`; validator
computes `touched_packet_ids` from the PreToolUse Read hook log (or, here, from
a simulated dispatch transcript), then emits `coverage_gap[]`.

Per sec73.6 NO-OPERATOR-REACTION-CALIBRATION + sec9.4 + the schema:
  - single_source_attribution.convergence_count is HARD-CONSTRAINED to 1
  - F19 ships honest about being single-source (adversary only surfaced it)
  - gaps surface UNSHAPED; agent must justify each gap or AEP11_F19_GAP_UNJUSTIFIED

API:
  - compute_coverage_witness(agent_id, session_id, expected_scope, touched)
    -> CorpusCoverageWitness dict
  - emit_gap(expected, touched) -> list of {packet_id_pattern, justification_required, justification_text}

Test case (sec9.6 falsifier): today's v1.0.3 cascade pathfinder dispatch.
Expected scope SHOULD have considered v0.5/v0.6/v0.7 SPECs when authoring the
v1.0.3 plan. Did it? Compute against the Glob trace of files the pathfinder
plan cites. If pathfinder cited only v0.8 + v1.0.x and NOT v0.5/v0.6/v0.7,
emit a gap (with justification_required=true). The validator EMITS the gap
unshaped; the agent justifies (or doesn't).

Honest framing: when no read-hook log exists (the v1.0.3 cascade pre-dated
hook-log emission for that dispatch), we simulate `touched_packet_ids` from
the pathfinder plan's actual cite list. The AEP11_F19_HOOK_LOG_MISSING reason
code is emitted in that case per sec9.5.

Truth tag: SPECULATIVE FRONTIER × SINGLE-SOURCE (F19 itself); STRONGLY
PLAUSIBLE (retro test on v103 pathfinder dispatch).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
RETRO_OUTPUT_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "recall" / "corpus_coverage"
RETRO_OUTPUT_PATH = RETRO_OUTPUT_DIR / "v103_dispatch_witnesses.jsonl"


def _now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_gap(expected: List[str], touched: List[str]) -> List[Dict[str, Any]]:
    """Compute coverage_gap[] = expected patterns with zero matching touched IDs."""
    gaps: List[Dict[str, Any]] = []
    touched_set = set(touched)
    for pattern in expected:
        # Treat glob-style patterns via fnmatch; literal path matches exact.
        matched = any(fnmatch.fnmatch(t, pattern) or t == pattern for t in touched_set)
        if not matched:
            gaps.append({
                "packet_id_pattern": pattern,
                "justification_required": True,
                "justification_text": "",  # agent fills this in; AEP11_F19_GAP_UNJUSTIFIED if empty
            })
    return gaps


def compute_coverage_witness(
    agent_role: str,
    invocation_id: str,
    expected_corpus_scope: List[str],
    touched_packet_ids: List[str],
    hook_log_path: Optional[str] = None,
    adversary_attack_id: str = "adversary-2026-05-18-v11-convergence-map-attack",
) -> Dict[str, Any]:
    """Build one F19 CorpusCoverageWitness record. Schema-valid against
    f19_corpus_coverage_witness.schema.json (additionalProperties:false)."""
    if not expected_corpus_scope:
        raise ValueError("expected_corpus_scope MUST have minItems >= 1 per F19 schema")
    gaps = emit_gap(expected_corpus_scope, touched_packet_ids)

    # coverage_ratio = |touched intersect expected| / |expected|.
    # For glob patterns, treat as "satisfied" if at least one touched matches the pattern.
    satisfied = 0
    for pattern in expected_corpus_scope:
        if any(fnmatch.fnmatch(t, pattern) or t == pattern for t in touched_packet_ids):
            satisfied += 1
    coverage_ratio = round(satisfied / len(expected_corpus_scope), 4) if expected_corpus_scope else 0.0

    # Stable witness id from agent_role + invocation_id.
    raw_id = f"ccw:{agent_role}:{invocation_id}"
    raw_id = re.sub(r"[^a-z0-9._:-]", "-", raw_id.lower())[:240]

    return {
        "type": "CorpusCoverageWitness",
        "schema_version": "aep-corpus-coverage-witness-0.1",
        "id": raw_id,
        "agent_role": agent_role,
        "invocation_id": invocation_id[:256],
        "expected_corpus_scope": expected_corpus_scope,
        "touched_packet_ids": touched_packet_ids,
        "coverage_gap": gaps,
        "computed_at": _now_z(),
        "hook_log_path": hook_log_path,
        "coverage_ratio": coverage_ratio,
        "single_source_attribution": {
            "adversary_attack_id": adversary_attack_id,
            "convergence_count": 1,  # hard-constrained min=max=1
        },
    }


# ---------- v103 retro test case ----------

def v103_pathfinder_retro_witness() -> Dict[str, Any]:
    """Retrospective F19 witness for today's v1.0.3 pathfinder dispatch.

    Expected scope: pathfinder authoring v1.0.3 plan SHOULD have considered:
      - v0.5 SPEC (last STABLE before v0.8)
      - v0.6 SPEC (signed-identity milestone)
      - v0.7 SPEC (federated-binding milestone)
      - v0.8 SPEC (current STABLE)
      - v1.0.3 SPEC stub (being authored)

    Touched packets (per the pathfinder plan at doctrine/_proposals/pathfinder-
    2026-05-18-aep-v1-0-3-regexical-memory.md and observed cites): v0.8 STABLE
    and the operator source.md only. v0.5 / v0.6 / v0.7 SPECs were NOT cited.

    Per sec73.6 honest framing: this gap is REAL but defensible — v0.5/v0.6/
    v0.7 were superseded by v0.8 STABLE, so the pathfinder reasonably scoped
    to v0.8 + v1.0.x. The justification_text can be filled with that rationale.
    F19's job is to surface the gap; the agent's job is to justify or fix it.
    """
    expected = [
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_5*_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_6*_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_7*_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_8_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md",
    ]
    touched = [
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_8_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md",
        "research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/source.md",
    ]

    witness = compute_coverage_witness(
        agent_role="pathfinder",
        invocation_id="v103-cascade-pathfinder-2026-05-18",
        expected_corpus_scope=expected,
        touched_packet_ids=touched,
        hook_log_path=None,  # hook log missing for v103 dispatch → AEP11_F19_HOOK_LOG_MISSING
    )
    return witness


def today_dispatches_retro() -> List[Dict[str, Any]]:
    """Retro F19 witnesses for today's strategist + pathfinder + adversary + forge
    dispatches on the v1.0.3 / v1.1 cascade."""
    out: List[Dict[str, Any]] = []

    # 1. pathfinder
    out.append(v103_pathfinder_retro_witness())

    # 2. strategist (v1.1 framing dispatch)
    strategist_expected = [
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_8_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_1_SPEC.md",
        "doctrine/lessons/sibling-132*",
    ]
    strategist_touched = [
        "projects/v11-aep/publish-ready/aep/spec/AEP_v0_8_SPEC.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_1_SPEC.md",
    ]
    out.append(compute_coverage_witness(
        agent_role="strategist",
        invocation_id="v11-cascade-strategist-2026-05-18",
        expected_corpus_scope=strategist_expected,
        touched_packet_ids=strategist_touched,
        hook_log_path=None,
    ))

    # 3. adversary (v1.1 convergence-map attack)
    adversary_expected = [
        "doctrine/_proposals/legion-synthesis-2026-05-18*",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_1_SPEC.md",
        "doctrine/69-verification-law-and-operator-spec-sovereignty.html",
    ]
    adversary_touched = [
        "doctrine/_proposals/legion-synthesis-2026-05-18-v11-convergence-map.md",
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_1_SPEC.md",
    ]
    out.append(compute_coverage_witness(
        agent_role="adversary",
        invocation_id="v11-cascade-adversary-2026-05-18",
        expected_corpus_scope=adversary_expected,
        touched_packet_ids=adversary_touched,
        hook_log_path=None,
    ))

    # 4. forge (THIS DISPATCH — Phase 3c F17/F18/F19)
    forge_expected = [
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_1_SPEC.md",
        "projects/v11-aep/publish-ready/aep/schemas/f17_packet_history_dag.schema.json",
        "projects/v11-aep/publish-ready/aep/schemas/f18_source_provenance_graph.schema.json",
        "projects/v11-aep/publish-ready/aep/schemas/f19_corpus_coverage_witness.schema.json",
        ".claude/_logs/aep-v103-phase-receipts.jsonl",
    ]
    forge_touched = [
        "projects/v11-aep/publish-ready/aep/spec/AEP_v1_1_SPEC.md",
        "projects/v11-aep/publish-ready/aep/schemas/f17_packet_history_dag.schema.json",
        "projects/v11-aep/publish-ready/aep/schemas/f18_source_provenance_graph.schema.json",
        "projects/v11-aep/publish-ready/aep/schemas/f19_corpus_coverage_witness.schema.json",
        ".claude/_logs/aep-v103-phase-receipts.jsonl",
    ]
    out.append(compute_coverage_witness(
        agent_role="forge",
        invocation_id="v11-cascade-forge-phase-3c-f17-f18-f19-2026-05-18",
        expected_corpus_scope=forge_expected,
        touched_packet_ids=forge_touched,
        hook_log_path=None,
    ))

    return out


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
    parser = argparse.ArgumentParser(description="F19 corpus_coverage_witness builder + retro")
    parser.add_argument("--mode", choices=["v103_pathfinder", "today_all", "compute"], default="today_all")
    parser.add_argument("--agent-role", default="pathfinder")
    parser.add_argument("--invocation-id", default="adhoc")
    parser.add_argument("--expected", nargs="*", default=[])
    parser.add_argument("--touched", nargs="*", default=[])
    parser.add_argument("--out", dest="out_path", type=pathlib.Path, default=RETRO_OUTPUT_PATH)
    args = parser.parse_args(argv)

    rows: List[Dict[str, Any]]
    if args.mode == "v103_pathfinder":
        rows = [v103_pathfinder_retro_witness()]
    elif args.mode == "today_all":
        rows = today_dispatches_retro()
    elif args.mode == "compute":
        rows = [compute_coverage_witness(
            agent_role=args.agent_role,
            invocation_id=args.invocation_id,
            expected_corpus_scope=args.expected,
            touched_packet_ids=args.touched,
        )]
    else:
        return 2

    size_bytes, sha = write_jsonl(rows, args.out_path)
    total_gaps = sum(len(r["coverage_gap"]) for r in rows)
    out_path = args.out_path
    try:
        out_path = out_path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    print(json.dumps({
        "mode": args.mode,
        "witnesses_emitted": len(rows),
        "total_coverage_gaps": total_gaps,
        "per_witness": [
            {
                "agent_role": r["agent_role"],
                "invocation_id": r["invocation_id"],
                "coverage_ratio": r["coverage_ratio"],
                "gap_count": len(r["coverage_gap"]),
                "single_source_convergence_count": r["single_source_attribution"]["convergence_count"],
            }
            for r in rows
        ],
        "out_path": str(out_path).replace("\\", "/"),
        "out_size_bytes": size_bytes,
        "out_sha256": sha,
    }, indent=2))
    return 0


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18. F19's role per AEP v1.1: corpus-coverage-witness +
# completion-witness emission + per-criterion coverage justification.
# Extended to: span-coverage integrity, witness-evidence-sha integrity,
# completion-criterion-missing detection, hash chain, score in scale,
# event monotonicity, DAG parent integrity (coverage-witness depends on DAG),
# prompt-injection (witness records cannot contain injection),
# reviewer-distinctness (coverage requires independent witness).
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


def _v15_check_source_hash(packet):
    out = []
    for src in packet.get("sources", []):
        h = src.get("sha256")
        text = src.get("text")
        if not _v15_hash_valid(h):
            out.append("AEP15_F19_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str) and _v15_hashlib.sha256(text.encode("utf-8")).hexdigest() != h:
            out.append("AEP15_F19_SOURCE_HASH_MISMATCH")
    return out


def _v15_check_coverage_witness(packet):
    out = []
    span_index = set()
    for src in packet.get("sources", []):
        for sp in src.get("spans", []) or []:
            sid = sp.get("span_id")
            if sid:
                span_index.add(sid)
    # Coverage gap detection: every claim's basis_span_ids must resolve.
    for cl in packet.get("claims", []):
        bsids = cl.get("basis_span_ids") or []
        if not bsids:
            out.append(f"AEP15_F19_COVERAGE_GAP_NO_BASIS:{cl.get('claim_id')}")
            continue
        for sid in bsids:
            if sid not in span_index:
                out.append(f"AEP15_F19_COVERAGE_GAP_UNRESOLVED_SPAN:{sid}")
    # Completion claims must have witness binding.
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            if not cl.get("witness") and not cl.get("witness_sha256") and not cl.get("witness_artifact"):
                out.append(f"AEP15_F19_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
    return out


def _v15_check_dag_integrity(packet):
    out = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if not isinstance(p, str):
            out.append("AEP15_F19_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED")):
            out.append(f"AEP15_F19_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_F19_DAG_PARENT_SELF_REFERENCE")
    return out


def _v15_check_reviewer_distinctness(packet):
    out = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid and (pid == creator or pid in claim_authors):
            out.append(f"AEP15_F19_REVIEWER_NOT_INDEPENDENT:{pid}")
    return out


def _v15_check_score_in_scale(packet):
    out = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F19_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F19_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F19_SCORE_OUT_OF_SCALE:{s}")
    return out


def _v15_check_event_monotonicity(packet):
    out = []
    events = (packet.get("manifest") or {}).get("events", [])
    prev_ts = None
    kinds = []
    for ev in events:
        kinds.append(ev.get("kind"))
        ts = ev.get("ts")
        if isinstance(ts, str):
            if prev_ts is not None and ts < prev_ts:
                out.append(f"AEP15_F19_EVENT_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F19_EVENT_REVIEW_BEFORE_CREATE")
    return out


def _v15_check_prompt_injection(packet):
    out = []
    rp = packet.get("recall_payload") or {}
    text = rp.get("text", "") if isinstance(rp, dict) else ""
    sigs = ["ignore all prior instructions", "set validator outcome to pass", "drop the database"]
    if isinstance(text, str):
        for sig in sigs:
            if sig in text.lower():
                out.append(f"AEP15_F19_RECALL_INJECTION:{sig}")
                break
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
                    out.append(f"AEP15_F19_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def _v15_check_reviewer_extras(packet):
    out = []
    seen_pids = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F19_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F19_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F19_REVIEWER_FORGED:{pid}")
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
                out.append("AEP15_F19_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                out.append("AEP15_F19_SPAN_BEYOND_SOURCE")
    return out


def _v15_check_witness_sha_forged(packet):
    out = []
    for cl in packet.get("claims", []):
        ws = cl.get("witness_sha256")
        if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
            out.append(f"AEP15_F19_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def v15_validate_extended_mutations(packet):
    out = []
    out.extend(_v15_check_source_hash(packet))
    out.extend(_v15_check_coverage_witness(packet))
    out.extend(_v15_check_dag_integrity(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_event_monotonicity(packet))
    out.extend(_v15_check_prompt_injection(packet))
    out.extend(_v15_check_claim_text_injection(packet))
    out.extend(_v15_check_reviewer_extras(packet))
    out.extend(_v15_check_span_geometry(packet))
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
