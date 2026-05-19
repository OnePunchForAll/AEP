#!/usr/bin/env python3
"""test_v15_daemon_mode_n1000.py - Wave 2 daemon-mode N=1000 benchmark.

Wave 2 of AEP v1.5 LTS Ultimate Last Pass mission (2026-05-18).
Closes FINAL PASS-CLOSURE GAP 1: PreToolUse p95 cold-start floor.

TARGET: p95 <= 75ms STRICT (currently 82.728ms PASS-EQUIVALENT per v1.5 LTS
commit 9adb33da3 - 7.7ms over the 75ms gate).

This benchmark fires N=1000 subprocess calls to the daemon-mode client shim,
matching the production hook invocation path. Records latency per call.
Computes p50, p95, p99, mean, min, max. Writes to
.claude/aep/perf/daemon_mode_bench_wave2.jsonl.

INVOCATION
==========
python tests/test_v15_daemon_mode_n1000.py
  --n 1000                    (default; iterations)
  --warmup 5                  (default; pre-warm daemon)
  --client <path>             (default: .claude/hooks/aep/aep_pre_tool_guard_client.py)
  --no-skip-site              (default: false; use 'python -S' for fast startup)

Stdlib only. sec68-compliant (Python only).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CLIENT = os.path.join(REPO_ROOT, ".claude", "hooks", "aep", "aep_pre_tool_guard_client.py")
OUT_LOG = os.path.join(REPO_ROOT, ".claude", "aep", "perf", "daemon_mode_bench_wave2.jsonl")
SUMMARY_LOG = os.path.join(REPO_ROOT, ".claude", "aep", "perf", "daemon_mode_bench_wave2_summary.json")


def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fire_one(client_path, event_json, skip_site=True):
    """Fire one subprocess call. Returns (latency_ms, exit_code)."""
    cmd = ["python"]
    if skip_site:
        cmd.append("-S")
    cmd.append(client_path)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, input=event_json, capture_output=True, text=True, timeout=10)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return (elapsed_ms, proc.returncode, proc.stderr)


def percentile(sorted_list, p):
    if not sorted_list:
        return 0.0
    idx = int(len(sorted_list) * p)
    idx = min(idx, len(sorted_list) - 1)
    return sorted_list[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--client", default=DEFAULT_CLIENT)
    ap.add_argument("--no-skip-site", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.client):
        print(f"FATAL: client shim not found at {args.client}", file=sys.stderr)
        return 2

    # Vary event payloads so the benchmark isn't pathologically uniform
    events = [
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/test1.txt"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "C:/tmp/test2.py", "old_string": "a", "new_string": "b"}},
        {"tool_name": "Write", "tool_input": {"file_path": "/tmp/test3.txt", "content": "hello"}},
        {"tool_name": "Bash", "tool_input": {"command": "echo hello"}},
        {"tool_name": "Bash", "tool_input": {"command": "ls /tmp"}},
    ]

    os.makedirs(os.path.dirname(OUT_LOG), exist_ok=True)
    # Clear previous bench log so this run is fresh
    with open(OUT_LOG, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _utc_now_iso(), "phase": "bench_start", "n": args.n, "warmup": args.warmup}) + "\n")

    skip_site = not args.no_skip_site
    print(f"Wave-2 daemon-mode benchmark: N={args.n}, warmup={args.warmup}, client={args.client}, skip_site={skip_site}")

    # Warmup (spawn daemon, prime any caches)
    print(f"Warming up with {args.warmup} calls...")
    warmup_times = []
    for i in range(args.warmup):
        event_json = json.dumps(events[i % len(events)])
        latency, rc, _ = fire_one(args.client, event_json, skip_site=skip_site)
        warmup_times.append(latency)
        print(f"  warmup {i+1}: {latency:.2f}ms rc={rc}")

    # Real benchmark
    print(f"\nRunning N={args.n} benchmark...")
    latencies = []
    exit_codes = []
    errors = 0
    t_start = time.perf_counter()
    progress_every = max(1, args.n // 20)
    for i in range(args.n):
        event = events[i % len(events)]
        event_json = json.dumps(event)
        latency, rc, stderr = fire_one(args.client, event_json, skip_site=skip_site)
        latencies.append(latency)
        exit_codes.append(rc)
        if rc != 0 and rc != 2:
            errors += 1
        # Record per-call
        with open(OUT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": _utc_now_iso(),
                "iter": i,
                "tool_name": event["tool_name"],
                "latency_ms": round(latency, 3),
                "exit_code": rc,
            }, separators=(",", ":")) + "\n")
        if (i + 1) % progress_every == 0:
            so_far_sorted = sorted(latencies)
            so_far_p95 = percentile(so_far_sorted, 0.95)
            elapsed = time.perf_counter() - t_start
            print(f"  {i+1}/{args.n}  elapsed={elapsed:.1f}s  running p95={so_far_p95:.2f}ms")

    elapsed = time.perf_counter() - t_start

    # Stats
    latencies_sorted = sorted(latencies)
    p50 = percentile(latencies_sorted, 0.5)
    p95 = percentile(latencies_sorted, 0.95)
    p99 = percentile(latencies_sorted, 0.99)
    mean = sum(latencies) / len(latencies)
    mn = min(latencies)
    mx = max(latencies)
    target_ms = 75.0
    verdict = "PASS" if p95 <= target_ms else "FAIL"
    cold_start_baseline = 82.728  # from v1.5 LTS commit 9adb33da3

    summary = {
        "ts": _utc_now_iso(),
        "mission": "AEP-WAVE-2-AEP-V1-5-LTS-DAEMON-MODE-FORGE-A",
        "n": args.n,
        "warmup": args.warmup,
        "skip_site": skip_site,
        "client_path": args.client,
        "elapsed_s": round(elapsed, 2),
        "throughput_per_s": round(args.n / elapsed, 2) if elapsed > 0 else 0,
        "errors": errors,
        "blocks": sum(1 for rc in exit_codes if rc == 2),
        "allows": sum(1 for rc in exit_codes if rc == 0),
        "latency_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "p99": round(p99, 3),
            "mean": round(mean, 3),
            "min": round(mn, 3),
            "max": round(mx, 3),
        },
        "target_p95_ms": target_ms,
        "cold_start_baseline_p95_ms": cold_start_baseline,
        "improvement_ms": round(cold_start_baseline - p95, 3),
        "improvement_pct": round((cold_start_baseline - p95) / cold_start_baseline * 100, 2),
        "verdict": verdict,
        "warmup_times": [round(t, 3) for t in warmup_times],
    }

    with open(SUMMARY_LOG, "w", encoding="utf-8") as f:
        f.write(json.dumps(summary, indent=2))
    with open(OUT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"phase": "bench_end", **summary}, separators=(",", ":")) + "\n")

    print(f"\n=== Wave-2 daemon-mode N={args.n} benchmark ===")
    print(f"  elapsed: {elapsed:.2f}s ({summary['throughput_per_s']:.1f} calls/s)")
    print(f"  p50: {p50:.3f}ms")
    print(f"  p95: {p95:.3f}ms (target: {target_ms}ms, baseline cold-start: {cold_start_baseline}ms)")
    print(f"  p99: {p99:.3f}ms")
    print(f"  mean: {mean:.3f}ms")
    print(f"  range: {mn:.3f}-{mx:.3f}ms")
    print(f"  errors: {errors}, blocks: {summary['blocks']}, allows: {summary['allows']}")
    print(f"  improvement: -{summary['improvement_ms']:.3f}ms ({summary['improvement_pct']:.1f}% reduction)")
    print(f"  VERDICT: {verdict}")
    print(f"\n  summary -> {SUMMARY_LOG}")
    print(f"  rows    -> {OUT_LOG}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
