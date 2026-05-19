#!/usr/bin/env python3
"""aep_pre_tool_guard_daemon_tcp.py - TCP-server daemon for Wave-2 daemon-mode.

Wave 2 of AEP v1.5 LTS Ultimate Last Pass mission (2026-05-18).
Pairs with aep_pre_tool_guard_client.py to close FINAL PASS-CLOSURE GAP 1.

ARCHITECTURE
============
Persistent TCP server on 127.0.0.1:<ephemeral-port>. Port written to
.claude/aep/runtime/daemon.port; PID written to daemon.pid.

Per-request flow:
  CLIENT  -> {"tool_name":"Read","tool_input":{...}}\n
  SERVER  -> {"exit_code":0,"reason":"","rule_id":"","risk_tier":"Casual"}\n

Idle timeout: 1 hour of no activity -> graceful shutdown.

SECURITY
========
- Binds 127.0.0.1 ONLY (no external network exposure).
- Port is ephemeral (OS-assigned).
- Each connection gets ONE request then closed (no persistent socket state).
- Daemon loads constitution ONCE at startup; no per-request file IO for policy.

Stdlib only. sec68-compliant (Python only, no PowerShell).
"""
from __future__ import annotations

import os
import sys
import time
import json
import socket
import socketserver
import threading

_DAEMON_FILE = __file__


def _find_repo_root():
    p = os.path.abspath(_DAEMON_FILE)
    for _ in range(10):
        p = os.path.dirname(p)
        if os.path.isdir(os.path.join(p, ".claude")) and os.path.isdir(os.path.join(p, "doctrine")):
            return p
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(_DAEMON_FILE)))))


_REPO_ROOT = _find_repo_root()
_RUNTIME_DIR = os.path.join(_REPO_ROOT, ".claude", "aep", "runtime")
_PORT_FILE = os.path.join(_RUNTIME_DIR, "daemon.port")
_PID_FILE = os.path.join(_RUNTIME_DIR, "daemon.pid")
_LOG_FILE = os.path.join(_REPO_ROOT, ".claude", "aep", "perf", "daemon_lifecycle.jsonl")
_HOOK_PATH = os.path.join(_REPO_ROOT, ".claude", "hooks", "aep", "aep_pre_tool_guard.py")

_IDLE_TIMEOUT_S = 3600.0  # 1 hour
_last_activity = time.time()
_activity_lock = threading.Lock()


def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _log(event, **extra):
    row = {"ts": _utc_now_iso(), "event": event, "pid": os.getpid()}
    row.update(extra)
    try:
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _load_hook_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("aep_pre_tool_guard_daemon_loaded", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_hook_mod = None


def _evaluate(event):
    global _hook_mod
    if _hook_mod is None:
        _hook_mod = _load_hook_module()
        # Pre-warm constitution
        _hook_mod._load_constitution()
    try:
        return _hook_mod.evaluate(event)
    except Exception as e:
        return (0, f"daemon_eval_err:{type(e).__name__}:{e}", "", "Casual")


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        global _last_activity
        with _activity_lock:
            _last_activity = time.time()
        try:
            self.request.settimeout(2.0)
            buf = b""
            while b"\n" not in buf:
                chunk = self.request.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 1_048_576:
                    break
            line = buf.split(b"\n", 1)[0].decode("utf-8")
            event = json.loads(line)
            code, reason, rule_id, risk_tier = _evaluate(event)
            resp = {
                "exit_code": int(code),
                "reason": reason,
                "rule_id": rule_id,
                "risk_tier": risk_tier,
            }
            self.request.sendall((json.dumps(resp, separators=(",", ":")) + "\n").encode("utf-8"))
        except Exception as e:
            try:
                err = {
                    "exit_code": 0,
                    "reason": f"daemon_handler_err:{type(e).__name__}",
                    "rule_id": "",
                    "risk_tier": "Casual",
                }
                self.request.sendall((json.dumps(err) + "\n").encode("utf-8"))
            except Exception:
                pass


class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _idle_watchdog(server):
    global _last_activity
    while True:
        time.sleep(60.0)
        with _activity_lock:
            elapsed = time.time() - _last_activity
        if elapsed > _IDLE_TIMEOUT_S:
            _log("idle_shutdown", idle_seconds=round(elapsed, 1))
            try:
                _cleanup()
            finally:
                server.shutdown()
            return


def _cleanup():
    for f in (_PORT_FILE, _PID_FILE):
        try:
            os.remove(f)
        except Exception:
            pass


def main():
    os.makedirs(_RUNTIME_DIR, exist_ok=True)
    # Pre-warm
    _evaluate({"tool_name": "Read", "tool_input": {"file_path": "/tmp/warmup"}})
    server = _ThreadedServer(("127.0.0.1", 0), _Handler)
    host, port = server.server_address
    # Write port + pid atomically (write tmp then rename)
    tmp_port = _PORT_FILE + ".tmp"
    tmp_pid = _PID_FILE + ".tmp"
    with open(tmp_port, "w", encoding="utf-8") as f:
        f.write(str(port))
    with open(tmp_pid, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    os.replace(tmp_port, _PORT_FILE)
    os.replace(tmp_pid, _PID_FILE)
    _log("daemon_listening", host=host, port=port)
    # Watchdog thread
    threading.Thread(target=_idle_watchdog, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()
        _log("daemon_exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
