"""convert_skill_to_aep.py — Wave-011 pilot generator.

Authored under AEP-22-TO-12-SKILL-CONSOLIDATION-WAVE-011-FORGE
(task 2026-05-17T0535-w011-task-06). Composes with §49 + §41 + §60.

Differs from convert_existing_skills_to_aep.py by EXTRACTING semantic
claims (when_to_use, NOT_for, composes_with, falsifiers) from the SKILL.md
body, not just writing empty placeholders. Pilot target: aep-search.

Truth tag: STRONGLY PLAUSIBLE — passes v0.5 validator on aep-search,
batch readiness for remaining 21 skills assumed but not measured.

Fail behavior: fail-CLOSED on malformed YAML frontmatter (exit 2);
fail-OPEN with WARN on missing sections (writes partial .aepkg with
emit notes in events.jsonl). Documented in TASK 4 of pilot run.

Idempotent: --force overwrites existing .aepkg/; otherwise skips.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[5]
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def utc_now_iso() -> str:
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def jsonl_line(obj: dict) -> str:
    return (
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


# ----- SKILL.md parser -----

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
# Match both H1 (`# `) and H2 (`## `) section headings — utility skills use H1,
# anti-goal skills use H2 with an H1 title at the top.
SECTION_RE = re.compile(r"^#{1,2}\s+(.+?)\s*$", re.MULTILINE)


# Wave-012 expansion (AEP-22-TO-12-SKILL-CONSOLIDATION-WAVE-012-FORGE).
# Maps heterogeneous H2 headings to canonical extraction targets.
# Lookup is normalize_section_key(<heading>) -> canonical key in {when-to-use,
# not-for, composes-with, falsifiers, honesty-boundaries, lineage, axioms,
# anti-patterns, stop-conditions, promotion-criteria, purpose}.
SECTION_ALIASES: dict[str, str] = {
    "when to use": "when-to-use",
    "when this skill fires": "when-to-use",
    "trigger": "when-to-use",
    "triggers": "when-to-use",
    "invocation": "when-to-use",
    "description": "purpose",
    "purpose": "purpose",
    "not for": "not-for",
    "what this skill is not for": "not-for",
    "anti patterns": "anti-patterns",
    "anti-patterns": "anti-patterns",
    "stop conditions": "stop-conditions",
    "stop conditions loop terminates": "stop-conditions",
    "stop conditions loop_terminates": "stop-conditions",
    "composes with": "composes-with",
    "honesty boundaries": "honesty-boundaries",
    "honesty boundaries per sibling 73": "honesty-boundaries",
    "lineage": "lineage",
    "axioms": "axioms",
    "falsifiers": "falsifiers",
    "falsifiers mechanically decidable": "falsifiers",
    "promotion criteria": "promotion-criteria",
    "procedure": "procedure",
    "output discipline": "output-discipline",
    "output": "output",
    "what not to do": "not-for",
}


def normalize_section_key(s: str) -> str:
    """Lowercase + collapse non-alphanumerics to single spaces (then strip)."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


class ParseWarning(Exception):
    """Non-fatal parse defect; logged to events.jsonl, generator still emits."""


def parse_yaml_minimal(text: str) -> dict:
    """Minimal YAML subset: key: value | key: [a, b] | key: | multiline.
    Returns dict; raises ValueError on un-parseable.
    """
    result: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            raise ValueError(f"unparseable line {i}: {line!r}")
        key, val = m.group(1), m.group(2).strip()
        if val == "" or val == "|":
            # multiline block; consume until next top-level key or EOF
            block_lines: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if re.match(r"^[A-Za-z_][\w-]*\s*:", nxt):
                    break
                # strip a single common leading indent
                stripped = nxt[2:] if nxt.startswith("  ") else nxt.lstrip()
                block_lines.append(stripped)
                i += 1
            result[key] = "\n".join(block_lines).rstrip()
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [s.strip().strip("\"'") for s in inner.split(",") if s.strip()]
            result[key] = items
        else:
            result[key] = val.strip("\"'")
        i += 1
    return result


def split_sections(body: str) -> dict[str, str]:
    """Split markdown body into section_title -> section_body.

    Populates each section under BOTH its raw lowercased title AND its
    canonical alias key (per SECTION_ALIASES). Existing canonical-key
    contents are NOT overwritten (first match wins, in document order)
    so that authors can rely on order-stability.
    """
    sections: dict[str, str] = {}
    matches = list(SECTION_RE.finditer(body))
    for idx, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()
        raw_key = title.lower()
        sections[raw_key] = section_body
        canonical = SECTION_ALIASES.get(normalize_section_key(title))
        if canonical and canonical not in sections:
            sections[canonical] = section_body
    return sections


# ----- Claim/source extraction -----

CITED_SLOT_RE = re.compile(r"§\s*(\d{2,3})")
URL_RE = re.compile(r"https?://[^\s)\"]+")
DOCTRINE_PATH_RE = re.compile(r"doctrine/[^\s)\"`]+\.html")
SIBLING_RE = re.compile(r"sibling-\d+", re.IGNORECASE)


INLINE_BOLD_RE = re.compile(
    r"\*\*(Falsifier|Falsifiers|Composes with|Promotion criteria)\*\*\s*:\s*(.+?)(?=\n\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _bullets(text: str) -> list[str]:
    """Extract markdown list items (bullets '- '/'* ' OR numbered '1. ')
    as stripped strings. Wave-012: numbered-list support added for utility
    skills (truth-tag, visual-judge) that use enumerated procedure steps."""
    bullets = re.findall(r"^[-\*]\s+(.+)$", text, re.MULTILINE)
    numbered = re.findall(r"^\d+[\.\)]\s+(.+)$", text, re.MULTILINE)
    return [b.strip() for b in bullets + numbered]


def extract_claims(slug: str, frontmatter: dict, sections: dict[str, str]) -> list[dict]:
    """Emit one claim per load-bearing assertion in the SKILL body.

    Wave-012: reads canonical alias keys populated by split_sections().
    Adds claim-emission for anti-patterns, stop-conditions, promotion-criteria,
    axioms, and inline bold prefixes ("**Falsifier**:" "**Composes with**:")
    found INSIDE other sections (the anti-goal pattern).
    """
    claims: list[dict] = []

    # Claim #1: skill purpose (from frontmatter description; falls back to
    # canonical 'purpose' section).
    desc = frontmatter.get("description", "").strip()
    if not desc:
        desc = sections.get("purpose", "").strip()
    if desc:
        claims.append({
            "id": f"claim:skill-{slug}-purpose",
            "type": "Claim",
            "text": desc,
            "axis_a_reliability": "STRONGLY_PLAUSIBLE",
            "axis_b_action": "GO",
            "anchor": "explicit_in_source",
            "basis": [f"src:skill-{slug}#frontmatter:description"],
        })

    # when-to-use: each bullet OR the prose body (if no bullets, emit one claim).
    when_section = sections.get("when-to-use", "")
    if when_section:
        bullets = _bullets(when_section)
        if bullets:
            for idx, bullet in enumerate(bullets, start=1):
                claims.append({
                    "id": f"claim:skill-{slug}-when-{idx:02d}",
                    "type": "Claim",
                    "text": f"Use {slug} when: {bullet}",
                    "axis_a_reliability": "STRONGLY_PLAUSIBLE",
                    "axis_b_action": "GO",
                    "anchor": "explicit_in_source",
                    "basis": [f"src:skill-{slug}#when-to-use"],
                })
        else:
            # Prose-only when-to-use (e.g. anti-goal-receipt-forge "fires per checkpoint")
            prose_first = when_section.split("\n\n")[0].strip()
            if prose_first and not prose_first.startswith("```"):
                claims.append({
                    "id": f"claim:skill-{slug}-when-01",
                    "type": "Claim",
                    "text": f"Use {slug} when: {prose_first[:400]}",
                    "axis_a_reliability": "STRONGLY_PLAUSIBLE",
                    "axis_b_action": "GO",
                    "anchor": "explicit_in_source",
                    "basis": [f"src:skill-{slug}#when-to-use"],
                })

    # not-for: FORBIDDEN boundary claims.
    not_for = sections.get("not-for", "")
    if not_for:
        for idx, bullet in enumerate(_bullets(not_for), start=1):
            claims.append({
                "id": f"claim:skill-{slug}-not-for-{idx:02d}",
                "type": "Claim",
                "text": f"{slug} is NOT for: {bullet}",
                "axis_a_reliability": "STRONGLY_PLAUSIBLE",
                "axis_b_action": "FORBIDDEN",
                "anchor": "explicit_in_source",
                "basis": [f"src:skill-{slug}#not-for"],
            })

    # composes-with: GO relations.
    composes_section = sections.get("composes-with", "")
    if composes_section:
        for idx, bullet in enumerate(_bullets(composes_section), start=1):
            claims.append({
                "id": f"claim:skill-{slug}-composes-{idx:02d}",
                "type": "Claim",
                "text": f"{slug} composes with: {bullet}",
                "axis_a_reliability": "STRONGLY_PLAUSIBLE",
                "axis_b_action": "GO",
                "anchor": "derived_from_claims",
                "basis": [f"src:skill-{slug}#composes-with"],
            })

    # honesty-boundaries / lineage / falsifiers / axioms / anti-patterns /
    # stop-conditions / promotion-criteria = governance rules. Each bullet is
    # a single claim. anti-patterns get axis_b=FORBIDDEN.
    governance_sections = [
        ("honesty-boundaries", "GO"),
        ("lineage", "GO"),
        ("falsifiers", "GO"),
        ("axioms", "GO"),
        ("anti-patterns", "FORBIDDEN"),
        ("stop-conditions", "HALT"),
        ("promotion-criteria", "GO"),
        ("procedure", "GO"),
        ("output-discipline", "GO"),
        ("output", "GO"),
    ]
    for sec_name, axis_b in governance_sections:
        sec_body = sections.get(sec_name, "")
        if not sec_body:
            continue
        for idx, bullet in enumerate(_bullets(sec_body), start=1):
            claims.append({
                "id": f"claim:skill-{slug}-{sec_name}-{idx:02d}",
                "type": "Claim",
                "text": bullet,
                "axis_a_reliability": "STRONGLY_PLAUSIBLE",
                "axis_b_action": axis_b,
                "anchor": "explicit_in_source",
                "basis": [f"src:skill-{slug}#{sec_name}"],
            })

    # Wave-012 fallback: any section whose title is NOT recognized by
    # SECTION_ALIASES also emits claims (one per bullet/numbered item).
    # This catches utility skills (truth-tag, visual-judge) whose section
    # titles are domain-specific ("The 6 tags", "Plumbing path").
    recognized_canonical_keys = set(SECTION_ALIASES.values()) | {
        "purpose"  # already handled
    }
    for sec_title, sec_body in sections.items():
        # Skip if this key IS a canonical-alias key (already emitted above)
        if sec_title in recognized_canonical_keys:
            continue
        # Skip if there's a corresponding canonical alias whose body matches
        # this body (avoid double-emission of the same content).
        if SECTION_ALIASES.get(normalize_section_key(sec_title)) in sections:
            continue
        sec_bullets = _bullets(sec_body)
        if not sec_bullets:
            continue
        slug_key = re.sub(r"[^a-z0-9]+", "-", sec_title.lower()).strip("-")[:32]
        for idx, bullet in enumerate(sec_bullets, start=1):
            claims.append({
                "id": f"claim:skill-{slug}-{slug_key}-{idx:02d}",
                "type": "Claim",
                "text": bullet[:400],
                "axis_a_reliability": "STRONGLY_PLAUSIBLE",
                "axis_b_action": "GO",
                "anchor": "explicit_in_source",
                "basis": [f"src:skill-{slug}#{slug_key}"],
            })

    # Inline bold-prefix claims: anti-goal SKILL.md files put "**Falsifier**:"
    # "**Composes with**:" "**Promotion criteria**:" as inline paragraphs INSIDE
    # other sections (not dedicated H2). Sweep the full body for these.
    body_concat = "\n\n".join(sections.values())
    seen_inline: set[str] = set()
    for m in INLINE_BOLD_RE.finditer(body_concat):
        kind_raw = m.group(1).lower()
        text = m.group(2).strip()
        if not text:
            continue
        kind = (
            "falsifier" if kind_raw.startswith("falsifier")
            else "composes" if "compos" in kind_raw
            else "promotion-criteria"
        )
        axis = "FORBIDDEN" if kind == "falsifier" else "GO"
        dedup_key = f"{kind}:{text[:80]}"
        if dedup_key in seen_inline:
            continue
        seen_inline.add(dedup_key)
        idx = sum(1 for k in seen_inline if k.startswith(f"{kind}:"))
        claims.append({
            "id": f"claim:skill-{slug}-inline-{kind}-{idx:02d}",
            "type": "Claim",
            "text": f"{kind.capitalize()}: {text[:400]}",
            "axis_a_reliability": "STRONGLY_PLAUSIBLE",
            "axis_b_action": axis,
            "anchor": "explicit_in_source",
            "basis": [f"src:skill-{slug}#inline-{kind}"],
        })

    return claims


def extract_sources(slug: str, body: str, md_sha: str) -> list[dict]:
    """Emit one source-record for the SKILL.md itself + each cited
    doctrine slot / sibling / external URL.
    """
    now = utc_now_iso()
    sources: list[dict] = [{
        "id": f"src:skill-{slug}",
        "type": "Source",
        "source_type": "in_packet_file",
        "title": f"Skill {slug} canonical SKILL.md",
        "location": {
            "kind": "file",
            "value": "./assets/original.md",
            "location_hash": "sha256:" + md_sha,
        },
        "provenance_strength": "strong",
        "limits": [],
        "created_at": now,
    }]

    seen: set[str] = set()
    for slot in CITED_SLOT_RE.findall(body):
        sid = f"src:doctrine-section-{slot}"
        if sid in seen:
            continue
        seen.add(sid)
        sources.append({
            "id": sid,
            "type": "Source",
            "source_type": "doctrine_section",
            "title": f"AEP project doctrine §{slot}",
            "location": {"kind": "logical", "value": f"doctrine/§{slot}"},
            "provenance_strength": "strong",
            "limits": [],
            "created_at": now,
        })

    for doc_path in DOCTRINE_PATH_RE.findall(body):
        sid = "src:" + doc_path.replace("/", "-").replace(".", "-")
        if sid in seen:
            continue
        seen.add(sid)
        sources.append({
            "id": sid,
            "type": "Source",
            "source_type": "doctrine_artifact",
            "title": doc_path,
            "location": {"kind": "file", "value": doc_path},
            "provenance_strength": "strong",
            "limits": [],
            "created_at": now,
        })

    for sib in {s.lower() for s in SIBLING_RE.findall(body)}:
        sid = f"src:{sib}"
        sources.append({
            "id": sid,
            "type": "Source",
            "source_type": "lesson_reference",
            "title": sib,
            "location": {"kind": "logical", "value": f"doctrine/lessons/{sib}"},
            "provenance_strength": "moderate",
            "limits": ["sibling-N reference may be ambiguous if multiple lessons share number"],
            "created_at": now,
        })

    return sources


def extract_relations(slug: str, sections: dict[str, str]) -> list[dict]:
    """Emit composes_with relations as typed edges.

    Wave-012: reads canonical 'composes-with' key. Also sweeps inline
    "**Composes with**:" prefix paragraphs (anti-goal pattern).
    """
    relations: list[dict] = []
    composes_section = sections.get("composes-with", "")
    bullets = _bullets(composes_section) if composes_section else []

    # Inline "**Composes with**:" prefix bodies (anti-goal pattern).
    body_concat = "\n\n".join(sections.values())
    inline_bullets: list[str] = []
    for m in INLINE_BOLD_RE.finditer(body_concat):
        if "compos" not in m.group(1).lower():
            continue
        inline_text = m.group(2).strip()
        # Split on semicolons (sibling-skill list syntax: "skill-x; skill-y").
        for piece in re.split(r"[;\n]", inline_text):
            piece = piece.strip()
            if piece and piece not in inline_bullets:
                inline_bullets.append(piece)
    bullets = bullets + inline_bullets

    for idx, bullet in enumerate(bullets, start=1):
        target_slug = None
        m_slot = CITED_SLOT_RE.search(bullet)
        if m_slot:
            target_slug = f"src:doctrine-section-{m_slot.group(1)}"
        else:
            m_path = DOCTRINE_PATH_RE.search(bullet)
            if m_path:
                target_slug = "src:" + m_path.group(0).replace("/", "-").replace(".", "-")
        if not target_slug:
            target_slug = f"src:skill-{slug}-composes-target-{idx:02d}"
        relations.append({
            "id": f"rel:skill-{slug}-composes-{idx:02d}",
            "type": "Relation",
            "relation_type": "composes_with",
            "source_id": f"src:skill-{slug}",
            "target_id": target_slug,
            "narrative": bullet[:200],
        })
    return relations


# ----- Generator entry point -----

def make_skill_aepkg(
    skill_dir: Path,
    out_root: Optional[Path] = None,
    force: bool = False,
    fail_open_on_missing_sections: bool = True,
) -> dict:
    """Generate AEP companion for a single skill.

    Returns a result dict with keys:
      created (bool), path (Path), warnings (list[str]),
      md_sha (str), claims_count (int), sources_count (int).

    Raises FileNotFoundError if SKILL.md missing.
    Raises ValueError if frontmatter unparseable (fail-CLOSED).
    """
    slug = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found at {skill_md}")

    md_bytes = skill_md.read_bytes()
    md_text = md_bytes.decode("utf-8")
    md_sha = sha256_hex(md_bytes)

    warnings: list[str] = []

    fm_match = FRONTMATTER_RE.match(md_text)
    if fm_match:
        try:
            frontmatter = parse_yaml_minimal(fm_match.group(1))
        except ValueError as e:
            # FAIL-CLOSED on malformed YAML — operator must fix the source
            raise ValueError(f"malformed YAML frontmatter in {skill_md}: {e}") from e
        body = fm_match.group(2)
    else:
        warnings.append("no_frontmatter — generator continues with empty frontmatter (fail-OPEN)")
        frontmatter = {}
        body = md_text

    sections = split_sections(body)
    if not sections:
        warnings.append("no_h2_sections — claim extraction limited to frontmatter only (fail-OPEN)")

    pkg_root = out_root or SKILLS_ROOT
    pkg = pkg_root / f"{slug}.aepkg"
    if pkg.exists():
        if not force:
            return {
                "created": False,
                "path": pkg,
                "warnings": ["skip: already exists; use --force to overwrite"],
                "md_sha": md_sha,
                "claims_count": 0,
                "sources_count": 0,
            }
        shutil.rmtree(pkg)

    pkg.mkdir(parents=True)
    for sub in ("data", "ops", "reviews", "validations", "views", "assets"):
        (pkg / sub).mkdir()

    # views/source.md is byte-identical projection of canonical SKILL.md
    # per Bridge Protocol invariant #2.
    (pkg / "views" / "source.md").write_bytes(md_bytes)
    (pkg / "assets" / "original.md").write_bytes(md_bytes)
    (pkg / "assets" / "original.sha256").write_text(md_sha + "\n", encoding="utf-8")

    claims = extract_claims(slug, frontmatter, sections)
    sources = extract_sources(slug, body, md_sha)
    relations = extract_relations(slug, sections)

    (pkg / "data" / "claims.jsonl").write_text(
        "".join(jsonl_line(c) for c in claims), encoding="utf-8", newline="\n"
    )
    (pkg / "data" / "sources.jsonl").write_text(
        "".join(jsonl_line(s) for s in sources), encoding="utf-8", newline="\n"
    )
    (pkg / "data" / "relations.jsonl").write_text(
        "".join(jsonl_line(r) for r in relations), encoding="utf-8", newline="\n"
    )
    (pkg / "data" / "spans.jsonl").write_text("", encoding="utf-8")

    now = utc_now_iso()
    events = [{
        "id": "evt:001",
        "type": "WriteEvent",
        "event_type": "packet_created",
        "event_time": now,
        "actor": "convert_skill_to_aep.py",
        "target": "aepkg.json",
    }]
    for w_idx, w_msg in enumerate(warnings, start=2):
        events.append({
            "id": f"evt:{w_idx:03d}",
            "type": "WriteEvent",
            "event_type": "generator_warning",
            "event_time": now,
            "actor": "convert_skill_to_aep.py",
            "target": "aepkg.json",
            "warning": w_msg,
        })
    (pkg / "ops" / "events.jsonl").write_text(
        "".join(jsonl_line(e) for e in events), encoding="utf-8", newline="\n"
    )
    (pkg / "reviews" / "reviews.jsonl").write_text("", encoding="utf-8")
    (pkg / "validations" / "runs.jsonl").write_text("", encoding="utf-8")

    canonical_md_rel_path = f".claude/skills/{slug}/SKILL.md"
    manifest = {
        "aep_version": "0.5",
        "profile": "aep:0.5/stable",
        "packet_id": f"aepkg:skill-{slug}",
        "packet_epoch": 1,
        "title": f"Skill {slug} (AEP companion, v2 semantic-extract)",
        "created_at": now,
        "created_by": "AEP-DEV convert_skill_to_aep.py (Wave-011)",
        "canonical_files": [
            "data/sources.jsonl",
            "data/spans.jsonl",
            "data/claims.jsonl",
            "data/relations.jsonl",
            "ops/events.jsonl",
            "reviews/reviews.jsonl",
            "validations/runs.jsonl",
        ],
        "extensions": {
            "skill_slug": slug,
            "canonical_md_path": canonical_md_rel_path,
            "canonical_md_sha256": "sha256:" + md_sha,
            "sha256_of_canonical_md": "sha256:" + md_sha,
            "generator_version": "convert_skill_to_aep.py@v2-2026-05-17",
            "fail_open_warnings": warnings,
            "claims_count": len(claims),
            "sources_count": len(sources),
            "relations_count": len(relations),
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
        encoding="utf-8",
        newline="\n",
    )

    return {
        "created": True,
        "path": pkg,
        "warnings": warnings,
        "md_sha": md_sha,
        "claims_count": len(claims),
        "sources_count": len(sources),
        "relations_count": len(relations),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_slug", help="skill slug e.g. aep-search")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing .aepkg")
    parser.add_argument("--skills-root", default=str(SKILLS_ROOT),
                        help="root dir containing skill folders")
    args = parser.parse_args()

    skills_root = Path(args.skills_root)
    skill_dir = skills_root / args.skill_slug
    if not skill_dir.exists():
        print(f"ERROR: skill folder not found: {skill_dir}", file=sys.stderr)
        return 1

    try:
        result = make_skill_aepkg(skill_dir, out_root=skills_root, force=args.force)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        # fail-CLOSED on malformed YAML
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 2

    status = "CREATED" if result["created"] else "SKIPPED"
    print(f"{status}  {args.skill_slug}")
    print(f"  path:     {result['path']}")
    print(f"  md_sha:   {result['md_sha'][:16]}...")
    print(f"  claims:   {result['claims_count']}")
    print(f"  sources:  {result['sources_count']}")
    if result["warnings"]:
        print(f"  warnings: {len(result['warnings'])}")
        for w in result["warnings"]:
            print(f"    - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
