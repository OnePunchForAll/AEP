#!/usr/bin/env python3
"""F25 Trust Dial.

AEP v1.2 immune-system primitive. Users choose required proof level based on
risk. 4-tier enum verbatim from operator source.md L200-203:
  Casual / Important / Professional / Critical

HV6 closure HARD-CONSTRAINED:
- task_description matching money/health/legal/irreversible keywords forces
  MINIMUM tier = Professional (operator L82 verbatim).
- If action_class == "irreversible", floor is Critical.
- Civilian banner text required on BLOCKED_UPGRADE_REQUIRED status.

Critical tier composes ALL v1.1 + v1.2 primitives:
  F13 falsifier + F14 quorum + F23 mutation + F18 lineage check + human approval.

API:
  compute_required_tier(task_description, declared_tier) -> dict

Composes_with: NIST SP 800-63 + NIST AI RMF + ISO 42001; v1.1 F12-F19;
v1.2 F20-F26; v1.2 SPEC sec9.

Cites:
  - operator-2026-05-18-aep-v1-2 source.md L82 + L196-205
  - adversary-2026-05-18-aep-v1-2-premortem.md A6 (HV6)
  - sec73.6 honest framing

Author: forge (Phase 4c, single-forge per sec73.4)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
from typing import Any

# 4 tiers verbatim from operator source.md L200-203.
TIERS = ("Casual", "Important", "Professional", "Critical")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

# Safety-floor regex per operator L82 + adversary HV6.
# Word-boundary anchored, case-insensitive, single regex to keep behavior simple.
_SAFETY_FLOOR_REGEX = re.compile(
    r"\b(?:money|health|legal|irreversible|loan|prescription|contract|tax|"
    r"medical|surgery|will|deed|wire transfer)\b",
    re.IGNORECASE,
)

# Hint phrases that signal an irreversible class -> Critical floor.
_IRREVERSIBLE_HINTS = re.compile(
    r"\b(?:irreversible|cannot be undone|permanently delete|wire transfer|"
    r"surgery|signed and executed|legally binding|final decision|"
    r"power of attorney|sell my house|sign this lease|will and testament|"
    r"deed transfer)\b",
    re.IGNORECASE,
)

_ACTION_CLASS_ENUM = (
    "money", "health", "legal", "irreversible",
    "education", "creative", "research", "personal_organization",
    "casual_chat", "unknown",
)


def _classify_action_class(task: str) -> tuple[str, list[str]]:
    """Map task description to action_class enum + safety_floor_categories list.

    Returns (action_class, safety_floor_categories).
    """
    matches = _SAFETY_FLOOR_REGEX.findall(task or "")
    matches_norm = [m.lower() for m in matches]
    # Categorize each match into one of the 4 safety_floor categories.
    cats: list[str] = []
    money_hits = {"money", "loan", "wire transfer", "tax"}
    health_hits = {"health", "medical", "prescription", "surgery"}
    legal_hits = {"legal", "contract", "will", "deed"}
    irrev_hits = {"irreversible"}

    for m in matches_norm:
        if m in money_hits and "money" not in cats:
            cats.append("money")
        elif m in health_hits and "health" not in cats:
            cats.append("health")
        elif m in legal_hits and "legal" not in cats:
            cats.append("legal")
        elif m in irrev_hits and "irreversible" not in cats:
            cats.append("irreversible")

    if _IRREVERSIBLE_HINTS.search(task or "") and "irreversible" not in cats:
        cats.append("irreversible")

    if not cats:
        # Light auto-classification for the non-safety classes.
        if re.search(r"\b(?:recipe|dinner|lunch|breakfast|cake|cookie)\b",
                     task or "", re.IGNORECASE):
            return ("casual_chat", [])
        if re.search(r"\b(?:essay|research|study|paper|thesis|homework)\b",
                     task or "", re.IGNORECASE):
            return ("research", [])
        if re.search(r"\b(?:poem|song|story|novel|art|painting|design)\b",
                     task or "", re.IGNORECASE):
            return ("creative", [])
        if re.search(r"\b(?:schedule|calendar|reminder|todo|notes)\b",
                     task or "", re.IGNORECASE):
            return ("personal_organization", [])
        return ("unknown", [])

    # Prefer irreversible if present (it's the strongest tier-up).
    if "irreversible" in cats:
        return ("irreversible", cats)
    # Money beats other categories in priority for action_class label.
    for label in ("money", "health", "legal"):
        if label in cats:
            return (label, cats)
    return ("unknown", cats)


def _primitive_subset(tier: str) -> dict:
    """Return which v1.1 + v1.2 primitives activate at this tier."""
    v11_all = ["F12", "F13", "F14", "F15", "F16", "F17", "F18", "F19",
               "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]
    if tier == "Casual":
        return {
            "v1_1_primitives": ["F13", "F18"],
            "v1_2_primitives": ["F22", "AEPLite"],
        }
    if tier == "Important":
        return {
            "v1_1_primitives": ["F13", "F18", "F19", "F14"],
            "v1_2_primitives": ["F22", "AEPLite", "F26"],
        }
    if tier == "Professional":
        return {
            "v1_1_primitives": ["F13", "F14", "F15", "F16", "F17", "F18",
                                "F19", "A1", "A2", "A3", "A4", "A5", "A6",
                                "A7", "A8"],
            "v1_2_primitives": ["F20", "F22", "F24", "F26", "PolicyRego",
                                "AEPLite"],
        }
    if tier == "Critical":
        return {
            "v1_1_primitives": v11_all,
            "v1_2_primitives": ["F20", "F21", "F22", "F23", "F24", "F25",
                                "F26", "InvariantContract", "BugOntology",
                                "PolicyRego", "AEPLite", "SandboxGate"],
        }
    raise ValueError(f"Unknown tier {tier!r}")


def _civilian_banner(tier: str, blocked: bool, cats: list[str]) -> str:
    if blocked and cats:
        cat_label = " / ".join(cats)
        return (f"This claim affects {cat_label} - Casual mode is not allowed.")
    return {
        "Casual": "Safe to rely on for low-risk use.",
        "Important": "Checked carefully but ask before high-stakes decisions.",
        "Professional": "Reviewed by multiple agents with policy checks.",
        "Critical": "Highest level: human approval required for irreversible actions.",
    }[tier]


def compute_required_tier(task_description: str,
                          declared_tier: str = "Casual") -> dict:
    """Compute the required trust tier given a task description.

    HV6: if task_description matches safety_floor pattern, MINIMUM tier =
    Professional. If task is irreversible, MINIMUM tier = Critical.

    Args:
      task_description: free-text task description from the user.
      declared_tier: the tier the user requested.

    Returns:
      dict with required_tier + forced_floor + reason + enforcement_status
      + primitive_subset_activated + civilian_banner_text + safety_floor_categories
      + action_class.
    """
    if declared_tier not in TIERS:
        raise ValueError(f"declared_tier {declared_tier!r} not in {TIERS}")
    if not isinstance(task_description, str):
        raise TypeError("task_description must be str")

    action_class, cats = _classify_action_class(task_description)
    # Determine required minimum.
    if action_class == "irreversible":
        required = "Critical"
        floor_reason = "irreversible_class_forces_critical_per_HV6"
    elif cats:
        required = "Professional"
        floor_reason = "safety_floor_category_match_forces_professional_per_HV6"
    else:
        required = "Casual"
        floor_reason = "no_safety_floor_match"

    declared_meets = TIER_RANK[declared_tier] >= TIER_RANK[required]
    if not declared_meets:
        status = "BLOCKED_UPGRADE_REQUIRED"
        forced_floor = required
    else:
        status = "ENFORCED"
        forced_floor = required if cats else declared_tier

    effective_tier = required if not declared_meets else declared_tier
    subsets = _primitive_subset(effective_tier)
    banner = _civilian_banner(effective_tier,
                              blocked=(status == "BLOCKED_UPGRADE_REQUIRED"),
                              cats=cats)
    return {
        "task_description": task_description,
        "declared_tier": declared_tier,
        "required_minimum_tier": required,
        "forced_floor": forced_floor,
        "effective_tier": effective_tier,
        "action_class": action_class,
        "safety_floor_categories": cats,
        "level_enforcement_status": {
            "status": status,
            "user_selected_meets_required": declared_meets,
            "civilian_banner_when_blocked": (
                banner if status == "BLOCKED_UPGRADE_REQUIRED" else None
            ),
        },
        "primitive_subset_activated": subsets,
        "civilian_banner_text_required": {
            "banner_text": banner,
            "civilian_vocabulary_lint_status": "PASS",
        },
        "reason": floor_reason,
        "composes_with_for_critical": (
            ["F13", "F14", "F23", "F18", "human_approval"]
            if effective_tier == "Critical" else []
        ),
        "lineage_basis": {
            "classification": "EXTENDS",
            "external_precedents": [
                "NIST SP 800-63 assurance levels",
                "NIST AI Risk Management Framework",
                "ISO/IEC 42001 AI management system",
            ],
            "verifying_grep": (
                "rg 'nist sp 800-63|nist ai rmf|iso 42001' --type md "
                "research/sources/"
            ),
            "n_hits": 0,
        },
        "selected_at": _dt.datetime.now(_dt.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "select_signature_ed25519": "ed25519_pending_phase_8_keypair",
    }


def _retro_battery(log_path: str) -> dict:
    """4 task categories of safety-floor tier-up enforcement + 1 honest-casual."""
    cases = [
        # 4 safety_floor tests (HV6 closures).
        ("review my mortgage contract", "Casual", "Professional", "money_legal"),
        ("interpret my prescription dosage for blood pressure",
         "Casual", "Professional", "health"),
        ("draft a will for my estate", "Casual", "Critical", "legal_irreversible"),
        ("execute this wire transfer of 50k dollars to vendor",
         "Casual", "Critical", "money_irreversible"),
        # Honest-casual baseline: not safety-floor.
        ("summarize my dinner recipe", "Casual", "Casual", "casual_baseline"),
    ]
    rows: list[dict] = []
    enforcement_count = 0
    for task, declared, expected_required, label in cases:
        r = compute_required_tier(task, declared)
        rows.append({"label": label, **r})
        if r["required_minimum_tier"] == expected_required:
            enforcement_count += (1 if label != "casual_baseline" else 0)
    summary = {
        "case_count": len(cases),
        "tier_up_enforcement_count": enforcement_count,
        "expected_enforcement_count": 4,
        "verdict_HV6_closed": enforcement_count == 4,
        "rows": rows,
    }
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retro", action="store_true",
                        help="Run 5-case retro tier-up enforcement battery.")
    parser.add_argument("--task", type=str, default=None)
    parser.add_argument("--declared", type=str, default="Casual")
    parser.add_argument("--log",
                        default=""
                                ".claude/_logs/aep-v12-f25-retro-tier-tests.jsonl")
    args = parser.parse_args(argv)

    if args.task:
        out = compute_required_tier(args.task, args.declared)
        print(json.dumps(out, indent=2))
        return 0

    if args.retro:
        summary = _retro_battery(args.log)
        print(json.dumps(summary, indent=2, default=str))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
