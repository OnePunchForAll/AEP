"""falsifier_meta_validate.py — Falsifier Meta-Validation (FMV) scanner.

Scans a falsifier script for known bias patterns that produce inflated PASS
verdicts. Catches the kind of structural flaw judge identified manually on F2
(tag-token leakage 90.2% → 84.7% honest) BEFORE the falsifier ships.

Known bias patterns this scanner catches (load-bearing):
  BP-1 LOOK-AHEAD-BIAS: query/corpus derived from same row whose
       outcome the auto-label evaluates.
  BP-2 SAME-TOKENS-WIN-TWICE: tokens that drive retrieval (e.g., cluster_tags)
       are ALSO used by the auto-label (e.g., cluster_tag set intersection).
  BP-3 ANCHOR-POOL-SIZE-CONFOUND: P@N gate where N is small but anchor pool
       per probe is ≥ corpus_size * 0.5 (P@N=1.0 is random-baseline).
  BP-4 TAUTOLOGICAL-PASS: PASS criterion is satisfiable by accident (e.g.,
       `not (A and C)` PASSes if EITHER is excluded for unrelated reasons).
  BP-5 THRESHOLD-FLOOR-DRIFT: critical floor (cosine ≥ X, p-value ≤ Y)
       removed/lowered after empirical observation without documented
       justification (silent recalibration to match data, not vice versa).
  BP-6 MANUFACTURED-BASELINE: PASS threshold computed FROM the same sample
       that's being evaluated (no holdout).
  BP-7 SCOPE-LAUNDERING: SYNTHETIC verdict produced + missing explicit
       SYNTHETIC- prefix in output.

Output: per-falsifier meta-receipt at .claude/_logs/fmv-receipts.jsonl with
WARN/BLOCK findings, score, and recommended remediation.

This pattern itself is the doctrine slot §55 candidate. Born from judge's
operator-double #2 meta-validation 2026-05-15 that caught the F2 leakage.

Usage:
    python falsifier_meta_validate.py --falsifier <path>
    python falsifier_meta_validate.py --scan-all  # scan all falsifier_*.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def b2(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8"), digest_size=32).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# Bias pattern detectors
def detect_bp1_lookahead(src: str) -> List[Dict]:
    """LOOK-AHEAD-BIAS: query vector built from the SAME row whose outcome the
    label evaluates. Heuristic: look for `target.invocation` (or similar)
    appearing in BOTH the query construction AND the label computation."""
    findings = []
    # Heuristic: presence of `target_row` + `target.invocation` + label evaluation
    # in close proximity without an explicit "exclude self" or "leave-one-out" guard.
    if re.search(r"target[._]?(invocation|tags|notes)", src) and \
       re.search(r"(label|relevant|anchors)", src):
        # Tighten leave-one-out detection: includes slicing patterns + range-based exclusion
        has_loo = bool(re.search(
            r"leave[\-_]one[\-_]out|exclude.*target|drop.*probe|"
            r"prior\s*=\s*rows\[:\s*i\s*\]|"  # rows[:i] slice (back-test in time order)
            r"\bif\s+r\[.vec_id.\]\s*==\s*probe_vec_id\b|"  # explicit vec_id skip
            r"range\(\s*\d+\s*,\s*len\(rows\)", src, re.I  # range-walk from offset
        ))
        if not has_loo:
            findings.append({
                "pattern": "BP-1-look-ahead-bias",
                "severity": "BLOCK",
                "evidence": "target row referenced in both query construction and label without leave-one-out guard",
                "remediation": "exclude target row from corpus before scoring; document leave-one-out invariant explicitly",
            })
    return findings


def detect_bp2_same_tokens_twice(src: str) -> List[Dict]:
    """SAME-TOKENS-WIN-TWICE: cluster_tags (or any high-IDF unique-vocab token set)
    used to compute BOTH the query/retrieval AND the auto-label.

    Tightened v2: only flag if the ACTUAL ASSIGNMENT statement building the
    query text/vector contains cluster_tags. The presence of `target_tags &
    prior_tags` in the auto-label alone is OK if the query doesn't share."""
    findings = []
    # Look for ACTIVE assignment of query_text or qvec that includes cluster_tags
    # Pattern: query_text = <expr involving cluster_tags or target_tags>
    # NOT just any line that mentions both anywhere
    query_assignment_includes_tags = False
    for m in re.finditer(
        r"\b(query_text|qvec|target_text|query_doc)\s*=\s*([^\n]+(?:\n[^=\n]+)?)\n", src
    ):
        rhs = m.group(2)
        if re.search(r"(cluster_tags|target_tags)\b", rhs) and \
           not re.search(r"#.*(?:no.*tags|strip.*tags|removed.*tags)", rhs, re.I):
            query_assignment_includes_tags = True
            break

    label_uses_tag_intersection = bool(re.search(
        r"(target_tags?\s*[&|]\s*prior_tags?|prior_tags?\s*[&|]\s*target_tags?|"
        r"tags_jaccard|cluster_tag_jaccard|tag_overlap)", src
    ))
    if query_assignment_includes_tags and label_uses_tag_intersection:
        findings.append({
            "pattern": "BP-2-same-tokens-win-twice",
            "severity": "BLOCK",
            "evidence": "cluster_tags appear in BOTH the query ASSIGNMENT and auto-label set-intersection (not just anywhere in the file)",
            "remediation": "strip cluster_tags from query text; keep them only in auto-label OR vice versa",
        })
    return findings


def detect_bp3_anchor_pool_confound(src: str) -> List[Dict]:
    """ANCHOR-POOL-SIZE-CONFOUND: P@N gate where typical anchor pool is large
    relative to corpus. Heuristic: presence of P@5 or P@10 + no explicit
    anchor downsampling or normalization. v4.1 broadened: also detect
    `anchor_downsample_applied`, `[:N]` slicing on truth/anchor sets, hash-based
    deterministic sampling."""
    findings = []
    has_p_at_n = bool(re.search(r"p[_@]at[_@]?\d+|precision[_@]at[_@]?\d+|p_at_5", src, re.I))
    # Broader downsample detection patterns (sibling-76 BP-8 + uniform-application discipline)
    downsample_markers = [
        "max_anchors", "anchor_downsample", "downsample_anchors", "anchor_budget",
        "anchor_cap", "truth_sorted[:", "anchors_sorted[:", "anchor_pool_normalization",
        "hash-based deterministic", "BP-3 mitigation", "BP-3 fix",
        "truth_relevant = set(truth_sorted",
    ]
    has_downsample = any(marker in src for marker in downsample_markers) or \
                     bool(re.search(r"anchors_full|truth_relevant_full", src))
    if has_p_at_n and not has_downsample:
        findings.append({
            "pattern": "BP-3-anchor-pool-size-confound",
            "severity": "WARN",
            "evidence": "P@N metric without anchor-pool downsampling or normalization",
            "remediation": "downsample anchor pool to ≤ N per probe so P@N=1.0 is NOT the random-baseline; OR add anchor-pool-size-normalized metric (e.g., NDCG@N or recall-at-N over a held-out anchor sample)",
        })
    return findings


def detect_bp4_tautological_pass(src: str) -> List[Dict]:
    """TAUTOLOGICAL-PASS: PASS criterion satisfiable by accident. Heuristic:
    look for `not (X and Y)` or `X or Y` patterns where X/Y could be False
    for unrelated reasons."""
    findings = []
    # `not (a and b)` style verdicts
    for m in re.finditer(r"(passes?|result|verdict)\s*=\s*not\s*\(([^)]+)\s*and\s*([^)]+)\)", src):
        findings.append({
            "pattern": "BP-4-tautological-pass",
            "severity": "WARN",
            "evidence": f"verdict `not ({m.group(2).strip()} and {m.group(3).strip()})` PASSes if EITHER is False for unrelated reasons",
            "remediation": "tighten verdict: assert the load-bearing mechanism explicitly fires (e.g., chain-walk excluded the row), not just that the outcome aligned with the mechanism",
        })
    return findings


def detect_bp5_threshold_drift(src: str) -> List[Dict]:
    """THRESHOLD-FLOOR-DRIFT: a critical floor was lowered/removed. Heuristic:
    look for comments mentioning recalibration without rigorous justification."""
    findings = []
    # Look for "drop" + "floor" or "lower" + "threshold" comments
    if re.search(r"(drop(ped)?|removed?|lower(ed)?)\s+.*(floor|threshold|gate|cos_floor)", src, re.I):
        # Look for justification (e.g., reference to empirical observation + new metric)
        has_justification = bool(re.search(
            r"(empirical|measured|observed).*(median|distribution|recalibrat)|"
            r"(per[\-_]agent|smaller|narrow).*?(corpus|vocab|distribution)", src, re.I
        ))
        has_replacement = bool(re.search(r"(rank[\-_]margin|p[_@]at|perfect[_\-]rate|"
                                         r"recalibrat|replacement)", src, re.I))
        if not (has_justification and has_replacement):
            findings.append({
                "pattern": "BP-5-threshold-floor-drift",
                "severity": "WARN",
                "evidence": "threshold floor lowered/removed without documented empirical justification + replacement metric",
                "remediation": "document the empirical reason for the change AND the replacement metric in source comment",
            })
    return findings


def detect_bp6_manufactured_baseline(src: str) -> List[Dict]:
    """MANUFACTURED-BASELINE: PASS threshold derived from same sample used to
    evaluate. Heuristic: look for `mean/median/std` computed on a sample +
    used as threshold."""
    findings = []
    # Look for threshold computed from sample stats
    if re.search(r"(threshold|gate|cutoff)\s*=.*?(mean|median|std|percentile)\s*\(", src):
        findings.append({
            "pattern": "BP-6-manufactured-baseline",
            "severity": "WARN",
            "evidence": "threshold computed from sample statistics without a holdout",
            "remediation": "compute thresholds on a held-out calibration sample; evaluate on a separate test sample",
        })
    return findings


def detect_bp7_scope_laundering(src: str) -> List[Dict]:
    """SCOPE-LAUNDERING: SYNTHETIC verdict produced but missing SYNTHETIC- prefix.

    Tightened v2: only flags if the script ACTUALLY produces a verdict (not just
    mentions synthetic in docstring). Looks for verdict-emitting patterns +
    cross-references whether SYNTHETIC prefix appears in verdict contexts."""
    findings = []
    # Does the script produce verdict labels at all?
    emits_verdict = bool(re.search(
        r"['\"](?:verdict|result|status)['\"]?\s*[:=]\s*['\"](PASS|FAIL|WARN|BLOCK|PROVISIONAL)",
        src, re.I
    )) or bool(re.search(r"verdict\s*=\s*['\"](PASS|FAIL|WARN|BLOCK|PROVISIONAL)", src))
    if not emits_verdict:
        return findings

    # Does the script claim to be synthetic/back-test in implementation (not just docs)?
    impl_is_synthetic = bool(re.search(
        r"\b(retrospective|back[_\-]?test|synthetic.*(verdict|pass|fail|metric)|"
        r"would_have_helped|missed_correction|would_have_prevented)\b", src
    ))
    if not impl_is_synthetic:
        return findings

    # If synthetic implementation present, does verdict emit SYNTHETIC- prefix?
    emits_prefix = bool(re.search(
        r"['\"]SYNTHETIC[\-_]?(PASS|FAIL|PROVISIONAL)['\"]?", src
    ))
    if not emits_prefix:
        findings.append({
            "pattern": "BP-7-scope-laundering-missing-prefix",
            "severity": "BLOCK",
            "evidence": "script produces synthetic-backtest verdicts but does not emit explicit SYNTHETIC- prefix",
            "remediation": "prepend SYNTHETIC- to all verdict labels; ensure prefix survives JSON serialization",
        })
    return findings


def detect_bp8_citation_format_drift(src: str) -> List[Dict]:
    """CITATION-FORMAT-DRIFT: script mines citations from agent ledgers but only
    matches the canonical `ledger::name::lamport-N::session` format. Per sibling-76
    finding 2026-05-15: agents emit citations in 7+ syntactic formats (vec:, ledger:,
    forge:, lamport-N-, descriptive strings). Canonical-only matching undercounts by
    ~70%. Severity WARN (undercounts; doesn't over-inflate).

    Heuristic: script imports/regex for ledger:: format AND iterates over
    `cites` or `lag_influenced_by` fields BUT does NOT include broader format
    patterns.
    """
    findings = []
    # Does the script mine citations?
    mines_citations = bool(re.search(
        r"(cites|lag_influenced_by|citations?)\b.*?(jsonl|ledger|agent)", src, re.S | re.I
    ))
    if not mines_citations:
        return findings
    # Does it use canonical-format-only matching?
    has_canonical_match = bool(re.search(
        r"(startswith\(['\"]ledger::|ledger::.*?::lamport-|VEC_ID_RE)", src
    ))
    # Does it ALSO accept broader formats? Look for marker strings the broader
    # citation-format detector would use.
    broader_markers = [
        "vec:", "forge:", "curator-", "pathfinder-", "scribe:",
        "warden:", "judge:", "adversary:", "scout:", "informal", "broad",
        "citation-format-drift", "BP-8", "citations_emitted_informal",
        "citations_emitted_canonical",
    ]
    has_broader_formats = any(marker in src for marker in broader_markers)
    if has_canonical_match and not has_broader_formats:
        findings.append({
            "pattern": "BP-8-citation-format-drift",
            "severity": "WARN",
            "evidence": "script mines citations using canonical 'ledger::' format ONLY; misses informal formats (vec:, agent-prefix, lamport-N-, descriptive strings) that agents naturally emit",
            "remediation": "add broader-format detection (vec:, ledger:, forge:, curator-, lamport-N-, descriptive strings) per sibling-76 BP-8 catalog; canonical-only undercounts by ~70%",
        })
    return findings


SCANNERS = [
    detect_bp1_lookahead, detect_bp2_same_tokens_twice, detect_bp3_anchor_pool_confound,
    detect_bp4_tautological_pass, detect_bp5_threshold_drift, detect_bp6_manufactured_baseline,
    detect_bp7_scope_laundering, detect_bp8_citation_format_drift,
]


def scan_file(path: Path) -> Dict:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"path": str(path), "error": "could-not-read", "findings": []}

    all_findings = []
    for scanner in SCANNERS:
        try:
            all_findings.extend(scanner(src))
        except Exception as e:
            all_findings.append({"pattern": "SCANNER-ERROR", "scanner": scanner.__name__,
                                 "error": str(e)[:120]})

    n_block = sum(1 for f in all_findings if f.get("severity") == "BLOCK")
    n_warn = sum(1 for f in all_findings if f.get("severity") == "WARN")
    score = 100 - (n_block * 30) - (n_warn * 10)  # 100=clean, 70+=ok, <50=block
    verdict = "BLOCK" if n_block > 0 else ("WARN" if n_warn > 0 else "PASS")

    return {
        "path": str(path),
        "src_sha256": "blake2b-256:" + b2(src),
        "n_lines": src.count("\n") + 1,
        "n_findings": len(all_findings),
        "n_block": n_block, "n_warn": n_warn,
        "fmv_score": score,
        "fmv_verdict": verdict,
        "findings": all_findings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--falsifier", type=Path)
    g.add_argument("--scan-all", action="store_true")
    ap.add_argument("--scripts-dir", type=Path,
                    default=Path("projects/v11-aep/publish-ready/aep/scripts"))
    ap.add_argument("--receipts-path", type=Path,
                    default=Path(".claude/_logs/fmv-receipts.jsonl"))
    args = ap.parse_args()

    if args.scan_all:
        paths = sorted(args.scripts_dir.glob("falsifier_*.py")) + \
                sorted(args.scripts_dir.glob("lane_b_*.py"))
        # Exclude FMV itself (meta-validator scanning meta-validator = infinite regress;
        # the regex-pattern code legitimately contains terms that trigger false positives)
        paths = [p for p in paths if "falsifier_meta_validate" not in p.name]
    else:
        paths = [args.falsifier]

    results = []
    for p in paths:
        if not p.exists():
            print(f"# skip {p}: not found", file=sys.stderr)
            continue
        r = scan_file(p)
        results.append(r)

    # Emit receipts (one per scanned file, HCRL-chain optional)
    args.receipts_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for r in results:
        receipt = {"receipt_type": "fmv_scan", "scanned_at": now, **r}
        with open(args.receipts_path, "a", encoding="utf-8") as f:
            f.write(canon(receipt) + "\n")

    n_pass = sum(1 for r in results if r["fmv_verdict"] == "PASS")
    n_warn = sum(1 for r in results if r["fmv_verdict"] == "WARN")
    n_block = sum(1 for r in results if r["fmv_verdict"] == "BLOCK")

    summary = {
        "scanned_at": now,
        "n_files": len(results),
        "n_pass": n_pass, "n_warn": n_warn, "n_block": n_block,
        "verdict": "BLOCK" if n_block > 0 else ("WARN" if n_warn > 0 else "PASS"),
        "results": results,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if n_block == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
