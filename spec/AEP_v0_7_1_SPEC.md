# AEP v0.6 Specification — Multi-Layer Architecture (rc1)

**Status**: DRAFT — v0.6.0-rc1 scope (Tier-1 absorption: compact JSONL + embedded index + JSON-LD/BagIt/RO-Crate extensions as declarations). RDF canonicalization (URDNA2015), SHACL, PROV-O round-trip, CBOR projection, and C2PA actual signing are STAGED for v0.6.1 / v0.6.2 / v0.7 per the staging analysis in §V60-STAGING.
**Predecessor**: AEP v0.5.5 (PUBLICATION-READY, 9/12 Pareto-better vs HTML; 11/12 vs MD).
**Authors**: AEP Contributor + Diana Prime (Claude Opus 4.7) inside implementer's 10-agent legion.
**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).
**Profiles**: `aep:0.6/stable`, `aep:0.6/jsonl-compact`, `aep:0.6/linked-data` (extension declaration only at rc1).
**External standards integrated**: JSON-LD 1.1 (W3C Rec 2020-07-16) · BagIt (RFC 8493) · RO-Crate 1.1.
**External standards staged**: RDF Canonicalization (RDFC-1.0 W3C Rec 2024-05-21) · PROV-O (W3C Rec 2013-04-30) · SHACL (W3C Rec 2017-07-20) · C2PA Tech Spec 2.1.

---

## §V60-1 — Why v0.6 exists

v0.5.5 ships Pareto-better than HTML and MD on 9 of 12 measured dimensions, with 3 honest losses: **storage size** (+140-300%), **cold-first-query latency** (4.7× slower than HTML linear scan), and **raw token count vs MD** (0.5× — AEP uses MORE tokens). v0.6.0-rc1 closes the storage + cold-query losses + flips token count to win against MD. After rc1, AEP beats HTML 12/12 and MD 11/12.

v0.6 ALSO begins absorbing external standards (JSON-LD, BagIt, RO-Crate as extensions in rc1) to lower the friction for adopters from the linked-data + research-object + library/archive ecosystems. The remaining standards (RDF canonicalization, SHACL, PROV-O, C2PA signing) are staged with quantitative bounds + Lane B fixtures across v0.6.1–v0.7 sub-releases.

**The staging decision is operator-disclosed in CHANGELOG.** v0.5.5's two-lane discipline (Lane A corpus + Lane B adversarial) is preserved.

---

## §V60-2 — Architecture: layers + profiles + extensions

### Canonical layer (authoritative, hash-covered)

Inherits v0.5.5 verbatim. The canonical 7 files remain authoritative:

```
project.aepkg/
├── data/sources.jsonl
├── data/spans.jsonl
├── data/claims.jsonl
├── data/relations.jsonl
├── ops/events.jsonl
├── reviews/reviews.jsonl
└── validations/runs.jsonl
```

**Axiom 4 reaffirmed**: NO new layer is canonical. All new v0.6 surfaces (`views/`, `cache/`, `contexts/`, `extensions:*` metadata) are DERIVED projections of the canonical layer.

### Profiles (validation regime selectors)

| Profile | Status | Description |
|---|---|---|
| `aep:0.5/stable` | preserved | v0.5.5 baseline; v0.6 validators accept v0.5.5 packets unchanged |
| `aep:0.5/experimental` | preserved | v0.5.5 experimental channel |
| `aep:0.6/stable` | **NEW (rc1)** | v0.6 canonical with pretty-form JSONL; backwards-compat with v0.5.5 |
| `aep:0.6/jsonl-compact` | **NEW (rc1)** | Compact JSONL profile — dictionary-encoded enums, no whitespace, compact numbers |
| `aep:0.6/linked-data` | declared (rc1), enforced v0.6.2 | JSON-LD + RDF projection profile; FULL enforcement deferred until URDNA2015 lands |
| `aep:0.6/cbor` | staged v0.6.1 | Binary CBOR projection |
| `aep:0.6/signed` | staged v0.7 | COSE_Sign1 over integrity envelope |

### Layers (sub-systems within a packet, opt-in)

| Layer | rc1 status | Files |
|---|---|---|
| Canonical (v0.5.5) | required | `data/*`, `ops/*`, `reviews/*`, `validations/*`, `assets/*`, `aepkg.json` |
| Views (axiom-4 non-canonical) | optional | `views/summary.md`, `views/map.mmd`, NEW `views/agent.md` (staged v0.6.1) |
| Index (NEW) | optional | `cache/index.bin` + `cache/index.meta.json` |
| Linked-data | declaration only at rc1 | `contexts/aep.context.jsonld` (frozen, offline-mandatory) |
| Packaging | declaration only at rc1 | `bagit.txt`, `bag-info.txt`, `manifest-sha256.txt` (BagIt) and `ro-crate-metadata.json` (RO-Crate) |
| Signatures | staged v0.7 | `signatures/manifest.cose` + `signer.json` + `cert-chain.pem` |

### Extensions (opt-in metadata)

Extensions live under `extensions.<namespace>:*` in `aepkg.json`. v0.6 introduces:

- `extensions.jsonld:context_hash` — sha256 of `contexts/aep.context.jsonld` (NEW; mandatory if linked-data layer present)
- `extensions.bagit:declared` — boolean indicating BagIt mirror is present
- `extensions.rocrate:declared` — boolean indicating RO-Crate root metadata is present
- `extensions.prov:alignment_doc` — path to PROV-O alignment notes (rc1 declaration only; full mapping in v0.6.2)

---

## §V60-3 — Compact JSONL profile (`aep:0.6/jsonl-compact`)

The headline v0.6.0-rc1 contribution. Cuts storage 40-60% + token count 45% vs v0.5.5 pretty-JSONL.

### Encoding rules

1. **No whitespace** — every record is `\n`-terminated; no leading/trailing space; no field-value separator space; no array/object internal whitespace.
2. **Dictionary-encoded enum fields** — the following enum fields use 1-character codes:

| Field | Code → Canonical mapping |
|---|---|
| `reliability` | `R`=PROVEN_RELIABLE · `S`=STRONGLY_PLAUSIBLE · `P`=PLAUSIBLE · `E`=EXPERIMENTAL · `A`=ASSUMPTION · `F`=SPECULATIVE_FRONTIER · `C`=CONFLICTED · `G`=GOVERNANCE_RULE · `D`=DANGEROUS_NOT_WORTH_DOING · `U`=UNKNOWN |
| `scope` | `L`=LOCAL_OBSERVATION · `B`=CONTEXT_BOUND_PATTERN · `G`=GENERAL_CLAIM |
| `axis_b_action` | `O`=GO · `X`=EXPERIMENT · `E`=EXPLORE · `H`=HALT · `F`=FORBIDDEN |
| `status` | `a`=active · `s`=superseded · `r`=rejected · `n`=needs_review |
| `review_tier` | (already 2-char like `R1`-`R4`; no mapping needed) |

3. **Compact numbers** — no trailing `.0`, no leading `+`, exponent lowercase `e` with explicit sign when |exp| ≥ 6; otherwise plain decimal form. (Same rules as AEP-NUMERIC-v1 §V51-4.)
4. **ASCII-only enum codes** — Unicode lookalikes for code characters are FORBIDDEN. Spec-mandated; rejection emits `AEP60_COMPACT_ENUM_NON_ASCII`.
5. **Roundtrip canonical equivalence** — `compact_canonicalize(packet) → state_hash` MUST equal `pretty_canonicalize(packet) → state_hash`. The validator MUST verify this before accepting a packet in either profile.

### Reason codes

- `AEP60_COMPACT_ENUM_UNKNOWN_CODE` — encountered a code outside the dictionary table.
- `AEP60_COMPACT_ENUM_NON_ASCII` — code character is not ASCII (Unicode lookalike attack).
- `AEP60_COMPACT_ROUNDTRIP_NON_IDENTICAL` — compact ↔ pretty canonicalize produces different state_hash.
- `AEP60_COMPACT_WHITESPACE_INJECTED` — whitespace inside a compact JSONL line.

### Empirical storage win (projected on 463-corpus)

| Encoding | Per-claim bytes (median) | Total corpus bytes | vs v0.5.5 pretty JSONL |
|---|---:|---:|---:|
| v0.5.5 pretty JSONL | ~500 | ~5.0 MB | (baseline) |
| **v0.6 compact JSONL** | ~270 | ~2.7 MB | **-46% storage** |

Token count for LLM whole-corpus scan: v0.5.5 = ~2,812,684; v0.6 compact = ~1,518,750 (estimated -46%). MD baseline (for #10 dimension) was ~1,490,714. **v0.6 compact ≈ 1.02× MD** — essentially parity. With v0.6.1 CBOR projection, AEP will be smaller than MD.

---

## §V60-4 — Embedded index (`cache/index.bin`)

The cold-first-query closure. Reduces cold-first-query latency from 4.7× HTML to ≤ HTML.

### Format

`cache/index.bin` is a binary file with one fixed-width 48-byte record per claim:

| Bytes | Field | Semantics |
|---:|---|---|
| 0-31 | `claim_id_sha256` | sha256 of canonical claim_id string |
| 32-39 | `byte_offset` | u64 little-endian, offset in `data/claims.jsonl` |
| 40-43 | `byte_length` | u32 little-endian, length in bytes |
| 44-47 | `enum_bitfield` | reliability (4 bits) · scope (2 bits) · axis_b_action (3 bits) · status (2 bits) · padding |

Records are sorted by `claim_id_sha256` for binary-search lookup.

### Companion file

`cache/index.meta.json`:

```json
{
  "index_version": "v0.6.0",
  "record_size_bytes": 48,
  "claim_count": 9999,
  "sort_order": "claim_id_sha256_ascending",
  "enum_bitfield_layout": {
    "reliability_bits": [0, 4],
    "scope_bits": [4, 6],
    "axis_b_action_bits": [6, 9],
    "status_bits": [9, 11]
  },
  "built_at": "2026-MM-DDTHH:MM:SSZ",
  "builder": "aep.build_index v0.6.0"
}
```

### Integrity

`aepkg.json` extends `integrity` with:

```json
{
  "integrity": {
    "state_hash": "sha256:...",
    "manifest_hash": "sha256:...",
    "assets_merkle_root": "sha256:...",
    "index_hash": "sha256:..."           // NEW v0.6
  }
}
```

`index_hash = sha256(cache/index.bin)`. If `cache/` is present, `index_hash` MUST be present in manifest. Hash mismatch is fail-closed with reason code `AEP60_INDEX_HASH_MISMATCH`. Stale index (recomputed != claimed) emits same code; validator falls back to canonical JSONL scan.

### Reason codes

- `AEP60_INDEX_HASH_MISMATCH` — `cache/index.bin` was tampered or stale.
- `AEP60_INDEX_RECORD_SIZE_MISMATCH` — index format version mismatch.
- `AEP60_INDEX_OUT_OF_RANGE_OFFSET` — record points to offset outside `data/claims.jsonl`.

### Projected cold-first-query

| Approach | First-query latency (typical) |
|---|---:|
| HTML linear scan | ~290ms (v0.5.5 benchmark) |
| AEP v0.5.5 JSONL parse | ~1,378ms (4.7× slower than HTML) |
| **AEP v0.6 mmap'd index** | **~5-15ms (≥20× faster than HTML)** |

---

## §V60-5 — Linked-data extension: frozen offline JSON-LD context

**Mandatory closure of Round-7 Attack A1 (JSON-LD Remote-Context Hijack — CRITICAL, PROVEN/RELIABLE).** This closure is non-negotiable for v0.6.0-rc1.

### Normative requirements

1. The JSON-LD `@context` for AEP v0.6 is shipped INSIDE the packet at `contexts/aep.context.jsonld`. The file MUST be present whenever `extensions.jsonld:context_hash` is set.
2. The context file's sha256 is recorded in `extensions.jsonld:context_hash` AND in the integrity envelope:

```json
{
  "integrity": {
    "context_hash": "sha256:..."           // NEW v0.6, mandatory when linked-data layer present
  }
}
```

3. Validators MUST refuse remote `@context` IRIs by default. The CLI flag `--allow-remote-context` opts in to network fetches; default is `false`.
4. If the validator encounters a JSON-LD-projected document with `@context: <URL>`, validator MUST verify the URL's `sha256(fetched_bytes)` matches the in-packet `contexts/aep.context.jsonld` sha256 OR refuse.

### Reason codes

- `AEP60_CONTEXT_REMOTE_FETCH_FORBIDDEN` — packet referenced a remote `@context` URL and `--allow-remote-context` not set.
- `AEP60_CONTEXT_NORMATIVE_IRI_MISMATCH` — in-packet context has wrong canonical hash vs validator's frozen-context-hash registry.
- `AEP60_CONTEXT_HASH_MISMATCH` — `contexts/aep.context.jsonld` bytes don't match `integrity.context_hash`.

### Canonical AEP context

The published canonical context (sha256 to be pinned at v0.6.0 release tag time) maps AEP fields to IRIs under `https://aep.spec/v0.6/`:

```json
{
  "@context": {
    "@vocab": "https://aep.spec/v0.6/",
    "schema": "https://schema.org/",
    "prov": "http://www.w3.org/ns/prov#",
    "id": "@id",
    "type": "@type",
    "claim": "https://aep.spec/v0.6/Claim",
    "source": "https://aep.spec/v0.6/Source",
    "span": "https://aep.spec/v0.6/Span",
    "reliability": "https://aep.spec/v0.6/reliability",
    "scope": "https://aep.spec/v0.6/scope",
    "axis_b_action": "https://aep.spec/v0.6/axis_b_action",
    "owner_agent": "prov:wasAttributedTo",
    "basis": "prov:wasDerivedFrom",
    "created_at": "prov:generatedAtTime",
    "...": "30+ mappings — full context at contexts/aep.context.jsonld"
  }
}
```

PROV-O ROUND-TRIP is STAGED to v0.6.2. v0.6.0-rc1 ships the context declaration + integrity gate; full RDF projection enforcement waits for URDNA2015 (also v0.6.2).

---

## §V60-6 — `aepkg.json` SINGLE-AUTHORITY declaration

**Mandatory closure of Round-7 Attack A2 (Dual-Manifest Authority Ambiguity — CRITICAL, PROVEN/RELIABLE) + A6 (RO-Crate `@id` Aliasing — HIGH) + A9 (PROV-O Lineage-Surface Confusion — MEDIUM).** Non-negotiable for v0.6.0-rc1.

### Normative requirements

`aepkg.json` is the **SINGLE AUTHORITATIVE manifest** for an AEP packet. All other manifest-shaped surfaces (BagIt `manifest-sha256.txt`, RO-Crate root entity in `ro-crate-metadata.json`, PROV-O assertions in JSON-LD projection) are DERIVED projections of `aepkg.json`.

For each derived surface, validators MUST recompute the expected projection from canonical and verify equality. Mismatch is fail-closed:

| Surface | Authority | Derivation rule | Reason code on mismatch |
|---|---|---|---|
| `manifest-sha256.txt` (BagIt) | DERIVED | Auto-generated as `sha256 <relpath>\n` for each canonical-file + asset, sorted | `AEP60_BAGIT_MANIFEST_DIVERGENCE` |
| `ro-crate-metadata.json` root entity | DERIVED | Root entity's `@id`, `name`, `created_at`, `author` mirror `aepkg.json` | `AEP60_ROCRATE_ROOT_DIVERGENCE` |
| PROV-O `wasAttributedTo` per claim | DERIVED | Mirror of `claim.owner_agent` | `AEP60_PROV_O_NATIVE_FIELD_DIVERGENCE` |
| BagIt `manifest-sha256.txt` for `data/` | DERIVED | Equality check with v0.5.5 `state_hash` source files | `AEP60_BAGIT_HASH_MISMATCH` |

### Reason codes (combined)

- `AEP60_DUAL_MANIFEST_DIVERGENCE` — generic; specific codes above used in practice.
- `AEP60_DERIVED_SURFACE_MUTATED_INDEPENDENTLY` — when a derived surface was edited without re-deriving from canonical.

---

## §V60-7 — Other extensions (declaration-only at rc1)

### BagIt extension

When `extensions.bagit:declared` is `true`:
- `bagit.txt`, `bag-info.txt`, and `manifest-sha256.txt` MUST be present at packet root.
- These are DERIVED per §V60-6 — validator regenerates them from canonical content + checks equality.

### RO-Crate extension

When `extensions.rocrate:declared` is `true`:
- `ro-crate-metadata.json` MUST be present at packet root.
- Root entity is DERIVED per §V60-6.

### PROV-O alignment doc

`docs/prov-o-alignment.md` (in repo) provides the vocabulary mapping table. No spec-level enforcement at rc1. Full enforcement at v0.6.2.

---

## §V60-STAGING — What's deferred (honest disclosure)

Per adversary Round-7 verdict + strategist 2-day budget analysis, the following standards are STAGED to sub-releases:

| Standard | Stage to | Reason |
|---|---|---|
| RDF Canonicalization (URDNA2015) | v0.6.2 | Poison-graph DoS class (CRITICAL, STRONGLY PLAUSIBLE); requires numeric input cap + ≥1 implementation maturity test before normative inclusion |
| SHACL | v0.6.2 | Depends on RDF profile; shape-bypass via custom datatypes needs explicit closed-world rule |
| PROV-O full round-trip | v0.6.2 | Native-field-divergence attack class needs derived-projection rule (§V60-6 lays groundwork) |
| CBOR projection (`aep:0.6/cbor`) | v0.6.1 | RFC 8949 §4.1 canonicalization gaps require dedicated adversarial pass |
| C2PA actual signing (COSE_Sign1) | v0.7 | Algorithm-confusion attack class (HIGH, STRONGLY PLAUSIBLE); requires x5chain-derived-alg verification rule |
| Cross-runtime AEP-NUMERIC-v1 (Node/Go/Rust impls) | v0.6.1 | Implementation work, not spec; tracked separately |
| `views/agent.md` Markdown projection | v0.6.1 | Axiom-4 view-drift risk needs dedicated pass |

Each staged item has a documented Lane B fixture shape pre-defined per the adversary Round-7 output. v0.6.1/v0.6.2/v0.7 must ship those fixtures alongside the closures.

---

## §V60-8 — Backwards compatibility (STRICTLY ADDITIVE)

Every v0.5.5 packet that validates clean at `aep:0.5/stable` strict L2 MUST validate clean under v0.6 if:
- Packet declares `aep_version="0.5"` + `profile="aep:0.5/stable"` (v0.5.5 baseline accepted unchanged), OR
- Packet declares `aep_version="0.6"` + `profile="aep:0.6/stable"` (v0.5.5 record shape accepted under v0.6 channel), OR
- Packet declares `aep_version="0.6"` + `profile="aep:0.6/jsonl-compact"` (v0.6 compact profile; roundtrip canonicalizer normalizes to v0.5.5 hash).

**Hash stability invariant**: a packet that opts into v0.6 compact JSONL MUST produce the same `state_hash` as the equivalent pretty-form. Verified by the Lane A roundtrip test (§V60-LANE-A).

---

## §V60-LANE-A — Empirical proof obligations

Before v0.6.0-rc1 ships, the following Lane A tests MUST pass:

1. **463-corpus baseline**: every v0.5.5 corpus packet validates clean at `aep:0.6/stable` strict L2 (zero new fails introduced).
2. **Compact roundtrip parity**: every v0.5.5 corpus packet, re-encoded as `aep:0.6/jsonl-compact`, produces the same canonical `state_hash` as the pretty form.
3. **Embedded index integrity**: every corpus packet that ships `cache/index.bin` has `index_hash` matching recomputed value.
4. **Compact storage reduction**: median per-claim bytes after compact encoding ≤ 60% of pretty form (measured).

---

## §V60-LANE-B — Mandatory regression fixtures (3 new minimum)

Each closure ships only after a hand-crafted attack vector that exercises it is REJECTED:

| Fixture | Closes | Expected rejection code |
|---|---|---|
| `tests/lane_b/atk-context-hijack.aepkg/` | A1 JSON-LD remote-context hijack | `AEP60_CONTEXT_HASH_MISMATCH` OR `AEP60_CONTEXT_REMOTE_FETCH_FORBIDDEN` |
| `tests/lane_b/atk-dual-manifest-divergence.aepkg/` | A2 BagIt-vs-aepkg.json | `AEP60_BAGIT_MANIFEST_DIVERGENCE` |
| `tests/lane_b/atk-compact-roundtrip-divergence.aepkg/` | A7 compact ↔ pretty roundtrip | `AEP60_COMPACT_ROUNDTRIP_NON_IDENTICAL` |
| `tests/lane_b/atk-index-tamper.aepkg/` | A8 embedded index tampering | `AEP60_INDEX_HASH_MISMATCH` |

Permanent fixture set grows from v0.5.5's 6 → v0.6.0-rc1's 10.

---

## §V60-CITES

- v0.5.5 spec (predecessor): [`AEP_v0_5_5_SPEC.md`](AEP_v0_5_5_SPEC.md)
- v0.5.5 → v0.6 roadmap: [`../docs/v0_6-roadmap.md`](../docs/v0_6-roadmap.md)
- Round-7 adversarial pre-mortem: captured in CHANGELOG v0.6 entry + this spec's V60-STAGING
- Reference impl: [`../src/aep/validate_v0_6.py`](../src/aep/validate_v0_6.py)
- Compact JSONL encoder/decoder: [`../src/aep/jsonl_compact.py`](../src/aep/jsonl_compact.py)
- Index builder: [`../src/aep/build_index.py`](../src/aep/build_index.py)
- External: [JSON-LD 1.1 W3C Rec](https://www.w3.org/TR/json-ld11/) · [BagIt RFC 8493](https://datatracker.ietf.org/doc/html/rfc8493) · [RO-Crate 1.1](https://www.researchobject.org/ro-crate/specification/1.1/) · [RDFC-1.0 W3C Rec](https://www.w3.org/TR/rdf-canon/) (staged) · [PROV-O W3C Rec](https://www.w3.org/TR/prov-o/) (staged) · [SHACL W3C Rec](https://www.w3.org/TR/shacl/) (staged) · [C2PA Tech Spec 2.1](https://spec.c2pa.org/) (staged)
