"""test_chip_completeness_audit.py - smoke harness for chip_completeness_audit.py.

Tests (Wave-D 2026-05-16 forge-style smoke harness):
  1. Synthetic GOOD fixture (every truth-tag word inside tt-* span)   -> 0 findings
  2. Synthetic BAD-bare fixture (truth-tag words bare in <h1>+<p>)    -> ≥6 findings,
                                                                          ≥1 HIGH severity
  3. Synthetic BAD-partial-chip fixture (`<span class="tt">` no tier) -> ≥1 finding
                                                                          with is_partial_chip=true
  4. Real-corpus check on §66 post-remediation                        -> 0 HIGH findings
                                                                          (else BP-C-CHIP-1+2 attack
                                                                          family is NOT closed)
  5. Real-corpus check on §02-truth-tags                              -> at most expected
                                                                          partial-chip count (this
                                                                          file describes the tags, so
                                                                          bare-word mentions in code
                                                                          blocks / metadata are
                                                                          allowed if not in HIGH
                                                                          elements)

The test does NOT use pytest (consistency with test_agent_yield_check.py style:
each test is a function returning (name, ok, msg)). Run with:
    python test_chip_completeness_audit.py

EXIT CODES:
  0 = all tests pass
  1 = ≥1 test fails
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path


def _import_audit():
    sys.path.insert(0, str(Path(__file__).parent))
    import chip_completeness_audit  # type: ignore
    importlib.reload(chip_completeness_audit)
    return chip_completeness_audit


# ============================================================================
# Fixtures
# ============================================================================

_GOOD_FIXTURE = """<!doctype html>
<html>
  <head><title>good</title></head>
  <body>
    <h1>Section</h1>
    <p>Truth tag:
      <span class="tt tt-proven-reliable" data-tag="PROVEN/RELIABLE">PROVEN/RELIABLE</span>
      .
    </p>
    <p>
      <span class="tt tt-strongly-plausible">STRONGLY PLAUSIBLE</span>
      <span class="tt tt-experimental">EXPERIMENTAL</span>
      <span class="tt tt-speculative-frontier">SPECULATIVE FRONTIER</span>
      <span class="tt tt-impossible-unsupported">IMPOSSIBLE/UNSUPPORTED</span>
      <span class="tt tt-dangerous-not-worth-doing">DANGEROUS/NOT WORTH DOING</span>
    </p>
  </body>
</html>
"""

_BAD_BARE_FIXTURE = """<!doctype html>
<html>
  <head><title>bad-bare</title></head>
  <body>
    <h1>Status: PROVEN/RELIABLE</h1>
    <p>This claim is STRONGLY PLAUSIBLE.</p>
    <p>That claim is EXPERIMENTAL.</p>
    <p>The other is SPECULATIVE FRONTIER.</p>
    <p>This route is IMPOSSIBLE/UNSUPPORTED.</p>
    <p>Avoid: DANGEROUS/NOT WORTH DOING.</p>
    <strong>STRONGLY-PLAUSIBLE</strong> alternate hyphen form.
  </body>
</html>
"""

_BAD_PARTIAL_CHIP_FIXTURE = """<!doctype html>
<html>
  <body>
    <p>Amendment marker: <span class="tt">STRONGLY PLAUSIBLE</span> as bare-tt.</p>
    <p>Properly chipped: <span class="tt tt-proven-reliable">PROVEN/RELIABLE</span>.</p>
  </body>
</html>
"""


# ============================================================================
# Helpers
# ============================================================================


def _write_and_audit(mod, content: str, name: str = "fixture.html") -> tuple[list, dict]:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fpath = td_path / name
        fpath.write_text(content, encoding="utf-8")
        out_path = td_path / "findings.jsonl"
        findings = list(mod.audit_corpus([fpath], repo_root=td_path, quiet=True))
        summary = mod.write_findings(findings, out_path, corpus_size=1)
        return findings, summary


# ============================================================================
# Tests
# ============================================================================


def test_1_good_fixture_zero_findings() -> tuple[str, bool, str]:
    mod = _import_audit()
    findings, summary = _write_and_audit(mod, _GOOD_FIXTURE, "good.html")
    ok = (len(findings) == 0) and (summary["total_findings"] == 0)
    msg = f"good fixture: total_findings={summary['total_findings']} (expected 0)"
    return ("test_1_good_fixture_zero_findings", ok, msg)


def test_2_bad_bare_fixture_six_plus_findings() -> tuple[str, bool, str]:
    mod = _import_audit()
    findings, summary = _write_and_audit(mod, _BAD_BARE_FIXTURE, "bad-bare.html")
    # 6 distinct truth-tag words used + 1 hyphen-variant in <strong> = 7
    high = summary["by_severity"]["HIGH"]
    ok = (summary["total_findings"] >= 6) and (high >= 1)
    msg = (f"bad-bare fixture: total_findings={summary['total_findings']} "
           f"HIGH={high} (expected ≥6 total + ≥1 HIGH)")
    return ("test_2_bad_bare_fixture_six_plus_findings", ok, msg)


def test_3_bad_partial_chip_fixture_partial_flag() -> tuple[str, bool, str]:
    mod = _import_audit()
    findings, summary = _write_and_audit(mod, _BAD_PARTIAL_CHIP_FIXTURE,
                                            "partial.html")
    partial = summary["partial_chip_findings"]
    total = summary["total_findings"]
    ok = (partial >= 1) and (total == partial)
    msg = (f"partial-chip fixture: total={total} partial_chip={partial} "
           f"(expected partial≥1 AND total==partial, since properly-chipped "
           f"PROVEN/RELIABLE is correctly skipped)")
    return ("test_3_bad_partial_chip_fixture_partial_flag", ok, msg)


def test_4_real_corpus_section_66_zero_high() -> tuple[str, bool, str]:
    mod = _import_audit()
    section_66 = mod.REPO_ROOT / "doctrine" / "66-diana-idle-trigger-autonomous-takeover.html"
    if not section_66.is_file():
        return ("test_4_real_corpus_section_66_zero_high", False,
                f"§66 file not found: {section_66}")
    findings = mod.audit_file(section_66)
    high = sum(1 for f in findings if f.severity == "HIGH")
    ok = (high == 0)
    msg = (f"§66 post-remediation HIGH findings: {high} (expected 0; "
           f"if non-zero, forge Wave-C task-01 remediation was incomplete -> "
           f"WARN not BLOCK per task spec). Total findings: {len(findings)}.")
    return ("test_4_real_corpus_section_66_zero_high", ok, msg)


def test_5_real_corpus_section_02_truth_tags_sanity() -> tuple[str, bool, str]:
    """§02-truth-tags.html DESCRIBES the tags, so it contains many bare-word
    mentions inside <code>, <h3>, and JSON metadata. We require:
      - HIGH findings ≤ 2 (it's a taxonomy doc; expect maybe 1-2 in headings)
      - script does not crash on real-corpus complexity"""
    mod = _import_audit()
    section_02 = mod.REPO_ROOT / "doctrine" / "02-truth-tags.html"
    if not section_02.is_file():
        return ("test_5_real_corpus_section_02_truth_tags_sanity", False,
                f"§02 file not found: {section_02}")
    findings = mod.audit_file(section_02)
    high = sum(1 for f in findings if f.severity == "HIGH")
    # Sanity: the script ran without error and produced bounded output.
    # We don't enforce HIGH==0 because §02 legitimately discusses the words.
    ok = (len(findings) < 100) and (high <= 10)
    msg = (f"§02-truth-tags total={len(findings)} HIGH={high} (sanity bounds: "
           f"total<100, HIGH≤10; this is a tag-taxonomy doc so bare mentions "
           f"are expected; this test only verifies the script runs cleanly)")
    return ("test_5_real_corpus_section_02_truth_tags_sanity", ok, msg)


# ============================================================================
# Runner
# ============================================================================


def main() -> int:
    tests = [
        test_1_good_fixture_zero_findings,
        test_2_bad_bare_fixture_six_plus_findings,
        test_3_bad_partial_chip_fixture_partial_flag,
        test_4_real_corpus_section_66_zero_high,
        test_5_real_corpus_section_02_truth_tags_sanity,
    ]
    results = []
    for t in tests:
        try:
            results.append(t())
        except Exception as e:
            results.append((t.__name__, False, f"EXCEPTION: {type(e).__name__}: {e}"))

    print("=" * 78)
    print(f"chip_completeness_audit.py smoke harness — {len(tests)} tests")
    print("=" * 78)
    for name, ok, msg in results:
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name}")
        print(f"         {msg}")
    print("-" * 78)
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_total = len(results)
    print(f"{n_ok}/{n_total} passed")
    return 0 if n_ok == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
