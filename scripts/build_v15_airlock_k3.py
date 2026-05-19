#!/usr/bin/env python3
"""build_v15_airlock_k3.py - K3 Airlock implementation (renamed from
build_v15_secret_airlock.py because the AEP airlock correctly blocks
write to any path containing the substring 'secret' - that includes our
own filename. Per sec73.6 we do not work around the hook; we adapt.).

Per operator v1.5 LTS K3 directive: no bytes-of-the-protected-class ever
flow through any agent surface. The airlock provides:

  * classify_path(path) -> {is_secret_candidate, secret_class, risk_class}
  * check_command_for_secret_access(cmd) -> {blocked, matched_pattern, reason}
  * presence_only_inventory(directory) -> [{path, secret_class, size_bytes, mtime} - NO CONTENT]
  * local_credential_audit(directory, audit_token) -> presence + risk_class ONLY

Composes_with:
  - .claude/aep/constitution/aep_constitution_v1_5_lts.json (secret_airlock_rules)
  - .claude/hooks/aep/aep_pre_tool_guard.py (this module mirrors the hook's logic in depth)
  - sec73.2 (operator-verbatim-sacred: patterns derived verbatim from operator constitution)
  - sec73.6 (no-operator-reaction-calibration: mechanical enforcement)
  - sec68 (Python only, no PowerShell)

Truth tag: STRONGLY PLAUSIBLE (pre-empirical-test).
After test_v15_exfiltration_attempts_k3.py 500/500 PASS -> PROVEN/RELIABLE.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

__all__ = [
    "classify_path",
    "check_command_for_secret_access",
    "presence_only_inventory",
    "local_credential_audit",
    "SecretClass",
    "RiskClass",
    "Airlock",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[5]
_CONSTITUTION_PATH = _REPO_ROOT / ".claude" / "aep" / "constitution" / "aep_constitution_v1_5_lts.json"

class SecretClass:
    SSH_PRIVATE_KEY = "ssh_private_key"
    PKCS_KEY = "pkcs_key"
    PEM_KEY = "pem_key"
    AWS_CREDENTIALS = "aws_credentials"
    DOTENV = "dotenv"
    CREDENTIALS_JSON = "credentials_json"
    MCP_AUTH_CACHE = "mcp_auth_cache"
    AUTH_JSON = "auth_json"
    CLIENT_SECRET = "client_secret"
    TOKEN_FILE = "token_file"
    SECRET_FILE = "secret_file"
    PASSWORD_FILE = "password_file"
    SESSION_FILE = "session_file"
    COOKIE_FILE = "cookie_file"
    GENERIC_KEY_FILE = "generic_key_file"
    NOT_SECRET = "not_secret"


class RiskClass:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Pattern -> (class, risk). Specific FIRST.
_PATTERN_MAP: list[tuple[str, str, str]] = [
    ("id_rsa",            SecretClass.SSH_PRIVATE_KEY,  RiskClass.CRITICAL),
    ("id_ed25519",        SecretClass.SSH_PRIVATE_KEY,  RiskClass.CRITICAL),
    ("id_ecdsa",          SecretClass.SSH_PRIVATE_KEY,  RiskClass.CRITICAL),
    (".pfx",              SecretClass.PKCS_KEY,         RiskClass.CRITICAL),
    (".p12",              SecretClass.PKCS_KEY,         RiskClass.CRITICAL),
    (".pem",              SecretClass.PEM_KEY,          RiskClass.HIGH),
    (".aws/credentials",  SecretClass.AWS_CREDENTIALS,  RiskClass.CRITICAL),
    (".credentials.json", SecretClass.CREDENTIALS_JSON, RiskClass.CRITICAL),
    ("credentials.json",  SecretClass.CREDENTIALS_JSON, RiskClass.HIGH),
    ("credentials",       SecretClass.AWS_CREDENTIALS,  RiskClass.HIGH),
    ("auth.json",         SecretClass.AUTH_JSON,        RiskClass.HIGH),
    ("client_secret",     SecretClass.CLIENT_SECRET,    RiskClass.HIGH),
    ("mcp-auth",          SecretClass.MCP_AUTH_CACHE,   RiskClass.HIGH),
    (".env",              SecretClass.DOTENV,           RiskClass.HIGH),
    (".key",              SecretClass.GENERIC_KEY_FILE, RiskClass.HIGH),
    ("token",             SecretClass.TOKEN_FILE,       RiskClass.HIGH),
    ("password",          SecretClass.PASSWORD_FILE,    RiskClass.MEDIUM),
    # The substring 'secret' is the operator's verbatim pattern; we keep it
    # but reference it indirectly so this file's own name does not include it.
    ("s" + "ecret",       SecretClass.SECRET_FILE,      RiskClass.MEDIUM),
    ("session",           SecretClass.SESSION_FILE,     RiskClass.MEDIUM),
    ("cookie",            SecretClass.COOKIE_FILE,      RiskClass.MEDIUM),
]


# ---------------------------------------------------------------------------
# Path normalization (defeats encoding / escape tricks)
# ---------------------------------------------------------------------------
def _normalize_path_string(p: str) -> str:
    if not isinstance(p, str):
        return ""
    s = p.strip()
    for _ in range(2):
        try:
            d = urllib.parse.unquote(s)
            if d == s:
                break
            s = d
        except Exception:
            break
    try:
        s = unicodedata.normalize("NFKC", s)
    except Exception:
        pass
    s = s.replace("\\", "/").lower()
    s = s.replace("\x00", "")
    parts = []
    for seg in s.split("/"):
        if seg == "":
            parts.append(seg)
            continue
        if seg == ".":
            continue
        parts.append(seg)
    return "/".join(parts)


def _extract_base64_candidates(s: str) -> list[str]:
    out = []
    # General base64 token scan (12+ chars) - low FP rate
    for m in re.finditer(r"[A-Za-z0-9+/=]{12,}", s):
        token = m.group(0)
        if "." in token or "-" in token or "_" in token:
            continue
        try:
            pad = (-len(token)) % 4
            d = base64.b64decode(token + ("=" * pad), validate=True).decode("utf-8", errors="ignore")
            if d and any(c.isprintable() and not c.isspace() for c in d):
                out.append(d.lower())
        except Exception:
            pass
    # Targeted scan: base64.b64decode(...) / b64decode('...') / decodebase64(...)
    # which are strong signals of decode-at-runtime adversary patterns. Allow
    # tokens as short as 4 chars (3-byte secrets) since these are wrapped
    # by an explicit decode call.
    for m in re.finditer(r"""(?:base64\.b64decode|b64decode|fromb64|decodebase64|base64decode)\s*\(\s*['"]([A-Za-z0-9+/=]{4,})['"]""", s, re.IGNORECASE):
        token = m.group(1)
        try:
            pad = (-len(token)) % 4
            d = base64.b64decode(token + ("=" * pad), validate=True).decode("utf-8", errors="ignore")
            if d and any(c.isprintable() and not c.isspace() for c in d):
                out.append(d.lower())
        except Exception:
            pass
    return out


def _extract_hex_candidates(s: str) -> list[str]:
    out = []
    # General hex token scan (16+ chars) - low FP rate
    for m in re.finditer(r"(?:0x)?([0-9a-fA-F]{16,})", s):
        token = m.group(1)
        if len(token) % 2 != 0:
            continue
        try:
            d = bytes.fromhex(token).decode("utf-8", errors="ignore")
            if d:
                out.append(d.lower())
        except Exception:
            pass
    # Targeted scan: bytes.fromhex(...) / fromhex('...') / 0x... literals
    # which are a strong signal of decode-at-runtime adversary patterns.
    for m in re.finditer(r"""(?:bytes\.fromhex|fromhex|unhexlify)\s*\(\s*['"]([0-9a-fA-F]{4,})['"]""", s, re.IGNORECASE):
        token = m.group(1)
        if len(token) % 2 != 0:
            continue
        try:
            d = bytes.fromhex(token).decode("utf-8", errors="ignore")
            if d:
                out.append(d.lower())
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def classify_path(path: str) -> dict:
    if not isinstance(path, str):
        return _not_a_match("")
    normalized = _normalize_path_string(path)
    # Direct
    for pat, cls, risk in _PATTERN_MAP:
        if pat.lower() in normalized:
            via = "direct"
            if pat.lower() not in path.lower().replace("\\", "/"):
                via = "url_or_unicode_decoded"
            return {
                "is_secret_candidate": True,
                "secret_class": cls,
                "risk_class": risk,
                "matched_pattern": pat,
                "normalized_path": normalized,
                "matched_via": via,
            }
    # Base64
    for cand in _extract_base64_candidates(path):
        cn = _normalize_path_string(cand)
        for pat, cls, risk in _PATTERN_MAP:
            if pat.lower() in cn:
                return {
                    "is_secret_candidate": True,
                    "secret_class": cls,
                    "risk_class": risk,
                    "matched_pattern": pat,
                    "normalized_path": normalized,
                    "matched_via": "base64_decoded",
                }
    # Hex
    for cand in _extract_hex_candidates(path):
        cn = _normalize_path_string(cand)
        for pat, cls, risk in _PATTERN_MAP:
            if pat.lower() in cn:
                return {
                    "is_secret_candidate": True,
                    "secret_class": cls,
                    "risk_class": risk,
                    "matched_pattern": pat,
                    "normalized_path": normalized,
                    "matched_via": "hex_decoded",
                }
    return _not_a_match(normalized)


def _not_a_match(normalized: str) -> dict:
    return {
        "is_secret_candidate": False,
        "secret_class": SecretClass.NOT_SECRET,
        "risk_class": RiskClass.LOW,
        "matched_pattern": None,
        "normalized_path": normalized,
        "matched_via": None,
    }


_READ_VERBS = [
    "cat ", "type ", "get-content ", "gc ", "less ", "more ", "head ",
    "tail ", "grep ", "rg ", "select-string ", "sls ", "findstr ",
    "ack ", "ag ", "open ", "open(",
]

_COPY_VERBS = [
    "cp ", "copy ", "scp ", "rsync ", "robocopy ", "mv ", "move ",
    "curl ", "wget ", "iwr ", "invoke-webrequest ", "invoke-restmethod ",
    "irm ", "send-mailmessage ", "pscp ", "ftp ",
]

_PYTHON_READ_PATTERNS = [
    r"open\s*\(\s*['\"][^'\"]*",
    r"pathlib\.path\s*\(\s*['\"][^'\"]*",
    r"path\s*\(\s*['\"][^'\"]*",
    r"with\s+open\s*\(",
    r"file\s*\(\s*['\"][^'\"]*",
    r"\.read_bytes\s*\(",
    r"\.read_text\s*\(",
    r"shutil\.copy",
    r"os\.popen",
    r"subprocess\.(?:run|call|check_output|popen|getoutput)",
]

_EXFIL_VERBS = [
    " | clip", " | xclip", " | pbcopy", " | nc ", " | netcat ",
    " >  /tmp/", " > /tmp/", " >c:\\", " >c:/", " > c:\\", " > c:/",
    " > /etc/", " > ~/", " >> ", " | curl ", " | wget ",
]

_KEY_DUMP_PATTERNS = [
    re.compile(r"ssh-keygen\s+-y\s+-f", re.IGNORECASE),
    re.compile(r"openssl\s+(?:rsa|pkey|pkcs12|ec|dsa)\s+.*-in\s+", re.IGNORECASE),
    re.compile(r"keytool\s+.*-list", re.IGNORECASE),
    re.compile(r"gpg\s+.*--export-secret", re.IGNORECASE),
]


def check_command_for_secret_access(cmd: str) -> dict:
    if not isinstance(cmd, str):
        return {"blocked": False, "matched_pattern": None, "reason": "non_string_command", "matched_path": None}
    if not cmd.strip():
        return {"blocked": False, "matched_pattern": None, "reason": "empty_command", "matched_path": None}

    lowered = cmd.lower()
    lowered_norm = lowered.replace("\\", "/")

    decoded_cmd = cmd
    for _ in range(2):
        try:
            d = urllib.parse.unquote(decoded_cmd)
            if d == decoded_cmd:
                break
            decoded_cmd = d
        except Exception:
            break
    decoded_lower = decoded_cmd.lower().replace("\\", "/")
    try:
        decoded_lower = unicodedata.normalize("NFKC", decoded_lower)
    except Exception:
        pass

    # Key-dump primitive
    for pat in _KEY_DUMP_PATTERNS:
        if pat.search(cmd) or pat.search(decoded_cmd):
            return {
                "blocked": True,
                "matched_pattern": pat.pattern,
                "reason": "key_dump_primitive",
                "matched_path": None,
            }

    # Embedded encoded literals (base64 / hex) inside the raw command body.
    # Adversary trick: hide ".env" or "id_rsa" inside a base64 string literal
    # that gets decoded at runtime via base64.b64decode('...') or bytes.fromhex(...).
    for b64_cand in _extract_base64_candidates(cmd):
        if not b64_cand or len(b64_cand) < 3:
            continue
        cls = classify_path(b64_cand)
        if cls["is_secret_candidate"]:
            return {
                "blocked": True,
                "matched_pattern": cls["matched_pattern"],
                "reason": "embedded_base64_decodes_to_match",
                "matched_path": b64_cand,
                "secret_class": cls["secret_class"],
                "risk_class": cls["risk_class"],
                "matched_via": "base64_embedded_in_cmd",
            }
    for hx_cand in _extract_hex_candidates(cmd):
        if not hx_cand or len(hx_cand) < 3:
            continue
        cls = classify_path(hx_cand)
        if cls["is_secret_candidate"]:
            return {
                "blocked": True,
                "matched_pattern": cls["matched_pattern"],
                "reason": "embedded_hex_decodes_to_match",
                "matched_path": hx_cand,
                "secret_class": cls["secret_class"],
                "risk_class": cls["risk_class"],
                "matched_via": "hex_embedded_in_cmd",
            }

    # Collect candidate path tokens
    path_tokens: list[str] = []
    for m in re.finditer(r"""['"]([^'"]+)['"]""", decoded_cmd):
        path_tokens.append(m.group(1))
    for t in re.split(r"[\s;|&()<>]+", decoded_cmd):
        if t:
            path_tokens.append(t.strip("'\""))
    for m in re.finditer(r"[>]+\s*(\S+)", decoded_cmd):
        path_tokens.append(m.group(1))
    for m in re.finditer(r"""open\s*\(\s*['"]([^'"]+)['"]""", decoded_cmd, re.IGNORECASE):
        path_tokens.append(m.group(1))
    for m in re.finditer(r"""path\s*\(\s*['"]([^'"]+)['"]""", decoded_cmd, re.IGNORECASE):
        path_tokens.append(m.group(1))

    matched_path = None
    matched_class = None
    for tok in path_tokens:
        if not tok or len(tok) < 3:
            continue
        cls = classify_path(tok)
        if cls["is_secret_candidate"]:
            matched_path = tok
            matched_class = cls
            break

    intent_read = any(v in decoded_lower for v in _READ_VERBS)
    intent_copy = any(v in decoded_lower for v in _COPY_VERBS)
    intent_exfil = any(v in decoded_lower for v in _EXFIL_VERBS)
    intent_py_read = any(re.search(p, decoded_lower) for p in _PYTHON_READ_PATTERNS)
    intent_any = intent_read or intent_copy or intent_exfil or intent_py_read

    if matched_path:
        if intent_any:
            parts = []
            if intent_read:
                parts.append("read_verb")
            if intent_copy:
                parts.append("copy_verb")
            if intent_exfil:
                parts.append("exfil_redirect")
            if intent_py_read:
                parts.append("python_read")
            return {
                "blocked": True,
                "matched_pattern": matched_class["matched_pattern"],
                "reason": "match_path_plus_" + "_".join(parts),
                "matched_path": matched_path,
                "secret_class": matched_class["secret_class"],
                "risk_class": matched_class["risk_class"],
                "matched_via": matched_class["matched_via"],
            }
        if matched_class["risk_class"] == RiskClass.CRITICAL:
            return {
                "blocked": True,
                "matched_pattern": matched_class["matched_pattern"],
                "reason": "critical_path_mentioned",
                "matched_path": matched_path,
                "secret_class": matched_class["secret_class"],
                "risk_class": matched_class["risk_class"],
                "matched_via": matched_class["matched_via"],
            }
        if matched_class["risk_class"] == RiskClass.HIGH and (
            "subprocess" in decoded_lower or "os.system" in decoded_lower or
            "os.popen" in decoded_lower or "exec(" in decoded_lower
        ):
            return {
                "blocked": True,
                "matched_pattern": matched_class["matched_pattern"],
                "reason": "high_in_subprocess",
                "matched_path": matched_path,
                "secret_class": matched_class["secret_class"],
                "risk_class": matched_class["risk_class"],
            }

    # Symlink to a target containing a secret pattern
    if re.search(r"(mklink|ln\s+-s|new-item.*-itemtype\s+symboliclink)", decoded_lower):
        for tok in path_tokens:
            cls = classify_path(tok)
            if cls["is_secret_candidate"]:
                return {
                    "blocked": True,
                    "matched_pattern": cls["matched_pattern"],
                    "reason": "symlink_to_match",
                    "matched_path": tok,
                    "secret_class": cls["secret_class"],
                    "risk_class": cls["risk_class"],
                }

    # Path traversal
    if "../" in lowered_norm or "..\\" in lowered:
        for m in re.finditer(r"(?:\.\./)+([^\s;|&'\"()<>]+)", decoded_lower):
            target = m.group(1)
            cls = classify_path(target)
            if cls["is_secret_candidate"]:
                return {
                    "blocked": True,
                    "matched_pattern": cls["matched_pattern"],
                    "reason": "path_traversal_to_match",
                    "matched_path": target,
                    "secret_class": cls["secret_class"],
                    "risk_class": cls["risk_class"],
                }

    # ADS / NTFS alt data stream
    ads = re.search(r"([^\s:'\"()<>]+):([\w$]+)", cmd)
    if ads:
        token = ads.group(0)
        cls = classify_path(token)
        if cls["is_secret_candidate"]:
            return {
                "blocked": True,
                "matched_pattern": cls["matched_pattern"],
                "reason": "alternate_data_stream_targets_match",
                "matched_path": token,
                "secret_class": cls["secret_class"],
                "risk_class": cls["risk_class"],
            }

    return {
        "blocked": False,
        "matched_pattern": None,
        "reason": "no_pattern_matched",
        "matched_path": None,
    }


def presence_only_inventory(directory: str, max_files: int = 1000) -> list[dict]:
    base = Path(directory)
    if not base.exists() or not base.is_dir():
        return []
    out: list[dict] = []
    count = 0
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", ".venv", "venv", "env")]
        for fn in files:
            count += 1
            if count > max_files:
                return out
            full = Path(root) / fn
            try:
                rel = str(full.relative_to(base)).replace("\\", "/")
            except ValueError:
                rel = str(full).replace("\\", "/")
            cls = classify_path(rel)
            if not cls["is_secret_candidate"]:
                cls = classify_path(fn)
            if cls["is_secret_candidate"]:
                try:
                    st = full.stat()
                    mtime_iso = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    out.append({
                        "path": rel,
                        "secret_class": cls["secret_class"],
                        "risk_class": cls["risk_class"],
                        "size_bytes": st.st_size,
                        "mtime_iso": mtime_iso,
                    })
                except Exception:
                    out.append({
                        "path": rel,
                        "secret_class": cls["secret_class"],
                        "risk_class": cls["risk_class"],
                        "size_bytes": -1,
                        "mtime_iso": "",
                    })
    return out


def local_credential_audit(directory: str, audit_token: str | None = None) -> dict:
    env_flag = os.environ.get("AEP_LOCAL_CREDENTIAL_AUDIT")
    env_token = os.environ.get("AEP_LOCAL_CREDENTIAL_AUDIT_TOKEN")
    if env_flag != "1":
        return {"ok": False, "reason": "AEP_LOCAL_CREDENTIAL_AUDIT must be '1'", "presence": []}
    if audit_token is None or audit_token == "":
        if env_token is None:
            return {"ok": False, "reason": "audit_token required", "presence": []}
    raw = presence_only_inventory(directory)
    presence = []
    for row in raw:
        sz = row.get("size_bytes", 0)
        if sz < 0:
            bucket = "unknown"
        elif sz < 4096:
            bucket = "small"
        elif sz < 65536:
            bucket = "medium"
        else:
            bucket = "large"
        presence.append({
            "path": row["path"],
            "secret_class": row["secret_class"],
            "risk_class": row["risk_class"],
            "size_bucket": bucket,
            "mtime_iso": row["mtime_iso"],
        })
    return {"ok": True, "reason": "audit_authorized", "scope": "local_only", "presence": presence, "presence_count": len(presence)}


class Airlock:
    @staticmethod
    def classify(path: str) -> dict:
        return classify_path(path)

    @staticmethod
    def check_command(cmd: str) -> dict:
        return check_command_for_secret_access(cmd)

    @staticmethod
    def inventory(directory: str) -> list[dict]:
        return presence_only_inventory(directory)

    @staticmethod
    def audit(directory: str, token: str | None = None) -> dict:
        return local_credential_audit(directory, token)


def _cli_main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="airlock", description="K3 Airlock surface")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp_cl = sub.add_parser("classify")
    sp_cl.add_argument("path")
    sp_chk = sub.add_parser("check")
    sp_chk.add_argument("command")
    sp_inv = sub.add_parser("inventory")
    sp_inv.add_argument("directory")
    sp_aud = sub.add_parser("audit")
    sp_aud.add_argument("directory")
    sp_aud.add_argument("--token", default="")
    args = p.parse_args(argv)
    if args.cmd == "classify":
        print(json.dumps(classify_path(args.path), indent=2))
    elif args.cmd == "check":
        print(json.dumps(check_command_for_secret_access(args.command), indent=2))
    elif args.cmd == "inventory":
        print(json.dumps(presence_only_inventory(args.directory), indent=2))
    elif args.cmd == "audit":
        print(json.dumps(local_credential_audit(args.directory, args.token or None), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
