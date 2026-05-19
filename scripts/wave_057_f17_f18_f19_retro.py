#!/usr/bin/env python3
"""
Wave-057 Phase 3c retro orchestrator: applies F17 + F18 + F19 retroactively to
today's v1.0.3 + v1.0.3.1 + v1.1 cascade and writes a unified retro report to
.claude/_logs/aep-v11-f17-f18-f19-retro.jsonl.

Composes the three builders:
  - F17: convert aep-v103-phase-receipts.jsonl (9 rows) -> packet_history_dag
         events. Verify row-7 has 2 parents (sec41 DAG re-anchor first manual
         instance).
  - F18: trace the v1.0.3 SPEC's basis-source chain (operator source.md ->
         the agent synthesis -> SPEC). Compute laundering_score. Per sec73.6
         HONEST framing, if score is HIGH (>0.5), SHIP that finding.
  - F19: emit witnesses for today's strategist + pathfinder + adversary + forge
         dispatches. Identify expected-but-untouched packets.

Per sec73.6: this retro orchestrator does NOT shape its outputs to be
favorable. If F18 reveals laundering risk, ship it. If F19 reveals coverage
gaps, ship them. Operator's "make it perfect" directive does NOT authorize
hiding laundering or coverage signals.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_f17_packet_history_dag as f17  # noqa: E402
import build_f18_provenance_graph as f18    # noqa: E402
import build_f19_coverage_witness as f19    # noqa: E402


RETRO_OUT = REPO_ROOT / ".claude" / "_logs" / "aep-v11-f17-f18-f19-retro.jsonl"


def _now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_of_file(p: pathlib.Path) -> str:
    if not p.exists():
        return "sha256:missing"
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def run_f17() -> Dict[str, Any]:
    events = f17.retro_build_from_hcrl(f17.HCRL_V103_PATH)
    size_bytes, sha = f17.write_jsonl(events, f17.RETRO_OUTPUT_PATH)
    reanchors = f17.find_re_anchor_events(events)
    # Row-7 in the HCRL was a DAG re-anchor (scribe with prev_receipt_hashes=
    # [warden_row5, judge_row6]). Check the corresponding F17 event.
    row7_evt = next((e for e in events if e["id"].startswith("phe:v103-spec:r7:")), None)
    row7_parents = row7_evt["parent_event_ids"] if row7_evt else []
    walk_fwd = f17.walk_dag_from_event(events, events[0]["id"], "forward") if events else []
    walk_bwd = f17.walk_dag_from_event(events, events[-1]["id"], "backward") if events else []

    return {
        "primitive": "F17",
        "rows_in_hcrl": len(events),
        "events_emitted": len(events),
        "out_path": str(f17.RETRO_OUTPUT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "out_size_bytes": size_bytes,
        "out_sha256": sha,
        "re_anchor_event_ids": reanchors,
        "re_anchor_count": len(reanchors),
        "row_7_event_id": row7_evt["id"] if row7_evt else None,
        "row_7_parent_event_ids": row7_parents,
        "row_7_has_two_parents": len(row7_parents) >= 2,
        "forward_walk_len_from_row_1": len(walk_fwd),
        "backward_walk_len_from_last": len(walk_bwd),
    }


def run_f18() -> Dict[str, Any]:
    # Sample 20 packets + the v103 spec retro trace.
    packets = f18.iter_packet_sources([f18.CONVERTED_ROOT, f18.PILOTS_ROOT], sample_size=20)
    sample_rows: List[Dict[str, Any]] = []
    per_packet_scores: Dict[str, float] = {}
    for packet_id, jsonl_path in packets:
        rows, score = f18.scan_packet(jsonl_path, packet_id)
        sample_rows.extend(rows)
        per_packet_scores[packet_id] = score

    v103_rows, v103_score = f18.trace_v103_spec_lineage()
    sample_rows.extend(v103_rows)
    per_packet_scores["projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md"] = v103_score

    size_bytes, sha = f18.write_jsonl(sample_rows, f18.RETRO_OUTPUT_PATH)
    overall = f18.laundering_score(sample_rows)

    # Honest sec73.6 framing.
    risk_class = "HIGH" if v103_score >= 0.7 else ("MODERATE" if v103_score >= 0.5 else "LOW")

    return {
        "primitive": "F18",
        "sample_packets_scanned": len(packets),
        "spg_rows_emitted": len(sample_rows),
        "out_path": str(f18.RETRO_OUTPUT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "out_size_bytes": size_bytes,
        "out_sha256": sha,
        "v103_spec_laundering_score": v103_score,
        "v103_spec_laundering_risk_class": risk_class,
        "overall_laundering_score_across_sample": overall,
        "per_packet_laundering_scores": per_packet_scores,
        "honest_sec73_6_framing": (
            f"v103 SPEC laundering_score = {v103_score} ({risk_class}). "
            "F18 surfaces this UNSHAPED per sec73.6 — operator-directive "
            "'make it perfect' does NOT authorize hiding the signal that "
            "v1.0.3 SPEC is heavily the agent-synthesized from operator source.md "
            "+ multi-agent ledger rows."
        ),
    }


def run_f19() -> Dict[str, Any]:
    witnesses = f19.today_dispatches_retro()
    size_bytes, sha = f19.write_jsonl(witnesses, f19.RETRO_OUTPUT_PATH)
    total_gaps = sum(len(w["coverage_gap"]) for w in witnesses)
    per_witness = [
        {
            "agent_role": w["agent_role"],
            "invocation_id": w["invocation_id"],
            "coverage_ratio": w["coverage_ratio"],
            "gap_count": len(w["coverage_gap"]),
            "unjustified_gap_count": sum(
                1 for g in w["coverage_gap"]
                if g["justification_required"] and not g["justification_text"]
            ),
            "single_source_convergence_count": w["single_source_attribution"]["convergence_count"],
        }
        for w in witnesses
    ]
    return {
        "primitive": "F19",
        "witnesses_emitted": len(witnesses),
        "out_path": str(f19.RETRO_OUTPUT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "out_size_bytes": size_bytes,
        "out_sha256": sha,
        "total_coverage_gaps": total_gaps,
        "per_witness": per_witness,
        "honest_sec73_6_framing": (
            "F19 is single-source by design (adversary only); "
            f"convergence_count=1 stamped on every witness. "
            f"{total_gaps} total gaps surfaced unshaped across "
            f"{len(witnesses)} dispatches. Each gap has "
            "justification_required=true; agents fill justifications, "
            "validator does NOT auto-resolve per sec73.6."
        ),
    }


def main() -> int:
    started_at = _now_z()
    f17_report = run_f17()
    f18_report = run_f18()
    f19_report = run_f19()

    rows = [
        {"row_kind": "wave_057_retro_meta", "started_at": started_at,
         "ended_at": _now_z(), "wave_id": "wave-057-phase-3c-f17-f18-f19-retro"},
        f17_report,
        f18_report,
        f19_report,
    ]

    RETRO_OUT.parent.mkdir(parents=True, exist_ok=True)
    blob = b""
    with RETRO_OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            line = json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n"
            fh.write(line)
            blob += line.encode("utf-8")
    out_sha = hashlib.sha256(blob).hexdigest()
    summary = {
        "wave": "057",
        "started_at": started_at,
        "ended_at": rows[0]["ended_at"],
        "retro_log_path": str(RETRO_OUT.relative_to(REPO_ROOT)).replace("\\", "/"),
        "retro_log_size_bytes": len(blob),
        "retro_log_sha256": out_sha,
        "f17_row_7_has_two_parents": f17_report["row_7_has_two_parents"],
        "f17_re_anchor_count": f17_report["re_anchor_count"],
        "f18_v103_laundering_score": f18_report["v103_spec_laundering_score"],
        "f18_v103_risk_class": f18_report["v103_spec_laundering_risk_class"],
        "f19_total_gaps": f19_report["total_coverage_gaps"],
        "f19_witnesses": f19_report["witnesses_emitted"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
