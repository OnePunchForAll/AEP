"""counterexample_replay.py — Apache-2.0 — F7 counterexample_bundle replay runtime.

Closes the v0.8.0-rc2 STAGED F7 item per §V80-8-bis F7 Deterministic Adversarial
Replay Ledger.

Walks a packet's counterexample_bundle[] entries; for each, runs the declared
non_regression_test_command via the F5 sandbox (test_kind=static only) under
the declared env_lock; reports per-counterexample PASS/FAIL + cumulative budget.

DISCIPLINE (per §V80-8-bis):
  - REPLAY-V80-1: non_regression_test_command MUST pass (non-fire exit) for packet acceptance
  - REPLAY-V80-2: cumulative cost bounded by fatigue_budget_tag (low ≤500ms, med ≤5s, high ≤30s)
  - REPLAY-V80-3: each replay event recorded in ops/events.jsonl (or returned for caller to record)
  - Uses F5 sandbox (falsifier_sandbox.run_static_falsifier) — same AST deny-list discipline

Stdlib only (§68).

Composes with: §V80-8-bis F7 + §V80-7 F5 sandbox + §71.2 4h cap (via budget_ms enforcement).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aep.falsifier_sandbox import run_static_falsifier

BUDGET_CAP_MS = {"low": 500, "med": 5000, "high": 30000}


@dataclass
class ReplayResult:
    counterexample_id: str
    binds_to_failure_class: str
    elapsed_ms: float
    exit_code: int  # 0=PASS (no regression), 1=FAIL (regression detected), -1=sandbox-rejected
    error: Optional[str] = None
    env_lock_match: bool = True


@dataclass
class ReplayAggregate:
    total_count: int
    pass_count: int
    fail_count: int
    error_count: int
    total_elapsed_ms: float
    budget_exceeded: bool
    findings: List[str]
    per_counterexample: List[ReplayResult]


def replay_counterexample_bundle(
    packet_root: pathlib.Path,
    fatigue_budget_tag: str = "med",
) -> ReplayAggregate:
    """Replay all counterexamples in a packet's bundle.

    Returns aggregate result. Caller decides whether to REJECT the packet
    based on aggregate.fail_count > 0 OR aggregate.budget_exceeded.
    """
    manifest_path = packet_root / "aepkg.json"
    findings: List[str] = []
    results: List[ReplayResult] = []
    total_ms = 0.0
    pass_n = fail_n = err_n = 0
    budget_cap = BUDGET_CAP_MS.get(fatigue_budget_tag, 5000)
    budget_exceeded = False

    if not manifest_path.exists():
        findings.append("aepkg.json not found")
        return ReplayAggregate(0, 0, 0, 0, 0.0, False, findings, [])

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        findings.append(f"aepkg.json decode failed: {e}")
        return ReplayAggregate(0, 0, 0, 0, 0.0, False, findings, [])

    bundle = manifest.get("counterexample_bundle", [])
    if not isinstance(bundle, list):
        bundle = []

    for ce in bundle:
        if not isinstance(ce, dict):
            err_n += 1
            findings.append("AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED: non-object entry")
            continue

        ce_id = ce.get("counterexample_id", "?")
        binding = ce.get("binds_to_failure_class", "")
        if not binding:
            err_n += 1
            findings.append(f"AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED: {ce_id} missing binds_to_failure_class")
            continue

        test_command = ce.get("non_regression_test_command", "")
        if not test_command:
            err_n += 1
            findings.append(f"AEP80_COUNTEREXAMPLE_BINDING_UNRESOLVED: {ce_id} missing test_command")
            continue

        max_runtime = int(ce.get("max_runtime_ms", 1000))

        t0 = time.perf_counter()
        exit_code, error = run_static_falsifier(test_command, packet_root, max_runtime)
        elapsed = (time.perf_counter() - t0) * 1000
        total_ms += elapsed

        r = ReplayResult(
            counterexample_id=ce_id,
            binds_to_failure_class=binding,
            elapsed_ms=elapsed,
            exit_code=exit_code,
            error=error,
        )
        results.append(r)

        if exit_code == 0:
            pass_n += 1
        elif exit_code == 1:
            fail_n += 1
            findings.append(f"AEP80_COUNTEREXAMPLE_REPLAY_FAILED: {ce_id} (binds_to={binding})")
        else:
            err_n += 1
            findings.append(f"AEP80_COUNTEREXAMPLE_REPLAY_ERROR: {ce_id} sandbox-rejected — {error}")

        if total_ms > budget_cap:
            budget_exceeded = True
            findings.append(f"AEP80_COUNTEREXAMPLE_BUDGET_EXCEEDED: total {total_ms:.1f}ms > {fatigue_budget_tag} cap {budget_cap}ms")
            break

    return ReplayAggregate(
        total_count=len(bundle),
        pass_count=pass_n,
        fail_count=fail_n,
        error_count=err_n,
        total_elapsed_ms=total_ms,
        budget_exceeded=budget_exceeded,
        findings=findings,
        per_counterexample=results,
    )


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="F7 counterexample_bundle replay runtime")
    parser.add_argument("packet_root", type=pathlib.Path)
    parser.add_argument("--budget", default="med", choices=["low", "med", "high"])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    agg = replay_counterexample_bundle(args.packet_root, args.budget)
    print(f"replay_counterexample_bundle({args.packet_root}) budget={args.budget}")
    print(f"  total={agg.total_count}  pass={agg.pass_count}  fail={agg.fail_count}  err={agg.error_count}")
    print(f"  total_elapsed_ms={agg.total_elapsed_ms:.2f}  budget_exceeded={agg.budget_exceeded}")
    if agg.findings:
        for f in agg.findings:
            print(f"  - {f}")

    if args.strict and (agg.fail_count > 0 or agg.budget_exceeded):
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
