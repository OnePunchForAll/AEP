"""llm_judge_semantic_layer.py — Tier-4 LLM-judge semantic layer for the
hybrid retriever.

This module is the loop-8 deliverable for the AEP-V11-AEP-LOOPS-5-8 ladder
(pathfinder.lamport-null-bcdc549e4ace, 2026-05-15). It implements the prompt
template from codex burn 15 (PASS/PARTIAL/FAIL JSON output, max 30-word reason)
and caches verdicts keyed by the canonical BLAKE2b hash of (query, row_id,
row_text) using `lamport_null_fallback.compute_null_lamport_token`.

DESIGN INTENT (operator directive 2026-05-15 + pathfinder loop-6 spec lines
360-411):
  1. Cache-first: a (query, row) pair is hashed via the canonical row-bytes
     serializer and the resulting 24-hex BLAKE2b prefix is the cache key.
  2. Stub LLM (this commit): the wrapped LLM is a deterministic keyword-overlap
     classifier — PASS iff EVERY non-stopword query token appears in row_text
     (case-folded); FAIL otherwise. This is the cheapest disconfirmer for the
     mechanical layer; full Codex Spark or Claude Haiku integration is gated on
     this stub passing the 5-FP rejection test.
  3. Tier-4 integration: invoked AFTER tier-3 contextual retrieval has produced
     hits whose `match_citation` fails. The LLM-judge is asked: "does the
     top-1 row semantically match the cite query?" PASS = recover (mark
     matched, tier='tier4-llm-judge-recover'). FAIL/PARTIAL = stay missed.
  4. Append-only cache file: every invocation appends one JSON line to
     llm_judge_cache.jsonl (cache_key, query, row_id, verdict, reason, ts).
     Lookup is O(N) scan on import; for the 5-FP test N<<100, fine.

ADVERSARY AC-CLOSURE (lamport-55 100% FP attack 2026-05-15):
  The 43 tier-2 FPs were vocabulary-overlap matches with zero semantic
  identity (e.g. "verify-tc-d-re-run-independent" matched a 9-day-old row on
  a different mission whose invocation happened to contain those tokens).
  The stub IS a vocabulary-overlap classifier and therefore CANNOT defeat
  adversary's attack on its own — it WILL false-positive on the same 5
  hand-crafted vocabulary attacks adversary used (the-audit-doctrine-slot-
  promotion-verdict, lesson-capture-sibling-cross-agent, doctrine-validation-
  2026-05-15, etc.). That is the load-bearing finding of the test: the stub
  proves the WIRING works (cache hits, append-only, tier-4 integration) but
  the stub is INSUFFICIENT as a semantic gate. The 5-FP test below MUST
  rerun once the LLM wrapper is replaced with a real model (Haiku /
  Codex Spark) and the rejection rate should approach 5/5.

USAGE — programmatic (tier-4 integration):
  from llm_judge_semantic_layer import llm_judge_pair
  verdict = llm_judge_pair(query="cross-agent citation discipline",
                            row_id="ledger::forge::lamport-220",
                            row_text="F6 SELF canonical-resolve...")
  # verdict == {"verdict": "PASS"|"PARTIAL"|"FAIL",
  #             "reason": "...<=30 words",
  #             "cache_key": "lamport-null-...",
  #             "cache_hit": True|False}

USAGE — CLI:
  python llm_judge_semantic_layer.py \
    --query "cross-agent citation discipline" \
    --row-id "ledger::forge::lamport-220" \
    --row-text "F6 SELF canonical-resolve..."

Truth tag: STRONGLY PLAUSIBLE (judge.loop-8 2026-05-15; stub mechanical
wiring proven via 5-FP test; LLM-replacement step DEFERRED).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lamport_null_fallback import compute_null_lamport_token


CACHE_PATH = Path(__file__).parent.parent / "data" / "llm_judge_cache.jsonl"

# Codex burn 15 prompt template (PASS/PARTIAL/FAIL JSON output, max 30-word
# reason). The full template is consumed by the real-LLM call in the next
# iteration; the stub bypasses prompt construction and returns the rule-based
# verdict directly. Kept in source for the LLM-wrapper handoff.
PROMPT_TEMPLATE = """You are a citation-relevance judge. Given a query (the
intent of a cross-agent citation) and one candidate row (an existing ledger
row that may or may not be the cited row), decide whether the candidate is
the SEMANTIC match for the query — not merely a vocabulary-overlap match.

Output STRICT JSON with these keys only:
  verdict: "PASS" | "PARTIAL" | "FAIL"
  reason: STRING (max 30 words; cite the load-bearing semantic mismatch
                  if FAIL, or the load-bearing semantic match if PASS)

PASS = the candidate row is the intended cited evidence. The query's
       load-bearing claim is supported by THIS row's specific content
       (not a different row with overlapping vocabulary).
PARTIAL = the candidate row is in the same topic cluster but supports a
          DIFFERENT specific claim than the query asserts.
FAIL = the candidate row does not support the query's claim; vocabulary
       overlap is incidental.

Query: {query}
Candidate row_id: {row_id}
Candidate row_text: {row_text}

Respond ONLY with the JSON object. No prose, no markdown fences.
"""

# Stopword list for the stub keyword-overlap classifier. Lifted from the
# slug-soft-match tokenizer in falsifier_6_cross_agent_hybrid.py:soft_match_by_slug
# (set of common AEP project vocabulary that drove adversary's 5/5 attack hit rate).
STUB_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "for", "is", "in",
    "on", "at", "by", "with", "from", "as", "be", "was", "are", "this",
    "that", "ledger", "lamport", "null", "row", "agent", "ledger::",
    "doctrine", "lesson", "pattern", "vec_id", "id",
}


def _tokenize(text: str) -> set[str]:
    """Tokenize on non-alphanumeric; case-fold; drop stopwords."""
    tokens = re.split(r"[^a-zA-Z0-9]+", text.lower())
    return {t for t in tokens if t and t not in STUB_STOPWORDS and len(t) >= 3}


def _stub_llm_verdict(query: str, row_id: str, row_text: str) -> dict:
    """Deterministic stub: PASS iff every non-stopword query token appears
    in row_text; FAIL otherwise. PARTIAL when >=50% but <100% tokens hit.

    This mirrors the existing tier-2 soft-match heuristic and INHERITS its
    100% FP rate on adversary's vocabulary-stuffing attack. The stub's role
    is to prove the WIRING (cache, append-only, tier-4 integration) before
    paying for real-LLM calls.
    """
    q_tokens = _tokenize(query)
    r_tokens = _tokenize(row_text)
    if not q_tokens:
        return {"verdict": "FAIL", "reason": "Query has no informative tokens."}
    hit = q_tokens & r_tokens
    coverage = len(hit) / len(q_tokens)
    if coverage >= 1.0:
        return {
            "verdict": "PASS",
            "reason": f"Stub keyword-overlap 100% ({len(hit)}/{len(q_tokens)} tokens).",
        }
    if coverage >= 0.5:
        return {
            "verdict": "PARTIAL",
            "reason": f"Stub keyword-overlap {int(coverage*100)}% ({len(hit)}/{len(q_tokens)} tokens).",
        }
    return {
        "verdict": "FAIL",
        "reason": f"Stub keyword-overlap {int(coverage*100)}% ({len(hit)}/{len(q_tokens)} tokens).",
    }


def _cache_key(query: str, row_id: str, row_text: str) -> str:
    """BLAKE2b canonical hash of the (query, row_id, row_text) triple.

    Uses lamport_null_fallback.compute_null_lamport_token so the cache key
    shape matches AEP project's ledger-row canonical token shape exactly. Any
    change to the canonical serializer is automatically reflected here.
    """
    triple = {"query": query, "row_id": row_id, "row_text": row_text}
    return compute_null_lamport_token(triple)


def _load_cache() -> dict[str, dict]:
    """Load the append-only cache file into a dict keyed by cache_key.
    Later writes win on duplicate keys (idempotent re-validation supported)."""
    cache: dict[str, dict] = {}
    if not CACHE_PATH.exists():
        return cache
    for line in CACHE_PATH.read_text(encoding="utf-8", errors="strict").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = row.get("cache_key")
        if k:
            cache[k] = row
    return cache


def _append_cache(entry: dict) -> None:
    """Append a single cache entry as one JSON line."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def llm_judge_pair(query: str, row_id: str, row_text: str,
                    *, force_refresh: bool = False) -> dict:
    """Return the LLM-judge verdict for a (query, row_id, row_text) triple.

    Hits cache on canonical-hash key; misses fall through to _stub_llm_verdict
    (replace with real LLM call when stub passes the 5-FP test).
    """
    key = _cache_key(query, row_id, row_text)
    cache = _load_cache()
    if not force_refresh and key in cache:
        entry = dict(cache[key])
        entry["cache_hit"] = True
        return entry
    verdict = _stub_llm_verdict(query, row_id, row_text)
    entry = {
        "cache_key": key,
        "query": query[:200],
        "row_id": row_id,
        "row_text_preview": row_text[:200],
        "verdict": verdict["verdict"],
        "reason": verdict["reason"][:200],
        "stub": True,
        "ts": time.time(),
    }
    _append_cache(entry)
    entry["cache_hit"] = False
    return entry


def tier4_recover(query: str, top1_row_id: str, top1_row_text: str) -> tuple[bool, str]:
    """Tier-4 hybrid-retriever integration: returns (matched, tier).
    Called when tier-3 returned hits but match_citation failed.
    """
    res = llm_judge_pair(query=query, row_id=top1_row_id, row_text=top1_row_text)
    if res["verdict"] == "PASS":
        return (True, "tier4-llm-judge-recover")
    return (False, f"tier4-llm-judge-{res['verdict'].lower()}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", required=True, help="Cite intent / task hint.")
    ap.add_argument("--row-id", required=True, help="Candidate row id (vec_id).")
    ap.add_argument("--row-text", required=True, help="Candidate row text.")
    ap.add_argument("--force-refresh", action="store_true",
                    help="Ignore cache hit; re-invoke the LLM (stub).")
    args = ap.parse_args()
    res = llm_judge_pair(query=args.query, row_id=args.row_id,
                         row_text=args.row_text, force_refresh=args.force_refresh)
    print(json.dumps(res, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
