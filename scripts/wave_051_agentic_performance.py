#!/usr/bin/env python3
"""wave_051_agentic_performance.py — Per-agent + cross-agent performance analyzer.

Reads .claude/agents/_ledgers/<agent>.jsonl for each of the 10 canonical agents
(+ visual-judge), computes per-agent metrics, cross-agent metrics, and emits a
comprehensive markdown report at projects/v11-aep/AGENTIC-PERFORMANCE-V1.0.2-2026-05-17.md.

Per operator "wheres the measured performance of our agents with the new aep" 2026-05-17.
Composes with AGENTIC-CAPABILITIES-V1.0.2 (Wave-046) which measured SUBSTRATE perf;
this fills the gap with AGENT-specific perf.

Per §V80-17 v1.0.2 substrate discipline:
  - Stdlib only (json, pathlib, datetime, collections, statistics)
  - Receipt to .claude/_logs/agentic-performance-receipts.jsonl
  - HCRL Lamport via existing chain
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import statistics
import sys
from typing import Any, Dict, List


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
LEDGER_DIR = REPO_ROOT / ".claude" / "agents" / "_ledgers"
OUTPUT_DOC = REPO_ROOT / "projects" / "v11-aep" / "AGENTIC-PERFORMANCE-V1.0.2-2026-05-17.md"
RECEIPT_LEDGER = REPO_ROOT / ".claude" / "_logs" / "agentic-performance-receipts.jsonl"

CANONICAL_AGENTS = [
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
]

NOW = dt.datetime.now(dt.timezone.utc)
NOW_ISO = NOW.isoformat().replace("+00:00", "Z")


def load_ledger(agent: str) -> List[Dict[str, Any]]:
    path = LEDGER_DIR / f"{agent}.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            if "_meta" in d:
                continue
            rows.append(d)
        except json.JSONDecodeError:
            continue
    return rows


def parse_date(s: str) -> dt.datetime:
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d
    except Exception:
        try:
            return dt.datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except Exception:
            return NOW


def agent_metrics(agent: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"agent": agent, "total_invocations": 0, "EMPTY_LEDGER": True}

    dates = [parse_date(r.get("date", "")) for r in rows]
    dates_sorted = sorted(dates)
    last_7d = NOW - dt.timedelta(days=7)
    last_30d = NOW - dt.timedelta(days=30)
    invocations_7d = sum(1 for d in dates if d.replace(tzinfo=d.tzinfo or dt.timezone.utc) >= last_7d)
    invocations_30d = sum(1 for d in dates if d.replace(tzinfo=d.tzinfo or dt.timezone.utc) >= last_30d)

    outcomes = collections.Counter()
    truth_tags = collections.Counter()
    cluster_tag_counts = collections.Counter()
    notes_lengths = []
    wave_mentions = collections.Counter()
    veto_rows = 0
    high_veto_rows = 0
    artifact_rows = 0
    session_ids = collections.Counter()

    for r in rows:
        outcomes[r.get("outcome", "UNKNOWN")] += 1
        truth_tags[r.get("truth_tag", "UNKNOWN")] += 1
        for ct in (r.get("cluster_tags") or []):
            cluster_tag_counts[ct] += 1
        if r.get("notes"):
            notes_lengths.append(len(str(r["notes"])))
        if r.get("artifact_path"):
            artifact_rows += 1
        sid = r.get("session_id") or "(no-session-id)"
        session_ids[sid] += 1
        # Wave references in notes/invocation
        text = (r.get("invocation") or "") + " " + str(r.get("notes") or "")
        for m in re.findall(r"[Ww]ave[- _]?(\d{3,4}[a-z]?)", text):
            wave_mentions[m] += 1
        # VETO detection
        text_lower = text.lower()
        if "veto" in text_lower:
            veto_rows += 1
            if "high" in text_lower or "high-veto" in text_lower:
                high_veto_rows += 1

    return {
        "agent": agent,
        "total_invocations": len(rows),
        "first_invocation": dates_sorted[0].isoformat() if dates_sorted else None,
        "last_invocation": dates_sorted[-1].isoformat() if dates_sorted else None,
        "invocations_last_7d": invocations_7d,
        "invocations_last_30d": invocations_30d,
        "outcome_distribution": dict(outcomes.most_common()),
        "truth_tag_distribution": dict(truth_tags.most_common()),
        "top_5_cluster_tags": dict(cluster_tag_counts.most_common(5)),
        "wave_participation_count": len(wave_mentions),
        "top_5_waves": dict(wave_mentions.most_common(5)),
        "veto_mentions": veto_rows,
        "high_veto_mentions": high_veto_rows,
        "artifact_rows": artifact_rows,
        "unique_sessions": len(session_ids),
        "notes_quality_proxy": {
            "mean_notes_length": int(statistics.mean(notes_lengths)) if notes_lengths else 0,
            "median_notes_length": int(statistics.median(notes_lengths)) if notes_lengths else 0,
            "p95_notes_length": int(sorted(notes_lengths)[min(len(notes_lengths)-1, int(len(notes_lengths)*0.95))]) if notes_lengths else 0,
        },
    }


def cross_agent_metrics(all_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_invocations = sum(m["total_invocations"] for m in all_metrics)
    total_7d = sum(m.get("invocations_last_7d", 0) for m in all_metrics)
    total_30d = sum(m.get("invocations_last_30d", 0) for m in all_metrics)
    total_vetoes = sum(m.get("veto_mentions", 0) for m in all_metrics)
    total_high_vetoes = sum(m.get("high_veto_mentions", 0) for m in all_metrics)
    total_artifacts = sum(m.get("artifact_rows", 0) for m in all_metrics)

    # Most-active agent ranking
    sorted_by_invocations = sorted(all_metrics, key=lambda m: m["total_invocations"], reverse=True)
    ranking = [(m["agent"], m["total_invocations"]) for m in sorted_by_invocations]

    # Most-recent activity ranking
    sorted_by_7d = sorted(all_metrics, key=lambda m: m.get("invocations_last_7d", 0), reverse=True)
    recent_ranking = [(m["agent"], m.get("invocations_last_7d", 0)) for m in sorted_by_7d]

    # Aggregate truth-tag distribution
    truth_total = collections.Counter()
    for m in all_metrics:
        for tag, cnt in (m.get("truth_tag_distribution") or {}).items():
            truth_total[tag] += cnt

    # Aggregate outcome distribution
    outcome_total = collections.Counter()
    for m in all_metrics:
        for tag, cnt in (m.get("outcome_distribution") or {}).items():
            outcome_total[tag] += cnt

    return {
        "total_invocations_across_all_agents": total_invocations,
        "total_invocations_last_7d": total_7d,
        "total_invocations_last_30d": total_30d,
        "total_veto_mentions": total_vetoes,
        "total_high_veto_mentions": total_high_vetoes,
        "total_artifact_rows": total_artifacts,
        "ranking_by_total_invocations": ranking,
        "ranking_by_last_7d_activity": recent_ranking,
        "aggregate_truth_tag_distribution": dict(truth_total.most_common()),
        "aggregate_outcome_distribution": dict(outcome_total.most_common()),
        "n_agents_tracked": len(all_metrics),
        "n_agents_with_recent_activity_7d": sum(1 for m in all_metrics if m.get("invocations_last_7d", 0) > 0),
        "n_agents_with_recent_activity_30d": sum(1 for m in all_metrics if m.get("invocations_last_30d", 0) > 0),
    }


def render_markdown(per_agent: List[Dict[str, Any]], cross: Dict[str, Any]) -> str:
    lines = []
    lines.append("# AEP v1.0.2 — Agentic Performance Report")
    lines.append("")
    lines.append(f"**Generated**: {NOW_ISO}")
    lines.append(f"**Authority**: operator 'wheres the measured performance of our agents with the new aep' 2026-05-17.")
    lines.append(f"**Composes with**: AGENTIC-CAPABILITIES-V1.0.2-2026-05-17.md (Wave-046 substrate perf); this fills the per-AGENT gap.")
    lines.append("")
    lines.append("## TL;DR")
    lines.append("")
    lines.append(f"- **{cross['n_agents_tracked']} canonical agents tracked** ({cross['n_agents_with_recent_activity_7d']} active last 7d; {cross['n_agents_with_recent_activity_30d']} active last 30d)")
    lines.append(f"- **{cross['total_invocations_across_all_agents']} total ledger rows** across all agents")
    lines.append(f"  - last 7d: **{cross['total_invocations_last_7d']}** invocations")
    lines.append(f"  - last 30d: **{cross['total_invocations_last_30d']}** invocations")
    lines.append(f"- **{cross['total_high_veto_mentions']} HIGH-VETO mentions** + {cross['total_veto_mentions'] - cross['total_high_veto_mentions']} other VETO mentions across all agents")
    lines.append(f"- **{cross['total_artifact_rows']} ledger rows with `artifact_path` set** (concrete artifacts produced)")
    lines.append("")

    lines.append("## Per-agent performance (ranked by total invocations)")
    lines.append("")
    lines.append("| Agent | Total | Last 7d | Last 30d | First | Last | VETOs | HIGH-VETOs |")
    lines.append("|---|---:|---:|---:|---|---|---:|---:|")
    sorted_agents = sorted(per_agent, key=lambda m: m["total_invocations"], reverse=True)
    for m in sorted_agents:
        if m.get("EMPTY_LEDGER"):
            lines.append(f"| {m['agent']} | 0 | — | — | — | — | — | — |")
            continue
        first = (m.get("first_invocation") or "")[:10]
        last = (m.get("last_invocation") or "")[:10]
        lines.append(
            f"| **{m['agent']}** | {m['total_invocations']} | {m.get('invocations_last_7d',0)} | "
            f"{m.get('invocations_last_30d',0)} | {first} | {last} | "
            f"{m.get('veto_mentions',0)} | {m.get('high_veto_mentions',0)} |"
        )
    lines.append("")

    lines.append("## Cross-agent aggregate metrics")
    lines.append("")
    lines.append("### Truth-tag distribution (aggregate)")
    lines.append("")
    for tag, cnt in cross["aggregate_truth_tag_distribution"].items():
        pct = (cnt / cross["total_invocations_across_all_agents"]) * 100 if cross["total_invocations_across_all_agents"] else 0
        lines.append(f"- `{tag}`: **{cnt}** ({pct:.1f}%)")
    lines.append("")

    lines.append("### Outcome distribution (aggregate)")
    lines.append("")
    for outcome, cnt in cross["aggregate_outcome_distribution"].items():
        pct = (cnt / cross["total_invocations_across_all_agents"]) * 100 if cross["total_invocations_across_all_agents"] else 0
        lines.append(f"- `{outcome}`: **{cnt}** ({pct:.1f}%)")
    lines.append("")

    lines.append("### Activity ranking (last 7 days)")
    lines.append("")
    for i, (agent, n) in enumerate(cross["ranking_by_last_7d_activity"], 1):
        lines.append(f"{i}. **{agent}** — {n} invocations")
    lines.append("")

    lines.append("## Per-agent detail")
    lines.append("")
    for m in sorted_agents:
        lines.append(f"### {m['agent']}")
        lines.append("")
        if m.get("EMPTY_LEDGER"):
            lines.append("_Ledger empty._")
            lines.append("")
            continue
        lines.append(f"- **Total invocations**: {m['total_invocations']}")
        lines.append(f"- **First**: {(m.get('first_invocation') or '')[:19]}")
        lines.append(f"- **Last**: {(m.get('last_invocation') or '')[:19]}")
        lines.append(f"- **Activity**: 7d={m.get('invocations_last_7d',0)} / 30d={m.get('invocations_last_30d',0)}")
        lines.append(f"- **Unique sessions**: {m.get('unique_sessions',0)}")
        lines.append(f"- **Artifact rows**: {m.get('artifact_rows',0)}")
        lines.append(f"- **VETO mentions**: {m.get('veto_mentions',0)} (HIGH-VETO: {m.get('high_veto_mentions',0)})")
        lines.append(f"- **Wave participation count**: {m.get('wave_participation_count',0)}")
        if m.get("top_5_waves"):
            lines.append(f"- **Top 5 waves**: {', '.join(f'wave-{w}×{c}' for w,c in m['top_5_waves'].items())}")
        if m.get("top_5_cluster_tags"):
            lines.append(f"- **Top 5 cluster tags**: {', '.join(f'{t}×{c}' for t,c in m['top_5_cluster_tags'].items())}")
        nq = m.get("notes_quality_proxy", {})
        lines.append(f"- **Notes quality proxy** (length stats): mean={nq.get('mean_notes_length',0)} / median={nq.get('median_notes_length',0)} / p95={nq.get('p95_notes_length',0)}")
        lines.append(f"- **Truth-tag distribution**: {dict(list(m.get('truth_tag_distribution',{}).items())[:5])}")
        lines.append(f"- **Outcome distribution**: {dict(list(m.get('outcome_distribution',{}).items())[:5])}")
        lines.append("")

    lines.append("## Honest framing per §69.5")
    lines.append("")
    lines.append("- These metrics are **ledger-derived** (proxy for agent activity). They do NOT measure:")
    lines.append("  - Per-invocation latency (would need invocation-time-stamping; not currently captured)")
    lines.append("  - Token cost per agent (would need token-usage capture per Anthropic billing API)")
    lines.append("  - Multi-agent convergence rate (would need cross-agent dispatch correlation IDs)")
    lines.append("  - Operator-judged quality per agent output (subjective; requires operator rating loop)")
    lines.append("- The metrics ARE empirical proxies for: activity volume, recency, VETO honor pattern, artifact production, doctrine ladder usage (truth-tag distribution).")
    lines.append("")
    lines.append("## STAGED for next session (per honest disclosure)")
    lines.append("")
    lines.append("- **Per-invocation latency capture** — add `invoked_at` + `completed_at` fields to ledger schema")
    lines.append("- **Token cost capture** — instrument Agent dispatches to record token usage; tie to ledger via session_id")
    lines.append("- **Multi-agent convergence metric** — when N agents fire on same wave, measure % agreement on TOP-1 frame")
    lines.append("- **Operator-rated quality loop** — post-wave operator scores each agent's contribution 0-10, recorded in dedicated ledger")
    return "\n".join(lines)


def main() -> int:
    if not LEDGER_DIR.exists():
        print(f"FAIL: {LEDGER_DIR} does not exist", file=sys.stderr)
        return 1

    print(f"Wave-051 agentic performance · {NOW_ISO}")
    print(f"  ledger dir: {LEDGER_DIR.relative_to(REPO_ROOT)}")
    print(f"  canonical agents: {len(CANONICAL_AGENTS)}")

    per_agent = []
    for agent in CANONICAL_AGENTS:
        rows = load_ledger(agent)
        per_agent.append(agent_metrics(agent, rows))
        print(f"  [{agent:14s}] rows={len(rows)}")

    cross = cross_agent_metrics(per_agent)
    md = render_markdown(per_agent, cross)

    OUTPUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DOC.write_text(md, encoding="utf-8")
    print(f"\n  report: {OUTPUT_DOC.relative_to(REPO_ROOT)}")
    print(f"  report size: {len(md)} bytes")

    summary = {
        "wave": "051",
        "audited_at": NOW_ISO,
        "n_agents": len(CANONICAL_AGENTS),
        "cross_metrics": cross,
        "report_path": str(OUTPUT_DOC.relative_to(REPO_ROOT)),
        "report_bytes": len(md),
    }
    canonical = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    summary["receipt_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    RECEIPT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":")) + "\n")

    print(f"  receipt sha256: {summary['receipt_sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
