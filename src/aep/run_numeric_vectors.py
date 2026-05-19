"""run_numeric_vectors — Apache-2.0 — AEP-NUMERIC-v1 conformance runner.

Reads the cross-runtime test vectors JSON corpus (default:
``test_vectors/v0_5/A.10-numeric-canonicalization/vectors.json``), evaluates every
vector against the Python reference implementation of AEP-NUMERIC-v1 (provided
by ``aep.validate_v0_5_1``), and reports per-vector + summary pass/fail.

For v0.6 cross-runtime conformance: each independent implementation (Node.js,
Go, Rust, …) runs the same vectors and produces byte-identical canonical
strings (or expected_error codes) per the v0.5.1 §V51-4 / v0.5.5 §V54 spec.

Usage:
  python -m aep.run_numeric_vectors                          # uses default corpus path
  python -m aep.run_numeric_vectors path/to/vectors.json     # explicit path
"""
from __future__ import annotations

import argparse
import decimal
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import the reference numeric helpers exposed by the unified v0.5.5 validator.
# We import lazily so a missing helper doesn't crash the whole module — the
# absent helper just means the corresponding category returns "skipped".
try:
    from aep.validate_v0_5_1 import (  # type: ignore[attr-defined]
        AEP51_NUMERIC_OUT_OF_RANGE,
        AEP51_NUMERIC_FORBIDDEN,
        AEP51_NUMERIC_PRECISION_LOSS,
        AEP51_NUMERIC_NONCANONICAL_FORM,
    )
except Exception:
    AEP51_NUMERIC_OUT_OF_RANGE = "AEP51_NUMERIC_OUT_OF_RANGE"
    AEP51_NUMERIC_FORBIDDEN = "AEP51_NUMERIC_FORBIDDEN"
    AEP51_NUMERIC_PRECISION_LOSS = "AEP51_NUMERIC_PRECISION_LOSS"
    AEP51_NUMERIC_NONCANONICAL_FORM = "AEP51_NUMERIC_NONCANONICAL_FORM"


AEP5_JSON_INVALID_DUPLICATE_KEY = "AEP5_JSON_INVALID_DUPLICATE_KEY"

# AEP-NUMERIC-v1 range bounds per spec §V51-4.
AEP_NUMERIC_MAX_EXP = 308
AEP_NUMERIC_MIN_NONZERO_EXP = -308
AEP_NUMERIC_MAX_SIG_FIGS = 17


def _parse_input(spec: Dict[str, Any]) -> Tuple[Optional[Any], Optional[str]]:
    """Evaluate the vector's input string (e.g. ``"0.1"``, ``"float('nan')"``,
    ``"1e+1000"``). Returns (value, parse_error_code).
    """
    raw = spec.get("input_python")
    if raw is None:
        return None, None
    s = str(raw).strip()
    if s == "":
        return "", None
    if s.startswith("float("):
        # forbidden literal
        return None, AEP51_NUMERIC_FORBIDDEN
    try:
        value = decimal.Decimal(s)
        return value, None
    except (decimal.InvalidOperation, ValueError):
        return None, "AEP_NUMERIC_PARSE_ERROR"


def aep_numeric_canonicalize(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """Reference canonicalize: returns (canonical_string, error_code).

    Implements AEP-NUMERIC-v1 §V51-4 / v0.5.5 §V54 spec rules.

    Canonical form rules:
      - Sign: leading '-' for negative; never '+' for positive; '-0' folds to '0'.
      - Integer: no decimal point, no leading zeros except '0' itself.
      - Decimal: no trailing zeros after decimal point; no '.0' suffix.
      - Exponent form used when |adjusted_exponent| >= 6 (i.e., values where
        scientific notation is shorter). Lowercase 'e' with explicit '+'/'-' sign.
      - Significand: single integer digit OR <int>.<fraction> with no trailing zeros.
    """
    if not isinstance(value, decimal.Decimal):
        return None, "AEP_NUMERIC_PARSE_ERROR"
    if not value.is_finite():
        return None, AEP51_NUMERIC_FORBIDDEN
    # Range check (strict less-than on negative exponent bound; strict less-than-or-equal on positive).
    if value != 0:
        abs_v = abs(value)
        try:
            if abs_v >= decimal.Decimal(f"1e{AEP_NUMERIC_MAX_EXP + 1}"):
                return None, AEP51_NUMERIC_OUT_OF_RANGE
            if abs_v < decimal.Decimal(f"1e{AEP_NUMERIC_MIN_NONZERO_EXP}"):
                return None, AEP51_NUMERIC_OUT_OF_RANGE
        except decimal.InvalidOperation:
            return None, AEP51_NUMERIC_OUT_OF_RANGE
    # Zero normalization.
    if value == 0:
        return "0", None
    # Precision check (using the AS-PARSED digits to honor explicit precision like 18 sig figs).
    sign_raw, digits_raw, _ = value.as_tuple()
    # Strip leading zeros from the digit tuple for sig-fig count.
    nonzero_idx = next((i for i, d in enumerate(digits_raw) if d != 0), len(digits_raw))
    sig_digits = digits_raw[nonzero_idx:]
    # Strip trailing zeros to count meaningful significant figures.
    last_nonzero = len(sig_digits)
    while last_nonzero > 0 and sig_digits[last_nonzero - 1] == 0:
        last_nonzero -= 1
    sig_figs = last_nonzero
    if sig_figs > AEP_NUMERIC_MAX_SIG_FIGS:
        return None, AEP51_NUMERIC_PRECISION_LOSS

    # Build canonical form from normalized value.
    normalized = value.normalize()
    sign, digits, exp = normalized.as_tuple()
    digits_str = "".join(str(d) for d in digits)
    # `adjusted()` is the exponent of the leading digit when in scientific form.
    adjusted_exp = normalized.adjusted()

    sign_str = "-" if sign == 1 else ""
    use_sci = abs(adjusted_exp) >= 6
    if use_sci:
        # Scientific notation: <sig_digit>[.<more>]e<+|->NN
        if len(digits_str) == 1:
            mantissa = digits_str
        else:
            mantissa = digits_str[0] + "." + digits_str[1:].rstrip("0")
            mantissa = mantissa.rstrip(".")
        exp_sign = "+" if adjusted_exp >= 0 else "-"
        canonical = f"{sign_str}{mantissa}e{exp_sign}{abs(adjusted_exp)}"
    else:
        # Plain decimal form.
        if exp >= 0:
            canonical = sign_str + digits_str + "0" * exp
        else:
            # exp < 0: insert decimal point.
            n_frac = -exp
            if n_frac >= len(digits_str):
                # Need leading zeros: 0.000... + digits
                frac = "0" * (n_frac - len(digits_str)) + digits_str
                canonical = sign_str + "0." + frac.rstrip("0")
            else:
                int_part = digits_str[: len(digits_str) - n_frac]
                frac_part = digits_str[len(digits_str) - n_frac:].rstrip("0")
                if frac_part:
                    canonical = sign_str + int_part + "." + frac_part
                else:
                    canonical = sign_str + int_part
    # -0 fold.
    if canonical == "-0":
        canonical = "0"
    return canonical, None


def _validate_stored_string(stored: str) -> Tuple[Optional[str], Optional[str]]:
    """For TV-N-070..074 category: parse stored_string AND verify it round-trips to itself."""
    s = stored.strip()
    if s == "":
        return None, "AEP_NUMERIC_PARSE_ERROR"
    # Reject leading + sign per AEP-NUMERIC-v1.
    if s.startswith("+"):
        return None, AEP51_NUMERIC_NONCANONICAL_FORM
    # Reject leading zero (except for "0" itself).
    if len(s) >= 2 and s[0] == "0" and s[1].isdigit():
        return None, AEP51_NUMERIC_NONCANONICAL_FORM
    # Reject uppercase E in exponent.
    if "E" in s and "e" not in s:
        return None, AEP51_NUMERIC_NONCANONICAL_FORM
    # Reject exponent without explicit sign.
    if "e" in s.lower():
        e_idx = s.lower().index("e")
        after_e = s[e_idx + 1:]
        if after_e and after_e[0] not in ("+", "-"):
            return None, AEP51_NUMERIC_NONCANONICAL_FORM
    try:
        value = decimal.Decimal(s)
    except (decimal.InvalidOperation, ValueError):
        return None, "AEP_NUMERIC_PARSE_ERROR"
    canonical, err = aep_numeric_canonicalize(value)
    if err:
        return None, err
    if canonical != s:
        return None, AEP51_NUMERIC_NONCANONICAL_FORM
    return canonical, None


def _validate_stored_json(stored: str) -> Tuple[Optional[Any], Optional[str]]:
    """Parse stored_json with strict canonical profile (rejects duplicate keys)."""
    seen_keys_per_object: List[set] = []
    decoder = json.JSONDecoder()

    def _object_pairs_hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError(AEP5_JSON_INVALID_DUPLICATE_KEY)
        return dict(pairs)

    try:
        value = json.loads(stored, object_pairs_hook=_object_pairs_hook)
        return value, None
    except ValueError as exc:
        msg = str(exc)
        if AEP5_JSON_INVALID_DUPLICATE_KEY in msg:
            return None, AEP5_JSON_INVALID_DUPLICATE_KEY
        return None, "AEP5_JSON_PARSE_ERROR"


def run_vectors(corpus_path: Path) -> int:
    if not corpus_path.exists():
        print(f"ERROR: vectors corpus not found at {corpus_path}", file=sys.stderr)
        return 2
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    categories = corpus.get("categories", [])
    total = 0
    passed = 0
    failed: List[Tuple[str, str, str]] = []
    skipped = 0

    for cat in categories:
        cat_name = cat.get("category", "<unknown>")
        for vec in cat.get("vectors", []):
            total += 1
            vec_id = vec.get("id", "<unknown>")
            expected = vec.get("expected")
            expected_error = vec.get("expected_error")

            actual: Optional[str] = None
            actual_error: Optional[str] = None

            if "stored_json" in vec:
                _, err = _validate_stored_json(vec["stored_json"])
                actual_error = err
            elif "stored_string" in vec:
                actual, actual_error = _validate_stored_string(vec["stored_string"])
            elif "input_python" in vec:
                value, parse_err = _parse_input(vec)
                if parse_err is not None:
                    actual_error = parse_err
                elif value is None:
                    skipped += 1
                    continue
                else:
                    actual, actual_error = aep_numeric_canonicalize(value)
            else:
                skipped += 1
                continue

            ok = False
            if expected_error is not None:
                ok = actual_error == expected_error
            elif expected is not None:
                ok = actual_error is None and actual == expected
            if ok:
                passed += 1
            else:
                failed.append((vec_id, f"expected={expected!r} expected_error={expected_error!r}",
                               f"actual={actual!r} actual_error={actual_error!r}"))

    print(f"AEP-NUMERIC-v1 conformance: {passed}/{total} passed, {skipped} skipped, {len(failed)} failed")
    for vid, exp, act in failed[:20]:
        print(f"  FAIL {vid}: {exp} | {act}")
    return 0 if not failed else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run AEP-NUMERIC-v1 conformance vectors.")
    parser.add_argument(
        "corpus_path",
        nargs="?",
        type=Path,
        default=Path("test_vectors/v0_5/A.10-numeric-canonicalization/vectors.json"),
        help="Path to vectors.json (default: test_vectors/v0_5/A.10-numeric-canonicalization/vectors.json)",
    )
    args = parser.parse_args(argv)
    return run_vectors(args.corpus_path)


if __name__ == "__main__":
    sys.exit(main())
