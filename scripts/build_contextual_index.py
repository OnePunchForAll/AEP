"""build_contextual_index.py - Anthropic Contextual Retrieval (DETERMINISTIC variant).

Reads each agent's ledger and, for each row, generates a deterministic context-prefix:

    [agent={agent} session={session_id_short} mission={mission_short} \
     cluster_tags={top-3-tags-joined}] {original invocation}

then indexes the prepended text rather than the raw invocation. Output: per-agent
contextual TF-IDF index sub-directory consumable by lag_retrieve_contextual.py.
Schema-additive parallel to existing build_lag_indices.py / lag_retrieve.py.

Why DETERMINISTIC variant: Anthropic's published method (Sept 2024) calls an LLM
to synthesize a context-prefix per chunk. That requires a paid model call per
indexed row (10K+ rows -> 10K+ calls). AEP project ledger rows already CARRY their
provenance fields (agent, session_id, mission, cluster_tags) as structured data,
so a deterministic template-prefix is build-time-free, byte-stable, and uses no
network. Falsifiable claim: the deterministic prefix captures most of the
context-uplift signal because ledger rows are already heavily provenance-tagged
(unlike Anthropic's narrative-text corpus). Smoke-test compares rank-of-cited.

Algorithm:
  1. For each ledger row, build context_prefix from row metadata (NO LLM call).
  2. contextual_text = context_prefix + " " + (invocation + " " + notes).
  3. TF-IDF tokenize the contextual_text (same tokenizer as build_lag_indices).
  4. Build per-agent index parallel to existing index but at output path
     contextual-indexes/<agent>.jsonl + contextual-indexes/<agent>.vocab.jsonl
     + contextual-indexes/<agent>.meta.json.

Anti-prompt-injection: same A7 imperative-pattern scrubbing applies at
RETRIEVE time in lag_retrieve_contextual.py (out-of-scope here).

Section 04: NO network calls (socket monkey-patch).
Section 41 HCRL: meta carries this_receipt_hash + prev_receipt_hash via BLAKE2b-256.
Section 50 Law-1: writes only to projects/v11-aep/publish-ready/aep/data/contextual-indexes/.
Section 52 Hybrid Bridge: indexes ledger JSONL companions; never reverses direction.
Cross-agent DENY (warden BLOCK amendment #1): per-agent isolation by --agent flag.

Usage:
    python build_contextual_index.py [--agents adversary,judge,...] [--all]
        [--output-root projects/v11-aep/publish-ready/aep/data/contextual-indexes]
        [--ledger-root .claude/agents/_ledgers]
        [--top-tags 3]
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
from typing import Dict, List


# Section 04 offline assertion
_orig_socket = socket.socket
def _no_network(*a, **kw):
    raise RuntimeError("Section 04: build_contextual_index makes ZERO network calls")
socket.socket = _no_network  # type: ignore

EMPTY = "blake2b-256:" + hashlib.blake2b(b"", digest_size=32).hexdigest()
MODEL_ID = "lag-contextual-tfidf-stdlib-v1"

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


def shorten_session(session_id: str, max_len: int = 40) -> str:
    """Produce a short-but-informative session_id snippet for the prefix."""
    if not isinstance(session_id, str) or not session_id:
        return "unknown-session"
    s = session_id[:max_len]
    return s


def shorten_mission(mission: str, max_len: int = 40) -> str:
    """Mission codes are dash-delimited; keep the meaningful tail."""
    if not isinstance(mission, str) or not mission:
        return "unknown-mission"
    # Strip the AEP-VN-AEP- generic prefix when present, keep the tail.
    if mission.startswith("AEP-V") and "-" in mission:
        parts = mission.split("-")
        # Keep last 4 dash-segments at most
        tail = "-".join(parts[-4:])
        if len(tail) <= max_len:
            return tail
    return mission[:max_len]


def top_tags(cluster_tags, k: int = 3) -> str:
    """Stable selection of top-k tags: take the FIRST k in declared order
    (preserves authoring intent; deterministic across runs)."""
    if not isinstance(cluster_tags, list):
        return "no-tags"
    selected = [str(t) for t in cluster_tags[:k] if isinstance(t, (str, int, float))]
    if not selected:
        return "no-tags"
    return ",".join(selected)


def build_context_prefix(row: Dict, agent: str, k_tags: int = 3) -> str:
    """The DETERMINISTIC contextual prefix.

    Format (single-line, bracket-delimited, comma-separated key=value pairs):
        [agent={agent} session={short} mission={short} cluster_tags={t1,t2,t3}]

    NO LLM call. NO network. Byte-stable across runs given identical input row.
    """
    sess = shorten_session(row.get("session_id") or "")
    miss = shorten_mission(row.get("mission") or "")
    tags = top_tags(row.get("cluster_tags") or [], k=k_tags)
    return f"[agent={agent} session={sess} mission={miss} cluster_tags={tags}]"


def extract_doc_from_ledger_row(row: Dict, agent_name: str, k_tags: int = 3) -> Dict:
    """Build a contextual document dict from one ledger JSONL row."""
    invocation = row.get("invocation") or ""
    notes = row.get("notes") or ""
    if not isinstance(invocation, str):
        invocation = str(invocation)
    if not isinstance(notes, str):
        notes = str(notes)

    context_prefix = build_context_prefix(row, agent_name, k_tags=k_tags)
    # The CONTEXTUAL text = prefix + original-invocation + notes (mirrors the
    # text composition in build_lag_indices but PREPENDED with structured ctx).
    contextual_text = (context_prefix + " " + invocation + " " + notes).strip()

    # vec_id identical to build_lag_indices for cross-index alignment.
    lamport = row.get("lamport_counter")
    session = row.get("session_id", "?")
    if lamport is None or lamport == "":
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
        "cluster_tags": row.get("cluster_tags") if isinstance(row.get("cluster_tags"), list) else [],
        "outcome": row.get("outcome"),
        "truth_tag": row.get("truth_tag"),
        "reliability": row.get("truth_tag"),
        "axis_b": row.get("axis_b"),
        "cites": row.get("cites") or [],
        "lag_influenced_by": row.get("lag_influenced_by") or [],
        "context_prefix": context_prefix,
        "contextual_text": contextual_text,
        "raw_invocation_excerpt": invocation[:300],
        "raw_notes_excerpt": notes[:300],
    }


def build_agent_index(agent: str, ledger_path: Path, out_root: Path, k_tags: int):
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

    docs = []
    for r in rows:
        if not r.get("invocation") and not r.get("notes") and not r.get("outcome"):
            continue
        d = extract_doc_from_ledger_row(r, agent, k_tags=k_tags)
        if len(d["contextual_text"]) < 40:
            continue
        docs.append(d)

    if not docs:
        return {"agent": agent, "status": "no-indexable-rows", "n_vectors": 0,
                "n_raw_rows": len(rows)}

    # Build TF-IDF over CONTEXTUAL text (deterministic; same alg as build_lag_indices).
    df = Counter()
    doc_tokens = []
    for d in docs:
        toks = tokenize(d["contextual_text"])
        tc = Counter(toks)
        doc_tokens.append(tc)
        for t in tc.keys():
            df[t] += 1

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

    # Top-K NN (excludes self) for completeness with the BM25 sibling index.
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

    out_root.mkdir(parents=True, exist_ok=True)

    # Per-agent files: <agent>.jsonl, <agent>.vocab.jsonl, <agent>.meta.json
    index_path = out_root / f"{agent}.jsonl"
    vocab_path = out_root / f"{agent}.vocab.jsonl"
    meta_path = out_root / f"{agent}.meta.json"

    with open(vocab_path, "w", encoding="utf-8") as f:
        for term in vocab:
            f.write(canon({"term": term, "idf": idf[term]}) + "\n")

    with open(index_path, "w", encoding="utf-8") as f:
        for i, d in enumerate(docs):
            text_sha = b2(d["contextual_text"])
            row_out = {
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
                "context_prefix": d["context_prefix"],
                "contextual_text_sha256": "blake2b-256:" + text_sha,
                "model_id": MODEL_ID,
                "raw_invocation_excerpt": d["raw_invocation_excerpt"],
                "raw_notes_excerpt": d["raw_notes_excerpt"],
                "sparse_vec": [{"t": k, "w": w} for k, w in sorted(sparse_vecs[i].items())],
                "top_k_nn": [{"vec_idx": j, "cos": s} for j, s in nn_results[i]],
            }
            f.write(canon(row_out) + "\n")

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
        "scope_assertion": (
            f"per-agent CONTEXTUAL index of {agent} ONLY; cross-agent retrieval "
            f"DENIED-BY-DEFAULT per LAG amendment #1"
        ),
        "method": "anthropic-contextual-retrieval-deterministic-variant",
        "context_prefix_template": "[agent={A} session={S} mission={M} cluster_tags={T}]",
        "k_top_tags": k_tags,
        "hash_algorithm": "blake2b-256",
        "ledger_path": str(ledger_path),
        "parallel_to_index": f"projects/v11-aep/publish-ready/aep/embeddings/agent-{agent}",
    }
    meta_path.write_text(canon(meta) + "\n", encoding="utf-8")

    # HCRL receipt (single chain per agent in this file's directory)
    receipts_path = out_root / f"{agent}.receipts.jsonl"
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
        "receipt_id": f"contextual-build-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "receipt_type": "contextual_index_build",
        "prev_receipt_hash": prev_hash,
        "agent": agent,
        "n_vectors": len(docs),
        "vocab_size": len(vocab),
        "vocab_sha256": "blake2b-256:" + vocab_sha,
        "k_top_tags": k_tags,
        "built_at": now,
        "actor": "build_contextual_index.py",
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
        "out_index": str(index_path),
        "out_vocab": str(vocab_path),
        "out_meta": str(meta_path),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agents", default=None, help="comma-separated agent names")
    ap.add_argument("--all", action="store_true", help="build for all 10 canonical agents")
    ap.add_argument("--output-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes"))
    ap.add_argument("--ledger-root", type=Path, default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--top-tags", type=int, default=3,
                    help="Top-K cluster_tags to embed in the deterministic prefix (default 3).")
    args = ap.parse_args()

    if args.all or not args.agents:
        agents = DEFAULT_AGENTS
    else:
        agents = [a.strip() for a in args.agents.split(",") if a.strip()]

    results = []
    for agent in agents:
        ledger_path = args.ledger_root / f"{agent}.jsonl"
        result = build_agent_index(agent, ledger_path, args.output_root, args.top_tags)
        results.append(result)

    summary = {
        "n_agents_processed": len(results),
        "total_vectors": sum(r.get("n_vectors", 0) for r in results),
        "method": "anthropic-contextual-retrieval-deterministic",
        "results": results,
    }
    print(canon(summary))


if __name__ == "__main__":
    main()
