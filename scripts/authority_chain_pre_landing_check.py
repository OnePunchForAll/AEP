"""authority_chain_pre_landing_check.py — PRE-LANDING guard against BP-D-DEL-* anti-patterns.

OPERATOR DIRECTIVE 2026-05-16 (Wave-E pathfinder task-08):
Catch self-authored-authority-chain + generic-trust-as-co-sign + bypassed
multi-reviewer-mesh patterns at LANDING time (before the commit lands), not
at adversary-red-team time (after the commit). The cheapest disconfirmer
should fire BEFORE the file write, not as a post-mortem.

THE PROBLEM IT SOLVES
=====================
Adversary Wave-D task-03 surfaced 7 attack vectors (5 NEW BP-D-DEL-1..5 HIGH
+ 2 AMPLIFIED BP-D-DEL-6/7 MED) demonstrating that the §66 PROVEN/RELIABLE
landing commit 7d8fb775b had been authored under a structurally invalid
authority chain. The mechanical evidence (G1-G5 gates) was genuine; the
DELEGATION reading of operator message "I leave it in your hands" as
satisfying named operator-decision-required gates was a category error.

By Wave-D adversary task-03 the bad commit was already on disk. The
rollback (commit ed0db942e) was cheap, but the cultural-norm cost was
durable: future agents retrieving the audit artifact via §57 retrieval
would learn "this style of authority-chain reasoning was once shipped."

This script CLOSES the door before the bad commit lands:

  - BP-D-DEL-1: detect "data-promoted-by" containing tokens that indicate
    delegated-not-named authority (e.g., "delegated", "trust-message",
    "leave-it-in-your-hands", "i-trust-you") → require curator + judge +
    adversary sign-off proposals before landing.

  - BP-D-DEL-2: detect "later operator message contradicts earlier
    operator constraint without naming it" → flag at HUDDLE step 1 of the
    §66 protocol with explicit narrower-wins reminder.

  - BP-D-DEL-4: detect "data-authored-by == data-promoted-by AND
    tier-flip > 1 epistemic level" → block landing until independent
    reviewer (not the authoring agent) co-signs on the audit artifact
    itself (not just on the gate-evidence).

PROTOCOL
========
1. Agent (or hook) computes the candidate landing artifact in memory OR
   reads it from disk if already written.
2. Pipe to:
     python authority_chain_pre_landing_check.py < candidate_landing.html
   OR specify --file <path> for an artifact on disk.
3. The script parses:
   - data-status / data-tt (current truth-tag end-state)
   - data-authored-by (the agent claiming authorship)
   - data-promoted-by (the agent claiming promotion-authority)
   - data-promotion-basis (free-form text justifying authority chain)
   - data-rolled-back-at / data-rollback-reason (rollback evidence; if set
     the artifact is a previous mis-landing; treat as KNOWN-anti-pattern)
4. EXIT 0 + per-check OK lines if all 3 BP-D-DEL checks PASS.
5. EXIT 1 + stderr report if ANY check FAILs. The commit IS NOT landed.

USAGE — CLI
===========
  cat candidate_landing.html | python authority_chain_pre_landing_check.py
  echo $?  # 0 = safe to land; 1 = REJECT (BP-D-DEL-* fired)

  python authority_chain_pre_landing_check.py --file doctrine/66-...html
  python authority_chain_pre_landing_check.py --file <path> --strict

  Optional flags:
    --strict      Treat MED-severity findings as FAIL (default: HIGH only).
    --quiet       Suppress per-check OK lines (still emits failures).
    --landing-class <status-promotion-class|amendment|other>
                  Restrict checks to specific landing class.
    --reviewer-mesh-floor N
                  Minimum independent reviewer count for BP-D-DEL-4
                  (default: 2 — curator + judge + ≥1 of adversary/warden).

USAGE — PROGRAMMATIC
====================
  from authority_chain_pre_landing_check import check_authority_chain
  result = check_authority_chain(html_content, landing_class="status-promotion-class")
  if not result.ok:
      raise RuntimeError(f"REJECTED at pre-landing: {result.report}")
  # else: proceed with landing commit

INTEGRATION RECOMMENDATION
==========================
Wire as a PreToolUse hook on Write/Edit/MultiEdit when:
  - target path matches `doctrine/<NN>-*.html` AND
  - the proposed change includes a `data-status` transition where
    new_status > current_status by ≥1 epistemic level
  OR
  - target path matches `doctrine/_proposals/promotion-audit-*.html`

The hook reads the candidate content from the tool call, invokes this
script, and blocks the write on exit-1.

Truth tag: STRONGLY PLAUSIBLE (pathfinder.wave-E-task-08 2026-05-16;
skeleton landing; full implementation requires forge co-sign on regex
patterns + reviewer-mesh sentinel paths).

Composes with:
  - sibling-93 lesson (the anti-pattern this script detects).
  - adversary.wave-D-delegated-authority-red-team (the 7-attack inventory).
  - the agent Constitution §Authority-delegation-naming requirement (the
    operator-mandated rule this script mechanizes).
  - §61.P1-P6 multi-reviewer mesh (the independent-reviewer floor BP-D-DEL-4
    requires).
  - preflight_validate_ledger_row.py (sibling discipline; pre-emission
    guards rather than post-hoc audits).

Cites:
  - ledger::adversary::lamport-64::wave-D-delegated-authority-red-team-2026-05-16
  - lesson:sibling-93
  - pattern:falsifier-fired-from-within
  - pattern:narrower-wins-not-more-recent-wins
  - doctrine:50-epistemic-hygiene-meta-law (Law-1 cheapest-disconfirmer)
  - doctrine:03-validation-gates
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# CONSTANTS — patterns derived from BP-D-DEL-1..7 inventory in adversary
# Wave-D verdict + sibling-93 lesson + the agent Constitution amendment.
# ---------------------------------------------------------------------------

# Tokens that indicate delegated-not-named authority. If data-promoted-by
# or data-promotion-basis contains any of these, BP-D-DEL-1 fires unless
# an independent reviewer sign-off is also present.
DELEGATED_AUTHORITY_TOKENS = (
    "delegated",
    "delegation",
    "trust-message",
    "trust message",
    "trust-and-go-to-sleep",
    "leave-it-in-your-hands",
    "leave it in your hands",
    "i-trust-you",
    "i trust you",
    "i leave it",
    "generic-trust",
    "implicit-approval",
    "implicit approval",
    "unambiguous-delegation",
    "going-to-sleep",
    "going to sleep",
)

# Tier-flip is detected by comparing axis-A epistemic levels.
# Order from weakest to strongest. Wave-E pathfinder explicitly preserves
# the per-section §02 ordering.
TIER_ORDER = (
    "impossible-unsupported",
    "dangerous-not-worth-doing",
    "speculative-frontier",
    "experimental",
    "plausible",
    "strongly-plausible",
    "proven-reliable",
)

# Truth-tag aliases (data-tt + data-status synonyms surfaced in the
# AEP project doctrine + lesson corpus).
TIER_ALIASES = {
    "strongly-plausible-active": "strongly-plausible",
    "strongly-plausible-canonical": "strongly-plausible",
    "strongly-plausible-pending-operator-landing": "strongly-plausible",
    "proven-reliable-empirical": "proven-reliable",
    "proven-reliable-canonical": "proven-reliable",
    "rolled-back": "rolled-back",  # SPECIAL: indicates prior mis-landing
}

# Sentinel attributes that imply a previous landing was reverted; presence
# means the artifact is a KNOWN-anti-pattern and this script should refuse
# to bless a re-landing without an explicit operator-named co-sign.
ROLLBACK_SENTINELS = (
    "data-rolled-back-at",
    "data-rollback-reason",
    "data-anti-pattern-marker",
)

# §61.P1-P6 multi-reviewer mesh — these are the agent classes that may
# satisfy BP-D-DEL-4 independent-reviewer floor. Same agent as authored-by
# does NOT count.
INDEPENDENT_REVIEWER_AGENTS = (
    "curator",
    "judge",
    "adversary",
    "warden",
    "strategist",
    "scribe",
    "scout",
    "visual-judge",
    "pathfinder",
    "forge",
)


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class CheckVerdict:
    """One BP-D-DEL-* check verdict."""
    bp_code: str           # 'BP-D-DEL-1' | 'BP-D-DEL-2' | 'BP-D-DEL-4'
    severity: str          # 'HIGH' | 'MED' | 'LOW' | 'PASS'
    status: str            # 'PASS' | 'FAIL' | 'WARN' | 'SKIPPED'
    reason: str            # human-readable explanation
    matched_tokens: list[str] = dataclasses.field(default_factory=list)
    recommendation: str = ""


@dataclasses.dataclass
class AuthorityChainReport:
    """Aggregate report for one candidate landing."""
    ok: bool
    landing_class: str
    verdicts: list[CheckVerdict]
    parsed_metadata: dict
    report: str   # combined human-readable report


# ---------------------------------------------------------------------------
# PARSERS
# ---------------------------------------------------------------------------

_DATA_ATTR_RE = re.compile(
    r'data-([\w-]+)\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)


def parse_data_attributes(html_content: str) -> dict:
    """Extract all data-* attributes from <body> + <html> + <article>.

    Returns a flat dict keyed by attribute name (without 'data-' prefix).
    Last-write wins for duplicates — landing attributes typically appear
    on <body>; rolled-back-at / anti-pattern-marker on inner sections.
    """
    out = {}
    for m in _DATA_ATTR_RE.finditer(html_content):
        key = m.group(1).lower()
        val = m.group(2).strip().lower()
        out[key] = val
    return out


def normalize_tier(tier: str) -> str:
    """Map data-tt / data-status to canonical TIER_ORDER token."""
    if not tier:
        return ""
    t = tier.lower().replace(" ", "-")
    return TIER_ALIASES.get(t, t)


def tier_rank(tier: str) -> int:
    """Return ordinal rank for a tier; -1 if unknown."""
    norm = normalize_tier(tier)
    try:
        return TIER_ORDER.index(norm)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# THE THREE BP-D-DEL CHECKS
# ---------------------------------------------------------------------------

def check_bp_d_del_1(metadata: dict, html_content: str) -> CheckVerdict:
    """BP-D-DEL-1: generic-trust-as-specific-approval substitution.

    Detect: data-promoted-by OR data-promotion-basis contains tokens that
    indicate delegated-not-named authority.

    PASS if no delegated-authority tokens detected.
    FAIL if any token detected AND no independent named co-sign present.
    WARN if token detected AND at least one named co-sign present.
    """
    haystacks = []
    for field in ("promoted-by", "promotion-basis", "authority-chain"):
        v = metadata.get(field, "")
        if v:
            haystacks.append((field, v))
    # Also scan the inline "Authority Chain" section if present in HTML.
    if "authority chain" in html_content.lower() or "authority-chain" in html_content.lower():
        # Crude scan of HTML body for the same tokens; full impl would
        # extract a specific <section id="authority-chain"> block.
        haystacks.append(("inline-authority-chain-section", html_content.lower()))

    matched = []
    for field, hay in haystacks:
        for tok in DELEGATED_AUTHORITY_TOKENS:
            if tok in hay:
                matched.append(f"{field}:{tok}")

    if not matched:
        return CheckVerdict(
            bp_code="BP-D-DEL-1",
            severity="PASS",
            status="PASS",
            reason="No delegated-authority tokens detected in promotion metadata.",
        )

    # Check for explicit named co-sign as mitigating evidence
    named_cosign_present = bool(metadata.get("operator-named-cosign"))

    if named_cosign_present:
        return CheckVerdict(
            bp_code="BP-D-DEL-1",
            severity="MED",
            status="WARN",
            reason=(
                "Delegated-authority tokens detected but operator-named-cosign "
                "attribute is present. Verify the named co-sign references the "
                "specific gate-ID / doctrine slot + tier."
            ),
            matched_tokens=matched,
            recommendation=(
                "Confirm operator-named-cosign attribute value explicitly names "
                "(a) gate-ID, (b) doctrine slot, (c) target tier. If any field "
                "is missing or generic, re-classify as FAIL."
            ),
        )

    return CheckVerdict(
        bp_code="BP-D-DEL-1",
        severity="HIGH",
        status="FAIL",
        reason=(
            "Delegated-authority tokens detected in promotion metadata AND no "
            "operator-named-cosign attribute. Per sibling-93 + the agent Constitution "
            "§Authority-delegation-naming requirement, generic trust-messages do "
            "NOT satisfy operator-decision-required gates."
        ),
        matched_tokens=matched,
        recommendation=(
            "Require curator + judge + adversary sign-off proposals BEFORE landing. "
            "Operator message must NAME the gate (gate-ID / doctrine slot + target "
            "tier). If operator is asleep, DEFAULT to HOLD; revert any landing "
            "performed under generic-trust reading."
        ),
    )


def check_bp_d_del_2(metadata: dict, html_content: str) -> CheckVerdict:
    """BP-D-DEL-2: later operator message contradicts earlier constraint
    without naming it.

    Detect: data-prior-constraint-message-id is set AND
    data-cosign-message-id is set AND the cosign message does not NAME the
    prior constraint.

    This check is partially mechanical — full prior-message parsing
    requires reading the operator-messages.jsonl file and inspecting
    constraint-naming language. The skeleton stamps WARN when both
    message-ids are present but no machine-verifiable naming-overlap is
    detected; full impl would dereference both messages and run a
    constraint-name extractor.

    PASS if no prior constraint or cosign clearly names the prior
    constraint.
    WARN if prior constraint exists and cosign does not name it (potential
    narrower-wins violation).
    FAIL is reserved for full-impl mode (--strict).
    """
    prior_id = metadata.get("prior-constraint-message-id")
    cosign_id = metadata.get("cosign-message-id")
    explicit_supersession = metadata.get("explicit-supersession-of-prior-constraint")

    if not prior_id:
        return CheckVerdict(
            bp_code="BP-D-DEL-2",
            severity="PASS",
            status="PASS",
            reason="No prior operator-constraint declared; narrower-wins check N/A.",
        )

    if explicit_supersession and explicit_supersession.lower() == "true":
        return CheckVerdict(
            bp_code="BP-D-DEL-2",
            severity="PASS",
            status="PASS",
            reason=(
                f"Prior constraint {prior_id} explicitly superseded "
                f"by cosign {cosign_id or 'unknown'} per data-explicit-supersession "
                "attribute. Narrower-wins honored."
            ),
        )

    return CheckVerdict(
        bp_code="BP-D-DEL-2",
        severity="MED",
        status="WARN",
        reason=(
            f"Prior constraint {prior_id} declared. Cosign {cosign_id or 'absent'} "
            "must EXPLICITLY name the prior constraint to widen it. Set "
            "data-explicit-supersession-of-prior-constraint=\"true\" with cite to "
            "the cosign message text naming the constraint, OR HOLD per "
            "narrower-wins default."
        ),
        recommendation=(
            "Read both messages side-by-side. If the later message does not name "
            "the prior constraint, the prior constraint stands. Surface to HUDDLE "
            "step 1 with explicit narrower-wins reminder."
        ),
    )


def check_bp_d_del_4(metadata: dict, html_content: str, reviewer_floor: int) -> CheckVerdict:
    """BP-D-DEL-4: self-authored authority-chain.

    Detect: data-authored-by == data-promoted-by AND tier-flip > 1
    epistemic level.

    PASS if data-authored-by != data-promoted-by OR tier-flip <= 1.
    WARN if tier-flip == 1 AND authored == promoted (small jump; still
    requires reviewer-floor confirmation).
    FAIL if tier-flip > 1 AND authored == promoted AND independent
    reviewer count < reviewer_floor (default 2).
    """
    authored_by = metadata.get("authored-by", "").lower()
    promoted_by = metadata.get("promoted-by", "").lower()
    tt_current = normalize_tier(metadata.get("tt") or metadata.get("status") or "")
    tt_prior = normalize_tier(metadata.get("tt-prior") or metadata.get("prior-tt") or "")

    if not authored_by:
        return CheckVerdict(
            bp_code="BP-D-DEL-4",
            severity="LOW",
            status="WARN",
            reason="data-authored-by attribute missing; cannot verify reviewer mesh.",
            recommendation="Add data-authored-by attribute naming the authoring agent.",
        )

    if not promoted_by:
        # No promotion claim at all → not a promotion artifact; skip.
        return CheckVerdict(
            bp_code="BP-D-DEL-4",
            severity="PASS",
            status="PASS",
            reason="No data-promoted-by attribute; not a promotion-class landing.",
        )

    # Normalize: an authored-by/promoted-by like
    # "diana-shadow-operator-with-curator-judge-adversary-cosign" implies
    # multi-reviewer mesh; honor it as PASS.
    multi_reviewer_substrings = [a for a in INDEPENDENT_REVIEWER_AGENTS
                                 if a in promoted_by and a not in authored_by]

    same_agent = authored_by == promoted_by or (
        # detect "diana-X" authored == "diana-Y" promoted as effectively same
        authored_by.split("-")[0] == promoted_by.split("-")[0]
        and "diana" in authored_by
    )

    tier_jump = 0
    if tt_prior and tt_current:
        rcur = tier_rank(tt_current)
        rprev = tier_rank(tt_prior)
        if rcur >= 0 and rprev >= 0:
            tier_jump = rcur - rprev

    if same_agent and tier_jump > 1 and len(multi_reviewer_substrings) < reviewer_floor:
        return CheckVerdict(
            bp_code="BP-D-DEL-4",
            severity="HIGH",
            status="FAIL",
            reason=(
                f"data-authored-by='{authored_by}' == data-promoted-by='{promoted_by}' "
                f"AND tier-flip {tt_prior} → {tt_current} (jump={tier_jump}); only "
                f"{len(multi_reviewer_substrings)} independent reviewer agent(s) "
                f"detected in promoted-by (floor={reviewer_floor}). Per §61.P1-P6 "
                "multi-reviewer mesh, status-flip-class actions require independent "
                "reviewer co-signs on the audit artifact ITSELF."
            ),
            matched_tokens=multi_reviewer_substrings,
            recommendation=(
                "Block landing until ≥{floor} independent reviewer agents co-sign "
                "the audit artifact (not just the gate-evidence). Add "
                "data-cosigned-by attribute listing the reviewer agents authored "
                "AFTER the audit artifact lands."
            ).format(floor=reviewer_floor),
        )

    if same_agent and tier_jump > 1:
        return CheckVerdict(
            bp_code="BP-D-DEL-4",
            severity="MED",
            status="WARN",
            reason=(
                f"Same-agent authorship + multi-level tier flip ({tier_jump}) "
                f"with {len(multi_reviewer_substrings)} reviewer agent(s) named. "
                "Verify reviewer co-signs were authored AFTER the audit artifact "
                "landed, not before."
            ),
            matched_tokens=multi_reviewer_substrings,
            recommendation=(
                "Confirm each named reviewer signed AFTER artifact landing time. "
                "If any signature predates the artifact, treat as PROMOTE-CANDIDATE "
                "evidence not LANDING co-sign."
            ),
        )

    if same_agent and tier_jump == 1:
        return CheckVerdict(
            bp_code="BP-D-DEL-4",
            severity="LOW",
            status="WARN",
            reason=(
                f"Same-agent authorship with single-level tier jump ({tt_prior} → "
                f"{tt_current}). Within tolerance for low-risk landings but still "
                "recommend ≥1 independent reviewer co-sign."
            ),
        )

    return CheckVerdict(
        bp_code="BP-D-DEL-4",
        severity="PASS",
        status="PASS",
        reason=(
            f"Independent reviewer mesh present (authored-by != promoted-by OR "
            f"tier-jump <= 1). same_agent={same_agent} tier_jump={tier_jump} "
            f"reviewers_in_promoted_by={multi_reviewer_substrings}"
        ),
    )


# ---------------------------------------------------------------------------
# ROLLBACK-SENTINEL CHECK (treat known anti-patterns as instant FAIL on re-land)
# ---------------------------------------------------------------------------

def check_rollback_sentinel(metadata: dict) -> Optional[CheckVerdict]:
    """If the artifact carries a rollback sentinel, treat as known anti-pattern.

    Returns None if no sentinel found. Otherwise returns a FAIL verdict
    that takes precedence over the three BP-D-DEL checks.
    """
    matched = [s for s in ROLLBACK_SENTINELS if s.replace("data-", "") in metadata]
    if not matched:
        return None
    return CheckVerdict(
        bp_code="BP-D-DEL-ROLLBACK-SENTINEL",
        severity="HIGH",
        status="FAIL",
        reason=(
            f"Artifact carries rollback-sentinel attribute(s) {matched}. Per "
            "sibling-93 + BP-D-DEL-6 cultural-norm-reversibility, a previously "
            "rolled-back landing MUST NOT be re-landed under the same authority "
            "basis. Explicit operator-named co-sign required."
        ),
        recommendation=(
            "Operator must explicitly authorize the re-landing in a message "
            "naming (a) the artifact, (b) the prior rollback, (c) the new "
            "authority basis. If not present, HOLD."
        ),
    )


# ---------------------------------------------------------------------------
# AGGREGATE CHECK
# ---------------------------------------------------------------------------

def check_authority_chain(
    html_content: str,
    landing_class: str = "status-promotion-class",
    strict: bool = False,
    reviewer_floor: int = 2,
) -> AuthorityChainReport:
    """Run all 3 BP-D-DEL checks + rollback sentinel; return aggregate report."""
    metadata = parse_data_attributes(html_content)

    verdicts: list[CheckVerdict] = []

    # Rollback sentinel takes precedence if present.
    sentinel = check_rollback_sentinel(metadata)
    if sentinel is not None:
        verdicts.append(sentinel)

    verdicts.append(check_bp_d_del_1(metadata, html_content))
    verdicts.append(check_bp_d_del_2(metadata, html_content))
    verdicts.append(check_bp_d_del_4(metadata, html_content, reviewer_floor))

    # Determine overall ok:
    # - Any HIGH FAIL → not ok
    # - In strict mode, MED FAIL or WARN → not ok
    ok = True
    for v in verdicts:
        if v.status == "FAIL":
            ok = False
            break
        if strict and v.status == "WARN" and v.severity in ("HIGH", "MED"):
            ok = False
            break

    # Build report
    lines = [
        f"# Authority-chain pre-landing check report",
        f"landing_class: {landing_class}",
        f"strict: {strict}",
        f"reviewer_floor: {reviewer_floor}",
        f"overall_ok: {ok}",
        f"",
        f"# Parsed metadata (subset of data-* attributes)",
    ]
    for k in ("authored-by", "promoted-by", "tt", "tt-prior", "status",
              "prior-constraint-message-id", "cosign-message-id",
              "operator-named-cosign", "rolled-back-at"):
        if k in metadata:
            lines.append(f"  {k}: {metadata[k]}")
    lines.append("")
    lines.append("# Verdicts")
    for v in verdicts:
        lines.append(f"  [{v.status}] {v.bp_code} ({v.severity}): {v.reason}")
        if v.matched_tokens:
            lines.append(f"    matched_tokens: {v.matched_tokens}")
        if v.recommendation:
            lines.append(f"    recommendation: {v.recommendation}")
    report = "\n".join(lines)

    return AuthorityChainReport(
        ok=ok,
        landing_class=landing_class,
        verdicts=verdicts,
        parsed_metadata=metadata,
        report=report,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-landing check for BP-D-DEL-* authority-chain anti-patterns.",
    )
    parser.add_argument("--file", help="Path to candidate landing HTML.")
    parser.add_argument("--strict", action="store_true",
                        help="Treat MED-severity WARN as FAIL.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-check PASS lines.")
    parser.add_argument("--landing-class", default="status-promotion-class",
                        help="Landing class for advisory routing.")
    parser.add_argument("--reviewer-mesh-floor", type=int, default=2,
                        help="Minimum independent reviewer count for BP-D-DEL-4.")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON-formatted report on stdout.")
    args = parser.parse_args(argv)

    if args.file:
        path = Path(args.file)
        if not path.exists():
            sys.stderr.write(f"ERROR: file not found: {path}\n")
            return 2
        html_content = path.read_text(encoding="utf-8", errors="replace")
    else:
        if sys.stdin.isatty():
            sys.stderr.write(
                "ERROR: no --file specified and stdin is a TTY. "
                "Pipe HTML content OR pass --file <path>.\n"
            )
            return 2
        html_content = sys.stdin.read()

    report = check_authority_chain(
        html_content,
        landing_class=args.landing_class,
        strict=args.strict,
        reviewer_floor=args.reviewer_mesh_floor,
    )

    if args.json:
        out = {
            "ok": report.ok,
            "landing_class": report.landing_class,
            "verdicts": [dataclasses.asdict(v) for v in report.verdicts],
            "parsed_metadata": report.parsed_metadata,
        }
        sys.stdout.write(json.dumps(out, indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        if not args.quiet or not report.ok:
            sys.stderr.write(report.report)
            sys.stderr.write("\n")

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
