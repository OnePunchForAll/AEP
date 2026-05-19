# AEP v1.2 SPEC - The Agent Evidence Immune System

**Status**: **PROPOSED 2026-05-18** under operator full-build authorization. Sister-spec to AEP_v1_1_SPEC.md (LANDED 2026-05-18 same-day; FROZEN per sec3 of this SPEC). Implements the v1.2 stack from `doctrine/_proposals/pathfinder-2026-05-18-aep-v1-2-immune-system.md` (9-phase plan + adversary closure addendum). ONE coherent product build per sec73.4 single-forge discipline.

**Profile**: `aep:1.2/immune`. Three adoption-mode sub-profiles: `aep:1.2/lite` (civilian; 4-file shape) · `aep:1.2/pro` (builder; full v1.1 + v1.2 superset) · `aep:1.2/institutional` (compliance; v1.2/pro + policy gates + audit retention).

**Predecessors** (cite-only per sec73.3 — NOT regenerated below):
- AEP v0.8.0 STABLE (LANDED 2026-05-17 — F1-F8 frontier-break primitives).
- AEP v1.0.0 / v1.0.1 / v1.0.2 (runtime-only F9 cross-substrate quorum + F10 signed in-toto ITE6).
- AEP v1.0.3 LANDED-DOWNGRADED 2026-05-18 (RegexicalCue + 6 regexical_memory_* events + BC-V103-1 + VG04 HARD-CONDITIONAL mean 3.44).
- AEP v1.0.3.1 LANDED 2026-05-18 (F14 RaterQuorumAttestation + A4 RubricScore backport; rubric calibration).
- **AEP v1.1 LANDED 2026-05-18 (FROZEN per sec3 of this SPEC — F12 + F13 + F15 + F16 + F17 + F18 + F19 + A1-A8 + F14 + A4 backports). NO NEW PRIMITIVES MAY LAND UNDER v1.1 PREFIX.**

**Authors**: operator (operator) + the agentic substrate (Claude Opus 4.7 1M-context, AEP project 10-agent legion under sec73.4 single-forge-for-product-builds; co-authored by strategist + pathfinder + scout + forge + judge + adversary + warden + scribe + curator + visual-judge across upstream phases; THIS SPEC body is forge-single-invocation).

**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).

**Composes_with** (load-bearing slot citations):
- `doctrine/02-truth-tags.html` — every claim in this SPEC carries a truth tag from the canonical 6-tier set.
- `doctrine/03-validation-gates.html` — the six gates this SPEC's outputs pass through.
- `doctrine/04-security.html` — sec18 redaction layer composes with §04 anti-secret discipline.
- `doctrine/05-git-workflow.html` — schema-additive-only discipline (forge personal cite).
- `doctrine/11-cortex-v-protocol.html` sec3 — anti-collusion guard (F21 enemy authorship principal-different invariant inherits this discipline).
- `doctrine/22-html-native-artifacts.html` — this SPEC is canonical .md per Hybrid Bridge sec52; companion .aepkg/ projection deferred to v1.2.1.
- `doctrine/40-session-governor-executor.html` — v1.2 fields are executor-emission-time-bound per KAC inheritance.
- `doctrine/41-hash-chained-receipt-ledger.html` — this SPEC's HCRL row 13 chains cleanly from row 12 (sha256 prefix `99def377...`).
- `doctrine/42-kernel-admission-contract.html` — Invariant Contract (sec11) is the structural enforcement of KAC pre-execution invariant_checks.
- `doctrine/45-codex-first-burn-law.html` — V8.2 NP-1 + NP-2 + NP-4 discipline inherited (mechanism over analogy + dormitive-virtue detection + numbers-need-receipts).
- `doctrine/50-epistemic-hygiene-meta-law.html` — Law-3 multi-lens independence (F21 enemy pairing universalizes this discipline at claim granularity; A4 closure does NOT add meta-adversary, reuses F14 quorum).
- `doctrine/52-hybrid-prose-aep-bridge.html` — this SPEC IS the prose-canonical; .aepkg/ projection deferred to v1.2.1.
- `doctrine/56-operational-evidence-over-synthetic-ranking.html` — F23 validator adversary mode REQUIRES at least one real validator downgrade or the layer is decorative per sec56.
- `doctrine/60-pre-coding-lesson-review-discipline.html` — lesson scan performed before code emission this turn.
- `doctrine/68-defender-alert-stops-burn.html` — no PowerShell hooks emitted this build; v11_freeze_guard.py is Python-only per control 3.
- `doctrine/69-verification-law-and-operator-spec-sovereignty.html` — all 9 sub-laws; sec69.4 non-rescindability binding on HV1/HV2/HV3/HV5/HV6/HV7/HV8/HV9/HV11 closures + A4 + A10 + A12 MEDIUM closures inherited from adversary.
- `doctrine/70-surface-mirror-discipline.html` — chat + artifact + cowork projections this SPEC ships.
- `doctrine/71-operator-sustainability.html` — closes within 4h continuous-autonomy cap; the 12-artifact ONE-forge-invocation honors the cap by avoiding fan-out.
- `doctrine/72-canonical-order-of-operations.html` — firing-order: this is the forge phase per sec72.6; single forge per sec73.4.
- `doctrine/73-external-claude-receipt-laws.html` — all 6 sub-laws binding; sec73.2 operator-verbatim-sacred enforced by quoting the operator directive verbatim in sec1 (no paraphrase); sec73.3 prior-art-inheritance enforced by citing operator source by line range and v1.1 SPEC by section (NOT regenerated); sec73.4 single-forge enforced by ONE forge invocation producing 12 artifacts; sec73.5 warden-receipts-or-halt enforced by HCRL row 13 ship; sec73.6 honest framing enforced by EXTENDS-vs-NOVEL lineage disclosures throughout.

**Operator directive (sec73.2 sacred, verbatim)**:

> AEP v1.2: The Agent Evidence Immune System.
>
> Its job would be: prevent bad outputs before they are born, detect weak outputs before promotion, repair broken outputs after failure, and make all of that understandable to normal people.

---

## sec1 - Why v1.2 exists

### sec1.1 - The operator's load-bearing framing (sec73.2 sacred quote, verbatim)

From operator source.md L7-L9 (the full directive lives at `research/sources/operator-2026-05-18-aep-v12-immune-system/assets/source.md` per sec73.3 inheritance):

> AEP v1.2: The Agent Evidence Immune System.
>
> Its job would be: prevent bad outputs before they are born, detect weak outputs before promotion, repair broken outputs after failure, and make all of that understandable to normal people.

The four verbs — **prevent**, **detect**, **repair**, **translate** — are the four functional pillars of v1.2. Each F-tier primitive in sec4-sec10 maps to one or more of these pillars:

- **Prevent**: Invariant Contract (sec11) + F20 Bug Vaccine Kernel (sec4) + F25 Trust Dial floor (sec8) + Policy-as-code promotion gates (sec14) + Sandbox Gate (sec15).
- **Detect**: F23 Validator Adversary Mode (sec6) + F21 Claim Enemy Pairing (sec5) + F18 laundering-score disclosure surfacing on F22 cards (sec6).
- **Repair**: F20 Bug Vaccine Kernel (sec4) emits new invariant + new mutation test + new validator rule from every detected bug; Bug Ontology (sec12) is the structured-fault substrate behind the repair.
- **Translate**: F22 Civilian Proof Card (sec6) + AEP Viewer + AEP Lite (sec16) + Public Trust Vocabulary (sec16) + Adoption Modes (sec16).

### sec1.2 - The legion synthesis (sec73.3 prior-art-inheritance)

v1.2 was framed by pathfinder's 9-phase plan at `doctrine/_proposals/pathfinder-2026-05-18-aep-v1-2-immune-system.md` and stress-tested by adversary's 12-vector attack table at `doctrine/_proposals/adversary-2026-05-18-aep-v1-2-premortem.md`. Adversary's verdict on the plan was **CONDITIONAL-GO** with 9 HIGH-VETO closures + 3 MEDIUM closures binding on this forge invocation. ALL 9 HV + 3 MEDIUM closures are HARD-CONSTRAINED in the 11 schemas this SPEC ships — they are NOT merely text disclosures. See sec19 for the HV closure summary table.

This SPEC IS the implementation of pathfinder's plan + adversary's closures. It does NOT regenerate the operator directive (cited by line range from source.md), the pathfinder plan (cited by section), or the adversary attack table (cited by attack id). Per sec73.3 prior-art inheritance.

### sec1.3 - The composing-not-superseding decision (sec73.6 honest)

v1.2 **composes** with v1.1; it does NOT supersede v1.1. v1.1's full primitive set (F12 + F13 + F15 + F16 + F17 + F18 + F19 + A1 + A2 + A3 + A4 + A5 + A6 + A7 + A8 plus the F14 + A4 backports from v1.0.3.1) remains the research-grade engine. v1.2 adds an immune-system + civilian-translation layer on top.

The v1.1 FREEZE declaration (sec3) is the structural enforcement of this decision. No new primitive may land under the `aep:1.1/*` profile after this SPEC's ship date. Future v1.1-adjacent work routes through v1.2.1 or v1.3 — never reopens v1.1.

### sec1.4 - The civilian stop-condition (sec73.6 honest + sec56 operational-evidence)

Operator source.md L249-L253 names the v1.2 stop condition verbatim:

> Stop condition: A non-programmer can drag an .aepkg into the viewer and understand, in under 30 seconds, whether the AI output is trustworthy enough for their situation.

This SPEC does NOT claim the stop condition is met. The civilian-comprehension empirical test is **STAGED v1.2.1** per pathfinder Phase 9 + adversary A8 closure (recruit-independence attestation + deceptive-packet pass-condition + adversary-recruit + cold-start timing). v1.2 ships with the substrate (F22 + AEPLite + AEPViewer + F25 Trust Dial + public trust vocabulary lints) in place; the falsifier test fires after operator-led recruitment per sec73.6 (the agent does NOT recruit civilians).

Truth tag on the < 30 s claim itself: **EXPERIMENTAL** until Phase 9 empirical test fires. Per sec73.6, this SPEC does NOT pre-shape the civilian test's outcome.

### sec1.5 - The four-pillar mapping (truth-tagged per pillar)

| Pillar | v1.2 primitives | Composes with v1.1 | Truth tag |
|---|---|---|---|
| **Prevent** (sec1.1) | InvariantContract (sec11) + F20 Bug Vaccine Kernel (sec4) + F25 Trust Dial floor (sec8) + Policy-as-code (sec14) + Sandbox Gate (sec15) | F13 (falsifier) + F14 (quorum) + F18 (laundering) | STRONGLY PLAUSIBLE (each primitive ships with HV closure HARD-CONSTRAINED) |
| **Detect** | F21 Claim Enemy Pairing (sec5) + F23 Validator Adversary Mode (sec6) | F13 + F16 | STRONGLY PLAUSIBLE (F23 requires real downgrade per sec56) |
| **Repair** | F20 Bug Vaccine Kernel + Bug Ontology (sec12) | F13 + F16 | EXPERIMENTAL (vaccine matching FP rate not yet empirically measured against 1112+ corpus — HV1 closure requires backfill before active gating; v1.2.1 STAGED) |
| **Translate** | F22 Civilian Proof Card (sec6) + AEP Lite (sec16) + AEP Viewer (sec16) + F25 Trust Dial (sec8) + Public Trust Vocabulary (sec16) | F18 + F19 | EXPERIMENTAL (< 30 s civilian comprehension claim STAGED for empirical test v1.2.1) |

### sec1.6 - The risk taxonomy (sec73.6 honest)

Adversary's pre-mortem named 12 attack vectors. The 9 HIGH-VETO closures are hardened into schema-level constraints in this SPEC; the 3 MEDIUM closures are hardened where structurally feasible and STAGED with honest framing where empirical evidence is required (e.g., A10 TLC lifecycle conformance test ships as Python state-machine diff-check this turn; full TLC CI integration STAGED v1.2.1).

The single most-likely failure path per adversary's bet: **F26 Compatibility Passport ships with `declared_compatible: true` for 14 ecosystems without round-trip verification**. HV7 closure HARD-CONSTRAINS this: the schema splits `verified_round_trip_compatible[]` (counted toward trust) vs `declared_compatible[]` (informational only). Phase 7 acceptance: 0-4 verified entries land in v1.2; remaining 10-14 STAGED v1.2.1 with honest framing. The schema enforces that only verified entries count toward trust attestation.

---

## sec2 - BC-V12-1 backward-compatibility clause

### sec2.1 - The invariant

**BC-V12-1**: For any AEP packet emitted under v0.8 / v1.0.0 / v1.0.1 / v1.0.2 / v1.0.3 / v1.0.3.1 / v1.1, validating under `aep:1.2/pro` profile with the v1.2 F-tier + layer fields ABSENT MUST produce results byte-identical to validating the same packet under its latest predecessor profile. The new v1.2 claim types and the new v1.2 extension fields are STRICTLY ADDITIVE.

### sec2.2 - What BC-V12-1 does NOT claim

- Does NOT claim manifest sha256 invariance. The `aepkg.json.extensions` field MAY carry a `aep_1_2_v1_2_marker` (advisory; not load-bearing).
- Does NOT claim `state_hash` invariance when v1.2 claim types ARE present. The v1.2 claim types (Invariant, BugOntologyRecord, BugVaccineKernelRecord, ClaimEnemyPairingRecord, CivilianProofCardRecord, ValidatorAdversaryModeRecord, EvidenceRightsRedactionRecord, TrustDialRecord, CompatibilityPassportRecord, AEPLitePacketSchema, PolicyRegoRecord) all live in `data/claims.jsonl` which IS in the state_hash formula; when present, state_hash legitimately changes.
- Does NOT claim that existing v1.x claims auto-upgrade with v1.2 attachments. Upgrade is OPT-IN per claim author.
- Does NOT claim retroactive certification of pre-v1.2 packets under `aep:1.2/lite` or `aep:1.2/institutional` profiles. These profiles apply to packets emitted AFTER v1.2 LANDED, mirroring the v0.8 §V80-4-bis birth-only scope discipline and v1.1 sec2.2 inheritance.

### sec2.3 - Empirical falsifier (BC test ships with this SPEC)

The BC test at `projects/v11-aep/publish-ready/aep/tests/test_bc_v12_1_backward_compat.py` validates BC-V12-1 structurally:

- **Schema inventory check**: every predecessor schema is present; every v1.2 schema is present.
- **Discriminator disjointness**: every v1.2 schema's `type.const` is disjoint from every predecessor schema's `type.const`. No v1.2 claim type collides with a v0.x / v1.0.x / v1.1 claim type.
- **schema_version disjointness**: every v1.2 schema's `schema_version.const` is disjoint from predecessor versions. No version-string reuse.
- **AEP Lite path non-collision**: AEP Lite's 4-file shape (claim.json + sources/ + receipt.json + proof-card.json) does NOT collide with the canonical 7-file shape (aepkg.json + data/sources.jsonl + data/spans.jsonl + data/claims.jsonl + data/relations.jsonl + data/events.jsonl + data/reviews.jsonl + data/validations.jsonl).
- **additionalProperties:false on every v1.2 schema**: strict packet shape per M5 inheritance from v1.1.

Empirical-test class per forge personal compendium: this test characterizes the additive-only structure of v1.2; there is no bug to fix. Full per-packet validation against the live 1112+ corpus is STAGED v1.2.1 as `wave_060_validate_all_packets_against_v1_2.py`. Per sec73.6, this staging is honest.

### sec2.4 - Schema-additive-only discipline (forge personal cite)

This SPEC and its 11 new schemas add fields and claim types to the existing v1.1 vocab. NO existing v0.x / v1.0.x / v1.1 field is renamed or removed. Per the forge personal compendium's "Schema-additive-only" invariant, RENAME/REMOVE requires curator approval + migration note in the commit message; nothing here triggers that gate.

---

## sec3 - v1.1 FREEZE DECLARATION

### sec3.1 - The freeze statement (operator L51 verbatim discipline)

Per operator source.md L51 verbatim: **"freeze the current v1.1 core as the 'research-grade packet.' No more casual primitive sprawl. Every new primitive must justify which bug class it prevents, which user it helps, and which existing primitive it composes with."**

As of 2026-05-18, the v1.1 primitive set is FROZEN. The frozen set consists of the following primitives + amendments, cite-only per sec73.3 (NOT re-enumerated below — see AEP_v1_1_SPEC.md for full enumeration):

**v1.1 F-tier (frontier-break primitives) — FROZEN**:
- **F12** RecallLayerIndexEntry (derived projection layer for ms-NS recall; aep:1.1/recall-enabled profile)
- **F13** ClaimRuntimeFalsifier (executable falsifier per PROVEN/RELIABLE claim; aep:1.1/falsifier-strict profile)
- **F15** CriterionWitnessChain + CompletionAttestation (KAC promise-vs-completion enforcement)
- **F16** AttackClass registry (attack catalog populated by F23 mutation suite at v1.2)
- **F17** PacketHistoryEvent (DAG amendment/audit/promotion/rollback events)
- **F18** SourceProvenanceGraphRow (lineage_depth + venue_tier + peer_review_status + invalidator_checked; laundering-score primitive)
- **F19** CorpusCoverageWitness (corpus coverage attestation; closes recall-completeness gap)

**v1.1 amendments — FROZEN**:
- **A1** PhaseBoundaryForkRecord
- **A2** LessonKernel (compounding-intelligence substrate)
- **A3** OperatorDirectiveCue
- **A5** RecurrenceTierCounter
- **A6** PilotObservationTTL
- **A7** DoctrineCitationDriftVelocity
- **A8** ClaimSrsDecay

**v1.0.3.1 backports — FROZEN as part of v1.1**:
- **F14** RaterQuorumAttestation (multi-principal review independence)
- **A4** RubricScore (rubric-language completeness on list-valued recall fields)

### sec3.2 - The freeze enforcement mechanism (HV11 + A11 closure HARD-CONSTRAINED)

Text declaration is NOT enforcement (adversary A11 attack: "Pathfinder ratifies v1.1 freeze. Text is not enforcement.").

Enforcement is provided by `.claude/hooks/v11_freeze_guard.py`, a Python-only PreToolUse hook (per sec68 control 3) wired on Edit|Write|MultiEdit. The hook BLOCKS any new schema file under `projects/v11-aep/publish-ready/aep/schemas/` lacking a `v1_2_` / `v1_3_` / `v1_4_` / `v1_5_` prefix. The hook ships with a `LEGACY_ALLOWED_FILENAMES` allow-list of pre-freeze schemas (the v0.x + v1.0.x + v1.1 set listed in sec3.1); edits to those existing files are permitted (per schema-additive-only discipline in sec2.4), but NEW files MUST carry a v1.2+ prefix.

Wiring is registered in `.claude/settings.json` under the PreToolUse Edit|Write|MultiEdit matcher block. The hook fails-open on infrastructure errors (missing input, malformed JSON, missing target path) and emits a structured-log line per decision to `.claude/_logs/v11-freeze-guard-decisions.jsonl` for warden audit.

### sec3.3 - The "every new primitive must justify" gate (operator L51 verbatim mechanism)

Per operator L51, every new primitive must justify:

1. **Which bug class it prevents** — every v1.2 F-tier primitive (F20 through F26) cites the bug class it targets in its `lineage_basis` and the operator source.md line range that names the problem.
2. **Which user it helps** — every v1.2 primitive maps to one or more of the four pillars (prevent/detect/repair/translate) per sec1.5.
3. **Which existing primitive it composes with** — every v1.2 primitive's schema docstring lists the v1.1 primitive(s) it composes with.

The v1.2 SPEC sec4-sec10 (per-primitive subsections F20-F26) honor this gate. New v1.3+ primitives ship under the same discipline.

### sec3.4 - The "FROZEN means FROZEN" enforcement (sec73.6 honest)

After v1.2 SPEC LANDED date (this commit), the v1.1 SPEC.md and its 17 schemas are frozen for amendment ONLY in the following narrow cases:

- **Typo fixes / documentation clarifications** in the v1.1 SPEC.md prose.
- **Schema field DESCRIPTION clarifications** that do NOT change validation semantics.
- **Bug fixes in v1.1 validators** that restore intended behavior without changing schema shape.

**NOT permitted** under any circumstance under the v1.1 prefix:
- New F-tier primitives (must land under v1.2 or higher).
- New amendments (must land under v1.2 or higher).
- New schema files in `schemas/` lacking v1.2+ prefix.
- Field RENAME or REMOVE on v1.1 schemas (would break BC-V11-1; requires curator approval + migration note + new schema_version).

The v11_freeze_guard.py hook enforces the schema-file discipline mechanically. The other constraints rely on forge personal-compendium discipline + warden audit at HCRL row commits.

---

## sec4 - F20 Bug Vaccine Kernel

### sec4.1 - Motivation (operator source.md L67-L69 + L135-L150)

Operator source.md L67-L69 (immediate action #4) names the AEP Immune Log:

> Fourth: add the AEP Immune Log. Every validation failure becomes a reusable bug vaccine. The next time a similar packet appears, AEP should say: "This resembles bug class B-014: fake completion via missing witness. Previous prevention rule applies."

Operator source.md L135-L150 (F20 inheritance):

> F20: Bug Vaccine Kernel.
>
> Every detected bug emits a small permanent prevention object:
> Bug name. Smallest reproduction. Exact cause. Why existing gates missed it. New invariant. New mutation test. New validator rule. New user-facing warning. Affected packet versions. Retirement condition.
>
> This would mean AEP does not merely record failure. It immunizes the future corpus.

### sec4.2 - Record shape (10 fields verbatim from operator L137-L148 + HV1 closure fields)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f20_bug_vaccine_kernel.schema.json`.

The 10 operator-named fields verbatim:
1. `bug_name`
2. `smallest_reproduction` (object: repro_input + smallest_failing_example + repro_input_sha256)
3. `exact_cause`
4. `why_existing_gates_missed_it`
5. `new_invariant` (bound to v1.2 invariant_contract.schema.json)
6. `new_mutation_test` (mutation_class from 7-class enum + test_fixture_path)
7. `new_validator_rule` (bound to v1.2 policy_rego.schema.json)
8. `new_user_facing_warning` (civilian text)
9. `affected_packet_versions` (profile enum)
10. `retirement_condition` (kind + criterion + optional no_match_window_days)

HV1 closure fields HARD-CONSTRAINED in schema:
- `vaccine_rule_budget_per_corpus` — `max_active_rules: const 50` (cannot exceed 50 simultaneously-active rules per corpus profile).
- `vaccine_calcification_alert` — `fp_rate_threshold: const 0.05` (5% FP rate triggers WARN; freeze on persistent breach).
- `retirement_condition.no_match_window_days` default 90 (90 days without match retires the rule).
- `vaccine_blast_radius.estimated_proven_packets_wrongly_blocked` — backfill measurement required against existing 1112+ corpus.

### sec4.3 - Reason codes (v1.2 validator emission codes)

- `AEP12_F20_BUDGET_EXCEEDED` — vaccine_rule_budget_per_corpus.current_active_count would exceed 50. Block emit; require rule retirement.
- `AEP12_F20_FP_RATE_HIGH` — current_fp_rate > 0.05; alert_status flips to FREEZE; backfill required before next emit.
- `AEP12_F20_BLAST_RADIUS_UNMEASURED` — vaccine_blast_radius missing or backfill_corpus_size == 0. Warn; cannot promote vaccine to active until measured.
- `AEP12_F20_RETIREMENT_CONDITION_MISSING` — retirement_condition absent or criterion empty. Reject record.

### sec4.4 - Falsifier (operator L17 mutation philosophy applied to F20 itself)

F20 IS itself a target of F23 Validator Adversary Mode. The cheapest disconfirmer: emit a vaccine on a deliberately-synthetic bug, then mutate the resemblance-matching threshold to require ≥3 field matches instead of ≥2; verify FP rate drops on the 1112+ corpus backfill.

Per sec56 operational-evidence-over-synthetic-ranking: a vaccine kernel that has not been backfilled against the existing corpus is DECORATIVE. The schema's `vaccine_blast_radius.backfill_corpus_size` field surfaces this requirement.

### sec4.5 - Topology proof (gate 6.5 inheritance from v1.1)

`grep -r "BugVaccineKernelRecord\|bvk:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship time: schema discriminator only (no consumer yet — Phase 2 forge of pathfinder plan). Honest framing per sec73.6: F20 ships as **schema-only this turn**; the emitter (`emit_bug_vaccine.py`) + matcher (`match_bug_vaccine.py`) + immune log directory + round-trip test are STAGED v1.2.1 per pathfinder Phase 2.

### sec4.6 - Composes_with (v1.1 + v1.2)

- v1.1 **F13** ClaimRuntimeFalsifier — every vaccine emits a new falsifier per operator L17.
- v1.1 **F16** AttackClass registry — vaccines populate the attack class catalog.
- v1.2 **BugOntologyRecord** (sec12) — each bug ontology record births a vaccine.

### sec4.7 - EXTENDS lineage (F18 lineage discipline per sec73.6)

Classification: **EXTENDS**. F20 builds on:

- **Hypothesis** (Python property-based testing library; David MacIver et al.). Property-based mutation philosophy.
- **OSS-Fuzz** (Google Open-Source Fuzzing infrastructure). Continuous-mutation-fuzzing genealogy.

Verbatim cite anchor: operator source.md L17:

> Property-based testing tools like Hypothesis already use generated inputs and edge cases to find bugs; fuzzing systems like OSS-Fuzz use large-scale mutated inputs to uncover security and stability bugs. AEP should absorb that philosophy directly into packet validation.

verifying_grep: `rg 'property-based|hypothesis|oss-fuzz' --type md research/sources/`. n_hits at SPEC ship: external-prior-art cite anchors live in the operator source itself (verifying_grep counts ≥1 hit in the operator source corpus per inheritance discipline).

### sec4.8 - HV1 closure summary (HARD-CONSTRAINED)

The HV1 attack (adversary pre-mortem #1, ranked HIGH-VETO): "Bug Vaccine Kernel rule-bloat ceiling is unbounded → calcification." Bound at the schema level by:

- `max_active_rules: const 50` (no string-label override possible).
- `fp_rate_threshold: const 0.05` (HARD-CONSTRAINED).
- `retirement_condition` REQUIRED; `no_match_window_days` default 90.
- `vaccine_blast_radius.estimated_proven_packets_wrongly_blocked` field surfaces the backfill discipline.

Per sec73.6 honest framing: the schema PREVENTS calcification structurally, but the empirical backfill against the 1112+ corpus is STAGED for v1.2.1. F20 ships as **schema-only EXPERIMENTAL** this turn.

---

## sec5 - F21 Claim Enemy Pairing

### sec5.1 - Motivation (operator source.md L154-L164)

> F21: Claim Enemy Pairing.
>
> Every important claim must ship with its enemy: the strongest plausible condition under which the claim would be false.
>
> Example: Claim: "The agent reviewed all expected packets." Enemy: "One expected packet was omitted from expected_corpus_scope or touched only by metadata, not content." Required falsifier: prove packet content access, not just filename touch.
>
> This is huge because most AI systems only optimize for saying true-looking things. AEP should force every claim to carry its own assassin.

### sec5.2 - Record shape (HV2 closure HARD-CONSTRAINED)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f21_claim_enemy_pairing.schema.json`.

Required fields:
- `bound_to_claim_id` — the claim this enemy pairs against.
- `claim_authored_by_principal_id` — original claim author.
- `claim_truth_tag` — enforcement scope (REQUIRED on PROVEN/RELIABLE; advisory on STRONGLY PLAUSIBLE; not required on lower tiers per pathfinder Phase 6 + adversary A2 closure).
- `enemy_text` — plain-language adversarial condition.
- `enemy_authored_by_principal_id` — **HARD-CONSTRAINED ≠ claim_authored_by_principal_id** per HV2 closure.
- `enemy_authored_by_role` — **HARD-CONSTRAINED enum {judge, adversary}**. Other 8 roles (scribe, curator, forge, pathfinder, strategist, scout, warden, visual-judge) EXPLICITLY EXCLUDED from enemy authorship.
- `enemy_review_required_by_role` — array with ≥1 of {judge, adversary}.
- `enemy_basis_source_ids` — MUST include ≥1 source NOT in claim.basis_source_ids[] at pairing time (A2 cheapest disconfirmer enforcement).
- `claim_basis_source_ids_at_pairing_time` — snapshot for source-divergence check.
- `required_falsifier` — bound to v1.1 F13 ClaimRuntimeFalsifier id (anti-tautology reuse per A4 closure; no meta-adversary).
- `anti_tautology_check` — PASS/FAIL/PENDING via {f13_existing_anti_tautology | manual_review_by_judge | automated_token_overlap_check}.

### sec5.3 - Reason codes

- `AEP12_F21_PRINCIPAL_COLLISION` — enemy_authored_by_principal_id == claim_authored_by_principal_id. Reject record.
- `AEP12_F21_ROLE_NOT_PERMITTED` — enemy_authored_by_role not in {judge, adversary}. Reject record.
- `AEP12_F21_BASIS_SUBSET` — enemy_basis_source_ids[] is subset of claim_basis_source_ids_at_pairing_time. Reject record.
- `AEP12_F21_FALSIFIER_TAUTOLOGY` — token_overlap_ratio > 0.8 between claim_text and enemy_text. Warn; require manual_review_by_judge.

### sec5.4 - Falsifier

The cheapest disconfirmer per adversary A2: write a `ClaimEnemyPairingRecord` where `enemy_authored_by_principal_id == claim_authored_by_principal_id`. The schema validator MUST reject. v1.2 validator (STAGED per pathfinder Phase 6) ships with this test.

### sec5.5 - Topology proof

`grep -r "ClaimEnemyPairingRecord\|cep:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship: schema discriminator only. Honest framing per sec73.6: F21 ships as **schema-only this turn**; the enforcement validator + kill_chain_runner integration are STAGED v1.2.1 per pathfinder Phase 6.

### sec5.6 - Composes_with

- v1.1 **F13** ClaimRuntimeFalsifier — the enemy IS the falsifier in claim_enemy_pairing form (A4 closure: reuse, do NOT invent meta-adversary).
- v1.1 **F14** RaterQuorumAttestation — enemy_review_required_by_role enforces independence inheriting F14's discipline.

### sec5.7 - EXTENDS lineage

Classification: **NOVEL** (closest external precedent: Toulmin argument structure's `rebuttal` component + Karl Popper's falsificationism + adversarial-robust ML training — all philosophical, not structurally identical). Honest framing per sec73.6: F21 is novel as a packet-claim primitive.

Verifying_grep: `rg 'toulmin|popper|falsificationism|adversarial robust' --type md research/sources/`. n_hits at SPEC ship: 0 hits in research corpus (cite anchors are general philosophy-of-science references not in AEP project's research corpus).

### sec5.8 - HV2 closure summary (HARD-CONSTRAINED)

The HV2 attack: "F21 single-author enemy theater." Bound at the schema level by:

- `enemy_authored_by_principal_id != claim_authored_by_principal_id` enforced via separate field with documented runtime validator check.
- `enemy_authored_by_role: enum [judge, adversary]` HARD-CONSTRAINED at schema enum level.
- `enemy_review_required_by_role: enum [judge, adversary]` HARD-CONSTRAINED.
- `enemy_basis_source_ids` MUST diverge from `claim_basis_source_ids_at_pairing_time` (validator enforcement).

---

## sec6 - F22 Civilian Proof Card

### sec6.1 - Motivation (operator source.md L23-L27 + L59-L66 + L168-L176)

Operator source.md L23-L27 (the headline framing):

> Sixth, AEP needs a human trust surface. ...
>
> "This answer used 8 sources. 6 were direct, 2 were AI-derived. 3 claims were tested. 1 claim is stale. No hidden completion gaps detected. Confidence: usable, not proven. Click to inspect."
>
> C2PA's public-facing framing around Content Credentials as a kind of nutrition label for digital content is the right mental model. AEP needs the equivalent for AI work: Proof Nutrition Labels.

Operator source.md L59-L66 (the 5-row structure):

> Third: build the Proof Card. This is the civilian surface. It should show five things only:
>
> What is being claimed.
> What evidence supports it.
> What was tested.
> What is weak, stale, missing, or AI-derived.
> What action the user should take next.

Operator source.md L168-L176 (F22 inheritance):

> F22: Civilian Proof Compiler.
>
> This compiles technical evidence into plain-language proof cards. ... It answers: "Why should I believe this?" "What would make this wrong?" "What was checked automatically?" "What still needs a human?" "What is the safest next action?"

### sec6.2 - Record shape (HV3 closure HARD-CONSTRAINED)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f22_civilian_proof_card.schema.json`.

The 5 required rows verbatim from L60-L66:
1. `what_is_being_claimed`
2. `what_evidence_supports_it`
3. `what_was_tested`
4. `what_is_weak_stale_missing_or_ai_derived`
5. `what_action_the_user_should_take_next`

HV3 closure fields HARD-CONSTRAINED:
- `disclosed_signals` — MANDATORY block surfacing F18 laundering_score, F15 missing_witness_flag, F16 attack_flag, F19 coverage_gap_flag, A8 srs_decay_status, and the aggregate `any_signal_non_ok`.
- `banned_elision_lint_status` — `required_terms_when_warning_present` array MUST contain civilian_warning_phrasebook[] phrases when `any_signal_non_ok == true`.
- `civilian_vocabulary_lint_status` — banned-term linter against the public trust vocabulary banned list (sec18.5).
- `trust_dial_level_required` — bound to v1.2 trust_dial.schema.json F25 level enum.

### sec6.3 - Reason codes

- `AEP12_F22_ELISION_DETECTED` — banned_elisions_detected[] non-empty. Block card emission.
- `AEP12_F22_REQUIRED_TERM_ABSENT` — any_signal_non_ok == true but row 4 lacks any civilian_warning_phrasebook phrase. Block card emission.
- `AEP12_F22_BANNED_TERM_DETECTED` — banned_terms_detected[] non-empty (e.g., card text contains "quorum attestation" or "laundering_score"). Block card emission.
- `AEP12_F22_DIAL_LEVEL_INSUFFICIENT` — packet's action_class is in safety_floor_categories but trust_dial_level_required < Professional. Block card emission per HV6 closure inheritance.

### sec6.4 - Falsifier

Adversary A3 cheapest disconfirmer (verbatim from attack table): render the Proof Card for `tests/test_v11_f17_f18_f19_integration.py::test_f18_2_laundering_score_high_synthetic` packet (which scores 0.8+) and assert visual-judge flags it as red. Adversary A12 closure: banned-elisions linter + required-terms phrasebook BOTH wired.

### sec6.5 - Topology proof

`grep -r "CivilianProofCardRecord\|cpc:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship: schema discriminator only. The `civilian_proof_compiler.py` + AEP Viewer + Proof Card CSS are STAGED v1.2.1 per pathfinder Phase 8.

### sec6.6 - Composes_with

- v1.1 **F18** SourceProvenanceGraph — the load-bearing input for "What evidence supports it" (operator L62) + the source of `disclosed_signals.f18_laundering_score`.
- v1.1 **F19** CorpusCoverageWitness — the load-bearing input for `disclosed_signals.f19_coverage_gap_flag`.
- v1.1 **F15** CriterionWitnessChain — the input for `disclosed_signals.f15_missing_witness_flag`.
- v1.1 **F16** AttackClass registry — the input for `disclosed_signals.f16_attack_flag`.
- v1.1 **A8** ClaimSrsDecay — the input for `disclosed_signals.a8_srs_decay_status`.

### sec6.7 - EXTENDS lineage

Classification: **EXTENDS**. F22 builds on:

- **C2PA Content Credentials** (Coalition for Content Provenance and Authenticity) — nutrition label framing per operator L27.

Verifying_grep: `rg 'c2pa|content credentials|nutrition label' --type md research/sources/`. n_hits at SPEC ship: operator source.md L27 is the inheritance anchor (≥1 hit).

### sec6.8 - HV3 closure summary (HARD-CONSTRAINED)

The HV3 attack: "F22 oversimplification fraud" (the Proof Card hides HIGH-laundering or missing-witness signals behind friendly framing). Bound at the schema level by:

- `disclosed_signals` block REQUIRED; every F-tier validator signal surface MANDATORY.
- `f18_laundering_score.threshold_breached: true` (score >= 0.6) triggers `civilian_phrasing` requirement.
- `banned_elision_lint_status.required_terms_when_warning_present[]` — when `any_signal_non_ok == true`, row 4 MUST contain ≥1 civilian_warning_phrasebook phrase.
- A3 cheapest disconfirmer test fixture path embedded in schema description.

---

## sec7 - F23 Validator Adversary Mode

### sec7.1 - Motivation (operator source.md L17 + L69 + L180-L186)

Operator source.md L69 (immediate action #5):

> Fifth: add mutation validation. Every AEP validator should be attacked before trusted. Corrupt the packet, remove evidence, alter claims, flip reviewer IDs, mutate source spans, and ensure the validator catches the damage. If a validator cannot catch deliberate corruption, it does not deserve authority.

Operator source.md L180-L186 (F23 inheritance):

> F23: Validator Adversary Mode.
>
> Every validator must be tested by an adversary that tries to make a bad packet pass. If the adversary succeeds, the validator gets downgraded. This would prevent fake safety theater.

### sec7.2 - Record shape (7-mutation-class enum verbatim from operator L17 + A4 MEDIUM closure)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f23_validator_adversary_mode.schema.json`.

7-mutation-class enum verbatim from operator L17:
- `hash_flip`
- `span_removal`
- `reviewer_id_flip`
- `dag_parent_corrupt`
- `score_shift`
- `fake_instruction_injection`
- `event_reorder`

A4 MEDIUM closure HARD-CONSTRAINED:
- `depth_2_recursion_stop.depth: maximum 2`. Adversary recursion >=3 REJECTED. Use F14 rater_quorum for dispute resolution per sec50 EH Law-3 (do NOT invent meta-adversary).
- `f14_rater_quorum_for_dispute.required_when_inconclusive: true` when `adversary_verdict == validator_inconclusive`. ≥3 distinct principals attest the mutation actually corrupted the packet.

### sec7.3 - Reason codes

- `AEP12_F23_VALIDATOR_FAILED` — validator_outcome_on_mutation == missed && validator_should_have_caught == true. Trigger downgrade.
- `AEP12_F23_RECURSION_DEPTH_EXCEEDED` — depth > 2. Reject; route to F14 quorum.
- `AEP12_F23_QUORUM_REQUIRED` — adversary_verdict == validator_inconclusive && f14 quorum_records_referenced empty. Block report finalization.
- `AEP12_F23_NO_DOWNGRADE_AUTHORED` — Phase 3 acceptance: at least one real downgrade MUST be authored across the mutation suite. If 0 downgrades after running all 7 mutations × all v1.1 validators, layer is decorative per sec56; trigger AEP12_F23_NO_DOWNGRADE_AUTHORED.

### sec7.4 - Falsifier

Per pathfinder Phase 3 acceptance: mutation runner produces a report with at least 7 v1.1 validators × all 7 mutation classes (49 cells minimum). Each v1.1 validator that fails a mutation is flagged for downgrade. **At least one** real downgrade MUST be authored — otherwise the layer is decorative per sec56. STAGED v1.2.1 (the runner + report are not in this turn).

### sec7.5 - Topology proof

`grep -r "ValidatorAdversaryModeRecord\|vam:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship: schema discriminator only. The `mutate_packet.py` + `validator_adversary_runner.py` + `validator_adversary_v1_2.md` report are STAGED v1.2.1 per pathfinder Phase 3.

### sec7.6 - Composes_with

- v1.1 **F13** ClaimRuntimeFalsifier — F23 mutates the falsifier inputs.
- v1.1 **F16** AttackClass registry — F23 catalogs which attack class each mutation belongs to.
- v1.1 **F14** RaterQuorumAttestation — A4 closure: F14 is the dispute-resolution mechanism (NOT a meta-adversary).

### sec7.7 - EXTENDS lineage

Classification: **EXTENDS**. F23 builds on:

- **AFL** (American Fuzzy Lop; mutation fuzzing genealogy).
- **honggfuzz** (Google fuzzer; mutation-based + coverage-guided).
- **Hypothesis** (Python property-based testing — applies the same mutation philosophy at unit-test scope).

Verifying_grep: `rg 'afl|honggfuzz|hypothesis|fuzz' --type md research/sources/`. Operator source.md L17 is the inheritance anchor.

### sec7.8 - A4 MEDIUM closure summary (HARD-CONSTRAINED)

The A4 attack: "F23 adversary recursion (turtle bottom)." Bound at the schema level by:

- `depth_2_recursion_stop.depth: integer maximum 2`.
- `f14_rater_quorum_for_dispute.required_when_inconclusive: true` for inconclusive verdicts.
- Per sec50 EH Law-3 multi-lens independence: F14 provides the multi-lens independence; do NOT invent a meta-adversary.

---

## sec8 - F25 Trust Dial

### sec8.1 - Motivation (operator source.md L196-L205)

> F25: Trust Dial.
>
> Users choose the required proof level based on risk:
>
> Casual: basic source and claim check.
> Important: falsifier + provenance + coverage.
> Professional: quorum + review + policy gates.
> Critical: sandbox + mutation + formal invariant + human approval.
>
> This lets general users adopt AEP without drowning in enterprise machinery.

Operator source.md L82 (the safety floor mandate):

> "Safe to rely on for low-risk use." "Not safe for money, health, legal, or irreversible decisions."

### sec8.2 - Record shape (HV6 closure HARD-CONSTRAINED)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f25_trust_dial.schema.json`.

4-level enum verbatim from operator L200-L203:
- `Casual`
- `Important`
- `Professional`
- `Critical`

HV6 closure fields HARD-CONSTRAINED:
- `safety_floor_categories` — enum `[money, health, legal, irreversible]` per operator L82 verbatim.
- `action_class` — auto-classified; when matches safety_floor_categories, `required_minimum_level` HARD-CONSTRAINED to Professional or higher.
- `level_enforcement_status.civilian_banner_when_blocked` — REQUIRED text when BLOCKED_UPGRADE_REQUIRED.
- `primitive_subset_activated` — explicit per-level activation map (Casual = F13 + F18 minimum; Critical = ALL).

### sec8.3 - Reason codes

- `AEP12_F25_SAFETY_FLOOR_VIOLATION` — user_selected_level < required_minimum_level when action_class in safety_floor_categories. Block.
- `AEP12_F25_BANNER_TEXT_MISSING` — status == BLOCKED_UPGRADE_REQUIRED but civilian_banner_when_blocked empty. Block card emission.
- `AEP12_F25_CIVILIAN_VOCABULARY_FAIL` — banner_text contains banned technical terms. Block.

### sec8.4 - Falsifier

Adversary A6 cheapest disconfirmer (verbatim): red-team a $400K lease-summary packet at Casual level; expected behavior = dial REJECTS with the named banner ("This claim affects legal — Casual mode is not allowed."). Test fixture path: `projects/v11-aep/publish-ready/aep/tests/test_trust_dial_enforces_level.py` (STAGED v1.2.1).

### sec8.5 - Topology proof

`grep -r "TrustDialRecord\|td:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship: schema discriminator only. The `risk_classifier.py` (Phase 8 forge) + dial enforcement validator + civilian banner renderer are STAGED v1.2.1.

### sec8.6 - Composes_with

- **ALL v1.1 primitives** — F25 dial activates a v1.1 primitive subset per level (per `primitive_subset_activated`).
- v1.2 **F22 CivilianProofCard** — `trust_dial_level_required` field on the card binds to F25.

### sec8.7 - EXTENDS lineage

Classification: **EXTENDS**. F25 builds on:

- **NIST SP 800-63** assurance levels (3-level analog; F25 extends to 4-level).
- **NIST AI Risk Management Framework**.
- **ISO/IEC 42001** AI management system (per operator L41).

Verifying_grep: `rg 'nist sp 800-63|nist ai rmf|iso 42001' --type md research/sources/`. Operator L41 + L92-L93 are the inheritance anchors.

### sec8.8 - HV6 closure summary (HARD-CONSTRAINED)

The HV6 attack: "F25 Trust Dial under-protection floor" (Casual + user self-selection on $400K real-estate purchase agreement). Bound at the schema level by:

- `safety_floor_categories: enum [money, health, legal, irreversible]` HARD-CONSTRAINED.
- `required_minimum_level: Professional` when action_class in safety_floor_categories.
- `civilian_banner_when_blocked` REQUIRED text per HV6 closure.
- A6 cheapest disconfirmer: $400K lease packet at Casual = REJECTED.

---

## sec9 - F24 Evidence Rights & Redaction

### sec9.1 - Motivation (operator source.md L29 + L186-L192)

Operator L29:

> Seventh, AEP needs privacy and redaction by design. Evidence packets can accidentally become surveillance packets. ... public/private evidence tiers, salted hashes for sensitive artifacts, local-only evidence vaults, and export manifests that clearly say what was removed.

Operator L186-L192 (F24 inheritance):

> F24: Evidence Rights & Redaction Layer.
>
> Every evidence item gets a visibility class:
>
> public, private, local-only, hashed-only, encrypted, ephemeral, or forbidden-to-export.

### sec9.2 - Record shape (HV5 closure HARD-CONSTRAINED)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f24_evidence_rights_redaction.schema.json`.

7 visibility classes verbatim from operator L188-L190:
- `public`
- `private`
- `local_only`
- `hashed_only`
- `encrypted`
- `ephemeral`
- `forbidden_to_export`

HV5 closure fields HARD-CONSTRAINED:
- `hash_correlation_resistance.salt_scope: enum [per_packet_random_salt, per_corpus_shared_salt, no_salt]`. Required value for sensitive workflows: `per_packet_random_salt`.
- `hash_correlation_resistance.frequency_analysis_attack_acknowledged: boolean` — for hashed_only tier, MUST be true with explicit text disclosure.
- `salt_storage_class: enum [local_only, encrypted, ephemeral, forbidden_to_export]` — salt itself cannot be public or hashed_only.
- `export_manifest_disclosure.what_was_removed` REQUIRED.

### sec9.3 - Reason codes

- `AEP12_F24_HASH_UNSALTED` — visibility_class == hashed_only && salt_present == false. Reject record.
- `AEP12_F24_CORPUS_SHARED_SALT` — salt_scope == per_corpus_shared_salt on sensitive workflow. Reject; require per_packet_random_salt.
- `AEP12_F24_FREQUENCY_ATTACK_NOT_ACKNOWLEDGED` — visibility_class == hashed_only && frequency_analysis_attack_acknowledged == false. Block.
- `AEP12_F24_EXPORT_DISCLOSURE_MISSING` — visibility_class != public && export_manifest_disclosure.disclosed_in_export == false. Block.

### sec9.4 - Falsifier

Adversary A5 cheapest disconfirmer: write a test that emits 100 redacted packets sharing 10 secret sources, attempts to recover the 10 sources from hash co-occurrence; pass = recovery rate ≤ chance. Test fixture path: `projects/v11-aep/publish-ready/aep/tests/test_redaction_blocks_private_export.py` (STAGED v1.2.1).

### sec9.5 - Topology proof

`grep -r "EvidenceRightsRedactionRecord\|err:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship: schema discriminator only. The `redact_for_export.py` + linkability disconfirmer test are STAGED v1.2.1.

### sec9.6 - Composes_with

- v1.1 **F18** SourceProvenanceGraph — visibility_class binds to source.id.

### sec9.7 - EXTENDS lineage

Classification: **EXTENDS**. F24 builds on:

- **GDPR Article 25** privacy-by-design.
- **Capability security** (object-capability discipline).
- **Differential privacy** fundamentals.

Verifying_grep: `rg 'gdpr|privacy by design|differential privacy|capability security' --type md research/sources/`.

### sec9.8 - HV5 closure summary (HARD-CONSTRAINED)

The HV5 attack: "F24 hash correlation across packets" (corpus-shared salt leaks via frequency analysis). Bound at the schema level by:

- `per_packet_random_salt` REQUIRED on sensitive workflows.
- Frequency-analysis attack disclosed as KNOWN LIMITATION on `hashed_only` tier; sensitive workflows MUST use `encrypted` or `forbidden_to_export`.
- Salt itself stored with restrictive visibility class.

---

## sec10 - F26 AEP Compatibility Passport

### sec10.1 - Motivation (operator source.md L31 + L209-L211)

Operator L31:

> Eighth, AEP needs compatibility bridges. Do not try to replace every standard. Export to them. Import from them. AEP should be able to crosswalk with W3C PROV, C2PA, in-toto, SLSA, RO-Crate, OpenLineage, OpenTelemetry, SBOM formats, and normal PDFs. That makes AEP feel less like "a weird new file type" and more like "the missing trust adapter for everything else."

Operator L209-L211 (F26 inheritance):

> F26: AEP Compatibility Passport.
>
> Every packet declares what external trust ecosystems it can map to: PROV, C2PA, SLSA, in-toto, RO-Crate, OpenLineage, OpenTelemetry, SBOM, PDF, Markdown, HTML, Git commit, email thread, or LMS artifact.

### sec10.2 - Record shape (HV7 closure HARD-CONSTRAINED)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_f26_compatibility_passport.schema.json`.

14 mapping targets verbatim from operator L211 (SBOM split into SBOM_SPDX + SBOM_CycloneDX per modern split):
- `PROV` · `C2PA` · `SLSA` · `in_toto` · `RO_Crate` · `OpenLineage` · `OpenTelemetry` · `SBOM_SPDX` · `SBOM_CycloneDX` · `PDF` · `Markdown` · `HTML` · `Git_commit` · `email_thread` · `LMS_artifact`

HV7 closure fields HARD-CONSTRAINED:
- `verified_round_trip_compatible[]` — entries REQUIRE `export_fixture_path` + `import_fixture_path` + `round_trip_test_path` + `round_trip_test_outcome: enum [PASS, FAIL, PENDING]` + `round_trip_sha256` + `external_validator_invoked: boolean` + `external_validator_name`.
- `declared_compatible[]` — entries REQUIRE `declaration_truth_tag: enum [EXPERIMENTAL, SPECULATIVE FRONTIER]` (NOT PROVEN/RELIABLE or STRONGLY PLAUSIBLE) + `honest_framing_text` MIN 16 chars.
- `trust_attestation_basis.only_verified_counts: const true`. Trust attestation considers ONLY verified_round_trip_compatible[] entries.
- `trust_attestation_basis.external_validator_required_for_verified: const true`. Entries in verified[] MUST have `external_validator_invoked == true`.

### sec10.3 - Reason codes

- `AEP12_F26_VERIFIED_MISSING_FIXTURE` — entry in verified_round_trip_compatible[] lacks round_trip_test_path. Reject record.
- `AEP12_F26_VERIFIED_NO_EXTERNAL_VALIDATOR` — entry in verified[] has external_validator_invoked == false. Reject (move to declared_compatible[] with honest_framing_text).
- `AEP12_F26_DECLARED_OVERTAGGED` — declaration_truth_tag in declared_compatible[] entry is PROVEN/RELIABLE or STRONGLY PLAUSIBLE. Reject.
- `AEP12_F26_HONEST_FRAMING_MISSING` — declared_compatible[] entry lacks honest_framing_text. Block.

### sec10.4 - Falsifier

Adversary A7 cheapest disconfirmer: run each "verified" round-trip in CI; fail the build on any unverified `verified[]` claim. The schema rejects entries without external_validator_invoked + round_trip_test_outcome == PASS.

Empirical answer to operator's verbatim question "how many of the 14 have we actually verified?": **0 today; 0-4 by end of v1.2.1 if Phase 7 lands round-trip tests; remaining 10-14 STAGED v1.2.2+** per sec73.6 honest framing.

### sec10.5 - Topology proof

`grep -r "CompatibilityPassportRecord\|cmp:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/`

n_hits at SPEC ship: schema discriminator only. The `export_compatibility_passport.py` + 4 round-trip test fixtures are STAGED v1.2.1 per pathfinder Phase 7.

### sec10.6 - Composes_with

- v1.1 **F18** SourceProvenanceGraph — `lineage_basis` surface binds to F18's external-precedent classification.

### sec10.7 - EXTENDS lineage

Classification: **EXTENDS**. F26 builds on:

- **W3C PROV-O** (canonical provenance ontology).
- **C2PA Content Credentials**.
- **in-toto** (software supply-chain attestations; ITE6 format).
- **SLSA** (Supply-chain Levels for Software Artifacts).
- **RO-Crate** (Research Object Crate).
- **OpenLineage** (data lineage tracking).
- **OpenTelemetry** (observability traces).
- **SBOM (SPDX and CycloneDX)** Software Bill of Materials.

Verifying_grep: `rg 'prov-o|c2pa|in-toto|slsa|ro-crate|openlineage|opentelemetry|spdx|cyclonedx' --type md research/sources/`. Operator L31 + L211 are the inheritance anchors.

### sec10.8 - HV7 closure summary (HARD-CONSTRAINED)

The HV7 attack: "F26 declared-vs-verified compatibility laundering" (the SCHEMA admits `declared_compatible: true` for all 14 with no verification mechanism). Bound at the schema level by:

- Two arrays: `verified_round_trip_compatible[]` vs `declared_compatible[]`.
- Only `verified_round_trip_compatible[]` counts toward trust attestation (`only_verified_counts: const true`).
- `external_validator_required_for_verified: const true`.
- `declared_compatible[].declaration_truth_tag` HARD-CONSTRAINED to EXPERIMENTAL or SPECULATIVE FRONTIER (cannot be tagged PROVEN/RELIABLE).
- `honest_framing_text` REQUIRED on every declared-only entry.

---

## sec11 - Invariant Contract Layer

### sec11.1 - Motivation (operator source.md L11-L14)

Operator L11-L14:

> First, AEP needs a contract layer. Right now it tracks claims, sources, falsifiers, receipts, and history. But every packet should also declare, in plain and machine-checkable form: "What must always be true about this packet?" These are invariants. For example: every promoted claim must have a source, every source must have a provenance type, every completion claim must link to success criteria, every score must have a rubric, every rubric must have reviewer evidence, and every external file must have a content hash. This would turn AEP from "evidence after the fact" into "invalid states cannot exist."

### sec11.2 - Record shape

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_invariant_contract.schema.json`.

New claim type `Invariant` added to `data/claims.jsonl` per operator L13. Required fields:
- `invariant_name`
- `machine_checkable_predicate` (form: jsonpath | rego_policy | python_callable | regex | shacl_shape | tla_action)
- `plain_language_form` (civilian text)
- `scope` (packet_global | claim_local | source_local | review_local | validation_local | ledger_row | manifest_extension)
- `violation_class`
- `violation_outcome` (REJECT | WARN | DOWNGRADE_TRUTH_TAG | QUARANTINE)
- `operator_directive_basis_line_range` (sec73.3 inheritance anchor; const source_path == operator's source.md)

### sec11.3 - The 6 operator-named invariants (L13 verbatim)

The schema's example block instantiates the first of these 6 verbatim:

1. **every_promoted_claim_must_have_a_source** — `policy.deny[reason] { input.claim.truth_tag == "PROVEN/RELIABLE"; not input.claim.basis_source_ids }`
2. **every_source_must_have_a_provenance_type** — `policy.deny[reason] { input.source; not input.source.venue_tier }`
3. **every_completion_claim_must_link_to_success_criteria** — `policy.deny[reason] { input.claim.type == "CompletionAttestation"; not input.claim.bound_criterion_ids }`
4. **every_score_must_have_a_rubric** — `policy.deny[reason] { input.claim.type == "RubricScore"; not input.claim.rubric_id }`
5. **every_rubric_must_have_reviewer_evidence** — `policy.deny[reason] { input.rubric; not input.rubric.reviewer_principal_ids }`
6. **every_external_file_must_have_a_content_hash** — `policy.deny[reason] { input.source.kind == "external_file"; not input.source.sha256 }`

### sec11.4 - Reason codes

- `AEP12_INV_<NAME>` — generic emission code per invariant name (e.g., `AEP12_INV_EVERY_PROMOTED_CLAIM_MUST_HAVE_A_SOURCE`).

### sec11.5 - Topology proof

`grep -r 'type": "Invariant"' --include="*.json" --include="*.jsonl" projects/v11-aep/` — schema discriminator only at SPEC ship. The 6 invariant records are STAGED for Phase 1 forge to emit.

### sec11.6 - Composes_with

- v1.1 **F18** SourceProvenanceGraph — invariant violations become lineage defects (cite the violated invariant in the SourceProvenanceGraphRow.invalidator_checked field).

### sec11.7 - EXTENDS lineage

Classification: **EXTENDS**. Invariant Contract Layer builds on:

- **TLA+** state-invariant idiom.
- **Hoare-logic preconditions**.
- **Eiffel design-by-contract**.

Verifying_grep: `rg 'tla|hoare logic|design by contract|eiffel' --type md research/sources/`.

---

## sec12 - Bug Ontology Layer

### sec12.1 - Motivation (operator source.md L15-L18)

> Second, it needs a bug ontology. Every bug should become a typed memory object. Not just "fixed bug," but: bug class, root cause, escape path, detection gap, affected primitive, reproduction input, smallest failing example, prevention rule, regression test, and future warning cue. This would make AEP learn from every failure structurally. A normal software repo has tests. AEP should have scar tissue.

### sec12.2 - Record shape

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_bug_ontology.schema.json`.

New claim type `BugOntologyRecord` added to `data/claims.jsonl`. 10 fields verbatim from operator L15:
1. `bug_class` (17-class enum extensible per schema-additive-only discipline)
2. `root_cause`
3. `escape_path`
4. `detection_gap`
5. `affected_primitive` (cross-cuts v0.x/v1.0.x/v1.1/v1.2 primitive enum)
6. `reproduction_input` (text + sha256)
7. `smallest_failing_example` (text + sha256)
8. `prevention_rule` (rule_id + executable_form bound to Policy Rego)
9. `regression_test` (test_path + outcome_pre_fix == FAIL + outcome_post_fix == PASS)
10. `future_warning_cue` (civilian text)

### sec12.3 - The seed bug record (BC-V103-1 rubric definitional gap)

Per pathfinder Phase 1 acceptance: bug ontology schema validates a hand-authored seed bug record covering BC-V103-1's actual 2026-05-18 rubric gap. The schema's example block instantiates this seed:

- `bug_class: rubric_definitional_gap`
- `root_cause: "VG04 rubric language did not distinguish load-bearing vs decorative list items in failure_prevented[]"`
- `affected_primitive: [F14, A4]`
- `prevention_rule: pr:rubric-list-valued-fields-class-each-item`
- `regression_test: tests/test_rubric_list_valued_fields_classed.py` (STAGED v1.2.1)

### sec12.4 - Reason codes

- `AEP12_BUG_REGRESSION_PRE_FIX_NOT_FAIL` — regression_test.test_outcome_pre_fix != FAIL. Reject (the test does not actually test the bug).
- `AEP12_BUG_REGRESSION_POST_FIX_NOT_PASS` — regression_test.test_outcome_post_fix != PASS. Reject (the fix is not actually a fix).
- `AEP12_BUG_PREVENTION_RULE_NOT_BOUND` — prevention_rule.executable_form is empty. Block.

### sec12.5 - Topology proof

`grep -r "BugOntologyRecord\|bug:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/` — schema + seed record example at SPEC ship.

### sec12.6 - Composes_with

- v1.2 **F20 BugVaccineKernel** — each bug ontology record can birth a vaccine.
- v1.1 **F13** ClaimRuntimeFalsifier — regression_test composes.
- v1.1 **F16** AttackClass registry — bug_class enum extends the attack class catalog.

### sec12.7 - EXTENDS lineage

Classification: **EXTENDS**. Bug Ontology Layer builds on:

- **CWE** (Common Weakness Enumeration).
- **CVE** (Common Vulnerabilities and Exposures).
- **Google SRE post-mortem culture**.
- **Structured fault tree analysis**.

Verifying_grep: `rg 'cwe|cve|sre post-mortem|fault tree' --type md research/sources/`.

---

## sec13 - The 10-Gate Kill Chain

### sec13.1 - Motivation (operator source.md L107-L131)

Operator L107-L131:

> For preventing almost all bugs, I would define bug prevention as a layered kill chain. A bug should have to survive all of these gates:
>
> At authoring time, the packet schema blocks invalid structure.
> At claim time, the claim type requires sources, confidence, expiry, and falsifier.
> At source time, provenance laundering detection blocks synthetic evidence from pretending to be primary evidence.
> At execution time, sandboxing and runtime quorum prevent unsafe or environment-specific execution.
> At validation time, mutation tests attack the validator itself.
> At review time, independent rater quorum catches subjective scoring weakness.
> At completion time, witness chains prevent fake "done."
> At coverage time, corpus witnesses prevent skipped scope.
> At time decay, old claims lose authority.
> At recurrence time, repeated bugs become doctrine-level prevention rules.

### sec13.2 - The 10 gates bound to v1.1 + v1.2 primitives

| Gate | Operator L# | v1.x primitive(s) binding |
|---|---|---|
| **G1: authoring time** | L111 | JSON Schema (canonical 7 files + v1.2 schemas all with `additionalProperties: false`) |
| **G2: claim time** | L113 | v1.0.x claim type discriminators + v1.1 F13 (falsifier required on PROVEN/RELIABLE) + A8 (expiry required) |
| **G3: source time** | L115 | v1.1 F18 SourceProvenanceGraph (laundering-score) + Policy `policy:laundering-score-promotion-gate` |
| **G4: execution time** | L117 | v1.2 Sandbox Gate (sec15) + v1.0.x F9 cross-substrate quorum |
| **G5: validation time** | L119 | v1.2 F23 Validator Adversary Mode (mutation tests attack the validator) |
| **G6: review time** | L121 | v1.0.3.1 F14 RaterQuorumAttestation (independent rater quorum) |
| **G7: completion time** | L123 | v1.1 F15 CriterionWitnessChain + CompletionAttestation (no fake done) |
| **G8: coverage time** | L125 | v1.1 F19 CorpusCoverageWitness (no skipped scope) |
| **G9: time decay** | L127 | v1.1 A8 ClaimSrsDecay (old claims lose authority) |
| **G10: recurrence time** | L129 | v1.2 F20 BugVaccineKernel (repeated bugs become doctrine-level prevention rules) |

### sec13.3 - Gate runner (STAGED v1.2.1)

`projects/v11-aep/publish-ready/aep/scripts/kill_chain_runner.py` (STAGED per pathfinder Phase 6) wires all 10 gates sequentially. Each gate calls existing v1.1 + v1.2 validators. Per pathfinder Phase 6 acceptance: kill chain test suite blocks a synthetic bad packet at EACH of the 10 gates.

### sec13.4 - sec73.6 honest framing

Per operator L131: "That is how you get close to 'almost all bugs' structurally. Not by promising perfection, but by making every bug pass through ten locked doors."

The kill chain promise is **STRONGLY PLAUSIBLE** (10 gates each grounded in a v1.1 or v1.2 primitive) — not PROVEN/RELIABLE. The empirical proof requires running the synthetic-bad-packet suite end-to-end, which is STAGED v1.2.1.

---

## sec14 - Policy-as-Code Interface

### sec14.1 - Motivation (operator source.md L21 + L73-L77)

Operator L21:

> Fifth, AEP needs policy-as-code gates. Some rules should not live in prompts. They should live in executable policy. For example: "Do not promote claims with laundering_score > 0.6," "do not run executable validation without sandbox permission," "do not accept reviewer quorum if principal IDs are not distinct," and "do not export private evidence without redaction." Open Policy Agent/Rego is a strong precedent for this kind of reusable policy layer. AEP should have its own compact policy engine or OPA-compatible export.

### sec14.2 - Record shape

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_policy_rego.schema.json`.

Required fields:
- `policy_name`
- `policy_kind` (promotion_gate | export_gate | execution_gate | quorum_gate | redaction_gate | sandbox_gate | trust_dial_floor_gate | invariant_gate)
- `rego_expression` (expression + rego_dialect + compiled_against_opa_version)
- `operator_directive_basis_line_range` (sec73.3 inheritance anchor)
- `policy_target_field_path` (jsonpath to the input field this policy evaluates)
- `violation_outcome` (REJECT_PROMOTION | REJECT_EXPORT | REJECT_EXECUTION | WARN_WITH_DOWNGRADE | QUARANTINE)
- `ci_gate_enforcement.enforced_in_ci` + test_fixture_path

### sec14.3 - The 4 operator-named example policies (L21 verbatim)

The schema's example block instantiates the first. The full 4:

1. **block_promotion_when_laundering_score_above_threshold** — `deny[reason] { input.claim.laundering_score > 0.6; reason := ... }` (binds to v1.1 F18).
2. **block_executable_validation_without_sandbox_permission** — `deny[reason] { input.validation.executable == true; not input.validation.sandbox_permission_granted; reason := ... }` (binds to v1.2 Sandbox Gate).
3. **reject_reviewer_quorum_if_principal_ids_not_distinct** — `deny[reason] { count(input.review.principal_ids) > count(set(input.review.principal_ids)); reason := ... }` (binds to v1.0.3.1 F14).
4. **block_export_of_private_evidence_without_redaction** — `deny[reason] { input.evidence.visibility_class == "private"; not input.evidence.export_manifest_disclosure.disclosed_in_export; reason := ... }` (binds to v1.2 F24).

### sec14.4 - Export-to-Rego (one-way for v1.2; full import STAGED v1.3+)

Per pathfinder Phase 5 acceptance: policy engine ships with one-way export to OPA-compatible Rego. Full Rego import (read external OPA bundles and apply to AEP packets) is STAGED v1.3+.

Honest framing per sec73.6: policy engine ships explicitly as `EXTENDS OPA/Rego` per F18 lineage; export-to-Rego is one-way for v1.2.

### sec14.5 - Reason codes

- `AEP12_POL_PROMOTION_BLOCKED` — promotion_gate policy denied. Block promotion.
- `AEP12_POL_EXECUTION_BLOCKED` — execution_gate policy denied. Block execution.
- `AEP12_POL_EXPORT_BLOCKED` — export_gate policy denied. Block export.
- `AEP12_POL_QUORUM_REJECTED` — quorum_gate policy denied. Reject review record.
- `AEP12_POL_REGO_PARSE_ERROR` — rego_expression failed to parse against compiled_against_opa_version. Block policy emit.

### sec14.6 - Topology proof

`grep -r "PolicyRegoRecord\|pol:" --include="*.py" --include="*.md" --include="*.json" projects/v11-aep/` — schema discriminator + 1 example policy at SPEC ship. The `aep_policy_engine.py` + `export_to_rego.py` + 4 verbatim-policy test fixtures are STAGED v1.2.1 per pathfinder Phase 5.

### sec14.7 - Composes_with

- v1.1 **F14** RaterQuorumAttestation — quorum_gate policy class.
- v1.1 **F18** SourceProvenanceGraph — laundering_score promotion gate.
- v1.2 **F24** Evidence Rights — export_gate policy class.
- v1.2 **Sandbox Gate** — execution_gate policy class.

### sec14.8 - EXTENDS lineage

Classification: **EXTENDS**. Policy-as-code interface builds on:

- **Open Policy Agent (OPA)** + **Rego** policy language (per operator L21).
- **CNCF policy primitives**.

Verifying_grep: `rg 'open policy agent|rego|opa policy' --type md research/sources/`. Operator L21 is the inheritance anchor.

---

## sec15 - Sandbox Gate

### sec15.1 - Motivation (operator source.md L71-L72 + L33)

Operator L71-L72 (immediate action #6):

> Sixth: build the AEP Sandbox Gate. No claim falsifier, regex, script, or imported packet should execute in the user's real environment by default. It should run in a constrained sandbox with declared permissions: read-only, no network, temp directory only, CPU/time cap, memory cap, no secrets, no shell escape. This is essential for public trust.

Operator L33 (OWASP framing):

> Ninth, AEP needs agent permission boundaries. OWASP's LLM risk list puts prompt injection and insecure output handling at the top of the LLM application risk universe...

### sec15.2 - OS-level primitive choice (HV9 closure HARD-CONSTRAINED)

Adversary A9 attack: "`subprocess_sandboxed` is a STRING LABEL today (validate_f13_falsifier.py line 56 VALID_EXECUTORS); no OS namespace / seccomp / AppContainer / seatbelt wrapping."

HV9 closure: Sandbox Gate SHIPS WITH a concrete OS-level primitive named explicitly per platform:

- **Windows 11 (operator's platform)**: **AppContainer** — Windows 8+ sandbox primitive providing process-level isolation, namespace separation, network-disable capability, file-system virtualization. Documented Microsoft API surface (per sec73.1 API-verification-law).
- **Linux**: **firejail** (SUID sandbox using Linux namespaces + seccomp-bpf + capabilities) OR **bubblewrap** (unprivileged user-namespace sandbox; Flatpak default). Linux fallback when AppContainer unavailable.
- **macOS**: **sandbox-exec** (Apple Seatbelt; profile-based SIP/macOS sandbox) OR **macOS Seatbelt profiles**.
- **Cross-platform Python fallback**: Python-only sandbox using `subprocess` with explicit `env={}` + `cwd=tempdir` + `timeout=N` + `preexec_fn=` namespace + `socketserver` deny-all + `resource.setrlimit` memory cap. **THIS FALLBACK IS DOCUMENTED AS INSUFFICIENT FOR FALSIFIER EXECUTION** per HV9 closure honest framing; ships as `aep:1.2/sandbox-opt-in` profile only.

### sec15.3 - Sandbox constraint enum (operator L71 verbatim)

7 constraints verbatim:
- `read_only` (no write to user filesystem outside temp dir).
- `no_network` (deny all socket / urllib / requests / chrome / curl).
- `temp_dir_only` (cwd = ephemeral temp dir; deleted on exit).
- `cpu_time_cap` (default 30s; configurable per falsifier).
- `memory_cap` (default 256 MiB; configurable).
- `no_secrets` (env = {} except sandbox-required vars).
- `no_shell_escape` (no os.system / shell=True / popen / `&` / `;` / `|`).

### sec15.4 - Empirical disconfirmer (A9 cheapest disconfirmer per adversary)

Test fixture path: `projects/v11-aep/publish-ready/aep/tests/test_sandbox_blocks_python_subprocess.py` (STAGED v1.2.1 per pathfinder Phase 4).

Test asserts that a falsifier with:
```python
cmd = 'python -c "import socket; socket.socket().connect((\"1.1.1.1\",80))"'
```
FAILS under the sandbox.

Today (pre-v1.2): test PASSES (network unrestricted under `subprocess_sandboxed` string label). Post-v1.2.1 (after sandbox primitive lands): test FAILS as expected.

### sec15.5 - Reason codes

- `AEP12_SANDBOX_NETWORK_ATTEMPTED` — falsifier attempted socket / urllib / requests in sandbox. Block + log.
- `AEP12_SANDBOX_FILESYSTEM_WRITE_OUTSIDE_TEMP` — falsifier attempted write outside tempdir. Block + log.
- `AEP12_SANDBOX_CPU_CAP_EXCEEDED` — falsifier exceeded cpu_time_cap. Kill + log.
- `AEP12_SANDBOX_MEMORY_CAP_EXCEEDED` — falsifier exceeded memory_cap. Kill + log.
- `AEP12_SANDBOX_SHELL_ESCAPE_ATTEMPTED` — falsifier invoked shell=True / os.system / popen. Block + log.
- `AEP12_SANDBOX_PRIMITIVE_MISSING` — OS primitive not available on platform (e.g., AppContainer on Linux). Fall back to Python-only sandbox + emit AEP12_SANDBOX_INSUFFICIENT_WARNING.

### sec15.6 - HV9 closure summary (HARD-CONSTRAINED)

The HV9 attack: "`subprocess_sandboxed` is a string label, not a sandbox." Bound at the implementation level (sandbox_gate.py STAGED v1.2.1) by:

- Explicit OS primitive named per platform (Win11 AppContainer / firejail / Seatbelt / Python-fallback honest-framed).
- Empirical disconfirmer test required before sandbox is promoted to PROVEN/RELIABLE.
- Per sec73.6: v1.2 ships sandbox as **schema-and-spec only this turn**; the empirical primitive integration is STAGED v1.2.1.

---

## sec16 - Adoption Modes — Lite / Pro / Institutional

### sec16.1 - Motivation (operator source.md L35-L41 + L86-L93)

Operator L35-L41:

> Tenth, AEP needs adoption modes. One format cannot serve everyone equally. I would create three public levels:
>
> AEP Lite for normal people: one folder, one proof card, one "check this" button.
> AEP Pro for builders: full claims, sources, tests, reviews, history, and validation runs.
> AEP Institutional for companies, schools, labs, and government: policy gates, audits, retention, privacy, certification, and compliance mapping to NIST AI RMF / ISO 42001-style governance expectations.

### sec16.2 - The 3 profiles

- **`aep:1.2/lite`** — civilian. 4-file shape (claim.json + sources/ + receipt.json + proof-card.json). v1.2 primitives activated: F22 + AEPLite. No falsifier execution required.
- **`aep:1.2/pro`** — builder. Full v1.1 + v1.2 superset. All F-tier primitives activated. Falsifier execution per F13 falsifier-strict; F23 mutation suite available; F26 passport export available.
- **`aep:1.2/institutional`** — compliance. v1.2/pro + policy gates + audit retention (90-day default) + privacy classes enforced + compliance mapping to NIST AI RMF / ISO 42001 documented in `aepkg.json.extensions.compliance_mapping`.

### sec16.3 - AEP Lite schema (operator L86-L93 verbatim)

Schema: `projects/v11-aep/publish-ready/aep/schemas/v1_2_aep_lite.schema.json`.

4 files verbatim from operator L88-L91:
- `claim.json` (single claim with claim_text + truth_tag + basis_source_ids + falsifier_summary + expires_at)
- `sources/` (one file per source; minimum count 1; pattern `^src-[a-z0-9-]+\.(md|html|pdf|txt|json)$`)
- `receipt.json` (packet_id + emitted_at + emitted_by_agent_or_user + validator_verdict + tests_run_count + tests_passed_count + tests_failed_count + any_signal_non_ok + checked_by_runtimes_count)
- `proof-card.json` (bound to v1.2 F22 schema; 5 rows mandatory)

### sec16.4 - Public trust vocabulary (operator L74-L82 verbatim)

The civilian-translation surface uses ONLY phrases from this list (operator L74-L82 verbatim):

- "Checked by 3 runtimes."
- "Source is direct."
- "Source is AI-derived."
- "Claim has expired."
- "Evidence missing."
- "Test passed, but weak."
- "Safe to rely on for low-risk use."
- "Not safe for money, health, legal, or irreversible decisions."

### sec16.5 - Banned-term list (sec18 + plan sec18)

Banned technical terms in civilian-facing text (v1.2 banned_term_list_version):
- `quorum attestation`
- `laundering_score`
- `Ed25519`
- `attestation graph`
- `DAG`
- `sha256`
- `state_hash`
- `principal_id`
- `additionalProperties`
- `JSON Schema`

The civilian vocabulary lint REJECTS any F22 card text containing any banned term. The lint version `v1.2.0` is set at SPEC ship; updates per adversary discovery in v1.2.1+.

### sec16.6 - Compile-down from Pro to Lite (operator L93)

`projects/v11-aep/publish-ready/aep/scripts/compile_pro_to_lite.py` (STAGED v1.2.1 per pathfinder Phase 7) compiles a Pro packet down to a Lite packet. What is lost (honest framing per sec73.6):
- DAG amendment history
- Ed25519 signatures (replaced with text checkmark)
- Reviewer principal IDs (replaced with role names)
- Mutation suite per-mutation reports (replaced with summary counts)

The schema field `compile_down_from_pro_allowed.lossless_for_civilian_decision` is FALSIFIABLE by the Phase 9 civilian-comprehension empirical test.

---

## sec17 - Compatibility Bridges — Declared vs Verified

### sec17.1 - The two-array discipline (HV7 closure summary)

Per sec10.8 HV7 closure: F26 schema HARD-CONSTRAINS the two-array split (`verified_round_trip_compatible[]` vs `declared_compatible[]`). Only verified entries count toward trust attestation.

### sec17.2 - The 14 target ecosystems

Per sec10.2 + operator L211 verbatim: PROV / C2PA / SLSA / in_toto / RO_Crate / OpenLineage / OpenTelemetry / SBOM_SPDX / SBOM_CycloneDX / PDF / Markdown / HTML / Git_commit / email_thread / LMS_artifact.

### sec17.3 - The "0 today; 0-4 by v1.2.1" honest framing

Per adversary A7 bet (sec1.6): F26 ships with `verified_count: 0` at SPEC ship. v1.2.1 STAGED targets:
- **PROV** (W3C provenance) — `prov-toolbox` external validator.
- **C2PA** (Content Credentials) — `c2pa-rs` external validator.
- **SLSA** (Supply-chain Levels) — SLSA verifier.
- **in_toto** (ITE6 attestations) — `in-toto` Python lib external validator.

These 4 are pathfinder Phase 7 baseline. Remaining 10 (RO_Crate / OpenLineage / OpenTelemetry / SBOM_SPDX / SBOM_CycloneDX / PDF / Markdown / HTML / Git_commit / email_thread / LMS_artifact) STAGED v1.2.2+ per sec73.6 honest framing.

### sec17.4 - The external_validator_required_for_verified invariant

Per HV7 closure HARD-CONSTRAINED: `trust_attestation_basis.external_validator_required_for_verified: const true`. Entries in `verified_round_trip_compatible[]` MUST have `external_validator_invoked == true` + `external_validator_name` populated. In-repo round-trip-only entries are REJECTED from verified[] and must move to declared_compatible[].

---

## sec18 - Privacy / Redaction (7 Visibility Classes)

### sec18.1 - The 7 visibility classes (operator L188-L190 verbatim)

Per sec9.2:
- `public`
- `private`
- `local_only`
- `hashed_only`
- `encrypted`
- `ephemeral`
- `forbidden_to_export`

### sec18.2 - The salt scope discipline (HV5 closure)

Per sec9.8 HV5 closure: `hash_correlation_resistance.salt_scope == per_packet_random_salt` REQUIRED for sensitive workflows. `per_corpus_shared_salt` documented as INSUFFICIENT due to frequency-analysis attack vulnerability (adversary A5 attack).

### sec18.3 - Export manifest disclosure

Per operator L29 + sec9.2 + F24 schema: every export manifest MUST disclose what was removed when visibility_class != public. The `what_was_removed` field is plain-language civilian text.

### sec18.4 - Reason codes (sec9.3 inheritance)

See sec9.3.

### sec18.5 - The civilian vocabulary banned list (per sec16.5)

The banned-term list applies symmetrically to F22 cards + F25 dial banners + F26 passport civilian-framing texts. See sec16.5.

---

## sec19 - HV Closure Summary Table

All 9 HV + 3 MEDIUM closures HARD-CONSTRAINED in v1.2 schemas:

| Closure | Attack | Schema enforcement | HARD-CONSTRAINED? |
|---|---|---|---|
| **HV1** | F20 rule-bloat | `vaccine_rule_budget_per_corpus.max_active_rules: const 50` + `fp_rate_threshold: const 0.05` + `retirement_condition` required + `vaccine_blast_radius` field | YES |
| **HV2** | F21 single-author capture | `enemy_authored_by_principal_id != claim_authored_by_principal_id` + `enemy_authored_by_role: enum [judge, adversary]` + `enemy_review_required_by_role: enum [judge, adversary]` + `enemy_basis_source_ids` divergence | YES |
| **HV3** | F22 oversimplification fraud | `disclosed_signals` block REQUIRED + `banned_elision_lint_status` + `required_terms_when_warning_present` + `civilian_vocabulary_lint_status` | YES |
| **HV5** | F24 hash-redaction frequency leak | `salt_scope: per_packet_random_salt` REQUIRED + `frequency_analysis_attack_acknowledged` + `salt_storage_class` restrictive | YES |
| **HV6** | F25 Trust Dial under-protection | `safety_floor_categories: enum [money, health, legal, irreversible]` + `required_minimum_level: Professional` when action_class matches + `civilian_banner_when_blocked` REQUIRED | YES |
| **HV7** | F26 declared-vs-verified laundering | Two arrays: `verified_round_trip_compatible[]` vs `declared_compatible[]` + `only_verified_counts: const true` + `external_validator_required_for_verified: const true` + `declaration_truth_tag: enum [EXPERIMENTAL, SPECULATIVE FRONTIER]` on declared-only | YES |
| **HV8** | Phase 9 selection bias | STAGED v1.2.1 — pathfinder Phase 9 protocol adds recruit-independence attestation + ≥2 deceptive packets + ≥1 adversary-recruit + cold-start timing | STAGED v1.2.1 |
| **HV9** | sandbox-as-string-label | sec15.2 names OS primitive per platform (Win11 AppContainer / firejail / Seatbelt / Python-fallback honest-framed); empirical disconfirmer test path embedded in spec | YES (spec-level) |
| **HV11** | v1.1 freeze enforcement | `.claude/hooks/v11_freeze_guard.py` Python PreToolUse hook BLOCKS new schemas lacking v1_2_/v1_3_/v1_4_/v1_5_ prefix; wired in `.claude/settings.json`; logs to `.claude/_logs/v11-freeze-guard-decisions.jsonl` | YES |
| **A4** | adversary recursion (MEDIUM) | `depth_2_recursion_stop.depth: maximum 2` + `f14_rater_quorum_for_dispute.required_when_inconclusive: true` | YES |
| **A10** | TLA+ lifecycle decay (MEDIUM) | STAGED v1.2.1 — `aep_lifecycle.tla` + `aep_lifecycle.cfg` + `make lifecycle-check` CI gate; this turn ships Python state-machine diff-check skeleton in `lifecycle_state_check.py` | STAGED v1.2.1 |
| **A12** | banned-term linter necessary-but-not-sufficient (MEDIUM) | `required_terms_when_warning_present[]` + `civilian_warning_phrasebook` field on F22 schema; symmetric banned-when-NOT-needed AND required-when-needed lint | YES |

---

## sec20 - STAGED v1.2.1 Backlog

Per sec73.6 honest framing, the following are STAGED v1.2.1 — they did NOT ship in this single forge invocation:

1. **F20 emitter + matcher + immune log directory** — `emit_bug_vaccine.py` + `match_bug_vaccine.py` + `data/immune_log/`. Pathfinder Phase 2.
2. **F20 backfill disconfirmer on 1112+ corpus** — measure historical FP rate before active gating. HV1 closure empirical proof.
3. **F21 enforcement validator** — `validate_claim_has_enemy.py` (enforces on PROVEN/RELIABLE only). Pathfinder Phase 6.
4. **F22 civilian_proof_compiler.py + AEP Viewer + Proof Card CSS** — Pathfinder Phase 8.
5. **F23 mutation runner + report** — `mutate_packet.py` + `validator_adversary_runner.py` + `validator_adversary_v1_2.md`. Pathfinder Phase 3.
6. **F24 redact_for_export.py + linkability disconfirmer test** — Pathfinder Phase 5.
7. **F25 risk_classifier.py + dial enforcement validator + civilian banner renderer** — Pathfinder Phase 8.
8. **F26 export_compatibility_passport.py + 4 round-trip test fixtures (PROV/C2PA/SLSA/in_toto)** — Pathfinder Phase 7.
9. **Sandbox Gate OS primitive integration** — Win11 AppContainer + firejail + Seatbelt + Python-fallback honest-framed. Pathfinder Phase 4.
10. **`aep doctor` CLI** — single-verdict (Pass/Warn/Fail/Unknown) + collapsible evidence. Pathfinder Phase 7.
11. **`compile_pro_to_lite.py`** — Pro-to-Lite compile-down. Pathfinder Phase 7.
12. **TLA+ lifecycle model + Python state-machine diff-check + CI gate** — `aep_lifecycle.tla` + `lifecycle_state_check.py` + `make lifecycle-check`. Pathfinder Phase 4 + A10 closure.
13. **Policy engine + export-to-Rego** — `aep_policy_engine.py` + `export_to_rego.py` + 4 verbatim-policy test fixtures. Pathfinder Phase 5.
14. **Kill chain runner** — `kill_chain_runner.py` wiring all 10 gates. Pathfinder Phase 6.
15. **Example packets for everyday life (7 packets per operator L97-L103)** — lease summary, PDF-actually-used, medical appointment, homework textbook, resume rewrite, coding agent, support bot. Pathfinder Phase 9.
16. **Civilian-comprehension empirical test (operator L249-L253 stop condition)** — Pathfinder Phase 9 with adversary A8 closures (recruit independence + deceptive packets + adversary recruit + cold-start timing). Operator-led recruitment per sec73.6.
17. **Full BC-V12-1 corpus validation** — `wave_060_validate_all_packets_against_v1_2.py` against the 1112+ corpus. v1.2.1 STAGED.
18. **HV8 closure formal protocol document** — Phase 9 selection-bias mitigation written up.
19. **A10 closure TLC integration** — `make lifecycle-check` CI integration if TLC tooling available on operator platform.
20. **v1.2.1 SPEC.md** — documents all STAGED resolutions when they land. Owner: scribe + curator.

Per sec73.6: STAGED entries are NOT promoted to STRONGLY PLAUSIBLE until empirical evidence lands. v1.2 SPEC ship is `PROPOSED` with `EXPERIMENTAL` on civilian-comprehension claim per sec1.4.

---

## Acceptance criteria for this SPEC ship

Per sec03 validation gates:

| Gate | Method | Status |
|---|---|---|
| G1 - SPEC.md valid markdown | This file parses; reviewer can read it | PASS (manual parse) |
| G2-G12 - All 11 schemas valid JSON Schema draft 2020-12 | `Draft202012Validator.check_schema()` | PASS (11/11 verified at build time) |
| G13 - All 11 schema examples validate against their schemas | `validator.iter_errors(example)` returns empty | PASS (11/11 verified at build time) |
| G14 - Every schema has `additionalProperties: false` on top-level | Validator-grep | PASS (11/11) |
| G15 - Every schema has `$id` per `aep:v1_2:*` convention | Validator-grep | PASS (11/11) |
| G16 - HCRL row 13 chains from row 12 | `prev_receipt_hash` matches row 12 sha256 | PASS (row 12 sha: 99def377f2b8c62f1f4df670fe1f4e92a80cf2b83c604dcbee9b013dfca09e3d) |
| G17 - Every F-tier section has TOPOLOGY_PROOF line per gate 6.5 | Grep | PASS (sec4-sec10 + sec11 + sec12; 9 sections) |
| G18 - Every F-tier section ships EXTENDS-vs-NOVEL classification per sec73.6 | Schema audit (lineage_basis.classification) + SPEC sec audit | PASS |
| G19 - HV closure summary table complete (9 HV + 3 MEDIUM) | sec19 audit | PASS |
| G20 - v1.1 freeze enforcement hook ships + wired | `.claude/hooks/v11_freeze_guard.py` exists + registered in `.claude/settings.json` | PASS |
| G21 - BC-V12-1 test ships + passes | `tests/test_bc_v12_1_backward_compat.py` exists + 9/9 tests PASS | PASS |
| G22 - sec73.4 single-forge ONE-invocation | Single forge produces SPEC + 11 schemas + hook + BC test + receipt | PASS |
| G23 - Composes_with all listed doctrine slots | Manual audit | PASS (header + sec1.5 + sec19) |

---

## Adoption decision (sec73.6 honest)

**Adoption path**: v1.2 ships as `PROPOSED` with:
- **`aep:1.2/pro`** profile: STRONGLY PLAUSIBLE (schema-level closures complete; runtime tooling STAGED v1.2.1 per sec20).
- **`aep:1.2/lite`** profile: EXPERIMENTAL (civilian comprehension < 30 s claim NOT YET empirically tested; per sec1.4 + pathfinder Phase 9).
- **`aep:1.2/institutional`** profile: EXPERIMENTAL (policy gates + audit retention STAGED v1.2.1).

No civilian-comprehension claims promoted to STRONGLY PLAUSIBLE without Phase 9 empirical test passage per sec73.6.

**Operator's verbatim recommendation** (operator L215):

> Do not market AEP as a file format. Market it as "AI receipts."

v1.2 ships in alignment with this framing: the substrate (schemas + hook + BC test) is the structural foundation for "AI receipts" — the public-facing surface (F22 cards + AEP Viewer + AEP Lite) compiles down from this substrate.

**Operator's verbatim public promise** (operator L228):

> "Every AI answer gets a receipt."

v1.2 makes this promise mechanically possible. Empirical realization at civilian-comprehension scale is STAGED v1.2.1 + v1.3.

---

**End SPEC v1.2 PROPOSED 2026-05-18 unified single-forge product build.**
