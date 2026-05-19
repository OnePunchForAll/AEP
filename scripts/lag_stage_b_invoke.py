"""lag_stage_b_invoke.py — Stage B explicit-invocation pattern for LAG.

Per LAG proposal v2 amendment #5 (forge HONEST GATE): Claude Code's PreToolUse
hook CANNOT mutate the dispatched agent's prompt. The Stage A advisory-stderr
hook delivers retrieval to the operator's stderr panel but does NOT close the
F2 mistakes-pct loop because the agent never sees the retrieved context.

Stage B: explicit orchestrator-level pre-dispatch invocation. The orchestrator
(the agent) calls this script BEFORE the Task tool dispatch, captures the injection
block, and PREPENDS it to the prompt explicitly. Operator-explicit (not auto),
preserving §50 single-writer + Hybrid Bridge direction.

This script is the canonical orchestrator-side wrapper. Returns the augmented
prompt on stdout for piping or capture.

Usage:
    # Inside the agent's orchestrator code, BEFORE Task dispatch:
    augmented=$(python lag_stage_b_invoke.py --agent <name> --prompt "$ORIGINAL_PROMPT" --format prompt-prepended)
    # Then dispatch Task with augmented prompt.

    # Or get the injection block separately:
    block=$(python lag_stage_b_invoke.py --agent <name> --prompt "$ORIGINAL_PROMPT" --format block-only)

Closes F2 mechanically by: (a) injecting context the agent actually reads;
(b) emitting an HCRL receipt to .claude/_logs/lag-stage-b-invocations.jsonl;
(c) marking the prompt with <prior-runs-context source="LAG-Stage-B"> so
warden's F4 audit can verify the agent acknowledged.

Anthropic GH issue #49106 (OnAgentSpawn) is the long-term sanctioned surface;
until shipped, Stage B is the operator-explicit canonical mechanism.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CANONICAL_AGENTS = {
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
}
# A11 mitigation (BLOCK) per adversary operator-double 2026-05-15: enforce canonical-10
# at this CLI entry point too (not just hook + retrieve.py).


def b2(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=32).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--prompt", required=True, help="original task prompt")
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--format", choices=["prompt-prepended", "block-only", "json"],
                    default="prompt-prepended")
    ap.add_argument("--index-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings"))
    ap.add_argument("--allow-non-canonical-agent", action="store_true",
                    help="debug-only: skip canonical-10 allowlist (A11 mitigation)")
    args = ap.parse_args(argv)

    # A11 BLOCK per adversary operator-double findings
    if args.agent not in CANONICAL_AGENTS and not args.allow_non_canonical_agent:
        raise SystemExit(
            f"A11 BLOCK: agent='{args.agent}' is not in canonical-10 allowlist. "
            f"Operator-disabled or unknown agents cannot have ledgers retrieved."
        )

    hint = args.prompt[:200] if len(args.prompt) > 200 else args.prompt

    result = subprocess.run(
        [sys.executable, "projects/v11-aep/publish-ready/aep/scripts/lag_retrieve.py",
         "--agent", args.agent, "--task-hint", hint, "--top-k", str(args.top_k),
         "--max-tokens", str(args.max_tokens), "--format", "injection-block",
         "--index-root", str(args.index_root)],
        capture_output=True, text=True, timeout=60,
    )

    block = result.stdout.strip()
    if not block or block.startswith("# LAG: no index"):
        # No index or empty result — return prompt unchanged
        if args.format == "prompt-prepended":
            print(args.prompt)
        elif args.format == "block-only":
            print("")
        else:
            print(canon({"agent": args.agent, "injection_status": "skipped",
                         "reason": "no_index_or_empty"}))
        return 0

    # Replace Stage-A "LAG" source attribute with "LAG-Stage-B" for F4 audit clarity
    block = block.replace('source="LAG"', 'source="LAG-Stage-B"', 1)

    # Emit HCRL receipt
    receipts_path = Path(".claude/_logs/lag-stage-b-invocations.jsonl")
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "receipt_type": "lag_stage_b_invocation",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": args.agent,
        "prompt_sha256": "blake2b-256:" + b2(args.prompt),
        "hint_length": len(hint),
        "top_k": args.top_k,
        "max_tokens": args.max_tokens,
        "block_length": len(block),
        "block_lines": len(block.split("\n")),
    }
    receipt["this_receipt_hash"] = "blake2b-256:" + b2(canon(receipt))
    with open(receipts_path, "a", encoding="utf-8") as f:
        f.write(canon(receipt) + "\n")

    if args.format == "prompt-prepended":
        print(block)
        print()
        print(args.prompt)
    elif args.format == "block-only":
        print(block)
    else:
        print(canon({
            "agent": args.agent,
            "injection_status": "ok",
            "block": block,
            "augmented_prompt_length": len(block) + 2 + len(args.prompt),
            "original_prompt_length": len(args.prompt),
            "estimated_overhead_tokens": len(block) // 4,
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
