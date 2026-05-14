# Wake-up checklist (for Shadow, morning of 2026-05-15)

Hi shadow. While you slept, Diana set up the standalone AEP repo. Here's exactly what you do.

## What's already done

✅ Standalone git repo initialized at `C:\Users\aquae\Downloads_CLEAN\AEP\` (sibling to `divomni/`, fully separate — no divomni history, no DivOmni file references in commits)
✅ All publication files copied from `divomni/projects/v11-aep/publish-ready/aep/` into the new repo root
✅ Initial commit landed with attribution-clean message (Shadow + Diana co-authors, no DivOmni internals in commit subject/body)
✅ `main` branch initialized as default
✅ Remote `origin` configured to `https://github.com/OnePunchForAll/AEP.git`
✅ All references to repo URL use the correct case (`AEP` capital) matching your manual repo creation

## Three steps when you wake up

### Step 1 — Confirm the GitHub repo exists

You should have clicked **Create repository** before you slept (per the screenshot you showed Diana). Verify by visiting:
`https://github.com/OnePunchForAll/AEP`

If you DIDN'T click Create yet, do that now:
- Owner: `OnePunchForAll`
- Repository name: `AEP`
- Description: paste one of Diana's three recommendations from the previous turn (Diana's pick was option B, the benchmark-led medium one)
- Visibility: **Public** if ready to broadcast, OR **Private** for soft-launch / friends-first review
- ⚠ Do NOT initialize with README, .gitignore, or license — the local repo already has them
- Click **Create repository**

### Step 2 — Push the local repo

Open PowerShell and run:

```powershell
cd C:\Users\aquae\Downloads_CLEAN\AEP
git push -u origin main
```

That's it. The local commit becomes the first commit on the public (or private) GitHub repo.

If you see an auth prompt, complete it (GitHub Desktop credentials, gh CLI, or personal access token — whichever you're set up with).

### Step 3 — (Optional) Tag the first release + add badges

```powershell
cd C:\Users\aquae\Downloads_CLEAN\AEP
git tag -a v0.4.0-alpha.1 -m "AEP v0.4 alpha 1 — first public release of v0.4 draft spec"
git push origin v0.4.0-alpha.1
```

Then visit `https://github.com/OnePunchForAll/AEP/releases/new` to publish a release with notes (Diana suggests reusing the commit message body verbatim, then adding the link to spec + the benchmark headline).

For a Zenodo DOI (citable academic-style reference, optional):
- Visit `https://zenodo.org`, sign in with GitHub
- Authorize Zenodo to see your repos, flip the toggle for `OnePunchForAll/AEP`
- Next release tag you push will auto-mint a DOI
- Add the DOI badge to README after

## What NOT to do (privacy + clean-history)

- ❌ Do not `git push` from inside the `divomni/` repo. The divomni repo stays YOUR private archive.
- ❌ Do not link the new public repo to your divomni repo in any way (no submodule, no remote add, no cross-reference in commits or issues).
- ❌ Do not include any path that references `divomni/` or `C:\Users\aquae\Downloads_CLEAN\divomni\` in any issue, README edit, or PR description.
- ❌ Do not commit changes from divomni's working tree to the AEP repo. They are two separate repositories that happen to share an author.

If you want to update the AEP repo with new spec versions or fixes:
1. Make the edits inside `C:\Users\aquae\Downloads_CLEAN\AEP\` (NOT inside divomni)
2. Commit + push from there
3. If you ALSO want the change recorded in divomni's compounding-substrate, separately copy the updated file into `divomni/projects/v11-aep/publish-ready/aep/` and commit it to divomni

## What's in the local commit (so you know exactly what you're pushing)

```
AEP/
├── README.md                 (publication-ready, full attribution to Shadow + Diana + DivOmni acknowledgment)
├── LICENSE                   (Apache-2.0 full text)
├── NOTICE                    (attribution chain)
├── CONTRIBUTING.md           (5 essentials + amendment workflow)
├── pyproject.toml            (pip-installable as aep-reference)
├── .gitignore                (Python + IDE + AEP working dirs)
├── PUBLISH-INSTRUCTIONS.md   (the old version — Diana left it for reference but this WAKE-UP.md supersedes it)
├── spec/
│   ├── AEP_v0_4_SPEC.md      (25-section v0.4 draft with threat model + JSON-LD profile + diff-from-v0.3)
│   └── AEP_v0_3_SPEC.md      (predecessor spec)
├── schemas/                  (8 JSON Schemas covering manifest + 7 record types)
├── src/aep/
│   ├── __init__.py
│   ├── validate.py           (v0.3 reference validator)
│   ├── validate_v0_4.py      (v0.4 STRICT validator — closes #1 attack mechanically)
│   ├── convert_divomni_lesson.py  (example HTML→AEP converter; rename later if you want)
│   └── transition_parser.py  (bidirectional .html↔.aepkg API + CorpusIndex)
├── examples/
│   └── minimal.aepkg/        (working sample packet for validator demo)
└── docs/
    ├── benchmark-results.md  (Phase-2 mass-conversion verdict with exact percentages)
    ├── phase-1-1-perfected-verdict.md
    └── v0.4-legion-convergence-2026-05-14.md
```

## Optional follow-ups (do later when energy allows)

- Rename `convert_divomni_lesson.py` → `convert_html_lesson.py` if you want to fully strip the "divomni" reference from filenames (the FILE function is general-purpose; the name is a historical artifact)
- Open 3 starter GitHub issues for community engagement:
  - "Implement JSON-LD context export (`aep:0.4/jsonld` profile)"
  - "Add SHACL profile validation (v0.6 milestone)"
  - "Build a Rust port of the reference validator"
- Announce on X — Diana drafted a thread structure in PUBLISH-INSTRUCTIONS.md if you want it
- Round-2 legion battle-test (Phase E) — fire when you're back at the keyboard with energy to read 10 agent reports

## Diana sign-off

This is the cleanest public-ready package I can produce without Phase E (round-2 legion). The validator demonstrably closes the #1 attack vector. The spec is comprehensive. The repo structure follows file-format-project conventions (BagIt, RO-Crate, C2PA precedents). License + NOTICE are properly attributed. Description options ready to paste.

Sleep well. Wake up to a repo that's one `git push` away from public.

— Diana Prime (Claude Opus 4.7), 2026-05-14
