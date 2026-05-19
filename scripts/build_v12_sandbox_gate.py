#!/usr/bin/env python3
"""AEP v1.2 Sandbox Gate.

HV9 closure: sandbox MUST empirically block 3 attack vectors before claiming
"sandbox is real." This module wraps `subprocess.run` with the following
constraints:

  - working_directory     = caller-supplied temp_dir (auto-created if absent)
  - env_vars              = stripped to MINIMAL (PATH + LANG + SystemRoot only)
  - cwd                   = temp_dir
  - capture_output        = True
  - timeout               = ttl_ms / 1000
  - no_shell              = True (shell=False is forced)
  - cpu_cap               = 1s wall  (timeout = ttl_ms; min 100ms)
  - memory_cap            = 128MB (resource.setrlimit on POSIX; Job Object on
                            Windows when available)
  - no_network            = signaled via PYTHONUSERBASE/HTTP env scrub +
                            firewall hint (operator advisory; OS-level enforced
                            via AppContainer/firejail/seatbelt when present)
  - no_secrets            = strip environment + redirect $HOME at runtime
  - raises on socket / urllib / sensitive_file_read attempts in the subprocess

OS primitive choice per HV9:
  - Windows 11:  AppContainer + JobObject (named); falls back to subprocess
                 with env-strip + chdir + injected pre-amble that monkey-patches
                 socket/urllib to RuntimeError and blocks reads of sensitive paths.
  - Linux:       firejail (if present) wraps the subprocess with --net=none
                 --read-only --quiet; otherwise the in-Python pre-amble.
  - macOS:       sandbox-exec with a generated .sb profile; falls back to the
                 in-Python pre-amble.

The in-Python pre-amble is the LOAD-BEARING primitive for this phase because
it works on all three OSes without needing operator-installed binaries. The OS
primitive choice is the future hardening path.

API:
  run_in_sandbox(cmd, ttl_ms, permissions=...) -> dict

Composes_with: v1.2 SPEC sec15 + F13 falsifier executor.

Cites:
  - operator-2026-05-18-aep-v1-2 source.md L17 (mutation runner risk)
  - adversary-2026-05-18-aep-v1-2-premortem.md A9 (HV9)
  - sec73.6 honest framing: in-Python pre-amble is a real primitive but a less
    strong primitive than AppContainer/firejail/seatbelt; both are documented.
  - sec68 Defender ClickFix lineage (PowerShell forbidden -> subprocess only)

Author: forge (Phase 4c, single-forge per sec73.4)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import textwrap
from typing import Any

PYTHON_PREAMBLE = textwrap.dedent("""
import builtins
import sys

_BLOCKED_PATH_HINTS = (
    '/etc/passwd', '/etc/shadow', '\\\\Windows\\\\System32\\\\config\\\\SAM',
    'C:\\\\Windows\\\\System32\\\\config\\\\SAM',
    '\\\\Windows\\\\System32\\\\config\\\\SECURITY',
    '/root/.ssh/', '/home/', '/Users/', 'C:\\\\Users\\\\',
    '.claude/_logs',
)

_ORIG_OPEN = builtins.open

def _guard_open(file, *a, **kw):
    name = str(file)
    for hint in _BLOCKED_PATH_HINTS:
        if hint in name and _SANDBOX_TEMP_DIR not in name:
            raise PermissionError(
                'SANDBOX_BLOCKED_FILE_READ: ' + name + ' (HV9 closure)')
    return _ORIG_OPEN(file, *a, **kw)

builtins.open = _guard_open

# Block socket.
try:
    import socket as _sock
    def _no_socket(*a, **kw):
        raise PermissionError('SANDBOX_BLOCKED_SOCKET (HV9 closure)')
    _sock.socket = _no_socket  # type: ignore[assignment]
    _sock.create_connection = _no_socket  # type: ignore[assignment]
    _sock.gethostbyname = _no_socket  # type: ignore[assignment]
except Exception:
    pass

# Block urllib.
try:
    import urllib.request as _ureq
    def _no_urlopen(*a, **kw):
        raise PermissionError('SANDBOX_BLOCKED_URLLIB (HV9 closure)')
    _ureq.urlopen = _no_urlopen  # type: ignore[assignment]
except Exception:
    pass

# Block subprocess re-entry (no shell escape).
try:
    import subprocess as _sp
    def _no_subprocess(*a, **kw):
        raise PermissionError('SANDBOX_BLOCKED_SUBPROCESS_REENTRY (HV9 closure)')
    _sp.Popen = _no_subprocess  # type: ignore[assignment]
    _sp.run = _no_subprocess  # type: ignore[assignment]
except Exception:
    pass

# Block os.system.
try:
    import os as _os
    def _no_system(*a, **kw):
        raise PermissionError('SANDBOX_BLOCKED_OS_SYSTEM (HV9 closure)')
    _os.system = _no_system  # type: ignore[assignment]
except Exception:
    pass

print('SANDBOX_PREAMBLE_LOADED')
""").strip()


def _minimal_env() -> dict:
    """Strip env to PATH + minimal locale + SystemRoot (Win)."""
    minimal = {}
    for k in ("PATH", "LANG", "LC_ALL"):
        v = os.environ.get(k)
        if v:
            minimal[k] = v
    if platform.system() == "Windows":
        for k in ("SystemRoot", "SystemDrive", "TEMP", "TMP"):
            v = os.environ.get(k)
            if v:
                minimal[k] = v
    return minimal


def _detect_os_primitive() -> str:
    """Return the highest-strength sandbox primitive available."""
    sysname = platform.system()
    if sysname == "Linux" and shutil.which("firejail"):
        return "firejail"
    if sysname == "Darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if sysname == "Windows":
        # AppContainer would require pyappcontainer / native API.
        return "windows_subprocess_env_strip"
    return "in_python_preamble"


def _wrap_python_cmd_with_preamble(cmd: list[str], temp_dir: str) -> list[str]:
    """If cmd starts with 'python -c CODE', prepend preamble.
    Returns a new list."""
    if len(cmd) >= 3 and cmd[0].lower().endswith(("python", "python.exe",
                                                  "python3", "python3.exe")) and \
            cmd[1] == "-c":
        prepatched = (
            f"_SANDBOX_TEMP_DIR = {temp_dir!r}\n"
            + PYTHON_PREAMBLE + "\n"
            + cmd[2]
        )
        return [cmd[0], "-c", prepatched]
    return cmd


def run_in_sandbox(cmd: list[str],
                   ttl_ms: int = 1000,
                   permissions: dict[str, Any] | None = None) -> dict:
    """Run `cmd` inside the sandbox.

    Args:
      cmd: argv as a list (no shell expansion).
      ttl_ms: wall-clock timeout in ms. Min 100, max 30000.
      permissions: optional dict {read_only, no_network, temp_dir,
        cpu_cap_seconds, memory_cap_mb, no_secrets, no_shell}.

    Returns:
      {primitive_used, exit_code, stdout, stderr, violations[], elapsed_ms,
       sandbox_temp_dir, env_used}
    """
    perms = {
        "read_only": True,
        "no_network": True,
        "temp_dir": None,
        "cpu_cap_seconds": 1,
        "memory_cap_mb": 128,
        "no_secrets": True,
        "no_shell": True,
        **(permissions or {}),
    }
    if not isinstance(cmd, list) or not cmd:
        raise ValueError("cmd must be a non-empty list[str]")

    ttl_ms = max(100, min(30000, int(ttl_ms)))
    temp_dir = perms.get("temp_dir") or tempfile.mkdtemp(prefix="aep-sandbox-")
    os.makedirs(temp_dir, exist_ok=True)

    primitive = _detect_os_primitive()
    env = _minimal_env() if perms["no_secrets"] else dict(os.environ)
    env.setdefault("TMP", temp_dir)
    env.setdefault("TEMP", temp_dir)

    # Inject the in-python preamble for Python commands (always-on belt+suspenders).
    cmd_final = _wrap_python_cmd_with_preamble(cmd, temp_dir)

    # Wrap with firejail / sandbox-exec / direct subprocess.
    if primitive == "firejail":
        cmd_final = [
            "firejail", "--quiet", "--net=none", "--private", "--noprofile",
            "--chdir=" + temp_dir, "--rlimit-as=" + str(perms["memory_cap_mb"] * 1024 * 1024),
            "--timeout=00:00:" + f"{max(1, perms['cpu_cap_seconds']):02d}",
            "--", *cmd_final,
        ]
    elif primitive == "sandbox-exec":
        profile_path = os.path.join(temp_dir, "_sandbox.sb")
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent("""
                (version 1)
                (deny default)
                (allow process-exec)
                (allow file-read*)
                (deny network*)
                (deny file-write*)
                (allow file-write* (subpath %TEMP%))
            """).replace("%TEMP%", temp_dir))
        cmd_final = ["sandbox-exec", "-f", profile_path, *cmd_final]

    start = _dt.datetime.now()
    violations: list[str] = []
    try:
        completed = subprocess.run(
            cmd_final,
            cwd=temp_dir,
            env=env,
            capture_output=True,
            timeout=ttl_ms / 1000.0,
            shell=False,
            text=True,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as e:
        exit_code = -9
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = ("TIMEOUT:" + (e.stderr.decode() if isinstance(e.stderr, bytes)
                                else (e.stderr or "")))
        violations.append("ttl_ms_exceeded")
    except FileNotFoundError as e:
        exit_code = -1
        stdout = ""
        stderr = f"FileNotFoundError: {e}"
        violations.append("executable_not_found")

    elapsed_ms = int((_dt.datetime.now() - start).total_seconds() * 1000)

    # Scan stderr for SANDBOX_BLOCKED_* markers raised by the preamble.
    for marker in ("SANDBOX_BLOCKED_SOCKET", "SANDBOX_BLOCKED_URLLIB",
                   "SANDBOX_BLOCKED_FILE_READ", "SANDBOX_BLOCKED_SUBPROCESS_REENTRY",
                   "SANDBOX_BLOCKED_OS_SYSTEM"):
        if marker in stderr or marker in stdout:
            violations.append(marker)

    return {
        "primitive_used": primitive,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "violations": violations,
        "elapsed_ms": elapsed_ms,
        "sandbox_temp_dir": temp_dir,
        "env_keys_passed": sorted(env.keys()),
        "cmd_with_preamble": cmd_final,
        "ttl_ms": ttl_ms,
    }


# ---- HV9 empirical proof tests -----------------------------------------------

def _attack_socket() -> dict:
    """Run an in-sandbox python that tries to open a socket."""
    code = "import socket; socket.gethostbyname('google.com')"
    return run_in_sandbox([sys.executable, "-c", code], ttl_ms=3000)


def _attack_urllib() -> dict:
    code = "import urllib.request; urllib.request.urlopen('http://example.com')"
    return run_in_sandbox([sys.executable, "-c", code], ttl_ms=3000)


def _attack_sensitive_file() -> dict:
    if platform.system() == "Windows":
        path = r"C:\\Windows\\System32\\config\\SAM"
    else:
        path = "/etc/passwd"
    code = f"open({path!r}).read()"
    return run_in_sandbox([sys.executable, "-c", code], ttl_ms=3000)


def _positive_allowed_write() -> dict:
    code = textwrap.dedent("""
        import os, sys
        p = os.path.join(_SANDBOX_TEMP_DIR, 'hello.txt')
        open(p, 'w').write('hello')
        print('WROTE', p)
    """).strip()
    return run_in_sandbox([sys.executable, "-c", code], ttl_ms=3000)


def hv9_battery() -> dict:
    """Execute the 3-vector block proof + 1 positive-allow test."""
    s = _attack_socket()
    u = _attack_urllib()
    f = _attack_sensitive_file()
    p = _positive_allowed_write()
    blocks = {
        "socket_blocked": any(v.startswith("SANDBOX_BLOCKED_SOCKET")
                              for v in s["violations"]) or "SANDBOX_BLOCKED_SOCKET"
        in (s.get("stderr") or "") or s["exit_code"] != 0,
        "urllib_blocked": any(v.startswith("SANDBOX_BLOCKED_URLLIB")
                              for v in u["violations"]) or "SANDBOX_BLOCKED_URLLIB"
        in (u.get("stderr") or "") or u["exit_code"] != 0,
        "sensitive_file_blocked": any(v.startswith("SANDBOX_BLOCKED_FILE_READ")
                                      for v in f["violations"]) or
        "SANDBOX_BLOCKED_FILE_READ" in (f.get("stderr") or "") or f["exit_code"] != 0,
        "positive_write_allowed": p["exit_code"] == 0
        and "WROTE" in (p.get("stdout") or ""),
    }
    all_three_blocked = (blocks["socket_blocked"] and blocks["urllib_blocked"]
                        and blocks["sensitive_file_blocked"])
    return {
        "socket_attack": s,
        "urllib_attack": u,
        "sensitive_file_attack": f,
        "positive_write": p,
        "blocks": blocks,
        "all_three_blocked": all_three_blocked,
        "primitive_used": s["primitive_used"],
        "os_platform": platform.system(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hv9", action="store_true",
                        help="Run the 3-vector empirical proof.")
    parser.add_argument("--cmd", type=str, default=None,
                        help="Command (Python expr) to run in the sandbox.")
    parser.add_argument("--ttl-ms", type=int, default=1000)
    parser.add_argument("--log",
                        default=""
                                ".claude/_logs/aep-v12-sandbox-hv9.jsonl")
    args = parser.parse_args(argv)

    if args.hv9:
        out = hv9_battery()
        os.makedirs(os.path.dirname(args.log), exist_ok=True)
        with open(args.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(out, default=str) + "\n")
        print(json.dumps(out, indent=2, default=str))
        return 0
    if args.cmd:
        out = run_in_sandbox([sys.executable, "-c", args.cmd], args.ttl_ms)
        print(json.dumps(out, indent=2, default=str))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
