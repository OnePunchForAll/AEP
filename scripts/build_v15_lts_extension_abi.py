#!/usr/bin/env python3
"""
build_v15_lts_extension_abi.py - K11 LTS Extension ABI (AEP v1.5 LTS)

Operator directive (sec73.2 sacred): K11 LTS Extension ABI.
"No future extension may require breaking the core."

The kernel schema is FROZEN at v1.5. Extensions:
  - MUST be namespaced (ext.<vendor>.<name>)
  - CANNOT modify core schema fields
  - MUST declare compatibility_range
  - MUST be installable + uninstallable WITHOUT changing kernel state

Extension manifest schema:
{
  "extension_id": "ext:<namespace>:<name>:v<x>",
  "schema_hash": "sha256:...",
  "compatibility_range": ["v1.5.0", "v1.999.x"],
  "policy_impact": "none|advisory|enforcement",
  "migration_behavior": "additive_only|namespaced|forbidden",
  "rollback_behavior": "instant|graceful_decay",
  "tests": ["test_path1"],
  "trust_tier": "Casual|Important|Professional|Critical"
}

API:
  - install_extension(manifest_path)
  - uninstall_extension(extension_id)
  - verify_kernel_unchanged_after_extension_ops(N)

Storage: .claude/aep/extensions/installed/<extension_id>.json
Audit:   .claude/_logs/aep-v15-lts-extension-abi.jsonl

Truth tag: STRONGLY PLAUSIBLE (T3 install/uninstall x20 empirical this turn;
production rollout STAGED v1.5.1 with operator-approved extension registry).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


# ---------- Constants ----------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CONSTITUTION_PATH = REPO_ROOT / ".claude" / "aep" / "constitution" / "aep_constitution_v1_5_lts.json"
EXTENSIONS_DIR = REPO_ROOT / ".claude" / "aep" / "extensions" / "installed"
AUDIT_LOG = REPO_ROOT / ".claude" / "_logs" / "aep-v15-lts-extension-abi.jsonl"

EXTENSION_ID_RE = re.compile(r"^ext:[a-z0-9_]+:[a-z0-9_]+:v\d+(\.\d+)*$")
NAMESPACE_RE = re.compile(r"^ext\.[a-z0-9_]+\.[a-z0-9_]+$")

VALID_POLICY_IMPACT = {"none", "advisory", "enforcement"}
VALID_MIGRATION = {"additive_only", "namespaced", "forbidden"}
VALID_ROLLBACK = {"instant", "graceful_decay"}
VALID_TRUST_TIER = {"Casual", "Important", "Professional", "Critical"}

# Core schema fields that extensions CANNOT touch.
CORE_SCHEMA_FIELDS = (
    "version",
    "frozen_at",
    "operator_authority",
    "policy_precedence",
    "forbidden_actions",
    "secret_airlock_rules",
    "trust_tiers",
    "completion_witness_requirements",
)


# ---------- Helpers ----------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _kernel_state_hash() -> str:
    """
    Compute a deterministic hash of the kernel's core schema fields.

    This is the integrity oracle for verify_kernel_unchanged_after_extension_ops.
    Reads the constitution; extracts only CORE_SCHEMA_FIELDS; hashes the
    canonical JSON of that subset.
    """
    if not CONSTITUTION_PATH.is_file():
        return "MISSING_CONSTITUTION"
    try:
        c = json.loads(CONSTITUTION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "MALFORMED_CONSTITUTION"
    core = {k: c.get(k) for k in CORE_SCHEMA_FIELDS}
    canon = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _audit_row(payload: Dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["timestamp"] = _now_iso()
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------- Manifest validation ----------

def validate_manifest(manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate an extension manifest. Returns (ok, errors).
    """
    errors: List[str] = []

    eid = manifest.get("extension_id")
    if not isinstance(eid, str) or not EXTENSION_ID_RE.match(eid):
        errors.append(
            f"extension_id must match {EXTENSION_ID_RE.pattern!r}, got {eid!r}"
        )

    sh = manifest.get("schema_hash")
    if not isinstance(sh, str) or not (sh.startswith("sha256:") and len(sh) >= 70):
        errors.append(f"schema_hash must be 'sha256:<64hex>', got {sh!r}")

    cr = manifest.get("compatibility_range")
    if not (isinstance(cr, list) and len(cr) == 2 and all(isinstance(x, str) for x in cr)):
        errors.append(f"compatibility_range must be [from, to] strings, got {cr!r}")

    pi = manifest.get("policy_impact")
    if pi not in VALID_POLICY_IMPACT:
        errors.append(
            f"policy_impact must be one of {sorted(VALID_POLICY_IMPACT)}, got {pi!r}"
        )

    mb = manifest.get("migration_behavior")
    if mb not in VALID_MIGRATION:
        errors.append(
            f"migration_behavior must be one of {sorted(VALID_MIGRATION)}, got {mb!r}"
        )

    rb = manifest.get("rollback_behavior")
    if rb not in VALID_ROLLBACK:
        errors.append(
            f"rollback_behavior must be one of {sorted(VALID_ROLLBACK)}, got {rb!r}"
        )

    tests = manifest.get("tests")
    if not isinstance(tests, list):
        errors.append(f"tests must be a list, got {type(tests).__name__}")

    tt = manifest.get("trust_tier")
    if tt not in VALID_TRUST_TIER:
        errors.append(
            f"trust_tier must be one of {sorted(VALID_TRUST_TIER)}, got {tt!r}"
        )

    # Cross-check: extension_id namespace cannot collide with core schema fields
    if isinstance(eid, str) and ":" in eid:
        parts = eid.split(":")
        if len(parts) >= 3 and parts[1] in CORE_SCHEMA_FIELDS:
            errors.append(
                f"extension namespace {parts[1]!r} collides with core schema field"
            )

    return (not errors, errors)


def _namespace_from_extension_id(eid: str) -> str:
    """ext:vendor:name:vX -> ext.vendor.name"""
    parts = eid.split(":")
    if len(parts) < 3:
        return ""
    return f"ext.{parts[1]}.{parts[2]}"


# ---------- Install ----------

def install_extension(manifest_path: pathlib.Path) -> Dict[str, Any]:
    """
    Install an extension from its manifest JSON.

    Returns:
      {
        "accepted": bool,
        "namespace_id": str,
        "conflicts": [str],
        "errors": [str],
        "kernel_state_hash_pre": str,
        "kernel_state_hash_post": str,
        "kernel_unchanged": bool
      }
    """
    pre = _kernel_state_hash()
    p = pathlib.Path(manifest_path)
    if not p.is_file():
        result = {
            "accepted": False,
            "namespace_id": "",
            "conflicts": [],
            "errors": [f"manifest not found: {p}"],
            "kernel_state_hash_pre": pre,
            "kernel_state_hash_post": pre,
            "kernel_unchanged": True,
        }
        _audit_row({"op": "install", **result})
        return result
    try:
        manifest = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        result = {
            "accepted": False,
            "namespace_id": "",
            "conflicts": [],
            "errors": [f"manifest not valid JSON: {e}"],
            "kernel_state_hash_pre": pre,
            "kernel_state_hash_post": pre,
            "kernel_unchanged": True,
        }
        _audit_row({"op": "install", **result})
        return result

    ok, errors = validate_manifest(manifest)
    if not ok:
        result = {
            "accepted": False,
            "namespace_id": "",
            "conflicts": [],
            "errors": errors,
            "kernel_state_hash_pre": pre,
            "kernel_state_hash_post": _kernel_state_hash(),
            "kernel_unchanged": True,
        }
        _audit_row({"op": "install", **result})
        return result

    eid = manifest["extension_id"]
    namespace_id = _namespace_from_extension_id(eid)

    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
    target = EXTENSIONS_DIR / f"{eid.replace(':', '_')}.json"

    conflicts: List[str] = []
    if target.is_file():
        conflicts.append(f"already installed: {eid}")

    # Namespace collision check
    for existing_p in EXTENSIONS_DIR.glob("*.json"):
        try:
            existing = json.loads(existing_p.read_text(encoding="utf-8"))
        except Exception:
            continue
        ex_eid = existing.get("manifest", {}).get("extension_id", "")
        if ex_eid and ex_eid != eid:
            ex_ns = _namespace_from_extension_id(ex_eid)
            if ex_ns == namespace_id:
                conflicts.append(
                    f"namespace collision: {namespace_id} already used by {ex_eid}"
                )

    if conflicts:
        result = {
            "accepted": False,
            "namespace_id": namespace_id,
            "conflicts": conflicts,
            "errors": [],
            "kernel_state_hash_pre": pre,
            "kernel_state_hash_post": _kernel_state_hash(),
            "kernel_unchanged": True,
        }
        _audit_row({"op": "install", "extension_id": eid, **result})
        return result

    # Write installation record
    record = {
        "manifest": manifest,
        "installed_at": _now_iso(),
        "namespace_id": namespace_id,
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            .encode("utf-8")
        ).hexdigest(),
    }
    target.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    post = _kernel_state_hash()
    result = {
        "accepted": True,
        "namespace_id": namespace_id,
        "conflicts": [],
        "errors": [],
        "kernel_state_hash_pre": pre,
        "kernel_state_hash_post": post,
        "kernel_unchanged": (pre == post),
        "record_path": str(target),
    }
    _audit_row({"op": "install", "extension_id": eid, **result})
    return result


# ---------- Uninstall ----------

def uninstall_extension(extension_id: str) -> Dict[str, Any]:
    """
    Uninstall an extension by id. Returns rollback report.
    """
    pre = _kernel_state_hash()
    target = EXTENSIONS_DIR / f"{extension_id.replace(':', '_')}.json"
    if not target.is_file():
        result = {
            "removed": False,
            "rollback_complete": True,
            "errors": [f"not installed: {extension_id}"],
            "kernel_state_hash_pre": pre,
            "kernel_state_hash_post": pre,
            "kernel_unchanged": True,
        }
        _audit_row({"op": "uninstall", "extension_id": extension_id, **result})
        return result
    try:
        target.unlink()
    except Exception as e:
        result = {
            "removed": False,
            "rollback_complete": False,
            "errors": [f"unlink failed: {e}"],
            "kernel_state_hash_pre": pre,
            "kernel_state_hash_post": _kernel_state_hash(),
            "kernel_unchanged": True,
        }
        _audit_row({"op": "uninstall", "extension_id": extension_id, **result})
        return result

    post = _kernel_state_hash()
    result = {
        "removed": True,
        "rollback_complete": True,
        "errors": [],
        "kernel_state_hash_pre": pre,
        "kernel_state_hash_post": post,
        "kernel_unchanged": (pre == post),
    }
    _audit_row({"op": "uninstall", "extension_id": extension_id, **result})
    return result


# ---------- Kernel integrity probe ----------

def verify_kernel_unchanged_after_extension_ops(N: int = 20) -> Dict[str, Any]:
    """
    Empirical probe: install + uninstall N synthetic extensions and assert
    the kernel's core schema hash never changes.

    Returns:
      {
        "core_schema_intact": bool,
        "rounds": int,
        "kernel_state_hash_initial": str,
        "kernel_state_hash_final": str,
        "all_installs_accepted": bool,
        "all_uninstalls_removed": bool,
        "per_round": [...]
      }
    """
    initial = _kernel_state_hash()
    per_round: List[Dict[str, Any]] = []
    all_installs = True
    all_uninstalls = True
    intact = True

    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = REPO_ROOT / ".claude" / "aep" / "extensions" / "_synthetic_manifests"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for i in range(N):
        vendor = f"v{i:03d}"
        name = f"syn{i:03d}"
        eid = f"ext:{vendor}:{name}:v1"
        manifest = {
            "extension_id": eid,
            "schema_hash": "sha256:" + ("0" * 64),
            "compatibility_range": ["v1.5.0", "v1.999.x"],
            "policy_impact": "advisory",
            "migration_behavior": "additive_only",
            "rollback_behavior": "instant",
            "tests": [f"tests/synthetic_{i}.py"],
            "trust_tier": "Casual",
        }
        mpath = tmp_dir / f"{eid.replace(':', '_')}.json"
        mpath.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ins = install_extension(mpath)
        installed_hash = _kernel_state_hash()
        if not ins["accepted"]:
            all_installs = False
        uns = uninstall_extension(eid)
        post_hash = _kernel_state_hash()
        if not uns["removed"]:
            all_uninstalls = False
        if installed_hash != initial or post_hash != initial:
            intact = False
        per_round.append({
            "round": i,
            "extension_id": eid,
            "install_accepted": ins["accepted"],
            "uninstall_removed": uns["removed"],
            "hash_after_install": installed_hash,
            "hash_after_uninstall": post_hash,
            "hash_matches_initial": (post_hash == initial),
        })
        # Cleanup synthetic manifest
        try:
            mpath.unlink()
        except Exception:
            pass

    final = _kernel_state_hash()
    return {
        "core_schema_intact": intact and (final == initial),
        "rounds": N,
        "kernel_state_hash_initial": initial,
        "kernel_state_hash_final": final,
        "all_installs_accepted": all_installs,
        "all_uninstalls_removed": all_uninstalls,
        "per_round": per_round,
    }


# ---------- CLI ----------

def _cli() -> int:
    ap = argparse.ArgumentParser(description="K11 LTS Extension ABI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_inst = sub.add_parser("install")
    sp_inst.add_argument("manifest")

    sp_uninst = sub.add_parser("uninstall")
    sp_uninst.add_argument("extension_id")

    sp_verify = sub.add_parser("verify-kernel")
    sp_verify.add_argument("--rounds", type=int, default=20)

    args = ap.parse_args()
    if args.cmd == "install":
        result = install_extension(pathlib.Path(args.manifest))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["accepted"] else 1
    if args.cmd == "uninstall":
        result = uninstall_extension(args.extension_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["removed"] else 1
    if args.cmd == "verify-kernel":
        result = verify_kernel_unchanged_after_extension_ops(args.rounds)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["core_schema_intact"] else 2
    return 3


if __name__ == "__main__":
    sys.exit(_cli())
