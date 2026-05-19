"""PDF -> AEP companion pipeline.

Generality test for AEP project canonical-resolve approach beyond own ledger corpus.

Pipeline (PROVEN/RELIABLE for steps 1-4; STRONGLY PLAUSIBLE for step 5 .aepkg wrap):
  1. Read PDF text (try pdfplumber; else fallback to raw-stream BT/ET text extractor;
     else exit with `pip install pdfplumber` recommendation).
  2. Chunk text into 80-200 char rows (matches AEP project ledger row size).
  3. Emit JSONL with schema:
       {lamport_counter, session_id, invocation, notes, cluster_tags, citations, page}
  4. Extract citation patterns: `[N]`, `(Author Year)`, `Author et al. (Year)`,
     `(Author et al., Year)`.
  5. Wrap output JSONL in an .aepkg/ companion by delegating to
     convert_ledgers_and_agents_to_aep.step1_convert_ledger as the single-writer
     (pattern: single-writer-via-import; see forge.lamport-213).

Generality claim being tested: the canonical-resolve approach (sibling-82) =
direct-lookup over structured IDs. PDFs lack canonical IDs natively, so we
EMIT canonical IDs at chunk time (chunk:p<N>:<i>) and treat citation patterns
as cross-doc canonical-ID candidates. If retrieval over the resulting .aepkg
behaves the same way AEP project's own ledger corpus does (T1 canonical-resolve
dominates over T3 contextual-fallback), the approach generalizes.

Usage:
  python pdf_to_aep_companion.py <pdf_path> <output_dir>
  python pdf_to_aep_companion.py --self-test <output_dir>

Cites:
  - scout.lamport-null-0f4c5c5e1c30 (external-prior-art-retrieval-architectures-beyond-tfidf)
  - pathfinder.lamport-60 (4-phase-retrieval-arch-ladder)
  - scribe.lamport-null-9d3a8b1c4e5f7a2b8c6d0e9f (sibling-82 author)
  - pattern: single-writer-via-import; canonical-resolve-tier-1
  - doctrine:57-retrieval-architecture-pattern; doctrine:50-epistemic-hygiene-meta-law
"""
import argparse
import hashlib
import json
import re
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path


# ---------- PDF text extraction ----------

def _try_pdfplumber(pdf_path: Path) -> list[tuple[int, str]] | None:
    """Returns list of (page_num, text). None if pdfplumber unavailable."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return None
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            pages.append((i, txt))
    return pages


def _fallback_pdf_text(pdf_path: Path) -> list[tuple[int, str]]:
    """Minimal raw PDF text extractor.

    Parses the PDF wire format: walks `obj` containers, locates streams with
    `/Filter /FlateDecode` or no filter, decompresses, then pulls glyph strings
    from BT...ET text objects via `(...)Tj` and `[...]TJ` operators.

    Limits (declare honestly per doctrine/50): no font/CMap decoding; no
    cross-page reading-order reconstruction beyond `obj` source order; no
    handling of non-FlateDecode filters or encrypted PDFs.
    Sufficient for PDFs we author with the synthetic generator below.
    Truth tag: STRONGLY PLAUSIBLE.
    """
    raw = pdf_path.read_bytes()
    pages: list[tuple[int, str]] = []
    page_num = 0
    # Walk object containers
    for m in re.finditer(rb"\d+ 0 obj\s*<<(.*?)>>\s*(stream\r?\n(.*?)\r?\nendstream)?\s*endobj",
                          raw, re.DOTALL):
        dict_blob = m.group(1)
        stream_blob = m.group(3)
        if stream_blob is None:
            continue
        # Identify page content streams: heuristic = has BT after decompress
        data = stream_blob
        if b"/FlateDecode" in dict_blob:
            try:
                data = zlib.decompress(stream_blob)
            except zlib.error:
                continue
        if b"BT" not in data:
            continue
        page_num += 1
        text_parts = []
        # (...)Tj   parenthesized literal
        for tm in re.finditer(rb"\(((?:\\.|[^\\()])*)\)\s*Tj", data):
            try:
                text_parts.append(tm.group(1).decode("latin-1"))
            except UnicodeDecodeError:
                pass
        # [(..)(..)]TJ   array of literals + kerning numerics
        for tm in re.finditer(rb"\[((?:\\.|[^\\\]])*)\]\s*TJ", data):
            arr = tm.group(1)
            for lit in re.finditer(rb"\(((?:\\.|[^\\()])*)\)", arr):
                try:
                    text_parts.append(lit.group(1).decode("latin-1"))
                except UnicodeDecodeError:
                    pass
        text = "".join(text_parts)
        # Unescape common PDF string escapes
        text = (text.replace("\\(", "(").replace("\\)", ")")
                    .replace("\\\\", "\\").replace("\\n", "\n")
                    .replace("\\r", "\r").replace("\\t", "\t"))
        pages.append((page_num, text))
    return pages


def extract_pdf_text(pdf_path: Path) -> tuple[list[tuple[int, str]], str]:
    """Returns (pages, extractor_name). Raises FileNotFoundError if pdf_path missing."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    pages = _try_pdfplumber(pdf_path)
    if pages is not None:
        return pages, "pdfplumber"
    pages = _fallback_pdf_text(pdf_path)
    if not pages:
        sys.stderr.write(
            "[warn] no text extracted with fallback parser. "
            "For richer PDFs install pdfplumber: pip install pdfplumber\n"
        )
    return pages, "fallback-raw-stream"


# ---------- Chunking ----------

CHUNK_MIN = 80
CHUNK_MAX = 200


def chunk_text(text: str) -> list[str]:
    """Chunk into 80-200 char rows on sentence-ish boundaries.

    AEP project ledger rows are typically 80-200 chars in their `invocation` /
    short-`notes` fields. Match that size for fair generality comparison.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        # Target 150 chars; prefer breaking on sentence boundary in [80, 200]
        end = min(i + CHUNK_MAX, n)
        if end < n:
            # Search for ". " in (i+CHUNK_MIN, i+CHUNK_MAX]
            window = text[i + CHUNK_MIN:end]
            m = re.search(r"\.\s", window)
            if m:
                end = i + CHUNK_MIN + m.end()
        chunk = text[i:end].strip()
        if len(chunk) >= CHUNK_MIN or i + CHUNK_MAX >= n:
            chunks.append(chunk)
        i = end
    return [c for c in chunks if c]


# ---------- Citation extraction ----------

CITE_PATTERNS = [
    # [12]  or [12, 34]  numeric bracket
    (re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]"), "bracket-num"),
    # (Smith et al., 2021)  or  (Smith et al. 2021)
    (re.compile(r"\(([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?),?\s+(\d{4})\)"), "paren-author-year"),
    # Smith et al. (2021)
    (re.compile(r"\b([A-Z][A-Za-z\-]+)\s+et\s+al\.?\s*\((\d{4})\)"), "narrative-et-al"),
    # Smith (2021)
    (re.compile(r"\b([A-Z][A-Za-z\-]+)\s*\((\d{4})\)"), "narrative-author-year"),
]


def extract_citations(text: str) -> list[dict]:
    cites = []
    seen = set()
    for pat, kind in CITE_PATTERNS:
        for m in pat.finditer(text):
            tok = (kind, m.group(0))
            if tok in seen:
                continue
            seen.add(tok)
            cites.append({"kind": kind, "raw": m.group(0), "span": [m.start(), m.end()]})
    return cites


# ---------- Cluster tags ----------

STOPWORDS = set("the a an and or of in on at to from for by with as is are was were "
                "be been being this that these those it its their there here have has had "
                "not no but so if then than which who whom whose where when how why what "
                "do does did done can could would should may might must will shall about into "
                "over under between through within without across after before above below "
                "ours yours hers his its theirs we you they them us i me my our your".split())


def cluster_tags_from(text: str, k: int = 6) -> list[str]:
    """Top-k content keywords as cluster_tags."""
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w in STOPWORDS:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:k]]


# ---------- Row emission ----------

def emit_rows(pages: list[tuple[int, str]], session_id: str) -> list[dict]:
    rows = []
    lamport = 0
    for page_num, page_text in pages:
        chunks = chunk_text(page_text)
        for i, chunk in enumerate(chunks):
            lamport += 1
            cites = extract_citations(chunk)
            tags = cluster_tags_from(chunk)
            rows.append({
                "lamport_counter": lamport,
                "session_id": session_id,
                "invocation": chunk[:80],
                "notes": chunk,
                "cluster_tags": tags,
                "citations": cites,
                "page": page_num,
                "chunk_id": f"chunk:p{page_num:03d}:{i:03d}",
            })
    return rows


# ---------- Synthetic PDF generator (no external lib) ----------

SYNTH_TEXT_PAGES = [
    # 5 pages of academic-style prose with 10 distinct citations
    "Retrieval-Augmented Generation has emerged as a load-bearing pattern in "
    "large-language-model systems [1]. Lewis et al. (2020) introduced the "
    "canonical formulation, and subsequent work by Karpukhin et al. (2020) "
    "established dense passage retrieval as a strong baseline [2]. The TF-IDF "
    "and BM25 (Robertson 2009) families remain competitive when documents are "
    "structurally homogeneous.",

    "Recent contextual retrieval approaches (Anthropic 2024) prepend "
    "structural metadata to each chunk before embedding, claiming up to "
    "sixty-seven percent reduction in retrieval failures [3]. Independent "
    "replication on the BEIR benchmark by Thakur et al. (2021) reports the "
    "magnitude depends on corpus length distribution [4]. Short-document "
    "regimes such as microblogs and ledger rows exhibit different scaling "
    "(Smith 2023).",

    "AEP project operates a structured ten-agent legion with append-only ledger "
    "rows. Each row carries cluster_tags and explicit cites arrays [5]. The "
    "canonical-resolve tier (the agent 2026) achieves seventy-one-point-five "
    "percent direct lookup recall before any soft matching fires (the project et "
    "al., 2026). This is structurally different from unstructured PDF "
    "retrieval [6].",

    "Hybrid three-tier retrieval composes canonical-resolve, slug-soft-match, "
    "and contextual-fallback into a single pipeline (the agent et al., 2026). "
    "When the corpus contains canonical IDs, tier-one dominates and tier-three "
    "graceful-degrades to zero [7]. When the corpus is unstructured (PDFs "
    "without DOIs), tier-three carries the load (Anthropic 2024) [8].",

    "The generality claim under test is whether the canonical-resolve "
    "approach transfers to substrates outside AEP project's own ledger. PDFs lack "
    "native canonical IDs, but citation tokens (Smith et al. 2023) can be "
    "treated as cross-document IDs, restoring tier-one applicability [9]. "
    "Page numbers and chunk indices act as auxiliary canonical anchors "
    "(Karpukhin et al., 2020) [10].",
]


def build_synthetic_pdf(out_path: Path) -> None:
    """Emit a valid minimal multi-page PDF with the SYNTH_TEXT_PAGES content.

    Hand-built PDF wire format. No external dependency. Uses Helvetica
    (PDF base-14 font, no embedding needed). Each page is a single column with
    simple wrapping.
    """
    def pdf_escape(s: str) -> str:
        return (s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)"))

    objs: list[bytes] = []

    def add(obj_bytes: bytes) -> int:
        objs.append(obj_bytes)
        return len(objs)  # 1-indexed obj number

    # Object 1: Catalog (forward reference to Pages obj)
    catalog_idx = add(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_idx = add(b"")  # placeholder; filled after page objs known
    font_idx = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_obj_nums: list[int] = []
    for page_text in SYNTH_TEXT_PAGES:
        # Wrap to ~80 chars per line
        words = page_text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 > 80:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)

        # Content stream: BT, set font, position, write each line, ET
        body_parts = ["BT", "/F1 12 Tf", "50 750 Td", "14 TL"]
        for j, line in enumerate(lines):
            esc = pdf_escape(line)
            if j == 0:
                body_parts.append(f"({esc}) Tj")
            else:
                body_parts.append("T*")
                body_parts.append(f"({esc}) Tj")
        body_parts.append("ET")
        body = "\n".join(body_parts).encode("latin-1", errors="replace")
        # Wrap in length dict + stream
        content_idx = add(b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream")
        page_idx = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 " + str(font_idx).encode() + b" 0 R >> >> "
            b"/Contents " + str(content_idx).encode() + b" 0 R >>"
        )
        page_obj_nums.append(page_idx)

    # Fill /Pages
    kids = b" ".join(str(n).encode() + b" 0 R" for n in page_obj_nums)
    objs[pages_idx - 1] = (
        b"<< /Type /Pages /Kids [" + kids + b"] /Count "
        + str(len(page_obj_nums)).encode() + b" >>"
    )

    # Build file
    out = bytearray()
    out += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = []
    for i, ob in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + ob + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n"
    out += f"0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n"
    out += b"<< /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"

    out_path.write_bytes(bytes(out))


# ---------- AEP wrap (delegate to single-writer) ----------

def wrap_as_aepkg(jsonl_path: Path, packet_name: str) -> tuple[bool, str]:
    """Delegate to the existing single-writer convert_ledgers_and_agents_to_aep.
    Pattern: single-writer-via-import (see forge.lamport-213).
    """
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    try:
        import convert_ledgers_and_agents_to_aep as conv
    except ImportError as e:
        return False, f"single-writer module unavailable: {e}"
    ok, msg = conv.step1_convert_ledger(jsonl_path, packet_name)
    return ok, msg


# ---------- CLI ----------

def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main():
    p = argparse.ArgumentParser(description="PDF -> AEP companion pipeline (AEP project generality test).")
    p.add_argument("pdf", nargs="?", help="Path to input PDF (or omit + --self-test)")
    p.add_argument("output_dir", help="Output directory for JSONL + .aepkg/")
    p.add_argument("--self-test", action="store_true",
                   help="Generate a synthetic PDF and ingest it (no real PDF needed)")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        pdf_path = out_dir / "input" / "synthetic_test_2026-05-15.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        build_synthetic_pdf(pdf_path)
        sys.stdout.write(f"[synthetic] wrote {pdf_path} ({pdf_path.stat().st_size} bytes)\n")
    else:
        if not args.pdf:
            p.error("pdf argument required unless --self-test")
        pdf_path = Path(args.pdf)

    pages, extractor = extract_pdf_text(pdf_path)
    sys.stdout.write(f"[extract] {extractor}: {len(pages)} pages\n")

    session_id = pdf_path.stem
    rows = emit_rows(pages, session_id=session_id)

    jsonl_path = (out_dir / f"{session_id}.jsonl").resolve()
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.write(f"[jsonl] wrote {jsonl_path}: {len(rows)} rows\n")

    # Citation summary
    all_cites = [c for r in rows for c in r["citations"]]
    by_kind: dict[str, int] = {}
    for c in all_cites:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    sys.stdout.write(f"[citations] {len(all_cites)} total: {json.dumps(by_kind)}\n")

    # AEP wrap (delegate)
    ok, msg = wrap_as_aepkg(jsonl_path, session_id)
    sys.stdout.write(f"[aepkg] ok={ok}: {msg}\n")

    # Manifest summary
    summary = {
        "extractor": extractor,
        "pdf_path": str(pdf_path).replace("\\", "/"),
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "pages": len(pages),
        "rows": len(rows),
        "citations_total": len(all_cites),
        "citations_by_kind": by_kind,
        "session_id": session_id,
        "jsonl_path": str(jsonl_path).replace("\\", "/"),
        "aepkg_wrap_ok": ok,
        "aepkg_wrap_msg": msg,
        "created_at": utc_now_iso(),
    }
    (out_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sys.stdout.write(f"[summary] wrote {out_dir / 'pipeline_summary.json'}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
