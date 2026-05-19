#!/usr/bin/env node
/**
 * aep_doctor_node.js - K12 AEP Doctor (Node port)
 *
 * Cross-runtime byte-parity sibling of aep_doctor_supreme.py.
 *
 * Mirrors Python doctor verdict logic for v1.5 LTS Phase A pass-chase:
 *   - 7 verdicts: PASS / WARN / FAIL / UNKNOWN / EXPIRED / CONTESTED / QUARANTINED
 *   - Precedence: QUARANTINED > CONTESTED > EXPIRED > FAIL > WARN > PASS
 *   - Same signal thresholds + same block_reason_id mapping
 *
 * Composes with:
 *   - F9 cross-substrate quorum (Python + Node + Perl)
 *   - sec73.4 single-forge ONE coherent product (this dispatch)
 *   - sec73.5 WARDEN RECEIPTS chain
 *
 * Truth tag: STRONGLY PLAUSIBLE (byte-parity proven against Python on 10
 * canonical fixtures this turn; v1.5.1 will widen to 1000-packet corpus).
 *
 * CLI:
 *   node aep_doctor_node.js <packet>
 *   node aep_doctor_node.js <packet> --json
 *   node aep_doctor_node.js <packet> --no-cache
 *
 * Stdin/stdout protocol matches Python sibling: --json --no-cache --quiet
 * emits the same verdict record shape.
 *
 * Stdlib only - no npm dependencies (uses node:fs / node:crypto / node:path).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const process = require('node:process');

// ---------- Constants ----------
const VERDICT = {
  PASS: 'PASS',
  WARN: 'WARN',
  FAIL: 'FAIL',
  UNKNOWN: 'UNKNOWN',
  EXPIRED: 'EXPIRED',
  CONTESTED: 'CONTESTED',
  QUARANTINED: 'QUARANTINED',
};

const F18_LAUNDERING_FAIL_THRESHOLD = 0.8;
const F18_LAUNDERING_WARN_THRESHOLD = 0.6;

const IRREVERSIBLE_ACTION_CLASSES = new Set([
  'financial', 'medical', 'legal', 'employment', 'housing', 'irreversible',
]);

const TRUST_DIAL_RECOMMENDATION = {
  general: 'Casual',
  financial: 'Professional',
  medical: 'Professional',
  legal: 'Professional',
  employment: 'Professional',
  housing: 'Professional',
  irreversible: 'Professional',
};

const DOCTOR_VERSION = 'v1.5.0-lts-node';

// ---------- Helpers ----------
function sha256OfBuffer(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

function nowIsoUtc() {
  return new Date().toISOString().replace('.000Z', 'Z');
}

function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) return [];
  const text = fs.readFileSync(filePath, 'utf-8');
  const rows = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      rows.push(JSON.parse(trimmed));
    } catch (e) {
      // skip malformed line
    }
  }
  return rows;
}

function safeReadText(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf-8');
  } catch (e) {
    return '';
  }
}

function isFile(p) {
  try { return fs.statSync(p).isFile(); } catch (e) { return false; }
}

function isDir(p) {
  try { return fs.statSync(p).isDirectory(); } catch (e) { return false; }
}

function exists(p) {
  try { fs.statSync(p); return true; } catch (e) { return false; }
}

// ---------- Packet parse check ----------
function packetIsParseable(packetPath) {
  if (!exists(packetPath)) return [false, `Path does not exist: ${packetPath}`];
  if (isFile(packetPath)) {
    if (packetPath.endsWith('.json')) return [true, 'single-file packet'];
    return [false, `Path is a file but not a JSON file: ${packetPath}`];
  }
  const hasAepkg = isFile(path.join(packetPath, 'aepkg.json'));
  const hasClaim = isFile(path.join(packetPath, 'claim.json'));
  const hasClaimsJsonl = isFile(path.join(packetPath, 'data', 'claims.jsonl'));
  const hasSourcesJsonl = isFile(path.join(packetPath, 'data', 'sources.jsonl'));
  if (hasAepkg || hasClaim || hasClaimsJsonl || hasSourcesJsonl) {
    return [true, 'packet structure detected'];
  }
  return [false, 'no aepkg.json / claim.json / data/*.jsonl found'];
}

// ---------- Signal extractors ----------
//
// MIRRORS Python build_f22_civilian_proof_card.extract_signals_from_packet
// exactly: read pre-computed signal files at data/f18_provenance.json,
// data/f15_witness.json, data/f16_attacks.json, data/f19_coverage.json,
// data/a8_srs_decay.json. Default to clean if absent. This is the load-bearing
// behavior the Python sibling has shipped; cross-runtime byte-parity REQUIRES
// the Node + Perl ports to inherit this exact logic, NOT invent new inference.

function readJsonSafe(filePath) {
  if (!isFile(filePath)) return null;
  try { return JSON.parse(fs.readFileSync(filePath, 'utf-8')); } catch (e) { return null; }
}

function extractSignals(packetDir) {
  // Default-clean signal baseline (mirrors Python f22 lines 184-207)
  const sigs = {
    f18_laundering_score: {
      score: 0.0,
      threshold_breached: false,
      civilian_phrasing: 'Source provenance: direct sources.',
    },
    f15_missing_witness_flag: {
      any_criterion_missing_witness: false,
      count: 0,
    },
    f16_attack_flag: {
      any_attack_class_present: false,
      count: 0,
    },
    f19_coverage_gap_flag: {
      any_corpus_gap_detected: false,
      count: 0,
    },
    a8_srs_decay_status: {
      any_claim_decayed: false,
      count: 0,
    },
    any_signal_non_ok: false,
  };

  // F18 laundering (data/f18_provenance.json)
  const f18 = readJsonSafe(path.join(packetDir, 'data', 'f18_provenance.json'));
  if (f18 && typeof f18 === 'object') {
    const score = Number(f18.laundering_score || 0);
    sigs.f18_laundering_score.score = Math.round(score * 10000) / 10000;
    sigs.f18_laundering_score.threshold_breached = score >= 0.6;
    if (score >= 0.6) {
      sigs.f18_laundering_score.civilian_phrasing =
        'Source provenance: HIGH-RISK (most evidence is AI-derived). ' +
        'This may be AI making things up about itself.';
    } else if (score >= 0.4) {
      sigs.f18_laundering_score.civilian_phrasing =
        'Source provenance: medium (some evidence is paraphrased).';
    }
  }

  // F15 missing witness (data/f15_witness.json)
  const f15 = readJsonSafe(path.join(packetDir, 'data', 'f15_witness.json'));
  if (f15 && typeof f15 === 'object') {
    const miss = parseInt(f15.missing_witness_count || 0, 10);
    sigs.f15_missing_witness_flag.count = miss;
    sigs.f15_missing_witness_flag.any_criterion_missing_witness = miss > 0;
    if (miss > 0) {
      sigs.f15_missing_witness_flag.civilian_phrasing =
        `Hidden completion gap detected: ${miss} expected check(s) missing.`;
    }
  }

  // F16 attack flag (data/f16_attacks.json)
  const f16 = readJsonSafe(path.join(packetDir, 'data', 'f16_attacks.json'));
  if (f16 && typeof f16 === 'object') {
    const cnt = parseInt(f16.attack_count || 0, 10);
    sigs.f16_attack_flag.count = cnt;
    sigs.f16_attack_flag.any_attack_class_present = cnt > 0;
    if (cnt > 0) {
      sigs.f16_attack_flag.civilian_phrasing =
        `${cnt} known attack pattern(s) flagged against this packet.`;
    }
  }

  // F19 coverage gap (data/f19_coverage.json)
  const f19 = readJsonSafe(path.join(packetDir, 'data', 'f19_coverage.json'));
  if (f19 && typeof f19 === 'object') {
    const gaps = parseInt(f19.coverage_gap_count || 0, 10);
    sigs.f19_coverage_gap_flag.count = gaps;
    sigs.f19_coverage_gap_flag.any_corpus_gap_detected = gaps > 0;
    if (gaps > 0) {
      const expected = parseInt(f19.expected_count || gaps, 10);
      sigs.f19_coverage_gap_flag.civilian_phrasing =
        `Skipped scope: ${gaps} of ${expected} expected packets not covered.`;
    }
  }

  // A8 SRS decay (data/a8_srs_decay.json)
  const a8 = readJsonSafe(path.join(packetDir, 'data', 'a8_srs_decay.json'));
  if (a8 && typeof a8 === 'object') {
    const dec = parseInt(a8.decayed_claim_count || 0, 10);
    sigs.a8_srs_decay_status.count = dec;
    sigs.a8_srs_decay_status.any_claim_decayed = dec > 0;
    if (dec > 0) {
      sigs.a8_srs_decay_status.civilian_phrasing =
        `${dec} claim(s) are stale (last reviewed >90 days ago).`;
    }
  }

  sigs.any_signal_non_ok = !!(
    sigs.f18_laundering_score.threshold_breached ||
    sigs.f15_missing_witness_flag.any_criterion_missing_witness ||
    sigs.f16_attack_flag.any_attack_class_present ||
    sigs.f19_coverage_gap_flag.any_corpus_gap_detected ||
    sigs.a8_srs_decay_status.any_claim_decayed
  );
  return sigs;
}

// ---------- v1.5 detectors ----------
function detectQuarantined(packetDir) {
  const violations = [];
  let reason = '';
  const claimPath = path.join(packetDir, 'claim.json');
  if (isFile(claimPath)) {
    try {
      const c = JSON.parse(safeReadText(claimPath));
      if (c && c.quarantined === true) {
        violations.push('claim.json quarantined=true');
        reason = 'claim.quarantined explicit flag';
      }
    } catch (e) { /* skip */ }
  }
  // Scan up to 200 files for forbidden patterns (matches Python's rglob+suffix filter)
  const forbiddenPatterns = [
    'FORBIDDEN_ACTION_DETECTED',
    'SECRET_AIRLOCK_BREACH',
    'policy_violation:true',
    'sandbox_escape',
    'powershell_hook_attempt',
  ];
  const visited = walkPacketTextFiles(packetDir, 200);
  for (const fp of visited) {
    const text = safeReadText(fp);
    if (!text) continue;
    for (const pat of forbiddenPatterns) {
      if (text.includes(pat)) {
        const rel = path.relative(packetDir, fp).replace(/\\/g, '/');
        violations.push(`${pat} in ${rel}`);
        if (!reason) reason = pat;
        break;
      }
    }
    if (violations.length > 0 && violations[violations.length - 1].includes('in ')) break;
  }
  return { is: violations.length > 0, reason, violations };
}

function detectContested(packetDir) {
  const evidence = [];
  let reason = '';
  if (exists(path.join(packetDir, '.merge_conflict'))) {
    evidence.push('.merge_conflict marker present');
    reason = 'merge-conflict marker file';
  }
  const claimPath = path.join(packetDir, 'claim.json');
  if (isFile(claimPath)) {
    try {
      const c = JSON.parse(safeReadText(claimPath));
      if (c && c.contested === true) {
        evidence.push('claim.json contested=true');
        if (!reason) reason = 'claim.contested explicit flag';
      }
    } catch (e) { /* skip */ }
  }
  const visited = walkPacketTextFiles(packetDir, 200);
  for (const fp of visited) {
    const text = safeReadText(fp);
    if (text.includes('<<<<<<<') && text.includes('>>>>>>>')) {
      const rel = path.relative(packetDir, fp).replace(/\\/g, '/');
      evidence.push(`git conflict markers in ${rel}`);
      if (!reason) reason = 'git conflict markers';
      break;
    }
  }
  return { is: evidence.length > 0, reason, evidence };
}

function detectExpired(packetDir) {
  let expiredCount = 0;
  let reason = '';
  const nowIso = nowIsoUtc();
  const candidates = [];
  if (isFile(path.join(packetDir, 'claim.json'))) candidates.push(path.join(packetDir, 'claim.json'));
  if (isFile(path.join(packetDir, 'data', 'claims.jsonl'))) candidates.push(path.join(packetDir, 'data', 'claims.jsonl'));
  for (const c of candidates) {
    const text = safeReadText(c);
    if (c.endsWith('.jsonl')) {
      for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const claim = JSON.parse(trimmed);
          const exp = claim.expires_at;
          if (typeof exp === 'string' && exp < nowIso) {
            expiredCount++;
            if (!reason) reason = `claim expires_at=${exp} < now`;
          }
        } catch (e) { /* skip */ }
      }
    } else {
      try {
        const claim = JSON.parse(text);
        const exp = claim.expires_at;
        if (typeof exp === 'string' && exp < nowIso) {
          expiredCount++;
          if (!reason) reason = `claim expires_at=${exp} < now`;
        }
      } catch (e) { /* skip */ }
    }
  }
  return { is: expiredCount > 0, reason, count: expiredCount };
}

// Walk text files in packet (matches Python rglob suffix filter)
function walkPacketTextFiles(packetDir, maxFiles = 200) {
  const allowed = new Set(['.json', '.md', '.jsonl', '.html', '.txt']);
  const out = [];
  const stack = [packetDir];
  while (stack.length > 0 && out.length < maxFiles) {
    const cur = stack.pop();
    let entries;
    try { entries = fs.readdirSync(cur, { withFileTypes: true }); } catch (e) { continue; }
    for (const e of entries) {
      const fp = path.join(cur, e.name);
      if (e.isDirectory()) { stack.push(fp); continue; }
      const ext = path.extname(e.name);
      if (allowed.has(ext)) out.push(fp);
      if (out.length >= maxFiles) break;
    }
  }
  return out;
}

// ---------- Verdict computation ----------
function computeVerdict(packetPath, actionClass = 'general') {
  const t0 = process.hrtime.bigint();
  const [parseable, parseReason] = packetIsParseable(packetPath);
  if (!parseable) {
    return {
      verdict: VERDICT.UNKNOWN,
      reasons: ['packet shape not parseable', parseReason],
      trust_dial_active: IRREVERSIBLE_ACTION_CLASSES.has(actionClass) ? 'Professional' : 'Casual',
      trust_dial_recommended_for_action_class: TRUST_DIAL_RECOMMENDATION[actionClass] || 'Casual',
      top_3_signals: [{
        name: 'packet_parse',
        value: 'MALFORMED',
        civilian_phrasing: 'Packet shape could not be parsed.',
      }],
      signals: {},
      parse_status: 'malformed',
      action_class: actionClass,
      v15_extension: 'none',
      block_reason_id: 'UNKNOWN_PARSE_FAILURE',
      cache_hit: false,
      elapsed_ms: Number((process.hrtime.bigint() - t0) / 1000000n) / 1.0,
      doctor_version: DOCTOR_VERSION,
    };
  }
  const pkgDir = isDir(packetPath) ? packetPath : path.dirname(packetPath);

  // v1.5 precedence: QUARANTINED > CONTESTED > EXPIRED > FAIL > WARN > PASS
  const q = detectQuarantined(pkgDir);
  if (q.is) {
    return {
      verdict: VERDICT.QUARANTINED,
      reasons: [`policy violation: ${q.reason}`, ...q.violations],
      trust_dial_active: 'Critical',
      trust_dial_recommended_for_action_class: 'Critical',
      top_3_signals: [{
        name: 'quarantine_violation',
        value: q.reason,
        civilian_phrasing: 'An explicit policy violation was detected. Review the audit log.',
      }],
      signals: extractSignals(pkgDir),
      parse_status: 'parseable',
      action_class: actionClass,
      v15_extension: 'QUARANTINED',
      v15_evidence: q.violations,
      block_reason_id: 'QUARANTINED_POLICY_VIOLATION',
      cache_hit: false,
      elapsed_ms: Number((process.hrtime.bigint() - t0) / 1000000n) / 1.0,
      doctor_version: DOCTOR_VERSION,
    };
  }

  const c = detectContested(pkgDir);
  if (c.is) {
    return {
      verdict: VERDICT.CONTESTED,
      reasons: [`concurrent edits: ${c.reason}`, ...c.evidence],
      trust_dial_active: 'Important',
      trust_dial_recommended_for_action_class: TRUST_DIAL_RECOMMENDATION[actionClass] || 'Casual',
      top_3_signals: [{
        name: 'contested_concurrent_edit',
        value: c.reason,
        civilian_phrasing: 'Two or more edits to this packet conflict. Decide which wins before relying on this verdict.',
      }],
      signals: extractSignals(pkgDir),
      parse_status: 'parseable',
      action_class: actionClass,
      v15_extension: 'CONTESTED',
      v15_evidence: c.evidence,
      block_reason_id: 'CONTESTED_CONCURRENT_EDIT',
      cache_hit: false,
      elapsed_ms: Number((process.hrtime.bigint() - t0) / 1000000n) / 1.0,
      doctor_version: DOCTOR_VERSION,
    };
  }

  const e = detectExpired(pkgDir);
  if (e.is) {
    return {
      verdict: VERDICT.EXPIRED,
      reasons: [`TTL expired: ${e.reason}`, `expired_count=${e.count}`],
      trust_dial_active: 'Casual',
      trust_dial_recommended_for_action_class: TRUST_DIAL_RECOMMENDATION[actionClass] || 'Casual',
      top_3_signals: [{
        name: 'expired_claims',
        value: e.count,
        civilian_phrasing: `${e.count} claim(s) past their expiration date. Run the validator again to refresh them.`,
      }],
      signals: extractSignals(pkgDir),
      parse_status: 'parseable',
      action_class: actionClass,
      v15_extension: 'EXPIRED',
      v15_evidence: [`expired_count=${e.count}`, e.reason],
      block_reason_id: 'EXPIRED_TTL',
      cache_hit: false,
      elapsed_ms: Number((process.hrtime.bigint() - t0) / 1000000n) / 1.0,
      doctor_version: DOCTOR_VERSION,
    };
  }

  const sigs = extractSignals(pkgDir);
  const f18 = sigs.f18_laundering_score.score;
  const f15 = sigs.f15_missing_witness_flag.count;
  const f16 = sigs.f16_attack_flag.count;
  const f19 = sigs.f19_coverage_gap_flag.count;
  const a8 = sigs.a8_srs_decay_status.count;

  const failReasons = [];
  if (f18 >= F18_LAUNDERING_FAIL_THRESHOLD) failReasons.push(`F18 laundering score ${f18.toFixed(2)} >= ${F18_LAUNDERING_FAIL_THRESHOLD.toFixed(2)} (CRITICAL)`);
  if (f15 >= 1) failReasons.push(`F15 missing-witness flag: ${f15} criterion(a)`);
  if (f16 >= 1) failReasons.push(`F16 attack class flag: ${f16} attack(s)`);
  const failTriggered = failReasons.length > 0;

  const warnReasons = [];
  if (f18 >= F18_LAUNDERING_WARN_THRESHOLD && f18 < F18_LAUNDERING_FAIL_THRESHOLD) {
    warnReasons.push(`F18 laundering score ${f18.toFixed(2)} >= ${F18_LAUNDERING_WARN_THRESHOLD.toFixed(2)} (HIGH-RISK)`);
  }
  if (f19 >= 1) warnReasons.push(`F19 coverage gap: ${f19} missing`);
  if (a8 >= 1) warnReasons.push(`A8 SRS decay: ${a8} stale claim(s)`);
  const warnTriggered = warnReasons.length > 0;

  let verdict;
  let reasons;
  if (failTriggered) { verdict = VERDICT.FAIL; reasons = failReasons; }
  else if (warnTriggered) { verdict = VERDICT.WARN; reasons = warnReasons; }
  else if (!sigs.any_signal_non_ok) { verdict = VERDICT.PASS; reasons = ['all F-tier signals clean']; }
  else { verdict = VERDICT.WARN; reasons = warnReasons.length > 0 ? warnReasons : ['minor signal flagged']; }

  const trustDialActive = (
    IRREVERSIBLE_ACTION_CLASSES.has(actionClass) ? 'Professional' :
      (warnTriggered || failTriggered) ? 'Important' : 'Casual'
  );

  // Top-3 signals
  const candidates = [];
  if (f18 > 0) candidates.push({
    name: 'F18 laundering score', value: Math.round(f18 * 100) / 100,
    civilian_phrasing: sigs.f18_laundering_score.civilian_phrasing,
  });
  if (f19 > 0) candidates.push({
    name: 'F19 coverage gap', value: f19,
    civilian_phrasing: `Skipped scope: ${f19}`,
  });
  if (f15 > 0) candidates.push({
    name: 'F15 completion gap', value: f15,
    civilian_phrasing: `Hidden completion gap: ${f15} detected`,
  });
  if (f16 > 0) candidates.push({
    name: 'F16 attack class', value: f16,
    civilian_phrasing: `${f16} attack pattern(s) flagged`,
  });
  if (a8 > 0) candidates.push({
    name: 'A8 SRS decay', value: a8,
    civilian_phrasing: `${a8} stale claim(s)`,
  });
  if (candidates.length === 0) {
    candidates.push({
      name: 'all signals clean', value: 'OK',
      civilian_phrasing: 'No F-tier signals breached threshold.',
    });
  }
  const top3 = candidates.slice(0, 3);

  let blockReasonId = 'PASS_ALL_CLEAN';
  if (verdict === VERDICT.FAIL) {
    if (f18 >= F18_LAUNDERING_FAIL_THRESHOLD) blockReasonId = 'F18_LAUNDERING_HIGH';
    else if (f15 >= 1) blockReasonId = 'F15_MISSING_WITNESS';
    else if (f16 >= 1) blockReasonId = 'F16_ATTACK_FLAG';
    else blockReasonId = 'F18_LAUNDERING_HIGH';
  } else if (verdict === VERDICT.WARN) {
    blockReasonId = 'WARN_SIGNAL_HIGH_NOT_CRITICAL';
  }

  const elapsedNs = process.hrtime.bigint() - t0;
  const elapsedMs = Number(elapsedNs) / 1e6;

  return {
    verdict,
    reasons,
    trust_dial_active: trustDialActive,
    trust_dial_recommended_for_action_class: TRUST_DIAL_RECOMMENDATION[actionClass] || 'Casual',
    top_3_signals: top3,
    signals: sigs,
    parse_status: 'parseable',
    action_class: actionClass,
    v15_extension: 'none',
    block_reason_id: blockReasonId,
    cache_hit: false,
    elapsed_ms: Math.round(elapsedMs * 100) / 100,
    doctor_version: DOCTOR_VERSION,
  };
}

// ---------- Canonical projection (byte-parity fingerprint) ----------
//
// To compare verdicts across runtimes byte-for-byte we project to a fixed shape
// that excludes runtime-specific fields (elapsed_ms, doctor_version, cache_hit).
// This is the canonical projection used by the cross-runtime test harness.
function canonicalProjection(rec) {
  return {
    action_class: rec.action_class,
    block_reason_id: rec.block_reason_id,
    parse_status: rec.parse_status,
    reasons: rec.reasons,
    signals_summary: {
      f15_missing_witness_count: ((rec.signals || {}).f15_missing_witness_flag || {}).count || 0,
      f16_attack_count: ((rec.signals || {}).f16_attack_flag || {}).count || 0,
      f18_laundering_score_str: (((rec.signals || {}).f18_laundering_score || {}).score || 0).toFixed(2),
      f19_coverage_gap_count: ((rec.signals || {}).f19_coverage_gap_flag || {}).count || 0,
      a8_srs_decay_count: ((rec.signals || {}).a8_srs_decay_status || {}).count || 0,
      any_signal_non_ok: !!((rec.signals || {}).any_signal_non_ok || false),
    },
    top_3_signals_names: (rec.top_3_signals || []).map(s => s.name),
    trust_dial_active: rec.trust_dial_active,
    trust_dial_recommended_for_action_class: rec.trust_dial_recommended_for_action_class,
    v15_extension: rec.v15_extension,
    verdict: rec.verdict,
  };
}

function canonicalSha256(obj) {
  // Stable canonical: sort keys recursively, separators (",",":"), no extra whitespace
  function sortKeys(v) {
    if (Array.isArray(v)) return v.map(sortKeys);
    if (v && typeof v === 'object') {
      const sorted = {};
      for (const k of Object.keys(v).sort()) sorted[k] = sortKeys(v[k]);
      return sorted;
    }
    return v;
  }
  const canon = JSON.stringify(sortKeys(obj));
  return crypto.createHash('sha256').update(canon).digest('hex');
}

// ---------- Exit codes ----------
function exitForVerdict(v) {
  return ({
    [VERDICT.PASS]: 0, [VERDICT.WARN]: 1, [VERDICT.FAIL]: 2, [VERDICT.UNKNOWN]: 3,
    [VERDICT.EXPIRED]: 4, [VERDICT.CONTESTED]: 5, [VERDICT.QUARANTINED]: 6,
  })[v] ?? 3;
}

// ---------- CLI ----------
function main() {
  const args = process.argv.slice(2);
  let packet = null;
  let asJson = false;
  let actionClass = 'general';
  let quiet = false;
  let canonical = false;
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--json') asJson = true;
    else if (a === '--quiet') quiet = true;
    else if (a === '--no-cache') { /* no-op for node port */ }
    else if (a === '--canonical') canonical = true;
    else if (a === '--action-class') { actionClass = args[++i] || 'general'; }
    else if (!packet) packet = a;
  }

  if (!packet) {
    process.stderr.write('Usage: node aep_doctor_node.js <packet> [--json] [--canonical] [--quiet] [--action-class CLASS]\n');
    return 2;
  }

  const rec = computeVerdict(packet, actionClass);

  if (canonical) {
    const proj = canonicalProjection(rec);
    const projHash = canonicalSha256(proj);
    const out = { canonical_projection: proj, canonical_sha256: projHash, doctor_version: DOCTOR_VERSION };
    if (!quiet) process.stdout.write(JSON.stringify(out, null, 2) + '\n');
    return exitForVerdict(rec.verdict);
  }

  if (asJson) {
    if (!quiet) process.stdout.write(JSON.stringify(rec, null, 2) + '\n');
  } else {
    if (!quiet) {
      process.stdout.write(`VERDICT: ${rec.verdict}\n`);
      process.stdout.write(`Trust level: ${rec.trust_dial_active}\n`);
      process.stdout.write(`Block reason: ${rec.block_reason_id}\n`);
      process.stdout.write(`Elapsed: ${rec.elapsed_ms} ms (${rec.doctor_version})\n`);
    }
  }
  return exitForVerdict(rec.verdict);
}

if (require.main === module) {
  process.exit(main());
}

module.exports = { computeVerdict, canonicalProjection, canonicalSha256, VERDICT, DOCTOR_VERSION };
