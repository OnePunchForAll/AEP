# AEP v1.0.3 SPEC - Regexical Memory

**Status**: **LANDED-DOWNGRADED 2026-05-18**. Ships under VG04 `HARD-CONDITIONAL` verdict (3-reader mean 3.44 below 4.0 PASS threshold) per Phase 2 receipts row 2 + row 2.5. Scope reduced via Rollback A: schema + validator + F9 quorum + DRY-RUN sandbox retrofit + STAGED corpus migrator + BC-V103-1 empirical test. Canonical adversary retrofit + full 10-agent retrofit + L01-L12 doctrine promotion ALL STAGED for v1.0.3.1.
**Predecessors**: AEP v0.8.0 STABLE (LANDED 2026-05-17, last frontier-break SPEC.md); v1.0.0 / v1.0.1 / v1.0.2 runtime-only (no SPEC.md; F9 cross-substrate quorum + F10 signed in-toto ITE6 receipts unlocked at v1.0.2).
**Authors**: operator (operator) + the agentic substrate (Claude Opus 4.7 1M-context, AEP project 10-agent legion: pathfinder + judge + warden + adversary + forge co-authored under §73.4 single-forge-for-product-builds for this SPEC body).
**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).
**Profiles**:
- `aep:1.0.3/stable` (regexical_memory ACTIVE; cue records present in `data/claims.jsonl`; recall events in `ops/events.jsonl`)
- `aep:1.0.3/regexical-disabled` (additive fields ABSENT; BC-V103-1 baseline - byte-identical canonical-JSONL state_hash to v0.8/v1.0.x reader)
- `aep:1.0.3/regexical-staged` (DRY-RUN sandbox copy carries cue; canonical packet untouched; this is the v1.0.3.0 default for the adversary pilot)

**Composes with**:
- `doctrine/02-truth-tags.html` (Amendment A15 GOVERNANCE-RULE)
- `doctrine/41-hash-chained-receipt-ledger.html` (HCRL anti-compliance-theater + `evidence_bindings_size_bytes` per M6 closure)
- `doctrine/50-epistemic-hygiene-meta-law.html` (Law 1 mechanism-not-name + Law 3 multi-lens convergence + anti-source-laundering)
- `doctrine/52-hybrid-prose-aep-bridge.html` (Hybrid Bridge Protocol for prose <-> AEP delegation)
- `doctrine/60-pre-coding-lesson-review-discipline.html` (lesson scan before any code emission)
- `doctrine/69-verification-law-and-operator-spec-sovereignty.html` (all 9 sub-laws; sec69.4 non-rescindability binding on this SPEC)
- `doctrine/70-surface-mirror-discipline.html` (chat + artifact + cowork projections this SPEC ships)
- `doctrine/71-operator-sustainability.html` (rest-signal cap respected; this SPEC closes within the 4h continuous-autonomy cap)
- `doctrine/72-canonical-order-of-operations.html` (firing-order: pathfinder -> adversary -> judge VG04 -> warden re-score -> judge tiebreaker -> forge unified Phase 3+4+5 -> scribe lesson)
- `doctrine/73-external-claude-receipt-laws.html` (all 6 sub-laws binding; sec73.4 enforced by this single forge invocation)
- `doctrine/_proposals/operator-2026-05-18-aep-v1-0-3-regexical-memory-charter.html` (charter)

**Cites (sec73.3 prior-art-inheritance, NOT regenerated)**:
- `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/source.md` (operator proposal · IQ01-IQ12 L217-230 · R01-R18 L234-253 · VG01-VG11 L257-269 · L01-L12 L285-297 · P01-P08 L302-310)
- `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/regexical_memory_schema.json` (operator JSON Schema draft 2020-12; byte-identical copy at `projects/v11-aep/publish-ready/aep/schemas/regexical_memory.schema.json` · sha256 `1bb674654ff75afc2660ade6f96456bab7ef054a33390ea85a7178bbf0d314bb`)
- `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/regexical_memory_example_adversary.jsonl` (operator seed cue · `premortem weakest-assumption` on adversary AEP)

---

## sec1 - Frontier-break delta from v0.8 to v1.0.3

### sec1.1 - Why v1.0.3 exists as the first SPEC.md after v0.8

v0.8.0 (LANDED 2026-05-17) closed bit-for-bit packet reproducibility from sources. v1.0.0 / v1.0.1 / v1.0.2 added runtime primitives (F9 cross-substrate quorum executor + F10 signed in-toto ITE6 receipts) WITHOUT a new SPEC.md - packet structure was unchanged per `wave_044_corpus_migrate_v1_0_2.py` `aepkg_json_untouched: true`. v1.0.3 breaks that pattern by introducing the **first new claim type since v0.5** (`RegexicalCue`) and the **first new event-family since v0.5** (`regexical_memory_*`), justifying a SPEC.md release.

Why now: operator directive 2026-05-18 "autonomously please work on AEP v1.0.2 into v1.0.3 maintaining our current advancements but lets take it even further: Done. I built a agent-ready packet plus machine-readable assets for **Regexical Memory as AEP-native spaced repetition**." (verbatim per sec73.2 OPERATOR-VERBATIM-SACRED).

What v1.0.3 delivers (HONEST DOWNGRADED SCOPE per VG04 Rollback A):
1. `RegexicalCue` claim type schema (operator-supplied; byte-identical inheritance per sec73.3).
2. Six `regexical_memory_*` event types (created / validated / review_due / cue_superseded / collision_detected / recall_attempted).
3. Optional `aepkg.json.extensions.regexical_memory` manifest field pointing at active cue IDs.
4. Portable-regex quorum runner (F9 wrapper at `scripts/f9_regex_quorum.py`).
5. JSON Schema validator with allow-list audit per M5 closure (at `scripts/validate_regexical_memory.py`).
6. DRY-RUN sandbox adversary pilot (canonical `.claude/agents/adversary.aepkg/` UNTOUCHED; sandbox copy at `projects/v11-aep/pilots/regexical-memory-pilot/adversary-sandbox.aepkg/`).
7. SKELETON-STUB corpus migrator (STAGED; v1.0.3.1 GA after >= 10 pilot retrofits clear).
8. Empirical BC-V103-1 test (canonical JSONL state_hash unchanged).

### sec1.2 - Truth-tag downgrade per VG04 outcome

The original riskiest claim was:

> Cues survive blind-recall >=90% structured-field accuracy on N=3 attempts across canonical agents WITHOUT opening source files.

This claim was tagged `EXPERIMENTAL` in the pathfinder plan. Phase 2 VG04 pilot **PARTIALLY FALSIFIED** it: 3 readers produced means of 4.00 (the agent) / 3.00 (warden) / 3.33 (judge); overall mean 3.44 below the 4.0 PASS threshold. The persona-bound extensions (checkbox-laundering, prompt-injection, scope-creep additions to `failure_prevented`) scored reasonable but did NOT compensate for the missing gold-standard items (b) `schema-valid-but-reliability-unsupported-promotion` and (c) `fabricated-or-unresolved-citation` - both anchored to citation-integrity per judge's load-bearing analysis at `.claude/_logs/aep-v103-vg04-judge-tiebreaker.jsonl`.

Per sec02 truth-tag taxonomy + V11-AEP two-axis schema, sec3 cue-recall claim ships at:

| Axis | Tag |
|---|---|
| sec02 single-axis | `EXPERIMENTAL × CONTEXT-BOUND PATTERN` |
| V11-AEP Axis A (epistemic) | `PLAUSIBLE` |
| V11-AEP Axis B (action) | `EXPERIMENT` |

This is a **downgrade from `STRONGLY PLAUSIBLE`** which would have been the tag had VG04 cleared 4.0 mean. The downgrade is binding under sec69.4 (non-rescindable adversary closures).

### sec1.3 - Honest framing: not novel primitive, novel application domain

Spaced repetition is well-established human-learning literature: Anki manual + SuperMemo SM-2 algorithm + FSRS (cited verbatim in operator source.md S7/S8 at L37-39 - inherited NOT regenerated). The novelty of v1.0.3 is **transposing SRS into agent-evidence packet memory**: each AEP packet becomes a source-bound spaced-repetition card, with cues that route retrieval and reconstruct minimum operational meaning WITHOUT full-file reabsorption. This mirrors AEP v0.8's framing: "the first agent-evidence-domain transposition of [build-reproducibility discipline] into the claim-graph domain" (per AEP_v0_8_SPEC.md sec V80-4).

What v1.0.3 explicitly does NOT claim:
- Not "perfect compression" (per operator source.md C10/C11 at L56-57 - cues are handles, not content).
- Not "perfect recall" (VG04 mean 3.44 empirically refutes this).
- Not a substitute for the full AEP file (sec02 anti-source-laundering binding; full file remains authority for exact quotes / current tool lists / line-level audit).
- Not promotable as evidence (Law L10 candidate "SRS Optimizes Retrieval, Not Truth" - inherited from operator source.md L295).

---

## sec2 - BC-V103-1 backward-compatibility clause (HV1 CLOSURE)

### sec2.1 - Revised BC-V103-1 statement

Per adversary HV1 closure (binding under sec69.4):

> **BC-V103-1**: For any AEP packet, the canonical JSONL `state_hash` (computed per `lib/aep-reference/src/aep/validate.py` L150-167 over the sorted set `data/claims.jsonl`, `data/relations.jsonl`, `data/spans.jsonl`, `data/sources.jsonl`, and `ops/events.jsonl`) MUST be byte-equal between (a) the canonical packet and (b) the same canonical packet with all `type: RegexicalCue` claims filtered out + all `regexical_memory_*` events filtered out. The `state_hash` reflects only the canonical claim-graph + event-stream content; regexical_memory rows are additive opt-in projections that the state_hash MUST NOT depend on.

### sec2.2 - What BC-V103-1 does NOT claim (HV1 dormitive-virtue dropped)

The original BC-V80-1 invariant phrasing "manifest sha256 unchanged" was DROPPED per HV1 closure. Reasons:
- `aepkg.json` is NOT in the `state_hash` formula (per `validate.py` L150-167 - state_hash iterates `canonical_files` declared in manifest, but `aepkg.json` itself is not in that list).
- Manifest invariance is a weaker claim than canonical-content invariance; the load-bearing property is "the claim-graph hash does not depend on regexical fields."
- Manifest sha256 CAN legally change when `extensions.regexical_memory` is added (that field IS in the manifest); demanding manifest-hash invariance would prohibit the manifest extension entirely, defeating the optional-extension design.

### sec2.3 - Empirical falsifier for BC-V103-1

Ships at `projects/v11-aep/publish-ready/aep/tests/test_bc_v103_1_canonical_state_hash_unchanged.py`. The test:

1. Computes `state_hash` over the canonical `.claude/agents/adversary.aepkg/` (PRE-retrofit baseline).
2. Computes `state_hash` over `projects/v11-aep/pilots/regexical-memory-pilot/adversary-sandbox.aepkg/` (DRY-RUN sandbox WITH regexical rows present).
3. Filters out `type: RegexicalCue` claims + `regexical_memory_*` events from the sandbox view.
4. Computes `state_hash` over the filtered view (POST-retrofit, regexical-stripped).
5. Asserts byte-equal between (1) and (4).

PASS exit code 0. FAIL exit code 1 with diagnostic showing which canonical file's hash differs.

This is the load-bearing empirical test for the BC-V103-1 claim. If this test ever fails for a v1.0.3 packet, the BC-V103-1 invariant is FALSIFIED and v1.0.3 is broken - either the regexical write path leaked into a canonical file outside the `extensions.regexical_memory` projection (which is the violation pattern), or the filter logic is wrong (which is fixable in the test).

### sec2.4 - sec73.5 warden receipt for BC-V103-1

The test produces a structured-log row to be captured in HCRL receipt row 4 per sec73.5 (parse-check + runtime-trace + no-screen-fail). The test runner script also writes a one-line JSONL receipt to `.claude/_logs/aep-v103-bc-test-receipts.jsonl` per `evidence_bindings_size_bytes` discipline (M6 closure).

---

## sec3 - RegexicalCue claim type

### sec3.1 - Schema location + integrity

The JSON Schema (draft 2020-12) at `projects/v11-aep/publish-ready/aep/schemas/regexical_memory.schema.json` is byte-identical to the operator-supplied schema at `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/regexical_memory_schema.json` per sec73.3 prior-art-inheritance.

**sha256**: `1bb674654ff75afc2660ade6f96456bab7ef054a33390ea85a7178bbf0d314bb`
**size**: 6881 bytes
**$id**: `aep:regexical-memory:0.1`
**title**: AEP Regexical Memory Cue

### sec3.2 - Required fields (inherited from operator schema; cite-only per sec73.3)

Per operator schema `required` array (operator source asset L301-316):

`type, schema_version, id, packet_id, profile, created_at, created_by_agent, cue_words, cue_phrase, regex, source_bindings, recall_payload, srs, validation`

the agent does NOT re-enumerate field semantics here - the schema is the canonical normative source (sec50 EH no-source-laundering). The validator at `scripts/validate_regexical_memory.py` enforces these requirements mechanically.

### sec3.3 - M5 closure: allow-list enforcement on `additionalProperties: true` defaults

The operator schema declares `additionalProperties: true` on three sub-objects:
- `recall_payload` (operator schema L75-76)
- `integrity` (operator schema L49-50)
- `srs` (operator schema L205-207)

This is a SECURITY-SHAPED LOOSENESS per adversary M5 closure (binding under sec69.4). Validator-side mitigation:

The shipped `scripts/validate_regexical_memory.py` extends standard JSON Schema validation with a **post-validation explicit allow-list audit** for these three sub-objects. After draft-2020-12 validation passes, the validator iterates the keys of `recall_payload`, `integrity`, and `srs` and flags any key NOT in the schema's declared `properties` list. The validator emits a `WARN` (not blocking error) by default; `--strict-allow-list` flag escalates to a blocking error. This is the v1.0.3 ship; v1.0.3.1 will tighten the schema to `additionalProperties: false` after `>=10 pilot retrofits` have shipped to confirm no legitimate extensions are needed.

The allow-list for each sub-object (computed mechanically from the schema's `properties` keys):

| Sub-object | Allow-list (schema properties) |
|---|---|
| `recall_payload` | `distinguishers`, `failure_prevented`, `kind`, `minimum_recall_fields`, `one_sentence`, `owner_agent`, `stop_condition`, `when_to_open_full_file` |
| `integrity` | `canonicalization`, `cue_record_sha256_excluding_integrity`, `receipt_required_for_install` |
| `srs` | `algorithm`, `due_at`, `ease_factor`, `interval_days`, `lapses`, `minimum_ease_factor`, `next_reviews_seed`, `repetitions`, `review_scale` |

### sec3.4 - Compound-cue limit (cited per M5 closure)

Per operator schema `regex.patterns.maxItems: 8` (operator schema L155), a `RegexicalCue` may have at MOST 8 portable-regex patterns. Compound cues with >8 patterns MUST split into two cues per sec3.4. The validator enforces this mechanically via the JSON Schema `maxItems`.

### sec3.5 - Truth-tag for sec3 (per VG04 downgrade)

The claim "RegexicalCue is a useful agent-recall primitive" ships at:

- sec02 tag: `EXPERIMENTAL × CONTEXT-BOUND PATTERN` (DOWNGRADED from STRONGLY PLAUSIBLE per VG04 Rollback A; binding sec69.4)
- V11-AEP Axis A: `PLAUSIBLE`
- V11-AEP Axis B: `EXPERIMENT`

Promotion to `STRONGLY PLAUSIBLE` requires sec73.5 warden receipt of >= 10 pilot retrofits clearing >= 4.0 mean rubric on cross-reader VG04 (the agent + warden + judge) per VG09 amendment below.

---

## sec4 - regexical_memory_* event types

### sec4.1 - The 6 event types (per operator IQ02 + source.md AEP project Architecture Impact table at L178-179)

Cite-only per sec73.3 (operator source.md L172-186 "AEP project Architecture Impact" + L178 "Events" row). AEP project adds the following event types to `ops/events.jsonl`:

| Event type | Fires when | Required fields | Owner |
|---|---|---|---|
| `regexical_memory_created` | Cue is born (birth_event OR retrofit_existing_packet OR retrofit_example_for_existing_packet) | `cue_id`, `packet_id`, `creation_mode`, `created_by_agent`, `created_at` | originating agent |
| `regexical_memory_validated` | F9 quorum passes (compile + match) across required runtimes | `cue_id`, `quorum_target`, `compile_and_match_results`, `validated_at` | forge + warden |
| `regexical_review_due` | SRS scheduler determines cue's `due_at` has elapsed | `cue_id`, `due_at`, `interval_days`, `repetitions`, `next_review_action` | curator |
| `regexical_cue_superseded` | Body-hash drift guard fires OR cue manually replaced | `superseded_cue_id`, `successor_cue_id_or_null`, `reason_code`, `superseded_at` | warden + curator |
| `regexical_collision_detected` | Corpus collision scan finds another packet matching the same cue_phrase | `cue_id`, `colliding_packet_ids`, `collision_severity`, `distinguisher_required` | scout + curator |
| `regexical_recall_attempted` | Agent uses cue (cue-only retrieval) and emits recall_payload | `cue_id`, `attempt_id`, `rubric_score`, `fabrication_count`, `stop_condition_present`, `attempted_at` | judge |

### sec4.2 - M4 closure: `regexical_recall_attempted` must encode the `line_numbers_in_source_md` adversarial probe trap

Per adversary M4 closure (binding under sec69.4), every `regexical_recall_attempted` event for a VG04 attempt MUST include the `line_numbers_in_source_md` field on the embedded `recall_payload` (or its containing attempt record). If the cue agent emits non-empty line numbers (i.e., fabricated specific source line ranges WITHOUT opening the source.md), the rubric_score MUST be `1` (FAIL-MISLEADING) regardless of other fields. The honest behavior is `[]` (empty array - no line numbers known) per Phase 2 attempts vg04-001 / vg04-002 / vg04-003 which all emitted `[]` and passed the M4 probe.

This is a MANDATORY field for any future VG04 cue activation per VG09 amendment.

### sec4.3 - Event-stream BC-V103-1 invariance

All 6 event types live in `ops/events.jsonl` which IS part of `state_hash`. Therefore the BC-V103-1 invariant (sec2.1) requires that when these events are filtered out (i.e., when `event_type` startswith `regexical_memory_` OR `regexical_review_` OR `regexical_cue_` OR `regexical_collision_` OR `regexical_recall_`), the resulting filtered event-stream's hash equals the pre-retrofit event-stream's hash. The empirical BC test at `tests/test_bc_v103_1_canonical_state_hash_unchanged.py` enforces this.

---

## sec5 - Optional `aepkg.json.extensions.regexical_memory` manifest field

### sec5.1 - Field shape (cite-only per sec73.3)

Per operator source.md L185 "Manifests" row: optional `aepkg.json.extensions.regexical_memory` MAY store pointer to active cue IDs; canonical event/review/validation ledgers remain authoritative per IQ03 (operator source.md L221).

Shape proposed (NOT operator-prescribed verbatim; AEP project inference):

```json
"extensions": {
  "regexical_memory": {
    "active_cue_ids": ["rxmem:<packet-id>:<cue-phrase>:v0", ...],
    "schema_version": "aep-regexical-memory-0.1",
    "default_quorum": "F9_cross_substrate_quorum_default_N3_python_node_perl",
    "default_srs_algorithm": "SM2_LITE_BOOTSTRAP",
    "last_updated_at": "<ISO-8601 UTC>"
  }
}
```

Because `aepkg.json` is NOT in `state_hash`, adding this extension does NOT trigger any BC-V103-1 violation per sec2.1.

### sec5.2 - Validator behavior

Validator MAY check that every cue_id in `extensions.regexical_memory.active_cue_ids` resolves to a `type: RegexicalCue` claim in `data/claims.jsonl` with `status: active`. Mismatch emits `RXMEM_MANIFEST_POINTER_UNRESOLVED` (WARN, not blocking error) since extensions are advisory.

### sec5.3 - DRY-RUN status

For the v1.0.3 adversary pilot ship, NO `aepkg.json.extensions.regexical_memory` is written. The DRY-RUN sandbox writes the cue claim + 4 events ONLY; the manifest stays untouched (preserving canonical adversary.aepkg byte-equality in the sandbox copy minus the additive rows).

---

## sec6 - sec73.3 inheritance lines (NOT regenerated)

### sec6.1 - Implementation Queue IQ01-IQ12

Cite-only per sec73.3. See `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/source.md` L217-230 "Implementation Queue" table.

| Inheritance | Operator source line range | AEP project this-ship status |
|---|---|---|
| IQ01 Define AEP Regexical Memory extension | L219 | LANDED (this SPEC.md + schema) |
| IQ02 Add creation-time cue hook | L220 | STAGED (v1.0.3.1; no hook this ship) |
| IQ03 Use existing ledgers for storage | L221 | LANDED (cue in `claims.jsonl`, events in `events.jsonl`) |
| IQ04 Implement portable regex validator | L222 | LANDED (`scripts/validate_regexical_memory.py` + `f9_regex_quorum.py`) |
| IQ05 Implement corpus collision scanner | L223 | STAGED (v1.0.3.1) |
| IQ06 Add recall payload rubric | L224 | LANDED-CONDITIONAL (rubric used in VG04; rubric refinement STAGED v1.0.3.1 per VG04 HARD-CONDITIONAL gap finding) |
| IQ07 Add SRS scheduler | L225 | STAGED (SM2-lite bootstrap field present in schema; scheduler not running) |
| IQ08 Add F10 install receipt | L226 | STAGED (sandbox carries `signature: STAGED_v_1_0_3_1` stub) |
| IQ09 Add body-hash drift guard | L227 | STAGED (schema carries `source_bindings.source_sha256`; guard not running) |
| IQ10 Pilot on canonical agents | L228 | LANDED-DRY-RUN (adversary sandbox only; canonical untouched) |
| IQ11 Add retrieval command | L229 | STAGED (v1.0.3.1; no CLI this ship) |
| IQ12 Promote laws after pilot | L230 | STAGED (L01-L12 promotion deferred per VG04 HARD-CONDITIONAL) |

### sec6.2 - Adversarial Risks R01-R18

Cite-only per sec73.3. See operator source.md L234-253 "Adversarial Risks" table.

| Inheritance | Operator source line range | AEP project this-ship mitigation status |
|---|---|---|
| R01 Mnemonic overclaim | L236 | LANDED (sec1.3 explicit anti-claim list; Law L01 candidate STAGED) |
| R02 Cue collision retrieves wrong packet | L237 | STAGED (collision scan IQ05 deferred v1.0.3.1) |
| R03 Cute/arbitrary words are not source-grounded | L238 | LANDED (schema requires `source_bindings.minItems: 1`) |
| R04 Regex engine divergence | L239 | LANDED (F9 quorum runner ships) |
| R05 Regex ReDoS / catastrophic backtracking | L240 | LANDED (validator lints `forbidden_features`) |
| R06 Stale cue after source/body mutation | L241 | STAGED (drift guard IQ09 v1.0.3.1) |
| R07 Prompt injection from source text | L242 | STAGED (warden sensitivity scan v1.0.3.1) |
| R08 False recall fluency | L243 | LANDED-CONDITIONAL (VG04 rubric used; 3.44 mean is partial mitigation evidence) |
| R09 Review burden / queue spam | L244 | STAGED (SRS scheduler IQ07 v1.0.3.1) |
| R10 Privacy leakage in cue words | L245 | STAGED (warden scan v1.0.3.1) |
| R11 Duplicate doctrine or duplicate memory cards | L246 | STAGED (curator dedupe v1.0.3.1) |
| R12 Source laundering through recall payload | L247 | LANDED (sec1.3 anti-claim list + sec02 EH binding) |
| R13 Storage bloat and hidden dependency | L248 | LANDED (schema `maxItems: 8` on patterns; sec3.4) |
| R14 "Perfect recall" myth | L249 | LANDED (sec1.3 explicit honest framing) |
| R15 v1.0.2 compatibility error | L250 | LANDED (BC-V103-1 empirical test sec2.3) |
| R16 Self-generated recall as gold standard | L251 | LANDED (HV2 closure: warden + judge re-score independent of the agent) |
| R17 Cue hijacking by malicious packet text | L252 | STAGED (warden scan + source hierarchy v1.0.3.1) |
| R18 Schedule optimizes confidence rather than correctness | L253 | STAGED (SRS scheduler IQ07 v1.0.3.1) |

### sec6.3 - Validation Gates VG01-VG11

Cite-only per sec73.3. See operator source.md L257-269 "Validation Gates" table.

| Inheritance | Operator source line range | AEP project this-ship status |
|---|---|---|
| VG01 Source-binding check | L259 | LANDED (schema `source_bindings.minItems: 1` enforced) |
| VG02 Portable regex quorum | L260 | LANDED (F9 runner ships; 3 patterns x 3 runtimes per operator example) |
| VG03 Collision scan | L261 | STAGED (v1.0.3.1) |
| VG04 Blind recall test | L262 | LANDED-DOWNGRADED (mean 3.44 HARD-CONDITIONAL; sec7 below) |
| VG05 File-open discipline | L263 | LANDED (stop_condition required field per schema) |
| VG06 Scheduler sanity | L264 | STAGED (no scheduler running v1.0.3) |
| VG07 Drift guard | L265 | STAGED (no drift guard running v1.0.3) |
| VG08 F10 receipt audit | L266 | STAGED (sandbox stub only; not signed) |
| VG09 Cross-agent reviewer gate | L267 | LANDED-AMENDED (HV2 closure: warden + judge re-score; 3-reader minimum codified as SPEC-canonical per amendment below) |
| VG10 Pilot threshold | L268 | LANDED-DOWNGRADED-DRY-RUN (1 agent pilot, NOT 10; STAGED v1.0.3.1) |
| VG11 Generalization block | L269 | LANDED (sec1.3 anti-claim list + sec02 EH binding) |

### sec6.3.1 - VG09 amendment (HV2 closure binding)

VG09 amended in this SPEC body per adversary HV2 closure: Phase 2 second-score MUST be warden (not judge), with judge as tiebreaker if `|warden_mean - agent_mean| > 0.5`. The 3-reader pattern (the agent + warden + judge) is now SPEC-canonical for any future cue activation. Mean-delta threshold for independence-PASS is `<= 0.5` cross-reader. Sample Phase 2 outcome: the agent 4.00 / warden 3.00 -> delta 1.00 > 0.5 -> judge tiebreaker fired -> judge 3.33 -> overall mean 3.44 -> verdict HARD-CONDITIONAL.

### sec6.4 - Law Candidates L01-L12

Cite-only per sec73.3. See operator source.md L285-297 "Law Candidates" table. ALL 12 candidates STAGED for v1.0.3.1 doctrine promotion per VG04 HARD-CONDITIONAL outcome - no law candidates promoted in this SPEC ship. Promotion path: post-pilot curator audit at `doctrine/_proposals/curator-<date>-rxmem-law-promotions.html` requires (a) `>= 10` pilot retrofits cleared at `>= 4.0` rubric mean (b) `>= 3-reader` independence per VG09 amendment (c) sec73.5 warden receipt chain unbroken from row 1 to promotion row.

| L candidate | Name | Adoption status |
|---|---|---|
| L01 | Cue Is Handle, Not Evidence | STAGED v1.0.3.1 |
| L02 | Source-Bound Mnemonic | STAGED v1.0.3.1 |
| L03 | Low Collision Before Activation | STAGED v1.0.3.1 |
| L04 | Portable Regex Only | STAGED v1.0.3.1 |
| L05 | Recall Payload Must Declare Stop Condition | STAGED v1.0.3.1 |
| L06 | Review Event Or It Did Not Stick | STAGED v1.0.3.1 |
| L07 | Body Hash Drift Quarantines Cue | STAGED v1.0.3.1 |
| L08 | Birth-Time Cue, Retrofit Marked | STAGED v1.0.3.1 |
| L09 | Agent-Readable Beats Clever | STAGED v1.0.3.1 |
| L10 | SRS Optimizes Retrieval, Not Truth | STAGED v1.0.3.1 |
| L11 | Creator Cannot Solely Certify Own Cue | STAGED v1.0.3.1 |
| L12 | Cue Failure Triggers Reformulation | STAGED v1.0.3.1 |

### sec6.5 - Packet / Review Mesh P01-P08

Cite-only per sec73.3. See operator source.md L302-310 "Packet / Review Mesh Recommendations" table. P01-P08 are review-flow recommendations for cue lifecycle - all STAGED for v1.0.3.1 implementation. None executed in this ship.

| P recommendation | Originating agent | Status |
|---|---|---|
| P01 Regexical Memory schema proposal | scribe | LANDED (this SPEC + schema) |
| P02 Cue birth-hook implementation | forge | STAGED v1.0.3.1 |
| P03 Portable regex/F9 validator | forge | LANDED (`f9_regex_quorum.py`) |
| P04 Collision scanner pilot | scout | STAGED v1.0.3.1 |
| P05 Recall rubric + SRS pilot | judge | LANDED-CONDITIONAL (rubric used; refinement STAGED) |
| P06 F10 receipt integration | warden | STAGED v1.0.3.1 (stub only) |
| P07 Drift guard | warden | STAGED v1.0.3.1 |
| P08 Doctrine promotion packet | curator | STAGED v1.0.3.1 |

---

## sec7 - Phase 2 VG04 pilot results (DOWNGRADED-VERBATIM)

### sec7.1 - Empirical scores

3 attempts via `general-purpose` subagents on cue `premortem weakest-assumption`. Source: `.claude/_logs/aep-v103-vg04-attempts.jsonl` (the agent initial rubric) + `aep-v103-vg04-warden-rescore.jsonl` (warden blind re-score) + `aep-v103-vg04-judge-tiebreaker.jsonl` (judge tiebreaker).

| Attempt | the agent score | Warden score | Judge score | Mean |
|---|---:|---:|---:|---:|
| vg04-001 | 4 | 3 | 3.5 | 3.500 |
| vg04-002 | 4 | 3 | 3.5 | 3.500 |
| vg04-003 | 4 | 3 | 3.0 | 3.333 |
| **Overall mean** | 4.00 | 3.00 | 3.333 | **3.444** |

3-reader mean = 3.444. PASS threshold = 4.0. **Verdict: HARD-CONDITIONAL**.

### sec7.2 - Reader divergence analysis

- **the agent scored optimistic (4.0 mean)**: counted persona-bound extensions to `failure_prevented` (checkbox-laundering, prompt-injection-filter, scope-creep) as reasonable additive coverage of the adversary persona's broader skill surface. Did not weight gold-standard items (b) `schema-valid-but-reliability-unsupported-promotion` and (c) `fabricated-or-unresolved-citation` as MUST-have load-bearing items.
- **Warden scored strict (3.0 mean)**: counted ANY load-bearing field miss as HARD per rubric definition. Gold-standard `failure_prevented` 3-item set was treated as the rubric anchor; missing 2 of 3 items qualified as a load-bearing miss regardless of additive coverage.
- **Judge tiebreaker (3.333 mean)**: positioned between the agent and warden. Critical calls:
  - **Call 1**: `packet_id` suffix `-agent` drift (emitted `aepkg:adversary` vs gold `aepkg:adversary-agent`) is **NON-load-bearing** because `owner_agent` field disambiguates routing unambiguously. Judge agreed with the agent on this call.
  - **Call 2**: `failure_prevented` missing items (b) + (c) IS load-bearing because they are anchored to `when_to_open_full_file` gating clauses in the gold record - they define when the cue is no longer sufficient and the agent MUST open the source.md. Missing both qualifies as ONE load-bearing field miss. Judge agreed with warden on this call.
  - Combined: 1 non-load-bearing miss (packet_id suffix) + 1 load-bearing miss (failure_prevented anchor) = HARD_PLUS (3.5) for vg04-001 + vg04-002; HARD (3.0) for vg04-003 which additionally drifted on mission framing.

### sec7.3 - Rubric definitional gap (judge finding)

The rubric inherited from operator source.md L271-280 does NOT specify a threshold for completeness on list-valued recall fields (e.g., `failure_prevented`, `when_to_open_full_file`, `distinguishers`). The rubric defines:
- Score 5 EXACT: all minimum_recall_fields correctly + stop_condition + no fabrication.
- Score 4 GOOD: one non-load-bearing omission + no fabrication + stop_condition.
- Score 3 HARD: correct rough identity but misses one load-bearing field OR opens file too late.

But it does NOT specify: what fraction of a list-valued field's items must overlap with gold for it to count as "present" vs "missing"? the agent applied a loose pass (any overlap + reasonable extensions = present). Warden + judge applied a strict pass (less than majority overlap = missing). The gap is real and structural - the rubric did not anticipate list-valued field partial-overlap scoring.

**STAGED for v1.0.3.1 rubric refinement**: add explicit threshold (e.g., "for list-valued recall fields, overlap with gold's items MUST be >= ceil(N_gold/2) where N_gold is the gold list length, else count as missing field per HARD criterion").

### sec7.4 - DOWNGRADE actions taken in this SPEC

Per Rollback A binding:

1. **sec3 cue-recall claim truth-tag**: `EXPERIMENTAL × CONTEXT-BOUND PATTERN` (DOWNGRADED from STRONGLY PLAUSIBLE).
2. **Adversary retrofit**: DRY-RUN to sandbox at `projects/v11-aep/pilots/regexical-memory-pilot/adversary-sandbox.aepkg/`, NOT canonical `.claude/agents/adversary.aepkg/`.
3. **Full 10-agent retrofit**: STAGED v1.0.3.1.
4. **Canonical-adversary retrofit**: STAGED v1.0.3.1 (after rubric refinement + 1 more VG04 pass clearing 4.0 mean).
5. **L01-L12 doctrine promotion**: ALL STAGED v1.0.3.1.
6. **Corpus migrator**: SKELETON-STUB only (`wave_053_corpus_migrate_v1_0_3.py` exits 2 with STAGED message).

### sec7.5 - sec73.6 NO-OPERATOR-REACTION-CALIBRATION binding

Per sec73.6, this SPEC is NOT shaped for anticipated operator reaction. The honest DOWNGRADED scope ships even though it is less impressive than full-vision delivery. Operator-spec sovereignty per sec69.5: operator's vision is honored verbatim where the verification gate clears, and is honestly disclosed-as-deferred where the gate does not clear. VG04 is the gate; it did not clear at PASS-threshold; v1.0.3 ships DOWNGRADED accordingly.

---

## sec8 - STAGED v1.0.3.1 backlog

The following items are STAGED for v1.0.3.1 release (post-pilot, post-rubric-refinement). Each item ships ONLY when its precondition gate clears.

### sec8.1 - Rubric refinement (PRECONDITION for all other v1.0.3.1 items)

- **Authoring**: judge ships VG04 rubric v2 at `projects/v11-aep/publish-ready/aep/spec/vg04_rubric_v2.md` with explicit list-valued field overlap thresholds.
- **Gate**: warden + adversary independent review; both PASS.

### sec8.2 - Canonical adversary retrofit (PRECONDITION: sec8.1 cleared + VG04 v2 rubric clears 4.0 mean on existing 3 attempts re-scored)

- **Authoring**: forge ships canonical-mode `wave_054_regexical_pilot_adversary_canonical.py` that writes to `.claude/agents/adversary.aepkg/data/claims.jsonl` + `ops/events.jsonl` (NOT sandbox).
- **Gate**: BC-V103-1 test passes against canonical-retrofitted adversary.aepkg + judge + warden cleanup verdicts.

### sec8.3 - 9-agent retrofit (PRECONDITION: sec8.2 cleared)

- **Authoring**: forge ships 9 wave scripts (one per non-adversary canonical agent: strategist + pathfinder + scout + judge + warden + scribe + curator + visual-judge + forge).
- **Gate**: VG04 v2 rubric clears 4.0 mean on each agent's pilot recall attempts. Each agent's pilot cue has independent warden + judge re-score per VG09.

### sec8.4 - Corpus migrator GA (PRECONDITION: sec8.3 cleared + 10 pilot retrofits in sample)

- **Authoring**: forge promotes `wave_053_corpus_migrate_v1_0_3.py` from SKELETON-STUB to GA (full body following `wave_044` pattern).
- **Gate**: sample run on 5 packets shows additive-only behavior (state_hash unchanged on non-regexical packets; state_hash changes ONLY when regexical-additive rows are present).

### sec8.5 - L01-L12 doctrine promotion (PRECONDITION: sec8.4 cleared + curator promotion audit clears)

- **Authoring**: curator ships 12 promotion proposals at `doctrine/_proposals/curator-<date>-rxmem-l01.html` through `l12.html`.
- **Gate**: each law candidate has >= 2 cited validation receipts + >= 1 falsifier shipped + scribe single-writer review per sec72.6.

### sec8.6 - Other v1.0.3.1 features (LOWER PRIORITY)

- FSRS-lite scheduler (currently SM2-lite bootstrap only).
- Schema `additionalProperties: false` tightening (currently allow-list audit only).
- F10 signed receipt integration (currently STAGED stub only).
- Corpus collision scanner (IQ05).
- Body-hash drift guard (IQ09).
- Retrieval CLI (IQ11).
- Cue birth hook (IQ02).
- Prompt-injection scan (R07).

---

## sec73.5 Phase 3+4+5 unified-forge receipt anchor

This SPEC.md body is one of the SIX artifacts produced in the single Phase 3+4+5 forge invocation per HV3 closure (binding sec69.4). The other five artifacts ship in the same invocation:

1. `projects/v11-aep/publish-ready/aep/scripts/validate_regexical_memory.py` (~200 LOC)
2. `projects/v11-aep/publish-ready/aep/scripts/f9_regex_quorum.py` (~250 LOC)
3. `projects/v11-aep/publish-ready/aep/scripts/wave_052_regexical_pilot_adversary.py` (~300 LOC, DRY-RUN per Rollback A)
4. `projects/v11-aep/publish-ready/aep/scripts/wave_053_corpus_migrate_v1_0_3.py` (~80 LOC SKELETON-STUB STAGED)
5. `projects/v11-aep/publish-ready/aep/tests/test_bc_v103_1_canonical_state_hash_unchanged.py` (~120 LOC HV1 closure)

HCRL receipt row 4 chains to row 3's `acff6e4a15de29fa7aa9b1319b684e72c19bdfee89a00f66a5fe80934a93db48` and captures: parse-check (markdown valid for SPEC.md, python syntax valid for 4 scripts, no JSON involved in this row), runtime-trace (byte counts + sha256 prefixes for all 6 artifacts), no-screen-fail (BC test PASS empirically + F9 quorum 9/9 or 6/6 + validator positive+negative paths), `evidence_bindings_size_bytes` per M6.

### sec73 composability summary

This SPEC and its 5 companion scripts compose with every doctrine slot listed in the header. Specific load-bearing compositions:
- sec73.2 OPERATOR-VERBATIM-SACRED: operator's source.md is cited per line range, never paraphrased.
- sec73.3 PRIOR-ART-INHERITANCE: IQ / R / VG / L / P inheritance rate target >= 95% (cite-only lines vs regenerated inventory lines).
- sec73.4 SINGLE-FORGE-FOR-PRODUCT-BUILDS: this single forge invocation produces all 6 artifacts; no sub-forge dispatch; no recursive forge re-entry.
- sec73.5 WARDEN-RECEIPTS-OR-HALT: every artifact ships with sha256 + byte count + parse-check captured in HCRL row 4.
- sec73.6 NO-OPERATOR-REACTION-CALIBRATION: this SPEC ships the honest DOWNGRADED scope without optimization for operator approval.

### sec70 surface mirror projections

Per sec70.1, this SPEC.md ships with 3 projections at minimum:
- **Chat surface**: forge's response to the agent includes the 1-screen summary (6 paths + byte counts + sha256 prefixes + BC test outcome + F9 quorum outcome + HCRL row 4 sha + 7 closure callouts).
- **Artifact surface**: this SPEC.md at `projects/v11-aep/publish-ready/aep/spec/AEP_v1_0_3_SPEC.md`.
- **Cowork surface**: HCRL receipt row 4 at `.claude/_logs/aep-v103-phase-receipts.jsonl` per sec70.2 canonical-source-Claude-Code-in-this-repo.

Decay falsifier per sec70.3: if `>=30` days elapse without progress on sec8 STAGED items, this SPEC enters decay-WARN; >=90 days enters decay-BLOCK and operator-review-required surfaces.

---

**End SPEC v1.0.3 DOWNGRADED ship.**
