#!/usr/bin/env python3
"""validate_corpus_v0_8.py — exhaustive v0.8 validation across the entire .aepkg corpus.

Operator directive 2026-05-17: "ensure all files are working, test using every
single aep file including associated core aep file rules ie. minimal.aepkg".

This script walks EVERY .aepkg in the repo, runs validate_v0_8, aggregates
findings by reason code + severity + packet class (lesson / doctrine / agent
ledger / agent SKILL / research source / research analysis / proposal /
project artifact / example / test fixture), emits both a flat JSONL receipt
ledger AND a structured human-readable summary.

Stdlib only (§68). No network. No subprocess. No shell.

Usage:
    python scripts/validate_corpus_v0_8.py                       # full corpus
    python scripts/validate_corpus_v0_8.py --limit 50            # first 50
    python scripts/validate_corpus_v0_8.py --json out.json       # JSON output
    python scripts/validate_corpus_v0_8.py --by-class            # group by packet class
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

# Locate repo root and the aep src dir.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
AEP_SRC = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "src"
if str(AEP_SRC) not in sys.path:
    sys.path.insert(0, str(AEP_SRC))

from aep.validate_v0_8 import validate_v0_8  # noqa: E402

# Receipts go to a non-canonical audit log per §V60-2 Axiom 4.
RECEIPTS_PATH = REPO_ROOT / ".claude" / "_logs" / "v0_8-corpus-audit.jsonl"


def packet_class(packet_path: pathlib.Path) -> str:
    """Classify a packet by its location in the repo for averaging by class."""
    rel = packet_path.relative_to(REPO_ROOT).as_posix()
    if rel.startswith("doctrine/lessons/"):
        return "lesson"
    if rel.startswith("doctrine/_proposals/"):
        return "proposal"
    if rel.startswith("doctrine/skills/"):
        return "skill-doctrine"
    if rel.startswith("doctrine/"):
        return "doctrine-slot"
    if rel.startswith(".claude/agents/_ledgers/"):
        return "agent-ledger"
    if rel.startswith(".claude/agents/"):
        return "agent-skill"
    if rel.startswith(".claude/skills/"):
        return "claude-skill"
    if rel.startswith(".claude/diana/"):
        return "diana-internal"
    if rel.startswith("research/sources/"):
        return "research-source"
    if rel.startswith("research/analysis/"):
        return "research-analysis"
    if rel.startswith("projects/v11-aep/publish-ready/aep/examples/"):
        return "v11-aep-example"
    if rel.startswith("projects/v11-aep/publish-ready/aep/tests/"):
        return "v11-aep-test-fixture"
    if rel.startswith("projects/v11-aep/"):
        return "v11-aep-project"
    if rel.startswith("projects/"):
        return "project-artifact"
    if rel.startswith("library/"):
        return "library"
    if rel.startswith("tmp/"):
        return "tmp"
    return "other"


def find_aepkg_dirs(root: pathlib.Path, exclude_patterns: Optional[List[str]] = None) -> List[pathlib.Path]:
    exclude_patterns = exclude_patterns or []
    found: List[pathlib.Path] = []
    for p in root.rglob("*.aepkg"):
        if not p.is_dir() or not (p / "aepkg.json").exists():
            continue
        rel = p.relative_to(root).as_posix()
        if any(pat in rel for pat in exclude_patterns):
            continue
        found.append(p)
    return sorted(set(found))


def validate_one(packet: pathlib.Path) -> Dict[str, Any]:
    t0 = time.perf_counter()
    rec: Dict[str, Any] = {
        "packet": packet.relative_to(REPO_ROOT).as_posix(),
        "class": packet_class(packet),
        "elapsed_ms": 0.0,
        "schema_result": "unknown",
        "error_count": 0,
        "warning_count": 0,
        "info_count": 0,
        "findings_by_code": {},
        "v0_8_migrated": False,
        "exception": None,
    }
    try:
        result = validate_v0_8(packet)
        rec["schema_result"] = result.schema_result
        rec["error_count"] = result.error_count
        rec["warning_count"] = result.warning_count
        rec["info_count"] = sum(1 for f in result.findings if f.severity == "info")
        codes: Dict[str, int] = collections.Counter()
        for f in result.findings:
            codes[f.code] = codes.get(f.code, 0) + 1
        rec["findings_by_code"] = dict(codes)
        # Determine v0.8 migration status by looking at manifest.
        try:
            mfp = json.loads((packet / "aepkg.json").read_text(encoding="utf-8"))
            rec["v0_8_migrated"] = mfp.get("profile", "").startswith("aep:0.8/")
            rec["spec_version"] = mfp.get("spec_version", "")
        except (OSError, json.JSONDecodeError):
            pass
    except Exception as e:
        rec["exception"] = f"{type(e).__name__}: {e}"
        rec["exception_traceback"] = traceback.format_exc()
    rec["elapsed_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return rec


def aggregate(receipts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the corpus-level averaged summary the operator asked for."""
    by_class: Dict[str, Dict[str, Any]] = collections.defaultdict(
        lambda: {
            "count": 0, "pass": 0, "fail": 0,
            "v0_8_migrated": 0, "v0_8_not_migrated": 0,
            "total_errors": 0, "total_warnings": 0, "total_infos": 0,
            "total_elapsed_ms": 0.0, "max_elapsed_ms": 0.0,
            "findings_by_code": collections.Counter(),
            "exceptions": 0,
        }
    )
    global_findings: Dict[str, int] = collections.Counter()
    global_pass = global_fail = global_exception = 0
    global_migrated = global_not_migrated = 0
    total_packets = len(receipts)
    total_elapsed_ms = 0.0

    for r in receipts:
        cls = r["class"]
        bc = by_class[cls]
        bc["count"] += 1
        if r["exception"]:
            bc["exceptions"] += 1
            global_exception += 1
        elif r["schema_result"] == "pass":
            bc["pass"] += 1
            global_pass += 1
        else:
            bc["fail"] += 1
            global_fail += 1
        if r["v0_8_migrated"]:
            bc["v0_8_migrated"] += 1
            global_migrated += 1
        else:
            bc["v0_8_not_migrated"] += 1
            global_not_migrated += 1
        bc["total_errors"] += r["error_count"]
        bc["total_warnings"] += r["warning_count"]
        bc["total_infos"] += r["info_count"]
        bc["total_elapsed_ms"] += r["elapsed_ms"]
        bc["max_elapsed_ms"] = max(bc["max_elapsed_ms"], r["elapsed_ms"])
        total_elapsed_ms += r["elapsed_ms"]
        for code, n in r["findings_by_code"].items():
            bc["findings_by_code"][code] += n
            global_findings[code] += n

    # Average computations per class.
    for cls, bc in by_class.items():
        if bc["count"] > 0:
            bc["avg_elapsed_ms"] = round(bc["total_elapsed_ms"] / bc["count"], 2)
            bc["pass_rate_pct"] = round(bc["pass"] * 100.0 / bc["count"], 1)
            bc["v0_8_migration_rate_pct"] = round(bc["v0_8_migrated"] * 100.0 / bc["count"], 1)
            bc["findings_by_code"] = dict(bc["findings_by_code"].most_common())

    return {
        "audit_id": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_packets": total_packets,
        "global_pass": global_pass,
        "global_fail": global_fail,
        "global_exception": global_exception,
        "global_pass_rate_pct": round(global_pass * 100.0 / max(total_packets, 1), 1),
        "global_migrated": global_migrated,
        "global_not_migrated": global_not_migrated,
        "global_migration_rate_pct": round(global_migrated * 100.0 / max(total_packets, 1), 1),
        "total_elapsed_ms": round(total_elapsed_ms, 2),
        "avg_elapsed_ms": round(total_elapsed_ms / max(total_packets, 1), 2),
        "findings_by_code": dict(global_findings.most_common()),
        "by_class": dict(by_class),
    }


def print_human(summary: Dict[str, Any]) -> None:
    print(f"AEP v0.8.0-rc1 — CORPUS AUDIT")
    print(f"  audit_id={summary['audit_id']}")
    print(f"  total_packets={summary['total_packets']}")
    print(f"  PASS={summary['global_pass']} ({summary['global_pass_rate_pct']}%)  "
          f"FAIL={summary['global_fail']}  EXCEPTION={summary['global_exception']}")
    print(f"  v0.8 migrated: {summary['global_migrated']} ({summary['global_migration_rate_pct']}%)")
    print(f"  avg validation: {summary['avg_elapsed_ms']} ms/packet  "
          f"(total {summary['total_elapsed_ms']/1000.0:.1f}s)")
    print()
    print("BY PACKET CLASS:")
    print(f"  {'class':<26} {'count':>6} {'pass':>6} {'fail':>6} {'mig%':>6} {'avg_ms':>8} {'max_ms':>8}")
    for cls in sorted(summary["by_class"].keys()):
        bc = summary["by_class"][cls]
        print(f"  {cls:<26} {bc['count']:>6} {bc['pass']:>6} {bc['fail']:>6} "
              f"{bc.get('v0_8_migration_rate_pct', 0):>5}% "
              f"{bc.get('avg_elapsed_ms', 0):>8} {bc['max_elapsed_ms']:>8}")
    print()
    print("TOP-15 FINDINGS BY CODE (global):")
    for code, n in list(summary["findings_by_code"].items())[:15]:
        print(f"  {n:>6}  {code}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AEP v0.8 corpus-wide validation audit")
    parser.add_argument("--limit", type=int, default=0, help="limit to first N packets (0=all)")
    parser.add_argument("--json", type=str, default="", help="write JSON summary to path")
    parser.add_argument("--receipts", type=str, default=str(RECEIPTS_PATH),
                        help="write per-packet receipts JSONL to path")
    parser.add_argument("--exclude", action="append", default=[],
                        help="exclude packets matching pattern (repeatable)")
    parser.add_argument("--report-every", type=int, default=100, help="progress cadence")
    args = parser.parse_args(argv)

    packets = find_aepkg_dirs(REPO_ROOT, exclude_patterns=args.exclude)
    if args.limit:
        packets = packets[:args.limit]
    if not packets:
        print("no .aepkg dirs found", file=sys.stderr)
        return 1

    print(f"Auditing {len(packets)} packets under v0.8.0-rc1 validator")
    t_start = time.perf_counter()
    receipts: List[Dict[str, Any]] = []
    receipts_path = pathlib.Path(args.receipts)
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    with receipts_path.open("w", encoding="utf-8") as rf:
        for i, packet in enumerate(packets, 1):
            r = validate_one(packet)
            receipts.append(r)
            # Trim heavy fields for the streaming JSONL.
            stream_r = {k: v for k, v in r.items() if k != "exception_traceback"}
            rf.write(json.dumps(stream_r, separators=(",", ":")) + "\n")
            if i % args.report_every == 0:
                elapsed = time.perf_counter() - t_start
                rate = i / max(elapsed, 1e-6)
                print(f"  progress: {i}/{len(packets)} ({i*100//len(packets)}%) "
                      f"@ {rate:.1f} pkt/s")

    elapsed = time.perf_counter() - t_start
    print(f"\nAudit complete in {elapsed:.1f}s")
    summary = aggregate(receipts)
    print_human(summary)

    if args.json:
        out = pathlib.Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nJSON summary: {out}")

    print(f"Receipts: {receipts_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
