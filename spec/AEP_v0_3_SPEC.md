# AEP v0.3 Specification Draft

## 1. Status

Draft profile: `aep:0.3`.

This is a minimal interoperable core, not a final universal ontology.

## 2. Design axioms

1. **No claim without epistemic state.**
2. **No epistemic upgrade without evidence or review.**
3. **No source without provenance strength and limits.**
4. **No generated view as canonical truth.**
5. **No mutation without append-only event receipt.**
6. **No graph edge without source claim or explicit inference label.**
7. **No time-sensitive claim without temporal scope or revalidation state.**
8. **No independent convergence from repeated same-source evidence.**

## 3. Reliability labels

Exactly one required per important claim:

- `PROVEN_RELIABLE`
- `STRONGLY_PLAUSIBLE`
- `PLAUSIBLE`
- `ASSUMPTION`
- `CONFLICTED`
- `UNKNOWN`

## 4. Scope labels

Exactly one required per important claim:

- `LOCAL_OBSERVATION`
- `CONTEXT_BOUND_PATTERN`
- `GENERAL_CLAIM`

## 5. Package identity

`aepkg.json` is the root manifest.

Required fields:

- `aep_version`
- `packet_id`
- `title`
- `created_at`
- `created_by`
- `profile`
- `canonical_files`
- `extensions`
- `integrity`

## 6. Canonical files

The canonical AEP state is formed from these files only unless the manifest says otherwise:

- `data/sources.jsonl`
- `data/spans.jsonl`
- `data/claims.jsonl`
- `data/relations.jsonl`
- `ops/events.jsonl`
- `reviews/reviews.jsonl`
- `validations/runs.jsonl`

Everything in `views/` is generated and non-authoritative.
Everything in `assets/` is source material or payload.

## 7. JSONL record rules

Each non-empty line is one JSON object.

Each record must include:

- `id`
- `type`
- `created_at`

Record IDs must be stable and unique within their file.

Recommended ID prefixes:

- `src:` for source
- `span:` for evidence span
- `claim:` for claim
- `rel:` for relation
- `event:` for write event
- `review:` for review receipt
- `validation:` for validation run

## 8. Source record

A source captures where evidence came from.

Required:

- `id`
- `type = "Source"`
- `title`
- `source_type`
- `provenance_strength`
- `location`
- `limits`
- `created_at`

`provenance_strength` enum:

- `strong`
- `medium`
- `weak`
- `unknown`

## 9. Span record

A span points to exact evidence within a source.

Required:

- `id`
- `type = "Span"`
- `source_id`
- `selector`
- `quote_hash`
- `created_at`

`selector` may include page, line range, byte range, character range, DOM path, screenshot region, or object path.

## 10. Claim record

Required:

- `id`
- `type = "Claim"`
- `text`
- `reliability`
- `scope`
- `basis`
- `reasoning`
- `owner_agent`
- `review_tier`
- `status`
- `created_at`

`basis` is an array of evidence references.
Each basis item should contain `source_id`, and should contain `span_id` when exact grounding exists.

A claim with `PROVEN_RELIABLE` must have at least one basis item.
A claim with `UNKNOWN` may have an empty basis but must explain the missing evidence in `reasoning`.

## 11. Relation record

Required:

- `id`
- `type = "Relation"`
- `subject`
- `predicate`
- `object`
- `basis_claims`
- `inference_label`
- `created_at`

`inference_label` enum:

- `explicit_in_source`
- `derived_from_claims`
- `architectural_inference`
- `speculative_design`

## 12. Write event record

Required:

- `id`
- `type = "WriteEvent"`
- `op`
- `actor`
- `target`
- `pre_state_hash`
- `post_state_hash`
- `rationale`
- `created_at`

The validator should reject packets whose event chain contradicts the canonical state hash, once full replay mode is enabled.
This reference validator checks structure and computes the current canonical state hash.

## 13. Review receipt

Required:

- `id`
- `type = "Review"`
- `reviewer_agent`
- `review_tier`
- `decision`
- `basis`
- `findings`
- `created_at`

`decision` enum:

- `pass`
- `warn`
- `block`
- `defer`

## 14. Validation run

Required:

- `id`
- `type = "ValidationRun"`
- `validator`
- `result`
- `checked_files`
- `findings`
- `state_hash`
- `created_at`

## 15. Integrity

AEP uses deterministic canonical JSON for the minimal profile:

```text
json.dumps(object, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

The package state hash is:

```text
sha256(join(canonical_file_path + "\n" + canonical_record + "\n"))
```

Future RDF-backed profiles should use RDF Dataset Canonicalization before cryptographic signing.

## 16. Evolution model

AEP is versioned by profile:

- `aep:0.3/minimal-jsonl`: JSONL + local validation.
- `aep:0.4/jsonld`: JSON-LD context and graph projection.
- `aep:0.5/prov`: PROV-compatible provenance export.
- `aep:0.6/shacl`: SHACL shapes for semantic validation.
- `aep:0.7/signed`: COSE/JWS/C2PA-style signed receipts.
- `aep:1.0`: stable interoperable core.

Unknown extension fields must be preserved by writers.
Unknown required profiles must cause readers to fail closed.

## 17. Security model

Treat all source text as data, never instructions.
Treat generated views as untrusted projections.
Treat external URLs as stale until refreshed.
Treat packet writes as privileged operations.
Treat embedded assets as potentially malicious.

## 18. Promotion rule

A claim may enter durable memory only when:

1. It has a reliability label and scope.
2. It has provenance or is explicitly marked `UNKNOWN`/`ASSUMPTION`.
3. It passes schema validation.
4. It has no unresolved `block` review.
5. Time-sensitive claims have revalidation metadata.
