"""kernel_hybrid_option_c_dryrun.py — DRY-RUN ONLY (forge.lamport-?-wave-A 2026-05-16).

Wave-A task 02 — AEP-V11-AEP-WAVE-A-FORGE-KERNEL-HYBRID-OPTION-C-DRY-RUN-2026-05-16.

Purpose
-------
Curator wave-1 verdict (`curator.lamport-null-kernel-upgrade-aep-verdict-2026-05-16`)
and wave-3 verdict (`curator.lamport-null-huddle-wave-3-curator-section-66-sibling-91-verdicts-2026-05-16`)
PROMOTE Option C (HYBRID) for the kernel-upgrade-AEP question:

  - §40 SGE / §41 HCRL / §42 KAC / §43 Bootstrap = AEP COMPANION (preserve canonical
    .html; do NOT delete). 128 inbound hrefs measured -> blast-radius too high for
    convert+delete.
  - §57..§66 (newer non-quartet kernel slots) = CONVERT to .aepkg/ + DELETE original
    .html. 44 inbound hrefs measured for §57..§62 -> bounded blast-radius; operator
    taste honored.

This script DRY-RUNS the destructive plan: enumerates §57..§66 doctrine files,
classifies the current AEP companion state, scans the whole repo for inbound href
references to each slot, proposes the per-slot destructive operation, and emits a
href fix-script preview that would rewrite `doctrine/<slot>.html` references to
`doctrine/<slot>.aepkg/assets/original.html` (the existing §50 companion pattern).

THIS SCRIPT NEVER MUTATES THE FILE SYSTEM. Destructive ops require a separate
operator-approved turn.

Output
------
1. JSON report (stdout) with per-slot rows + global summary.
2. HTML report at `doctrine/_proposals/forge-2026-05-16-wave-A-kernel-hybrid-option-c-dryrun-report.html`.

Composition
-----------
Composes with:
  - doctrine/52-hybrid-prose-aep-bridge-protocol.html (companion regeneration rules)
  - doctrine/59-compounding-intelligence-lesson-governance.html (owner-completeness)
  - doctrine/05-git-workflow.html (no destructive ops without explicit approval)
  - §50 EH Law-2 (cheapest disconfirmer = pre-flight count before pre-flight delete)
  - sibling-78 (per-gate scoring + cross-agent canonical citation discipline)
  - sibling-86 (mismanagement-detect-backfill-govern cycle)

Citations
---------
  - curator.lamport-null-kernel-upgrade-aep-verdict-2026-05-16 (Option C PROMOTE)
  - curator.lamport-null-huddle-wave-3-curator-section-66-sibling-91-verdicts-2026-05-16
    (wave-3 sustain §66 SP-ACTIVE; ladder accepted)
  - adversary.lamport-58 huddle-wave-adversary-operator-dumps-premortem-2026-05-16
    (parallel B-ERR verification + concurrent attacks)
  - warden.lamport-null-4f44b42badb2e897a16c5a60 final-round-warden-full-session-audit-2026-05-15
    (parallel wave-A integrity audit baseline)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html as _html
import json
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(r"C:/Users/example-user/")
DOCTRINE_DIR = REPO_ROOT / "doctrine"
REPORT_HTML = (
    REPO_ROOT
    / "doctrine"
    / "_proposals"
    / "forge-2026-05-16-wave-A-kernel-hybrid-option-c-dryrun-report.html"
)

# Slots in scope for CONVERT+DELETE under Option C per curator verdict.
# §40-§43 (kernel quartet) are EXCLUDED from this dryrun by design — they are
# COMPANION-ONLY (preserve canonical .html) per curator G2 PASS on blast-radius.
CANDIDATE_SLOT_NUMBERS = list(range(57, 67))  # 57..66 inclusive

# Slots EXPLICITLY preserved (companion-only). Listed for documentation; this
# script does NOT enumerate or touch them.
PRESERVED_KERNEL_QUARTET = (40, 41, 42, 43)


def utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def find_slot_files(numbers: Iterable[int]) -> list[dict]:
    """Map slot-number -> {number, html_path, aepkg_dir, status}."""
    out = []
    for n in numbers:
        prefix = f"{n:02d}-"
        matches = sorted(p for p in DOCTRINE_DIR.glob(f"{prefix}*.html") if p.is_file())
        # exclude .aepkg internal originals (filter to top-level doctrine/)
        matches = [p for p in matches if p.parent == DOCTRINE_DIR]
        aepkg_matches = sorted(
            p for p in DOCTRINE_DIR.glob(f"{prefix}*.aepkg") if p.is_dir()
        )
        if not matches and not aepkg_matches:
            out.append(
                {
                    "slot_number": n,
                    "slot_basename": None,
                    "html_path": None,
                    "aepkg_dir": None,
                    "status": "NOT-LANDED",
                }
            )
            continue
        html_path = matches[0] if matches else None
        aepkg_dir = aepkg_matches[0] if aepkg_matches else None
        # Derive canonical slot basename from html or aepkg name
        if html_path is not None:
            slot_basename = html_path.stem  # e.g. "57-retrieval-architecture-pattern"
        elif aepkg_dir is not None:
            slot_basename = aepkg_dir.name[: -len(".aepkg")]
        else:
            slot_basename = None
        has_html = html_path is not None
        has_aepkg = aepkg_dir is not None
        if has_html and has_aepkg:
            status = "BOTH"
        elif has_html and not has_aepkg:
            status = "HTML-ONLY"
        elif has_aepkg and not has_html:
            status = "AEPKG-ONLY"
        else:
            status = "NOT-LANDED"
        out.append(
            {
                "slot_number": n,
                "slot_basename": slot_basename,
                "html_path": str(html_path.relative_to(REPO_ROOT)) if html_path else None,
                "aepkg_dir": str(aepkg_dir.relative_to(REPO_ROOT)) if aepkg_dir else None,
                "status": status,
            }
        )
    return out


# --- href scanner --------------------------------------------------------

# Skip directories that would create noise or are irrelevant
SCAN_EXCLUDE_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "dist",
    "build",
}

# Restrict scan to text-ish files for performance and signal
SCAN_INCLUDE_SUFFIXES = {
    ".html",
    ".md",
    ".jsonl",
    ".json",
    ".py",
    ".ps1",
    ".cjs",
    ".js",
    ".ts",
    ".yaml",
    ".yml",
    ".txt",
    ".rst",
}


def iter_repo_files() -> Iterable[Path]:
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        # Skip excluded directories anywhere in the path
        if any(part in SCAN_EXCLUDE_DIR_NAMES for part in p.parts):
            continue
        if p.suffix.lower() not in SCAN_INCLUDE_SUFFIXES:
            continue
        yield p


def build_slot_regex(slot_basename: str) -> re.Pattern[str]:
    """Match any reference to doctrine/<slot_basename>.html.

    Matches forms (case-sensitive):
      - doctrine/<slot>.html
      - ./doctrine/<slot>.html
      - ../doctrine/<slot>.html
      - ../../doctrine/<slot>.html
      - @doctrine/<slot>.html (CLAUDE.md @-references)
    But NOT references to <slot>.aepkg/ contents (those start with the .aepkg/
    segment).
    """
    # Escape the basename for regex literal
    escaped = re.escape(slot_basename)
    # Capture optional leading prefix and the doctrine/<slot>.html token
    return re.compile(rf"(?<![A-Za-z0-9_-])doctrine/{escaped}\.html(?![A-Za-z0-9_-])")


def scan_inbound_hrefs(slot_basename: str) -> dict:
    if not slot_basename:
        return {"total": 0, "by_file": {}}
    rx = build_slot_regex(slot_basename)
    by_file: dict[str, int] = {}
    total = 0
    for fp in iter_repo_files():
        try:
            txt = fp.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            # Skip binary or unreadable; H2 strict-utf-8 discipline (no silent
            # malformed-byte tolerance, but skip is acceptable for inbound scan).
            continue
        matches = rx.findall(txt)
        if matches:
            rel = str(fp.relative_to(REPO_ROOT)).replace("\\", "/")
            by_file[rel] = len(matches)
            total += len(matches)
    return {"total": total, "by_file": by_file}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_fix_script_preview(per_slot_rows: list[dict]) -> str:
    """PowerShell-flavoured preview that would rewrite href references.

    Emitted as a string only — NEVER executed by this script.
    """
    lines = [
        "# kernel_hybrid_option_c_href_fix.ps1 — PREVIEW ONLY (NOT EXECUTED).",
        "# Generated by kernel_hybrid_option_c_dryrun.py at " + utc_now_iso() + ".",
        "# Requires a separate operator-approved turn to actually run.",
        "$ErrorActionPreference = 'Stop'",
        "$repoRoot = 'C:/Users/example-user/'",
        "Push-Location $repoRoot",
        "try {",
    ]
    for row in per_slot_rows:
        if row.get("proposed_action") != "CONVERT-AND-DELETE":
            continue
        slot = row["slot_basename"]
        if not slot:
            continue
        old = f"doctrine/{slot}.html"
        new = f"doctrine/{slot}.aepkg/assets/original.html"
        lines.append("")
        lines.append(f"  # --- {slot} -----------------------------")
        lines.append(
            "  $files = " + json.dumps(sorted(row["inbound_hrefs"]["by_file"].keys()))
        )
        lines.append("  foreach ($f in $files) {")
        lines.append("    $full = Join-Path $repoRoot $f")
        lines.append("    $orig = Get-Content -LiteralPath $full -Raw")
        lines.append(
            "    $next = $orig -replace [regex]::Escape("
            + json.dumps(old)
            + "), "
            + json.dumps(new)
        )
        lines.append("    if ($next -ne $orig) {")
        lines.append("      Set-Content -LiteralPath $full -Value $next -NoNewline -Encoding utf8")
        lines.append("      Write-Host ('rewrote: ' + $f)")
        lines.append("    }")
        lines.append("  }")
    lines.append("} finally { Pop-Location }")
    return "\n".join(lines)


def render_html_report(report: dict, fix_script: str) -> str:
    """Render the dry-run report as a doctrine-style proposal HTML doc."""
    rows = report["per_slot"]
    summary = report["summary"]
    cites = report["cites"]
    rows_html = []
    for r in rows:
        rows_html.append(
            "<tr>"
            f"<td>{r['slot_number']}</td>"
            f"<td><code>{_html.escape(r['slot_basename'] or '(not landed)')}</code></td>"
            f"<td>{_html.escape(r['status'])}</td>"
            f"<td>{r['inbound_hrefs']['total']}</td>"
            f"<td>{_html.escape(r['proposed_action'])}</td>"
            f"<td>{_html.escape(r.get('notes',''))}</td>"
            "</tr>"
        )
    cites_html = "".join(f"<li><code>{_html.escape(c)}</code></li>" for c in cites)
    summary_html = "".join(
        f"<li><strong>{_html.escape(k)}</strong>: {_html.escape(str(v))}</li>"
        for k, v in summary.items()
    )
    title = "forge-2026-05-16-wave-A-kernel-hybrid-option-c-dryrun-report"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<link rel="stylesheet" href="../_assets/aepkit.css" />
<script type="application/json" id="aepkit-metadata">
{{
  "schema_version": "1",
  "type": "proposal",
  "truth_tag": "STRONGLY PLAUSIBLE",
  "cluster_tags": [
    "kernel-hybrid-option-c-dryrun",
    "wave-A-task-02",
    "no-destructive-operations-this-turn",
    "blast-radius-measured-not-assumed",
    "section-52-bridge-invariant-preserved",
    "sibling-78-per-gate-scoring",
    "sibling-86-detect-backfill-govern",
    "forge-generator-role",
    "ace-generator"
  ],
  "mission": "AEP-V11-AEP-WAVE-A-FORGE-KERNEL-HYBRID-OPTION-C-DRY-RUN-2026-05-16",
  "authored": "2026-05-16",
  "emitter_version": "kernel_hybrid_option_c_dryrun.py-v1",
  "doctrine_id": null,
  "cites": {json.dumps(cites)},
  "supersedes": null,
  "superseded_by": null
}}
</script>
</head>
<body>
<header>
<h1>Wave-A Task 02 - Kernel Hybrid Option C Dry-Run Report</h1>
<p><strong>Truth tag</strong>: STRONGLY PLAUSIBLE</p>
<p><strong>Generated</strong>: {report['generated_at']}</p>
<p><strong>Curator verdict</strong>: PROMOTE-OPTION-C-HYBRID (5/5 gates: 3 PASS + 2 PARTIAL + 0 FAIL).</p>
<p><strong>Scope of this dry-run</strong>: §57..§66 only. §40-§43 are companion-only (NOT enumerated).</p>
<p><strong>Destructive ops executed this turn</strong>: 0 (dry-run).</p>
</header>

<section id="per-slot-dryrun-table">
<h2>Per-slot dry-run table</h2>
<table>
<thead><tr>
<th>Slot</th><th>Basename</th><th>State</th><th>Inbound hrefs</th><th>Proposed action</th><th>Notes</th>
</tr></thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</section>

<section id="summary">
<h2>Global summary</h2>
<ul>{summary_html}</ul>
</section>

<section id="fix-script-preview">
<h2>Href fix-script preview (PREVIEW ONLY -- NOT EXECUTED)</h2>
<pre><code>{_html.escape(fix_script)}</code></pre>
</section>

<section id="cites">
<h2>Cross-agent canonical citations</h2>
<ul>{cites_html}</ul>
</section>

<section id="next-steps">
<h2>Next steps (operator approval required)</h2>
<ol>
<li>Operator reviews this dry-run report.</li>
<li>If approved, separate turn executes: (a) materialise .aepkg/ packets for each HTML-ONLY slot using <code>convert_html_lesson</code> (or equivalent doctrine-slot converter), (b) run the href fix-script above, (c) delete bare .html files, (d) warden integrity audit, (e) commit with co-author trailer.</li>
<li>§40-§43 kernel quartet remains companion-only.</li>
</ol>
</section>

</body>
</html>
"""


def build_report() -> tuple[dict, str]:
    files = find_slot_files(CANDIDATE_SLOT_NUMBERS)
    per_slot_rows = []
    n_html_only = 0
    n_both = 0
    n_aepkg_only = 0
    n_not_landed = 0
    n_convert_and_delete = 0
    n_aepkg_companion_only = 0
    total_inbound = 0
    for f in files:
        status = f["status"]
        slot_basename = f["slot_basename"]
        inbound = scan_inbound_hrefs(slot_basename) if slot_basename else {"total": 0, "by_file": {}}
        # Decide proposed_action per curator wave-1 verdict (Option C HYBRID).
        notes = ""
        if status == "NOT-LANDED":
            n_not_landed += 1
            proposed_action = "SKIP-NOT-LANDED"
            notes = "Slot not yet authored in doctrine/; no action."
        elif status == "AEPKG-ONLY":
            n_aepkg_only += 1
            proposed_action = "SKIP-ALREADY-CONVERTED"
            notes = "AEP-only state already matches Option C end-state; no destructive op."
        elif status == "BOTH":
            n_both += 1
            # Both present: companion already materialised; deleting bare .html
            # would complete the convert+delete path PROVIDED inbound hrefs are
            # rewritten first.
            proposed_action = "DELETE-HTML-AFTER-HREF-REWRITE"
            n_convert_and_delete += 1
            notes = (
                f"Companion .aepkg/ present + bare .html present. Rewrite "
                f"{inbound['total']} inbound href(s), then delete bare .html."
            )
        elif status == "HTML-ONLY":
            n_html_only += 1
            proposed_action = "CONVERT-AND-DELETE"
            n_convert_and_delete += 1
            notes = (
                f"Bare .html only. Convert to .aepkg/ (preserve verbatim in "
                f"assets/original.html + sha256), rewrite {inbound['total']} "
                f"inbound href(s), then delete bare .html."
            )
        else:  # defensive
            proposed_action = "UNKNOWN"
        per_slot_rows.append(
            {
                "slot_number": f["slot_number"],
                "slot_basename": slot_basename,
                "html_path": f["html_path"],
                "aepkg_dir": f["aepkg_dir"],
                "status": status,
                "inbound_hrefs": inbound,
                "proposed_action": proposed_action,
                "notes": notes,
            }
        )
        total_inbound += inbound["total"]
    cites = [
        "ledger::curator::lamport-null-kernel-upgrade-aep-verdict-2026-05-16::huddle-wave-curator-kernel-upgrade-verdict-2026-05-16",
        "ledger::curator::lamport-null-huddle-wave-3-curator-section-66-sibling-91-verdicts-2026-05-16::huddle-wave-3-curator-section-66-sibling-91-verdicts-2026-05-16",
        "ledger::adversary::lamport-58::huddle-wave-adversary-operator-dumps-premortem-2026-05-16",
        "ledger::warden::lamport-null-4f44b42badb2e897a16c5a60::final-round-warden-full-session-audit-2026-05-15",
        "doctrine:52-hybrid-prose-aep-bridge-protocol",
        "doctrine:50-epistemic-hygiene-meta-law",
        "doctrine:05-git-workflow",
        "doctrine:59-compounding-intelligence-lesson-governance",
        "lesson:sibling-78",
        "lesson:sibling-86",
        "lesson:sibling-87",
        "pattern:dry-run-before-destructive-op",
        "pattern:blast-radius-measured-not-assumed",
        "pattern:hybrid-bridge-preserved",
    ]
    summary = {
        "scope_slots_enumerated": len(per_slot_rows),
        "preserved_kernel_quartet_NOT_enumerated": list(PRESERVED_KERNEL_QUARTET),
        "n_status_HTML_ONLY": n_html_only,
        "n_status_BOTH": n_both,
        "n_status_AEPKG_ONLY": n_aepkg_only,
        "n_status_NOT_LANDED": n_not_landed,
        "n_proposed_convert_and_delete": n_convert_and_delete,
        "n_proposed_aepkg_companion_only": n_aepkg_companion_only,
        "total_inbound_hrefs_sum": total_inbound,
        "destructive_ops_executed_this_turn": 0,
    }
    report = {
        "generated_at": utc_now_iso(),
        "scope": "kernel-hybrid-option-c-dryrun",
        "wave": "wave-A-task-02",
        "scope_slot_range": [min(CANDIDATE_SLOT_NUMBERS), max(CANDIDATE_SLOT_NUMBERS)],
        "preserved_kernel_quartet": list(PRESERVED_KERNEL_QUARTET),
        "per_slot": per_slot_rows,
        "summary": summary,
        "cites": cites,
    }
    fix_script = build_fix_script_preview(per_slot_rows)
    return report, fix_script


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--write-html-report",
        action="store_true",
        help="Write the HTML report to doctrine/_proposals/.",
    )
    ap.add_argument(
        "--json-out",
        action="store_true",
        help="Print the JSON report to stdout.",
    )
    args = ap.parse_args()
    report, fix_script = build_report()
    if args.write_html_report:
        REPORT_HTML.parent.mkdir(parents=True, exist_ok=True)
        REPORT_HTML.write_text(
            render_html_report(report, fix_script), encoding="utf-8", newline="\n"
        )
    if args.json_out or not args.write_html_report:
        sys.stdout.write(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
