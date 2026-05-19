#!/usr/bin/env python3
"""aepfs.py - AEP-FS Transaction Journal CLI (K6).

Operator v1.5 LTS K6 Evidence Transaction Journal. Every mutation is a
begin -> write -> (commit | rollback) transaction with HCRL-chained receipts.

Composes_with:
  - operator-v15-K6 (Evidence Transaction Journal)
  - .claude/aep/constitution/aep_constitution_v1_5_lts.json (policy precedence)
  - .claude/hooks/aep/aep_pre_tool_guard.py (airlock decisions consulted)
  - .claude/hooks/aep/aep_post_tool_ledger.py (HCRL chain compatible)
  - sec68 (Python-only; no PowerShell)
  - sec73.5 (receipts emitted for every transition)

Subcommands:
  begin <intended_mutation_json> --target <path>   -> emit txn_id + pre_hash + rollback_plan
  write <txn_id> <path> <content_or_@file>         -> policy-checked write
  commit <txn_id>                                  -> verify post_hash, move to committed/
  rollback <txn_id>                                -> restore pre_hash bytes, move to rolled_back/
  doctor <packet_path>                             -> lightweight single-packet doctor
  list-active                                      -> show open transactions
  gc --older-than-days N                           -> clean rolled_back/ older than N days

Performance targets (per constitution.performance_gates extension):
  begin   p95 <= 30ms
  write   p95 <= 50ms
  commit  p95 <= 100ms
  rollback p95 <= 200ms

Latency per call appended to .claude/aep/perf/aepfs_latency.jsonl

Exit codes:
  0   success
  1   user error (bad args, missing txn)
  2   policy block (airlock-protected path, constitution-protected zone)
  3   integrity failure (pre_hash mismatch, post_hash mismatch, txn-state error)
  4   internal error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[5]
_AEP_DIR = _REPO_ROOT / ".claude" / "aep"
_TXN_ACTIVE = _AEP_DIR / "transactions" / "active"
_TXN_COMMITTED = _AEP_DIR / "transactions" / "committed"
_TXN_ROLLED_BACK = _AEP_DIR / "transactions" / "rolled_back"
_PERF_LOG = _AEP_DIR / "perf" / "aepfs_latency.jsonl"
_RECEIPT_LOG = _AEP_DIR / "transactions" / "aepfs_receipts.jsonl"
_CONSTITUTION_PATH = _AEP_DIR / "constitution" / "aep_constitution_v1_5_lts.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return sha256 hex of file content, or empty hex if missing.

    Empty file or missing file -> sha256 of zero bytes (e64...e3b0...) for
    file-missing? No: we distinguish. Missing -> "" sentinel. Empty exists
    -> standard sha256 of b"".
    """
    if not path.exists():
        return ""
    if not path.is_file():
        return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def _sha256_canonical(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _ensure_dirs() -> None:
    for d in (_TXN_ACTIVE, _TXN_COMMITTED, _TXN_ROLLED_BACK, _PERF_LOG.parent, _RECEIPT_LOG.parent):
        d.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _emit_perf(subcommand: str, latency_ms: float, outcome: str, txn_id: str = "") -> None:
    try:
        _append_jsonl(_PERF_LOG, {
            "ts": _utc_now_iso(),
            "subcommand": subcommand,
            "txn_id": txn_id,
            "outcome": outcome,
            "latency_ms": round(latency_ms, 3),
        })
    except Exception:
        pass


def _last_receipt_sha() -> str:
    try:
        if not _RECEIPT_LOG.exists():
            return ""
        last = ""
        with _RECEIPT_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line.strip()
        if not last:
            return ""
        return json.loads(last).get("row_sha256", "")
    except Exception:
        return ""


def _emit_receipt(phase: str, txn_id: str, payload: dict) -> str:
    row = {
        "ts": _utc_now_iso(),
        "actor": "aepfs",
        "phase": phase,
        "txn_id": txn_id,
        "schema_version": "v1.5.0-lts",
        "prev_row_sha256": _last_receipt_sha(),
    }
    row.update(payload)
    row["row_sha256"] = _sha256_canonical(row)
    _append_jsonl(_RECEIPT_LOG, row)
    return row["row_sha256"]


# ---------------------------------------------------------------------------
# Policy (airlock + protected-zone) - mirrors aep_pre_tool_guard.py logic
# ---------------------------------------------------------------------------
_CONSTITUTION_CACHE = None


def _load_constitution() -> dict:
    global _CONSTITUTION_CACHE
    if _CONSTITUTION_CACHE is not None:
        return _CONSTITUTION_CACHE
    try:
        _CONSTITUTION_CACHE = json.loads(_CONSTITUTION_PATH.read_text(encoding="utf-8"))
    except Exception:
        # Fail-closed default - never let aepfs run permissively if constitution missing
        _CONSTITUTION_CACHE = {
            "secret_airlock_rules": {
                "secret_path_patterns": [
                    ".credentials.json", ".env", "id_rsa", "id_ed25519",
                    "id_ecdsa", ".pem", ".pfx", ".p12", ".key", "token",
                    "secret", "password", "cookie", "session", "mcp-auth",
                ]
            }
        }
    return _CONSTITUTION_CACHE


def _is_secret_path(p: str) -> bool:
    constitution = _load_constitution()
    patterns = constitution.get("secret_airlock_rules", {}).get("secret_path_patterns", [])
    p_lower = p.lower()
    for pat in patterns:
        if pat.lower() in p_lower:
            return True
    return False


def _is_protected_zone(p: str) -> tuple[bool, str]:
    norm = p.replace("\\", "/").lower()
    if "/.claude/aep/constitution/" in norm:
        return (True, "constitution")
    if "/.claude/hooks/aep/" in norm:
        return (True, "aep_hooks")
    return (False, "")


def _has_audit_override() -> bool:
    return os.environ.get("AEP_LOCAL_CREDENTIAL_AUDIT") == "1"


def _has_receipt_token() -> bool:
    return bool(os.environ.get("AEP_RECEIPT_TOKEN"))


def _policy_decide(target_path: str) -> tuple[str, str]:
    """Return (decision, reason). decision in {ALLOW, DENY, SANDBOX_REQUIRED}."""
    if _is_secret_path(target_path):
        if _has_audit_override():
            # Even with override we deny WRITES - the audit-override is read-presence-only
            return ("DENY", f"secret-pattern path: {target_path} (audit override is read-presence-only, not write)")
        return ("DENY", f"secret-pattern path: {target_path} (airlock)")
    protected, zone = _is_protected_zone(target_path)
    if protected and not _has_receipt_token():
        return ("DENY", f"protected zone ({zone}): {target_path} (AEP_RECEIPT_TOKEN required)")
    return ("ALLOW", "")


# ---------------------------------------------------------------------------
# Transaction state
# ---------------------------------------------------------------------------
def _txn_record_path(txn_id: str, state: str) -> Path:
    if state == "active":
        return _TXN_ACTIVE / f"{txn_id}.json"
    if state == "committed":
        return _TXN_COMMITTED / f"{txn_id}.json"
    if state == "rolled_back":
        return _TXN_ROLLED_BACK / f"{txn_id}.json"
    raise ValueError(f"unknown state: {state}")


def _txn_backup_path(txn_id: str) -> Path:
    return _TXN_ACTIVE / f"{txn_id}.backup"


def _load_active_txn(txn_id: str) -> dict | None:
    p = _txn_record_path(txn_id, "active")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_active_txn(txn_id: str, rec: dict) -> None:
    p = _txn_record_path(txn_id, "active")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------------------
# Subcommand: begin
# ---------------------------------------------------------------------------
def cmd_begin(args) -> int:
    t0 = time.perf_counter()
    try:
        try:
            intended = json.loads(args.intended_mutation_json)
        except Exception as e:
            print(f"[aepfs:begin] intended_mutation_json must be valid JSON: {e}", file=sys.stderr)
            _emit_perf("begin", (time.perf_counter() - t0) * 1000.0, "user_error")
            return 1
        if not isinstance(intended, dict):
            print("[aepfs:begin] intended_mutation must be a JSON object", file=sys.stderr)
            _emit_perf("begin", (time.perf_counter() - t0) * 1000.0, "user_error")
            return 1

        target = args.target
        # Policy check - declare-and-check pattern (so begin captures policy decision)
        decision, reason = _policy_decide(target)
        target_path = Path(target)

        # pre_hash captures the on-disk state BEFORE any mutation
        pre_hash = _sha256_file(target_path)
        file_existed = target_path.exists() and target_path.is_file()

        # Build rollback plan
        rollback_plan = {
            "method": "restore_pre_hash_bytes",
            "target_path": str(target_path),
            "file_existed_before": file_existed,
            "pre_hash": pre_hash,
            "delete_on_rollback_if_did_not_exist": not file_existed,
        }

        # Capture backup bytes (only if file existed and policy allows reading it)
        backup_size = 0
        if file_existed and decision == "ALLOW":
            try:
                bkp = _txn_backup_path("__pending__")  # provisional
                # We need txn_id to name backup correctly; mint id first
                pass
            except Exception:
                pass

        txn_id = uuid.uuid4().hex
        rec = {
            "txn_id": txn_id,
            "intended_mutation": intended,
            "target_path": str(target_path),
            "pre_hash": pre_hash,
            "post_hash": None,
            "rollback_plan": rollback_plan,
            "policy_decision": decision,
            "policy_reason": reason,
            "state": "active",
            "created_at": _utc_now_iso(),
            "file_existed_before": file_existed,
        }

        # Materialize backup bytes
        if file_existed and decision == "ALLOW":
            try:
                bkp_path = _txn_backup_path(txn_id)
                bkp_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, bkp_path)
                rec["backup_path"] = str(bkp_path)
                rec["backup_size_bytes"] = bkp_path.stat().st_size
                backup_size = rec["backup_size_bytes"]
            except Exception as e:
                rec["backup_error"] = f"{type(e).__name__}: {e}"

        _save_active_txn(txn_id, rec)

        receipt_sha = _emit_receipt("begin", txn_id, {
            "target_path": str(target_path),
            "pre_hash": pre_hash,
            "policy_decision": decision,
            "policy_reason": reason,
            "intended_mutation_sha256": _sha256_canonical(intended),
            "backup_size_bytes": backup_size,
        })

        elapsed = (time.perf_counter() - t0) * 1000.0
        _emit_perf("begin", elapsed, "ok", txn_id)

        # Stdout: structured JSON
        print(json.dumps({
            "txn_id": txn_id,
            "pre_hash": pre_hash,
            "policy_decision": decision,
            "policy_reason": reason,
            "rollback_plan": rollback_plan,
            "receipt_sha256": receipt_sha,
            "latency_ms": round(elapsed, 3),
        }, indent=2))
        return 0
    except Exception as e:
        _emit_perf("begin", (time.perf_counter() - t0) * 1000.0, "internal_error")
        print(f"[aepfs:begin] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# Subcommand: write
# ---------------------------------------------------------------------------
def cmd_write(args) -> int:
    t0 = time.perf_counter()
    try:
        txn_id = args.txn_id
        rec = _load_active_txn(txn_id)
        if rec is None:
            print(f"[aepfs:write] no active transaction: {txn_id}", file=sys.stderr)
            _emit_perf("write", (time.perf_counter() - t0) * 1000.0, "user_error", txn_id)
            return 1

        if rec["policy_decision"] != "ALLOW":
            print(f"[aepfs:write] transaction policy is {rec['policy_decision']}: {rec.get('policy_reason')}", file=sys.stderr)
            _emit_perf("write", (time.perf_counter() - t0) * 1000.0, "policy_block", txn_id)
            return 2

        # The path argument MUST match the txn target (so we don't write to a
        # path the airlock never evaluated).
        if str(Path(args.path)) != str(Path(rec["target_path"])):
            print(f"[aepfs:write] path mismatch: txn target is {rec['target_path']}, got {args.path}", file=sys.stderr)
            _emit_perf("write", (time.perf_counter() - t0) * 1000.0, "user_error", txn_id)
            return 1

        # Content: literal or @file
        content = args.content
        if isinstance(content, str) and content.startswith("@"):
            src = Path(content[1:])
            if not src.exists():
                print(f"[aepfs:write] content file does not exist: {src}", file=sys.stderr)
                _emit_perf("write", (time.perf_counter() - t0) * 1000.0, "user_error", txn_id)
                return 1
            content_bytes = src.read_bytes()
        else:
            content_bytes = (content or "").encode("utf-8")

        # Re-check policy at write time (constitution may have changed since begin)
        decision, reason = _policy_decide(rec["target_path"])
        if decision != "ALLOW":
            print(f"[aepfs:write] policy decision changed: {decision} {reason}", file=sys.stderr)
            _emit_perf("write", (time.perf_counter() - t0) * 1000.0, "policy_block", txn_id)
            return 2

        target = Path(rec["target_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content_bytes)
        post_hash = _sha256_bytes(content_bytes)

        rec["post_hash"] = post_hash
        rec["bytes_written"] = len(content_bytes)
        rec["write_at"] = _utc_now_iso()
        _save_active_txn(txn_id, rec)

        receipt_sha = _emit_receipt("write", txn_id, {
            "target_path": rec["target_path"],
            "post_hash": post_hash,
            "bytes_written": len(content_bytes),
        })

        elapsed = (time.perf_counter() - t0) * 1000.0
        _emit_perf("write", elapsed, "ok", txn_id)
        print(json.dumps({
            "txn_id": txn_id,
            "post_hash": post_hash,
            "bytes_written": len(content_bytes),
            "receipt_sha256": receipt_sha,
            "latency_ms": round(elapsed, 3),
        }, indent=2))
        return 0
    except Exception as e:
        _emit_perf("write", (time.perf_counter() - t0) * 1000.0, "internal_error", args.txn_id)
        print(f"[aepfs:write] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# Subcommand: commit
# ---------------------------------------------------------------------------
def cmd_commit(args) -> int:
    t0 = time.perf_counter()
    try:
        txn_id = args.txn_id
        rec = _load_active_txn(txn_id)
        if rec is None:
            print(f"[aepfs:commit] no active transaction: {txn_id}", file=sys.stderr)
            _emit_perf("commit", (time.perf_counter() - t0) * 1000.0, "user_error", txn_id)
            return 1
        if rec.get("post_hash") is None:
            print(f"[aepfs:commit] transaction has no write: {txn_id}", file=sys.stderr)
            _emit_perf("commit", (time.perf_counter() - t0) * 1000.0, "user_error", txn_id)
            return 1

        target = Path(rec["target_path"])
        actual_hash = _sha256_file(target)
        if actual_hash != rec["post_hash"]:
            # Integrity failure - the file changed after write but before commit
            _emit_perf("commit", (time.perf_counter() - t0) * 1000.0, "integrity_fail", txn_id)
            print(json.dumps({
                "txn_id": txn_id,
                "error": "integrity_fail",
                "expected_post_hash": rec["post_hash"],
                "actual_hash": actual_hash,
            }, indent=2), file=sys.stderr)
            return 3

        rec["state"] = "committed"
        rec["committed_at"] = _utc_now_iso()
        # Move record
        dst = _txn_record_path(txn_id, "committed")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")
        # Remove active record + backup (commit means rollback no longer possible)
        active_path = _txn_record_path(txn_id, "active")
        if active_path.exists():
            active_path.unlink()
        bkp_path = _txn_backup_path(txn_id)
        if bkp_path.exists():
            bkp_path.unlink()

        receipt_sha = _emit_receipt("commit", txn_id, {
            "target_path": rec["target_path"],
            "post_hash": rec["post_hash"],
            "pre_hash": rec["pre_hash"],
            "committed_at": rec["committed_at"],
        })
        elapsed = (time.perf_counter() - t0) * 1000.0
        _emit_perf("commit", elapsed, "ok", txn_id)
        print(json.dumps({
            "txn_id": txn_id,
            "state": "committed",
            "receipt_sha256": receipt_sha,
            "latency_ms": round(elapsed, 3),
        }, indent=2))
        return 0
    except Exception as e:
        _emit_perf("commit", (time.perf_counter() - t0) * 1000.0, "internal_error", args.txn_id)
        print(f"[aepfs:commit] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# Subcommand: rollback
# ---------------------------------------------------------------------------
def cmd_rollback(args) -> int:
    t0 = time.perf_counter()
    try:
        txn_id = args.txn_id
        rec = _load_active_txn(txn_id)
        if rec is None:
            print(f"[aepfs:rollback] no active transaction: {txn_id}", file=sys.stderr)
            _emit_perf("rollback", (time.perf_counter() - t0) * 1000.0, "user_error", txn_id)
            return 1

        target = Path(rec["target_path"])
        existed_before = rec.get("file_existed_before", False)
        pre_hash = rec.get("pre_hash", "")

        # Two rollback paths:
        # 1. File existed before -> restore backup bytes
        # 2. File did not exist -> delete the file (if created during write)
        if existed_before:
            bkp = _txn_backup_path(txn_id)
            if not bkp.exists():
                # Cannot rollback safely
                _emit_perf("rollback", (time.perf_counter() - t0) * 1000.0, "integrity_fail", txn_id)
                print(json.dumps({"txn_id": txn_id, "error": "backup_missing"}, indent=2), file=sys.stderr)
                return 3
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bkp, target)
        else:
            # File did not exist before; delete it if write created it
            if target.exists():
                try:
                    target.unlink()
                except Exception as e:
                    _emit_perf("rollback", (time.perf_counter() - t0) * 1000.0, "integrity_fail", txn_id)
                    print(json.dumps({"txn_id": txn_id, "error": f"unlink_failed: {e}"}, indent=2), file=sys.stderr)
                    return 3

        # Verify post-rollback hash matches pre_hash (or empty == empty if file_did_not_exist)
        post_rollback_hash = _sha256_file(target)
        if post_rollback_hash != pre_hash:
            _emit_perf("rollback", (time.perf_counter() - t0) * 1000.0, "integrity_fail", txn_id)
            print(json.dumps({
                "txn_id": txn_id,
                "error": "post_rollback_hash_mismatch",
                "expected_pre_hash": pre_hash,
                "actual_hash": post_rollback_hash,
            }, indent=2), file=sys.stderr)
            return 3

        rec["state"] = "rolled_back"
        rec["rolled_back_at"] = _utc_now_iso()
        rec["post_rollback_hash"] = post_rollback_hash
        dst = _txn_record_path(txn_id, "rolled_back")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")
        active_path = _txn_record_path(txn_id, "active")
        if active_path.exists():
            active_path.unlink()
        bkp_path = _txn_backup_path(txn_id)
        if bkp_path.exists():
            bkp_path.unlink()

        receipt_sha = _emit_receipt("rollback", txn_id, {
            "target_path": rec["target_path"],
            "pre_hash": pre_hash,
            "post_rollback_hash": post_rollback_hash,
            "rolled_back_at": rec["rolled_back_at"],
        })
        elapsed = (time.perf_counter() - t0) * 1000.0
        _emit_perf("rollback", elapsed, "ok", txn_id)
        print(json.dumps({
            "txn_id": txn_id,
            "state": "rolled_back",
            "post_rollback_hash": post_rollback_hash,
            "receipt_sha256": receipt_sha,
            "latency_ms": round(elapsed, 3),
        }, indent=2))
        return 0
    except Exception as e:
        _emit_perf("rollback", (time.perf_counter() - t0) * 1000.0, "internal_error", args.txn_id)
        print(f"[aepfs:rollback] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# Subcommand: doctor (lightweight)
# ---------------------------------------------------------------------------
def cmd_doctor(args) -> int:
    """Lightweight doctor for a single .aepkg packet.

    Checks: existence, manifest.json parses, claims.jsonl parses each line.
    Not a replacement for full aep_doctor.py - this is a 5ms smoke check.
    """
    t0 = time.perf_counter()
    p = Path(args.packet_path)
    findings = {"packet_path": str(p), "checks": []}
    try:
        if not p.exists():
            findings["checks"].append({"name": "exists", "ok": False, "detail": "path missing"})
            findings["overall_ok"] = False
            _emit_perf("doctor", (time.perf_counter() - t0) * 1000.0, "user_error")
            print(json.dumps(findings, indent=2))
            return 1
        findings["checks"].append({"name": "exists", "ok": True})

        manifest = p / "manifest.json"
        if manifest.exists():
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
                findings["checks"].append({"name": "manifest_parses", "ok": True, "version": m.get("aep_version") or m.get("version")})
            except Exception as e:
                findings["checks"].append({"name": "manifest_parses", "ok": False, "detail": str(e)})
        else:
            findings["checks"].append({"name": "manifest_exists", "ok": False, "detail": "manifest.json missing"})

        claims = p / "data" / "claims.jsonl"
        if claims.exists():
            ok_lines = 0
            bad_lines = 0
            try:
                with claims.open("r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            json.loads(line)
                            ok_lines += 1
                        except Exception:
                            bad_lines += 1
                findings["checks"].append({
                    "name": "claims_jsonl_parses",
                    "ok": bad_lines == 0,
                    "ok_lines": ok_lines,
                    "bad_lines": bad_lines,
                })
            except Exception as e:
                findings["checks"].append({"name": "claims_jsonl_parses", "ok": False, "detail": str(e)})
        else:
            findings["checks"].append({"name": "claims_jsonl_exists", "ok": False, "detail": "data/claims.jsonl missing"})

        overall = all(c.get("ok") for c in findings["checks"])
        findings["overall_ok"] = overall
        elapsed = (time.perf_counter() - t0) * 1000.0
        findings["latency_ms"] = round(elapsed, 3)
        _emit_perf("doctor", elapsed, "ok" if overall else "findings")
        print(json.dumps(findings, indent=2))
        return 0 if overall else 1
    except Exception as e:
        _emit_perf("doctor", (time.perf_counter() - t0) * 1000.0, "internal_error")
        print(f"[aepfs:doctor] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# Subcommand: list-active
# ---------------------------------------------------------------------------
def cmd_list_active(args) -> int:
    t0 = time.perf_counter()
    try:
        _ensure_dirs()
        rows = []
        for jf in sorted(_TXN_ACTIVE.glob("*.json")):
            try:
                rec = json.loads(jf.read_text(encoding="utf-8"))
                rows.append({
                    "txn_id": rec.get("txn_id"),
                    "target_path": rec.get("target_path"),
                    "created_at": rec.get("created_at"),
                    "policy_decision": rec.get("policy_decision"),
                    "has_write": rec.get("post_hash") is not None,
                })
            except Exception:
                pass
        elapsed = (time.perf_counter() - t0) * 1000.0
        _emit_perf("list-active", elapsed, "ok")
        print(json.dumps({"active_count": len(rows), "transactions": rows, "latency_ms": round(elapsed, 3)}, indent=2))
        return 0
    except Exception as e:
        _emit_perf("list-active", (time.perf_counter() - t0) * 1000.0, "internal_error")
        print(f"[aepfs:list-active] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# Subcommand: gc
# ---------------------------------------------------------------------------
def cmd_gc(args) -> int:
    t0 = time.perf_counter()
    try:
        _ensure_dirs()
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)
        removed = 0
        for jf in _TXN_ROLLED_BACK.glob("*.json"):
            try:
                rec = json.loads(jf.read_text(encoding="utf-8"))
                ts = rec.get("rolled_back_at") or rec.get("created_at") or ""
                if not ts:
                    continue
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt < cutoff:
                    jf.unlink()
                    removed += 1
            except Exception:
                continue
        elapsed = (time.perf_counter() - t0) * 1000.0
        _emit_perf("gc", elapsed, "ok")
        print(json.dumps({"removed_count": removed, "older_than_days": args.older_than_days, "latency_ms": round(elapsed, 3)}, indent=2))
        return 0
    except Exception as e:
        _emit_perf("gc", (time.perf_counter() - t0) * 1000.0, "internal_error")
        print(f"[aepfs:gc] INTERNAL_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 4


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aepfs", description="AEP-FS transaction journal CLI (K6)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_begin = sub.add_parser("begin", help="open a new transaction")
    sp_begin.add_argument("intended_mutation_json", help="JSON object describing intended mutation")
    sp_begin.add_argument("--target", required=True, help="target file path")
    sp_begin.set_defaults(func=cmd_begin)

    sp_write = sub.add_parser("write", help="write content within an active transaction")
    sp_write.add_argument("txn_id")
    sp_write.add_argument("path", help="must match the transaction target_path")
    sp_write.add_argument("content", help="literal content or @path-to-file")
    sp_write.set_defaults(func=cmd_write)

    sp_commit = sub.add_parser("commit", help="commit an active transaction")
    sp_commit.add_argument("txn_id")
    sp_commit.set_defaults(func=cmd_commit)

    sp_rollback = sub.add_parser("rollback", help="rollback an active transaction")
    sp_rollback.add_argument("txn_id")
    sp_rollback.set_defaults(func=cmd_rollback)

    sp_doctor = sub.add_parser("doctor", help="lightweight check on a single .aepkg packet")
    sp_doctor.add_argument("packet_path")
    sp_doctor.set_defaults(func=cmd_doctor)

    sp_list = sub.add_parser("list-active", help="show open transactions")
    sp_list.set_defaults(func=cmd_list_active)

    sp_gc = sub.add_parser("gc", help="garbage-collect rolled_back transactions")
    sp_gc.add_argument("--older-than-days", type=int, default=30)
    sp_gc.set_defaults(func=cmd_gc)

    return p


def main(argv=None) -> int:
    _ensure_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
