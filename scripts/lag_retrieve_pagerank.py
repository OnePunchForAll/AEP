"""lag_retrieve_pagerank.py — PageRank-augmented LAG retriever.

Hybrid signal: TF-IDF cosine over the per-agent LAG index FUSED with PageRank
score (from citation_graph_features.py).

Why useful: TF-IDF is purely lexical; it cannot see that a row is heavily
peer-cited (load-bearing in the citation graph). PageRank score is a global
ranking signal completely independent of the query text, so it can be RRF-fused
with text-based retrieval without double-counting.

Two fusion modes (CLI flag --mode):
  - rrf  (default) — Reciprocal-Rank-Fusion between (a) TF-IDF ranking
    truncated to depth D and (b) the PageRank ranking restricted to the same
    candidate set. RRF k=60 per Cormack/Clarke/Buttcher SIGIR 2009.
  - linear — final_score = (1 - alpha) * cosine_norm + alpha * pagerank_norm.
    Defaults: alpha=0.30. Both signals min-max normalized to [0, 1].

The retriever delegates the TF-IDF stage to lag_retrieve.py (subprocess);
this preserves the single-writer invariant — there is exactly one TF-IDF
implementation, and this script only adds the PageRank lift on top.

PageRank scores load from data/citegraph-pagerank.json (produced by
citation_graph_features.py --out-pagerank-json). Vec_ids absent from the
PageRank map get score 0.0 (no boost; falls back to pure TF-IDF rank).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path("C:/Users/example-user/")


def load_pagerank(path: Path) -> dict[str, float]:
    if not path.exists():
        sys.stderr.write(f"WARN: pagerank map not found at {path}; "
                         f"all PR scores default to 0.0 (no boost)\n")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_tfidf_retriever(agent: str, task_hint: str, depth: int,
                         hot_reload: bool = False,
                         hot_reload_ledger_path: str | None = None) -> list[dict]:
    """Shell out to lag_retrieve.py at the given depth; return list of
    {vec_id, score} dicts in rank order (depth-K from base TF-IDF stage).

    Loop 9 F1/F2: when hot_reload=True, pass --hot-reload through to the base
    retriever so the candidate pool reflects the live ledger. NB: the PageRank
    map is pre-computed and STALE by construction — newly-appended marker rows
    will have PR=0.0 (no boost). Top-K-after-fusion ordering depends on RRF /
    linear weighting; the marker may not survive to top-1 if cosine alone
    isn't dominant. This is honest: fusion can NOT fully fix a stale PR map;
    only a graph rebuild can. We document the limit; we do NOT pretend.
    """
    # Defender-incident remediation 2026-05-16: task_hint is written to a
    # temp JSON file and passed via --task-file. Argv stays short + ASCII.
    # Policy: doctrine/68-defender-alert-stops-burn.html.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".task.json", delete=False, encoding="utf-8"
    ) as tf:
        json.dump({"task_hint": task_hint}, tf, ensure_ascii=False)
        task_file_path = tf.name
    try:
        cmd = [sys.executable, "projects/v11-aep/publish-ready/aep/scripts/lag_retrieve.py",
               "--agent", agent, "--task-file", task_file_path,
               "--top-k", str(depth), "--format", "ndjson"]
        if hot_reload:
            cmd.append("--hot-reload")
            if hot_reload_ledger_path:
                cmd.extend(["--hot-reload-ledger-path", hot_reload_ledger_path])
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    finally:
        try:
            Path(task_file_path).unlink()
        except OSError:
            pass
    hits = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_summary" in j:
            continue
        vid = j.get("vec_id")
        if vid:
            hits.append({"vec_id": vid,
                         "cosine": j.get("cos", j.get("cosine", j.get("score", 0.0)))})
    return hits


def rrf_fuse_pagerank(tfidf_hits: list[dict], pr_map: dict[str, float],
                      top_k: int, k: int = 60) -> list[dict]:
    """RRF-fuse the TF-IDF ranking (depth-D) with the candidate set's
    PageRank-induced ranking restricted to those same vec_ids."""
    # PR-ranking of THIS query's candidate set
    pr_ranked = sorted(
        [(h["vec_id"], pr_map.get(h["vec_id"], 0.0)) for h in tfidf_hits],
        key=lambda kv: kv[1], reverse=True,
    )
    scores: dict[str, float] = {}
    for rank_minus_1, h in enumerate(tfidf_hits):
        scores[h["vec_id"]] = scores.get(h["vec_id"], 0.0) + 1.0 / (k + rank_minus_1 + 1)
    for rank_minus_1, (vid, _) in enumerate(pr_ranked):
        scores[vid] = scores.get(vid, 0.0) + 1.0 / (k + rank_minus_1 + 1)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [{"vec_id": vid, "rrf_score": round(s, 6),
             "pagerank": round(pr_map.get(vid, 0.0), 10)}
            for vid, s in ordered]


def linear_fuse_pagerank(tfidf_hits: list[dict], pr_map: dict[str, float],
                         top_k: int, alpha: float = 0.30) -> list[dict]:
    """linear: (1-alpha) * cosine_norm + alpha * pagerank_norm. Min-max norm."""
    if not tfidf_hits:
        return []
    cosines = [h.get("cosine", 0.0) or 0.0 for h in tfidf_hits]
    prs = [pr_map.get(h["vec_id"], 0.0) for h in tfidf_hits]
    c_min, c_max = min(cosines), max(cosines)
    p_min, p_max = min(prs), max(prs)
    c_range = (c_max - c_min) or 1.0
    p_range = (p_max - p_min) or 1.0
    scored = []
    for h, c, p in zip(tfidf_hits, cosines, prs):
        c_n = (c - c_min) / c_range
        p_n = (p - p_min) / p_range
        scored.append({"vec_id": h["vec_id"],
                       "fused_score": round((1 - alpha) * c_n + alpha * p_n, 6),
                       "cosine_norm": round(c_n, 4),
                       "pagerank_norm": round(p_n, 4),
                       "pagerank": round(p, 10)})
    scored.sort(key=lambda d: d["fused_score"], reverse=True)
    return scored[:top_k]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", required=True)
    # Defender-incident remediation 2026-05-16: --task-file preferred;
    # --task-hint restricted to short ASCII.
    from _safe_task_loader import (  # noqa: E402
        TaskHintRejected,
        add_task_args,
        die_on_rejection,
        load_task_hint,
    )
    add_task_args(ap)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--depth", type=int, default=20,
                    help="TF-IDF candidate pool depth before fusion")
    ap.add_argument("--mode", choices=["rrf", "linear"], default="rrf")
    ap.add_argument("--alpha", type=float, default=0.30,
                    help="(linear only) PageRank weight in [0, 1]")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--pagerank-json", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/data/citegraph-pagerank.json"))
    ap.add_argument("--format", choices=["ndjson", "stderr-advisory"],
                    default="ndjson")
    # Loop 9 F1/F2 hot-reload pass-through. NOTE: PageRank map is pre-computed
    # and STALE by construction; new marker rows get PR=0.0 (no boost). The
    # candidate POOL refreshes but the global PR ranking does NOT. We do not
    # pretend otherwise.
    ap.add_argument("--hot-reload", action="store_true",
                    help="Pass --hot-reload through to the underlying TF-IDF subprocess. "
                         "Refreshes the candidate POOL; PageRank scores remain STALE "
                         "(graph rebuild required for fresh PR). Default OFF.")
    ap.add_argument("--hot-reload-ledger-path", type=str, default=None)
    args = ap.parse_args()

    try:
        task_hint = load_task_hint(args)
    except TaskHintRejected as exc:
        die_on_rejection(exc)
        return 2  # unreachable

    pr_map = load_pagerank(args.pagerank_json)
    tfidf_hits = run_tfidf_retriever(args.agent, task_hint, args.depth,
                                      hot_reload=args.hot_reload,
                                      hot_reload_ledger_path=args.hot_reload_ledger_path)
    if args.mode == "rrf":
        fused = rrf_fuse_pagerank(tfidf_hits, pr_map, args.top_k, k=args.rrf_k)
    else:
        fused = linear_fuse_pagerank(tfidf_hits, pr_map, args.top_k, alpha=args.alpha)

    if args.format == "ndjson":
        for i, h in enumerate(fused, 1):
            print(json.dumps({"rank": i, **h, "fusion": args.mode}))
        print(json.dumps({"_summary": {"agent": args.agent,
                                       "n_hits": len(fused),
                                       "depth": args.depth,
                                       "mode": args.mode,
                                       "pagerank_loaded": len(pr_map),
                                       "hot_reload": bool(args.hot_reload),
                                       "pagerank_freshness_note":
                                         "STALE by construction — graph rebuild required for fresh PR"}}))
    else:
        sys.stderr.write(json.dumps({"fused_top_k": fused,
                                     "agent": args.agent}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
