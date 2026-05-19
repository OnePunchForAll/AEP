"""cross_corpus_pool_retriever_multimodal.py - Loop 7 multi-modal extension.

OPERATOR DIRECTIVE 2026-05-15 (Loop 7): Extend the cross-corpus pool retriever
beyond {AEP project-ledger + PDF-AEP} to include TWO additional corpora:

  1. CODE-AST corpus: walk projects/v11-aep/publish-ready/aep/scripts/*.py;
     parse via stdlib ast; emit a row per top-level FunctionDef / AsyncFunctionDef
     with docstring; cluster_tags := keywords mined from docstring.

  2. IMAGE-OCR corpus (PILOT): if pytesseract + a tesseract binary are present,
     OCR the first N PNG/JPG candidates under .aepkit/{visual-evidence,
     reference-images,browser-evidence}/ and emit one row per image whose OCR
     yielded >=20 chars. Otherwise SKIP gracefully with a stderr note (so the
     pilot still validates the unified-pool architecture against code-AST).

The unified-pool / 3-tier scorer architecture is REUSED VERBATIM from
cross_corpus_pool_retriever.py. We import the existing loaders + scorer and
add two new loaders + a thin "load_all" facade. Single-writer discipline holds:
the canonical scorer remains in cross_corpus_pool_retriever.py.

CLI:
  python cross_corpus_pool_retriever_multimodal.py \\
      --query "compute null lamport token" --top-k 3

Output: ndjson rows + summary with per-corpus pool sizes + per-corpus top-k counts.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# Reuse the canonical scorer + 3-tier retrieval verbatim
sys.path.insert(0, str(Path(__file__).parent))
from cross_corpus_pool_retriever import (  # noqa: E402
    load_aepkit_pool,
    load_pdf_pool,
    retrieve,
    tokenize,
)


def _docstring_keywords(docstring: str, max_n: int = 8) -> list[str]:
    """Mine cluster_tag-style keywords from a docstring."""
    if not docstring:
        return []
    toks = tokenize(docstring)
    # Prefer "domain-y" tokens: those containing a digit, hyphen, or underscore
    # OR longer than 6 chars (heuristic for compound technical terms).
    scored = []
    seen = set()
    for t in toks:
        if t in seen:
            continue
        seen.add(t)
        score = 0
        if any(c in t for c in "-_") or any(c.isdigit() for c in t):
            score += 2
        if len(t) > 6:
            score += 1
        scored.append((score, t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:max_n]]


def load_code_ast_pool(scripts_dir: Path) -> list[dict]:
    """Walk *.py under scripts_dir; emit one row per top-level (Async)FunctionDef
    with a non-empty docstring."""
    pool: list[dict] = []
    if not scripts_dir.exists():
        return pool
    files = sorted(p for p in scripts_dir.glob("*.py") if p.is_file())
    for file_index, py_path in enumerate(files):
        try:
            src = py_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=str(py_path))
        except (SyntaxError, OSError):
            continue
        # Module-level functions only (Loop-7 pilot); nested functions deferred.
        func_index = 0
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node) or ""
            if not doc.strip():
                continue
            # Build a signature string: name(arg1, arg2, ...)
            args = [a.arg for a in node.args.args]
            sig = f"{node.name}({', '.join(args)})"
            tags = _docstring_keywords(doc)
            # Compose text from docstring + signature; mirrors how AEP project rows
            # combine context_prefix + raw_invocation_excerpt + raw_notes_excerpt.
            text = f"{sig}\n{doc}"
            pool.append({
                "pool_id": f"code-ast::{py_path.name}::{node.name}",
                "source_kind": "code-ast-python",
                "agent": "code-source",
                "text": text,
                "cluster_tags": tags,
                "date": "?",
                "session_id": py_path.name,
                "lamport_counter": file_index * 100 + func_index,
                "reliability": "?",
                "outcome": "n/a",
                "func_signature": sig,
                "func_lineno": node.lineno,
            })
            func_index += 1
    return pool


def _find_image_candidates(repo_root: Path, max_images: int = 10) -> list[Path]:
    """Sample images for the OCR pilot from .aepkit/ subtrees."""
    cands: list[Path] = []
    roots = [
        repo_root / ".aepkit" / "visual-evidence",
        repo_root / ".aepkit" / "reference-images",
        repo_root / ".aepkit" / "browser-evidence",
    ]
    for r in roots:
        if not r.exists():
            continue
        for ext in ("*.png", "*.jpg", "*.jpeg"):
            for p in sorted(r.rglob(ext)):
                # Skip tiny or huge images for the pilot
                try:
                    sz = p.stat().st_size
                except OSError:
                    continue
                if 5_000 < sz < 5_000_000:
                    cands.append(p)
                if len(cands) >= max_images:
                    return cands
    return cands


def load_image_ocr_pool(repo_root: Path, max_images: int = 10) -> tuple[list[dict], dict]:
    """PILOT image-OCR corpus. Returns (pool, status). Status fields:
    available (bool), reason (str), candidates_seen (int), ocr_success (int)."""
    status = {
        "available": False,
        "reason": "",
        "candidates_seen": 0,
        "ocr_success": 0,
    }
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as e:
        status["reason"] = f"skip: dependency missing ({e.name})"
        print(f"[image-ocr-pilot] SKIP: {status['reason']} - "
              f"unified pool will validate on code-AST + AEP project + PDF only",
              file=sys.stderr)
        return [], status
    # Check that a tesseract binary is callable
    try:
        _ = pytesseract.get_tesseract_version()
    except Exception as e:  # pragma: no cover - depends on env
        status["reason"] = f"skip: tesseract binary not callable ({type(e).__name__})"
        print(f"[image-ocr-pilot] SKIP: {status['reason']}", file=sys.stderr)
        return [], status
    candidates = _find_image_candidates(repo_root, max_images)
    status["candidates_seen"] = len(candidates)
    pool: list[dict] = []
    for img_path in candidates:
        try:
            with Image.open(img_path) as im:
                text = pytesseract.image_to_string(im) or ""
        except Exception:
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 20:
            continue
        status["ocr_success"] += 1
        pool.append({
            "pool_id": f"image-ocr::{img_path.name}",
            "source_kind": "image-ocr",
            "agent": "image-source",
            "text": text[:2000],
            "cluster_tags": [],
            "date": "?",
            "session_id": str(img_path.relative_to(repo_root)),
            "lamport_counter": None,
            "reliability": "?",
            "outcome": "n/a",
            "image_path": str(img_path.relative_to(repo_root)),
            "ocr_chars": len(text),
        })
    status["available"] = True
    if status["ocr_success"] == 0 and status["candidates_seen"] > 0:
        status["reason"] = "ocr-yielded-zero-substantive-strings"
    return pool, status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--idx-root", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/data/contextual-indexes"))
    ap.add_argument("--ledger-root", type=Path,
                    default=Path(".claude/agents/_ledgers"))
    ap.add_argument("--pdf-aep-claims", type=Path,
                    default=Path("tmp/pdf_test_output_2026-05-15/synthetic_test_2026-05-15.aepkg/data/claims.jsonl"))
    ap.add_argument("--pdf-fallback-jsonl", type=Path,
                    default=Path("tmp/pdf_test_output_2026-05-15/synthetic_test_2026-05-15.jsonl"))
    ap.add_argument("--code-scripts-dir", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/scripts"))
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--image-max", type=int, default=10)
    args = ap.parse_args()

    aepkit_pool = load_aepkit_pool(args.idx_root)
    pdf_pool = load_pdf_pool(args.pdf_aep_claims, args.pdf_fallback_jsonl)
    code_pool = load_code_ast_pool(args.code_scripts_dir)
    image_pool, image_status = load_image_ocr_pool(args.repo_root, args.image_max)

    unified_pool = aepkit_pool + pdf_pool + code_pool + image_pool

    hits, summary = retrieve(args.query, unified_pool, args.top_k, args.ledger_root)

    summary["aepkit_pool_size"] = len(aepkit_pool)
    summary["pdf_pool_size"] = len(pdf_pool)
    summary["code_ast_pool_size"] = len(code_pool)
    summary["image_ocr_pool_size"] = len(image_pool)
    summary["image_ocr_status"] = image_status
    summary["code_in_top_k"] = sum(
        1 for h in hits if h["source_kind"].startswith("code-ast"))
    summary["image_in_top_k"] = sum(
        1 for h in hits if h["source_kind"].startswith("image-ocr"))

    for h in hits:
        if h["score"] == float("inf"):
            h["score"] = "canonical-exact"
        print(json.dumps(h, ensure_ascii=False))
    print(json.dumps({"_summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
