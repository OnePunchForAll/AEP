# AEP v0.4 Specification

**Status**: Draft, target publication 2026-Q2.
**Predecessor**: AEP v0.3 (2026-05-14 first reference impl, Phase-1.1 perfected).
**Authors**: operator  + the agentic substrate (Claude Opus 4.7, operating inside AEP project's 10-agent legion).
**License**: Apache-2.0 (spec + reference implementation), CC-BY-4.0 (prose documentation).
**Profile**: `aep:0.4/jsonld` (introduces JSON-LD context + RO-Crate compatibility).

---

## Abstract

AEP — Agent Evidence Packet — is a portable, schema-validated, content-addressed file-format for AI-agent memory. Each packet is a directory of JSONL canonical records (sources, spans, claims, relations, events, reviews, validations) plus a deterministic sha256 state-hash that any conforming validator independently reproduces. Every claim carries explicit reliability, scope, evidence basis, and reviewer receipts, making AI outputs auditable at the paragraph level rather than the document level. v0.4 introduces a JSON-LD profile aligned with RO-Crate / PROV-O / schema.org; mandates Unicode NFC normalization and manifest+assets in the canonical state-hash; closes the closed-loop-fabricated-provenance attack via the external-anchor requirement; and enforces axiom 8 (no independent convergence from same-source evidence) mechanically rather than as prose.

## 1. Positioning

AEP is the **per-claim epistemic-state substrate** layer in the agentic file-format stack:
- *Above* packaging formats (BagIt, RO-Crate) — AEP packets can be valid RO-Crate Profiles.
- *Alongside* provenance signing (C2PA, Sigstore, COSE) — AEP v0.7 will adopt signed receipts.
- *Composing with* semantic web (JSON-LD, RDF, PROV-O, SHACL) — `aep:0.4/jsonld` is the entry point.
- *Feeding* agent runtime protocols (MCP) — AEP packets are the durable memory that MCP tools query.

AEP is **NOT** a runtime protocol, an LLM training format, a blockchain, or a replacement for human-readable `.html` / `.md`. The original-source files stay canonical for authoring and reading; the packet is the queryable structural index.

## 2. Design axioms (8, normative)

Every conforming reader, writer, and validator preserves these:

1. **No claim without epistemic state.** Every claim records reliability + scope + basis + reasoning + owner_agent + review_tier + status.
2. **No epistemic upgrade without evidence or review.** Confidence cannot exceed provenance strength. Upgrades require either external anchors (§13) or independent reviewer receipts.
3. **No source without provenance strength and limits.** Source records declare provenance strength, location, and the limits of what they support.
4. **No generated view as canonical truth.** Markdown, HTML, Mermaid, JSON-LD exports under `views/` are projections and never authoritative.
5. **No mutation without append-only event receipt.** `ops/events.jsonl` is append-only; each event chains `pre_state_hash → post_state_hash`.
6. **No graph edge without source claim or explicit inference label.** Relations declare their inference type from a fixed enum.
7. **No time-sensitive claim without temporal scope or revalidation state.** Time-sensitive claims carry expiry or revalidation metadata.
8. **No independent convergence from repeated same-source evidence.** A claim's `basis[]` must reference ≥2 distinct sources for `PROVEN_RELIABLE`; validators MUST enforce this mechanically, not as prose.

## 3. Reliability labels (Axis A — epistemic state)

Exactly one required per important claim:

- `PROVEN_RELIABLE` — replicated empirical support OR formally verified OR ≥2 independent sources + reviewer receipts.
- `STRONGLY_PLAUSIBLE` — strong evidence + coherent mechanism, missing one of (independence, replication, external prior art).
- `PLAUSIBLE` — one credible source + reasonable mechanism.
- `ASSUMPTION` — working hypothesis without strong evidence; held provisionally.
- `CONFLICTED` — multiple credible sources disagree; honest representation of dispute.
- `UNKNOWN` — not yet investigated; `reasoning` field MUST explain the missing-evidence state.
- `GOVERNANCE_RULE` — operator-attested constitutional rule (added v0.4 per AEP project §02 Amendment A15); validators MUST NOT apply external-anchor enforcement to this class.

## 4. Scope labels

Exactly one per important claim:

- `LOCAL_OBSERVATION` — specific to this packet's context.
- `CONTEXT_BOUND_PATTERN` — generalizes within a bounded domain.
- `GENERAL_CLAIM` — broad applicability.

## 5. Axis B — action disposition (v0.4 addition)

Every claim may also carry an action-disposition label:

- `GO` — proceed; license action.
- `EXPERIMENT` — bounded trial; instrument and observe.
- `EXPLORE` — read/sketch only; do not commit code.
- `HALT` — stop; do not proceed.
- `FORBIDDEN` — constitutional bar regardless of evidence.

Backward-compatible mapping from single-axis taxonomies (e.g., AEP project §02) to `(Axis A, Axis B)` ships at `contexts/aep.context.jsonld#legacy-tag-map`.

## 6. Package identity

`aepkg.json` root manifest. Required fields:

- `aep_version` — `"0.4"`.
- `packet_id` — pattern `^aepkg:[A-Za-z0-9._:-]+$`.
- `title` — non-empty string.
- `created_at` — **RFC3339 with explicit `Z` UTC suffix** (v0.4 normative; v0.3 was unspecified).
- `created_by` — non-empty string.
- `profile` — one of `aep:0.4/minimal-jsonl` or `aep:0.4/jsonld`.
- `canonical_files` — array of paths to include in canonical state-hash.
- `extensions` — object; writers MUST preserve unknown extension fields byte-perfectly across read+write roundtrips.
- `integrity` — object with `algorithm` + `state_hash` + (v0.4 new) `manifest_hash` + `assets_merkle_root`.

## 7. Canonical files

The canonical AEP state is formed from these files only:

```
data/sources.jsonl
data/spans.jsonl
data/claims.jsonl
data/relations.jsonl
ops/events.jsonl
reviews/reviews.jsonl
validations/runs.jsonl
```

Plus the v0.4-additions to integrity scope:

- `aepkg.json` (manifest itself, canonicalized) — included in `integrity.manifest_hash`.
- `assets/**` — included in `integrity.assets_merkle_root` (recursive sha256 Merkle tree).

`views/` files are generated and never authoritative.

## 8. JSONL record rules

Each non-empty line is one JSON object. UTF-8 encoding only. **No BOM.** LF line endings only (CRLF rejected by validators). Each record MUST include `id`, `type`, `created_at`.

Recommended id prefixes: `src:`, `span:`, `claim:`, `rel:`, `event:`, `review:`, `validation:`.

## 9. Source record

Required: `id`, `type=Source`, `title`, `source_type`, `provenance_strength`, `location`, `limits`, `created_at`.

`source_type` enum (v0.4 extends v0.3):

- `user_artifact`
- `official_spec`
- `primary_source`
- `secondary_source`
- `runtime_output`
- `inference_note`
- `llm_output` *(v0.4 added)*
- `tool_output` *(v0.4 added)*
- `external_research` *(v0.4 added)*
- `human_testimony` *(v0.4 added)*
- `derivation` *(v0.4 added)*
- `other`

`provenance_strength` enum (v0.4 extends v0.3):

- `independent_convergent` *(v0.4 added — operationalizes axiom 8: requires ≥2 sources, lineage-disjoint)*
- `strong`
- `medium`
- `weak`
- `unknown`

`location` is an **object** (not a string), with required `kind` field:
- `kind: "filesystem-path"`, `path`
- `kind: "url"`, `value`, optional `location_hash` (sha256 of fetched bytes at `fetched_at`)
- `kind: "git-ref"`, `repo`, `ref`, `path`
- `kind: "url-or-path"` (mixed; reader-discretion)
- `kind: "in-packet"` — references an `assets/**` file by relative path

For `PROVEN_RELIABLE` claims, at least one basis source MUST be of kind requiring an external anchor: a `url` with `location_hash` set, OR a `git-ref` with `ref` immutable (commit sha, not branch), OR an `in-packet` reference whose hash is committed to `assets_merkle_root`. **This closes the closed-loop fabricated-provenance attack.**

## 10. Span record

Required: `id`, `type=Span`, `source_id`, `selector`, `quote_hash`, `created_at`.

`selector` is an object with required discriminator `kind` (v0.4 normative):
- `kind: "section-paragraph"` — required `section_id` + `paragraph_ordinal`
- `kind: "page-line"` — required `page` + `line_start` + `line_end`
- `kind: "byte-range"` — required `byte_start` + `byte_end`
- `kind: "char-range"` — required `char_start` + `char_end`
- `kind: "dom-path"` — required `xpath` or `css`
- `kind: "screenshot-region"` — required `x` + `y` + `width` + `height` + `screenshot_id`
- `kind: "object-path"` — required `jsonpath` or `dotted_path`

`quote_hash` is `sha256:` + lowercase-hex SHA-256 of:
- UTF-8 NFC-normalized quote text (Unicode normalization REQUIRED; v0.4 normative — v0.3 silently allowed NFC/NFD drift).
- HTML entities decoded.
- Whitespace collapsed via `\s+` → single space, then trimmed.

## 11. Claim record

Required: `id`, `type=Claim`, `text`, `reliability`, `scope`, `basis`, `reasoning`, `owner_agent`, `review_tier`, `status`, `created_at`.

`reliability` MUST be in §3 enum.
`scope` MUST be in §4 enum.
`review_tier` MUST match `^R[1-4]$`.
`status` MUST be in `{active, superseded, rejected, needs_review}`.
`basis` is an array of `{source_id, span_id?}` objects.

**Mechanical enforcement (v0.4 new)**:
- `reliability=PROVEN_RELIABLE` requires `len(basis) ≥ 2` AND at least 2 distinct `source_id` values.
- `reliability=PROVEN_RELIABLE` requires at least one basis source to satisfy §9's external-anchor rule.
- `reliability=UNKNOWN` requires non-empty `reasoning` explaining the missing-evidence state.

Optional `axis_b_action` (§5) recommended for new packets.

## 12. Relation record

Required: `id`, `type=Relation`, `subject`, `predicate`, `object`, `basis_claims`, `inference_label`, `created_at`.

`inference_label` enum:
- `explicit_in_source`
- `derived_from_claims`
- `architectural_inference`
- `analogical_transfer` *(v0.4 added — distinguishes cross-domain analogy from in-domain derivation)*
- `cross_packet_synthesis` *(v0.4 added — relations spanning multiple packets carry stronger provenance discipline)*
- `speculative_design`

## 13. Write event record

Required: `id`, `type=WriteEvent`, `op`, `actor`, `target`, `pre_state_hash`, `post_state_hash`, `rationale`, `created_at`.

**v0.4 mechanical enforcement**: each event's `pre_state_hash` MUST equal the previous event's `post_state_hash`. The first event's `pre_state_hash` MUST be `sha256:` + sha256 of empty string (`e3b0c44...`). Validators reject packets whose event chain breaks this invariant. This closes replay attacks + silent at-rest tampering of the event log.

## 14. Review receipt

Required: `id`, `type=Review`, `reviewer_agent`, `review_tier`, `decision`, `basis`, `findings`, `created_at`.

`decision` enum: `pass | warn | block | defer`.

**v0.4 enforcement of LAW-05 (operator drop)**: when N≥2 reviews target the same claim, validators MUST flag if all reviews' `basis[].source_id` sets collapse to one source-lineage (same-source-not-convergence detection). Flagged as `warn` until v0.8 review-mesh hardens this to `block`.

## 15. Validation run

Required: `id`, `type=ValidationRun`, `validator`, `schema_result`, `checked_files`, `findings`, `state_hash`, `created_at`.

**v0.4 rename**: `result` → `schema_result`. The rename prevents conflation with reliability promotion (per axiom + LAW-06: schema validity is not claim reliability).

`schema_result` enum: `pass | warn | fail`.

## 16. Integrity (state-hash + manifest hash + assets Merkle root)

v0.4 introduces a three-component integrity envelope:

### 16.1 `canonical_state_hash`
Computed over the 7 canonical files. Algorithm:

```python
def canonical_state_hash(packet_root: Path, canonical_files: List[str]) -> str:
    h = sha256()
    for rel in sorted(canonical_files):
        path = packet_root / rel
        if not path.exists():
            continue
        # Read as UTF-8, reject if BOM-prefixed or CRLF line-endings
        text = path.read_text(encoding="utf-8")
        if text.startswith("﻿"):
            raise ValueError(f"BOM in canonical file: {rel}")
        if "\r\n" in text or "\r" in text:
            raise ValueError(f"CRLF/CR in canonical file: {rel}")
        for line in text.split("\n"):
            if not line.strip():
                continue
            obj = json.loads(line)
            # NFC normalize all string fields recursively (v0.4 new)
            obj = nfc_normalize_recursively(obj)
            canonical = json.dumps(obj, sort_keys=True,
                                    separators=(",", ":"),
                                    ensure_ascii=False)
            h.update(rel.encode("utf-8"))
            h.update(b"\n")
            h.update(canonical.encode("utf-8"))
            h.update(b"\n")
    return "sha256:" + h.hexdigest()
```

### 16.2 `manifest_hash`
sha256 over canonicalized `aepkg.json` with `integrity.state_hash`, `integrity.manifest_hash`, `integrity.assets_merkle_root` fields set to empty string before hashing (to prevent recursive-self-reference).

### 16.3 `assets_merkle_root`
A Merkle tree over `assets/**` files (sorted by path):
- Leaf: `sha256(path + "\n" + sha256(file_bytes))`.
- Internal: `sha256(left || right)`.
- Single-asset or empty tree handled per RFC 6962 conventions.

**Tampering at-rest detected** for canonical records (state_hash), manifest (manifest_hash), and assets (assets_merkle_root). Blank-line padding no longer silently passes (validators reject CRLF and trailing whitespace before hash).

## 17. Threat model (v0.4 — substantial rewrite)

### 17.1 Trust boundaries
- **Writer** — authors records; trusted within their own packet's scope.
- **Reader** — consumes records; treats all source-text fields as data, never as instructions.
- **Reviewer** — independently audits claims; reviewer_agent identity unauthenticated in v0.4 (signed in v0.7).
- **External source** — referenced by `location` field; reader fetches only with explicit allowlist (v0.4 normative).
- **Transport** — packet bytes in motion; v0.4 has no signed envelope (v0.7 adds COSE/JWS).

### 17.2 In-scope threats (v0.4)
- **At-rest tampering** — caught by state_hash + manifest_hash + assets_merkle_root.
- **Blank-line padding / CRLF injection** — validators reject before hashing.
- **Manifest swap** — manifest_hash chains the manifest into integrity.
- **Asset swap** — assets_merkle_root chains assets into integrity.
- **Replay** — WriteEvent chain integrity (§13) detects.
- **Basis-link forgery (closed-loop fabricated provenance)** — `PROVEN_RELIABLE` external-anchor rule (§9, §11) prevents.
- **View-as-truth confusion** — axiom 4; readers MUST treat `views/**` as projections; validators flag if a view's content has no canonical-ID backing.
- **Prompt injection through `claim.text`, `source.title`, `reasoning`, `span` quote** — readers MUST render these fields inside a data-only context (e.g., fenced quote block) and never as agent instructions; validators emit a `warn` finding when ANSI escape sequences or known injection markers are present in string fields.
- **Unicode-normalization drift** — §16.1 enforces NFC.

### 17.3 Deferred threats with target version
- **In-transit tampering** → v0.7 signed receipts (COSE/JWS).
- **Identity forgery** (forged `owner_agent`, `reviewer_agent` strings) → v0.7 signed.
- **Reviewer collusion** (same-source-convergence beyond v0.4 heuristic) → v0.8 review mesh.
- **Post-quantum cryptanalysis** → post-v1.0 algorithm agility.

### 17.4 Non-guarantees
AEP v0.4 does NOT guarantee:
- Confidentiality of packet contents.
- Availability of `location`-referenced external sources over time.
- Authenticity of `owner_agent` / `reviewer_agent` identity strings (until v0.7).
- Detection of socially-engineered consensus among colluding writers.

### 17.5 Validator obligations (fail-closed)
Validators MUST fail closed on:
- Chain break (event N+1's `pre_state_hash` ≠ event N's `post_state_hash`).
- State-hash mismatch.
- Manifest-hash mismatch.
- Assets Merkle-root mismatch.
- Unknown required profile.
- CRLF or BOM in canonical files.
- Empty basis on `PROVEN_RELIABLE` claim.
- Same-source basis collapse on `PROVEN_RELIABLE` claim.
- Missing reasoning on `UNKNOWN` claim.

## 18. Promotion rule (clarified)

A claim may enter durable memory (be cited by other packets as `PROVEN_RELIABLE`) only when:

1. It has a reliability label and scope.
2. It has provenance OR is explicitly marked `UNKNOWN` / `ASSUMPTION`.
3. It passes schema validation (necessary but **not sufficient** — schema validity is not reliability per LAW-06).
4. It has no unresolved `block` review.
5. Time-sensitive claims have revalidation metadata.
6. **v0.4 new**: `PROVEN_RELIABLE` claims have ≥2 distinct-source basis with at least one external anchor per §9.
7. **v0.4 new**: `validations/runs.jsonl` has at least one entry with `schema_result=pass` against the packet's profile schema.

## 19. JSON-LD profile (`aep:0.4/jsonld`)

The v0.4 JSON-LD profile is the recommended interoperability tier. Specifies:

- `contexts/aep.context.jsonld` — required for `aep:0.4/jsonld`.
- Maps `claim`, `source`, `span`, `relation`, `event`, `review`, `validation` to schema.org + PROV-O concepts where stable:
  - `aep:Claim` → `schema:ClaimReview` + `prov:Entity` aspects.
  - `aep:Source` → `schema:Dataset` + `prov:Entity`.
  - `aep:Span` → `prov:Entity` (a fragment of a Source).
  - `aep:WriteEvent` → `prov:Activity` + `prov:wasGeneratedBy`.
  - `aep:Review` → `prov:Activity` + `schema:Review`.
- Backward compatibility: every `aep:0.4/jsonld` packet is also a valid `aep:0.4/minimal-jsonl` packet (the JSON-LD layer is additive; canonical files unchanged).

JSON-LD export MUST preserve claim IDs and basis links byte-perfectly across roundtrip (v0.4 normative gate).

## 20. Evolution model + versioning policy

Versioning: **profile-versioned with semver-on-each-profile.**

- Profile name: `aep:<major>.<minor>/<profile>` (e.g., `aep:0.4/jsonld`).
- Patch versions handle tooling fixes (`0.4.0 → 0.4.1`).
- Minor versions handle backward-compatible additions (`0.4 → 0.5`).
- Profile name change handles breaking changes (`aep:0.4/jsonld → aep:0.5/prov` adds PROV-O profile).
- Spec semantic version frozen at `aep:1.0` after ≥3 independent implementations validate the same corpus identically.

Roadmap:

| Profile | Adds | Target |
|---|---|---|
| `aep:0.3/minimal-jsonl` | Baseline JSONL + validator (already shipped) | — |
| `aep:0.4/minimal-jsonl` | Mandatory amendments from this spec (NFC, manifest+assets hash, event chain, axiom-8 enforce, external-anchor, schema-result rename) | 2026-Q2 |
| `aep:0.4/jsonld` | JSON-LD context + RO-Crate compatibility | 2026-Q2 |
| `aep:0.5/prov` | Full PROV-O ontology mapping | 2026-Q3 |
| `aep:0.6/shacl` | SHACL shapes + RDF/TriG export | 2026-Q4 |
| `aep:0.7/signed` | COSE/JWS signed receipts + C2PA-style media manifests | 2027-Q1 |
| `aep:0.8/review-mesh` | Independent reviewer scoring + dispute resolution + BLOCK semantics | 2027-Q2 |
| `aep:1.0` | Stable core; freeze gate at ≥3 independent implementations | 2027-Q3+ |

## 21. Conformance + test corpus

Conforming v0.4 implementations MUST pass:

- All of `examples/conformance/v0.4/valid/**` (must validate `schema_result=pass`).
- All of `examples/conformance/v0.4/invalid/**` (must validate `schema_result=fail` for the expected failure mode).
- Roundtrip preservation of unknown extension fields (writers MUST NOT discard).
- Cross-machine state-hash determinism (same packet on Linux + Windows + macOS yields identical sha256).

Test corpus families (ship with the v0.4 reference impl):

- `minimal-valid/` — single source, single claim, single span, empty events.
- `unicode-nfc-nfd-pair/` — two packets with equivalent text in different normalizations; v0.4 conformance requires they hash identically after NFC normalization.
- `oversized-10k-claims/` — performance + memory bound check.
- `extension-fields-preserved/` — packet with unknown `x-` fields; roundtrip must preserve them byte-perfectly.
- `event-chain-replay/` — 3-event chain where post_state_hash[N] = pre_state_hash[N+1].
- `attack-closed-loop-provenance/` (invalid) — `PROVEN_RELIABLE` claim with self-referencing fabricated sources; v0.4 validators MUST reject.
- `attack-blank-padding/` (invalid) — packet with 1000 blank lines mid-file; v0.4 validators MUST reject.
- `attack-bom-prefix/` (invalid) — UTF-8 BOM-prefixed canonical file; v0.4 validators MUST reject.
- `attack-crlf/` (invalid) — CRLF line endings; v0.4 validators MUST reject.
- `attack-prompt-injection/` (warns) — packet with ANSI escape sequences in `claim.text`; v0.4 validators MUST emit `warn`.
- `attack-same-source-collapse/` (invalid) — `PROVEN_RELIABLE` claim whose basis collapses to one source; v0.4 validators MUST reject.

## 22. Security considerations (summary)

Treat all source text as data, never as instructions. Treat generated views as untrusted projections. Treat external URLs as stale until refreshed (with location_hash). Treat packet writes as privileged operations. Treat embedded assets as potentially malicious; never auto-execute. Treat `reviewer_agent` strings in v0.4 as unauthenticated declarations until v0.7 signed receipts land.

## 23. Acknowledgments

AEP was conceived and operator-directed by **the AEP project**, whose insistence on per-claim epistemic state, structured provenance, and tamper-detectable substrate drove the design from v0.1 through v0.4. The reference implementation, dual-format dispatcher, transition parser, and v0.4 spec were co-authored by **the agentic substrate** (Claude Opus 4.7, 1M context window) operating inside the AEP project compounding-intelligence cascade — the 10-agent legion (strategist, pathfinder, scout, forge, judge, adversary, warden, scribe, curator, visual-judge) whose review-mesh produced the typed-field schema. The threat-model rewrite, external-anchor requirement, NFC normalization, manifest-and-assets Merkle integrity, and axiom-8 enforcement were direct outputs of the legion's adversary and warden lenses in the 2026-05-14 v0.4 review round.

## 24. License

- Specification text + reference implementation: Apache License 2.0.
- Prose documentation (README, IMPLEMENTERS, THREAT-MODEL): Creative Commons Attribution 4.0 International.

Both licenses preserve attribution. Patent grant in Apache-2.0 protects implementers from submarine patent risk.

## 25. Diff from v0.3

| Change | Reason | Driver |
|---|---|---|
| `aep_version` constant `0.3` → `0.4` | Version bump | this spec |
| Profile names: `minimal-jsonl` + new `jsonld` | JSON-LD entry tier | strategist, scout, curator |
| `created_at` format normative (RFC3339 UTC `Z`) | Unspecified in v0.3 | forge |
| `source.location` is object with `kind` discriminator | v0.3 silently allowed any | forge, judge |
| `source_type` enum extended (+5 values: `llm_output`, `tool_output`, `external_research`, `human_testimony`, `derivation`) | v0.3 collapsed real cases into `other` | judge |
| `provenance_strength` adds `independent_convergent` | Operationalizes axiom 8 | judge, curator |
| `span.selector` has required `kind` enum + per-kind schema | v0.3 schema was `{type:object}` only | forge |
| `span.quote_hash` algorithm normative (NFC + entity-decode + whitespace-collapse) | v0.3 algorithm unspecified | forge, warden, adversary |
| `claim.reliability` adds `GOVERNANCE_RULE` class | AEP project §02 Amendment A15 | curator |
| `claim.basis` for `PROVEN_RELIABLE` requires ≥2 distinct sources + external anchor | Closes closed-loop fabricated-provenance attack | adversary, judge |
| `axis_b_action` field optional but recommended | Two-axis schema from V11 charter | strategist, curator |
| `relations.inference_label` adds `analogical_transfer` + `cross_packet_synthesis` | Conflation hidden in v0.3 | judge |
| `event.pre_state_hash` must chain to previous event's `post_state_hash` | Replay attack mitigation | warden, adversary |
| `validation.result` renamed to `schema_result` | Prevents conflation with reliability promotion | judge |
| `integrity` adds `manifest_hash` + `assets_merkle_root` | Tampering at-rest of manifest/assets was undetected | warden |
| State-hash requires NFC normalization | Cross-platform determinism | warden, adversary |
| State-hash rejects BOM + CRLF | Tampering disguise / determinism | warden |
| Threat model expanded to 8 sub-sections from 5 prose truisms | Pre-publication adversary battle-test | adversary, warden |
| Conformance test corpus + attack-family fixtures specified | Independent-implementation gate | forge, curator |
| JSON-LD profile + RO-Crate compatibility | Adoption via existing ecosystem | strategist, scout, curator |
| Promotion rule explicit re: schema-not-reliability | LAW-06 enforcement | judge, curator |

Implementers upgrading from v0.3 → v0.4: re-validate the existing corpus; non-NFC strings will hash differently and trigger validator findings. The reference implementation ships a `migrate_v0_3_to_v0_4.py` tool that detects non-conformant packets and emits a migration plan.
