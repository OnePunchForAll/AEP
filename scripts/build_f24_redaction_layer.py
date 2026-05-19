#!/usr/bin/env python3
"""F24 Evidence Rights & Redaction Layer.

AEP v1.2 immune-system primitive. Classifies every evidence row by visibility
class (operator source.md L188-190 verbatim 7-class enum) and produces redacted
exports with manifests that disclose what was removed.

HV5 closure HARD-CONSTRAINED:
- Every `hashed_only` field uses a per-packet random salt.
- Salt itself is stored under a non-public visibility class (recursion guard).
- Frequency-analysis attack is acknowledged explicitly per packet.
- Empirical: corpus-shared salt is shown to leak via co-occurrence; per-packet
  salt defeats the same attack at the same N.

API:
  classify_evidence(source_record, sensitivity_hint=None) -> dict
  redact_for_export(packet, target_visibility="public") -> redacted_packet (dict)
  per_packet_random_salt_defeats_freq_analysis(synthetic_n=10) -> bool

Composes_with: F18 SourceProvenanceGraph (lineage_basis stamped on each
EvidenceRightsRedactionRecord); v1.2 SPEC sec8 + sec18.

Cites:
  - operator-2026-05-18-aep-v1-2 source.md L29 + L186-192 (visibility enum)
  - adversary-2026-05-18-aep-v1-2-premortem.md A5 (HV5 hash correlation)
  - sec73.6 honest framing (synthetic-N + bounded-N disclaimer)
  - GDPR Article 25 + Capability security + Differential privacy fundamentals

Author: forge (Phase 4c, single-forge per sec73.4)
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Iterable

# 7 visibility classes verbatim from operator source.md L188-190.
VISIBILITY_CLASSES = (
    "public",
    "private",
    "local_only",
    "hashed_only",
    "encrypted",
    "ephemeral",
    "forbidden_to_export",
)

# Heuristic auto-classifier rules. sensitivity_hint overrides if present.
_SENSITIVE_KEY_FRAGMENTS = (
    "password", "secret", "private_key", "ssn", "tax_id", "bank_account",
    "credit_card", "api_key", "token", "session",
)

_PRIVATE_KEY_FRAGMENTS = (
    "personal", "user_path", "home_path", "device_id", "operator_email",
)

_LOCATION_PRIVATE_HINTS = (
    "C:/Users/", "C:\\Users\\", "/Users/", "/home/", "user-uploaded",
)


def classify_evidence(source_record: dict, sensitivity_hint: str | None = None) -> dict:
    """Return a classification dict with visibility_class and reasoning.

    Args:
      source_record: a dict shaped like an AEP source row (with keys 'id',
        'kind', 'location', 'metadata', etc.).
      sensitivity_hint: optional explicit override in VISIBILITY_CLASSES.

    Returns:
      {visibility_class, reason, candidate_redaction_method,
       source_record_id, source_record_kind}
    """
    if not isinstance(source_record, dict):
        raise TypeError("source_record must be a dict")
    rid = source_record.get("id", "src:UNKNOWN")
    kind = source_record.get("kind") or source_record.get("evidence_kind") or "source"

    if sensitivity_hint is not None:
        if sensitivity_hint not in VISIBILITY_CLASSES:
            raise ValueError(
                f"sensitivity_hint {sensitivity_hint!r} not in VISIBILITY_CLASSES"
            )
        return {
            "source_record_id": rid,
            "source_record_kind": kind,
            "visibility_class": sensitivity_hint,
            "reason": "explicit_sensitivity_hint",
            "candidate_redaction_method": _method_for(sensitivity_hint),
        }

    flat = json.dumps(source_record, sort_keys=True).lower()

    # Forbidden-to-export keys = real secret material.
    if any(frag in flat for frag in _SENSITIVE_KEY_FRAGMENTS):
        return {
            "source_record_id": rid,
            "source_record_kind": kind,
            "visibility_class": "forbidden_to_export",
            "reason": "matched_secret_key_fragment",
            "candidate_redaction_method": "field_marked_ephemeral_no_export",
        }

    # User-personal paths or device IDs.
    if any(frag in flat for frag in _PRIVATE_KEY_FRAGMENTS):
        return {
            "source_record_id": rid,
            "source_record_kind": kind,
            "visibility_class": "private",
            "reason": "matched_private_key_fragment",
            "candidate_redaction_method": "value_replaced_with_placeholder",
        }

    # Local file references with operator/user paths -> hashed_only on export.
    loc = source_record.get("location", {})
    if isinstance(loc, dict):
        val = str(loc.get("value", ""))
        if any(h in val for h in _LOCATION_PRIVATE_HINTS):
            return {
                "source_record_id": rid,
                "source_record_kind": kind,
                "visibility_class": "hashed_only",
                "reason": "matched_local_filesystem_hint_in_location",
                "candidate_redaction_method": "value_replaced_with_hash",
            }
        if loc.get("kind") == "file":
            return {
                "source_record_id": rid,
                "source_record_kind": kind,
                "visibility_class": "local_only",
                "reason": "location_kind_is_file",
                "candidate_redaction_method": "value_dropped_at_export_only",
            }

    # _unverified_fetch hints toward EXPERIMENTAL provenance (not sensitive).
    if isinstance(loc, dict) and loc.get("_unverified_fetch") is True:
        return {
            "source_record_id": rid,
            "source_record_kind": kind,
            "visibility_class": "public",
            "reason": "url_source_unverified_fetch_but_public",
            "candidate_redaction_method": "field_removed",
        }

    # Default = public (URL-cited sources, well-known docs, etc.).
    return {
        "source_record_id": rid,
        "source_record_kind": kind,
        "visibility_class": "public",
        "reason": "default_public_no_sensitive_markers",
        "candidate_redaction_method": "field_removed",
    }


def _method_for(vis: str) -> str:
    return {
        "public": "field_removed",
        "private": "value_replaced_with_placeholder",
        "local_only": "value_dropped_at_export_only",
        "hashed_only": "value_replaced_with_hash",
        "encrypted": "value_encrypted_aes256",
        "ephemeral": "field_marked_ephemeral_no_export",
        "forbidden_to_export": "field_marked_ephemeral_no_export",
    }[vis]


def _gen_packet_salt() -> str:
    return secrets.token_hex(32)  # 256-bit per-packet salt


def _salt_record(visibility_class: str) -> dict:
    """HV5 closure record. Always per_packet_random_salt for hashed_only."""
    if visibility_class == "hashed_only":
        salt = _gen_packet_salt()
        return {
            "salt_scope": "per_packet_random_salt",
            "salt_present": True,
            "salt_storage_class": "local_only",  # salt itself never public
            "salt_value": salt,
            "frequency_analysis_attack_acknowledged": True,
            "frequency_analysis_attack_text": (
                "Cross-packet hash correlation could in theory reveal that the same "
                "source was used across packets. This packet uses a per-packet random "
                "salt (256 bits of entropy), so frequency-analysis recovery would "
                "require corpus-wide salt recovery rather than direct hash matching."
            ),
        }
    return {
        "salt_scope": "no_salt",
        "salt_present": False,
        "frequency_analysis_attack_acknowledged": False,
    }


def _salt_hash(value: str, salt: str) -> str:
    """Salted hash using HMAC-SHA256 (per-packet key)."""
    return hmac.new(salt.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_redaction_record(
    source_record: dict, classification: dict, packet_salt: dict
) -> dict:
    """Build an EvidenceRightsRedactionRecord-shaped dict for the source."""
    vis = classification["visibility_class"]
    rec = {
        "type": "EvidenceRightsRedactionRecord",
        "schema_version": "aep-evidence-rights-redaction-0.1",
        "id": f"err:{classification['source_record_id'].replace(':','-')}-{vis}",
        "bound_to_evidence_id": classification["source_record_id"],
        "evidence_kind": classification.get("source_record_kind", "source"),
        "visibility_class": vis,
        "hash_correlation_resistance": packet_salt if vis == "hashed_only" else {
            "salt_scope": "no_salt",
            "salt_present": False,
            "frequency_analysis_attack_acknowledged": False,
        },
        "export_manifest_disclosure": {
            "disclosed_in_export": vis != "public",
            "what_was_removed": _disclosure_removed(vis),
            "what_was_kept": _disclosure_kept(vis),
        },
        "redaction_method": classification["candidate_redaction_method"],
        "lineage_basis": {
            "classification": "EXTENDS",
            "external_precedents": [
                "GDPR Article 25 privacy-by-design",
                "Capability security",
                "Differential privacy fundamentals",
            ],
            "verifying_grep": (
                "rg 'gdpr|privacy by design|differential privacy|capability "
                "security' --type md research/sources/"
            ),
            "n_hits": 0,
        },
        "classified_at": _dt.datetime.now(_dt.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classify_signature_ed25519": "ed25519_pending_phase_5_keypair",
    }
    return rec


def _disclosure_removed(vis: str) -> str:
    return {
        "public": "Nothing was removed; this row is fully public.",
        "private": (
            "Personal identifiers (paths, names, device IDs) were replaced with "
            "placeholders. The fact a private value existed is disclosed."
        ),
        "local_only": (
            "The source value was kept local to the authoring machine and was not "
            "included in the export."
        ),
        "hashed_only": (
            "The original source value was replaced with a per-packet salted hash. "
            "The original is recoverable only by an authorized holder of the salt."
        ),
        "encrypted": (
            "The source value was replaced with AES-256 ciphertext. The key is held "
            "by the authoring principal and is not in this export."
        ),
        "ephemeral": (
            "The field was marked ephemeral and dropped at export time. It is not "
            "stored beyond the producing session."
        ),
        "forbidden_to_export": (
            "The field is forbidden to export under any visibility class. The "
            "manifest discloses the field existed but never leaves local."
        ),
    }[vis]


def _disclosure_kept(vis: str) -> str:
    return {
        "public": "All fields kept verbatim.",
        "private": "The structural shape of the row (kind, relations) is kept.",
        "local_only": "Only the row id and kind survive in the export manifest.",
        "hashed_only": "The salted hash, the kind, and the relations survive.",
        "encrypted": "The ciphertext blob and its key fingerprint survive.",
        "ephemeral": "Nothing survives in the export.",
        "forbidden_to_export": "Nothing survives beyond a manifest acknowledgement.",
    }[vis]


def redact_for_export(packet: dict, target_visibility: str = "public") -> dict:
    """Apply F24 redaction rules to a packet dict.

    Args:
      packet: a dict with key 'sources' = list of source records.
      target_visibility: the lowest visibility class the consumer is cleared for.

    Returns:
      A dict {redacted_packet, redaction_records[], packet_salt_record}.
      The redacted_packet drops or transforms rows above target_visibility.
    """
    if not isinstance(packet, dict):
        raise TypeError("packet must be a dict")
    if target_visibility not in VISIBILITY_CLASSES:
        raise ValueError(f"target_visibility {target_visibility!r} invalid")

    sources = packet.get("sources") or packet.get("data", {}).get("sources") or []
    packet_salt = _gen_packet_salt()
    redaction_records: list[dict] = []
    redacted_sources: list[dict] = []
    classes_seen: collections.Counter = collections.Counter()

    for src in sources:
        cls = classify_evidence(src)
        classes_seen[cls["visibility_class"]] += 1
        rec = _build_redaction_record(
            src,
            cls,
            packet_salt={
                "salt_scope": "per_packet_random_salt",
                "salt_present": True,
                "salt_storage_class": "local_only",
                "frequency_analysis_attack_acknowledged": True,
                "frequency_analysis_attack_text": (
                    "Cross-packet hash correlation could in theory reveal that "
                    "the same source was used across packets. Per-packet random "
                    "salt makes this attack require corpus-wide salt recovery."
                ),
            } if cls["visibility_class"] == "hashed_only" else {
                "salt_scope": "no_salt",
                "salt_present": False,
                "frequency_analysis_attack_acknowledged": False,
            },
        )
        redaction_records.append(rec)

        # Apply the redaction to the row itself.
        cls_v = cls["visibility_class"]
        if _allowed_in_export(cls_v, target_visibility):
            if cls_v == "hashed_only":
                hashed = dict(src)
                loc_val = json.dumps(src.get("location", {}), sort_keys=True)
                hashed["location"] = {
                    "kind": "salted_hash",
                    "value": _salt_hash(loc_val, packet_salt),
                    "salt_scope": "per_packet_random_salt",
                }
                redacted_sources.append(hashed)
            elif cls_v == "private":
                placeheld = dict(src)
                placeheld["location"] = {
                    "kind": "placeholder",
                    "value": "<redacted: private>",
                }
                redacted_sources.append(placeheld)
            else:
                redacted_sources.append(src)
        # else dropped entirely

    redacted_packet = dict(packet)
    redacted_packet["sources"] = redacted_sources
    redacted_packet["_f24_export_manifest"] = {
        "target_visibility": target_visibility,
        "rows_kept": len(redacted_sources),
        "rows_dropped": len(sources) - len(redacted_sources),
        "class_counts": dict(classes_seen),
        "packet_salt_storage": "local_only_NOT_INCLUDED_IN_EXPORT",
    }

    return {
        "redacted_packet": redacted_packet,
        "redaction_records": redaction_records,
        "packet_salt_value_local_only": packet_salt,
    }


def _allowed_in_export(cls_v: str, target_v: str) -> bool:
    """Order: public > hashed_only > private > local_only > encrypted >
       ephemeral > forbidden_to_export. Higher class is kept in export at that
       target or lower-trust target."""
    order = {
        "public": 7,
        "hashed_only": 6,
        "encrypted": 5,
        "private": 4,
        "local_only": 3,
        "ephemeral": 2,
        "forbidden_to_export": 1,
    }
    # An export at target_v only carries classes >= target_v in trust order.
    # 'public' export carries only public (or hashed_only). Override: hashed
    # always allowed in any export because the salt hides the original.
    if cls_v == "forbidden_to_export":
        return False
    if cls_v == "ephemeral":
        return False
    if cls_v == "local_only":
        return target_v in ("local_only", "encrypted", "private")
    if cls_v == "private":
        return target_v in ("private", "local_only", "encrypted")
    return True


def per_packet_random_salt_defeats_freq_analysis(synthetic_n: int = 10) -> dict:
    """Empirical disconfirmer for HV5.

    Builds two attack scenarios over `synthetic_n` synthetic packets that
    each cite the same N=10 secret sources. Scenario A uses a corpus-shared
    salt; scenario B uses a per-packet random salt. Returns recovery counts
    and verdict.
    """
    secret_sources = [f"file:/operator/secret_{i}.pdf" for i in range(10)]

    # Scenario A: corpus-shared salt.
    shared_salt = _gen_packet_salt()
    a_hashes_by_packet: list[list[str]] = []
    for _ in range(synthetic_n):
        a_hashes_by_packet.append([_salt_hash(s, shared_salt) for s in secret_sources])
    # Adversary: hash that appears in EVERY packet is a strong signal of a shared source.
    flat_a = collections.Counter()
    for pkt in a_hashes_by_packet:
        for h in pkt:
            flat_a[h] += 1
    a_recovered = sum(1 for h, c in flat_a.items() if c == synthetic_n)

    # Scenario B: per-packet random salt.
    b_hashes_by_packet: list[list[str]] = []
    for _ in range(synthetic_n):
        per_salt = _gen_packet_salt()
        b_hashes_by_packet.append([_salt_hash(s, per_salt) for s in secret_sources])
    flat_b = collections.Counter()
    for pkt in b_hashes_by_packet:
        for h in pkt:
            flat_b[h] += 1
    b_recovered = sum(1 for h, c in flat_b.items() if c == synthetic_n)

    verdict = (a_recovered == len(secret_sources)) and (b_recovered == 0)
    return {
        "synthetic_n_packets": synthetic_n,
        "secret_source_count": len(secret_sources),
        "corpus_shared_salt_recovered": a_recovered,
        "per_packet_salt_recovered": b_recovered,
        "verdict_per_packet_salt_defeats_freq_analysis": verdict,
        "note": (
            "Scenario A: a hash present in every packet is recoverable as a shared "
            "source. Scenario B: per-packet random salt makes the same hash differ "
            "across packets, defeating direct frequency analysis."
        ),
    }


def _retro_apply_to_packets(packet_paths: list[str]) -> dict:
    """Retro-classify all sources rows in the given .aepkg packet paths."""
    summary: list[dict] = []
    classes_total: collections.Counter = collections.Counter()
    for p in packet_paths:
        src_path = os.path.join(p, "data", "sources.jsonl")
        if not os.path.exists(src_path):
            summary.append({"packet": p, "sources_jsonl_present": False})
            continue
        rows = []
        with open(src_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        classifications = [classify_evidence(r) for r in rows]
        counts = collections.Counter(c["visibility_class"] for c in classifications)
        classes_total.update(counts)
        summary.append({
            "packet": p,
            "sources_jsonl_present": True,
            "rows": len(rows),
            "class_counts": dict(counts),
        })
    return {
        "packets": summary,
        "class_counts_aggregate": dict(classes_total),
    }


def _emit_log(outcome: dict, log_path: str) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(outcome) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retro", action="store_true",
                        help="Run retro-classification on 3 v1.0.3 packets.")
    parser.add_argument("--freq-test", action="store_true",
                        help="Run HV5 frequency-analysis disconfirmer.")
    parser.add_argument("--log",
                        default=""
                                ".claude/_logs/aep-v12-f24-retro-redaction.jsonl")
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args(argv)

    outcomes: dict[str, Any] = {
        "tool": "build_f24_redaction_layer.py",
        "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if args.freq_test:
        outcomes["freq_test"] = per_packet_random_salt_defeats_freq_analysis(args.n)
        _emit_log(outcomes["freq_test"], args.log)

    if args.retro:
        packet_paths = [
            "projects/v11-aep/"
            "publish-ready/aep/examples/minimal.aepkg",
            "projects/v11-aep/"
            "publish-ready/aep/examples/minimal-v0_7-signed.aepkg",
            "projects/v11-aep/"
            "publish-ready/aep/tests/lane_b/atk-api-surface-hallucination.aepkg",
        ]
        outcomes["retro"] = _retro_apply_to_packets(packet_paths)
        _emit_log(outcomes["retro"], args.log)

    print(json.dumps(outcomes, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
