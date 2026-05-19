"""emit_counter_claims_wave_019.py - Wave-019 emission script.

Authored under AEP-FRONTIER-WAVE-019-FORGE-COUNTER-CLAIM-BINDING
(task 2026-05-17T1205-w019-task-01). One-shot script that:

Task 2: emits one bound CounterClaim per persona (12 total) into the
top-level `counter_claims` array of each `.aepkg/aepkg.json`, then
runs validate_counter_claim per entry.

Task 3: backfills `lineage_predecessor_hash` for each persona using the
Wave-019 rule:
  - Source-meshed personas (>=1 doctrine/lesson source): hash =
    sha256(concat(sorted(source canonical_md_sha256))). The hash is
    deterministic in the sorted source-sha order.
  - visual-judge (PROMOTE-1-source same-name, mutated-in-place): hash =
    pre-edit Wave-013 sha recovered from git commit 1229a90ad
    (sha256:affeb19fd86de0177f5293f39f709ce392e3edbf0fc7dd4731e279b33055c25a).
  - forge (MINT-FROM-SUBSTRATE): hash = sha256 of the substrate file
    `.claude/agents/forge.md` at emission time. Already captured as the
    in_packet_file source's location_hash.
  - claude-main (utility-substrate): hash = sha256(concat(sorted by
    type-ascending: truth-tag + aep-search canonical_md_sha256)).
    The legacy truth-tag + aep-search substrate is preserved in the
    `_archive/2026-05-17-pre-22-to-12-consolidation/` directory.

Rule documented also in skill_lineage_dag.py docstring (Wave-014 hydration
plan reference).

Truth tag: STRONGLY PLAUSIBLE - one-shot emission with per-persona
validation. Failures surface loudly via sys.exit(1).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_AEP_ROOT = _HERE.parent
if str(_AEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_AEP_ROOT))

from security.counter_claim_schema import (  # noqa: E402
    CounterClaim,
    serialize_counter_claim_list,
    validate_counter_claim,
)

REPO_ROOT = _HERE.parents[4]
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
ARCHIVE_ROOT = SKILLS_ROOT / "_archive" / "2026-05-17-pre-22-to-12-consolidation"

# The 12 canonical persona slugs.
TWELVE_PERSONAS = [
    "strategist",
    "pathfinder",
    "scout",
    "forge",
    "judge",
    "adversary",
    "warden",
    "scribe",
    "curator",
    "visual-judge",
    "diana",
    "claude-main",
]

# Wave-019 authored_at: emission time
AUTHORED_AT = "2026-05-17T12:15:00Z"

# Per-persona counter-claim spec from the Wave-019 mission brief.
# (uri, type, authored_by, strength, internal_path_for_sha?)
# When internal_path_for_sha is set, the script computes sha256 of the
# file at emission time and embeds it. None means external/no-sha.
COUNTER_CLAIM_SPEC: dict[str, dict] = {
    "strategist": {
        "uri": "doctrine/_proposals/adversary-2026-05-17-wave-014-group-A-consolidation-premortem-with-bp-status-review.html#BP-014-STRATEGIST-SINGLE-SOURCE-SHALLOWNESS-1",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "adversary",
        "strength": "DISCONFIRMS",
        "internal_path": "doctrine/_proposals/adversary-2026-05-17-wave-014-group-A-consolidation-premortem-with-bp-status-review.html",
    },
    "pathfinder": {
        "uri": "doctrine/_proposals/adversary-2026-05-17-wave-014-group-A-consolidation-premortem-with-bp-status-review.html#BP-014-PATHFINDER-CROSS-CATEGORY-MERGE-1",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "adversary",
        "strength": "WEAKENS",
        "internal_path": "doctrine/_proposals/adversary-2026-05-17-wave-014-group-A-consolidation-premortem-with-bp-status-review.html",
    },
    "scout": {
        "uri": "doctrine/_proposals/adversary-2026-05-17-wave-005-pivot-premortem-plus-own-attack-chain-audit.html#BP-DROP-002-MISSING-CROSS-CORPUS-EXTERNAL-PRIOR-ART",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "adversary",
        "strength": "WEAKENS",
        "internal_path": "doctrine/_proposals/adversary-2026-05-17-wave-005-pivot-premortem-plus-own-attack-chain-audit.html",
    },
    "forge": {
        # NB: mission brief referenced wave-016-12-of-12-persona-bound-skill-audit-premortem.html
        # but the actual adversary wave-016 premortem on disk is named
        # wave-016-full-backward-plus-group-C-premortem.html. Resolved to actual file.
        "uri": "doctrine/_proposals/adversary-2026-05-17-wave-016-full-backward-plus-group-C-premortem.html#BP-016-FORGE-MINT-FROM-SUBSTRATE-1",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "adversary",
        "strength": "DISCONFIRMS",
        "internal_path": "doctrine/_proposals/adversary-2026-05-17-wave-016-full-backward-plus-group-C-premortem.html",
    },
    "judge": {
        "uri": "doctrine/_proposals/judge-2026-05-17-wave-004-disconfirmer-v2-execution.html#PARTIAL-verdict",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "judge-self",
        "strength": "WEAKENS",
        "internal_path": "doctrine/_proposals/judge-2026-05-17-wave-004-disconfirmer-v2-execution.html",
    },
    "adversary": {
        "uri": "doctrine/lessons/2026-05-17-wave-002-disconfirmer-fail-as-protocol-success-pattern.html",
        "type": "SIBLING_LESSON",
        "authored_by": "scribe",
        "strength": "ADJACENCY-ONLY",
        "internal_path": None,
    },
    "warden": {
        "uri": "doctrine/_proposals/warden-2026-05-17-wave-017-cycle-close-readiness-audit.html#WAVE-017-WITH-ISSUES",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "warden-self",
        "strength": "DISCONFIRMS",
        "internal_path": "doctrine/_proposals/warden-2026-05-17-wave-017-cycle-close-readiness-audit.html",
    },
    "scribe": {
        "uri": "NO_KNOWN_COUNTER (sibling-graph deprecation mechanism missing per Wave-017 scribe improvement-gap)",
        "type": "NO_KNOWN_COUNTER",
        "authored_by": "adversary",
        "strength": "NULL",
        "internal_path": None,
    },
    "curator": {
        # NB: mission brief referenced a curator-authored shallow-consolidation
        # self-disclosure file; on-disk the strongest disconfirmer against
        # curator's shallow_consolidation=true single-source persona class
        # is adversary-wave-014 BP-014 attack. Honesty-pivot: use the actual
        # adversary disconfirmer rather than fabricate a curator-self file.
        # authored_by remains 'adversary' (anti-incest preserved); self-disclosure
        # of curator's 85% rename pattern stays in the lesson record once authored.
        "uri": "doctrine/_proposals/adversary-2026-05-17-wave-014-group-A-consolidation-premortem-with-bp-status-review.html#shallow_consolidation_true_single_source_persona",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "adversary",
        "strength": "WEAKENS",
        "internal_path": "doctrine/_proposals/adversary-2026-05-17-wave-014-group-A-consolidation-premortem-with-bp-status-review.html",
    },
    "visual-judge": {
        "uri": "doctrine/_proposals/warden-2026-05-17-wave-016-12-of-12-persona-bound-skill-audit.html#visual-judge-path-collision-WARN",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "warden",
        "strength": "DISCONFIRMS",
        "internal_path": "doctrine/_proposals/warden-2026-05-17-wave-016-12-of-12-persona-bound-skill-audit.html",
    },
    "diana": {
        "uri": "doctrine/_proposals/adversary-2026-05-17-wave-013-diana-autonomous-takeover-invocation-governance-review.html#Scenario-B-UNSAFE-PROBABLE",
        "type": "INTERNAL_FILE_PATH",
        "authored_by": "adversary",
        "strength": "DISCONFIRMS",
        "internal_path": "doctrine/_proposals/adversary-2026-05-17-wave-013-diana-autonomous-takeover-invocation-governance-review.html",
    },
    "claude-main": {
        "uri": "Wave-017-12-lens-fan-out claude-main improvement-gap section: substrate-as-poetic-not-mechanically-defined",
        "type": "EXTERNAL_URL",
        "authored_by": "claude-main-self",
        "strength": "WEAKENS",
        "internal_path": None,
    },
}


def _sha256_file(path: Path) -> Optional[str]:
    """Compute sha256:<hex> of a file's bytes. Returns None if file missing
    (counter-claim emission should NOT silently FAIL the entire batch
    because a single counter-artifact is missing — surface as warning
    later in the per-persona validate pass)."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _sha256_concat(shas: list[str]) -> str:
    """Compute sha256 of concat(sorted(shas)) for lineage_predecessor_hash
    derivation. Inputs are sha256:<hex> tokens; the function strips the
    sha256: prefix, sorts, joins with empty separator, and re-hashes."""
    cleaned = sorted(s.replace("sha256:", "") for s in shas)
    joined = "".join(cleaned).encode("ascii")
    h = hashlib.sha256(joined)
    return f"sha256:{h.hexdigest()}"


def _read_persona_sources(persona: str) -> list[str]:
    """Read sources.jsonl for a persona and return the canonical_md_sha256
    of each source where source_type is doctrine_artifact / doctrine_section /
    lesson_reference. Excludes the in_packet_file (which IS the SKILL itself).

    For source.location.location_hash: used when available; otherwise the
    source's canonical_md_sha256 location_hash field is used. We fall back
    to source.location.value as the hash-input when no hash is captured
    (string-based stand-in for sources whose hash was not captured).
    """
    pkg = SKILLS_ROOT / f"{persona}.aepkg"
    src_path = pkg / "data" / "sources.jsonl"
    if not src_path.exists():
        return []
    shas: list[str] = []
    for line in src_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("source_type") == "in_packet_file":
            # Skip the SKILL.md self-source; predecessor is over OTHER bases
            continue
        loc = rec.get("location", {})
        # Prefer location_hash when present; else use a deterministic stand-in
        # from the logical path so the lineage predecessor is reproducible.
        h = loc.get("location_hash")
        if h and h.startswith("sha256:"):
            shas.append(h)
        else:
            # Stand-in: sha256 of the logical source identifier (e.g.
            # 'doctrine/02-truth-tags.html' or 'doctrine/lessons/sibling-78').
            # This is deterministic AND surfaces source-identity-as-bytes.
            val = (loc.get("value") or rec.get("id") or "").encode("utf-8")
            stand_in = hashlib.sha256(val).hexdigest()
            shas.append(f"sha256:{stand_in}")
    return shas


def _lineage_predecessor_for(persona: str) -> Optional[str]:
    """Compute lineage_predecessor_hash per the Wave-019 rule (documented
    at top of this script and in skill_lineage_dag.py)."""
    if persona == "visual-judge":
        # PROMOTE-1-source same-name, mutated-in-place. Pre-edit sha
        # captured from git commit 1229a90ad (Wave-013 baseline).
        return "sha256:affeb19fd86de0177f5293f39f709ce392e3edbf0fc7dd4731e279b33055c25a"
    if persona == "forge":
        # MINT-FROM-SUBSTRATE: substrate is .claude/agents/forge.md
        substrate = REPO_ROOT / ".claude" / "agents" / "forge.md"
        return _sha256_file(substrate)
    if persona == "claude-main":
        # Utility-substrate: concat sorted truth-tag + aep-search archive shas
        tt = ARCHIVE_ROOT / "truth-tag.aepkg" / "aepkg.json"
        ae = ARCHIVE_ROOT / "aep-search.aepkg" / "aepkg.json"
        shas: list[str] = []
        for path in (tt, ae):
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            ext = data.get("extensions", {})
            sha = ext.get("canonical_md_sha256") or ext.get("sha256_of_canonical_md")
            if sha:
                shas.append(sha)
        if not shas:
            return None
        return _sha256_concat(shas)
    # Source-meshed: hash of concat(sorted(source canonical_md_sha256))
    shas = _read_persona_sources(persona)
    if not shas:
        return None
    return _sha256_concat(shas)


def _build_counter_claim(persona: str) -> CounterClaim:
    spec = COUNTER_CLAIM_SPEC[persona]
    sha: Optional[str] = None
    if spec["internal_path"]:
        full = REPO_ROOT / spec["internal_path"]
        sha = _sha256_file(full)
    return CounterClaim(
        counter_claim_uri=spec["uri"],
        counter_claim_type=spec["type"],
        counter_claim_authored_by=spec["authored_by"],
        counter_claim_strength=spec["strength"],
        authored_at_utc=AUTHORED_AT,
        counter_claim_sha256=sha,
    )


def emit_for_persona(persona: str) -> dict:
    """Emit counter_claim + lineage_predecessor_hash backfill for one persona.

    Returns a per-persona status dict:
      {
        "persona": str,
        "counter_claim_validation": "PASS" | "FAIL",
        "counter_claim_reasons": [(rule, severity, message), ...],
        "lineage_predecessor_hash": str | None,
        "manifest_updated": bool,
      }
    """
    manifest = SKILLS_ROOT / f"{persona}.aepkg" / "aepkg.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))

    cc = _build_counter_claim(persona)
    # Validate before write
    claim = {"authored_by": persona}
    report = validate_counter_claim(claim, cc, repo_root=REPO_ROOT)

    # Mutate manifest: top-level counter_claims array + lineage_predecessor_hash
    data["counter_claims"] = serialize_counter_claim_list([cc])
    pred = _lineage_predecessor_for(persona)
    data["lineage_predecessor_hash"] = pred

    # Write back with sorted keys + UTF-8 + trailing newline (matches existing
    # AEP companion convention from convert_skill_to_aep.py).
    manifest.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "persona": persona,
        "counter_claim_validation": "PASS" if report.pass_ else "FAIL",
        "counter_claim_reasons": report.reasons,
        "lineage_predecessor_hash": pred,
        "manifest_updated": True,
    }


def main() -> int:
    print("=" * 80)
    print("Wave-019 emission: counter-claim binding + lineage_predecessor_hash backfill")
    print("=" * 80)
    n_pass = 0
    n_fail = 0
    n_backfilled = 0
    for persona in TWELVE_PERSONAS:
        result = emit_for_persona(persona)
        marker = "PASS" if result["counter_claim_validation"] == "PASS" else "FAIL"
        pred = result["lineage_predecessor_hash"] or "null"
        pred_short = pred[:24] + "..." if pred != "null" and len(pred) > 24 else pred
        print(f"  {marker:4s} {persona:14s} pred={pred_short}")
        if result["counter_claim_validation"] == "PASS":
            n_pass += 1
        else:
            n_fail += 1
            for rule, sev, msg in result["counter_claim_reasons"]:
                print(f"          {sev:4s} {rule}: {msg}")
        if result["lineage_predecessor_hash"] is not None:
            n_backfilled += 1
    print("=" * 80)
    print(f"counter_claim validation: {n_pass}/12 PASS, {n_fail}/12 FAIL")
    print(f"lineage_predecessor_hash: {n_backfilled}/12 backfilled")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
