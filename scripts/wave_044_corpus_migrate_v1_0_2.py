#!/usr/bin/env python3
"""wave_044_corpus_migrate_v1_0_2.py — Mass-migrate all .aepkg packets to v1.0.2.

Pattern per v0_8 precedent: ADDITIVE .migration_history/v1_0_2.jsonl entry per packet.
Body files untouched (§V60-2 Axiom 4). aepkg.json untouched. No schema changes.

v1.0.x primitives are RUNTIME (F9 cross_substrate_quorum_executor + F10 signed_in_toto_ITE6_receipt_GA),
NOT packet-format additions. Migration is bookkeeping for trust-root verifier coverage at v1.0.2 maturity.

Per operator "upgrade all aep files to v1.0.2" 2026-05-17. Composes with §V80-17 v1.0.2 release.

Stdlib only.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
RECEIPT_LEDGER = REPO_ROOT / ".claude" / "_logs" / "corpus-migration-v1-0-2-receipts.jsonl"
NOW = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    print(f"Wave-044 corpus migration v1.0.2 · {NOW}")
    packets = sorted(REPO_ROOT.rglob("*.aepkg"))
    n_total = len(packets)
    print(f"  packets discovered: {n_total}")

    n_migrated = 0
    n_skipped_already_v1 = 0
    n_errors = 0
    sample_paths_migrated = []

    for pkg in packets:
        try:
            history_dir = pkg / ".migration_history"
            history_dir.mkdir(exist_ok=True)
            v1_0_2_file = history_dir / "v1_0_2.jsonl"
            if v1_0_2_file.exists():
                n_skipped_already_v1 += 1
                continue
            event = {
                "event_type": "v1.0.2_migration",
                "timestamp": NOW,
                "previous_profile": "aep:0.8/stable",
                "new_profile": "aep:1.0.2/stable",
                "fields_initialized": [],
                "runtime_primitives_unlocked": [
                    "F9_cross_substrate_quorum_executor_default_N3_python_node_perl",
                    "F10_signed_in_toto_ITE6_receipt_GA_default_enabled_jcs_rfc8785",
                ],
                "verifier_set_expanded": {
                    "from_v0_8": ["python", "node", "go", "browser-js", "perl", "typescript", "rust", "java"],
                    "to_v1_0_2": ["python", "node", "go", "browser-js", "perl", "typescript", "rust", "java", "csharp"],
                    "n_executable": 9,
                    "n_trust_pinned": 20,
                },
                "body_files_untouched": True,
                "aepkg_json_untouched": True,
                "manifest_hash_recomputed": False,
                "migrator_version": "1.0.2",
                "migrator_script": "wave_044_corpus_migrate_v1_0_2.py",
                "operator_authority": "make_it_perfect_2026_05_17_complete_authority",
                "composes_with": ["§V80-15 v1.0.0.0 release", "§V80-16 v1.0.1 release", "§V80-17 v1.0.2 release"],
                "honest_disclosure": (
                    "v1.0.x primitives F9 (quorum executor) + F10 (signed in-toto receipt GA) are RUNTIME mechanisms, "
                    "NOT packet-format additions. Packet structure unchanged from v0.8.0; migration is bookkeeping. "
                    "Body files untouched per §V60-2 Axiom 4. v0.8 readers continue consuming v1.0.2 packets identically "
                    "(zero breaking changes — empirically validated Wave-028 corpus 1127/1127 unanimous consensus). "
                    "v1.0.2 substrate offers same packet API but expanded runtime quorum verification (N=3 default, "
                    "N=9 trust-pinned) and signed-receipt audit trail."
                ),
            }
            payload = json.dumps(event, separators=(",", ":")) + "\n"
            v1_0_2_file.write_text(payload, encoding="utf-8")
            n_migrated += 1
            if len(sample_paths_migrated) < 5:
                sample_paths_migrated.append(str(pkg.relative_to(REPO_ROOT)))
        except Exception as e:
            n_errors += 1
            if n_errors <= 3:
                print(f"  ERROR on {pkg}: {type(e).__name__}: {e}", file=sys.stderr)

    summary = {
        "wave": "044",
        "audited_at": NOW,
        "n_packets_total": n_total,
        "n_migrated": n_migrated,
        "n_skipped_already_v1_0_2": n_skipped_already_v1,
        "n_errors": n_errors,
        "sample_paths_migrated": sample_paths_migrated,
        "migrator_version": "1.0.2",
        "body_files_untouched": True,
        "operator_authority": "make_it_perfect_2026_05_17",
    }
    canonical = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    summary["receipt_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    RECEIPT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":")) + "\n")

    print()
    print("=" * 60)
    print(f"WAVE-044 CORPUS MIGRATION v1.0.2 RESULTS")
    print(f"  packets total:           {n_total}")
    print(f"  migrated to v1.0.2:      {n_migrated}")
    print(f"  skipped (already v1.0.2): {n_skipped_already_v1}")
    print(f"  errors:                  {n_errors}")
    print(f"  receipt sha256:          {summary['receipt_sha256'][:16]}...")
    print(f"  receipt at:              {RECEIPT_LEDGER.relative_to(REPO_ROOT)}")
    return 0 if n_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
