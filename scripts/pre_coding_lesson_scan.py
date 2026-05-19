"""pre_coding_lesson_scan.py — operator law 2026-05-15:
"before every time they start coding after understanding their mission they
quickly scan their lessons this way they are actually compounding because they
are technically using their lessons to prevent errors in the code they are
about to make."

Tool: given a task-hint (file path + change description + cluster_tags), surface
the top-K most-relevant lessons from doctrine/lessons/*.aepkg/ packets. The
agent MUST review these BEFORE coding — citing them after the fact is theatre.

Mechanism:
  1. Read all lesson .aepkg/assets/original.html (or summary.md if available)
  2. Build a TF-IDF index over (frontmatter tags + first 200 chars of body)
  3. Score against task_hint
  4. Return top-K with: sibling_index, slug, truth_tag, tags, 1-line hook

Used by:
  - .claude/hooks/pre-coding-lesson-scan.ps1 (PreToolUse hook)
  - Agents directly via CLI when they want to scan before coding
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from collections import Counter


REPO_ROOT = Path("C:/Users/example-user/")
LESSON_ROOT = REPO_ROOT / "doctrine" / "lessons"

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]+")
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "when",
    "before", "after", "where", "what", "than", "have", "been", "they",
    "their", "these", "those", "such", "also", "some", "more", "most",
    "are", "was", "were", "but", "not", "all", "any", "can", "should",
    "must", "may", "would", "could", "lesson", "html", "aepkg", "div",
    "p", "h1", "h2", "h3", "li", "ul", "ol", "br", "doctype", "html",
}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower())
            if t not in STOPWORDS and len(t) >= 3]


def extract_lesson_meta(packet: Path) -> dict | None:
    """Read a lesson packet's body + frontmatter and return searchable metadata."""
    html_path = packet / "assets" / "original.html"
    if not html_path.exists():
        return None
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Extract frontmatter
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return None
    fm, body = m.group(1), m.group(2)
    fm_fields = {}
    for line in fm.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            fm_fields[key.strip()] = val.strip()
    # Strip HTML tags for body scan
    body_text = re.sub(r"<[^>]+>", " ", body)
    body_text = re.sub(r"\s+", " ", body_text).strip()[:2000]
    return {
        "slug": packet.stem,
        "sibling_index": fm_fields.get("sibling_index", "?"),
        "truth_tag": fm_fields.get("truth_tag", "?"),
        "tags": fm_fields.get("tags", ""),
        "slug_field": fm_fields.get("slug", packet.stem),
        "body_preview": body_text[:200],
        "tokens": tokenize(
            fm_fields.get("tags", "") + " " +
            fm_fields.get("slug", "") + " " +
            body_text
        ),
    }


def build_index(lesson_root: Path):
    """Build a TF-IDF index over all lessons."""
    packets = sorted(p for p in lesson_root.glob("*.aepkg") if p.is_dir())
    docs = []
    for pkg in packets:
        meta = extract_lesson_meta(pkg)
        if meta:
            docs.append(meta)
    # IDF
    df = Counter()
    for d in docs:
        for tok in set(d["tokens"]):
            df[tok] += 1
    n_docs = len(docs)
    idf = {t: math.log((n_docs + 1) / (df_t + 1)) + 1.0 for t, df_t in df.items()}
    # TF-IDF vectors
    for d in docs:
        tf = Counter(d["tokens"])
        d["vec"] = {t: tf[t] * idf.get(t, 1.0) for t in tf}
        d["norm"] = math.sqrt(sum(v * v for v in d["vec"].values())) or 1.0
    return docs, idf


def score_query(query_tokens: list[str], idf: dict, docs: list[dict]) -> list[tuple[dict, float]]:
    """Cosine score query against each doc."""
    q_tf = Counter(query_tokens)
    q_vec = {t: q_tf[t] * idf.get(t, 1.0) for t in q_tf}
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
    scored = []
    for d in docs:
        common = set(q_vec) & set(d["vec"])
        dot = sum(q_vec[t] * d["vec"][t] for t in common)
        sim = dot / (q_norm * d["norm"])
        if sim > 0:
            scored.append((d, sim))
    return sorted(scored, key=lambda kv: kv[1], reverse=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task-hint", required=True,
                    help="Description of the upcoming change + cluster_tags")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--format", default="markdown",
                    choices=["markdown", "ndjson", "stderr-advisory"])
    ap.add_argument("--lesson-root", type=Path, default=LESSON_ROOT)
    args = ap.parse_args()

    docs, idf = build_index(args.lesson_root)
    q_tokens = tokenize(args.task_hint)
    if not q_tokens:
        print("# No queryable tokens in task hint — lesson scan skipped.",
              file=sys.stderr if args.format == "stderr-advisory" else sys.stdout)
        return 0
    scored = score_query(q_tokens, idf, docs)[:args.top_k]

    out_stream = sys.stderr if args.format == "stderr-advisory" else sys.stdout

    if args.format in ("markdown", "stderr-advisory"):
        print(f"# Pre-Coding Lesson Scan (§60 law) — top {args.top_k} relevant lessons",
              file=out_stream)
        print(f"# Task hint: {args.task_hint[:120]}", file=out_stream)
        print(f"# Query tokens: {q_tokens[:12]}", file=out_stream)
        print("", file=out_stream)
        if not scored:
            print("# No matching lessons found. Proceed with awareness of"
                  " sibling-78 inherent-power discipline.", file=out_stream)
        for i, (d, sim) in enumerate(scored, 1):
            print(f"## {i}. sibling-{d['sibling_index']} — {d['slug_field']}",
                  file=out_stream)
            print(f"   truth_tag: {d['truth_tag']} | cosine: {sim:.3f}",
                  file=out_stream)
            print(f"   tags: {d['tags'][:120]}", file=out_stream)
            print(f"   preview: {d['body_preview'][:160]}", file=out_stream)
            print(f"   path: doctrine/lessons/{d['slug']}.aepkg/assets/original.html",
                  file=out_stream)
            print("", file=out_stream)
        print(f"# ACK by citing sibling-N in your ledger row's cites: field"
              f" if you reviewed them. Per §60 law: review BEFORE coding.",
              file=out_stream)
    elif args.format == "ndjson":
        for d, sim in scored:
            print(json.dumps({
                "sibling_index": d["sibling_index"],
                "slug": d["slug_field"],
                "truth_tag": d["truth_tag"],
                "tags": d["tags"],
                "cosine": round(sim, 4),
                "path": f"doctrine/lessons/{d['slug']}.aepkg/assets/original.html",
                "preview": d["body_preview"][:200],
            }, ensure_ascii=False))
        print(json.dumps({"_summary": {
            "n_hits": len(scored), "top_k": args.top_k,
            "method": "lesson-scan-pre-coding-section-60-law",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
