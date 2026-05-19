#!/usr/bin/env python3
"""aep_prompt_contract.py - AEP v1.5 LTS UserPromptSubmit hook (K4 Deterministic Meaning Compiler).

Per operator v1.5 LTS Phase 2+3 directive: compile each user prompt into a
deterministic "task contract" capturing intent, scope, risk tier, forbidden
actions, success criteria, required evidence, token budget, output format,
and stop condition.

This hook is INFORMATIONAL ONLY (UserPromptSubmit is not a blocker in
Claude Code hooks docs). It always exits 0; its job is to write the contract
to the ledger for downstream Doctor verdicts + Stop-hook completion checks.

Per sec68 - Python only.
Per K4 - "deterministic" means same prompt -> same contract (with timestamp).
Per K10 - operator sovereignty preserved: contract does NOT rewrite operator
words; it merely extracts structured signal.

Target: <=700 tokens contract for complex prompts; <=250 for normal.
Performance target: p95 <= 200ms.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_LOG = _REPO_ROOT / ".claude" / "aep" / "transactions" / "prompt_contracts.jsonl"
_PERF_LOG = _REPO_ROOT / ".claude" / "aep" / "perf" / "userprompt_latency.jsonl"
_CONSTITUTION_PATH = _REPO_ROOT / ".claude" / "aep" / "constitution" / "aep_constitution_v1_5_lts.json"

# Risk-tier keyword maps (deterministic, lowercase match)
_CRITICAL_KEYWORDS = {
    "constitution", "settings.json", "rm -rf", "git push --force", "doctrine/68", "doctrine/69",
    "irreversible", "production", "payment", "money", "wire", "transfer", "medical",
    "legal advice", "release", "publish", "deploy",
}
_PROFESSIONAL_KEYWORDS = {
    "doctrine", "lesson", "promote", "canonical", "spec", "schema",
    "spawn", "/spawn", "warden", "curator", "scribe", "validator",
}
_IMPORTANT_KEYWORDS = {
    "agent", "subagent", "edit", "write", "implement", "build", "fix",
    "bash", "run", "execute", "create", "wire",
}

_BURN_REQUIRED_KEYWORDS = {
    "codex", "codex exec", "burn", "spark",
}

# Success-criteria extraction patterns
_SUCCESS_PATTERNS = [
    re.compile(r"\bmust\b\s+([^\.\n]+)", re.IGNORECASE),
    re.compile(r"\bshould\b\s+([^\.\n]+)", re.IGNORECASE),
    re.compile(r"\bevery\b\s+([^\.\n]+)", re.IGNORECASE),
    re.compile(r"\buntil\b\s+([^\.\n]+)", re.IGNORECASE),
    re.compile(r"\bensure\b\s+([^\.\n]+)", re.IGNORECASE),
]
_STOP_PATTERNS = [
    re.compile(r"\buntil\s+([^\.\n]+)", re.IGNORECASE),
    re.compile(r"\bwhen\s+([^\.\n]+\s+(?:done|complete|finished|works))", re.IGNORECASE),
]
_PATH_PATTERN = re.compile(r"[\.\w/\\-]+\.(?:py|js|ts|md|html|json|jsonl|yml|yaml|toml|aepkg|sh|ps1)", re.IGNORECASE)
_AGENT_PATTERN = re.compile(r"\b(strategist|pathfinder|scout|forge|judge|adversary|warden|scribe|curator|visual-judge)\b", re.IGNORECASE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_canonical(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _append_jsonl(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _load_constitution() -> dict:
    try:
        return json.loads(_CONSTITUTION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _classify_risk_tier(prompt: str) -> str:
    p = prompt.lower()
    for kw in _CRITICAL_KEYWORDS:
        if kw in p:
            return "Critical"
    for kw in _PROFESSIONAL_KEYWORDS:
        if kw in p:
            return "Professional"
    for kw in _IMPORTANT_KEYWORDS:
        if kw in p:
            return "Important"
    return "Casual"


def _extract_intent(prompt: str) -> str:
    """Pull a 1-sentence summary - first sentence ending in `.` or `!` or `?`,
    truncated to 240 chars."""
    s = prompt.strip()
    if not s:
        return ""
    # Find first sentence boundary
    m = re.search(r"[\.!?]\s", s)
    intent = s[: m.start() + 1] if m else s[:240]
    return intent[:240].replace("\n", " ").strip()


def _extract_scope(prompt: str) -> dict:
    paths = sorted(set(_PATH_PATTERN.findall(prompt)))[:32]
    agents = sorted(set(m.group(0).lower() for m in _AGENT_PATTERN.finditer(prompt)))
    return {"paths": paths, "agents": agents}


def _extract_success_criteria(prompt: str) -> list[str]:
    """Up to 12 normalized success-criteria phrases."""
    out = []
    seen = set()
    for pat in _SUCCESS_PATTERNS:
        for m in pat.finditer(prompt):
            phrase = m.group(1).strip()[:160]
            if phrase and phrase.lower() not in seen:
                seen.add(phrase.lower())
                out.append(phrase)
                if len(out) >= 12:
                    return out
    return out


def _extract_stop_condition(prompt: str) -> str:
    for pat in _STOP_PATTERNS:
        m = pat.search(prompt)
        if m:
            return m.group(1).strip()[:200]
    return ""


def _extract_forbidden(prompt: str, constitution: dict) -> list[str]:
    """Pull forbidden actions from constitution + any explicit "don't" patterns in prompt."""
    base = list(constitution.get("forbidden_actions", []))[:16]
    extras = []
    for pat in (r"don't\s+([^\.\n]+)", r"do not\s+([^\.\n]+)", r"never\s+([^\.\n]+)"):
        for m in re.finditer(pat, prompt, re.IGNORECASE):
            extras.append(("forbid: " + m.group(1).strip())[:200])
            if len(extras) >= 8:
                break
    return base + extras


def _extract_required_evidence(prompt: str) -> list[str]:
    out = []
    for kw in ("receipt", "witness", "sha256", "test", "validation", "smoke-test",
               "import smoke", "verify", "hcrl", "citation", "cite"):
        if kw in prompt.lower():
            out.append(kw)
    return out


def _token_estimate(s: str) -> int:
    # Heuristic: ~4 chars per token
    return max(1, len(s) // 4)


def _token_budget(risk_tier: str, constitution: dict) -> int:
    pb = constitution.get("proof_budgets", {})
    if risk_tier == "Critical":
        return int(pb.get("critical_max_token_overhead", 2400))
    if risk_tier == "Professional":
        return int(pb.get("professional_max_token_overhead", 1200))
    if risk_tier == "Important":
        return int(pb.get("important_max_token_overhead", 700))
    return int(pb.get("casual_max_token_overhead", 350))


def _extract_output_format(prompt: str) -> str:
    p = prompt.lower()
    if "1-screen summary" in p or "1 screen summary" in p or "one-screen" in p:
        return "one_screen_summary"
    if "file paths" in p and "summary" in p:
        return "file_paths_plus_summary"
    if "verdict" in p:
        return "verdict"
    if "json" in p and "row" in p:
        return "json_row"
    if "paste-ready" in p or "artifact-first" in p:
        return "artifact"
    return "prose"


def _operator_authority_invoked(prompt: str) -> bool:
    markers = (
        "go beyond all reasoning",
        "complete authority",
        "regardless of what adversary",
        "sec73.2",
        "operator-spec-sovereignty",
        "pull it off",
    )
    pl = prompt.lower()
    return any(m in pl for m in markers)


def _burn_required(prompt: str) -> bool:
    pl = prompt.lower()
    return any(k in pl for k in _BURN_REQUIRED_KEYWORDS)


def compile_contract(prompt: str, constitution: dict) -> dict:
    risk_tier = _classify_risk_tier(prompt)
    intent = _extract_intent(prompt)
    scope = _extract_scope(prompt)
    success_criteria = _extract_success_criteria(prompt)
    stop_condition = _extract_stop_condition(prompt)
    forbidden = _extract_forbidden(prompt, constitution)
    required_evidence = _extract_required_evidence(prompt)
    output_format = _extract_output_format(prompt)
    budget = _token_budget(risk_tier, constitution)

    contract = {
        "ts": _utc_now_iso(),
        "schema_version": "v1.5.0-lts",
        "prompt_sha256": _sha256_string(prompt),
        "prompt_token_estimate": _token_estimate(prompt),
        "intent": intent,
        "scope": scope,
        "risk_tier": risk_tier,
        "forbidden_actions": forbidden,
        "success_criteria": success_criteria,
        "required_evidence": required_evidence,
        "token_budget": budget,
        "output_format": output_format,
        "stop_condition": stop_condition,
        "operator_authority_invoked": _operator_authority_invoked(prompt),
        "burn_required": _burn_required(prompt),
    }
    contract["contract_sha256"] = _sha256_canonical({k: v for k, v in contract.items() if k != "contract_sha256"})
    return contract


def compile_first_turn_compact(prompt: str, constitution: dict) -> str:
    """FINAL PASS-CLOSURE GAP 2 (2026-05-18): compact first-turn contract emission.

    Emits ONLY the 7 required fields (intent / scope / risk_tier / success_criteria /
    forbidden_actions / token_budget / stop_condition) using 2-letter aliases. This
    is what gets injected into the LLM context window as the first-turn AEP contract
    overhead. Steady-state turns use the K7 cache-hit short form.

    Target: <=1200 tokens (<=4800 chars at ~4 chars/token).

    2-letter aliases (unambiguous in JSON context):
      in -> intent, sc -> scope, rt -> risk_tier, ok -> success_criteria,
      no -> forbidden_actions, tb -> token_budget, st -> stop_condition.

    Optional fields DROPPED from first-turn (available via full contract log):
      ts, schema_version, prompt_sha256, prompt_token_estimate, contract_sha256,
      required_evidence, output_format, operator_authority_invoked, burn_required.
    """
    risk_tier = _classify_risk_tier(prompt)
    intent = _extract_intent(prompt)
    scope = _extract_scope(prompt)
    success_criteria = _extract_success_criteria(prompt)
    stop_condition = _extract_stop_condition(prompt)
    forbidden = _extract_forbidden(prompt, constitution)
    budget = _token_budget(risk_tier, constitution)
    compact = {
        "in": intent,
        "sc": {"p": scope.get("paths", [])[:8], "a": scope.get("agents", [])[:6]},
        "rt": risk_tier,
        "ok": success_criteria[:6],
        "no": forbidden[:6],
        "tb": budget,
        "st": stop_condition,
    }
    return json.dumps(compact, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    t0 = time.perf_counter()
    # GAP 2 first-turn-payload mode: emit compact first-turn contract to stdout.
    # When invoked as `python aep_prompt_contract.py --first-turn-payload`, read prompt
    # from stdin (as JSON event or plain text), emit compact JSON to stdout, exit.
    if "--first-turn-payload" in sys.argv:
        try:
            raw = sys.stdin.read()
            prompt = ""
            if raw.strip():
                try:
                    ev = json.loads(raw)
                    prompt = ev.get("prompt") or ev.get("user_prompt") or ""
                except Exception:
                    prompt = raw
            constitution = _load_constitution()
            sys.stdout.write(compile_first_turn_compact(prompt, constitution))
            return 0
        except Exception as e:
            sys.stderr.write(f"[aep_prompt_contract:FIRST_TURN_ERR] {e}\n")
            return 0
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            _append_jsonl(_PERF_LOG, {
                "ts": _utc_now_iso(),
                "decision": "skip_no_event",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            })
            return 0
        event = json.loads(raw)
        prompt = event.get("prompt") or event.get("user_prompt") or ""
        if not isinstance(prompt, str):
            prompt = ""
        session_id = event.get("session_id") or event.get("sessionId") or ""

        constitution = _load_constitution()
        contract = compile_contract(prompt, constitution)
        contract["session_id"] = session_id

        _append_jsonl(_CONTRACT_LOG, contract)

        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "decision": "contract_compiled",
            "latency_ms": round(latency_ms, 3),
            "risk_tier": contract.get("risk_tier"),
            "prompt_token_estimate": contract.get("prompt_token_estimate"),
        })
        return 0
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "decision": "internal_error",
            "latency_ms": round(latency_ms, 3),
            "error_type": type(e).__name__,
        })
        # UserPromptSubmit isn't a blocker - exit 0 on any error.
        sys.stderr.write(f"[aep_prompt_contract:INTERNAL_ERROR] {type(e).__name__}: {e}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
