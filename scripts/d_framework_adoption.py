"""D-Framework Adoption Measurement (Wave-007 Task 5).

Truth tag: STRONGLY PLAUSIBLE (instrument; baseline-pre-instrumentation expected to be ~0%).

Measures per-agent ledger-row adoption of the D1 `acts_on` and D2 `predecessor_primary`
schema reservations introduced in AEP-AUTONOMOUS-WAVE-007 (pathfinder Task 1, forge
Task 3-4). The script is the **disconfirmer** for adoption: it answers "is forge's
instrumentation actually being used at the row level, or is it stuck in the prompt?"

Disconfirmer thresholds (per Wave-007 spec):
  - GREEN (PASS):    adoption rate >= 80%
  - YELLOW (PARTIAL): 50% <= adoption rate < 80%
  - RED   (FAIL):    adoption rate < 50%

Design discipline:
  - Read-only on every ledger file (sibling-87 append-only-on-ledger-reads check;
    file is opened in 'r' mode, never 'a' / 'w' / 'r+').
  - Schema-additive: this script never writes to ledgers; it only summarizes.
  - Stdlib + argparse only (operator constraint).
  - Empty-string + null-string + missing-key all count as NOT adopted.

CLI:
  python d_framework_adoption.py --agent forge --field both --days 7
  python d_framework_adoption.py --all-agents --field both --days 7
  python d_framework_adoption.py --agent forge --field acts_on --days 1 \\
      --since-utc 2026-05-17T03:00:00Z

Cites:
  - pathfinder Wave-007 task 1 (schema reservation plan)
  - forge Wave-007 task 3-4 (instrumentation impl)
  - doctrine/08-ledger-schema.html (schema warden enforces)
  - sibling-87 race-aware audit (MISSING-CONFIRMED vs NOT-OBSERVED-AT-AUDIT-TIME)
  - sibling-78 preflight discipline (pre-emission validation pattern)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

# Wave-008 M2: canonical shape regexes for strict-validity mode.
# Adversary Wave-007 task-2 spec verbatim:
#   acts_on element shape: <agent>::lamport-<N>::wave-<XXX>
#   predecessor_primary shape: <ledger-vec-id>::<citation>
# The agent allowlist is the canonical 10 (per CANONICAL_AGENTS below).
_AGENTS_RE = "(?:adversary|curator|forge|judge|pathfinder|scout|scribe|strategist|visual-judge|warden)"
_ACTS_ON_ELEMENT_RE = re.compile(
    rf"^{_AGENTS_RE}::lamport-(?:null-[0-9a-f]{{12,32}}|[1-9][0-9]*)::wave-[A-Za-z0-9\-]+$"
)
# predecessor_primary is broader: it accepts any string with the two-segment
# vec-id-style `<ledger-vec-id>::<citation>` shape, BUT placeholder strings
# (TODO, empty, whitespace) FAIL. The vec-id-side must look like one of:
#   adversary::lamport-N::<slug>
#   doctrine:NN-slug
#   lesson:sibling-N
#   proposal:doctrine/_proposals/<slug>.html
#   doctrine/_proposals/<slug>.html
#   <path>.html
# The ::<citation> tail is mandatory (the M2 spec calls it "vec-id::citation").
_PREDECESSOR_PRIMARY_RE = re.compile(
    r"^(?:"
    rf"{_AGENTS_RE}::lamport-(?:null-[0-9a-f]{{12,32}}|[1-9][0-9]*)::[A-Za-z0-9\-]+"
    r"|doctrine:[0-9]+-[A-Za-z0-9\-]+"
    r"|lesson:sibling-[0-9]+"
    r"|(?:proposal:)?doctrine/_proposals/[A-Za-z0-9_\-]+\.html"
    r"|[A-Za-z0-9_./\-]+\.html"
    r")"
    r"::"  # mandatory separator
    r".+"  # non-empty citation tail
    r"$"
)
_PLACEHOLDER_TOKENS = frozenset({
    "TODO", "todo", "TBD", "tbd", "FIXME", "fixme", "XXX",
    "PLACEHOLDER", "placeholder", "N/A", "n/a",
})

# --- Constants -----------------------------------------------------------

CANONICAL_AGENTS = (
    "adversary",
    "curator",
    "forge",
    "judge",
    "pathfinder",
    "scout",
    "scribe",
    "strategist",
    "visual-judge",
    "warden",
)

D_FIELDS = ("acts_on", "predecessor_primary")

# Default ledger root. Resolved at runtime relative to repo root.
# repo root = parents[5]: scripts/ -> aep/ -> publish-ready/ -> v11-aep/ -> projects/ -> aepkit/
_DEFAULT_LEDGER_ROOT = Path(__file__).resolve().parents[5] / ".claude" / "agents" / "_ledgers"


# --- Helpers --------------------------------------------------------------

def _is_field_adopted(row: dict, field: str) -> bool:
    """A field is adopted iff it is present AND non-empty AND non-null.

    Empty string, empty list, empty dict, and None all count as NOT adopted.
    """
    if field not in row:
        return False
    val = row[field]
    if val is None:
        return False
    # Treat empty containers and empty/whitespace strings as not-adopted.
    if isinstance(val, str):
        return val.strip() != ""
    if isinstance(val, (list, dict, tuple, set)):
        return len(val) > 0
    # Any other truthy value (e.g. number, bool True) counts as adopted.
    return bool(val)


def _is_field_strictly_valid(row: dict, field: str) -> bool:
    """Wave-008 M2 value-validity check (closes BP-007-MEASUREMENT-VALIDATES-
    SHAPE-NOT-VALUE-1).

    A field counts as STRICTLY adopted only when the VALUE is well-formed,
    not merely present. The adversary Wave-007 mitigation spec:

      - `acts_on`: a list AND non-empty AND each element matches the
        canonical regex `<agent>::lamport-<N>::wave-<XXX>`.
      - `predecessor_primary`: a string AND non-empty AND not a placeholder
        token (TODO/TBD/FIXME/etc) AND matches the broader vec-id-style
        `<ledger-vec-id>::<citation>` shape.

    Returns False for any malformed/placeholder/empty value; returns True
    only when every constituent passes its shape check. The lax
    `_is_field_adopted` is preserved unchanged for backward-compat.
    """
    if not _is_field_adopted(row, field):
        return False
    val = row[field]
    if field == "acts_on":
        if not isinstance(val, list) or len(val) == 0:
            return False
        for elem in val:
            if not isinstance(elem, str):
                return False
            if not _ACTS_ON_ELEMENT_RE.match(elem):
                return False
        return True
    if field == "predecessor_primary":
        if not isinstance(val, str):
            return False
        if val.strip() in _PLACEHOLDER_TOKENS:
            return False
        if not _PREDECESSOR_PRIMARY_RE.match(val.strip()):
            return False
        return True
    # Unknown field: fall back to the lax check.
    return True


def _parse_row_date(row: dict) -> datetime | None:
    """Parse a ledger row's `date` field into an aware UTC datetime.

    Falls back to None if the field is missing or unparseable; such rows are
    treated as outside any --days window.
    """
    raw = row.get("date")
    if not raw or not isinstance(raw, str):
        return None
    # Accept date-only (YYYY-MM-DD) and full ISO 8601 with optional Z.
    raw = raw.strip()
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_since_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError as e:
        raise SystemExit(f"--since-utc: cannot parse {raw!r}: {e}")


def _iter_ledger_rows(path: Path) -> Iterable[dict]:
    """Yield each JSON-decodable row from a ledger file.

    Skips the `_meta` header row and any malformed line (does not crash).
    Honors BOM. Read-only.
    """
    if not path.exists():
        return
    # 'utf-8-sig' strips a leading BOM if present; otherwise reads as UTF-8.
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            # Skip the ledger header row.
            if "_meta" in row and "_agent" in row:
                continue
            yield row


def _in_window(
    row: dict,
    *,
    cutoff: datetime | None,
    since: datetime | None,
) -> bool:
    """True iff the row's date is within [since, now] AND >= cutoff.

    Rows with unparseable dates are excluded from any windowed measurement
    so we never silently count rows we cannot place in time.
    """
    if cutoff is None and since is None:
        return True
    row_dt = _parse_row_date(row)
    if row_dt is None:
        return False
    if cutoff is not None and row_dt < cutoff:
        return False
    if since is not None and row_dt < since:
        return False
    return True


# --- Core measurement -----------------------------------------------------

def measure_agent(
    agent: str,
    *,
    days: int,
    since: datetime | None,
    ledger_root: Path,
    now: datetime | None = None,
    strict: bool = False,
) -> dict:
    """Compute adoption metrics for one agent over a time window.

    Returns:
      {
        "agent": str,
        "ledger_path": str,
        "window_days": int,
        "cutoff_utc": str | None,
        "total_rows_in_window": int,
        "rows_with_acts_on": int,
        "rows_with_predecessor_primary": int,
        "adoption_rate_acts_on_pct": float,
        "adoption_rate_predecessor_primary_pct": float,
        "ledger_exists": bool,
      }
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff: datetime | None
    if days <= 0:
        cutoff = None
    else:
        cutoff = now - timedelta(days=days)

    ledger_path = ledger_root / f"{agent}.jsonl"
    total = 0
    with_acts_on = 0
    with_predecessor = 0
    ledger_exists = ledger_path.exists()

    # Wave-008 M2: when strict=True, the adoption count uses the value-validity
    # gate (`_is_field_strictly_valid`) rather than the lax presence-only gate.
    # Closes BP-007-MEASUREMENT-VALIDATES-SHAPE-NOT-VALUE-1. Single-writer
    # discipline: both gates are stricter-or-equal supersets, so a row that
    # passes strict ALWAYS passes lax (never the reverse).
    _check = _is_field_strictly_valid if strict else _is_field_adopted
    for row in _iter_ledger_rows(ledger_path):
        if not _in_window(row, cutoff=cutoff, since=since):
            continue
        total += 1
        if _check(row, "acts_on"):
            with_acts_on += 1
        if _check(row, "predecessor_primary"):
            with_predecessor += 1

    def _rate(n: int) -> float:
        return (n / total * 100.0) if total > 0 else 0.0

    return {
        "agent": agent,
        "ledger_path": str(ledger_path),
        "ledger_exists": ledger_exists,
        "window_days": days,
        "cutoff_utc": cutoff.isoformat() if cutoff else None,
        "since_utc": since.isoformat() if since else None,
        "strict_validity": strict,
        "total_rows_in_window": total,
        "rows_with_acts_on": with_acts_on,
        "rows_with_predecessor_primary": with_predecessor,
        "adoption_rate_acts_on_pct": _rate(with_acts_on),
        "adoption_rate_predecessor_primary_pct": _rate(with_predecessor),
    }


def classify_rate(rate_pct: float) -> tuple[str, str]:
    """Return (color, verdict) for a percent rate."""
    if rate_pct >= 80.0:
        return ("GREEN", "PASS")
    if rate_pct >= 50.0:
        return ("YELLOW", "PARTIAL")
    return ("RED", "FAIL")


def aggregate_verdict(
    *,
    field: str,
    metrics: dict,
) -> tuple[str, str, float]:
    """Pick the relevant rate(s) for the requested --field setting.

    For field='both' the verdict is the WORST of the two field verdicts
    (so a partial in one field downgrades a pass in the other).
    """
    rate_acts_on = metrics["adoption_rate_acts_on_pct"]
    rate_pred = metrics["adoption_rate_predecessor_primary_pct"]
    if field == "acts_on":
        c, v = classify_rate(rate_acts_on)
        return (c, v, rate_acts_on)
    if field == "predecessor_primary":
        c, v = classify_rate(rate_pred)
        return (c, v, rate_pred)
    # both: worst-of
    c1, v1 = classify_rate(rate_acts_on)
    c2, v2 = classify_rate(rate_pred)
    order = {"GREEN": 2, "YELLOW": 1, "RED": 0}
    if order[c1] <= order[c2]:
        worst_color, worst_verdict, worst_rate = c1, v1, rate_acts_on
    else:
        worst_color, worst_verdict, worst_rate = c2, v2, rate_pred
    return (worst_color, worst_verdict, worst_rate)


# --- Rendering ------------------------------------------------------------

def _render_single(agent_metrics: dict, field: str) -> str:
    m = agent_metrics
    color, verdict, rate = aggregate_verdict(field=field, metrics=m)
    lines = []
    lines.append(f"D-Framework Adoption — agent: {m['agent']}")
    lines.append(f"  Ledger:                       {m['ledger_path']}")
    lines.append(f"  Ledger exists:                {m['ledger_exists']}")
    lines.append(f"  Window (days):                {m['window_days']}")
    if m["cutoff_utc"]:
        lines.append(f"  Cutoff (UTC):                 {m['cutoff_utc']}")
    if m["since_utc"]:
        lines.append(f"  Since (UTC):                  {m['since_utc']}")
    lines.append(f"  Total rows in window:         {m['total_rows_in_window']}")
    lines.append(f"  Rows with acts_on:            {m['rows_with_acts_on']}")
    lines.append(f"  Rows with predecessor_primary: {m['rows_with_predecessor_primary']}")
    lines.append(
        f"  Adoption rate acts_on:        "
        f"{m['adoption_rate_acts_on_pct']:.1f}%"
    )
    lines.append(
        f"  Adoption rate predecessor_primary: "
        f"{m['adoption_rate_predecessor_primary_pct']:.1f}%"
    )
    lines.append(f"  Field tested:                 {field}")
    lines.append(f"  Color:                        {color}")
    lines.append(f"  Verdict:                      {verdict} (rate={rate:.1f}%)")
    lines.append("  Thresholds:                   GREEN >=80% | YELLOW 50-79% | RED <50%")
    return "\n".join(lines)


def _render_all_agents_table(rows: list[dict], field: str) -> str:
    lines = []
    lines.append(f"D-Framework Adoption — all 10 canonical agents (field={field})")
    lines.append("Thresholds: GREEN >=80% | YELLOW 50-79% | RED <50%")
    lines.append("")
    header = (
        f"{'agent':<14}{'rows':>6}{'acts_on%':>11}"
        f"{'pred%':>9}{'color':>9}{'verdict':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for m in rows:
        color, verdict, _ = aggregate_verdict(field=field, metrics=m)
        lines.append(
            f"{m['agent']:<14}"
            f"{m['total_rows_in_window']:>6}"
            f"{m['adoption_rate_acts_on_pct']:>10.1f}%"
            f"{m['adoption_rate_predecessor_primary_pct']:>8.1f}%"
            f"{color:>9}"
            f"{verdict:>10}"
        )
    return "\n".join(lines)


# --- CLI ------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="d_framework_adoption",
        description=(
            "Measure D-framework (acts_on / predecessor_primary) adoption rate "
            "across one or all agent ledgers. Wave-007 Task 5."
        ),
    )
    p.add_argument(
        "--agent",
        default=None,
        help="Agent name (e.g. forge, judge, scribe). Mutually exclusive with --all-agents.",
    )
    p.add_argument(
        "--all-agents",
        action="store_true",
        help="Run across all 10 canonical agents and emit a comparison table.",
    )
    p.add_argument(
        "--field",
        choices=("acts_on", "predecessor_primary", "both"),
        default="both",
        help="Which D-field to evaluate. 'both' uses worst-of verdict.",
    )
    p.add_argument(
        "--days",
        type=int,
        default=7,
        help="Window length in days from now. 0 disables the window. Default 7.",
    )
    p.add_argument(
        "--since-utc",
        default=None,
        help="ISO 8601 UTC cutoff (additional lower bound; e.g. 2026-05-17T03:00:00Z).",
    )
    p.add_argument(
        "--ledger-root",
        default=str(_DEFAULT_LEDGER_ROOT),
        help="Override ledger directory (default resolves to repo .claude/agents/_ledgers/).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human-rendered table.",
    )
    p.add_argument(
        "--strict-validity",
        action="store_true",
        help=(
            "Wave-008 M2: enforce value-validity on acts_on and "
            "predecessor_primary. A row counts as adopted only when the "
            "value matches the canonical shape regex (lists for acts_on "
            "with each element matching <agent>::lamport-<N>::wave-<XXX>; "
            "predecessor_primary a non-placeholder string matching "
            "<ledger-vec-id>::<citation>). Closes "
            "BP-007-MEASUREMENT-VALIDATES-SHAPE-NOT-VALUE-1."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.agent and args.all_agents:
        print("error: --agent and --all-agents are mutually exclusive", file=sys.stderr)
        return 2
    if not args.agent and not args.all_agents:
        print("error: pick --agent <name> or --all-agents", file=sys.stderr)
        return 2

    ledger_root = Path(args.ledger_root)
    since = _parse_since_utc(args.since_utc)

    if args.all_agents:
        rows = [
            measure_agent(
                a,
                days=args.days,
                since=since,
                ledger_root=ledger_root,
                strict=args.strict_validity,
            )
            for a in CANONICAL_AGENTS
        ]
        if args.json:
            print(json.dumps({"all_agents": rows, "field": args.field}, indent=2))
        else:
            print(_render_all_agents_table(rows, field=args.field))
        # Exit 0 even if RED — this is a measurement tool, not an enforcement gate.
        return 0

    metrics = measure_agent(
        args.agent,
        days=args.days,
        since=since,
        ledger_root=ledger_root,
        strict=args.strict_validity,
    )
    if args.json:
        print(json.dumps({"single": metrics, "field": args.field}, indent=2))
    else:
        print(_render_single(metrics, field=args.field))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
