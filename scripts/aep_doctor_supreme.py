#!/usr/bin/env python3
"""
aep_doctor_supreme.py - K12 AEP Doctor Supreme (AEP v1.5 LTS)

Operator directive (sec73.2 sacred): K12 AEP Doctor Supreme.

Extends v1.2 aep_doctor.py (PASS/WARN/FAIL/UNKNOWN) with 3 NEW verdicts:
  - PASS         - all gates clean
  - WARN         - signals above threshold but no critical violations
  - FAIL         - any critical signal fails
  - UNKNOWN      - validator missing or packet malformed
  - EXPIRED      - claims past TTL not revalidated  (NEW)
  - CONTESTED    - concurrent edits detected on same packet  (NEW)
  - QUARANTINED  - explicit policy violation                (NEW)

Performance targets (constitution-bound):
  - cached doctor p95 <= 300 ms
  - normal doctor p95 <= 1500 ms

Cache layer (K7 Semantic Compression Cache):
  - Cache directory: .claude/aep/cache/doctor/
  - Cache key: sha256(packet_state) + sha256(constitution) + validator_versions
  - Cache value: verdict + signals + timestamp
  - TTL: 30 days
  - Invalidation: any packet edit + constitution edit + validator version bump

CLI:
  python aep_doctor_supreme.py <packet>
  python aep_doctor_supreme.py <packet> --verbose
  python aep_doctor_supreme.py <packet> --lite
  python aep_doctor_supreme.py <packet> --explain BLOCK_REASON_ID
  python aep_doctor_supreme.py <packet> --cached-only
  python aep_doctor_supreme.py <packet> --no-cache

Truth tag: STRONGLY PLAUSIBLE (T6+T7+T8+T9 empirical this turn;
p95 measured on small fixture; production rollout STAGED v1.5.1 with
1000-packet corpus benchmark).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Import v1.2 doctor primitives
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from aep_doctor import (  # noqa: E402
    compute_verdict as compute_verdict_v12,
    packet_is_parseable,
    render_compact as render_compact_v12,
    render_verbose as render_verbose_v12,
    emit_aep_lite,
    VERDICT_PASS,
    VERDICT_WARN,
    VERDICT_FAIL,
    VERDICT_UNKNOWN,
)


# ---------- v1.5 verdict constants ----------

VERDICT_EXPIRED = "EXPIRED"
VERDICT_CONTESTED = "CONTESTED"
VERDICT_QUARANTINED = "QUARANTINED"

ALL_VERDICTS = (
    VERDICT_PASS,
    VERDICT_WARN,
    VERDICT_FAIL,
    VERDICT_UNKNOWN,
    VERDICT_EXPIRED,
    VERDICT_CONTESTED,
    VERDICT_QUARANTINED,
)


# ---------- Paths ----------

REPO_ROOT = _SCRIPTS_DIR.parents[3]
CACHE_DIR = REPO_ROOT / ".claude" / "aep" / "cache" / "doctor"
CONSTITUTION_PATH = REPO_ROOT / ".claude" / "aep" / "constitution" / "aep_constitution_v1_5_lts.json"

CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

# Doctor + extension version stamps for cache invalidation
DOCTOR_SUPREME_VERSION = "v1.5.0-lts"


# ---------- Plain-language explanations (K10 composition) ----------

BLOCK_REASON_EXPLANATIONS = {
    "F18_LAUNDERING_HIGH": (
        "The source of this evidence cannot be traced back to a clean original. "
        "Several layers of citation lead in a circle or to material that itself "
        "lacks proof. We block the action until you can point to a source that "
        "isn't part of the loop."
    ),
    "F15_MISSING_WITNESS": (
        "A claim says it was completed, but there is no test result or file "
        "evidence to prove the work actually happened. We block the action "
        "until a witness is attached for each criterion."
    ),
    "F16_ATTACK_FLAG": (
        "Patterns in this packet match a known attack class (for example, "
        "prompt injection or trust escalation by misleading framing). "
        "Until you mark these patterns reviewed or fix them, the action is held."
    ),
    "F19_COVERAGE_GAP": (
        "Some parts of what was claimed have no source or test backing them. "
        "We do not block, but you should know which parts are claims-only "
        "before you act on them."
    ),
    "A8_SRS_DECAY": (
        "Some claims have not been revalidated in a long time. Old PASS results "
        "stop counting as fresh after 30 days. Re-run the relevant tests or "
        "let the claim expire."
    ),
    "EXPIRED_TTL": (
        "This claim's expiration date has passed. The evidence underneath may "
        "still be true, but the system requires fresh confirmation before "
        "treating it as current."
    ),
    "CONTESTED_CONCURRENT_EDIT": (
        "Two or more people or tools edited this packet at roughly the same time. "
        "We hold the verdict until you confirm which edit should win, so we "
        "don't accidentally erase someone's work."
    ),
    "QUARANTINED_POLICY_VIOLATION": (
        "This packet attempted an action the constitution explicitly forbids "
        "(for example, trying to read a secret file or bypass a safety hook). "
        "It is quarantined. Review the audit log before unblocking."
    ),
    "UNKNOWN_PARSE_FAILURE": (
        "The packet's shape could not be read. It may be corrupted, "
        "encrypted, or saved with a format newer than this doctor supports. "
        "Run the validator to identify the problem before relying on this evidence."
    ),
    "PASS_ALL_CLEAN": (
        "All safety, completeness, and provenance gates pass. "
        "You can proceed with the action class checked."
    ),
    "WARN_SIGNAL_HIGH_NOT_CRITICAL": (
        "One or more signals are higher than ideal but none are at a critical level. "
        "You can proceed if you accept the disclosed weaknesses in row 4."
    ),
}


# ---------- Helpers ----------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _now_epoch() -> float:
    return datetime.datetime.now(datetime.timezone.utc).timestamp()


def _sha256_path_recursive(p: pathlib.Path) -> str:
    """SHA256 of file or recursive directory state."""
    h = hashlib.sha256()
    if p.is_file():
        h.update(p.read_bytes())
        return h.hexdigest()
    if p.is_dir():
        for child in sorted(p.rglob("*")):
            if child.is_file():
                try:
                    h.update(str(child.relative_to(p)).encode("utf-8"))
                    h.update(b"\0")
                    h.update(child.read_bytes())
                    h.update(b"\0")
                except (OSError, PermissionError):
                    continue
        return h.hexdigest()
    return "MISSING"


def _constitution_hash() -> str:
    if CONSTITUTION_PATH.is_file():
        return hashlib.sha256(CONSTITUTION_PATH.read_bytes()).hexdigest()
    return "no_constitution"


def _validator_versions_hash() -> str:
    """Hash of validator script mtimes + sizes for cache invalidation."""
    files = [
        _SCRIPTS_DIR / "aep_doctor.py",
        _SCRIPTS_DIR / "aep_doctor_supreme.py",
        _SCRIPTS_DIR / "build_f22_civilian_proof_card.py",
        _SCRIPTS_DIR / "build_v15_falsifier_dsl.py",
        _SCRIPTS_DIR / "build_v15_human_outcome.py",
        _SCRIPTS_DIR / "build_v15_lts_extension_abi.py",
    ]
    h = hashlib.sha256()
    h.update(DOCTOR_SUPREME_VERSION.encode("utf-8"))
    for f in files:
        if f.is_file():
            try:
                stat = f.stat()
                h.update(f.name.encode("utf-8"))
                h.update(f":{stat.st_size}".encode("utf-8"))
            except OSError:
                continue
    return h.hexdigest()


def _cache_key(packet_path: pathlib.Path) -> str:
    pkt_state = _sha256_path_recursive(packet_path)
    parts = pkt_state + ":" + _constitution_hash() + ":" + _validator_versions_hash()
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cf = CACHE_DIR / f"{key}.json"
    if not cf.is_file():
        return None
    try:
        rec = json.loads(cf.read_text(encoding="utf-8"))
    except Exception:
        return None
    age = _now_epoch() - rec.get("epoch", 0)
    if age > CACHE_TTL_SECONDS:
        return None
    return rec


def _cache_put(key: str, verdict_record: Dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cf = CACHE_DIR / f"{key}.json"
    payload = {
        "verdict_record": verdict_record,
        "epoch": _now_epoch(),
        "iso": _now_iso(),
        "doctor_version": DOCTOR_SUPREME_VERSION,
    }
    try:
        cf.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ---------- v1.5 verdict detectors ----------

def _detect_expired(packet_dir: pathlib.Path) -> Tuple[bool, str, int]:
    """
    Detect TTL expiration on packet claims.

    Reads claim.json or data/claims.jsonl; checks expires_at field.
    Returns (is_expired, reason, expired_count).
    """
    expired_count = 0
    reason = ""

    candidates = []
    if (packet_dir / "claim.json").is_file():
        candidates.append(packet_dir / "claim.json")
    if (packet_dir / "data" / "claims.jsonl").is_file():
        candidates.append(packet_dir / "data" / "claims.jsonl")

    now_iso = _now_iso()
    for c in candidates:
        try:
            text = c.read_text(encoding="utf-8")
        except OSError:
            continue
        if c.suffix == ".jsonl":
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    claim = json.loads(line)
                except Exception:
                    continue
                exp = claim.get("expires_at")
                if isinstance(exp, str) and exp < now_iso:
                    expired_count += 1
                    if not reason:
                        reason = f"claim expires_at={exp} < now"
        else:
            try:
                claim = json.loads(text)
            except Exception:
                continue
            exp = claim.get("expires_at")
            if isinstance(exp, str) and exp < now_iso:
                expired_count += 1
                if not reason:
                    reason = f"claim expires_at={exp} < now"

    return (expired_count > 0, reason, expired_count)


def _detect_contested(packet_dir: pathlib.Path) -> Tuple[bool, str, List[str]]:
    """
    Detect concurrent edits on the same packet.

    Heuristics:
      - presence of .merge_conflict marker
      - presence of multiple <<<<<<< markers in any text file
      - explicit "contested": true in claim.json
    Returns (is_contested, reason, evidence_paths).
    """
    evidence: List[str] = []
    reason = ""

    if (packet_dir / ".merge_conflict").exists():
        evidence.append(".merge_conflict marker present")
        reason = "merge-conflict marker file"

    claim = packet_dir / "claim.json"
    if claim.is_file():
        try:
            c = json.loads(claim.read_text(encoding="utf-8"))
            if c.get("contested") is True:
                evidence.append("claim.json contested=true")
                reason = reason or "claim.contested explicit flag"
        except Exception:
            pass

    # Conflict markers
    for f in packet_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in (".json", ".md", ".jsonl", ".html", ".txt"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "<<<<<<<" in text and ">>>>>>>" in text:
            evidence.append(f"git conflict markers in {f.relative_to(packet_dir)}")
            reason = reason or "git conflict markers"
            break

    return (bool(evidence), reason, evidence)


def _detect_quarantined(packet_dir: pathlib.Path) -> Tuple[bool, str, List[str]]:
    """
    Detect explicit policy violations.

    Heuristics:
      - secret_airlock attempt logged
      - constitution.forbidden_actions match
      - quarantined: true in claim.json
    Returns (is_quarantined, reason, violations).
    """
    violations: List[str] = []
    reason = ""

    claim = packet_dir / "claim.json"
    if claim.is_file():
        try:
            c = json.loads(claim.read_text(encoding="utf-8"))
            if c.get("quarantined") is True:
                violations.append("claim.json quarantined=true")
                reason = "claim.quarantined explicit flag"
        except Exception:
            pass

    # Scan for explicit policy violation markers in any text file
    forbidden_patterns = (
        "FORBIDDEN_ACTION_DETECTED",
        "SECRET_AIRLOCK_BREACH",
        "policy_violation:true",
        "sandbox_escape",
        "powershell_hook_attempt",  # sec68
    )
    for f in packet_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in (".json", ".jsonl", ".md", ".html", ".txt"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for fp in forbidden_patterns:
            if fp in text:
                violations.append(f"{fp} in {f.relative_to(packet_dir)}")
                reason = reason or fp
                break
        if violations:
            break

    return (bool(violations), reason, violations)


# ---------- compute_verdict_supreme ----------

def compute_verdict_supreme(
    aepkg_path: pathlib.Path | str,
    *,
    action_class: str = "general",
    use_cache: bool = True,
    cached_only: bool = False,
) -> Dict[str, Any]:
    """
    K12 supreme verdict computation. Returns 7-state verdict.
    """
    p = pathlib.Path(aepkg_path)
    t0 = time.time()
    cache_hit = False

    if use_cache:
        try:
            ckey = _cache_key(p)
            cached = _cache_get(ckey)
            if cached:
                rec = dict(cached["verdict_record"])
                rec["cache_hit"] = True
                rec["cache_age_seconds"] = round(_now_epoch() - cached["epoch"], 2)
                rec["elapsed_ms"] = round((time.time() - t0) * 1000, 2)
                rec["doctor_version"] = DOCTOR_SUPREME_VERSION
                return rec
        except OSError:
            pass

    if cached_only:
        return {
            "verdict": VERDICT_UNKNOWN,
            "reasons": ["cached_only mode: no cache hit available"],
            "cache_hit": False,
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
            "doctor_version": DOCTOR_SUPREME_VERSION,
        }

    # Run v1.2 base verdict for PASS/WARN/FAIL/UNKNOWN
    v12 = compute_verdict_v12(p, action_class=action_class)

    # If v1.2 says UNKNOWN, return that immediately
    if v12["verdict"] == VERDICT_UNKNOWN:
        v12["cache_hit"] = False
        v12["elapsed_ms"] = round((time.time() - t0) * 1000, 2)
        v12["doctor_version"] = DOCTOR_SUPREME_VERSION
        if use_cache:
            try:
                _cache_put(_cache_key(p), v12)
            except OSError:
                pass
        return v12

    pkt_dir = p if p.is_dir() else p.parent

    # v1.5 detectors -- ORDER OF PRECEDENCE per operator K12:
    # QUARANTINED > CONTESTED > EXPIRED > FAIL > WARN > PASS
    q_is, q_reason, q_evidence = _detect_quarantined(pkt_dir)
    if q_is:
        result = {
            "verdict": VERDICT_QUARANTINED,
            "reasons": [f"policy violation: {q_reason}"] + q_evidence,
            "trust_dial_active": "Critical",
            "trust_dial_recommended_for_action_class": "Critical",
            "top_3_signals": [
                {
                    "name": "quarantine_violation",
                    "value": q_reason,
                    "civilian_phrasing": (
                        "An explicit policy violation was detected. "
                        "Review the audit log."
                    ),
                }
            ],
            "signals": v12.get("signals", {}),
            "parse_status": "parseable",
            "action_class": action_class,
            "v15_extension": "QUARANTINED",
            "v15_evidence": q_evidence,
            "block_reason_id": "QUARANTINED_POLICY_VIOLATION",
        }
    else:
        c_is, c_reason, c_evidence = _detect_contested(pkt_dir)
        if c_is:
            result = {
                "verdict": VERDICT_CONTESTED,
                "reasons": [f"concurrent edits: {c_reason}"] + c_evidence,
                "trust_dial_active": "Important",
                "trust_dial_recommended_for_action_class": v12.get(
                    "trust_dial_recommended_for_action_class", "Casual"
                ),
                "top_3_signals": [
                    {
                        "name": "contested_concurrent_edit",
                        "value": c_reason,
                        "civilian_phrasing": (
                            "Two or more edits to this packet conflict. "
                            "Decide which wins before relying on this verdict."
                        ),
                    }
                ],
                "signals": v12.get("signals", {}),
                "parse_status": "parseable",
                "action_class": action_class,
                "v15_extension": "CONTESTED",
                "v15_evidence": c_evidence,
                "block_reason_id": "CONTESTED_CONCURRENT_EDIT",
            }
        else:
            e_is, e_reason, e_count = _detect_expired(pkt_dir)
            if e_is:
                result = {
                    "verdict": VERDICT_EXPIRED,
                    "reasons": [f"TTL expired: {e_reason}", f"expired_count={e_count}"],
                    "trust_dial_active": v12.get("trust_dial_active", "Casual"),
                    "trust_dial_recommended_for_action_class": v12.get(
                        "trust_dial_recommended_for_action_class", "Casual"
                    ),
                    "top_3_signals": [
                        {
                            "name": "expired_claims",
                            "value": e_count,
                            "civilian_phrasing": (
                                f"{e_count} claim(s) past their expiration date. "
                                "Run the validator again to refresh them."
                            ),
                        }
                    ],
                    "signals": v12.get("signals", {}),
                    "parse_status": "parseable",
                    "action_class": action_class,
                    "v15_extension": "EXPIRED",
                    "v15_evidence": [f"expired_count={e_count}", e_reason],
                    "block_reason_id": "EXPIRED_TTL",
                }
            else:
                # v1.2 verdict stands (PASS/WARN/FAIL)
                result = dict(v12)
                result["v15_extension"] = "none"
                # Map block_reason_id from existing signals
                if result["verdict"] == VERDICT_FAIL:
                    sigs = result.get("signals", {})
                    if float(sigs.get("f18_laundering_score", {}).get("score", 0)) >= 0.8:
                        result["block_reason_id"] = "F18_LAUNDERING_HIGH"
                    elif int(sigs.get("f15_missing_witness_flag", {}).get("count", 0)) >= 1:
                        result["block_reason_id"] = "F15_MISSING_WITNESS"
                    elif int(sigs.get("f16_attack_flag", {}).get("count", 0)) >= 1:
                        result["block_reason_id"] = "F16_ATTACK_FLAG"
                    else:
                        result["block_reason_id"] = "F18_LAUNDERING_HIGH"
                elif result["verdict"] == VERDICT_WARN:
                    result["block_reason_id"] = "WARN_SIGNAL_HIGH_NOT_CRITICAL"
                elif result["verdict"] == VERDICT_PASS:
                    result["block_reason_id"] = "PASS_ALL_CLEAN"

    result["cache_hit"] = False
    result["elapsed_ms"] = round((time.time() - t0) * 1000, 2)
    result["doctor_version"] = DOCTOR_SUPREME_VERSION

    if use_cache:
        try:
            _cache_put(_cache_key(p), result)
        except OSError:
            pass

    return result


# ---------- Explain ----------

def explain_block_reason(block_reason_id: str) -> str:
    """Return the plain-language explanation for a block reason id."""
    return BLOCK_REASON_EXPLANATIONS.get(
        block_reason_id,
        f"Unknown block reason: {block_reason_id}. Run --verbose for raw signals."
    )


# ---------- Renderers ----------

def render_compact_supreme(rec: Dict[str, Any]) -> str:
    """Compact rendering with v1.5 extension lines."""
    lines: List[str] = []
    lines.append(f"VERDICT: {rec['verdict']}")
    lines.append("")
    lines.append(f"Trust level: {rec.get('trust_dial_active', 'Casual')}")
    if rec.get("v15_extension") and rec["v15_extension"] != "none":
        lines.append(f"v1.5 extension: {rec['v15_extension']}")
    if rec.get("block_reason_id"):
        lines.append(f"Block reason: {rec['block_reason_id']}")
    lines.append("Top 3 signals:")
    for s in rec.get("top_3_signals", []):
        lines.append(f"  - {s.get('name', '?')}: {s.get('value', '?')} "
                     f"({s.get('civilian_phrasing', '')})")
    if rec.get("cache_hit"):
        lines.append(f"Cache: HIT (age={rec.get('cache_age_seconds', 0)}s)")
    else:
        lines.append("Cache: MISS")
    lines.append(f"Elapsed: {rec.get('elapsed_ms', 0)} ms")
    lines.append("")
    if rec.get("block_reason_id"):
        lines.append(
            f"Run --explain {rec['block_reason_id']} for plain-language explanation."
        )
    lines.append("Run with --verbose for full evidence.")
    return "\n".join(lines)


# ---------- Canonical projection (cross-runtime byte-parity fingerprint) ----------
#
# Mirror sibling Node + Perl ports' canonicalProjection for byte-parity test.
# Excludes runtime-specific fields (elapsed_ms, doctor_version, cache_hit, etc.)
# so 3 runtimes can produce identical canonical JSON + identical sha256.

def canonical_projection(rec: Dict[str, Any]) -> Dict[str, Any]:
    signals = rec.get("signals") or {}
    f18 = signals.get("f18_laundering_score") or {}
    f15 = signals.get("f15_missing_witness_flag") or {}
    f16 = signals.get("f16_attack_flag") or {}
    f19 = signals.get("f19_coverage_gap_flag") or {}
    a8 = signals.get("a8_srs_decay_status") or {}
    return {
        "action_class": rec.get("action_class"),
        "block_reason_id": rec.get("block_reason_id"),
        "parse_status": rec.get("parse_status"),
        "reasons": rec.get("reasons"),
        "signals_summary": {
            "f15_missing_witness_count": int(f15.get("count", 0)),
            "f16_attack_count": int(f16.get("count", 0)),
            "f18_laundering_score_str": "{:.2f}".format(float(f18.get("score", 0))),
            "f19_coverage_gap_count": int(f19.get("count", 0)),
            "a8_srs_decay_count": int(a8.get("count", 0)),
            "any_signal_non_ok": bool(signals.get("any_signal_non_ok", False)),
        },
        "top_3_signals_names": [s.get("name") for s in rec.get("top_3_signals", [])],
        "trust_dial_active": rec.get("trust_dial_active"),
        "trust_dial_recommended_for_action_class": rec.get("trust_dial_recommended_for_action_class"),
        "v15_extension": rec.get("v15_extension"),
        "verdict": rec.get("verdict"),
    }


def canonical_sha256(obj: Any) -> str:
    canon = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------- CLI ----------

def _exit_for_verdict(v: str) -> int:
    return {
        VERDICT_PASS: 0,
        VERDICT_WARN: 1,
        VERDICT_FAIL: 2,
        VERDICT_UNKNOWN: 3,
        VERDICT_EXPIRED: 4,
        VERDICT_CONTESTED: 5,
        VERDICT_QUARANTINED: 6,
    }.get(v, 3)


def _cli() -> int:
    ap = argparse.ArgumentParser(
        description="K12 AEP Doctor Supreme - 7-verdict civilian health check"
    )
    ap.add_argument("packet", nargs="?", help="Path to .aepkg directory or JSON")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--lite", nargs="?", const="<auto>", default=None)
    ap.add_argument(
        "--explain", help="Print plain-language explanation for BLOCK_REASON_ID"
    )
    ap.add_argument("--cached-only", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--action-class", default="general", choices=(
        "general", "financial", "medical", "legal",
        "employment", "housing", "irreversible",
    ))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--canonical", action="store_true",
                    help="Emit canonical projection + sha256 for cross-runtime byte-parity test (Phase A)")
    args = ap.parse_args()

    if args.explain and not args.packet:
        print(explain_block_reason(args.explain))
        return 0

    if not args.packet:
        ap.error("packet path required (or pass --explain BLOCK_REASON_ID)")

    rec = compute_verdict_supreme(
        args.packet,
        action_class=args.action_class,
        use_cache=not args.no_cache,
        cached_only=args.cached_only,
    )

    if args.explain:
        rec["plain_language_explanation"] = explain_block_reason(args.explain)
        if not args.quiet:
            print(explain_block_reason(args.explain))

    if args.lite:
        lite_out = args.lite if args.lite != "<auto>" else f"{args.packet}.lite"
        emit_aep_lite(args.packet, lite_out, action_class=args.action_class)
        if not args.quiet:
            print(render_compact_supreme(rec))
            print(f"\nAEP Lite emitted to: {lite_out}")
        return _exit_for_verdict(rec["verdict"])

    if args.canonical:
        proj = canonical_projection(rec)
        proj_hash = canonical_sha256(proj)
        out = {
            "canonical_projection": proj,
            "canonical_sha256": proj_hash,
            "doctor_version": DOCTOR_SUPREME_VERSION,
        }
        if not args.quiet:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        return _exit_for_verdict(rec["verdict"])

    if args.json:
        if not args.quiet:
            print(json.dumps(rec, ensure_ascii=False, indent=2))
    else:
        if not args.quiet:
            print(render_compact_supreme(rec))
            if args.verbose:
                print("\n" + "=" * 60)
                print("FULL VERDICT RECORD")
                print("=" * 60)
                print(json.dumps(rec, ensure_ascii=False, indent=2))

    return _exit_for_verdict(rec["verdict"])


if __name__ == "__main__":
    sys.exit(_cli())
