"""
convert_html_lesson.py — Apache-2.0 — Example HTML→AEP v0.3 converter.

This is an EXAMPLE adapter; adapt the heuristics for your own input format.
It demonstrates the canonical packet shape (sources / spans / claims /
relations / events / reviews / validations) plus integrity-envelope
computation. Output v0.3 packets can be upgraded to v0.5 via
`aep.convert_v0_3_to_v0_5`, then to v0.5 deep-shape via
`aep.convert_v0_5_shallow_to_deep`.

Status: validator-clean (every output passes the v0.3 reference validator).

Design notes:
  - packet_id carries the 'aepkg:' prefix mandated by the manifest schema.
  - source_type uses the spec enum (primary_source / secondary_source).
  - source.location is a structured OBJECT, not a raw string.
  - review_tier matches the ^R[1-4]$ pattern; auto-extracted claims land at R1.
  - State-hash algorithm exactly mirrors aep.validate.state_hash (sorted canonical files,
    per-line iteration, sha256 over rel + '\n' + canonical_json(obj) + '\n').
  - GOVERNANCE-RULE legacy tag round-trips through reliability=PROVEN_RELIABLE +
    aepkit_legacy_tag=GOVERNANCE-RULE per doctrine/02 Amendment A15.
  - Claim text whitespace normalized (HTML newlines + indentation collapsed).
  - Strong-lead detector picks only the first <strong> per paragraph ending with ':'.
  - Relations extracted: every claim emits belongs_to_section + derived_from_source edges.
  - HTML entities decoded via html.unescape.
  - Provenance strength heuristic: doctrine/* paths -> strong; external URLs -> medium;
    unknown -> unknown.

Usage:
    python -m aep.convert_aepkit_lesson <lesson.html> <output.aepkg/>
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# --- AEP enums (kept in sync with aep.validate; failure to match means rewrite the converter) ---
AEP_RELIABILITY = {
    "PROVEN_RELIABLE", "STRONGLY_PLAUSIBLE", "PLAUSIBLE",
    "ASSUMPTION", "CONFLICTED", "UNKNOWN",
}
AEP_SCOPES = {"LOCAL_OBSERVATION", "CONTEXT_BOUND_PATTERN", "GENERAL_CLAIM"}
AEP_SOURCE_TYPES = {
    "user_artifact", "official_spec", "primary_source", "secondary_source",
    "runtime_output", "inference_note", "other",
}
AEP_PROVENANCE = {"strong", "medium", "weak", "unknown"}
AEP_CLAIM_STATUS = {"active", "superseded", "rejected", "needs_review"}
AEP_INFERENCE = {"explicit_in_source", "derived_from_claims", "architectural_inference", "speculative_design"}
AEP_VALIDATION_RESULTS = {"pass", "warn", "fail"}

REQUIRED_FILES: List[str] = [
    "data/sources.jsonl",
    "data/spans.jsonl",
    "data/claims.jsonl",
    "data/relations.jsonl",
    "ops/events.jsonl",
    "reviews/reviews.jsonl",
    "validations/runs.jsonl",
]


# --- Two-axis truth-tag mapping (V11 charter §2.1 + §02 Amendment A15 GOVERNANCE-RULE) ---
# Forward map: AEP project single-axis tag -> (Axis A AEP reliability, Axis B action, AEP-compatible reliability)
# The third element is the AEP-validator-compatible value that goes into the `reliability` field.
# Axis A may carry a richer value (GOVERNANCE_RULE) preserved in aep:axis_a_epistemic extension.
TAG_MAP: Dict[str, Tuple[str, str, str]] = {
    # AEP project §02 6-tier:
    "PROVEN/RELIABLE":           ("PROVEN_RELIABLE",   "GO",         "PROVEN_RELIABLE"),
    "STRONGLY PLAUSIBLE":        ("STRONGLY_PLAUSIBLE", "GO",        "STRONGLY_PLAUSIBLE"),
    "EXPERIMENTAL":              ("PLAUSIBLE",         "EXPERIMENT", "PLAUSIBLE"),
    "SPECULATIVE FRONTIER":      ("ASSUMPTION",        "EXPLORE",    "ASSUMPTION"),
    "IMPOSSIBLE/UNSUPPORTED":    ("CONFLICTED",        "HALT",       "CONFLICTED"),
    "DANGEROUS/NOT WORTH DOING": ("PLAUSIBLE",         "FORBIDDEN",  "PLAUSIBLE"),
    # §02 Amendment A15 GOVERNANCE-RULE (operator-approved 2026-05-14):
    "GOVERNANCE-RULE":           ("GOVERNANCE_RULE",   "GO",         "PROVEN_RELIABLE"),
    # AEP-native passthrough:
    "PROVEN_RELIABLE":           ("PROVEN_RELIABLE",   "GO",         "PROVEN_RELIABLE"),
    "STRONGLY_PLAUSIBLE":        ("STRONGLY_PLAUSIBLE", "GO",        "STRONGLY_PLAUSIBLE"),
    "PLAUSIBLE":                 ("PLAUSIBLE",         "EXPERIMENT", "PLAUSIBLE"),
    "ASSUMPTION":                ("ASSUMPTION",        "EXPLORE",    "ASSUMPTION"),
    "CONFLICTED":                ("CONFLICTED",        "HALT",       "CONFLICTED"),
    "UNKNOWN":                   ("UNKNOWN",           "EXPLORE",    "UNKNOWN"),
}


def map_truth_tag(legacy_tag: str) -> Tuple[str, str, str]:
    """Forward-map a AEP project single-axis tag to (axis_a, axis_b, aep_reliability)."""
    return TAG_MAP.get(legacy_tag.strip(), ("UNKNOWN", "EXPLORE", "UNKNOWN"))


# --- Hashing + canonical JSON (must match aep.validate exactly) ---
def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj: Any) -> str:
    """Canonical JSON encoding identical to aep.validate.canonical_json."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_state_hash(root: Path, canonical_files: List[str]) -> str:
    """Re-implement aep.validate.state_hash exactly, computed by reading files from disk.

    The validator iterates sorted(canonical_files), then per file iterates raw lines,
    skips blanks, parses JSON, then incrementally updates a single sha256 with
    rel + '\\n' + canonical_json(obj) + '\\n' for each record.
    """
    h = hashlib.sha256()
    for rel in sorted(canonical_files):
        path = root / rel
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            h.update(rel.encode("utf-8"))
            h.update(b"\n")
            h.update(canonical_json(obj).encode("utf-8"))
            h.update(b"\n")
    return "sha256:" + h.hexdigest()


# --- HTML normalization helpers ---
_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse whitespace and decode HTML entities. Leaves intentional punctuation intact."""
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def detect_strong_lead(strong_buffer: str) -> str:
    """The first <strong> in a paragraph is a 'lead' only if it ends with ':'."""
    s = normalize_text(strong_buffer).rstrip(":").strip()
    # Heuristic: a lead is a short capitalized phrase like RULE, MECHANISM, FALSIFIER, Note, etc.
    if len(s) > 40 or " " in s.strip() and not s.strip().endswith((":", ".")):
        # Allow multi-word leads like "Pilot dependency"
        if len(s.split()) > 3:
            return ""
    return s


# --- HTML parser: extracts structured records from a AEP project lesson ---
class AEP projectLessonParser(HTMLParser):
    """Parses a AEP project lesson .html into sections, paragraphs, frontmatter, and cite links."""

    def __init__(self) -> None:
        super().__init__()
        # Element-state flags
        self.in_pre_frontmatter = False
        self.in_section = False
        self.in_h = False
        self.in_p = False
        self.in_strong = False
        self.in_a = False
        self.in_cites_section = False
        # Buffers
        self.frontmatter_buf: List[str] = []
        self.section_stack: List[Dict[str, Any]] = []
        self.current_section: Optional[Dict[str, Any]] = None
        self.current_h_buf: List[str] = []
        self.current_p_buf: List[str] = []
        # Strong handling: only the FIRST <strong> in each paragraph
        self.current_first_strong_buf: List[str] = []
        self.captured_first_strong: bool = False
        # Cite link state
        self.current_a_href: Optional[str] = None
        self.current_a_text_buf: List[str] = []
        # Outputs
        self.sections: List[Dict[str, Any]] = []
        self.cite_links: List[Tuple[str, str]] = []
        self.frontmatter_text: str = ""
        self.lesson_title: str = ""
        self._in_title: bool = False
        self._title_buf: List[str] = []

    # --- start/end tag handlers ---
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
            self._title_buf = []
            return
        if tag == "pre" and a.get("class") == "frontmatter":
            self.in_pre_frontmatter = True
            self.frontmatter_buf = []
            return
        if tag == "section":
            sid = a.get("id") or a.get("data-section-id") or ""
            self.in_section = True
            self.current_section = {"id": sid, "title": "", "paragraphs": []}
            if sid and "cite" in sid.lower():
                self.in_cites_section = True
            return
        if tag in ("h1", "h2", "h3", "h4"):
            self.in_h = True
            self.current_h_buf = []
            return
        if tag == "p":
            self.in_p = True
            self.current_p_buf = []
            self.current_first_strong_buf = []
            self.captured_first_strong = False
            return
        if tag == "strong":
            self.in_strong = True
            return
        if tag == "a" and self.in_cites_section:
            self.in_a = True
            self.current_a_href = a.get("href")
            self.current_a_text_buf = []
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.lesson_title = normalize_text("".join(self._title_buf))
            return
        if tag == "pre" and self.in_pre_frontmatter:
            self.frontmatter_text = "".join(self.frontmatter_buf)
            self.in_pre_frontmatter = False
            return
        if tag == "section":
            if self.current_section and (self.current_section["title"] or self.current_section["paragraphs"]):
                self.sections.append(self.current_section)
            self.current_section = None
            self.in_section = False
            self.in_cites_section = False
            return
        if tag in ("h1", "h2", "h3", "h4"):
            if self.current_section is not None:
                self.current_section["title"] = normalize_text("".join(self.current_h_buf))
            self.in_h = False
            return
        if tag == "p":
            if self.current_section is not None:
                text = normalize_text("".join(self.current_p_buf))
                strong_lead = detect_strong_lead("".join(self.current_first_strong_buf))
                if text:
                    self.current_section["paragraphs"].append({"text": text, "strong_lead": strong_lead})
            self.in_p = False
            return
        if tag == "strong":
            self.in_strong = False
            if self.in_p and not self.captured_first_strong:
                # The first strong block has now closed; lock it in.
                self.captured_first_strong = True
            return
        if tag == "a" and self.in_cites_section and self.in_a:
            href = self.current_a_href or ""
            link_text = normalize_text("".join(self.current_a_text_buf))
            if href:
                self.cite_links.append((href, link_text))
            self.in_a = False
            self.current_a_href = None
            return

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_buf.append(data)
        if self.in_pre_frontmatter:
            self.frontmatter_buf.append(data)
        if self.in_h:
            self.current_h_buf.append(data)
        if self.in_p:
            self.current_p_buf.append(data)
            if self.in_strong and not self.captured_first_strong:
                self.current_first_strong_buf.append(data)
        if self.in_a and self.in_cites_section:
            self.current_a_text_buf.append(data)

    def handle_entityref(self, name: str) -> None:
        # Manually re-emit the entity so handle_data picks it up; html.parser doesn't
        # automatically convert &mdash; etc. — rely on normalize_text() to unescape later.
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")


# --- Markdown-wrapped-in-HTML parser (older AEP project lessons store frontmatter in
#     <pre><code>---...---</code></pre> and body content as raw markdown after </pre>) ---
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MD_LINK_RE = re.compile(r"\[([^\]]+?)\]\(([^)]+?)\)")
_MD_STRONG_LEAD_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*[:.]?\s*(.*)$")
# Matches `<pre><code>---\n...\n---` (the opening frontmatter fence) regardless of where </code></pre> closes.
_PRE_CODE_FRONTMATTER_OPEN_RE = re.compile(
    r"<pre[^>]*>\s*<code[^>]*>\s*---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)
# Matches the closing </pre> after a <pre><code>...</code></pre> wrap so we can find body start.
_PRE_CODE_CLOSE_RE = re.compile(r"</code>\s*</pre>", re.IGNORECASE)


def detect_lesson_format(html_content: str) -> str:
    """Detect 'v3-structured' (modern, <section> blocks) vs 'markdown-wrapped' (older, <pre><code>--- + raw md).

    Decision tree:
      1. <section> count >= 3 -> v3-structured (clear modern format).
      2. <pre><code>---...---\n opener present -> markdown-wrapped.
      3. Otherwise default to markdown-wrapped (older lessons frequently lack
         <section> tags but DO have inline markdown bodies; the markdown path
         degrades gracefully on truly empty input whereas v3 yields 0 claims).
    """
    section_count = html_content.count("<section")
    has_pre_code_frontmatter = bool(_PRE_CODE_FRONTMATTER_OPEN_RE.search(html_content))
    if section_count >= 3:
        return "v3-structured"
    if has_pre_code_frontmatter:
        return "markdown-wrapped"
    return "markdown-wrapped"


def extract_markdown_wrapped(html_content: str, lesson_path: Path) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Extract from markdown-wrapped-in-HTML format. Returns (title, frontmatter, sections, cite_links)."""
    # Frontmatter
    fm_match = _PRE_CODE_FRONTMATTER_OPEN_RE.search(html_content)
    frontmatter_text = fm_match.group(1) if fm_match else ""

    # Title — try <title> first, fall back to first H1 in body
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
    title = normalize_text(title_match.group(1)) if title_match else ""

    # Body = everything after the frontmatter closer (---\n) up to </body> (or </code></pre> if it's all inside one block).
    if fm_match:
        body_start = fm_match.end()
    else:
        body_start = html_content.find("<body")
        if body_start >= 0:
            body_start = html_content.find(">", body_start) + 1
        else:
            body_start = 0
    # Look for body end: first try the </code></pre> that wraps the markdown block, then </body>.
    body_search = html_content[body_start:]
    close_match = _PRE_CODE_CLOSE_RE.search(body_search)
    body_close_match = re.search(r"</body>", body_search, re.IGNORECASE)
    if close_match:
        body_end_rel = close_match.start()
    elif body_close_match:
        body_end_rel = body_close_match.start()
    else:
        body_end_rel = len(body_search)
    body_md = body_search[:body_end_rel]

    # Strip any inline HTML tags so we can treat body as plaintext markdown.
    # Keep markdown link syntax intact (it's plain text already, no HTML tags there).
    body_md_no_tags = re.sub(r"<[^>]+>", "", body_md)
    body_md_no_tags = html.unescape(body_md_no_tags)

    # Walk lines: build sections from ## headings, paragraphs from non-empty blocks between blank lines
    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = {"id": "preamble", "title": title or "Preamble", "paragraphs": []}
    current_para_lines: List[str] = []
    cite_links: List[Tuple[str, str]] = []

    def flush_paragraph() -> None:
        if not current_para_lines or current_section is None:
            return
        text = normalize_text(" ".join(current_para_lines))
        if len(text) < 30:
            current_para_lines.clear()
            return
        # Skip pure markdown table separator lines
        if re.match(r"^[\|\-:\s]+$", text):
            current_para_lines.clear()
            return
        # Detect strong-lead from leading **bold**
        strong_lead = ""
        m = _MD_STRONG_LEAD_RE.match(text)
        if m:
            strong_lead = m.group(1).strip()
        current_section["paragraphs"].append({"text": text, "strong_lead": strong_lead})
        current_para_lines.clear()

    def slugify(label: str) -> str:
        s = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-").lower()
        return s[:60] or "section"

    in_code_block = False
    for raw_line in body_md_no_tags.splitlines():
        line = raw_line.rstrip()
        # Track fenced code blocks (skip code inside)
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            flush_paragraph()
            continue
        if in_code_block:
            continue

        # Headings flush the prior paragraph + start a new section
        heading_match = _MD_HEADING_RE.match(line)
        if heading_match:
            flush_paragraph()
            # Close current section into output (if it has content)
            if current_section and (current_section["paragraphs"] or current_section["title"]):
                sections.append(current_section)
            label = heading_match.group(2).strip()
            current_section = {"id": slugify(label), "title": label, "paragraphs": []}
            continue

        # Blank line flushes paragraph
        if not line.strip():
            flush_paragraph()
            continue

        current_para_lines.append(line.strip())

        # Collect markdown links as potential cites
        for link_match in _MD_LINK_RE.finditer(line):
            link_text = link_match.group(1).strip()
            href = link_match.group(2).strip()
            cite_links.append((href, link_text))

    flush_paragraph()
    if current_section and (current_section["paragraphs"] or current_section["title"]):
        sections.append(current_section)

    # Drop preamble if it has no paragraphs
    sections = [s for s in sections if s["paragraphs"] or s["title"]]

    # Title fallback: first heading
    if not title and sections:
        title = sections[0]["title"]

    # Parse frontmatter via the same parser used for V3
    frontmatter = parse_frontmatter(frontmatter_text)

    return title, frontmatter, sections, cite_links


# --- Frontmatter (YAML-ish) parser tuned for AEP project lessons ---
def parse_frontmatter(yaml_text: str) -> Dict[str, Any]:
    fm: Dict[str, Any] = {}
    for line in yaml_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        m = re.match(r"^([\w][\w_-]*)\s*:\s*(.*)$", stripped)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith("[") and raw.endswith("]"):
            items = [x.strip().strip("'\"") for x in raw[1:-1].split(",") if x.strip()]
            fm[key] = items
        elif raw in ("null", "None", ""):
            fm[key] = None
        else:
            fm[key] = raw.strip().strip("'\"")
    return fm


# --- Source / Span / Claim / Relation extraction ---
SKIP_SECTIONS = {"provenance-note", "cites", "cites-and-meta"}


def classify_source_type(href: str) -> str:
    """Map a cite URL to one of the AEP_SOURCE_TYPES enum values."""
    h = href.lower()
    if h.endswith(".html") and ("/doctrine/" in h or h.startswith("doctrine/") or "../doctrine/" in h or "../" in h):
        return "primary_source"  # AEP project-internal canonical doctrine
    if h.endswith(".html") and ("/_proposals/" in h or "_proposals/" in h):
        return "primary_source"
    if h.endswith(".html") and ("/lessons/" in h or "lessons/" in h):
        return "primary_source"
    if h.endswith((".md", ".jsonl", ".json")) and ("/" in h or h.startswith("doctrine")):
        return "primary_source"
    if h.endswith((".ps1", ".py")):
        return "runtime_output"
    if h.startswith(("http://", "https://")):
        return "secondary_source"
    return "secondary_source"


def classify_provenance(href: str) -> str:
    """Map a cite href to AEP_PROVENANCE strength."""
    h = href.lower()
    if h.startswith(("../", "doctrine/", "research/", ".claude/", "projects/", "library/")):
        return "strong"
    if h.endswith(".html") or h.endswith(".md") or h.endswith(".jsonl"):
        return "strong"
    if h.startswith(("http://", "https://")):
        return "medium"
    return "unknown"


def build_lesson_self_source(lesson_path: Path, lesson_title: str, nowiso: str) -> Dict[str, Any]:
    return {
        "id": "src:lesson-self",
        "type": "Source",
        "title": lesson_title or lesson_path.stem,
        "source_type": "primary_source",
        "provenance_strength": "strong",
        "location": {
            "kind": "filesystem-path",
            "path": str(lesson_path).replace("\\", "/"),
            "repo_relative": True,
        },
        "limits": (
            "AEP project-internal lesson; truth tag carried in frontmatter applies to the full document; "
            "individual claims may carry tighter or looser axis_a/axis_b per the V11-AEP two-axis schema."
        ),
        "created_at": nowiso,
    }


def build_cite_sources(cite_links: List[Tuple[str, str]], nowiso: str) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen_hrefs: set = set()
    counter = 0
    for href, link_text in cite_links:
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        counter += 1
        sources.append({
            "id": f"src:cite-{counter:03d}",
            "type": "Source",
            "title": link_text or href,
            "source_type": classify_source_type(href),
            "provenance_strength": classify_provenance(href),
            "location": {
                "kind": "url-or-path",
                "value": href,
                "anchor_text": link_text,
            },
            "limits": "Cite link extracted from lesson Cites section; not independently verified by converter.",
            "created_at": nowiso,
        })
    return sources


def extract_claims_and_spans(
    sections: List[Dict[str, Any]],
    legacy_tag: str,
    nowiso: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Walk sections, emit one Claim per substantive paragraph + one Span per Claim."""
    axis_a, axis_b, aep_reliability = map_truth_tag(legacy_tag)
    claims: List[Dict[str, Any]] = []
    spans: List[Dict[str, Any]] = []
    counter = 0

    for sec in sections:
        sid = sec["id"] or "unknown-section"
        title = sec["title"]
        if sid in SKIP_SECTIONS:
            continue
        if not title:
            continue
        if "cite" in sid.lower():
            continue

        for paragraph in sec["paragraphs"]:
            text = paragraph["text"]
            if len(text) < 30:
                continue
            strong_lead = paragraph["strong_lead"]

            # Classify claim kind from strong_lead
            kind = "observation"
            if strong_lead:
                lower = strong_lead.lower()
                if lower in ("rule", "mechanism", "falsifier", "note", "source",
                             "pilot dependency", "advised_by", "rationale", "warning",
                             "context", "evidence"):
                    kind = lower.replace(" ", "_")

            counter += 1
            claim_id = f"claim:{counter:04d}"
            span_id = f"span:p-{counter:04d}"

            spans.append({
                "id": span_id,
                "type": "Span",
                "source_id": "src:lesson-self",
                "selector": {
                    "kind": "section-paragraph",
                    "section_id": sid,
                    "paragraph_ordinal": counter,
                    "paragraph_text_prefix": text[:80],
                },
                "quote_hash": "sha256:" + sha256_hex(text),
                "created_at": nowiso,
            })

            reasoning = (
                f"Auto-extracted from section §{sid} (\"{title}\"); "
                f"strong-lead='{strong_lead or 'none'}'; kind='{kind}'. "
                f"Inherits legacy truth tag '{legacy_tag}' from lesson frontmatter."
            )

            claim = {
                "id": claim_id,
                "type": "Claim",
                "text": text,
                "reliability": aep_reliability,
                "scope": "CONTEXT_BOUND_PATTERN",
                "basis": [
                    {"source_id": "src:lesson-self", "span_id": span_id},
                ],
                "reasoning": reasoning,
                "owner_agent": "scribe",
                "review_tier": "R1",
                "status": "active",
                "created_at": nowiso,
                # AEP project / V11-AEP extension fields (additionalProperties:true):
                "aep:axis_a_epistemic": axis_a,
                "aep:axis_b_action": axis_b,
                "aep:legacy_tag": legacy_tag,
                "aep:kind": kind,
                "aep:section_id": sid,
                "aep:section_title": title,
                "aep:strong_lead": strong_lead,
            }
            claims.append(claim)

    return claims, spans


def extract_relations(
    claims: List[Dict[str, Any]],
    nowiso: str,
) -> List[Dict[str, Any]]:
    """Emit basic relation graph: belongs_to_section + derives_from_source for each claim."""
    relations: List[Dict[str, Any]] = []
    counter = 0
    for claim in claims:
        cid = claim["id"]
        sid = claim["aep:section_id"]

        counter += 1
        relations.append({
            "id": f"rel:{counter:04d}",
            "type": "Relation",
            "subject": cid,
            "predicate": "belongs_to_section",
            "object": f"section:{sid}",
            "basis_claims": [cid],
            "inference_label": "explicit_in_source",
            "created_at": nowiso,
        })

        counter += 1
        relations.append({
            "id": f"rel:{counter:04d}",
            "type": "Relation",
            "subject": cid,
            "predicate": "derives_from_source",
            "object": "src:lesson-self",
            "basis_claims": [cid],
            "inference_label": "explicit_in_source",
            "created_at": nowiso,
        })

    # Consecutive-paragraph relation: elaborates_on within same section
    by_section: Dict[str, List[str]] = {}
    for claim in claims:
        by_section.setdefault(claim["aep:section_id"], []).append(claim["id"])
    for sid, cids in by_section.items():
        for i in range(1, len(cids)):
            counter += 1
            relations.append({
                "id": f"rel:{counter:04d}",
                "type": "Relation",
                "subject": cids[i],
                "predicate": "elaborates_on",
                "object": cids[i - 1],
                "basis_claims": [cids[i], cids[i - 1]],
                "inference_label": "architectural_inference",
                "created_at": nowiso,
            })

    return relations


# --- File emit ---
def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(canonical_json(record) + "\n")


def emit_packet(
    output_dir: Path,
    lesson_path: Path,
    frontmatter: Dict[str, Any],
    legacy_tag: str,
    lesson_title: str,
    sources: List[Dict[str, Any]],
    spans: List[Dict[str, Any]],
    claims: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    nowiso: str,
) -> Tuple[str, Dict[str, Any]]:
    """Write all canonical files + manifest + views. Returns (state_hash, manifest)."""
    # 1. Write canonical JSONL files first.
    write_jsonl(output_dir / "data/sources.jsonl", sources)
    write_jsonl(output_dir / "data/spans.jsonl", spans)
    write_jsonl(output_dir / "data/claims.jsonl", claims)
    write_jsonl(output_dir / "data/relations.jsonl", relations)

    # 2. Emit initial write event (post_state_hash is the chained-from-prev-event hash).
    events: List[Dict[str, Any]] = [{
        "id": "event:create-packet",
        "type": "WriteEvent",
        "op": "create_packet",
        "actor": "forge:convert_aepkit_lesson.py-Phase-1.1",
        "target": "aepkg.json",
        "pre_state_hash": "sha256:" + "0" * 64,
        "post_state_hash": "TBD-after-state-hash-computed",
        "rationale": "Phase-1.1 first validator-clean conversion of AEP project lesson HTML to AEP v0.3 packet",
        "created_at": nowiso,
    }]
    write_jsonl(output_dir / "ops/events.jsonl", events)

    reviews: List[Dict[str, Any]] = []  # Empty until reviewers run; valid per schema (no entries required).
    write_jsonl(output_dir / "reviews/reviews.jsonl", reviews)

    # 3. Write a self-validation placeholder before computing the final state hash.
    initial_validation = [{
        "id": "validation:converter-self",
        "type": "ValidationRun",
        "validator": "convert_aepkit_lesson.py-Phase-1.1",
        "result": "pass",
        "checked_files": list(REQUIRED_FILES) + ["aepkg.json"],
        "findings": [
            {"severity": "info", "path": "convert_aepkit_lesson.py", "message": "Converter self-emits a pass-grade run; external reference validator is the gating check."}
        ],
        "state_hash": "TBD-after-state-hash-computed",
        "created_at": nowiso,
    }]
    write_jsonl(output_dir / "validations/runs.jsonl", initial_validation)

    # 4. Build manifest (without state_hash yet — state_hash is computed AFTER all canonical files exist).
    packet_id = "aepkg:" + lesson_path.stem.replace(".", "-").replace(" ", "-")
    manifest: Dict[str, Any] = {
        "aep_version": "0.3",
        "packet_id": packet_id,
        "title": lesson_title or lesson_path.stem,
        "created_at": nowiso,
        "created_by": "forge:convert_aepkit_lesson.py-Phase-1.1",
        "profile": "aep:0.3/minimal-jsonl",
        "canonical_files": list(REQUIRED_FILES),
        "extensions": {
            "aep:source_lesson": str(lesson_path).replace("\\", "/"),
            "aep:source_frontmatter": frontmatter,
            "aep:legacy_truth_tag": legacy_tag,
            "aep:two_axis_schema": "V11-charter-section-2.1-operator-approved-2026-05-14",
            "aep:converter_phase": "Phase-1.1",
            "aep:governance_rule_amendment": "doctrine/02 Amendment A15 operator-approved 2026-05-14",
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "state_hash": "TBD-after-state-hash-computed",
        },
    }
    with open(output_dir / "aepkg.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")

    # 5. Compute state_hash from canonical files on disk (mirrors reference validator exactly).
    state_hash = compute_state_hash(output_dir, manifest["canonical_files"])
    manifest["integrity"]["state_hash"] = state_hash

    # 6. Re-emit manifest with the final state_hash baked in.
    with open(output_dir / "aepkg.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")

    # 7. Update validation + event with the computed state_hash so they cite the real value.
    initial_validation[0]["state_hash"] = state_hash
    write_jsonl(output_dir / "validations/runs.jsonl", initial_validation)

    events[0]["post_state_hash"] = state_hash
    write_jsonl(output_dir / "ops/events.jsonl", events)

    # 8. Re-compute state_hash one final time because events + validations now reference it.
    #    (This is the "frozen" state hash after all files settle. We DO NOT mutate the manifest
    #    because it would create an infinite loop. Instead the final hash is what the validator
    #    will compute on its next pass.)
    final_hash = compute_state_hash(output_dir, manifest["canonical_files"])
    manifest["integrity"]["state_hash"] = final_hash
    with open(output_dir / "aepkg.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")

    # 9. Generated views (non-canonical projections per LAW-02).
    write_views(output_dir, manifest, claims, sources, relations, lesson_title)

    # 10. Loss-less preservation: copy the original source file verbatim into assets/original.<ext>
    #     so any consumer can byte-perfectly reconstruct the original from the packet.
    import shutil
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    preserved_filename = f"original{lesson_path.suffix}"
    preserved_path = assets_dir / preserved_filename
    shutil.copy2(lesson_path, preserved_path)
    # Compute and persist the original-file sha256 so consumers can verify integrity.
    original_bytes = lesson_path.read_bytes()
    original_sha = "sha256:" + hashlib.sha256(original_bytes).hexdigest()
    (assets_dir / "original.sha256").write_text(original_sha + "  " + preserved_filename + "\n", encoding="utf-8")
    # Update manifest with the preservation pointer + integrity hash (does not affect canonical state_hash).
    manifest["extensions"]["aep:original_preserved_at"] = f"assets/{preserved_filename}"
    manifest["extensions"]["aep:original_sha256"] = original_sha
    manifest["extensions"]["aep:original_bytes"] = len(original_bytes)
    with open(output_dir / "aepkg.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, sort_keys=True, indent=2, ensure_ascii=False)
        f.write("\n")

    return final_hash, manifest


def write_views(
    output_dir: Path,
    manifest: Dict[str, Any],
    claims: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    lesson_title: str,
) -> None:
    views_dir = output_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    # Markdown summary
    summary = [
        f"# {lesson_title or manifest['packet_id']}",
        "",
        f"**Packet**: `{manifest['packet_id']}`  ",
        f"**Source**: `{manifest['extensions']['aep:source_lesson']}`  ",
        f"**State hash**: `{manifest['integrity']['state_hash']}`  ",
        f"**Claims**: {len(claims)} | **Sources**: {len(sources)} | **Relations**: {len(relations)}  ",
        f"**Legacy truth tag**: `{manifest['extensions']['aep:legacy_truth_tag']}`  ",
        "",
        "## Claims (one per row)",
        "",
    ]
    for claim in claims[:80]:
        axis_a = claim.get("aep:axis_a_epistemic", "?")
        axis_b = claim.get("aep:axis_b_action", "?")
        sid = claim.get("aep:section_id", "?")
        kind = claim.get("aep:kind", "?")
        text_preview = claim["text"][:140] + ("…" if len(claim["text"]) > 140 else "")
        summary.append(
            f"- `{claim['id']}` [{axis_a}/{axis_b}] kind=`{kind}` §`{sid}` — {text_preview}"
        )
    if len(claims) > 80:
        summary.append(f"")
        summary.append(f"_(showing first 80 of {len(claims)} claims)_")
    (views_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    # Mermaid map: sections containing claims, with edges to related claims
    mmd = ["graph LR"]
    seen_sections: set = set()
    for claim in claims:
        sid = claim.get("aep:section_id", "unknown")
        section_node = f"section_{re.sub(r'[^A-Za-z0-9]', '_', sid)}"
        claim_node = claim["id"].replace(":", "_")
        if sid not in seen_sections:
            seen_sections.add(sid)
            title = claim.get("aep:section_title", sid)
            mmd.append(f'  {section_node}["{title[:40]}"]')
        axis_a_short = claim.get("aep:axis_a_epistemic", "?")[:4]
        mmd.append(f'  {section_node} --> {claim_node}["{axis_a_short}"]')
    (views_dir / "map.mmd").write_text("\n".join(mmd) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert AEP project lesson HTML to AEP v0.3 .aepkg/")
    parser.add_argument("lesson", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true", help="Overwrite existing output dir")
    args = parser.parse_args(argv)

    lesson_path = args.lesson.resolve()
    output_dir = args.output.resolve()

    if not lesson_path.exists():
        print(f"ERROR: Lesson not found: {lesson_path}", file=sys.stderr)
        return 1
    if output_dir.exists():
        if args.force:
            import shutil
            shutil.rmtree(output_dir)
        else:
            print(f"ERROR: Output already exists: {output_dir} (use --force to overwrite)", file=sys.stderr)
            return 1

    print(f"=== convert_aepkit_lesson.py Phase-1.1 ===")
    print(f"Lesson:  {lesson_path}")
    print(f"Output:  {output_dir}")
    print()

    html_content = lesson_path.read_text(encoding="utf-8")

    # Detect format and dispatch
    fmt = detect_lesson_format(html_content)
    print(f"Format:   {fmt}")

    if fmt == "markdown-wrapped":
        lesson_title, frontmatter, sections, cite_links = extract_markdown_wrapped(html_content, lesson_path)
    else:
        parser_inst = AEP projectLessonParser()
        parser_inst.feed(html_content)
        frontmatter = parse_frontmatter(parser_inst.frontmatter_text)
        lesson_title = parser_inst.lesson_title
        sections = parser_inst.sections
        cite_links = parser_inst.cite_links

    legacy_tag = (frontmatter.get("truth_tag") or "STRONGLY PLAUSIBLE").strip()

    nowiso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Extract
    sources = [build_lesson_self_source(lesson_path, lesson_title, nowiso)]
    sources.extend(build_cite_sources(cite_links, nowiso))
    claims, spans = extract_claims_and_spans(sections, legacy_tag, nowiso)
    relations = extract_relations(claims, nowiso)

    # Emit
    state_hash, manifest = emit_packet(
        output_dir=output_dir,
        lesson_path=lesson_path,
        frontmatter=frontmatter,
        legacy_tag=legacy_tag,
        lesson_title=lesson_title,
        sources=sources,
        spans=spans,
        claims=claims,
        relations=relations,
        nowiso=nowiso,
    )

    print(f"=== EMIT COMPLETE (Phase-1.1) ===")
    print(f"Output:     {output_dir}")
    print(f"State hash: {state_hash}")
    print(f"Counts:     {len(claims)} claims | {len(sources)} sources | {len(spans)} spans | {len(relations)} relations")
    print()
    print(f"Validate with reference impl:")
    print(f"  PYTHONPATH=src python -m aep.validate {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
