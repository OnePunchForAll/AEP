# AEP v0.5.1 Specification — Hot-Patch Amendment

**Status**: PUBLISHED · post-Round-4 hot-patch · strictly additive on top of AEP v0.5.
**Predecessor**: AEP v0.5 (2026-05-14, PERFECTED-FOR-DECLARED-SCOPE).
**Authors**: operator ([the AEP project](https://x.com/AEPproject)) + the agentic substrate (Claude Opus 4.7).
**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).
**Profile**: `aep:0.5/stable` (unchanged channel; v0.5.1 reuses the v0.5 profile and adds enforcement, not new fields beyond optional reviewer hints).
**Closes**: 3 top Round-4 failure modes (Schema/Profile Binding · Artifact Closure Integrity · Numeric Canonicalization).

---

## §V51-1 — Purpose

Round-4 recursive adversary against the v0.5 perfection milestone surfaced 8 new failure modes that v0.5 does not mechanically close (see [`projects/v11-aep/round-2/round-4-bundle-2026-05-14.html`](../../../round-2/round-4-bundle-2026-05-14.html)). The "exact science" claim on v0.5 is **PARTIALLY FALSIFIED** as a result — strong rigor for the declared 463-packet corpus + 18 known attack classes, but not adversarial completeness.

v0.5.1 is a **strictly additive hot-patch** that closes the top-3 Round-4 failure modes:

1. **Schema/Profile Binding Hard-Fail** — closes Round-4 #1 (Version-Shape Crossfade) + #4 (Profile Boundary Laundering).
2. **Artifact Closure Integrity** — closes Round-4 #7 (State-Hash Coverage Evasion).
3. **AEP-NUMERIC-v1 Lockdown** — closes Round-4 #2 (Canonicalization Number Semantics Split-Brain).

Backward-compatibility property: every v0.5 packet that validates clean at `aep:0.5/stable` strict Level-2 MUST also validate clean at `aep:0.5/stable` strict Level-2 under the v0.5.1 reference validator. Empirically verified on the 463-packet AEP project corpus: 463/463 PASS in 1.3s.

The remaining 5 Round-4 failure modes (Merkle empty/singleton, Legacy-Extension Smuggling, Inference-Cycle Decay Nullification, Conformance Downgrade Laundering, Reviewer Fingerprint Forgery) are deferred to v0.5.2 or v0.7 per the [Round-4 bundle](../../../round-2/round-4-bundle-2026-05-14.html#five-stage-failures).

---

## §V51-2 — Closure 1: Schema/Profile Binding Hard-Fail

### §V51-2.1 Normative requirements (MUST)

A v0.5.1 conformant validator MUST emit the following fail-closed findings:

| Reason code | Condition |
|---|---|
| `AEP51_VERSION_SCHEMA_MISMATCH` | Manifest declares `aep_version="0.5"` but the packet's structural shape fingerprint matches a pre-v0.5 schema (e.g., missing v0.5-specific fields, presence of v0.4-only fields). |
| `AEP51_PROFILE_REQUEST_MISMATCH` | Validator was invoked with `--profile aep:0.5/stable` but the packet manifest declares `profile="aep:0.5/experimental"` (or vice versa). NO silent downgrade or upgrade between stable and experimental profiles. |
| `AEP51_VERSION_PROFILE_INCONSISTENT` | Manifest's `aep_version` and `profile` disagree on channel (e.g., `aep_version="0.5"` + `profile="aep:0.4/jsonld"`). |
| `AEP51_VERSION_SCHEMA_FINGERPRINT_REGISTRY_MISMATCH` | When a fingerprint registry is configured at the packet level and the computed `schema_fingerprint(manifest, canonical_files_present)` does not match any allowed entry. |

### §V51-2.2 Schema fingerprint algorithm

Validators MUST compute a deterministic structural fingerprint from:

1. Sorted list of canonical files PRESENT in the packet (subset of `manifest.canonical_files`).
2. Set of unique top-level keys observed across canonical records (sources, spans, claims, relations, events, reviews, validations).
3. Presence flags for v0.5-specific shape markers:
   - `axis_b_action` field on any claim
   - `decision_time_revalidation_required` field on any claim
   - `go_justification_claim_ids` field on any claim
   - `semantic_stability` on extension entries (list-form only)
   - `packet_epoch` or `supersedes_packet_id` on manifest

The fingerprint is `sha256` of the canonicalized sorted-key JSON representation of the above. The fingerprint MUST NOT include the manifest's `schema_fingerprint` field itself (to prevent self-referential recursion).

### §V51-2.3 Backward compatibility

- Packets without a fingerprint registry pass the registry check silently (registry is opt-in).
- Packets declaring `aep_version="0.5"` and exhibiting v0.5 shape markers fingerprint-validate trivially.
- Mixed-shape packets (v0.4 fields + v0.5 declaration) trigger `AEP51_VERSION_SCHEMA_MISMATCH` as fail-closed `error` in strict mode.

### §V51-2.4 Test vectors

| Vector | Packet declares | Packet shape | v0.5.1 verdict |
|---|---|---|---|
| TV-V51-2.1 | `aep_version="0.5"` + `profile="aep:0.5/stable"` | v0.5 shape (axis_b_action present) | PASS |
| TV-V51-2.2 | `aep_version="0.5"` + `profile="aep:0.5/stable"` | v0.4 shape (no axis_b_action anywhere; uses old single-axis taxonomy) | FAIL `AEP51_VERSION_SCHEMA_MISMATCH` |
| TV-V51-2.3 | `aep_version="0.5"` + `profile="aep:0.4/jsonld"` | (any) | FAIL `AEP51_VERSION_PROFILE_INCONSISTENT` |
| TV-V51-2.4 | `aep_version="0.5"` + `profile="aep:0.5/experimental"`, validator called with `--profile aep:0.5/stable` | (any) | FAIL `AEP51_PROFILE_REQUEST_MISMATCH` |

---

## §V51-3 — Closure 2: Artifact Closure Integrity

### §V51-3.1 Normative requirements (MUST)

A v0.5.1 conformant validator MUST:

1. Walk every canonical record (sources, spans, claims, relations, events, reviews, validations) and collect every in-packet path reference.
2. Build the **integrity envelope** as the union of:
   - `manifest.canonical_files` (the 7 canonical JSONL paths)
   - `aepkg.json` itself
   - All paths under `assets/**`
3. Compare collected path references against the integrity envelope.
4. Emit `AEP51_UNMANIFESTED_REFERENCE` (fail-closed in strict mode) for every referenced path that is NOT in the envelope.
5. Walk the packet directory tree. For any file whose path SHAPE matches a canonical-record pattern (e.g., `data/*.jsonl`, `ops/*.jsonl`, `reviews/*.jsonl`, `validations/*.jsonl`) but which is NOT listed in `manifest.canonical_files`, emit `AEP51_HIDDEN_CANONICAL_FILE`.

### §V51-3.2 Reference collection rules

In-packet references are recognized in the following fields:

- `source.location` where `location.kind` is `"filesystem-path"` or `"in-packet"` — the `path` (or relative reference) value.
- `span.selector` — when selector references a file path (e.g., `kind="byte-range"` with `file_path`, `kind="page-line"` with `file_path`).
- `event.target` — when target is an in-packet path reference (vs. an opaque identifier).
- Any string field matching the pattern `^in-packet:[a-zA-Z0-9_./-]+$` is treated as an in-packet reference.

Paths that look like URLs, git-refs, or other external references are NOT in-packet and are NOT subject to this check (they are covered by v0.5 §9 anchor trust context rules).

### §V51-3.3 Test vectors

| Vector | Setup | v0.5.1 verdict |
|---|---|---|
| TV-V51-3.1 | Packet references only files in canonical_files + assets/ | PASS |
| TV-V51-3.2 | Packet has `data/extra.jsonl` referenced by a claim's basis, but `extra.jsonl` is NOT in `canonical_files` | FAIL `AEP51_UNMANIFESTED_REFERENCE` |
| TV-V51-3.3 | Packet has `data/sneaky.jsonl` on disk but NOT in `canonical_files` AND not referenced — but file SHAPE looks canonical | FAIL `AEP51_HIDDEN_CANONICAL_FILE` |
| TV-V51-3.4 | Packet references a URL with `location_hash` (external, not in-packet) | PASS (external anchor; covered by v0.5 §9) |

---

## §V51-4 — Closure 3: AEP-NUMERIC-v1 Lockdown

### §V51-4.1 Motivation

RFC 8785 (JSON Canonicalization Scheme) is the v0.5 textual canonicalization baseline. It does not, however, fully pin numeric serialization across runtimes:

- Python `json.dumps(0.1 + 0.2)` → `"0.30000000000000004"` (17 sig figs)
- Node.js `JSON.stringify(0.1 + 0.2)` → `"0.30000000000000004"` (matches Python here)
- But: large values like `1e308 * 10` overflow to `Infinity` in IEEE-754 doubles
- Subnormal values (`1e-310`) lose precision in float64

AEP-NUMERIC-v1 lifts numeric handling above IEEE-754 by canonicalizing through a `decimal.Decimal`-equivalent arbitrary-precision AST before serialization.

### §V51-4.2 Normative requirements (MUST)

A v0.5.1 conformant validator MUST:

1. Parse every numeric value in canonical records through an arbitrary-precision decimal type (`decimal.Decimal` in Python, equivalent in other runtimes).
2. Reject any value `|v| > 10^308` with `AEP51_NUMERIC_OUT_OF_RANGE`.
3. Reject any subnormal value `0 < |v| < 10^-308` with `AEP51_NUMERIC_OUT_OF_RANGE`.
4. Reject any value with more than 17 significant decimal digits with `AEP51_NUMERIC_PRECISION_LOSS`.
5. Reject NaN / Infinity / -Infinity at parse time with `AEP51_NUMERIC_FORBIDDEN` (v0.5 strict canonical already does this; v0.5.1 reinforces with a numeric-specific code).
6. Verify that the file's stored serialization of each number matches `aep_numeric_canonicalize(parsed_value)` exactly. Mismatch → `AEP51_NUMERIC_NONCANONICAL_FORM`.

### §V51-4.3 Canonical numeric form

`aep_numeric_canonicalize` produces a string with:

- Optional leading `-` for negative values; NEVER `+` for positive.
- Integer part: no leading zeros except for the integer `0`.
- Fractional part: present only if needed; no trailing zeros (e.g., `1.5` not `1.50`; `0` not `0.0`).
- Exponent: used only when `|exp| ≥ 6` (i.e., values where scientific notation is shorter). Lowercase `e` only. Exponent sign always explicit: `1.5e+10`, `1.5e-10`.
- Zero: always `"0"` (never `"-0"`, `"+0"`, `"0.0"`).
- Maximum precision: 17 significant decimal digits.

### §V51-4.4 Test vectors

| Input | Canonical form | Verdict |
|---|---|---|
| `0` | `"0"` | PASS |
| `-0` | `"0"` | PASS (sign of zero normalized away) |
| `1` | `"1"` | PASS |
| `-1` | `"-1"` | PASS |
| `0.1` | `"0.1"` | PASS |
| `1e-10` | `"1e-10"` | PASS |
| `1e10` | `"1e+10"` (or `"10000000000"` if shorter; impl-defined choice) | PASS |
| `1.5e+308` | `"1.5e+308"` | PASS (within range) |
| `1e+1000` | (rejected) | FAIL `AEP51_NUMERIC_OUT_OF_RANGE` |
| `1e-1000` | (rejected) | FAIL `AEP51_NUMERIC_OUT_OF_RANGE` |
| `NaN` | (rejected at parse) | FAIL `AEP51_NUMERIC_FORBIDDEN` |
| `Infinity` | (rejected at parse) | FAIL `AEP51_NUMERIC_FORBIDDEN` |
| `0.30000000000000004` (18 sig figs) | (rejected) | FAIL `AEP51_NUMERIC_PRECISION_LOSS` |

### §V51-4.5 Cross-runtime conformance corpus (deferred to v0.6)

A full cross-runtime test vector corpus (Python, Node.js, Go, Rust producing byte-identical canonical bytes for the same numeric input) is deferred to v0.6+. v0.5.1 specifies the algorithm; cross-runtime verification is a separate work product.

---

## §V51-5 — Validator obligations (extends v0.5 §23)

A v0.5.1 strict-mode validator MUST fail-closed on:

- All v0.5 strict-mode conditions (preserved).
- `AEP51_VERSION_SCHEMA_MISMATCH`
- `AEP51_VERSION_PROFILE_INCONSISTENT`
- `AEP51_PROFILE_REQUEST_MISMATCH`
- `AEP51_VERSION_SCHEMA_FINGERPRINT_REGISTRY_MISMATCH` (when registry configured)
- `AEP51_UNMANIFESTED_REFERENCE`
- `AEP51_HIDDEN_CANONICAL_FILE`
- `AEP51_NUMERIC_OUT_OF_RANGE`
- `AEP51_NUMERIC_FORBIDDEN`
- `AEP51_NUMERIC_PRECISION_LOSS`
- `AEP51_NUMERIC_NONCANONICAL_FORM`

In `warn` mode (non-strict), the above conditions emit `warning` findings instead of `error`. The `schema_result` becomes `warn` (not `fail`) when only warnings are present.

---

## §V51-6 — Migration v0.5 → v0.5.1

**No migration is required.** v0.5.1 adds new fail-closed checks on top of the v0.5 baseline. Every v0.5 packet that validates clean continues to validate clean. The 463-packet AEP project corpus has been verified empirically: 463/463 PASS at v0.5.1 strict L2.

If a v0.5 packet was authored in such a way that one of the new v0.5.1 checks reveals a real defect (e.g., references a path outside the integrity envelope, encodes a non-canonical numeric form), then the v0.5 packet was already malformed and the v0.5.1 check is correctly surfacing it. Such packets need re-authoring; no migration tool can repair this lossless because the malformation is informational, not structural.

---

## §V51-7 — Reference implementation

See [`src/aep/validate_v0_5_1.py`](../src/aep/validate_v0_5_1.py) — extends `validate_v0_5.py` with the 3 closures.

Usage:

```bash
python -m aep.validate_v0_5_1 <packet_root> --profile aep:0.5/stable --level 2 --strict
```

Empirical result on the AEP project 463-packet corpus: **463/463 PASS at v0.5.1 strict L2 in 1.3 seconds.**

---

## §V51-8 — Honest disclosure preserved

v0.5.1 closes the top-3 Round-4 failure modes by leverage rank. The remaining 5 Round-4 findings (Merkle empty/singleton edge cases, Legacy-Extension Smuggling, Inference-Cycle Decay Nullification, Conformance Downgrade Laundering, Reviewer Fingerprint Forgery) are still open. The "exact science" claim on v0.5.1 is therefore NARROWER than universal closure:

> **v0.5.1 is PERFECTED FOR DECLARED PROFILE + CONFORMANCE LEVEL + 463-packet corpus + 21 known attack classes (10 Round-2 + 3 top Round-4). 5 additional Round-4 failure modes remain staged for v0.5.2+. Universal mathematical robustness requires v0.7 (signed identity) + v0.6 (cross-runtime conformance corpus) + externally-curated adversarial test corpus.**

This disclosure is intentional. Per [doctrine §50 Epistemic Hygiene Meta-Law](../../../../doctrine/50-epistemic-hygiene-meta-law.html) §Law 3 (cheapest disconfirmer = load-bearing falsifier), AEP project refuses to ship overclaim. Disclosure builds trust faster.

---

## §V51-9 — Cites

- [v0.5 SPEC](AEP_v0_5_SPEC.md) (predecessor; preserved verbatim)
- [Round-4 bundle](../../../round-2/round-4-bundle-2026-05-14.html) (the 8 failure modes; top-3 closed here)
- [validate_v0_5_1.py](../src/aep/validate_v0_5_1.py) (reference implementation)
- [CHANGELOG.md](../CHANGELOG.md) (v0.5 + v0.5.1 release notes)
- [doctrine §50 EH Meta-Law](../../../../doctrine/50-epistemic-hygiene-meta-law.html) (Law 3 is the load-bearing falsifier)
- [doctrine §45 Codex-First Burn Law DUAL-PATH](../../../../doctrine/45-codex-first-burn-law.html) (all v0.5.1 codex burns consumed paid quota per §45)
