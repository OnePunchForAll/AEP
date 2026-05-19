"""capture_operator_message_to_aepkg.py — operator directive 2026-05-16:
"let's start breaking down all of every single message i send into a separate
aep file dump (same rules initiates a new aep file dump folder after reaching
500 MB)".

Captures every operator message into:
  .claude/diana/operator-messages/dump-NNN/message-<seq>-<utc>.aepkg/

Folder rolls when dump-NNN reaches 500 MB.

the agent reads this dump FIRST before any execution (priority area per operator
directive).

Invoked by .claude/hooks/capture-operator-message.ps1 on UserPromptSubmit hook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path("C:/Users/example-user/")
DUMP_ROOT = REPO_ROOT / ".claude" / "diana" / "operator-messages"
DUMP_CAP_BYTES = 500 * 1024 * 1024  # 500 MB per dump folder


def dir_size_bytes(d: Path) -> int:
    """Recursive size of a directory in bytes."""
    if not d.exists():
        return 0
    total = 0
    for p in d.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def get_current_dump_dir() -> Path:
    """Find the active dump-NNN folder, rolling if cap exceeded."""
    DUMP_ROOT.mkdir(parents=True, exist_ok=True)
    existing = sorted([d for d in DUMP_ROOT.iterdir()
                       if d.is_dir() and d.name.startswith("dump-")])
    if not existing:
        new = DUMP_ROOT / "dump-001"
        new.mkdir(parents=True)
        return new
    current = existing[-1]
    if dir_size_bytes(current) >= DUMP_CAP_BYTES:
        # Roll to next
        next_num = int(current.name.split("-")[1]) + 1
        new = DUMP_ROOT / f"dump-{next_num:03d}"
        new.mkdir(parents=True)
        return new
    return current


def get_next_seq(dump_dir: Path) -> int:
    """Highest existing message-NNN in this dump + 1."""
    existing_seqs = []
    for p in dump_dir.iterdir():
        if p.is_dir() and p.name.startswith("message-"):
            try:
                seq = int(p.name.split("-")[1])
                existing_seqs.append(seq)
            except (ValueError, IndexError):
                continue
    if not existing_seqs:
        return 1
    return max(existing_seqs) + 1


def capture_message(content: str, session_id: str | None = None) -> Path:
    """Write the operator message as an AEP packet and return the packet path."""
    dump_dir = get_current_dump_dir()
    seq = get_next_seq(dump_dir)
    now = datetime.now(tz=timezone.utc)
    utc_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    utc_compact = now.strftime("%Y%m%dT%H%M%SZ")
    pkg_name = f"message-{seq:04d}-{utc_compact}.aepkg"
    pkg = dump_dir / pkg_name
    pkg.mkdir(parents=True)
    for sub in ("data", "ops", "reviews", "validations", "views", "assets"):
        (pkg / sub).mkdir()

    content_bytes = content.encode("utf-8")
    content_sha = hashlib.sha256(content_bytes).hexdigest()
    (pkg / "assets" / "raw.txt").write_bytes(content_bytes)
    (pkg / "assets" / "raw.sha256").write_text(content_sha + "\n",
                                                encoding="utf-8")

    source_rec = {
        "id": f"src:operator-message-{seq:04d}",
        "type": "Source",
        "source_type": "in_packet_file",
        "title": f"Operator message #{seq} ({utc_iso})",
        "location": {"kind": "file", "value": "./assets/raw.txt",
                     "location_hash": "sha256:" + content_sha},
        "provenance_strength": "strong",
        "limits": ["operator-authored verbatim; do not paraphrase"],
        "created_at": utc_iso,
    }
    (pkg / "data" / "sources.jsonl").write_text(
        json.dumps(source_rec, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    for f in ("spans.jsonl", "claims.jsonl", "relations.jsonl"):
        (pkg / "data" / f).write_text("", encoding="utf-8")
    (pkg / "ops" / "events.jsonl").write_text(
        json.dumps({
            "id": "evt:001", "type": "WriteEvent",
            "event_type": "operator_message_captured",
            "event_time": utc_iso,
            "actor": "capture_operator_message_to_aepkg.py",
            "target": "raw.txt",
            "session_id": session_id or "unknown",
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n")
    (pkg / "reviews" / "reviews.jsonl").write_text("", encoding="utf-8")
    (pkg / "validations" / "runs.jsonl").write_text("", encoding="utf-8")

    manifest = {
        "aep_version": "0.5",
        "profile": "aep:0.5/stable",
        "packet_id": f"aepkg:operator-message-{seq:04d}-{utc_compact}",
        "packet_epoch": 1,
        "title": f"Operator message #{seq} ({utc_iso})",
        "created_at": utc_iso,
        "created_by": "capture_operator_message_to_aepkg.py",
        "canonical_files": [
            "data/sources.jsonl", "data/spans.jsonl", "data/claims.jsonl",
            "data/relations.jsonl", "ops/events.jsonl",
            "reviews/reviews.jsonl", "validations/runs.jsonl",
        ],
        "extensions": {
            "message_sequence": seq,
            "dump_folder": dump_dir.name,
            "message_utc_iso": utc_iso,
            "content_sha256": "sha256:" + content_sha,
            "content_bytes": len(content_bytes),
            "session_id": session_id or "unknown",
            "priority_for_agent_read_before_execution": True,
        },
        "integrity": {
            "algorithm": "sha256-canonical-json-sorted-canonical-files",
            "state_hash": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "manifest_hash": "sha256:" + hashlib.sha256(b"").hexdigest(),
            "assets_merkle_root": "sha256:" + content_sha,
        },
    }
    (pkg / "aepkg.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    return pkg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--content-file", type=Path,
                    help="File containing the operator message verbatim. "
                         "If absent, reads from stdin.")
    ap.add_argument("--content", type=str, default=None,
                    help="Operator message as inline string (alternative to --content-file).")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--silent", action="store_true",
                    help="Suppress stdout (still writes the packet).")
    args = ap.parse_args()

    if args.content is not None:
        content = args.content
    elif args.content_file and args.content_file.exists():
        content = args.content_file.read_text(encoding="utf-8")
    else:
        content = sys.stdin.read()

    if not content.strip():
        if not args.silent:
            print("# Empty message; nothing captured.", file=sys.stderr)
        return 0

    pkg = capture_message(content, session_id=args.session_id)
    if not args.silent:
        print(f"Captured operator message to {pkg.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
