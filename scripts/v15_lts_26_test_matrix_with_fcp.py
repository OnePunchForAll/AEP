#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AEP v1.5 LTS - 26-Test Matrix (extends 25 with Gate 26: Headless Chromium FCP)
==============================================================================

Operator directive 2026-05-18 Wave 2 (sec73.2 sacred):
  "headless-Chromium first-paint viewer harness ... STAGED v1.5.1"

This runner is the SIBLING of v15_lts_25_test_matrix.py. It invokes the
existing 25-test matrix as a black box (no mutation; sec73.4 single-forge-
per-coherent-product-family), then runs Gate 26 (FCP) via the Node+Playwright
harness at tests/test_v15_viewer_first_paint_headless_chromium.cjs.

Gate 26 target: viewer first-contentful-paint p95 <= 2000ms.
Why FCP (not arbitrary "first paint"): FCP is the W3C Paint Timing API metric
that fires when text or images first paint - this is the perceived-load
moment a real user experiences. It is the canonical web-vitals load metric.

Composes with:
  - sec45 (codex-first burn fired BEFORE harness authored;
    see .claude/_logs/codex-prompt-wave2-viewer-fp.txt)
  - sec68 (no PowerShell; Node + Python only)
  - sec73.4 (ONE forge owns this coherent product family: Wave 2 FCP)
  - sec73.5 (HCRL row chains from cee162f57bead3b9)
  - sec73.6 (honest framing: FCP is the load-anchor; p95 from N=20 cold
    iterations excludes browser process startup but INCLUDES Chrome
    new-context cost which IS load-bearing for a civilian viewer)

Outputs:
  - .claude/_logs/aep-v15-lts-26-test-matrix-outcomes.jsonl
  - prior 25 outcomes inherited from .claude/_logs/aep-v15-lts-25-test-matrix-outcomes.jsonl
  - per-iter FCP data: .claude/aep/perf/viewer_first_paint_wave2.jsonl

Exit codes:
  0 = all 26 gates PASS or COVERED_BY_PRIOR_PHASE
  1 = at least one gate FAIL (other than STAGED)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path("C:/Users/example-user/")
LOGS = ROOT / ".claude" / "_logs"
PERF = ROOT / ".claude" / "aep" / "perf"

PRIOR_OUTCOMES = LOGS / "aep-v15-lts-25-test-matrix-outcomes.jsonl"
NEW_OUTCOMES = LOGS / "aep-v15-lts-26-test-matrix-outcomes.jsonl"

FCP_HARNESS_JS = ROOT / "tests" / "test_v15_viewer_first_paint_headless_chromium.cjs"
FCP_PERF_LOG = PERF / "viewer_first_paint_wave2.jsonl"

FCP_GATE_TARGET_MS = 2000  # constitution-bound


def ts_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime()) + \
        ("%06dZ" % (int((time.time() * 1_000_000) % 1_000_000)))


def run_fcp_harness(n: int = 20) -> Dict[str, Any]:
    """Invoke the Node+Playwright FCP harness and parse the summary line."""
    if not FCP_HARNESS_JS.exists():
        return {
            "status": "RUN_THIS_SESSION",
            "pass_count": 0,
            "fail_count": 1,
            "total_count": 1,
            "gate_met": False,
            "evidence_file_path": "",
            "note": "FCP harness not found at " + str(FCP_HARNESS_JS),
        }
    try:
        proc = subprocess.run(
            ["node", str(FCP_HARNESS_JS), "--n", str(n)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "RUN_THIS_SESSION",
            "pass_count": 0,
            "fail_count": 1,
            "total_count": 1,
            "gate_met": False,
            "evidence_file_path": str(FCP_PERF_LOG),
            "note": "FCP harness timed out after 300s",
        }
    except FileNotFoundError:
        return {
            "status": "STAGED",
            "pass_count": 0,
            "fail_count": 0,
            "total_count": 0,
            "gate_met": False,
            "evidence_file_path": "",
            "note": "node not on PATH; FCP harness STAGED",
        }

    # Parse summary line from stdout (last line is the summary JSON)
    summary = None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
            if isinstance(j, dict) and j.get("summary") is True:
                summary = j
                break
        except json.JSONDecodeError:
            continue

    if summary is None:
        return {
            "status": "RUN_THIS_SESSION",
            "pass_count": 0,
            "fail_count": 1,
            "total_count": 1,
            "gate_met": False,
            "evidence_file_path": str(FCP_PERF_LOG),
            "note": "no summary line in harness output; rc=" + str(proc.returncode),
            "stderr_tail": proc.stderr[-400:],
        }

    n_completed = summary.get("n_completed", 0)
    p95_fcp = summary.get("p95_fcp_ms")
    gate_met = bool(summary.get("gate_met"))

    return {
        "status": "RUN_THIS_SESSION",
        "pass_count": int(gate_met),
        "fail_count": 0 if gate_met else 1,
        "total_count": 1,
        "gate_met": gate_met,
        "evidence_file_path": str(FCP_PERF_LOG),
        "metrics": {
            "n_completed": n_completed,
            "p50_fcp_ms": summary.get("p50_fcp_ms"),
            "p95_fcp_ms": p95_fcp,
            "p99_fcp_ms": summary.get("p99_fcp_ms"),
            "p95_load_ms": summary.get("p95_load_ms"),
            "mean_fcp_ms": summary.get("mean_fcp_ms"),
            "min_fcp_ms": summary.get("min_fcp_ms"),
            "max_fcp_ms": summary.get("max_fcp_ms"),
        },
        "target_ms": FCP_GATE_TARGET_MS,
        "note": ("Headless Chromium FCP from W3C Paint Timing API. "
                 "N=%d iterations; p95=%s ms target=%d ms %s." % (
                     n_completed, p95_fcp, FCP_GATE_TARGET_MS,
                     "PASS" if gate_met else "FAIL"))
    }


def inherit_prior_outcomes() -> List[Dict[str, Any]]:
    """Read prior 25-test outcomes if available."""
    if not PRIOR_OUTCOMES.exists():
        return []
    rows = []
    with PRIOR_OUTCOMES.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main() -> int:
    prior_rows = inherit_prior_outcomes()
    # Strip the prior summary row (if any) so we can append the new one
    prior_data = [r for r in prior_rows if not r.get("summary")]

    print("[v15-LTS 26-test matrix] inherited %d prior rows from 25-test matrix"
          % len(prior_data))
    print("=" * 72)

    rows_out: List[Dict[str, Any]] = list(prior_data)

    # Echo prior gates to stdout
    pass_count = 0
    fail_count = 0
    staged_count = 0
    gate_pass = 0
    gate_fail = 0
    gate_staged = 0

    for row in prior_data:
        if row.get("status") == "COVERED_BY_PRIOR_PHASE":
            pass_count += 1
        elif row.get("status") == "STAGED":
            staged_count += 1
        else:
            if row.get("gate_met"):
                pass_count += 1
            else:
                fail_count += 1
        if row.get("gate_met"):
            gate_pass += 1
        elif row.get("status") == "STAGED":
            gate_staged += 1
        else:
            gate_fail += 1

    # Gate 26: headless Chromium FCP
    print("[26] running headless_chromium_first_paint ...")
    fcp_result = run_fcp_harness(n=20)
    fcp_row = {
        "index": 26,
        "category": "headless_chromium_first_paint",
        "ts": ts_iso(),
        "status": fcp_result.get("status"),
        "pass_count": fcp_result.get("pass_count", 0),
        "fail_count": fcp_result.get("fail_count", 0),
        "total_count": fcp_result.get("total_count", 0),
        "gate_met": bool(fcp_result.get("gate_met", False)),
        "evidence_file_path": fcp_result.get("evidence_file_path", ""),
        "metrics": fcp_result.get("metrics"),
        "target_ms": fcp_result.get("target_ms"),
        "note": fcp_result.get("note", ""),
        "hcrl_row_id": None,
        "wave": "Wave-2-2026-05-18",
        "composes_with": ["sec45", "sec68", "sec73.4", "sec73.5", "sec73.6"],
    }
    rows_out.append(fcp_row)
    print("[26] %-36s %-22s pass=%d fail=%d/%d gate=%s" % (
        "headless_chromium_first_paint",
        fcp_row["status"],
        fcp_row["pass_count"],
        fcp_row["fail_count"],
        fcp_row["total_count"],
        "Y" if fcp_row["gate_met"] else "N",
    ))
    if fcp_row.get("metrics"):
        m = fcp_row["metrics"]
        print("     p50=%s p95=%s p99=%s mean=%s n=%s" % (
            m.get("p50_fcp_ms"), m.get("p95_fcp_ms"), m.get("p99_fcp_ms"),
            m.get("mean_fcp_ms"), m.get("n_completed"),
        ))

    if fcp_row["status"] == "STAGED":
        staged_count += 1
        gate_staged += 1
    elif fcp_row["gate_met"]:
        pass_count += 1
        gate_pass += 1
    else:
        fail_count += 1
        gate_fail += 1

    summary = {
        "summary": True,
        "ts": ts_iso(),
        "total_categories": 26,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "staged_count": staged_count,
        "gate_pass_count": gate_pass,
        "gate_fail_count": gate_fail,
        "gate_staged_count": gate_staged,
        "wave_2_addition": "headless_chromium_first_paint at gate 26",
    }
    rows_out.append(summary)
    NEW_OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
    with NEW_OUTCOMES.open("w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
    print("=" * 72)
    print("PASS=%d  FAIL=%d  STAGED=%d  TOTAL=26" % (pass_count, fail_count, staged_count))
    print("Gates  PASS=%d  FAIL=%d  STAGED=%d" % (gate_pass, gate_fail, gate_staged))
    print("Outcomes log: %s" % NEW_OUTCOMES)
    return 0 if gate_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
