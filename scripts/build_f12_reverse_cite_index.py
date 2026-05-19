#!/usr/bin/env python3
"""build_f12_reverse_cite_index.py - F12 source_reverse_citation columnar index.

AEP v1.1 F12 source_reverse_citation variant (sec3.4 row 8). Builds a
{source_id_canonical: [packet_ids[]]} reverse-lookup map by scanning every
.aepkg packet's data/sources.jsonl in the corpus. Writes the map to a single
JSONL file under recall/reverse_cite/source_index.jsonl with one row per
source_id.

Query API: query_reverse_cite(source_id) -> [packet_ids] in O(1) hash lookup
after a one-time index load. Benchmark mode times 1000 random queries.

Composes_with: AEP v1.1 sec3.4 source_reverse_citation row; F12 schema
key_grain=source_id. Stdlib-only (json + pathlib + time).
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import random
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _iter_jsonl(p: pathlib.Path) -> Iterable[Dict[str, Any]]:
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    except OSError:
        return


def _extract_source_id(row: Dict[str, Any]) -> Optional[str]:
    """Canonicalize a source's identity. Prefer explicit id; fallback to sha256+url."""
    for k in ("source_id", "id", "uri", "url", "source"):
        v = row.get(k)
        if isinstance(v, str) and v:
            return v.strip()
    # Final fallback: synthesize from sha256 if present
    sha = row.get("sha256") or row.get("hash")
    if isinstance(sha, str) and sha:
        return f"sha256:{sha}" if not sha.startswith("sha256:") else sha
    return None


def scan_sources(corpus_root: pathlib.Path, verbose: bool = False) -> Dict[str, List[str]]:
    """Walk all .aepkg dirs; build {source_id: [packet_ids]} reverse map."""
    rev: Dict[str, List[str]] = {}
    if not corpus_root.exists():
        return rev

    aepkg_dirs = [p for p in corpus_root.rglob("*.aepkg") if p.is_dir()]
    if verbose:
        print(f"[F12-revcite] scan: {len(aepkg_dirs)} .aepkg dirs", file=sys.stderr)

    for pkg_dir in aepkg_dirs:
        try:
            packet_id = str(pkg_dir.relative_to(corpus_root)).replace("\\", "/")
        except ValueError:
            packet_id = str(pkg_dir).replace("\\", "/")
        sources_path = pkg_dir / "data" / "sources.jsonl"
        if not sources_path.is_file():
            continue
        seen_in_packet: set = set()
        for row in _iter_jsonl(sources_path):
            sid = _extract_source_id(row)
            if not sid or sid in seen_in_packet:
                continue
            seen_in_packet.add(sid)
            rev.setdefault(sid, []).append(packet_id)
    return rev


def build_reverse_cite_index(corpus_root: pathlib.Path, recall_root: pathlib.Path,
                             verbose: bool = False) -> Dict[str, Any]:
    """Build reverse-cite index; write to recall/reverse_cite/source_index.jsonl."""
    rev = scan_sources(corpus_root, verbose=verbose)
    out_dir = recall_root / "reverse_cite"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "source_index.jsonl"

    with out_path.open("w", encoding="utf-8") as fp:
        for sid, packet_ids in sorted(rev.items()):
            row = {
                "type": "F12ReverseCiteEntry",
                "schema_version": "aep-recall-layer-index-0.1",
                "source_id": sid,
                "packet_ids": sorted(set(packet_ids)),
                "citation_count": len(set(packet_ids)),
            }
            fp.write(json.dumps(row, separators=(",", ":")) + "\n")

    manifest = {
        "type": "F12ReverseCiteManifest",
        "schema_version": "aep-recall-layer-index-0.1",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "corpus_root": str(corpus_root).replace("\\", "/"),
        "unique_source_ids": len(rev),
        "total_citations": sum(len(v) for v in rev.values()),
        "index_path": str(out_path.relative_to(recall_root)).replace("\\", "/"),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


class ReverseCiteIndex:
    """Loaded F12 reverse-cite index for query-time use. O(1) lookup."""

    def __init__(self, recall_root: pathlib.Path):
        idx_path = recall_root / "reverse_cite" / "source_index.jsonl"
        if not idx_path.is_file():
            raise FileNotFoundError(f"reverse-cite index missing: {idx_path}")
        self.map: Dict[str, List[str]] = {}
        for row in _iter_jsonl(idx_path):
            sid = row.get("source_id")
            pids = row.get("packet_ids", [])
            if isinstance(sid, str) and isinstance(pids, list):
                self.map[sid] = pids

    def query(self, source_id: str) -> List[str]:
        return self.map.get(source_id, [])


def benchmark_reverse_cite(recall_root: pathlib.Path, n_queries: int = 1000,
                           seed: int = 0xCAFE) -> Dict[str, Any]:
    """Time N random queries; mix of present + absent source_ids."""
    idx = ReverseCiteIndex(recall_root)
    keys = list(idx.map.keys())
    if not keys:
        return {"error": "empty index", "n_queries": 0}

    rng = random.Random(seed)
    samples_ns: List[int] = []

    # warmup
    for _ in range(50):
        idx.query(rng.choice(keys))

    for _ in range(n_queries):
        # 70% present (likely hit), 30% absent
        if rng.random() < 0.7:
            sid = rng.choice(keys)
        else:
            sid = f"absent_source_{rng.randrange(1<<32):x}"
        t0 = time.perf_counter_ns()
        _ = idx.query(sid)
        t1 = time.perf_counter_ns()
        samples_ns.append(t1 - t0)

    samples_ns.sort()
    n = len(samples_ns)
    return {
        "n_queries": n,
        "p50_us": samples_ns[int(n * 0.50)] / 1000.0,
        "p99_us": samples_ns[min(int(n * 0.99), n - 1)] / 1000.0,
        "p999_us": samples_ns[min(int(n * 0.999), n - 1)] / 1000.0,
        "min_us": samples_ns[0] / 1000.0,
        "max_us": samples_ns[-1] / 1000.0,
        "unique_source_ids": len(idx.map),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="F12 reverse-cite columnar index.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_b = sub.add_parser("build")
    p_b.add_argument("--corpus-root", required=True)
    p_b.add_argument("--recall-root", required=True)
    p_b.add_argument("--verbose", action="store_true")

    p_q = sub.add_parser("query")
    p_q.add_argument("--recall-root", required=True)
    p_q.add_argument("--source-id", required=True)

    p_bench = sub.add_parser("benchmark")
    p_bench.add_argument("--recall-root", required=True)
    p_bench.add_argument("--n", type=int, default=1000)

    args = parser.parse_args()

    if args.cmd == "build":
        manifest = build_reverse_cite_index(
            pathlib.Path(args.corpus_root),
            pathlib.Path(args.recall_root),
            verbose=args.verbose,
        )
        print(json.dumps({"ok": True, **manifest}, indent=2))
        return 0
    if args.cmd == "query":
        idx = ReverseCiteIndex(pathlib.Path(args.recall_root))
        print(json.dumps({"source_id": args.source_id, "packet_ids": idx.query(args.source_id)}, indent=2))
        return 0
    if args.cmd == "benchmark":
        result = benchmark_reverse_cite(pathlib.Path(args.recall_root), n_queries=args.n)
        print(json.dumps(result, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
