# AEP v0.5 Conformance Test Vectors

**Status**: PERFECTED — every Round-2 attack closure has a corresponding test vector here.

Every conforming AEP v0.5 validator MUST pass this entire corpus to claim Level-2 conformance.

## Structure

```
test_vectors/v0_5/
├── README.md                        (this file)
├── A.1-json-canonical/              (Attack 1 — Canonicalization Differential)
│   ├── reject-duplicate-keys.json
│   ├── reject-nan-infinity.json
│   ├── reject-leading-plus-number.json
│   ├── reject-leading-zero-number.json
│   ├── reject-trailing-zero-decimal.json
│   ├── reject-uppercase-exponent.json
│   ├── accept-canonical-numbers.json
│   └── expected_outcomes.json       (file → expected error code)
├── A.2-aep-merkle-v1/               (Attack 2 — Assets Merkle Ambiguity)
│   ├── empty-tree.aepkg/            (assets/ empty → MERKLE_EMPTY)
│   ├── single-leaf.aepkg/           (1 file → leaf hash)
│   ├── two-leaves.aepkg/            (2 files → internal)
│   ├── three-leaves.aepkg/          (odd → duplicate-last-leaf)
│   ├── nfc-collision.aepkg/         (NFC vs NFD path → must agree post-norm)
│   ├── case-sensitive.aepkg/        (path_case_policy="preserve")
│   ├── case-folded.aepkg/           (path_case_policy="lowercase")
│   └── expected_roots.json          (packet → expected assets_merkle_root)
├── A.3-event-chain-replay/          (Attack 3 — Cross-Packet Replay)
│   ├── valid-genesis.aepkg/         (first event pre_state_hash == empty)
│   ├── broken-chain.aepkg/          (event N+1 pre != event N post)
│   ├── stale-go-claim.aepkg/        (now > revalidate_after + GO)
│   ├── valid-supersedes.aepkg/      (epoch monotonic)
│   └── expected_outcomes.json
├── A.4-inference-decay/             (Attack 6 — Inference Label Escalation)
│   ├── two-hop-proven.aepkg/        (PROVEN with 2 architectural_inference hops, no anchor — REJECT)
│   ├── single-hop-with-anchor.aepkg/(PROVEN with 1 anchor + 1 inference — ACCEPT)
│   ├── pure-inference-chain.aepkg/  (4-hop analogical, no anchor — REJECT)
│   └── expected_outcomes.json
├── A.5-go-governance-coupling/      (Attack 5 — GO-Path Laundering)
│   ├── go-without-evidence.aepkg/   (axis_b=GO + GOVERNANCE_RULE + empty go_justification — REJECT)
│   ├── go-with-evidence.aepkg/      (GO + GOVERNANCE_RULE + ≥1 non-GR justification claim — ACCEPT)
│   ├── governance-override.aepkg/   (governance_override=true + R4 + ≥2 R4 reviews — ACCEPT)
│   ├── governance-override-no-r4.aepkg/(governance_override without R4 — REJECT)
│   └── expected_outcomes.json
├── A.6-version-polyglot/            (Attack 7 — Schema-Version Polyglot)
│   ├── v0_4-rejected-by-v0_5-strict.aepkg/(aep_version="0.4" under strict v0.5 — REJECT)
│   ├── v0_5-stable-accepted.aepkg/  (aep_version="0.5", profile=stable — ACCEPT)
│   ├── unstable-extension-in-strict.aepkg/(experimental ext affecting reliability — REJECT)
│   └── expected_outcomes.json
├── A.7-sybil-interim/               (Attack 8 — Review Signal Gaming)
│   ├── unverified-only-consensus.aepkg/(GO threshold met only by unverified — REJECT strict)
│   ├── mixed-verified-consensus.aepkg/(2 verified + 3 unverified, weighted sum ≥ threshold — ACCEPT)
│   └── expected_outcomes.json
├── A.8-toctou/                      (Attack 9 — TOCTOU on Anchors)
│   ├── stale-go-revalidation-required.aepkg/(decision_time_revalidation_required=True + stale — REJECT)
│   ├── stale-go-with-revalidation-event.aepkg/(stale but revalidated within window — ACCEPT)
│   └── expected_outcomes.json
└── A.9-execution-inputs-manifest/   (Attack 10 — State-Hash Coverage Evasion, optional)
    ├── undeclared-side-input.aepkg/ (GO claim references file outside canonical scope — WARN)
    └── expected_outcomes.json
```

## Running the test vectors

```bash
# Against the v0.5 reference validator:
cd projects/v11-aep/publish-ready/aep/
python -m pytest tests/v0_5/test_conformance.py

# Or against any validator implementation:
for packet in test_vectors/v0_5/**/*.aepkg/; do
  expected=$(jq -r --arg p "$packet" '.[$p]' test_vectors/v0_5/expected_outcomes.json)
  actual=$(python -m aep.validate_v0_5 "$packet" --profile aep:0.5/stable --strict 2>&1; echo "exit=$?")
  diff <(echo "$expected") <(echo "$actual") || echo "MISMATCH: $packet"
done
```

## Conformance levels (per v0.5 spec §C)

- **Level-1**: passes A.3 (event chain) only — backward-compat with v0.4 axiom 5 / 8.
- **Level-2**: passes A.1 through A.6 + A.7 + A.8 — full v0.5 mechanical enforcement.
- **Level-3**: Level-2 + passes A.9 — experimental execution_inputs_manifest enforcement.

## Hash-stable expected outputs

Every `expected_outcomes.json` is committed with PINNED sha256 values where outputs are deterministic (state_hash, assets_merkle_root). Validator implementations that compute different hashes from the same input have a CRITICAL bug per Attack 1 / Attack 2.

## License

Apache-2.0 (same as the rest of the AEP reference impl).

## Cite

- [AEP v0.5 SPEC](../../spec/AEP_v0_5_SPEC.md)
- [Round-2 attack bundle](../../../../round-2/round-2-bundle-2026-05-14.html)
- [validate_v0_5.py](../../src/aep/validate_v0_5.py)
