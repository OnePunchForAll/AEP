"""convert_existing_skills_to_aep.py — operator directive 2026-05-15:
"if not i think we should be giving each claude main agent a set of high
quality skills to utilize (all in aep format of course)."

Generates AEP companions for the 8 existing AEP project skills + any skill in
.claude/skills/ that doesn't yet have a .aepkg companion. Idempotent.

Mirrors the make_skill_aepkg pattern from generate_anti_goal_skill_pack.py.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("C:/Users/example-user/")
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_skill_aepkg(skill_dir: Path) -> tuple[bool, str]:
    """Create AEP companion for a skill folder. Returns (created, msg)."""
    slug = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return (False, f"missing SKILL.md")

    pkg = SKILLS_ROOT / f"{slug}.aepkg"
    if pkg.exists():
        return (False, "already exists (skip)")

    pkg.mkdir(parents=True)
    for sub in ("data", "ops", "reviews", "validations", "views", "assets"):
        (pkg / sub).mkdir()

    md_bytes = skill_md.read_bytes()
    md_sha = sha256_hex(md_bytes)
    (pkg / "assets" / "original.md").write_bytes(md_bytes)
    (pkg / "assets" / "original.sha256").write_text(md_sha + "\n",
                                                     encoding="utf-8")

    now_iso = utc_now_iso()
    sources = {
        "id": f"src:skill-{slug}",
        "type": "Source",
        "source_type": "in_packet_file",
        "title": f"Skill {slug}",
        "location": {"kind": "file", "value": "./assets/original.md",
                     "location_hash": "sha256:" + md_sha},
        "provenance_strength": "strong",
        "limits": [],
        "created_at": now_iso,
    }
    (pkg / "data" / "sources.jsonl").write_text(
        json.dumps(sources, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    for f in ("spans.jsonl", "claims.jsonl", "relations.jsonl"):
        (pkg / "data" / f).write_text("", encoding="utf-8")
    (pkg / "ops" / "events.jsonl").write_text(
        json.dumps({
            "id": "evt:001", "type": "WriteEvent",
            "event_type": "packet_created", "event_time": now_iso,
            "actor": "convert_existing_skills_to_aep.py",
            "target": "aepkg.json",
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    (pkg / "reviews" / "reviews.jsonl").write_text("", encoding="utf-8")
    (pkg / "validations" / "runs.jsonl").write_text("", encoding="utf-8")

    manifest = {
        "aep_version": "0.5",
        "profile": "aep:0.5/stable",
        "packet_id": f"aepkg:skill-{slug}",
        "packet_epoch": 1,
        "title": f"Skill {slug} (AEP companion)",
        "created_at": now_iso,
        "created_by": "AEP-DEV convert_existing_skills_to_aep.py",
        "canonical_files": [
            "data/sources.jsonl", "data/spans.jsonl", "data/claims.jsonl",
            "data/relations.jsonl", "ops/events.jsonl",
            "reviews/reviews.jsonl", "validations/runs.jsonl",
        ],
        "extensions": {
            "skill_slug": slug,
            "canonical_md_path": f".claude/skills/{slug}/SKILL.md",
            "canonical_md_sha256": "sha256:" + md_sha,
            "from_existing_pre_2026_05_16": True,
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "state_hash": "sha256:" + sha256_hex(b""),
            "manifest_hash": "sha256:" + sha256_hex(b""),
            "assets_merkle_root": "sha256:" + md_sha,
        },
    }
    (pkg / "aepkg.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    return (True, f"created (md_sha256={md_sha[:12]}...)")


def main():
    actions = {"created": 0, "skipped": 0, "missing_md": 0}
    skill_dirs = sorted(p for p in SKILLS_ROOT.iterdir()
                         if p.is_dir() and not p.name.endswith(".aepkg"))
    for d in skill_dirs:
        created, msg = make_skill_aepkg(d)
        status = "CREATED" if created else ("SKIP   " if "exists" in msg else "MISSING")
        print(f"{status}  {d.name:<45} {msg}")
        if created:
            actions["created"] += 1
        elif "exists" in msg:
            actions["skipped"] += 1
        else:
            actions["missing_md"] += 1
    print()
    print(f"Summary: {actions['created']} created / {actions['skipped']} skipped / {actions['missing_md']} missing SKILL.md")


if __name__ == "__main__":
    main()
