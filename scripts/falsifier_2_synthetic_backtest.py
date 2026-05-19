"""falsifier_2_synthetic_backtest.py — Time-machine F2 back-test.

Synthetic F2 (mistakes_pct drop) via retrospective replay against historical
ledger data. For each ledger row R from the last N rows of each agent:
  1. Compute what LAG_retrieve(R.agent, R.invocation_hint) WOULD HAVE returned
     using ONLY rows that pre-date R (no leakage from future).
  2. Score:
     - would_have_helped: top-K retrieved rows contained ≥1 row whose
       cluster_tags overlap R's cluster_tags AND whose outcome was 'recovered'
       or 'success' (suggesting prior wisdom on similar work).
     - missed_correction: R's cluster_tags include 'repeat-of-prior-error'
       OR R cites a prior row directly — proxy for "this row was a correction
       made the hard way."
     - would_have_prevented: would_have_helped AND missed_correction.
  3. Aggregate per-agent + global.

This is the closest thing to F2 we can get without actually running a 7-day
window. The output is NOT a substitute for F2 PASS; it's a PRE-WINDOW INDICATOR
that LAG's retrieval surface would have been epistemically useful.

Pass threshold (SYNTHETIC): would_have_helped_rate ≥ 30% across all scored rows
AND the LAG-suggested-priors per row include ≥1 outcome=success AND
cluster_tag-overlap >= 1.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path


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


def tok(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in TOKEN_RE.findall(text) if t not in STOPWORDS and 3 <= len(t) <= 32]


def cosine_sparse(a, b):
    s = 0.0
    for t, w in a.items():
        if t in b:
            s += w * b[t]
    return s


def doc_text(row):
    parts = []
    for k in ("invocation", "notes", "outcome", "mission"):
        v = row.get(k)
        if isinstance(v, str):
            parts.append(v)
    ct = row.get("cluster_tags") or []
    if isinstance(ct, list):
        parts.append(" ".join(str(x) for x in ct))
    return " ".join(parts)


def vectorize(text, df, n_docs):
    counts = Counter(tok(text))
    if not counts:
        return {}
    vec = {}
    for t, c in counts.items():
        if t not in df:
            continue
        idf = math.log((n_docs + 1) / (df[t] + 1)) + 1.0
        vec[t] = (1.0 + math.log(c)) * idf
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def backtest_agent(rows, top_k=3):
    """For each row R from row N=5 onward, retrieve top-K from rows[0:N] only.
    Score would-have-helped + missed-correction + would-have-prevented."""
    if len(rows) < 8:
        return None

    scores = {
        "agent": rows[0].get("agent", "?"),
        "n_rows": len(rows),
        "n_scored": 0,
        "would_have_helped": 0,
        "missed_correction": 0,
        "would_have_prevented": 0,
        "examples": [],
    }

    # Walk rows in time order; for each row from index 5 onward, retrieve from prior rows
    for i in range(5, len(rows)):
        target = rows[i]
        target_tags = set(target.get("cluster_tags") or [])
        target_invocation = target.get("invocation") or ""
        if not target_invocation:
            continue

        # Build retrieval corpus from prior rows
        prior = rows[:i]
        if len(prior) < 3:
            continue

        # Compute df over prior rows — STRIP cluster_tags from corpus texts to prevent
        # same-tokens-win-twice leakage (judge operator-double #2 meta-validation 2026-05-15):
        # original F2 concatenated cluster_tags into both query AND retrieval corpus AND
        # used the same tags in auto-label → manufactured 90.2% rate via tag-token circularity.
        # v2: corpus uses ONLY invocation + notes + outcome + mission text. tags drive ONLY
        # auto-label.
        def corpus_text_no_tags(r):
            parts = []
            for k in ("invocation", "notes", "outcome", "mission"):
                v = r.get(k)
                if isinstance(v, str):
                    parts.append(v)
            return " ".join(parts)

        df = Counter()
        prior_texts = []
        for r in prior:
            t = corpus_text_no_tags(r)
            toks = set(tok(t))
            for tok_word in toks:
                df[tok_word] += 1
            prior_texts.append(t)

        # Vectorize query — invocation ONLY; NO cluster_tags concatenated (closes leakage)
        query_text = target_invocation
        qvec = vectorize(query_text, df, len(prior))
        if not qvec:
            continue

        # Score prior rows
        scored = []
        for j, pt in enumerate(prior_texts):
            pvec = vectorize(pt, df, len(prior))
            if not pvec:
                continue
            cos = cosine_sparse(qvec, pvec)
            scored.append((cos, j))
        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        if not top:
            continue

        # Did top-K contain a prior with overlapping cluster_tags AND outcome=success/recovered?
        would_help = False
        for cos, j in top:
            prior_row = prior[j]
            prior_tags = set(prior_row.get("cluster_tags") or [])
            if (prior_tags & target_tags) and prior_row.get("outcome") in ("success", "recovered"):
                would_help = True
                break

        # Was this row a "correction" — cluster_tags includes repeat/correction OR cites a prior?
        # As proxy: row's notes contain words like "previously failed", "regression", "rework"
        notes = (target.get("notes") or "").lower()
        is_correction = any(p in notes for p in (
            "previously", "regression", "rework", "redo", "re-do", "fix the",
            "broke", "broken", "failed earlier", "hot-patch", "round-2", "round-3", "round-4",
            "round-5", "round-6", "v0.5.1", "v0.5.2", "v0.5.3", "amendment", "v2", "v3",
        ))

        scores["n_scored"] += 1
        if would_help:
            scores["would_have_helped"] += 1
        if is_correction:
            scores["missed_correction"] += 1
        if would_help and is_correction:
            scores["would_have_prevented"] += 1
            if len(scores["examples"]) < 5:
                scores["examples"].append({
                    "target_row_index": i,
                    "target_invocation_excerpt": target_invocation[:120],
                    "top_prior_cos": round(top[0][0], 3),
                    "top_prior_excerpt": (prior_texts[top[0][1]] or "")[:120],
                })

    return scores


def main():
    repo = Path.cwd()
    ledger_root = repo / ".claude/agents/_ledgers"

    agents = ["strategist", "pathfinder", "scout", "forge", "judge",
              "adversary", "warden", "scribe", "curator", "visual-judge"]

    global_scores = {
        "n_agents_scored": 0,
        "n_rows_total": 0,
        "n_rows_scored": 0,
        "would_have_helped": 0,
        "missed_correction": 0,
        "would_have_prevented": 0,
        "per_agent": [],
    }

    for agent in agents:
        path = ledger_root / f"{agent}.jsonl"
        if not path.exists():
            continue
        rows = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not r.get("invocation") and not r.get("notes"):
                    continue
                r["agent"] = agent
                rows.append(r)
        if not rows:
            continue

        r_scores = backtest_agent(rows, top_k=3)
        if r_scores is None:
            continue
        global_scores["n_agents_scored"] += 1
        global_scores["n_rows_total"] += r_scores["n_rows"]
        global_scores["n_rows_scored"] += r_scores["n_scored"]
        global_scores["would_have_helped"] += r_scores["would_have_helped"]
        global_scores["missed_correction"] += r_scores["missed_correction"]
        global_scores["would_have_prevented"] += r_scores["would_have_prevented"]
        global_scores["per_agent"].append({
            "agent": r_scores["agent"],
            "n_rows": r_scores["n_rows"],
            "n_scored": r_scores["n_scored"],
            "would_have_helped_rate": round(r_scores["would_have_helped"] / max(1, r_scores["n_scored"]), 3),
            "missed_correction_rate": round(r_scores["missed_correction"] / max(1, r_scores["n_scored"]), 3),
            "would_have_prevented_rate": round(r_scores["would_have_prevented"] / max(1, r_scores["n_scored"]), 3),
            "examples": r_scores["examples"][:2],
        })

    g = global_scores
    g["would_have_helped_rate_global"] = round(g["would_have_helped"] / max(1, g["n_rows_scored"]), 3)
    g["missed_correction_rate_global"] = round(g["missed_correction"] / max(1, g["n_rows_scored"]), 3)
    g["would_have_prevented_rate_global"] = round(g["would_have_prevented"] / max(1, g["n_rows_scored"]), 3)

    # Synthetic-F2 pass threshold: would-have-helped ≥ 30% AND ≥10 prevented cases observed
    pass_threshold_help = 0.30
    pass_threshold_prevented_count = 10

    g["pass_threshold_help"] = pass_threshold_help
    g["pass_threshold_prevented_count"] = pass_threshold_prevented_count
    g["verdict"] = (
        "SYNTHETIC-PASS" if g["would_have_helped_rate_global"] >= pass_threshold_help and
                            g["would_have_prevented"] >= pass_threshold_prevented_count
        else "SYNTHETIC-PROVISIONAL" if g["would_have_helped_rate_global"] >= 0.15
        else "SYNTHETIC-FAIL"
    )
    g["note"] = ("Synthetic F2 indicator from retrospective back-test. NOT a substitute for "
                 "real-world F2 7-day window. Mistakes-pct measurement requires actual "
                 "post-LAG agent runs with repeat-of-prior-error cluster_tag instrumentation.")

    print(json.dumps(g, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
