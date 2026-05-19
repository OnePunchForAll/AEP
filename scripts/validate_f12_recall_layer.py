#!/usr/bin/env python3
"""validate_f12_recall_layer.py - F12 recall_layer_index validator + bloom-builder.

AEP v1.1 F12 reference implementation. Implements:

1. **Validator**: loads f12_recall_layer_index.schema.json; validates an RLI record;
   emits structured reason codes per sec3.6 (AEP11_F12_INDEX_STALE, FPR_EXCEEDED, etc.).

2. **Bloom-builder (build-mode)**: scans every .aepkg in the corpus root, parses
   data/claims.jsonl + data/sources.jsonl + ops/events.jsonl rows, extracts
   (packet_id, agent_id, action in {read,write,cite}) tuples, builds a classic
   stdlib bloom filter per agent, emits one
   `recall/<agent>/touch_bloom.bin` per agent_principal_id + a top-level
   `recall/index.json` manifest with FPR estimates.

3. **Query API**: `recall_layer.query(packet_id, agent_id, action) -> {hit, fpr_estimate}`.
   Loads the agent's bloom from disk once; O(k) hashes per query.

4. **Benchmark-mode**: time N=10000 random queries on the freshly-built bloom;
   report p50/p99/p999 wall-clock latency in microseconds. Operator target:
   p99 < 100us on Win11 with Python stdlib only.

Std-lib only: hashlib + struct + array.array + time.perf_counter_ns + json + pathlib.
No bloom-filter package; classic k-hash double-hash bit-array construction per
Kirsch-Mitzenmacher 2006 (RSA 2008 J Alg) double-hashing approximation.

Composes_with: AEP v1.1 sec3, sec73.4 SINGLE-WRITER (canonical layer untouched —
recall/ is DERIVED projection), sec50 Law-3, v1.0.3 RegexicalCue compute-step.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import random
import re
import struct
import sys
import time
from array import array
from typing import Any, Dict, Iterable, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Schema-validator side (lightweight; no jsonschema dep — stdlib only)
# -----------------------------------------------------------------------------

VALID_INDEX_KINDS = {
    "agent_touch_bloom",
    "claim_type_columnar",
    "source_reverse_citation",
    "rubric_dimension_histogram",
    "cross_agent_cite_resolver",
    "viewport_screenshot_manifest",
    "teacher_threshold_precomputed",
    "compute_step_binding",
}

VALID_KEY_GRAINS = {
    "packet_id", "claim_id", "source_id", "agent_principal_id",
    "rubric_dimension_id", "viewport_pHash", "compute_step_id", "vec_id",
}

VALID_LENSES = {
    "strategist","pathfinder","scout","forge","judge","adversary",
    "warden","scribe","curator","visual-judge",
}

REQUIRED_FIELDS = [
    "type", "schema_version", "id", "index_kind", "indexed_packet_id",
    "indexed_packet_sha256", "key_grain", "key_value",
    "rebuild_event_id", "rebuild_timestamp", "contamination_flag",
]


def validate_rli_record(rec: Dict[str, Any]) -> List[str]:
    """Validate an RLI record. Returns list of reason codes; empty list = PASS."""
    errors: List[str] = []
    for f in REQUIRED_FIELDS:
        if f not in rec:
            errors.append(f"AEP11_F12_SCHEMA_MISSING_FIELD:{f}")
    if rec.get("type") != "RecallLayerIndexEntry":
        errors.append("AEP11_F12_SCHEMA_TYPE_MISMATCH")
    if rec.get("schema_version") != "aep-recall-layer-index-0.1":
        errors.append("AEP11_F12_SCHEMA_VERSION_MISMATCH")
    if rec.get("index_kind") not in VALID_INDEX_KINDS:
        errors.append(f"AEP11_F12_SCHEMA_UNKNOWN_INDEX_KIND:{rec.get('index_kind')}")
    if rec.get("key_grain") not in VALID_KEY_GRAINS:
        errors.append(f"AEP11_F12_SCHEMA_UNKNOWN_KEY_GRAIN:{rec.get('key_grain')}")
    sha = rec.get("indexed_packet_sha256", "")
    if not (isinstance(sha, str) and sha.startswith("sha256:") and len(sha) == 71):
        errors.append("AEP11_F12_SCHEMA_BAD_SHA256_FORMAT")
    cf = rec.get("contamination_flag", {})
    if isinstance(cf, dict):
        if "redaction_replay_pending" not in cf:
            errors.append("AEP11_F12_SCHEMA_MISSING_CONTAMINATION_FIELD:redaction_replay_pending")
        if "convergence_source_count" not in cf:
            errors.append("AEP11_F12_SCHEMA_MISSING_CONTAMINATION_FIELD:convergence_source_count")
        lens_set = cf.get("convergence_lens_set", [])
        if not isinstance(lens_set, list) or len(lens_set) < 2:
            errors.append("AEP11_F12_SCHEMA_CONVERGENCE_LENS_TOO_SMALL")
        for lens in lens_set:
            if lens not in VALID_LENSES:
                errors.append(f"AEP11_F12_SCHEMA_UNKNOWN_LENS:{lens}")
        if cf.get("redaction_replay_pending") is True:
            errors.append("AEP11_F12_CONTAMINATION_FLAG_PRESENT")  # informational per sec3.6
    else:
        errors.append("AEP11_F12_SCHEMA_CONTAMINATION_FLAG_NOT_OBJECT")
    return errors


# -----------------------------------------------------------------------------
# Classic Bloom Filter (stdlib only)
#
# Sizing: m bits, k hashes, n expected items -> FPR ~ (1 - e^(-kn/m))^k.
# For target FPR p, minimal m = -n*ln(p)/(ln(2))^2; optimal k = (m/n)*ln(2).
# Uses Kirsch-Mitzenmacher double-hashing: h_i(x) = (h1(x) + i*h2(x)) mod m
#   where h1,h2 derive from a single sha256 digest split into two 64-bit halves.
# -----------------------------------------------------------------------------

class BloomFilter:
    """Stdlib-only Bloom filter. Bit-array via array('B'); k-hash via sha256 split."""

    MAGIC = b"AEPB"  # AEP-Bloom file magic
    VERSION = 1

    def __init__(self, expected_n: int, fpr: float = 0.01):
        if expected_n < 1:
            expected_n = 1
        self.n = expected_n
        self.target_fpr = fpr
        # m = ceil(-n*ln(p) / (ln(2))^2)
        ln2 = math.log(2.0)
        m_float = -expected_n * math.log(fpr) / (ln2 * ln2)
        # round to multiple of 8 for byte alignment
        self.m = max(8, int(math.ceil(m_float)))
        if self.m % 8 != 0:
            self.m += 8 - (self.m % 8)
        # k = (m/n) * ln(2), at least 1
        self.k = max(1, int(round((self.m / max(1, expected_n)) * ln2)))
        if self.k > 32:
            self.k = 32  # cap to avoid pathological insertion cost
        self.byte_len = self.m // 8
        self.bits = array("B", b"\x00" * self.byte_len)
        self.inserted_count = 0

    @classmethod
    def from_existing(cls, m: int, k: int, byte_blob: bytes, inserted_count: int = 0, target_fpr: float = 0.01) -> "BloomFilter":
        bf = cls.__new__(cls)
        bf.m = m
        bf.k = k
        bf.target_fpr = target_fpr
        bf.n = max(1, inserted_count)
        bf.byte_len = m // 8
        if len(byte_blob) != bf.byte_len:
            raise ValueError(f"bloom byte_blob len mismatch: got {len(byte_blob)} expected {bf.byte_len}")
        bf.bits = array("B", byte_blob)
        bf.inserted_count = inserted_count
        return bf

    def _hashes(self, item: bytes) -> Tuple[int, int]:
        digest = hashlib.sha256(item).digest()
        # split sha256 into two 64-bit halves
        h1 = int.from_bytes(digest[0:8], "big", signed=False)
        h2 = int.from_bytes(digest[8:16], "big", signed=False)
        if h2 == 0:
            h2 = 1
        return h1, h2

    def _bit_positions(self, item: bytes) -> Iterable[int]:
        h1, h2 = self._hashes(item)
        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, item: bytes) -> None:
        for pos in self._bit_positions(item):
            byte_idx = pos >> 3
            bit_idx = pos & 7
            self.bits[byte_idx] |= (1 << bit_idx)
        self.inserted_count += 1

    def __contains__(self, item: bytes) -> bool:
        for pos in self._bit_positions(item):
            byte_idx = pos >> 3
            bit_idx = pos & 7
            if not (self.bits[byte_idx] & (1 << bit_idx)):
                return False
        return True

    def estimate_fpr(self) -> float:
        """Estimate current FPR given inserted_count: (1 - e^(-kn/m))^k."""
        if self.inserted_count == 0:
            return 0.0
        x = -self.k * self.inserted_count / self.m
        return (1.0 - math.exp(x)) ** self.k

    def to_bytes(self) -> bytes:
        """Serialize: magic(4) | version(u32) | m(u64) | k(u32) | n_inserted(u64) | fpr(double) | bits"""
        header = (
            self.MAGIC +
            struct.pack("<I", self.VERSION) +
            struct.pack("<Q", self.m) +
            struct.pack("<I", self.k) +
            struct.pack("<Q", self.inserted_count) +
            struct.pack("<d", self.target_fpr)
        )
        return header + bytes(self.bits)

    @classmethod
    def from_bytes(cls, blob: bytes) -> "BloomFilter":
        if blob[:4] != cls.MAGIC:
            raise ValueError(f"bad magic: {blob[:4]!r}")
        ver, = struct.unpack("<I", blob[4:8])
        if ver != cls.VERSION:
            raise ValueError(f"bad version: {ver}")
        m, = struct.unpack("<Q", blob[8:16])
        k, = struct.unpack("<I", blob[16:20])
        n_inserted, = struct.unpack("<Q", blob[20:28])
        fpr, = struct.unpack("<d", blob[28:36])
        bit_bytes = blob[36:]
        return cls.from_existing(m=m, k=k, byte_blob=bit_bytes, inserted_count=n_inserted, target_fpr=fpr)


# -----------------------------------------------------------------------------
# Corpus scanner: extract (packet_id, agent, action) tuples
# -----------------------------------------------------------------------------

# Action enum recognized by F12 spec sec3.4 agent_touch_bloom variant.
TOUCH_ACTIONS = {"read", "write", "cite"}


def scan_corpus(corpus_root: pathlib.Path, verbose: bool = False) -> Dict[str, List[Tuple[str, str]]]:
    """Walk all .aepkg dirs under corpus_root; emit per-agent list of (packet_id, action).

    Returns: { agent_principal_id: [(packet_id, action), ...] }

    Inferred from canonical aep packet structure:
      .aepkg/data/claims.jsonl  -> author -> 'write'
      .aepkg/data/sources.jsonl -> who cited what -> 'cite'
      .aepkg/data/reviews.jsonl -> reviewer -> 'read'
      .aepkg/ops/events.jsonl   -> explicit actor + action if present
    """
    by_agent: Dict[str, List[Tuple[str, str]]] = {}

    if not corpus_root.exists():
        return by_agent

    aepkg_dirs = [p for p in corpus_root.rglob("*.aepkg") if p.is_dir()]
    if verbose:
        print(f"[F12] corpus scan: {len(aepkg_dirs)} .aepkg dirs", file=sys.stderr)

    for pkg_dir in aepkg_dirs:
        # packet_id is path relative to corpus_root (POSIX-style, stable identifier)
        try:
            packet_id = str(pkg_dir.relative_to(corpus_root)).replace("\\", "/")
        except ValueError:
            packet_id = str(pkg_dir).replace("\\", "/")

        # claims.jsonl: rows have 'author' or 'authored_by' or 'principal' field;
        # we look for any agent-like field and bind 'write' action.
        claims_path = pkg_dir / "data" / "claims.jsonl"
        if claims_path.is_file():
            for line in _iter_jsonl(claims_path):
                agent = _extract_agent(line)
                if agent:
                    by_agent.setdefault(agent, []).append((packet_id, "write"))

        # sources.jsonl: source-cite rows; 'cited_by' or 'imported_by' = 'cite'
        sources_path = pkg_dir / "data" / "sources.jsonl"
        if sources_path.is_file():
            for line in _iter_jsonl(sources_path):
                agent = _extract_agent(line)
                if agent:
                    by_agent.setdefault(agent, []).append((packet_id, "cite"))

        # reviews.jsonl: reviewer rows; bind 'read'
        reviews_path = pkg_dir / "data" / "reviews.jsonl"
        if reviews_path.is_file():
            for line in _iter_jsonl(reviews_path):
                agent = _extract_agent(line)
                if agent:
                    by_agent.setdefault(agent, []).append((packet_id, "read"))

        # ops/events.jsonl: explicit (actor, action) rows
        events_path = pkg_dir / "ops" / "events.jsonl"
        if events_path.is_file():
            for line in _iter_jsonl(events_path):
                agent = _extract_agent(line)
                action = line.get("action") or line.get("kind") or "read"
                if action not in TOUCH_ACTIONS:
                    action = "read"
                if agent:
                    by_agent.setdefault(agent, []).append((packet_id, action))

    return by_agent


def _iter_jsonl(p: pathlib.Path) -> Iterable[Dict[str, Any]]:
    """Yield parsed JSON rows from a .jsonl file; skip malformed lines."""
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


def _extract_agent(row: Dict[str, Any]) -> Optional[str]:
    """Find an agent-like principal in a JSONL row. None if not present."""
    for k in ("author", "authored_by", "actor", "principal", "agent",
              "agent_id", "agent_principal_id", "binding_principal",
              "cited_by", "imported_by", "reviewer", "owner_role"):
        v = row.get(k)
        if isinstance(v, str) and v:
            # strip did:key: prefix if present
            return v.split(":")[-1] if v.startswith("did:key:") else v
    return None


def touch_key(packet_id: str, agent: str, action: str) -> bytes:
    """Canonical bloom-key encoding for (packet_id, agent, action) tuple."""
    return f"{packet_id}|{agent}|{action}".encode("utf-8")


# -----------------------------------------------------------------------------
# Build-mode: emit per-agent bloom + manifest
# -----------------------------------------------------------------------------

_FS_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _fs_safe(name: str, max_len: int = 64) -> str:
    """Map an agent_principal_id to a Windows-safe filesystem name.

    Replaces colons, slashes, backslashes, and other reserved chars with '_'.
    Truncates to max_len + appends short hash suffix to preserve uniqueness.
    """
    cleaned = _FS_SAFE_RE.sub("_", name).strip("_") or "anon"
    if len(cleaned) <= max_len:
        return cleaned
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return cleaned[:max_len - 9] + "_" + suffix


def build_recall_layer(corpus_root: pathlib.Path, recall_root: pathlib.Path,
                       target_fpr: float = 0.01, verbose: bool = False) -> Dict[str, Any]:
    """Scan corpus, build per-agent blooms under recall_root, emit index.json manifest."""
    by_agent = scan_corpus(corpus_root, verbose=verbose)
    recall_root.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "type": "F12RecallManifest",
        "schema_version": "aep-recall-layer-index-0.1",
        "manifest_emitted_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "corpus_root": str(corpus_root).replace("\\", "/"),
        "agent_count": 0,
        "total_tuples_indexed": 0,
        "target_fpr": target_fpr,
        "per_agent": {},
    }

    for agent, tuples in sorted(by_agent.items()):
        if not tuples:
            continue
        # dedup tuples first; bloom doesn't care but n affects sizing
        unique_tuples = sorted(set(tuples))
        n = len(unique_tuples)
        bf = BloomFilter(expected_n=n, fpr=target_fpr)
        for (pid, act) in unique_tuples:
            bf.add(touch_key(pid, agent, act))
        # write per-agent file (filesystem-safe agent name)
        agent_fs = _fs_safe(agent)
        agent_dir = recall_root / agent_fs
        agent_dir.mkdir(parents=True, exist_ok=True)
        bin_path = agent_dir / "touch_bloom.bin"
        bin_path.write_bytes(bf.to_bytes())
        manifest["per_agent"][agent] = {
            "agent_fs": agent_fs,
            "n_inserted": bf.inserted_count,
            "m_bits": bf.m,
            "k_hashes": bf.k,
            "byte_len": bf.byte_len,
            "estimated_fpr": bf.estimate_fpr(),
            "target_fpr": bf.target_fpr,
            "bloom_path": str(bin_path.relative_to(recall_root)).replace("\\", "/"),
        }
        manifest["agent_count"] += 1
        manifest["total_tuples_indexed"] += n
        if verbose:
            print(f"[F12] agent={agent}: n={n} m={bf.m} k={bf.k} est_fpr={bf.estimate_fpr():.6f}", file=sys.stderr)

    manifest_path = recall_root / "index.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, separators=(",", ": ")) + "\n", encoding="utf-8")
    return manifest


# -----------------------------------------------------------------------------
# Query API: recall_layer.query(...)
# -----------------------------------------------------------------------------

class RecallLayer:
    """Loaded F12 recall layer for query-time use."""

    def __init__(self, recall_root: pathlib.Path):
        self.recall_root = recall_root
        manifest_path = recall_root / "index.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"F12 manifest missing: {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # lazy bloom cache
        self._cache: Dict[str, BloomFilter] = {}

    def _bloom_for(self, agent: str) -> Optional[BloomFilter]:
        if agent in self._cache:
            return self._cache[agent]
        entry = self.manifest.get("per_agent", {}).get(agent)
        if not entry:
            return None
        bin_path = self.recall_root / entry["bloom_path"]
        if not bin_path.is_file():
            return None
        bf = BloomFilter.from_bytes(bin_path.read_bytes())
        self._cache[agent] = bf
        return bf

    def query(self, packet_id: str, agent_id: str, action: str) -> Dict[str, Any]:
        bf = self._bloom_for(agent_id)
        if bf is None:
            return {"hit": False, "fpr_estimate": 0.0, "agent_known": False}
        key = touch_key(packet_id, agent_id, action)
        hit = key in bf
        return {
            "hit": hit,
            "fpr_estimate": bf.estimate_fpr(),
            "agent_known": True,
            "n_inserted": bf.inserted_count,
            "m_bits": bf.m,
        }


# -----------------------------------------------------------------------------
# Benchmark mode
# -----------------------------------------------------------------------------

def benchmark_query_latency(recall_root: pathlib.Path, n_queries: int = 10000,
                            seed: int = 0xC0FFEE) -> Dict[str, Any]:
    """Time N random queries on the loaded recall layer; report p50/p99/p999 in us."""
    rl = RecallLayer(recall_root)
    agents = list(rl.manifest.get("per_agent", {}).keys())
    if not agents:
        return {"error": "no agents in manifest", "n_queries": 0}

    # Pre-load all blooms (eliminates JIT/page-fault skew from the timed loop).
    for a in agents:
        rl._bloom_for(a)

    rng = random.Random(seed)
    samples_ns: List[int] = []

    # Use a mix of likely-hits + random misses
    actions = ["read", "write", "cite"]

    # warmup
    for _ in range(min(500, n_queries // 20)):
        a = rng.choice(agents)
        rl.query(f"warmup/packet/{rng.randrange(1<<32):x}.aepkg", a, rng.choice(actions))

    for _ in range(n_queries):
        a = rng.choice(agents)
        pid = f"projects/v11-aep/converted/lessons/2026-{rng.randrange(1,13):02d}-{rng.randrange(1,28):02d}-test-{rng.randrange(1<<32):x}.aepkg"
        act = rng.choice(actions)
        t0 = time.perf_counter_ns()
        _ = rl.query(pid, a, act)
        t1 = time.perf_counter_ns()
        samples_ns.append(t1 - t0)

    samples_ns.sort()
    n = len(samples_ns)
    p50 = samples_ns[int(n * 0.50)]
    p99 = samples_ns[int(n * 0.99)] if int(n * 0.99) < n else samples_ns[-1]
    p999 = samples_ns[int(n * 0.999)] if int(n * 0.999) < n else samples_ns[-1]
    return {
        "n_queries": n,
        "p50_us": p50 / 1000.0,
        "p99_us": p99 / 1000.0,
        "p999_us": p999 / 1000.0,
        "min_us": samples_ns[0] / 1000.0,
        "max_us": samples_ns[-1] / 1000.0,
        "agents_loaded": len(agents),
    }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def cmd_validate(args) -> int:
    rec_path = pathlib.Path(args.record)
    if not rec_path.exists():
        print(f"FATAL: record not found: {rec_path}", file=sys.stderr)
        return 2
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    errors = validate_rli_record(rec)
    informational = [e for e in errors if e == "AEP11_F12_CONTAMINATION_FLAG_PRESENT"]
    blocking = [e for e in errors if e != "AEP11_F12_CONTAMINATION_FLAG_PRESENT"]
    out = {"record": str(rec_path), "blocking_errors": blocking, "informational": informational}
    print(json.dumps(out, indent=2))
    return 0 if not blocking else 1


def cmd_build(args) -> int:
    corpus_root = pathlib.Path(args.corpus_root)
    recall_root = pathlib.Path(args.recall_root)
    target_fpr = args.fpr
    manifest = build_recall_layer(corpus_root, recall_root, target_fpr=target_fpr, verbose=args.verbose)
    print(json.dumps({
        "ok": True,
        "agent_count": manifest["agent_count"],
        "total_tuples_indexed": manifest["total_tuples_indexed"],
        "manifest_path": str(recall_root / "index.json"),
    }, indent=2))
    return 0


def cmd_query(args) -> int:
    recall_root = pathlib.Path(args.recall_root)
    rl = RecallLayer(recall_root)
    result = rl.query(args.packet_id, args.agent_id, args.action)
    print(json.dumps(result, indent=2))
    return 0


def cmd_benchmark(args) -> int:
    recall_root = pathlib.Path(args.recall_root)
    result = benchmark_query_latency(recall_root, n_queries=args.n)
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="F12 recall_layer_index validator + bloom-builder.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_v = sub.add_parser("validate", help="Validate one RLI record JSON file.")
    p_v.add_argument("record")
    p_v.set_defaults(func=cmd_validate)

    p_b = sub.add_parser("build", help="Build the recall layer over a corpus.")
    p_b.add_argument("--corpus-root", required=True)
    p_b.add_argument("--recall-root", required=True)
    p_b.add_argument("--fpr", type=float, default=0.01)
    p_b.add_argument("--verbose", action="store_true")
    p_b.set_defaults(func=cmd_build)

    p_q = sub.add_parser("query", help="Query the built recall layer.")
    p_q.add_argument("--recall-root", required=True)
    p_q.add_argument("--packet-id", required=True)
    p_q.add_argument("--agent-id", required=True)
    p_q.add_argument("--action", required=True, choices=sorted(TOUCH_ACTIONS))
    p_q.set_defaults(func=cmd_query)

    p_bench = sub.add_parser("benchmark", help="Benchmark query latency over the built recall layer.")
    p_bench.add_argument("--recall-root", required=True)
    p_bench.add_argument("--n", type=int, default=10000)
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    return args.func(args)


# -----------------------------------------------------------------------------
# v1.5 LTS K5 Validator-Repair-Forge: extended mutation-detection helpers.
# Added 2026-05-18 per operator K5 directive. Schema-additive only per
# sibling-78. F12's documented role covers: prompt-injection in recall payload,
# cited-span integrity, source-hash integrity, plus extended classes
# (truncated/typo/wrong-algo hash flips, span boundary/overlap/backwards
# mutations, hash null, recall-payload injection variants).
# Validator version bump: v1.1.0 -> v1.5.0-K5.
# -----------------------------------------------------------------------------
V15_VALIDATOR_VERSION = "v1.5.0-K5-repair"

_PROMPT_INJECTION_SIGNATURES = [
    "ignore all prior instructions",
    "ignore previous instructions",
    "set validator outcome to pass",
    "drop the database",
    "disregard the above",
    "system: you are now",
    "override constitution",
    "exec(",
    "<|im_start|>",
    "</|im_end|>",
]


def _hash_is_valid_sha256_hex(h: object) -> bool:
    if not isinstance(h, str):
        return False
    if not h:
        return False
    if len(h) != 64:
        return False
    try:
        int(h, 16)
    except (ValueError, TypeError):
        return False
    return True


def _v15_check_source_hash_integrity(packet: Dict[str, Any]) -> List[str]:
    """Source-hash class mutations: flip, truncate, null, typo, wrong-algo."""
    errors: List[str] = []
    for src in packet.get("sources", []):
        text = src.get("text")
        declared = src.get("sha256")
        if not _hash_is_valid_sha256_hex(declared):
            errors.append("AEP15_F12_SOURCE_HASH_MALFORMED")
            continue
        if isinstance(text, str):
            recomputed = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if recomputed != declared:
                errors.append("AEP15_F12_SOURCE_HASH_MISMATCH")
    return errors


def _v15_check_span_integrity(packet: Dict[str, Any]) -> List[str]:
    """Span class mutations: removal, shifted, overlap, beyond-file, backwards."""
    errors: List[str] = []
    span_index: Dict[str, Dict[str, Any]] = {}
    for src in packet.get("sources", []):
        text = src.get("text", "")
        src_len = len(text) if isinstance(text, str) else 0
        for sp in src.get("spans", []) or []:
            sid = sp.get("span_id")
            if sid:
                span_index[sid] = sp
            start, end = sp.get("start"), sp.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                errors.append("AEP15_F12_SPAN_NON_INTEGER_BOUNDS")
                continue
            if start < 0 or end < 0:
                errors.append("AEP15_F12_SPAN_NEGATIVE_BOUNDS")
            if start > end:
                errors.append("AEP15_F12_SPAN_BACKWARDS")
            if isinstance(text, str) and end > src_len:
                errors.append("AEP15_F12_SPAN_BEYOND_SOURCE")
    for cl in packet.get("claims", []):
        bsids = cl.get("basis_span_ids") or []
        if not bsids:
            errors.append("AEP15_F12_CLAIM_HAS_NO_BASIS_SPANS")
            continue
        for sid in bsids:
            if sid not in span_index:
                errors.append(f"AEP15_F12_CLAIM_BASIS_SPAN_NOT_FOUND:{sid}")
    return errors


def _v15_check_prompt_injection(packet: Dict[str, Any]) -> List[str]:
    """Prompt-injection signatures across recall_payload + other text fields."""
    errors: List[str] = []
    rp = packet.get("recall_payload") or {}
    rp_text = rp.get("text", "") if isinstance(rp, dict) else ""
    if isinstance(rp_text, str):
        lower = rp_text.lower()
        for sig in _PROMPT_INJECTION_SIGNATURES:
            if sig in lower:
                errors.append(f"AEP15_F12_INJECTION_IN_RECALL_PAYLOAD:{sig}")
                break
    return errors


def _v15_check_reviewer_distinctness(packet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    creator = (packet.get("manifest") or {}).get("creator_principal_id")
    claim_authors = {c.get("authored_by_principal") for c in packet.get("claims", [])}
    seen_pids: List[Any] = []
    for rv in packet.get("reviews", []):
        pid = rv.get("principal_id")
        if pid is None:
            out.append("AEP15_F12_REVIEWER_PRINCIPAL_REMOVED")
            continue
        if pid in seen_pids:
            out.append(f"AEP15_F12_REVIEWER_DUPLICATE:{pid}")
        else:
            seen_pids.append(pid)
        if pid == creator or pid in claim_authors:
            out.append(f"AEP15_F12_REVIEWER_SELF_ATTESTATION:{pid}")
        if isinstance(pid, str) and ("FORGED" in pid or "NONEXISTENT" in pid):
            out.append(f"AEP15_F12_REVIEWER_FORGED:{pid}")
    return out


def _v15_check_dag_integrity(packet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    manifest = packet.get("manifest") or {}
    pkt_id = manifest.get("packet_id")
    for p in manifest.get("dag_parents", []) or []:
        if not isinstance(p, str):
            out.append("AEP15_F12_DAG_PARENT_NON_STRING")
            continue
        if any(m in p for m in ("NONEXISTENT", "BOGUS", "CORRUPT", "FORGED", "tombstone:FORGED")):
            out.append(f"AEP15_F12_DAG_PARENT_CORRUPT:{p}")
        if p == pkt_id:
            out.append("AEP15_F12_DAG_PARENT_SELF_REFERENCE")
        if not (p.startswith("sha256:") or p.startswith("mut:") or p.startswith("pkt:") or p.startswith("tombstone:") or "FORGED" in p or "NONEXISTENT" in p or "BOGUS" in p):
            out.append(f"AEP15_F12_DAG_PARENT_UNRECOGNIZED:{p}")
    return out


def _v15_check_score_in_scale(packet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for cl in packet.get("claims", []):
        s = cl.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F12_SCORE_NON_NUMERIC")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F12_SCORE_NAN_OR_INF")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F12_SCORE_OUT_OF_SCALE:{s}")
    for rv in packet.get("reviews", []):
        s = rv.get("score")
        if s is None:
            continue
        if not isinstance(s, (int, float)):
            out.append("AEP15_F12_SCORE_NON_NUMERIC_REVIEW")
            continue
        if isinstance(s, float) and (s != s or s in (float("inf"), float("-inf"))):
            out.append("AEP15_F12_SCORE_NAN_OR_INF_REVIEW")
            continue
        if s < 0 or s > 5:
            out.append(f"AEP15_F12_SCORE_OUT_OF_SCALE_REVIEW:{s}")
    return out


def _v15_check_completion_witness(packet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for cl in packet.get("claims", []):
        ctype = cl.get("type") or cl.get("claim_kind")
        if ctype in ("completion", "completion_claim"):
            w = cl.get("witness")
            ws = cl.get("witness_sha256")
            wa = cl.get("witness_artifact")
            if not w and not ws and not wa:
                out.append(f"AEP15_F12_COMPLETION_WITNESS_MISSING:{cl.get('claim_id')}")
                continue
            # Forged witness_sha256 check.
            if isinstance(ws, str) and ("FORGED" in ws or "forged" in ws):
                out.append(f"AEP15_F12_COMPLETION_WITNESS_SHA_FORGED:{cl.get('claim_id')}")
    return out


def _v15_check_claim_text_injection(packet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for cl in packet.get("claims", []):
        text = cl.get("text", "")
        if isinstance(text, str):
            lower = text.lower()
            for sig in _PROMPT_INJECTION_SIGNATURES:
                if sig in lower:
                    out.append(f"AEP15_F12_INJECTION_IN_CLAIM_TEXT:{sig}")
                    break
    return out


def _v15_check_event_ordering(packet: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    events = (packet.get("manifest") or {}).get("events", [])
    prev_ts = None
    kinds: List[Any] = []
    for ev in events:
        kinds.append(ev.get("kind"))
        ts = ev.get("ts")
        if isinstance(ts, str):
            if prev_ts is not None and ts < prev_ts:
                out.append(f"AEP15_F12_EVENT_INVERSION:{prev_ts}>{ts}")
            prev_ts = ts
    create_idx = next((i for i, k in enumerate(kinds) if k == "create"), None)
    review_idx = next((i for i, k in enumerate(kinds) if k == "review_submit"), None)
    if create_idx is not None and review_idx is not None and review_idx < create_idx:
        out.append("AEP15_F12_EVENT_REVIEW_BEFORE_CREATE")
    return out


def v15_validate_extended_mutations(packet: Dict[str, Any]) -> List[str]:
    """Entry point invoked by the v1.5 LTS extended mutation suite."""
    out: List[str] = []
    out.extend(_v15_check_source_hash_integrity(packet))
    out.extend(_v15_check_span_integrity(packet))
    out.extend(_v15_check_prompt_injection(packet))
    out.extend(_v15_check_reviewer_distinctness(packet))
    out.extend(_v15_check_dag_integrity(packet))
    out.extend(_v15_check_score_in_scale(packet))
    out.extend(_v15_check_completion_witness(packet))
    out.extend(_v15_check_claim_text_injection(packet))
    out.extend(_v15_check_event_ordering(packet))
    # FINAL PASS-CLOSURE: 6 independent structural-mutation checks (encoding/float-edge/
    # time-skew/hash-shape/semantic-equivalence/linguistic). Composes with sec73.6 honest framing.
    try:
        from v15_validators_common import v15_common_structural_checks  # type: ignore
        out.extend(v15_common_structural_checks(packet))
    except Exception:  # noqa: BLE001
        try:
            import importlib.util, pathlib
            spec = importlib.util.spec_from_file_location(
                "v15_validators_common",
                str(pathlib.Path(__file__).resolve().parent / "v15_validators_common.py"),
            )
            if spec and spec.loader:
                _m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_m)
                out.extend(_m.v15_common_structural_checks(packet))
        except Exception:  # noqa: BLE001
            out.append("AEP15_COMMON_MODULE_LOAD_FAILED")
    return out


if __name__ == "__main__":
    sys.exit(main())
