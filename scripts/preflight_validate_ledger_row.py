"""preflight_validate_ledger_row.py — Anti-hallucination PRE-EMISSION cite guard.

OPERATOR DIRECTIVE 2026-05-15 (AEP-V11-AEP-MEGA-WAVE-ALL-METRICS-TO-100):
Prevent fabricated cites at EMISSION time, not just detect post-hoc. This is the
forge complement to the F6 post-hoc audit (falsifier_6_cross_agent_cites.py) —
agents call THIS script BEFORE writing a ledger row, and the row is REJECTED if
any cite fails canonical validation. Path to 100% full-denominator recall.

THE PROBLEM IT SOLVES:
  Sibling-78 + F6 audit detect fabricated cross-agent cites POST-HOC. By then,
  the bad row is on disk and either (a) gets recall-counted via false-positive
  soft-match (adversary.lamport-55 tier-2 attack: 43/43 hits status=fabricated)
  or (b) requires a corrective row + scribe lesson. The pre-emission guard
  CLOSES the door before the bad cite is ever written: emit-time rejection >
  detect-time recovery.

PROTOCOL:
  1. Agent constructs a candidate ledger row dict in memory.
  2. Agent serializes the row to JSON and pipes to:
       python preflight_validate_ledger_row.py < candidate.json
  3. This script validates every entry in `cites` and `lag_influenced_by`
     that matches the canonical-vec_id shape (ledger::<agent>::lamport-<N>::<slug>
     or ledger::<agent>::lamport-null-<hex>::<slug>).
  4. Non-vec_id cites (pattern:X, doctrine:X, lesson:X, commit:X) pass through
     unchecked — they are not ledger references and not in the F6 attack surface.
  5. EXIT 0 + stamped-row-on-stdout if every vec_id cite is `verified`.
  6. EXIT 1 + stderr report if ANY vec_id cite is `fabricated`/`ambiguous`/
     `malformed`. The row IS NOT WRITTEN.

USAGE — CLI:
  cat candidate_row.json | python preflight_validate_ledger_row.py
  echo $? # 0 = safe to append; 1 = REJECT, fix cites first

  Optional flags:
    --ledger-root <path>       (default: .claude/agents/_ledgers)
    --allow-non-canonical-agents  bypass CANONICAL_10 allowlist check
    --quiet                    suppress per-cite OK lines (still emits errors)

USAGE — PROGRAMMATIC (via validate_my_cites helper):
  from preflight_validate_ledger_row import validate_my_cites
  result = validate_my_cites(my_candidate_row_dict)
  if not result.ok:
      raise RuntimeError(f"REJECTED at pre-emission: {result.report}")
  # else: append result.stamped_row to your ledger

INTEGRATION RECOMMENDATION:
  Wire as a PreToolUse hook on Write/Edit/MultiEdit when the target path
  matches `.claude/agents/_ledgers/<agent>.jsonl`. The hook reads the
  candidate row from the tool call's content, invokes this script, and
  blocks the write on exit-1.

Truth tag: STRONGLY PLAUSIBLE (forge.lamport-215 2026-05-15; demonstrated via
fabricated-cite reject test against current corpus).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import Iterable

# Single-writer discipline: delegate to the F6 validator so the pre-emission
# guard and the post-hoc audit agree byte-for-byte (sibling-78 invariant).
# Both modules live in the same scripts/ directory; add it to sys.path so
# `import` works whether called from repo-root or scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from falsifier_6_cross_agent_cites import (  # noqa: E402
    CANONICAL_VEC_ID_RE,
    CANONICAL_10,
    validate_cite_against_ledger,
)
from lamport_null_fallback import (  # noqa: E402
    compute_null_lamport_token,
)


# Match the broader vec_id shape — both numeric (lamport-N) and null-fallback
# (lamport-null-HEX). The strict per-token regexes live in F6 module; we
# delegate the strict check there. Here we only need a "looks like a vec_id"
# discriminator to separate canonical cites from prose tokens like
# "pattern:single-writer" or "doctrine:50-epistemic-hygiene-meta-law".
_VEC_ID_LOOKS_LIKE = re.compile(r"^ledger::[a-z\-]+::lamport-")


CITE_FIELDS = ("cites", "lag_influenced_by")


@dataclasses.dataclass
class CiteVerdict:
    """One cite's pre-emission verdict."""
    field: str
    index: int
    cite: str
    kind: str  # 'vec_id' | 'pattern' | 'doctrine' | 'lesson' | 'commit' | 'other'
    status: str  # 'verified' | 'fabricated' | 'ambiguous' | 'malformed' | 'skipped'
    reason: str

    def is_rejection(self) -> bool:
        return self.status in ("fabricated", "ambiguous", "malformed")


@dataclasses.dataclass
class PreflightResult:
    """Aggregate verdict for a candidate ledger row."""
    ok: bool
    n_vec_id_cites: int
    n_verified: int
    n_fabricated: int
    n_ambiguous: int
    n_malformed: int
    n_skipped_non_vec_id: int
    verdicts: list[CiteVerdict]
    stamped_row: dict | None  # only populated when ok=True
    # When auto_fix=True, populated with {field, index, original, suggested}
    # entries for each fabricated lamport-null-HEX cite the script could
    # resolve to a canonical vec_id via session_id-slug matching.
    auto_fix_suggestions: list[dict] = dataclasses.field(default_factory=list)

    @property
    def report(self) -> str:
        """Human-readable failure summary; empty when ok=True."""
        if self.ok:
            return ""
        lines = []
        lines.append(
            f"PREFLIGHT REJECT: {self.n_fabricated} fabricated, "
            f"{self.n_ambiguous} ambiguous, {self.n_malformed} malformed "
            f"(out of {self.n_vec_id_cites} vec_id cites; "
            f"{self.n_skipped_non_vec_id} prose tokens skipped)."
        )
        for v in self.verdicts:
            if v.is_rejection():
                lines.append(
                    f"  [{v.status.upper()}] {v.field}[{v.index}] {v.cite!r} "
                    f"-- {v.reason}"
                )
        return "\n".join(lines)


def classify_cite_kind(cite: str) -> str:
    """Return the prose token kind. vec_id is the only one validated."""
    if not isinstance(cite, str):
        return "other"
    if _VEC_ID_LOOKS_LIKE.match(cite):
        return "vec_id"
    for prefix in ("pattern:", "doctrine:", "lesson:", "commit:", "research:"):
        if cite.startswith(prefix):
            return prefix.rstrip(":")
    return "other"


def _iter_cite_strings(row: dict, field: str) -> Iterable[tuple[int, str]]:
    """Yield (index, cite_str) pairs from row[field], coercing non-list/non-str
    to skipped entries the caller can still classify."""
    v = row.get(field)
    if v is None:
        return
    if isinstance(v, list):
        for i, c in enumerate(v):
            if isinstance(c, str):
                yield i, c
            else:
                yield i, repr(c)
    elif isinstance(v, str):
        # Some agents emit advised_by as a single string; tolerate.
        yield 0, v


_VEC_ID_PARTS_RE = re.compile(
    r"^ledger::([a-z\-]+)::(lamport-(?:null-[0-9a-f]{12,32}|[1-9][0-9]*))::([A-Za-z0-9\-]+)$"
)


def _suggest_canonical_for_fabricated(
    fabricated_cite: str, ledger_root: Path
) -> str | None:
    """Auto-fix helper: when `fabricated_cite` is a `lamport-null-HEX` cite whose
    slug-suffix matches exactly one row in the cited agent's ledger by session_id
    OR by an invocation-derived slug, return the canonical corrected vec_id.

    Returns None when no unambiguous correction can be made (slug missing,
    multiple matches, or numeric-lamport variant where slug-to-row mapping
    is ambiguous).

    Algorithm:
      1. Parse the fabricated vec_id into (agent, lamport_token, slug).
      2. Only act on `lamport-null-HEX` shape; numeric `lamport-N` cites
         are agent-counter-owned and not auto-fixable here.
      3. Read .claude/agents/_ledgers/<agent>.jsonl.
      4. Find rows whose session_id == slug OR whose session_id contains slug
         as a substring. If exactly one match -> compute the canonical token
         via compute_null_lamport_token(row) and emit the corrected vec_id.
    """
    m = _VEC_ID_PARTS_RE.match(fabricated_cite)
    if not m:
        return None
    agent, lamport_token, slug = m.group(1), m.group(2), m.group(3)
    if not lamport_token.startswith("lamport-null-"):
        return None
    if agent not in CANONICAL_10:
        return None
    ledger_path = ledger_root / f"{agent}.jsonl"
    if not ledger_path.exists():
        return None
    try:
        text = ledger_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None
    matches: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        session_id = row.get("session_id", "")
        if not isinstance(session_id, str):
            continue
        # Exact-match preferred; substring match accepted only when exact yields none.
        if session_id == slug:
            matches.append(row)
    if not matches:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            session_id = row.get("session_id", "")
            if isinstance(session_id, str) and slug in session_id:
                matches.append(row)
    if len(matches) != 1:
        return None
    matched_row = matches[0]
    lc = matched_row.get("lamport_counter")
    # Identity-token resolution rules (precedence):
    #   1. numeric int lamport_counter -> canonical "lamport-<int>"
    #   2. string lamport_counter starting with "lamport-" -> emitter declared
    #      its own token (the 14 hash-divergent rows live here); use it verbatim
    #   3. None lamport_counter -> recompute BLAKE2b via compute_null_lamport_token
    if isinstance(lc, int) and lc > 0:
        return f"ledger::{agent}::lamport-{lc}::{matched_row.get('session_id', slug)}"
    if isinstance(lc, str) and lc.startswith("lamport-"):
        return f"ledger::{agent}::{lc}::{matched_row.get('session_id', slug)}"
    if lc is None:
        try:
            canonical_token = compute_null_lamport_token(matched_row)
        except (TypeError, ValueError):
            return None
        return f"ledger::{agent}::{canonical_token}::{matched_row.get('session_id', slug)}"
    return None


def validate_my_cites(
    candidate_row: dict,
    *,
    ledger_root: Path | None = None,
    allow_non_canonical_agents: bool = False,
    auto_fix: bool = False,
) -> PreflightResult:
    """Agent-side helper: validate every vec_id cite in `candidate_row`.

    Returns PreflightResult. Caller checks `.ok` and either appends
    `.stamped_row` to the ledger (ok=True) or surfaces `.report` (ok=False).

    The stamped row adds field `preflight_validated: True` when every vec_id
    cite is `verified`. NO mutation of the original row beyond stamp-on-pass.
    """
    if ledger_root is None:
        ledger_root = Path(".claude/agents/_ledgers")

    verdicts: list[CiteVerdict] = []
    n_vec = n_ver = n_fab = n_amb = n_mal = n_skip = 0

    for field in CITE_FIELDS:
        for idx, cite in _iter_cite_strings(candidate_row, field):
            kind = classify_cite_kind(cite)
            if kind != "vec_id":
                n_skip += 1
                verdicts.append(CiteVerdict(
                    field=field, index=idx, cite=cite, kind=kind,
                    status="skipped",
                    reason=f"non-vec_id token ({kind}); not validated against ledger",
                ))
                continue
            n_vec += 1
            # CANONICAL_10 agent allowlist gate
            m = CANONICAL_VEC_ID_RE.search(cite)
            if not m:
                n_mal += 1
                verdicts.append(CiteVerdict(
                    field=field, index=idx, cite=cite, kind=kind,
                    status="malformed",
                    reason="vec_id shape lacks slug suffix or has invalid chars",
                ))
                continue
            agent_name = m.group(1)
            if not allow_non_canonical_agents and agent_name not in CANONICAL_10:
                n_mal += 1
                verdicts.append(CiteVerdict(
                    field=field, index=idx, cite=cite, kind=kind,
                    status="malformed",
                    reason=(f"cited agent {agent_name!r} not in CANONICAL_10 "
                            f"(closed-set allowlist)"),
                ))
                continue
            v = validate_cite_against_ledger(cite, ledger_root)
            status = v.get("status", "malformed")
            reason = v.get("reason", "(no reason supplied)")
            verdicts.append(CiteVerdict(
                field=field, index=idx, cite=cite, kind=kind,
                status=status, reason=reason,
            ))
            if status == "verified":
                n_ver += 1
            elif status == "fabricated":
                n_fab += 1
            elif status == "ambiguous":
                n_amb += 1
            else:
                n_mal += 1

    ok = (n_fab == 0 and n_amb == 0 and n_mal == 0)
    suggestions: list[dict] = []
    if auto_fix:
        for v in verdicts:
            if v.status != "fabricated":
                continue
            suggested = _suggest_canonical_for_fabricated(v.cite, ledger_root)
            if suggested:
                suggestions.append({
                    "field": v.field,
                    "index": v.index,
                    "original": v.cite,
                    "suggested": suggested,
                })
    stamped = None
    if ok:
        stamped = dict(candidate_row)
        stamped["preflight_validated"] = True
    return PreflightResult(
        ok=ok,
        n_vec_id_cites=n_vec,
        n_verified=n_ver,
        n_fabricated=n_fab,
        n_ambiguous=n_amb,
        n_malformed=n_mal,
        n_skipped_non_vec_id=n_skip,
        verdicts=verdicts,
        stamped_row=stamped,
        auto_fix_suggestions=suggestions,
    )


def _merge_operational_evidence_fields(
    row: dict, acts_on: list[str] | None, predecessor_primary: str | None,
) -> dict:
    """§56 D1/D2 emission helper — additive only.

    Per doctrine/_proposals/sec56-d1-acts-on-schema-2026-05-17.html and
    sec56-d2-predecessor-primary-schema-2026-05-17.html: merge the two
    optional operational-evidence fields onto the candidate row before
    the row is validated. Empty/None values are NOT emitted (the field
    remains absent rather than null) per schema-additive discipline.

    Returns a NEW dict; does not mutate the caller's row.
    """
    out = dict(row)
    if acts_on:
        out["acts_on"] = list(acts_on)
    if predecessor_primary:
        out["predecessor_primary"] = predecessor_primary
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--allow-non-canonical-agents", action="store_true",
                    help="bypass CANONICAL_10 allowlist (use only for "
                         "experimental cross-cascade integrations)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress per-cite OK lines on stderr")
    ap.add_argument(
        "--acts-on", default=None,
        help=(
            "§56-D1: comma-separated list of warn_ids the candidate row "
            "acts on. Each warn_id is one of: "
            "<agent>::lamport-N::wave-XXX | lesson:sibling-N | doctrine:NN-slug. "
            "When supplied, merged onto the candidate row as `acts_on: [...]` "
            "BEFORE preflight validation. Default: not emitted. "
            "Schema-additive only per "
            "doctrine/_proposals/sec56-d1-acts-on-schema-2026-05-17.html."
        ),
    )
    ap.add_argument(
        "--predecessor-primary", default=None,
        help=(
            "§56-D2: single canonical citation naming the proximate "
            "upstream cause of this row. One of: "
            "<agent>::lamport-N::<slug> | lesson:sibling-N | doctrine:NN-slug. "
            "When supplied, merged onto the candidate row as "
            "`predecessor_primary: '<vec_id>'` BEFORE preflight validation. "
            "Default: not emitted. Schema-additive only per "
            "doctrine/_proposals/sec56-d2-predecessor-primary-schema-2026-05-17.html."
        ),
    )
    ap.add_argument("--auto-fix", action="store_true",
                    help="for each fabricated lamport-null-HEX cite, attempt "
                         "to resolve the canonical token via session_id-slug "
                         "match against the cited agent's ledger; emit "
                         "AUTO-FIX SUGGESTION lines on stderr. When every "
                         "fabricated cite has an unambiguous suggestion, "
                         "downgrade the verdict from REJECT (exit 1) to "
                         "WARN (exit 0) and stamp the row with "
                         "`auto_fix_suggestions`. The caller is expected to "
                         "apply the suggestions and re-run preflight before "
                         "appending.")
    ap.add_argument(
        "--require-operational-evidence", action="store_true",
        help=(
            "Wave-008 M1 closure for BP-007-SCHEMA-WITHOUT-ENFORCEMENT-1: "
            "REJECT the row if `acts_on` OR `predecessor_primary` is missing/"
            "empty. Flag is OPT-IN at flag-level so existing scripts that do "
            "not pass this flag remain compatible. Forge sets this flag on "
            "its own ledger-append going forward per adversary Wave-007 "
            "PROCEED-WAVE-008-WITH-3-MITIGATIONS recommendation."
        ),
    )
    args = ap.parse_args()

    try:
        raw = sys.stdin.read()
    except KeyboardInterrupt:
        print("PREFLIGHT REJECT: stdin read interrupted", file=sys.stderr)
        return 1
    raw = raw.strip()
    if not raw:
        print(
            "PREFLIGHT REJECT: empty stdin (expected one JSON dict)",
            file=sys.stderr,
        )
        return 1
    try:
        row = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"PREFLIGHT REJECT: stdin is not valid JSON ({e})",
              file=sys.stderr)
        return 1
    if not isinstance(row, dict):
        print(
            f"PREFLIGHT REJECT: expected JSON dict; got {type(row).__name__}",
            file=sys.stderr,
        )
        return 1

    # §56 D1/D2 schema-additive merge — applied BEFORE cite validation so
    # the merged fields (a) appear in the stamped row on PASS and (b)
    # become visible to any future hook that validates operational-evidence
    # field presence. Empty/missing flags leave the row unchanged.
    acts_on_list: list[str] | None = None
    if args.acts_on:
        acts_on_list = [w.strip() for w in args.acts_on.split(",") if w.strip()]
    row = _merge_operational_evidence_fields(
        row, acts_on_list, args.predecessor_primary,
    )

    # Wave-008 M1: REJECT if --require-operational-evidence is set AND either
    # acts_on or predecessor_primary is missing/empty. Closes
    # BP-007-SCHEMA-WITHOUT-ENFORCEMENT-1 (adversary Wave-007 mitigation M1).
    # Field-presence rule mirrors d_framework_adoption._is_field_adopted:
    # missing key, None, empty string, empty list, empty dict all count as
    # NOT-ADOPTED. This keeps the preflight gate and the warden adoption
    # measurement byte-for-byte consistent (single-writer discipline).
    if args.require_operational_evidence:
        missing: list[str] = []
        for field in ("acts_on", "predecessor_primary"):
            v = row.get(field)
            if v is None:
                missing.append(field)
                continue
            if isinstance(v, str) and v.strip() == "":
                missing.append(field)
                continue
            if isinstance(v, (list, dict, tuple, set)) and len(v) == 0:
                missing.append(field)
                continue
        if missing:
            print(
                f"PREFLIGHT REJECT: --require-operational-evidence set but "
                f"the following field(s) are missing/empty on the candidate "
                f"row: {', '.join(missing)}. Closes "
                f"BP-007-SCHEMA-WITHOUT-ENFORCEMENT-1; either populate the "
                f"field(s) via --acts-on / --predecessor-primary CLI args "
                f"OR by emitting them inline in the JSON candidate row.",
                file=sys.stderr,
            )
            return 1

    result = validate_my_cites(
        row, ledger_root=args.ledger_root,
        allow_non_canonical_agents=args.allow_non_canonical_agents,
        auto_fix=args.auto_fix,
    )

    if not args.quiet:
        for v in result.verdicts:
            if v.status == "verified":
                print(f"  [VERIFIED] {v.field}[{v.index}] {v.cite}",
                      file=sys.stderr)

    if not result.ok:
        print(result.report, file=sys.stderr)
        if args.auto_fix and result.auto_fix_suggestions:
            print(
                f"\nAUTO-FIX SUGGESTION: {len(result.auto_fix_suggestions)} "
                f"of {result.n_fabricated} fabricated cites have a canonical "
                f"correction.",
                file=sys.stderr,
            )
            for s in result.auto_fix_suggestions:
                same = (s["original"] == s["suggested"])
                if same:
                    print(
                        f"  AUTO-FIX SUGGESTION: {s['field']}[{s['index']}]\n"
                        f"    original:  {s['original']}\n"
                        f"    suggested: {s['suggested']}\n"
                        f"    NOTE: original == suggested -- the cite IS to a "
                        f"real row, but F6 currently classifies it as "
                        f"fabricated because the cited row has a string-typed "
                        f"`lamport_counter` field (one of the 14 hash-divergent "
                        f"rows surfaced by forge.lamport-215). This is a known "
                        f"F6 classification gap, not an agent-emission defect.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"  AUTO-FIX SUGGESTION: {s['field']}[{s['index']}]\n"
                        f"    original:  {s['original']}\n"
                        f"    suggested: {s['suggested']}",
                        file=sys.stderr,
                    )
            # When every fabricated cite has an unambiguous canonical
            # suggestion, downgrade REJECT -> WARN. Caller is expected to
            # apply suggestions and retry preflight before append.
            if (len(result.auto_fix_suggestions) == result.n_fabricated
                    and result.n_ambiguous == 0
                    and result.n_malformed == 0):
                stamped_with_suggestions = dict(row)
                stamped_with_suggestions["auto_fix_suggestions"] = (
                    result.auto_fix_suggestions
                )
                stamped_with_suggestions["preflight_validated"] = False
                stamped_with_suggestions["preflight_status"] = "warn-auto-fix-suggested"
                sys.stdout.write(
                    json.dumps(stamped_with_suggestions, ensure_ascii=False)
                )
                print(
                    "\nPREFLIGHT WARN (auto-fix mode): all fabricated cites "
                    "have canonical suggestions; downgraded REJECT->WARN. "
                    "Apply suggestions and re-run preflight (without "
                    "--auto-fix) before appending.",
                    file=sys.stderr,
                )
                return 0
        return 1

    print(
        f"PREFLIGHT OK: {result.n_verified}/{result.n_vec_id_cites} vec_id cites "
        f"verified; {result.n_skipped_non_vec_id} prose tokens skipped. "
        f"Row stamped preflight_validated=True.",
        file=sys.stderr,
    )
    sys.stdout.write(json.dumps(result.stamped_row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
