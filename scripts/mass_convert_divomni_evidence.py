"""Mass-convert AEP project evidence-content HTML files to AEP packets.

Scope (defensible per AEP v0.7.1 Pareto matrix 15.5/16 for evidence-packet use-case):
  - doctrine/lessons/*.html            (lesson records with truth tags + basis)
  - research/analysis/**/analysis.html (the agent syntheses with claim ledgers)
  - research/sources/**/source.html    (operator drops with provenance)
  - doctrine/_proposals/*.html         (staged proposals with truth tags)

NOT in scope (would lose dim 12 hand-authoring + dim 10 prose):
  - CLAUDE.md / README.md (operator-facing prose)
  - doctrine/00-mission.html etc. (canonical-doctrine prose)
  - Build configs, scripts

Each converted packet is placed next to the original as `<name>.aepkg/`. The
original HTML is preserved (zero workflow breakage). The AEP packet adds the
integrity layer + cross-runtime verifiable form.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

AEP_ROOT = Path(__file__).resolve().parents[5]
AEP_PROJECT = Path(__file__).resolve().parents[1]

# Convert tiers (in this priority order):
TIERS = [
    ("lessons",       AEP_ROOT / "doctrine" / "lessons",       "*.html"),
    ("analyses",      AEP_ROOT / "research" / "analysis",      "**/analysis.html"),
    ("sources",       AEP_ROOT / "research" / "sources",       "**/source.html"),
    ("proposals",     AEP_ROOT / "doctrine" / "_proposals",    "*.html"),
]


def is_index_or_template(p: Path) -> bool:
    """Skip non-content files: _index.html, templates, etc."""
    name = p.name
    if name.startswith("_") and name.endswith("_index.html"):
        return True
    if name in ("_index.html", "template.html"):
        return True
    return False


def convert_one(src: Path, out_dir: Path) -> tuple[bool, str]:
    """Convert single HTML to AEP packet. Returns (success, message)."""
    if out_dir.exists():
        # Already converted; skip unless --force
        return True, "already-converted (skipped)"
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "aep.convert_html_lesson",
                str(src), str(out_dir), "--force",
            ],
            cwd=AEP_PROJECT,
            env={
                "PYTHONPATH": str(AEP_PROJECT / "src"),
                **{k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"},
            },
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False, f"converter exit {result.returncode}: {result.stderr[:200]}"
        # Parse counts from stdout
        for line in result.stdout.splitlines():
            if line.startswith("Counts:"):
                return True, line.strip()
        return True, "converted (no counts line)"
    except subprocess.TimeoutExpired:
        return False, "converter timeout (60s)"
    except Exception as exc:
        return False, f"exception: {exc}"


def main():
    overall_start = time.perf_counter()
    grand_total = 0
    grand_success = 0
    grand_fail = 0
    grand_skip = 0
    failures: list[tuple[str, str, str]] = []  # (tier, path, reason)

    for tier_name, base_dir, pattern in TIERS:
        if not base_dir.exists():
            print(f"\n[{tier_name}] base dir missing: {base_dir}")
            continue
        files = list(base_dir.glob(pattern))
        files = [f for f in files if f.is_file() and not is_index_or_template(f)]
        print(f"\n[{tier_name}] {len(files)} files at {base_dir}")
        tier_start = time.perf_counter()
        for i, src in enumerate(files, 1):
            out_dir = src.with_suffix("") if src.suffix == ".html" else src.parent / (src.stem + ".aepkg")
            # convert_html_lesson expects output dir to be name.aepkg
            out_dir = src.parent / (src.stem + ".aepkg") if not src.stem.endswith(".aepkg") else src.parent / src.stem
            ok, msg = convert_one(src, out_dir)
            grand_total += 1
            if ok:
                if "skipped" in msg:
                    grand_skip += 1
                else:
                    grand_success += 1
            else:
                grand_fail += 1
                failures.append((tier_name, str(src.relative_to(AEP_ROOT)), msg))
            if i % 20 == 0 or i == len(files):
                elapsed = time.perf_counter() - tier_start
                rate = i / elapsed if elapsed > 0 else 0
                print(f"  [{tier_name}] {i}/{len(files)} ({rate:.1f} files/s, success={grand_success}, fail={grand_fail}, skip={grand_skip})")

    overall_elapsed = time.perf_counter() - overall_start
    print()
    print(f"{'='*60}")
    print(f"MASS-CONVERSION COMPLETE in {overall_elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"Total:       {grand_total}")
    print(f"Success:     {grand_success}")
    print(f"Skipped:     {grand_skip} (already-converted)")
    print(f"Failed:      {grand_fail}")
    if failures:
        print(f"\nFAILURES (top 20):")
        for tier, path, reason in failures[:20]:
            print(f"  [{tier}] {path}: {reason}")
    print()
    # Output a manifest for downstream tools
    summary = {
        "grand_total": grand_total,
        "success": grand_success,
        "skipped": grand_skip,
        "failed": grand_fail,
        "elapsed_seconds": round(overall_elapsed, 1),
        "tiers": [t[0] for t in TIERS],
        "failures": failures[:50],
    }
    out = AEP_PROJECT.parent.parent / "mass-conversion-summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Summary written to {out}")


if __name__ == "__main__":
    main()
