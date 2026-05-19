"""_wave_q_depth2_smoketest.py — Wave-Q depth-2 nested-spawn smoke test.

Purpose: depth-2 verification harness for the 3 Wave-Q refactors. This
script subprocess.runs each refactored falsifier (depth-1 boundary); the
refactored falsifier internally now imports its retrieval module
(formerly depth-2 subprocess.run); so this harness drives the full
depth-1+depth-2 path that previously fired sibling-49 WinError 5.

Expected post-refactor: all 3 return rc=0, no PermissionError trace.

Cited modules: falsifier_6_cross_agent_contextual.py,
falsifier_6_cross_agent_hybrid.py, falsifier_6_citation_based.py.

This file is OPERATIONAL TOOLING. Not promoted; not load-bearing for
canonical metrics; smoke-test only. May be deleted after Wave-Q close.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPTS = [
    "projects/v11-aep/publish-ready/aep/scripts/falsifier_6_cross_agent_contextual.py",
    "projects/v11-aep/publish-ready/aep/scripts/falsifier_6_cross_agent_hybrid.py",
    "projects/v11-aep/publish-ready/aep/scripts/falsifier_6_citation_based.py",
]


def main() -> int:
    print("Wave-Q depth-2 nested-spawn smoke test (forge sibling-49 cluster condition 2)")
    print("=" * 80)
    results = []
    for s in SCRIPTS:
        cmd = [sys.executable, s, "--top-k", "3"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            rc = proc.returncode
            # Check for the sibling-49 fingerprint
            err_blob = (proc.stderr or "") + (proc.stdout or "")
            has_winerror5 = "WinError 5" in err_blob or "Access is denied" in err_blob
            has_perm_err = "PermissionError" in err_blob
            ok = (rc == 0) and not has_winerror5 and not has_perm_err
            results.append((s, rc, ok, has_winerror5 or has_perm_err))
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {Path(s).name}: rc={rc} winerror5={has_winerror5} permerr={has_perm_err}")
        except subprocess.TimeoutExpired:
            results.append((s, -1, False, False))
            print(f"[TIMEOUT] {Path(s).name}: 600s exceeded")
    print("=" * 80)
    n_pass = sum(1 for _, _, ok, _ in results if ok)
    print(f"OVERALL: {n_pass}/{len(SCRIPTS)} PASS (no WinError 5 at depth-2)")
    return 0 if n_pass == len(SCRIPTS) else 1


if __name__ == "__main__":
    sys.exit(main())
