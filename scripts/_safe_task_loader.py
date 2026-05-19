"""_safe_task_loader.py - shared task-hint loader for lag_retrieve*.py.

Per doctrine/68-defender-alert-stops-burn.html (operator incident-remediation
directive 2026-05-16): natural-language task hints MUST NOT pass through
process argv. Use a task-file containing JSON instead.

This module provides one helper:
    load_task_hint(args) -> str
        - if args.task_file is set: read JSON from that file, return its
          "task_hint" field.
        - elif args.task_hint is set: validate it is short + ASCII +
          mojibake-free + does not trip command_safety; return it.
        - else: argparse-side --task-file or --task-hint is required.

Apply via add_task_args(ap) which adds the two mutually-exclusive flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the security module importable from the scripts/ dir.
_HERE = Path(__file__).resolve().parent
_AEP_ROOT = _HERE.parent
if str(_AEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_AEP_ROOT))

from security.command_safety import (  # noqa: E402
    CommandUnsafeError,
    assert_command_safe,
    classify_command,
)


# A direct --task-hint is allowed ONLY if it is short, ASCII, and free of
# spaces / shell metacharacters. Anything else MUST come via --task-file.
_TASK_HINT_MAX_CHARS = 96
_TASK_HINT_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./"
)


class TaskHintRejected(RuntimeError):
    """Raised when --task-hint argv text fails the safety policy."""


def add_task_args(ap: argparse.ArgumentParser) -> None:
    """Add mutually-exclusive --task-file and --task-hint to an argparse parser."""
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--task-file",
        type=Path,
        default=None,
        help=(
            "Path to a JSON file containing {'task_hint': '<text>'}. PREFERRED. "
            "Natural-language hints belong in files, not argv."
        ),
    )
    group.add_argument(
        "--task-hint",
        default=None,
        help=(
            "Short ASCII task-hint (max %d chars, no spaces). For longer prose "
            "or any Unicode, use --task-file. Per doctrine/68-defender-alert-"
            "stops-burn.html."
        ) % _TASK_HINT_MAX_CHARS,
    )


def _validate_inline_hint(hint: str) -> str:
    if len(hint) > _TASK_HINT_MAX_CHARS:
        raise TaskHintRejected(
            f"--task-hint exceeds {_TASK_HINT_MAX_CHARS} chars (got {len(hint)}). "
            f"Use --task-file <path> for longer hints. "
            f"Policy: doctrine/68-defender-alert-stops-burn.html"
        )
    bad = sorted({c for c in hint if c not in _TASK_HINT_ALLOWED})
    if bad:
        raise TaskHintRejected(
            f"--task-hint contains disallowed characters {bad!r}. "
            f"Inline hints must be ASCII alphanumerics + [-_./]. "
            f"Use --task-file for anything else. "
            f"Policy: doctrine/68-defender-alert-stops-burn.html"
        )
    # Last belt: synthesize a representative argv and run the classifier.
    synth = f"python lag_retrieve.py --task-hint {hint}"
    try:
        assert_command_safe(synth)
    except CommandUnsafeError as exc:
        raise TaskHintRejected(
            f"--task-hint failed command_safety classifier:\n{exc}"
        ) from exc
    return hint


def _load_from_file(path: Path) -> str:
    if not path.exists():
        raise TaskHintRejected(f"--task-file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise TaskHintRejected(
            f"--task-file {path} is not valid JSON: {type(e).__name__}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise TaskHintRejected(
            f"--task-file {path} must contain a JSON object at top level."
        )
    hint = data.get("task_hint")
    if not isinstance(hint, str) or not hint.strip():
        raise TaskHintRejected(
            f"--task-file {path} must define a non-empty string field 'task_hint'."
        )
    # Unicode hint INSIDE a file is fine (UTF-8 textfile substrate). We do not
    # apply the ASCII/length restriction here.
    return hint


def load_task_hint(args: argparse.Namespace) -> str:
    """Resolve args.task_file / args.task_hint to the final hint string.

    Raises TaskHintRejected (printed to stderr; exit 2) on policy violation.
    """
    if getattr(args, "task_file", None):
        return _load_from_file(args.task_file)
    if getattr(args, "task_hint", None):
        return _validate_inline_hint(args.task_hint)
    raise TaskHintRejected(
        "Either --task-file <path> or --task-hint <short-ascii> is required."
    )


def die_on_rejection(exc: TaskHintRejected, *, exit_code: int = 2) -> None:
    """Helper for scripts to print + exit cleanly."""
    print(f"[task-hint REJECTED] {exc}", file=sys.stderr)
    sys.exit(exit_code)
