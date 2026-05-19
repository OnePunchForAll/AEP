#!/usr/bin/env python3
"""Inspect HCRL row 7 of v1.0.3 to find canonical DAG re-anchor structure."""
import json
from pathlib import Path

rows = [json.loads(l) for l in Path('.claude/_logs/aep-v103-phase-receipts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
for r in rows:
    if str(r.get('phase')) == '7':
        print('ROW_7_KEYS:', sorted(r.keys()))
        # Look for any field naming parents/anchors/predecessors
        for k in r:
            v = r[k]
            sv = json.dumps(v)[:120] if not isinstance(v, str) else v[:120]
            if any(token in k.lower() for token in ['anchor', 'parent', 'predec', 'chain', 'prior', 'sha', 'row', 'link', 'reanchor']):
                print(f"  {k} = {sv}")
        break
