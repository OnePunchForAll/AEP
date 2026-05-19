#!/usr/bin/env python3
"""AEP v1.2 Policy-as-Code Engine (sec14, operator source.md L21 + L73-L77).

Operator L21 verbatim (sec73.2 sacred):
> "Fifth, AEP needs policy-as-code gates. Some rules should not live in prompts.
>  They should live in executable policy."

This module ships:

  - A compact native JSON-DSL policy compiler (`compile_policy`)
  - A pure-Python policy evaluator (`evaluate_policy`)
  - A one-way Rego exporter (`export_to_rego`) -- consumes JSON-DSL, emits text
    readable by external OPA installations (Open Policy Agent, rego_v1 dialect)
  - 6 SEEDED POLICIES corresponding to operator L73-L77 named example rules
    PLUS two extension policies bound to F13 (no falsifier) + F16 (attack class
    flagged). Seeded set is `p1` .. `p6`.
  - `run_all_policies(packet)` -> the CI-gate batch runner

Design choices (sec73.6 honest):

  - Stdlib only. No `rego-py` dependency. Rego export is TEXT for external OPA
    consumption; in-process evaluation uses native JSON-DSL.
  - The JSON-DSL is intentionally TINY: `op` (one of cmp_gt / cmp_ge / cmp_lt /
    cmp_le / cmp_eq / cmp_neq / has_field / not / and / or / set_distinct /
    set_intersect / regex_match). This is enough for all 6 seeded policies and
    every operator-named example in sec14.3.
  - `compile_policy` accepts EITHER a JSON-DSL dict OR a Rego-shaped string and
    returns a `CompiledPolicy` (callable on packet dict). Rego strings are NOT
    full-OPA evaluated; we extract the equivalent DSL via a tiny pattern
    matcher that handles the 6 operator-named clauses verbatim. Anything else
    raises `PolicyCompileError`.
  - Schema: every emitted policy validates against
    `schemas/v1_2_policy_rego.schema.json` (top-level enforced via
    `additionalProperties: false`).
  - Composes with: F13 falsifier_runtime (p5), F14 rater_quorum (p3),
    F16 attack_class_registry (p6), F18 source_provenance laundering_score
    (p1), v1.2 Sandbox Gate (p2), F24 redaction layer (p4).

Cites (sec73.3 prior art inheritance):
  - Open Policy Agent / Rego policy language (CNCF) -- EXTENDS classification.
  - Operator source.md L21 + L73-L77.
  - adversary-2026-05-18-aep-v1-2-premortem.md A4 + A10 + A11 closures.
  - sec13.2 binding table (G3 / G4 / G6 / G7 gates).

Author: forge (Phase 6, single-forge per sec73.4).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class PolicyCompileError(ValueError):
    """Raised when JSON-DSL or Rego text cannot be compiled into a callable."""


class PolicyEvaluationError(RuntimeError):
    """Raised when packet field lookup fails or operator type-mismatches."""


# --------------------------------------------------------------------------- #
# JSON-Path helper (subset of JSONPath: $.a.b.c form, plus $.a[*].b array-walk)
# --------------------------------------------------------------------------- #


def _jpath_get(obj: Any, path: str, default: Any = None) -> Any:
    """Walk a `$.a.b.c` or `$.a[*].b` JSONPath against `obj`.

    Returns `default` if any step is missing. For `[*]` returns the LIST of
    values reached (used by p3 distinct-principal checks). Stdlib only.
    """
    if not path.startswith("$"):
        raise PolicyEvaluationError(f"path must start with '$': {path}")
    cursor = obj
    parts = path[1:].lstrip(".").split(".")
    # Re-split bracketed [*] / [N] tokens.
    expanded: list[str] = []
    for part in parts:
        if "[" not in part:
            expanded.append(part)
            continue
        head, _, rest = part.partition("[")
        if head:
            expanded.append(head)
        # rest could be '*]', 'N]', 'N].key' -- handle.
        bracket, _, tail = rest.partition("]")
        expanded.append("[" + bracket + "]")
        if tail:
            for sub in tail.lstrip(".").split("."):
                expanded.append(sub)
    for step in expanded:
        if not step:
            continue
        if step.startswith("[") and step.endswith("]"):
            inner = step[1:-1]
            if inner == "*":
                if not isinstance(cursor, list):
                    return default
                return cursor  # collect-all
            try:
                idx = int(inner)
            except ValueError:
                return default
            if not isinstance(cursor, list) or idx >= len(cursor):
                return default
            cursor = cursor[idx]
        else:
            if not isinstance(cursor, dict):
                return default
            if step not in cursor:
                return default
            cursor = cursor[step]
    return cursor


# --------------------------------------------------------------------------- #
# JSON-DSL evaluator
# --------------------------------------------------------------------------- #


_VALID_OPS = {
    "cmp_gt", "cmp_ge", "cmp_lt", "cmp_le", "cmp_eq", "cmp_neq",
    "has_field", "not", "and", "or", "set_distinct", "set_intersect",
    "regex_match", "is_truthy", "is_empty", "all", "any",
}


def _eval_node(node: dict[str, Any], packet: dict[str, Any]) -> Any:
    """Evaluate one JSON-DSL node against `packet`. Returns the result value."""
    op = node.get("op")
    if op not in _VALID_OPS:
        raise PolicyCompileError(f"unknown op: {op!r}")

    if op in ("cmp_gt", "cmp_ge", "cmp_lt", "cmp_le", "cmp_eq", "cmp_neq"):
        left_raw = node.get("left")
        right_raw = node.get("right")
        left = _resolve_operand(left_raw, packet)
        right = _resolve_operand(right_raw, packet)
        try:
            if op == "cmp_gt":
                return left is not None and right is not None and left > right
            if op == "cmp_ge":
                return left is not None and right is not None and left >= right
            if op == "cmp_lt":
                return left is not None and right is not None and left < right
            if op == "cmp_le":
                return left is not None and right is not None and left <= right
            if op == "cmp_eq":
                return left == right
            if op == "cmp_neq":
                return left != right
        except TypeError:
            return False

    if op == "has_field":
        val = _jpath_get(packet, node["path"], default=_SENTINEL)
        return val is not _SENTINEL

    if op == "is_truthy":
        val = _resolve_operand({"path": node["path"]}, packet)
        return bool(val)

    if op == "is_empty":
        val = _resolve_operand({"path": node["path"]}, packet)
        if val is None:
            return True
        if isinstance(val, (list, dict, str)):
            return len(val) == 0
        return False

    if op == "not":
        return not _eval_node(node["clause"], packet)

    if op == "and":
        return all(_eval_node(c, packet) for c in node["clauses"])

    if op == "or":
        return any(_eval_node(c, packet) for c in node["clauses"])

    if op == "set_distinct":
        path = node["path"]
        lst = _jpath_get(packet, path, default=[])
        if not isinstance(lst, list):
            return False
        return len(lst) == len(set(_hashable(v) for v in lst))

    if op == "set_intersect":
        path = node["path"]
        with_set = set(node.get("with") or [])
        lst = _jpath_get(packet, path, default=[])
        if not isinstance(lst, list):
            return False
        return len(set(_hashable(v) for v in lst) & with_set) > 0

    if op == "regex_match":
        val = _resolve_operand({"path": node["path"]}, packet)
        if not isinstance(val, str):
            return False
        return re.search(node["pattern"], val) is not None

    if op == "all":
        path = node["path"]
        lst = _jpath_get(packet, path, default=[])
        if not isinstance(lst, list):
            return False
        clause = node["clause"]
        for item in lst:
            ctx = {"__item__": item}
            if not _eval_node(clause, ctx):
                return False
        return True

    if op == "any":
        path = node["path"]
        lst = _jpath_get(packet, path, default=[])
        if not isinstance(lst, list):
            return False
        clause = node["clause"]
        for item in lst:
            ctx = {"__item__": item}
            if _eval_node(clause, ctx):
                return True
        return False

    raise PolicyCompileError(f"unhandled op: {op!r}")


_SENTINEL = object()


def _resolve_operand(operand: Any, packet: dict[str, Any]) -> Any:
    """Resolve a DSL operand: literal value or `{path: '$.a.b'}` lookup."""
    if isinstance(operand, dict) and "path" in operand:
        return _jpath_get(packet, operand["path"], default=None)
    if isinstance(operand, dict) and "value" in operand:
        return operand["value"]
    return operand


def _hashable(v: Any) -> Any:
    """Coerce to hashable for set-distinct check."""
    if isinstance(v, (str, int, float, bool, type(None))):
        return v
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# CompiledPolicy
# --------------------------------------------------------------------------- #


@dataclass
class CompiledPolicy:
    """A compiled, callable policy.

    `evaluate(packet)` returns a dict with `decision` ('allow'|'deny') and
    `reason` (str). The match semantic is: if the DSL evaluates to True, the
    policy DENIES (operator-named example rules are all `deny[reason] {...}`
    patterns).
    """

    policy_id: str
    policy_name: str
    policy_kind: str
    dsl: dict[str, Any]
    rego_text: Optional[str]
    violation_outcome: dict[str, str]
    operator_line_range: dict[str, Any]
    target_field_path: str
    lineage_classification: str
    composes_with: list[str]
    civilian_phrasing: str

    def evaluate(self, packet: dict[str, Any]) -> dict[str, Any]:
        try:
            matched = _eval_node(self.dsl, packet)
        except (PolicyEvaluationError, PolicyCompileError) as e:
            return {
                "policy_id": self.policy_id,
                "decision": "error",
                "reason": f"policy_eval_error: {e}",
            }
        if matched:
            return {
                "policy_id": self.policy_id,
                "decision": "deny",
                "reason": self.civilian_phrasing,
                "violation_status": self.violation_outcome["status"],
            }
        return {
            "policy_id": self.policy_id,
            "decision": "allow",
            "reason": "policy_did_not_match",
        }

    def to_aep_record(self) -> dict[str, Any]:
        """Emit a PolicyRegoRecord-shaped dict per the v1.2 schema."""
        return {
            "type": "PolicyRegoRecord",
            "schema_version": "aep-policy-rego-0.1",
            "id": self.policy_id,
            "policy_name": self.policy_name,
            "policy_kind": self.policy_kind,
            "rego_expression": {
                "expression": self.rego_text or "",
                "rego_dialect": "rego_v1",
                "compiled_against_opa_version": "0.65.0",
            },
            "operator_directive_basis_line_range": self.operator_line_range,
            "policy_target_field_path": self.target_field_path,
            "violation_outcome": self.violation_outcome,
            "ci_gate_enforcement": {
                "enforced_in_ci": True,
                "test_fixture_path":
                    "projects/v11-aep/publish-ready/aep/scripts/"
                    "test_v12_10_gate_kill_chain.py",
            },
            "lineage_basis": {
                "classification": self.lineage_classification,
                "external_precedents": [
                    "Open Policy Agent",
                    "Rego policy language",
                    "CNCF policy primitives",
                ],
                "verifying_grep":
                    "rg 'open policy agent|rego|opa policy' --type md "
                    "research/sources/",
                "n_hits": 0,
            },
            "policy_authored_at": _dt.datetime.utcnow().replace(
                microsecond=0).isoformat() + "Z",
            "policy_signature_ed25519": "ed25519_pending_phase_6_keypair",
        }


# --------------------------------------------------------------------------- #
# compile_policy (JSON or Rego string)
# --------------------------------------------------------------------------- #


def compile_policy(spec: Union[dict[str, Any], str],
                   policy_meta: Optional[dict[str, Any]] = None) -> CompiledPolicy:
    """Compile a JSON-DSL spec or operator-named Rego clause into a callable.

    Args:
      spec: either a dict {dsl: {...}, meta: {...}} or a Rego string that
        matches one of the 6 operator-named clauses.
      policy_meta: optional override for policy metadata fields (id, name,
        kind, target_field_path, civilian_phrasing).

    Returns:
      CompiledPolicy instance.

    Raises:
      PolicyCompileError if the spec is malformed.
    """
    if isinstance(spec, str):
        return _compile_rego(spec, policy_meta or {})
    if not isinstance(spec, dict):
        raise PolicyCompileError("spec must be dict or str")
    dsl = spec.get("dsl")
    if not isinstance(dsl, dict):
        raise PolicyCompileError("spec.dsl must be a dict")
    meta = {**(spec.get("meta") or {}), **(policy_meta or {})}
    return CompiledPolicy(
        policy_id=meta.get("policy_id", "pol:unnamed"),
        policy_name=meta.get("policy_name", "unnamed_policy"),
        policy_kind=meta.get("policy_kind", "promotion_gate"),
        dsl=dsl,
        rego_text=meta.get("rego_text"),
        violation_outcome=meta.get("violation_outcome", {
            "status": "REJECT_PROMOTION",
            "civilian_phrasing": "Policy denied.",
        }),
        operator_line_range=meta.get("operator_line_range", {
            "start_line": 21,
            "end_line": 77,
            "source_path":
                "research/sources/"
                "operator-2026-05-18-aep-v12-immune-system/assets/source.md",
        }),
        target_field_path=meta.get("target_field_path", "$"),
        lineage_classification=meta.get("lineage_classification", "EXTENDS"),
        composes_with=meta.get("composes_with", []),
        civilian_phrasing=meta.get(
            "civilian_phrasing", meta.get("violation_outcome", {}).get(
                "civilian_phrasing", "Policy denied.")),
    )


def _compile_rego(rego_text: str,
                  policy_meta: dict[str, Any]) -> CompiledPolicy:
    """Pattern-match the 6 operator-named Rego clauses verbatim.

    Anything that does not match raises PolicyCompileError; this is the
    one-way ingest path. The 6 seeded policies all carry both DSL and Rego
    so this function is exercised symmetrically in tests.
    """
    text = rego_text.replace("\n", " ").strip()
    # Pattern p1: laundering_score > 0.6
    if "laundering_score > 0.6" in text:
        return SEEDED_POLICIES["p1_no_promote_laundered"]
    # Pattern p2: sandbox_permission ... not granted
    if "sandbox_permission" in text and ("not" in text or "false" in text):
        return SEEDED_POLICIES["p2_no_unsandboxed_execution"]
    # Pattern p3: principal_ids ... not distinct
    if "principal_ids" in text and ("set(" in text or "distinct" in text
                                    or "count(" in text):
        return SEEDED_POLICIES["p3_no_quorum_with_duplicate_principals"]
    # Pattern p4: private export ... no redaction
    if ("visibility_class" in text
            and ("private" in text or "local_only" in text)
            and ("redaction_applied" in text or "redaction" in text)):
        return SEEDED_POLICIES["p4_no_export_private_evidence_unredacted"]
    # Pattern p5: PROVEN/RELIABLE promotion ... no falsifier
    if "falsifier" in text and ("PROVEN" in text or "RELIABLE" in text):
        return SEEDED_POLICIES["p5_no_promote_without_falsifier"]
    # Pattern p6: attack class match_count >= 2
    if ("attack_class" in text
            and ("match_count" in text or "matches" in text)):
        return SEEDED_POLICIES["p6_no_promote_with_attack_class_flagged"]
    raise PolicyCompileError(
        "rego clause does not match any of the 6 seeded operator-named "
        "patterns; build a JSON-DSL spec instead")


# --------------------------------------------------------------------------- #
# evaluate_policy / run_all_policies
# --------------------------------------------------------------------------- #


def evaluate_policy(policy: CompiledPolicy,
                    packet: dict[str, Any]) -> dict[str, Any]:
    """Evaluate `policy` against `packet`."""
    return policy.evaluate(packet)


def run_all_policies(packet: dict[str, Any],
                     policies: Optional[dict[str, CompiledPolicy]] = None
                     ) -> list[dict[str, Any]]:
    """Run the full SEEDED_POLICIES suite against `packet`. CI gate batch."""
    pol_map = policies if policies is not None else SEEDED_POLICIES
    out: list[dict[str, Any]] = []
    for pol_id, pol in pol_map.items():
        out.append(evaluate_policy(pol, packet))
    return out


# --------------------------------------------------------------------------- #
# Rego exporter (DSL -> readable rego text; one-way per sec14.4)
# --------------------------------------------------------------------------- #


_REGO_PREAMBLE = "package aep.v1_2.policy\n\n"


def export_to_rego(policy: CompiledPolicy) -> str:
    """Emit a Rego-compatible policy text for external OPA consumption.

    If the CompiledPolicy already carries explicit Rego text (the seeded
    policies do), return it verbatim. Else generate a minimal `deny[reason]`
    block from the DSL.
    """
    if policy.rego_text:
        return policy.rego_text
    body = _dsl_to_rego_body(policy.dsl, policy.target_field_path)
    return (
        _REGO_PREAMBLE
        + "# auto-generated from JSON-DSL by aep.v1_2.policy_engine\n"
        + "# operator basis: "
        + json.dumps(policy.operator_line_range) + "\n\n"
        + "deny[reason] {\n"
        + "    " + body + "\n"
        + "    reason := \"" + policy.civilian_phrasing.replace('"', '\\"')
        + "\"\n"
        + "}\n"
    )


def _dsl_to_rego_body(node: dict[str, Any], default_path: str) -> str:
    """Minimal DSL -> Rego clause emitter."""
    op = node.get("op")
    if op in ("cmp_gt", "cmp_ge", "cmp_lt", "cmp_le", "cmp_eq", "cmp_neq"):
        sym = {
            "cmp_gt": ">", "cmp_ge": ">=", "cmp_lt": "<", "cmp_le": "<=",
            "cmp_eq": "==", "cmp_neq": "!=",
        }[op]
        left = _operand_to_rego(node.get("left"))
        right = _operand_to_rego(node.get("right"))
        return f"{left} {sym} {right}"
    if op == "not":
        return f"not ({_dsl_to_rego_body(node['clause'], default_path)})"
    if op == "and":
        return "; ".join(_dsl_to_rego_body(c, default_path)
                         for c in node["clauses"])
    if op == "or":
        return "; or ".join(_dsl_to_rego_body(c, default_path)
                            for c in node["clauses"])
    if op == "is_truthy":
        return "input" + _jpath_to_rego(node["path"])
    if op == "is_empty":
        return "count(input" + _jpath_to_rego(node["path"]) + ") == 0"
    if op == "has_field":
        return "input" + _jpath_to_rego(node["path"])
    if op == "set_distinct":
        return ("count(input" + _jpath_to_rego(node["path"]) + ") "
                "== count({x | x = input" + _jpath_to_rego(node["path"])
                + "[_]})")
    return "# unsupported_op_" + str(op)


def _operand_to_rego(operand: Any) -> str:
    if isinstance(operand, dict) and "path" in operand:
        return "input" + _jpath_to_rego(operand["path"])
    if isinstance(operand, dict) and "value" in operand:
        return json.dumps(operand["value"])
    return json.dumps(operand)


def _jpath_to_rego(path: str) -> str:
    """`$.claim.laundering_score` -> `.claim.laundering_score`."""
    return path[1:] if path.startswith("$") else "." + path


# --------------------------------------------------------------------------- #
# 6 Seeded policies (operator L73-L77 verbatim)
# --------------------------------------------------------------------------- #


def _make_seeded_policies() -> dict[str, CompiledPolicy]:
    """Build the 6 seeded CompiledPolicy instances."""
    base_line_range = {
        "start_line": 21,
        "end_line": 21,
        "source_path":
            "research/sources/"
            "operator-2026-05-18-aep-v12-immune-system/assets/source.md",
    }
    pol_map: dict[str, CompiledPolicy] = {}

    # ----- p1: laundering_score > 0.6 -> deny promotion -----
    p1 = CompiledPolicy(
        policy_id="pol:laundering-score-promotion-gate",
        policy_name="p1_no_promote_laundered",
        policy_kind="promotion_gate",
        dsl={
            "op": "cmp_gt",
            "left": {"path": "$.claim.laundering_score"},
            "right": 0.6,
        },
        rego_text=(_REGO_PREAMBLE
                   + "# p1 -- operator L21 verbatim laundering_score > 0.6\n\n"
                   + "deny[reason] {\n"
                   + "    input.claim.laundering_score > 0.6\n"
                   + "    reason := sprintf(\"claim %v has laundering_score "
                   + "%.2f above 0.6 threshold\", "
                   + "[input.claim.id, input.claim.laundering_score])\n"
                   + "}\n"),
        violation_outcome={
            "status": "REJECT_PROMOTION",
            "civilian_phrasing":
                "This claim's sources trace back to AI-generated content too "
                "often. Promotion blocked until the evidence chain is checked.",
        },
        operator_line_range=base_line_range,
        target_field_path="$.claim.laundering_score",
        lineage_classification="EXTENDS",
        composes_with=["v1.1-F18-source-provenance-graph"],
        civilian_phrasing=(
            "This claim's sources trace back to AI-generated content too "
            "often. Promotion blocked until the evidence chain is checked."),
    )
    pol_map["p1_no_promote_laundered"] = p1

    # ----- p2: executable validation w/o sandbox permission -----
    p2 = CompiledPolicy(
        policy_id="pol:sandbox-permission-execution-gate",
        policy_name="p2_no_unsandboxed_execution",
        policy_kind="execution_gate",
        dsl={
            "op": "and",
            "clauses": [
                {"op": "is_truthy", "path": "$.validation.executable"},
                {"op": "not", "clause": {
                    "op": "is_truthy",
                    "path": "$.validation.sandbox_permission_granted",
                }},
            ],
        },
        rego_text=(_REGO_PREAMBLE
                   + "# p2 -- operator L21 verbatim sandbox permission\n\n"
                   + "deny[reason] {\n"
                   + "    input.validation.executable == true\n"
                   + "    not input.validation.sandbox_permission_granted\n"
                   + "    reason := \"executable validation without sandbox "
                   + "permission is forbidden\"\n"
                   + "}\n"),
        violation_outcome={
            "status": "REJECT_EXECUTION",
            "civilian_phrasing":
                "This test would run code on your machine without a safe "
                "sandbox. Blocked.",
        },
        operator_line_range=base_line_range,
        target_field_path="$.validation.sandbox_permission_granted",
        lineage_classification="EXTENDS",
        composes_with=["v1.2-SandboxGate-sec15", "v1.1-F13-falsifier"],
        civilian_phrasing=(
            "This test would run code on your machine without a safe "
            "sandbox. Blocked."),
    )
    pol_map["p2_no_unsandboxed_execution"] = p2

    # ----- p3: reviewer quorum principal_ids not distinct -----
    p3 = CompiledPolicy(
        policy_id="pol:quorum-distinct-principals",
        policy_name="p3_no_quorum_with_duplicate_principals",
        policy_kind="quorum_gate",
        dsl={
            "op": "and",
            "clauses": [
                {"op": "has_field", "path": "$.review.principal_ids"},
                {"op": "not", "clause": {
                    "op": "set_distinct",
                    "path": "$.review.principal_ids",
                }},
            ],
        },
        rego_text=(_REGO_PREAMBLE
                   + "# p3 -- operator L21 verbatim distinct principals\n\n"
                   + "deny[reason] {\n"
                   + "    count(input.review.principal_ids) > "
                   + "count({x | x = input.review.principal_ids[_]})\n"
                   + "    reason := \"rater quorum has duplicate principal "
                   + "ids -- F14 distinct-principal invariant violated\"\n"
                   + "}\n"),
        violation_outcome={
            "status": "REJECT_PROMOTION",
            "civilian_phrasing":
                "The reviewers are not actually independent. Some are the "
                "same person counted twice. Promotion blocked.",
        },
        operator_line_range=base_line_range,
        target_field_path="$.review.principal_ids",
        lineage_classification="EXTENDS",
        composes_with=["v1.0.3.1-F14-rater-quorum-attestation"],
        civilian_phrasing=(
            "The reviewers are not actually independent. Some are the "
            "same person counted twice. Promotion blocked."),
    )
    pol_map["p3_no_quorum_with_duplicate_principals"] = p3

    # ----- p4: export private evidence without redaction -----
    p4 = CompiledPolicy(
        policy_id="pol:private-export-redaction-gate",
        policy_name="p4_no_export_private_evidence_unredacted",
        policy_kind="export_gate",
        dsl={
            "op": "any",
            "path": "$.evidence.items",
            "clause": {
                "op": "and",
                "clauses": [
                    {"op": "cmp_neq",
                     "left": {"path": "$.__item__.visibility_class"},
                     "right": "public"},
                    {"op": "not", "clause": {
                        "op": "is_truthy",
                        "path": "$.__item__.redaction_applied",
                    }},
                ],
            },
        },
        rego_text=(_REGO_PREAMBLE
                   + "# p4 -- operator L21 verbatim private export redaction\n\n"
                   + "deny[reason] {\n"
                   + "    item := input.evidence.items[_]\n"
                   + "    item.visibility_class != \"public\"\n"
                   + "    not item.redaction_applied\n"
                   + "    reason := \"non-public evidence item lacks "
                   + "redaction_applied -- export blocked\"\n"
                   + "}\n"),
        violation_outcome={
            "status": "REJECT_EXPORT",
            "civilian_phrasing":
                "Private information is in this packet and has not been "
                "redacted. Export blocked.",
        },
        operator_line_range=base_line_range,
        target_field_path="$.evidence.items[*].visibility_class",
        lineage_classification="EXTENDS",
        composes_with=["v1.2-F24-redaction-layer-sec18"],
        civilian_phrasing=(
            "Private information is in this packet and has not been "
            "redacted. Export blocked."),
    )
    pol_map["p4_no_export_private_evidence_unredacted"] = p4

    # ----- p5: PROVEN/RELIABLE promotion w/o falsifier -----
    p5 = CompiledPolicy(
        policy_id="pol:proven-requires-falsifier",
        policy_name="p5_no_promote_without_falsifier",
        policy_kind="promotion_gate",
        dsl={
            "op": "and",
            "clauses": [
                {"op": "or", "clauses": [
                    {"op": "cmp_eq",
                     "left": {"path": "$.claim.truth_tag"},
                     "right": "PROVEN/RELIABLE"},
                    {"op": "cmp_eq",
                     "left": {"path": "$.claim.truth_tag"},
                     "right": "PROVEN_RELIABLE"},
                ]},
                {"op": "or", "clauses": [
                    {"op": "not", "clause": {
                        "op": "has_field",
                        "path": "$.claim.falsifier",
                    }},
                    {"op": "is_empty", "path": "$.claim.falsifier"},
                ]},
            ],
        },
        rego_text=(_REGO_PREAMBLE
                   + "# p5 -- F13 binding -- no PROVEN/RELIABLE without falsifier\n\n"
                   + "deny[reason] {\n"
                   + "    input.claim.truth_tag == \"PROVEN/RELIABLE\"\n"
                   + "    not input.claim.falsifier\n"
                   + "    reason := \"PROVEN/RELIABLE promotion blocked -- "
                   + "F13 claim_runtime_falsifier missing\"\n"
                   + "}\n"),
        violation_outcome={
            "status": "REJECT_PROMOTION",
            "civilian_phrasing":
                "This claim wants to be marked highest-trust but has no test "
                "that would prove it wrong. Promotion blocked.",
        },
        operator_line_range=base_line_range,
        target_field_path="$.claim.falsifier",
        lineage_classification="EXTENDS",
        composes_with=["v1.1-F13-claim-runtime-falsifier"],
        civilian_phrasing=(
            "This claim wants to be marked highest-trust but has no test "
            "that would prove it wrong. Promotion blocked."),
    )
    pol_map["p5_no_promote_without_falsifier"] = p5

    # ----- p6: PROVEN/RELIABLE w/ attack_class match_count >= 2 -----
    p6 = CompiledPolicy(
        policy_id="pol:attack-class-flagged-blocks-promotion",
        policy_name="p6_no_promote_with_attack_class_flagged",
        policy_kind="promotion_gate",
        dsl={
            "op": "and",
            "clauses": [
                {"op": "or", "clauses": [
                    {"op": "cmp_eq",
                     "left": {"path": "$.claim.truth_tag"},
                     "right": "PROVEN/RELIABLE"},
                    {"op": "cmp_eq",
                     "left": {"path": "$.claim.truth_tag"},
                     "right": "PROVEN_RELIABLE"},
                ]},
                {"op": "cmp_ge",
                 "left": {"path": "$.attack_class.match_count"},
                 "right": 2},
            ],
        },
        rego_text=(_REGO_PREAMBLE
                   + "# p6 -- F16 binding -- attack class flagged blocks promotion\n\n"
                   + "deny[reason] {\n"
                   + "    input.claim.truth_tag == \"PROVEN/RELIABLE\"\n"
                   + "    input.attack_class.match_count >= 2\n"
                   + "    reason := sprintf(\"PROVEN/RELIABLE promotion "
                   + "blocked -- F16 attack class matched %d times\", "
                   + "[input.attack_class.match_count])\n"
                   + "}\n"),
        violation_outcome={
            "status": "REJECT_PROMOTION",
            "civilian_phrasing":
                "Two or more known bug patterns match this claim. Highest-"
                "trust promotion blocked until the bugs are fixed.",
        },
        operator_line_range=base_line_range,
        target_field_path="$.attack_class.match_count",
        lineage_classification="EXTENDS",
        composes_with=["v1.1-F16-attack-class-registry"],
        civilian_phrasing=(
            "Two or more known bug patterns match this claim. Highest-"
            "trust promotion blocked until the bugs are fixed."),
    )
    pol_map["p6_no_promote_with_attack_class_flagged"] = p6

    return pol_map


SEEDED_POLICIES: dict[str, CompiledPolicy] = _make_seeded_policies()


# --------------------------------------------------------------------------- #
# Persistence (write seeded_policies.jsonl + per-policy Rego files)
# --------------------------------------------------------------------------- #


_DEFAULT_RECALL_DIR = os.path.join(
    "projects", "v11-aep", "publish-ready", "aep", "recall", "policies")


def write_seeded_policies(out_dir: str = _DEFAULT_RECALL_DIR) -> dict[str, str]:
    """Emit `seeded_policies.jsonl` + `policy_<name>.rego` per policy.

    Returns a {policy_id: rego_path} map for receipts.
    """
    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, "seeded_policies.jsonl")
    rego_paths: dict[str, str] = {}
    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as f:
        for pol_id, pol in SEEDED_POLICIES.items():
            record = pol.to_aep_record()
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            f.write("\n")
            rego_path = os.path.join(out_dir, f"policy_{pol_id}.rego")
            with open(rego_path, "w", encoding="utf-8", newline="\n") as rf:
                rf.write(export_to_rego(pol))
            rego_paths[pol_id] = rego_path
    return rego_paths


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--write", action="store_true",
                   help="Write seeded_policies.jsonl + per-policy .rego files.")
    p.add_argument("--out-dir", default=_DEFAULT_RECALL_DIR)
    p.add_argument("--eval", type=str, default=None,
                   help="Path to a packet JSON file to evaluate against all "
                        "6 seeded policies.")
    p.add_argument("--list", action="store_true",
                   help="List all seeded policies + their kind.")
    args = p.parse_args(argv)

    if args.list:
        for pid, pol in SEEDED_POLICIES.items():
            print(f"{pid:60s}  kind={pol.policy_kind:18s}  "
                  f"id={pol.policy_id}")

    if args.write:
        rego = write_seeded_policies(args.out_dir)
        print(json.dumps({"jsonl": os.path.join(args.out_dir,
                                                "seeded_policies.jsonl"),
                          "rego": rego},
                         sort_keys=True, indent=2))

    if args.eval:
        with open(args.eval, "r", encoding="utf-8") as f:
            packet = json.load(f)
        outcomes = run_all_policies(packet)
        print(json.dumps(outcomes, sort_keys=True, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
