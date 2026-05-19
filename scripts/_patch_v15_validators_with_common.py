#!/usr/bin/env python3
"""_patch_v15_validators_with_common.py - one-shot patcher (idempotent).

For each of the 9 v1.1 validators, inject a call to v15_validators_common
right before the final 'return out' of v15_validate_extended_mutations.

Idempotent: if the call already exists, skip.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPTS = pathlib.Path(__file__).resolve().parent

TARGETS = [
    "validate_f13_falsifier.py",
    "validate_f15_witness_chain.py",
    "build_f16_attack_registry.py",
    "build_f17_packet_history_dag.py",
    "build_f18_provenance_graph.py",
    "build_f19_coverage_witness.py",
    "validate_v11_amendments.py",
    "validate_v1_0_3_1.py",
]

# Marker we look for in the source: the `return out` immediately after the v15_validate_extended_mutations
# function declaration block. We match a flexible-but-bounded shape.

INJECT_BLOCK = """    # FINAL PASS-CLOSURE: 6 independent structural-mutation checks (encoding/float-edge/
    # time-skew/hash-shape/semantic-equivalence/linguistic). Composes with sec73.6 honest framing.
    try:
        from v15_validators_common import v15_common_structural_checks  # type: ignore
        out.extend(v15_common_structural_checks(packet))
    except Exception:  # noqa: BLE001
        try:
            import importlib.util, pathlib as _pl
            _spec = importlib.util.spec_from_file_location(
                "v15_validators_common",
                str(_pl.Path(__file__).resolve().parent / "v15_validators_common.py"),
            )
            if _spec and _spec.loader:
                _m = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_m)
                out.extend(_m.v15_common_structural_checks(packet))
        except Exception:  # noqa: BLE001
            out.append("AEP15_COMMON_MODULE_LOAD_FAILED")
    return out
"""

MARKER = "v15_common_structural_checks"


def patch_file(path: pathlib.Path) -> str:
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        return "skip-already-patched"
    # Find the def v15_validate_extended_mutations block
    m = re.search(
        r"(def v15_validate_extended_mutations\([^\)]*\)[^:]*:\s*\n(?:(?:[ \t]+[^\n]*\n)+))",
        src,
    )
    if not m:
        return "no-match-for-v15-entry"
    block = m.group(1)
    # Find the LAST occurrence of '    return out\n' in that block.
    last_idx = block.rfind("    return out\n")
    if last_idx == -1:
        # Try without trailing newline
        last_idx = block.rfind("    return out")
        if last_idx == -1:
            return "no-return-out-found"
        # Append newline boundary
        new_block = block[:last_idx] + INJECT_BLOCK
    else:
        new_block = block[:last_idx] + INJECT_BLOCK
    new_src = src[: m.start(1)] + new_block + src[m.end(1):]
    path.write_text(new_src, encoding="utf-8")
    return "patched"


def main(argv):
    outcomes = {}
    for name in TARGETS:
        p = SCRIPTS / name
        if not p.exists():
            outcomes[name] = "missing"
            continue
        outcomes[name] = patch_file(p)
    for k, v in outcomes.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
