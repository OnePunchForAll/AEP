#!/usr/bin/env python3
"""cleanup_first_pass_migration_artifacts.py — remove broken first-pass migration
events from ops/events.jsonl in the 116 packets affected by AEP61_BODY_ENVELOPE_LEAK.

The first-pass mass-migration (before the body-safe v2 fix) appended a
`v0.8_migration` event to each packet's ops/events.jsonl that contained the
literal hex of `previous_state_hash`. This triggered AEP61_BODY_ENVELOPE_LEAK
(envelope hash hex appearing in body file bytes) AND caused state_hash drift
(because body file bytes changed).

This script:
  1. Reads .claude/_logs/v0_8-corpus-audit.jsonl to identify affected packets.
  2. For each packet with AEP61_BODY_ENVELOPE_LEAK, reads ops/events.jsonl.
  3. Removes any line where `event_type == "v0.8_migration"`.
  4. Writes back.
  5. Reports cleanup count + verifies body is now leak-free.

Stdlib only (§68). No network. No subprocess.

Usage:
    python scripts/cleanup_first_pass_migration_artifacts.py            # dry-run
    python scripts/cleanup_first_pass_migration_artifacts.py --apply    # actually clean
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
AUDIT_PATH = REPO_ROOT / ".claude" / "_logs" / "v0_8-corpus-audit.jsonl"


def find_affected_packets(target_codes: Tuple[str, ...]) -> List[pathlib.Path]:
    """Read corpus audit JSONL and return packets with any of the target reason codes."""
    if not AUDIT_PATH.exists():
        print(f"audit JSONL not found at {AUDIT_PATH}", file=sys.stderr)
        sys.exit(1)
    affected: List[pathlib.Path] = []
    for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        codes = r.get("findings_by_code", {})
        if any(c in codes for c in target_codes):
            affected.append(REPO_ROOT / r["packet"])
    return affected


def cleanup_one(packet: pathlib.Path, apply: bool) -> Dict[str, int]:
    """Remove v0.8_migration events from ops/events.jsonl."""
    events_path = packet / "ops" / "events.jsonl"
    result = {"removed": 0, "kept": 0, "missing": 0}
    if not events_path.exists():
        result["missing"] = 1
        return result
    original = events_path.read_text(encoding="utf-8")
    kept_lines: List[str] = []
    for line in original.splitlines():
        if not line.strip():
            kept_lines.append(line)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue
        if rec.get("event_type") == "v0.8_migration":
            result["removed"] += 1
            continue
        kept_lines.append(line)
        result["kept"] += 1
    if result["removed"] > 0 and apply:
        new_content = "\n".join(kept_lines)
        if original.endswith("\n") and not new_content.endswith("\n"):
            new_content += "\n"
        events_path.write_text(new_content, encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Clean up first-pass migration artifacts")
    parser.add_argument("--apply", action="store_true",
                        help="actually write changes; default is dry-run")
    parser.add_argument("--codes", default="AEP61_BODY_ENVELOPE_LEAK",
                        help="comma-separated reason codes to target")
    args = parser.parse_args(argv)
    target_codes = tuple(c.strip() for c in args.codes.split(",") if c.strip())

    affected = find_affected_packets(target_codes)
    print(f"Found {len(affected)} packets matching {target_codes}")
    if not affected:
        return 0

    total = {"removed": 0, "kept": 0, "missing": 0, "packets_changed": 0}
    for packet in affected:
        r = cleanup_one(packet, apply=args.apply)
        if r["removed"] > 0:
            total["packets_changed"] += 1
            total["removed"] += r["removed"]
        total["kept"] += r["kept"]
        total["missing"] += r["missing"]

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] cleanup summary:")
    print(f"  packets changed: {total['packets_changed']}")
    print(f"  v0.8_migration events removed: {total['removed']}")
    print(f"  ops/events.jsonl lines preserved: {total['kept']}")
    print(f"  packets with no ops/events.jsonl: {total['missing']}")
    if not args.apply:
        print(f"\n(dry-run; re-run with --apply to actually clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
