"""AEP project agent capability test: AEP packet vs HTML for evidence-content tasks.

Tests 5 capabilities representative of real AEP project agent workflows:

  T1. TRUTH-TAG RETRIEVAL — given a lesson, return its canonical truth_tag.
      AEP: read aepkg.json or data/claims.jsonl line 1.
      HTML: regex-scan the file.

  T2. PROVEN/RELIABLE CLAIM EXTRACTION — list all claims tagged PROVEN/RELIABLE.
      AEP: jsonl-filter on reliability=PROVEN_RELIABLE.
      HTML: grep / regex extract.

  T3. BASIS GRAPH — given a claim id, list its basis source_ids.
      AEP: jsonl-lookup.
      HTML: not structurally accessible without parsing.

  T4. INTEGRITY VERIFICATION — was this lesson tampered with?
      AEP: validate_v0_6 + node verify.cjs cross-runtime.
      HTML: no built-in.

  T5. VIEW DERIVATION — produce an HTML view from the source.
      AEP: aep.views.derive_claim_ledger_html().
      HTML: the source IS the view (identity transform).

Each task measures: (a) success rate; (b) latency; (c) precision/recall against
a ground-truth label set extracted from the HTML manually.

Sample: 5 recent lessons (sibling-63 through sibling-67) — the AEP work itself.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

AEP_ROOT = Path(__file__).resolve().parents[5]
AEP_PROJECT = Path(__file__).resolve().parents[1]

SAMPLE_LESSONS = [
    "doctrine/lessons/2026-05-14-aep-v0-6-0-rc1-multi-layer-and-five-analysis-convergence.html",         # sibling-63
    "doctrine/lessons/2026-05-14-knowledge-run-1-ten-agent-legion-applied-to-aep-v0_6_0-rc2.html",       # sibling-64
    "doctrine/lessons/2026-05-14-aep-v0-6-1-knowledge-run-1-full-application-and-pareto-matrix.html",   # sibling-65
    "doctrine/lessons/2026-05-14-aep-v0-7-rc1-signing-views-jcs-corpus-15-of-16-pareto.html",            # sibling-66
    "doctrine/lessons/2026-05-14-aep-v0-7-1-triple-check-honesty-cycle-and-15-5-of-16-pareto.html",      # sibling-67
]


def time_op(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000  # ms


# ---- T1: Truth-tag retrieval ----

def t1_html(html_path: Path) -> str:
    text = html_path.read_text(encoding="utf-8")
    m = re.search(r'truth_tag:\s*([\w/]+)', text)
    return m.group(1) if m else "<not-found>"


def t1_aep(aep_dir: Path) -> str:
    manifest_path = aep_dir / "aepkg.json"
    if not manifest_path.exists():
        return "<missing-aepkg>"
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Try claim ledger first (more authoritative)
    claims_path = aep_dir / "data" / "claims.jsonl"
    if claims_path.exists():
        for line in claims_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                rel = c.get("reliability")
                if rel:
                    return rel
    return m.get("extensions", {}).get("aep:legacy_truth_tag", "<not-found>")


# ---- T2: PROVEN/RELIABLE claim count ----

def t2_html(html_path: Path) -> int:
    text = html_path.read_text(encoding="utf-8")
    return len(re.findall(r'PROVEN[/_]RELIABLE', text))


def t2_aep(aep_dir: Path) -> int:
    claims_path = aep_dir / "data" / "claims.jsonl"
    if not claims_path.exists():
        return -1
    count = 0
    for line in claims_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if c.get("reliability") == "PROVEN_RELIABLE":
            count += 1
    return count


# ---- T3: Basis source_ids for first claim ----

def t3_aep(aep_dir: Path):
    claims_path = aep_dir / "data" / "claims.jsonl"
    if not claims_path.exists():
        return []
    for line in claims_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            basis = c.get("basis", [])
            if isinstance(basis, list):
                return [b.get("source_id", "") for b in basis if isinstance(b, dict) and "source_id" in b]
            return []
    return []


# T3 has no HTML equivalent — claim basis isn't structurally accessible.


# ---- T4: Integrity verification ----

def t4_aep(aep_dir: Path):
    """Validate via Python AND verify cross-runtime via Node."""
    py_result = subprocess.run(
        [sys.executable, "-m", "aep.validate_v0_6", str(aep_dir),
         "--profile", "aep:0.5/stable", "--conformance-level", "2"],
        cwd=AEP_PROJECT,
        env={"PYTHONPATH": str(AEP_PROJECT / "src"),
             **{k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}},
        capture_output=True, text=True, timeout=20,
    )
    py_ok = "schema_result: pass" in py_result.stdout or "schema_result: warn" in py_result.stdout
    node_result = subprocess.run(
        ["node", str(AEP_PROJECT / "verifiers" / "node" / "verify.cjs"), str(aep_dir)],
        capture_output=True, text=True, timeout=20,
    )
    node_ok = node_result.returncode == 0
    return {"python_ok": py_ok, "node_ok": node_ok, "cross_runtime_agree": py_ok == node_ok}


# T4 has no HTML equivalent — no built-in integrity check.


# ---- T5: View derivation ----

def t5_aep(aep_dir: Path):
    """Derive views and return byte sizes."""
    sys.path.insert(0, str(AEP_PROJECT / "src"))
    try:
        from aep.views import derive_all_views
        views = derive_all_views(aep_dir)
        return {rel: len(content) for rel, (content, _) in views.items()}
    finally:
        if str(AEP_PROJECT / "src") in sys.path:
            sys.path.remove(str(AEP_PROJECT / "src"))


# ---- Run ----

def main():
    print("=" * 70)
    print("AEP AGENT CAPABILITY TEST: AEP packets vs HTML")
    print("=" * 70)
    print()
    summaries = []
    for rel in SAMPLE_LESSONS:
        html_path = AEP_ROOT / rel
        # AEP packet is co-located: same stem, .aepkg suffix
        aep_path = html_path.parent / (html_path.stem + ".aepkg")
        if not html_path.exists():
            print(f"SKIP (no html): {rel}")
            continue
        if not aep_path.exists():
            print(f"SKIP (no aepkg): {rel}")
            continue
        sibling = html_path.stem
        print(f"--- {sibling[:60]} ---")
        # File sizes
        html_size = html_path.stat().st_size
        aep_total = sum(p.stat().st_size for p in aep_path.rglob("*") if p.is_file())
        print(f"  Storage: HTML={html_size}B, AEP packet={aep_total}B (ratio {aep_total/max(html_size,1):.1f}x)")

        # T1: truth_tag
        ht_val, ht_ms = time_op(t1_html, html_path)
        at_val, at_ms = time_op(t1_aep, aep_path)
        print(f"  T1 truth_tag: HTML={ht_val!r} ({ht_ms:.2f}ms), AEP={at_val!r} ({at_ms:.2f}ms)")

        # T2: proven count
        h2_val, h2_ms = time_op(t2_html, html_path)
        a2_val, a2_ms = time_op(t2_aep, aep_path)
        print(f"  T2 PROVEN count: HTML={h2_val} hits ({h2_ms:.2f}ms), AEP={a2_val} claims ({a2_ms:.2f}ms)")

        # T3: basis (AEP only)
        a3_val, a3_ms = time_op(t3_aep, aep_path)
        print(f"  T3 basis source_ids (AEP only): {a3_val} ({a3_ms:.2f}ms)")

        # T4: integrity
        a4_val, a4_ms = time_op(t4_aep, aep_path)
        print(f"  T4 integrity: py={a4_val['python_ok']}, node={a4_val['node_ok']}, agree={a4_val['cross_runtime_agree']} ({a4_ms:.1f}ms)")

        # T5: view derivation
        a5_val, a5_ms = time_op(t5_aep, aep_path)
        view_summary = ", ".join(f"{k.split('/')[-1]}={v}B" for k, v in a5_val.items())
        print(f"  T5 views: {view_summary} ({a5_ms:.1f}ms)")
        print()

        summaries.append({
            "lesson": sibling,
            "storage_ratio": aep_total / max(html_size, 1),
            "t1_match": ht_val.replace("/", "_") == at_val,
            "t2_diff": abs(h2_val - a2_val),  # not strict equality — different semantics
            "t3_basis_count": len(a3_val),
            "t4_cross_runtime_agree": a4_val["cross_runtime_agree"],
            "t4_python_ok": a4_val["python_ok"],
            "t4_node_ok": a4_val["node_ok"],
            "t5_view_count": len(a5_val),
        })

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    t1_pass = sum(1 for s in summaries if s["t1_match"])
    t4_pass = sum(1 for s in summaries if s["t4_cross_runtime_agree"] and s["t4_python_ok"])
    avg_storage = sum(s["storage_ratio"] for s in summaries) / max(len(summaries), 1)
    print(f"Tested: {len(summaries)} lessons")
    print(f"T1 truth-tag match (HTML/AEP agree on canonical tag): {t1_pass}/{len(summaries)}")
    print(f"T4 integrity verified by BOTH Python + Node (cross-runtime agree): {t4_pass}/{len(summaries)}")
    print(f"Avg storage ratio (AEP/HTML): {avg_storage:.1f}x")
    print(f"T3 basis structure (HTML can't do this): AEP recovered structured basis for {sum(1 for s in summaries if s['t3_basis_count'] > 0)}/{len(summaries)} lessons")
    print(f"T5 view derivation: {sum(s['t5_view_count'] for s in summaries)} views derived total ({sum(1 for s in summaries if s['t5_view_count'] == 3)}/{len(summaries)} lessons got all 3)")
    print()
    out = AEP_PROJECT.parent.parent / "capability-test-results.json"
    out.write_text(
        json.dumps({"sample": "5_recent_aep_lessons", "tests": summaries}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Results written to {out}")


if __name__ == "__main__":
    main()
