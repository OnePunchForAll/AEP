"""lag_retrieve_bm25.py — BM25 alternative to lag_retrieve.py (TF-IDF cosine).

DROP-IN ALTERNATIVE to lag_retrieve.py with the SAME CLI surface
(--agent / --task-hint / --top-k / --format), but ranking with BM25Okapi
(k1=1.2, b=0.75 — Robertson/Zaragoza literature defaults).

Why this exists
  Pathfinder G2 step-2: surface a non-TF-IDF retriever so F6 task-aligned
  recall_lift can be measured ACROSS retrievers, not just at one fixed
  ranking function. Scout's external prior-art row (lamport-null-0f4c5c5e
  -1c30… "retrieval architectures beyond TF-IDF") names BM25 as the 1990s
  floor that pure-TF-IDF stacks fall below. Forge ships the floor so
  future hybrid stacks (RRF / SPLADE / ColBERT) have a calibrated baseline.

Schema-additive
  * Reads the SAME index (built by build_lag_indices.py — index.jsonl +
    vocabulary.jsonl). Re-tokenizes raw_invocation_excerpt + raw_notes_excerpt
    on the fly to recover term-frequency counts BM25 needs (the cached
    sparse_vec already pre-multiplied tf*idf, so we'd lose tf granularity).
  * Output JSON includes `retriever: "bm25"` field for downstream falsifier
    detection (so falsifier_6_task_aligned.py can A/B both retrievers).
  * lag_retrieve.py is UNCHANGED.

Cross-agent canonical citations (eat-own-dogfood with sibling-78
compute_null_lamport_token):
  * scout    — ledger::scout::lamport-null-0f4c5c5e1c30::external-prior-art-retrieval
  * pathfinder — ledger::pathfinder::lamport-59::closure-surge-pathfinder-g2-ladder
  * judge    — ledger::judge::lamport-208::final-round-judge-f6-battery

Truth tag: STRONGLY PLAUSIBLE (forge.lamport-212 2026-05-15;
sibling-78-aligned, schema-additive).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Single-writer discipline: import shared filters/scrubbers/canonicals from
# lag_retrieve.py (so A7/A11/A12 mitigations stay in lock-step). Per §50 EH.
from lag_retrieve import (
    CANONICAL_AGENTS,
    IMPERATIVE_PATTERNS,
    STOPWORDS,
    TOKEN_RE,
    b2,
    canon,
    days_since,
    estimate_tokens,
    format_injection_block,
    is_superseded,
    scrub_imperatives,
    tokenize,
)


# ----------------------------------------------------------------------------
# BM25Okapi (hand-rolled, ~40 LOC)
# ----------------------------------------------------------------------------

# Robertson/Zaragoza "Probabilistic Relevance Framework" (2009) defaults; same
# values used by Lucene/Elasticsearch/Whoosh/rank_bm25 out of the box.
BM25_K1_DEFAULT = 1.2
BM25_B_DEFAULT = 0.75


def bm25_idf(n_docs: int, df: int) -> float:
    """Robertson-Spärck Jones IDF used by BM25Okapi.

    idf(t) = ln( (N - df + 0.5) / (df + 0.5) + 1 )

    The +1 inside the ln keeps idf >= 0 even when df > N/2 (common terms),
    matching rank_bm25's BM25Okapi behavior. Without it, very common terms
    can produce negative scores, which BM25Plus addresses but Okapi does not.
    """
    return math.log(((n_docs - df + 0.5) / (df + 0.5)) + 1.0)


def build_bm25_corpus(rows: List[Dict[str, Any]]) -> Tuple[List[List[str]], Dict[str, int], float]:
    """Tokenize all rows; return (per-doc token lists, document-frequency map,
    average doc length).

    Re-tokenizes raw_invocation_excerpt + raw_notes_excerpt on the fly because
    the cached sparse_vec is already tf*idf-weighted (we'd lose raw tf counts
    BM25 needs).
    """
    docs: List[List[str]] = []
    df_map: Dict[str, int] = {}
    total_len = 0
    for r in rows:
        text = ((r.get("raw_invocation_excerpt") or "") + " "
                + (r.get("raw_notes_excerpt") or ""))
        toks = tokenize(text)
        docs.append(toks)
        total_len += len(toks)
        for t in set(toks):  # df = doc frequency (set, not multi-count)
            df_map[t] = df_map.get(t, 0) + 1
    avgdl = (total_len / len(docs)) if docs else 1.0
    return docs, df_map, avgdl


def bm25_score(
    query_toks: List[str],
    doc_toks: List[str],
    df_map: Dict[str, int],
    n_docs: int,
    avgdl: float,
    k1: float = BM25_K1_DEFAULT,
    b: float = BM25_B_DEFAULT,
) -> float:
    """BM25Okapi score for one (query, document) pair.

    Sum over query terms of:
        idf(t) * (tf(t,d) * (k1+1)) / (tf(t,d) + k1 * (1 - b + b*|d|/avgdl))

    Returns 0.0 on empty query or empty document.
    """
    if not query_toks or not doc_toks:
        return 0.0
    doc_len = len(doc_toks)
    doc_tf = Counter(doc_toks)
    score = 0.0
    for qt in set(query_toks):  # dedup query terms (same as rank_bm25)
        df = df_map.get(qt, 0)
        if df == 0:
            continue
        tf = doc_tf.get(qt, 0)
        if tf == 0:
            continue
        idf = bm25_idf(n_docs, df)
        denom = tf + k1 * (1.0 - b + b * doc_len / avgdl)
        score += idf * (tf * (k1 + 1.0)) / denom
    return score


# ----------------------------------------------------------------------------
# Index loader (reuses index.jsonl + index.meta.json; vocabulary.jsonl ignored
# because BM25 computes IDF from doc-frequency directly, not the cached IDF)
# ----------------------------------------------------------------------------

def load_index_for_bm25(index_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(index_dir / "index.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    meta: Dict[str, Any] = {}
    if (index_dir / "index.meta.json").exists():
        meta = json.loads((index_dir / "index.meta.json").read_text(encoding="utf-8"))
    return rows, meta


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", required=True)
    # Defender-incident remediation 2026-05-16: --task-file <path> is preferred;
    # --task-hint argv is restricted to short ASCII via _safe_task_loader.
    # Policy: doctrine/68-defender-alert-stops-burn.html.
    from _safe_task_loader import (  # noqa: E402
        TaskHintRejected,
        add_task_args,
        die_on_rejection,
        load_task_hint,
    )
    add_task_args(ap)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--excerpt-chars", type=int, default=300)
    ap.add_argument("--max-age-days", type=int, default=30)
    ap.add_argument("--min-score-stale", type=float, default=4.0,
                    help="BM25 score floor that overrides the age filter "
                         "(roughly equivalent to lag_retrieve's --min-cos-stale).")
    ap.add_argument("--exclude-reliability", default="",
                    help="comma-separated reliability tiers to exclude")
    ap.add_argument("--index-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/embeddings"))
    ap.add_argument("--format", choices=["ndjson", "injection-block", "stderr-advisory"],
                    default="injection-block")
    ap.add_argument("--allow-non-canonical-agent", action="store_true",
                    help="debug-only: skip canonical-10 allowlist (A11)")
    ap.add_argument("--bm25-k1", type=float, default=BM25_K1_DEFAULT,
                    help=f"BM25 k1 (default {BM25_K1_DEFAULT}, lit. range 1.2-2.0)")
    ap.add_argument("--bm25-b", type=float, default=BM25_B_DEFAULT,
                    help=f"BM25 b (default {BM25_B_DEFAULT}, lit. value)")
    # Loop 9 F1/F2 hot-reload integration. When ON: routes through HotReloadIndex
    # over the contextual-indexes/ substrate; BM25 re-tokenizes the
    # raw_invocation_excerpt + raw_notes_excerpt on the post-refresh rows.
    # PageRank etc are downstream-only; here we only refresh the candidate pool.
    ap.add_argument("--hot-reload", action="store_true",
                    help="Route through HotReloadIndex; closes adversary L2-NEW-A4 stale-index "
                         "race at retriever boundary. --index-root is overridden to "
                         "projects/v11-aep/publish-ready/aep/data/contextual-indexes when ON.")
    ap.add_argument("--hot-reload-ledger-path", type=Path, default=None)
    ap.add_argument("--hot-reload-index-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes"))
    args = ap.parse_args(argv)

    try:
        task_hint = load_task_hint(args)
    except TaskHintRejected as exc:
        die_on_rejection(exc)
        return 2  # unreachable

    # A11 mitigation (BLOCK): canonical-10 allowlist enforced at CLI level.
    if args.agent not in CANONICAL_AGENTS and not args.allow_non_canonical_agent:
        raise SystemExit(
            f"A11 BLOCK: agent='{args.agent}' is not in canonical-10 allowlist. "
            f"Operator-disabled or unknown agents cannot have ledgers retrieved. "
            f"Pass --allow-non-canonical-agent ONLY for debug; production callers "
            f"must check."
        )

    # Loop 9 hot-reload integration: route via HotReloadIndex over the
    # contextual-indexes/ substrate. BM25 just needs the refreshed rows with
    # raw_invocation_excerpt + raw_notes_excerpt (HRI's extract_doc_from_ledger_row
    # provides both). text_sha256 is aliased from contextual_text_sha256.
    hot_reload_meta = None
    if args.hot_reload:
        from hot_reload_index import HotReloadIndex
        hri_index_path = args.hot_reload_index_root / f"{args.agent}.jsonl"
        if not hri_index_path.exists():
            msg = f"# LAG-BM25: hot-reload contextual index not found for agent={args.agent} at {hri_index_path}"
            if args.format == "stderr-advisory":
                print(f"[LAG-BM25] {msg}", file=sys.stderr)
            else:
                print(msg)
            return 0
        ledger_path = args.hot_reload_ledger_path or Path(".claude/agents/_ledgers") / f"{args.agent}.jsonl"
        hri = HotReloadIndex(args.agent, ledger_path, args.hot_reload_index_root, k_tags=3)
        n_added = hri._maybe_refresh()
        rows = []
        for r in hri.rows:
            r2 = dict(r)
            if "text_sha256" not in r2 and "contextual_text_sha256" in r2:
                r2["text_sha256"] = r2["contextual_text_sha256"]
            rows.append(r2)
        meta = {"hot_reload": True, "n_added_in_refresh": n_added,
                "n_docs_indexed_post_refresh": hri.n_docs}
        hot_reload_meta = hri.refresh_status()
        index_dir = hri_index_path.parent
    else:
        index_dir = args.index_root / f"agent-{args.agent}"
        if not (index_dir / "index.jsonl").exists():
            msg = f"# LAG-BM25: no index for agent={args.agent} at {index_dir}"
            if args.format == "stderr-advisory":
                print(f"[LAG-BM25] {msg}", file=sys.stderr)
            else:
                print(msg)
            return 0

        rows, meta = load_index_for_bm25(index_dir)

    # SCOPE ASSERTION (warden BLOCK amendment #1): all rows must belong to
    # args.agent. Cross-agent retrieval is DENIED-BY-DEFAULT.
    for r in rows:
        if r.get("agent") != args.agent:
            raise SystemExit(
                f"§04 LAG SECURITY VIOLATION: row {r.get('vec_id')} in index "
                f"{index_dir} belongs to agent={r.get('agent')} but spawning "
                f"agent={args.agent}. Cross-agent retrieval is DENIED. Halting."
            )

    query_toks = tokenize(task_hint)
    if not query_toks:
        msg = "# LAG-BM25: empty query token list (no in-vocab tokens)"
        if args.format == "stderr-advisory":
            print(f"[LAG-BM25] {msg}", file=sys.stderr)
        else:
            print(msg)
        return 0

    # Build BM25 corpus from raw text (sparse_vec is tf*idf, can't recover tf).
    docs, df_map, avgdl = build_bm25_corpus(rows)
    n_docs = len(rows)

    exclude_rel = set(r.strip().upper() for r in args.exclude_reliability.split(",") if r.strip())

    # Score all rows
    scored = []
    n_superseded_filtered = 0
    for i, r in enumerate(rows):
        score = bm25_score(query_toks, docs[i], df_map, n_docs, avgdl,
                           k1=args.bm25_k1, b=args.bm25_b)
        if score <= 0:
            continue

        rel = (r.get("reliability") or "").upper().replace(" ", "_").replace("/", "_")
        if rel in exclude_rel:
            continue

        age = days_since(r.get("date"))
        if age is not None and age > args.max_age_days and score < args.min_score_stale:
            continue

        if is_superseded(r):
            n_superseded_filtered += 1
            continue

        scored.append((score, age, r))

    scored.sort(key=lambda x: -x[0])

    # lag_influenced_by transitive exclusion (warden amendment #3 + A8 / A9
    # mitigation; chain-closed v2 per adversary operator-double 2026-05-15).
    by_vec = {r["vec_id"]: r for r in rows}

    def lag_closure(start_vec_id: str, depth_limit: int = 4) -> set:
        seen: set = set()
        frontier = {start_vec_id}
        for _ in range(depth_limit):
            new_frontier: set = set()
            for vid in frontier:
                if vid in seen:
                    continue
                seen.add(vid)
                rr = by_vec.get(vid)
                if rr:
                    new_frontier.update(rr.get("lag_influenced_by") or [])
            if not new_frontier - seen:
                break
            frontier = new_frontier - seen
        return seen

    selected = []
    closure_union: set = set()
    for score, age, r in scored:
        candidate_closure = lag_closure(r["vec_id"])
        if candidate_closure & closure_union:
            continue
        selected.append((score, age, r))
        closure_union.update(candidate_closure)
        if len(selected) >= args.top_k:
            break

    # Build hits with A7 scrubbing + tokenization
    hits = []
    total_tokens = 0
    for score, age, r in selected:
        excerpt_raw = (r.get("raw_invocation_excerpt") or "")[:args.excerpt_chars]
        notes_excerpt = (r.get("raw_notes_excerpt") or "")[:args.excerpt_chars]
        full_excerpt = (excerpt_raw + " | " + notes_excerpt).strip()[:args.excerpt_chars]
        scrubbed, n_scrubbed = scrub_imperatives(full_excerpt)
        toks = estimate_tokens(scrubbed) + 50
        if total_tokens + toks > args.max_tokens and hits:
            break
        total_tokens += toks
        age_str = f"{age:.0f}d" if age is not None else "?"
        hits.append({
            "rank": len(hits) + 1,
            "retriever": "bm25",          # downstream falsifier discriminator
            "bm25_k1": args.bm25_k1,
            "bm25_b": args.bm25_b,
            "score": round(score, 4),
            "cos": round(score, 4),       # alias for downstream callers that
                                          # parse "cos" generically; same number
            "vec_id": r["vec_id"],
            "agent": r["agent"],
            "source_path": r["source_path"],
            "session_id": r.get("session_id"),
            "date": r.get("date"),
            "cluster_tags": r.get("cluster_tags") or [],
            "outcome": r.get("outcome"),
            "reliability": r.get("reliability"),
            "axis_b": r.get("axis_b"),
            "text_sha256": r["text_sha256"],
            "age_days": age,
            "age_days_str": age_str,
            "scrubbed_excerpt": scrubbed,
            "n_imperatives_scrubbed": n_scrubbed,
            "derived_from_ledger": True,
        })

    # HCRL receipt
    receipts_path = Path(".claude/_logs/lag-receipts.jsonl")
    receipts_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "receipt_type": "lag_retrieval_bm25",
        "retriever": "bm25",
        "bm25_k1": args.bm25_k1,
        "bm25_b": args.bm25_b,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "agent": args.agent,
        "task_hint_sha256": "blake2b-256:" + b2(task_hint),
        "top_k": args.top_k,
        "retrieved_vec_ids": [h["vec_id"] for h in hits],
        "n_total_imperatives_scrubbed": sum(h["n_imperatives_scrubbed"] for h in hits),
        "n_superseded_filtered": n_superseded_filtered,
        "est_tokens": total_tokens,
        "max_tokens": args.max_tokens,
        "index_path": str(index_dir),
        "n_docs_indexed": n_docs,
        "avgdl": round(avgdl, 4),
    }
    receipt["this_receipt_hash"] = "blake2b-256:" + b2(canon(receipt))
    with open(receipts_path, "a", encoding="utf-8") as f:
        f.write(canon(receipt) + "\n")

    summary = {
        "agent": args.agent,
        "retriever": "bm25",
        "bm25_k1": args.bm25_k1,
        "bm25_b": args.bm25_b,
        "n_hits": len(hits),
        "n_total_searched": len(rows),
        "n_docs_indexed": n_docs,
        "avgdl": round(avgdl, 4),
        "est_tokens": total_tokens,
        "max_tokens": args.max_tokens,
        "cross_agent_assertion": "DENIED-BY-DEFAULT (warden amendment #1)",
        "hot_reload": bool(args.hot_reload),
        "hot_reload_meta": hot_reload_meta,
    }

    if args.format == "ndjson":
        for h in hits:
            print(canon(h))
        print(canon({"_summary": summary}))
    elif args.format == "injection-block":
        print(format_injection_block(hits, args.agent, summary))
    else:  # stderr-advisory
        block = format_injection_block(hits, args.agent, summary)
        for line in block.split("\n"):
            print(f"[LAG-BM25] {line}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
