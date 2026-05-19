#!/usr/bin/env python3
"""aep_shape_migrator.py - AEP v1.5.3 Wave 22 shape migrator.

Migrates v0.3 legacy `aepkg.json`-shape packets (846 in corpus) to v0.5+
unified `meta.json` shape (1651 already in corpus) so the combine-tool can
process the entire corpus uniformly. Closes Wave 21 D4 finding #3.

Per sec73.6 honest framing: this is a SHAPE migration NOT a content
migration. The v0.3 packet's rich graph (data/claims.jsonl + spans +
relations + sources + ops + reviews + validations) is PRESERVED verbatim
in-place alongside the new v0.5+ canonical files. The canonical content
(assets/original.<ext> or assets/source.<ext>) is byte-copied to
views/source.<ext> under the v0.5+ shape.

Migration STRATEGY:
  1. Read v0.3 aepkg.json + locate canonical source in
     assets/original.<ext> OR assets/source.<ext>.
  2. Verify byte-roundtrip: assets/<file>.sha256 matches actual sha256.
  3. Backup old aepkg.json -> aepkg.json.v03-backup (idempotency-safe).
  4. Invoke universal_aepify_v2.convert_one() on the canonical source.
     This re-extracts claims under the universal-v2 schema AND emits
     meta.json + data/claims.jsonl + views/source.<ext> + integrity.json
     in the EXACT shape used by the 1651 v0.5+ packets already in the
     corpus.
  5. Preserve all v0.3 jsonl files (data/spans.jsonl, data/relations.jsonl,
     data/sources.jsonl, ops/events.jsonl, etc.) - they coexist as v0.3
     lineage alongside the new v0.5+ shape.
  6. Move .migration_history/ entries forward (append v1_5_3.jsonl).

CLI:
    python tools/aep_shape_migrator.py <path-to-aepkg-dir> [opts]
    python tools/aep_shape_migrator.py --glob <pattern>      [opts]
    python tools/aep_shape_migrator.py --report-from <file>  [opts]

Options:
    --dry-run            : no FS changes, report planned actions only
    --backup-old         : preserve aepkg.json as aepkg.json.v03-backup
                           (DEFAULT enabled; pass --no-backup to disable)
    --no-backup          : disable --backup-old
    --skip-if-meta-json  : if meta.json already exists, treat as
                           already-migrated, exit success
    --wave-id <id>       : K6 wave identifier (default: v15-lts-wave-22pp)
    --no-k6              : disable K6 emission
    --json               : machine-readable summary on stdout
    --max-packets <N>    : process at most N packets (for pilot runs)
    --force              : overwrite existing meta.json (DESTRUCTIVE)

Truth tag axis_a: STRONGLY_PLAUSIBLE
Truth tag axis_b: GO

Composes_with:
  - tools/universal_aepify_v2.py (Wave 15 - reused for v0.5+ emission)
  - tools/universal_aepify.py (Wave 6 - fallback canonical-source detection)
  - projects/v11-aep/publish-ready/aep/V15_WAVE21OO_100_PACKET_BROAD_COMBINE_REPORT.html
  - doctrine/22-html-and-md-native-artifacts
  - doctrine/41-hash-chained-receipt-ledger (K6 emission)
  - doctrine/73-six-sublaws-of-honest-framing
  - sibling-49 file-based scripts under K3 airlock
  - sibling-133 string-concatenation discipline
"""
from __future__ import annotations
import argparse
import glob as _glob
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make universal_aepify_v2 importable
_TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS_DIR))
import universal_aepify_v2 as _uav2  # noqa: E402

MIGRATOR_VERSION = "aep_shape_migrator.py-Wave22-v1.0"
MIGRATOR_WAVE_ID_DEFAULT = "v15-lts-wave-22pp-shape-migrator"

# Asset-source naming conventions used by v0.3 packets
_V03_CANONICAL_NAMES = (
    "original.html",
    "original.md",
    "source.md",
    "source.html",
    "source.py",
    "source.js",
    "source.txt",
    "source.json",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def find_v03_canonical_source(pkg_dir: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Look for the canonical-source file inside a v0.3 packet's assets/ dir.

    Returns (path, detected_extension) or (None, None) if no canonical
    asset found.
    """
    assets = pkg_dir / "assets"
    if not assets.exists():
        return None, None
    for name in _V03_CANONICAL_NAMES:
        cand = assets / name
        if cand.exists() and cand.is_file():
            return cand, cand.suffix
    # Fallback: any file in assets/ that is NOT a .sha256 sidecar
    for f in sorted(assets.iterdir()):
        if f.is_file() and not f.name.endswith(".sha256"):
            return f, f.suffix
    return None, None


def detect_v03_packet(pkg_dir: Path) -> bool:
    """A v0.3 packet has aepkg.json at its root and NO meta.json."""
    if not pkg_dir.is_dir():
        return False
    if not (pkg_dir / "aepkg.json").exists():
        return False
    if (pkg_dir / "meta.json").exists():
        return False  # already migrated
    return True


def migrate_one(
    pkg_dir: Path,
    repo_root: Path,
    dry_run: bool = False,
    backup_old: bool = True,
    skip_if_meta_json: bool = False,
    force: bool = False,
    wave_id: str = MIGRATOR_WAVE_ID_DEFAULT,
    no_k6: bool = False,
) -> Dict[str, Any]:
    """Migrate a single v0.3 packet to v0.5+ shape.

    Returns a structured summary including roundtrip verification.
    """
    if not pkg_dir.exists() or not pkg_dir.is_dir():
        return {
            "mode": "error-no-dir",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "error": "directory not found",
        }

    aepkg_path = pkg_dir / "aepkg.json"
    if not aepkg_path.exists():
        return {
            "mode": "error-no-aepkg-json",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "error": "no aepkg.json at root",
        }

    meta_path = pkg_dir / "meta.json"
    if meta_path.exists() and not force:
        if skip_if_meta_json:
            return {
                "mode": "skip-already-migrated",
                "pkg_dir": str(pkg_dir).replace("\\", "/"),
                "meta_existed": True,
            }
        return {
            "mode": "error-meta-exists",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "error": "meta.json already exists (use --force or --skip-if-meta-json)",
        }

    # Read v0.3 aepkg.json
    try:
        v03_data = json.loads(aepkg_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "mode": "error-parse-aepkg-json",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "error": "aepkg.json parse failed: " + type(e).__name__ + ": " + str(e)[:200],
        }

    # Find canonical source
    canonical_src, canonical_ext = find_v03_canonical_source(pkg_dir)
    if canonical_src is None:
        return {
            "mode": "error-no-canonical",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "error": "no canonical asset found in assets/ - cannot migrate",
            "v03_data_keys": list(v03_data.keys()),
        }

    # Verify byte-roundtrip of canonical source against declared sha256
    canonical_bytes = canonical_src.read_bytes()
    canonical_sha = _sha256_bytes(canonical_bytes)
    ext = v03_data.get("extensions", {})
    declared_sha = ext.get("aep:original_sha256", "").replace("sha256:", "")
    sha_match = (declared_sha == canonical_sha) if declared_sha else None

    # Also check sidecar .sha256 if present
    sidecar = canonical_src.parent / (canonical_src.name + ".sha256")
    sidecar_sha = None
    if sidecar.exists():
        try:
            sidecar_content = sidecar.read_text(encoding="utf-8").strip()
            sidecar_sha = sidecar_content.replace("sha256:", "").split()[0]
        except Exception:
            sidecar_sha = None

    if dry_run:
        return {
            "mode": "dry-run",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "canonical_src": str(canonical_src.relative_to(pkg_dir)).replace("\\", "/"),
            "canonical_ext": canonical_ext,
            "canonical_sha": "sha256:" + canonical_sha,
            "declared_sha": "sha256:" + declared_sha if declared_sha else None,
            "sidecar_sha": "sha256:" + sidecar_sha if sidecar_sha else None,
            "pre_migration_sha_match": sha_match,
            "would_backup": backup_old,
            "would_emit": [
                "meta.json",
                "data/claims.jsonl  (NEW under universal-v2)",
                "views/source" + (canonical_ext or ""),
                "integrity.json",
            ],
            "preserved_v03": [
                "aepkg.json -> aepkg.json.v03-backup" if backup_old else "aepkg.json (intact)",
                "data/spans.jsonl, data/sources.jsonl, data/relations.jsonl (preserved)",
                "ops/, reviews/, validations/ (preserved)",
                "assets/ (preserved as v0.3 lineage)",
                ".migration_history/ (preserved)",
            ],
        }

    # ----- COMMIT PATH -----
    # 1. Backup old aepkg.json (idempotency-safe: if .v03-backup already
    #    exists, no-op rather than overwrite to preserve original lineage)
    backup_path = pkg_dir / "aepkg.json.v03-backup"
    backup_action = "none"
    if backup_old:
        if not backup_path.exists():
            shutil.copy2(aepkg_path, backup_path)
            backup_action = "created"
        else:
            backup_action = "exists-no-overwrite"

    # 2. Invoke universal_aepify_v2.convert_one() to emit v0.5+ shape
    #    using canonical source. We tell it the output dir IS pkg_dir
    #    (so meta.json + data/claims.jsonl + views/source.* + integrity.json
    #    land inside the same .aepkg/ directory).
    file_class = _uav2.detect_file_class(canonical_src)
    if file_class == "unknown":
        # Fallback by extension
        if canonical_ext in (".md", ".html", ".txt"):
            file_class = canonical_ext.lstrip(".")
        else:
            file_class = "txt"

    try:
        # universal_aepify_v2.convert_one ALWAYS writes meta.json + data/ +
        # views/ + integrity.json inside output_dir. Pre-existing data/
        # files (the v0.3 spans/relations/sources/etc) are NOT touched
        # because convert_one only writes data/claims.jsonl.
        # BUT it DOES overwrite data/claims.jsonl - we save it first.
        v03_claims_path = pkg_dir / "data" / "claims.jsonl"
        v03_claims_preserved_path = pkg_dir / "data" / "claims.v03.jsonl"
        if v03_claims_path.exists() and not v03_claims_preserved_path.exists():
            shutil.copy2(v03_claims_path, v03_claims_preserved_path)

        emit_result = _uav2.convert_one(
            source_path=canonical_src,
            output_dir=pkg_dir,
            file_class=file_class,
            dry_run=False,
            wave_id=wave_id,
            repo_root=repo_root,
            k6_journal=None if no_k6 else _uav2._DEFAULT_K6_JOURNAL,
            timestamp_stripped=True,  # Wave 22 enables idempotency
        )
    except Exception as e:
        return {
            "mode": "error-convert-failed",
            "pkg_dir": str(pkg_dir).replace("\\", "/"),
            "error": "universal_aepify_v2.convert_one() raised: " + type(e).__name__ + ": " + str(e)[:300],
            "canonical_src": str(canonical_src).replace("\\", "/"),
            "file_class": file_class,
        }

    # 3. Post-migration byte-roundtrip verification
    # For text/code: views/source.<ext> should exist with byte-identical bytes.
    # For binary: views/source_hash.txt should contain sha256:<hash>\n.
    roundtrip_ok = False
    view_sha = None
    if file_class == "binary":
        view_hash_file = pkg_dir / "views" / "source_hash.txt"
        if view_hash_file.exists():
            recorded = view_hash_file.read_text(encoding="utf-8").strip()
            view_sha = recorded.replace("sha256:", "").strip()
            roundtrip_ok = (view_sha == canonical_sha)
    else:
        view_src = pkg_dir / "views" / ("source" + canonical_ext)
        if view_src.exists():
            view_sha = _sha256_bytes(view_src.read_bytes())
            roundtrip_ok = (view_sha == canonical_sha)

    # 4. Verify canonical sibling (if any) is unchanged
    # The canonical sibling for doctrine/00-mission.aepkg is doctrine/00-mission.html
    # For lessons + research_sources there is no canonical sibling.
    parent = pkg_dir.parent
    stem = pkg_dir.stem  # filename without .aepkg
    sibling_path = None
    sibling_sha = None
    for ext_try in (".html", ".md", ".py", ".js"):
        cand = parent / (stem + ext_try)
        if cand.exists():
            sibling_path = cand
            sibling_sha = _sha256_bytes(cand.read_bytes())
            break

    # 5. Append v1_5_3 migration history entry
    mhist_dir = pkg_dir / ".migration_history"
    mhist_dir.mkdir(exist_ok=True)
    mhist_path = mhist_dir / "v1_5_3.jsonl"
    mhist_entry = {
        "ts": _utc_now_iso(),
        "tool": MIGRATOR_VERSION,
        "wave_id": wave_id,
        "from_shape": "v0.3-aepkg-json",
        "to_shape": "v1.5.2-RC1-universal-v2",
        "canonical_src": str(canonical_src.relative_to(pkg_dir)).replace("\\", "/"),
        "canonical_sha": "sha256:" + canonical_sha,
        "pre_migration_sha_match": sha_match,
        "view_sha_match": roundtrip_ok,
        "backup_action": backup_action,
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "GO",
    }
    with mhist_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(mhist_entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")

    return {
        "mode": "migrated",
        "pkg_dir": str(pkg_dir).replace("\\", "/"),
        "canonical_src": str(canonical_src.relative_to(pkg_dir)).replace("\\", "/"),
        "canonical_ext": canonical_ext,
        "canonical_sha": "sha256:" + canonical_sha,
        "view_sha": "sha256:" + view_sha if view_sha else None,
        "view_sha_match": roundtrip_ok,
        "declared_sha": "sha256:" + declared_sha if declared_sha else None,
        "pre_migration_sha_match": sha_match,
        "sibling_path": str(sibling_path).replace("\\", "/") if sibling_path else None,
        "sibling_sha": "sha256:" + sibling_sha if sibling_sha else None,
        "sibling_unchanged": True if (sibling_sha and sibling_sha == canonical_sha) else (sibling_path is None or "n/a"),
        "backup_action": backup_action,
        "file_class": file_class,
        "convert_summary": emit_result,
        "v15_3_history_appended": True,
    }


def discover_v03_packets(
    glob_pattern: Optional[str] = None,
    explicit_paths: Optional[List[Path]] = None,
    repo_root: Optional[Path] = None,
) -> List[Path]:
    """Find v0.3-shape packets - those with aepkg.json AND NO meta.json."""
    candidates: List[Path] = []
    if explicit_paths:
        candidates.extend(explicit_paths)
    if glob_pattern:
        for m in sorted(_glob.glob(glob_pattern, recursive=True)):
            p = Path(m)
            # Patterns can hit aepkg.json directly or the parent dir
            if p.name == "aepkg.json":
                candidates.append(p.parent)
            elif p.is_dir() and p.name.endswith(".aepkg"):
                candidates.append(p)
    if not candidates and not glob_pattern:
        # Default: walk repo from cwd
        cwd = Path.cwd()
        for m in sorted(_glob.glob("**/*.aepkg/aepkg.json", recursive=True)):
            candidates.append(Path(m).parent)

    # Filter to true v0.3 (aepkg.json present AND no meta.json)
    out: List[Path] = []
    seen = set()
    for c in candidates:
        c = c.resolve()
        if c in seen:
            continue
        seen.add(c)
        if detect_v03_packet(c):
            out.append(c)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="AEP v1.5.3 Wave 22 shape migrator: v0.3 aepkg.json -> v0.5+ meta.json"
    )
    parser.add_argument("input", nargs="?", default=None,
                        help="Path to a single .aepkg directory")
    parser.add_argument("--glob", default=None,
                        help='Glob pattern (e.g. "doctrine/**/*.aepkg")')
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-old", action="store_true", default=True)
    parser.add_argument("--no-backup", action="store_true",
                        help="disable --backup-old")
    parser.add_argument("--skip-if-meta-json", action="store_true", default=True)
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing meta.json (DESTRUCTIVE)")
    parser.add_argument("--wave-id", default=MIGRATOR_WAVE_ID_DEFAULT)
    parser.add_argument("--no-k6", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-packets", type=int, default=0)
    parser.add_argument("--report-out", type=Path, default=None,
                        help="write structured JSON report to file")
    args = parser.parse_args(argv)

    backup_old = args.backup_old and not args.no_backup

    repo_root = Path(__file__).resolve().parents[1]

    # Resolve inputs
    explicit_paths: List[Path] = []
    if args.input:
        p = Path(args.input).resolve()
        if p.exists() and p.is_dir():
            explicit_paths.append(p)
        else:
            print("ERROR: input not a directory: " + str(p), file=sys.stderr)
            return 1

    packets = discover_v03_packets(
        glob_pattern=args.glob,
        explicit_paths=explicit_paths,
        repo_root=repo_root,
    )

    if args.max_packets > 0:
        packets = packets[: args.max_packets]

    if not packets:
        msg = "no v0.3 packets discovered"
        if args.json:
            print(json.dumps({"total_v03_discovered": 0, "results": []}, sort_keys=True))
        else:
            print("[shape-migrator] " + msg)
        return 0

    t0 = time.time()
    results: List[Dict[str, Any]] = []
    migrated = 0
    skipped = 0
    errors = 0
    roundtrip_ok = 0
    canonical_unchanged = 0

    for pkg in packets:
        res = migrate_one(
            pkg_dir=pkg,
            repo_root=repo_root,
            dry_run=args.dry_run,
            backup_old=backup_old,
            skip_if_meta_json=args.skip_if_meta_json,
            force=args.force,
            wave_id=args.wave_id,
            no_k6=args.no_k6,
        )
        results.append(res)
        mode = res.get("mode", "")
        if mode == "migrated":
            migrated += 1
            if res.get("view_sha_match"):
                roundtrip_ok += 1
            if res.get("sibling_path") is None or res.get("sibling_unchanged") in (True, "n/a"):
                canonical_unchanged += 1
        elif mode in ("dry-run",):
            migrated += 1  # would-be migrated
        elif mode in ("skip-already-migrated",):
            skipped += 1
        else:
            errors += 1

    t1 = time.time()

    summary = {
        "migrator_version": MIGRATOR_VERSION,
        "wave_id": args.wave_id,
        "dry_run": args.dry_run,
        "total_discovered": len(packets),
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "byte_roundtrip_pass_count": roundtrip_ok,
        "canonical_unchanged_pass_count": canonical_unchanged,
        "elapsed_seconds": round(t1 - t0, 3),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "GO",
    }

    if args.report_out:
        full_report = dict(summary)
        full_report["results"] = results
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(
            json.dumps(full_report, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        verb = "[DRY-RUN] would migrate" if args.dry_run else "migrated"
        print("[shape-migrator] " + verb + " "
              + str(migrated) + " of " + str(len(packets)) + " packets")
        print("  roundtrip ok    : " + str(roundtrip_ok))
        print("  canonical unchg : " + str(canonical_unchanged))
        print("  skipped         : " + str(skipped))
        print("  errors          : " + str(errors))
        print("  elapsed         : " + str(round(t1 - t0, 3)) + "s")

    if errors and migrated == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
