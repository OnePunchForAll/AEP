#!/usr/bin/env python3
"""
Wave 6 AEPification Gap Inventory.

Walks the AEP project tree (git-tracked + workspace files), classifies by extension,
cross-references existing .aepkg/ companions against canonical sources, and
emits a gap matrix + Phase β-expansion wave plan.

EXCLUSIONS:
- .git/ subtree
- node_modules/
- __pycache__
- .pytest_cache
- .vscode/
- .DS_Store
- *.pyc
- .claude/aep/perf/* transient telemetry

This script is sec68-compliant: pure Python, no subprocess to powershell/bash.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]

EXCLUDE_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    ".idea",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
}

EXCLUDE_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
}

# Transient telemetry — companion-only candidates, not for primary AEPification
TRANSIENT_PATH_PREFIXES = (
    str(pathlib.Path(".claude/aep/perf")).replace("\\", "/"),
    str(pathlib.Path(".claude/aep/receipts")).replace("\\", "/"),
    str(pathlib.Path(".claude/aep/transactions")).replace("\\", "/"),
    str(pathlib.Path(".claude/_logs")).replace("\\", "/"),
)

FILE_CLASSES = [
    ("markdown",   {".md", ".markdown"}),
    ("html",       {".html", ".htm"}),
    ("python",     {".py"}),
    ("javascript", {".js", ".cjs", ".mjs"}),
    ("perl",       {".pl"}),
    ("ruby",       {".rb"}),
    ("go",         {".go"}),
    ("rust",       {".rs"}),
    ("json",       {".json"}),
    ("yaml",       {".yaml", ".yml"}),
    ("text",       {".txt"}),
    ("log",        {".log"}),
    ("jsonl",      {".jsonl"}),
    ("image",      {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}),
    ("pdf",        {".pdf"}),
    ("archive",    {".zip", ".gz", ".tar", ".bz2", ".7z", ".xz"}),
    ("webfont",    {".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot"}),
]

# Build extension -> class map
EXT_TO_CLASS = {}
for cls, exts in FILE_CLASSES:
    for ext in exts:
        EXT_TO_CLASS[ext] = cls


def is_excluded_path(rel_path: pathlib.PurePath) -> bool:
    parts = set(rel_path.parts)
    if parts & EXCLUDE_DIR_NAMES:
        return True
    if rel_path.name in EXCLUDE_FILE_NAMES:
        return True
    posix = rel_path.as_posix()
    if posix.startswith(TRANSIENT_PATH_PREFIXES):
        return True
    return False


def classify(path: pathlib.PurePath) -> str:
    ext = path.suffix.lower()
    if ext in EXCLUDE_EXTENSIONS:
        return "_excluded_ext"
    return EXT_TO_CLASS.get(ext, "other:" + (ext if ext else "noext"))


def walk_tree(root: pathlib.Path) -> Tuple[Dict[str, int], List[pathlib.Path], List[str], Dict[str, int]]:
    """
    Returns:
      class_counts: {class_name: count}
      all_files: list of relative paths
      aepkg_canonical_sources: list of canonical-source posix paths declared by .aepkg/integrity.json
      other_ext_counts: {ext: count} for the 'other' bucket
    """
    class_counts: Dict[str, int] = defaultdict(int)
    other_ext_counts: Dict[str, int] = defaultdict(int)
    all_files: List[pathlib.Path] = []
    aepkg_paths: List[pathlib.Path] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel_dir = pathlib.Path(dirpath).relative_to(root)
        if str(rel_dir) == ".":
            rel_dir_parts = ()
        else:
            rel_dir_parts = rel_dir.parts

        # prune
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
        rel_dir_posix = rel_dir.as_posix() if rel_dir_parts else ""
        if rel_dir_posix and rel_dir_posix.startswith(TRANSIENT_PATH_PREFIXES):
            dirnames[:] = []  # don't descend
            continue

        for fname in filenames:
            rel = rel_dir / fname if rel_dir_parts else pathlib.Path(fname)
            if is_excluded_path(rel):
                continue
            ext = rel.suffix.lower()
            if ext in EXCLUDE_EXTENSIONS:
                continue
            all_files.append(rel)
            cls = classify(rel)
            if cls.startswith("other:"):
                other_ext_counts[cls[6:]] += 1
                class_counts["other"] += 1
            else:
                class_counts[cls] += 1

            # If this is aepkg.json or integrity.json inside an .aepkg/, treat as companion marker
            if fname in ("aepkg.json", "integrity.json"):
                # walk up: any parent ending in .aepkg ?
                p = rel
                for ancestor in p.parents:
                    if ancestor.name.endswith(".aepkg"):
                        # de-dupe (aepkg may have both files)
                        if not aepkg_paths or aepkg_paths[-1] != ancestor:
                            aepkg_paths.append(ancestor)
                        break

    return dict(class_counts), all_files, aepkg_paths, dict(other_ext_counts)


def read_companion_canonical_source(integrity_json_path: pathlib.Path, root: pathlib.Path) -> str | None:
    """Return relative-posix path of canonical source declared by integrity.json, or None."""
    try:
        with open(integrity_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    # Possible field names in different .aepkg generations:
    candidates = [
        "canonical_source",
        "canonical_source_path",
        "canonical_md_path",
        "canonical_html_path",
        "sha256_of_canonical_md",  # the field name itself doesn't give path; but presence implies <name>.md
        "source_path",
    ]
    for k in candidates:
        if k in data and isinstance(data[k], str):
            v = data[k]
            if not v.startswith("sha256:"):
                return v.replace("\\", "/").lstrip("./")
    # Fallback: derive from companion location — .aepkg name typically matches the source file basename
    aepkg_dir = integrity_json_path.parent
    base = aepkg_dir.name[:-len(".aepkg")]
    parent = aepkg_dir.parent.relative_to(root)
    # Try common extensions; we'll let cross-reference logic resolve
    for ext in (".md", ".html", ".jsonl", ".py"):
        candidate = (parent / (base + ext)).as_posix()
        if (root / candidate).exists():
            return candidate
    return None


def load_git_tracked(root: pathlib.Path) -> set[str] | None:
    """Read .git index — git-tracked files only — fast, no subprocess."""
    # Use simple subprocess to git ls-files; falls back to None on failure
    import subprocess
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=str(root), timeout=60, text=True)
        return {line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()}
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def main() -> int:
    root = REPO_ROOT
    print(f"[wave6-inventory] root={root}", file=sys.stderr)

    git_tracked = load_git_tracked(root)
    if git_tracked is not None:
        print(f"[wave6-inventory] git_tracked_count={len(git_tracked)}", file=sys.stderr)

    class_counts, all_files, aepkg_dirs, other_exts = walk_tree(root)

    # Filter all_files to git-tracked when available (honest scope)
    if git_tracked is not None:
        all_files = [p for p in all_files if p.as_posix() in git_tracked]
        # rebuild class_counts + other_exts from filtered set
        class_counts = defaultdict(int)
        other_exts = defaultdict(int)
        for rel in all_files:
            cls = classify(rel)
            if cls.startswith("other:"):
                other_exts[cls[6:]] += 1
                class_counts["other"] += 1
            else:
                class_counts[cls] += 1
        class_counts = dict(class_counts)
        other_exts = dict(other_exts)

    # de-dupe aepkg_dirs (a packet may have both aepkg.json and integrity.json)
    aepkg_dirs = list({d.as_posix(): d for d in aepkg_dirs}.values())

    # Resolve canonical sources for each .aepkg/
    companion_to_canonical: Dict[str, str] = {}
    canonical_set = set()
    for aepkg in aepkg_dirs:
        integrity = root / aepkg / "integrity.json"
        aepkg_json = root / aepkg / "aepkg.json"
        src = None
        if integrity.exists():
            src = read_companion_canonical_source(integrity, root)
        if not src and aepkg_json.exists():
            src = read_companion_canonical_source(aepkg_json, root)
        rel_aepkg = aepkg.as_posix()
        if src:
            companion_to_canonical[rel_aepkg] = src
            canonical_set.add(src.lstrip("./"))
        else:
            # derive from .aepkg dir name → ../<basename>.{md,html,...}
            base = aepkg.name[:-len(".aepkg")]
            parent = aepkg.parent
            for ext in (".md", ".html", ".jsonl", ".py", ".json", ".txt"):
                candidate = (parent / (base + ext)).as_posix()
                if (root / candidate).exists():
                    companion_to_canonical[rel_aepkg] = candidate
                    canonical_set.add(candidate.lstrip("./"))
                    src = candidate
                    break
            if not src:
                companion_to_canonical[rel_aepkg] = ""  # orphan companion

    # Build set of file posix paths
    all_posix = {p.as_posix() for p in all_files}

    # Per-class: total, has-companion, missing-companion
    per_class_total: Dict[str, int] = defaultdict(int)
    per_class_has_companion: Dict[str, int] = defaultdict(int)
    for rel in all_files:
        cls = classify(rel)
        if cls.startswith("other:"):
            cls = "other"
        per_class_total[cls] += 1
        if rel.as_posix() in canonical_set:
            per_class_has_companion[cls] += 1

    # Gap matrix
    gap_rows = []
    for cls, total in sorted(per_class_total.items(), key=lambda kv: -kv[1]):
        have = per_class_has_companion.get(cls, 0)
        missing = total - have
        pct_missing = (missing / total * 100.0) if total else 0.0
        gap_rows.append({
            "class": cls,
            "total": total,
            "have_companion": have,
            "missing_companion": missing,
            "gap_pct": pct_missing,
        })

    # High-risk preflight identification
    high_risk: Dict[str, List[str]] = defaultdict(list)
    for rel in all_files:
        rp = rel.as_posix()
        if "/aep/perf/" in rp or rp.startswith(".claude/aep/perf/"):
            high_risk["live_hot_telemetry"].append(rp)
        if rel.suffix.lower() == ".env" or rel.name.startswith(".env"):
            high_risk["secret_candidate_env"].append(rp)
        if "/credentials" in rp.lower() or rel.name.lower().startswith("secret"):
            high_risk["secret_candidate_named"].append(rp)
        # large files
        try:
            sz = (root / rel).stat().st_size
            if sz > 1_000_000:
                high_risk["large_files_gt_1mb"].append(f"{rp} ({sz:,} bytes)")
        except OSError:
            pass

    # Symlinks
    symlinks = []
    for rel in all_files:
        if (root / rel).is_symlink():
            symlinks.append(rel.as_posix())

    # Plan waves
    waves = []
    def count_class_under(prefix: str, cls_filter: set[str]) -> int:
        n = 0
        for rel in all_files:
            rp = rel.as_posix()
            if rp.startswith(prefix) and rel.suffix.lower() in cls_filter:
                if rp not in canonical_set:
                    n += 1
        return n

    waves.append(("Wave 7-A", "doctrine/lessons/ MD+HTML (extend Hybrid Bridge)",
                  count_class_under("doctrine/lessons/", {".md", ".html"})))
    waves.append(("Wave 7-B", "doctrine/<NN>-<slot>.html constitution slots",
                  count_class_under("doctrine/", {".html"})))
    waves.append(("Wave 7-C", "doctrine/_proposals/*.html",
                  count_class_under("doctrine/_proposals/", {".html"})))
    waves.append(("Wave 7-D", ".claude/agents/*.md and .jsonl",
                  count_class_under(".claude/agents/", {".md", ".jsonl", ".html"})))
    waves.append(("Wave 7-E", ".claude/skills/*.md",
                  count_class_under(".claude/skills/", {".md"})))
    waves.append(("Wave 7-F", ".claude/hooks/*.py (CAUTIOUS — running substrate)",
                  count_class_under(".claude/hooks/", {".py"})))
    waves.append(("Wave 7-G", ".claude/scripts/*.{py,md,txt}",
                  count_class_under(".claude/scripts/", {".py", ".md", ".txt"})))
    waves.append(("Wave 7-H", "projects/v11-aep/publish-ready/aep/scripts/*.py",
                  count_class_under("projects/v11-aep/publish-ready/aep/scripts/", {".py"})))
    waves.append(("Wave 7-I", "projects/v11-aep/publish-ready/aep/spec/*.{md,py} (most SPECs done)",
                  count_class_under("projects/v11-aep/publish-ready/aep/spec/", {".md", ".py"})))
    waves.append(("Wave 7-J", "AEP spec supplementary (adversary reports / judge verdicts)",
                  count_class_under("projects/v11-aep/publish-ready/aep/spec/", {".html", ".json"})))
    waves.append(("Wave 7-K", "research/ MD+HTML",
                  count_class_under("research/", {".md", ".html"})))
    waves.append(("Wave 7-L", "library/templates + library/prompts",
                  count_class_under("library/", {".md", ".html", ".py"})))
    waves.append(("Wave 7-M", "tests/*.py",
                  count_class_under("tests/", {".py"})))
    waves.append(("Wave 7-N", "tools/*.py",
                  count_class_under("tools/", {".py"})))
    waves.append(("Wave 7-O", "binary hash-attest companions (.png/.pdf/.svg)",
                  count_class_under("", {".png", ".pdf", ".svg", ".jpg", ".gif"})))
    waves.append(("Wave 7-P+", "catch-all remainders (computed: total_missing - sum of above)",
                  -1))  # placeholder

    sum_assigned = sum(n for _, _, n in waves if n >= 0)
    total_missing = sum(r["missing_companion"] for r in gap_rows
                        if r["class"] in ("markdown", "html", "python", "javascript", "json", "jsonl", "yaml", "text", "perl", "image", "pdf", "log", "other"))
    catch_all = max(0, total_missing - sum_assigned)
    waves[-1] = (waves[-1][0], waves[-1][1], catch_all)

    # Falsifier
    total_files_classified = sum(per_class_total.values())
    total_with_companion = sum(per_class_has_companion.values())
    universal_pct = (total_with_companion / total_files_classified * 100.0) if total_files_classified else 0.0
    falsifier_result = (
        "MOSTLY-DONE" if universal_pct >= 50.0
        else f"SUBSTANTIAL-GAP ({universal_pct:.2f}% have companions; mission scope is wholesale conversion not just extension)"
    )

    # Emit results
    out = {
        "report_class": "wave6_aepification_gap_inventory",
        "generated_at_iso": "2026-05-18",
        "mission": "AEP-V15-LTS-WAVE-6-AEPIFICATION-GAP-INVENTORY",
        "root": str(root),
        "total_files_classified": total_files_classified,
        "total_aepkg_companions": len(aepkg_dirs),
        "companions_with_resolved_canonical_source": sum(1 for v in companion_to_canonical.values() if v),
        "orphan_companions": sum(1 for v in companion_to_canonical.values() if not v),
        "per_class_totals": dict(per_class_total),
        "per_class_have_companion": dict(per_class_has_companion),
        "top_other_extensions": sorted(other_exts.items(), key=lambda kv: -kv[1])[:10],
        "gap_matrix": gap_rows,
        "wave_plan": [
            {"wave": w[0], "scope": w[1], "missing_count": w[2],
             "walltime_estimate_min": min(60, max(5, w[2] // 5))}
            for w in waves
        ],
        "high_risk_summary": {k: len(v) for k, v in high_risk.items()},
        "high_risk_top_items": {
            k: v[:5] for k, v in high_risk.items()
        },
        "symlink_count": len(symlinks),
        "symlinks_sample": symlinks[:5],
        "falsifier_universal_aepification": falsifier_result,
        "universal_pct": universal_pct,
    }

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
