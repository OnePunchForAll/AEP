"""
transition_parser.py — Bidirectional transition parser for the AEP/HTML-MD substrate.

Owner: forge.
Phase: Phase-2 mass-conversion infrastructure per operator directive 2026-05-14
("transition parser that perfectly connects to these .html and .md files so we have
a loss-less architecture").

This module is the connective tissue between the canonical .html/.md authoring
surface and the queryable .aepkg/ compounding-substrate. Three primary APIs:

  find_packet_for_source(source_path) -> packet_path | None
      Given a .html/.md path, locate the corresponding .aepkg/ packet (if converted).

  source_for_packet(packet_path) -> source_path
      Given an .aepkg/ path, return the original .html/.md path it was derived from.

  read_packet_lossless(packet_path) -> dict
      Open a packet and return both the structured records AND the byte-perfect
      original-source preserved in assets/original.<ext>. The loss-less guarantee:
      sha256 of assets/original.<ext> MUST match the manifest's aep:original_sha256.

  reconstruct_html_from_packet(packet_path, out_path) -> sha256
      Write the byte-perfect original .html/.md to out_path (used when an agent
      needs the narrative form). Verifies sha256 before writing.

  packet_query(packet_path, **filters) -> List[Claim]
      Filter claims by section_id / axis_a / axis_b / kind / text-substring.
      Returns typed claim records.

  agent_view(source_path_or_packet_path) -> dict
      The all-in-one agent entry point: given either a source or packet path,
      return the dual-mode view (structured query API + narrative pointer).

Test:
  python -m aep.transition_parser <source-or-packet-path>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# --- Path resolution ---
def repo_root() -> Path:
    """Heuristic: walk up from this file until we find a directory with doctrine/ + .claude/."""
    p = Path(__file__).resolve()
    for ancestor in [p, *p.parents]:
        if (ancestor / "doctrine").is_dir() and (ancestor / ".claude").is_dir():
            return ancestor
    raise RuntimeError("Could not locate AEP project repo root from " + str(p))


CONVERTED_ROOT_REL = Path("projects") / "v11-aep" / "converted"


def source_to_packet_path(source_path: Path, root: Optional[Path] = None) -> Path:
    """Map a .html/.md source path to its expected .aepkg/ packet location under projects/v11-aep/converted/."""
    root = root or repo_root()
    source_path = source_path.resolve()
    rel = source_path.relative_to(root)
    # Map original-tree section to converted-tree section
    parts = rel.parts
    if parts[0] == "doctrine" and len(parts) >= 2 and parts[1] == "lessons":
        kind = "lessons"
        stem = source_path.stem
    elif parts[0] == "doctrine" and len(parts) >= 2 and parts[1] == "_proposals":
        kind = "proposals"
        stem = source_path.stem
    elif parts[0] == "doctrine" and len(parts) >= 2 and parts[1] == "agents":
        kind = "agents"
        stem = source_path.stem
    elif parts[0] == "doctrine":
        kind = "doctrine"
        stem = source_path.stem
    elif parts[0] == "research" and len(parts) >= 4 and parts[1] == "analysis" and parts[3] == "analysis.html":
        kind = "analysis"
        stem = parts[2]
    else:
        # Unknown mapping; fall back to flat naming
        kind = "other"
        stem = source_path.stem
    return root / CONVERTED_ROOT_REL / kind / f"{stem}.aepkg"


def find_packet_for_source(source_path: Path) -> Optional[Path]:
    """Return the packet dir if it exists; else None."""
    expected = source_to_packet_path(source_path)
    return expected if expected.exists() else None


def source_for_packet(packet_path: Path) -> Optional[Path]:
    """Read aepkg.json and return the original source_lesson path."""
    manifest_path = packet_path / "aepkg.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rel = manifest.get("extensions", {}).get("aep:source_lesson")
    if not source_rel:
        return None
    p = Path(source_rel)
    if not p.is_absolute():
        p = repo_root() / p
    return p if p.exists() else None


# --- Loss-less reconstruction ---
def read_packet_lossless(packet_path: Path) -> Dict[str, Any]:
    """Open a packet and load: manifest + claims + sources + spans + relations + original bytes."""
    manifest = json.loads((packet_path / "aepkg.json").read_text(encoding="utf-8"))

    def load_jsonl(rel: str) -> List[Dict[str, Any]]:
        p = packet_path / rel
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    claims = load_jsonl("data/claims.jsonl")
    sources = load_jsonl("data/sources.jsonl")
    spans = load_jsonl("data/spans.jsonl")
    relations = load_jsonl("data/relations.jsonl")

    # Locate preserved original
    preserved_rel = manifest.get("extensions", {}).get("aep:original_preserved_at")
    original_path = packet_path / preserved_rel if preserved_rel else None
    original_bytes = original_path.read_bytes() if original_path and original_path.exists() else None

    # Verify sha256 integrity of the preserved original
    expected_sha = manifest.get("extensions", {}).get("aep:original_sha256", "")
    actual_sha = None
    integrity_ok = None
    if original_bytes is not None:
        actual_sha = "sha256:" + hashlib.sha256(original_bytes).hexdigest()
        integrity_ok = (actual_sha == expected_sha)

    return {
        "manifest": manifest,
        "claims": claims,
        "sources": sources,
        "spans": spans,
        "relations": relations,
        "original_bytes": original_bytes,
        "original_sha256_expected": expected_sha,
        "original_sha256_actual": actual_sha,
        "integrity_ok": integrity_ok,
    }


def reconstruct_html_from_packet(packet_path: Path, out_path: Path, verify: bool = True) -> str:
    """Write the byte-perfect preserved original to out_path. Returns sha256 of bytes written."""
    pkt = read_packet_lossless(packet_path)
    if pkt["original_bytes"] is None:
        raise FileNotFoundError(f"Packet {packet_path} has no preserved original")
    if verify and pkt["integrity_ok"] is False:
        raise ValueError(f"Integrity check FAILED for {packet_path}: expected {pkt['original_sha256_expected']} got {pkt['original_sha256_actual']}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pkt["original_bytes"])
    return pkt["original_sha256_actual"] or ""


# --- Structured query API ---
def packet_query(
    packet_path: Path,
    section_id_contains: Optional[str] = None,
    axis_a: Optional[str] = None,
    axis_b: Optional[str] = None,
    kind: Optional[str] = None,
    text_contains: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter claims in a single packet by structural and full-text criteria."""
    pkt = read_packet_lossless(packet_path)
    out: List[Dict[str, Any]] = []
    for c in pkt["claims"]:
        if section_id_contains and section_id_contains.lower() not in (c.get("aep:section_id") or "").lower():
            continue
        if axis_a and (c.get("aep:axis_a_epistemic") or "") != axis_a:
            continue
        if axis_b and (c.get("aep:axis_b_action") or "") != axis_b:
            continue
        if kind and (c.get("aep:kind") or "") != kind:
            continue
        if text_contains and text_contains.lower() not in (c.get("text") or "").lower():
            continue
        out.append(c)
    return out


def corpus_query(
    converted_root: Optional[Path] = None,
    **filters: Any,
) -> List[Dict[str, Any]]:
    """Run packet_query across every .aepkg/ under projects/v11-aep/converted/. Returns flat list of matches."""
    root = converted_root or (repo_root() / CONVERTED_ROOT_REL)
    out: List[Dict[str, Any]] = []
    for packet_dir in sorted(root.rglob("*.aepkg")):
        if not packet_dir.is_dir():
            continue
        matches = packet_query(packet_dir, **filters)
        for m in matches:
            m["__packet"] = str(packet_dir.relative_to(repo_root())).replace("\\", "/")
            out.append(m)
    return out


# --- Agent dual-mode view ---
def agent_view(path: Path) -> Dict[str, Any]:
    """One-stop agent entry point. Accepts EITHER a .html/.md source path OR an .aepkg/ packet path.

    Returns a unified dict with:
      - source_path: path to the canonical .html/.md (always present)
      - packet_path: path to .aepkg/ (None if not yet converted)
      - has_packet: bool
      - is_lossless: bool (sha256 of preserved original matches manifest record)
      - manifest, claims, sources, spans, relations: structured records (if packet exists)
    """
    if path.suffix == "":
        # Likely a packet directory
        packet_path = path
        source_path = source_for_packet(packet_path)
    else:
        source_path = path
        packet_path = find_packet_for_source(source_path)

    out: Dict[str, Any] = {
        "source_path": str(source_path).replace("\\", "/") if source_path else None,
        "packet_path": str(packet_path).replace("\\", "/") if packet_path else None,
        "has_packet": packet_path is not None and packet_path.exists(),
        "is_lossless": None,
    }

    if out["has_packet"]:
        pkt = read_packet_lossless(packet_path)
        out["is_lossless"] = bool(pkt["integrity_ok"])
        out["manifest"] = pkt["manifest"]
        out["claim_count"] = len(pkt["claims"])
        out["source_count"] = len(pkt["sources"])
        out["span_count"] = len(pkt["spans"])
        out["relation_count"] = len(pkt["relations"])
        out["state_hash"] = pkt["manifest"].get("integrity", {}).get("state_hash", "")
    else:
        out["claim_count"] = out["source_count"] = out["span_count"] = out["relation_count"] = 0

    return out


# --- Corpus index (build-once, query-many-times) ---------------------------------
class CorpusIndex:
    """In-memory index over all converted AEP packets. Build cost amortizes across N queries."""

    def __init__(self, converted_root: Optional[Path] = None) -> None:
        self.root = converted_root or (repo_root() / CONVERTED_ROOT_REL)
        self.claims: List[Dict[str, Any]] = []
        self.sources: List[Dict[str, Any]] = []
        self.relations: List[Dict[str, Any]] = []
        self.by_packet: Dict[str, List[Dict[str, Any]]] = {}
        self.by_axis_a: Dict[str, List[Dict[str, Any]]] = {}
        self.by_section: Dict[str, List[Dict[str, Any]]] = {}
        self.by_kind: Dict[str, List[Dict[str, Any]]] = {}
        self.sources_by_location_substring: List[Any] = []
        self._build_time_seconds: float = 0.0

    def build(self) -> "CorpusIndex":
        import time as _t
        start = _t.perf_counter()
        for packet_dir in sorted(self.root.rglob("*.aepkg")):
            if not packet_dir.is_dir():
                continue
            packet_rel = str(packet_dir.relative_to(repo_root())).replace("\\", "/")
            cf = packet_dir / "data" / "claims.jsonl"
            if cf.exists():
                for line in cf.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        c = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    c["__packet"] = packet_rel
                    self.claims.append(c)
                    self.by_packet.setdefault(packet_rel, []).append(c)
                    self.by_axis_a.setdefault(c.get("aep:axis_a_epistemic") or c.get("reliability") or "UNKNOWN", []).append(c)
                    self.by_section.setdefault(c.get("aep:section_id") or "", []).append(c)
                    self.by_kind.setdefault(c.get("aep:kind") or "", []).append(c)
            sf = packet_dir / "data" / "sources.jsonl"
            if sf.exists():
                for line in sf.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        s = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    s["__packet"] = packet_rel
                    self.sources.append(s)
                    loc = s.get("location") or {}
                    loc_str = json.dumps(loc, ensure_ascii=False).lower() if isinstance(loc, dict) else str(loc).lower()
                    self.sources_by_location_substring.append((loc_str, s, packet_rel))
            rf = packet_dir / "data" / "relations.jsonl"
            if rf.exists():
                for line in rf.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    r["__packet"] = packet_rel
                    self.relations.append(r)
        self._build_time_seconds = _t.perf_counter() - start
        return self

    @property
    def build_time_ms(self) -> float:
        return self._build_time_seconds * 1000

    def query(self, *, axis_a: Optional[str] = None, axis_b: Optional[str] = None,
              section_id_contains: Optional[str] = None, kind: Optional[str] = None,
              text_contains: Optional[str] = None) -> List[Dict[str, Any]]:
        candidates = self.by_axis_a.get(axis_a, self.claims) if axis_a else self.claims
        out: List[Dict[str, Any]] = []
        text_lc = text_contains.lower() if text_contains else None
        section_lc = section_id_contains.lower() if section_id_contains else None
        for c in candidates:
            if axis_b and (c.get("aep:axis_b_action") or "") != axis_b:
                continue
            if section_lc and section_lc not in (c.get("aep:section_id") or "").lower():
                continue
            if kind and (c.get("aep:kind") or "") != kind:
                continue
            if text_lc and text_lc not in (c.get("text") or "").lower():
                continue
            out.append(c)
        return out

    def source_location_contains(self, substr: str) -> List[Dict[str, Any]]:
        substr_lc = substr.lower()
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for loc_str, source_rec, packet_rel in self.sources_by_location_substring:
            if substr_lc in loc_str and packet_rel not in seen:
                seen.add(packet_rel)
                out.append({"packet": packet_rel, "source": source_rec})
        return out


def build_corpus_index(converted_root: Optional[Path] = None) -> CorpusIndex:
    return CorpusIndex(converted_root).build()


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: python -m aep.transition_parser <source-or-packet-path> [--query section=X | text=Y]", file=sys.stderr)
        return 2

    path = Path(argv[0]).resolve()
    view = agent_view(path)
    print(json.dumps(view, indent=2, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
