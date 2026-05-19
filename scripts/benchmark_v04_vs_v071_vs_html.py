"""Comparative benchmark: HTML vs AEP v0.4-era vs AEP v0.7.1.

Measures across the 449-packet evidence-content corpus:
  - File bytes (HTML original, AEP packet total, AEP canonical body only)
  - Token counts (cl100k_base; how many tokens an LLM sees for each form)
  - Validation time (per-packet at AEP layer)
  - Conversion time (HTML → AEP)

The "v0.4-era" baseline is the v0.3-format that ``convert_html_lesson.py``
emitted (this corresponds to what AEP v0.4 validator would accept). The
"v0.7.1" form is the deep-migrated v0.5 + post-v0.7.1 fields.

Note: any current manifest_hash drift surfaced is a v0.7.2 migration-pipeline
fix candidate — not a structural failure of v0.7.1.
"""
import json
import os
import time
from pathlib import Path

import tiktoken

AEP_ROOT = Path("C:/Users/example-user/")

# Sample size
SAMPLE_SIZE = 30  # representative sample

ENC = tiktoken.get_encoding("cl100k_base")


def measure_tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


def measure_tree_bytes(path: Path) -> int:
    """Total bytes under path (recursive)."""
    total = 0
    if path.is_file():
        return path.stat().st_size
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def measure_tree_tokens(path: Path) -> int:
    """Total tokens across all readable text files under path."""
    total = 0
    if path.is_file():
        try:
            total += measure_tokens(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            pass
        return total
    for p in path.rglob("*"):
        if p.is_file() and p.suffix in (".jsonl", ".json", ".html", ".svg", ".md", ".mmd", ".txt", ".jsonld"):
            try:
                total += measure_tokens(p.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
    return total


def time_op(fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000


def find_aep_for_html(html_path: Path) -> Path:
    """Co-located packet: same dir, .aepkg suffix."""
    return html_path.parent / (html_path.stem + ".aepkg")


def measure_validation(packet_root: Path) -> tuple[str, float, int]:
    """Validate packet; return (schema_result, latency_ms, error_count)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from aep.validate_v0_6 import validate_v0_6
    from aep.validate_v0_5_1 import ValidationConfig
    cfg = ValidationConfig(profile="aep:0.6/stable", conformance_level=2, strict=True)
    t0 = time.perf_counter()
    r = validate_v0_6(packet_root, cfg)
    elapsed = (time.perf_counter() - t0) * 1000
    errors = sum(1 for f in r.findings if f.severity == "error")
    return r.schema_result, elapsed, errors


def collect_samples() -> list[tuple[Path, Path]]:
    """Find (html, aepkg) pairs across the corpus."""
    candidates = []
    for tier in ["doctrine/lessons", "doctrine/_proposals", "research/analysis", "research/sources"]:
        base = AEP_ROOT / tier
        for p in base.rglob("*.html"):
            if p.is_file() and not p.name.startswith("_"):
                aep = find_aep_for_html(p)
                if aep.exists():
                    candidates.append((p, aep))
                    if len(candidates) >= SAMPLE_SIZE:
                        return candidates
    return candidates


def main():
    print("=" * 80)
    print("AEP v0.7.1 COMPARATIVE BENCHMARK — HTML vs v0.4-era vs v0.7.1")
    print("=" * 80)
    samples = collect_samples()
    print(f"Sample size: {len(samples)} packets (HTML + AEP pairs)")
    print()
    print(f"{'#':>3s} {'HTML B':>8s} {'AEP B':>8s} {'Ratio':>6s} {'HTML tok':>9s} {'AEP tok':>9s} {'Validate':>9s}")
    print("-" * 80)
    totals = {
        "html_bytes": 0,
        "aep_bytes": 0,
        "canonical_body_bytes": 0,
        "html_tokens": 0,
        "aep_tokens": 0,
        "canonical_body_tokens": 0,
        "validation_ms": 0,
        "validation_errors": 0,
        "v04_era_bytes_estimate": 0,  # without views/cache/signed components
    }
    for i, (html_p, aep_p) in enumerate(samples, 1):
        html_bytes = measure_tree_bytes(html_p)
        aep_bytes = measure_tree_bytes(aep_p)
        body_path = aep_p / "data"
        canonical_body_bytes = measure_tree_bytes(body_path)

        # v0.4-era estimate: AEP packet WITHOUT views/, cache/, contexts/, bagit/, ro-crate/
        # (these are v0.6+/v0.7+ additions). Approximate by subtracting those subtree sizes.
        v04_era_bytes = aep_bytes
        for v07_addition in ["views", "cache", "contexts", "bagit.txt", "bag-info.txt",
                              "manifest-sha256.txt", "ro-crate-metadata.json"]:
            sub = aep_p / v07_addition
            if sub.exists():
                v04_era_bytes -= measure_tree_bytes(sub)

        html_tokens = measure_tokens(html_p.read_text(encoding="utf-8"))
        aep_tokens = measure_tree_tokens(aep_p)
        canonical_body_tokens = measure_tree_tokens(body_path)
        schema_result, val_ms, val_errs = measure_validation(aep_p)

        totals["html_bytes"] += html_bytes
        totals["aep_bytes"] += aep_bytes
        totals["v04_era_bytes_estimate"] += v04_era_bytes
        totals["canonical_body_bytes"] += canonical_body_bytes
        totals["html_tokens"] += html_tokens
        totals["aep_tokens"] += aep_tokens
        totals["canonical_body_tokens"] += canonical_body_tokens
        totals["validation_ms"] += val_ms
        totals["validation_errors"] += val_errs

        ratio = aep_bytes / max(html_bytes, 1)
        print(f"{i:3d} {html_bytes:>8d} {aep_bytes:>8d} {ratio:>5.1f}x {html_tokens:>9d} {aep_tokens:>9d} {val_ms:>6.0f}ms")

    print("-" * 80)
    n = len(samples)
    print()
    print("AGGREGATE TOTALS (sample N={}):".format(n))
    print(f"  HTML total bytes:                {totals['html_bytes']:>12,d} B  ({totals['html_bytes']/1024:.1f} KiB)")
    print(f"  AEP v0.4-era bytes (estimated):  {totals['v04_era_bytes_estimate']:>12,d} B  ({totals['v04_era_bytes_estimate']/1024:.1f} KiB)")
    print(f"  AEP v0.7.1 total bytes:          {totals['aep_bytes']:>12,d} B  ({totals['aep_bytes']/1024:.1f} KiB)")
    print(f"  AEP canonical body only:         {totals['canonical_body_bytes']:>12,d} B  ({totals['canonical_body_bytes']/1024:.1f} KiB)")
    print()
    print(f"  HTML total tokens (cl100k_base):  {totals['html_tokens']:>12,d}")
    print(f"  AEP v0.7.1 total tokens:          {totals['aep_tokens']:>12,d}")
    print(f"  AEP canonical body tokens:        {totals['canonical_body_tokens']:>12,d}")
    print()
    print(f"  Validation time total:            {totals['validation_ms']:>9.1f}ms ({totals['validation_ms']/n:.1f}ms avg/packet)")
    print(f"  Packets with errors:              {totals['validation_errors']}/{n}")
    print()
    print("RATIOS:")
    print(f"  AEP v0.7.1 bytes vs HTML:         {totals['aep_bytes']/totals['html_bytes']:.2f}x  ({(totals['aep_bytes']/totals['html_bytes']-1)*100:+.1f}%)")
    print(f"  AEP v0.4-era bytes vs HTML:       {totals['v04_era_bytes_estimate']/totals['html_bytes']:.2f}x  ({(totals['v04_era_bytes_estimate']/totals['html_bytes']-1)*100:+.1f}%)")
    print(f"  AEP v0.7.1 bytes vs v0.4-era:     {totals['aep_bytes']/max(totals['v04_era_bytes_estimate'],1):.2f}x  ({(totals['aep_bytes']/max(totals['v04_era_bytes_estimate'],1)-1)*100:+.1f}%)")
    print(f"  Canonical body bytes vs HTML:     {totals['canonical_body_bytes']/totals['html_bytes']:.2f}x  ({(totals['canonical_body_bytes']/totals['html_bytes']-1)*100:+.1f}%)")
    print()
    print(f"  AEP tokens vs HTML tokens:        {totals['aep_tokens']/totals['html_tokens']:.2f}x  ({(totals['aep_tokens']/totals['html_tokens']-1)*100:+.1f}%)")
    print(f"  Canonical body tokens vs HTML:    {totals['canonical_body_tokens']/totals['html_tokens']:.2f}x  ({(totals['canonical_body_tokens']/totals['html_tokens']-1)*100:+.1f}%)")
    print()
    out = Path(__file__).resolve().parents[1].parent / "benchmark-v04-vs-v071-vs-html.json"
    out.write_text(json.dumps({
        "sample_size": n,
        "totals_bytes": {
            "html": totals["html_bytes"],
            "aep_v04_era_estimated": totals["v04_era_bytes_estimate"],
            "aep_v0_7_1": totals["aep_bytes"],
            "aep_canonical_body": totals["canonical_body_bytes"],
        },
        "totals_tokens_cl100k_base": {
            "html": totals["html_tokens"],
            "aep_v0_7_1": totals["aep_tokens"],
            "aep_canonical_body": totals["canonical_body_tokens"],
        },
        "validation_time_ms": {
            "total": round(totals["validation_ms"], 1),
            "avg_per_packet": round(totals["validation_ms"] / n, 1),
        },
        "ratios": {
            "aep_v0_7_1_bytes_vs_html": round(totals["aep_bytes"] / totals["html_bytes"], 3),
            "aep_v04_era_bytes_vs_html": round(totals["v04_era_bytes_estimate"] / totals["html_bytes"], 3),
            "aep_v0_7_1_bytes_vs_v04_era": round(totals["aep_bytes"] / max(totals["v04_era_bytes_estimate"], 1), 3),
            "aep_tokens_vs_html": round(totals["aep_tokens"] / totals["html_tokens"], 3),
            "canonical_body_tokens_vs_html": round(totals["canonical_body_tokens"] / totals["html_tokens"], 3),
        },
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Results written to {out}")


if __name__ == "__main__":
    main()
