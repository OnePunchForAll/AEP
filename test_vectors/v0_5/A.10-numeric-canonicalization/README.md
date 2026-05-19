# A.10 — AEP-NUMERIC-v1 Cross-Runtime Conformance Vectors

**Spec section**: [AEP_v0_5_5_SPEC.md §V54](../../../spec/AEP_v0_5_5_SPEC.md)

This directory is the **cross-runtime conformance corpus** for AEP-NUMERIC-v1 — the strict numeric canonicalization profile introduced in v0.5.1 to close Round-4 Attack #2 (Canonicalization Number Semantics Split-Brain).

## What v0.6 expects from this corpus

Every conforming implementation of `aep_numeric_canonicalize(input)` MUST:

1. Pass **100%** of the vectors in `vectors.json` byte-for-byte.
2. Produce the **exact** `expected` canonical string for inputs marked `expected_error: null`.
3. Raise the **exact** `expected_error` code for inputs marked otherwise.
4. NOT silently coerce, round, or reformat values outside the spec.

Discrepancies between runtimes (Python vs Node vs Go vs Rust) constitute a v0.6 specification gap and MUST be filed as issues.

## Why this matters

v0.5.1's "exact science" claim was honestly downgraded to "PERFECTED FOR DECLARED SCOPE" because cross-runtime numeric determinism was un-verified. v0.6 closes this by:

1. Authoring at least 2 additional implementations (Node.js + Go) that pass these vectors byte-for-byte.
2. Adding edge cases captured during cross-runtime divergence (`open_test_vector_gaps_for_v0_6` in vectors.json).
3. Promoting AEP-NUMERIC-v1 from STRONGLY_PLAUSIBLE to PROVEN_RELIABLE only after ≥3 independent runtimes agree on every vector.

## Vector categories (8 categories, 35 vectors)

| Category | # vectors | What it tests |
|---|---|---|
| `zero_normalization` | 4 | Sign of zero and decimal-point dropping |
| `integer_canonical` | 6 | Integer serialization without decimal point |
| `decimal_canonical_no_trailing_zeros` | 6 | Decimal trailing-zero removal |
| `exponent_form` | 7 | Scientific notation threshold + sign |
| `range_limits` | 5 | `|v| > 10^308` and subnormal rejection |
| `forbidden_values` | 3 | NaN / Inf / -Inf rejection |
| `precision_limits` | 4 | 17-significant-digit boundary |
| `noncanonical_input_rejection` | 5 | Round-trip canonical-form enforcement |
| `duplicate_key_rejection_strict_canonical` | 1 | Inherited from v0.5 strict JSON parser |

## Running the vectors against the Python reference

```bash
cd projects/v11-aep/publish-ready/aep
PYTHONPATH=src python -m aep.run_numeric_vectors test_vectors/v0_5/A.10-numeric-canonicalization/vectors.json
```

The Python reference is the canonical baseline. Node/Go/Rust implementations target this baseline for v0.6.

## Cross-runtime conformance promise

When a runtime claims AEP-NUMERIC-v1 conformance, it MUST:

1. Publish a passing-vectors report against this exact `vectors.json` file (sha256-pinned).
2. Surface its `runtime_id` (e.g., `python-3.12.0`, `node-22.0.0`, `go-1.23.0`, `rust-1.79.0`) in the report.
3. Maintain backward-compatibility with new vectors added in v0.6+ (failing to pass new vectors invalidates conformance until updated).

## License

Apache-2.0 (vectors.json + this README, consistent with the rest of the AEP reference impl).

## Cite

- [Spec §V51-4 AEP-NUMERIC-v1](../../../spec/AEP_v0_5_1_SPEC.md)
- [Round-2 Attack #2 source](../../../../../round-2/round-2-bundle-2026-05-14.html)
- Full honesty trail across v0.5 → v0.5.5: see [`../../../CHANGELOG.md`](../../../CHANGELOG.md)
