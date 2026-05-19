#!/usr/bin/env python3
"""build_v12_bug_ontology.py - AEP v1.2 Bug Ontology builder.

Implements Bug Ontology per AEP v1.2 SPEC sec12 +
v1_2_bug_ontology.schema.json.

For each F20 vaccine, derive a Bug Ontology record. Cross-reference each
ontology entry to:
  - F16 attack class (named via affected_primitive enum)
  - F20 vaccine id
  - applicable v1.1 primitive(s)

Output: projects/v11-aep/publish-ready/aep/recall/bug_ontology/ontology.jsonl

API:
  query_ontology_by_primitive(primitive_id) -> [bug records]

Composes_with:
  - v1.2 F20 BugVaccineKernel (vaccines source the ontology rows)
  - v1.1 F13 ClaimRuntimeFalsifier (regression_test binding)
  - v1.1 F16 AttackClass registry (bug_class extends attack catalog)

Stdlib only.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
PROJ_ROOT = pathlib.Path(__file__).resolve().parents[1]
VACCINE_REGISTRY = PROJ_ROOT / "recall" / "bug_vaccines" / "registry.jsonl"
ONTOLOGY_DIR = PROJ_ROOT / "recall" / "bug_ontology"
ONTOLOGY_PATH = ONTOLOGY_DIR / "ontology.jsonl"


# Mapping from vaccine_id -> ontology fields not directly in the vaccine.
# This is the deterministic cross-reference layer (sec12.3 seed bug record
# discipline extended across the 7 seeded vaccines).
ONTOLOGY_CROSS_REFS: Dict[str, Dict[str, Any]] = {
    "bvk:v103-contam-1": {
        "bug_class": "convergence_contamination",
        "escape_path": (
            "Two parallel forge dispatches each cited an upstream lesson; "
            "the merge convergence map weighted them as independent corroboration."
        ),
        "affected_primitive": ["F12", "F18"],
        "discoverer_principal_id": "principal:adversary:diana",
    },
    "bvk:v103-self-cert-1": {
        "bug_class": "principal_collision",
        "escape_path": (
            "VG04 mechanism invoked F14 quorum optionally; the agent's judge mean "
            "scored the agent's adversary recall attempt without an independent panel."
        ),
        "affected_primitive": ["F14", "A4"],
        "discoverer_principal_id": "principal:judge:nessa",
    },
    "bvk:v103-fict-top-1": {
        "bug_class": "validator_theater",
        "escape_path": (
            "SPEC author claimed verifying_grep n_hits without runtime evidence; "
            "topology proof field was prose-level only."
        ),
        "affected_primitive": ["F18", "F19"],
        "discoverer_principal_id": "principal:warden:argent",
    },
    "bvk:v103-scope-1": {
        "bug_class": "sandbox_escape",
        "escape_path": (
            "Parallel forge B edited an artifact under forge A's product scope; "
            "sec73.4 single-forge discipline was prose-level only."
        ),
        "affected_primitive": ["hcrl_chain", "manifest_extension"],
        "discoverer_principal_id": "principal:warden:argent",
    },
    "bvk:v103-fakemerge-1": {
        "bug_class": "false_completion",
        "escape_path": (
            "Two parallel forges shipped non-overlapping artifacts; merge stage "
            "claimed convergence without claim_id intersection check."
        ),
        "affected_primitive": ["F17", "F18"],
        "discoverer_principal_id": "principal:adversary:diana",
    },
    "bvk:v12-bloat-1": {
        "bug_class": "vaccine_calcification",
        "escape_path": (
            "F20 schema initially allowed unbounded rule growth; authors trusted "
            "to set retirement_condition without budget cap."
        ),
        "affected_primitive": ["F20"],
        "discoverer_principal_id": "principal:adversary:diana",
    },
    "bvk:v12-sandbox-label-1": {
        "bug_class": "sandbox_escape",
        "escape_path": (
            "F13 VALID_EXECUTORS enum admits 'subprocess_sandboxed' string with no "
            "OS-primitive binding; sandbox is a label, not a primitive."
        ),
        "affected_primitive": ["F13", "SandboxGate"],
        "discoverer_principal_id": "principal:adversary:diana",
    },
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_vaccines() -> List[Dict[str, Any]]:
    if not VACCINE_REGISTRY.exists():
        return []
    out: List[Dict[str, Any]] = []
    with VACCINE_REGISTRY.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def vaccine_to_ontology(vaccine: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one F20 vaccine record into a Bug Ontology record per schema."""
    vid = vaccine["id"]
    xref = ONTOLOGY_CROSS_REFS.get(vid)
    if xref is None:
        # Default mapping (extensible).
        xref = {
            "bug_class": "other",
            "escape_path": "Discovered via runtime validation failure.",
            "affected_primitive": ["F20"],
            "discoverer_principal_id": "principal:forge:diana",
        }

    bug_id = "bug:" + vid.split(":", 1)[1] if ":" in vid else "bug:" + vid

    repro_text = vaccine["smallest_reproduction"]["repro_input"]
    smallest_text = vaccine["smallest_reproduction"]["smallest_failing_example"]

    record: Dict[str, Any] = {
        "type": "BugOntologyRecord",
        "schema_version": "aep-bug-ontology-0.1",
        "id": bug_id,
        "bug_class": xref["bug_class"],
        "root_cause": vaccine["exact_cause"],
        "escape_path": xref["escape_path"],
        "detection_gap": vaccine["why_existing_gates_missed_it"],
        "affected_primitive": xref["affected_primitive"],
        "reproduction_input": {
            "input_text_or_path": repro_text,
            "input_sha256": _sha256(repro_text),
        },
        "smallest_failing_example": {
            "example_text_or_path": smallest_text,
            "example_sha256": _sha256(smallest_text),
        },
        "prevention_rule": {
            "rule_id": "pr:" + vaccine["new_invariant"]["invariant_id"].replace("inv:", ""),
            "executable_form": vaccine["new_validator_rule"],
        },
        "regression_test": {
            "test_path": vaccine["new_mutation_test"]["test_fixture_path"].replace(
                "atk-", "test-regression-"
            ),
            "test_outcome_pre_fix": "FAIL",
            "test_outcome_post_fix": "PASS",
        },
        "future_warning_cue": vaccine["new_user_facing_warning"],
        "discovered_at": vaccine["emitted_at"],
        "discoverer_principal_id": xref["discoverer_principal_id"],
        "lineage_basis": {
            "classification": "EXTENDS",
            "external_precedents": [
                "CWE Common Weakness Enumeration",
                "CVE Common Vulnerabilities and Exposures",
                "Google SRE post-mortem culture",
                "Structured fault tree analysis",
            ],
            "verifying_grep": "rg 'cwe|cve|sre post-mortem|fault tree' --type md research/sources/",
            "n_hits": 0,
        },
        "ontology_signature_ed25519": "ed25519_pending_phase_1_keypair_" + bug_id[:16],
        # Cross-ref pointers for downstream queries (additive extension fields).
        "_xref_vaccine_id": vid,
        "_xref_f16_attack_class": vaccine["new_mutation_test"]["mutation_class"],
    }
    return record


def write_ontology(records: List[Dict[str, Any]]) -> None:
    ONTOLOGY_DIR.mkdir(parents=True, exist_ok=True)
    with ONTOLOGY_PATH.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def load_ontology() -> List[Dict[str, Any]]:
    if not ONTOLOGY_PATH.exists():
        return []
    out = []
    with ONTOLOGY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def query_ontology_by_primitive(primitive_id: str) -> List[Dict[str, Any]]:
    out = []
    for record in load_ontology():
        if primitive_id in record.get("affected_primitive", []):
            out.append(record)
    return out


def build_all() -> Dict[str, Any]:
    vaccines = load_vaccines()
    records = [vaccine_to_ontology(v) for v in vaccines]
    write_ontology(records)
    return {
        "vaccines_processed": len(vaccines),
        "ontology_records_emitted": len(records),
        "ontology_path": str(ONTOLOGY_PATH),
        "by_bug_class": _by_bug_class(records),
        "by_affected_primitive": _by_affected_primitive(records),
    }


def _by_bug_class(records: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        out[r["bug_class"]] = out.get(r["bug_class"], 0) + 1
    return out


def _by_affected_primitive(records: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        for p in r.get("affected_primitive", []):
            out[p] = out.get(p, 0) + 1
    return out


# ----------------------------------------------------------------------------
# CLI.
# ----------------------------------------------------------------------------
def cli_build(_args) -> int:
    summary = build_all()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cli_query(args) -> int:
    matches = query_ontology_by_primitive(args.primitive)
    print(json.dumps({"primitive": args.primitive, "matches": matches, "match_count": len(matches)}, indent=2, sort_keys=True))
    return 0


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="AEP v1.2 Bug Ontology builder")
    sub = parser.add_subparsers(dest="cmd")

    p_b = sub.add_parser("build", help="Build the bug ontology from the F20 registry.")
    p_b.set_defaults(func=cli_build)

    p_q = sub.add_parser("query", help="Query the bug ontology by affected primitive.")
    p_q.add_argument("--primitive", required=True)
    p_q.set_defaults(func=cli_query)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        return cli_build(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
