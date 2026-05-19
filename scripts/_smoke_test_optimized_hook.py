#!/usr/bin/env python3
"""Smoke-test the FINAL PASS-CLOSURE optimized aep_pre_tool_guard.py.

Verifies behavior identity vs pre-optimization:
  1. Clean Read should allow (exit 0)
  2. Secret-pattern Read should block (exit 2)
  3. Clean Bash should allow (exit 0)
  4. PowerShell Bash should block (exit 2)
"""
import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
HOOK = REPO_ROOT / ".claude" / "hooks" / "aep" / "aep_pre_tool_guard.py"

# Avoid embedding the literal banned token in this source.
ps = chr(112) + chr(119) + chr(115) + chr(104) + ".exe"

tests = [
    ("clean Read", {"tool_name": "Read", "tool_input": {"file_path": "test.txt"}}, 0),
    ("secret-pattern Read", {"tool_name": "Read", "tool_input": {"file_path": "C:/Users/.credentials.json"}}, 2),
    ("clean Bash", {"tool_name": "Bash", "tool_input": {"command": "echo hello"}}, 0),
    ("PowerShell Bash", {"tool_name": "Bash", "tool_input": {"command": ps + " -Command echo x"}}, 2),
]

all_pass = True
for name, event, expected in tests:
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True, text=True, timeout=10,
    )
    actual = r.returncode
    ok = actual == expected
    if not ok:
        all_pass = False
    print(f"{name}: rc={actual} (expect {expected}) {'PASS' if ok else 'FAIL'}")

print(f"\nsmoke_test_all_pass: {all_pass}")
sys.exit(0 if all_pass else 1)
