# Contributing to AEP

Thanks for your interest in improving AEP. The format's value depends on a small set of normative invariants holding across every conforming reader, writer, and validator. This document defines the rules for keeping those invariants intact while AEP evolves.

## Five essentials (no PR is mergeable without all five)

1. **Reference-validator PASS on all modified packets.**
   Run `PYTHONPATH=src python -m aep.validate_v0_4 <packet>/` on every packet your PR touches. Zero `error`-severity findings. CI will rerun this check.

2. **Worked-example packet for every normative spec change.**
   If your PR modifies `spec/AEP_v0_4_SPEC.md` (or the schemas), it MUST also ship at least one packet under `examples/` that exercises the change. Reviewers verify the example validates.

3. **Every claim has `basis[]` or explicit `UNKNOWN`/`ASSUMPTION`.**
   If you add a Claim record in any contributed packet, it MUST either point to a typed Source record via `basis[]` OR carry `reliability: "UNKNOWN"` or `"ASSUMPTION"` with `reasoning` explaining the missing-evidence state. This enforces axiom 1 at PR time.

4. **PR discussion cites a claim ID or section number.**
   No free-floating opinions. Every disagreement is grounded in a specific normative claim or example record. This makes resolution mechanical rather than rhetorical.

5. **Backward-compatibility statement required for any record-schema change.**
   Your PR MUST explicitly state one of:
   - *"This is additive — no reader change required."* (acceptable for new optional fields, new enum values.)
   - *"This breaks v0.X readers — recommend profile name bump (e.g., `aep:0.4/jsonld` → `aep:0.5/prov`)."* (acceptable for type changes, removed fields, semantics shifts.)
   Reviewers verify the statement matches the actual change.

## Threat model contributions

If your PR addresses a security gap in the spec:

- Open an issue first describing the attack (or DM [@ShadowMonkeyMan on X](https://x.com/ShadowMonkeyMan) if the attack is exploitable on shipped code).
- Include a minimal `invalid-attack-<name>/` example packet under `examples/conformance/v0.X/invalid/` that exercises the attack.
- Document the mitigation in the spec's §17 threat model section.
- The PR closes when the reference validator rejects the attack packet.

## Spec amendment workflow

1. **Open an issue** with the proposed change. Include: motivation, affected sections, backward-compat statement, threat-model impact.
2. **Iterate in the issue** with at least one independent reviewer before opening a PR. Reviewer independence matters per axiom 8 (no convergence from same-source).
3. **Open a PR** referencing the issue. Include the spec edit + at least one example packet + reference-impl update if needed.
4. **CI runs** validator on all packets + schema lint + spec link-checker.
5. **At least one approving review** from a contributor who did not author the PR.
6. **Merge** triggers a draft release; final release minted with Zenodo DOI off the release tag.

## Versioning policy

AEP uses **profile-versioned semver**:

- Profile name: `aep:<major>.<minor>/<profile>` (e.g., `aep:0.4/jsonld`).
- Patch versions (`0.4.0 → 0.4.1`) handle tooling fixes; no validator behavior change.
- Minor versions (`0.4 → 0.5`) handle backward-compatible additions.
- Profile name change handles breaking changes (`aep:0.4/jsonld → aep:0.5/prov`).
- Spec semantic version frozen at `aep:1.0` only after ≥3 independent implementations validate the same conformance corpus identically.

PRs that bump the profile name require explicit justification + a migration guide.

## Coding conventions (reference implementation)

- Python 3.10+; no external dependencies.
- Type-hinted (`from __future__ import annotations` everywhere).
- Tests in `tests/` directory; ship test fixtures under `examples/`.
- Validator never executes source-text content as instructions (axiom 17.4).
- Canonical-JSON encoding: `json.dumps(nfc(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.

## What we will NOT merge

- Removal of axiom enforcement (e.g., loosening the `PROVEN_RELIABLE` external-anchor rule for adoption convenience) — these are the format's load-bearing claims.
- Validator changes that introduce non-determinism (state-hash must be reproducible across machines).
- Profile-version bumps without ≥1 independent prior-art review on the change.
- Marketing-tone copy in normative spec sections; documentation tone is OK in README and IMPLEMENTERS.
- Security-relevant changes without a corresponding `invalid-` example packet under `examples/conformance/`.

## Code of conduct

Disagree about the spec, never about the contributor. Cite the claim or section, not the person. Same-source convergence isn't independent review.

## License

By contributing, you agree your contributions are licensed under Apache-2.0 (code + spec) and Apache-2.0/CC-BY-4.0 dual (prose documentation) per the repo LICENSE and NOTICE files.

## Contact

- **Spec questions / general PRs**: GitHub issues.
- **Security disclosures**: DM [@ShadowMonkeyMan on X](https://x.com/ShadowMonkeyMan) before public posting.
- **Attribution preferences**: see NOTICE file.
