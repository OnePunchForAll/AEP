"""falsifier_2_non_exact_slug.py — F2 P@10 restricted to NON-EXACT-SLUG queries.

Per sibling-85 H2 structural-bound attack discipline (2026-05-15):
  Baseline F2 (falsifier_2_precision_at_10.py) on full 20-query corpus reported
  mean_lift = -0.067 (TF-IDF cosine UNDER grep).  Hypothesis: grep dominates
  because many anchor rows live in source paths whose SLUG matches a verbatim
  query token (e.g. query "kernel admission contract" hits doctrine/lessons/...
  -kernel-admission-contract.aepkg via exact substring), giving grep a
  word-overlap advantage that no semantic retriever can structurally beat on
  20-row P@10.  Restricting F2 to NON-EXACT-SLUG queries (queries whose tokens
  do NOT appear verbatim in any cited-row slug) is predicted to flip lift
  positive: semantic-only queries are the regime where TF-IDF cosine can
  surface meaning-similar rows that share no surface tokens with the query.

Pattern citation: doctrine/lessons/2026-05-15-structural-bound-attack-
discipline.html (sibling-85, scribe-authored; predicts semantic-only subset
lift flips positive).

Methodology:
  1. Reuse F2's 20 deterministic queries from falsifier_2_precision_at_10.py.
  2. Reuse F2's auto-relevance labeling (cluster_tag/path/claim overlap with
     query tokens, ≥ max(2, |tokens|/2) match threshold) -> truth_relevant set.
  3. NEW STEP: derive slug-tokens from each truth-relevant row's source_path
     (strip directory + .aepkg/.html extension + date prefix + doctrine NN-
     prefix; split on '-'; keep tokens ≥ 3 chars).
  4. Classify query as EXACT-SLUG if any query token appears verbatim as a
     slug token in any truth-relevant row's source_path; else NON-EXACT-SLUG.
  5. Compute P@10 (TF-IDF cosine) and P@10 (grep) on the NON-EXACT-SLUG
     subset only.  Compare lift on full corpus vs lift on semantic-only.
  6. Verdict: did the restriction flip mean_lift positive?

Output: single JSON summary on stdout.

Cross-agent canonical citations (≥3, sibling-78 dual-axis discipline):
  - scribe:doctrine/lessons/2026-05-15-structural-bound-attack-discipline.html
    (sibling-85 author; H2 prediction this script tests)
  - judge:doctrine/_proposals/judge-2026-05-15-mega-wave-all-falsifiers-
    master-verdict-table.html (master verdict table; F2 baseline -0.067 row)
  - forge:doctrine/_proposals/forge-2026-05-15-impossible-cross-corpus-pool-
    retriever.html (cross-corpus pool retriever; structural-bound-attack
    analog on F1 — first empirical demonstration of the discipline)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


# 20 deterministic queries — IDENTICAL to falsifier_2_precision_at_10.py for
# apples-to-apples comparison on the same corpus.
QUERIES = [
    "codex burn evidence",
    "two-lane discipline falsifier",
    "hash chained receipt ledger",
    "epistemic hygiene meta law",
    "agent companion bridge",
    "operator scope expansion",
    "judge halt validator",
    "ten agent legion",
    "deep migration cycle closed",
    "lane B adversarial fixture",
    "single-source frontier risk",
    "contradiction reliability tier",
    "sharded aep dump",
    "stale candidate cleanup",
    "self cleaning architecture",
    "node cross runtime byte parity",
    "kernel admission contract",
    "session governor executor",
    "absorption pipeline §49",
    "operator unprompted re-derivation",
]


def tokenize_simple(text: str):
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-_]{2,}", text.lower()) if 3 <= len(t) <= 32]


def is_relevant(query: str, row: dict, query_tokens) -> bool:
    """Same auto-labeling as F2 baseline."""
    haystack = " ".join([
        row.get("source_path", "") or "",
        row.get("cluster_tag", "") or "",
        row.get("claim_id", "") or "",
        row.get("vec_id", "") or "",
    ]).lower()
    n_match = sum(1 for t in query_tokens if t in haystack)
    return n_match >= max(2, len(query_tokens) // 2)


SLUG_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
SLUG_DOC_PREFIX_RE = re.compile(r"^\d{2}-")
SLUG_EXT_RE = re.compile(r"\.(aepkg|html|md|jsonl|json)$")


def derive_slug_tokens(source_path: str) -> set:
    """Extract slug tokens from a source path.

    Strips directory, extension, date prefix (lessons), doctrine NN- prefix,
    and returns the residue tokenized on '-'.  Tokens shorter than 3 chars
    are dropped (matches tokenize_simple lower bound).
    """
    if not source_path:
        return set()
    p = source_path.replace("\\", "/").rsplit("/", 1)[-1]
    p = SLUG_EXT_RE.sub("", p)
    p = SLUG_DATE_RE.sub("", p)
    p = SLUG_DOC_PREFIX_RE.sub("", p)
    return {t for t in p.lower().split("-") if len(t) >= 3}


def grep_top10(query: str, repo_root: Path):
    tokens = tokenize_simple(query)
    if not tokens:
        return []
    tokens_by_len = sorted(tokens, key=len, reverse=True)
    primary = tokens_by_len[0]
    try:
        result = subprocess.run(
            ["grep", "-lir", "--include=*.jsonl", "--include=*.html", "--include=*.json", primary,
             str(repo_root / "doctrine"), str(repo_root / ".claude" / "agents")],
            capture_output=True, text=True, timeout=30,
        )
        hits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return hits[:10]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def semantic_top10(query: str, index_dir: Path):
    result = subprocess.run(
        [sys.executable, "projects/v11-aep/publish-ready/aep/scripts/aep_search.py",
         query, "--index", str(index_dir), "--top-k", "10", "--format", "jsonl"],
        capture_output=True, text=True, timeout=60,
    )
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_summary" in row:
            continue
        rows.append(row)
    return rows


def main():
    repo = Path.cwd()
    index_dir = repo / "projects/v11-aep/publish-ready/aep/embeddings/v1"
    if not (index_dir / "index.jsonl").exists():
        raise SystemExit(f"index not found at {index_dir}; run build_semantic_index.py first")

    rows_by_vec = {}
    rows_list = []
    with open(index_dir / "index.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows_by_vec[r["vec_id"]] = r
            rows_list.append(r)

    per_query_full = []      # all queries (matches F2 baseline)
    per_query_semantic = []  # NON-EXACT-SLUG subset (this attack)

    for q in QUERIES:
        qtok = tokenize_simple(q)
        if not qtok:
            continue

        # ===== TRUTH SET (same as F2 baseline) =====
        truth_relevant_full = set()
        for r in rows_list:
            if is_relevant(q, r, qtok):
                truth_relevant_full.add(r["vec_id"])

        if len(truth_relevant_full) < 3:
            continue

        # FMV BP-3 anchor downsample (matches F2 baseline)
        truth_sorted = sorted(truth_relevant_full, key=lambda v: hash((q, v)))
        truth_relevant = set(truth_sorted[:10])

        # ===== EXACT-SLUG CLASSIFIER =====
        qtok_set = set(qtok)
        exact_slug_hit = False
        slug_overlap_examples = []
        for vid in truth_relevant:
            sp = rows_by_vec.get(vid, {}).get("source_path", "") or ""
            slug_toks = derive_slug_tokens(sp)
            overlap = qtok_set & slug_toks
            if overlap:
                exact_slug_hit = True
                slug_overlap_examples.append({"row_path": sp, "overlap": sorted(overlap)})
                if len(slug_overlap_examples) >= 2:
                    break

        # ===== SEMANTIC top-10 =====
        sem_hits = semantic_top10(q, index_dir)
        sem_relevant_count = sum(1 for h in sem_hits if h["vec_id"] in truth_relevant)
        sem_p10 = sem_relevant_count / 10.0

        # ===== GREP top-10 =====
        grep_hits = grep_top10(q, repo)
        truth_paths = set()
        for vid in truth_relevant:
            r = rows_by_vec.get(vid, {})
            sp = r.get("source_path", "") or ""
            if sp:
                truth_paths.add(sp.replace("\\", "/"))
        grep_relevant_count = 0
        for g in grep_hits:
            g_norm = g.replace("\\", "/")
            for tp in truth_paths:
                if g_norm.endswith(tp) or tp in g_norm:
                    grep_relevant_count += 1
                    break
        grep_p10 = grep_relevant_count / 10.0

        rec = {
            "query": q,
            "exact_slug_hit": exact_slug_hit,
            "slug_overlap_examples": slug_overlap_examples,
            "sem_p10": round(sem_p10, 3),
            "grep_p10": round(grep_p10, 3),
            "lift": round(sem_p10 - grep_p10, 3),
            "sem_relevant": sem_relevant_count,
            "grep_relevant": grep_relevant_count,
            "n_truth_full": len(truth_relevant_full),
        }
        per_query_full.append(rec)
        if not exact_slug_hit:
            per_query_semantic.append(rec)

    if not per_query_full:
        raise SystemExit("no queries produced labelable results")

    def stats(rows):
        if not rows:
            return None
        ms = sum(r["sem_p10"] for r in rows) / len(rows)
        mg = sum(r["grep_p10"] for r in rows) / len(rows)
        return {
            "n": len(rows),
            "mean_sem_p10": round(ms, 4),
            "mean_grep_p10": round(mg, 4),
            "mean_lift": round(ms - mg, 4),
        }

    s_full = stats(per_query_full)
    s_sem = stats(per_query_semantic)
    delta = None
    if s_sem and s_full:
        delta = round(s_sem["mean_lift"] - s_full["mean_lift"], 4)
    flipped_positive = bool(s_sem and s_sem["mean_lift"] > 0)

    summary = {
        "falsifier": "F2-non-exact-slug-attack",
        "hypothesis": (
            "Restricting F2 to NON-EXACT-SLUG queries flips mean_lift positive "
            "by removing grep's word-overlap structural advantage."
        ),
        "pattern_source": "sibling-85 structural-bound-attack-discipline",
        "h2_prediction": "lift on semantic-only subset turns positive",
        "full_corpus": s_full,
        "non_exact_slug_subset": s_sem,
        "delta_mean_lift": delta,
        "n_queries_filtered_out_exact_slug": (s_full["n"] - s_sem["n"]) if s_sem else None,
        "h2_verdict": "PASS-FLIPPED-POSITIVE" if flipped_positive else (
            "PARTIAL-LIFT-IMPROVED" if (delta is not None and delta > 0) else
            "FAIL-NO-FLIP"
        ),
        "per_query_full": per_query_full,
        "per_query_non_exact_slug": per_query_semantic,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
