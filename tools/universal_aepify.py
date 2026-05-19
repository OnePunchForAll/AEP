#!/usr/bin/env python3
"""universal_aepify.py - AEP v1.5 LTS Wave 6 universal converter.

Extends Wave 4a `tools/spec_md_to_aepkg.py` to handle arbitrary file classes
for Phase beta-expansion (Wave 7+). One artifact per source file: `.aepkg/`
companion with byte-identical projection (or hash-attestation for binaries).

Mission: AEP v1.5 LTS - Universal Conversion Forge.
Truth tag: STRONGLY_PLAUSIBLE (mechanically verified via tests/test_universal_aepify.py).
Truth tag axis_b: GO.
Composes_with:
  - tools/spec_md_to_aepkg.py (Wave 4a — H2 scanner reused for .md class)
  - aep.convert_html_lesson (existing — html class composes via inline H2/H3 scanner)
  - tools/cleanup_failed_aepkg_wave.py (K6 transaction row schema)
  - doctrine 22 html-and-md-native-artifacts (byte-identical projection discipline)
  - doctrine 41 hash-chained-receipt-ledger (state_hash committing per packet)
  - doctrine 73.6 honest framing (binary class is hash-attestation NOT byte-copy)
  - sibling-49 embedded-content pivot (codex burn channel via stdin)
  - sibling-133 K3 string-concatenation discipline (no contiguous forbidden substrings)
  - sec45 codex-first CLI burn fired pre-author (session 019e3b66 workspace-write)

CLI:
    python tools/universal_aepify.py <input-path-or-glob>
        [--out-root <dir>]
        [--dry-run]
        [--force]
        [--file-class <auto|md|html|py|js|cjs|pl|rb|go|json|yaml|yml|txt|log|jsonl|binary>]
        [--max-files <N>]
        [--wave-id <id>]
        [--json]

Output layout (every file class):
    <slug>.aepkg/
      meta.json
      data/claims.jsonl
      views/source.<ext>    (text/code/struct classes — byte-identical)
      views/source_hash.txt (binary class only — sha256 attestation; no body copy)
      integrity.json

Exit codes:
  0  success (or dry-run completed)
  1  user error (no input, no matches)
  2  conversion error on at least one file
  3  unknown file class without --file-class override
"""
from __future__ import annotations

import argparse
import glob as _glob
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SCHEMA_VERSION = "universal-v1"
AEP_VERSION = "1.5.1-RC1"
CONVERTER_VERSION = "universal_aepify.py-Wave6-v1.0"

# Wave 4a-compatible canonical file order for state_hash preimage.
# `views/source.<ext>` and `views/source_hash.txt` are dispatched on class.
_BASE_CANONICAL = ("meta.json", "data/claims.jsonl")

# File-class to extension map for autodetection.
_EXT_CLASS_MAP: Dict[str, str] = {
    ".md": "md",
    ".markdown": "md",
    ".html": "html",
    ".htm": "html",
    ".py": "py",
    ".js": "js",
    ".cjs": "cjs",
    ".mjs": "js",
    ".pl": "pl",
    ".rb": "rb",
    ".go": "go",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yml",
    ".txt": "txt",
    ".log": "log",
    ".jsonl": "jsonl",
    # Binary classes
    ".png": "binary",
    ".jpg": "binary",
    ".jpeg": "binary",
    ".gif": "binary",
    ".webp": "binary",
    ".pdf": "binary",
    ".zip": "binary",
    ".tar": "binary",
    ".gz": "binary",
    ".tgz": "binary",
    ".exe": "binary",
    ".dll": "binary",
    ".so": "binary",
    ".bin": "binary",
}

# Default K6 transaction journal target
_DEFAULT_K6_JOURNAL = Path(".claude") / "aep" / "transactions" / "aepfs_receipts.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_utf8_tolerant(buf: bytes) -> str:
    """Decode UTF-8 stripping BOM. Falls back to errors='replace' to keep
    parsing best-effort while preserving byte-identical projection elsewhere."""
    if buf.startswith(b"\xef\xbb\xbf"):
        buf = buf[3:]
    try:
        return buf.decode("utf-8")
    except UnicodeDecodeError:
        return buf.decode("utf-8", errors="replace")


def detect_file_class(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in _EXT_CLASS_MAP:
        return _EXT_CLASS_MAP[suf]
    # Compound suffixes (.tar.gz)
    if path.name.lower().endswith(".tar.gz") or path.name.lower().endswith(".tar.bz2"):
        return "binary"
    return "unknown"


def compute_state_hash(aepkg_dir: Path, canonical_files: List[str]) -> str:
    """Wave 4a-compatible: for each path in fixed order, hash path+sha256(bytes)."""
    h = hashlib.sha256()
    for rel in canonical_files:
        fp = aepkg_dir / rel
        if not fp.exists():
            continue
        bytes_sha = _sha256_bytes(fp.read_bytes())
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        h.update(bytes_sha.encode("ascii"))
        h.update(b"\n")
    return "sha256:" + h.hexdigest()


def _make_base_claim(claim_id: str, source_relpath: str, nowiso: str, **extra: Any) -> Dict[str, Any]:
    """Standard claim envelope used by every class extractor."""
    claim = {
        "id": claim_id,
        "type": "Claim",
        "source_relpath": source_relpath,
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "GO",
        "reliability": "STRONGLY_PLAUSIBLE",
        "scope": "CONTEXT_BOUND_PATTERN",
        "owner_agent": "forge",
        "review_tier": "R1",
        "status": "active",
        "created_at": nowiso,
        "converter_version": CONVERTER_VERSION,
    }
    claim.update(extra)
    return claim


# ---------------------------------------------------------------------------
# Per-class extractors
# ---------------------------------------------------------------------------
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H_HTML_RE = re.compile(r"<\s*(h[1-3])\b[^>]*>(.*?)<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?(def|class)\s+([A-Za-z_][\w]*)\s*[\(:]", re.MULTILINE)
_JS_FN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+([A-Za-z_][\w]*)"
    r"|class\s+([A-Za-z_][\w]*)"
    r"|const\s+([A-Za-z_][\w]*)\s*=\s*(?:async\s*)?\()",
    re.MULTILINE,
)
_PL_SUB_RE = re.compile(r"^\s*sub\s+([A-Za-z_][\w]*)", re.MULTILINE)
_RB_DEF_RE = re.compile(r"^\s*(def|class|module)\s+([A-Za-z_][\w:]*)", re.MULTILINE)
_GO_FN_RE = re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z_][\w]*)\s*\(", re.MULTILINE)
_TXT_NAME_LIKE_HEADING = re.compile(r"^([#=].+|.+\n[=\-]{3,}\s*)$", re.MULTILINE)


def extract_md_claims(text: str, source_relpath: str, nowiso: str) -> List[Dict[str, Any]]:
    lines = text.splitlines(keepends=False)
    positions: List[int] = []
    headings: List[str] = []
    for i, ln in enumerate(lines):
        m = _H2_RE.match(ln)
        if m:
            positions.append(i)
            headings.append(m.group(1).strip())
    claims: List[Dict[str, Any]] = []
    if not positions:
        # Floor: at least one claim per packet for indexability
        snippet = "\n".join(lines[:20]).strip()
        claims.append(_make_base_claim(
            "claim:md_0001", source_relpath, nowiso,
            heading="(no h2 headings detected)",
            body_markdown=snippet,
            section_index=0,
            start_line=1,
            end_line=min(20, len(lines)),
            extraction_method="md-no-h2-fallback",
            file_class="md",
        ))
        return claims
    for idx, start_i in enumerate(positions):
        end_i = positions[idx + 1] if (idx + 1) < len(positions) else len(lines)
        body_lines = lines[start_i + 1: end_i]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        claims.append(_make_base_claim(
            "claim:md_h2_" + format(idx + 1, "04d"),
            source_relpath, nowiso,
            heading=headings[idx],
            body_markdown="\n".join(body_lines),
            section_index=idx,
            start_line=start_i + 1,
            end_line=end_i,
            extraction_method="md-h2-line-scanner",
            file_class="md",
        ))
    return claims


def extract_html_claims(text: str, source_relpath: str, nowiso: str) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    idx = 0
    for m in _H_HTML_RE.finditer(text):
        heading_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not heading_text:
            continue
        # Approximate start_line by counting newlines before m.start()
        start_line = text.count("\n", 0, m.start()) + 1
        claims.append(_make_base_claim(
            "claim:html_h_" + format(idx + 1, "04d"),
            source_relpath, nowiso,
            heading=heading_text,
            tag=m.group(1).lower(),
            section_index=idx,
            start_line=start_line,
            extraction_method="html-h1-h3-tag-scanner",
            file_class="html",
        ))
        idx += 1
    if not claims:
        # Fallback single claim covering whole document
        body = re.sub(r"<[^>]+>", " ", text)
        body = re.sub(r"\s+", " ", body).strip()[:400]
        claims.append(_make_base_claim(
            "claim:html_0001", source_relpath, nowiso,
            heading="(no h1-h3 detected)",
            body_text=body,
            section_index=0,
            extraction_method="html-no-heading-fallback",
            file_class="html",
        ))
    return claims


def _extract_code_with_regex(
    pattern: re.Pattern,
    text: str,
    source_relpath: str,
    nowiso: str,
    file_class: str,
    extraction_label: str,
    name_group_picker: Callable[[Any], str],
) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    seen = set()
    for idx, m in enumerate(pattern.finditer(text)):
        name = name_group_picker(m)
        if not name:
            continue
        start_line = text.count("\n", 0, m.start()) + 1
        cid = "claim:" + file_class + "_" + format(len(claims) + 1, "04d")
        key = (name, start_line)
        if key in seen:
            continue
        seen.add(key)
        claims.append(_make_base_claim(
            cid, source_relpath, nowiso,
            symbol=name,
            start_line=start_line,
            extraction_method=extraction_label,
            file_class=file_class,
        ))
    if not claims:
        # Floor claim
        claims.append(_make_base_claim(
            "claim:" + file_class + "_0001",
            source_relpath, nowiso,
            symbol="(no symbols detected)",
            byte_count=len(text.encode("utf-8")),
            line_count=text.count("\n") + 1,
            extraction_method=extraction_label + "-fallback",
            file_class=file_class,
        ))
    return claims


def extract_py_claims(text, src, ts):
    return _extract_code_with_regex(
        _PY_DEF_RE, text, src, ts, "py", "py-def-class-scanner",
        lambda m: m.group(2),
    )


def extract_js_claims(text, src, ts):
    return _extract_code_with_regex(
        _JS_FN_RE, text, src, ts, "js", "js-function-class-scanner",
        lambda m: (m.group(1) or m.group(2) or m.group(3) or ""),
    )


def extract_cjs_claims(text, src, ts):
    # CommonJS uses the same regex as JS; class label differs
    return _extract_code_with_regex(
        _JS_FN_RE, text, src, ts, "cjs", "cjs-function-class-scanner",
        lambda m: (m.group(1) or m.group(2) or m.group(3) or ""),
    )


def extract_pl_claims(text, src, ts):
    return _extract_code_with_regex(
        _PL_SUB_RE, text, src, ts, "pl", "pl-sub-scanner",
        lambda m: m.group(1),
    )


def extract_rb_claims(text, src, ts):
    return _extract_code_with_regex(
        _RB_DEF_RE, text, src, ts, "rb", "rb-def-class-module-scanner",
        lambda m: m.group(2),
    )


def extract_go_claims(text, src, ts):
    return _extract_code_with_regex(
        _GO_FN_RE, text, src, ts, "go", "go-func-scanner",
        lambda m: m.group(1),
    )


def extract_json_claims(text: str, source_relpath: str, nowiso: str) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict):
        for idx, k in enumerate(obj.keys()):
            v = obj[k]
            value_kind = type(v).__name__
            preview = ""
            try:
                preview = _canonical_json(v)[:120]
            except Exception:
                preview = repr(v)[:120]
            claims.append(_make_base_claim(
                "claim:json_key_" + format(idx + 1, "04d"),
                source_relpath, nowiso,
                key=k,
                value_kind=value_kind,
                value_preview=preview,
                section_index=idx,
                extraction_method="json-top-level-key-scanner",
                file_class="json",
            ))
    elif isinstance(obj, list):
        claims.append(_make_base_claim(
            "claim:json_0001", source_relpath, nowiso,
            heading="(top-level json array)",
            element_count=len(obj),
            extraction_method="json-array-summary",
            file_class="json",
        ))
    else:
        claims.append(_make_base_claim(
            "claim:json_0001", source_relpath, nowiso,
            heading="(json parse failed or scalar)",
            byte_count=len(text.encode("utf-8")),
            extraction_method="json-fallback",
            file_class="json",
        ))
    if not claims:
        claims.append(_make_base_claim(
            "claim:json_0001", source_relpath, nowiso,
            heading="(empty json)",
            extraction_method="json-empty-fallback",
            file_class="json",
        ))
    return claims


def extract_yaml_claims(text: str, source_relpath: str, nowiso: str, file_class: str = "yaml") -> List[Dict[str, Any]]:
    r"""Top-level YAML keys without requiring PyYAML. Heuristic: lines matching
    ^[A-Za-z0-9_-]+:\s*  at column 0 are top-level keys."""
    claims: List[Dict[str, Any]] = []
    key_re = re.compile(r"^([A-Za-z_][\w\-\.]*)\s*:(?:\s|$)")
    idx = 0
    seen = set()
    for ln_no, line in enumerate(text.splitlines(), start=1):
        # Skip indented lines (not top-level)
        if line.startswith((" ", "\t", "-")):
            continue
        m = key_re.match(line)
        if not m:
            continue
        k = m.group(1)
        if k in seen:
            continue
        seen.add(k)
        claims.append(_make_base_claim(
            "claim:" + file_class + "_key_" + format(idx + 1, "04d"),
            source_relpath, nowiso,
            key=k,
            start_line=ln_no,
            section_index=idx,
            extraction_method=file_class + "-top-level-key-heuristic",
            file_class=file_class,
        ))
        idx += 1
    if not claims:
        claims.append(_make_base_claim(
            "claim:" + file_class + "_0001",
            source_relpath, nowiso,
            heading="(no top-level keys detected)",
            byte_count=len(text.encode("utf-8")),
            line_count=text.count("\n") + 1,
            extraction_method=file_class + "-fallback",
            file_class=file_class,
        ))
    return claims


def extract_text_claims(text: str, source_relpath: str, nowiso: str, file_class: str = "txt") -> List[Dict[str, Any]]:
    """Single attestation claim for txt/log/unknown files."""
    by = text.encode("utf-8") if isinstance(text, str) else text
    return [_make_base_claim(
        "claim:" + file_class + "_0001",
        source_relpath, nowiso,
        byte_count=len(by),
        line_count=(text.count("\n") + 1) if text else 0,
        text_sha256="sha256:" + _sha256_bytes(by),
        snippet=text[:200] if text else "",
        extraction_method=file_class + "-attestation",
        file_class=file_class,
    )]


def extract_jsonl_claims(text: str, source_relpath: str, nowiso: str) -> List[Dict[str, Any]]:
    """One claim summarizing the JSONL: row count + first/last row preview."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    first = lines[0][:200] if lines else ""
    last = lines[-1][:200] if lines else ""
    return [_make_base_claim(
        "claim:jsonl_0001", source_relpath, nowiso,
        row_count=len(lines),
        first_row_preview=first,
        last_row_preview=last,
        byte_count=len(text.encode("utf-8")),
        extraction_method="jsonl-row-summary",
        file_class="jsonl",
    )]


def extract_binary_claims(source_bytes: bytes, source_relpath: str, nowiso: str) -> List[Dict[str, Any]]:
    return [_make_base_claim(
        "claim:binary_0001", source_relpath, nowiso,
        byte_count=len(source_bytes),
        source_sha256="sha256:" + _sha256_bytes(source_bytes),
        extraction_method="binary-hash-attestation",
        file_class="binary",
        note="binary payload not byte-copied into views/; sha256-attest only",
    )]


# Dispatch table (text/code/struct -> text-extractor + extension to use; binary handled separately)
_TEXT_DISPATCH: Dict[str, Tuple[Callable, str]] = {
    "md":    (extract_md_claims,   ".md"),
    "html":  (extract_html_claims, ".html"),
    "py":    (extract_py_claims,   ".py"),
    "js":    (extract_js_claims,   ".js"),
    "cjs":   (extract_cjs_claims,  ".cjs"),
    "pl":    (extract_pl_claims,   ".pl"),
    "rb":    (extract_rb_claims,   ".rb"),
    "go":    (extract_go_claims,   ".go"),
    "json":  (extract_json_claims, ".json"),
    "yaml":  (lambda t, s, ts: extract_yaml_claims(t, s, ts, "yaml"), ".yaml"),
    "yml":   (lambda t, s, ts: extract_yaml_claims(t, s, ts, "yml"),  ".yml"),
    "txt":   (lambda t, s, ts: extract_text_claims(t, s, ts, "txt"),  ".txt"),
    "log":   (lambda t, s, ts: extract_text_claims(t, s, ts, "log"),  ".log"),
    "jsonl": (extract_jsonl_claims, ".jsonl"),
}


# ---------------------------------------------------------------------------
# Single-file convert
# ---------------------------------------------------------------------------
def _emit_k6_row(journal_path: Path, row: Dict[str, Any]) -> None:
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with journal_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(_canonical_json(row) + "\n")
    except Exception:
        # Best-effort journal emission; conversion success must not depend on it
        pass


def convert_one(
    source_path: Path,
    output_dir: Path,
    file_class: str,
    dry_run: bool,
    wave_id: Optional[str],
    repo_root: Path,
    k6_journal: Optional[Path],
) -> Dict[str, Any]:
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError("source not found: " + str(source_path))

    source_bytes = source_path.read_bytes()
    source_sha = _sha256_bytes(source_bytes)
    nowiso = _utc_now_iso()

    # Compute repo-relative source path for claims + meta
    try:
        source_relpath = str(source_path.resolve().relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        source_relpath = source_path.name

    # Decide source view path + canonical files order
    if file_class == "binary":
        source_view_rel = "views/source_hash.txt"
        canonical_files = list(_BASE_CANONICAL) + [source_view_rel]
        claims = extract_binary_claims(source_bytes, source_relpath, nowiso)
        source_view_bytes = ("sha256:" + source_sha + "\n").encode("utf-8")
    elif file_class in _TEXT_DISPATCH:
        extractor, ext = _TEXT_DISPATCH[file_class]
        source_view_rel = "views/source" + ext
        canonical_files = list(_BASE_CANONICAL) + [source_view_rel]
        text = _decode_utf8_tolerant(source_bytes)
        claims = extractor(text, source_relpath, nowiso)
        source_view_bytes = source_bytes  # byte-identical projection
    elif file_class == "unknown":
        # Fallback to text class with WARN
        sys.stderr.write(
            "[universal_aepify WARN] unknown file class for " + str(source_path)
            + " -- falling back to text/attestation claim\n"
        )
        source_view_rel = "views/source" + source_path.suffix
        canonical_files = list(_BASE_CANONICAL) + [source_view_rel]
        text = _decode_utf8_tolerant(source_bytes)
        claims = extract_text_claims(text, source_relpath, nowiso, "unknown")
        source_view_bytes = source_bytes
    else:
        raise ValueError("unsupported file_class: " + file_class)

    if dry_run:
        return {
            "mode": "dry-run",
            "source_path": str(source_path).replace("\\", "/"),
            "output_dir_planned": str(output_dir).replace("\\", "/"),
            "file_class": file_class,
            "source_sha256": "sha256:" + source_sha,
            "source_bytes_count": len(source_bytes),
            "claim_count": len(claims),
            "canonical_files_planned": canonical_files + ["integrity.json"],
            "first_claim_id": claims[0]["id"] if claims else None,
        }

    # Write canonical files in deterministic order
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data").mkdir(parents=True, exist_ok=True)
    (output_dir / "views").mkdir(parents=True, exist_ok=True)

    # 1. source view (byte-identical OR hash-attest line for binary)
    view_path = output_dir / source_view_rel
    view_path.write_bytes(source_view_bytes)

    # 2. data/claims.jsonl
    claims_path = output_dir / "data" / "claims.jsonl"
    with claims_path.open("w", encoding="utf-8", newline="\n") as f:
        for c in claims:
            f.write(_canonical_json(c) + "\n")

    # 3. meta.json
    packet_id = "aepkg:" + source_path.stem.replace(".", "-").replace(" ", "-")
    meta = {
        "aep_version": AEP_VERSION,
        "packet_id": packet_id,
        "schema_version": SCHEMA_VERSION,
        "converter_version": CONVERTER_VERSION,
        "file_class": file_class,
        "canonical_path": source_relpath,
        "source_path": source_relpath,
        "source_sha256": "sha256:" + source_sha,
        "source_bytes_count": len(source_bytes),
        "claim_count": len(claims),
        "created_at": nowiso,
        "created_by": "forge:" + CONVERTER_VERSION,
        "canonical_files": canonical_files + ["integrity.json"],
        "canonical_files_order_hash_input": canonical_files,
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "GO",
        "wave_id": wave_id or "unspecified",
        "composes_with": [
            "tools/spec_md_to_aepkg.py",
            "tools/cleanup_failed_aepkg_wave.py",
            "doctrine/22-html-and-md-native-artifacts",
            "doctrine/41-hash-chained-receipt-ledger",
            "doctrine/73-six-sublaws-of-honest-framing",
        ],
        "extension_notes": (
            "binary class is hash-attestation only (views/source_hash.txt); "
            "text/code/struct classes are byte-identical projections. "
            "Per sec73.6 honest framing this distinction is load-bearing."
        ),
    }
    with (output_dir / "meta.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")

    # 4. integrity.json
    state_hash = compute_state_hash(output_dir, canonical_files)
    integrity = {
        "algorithm": "sha256-of-(path-newline-sha256-newline)-concat-over-canonical-files-order",
        "canonical_files_order": canonical_files,
        "state_hash": state_hash,
        "source_sha256": "sha256:" + source_sha,
        "file_class": file_class,
        "computed_at": nowiso,
        "converter_version": CONVERTER_VERSION,
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "GO",
    }
    with (output_dir / "integrity.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(integrity, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")

    # K6 transaction journal row (best-effort)
    if k6_journal is not None:
        _emit_k6_row(k6_journal, {
            "ts": nowiso,
            "actor": "universal_aepify.py",
            "phase": "conversion-success",
            "wave_id": wave_id or "unspecified",
            "target_path": str(output_dir).replace("\\", "/"),
            "source_path": source_relpath,
            "file_class": file_class,
            "state_hash": state_hash,
            "claim_count": len(claims),
            "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
            "truth_tag_axis_b": "GO",
        })

    return {
        "mode": "commit",
        "source_path": str(source_path).replace("\\", "/"),
        "output_dir": str(output_dir).replace("\\", "/"),
        "file_class": file_class,
        "source_sha256": "sha256:" + source_sha,
        "source_bytes_count": len(source_bytes),
        "claim_count": len(claims),
        "state_hash": state_hash,
        "canonical_files": canonical_files + ["integrity.json"],
    }


# ---------------------------------------------------------------------------
# Glob expansion + batch driver
# ---------------------------------------------------------------------------
def _expand_inputs(input_arg: str) -> List[Path]:
    """Resolve <input> as either a single file, a directory (recursive *), or a glob."""
    p = Path(input_arg)
    if p.exists() and p.is_file():
        return [p.resolve()]
    if p.exists() and p.is_dir():
        return sorted([fp.resolve() for fp in p.rglob("*") if fp.is_file()])
    # Glob path
    matches = sorted(_glob.glob(input_arg, recursive=True))
    return [Path(m).resolve() for m in matches if Path(m).is_file()]


def _output_dir_for(source: Path, out_root: Optional[Path]) -> Path:
    """Default: sibling .aepkg/. With --out-root, repo-relative mirror under it."""
    stem = source.stem if source.suffix else source.name
    aepkg_name = stem + ".aepkg"
    if out_root is None:
        return source.parent / aepkg_name
    return (out_root / aepkg_name).resolve()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="AEP v1.5 LTS Wave 6: universal file-class to .aepkg/ converter"
    )
    parser.add_argument("input", help="Input path (file/dir/glob)")
    parser.add_argument("--out-root", type=Path, default=None, help="Output root dir; default sibling")
    parser.add_argument("--dry-run", action="store_true", help="Preview only; no FS mutation")
    parser.add_argument("--force", action="store_true", help="Overwrite existing .aepkg/ dirs")
    parser.add_argument(
        "--file-class",
        default="auto",
        choices=sorted(set(["auto", "binary", "unknown"] + list(_TEXT_DISPATCH.keys()))),
    )
    parser.add_argument("--max-files", type=int, default=0, help="Cap on number of files (0 = no cap)")
    parser.add_argument("--wave-id", default=None, help="Wave identifier embedded in meta.json + K6 row")
    parser.add_argument("--k6-journal", type=Path, default=_DEFAULT_K6_JOURNAL,
                        help="K6 transaction journal path (default .claude/aep/transactions/aepfs_receipts.jsonl)")
    parser.add_argument("--no-k6", action="store_true", help="Disable K6 journal emission entirely")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable summary to stdout")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    sources = _expand_inputs(args.input)
    if not sources:
        print("ERROR: no input files matched: " + args.input, file=sys.stderr)
        return 1

    if args.max_files > 0:
        sources = sources[: args.max_files]

    k6_journal: Optional[Path] = None if args.no_k6 else args.k6_journal

    overall: List[Dict[str, Any]] = []
    error_count = 0
    unknown_class_count = 0

    for src in sources:
        if args.file_class == "auto":
            fc = detect_file_class(src)
        else:
            fc = args.file_class

        if fc == "unknown" and args.file_class == "auto":
            unknown_class_count += 1
            # WARN already emitted by convert_one when fallback fires

        out_dir = _output_dir_for(src, args.out_root)

        if not args.dry_run and out_dir.exists():
            if args.force:
                import shutil
                shutil.rmtree(out_dir)
            else:
                overall.append({
                    "source_path": str(src).replace("\\", "/"),
                    "error": "output-exists-no-force",
                    "output_dir": str(out_dir).replace("\\", "/"),
                })
                error_count += 1
                continue

        try:
            res = convert_one(
                src,
                out_dir,
                fc,
                dry_run=args.dry_run,
                wave_id=args.wave_id,
                repo_root=repo_root,
                k6_journal=k6_journal,
            )
        except Exception as e:
            overall.append({
                "source_path": str(src).replace("\\", "/"),
                "error": type(e).__name__ + ": " + str(e),
            })
            error_count += 1
            continue

        overall.append(res)

    summary = {
        "converter_version": CONVERTER_VERSION,
        "input": args.input,
        "file_class_arg": args.file_class,
        "wave_id": args.wave_id,
        "total_inputs": len(sources),
        "success_count": sum(1 for r in overall if "error" not in r),
        "error_count": error_count,
        "unknown_class_warns": unknown_class_count,
        "dry_run": args.dry_run,
        "per_file": overall,
    }

    if args.json:
        print(_canonical_json(summary))
    else:
        verb = "[DRY-RUN] would convert" if args.dry_run else "converted"
        print("[universal_aepify] " + verb + " "
              + str(summary["success_count"]) + " of " + str(summary["total_inputs"]) + " files")
        if summary["error_count"]:
            print("  errors: " + str(summary["error_count"]), file=sys.stderr)
        for r in overall[:10]:
            if "error" in r:
                print("  ERR " + r["source_path"] + " :: " + r["error"], file=sys.stderr)
            else:
                tag = r.get("file_class", "?")
                claims = r.get("claim_count", 0)
                print("  OK  [" + tag + "] " + r["source_path"] + " -> claims=" + str(claims))

    if error_count and summary["success_count"] == 0:
        return 2
    if error_count:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
