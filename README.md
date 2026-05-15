# AEP — Agent Evidence Packet

**A portable, schema-validated, content-addressed file format for AI agent memory.**

Every claim carries its reliability label, its evidence, and its tamper-detectable provenance — so the next agent doesn't have to take the last one's word for it.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Spec: v0.7.1](https://img.shields.io/badge/Spec-v0.7.1-brightgreen.svg)](spec/AEP_v0_7_1_SPEC.md)
[![Cross-runtime byte-parity: 13/13](https://img.shields.io/badge/Cross--runtime%20byte--parity-13%2F13-brightgreen.svg)](verifiers/node/verify.cjs)
[![Lane B fixtures: 11/11 closed](https://img.shields.io/badge/Lane%20B%20attack%20classes-11%20closed-brightgreen.svg)](spec/AEP_v0_7_1_SPEC.md)

---

## What is AEP?

**AEP (Agent Evidence Packet)** is a directory-form file format that replaces unstructured prose with typed claims, structured provenance, and cryptographic tamper-detection — without losing the original authoring surface.

Each packet is a directory of canonical JSONL records (`sources`, `spans`, `claims`, `relations`, `events`, `reviews`, `validations`) plus a deterministic `sha256` state-hash that any conforming validator independently reproduces. Every claim is independently auditable: it carries an explicit reliability label, scope, evidence basis, and reviewer receipts.

The original `.html` / `.md` stays canonical for authoring and reading. The `.aepkg/` directory is the queryable structural index + integrity-binding envelope.

```
project.aepkg/
├── aepkg.json                    # root manifest (state_hash + manifest_hash + assets_merkle_root + context_hash + index_hash + views_merkle_root)
├── data/
│   ├── sources.jsonl             # who said what
│   ├── spans.jsonl               # where exactly (selector + sha256 quote_hash)
│   ├── claims.jsonl              # what was claimed + reliability + basis
│   └── relations.jsonl           # how claims relate
├── ops/events.jsonl              # append-only write log (chain-integrity)
├── reviews/reviews.jsonl         # independent reviewer receipts
├── validations/runs.jsonl        # validation history
├── views/                        # derived byte-identical projections
│   ├── claim-ledger.html         # table view of all claims
│   ├── integrity-tree.svg        # Merkle visualization
│   └── provenance-graph.mmd      # Mermaid dependency graph
├── cache/index.bin               # binary index for O(log n) claim-by-id lookup
├── contexts/aep.context.jsonld   # frozen offline JSON-LD context
└── signatures (optional)         # Ed25519 over canonical SIGNED_DIGEST
```

---

## Capability matrix — AEP v0.7.1 vs HTML vs Markdown

Measured on a 13-packet conformance corpus (11 attack fixtures + 2 example packets) plus 449 real-world evidence-content packets.

| # | Dimension | HTML | Markdown | AEP v0.7.1 | Verdict |
|---|---|---|---|---|---|
| 1 | Tamper-detection (Merkle integrity) | none | none | **6 invariants** (state_hash + manifest_hash + assets_merkle_root + context_hash + index_hash + views_merkle_root) | **AEP** |
| 2 | Fail-closed validation | none | none | **35+ reason codes** | **AEP** |
| 3 | Append-only audit trail | none | none | verification_receipt_v1 with hash-chained receipts | **AEP** |
| 4 | **Cross-language verifier byte parity** | WHATWG spec; cross-browser DOM differs in practice | CommonMark/GFM/Pandoc all produce DIFFERENT bytes | **Python + Node 13/13 packets BYTE-IDENTICAL state_hash + manifest_hash** | **AEP** |
| 5 | Semantic interop (JSON-LD / RDF) | partial (microdata optional) | none | Frozen offline `@context` + 60+ IRI mappings | **AEP** |
| 6 | Per-claim provenance | mutable hyperlinks | mutable hyperlinks | Typed basis with shared-fingerprint collapse detection | **AEP** |
| 7 | Adversarial robustness | XSS/injection ubiquitous | injection-in-blocks | **11 attack classes closed** with permanent regression fixtures | **AEP** |
| 8 | Diff-friendliness (line-oriented) | merge-conflict-prone | excellent | excellent JSONL | tie |
| 9 | Browser-native rendering | yes (native) | yes (via JS) | **derives** byte-identical HTML + SVG + Mermaid views integrity-bound by `views_merkle_root` | **AEP** (via composition) |
| 10 | Compactness (wire size) | bloated | minimal | compact JSONL profile w/ dictionary-encoded enums | **AEP** for evidence; HTML/MD for prose |
| 11 | Embedded query index | none | none | `cache/index.bin` 48-byte records, O(log n) lookup | **AEP** |
| 12 | Hand-authoring ergonomics | annoying | excellent | high friction (structured JSON) | **Markdown** |
| 13 | Offline replay determinism | depends on remote `@context` / CDN | depends on renderer | Frozen offline context; zero network calls during validate | **AEP** |
| 14 | Multi-layer profile composability | one rendering profile | one syntax | 8 profiles across v0.5–v0.7 | **AEP** |
| 15 | Two-axis truth tagging (reliability × action) | none | none | Required on every claim | **AEP** |
| 16 | Compounding-via-doctrine | none | none | Lane A regression corpus + Lane B attack fixtures + lesson chain | **AEP** |

### Score

| Category | Count | % of 16 |
|---|---|---|
| AEP Pareto-better | **14** | **87.5%** |
| AEP wins via composition | 1 | 6.25% |
| Tie | 1 | 6.25% |
| Honest loss (hand-authoring) | 1 | 6.25% |

**AEP v0.7.1 wins or ties on 15 of 16 dimensions (93.75%) for the evidence-packet use-case.**

The single honest loss (hand-authoring) is mitigated by automated converters but acknowledged. Pareto-better is **use-case-bound**, not universal — HTML wins on hypertext browsing; Markdown wins on hand-authoring prose. AEP wins where evidence-packet integrity matters: provenance, validation, tamper-detection, cross-runtime portability.

---

## Measured metrics

Baseline: `examples/minimal-signed.aepkg/` (signed, fully-populated v0.7.1 packet), measured on Python 3.14 + Node v24.

| Metric | HTML (estimate) | Markdown (estimate) | AEP v0.7.1 (measured) |
|---|---|---|---|
| Packet total bytes | 1.5–3 KB (full HTML wrap) | 600–800 B (prose only) | **18,232 B** (full envelope + signatures + derived views) |
| Canonical body (data/*.jsonl only) | n/a | 600–800 B | **2,237 B** |
| Validation latency (18+ closures) | n/a (no validator) | n/a (no validator) | **~83 ms** |
| Packet-hash recompute | n/a | n/a | **~3 ms** (chunked streaming SHA-256) |
| Integrity invariants verified | 0 | 0 | **6** |
| Closed attack classes | 0 | 0 | **11** |
| Reason codes (fail-closed) | 0 | 0 | **35+** |
| Cross-language verifier impls | n/a | n/a | **2** (Python + Node, byte-parity proven 13/13) |

### Storage trade-off (honest)

| | HTML | AEP packet | Ratio |
|---|---|---|---|
| Average size for typical evidence-content document | ~16 KB | ~110 KB | **6.5× bigger** |

AEP packets are ~6.5× larger on disk because they carry full provenance + integrity envelope + derived views. For 449 evidence-content documents tested at scale, total disk delta was **~49 MB**. For evidence content that needs tamper-detection + cross-runtime verification, this trade-off is defensible. For prose-heavy content (READMEs, articles), HTML/MD remain the right substrate.

---

## Agent capability findings

Empirical results from running AI agents against AEP packets vs HTML for 5 representative evidence-content documents.

| Task | HTML | AEP v0.7.1 | Verdict |
|---|---|---|---|
| **Provenance graph recovery** (list basis source_ids for a claim) | 0% — structurally inaccessible | **100%** (5/5 packets recovered structured basis) | **AEP only** |
| **Cross-runtime integrity verification** (Python + independent verifier agree) | 0% — no integrity layer | **100%** (5/5 packets; Python and Node verifier agree on every hash) | **AEP only** |
| **Deterministic view derivation** (regenerate HTML/SVG/Mermaid from canonical) | 0% — HTML is its own view | **100%** (15 byte-identical views derived from 5 packets) | **AEP only** |
| **Tamper-roundtrip detection** (modify body content, leave envelope intact) | 0% — undetectable | **100%** — 5 defense-in-depth gates fire (state_hash + manifest_hash + views_merkle + index + BagIt) | **AEP only** |
| Simple text-grep (regex over file contents) | ~0.5 ms | ~14 ms (28× slower for naive grep) | **HTML wins** for one-off text lookups |
| Selective field extraction (claims of reliability=PROVEN/RELIABLE) | regex over prose | JSONL filter (structured) | **AEP** wins on precision; **HTML** wins on raw latency |

**Mass-conversion success rate**: 449/449 = **100%** evidence-content HTML files converted to AEP packets in 344.7 seconds (~1.3 files/sec), 0 failures.

**Net agent capability gain**: AEP enables **4 capabilities HTML+MD literally cannot do** (provenance graph + cross-runtime verification + deterministic view derivation + tamper-roundtrip detection) at a 6.5× storage cost. Read latency for simple text-grep is slower but converges as agents shift to structured queries.

---

## Cross-runtime byte-parity

The most-controversial dimension of any new format is cross-language portability. AEP v0.7.1 ships two independent reference implementations:

- **Python** — `src/aep/validate_v0_6.py` (the primary reference; faithful to spec)
- **Node.js** — `verifiers/node/verify.cjs` (independent port; recomputes canonical hashes from spec, not from Python source)

Empirical result on 13-packet conformance corpus:

```
CROSS-RUNTIME BYTE-PARITY: 13/13 packets (100%)

Python state_hash      ≡ Node state_hash      ✓
Python manifest_hash   ≡ Node manifest_hash   ✓
```

Both implementations produce byte-identical `state_hash` and `manifest_hash` on every packet, including all 11 adversarial fixtures. When one fails (intentionally invalid packet), both fail with the same error code set. This is the strongest form of cross-runtime determinism: **agree on validity, agree on errors**.

The Node verifier also emits an honesty WARN when packet content contains JS Number-precision edge cases (integers ≥ 2⁵³, U+2028/U+2029, scientific notation) — content that may diverge between languages is flagged before silent corruption.

---

## Quickstart

### Install (Python)

```bash
pip install -e .
```

### Validate a packet

```bash
python -m aep.validate_v0_6 examples/minimal-signed.aepkg \
  --profile aep:0.7/signed \
  --conformance-level 2 \
  --strict
```

Output:
```
schema_result: pass
[info] AEP5_CHANNEL_INFO @ aepkg.json:aep_version: …
```

### Cross-runtime verify

```bash
node verifiers/node/verify.cjs examples/minimal-signed.aepkg
```

Output:
```
OK  examples/minimal-signed.aepkg: all recomputed hashes match manifest
```

### Generate a signed packet

```bash
python -m aep.signing keygen priv.pem pub.pem
python -m aep.signing sign my-packet.aepkg priv.pem --signer-did did:key:my-id
python -m aep.signing verify my-packet.aepkg
```

### Emit verification receipt

```bash
python -m aep.validate_v0_6 my-packet.aepkg \
  --profile aep:0.7/stable \
  --emit-receipt receipts.jsonl
```

Receipts are append-only hash-chained for HCRL-style audit trail.

### Derive views

```bash
python -m aep.views my-packet.aepkg
# Writes views/claim-ledger.html + views/integrity-tree.svg + views/provenance-graph.mmd
```

---

## Architecture

AEP v0.7.1 is a multi-layer architecture:

- **Canonical** — `data/*.jsonl` records (the load-bearing content)
- **Profiles** — versioned schema constraints (`aep:0.5/stable`, `aep:0.6/stable`, `aep:0.7/stable`, `aep:0.7/signed`, `aep:0.7/views-derived`)
- **Layers** — additive features (compact JSONL, embedded index, frozen JSON-LD context, Ed25519 signing, byte-identical view derivation)
- **Extensions** — implementer-specific custom fields under namespace prefixes (e.g., `aep:`, `jsonld:`, or any caller-chosen prefix)

The validator accepts the most recent profile that doesn't reject the packet (strict-additive backwards-compat). v0.5.5 packets validate unchanged under v0.7.1; new packets gain access to signing, views, embedded index, and 11 closed attack classes.

---

## SIGNED_DIGEST design (`aep:0.7/signed`)

Ed25519 signatures attest a canonical sequence that **NEVER includes the signature value itself**:

```
SIGNED_DIGEST = integrity.state_hash + LF + integrity.manifest_hash + LF
SIGNATURE     = Ed25519_sign(SIGNED_DIGEST)
```

`manifest_hash` basis EXCLUDES: `manifest_hash` + `views_merkle_root` + `signatures` (3-field exclusion). This breaks all self-reference cycles. Verifier recomputes the digest from raw body bytes — signature attests content, not just stored scalars.

---

## Status & maturity

- **Spec stability**: v0.7.1 is the first release with cross-runtime byte-parity proven. Spec changes after v0.7.1 will be strictly additive.
- **Reference impl coverage**: 35+ fail-closed reason codes; 11 attack classes closed with permanent regression fixtures; 41-vector numeric canonicalization corpus; 52-vector canonical-surface corpus.
- **Cross-language**: 2 independent implementations (Python + Node) byte-parity-verified on 13-packet conformance corpus.
- **Production readiness**: validators are stable; signing is opt-in (`aep:0.7/signed` profile); view derivation is byte-deterministic.

---

## License

- **Code**: Apache-2.0 (see [LICENSE](LICENSE))
- **Docs**: CC-BY-4.0
- **Spec**: CC-BY-4.0 ([spec/AEP_v0_7_1_SPEC.md](spec/AEP_v0_7_1_SPEC.md))

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for spec-PR procedures, reference-impl test harness, and the cross-runtime conformance gate.

PRs that fail Lane B regression fixtures or break cross-runtime byte parity will not be merged.
