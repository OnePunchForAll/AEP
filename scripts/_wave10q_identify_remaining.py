"""Wave 10q (final batch-3) — identify the 63 remaining doctrine/_proposals/*.html
not yet converted by Wave 8c (200) + Wave 9c2 batch-2 (200) per K6 ledger.

Per V15-WAVE-10Q charter (sec73.6 honest framing):
  - 263 entering Wave 9 (cohort entering point per Wave 9c-2 report)
  - 200 converted in Wave 9c-2 (batch-2)
  - 63 remaining = THIS WAVE (batch-3 final closure to 463/463)

Outputs:
  - prints CSV-ready list of remaining canonical .html paths
  - writes manifest to projects/v11-aep/publish-ready/aep/V15_WAVE10Q_MANIFEST.json
"""
import json, os, sys, glob

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
RECEIPTS = os.path.join(ROOT, '.claude', 'aep', 'transactions', 'aepfs_receipts.jsonl')
PROPOSAL_GLOB = os.path.join(ROOT, 'doctrine', '_proposals', '*.html')


def norm(p: str) -> str:
    """Normalize to forward-slash + lowercase drive-letter + absolute by repo root."""
    p = p.replace('\\', '/').replace('//', '/')
    if len(p) > 2 and p[1] == ':':
        p = p[0].lower() + p[1:]
    # If relative, anchor at repo root
    if not (len(p) > 2 and p[1] == ':') and not p.startswith('/'):
        # treat as relative to ROOT
        repo_root = ROOT.replace('\\', '/')
        if len(repo_root) > 2 and repo_root[1] == ':':
            repo_root = repo_root[0].lower() + repo_root[1:]
        p = repo_root.rstrip('/') + '/' + p
    return p


def canonical_for_aepkg_path(p: str) -> str:
    """If p is a .aepkg/* path inside doctrine/_proposals/, derive the canonical .html.
    Otherwise return p unchanged."""
    if '.aepkg' not in p:
        return p
    # split at '.aepkg'
    idx = p.find('.aepkg')
    base = p[:idx]
    return base + '.html'


def main():
    # 1. Collect canonical .html files in doctrine/_proposals
    all_proposals = sorted({
        norm(p) for p in glob.glob(PROPOSAL_GLOB)
    })

    # 2. Collect already-converted target paths from K6 receipts
    done_canonical = set()
    waves_of_interest = {'wave8c-doctrine-proposals', 'wave9c2-doctrine-proposals-batch2'}
    with open(RECEIPTS, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            wave = row.get('wave_id') or row.get('wave')
            if wave not in waves_of_interest:
                continue
            # Wave 8c uses target_path (.aepkg). Wave 9c2 uses source_path (canonical .html).
            for k in ('source_path', 'target_path', 'companion_path'):
                tp = row.get(k) or ''
                if not tp:
                    continue
                tp_norm = norm(tp)
                if '/doctrine/_proposals/' not in tp_norm:
                    continue
                canon = canonical_for_aepkg_path(tp_norm)
                # Some target_path entries point at .aepkg directory without trailing /
                # If canon doesn't end in .html, add it
                if not canon.endswith('.html'):
                    if canon.endswith('.aepkg') or canon.endswith('.aepkg/'):
                        canon = canon.rstrip('/').replace('.aepkg', '.html')
                done_canonical.add(canon)

    # 3. Determine remaining = all - done
    remaining = sorted([p for p in all_proposals if p not in done_canonical])

    print(f"[Wave 10q identify] cohort total .html = {len(all_proposals)}")
    print(f"[Wave 10q identify] K6 already-done canonical = {len(done_canonical)}")
    print(f"[Wave 10q identify] remaining canonical = {len(remaining)}")

    manifest = {
        "wave_id": "v15-lts-wave-10q-doctrine-proposals-batch3-final",
        "cohort_total": len(all_proposals),
        "already_converted_canonical": sorted(done_canonical),
        "remaining_for_this_wave": remaining,
        "expected_remaining_count": 63,
        "honest_framing": (
            "Per Wave 9c-2 forge report, 263 cohort entering Wave 9 -> 200 done in 9c-2 -> "
            "63 remaining. Drift detected here would indicate "
            "K6 ledger / cohort glob mismatch and must be reconciled "
            "per sec73.6 honest framing."
        ),
    }

    out = os.path.join(ROOT, 'projects', 'v11-aep', 'publish-ready', 'aep', 'V15_WAVE10Q_MANIFEST.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    print(f"[Wave 10q identify] manifest -> {out}")


if __name__ == '__main__':
    main()
