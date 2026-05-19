"""f6_cross_agent_inproc_quickfire.py — In-process cross-agent F6 recall@5 quick-fire.

WHY THIS EXISTS (extends sibling-49 Windows pivot pattern):
falsifier_6_cross_agent_cites.py uses subprocess.run(["python", ...]) which
sandbox-blocks on Win11 with CreateProcessAsUserW failed: 5 (sibling-49
fingerprint). This wrapper inlines the retrieval step using lag_retrieve.py's
on-disk indexes directly (no shell-out), reproducing the F6 cross-agent recall
test in-process. STRICTLY OPERATIONAL TOOLING; reads only index files; emits
JSON summary to stdout. Composes with sibling-49, sibling-96 UTC discipline.

Truth tag: STRONGLY PLAUSIBLE (forge wave-N 2026-05-16; recall computed
identically to falsifier_6_cross_agent_cites but without subprocess.run).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Same tokenizer as build_lag_indices.py
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
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-_]{2,}")
CANONICAL_10 = frozenset([
    "strategist", "pathfinder", "scout", "forge", "judge",
    "adversary", "warden", "scribe", "curator", "visual-judge",
])
CANONICAL_VEC_ID_RE = re.compile(
    r"ledger::(strategist|pathfinder|scout|forge|judge|adversary|warden|scribe|curator|visual-judge)::lamport-([a-zA-Z0-9_\-]+)::"
)


def tokenize(text: str) -> list:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def load_index(agent: str, index_root: Path):
    """Load per-agent index.jsonl + vocabulary.jsonl into memory."""
    idx_path = index_root / f"agent-{agent}" / "index.jsonl"
    vocab_path = index_root / f"agent-{agent}" / "vocabulary.jsonl"
    if not idx_path.exists() or not vocab_path.exists():
        return None
    vocab = {}
    with open(vocab_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            vocab[v["term"]] = (len(vocab), v["idf"])
    docs = []
    with open(idx_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return {"vocab": vocab, "docs": docs}


def retrieve_topk(idx, task_hint: str, top_k: int = 5):
    """In-process TF-IDF cosine ranking (same algo as lag_retrieve.py)."""
    if idx is None:
        return []
    query_tokens = tokenize(task_hint)
    if not query_tokens:
        return []
    tc = Counter(query_tokens)
    qvec = {}
    for t, c in tc.items():
        if t in idx["vocab"]:
            tidx, idf = idx["vocab"][t]
            qvec[tidx] = (1.0 + math.log(c)) * idf
    qnorm = math.sqrt(sum(w * w for w in qvec.values())) or 1.0
    qvec = {k: v / qnorm for k, v in qvec.items()}
    scores = []
    for d in idx["docs"]:
        s = 0.0
        for sv in d.get("sparse_vec", []):
            t = sv["t"]
            w = sv["w"]
            if t in qvec:
                s += qvec[t] * w
        if s > 0:
            scores.append((s, d.get("vec_id")))
    scores.sort(reverse=True)
    return [vid for _, vid in scores[:top_k]]


def mine_cross_agent_cites(ledger_root: Path):
    """Yield (citing_agent, cited_agent, task_hint, citation_str) tuples."""
    for ledger in sorted(ledger_root.glob("*.jsonl")):
        citing_agent = ledger.stem
        if citing_agent not in CANONICAL_10:
            continue
        try:
            with open(ledger, "r", encoding="utf-8") as f:
                rows = []
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("//") or line.startswith("#"):
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
        for r in rows:
            task_hint = (r.get("invocation") or "")[:200]
            if len(task_hint) < 30:
                continue
            cite_strs = []
            for field in ("lag_influenced_by", "cites"):
                v = r.get(field)
                if isinstance(v, list):
                    for c in v:
                        if isinstance(c, str):
                            cite_strs.append(c)
            notes = r.get("notes", "") or ""
            if isinstance(notes, str):
                for m in CANONICAL_VEC_ID_RE.finditer(notes[:64 * 1024]):
                    cite_strs.append(m.group(0))
            for c in cite_strs:
                m = CANONICAL_VEC_ID_RE.search(c)
                if not m:
                    continue
                cited_agent = m.group(1)
                if cited_agent == citing_agent:
                    continue
                yield {
                    "citing_agent": citing_agent,
                    "cited_agent": cited_agent,
                    "task_hint": task_hint,
                    "cited_vec_id_pattern": c,
                }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--ledger-root", type=Path, default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--index-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings"))
    args = ap.parse_args()

    # Preload all 10 indexes
    indexes = {a: load_index(a, args.index_root) for a in CANONICAL_10}

    n_citations = 0
    n_self_recall_hits = 0     # cited vec in citing agent's own index top-K (should be 0 by design)
    n_cross_recall_hits = 0    # cited vec in cited agent's index top-K (true recall)
    n_resolvable = 0           # cited vec_id syntactically valid (matched CANONICAL_VEC_ID_RE)
    cross_examples = []

    for c in mine_cross_agent_cites(args.ledger_root):
        n_citations += 1
        m = CANONICAL_VEC_ID_RE.search(c["cited_vec_id_pattern"])
        if not m:
            continue
        n_resolvable += 1
        # Need full vec_id token to check appearance — use the prefix-match pattern
        # (the cite may have a partial session-id; lookup based on first chars).
        # Approach: get cited_vec_id token (truncated up to ::session prefix), check
        # if ANY top-K result in cited_agent's index startswith the cite's token prefix.
        cite_prefix = c["cited_vec_id_pattern"]
        # Run query on cited agent's index (true cross-agent recall test)
        cited_topk = retrieve_topk(indexes.get(c["cited_agent"]), c["task_hint"], args.top_k)
        for vid in cited_topk:
            if vid and (vid.startswith(cite_prefix) or cite_prefix.startswith(vid[:60])):
                n_cross_recall_hits += 1
                if len(cross_examples) < 5:
                    cross_examples.append({
                        "citing_agent": c["citing_agent"],
                        "cited_agent": c["cited_agent"],
                        "task_hint": c["task_hint"][:80],
                        "matched_vec_id": vid,
                    })
                break
        # Also check citing agent's own index (should NOT find cross-agent vec — index isolation)
        citing_topk = retrieve_topk(indexes.get(c["citing_agent"]), c["task_hint"], args.top_k)
        for vid in citing_topk:
            if vid and (vid.startswith(cite_prefix) or cite_prefix.startswith(vid[:60])):
                n_self_recall_hits += 1
                break

    cross_recall = (n_cross_recall_hits / n_resolvable) if n_resolvable else 0.0
    self_recall = (n_self_recall_hits / n_resolvable) if n_resolvable else 0.0

    summary = {
        "wave": "wave-N forge LAG quick-fire (in-process; sibling-49 pivot)",
        "computed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "top_k": args.top_k,
        "n_cross_agent_citations_mined": n_citations,
        "n_resolvable_canonical_cites": n_resolvable,
        "n_cross_recall_hits": n_cross_recall_hits,
        "n_self_recall_hits_should_be_zero_by_isolation": n_self_recall_hits,
        "cross_recall_at_k": round(cross_recall, 4),
        "self_emitted_baseline_f6": 0.167,  # from prior F6 self-emitted measurement
        "uplift_vs_self_baseline": round(cross_recall - 0.167, 4),
        "examples": cross_examples,
        "honest_notes": [
            "In-process retrieval; identical TF-IDF algo to lag_retrieve.py.",
            "Cite-match uses prefix-startswith (partial cite vec_id tokens are common).",
            "Per warden DENY: cross-agent queries via citing index intentionally fail.",
            "G2 floor target: cross_recall_at_k >= 0.25 unlocks LANDING next-eligible.",
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
