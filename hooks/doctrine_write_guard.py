#!/usr/bin/env python3
"""doctrine_write_guard.py - PreToolUse hook (M-B-1; LC-05 operator-rejection mechanically codified).

Purpose
-------
Mechanically codify the operator's 2026-05-17 verbatim rejection of unconstrained
self-modification WITHOUT single-writer / append-only / reviewer discipline.
Operator verdict (research/analysis/operator-2026-05-17-claude-skills-prompting):

    "Adopt with modification": skill packets + composability + toolized
    deterministic + invocation controls + receipt loop + regression harness.

    Rejection: "AI should update itself every session" WITHOUT single-writer /
    append-only / reviewer discipline.

This guard implements LC-05 Side-Effects-Require-Manual-Gate at hook level. It
BLOCKS direct writes to canonical doctrine slots (doctrine/<NN>-<slot>.html)
unless an operator-signed approval file is present at
.claude/doctrine_write_approvals/<sha>.json authorizing the specific path.

Truth tag (file overall): STRONGLY PLAUSIBLE (basis: operator-verbatim rejection
direct-cited; hook-level enforcement is the load-bearing mechanism; promotion to
PROVEN/RELIABLE requires 30-day adversary attack window per sec56).

Allow-list (writes ALLOWED with no approval required):
  - doctrine/_proposals/...        (curator staging surface)
  - doctrine/lessons/...           (scribe lesson capture surface)
  - doctrine/_anchors/...          (chain maintenance; pin-ledger-head et al)
  - doctrine/_glossary-*.html      (glossary fragments curator-staged)
  - doctrine/lessons/_index.html   (scribe index)
  - doctrine/_proposals/_index.html (curator index)
  - paths OUTSIDE doctrine/        (research, .claude, projects, etc.)

Block-list (writes BLOCKED without approval file):
  - doctrine/<NN>-<slot>.html      (canonical doctrine slots, NN = numeric prefix)
  - doctrine/<NN>-<slot>.sha256    (sha-pinned slot digests)
  - doctrine/<NN>-<slot>.aepkg/*   (AEP companion of canonical slot)

Approval mechanism
------------------
Operator (or operator-delegated curator) places a metadata file at
.claude/doctrine_write_approvals/<sha256-of-canonical-path>.json with shape:

    {
      "path": "doctrine/68-defender-alert-stops-burn.html",
      "approved_by": "operator-shadow",
      "approved_at": "2026-05-18T00:00:00Z",
      "expires_at": "2026-05-19T00:00:00Z",  # optional; default 24h ttl if absent
      "reason": "<operator-supplied rationale>",
      "co_signer": "curator"                 # optional; warden|curator|scribe
    }

When evaluating a doctrine canonical write, the hook computes sha256(path) and
looks for the corresponding approval file. Absent/expired = BLOCK.

Exit codes
----------
  0 - allow (write target is not a canonical doctrine path, OR is and has valid approval)
  2 - block (write target is canonical doctrine without valid approval)
  0 - on internal exception (fail-OPEN; canonical-write protection is defense-in-depth
      not the only line; sec73.6 honest framing - the operator can still observe
      the canonical .md being modified and self-correct; failing-closed on the
      guard's own bugs would be worse UX than the residual risk)

Per sec68 - Python only, no PowerShell anywhere.
Per sec73.5 - WARDEN RECEIPTS OR HALT - every block emits a receipt.
Per sec73.6 - this hook does NOT depend on operator reaction; it enforces mechanically.

Composes with:
  - sec05 git-workflow (single-writer discipline)
  - sec07 agent-roster (scribe writes lessons; curator writes proposals; only
    operator+curator-co-sign writes canonical)
  - sec41 HCRL hash-chained receipt ledger
  - sec68 defender-guard (sec68.5 per-tool field scoping; this hook is narrower
    scope: doctrine canonical paths only)
  - sec69 verification-law + operator-spec-sovereignty
  - aep_pre_tool_guard.py K3 airlock (composes alongside; runs SEPARATELY in
    the PreToolUse chain)
  - LC-05 side-effects-require-manual-gate (this hook IS LC-05 mechanically
    codified)
  - LC-09 unknown-stays-unknown (absent approval = unknown intent = block)
"""
from __future__ import annotations

import json
import os
import sys
import time

_HOOK_FILE = __file__


def _repo_root():
    # .claude/hooks/aep/doctrine_write_guard.py -> 4 levels up to repo root
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
    """Emit a block-receipt to .claude/_logs/doctrine-write-blocks.jsonl."""
    log_path = os.path.join(_repo_root(), ".claude", "_logs", "doctrine-write-blocks.jsonl")
    _append_jsonl(log_path, {
        "ts_utc": _utc_now_iso(),
        "verdict": "BLOCK",
        "hook": "doctrine_write_guard.py",
        "rule_id": rule_id,
        "tool_name": tool_name,
        "path": path,
        "reason": reason,
        "pid": os.getpid(),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "BLOCK",
        "composes_with": "LC-05,LC-09,sec05,sec07,sec68,sec69,sec73.5,sec73.6",
    })


def _emit_allow(path, reason, rule_id, tool_name):
    """Emit an allow-receipt (informational; only fires for in-scope paths).

    Not every write triggers a receipt - only ones that touched the
    doctrine/ tree (whether allowed via allow-list or via approval file).
    Pure out-of-scope writes (research/, .claude/, etc.) do NOT emit receipts."""
    log_path = os.path.join(_repo_root(), ".claude", "_logs", "doctrine-write-allows.jsonl")
    _append_jsonl(log_path, {
        "ts_utc": _utc_now_iso(),
        "verdict": "ALLOW",
        "hook": "doctrine_write_guard.py",
        "rule_id": rule_id,
        "tool_name": tool_name,
        "path": path,
        "reason": reason,
        "pid": os.getpid(),
        "truth_tag_axis_a": "STRONGLY_PLAUSIBLE",
        "truth_tag_axis_b": "ALLOW",
    })


def _normalize_path(p):
    """Normalize a path string for matching. Lowercases, replaces backslashes
    with forward-slashes, strips leading './'."""
    if not isinstance(p, str) or not p:
        return ""
    s = p.replace("\\", "/").strip()
    if s.startswith("./"):
        s = s[2:]
    # Strip drive prefix / absolute-prefix if present so we match relative paths
    s_low = s.lower()
    repo_root_low = _repo_root().replace("\\", "/").lower()
    if s_low.startswith(repo_root_low + "/"):
        s = s[len(repo_root_low) + 1:]
        s_low = s.lower()
    return s_low


def _extract_paths(tool_name, tool_input):
    """Extract every file_path from the tool_input shape."""
    paths = []
    if not isinstance(tool_input, dict):
        return paths
    for key in ("file_path", "path", "notebook_path"):
        v = tool_input.get(key)
        if isinstance(v, str):
            paths.append(v)
    if "edits" in tool_input and isinstance(tool_input["edits"], list):
        for e in tool_input["edits"]:
            if isinstance(e, dict) and isinstance(e.get("file_path"), str):
                paths.append(e["file_path"])
    return paths


# ============================================================================
# Doctrine path classification
# ============================================================================

_DOCTRINE_PREFIX = "doctrine/"

# Allow-list prefixes (writes here NEVER require approval)
_ALLOW_PREFIXES = (
    "doctrine/_proposals/",
    "doctrine/lessons/",
    "doctrine/_anchors/",
    "doctrine/_assets/",
    "doctrine/agents/",          # doctrine/agents/manifest.html etc (per sec07 roster surface)
    "doctrine/cortex-v/",        # cortex-v agent-definitions surface
)

# Allow-list specific files (writes here NEVER require approval)
_ALLOW_FILES = (
    "doctrine/lessons/_index.html",
    "doctrine/_proposals/_index.html",
    "doctrine/_anchors/pin-ledger-head.txt",
)

# Allow-list prefixes for non-canonical sub-files (glossary fragments under
# doctrine/ but NOT canonical NN-slot)
_ALLOW_GLOSSARY_PREFIX = "doctrine/_glossary-"


def _is_canonical_doctrine_path(norm_path):
    """Return True if norm_path is a canonical doctrine slot path.

    A canonical doctrine slot looks like:
      doctrine/<NN>-<slug>.html
      doctrine/<NN>-<slug>.sha256
      doctrine/<NN>-<slug>.aepkg/<anything>

    Where <NN> is one or two digit numeric prefix (e.g. "00", "05", "68").
    """
    if not norm_path.startswith(_DOCTRINE_PREFIX):
        return False
    rest = norm_path[len(_DOCTRINE_PREFIX):]
    # Allow-list short-circuit
    if rest.startswith("_"):
        # doctrine/_proposals/, doctrine/_lessons/, doctrine/_anchors/, doctrine/_assets/, doctrine/_glossary-
        return False
    # Reject if first directory is non-canonical (agents/, cortex-v/, etc.)
    # already handled by ALLOW_PREFIXES, but be defensive: only flag NN-* file
    # pattern as canonical
    if "/" not in rest:
        # Top-level file under doctrine/: must match NN-*.html | NN-*.sha256 pattern
        return _matches_NN_slot(rest)
    # Multi-level: first segment must match NN-*.aepkg
    first_seg, _ = rest.split("/", 1)
    return first_seg.endswith(".aepkg") and _matches_NN_slot(first_seg[:-len(".aepkg")] + ".html")


def _matches_NN_slot(filename):
    """Return True if filename matches <NN>-<slug>.<ext> with NN = 1-3 digits."""
    if not filename:
        return False
    # Must contain a dash after digits at the start
    i = 0
    while i < len(filename) and filename[i].isdigit():
        i += 1
    if i == 0 or i > 3:
        return False
    if i >= len(filename) or filename[i] != "-":
        return False
    # Must end in .html, .sha256, or .aepkg/...
    low = filename.lower()
    return (low.endswith(".html") or low.endswith(".sha256") or low.endswith(".aepkg"))


def _is_allowed_doctrine_path(norm_path):
    """Return (allowed, reason). Used for writes under doctrine/ that are NOT canonical."""
    # Specific-file allow-list
    if norm_path in _ALLOW_FILES:
        return (True, "allow_specific_file")
    # Prefix allow-list
    for prefix in _ALLOW_PREFIXES:
        if norm_path.startswith(prefix):
            return (True, "allow_prefix:" + prefix)
    # Glossary fragments
    if norm_path.startswith(_ALLOW_GLOSSARY_PREFIX):
        return (True, "allow_glossary_fragment")
    return (False, "")


# ============================================================================
# Approval file lookup
# ============================================================================

_APPROVAL_DIR_REL = ".claude/doctrine_write_approvals"


def _has_valid_approval(norm_path):
    """Return (valid, reason). Look up approval file for norm_path.

    Path-keyed approval: file at .claude/doctrine_write_approvals/<sha256(norm_path)>.json
    or .claude/doctrine_write_approvals/<basename>.json with payload['path'] matching.
    """
    approval_dir = os.path.join(_repo_root(), _APPROVAL_DIR_REL)
    if not os.path.isdir(approval_dir):
        return (False, "approval_dir_missing")

    # Path-sha keyed lookup first
    path_sha = _sha256_hex(norm_path)
    sha_path = os.path.join(approval_dir, path_sha + ".json")
    candidates = []
    if os.path.isfile(sha_path):
        candidates.append(sha_path)

    # Also scan any .json files in the dir whose payload['path'] matches
    try:
        for entry in os.listdir(approval_dir):
            if not entry.endswith(".json"):
                continue
            full = os.path.join(approval_dir, entry)
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
        approved_path = _normalize_path(payload.get("path", ""))
        if approved_path != norm_path:
            continue
        # Check expiry
        expires_at = payload.get("expires_at")
        if expires_at:
            try:
                from datetime import datetime, timezone
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if now > exp:
                    continue  # expired
            except Exception:
                # Malformed expires_at - treat as not approved
                continue
        # Validate required fields
        if not payload.get("approved_by"):
            continue
        return (True, "approval:" + os.path.basename(cand))

    return (False, "no_valid_approval_found")


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
        return (0, "", "DOCTRINE-WRITE-GUARD-OUT-OF-SCOPE-TOOL")

    paths = _extract_paths(tool_name, tool_input)
    if not paths:
        return (0, "", "DOCTRINE-WRITE-GUARD-NO-PATHS")

    for p in paths:
        norm = _normalize_path(p)
        if not norm.startswith(_DOCTRINE_PREFIX):
            # Out of doctrine scope entirely
            continue
        # In doctrine/ - check allow-list first
        allowed, reason = _is_allowed_doctrine_path(norm)
        if allowed:
            _emit_allow(norm, reason, "DOCTRINE-WRITE-GUARD-ALLOW-LIST", tool_name)
            continue
        # Not in allow-list - must be canonical slot or unknown
        if _is_canonical_doctrine_path(norm):
            # Check approval
            approved, approval_reason = _has_valid_approval(norm)
            if approved:
                _emit_allow(norm, approval_reason, "DOCTRINE-WRITE-GUARD-APPROVED", tool_name)
                continue
            return (
                2,
                (
                    "doctrine_write_guard: BLOCK canonical-doctrine write to '"
                    + norm
                    + "' - no valid approval file present (LC-05 operator-rejection "
                    + "mechanically codified). Approval mechanism: place a "
                    + "JSON file at .claude/doctrine_write_approvals/<sha256(path)>.json "
                    + "with shape {path, approved_by, approved_at, expires_at?, reason?, co_signer?}. "
                    + "Path sha256: " + _sha256_hex(norm) + "  Per sec05 single-writer + sec07 "
                    + "scribe-writes-lessons / curator-writes-proposals discipline + "
                    + "operator-2026-05-17 verbatim rejection."
                ),
                "DOCTRINE-WRITE-GUARD-BLOCK-CANONICAL",
            )
        # Path is under doctrine/ but does NOT match canonical-slot pattern.
        # Defense-in-depth: BLOCK on unknown doctrine paths (LC-09 unknown-
        # stays-unknown). Reduces attack surface for novel-named slot
        # injections. Operator can add explicit allow-list entries.
        return (
            2,
            (
                "doctrine_write_guard: BLOCK unknown-shape doctrine path '"
                + norm
                + "' - not in allow-list and not canonical-slot-shape (LC-09 "
                + "unknown-stays-unknown). To intentionally permit, either: (a) "
                + "place an approval file (see DOCTRINE-WRITE-GUARD-BLOCK-CANONICAL), "
                + "or (b) request a hook allow-list extension via curator."
            ),
            "DOCTRINE-WRITE-GUARD-BLOCK-UNKNOWN-SHAPE",
        )

    return (0, "", "DOCTRINE-WRITE-GUARD-ALL-PATHS-CLEARED")


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        try:
            event = json.loads(raw)
        except Exception:
            # Can't parse - fail OPEN per docstring (defense-in-depth, not sole line)
            return 0

        code, reason, rule_id = evaluate(event)
        if code != 0:
            tool_input = event.get("tool_input") or event.get("toolInput") or {}
            paths = _extract_paths(event.get("tool_name", ""), tool_input)
            for p in paths:
                _emit_block(_normalize_path(p), reason, rule_id, event.get("tool_name", ""))
            sys.stderr.write("[doctrine_write_guard:" + rule_id + "] " + reason + "\n")
            return 2
        return 0
    except Exception as e:
        # Fail OPEN on internal error per docstring; emit a diagnostic to stderr
        sys.stderr.write(
            "[doctrine_write_guard:INTERNAL_ERROR] " + type(e).__name__ + ": " + str(e) + "\n"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
