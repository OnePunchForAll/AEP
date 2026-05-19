#!/usr/bin/env python3
"""wave_022_stress_test.py — Wave-022 byte-parity stress test.

Runs the byte_parity_drift.py hook against every available .aep fixture
(happy path + 3 v0_8_parity attack fixtures). Aggregates per-fixture parity
outcomes. Captures HCRL receipt to .claude/_logs/byte-parity-stress-test-receipts.jsonl.

Purpose: empirically demonstrate that the extended N=8 drift hook surfaces
real divergence (regex omission, hits stringification, IEEE-754 boundary, bankers-round
boundary) across the diverse fixture set, NOT just on the single canonical example.

Composes with: §69 Verification Law (mechanical not theoretical), §41 HCRL,
§70 Surface Mirror Discipline (this stress-test receipt is the artifact mirror).

Stdlib only (§68): json, subprocess, pathlib, datetime, hashlib, sys.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
HOOK = REPO_ROOT / ".claude" / "hooks" / "byte_parity_drift.py"
LEDGER = REPO_ROOT / ".claude" / "_logs" / "byte-parity-stress-test-receipts.jsonl"

FIXTURES = [
    ("happy_path", "projects/v11-aep/publish-ready/aep/examples/example-preflight-header.aep"),
    ("atk_bad_pattern_injection", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-bad-pattern-injection.aep"),
    ("atk_ieee754_int_boundary", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-ieee754-int-boundary.aep"),
    ("atk_score_half_cent_boundary", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-score-half-cent-boundary.aep"),
    # Wave-026 additions (atk_genuine_block_network_capability + 3 fresh fixtures)
    ("atk_genuine_block_network_capability", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-genuine-block-network-capability.aep"),
    ("atk_nfkc_fullwidth_ascii_bypass", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-nfkc-fullwidth-ascii-bypass.aep"),
    ("atk_deep_nesting_stack", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-deep-nesting-stack.aep"),
    ("atk_rtl_override_id", "projects/v11-aep/publish-ready/aep/tests/v0_8_parity/atk-rtl-override-id.aep"),
]


def run_fixture(name: str, path: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HOOK), "--json", "--test-packet", path],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    if proc.returncode not in (0, 1):
        return {"fixture": name, "_error": f"hook_exit_{proc.returncode}",
                "_stderr": proc.stderr[:300]}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"fixture": name, "_error": f"json_decode_{e}",
                "_stdout": proc.stdout[:300]}
    return {
        "fixture": name,
        "fixture_path": path,
        "n_verifiers": data.get("n_verifiers", 0),
        "all_pins_ok": data.get("all_pins_ok", False),
        "byte_parity_ok": data.get("byte_parity_ok", False),
        "drift_count": data.get("drift_count", 0),
        "drift_messages_first3": data.get("drift_messages", [])[:3],
        "results_by_verifier": {
            k: {"verdict": v.get("verdict"), "score": v.get("score"),
                "hits_count": len(v.get("hits", []) or []) if isinstance(v.get("hits"), list) else None,
                "skipped": v.get("_skip", False), "error": v.get("_error")}
            for k, v in data.get("results_summary", {}).items()
        },
    }


def main() -> int:
    print(f"WAVE-022 stress test · {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  hook: {HOOK.relative_to(REPO_ROOT)}")
    print(f"  fixtures: {len(FIXTURES)}")
    print()

    results = []
    for name, path in FIXTURES:
        print(f"--- {name} ({path}) ---")
        result = run_fixture(name, path)
        results.append(result)
        if "_error" in result:
            print(f"  ERROR: {result['_error']}")
            continue
        print(f"  n_verifiers: {result['n_verifiers']}  all_pins_ok: {result['all_pins_ok']}")
        print(f"  byte_parity_ok: {result['byte_parity_ok']}  drift_count: {result['drift_count']}")
        for verifier, r in result["results_by_verifier"].items():
            if r.get("skipped"):
                marker = "skip"
            elif r.get("error"):
                marker = f"ERR:{r['error'][:30]}"
            else:
                marker = f"{r['verdict'][:12]:12s} score={r['score']} hits={r['hits_count']}"
            print(f"    [{verifier:32s}] {marker}")
        print()

    # Aggregate
    summary = {
        "wave": "022",
        "audited_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_fixtures": len(FIXTURES),
        "n_verifiers_pinned": 8,
        "n_verifiers_executable": 7,  # browser-js intentionally skipped
        "fixtures_with_full_parity": sum(1 for r in results if r.get("byte_parity_ok")),
        "fixtures_with_drift": sum(1 for r in results if not r.get("byte_parity_ok") and "_error" not in r),
        "fixtures_with_error": sum(1 for r in results if "_error" in r),
        "results": results,
    }

    receipt_body = json.dumps(summary, separators=(",", ":"), sort_keys=True)
    summary["receipt_sha256"] = hashlib.sha256(receipt_body.encode("utf-8")).hexdigest()

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":"), sort_keys=True) + "\n")

    print("=" * 60)
    print(f"AGGREGATE: {summary['n_fixtures']} fixtures × {summary['n_verifiers_executable']} executable verifiers")
    print(f"  full parity: {summary['fixtures_with_full_parity']}")
    print(f"  drift surfaced: {summary['fixtures_with_drift']}")
    print(f"  errors: {summary['fixtures_with_error']}")
    print(f"  receipt sha256: {summary['receipt_sha256'][:16]}...")
    print(f"  receipt at: {LEDGER.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
