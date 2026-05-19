#!/usr/bin/env python3
"""truth_tag_required_guard.py - PreToolUse hook (M-B-2; LC-09 Unknown-Stays-Unknown mechanically codified).

Purpose
-------
Mechanically enforce the truth-tag-required-on-claims discipline at hook level.
Per the agent analysis of operator research drop 2026-05-17 (LC-09 PROVEN/RELIABLE-ready):

    "A skill MUST NOT manufacture certainty it does not have; the unknown
    remains tagged unknown until evidence accrues."

This guard BLOCKS substantive in-scope artifact writes that lack ANY truth-tag.
Per sibling-50 EH Law-1 + the agentic substrate Constitution no-fabrication rule +
truth-tag IMPOSSIBLE/UNSUPPORTED tier: artifacts that DO have claims must
declare their confidence-level explicitly.

Truth tag (file overall): STRONGLY PLAUSIBLE (basis: LC-09 PROVEN/RELIABLE-ready
per the agent analysis but hook-level enforcement only reaches PROVEN/RELIABLE after
30-day adversary attack window per sec56; the hook itself is reflexive evidence
of LC-09 - the unknown stays unknown until proven, including the question of
whether this hook is reliable).

Scope (in-scope path prefixes; substantive writes here require truth-tag):
  - doctrine/lessons/                           (lessons require truth-tags)
  - doctrine/_proposals/                        (proposals require truth-tags)
  - research/sources/                           (research drops have truth-tags)
  - research/analysis/                          (analyses have truth-tags)
  - projects/v11-aep/publish-ready/aep/         (the agent reports have truth-tags)

Out-of-scope (always allowed; no truth-tag required regardless of size):
  - everything outside the in-scope path prefixes above
  - README.md / CHANGELOG.md / source-code files
  - Index files (.html ending in _index)
  - JSON/JSONL/YAML data files

Substantive threshold (OR gate per Codex sec45 burn recommendation):
  - LOC > 200, OR
  - Has at least 1 markdown/HTML heading AND >= 120 non-whitespace body chars

Truth-tag detection patterns (ANY ONE satisfies):
  1. data-truth-tag="<TIER>" or data-tt="<TIER>" HTML attribute
  2. YAML frontmatter truth_tag: <TIER> field
  3. Prose "Truth tag" / "Truth-tag" / "**Truth tag**" followed by tier value

Canonical tier values (9 accepted: 6 knowledge tiers + GOVERNANCE-RULE + PLAUSIBLE + unknown):
  - PROVEN/RELIABLE
  - STRONGLY PLAUSIBLE  (also strongly-plausible kebab-case)
  - EXPERIMENTAL
  - SPECULATIVE FRONTIER (also speculative-frontier)
  - IMPOSSIBLE/UNSUPPORTED (also impossible-unsupported)
  - DANGEROUS/NOT WORTH DOING (also dangerous-not-worth-doing)
  - GOVERNANCE-RULE          (per A15 amendment 2026-05-14)
  - PLAUSIBLE                (transitional tier in active use per LC-08 analysis row)
  - unknown                  (per LC-09 reflexive: unknown stays unknown is itself valid)

Approval mechanism
------------------
Operator (or operator-delegated curator) places a waiver file at
.claude/truth_tag_waivers/<sha256-of-canonical-path>.json with shape:

    {
      "path": "doctrine/lessons/2026-05-18-some-slug.html",
      "approved_by": "operator-shadow",
      "approved_at": "2026-05-18T00:00:00Z",
      "expires_at": "2026-05-19T00:00:00Z",  # optional; default no expiry
      "reason": "<operator-supplied rationale>",
      "tier_declared": "unknown"             # optional; what tier would have been declared
    }

Exit codes
----------
  0 - allow (out-of-scope OR sub-threshold OR truth-tagged OR waivered)
  2 - block (in-scope + substantive + no truth-tag + no waiver)
  0 - on internal exception (fail-OPEN; LC-09 enforcement is defense-in-depth
      not the only line; sec73.6 honest framing - the operator can still
      observe untagged artifacts and self-correct; failing-closed on the
      guard's own bugs would be worse UX than the residual risk)

Per sec68 - Python only, no PowerShell anywhere.
Per sec73.5 - WARDEN RECEIPTS OR HALT - every block emits a receipt.
Per sec73.6 - this hook does NOT depend on operator reaction; it enforces mechanically.

Composes with:
  - sec02 truth-tags (the 6-tier taxonomy + A15 GOVERNANCE-RULE class)
  - sec05 git-workflow (single-writer discipline)
  - sec07 agent-roster (scribe writes lessons; curator writes proposals)
  - sec41 HCRL hash-chained receipt ledger
  - sec50 EH Law-1 (falsification path; LC-09 IS Law-1 mechanically codified)
  - sec56 operational-evidence-over-synthetic-ranking (promotion gate)
  - sec68 defender-guard (composes alongside; runs SEPARATELY in PreToolUse)
  - sec73.6 (honest-framing requires explicit truth-tag declaration)
  - doctrine_write_guard.py M-B-1 (composes alongside; runs SEPARATELY)
  - aep_pre_tool_guard.py K3 airlock (composes alongside)
  - LC-09 unknown-stays-unknown (this hook IS LC-09 mechanically codified)
  - sibling-50 EH Law-1 falsification-path (composes_with)
  - the agentic substrate Constitution no-fabrication rule (composes_with)
"""
from __future__ import annotations

import json
import os
import re
import sys

_HOOK_FILE = __file__


def _repo_root():
    # .claude/hooks/aep/truth_tag_required_guard.py -> 4 levels up to repo root
    p = os.path.abspath(_HOOK_FILE)
    for _ in range(4):
        p = os.path.dirname(p)
    return p


def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_hex(s):
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _append_jsonl(path, row):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _emit_block(path, reason, rule_id, tool_name):
    """Emit a block-receipt to .claude/_logs/truth-tag-required-blocks.jsonl."""
    log_path = os.path.join(_repo_root(), ".claude", "_logs", "truth-tag-required-blocks.jsonl")
    _append_jsonl(log_path, {
        "ts_utc": _utc_now_iso(),
        "verdict": "BLOCK",
        "hook": "truth_tag_required_guard.py",
        "rule_id": rule_id,
        "tool_name": tool_name,
        "path": path,
        "reason": reason,
        "pid": os.getpid(),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "BLOCK",
        "composes_with": "LC-09,sec02,sec50,sec56,sec68,sec73.5,sec73.6",
    })


def _emit_allow(path, reason, rule_id, tool_name):
    """Emit an allow-receipt (informational; only for in-scope paths)."""
    log_path = os.path.join(_repo_root(), ".claude", "_logs", "truth-tag-required-allows.jsonl")
    _append_jsonl(log_path, {
        "ts_utc": _utc_now_iso(),
        "verdict": "ALLOW",
        "hook": "truth_tag_required_guard.py",
        "rule_id": rule_id,
        "tool_name": tool_name,
        "path": path,
        "reason": reason,
        "pid": os.getpid(),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "ALLOW",
    })


def _normalize_path(p):
    """Normalize a path string for matching."""
    if not isinstance(p, str) or not p:
        return ""
    s = p.replace("\\", "/").strip()
    if s.startswith("./"):
        s = s[2:]
    s_low = s.lower()
    repo_root_low = _repo_root().replace("\\", "/").lower()
    if s_low.startswith(repo_root_low + "/"):
        s = s[len(repo_root_low) + 1:]
        s_low = s.lower()
    return s_low


def _extract_paths_and_contents(tool_name, tool_input):
    """Extract a list of (file_path, proposed_content) pairs from tool_input.

    For Write/Edit/MultiEdit, the proposed-content is reconstructed from the
    tool_input shape. For MultiEdit, we approximate the content as concatenation
    of new_string fields (used for tag-detection only, not file ops).
    """
    out = []
    if not isinstance(tool_input, dict):
        return out

    file_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    if not isinstance(file_path, str) or not file_path:
        return out

    # Write tool: content is in tool_input['content']
    if tool_name == "Write":
        content = tool_input.get("content", "")
        if isinstance(content, str):
            out.append((file_path, content))
            return out

    # Edit tool: new_string is the replacement segment; we evaluate against
    # post-edit file content (best-effort: read current file + apply edit)
    if tool_name == "Edit":
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        post = _reconstruct_post_edit(file_path, old_string, new_string,
                                       replace_all=bool(tool_input.get("replace_all", False)))
        out.append((file_path, post))
        return out

    # MultiEdit: apply edits sequentially to current file content
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        post = _read_file_safe(file_path)
        if isinstance(edits, list):
            for e in edits:
                if not isinstance(e, dict):
                    continue
                old_s = e.get("old_string", "")
                new_s = e.get("new_string", "")
                if not isinstance(old_s, str) or not isinstance(new_s, str):
                    continue
                if e.get("replace_all"):
                    post = post.replace(old_s, new_s)
                else:
                    post = post.replace(old_s, new_s, 1)
        out.append((file_path, post))
        return out

    # NotebookEdit: best-effort; cell sources may be in tool_input
    if tool_name == "NotebookEdit":
        # We don't deeply parse notebook structure; just allow (out-of-typical-scope)
        out.append((file_path, ""))
        return out

    return out


def _read_file_safe(file_path):
    """Best-effort read of current file content; empty string on any error."""
    try:
        if not os.path.isabs(file_path):
            full = os.path.join(_repo_root(), file_path)
        else:
            full = file_path
        if not os.path.isfile(full):
            return ""
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            return f.read(1024 * 1024)
    except Exception:
        return ""


def _reconstruct_post_edit(file_path, old_string, new_string, replace_all=False):
    """Apply a single Edit op to the current file content."""
    if not isinstance(old_string, str) or not isinstance(new_string, str):
        return ""
    base = _read_file_safe(file_path)
    if not base:
        return new_string
    if old_string == "":
        return new_string
    if replace_all:
        return base.replace(old_string, new_string)
    return base.replace(old_string, new_string, 1)


# ============================================================================
# Scope classification
# ============================================================================

_IN_SCOPE_PREFIXES = (
    "doctrine/lessons/",
    "doctrine/_proposals/",
    "research/sources/",
    "research/analysis/",
    "projects/v11-aep/publish-ready/aep/",
)

_AUTO_ALLOW_BASENAMES = (
    "_index.html",
    "_index.md",
    "index.html",
    "index.md",
)

_DATA_OR_CODE_EXTS = (
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".cjs", ".mjs", ".js", ".ts", ".tsx", ".jsx",
    ".pl", ".rb", ".sh", ".bat", ".cmd",
    ".csv", ".tsv", ".txt",
    ".css", ".scss", ".less",
    ".sha256", ".sig", ".lock", ".log",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".pdf", ".zip", ".gz", ".tar",
)


def _is_in_scope(norm_path):
    """Return True if the path is in a truth-tag-required scope."""
    if not norm_path:
        return False
    for prefix in _IN_SCOPE_PREFIXES:
        if norm_path.startswith(prefix):
            return True
    return False


def _is_auto_allowed_basename(norm_path):
    """Return True if the basename matches an auto-allow list (index files)."""
    basename = os.path.basename(norm_path)
    return basename in _AUTO_ALLOW_BASENAMES


def _is_data_or_code_ext(norm_path):
    """Return True if the extension is data/code (truth-tag not applicable)."""
    low = norm_path.lower()
    for ext in _DATA_OR_CODE_EXTS:
        if low.endswith(ext):
            return True
    return False


# ============================================================================
# Substantive-threshold detection
# ============================================================================

_HEADING_RE = re.compile(r"(?m)^\s*(#{1,6}\s+\S|<h[1-6][\s>])", re.IGNORECASE)


def _is_substantive(content):
    """Return (is_substantive, reason).

    OR gate per Codex sec45 burn recommendation:
      1. LOC > 200, OR
      2. Has at least 1 markdown/HTML heading AND >= 120 non-whitespace body chars
    """
    if not isinstance(content, str) or not content:
        return (False, "empty_content")
    loc = content.count("\n") + (0 if content.endswith("\n") else 1)
    if loc > 200:
        return (True, "loc>200 (actual=" + str(loc) + ")")
    nonws = len(re.sub(r"\s+", "", content))
    if _HEADING_RE.search(content) and nonws >= 120:
        return (True, "has_heading_and_nonws>=120 (actual_nonws=" + str(nonws) + ")")
    return (False, "below_threshold (loc=" + str(loc) + ", nonws=" + str(nonws) + ")")


# ============================================================================
# Truth-tag detection
# ============================================================================

# Canonical tier values (case-insensitive match; both spaced and kebab-case)
_CANONICAL_TIERS_NORMALIZED = (
    "proven/reliable", "proven-reliable",
    "strongly plausible", "strongly-plausible",
    "experimental",
    "speculative frontier", "speculative-frontier",
    "impossible/unsupported", "impossible-unsupported",
    "dangerous/not worth doing", "dangerous-not-worth-doing",
    "governance-rule", "governance rule",
    "unknown",
    "plausible",  # transitional tier (per LC-08 row in analysis.html)
)

# data-truth-tag="..." or data-tt="..." attribute
_DATA_TAG_RE = re.compile(
    r"""data-(?:truth-tag|tt)\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)

# YAML frontmatter truth_tag: value
_YAML_TAG_RE = re.compile(
    r"""(?m)^\s*truth[-_]tag\s*:\s*["']?([^"'\n]+?)["']?\s*$""",
    re.IGNORECASE,
)

# Prose "Truth tag" / "Truth-tag" / "**Truth tag**" followed by tier.
# Gap is up to 60 chars (any char incl HTML tags like </strong>: ) — the
# tag label and tier must appear close together, but markdown/HTML wrappers
# between them are allowed.
_PROSE_TAG_RE = re.compile(
    r"""(?is)truth[-\s]?tag\b.{0,60}?
        (proven\s*[/-]\s*reliable
        | strongly\s*[-\s]?\s*plausible
        | experimental
        | speculative\s*[-\s]?\s*frontier
        | impossible\s*[/-]\s*unsupported
        | dangerous\s*[/-]\s*not\s*worth\s*doing
        | governance\s*[-\s]?\s*rule
        | unknown
        | plausible
        )""",
    re.VERBOSE,
)


def _normalize_tier(tier_raw):
    """Lowercase + collapse whitespace for tier comparison."""
    if not isinstance(tier_raw, str):
        return ""
    t = tier_raw.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _is_canonical_tier(tier_raw):
    """Return True if tier_raw matches any canonical tier (case/format-insensitive)."""
    norm = _normalize_tier(tier_raw)
    if norm in _CANONICAL_TIERS_NORMALIZED:
        return True
    # Also accept slash <-> hyphen variants
    slash_to_hyphen = norm.replace("/", "-").replace(" ", "-")
    hyphen_to_slash = norm.replace("-", "/").replace(" ", "/")
    spaced = norm.replace("-", " ").replace("/", " ")
    if slash_to_hyphen in _CANONICAL_TIERS_NORMALIZED:
        return True
    if hyphen_to_slash in _CANONICAL_TIERS_NORMALIZED:
        return True
    if spaced in _CANONICAL_TIERS_NORMALIZED:
        return True
    return False


def _has_valid_truth_tag(content):
    """Return (has_tag, tag_value, detection_mode).

    detection_mode: 'data-attr' | 'yaml-frontmatter' | 'prose' | 'none'
    """
    if not isinstance(content, str) or not content:
        return (False, "", "none")

    # 1. HTML data attribute
    for m in _DATA_TAG_RE.finditer(content):
        tag_val = m.group(1)
        if _is_canonical_tier(tag_val):
            return (True, tag_val, "data-attr")
    has_any_data_attr = bool(_DATA_TAG_RE.search(content))

    # 2. YAML frontmatter
    for m in _YAML_TAG_RE.finditer(content):
        tag_val = m.group(1)
        if _is_canonical_tier(tag_val):
            return (True, tag_val, "yaml-frontmatter")

    # 3. Prose mention
    for m in _PROSE_TAG_RE.finditer(content):
        tag_val = m.group(1)
        if _is_canonical_tier(tag_val):
            return (True, tag_val, "prose")

    if has_any_data_attr:
        return (False, "", "data-attr-invalid-value")
    return (False, "", "none")


# ============================================================================
# Waiver lookup
# ============================================================================

_WAIVER_DIR_REL = ".claude/truth_tag_waivers"


def _has_valid_waiver(norm_path):
    """Return (valid, reason)."""
    waiver_dir = os.path.join(_repo_root(), _WAIVER_DIR_REL)
    if not os.path.isdir(waiver_dir):
        return (False, "waiver_dir_missing")

    path_sha = _sha256_hex(norm_path)
    sha_path = os.path.join(waiver_dir, path_sha + ".json")
    candidates = []
    if os.path.isfile(sha_path):
        candidates.append(sha_path)

    try:
        for entry in os.listdir(waiver_dir):
            if not entry.endswith(".json"):
                continue
            full = os.path.join(waiver_dir, entry)
            if full in candidates:
                continue
            candidates.append(full)
    except Exception:
        pass

    for cand in candidates:
        try:
            with open(cand, "r", encoding="utf-8") as f:
                payload = json.loads(f.read())
        except Exception:
            continue
        waivered_path = _normalize_path(payload.get("path", ""))
        if waivered_path != norm_path:
            continue
        expires_at = payload.get("expires_at")
        if expires_at:
            try:
                from datetime import datetime, timezone
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if now > exp:
                    continue
            except Exception:
                continue
        if not payload.get("approved_by"):
            continue
        return (True, "waiver:" + os.path.basename(cand))

    return (False, "no_valid_waiver_found")


# ============================================================================
# Evaluation
# ============================================================================

_PROTECTED_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def evaluate(event):
    """Return (exit_code, reason, rule_id) for the given hook event."""
    tool_name = event.get("tool_name") or event.get("toolName") or ""
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool_name not in _PROTECTED_TOOLS:
        return (0, "", "TRUTH-TAG-REQUIRED-OUT-OF-SCOPE-TOOL")

    pairs = _extract_paths_and_contents(tool_name, tool_input)
    if not pairs:
        return (0, "", "TRUTH-TAG-REQUIRED-NO-PATHS")

    for file_path, content in pairs:
        norm = _normalize_path(file_path)

        # 1. In-scope check
        if not _is_in_scope(norm):
            continue

        # 2. Auto-allow extensions (data/code files in scope dirs don't need truth-tags)
        if _is_data_or_code_ext(norm):
            _emit_allow(norm, "auto_allow_data_or_code_ext", "TRUTH-TAG-REQUIRED-DATA-OR-CODE-EXT", tool_name)
            continue

        # 3. Auto-allow basenames (index files)
        if _is_auto_allowed_basename(norm):
            _emit_allow(norm, "auto_allow_index_basename", "TRUTH-TAG-REQUIRED-INDEX-BASENAME", tool_name)
            continue

        # 4. Substantive threshold check
        is_subst, subst_reason = _is_substantive(content)
        if not is_subst:
            _emit_allow(norm, "below_substantive_threshold: " + subst_reason,
                        "TRUTH-TAG-REQUIRED-BELOW-THRESHOLD", tool_name)
            continue

        # 5. Truth-tag presence check
        has_tag, tag_value, det_mode = _has_valid_truth_tag(content)
        if has_tag:
            _emit_allow(norm, "has_truth_tag:" + tag_value + " (mode=" + det_mode + ")",
                        "TRUTH-TAG-REQUIRED-TAGGED", tool_name)
            continue

        # 6. Waiver fallback
        waivered, waiver_reason = _has_valid_waiver(norm)
        if waivered:
            _emit_allow(norm, waiver_reason, "TRUTH-TAG-REQUIRED-WAIVER", tool_name)
            continue

        # 7. BLOCK - in-scope + substantive + no tag + no waiver
        return (
            2,
            (
                "truth_tag_required_guard: BLOCK in-scope substantive artifact '"
                + norm
                + "' has no truth-tag declared (LC-09 unknown-stays-unknown "
                + "mechanically codified). Substantive trigger: "
                + subst_reason
                + ". Declare ONE of: (a) HTML attribute data-truth-tag=\"<TIER>\" "
                + "or data-tt=\"<TIER>\" in the body; (b) YAML frontmatter "
                + "truth_tag: <TIER>; (c) prose \"Truth tag: <TIER>\" near the "
                + "top of the document. Canonical tiers: PROVEN/RELIABLE | "
                + "STRONGLY PLAUSIBLE | EXPERIMENTAL | SPECULATIVE FRONTIER | "
                + "IMPOSSIBLE/UNSUPPORTED | DANGEROUS/NOT WORTH DOING | "
                + "GOVERNANCE-RULE | PLAUSIBLE | unknown. Per sec02 truth-tag "
                + "taxonomy + sec50 EH Law-1 + the agentic substrate Constitution "
                + "no-fabrication rule. To intentionally permit untagged: place "
                + "a waiver file at .claude/truth_tag_waivers/<sha256(path)>.json. "
                + "Path sha256: " + _sha256_hex(norm)
            ),
            "TRUTH-TAG-REQUIRED-BLOCK-NO-TAG",
        )

    return (0, "", "TRUTH-TAG-REQUIRED-ALL-PATHS-CLEARED")


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        try:
            event = json.loads(raw)
        except Exception:
            return 0

        code, reason, rule_id = evaluate(event)
        if code != 0:
            tool_input = event.get("tool_input") or event.get("toolInput") or {}
            pairs = _extract_paths_and_contents(event.get("tool_name", ""), tool_input)
            for p, _ in pairs:
                _emit_block(_normalize_path(p), reason, rule_id, event.get("tool_name", ""))
            sys.stderr.write("[truth_tag_required_guard:" + rule_id + "] " + reason + "\n")
            return 2
        return 0
    except Exception as e:
        # Fail OPEN on internal error per docstring; emit diagnostic to stderr
        sys.stderr.write(
            "[truth_tag_required_guard:INTERNAL_ERROR] " + type(e).__name__ + ": " + str(e) + "\n"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
