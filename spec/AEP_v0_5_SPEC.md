# AEP v0.5 Specification

**Status**: PERFECTED (exact-science release).  
**Predecessor**: AEP v0.4 (2026-05-14 publication-ready).  
**Authors**: operator ([the AEP project](https://x.com/AEPproject)) + the agentic substrate (Claude Opus 4.7).  
**License**: Apache-2.0 (spec + reference impl), CC-BY-4.0 (prose docs).  
**Profile**: `aep:0.5/stable` and `aep:0.5/experimental`.  
**Closes**: 10 Round-2 attacks, 8 Round-3 failure modes, all cycle-2 P0 amendments.

## Abstract

AEP v0.5 defines an exact-science, machine-verifiable Agent Evidence Packet format with fail-closed semantics for provenance, integrity, freshness, inference control, and decision gating.  
This release preserves the v0.4 core model and extends it to remove undefined behavior that could permit parser split, replay, laundering, stale authority, or cross-version semantic drift.  
v0.5 is normative about canonicalization and integrity: canonical JSON behavior is explicitly pinned to RFC 8785 (JSON Canonicalization Scheme) with additional rejection constraints aligned to I-JSON safety goals, and packet integrity includes a fully-specified `AEP-MERKLE-v1` algorithm with domain separation, path normalization policy, odd-leaf handling, and empty-tree constant.  
Every fail-closed rule in validator obligations is uniquely identified and mapped to explicit conformance vectors in Appendix A.  
The result is deterministic interoperability: two conformant implementations must compute identical hashes, reach identical pass/fail outcomes, and emit equivalent violation classes for the same packet and policy profile.

## 1. Positioning

AEP is a reproducibility and governance protocol for agentic decision systems that produce claims, relations, and actions under evidence constraints.  
AEP is not a replacement for domain science; it is an integrity envelope that makes epistemic state explicit, machine-checkable, and reviewable over time.  
AEP v0.5 is optimized for high-assurance operation under adversarial and operational drift conditions.  
AEP packets are append-only event-governed bundles with canonical state surfaces and validator-run receipts.  
AEP supports multiple conformance levels and profile channels while enforcing a strict fail-closed core in production settings.

Normative goals of v0.5 are:

1. Remove parser and canonicalization ambiguity from all hash-affecting paths.
2. Prevent policy laundering from governance-only claims into unsafe `GO` actions.
3. Tie time-sensitive decisions to explicit freshness and revalidation obligations.
4. Prevent epistemic over-promotion through long inference chains without anchored basis.
5. Support version/channel evolution without semantic polyglot ambiguity.
6. Strengthen reviewer signal quality before cryptographic identity lands in v0.7.
7. Preserve v0.4 migration feasibility with explicit degradation pathways.

## 2. Design axioms (now 10, normative — add 2 v0.5 axioms)

The following axioms are normative and MUST be enforced by conformant validators at the appropriate conformance level.

1. No claim without epistemic state.
2. No epistemic upgrade without evidence or review.
3. No source without provenance strength and limits.
4. No generated view as canonical truth.
5. No mutation without append-only event receipt.
6. No graph edge without source claim or explicit inference label.
7. No time-sensitive claim without temporal scope or revalidation state.
8. No independent convergence from repeated same-source evidence.
9. **No PROVEN_RELIABLE without anchor diversity.**
10. **No decision without time-validated evidence.**

Interpretation notes:

- Axioms 1-8 are preserved verbatim from v0.4.
- Axiom 9 closes inference escalation and monoculture anchoring paths.
- Axiom 10 closes TOCTOU authority drift on decision paths.

## 3. Reliability labels (Axis A) — unchanged

Axis A reliability labels are unchanged from v0.4 and remain ordered as:

1. `PROVEN_RELIABLE`
2. `STRONGLY_PLAUSIBLE`
3. `PLAUSIBLE`
4. `ASSUMPTION`
5. `CONFLICTED`
6. `UNKNOWN`
7. `GOVERNANCE_RULE`

Normative ordering and promotion constraints:

- Reliability ordering for promotion calculations is:
`PROVEN_RELIABLE` > `STRONGLY_PLAUSIBLE` > `PLAUSIBLE` > `ASSUMPTION` > `CONFLICTED` > `UNKNOWN`.
- `GOVERNANCE_RULE` is policy-typed and is not an empirical evidence tier.
- Validators MUST treat `GOVERNANCE_RULE` as non-evidentiary for anchor diversity and minimum empirical support checks unless a profile-specific override explicitly allows otherwise.
- `CONFLICTED` and `UNKNOWN` claims MUST include structured reasoning metadata (§11).

## 4. Scope labels — unchanged

Scope labels from v0.4 are unchanged.  
Each claim MUST include a scope label from the allowed enumerated set defined by packet schema/profile policy.  
Scope labels MUST be interpreted as partitioning decision applicability, not reliability promotion authority.  
Cross-scope promotion MUST be explicit and traceable through relation records.

Normative requirements:

- Scope must be explicit on claim record.
- Absent scope is fail-closed.
- Scope override via generated view is forbidden.
- Scope mutations require append-only event receipt.

## 5. Axis B action disposition — unchanged + new mechanical rules (Attack 5)

Axis B action dispositions remain:

1. `GO`
2. `EXPERIMENT`
3. `EXPLORE`
4. `HALT`
5. `FORBIDDEN`

v0.5 adds mandatory coupling rules for `GO`:

1. `GO` on non-trivial mutation MUST have at least one non-`GOVERNANCE_RULE` evidentiary dependency in lineage DAG.
2. If a claim has `axis_b = GO` and `reliability = GOVERNANCE_RULE`, then `go_justification_claim_ids` MUST be present and non-empty.
3. Each ID in `go_justification_claim_ids` MUST resolve to a reachable claim with reliability not equal to `GOVERNANCE_RULE`.
4. In strict profile, `policy_only_go` is fail-closed unless `governance_override` is enabled and review tier `R4` is satisfied.
5. `FORBIDDEN` claims dominate conflicting `GO` claims unless a higher-tier review explicitly annotates conflict resolution.

Definitions:

- Non-trivial mutation: any action modifying external state, code, data model, deployment, access control, or financial/legal posture.
- Governance override: constrained exception mechanism for legal-hold/compliance constraints requiring tiered review.

## 6. Package identity — extended (aep_version="0.5", profile updates)

Every packet MUST contain `aepkg.json` with package identity and integrity metadata.

Required fields:

1. `packet_id` (string, immutable identifier).
2. `aep_version` (string, MUST be `"0.5"` for this spec).
3. `profile` (string enum: `aep:0.5/stable`, `aep:0.5/experimental`).
4. `producer_version` (semver string).
5. `consumer_min_version` (semver string).
6. `packet_epoch` (integer, monotonic per packet lineage).
7. `supersedes_packet_id` (string or null).
8. `manifest_hash` (string, lowercase hex SHA-256 of canonical manifest object).
9. `state_hash` (string, lowercase hex SHA-256 over canonical state envelope).
10. `assets_merkle_root` (string, lowercase hex SHA-256 from `AEP-MERKLE-v1`).
11. `path_case_policy` (enum: `preserve` or `lowercase`).
12. `created_at` (RFC 3339 timestamp, UTC recommended).
13. `channel` (alias of profile channel semantics; MAY equal `profile` exactly).
14. `extensions` (array of extension declarations).
15. `execution_inputs_manifest` (optional object in experimental/reproducibility contexts).

Normative identity rules:

- `packet_epoch` MUST be strictly increasing when `supersedes_packet_id` is non-null.
- Reuse of older packet with lower epoch for same lineage in `GO` contexts is stale by policy unless explicitly allowed for exploratory dispositions.
- `producer_version` and `consumer_min_version` are required on every record type (§21).

JSON Schema fragment (illustrative, normative constraints in prose + schema tooling):

```json
{
  "$id": "https://aep.dev/schema/0.5/aepkg.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "packet_id",
    "aep_version",
    "profile",
    "producer_version",
    "consumer_min_version",
    "packet_epoch",
    "manifest_hash",
    "state_hash",
    "assets_merkle_root",
    "path_case_policy",
    "created_at",
    "extensions"
  ],
  "properties": {
    "packet_id": { "type": "string", "minLength": 1 },
    "aep_version": { "type": "string", "const": "0.5" },
    "profile": { "type": "string", "enum": ["aep:0.5/stable", "aep:0.5/experimental"] },
    "producer_version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+([-.+][A-Za-z0-9.-]+)?$" },
    "consumer_min_version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+([-.+][A-Za-z0-9.-]+)?$" },
    "packet_epoch": { "type": "integer", "minimum": 0 },
    "supersedes_packet_id": { "type": ["string", "null"] },
    "manifest_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "state_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "assets_merkle_root": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "path_case_policy": { "type": "string", "enum": ["preserve", "lowercase"] },
    "created_at": { "type": "string", "format": "date-time" },
    "channel": { "type": "string" },
    "extensions": {
      "type": "array",
      "items": { "$ref": "#/$defs/extensionDecl" }
    },
    "execution_inputs_manifest": { "type": "object" }
  },
  "$defs": {
    "extensionDecl": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "name",
        "version",
        "semantic_stability",
        "min_consumer_version",
        "max_tested_version",
        "affects_decision_semantics"
      ],
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" },
        "semantic_stability": { "type": "string", "enum": ["experimental", "stable", "deprecated"] },
        "min_consumer_version": { "type": "string" },
        "max_tested_version": { "type": "string" },
        "affects_decision_semantics": { "type": "boolean" }
      }
    }
  }
}
```

## 7. Canonical files — unchanged

Canonical file set included in `state_hash` remains:

1. `data/sources.jsonl`
2. `data/spans.jsonl`
3. `data/claims.jsonl`
4. `data/relations.jsonl`
5. `ops/events.jsonl`
6. `reviews/reviews.jsonl`
7. `validations/runs.jsonl`
8. `aepkg.json`
9. `assets/**` via `assets_merkle_root`
10. `manifest_hash` as declared in `aepkg.json`

Normative:

- Omission of any canonical file path is fail-closed.
- Inclusion of extra non-canonical files is permitted but ignored for `state_hash` unless declared in `execution_inputs_manifest` (experimental Level-3).
- `assets/**` integrity is represented by Merkle root, not direct concatenation hash.

## 8. JSONL record rules — ADD strict-canonical profile (Attack 1)

Each `.jsonl` canonical record file MUST satisfy:

1. UTF-8 encoding only.
2. LF line endings only (`\n`).
3. No UTF-8 BOM.
4. One JSON object per line.
5. No trailing commas or comments.
6. No blank lines in canonical record files.
7. Record objects MUST pass strict canonical JSON profile (§17).
8. Duplicate keys in any object depth are forbidden.
9. Numeric values MUST be finite JSON numbers, never NaN/Infinity.
10. Hash-affecting canonical bytes MUST be derived from strict AST re-serialization (§17.6), not raw source bytes.

Record common envelope fields (required on every record line across sources/spans/claims/relations/events/reviews/runs):

1. `id` (string)
2. `aep_version` (string, MUST be `"0.5"`)
3. `producer_version` (string semver)
4. `consumer_min_version` (string semver)
5. `created_at` (RFC 3339 timestamp)
6. `schema_uri` (string URI)
7. `record_type` (enum by file)
8. `packet_id` (string matching `aepkg.json`)

Common envelope schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/common-envelope.json",
  "type": "object",
  "additionalProperties": true,
  "required": [
    "id",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "schema_uri",
    "record_type",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string", "minLength": 1 },
    "aep_version": { "type": "string", "const": "0.5" },
    "producer_version": { "type": "string" },
    "consumer_min_version": { "type": "string" },
    "created_at": { "type": "string", "format": "date-time" },
    "schema_uri": { "type": "string", "format": "uri" },
    "record_type": { "type": "string" },
    "packet_id": { "type": "string", "minLength": 1 }
  }
}
```

## 9. Source record — extended (Attack 4 trust context)

Source record purpose: represent provenance-bearing sources that ground claims.

Required core fields:

1. `id`
2. `record_type` = `source`
3. `source_kind` (enum: `url`, `git`, `asset`, `human_report`, `other`)
4. `provenance_strength` (enum aligned to policy)
5. `limits` (array of strings)
6. `anchors` (array, non-empty for anchored kinds)
7. `same_source_fingerprint` (string)
8. `retrieval_time` (timestamp)
9. `trust_context` (object for `url`/`git` kinds)

Anchor requirements by kind:

- `asset`: must include `asset_path`, `asset_sha256`, and path participation in assets Merkle set.
- `git`: must include immutable commit SHA and trust context fields below.
- `url`: must include URL + location hash + trust context fields below.

`git` trust context required fields:

1. `remote_url` (string URI)
2. `immutable_sha` (40-hex git commit id)
3. `trusted_root_policy` (string policy id)
4. `reachability_evidence` (object, includes trusted ref and proof snapshot)

Optional `git` trust fields:

1. `signed_tag` (string)
2. `sig_verification` (object)
3. `two_fetch_quorum` (boolean)

`url` trust context required fields:

1. `scheme` (enum: `https`, `http`, `ipfs`, `other`)
2. `host` (string)
3. `fetch_agent_id` (string)
4. `location_hash` (SHA-256 of byte range/location binding)

Optional `url` trust fields:

1. `tls_fingerprint` (string)
2. `transparency_proof` (object)
3. `two_fetch_quorum` (boolean)

Source schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/source-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "source_kind",
    "provenance_strength",
    "limits",
    "anchors",
    "same_source_fingerprint",
    "retrieval_time",
    "trust_context",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "source" },
    "source_kind": { "type": "string", "enum": ["url", "git", "asset", "human_report", "other"] },
    "provenance_strength": { "type": "string" },
    "limits": { "type": "array", "items": { "type": "string" } },
    "anchors": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/anchor" }
    },
    "same_source_fingerprint": { "type": "string", "minLength": 1 },
    "retrieval_time": { "type": "string", "format": "date-time" },
    "trust_context": { "$ref": "#/$defs/trustContext" }
  },
  "$defs": {
    "anchor": {
      "type": "object",
      "additionalProperties": false,
      "required": ["anchor_type"],
      "properties": {
        "anchor_type": { "type": "string", "enum": ["url", "git", "asset"] },
        "url": { "type": "string", "format": "uri" },
        "location_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
        "git_ref": { "type": "string" },
        "immutable_sha": { "type": "string", "pattern": "^[a-f0-9]{40}$" },
        "asset_path": { "type": "string" },
        "asset_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
      }
    },
    "trustContext": {
      "type": "object",
      "additionalProperties": true,
      "required": ["kind"],
      "properties": {
        "kind": { "type": "string", "enum": ["url", "git", "asset", "other"] },
        "remote_url": { "type": "string", "format": "uri" },
        "trusted_root_policy": { "type": "string" },
        "reachability_evidence": { "type": "object" },
        "signed_tag": { "type": "string" },
        "scheme": { "type": "string" },
        "host": { "type": "string" },
        "tls_fingerprint": { "type": "string" },
        "fetch_agent_id": { "type": "string" },
        "transparency_proof": { "type": "object" },
        "two_fetch_quorum": { "type": "boolean" }
      }
    }
  }
}
```

Normative trust rules:

- For `PROVEN_RELIABLE` claims referencing `git`/`url` anchors, trust context fields above are mandatory.
- Missing trust context on required anchored kinds is fail-closed in Level-2 and higher.
- `two_fetch_quorum` MAY be required by profile for high-criticality domains.

## 10. Span record — unchanged

Span records identify source-local evidence spans used by claims.

Required fields:

1. `id`
2. `record_type` = `span`
3. `source_id`
4. `locator` (offset/range/path selector object)
5. `extract_hash` (SHA-256 of normalized extracted bytes)
6. `normalization_method` (string)
7. `notes` (optional string)

Normative:

- `source_id` MUST resolve to an existing source record.
- `locator` syntax MUST be deterministic and unambiguous within source kind.
- `extract_hash` mismatch on recomputation is fail-closed for anchored claims.

Span schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/span-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "source_id",
    "locator",
    "extract_hash",
    "normalization_method",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "span" },
    "source_id": { "type": "string" },
    "locator": { "type": "object" },
    "extract_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "normalization_method": { "type": "string" },
    "notes": { "type": "string" }
  }
}
```

## 11. Claim record — extended (Attack 5 go_justification, Attack 9 decision_time_revalidation, Attack 6 transitive constraints)

Claim record is the primary epistemic unit.

Required fields:

1. `id`
2. `record_type` = `claim`
3. `claim_text` (string)
4. `axis_a_reliability` (enum in §3)
5. `axis_b_disposition` (enum in §5)
6. `scope_label` (string enum by policy)
7. `basis` (array of basis refs; rules vary by reliability)
8. `epistemic_state` (object)
9. `temporal_scope` (object)
10. `lineage_requirements` (object)
11. `decision_constraints` (object)

New v0.5 fields:

1. `go_justification_claim_ids` (array of claim IDs, required for policy-only GO cases).
2. `decision_time_revalidation_required` (boolean).
3. `revalidate_after` (timestamp or null).
4. `valid_from` (timestamp or null).
5. `valid_until` (timestamp or null).
6. `freshness_class` (enum: `static`, `periodic`, `volatile`).
7. `requires_anchor_diversity` (boolean; default true for `PROVEN_RELIABLE`).
8. `promotion_override_review_ids` (array; only valid with sufficient review tier).
9. `inference_lineage_checked` (boolean).
10. `conformance_run_id` (optional string, validator-supplied for external-anchor verification).

Claim schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/claim-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "claim_text",
    "axis_a_reliability",
    "axis_b_disposition",
    "scope_label",
    "basis",
    "epistemic_state",
    "temporal_scope",
    "lineage_requirements",
    "decision_constraints",
    "decision_time_revalidation_required",
    "inference_lineage_checked",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "claim" },
    "claim_text": { "type": "string", "minLength": 1 },
    "axis_a_reliability": {
      "type": "string",
      "enum": [
        "PROVEN_RELIABLE",
        "STRONGLY_PLAUSIBLE",
        "PLAUSIBLE",
        "ASSUMPTION",
        "CONFLICTED",
        "UNKNOWN",
        "GOVERNANCE_RULE"
      ]
    },
    "axis_b_disposition": {
      "type": "string",
      "enum": ["GO", "EXPERIMENT", "EXPLORE", "HALT", "FORBIDDEN"]
    },
    "scope_label": { "type": "string" },
    "basis": {
      "type": "array",
      "items": { "$ref": "#/$defs/basisRef" }
    },
    "epistemic_state": { "type": "object" },
    "temporal_scope": { "$ref": "#/$defs/temporalScope" },
    "lineage_requirements": { "type": "object" },
    "decision_constraints": { "type": "object" },
    "go_justification_claim_ids": {
      "type": "array",
      "items": { "type": "string" }
    },
    "decision_time_revalidation_required": { "type": "boolean" },
    "revalidate_after": { "type": ["string", "null"], "format": "date-time" },
    "valid_from": { "type": ["string", "null"], "format": "date-time" },
    "valid_until": { "type": ["string", "null"], "format": "date-time" },
    "freshness_class": { "type": "string", "enum": ["static", "periodic", "volatile"] },
    "requires_anchor_diversity": { "type": "boolean" },
    "promotion_override_review_ids": {
      "type": "array",
      "items": { "type": "string" }
    },
    "inference_lineage_checked": { "type": "boolean" },
    "conformance_run_id": { "type": "string" }
  },
  "$defs": {
    "basisRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["basis_type", "ref_id"],
      "properties": {
        "basis_type": { "type": "string", "enum": ["source", "span", "claim", "review"] },
        "ref_id": { "type": "string" },
        "same_source_fingerprint": { "type": "string" }
      }
    },
    "temporalScope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["is_time_sensitive"],
      "properties": {
        "is_time_sensitive": { "type": "boolean" },
        "valid_from": { "type": ["string", "null"], "format": "date-time" },
        "valid_until": { "type": ["string", "null"], "format": "date-time" },
        "revalidate_after": { "type": ["string", "null"], "format": "date-time" }
      }
    }
  }
}
```

Normative claim rules:

- `PROVEN_RELIABLE` MUST have non-empty `basis`.
- `PROVEN_RELIABLE` basis must include at least one external-anchor-qualifying basis unless claim is `GOVERNANCE_RULE`.
- `UNKNOWN` MUST include explicit reasoning details.
- `GO` + `GOVERNANCE_RULE` requires `go_justification_claim_ids` and policy checks.
- If `decision_time_revalidation_required` is true and `now > revalidate_after`, claim is stale for GO decisions.
- `valid_from` and `valid_until` boundaries are hard validity gates for time-sensitive claims.
- `inference_lineage_checked` MUST be true for Level-2/3 conformance on `GO` claims.

## 12. Relation record — extended (Attack 6 inference-hop decay rules)

Relation records define directed edges in evidence and reasoning DAG.

Required fields:

1. `id`
2. `record_type` = `relation`
3. `from_claim_id`
4. `to_claim_id`
5. `relation_type`
6. `inference_class`
7. `is_inference_only` (boolean)
8. `hop_index` (integer >= 1 for chain-local indexing)
9. `weight` (number in [0,1], optional but recommended)
10. `notes` (optional)

Allowed `relation_type` includes (non-exhaustive): `supports`, `contradicts`, `derives`, `reframes`, `supersedes`.

Inference classes:

1. `direct_evidence`
2. `architectural_inference`
3. `analogical_transfer`
4. `cross_packet_synthesis`
5. `other_inference`

Normative transitive constraints:

1. Default no-upgrade rule: terminal reliability must be <= min reliability across dependency DAG unless override via qualified review evidence.
2. Hop decay rule: for inference-only edges of class `architectural_inference`, `analogical_transfer`, `cross_packet_synthesis`, apply one-tier decay for each hop beyond two.
3. If lineage to `PROVEN_RELIABLE` includes any inference-only chain without at least one direct anchored basis edge into the terminal claim’s support set, fail-closed.
4. Mixed chains with both direct evidence and inference edges MAY retain higher tier if direct anchored basis independently supports terminal claim.

Relation schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/relation-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "from_claim_id",
    "to_claim_id",
    "relation_type",
    "inference_class",
    "is_inference_only",
    "hop_index",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "relation" },
    "from_claim_id": { "type": "string" },
    "to_claim_id": { "type": "string" },
    "relation_type": { "type": "string" },
    "inference_class": {
      "type": "string",
      "enum": [
        "direct_evidence",
        "architectural_inference",
        "analogical_transfer",
        "cross_packet_synthesis",
        "other_inference"
      ]
    },
    "is_inference_only": { "type": "boolean" },
    "hop_index": { "type": "integer", "minimum": 1 },
    "weight": { "type": "number", "minimum": 0, "maximum": 1 },
    "notes": { "type": "string" }
  }
}
```

## 13. Write event record — extended (Attack 3 freshness)

Write events govern append-only mutation history.

Required fields:

1. `id`
2. `record_type` = `write_event`
3. `event_type` (enum includes `append_claim`, `append_relation`, `revalidation_event`, `supersede_packet`, `review_attach`)
4. `event_time` (timestamp)
5. `actor_id` (string)
6. `prev_event_hash` (string hash or null for genesis)
7. `event_hash` (string hash over canonical event object)
8. `packet_epoch` (integer)
9. `supersedes_packet_id` (string or null)
10. `state_hash_after` (string)

Revalidation event (`event_type = revalidation_event`) required subfields:

1. `target_claim_id`
2. `revalidated_anchor_ids` (array)
3. `revalidation_method` (string)
4. `revalidation_result` (enum: `pass`, `fail`, `indeterminate`)
5. `conformance_run_id` (optional but recommended)
6. `next_revalidate_after` (timestamp or null)

Event schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/write-event-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "event_type",
    "event_time",
    "actor_id",
    "prev_event_hash",
    "event_hash",
    "packet_epoch",
    "state_hash_after",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "write_event" },
    "event_type": {
      "type": "string",
      "enum": ["append_claim", "append_relation", "revalidation_event", "supersede_packet", "review_attach"]
    },
    "event_time": { "type": "string", "format": "date-time" },
    "actor_id": { "type": "string" },
    "prev_event_hash": { "type": ["string", "null"], "pattern": "^[a-f0-9]{64}$" },
    "event_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "packet_epoch": { "type": "integer", "minimum": 0 },
    "supersedes_packet_id": { "type": ["string", "null"] },
    "state_hash_after": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "revalidation_payload": { "type": "object" }
  }
}
```

Freshness/replay invariants:

- For same lineage, decreasing `packet_epoch` relative to already-known packet is stale.
- `supersedes_packet_id` chain continuity MUST be acyclic.
- Replayed packet with valid old hashes but expired temporal validity fails GO policy.
- `event_hash` chain mismatch is fail-closed.

## 14. Review receipt — extended (Attack 8 weighted review, reviewer fingerprints)

Review receipts attach human/agent review judgments and confidence.

Required fields:

1. `id`
2. `record_type` = `review`
3. `target_ids` (array of claim/relation/event IDs)
4. `review_tier` (enum: `R1`, `R2`, `R3`, `R4`)
5. `decision` (enum: `approve`, `reject`, `needs_changes`)
6. `reviewer_identity` (object)
7. `reviewer_capability_manifest` (object)
8. `reviewer_fingerprint` (string)
9. `identity_verification_level` (enum: `verified`, `unverified`)
10. `weight_assigned` (number)

Sybil-hardening interim rules:

1. Unverified reviewer max weight default 0.5.
2. Verified reviewer default max weight 1.0.
3. Profile policy MAY alter thresholds but cannot exceed 0.5 for unverified in strict GO gating.
4. GO consensus threshold MUST NOT be satisfiable solely by unverified identities in strict profile.
5. Capability manifest must include toolchain fingerprint, execution environment digest, and attestation mode.

Review schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/review-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "target_ids",
    "review_tier",
    "decision",
    "reviewer_identity",
    "reviewer_capability_manifest",
    "reviewer_fingerprint",
    "identity_verification_level",
    "weight_assigned",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "review" },
    "target_ids": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string" }
    },
    "review_tier": { "type": "string", "enum": ["R1", "R2", "R3", "R4"] },
    "decision": { "type": "string", "enum": ["approve", "reject", "needs_changes"] },
    "reviewer_identity": { "type": "object" },
    "reviewer_capability_manifest": { "type": "object" },
    "reviewer_fingerprint": { "type": "string", "minLength": 1 },
    "identity_verification_level": { "type": "string", "enum": ["verified", "unverified"] },
    "weight_assigned": { "type": "number", "minimum": 0, "maximum": 1.0 },
    "rationale": { "type": "string" }
  }
}
```

## 15. Validation run — unchanged

Validation runs record conformance execution results for a packet/profile.

Required fields:

1. `id`
2. `record_type` = `validation_run`
3. `validator_id`
4. `validator_version`
5. `profile`
6. `conformance_level`
7. `started_at`
8. `finished_at`
9. `result` (`pass`/`fail`)
10. `violations` (array of violation objects)
11. `state_hash_observed`
12. `manifest_hash_observed`
13. `assets_merkle_root_observed`
14. `conformance_run_id` (optional, recommended when external anchor measurements are performed)

Normative:

- Violation objects MUST include `rule_id`, `severity`, `record_id` where applicable, and deterministic `details`.
- Multiple validators MAY produce independent runs; a run does not overwrite prior runs.
- Conformance results are profile-scoped.

Validation run schema fragment:

```json
{
  "$id": "https://aep.dev/schema/0.5/validation-run-record.json",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "id",
    "record_type",
    "validator_id",
    "validator_version",
    "profile",
    "conformance_level",
    "started_at",
    "finished_at",
    "result",
    "violations",
    "state_hash_observed",
    "manifest_hash_observed",
    "assets_merkle_root_observed",
    "aep_version",
    "producer_version",
    "consumer_min_version",
    "created_at",
    "packet_id"
  ],
  "properties": {
    "id": { "type": "string" },
    "record_type": { "type": "string", "const": "validation_run" },
    "validator_id": { "type": "string" },
    "validator_version": { "type": "string" },
    "profile": { "type": "string", "enum": ["aep:0.5/stable", "aep:0.5/experimental"] },
    "conformance_level": { "type": "string", "enum": ["L1", "L2", "L3"] },
    "started_at": { "type": "string", "format": "date-time" },
    "finished_at": { "type": "string", "format": "date-time" },
    "result": { "type": "string", "enum": ["pass", "fail"] },
    "violations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["rule_id", "severity", "message"],
        "properties": {
          "rule_id": { "type": "string" },
          "severity": { "type": "string", "enum": ["error", "warning"] },
          "message": { "type": "string" },
          "record_id": { "type": "string" }
        }
      }
    },
    "state_hash_observed": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "manifest_hash_observed": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "assets_merkle_root_observed": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "conformance_run_id": { "type": "string" }
  }
}
```

## 16. Integrity (now formal) — ADD AEP-MERKLE-v1 with full algorithm + test vectors (Attack 2)

### 16.1 Overview

`AEP-MERKLE-v1` is the normative algorithm for computing `assets_merkle_root`.  
All implementations MUST produce byte-identical root values for the same `assets/**` set and `path_case_policy`.

### 16.2 Inputs

Inputs to `AEP-MERKLE-v1`:

1. Ordered set of assets under `assets/**`.
2. For each asset:
- Relative path from packet root.
- File byte content.
3. `path_case_policy` from `aepkg.json`.

### 16.3 Path normalization

For each asset path:

1. Convert separators to `/`.
2. Disallow `.` and `..` path segments.
3. Disallow leading `/`.
4. Normalize Unicode to NFC.
5. Apply case policy:
- `preserve`: keep normalized case.
- `lowercase`: ASCII lowercase A-Z only; non-ASCII unaffected.
6. Encode normalized path as UTF-8 bytes.

If two assets collapse to same normalized path after policy application, fail-closed.

### 16.4 Leaf hash

For each asset:

1. Compute `file_bytes_hash = sha256(file_bytes)` as 32-byte binary digest.
2. Compute leaf preimage bytes:

`"AEP_LEAF\n" || normalized_path_utf8 || "\n" || hex_lower(file_bytes_hash)`

3. Leaf hash is:

`leaf_hash = sha256(leaf_preimage_bytes)`

Hex presentation MUST be lowercase.

### 16.5 Leaf ordering

Sort leaves by lexicographic byte order of `normalized_path_utf8`.  
Stable sorting required.

### 16.6 Internal node hash

Given left and right child hashes in 32-byte binary:

1. Convert each to lowercase hex string.
2. Node preimage:

`"AEP_NODE\n" || left_hex || right_hex`

3. Node hash:

`node_hash = sha256(node_preimage_bytes)`

### 16.7 Odd-node handling

At each tree level, if node count is odd and count > 1, duplicate the last node and hash pair(last,last).  
This rule is mandatory and frozen for v1.

### 16.8 Empty tree constant

If asset set is empty, root is:

`sha256("AEP_EMPTY")`

using exact ASCII bytes of `AEP_EMPTY` (no newline).  
Hex lowercase output is the canonical empty root.

### 16.9 One-asset case

If exactly one leaf exists, root = that leaf hash (no additional internal hash).

### 16.10 Algorithm pseudocode

```text
function aep_merkle_v1(assets, path_case_policy):
  normalized = []
  for asset in assets:
    p = normalize_path(asset.path, path_case_policy)
    if p already seen: fail path_collision_after_normalization
    h_file = sha256(asset.bytes)        // binary
    pre = bytes("AEP_LEAF\n") + utf8(p) + bytes("\n") + ascii(hex(h_file))
    h_leaf = sha256(pre)                // binary
    normalized.append((p, h_leaf))

  if normalized.length == 0:
    return hex(sha256(bytes("AEP_EMPTY")))

  sort normalized by utf8(p) ascending
  level = [h_leaf for each entry in normalized]

  while level.length > 1:
    next = []
    i = 0
    while i < level.length:
      left = level[i]
      right = level[i+1] if i+1 < level.length else level[i]
      pre = bytes("AEP_NODE\n") + ascii(hex(left)) + ascii(hex(right))
      next.append(sha256(pre))
      i += 2
    level = next

  return hex(level[0])
```

### 16.11 Integrity envelope composition

`state_hash` computation must include:

1. Canonical serialization/hashing of canonical JSONL record sets and `aepkg.json`.
2. `manifest_hash`.
3. `assets_merkle_root` from `AEP-MERKLE-v1`.

The exact state hash composition for v0.5:

`state_hash = sha256( JCS( state_envelope_object ) )`

where `state_envelope_object` includes canonical file hashes + `manifest_hash` + `assets_merkle_root` fields with deterministic keys.

### 16.12 Worked examples linkage

Worked vectors for 0-5 assets are normative in Appendix A.2.

## 17. Strict JSON canonical profile (NEW) — full RFC 8785 reference + extra constraints (Attack 1)

### 17.1 Normative base

AEP v0.5 canonical JSON profile is based on:

1. RFC 8785 (JSON Canonicalization Scheme, JCS) for canonical serialization.
2. RFC 7493 (I-JSON) safety constraints where relevant.

Reference:

- RFC 8785: canonical member ordering, UTF-8, deterministic number and string serialization.
- RFC 7493: interoperability subset constraints and avoidance of non-portable constructs.

### 17.2 Mandatory parser constraints (pre-AST)

Before canonicalization, parser MUST reject:

1. Duplicate object member names at any object depth.
2. `NaN`, `Infinity`, `-Infinity` tokens (not valid JSON; some parsers admit them).
3. Leading BOM.
4. Invalid UTF-8 byte sequences.
5. Surrogate misuse in strings (invalid Unicode scalar representations).

### 17.3 Numeric constraints

Numbers MUST satisfy all:

1. Parse as finite IEEE-754 representable numbers if implementation uses floating backend, or precise decimal path with equivalent JCS output.
2. Canonical output must follow RFC 8785 number rules.
3. `-0` and `0` canonicalize to JCS-compliant representation with no sign for zero.
4. Exponent and decimal notation must exactly match JCS serializer output.
5. Integers outside interoperable bounds SHOULD be represented as strings in schema when precision matters; validators MUST not silently round and continue in hash-affecting fields.

### 17.4 String constraints

Strings MUST:

1. Be Unicode scalar sequences.
2. Canonicalize escapes per RFC 8785.
3. Preserve semantic code points after parser decode.
4. Disallow parser-specific non-standard escape forms.

Normalization note:

- JSON string value normalization is not Unicode normalization; path normalization for Merkle is separate (§16.3 NFC requirement).

### 17.5 Object member ordering

Canonical serialization MUST order object member names lexicographically by Unicode code point order as defined by RFC 8785.

### 17.6 Hashing rule (critical)

For every hash-affecting JSON object (record line object, manifest object, state envelope object), validator MUST:

1. Parse with strict parser constraints (§17.2-§17.4).
2. Produce strict AST.
3. Serialize AST with RFC 8785 canonical serializer.
4. Hash serialized bytes.

Validators MUST NOT hash:

- Raw input bytes.
- Pretty-printed equivalents.
- Parser-specific internal object order without canonical re-serialization.

### 17.7 JSONL canonical line handling

For each JSONL line:

1. Parse strict.
2. Canonicalize to RFC 8785 bytes.
3. Hash canonical line bytes.
4. Build file-level digest as deterministic concatenation of line hashes with LF separators or as schema-defined object map (implementation must be deterministic and profile-documented).

### 17.8 Deviations and additions relative to plain RFC 8785

AEP profile is stricter than plain JCS in these ways:

1. Explicit duplicate-key rejection is mandatory (some parsers otherwise last-key-wins).
2. BOM rejection is mandatory.
3. JSONL format constraints apply (one object per line, no blank lines).
4. Numeric precision governance for schema-critical fields is mandated (no silent overflow/rounding acceptance).
5. Hash-affecting fields may be additionally typed/pattern-constrained by schema and are fail-closed on mismatch.

### 17.9 Canonical profile identifier

Profile ID string: `aep-json-canonical-profile:v1`  
This identifier SHOULD appear in validator metadata and MAY appear in packet metadata for explicit toolchain pinning.

## 18. Threat model (v0.5 substantial rewrite)

### 18.1 Scope

Threat model covers integrity, provenance, freshness, inference, review, and compatibility attacks against packet-based decision systems.

### 18.2 Adversary classes

1. Parser differential attacker.
2. Supply-chain/source mutability attacker.
3. Replay/staleness attacker.
4. Governance laundering attacker.
5. Inference inflation attacker.
6. Version polyglot attacker.
7. Review Sybil attacker.
8. TOCTOU attacker.
9. Coverage evasion attacker.

### 18.3 Attack-to-control mapping

Round-2 Attack 1 — Canonicalization Differential:

- Control: §8 strict JSONL rules, §17 canonical profile, fail-closed F001/F002/F003/F004/F005.
- Outcome: parser split eliminated under conformant implementations.

Round-2 Attack 2 — Assets Merkle Ambiguity:

- Control: §16 `AEP-MERKLE-v1`, domain separation, path normalization, odd-leaf freezing, empty constant.
- Outcome: deterministic root across implementations.

Round-2 Attack 3 — Cross-Packet Replay/Stale Authority:

- Control: §6 packet epoch/supersession, §11 temporal fields, §13 replay/freshness events.
- Outcome: stale replay blocked for GO under strict policy.

Round-2 Attack 4 — Anchor Mutability Confusion:

- Control: §9 trust context requirements for URL/git anchors, optional quorum.
- Outcome: hash-only anchors without trust context fail in strict conformance.

Round-2 Attack 5 — GO-path Laundering via GOVERNANCE_RULE:

- Control: §5 GO coupling, §11 go_justification_claim_ids, §23 `policy_only_go`.
- Outcome: governance-only GO blocked absent empirical dependency or R4 override.

Round-2 Attack 6 — Inference Label Escalation:

- Control: §12 no-upgrade + hop decay + anchored basis requirement.
- Outcome: PROVEN escalation from weak/inference-only lineage blocked.

Round-2 Attack 7 — Schema-Version Polyglot:

- Control: §21 channel strategy + extension stability + min/max version fields.
- Outcome: incompatible semantics fail-closed in strict profile.

Round-2 Attack 8 — Review Signal Gaming (Sybil):

- Control: §14 fingerprint/capability manifest + weighted caps.
- Outcome: unverified-only consensus cannot authorize strict GO.

Round-2 Attack 9 — TOCTOU on External Anchors:

- Control: §11 decision-time revalidation fields + §13 revalidation events.
- Outcome: stale-at-decision-time fails GO when required.

Round-2 Attack 10 — State-Hash Coverage Evasion:

- Control: optional §6 `execution_inputs_manifest`, §23 warning/fail policy by level.
- Outcome: declared side-input reproducibility strengthened; undeclared input use flagged.

### 18.4 Residual risks

1. Pre-v0.7 reviewer identity is hardened but not cryptographically final.
2. URL trust still depends on broader PKI/trust stack if transparency proofs absent.
3. Domain correctness of claim content remains outside protocol guarantee.
4. Optional execution input coverage in Level-2 leaves potential blind spots unless Level-3 adopted.

## 19. Promotion rule (clarified + axiom 9 + axiom 10)

Promotion rule determines allowed reliability for terminal claims.

### 19.1 Base no-upgrade rule

Without qualified override, terminal claim reliability MUST NOT exceed minimum reliability among supporting lineage claims.

### 19.2 Qualified override path

Upgrade above min lineage reliability is allowed only when:

1. Additional direct anchored basis supports the terminal claim, or
2. Review evidence of tier >= R3 justifies methodological override, and
3. Override evidence itself satisfies freshness and provenance requirements.

### 19.3 Anchor diversity requirement (Axiom 9)

For `PROVEN_RELIABLE` terminal claims:

1. Must include at least one external anchor-qualified basis as defined in §9 and §11.
2. Must not rely solely on repeated same-source fingerprints.
3. If all basis entries collapse to one same-source fingerprint, claim cannot exceed `STRONGLY_PLAUSIBLE`.

### 19.4 Time validation requirement (Axiom 10)

For decision-effective claims (`axis_b = GO`):

1. If time-sensitive, claim must be within `[valid_from, valid_until]` when those bounds exist.
2. If `decision_time_revalidation_required = true`, `revalidate_after` must not be exceeded at decision time without a passing revalidation event.

### 19.5 Inference decay integration

Inference-only hops beyond two reduce eligible maximum tier by one tier per hop classed as decay-applicable inference (§12).

### 19.6 Conflict with FORBIDDEN/HALT

A `FORBIDDEN` claim with valid lineage and sufficient review weight dominates contradictory `GO` unless explicit override at tier `R4`.

## 20. Conformance test suite (NEW) — test vector appendix

AEP v0.5 defines a normative conformance suite:

1. Parser and canonicalization vectors (§A.1).
2. Merkle vectors (§A.2).
3. Event chain and replay vectors (§A.3).
4. Inference DAG decay vectors (§A.4).
5. GO coupling and governance laundering vectors (§A.5).
6. Version and migration vectors (§A.6).

Conformance requirements:

- A validator is conformant only if all mandatory vectors for claimed level/profile pass.
- Test harness outputs MUST include deterministic rule IDs for failures.
- Optional vectors may be marked warning-only by conformance level, but mandatory fail-closed vectors cannot be downgraded.

## 21. Versioning + compatibility matrix (NEW) — semver + channel + extension registry (Attack 7, cycle-2 #1 & #2)

### 21.1 Channel strategy

Defined channels:

1. `aep:0.5/stable`:
- Frozen feature set for production tooling.
- No unstable decision-affecting extension permitted.
- Strict fail-closed semantics for listed mandatory controls.

2. `aep:0.5/experimental`:
- Opt-in features.
- Features may migrate to stable in future minor/major updates.
- Must declare extension stability and version bounds.

### 21.2 Record-level version fields

Every record MUST carry:

1. `aep_version`
2. `producer_version`
3. `consumer_min_version`

Packet-level tooling MAY reject if any record version envelope is missing or inconsistent.

### 21.3 Semver policy

1. Patch (`x.y.z`): non-semantic clarifications and bugfixes, no hash-affecting format changes.
2. Minor (`x.y+1.0`): additive fields/behaviors backward-compatible for consumers honoring unknown-field policy where permitted.
3. Major (`x+1.0.0`): hash-affecting canonicalization/integrity changes or semantics that could alter validator pass/fail outcomes on unchanged data.

### 21.4 Extension registry model

Each extension declaration MUST include:

1. `name`
2. `version`
3. `semantic_stability` (`experimental`/`stable`/`deprecated`)
4. `min_consumer_version`
5. `max_tested_version`
6. `affects_decision_semantics` (boolean)

Strict profile behavior:

- If `affects_decision_semantics = true` and `semantic_stability != stable`, fail-closed in `aep:0.5/stable`.
- In `aep:0.5/experimental`, unstable decision-affecting extensions are allowed with explicit warning and policy opt-in.

### 21.5 Producer/consumer compatibility

Consumer MUST reject packet if:

1. `aep_version` unsupported.
2. Consumer version < record `consumer_min_version`.
3. Extension compatibility bounds exclude consumer.
4. Packet profile channel not supported.

### 21.6 Compatibility matrix reference

Detailed tables are in Appendix B.

## 22. Migration v0.4 → v0.5 (NEW) — what changes, what's compatible, what breaks

### 22.1 Migration guarantee

Every valid v0.4 packet can be transformed into a syntactically valid v0.5 packet.  
Conformance level may degrade if new mandatory evidence is unavailable.

### 22.2 Direct carry-forward fields

Unchanged carry-forward:

1. Reliability labels (§3).
2. Axis B labels (§5).
3. Canonical file set (§7).
4. Core append-only event structure.

### 22.3 Required additions for v0.5 compliance

Additions required:

1. `aep_version = "0.5"` on all records and `aepkg.json`.
2. `producer_version`, `consumer_min_version` on every record.
3. `profile` channel field in packet identity.
4. `path_case_policy` in packet identity.
5. Strict canonical JSON profile enforcement.
6. Trust context fields for URL/git anchors tied to PROVEN claims.
7. Freshness fields where claims are time-sensitive.
8. GO governance coupling fields (`go_justification_claim_ids`) where applicable.

### 22.4 Potential breakpoints

1. Duplicate keys previously tolerated by parsers now fail.
2. Numeric edge representations accepted by permissive parsers now fail or canonicalize differently.
3. PROVEN claims lacking trust context now fail Level-2 strict checks.
4. Governance-only GO decisions now fail without justified evidentiary chain.
5. Inference-only promoted PROVEN claims may be downgraded or fail.

### 22.5 Degradation pathways

If full v0.5 fields unavailable:

1. Emit valid v0.5 packet with reduced conformance target (`L1`).
2. Mark unresolved controls as warnings where level allows.
3. Provide migration notes in validation run for required uplift to `L2` or `L3`.

### 22.6 Loss-less transformation procedure

1. Parse v0.4 packet with strict parser.
2. Normalize/canonicalize all objects with RFC 8785 serializer.
3. Insert version envelope fields.
4. Compute/insert `path_case_policy` and recompute Merkle using v1.
5. Backfill freshness fields:
- If unknown, set `is_time_sensitive=false` only when defensible.
- Else set conservative time sensitivity and require revalidation.
6. Backfill trust context from source metadata; if unavailable, mark for downgraded conformance.
7. Recompute manifest/state hashes under v0.5 rules.
8. Emit migration validation run.

### 22.7 Migration test vectors reference

See Appendix A.6 for normative migration cases.

## 23. Validator obligations (fail-closed list — substantially extended)

This section is normative.  
Rule IDs are stable and MUST be emitted in violations.  
Each fail-closed rule below has a corresponding Appendix A test vector.

### 23.1 Core integrity rules

`F001` Canonical parser duplicate-key rejection  
Condition: any object contains duplicate member names.  
Action: fail-closed.  
Vector: A.1-V1.

`F002` Non-finite number rejection  
Condition: NaN/Infinity/-Infinity observed or parser-admitted equivalent.  
Action: fail-closed.  
Vector: A.1-V2.

`F003` Canonical profile byte mismatch  
Condition: hash computed from non-JCS serialization or raw bytes differs from strict AST-JCS hash.  
Action: fail-closed.  
Vector: A.1-V3.

`F004` BOM/CRLF violation in canonical JSONL  
Condition: BOM present or CRLF line endings in canonical files.  
Action: fail-closed.  
Vector: A.1-V4.

`F005` Invalid UTF-8 / Unicode scalar violation  
Condition: invalid UTF-8 or invalid Unicode escape/surrogate handling.  
Action: fail-closed.  
Vector: A.1-V5.

`F006` Unknown profile channel  
Condition: profile not one of supported declared channels.  
Action: fail-closed.  
Vector: A.6-V4.

`F007` Manifest hash mismatch  
Condition: observed manifest hash != declared `manifest_hash`.  
Action: fail-closed.  
Vector: A.3-V5.

`F008` State hash mismatch  
Condition: observed state hash != declared `state_hash`.  
Action: fail-closed.  
Vector: A.3-V6.

`F009` Assets Merkle root mismatch  
Condition: recomputed root != declared `assets_merkle_root`.  
Action: fail-closed.  
Vector: A.2-V7.

`F010` Merkle path normalization collision  
Condition: two assets collapse to same normalized path after case/NFC policy.  
Action: fail-closed.  
Vector: A.2-V8.

### 23.2 Evidence and provenance rules

`F011` Empty basis on `PROVEN_RELIABLE`  
Condition: claim reliability PROVEN with empty basis.  
Action: fail-closed.  
Vector: A.5-V1.

`F012` Missing external anchor qualification for PROVEN  
Condition: PROVEN claim lacks at least one qualifying external anchor basis (unless allowed exemption).  
Action: fail-closed.  
Vector: A.5-V2.

`F013` Same-source basis collapse for claimed convergence  
Condition: independent convergence claimed but all bases share same-source fingerprint.  
Action: fail-closed or downgrade per policy.  
Vector: A.5-V3.

`F014` Missing reasoning on UNKNOWN/CONFLICTED  
Condition: UNKNOWN or CONFLICTED claim without required reasoning fields.  
Action: fail-closed.  
Vector: A.5-V4.

`F015` Missing trust context for URL/git anchor on PROVEN path  
Condition: required trust context fields absent.  
Action: fail-closed (L2+).  
Vector: A.5-V5.

`F016` Git reachability evidence missing/untrusted  
Condition: immutable SHA not proven reachable from trusted ref policy when required.  
Action: fail-closed (L2+).  
Vector: A.5-V6.

`F017` URL trust context insufficient for strict profile  
Condition: required URL fields absent or invalid under strict profile policy.  
Action: fail-closed.  
Vector: A.5-V7.

### 23.3 Freshness, replay, and TOCTOU rules

`F018` Packet epoch regression replay  
Condition: packet epoch lower than known superseding lineage state in strict GO evaluation.  
Action: fail-closed for GO; warning for EXPLORE/EXPERIMENT.  
Vector: A.3-V1.

`F019` Supersession chain invalid/acyclicity violation  
Condition: `supersedes_packet_id` chain cycle or broken reference.  
Action: fail-closed.  
Vector: A.3-V2.

`F020` Time-sensitive claim missing temporal scope/revalidation state  
Condition: claim marked or inferred time-sensitive without required fields.  
Action: fail-closed.  
Vector: A.3-V3.

`F021` Stale at decision time with required revalidation  
Condition: `decision_time_revalidation_required=true` and now > `revalidate_after` without passing revalidation event.  
Action: fail-closed for GO.  
Vector: A.3-V4.

`F022` Validity window violation  
Condition: decision time outside `[valid_from, valid_until]` when bounds provided.  
Action: fail-closed for GO.  
Vector: A.3-V7.

### 23.4 GO coupling and governance laundering rules

`F023` Policy-only GO without empirical dependency  
Condition: GO claim lineage contains only GOVERNANCE_RULE evidentiary basis for non-trivial mutation.  
Action: fail-closed (strict).  
Vector: A.5-V8.

`F024` Missing `go_justification_claim_ids` on GO+GOVERNANCE_RULE  
Condition: reliability GOVERNANCE_RULE + axis_b GO and field absent/empty.  
Action: fail-closed.  
Vector: A.5-V9.

`F025` GO justification ids unresolved or non-evidentiary  
Condition: referenced justification claims missing or all GOVERNANCE_RULE.  
Action: fail-closed.  
Vector: A.5-V10.

`F026` Governance override used without R4 review tier  
Condition: override path requested but R4 review absent.  
Action: fail-closed.  
Vector: A.5-V11.

### 23.5 Inference escalation and promotion rules

`F027` Reliability upgrade above lineage minimum without valid override  
Condition: terminal reliability exceeds allowed tier absent qualifying direct evidence/review override.  
Action: fail-closed.  
Vector: A.4-V1.

`F028` Inference hop decay not applied  
Condition: decay-applicable hops beyond threshold but terminal tier unchanged.  
Action: fail-closed.  
Vector: A.4-V2.

`F029` PROVEN claim supported by inference-only chain without anchored direct basis  
Condition: lineage to PROVEN includes inference-only chain and no qualifying direct anchored basis.  
Action: fail-closed.  
Vector: A.4-V3.

`F030` Inference lineage unchecked flag false on GO claim  
Condition: GO claim has `inference_lineage_checked=false` under L2+.  
Action: fail-closed.  
Vector: A.4-V4.

### 23.6 Versioning and extension rules

`F031` Missing record version envelope fields  
Condition: record lacks `aep_version`, `producer_version`, or `consumer_min_version`.  
Action: fail-closed.  
Vector: A.6-V1.

`F032` Consumer version below required minimum  
Condition: validator/consumer version < record `consumer_min_version`.  
Action: fail-closed.  
Vector: A.6-V2.

`F033` Unstable decision-affecting extension in stable channel  
Condition: extension affects decision semantics and stability is not `stable` in `aep:0.5/stable`.  
Action: fail-closed.  
Vector: A.6-V3.

`F034` Extension compatibility bounds violated  
Condition: consumer outside extension min/max tested compatibility window under strict policy.  
Action: fail-closed.  
Vector: A.6-V5.

### 23.7 Review Sybil-hardening rules

`F035` Missing reviewer fingerprint/capability manifest  
Condition: review record missing required interim identity hardening fields.  
Action: fail-closed for GO consensus use.  
Vector: A.5-V12.

`F036` Unverified reviewer weight exceeds cap  
Condition: unverified identity with weight > policy cap (default 0.5).  
Action: fail-closed in strict GO profiles.  
Vector: A.5-V13.

`F037` GO consensus satisfied solely by unverified reviewers  
Condition: threshold met without verified-weight contribution under strict profile.  
Action: fail-closed.  
Vector: A.5-V14.

### 23.8 Optional coverage/reproducibility rules

`F038` Undeclared decision-critical side input used (Level-3 strict repro)  
Condition: GO decision references input not listed in `execution_inputs_manifest` where profile requires it.  
Action: fail-closed in L3, warning in L2.  
Vector: A.6-V6.

### 23.9 Rule-processing obligations

- Validators MUST process all applicable rules and emit full violation list, not stop at first error (unless explicitly configured for short-circuit diagnostics).
- Severity mapping is normative for fail/warn behavior by level/profile.
- Rule IDs MUST remain stable within v0.5 major line.

## 24. Non-guarantees (clearly enumerated)

AEP v0.5 does not guarantee:

1. Truth of underlying domain claims beyond recorded evidence/review structure.
2. Security of all external infrastructure (DNS/PKI, hosting, transport) without additional controls.
3. Identity non-repudiation equal to strong signatures (interim v0.5 review hardening is not final cryptographic identity).
4. Completeness of side-input capture unless `execution_inputs_manifest` is mandated and audited.
5. Immunity to malicious but internally consistent fabricated evidence if trust roots themselves are compromised.
6. Deterministic behavior for non-canonical, non-hash-affecting auxiliary tooling outputs.
7. Automatic conflict resolution quality; protocol preserves structure, not substantive correctness.
8. Protection from policy misuse outside configured validator profiles.
9. Cross-org trust alignment without explicit shared root policy configuration.
10. Backward acceptance by v0.4-only consumers without migration adaptation.

## Appendix A: Test vectors

All vectors below are normative.  
Each vector has an ID and maps to fail-closed rules in §23.

### A.1 — JSON canonical profile test vectors (Attack 1)

#### A.1-V1 Duplicate key rejection (`F001`)

Input line:

```json
{"id":"c1","value":1,"value":2}
```

Expected:

- Parse failure under strict profile.
- Emit `F001`.

#### A.1-V2 Non-finite number rejection (`F002`)

Input line (parser-permissive dialect example, invalid strict JSON):

```json
{"id":"c2","value":NaN}
```

Expected:

- Reject tokenization/parsing.
- Emit `F002`.

#### A.1-V3 Re-serialize strict AST before hash (`F003`)

Input raw bytes line:

```json
{"b":1,"a":2}
```

Canonical RFC 8785 bytes expected:

```json
{"a":2,"b":1}
```

Expected:

- Hash computed over canonical bytes only.
- If raw-byte hash used, validator must detect mismatch path and emit `F003`.

#### A.1-V4 BOM/CRLF rejection (`F004`)

Input file bytes starts with UTF-8 BOM and `\r\n` endings.

Expected:

- Fail canonical file constraints.
- Emit `F004`.

#### A.1-V5 Invalid Unicode surrogate handling (`F005`)

Input line contains invalid lone surrogate escape:

```json
{"id":"c5","txt":"\uD800"}
```

Expected:

- Strict parse rejection or canonicalization rejection.
- Emit `F005`.

#### A.1-V6 Numeric canonicalization equivalence check

Input lines:

```json
{"n":0}
{"n":-0}
```

Expected:

- Canonical serializer outputs equivalent zero representation.
- If implementation diverges between lines in hash-affecting context, emit `F003`.

#### A.1-V7 Escape normalization equivalence

Input lines:

```json
{"s":"A\u005C"}
{"s":"A\\"}
```

Expected:

- Canonical semantic equivalence under RFC 8785 escaping rules.
- Divergent hash due to non-canonical escaping is `F003`.

### A.2 — AEP-MERKLE-v1 test vectors (0, 1, 2, 3, 4, 5 assets) (Attack 2)

Notation:

- `H(x)` = SHA-256 hex lowercase of bytes `x`.
- File hash is SHA-256 of raw file bytes.
- Paths are already relative and valid.

#### A.2-V1 Empty assets set

Assets: none.  
Expected root:

`H("AEP_EMPTY")`

Rule linkage: baseline integrity, supports `F009`.

#### A.2-V2 One asset

Assets:

1. `assets/a.txt` bytes = ASCII `"alpha"`

Compute:

1. `f1 = H("alpha")`
2. `leaf1 = H("AEP_LEAF\nassets/a.txt\n" + f1)`
3. root = `leaf1`

Rule linkage: `F009` if mismatch.

#### A.2-V3 Two assets

Assets:

1. `assets/a.txt` = `"alpha"`
2. `assets/b.txt` = `"beta"`

Compute:

1. `f1`, `f2`
2. `leaf1 = H("AEP_LEAF\nassets/a.txt\n" + f1)`
3. `leaf2 = H("AEP_LEAF\nassets/b.txt\n" + f2)`
4. root = `H("AEP_NODE\n" + leaf1 + leaf2)` (sorted by normalized path)

Rule linkage: `F009`.

#### A.2-V4 Three assets (odd duplication)

Assets:

1. `assets/a.txt` = `"alpha"`
2. `assets/b.txt` = `"beta"`
3. `assets/c.txt` = `"gamma"`

Leaves sorted: `L1`, `L2`, `L3`.

Level 1:

1. `N1 = H("AEP_NODE\n" + L1 + L2)`
2. `N2 = H("AEP_NODE\n" + L3 + L3)`  (duplicate-last)

Root:

1. `R = H("AEP_NODE\n" + N1 + N2)`

Rule linkage: `F009`.

#### A.2-V5 Four assets

Assets:

1. `assets/a.txt` = `"alpha"`
2. `assets/b.txt` = `"beta"`
3. `assets/c.txt` = `"gamma"`
4. `assets/d.txt` = `"delta"`

Tree:

1. `N1 = H("AEP_NODE\n" + L1 + L2)`
2. `N2 = H("AEP_NODE\n" + L3 + L4)`
3. `R = H("AEP_NODE\n" + N1 + N2)`

Rule linkage: `F009`.

#### A.2-V6 Five assets

Assets:

1. `assets/a.txt` = `"alpha"`
2. `assets/b.txt` = `"beta"`
3. `assets/c.txt` = `"gamma"`
4. `assets/d.txt` = `"delta"`
5. `assets/e.txt` = `"epsilon"`

Level 1:

1. `N1 = H("AEP_NODE\n" + L1 + L2)`
2. `N2 = H("AEP_NODE\n" + L3 + L4)`
3. `N3 = H("AEP_NODE\n" + L5 + L5)` (dup)

Level 2:

1. `M1 = H("AEP_NODE\n" + N1 + N2)`
2. `M2 = H("AEP_NODE\n" + N3 + N3)` (dup)

Root:

1. `R = H("AEP_NODE\n" + M1 + M2)`

Rule linkage: `F009`.

#### A.2-V7 Declared root mismatch (`F009`)

Packet declares root `R_declared`, recomputed root `R_actual != R_declared`.  
Expected fail with `F009`.

#### A.2-V8 Path normalization collision (`F010`)

With `path_case_policy=lowercase`, assets include:

1. `assets/Readme.txt`
2. `assets/readme.txt`

Both normalize to same path.  
Expected fail `F010`.

### A.3 — Event chain test vectors (Attack 3 + valid replay rejection)

#### A.3-V1 Packet epoch regression replay (`F018`)

Known latest lineage: `packet_epoch=7`.  
Candidate packet: same lineage id, `packet_epoch=5`, valid hashes.  
Decision context: `GO`.

Expected:

- Strict fail `F018` for GO.
- Warning-only in `EXPLORE` context allowed by policy.

#### A.3-V2 Supersession cycle (`F019`)

Chain:

- P10 supersedes P09
- P09 supersedes P10

Expected fail `F019`.

#### A.3-V3 Missing temporal scope on time-sensitive claim (`F020`)

Claim has `freshness_class=volatile`, `axis_b=GO`, no `revalidate_after` and no valid window.  
Expected fail `F020`.

#### A.3-V4 Stale at decision time (`F021`)

Claim:

- `decision_time_revalidation_required=true`
- `revalidate_after=2026-05-14T10:00:00Z`

Decision at `2026-05-14T12:00:00Z` with no passing revalidation event.  
Expected fail `F021`.

#### A.3-V5 Manifest hash mismatch (`F007`)

Declared manifest hash not equal recomputed JCS-hashed manifest object.  
Expected fail `F007`.

#### A.3-V6 State hash mismatch (`F008`)

Declared state hash not equal recomputed envelope hash.  
Expected fail `F008`.

#### A.3-V7 Validity window expired (`F022`)

Claim:

- `valid_until=2026-05-01T00:00:00Z`
- Decision at `2026-05-14T00:00:00Z`
- `axis_b=GO`

Expected fail `F022`.

#### A.3-V8 Revalidation event pass path

Same as V4 plus a `revalidation_event` at `2026-05-14T11:55:00Z` with `revalidation_result=pass` and new `next_revalidate_after` in future.  
Expected pass for freshness checks.

### A.4 — Inference DAG decay test vectors (Attack 6)

#### A.4-V1 No-upgrade violation (`F027`)

Lineage reliability minima: `PLAUSIBLE`.  
Terminal claim marked `PROVEN_RELIABLE`, no override evidence.  
Expected fail `F027`.

#### A.4-V2 Missing hop decay (`F028`)

Inference-only chain of 5 hops using `architectural_inference`.  
Expected maximum tier should decay by 3 tiers beyond hop 2.  
If terminal not decayed, fail `F028`.

#### A.4-V3 PROVEN from inference-only chain without anchor (`F029`)

Terminal PROVEN claim supported only via inference-only edges from weak origin, no direct anchored basis.  
Expected fail `F029`.

#### A.4-V4 Lineage unchecked flag false (`F030`)

GO claim sets `inference_lineage_checked=false`.  
Expected fail `F030` at L2+.

#### A.4-V5 Valid mixed support path

Terminal claim has inference chain plus independent direct anchored basis with sufficient reliability.  
Expected pass if promotion rule satisfied.

### A.5 — GO disposition coupling test vectors (Attack 5)

#### A.5-V1 PROVEN empty basis (`F011`)

PROVEN claim with `basis=[]`.  
Expected fail `F011`.

#### A.5-V2 PROVEN missing external anchor (`F012`)

PROVEN claim basis references only unanchored internal claim.  
Expected fail `F012`.

#### A.5-V3 Same-source collapse (`F013`)

Three basis entries all share same `same_source_fingerprint`, claim asserts independent convergence.  
Expected fail/downgrade `F013`.

#### A.5-V4 UNKNOWN without reasoning (`F014`)

UNKNOWN claim missing `epistemic_state.reasoning`.  
Expected fail `F014`.

#### A.5-V5 Missing trust context URL/git (`F015`)

PROVEN claim references URL source missing `fetch_agent_id`.  
Expected fail `F015`.

#### A.5-V6 Git reachability evidence absent (`F016`)

Git anchor has immutable SHA but no trusted ref reachability proof.  
Expected fail `F016`.

#### A.5-V7 URL strict context invalid (`F017`)

URL anchor in strict profile missing host/scheme/location hash validity.  
Expected fail `F017`.

#### A.5-V8 Policy-only GO (`F023`)

Non-trivial mutation claim:
- `axis_b=GO`
- all dependencies are `GOVERNANCE_RULE`
Expected fail `F023`.

#### A.5-V9 Missing go justification ids (`F024`)

Claim:
- `axis_b=GO`
- `axis_a_reliability=GOVERNANCE_RULE`
- no `go_justification_claim_ids`
Expected fail `F024`.

#### A.5-V10 GO justification unresolved/non-evidentiary (`F025`)

`go_justification_claim_ids=["c404"]` not found, or found claim is also GOVERNANCE_RULE only.  
Expected fail `F025`.

#### A.5-V11 Governance override without R4 (`F026`)

Override flag true, strongest review is R3.  
Expected fail `F026`.

#### A.5-V12 Missing reviewer hardening fields (`F035`)

Review receipt lacks capability manifest or fingerprint.  
Expected fail `F035` when used for GO consensus.

#### A.5-V13 Unverified weight cap violation (`F036`)

Unverified reviewer assigned weight 0.8 in strict profile.  
Expected fail `F036`.

#### A.5-V14 Unverified-only consensus (`F037`)

GO threshold met entirely with unverified reviewers (weights within cap).  
Expected fail `F037`.

### A.6 — Cross-version migration test vectors (Attack 7)

#### A.6-V1 Missing version envelope (`F031`)

Record missing `consumer_min_version`.  
Expected fail `F031`.

#### A.6-V2 Consumer too old (`F032`)

Record `consumer_min_version=0.5.4`, validator is `0.5.1`.  
Expected fail `F032`.

#### A.6-V3 Unstable decision extension in stable channel (`F033`)

Profile `aep:0.5/stable`, extension:
- `semantic_stability=experimental`
- `affects_decision_semantics=true`
Expected fail `F033`.

#### A.6-V4 Unknown profile (`F006`)

Profile `aep:0.5/preview` (unsupported).  
Expected fail `F006`.

#### A.6-V5 Extension compatibility bounds violation (`F034`)

Extension declares:
- `min_consumer_version=0.5.3`
- `max_tested_version=0.5.4`
Validator at `0.5.8` with strict compatibility policy.  
Expected fail `F034`.

#### A.6-V6 Undeclared side input usage (`F038`)

L3 conformance, GO decision references model file not in `execution_inputs_manifest`.  
Expected fail `F038`.

#### A.6-V7 v0.4 to v0.5 downgrade path

Migrated packet syntactically valid but lacks trust context for some PROVEN anchors.  
Expected:

- L1 pass possible.
- L2 fail with corresponding trust-context rule IDs.

#### A.6-V8 Stable vs experimental channel behavior

Same packet with unstable non-decision extension:

- In stable channel: may pass if extension non-decision and policy allows.
- In experimental channel: pass with warning if declared compatibility valid.

## Appendix B: Compatibility matrix (Attack 7, cycle-2 #2)

### B.1 — channel × feature × stability table

| Feature | Stable Channel (`aep:0.5/stable`) | Experimental Channel (`aep:0.5/experimental`) | Stability Class |
|---|---|---|---|
| Strict JSON canonical profile v1 | REQUIRED | REQUIRED | stable |
| AEP-MERKLE-v1 | REQUIRED | REQUIRED | stable |
| GO governance coupling checks | REQUIRED | REQUIRED | stable |
| Trust context for PROVEN URL/git anchors | REQUIRED | REQUIRED | stable |
| Weighted review Sybil-hardening | REQUIRED for GO | REQUIRED for GO | stable (interim) |
| Unstable decision-affecting extension | FORBIDDEN | ALLOWED with explicit opt-in | experimental |
| execution_inputs_manifest enforcement | OPTIONAL (warn) | OPTIONAL/REQUIRED by policy | experimental |
| Conformance run external anchor id | MAY | MAY | stable |

### B.2 — producer × consumer version compatibility

| Producer `aep_version` | Consumer capability | Outcome |
|---|---|---|
| `0.5` | Supports `0.5`, consumer >= all `consumer_min_version` | Accept |
| `0.5` | Supports `0.5`, consumer below min for any record | Reject (`F032`) |
| `0.5` | Does not support declared profile channel | Reject (`F006`) |
| `0.4` packet migrated to `0.5` | Consumer supports `0.5` | Accept per conformance level |
| `0.5` with unsupported major extensions | Consumer cannot satisfy extension constraints | Reject (`F034`) |
| `0.5` stable + experimental decision extension | Stable-only consumer | Reject (`F033`) |

Compatibility policy notes:

- Hash-affecting semantics changes require major version.
- Additive non-hash-affecting fields may be minor if they do not alter pass/fail outcomes in existing profiles.
- Consumers SHOULD log compatibility rationale with rule IDs.

## Appendix C: Conformance levels

### C.1 — Level-1 conformance (axioms 1-8 + v0.4 fail-closed list)

Level-1 includes baseline v0.4-aligned controls:

1. Canonical file presence.
2. Chain integrity.
3. State/manifest/assets hash checks.
4. PROVEN basis non-empty and basic anchor rule.
5. Same-source collapse check.
6. UNKNOWN reasoning requirement.
7. Profile recognition.

Level-1 may treat some v0.5 additions as warnings where explicitly permitted by profile.

### C.2 — Level-2 conformance (axioms 1-10 + Round-2 mitigations active)

Level-2 is recommended production strictness:

1. Full strict JSON canonical profile enforcement.
2. Full `AEP-MERKLE-v1` enforcement.
3. Freshness/revalidation fail-closed on GO.
4. Trust context requirements for PROVEN URL/git anchors.
5. GO governance coupling fail-closed.
6. Inference decay/no-upgrade controls fail-closed.
7. Version/extension stability fail-closed.
8. Weighted review Sybil-hardening fail-closed for GO decisions.

### C.3 — Level-3 conformance (Level-2 + experimental features + execution_inputs_manifest)

Level-3 adds reproducibility hardening and experimental controls:

1. Mandatory `execution_inputs_manifest` for declared strict reproducibility contexts.
2. Fail-closed undeclared side-input usage.
3. Extended experimental feature checks under opt-in policy.
4. Additional determinism and evidence replay harness checks.

### C.4 — Conformance declaration format

Validators SHOULD emit declaration object:

```json
{
  "conformance_level": "L2",
  "profile": "aep:0.5/stable",
  "rule_set_version": "0.5.0",
  "canonical_profile": "aep-json-canonical-profile:v1",
  "merkle_profile": "AEP-MERKLE-v1"
}
```

### C.5 — Minimum claims by channel

- Production deployments SHOULD require at least Level-2 on `aep:0.5/stable`.
- Experimental research may use Level-2 or Level-3 on `aep:0.5/experimental`.
- Level-1 is transitional/migration-only and SHOULD NOT authorize high-impact GO mutations without external governance.

### C.6 — Auditor interoperability guidance

Auditors validating across implementations SHOULD:

1. Recompute all canonical hashes from strict AST.
2. Compare Merkle roots using identical normalization/case policy.
3. Replay event chain from genesis to ensure deterministic state.
4. Re-evaluate GO gating with current time and required revalidation events.
5. Emit comparable violation IDs for cross-tool agreement.

### C.7 — Policy binding recommendation

Organizations SHOULD publish an AEP policy bundle containing:

1. Allowed channels.
2. Required conformance level per action class.
3. Trust root policy for git/url anchors.
4. Review consensus thresholds and weight caps.
5. Freshness windows by claim type.
6. Extension allowlist and compatibility stance.

### C.8 — Determinism checklist

Implementation determinism checklist:

1. Strict parser with duplicate-key rejection.
2. RFC 8785 serializer byte-verified.
3. Stable lexicographic path sort.
4. Case policy applied exactly once after NFC normalization.
5. Event chain hash computed from canonical event objects.
6. Rule processing order deterministic and complete.
7. Timestamp comparison timezone-safe (UTC normalization recommended).

### C.9 — Claim discipline matrix

| Claim Type | Minimum Fields | Freshness Required | Anchor Diversity Required | GO Allowed Conditions |
|---|---|---|---|---|
| `PROVEN_RELIABLE` | basis + anchor + trust context | if time-sensitive | yes | only with valid lineage and freshness |
| `STRONGLY_PLAUSIBLE` | basis + epistemic state | recommended | preferred | with policy review |
| `PLAUSIBLE` | basis or rationale | optional | optional | usually EXPERIMENT/EXPLORE |
| `ASSUMPTION` | rationale required | optional | no | not direct GO for high-impact mutation |
| `CONFLICTED` | conflict reasoning required | context-dependent | no | typically HALT/EXPLORE |
| `UNKNOWN` | unknown reasoning required | context-dependent | no | not GO without supporting chain |
| `GOVERNANCE_RULE` | policy source + scope | if time-bound policy | n/a | GO only with coupling constraints |

### C.10 — Final conformance statement

AEP v0.5 conformance means deterministic validator behavior under this specification and declared profile/level.  
Conformance does not imply domain truth, but it guarantees exact-science integrity semantics for evidence packaging, governance gates, and replayable validation decisions.

