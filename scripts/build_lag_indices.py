"""build_lag_indices.py — Per-agent LAG indices over .claude/agents/_ledgers/<name>.jsonl.

Builds one TF-IDF index per agent, deterministic, BLAKE2b-256 hashed. Composes with
KR-4 v2 tokenizer + TF-IDF math (same vocab discipline). Output: per-agent embeddings
sub-directory consumable by lag_retrieve.py.

§04: NO network calls (socket monkey-patch from build_semantic_index.py applies).
§41 HCRL: index meta carries this_receipt_hash + prev_receipt_hash via BLAKE2b-256.
§50 Law-1: writes only to projects/v11-aep/publish-ready/aep/embeddings/agent-<name>/.
§52 Hybrid Bridge: indexes companion-derived ledger rows; never reverses direction.
Cross-agent DENY (warden BLOCK amendment #1): each index isolated by --agent flag.

Usage:
    python build_lag_indices.py [--agents adversary,judge,...] [--all]
        [--output-root projects/v11-aep/publish-ready/aep/embeddings]
        [--ledger-root .claude/agents/_ledgers]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import socket
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


# §04 offline assertion
_orig_socket = socket.socket
def _no_network(*a, **kw):
    raise RuntimeError("§04: build_lag_indices makes ZERO network calls")
socket.socket = _no_network  # type: ignore

EMPTY = "blake2b-256:" + hashlib.blake2b(b"", digest_size=32).hexdigest()
MODEL_ID = "lag-tfidf-stdlib-v1"

# Same stopwords + tokenizer as KR-4 build_semantic_index for compositional consistency
STOPWORDS = frozenset(
    "a an the of and or but not for to in on at by from with as is are was were be been being "
    "have has had do does did this that these those it its their there here we us our you your "
    "they them he she his her him will would should could may might must can shall about above "
    "after again against all am any aren't because been before below between both can't cannot "
    "couldn't did didn't doesn't doing don't down during each few further haven't hasn't hadn't "
    "her here's hers herself himself his how if into let's me more most mustn't my myself nor "
    "off once only other ought our ours ourselves out over own same shan't she'd she'll she's so "
    "some such than that's then theirs themselves there's they'd they'll they're they've through "
    "too under until up very wasn't we'd we'll we're we've weren't what what's when when's where "
    "where's which while who who's whom why why's won't wouldn't yours yourself yourselves".split()
)
STOPWORDS_SHA = hashlib.blake2b(" ".join(sorted(STOPWORDS)).encode("utf-8"), digest_size=32).hexdigest()
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_]{2,}")
DEFAULT_AGENTS = [
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
]


def tokenize(text: str) -> List[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def b2(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=32).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def extract_doc_from_ledger_row(row: Dict, agent_name: str) -> Dict:
    """Build a document dict from one ledger JSONL row."""
    text_parts = []
    for k in ("invocation", "notes", "outcome", "mission"):
        v = row.get(k)
        if isinstance(v, str) and v:
            text_parts.append(v)
        elif isinstance(v, list):
            text_parts.extend(str(x) for x in v)
    cluster_tags = row.get("cluster_tags", [])
    if isinstance(cluster_tags, list):
        text_parts.append(" ".join(cluster_tags))
    text = " ".join(text_parts).strip()

    # A14 mitigation (adversary operator-double 2026-05-15): if lamport_counter is null
    # AND another row shares the first 24 chars of session_id, vec_ids collide and the
    # second-emitted row is silently dropped at retrieve-time set-dedup. Mitigation:
    # if lamport is None/missing, derive a deterministic tie-breaker from the row's
    # text content sha256 (first 12 hex chars). This guarantees vec_id uniqueness even
    # for malformed rows.
    lamport = row.get("lamport_counter")
    session = row.get("session_id", "?")
    if lamport is None or lamport == "":
        # Compute a deterministic disambiguator from row content
        content_blob = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        lamport_fallback = "null-" + hashlib.blake2b(content_blob.encode("utf-8"), digest_size=8).hexdigest()[:12]
        vec_id = f"ledger::{agent_name}::lamport-{lamport_fallback}::{session[:24]}"
    else:
        vec_id = f"ledger::{agent_name}::lamport-{lamport}::{session[:24]}"

    return {
        "vec_id": vec_id,
        "agent": agent_name,
        "source_path": f".claude/agents/_ledgers/{agent_name}.jsonl",
        "session_id": session,
        "date": row.get("date"),
        "lamport_counter": lamport,
        "cluster_tags": cluster_tags if isinstance(cluster_tags, list) else [],
        "outcome": row.get("outcome"),
        "truth_tag": row.get("truth_tag"),
        "reliability": row.get("truth_tag"),  # use truth_tag as reliability tier for filter
        "axis_b": row.get("axis_b"),
        "cites": row.get("cites") or [],
        "lag_influenced_by": row.get("lag_influenced_by") or [],
        "text": text,
        "raw_invocation_excerpt": (row.get("invocation") or "")[:300],
        "raw_notes_excerpt": (row.get("notes") or "")[:300],
    }


def build_agent_index(agent: str, ledger_path: Path, out_root: Path):
    if not ledger_path.exists():
        return {"agent": agent, "status": "no-ledger-file", "n_vectors": 0}

    rows = []
    with open(ledger_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Filter out header/meta rows (those without invocation or notes)
    docs = []
    for r in rows:
        if not r.get("invocation") and not r.get("notes") and not r.get("outcome"):
            continue
        d = extract_doc_from_ledger_row(r, agent)
        if len(d["text"]) < 40:
            continue
        docs.append(d)

    if not docs:
        return {"agent": agent, "status": "no-indexable-rows", "n_vectors": 0, "n_raw_rows": len(rows)}

    # Build TF-IDF (deterministic; identical algorithm to KR-4 build_semantic_index)
    df = Counter()
    doc_tokens = []
    for d in docs:
        toks = tokenize(d["text"])
        tc = Counter(toks)
        doc_tokens.append(tc)
        for t in tc.keys():
            df[t] += 1

    # min_df=1 for small ledger corpora; sort vocab alphabetically
    vocab = sorted(df.keys())
    vocab_idx = {t: i for i, t in enumerate(vocab)}
    n = len(docs)
    idf = {t: round(math.log((n + 1) / (df[t] + 1)) + 1.0, 6) for t in vocab}

    sparse_vecs = []
    for tc in doc_tokens:
        vec = {}
        for t, c in tc.items():
            tf = 1.0 + math.log(c)
            vec[vocab_idx[t]] = tf * idf[t]
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vec = {k: round(v / norm, 6) for k, v in vec.items()}
        sparse_vecs.append(vec)

    # Top-K NN via inverted index (excludes self)
    inverted = defaultdict(list)
    for i, v in enumerate(sparse_vecs):
        for t, w in v.items():
            inverted[t].append((i, w))
    nn_results = []
    for i, v in enumerate(sparse_vecs):
        scores = defaultdict(float)
        for t, w in v.items():
            for j, w2 in inverted[t]:
                if j == i:
                    continue
                scores[j] += w * w2
        topk = sorted(scores.items(), key=lambda kv: -kv[1])[:10]
        nn_results.append([(j, round(s, 6)) for j, s in topk])

    out_dir = out_root / f"agent-{agent}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write vocabulary
    with open(out_dir / "vocabulary.jsonl", "w", encoding="utf-8") as f:
        for term in vocab:
            f.write(canon({"term": term, "idf": idf[term]}) + "\n")

    # Write index rows (NO per-row timestamps; determinism per KR-4 v2)
    with open(out_dir / "index.jsonl", "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            text_sha = b2(d["text"])
            row = {
                "vec_idx": i,
                "vec_id": d["vec_id"],
                "agent": d["agent"],
                "source_path": d["source_path"],
                "session_id": d["session_id"],
                "date": d["date"],
                "lamport_counter": d["lamport_counter"],
                "cluster_tags": d["cluster_tags"],
                "outcome": d["outcome"],
                "reliability": d["reliability"],
                "axis_b": d["axis_b"],
                "cites": d["cites"],
                "lag_influenced_by": d["lag_influenced_by"],
                "text_sha256": "blake2b-256:" + text_sha,
                "model_id": MODEL_ID,
                "raw_invocation_excerpt": d["raw_invocation_excerpt"],
                "raw_notes_excerpt": d["raw_notes_excerpt"],
                "sparse_vec": [{"t": k, "w": w} for k, w in sorted(sparse_vecs[i].items())],
                "top_k_nn": [{"vec_idx": j, "cos": s} for j, s in nn_results[i]],
            }
            f.write(canon(row) + "\n")

    # Meta + HCRL receipt
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    vocab_blob = canon({"vocab": vocab, "idf": idf})
    vocab_sha = b2(vocab_blob)
    meta = {
        "schema_version": "1",
        "model_id": MODEL_ID,
        "agent": agent,
        "n_vectors": len(docs),
        "vocab_size": len(vocab),
        "vocab_sha256": "blake2b-256:" + vocab_sha,
        "stopwords_sha256": "blake2b-256:" + STOPWORDS_SHA,
        "indexed_at": now,
        "scope_assertion": f"per-agent index of {agent} ONLY; cross-agent retrieval DENIED-BY-DEFAULT per LAG amendment #1",
        "hash_algorithm": "blake2b-256",
        "ledger_path": str(ledger_path),
    }
    (out_dir / "index.meta.json").write_text(canon(meta) + "\n", encoding="utf-8")

    # HCRL receipt
    receipts_path = out_dir / "receipts.jsonl"
    prev_rows = []
    if receipts_path.exists():
        with open(receipts_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        prev_rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    prev_hash = ("blake2b-256:" + b2(canon(prev_rows[-1]))) if prev_rows else EMPTY
    receipt = {
        "receipt_id": f"lag-build-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "receipt_type": "lag_index_build",
        "prev_receipt_hash": prev_hash,
        "agent": agent,
        "n_vectors": len(docs),
        "vocab_size": len(vocab),
        "vocab_sha256": "blake2b-256:" + vocab_sha,
        "built_at": now,
        "actor": "build_lag_indices.py",
    }
    receipt["this_receipt_hash"] = "blake2b-256:" + b2(canon({k: v for k, v in receipt.items() if k != "this_receipt_hash"}))
    with open(receipts_path, "a", encoding="utf-8") as f:
        f.write(canon(receipt) + "\n")

    return {
        "agent": agent,
        "status": "ok",
        "n_vectors": len(docs),
        "n_raw_rows": len(rows),
        "vocab_size": len(vocab),
        "out_dir": str(out_dir),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agents", default=None, help="comma-separated agent names")
    ap.add_argument("--all", action="store_true", help="build for all 10 canonical agents")
    ap.add_argument("--output-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings"))
    ap.add_argument("--ledger-root", type=Path, default=Path(".claude/agents/_ledgers"))
    args = ap.parse_args()

    if args.all or not args.agents:
        agents = DEFAULT_AGENTS
    else:
        agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    results = []
    for agent in agents:
        ledger_path = args.ledger_root / f"{agent}.jsonl"
        result = build_agent_index(agent, ledger_path, args.output_root)
        results.append(result)

    summary = {
        "n_agents_processed": len(results),
        "total_vectors": sum(r.get("n_vectors", 0) for r in results),
        "results": results,
    }
    print(canon(summary))


if __name__ == "__main__":
    main()
