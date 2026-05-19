"""governance_owner_completeness.py — Pre-write validator for lesson `owners:` completeness.

PURPOSE
-------
Mechanically enforces the §59 Compounding-Intelligence-Lesson-Governance discipline:
EVERY agent cited in a lesson body — whether by canonical vec_id token
(`ledger::<agent>::lamport-...`) or by narrative mention ("forge dispatched", "judge verdict",
"adversary pre-mortem") — MUST appear in the lesson's frontmatter `owners:` field.

This closes the failure mode operator surfaced 2026-05-15:
  "ensure this behavior of mismanagement of lessons and owners and upgrades never happens again"
The behavior in question: scribe authors a lesson citing forge.lamport-X and judge.lamport-Y
in the body, but lists `owners: [scribe]` in frontmatter. Curator promotes the lesson without
catching the gap. Warden audits without owner-completeness check. The cited agents never
receive a cross-cite back-link, breaking the compounding-intelligence substrate.

USAGE
-----
Pipe candidate lesson HTML to stdin:
    python governance_owner_completeness.py < doctrine/lessons/2026-05-15-foo.aepkg/assets/original.html

Or pass --file:
    python governance_owner_completeness.py --file doctrine/lessons/2026-05-15-foo.aepkg/assets/original.html

EXIT CODES
----------
  0 : All cited agents appear in `owners:`. stdout: governance_owner_completeness_validated: true
  1 : One or more cited agents missing from `owners:`. stderr: missing-owners report + suggested fix.
  2 : Could not parse the lesson (malformed frontmatter, no body). Treated as ALLOW upstream
       (this is a governance check, not a schema validator).

CITES (sibling-78 anti-laundering + cross-agent canonical citations)
--------------------------------------------------------------------
  ledger::scribe::lamport-null-c8f3a2b5d7e1f4a6b9c2d5e8::loops-5-8-scribe-sibling-85-f1-f2-bound-attack-2026-05-15
  ledger::curator::lamport-null-loop-9-curator-s84-s85-s57-s58::curator-promote-sibling-84-85-section-57-58-2026-05-15
  ledger::adversary::lamport-56::loops-2-3-4-adversary-premortem-each-loop-2026-05-15
  doctrine:50-epistemic-hygiene-meta-law (NP-1 Explanation Ladder Gate)
  doctrine:41-hash-chained-receipt-ledger (HCRL composes with owner-completeness)
  pattern:single-writer-via-import (sibling-78)

Truth tag: STRONGLY PLAUSIBLE (forge.lamport-221 governance hook 2026-05-15).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

# The 9 canonical AEP project agents + visual-judge (per doctrine/agents/manifest.html).
# Plus operator-shadow which legitimately appears in owner lists.
_CANONICAL_AGENTS = frozenset({
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
    "operator-shadow",
})

# vec_id citation pattern: `ledger::<agent>::lamport-<counter>::<slug>` (or `lamport-null-<hex>`)
# Capture group 1 = the agent name slot.
_VEC_ID_RE = re.compile(
    r"ledger::([a-z][a-z\-]*[a-z])::lamport(?:-null)?-[0-9a-zA-Z\-]+",
    re.IGNORECASE,
)

# Narrative mention pattern: e.g. "forge dispatched", "judge verdict", "adversary pre-mortem".
# We use a deliberately conservative verb-list to avoid false positives on common English
# (e.g. "scribe wrote" only matches if "scribe" appears in agent-position with verb-context).
# Pattern: <agent>\s+(<one of these verbs/nouns>)
_NARRATIVE_VERBS = (
    r"dispatched|verdict|pre-mortem|premortem|audit|audited|built|"
    r"authored|emitted|surfaced|landed|fired|attack|attacked|"
    r"escalat(?:ed|ion)|promot(?:ed|ion)|verified|"
    r"validated|reviewed|approved|denied|blocked|recovered|signed|reserved|"
    r"flagged|stamped|graded|routed"
)
_NARRATIVE_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in sorted(_CANONICAL_AGENTS)) +
    r")\b[^a-zA-Z\-]*?(?:" + _NARRATIVE_VERBS + r")\b",
    re.IGNORECASE,
)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a lesson HTML/MD into (frontmatter_block, body_block).

    Frontmatter is delimited by leading `---` and a closing `---` line.
    If absent, returns ("", text).
    """
    # Allow a leading BOM / whitespace before the first `---`.
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


def _extract_owners_field(frontmatter: str) -> tuple[list[str] | None, int | None]:
    """Extract the `owners:` list from frontmatter.

    Returns (owners_list, line_number_of_owners_field) or (None, None) if absent.

    Supports both:
        owners: [a, b, c]                      (inline list)
        owners:                                 (block list)
          - a
          - b
          - c
    """
    lines = frontmatter.splitlines()
    for idx, line in enumerate(lines):
        if not re.match(r"^\s*owners\s*:", line):
            continue
        # Inline list on same line?
        m = re.match(r"^\s*owners\s*:\s*\[(?P<items>[^\]]*)\]\s*$", line)
        if m:
            raw = m.group("items").strip()
            if not raw:
                return [], idx + 1
            return [p.strip().strip("\"'") for p in raw.split(",")], idx + 1
        # Multi-line inline list? Prettier reflows `owners: [a, b, c]` to:
        #   owners:
        #     [
        #       a,
        #       b,
        #       c,
        #     ]
        # Look for `owners:` followed by lines beginning with `[`, items, `]`.
        if re.match(r"^\s*owners\s*:\s*$", line):
            # Look ahead for `[` ... `]` block within the next ~80 lines.
            buf: list[str] = []
            in_bracket = False
            for j, sub in enumerate(lines[idx + 1: idx + 81]):
                stripped = sub.strip()
                if not in_bracket:
                    if stripped == "[":
                        in_bracket = True
                        continue
                    # Inline list on the next line (rare).
                    bm = re.match(r"^\s*\[(?P<items>[^\]]*)\]\s*$", sub)
                    if bm:
                        raw = bm.group("items").strip()
                        if not raw:
                            return [], idx + 1
                        return [p.strip().strip("\"'") for p in raw.split(",")], idx + 1
                    # Block list `- item`?
                    if re.match(r"^\s*-\s*\S", sub):
                        break  # fall through to block-list parser below
                    # Anything else (blank, next key) → owners has no list value.
                    if stripped == "" or re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*:", sub):
                        return None, idx + 1
                else:
                    if stripped == "]" or stripped.endswith("]"):
                        # Capture content before the closing bracket on this line, if any.
                        tail = stripped.rstrip("]").rstrip(",").strip()
                        if tail:
                            buf.append(tail)
                        items = []
                        for piece in buf:
                            for sub_piece in piece.split(","):
                                p = sub_piece.strip().strip("\"'").strip(",").strip()
                                if p:
                                    items.append(p)
                        return items, idx + 1
                    # Strip trailing comma; the value may be a quoted string.
                    val = stripped.rstrip(",").strip()
                    if val:
                        buf.append(val)
            # Bracket-block didn't close cleanly within window — fall through.
        # Block list — collect subsequent `  - <item>` lines until indent drops or blank.
        items: list[str] = []
        for sub in lines[idx + 1:]:
            if re.match(r"^\s*-\s*\S", sub):
                items.append(sub.strip().lstrip("-").strip().strip("\"'"))
                continue
            if sub.strip() == "":
                continue
            # New top-level frontmatter key → owners block ended.
            if re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*:", sub):
                break
        return items, idx + 1
    return None, None


def _extract_cited_agents_from_body(body: str) -> tuple[set[str], set[str]]:
    """Scan the lesson body for cited agents.

    Returns (vec_id_agents, narrative_agents) — two disjoint sets of agent names
    found via canonical vec_id tokens vs narrative mentions. We separate them so
    the report can recommend "MUST add" (vec_id cites) vs "SHOULD add" (narrative).
    """
    vec_id_agents: set[str] = set()
    for m in _VEC_ID_RE.finditer(body):
        agent = m.group(1).lower()
        if agent in _CANONICAL_AGENTS:
            vec_id_agents.add(agent)

    narrative_agents: set[str] = set()
    for m in _NARRATIVE_RE.finditer(body):
        agent = m.group(1).lower()
        if agent in _CANONICAL_AGENTS:
            narrative_agents.add(agent)
    # Narrative-only = mentioned narratively but NOT via vec_id.
    narrative_only = narrative_agents - vec_id_agents
    return vec_id_agents, narrative_only


def _suggest_owners_line(existing: Iterable[str], add: Iterable[str]) -> str:
    """Render a suggested `owners:` line preserving existing order then appending new."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for o in existing:
        norm = o.strip().lower()
        if norm and norm not in seen_set:
            seen.append(norm)
            seen_set.add(norm)
    for a in sorted(add):
        if a not in seen_set:
            seen.append(a)
            seen_set.add(a)
    return "owners: [" + ", ".join(seen) + "]"


def validate(text: str, *, source_label: str = "<stdin>") -> int:
    """Run the governance check. Returns 0 (allow), 1 (block), or 2 (skip).

    On exit-1, prints a structured stderr report:
      missing_via_vec_id: [...]    (MUST be in owners — these are canonical cites)
      missing_via_narrative: [...]  (SHOULD be in owners — narrative mentions)
      suggested_owners_line: owners: [...]
      suggested_fix_for: <source_label>
    """
    frontmatter, body = _split_frontmatter(text)
    if not frontmatter:
        # Not a frontmatter-bearing lesson. Skip (treat as allow upstream).
        print("governance_owner_completeness: SKIP (no YAML frontmatter)", file=sys.stderr)
        return 2

    owners_list, _line_no = _extract_owners_field(frontmatter)
    if owners_list is None:
        print(
            "governance_owner_completeness: BLOCK (frontmatter has no `owners:` field). "
            "Add `owners: [<agents>]` listing every contributing agent per §59.",
            file=sys.stderr,
        )
        return 1

    owners_normalized = {o.strip().lower() for o in owners_list if o.strip()}
    vec_id_agents, narrative_only = _extract_cited_agents_from_body(body)

    # operator-shadow is allowed but not required to appear in body cites; skip narrative
    # detection of "operator-shadow" entirely (not in canonical agent set in narrative form).
    missing_vec_id = sorted(vec_id_agents - owners_normalized)
    missing_narrative = sorted(narrative_only - owners_normalized)

    if not missing_vec_id and not missing_narrative:
        print("governance_owner_completeness_validated: true", file=sys.stdout)
        return 0

    # BLOCK with structured report
    print("=" * 72, file=sys.stderr)
    print("§59 GOVERNANCE OWNER-COMPLETENESS BLOCK", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print(f"target: {source_label}", file=sys.stderr)
    print(f"current_owners: {sorted(owners_normalized)}", file=sys.stderr)

    if missing_vec_id:
        print(
            f"missing_via_vec_id (MUST add — canonical cites in body): {missing_vec_id}",
            file=sys.stderr,
        )
    if missing_narrative:
        print(
            f"missing_via_narrative (SHOULD add — narrative mentions): {missing_narrative}",
            file=sys.stderr,
        )

    suggested = _suggest_owners_line(
        existing=owners_normalized,
        add=set(missing_vec_id) | set(missing_narrative),
    )
    print(f"suggested_fix:", file=sys.stderr)
    print(f"  {suggested}", file=sys.stderr)
    print(
        "rationale: §59 Compounding-Intelligence-Lesson-Governance — every cited "
        "agent receives a back-link via owners; this is the load-bearing substrate "
        "for cross-agent recall and tier-promotion gates. "
        "Composes-with: §41 HCRL receipts + §50 EH NP-1/NP-2 + sibling-78 anti-laundering schema.",
        file=sys.stderr,
    )
    print("=" * 72, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--file", "-f", type=Path, default=None,
        help="Read lesson HTML from FILE instead of stdin",
    )
    args = ap.parse_args(argv)

    if args.file is not None:
        if not args.file.exists():
            print(f"governance_owner_completeness: file not found: {args.file}", file=sys.stderr)
            return 2
        text = args.file.read_text(encoding="utf-8", errors="replace")
        label = str(args.file)
    else:
        text = sys.stdin.read()
        label = "<stdin>"

    if not text.strip():
        # Empty input — no candidate to check. Allow.
        return 0

    return validate(text, source_label=label)


if __name__ == "__main__":
    sys.exit(main())
