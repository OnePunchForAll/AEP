"""citation_graph_features.py — Loop-4 citation-graph features (PageRank + HITS).

Mines all cross-agent canonical citations from .claude/agents/_ledgers/*.jsonl
via mine_cross_agent_citations() from falsifier_6_cross_agent_cites and builds
a directed graph where edges go from the CITING row to the CITED row. Then:
  1. PageRank (damping=0.85, 50 power-iter, L1-tolerance 1e-6) — surfaces
     globally-important ledger rows (heavily-cited transitively).
  2. HITS (Kleinberg) — hubs (cite many) and authorities (cited by many).
  3. Per-agent + global graph stats (density, avg out-degree, top-K).

networkx is OPTIONAL — if missing we hand-roll both algorithms in <40 LOC
each via power iteration on a row-stochastic transition matrix. Power-iter
PageRank is the classic Brin-Page formulation (Stanford 1998); HITS is the
classic Kleinberg formulation (JACM 1999). NP-4 receipts in stdout via the
formula + iteration count + L1-residual report.

Output is a structured JSON dict on stdout AND a per-agent ranked-list NDJSON
when --emit-per-agent-ndjson is set; both are deterministic given an
identical ledger-root.

Composes with:
  - falsifier_6_cross_agent_cites.mine_cross_agent_citations (single-writer)
  - lag_retrieve_pagerank.py (Loop-4 RRF-fused retriever uses our PageRank)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from falsifier_6_cross_agent_cites import (  # noqa: E402
    CANONICAL_VEC_ID_RE,
    mine_cross_agent_citations,
    _load_ledger_cached,
)


def vec_id_of_row(agent: str, row: dict) -> str | None:
    """Construct the canonical vec_id 'ledger::<agent>::lamport-<N>::<slug>'.

    Slug = session_id ASCII normalization (the same convention used by
    build_lag_indices.py). Returns None if the row lacks lamport_counter.
    """
    counter = row.get("lamport_counter")
    if counter is None:
        counter = row.get("lamport_id")  # some agents use this field
    if counter is None:
        return None
    sid = row.get("session_id") or "unknown"
    sid = "".join(c if c.isalnum() or c == "-" else "-" for c in sid)
    # Strict canonical form per CANONICAL_VEC_ID_RE
    if isinstance(counter, int):
        token = f"lamport-{counter}"
    else:
        ctr = str(counter).strip()
        if ctr.startswith("lamport-"):
            token = ctr
        elif ctr.isdigit():
            token = f"lamport-{ctr}"
        else:
            token = f"lamport-null-{ctr}"
    return f"ledger::{agent}::{token}::{sid}"


def extract_cited_vec_id(citation: str) -> str | None:
    """Normalize a cite string to its canonical 'ledger::agent::lamport-N::slug'
    form when possible; informal mentions return the raw string."""
    m = CANONICAL_VEC_ID_RE.search(citation)
    if m:
        # Already canonical — return full match
        return m.group(0)
    return None


def build_citation_graph(ledger_root: Path) -> dict:
    """Walk all ledger rows, build a {source_vec_id -> [target_vec_id, ...]}
    directed-graph adjacency. Returns the adjacency + the per-row metadata
    needed downstream (agent owner, lamport, slug).
    """
    adjacency: dict[str, list[str]] = defaultdict(list)
    nodes_meta: dict[str, dict] = {}

    for ledger in sorted(ledger_root.glob("*.jsonl")):
        agent = ledger.stem
        cached = _load_ledger_cached(ledger)
        if cached["read_error"]:
            sys.stderr.write(f"WARN: skip {ledger.name}: {cached['read_error']}\n")
            continue
        for r in cached["rows"]:
            src_id = vec_id_of_row(agent, r)
            if src_id is None:
                continue
            nodes_meta.setdefault(src_id, {"agent": agent,
                                          "invocation": (r.get("invocation") or "")[:120]})
            for field in ("cites", "lag_influenced_by"):
                v = r.get(field) or []
                if not isinstance(v, list):
                    continue
                for c in v:
                    if not isinstance(c, str):
                        continue
                    tgt = extract_cited_vec_id(c)
                    if tgt is None:
                        continue
                    # Skip self-loops at the row level (same vec_id)
                    if tgt == src_id:
                        continue
                    adjacency[src_id].append(tgt)
                    # Register target node (may be referenced before encountered)
                    if tgt not in nodes_meta:
                        m = CANONICAL_VEC_ID_RE.search(tgt)
                        tgt_agent = m.group(1) if m else "unknown"
                        nodes_meta[tgt] = {"agent": tgt_agent, "invocation": ""}

    return {"adjacency": dict(adjacency), "nodes_meta": nodes_meta}


def pagerank(adjacency: dict[str, list[str]], nodes: list[str],
             damping: float = 0.85, max_iter: int = 50,
             tol: float = 1e-6) -> tuple[dict[str, float], dict]:
    """Hand-rolled PageRank via power iteration (Brin-Page 1998).

    Formula: PR(p) = (1-d)/N + d * sum_{q in BL(p)} PR(q) / L(q)
    where BL(p) = back-links to p, L(q) = out-degree of q.
    Dangling nodes (L(q)=0) redistribute mass uniformly per the standard
    teleportation handling.

    Returns (scores_dict, receipts_dict) where receipts captures iteration
    count + final L1 residual per NP-4 numbers-need-receipts discipline.
    """
    N = len(nodes)
    if N == 0:
        return {}, {"iterations": 0, "l1_residual": 0.0, "N": 0, "damping": damping}
    out_deg = {n: len(adjacency.get(n, [])) for n in nodes}
    # Reverse adjacency for back-link lookup
    in_links: dict[str, list[str]] = defaultdict(list)
    for src, tgts in adjacency.items():
        for t in tgts:
            in_links[t].append(src)
    pr = {n: 1.0 / N for n in nodes}
    teleport = (1.0 - damping) / N
    iters = 0
    l1 = 1.0
    for it in range(max_iter):
        iters = it + 1
        # Dangling mass: rows with no out-links donate uniformly
        dangle = sum(pr[n] for n in nodes if out_deg.get(n, 0) == 0)
        dangle_share = damping * dangle / N
        new_pr = {}
        for n in nodes:
            s = 0.0
            for q in in_links.get(n, []):
                deg = out_deg.get(q, 0)
                if deg > 0:
                    s += pr[q] / deg
            new_pr[n] = teleport + dangle_share + damping * s
        l1 = sum(abs(new_pr[n] - pr[n]) for n in nodes)
        pr = new_pr
        if l1 < tol:
            break
    return pr, {"iterations": iters, "l1_residual": l1, "N": N,
                "damping": damping, "formula": "PR=(1-d)/N + d*sum(PR(q)/L(q)) + d*dangle/N"}


def hits(adjacency: dict[str, list[str]], nodes: list[str],
         max_iter: int = 50, tol: float = 1e-6) -> tuple[dict[str, float], dict[str, float], dict]:
    """Hand-rolled HITS (Kleinberg JACM 1999).

    Formula:
      authority(p) = sum_{q in BL(p)} hub(q)
      hub(p)       = sum_{q in OL(p)} authority(q)
    Normalize by L2 each iter; converges in <20 iters typically.

    Returns (hubs, authorities, receipts).
    """
    if not nodes:
        return {}, {}, {"iterations": 0, "N": 0}
    in_links: dict[str, list[str]] = defaultdict(list)
    for src, tgts in adjacency.items():
        for t in tgts:
            in_links[t].append(src)
    hub = {n: 1.0 for n in nodes}
    auth = {n: 1.0 for n in nodes}
    iters = 0
    for it in range(max_iter):
        iters = it + 1
        # authority update
        new_auth = {n: sum(hub[q] for q in in_links.get(n, [])) for n in nodes}
        # hub update
        new_hub = {n: sum(new_auth[q] for q in adjacency.get(n, [])) for n in nodes}
        # L2 normalize
        a_norm = (sum(v * v for v in new_auth.values()) ** 0.5) or 1.0
        h_norm = (sum(v * v for v in new_hub.values()) ** 0.5) or 1.0
        new_auth = {k: v / a_norm for k, v in new_auth.items()}
        new_hub = {k: v / h_norm for k, v in new_hub.items()}
        d_auth = sum(abs(new_auth[n] - auth[n]) for n in nodes)
        d_hub = sum(abs(new_hub[n] - hub[n]) for n in nodes)
        auth, hub = new_auth, new_hub
        if max(d_auth, d_hub) < tol:
            break
    return hub, auth, {"iterations": iters, "N": len(nodes),
                       "formula": "authority(p)=sum hub(q in BL); hub(p)=sum auth(q in OL); L2-norm"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--damping", type=float, default=0.85)
    ap.add_argument("--max-iter", type=int, default=50)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--top-hub-auth", type=int, default=5)
    ap.add_argument("--out-pagerank-json", type=Path, default=None,
                    help="If set, write {vec_id: pagerank_score} JSON for lag_retrieve_pagerank.py to consume.")
    ap.add_argument("--emit-per-agent-ndjson", action="store_true")
    args = ap.parse_args()

    graph = build_citation_graph(args.ledger_root)
    adjacency = graph["adjacency"]
    nodes_meta = graph["nodes_meta"]
    nodes = sorted(nodes_meta.keys())
    n_nodes = len(nodes)
    n_edges = sum(len(v) for v in adjacency.values())

    pr_scores, pr_receipts = pagerank(adjacency, nodes,
                                       damping=args.damping,
                                       max_iter=args.max_iter)
    hub_scores, auth_scores, hits_receipts = hits(adjacency, nodes,
                                                   max_iter=args.max_iter)

    # Density: edges / (N * (N-1)) for directed graph
    density = (n_edges / (n_nodes * (n_nodes - 1))) if n_nodes > 1 else 0.0
    avg_out_degree = (n_edges / n_nodes) if n_nodes else 0.0

    top_pr = sorted(pr_scores.items(), key=lambda kv: kv[1], reverse=True)[:args.top_k]
    top_hubs = sorted(hub_scores.items(), key=lambda kv: kv[1], reverse=True)[:args.top_hub_auth]
    top_auths = sorted(auth_scores.items(), key=lambda kv: kv[1], reverse=True)[:args.top_hub_auth]

    # Per-agent breakdown
    per_agent_rankings: dict[str, list] = defaultdict(list)
    for vid, score in pr_scores.items():
        per_agent_rankings[nodes_meta[vid]["agent"]].append((vid, score))
    per_agent_top = {}
    for ag, pairs in per_agent_rankings.items():
        pairs.sort(key=lambda kv: kv[1], reverse=True)
        per_agent_top[ag] = [{"vec_id": v, "pagerank": round(s, 8),
                              "invocation": nodes_meta[v]["invocation"][:80]}
                              for v, s in pairs[:args.top_k]]

    out = {
        "loop": "loop-4-pagerank-citegraph-features",
        "ledger_root": str(args.ledger_root),
        "graph_stats": {
            "n_nodes": n_nodes,
            "n_edges": n_edges,
            "density": round(density, 6),
            "avg_out_degree": round(avg_out_degree, 4),
        },
        "pagerank": {
            "damping": args.damping,
            "iterations": pr_receipts["iterations"],
            "l1_residual_final": pr_receipts["l1_residual"],
            "formula": pr_receipts["formula"],
            "top_k": [{"rank": i + 1, "vec_id": v,
                       "pagerank": round(s, 8),
                       "agent": nodes_meta[v]["agent"],
                       "invocation": nodes_meta[v]["invocation"][:80]}
                      for i, (v, s) in enumerate(top_pr)],
        },
        "hits": {
            "iterations": hits_receipts["iterations"],
            "formula": hits_receipts["formula"],
            "top_hubs": [{"rank": i + 1, "vec_id": v,
                          "hub_score": round(s, 6),
                          "agent": nodes_meta[v]["agent"],
                          "invocation": nodes_meta[v]["invocation"][:80]}
                         for i, (v, s) in enumerate(top_hubs)],
            "top_authorities": [{"rank": i + 1, "vec_id": v,
                                 "authority_score": round(s, 6),
                                 "agent": nodes_meta[v]["agent"],
                                 "invocation": nodes_meta[v]["invocation"][:80]}
                                for i, (v, s) in enumerate(top_auths)],
        },
        "per_agent_top_k": per_agent_top,
        "advised_by": "scout.lamport-null-7a3b9c2d (external-prior-art agent-memory-mgmt) + "
                      "pathfinder.lamport-60 (4-phase ladder) + judge.lamport-210 (master verdict)",
    }

    if args.out_pagerank_json:
        # Write a flat {vec_id: pr_score} map for lag_retrieve_pagerank.py
        args.out_pagerank_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_pagerank_json.write_text(
            json.dumps({v: round(s, 10) for v, s in pr_scores.items()},
                       indent=2, sort_keys=True), encoding="utf-8")
        out["out_pagerank_json"] = str(args.out_pagerank_json)

    if args.emit_per_agent_ndjson:
        for ag, items in per_agent_top.items():
            for it in items:
                print(json.dumps({"agent": ag, **it}))
        print(json.dumps({"_summary": out["graph_stats"]}))
    else:
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
