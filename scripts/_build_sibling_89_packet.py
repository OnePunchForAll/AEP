"""Build the AEP packet metadata for sibling-89.

Creates the canonical files (sources / spans / claims / relations / events /
reviews / validations) + aepkg.json with proper sha256 integrity.

Follows the sibling-87 + sibling-88 packet structure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path("C:/Users/example-user/")
PACKET = (
    REPO
    / "doctrine"
    / "lessons"
    / "2026-05-16-operator-message-dump-plus-psychology-eval-as-shadow-operator-continuity-substrate.aepkg"
)
SLUG = "2026-05-16-operator-message-dump-plus-psychology-eval-as-shadow-operator-continuity-substrate"
SIBLING = 89
DATE = "2026-05-16"
ORIGINAL = PACKET / "assets" / "original.html"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    if not ORIGINAL.exists():
        raise SystemExit(f"missing body: {ORIGINAL}")

    canonical_html_sha = sha256_file(ORIGINAL)
    src_id = f"src:lesson-{SLUG}"
    span_id = f"span:lesson-{SLUG}-body"
    claim_p1 = f"claim:{SLUG}-pattern-1-operator-message-dump"
    claim_p2 = f"claim:{SLUG}-pattern-2-psychology-eval"
    claim_continuity = f"claim:{SLUG}-shadow-operator-continuity"

    # Sources
    sources = [
        {
            "id": src_id,
            "type": "Source",
            "format": "text/html",
            "location": f"./assets/original.html",
            "provenance_strength": "primary-canonical",
            "sha256": f"sha256:{canonical_html_sha}",
            "title": "Lesson 89 - Operator-Message-Dump + Psychology-Eval as operator Operator Continuity Substrate",
            "limits": "Primary-canonical for this lesson; verbatim of authored body.",
        }
    ]

    # Spans
    spans = [
        {
            "id": span_id,
            "type": "Span",
            "source": src_id,
            "selector": {"type": "DocumentRoot", "scope": "full-body"},
            "quote_hash": f"sha256:{canonical_html_sha}",
        }
    ]

    # Claims (3 load-bearing)
    claims = [
        {
            "id": claim_p1,
            "type": "Claim",
            "text": "Operator-message verbatim dump at .claude/diana/operator-messages/dump-NNN/message-NNNN.aepkg/ with rolling-500MB folder discipline is the compounding-taste substrate that grounds every operator-taste claim in a citable raw message.",
            "axis_a": "STRONGLY_PLAUSIBLE",
            "axis_b": "GO",
            "truth_tag": "STRONGLY PLAUSIBLE",
            "basis": [span_id],
            "owner_agent": "scribe",
            "scope": "shadow-operator-continuity",
            "status": "active-fresh",
        },
        {
            "id": claim_p2,
            "type": "Claim",
            "text": "the agent's psychological evaluation of each operator message at .claude/diana/operator-psychology/dump-NNN/eval-NNNN.aepkg/ is the read-projection of the verbatim corpus and the only mechanism by which operator Operator continuity is cite-anchored rather than fabricated.",
            "axis_a": "STRONGLY_PLAUSIBLE",
            "axis_b": "GO",
            "truth_tag": "STRONGLY PLAUSIBLE",
            "basis": [span_id],
            "owner_agent": "scribe",
            "scope": "shadow-operator-continuity",
            "status": "active-fresh",
        },
        {
            "id": claim_continuity,
            "type": "Claim",
            "text": "Sibling-89 + sibling-88 together: sibling-88 codifies the operator Operator ROLE; sibling-89 codifies the EVIDENCE-BASIS that makes the role honest. Without both, the role is a hallucination dressed as continuity.",
            "axis_a": "STRONGLY_PLAUSIBLE",
            "axis_b": "GO",
            "truth_tag": "STRONGLY PLAUSIBLE",
            "basis": [span_id],
            "owner_agent": "scribe",
            "scope": "doctrine-cross-reference",
            "status": "active-fresh",
        },
    ]

    # Relations (cross-corpus + predecessor chain)
    relations = [
        {
            "id": f"rel:{SLUG}-predecessor-sibling-88",
            "type": "Relation",
            "subject": claim_continuity,
            "predicate": "predecessor",
            "object": "lesson:sibling-88",
        },
        {
            "id": f"rel:{SLUG}-cross-agent-cite-forge",
            "type": "Relation",
            "subject": claim_p1,
            "predicate": "cites",
            "object": "ledger::forge::lamport-223::comprehensive-agent-evolution-section-60-amendment-2026-05-16",
        },
        {
            "id": f"rel:{SLUG}-cross-agent-cite-judge",
            "type": "Relation",
            "subject": claim_p2,
            "predicate": "cites",
            "object": "ledger::judge::lamport-210::mega-wave-judge-all-falsifiers-audit-2026-05-15",
        },
        {
            "id": f"rel:{SLUG}-cross-agent-cite-curator",
            "type": "Relation",
            "subject": claim_continuity,
            "predicate": "cites",
            "object": "ledger::curator::lamport-null-section-60-61-curator-verdict-2026-05-16::section-60-61-law-and-agent-evolution-verdict-2026-05-16",
        },
    ]

    # Ops (event-log)
    events = [
        {
            "id": f"ev:{SLUG}-author-2026-05-16",
            "type": "Event",
            "action": "lesson-authored",
            "agent": "scribe",
            "timestamp": "2026-05-16T00:00:00Z",
            "mission": "AEP-V11-AEP-SIBLING-89-OPERATOR-DUMP-PLUS-PSYCHOLOGY-EVAL-AS-CONTINUITY-SUBSTRATE-2026-05-16",
            "session_id": "huddle-wave-scribe-sibling-89-author-2026-05-16",
        }
    ]

    # Reviews + validations (empty initial)
    reviews: list[dict] = []
    validations: list[dict] = []

    write_jsonl(PACKET / "data" / "sources.jsonl", sources)
    write_jsonl(PACKET / "data" / "spans.jsonl", spans)
    write_jsonl(PACKET / "data" / "claims.jsonl", claims)
    write_jsonl(PACKET / "data" / "relations.jsonl", relations)
    write_jsonl(PACKET / "ops" / "events.jsonl", events)
    write_jsonl(PACKET / "reviews" / "reviews.jsonl", reviews)
    write_jsonl(PACKET / "validations" / "runs.jsonl", validations)

    # Views: byte-identical projection of original.html as source.html (for verifier roundtrip)
    views_src = PACKET / "views" / "source.html"
    views_src.parent.mkdir(parents=True, exist_ok=True)
    views_src.write_bytes(ORIGINAL.read_bytes())

    # Build assets merkle root over all canonical files
    canonical = [
        "data/sources.jsonl",
        "data/spans.jsonl",
        "data/claims.jsonl",
        "data/relations.jsonl",
        "ops/events.jsonl",
        "reviews/reviews.jsonl",
        "validations/runs.jsonl",
    ]
    file_hashes = []
    for rel in canonical:
        p = PACKET / rel
        file_hashes.append(sha256_file(p))
    merkle = hashlib.sha256("\n".join(sorted(file_hashes)).encode("utf-8")).hexdigest()

    aepkg = {
        "aep_version": "0.5",
        "canonical_files": canonical,
        "created_at": "2026-05-16T00:00:00Z",
        "created_by": "sibling-89-author-script",
        "extensions": {
            "canonical_html_sha256": f"sha256:{canonical_html_sha}",
            "lesson_slug": SLUG,
            "original_html_path": "./assets/original.html",
            "sibling_index": SIBLING,
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "assets_merkle_root": f"sha256:{canonical_html_sha}",
            "manifest_hash": f"sha256:{merkle}",
            "state_hash": f"sha256:{merkle}",
        },
        "packet_epoch": 1,
        "packet_id": f"aepkg:lesson-{SLUG}",
        "profile": "aep:0.5/stable",
        "title": f"Lesson sibling-{SIBLING} ({SLUG})",
    }

    (PACKET / "aepkg.json").write_text(
        json.dumps(aepkg, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"OK sibling-{SIBLING} packet built at {PACKET}")
    print(f"   canonical_html_sha256 = sha256:{canonical_html_sha}")
    print(f"   manifest_hash = sha256:{merkle}")
    print(f"   body lines = {sum(1 for _ in ORIGINAL.read_text(encoding='utf-8').splitlines())}")


if __name__ == "__main__":
    main()
