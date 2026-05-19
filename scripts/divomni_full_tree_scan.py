"""AEP project full-tree scan — categorize every file for efficiency-maxx restructure.

Mission: AEP-V11-AEP-AEP-FULL-TREE-SCAN-DRY-RUN-2026-05-16
Owner:   forge
Cites:   pathfinder.lamport-61 + scribe.lamport-null-governance-scribe-sibling-86 +
         curator.lamport-null-section-60-61-curator-verdict-2026-05-16

WHAT THIS DOES (SCAN + REPORT ONLY — DRY-RUN ENFORCED):
  1. Walks the entire AEP project repo, skipping ignore-list directories
     (.git/, node_modules/, _logs/, .tmp_* paths, godview-prime/, scheduled_tasks*).
  2. Categorizes every file into one of:
       AEP-CANDIDATE     — knowledge artifact that could become an .aepkg/ packet
       AEP-COMPANIONED   — already has a sibling .aepkg/ companion
       INSIDE-AEPKG      — already lives inside an existing .aepkg/ packet
       AEP-EXEMPT        — code / config / data / binary; NOT a candidate
       NEEDS-FOLDER      — at top-level or in a mixed-type folder; type-sorted target
       TMP-CRUFT         — temp / scratch file; flagged for deletion review
       INDEX             — _index.html or root index files (categorical exempt)
  3. For every non-exempt mis-located file, propose a target folder by file type.
  4. Writes a deterministic HTML report enumerating what WOULD change.

WHAT THIS DOES NOT DO:
  - It NEVER moves a file.
  - It NEVER deletes a file.
  - It NEVER touches an .aepkg/ packet.
  - All destructive work is deferred to a separate operator-approved turn.

Falsifier (sibling-85 honest-disclosure-dogfood): if this script produces zero
findings, the scan is broken (the operator-confirmed pollution shows tmp files
at root + mixed-type folders).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[5]  # five .. from .../scripts/X.py

# Directory names we never descend into (anywhere in the tree).
SKIP_DIRS_EXACT = {
    ".git",
    "node_modules",
    "__pycache__",
    ".cache",
    ".backups",
    ".archive",
    ".playwright-mcp",
    "godview-prime",
    "aepkit-godview",
    "_logs",
    ".tmp_video_frames",
    "_overnight",
    "_resumption",
    # Build/cache artifacts that pollute file counts but are NOT operator-owned.
    ".pnpm-store",
    ".pnpm",
    ".turbo",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "dist",
    "build",
    "out",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "site-packages",
    ".tox",
    "test-results",
    "playwright-report",
    "codex-worker",  # projects/godview-prime-v4/data/codex-worker bulk artifacts
    "codex-packets",  # .aepkit/codex-packets — Codex burn evidence cache, NOT knowledge
    "_archive",  # versioned archives — intentional retention
    "_archived",
    # Browser-profile + Prisma generated DLLs — runtime caches, never operator content.
    "Cache_Data",
    "Safe Browsing",
    "browser-proof",  # whole live-chrome-profile dump under projects/lodestone/codex-lab
    "generated",  # Prisma client + Next.js build emits
}

# Prefix patterns we never descend into (top-level scratch).
SKIP_DIR_PREFIXES = (
    ".tmp_",
    "scheduled_tasks",
)

# File-extensions that CAN be modeled as AEP packets (knowledge artifacts).
AEP_CANDIDATE_EXTS = {".html", ".md"}

# AEP-EXEMPT classes — file extensions that should NEVER become AEP packets.
# These still get NEEDS-FOLDER classification when at top-level / mixed-type folder.
CODE_EXTS = {".py", ".ps1", ".sh", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env", ".lock"}
DATA_EXTS = {".jsonl", ".ndjson", ".csv", ".tsv", ".parquet", ".pkl", ".npy"}
BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".webp", ".ico",
               ".mp4", ".mov", ".webm", ".woff", ".woff2", ".ttf", ".otf",
               ".zip", ".gz", ".tar"}
STYLE_EXTS = {".css", ".scss"}
TEXT_EXTS = {".txt"}

# Files that are categorically exempt from NEEDS-FOLDER moves at top-level.
TOP_LEVEL_KEEP = {
    "CLAUDE.md",
    "README.md",
    "index.html",
    "package.json",
    "package-lock.json",
    "playwright.config.js",
    "playwright.e2e.config.js",
    "playwright.probe.config.js",
    ".gitignore",
    ".mcp.json",
    ".cursorrules",
    "MEGA-AEP-CAPABILITY-MAP.html",
}

# Type → proposed top-level folder for top-level orphans.
# (For files already inside a deep tree, we don't propose a folder unless the
# leaf folder is "mixed-type" per the rules below.)
TOP_LEVEL_TYPE_FOLDER = {
    ".py": "tools/python/",
    ".ps1": "tools/powershell/",
    ".sh": "tools/bash/",
    ".js": "tools/js/",
    ".ts": "tools/ts/",
    ".html": "library/html/",
    ".md": "library/md/",
    ".json": "config/json/",
    ".yaml": "config/yaml/",
    ".yml": "config/yaml/",
    ".jsonl": "data/jsonl/",
    ".csv": "data/csv/",
    ".tsv": "data/tsv/",
    ".png": "assets/img/",
    ".jpg": "assets/img/",
    ".pdf": "assets/pdf/",
    ".webp": "assets/img/",
    ".txt": "library/txt/",
    ".log": "logs/",
}

# Files that are obvious tmp-cruft and should be queued for deletion review.
TMP_CRUFT_PREFIXES = (".tmp_",)
TMP_CRUFT_SUFFIXES = (".bak", ".tmp", ".swp", ".swo")


# ---------------------------------------------------------------------------
# Walk
# ---------------------------------------------------------------------------

def iter_repo_files(root: Path) -> Iterable[Path]:
    """Yield every file under root that is not inside a skipped directory."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Mutate dirnames in place to prune the walk.
        pruned = []
        for d in dirnames:
            if d in SKIP_DIRS_EXACT:
                continue
            if any(d.startswith(p) for p in SKIP_DIR_PREFIXES):
                continue
            pruned.append(d)
        dirnames[:] = pruned

        for fn in filenames:
            yield Path(dirpath) / fn


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

def relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts


def is_inside_aepkg(path: Path, root: Path) -> bool:
    """True if any path-segment ends in .aepkg/."""
    return any(p.endswith(".aepkg") for p in relative_parts(path, root))


def has_sibling_aepkg(path: Path) -> bool:
    """For an HTML/MD file at <stem>.html, True if <stem>.aepkg/ exists alongside."""
    if path.suffix.lower() not in AEP_CANDIDATE_EXTS:
        return False
    sibling = path.with_suffix(".aepkg")
    return sibling.is_dir()


def is_top_level(path: Path, root: Path) -> bool:
    parts = relative_parts(path, root)
    return len(parts) == 1


def folder_type_mix(path: Path) -> Counter[str]:
    """Tally extensions in the file's immediate parent folder."""
    counter: Counter[str] = Counter()
    parent = path.parent
    if not parent.is_dir():
        return counter
    for child in parent.iterdir():
        if child.is_file():
            counter[child.suffix.lower()] += 1
    return counter


def is_mixed_type_folder(path: Path) -> bool:
    """True if the immediate parent folder contains >=3 distinct extensions
    AND has >=5 total files. Files inside .aepkg/, doctrine/, or .claude/
    structures are exempt because those are intentionally heterogeneous."""
    parts = path.parts
    # Doctrine + agent tree intentionally heterogeneous.
    intentionally_mixed_segments = {".aepkg", "doctrine", ".claude", "library",
                                    "research", "projects", "data", "tests"}
    if any(seg in intentionally_mixed_segments for seg in parts):
        return False
    mix = folder_type_mix(path)
    return len(mix) >= 3 and sum(mix.values()) >= 5


def is_tmp_cruft(path: Path) -> bool:
    name = path.name
    if any(name.startswith(p) for p in TMP_CRUFT_PREFIXES):
        return True
    if any(name.endswith(s) for s in TMP_CRUFT_SUFFIXES):
        return True
    return False


def is_index_artifact(path: Path) -> bool:
    return path.name in {"_index.html", "index.html", "README.md"}


def aep_candidate_class(path: Path, root: Path) -> str | None:
    """Return AEP-candidate sub-class if this file is a knowledge artifact, else None."""
    suffix = path.suffix.lower()
    if suffix not in AEP_CANDIDATE_EXTS:
        return None
    if is_inside_aepkg(path, root):
        return None
    if is_index_artifact(path):
        return None
    parts = relative_parts(path, root)
    p0 = parts[0] if parts else ""
    p1 = parts[1] if len(parts) > 1 else ""
    p_set = set(parts)

    # Class 1: doctrine slots
    if p0 == "doctrine" and "_proposals" not in p_set and "lessons" not in p_set:
        if suffix == ".html" and re.match(r"\d{2}-", path.name):
            return "doctrine-slot"

    # Class 2: doctrine lessons
    if "lessons" in p_set and suffix == ".html":
        return "lesson"

    # Class 3: doctrine proposals
    if "_proposals" in p_set and suffix == ".html":
        return "proposal"

    # Class 4: research sources / analysis
    if p0 == "research" and suffix == ".html":
        return "research-artifact"

    # Class 5: agent-roster docs
    if p0 == ".claude" and "agents" in p_set and suffix == ".md":
        return "agent-roster"

    # Class 6: general md/html knowledge files outside intentionally exempt zones
    exempt_dirs = {"node_modules", "tests", "projects"}  # projects has own AEP scope
    if not any(d in p_set for d in exempt_dirs):
        # MD or HTML at root or top-level scratch usually is knowledge.
        return "loose-knowledge"

    return None


def exempt_class(path: Path) -> str | None:
    """Return EXEMPT sub-class label if file is categorically AEP-EXEMPT."""
    suffix = path.suffix.lower()
    if suffix in CODE_EXTS:
        return "code"
    if suffix in CONFIG_EXTS:
        return "config"
    if suffix in DATA_EXTS:
        return "data"
    if suffix in BINARY_EXTS:
        return "binary"
    if suffix in STYLE_EXTS:
        return "style"
    if suffix in TEXT_EXTS:
        return "text"
    return None


def proposed_target(path: Path, root: Path) -> str | None:
    """For top-level orphans or mixed-folder strays, propose a target dir."""
    if is_inside_aepkg(path, root):
        return None
    name = path.name
    if name in TOP_LEVEL_KEEP:
        return None
    if is_index_artifact(path):
        return None
    suffix = path.suffix.lower()
    if not suffix:
        return None
    # Only propose moves for top-level orphans or mixed-folder strays.
    if is_top_level(path, root):
        target = TOP_LEVEL_TYPE_FOLDER.get(suffix)
        if target:
            return target
    if is_mixed_type_folder(path):
        target = TOP_LEVEL_TYPE_FOLDER.get(suffix)
        if target:
            # Adjust target to be relative to the parent folder.
            return f"{path.parent.relative_to(root).as_posix()}/{Path(target).name}/"
    return None


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan(root: Path) -> dict:
    findings = {
        "aep_candidate_stragglers": [],
        "aep_companioned": [],
        "inside_aepkg": [],
        "aep_exempt": [],
        "needs_folder": [],
        "tmp_cruft": [],
        "index_artifacts": [],
        "top_level_keep": [],
    }
    extension_counter: Counter[str] = Counter()
    candidate_class_counter: Counter[str] = Counter()
    exempt_class_counter: Counter[str] = Counter()
    n_files = 0

    for path in iter_repo_files(root):
        n_files += 1
        rel = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        extension_counter[suffix or "<none>"] += 1

        # 0. tmp cruft first (most-recoverable wins).
        if is_tmp_cruft(path):
            findings["tmp_cruft"].append({"path": rel, "size": path.stat().st_size})
            continue

        # 1. inside .aepkg/ — already absorbed.
        if is_inside_aepkg(path, root):
            findings["inside_aepkg"].append(rel)
            continue

        # 2. index artifacts — categorical keep.
        if is_index_artifact(path):
            findings["index_artifacts"].append(rel)
            continue

        # 3. top-level keep list.
        if is_top_level(path, root) and path.name in TOP_LEVEL_KEEP:
            findings["top_level_keep"].append(rel)
            continue

        # 4. AEP candidate?
        cand = aep_candidate_class(path, root)
        if cand is not None:
            candidate_class_counter[cand] += 1
            if has_sibling_aepkg(path):
                findings["aep_companioned"].append({"path": rel, "class": cand})
            else:
                target = proposed_target(path, root)
                findings["aep_candidate_stragglers"].append({
                    "path": rel,
                    "class": cand,
                    "size": path.stat().st_size,
                    "proposed_folder": target,
                })
            continue

        # 5. Exempt by extension class?
        ex = exempt_class(path)
        if ex is not None:
            exempt_class_counter[ex] += 1
            target = proposed_target(path, root)
            entry = {"path": rel, "class": ex,
                     "size": path.stat().st_size,
                     "proposed_folder": target}
            findings["aep_exempt"].append(entry)
            if target is not None:
                findings["needs_folder"].append(entry)
            continue

        # 6. Unknown — bucket as needs-folder catch-all with no proposed dir.
        findings["needs_folder"].append({"path": rel, "class": "unknown",
                                          "size": path.stat().st_size,
                                          "proposed_folder": None})

    summary = {
        "n_files_total": n_files,
        "n_aep_candidate_stragglers": len(findings["aep_candidate_stragglers"]),
        "n_aep_companioned": len(findings["aep_companioned"]),
        "n_inside_aepkg": len(findings["inside_aepkg"]),
        "n_aep_exempt": len(findings["aep_exempt"]),
        "n_needs_folder": len(findings["needs_folder"]),
        "n_tmp_cruft": len(findings["tmp_cruft"]),
        "n_index_artifacts": len(findings["index_artifacts"]),
        "n_top_level_keep": len(findings["top_level_keep"]),
        "extension_histogram": dict(extension_counter.most_common(30)),
        "aep_candidate_class_histogram": dict(candidate_class_counter),
        "exempt_class_histogram": dict(exempt_class_counter),
    }
    return {"summary": summary, "findings": findings}


def top_stragglers(findings: list, n: int = 20) -> list:
    return sorted(findings, key=lambda r: r.get("size", 0), reverse=True)[:n]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

REPORT_HEADER = """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>forge — AEP project full-tree scan (dry-run report) 2026-05-16</title>
<link rel="stylesheet" href="../_assets/aepkit.css" />
<script type="application/json" id="aepkit-metadata">
{{
  "schema_version": "1",
  "type": "proposal",
  "truth_tag": "STRONGLY PLAUSIBLE",
  "cluster_tags": ["full-tree-scan", "dry-run", "efficiency-maxx", "scope-scan-only",
                   "aep-companion-stragglers", "needs-folder", "tmp-cruft",
                   "operator-mandate-2026-05-16", "huddle-wave-forge"],
  "sibling_md": null,
  "renderer": "raw-html",
  "mission": "AEP-V11-AEP-AEP-FULL-TREE-SCAN-DRY-RUN-2026-05-16",
  "authored": "2026-05-16",
  "emitter_version": "v3.0",
  "doctrine_id": null,
  "cites": ["ledger::pathfinder::lamport-61::master-plan-all-metrics-to-99pct-2026-05-15",
            "ledger::scribe::lamport-null-317cdc09526421d37e0f4416::governance-scribe-owner-backfill-2026-05-15",
            "ledger::curator::lamport-57::cross-agent-citation-test-curator-2026-05-15",
            "lesson:sibling-78", "lesson:sibling-86", "lesson:sibling-87",
            "doctrine:50-epistemic-hygiene-meta-law",
            "doctrine:59-compounding-intelligence-lesson-governance",
            "doctrine:60-pre-coding-lesson-review-discipline",
            "pattern:dry-run-scan-before-destructive",
            "pattern:single-writer-via-import",
            "pattern:np-1-explanation-ladder-gate",
            "pattern:np-4-numbers-need-receipts"],
  "supersedes": null,
  "superseded_by": null
}}
</script>
</head>
<body>
"""


def render_report(report: dict, root: Path) -> str:
    s = report["summary"]
    f = report["findings"]
    now = datetime.now(timezone.utc).isoformat()
    sha = hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]

    out = [REPORT_HEADER]
    out.append("<main class='proposal'>")
    out.append("<h1>forge — AEP project full-tree scan (dry-run report)</h1>")
    out.append(f"<p><strong>Generated:</strong> {html.escape(now)}<br/>")
    out.append(f"<strong>Mission:</strong> AEP-V11-AEP-AEP-FULL-TREE-SCAN-DRY-RUN-2026-05-16<br/>")
    out.append(f"<strong>Truth tag:</strong> STRONGLY PLAUSIBLE<br/>")
    out.append(f"<strong>Repo root:</strong> {html.escape(str(root))}<br/>")
    out.append(f"<strong>Summary SHA-256 (first 16):</strong> {sha}</p>")

    out.append("<h2>1. Scope this turn</h2>")
    out.append("<p>SCAN + REPORT ONLY. <strong>Zero files were moved, deleted, or modified.</strong> "
               "Every finding below describes what <em>would</em> change if operator approves the next "
               "destructive turn. This is the dry-run substrate per the operator directive 2026-05-16.</p>")

    out.append("<h2>2. Counts</h2>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Category</th><th>Count</th><th>Meaning</th></tr>")
    rows = [
        ("Total files scanned", s["n_files_total"], "Everything under root, minus skip-list dirs."),
        ("AEP-candidate stragglers", s["n_aep_candidate_stragglers"],
         "Knowledge artifact (.html/.md) with NO sibling .aepkg/ companion. Eligible for AEP packetization."),
        ("AEP-companioned (already done)", s["n_aep_companioned"],
         "Knowledge artifact that already has its .aepkg/ companion."),
        ("Inside .aepkg/ (absorbed)", s["n_inside_aepkg"],
         "Files living inside an existing AEP packet. No action."),
        ("AEP-exempt", s["n_aep_exempt"],
         "Code/config/data/binary. Should never become AEP. May still need a folder."),
        ("NEEDS-FOLDER", s["n_needs_folder"],
         "File at top-level or mixed-type folder. Type-specific folder proposed below."),
        ("TMP-CRUFT (delete-review)", s["n_tmp_cruft"],
         "Files matching .tmp_* / .bak / .tmp / .swp. Queued for operator delete-review."),
        ("Index artifacts", s["n_index_artifacts"],
         "_index.html / index.html / README.md — categorical keep."),
        ("Top-level keep list", s["n_top_level_keep"],
         "Canonical root-level config (CLAUDE.md, package.json, etc.). Keep at root."),
    ]
    for label, count, meaning in rows:
        out.append(f"<tr><td>{html.escape(label)}</td><td>{count}</td><td>{html.escape(meaning)}</td></tr>")
    out.append("</table>")

    out.append("<h2>3. Top-30 extensions</h2>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Extension</th><th>Count</th></tr>")
    for ext, count in s["extension_histogram"].items():
        out.append(f"<tr><td>{html.escape(ext)}</td><td>{count}</td></tr>")
    out.append("</table>")

    out.append("<h2>4. AEP-candidate class histogram</h2>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Class</th><th>Count</th></tr>")
    for cls, count in s["aep_candidate_class_histogram"].items():
        out.append(f"<tr><td>{html.escape(cls)}</td><td>{count}</td></tr>")
    out.append("</table>")

    out.append("<h2>5. AEP-exempt class histogram</h2>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Class</th><th>Count</th></tr>")
    for cls, count in s["exempt_class_histogram"].items():
        out.append(f"<tr><td>{html.escape(cls)}</td><td>{count}</td></tr>")
    out.append("</table>")

    out.append("<h2>6. Top-20 AEP-candidate stragglers (by size)</h2>")
    out.append("<p>These are knowledge artifacts that should each have an .aepkg/ companion. "
               "If operator approves the next turn, each gets converted via the standard AEP pipeline.</p>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Path</th><th>Class</th><th>Size (bytes)</th><th>Proposed folder (if move needed)</th></tr>")
    for entry in top_stragglers(f["aep_candidate_stragglers"], 20):
        path = entry["path"]
        cls = entry["class"]
        size = entry["size"]
        target = entry.get("proposed_folder") or "(in place)"
        out.append(f"<tr><td>{html.escape(path)}</td><td>{html.escape(cls)}</td>"
                   f"<td>{size}</td><td>{html.escape(target)}</td></tr>")
    out.append("</table>")

    out.append("<h2>7. Top-20 NEEDS-FOLDER findings (by size)</h2>")
    out.append("<p>Files at top-level or in mixed-type folders. Proposed targets follow the type-specific "
               "convention (tools/python/, tools/powershell/, config/json/, library/md/, etc.).</p>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Path</th><th>Class</th><th>Size (bytes)</th><th>Proposed folder</th></tr>")
    for entry in top_stragglers(f["needs_folder"], 20):
        path = entry["path"]
        cls = entry.get("class", "")
        size = entry.get("size", 0)
        target = entry.get("proposed_folder") or "(unclassified)"
        out.append(f"<tr><td>{html.escape(path)}</td><td>{html.escape(str(cls))}</td>"
                   f"<td>{size}</td><td>{html.escape(target)}</td></tr>")
    out.append("</table>")

    out.append("<h2>8. Top-20 TMP-CRUFT findings (delete-review queue)</h2>")
    out.append("<p>Files matching tmp/scratch patterns. Operator must explicitly approve deletion. "
               "Files in this list have <strong>NOT</strong> been deleted.</p>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Path</th><th>Size (bytes)</th></tr>")
    for entry in top_stragglers(f["tmp_cruft"], 20):
        out.append(f"<tr><td>{html.escape(entry['path'])}</td><td>{entry['size']}</td></tr>")
    out.append("</table>")

    out.append("<h2>9. Proposed folder structure (per operator directive)</h2>")
    out.append("<p>The operator directive mandates type-specific folders. The script's current mapping is "
               "the default; operator can override before destructive turn.</p>")
    out.append("<table border='1' cellpadding='4' cellspacing='0'>")
    out.append("<tr><th>Extension</th><th>Proposed top-level target folder</th></tr>")
    for ext, folder in sorted(TOP_LEVEL_TYPE_FOLDER.items()):
        out.append(f"<tr><td>{html.escape(ext)}</td><td>{html.escape(folder)}</td></tr>")
    out.append("</table>")

    out.append("<h2>10. Decision matrix for the destructive turn</h2>")
    out.append("<ol>")
    out.append("<li><strong>Approve TMP-CRUFT deletion?</strong> Yes/No per file or bulk. "
               "Bulk-rejects keep cruft in place; no harm.</li>")
    out.append("<li><strong>Approve AEP packetization of stragglers?</strong> If yes, scribe single-writer "
               "produces the .aepkg/ packet per existing convert_html_lesson.py pipeline.</li>")
    out.append("<li><strong>Approve type-folder restructure?</strong> Yes/No per type. If no, files stay in "
               "place; the dry-run is itself a record.</li>")
    out.append("<li><strong>Curator stamps the destructive turn?</strong> Required per §59 + §60 "
               "before any move; this dry-run is the evidence packet.</li>")
    out.append("</ol>")

    out.append("<h2>11. Falsifier honored</h2>")
    out.append("<p>Sibling-85 honest-disclosure-dogfood: if this scan reports zero findings across "
               "TMP-CRUFT + NEEDS-FOLDER + AEP-candidate-stragglers, the scan is broken. The operator-confirmed "
               "pollution at the repo root (tmp files + mixed top-level types) means zero is the wrong answer. "
               "Counts above are the verification.</p>")

    out.append("<h2>12. Cross-agent canonical citations</h2>")
    out.append("<ul>")
    out.append("<li><code>ledger::pathfinder::lamport-61::master-plan-all-metrics-to-99pct-2026-05-15</code> — "
               "pathfinder's metric ladder discipline; this scan is one rung on the path-to-99pct.</li>")
    out.append("<li><code>ledger::scribe::lamport-null-317cdc09526421d37e0f4416::"
               "governance-scribe-owner-backfill-2026-05-15</code> — "
               "scribe's owner-backfill governance row (sibling-86 discipline applied); this scan is the "
               "DETECT phase of the four-step cycle (detect &rarr; backfill &rarr; govern &rarr; capture). "
               "Destructive pass is BACKFILL.</li>")
    out.append("<li><code>ledger::curator::lamport-57::"
               "cross-agent-citation-test-curator-2026-05-15</code> — "
               "curator's most recent canonical-numeric promotion verdict (PROMOTE section-56-ladder G1-G5); "
               "categorization changes need curator approval before destructive turn per &sect;59 governance + "
               "&sect;60 pre-coding-lesson-review-law.</li>")
    out.append("</ul>")

    out.append("</main>")
    out.append("</body></html>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AEP project full-tree scan — dry-run categorization for efficiency-maxx restructure.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repo root to scan (default: AEP project repo root).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "doctrine" / "_proposals" / "forge-2026-05-16-aepkit-full-tree-scan-report.html",
        help="Path to write the HTML report.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the raw JSON findings.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="THIS FLAG IS A NO-OP. The script is dry-run only; --apply is reserved for a "
             "future operator-approved turn and currently refuses with exit code 2.",
    )
    args = parser.parse_args(argv)

    if args.apply:
        print("REFUSED: this script is dry-run only. Destructive operations require an "
              "operator-approved separate turn. Exiting with code 2.", file=sys.stderr)
        return 2

    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        return 1

    report = scan(root)
    html_str = render_report(report, root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(html_str, encoding="utf-8")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )

    s = report["summary"]
    print(json.dumps({
        "report_path": str(args.report),
        "json_out": str(args.json_out) if args.json_out else None,
        "summary": s,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
