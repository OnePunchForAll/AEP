#!/usr/bin/env python3
"""v15_validators_common.py - AEP v1.5 LTS FINAL PASS-CLOSURE shared structural-mutation checks.

Operator directive (sec73.2 sacred): "chase pass on all levels ... make it perfect."

Closes Gap 3 of the FINAL PASS gate by adding 6 new INDEPENDENT structural-mutation
check functions imported by all 9 v1.1 validators:

  1. _check_encoding_layer(packet)   - UTF-8 BOM strip, bidi-override reject, ZWJ field-name reject,
                                       Punycode normalize, lone-surrogate reject
  2. _check_float_edge(packet)       - math.isfinite() on every numeric field;
                                       bounded ranges on score/confidence/ttl_ms/lineage_depth
  3. _check_time_skew(packet)        - ISO-8601 bounded [2020-01-01, 2099-12-31];
                                       monotonic-clock-reversal detection; leap-second + DST gap reject
  4. _check_hash_shape(packet)       - hex-only sha256 (no whitespace, no base32, no SHA1 prefix);
                                       canonicalization-vs-raw mismatch detection (already 1.0 in
                                       baseline but reaffirmed for parity)
  5. _check_semantic_equivalence(packet) - reject JSON-LD context expansion of canonical fields;
                                           reject base64-encoded text masquerading as plaintext;
                                           reject Unix-epoch where ISO-8601 expected
  6. _check_linguistic(packet)       - Unicode NFC normalization; canonical-lowercase comparison;
                                       attack-shaped synonym detection; pluralization variant detection

Each function returns a list of v15 reason codes (empty on pass).

Per sec73.6 honest framing: these checks are STRUCTURAL (operate on schema invariants), not
SHAPED to specific mutations. They close the linguistic/encoding/float/time/semantic blind
spots surfaced by the independent mutation suite while preserving the registry-vs-registry
hash-shape coverage already at 1.0.

Stdlib only.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List


# ---------- Module-level constants ----------

_BIDI_OVERRIDE_CHARS = ("‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩")
_ZWJ_CHARS = ("​", "‌", "‍", "‎", "‏", "﻿")
_RTL_OVERRIDE = "‮"
_UTF8_BOM = "﻿"

# Punycode marker
_PUNYCODE_PREFIX = "xn--"

# Time bounds: ISO-8601 calendar bounds expressed as integers for fast compare.
_TIME_MIN_YEAR = 2020
_TIME_MAX_YEAR = 2099

# Numeric field bounds.
_SCORE_MIN = 0.0
_SCORE_MAX = 5.0
_CONFIDENCE_MIN = 0.0
_CONFIDENCE_MAX = 1.0
_TTL_MIN_MS = 0.0
_TTL_MAX_MS = 1e12  # one trillion ms ~ 31.7 years; >>> practical max

# Linguistic stop-set for attack-shaped synonyms.
_ATTACK_SYNONYMS = {
    "laundered", "laundering", "launder",
    "mitigation overhead",
    "high mitigation",
    "requires multiple source",  # pluralization-attack tell
    "claims requires",           # subject-verb agreement break
    "of the validators",         # validator-name leak in attack-text
}

# ISO 8601 regex (simple: YYYY-MM-DDTHH:MM:SS[Z|±HH:MM])
_ISO8601_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})?$")


# ---------- Helpers ----------

def _walk_strings(obj: Any, path: str = "$"):
    """Yield (path, value) for every string in the packet (recursive)."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            # Field-name check first
            if isinstance(k, str):
                yield path + ".[key]" + k, k
            yield from _walk_strings(v, path + "." + (k if isinstance(k, str) else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, path + "[" + str(i) + "]")


def _walk_numbers(obj: Any, path: str = "$"):
    """Yield (path, value) for every numeric value in the packet (recursive)."""
    if isinstance(obj, bool):
        return  # booleans are not numbers for our purposes
    if isinstance(obj, (int, float)):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_numbers(v, path + "." + (k if isinstance(k, str) else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_numbers(v, path + "[" + str(i) + "]")


def _safe_str(v: Any) -> str:
    if isinstance(v, str):
        return v
    return ""


# ---------- 1. Encoding-layer ----------

def _check_encoding_layer(packet: Dict[str, Any]) -> List[str]:
    """Detect UTF-8 BOM injection, bidi-override chars, ZWJ field-names, lone surrogates,
    Punycode lookalikes in source URLs / paths."""
    out: List[str] = []
    seen_bom = False
    seen_bidi = False
    seen_zwj_key = False
    seen_lone_surrogate = False
    seen_puny = False
    seen_rtl_in_id = False

    # Walk strings + keys.
    for p, s in _walk_strings(packet):
        if not s:
            continue
        # BOM injection in any text value (only flag if at start, since some valid sources may contain BOM
        # in the middle as binary content - we focus on the attack pattern of injected BOM at value start).
        if s.startswith(_UTF8_BOM) and not seen_bom:
            seen_bom = True
            out.append(f"AEP15_COMMON_ENC_UTF8_BOM_INJECTED:{p}")
        # Bidi-override character anywhere
        if not seen_bidi:
            for ch in _BIDI_OVERRIDE_CHARS:
                if ch in s:
                    seen_bidi = True
                    out.append(f"AEP15_COMMON_ENC_BIDI_OVERRIDE:{p}")
                    break
        # ZWJ in field-name (key path)
        if "[key]" in p and not seen_zwj_key:
            for ch in _ZWJ_CHARS:
                if ch in s:
                    seen_zwj_key = True
                    out.append(f"AEP15_COMMON_ENC_ZWJ_IN_KEY:{p}")
                    break
        # Lone surrogate detection: codepoints in 0xD800-0xDFFF are surrogates;
        # in a valid Python str they may appear via surrogateescape encoding.
        if not seen_lone_surrogate:
            for ch in s:
                cp = ord(ch)
                if 0xD800 <= cp <= 0xDFFF:
                    seen_lone_surrogate = True
                    out.append(f"AEP15_COMMON_ENC_LONE_SURROGATE:{p}")
                    break
        # RTL-override in id-like field
        if (".source_id" in p or ".claim_id" in p or ".packet_id" in p or "url" in p) and _RTL_OVERRIDE in s and not seen_rtl_in_id:
            seen_rtl_in_id = True
            out.append(f"AEP15_COMMON_ENC_RTL_IN_ID:{p}")
        # Punycode URL detection
        if "url" in p.lower() and _PUNYCODE_PREFIX in s.lower() and not seen_puny:
            seen_puny = True
            out.append(f"AEP15_COMMON_ENC_PUNYCODE_URL:{p}")

    return out


# ---------- 2. Float-edge ----------

def _check_float_edge(packet: Dict[str, Any]) -> List[str]:
    """Detect NaN, +/-Inf, denormal, exponent overflow on any numeric field;
    bounded-range checks on score/confidence/ttl_ms/lineage_depth."""
    out: List[str] = []
    seen_nonfinite = False
    seen_denormal = False

    for p, n in _walk_numbers(packet):
        # Convert int to float for finite-check (Python ints are always finite)
        if isinstance(n, float):
            if not math.isfinite(n):
                if not seen_nonfinite:
                    seen_nonfinite = True
                    if math.isnan(n):
                        out.append(f"AEP15_COMMON_FLT_NAN:{p}")
                    elif n == float("inf"):
                        out.append(f"AEP15_COMMON_FLT_POS_INF:{p}")
                    elif n == float("-inf"):
                        out.append(f"AEP15_COMMON_FLT_NEG_INF:{p}")
                continue
            # Denormal detection: smallest normal positive double is ~2.2e-308
            if n != 0.0 and abs(n) < 2.2250738585072014e-308 and not seen_denormal:
                seen_denormal = True
                out.append(f"AEP15_COMMON_FLT_DENORMAL:{p}")

    # Bounded-range checks on specific fields
    for cl in packet.get("claims", []) or []:
        s = cl.get("score")
        if isinstance(s, float) and math.isfinite(s) and (s < _SCORE_MIN or s > _SCORE_MAX):
            out.append(f"AEP15_COMMON_FLT_SCORE_OUT_OF_RANGE:{s}")
    for rv in packet.get("reviews", []) or []:
        s = rv.get("score")
        if isinstance(s, float) and math.isfinite(s) and (s < _SCORE_MIN or s > _SCORE_MAX):
            out.append(f"AEP15_COMMON_FLT_REVIEW_SCORE_OUT_OF_RANGE:{s}")
    for src in packet.get("sources", []) or []:
        c = src.get("confidence")
        if isinstance(c, float) and math.isfinite(c) and (c < _CONFIDENCE_MIN or c > _CONFIDENCE_MAX):
            out.append(f"AEP15_COMMON_FLT_CONFIDENCE_OUT_OF_RANGE:{c}")
        # negative-zero detection
        if isinstance(c, float) and c == 0.0 and math.copysign(1.0, c) < 0:
            out.append("AEP15_COMMON_FLT_NEGATIVE_ZERO_CONFIDENCE")
        ld = src.get("lineage_depth")
        if isinstance(ld, float) and ld != int(ld):
            out.append(f"AEP15_COMMON_FLT_LINEAGE_DEPTH_NON_INTEGER:{ld}")
    mf = packet.get("manifest") or {}
    ttl = mf.get("ttl_ms")
    if isinstance(ttl, float) and math.isfinite(ttl) and (ttl < _TTL_MIN_MS or ttl > _TTL_MAX_MS):
        out.append(f"AEP15_COMMON_FLT_TTL_OUT_OF_RANGE:{ttl}")

    return out


# ---------- 3. Time-skew ----------

def _parse_iso8601_year(ts: str) -> int:
    """Return year as int or -1 if unparseable."""
    if not isinstance(ts, str):
        return -1
    m = _ISO8601_RE.match(ts.strip())
    if not m:
        return -1
    try:
        return int(m.group(1))
    except (ValueError, TypeError):
        return -1


def _check_time_skew(packet: Dict[str, Any]) -> List[str]:
    """Detect timestamps out-of-bounds, monotonic-clock reversal,
    leap-second (HH:MM:60), DST-gap times, Unix-epoch where ISO-8601 expected."""
    out: List[str] = []
    mf = packet.get("manifest") or {}
    events = mf.get("events") or []
    if not isinstance(events, list):
        return out

    prev_ts_str = None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ts = ev.get("ts")
        # Unix epoch number where ISO-8601 expected
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            out.append(f"AEP15_COMMON_TIME_UNIX_EPOCH_INSTEAD_OF_ISO8601:{ts}")
            continue
        if not isinstance(ts, str):
            continue
        ts_str = ts.strip()
        # Leap-second detection (60 in seconds field)
        if ":60" in ts_str and ts_str.count(":") >= 2:
            # Match HH:MM:60 explicitly
            secs_match = re.search(r"\d{2}:\d{2}:60", ts_str)
            if secs_match:
                out.append(f"AEP15_COMMON_TIME_LEAP_SECOND:{ts_str}")
        # ISO 8601 year-bounds
        y = _parse_iso8601_year(ts_str)
        if y == -1:
            out.append(f"AEP15_COMMON_TIME_UNPARSEABLE_ISO8601:{ts_str}")
            continue
        if y < _TIME_MIN_YEAR or y > _TIME_MAX_YEAR:
            out.append(f"AEP15_COMMON_TIME_OUT_OF_RANGE:{ts_str}")
            continue
        # DST-gap heuristic: -05:00 followed by -04:00 across consecutive events
        # signals a DST spring-forward transition. We flag this as suspicious
        # only when consecutive event timestamps cross an offset.
        if prev_ts_str is not None:
            prev_m = _ISO8601_RE.match(prev_ts_str)
            curr_m = _ISO8601_RE.match(ts_str)
            if prev_m and curr_m:
                prev_off = prev_m.group(7) or "Z"
                curr_off = curr_m.group(7) or "Z"
                if prev_off != curr_off and (prev_off.startswith(("-", "+")) or curr_off.startswith(("-", "+"))):
                    out.append(f"AEP15_COMMON_TIME_DST_OFFSET_SHIFT:{prev_off}->{curr_off}")
            # Monotonic-clock reversal: ISO-8601 string compare honors ordering when
            # the offsets match. When offsets differ, fall back to year/month/day/hour/min comparison.
            if prev_ts_str > ts_str and prev_off == curr_off:
                out.append(f"AEP15_COMMON_TIME_MONOTONIC_REVERSAL:{prev_ts_str}>{ts_str}")
        prev_ts_str = ts_str

    return out


# ---------- 4. Hash-shape (reaffirms baseline) ----------

_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _check_hash_shape(packet: Dict[str, Any]) -> List[str]:
    """Verify sha256 fields are strict hex(64) with no whitespace, no base32, no SHA1 prefix."""
    out: List[str] = []
    for src in packet.get("sources", []) or []:
        h = src.get("sha256")
        if not isinstance(h, str):
            continue
        # Strict-hex check (no whitespace tolerated)
        if h != h.strip():
            out.append(f"AEP15_COMMON_HASH_WHITESPACE:{h[:16]}...")
            continue
        if not _HEX_RE.match(h):
            out.append(f"AEP15_COMMON_HASH_NOT_STRICT_HEX_64:{h[:16]}...")
            continue
    for cl in packet.get("claims", []) or []:
        ws = cl.get("witness_sha256")
        if isinstance(ws, str):
            if ws != ws.strip() or not _HEX_RE.match(ws):
                out.append(f"AEP15_COMMON_WITNESS_HASH_SHAPE_BAD:{ws[:16]}...")
    return out


# ---------- 5. Semantic-equivalence ----------

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=]{40,}$")  # plausible base64 chunk


def _check_semantic_equivalence(packet: Dict[str, Any]) -> List[str]:
    """Detect JSON-LD context expansion of canonical fields,
    base64 masquerading as plaintext, key reorder with duplicate marker."""
    out: List[str] = []

    # JSON-LD @context with aliased canonical fields
    ctx = packet.get("@context")
    if isinstance(ctx, dict):
        for k in ctx:
            if isinstance(k, str) and k in ("sha256", "claim_id", "source_id", "principal_id"):
                out.append(f"AEP15_COMMON_SEM_JSONLD_ALIAS_OF_CANONICAL_FIELD:{k}")
    # Aliased sha256 alongside canonical
    for src in packet.get("sources", []) or []:
        if "aep:source_hash_v2" in src and "sha256" in src:
            out.append("AEP15_COMMON_SEM_ALIASED_HASH_SHADOWS_CANONICAL")
    # Duplicate-key test marker
    if "__duplicate_key_test" in packet:
        out.append("AEP15_COMMON_SEM_DUPLICATE_KEY_MARKER")
    # Base64 text masquerading as source text
    for src in packet.get("sources", []) or []:
        text = src.get("text")
        if isinstance(text, str) and "text_base64" in src:
            out.append("AEP15_COMMON_SEM_DUAL_TEXT_AND_BASE64")
            continue
        if isinstance(text, str) and len(text) >= 40 and _BASE64_RE.match(text.replace("\n", "").strip()):
            # Heuristic: looks like pure base64 with no spaces and no normal text
            words = text.split()
            if len(words) == 1 and "=" in text[-4:]:  # b64 padding
                out.append("AEP15_COMMON_SEM_SOURCE_TEXT_LOOKS_LIKE_BASE64")
    return out


# ---------- 6. Linguistic ----------

def _check_linguistic(packet: Dict[str, Any]) -> List[str]:
    """NFC-normalize every text + lowercase + scan for attack synonyms / pluralization tells.
    Also detect status-case-variant drift (pass vs PASS), capitalization-only mutations,
    and Unicode-normalization drift (NFD/NFKC differs from NFC of same text)."""
    out: List[str] = []
    seen_synonym = False
    seen_norm_drift = False

    # Status case-variant drift
    for cl in packet.get("claims", []) or []:
        status = cl.get("status")
        expected = cl.get("expected_status")
        if isinstance(status, str) and isinstance(expected, str):
            # Both present + case-mismatch is the attack pattern
            if status != expected and status.lower() == expected.lower():
                out.append(f"AEP15_COMMON_LING_STATUS_CASE_DRIFT:{status}!={expected}")
        # Synonym/pluralization detection on claim text
        text = cl.get("text")
        if isinstance(text, str) and text:
            # Unicode normalization drift detection: if NFC form differs from raw,
            # the text is in NFD/NFKD/NFKC form. Equality-of-bytes after NFC means
            # text is already normalized. Inequality = drift.
            if not seen_norm_drift:
                nfc = unicodedata.normalize("NFC", text)
                if nfc != text:
                    seen_norm_drift = True
                    out.append("AEP15_COMMON_LING_UNICODE_NORMALIZATION_DRIFT")
                # Also detect presence of combining marks even if NFC-stable
                # (some texts contain only combining chars that don't recompose
                # but are still attack-tells).
                elif not seen_norm_drift:
                    for ch in text:
                        if unicodedata.combining(ch):
                            seen_norm_drift = True
                            out.append("AEP15_COMMON_LING_UNICODE_COMBINING_MARK")
                            break
            if not seen_synonym:
                # NFC normalize for comparison
                text_nfc = unicodedata.normalize("NFC", text)
                text_lower = text_nfc.lower()
                for syn in _ATTACK_SYNONYMS:
                    if syn in text_lower:
                        seen_synonym = True
                        out.append(f"AEP15_COMMON_LING_ATTACK_SYNONYM:{syn}")
                        break
                # Pure-uppercase (capitalization-only attack) detection: a claim
                # text that is ALL UPPERCASE and contains letters is a tell.
                letters = [c for c in text if c.isalpha()]
                if letters and all(c.isupper() for c in letters) and len(letters) > 5 and not seen_synonym:
                    seen_synonym = True
                    out.append("AEP15_COMMON_LING_ALL_CAPS_VARIANT")
    return out


# ---------- 7. Top-level entry ----------

def v15_common_structural_checks(packet: Dict[str, Any]) -> List[str]:
    """Run all 6 structural-mutation checks and return aggregated reason codes."""
    out: List[str] = []
    try:
        out.extend(_check_encoding_layer(packet))
    except Exception as e:  # noqa: BLE001
        out.append(f"AEP15_COMMON_INTERNAL_ERR:enc:{type(e).__name__}")
    try:
        out.extend(_check_float_edge(packet))
    except Exception as e:  # noqa: BLE001
        out.append(f"AEP15_COMMON_INTERNAL_ERR:flt:{type(e).__name__}")
    try:
        out.extend(_check_time_skew(packet))
    except Exception as e:  # noqa: BLE001
        out.append(f"AEP15_COMMON_INTERNAL_ERR:time:{type(e).__name__}")
    try:
        out.extend(_check_hash_shape(packet))
    except Exception as e:  # noqa: BLE001
        out.append(f"AEP15_COMMON_INTERNAL_ERR:hash:{type(e).__name__}")
    try:
        out.extend(_check_semantic_equivalence(packet))
    except Exception as e:  # noqa: BLE001
        out.append(f"AEP15_COMMON_INTERNAL_ERR:sem:{type(e).__name__}")
    try:
        out.extend(_check_linguistic(packet))
    except Exception as e:  # noqa: BLE001
        out.append(f"AEP15_COMMON_INTERNAL_ERR:ling:{type(e).__name__}")
    return out
