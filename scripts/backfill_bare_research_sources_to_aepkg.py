"""backfill_bare_research_sources_to_aepkg.py — convert legacy
research/sources/<slug>/source.html bare-pattern directories into the
new auto-AEP companion form research/sources/<slug>.aepkg/.

Per operator's 2026-05-16 auto-AEP rule (codified in doctrine/64 candidate
slot), every absorbed source must live as an .aepkg/ packet. Legacy
artifacts that pre-date the rule live as bare directories with a single
source.html. This helper preserves the .html VERBATIM in assets/source.html
and emits the manifest + canonical files per the new convention.

DRY-RUN by default. The destructive --apply path requires explicit operator
approval per doctrine/59 governance owner-completeness; this script will
generate companion .aepkg/ directories but does NOT delete the legacy
bare directories. Operator decides removal in a separate gate.

Cites:
  pathfinder §64 doctrine slot (auto-AEP rule canonicalization).
  scribe sibling-90 (the operator-drop pattern + idempotency invariants).
  adversary huddle-wave-2 pre-mortem attack B1 (schema-drift across 4
    capture paths) and B3 (hallucinated-source-citations during backfill).

Usage:
  # Dry-run (default): scan + report only, no mutations.
  python backfill_bare_research_sources_to_aepkg.py

  # Apply (destructive write of new .aepkg/ companions; bare dirs preserved):
  python backfill_bare_research_sources_to_aepkg.py --apply

  # Limit to a single slug:
  python backfill_bare_research_sources_to_aepkg.py \\
    --target-slug operator-2026-05-15-goal-anti-immune-system-verdict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Local import — same scripts/ directory.
sys.path.insert(0, str(Path(__file__).parent))
from capture_absorbed_content_to_aepkg import capture_absorbed  # noqa: E402

REPO_ROOT = Path("C:/Users/example-user/")
RESEARCH_SOURCES = REPO_ROOT / "research" / "sources"

# Regex matches:
#   operator-YYYY-MM-DD-<slug>
#   external-prior-art-<slug>-YYYY-MM-DD
#   external-<source-type>-<slug>-YYYY-MM-DD
_OPERATOR_RE = re.compile(r"^operator-(\d{4}-\d{2}-\d{2})-(.+)$")
_EXTERNAL_PRIOR_ART_RE = re.compile(
    r"^external-prior-art-(.+?)-(\d{4}-\d{2}-\d{2})$")


def classify_bare_dir(dirname: str) -> tuple[str, str, Optional[str]]:
    """Map a bare-dir name to (source_type, slug, drop_date).

    Returns ('unknown', dirname, None) when neither convention matches.
    """
    m = _OPERATOR_RE.match(dirname)
    if m:
        return "operator-drop", m.group(2), m.group(1)
    m = _EXTERNAL_PRIOR_ART_RE.match(dirname)
    if m:
        return "external-prior-art", m.group(1), m.group(2)
    return "unknown", dirname, None


def find_bare_pattern_dirs() -> list[Path]:
    """Find research/sources/* that are bare directories (NOT .aepkg/).

    A directory qualifies as the bare-pattern legacy form when:
      - the name does NOT end in .aepkg
      - it contains exactly one file: source.html (or source.md / .txt)
      - it has no aepkg.json
    """
    out = []
    if not RESEARCH_SOURCES.is_dir():
        return out
    for child in sorted(RESEARCH_SOURCES.iterdir()):
        if not child.is_dir():
            continue
        if child.name.endswith(".aepkg"):
            continue
        # Already-companioned check: does <slug>.aepkg/ already exist?
        companion = RESEARCH_SOURCES / f"{child.name}.aepkg"
        if companion.exists():
            continue
        # Detect the canonical source file inside.
        candidates = [child / f"source.{ext}"
                      for ext in ("html", "md", "txt")]
        candidates = [c for c in candidates if c.exists()]
        if not candidates:
            continue
        out.append(child)
    return out


def plan_backfill_one(bare_dir: Path) -> dict:
    """Build a deterministic plan record for one bare-pattern dir."""
    source_type, slug, drop_date = classify_bare_dir(bare_dir.name)
    # Find canonical source file (prefer .html > .md > .txt to match priors).
    source_file = None
    for ext in ("html", "md", "txt"):
        candidate = bare_dir / f"source.{ext}"
        if candidate.exists():
            source_file = candidate
            break
    if source_file is None:
        return {
            "bare_dir": str(bare_dir.relative_to(REPO_ROOT)),
            "status": "skip-no-canonical-source",
        }
    content_bytes = source_file.read_bytes()
    content_sha = hashlib.sha256(content_bytes).hexdigest()
    ext = source_file.suffix.lstrip(".").lower()
    target_pkg = RESEARCH_SOURCES / f"{bare_dir.name}.aepkg"
    return {
        "bare_dir": str(bare_dir.relative_to(REPO_ROOT)),
        "source_type": source_type,
        "slug": slug,
        "operator_drop_date": drop_date,
        "canonical_source": str(source_file.relative_to(REPO_ROOT)),
        "canonical_source_sha256": "sha256:" + content_sha,
        "canonical_source_bytes": len(content_bytes),
        "canonical_source_ext": ext,
        "target_pkg": str(target_pkg.relative_to(REPO_ROOT)),
        "target_pkg_already_exists": target_pkg.exists(),
        "status": "ready" if not target_pkg.exists() else "already-companioned",
    }


def derive_title(bare_dir: Path, source_file: Path) -> str:
    """Best-effort title extraction.

    For .html: pull <title>...</title> if present; else the bare dir name.
    For .md: first '# ' heading; else dir name.
    """
    try:
        content = source_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return bare_dir.name
    if source_file.suffix.lower() == ".html":
        m = re.search(r"<title>(.+?)</title>", content,
                      flags=re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    elif source_file.suffix.lower() == ".md":
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line.lstrip("# ").strip()
    return bare_dir.name


def apply_backfill_one(plan: dict, session_id: Optional[str]) -> dict:
    """Execute backfill for one bare-pattern dir per the plan."""
    if plan.get("status") != "ready":
        return {"plan": plan, "executed": False, "reason": plan.get("status")}
    bare_dir = REPO_ROOT / plan["bare_dir"]
    source_file = REPO_ROOT / plan["canonical_source"]
    content = source_file.read_text(encoding="utf-8")
    title = derive_title(bare_dir, source_file)
    pkg, was_noop = capture_absorbed(
        content=content,
        ext=plan["canonical_source_ext"],
        source_type=plan["source_type"],
        slug=plan["slug"],
        title=title,
        target_root=RESEARCH_SOURCES,
        drop_date=plan["operator_drop_date"],
        # Default to anti-source-laundering=true for legacy operator drops
        # (matches the convention used in operator-2026-05-16-grill-with-docs).
        anti_source_laundering_preserved=True,
        # Legacy bare pattern predates GPT-synthesizer two-stage pattern;
        # default false. Operator can override via a per-packet edit.
        gpt_synthesizer_pre_processed=False,
        session_id=session_id or "backfill-bare-research-sources",
        silent=True,
    )
    return {
        "plan": plan,
        "executed": True,
        "was_noop": was_noop,
        "packet_path": str(pkg.relative_to(REPO_ROOT)),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Execute the backfill. Default is DRY-RUN (report only).")
    ap.add_argument("--target-slug", default=None,
                    help="Limit to a single legacy slug (otherwise all bare dirs "
                         "under research/sources/).")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--json", action="store_true",
                    help="Emit machine-readable JSON report instead of human-text.")
    args = ap.parse_args()

    bare_dirs = find_bare_pattern_dirs()
    if args.target_slug:
        bare_dirs = [d for d in bare_dirs if d.name == args.target_slug]

    plans = [plan_backfill_one(d) for d in bare_dirs]
    ready = [p for p in plans if p.get("status") == "ready"]
    skipped = [p for p in plans if p.get("status") != "ready"]

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "scanned_at": datetime.now(tz=timezone.utc).isoformat(
            timespec="seconds").replace("+00:00", "Z"),
        "bare_dirs_found": len(bare_dirs),
        "ready_count": len(ready),
        "skipped_count": len(skipped),
        "plans": plans,
        "executed": [],
    }

    if args.apply:
        for plan in ready:
            result = apply_backfill_one(plan, session_id=args.session_id)
            report["executed"].append(result)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(f"# backfill_bare_research_sources_to_aepkg.py [{report['mode']}]")
    print(f"# scanned_at: {report['scanned_at']}")
    print(f"# bare-pattern dirs found: {report['bare_dirs_found']}")
    print(f"# ready to backfill: {report['ready_count']}")
    print(f"# skipped: {report['skipped_count']}")
    print()
    for plan in plans:
        status = plan.get("status", "?")
        bare = plan.get("bare_dir", "?")
        target = plan.get("target_pkg", "?")
        sha = plan.get("canonical_source_sha256", "?")
        nbytes = plan.get("canonical_source_bytes", 0)
        print(f"  [{status}] {bare}")
        print(f"    -> {target}")
        print(f"    sha256={sha} bytes={nbytes}")
    if args.apply:
        print()
        print(f"# executed: {len(report['executed'])} backfills")
        for r in report["executed"]:
            tag = "noop" if r.get("was_noop") else "wrote"
            print(f"  [{tag}] {r.get('packet_path', '?')}")
    else:
        print()
        print("# DRY-RUN. To execute, re-run with --apply. Per doctrine/59 "
              "governance owner-completeness, destructive backfill requires "
              "operator approval.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
