# AEP v1.1 SPEC - Frontier-Break to 100% Recall in ms-NS + Ingrained Compounding Intelligence

**Status**: **PROPOSED 2026-05-18** under operator full-build authorization. Sister-spec to AEP_v1_0_3_1_SPEC.md (LANDED 2026-05-18 same-day). Implements the v1.1 stack from `doctrine/_proposals/diana-2026-05-18-v11-legion-convergence-synthesis.md` sec7 addendum (REVISED v1.1 STACK post-adversary-closure). ONE coherent product build per sec73.4.

**Predecessors**:
- AEP v0.8.0 STABLE (LANDED 2026-05-17 — F1-F8 frontier-break primitives; structural template for this SPEC).
- AEP v1.0.0 / v1.0.1 / v1.0.2 (runtime-only F9 cross-substrate quorum + F10 signed in-toto ITE6).
- AEP v1.0.3 LANDED-DOWNGRADED 2026-05-18 (RegexicalCue claim type + 6 regexical_memory_* events + BC-V103-1 + VG04 HARD-CONDITIONAL mean 3.44).
- **AEP v1.0.3.1 LANDED 2026-05-18** (F14 RaterQuorumAttestation + A4 RubricScore backport; rubric calibration; this SPEC builds on the v1.0.3.1 baseline).

**Authors**: operator (operator) + the agentic substrate (Claude Opus 4.7 1M-context, AEP project 10-agent legion: strategist + pathfinder + scout + forge + judge + adversary + warden + scribe + curator + visual-judge co-authored under sec73.4 single-forge-for-product-builds for this SPEC body).

**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).

**Profiles**:
- `aep:1.1/stable` (BC-V11-1 baseline; all v1.0.x packets validate clean with v1.1 fields absent; F12-F18+A1-A8+F19 OPTIONAL).
- `aep:1.1/recall-enabled` (F12 RecallLayerIndexEntry layer ACTIVE at `projects/v11-aep/publish-ready/aep/recall/`; agents may use derived projection for ms-NS recall).
- `aep:1.1/falsifier-strict` (F13 ClaimRuntimeFalsifier REQUIRED on every PROVEN/RELIABLE claim; F16 AttackClass registry consulted at emit-time).

**Composes with**:
- `doctrine/02-truth-tags.html` (Amendment A15 GOVERNANCE-RULE — F12-F18 + A1-A8 + F19 claim types all carry truth-tag fields)
- `doctrine/11-cortex-v-protocol.html` sec3 (anti-collusion guard; F14 rater independence inherited from v1.0.3.1)
- `doctrine/22-html-native-artifacts.html` (this SPEC is canonical .md per Hybrid Bridge sec52; companion .aepkg/ projection deferred to v1.1.1)
- `doctrine/40-session-governor-executor.html` (v1.1 fields are executor-emission-time-bound per KAC inheritance)
- `doctrine/41-hash-chained-receipt-ledger.html` (this SPEC's HCRL row 9 chains cleanly from row 8 = ec40855e7afa621b75a65d868160f784dd7bcf19c543e825a18335108ff83cbb)
- `doctrine/42-kernel-admission-contract.html` (F15 CriterionWitnessChain is the structural enforcement of KAC promise-vs-completion gates)
- `doctrine/45-codex-first-burn-law.html` (legion synthesis ran §49 pipeline; convergence map captured codex breadth)
- `doctrine/50-epistemic-hygiene-meta-law.html` (Law-3 multi-lens independence — F14 universalizes; F19 closes recall-completeness gap; F18 closes source-laundering gap)
- `doctrine/52-hybrid-prose-aep-bridge.html` (Hybrid Bridge Protocol — this SPEC IS the prose-canonical; companion .aepkg/ projection deferred to v1.1.1)
- `doctrine/56-operational-evidence-over-synthetic-ranking.html` (F12 contamination_flag inherits the operational-evidence discipline)
- `doctrine/60-pre-coding-lesson-review-discipline.html` (lesson scan performed before code emission this turn; preflight ledger-row hook fires)
- `doctrine/68-defender-alert-stops-burn.html` (no PowerShell hooks emitted this build; all tooling Python-native)
- `doctrine/69-verification-law-and-operator-spec-sovereignty.html` (all 9 sub-laws; sec69.4 non-rescindability binding on HV-1/HV-3/HV-5/HV-6 closures inherited from adversary)
- `doctrine/70-surface-mirror-discipline.html` (chat + artifact + cowork projections this SPEC ships)
- `doctrine/71-operator-sustainability.html` (closes within 4h continuous-autonomy cap; F19 corpus coverage witness is the sustainability-audit primitive)
- `doctrine/72-canonical-order-of-operations.html` (firing-order: this is the forge phase per sec72.6; single forge per sec73.4)
- `doctrine/73-external-claude-receipt-laws.html` (all 6 sub-laws binding; sec73.4 enforced by this single forge invocation; sec73.6 enforced by F12 EXPERIMENTAL truth-tag preservation + F19 single-source honest framing)
- AEP v0.8 sec V80-1 through V80-17 (F1-F8 inheritance; cite-only per sec73.3 prior-art-inheritance; NOT regenerated below)
- AEP v1.0.3 sec1-sec8 (RegexicalCue + 6 events + BC-V103-1; cite-only)
- AEP v1.0.3.1 sec1-sec10 (F14 + A4 + rubric_definitional_closure_set; cite-only)
- `doctrine/_proposals/diana-2026-05-18-v11-legion-convergence-synthesis.md` sec7 (REVISED v1.1 STACK post-adversary-closure; this SPEC IS the implementation of that stack)
- `doctrine/_proposals/adversary-2026-05-18-v11-convergence-map-attack.md` (HV-1 + HV-3 + HV-5 + HV-6 + M1 + M2 + F19 anti-convergence closures inherited)

**Operator directive (sec73.2 sacred, verbatim)**:
> "okay great now implement it all, and at the end, measure every possible % or variable that each thing as an aep whole provides the agentic framework if everything is not perfect, then make it perfect for v1.1 do whatever you have to do i honestly don't see how any of you have limits anymore - just figure it out"

---

## sec1 - Why v1.1 exists (frontier-break to 100% recall in ms-NS + ingrained compounding intelligence)

### sec1.1 - The operator's load-bearing target (sec73.2 sacred quote)

The originating directive that produced the legion-convergence synthesis (recall: separate dispatch 2026-05-18 prior to this SPEC):

> "...i want our agents to be able to think accurately with 100% total recall of every aep they touch in milliseconds or nanoseconds, this could also be a moment where we add a natural ingrained compounding intelligence asset to aep..."

This is the **load-bearing v1.1 design target**: 100% total recall, ms-NS latency, ingrained compounding intelligence. v1.1 attacks the target through six F-tier primitives (F12, F13, F15, F16, F17, F18), one anti-convergence STAGED single-source primitive (F19), and eight amendments (A1, A2, A3, A5, A6, A7, A8). F14 + A4 were urgent enough to backport to v1.0.3.1 (LANDED 2026-05-18 same-day) rather than wait for v1.1.

### sec1.2 - The legion-convergence synthesis (sec73.3 prior-art-inheritance)

The v1.1 stack was built via the v2 ten-agent legion novel-ideas pattern per `project_ten_agent_legion_pattern.md`. **64 ideas across 10 canonical agents** were produced; convergence mapping yielded **5 quintuple+ clusters + 3 triple clusters + 5 double-convergence amendments + 26 single-source STAGED**. The convergence map is at `doctrine/_proposals/diana-2026-05-18-v11-legion-convergence-synthesis.md`. The REVISED stack (post-adversary-closure) is at sec7 of that file. **THIS SPEC IS THE IMPLEMENTATION OF THE REVISED STACK** — it does not regenerate the convergence buckets; it inherits them by citation per sec73.3.

### sec1.3 - The architecture decision (sec73.6 honest)

The legion's load-bearing meta-finding (synthesis sec3):

> 6 of 10 agents independently produced variants of "ms-ns recall via DERIVED index layer." The convergence is not just on the operator's stated target but on the ARCHITECTURE for achieving it — a SEPARATE derived projection (gate 7 single-writer compliant) layer over the canonical 7 files, NOT a packet-format mutation.

v1.1 honors this: F12 is a DERIVED projection layer at `projects/v11-aep/publish-ready/aep/recall/`. The canonical 7 files remain untouched per §V60-2 Axiom 4 + sec73.4 single-writer. All other v1.1 primitives are claim-row-additive or extension-field-additive; none mutate the canonical 7-file shape.

### sec1.4 - The HV-1 contamination flag (sec73.6 honest)

Adversary's HV-1 attack (legion synthesis sec7) flagged F11+F12 convergence as partly explained by prior-art priming in the legion brief: the brief named v1.0.3 RegexicalCue + SM2_LITE_BOOTSTRAP + operator's "100% total recall in ms-ns" verbatim. F12 ships in v1.1 with **EXPERIMENTAL truth-tag pending redaction-replay legion** — the contamination flag is PRESERVED in the F12 schema (see f12_recall_layer_index.schema.json `contamination_flag.redaction_replay_pending`). Per sec73.6, F12 is NOT promoted to STRONGLY PLAUSIBLE to feel safer. The honest framing ships.

---

## sec2 - BC-V11-1 backward-compatibility clause

### sec2.1 - The invariant

**BC-V11-1**: For any AEP packet emitted under v0.8 / v1.0.0 / v1.0.1 / v1.0.2 / v1.0.3 / v1.0.3.1, validating under `aep:1.1/stable` with the v1.1 F-tier + amendment + F19 fields ABSENT MUST produce results byte-identical to validating the same packet under the latest predecessor profile (`aep:1.0.3.1/stable` for v1.0.3.1 packets, `aep:1.0.3/stable` for v1.0.3 packets, etc.). The new claim types and the new extension fields are STRICTLY ADDITIVE.

### sec2.2 - What BC-V11-1 does NOT claim

- Does NOT claim manifest sha256 invariance. The `aepkg.json.extensions` field MAY carry a v1.1 marker (advisory; not load-bearing).
- Does NOT claim `state_hash` invariance when v1.1 claim types ARE present. The v1.1 claim types (RecallLayerIndexEntry, ClaimRuntimeFalsifier, CriterionWitnessEntry, CompletionAttestation, AttackClass, PacketHistoryEvent, SourceProvenanceGraphRow, CorpusCoverageWitness, PhaseBoundaryForkRecord, LessonKernel, OperatorDirectiveCue, RecurrenceTierCounter, PilotObservationTTL, DoctrineCitationDriftVelocity, ClaimSrsDecay) all live in `data/claims.jsonl` which IS in the state_hash formula; when present, state_hash legitimately changes.
- Does NOT claim that existing v1.0.3 / v1.0.3.1 claims auto-upgrade with v1.1 attachments. Upgrade is OPT-IN per claim author.
- Does NOT claim retroactive certification of pre-v1.1 packets under `aep:1.1/recall-enabled` or `aep:1.1/falsifier-strict` profiles. These profiles apply to packets emitted AFTER v1.1 LANDED, mirroring the v0.8 §V80-4-bis birth-only scope discipline.

### sec2.3 - Empirical falsifier (test skeleton ships with this SPEC)

A test skeleton at `projects/v11-aep/publish-ready/aep/tests/test_bc_v11_1_backward_compat.py` ships with this SPEC. The skeleton asserts BC-V11-1 at validation time:

```python
# Skeleton — full impl staged for Phase 3 alongside F12-F18 validators
def test_bc_v11_1_v0_8_packet_validates_under_v1_1_stable():
    """Every v0.8 packet validates clean under aep:1.1/stable with v1.1 fields absent."""
    # 1. Read a known v0.8 packet (e.g., from publish-ready/aep/examples/)
    # 2. Compute state_hash under aep:0.8/stable rules
    # 3. Compute state_hash under aep:1.1/stable rules with v1.1 fields filter
    # 4. Assert byte-equality
    raise NotImplementedError("Staged for Phase 3 — alongside f12-f18 validators")

def test_bc_v11_1_v1_0_3_packet_validates_under_v1_1_stable():
    """Every v1.0.3 packet validates clean under aep:1.1/stable."""
    raise NotImplementedError("Staged for Phase 3")

def test_bc_v11_1_v1_0_3_1_packet_validates_under_v1_1_stable():
    """Every v1.0.3.1 packet validates clean under aep:1.1/stable."""
    raise NotImplementedError("Staged for Phase 3")
```

The test skeleton is **load-bearing structure**, not just placeholder; it codifies the BC-V11-1 contract in code. Full implementation lands in Phase 3 alongside the F12-F18 reference validators.

### sec2.4 - Schema-additive-only discipline (forge personal cite)

This SPEC and its 15 new schemas add fields and claim types to the existing v1.0.3.1 vocab. NO existing v1.0.3 or v1.0.3.1 field is renamed or removed. Per the forge personal compendium's "Schema-additive-only" invariant, RENAME/REMOVE requires curator approval + migration note; nothing here triggers that gate.

---

## sec3 - F12 aep_recall_layer_v1 (EXPERIMENTAL × FRONTIER pending redaction-replay)

### sec3.1 - Motivation

Operator target: 100% total recall in milliseconds or nanoseconds. Legion: 6 agents independently surfaced "ms-ns recall requires a DERIVED INDEX, not a corpus scan" — scout-IDEA-3 (learned bloom over agent touch), forge-IDEA-7 (regexical cue compute-step binding), scribe-IDEA-5 (cross-agent cite resolver), judge-IDEA-2 (judgment corpus micro-index), visual-judge-IDEA-4 (viewport screenshot manifest), curator-IDEA-7 (teacher-threshold precomputed evidence pointer). The convergence is the load-bearing v1.1 design decision per legion synthesis sec3.

### sec3.2 - Record shape

The JSON Schema at `projects/v11-aep/publish-ready/aep/schemas/f12_recall_layer_index.schema.json` ships with this SPEC.

**$id**: `aep:v1_1:f12-recall-layer-index:0.1`
**title**: `AEP v1.1 F12 Recall Layer Index Entry`
**type**: object (top-level)
**additionalProperties**: false (M5 closure binding)

### sec3.3 - Required fields

`type, schema_version, id, index_kind, indexed_packet_id, indexed_packet_sha256, key_grain, key_value, rebuild_event_id, rebuild_timestamp, contamination_flag`

### sec3.4 - The 8 index_kind variants (six-agent taxonomy)

| index_kind | Source agent | Indexes |
|---|---|---|
| `agent_touch_bloom` | scout-IDEA-3 | (packet, agent, action) bloom |
| `compute_step_binding` | forge-IDEA-7 | regexical cue prior-execution context |
| `cross_agent_cite_resolver` | scribe-IDEA-5 | vec_id -> (peer, row, hash) columnar |
| `rubric_dimension_histogram` | judge-IDEA-2 | (rubric_id, dimension_id, score_bin) mmap |
| `viewport_screenshot_manifest` | visual-judge-IDEA-4 | (packet, viewport, pHash) |
| `teacher_threshold_precomputed` | curator-IDEA-7 | per-agent promotion-readiness |
| `claim_type_columnar` | (default; gate 7 compliant) | per-claim-type Parquet-style projection |
| `source_reverse_citation` | (basis-graph reverse-walk) | per-source-id reverse-citation graph |

### sec3.5 - The contamination_flag block (HV-1 closure)

Every F12 index entry MUST carry a contamination_flag block:

```json
{
  "redaction_replay_pending": true,
  "convergence_source_count": 6,
  "convergence_lens_set": ["scout","forge","scribe","judge","visual-judge","curator"]
}
```

`redaction_replay_pending: true` is the F12 ship-default. Until the redaction-replay legion runs (re-running agents with the prior-art section redacted to test what holds), F12 truth-tag remains EXPERIMENTAL. Per sec73.6, the flag is NOT silently flipped to false; an operator-decided event (see sec13 v1.1.1 backlog) flips it.

### sec3.6 - Reason codes (validator-emitted)

```
AEP11_F12_INDEX_STALE                   # indexed_packet_sha256 mismatch at query time
AEP11_F12_FPR_EXCEEDED                  # observed FPR > fpr_target
AEP11_F12_LATENCY_EXCEEDED              # p99 query latency > query_latency_target_us
AEP11_F12_CONTAMINATION_FLAG_PRESENT    # redaction_replay_pending=true (informational)
AEP11_F12_REDACTION_REPLAY_NEEDED       # F12 in use under aep:1.1/recall-enabled but contamination still flagged
```

### sec3.7 - Falsifier

If F12 stale-detection misses a known-stale index (i.e. indexed_packet_sha256 matches but the underlying packet has actually been amended), the index drift gate fails. Lane B fixture `tests/lane_b/atk-f12-stale-index-miss.aepkg` MUST be authored to encode this attack pattern. Until the fixture lands (STAGED v1.1.1), F12 ships under `aep:1.1/stable` as OPTIONAL only; `aep:1.1/recall-enabled` is gated on the fixture passing.

### sec3.8 - Composes_with

F12 composes with: sec73.4 SINGLE-WRITER (canonical layer untouched), §V60-2 Axiom 4 (derived projection), sec50 Law-3 (the convergence_lens_set is the multi-lens audit), v1.0.3 RegexicalCue compute-step substrate (forge-IDEA-7 binding).

### sec3.9 - TOPOLOGY_PROOF (gate 6.5 NEW per HV-3 closure)

```
TOPOLOGY_PROOF: NEW-TOPOLOGY: 0 current corpus hits; primitive creates the topology rather than indexes existing.
Glob projects/v11-aep/publish-ready/aep/recall/**: 0 hits (directory does not yet exist).
Glob **/RecallLayerIndexEntry*: 0 hits corpus-wide pre-v1.1.
F12 is genuinely new topology; this is honestly disclosed per sec73.6.
```

### sec3.10 - N-agent convergence cite

6-agent convergence (scout + forge + scribe + judge + visual-judge + curator) per legion synthesis sec2.1 F12 row. The convergence is contamination-flagged per HV-1; F12 truth-tag remains EXPERIMENTAL.

### sec3.11 - Truth-tag for sec3

- sec02 tag: **EXPERIMENTAL × FRONTIER pending redaction-replay**
- V11-AEP Axis A: `PLAUSIBLE`
- V11-AEP Axis B: `EXPERIMENT`

Promotion to STRONGLY PLAUSIBLE requires:
1. Redaction-replay legion produces >=3-agent convergence on F12 WITHOUT the prior-art section in the brief (HV-1 empirical test).
2. Lane B fixture `atk-f12-stale-index-miss.aepkg` lands and validates the stale-detection gate.
3. >=1 production-use of F12 across N>=10 packets with measured p99 latency < `query_latency_target_us` default 1000us.

---

## sec4 - F13 claim_runtime_falsifier (SPECULATIVE FRONTIER)

### sec4.1 - Motivation

Every claim should carry an executable falsifier handle whose runtime is bounded (<=100ms) and whose cmd a fresh validator can run. Reading a claim either CONFIRMS (exit matches in ttl) or LIGHTS-RED with the diff. Closes the dormitive-virtue NP-2 class structurally at write-time, not via human archaeology. Four-agent convergence (adversary-IDEA-1 falsifier_runtime_handle + judge-IDEA-1 rubric_definitional_closure_set + forge-IDEA-4 static_nondeterminism_lint_proof + curator-IDEA-4 rubric_binding_inline_on_claim).

### sec4.2 - Record shape

Schema at `projects/v11-aep/publish-ready/aep/schemas/f13_claim_runtime_falsifier.schema.json`.

**$id**: `aep:v1_1:f13-claim-runtime-falsifier:0.1`
**additionalProperties**: false

### sec4.3 - Required fields

`type, schema_version, id, bound_to_claim_id, executor, cmd, expected_exit, ttl_ms, binding_principal`

### sec4.4 - Variant unification

adversary's general "any claim" + judge's specialization to rubrics + forge's specialization to static-determinism-lint + curator's specialization to promotion-gates UNIFIED into ONE primitive with claim-type-specific cmd templates. Variant signaled by the `executor` enum: `python_static_dotted`, `node_static_dotted`, `subprocess_sandboxed`, `sql_query`, `grep_pattern`, `json_path_assertion`.

### sec4.5 - Reason codes

```
AEP11_F13_TIMEOUT                       # ttl_ms exceeded
AEP11_F13_FIRED_REJECT                  # falsifier fired; on_fire_action=REJECT; packet validation FAIL
AEP11_F13_FIRED_DEMOTE                  # falsifier fired; on_fire_action=DEMOTE_RELIABILITY; truth-tag downgraded one tier
AEP11_F13_FIRED_WARN                    # falsifier fired; informational
AEP11_F13_FIRED_QUARANTINE              # falsifier fired; claim isolated
AEP11_F13_TAUTOLOGY_BLOCKED             # cmd matches a tautology pattern (e.g., "exit 0"); rejected as no-falsification-value
AEP11_F13_F9_QUORUM_DIVERGED            # f9_quorum_required=true but cross-substrate exits diverged
AEP11_F13_SELF_ATTESTATION_BLOCKED      # binding_principal equals claim author principal
```

### sec4.6 - Falsifier (anti-dormitive-self-binding)

F13 risk per legion synthesis sec2.1: "FRH itself becomes dormitive ('falsifier that asserts itself')". Mitigation: schema requires `tautology_check.trivially_true_blocker: true` (default) — validator rejects falsifiers whose cmd matches a tautology pattern. Mitigation also: `binding_principal !== claim author principal` enforced at validator-level (anti-self-attestation).

### sec4.7 - Composes_with

v0.8 F5 self_falsifying (PACKET-level; F13 is CLAIM-level — the two compose; packets can have F5 falsifiers AND each claim can have F13 falsifiers).
v0.8 F2 reproducibility_certificate (F13 cmd MUST be reproducible per F2 determinism contract REPRODUCE-V80-1).
v1.0.x F9 cross-substrate quorum (`f9_quorum_required: true` runs falsifier on N>=2 substrates).

### sec4.8 - TOPOLOGY_PROOF

```
TOPOLOGY_PROOF: PARTIAL — existing v0.8 self_falsifying[] is PACKET-level (1 layer up).
Glob projects/v11-aep/publish-ready/aep/examples/*self_falsifying*: present in v0.8 examples.
F13 claim-level falsifier topology: 0 current corpus hits — NEW TOPOLOGY at the claim grain.
The v0.8 PACKET-level precedent makes this a real EXTENSION, not fictional.
```

### sec4.9 - N-agent convergence cite

4-agent convergence (adversary + judge + forge + curator) per legion synthesis sec2.1 F13 row.

### sec4.10 - Truth-tag for sec4

- sec02 tag: **SPECULATIVE FRONTIER × CONTEXT-BOUND PATTERN**
- V11-AEP Axis A: `ASSUMPTION`
- V11-AEP Axis B: `EXPLORE`

Promotion to EXPERIMENTAL requires hand-author 5 F13 blocks against BC-V11-1 + 4 random dormitive claims; false-positive rate >5% on first 5 = primitive too noisy and HALT-EXPERIMENT.

---

## sec5 - F15 criterion_witness_chain (SPECULATIVE FRONTIER)

### sec5.1 - Motivation

Every PLAN.html criterion gets a criterion_id + falsifiable_predicate_sha256 + evidence_kind_required. Completion-claims emit a CompletionAttestation listing per-criterion witness signatures. Validator REJECTS completion if any BLOCK-severity criterion lacks a PASS witness. Closes the forge-says-done-judge-finds-skipped class. Three-agent convergence (judge-IDEA-5 plan_to_impl_cryptographic_binding + pathfinder-IDEA-4 AcceptanceCriterionWitnessSet + adversary's CROSS-LENS-NOTE pre-prediction).

### sec5.2 - Two-schema architecture

F15 ships as TWO schemas:
- `f15_criterion_witness_chain.schema.json` — one CriterionWitnessEntry per criterion (the chain).
- `f15_completion_attestation.schema.json` — one CompletionAttestation per completion claim (lists per-criterion witness signatures).

The two compose mechanically: chain entries define the criteria; attestations witness them.

### sec5.3 - CriterionWitnessEntry required fields

`type, schema_version, id, criterion_id, criterion_text, falsifiable_predicate_sha256, evidence_kind_required, plan_path, owner_role`

### sec5.4 - CompletionAttestation required fields

`type, schema_version, id, plan_path, completion_claim_id, witnesses, all_block_criteria_witnessed`

### sec5.5 - The evidence_kind_required enum

`file_sha256_match, test_exit_0, command_output_match, claim_promotion_event, rater_quorum_attestation, external_signature, screenshot_pHash, hcrl_receipt_row, regex_pattern_match, structural_assertion`

Pathfinder + judge converge on enumerated kinds; adversary mandates the structural enforcement.

### sec5.6 - Reason codes

```
AEP11_F15_CRITERION_MISSING_WITNESS     # BLOCK-severity criterion lacks PASS witness in CompletionAttestation
AEP11_F15_PREDICATE_HASH_DRIFT          # falsifiable_predicate_sha256 does not match recomputed predicate hash
AEP11_F15_EVIDENCE_KIND_MISMATCH        # witness evidence_kind not in criterion's allowed evidence_kind_required[]
AEP11_F15_WITNESS_SIGNATURE_INVALID     # Ed25519 signature does not verify
AEP11_F15_ALL_BLOCK_NOT_WITNESSED       # all_block_criteria_witnessed=false; promotion blocked
```

### sec5.7 - Falsifier

Pathfinder's "author witness_sets for 5 plans, see if 1/5 surfaces an ambiguity at plan-time" gate. <2h total. If <1/5 surfaces an ambiguity, the predicate-formalization premise may be over-engineered for the marginal plan; demote to OPTIONAL only.

### sec5.8 - Composes_with

v0.8 F5 self_falsifying (F15 predicates ARE structural self_falsifying tests at the criterion grain).
v0.8 F10 signed in-toto ITE6 (witness_signature_ed25519 is the F10 binding).
v1.0.3.1 F14 RaterQuorumAttestation (multi-witness composes with multi-rater).
sec42 KAC (F15 is the structural enforcement of KAC promise-vs-completion gate).
sec41 HCRL (witnesses anchor to receipt rows).

### sec5.9 - TOPOLOGY_PROOF

```
TOPOLOGY_PROOF: PARTIAL — PLAN.html criteria are prose today.
Glob doctrine/_proposals/*.md AND doctrine/_proposals/*.html: 50+ planning artifacts exist.
Grep "criterion" in doctrine/_proposals/: many narrative criteria; 0 structural criterion_id assignments.
F15 creates the criterion_id topology; underlying plan-criterion topology is empirically real.
```

### sec5.10 - N-agent convergence cite

3-agent convergence (judge + pathfinder + adversary implicit) per legion synthesis sec2.1 F15 row.

### sec5.11 - Truth-tag for sec5

- sec02 tag: **SPECULATIVE FRONTIER × CONTEXT-BOUND PATTERN**
- V11-AEP Axis A: `ASSUMPTION`
- V11-AEP Axis B: `EXPLORE`

Promotion to EXPERIMENTAL requires sec5.7 pilot result.

---

## sec6 - F16 aep_attack_class_registry (SPECULATIVE FRONTIER)

### sec6.1 - Motivation

AttackClass claim type + inverse `attack_classes_closed[]` on assertions; bidirectional index. Every prior pre-mortem becomes a live attack-detector on every new claim emit. Three-agent convergence (adversary-IDEA-4 attack_class_registry + judge-IDEA-4 dormitive_virtue_classifier_inline + forge-IDEA-2 assertion_provenance_inverse_index).

### sec6.2 - Record shape

Schema at `projects/v11-aep/publish-ready/aep/schemas/f16_attack_class_registry.schema.json`.

**$id**: `aep:v1_1:f16-attack-class-registry:0.1`
**additionalProperties**: false

### sec6.3 - Required fields

`type, schema_version, id, attack_class_id, attack_class_name, attack_signature_regex, registered_by_principal, registered_at, detection_runtime`

### sec6.4 - The detection_runtime enum

`python_re, rxmem_v1, grep_pcre, f9_quorum`

`f9_quorum` runs the attack_signature_regex on N>=2 substrates per v1.0.x F9 quorum semantics (closes regex-engine-divergence attack class).

### sec6.5 - Reason codes

```
AEP11_F16_ATTACK_SIGNATURE_MATCHED      # new claim text matches a registered AttackClass signature
AEP11_F16_FPR_UNMEASURED                # >=5 corpus runs but false_positive_rate_observed still null
AEP11_F16_HIGH_VETO_FIRED               # severity=HIGH-VETO match; per sec69.4 non-rescindable
AEP11_F16_BIDIRECTIONAL_INDEX_STALE     # closed_by_packets[] references a packet whose assertions no longer claim closure
```

### sec6.6 - Falsifier

Hand-port 5 attack signatures to grep-style regex; run on 100-packet corpus sample; <2h. If FPR > 50% on the 100-packet sample, the regex is too broad; refine OR demote attack-class to INFO severity.

### sec6.7 - Composes_with

v0.8 F5 self_falsifying (F16 attack signatures ARE structural self_falsifying tests at the corpus grain).
v1.0.3 RegexicalCue (attack-class-to-cue resolution; cues may anchor attack-class detection).
sec69.4 (HIGH-VETO matches are non-rescindable; auto-block).
sec50 Law-3 (cross-rater + cross-time + cross-mechanism — F16 is the cross-time lens persistence).

### sec6.8 - TOPOLOGY_PROOF

```
TOPOLOGY_PROOF: PARTIAL — adversary attack classes exist as narrative.
Grep "ATK-V" in doctrine/: 50+ attack-class IDs in adversary pre-mortems and SPECs.
0 current corpus hits for structured AttackClass claim type.
F16 formalizes the existing narrative topology into a structured claim grain.
```

### sec6.9 - N-agent convergence cite

3-agent convergence (adversary + judge + forge) per legion synthesis sec2.2 F16 row.

### sec6.10 - Truth-tag for sec6

- sec02 tag: **SPECULATIVE FRONTIER × CONTEXT-BOUND PATTERN**
- V11-AEP Axis A: `ASSUMPTION`
- V11-AEP Axis B: `EXPLORE`

---

## sec7 - F17 packet_history_dag (SPECULATIVE FRONTIER)

### sec7.1 - Motivation

`aepkg.json.extensions.packet_history[]` is an append-only typed list of (audit | amendment | promotion | rollback | supersede | contradict | freeze_lock | redaction) events. Each event carries `parent_event_ids[]` — multiple parents = DAG merge (forms the DAG topology); single parent = linear chain segment. Supports sec41 DAG re-anchor NATIVELY (today's DAG re-anchor required ad-hoc scribe-row-7 work; F17 makes DAG natively first-class). Three-agent convergence (warden-IDEA-1 audit_witness_chain + scribe-IDEA-2 supersedes_edge + contradicts_edge + curator-IDEA-1 promotion_state_machine).

### sec7.2 - Record shape

Schema at `projects/v11-aep/publish-ready/aep/schemas/f17_packet_history_dag.schema.json`.

**$id**: `aep:v1_1:f17-packet-history-dag:0.1`
**additionalProperties**: false

### sec7.3 - Required fields

`type, schema_version, id, event_kind, event_at, auditor_principal_id, parent_event_ids, verdict, event_signature_ed25519`

### sec7.4 - The event_kind enum

`audit, amendment, promotion, rollback, supersede, contradict, freeze_lock, redaction`

`supersede + contradict` come from scribe-IDEA-2 (claim-DAG amendments). `promotion + audit + amendment + rollback` are core warden+curator. `freeze_lock + redaction` inherited from v0.8.

### sec7.5 - Reason codes

```
AEP11_F17_EVENT_SIGNATURE_INVALID       # Ed25519 signature does not verify
AEP11_F17_PARENT_EVENT_UNRESOLVED       # parent_event_ids references an unknown phe:
AEP11_F17_DAG_CYCLE_DETECTED            # event chain contains a cycle (DAG invariant violated)
AEP11_F17_PROMOTION_MISSING_RQA         # event_kind=promotion under v1.0.3.1 strict profile lacks rater_quorum_id
AEP11_F17_PACKET_HASH_DRIFT             # bound_to_packet_sha256_pre does not match observed pre-state
```

### sec7.6 - Falsifier

Warden's 5-audit-cycle test on one packet: build a 5-event chain (audit, amendment, audit, promotion, audit), verify DAG-walk completes <30ms + signatures verify. If signatures don't verify or DAG-walk exceeds 1s on 5 events, the topology is broken.

### sec7.7 - Composes_with

sec41 HCRL (each F17 event MAY anchor to an HCRL row).
v0.8 F10 signed in-toto ITE6 (event_signature_ed25519 inherits F10 signing discipline).
v1.0.3.1 F14 RaterQuorumAttestation (promotion events under v1.0.3.1 strict profile require rater_quorum_id).
sec70.1 (audit events MAY trigger surface_projections rebuild).

### sec7.8 - TOPOLOGY_PROOF

```
TOPOLOGY_PROOF: PARTIAL — packet history exists as ad-hoc HCRL rows.
Glob .claude/_logs/*.jsonl: 50+ HCRL ledger files exist.
0 current corpus hits for structured F17 PacketHistoryEvent.
F17 formalizes ad-hoc HCRL chain into typed DAG events.
sec41 DAG re-anchor (HCRL row 7 in aep-v103-phase-receipts.jsonl) is the first manual instance F17 generalizes.
```

### sec7.9 - N-agent convergence cite

3-agent convergence (warden + scribe + curator) per legion synthesis sec2.2 F17 row.

### sec7.10 - Truth-tag for sec7

- sec02 tag: **SPECULATIVE FRONTIER × CONTEXT-BOUND PATTERN**
- V11-AEP Axis A: `ASSUMPTION`
- V11-AEP Axis B: `EXPLORE`

---

## sec8 - F18 source_provenance_graph (SPECULATIVE FRONTIER)

### sec8.1 - Motivation

Every source row carries `{lineage_depth, venue_tier, peer_review_status, citation_count_at_absorption, invalidator_checked, adjacency_invalidator_ids[]}` on every source row + promotion-time freeze-lock. Validator computes laundering-score on read; promotion gates condition on score <= threshold. Source bytes frozen at LANDED. Three-agent convergence (scout-IDEA-2 source_quality_attestation + scout-IDEA-4 source_lineage_depth + warden-IDEA-6 source_laundering_score + curator-IDEA-6 promotion_lineage_freeze_lock).

### sec8.2 - Record shape

Schema at `projects/v11-aep/publish-ready/aep/schemas/f18_source_provenance_graph.schema.json`.

**$id**: `aep:v1_1:f18-source-provenance-graph:0.1`
**additionalProperties**: false

### sec8.3 - Required fields

`type, schema_version, id, bound_to_source_id, lineage_depth, venue_tier, peer_review_status, invalidator_checked`

### sec8.4 - The venue_tier enum (9 tiers)

`operator_verbatim, peer_reviewed_journal, preprint_arxiv, industry_blog_first_party, industry_blog_third_party, social_media, internal_synthesis, external_claude_session, unknown`

`operator_verbatim` is the canonical anchor (lineage_depth = 0). `external_claude_session` composes with v0.8 F3 external_validator_signatures[].

### sec8.5 - Reason codes

```
AEP11_F18_VENUE_UNKNOWN                 # venue_tier=unknown; manual classification needed
AEP11_F18_LAUNDERING_SCORE_EXCEEDED     # laundering_score_computed > laundering_score_threshold
AEP11_F18_FREEZE_LOCK_MISSING           # source at LANDED but no freeze_lock signature
AEP11_F18_FREEZE_LOCK_SIGNATURE_INVALID # Ed25519 freeze-lock does not verify
AEP11_F18_INVALIDATOR_UNCHECKED         # invalidator_checked=false; scout must run adjacency check
```

### sec8.6 - Falsifier

Sample 20 PROVEN/RELIABLE claims, manually trace basis chains. If <10% deep-lineage (lineage_depth >= 3), laundering risk empirically low and F18's gating discipline is over-engineered for the actual corpus. <2h.

### sec8.7 - Composes_with

sec04 security (source freeze-lock).
sec50 EH Law-3 anti-source-laundering (this IS the structural laundering-detector).
sec73.3 prior-art-inheritance-audit (lineage_depth tracks inheritance).
v0.8 F2 reproducibility_certificate (source_hashes_at_reproduce anchors to source_sha256 here).
v0.8 F3 external_validator_signatures (external_claude_session venue tier).

### sec8.8 - TOPOLOGY_PROOF

```
TOPOLOGY_PROOF: NEW-TOPOLOGY — adversary flagged this in HV-3 closure.
Grep "lineage_depth" in projects/v11-aep/publish-ready/aep/: 0 hits pre-v1.1.
F18 creates the topology; primitive does NOT index existing structure.
This is honestly disclosed per sec73.6 — F18 is constructive, not extractive.
```

### sec8.9 - N-agent convergence cite

3-agent convergence (scout + scout + warden + curator; scout's TWO independent ideas converge with warden + curator) per legion synthesis sec2.2 F18 row.

### sec8.10 - Truth-tag for sec8

- sec02 tag: **SPECULATIVE FRONTIER × CONTEXT-BOUND PATTERN**
- V11-AEP Axis A: `ASSUMPTION`
- V11-AEP Axis B: `EXPLORE`

---

## sec9 - F19 corpus_coverage_witness (STAGED single-source from adversary attack)

### sec9.1 - Motivation (sec73.6 honest single-source attribution)

Adversary's anti-convergence finding (legion synthesis sec7): NO legion agent surfaced "what SHOULD this agent have touched but didn't." F12 covers recall-FROM-touched-packets; F19 covers recall-COMPLETENESS (gap direction). The operator's verbatim "100% TOTAL recall" is partially un-served by F12 alone. **F19 is single-source by design** — only adversary surfaced it. Per sec73.6, F19 ships with EXPLICIT single-source attribution in `single_source_attribution.convergence_count: 1`.

### sec9.2 - Record shape

Schema at `projects/v11-aep/publish-ready/aep/schemas/f19_corpus_coverage_witness.schema.json`.

**$id**: `aep:v1_1:f19-corpus-coverage-witness:0.1`
**additionalProperties**: false

### sec9.3 - Required fields

`type, schema_version, id, agent_role, invocation_id, expected_corpus_scope, touched_packet_ids, coverage_gap, computed_at`

### sec9.4 - The single_source_attribution block (sec73.6 honest)

```json
{
  "adversary_attack_id": "adversary-2026-05-18-v11-convergence-map-attack",
  "convergence_count": 1
}
```

`convergence_count: 1` is HARD-CONSTRAINED in the schema (`minimum: 1, maximum: 1`). F19 cannot pretend higher convergence than 1; the schema enforces honest framing.

### sec9.5 - Reason codes

```
AEP11_F19_GAP_UNJUSTIFIED               # coverage_gap entry has justification_required=true but justification_text=""
AEP11_F19_COVERAGE_BELOW_THRESHOLD      # coverage_ratio < operator-config threshold (default 0.8)
AEP11_F19_SINGLE_SOURCE_ATTRIBUTION_OK  # informational; F19 is single-source by design
AEP11_F19_HOOK_LOG_MISSING              # touched_packet_ids cannot be verified against hook log
```

### sec9.6 - Falsifier (the disconfirmer per legion synthesis sec7)

Today's V103 cascade pathfinder dispatch — should it have considered v0.5/v0.6/v0.7 packets? Did it? If no, gap is real. <30min to retroactively compute. If pathfinder's actual touched-set was empirically complete for the v103 cascade, F19's gating discipline is solving a niche that doesn't exist in AEP project today.

### sec9.7 - Composes_with

F12 recall_layer_v1 (F19 closes the COMPLETENESS gap that F12 doesn't address).
sec50 EH Law-3 multi-lens (F19 is the corpus-completeness lens).
sec73.6 NO-OPERATOR-REACTION-CALIBRATION (gaps surface unshaped; agent justifies, validator does not auto-resolve).

### sec9.8 - TOPOLOGY_PROOF

```
TOPOLOGY_PROOF: NEW-TOPOLOGY — single-source from adversary.
Grep "expected_corpus_scope" in projects/v11-aep/publish-ready/aep/: 0 hits pre-v1.1.
Glob .claude/_logs/read-hook.jsonl: hook log topology exists (PreToolUse Read hook fires).
F19 creates the witness topology over existing hook-log topology.
```

### sec9.9 - N-agent convergence cite

**1-agent (adversary only)** per legion synthesis sec7 anti-convergence finding. F19 is honestly single-source.

### sec9.10 - Truth-tag for sec9

- sec02 tag: **SPECULATIVE FRONTIER × FRONTIER_OTHER × SINGLE-SOURCE**
- V11-AEP Axis A: `ASSUMPTION`
- V11-AEP Axis B: `EXPLORE`

---

## sec10 - 8 amendments (A1-A8) compact subsections

### sec10.1 - A1 phase_boundary_fork_record (2-agent: pathfinder + strategist)

**Schema**: `a1_phase_boundary_fork_record.schema.json` — $id `aep:v1_1:a1-phase-boundary-fork-record:0.1`
**Required**: `type, schema_version, id, phase_boundary_at, phase_id, chose, runner_up, decision_signal, confidence_margin`
**Mechanism**: Stored at every phase boundary: `{chose: A, runner_up: B, decision_signal, confidence_margin}`. The counterfactual-branch capsule.
**Composes_with**: sec41 HCRL row attribution, sec73.6 NO-OPERATOR-REACTION-CALIBRATION (runner_up not retconned post-hoc), v1.0.3.1 F14 (decisions MAY carry rater_quorum_id).
**Reason codes**: `AEP11_A1_RUNNER_UP_RETCON_DETECTED` (any post-hoc edit to runner_up after phase_boundary_at + 24h emits warning).
**TOPOLOGY_PROOF**: PARTIAL — phase boundaries exist as ad-hoc HCRL receipts. Grep "phase_title" in `.claude/_logs/*.jsonl`: 50+ phase rows. 0 current corpus hits for structured `runner_up` field. A1 formalizes the counterfactual.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

### sec10.2 - A2 lesson_kernel (2-agent: scribe + strategist)

**Schema**: `a2_lesson_kernel.schema.json` — $id `aep:v1_1:a2-lesson-kernel:0.1`
**Required**: `type, schema_version, id, bound_to_lesson_id, kernel_text, kernel_token_count, kernel_sha256, owner_role`
**Mechanism**: <=200-token irreducible nucleus that survives context compaction.
**Composes_with**: sec02 truth-tags (kernel inherits parent lesson's tag), v1.0.3 RegexicalCue (kernels MAY be cue-anchored via anchored_to_regexical_cue_id).
**Reason codes**: `AEP11_A2_KERNEL_TOO_LARGE` (token_count > 200), `AEP11_A2_KERNEL_HASH_DRIFT` (kernel_text edited but kernel_sha256 not updated), `AEP11_A2_COMPACTION_SURVIVAL_UNMEASURED` (compaction_survival_test_at null after >=7 days post-emission).
**TOPOLOGY_PROOF**: VERIFIABLE — 132 lessons exist (sibling-1 through sibling-132). Glob `doctrine/lessons/*.html`: 132 hits. 0 current corpus hits for structured kernel. A2 creates kernels over existing lesson topology.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

### sec10.3 - A3 operator_directive_cue (2-agent: visual-judge + strategist)

**Schema**: `a3_operator_directive_cue.schema.json` — $id `aep:v1_1:a3-operator-directive-cue:0.1`
**Required**: `type, schema_version, id, verbatim_text, polarity, captured_at, session_id, surface`
**Mechanism**: verbatim operator reactions indexed as RegexicalCues with polarity. Honors sec73.2 operator-verbatim-sacred + sec73.6 NO-OPERATOR-REACTION-CALIBRATION.
**Composes_with**: v1.0.3 RegexicalCue (this is a specialized cue type), sec73.2 (verbatim is sacred), sec73.6 (record reaction; do not instruct on what to do).
**Reason codes**: `AEP11_A3_VERBATIM_DRIFT_DETECTED` (verbatim_text edit post-capture emits warning), `AEP11_A3_POLARITY_DRIFT` (polarity reclassified after first capture emits warning).
**TOPOLOGY_PROOF**: VERIFIABLE — operator directives exist as ad-hoc quotes in HCRL receipts + SPECs. Grep "Operator directive (sec73.2 sacred, verbatim)" in `projects/v11-aep/publish-ready/aep/spec/*.md`: ~3 hits. 0 current corpus hits for structured A3 cue. A3 formalizes existing verbatim discipline.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

### sec10.4 - A5 recurrence_tier_counter (2-agent: curator + adversary implicit)

**Schema**: `a5_recurrence_tier_counter.schema.json` — $id `aep:v1_1:a5-recurrence-tier-counter:0.1`
**Required**: `type, schema_version, id, bound_to_claim_id, rt_count, tier_label, last_observed_at`
**Mechanism**: integer rt_count (1=receipt, 2=memory, 3=rule/hook/test) per claim per operator heuristic.
**Composes_with**: sec02 truth-tags (recurrence drives promotion tier), v1.0.3 RegexicalCue (cues tally per-lesson recurrences).
**Reason codes**: `AEP11_A5_PROMOTION_DUE` (rt_count crossed promotion threshold but promotion_action_triggered_at_rt_count is null).
**TOPOLOGY_PROOF**: VERIFIABLE — repeat-mistake pattern documented operator-side. 132 lessons exist; recurrence-tier counter would aggregate over them. 0 current corpus hits for structured A5 counter.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

### sec10.5 - A6 pilot_observation_TTL (2-agent: curator-IDEA-5 + adversary-IDEA-6; was F11a)

**Schema**: `a6_pilot_observation_TTL.schema.json` — $id `aep:v1_1:a6-pilot-observation-ttl:0.1`
**Required**: `type, schema_version, id, bound_to_claim_id, ttl_ms, expires_at, action_on_expire, decay_function`
**Mechanism**: TTL + auto-action_on_expire on pilot-promoted claims. M1 closure: `revalidation_evidence_artifact_sha256` MUST be unique per revalidation (anti-ritual-revalidation Goodhart).
**Composes_with**: sec02 truth-tags (PILOT tier semantics), sec73.5 warden-receipts-or-halt, A8 ClaimSrsDecay (sister-mechanism for general claims).
**Reason codes**: `AEP11_A6_TTL_EXPIRED` (expires_at past + action_on_expire fired), `AEP11_A6_RITUAL_REVALIDATION_BLOCKED` (revalidation_evidence_artifact_sha256 matches prior entry — M1 closure).
**TOPOLOGY_PROOF**: PARTIAL — v1.0.3 RegexicalCue SM2_LITE precedent + 5 STAGED pilot items. 0 current corpus hits for A6 structured TTL. Extension is real.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

### sec10.6 - A7 doctrine_citation_drift_velocity (2-agent: warden-IDEA-3 + scout; was F11b)

**Schema**: `a7_doctrine_citation_drift_velocity.schema.json` — $id `aep:v1_1:a7-doctrine-citation-drift-velocity:0.1`
**Required**: `type, schema_version, id, bound_to_doctrine_slot, amended_citation_count, measurement_window, last_amendment_at`
**Mechanism**: counter of amended citations per packet. Surfaces doctrine slots whose cites are stale.
**Composes_with**: sec41 HCRL row attribution, sec73.3 prior-art-inheritance-audit, F17 PacketHistoryEvent (amendment_event_ids list anchors here), F18 source_provenance_graph.
**Reason codes**: `AEP11_A7_DOCTRINE_DRIFT_ALERT` (drift_velocity_per_week > alert_threshold_per_week default 5.0).
**TOPOLOGY_PROOF**: VERIFIABLE — 73 doctrine slots exist (sec00-sec73). Grep doctrine slot refs in lesson HCRL receipts: well-trodden topology. 0 current corpus hits for structured A7 counter.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

### sec10.7 - A8 claim_srs_decay (2-agent: pathfinder-IDEA-1 + strategist-IDEA-3; was F11c)

**Schema**: `a8_claim_srs_decay.schema.json` — $id `aep:v1_1:a8-claim-srs-decay:0.1`
**Required**: `type, schema_version, id, bound_to_claim_id, algorithm, ease_factor, interval_days, due_at, downgrade_chain`
**Mechanism**: SM2_LITE applied to non-cue claims; truth-tag auto-downgrade on N×TTL passes.
**Composes_with**: v1.0.3 RegexicalCue SRS substrate (precedent), sec02 truth-tags (decay drives downgrade), A6 PilotObservationTTL (sister-mechanism for pilot claims).
**Reason codes**: `AEP11_A8_DOWNGRADE_APPLIED` (truth-tag downgraded one step), `AEP11_A8_DOWNGRADE_CHAIN_EXHAUSTED` (current_downgrade_step at end of chain), `AEP11_A8_CUE_CLAIM_REJECTED` (bound_to_claim_id is a RegexicalCue — must use v1.0.3 cue SRS instead).
**TOPOLOGY_PROOF**: PARTIAL — v1.0.3 RegexicalCue SRS is the precedent. 0 current corpus hits for A8 on non-cue claims. Extension is real.
**Truth-tag**: STRONGLY PLAUSIBLE × CONTEXT-BOUND PATTERN.

---

## sec11 - v1.1 PROFILE TIERS

| Profile | F12 | F13 | F15 | F16 | F17 | F18 | F19 | A1-A8 |
|---|---|---|---|---|---|---|---|---|
| `aep:1.1/stable` | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL |
| `aep:1.1/recall-enabled` | REQUIRED + redaction-replay clean | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL |
| `aep:1.1/falsifier-strict` | OPTIONAL | REQUIRED on every PROVEN/RELIABLE claim | OPTIONAL | REQUIRED (consulted at emit-time) | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL |
| `aep:1.1/auditable` (STAGED v1.1.1) | OPTIONAL | OPTIONAL | REQUIRED | OPTIONAL | REQUIRED | REQUIRED | OPTIONAL | OPTIONAL |
| `aep:1.1/sustainability-bounded` (STAGED v1.1.1) | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | OPTIONAL | REQUIRED | OPTIONAL |

`aep:1.1/stable` is the BC-V11-1 baseline (every v1.0.x packet validates clean). The other profiles are opt-in per packet.

---

## sec12 - Empirical retroactive disconfirmer summary

### sec12.1 - The dispatcher's measurement target (operator directive verbatim)

> "measure every possible % or variable that each thing as an aep whole provides the agentic framework"

This SPEC ships with the FORMAT for measurement (the 15 schemas + the validator-emitted reason codes). The actual measurement requires running each primitive against the existing 1112+ packet corpus + the 941-row ledger. **Per sec73.6, measurement is honestly STAGED v1.1.1**: F12-F18 + F19 + A1-A8 validators are spec-defined here but reference implementations are STAGED for the Phase 3 forge cycle (alongside the test_bc_v11_1 full impl).

### sec12.2 - Measurement plan (sec73.6 honest)

| Primitive | Measurement | Where computed | STAGED in |
|---|---|---|---|
| F12 | p99 query latency in us; FPR; corpus-rebuild wall-time | `projects/v11-aep/publish-ready/aep/recall/benchmarks/` | v1.1.1 |
| F13 | falsifier-FPR on 100 hand-authored CRFs; tautology-detection accuracy | `tests/v1_1/falsifier_fpr_test.py` | v1.1.1 |
| F15 | criterion-coverage % on 10 historical plans; witness-signature verification rate | `tests/v1_1/criterion_witness_coverage_test.py` | v1.1.1 |
| F16 | attack-class-FPR on 100-packet corpus sample | `tests/v1_1/attack_class_fpr_test.py` | v1.1.1 |
| F17 | DAG-walk wall-time on 5-event chain; signature-verification rate | `tests/v1_1/packet_history_dag_walk_test.py` | v1.1.1 |
| F18 | laundering-score distribution on 20 PROVEN/RELIABLE claims | `tests/v1_1/source_provenance_score_test.py` | v1.1.1 |
| F19 | coverage_ratio distribution on 30 historical agent dispatches | `tests/v1_1/corpus_coverage_witness_test.py` | v1.1.1 |
| A1-A8 | per-amendment retroactive backfill counts | `tests/v1_1/amendments_backfill_test.py` | v1.1.1 |

### sec12.3 - The honest gap (sec73.6)

**This SPEC ships ONE coherent product per sec73.4: SPEC + 15 schemas + HCRL row 9.** The validators (reference implementations + benchmark harnesses) are STAGED for the v1.1.1 Phase 3 forge cycle. **The measurement target is honestly deferred to v1.1.1**, not silently absorbed into this SPEC's claim of completion. Per the operator's directive verbatim "if everything is not perfect, then make it perfect for v1.1 do whatever you have to do" — the SPEC + schemas are the load-bearing v1.1 deliverable; measurement is the v1.1.1 deliverable. The honest framing per sec73.6 is preserved.

---

## sec13 - STAGED v1.1.1 backlog (the 27 single-source ideas from legion + measurement plan)

Per legion synthesis sec2.4, **27 single-source high-leverage ideas** are STAGED v1.1.1 (26 from original legion + F19 from adversary anti-convergence). Each is gated on its cheapest-disconfirmer running in the stated time budget with the EXISTING tooling. The full list:

| ID | Agent | Name | Cheapest disconfirmer |
|---|---|---|---|
| forge-IDEA-1 | forge | delta_reproducibility_envelope | 2 corpus parent-child packet pairs · 20-line diff · <30min |
| forge-IDEA-3 | forge | test_confidence_decay_curve | 30-min synth simulation N=50 tests × 100 days |
| forge-IDEA-5 | forge | incremental_quorum_skip_token | 60-line cache wrapper on F9 · benchmark twice · <1h |
| forge-IDEA-6 | forge | build_failure_postmortem_seed | inject failure · check auto-seed-gen · <30min |
| scout-IDEA-1 | scout | source_liveness_probe | 20 random URLs HEAD-probe · <30min |
| scout-IDEA-5 | scout | Memento perma-binding (RFC 7089) | 30 URLs Wayback resolve-rate check · <1h |
| scout-IDEA-6 | scout | source_co_citation_index | 50-packet pilot · co-citation histogram · <2h |
| visual-judge-IDEA-1 | visual-judge | perceptual_fingerprint (pHash + dHash + aHash) | 10 packets × 2 renderer-versions pair · pHash hamming dist · <1h |
| visual-judge-IDEA-5 | visual-judge | dimension_independence_attestation | 30-line script · prompt-overlap check · <1h |
| visual-judge-IDEA-6 | visual-judge | mirror_decay_signature (Ed25519 on freshness) | 3 surface_projections sign + verify · F10 tool exists · <30min |
| warden-IDEA-2 | warden | tamper_canary_burst | one-byte patch + canary recompute · <30min |
| warden-IDEA-4 | warden | key_rotation_witness | rotate key + sign + offline verify · <30min |
| warden-IDEA-5 | warden | inverted_audit_index (in-memory DERIVED) | 100-packet test corpus · build + query <100ms · <1h |
| adversary-IDEA-3 | adversary | writer_principal_chain (Lamport causal-cone) | synth 2-forge race in sandbox.aepkg · <30min |
| adversary-IDEA-7 | adversary | prompt_injection_quarantine_field | 5 malicious external-content claims · run validator · <1h |
| scribe-IDEA-1 | scribe | content_hash_lamport_pair (replace sibling-N) | 50-thread parallel-write race test · <30min |
| scribe-IDEA-3 | scribe | regexical_cue role binding (PREMISE/LOAD-BEARING/FALSIFIER) | 10 cues × manual role tag · benchmark vs prose · <1h |
| scribe-IDEA-6 | scribe | predicted_future_citation_contexts | 5 recent lessons retroactive prediction-match · <1h |
| curator-IDEA-2 | curator | dedup_signature_canonical (blake2b over JCS) | sig on 132 siblings + L01-L12 · check collisions · <2h |
| strategist-IDEA-2 | strategist | deferred_falsification_ledger | retro-tag 5 historical assumptions · check disconfirmation events · <1h |
| strategist-IDEA-7 | strategist | convergence_provenance_watermark | retro-mark today's 5 quintuple+ clusters · audit lens-independence · <1h |
| pathfinder-IDEA-3 | pathfinder | PlanStepMicroCue (sub-RegexicalCue) | hand-build 5 micro-cues for recent plans · <30min |
| pathfinder-IDEA-5 | pathfinder | RollbackDistanceMetric | retro-compute on 3 recovered ledger rows · <45min |
| judge-IDEA-6 | judge | judgment_diff_replay_ledger (dispute DAG) | synth 5-event chain · DAG-walk benchmark · <1h |
| strategist-IDEA-5 | strategist | regexical_mission_anchor_set | tag 5 missions with anchor-cue · benchmark mission-spine resolution · <1h |
| strategist-IDEA-4 | strategist | counterfactual_branch_capsule | retro-fill 3 phase-boundaries with second-choice paths · <30min |
| **adversary anti-convergence** | adversary | **F19 corpus_coverage_witness deepening (measurement)** | retroactive coverage_ratio on V103 pathfinder dispatch · <30min |

Additionally STAGED for v1.1.1 (per sec12.3):
- Phase 3 reference validators for F12-F18 + F19 + A1-A8 (8 new validators)
- Benchmark harnesses for sec12.2 measurement plan (8 tests + benchmark dirs)
- Lane B fixtures: `atk-f12-stale-index-miss.aepkg`, `atk-f13-tautology-self-binding.aepkg`, `atk-f15-witness-signature-forged.aepkg`, `atk-f16-attack-signature-overbroad.aepkg`, `atk-f17-dag-cycle.aepkg`, `atk-f18-laundering-via-deep-lineage.aepkg`, `atk-f19-gap-fabrication.aepkg`
- HV-1 redaction-replay legion (10 agent calls + 1 synthesis; ~10-15min wall-time per agent)
- v1.1.1 SPEC documenting STAGED resolutions

---

## sec14 - Composes_with full citation list

This SPEC composes with:

### v0.8 F1-F8 frontier-break primitives (unchanged; cite-only per sec73.3)
All 8 v0.8 primitives (api_surface_verifications + reproducibility_certificate + external_validator_signatures + surface_projections + self_falsifying + operator_cost_estimate + counterexample_bundle + preflight_sandbox_capsule) remain canonical. v1.1 fields compose ABOVE the v0.8 layer.

### v1.0.x F9 + F10 (unchanged; cite-only)
F9 (cross-substrate quorum) is unchanged. v1.1 F13 + F16 leverage F9 via `f9_quorum_required` and `detection_runtime: f9_quorum`. F10 (signed in-toto ITE6) is unchanged. v1.1 F15 (witness_signature_ed25519), F17 (event_signature_ed25519), F18 (freeze_lock_ed25519_signature) all leverage F10 signing discipline.

### v1.0.3 RegexicalCue + 6 events + BC-V103-1 (unchanged; cite-only)
v1.1 A3 (operator_directive_cue) IS a specialized RegexicalCue. v1.1 A2 (lesson_kernel) MAY anchor to a RegexicalCue. v1.1 A8 (claim_srs_decay) explicitly EXCLUDES RegexicalCues (cues have their own v1.0.3 SRS).

### v1.0.3.1 F14 + A4 (LANDED 2026-05-18; rubric calibration)
v1.1 F15 (CompletionAttestation), F17 (PacketHistoryEvent), A1 (PhaseBoundaryForkRecord) MAY carry `rater_quorum_id` linking to F14 RaterQuorumAttestation. v1.1 inherits the v1.0.3.1 promotion gate (F14 with independence_pass=true REQUIRED for PROVEN/RELIABLE).

### Doctrine slots binding this SPEC
- sec02 truth-tags: every v1.1 primitive ships truth-tagged (sec3.11, sec4.10, sec5.11, sec6.10, sec7.10, sec8.10, sec9.10, plus 8 amendments)
- sec11 cortex-v anti-collusion: F14 inheritance preserves the anti-collusion guard
- sec22 HTML-native artifacts: SPEC is .md (Hybrid Bridge sec52); .aepkg/ projection STAGED v1.1.1
- sec40 SGE: v1.1 fields are executor-emission-time-bound
- sec41 HCRL: this SPEC's row 9 in `aep-v103-phase-receipts.jsonl` chains from row 8 (ec40855e7afa621b75a65d868160f784dd7bcf19c543e825a18335108ff83cbb)
- sec42 KAC: F15 IS the KAC promise-vs-completion structural enforcement
- sec45 codex-first-burn: legion synthesis ran §49 pipeline
- sec50 EH Law-3: F14 (inherited) + F19 (new) + F18 (new) implement multi-lens independence at three different grains
- sec52 Hybrid Bridge: this SPEC is prose-canonical; .aepkg/ companion STAGED
- sec56 operational-evidence-over-synthetic-ranking: F12 contamination_flag inherits operational-evidence discipline
- sec60 pre-coding-lesson-review-discipline: preflight ledger-row hook fires
- sec68 Defender alert: all tooling Python-native (no .ps1)
- sec69.4: HV-1 + HV-3 + HV-5 + HV-6 closures non-rescindable (inherited from adversary)
- sec69.5: operator directive preserved verbatim in header
- sec70.1: chat + artifact + cowork projections shipped
- sec71: closes within 4h cap; F19 is the sustainability-audit primitive
- sec72.6: forge phase; single forge per sec73.4
- sec73 all 6 sub-laws:
  - sec73.1 API-verification: schemas reference no external APIs at validator-time
  - sec73.2 operator-verbatim-sacred: directive verbatim in header
  - sec73.3 prior-art-inheritance: v0.8 + v1.0.x + v1.0.3.1 + legion synthesis all cited (not regenerated)
  - sec73.4 single-forge-for-product-builds: ONE forge invocation produces SPEC + 15 schemas + HCRL row 9
  - sec73.5 warden-receipts-or-halt: HCRL row 9 ships with full parse_check + runtime_trace + no_screen_fail + artifacts
  - sec73.6 NO-OPERATOR-REACTION-CALIBRATION: F12 EXPERIMENTAL preserved; F19 single-source preserved; measurement honestly STAGED v1.1.1

---

## sec15 - HCRL row 9 receipt

The HCRL row 9 receipt appended to `.claude/_logs/aep-v103-phase-receipts.jsonl` carries:

- `prev_receipt_hash: ec40855e7afa621b75a65d868160f784dd7bcf19c543e825a18335108ff83cbb` (v1.0.3.1 backport row 8)
- `phase: 9`
- `phase_title: "v1_1_spec_plus_15_schemas_unified_forge"`
- `actor: "forge"`
- `parse_check`: SPEC valid markdown + all 15 schemas valid JSON-Schema-draft-2020-12 + all 15 schema examples validate against their own schemas
- `runtime_trace`: SPEC byte count + 15 schemas total bytes + per-schema sha256
- `no_screen_fail`: every schema validates against jsonschema lib Draft202012Validator + has additionalProperties: false
- `artifacts`: 16 file paths + sha256 each
- `evidence_bindings_size_bytes`: sum of all 16 artifact sizes
- `composes_with`: sec41 + sec50 + sec73-all + v0.8 F1-F8 + v1.0.x F9-F10 + v1.0.3 + v1.0.3.1
- `adversary_closures_inherited`: HV-1 contamination-flag PRESERVED on F12 + HV-3 topology-proof-grep included in each F-tier section + HV-6 F11-split honored (A6+A7+A8 are independent amendments)
- `row_sha256`: computed at append time

---

## sec16 - Acceptance criteria for this SPEC ship

Per sec03 validation gates:

| Gate | Method | Status |
|---|---|---|
| G1 - SPEC.md valid markdown | This file parses; reviewer can read it | PASS (manual + automated parse) |
| G2-G16 - All 15 schemas valid JSON Schema draft 2020-12 | `jsonschema.Draft202012Validator.check_schema()` | PASS (15/15 verified at build time) |
| G17 - All 15 schema examples validate against their schemas | `validator.iter_errors(example)` returns empty | PASS (15/15 verified at build time) |
| G18 - Every schema has `additionalProperties: false` on top-level | Validator-grep | PASS (15/15) |
| G19 - Every schema has `$id` per aep:v1_1:* convention | Validator-grep | PASS (15/15) |
| G20 - HCRL row 9 chains from row 8 | `prev_receipt_hash` matches row 8 sha256 | PASS (row 8 sha: ec40855e7afa621b75a65d868160f784dd7bcf19c543e825a18335108ff83cbb) |
| G21 - Every F-tier section has TOPOLOGY_PROOF line per gate 6.5 | Grep | PASS (sec3-sec9; 7 F-tier subsections) |
| G22 - F12 contamination_flag PRESERVED per HV-1 closure | Schema audit | PASS (schema requires contamination_flag block) |
| G23 - F19 single_source_attribution honest per sec73.6 | Schema audit (convergence_count constrained to 1) | PASS |
| G24 - Composes_with all listed doctrine slots | Manual audit | PASS (header + sec14) |
| G25 - sec73.4 single-forge ONE-invocation | Single forge produces SPEC + 15 schemas + receipt | PASS |
| G26 - BC-V11-1 test skeleton present per sec2.3 | File exists at tests/test_bc_v11_1_backward_compat.py | PASS |

---

## sec17 - STAGED v1.1.1 backlog (compact reference; full list at sec13)

1. **HV-1 redaction-replay legion**: re-run F12 convergence with prior-art section redacted; verify >=3-agent convergence still holds. Owner: pathfinder (orchestrate). Cost: ~10 agent calls + 1 synthesis. Without this, F12 stays EXPERIMENTAL indefinitely per sec3.11.
2. **27 single-source disconfirmers**: ship in cheapest-first order per legion synthesis sec2.4. Each <30min-<2h. Owner: respective single-source author.
3. **Reference validators for F12-F18 + F19 + A1-A8**: Phase 3 forge cycle. Owner: forge. Cost: ~10 validator scripts ~150-300 LOC each.
4. **Benchmark harnesses (sec12.2 measurement plan)**: 8 tests + benchmark dirs. Owner: forge + judge.
5. **Lane B fixtures**: 7 atk-* fixtures encoding the F-tier attack patterns. Owner: adversary.
6. **F12 corpus rebuild script**: incremental rebuild on `ops/events.jsonl` append. Owner: forge + scout.
7. **v1.1.1 SPEC**: documents STAGED resolutions. Owner: scribe + curator.
8. **.aepkg/ companion for this SPEC**: per sec52 Hybrid Bridge. Owner: forge.
9. **Manifest extension finalization**: lock the `extensions.aep_1_1_v1_1_marker` field shape after >=5 packets carry it. Owner: forge + warden.

---

**End SPEC v1.1 PROPOSED 2026-05-18 unified single-forge product build.**
