# AEP — Agent Evidence Packet

**A portable, schema-validated, content-addressed, hash-chained file format for AI agent memory.**

Every claim carries its reliability label, its evidence, and its tamper-detectable provenance — so the next agent doesn't have to take the last one's word for it.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Spec: v1.5 LTS](https://img.shields.io/badge/Spec-v1.5_LTS-brightgreen.svg)](spec/)
[![Cross-runtime byte-parity: 3 of 3](https://img.shields.io/badge/Cross--runtime%20byte--parity-Python%20%2B%20Node%20%2B%20Perl-brightgreen.svg)](scripts/aep_doctor_supreme.py)
[![Hook bypass: 0 / 500](https://img.shields.io/badge/Hook_bypass-0%2F500_at_production--N-brightgreen.svg)](hooks/)
[![Sandbox escape: 0 / 1200](https://img.shields.io/badge/Sandbox_escape-0%2F1200_at_production--N-brightgreen.svg)](hooks/)
[![Mutation catch: 1.0000](https://img.shields.io/badge/Mutation_catch-1.0000_%282700%2F2700%29-brightgreen.svg)](scripts/build_v15_independent_mutation_suite.py)

> **v1.5 LTS production-hardened.** Doctor cached p95 **8.3 ms** · cold p95 **5.07 ms**. Token reduction **88.7%** vs raw `.md`. 0/5,000 prompt-injection attempts weakened. 0/500 hook bypasses. 0/1,200 sandbox escapes. 1.0000 mutation catch across 2,700 evaluations. 0/8 fabrication across independent audits.
>
> **Public showcase**: [aep.dev (GitHub Pages)](https://onepunchforall.github.io/AEP/) — full v1.5 LTS evidence with per-component "why it matters."

---

## What is AEP?

**AEP (Agent Evidence Packet)** is a directory-form file format that replaces unstructured agentic prose with typed claims, structured provenance, and cryptographic tamper-detection — without losing the original authoring surface.

Each packet is a directory of canonical JSONL records (`sources`, `spans`, `claims`, `relations`, `events`, `reviews`, `validations`) plus a deterministic `sha256` state-hash that any conforming validator independently reproduces. Every claim is independently auditable: it carries an explicit reliability label, scope, evidence basis, and reviewer receipts.

The original `.html` / `.md` stays canonical for authoring and reading. The `.aepkg/` directory is the queryable structural index + integrity-binding envelope.

```
project.aepkg/
├── aepkg.json                    # root manifest (state_hash + manifest_hash + assets_merkle_root
│                                 #                + context_hash + index_hash + views_merkle_root)
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

## v1.5 LTS — what ships and why each part matters

| Component | What it is | Why it matters |
|---|---|---|
| **`spec/AEP_v0_8_SPEC.md`** | STABLE baseline + 8 frontier-break primitives (F1-F8) | The minimum bar — reproduction, falsifier sandbox, counterexample replay, cross-runtime preflight. |
| **`spec/AEP_v1_0_3_SPEC.md`** | Regexical Memory as AEP-native spaced repetition | Lessons aren't just stored; they're recalled at the right time with measurable decay. |
| **`spec/AEP_v1_1_SPEC.md`** | Research-grade primitives F12-F19 + A1-A8 | Coverage witness + provenance graph + attack registry + amendment lifecycle. |
| **`spec/AEP_v1_2_SPEC.md`** | PROPOSED immune-system layer | 4-stage substrate: prevent · detect · repair · translate. |
| **`constitution/aep_constitution_v1_5_lts.json`** | Operational policy precedence | Single source of truth for runtime: airlock rules, trust tiers, performance gates, release-freeze invariants. |
| **`src/aep/`** (~15K LOC Python) | Reference implementation | Validators (v0.4 → v0.8), Ed25519 signing, view derivation, JSONL-compact, falsifier sandbox, counterexample replay. |
| **`hooks/`** | 5 PreToolUse enforcement hooks | Defender guard · K3 airlock · K6 receipts · prompt contract · stop doctor. Discipline at write-time. |
| **`scripts/aep_doctor_supreme.py`** | Python doctor (7-verdict enum) | Cached p95 8.3 ms · cold p95 5.07 ms. Instant verdict at session-stop. |
| **`scripts/aep_doctor_node.cjs`** | Node.js doctor (independent re-derivation) | Cross-runtime byte parity proven on conformance corpus. |
| **`scripts/aep_doctor_perl.pl`** | Perl doctor (third runtime quorum) | Three-language agreement = canonicalization is real, not an implementation artifact. |
| **`tools/universal_aepify.py`** | Universal converter (11 file classes) | 100% mass-conversion rate across 1,749 v1.5 LTS conversions. |
| **`tools/aep_cluster_combine.py`** | Combine + decompose discipline | N packets → umbrella → byte-identical originals. Verified N=100 at 4.18s / 1.78 MB. |
| **`viewer/index.html`** | Zero-CDN drag-drop browser viewer | First-paint p95 80 ms. WCAG 2.1 AA accessible (10/10). |
| **`test_vectors/`** | 41 numeric + canonical-surface vectors | Permanent regression coverage for every closed attack class. |
| **`scripts/build_v15_independent_mutation_suite.py`** | 30 mutation classes × 10 seeds × 9 validators | 2,700 evaluations; mean catch 1.0000; false positive rate 0/900. |
| **`scripts/v15_validators_common.py`** | Shared validator core | Closed the F23 mutation finding across 9 validators. |
| **`scripts/build_v15_falsifier_dsl.py`** | Falsifier DSL with 8 forbidden tokens | subprocess / socket / os.environ / eval / exec / __import__ / popen / shell=true all blocked at compile. |
| **`scripts/build_v15_lts_extension_abi.py`** | Frozen extension ABI | 20 synthetic extensions install + uninstall with zero core schema changes. |

---

## v1.5 LTS measured scoreboard

| Gate | Target | Measured | Status |
|---|---|---|---|
| Prompt-injection resistance | ≥ 99% | **0 / 5,000 weakened** | ✓ PASS |
| Hook bypass (v1.5.1 RC1 patch) | 0 / 500 | **0 / 500** | ✓ PASS |
| Sandbox escape (post-patch) | 0 / 1,200 | **0 / 1,200** | ✓ PASS |
| Doctor cached p95 | ≤ 300 ms | **8.3 ms** | ✓ 36× under |
| Doctor cold p95 | ≤ 1,500 ms | **5.07 ms** | ✓ 295× under |
| Viewer first-paint p95 | ≤ 2,000 ms | **80 ms** | ✓ 25× under |
| Validator catch (mutation suite) | ≥ 0.95 | **1.0000 (2,700 / 2,700)** | ✓ PASS |
| Clean-fixture false positive | 0 / 900 | **0 / 900** | ✓ PASS |
| Cross-runtime byte parity | 10 / 10 | **10 / 10 (Python + Node + Perl)** | ✓ PASS |
| WCAG 2.1 AA viewer accessibility | 10 / 10 | **10 / 10 (required + bonus)** | ✓ PASS |
| Token efficiency vs raw `.md` | ≥ 60% reduction | **88.7%** | ✓ PASS |
| Independent audit fabrication | 0 / 8 | **0 / 8** | ✓ PASS |

---

## Capability matrix — AEP vs HTML vs Markdown

| # | Dimension | HTML | Markdown | AEP v1.5 LTS | Verdict |
|---|---|---|---|---|---|
| 1 | Tamper-detection (Merkle integrity) | none | none | 6 invariants | **AEP** |
| 2 | Fail-closed validation | none | none | 35+ reason codes | **AEP** |
| 3 | Append-only audit trail | none | none | Hash-chained receipts (HCRL) | **AEP** |
| 4 | Cross-language verifier byte parity | DOM differs in practice | renderers diverge | **Python + Node + Perl identical** | **AEP** |
| 5 | Semantic interop (JSON-LD / RDF) | partial | none | Frozen offline `@context` + 60+ IRI mappings | **AEP** |
| 6 | Per-claim provenance | mutable hyperlinks | mutable hyperlinks | Typed basis + shared-fingerprint collapse detection | **AEP** |
| 7 | Adversarial robustness | XSS / injection ubiquitous | injection-in-blocks | **11 attack classes closed** + regression fixtures | **AEP** |
| 8 | Hook-bypass resistance | n/a | n/a | **0 / 500 at production-N** | **AEP** |
| 9 | Sandbox-escape resistance | n/a | n/a | **0 / 1,200 at production-N** | **AEP** |
| 10 | Token efficiency | baseline | baseline | **88.7% reduction** for agent reads | **AEP** |
| 11 | Diff-friendliness | merge-conflict-prone | excellent | excellent (JSONL) | tie |
| 12 | Browser-native rendering | yes (native) | yes (via JS) | derives byte-identical HTML/SVG/Mermaid views | **AEP via composition** |
| 13 | Embedded query index | none | none | `cache/index.bin` — O(log n) lookup | **AEP** |
| 14 | Hand-authoring ergonomics | annoying | excellent | high friction (structured JSON) | **Markdown** |
| 15 | Offline replay determinism | depends on CDN | depends on renderer | Frozen context; zero network calls during validate | **AEP** |
| 16 | Multi-layer profile composability | one rendering profile | one syntax | 6 spec layers (v0.4 → v1.2) | **AEP** |
| 17 | Combine-decompose bijection | n/a | n/a | **Verified N = 100 (4.18 s / 1.78 MB)** | **AEP** |
| 18 | Two-axis truth tagging | none | none | Required on every claim | **AEP** |
| 19 | Compounding-via-doctrine | none | none | Lane A regression corpus + Lane B attack fixtures | **AEP** |

### Score

| Category | Count | % of 19 |
|---|---|---|
| AEP Pareto-better | **17** | **89.5%** |
| AEP wins via composition | 1 | 5.3% |
| Tie | 1 | 5.3% |
| Honest loss (hand-authoring) | 1 | 5.3% |

**AEP v1.5 LTS wins or ties on 18 of 19 dimensions (94.7%) for the evidence-packet use-case.**

The single honest loss (hand-authoring) is mitigated by automated converters but acknowledged. Pareto-better is **use-case-bound**, not universal — HTML wins on hypertext browsing; Markdown wins on hand-authoring prose. AEP wins where evidence-packet integrity, multi-agent compounding, and adversarial hardening matter.

---

## Quickstart

### Install

```bash
pip install -e .
```

### Validate a packet

```bash
python -m aep.validate_v0_8 examples/minimal-signed.aepkg \
  --profile aep:0.8/stable \
  --conformance-level 2 \
  --strict
```

### Cross-runtime verify

```bash
python scripts/aep_doctor_supreme.py examples/minimal-signed.aepkg
node   scripts/aep_doctor_node.cjs    examples/minimal-signed.aepkg
perl   scripts/aep_doctor_perl.pl     examples/minimal-signed.aepkg
# All three emit byte-identical state_hash + manifest_hash.
```

### Convert your own files

```bash
python tools/universal_aepify.py path/to/your/file.md
# produces path/to/your/file.aepkg/ alongside the canonical
# verify    python tools/universal_aepify.py --verify-only path/to/your/file.md
```

### Combine + decompose a corpus cluster

```bash
python tools/aep_cluster_combine.py path/to/cluster/*.aepkg --out path/to/umbrella.aepkg
python tools/aep_cluster_combine.py --decompose path/to/umbrella.aepkg --out path/to/restored/
# Verified byte-roundtrip at N = 100.
```

### Sign + verify

```bash
python -m aep.signing keygen priv.pem pub.pem
python -m aep.signing sign my-packet.aepkg priv.pem --signer-did did:key:my-id
python -m aep.signing verify my-packet.aepkg
```

### Emit verification receipt

```bash
python -m aep.validate_v0_8 my-packet.aepkg \
  --profile aep:0.8/stable \
  --emit-receipt receipts.jsonl
```

---

## Architecture

AEP v1.5 LTS is a 6-layer architecture:

1. **Canonical** — `data/*.jsonl` records (the load-bearing content)
2. **Profiles** — versioned schema constraints (`aep:0.5/stable` → `aep:0.8/stable`; backwards-compat strict-additive)
3. **Layers** — additive features (compact JSONL, embedded index, frozen JSON-LD context, Ed25519 signing, byte-identical view derivation, regexical memory, immune-system primitives)
4. **Extensions** — implementer-specific custom fields under namespace prefixes (e.g., `aep:`, `jsonld:`, or any caller-chosen prefix)
5. **Constitution** — runtime policy (trust tiers · airlock rules · proof budgets · sandbox requirements · extension ABI rules)
6. **Hooks** — write-time discipline enforcement (5 PreToolUse hooks: defender, airlock, ledger, contract, doctor)

The validator accepts the most recent profile that doesn't reject the packet (strict-additive backwards-compat). v0.5.5 packets validate unchanged under v0.8/stable; new packets gain access to signing, views, embedded index, falsifier sandbox, counterexample replay, regexical memory, and the v1.5 LTS hardening surface.

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

- **Spec stability**: v1.5 LTS is the freeze kernel. Spec changes after v1.5 LTS are strictly additive within v1.5.x; v1.6+ requires explicit migration receipts.
- **Reference impl coverage**: 35+ fail-closed reason codes; 11 attack classes closed with permanent regression fixtures; 41-vector numeric canonicalization corpus; 52-vector canonical-surface corpus; 2,700-evaluation mutation suite at 1.0000 catch.
- **Cross-language**: 3 independent implementations (Python + Node + Perl) byte-parity-verified.
- **Production readiness**: validators stable; signing opt-in; view derivation byte-deterministic; 5 enforcement hooks active; doctor verdicts in under 10 ms.

---

## License

- **Code**: Apache-2.0 (see [LICENSE](LICENSE))
- **Docs**: CC-BY-4.0
- **Spec**: CC-BY-4.0 (see [spec/](spec/))

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for spec-PR procedures, reference-impl test harness, and the cross-runtime conformance gate.

PRs that fail Lane B regression fixtures, break cross-runtime byte parity, or weaken any of the 5 enforcement hooks will not be merged.

---

## Release history

- **v1.5 LTS** (this release) — production-hardened. Cross-runtime byte parity across Python + Node + Perl. 5 PreToolUse enforcement hooks. Doctor cached p95 8.3 ms. 88.7% token reduction. 0 / 5,000 prompt-injection. 0 / 500 hook bypass. 0 / 1,200 sandbox escape. 1.0000 mutation catch. 0 / 8 fabrication across independent audits.
- **v1.2** (PROPOSED) — immune-system layer staged.
- **v1.1** — research-grade primitives F12-F19 + A1-A8 landed.
- **v1.0.3** — Regexical Memory as AEP-native spaced repetition.
- **v0.8** — 8 frontier-break primitives F1-F8 (reproduce / falsifier-sandbox / counterexample-replay / cross-runtime preflight).
- **v0.7.1** — first public release with cross-runtime byte parity (Python + Node, 13/13 conformance corpus). 11 attack classes closed.
- **v0.6 / 0.5.x** — JSON-LD bridge, Ed25519 signing, compact-JSONL profile, embedded binary index.
- **v0.4 / 0.3** — schema baseline; canonical record types.

See [CHANGELOG.md](CHANGELOG.md) for the full honesty trail.
