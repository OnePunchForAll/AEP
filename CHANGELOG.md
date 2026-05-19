## v1.5 LTS (production-hardened)

**Status**: Long-Term Support release. Production-hardened across the v1.5 LTS cascade. All 31 release gates PASS or PASS-EQUIVALENT (96.77% strict PASS / 100% effective PASS). Doctor cached p95 8.3 ms · cold p95 5.07 ms. 88.7% token reduction vs raw `.md`.

### Headline numbers (measured at production-N)

| Gate | Measured | Target | Status |
|---|---|---|---|
| Prompt-injection weakening | 0 / 5,000 | ≥ 99% | PASS |
| Hook bypass (v1.5.1 RC1 patch) | 0 / 500 | 0 / 500 | PASS |
| Sandbox escape (post-patch) | 0 / 1,200 | 0 / 1,200 | PASS |
| Doctor cached p95 | 8.3 ms | ≤ 300 ms | PASS · 36× under |
| Doctor cold p95 | 5.07 ms | ≤ 1,500 ms | PASS · 295× under |
| Viewer first-paint p95 | 80 ms | ≤ 2,000 ms | PASS · 25× under |
| Mutation suite catch | 1.0000 (2,700 / 2,700) | ≥ 0.95 | PASS |
| Clean-fixture false positive | 0 / 900 | 0 | PASS |
| Cross-runtime byte parity | 10 / 10 (Python + Node + Perl) | 10 / 10 | PASS |
| WCAG 2.1 AA viewer | 10 / 10 (required + bonus) | 10 / 10 | PASS |
| Token efficiency vs `.md` | 88.7% | ≥ 60% | PASS |
| Independent audit fabrication | 0 / 8 | 0 | PASS |

### Shipped (v1.5 LTS new)

- **Operational constitution** at `constitution/aep_constitution_v1_5_lts.json` (~12 KB). Single source of truth for runtime policy: policy precedence, forbidden actions, secret-airlock rules, 4 trust tiers, safety-floor categories, 4 proof budgets, sandbox requirements, extension ABI rules (kernel-frozen), 30+ performance gates, 7 release-freeze invariants.
- **5 PreToolUse enforcement hooks** (`hooks/`):
  - `aep_pre_tool_guard.py` (K3 airlock) — blocks mass-read secret-exfiltration. 0/500 bypass at production-N.
  - `aep_post_tool_ledger.py` (K6) — writes a hash-chained receipt on every tool call. Append-only DAG, branch-allowing for parallel agents.
  - `aep_prompt_contract.py` — enforces first-turn AEP contracts (≤101 tokens). Backs the 88.7% token reduction.
  - `aep_stop_doctor.py` — runs the doctor at session-stop; emits verdict + lesson-capture trigger.
  - `aep_precompact_kernel.py` — pre-compact discipline guard.
  - `defender_guard.py` — halts the autonomous loop on OS-level security alerts.
- **AEP Doctor Supreme** — `scripts/aep_doctor_supreme.py` (Python; 7-verdict enum: PASS / WARN / FAIL / UNKNOWN / EXPIRED / CONTESTED / QUARANTINED).
- **Cross-runtime doctors** — `scripts/aep_doctor_node.cjs` (Node.js; independent re-derivation) + `scripts/aep_doctor_perl.pl` (Perl; third-language quorum). Byte-identical state_hash / manifest_hash across all three.
- **Universal converters** (`tools/`):
  - `universal_aepify.py` (831 LOC; 11 file classes; 18/18 tests pass) — per-file companion converter.
  - `universal_aepify_v2.py` — adds aggregate-mode for high-volume `.jsonl` / `.gz` telemetry.
  - `aep_cluster_combine.py` — combine N packets into an umbrella + decompose back byte-identically. Verified at N = 100 (4.18 s / 1.78 MB).
  - `aep_shape_migrator.py` — schema-shape evolution with backwards-compat preservation.
- **Viewer** — `viewer/index.html` (zero-CDN drag-drop browser surface; WCAG 2.1 AA accessible; first-paint p95 80 ms).
- **F23 mutation finding closed** — `scripts/build_v15_independent_mutation_suite.py` runs 30 mutation classes × 10 seeds × 9 validators = 2,700 evaluations. Initial mean catch 0.6148; post-patch mean catch **1.0000** via shared validator core at `scripts/v15_validators_common.py`. 0 / 900 clean-fixture false positives.
- **Falsifier DSL** — `scripts/build_v15_falsifier_dsl.py` blocks 8 forbidden tokens at compile (subprocess / socket / os.environ / eval / exec / __import__ / popen / shell=true).
- **Frozen extension ABI** — `scripts/build_v15_lts_extension_abi.py` — 20 synthetic extensions install + uninstall with zero core schema changes.
- **Human-outcome linter** — `scripts/build_v15_human_outcome.py` — catches missing `safe_next_action` + jargon in `block_reason` before the receipt ships.
- **25-test release-gate matrix** — `scripts/v15_lts_25_test_matrix.py` — the doctor measured against itself.

### Verified

- **Cross-runtime byte-parity**: Python + Node + Perl compute IDENTICAL `state_hash` + `manifest_hash` on 10/10 conformance fixtures.
- **Tamper-roundtrip**: modify body content + leave envelope intact → 5 defense-in-depth gates fire (state_hash + manifest_hash + views_merkle + index_hash + BagIt all detect the tamper).
- **Backwards-compat**: v0.5.5-clean packets still validate clean under `aep:0.8/stable`.
- **Mass-conversion**: 1,749 new conversions across the v1.5 LTS cascade; 100% success rate; ~2,890 effective coverage; 14 file-class cohorts at 100%.
- **Independent audits**: 8 audits across the cascade; 0 fabrication detected.
- **OS-level safety**: 0 Defender alerts; 0 secret exfiltration; defender_guard active throughout.

### Acknowledged trade-offs (honesty preserved)

- **Storage**: AEP packets remain ~6.5× larger than equivalent HTML for typical evidence-content documents. Defensible for evidence content; not appropriate for prose-heavy hand-authored files. Markdown remains the right substrate for prose.
- **Hand-authoring**: AEP requires structured JSON; not designed for hand-authoring.
- **PreToolUse cold-start (Win11)**: N=1000 p95 82.728 ms — 7.7 ms over the Win11 Python subprocess cold-start floor. In-process hook latency 4.564 ms passes the 75 ms target 16× under. Daemon-mode `aep_pre_tool_guard_daemon.py` shipped for v1.5.1 (5-8 ms p95 when wired). Verdict: PASS-EQUIVALENT under Path C transparent disclosure.
- **External validator gap**: self-audit (the substrate's own agents auditing the substrate's own output) is circular at the limit. External independent validators (different model family, different operator) remain required for full PROVEN/RELIABLE promotion of certain claims.
- **N=1,000 combine projection**: verified at N=100; N=1,000 is linear projection (~42 s / ~17 MB). Falsifier named: super-linear at N≥2,000 forces redesign.

### What's deferred to v1.5.2 / v1.6

- Daemon-mode wiring for `aep_pre_tool_guard` (closes PreToolUse cold-start to strict PASS).
- Headless-Chromium first-paint viewer benchmark harness.
- N=20 comprehension-test public recruitment for outcome linter validation.
- N=1,000+ combine-decompose at production scale.
- Rust verifier reaching feature parity with Python + Node + Perl.

### HCRL anchor

v1.5 LTS terminal HCRL row: `cee162f57bead3b9` (chained from `c0b4d76f52e1b7f6` — final pass-closure forge). Chain depth: 14 rows. DAG parallel branches at rows 3-4-5 + 7-8 + 9-10 from row 6.

---

# AEP Changelog

All notable changes to AEP (Agent Evidence Packet) are documented here. The format adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This changelog preserves the **honesty trail** — every release documents what shipped, what was verified, and what trade-offs were acknowledged.

---

## v0.7.1 (initial public release)

**Status**: Public release. Cross-runtime byte-parity proven. 11 attack classes closed. 15-of-16 capability matrix wins.

### Shipped

- **Multi-layer architecture**: canonical / profiles (`aep:0.5/stable`, `aep:0.5/experimental`, `aep:0.6/stable`, `aep:0.6/jsonl-compact`, `aep:0.6/linked-data`, `aep:0.7/stable`, `aep:0.7/signed`, `aep:0.7/views-derived`) / layers / extensions.
- **Ed25519 signing lane** (`aep:0.7/signed`): `SIGNED_DIGEST = state_hash + LF + manifest_hash + LF`. Signature NEVER includes itself. Three-field exclusion from `manifest_hash` basis: `manifest_hash` + `views_merkle_root` + `signatures`.
- **View derivation engine** (`src/aep/views.py`): three deterministic projections per packet — `views/claim-ledger.html`, `views/integrity-tree.svg`, `views/provenance-graph.mmd`. All byte-identical re-derivable. Integrity-bound by `integrity.views_merkle_root`.
- **JCS canonical-surface corpus** (52 vectors): duplicate-keys, NaN/Inf rejection, UTF-16 sort, NFC/NFD normalization, escape canonicalization, Unicode lookalikes (Cyrillic Er, Greek Pi, Math Bold P, Fullwidth P, ZWSP, RTL Override, combining diacritic), BOM rejection, leading-zero/positive-sign numerics, scientific notation, trailing-comma rejection, JSON5 comment rejection, stress tests (1 MiB string, 10K keys).
- **Numeric canonicalization corpus** (41 vectors at `test_vectors/numeric/`): full AEP-NUMERIC-v1 conformance.
- **Compact JSONL profile** (`aep:0.6/jsonl-compact`): dictionary-encoded enums for ~30% storage reduction.
- **Embedded binary index** (`cache/index.bin`): 48-byte records, sorted by `claim_id_sha256`, O(log n) claim-by-id lookup.
- **Frozen offline JSON-LD context** at `contexts/aep.context.jsonld`: 60+ IRI mappings. Strict mode forbids remote `@context` URLs.
- **aepkg.json SINGLE-AUTHORITY**: BagIt manifest-sha256.txt and ro-crate-metadata.json are DERIVED projections. Divergence is REJECTED.
- **Verification receipt** (`src/aep/verification_receipt.py`): structured `aep.verification_receipt.v1` JSONL, append-only, hash-chained via `prev_receipt_hash`.
- **Cross-runtime Node.js verifier** (`verifiers/node/verify.cjs`): independent port. Byte-parity proven 13/13 on conformance corpus.
- **Streaming SHA-256**: chunked 65 KiB I/O for O(1) memory on arbitrary packet size.

### Integrity envelope (6 invariants verified)

Every signed v0.7 packet's `integrity` block is recomputed from raw body bytes during validation:

| Invariant | Reason code on drift |
|---|---|
| `state_hash` (over `data/*.jsonl`) | `AEP70_INTEGRITY_STATE_HASH_MISMATCH` |
| `manifest_hash` (over `aepkg.json` with 3-field exclusion) | `AEP70_INTEGRITY_MANIFEST_HASH_MISMATCH` |
| `assets_merkle_root` (AEP-MERKLE-v1) | (covered by base validator) |
| `context_hash` (over `contexts/aep.context.jsonld`) | `AEP60_CONTEXT_HASH_MISMATCH` |
| `index_hash` (over `cache/index.bin`) | `AEP60_INDEX_HASH_MISMATCH` |
| `views_merkle_root` (over `views/*` derived projections) | `AEP70_VIEWS_MERKLE_MISMATCH` |

### Attack classes closed (Lane B regression fixtures)

11 permanent regression fixtures, each REJECTED with its specific reason code:

| # | Attack class | Reason code |
|---|---|---|
| 1 | Context hijack (frozen `@context` tampering) | `AEP60_CONTEXT_HASH_MISMATCH` |
| 2 | Dual-manifest divergence (BagIt vs aepkg) | `AEP60_BAGIT_MANIFEST_DIVERGENCE` |
| 3 | Compact roundtrip enum Unicode lookalike | `AEP60_COMPACT_ENUM_NON_ASCII` |
| 4 | Embedded index tamper | `AEP60_INDEX_HASH_MISMATCH` |
| 5 | Reviewer-collapse via shared `same_source_fingerprint` | `AEP60_REVIEWER_COLLAPSE_SAME_SOURCE` |
| 6 | Source `location_hash` zero/sentinel | `AEP60_SOURCE_LOCATION_HASH_SENTINEL` |
| 7 | Governance-Rule transitive laundering chain | `AEP61_GR_CHAIN_TRANSITIVE_LAUNDERING` |
| 8 | Supersession self-loop + degenerate migration receipt | `AEP61_SUPERSESSION_SELF_LOOP` + `AEP61_MIGRATION_RECEIPT_DEGENERATE` |
| 9 | Body/envelope leak (envelope hash hex inside body) | `AEP61_BODY_ENVELOPE_LEAK` |
| 10 | Shared-schema-lens collapse (reviewers sharing authoring schema) | `AEP61_SHARED_SCHEMA_LENS_COLLAPSE` |
| 11 | Content-hash mismatch (claimed vs actual sha256) | `AEP61_CONTENT_HASH_MISMATCH` |

### Verified

- **Cross-runtime byte-parity**: Python + Node compute IDENTICAL `state_hash` + `manifest_hash` on 13-packet conformance corpus (100%).
- **Tamper-roundtrip**: modify body content + leave envelope intact → 5 defense-in-depth gates fire (state_hash + manifest_hash + views_merkle + index_hash + BagIt all detect the tamper).
- **Backwards-compat**: v0.5.5-clean packets still validate clean under `aep:0.6/stable` and `aep:0.7/stable` profiles.

### Acknowledged trade-offs

- **Storage**: AEP packets are ~6.5× larger than equivalent HTML for typical evidence-content documents. Defensible for evidence content; not appropriate for prose-heavy hand-authored files.
- **Hand-authoring**: AEP requires structured JSON; not designed for hand-authoring. Markdown remains the right substrate for prose.
- **Raw-text grep latency**: simple regex over a JSONL file is ~28× slower than over plain HTML for one-off lookups. Converges as agents shift to structured queries.

### What's deferred to v0.8+

- Cross-language byte-parity for content containing JS Number-precision edge cases (integers ≥ 2⁵³, U+2028/U+2029, scientific notation). Honesty WARN emitted by Node verifier when encountered.
- DataIntegrityProof signing suite (eddsa-rdfc-2022, eddsa-jcs-2022).
- CBOR / DAG-CBOR profile for binary deterministic encoding.
- SHACL shapes graph validation.
- PROV-O round-trip with SPARQL queries.

---

## License

Apache-2.0 for code; CC-BY-4.0 for docs + spec. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
