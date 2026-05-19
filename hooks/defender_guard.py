#!/usr/bin/env python3
"""defender_guard.py - Claude Code PreToolUse hook (Python; no PowerShell).

Reads a Claude Code hook payload (JSON) from stdin. Inspects any command-
bearing field. Calls aep.security.command_safety.classify_command. If the
result is UNSAFE, prints a concise reason to stderr and exits 2 (BLOCK). On
SAFE, exits 0.

Per operator incident-remediation directive 2026-05-16:
  - This script MUST NOT invoke PowerShell.
  - This script MUST NOT call the network.
  - This script MUST NOT modify Defender settings.
  - This script MUST log every block decision to .claude/_logs/defender-guard.jsonl.

Install via `.claude/settings.json` PreToolUse hook for matchers:
  Bash | Task | Agent | mcp__codex__codex | mcp__codex__codex-reply | Edit | Write | MultiEdit

Exit codes:
  0  safe - allow tool
  2  unsafe - block tool (stderr message becomes operator-visible reason)
  0  on internal error - fail-OPEN intentionally is REJECTED here; we fail-CLOSED
     to err on the side of stopping work when the guard itself is broken.

Note on fail-mode: per Constitution rule 5 transparency + sibling-94 honest-
framing, this hook fails CLOSED (exit 2) on any internal exception so an
operator notices guard regressions immediately. The previous all-PowerShell
hook regime used SilentlyContinue + exit-0; that swallowed errors and let the
ClickFix incident develop. The new regime is loud-and-blocking.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Import command_safety from the canonical location
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_AEP_ROOT = _REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep"
if str(_AEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_AEP_ROOT))


# ---------------------------------------------------------------------------
# Wave-003 M4 - SHA256-bound canonical text for doctrine/68 (BP-002 attack
# closure: "sec68.5 sub-clause is text-only; nothing prevents future drift
# away from the operator-ratified content"). Truth tag: STRONGLY PLAUSIBLE.
#
# This check is INFORMATIONAL only. We do NOT halt on drift - the operator
# may legitimately amend the doctrine and re-ratify the .sha256 digest. A
# drift emits a RED-flag receipt + a "DOCTRINE_DRIFT_DETECTED" verdict in
# defender-guard.jsonl so the next session-open scan surfaces it.
# ---------------------------------------------------------------------------

_DOCTRINE_68_PATH = _REPO_ROOT / "doctrine" / "68-defender-alert-stops-burn.html"
_DOCTRINE_68_SHA256_PATH = _REPO_ROOT / "doctrine" / "68-defender-alert-stops-burn.sha256"


def _compute_sha256(path: Path):
    """Return hex sha256 of a file, or None on error."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


def _read_ratified_digest():
    """Parse the .sha256 file. Returns (digest_hex, ratified_metadata_str) or (None, None)."""
    try:
        line = _DOCTRINE_68_SHA256_PATH.read_text(encoding="utf-8").strip().splitlines()[0]
        # Format: "<sha256>  <path>  # ratified ..."
        parts = line.split(None, 1)
        if not parts:
            return (None, None)
        digest = parts[0].strip().lower()
        meta = parts[1] if len(parts) > 1 else ""
        return (digest, meta)
    except Exception:
        return (None, None)


def check_doctrine_digest():
    """Return a dict describing the doctrine/68 digest-check result.

    Keys:
      verdict     - "PASS" | "DOCTRINE_DRIFT_DETECTED" | "DIGEST_FILE_MISSING"
                   | "DOCTRINE_FILE_MISSING" | "READ_ERROR"
      computed    - hex sha256 of doctrine/68 .html (or None)
      ratified    - hex sha256 from the .sha256 file (or None)
      ratified_meta - the trailing "# ratified ..." comment (informational)
      doctrine_path - absolute path inspected
    """
    out = {
        "verdict": "PASS",
        "computed": None,
        "ratified": None,
        "ratified_meta": None,
        "doctrine_path": str(_DOCTRINE_68_PATH),
        "sha256_file": str(_DOCTRINE_68_SHA256_PATH),
    }
    if not _DOCTRINE_68_PATH.exists():
        out["verdict"] = "DOCTRINE_FILE_MISSING"
        return out
    if not _DOCTRINE_68_SHA256_PATH.exists():
        out["verdict"] = "DIGEST_FILE_MISSING"
        out["computed"] = _compute_sha256(_DOCTRINE_68_PATH)
        return out
    computed = _compute_sha256(_DOCTRINE_68_PATH)
    ratified, meta = _read_ratified_digest()
    out["computed"] = computed
    out["ratified"] = ratified
    out["ratified_meta"] = meta
    if computed is None or ratified is None:
        out["verdict"] = "READ_ERROR"
        return out
    if computed.lower() != ratified.lower():
        out["verdict"] = "DOCTRINE_DRIFT_DETECTED"
    return out


def _emit_doctrine_digest_red_flag(check_result):
    """Append a RED-flag receipt + a doctrine-drift verdict to defender-guard.jsonl.

    Called once per process invocation that detects drift. Never halts;
    operator opens next session and sees the RED-flag receipt in
    receipt_validator output.
    """
    try:
        record = {
            "verdict": "DOCTRINE_DRIFT_DETECTED",
            "doctrine_digest_check": check_result,
            "policy_basis": "doctrine/68-defender-alert-stops-burn.html",
            "wave": "wave-003-m4",
        }
        _log(record)
    except Exception:
        pass
    # Also stamp a CommandReceipt with the RED-flag in notes so
    # receipt_validator surfaces it.
    try:
        from security.receipts import CommandReceipt, emit_receipt
        rec = CommandReceipt(
            command="<defender_guard.py startup doctrine digest check>",
            parent_task=os.environ.get("CLAUDE_PARENT_TASK")
                        or os.environ.get("CLAUDE_SESSION_ID")
                        or "wave-pretooluse",
            agent="defender_guard",
            exit_code=0,  # informational; we do not block on drift
            files_touched=[],
            network_attempted=False,
            defender_alert_observed=False,
            pause_marker_state="none",
            notes=(
                f"tool=defender_guard | verdict=DOCTRINE_DRIFT_DETECTED | "
                f"hook=defender_guard.py | "
                f"computed={check_result.get('computed')} | "
                f"ratified={check_result.get('ratified')} | "
                f"basis=doctrine/68"
            ),
        )
        emit_receipt(rec)
    except Exception:
        pass


def _emit_block(reason_lines, payload_summary):
    sys.stderr.write("\n".join(reason_lines) + "\n")
    sys.stderr.flush()
    _log({
        "verdict": "BLOCK",
        "reason_lines": reason_lines,
        "payload_summary": payload_summary,
    })
    _emit_command_receipt(verdict="BLOCK", payload_summary=payload_summary,
                           reason_lines=reason_lines)


def _emit_allow(payload_summary):
    _log({
        "verdict": "ALLOW",
        "payload_summary": payload_summary,
    })
    _emit_command_receipt(verdict="ALLOW", payload_summary=payload_summary,
                           reason_lines=None)


def _log(record):
    try:
        record["ts_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        record["pid"] = os.getpid()
        record["hook"] = "defender_guard.py"
        log_path = _REPO_ROOT / ".claude" / "_logs" / "defender-guard.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    except Exception:
        # Never let logging failure crash the guard.
        pass


def _emit_command_receipt(verdict, payload_summary, reason_lines):
    """Emit an incident-grade CommandReceipt to .claude/_logs/command-receipts.jsonl.

    Per doctrine/68-defender-alert-stops-burn.html "Incident-grade receipt
    requirement": every tool execution from 2026-05-16 forward MUST emit a
    receipt with timestamp, cwd, command, parent_task, agent, exit_code,
    files_touched, network_attempted, defender_alert_observed, pause_marker_state.

    Wave-002 task 4 wires this emit alongside the verbose defender-guard.jsonl
    log: both files are kept (verbose audit vs canonical operator-visible
    receipt). Adversary's F3 falsifier identified the missing file; this
    closes the gap.

    Never blocks the hook on receipt-emit failure (try/except wraps).
    """
    try:
        from security.receipts import CommandReceipt, emit_receipt
    except Exception:
        # If receipts module unavailable, fall back to inline schema-conforming
        # write so the canonical receipt log exists even when the package
        # cannot import for any reason.
        _emit_fallback_receipt(verdict, payload_summary, reason_lines)
        return

    try:
        tool_name = (payload_summary or {}).get("tool_name") or "unknown"
        command_preview = (payload_summary or {}).get("command_preview") or ""

        # Translate hook verdict into receipt exit_code semantics:
        #   ALLOW -> 0 (the guard permitted the tool; actual tool exit unknown
        #            at this PreToolUse stage; 0 signals "guard cleared")
        #   BLOCK -> 2 (the guard blocked the tool; matches defender_guard
        #            process exit code semantics)
        exit_code = 0 if verdict == "ALLOW" else 2

        notes_parts = [f"verdict={verdict}", f"hook=defender_guard.py"]
        if reason_lines:
            # Compact the reason for the receipt notes field (full payload is
            # in defender-guard.jsonl).
            short_reason = "; ".join(
                line.strip().lstrip("- ").lstrip()
                for line in (reason_lines or [])
                if line and line.strip()
            )[:400]
            if short_reason:
                notes_parts.append(f"reason={short_reason}")

        receipt = CommandReceipt(
            command=str(command_preview)[:800],
            parent_task=os.environ.get("CLAUDE_PARENT_TASK")
                        or os.environ.get("CLAUDE_SESSION_ID")
                        or "wave-pretooluse",
            agent=os.environ.get("CLAUDE_AGENT") or "diana-pretooluse",
            exit_code=exit_code,
            files_touched=[],
            network_attempted=False,
            # The guard FIRING is a Defender-class control surface, but
            # "defender_alert_observed" semantically means "Microsoft Defender
            # actually fired" — not "our policy guard fired." Keep False
            # unless pause_marker indicates an active alert.
            defender_alert_observed=False,
            pause_marker_state="none",  # auto-detected by emit_receipt
            notes=" | ".join(notes_parts),
        )
        # Stamp the tool_name into the receipt via a notes prefix so operator-
        # visible greps work (CommandReceipt schema is fixed by the AEP
        # package; we don't extend it here).
        receipt.notes = f"tool={tool_name} | {receipt.notes}"
        emit_receipt(receipt)
    except Exception:
        _emit_fallback_receipt(verdict, payload_summary, reason_lines)


def _emit_fallback_receipt(verdict, payload_summary, reason_lines):
    """Inline schema-conforming receipt write when the receipts module can't import."""
    try:
        import socket
        tool_name = (payload_summary or {}).get("tool_name") or "unknown"
        command_preview = (payload_summary or {}).get("command_preview") or ""
        receipt = {
            "command": str(command_preview)[:800],
            "parent_task": os.environ.get("CLAUDE_PARENT_TASK")
                          or os.environ.get("CLAUDE_SESSION_ID")
                          or "wave-pretooluse",
            "agent": os.environ.get("CLAUDE_AGENT") or "diana-pretooluse",
            "exit_code": 0 if verdict == "ALLOW" else 2,
            "files_touched": [],
            "network_attempted": False,
            "defender_alert_observed": False,
            "pause_marker_state": "none",
            "notes": f"tool={tool_name} | verdict={verdict} | hook=defender_guard.py | receipts-module-unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "hostname": socket.gethostname() if hasattr(socket, "gethostname") else "unknown",
        }
        receipts_path = _REPO_ROOT / ".claude" / "_logs" / "command-receipts.jsonl"
        receipts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(receipts_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def _extract_command_text(tool_name, tool_input):
    """Pull command-bearing fields out of any tool input shape.

    Per-tool scope (incident-remediation 2026-05-16):
      - Bash / shell tools: scan command/cmd/shell_command/script (these are
        actually executed in a shell — full pattern scan applies).
      - Task / Agent: scan prompt for natural-language argv patterns and
        explicit PS/mojibake — these become part of dispatched subagent context.
      - mcp__codex__codex / -reply: scan prompt/input/code for what's sent to
        Codex (which may execute it).
      - Edit / Write / MultiEdit: SCAN ONLY file_path. The file CONTENT is
        static data being placed on disk, not a command line being executed.
        Scanning content here would block all documentation/policy/source files
        that legitimately reference forbidden patterns (false-positive cascade).
        The DEFENDER ALERT STOPS BURN law (doctrine/68) covers content-level
        risk via separate authoring discipline; the guard's job is command-
        execution shape, not content prose.
    """
    fields = []
    if tool_input is None:
        return ""
    if isinstance(tool_input, str):
        return tool_input
    if not isinstance(tool_input, dict):
        return str(tool_input)

    tool = (tool_name or "").lower()

    if tool in ("edit", "write", "multiedit"):
        # Only scan the file_path. Block attempts to write into hook dirs or
        # other dangerous targets. Do NOT scan content.
        v = tool_input.get("file_path") or tool_input.get("filePath") or ""
        return str(v)

    if tool in ("bash",):
        for key in ("command", "cmd", "shell_command", "script", "args"):
            v = tool_input.get(key)
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                fields.append(" ".join(str(x) for x in v))
            else:
                fields.append(str(v))
        return " ".join(f for f in fields if f).strip()

    if tool in ("task", "agent"):
        for key in ("prompt", "input"):
            v = tool_input.get(key)
            if v is None:
                continue
            fields.append(str(v))
        return " ".join(f for f in fields if f).strip()

    if tool in ("mcp__codex__codex", "mcp__codex__codex-reply"):
        for key in ("prompt", "input", "code", "args"):
            v = tool_input.get(key)
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                fields.append(" ".join(str(x) for x in v))
            else:
                fields.append(str(v))
        return " ".join(f for f in fields if f).strip()

    # Unknown tool: scan command-bearing fields only.
    for key in ("command", "cmd", "prompt", "shell_command", "script", "code", "args"):
        v = tool_input.get(key)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            fields.append(" ".join(str(x) for x in v))
        else:
            fields.append(str(v))
    return " ".join(f for f in fields if f).strip()


def print_last_session_verdict():
    """SessionStart-hook compatible: surface the last receipt-validation verdict.

    Per BP-004-WRITE-ONLY-SUMMARY-RECURSION-1 + BP-004-VALIDATOR-FAIL-OPEN-IS-SILENT-1
    (adversary wave-004 falsifiers): the stop_receipt_validator.py output is
    appended to .claude/_logs/receipt-validation-reports.jsonl but nothing reads
    it at session-start. Validator-without-startup-readback is theater. This
    function closes the loop:

      - reads the LAST line of receipt-validation-reports.jsonl
      - parses verdict (CLEAN | YELLOW | RED | HOOK_ERROR)
      - CLEAN -> silent (exit 0; do not pollute operator session start)
      - YELLOW | RED | HOOK_ERROR -> prints concise summary to stderr (exit 0;
        SessionStart hooks should NOT block session resumption — surfacing is
        the contract, blocking is the operator's call)
      - File missing or empty -> silent (first-run / fresh-clone case)
      - JSON parse error on last line -> stderr warning only

    Wire via .claude/settings.json SessionStart hook with empty matcher.
    Composes with sibling-94 honest-framing: silent on CLEAN means the operator
    sees no noise when state is good, but YELLOW/RED gets surfaced loudly.
    """
    try:
        path = _REPO_ROOT / ".claude" / "_logs" / "receipt-validation-reports.jsonl"
        if not path.exists():
            return 0
        try:
            data = path.read_bytes()
        except Exception:
            return 0
        if not data.strip():
            return 0
        # Last non-empty line
        lines = [ln for ln in data.splitlines() if ln.strip()]
        if not lines:
            return 0
        last = lines[-1]
        try:
            rec = json.loads(last)
        except Exception as e:
            sys.stderr.write(
                f"\n[SessionStart] receipt-validation-reports.jsonl last line parse error: {type(e).__name__}\n"
            )
            sys.stderr.flush()
            return 0
        verdict = (rec.get("verdict") or "").upper()
        if verdict == "CLEAN":
            return 0
        if verdict in ("YELLOW", "RED", "HOOK_ERROR"):
            ts = rec.get("_emitted_at_utc") or rec.get("last_timestamp") or "?"
            session = rec.get("_session_id") or "?"
            tools = rec.get("by_tool") or {}
            tool_summary = ", ".join(f"{k}={v}" for k, v in tools.items()) or "no tool counts"
            red_flags = rec.get("red_flags") or []
            gaps = rec.get("gaps_detected") or []
            blocked = rec.get("blocked_tools_summary") or []
            sys.stderr.write(
                "\n"
                + "=" * 78 + "\n"
                + f"[SessionStart] LAST SESSION VERDICT: {verdict}\n"
                + f"  emitted_at: {ts}\n"
                + f"  session_id: {session}\n"
                + f"  tools: {tool_summary}\n"
                + f"  red_flags: {len(red_flags)} | gaps_detected: {len(gaps)} | blocked: {len(blocked)}\n"
                + f"  log_path: {path}\n"
                + "  Source: BP-004-WRITE-ONLY-SUMMARY-RECURSION-1 closure (forge wave-006).\n"
                + "  Action: review .claude/_logs/receipt-validation-reports.jsonl before dispatching new work.\n"
                + "=" * 78 + "\n"
            )
            sys.stderr.flush()
            return 0
        # Unknown verdict - surface as advisory
        sys.stderr.write(
            f"\n[SessionStart] LAST SESSION VERDICT: {verdict!r} (unknown class) — review {path}\n"
        )
        sys.stderr.flush()
        return 0
    except Exception:
        # Never let SessionStart-hook readback crash session resumption
        return 0


def _cli_check_doctrine_digest_and_exit():
    """CLI: `python .claude/hooks/defender_guard.py --check-doctrine-digest`.

    Prints a human-readable PASS/FAIL plus the canonical digest pair.
    Exits 0 on PASS, 1 on any non-PASS verdict. Informational only - does
    NOT call _emit_doctrine_digest_red_flag (CLI is a manual operator
    audit path; runtime drift handling happens in the main() hook path).
    """
    result = check_doctrine_digest()
    print(f"doctrine_digest_check verdict={result['verdict']}")
    print(f"  doctrine_path: {result['doctrine_path']}")
    print(f"  sha256_file:   {result['sha256_file']}")
    print(f"  computed:      {result.get('computed')}")
    print(f"  ratified:      {result.get('ratified')}")
    if result.get("ratified_meta"):
        print(f"  ratified_meta: {result['ratified_meta']}")
    if result["verdict"] == "PASS":
        return 0
    print("FAIL: doctrine/68 canonical body has drifted or the digest pair could not be read.")
    print("This is INFORMATIONAL - operators may legitimately amend doctrine and re-ratify.")
    print("To re-ratify after an authorized amendment, regenerate the .sha256 file with:")
    print("  python -c \"import hashlib,pathlib; p=pathlib.Path('doctrine/68-defender-alert-stops-burn.html'); print(hashlib.sha256(p.read_bytes()).hexdigest())\"")
    return 1


def main() -> int:
    # Wave-003 M4: check doctrine/68 digest once on each invocation BEFORE
    # processing the hook payload. Drift emits a RED-flag receipt + a
    # DOCTRINE_DRIFT_DETECTED record in defender-guard.jsonl. Never halts.
    try:
        if "--check-doctrine-digest" in sys.argv:
            return _cli_check_doctrine_digest_and_exit()
        if "--print-last-session-verdict" in sys.argv:
            return print_last_session_verdict()
        digest_result = check_doctrine_digest()
        if digest_result["verdict"] == "DOCTRINE_DRIFT_DETECTED":
            _emit_doctrine_digest_red_flag(digest_result)
    except Exception:
        # Digest check failures must never break the guard.
        pass

    try:
        raw = sys.stdin.read()
        if not raw.strip():
            _emit_allow({"reason": "empty-stdin", "tool_name": None})
            return 0
        try:
            payload = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            # If we can't parse, treat as suspicious. Fail CLOSED.
            reason = [
                "defender_guard: failed to parse hook JSON payload — failing closed.",
                f"  parse-error: {type(e).__name__}: {e}",
                "  See doctrine/68-defender-alert-stops-burn.html.",
            ]
            _emit_block(reason, {"raw_bytes": len(raw)})
            return 2

        tool_name = payload.get("tool_name") or payload.get("tool") or ""
        tool_input = payload.get("tool_input") or payload.get("input") or {}
        command_text = _extract_command_text(tool_name, tool_input)

        try:
            from security.command_safety import classify_command
        except Exception as e:  # noqa: BLE001
            reason = [
                "defender_guard: command_safety module failed to import — failing closed.",
                f"  import-error: {type(e).__name__}: {e}",
                "  Repair aep/security/command_safety.py before continuing.",
            ]
            _emit_block(reason, {"tool_name": tool_name})
            return 2

        result = classify_command(command_text)

        # ------------------------------------------------------------------
        # Per the agent-Wave-001 mid-wave finding 2026-05-17: Agent/Task tool
        # prompts are natural-language orchestration text routed to
        # subagents, NOT shell commands. The shell-argv blocklist
        # (PS-EXE-*, NL-ARGV-PROSE-RUN, ARGV-SECTION-MARKER, NL-ARGV-
        # POWERSHELL-PRETOOLUSE, NL-ARGV-PYTHON-VALIDATOR-PS) over-blocks
        # legitimate orchestration prose (negation mentions of forbidden
        # words, section markers, dash-bulleted prose lists). Subagents
        # have their own Bash-tool guard which fires at actual shell-
        # execution time — defense-in-depth holds. At the orchestration
        # layer we retain ONLY the categories valid for any-context:
        #   - mojibake (data-integrity signal; bad encoding is bad anywhere)
        #   - defender-tamper (instructions to subagents to tamper Defender)
        # Composes with sec68 DEFENDER ALERT STOPS BURN per-tool field
        # scoping principle: Bash full scan, Edit/Write file_path only,
        # Agent/Task = narrow scope (mojibake + defender-tamper only).
        # ------------------------------------------------------------------
        if (tool_name or "").lower() in ("task", "agent"):
            _AGENT_KEEP_CATEGORIES = ("mojibake", "defender-tamper")
            result.blocks = [
                b for b in result.blocks
                if b.get("category") in _AGENT_KEEP_CATEGORIES
            ]
            result.warnings = [
                w for w in result.warnings
                if w.get("category") in _AGENT_KEEP_CATEGORIES
            ]
            result.safe = (len(result.blocks) == 0)

        payload_summary = {
            "tool_name": tool_name,
            "command_preview": result.command_preview,
            "blocks": result.blocks,
            "warnings": result.warnings,
            "allowlisted": result.allowlisted,
        }

        if result.safe:
            _emit_allow(payload_summary)
            return 0

        reason_lines = [
            "defender_guard: command BLOCKED by command_safety policy.",
            f"  tool: {tool_name!r}",
            f"  preview: {result.command_preview!r}",
        ]
        for b in result.blocks:
            reason_lines.append(f"  [{b['id']} / {b['category']}] {b['reason']}")
            reason_lines.append(f"    matched: {b['match']!r}")
        reason_lines.append("  Policy: doctrine/68-defender-alert-stops-burn.html")
        reason_lines.append("  Remediate the calling site; do NOT add Defender exclusions.")
        _emit_block(reason_lines, payload_summary)
        return 2

    except Exception:  # noqa: BLE001 - last-resort fail-closed
        sys.stderr.write(
            "defender_guard: unhandled exception — failing closed.\n"
            + traceback.format_exc()
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
