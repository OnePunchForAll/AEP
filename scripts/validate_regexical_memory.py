#!/usr/bin/env python3
"""validate_regexical_memory.py - JSON Schema validator for RegexicalCue records (AEP v1.0.3).

Loads schema at projects/v11-aep/publish-ready/aep/schemas/regexical_memory.schema.json
Validates each JSONL row in input file against draft 2020-12.
Lints regex.forbidden_features (rejects lookbehind, backreferences, catastrophic nested quantifiers,
engine-specific conditionals if present in patterns).
M5 closure: explicit allow-list audit on recall_payload / integrity / srs sub-objects
(schema declares additionalProperties: true; validator-side WARN by default, --strict-allow-list
escalates to ERROR).

Exits 0 on operator's regexical_memory_example_adversary.jsonl.
Exits 1 on synthetic invalid (missing stop_condition or other required field).

Composes with AEP_v1_0_3_SPEC.md sec3 + M5 closure binding under sec69.4.

Stdlib + jsonschema dependency.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
import sys
from typing import Any, Dict, List

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("FATAL: jsonschema package required (pip install jsonschema>=4.0)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCHEMA_PATH = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "schemas" / "regexical_memory.schema.json"

# M5 closure: explicit allow-list per sub-object (computed from schema's `properties` keys).
ALLOW_LIST = {
    "recall_payload": {
        "distinguishers", "failure_prevented", "kind", "minimum_recall_fields",
        "one_sentence", "owner_agent", "stop_condition", "when_to_open_full_file",
    },
    "integrity": {
        "canonicalization", "cue_record_sha256_excluding_integrity", "receipt_required_for_install",
    },
    "srs": {
        "algorithm", "due_at", "ease_factor", "interval_days", "lapses",
        "minimum_ease_factor", "next_reviews_seed", "repetitions", "review_scale",
    },
}

# Forbidden regex features (rejected if present in any cue's regex.patterns).
# Mechanical detection patterns (best-effort lints, not full parsers).
FORBIDDEN_FEATURE_DETECTORS = {
    "lookbehind": re.compile(r"\(\?<[=!]"),
    "lookahead_with_capture_groups_outside_class": re.compile(r"\(\?[=!]"),
    "backreferences": re.compile(r"\\[1-9]"),
    "catastrophic_nested_quantifiers": re.compile(r"\([^)]*[+*]\)[+*]"),
    "engine_specific_conditionals": re.compile(r"\(\?\("),
    "atomic_groups": re.compile(r"\(\?>"),
    "named_backreference": re.compile(r"\\k<"),
}


def load_schema() -> Dict[str, Any]:
    if not SCHEMA_PATH.exists():
        print(f"FATAL: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(2)
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_one_row(row: Dict[str, Any], schema: Dict[str, Any], strict_allow_list: bool) -> List[str]:
    """Return list of error strings (empty if PASS)."""
    errors: List[str] = []
    warnings: List[str] = []

    # Step 1: standard draft 2020-12 validation.
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(row), key=lambda e: e.path):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"SCHEMA_ERROR at {path}: {err.message}")

    if errors:
        return errors

    # Step 2: M5 closure - allow-list audit on recall_payload / integrity / srs.
    for sub_obj_name, allowed_keys in ALLOW_LIST.items():
        sub_obj = row.get(sub_obj_name)
        if not isinstance(sub_obj, dict):
            continue
        unknown_keys = set(sub_obj.keys()) - allowed_keys
        for unk in sorted(unknown_keys):
            msg = f"ALLOW_LIST_WARN at {sub_obj_name}.{unk}: key not in schema's declared properties (additionalProperties: true default; v1.0.3.1 will tighten to false)"
            if strict_allow_list:
                errors.append(msg.replace("ALLOW_LIST_WARN", "ALLOW_LIST_ERROR"))
            else:
                warnings.append(msg)

    # Step 3: portable-rxmem-v1 dialect lint - reject forbidden_features if found in actual patterns.
    regex_obj = row.get("regex", {})
    patterns = regex_obj.get("patterns", []) or []
    declared_forbidden = set(regex_obj.get("forbidden_features", []) or [])
    for i, pat in enumerate(patterns):
        if not isinstance(pat, str):
            continue
        for feat_name, detector in FORBIDDEN_FEATURE_DETECTORS.items():
            if detector.search(pat):
                # If detected feature is in declared forbidden_features, it's a contradiction
                # (cue declares the feature is forbidden yet uses it).
                if feat_name in declared_forbidden or feat_name.split("_")[0] in declared_forbidden:
                    errors.append(
                        f"FORBIDDEN_FEATURE_ERROR in regex.patterns[{i}] = {pat!r}: "
                        f"pattern uses '{feat_name}' which cue declared as forbidden"
                    )
                else:
                    warnings.append(
                        f"FORBIDDEN_FEATURE_WARN in regex.patterns[{i}] = {pat!r}: "
                        f"pattern uses '{feat_name}' (potential cross-runtime hazard; portable-rxmem-v1 prefers literal+word_boundary+optional_hyphen_space only)"
                    )

    # Step 4: integrity sub-object self-consistency (informational).
    integ = row.get("integrity", {}) or {}
    receipt_req = integ.get("receipt_required_for_install")
    if receipt_req and not receipt_req.startswith(("F10_signed_in_toto", "STAGED_v_")):
        warnings.append(
            f"INTEGRITY_RECEIPT_FORMAT_WARN: receipt_required_for_install = {receipt_req!r} "
            f"does not start with 'F10_signed_in_toto' or 'STAGED_v_' (not strictly required, but uncommon)"
        )

    # Emit warnings on stderr.
    for w in warnings:
        print(w, file=sys.stderr)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RegexicalCue JSONL rows against AEP v1.0.3 schema.")
    parser.add_argument("input_path", help="Path to JSONL file (one RegexicalCue per line).")
    parser.add_argument("--strict-allow-list", action="store_true",
                        help="Escalate M5 allow-list violations from WARN to ERROR.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-row PASS messages on stdout.")
    args = parser.parse_args()

    schema = load_schema()
    input_path = pathlib.Path(args.input_path)
    if not input_path.exists():
        print(f"FATAL: input file not found: {input_path}", file=sys.stderr)
        return 1

    total_rows = 0
    pass_rows = 0
    fail_rows = 0
    for i, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        total_rows += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"PARSE_ERROR at line {i}: {e}", file=sys.stderr)
            fail_rows += 1
            continue
        errors = validate_one_row(row, schema, args.strict_allow_list)
        if errors:
            fail_rows += 1
            print(f"FAIL line {i} (id={row.get('id', '<no id>')})", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
        else:
            pass_rows += 1
            if not args.quiet:
                print(f"PASS line {i} (id={row.get('id', '<no id>')})")

    print(f"\nSummary: {pass_rows}/{total_rows} PASS, {fail_rows}/{total_rows} FAIL")
    return 0 if fail_rows == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
