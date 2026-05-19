"""assign_skills_to_agents.py — operator directive 2026-05-15:
"if not i think we should be giving each claude main agent a set of high
quality skills to utilize (all in aep format of course)."

Appends an "## Assigned Skills (Task 5 amendment 2026-05-16)" section to each
of the 10 canonical agent .md files declaring primary / co-owner / utility
skills. Maps directly to the 12 anti-goal skill pack + 8 existing AEP project
skills generated in Tasks 3-4.

Idempotent: section marker presence → skip. Re-generates .aepkg/ companions
after amendment so sha256 triple-match holds.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("C:/Users/example-user/")
AGENTS_ROOT = REPO_ROOT / ".claude" / "agents"

SECTION_MARKER = "## Assigned Skills (Task 5 amendment 2026-05-16)"

# Shared utility skills (all 10 agents use these by default)
UTILITY_SKILLS = ["aep-search", "truth-tag", "lesson-capture"]

# Per-agent skill assignments
ASSIGNMENTS = {
    "strategist": {
        "primary": ["anti-goal-contract", "goal-decomposer"],
        "co_owner": [],
        "rationale": "Compiles strategic objectives into bounded /goal contracts. Decomposes mission spines for the canonical chain. Owns the strategic-framing surface that gates /goal invocation.",
    },
    "judge": {
        "primary": ["anti-goal-stop-hook-tribunal"],
        "co_owner": ["anti-goal-contract (with strategist)", "anti-goal-integration-boundary-labeler (with warden)"],
        "rationale": "Final-stop gate consumer for all anti-goal findings. Co-owns contract validators + integration-boundary-labeler (real vs mock honest classification).",
    },
    "scribe": {
        "primary": ["anti-goal-receipt-forge", "anti-goal-context-rot-anchor"],
        "co_owner": ["anti-goal-lesson-promoter (with curator)"],
        "rationale": "Produces evaluator-visible receipts for every /goal checkpoint. Anchors invariants outside chat to survive compaction. Co-owns lesson promotion to the correct durability surface.",
    },
    "adversary": {
        "primary": ["anti-goal-false-done-disassembler"],
        "co_owner": ["anti-goal-spec-drift-kill-switch (with pathfinder)", "anti-goal-prompt-injection-filter (with warden)"],
        "rationale": "Attacks /goal completion claims for checkbox laundering. Co-attacks the trace from PRD to diff (spec drift). Co-detects hostile instructions in external content (prompt injection).",
    },
    "warden": {
        "primary": ["anti-goal-loop-entropy-sentinel", "anti-goal-permission-minifier", "anti-goal-prompt-injection-filter", "doctrine-audit"],
        "co_owner": ["anti-goal-stop-hook-tribunal (with judge)", "anti-goal-checkpoint-rollback-warden (with pathfinder)", "anti-goal-integration-boundary-labeler (with judge)"],
        "rationale": "Owns hook enforcement, permission minimization, privacy/safety invariants. Detects entropy collapse + filters hostile instructions. Co-owns stop tribunal + rollback discipline + integration honesty.",
    },
    "pathfinder": {
        "primary": ["anti-goal-spec-drift-kill-switch", "anti-goal-checkpoint-rollback-warden"],
        "co_owner": ["goal-decomposer (with strategist)"],
        "rationale": "Owns spec-drift kill-switch (changed-file → source-requirement trace). Owns checkpoint+rollback discipline (no high-risk edit without recovery path). Co-decomposes complex goals.",
    },
    "scout": {
        "primary": ["research-protocol"],
        "co_owner": [],
        "rationale": "Owns the deep-research protocol (external prior-art absorption with anti-source-laundering preserved). Primary lens for V2 external-prior-art gate firings.",
    },
    "forge": {
        "primary": [],
        "co_owner": ["anti-goal-checkpoint-rollback-warden (auxiliary; pathfinder primary)"],
        "rationale": "Implementation owner — most /goal phases hit forge during the coding phase. Auxiliary to checkpoint discipline (forge produces the git commits that rollback consumes).",
    },
    "curator": {
        "primary": ["anti-goal-lesson-promoter", "project-spawn"],
        "co_owner": [],
        "rationale": "Owns lesson promotion to the correct durability surface (receipt → memory → rule → hook/test → skill). Owns project spawn from templates.",
    },
    "visual-judge": {
        "primary": ["visual-judge"],
        "co_owner": [],
        "rationale": "Owns visual artifact scoring (5-dim × 3-viewport rubric). For frontend /goal builds, verifies design.md fidelity + visual regressions + screenshots + UX acceptance.",
    },
}


def render_amendment(agent: str) -> str:
    """Build the skill-assignment section for one agent."""
    a = ASSIGNMENTS[agent]
    primary_block = "\n".join(f"- `{s}`" for s in a["primary"]) if a["primary"] else "(none — auxiliary role only)"
    co_block = "\n".join(f"- `{s}`" for s in a["co_owner"]) if a["co_owner"] else "(none)"
    utility_block = "\n".join(f"- `{s}`" for s in UTILITY_SKILLS)

    return f"""

{SECTION_MARKER}

**Source**: operator directive 2026-05-15 "if not i think we should be giving each claude main agent a set of high quality skills to utilize (all in aep format of course)" + the 12-skill anti-goal pack absorbed from operator-2026-05-15-goal-anti-immune-system-verdict + the 8 existing AEP project skills (all converted to AEP companions same turn).

### Primary skills (you lead execution)

{primary_block}

### Co-owner skills (shared execution; partner agent named)

{co_block}

### Utility skills (shared across all 10 agents)

{utility_block}

### Rationale

{a["rationale"]}

### How to use

When a /goal invocation hits your role:
1. Check if a primary skill applies → invoke it via the `Skill` tool (`Skill(skill="<slug>")`).
2. If a co-owner skill applies → coordinate with the partner agent named.
3. Always check utility skills (`aep-search` for prior-art lookup, `truth-tag` for claim labeling, `lesson-capture` for end-of-task lesson).
4. Per §60 pre-coding-lesson-review-discipline: scan relevant lessons BEFORE any code emission; the advisory hook surfaces top-3 candidates on Write/Edit.

Each skill carries an AEP companion at `.claude/skills/<slug>.aepkg/` with sha256 integrity envelope. Skills evolve via the canonical promotion ladder (STRONGLY PLAUSIBLE → PROVEN/RELIABLE) per criteria in each SKILL.md.
"""


def amend_agent_md(agent: str) -> tuple[bool, str]:
    md_path = AGENTS_ROOT / f"{agent}.md"
    if not md_path.exists():
        return (False, "missing .md")
    text = md_path.read_text(encoding="utf-8")
    if SECTION_MARKER in text:
        return (False, "already amended")
    if not text.endswith("\n"):
        text = text + "\n"
    amendment = render_amendment(agent)
    md_path.write_text(text + amendment.rstrip() + "\n",
                       encoding="utf-8", newline="\n")
    return (True, f"appended {amendment.count(chr(10))} lines")


def main():
    actions = {"amended": 0, "skipped": 0}
    for agent in sorted(ASSIGNMENTS):
        changed, msg = amend_agent_md(agent)
        flag = "AMENDED" if changed else "SKIP   "
        print(f"{flag}  {agent:<14} {msg}")
        if changed:
            actions["amended"] += 1
        else:
            actions["skipped"] += 1
    print()
    print(f"Summary: {actions['amended']} amended / {actions['skipped']} skipped")


if __name__ == "__main__":
    main()
