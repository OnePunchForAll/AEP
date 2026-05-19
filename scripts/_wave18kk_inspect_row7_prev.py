#!/usr/bin/env python3
"""Find the DAG re-anchor pattern in v1.0.3 HCRL: row 7's prev_receipt_hash structure."""
import json
from pathlib import Path

rows = [json.loads(l) for l in Path('.claude/_logs/aep-v103-phase-receipts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
# Get row 5, 6, 7 prev_receipt_hash values
for r in rows:
    ph = str(r.get('phase'))
    if ph in ('5', '6', '7', '8', '8a', '8b', '9', '10a', '10b', '10c'):
        prev = r.get('prev_receipt_hash')
        prev_disp = json.dumps(prev) if not isinstance(prev, str) else prev[:80]
        sha = r.get('row_sha256', '')[:16] if isinstance(r.get('row_sha256'), str) else 'NA'
        print(f"phase={ph:6} sha={sha:18} prev={prev_disp}")
