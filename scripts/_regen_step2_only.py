"""Run only STEP 2 — agent definition companions — to avoid the unrelated
forge.jsonl non-canonical-number issue in STEP 1 ledger packets.

Per mission: ledger-packet regen noise restored via `git checkout HEAD -- .claude/agents/_ledgers/*.aepkg/`
after this script runs (step 1 .aepkg packets are unrelated to the .md amendment).
"""
from __future__ import annotations
import sys
from pathlib import Path

AEP_PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AEP_PROJECT / "scripts"))
from convert_ledgers_and_agents_to_aep import step2_agent_companion, CANONICAL_AGENTS


def main():
    print("=" * 70)
    print("STEP 2 ONLY — Build agent definition AEP companions")
    print("=" * 70)
    results = []
    for agent in CANONICAL_AGENTS:
        ok, msg = step2_agent_companion(agent)
        print(f"  {'OK' if ok else 'FAIL'}  {agent}: {msg}")
        results.append((agent, ok, msg))
    n_ok = sum(1 for _, ok, _ in results if ok)
    print(f"\n  Total: {n_ok}/{len(CANONICAL_AGENTS)} companions regenerated")


if __name__ == "__main__":
    main()
