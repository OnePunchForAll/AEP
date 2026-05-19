"""AEP — Agent Evidence Packet — reference implementation.

Apache-2.0 licensed. See LICENSE + NOTICE.

External usage:

    from aep import (
        # v0.5.5 unified validator (entry point)
        validate_v0_5_1,
        ValidationConfig,
        ValidationResult,
        Finding,
        # v0.5 baseline (kept for backward-compat)
        validate_v0_5,
        # v0.4 baseline (compat-mode only)
        validate_packet_v04,
        # Migration tools
        migrate_v0_3_to_v0_5,
        deep_migrate_v0_5_shallow_to_v0_5,
    )

The unified post-v0.5 validator is ``validate_v0_5_1`` despite the v0.5.1 in the
function name (kept for git-history continuity through v0.5.3 + v0.5.4
sub-sprint patches; the file is the canonical v0.5.5 implementation).
"""
from __future__ import annotations

__version__ = "0.7.1"

# v0.4 baseline (compat mode)
from aep.validate_v0_4 import (  # noqa: F401
    validate_packet_v04,
    Report as ValidationReportV04,
)

# v0.5 baseline (Round-2 + Round-3 closures)
from aep.validate_v0_5 import (  # noqa: F401
    validate_v0_5,
)

# v0.5.5 unified validator (entry point for production callers)
from aep.validate_v0_5_1 import (  # noqa: F401
    validate_v0_5_1,
    ValidationConfig,
    ValidationResult,
    Finding,
)

# v0.6.0-rc1 validator + closures (strictly additive on v0.5.5)
try:
    from aep.validate_v0_6 import (  # noqa: F401
        validate_v0_6,
        VALID_PROFILES_V0_6,
        AEP60_COMPACT_ENUM_UNKNOWN_CODE,
        AEP60_COMPACT_ENUM_NON_ASCII,
        AEP60_COMPACT_ROUNDTRIP_NON_IDENTICAL,
        AEP60_COMPACT_WHITESPACE_INJECTED,
        AEP60_INDEX_HASH_MISMATCH,
        AEP60_INDEX_RECORD_SIZE_MISMATCH,
        AEP60_CONTEXT_HASH_MISMATCH,
        AEP60_CONTEXT_REMOTE_FETCH_FORBIDDEN,
        AEP60_BAGIT_MANIFEST_DIVERGENCE,
        AEP60_ROCRATE_ROOT_DIVERGENCE,
        AEP60_REVIEWER_COLLAPSE_SAME_SOURCE,
        AEP60_SOURCE_LOCATION_HASH_SENTINEL,
        AEP61_GR_CHAIN_TRANSITIVE_LAUNDERING,
        AEP61_SUPERSESSION_SELF_LOOP,
        AEP61_MIGRATION_RECEIPT_DEGENERATE,
        AEP61_IDENTITY_UNAUTHENTICATED,
        AEP61_BODY_ENVELOPE_LEAK,
        AEP61_SHARED_SCHEMA_LENS_COLLAPSE,
        AEP61_CONTENT_HASH_MISMATCH,
        AEP70_VIEW_DETERMINISM_MISMATCH,
        AEP70_VIEWS_MERKLE_MISMATCH,
        AEP70_INTEGRITY_STATE_HASH_MISMATCH,
        AEP70_INTEGRITY_MANIFEST_HASH_MISMATCH,
    )
    from aep.jsonl_compact import (  # noqa: F401
        RELIABILITY_TO_CODE,
        RELIABILITY_FROM_CODE,
        SCOPE_TO_CODE,
        AXIS_B_TO_CODE,
        STATUS_TO_CODE,
        encode_record,
        decode_record,
        encode_jsonl_line,
        encode_jsonl_file,
        decode_jsonl_line,
        decode_jsonl_bytes,
        verify_roundtrip,
    )
    from aep.build_index import (  # noqa: F401
        build_index,
        write_index,
        verify_index,
    )
    from aep.verification_receipt import (  # noqa: F401
        SCHEMA_VERSION as RECEIPT_SCHEMA_VERSION,
        build_receipt,
        emit_receipt,
        verify_chain,
        compute_packet_sha256,
        receipt_sha256,
        last_receipt_hash,
    )
    from aep.views import (  # noqa: F401
        derive_claim_ledger_html,
        derive_integrity_tree_svg,
        derive_provenance_graph_mmd,
        derive_all_views,
        write_all_views,
        view_sha256,
        views_merkle_root,
        verify_views,
    )
    from aep.signing import (  # noqa: F401
        AEP70_SIGNATURE_REQUIRED,
        AEP70_SIGNATURE_INVALID,
        AEP70_SIGNATURE_PUBKEY_FORMAT,
        AEP70_SIGNATURE_ALG_UNSUPPORTED,
        AEP70_SIGNATURE_DIGEST_DRIFT,
        signed_digest,
        sign_packet,
        verify_packet_signatures,
        generate_keypair,
    )
except ImportError:
    pass

# Migration tools
from aep.convert_v0_3_to_v0_5 import migrate_packet as migrate_v0_3_to_v0_5  # noqa: F401
from aep.convert_v0_5_shallow_to_deep import deep_migrate_packet as deep_migrate_v0_5_shallow_to_v0_5  # noqa: F401

# Bidirectional transition parser (.html / .md ↔ .aepkg/) — optional convenience API.
try:
    from aep.transition_parser import (  # noqa: F401
        find_packet_for_source,
        source_for_packet,
        read_packet_lossless,
        reconstruct_html_from_packet,
        packet_query,
        corpus_query,
        build_corpus_index,
        agent_view,
    )
except ImportError:
    pass

__all__ = [
    "__version__",
    "validate_packet_v04",
    "ValidationReportV04",
    "validate_v0_5",
    "validate_v0_5_1",
    "ValidationConfig",
    "ValidationResult",
    "Finding",
    "migrate_v0_3_to_v0_5",
    "deep_migrate_v0_5_shallow_to_v0_5",
    "validate_v0_6",
    "VALID_PROFILES_V0_6",
    "build_index",
    "write_index",
    "verify_index",
    "encode_jsonl_file",
    "decode_jsonl_bytes",
    "verify_roundtrip",
]
