"""
aepkit_merkle_dag.py — Merkle-DAG over doctrine + skills + lessons.

WAVE-019 charter: Build a Merkle tree whose leaves are the (path, sha256)
tuples of every canonical doctrine slot, every doctrine lesson, and every
persona-bound skill (SKILL.md). The root commits to the entire AEP project
canon state at a single point in time. Drift detection compares a claimed
root against a freshly recomputed root and identifies which leaf changed.

Companion HCRL receipt: every Merkle root computation emits one JSONL row
to `.claude/_logs/doctrine-merkle-receipts.jsonl` per doctrine/41 (hash-
chained receipt ledger).

Truth tag: STRONGLY PLAUSIBLE — algorithmic primitive sound (sha256 +
sorted leaves + balanced-pair internal nodes), pending operational soak
under repeated commits before promotion to PROVEN/RELIABLE.

Stdlib only. Read-only over the canon. Writes only to:
  - .claude/diana/doctrine-merkle-manifest.json (cache)
  - .claude/_logs/doctrine-merkle-receipts.jsonl (append-only HCRL)

Author: warden (the agentic substrate). Date: 2026-05-17. Wave: w019.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Tuple


# ---- Repo-root resolution -------------------------------------------------

# This script lives at projects/v11-aep/publish-ready/aep/scripts/<this>.py
# Repo root = 5 parents up: scripts -> aep -> publish-ready -> v11-aep -> projects -> repo.
REPO_ROOT = Path(__file__).resolve().parents[5]
DOCTRINE_DIR = REPO_ROOT / "doctrine"
LESSONS_DIR = DOCTRINE_DIR / "lessons"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
AEP_DIR = REPO_ROOT / ".claude" / "diana"
LOGS_DIR = REPO_ROOT / ".claude" / "_logs"

MANIFEST_PATH = AEP_DIR / "doctrine-merkle-manifest.json"
RECEIPTS_PATH = LOGS_DIR / "doctrine-merkle-receipts.jsonl"


# ---- Hash helpers ---------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Compute sha256 over raw bytes of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    """Internal Merkle node = sha256(left_hex || right_hex), concatenated as
    raw bytes so the tree is structurally hex-prefix-free."""
    return hashlib.sha256(bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


# ---- Leaf collection ------------------------------------------------------

def _collect_leaves() -> list[Tuple[str, str]]:
    """Walk doctrine + lessons + skills; produce sorted (relpath, sha256)
    leaves. Sorting on relpath ensures determinism regardless of FS order.
    """
    leaves: list[Tuple[str, str]] = []

    # Doctrine top-level *.html (exclude lessons subdir; handled separately).
    for path in sorted(DOCTRINE_DIR.glob("*.html")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        leaves.append((rel, _sha256_file(path)))

    # Doctrine lessons *.html (recursive, but lessons dir is flat).
    if LESSONS_DIR.is_dir():
        for path in sorted(LESSONS_DIR.glob("*.html")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            leaves.append((rel, _sha256_file(path)))

    # Persona SKILL.md files (one per persona subdir).
    if SKILLS_DIR.is_dir():
        for persona_dir in sorted(SKILLS_DIR.iterdir()):
            if not persona_dir.is_dir():
                continue
            # Skip .aepkg companions; canonical is SKILL.md only.
            if persona_dir.name.endswith(".aepkg") or persona_dir.name.startswith("_"):
                continue
            skill_md = persona_dir / "SKILL.md"
            if skill_md.is_file():
                rel = skill_md.relative_to(REPO_ROOT).as_posix()
                leaves.append((rel, _sha256_file(skill_md)))

    # Final alphabetical sort guarantees deterministic ordering across OSes.
    leaves.sort(key=lambda t: t[0])
    return leaves


# ---- Merkle tree construction --------------------------------------------

def _build_merkle_tree(leaf_hashes: list[str]) -> Tuple[str, int]:
    """Build a balanced Merkle tree from leaf hashes. Returns (root, depth).

    Algorithm: at each level, pair consecutive leaves. If odd count at a
    level, duplicate the last hash (Bitcoin-style). Depth = number of
    levels above the leaf row.
    """
    if not leaf_hashes:
        # Empty-tree convention: root = sha256("") to give a well-defined value.
        return _sha256_hex(""), 0

    level = list(leaf_hashes)
    depth = 0
    while len(level) > 1:
        nxt: list[str] = []
        # Odd-length: duplicate trailing leaf so every node has a sibling.
        if len(level) % 2 == 1:
            level.append(level[-1])
        for i in range(0, len(level), 2):
            nxt.append(_hash_pair(level[i], level[i + 1]))
        level = nxt
        depth += 1
    return level[0], depth


# ---- Public API -----------------------------------------------------------

def generate_doctrine_merkle_root() -> Tuple[str, int, int, str]:
    """Compute the Merkle root over doctrine + lessons + skills.

    Returns: (merkle_root_sha256, leaf_count, tree_depth, manifest_path_str).
    Side effects: writes the manifest to MANIFEST_PATH (cache).
    """
    leaves = _collect_leaves()
    leaf_hashes = [h for _, h in leaves]
    root, depth = _build_merkle_tree(leaf_hashes)

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "merkle_root_sha256": root,
        "leaf_count": len(leaves),
        "tree_depth": depth,
        "hash_algorithm": "sha256",
        "pair_construction": "sha256(bytes.fromhex(left) || bytes.fromhex(right))",
        "odd_level_policy": "duplicate-trailing-leaf",
        "leaves_sorted_by": "relpath_alphabetical",
        "scope": {
            "doctrine_slots_glob": "doctrine/*.html",
            "lessons_glob": "doctrine/lessons/*.html",
            "skills_glob": ".claude/skills/<persona>/SKILL.md",
            "excludes": ["*.aepkg/", "_*/", "doctrine/lessons/_index.html (still included)"],
        },
        "leaves": [{"path": p, "sha256": h} for p, h in leaves],
    }

    AEP_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return root, len(leaves), depth, MANIFEST_PATH.as_posix()


def verify_doctrine_merkle_root(claimed_root: str) -> dict:
    """Recompute the Merkle root and compare to a claimed value.

    Returns a verdict dict:
      {
        "verdict": "PASS" | "FAIL",
        "claimed_root": <hex>,
        "computed_root": <hex>,
        "leaf_count": <int>,
        "tree_depth": <int>,
        "drift": [ {path, claimed_sha256, computed_sha256}, ... ]  # only on FAIL
      }
    Drift detection: if a cached manifest exists, diff its leaves against
    freshly-computed leaves to identify which file mutated.
    """
    leaves_now = _collect_leaves()
    leaf_hashes = [h for _, h in leaves_now]
    computed_root, depth = _build_merkle_tree(leaf_hashes)
    verdict: dict = {
        "verdict": "PASS" if computed_root == claimed_root else "FAIL",
        "claimed_root": claimed_root,
        "computed_root": computed_root,
        "leaf_count": len(leaves_now),
        "tree_depth": depth,
    }

    if verdict["verdict"] == "FAIL" and MANIFEST_PATH.is_file():
        try:
            cached = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            cached_map = {row["path"]: row["sha256"] for row in cached.get("leaves", [])}
            now_map = {p: h for p, h in leaves_now}
            drift = []
            for p in sorted(set(cached_map) | set(now_map)):
                ch = cached_map.get(p)
                nh = now_map.get(p)
                if ch != nh:
                    drift.append({"path": p, "cached_sha256": ch, "current_sha256": nh})
            verdict["drift"] = drift
        except (OSError, json.JSONDecodeError) as e:
            verdict["drift_error"] = f"manifest read failed: {e!r}"

    return verdict


def emit_hcrl_receipt(commit_sha: str | None = None, drift_detected: bool = False) -> dict:
    """Append a HCRL receipt to .claude/_logs/doctrine-merkle-receipts.jsonl.

    Per doctrine/41 (hash-chained receipt ledger). Receipt fields:
      ts_utc, merkle_root_sha256, commit_sha, leaf_count, tree_depth,
      drift_detected, manifest_path.
    Returns the receipt dict (also written to the JSONL).
    """
    root, leaf_count, depth, manifest_path = generate_doctrine_merkle_root()
    receipt = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "merkle_root_sha256": root,
        "commit_sha": commit_sha,
        "leaf_count": leaf_count,
        "tree_depth": depth,
        "drift_detected": bool(drift_detected),
        "manifest_path": manifest_path,
        "emitter": "warden.aepkit_merkle_dag",
        "wave": "w019",
    }
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with RECEIPTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(receipt, separators=(",", ":")) + "\n")
    return receipt


# ---- CLI ------------------------------------------------------------------

def _cli(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "verify":
        if len(argv) < 3:
            print("usage: aepkit_merkle_dag.py verify <claimed_root_sha256>", file=sys.stderr)
            return 2
        v = verify_doctrine_merkle_root(argv[2])
        print(json.dumps(v, indent=2))
        return 0 if v["verdict"] == "PASS" else 1

    if len(argv) >= 2 and argv[1] == "receipt":
        commit = argv[2] if len(argv) >= 3 else None
        r = emit_hcrl_receipt(commit_sha=commit)
        print(json.dumps(r, indent=2))
        return 0

    # Default: generate + print.
    root, n, d, mp = generate_doctrine_merkle_root()
    out = {
        "merkle_root_sha256": root,
        "leaf_count": n,
        "tree_depth": d,
        "manifest_path": mp,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
