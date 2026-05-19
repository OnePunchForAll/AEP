"""chip_completeness_audit.py — Wave-D warden BP-C-CHIP-1+2 burn-down infrastructure.

PURPOSE
-------
Walks the corpus of agent-visible HTML artifacts and surfaces every occurrence of a
truth-tag WORD (PROVEN/RELIABLE, STRONGLY PLAUSIBLE, EXPERIMENTAL, SPECULATIVE
FRONTIER, IMPOSSIBLE/UNSUPPORTED, DANGEROUS/NOT WORTH DOING and their hyphen/space
variants) that is NOT enclosed in a `<span class="tt tt-*">...</span>` chip wrapper.

WHY THIS EXISTS (BP-C-CHIP-1+2 attack family per adversary wave-A/B/C reports)
----------------------------------------------------------------------------
BP-C-CHIP-1: doctrine HTML files use truth-tag words as bare text without wrapping
in `<span class="tt tt-*">` styling. visual-judge sees them as chip-bare and
downgrades the file (REJECT 6.6 chip-dim 4/10 at Wave-B baseline on §66).

BP-C-CHIP-2: edits that wrap SOME instances but miss others, creating partial-chip
regression. The PARTIAL form is harder to spot than full bare-text because grep
"appears wrapped" superficially passes.

Both attack classes occurred across Wave-A/B/C cycles on §66 until forge Wave-C
task-01 finally remediated by adding 14 chip wraps + a new `.tt-gate` CSS class
for promotion-ladder steps (G1/G2/G3/G4/G5). This audit script is the standing
verification harness that future regressions are detected mechanically.

SCOPE (operator task spec)
--------------------------
  - doctrine/**/*.html                        (top-level + aepkg companions)
  - doctrine/lessons/*.aepkg/assets/*.html    (lesson HTML companions; `original.html` is the actual filename)
  - .claude/diana/CONSTITUTION.html           (the agent operator Operator constitution)

A finding is emitted whenever a truth-tag WORD (case-insensitive) appears in a
position where its IMMEDIATE parent token-context is NOT `<span class="tt tt-*">`.

Severity rubric:
  - HIGH : occurrence inside <h1>, <h2>, or <strong> (visual-judge weighs these heaviest)
  - MED  : everywhere else

The audit DOES NOT mutate any artifact. It produces a JSONL file at
`.claude/diana/chip-completeness-findings.jsonl` with one row per finding plus a
trailing `_summary` row. Each finding row schema:
  {
    "file_path": str,              # repo-relative path
    "line_no": int,                # 1-indexed line where the word appears
    "surrounding_text": str,       # ≤200-char snippet, word in context
    "word": str,                   # the canonical truth-tag word found (e.g. "PROVEN/RELIABLE")
    "matched_form": str,           # the exact case+spacing form that matched
    "severity": "HIGH"|"MED",
    "in_element": str|null,        # h1|h2|h3|strong|p|code|... best-effort
    "is_within_tt_span": bool,     # always false in findings; true cases skipped
    "is_partial_chip": bool,       # true if surrounded by `<span class="tt">` (no -tier suffix)
  }

CLI
---
  python chip_completeness_audit.py                  # audit whole corpus, default out
  python chip_completeness_audit.py --file <path>    # audit single file
  python chip_completeness_audit.py --out <path>     # custom output
  python chip_completeness_audit.py --quiet          # suppress per-file progress

EXIT CODES
----------
  0  : audit completed (findings may or may not be > 0; that's the audit OUTCOME, not a failure)
  2  : invalid input (file not found, scope dir missing)

RACE-AWARENESS DISCIPLINE (per sibling-86)
------------------------------------------
This audit is OBSERVED-AT-AUDIT-TIME. A non-zero count on §66 itself does NOT
indicate forge Wave-C remediation failed UNLESS the matched form is the bare-word
form OUTSIDE any wrap. The audit must distinguish:
  - "PROVEN/RELIABLE" appearing inside <span class="tt tt-proven-reliable">  -> NOT a finding (clean)
  - "PROVEN/RELIABLE" appearing inside <span class="tt">                      -> finding, is_partial_chip=true
  - "PROVEN/RELIABLE" appearing as bare text in <h1>                          -> finding, severity=HIGH
The intent is to fail loudly on bare-word regressions and quietly observe
partial-chip (which is BP-C-CHIP-2 territory — wrapped, but tier-less so visual
styling is missing).

CITES (sibling-78 cross-agent citation discipline)
--------------------------------------------------
  ledger::forge::lamport-228::wave-B-combined-A-NEW-3-D-NEW-1-Option-D-2026-05-16
  ledger::adversary::lamport-62::wave-B-task-02-bypass-attacks-on-forge-fixes-2026-05-16
  ledger::visual-judge::lamport-null-wave-B-task-07-visual-judge-rescore-2026-05-16-a3b9d2e7f4c8::2026-05-16-auto-wave-B-task-07
  ledger::judge::lamport-216::wave-C-g1-final-verdict-and-g5-co-sign-eligibility-2026-05-16
  doctrine:66-diana-idle-trigger-autonomous-takeover  (target of remediation)
  doctrine:22-html-native-artifacts                    (chip-styling discipline source)
  lesson:sibling-78                                    (cross-agent vec_id discipline)
  lesson:sibling-86                                    (race-aware OBSERVED vs NOT-OBSERVED)
  lesson:sibling-87                                    (comprehensive-evolution)
  pattern:WARN-N-persistence                           (BP-C-CHIP-1 persisted Wave-A through Wave-C)
  pattern:absence-is-evidence                          (zero HIGH findings on §66 = remediation holds)

Truth tag: STRONGLY PLAUSIBLE (Wave-D infrastructure; promotes to PROVEN/RELIABLE
after N=3 wave audits show ≥0 HIGH and no false negatives).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Iterator


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Repo root (absolute, Windows-native).
REPO_ROOT = Path("C:/Users/example-user/")

# Default output location.
DEFAULT_OUT = REPO_ROOT / ".claude" / "diana" / "chip-completeness-findings.jsonl"

# The 6 canonical truth-tag words plus tolerated visual variants (hyphen-vs-slash,
# hyphen-vs-space). visual-judge accepts ANY of these spellings as "this is a
# truth-tag word"; the chip wrap requirement applies to all of them.
#
# Each entry is (canonical_name, regex_pattern). The pattern uses (?: ... )
# non-capturing alternation so re.findall returns the matched text directly.
# Word-boundary `\b` would break on the `/` separator, so we use explicit
# negative-lookarounds for letter-context on both sides.
_LETTER = r"[A-Za-z]"
_NEG_BEFORE = rf"(?<!{_LETTER})"   # not preceded by a letter
_NEG_AFTER  = rf"(?!{_LETTER})"    # not followed by a letter

TRUTH_TAG_WORDS: list[tuple[str, re.Pattern[str]]] = [
    (
        "PROVEN/RELIABLE",
        re.compile(rf"{_NEG_BEFORE}PROVEN[/\-]RELIABLE{_NEG_AFTER}", re.IGNORECASE),
    ),
    (
        "STRONGLY PLAUSIBLE",
        re.compile(rf"{_NEG_BEFORE}STRONGLY[\s\-]PLAUSIBLE{_NEG_AFTER}", re.IGNORECASE),
    ),
    (
        "EXPERIMENTAL",
        re.compile(rf"{_NEG_BEFORE}EXPERIMENTAL{_NEG_AFTER}", re.IGNORECASE),
    ),
    (
        "SPECULATIVE FRONTIER",
        re.compile(rf"{_NEG_BEFORE}SPECULATIVE[\s\-]FRONTIER{_NEG_AFTER}", re.IGNORECASE),
    ),
    (
        "IMPOSSIBLE/UNSUPPORTED",
        re.compile(rf"{_NEG_BEFORE}IMPOSSIBLE[/\-]UNSUPPORTED{_NEG_AFTER}", re.IGNORECASE),
    ),
    (
        "DANGEROUS/NOT WORTH DOING",
        re.compile(rf"{_NEG_BEFORE}DANGEROUS[/\-]NOT[\s\-]WORTH[\s\-]DOING{_NEG_AFTER}", re.IGNORECASE),
    ),
]

# Tier-suffix span pattern: `<span class="tt tt-something">...</span>`. The
# regex captures the inner text; we treat every word WITHIN such a span as
# "wrapped" (not a finding). Whitespace and other attributes between `class`
# and the value are tolerated.
TT_TIER_SPAN_RE = re.compile(
    r'<span\b[^>]*\bclass\s*=\s*"[^"]*\btt\s+tt-[A-Za-z0-9\-]+[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)

# Bare-tt span (no -tier suffix): `<span class="tt">...</span>`. This is the
# BP-C-CHIP-2 partial-chip case — wrapped but tier-less so visual chip styling
# (color, prefix) is missing.
TT_BARE_SPAN_RE = re.compile(
    r'<span\b[^>]*\bclass\s*=\s*"[^"]*\btt\b(?![ \t]+tt-)[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)

# Tag-tokenizer regex used by _enclosing_element() to walk backwards and
# maintain a tag stack. We don't need a full HTML parser — only the immediate
# open-tag context for severity classification.
ANY_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?>")


# -----------------------------------------------------------------------------
# Data shapes
# -----------------------------------------------------------------------------


@dataclass
class Finding:
    file_path: str
    line_no: int
    surrounding_text: str
    word: str
    matched_form: str
    severity: str
    in_element: str | None
    is_within_tt_span: bool
    is_partial_chip: bool
    # ADDITIVE FIELD (schema-additive-only check): flags findings where chip-wrap
    # is not applicable because the match is inside non-rendered content. Set to
    # True when in_element is `script`, `head`, `meta`, `link`, `title`, or when
    # the walk returned `html`/None (i.e. inside a multi-line tag's attribute
    # value, which cannot be chip-wrapped). Severity is preserved per the
    # operator-defined rubric; consumers may filter for chip-actionable findings
    # via `is_likely_false_positive == False`.
    is_likely_false_positive: bool = False


# -----------------------------------------------------------------------------
# Scope discovery
# -----------------------------------------------------------------------------


def discover_corpus(root: Path | None = None) -> list[Path]:
    """Return all in-scope HTML files (deterministic sort order).

    Scope:
      - root/doctrine/**/*.html  (includes top-level + aepkg companions)
      - root/doctrine/lessons/*.aepkg/assets/*.html
        (NOTE: operator task spec said `source.html`; actual filename is
        `original.html`. We accept *.html under that path to be future-proof.)
      - root/.claude/diana/CONSTITUTION.html
    """
    base = root or REPO_ROOT
    files: list[Path] = []

    doctrine = base / "doctrine"
    if doctrine.exists():
        for p in sorted(doctrine.rglob("*.html")):
            if p.is_file():
                files.append(p)

    # lessons aepkg assets already covered by the rglob above; no separate pass.
    # (Listed in docstring for clarity but the rglob naturally walks them.)

    constitution = base / ".claude" / "diana" / "CONSTITUTION.html"
    if constitution.is_file():
        files.append(constitution)

    return files


# -----------------------------------------------------------------------------
# Audit core
# -----------------------------------------------------------------------------


def _build_masked_text(content: str) -> tuple[str, list[tuple[int, int]]]:
    """Replace all `<span class="tt tt-*">...</span>` ranges with placeholders
    of identical length so finding-detection skips them. Returns the masked
    text AND the list of (start, end) spans that were tier-wrapped (used for
    the is_partial_chip distinction in a separate pass).

    We replace with `\x00` bytes (NUL is rare in HTML) so the regex
    word-boundary still works in the surrounding text.
    """
    masked = list(content)
    tier_spans: list[tuple[int, int]] = []
    for m in TT_TIER_SPAN_RE.finditer(content):
        s, e = m.span()
        tier_spans.append((s, e))
        for i in range(s, e):
            masked[i] = "\x00"
    return "".join(masked), tier_spans


def _detect_partial_chips(content: str) -> list[tuple[int, int]]:
    """Detect `<span class="tt">...</span>` (bare tt, no tier suffix). Returns
    list of (start, end) spans for the OUTER span (incl. tags). Used to set
    is_partial_chip on a finding whose word falls inside such a span."""
    return [m.span() for m in TT_BARE_SPAN_RE.finditer(content)]


def _enclosing_element(content: str, position: int) -> str | None:
    """Best-effort: look backwards from `position` to find the nearest opening
    HTML tag that is still open (no intervening matching closer). Returns
    lowercased tag name or None."""
    # Walk backwards through tag tokens until we find one whose closer is AFTER
    # our position.
    cursor = 0
    stack: list[str] = []
    for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?>", content[:position]):
        slash, tag = m.group(1), m.group(2).lower()
        if slash:
            if stack and stack[-1] == tag:
                stack.pop()
            else:
                # mismatched; pop until we find it or empty
                while stack and stack[-1] != tag:
                    stack.pop()
                if stack and stack[-1] == tag:
                    stack.pop()
        else:
            # void elements don't push
            if tag not in {"br", "hr", "img", "meta", "link", "input"}:
                stack.append(tag)
    return stack[-1] if stack else None


def _line_no(content: str, position: int) -> int:
    return content[:position].count("\n") + 1


def _snippet(content: str, position: int, span_len: int, width: int = 80) -> str:
    """Return up to ±width chars around the match, collapsing whitespace."""
    lo = max(0, position - width)
    hi = min(len(content), position + span_len + width)
    text = content[lo:hi]
    # collapse whitespace runs
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 200:
        text = text[:200]
    return text


def audit_file(path: Path, repo_root: Path = REPO_ROOT) -> list[Finding]:
    """Scan a single HTML file and emit Finding rows for every truth-tag word
    that is NOT wrapped in a tier-bearing `<span class="tt tt-*">`."""
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    masked_text, _ = _build_masked_text(raw)
    partial_chip_spans = _detect_partial_chips(raw)

    findings: list[Finding] = []
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()

    for canonical, pat in TRUTH_TAG_WORDS:
        for m in pat.finditer(masked_text):
            s, e = m.span()
            matched_form = raw[s:e]
            # If matched range overlaps a NUL (\x00) byte we placed, the masking
            # logic accidentally left it visible — defensive skip.
            if any(c == "\x00" for c in raw[s:e]):
                continue
            in_partial = any(ps <= s < pe for ps, pe in partial_chip_spans)
            in_el = _enclosing_element(raw, s)
            severity = "HIGH" if (in_el in {"h1", "h2", "h3", "strong"}) else "MED"
            # ADDITIVE: flag findings inside non-renderable contexts where
            # chip-wrap is structurally inapplicable. Operator's severity rubric
            # is preserved; consumers filter on this flag when prioritizing
            # remediation work.
            in_nonrender = in_el in {
                "script", "head", "meta", "link", "title", "style", "html", None,
            }
            findings.append(
                Finding(
                    file_path=rel,
                    line_no=_line_no(raw, s),
                    surrounding_text=_snippet(raw, s, e - s),
                    word=canonical,
                    matched_form=matched_form,
                    severity=severity,
                    in_element=in_el,
                    is_within_tt_span=False,
                    is_partial_chip=in_partial,
                    is_likely_false_positive=in_nonrender,
                )
            )
    return findings


def audit_corpus(corpus: Iterable[Path], repo_root: Path = REPO_ROOT,
                 quiet: bool = False) -> Iterator[Finding]:
    for path in corpus:
        if not quiet:
            try:
                rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                rel = path.as_posix()
            sys.stderr.write(f"# auditing {rel}\n")
        yield from audit_file(path, repo_root)


# -----------------------------------------------------------------------------
# Output writer
# -----------------------------------------------------------------------------


def write_findings(findings: list[Finding], out_path: Path,
                   corpus_size: int) -> dict:
    """Write findings as JSONL + a final `_summary` row. Returns the summary
    dict for caller convenience."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    by_severity = {"HIGH": 0, "MED": 0}
    by_severity_actionable = {"HIGH": 0, "MED": 0}
    by_file_high: dict[str, int] = {}
    by_file_actionable: dict[str, int] = {}
    partial_chip_count = 0
    false_positive_count = 0

    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for fnd in findings:
            f.write(json.dumps(asdict(fnd), ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
            by_severity[fnd.severity] = by_severity.get(fnd.severity, 0) + 1
            if fnd.severity == "HIGH":
                by_file_high[fnd.file_path] = by_file_high.get(fnd.file_path, 0) + 1
            if fnd.is_partial_chip:
                partial_chip_count += 1
            if fnd.is_likely_false_positive:
                false_positive_count += 1
            else:
                by_severity_actionable[fnd.severity] = by_severity_actionable.get(fnd.severity, 0) + 1
                by_file_actionable[fnd.file_path] = by_file_actionable.get(fnd.file_path, 0) + 1

        summary = {
            "_summary": True,
            "audit_script": "chip_completeness_audit.py",
            "audit_version": "v1.1 (Wave-D 2026-05-16; ADDITIVE is_likely_false_positive)",
            "corpus_size_files": corpus_size,
            "total_findings": len(findings),
            "by_severity": by_severity,
            "by_severity_actionable": by_severity_actionable,
            "partial_chip_findings": partial_chip_count,
            "false_positive_findings": false_positive_count,
            "high_severity_by_file": dict(sorted(by_file_high.items(),
                                                   key=lambda kv: (-kv[1], kv[0]))),
            "actionable_by_file_top20": dict(sorted(by_file_actionable.items(),
                                                     key=lambda kv: (-kv[1], kv[0]))[:20]),
        }
        f.write(json.dumps(summary, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n")
    return summary


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=None,
                    help="Audit a single file instead of full corpus")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"Output JSONL path (default: {DEFAULT_OUT})")
    ap.add_argument("--root", type=Path, default=REPO_ROOT,
                    help=f"Repo root override (default: {REPO_ROOT})")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress per-file progress on stderr")
    args = ap.parse_args(argv)

    if args.file:
        if not args.file.is_file():
            sys.stderr.write(f"error: file not found: {args.file}\n")
            return 2
        corpus = [args.file]
    else:
        corpus = discover_corpus(args.root)
        if not corpus:
            sys.stderr.write(f"error: no files in scope under {args.root}\n")
            return 2

    findings = list(audit_corpus(corpus, repo_root=args.root, quiet=args.quiet))
    summary = write_findings(findings, args.out, corpus_size=len(corpus))

    # Stdout: structured summary for downstream consumers + operator visibility.
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
