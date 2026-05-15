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
