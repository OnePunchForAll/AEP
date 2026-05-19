"""apply_cross_agent_citation_amendment.py — uniform amendment to all 10 canonical agent .md files.

Appends a "Cross-Agent Citation Discipline (sibling-76 amendment 2026-05-15)" section
that requires peer ledger references in canonical vec_id format:

  ledger::<peer-agent>::lamport-<N-or-id>::<short-slug>

The amendment closes the gap surfaced by falsifier_6_cross_agent_cites.py
(INSUFFICIENT-DATA verdict: n_cross_agent_citations = 0 in vec_id format across
all 10 canonical ledgers). Once the corpus contains N >= 4 cross-agent canonical
citations, F6 self-emitted recall (0.167) can be cross-validated against an
independent peer-judgment lens per scout op-double-evolution BEIR/TREC caution.

Idempotent: if the section marker is already present in a file, skip it.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path("C:/Users/example-user/")

CANONICAL_AGENTS = [
    "adversary", "curator", "forge", "judge", "pathfinder",
    "scout", "scribe", "strategist", "warden", "visual-judge",
]

SECTION_MARKER = "## Cross-Agent Citation Discipline (sibling-76 amendment 2026-05-15)"

AMENDMENT = """
## Cross-Agent Citation Discipline (sibling-76 amendment 2026-05-15)
**Added**: 2026-05-15 by sibling-76 universal-citation-and-uniform-application-discipline lesson + falsifier_6_cross_agent_cites.py INSUFFICIENT-DATA verdict.
**Truth tag**: STRONGLY PLAUSIBLE.
**Basis**: scout op-double-evolution BEIR/TREC caution about self-emitted-signal-as-gold circularity; F6 self-emitted recall 0.167 cannot yet be cross-validated against an independent peer-judgment lens because zero cross-agent citations exist in vec_id format across all 10 canonical ledgers.

### Required behavior
When you reference a peer agent's ledger row, emit the citation in the CANONICAL vec_id format inside `cites` or `lag_influenced_by`:

```
ledger::<peer-agent>::lamport-<N-or-id>::<short-slug>
```

Where `<peer-agent>` is one of the 10 canonical agents (adversary, curator, forge, judge, pathfinder, scout, scribe, strategist, visual-judge, warden) AND is different from your own role. Self-citations (same agent) use the same format but DO NOT satisfy the cross-agent gate.

### When cross-agent citations are required
Append a cross-agent citation whenever a peer's prior row was load-bearing for your dispatch:
- You consumed peer output as decision input (forge cites pathfinder's plan row; judge cites adversary's pre-mortem row; curator cites warden's audit row).
- You reproduced or extended a peer's claim (scribe cites curator's promotion row; strategist cites scout's external-prior-art absorption row).
- You ran a peer-emitted artifact and the outcome influenced your decision (visual-judge cites forge's artifact-build row; warden cites scribe's lesson row).
Narrative prose mentions ("scribe wrote sibling-76") DO NOT count — the canonical vec_id token is the only form that satisfies the peer-judgment lens.

### Discovery path when peer's lamport_counter is unknown
1. Read the peer's ledger at `.claude/agents/_ledgers/<peer-agent>.jsonl`.
2. Find the row by `session_id` + `invocation` substring match; copy its `lamport_counter` (or fall back to the BLAKE2b content-hash suffix per A14 closure if lamport is null).
3. Construct the vec_id: `ledger::<peer>::lamport-<N>::<short-slug-of-invocation>`.

### Anti-pattern to avoid
Do NOT fabricate a vec_id when you cannot find the peer's row. Emit either the verified canonical vec_id or an informal narrative reference; never invent lamport numbers. Citation-fabrication is a §50 Law-1 violation (semantic integrity over surface form).

### Composes with
- [sibling-76 universal-citation-and-uniform-application-discipline](../../doctrine/lessons/2026-05-15-universal-citation-and-uniform-application-discipline.html)
- [§55 FMV BP-8 citation-format-drift detector](../../doctrine/55-falsifier-meta-validation.html) — broader-format informal citations stay legal but do NOT satisfy the cross-agent gate.
- [§56 operational-evidence-over-synthetic-ranking](../../doctrine/56-operational-evidence-over-synthetic-ranking.html) — when N >= 4 cross-agent citations accumulate, F6 cross-agent recall can be computed per `projects/v11-aep/publish-ready/aep/scripts/falsifier_6_cross_agent_cites.py`; the resulting recall figure becomes a §56 promotion-gate input.
- [§50 Epistemic Hygiene Meta-Law](../../doctrine/50-epistemic-hygiene-meta-law.html) — Law-3 multi-lens convergence; cross-agent citations are the structural mechanism for an independent peer-judgment lens.
"""


def append_amendment(md_path: Path) -> tuple[bool, str]:
    text = md_path.read_text(encoding="utf-8")
    if SECTION_MARKER in text:
        return False, "already present (idempotent skip)"
    # Ensure exactly one blank line between existing tail and the new section
    if not text.endswith("\n"):
        text = text + "\n"
    new_text = text + AMENDMENT.rstrip() + "\n"
    md_path.write_text(new_text, encoding="utf-8", newline="\n")
    return True, f"appended {AMENDMENT.count(chr(10))} lines"


def main():
    results = []
    for agent in CANONICAL_AGENTS:
        md_path = REPO_ROOT / ".claude" / "agents" / f"{agent}.md"
        if not md_path.exists():
            results.append((agent, False, "MISSING"))
            continue
        changed, msg = append_amendment(md_path)
        results.append((agent, changed, msg))
    print(f"{'agent':<14} {'changed':<8} message")
    print("-" * 60)
    for agent, changed, msg in results:
        flag = "YES" if changed else "skip"
        print(f"{agent:<14} {flag:<8} {msg}")
    n_changed = sum(1 for _, c, _ in results if c)
    print(f"\nTotal changed: {n_changed}/{len(CANONICAL_AGENTS)}")


if __name__ == "__main__":
    main()
