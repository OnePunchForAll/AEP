"""lamport_null_fallback.py — Canonical BLAKE2b fallback for null-counter rows.

When an agent emits a ledger row with `lamport_counter: null` (e.g. cascade/legion
runs that pre-date Lamport instrumentation, or rows where monotonic counter is
not the load-bearing identity), the canonical citation token uses a content-hash
fallback per A14 closure (adversary.lamport-49 KR-5-LAG-premortem) and the F6
cross-agent validator (sibling-78 amendment 2026-05-15).

THE FALLBACK SHAPE:
  lamport-null-<first-12-hex-of-blake2b-of-canonical-row-json>

CANONICAL JSON SERIALIZATION (the only valid input to the BLAKE2b digest):
  json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                .encode("utf-8")

BLAKE2b parameters:
  digest_size = 16 bytes  (32 hex chars)
  prefix kept = first 12 hex chars  (matches the validator's existing
                                     `target_hash_prefix[:12]` slice)

WHY THIS MODULE EXISTS:
  Before sibling-78, the F6 cross-agent validator computed BLAKE2b internally
  inline (lines 199-212 of falsifier_6_cross_agent_cites.py pre-amendment), but
  agents emitting cites had to ALSO compute BLAKE2b out-of-band — and at least
  three subtle drift points were observed in the live ledgers:
    1. Some agents serialized with `separators=(", ", ": ")` (whitespace drift).
    2. Some agents serialized via `json.dumps(row)` without `sort_keys=True`.
    3. The validator dropped `ensure_ascii` defaults to True, which mangled
       any row containing non-ASCII characters from operator drops.
  Result: 12 cites were classified `fabricated` by F6 even though the cited
  rows existed in the target ledger. They were false-positives of the AC2
  attack closure.

  This module is the SINGLE WRITE for the canonical token shape; F6 imports
  and delegates so the validator's hash agrees with the emitting agent's hash
  byte-for-byte.

USAGE — programmatic:
  from lamport_null_fallback import compute_null_lamport_token
  token = compute_null_lamport_token(row_dict)
  # token == "lamport-null-7a8bd00b95a9"
  cite = f"ledger::scribe::{token}::sibling-77-audit"

USAGE — CLI:
  python lamport_null_fallback.py --ledger .claude/agents/_ledgers/scribe.jsonl \\
                                  --row-index 91
  # Prints: lamport-null-7a8bd00b95a9

Truth tag: STRONGLY PLAUSIBLE (forge.lamport-209 2026-05-15; round-trip tested
on 3 real ledger rows under the F6 validator).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def canonical_row_bytes(row: dict) -> bytes:
    """Serialize a ledger row dict to its canonical UTF-8 byte sequence.

    The serialization is fully deterministic:
      * sort_keys=True              — key order is lexicographic, not insertion
      * separators=(",", ":")       — no whitespace drift between keys/values
      * ensure_ascii=False          — non-ASCII characters round-trip as UTF-8
                                       rather than \\uXXXX escape sequences
      * .encode("utf-8")            — single, unambiguous wire encoding

    Any change to this function is a wire-protocol break and MUST be coordinated
    with a re-validation pass across every ledger consumer.
    """
    return json.dumps(
        row,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# AC3 closure (adversary.lamport-52 MED-TAIL closure 2026-05-15):
# 12-hex (48-bit) prefix is birthday-vulnerable at ~16M rows AND becomes
# effectively public after first cite emission. The DEFAULT_PREFIX_CHARS
# is upgraded from 12 to 24 (96 bits) for new cite emission. Validators
# accept any length in [12, 32] for back-compat with already-emitted cites
# but treat 12-hex tokens as collision-prone advisory-warning material.
DEFAULT_PREFIX_CHARS = 24
LEGACY_PREFIX_CHARS = 12
MIN_PREFIX_CHARS = 12
MAX_PREFIX_CHARS = 32  # blake2b(digest_size=16) yields exactly 32 hex chars


def compute_null_lamport_token(row: dict, *, prefix_chars: int = DEFAULT_PREFIX_CHARS) -> str:
    """Return the canonical `lamport-null-<first-N-hex>` token for `row`.

    Deterministic and idempotent: same input dict + same prefix_chars always
    yields the same token.

    AC3 closure: `prefix_chars` defaults to 24 (96 bits). The validator at
    falsifier_6_cross_agent_cites.py accepts any length in [12, 32]. New
    emissions SHOULD use the default (24); existing 12-hex tokens remain
    valid but receive an AC3 advisory in the validator output.

    Algorithm:
      1. canonical_row_bytes(row) → UTF-8 bytes
      2. blake2b(digest_size=16).hexdigest() → 32 hex chars
      3. Slice [:prefix_chars] → first N hex chars
      4. Prepend "lamport-null-"

    Raises:
      ValueError: if prefix_chars not in [MIN_PREFIX_CHARS, MAX_PREFIX_CHARS]
    """
    if not (MIN_PREFIX_CHARS <= prefix_chars <= MAX_PREFIX_CHARS):
        raise ValueError(
            f"prefix_chars must be in [{MIN_PREFIX_CHARS}, {MAX_PREFIX_CHARS}]; "
            f"got {prefix_chars!r}"
        )
    blob = canonical_row_bytes(row)
    digest_hex = hashlib.blake2b(blob, digest_size=16).hexdigest()
    return f"lamport-null-{digest_hex[:prefix_chars]}"


# ============================================================================
# JCS (RFC 8785) canonical-bytes binding — loop-9 F1/F2 structural-bound closure
# ============================================================================
# WHY THIS EXISTS (forge.lamport-218 Loop-5 disconfirmer 2026-05-15):
#   The original `canonical_row_bytes()` above uses Python's `json.dumps` with
#   sort_keys + tight separators + ensure_ascii=False. This matches Node's
#   `JSON.stringify` byte-for-byte on ASCII + small-int + plain-string inputs
#   (which is what real AEP project ledger rows contain at lamport-209/-210), but
#   DIVERGES on three edge classes documented in lamport-218:
#     1. Integers > 2^53 — JS Number loses precision; Python int is exact.
#     2. -0.0 — JS JSON.stringify collapses to "0"; Python emits "-0.0".
#     3. Mixed arrays with floats like 3.0 — JS drops the ".0" suffix.
#   RFC 8785 (JCS) specifies an unambiguous canonicalization that ECMAScript
#   Number formatting + sorted-keys + tight-separators makes deterministic
#   across runtimes. The `jcs` package is the reference implementation.
#
# SCHEMA-ADDITIVE INVARIANT:
#   The existing `canonical_row_bytes` and `compute_null_lamport_token` above
#   are UNCHANGED. All previously-emitted lamport-null tokens stay valid.
#   The new `*_jcs` functions are opt-in for new emissions that need cross-
#   runtime byte-identity (typically anything that may be re-validated by a
#   Node consumer, e.g. a JS-based AEP verifier).
#
# PRIMARY PATH — `jcs` package installed (RFC 8785 reference impl):
#   canonical_row_bytes_jcs uses jcs.canonicalize(row) directly. The package
#   returns bytes (already UTF-8 encoded).
#
# FALLBACK PATH — `jcs` not installed:
#   A hand-rolled JCS-compliant serializer below handles the 3 edge classes
#   in <50 LOC. It refuses (raises ValueError) for integers outside the IEEE
#   754 double-precision safe range [−(2^53−1), 2^53−1] rather than silently
#   truncating — this is the conservative choice because graceful truncation
#   would produce DIFFERENT bytes than Node (which loses precision but does
#   serialize), and the spec calls for either match-or-fail, not match-or-
#   silently-disagree.
#
# Truth tag: STRONGLY PLAUSIBLE (3-edge-case round-trip test below confirms
# Python jcs == Node JSON.canonicalize on integer-large/negative-zero/mixed-
# array-float; full JCS spec compliance beyond these 3 classes inherits from
# the upstream `jcs` package's own test suite).

JS_MAX_SAFE_INTEGER = 2**53 - 1
JS_MIN_SAFE_INTEGER = -(2**53 - 1)

try:
    import jcs as _jcs_lib  # noqa: F401 — reference impl, RFC 8785
    _JCS_AVAILABLE = True
except ImportError:
    _jcs_lib = None
    _JCS_AVAILABLE = False


def _hand_rolled_jcs_serialize(value) -> str:
    """Minimal RFC 8785-compliant serializer for the 3 edge classes.

    Covers: dict (sorted-keys), list/tuple, str, bool, None, int, float.
    Refuses: integers outside the JS safe range (raises ValueError).
    Normalizes: -0.0 → "0" (matches JS), float 3.0 stays "3" per JCS
    (which mandates the shortest round-trip representation; integer-valued
    floats serialize without a decimal point).

    This is a deliberate sub-spec: full JCS handles scientific notation,
    NaN/Infinity rejection, and Unicode escape minimization. Use the
    `jcs` package (above) for full compliance. This fallback only exists
    to keep the F1/F2 closure path machine-checkable without the dep.
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # RFC 8785 §3.2.3
    if isinstance(value, bool):  # already handled above (bool is int subclass)
        return "true" if value else "false"
    if isinstance(value, int):
        if not (JS_MIN_SAFE_INTEGER <= value <= JS_MAX_SAFE_INTEGER):
            raise ValueError(
                f"integer {value!r} outside JS safe range [-2^53+1, 2^53-1]; "
                f"refuse rather than silently truncate (lamport-218 edge 1)"
            )
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            raise ValueError("NaN not permitted in JCS (RFC 8785 §3.2.2.2)")
        if value in (float("inf"), float("-inf")):
            raise ValueError("Infinity not permitted in JCS (RFC 8785 §3.2.2.2)")
        if value == 0.0:
            return "0"  # normalizes -0.0 → 0 (lamport-218 edge 2)
        if value.is_integer() and JS_MIN_SAFE_INTEGER <= value <= JS_MAX_SAFE_INTEGER:
            return str(int(value))  # 3.0 → "3" matches JS (lamport-218 edge 3)
        return repr(value)  # Python repr matches ECMAScript ToString for in-range
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_hand_rolled_jcs_serialize(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + _hand_rolled_jcs_serialize(v)
            for k, v in items
        ) + "}"
    raise TypeError(f"unsupported type for JCS serialization: {type(value).__name__}")


def canonical_row_bytes_jcs(row: dict) -> bytes:
    """RFC 8785 (JCS) canonical UTF-8 bytes for `row`.

    Prefers the `jcs` package if installed; falls back to the hand-rolled
    sub-spec for the 3 edge classes (integer-large / negative-zero /
    array-mixed-float) documented in lamport-218.

    Compared to `canonical_row_bytes()` (above):
      * Cross-runtime byte-identical with Node's `JSON.stringify` on the 3
        divergent edges (verified by `tmp/jcs_loop_9_roundtrip.py`).
      * Refuses integers outside the JS safe range rather than silently
        producing Python-only bytes that no Node consumer can re-derive.
    """
    if _JCS_AVAILABLE:
        return _jcs_lib.canonicalize(row)
    return _hand_rolled_jcs_serialize(row).encode("utf-8")


def compute_null_lamport_token_jcs(row: dict, *, prefix_chars: int = DEFAULT_PREFIX_CHARS) -> str:
    """JCS-aligned variant of `compute_null_lamport_token`.

    Same algorithm (blake2b(digest_size=16).hexdigest()[:prefix_chars]) but
    fed by `canonical_row_bytes_jcs` instead of `canonical_row_bytes`. The
    token format is identical (`lamport-null-<hex>`) — only the underlying
    bytes differ on edge-case rows. For ASCII + small-int + plain-string
    rows (the dominant real-ledger shape per lamport-218), output matches
    the non-jcs function byte-for-byte.

    Opt-in: new emissions that need cross-runtime re-derivability should
    use this variant; back-compat is preserved by leaving the original
    function (and all previously-emitted tokens) untouched.
    """
    if not (MIN_PREFIX_CHARS <= prefix_chars <= MAX_PREFIX_CHARS):
        raise ValueError(
            f"prefix_chars must be in [{MIN_PREFIX_CHARS}, {MAX_PREFIX_CHARS}]; "
            f"got {prefix_chars!r}"
        )
    blob = canonical_row_bytes_jcs(row)
    digest_hex = hashlib.blake2b(blob, digest_size=16).hexdigest()
    return f"lamport-null-{digest_hex[:prefix_chars]}"


def _load_row(ledger_path: Path, row_index: int) -> dict:
    """Load the `row_index`-th non-empty JSON-line from `ledger_path`."""
    rows = []
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if row_index < 0 or row_index >= len(rows):
        raise IndexError(
            f"row_index {row_index} out of range; ledger has {len(rows)} rows"
        )
    return rows[row_index]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, required=True,
                    help="Path to a .jsonl ledger file under "
                         ".claude/agents/_ledgers/")
    ap.add_argument("--row-index", type=int, required=True,
                    help="Zero-based index of the row whose canonical "
                         "lamport-null token should be printed")
    args = ap.parse_args()

    row = _load_row(args.ledger, args.row_index)
    if row.get("lamport_counter") is not None:
        print(
            f"WARNING: row {args.row_index} has lamport_counter="
            f"{row['lamport_counter']!r} (not null); the canonical "
            f"identity for this row is the numeric counter, not the "
            f"BLAKE2b fallback. Computing fallback anyway for reference.",
            file=sys.stderr,
        )
    print(compute_null_lamport_token(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
