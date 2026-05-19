"""skill_lineage_dag.py - Wave-013 scaffold for Lamport-Chained Skill Lineage Merkle DAG.

Authored under AEP-22-TO-12-SKILL-CONSOLIDATION-WAVE-013-FORGE
(task 2026-05-17T0645-w013-task-01). Composes with strategist Wave-011
top-frontier-pick + pathfinder P3 perfection-metric requirement.

Pilot: each skill's `.aepkg/aepkg.json` carries
  - `lamport_counter` (monotonic version counter; starts at 1)
  - `lineage_predecessor_hash` (sha256 of previous version's canonical
    `SKILL.md`, or null for the first version)

Wave-013 scope: scaffold only. Single-version chains (counter=1 +
predecessor=null) validate as integrity-clean. Multi-version chain
verification + Merkle-root computation + consolidated-skill merge
deferred to Wave-014.

Wave-019 lineage_predecessor_hash backfill rule (closes cross-persona
HIGH gap surfaced by Wave-017 12-lens fan-out):
  - Source-meshed persona (1+ doctrine/lesson source):
      predecessor = sha256(concat(sorted(source canonical_md_sha256)))
      The hash is deterministic in sorted source-sha order. Sources whose
      canonical hash was not captured at conversion time fall back to a
      deterministic stand-in: sha256(source.location.value bytes).
  - visual-judge (PROMOTE-1-source same-name, mutated-in-place):
      predecessor = pre-edit Wave-013 sha (recovered from git commit
      1229a90ad before the wave-016 mutation;
      sha256:affeb19fd86de0177f5293f39f709ce392e3edbf0fc7dd4731e279b33055c25a).
  - forge (MINT-FROM-SUBSTRATE; n_sources=0):
      predecessor = sha256(.claude/agents/forge.md bytes at emission time).
      Substrate already captured as in_packet_file source's location_hash.
  - claude-main (utility-substrate, cross-cutting):
      predecessor = sha256(concat(sorted(truth-tag + aep-search archive
      canonical_md_sha256))).

Implementation: see `emit_counter_claims_wave_019.py` for the one-shot
emission script that filled `lineage_predecessor_hash` on all 12 canonical
persona companions 2026-05-17T1215Z.

Truth tag: STRONGLY PLAUSIBLE - signatures + happy-path verification
exercised by test_skill_lineage_dag.py. Cross-version chain semantics
still pending operator approval on the consolidation source-of-truth
model (concat-of-hashes vs jsonl-of-events vs git-commit-ref).

Fail behavior: fail-CLOSED on missing aepkg.json (FileNotFoundError);
fail-CLOSED on malformed JSON (json.JSONDecodeError); fail-CLOSED on
missing lamport_counter field (KeyError surfaced via verify=False).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[5]
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"


def _load_aepkg_manifest(skill_name: str, skills_root: Optional[Path] = None) -> dict:
    """Load aepkg.json for a given skill slug. Raises FileNotFoundError on miss."""
    root = skills_root or SKILLS_ROOT
    pkg = root / f"{skill_name}.aepkg"
    manifest = pkg / "aepkg.json"
    if not manifest.exists():
        raise FileNotFoundError(f"aepkg.json not found at {manifest}")
    return json.loads(manifest.read_text(encoding="utf-8"))


def read_lineage_chain(
    skill_name: str,
    skills_root: Optional[Path] = None,
) -> list[tuple[int, str, Optional[str]]]:
    """Return list of (lamport_counter, canonical_sha256, predecessor_hash) tuples.

    Wave-013 scaffold: returns a single-tuple list reflecting the current
    head of the chain. Wave-014 will hydrate a multi-version history from
    `ops/events.jsonl` (`event_type=skill_revision`) and/or from a planned
    `lineage/chain.jsonl` companion file.
    """
    data = _load_aepkg_manifest(skill_name, skills_root=skills_root)
    counter = data.get("lamport_counter")
    predecessor = data.get("lineage_predecessor_hash")
    canonical_sha = data.get("extensions", {}).get("canonical_md_sha256") or data.get(
        "extensions", {}
    ).get("sha256_of_canonical_md")
    if counter is None:
        raise KeyError(
            f"lamport_counter missing from {skill_name}.aepkg/aepkg.json "
            "(run Wave-013 foundation pass)"
        )
    return [(int(counter), canonical_sha or "", predecessor)]


def verify_chain_integrity(
    skill_name: str,
    skills_root: Optional[Path] = None,
) -> bool:
    """Verify a skill's lineage chain is integrity-clean.

    Returns True iff:
      - counter sequence is monotonic increasing (1, 2, 3, ...)
      - first entry's predecessor_hash is None
      - every subsequent entry's predecessor_hash matches the prior
        entry's canonical_sha256

    For single-version chains (counter=1 + predecessor=null), returns True
    by construction.

    Raises KeyError if lamport_counter is missing (fail-CLOSED) to surface
    foundation-pass omissions immediately rather than silently returning
    False.
    """
    chain = read_lineage_chain(skill_name, skills_root=skills_root)

    # Monotonic counter check
    for idx, (counter, _sha, _pred) in enumerate(chain, start=1):
        if counter != idx:
            return False

    # First-entry predecessor must be None
    _first_counter, _first_sha, first_pred = chain[0]
    if first_pred is not None:
        return False

    # Subsequent links: predecessor matches prior canonical_sha256
    for prior, curr in zip(chain, chain[1:]):
        _pc, prior_sha, _pp = prior
        _cc, _cs, curr_pred = curr
        if curr_pred != prior_sha:
            return False

    return True


def global_lineage_dag(
    skills_root: Optional[Path] = None,
) -> dict[str, list[tuple[int, str, Optional[str]]]]:
    """Build the global lineage DAG across all skills.

    Returns dict mapping skill_slug -> chain (as returned by read_lineage_chain).
    Skips skills whose aepkg.json is missing OR lacks lamport_counter
    (entry omitted; not an exception).
    """
    root = skills_root or SKILLS_ROOT
    dag: dict[str, list[tuple[int, str, Optional[str]]]] = {}
    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir() or not pkg.name.endswith(".aepkg"):
            continue
        slug = pkg.name[: -len(".aepkg")]
        try:
            dag[slug] = read_lineage_chain(slug, skills_root=root)
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            continue
    return dag


def main() -> int:
    """CLI entry: print the global lineage DAG + integrity report."""
    dag = global_lineage_dag()
    print(f"SKILL-Lineage-DAG: {len(dag)} skills")
    n_pass = 0
    n_fail = 0
    for slug in sorted(dag):
        ok = verify_chain_integrity(slug)
        marker = "OK" if ok else "FAIL"
        chain = dag[slug]
        head_counter, head_sha, head_pred = chain[-1]
        sha_short = head_sha[:16] if head_sha else "(none)"
        pred_short = (head_pred[:16] + "...") if head_pred else "null"
        print(f"  {marker:4s} {slug:40s} counter={head_counter} sha={sha_short}... pred={pred_short}")
        if ok:
            n_pass += 1
        else:
            n_fail += 1
    print(f"Result: {n_pass} integrity-clean, {n_fail} broken")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
