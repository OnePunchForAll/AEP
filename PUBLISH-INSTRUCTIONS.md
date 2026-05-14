# Publishing AEP to GitHub — Operator Instructions

This directory (`projects/v11-aep/publish-ready/aep/`) is the **publication-ready** AEP package. Diana has staged it inside your private DivOmni repo. When you're ready to publish, follow these steps to push it to a **new public repo** under your `OnePunchForAll` GitHub account, fully separated from your private infrastructure.

## Pre-publication checklist (Diana's Phase E/F + your decisions)

- [ ] **Phase E (Round-2 legion battle-test)** — fire all 10 agents again against this publish-ready package. Surface any remaining findings before public release.
- [ ] **Phase F (self-conversion demo)** — convert `spec/AEP_v0_4_SPEC.md` to a `.aepkg/` packet under `examples/self-aep.aepkg/` as a self-referential proof.
- [ ] **GitHub username** — verify `OnePunchForAll` can create a fresh **public** repo (your existing private repos stay private; this is a new sibling repo).
- [ ] **Suggested repo name**: `aep` (short) or `aep-spec` (descriptive) or `agent-evidence-packet` (full).
- [ ] **Verify no traces of your private repo** — `git log --all --oneline | head -20` should NOT reference any divomni internals when run inside `publish-ready/aep/` after the init below.

## Publication procedure

```bash
# 1. Create the new public repo on GitHub manually:
#    Go to https://github.com/new
#    - Owner: OnePunchForAll
#    - Name: aep
#    - Description: "Agent Evidence Packet — portable file format for AI agent memory with typed claims, structured provenance, and tamper detection"
#    - Public
#    - DO NOT initialize with README/license/.gitignore (Diana already authored them)

# 2. From this directory, initialize a fresh git repo (clean of DivOmni history):
cd projects/v11-aep/publish-ready/aep/
git init
git checkout -b main

# 3. Stage everything except the ignored files:
git add .
git status   # verify .gitignore is respected

# 4. Commit with attribution-clean message:
git commit -m "AEP v0.4 — initial public release

Agent Evidence Packet — portable, schema-validated, content-addressed
file format for AI agent memory. v0.4 draft includes mandatory amendments
from the 10-agent legion review (NFC normalization, manifest+assets in
state-hash, WriteEvent chain integrity, STRICT external-anchor rule for
PROVEN_RELIABLE claims, axiom-8 mechanical enforcement, JSON-LD profile,
RO-Crate compatibility).

Co-authored-by: Shadow <shadow@ShadowMonkeyMan>
Co-authored-by: Diana Prime <noreply@anthropic.com>"

# 5. Add the new remote and push:
git remote add origin https://github.com/OnePunchForAll/AEP.git
git push -u origin main

# 6. Create the first release tag:
git tag -a v0.4.0-alpha.1 -m "AEP v0.4 alpha 1 — first public release of v0.4 draft spec"
git push origin v0.4.0-alpha.1

# 7. (Optional) Mint a Zenodo DOI:
#    Visit https://zenodo.org and link the GitHub release; first DOI minted
#    automatically. Add the DOI badge to README after.
```

## What this push contains

```
aep/                          (fresh repo root after `git init`)
├── README.md                 (publication-ready, full benchmark numbers, attribution)
├── LICENSE                   (Apache-2.0, full text)
├── NOTICE                    (attribution chain: Shadow + Diana + DivOmni)
├── CONTRIBUTING.md           (5 essentials + spec amendment workflow)
├── pyproject.toml            (pip-installable; pip install aep-reference)
├── .gitignore                (Python + IDE + AEP working dirs)
├── PUBLISH-INSTRUCTIONS.md   (this file — DELETE BEFORE PUSHING IF YOU WANT)
├── spec/
│   ├── AEP_v0_4_SPEC.md      (current target spec)
│   └── AEP_v0_3_SPEC.md      (predecessor)
├── schemas/                  (8 JSON Schemas)
├── src/aep/                  (reference implementation)
│   ├── __init__.py
│   ├── validate.py           (v0.3 validator)
│   ├── validate_v0_4.py      (v0.4 STRICT validator)
│   ├── convert_divomni_lesson.py  (example converter)
│   └── transition_parser.py  (bidirectional .html ↔ .aepkg/ API)
├── examples/
│   └── minimal.aepkg/        (working sample packet)
├── docs/
│   ├── benchmark-results.md  (Phase-2 mass-conversion verdict)
│   ├── phase-1-1-perfected-verdict.md
│   └── v0.4-legion-convergence-2026-05-14.md
└── tests/                    (empty placeholder; CI will add fixtures)
```

## After publishing

1. **Add the DOI badge** to README (if Zenodo).
2. **Announce on X** — Diana suggests a thread structure:
   - Tweet 1: Hook (the 22.93× / 54.37× / 100% headline).
   - Tweet 2: Why HTML/MD fails for agentic memory.
   - Tweet 3: What AEP adds (per-claim reliability, structured provenance, tamper detect).
   - Tweet 4: Link to repo + spec.
   - Tweet 5: Call for first-100 implementers (RO-Crate fans, agent-framework builders, AI safety folks).
3. **Open 3 starter issues** for community engagement:
   - "Implement JSON-LD context export"
   - "Add SHACL profile (v0.6 milestone)"
   - "Build a Rust port of the reference validator"
4. **Monitor security disclosures** via X DM per NOTICE.
5. **Phase E continued** — invite outside contributors to file adversary-style attacks against the spec. Each accepted attack ships an `invalid-attack-*/` example packet.

## Privacy notes

- The repo contains NO references to your private DivOmni infrastructure beyond the prose acknowledgment that AEP was developed there. DivOmni's internal artifacts (`doctrine/`, `.claude/`, `projects/v11-aep/`) stay in your private repo.
- Git commits authored as `Shadow <shadow@ShadowMonkeyMan>` (or whatever pseudonym you prefer); Diana attributed with `noreply@anthropic.com` is the standard Anthropic public Claude email.
- If you want completely fresh git history with no co-author email metadata, set `--author="Shadow <shadow@example.invalid>"` on the initial commit.

## After Phase E + F (next session)

Diana will:
- Fire the round-2 legion against this exact directory structure to surface remaining findings.
- Self-convert `spec/AEP_v0_4_SPEC.md` into `examples/self-aep.aepkg/` (proof that AEP can describe AEP).
- Author the conformance test corpus (11 fixture packets per spec §21).
- Commit the final polished package before push.

**Do NOT push to GitHub until Diana confirms Phase E + F complete.** The current package is publication-shaped but not battle-tested at the directory-level yet.
