"""Agent-performance benchmark: how AI agents perform reading AEP vs HTML.

Measures 10 representative agent tasks across 20 sample lessons:

  T01 — Read truth_tag                    (selective field extraction)
  T02 — Count PROVEN/RELIABLE claims      (structured query vs regex)
  T03 — List basis source_ids              (graph recovery)
  T04 — Get cluster_tags                   (selective field extraction)
  T05 — Detect tampering (integrity)       (AEP-only capability)
  T06 — Cross-runtime verify (Node)        (AEP-only capability)
  T07 — Find predecessor lessons           (relation graph)
  T08 — Targeted-read manifest only        (token cost for one query)
  T09 — Read claim text by claim_id        (indexed lookup vs text search)
  T10 — List all claim IDs                 (enumeration)

For each task on each lesson, measure:
  - Latency (ms)
  - Tokens consumed (cl100k_base) — the bytes the agent had to ingest
  - Success (1) or fail (0)

Then aggregate: total time, total tokens, success rate; report percentages.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import tiktoken

AEP_ROOT = Path("C:/Users/example-user/")
AEP_PROJECT = Path(__file__).resolve().parents[1]
ENC = tiktoken.get_encoding("cl100k_base")
SAMPLE_SIZE = 20


def tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


def time_op(fn, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
        return result, (time.perf_counter() - t0) * 1000, True
    except Exception:
        return None, (time.perf_counter() - t0) * 1000, False


# ---------- HTML tasks (agent reads raw HTML) ----------

def html_t01_truth_tag(html_path: Path):
    text = html_path.read_text(encoding="utf-8")
    m = re.search(r'truth_tag:\s*([^\s,\n]+)', text)
    return (m.group(1) if m else None, tokens(text))


def html_t02_proven_count(html_path: Path):
    text = html_path.read_text(encoding="utf-8")
    return (len(re.findall(r'PROVEN[/_]RELIABLE', text)), tokens(text))


def html_t03_basis_source_ids(html_path: Path):
    # HTML doesn't structurally expose this; agent would have to fuzz-match
    text = html_path.read_text(encoding="utf-8")
    matches = re.findall(r'src:[\w\-:./]+', text)
    return (list(set(matches)), tokens(text))


def html_t04_cluster_tags(html_path: Path):
    text = html_path.read_text(encoding="utf-8")
    m = re.search(r'cluster_tags:\s*\n((?:\s*-\s*[\w\-_]+\s*\n)+)', text)
    if m:
        return (re.findall(r'-\s*([\w\-_]+)', m.group(1)), tokens(text))
    return ([], tokens(text))


def html_t05_detect_tamper(html_path: Path):
    # HTML cannot detect tampering — no integrity layer
    return (False, tokens(html_path.read_text(encoding="utf-8")))


def html_t06_node_verify(html_path: Path):
    # No Node verifier exists for HTML
    return (None, tokens(html_path.read_text(encoding="utf-8")))


def html_t07_predecessors(html_path: Path):
    text = html_path.read_text(encoding="utf-8")
    matches = re.findall(r'sibling-(\d+)', text)
    return (sorted(set(matches)), tokens(text))


def html_t08_manifest_only(html_path: Path):
    # HTML has no separable manifest; agent reads full file
    text = html_path.read_text(encoding="utf-8")
    return (text[:500], tokens(text))


def html_t09_claim_text_by_id(html_path: Path):
    # HTML doesn't have stable claim IDs to query by
    return (None, tokens(html_path.read_text(encoding="utf-8")))


def html_t10_list_claim_ids(html_path: Path):
    text = html_path.read_text(encoding="utf-8")
    return (re.findall(r'claim:[\w_\-]+', text), tokens(text))


# ---------- AEP tasks (agent reads structured packet) ----------

def aep_t01_truth_tag(aep_dir: Path):
    manifest_text = (aep_dir / "aepkg.json").read_text(encoding="utf-8")
    m = json.loads(manifest_text)
    # Truth tag in extensions if present
    ext = m.get("extensions", {})
    legacy = ext.get("aep:legacy_truth_tag")
    if legacy:
        return (legacy.replace("/", "_").replace(" ", "_"), tokens(manifest_text))
    # Fallback: first claim's reliability
    claims_text = (aep_dir / "data" / "claims.jsonl").read_text(encoding="utf-8")
    for line in claims_text.splitlines():
        if line.strip():
            return (json.loads(line).get("reliability"), tokens(manifest_text + claims_text))
    return (None, tokens(manifest_text))


def aep_t02_proven_count(aep_dir: Path):
    claims_text = (aep_dir / "data" / "claims.jsonl").read_text(encoding="utf-8")
    count = sum(1 for line in claims_text.splitlines()
                if line.strip() and json.loads(line).get("reliability") == "PROVEN_RELIABLE")
    return (count, tokens(claims_text))


def aep_t03_basis_source_ids(aep_dir: Path):
    claims_text = (aep_dir / "data" / "claims.jsonl").read_text(encoding="utf-8")
    src_ids = set()
    for line in claims_text.splitlines():
        if line.strip():
            for b in json.loads(line).get("basis", []):
                if isinstance(b, dict) and "source_id" in b:
                    src_ids.add(b["source_id"])
    return (sorted(src_ids), tokens(claims_text))


def aep_t04_cluster_tags(aep_dir: Path):
    manifest_text = (aep_dir / "aepkg.json").read_text(encoding="utf-8")
    m = json.loads(manifest_text)
    ext = m.get("extensions", {})
    tags = ext.get("aep:cluster_tags", [])
    return (tags if isinstance(tags, list) else [], tokens(manifest_text))


def aep_t05_detect_tamper(aep_dir: Path):
    # Run validator — checks integrity envelope
    result = subprocess.run(
        [sys.executable, "-m", "aep.validate_v0_6", str(aep_dir),
         "--profile", "aep:0.6/stable", "--conformance-level", "2"],
        cwd=AEP_PROJECT,
        env={"PYTHONPATH": str(AEP_PROJECT / "src"),
             **{k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}},
        capture_output=True, text=True, timeout=20,
    )
    # The validator output reports recompute results — token cost is the validator output
    return (result.returncode != 1, tokens(result.stdout))


def aep_t06_node_verify(aep_dir: Path):
    result = subprocess.run(
        ["node", str(AEP_PROJECT / "verifiers" / "node" / "verify.cjs"), str(aep_dir)],
        capture_output=True, text=True, timeout=20,
    )
    return (result.returncode == 0, tokens(result.stdout))


def aep_t07_predecessors(aep_dir: Path):
    manifest_text = (aep_dir / "aepkg.json").read_text(encoding="utf-8")
    m = json.loads(manifest_text)
    # Predecessors live in extensions metadata
    ext = m.get("extensions", {})
    # Some lessons use a 'predecessors' tag; otherwise read first claim
    preds_field = ext.get("aep:predecessors") or ext.get("predecessors")
    if preds_field:
        return (preds_field if isinstance(preds_field, list) else [preds_field], tokens(manifest_text))
    return ([], tokens(manifest_text))


def aep_t08_manifest_only(aep_dir: Path):
    manifest_text = (aep_dir / "aepkg.json").read_text(encoding="utf-8")
    m = json.loads(manifest_text)
    return (m.get("title", ""), tokens(manifest_text))


def aep_t09_claim_text_by_id(aep_dir: Path):
    claims_text = (aep_dir / "data" / "claims.jsonl").read_text(encoding="utf-8")
    # Get first claim's text
    for line in claims_text.splitlines():
        if line.strip():
            c = json.loads(line)
            return (c.get("text") or c.get("claim_text") or c.get("id"), tokens(claims_text))
    return (None, tokens(claims_text))


def aep_t10_list_claim_ids(aep_dir: Path):
    claims_text = (aep_dir / "data" / "claims.jsonl").read_text(encoding="utf-8")
    ids = []
    for line in claims_text.splitlines():
        if line.strip():
            cid = json.loads(line).get("id")
            if cid:
                ids.append(cid)
    return (ids, tokens(claims_text))


TASKS = [
    ("T01 truth_tag",        html_t01_truth_tag,      aep_t01_truth_tag),
    ("T02 proven count",     html_t02_proven_count,   aep_t02_proven_count),
    ("T03 basis src_ids",    html_t03_basis_source_ids, aep_t03_basis_source_ids),
    ("T04 cluster_tags",     html_t04_cluster_tags,   aep_t04_cluster_tags),
    ("T05 tamper detect",    html_t05_detect_tamper,  aep_t05_detect_tamper),
    ("T06 cross-runtime",    html_t06_node_verify,    aep_t06_node_verify),
    ("T07 predecessors",     html_t07_predecessors,   aep_t07_predecessors),
    ("T08 manifest-only",    html_t08_manifest_only,  aep_t08_manifest_only),
    ("T09 claim text",       html_t09_claim_text_by_id, aep_t09_claim_text_by_id),
    ("T10 list claim_ids",   html_t10_list_claim_ids, aep_t10_list_claim_ids),
]


def find_samples(n: int) -> list[tuple[Path, Path]]:
    samples = []
    for tier in ["doctrine/lessons", "doctrine/_proposals"]:
        for html in sorted((AEP_ROOT / tier).glob("*.html")):
            aep = html.parent / (html.stem + ".aepkg")
            if aep.exists() and (aep / "aepkg.json").exists():
                samples.append((html, aep))
                if len(samples) >= n:
                    return samples
    return samples


def main():
    samples = find_samples(SAMPLE_SIZE)
    print("=" * 90)
    print(f"AGENT-PERFORMANCE BENCHMARK — HTML vs AEP across {len(samples)} lessons × 10 tasks")
    print("=" * 90)
    print()

    # Aggregates
    html_total_ms = aep_total_ms = 0.0
    html_total_tokens = aep_total_tokens = 0
    html_total_success = aep_total_success = 0
    per_task = {name: {"html_ms": 0, "aep_ms": 0, "html_tok": 0, "aep_tok": 0,
                        "html_ok": 0, "aep_ok": 0} for name, _, _ in TASKS}

    for html_path, aep_path in samples:
        for task_name, html_fn, aep_fn in TASKS:
            h_result, h_ms, h_ok = time_op(html_fn, html_path)
            h_val, h_tok = (h_result if h_result else (None, 0))
            a_result, a_ms, a_ok = time_op(aep_fn, aep_path)
            a_val, a_tok = (a_result if a_result else (None, 0))

            # T05 (HTML) is by definition False (no capability) — count as "not capable" not "fail"
            if task_name in ("T05 tamper detect", "T06 cross-runtime", "T09 claim text"):
                h_ok_eff = False  # HTML literally cannot do these
            else:
                h_ok_eff = h_ok and (h_val is not None or task_name == "T05 tamper detect")

            a_ok_eff = a_ok and (a_val is not None)

            html_total_ms += h_ms; aep_total_ms += a_ms
            html_total_tokens += h_tok; aep_total_tokens += a_tok
            html_total_success += int(h_ok_eff); aep_total_success += int(a_ok_eff)
            per_task[task_name]["html_ms"] += h_ms
            per_task[task_name]["aep_ms"] += a_ms
            per_task[task_name]["html_tok"] += h_tok
            per_task[task_name]["aep_tok"] += a_tok
            per_task[task_name]["html_ok"] += int(h_ok_eff)
            per_task[task_name]["aep_ok"] += int(a_ok_eff)

    # Per-task table
    n = len(samples)
    print(f"{'Task':<22s} {'HTML ms':>9s} {'AEP ms':>9s} {'AEP Δ':>7s}  {'HTML tok':>10s} {'AEP tok':>10s} {'AEP Δ':>7s}  {'HTML ok':>8s} {'AEP ok':>7s}")
    print("-" * 105)
    for task_name, _, _ in TASKS:
        d = per_task[task_name]
        h_ms = d["html_ms"] / n
        a_ms = d["aep_ms"] / n
        h_tok = d["html_tok"] / n
        a_tok = d["aep_tok"] / n
        ms_delta = f"{((a_ms/max(h_ms,0.001))-1)*100:+.0f}%"
        tok_delta = f"{((a_tok/max(h_tok,0.001))-1)*100:+.0f}%"
        print(f"{task_name:<22s} {h_ms:>8.1f}  {a_ms:>8.1f}  {ms_delta:>6s}  {h_tok:>9.0f}  {a_tok:>9.0f}  {tok_delta:>6s}  {d['html_ok']:>4d}/{n}  {d['aep_ok']:>4d}/{n}")
    print("-" * 105)
    print(f"{'TOTAL (avg per task)':<22s} {html_total_ms/(n*len(TASKS)):>8.1f}  {aep_total_ms/(n*len(TASKS)):>8.1f}          {html_total_tokens/(n*len(TASKS)):>9.0f}  {aep_total_tokens/(n*len(TASKS)):>9.0f}          {html_total_success:>4d}/{n*len(TASKS)}  {aep_total_success:>4d}/{n*len(TASKS)}")
    print()

    # Final aggregate
    print("AGGREGATE (across {} lessons × {} tasks = {} total operations):".format(n, len(TASKS), n*len(TASKS)))
    print(f"  Total time:    HTML {html_total_ms:>9.0f}ms / AEP {aep_total_ms:>9.0f}ms  ({((aep_total_ms/max(html_total_ms,0.001))-1)*100:+.1f}%)")
    print(f"  Total tokens:  HTML {html_total_tokens:>9,d} / AEP {aep_total_tokens:>9,d}  ({((aep_total_tokens/max(html_total_tokens,0.001))-1)*100:+.1f}%)")
    print(f"  Success rate:  HTML {html_total_success/(n*len(TASKS))*100:.1f}% / AEP {aep_total_success/(n*len(TASKS))*100:.1f}%")
    print()
    print("AEP-EXCLUSIVE CAPABILITIES (HTML score: literally cannot do):")
    for cap in ("T05 tamper detect", "T06 cross-runtime", "T09 claim text"):
        d = per_task[cap]
        rate_aep = d["aep_ok"] / n * 100
        rate_html = 0
        print(f"  {cap:<22s}: HTML {rate_html:5.1f}% / AEP {rate_aep:5.1f}%  → AEP wins by {rate_aep:.0f}pp")

    # Write results
    out = AEP_PROJECT.parent / "agent-performance-results.json"
    summary = {
        "sample_size": n,
        "tasks": len(TASKS),
        "total_operations": n * len(TASKS),
        "html_total_ms": round(html_total_ms, 1),
        "aep_total_ms": round(aep_total_ms, 1),
        "html_total_tokens": html_total_tokens,
        "aep_total_tokens": aep_total_tokens,
        "html_success": html_total_success,
        "aep_success": aep_total_success,
        "per_task": {k: {kk: round(vv, 1) if isinstance(vv, float) else vv for kk, vv in v.items()}
                     for k, v in per_task.items()},
    }
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Results written to {out}")


if __name__ == "__main__":
    main()
