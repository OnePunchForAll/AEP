"""jcs_canonical_check.py — Loop 5 disconfirmer: Python vs Node.js canonical-bytes check.

GOAL (operator directive 2026-05-15 loops-5-8 ladder lamport-63):
  Cheapest disconfirmer for "is RFC 8785 JCS binding LOAD-BEARING for the
  lamport-null content-addressable identity, or is the current Python spec
  accidentally JCS-compliant?"

METHOD:
  1. Pick a sample ledger row (forge.lamport-209 — the canonical sibling-78
     spec row; non-ASCII fields exercised via cluster_tags & notes).
  2. Compute canonical bytes via the LIVE Python spec
     (`compute_null_lamport_token` / `canonical_row_bytes` from
     lamport_null_fallback.py).
  3. Write Python canonical bytes to tmp/jcs_test/python_canonical.bytes.
  4. Generate a Node.js script tmp/jcs_test/node_canonical.cjs that
     re-implements the spec INDEPENDENTLY using JSON.stringify with a
     sort-keys recursion (the Python spec's contract: sort_keys=True,
     separators=(',',':'), ensure_ascii=False, .encode('utf-8')).
  5. Run Node, capture node_canonical.bytes.
  6. SHA-256 + diff both files.
  7. Verdict:
       BYTE-IDENTICAL → JCS-binding NOT LOAD-BEARING; current spec is
                        accidentally cross-runtime-compatible for this row.
                        (Caveat: single-row test does not cover all RFC 8785
                        edge cases — number serialization, unicode normalization,
                        nested objects.)
       BYTE-DIFFERENT → JCS-binding IS LOAD-BEARING; without an explicit
                        binding, agents on Node runtimes will compute
                        different lamport-null tokens than agents on Python
                        runtimes.

USAGE:
  python jcs_canonical_check.py
    [--ledger ../../../.claude/agents/_ledgers/forge.jsonl]
    [--row-index 212]   # 0-indexed; lamport-209 is at line 213 → row index 212
    [--tmp-dir ./tmp/jcs_test]

OUTPUT:
  Prints SHA-256 hex + diff status to stdout.
  Exits 0 on BYTE-IDENTICAL, 1 on BYTE-DIFFERENT, 2 on harness error.

Truth tag: STRONGLY PLAUSIBLE (single-row test; broader edge-case coverage
deferred to a follow-on RFC 8785 conformance battery).

Cites:
  pathfinder.lamport-null-bcdc549e4ace::loops-5-8-dependency-ordered-ladder
  scout.lamport-null-9ef4b6577f6b::rfc-8785-adjacency-invalidator
  scribe.lamport-80::sibling-83-closure-surge-backfill (sibling-78 lineage)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Local import — sibling script
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from lamport_null_fallback import canonical_row_bytes, compute_null_lamport_token  # noqa: E402


def _load_row(ledger_path: Path, row_index: int) -> dict:
    rows = []
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if row_index < 0 or row_index >= len(rows):
        raise IndexError(
            f"row_index {row_index} out of range; ledger has {len(rows)} rows"
        )
    return rows[row_index]


# Node.js script template — independent re-implementation of the Python
# canonical-bytes contract. This script READS the row JSON from a sidecar
# file (so we control input bytes precisely) and writes canonical bytes to
# the supplied output path.
NODE_SCRIPT_TEMPLATE = r"""// node_canonical.cjs — independent re-impl of the Python canonical-bytes contract.
// Contract under test: sort_keys=True, separators=(',',':'), ensure_ascii=False, UTF-8.
// This implements the contract in vanilla Node JS WITHOUT pulling canonical-json
// as a dep — the question is whether vanilla JSON.stringify + a sort-keys recursion
// matches the Python serializer byte-for-byte.

const fs = require('fs');
const path = require('path');

if (process.argv.length < 4) {
  console.error('usage: node node_canonical.cjs <input-row-json> <output-bytes>');
  process.exit(2);
}

const inputPath = process.argv[2];
const outputPath = process.argv[3];

// Load the row.
const raw = fs.readFileSync(inputPath, 'utf8');
const row = JSON.parse(raw);

// Recursive sort-keys serializer — mimics Python json.dumps(..., sort_keys=True,
// separators=(',',':'), ensure_ascii=False).
function canonicalize(value) {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    // Python repr for ints + floats. JS Number.prototype.toString() is *similar*
    // but not byte-identical for many edge cases (e.g. 1e21, -0). For the row
    // under test (lamport_counter:209), this is an int so they match.
    if (Number.isInteger(value)) return value.toString();
    // For floats, JS uses 'shortest round-trip' which differs from Python's
    // repr for some values. Documented divergence point.
    return value.toString();
  }
  if (typeof value === 'string') {
    // JSON.stringify implements ensure_ascii=False semantics by default
    // (it does NOT escape non-ASCII characters).
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalize).join(',') + ']';
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort();
    const parts = keys.map(function (k) {
      return JSON.stringify(k) + ':' + canonicalize(value[k]);
    });
    return '{' + parts.join(',') + '}';
  }
  throw new Error('unsupported type: ' + typeof value);
}

const canonical = canonicalize(row);
fs.writeFileSync(outputPath, canonical, { encoding: 'utf8' });
process.stderr.write('node canonical bytes written: ' + Buffer.byteLength(canonical, 'utf8') + ' bytes\n');
"""


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--ledger",
        type=Path,
        default=Path(__file__).resolve().parents[5]
        / ".claude" / "agents" / "_ledgers" / "forge.jsonl",
        help="Path to ledger jsonl (default: aepkit/.claude/agents/_ledgers/forge.jsonl)",
    )
    ap.add_argument(
        "--row-index",
        type=int,
        default=211,
        help="Zero-based row index (forge lamport-209 is at file line 213 → 0-indexed 212; the loader skips blank lines so it lands at 211 in some cases — pass --row-index to override)",
    )
    ap.add_argument(
        "--tmp-dir",
        type=Path,
        default=SCRIPT_DIR.parent / "tmp" / "jcs_test",
        help="Sidecar file output directory",
    )
    args = ap.parse_args()

    if not args.ledger.exists():
        print(f"ERROR: ledger not found: {args.ledger}", file=sys.stderr)
        return 2

    args.tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load sample row.
    row = _load_row(args.ledger, args.row_index)
    print(f"Loaded row {args.row_index}: invocation={row.get('invocation', '<no-inv>')[:60]}")
    print(f"  lamport_counter={row.get('lamport_counter')!r}")
    print(f"  cluster_tags count={len(row.get('cluster_tags', []))}")
    print(f"  cites count={len(row.get('cites', []))}")

    # 2. Python canonical bytes.
    py_bytes = canonical_row_bytes(row)
    py_path = args.tmp_dir / "python_canonical.bytes"
    py_path.write_bytes(py_bytes)
    py_token = compute_null_lamport_token(row)
    py_sha = sha256_hex(py_bytes)
    print(f"\n[PY] bytes={len(py_bytes)} sha256={py_sha} token={py_token}")

    # 3. Write Node script + input row.
    node_js_path = args.tmp_dir / "node_canonical.cjs"
    node_js_path.write_text(NODE_SCRIPT_TEMPLATE, encoding="utf-8")

    # Feed the row to Node as a JSON file. We use the SAME canonical bytes as
    # input so Node parses an identical AST regardless of original whitespace.
    # (We could feed raw line, but Python's json.loads + json.dumps round-trip
    # would already normalize; the test isn't about parser drift, it's about
    # serializer drift.)
    node_input_path = args.tmp_dir / "row_input.json"
    node_input_path.write_bytes(py_bytes)

    node_out_path = args.tmp_dir / "node_canonical.bytes"

    # 4. Run Node.
    node_exe = shutil.which("node") or shutil.which("node.exe")
    if not node_exe:
        print("ERROR: node executable not found on PATH", file=sys.stderr)
        return 2

    proc = subprocess.run(
        [node_exe, str(node_js_path), str(node_input_path), str(node_out_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"ERROR: node failed (exit {proc.returncode})\nstderr:\n{proc.stderr}",
              file=sys.stderr)
        return 2
    if proc.stderr:
        print(f"  [node stderr] {proc.stderr.strip()}")

    # 5. Compare.
    node_bytes = node_out_path.read_bytes()
    node_sha = sha256_hex(node_bytes)
    print(f"[JS] bytes={len(node_bytes)} sha256={node_sha}")

    print()
    if py_sha == node_sha:
        print("VERDICT: BYTE-IDENTICAL (Python ≡ Node for this row)")
        print("  → Current spec is accidentally cross-runtime-compatible for this input.")
        print("  → JCS binding NOT load-bearing for this single-row test.")
        print("  → CAVEAT: single row does not exercise RFC 8785 edge cases:")
        print("      * floating-point number serialization (Python repr vs JS toString)")
        print("      * unicode normalization NFC vs NFD (RFC 8785 §3.2.5)")
        print("      * negative-zero -0.0")
        print("      * surrogate-pair handling")
        print("      * very large numbers (Python arbitrary-prec int vs JS Number)")
        print("  → Recommendation: build a corpus of 10-20 edge-case rows; if ANY")
        print("    diverge, JCS binding becomes load-bearing.")
        return 0
    else:
        print("VERDICT: BYTE-DIFFERENT (Python ≠ Node for this row)")
        print(f"  Python SHA: {py_sha}")
        print(f"  Node   SHA: {node_sha}")
        # Find first divergent byte for diagnostics.
        for i, (a, b) in enumerate(zip(py_bytes, node_bytes)):
            if a != b:
                ctx_lo = max(0, i - 20)
                ctx_hi = min(len(py_bytes), i + 20)
                print(f"  First diff at byte {i}:")
                print(f"    py: ...{py_bytes[ctx_lo:ctx_hi]!r}...")
                print(f"    js: ...{node_bytes[ctx_lo:ctx_hi]!r}...")
                break
        else:
            if len(py_bytes) != len(node_bytes):
                print(f"  Length differs: py={len(py_bytes)} js={len(node_bytes)}")
        print("  → JCS binding IS LOAD-BEARING — without an explicit canonical-")
        print("    JSON binding, agents on Node runtimes compute different lamport-")
        print("    null tokens than agents on Python runtimes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
