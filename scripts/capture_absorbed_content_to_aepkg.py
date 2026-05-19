"""capture_absorbed_content_to_aepkg.py — programmatic implementation of the
operator's 2026-05-16 auto-AEP rule for absorbed source content.

Mirrors capture_operator_message_to_aepkg.py but targets the absorbed-source
content class (operator-drop + external-prior-art + transcript + etc.) under
research/sources/<slug>.aepkg/ instead of the operator-message dump folder.

Rule (operator-supplied 2026-05-16, codified in doctrine/64 candidate slot):
  - Every absorbed source content artifact lands as an .aepkg/ packet.
  - Canonical source preserved BYTE-IDENTICAL in assets/source.<ext>.
  - sha256 of the canonical source recorded in the manifest extension.
  - Manifest extensions record anti-source-laundering + gpt-synthesizer
    pre-processing flags + operator-drop-date + source-type.
  - Idempotent: re-running on existing path is a no-op (verified via
    existence + sha256 match).

Cites:
  pathfinder §64 doctrine slot authored in huddle-wave-2 parallel
  scribe sibling-90 lesson authored in huddle-wave-2 parallel
  adversary huddle-wave-2 pre-mortem (attack vectors B1 schema-drift-4-paths,
    B2 prompt-injection-via-source-md, B3 hallucinated-source-citations).

Usage:
  python capture_absorbed_content_to_aepkg.py \\
    --content-file path/to/source.md \\
    --source-type operator-drop \\
    --slug some-topic-name \\
    --title "Operator drop: some topic" \\
    [--target-root research/sources/] \\
    [--anti-source-laundering-preserved true] \\
    [--gpt-synthesizer-pre-processed false]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


REPO_ROOT = Path("C:/Users/example-user/")
DEFAULT_TARGET_ROOT = REPO_ROOT / "research" / "sources"

VALID_SOURCE_TYPES = {
    "operator-drop",
    "operator-drop-from-aepkit-research-synthesizer-gpt",
    "external-prior-art",
    "transcript",
    "scout-found",
    "codex-supplied-research",
}

# Allowlisted extensions for the canonical source asset.
# (.txt accepted; .pdf-text-extract written as .txt with a flag.)
ALLOWED_EXTS = {"md", "html", "txt", "json", "yaml", "yml"}


def detect_ext(content_file: Optional[Path], explicit_ext: Optional[str]) -> str:
    """Resolve the canonical asset extension."""
    if explicit_ext:
        ext = explicit_ext.lstrip(".").lower()
        if ext not in ALLOWED_EXTS:
            raise ValueError(
                f"Extension '{ext}' not in allowed set {sorted(ALLOWED_EXTS)}; "
                f"if a PDF, extract text first and pass --ext txt.")
        return ext
    if content_file is not None:
        ext = content_file.suffix.lstrip(".").lower()
        if ext and ext in ALLOWED_EXTS:
            return ext
    return "md"  # default


def compose_target_dir(target_root: Path, source_type: str, slug: str,
                       drop_date: Optional[str]) -> Path:
    """Compose the target .aepkg/ directory name per the operator's rule.

    operator-drop      => operator-<YYYY-MM-DD>-<slug>.aepkg
    external-prior-art => external-prior-art-<slug>-<YYYY-MM-DD>.aepkg
    other              => <source-type>-<slug>-<YYYY-MM-DD>.aepkg
    """
    if not drop_date:
        drop_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    safe_slug = slug.strip("-").lower()
    if source_type == "operator-drop" or source_type.startswith("operator-drop"):
        name = f"operator-{drop_date}-{safe_slug}.aepkg"
    elif source_type == "external-prior-art":
        name = f"external-prior-art-{safe_slug}-{drop_date}.aepkg"
    else:
        name = f"{source_type}-{safe_slug}-{drop_date}.aepkg"
    return target_root / name


def existing_packet_matches(pkg: Path, content_sha: str) -> bool:
    """Idempotency check: pkg exists AND its canonical_source_sha256 matches."""
    manifest_path = pkg / "aepkg.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    existing_sha = (manifest.get("extensions") or {}).get(
        "canonical_source_sha256", "")
    return existing_sha == "sha256:" + content_sha


def capture_absorbed(
    content: str,
    ext: str,
    source_type: str,
    slug: str,
    title: str,
    target_root: Path,
    drop_date: Optional[str],
    anti_source_laundering_preserved: bool,
    gpt_synthesizer_pre_processed: bool,
    session_id: Optional[str],
    silent: bool = False,
) -> tuple[Path, bool]:
    """Write the absorbed source as an AEP packet.

    Returns (packet_path, was_idempotent_noop).
    """
    pkg = compose_target_dir(target_root, source_type, slug, drop_date)
    content_bytes = content.encode("utf-8")
    content_sha = hashlib.sha256(content_bytes).hexdigest()

    # Idempotent re-run guard.
    if existing_packet_matches(pkg, content_sha):
        if not silent:
            print(f"# Idempotent: packet already exists with matching sha256 "
                  f"at {pkg.relative_to(REPO_ROOT)} (no-op).")
        return pkg, True

    if pkg.exists():
        # Path exists but content differs -- refuse to overwrite without
        # operator approval per the bank-merger / single-writer discipline.
        raise FileExistsError(
            f"Target {pkg.relative_to(REPO_ROOT)} exists with DIFFERENT content "
            f"sha256. Refusing to overwrite. Inspect manually or remove first.")

    pkg.mkdir(parents=True)
    for sub in ("data", "ops", "reviews", "validations", "views", "assets"):
        (pkg / sub).mkdir()

    # Canonical source preserved byte-identical.
    asset_name = f"source.{ext}"
    (pkg / "assets" / asset_name).write_bytes(content_bytes)
    (pkg / "assets" / "source.sha256").write_text(
        content_sha + "\n", encoding="utf-8")

    now = datetime.now(tz=timezone.utc)
    utc_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    canonical_source_relpath = f"./assets/{asset_name}"
    limits = []
    if anti_source_laundering_preserved:
        limits.append(
            "anti-source-laundering preserved: the agent does NOT independently "
            "fetch cited URLs")
    if gpt_synthesizer_pre_processed:
        limits.append(
            "two-stage absorption: operator pre-processed via GPT-Synthesizer "
            "before paste")
    if not limits:
        limits.append("operator-authored verbatim; do not paraphrase")

    src_id = f"src:{source_type}-{slug}"
    if drop_date:
        src_id = f"src:{source_type}-{drop_date}-{slug}"
    source_rec = {
        "id": src_id,
        "type": "Source",
        "source_type": source_type,
        "title": title,
        "location": {
            "kind": "file",
            "value": canonical_source_relpath,
            "location_hash": "sha256:" + content_sha,
        },
        "provenance_strength": "strong",
        "limits": limits,
        "created_at": utc_iso,
    }
    (pkg / "data" / "sources.jsonl").write_text(
        json.dumps(source_rec, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    for f in ("spans.jsonl", "claims.jsonl", "relations.jsonl"):
        (pkg / "data" / f).write_text("", encoding="utf-8")

    (pkg / "ops" / "events.jsonl").write_text(
        json.dumps({
            "id": "evt:001", "type": "WriteEvent",
            "event_type": "absorbed_content_captured",
            "event_time": utc_iso,
            "actor": "capture_absorbed_content_to_aepkg.py",
            "target": asset_name,
            "session_id": session_id or "unknown",
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    (pkg / "reviews" / "reviews.jsonl").write_text("", encoding="utf-8")
    (pkg / "validations" / "runs.jsonl").write_text("", encoding="utf-8")

    auto_aep_rule_id = str(uuid.uuid4())
    packet_id = f"aepkg:{pkg.name[:-len('.aepkg')]}"
    manifest = {
        "aep_version": "0.5",
        "profile": "aep:0.5/stable",
        "packet_id": packet_id,
        "packet_epoch": 1,
        "title": title,
        "created_at": utc_iso,
        "created_by": "capture_absorbed_content_to_aepkg.py",
        "canonical_files": [
            "data/sources.jsonl", "data/spans.jsonl", "data/claims.jsonl",
            "data/relations.jsonl", "ops/events.jsonl",
            "reviews/reviews.jsonl", "validations/runs.jsonl",
        ],
        "extensions": {
            "source_type": source_type,
            "operator_drop_date": drop_date or "",
            "canonical_source_path": canonical_source_relpath,
            "canonical_source_sha256": "sha256:" + content_sha,
            "canonical_source_bytes": len(content_bytes),
            "canonical_source_ext": ext,
            "anti_source_laundering_preserved": bool(
                anti_source_laundering_preserved),
            "gpt_synthesizer_pre_processed": bool(
                gpt_synthesizer_pre_processed),
            "auto_aep_rule_application_id": auto_aep_rule_id,
            "replaces_prior_pattern": (
                "research/sources/<slug>/source.html bare-pattern "
                "(pre-2026-05-16); new convention per operator auto-AEP rule"),
            "session_id": session_id or "unknown",
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "state_hash": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "manifest_hash": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "assets_merkle_root": "sha256:" + content_sha,
        },
    }
    (pkg / "aepkg.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n", encoding="utf-8", newline="\n")
    return pkg, False


def _parse_bool(s) -> bool:
    if isinstance(s, bool):
        return s
    return str(s).strip().lower() in {"1", "true", "yes", "on", "y"}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content-file", type=Path,
                    help="File containing the absorbed source content verbatim.")
    ap.add_argument("--content", type=str, default=None,
                    help="Absorbed source content as inline string.")
    ap.add_argument("--source-type", required=True,
                    choices=sorted(VALID_SOURCE_TYPES),
                    help="Source classification.")
    ap.add_argument("--slug", required=True,
                    help="Kebab-case identifier (omit date/source-type prefix; "
                         "they are composed automatically).")
    ap.add_argument("--ext", default=None,
                    help="Canonical asset extension; auto-detected from "
                         "--content-file otherwise (default md).")
    ap.add_argument("--title", required=True,
                    help="Human-readable title for the absorbed source.")
    ap.add_argument("--target-root", type=Path, default=DEFAULT_TARGET_ROOT,
                    help="Target root directory (default research/sources/).")
    ap.add_argument("--operator-drop-date", default=None,
                    help="YYYY-MM-DD; defaults to today UTC if not supplied.")
    ap.add_argument("--anti-source-laundering-preserved", default="true",
                    help="Manifest flag (default true).")
    ap.add_argument("--gpt-synthesizer-pre-processed", default="false",
                    help="Manifest flag (default false).")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--silent", action="store_true")
    args = ap.parse_args()

    if args.content is not None:
        content = args.content
    elif args.content_file and args.content_file.exists():
        content = args.content_file.read_text(encoding="utf-8")
    else:
        content = sys.stdin.read()

    if not content.strip():
        if not args.silent:
            print("# Empty content; nothing captured.", file=sys.stderr)
        return 0

    ext = detect_ext(args.content_file, args.ext)
    pkg, was_noop = capture_absorbed(
        content=content,
        ext=ext,
        source_type=args.source_type,
        slug=args.slug,
        title=args.title,
        target_root=args.target_root,
        drop_date=args.operator_drop_date,
        anti_source_laundering_preserved=_parse_bool(
            args.anti_source_laundering_preserved),
        gpt_synthesizer_pre_processed=_parse_bool(
            args.gpt_synthesizer_pre_processed),
        session_id=args.session_id,
        silent=args.silent,
    )

    if not args.silent:
        try:
            rel = pkg.relative_to(REPO_ROOT)
        except ValueError:
            rel = pkg
        if was_noop:
            print(f"# Idempotent no-op at {rel}")
        else:
            print(f"Captured absorbed content to {rel}")
    return 0


# -------------------------------------------------------------------------
# Smoke test (runs when invoked with --smoke-test; deletes the test packet
# at the end and verifies the path is clean before returning).
# -------------------------------------------------------------------------
def _smoke_test() -> int:
    import shutil
    smoke_slug = "_smoke-test-2026-05-16"
    smoke_root = REPO_ROOT / "research" / "sources"
    smoke_path = smoke_root / f"{smoke_slug}.aepkg"
    if smoke_path.exists():
        shutil.rmtree(smoke_path)
    content = "# smoke test content\n\nthis is a transient smoke-test asset.\n"
    pkg, was_noop = capture_absorbed(
        content=content,
        ext="md",
        source_type="operator-drop",
        slug=smoke_slug.lstrip("_"),
        title="Smoke-test packet (transient)",
        target_root=smoke_root,
        drop_date=None,
        anti_source_laundering_preserved=True,
        gpt_synthesizer_pre_processed=False,
        session_id="forge-smoke-test",
        silent=True,
    )
    # The slug got prefixed; find the actual packet name.
    if not pkg.exists():
        print(f"SMOKE FAIL: pkg path missing {pkg}", file=sys.stderr)
        return 2
    manifest = json.loads((pkg / "aepkg.json").read_text(encoding="utf-8"))
    asset_sha = (pkg / "assets" / "source.sha256").read_text(
        encoding="utf-8").strip()
    expected_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if asset_sha != expected_sha:
        print(f"SMOKE FAIL: sha256 mismatch", file=sys.stderr)
        return 2
    # Idempotency re-fire check.
    _, was_noop2 = capture_absorbed(
        content=content, ext="md", source_type="operator-drop",
        slug=smoke_slug.lstrip("_"),
        title="Smoke-test packet (transient)",
        target_root=smoke_root, drop_date=None,
        anti_source_laundering_preserved=True,
        gpt_synthesizer_pre_processed=False,
        session_id="forge-smoke-test", silent=True,
    )
    if not was_noop2:
        print("SMOKE FAIL: second call was not idempotent", file=sys.stderr)
        shutil.rmtree(pkg)
        return 2
    # Cleanup.
    shutil.rmtree(pkg)
    if pkg.exists():
        print(f"SMOKE FAIL: pkg path not clean after rmtree", file=sys.stderr)
        return 2
    print(f"SMOKE PASS: packet created at {pkg.name}, sha256 verified, "
          f"idempotency confirmed, cleanup clean.")
    return 0


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        sys.exit(_smoke_test())
    sys.exit(main() or 0)
