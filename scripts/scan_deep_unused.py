"""scan_deep_unused.py — phase-2 deep scan for definitively-superseded files.

Targets paths the phase-1 Stop hook (.claude/hooks/self-clean-detect.ps1) skipped:
project-internal codex burn evidence, godview-worker job artifacts, v0.5-sprint
transient test corpora, .playwright-mcp/, transmutation/ outputs, aepkit-godview
server logs.

EXCLUDES files modified in the last 24h to avoid grabbing live/active artifacts.
EXCLUDES the canonical Lane B atk-*.aepkg fixtures (PROVEN/RELIABLE per sibling-60).

Usage:
    python scan_deep_unused.py --out .claude/_logs/deep-stale-candidates.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from datetime import datetime, timezone


# (path, cluster_tag, recurse, allow_recent_seconds)
TARGETS = [
    ("projects/godview-prime-v4/_codex-burns", "codex-burn-evidence-project-internal", True, 86400),
    ("projects/godview-prime-v4/data/codex-worker/jobs", "godview-worker-jobs", True, 86400),
    ("projects/godview-prime-v4/data/codex-worker/results", "godview-worker-results", True, 86400),
    ("projects/v11-aep/v0_5-perfection-sprint/batch-20", "v0_5-test-batch", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/batch-full", "v0_5-test-batch", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/deep-mig-test.aepkg", "v0_5-transient-test", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/deep-mig-test2.aepkg", "v0_5-transient-test", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/test-migration", "v0_5-migration-test", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/attack-hidden-2.aepkg", "v0_5-attack-scratch", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/attack-hidden-canonical.aepkg", "v0_5-attack-scratch", True, 0),
    ("projects/v11-aep/v0_5-perfection-sprint/attack-profile-laundering.aepkg", "v0_5-attack-scratch", True, 0),
    (".aepkit/codex-exec-proof", "codex-exec-proof", True, 86400),
    (".playwright-mcp", "playwright-test-artifacts", True, 86400),
    ("transmutation", "transmutation-outputs-stale", True, 86400),
    ("aepkit-godview/server.log", "predecessor-server-log", False, 0),
    ("aepkit-godview/server.log.err", "predecessor-server-log", False, 0),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--out", type=Path, default=Path(".claude/_logs/deep-stale-candidates.jsonl"))
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    out = (repo / args.out).resolve() if not args.out.is_absolute() else args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    now = time.time()
    rows = []
    summary = {}

    for rel_path, cluster_tag, recurse, allow_recent in TARGETS:
        full = repo / rel_path
        if not full.exists():
            continue

        if full.is_file():
            files = [full]
        elif recurse:
            files = [p for p in full.rglob("*") if p.is_file()]
        else:
            files = [p for p in full.iterdir() if p.is_file()]

        n_added = 0
        for f in files:
            try:
                mtime = f.stat().st_mtime
                age = now - mtime
                if allow_recent > 0 and age < allow_recent:
                    continue
                rel = str(f.relative_to(repo)).replace("\\", "/")
                rows.append({
                    "path": rel,
                    "rule": "R-deep-scan",
                    "cluster_tag": cluster_tag,
                    "size_bytes": f.stat().st_size,
                    "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    "age_days": round(age / 86400, 1),
                })
                n_added += 1
            except (OSError, PermissionError):
                continue

        summary[rel_path] = n_added

    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")

    print(json.dumps({
        "scan_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "n_candidates": len(rows),
        "total_bytes": sum(r["size_bytes"] for r in rows),
        "per_target": summary,
        "out_path": str(out.relative_to(repo) if out.is_relative_to(repo) else out),
    }, indent=2))


if __name__ == "__main__":
    main()
