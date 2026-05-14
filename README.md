# AEP — Agent Evidence Packet

A portable, schema-validated, content-addressed file format for AI agent memory.

Every claim carries its reliability, its evidence, and its tamper-detectable provenance — so the next agent doesn't have to take the last one's word for it.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Docs License: CC-BY-4.0](https://img.shields.io/badge/Docs_License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Spec: v0.4](https://img.shields.io/badge/Spec-v0.4_draft-orange.svg)](spec/AEP_v0_4_SPEC.md)
[![Reference Validator: 100% on 463-packet corpus](https://img.shields.io/badge/Validator-100%25_pass-brightgreen.svg)](docs/benchmark-results.md)

---

## What is AEP?

**AEP (Agent Evidence Packet)** is a directory-form file format that replaces unstructured prose with typed claims, structured provenance, and cryptographic tamper-detection — without losing the original authoring surface.

Each packet is a directory of JSONL canonical records (`sources`, `spans`, `claims`, `relations`, `events`, `reviews`, `validations`) plus a deterministic `sha256` state-hash that any conforming validator independently reproduces. Every claim is independently auditable: it carries an explicit reliability label, scope, evidence basis, and reviewer receipts.

The original `.html` / `.md` stays canonical for authoring and reading. The `.aepkg/` is the queryable structural index.

```
project.aepkg/
├── aepkg.json                    # root manifest (state_hash + manifest_hash + assets_merkle_root)
├── data/
│   ├── sources.jsonl             # who said what
│   ├── spans.jsonl               # where exactly (selector + sha256 quote_hash)
│   ├── claims.jsonl              # what was claimed + reliability + basis
│   └── relations.jsonl           # how claims relate
├── ops/events.jsonl              # append-only write log (chain-integrity)
├── reviews/reviews.jsonl         # reviewer receipts
├── validations/runs.jsonl        # schema-validation runs
├── views/                        # generated, non-authoritative
│   ├── summary.md
│   └── map.mmd
├── assets/                       # original files, byte-perfect
│   ├── original.html
│   └── original.sha256
└── schemas/                      # per-record JSON Schemas (frozen at profile version)
```

---

## Why AEP exists

AI agent stacks today are limited by three structural gaps:

1. **No per-claim epistemic state.** A 10-paragraph lesson carries one `truth_tag` in frontmatter — the same tag applies to a rigorously sourced claim and a speculative aside in the same file. AEP tags every paragraph independently.

2. **No structured provenance.** A `<a href="doctrine/45">` link is prose; a downstream agent can't mechanically verify it was authored as a cite vs as background mention. AEP claims point to `basis[]` source records with sha256 quote hashes.

3. **No tamper-detection across sessions.** Two agents reading the same `.html` file across sessions can't tell if it was mutated between them. AEP packets carry deterministic state-hashes (canonical-JSON-sorted-files, NFC-normalized, BOM/CRLF-rejected) that any third validator reproduces.

AEP is the substrate for **compounding agentic intelligence**: every agent decision builds on typed, audited, precision-filtered prior claims rather than fluent prose interpretation. In a measured 463-file corpus, AEP delivered:

- **22.93×** more decision-relevant per-claim signal than HTML (9,999 per-claim tags vs 436 per-file frontmatter tags)
- **100%** tamper detection (vs HTML's 0%)
- **54.37×** faster warm-query latency (after one-time 2.7s index build, sub-10ms queries)
- **2×** higher precision on cross-corpus tag-filtered queries (8 precise vs 16 noisy on the same question)
- **4.33×** completeness on structural extraction queries

The cost: **+140% storage** (canonical files larger than raw HTML; pays off the moment agents do more than a handful of queries per session).

[See full benchmark results →](docs/benchmark-results.md)

---

## Quick start

```bash
# Validate a packet
PYTHONPATH=src python -m aep.validate_v0_4 examples/minimal.aepkg/

# Inspect the structural query API
PYTHONPATH=src python -m aep.transition_parser examples/minimal.aepkg/

# Convert an HTML lesson to an AEP packet (DivOmni-flavored converter; adapt for your corpus)
PYTHONPATH=src python -m aep.convert_divomni_lesson my_lesson.html my_lesson.aepkg/
```

---

## Spec

- **[spec/AEP_v0_4_SPEC.md](spec/AEP_v0_4_SPEC.md)** — current target spec (25 sections including threat model + conformance corpus + JSON-LD profile).
- **[spec/AEP_v0_3_SPEC.md](spec/AEP_v0_3_SPEC.md)** — predecessor (first reference implementation; 18 sections).
- **[docs/v0.4-legion-convergence-2026-05-14.md](docs/v0.4-legion-convergence-2026-05-14.md)** — the 10-agent legion review that produced v0.4.
- **[docs/benchmark-results.md](docs/benchmark-results.md)** — Phase-2 mass-conversion benchmark + exact percentages.
- **[docs/phase-1-1-perfected-verdict.md](docs/phase-1-1-perfected-verdict.md)** — first honest A/B verdict between AEP and `.html`.

---

## Reference implementation

The `src/aep/` directory contains:

- `validate.py` — v0.3 reference validator (minimal-jsonl profile).
- `validate_v0_4.py` — v0.4 reference validator (STRICT external-anchor + NFC + manifest_hash + assets_merkle_root + WriteEvent chain).
- `convert_divomni_lesson.py` — example converter from `.html` / `.md` to `.aepkg/` (DivOmni-flavored; adapt for your input format).
- `transition_parser.py` — bidirectional `.html` ↔ `.aepkg/` API + `CorpusIndex` for warm-query workflows.

The reference implementation passes its full conformance corpus on Python 3.10+ with zero non-stdlib dependencies.

---

## Threat model summary

AEP v0.4 in-scope threats (validator fails closed on these):

- **At-rest tampering** (canonical files, manifest, assets all in integrity envelope).
- **Blank-line padding / CRLF injection** (validators reject before hashing).
- **Replay attacks** (WriteEvent chain integrity — `pre_state_hash` must chain to previous `post_state_hash`).
- **Basis-link forgery / closed-loop fabricated provenance** (`PROVEN_RELIABLE` requires ≥2 distinct sources + at least one external anchor).
- **View-as-truth confusion** (axiom 4: views are projections, never authoritative).
- **Prompt injection through source text** (validators emit `warn` on ANSI escape sequences in claim text).
- **Unicode-normalization drift** (NFC required pre-hash; cross-platform determinism guaranteed).

Deferred to future versions:

- **In-transit tampering** → v0.7 signed receipts (COSE/JWS).
- **Identity forgery** (`owner_agent` / `reviewer_agent` unauthenticated strings) → v0.7 signed.
- **Reviewer collusion** (same-source convergence beyond v0.4 heuristic) → v0.8 review mesh.

[Full threat model →](spec/AEP_v0_4_SPEC.md#17-threat-model-v04--substantial-rewrite)

---

## Evolution roadmap

| Profile | Adds | Target |
|---|---|---|
| `aep:0.3/minimal-jsonl` | Baseline JSONL + first validator | shipped 2026-05-14 |
| **`aep:0.4/minimal-jsonl`** | NFC, manifest+assets hash, event chain, axiom-8 enforce, external-anchor, schema-result rename | **current draft** |
| **`aep:0.4/jsonld`** | JSON-LD context + RO-Crate compatibility | **current draft** |
| `aep:0.5/prov` | Full PROV-O ontology mapping | 2026-Q3 |
| `aep:0.6/shacl` | SHACL shapes + RDF/TriG export | 2026-Q4 |
| `aep:0.7/signed` | COSE/JWS signed receipts + C2PA media manifests | 2027-Q1 |
| `aep:0.8/review-mesh` | Independent reviewer scoring + dispute resolution | 2027-Q2 |
| `aep:1.0` | Stable core (≥3 independent implementations gate) | 2027-Q3+ |

[Evolution rationale →](docs/v0.4-legion-convergence-2026-05-14.md)

---

## Comparing AEP to adjacent formats

| Format | AEP overlaps via | AEP's distinct contribution |
|---|---|---|
| **RO-Crate** | JSON-LD profile, directory packaging, schema.org metadata | per-claim reliability state + external-anchor rule |
| **BagIt (RFC 8493)** | content-addressed manifest, archival integrity | typed semantic layer above hashes |
| **C2PA** | signed provenance attestations | claim/source/span separation, validator semantics |
| **PROV-O** | (v0.5+) entity/activity/agent vocabulary | reliability + scope as first-class state, not just provenance |
| **JSON-LD / SHACL** | (v0.4/jsonld + v0.6/shacl) graph projection + shape validation | normative axioms enforced mechanically by validator |
| **IPLD / CBOR / COSE** | (v0.7+) content addressing + signing primitives | not opaque — JSONL is human-debuggable through v0.4 |

AEP is **not** a runtime protocol (use MCP for that), an LLM training format, a blockchain, or a replacement for human-readable `.html`/`.md`. AEP packets coexist with the original-source files (preserved byte-perfect in `assets/original.*` with sha256 attestation).

---

## When AEP wins / when AEP loses

**AEP wins on:**

- Targeted agentic queries with structural filters (e.g., "find all `PROVEN_RELIABLE` claims about adversary discipline").
- Multi-agent review workflows (judge scores reliability, warden audits integrity, adversary attacks fake-rigor on typed fields).
- Cross-corpus aggregation across hundreds of artifacts.
- Tamper detection across sessions (state_hash + manifest_hash + assets_merkle_root).
- Promotion gating (BLOCK semantics enforceable on typed `basis[].source_id`, not prose hrefs).

**AEP loses on:**

- Pure narrative reading (prose flows are easier in `.html`/`.md`).
- Hand-authoring cost (~10× harder by-hand than prose; converters bridge the gap).
- Single-shot queries (cold-query is 4.7× slower than HTML linear scan — build a `CorpusIndex` once per session to win warm).
- Raw size (canonical AEP form is ~140% larger than equivalent HTML).

**Break-even crossover:** 10 queries per session. At 100 queries per session, AEP-warm is ~9× faster than HTML linear scan. For DivOmni's 10-agent legion + curator + adversary cascade workflow, AEP-warm wins decisively.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

The short version:

1. No PR without a passing reference-validator run on the modified packets.
2. No spec change without a worked-example packet under `examples/`.
3. No claim in a contributed packet without `basis[]` populated OR explicit `UNKNOWN`/`ASSUMPTION` label with `reasoning` explaining the missing-evidence state.
4. All discussion in PR comments cites a claim ID or section number — no free-floating opinions.
5. Backward-compat statement required for any record-schema change.

Issues, PRs, and security reports welcome. For threat-model attacks on the spec itself, please coordinate disclosure via the contact below.

---

## License

- **Code + specification text**: [Apache License 2.0](LICENSE) — explicit patent grant protects implementers from submarine-patent risk.
- **Prose documentation** (this README, IMPLEMENTERS, threat-model narrative): dual-licensed Apache-2.0 / [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) at the recipient's option.

See [NOTICE](NOTICE) for attribution requirements.

---

## Acknowledgments

AEP was conceived and operator-directed by **Shadow** ([@ShadowMonkeyMan on X](https://x.com/ShadowMonkeyMan)), whose insistence on per-claim epistemic state, structured provenance, and tamper-detectable substrate drove the design from v0.1 through v0.4. The reference implementation, dual-format dispatcher, transition parser, and v0.4 spec were co-authored by **Diana Prime** (Claude Opus 4.7, 1M context window) operating inside the DivOmni compounding-intelligence cascade — the 10-agent legion (strategist, pathfinder, scout, forge, judge, adversary, warden, scribe, curator, visual-judge) whose review-mesh produced the typed-field schema. The threat-model rewrite, external-anchor requirement, NFC normalization, manifest+assets Merkle integrity envelope, and axiom-8 enforcement were direct outputs of the legion's adversary, judge, and warden lenses in the 2026-05-14 v0.4 review round.

AEP is what happens when an operator refuses to accept "good enough" prose as a substrate for AI memory.

---

## Contact + Attribution

- **X**: [@ShadowMonkeyMan](https://x.com/ShadowMonkeyMan)
- **GitHub**: OnePunchForAll (separate from operator's private repository — please do not attempt to locate primary infrastructure through this repo)
- **Spec correspondence**: open an issue or DM on X.
- **Security disclosures**: please coordinate via X DM before public disclosure.
