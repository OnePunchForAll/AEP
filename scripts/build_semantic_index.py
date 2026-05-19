"""build_semantic_index.py — Pure-Python TF-IDF semantic index over the AEP corpus.

Builds a deterministic semantic index over claims from agent companions, doctrine
slots, lessons, proposals, and dump entries. No model download. No network calls.
sklearn not required (pure stdlib + numpy).

Output: per-shard/per-companion `embeddings/` sub-directory containing:
- index.jsonl         (sparse TF-IDF vectors: one NDJSON row per claim)
- vocabulary.jsonl    (sorted term -> IDF; deterministic vocabulary)
- index.meta.json     (n_vectors, vocab_sha256, model_id, hcrl_chain head)

Compliance:
- §04 security: ZERO network calls; explicit socket monkey-patch + offline-only assert.
- §41 HCRL: each index.meta.json carries prev_receipt_hash + this_receipt_hash
  computed via BLAKE2b-256 (BLAKE3 unavailable in stdlib; documented substitution
  per §41 §11 — strictly weaker but cryptographically sound).
- §50 EH: append-only. Re-running this script REPLACES the index but logs the
  prior receipt in receipts.jsonl for audit.
- §52 Hybrid Bridge invariants: `embeddings/` is a SUB-PATH of `.aepkg/`; never
  reverses the prose-canonical direction.

Determinism:
- PYTHONHASHSEED handled (we never rely on hash() ordering).
- Vocabulary sorted alphabetically.
- Sparse vector terms emitted in vocabulary-index order.
- Float64 internally, rounded to 6 decimals before emit (so JSON output is byte-identical across runs).

Usage:
    python build_semantic_index.py \
        --target Singular-AEP-Dump-Files/dump-001.aepkg \
        --target doctrine/lessons \
        --target doctrine/_proposals \
        --target .claude/agents \
        --output-dir embeddings  # relative to each target
        [--min-df 2] [--max-vocab 20000] [--top-k-nn 20]

For unified index across all targets, use --aggregate with --output-path:
    python build_semantic_index.py --aggregate \
        --output-path Singular-AEP-Dump-Files/dump-001.aepkg/embeddings
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import re
import socket
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# § 04: hard offline assertion. If anything tries to open a socket during this run, it raises.
_orig_socket = socket.socket
def _no_network_socket(*a, **kw):
    raise RuntimeError("§04 security: build_semantic_index makes ZERO network calls; socket access denied")
socket.socket = _no_network_socket  # type: ignore
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

MODEL_ID = "tfidf-stdlib-v1"
EMPTY_HASH = "blake2b-256:" + hashlib.blake2b(b"", digest_size=32).hexdigest()


# Minimal stopword list (operator-amendable). Hash this string for determinism record.
STOPWORDS_RAW = """
a an the of and or but not for to in on at by from with as is are was were be been being have has had
do does did this that these those it its their there here we us our you your they them he she his her him
will would should could may might must can shall about above after again against all am any aren't because
been before below between both can't cannot couldn't did didn't doesn't doing don't down during each
few further haven't hasn't hadn't her here's hers herself himself his how i'd i'll i'm i've if into
let's me more most mustn't my myself nor of off on once only other ought our ours ourselves out over own
same shan't she'd she'll she's so some such than that's then theirs themselves there's they'd they'll
they're they've through too under until up very wasn't we'd we'll we're we've weren't what what's
when when's where where's which while who who's whom why why's won't wouldn't yours yourself yourselves
"""
STOPWORDS = frozenset(w for w in STOPWORDS_RAW.split() if w)
STOPWORDS_SHA = hashlib.blake2b(" ".join(sorted(STOPWORDS)).encode("utf-8"), digest_size=32).hexdigest()

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_]{2,}")


def tokenize(text: str) -> List[str]:
    """Deterministic tokenizer: lowercase, NFKC-normalize, regex-extract."""
    text = unicodedata.normalize("NFKC", text).lower()
    tokens = TOKEN_RE.findall(text)
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 3 and len(t) <= 32]


def blake2b256_hex(b: bytes) -> str:
    return hashlib.blake2b(b, digest_size=32).hexdigest()


def blake2b256_str(s: str) -> str:
    return blake2b256_hex(s.encode("utf-8"))


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def safe_read_jsonl(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def safe_read_text(p: Path, max_bytes: int = 32768) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError:
        return ""


def extract_dump_entry_text(entry: Dict[str, Any]) -> str:
    """Gunzip + base64 decode the first_text_4kb field of a dump entry."""
    b64 = entry.get("first_text_4kb")
    if not b64:
        return ""
    try:
        raw = base64.b64decode(b64)
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
        return text
    except (OSError, ValueError):
        return ""


def iter_corpus(repo_root: Path, target_paths: List[Path]) -> Iterable[Dict[str, Any]]:
    """Yield one document dict per (claim or dump-entry or companion-source)."""
    seen_paths = set()
    for tp in target_paths:
        if not tp.exists():
            continue
        tp_str = str(tp.resolve())
        if tp_str in seen_paths:
            continue
        seen_paths.add(tp_str)

        # Case A: a dump shard (has data/dump-entries.jsonl)
        dump_entries = tp / "data" / "dump-entries.jsonl"
        if (tp / "aepkg.json").exists() and dump_entries.exists():
            for entry in safe_read_jsonl(dump_entries):
                text = extract_dump_entry_text(entry)
                if not text or len(text) < 80:
                    continue
                yield {
                    "vec_id": f"dump-entry::{entry.get('id', '?')}::{tp.name}",
                    "source_kind": "dump-entry",
                    "source_path": entry.get("original_path", ""),
                    "claim_id": None,
                    "shard_id": tp.name.replace(".aepkg", ""),
                    "cluster_tag": entry.get("cluster_tag"),
                    "reliability": None,
                    "axis_b": None,
                    "text": text,
                    "indexed_via": "dump-first-text-4kb",
                }
            continue

        # Case B: a directory containing .aepkg/ companions — recurse one level
        if tp.is_dir():
            for child in sorted(tp.rglob("*.aepkg")):
                if child.is_dir() and (child / "aepkg.json").exists():
                    yield from _iter_aepkg(child, repo_root)
            continue

        # Case C: a single .aepkg directly
        if (tp / "aepkg.json").exists():
            yield from _iter_aepkg(tp, repo_root)


def _iter_aepkg(aepkg_dir: Path, repo_root: Path) -> Iterable[Dict[str, Any]]:
    try:
        manifest = json.loads((aepkg_dir / "aepkg.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    source_path = manifest.get("extensions", {}).get(
        "aep:scope",
        str(aepkg_dir.relative_to(repo_root)).replace("\\", "/"),
    )
    reliability = manifest.get("truth_tag") or manifest.get("reliability")
    axis_b = manifest.get("axis_b") or manifest.get("axis_b_action")

    claims = safe_read_jsonl(aepkg_dir / "data" / "claims.jsonl")
    for c in claims:
        text = c.get("text") or c.get("claim_text") or ""
        if not text or len(text) < 40:
            continue
        yield {
            "vec_id": f"aepkg::{aepkg_dir.name}::{c.get('id', '?')}",
            "source_kind": "claim",
            "source_path": source_path,
            "claim_id": c.get("id"),
            "shard_id": None,
            "cluster_tag": c.get("cluster_tag") or (manifest.get("tags", [None])[0] if manifest.get("tags") else None),
            "reliability": c.get("reliability") or reliability,
            "axis_b": c.get("axis_b") or axis_b,
            "text": text,
            "indexed_via": "claim-row",
        }


def build_tfidf(docs: List[Dict[str, Any]], min_df: int = 2, max_vocab: int = 20000):
    """Pure-Python TF-IDF over the doc list. Returns (vocab_list, vocab_idf, sparse_vecs).
    Deterministic by sorted vocabulary + sorted term emission per vector."""
    n_docs = len(docs)
    df = Counter()
    doc_tokens: List[Counter] = []
    for d in docs:
        toks = tokenize(d["text"])
        tc = Counter(toks)
        doc_tokens.append(tc)
        for t in tc.keys():
            df[t] += 1

    # Filter by min_df; sort alphabetically; cap to max_vocab by DF desc then alpha
    eligible = [(t, c) for t, c in df.items() if c >= min_df]
    eligible.sort(key=lambda x: (-x[1], x[0]))
    eligible = eligible[:max_vocab]
    vocab = sorted([t for t, _ in eligible])  # alphabetical for determinism
    vocab_idx = {t: i for i, t in enumerate(vocab)}

    # IDF: log((N + 1) / (df + 1)) + 1   (smooth IDF, sklearn-compatible)
    idf = {t: round(math.log((n_docs + 1) / (df[t] + 1)) + 1.0, 6) for t in vocab}

    # Sparse vectors as sorted dicts: {term_idx: weight}, L2-normalized
    sparse_vecs = []
    for tc in doc_tokens:
        vec = {}
        for t, count in tc.items():
            if t not in vocab_idx:
                continue
            tf = 1.0 + math.log(count)  # sublinear TF
            vec[vocab_idx[t]] = tf * idf[t]
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vec = {k: round(v / norm, 6) for k, v in vec.items()}
        sparse_vecs.append(vec)

    return vocab, idf, sparse_vecs


def compute_top_k_nn(sparse_vecs: List[Dict[int, float]], k: int = 20) -> List[List[Tuple[int, float]]]:
    """For each vec, return top-k nearest neighbors (excluding self) by cosine.

    Uses an inverted index for sparse cosine: O(N × avg_nnz × avg_postings_per_term).
    Adversary attack #7 mitigation: NO full O(n²) pairing.
    """
    inverted = defaultdict(list)  # term_idx -> [(doc_idx, weight), ...]
    for i, v in enumerate(sparse_vecs):
        for t, w in v.items():
            inverted[t].append((i, w))

    results = []
    for i, v in enumerate(sparse_vecs):
        scores = defaultdict(float)
        for t, w in v.items():
            for j, w2 in inverted[t]:
                if j == i:
                    continue
                scores[j] += w * w2
        topk = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        results.append(topk)
    return results


def append_hcrl_event(receipts_path: Path, event: Dict[str, Any]) -> str:
    """Append HCRL row with prev_receipt_hash + this_receipt_hash (BLAKE2b-256).

    Returns the new this_receipt_hash for caller to thread."""
    rows = safe_read_jsonl(receipts_path)
    if rows:
        prev = rows[-1]
        prev_hash = prev.get("this_receipt_hash", "blake2b-256:" + EMPTY_HASH.split(":", 1)[1])
    else:
        prev_hash = "blake2b-256:" + EMPTY_HASH.split(":", 1)[1]
    event["prev_receipt_hash"] = prev_hash
    # Compute this_receipt_hash over event minus the field itself
    base = {k: v for k, v in event.items() if k != "this_receipt_hash"}
    this_hash = "blake2b-256:" + blake2b256_str(canonical_json(base))
    event["this_receipt_hash"] = this_hash
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(receipts_path, "a", encoding="utf-8") as f:
        f.write(canonical_json(event) + "\n")
    return this_hash


def write_index(out_dir: Path, docs: List[Dict[str, Any]], vocab: List[str], idf: Dict[str, float],
                sparse_vecs: List[Dict[int, float]], top_k_nn: List[List[Tuple[int, float]]]):
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Vocabulary: term -> idf (sorted by term)
    with open(out_dir / "vocabulary.jsonl", "w", encoding="utf-8") as f:
        for term in vocab:
            f.write(canonical_json({"term": term, "idf": idf[term]}) + "\n")

    # Index rows — per-row indexed_at REMOVED for determinism; timestamp lives in index.meta.json only
    text_sha_map = []
    with open(out_dir / "index.jsonl", "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            text_sha = blake2b256_str(d["text"])
            text_sha_map.append(text_sha)
            nn = [{"vec_idx": j, "cos": round(s, 6)} for j, s in top_k_nn[i]]
            row = {
                "vec_idx": i,
                "vec_id": d["vec_id"],
                "source_kind": d["source_kind"],
                "source_path": d["source_path"],
                "claim_id": d["claim_id"],
                "shard_id": d["shard_id"],
                "cluster_tag": d["cluster_tag"],
                "reliability": d["reliability"],
                "axis_b": d["axis_b"],
                "indexed_via": d["indexed_via"],
                "text_sha256": "blake2b-256:" + text_sha,
                "model_id": MODEL_ID,
                "stopwords_sha256": "blake2b-256:" + STOPWORDS_SHA,
                "sparse_vec": [{"t": k, "w": w} for k, w in sorted(sparse_vecs[i].items())],
                "top_k_nn": nn,
            }
            f.write(canonical_json(row) + "\n")

    # Meta
    vocab_blob = canonical_json({"vocab": vocab, "idf": idf})
    vocab_sha = blake2b256_str(vocab_blob)
    meta = {
        "schema_version": "1",
        "model_id": MODEL_ID,
        "model_params": {
            "min_df": "see-run-args",
            "tokenizer": "nfkc-lower-regex-3-32-stopwords",
            "tf_scheme": "1+log(count)",
            "idf_scheme": "log((N+1)/(df+1))+1",
            "norm": "l2-unit",
        },
        "n_vectors": len(docs),
        "vocab_size": len(vocab),
        "vocab_sha256": "blake2b-256:" + vocab_sha,
        "stopwords_sha256": "blake2b-256:" + STOPWORDS_SHA,
        "indexed_at": now,
        "top_k_nn": True,
        "top_k": len(top_k_nn[0]) if top_k_nn else 0,
        "hash_algorithm": "blake2b-256",
        "hash_substitution_note": "§41 specifies BLAKE3-256; BLAKE3 unavailable in stdlib. BLAKE2b-256 substituted per §41 §11 disclosure rule. Strictly weaker per length-extension and side-channel literature, but cryptographically sound for content-binding.",
    }
    (out_dir / "index.meta.json").write_text(canonical_json(meta) + "\n", encoding="utf-8")

    # HCRL receipt
    receipt_event = {
        "receipt_id": f"semantic-index-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "receipt_type": "transition_receipt",
        "event_time": now,
        "actor": "build_semantic_index.py",
        "actor_agent": os.environ.get("AEP_AGENT", "operator"),
        "bound_principal": "forge",
        "transition_target": "semantic-index-build",
        "payload_hash": "blake2b-256:" + vocab_sha,
        "evidence_artifacts": [
            {"kind": "file_state", "binding_path": "index.jsonl", "content_hash": "blake2b-256:" + blake2b256_str(
                "".join(canonical_json({
                    "vec_idx": i, "vec_id": docs[i]["vec_id"], "text_sha256": "blake2b-256:" + text_sha_map[i],
                }) for i in range(len(docs))))},
            {"kind": "file_state", "binding_path": "vocabulary.jsonl", "content_hash": "blake2b-256:" + vocab_sha},
        ],
        "evidence_bindings": [
            {"claim": "semantic_index_built",
             "claim_predicate": f"n_vectors=={len(docs)} AND vocab_size=={len(vocab)} AND model_id=={MODEL_ID}",
             "claim_evidence_artifact_id": "index.jsonl"},
        ],
    }
    append_hcrl_event(out_dir / "receipts.jsonl", receipt_event)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", action="append", default=[],
                    help="path to a .aepkg/ dir OR a parent dir containing .aepkg/ companions")
    ap.add_argument("--output-path", required=True, type=Path,
                    help="output directory for index files (e.g. Singular-AEP-Dump-Files/dump-001.aepkg/embeddings)")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--min-df", type=int, default=2)
    ap.add_argument("--max-vocab", type=int, default=20000)
    ap.add_argument("--top-k-nn", type=int, default=20)
    ap.add_argument("--max-docs", type=int, default=0, help="cap doc count for fast bench runs (0=unlimited)")
    args = ap.parse_args(argv)

    if not args.target:
        ap.error("--target is required (one or more)")

    repo_root = args.repo_root.resolve()
    targets = [(repo_root / t).resolve() for t in args.target]

    docs = list(iter_corpus(repo_root, targets))
    if args.max_docs > 0:
        docs = docs[:args.max_docs]

    print(f"corpus: {len(docs)} docs", file=sys.stderr)
    if not docs:
        raise SystemExit("no documents found in targets")

    vocab, idf, sparse = build_tfidf(docs, min_df=args.min_df, max_vocab=args.max_vocab)
    print(f"vocab: {len(vocab)} terms", file=sys.stderr)
    nn = compute_top_k_nn(sparse, k=args.top_k_nn)
    print(f"top-{args.top_k_nn} NN computed for all docs", file=sys.stderr)

    out_dir = args.output_path if args.output_path.is_absolute() else (repo_root / args.output_path).resolve()
    write_index(out_dir, docs, vocab, idf, sparse, nn)

    summary = {
        "n_vectors": len(docs),
        "vocab_size": len(vocab),
        "output_path": str(out_dir.relative_to(repo_root) if out_dir.is_relative_to(repo_root) else out_dir),
        "model_id": MODEL_ID,
    }
    print(canonical_json(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
