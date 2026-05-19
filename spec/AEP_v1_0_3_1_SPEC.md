# AEP v1.0.3.1 SPEC - F14 RaterQuorumAttestation + A4 RubricScore Backport (Rubric Calibration)

**Status**: **LANDED 2026-05-18** under operator full-build authorization. Sister-spec to AEP_v1_0_3_SPEC.md. Implements the v1.0.3.1 BACKLOG item 1 ("Rubric calibration for list-valued recall fields") plus the HV-5 closure binding from `doctrine/_proposals/diana-2026-05-18-v11-legion-convergence-synthesis.md` sec7. ONE coherent product build per sec73.4.

**Predecessors**:
- AEP v0.8.0 STABLE (LANDED 2026-05-17, last frontier-break SPEC.md with F1-F8 primitives)
- AEP v1.0.0 / v1.0.1 / v1.0.2 (runtime-only F9 cross-substrate quorum + F10 signed in-toto ITE6)
- **AEP v1.0.3 LANDED-DOWNGRADED 2026-05-18** (RegexicalCue claim type + 6 regexical_memory_* events + BC-V103-1 + VG04 HARD-CONDITIONAL mean 3.44; predecessor of THIS spec)

**Authors**: operator (operator) + the agentic substrate (Claude Opus 4.7 1M-context, AEP project 10-agent legion: pathfinder + judge + warden + adversary + forge co-authored under sec73.4 single-forge-for-product-builds for this SPEC body).

**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).

**Profiles**:
- `aep:1.0.3.1/stable` (F14 RaterQuorumAttestation block + A4 RubricScore claim type ACTIVE; rubric_definitional_closure_set field present on every RubricScore claim)
- `aep:1.0.3.1/backport-compatible` (every v1.0.3 packet validates clean under v1.0.3.1 with F14 + A4 fields ABSENT; BC-V1031-1 baseline)
- `aep:1.0.3.1/promotion-gate` (RaterQuorumAttestation with independence_pass=true REQUIRED for any claim promotion to PROVEN/RELIABLE; v1.0.3 HV2 closure universalized)

**Composes with**:
- `doctrine/02-truth-tags.html` (Amendment A15 GOVERNANCE-RULE — score-bearing claims now MAY carry RubricScore attachment)
- `doctrine/11-cortex-v-protocol.html` sec3 (anti-collusion guard — read_path_excludes field hooks into PreToolUse deny)
- `doctrine/41-hash-chained-receipt-ledger.html` (HCRL chain row 8 binds this SPEC and 4 companion artifacts)
- `doctrine/50-epistemic-hygiene-meta-law.html` (Law-3 multi-lens independence — F14 universalizes the lens-count gate)
- `doctrine/52-hybrid-prose-aep-bridge.html` (Hybrid Bridge Protocol — this SPEC IS the prose-canonical; companion .aepkg/ projection deferred to v1.0.3.2)
- `doctrine/60-pre-coding-lesson-review-discipline.html` (lesson scan performed before code emission this turn)
- `doctrine/69-verification-law-and-operator-spec-sovereignty.html` (all 9 sub-laws; sec69.4 non-rescindability binding; sec69.5 operator-verbatim-sacred binding on the operator directive below)
- `doctrine/70-surface-mirror-discipline.html` (chat + artifact + cowork projections this SPEC ships)
- `doctrine/71-operator-sustainability.html` (closes within 4h continuous-autonomy cap)
- `doctrine/72-canonical-order-of-operations.html` (firing-order: this is the forge phase per sec72.6)
- `doctrine/73-external-claude-receipt-laws.html` (all 6 sub-laws binding; sec73.4 enforced by this single forge invocation; sec73.6 enforced by the honest disconfirmer outcome in sec7)
- AEP v1.0.3 SPEC sec1-sec8 (cite-only per sec73.3 prior-art-inheritance; NOT regenerated below)
- `doctrine/_proposals/diana-2026-05-18-v11-legion-convergence-synthesis.md` (sec7 adversary closure HV-5 mandates this backport; this SPEC IS the closure)

**Cites (sec73.3 prior-art-inheritance, NOT regenerated)**:
- `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/source.md` (operator rubric definition L272-281; the definitional gap closed by this spec)
- `research/sources/operator-2026-05-18-regexical-memory-aep-v102.aepkg/assets/regexical_memory_example_adversary.jsonl` (operator gold standard for the empirical disconfirmer)
- `.claude/_logs/aep-v103-vg04-attempts.jsonl` (3 historical attempts; the agent means)
- `.claude/_logs/aep-v103-vg04-warden-rescore.jsonl` (warden strict re-score)
- `.claude/_logs/aep-v103-vg04-judge-tiebreaker.jsonl` (judge tiebreaker, source of the load-bearing-vs-decorative call)
- `.claude/_logs/aep-v0103-1-vg04-retro-rescore.jsonl` (THIS spec's empirical disconfirmer output; sec7)

**Operator directive (sec73.2 sacred, verbatim)**:
> "okay great now implement it all, and at the end, measure every possible % or variable that each thing as an aep whole provides the agentic framework if everything is not perfect, then make it perfect for v1.1 do whatever you have to do i honestly don't see how any of you have limits anymore - just figure it out"

---

## sec1 - Why v1.0.3.1 exists

### sec1.1 - The HARD-CONDITIONAL outcome that triggered this backport

AEP v1.0.3 (LANDED-DOWNGRADED 2026-05-18) shipped six artifacts under VG04 verdict `HARD-CONDITIONAL`. The empirical floor: 3 blind-recall attempts on cue `premortem weakest-assumption` produced these rater means:

| Rater | Mean | Method |
|---|---:|---|
| the agent | 4.00 | Generous: counted persona-bound extensions to `failure_prevented[]` as additive coverage |
| warden | 3.00 | Strict: load-bearing-only-overlap; any item-set deviation counts as missing |
| judge | 3.33 | Tiebreaker: between the agent and warden; preserved warden's "load-bearing miss" call but agreed with the agent on packet_id suffix being non-load-bearing |
| **Overall** | **3.44** | Below the 4.0 PASS threshold; above the 3.0 ABORT floor |

The inter-rater max-pairwise-delta was **1.0** — well above the 0.5 independence threshold per HV2 closure. The judge tiebreaker root cause finding (preserved verbatim in v1.0.3 SPEC sec7.3): the operator-supplied rubric (`source.md` L271-280) does NOT specify a threshold for completeness on list-valued recall fields. Three raters applied three different rules and got three different scores. **The rubric was the bug.**

### sec1.2 - The HV-5 closure binding

The v1.1 legion-convergence synthesis (`doctrine/_proposals/diana-2026-05-18-v11-legion-convergence-synthesis.md`) ran adversary as the final-stop gate before v1.1 forge engagement. Adversary returned 4 HIGH-VETOs + 2 MEDIUM + 1 anti-convergence finding. **HV-5 was the binding closure**:

> Rubric-calibration (rater_quorum + rubric_score_claim) is v1.0.3.1 BACKLOG item 1 (already named). Delaying to v1.1 accumulates downstream rework on every cue activation. **Resolution**: F14 + A4 BACKPORT to v1.0.3.1. Net F-tier drops to 6.

Per sec69.4, adversary HIGH-VETO closures are non-rescindable. This SPEC IS the HV-5 closure.

### sec1.3 - sibling-132 lesson context

The v1.0.3 lesson `doctrine/lessons/2026-05-18-aep-v103-regexical-memory-shipped.html` (sibling-132) documented the HARD-CONDITIONAL outcome honestly. The lesson's falsifier-clause states:

> If v1.0.3.1 rubric calibration does NOT close the 0.5 inter-rater gate on the SAME 3 attempts that produced mean 3.44, then v1.0.3 HARD-CONDITIONAL hardens to FAIL, canonical adversary retrofit STAGED indefinitely, L01-L12 promotion stays deferred, and Regexical Memory's product viability requires architectural rework.

This SPEC's sec7 IS the empirical test of that falsifier. The result is captured at `.claude/_logs/aep-v0103-1-vg04-retro-rescore.jsonl`. **STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN** (Axis-A: PLAUSIBLE; Axis-B: GO for the F14+A4 mechanism, EXPERIMENT for the underlying RegexicalCue product-viability question).

---

## sec2 - BC-V1031-1 backward-compatibility clause

### sec2.1 - The invariant

**BC-V1031-1**: For any AEP packet, validating under `aep:1.0.3.1/backport-compatible` with the F14 RaterQuorumAttestation block ABSENT and zero `type: RubricScore` claims in `data/claims.jsonl` MUST produce results byte-identical to validating the same packet under `aep:1.0.3/stable`. The new claim type and the new top-level block are STRICTLY ADDITIVE.

### sec2.2 - What BC-V1031-1 does NOT claim

- Does NOT claim manifest sha256 invariance. The `aepkg.json.extensions` field MAY carry a v1.0.3.1 marker (advisory; not load-bearing).
- Does NOT claim `state_hash` invariance when RubricScore claims ARE present. RubricScore is in `data/claims.jsonl` which IS in the state_hash formula; when present, state_hash legitimately changes.
- Does NOT claim that existing v1.0.3 RegexicalCue claims auto-upgrade with RubricScore attachments. Upgrade is OPT-IN per claim author.

### sec2.3 - Empirical falsifier

The existing v1.0.3 BC test at `projects/v11-aep/publish-ready/aep/tests/test_bc_v103_1_canonical_state_hash_unchanged.py` continues to pass under v1.0.3.1 unchanged. No new BC test is required (the v1.0.3 test already covers the additive-only contract; adding new claim types in v1.0.3.1 follows the same pattern).

### sec2.4 - Schema-additive-only discipline (forge personal cite)

This SPEC and its 2 new schemas + 2 new scripts add fields and claim types to the existing v1.0.3 vocab. NO existing v1.0.3 field is renamed or removed. Per the forge personal compendium's "Schema-additive-only" invariant, RENAME/REMOVE requires curator approval + migration note; nothing here triggers that gate.

---

## sec3 - F14 RaterQuorumAttestation schema

### sec3.1 - Purpose

F14 universalizes the v1.0.3 HV2 closure (warden re-score + judge tiebreaker on cross-reader mean-delta > 0.5) as a schema-enforced invariant. Every score-bearing field that bears on PROMOTION (truth-tag upgrade, doctrine promotion, pilot-to-LANDED transition) MUST carry a RaterQuorumAttestation with `independence_pass=true`. Validator REJECTS promotion to `PROVEN/RELIABLE` if the attestation is absent or independence fails.

This closes the cargo-cult-agreement attack class + the self-certification attack class simultaneously.

### sec3.2 - Schema location + integrity

The JSON Schema (draft 2020-12) at `projects/v11-aep/publish-ready/aep/schemas/rater_quorum_attestation.schema.json` ships with this SPEC.

**$id**: `aep:rater-quorum-attestation:0.1`
**title**: `AEP Rater Quorum Attestation`
**type**: object (top-level)

### sec3.3 - Required fields

Per the schema's `required` array:
`type, schema_version, id, bound_to_artifact_sha256, raters, agreement_metric, agreement_score, independence_threshold, independence_pass`

### sec3.4 - The N>=2 raters invariant

`raters[]` has `minItems: 2`. Validator additionally enforces:
1. All `session_id` values MUST be distinct (anti-same-session-self-attestation per sec73.5 independence).
2. All `principal_id` values MUST be distinct (anti-self-attestation; one principal cannot rate twice).
3. If `prior_exposure_hash` values are shared across raters, validator emits `RQA_ANCHORING_RISK` warning (raters peeked at the same prior reads; defeats independence per sec50 Law-3).
4. If `roles[]` collapse to a single role, validator emits `RQA_ROLE_DIVERSITY` warning (recommended N>=2 distinct roles for cross-lens independence).

### sec3.5 - Agreement metrics

The `agreement_metric` enum supports three computation modes:

| Metric | When to use | Threshold semantics |
|---|---|---|
| `cohens_kappa` | N=2 raters, categorical/ordinal scores | `agreement_score >= independence_threshold` PASSES; default threshold 0.6 |
| `krippendorff_alpha` | N>=3 raters, ordinal or interval scores | `agreement_score >= independence_threshold` PASSES; default threshold 0.6 |
| `simple_mean_delta` | N=2-3 raters, continuous 0-5 scores (today's VG04 default per HV2) | `agreement_score <= independence_threshold` PASSES; default threshold 0.5 |

The validator reproduces `independence_pass` from `agreement_metric` + `agreement_score` + `independence_threshold` and ERRORS if the declared `independence_pass` disagrees with the computation.

### sec3.6 - Verdict enum

`verdict` ENUM maps mean and independence to a 4-way verdict:
- `PASS`: `mean_score >= pass_threshold` AND `independence_pass = true`
- `HARD_CONDITIONAL`: `abort_floor < mean_score < pass_threshold` (the v1.0.3 case)
- `FAIL`: `independence_pass = false` regardless of mean
- `ABORT`: `mean_score <= abort_floor` regardless of independence (sec7 retro-rescore case)

Default thresholds: `pass_threshold: 4.0`, `abort_floor: 3.0`. Both inherited from VG04 rubric (operator source.md L274-280).

### sec3.7 - disagreement_decomposition[]

The `disagreement_decomposition[]` array decomposes rater divergence by dimension. Each entry binds a `dimension_id` (matching a RubricScore claim's `dimension_id`) + max_delta + drivers[]. Curator reads this when proposing rubric refinements. This is the structured form of the v1.0.3 judge tiebreaker's narrative "critical_call_1 + critical_call_2" analysis.

### sec3.8 - Truth-tag for sec3

F14 mechanism ships at:
- sec02 tag: `STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN`
- V11-AEP Axis A: `STRONGLY_PLAUSIBLE`
- V11-AEP Axis B: `GO`

Promotion to `PROVEN/RELIABLE` requires sec73.5 warden receipt of >= 5 independent applications of F14 to score-bearing fields outside the VG04 domain (e.g., promotion gates, pilot-to-LANDED transitions, doctrine-tier promotions).

---

## sec4 - A4 RubricScore claim type

### sec4.1 - Purpose

A4 promotes rubric scores from prose-buried-in-rationale to first-class structured claims. Every rubric verdict's per-dimension score becomes a `RubricScore` claim row in `data/claims.jsonl`. Cross-rater queries (e.g., "show all dimensions where the agent and warden diverged by >0.5") become O(grep) rather than O(narrative-extraction).

A4 is the schema partner of F14: F14 attests the multi-rater bundle; A4 carries the individual scores. The two compose mechanically.

### sec4.2 - Schema location

`projects/v11-aep/publish-ready/aep/schemas/rubric_score_claim.schema.json`
**$id**: `aep:rubric-score-claim:0.1`

### sec4.3 - The RubricScore claim type

`RubricScore` is added to the v0.5+ `claim.type` value vocab. Existing `type` values (e.g., `RegexicalCue`, `Claim`, `Assertion`) remain unchanged. The new type follows the v0.3+ claim-row pattern (id + schema_version + binding fields + content fields).

### sec4.4 - Required fields

Per the schema's `required` array:
`type, schema_version, id, rubric_id, dimension_id, dimension_label, score, score_scale, bound_to_artifact_sha256, rater_principal_id`

### sec4.5 - The score_scale enum

| Scale | Range | When |
|---|---|---|
| `0_to_5` | 0.0 - 5.0 | VG04 default (operator source.md L274-280) |
| `0_to_10` | 0.0 - 10.0 | Verbose rubrics |
| `normalized_0_to_1` | 0.0 - 1.0 | Probability-like / κ-like scores |

Validator enforces range conformance per declared scale. Cross-scale comparison requires projection (e.g., `0_to_10 / 2 -> 0_to_5`).

### sec4.6 - rationale binding

Two paths:
1. `rationale_sha256` only: rationale lives elsewhere (referenced by hash; audit-replayable).
2. `rationale_sha256` + `rationale_text` both present: validator computes `sha256(rationale_text)` and ERRORS if mismatch.

Either path satisfies sec73.5 warden-receipts-or-halt (the rationale is auditable).

### sec4.7 - Truth-tag for sec4

A4 mechanism ships at:
- sec02 tag: `STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN`
- V11-AEP Axis A: `STRONGLY_PLAUSIBLE`
- V11-AEP Axis B: `GO`

Promotion to `PROVEN/RELIABLE` requires sec73.5 warden receipt of >= 20 RubricScore claims across >= 3 distinct rubric_id values.

---

## sec5 - rubric_definitional_closure_set field

### sec5.1 - Purpose (THE load-bearing addition)

`rubric_definitional_closure_set[]` is the load-bearing addition that closes the v1.0.3 VG04 root cause. Per the judge tiebreaker finding (v1.0.3 SPEC sec7.3): the operator rubric (L271-280) does NOT specify a threshold for completeness on list-valued recall fields. Three raters applied three different rules. The closure_set makes the rubric MACHINE-CHECKABLE.

Every `RubricScore` claim MAY carry a `rubric_definitional_closure_set[]` listing per-dimension resolution rules. When a `RubricScore` claim's `dimension_id` has an entry in its `closure_set`, the rubric is no longer rater-discretion for that dimension — it's a deterministic computation.

### sec5.2 - Closure-set entry shape

```json
{
  "dimension_id": "failure_prevented_overlap",
  "definitional_resolution": "Item is LOAD-BEARING if it names a specific lesson_id, doctrine sec-number, or attack-class anchored to gold's when_to_open_full_file gating clauses. Score gold-overlap on LOAD-BEARING items only.",
  "partial_credit_formula": "partial_credit = clamp(overlap_count_load_bearing / gold_load_bearing_count, 0, 1); final_score = partial_credit * 4.0 + (presence_of_stop_condition * 1.0)",
  "list_overlap_threshold": 0.5,
  "load_bearing_classifier": "item is load-bearing if it matches one of: (a) names a specific failure-mode taxonomy term anchored in gold's when_to_open_full_file, (b) names a specific lesson_id or doctrine sec-number, (c) anchors to a citation-integrity / schema-reliability / source-grounding attack-class.",
  "applies_to_scale": "0_to_5",
  "version": "1.0.3.1.a"
}
```

### sec5.3 - The list-overlap threshold

For list-valued recall fields (e.g., `failure_prevented[]`, `when_to_open_full_file[]`, `distinguishers[]`), the `list_overlap_threshold` answers the v1.0.3 unanswered question: what fraction of gold items must overlap for the field to count as present?

Default: `0.5` (majority overlap). This is the threshold the v1.0.3 judge tiebreaker implicitly applied when scoring the failure_prevented dimension.

### sec5.4 - The load_bearing_classifier

For list-valued fields where some items are load-bearing and some decorative, the `load_bearing_classifier` is the decision rule that distinguishes them. Without this rule, additive persona-bound extensions (e.g., adversary's "checkbox-laundering" / "scope-creep" / "prompt-injection-filter") inflate scores by counting toward overlap even though they don't anchor to gold's attack-classes.

The v1.0.3.1 closure_set for `failure_prevented_overlap` specifies: anchor-keyword match on attack-class is the load-bearing test. The retro-rescore script (`wave_054_vg04_retro_validate.py`) implements this mechanically.

### sec5.5 - The partial_credit_formula

The `partial_credit_formula` is a string expression of the computation. Validator REPRODUCES the computation given `computed_inputs` and ERRORS via `RUBRICSCORE_FORMULA_DRIFT` warning if `|declared_score - computed_score_from_formula| > 0.25`.

This makes rubric scoring AUDIT-REPLAYABLE: any future reader can re-run the formula against the captured inputs and verify the score. No prose archaeology required.

### sec5.6 - Truth-tag for sec5

`rubric_definitional_closure_set` mechanism ships at:
- sec02 tag: `EXPERIMENTAL × CONTEXT-BOUND PATTERN`
- V11-AEP Axis A: `PLAUSIBLE`
- V11-AEP Axis B: `EXPERIMENT`

Promotion to `STRONGLY PLAUSIBLE` requires:
1. >= 3 distinct rubrics (not just VG04) using the closure_set field
2. >= 1 cross-rater convergence demonstration (max-delta drops by >= 0.4 after closure_set applied)
3. >= 1 sec7-style retroactive empirical test on historical data

Today's sec7 retroactive test satisfies (3) for the failure_prevented_overlap dimension. (1) and (2) require subsequent applications (STAGED).

---

## sec6 - Backport mechanics

### sec6.1 - How v1.0.3 packets remain valid

Every existing v1.0.3 packet (the 1112+ corpus + the 5 v1.0.3-shipped artifacts) remains byte-identical under v1.0.3.1 validation. The v1.0.3.1 validator (`validate_v1_0_3_1.py`) handles the new artifact shapes; the existing v1.0.3 validator (`validate_regexical_memory.py`) continues to handle RegexicalCue claims unchanged.

### sec6.2 - How v1.0.3.1 packets are constructed

A v1.0.3.1 packet is a v1.0.3 packet plus optionally:
1. One or more `type: RubricScore` claims in `data/claims.jsonl`
2. A RaterQuorumAttestation block in `data/claims.jsonl` (or a sidecar at `data/attestations.jsonl` — TBD per v1.0.3.2 if claims.jsonl row-class proliferation requires it)
3. A manifest extension at `aepkg.json.extensions.aep_1_0_3_1_rubric_calibration` carrying:
   - `rubric_ids: [...]`
   - `attestation_count: N`
   - `last_attestation_id: "rqa:..."`
   - `independence_pass_count: N`
   - `verdict_distribution: {PASS: N, HARD_CONDITIONAL: N, FAIL: N, ABORT: N}`

(3) is advisory; canonical authority is the `data/claims.jsonl` rows.

### sec6.3 - No corpus migration required

Unlike v1.0.3 -> v1.0.3.2 (corpus migrator GA), the v1.0.3 -> v1.0.3.1 transition requires NO corpus migration. v1.0.3.1 is OPT-IN per claim author. Existing packets stay v1.0.3-shaped until an author chooses to attach RubricScore + RaterQuorumAttestation.

The promotion gate (sec3.1) is the forcing function: any claim that wants to upgrade to `PROVEN/RELIABLE` after this SPEC ships MUST carry F14 + A4 attestations.

### sec6.4 - F14 + A4 unlock retroactive auditability

After this SPEC ships, every v1.0.3 score-bearing artifact can be retroactively wrapped in F14 + A4 attestations by emitting the claims into a v1.0.3.1-shaped packet. The original artifact is unchanged; the attestation is additive. The v1.0.3 VG04 attempts are the first worked example (sec7).

---

## sec7 - Retroactive VG04 re-validation (EMPIRICAL DISCONFIRMER)

### sec7.1 - The test procedure

`projects/v11-aep/publish-ready/aep/scripts/wave_054_vg04_retro_validate.py` implements the empirical disconfirmer cited in the operator brief. Procedure:

1. Read 3 historical VG04 attempts from `.claude/_logs/aep-v103-vg04-attempts.jsonl`.
2. Read warden re-score + judge tiebreaker from companion JSONLs.
3. Read operator gold standard from `regexical_memory_example_adversary.jsonl`.
4. Apply v1.0.3.1 `rubric_definitional_closure_set` (specifically the `failure_prevented_overlap` dimension with the load_bearing_classifier from sec5.4).
5. Re-score each attempt under the closure_set mechanically.
6. Compute new mean + new max-pairwise-delta + closure_status.
7. Emit results to `.claude/_logs/aep-v0103-1-vg04-retro-rescore.jsonl`.

### sec7.2 - The mechanical closure

Per the closure_set, the `failure_prevented[]` field is scored by:
- **Gold load-bearing items**: 3 items (weak-assumption, schema-reliability-promotion, citation-integrity)
- **Load-bearing classifier**: keyword-anchor match on attack-class
- **Partial credit formula**: `partial_credit = clamp(overlap_count_load_bearing / 3, 0, 1); final_score = partial_credit * 4.0 + (stop_condition_present * 1.0)`

For each of the 3 historical attempts:
- **Emitted failure_prevented items**: 4-5 items each, all variations on adversary persona-bound extensions
- **Load-bearing overlap with gold**: ALL 3 attempts matched ONLY 1 of 3 gold items (the weak-assumption attack-class). Schema-reliability + citation-integrity were ABSENT from every emitted recall_payload.

Mechanical scoring:
- `partial_credit = 1/3 = 0.333`
- `final_score = 0.333 * 4.0 + 1.0 = 2.333`

### sec7.3 - The result (sec73.6 honest disconfirmer)

| Metric | Original (v1.0.3) | v1.0.3.1 retro |
|---|---:|---:|
| the agent mean | 4.00 | 2.33 |
| warden mean | 3.00 | 2.33 |
| judge mean | 3.33 | 2.33 |
| Overall mean | 3.44 | 2.33 |
| Max pairwise delta | 1.00 | 0.00 |
| Independence verdict | FAIL | PASS |
| Quality verdict | HARD_CONDITIONAL | ABORT (below 3.0 floor) |

**Closure status on the HV-5 question (rater independence): PASS.** F14 + A4 + closure_set mechanically converge raters to identical scores; max-pairwise-delta drops from 1.0 to 0.0; the 0.5 independence threshold is cleared by construction.

**Quality verdict: ABORT.** The new unified mean is 2.33, below the 3.0 ABORT floor. This is the HONEST disconfirmer outcome. the agent's generous 4.0 mean was masking that all 3 attempts only matched 1 of 3 gold load-bearing items on the failure_prevented dimension.

### sec7.4 - Two interpretations (sec73.6 NO-OPERATOR-REACTION-CALIBRATION)

The empirical result splits into two readings, both honest:

**Reading 1 (favorable for F14+A4)**: The mechanism IS THE CLOSURE. F14+A4 mechanically remove rater divergence; the v1.0.3 HV-5 closure is mechanically satisfied. The fact that the unified score is ABORT-tier reveals a PROPERTY OF THE UNDERLYING RECALL ATTEMPTS, not a failure of F14+A4. F14+A4 are working correctly — they expose that the recall quality was lower than the agent's generous scoring suggested.

**Reading 2 (unfavorable for v1.0.3 RegexicalCue product viability)**: The 3 attempts genuinely failed the strict rubric. The HARD_CONDITIONAL was masking ABORT-tier performance. RegexicalCue's product viability requires either (a) better cue design (the cue `premortem weakest-assumption` may be under-specified — the agents recalled the persona's GENERAL attack repertoire instead of the gold's SPECIFIC attack-class anchors), or (b) operator-source rubric realignment (perhaps the gold's 3 items are over-specific and the persona's broader attack repertoire IS adequate).

Per sec73.6, both readings ship UNSHAPED. Operator decides which interpretation is load-bearing for v1.1 RegexicalCue product direction. The mechanism shipped here is independent of that question.

### sec7.5 - What the closure DOES and DOES NOT prove

**DOES prove**:
- F14 RaterQuorumAttestation block is implementable as a stdlib-only validator (validate_v1_0_3_1.py)
- A4 RubricScore claim type is implementable as a stdlib-only validator (validate_v1_0_3_1.py)
- `rubric_definitional_closure_set` mechanically converges rater scores when applied to the same artifact
- The v1.0.3 HV-5 closure question (rater independence) is mechanically satisfiable

**DOES NOT prove**:
- That every future rubric can be machine-closed via a closure_set (only failure_prevented_overlap was tested)
- That the closure_set's load_bearing_classifier rules will generalize to other rubrics
- That RegexicalCue cue-recall quality is independent of cue design (sec7.4 reading 2)
- That the new lower mean (2.33) reflects "true" recall quality vs an over-strict gold standard

These are STAGED for v1.0.3.2+ empirical work.

### sec7.6 - HV-5 closure status

HV-5 demanded: "F14 + A4 BACKPORT to v1.0.3.1." This SPEC + 2 schemas + 2 scripts BACKPORT both. Status: **HV-5 CLOSED**.

The further question raised by sec7.4 reading 2 (RegexicalCue product viability under strict rubric) is a NEW finding, not part of HV-5. Captured as STAGED v1.0.3.2 / v1.1.0 backlog item: "RegexicalCue product viability under strict rubric — investigate cue-design vs gold-standard tension."

---

## sec8 - Composes_with summary

This SPEC composes with:

### v0.8 F1-F8 frontier-break primitives
All 8 v0.8 primitives (canonical-content + self-falsifying-tests + PSC + ITE6 receipts + F1-F4 + F5-F8) remain unchanged. v1.0.3.1 is additive.

### v1.0.x F9 + F10
F9 (cross-substrate quorum) is unchanged. F10 (signed in-toto ITE6 receipts) is unchanged. When a RubricScore is signed via F10, the signature attests the score's binding integrity.

### v1.0.3 RegexicalCue + 6 events + BC-V103-1
Unchanged. v1.0.3.1 adds RubricScore claims that MAY bind to RegexicalCue recall_payload sha256 hashes (forming the "rubric attests the cue's recall" pattern).

### v1.1 (forthcoming)
v1.1 was originally going to include F14 + A4 in its 8-primitive F-tier. Per HV-5 closure, F14 + A4 BACKPORT to v1.0.3.1 (this SPEC). v1.1's net F-tier drops to 6 (F12 + F13 + F15 + F16 + F17 + F18). v1.1 forge engagement proceeds AFTER:
1. This SPEC LANDED (status: LANDED 2026-05-18)
2. Adversary HV-1 redaction-replay legion runs (separate dispatch)
3. Operator decision on v1.0.3.2 / v1.1 boundary per legion-convergence sec8

### Doctrine slots binding this SPEC
- sec02 truth-tags: F14 + A4 + closure_set ship truth-tagged
- sec11 cortex-v anti-collusion: read_path_excludes field hooks into anti-collusion guard
- sec41 HCRL: this SPEC's row 8 in `aep-v103-phase-receipts.jsonl` chains cleanly from row 7
- sec50 EH Law-3: F14 universalizes the multi-lens independence gate
- sec69.4: HV-5 closure is non-rescindable; this SPEC IS that closure
- sec69.5: operator directive preserved verbatim in header
- sec70.1: chat + artifact + cowork projections shipped
- sec71: closes within 4h cap
- sec72.6: forge phase; single forge per sec73.4
- sec73 all 6 sub-laws: each sub-law explicitly honored in this build

---

## sec9 - Acceptance criteria for this SPEC ship

Per sec03 validation gates:

| Gate | Method | Status |
|---|---|---|
| G1 - SPEC.md valid markdown | This file parses; reviewer can read it | PASS (manual + automated parse) |
| G2 - F14 schema valid JSON Schema draft 2020-12 | `python -m json.tool` on the schema | PASS |
| G3 - A4 schema valid JSON Schema draft 2020-12 | `python -m json.tool` on the schema | PASS |
| G4 - validate_v1_0_3_1.py positive path exit 0 | Sample valid RQA + RubricScore | PASS (verified at build time) |
| G5 - validate_v1_0_3_1.py negative path exit 1 | Sample invalid RQA (duplicate session_id) | PASS (verified at build time) |
| G6 - wave_054_vg04_retro_validate.py runs to completion | Empirical disconfirmer | PASS (writes 5 rows to retro-rescore JSONL) |
| G7 - sec7 retro-result honest per sec73.6 | NO-OPERATOR-REACTION-CALIBRATION | PASS (PASS-on-independence + ABORT-on-quality both shipped) |
| G8 - HCRL row 8 chains from row 7 | `prev_receipt_hash` matches row 7 sha256 | PASS (row 7 sha: c6aff1442f8d5833ef898cb0623a94631bdc1871e701c1094ec3d6938218b9c4) |
| G9 - Composes_with all listed doctrine slots | Manual audit | PASS (header) |
| G10 - sec73.4 single-forge ONE-invocation | Single forge produces all 5 artifacts | PASS |

---

## sec10 - STAGED v1.0.3.2 / v1.1.0 backlog (post-this-ship)

1. **RegexicalCue product viability investigation** (sec7.4 reading 2): cue-design vs gold-standard tension. Owner: judge + scribe. Cheapest disconfirmer: re-run VG04 with the cue `premortem weakest-assumption citation-integrity schema-reliability` (more explicit gold-anchor keywords). If recall matches gold, the v1.0.3 cue was under-specified, not the gold over-specified.
2. **Closure_set across other rubrics**: emit closure_set entries for at least 2 other rubrics (e.g., visual-judge dimension rubric, doctrine-promotion rubric). Owner: judge + curator.
3. **Manifest extension finalization**: lock the `extensions.aep_1_0_3_1_rubric_calibration` field shape after >= 5 packets carry it. Owner: forge + warden.
4. **PROVEN/RELIABLE promotion gate hook**: PreToolUse hook on `Edit|Write|MultiEdit` to canonical doctrine files that demands F14 attestation when a `PROVEN/RELIABLE` tag is being applied. Owner: warden.
5. **Cross-rubric κ aggregation**: aggregate per-dimension Cohen's κ across rubrics into a single quality metric per agent's scoring corpus. Owner: judge + scribe.

---

**End SPEC v1.0.3.1 LANDED ship.**
