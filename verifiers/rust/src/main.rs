// AEP v0.8 F8 — Preflight Sandbox Capsule (PSC) verifier — Rust port.
// Wave-027 closure: pin_0007 PARTIAL → FULL execution-parity per operator
// complete-authority directive 2026-05-17 ("complete authority for every decision").
// Adds regex crate + unicode-normalization crate (8 transitive crates per Wave-022
// cargo-tree disclosure; all rust-lang/BurntSushi/unicode-rs maintained).
//
// Dependencies: serde_json + regex + unicode-normalization.

use regex::Regex;
use serde_json::Value;
use std::env;
use std::fs::File;
use std::io::{Read, Write};
use std::process;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};
use unicode_normalization::UnicodeNormalization;

const MAX_HEADER: usize = 65536;
const SCHEMA: &str = "aep-preflight-0.8";

// BAD_PATTERNS — byte-parity with Python pin_0001 + Node pin_0002 + Perl pin_0005 +
// TypeScript pin_0006 + Java pin_0008 BAD list (case-insensitive). Compiled once
// via OnceLock for thread-safe lazy init (no external deps; std::sync stable).
fn bad_patterns() -> &'static Vec<Regex> {
    static PATTERNS: OnceLock<Vec<Regex>> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        let raw = [
            r"(?i)\bignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions\b",
            r"(?i)\b(reveal|print|dump|exfiltrate)\s+(the\s+)?(system|developer|secret|token|key|env)\b",
            r"(?i)\b(run|execute|eval|subprocess|shell|powershell|cmd\.exe|bash)\b",
            r"(?i)\b(base64|rot13|unicode\s+homoglyph|zero[-\s]?width|hidden\s+instruction)\b",
            r"(?i)\b(remote\s+control|backdoor|trojan|persistence|credential|webhook)\b",
            r"(?i)\bhttp[s]?://|\bwww\.",
        ];
        raw.iter().map(|p| Regex::new(p).expect("BAD_PATTERN regex must compile")).collect()
    })
}

fn bankers_round3(x: f64) -> f64 {
    let factor = 1000.0_f64;
    let n = x * factor;
    let floor = n.floor();
    let diff = n - floor;
    let rounded = if (diff - 0.5).abs() < 1e-9 {
        if (floor as i64) % 2 == 0 { floor } else { floor + 1.0 }
    } else if diff < 0.5 { floor } else { floor + 1.0 };
    rounded / factor
}

fn clamp(v: &Value) -> f64 {
    let n = v.as_f64().unwrap_or(0.0);
    if !n.is_finite() { return 0.0; }
    if n < 0.0 { 0.0 } else if n > 1.0 { 1.0 } else { n }
}

fn emit(verdict: &str, reason: &str, packet_id: Option<&str>, hits: &[String], score: Option<f64>, exit_code: i32) {
    let pid = match packet_id {
        Some(p) => format!("\"{}\"", p),
        None => "null".to_string(),
    };
    let score_str = match score {
        Some(s) => format!("{}", s),
        None => "null".to_string(),
    };
    let hits_str: Vec<String> = hits.iter().map(|h| format!("\"{}\"", h.replace('\\', "\\\\").replace('"', "\\\""))).collect();
    let ts = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
    let out = format!(
        "{{\"verdict\":\"{}\",\"reason\":\"{}\",\"score\":{},\"hits\":[{}],\"packet_id\":{},\"ts\":{},\"verifier\":\"aep08_preflight_min_rs\"}}",
        verdict, reason, score_str, hits_str.join(","), pid, ts
    );
    println!("{}", out);
    let _ = std::io::stdout().flush();
    process::exit(exit_code);
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 {
        emit("USAGE", "preflight <aep-file>", None, &[], None, 2);
    }

    let mut buf = vec![0u8; MAX_HEADER + 1];
    let n_read = match File::open(&args[1]) {
        Ok(mut f) => f.read(&mut buf).unwrap_or(0),
        Err(e) => {
            emit("QUARANTINE", &format!("cannot_read:{}", e), None, &[], None, 2);
            return;
        }
    };
    buf.truncate(n_read);

    let end_marker = b"---END_AEP_PREFLIGHT---";
    if buf.len() > MAX_HEADER {
        let has_end = buf.windows(end_marker.len()).any(|w| w == end_marker);
        if !has_end {
            emit("QUARANTINE", "preflight_header_too_large_or_missing_end_marker", None, &[], None, 2);
        }
    }

    let text_raw = String::from_utf8_lossy(&buf).to_string();
    // Wave-027 closure: NFKC normalize via unicode-normalization crate.
    // Byte-parity with Python unicodedata.normalize('NFKC') / Node text.normalize('NFKC') /
    // Perl Unicode::Normalize::NFKC / Java Normalizer.Form.NFKC.
    let text: String = text_raw.nfkc().collect();

    let begin_idx = text.find("---BEGIN_AEP_PREFLIGHT---");
    let end_idx = text.find("---END_AEP_PREFLIGHT---");
    let (begin, end) = match (begin_idx, end_idx) {
        (Some(b), Some(e)) if b < e => (b, e),
        _ => { emit("QUARANTINE", "missing_preflight_capsule", None, &[], None, 2); return; }
    };
    let inner = &text[begin + "---BEGIN_AEP_PREFLIGHT---".len()..end];
    let json_start = inner.find('{').unwrap_or(0);
    let json_end = inner.rfind('}').map(|i| i + 1).unwrap_or(inner.len());
    let json_str = &inner[json_start..json_end];

    let o: Value = match serde_json::from_str(json_str) {
        Ok(v) => v,
        Err(e) => { emit("QUARANTINE", &format!("bad_preflight_json:{}", e.classify() as i32), None, &[], None, 2); return; }
    };

    let required = ["schema", "packet_id", "packet_sha256", "segments", "risk", "value_probe", "capabilities"];
    let missing: Vec<&str> = required.iter().filter(|k| o.get(**k).is_none()).copied().collect();
    let packet_id = o.get("packet_id").and_then(|v| v.as_str());
    if !missing.is_empty() {
        emit("QUARANTINE", &format!("missing_required:{}", missing.join(",")), packet_id, &[], None, 2);
    }

    if o.get("schema").and_then(|v| v.as_str()) != Some(SCHEMA) {
        emit("QUARANTINE", "schema_mismatch", packet_id, &[], None, 2);
    }

    let sha = o.get("packet_sha256").and_then(|v| v.as_str()).unwrap_or("");
    let sha_ok = sha == "UNKNOWN" || (sha.len() == 64 && sha.chars().all(|c| c.is_ascii_hexdigit()));
    if !sha_ok {
        emit("QUARANTINE", "bad_packet_sha256", packet_id, &[], None, 2);
    }
    // Wave-035 closure: strict packet_id regex matches Perl pin_0005 already-strict
    // closes atk-rtl-override-id Class-A divergence
    let pid_str = packet_id.unwrap_or("");
    let pid_ok = !pid_str.is_empty() && pid_str.len() <= 80 && pid_str.chars().all(|c|
        c.is_ascii_alphanumeric() || c == '_' || c == '.' || c == ':' || c == '-');
    if !pid_ok {
        emit("QUARANTINE", "bad_packet_id", packet_id, &[], None, 2);
    }

    let empty_map = serde_json::Map::new();
    let caps = o.get("capabilities").and_then(|v| v.as_object()).unwrap_or(&empty_map);
    for cap in ["network", "secrets", "write_host", "execute_packet_code"] {
        if caps.get(cap).and_then(|v| v.as_bool()).unwrap_or(false) {
            emit("BLOCK", "preflight_requested_forbidden_capability", packet_id, &[], None, 3);
        }
    }

    // Wave-027 closure: regex scan via regex crate. Byte-parity with Python re.search /
    // Node RegExp / Perl /.../ / Java Pattern.matcher / TS RegExp on the same 6 patterns.
    // Emit Python-style "(?i)..." hit format (matches Python pin_0001).
    let hits: Vec<String> = bad_patterns().iter()
        .filter(|p| p.is_match(&text))
        .map(|p| p.as_str().to_string())
        .collect();

    let segs = match o.get("segments").and_then(|v| v.as_array()) {
        Some(s) if !s.is_empty() => s,
        _ => { emit("QUARANTINE", "segments_not_nonempty_list", packet_id, &hits, None, 2); return; }
    };

    for (i, s) in segs.iter().take(256).enumerate() {
        let so = match s.as_object() {
            Some(o) => o,
            None => { emit("QUARANTINE", &format!("segment_{}_not_object", i), packet_id, &hits, None, 2); return; }
        };
        for k in ["id", "kind", "offset", "length", "sha256", "utility", "risk"] {
            if so.get(k).is_none() {
                emit("QUARANTINE", &format!("segment_{}_missing_{}", i, k), packet_id, &hits, None, 2);
            }
        }
    }

    let empty_vp = serde_json::Map::new();
    let vp = o.get("value_probe").and_then(|v| v.as_object()).unwrap_or(&empty_vp);
    let rk = o.get("risk").and_then(|v| v.as_object()).unwrap_or(&empty_vp);
    let v_def = Value::Null;
    let value = 0.30 * clamp(vp.get("evidence_density").unwrap_or(&v_def))
              + 0.20 * clamp(vp.get("implementation_ready").unwrap_or(&v_def))
              + 0.20 * clamp(vp.get("cross_corpus_fit").unwrap_or(&v_def))
              + 0.15 * clamp(vp.get("novelty").unwrap_or(&v_def))
              + 0.15 * clamp(vp.get("validation_ready").unwrap_or(&v_def));
    let risk = 0.35 * clamp(rk.get("prompt_injection").unwrap_or(&v_def))
             + 0.25 * clamp(rk.get("supply_chain").unwrap_or(&v_def))
             + 0.20 * clamp(rk.get("execution").unwrap_or(&v_def))
             + 0.10 * clamp(rk.get("secrets").unwrap_or(&v_def))
             + 0.10 * clamp(rk.get("cost_dos").unwrap_or(&v_def))
             + (0.05 * hits.len() as f64).min(0.25);
    let score = bankers_round3(value - risk);

    if !hits.is_empty() && risk >= 0.55 {
        emit("QUARANTINE", "adversary_hits_high_risk", packet_id, &hits, Some(score), 2);
    }
    if risk >= 0.75 {
        emit("BLOCK", "risk_threshold", packet_id, &hits, Some(score), 3);
    }
    if score >= 0.25 && value >= 0.55 {
        emit("ALLOW_FULL_RETRIEVE", "value_probe_passed_no_exec", packet_id, &hits, Some(score), 0);
    }
    emit("HEADER_ONLY", "insufficient_value_or_elevated_risk", packet_id, &hits, Some(score), 0);
}
