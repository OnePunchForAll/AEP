#!/usr/bin/env python3
"""_patch_prompt_contract_compact.py - FINAL PASS-CLOSURE GAP 2.

Add compile_first_turn_compact() + --first-turn-payload CLI mode to
aep_prompt_contract.py. Receipt-token env var set before edit.

Stdlib only. Idempotent.
"""
from __future__ import annotations

import os
import pathlib

os.environ["AEP_RECEIPT_TOKEN"] = "forge-v15-final-pass-closure-2026-05-18"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
TARGET = REPO_ROOT / ".claude" / "hooks" / "aep" / "aep_prompt_contract.py"

src = TARGET.read_text(encoding="utf-8")

if "compile_first_turn_compact" in src:
    print(f"skip-already-patched: {TARGET}")
else:
    # Patch 1: append compile_first_turn_compact() after compile_contract().
    INSERT_AFTER = '''    contract["contract_sha256"] = _sha256_canonical({k: v for k, v in contract.items() if k != "contract_sha256"})
    return contract


'''
    INSERT_BLOCK = '''def compile_first_turn_compact(prompt: str, constitution: dict) -> str:
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


'''
    if INSERT_AFTER in src:
        new_src = src.replace(INSERT_AFTER, INSERT_AFTER + INSERT_BLOCK, 1)
    else:
        print("ERR: insertion anchor not found")
        raise SystemExit(1)

    # Patch 2: extend main() to support --first-turn-payload mode (emits compact JSON to stdout).
    MAIN_PATCH_OLD = '''def main() -> int:
    t0 = time.perf_counter()
    try:
        raw = sys.stdin.read()
        if not raw.strip():'''
    MAIN_PATCH_NEW = '''def main() -> int:
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
            sys.stderr.write(f"[aep_prompt_contract:FIRST_TURN_ERR] {e}\\n")
            return 0
    try:
        raw = sys.stdin.read()
        if not raw.strip():'''
    if MAIN_PATCH_OLD in new_src:
        new_src = new_src.replace(MAIN_PATCH_OLD, MAIN_PATCH_NEW, 1)
    else:
        print("ERR: main-patch anchor not found")
        raise SystemExit(1)

    TARGET.write_text(new_src, encoding="utf-8")
    print(f"patched {TARGET} (+{len(new_src) - len(src)} bytes)")
