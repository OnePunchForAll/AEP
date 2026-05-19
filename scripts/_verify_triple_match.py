"""Verify the integrity bridge: 10/10 sha256 triple-match.

For each canonical agent:
- A = sha256 of `.claude/agents/<agent>.md` raw bytes
- B = aepkg.json extensions.canonical_md_sha256 (declared)
- C = sha256 of `.claude/agents/<agent>.aepkg/views/source.md` raw bytes

All three must match. Drift = BLOCK.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path("C:/Users/example-user/")
CANONICAL_AGENTS = [
    "adversary", "curator", "forge", "judge", "pathfinder",
    "scout", "scribe", "strategist", "warden", "visual-judge",
]


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(agent: str) -> tuple[bool, str, str, str, str]:
    md = REPO_ROOT / ".claude" / "agents" / f"{agent}.md"
    pkg = REPO_ROOT / ".claude" / "agents" / f"{agent}.aepkg"
    aepkg_json = pkg / "aepkg.json"
    view = pkg / "views" / "source.md"
    a = sha256_hex(md)
    c = sha256_hex(view)
    manifest = json.loads(aepkg_json.read_text(encoding="utf-8"))
    b_raw = manifest.get("extensions", {}).get("canonical_md_sha256", "")
    b = b_raw.replace("sha256:", "") if b_raw.startswith("sha256:") else b_raw
    ok = (a == b == c)
    return ok, agent, a[:16], b[:16], c[:16]


def main():
    print(f"{'agent':<14} {'match':<6} {'md':<16} {'aepkg.json':<16} {'views/source.md':<16}")
    print("-" * 76)
    n_ok = 0
    for agent in CANONICAL_AGENTS:
        ok, name, a, b, c = verify(agent)
        flag = "PASS" if ok else "FAIL"
        if ok:
            n_ok += 1
        print(f"{name:<14} {flag:<6} {a:<16} {b:<16} {c:<16}")
    print()
    print(f"TRIPLE-MATCH: {n_ok}/{len(CANONICAL_AGENTS)}")
    return n_ok == len(CANONICAL_AGENTS)


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
