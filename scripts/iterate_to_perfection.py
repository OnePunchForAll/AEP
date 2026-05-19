#!/usr/bin/env python3
"""iterate_to_perfection.py - the operator's make-it-perfect harness.

Operator directive (sec73.2 sacred verbatim):
> "if everything is not perfect, then make it perfect for v1.1 do whatever you
>  have to do i honestly don't see how any of you have limits anymore - just
>  figure it out"

Phase 4b deliverable per AEP_v1_1_SPEC.md. Companion to measure_v11_aep_completeness.py.

Workflow:
  1. Runs measure_v11_aep_completeness.py to (re)generate the completeness report.
  2. Reads the JSON report.
  3. For each primitive below 100% completeness, generates specific TODO lines:
     "primitive X is missing dimension Y -- to reach 100%, ship Z"
  4. For each operator-target unmet, surface HIGH-PRIORITY gap.
  5. For F18 laundering_score HIGH, surface as DISCLOSED RISK
     (does not block perfection; honest framing per sec73.6).
  6. Writes TODO list to:
       projects/v11-aep/publish-ready/aep/reports/v11_perfection_iteration_TODO.md
  7. Exit 0 if all primitives at 100% AND all operator targets met.
     Exit 1 otherwise (TODO file IS the proof).

Stdlib only. Discipline per sec73.6: gaps shipped UNSHAPED; the TODO is the truth.

Phase 5 (the agent orchestrates) actually runs this; Phase 4b ships it RUN-READY.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[5]
AEP_ROOT = THIS_FILE.parents[1]
SCRIPTS_DIR = AEP_ROOT / "scripts"
REPORTS_DIR = AEP_ROOT / "reports"
MEASURE_SCRIPT = SCRIPTS_DIR / "measure_v11_aep_completeness.py"
REPORT_JSON = REPORTS_DIR / "v11_completeness_report.json"
TODO_MD = REPORTS_DIR / "v11_perfection_iteration_TODO.md"

# Per-dimension remediation guidance: the to-reach-100% prescription for each
# missing dimension. Phase 5 fans these out to forge tasks.
DIMENSION_REMEDIATION: Dict[str, str] = {
    "schema_shipped": (
        "Author the JSON Schema file under `projects/v11-aep/publish-ready/aep/schemas/`. "
        "Use $schema: draft/2020-12 + $id: aep:v1_1:<primitive>:0.1. "
        "Mirror the structural fields named in AEP_v1_1_SPEC.md for this primitive. "
        "additionalProperties: false."
    ),
    "validator_shipped": (
        "Ship a validator script at `projects/v11-aep/publish-ready/aep/scripts/validate_<primitive>.py`. "
        "Stdlib-only. Loads the schema, validates input records against it, emits AEP11_<PRIM>_* reason codes "
        "on rejection. Exit 0 on positive path, exit 1 on negative path."
    ),
    "reference_impl_shipped": (
        "Ship a reference implementation alongside the validator. For F-tier primitives this is the "
        "build_<primitive>_*.py script that emits records from canonical inputs. For amendments, "
        "the reference impl is the script that *retroactively applies* the amendment to existing data."
    ),
    "tests_shipped": (
        "Author an integration test file at `projects/v11-aep/publish-ready/aep/tests/test_v11_<primitive>_integration.py`. "
        "Cover positive + negative + schema-binding tests. Match the existing test_v11_f12_f13_integration.py shape."
    ),
    "tests_pass": (
        "Run the integration tests; ensure all_<N>_integration_tests_pass == true in the HCRL row's no_screen_fail block. "
        "If tests fail, fix the validator/reference impl before declaring 100%."
    ),
    "receipt_in_hcrl": (
        "Append an HCRL row to `.claude/_logs/aep-v103-phase-receipts.jsonl` mentioning the primitive id "
        "or its measured-trace key. Phase 5 emits the row after the iterate-to-perfection cycle completes."
    ),
    "retro_applied_to_existing_corpus": (
        "Ship a wave_<NNN>_<primitive>_retro.py script that applies the primitive to existing corpus packets "
        "(or to ledger rows / HCRL chain / lesson archive). Goal: prove the primitive WORKS on real data, "
        "not just on synthetic examples in the SPEC."
    ),
    "empirical_disconfirmer_passed": (
        "The primitive's own validation gate must hit its declared target. See operator_target_alignment field "
        "in v11_completeness_report.json for the threshold + measurement procedure. If target not met, "
        "fix the implementation (NOT the target) and re-run."
    ),
}


def _run_measure() -> int:
    """Run the measurement harness as a subprocess. Returns the exit code."""
    if not MEASURE_SCRIPT.exists():
        print(f"FATAL: measurement script missing at {MEASURE_SCRIPT}", file=sys.stderr)
        return 2
    try:
        proc = subprocess.run(
            [sys.executable, str(MEASURE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("FATAL: measurement subprocess timed out (>120s)", file=sys.stderr)
        return 3
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    return 0


def _load_report() -> Optional[Dict[str, Any]]:
    if not REPORT_JSON.exists():
        return None
    try:
        with REPORT_JSON.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: report load failed: {e}", file=sys.stderr)
        return None


def _build_todos(report: Dict[str, Any]) -> Dict[str, Any]:
    """Walk the report; produce structured TODO records."""
    todos: List[Dict[str, Any]] = []
    high_priority: List[Dict[str, Any]] = []
    disclosed_risks: List[Dict[str, Any]] = []

    # 1. Per-primitive dimension gaps.
    for rec in report.get("per_primitive", []):
        pid = rec["id"]
        binary = rec.get("binary_dimensions", {})
        for dim_name, dim_val in binary.items():
            if dim_val == 0:
                todos.append({
                    "kind": "dimension_gap",
                    "primitive": pid,
                    "label": rec["label"],
                    "axis": rec["axis"],
                    "dimension": dim_name,
                    "remediation": DIMENSION_REMEDIATION.get(
                        dim_name,
                        "Remediation undefined; refer to AEP_v1_1_SPEC.md sec12.",
                    ),
                })
        # Operator-target alignment per primitive.
        tgt = rec.get("operator_target_alignment", {}) or {}
        if not tgt.get("target_met", False) and rec["completeness_pct"] < 100.0:
            high_priority.append({
                "kind": "primitive_target_unmet",
                "primitive": pid,
                "target_name": tgt.get("name", "(unnamed)"),
                "honest_note": tgt.get("honest_note", ""),
            })

    # 2. Operator-level target scoreboard.
    sw = report.get("system_wide", {})
    scoreboard = sw.get("operator_target_scoreboard", {})
    for tgt_name, tgt in scoreboard.items():
        if tgt.get("status") not in {"MET"}:
            high_priority.append({
                "kind": "operator_target",
                "name": tgt_name,
                "primitive": tgt.get("primitive"),
                "status": tgt.get("status"),
                "measurement": tgt.get("measurement", ""),
            })

    # 3. F18 disclosed risks (laundering signal HIGH).
    for rec in report.get("per_primitive", []):
        if rec["id"] == "F18":
            tgt = rec.get("operator_target_alignment", {}) or {}
            if tgt.get("risk_class") == "HIGH":
                disclosed_risks.append({
                    "kind": "f18_laundering_signal_HIGH",
                    "score": tgt.get("measured_value"),
                    "threshold": tgt.get("threshold"),
                    "note_per_sec73_6": tgt.get("honest_note", ""),
                    "blocks_perfection": False,
                })

    return {
        "todos": todos,
        "high_priority": high_priority,
        "disclosed_risks": disclosed_risks,
    }


def _is_perfect(report: Dict[str, Any], findings: Dict[str, Any]) -> bool:
    """Perfect iff all primitives 100% AND all operator targets MET.

    Disclosed risks (F18 HIGH) do NOT block perfection per sec73.6 honest framing.
    """
    sw = report.get("system_wide", {})
    if sw.get("primitives_at_100pct", 0) != sw.get("total_primitives", 0):
        return False
    if findings["todos"]:
        return False
    if findings["high_priority"]:
        return False
    return True


def _render_todo_md(report: Dict[str, Any], findings: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# AEP v1.1 Iterate-to-Perfection TODO Ledger")
    lines.append("")
    lines.append(f"**Generated**: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}  ")
    lines.append(f"**Driver**: `projects/v11-aep/publish-ready/aep/scripts/iterate_to_perfection.py`  ")
    lines.append(f"**Source report**: `projects/v11-aep/publish-ready/aep/reports/v11_completeness_report.json`  ")
    lines.append("**Discipline**: sec73.6 ship-the-zero; gaps unshaped.")
    lines.append("")
    lines.append("## Operator directive (sec73.2 sacred verbatim)")
    lines.append("")
    lines.append("> \"if everything is not perfect, then make it perfect for v1.1 do whatever you have to do i honestly don't see how any of you have limits anymore - just figure it out\"")
    lines.append("")
    sw = report.get("system_wide", {})
    is_perfect = _is_perfect(report, findings)
    lines.append("## Verdict")
    lines.append("")
    if is_perfect:
        lines.append("**PERFECT** -- all primitives at 100%, all operator targets MET.")
    else:
        lines.append("**NOT-PERFECT** -- one or more gaps remain. See TODOs below.")
    lines.append("")
    lines.append(f"- Mean completeness: {sw.get('mean_completeness_pct', 0):.2f}%")
    lines.append(f"- Primitives at 100%: {sw.get('primitives_at_100pct', 0)} / {sw.get('total_primitives', 0)}")
    lines.append(f"- Primitives below 50%: {sw.get('primitives_below_50pct', 0)}")
    lines.append(f"- TODO count: {len(findings['todos'])}")
    lines.append(f"- HIGH-PRIORITY count: {len(findings['high_priority'])}")
    lines.append(f"- Disclosed-risk count (non-blocking): {len(findings['disclosed_risks'])}")
    lines.append("")
    lines.append("## HIGH-PRIORITY operator-target gaps")
    lines.append("")
    if not findings["high_priority"]:
        lines.append("_None._")
    else:
        for hp in findings["high_priority"]:
            if hp["kind"] == "operator_target":
                lines.append(f"### `{hp['name']}`")
                lines.append(f"- Primitive: `{hp['primitive']}`")
                lines.append(f"- Status: **{hp['status']}**")
                lines.append(f"- Measurement: {hp['measurement']}")
                lines.append("")
            else:
                lines.append(f"### {hp['primitive']} primitive target unmet")
                lines.append(f"- Target: {hp['target_name']}")
                if hp.get("honest_note"):
                    lines.append(f"- sec73.6 note: {hp['honest_note']}")
                lines.append("")
    lines.append("## Per-primitive TODO (one line per missing dimension)")
    lines.append("")
    if not findings["todos"]:
        lines.append("_None._")
    else:
        # Group by primitive for readability.
        by_prim: Dict[str, List[Dict[str, Any]]] = {}
        for t in findings["todos"]:
            by_prim.setdefault(t["primitive"], []).append(t)
        for pid in sorted(by_prim.keys()):
            todos = by_prim[pid]
            lines.append(f"### {pid} ({todos[0]['label']})")
            for t in todos:
                lines.append(
                    f"- primitive **{t['primitive']}** is missing dimension "
                    f"`{t['dimension']}` -- to reach 100%, {t['remediation']}"
                )
            lines.append("")
    lines.append("## Disclosed risks (sec73.6 honest framing; non-blocking)")
    lines.append("")
    if not findings["disclosed_risks"]:
        lines.append("_None._")
    else:
        for r in findings["disclosed_risks"]:
            lines.append(f"### {r['kind']}")
            lines.append(f"- Score: {r.get('score')}")
            lines.append(f"- Threshold: {r.get('threshold')}")
            lines.append(f"- sec73.6 note: {r.get('note_per_sec73_6', '')}")
            lines.append(f"- Blocks perfection: **{r.get('blocks_perfection')}**")
            lines.append("")
    lines.append("## Recommended remediation order (Phase 5)")
    lines.append("")
    lines.append("1. Close HIGH-PRIORITY operator-target gaps first (these are the operator's directly-stated thresholds).")
    lines.append("2. For each primitive < 100%, ship the missing dimensions in this order: schema -> validator -> reference_impl -> tests -> tests_pass -> HCRL receipt -> retro -> empirical-disconfirmer.")
    lines.append("3. Re-run `measure_v11_aep_completeness.py` after each primitive closure to verify the completeness_pct rises.")
    lines.append("4. When mean_completeness_pct == 100 AND all operator_target_scoreboard statuses are MET, the cycle is COMPLETE.")
    lines.append("")
    lines.append("## Exit-code contract")
    lines.append("")
    lines.append("- `iterate_to_perfection.py` exits **0** when this TODO list is EMPTY + all operator targets MET.")
    lines.append("- Exits **1** otherwise. The TODO file IS the proof of remaining work.")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Run the measurement harness.
    rc = _run_measure()
    if rc != 0:
        return rc

    # 2. Load the report.
    report = _load_report()
    if report is None:
        return 4

    # 3. Build TODO findings.
    findings = _build_todos(report)

    # 4. Render TODO md.
    md = _render_todo_md(report, findings)
    with TODO_MD.open("w", encoding="utf-8") as fh:
        fh.write(md)

    # 5. Exit per perfection state.
    is_perfect = _is_perfect(report, findings)
    sw = report.get("system_wide", {})
    print("AEP v1.1 iterate-to-perfection cycle complete.")
    print(f"  is_perfect       : {is_perfect}")
    print(f"  todos            : {len(findings['todos'])}")
    print(f"  high_priority    : {len(findings['high_priority'])}")
    print(f"  disclosed_risks  : {len(findings['disclosed_risks'])} (non-blocking)")
    print(f"  todo_md_path     : {TODO_MD.relative_to(REPO_ROOT)}")
    print(f"  mean_completeness: {sw.get('mean_completeness_pct', 0):.2f}%")
    return 0 if is_perfect else 1


if __name__ == "__main__":
    sys.exit(main())
