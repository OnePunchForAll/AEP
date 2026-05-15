"""Build JCS edge-vector corpus with safe ASCII string encoding.

Produces test_vectors/v0_7/A.11-canonical-surface/vectors.json — a 52-vector
canonical-surface adversarial corpus. Input bytes that aren't safe JSON
strings (control chars, BOM, RTL override, raw NaN/Infinity) are stored as
hex-encoded fields with `_hex` suffix; runners decode to bytes before exercising.
"""
import json
from pathlib import Path

VECTORS = [
    {"id": "V001", "category": "duplicate_keys",
     "description": "Duplicate object keys MUST be rejected (RFC 8259 + RFC 8785).",
     "input_raw": '{"a":1,"a":2}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_DUPLICATE_KEY"},

    {"id": "V002", "category": "large_integer",
     "description": "Integer exceeding IEEE-754 safe range (2^53) MUST be encoded as decimal string in canonical form.",
     "input_decoded": {"big": 9007199254740993},
     "expected_canonical_output": '{"big":"9007199254740993"}',
     "expected_outcome": "ACCEPT_AS_STRING"},

    {"id": "V003", "category": "large_negative_integer",
     "description": "Negative integer below -2^53 MUST be encoded as decimal string.",
     "input_decoded": {"neg": -9007199254740993},
     "expected_canonical_output": '{"neg":"-9007199254740993"}',
     "expected_outcome": "ACCEPT_AS_STRING"},

    {"id": "V004", "category": "nan_rejection",
     "description": "NaN MUST be rejected (RFC 8785 disallows; AEP-NUMERIC-v1 already enforces).",
     "input_raw": '{"x":NaN}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_NAN"},

    {"id": "V005", "category": "infinity_rejection",
     "description": "Infinity MUST be rejected.",
     "input_raw": '{"x":Infinity}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_INFINITY"},

    {"id": "V006", "category": "negative_infinity_rejection",
     "description": "-Infinity MUST be rejected.",
     "input_raw": '{"x":-Infinity}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_INFINITY"},

    {"id": "V007", "category": "utf16_property_sort",
     "description": "Object keys MUST be sorted by UTF-16 code units (RFC 8785), NOT UTF-8 bytes.",
     "input_decoded": {"é": 1, "f": 2, "e": 3},
     "expected_canonical_output": '{"e":3,"f":2,"é":1}',
     "expected_outcome": "ACCEPT_SORTED"},

    {"id": "V008", "category": "nfc_vs_nfd",
     "description": "NFC and NFD forms of same visual string have different sort positions; AEP-CANON-v1 MUST preserve parsed bytes (no post-parse normalization).",
     "input_decoded": {"café": 1, "café": 2},
     "expected_canonical_output_form": "BOTH_KEYS_PRESERVED",
     "expected_outcome": "ACCEPT_WITHOUT_NORMALIZE"},

    {"id": "V009", "category": "empty_string_vs_null",
     "description": "Empty string MUST NOT equal null in canonical form.",
     "input_a": {"x": ""}, "input_b": {"x": None},
     "expected_outcome": "DISTINGUISHABLE"},

    {"id": "V010", "category": "absent_vs_null",
     "description": "Absent field MUST NOT equal explicit null in canonical form.",
     "input_a": {}, "input_b": {"x": None},
     "expected_outcome": "DISTINGUISHABLE"},

    {"id": "V011", "category": "whitespace_policy",
     "description": "Canonical form MUST contain no whitespace between tokens (RFC 8785 + separators).",
     "input_decoded": {"a": 1, "b": [2, 3]},
     "expected_canonical_output": '{"a":1,"b":[2,3]}',
     "expected_outcome": "ACCEPT_NO_WHITESPACE"},

    {"id": "V012", "category": "cyrillic_lookalike",
     "description": "Cyrillic Er (U+0420) where Latin P (U+0050) expected in compact enum code MUST be REJECTED (already AEP60_COMPACT_ENUM_NON_ASCII).",
     "input_hex": "7b227265 6c696162 696c6974 79223a22 d0a0227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP60_COMPACT_ENUM_NON_ASCII"},

    {"id": "V013", "category": "greek_lookalike",
     "description": "Greek Capital Pi (U+03A0) where Latin P expected MUST be REJECTED.",
     "input_hex": "7b227265 6c696162 696c6974 79223a22 ce a0 227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP60_COMPACT_ENUM_NON_ASCII"},

    {"id": "V014", "category": "math_bold_lookalike",
     "description": "Mathematical Bold Capital P (U+1D40F) MUST be REJECTED in enum code position.",
     "input_hex": "7b227265 6c696162 696c6974 79223a22 f09d908f 227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP60_COMPACT_ENUM_NON_ASCII"},

    {"id": "V015", "category": "fullwidth_lookalike",
     "description": "Fullwidth Latin Capital P (U+FF30) MUST be REJECTED in enum code position.",
     "input_hex": "7b227265 6c696162 696c6974 79223a22 efbcb0 227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP60_COMPACT_ENUM_NON_ASCII"},

    {"id": "V016", "category": "escape_canonicalization_quote",
     "description": "Quoted strings in canonical form MUST use \\\" escape, NOT \\u0022.",
     "input_decoded": {"x": 'a"b'},
     "expected_canonical_output": '{"x":"a\\"b"}',
     "expected_outcome": "ACCEPT_CANONICAL_ESCAPE"},

    {"id": "V017", "category": "escape_canonicalization_backslash",
     "description": "Backslash MUST be escaped as \\\\, NOT \\u005c.",
     "input_decoded": {"x": "a\\b"},
     "expected_canonical_output": '{"x":"a\\\\b"}',
     "expected_outcome": "ACCEPT_CANONICAL_ESCAPE"},

    {"id": "V018", "category": "escape_canonicalization_control",
     "description": "Control characters U+0001..U+001F (except specials \\b \\f \\n \\r \\t) MUST use \\u00XX form.",
     "input_decoded_hex": {"x_hex": "01"},
     "expected_canonical_output": '{"x":"\\u0001"}',
     "expected_outcome": "ACCEPT_CANONICAL_ESCAPE"},

    {"id": "V019", "category": "escape_canonicalization_newline",
     "description": "Newline U+000A MUST be \\n, NOT \\u000a.",
     "input_decoded": {"x": "\n"},
     "expected_canonical_output": '{"x":"\\n"}',
     "expected_outcome": "ACCEPT_CANONICAL_ESCAPE"},

    {"id": "V020", "category": "escape_canonicalization_tab",
     "description": "Tab U+0009 MUST be \\t.",
     "input_decoded": {"x": "\t"},
     "expected_canonical_output": '{"x":"\\t"}',
     "expected_outcome": "ACCEPT_CANONICAL_ESCAPE"},

    {"id": "V021", "category": "high_unicode_preserved",
     "description": "BMP characters above U+007F MUST be preserved literally (ensure_ascii=False).",
     "input_decoded": {"x": "中文"},
     "expected_canonical_output": '{"x":"中文"}',
     "expected_outcome": "ACCEPT_LITERAL"},

    {"id": "V022", "category": "surrogate_pair_preserved",
     "description": "Astral plane characters (U+10000+) MUST be preserved as literal UTF-8 bytes.",
     "input_decoded": {"x": "\U0001f525"},
     "expected_canonical_output": '{"x":"\U0001f525"}',
     "expected_outcome": "ACCEPT_LITERAL"},

    {"id": "V023", "category": "nested_empty_array",
     "description": "Empty array MUST be [] without internal whitespace.",
     "input_decoded": {"x": []},
     "expected_canonical_output": '{"x":[]}',
     "expected_outcome": "ACCEPT"},

    {"id": "V024", "category": "nested_empty_object",
     "description": "Empty object MUST be {} without internal whitespace.",
     "input_decoded": {"x": {}},
     "expected_canonical_output": '{"x":{}}',
     "expected_outcome": "ACCEPT"},

    {"id": "V025", "category": "deeply_nested",
     "description": "Deeply nested objects MUST canonicalize without depth-related drift.",
     "input_decoded": {"a": {"b": {"c": {"d": 1}}}},
     "expected_canonical_output": '{"a":{"b":{"c":{"d":1}}}}',
     "expected_outcome": "ACCEPT"},

    {"id": "V026", "category": "trailing_newline",
     "description": "Canonical JSONL file MUST end with exactly one LF; no CRLF; no extra trailing whitespace.",
     "input_lines": ['{"a":1}', '{"a":2}'],
     "expected_file_bytes": '{"a":1}\n{"a":2}\n',
     "expected_outcome": "ACCEPT_TRAILING_LF"},

    {"id": "V027", "category": "no_crlf",
     "description": "CRLF line endings MUST be rejected or normalized; canonical is LF-only.",
     "input_raw_hex": "7b2261223a317d 0d0a 7b2261223a327d 0d0a",
     "expected_outcome": "REJECT_OR_NORMALIZE", "expected_reason": "AEP70_LINE_ENDING_NOT_LF"},

    {"id": "V028", "category": "leading_zero_integer",
     "description": "Integers MUST NOT have leading zeros (except 0 itself).",
     "input_raw": '{"x":007}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_LEADING_ZERO"},

    {"id": "V029", "category": "positive_sign_integer",
     "description": "Integers MUST NOT have leading + sign.",
     "input_raw": '{"x":+5}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_POSITIVE_SIGN"},

    {"id": "V030", "category": "negative_zero",
     "description": "Negative zero MUST canonicalize to 0 (per AEP-NUMERIC-v1).",
     "input_decoded": {"x": -0.0},
     "expected_canonical_output": '{"x":0}',
     "expected_outcome": "ACCEPT_NORMALIZED_TO_ZERO"},

    {"id": "V031", "category": "trailing_decimal_point",
     "description": "Numbers MUST NOT end with decimal point alone (e.g., '5.').",
     "input_raw": '{"x":5.}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_TRAILING_DECIMAL"},

    {"id": "V032", "category": "leading_decimal_point",
     "description": "Numbers MUST NOT start with decimal point alone (e.g., '.5').",
     "input_raw": '{"x":.5}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_NUMERIC_LEADING_DECIMAL"},

    {"id": "V033", "category": "scientific_lowercase_e",
     "description": "Scientific notation MUST use lowercase 'e' canonical form.",
     "input_decoded": {"x": 1.5e10},
     "expected_canonical_output_pattern": "lowercase_e",
     "expected_outcome": "ACCEPT_LOWERCASE_E"},

    {"id": "V034", "category": "duplicate_keys_nested",
     "description": "Duplicate keys at any nesting depth MUST be rejected.",
     "input_raw": '{"x":{"a":1,"a":2}}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_DUPLICATE_KEY"},

    {"id": "V035", "category": "zero_width_space",
     "description": "Zero-width-space U+200B in enum code position MUST be REJECTED.",
     "input_hex": "7b227265 6c696162 696c6974 79223a22 50 e2808b 227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP60_COMPACT_ENUM_NON_ASCII"},

    {"id": "V036", "category": "rtl_override",
     "description": "Right-to-left override U+202E in any position MUST be REJECTED.",
     "input_hex": "7b2278223a22 61 e280ae 62 227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP70_BIDI_OVERRIDE_FORBIDDEN"},

    {"id": "V037", "category": "byte_order_mark",
     "description": "UTF-8 BOM at start of canonical JSONL file MUST be REJECTED.",
     "input_hex": "efbbbf 7b2261223a317d",
     "expected_outcome": "REJECT", "expected_reason": "AEP70_BOM_FORBIDDEN"},

    {"id": "V038", "category": "key_with_unicode_lookalike",
     "description": "Object key containing Cyrillic Er where Latin P expected MUST be REJECTED for enum-position keys.",
     "input_hex": "7b22 d180 656c69 6162696c697479 223a 22 50524f56454e5f52454c4941424c45 22 7d",
     "expected_outcome": "REJECT_OR_FLAG", "expected_reason": "AEP70_KEY_UNICODE_LOOKALIKE"},

    {"id": "V039", "category": "unicode_combiner_in_enum",
     "description": "Combining diacritic U+0301 attached to enum code letter MUST be REJECTED.",
     "input_hex": "7b227265 6c696162 696c6974 79223a22 50 cc81 227d",
     "expected_outcome": "REJECT", "expected_reason": "AEP60_COMPACT_ENUM_NON_ASCII"},

    {"id": "V040", "category": "tab_in_string",
     "description": "Literal tab character in string MUST be escaped as \\t, NOT preserved raw.",
     "input_decoded": {"x": "a\tb"},
     "expected_canonical_output": '{"x":"a\\tb"}',
     "expected_outcome": "ACCEPT_ESCAPED"},

    {"id": "V041", "category": "vertical_tab_in_string",
     "description": "Vertical tab U+000B in string MUST be escaped as \\u000b.",
     "input_decoded_hex": {"x_hex": "61 0b 62"},
     "expected_canonical_output": '{"x":"a\\u000bb"}',
     "expected_outcome": "ACCEPT_ESCAPED"},

    {"id": "V042", "category": "form_feed_in_string",
     "description": "Form feed U+000C MUST be escaped as \\f.",
     "input_decoded_hex": {"x_hex": "61 0c 62"},
     "expected_canonical_output": '{"x":"a\\fb"}',
     "expected_outcome": "ACCEPT_ESCAPED"},

    {"id": "V043", "category": "null_value_preserved",
     "description": "null value MUST be preserved as canonical null token.",
     "input_decoded": {"x": None},
     "expected_canonical_output": '{"x":null}',
     "expected_outcome": "ACCEPT"},

    {"id": "V044", "category": "boolean_true",
     "description": "true boolean MUST be canonical token.",
     "input_decoded": {"x": True},
     "expected_canonical_output": '{"x":true}',
     "expected_outcome": "ACCEPT"},

    {"id": "V045", "category": "boolean_false",
     "description": "false boolean MUST be canonical token.",
     "input_decoded": {"x": False},
     "expected_canonical_output": '{"x":false}',
     "expected_outcome": "ACCEPT"},

    {"id": "V046", "category": "array_with_mixed_types",
     "description": "Heterogeneous arrays MUST canonicalize element-by-element with separators.",
     "input_decoded": {"x": [1, "a", None, True, {}]},
     "expected_canonical_output": '{"x":[1,"a",null,true,{}]}',
     "expected_outcome": "ACCEPT"},

    {"id": "V047", "category": "single_quote_string",
     "description": "Single-quoted string literal MUST be REJECTED (JSON requires double quotes).",
     "input_raw": "{'a':1}",
     "expected_outcome": "REJECT", "expected_reason": "AEP70_INVALID_JSON_SYNTAX"},

    {"id": "V048", "category": "trailing_comma_object",
     "description": "Trailing comma in object MUST be REJECTED.",
     "input_raw": '{"a":1,}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_INVALID_JSON_SYNTAX"},

    {"id": "V049", "category": "trailing_comma_array",
     "description": "Trailing comma in array MUST be REJECTED.",
     "input_raw": "[1,2,]",
     "expected_outcome": "REJECT", "expected_reason": "AEP70_INVALID_JSON_SYNTAX"},

    {"id": "V050", "category": "comment_forbidden",
     "description": "JSON5/JS-style comments MUST be REJECTED.",
     "input_raw": '{"a":1 /* comment */}',
     "expected_outcome": "REJECT", "expected_reason": "AEP70_INVALID_JSON_SYNTAX"},

    {"id": "V051", "category": "extremely_long_string",
     "description": "Long-string (1 MiB) MUST canonicalize without precision loss or memory blow-up.",
     "input_decoded_size_hint": 1048576,
     "expected_outcome": "ACCEPT_NO_TRUNCATION"},

    {"id": "V052", "category": "many_keys",
     "description": "Object with 10K keys MUST sort deterministically by UTF-16 in O(n log n).",
     "input_key_count": 10000,
     "expected_outcome": "ACCEPT_SORTED_DETERMINISTIC"},
]


def main():
    corpus = {
        "schema": "aep.canonical_surface_vectors.v1",
        "spec_version": "0.7-rc1",
        "description": (
            "JCS edge-vector test corpus (SP-R8-04). Covers canonical surface "
            "beyond AEP-NUMERIC-v1. Vectors test: duplicate-key rejection, "
            "large-integer-as-string encoding, NaN/Infinity rejection, "
            "UTF-16 property sorting, NFC/NFD normalization discipline, "
            "empty-string-vs-null distinction, whitespace policy, "
            "Unicode-lookalike enum-code rejection, escape-sequence "
            "canonicalization, nested-empty disambiguation, "
            "trailing-newline policy, BOM/RTL/bidi-override rejection, "
            "and synthetic stress tests (1MiB strings, 10K keys)."
        ),
        "vector_count": len(VECTORS),
        "vectors": VECTORS,
    }
    out = Path(__file__).resolve().parents[1] / "test_vectors" / "v0_7" / "A.11-canonical-surface" / "vectors.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(corpus, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"Wrote {out}: {len(VECTORS)} vectors")


if __name__ == "__main__":
    main()
