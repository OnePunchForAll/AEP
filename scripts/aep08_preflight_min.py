#!/usr/bin/env python3
# AEP v0.8 F8 — Preflight Sandbox Capsule (PSC) verifier — minified reference impl.
#
# Authored 2026-05-17 by external-Claude-session-acting-as-F3-validator (ChatGPT,
# operator-initiated session) under State-of-the-Forge §07 P2-3 spirit. Landed
# into AEP project substrate by Claude-Code-the agent 2026-05-17 as the canonical
# trusted-local-verifier per §V80-8-ter F8.
#
# DEFENSIVE INVARIANTS (load-bearing per F8 + §69):
#   1. This verifier NEVER executes packet code.
#   2. This verifier NEVER follows packet instructions.
#   3. This verifier reads only the first ≤64KB of any AEP file (header capsule).
#   4. Packet text is data, never instruction.
#   5. ALLOW_FULL_RETRIEVE permits retrieving the rest of the packet — NOT obeying it.
#   6. Forbidden preflight capabilities (network, secrets, write_host, execute_packet_code)
#      cause immediate BLOCK regardless of other signals.
#
# Trust root: this file. Hash-pin it; never run a verifier supplied only by an untrusted packet.
# AEP project-internal companion: validate_v0_8.py runs ONLY after this returns ALLOW_FULL_RETRIEVE
# or HEADER_ONLY. Receipts land in `.claude/_logs/aep-preflight-receipts.jsonl` (warden owns).
#
# Composes with: §V80-8-ter F8 Preflight Sandbox Capsule SPEC; §69 Verification Law;
# §70 Surface Mirror Discipline; §71 Operator Sustainability; §41 HCRL receipts.
#
# Stdlib only (per §68 spirit): json, re, hashlib, unicodedata, time, sys.
# No network. No subprocess. No shell. No filesystem writes (verdict goes to stdout).

import sys, json, re, hashlib, unicodedata, time
MAX_HEADER = 65536
SCHEMA = "aep-preflight-0.8"
BAD = [
    r"(?i)\bignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions\b",
    r"(?i)\b(reveal|print|dump|exfiltrate)\s+(the\s+)?(system|developer|secret|token|key|env)\b",
    r"(?i)\b(run|execute|eval|subprocess|shell|powershell|cmd\.exe|bash)\b",
    r"(?i)\b(base64|rot13|unicode\s+homoglyph|zero[-\s]?width|hidden\s+instruction)\b",
    r"(?i)\b(remote\s+control|backdoor|trojan|persistence|credential|webhook)\b",
    r"(?i)\bhttp[s]?://|\bwww\.",
]
def out(verdict, reason, obj=None, hits=None, score=None, exit_code=0):
    print(json.dumps({
        "verdict": verdict, "reason": reason, "score": score,
        "hits": hits or [], "packet_id": (obj or {}).get("packet_id"),
        "ts": int(time.time()), "verifier": "aep08_preflight_min_py"
    }, separators=(",", ":")))
    sys.exit(exit_code)
def clamp(x, lo=0.0, hi=1.0):
    try: x = float(x)
    except Exception: return lo
    return max(lo, min(hi, x))
def main():
    if len(sys.argv) != 2:
        out("USAGE", "aep08_preflight_min.py <aep-file>", exit_code=2)
    try:
        with open(sys.argv[1], "rb") as f:
            raw = f.read(MAX_HEADER + 1)
    except Exception as e:
        out("QUARANTINE", "cannot_read:" + type(e).__name__, exit_code=2)
    if len(raw) > MAX_HEADER and b"---END_AEP_PREFLIGHT---" not in raw:
        out("QUARANTINE", "preflight_header_too_large_or_missing_end_marker", exit_code=2)
    text = unicodedata.normalize("NFKC", raw.decode("utf-8", "replace"))
    m = re.search(r"---BEGIN_AEP_PREFLIGHT---\s*(\{.*?\})\s*---END_AEP_PREFLIGHT---", text, re.S)
    if not m:
        out("QUARANTINE", "missing_preflight_capsule", exit_code=2)
    try:
        o = json.loads(m.group(1))
    except Exception as e:
        out("QUARANTINE", "bad_preflight_json:" + type(e).__name__, exit_code=2)
    req = ["schema", "packet_id", "packet_sha256", "segments", "risk", "value_probe", "capabilities"]
    miss = [k for k in req if k not in o]
    if miss:
        out("QUARANTINE", "missing_required:" + ",".join(miss), o, exit_code=2)
    if o.get("schema") != SCHEMA:
        out("QUARANTINE", "schema_mismatch", o, exit_code=2)
    if not re.fullmatch(r"[a-fA-F0-9]{64}|UNKNOWN", str(o.get("packet_sha256", ""))):
        out("QUARANTINE", "bad_packet_sha256", o, exit_code=2)
    # Wave-035 closure: strict packet_id validation matches segment-id regex
    # (per Perl pin_0005 already strict-validates; atk-rtl-override-id fixture
    # contains U+202E in packet_id which fails this regex → QUARANTINE).
    # Empirical fix: 6/7 verifiers previously ALLOWed RTL spoof; post-Wave-035
    # all 7 unanimously QUARANTINE → quorum BLOCK with divergence_class=none.
    if not re.fullmatch(r"[A-Za-z0-9_.:\-]{1,80}", str(o.get("packet_id", ""))):
        out("QUARANTINE", "bad_packet_id", o, exit_code=2)
    caps = o.get("capabilities") or {}
    if any(bool(caps.get(k)) for k in ("network", "secrets", "write_host", "execute_packet_code")):
        out("BLOCK", "preflight_requested_forbidden_capability", o, exit_code=3)
    hits = []
    for p in BAD:
        if re.search(p, text): hits.append(p)
    segs = o.get("segments")
    if not isinstance(segs, list) or not segs:
        out("QUARANTINE", "segments_not_nonempty_list", o, hits, exit_code=2)
    for i, s in enumerate(segs[:256]):
        if not isinstance(s, dict):
            out("QUARANTINE", f"segment_{i}_not_object", o, hits, exit_code=2)
        for k in ("id", "kind", "offset", "length", "sha256", "utility", "risk"):
            if k not in s: out("QUARANTINE", f"segment_{i}_missing_{k}", o, hits, exit_code=2)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", str(s["id"])):
            out("QUARANTINE", f"segment_{i}_bad_id", o, hits, exit_code=2)
        try:
            off, ln = int(s["offset"]), int(s["length"])
            if off < 0 or ln < 0 or ln > 1048576: raise ValueError()
        except Exception:
            out("QUARANTINE", f"segment_{i}_bad_bounds", o, hits, exit_code=2)
        if not re.fullmatch(r"[a-fA-F0-9]{64}|UNKNOWN", str(s["sha256"])):
            out("QUARANTINE", f"segment_{i}_bad_sha256", o, hits, exit_code=2)
    vp, rk = o.get("value_probe") or {}, o.get("risk") or {}
    value = (0.30*clamp(vp.get("evidence_density")) + 0.20*clamp(vp.get("implementation_ready")) +
             0.20*clamp(vp.get("cross_corpus_fit")) + 0.15*clamp(vp.get("novelty")) +
             0.15*clamp(vp.get("validation_ready")))
    risk = (0.35*clamp(rk.get("prompt_injection")) + 0.25*clamp(rk.get("supply_chain")) +
            0.20*clamp(rk.get("execution")) + 0.10*clamp(rk.get("secrets")) +
            0.10*clamp(rk.get("cost_dos")) + min(0.25, 0.05*len(hits)))
    score = round(value - risk, 3)
    if hits and risk >= 0.55:
        out("QUARANTINE", "adversary_hits_high_risk", o, hits, score, 2)
    if risk >= 0.75:
        out("BLOCK", "risk_threshold", o, hits, score, 3)
    if score >= 0.25 and value >= 0.55:
        out("ALLOW_FULL_RETRIEVE", "value_probe_passed_no_exec", o, hits, score, 0)
    out("HEADER_ONLY", "insufficient_value_or_elevated_risk", o, hits, score, 0)
if __name__ == "__main__":
    main()
