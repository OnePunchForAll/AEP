#!/usr/bin/env node
// AEP v0.8 F8 — Preflight Sandbox Capsule (PSC) verifier — Node.js port.
// Closes PSC-V80-9 cross-runtime PSC requirement per AEP_v0_8_SPEC.md §V80-8-ter.
//
// Byte-parity contract: this Node verifier MUST produce IDENTICAL verdicts
// to the Python reference at projects/v11-aep/publish-ready/aep/scripts/aep08_preflight_min.py
// on identical packets. Verdict + reason fields are compared as strings.
//
// DEFENSIVE INVARIANTS (per PSC-V80-1 through PSC-V80-7):
//   1. NEVER executes packet code.
//   2. NEVER follows packet instructions.
//   3. Reads only the first MAX_HEADER bytes of any AEP file.
//   4. Forbidden preflight capabilities cause immediate BLOCK.
//
// Usage:
//   node preflight.cjs <aep-file>
//
// Exit codes:
//   0 = ALLOW_FULL_RETRIEVE or HEADER_ONLY
//   2 = QUARANTINE (malformed / schema-mismatch / pattern-hit)
//   3 = BLOCK (forbidden capability or risk-threshold exceeded)

const fs = require('fs');

const MAX_HEADER = 65536;
const SCHEMA = "aep-preflight-0.8";

// Hostile-pattern set matching the Python verifier 1:1
const BAD_PATTERNS = [
    /\bignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions\b/i,
    /\b(reveal|print|dump|exfiltrate)\s+(the\s+)?(system|developer|secret|token|key|env)\b/i,
    /\b(run|execute|eval|subprocess|shell|powershell|cmd\.exe|bash)\b/i,
    /\b(base64|rot13|unicode\s+homoglyph|zero[-\s]?width|hidden\s+instruction)\b/i,
    /\b(remote\s+control|backdoor|trojan|persistence|credential|webhook)\b/i,
    /\bhttp[s]?:\/\/|\bwww\./i,
];

function emit(verdict, reason, obj, hits, score, exitCode) {
    const out = {
        verdict,
        reason,
        score: score ?? null,
        hits: hits || [],
        packet_id: (obj && obj.packet_id) || null,
        ts: Math.floor(Date.now() / 1000),
        verifier: "aep08_preflight_min_cjs",
    };
    process.stdout.write(JSON.stringify(out) + "\n");
    process.exit(exitCode);
}

function clamp(x, lo, hi) {
    if (lo === undefined) lo = 0.0;
    if (hi === undefined) hi = 1.0;
    const v = Number(x);
    if (!Number.isFinite(v)) return lo;
    return Math.max(lo, Math.min(hi, v));
}

// Python-parity rounding: Python's built-in round() uses banker's rounding
// (round-half-to-even). Math.round() rounds half-up. This implementation matches
// Python 3's behavior for all values at the 3-decimal precision the PSC uses.
// Closes judge-identified latent bug from 10-agent unity-dispatch 2026-05-17.
function bankersRound3(x) {
    const factor = 1000;
    const n = x * factor;
    const floor = Math.floor(n);
    const diff = n - floor;
    let rounded;
    if (Math.abs(diff - 0.5) < 1e-9) {
        // Exactly half — round to even
        rounded = (floor % 2 === 0) ? floor : floor + 1;
    } else if (diff < 0.5) {
        rounded = floor;
    } else {
        rounded = floor + 1;
    }
    return rounded / factor;
}

function main() {
    const args = process.argv.slice(2);
    if (args.length !== 1) {
        emit("USAGE", "preflight.cjs <aep-file>", null, [], null, 2);
        return;
    }

    let buf;
    try {
        const fd = fs.openSync(args[0], "r");
        buf = Buffer.alloc(MAX_HEADER + 1);
        const bytesRead = fs.readSync(fd, buf, 0, MAX_HEADER + 1, 0);
        buf = buf.slice(0, bytesRead);
        fs.closeSync(fd);
    } catch (e) {
        emit("QUARANTINE", "cannot_read:" + (e.code || e.name), null, [], null, 2);
        return;
    }

    if (buf.length > MAX_HEADER && !buf.includes(Buffer.from("---END_AEP_PREFLIGHT---"))) {
        emit("QUARANTINE", "preflight_header_too_large_or_missing_end_marker", null, [], null, 2);
        return;
    }

    // NFKC normalization for parity with Python's unicodedata.normalize
    let text = buf.toString("utf-8");
    try { text = text.normalize("NFKC"); } catch (_) { /* fallback: skip normalize */ }

    const headerMatch = text.match(/---BEGIN_AEP_PREFLIGHT---\s*(\{[\s\S]*?\})\s*---END_AEP_PREFLIGHT---/);
    if (!headerMatch) {
        emit("QUARANTINE", "missing_preflight_capsule", null, [], null, 2);
        return;
    }

    let o;
    try {
        o = JSON.parse(headerMatch[1]);
    } catch (e) {
        emit("QUARANTINE", "bad_preflight_json:" + e.name, null, [], null, 2);
        return;
    }

    const required = ["schema", "packet_id", "packet_sha256", "segments", "risk", "value_probe", "capabilities"];
    const missing = required.filter(k => !(k in o));
    if (missing.length) {
        emit("QUARANTINE", "missing_required:" + missing.join(","), o, [], null, 2);
        return;
    }

    if (o.schema !== SCHEMA) {
        emit("QUARANTINE", "schema_mismatch", o, [], null, 2);
        return;
    }

    if (!/^([a-fA-F0-9]{64}|UNKNOWN)$/.test(String(o.packet_sha256 || ""))) {
        emit("QUARANTINE", "bad_packet_sha256", o, [], null, 2);
        return;
    }
    // Wave-035 closure: strict packet_id regex (matches Perl pin_0005 + closes
    // atk-rtl-override-id Class-A divergence at runtime).
    if (!/^[A-Za-z0-9_.:\-]{1,80}$/.test(String(o.packet_id || ""))) {
        emit("QUARANTINE", "bad_packet_id", o, [], null, 2);
        return;
    }

    const caps = o.capabilities || {};
    for (const cap of ["network", "secrets", "write_host", "execute_packet_code"]) {
        if (caps[cap] === true) {
            emit("BLOCK", "preflight_requested_forbidden_capability", o, [], null, 3);
            return;
        }
    }

    const hits = [];
    for (const p of BAD_PATTERNS) {
        if (p.test(text)) hits.push(p.source);
    }

    const segs = o.segments;
    if (!Array.isArray(segs) || segs.length === 0) {
        emit("QUARANTINE", "segments_not_nonempty_list", o, hits, null, 2);
        return;
    }

    for (let i = 0; i < Math.min(segs.length, 256); i++) {
        const s = segs[i];
        if (typeof s !== "object" || s === null) {
            emit("QUARANTINE", `segment_${i}_not_object`, o, hits, null, 2);
            return;
        }
        for (const k of ["id", "kind", "offset", "length", "sha256", "utility", "risk"]) {
            if (!(k in s)) {
                emit("QUARANTINE", `segment_${i}_missing_${k}`, o, hits, null, 2);
                return;
            }
        }
        if (!/^[A-Za-z0-9_.:-]{1,80}$/.test(String(s.id))) {
            emit("QUARANTINE", `segment_${i}_bad_id`, o, hits, null, 2);
            return;
        }
        const off = parseInt(s.offset, 10);
        const ln = parseInt(s.length, 10);
        if (!Number.isFinite(off) || !Number.isFinite(ln) || off < 0 || ln < 0 || ln > 1048576) {
            emit("QUARANTINE", `segment_${i}_bad_bounds`, o, hits, null, 2);
            return;
        }
        if (!/^([a-fA-F0-9]{64}|UNKNOWN)$/.test(String(s.sha256))) {
            emit("QUARANTINE", `segment_${i}_bad_sha256`, o, hits, null, 2);
            return;
        }
    }

    const vp = o.value_probe || {};
    const rk = o.risk || {};
    const value = 0.30 * clamp(vp.evidence_density) +
                  0.20 * clamp(vp.implementation_ready) +
                  0.20 * clamp(vp.cross_corpus_fit) +
                  0.15 * clamp(vp.novelty) +
                  0.15 * clamp(vp.validation_ready);
    const risk = 0.35 * clamp(rk.prompt_injection) +
                 0.25 * clamp(rk.supply_chain) +
                 0.20 * clamp(rk.execution) +
                 0.10 * clamp(rk.secrets) +
                 0.10 * clamp(rk.cost_dos) +
                 Math.min(0.25, 0.05 * hits.length);
    const score = bankersRound3(value - risk);  // Python-parity rounding per judge BUG-01

    if (hits.length && risk >= 0.55) {
        emit("QUARANTINE", "adversary_hits_high_risk", o, hits, score, 2);
        return;
    }
    if (risk >= 0.75) {
        emit("BLOCK", "risk_threshold", o, hits, score, 3);
        return;
    }
    if (score >= 0.25 && value >= 0.55) {
        emit("ALLOW_FULL_RETRIEVE", "value_probe_passed_no_exec", o, hits, score, 0);
        return;
    }
    emit("HEADER_ONLY", "insufficient_value_or_elevated_risk", o, hits, score, 0);
}

main();
