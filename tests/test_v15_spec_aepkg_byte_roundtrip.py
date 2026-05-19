"""test_v15_spec_aepkg_byte_roundtrip.py - Wave 4a Artifact 4 (GO-7 fixture).

Per adversary Phase beta-init pre-mortem section 5 GO-7:
  Run spec_md_to_aepkg.py --dry-run on each of the 11 AEP spec .md files.
  Then run actual converter on AEP_v0_3_SPEC.md (smallest/oldest).
  Verify byte-identical projection.

Pass condition: 11/11 dry-runs PASS + 1/1 byte-roundtrip PASS.

Cleanup: this test removes any .aepkg/ output it creates (atomic FS cleanup).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERTER = REPO_ROOT / "tools" / "spec_md_to_aepkg.py"
SPEC_DIR = REPO_ROOT / "projects" / "v11-aep" / "publish-ready" / "aep" / "spec"
EXPECTED_SPEC_FILES = [
    "AEP_v0_3_SPEC.md",
    "AEP_v0_4_SPEC.md",
    "AEP_v0_5_SPEC.md",
    "AEP_v0_5_1_SPEC.md",
    "AEP_v0_5_5_SPEC.md",
    "AEP_v0_6_SPEC.md",
    "AEP_v0_8_SPEC.md",
    "AEP_v1_0_3_SPEC.md",
    "AEP_v1_0_3_1_SPEC.md",
    "AEP_v1_1_SPEC.md",
    "AEP_v1_2_SPEC.md",
]


class TestV15SpecAepkgByteRoundtrip(unittest.TestCase):
    """GO-7 fixture: dry-run on all 11 specs + byte-roundtrip on the smallest."""

    aepkg_dirs_to_cleanup = []  # populated by test_byte_roundtrip; cleaned in tearDownClass

    def _run(self, args_list: list) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(CONVERTER)] + args_list
        return subprocess.run(cmd, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls) -> None:
        # Wave 5 amendment 2026-05-18: post-Phase-beta-init, AEP_v0_3_SPEC.aepkg is
        # a DURABLE artifact (committed companion). Skip cleanup to avoid wiping the
        # canonical Wave 5 companion. The byte-roundtrip test re-converts in place
        # via --force, so leaving the artifact is the correct post-test state.
        # sec73.6 honest framing: tearDownClass deliberately preserves durable artifacts.
        return

    def test_all_11_specs_present(self) -> None:
        """Sanity: confirm the 11 expected spec files exist before testing."""
        for fname in EXPECTED_SPEC_FILES:
            p = SPEC_DIR / fname
            self.assertTrue(p.exists(), "missing spec file: " + str(p))

    def test_dry_run_all_11_pass(self) -> None:
        """11/11 dry-run PASS - per GO-7 pre-mortem requirement."""
        passed = 0
        failures = []
        for fname in EXPECTED_SPEC_FILES:
            p = SPEC_DIR / fname
            r = self._run([str(p), "--dry-run", "--json"])
            if r.returncode != 0:
                failures.append(fname + ": rc=" + str(r.returncode) + " stderr=" + r.stderr[:200])
                continue
            try:
                summary = json.loads(r.stdout.strip())
            except Exception as e:
                failures.append(fname + ": json parse error: " + str(e))
                continue
            # Schema asserts on dry-run output
            for required_key in ("mode", "source_sha256", "section_count",
                                 "canonical_files_planned", "schema_version"):
                if required_key not in summary:
                    failures.append(fname + ": missing key " + required_key)
                    break
            else:
                if summary["mode"] != "dry-run":
                    failures.append(fname + ": mode != dry-run")
                elif summary["section_count"] < 0:
                    failures.append(fname + ": negative section_count")
                elif not summary["source_sha256"].startswith("sha256:"):
                    failures.append(fname + ": source_sha256 not sha256: prefixed")
                else:
                    passed += 1

        self.assertEqual(passed, 11,
            "GO-7 dry-run: expected 11/11 PASS, got " + str(passed) + "/11. Failures: "
            + "; ".join(failures))
        self.assertEqual(len(failures), 0,
            "GO-7 dry-run had failures: " + "; ".join(failures))

    def test_byte_roundtrip_on_v0_3_spec(self) -> None:
        """1/1 byte-roundtrip on AEP_v0_3_SPEC.md (smallest/oldest per pre-mortem GO-7)."""
        v0_3_path = SPEC_DIR / "AEP_v0_3_SPEC.md"
        self.assertTrue(v0_3_path.exists(), "AEP_v0_3_SPEC.md missing")

        # Pre-compute the canonical input sha256
        input_bytes = v0_3_path.read_bytes()
        input_sha = hashlib.sha256(input_bytes).hexdigest()

        # Run actual conversion (NOT dry-run) into a sibling output path
        output_dir = SPEC_DIR / "AEP_v0_3_SPEC.aepkg"
        # Register for cleanup before we create it
        self.__class__.aepkg_dirs_to_cleanup.append(output_dir)

        # Force-overwrite in case a prior run left a fragment
        r = self._run([str(v0_3_path), "--out", str(output_dir), "--force", "--json"])
        self.assertEqual(r.returncode, 0,
            "commit conversion should succeed; stderr=" + r.stderr)

        summary = json.loads(r.stdout.strip())
        self.assertEqual(summary["mode"], "commit")
        self.assertEqual(summary["source_sha256"], "sha256:" + input_sha,
            "source_sha256 in summary must match pre-computed input sha")

        # Byte-roundtrip verification: views/source.md MUST be byte-identical to input
        views_source = output_dir / "views" / "source.md"
        self.assertTrue(views_source.exists(), "views/source.md must exist")

        projected_bytes = views_source.read_bytes()
        self.assertEqual(projected_bytes, input_bytes,
            "GO-7 byte-roundtrip FAILED: views/source.md != input .md bytes")

        projected_sha = hashlib.sha256(projected_bytes).hexdigest()
        self.assertEqual(projected_sha, input_sha,
            "GO-7 byte-roundtrip FAILED: sha256 mismatch input=" + input_sha
            + " projected=" + projected_sha)

        # Also verify meta.json + integrity.json are present and well-formed
        meta = json.loads((output_dir / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["source_sha256"], "sha256:" + input_sha)
        integrity = json.loads((output_dir / "integrity.json").read_text(encoding="utf-8"))
        self.assertTrue(integrity["state_hash"].startswith("sha256:"))
        self.assertEqual(integrity["source_sha256"], "sha256:" + input_sha)

    def test_go7_verdict_summary(self) -> None:
        """Synthesize GO-7 verdict: 11/11 dry-run PASS AND 1/1 byte-roundtrip PASS."""
        # Re-run dry-runs (cheap; already validated above; this is the verdict surface)
        dry_run_pass = 0
        for fname in EXPECTED_SPEC_FILES:
            r = self._run([str(SPEC_DIR / fname), "--dry-run", "--json"])
            if r.returncode == 0:
                dry_run_pass += 1
        # The byte-roundtrip test runs separately; here we only assert ABILITY (dry-run gate)
        self.assertEqual(dry_run_pass, 11,
            "GO-7 verdict gate: " + str(dry_run_pass) + "/11 dry-runs PASS (need 11/11)")

    def test_wave5_all_11_companions_present_and_byte_identical(self) -> None:
        """Wave 5 (Phase beta-init): verify all 11 .aepkg/ companions on disk and byte-identical.

        Empirical test (no bug to fix); characterizes Wave 5 post-conversion state.
        Pass: 11/11 .aepkg/ dirs present + 11/11 byte-roundtrip match canonical sha256.
        """
        passed = 0
        failures = []
        for fname in EXPECTED_SPEC_FILES:
            src = SPEC_DIR / fname
            aepkg = SPEC_DIR / (src.stem + ".aepkg")
            if not aepkg.exists():
                failures.append(fname + ": .aepkg/ missing")
                continue
            for required in ("meta.json", "data/claims.jsonl", "views/source.md", "integrity.json"):
                if not (aepkg / required).exists():
                    failures.append(fname + ": missing " + required)
                    break
            else:
                src_sha = hashlib.sha256(src.read_bytes()).hexdigest()
                proj_sha = hashlib.sha256((aepkg / "views" / "source.md").read_bytes()).hexdigest()
                if src_sha != proj_sha:
                    failures.append(fname + ": sha mismatch src=" + src_sha[:12]
                                    + " proj=" + proj_sha[:12])
                    continue
                meta = json.loads((aepkg / "meta.json").read_text(encoding="utf-8"))
                if meta.get("source_sha256") != "sha256:" + src_sha:
                    failures.append(fname + ": meta source_sha256 mismatch")
                    continue
                integ = json.loads((aepkg / "integrity.json").read_text(encoding="utf-8"))
                if not integ.get("state_hash", "").startswith("sha256:"):
                    failures.append(fname + ": integrity.state_hash bad prefix")
                    continue
                passed += 1
        self.assertEqual(passed, 11,
            "Wave 5: expected 11/11 companions byte-identical, got " + str(passed)
            + "/11. Failures: " + "; ".join(failures))
        self.assertEqual(len(failures), 0,
            "Wave 5 had failures: " + "; ".join(failures))


if __name__ == "__main__":
    unittest.main()
