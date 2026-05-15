"""validate.py — AEP v0.7.1 unified validator entry point.

Re-exports the v0.7.1 validator (internally named ``validate_v0_6`` for
file-history continuity from earlier prereleases). External callers should
use the names exported from this module:

    from aep.validate import validate, ValidationConfig, ValidationResult

The validator wraps the v0.5.5 base (``validate_v0_5_1``) with all v0.6 +
v0.7 closures including:

  - Compact JSONL profile roundtrip parity
  - Embedded binary index integrity
  - Frozen offline JSON-LD context hash
  - aepkg.json SINGLE-AUTHORITY over BagIt + RO-Crate
  - Ed25519 signature verification (under aep:0.7/signed)
  - View-determinism gate (claim-ledger.html + integrity-tree.svg + provenance-graph.mmd)
  - integrity.state_hash + integrity.manifest_hash + integrity.views_merkle_root
    recompute from raw bytes (closes content-binding gap)

CLI:
    python -m aep.validate <packet> --profile aep:0.7/stable --conformance-level 2 --strict
"""
from __future__ import annotations

from aep.validate_v0_6 import (
    validate_v0_6 as validate,
    VALID_PROFILES_V0_6 as VALID_PROFILES,
    main as _validate_main,
    AEP70_INTEGRITY_STATE_HASH_MISMATCH,
    AEP70_INTEGRITY_MANIFEST_HASH_MISMATCH,
    AEP70_VIEWS_MERKLE_MISMATCH,
    AEP70_VIEW_DETERMINISM_MISMATCH,
)
from aep.validate_v0_5_1 import (  # noqa: F401
    ValidationConfig,
    ValidationResult,
    Finding,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)


def main(argv=None):
    """Run the v0.7.1 validator CLI."""
    return _validate_main(argv)


if __name__ == "__main__":
    import sys
    sys.exit(main())
