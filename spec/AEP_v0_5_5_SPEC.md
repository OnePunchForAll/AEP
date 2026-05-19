# AEP v0.5.5 Specification — Consolidated Publication-Ready

**Status**: SHIPPABLE. Consolidates v0.5 + v0.5.1 + v0.5.3 + v0.5.4 into a single coherent specification suitable for first public publication of the AEP standard.
**Predecessor**: AEP v0.5.4 (2026-05-14 final patch-version; 24 cumulative reason codes across the v0.5.x series).
**Authors**: operator ([the AEP project](https://x.com/AEPproject)) + the agentic substrate (Claude Opus 4.7) inside AEP project's 10-agent legion.
**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).
**Profile**: `aep:0.5/stable` and `aep:0.5/experimental`.

This file is the canonical reference for AEP v0.5.5 publication. v0.5..v0.5.4 specs (AEP_v0_5_SPEC.md, AEP_v0_5_1_SPEC.md) remain in this repo as the honesty-trail provenance — they document the staged evolution. v0.5.5 is what an external consumer SHOULD read first.

---

## §0 — Reader's guide

- **§1–§20**: same numbered structure as v0.5 spec (predecessor). Each section notes any v0.5.1/v0.5.3/v0.5.4 amendments inline.
- **§21–§24**: v0.5.x additions (channel/compatibility, migration, validator obligations, non-guarantees).
- **§A–§C**: Appendix A test vectors, Appendix B compatibility matrix, Appendix C conformance levels.
- **§V53–§V54**: post-publication closures applied in v0.5.3 / v0.5.4 sub-sprints.

If you're an external implementer reading AEP for the first time, this file (`AEP_v0_5_5_SPEC.md`) is the authoritative spec. Predecessor files document the honesty trail but should not be used as implementation targets.

---

## §1–§20 — Inherited from v0.5

The 8 design axioms, reliability labels, scope labels, axis-B action labels, package identity, canonical files, JSONL record rules, source/span/claim/relation/event/review/validation records, integrity envelope (state_hash + manifest_hash + assets_merkle_root), strict JSON canonical profile (RFC 8785 + AEP extras), threat model, promotion rule, conformance test suite, versioning + compatibility matrix, migration tooling, validator obligations, and non-guarantees are all inherited from v0.5 verbatim. See [`AEP_v0_5_SPEC.md`](AEP_v0_5_SPEC.md) §1–§24 for the unchanged content.

The v0.5.5 consolidation makes ONE additive change in this range: **axiom 9 (anchor diversity) and axiom 10 (time-validated evidence) introduced in v0.5 are kept canonical AND extended with the v0.5.4 reliability↔axis-B consistency requirement (§V54-2 below) which is a corollary of axiom 9 applied to the axis-B disposition layer.**

---

## §V53 — Round-5 Top-3 Closures (originally AEP_v0_5_1_SPEC.md §V51-2/3/4 + post-publication v0.5.3 amendments)

### §V53-1 — Schema/Profile Binding Hard-Fail

Closes Round-2 Attack #1 (parser-split hashing) at the version/profile binding layer + Round-4 Attack #1 (Version-Shape Crossfade) + Round-4 Attack #4 (Profile Boundary Laundering).

Normative requirements:

1. Manifest `aep_version` and `profile` MUST be internally consistent — declaring `aep_version="0.5"` with `profile="aep:0.4/jsonld"` is fail-closed (`AEP51_VERSION_PROFILE_INCONSISTENT`).
2. Validator-requested profile MUST match manifest profile exactly — no silent acceptance of `aep:0.5/experimental` under `--profile aep:0.5/stable` (`AEP51_PROFILE_REQUEST_MISMATCH`).
3. In strict L2 a packet declaring v0.5 MUST exhibit at least ONE per-record universal v0.5 marker (`axis_b_action` or `decision_time_revalidation_required`) on at least one canonical CLAIM record. `manifest.packet_epoch` alone is INSUFFICIENT (`AEP53_MANIFEST_EPOCH_INSUFFICIENT_SHAPE`).
4. Zero-claim sparse packets are exempt from rule 3 and accepted under L1-style conformance with an honest WARN.

### §V53-2 — Strict Canonical Path Resolver + Traversal Rejection

Closes Round-4 Attack #2 (asset Merkle ambiguity) at the path-reference layer + Round-4 Attack #7 (state-hash coverage evasion).

Normative requirements (function `_canonicalize_in_packet_path_strict`):

1. Strip `in-packet:` prefix.
2. Reject absolute paths (`/`, `\`) and URI schemes (`://`) → `AEP53_PATH_ALIAS_REJECTED`.
3. Reject `..` and `.` path segments → `AEP53_PATH_TRAVERSAL_REJECTED`.
4. Reject percent-encoded traversal (`%2e%2e`, `%2f`).
5. Reject case-aliased manifest references (`aepkg.json` is case-exact).
6. Apply uniformly across `source.location`, `span.selector`, `event.target`, `relation` paths, and `review` path fields.

### §V53-3 — GR+GO Justification Integrity End-to-End

Closes Round-4 Attack #5 (GO-Path Laundering via GOVERNANCE_RULE) at the disposition-evidence layer.

Normative requirements: for every claim with `reliability=GOVERNANCE_RULE` AND `axis_b_action=GO`:

1. `go_justification_claim_ids` MUST exist AND be non-empty → `AEP53_GR_GO_EMPTY_JUSTIFICATION`.
2. Every referenced `claim_id` MUST exist in the packet → `AEP53_GR_GO_DANGLING_JUSTIFICATION`.
3. ≥1 referenced claim MUST have `reliability != GOVERNANCE_RULE` (prevents recursive GR-only chains) → `AEP53_GR_GO_JUSTIFICATION_IS_GR`.

---

## §V54 — Round-5 Remaining Closures (originally implemented in v0.5.4)

### §V54-1 — Deep-Migration Receipt Structural Validation

Closes Round-5 Attack #5 (Deep-Migration Provenance Forgery) at the structural layer. Full cryptographic verification of pre-state remains deferred to v0.7 signed identity.

Normative requirements: when `extensions.aep:deep_migrated_from` is set, manifest MUST also carry `extensions.aep:deep_migration_receipt` with required fields:

- `pre_state_hash` — must be `sha256:` + 64 hex digits.
- `post_state_hash` — must be `sha256:` + 64 hex digits.
- `tool` — string identifying the migration tool.
- `tool_version` — semver-shaped string.
- `timestamp` — RFC 3339 UTC.

Missing receipt is WARN-level (`AEP54_DEEP_MIGRATION_RECEIPT_MISSING`); malformed receipt is ERROR-level (`AEP54_DEEP_MIGRATION_RECEIPT_MALFORMED`).

### §V54-2 — Reliability ↔ Axis-B Semantic Consistency

Closes Round-5 Attack #6 (Reliability ↔ Axis-B Contradiction) at the semantic-consistency layer.

Canonical `RELIABILITY_AXIS_B_VALID` table (operator-approved 2026-05-14):

| Reliability | Valid Axis-B Actions |
|---|---|
| `PROVEN_RELIABLE` | GO · EXPERIMENT · EXPLORE |
| `STRONGLY_PLAUSIBLE` | GO · EXPERIMENT · EXPLORE |
| `PLAUSIBLE` | EXPERIMENT · EXPLORE · HALT |
| `EXPERIMENTAL` | EXPERIMENT · EXPLORE |
| `ASSUMPTION` | EXPLORE · HALT |
| `SPECULATIVE_FRONTIER` | EXPLORE · HALT |
| `CONFLICTED` | HALT |
| `GOVERNANCE_RULE` | GO · FORBIDDEN |
| `DANGEROUS_NOT_WORTH_DOING` | FORBIDDEN |
| `UNKNOWN` | (none — must NOT carry axis_b_action) |

For every claim with both `reliability` and `axis_b_action` populated, validator checks the combination. Forbidden combinations emit `AEP54_RELIABILITY_AXIS_B_CONTRADICTION`.

### §V54-3 — Epoch + Supersedes Structural Checks

Closes Round-5 Attack #7 (Epoch Replay / Non-Monotonic Lineage) at the structural layer. Full cross-packet monotonicity remains deferred to v0.7 signed lineage.

Normative requirements:

1. `packet_epoch` MUST be a positive integer (or Decimal whole-value post-strict-canonical-parse). Reject non-positive or non-integer → `AEP54_EPOCH_INVALID_VALUE`.
2. `supersedes_packet_id` MUST match canonical pattern `^aepkg:[A-Za-z0-9._:-]+$` → `AEP54_SUPERSEDES_MALFORMED`.
3. If `supersedes_packet_id` is set: `packet_epoch` MUST be > 1 → `AEP54_EPOCH_NON_MONOTONIC`.

---

## §V55-CONSOLIDATION — Honesty Trail (this section is unique to v0.5.5)

v0.5.5 is the publication consolidation of the v0.5.x series. The series shipped 9 commits across 4 cycles, surfacing and closing 18 attack classes under two-lane discipline (Lane A corpus conformance + Lane B adversarial conformance).

### v0.5.x cycle summary

| Version | Date | Cycle | Lane A | Lane B fixtures | Closures shipped |
|---|---|---|---|---|---|
| v0.5 | 2026-05-14 | Perfection sprint | 463/463 PASS (1.3s, FALSE pass — corpus was v0.3-shape under v0.5 declaration) | none | All Round-2 / Round-3 closures (10 attacks) |
| v0.5.1 | 2026-05-14 | Hot-patch after Round-4 PARTIAL falsification | (initially regressed; see v0.5.2) | none | Schema/Profile binding, Artifact closure, AEP-NUMERIC-v1 |
| v0.5.2 | 2026-05-14 | Deep-migration to add per-record v0.5 fields | 463/463 PASS (real, 42.9s) — Lane-A-only | none | (migration tool + validator relaxations) |
| v0.5.3 | 2026-05-14 | Round-5 top-3 + adopt two-lane discipline | 462 PASS + 1 WARN + 0 FAIL | 3 (GR+GO empty, path traversal, manifest-only shape) | GR+GO integrity, path resolver, shape gate |
| v0.5.4 | 2026-05-14 | Round-5 remaining + two-lane PROVEN/RELIABLE | 462 PASS + 1 WARN + 0 FAIL | +3 (provenance forgery, reliability↔axis-B, epoch replay) → cumulative 6 | Deep-migration receipt, reliability/axis-B consistency, epoch monotonicity |
| **v0.5.5** | **2026-05-14** | **Consolidated publication-ready** | **462/463 corpus PASS + 1 WARN + 0 FAIL** | **6 cumulative permanent regression fixtures** | (consolidation only; no new closures) |

### Cumulative reason codes shipped (24)

10 from v0.5 / v0.5.1 (AEP51_*) + 6 from v0.5.3 (AEP53_*) + 6 from v0.5.4 (AEP54_*) + 2 from AEP-NUMERIC-v1 carry-over = 24 fail-closed reason codes mechanically enforced.

### Permanent Lane B regression fixture set

`tests/lane_b/` (relative to the repo root):

1. `atk-gr-go-empty.aepkg/` — exercises §V53-3 (GR+GO empty justification)
2. `atk-path-traversal.aepkg/` — exercises §V53-2 (path traversal)
3. `atk-manifest-only-shape.aepkg/` — exercises §V53-1 (version-shape strictness)
4. `atk-provenance-forgery.aepkg/` — exercises §V54-1 (receipt missing)
5. `atk-reliability-axis-b-contradiction.aepkg/` — exercises §V54-2 (contradiction)
6. `atk-epoch-replay.aepkg/` — exercises §V54-3 (epoch non-monotonic)

Any future closure ships only after BOTH:
- Lane A: 463-packet corpus produces 0 fail-closed errors (warns are acceptable when honestly documented).
- Lane B: all 6 existing fixtures + the new fixture(s) for the closure produce the expected reason codes.

### Two-lane discipline (canonical doctrine)

Established in sibling-60; promoted to PROVEN/RELIABLE in sibling-61. Every closure ships ONLY after BOTH lanes pass. Lane B fixture set grows monotonically by construction; regressions are caught mechanically, not narratively.

### What v0.5.5 does NOT close (honest disclosure)

- **Cross-packet epoch monotonicity** (chain across distinct packets) → requires packet registry → v0.7 signed lineage.
- **Cryptographic verification of deep-migration receipts** (proves pre-state actually existed) → requires operator trust root → v0.7 signed identity.
- **Cross-runtime AEP-NUMERIC-v1 conformance** (Python+Node+Go+Rust byte-identical canonical bytes) → v0.6. Test vector corpus already landed at [`test_vectors/v0_5/A.10-numeric-canonicalization/`](../test_vectors/v0_5/A.10-numeric-canonicalization/) (35 vectors, 8 categories).
- **Externally-curated adversarial test corpus** from researchers outside AEP project cascade → v0.6+. The Lane B fixtures are operator-curated only.
- **Round-6+ findings** — by construction; the falsifier-vs-closer balance is structural, not terminal.

---

## §V55-PUBLICATION — What an external implementer needs

To implement AEP v0.5.5:

1. **Read this file** (`AEP_v0_5_5_SPEC.md`) for the consolidated normative spec.
2. **Read the reference implementation** at [`../src/aep/`](../src/aep/):
   - `validate_v0_4.py` — backward-compat baseline.
   - `validate_v0_5.py` — v0.5 axioms + Round-2 / Round-3 closures.
   - `validate_v0_5_1.py` — adds Round-4 + Round-5 closures (post-v0.5.1 hot-patches). This file's `validate_v0_5_1` function is the **unified v0.5.5 validator entry point** despite the v0.5.1 name in the filename (kept for git-history continuity).
   - `convert_v0_3_to_v0_5.py` — lossless v0.3/v0.4 → v0.5 migration (manifest level).
   - `convert_v0_5_shallow_to_deep.py` — v0.5 deep-migration (per-record v0.5 fields + receipt).
3. **Run the conformance test vectors** under [`../test_vectors/v0_5/`](../test_vectors/v0_5/).
4. **Run the Lane B regression fixtures** under [`../tests/lane_b/atk-*.aepkg/`](../tests/lane_b/) — your validator MUST reject each with the expected reason code. The conformance test driver at [`../tests/v0_5/test_conformance.py`](../tests/v0_5/test_conformance.py) automates this.

### Conformance levels (unchanged from v0.5)

- **Level-1**: v0.4 backward-compat (axioms 1-8 + v0.4 fail-closed list).
- **Level-2**: v0.5 full (axioms 1-10 + Round-2 / Round-3 / Round-4 / Round-5 mitigations + AEP-NUMERIC-v1 strict).
- **Level-3**: L2 + experimental features + execution_inputs_manifest.

### Production guidance

Run validators with `--profile aep:0.5/stable --level 2 --strict`. This is the recommended baseline for production deployments using AEP-validated packets in decision pipelines.

---

## §V55-CITES

- AEP v0.5 spec (predecessor; preserved): [`AEP_v0_5_SPEC.md`](AEP_v0_5_SPEC.md)
- AEP v0.5.1 spec (hot-patch; preserved): [`AEP_v0_5_1_SPEC.md`](AEP_v0_5_1_SPEC.md)
- v0.5 reference validator: [`../src/aep/validate_v0_5.py`](../src/aep/validate_v0_5.py)
- v0.5.x unified validator: [`../src/aep/validate_v0_5_1.py`](../src/aep/validate_v0_5_1.py)
- v0.3/v0.4 → v0.5 migration: [`../src/aep/convert_v0_3_to_v0_5.py`](../src/aep/convert_v0_3_to_v0_5.py)
- v0.5 deep-migration: [`../src/aep/convert_v0_5_shallow_to_deep.py`](../src/aep/convert_v0_5_shallow_to_deep.py)
- Conformance test vectors: [`../test_vectors/v0_5/`](../test_vectors/v0_5/)
- Lane B regression fixtures: [`../tests/lane_b/`](../tests/lane_b/)
- Conformance test driver: [`../tests/v0_5/test_conformance.py`](../tests/v0_5/test_conformance.py)
- AEP-NUMERIC-v1 runner: [`../src/aep/run_numeric_vectors.py`](../src/aep/run_numeric_vectors.py)
- CHANGELOG (full honesty trail across v0.5 → v0.5.5): [`../CHANGELOG.md`](../CHANGELOG.md)
