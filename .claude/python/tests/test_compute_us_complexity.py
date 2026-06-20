"""Tests for sdd_scripts.compute_us_complexity — deterministic US scoring."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import compute_us_complexity as cuc  # noqa: E402


SIMPLE_US = """# US-1: Counter

ID: 1-1-Counter
Parent FEAT: 1-Test
Status: Draft

## User Story
En tant que dev
Je veux afficher un compteur
Afin de vérifier que la page charge

## Acceptance Criteria
- AC-1: le compteur affiche 0 au chargement
- AC-2: cliquer incrémente le compteur

## Covers
- SFD-1
- FD-1

## Dependencies
- NONE

## Metadata
```json
{}
```
"""


COMPLEX_US = """# US-2: BatchExport

ID: 2-1-BatchExport
Parent FEAT: 2-Test
Status: Draft

## User Story
Export batch async avec retry, webhook, websocket polling temps-réel, transaction, encryption.

## Acceptance Criteria
- AC-1: JWT validation et permission RBAC scope check
- AC-2: batch async avec retry 3x exponential backoff
- AC-3: PDF encryption AES-256 avec HMAC signature
- AC-4: webhook idempotent avec saga compensating
- AC-5: websocket polling stream real-time
- AC-6: events loggés avec correlation ID
- AC-7: rollback transaction si deadlock

## Covers
- SFD-1
- SFD-2
- SFD-3
- BR-1
- AC-1
- AC-2
- FD-1
- FD-2

## Dependencies
- 1-1
- 1-2

## Metadata
```json
{}
```
"""


class TestExtractSignals(unittest.TestCase):
    def test_simple_us_signals(self):
        s = cuc.extract_signals(SIMPLE_US)
        self.assertEqual(s["ac_count"], 2)
        self.assertEqual(s["covers_count"], 2)
        self.assertEqual(s["deps_count"], 0)  # NONE excluded
        self.assertEqual(s["keyword_matches"], 0)
        self.assertGreater(s["user_story_len"], 0)

    def test_complex_us_signals(self):
        s = cuc.extract_signals(COMPLEX_US)
        self.assertEqual(s["ac_count"], 7)
        self.assertEqual(s["covers_count"], 8)
        self.assertEqual(s["deps_count"], 2)
        self.assertGreater(s["keyword_matches"], 5)

    def test_none_dependency_excluded(self):
        content = "## Dependencies\n- NONE\n- none\n- 1-1\n"
        s = cuc.extract_signals(content)
        self.assertEqual(s["deps_count"], 1)

    def test_placeholder_dep_excluded(self):
        content = "## Dependencies\n- <US-id ou NONE>\n- 2-3\n"
        s = cuc.extract_signals(content)
        self.assertEqual(s["deps_count"], 1)


class TestScoreSignals(unittest.TestCase):
    def test_simple_yields_low_score(self):
        s = cuc.extract_signals(SIMPLE_US)
        result = cuc.score_signals(s)
        self.assertLessEqual(result["score"], 4,
                             f"simple US scored {result['score']}, expected <= 4")
        self.assertGreaterEqual(result["score"], 1)

    def test_complex_yields_high_score(self):
        s = cuc.extract_signals(COMPLEX_US)
        result = cuc.score_signals(s)
        self.assertGreaterEqual(result["score"], 8,
                                f"complex US scored {result['score']}, expected >= 8")
        self.assertLessEqual(result["score"], 10)

    def test_score_clamped_to_1_10(self):
        # Empty content -> all signals zero -> score should be 1
        s = cuc.extract_signals("")
        result = cuc.score_signals(s)
        self.assertEqual(result["score"], 1)

    def test_contributions_sum_to_raw(self):
        s = cuc.extract_signals(COMPLEX_US)
        result = cuc.score_signals(s)
        self.assertAlmostEqual(
            sum(result["contributions"].values()), result["raw"], places=2
        )


class TestEstimateFromScore(unittest.TestCase):
    def test_mapping(self):
        cases = [(1, "S"), (2, "S"), (3, "M"), (4, "M"),
                 (5, "L"), (6, "L"), (7, "XL"), (8, "XL"),
                 (9, "XL"), (10, "XL")]
        for score, expected in cases:
            est, _ = cuc.estimate_from_score(score)
            self.assertEqual(est, expected, f"score={score} -> {est} (want {expected})")

    def test_high_score_advisory(self):
        _, advisory = cuc.estimate_from_score(9)
        self.assertIn("WARN", advisory)

    def test_low_score_no_advisory(self):
        _, advisory = cuc.estimate_from_score(2)
        self.assertEqual(advisory, "")


class TestUpdateMetadataBlock(unittest.TestCase):
    def test_injects_complexity_and_estimate(self):
        new_content, modified = cuc.update_metadata_block(SIMPLE_US, 3, "M")
        self.assertTrue(modified)
        # Extract the JSON block
        import re
        m = re.search(r"```json\s*\n(.*?)\n```", new_content, re.DOTALL)
        self.assertIsNotNone(m)
        data = json.loads(m.group(1))
        self.assertEqual(data["complexity"], 3)
        self.assertEqual(data["effort_estimate"], "M")

    def test_preserves_existing_keys(self):
        us = SIMPLE_US.replace('{}', '{"notes": "preserve me", "flags": ["x"]}')
        new_content, modified = cuc.update_metadata_block(us, 5, "L")
        self.assertTrue(modified)
        import re
        m = re.search(r"```json\s*\n(.*?)\n```", new_content, re.DOTALL)
        data = json.loads(m.group(1))
        self.assertEqual(data["notes"], "preserve me")
        self.assertEqual(data["flags"], ["x"])
        self.assertEqual(data["complexity"], 5)

    def test_no_metadata_section_returns_false(self):
        us_no_meta = SIMPLE_US.split("## Metadata")[0]
        new_content, modified = cuc.update_metadata_block(us_no_meta, 5, "L")
        self.assertFalse(modified)
        self.assertEqual(new_content, us_no_meta)

    def test_invalid_json_returns_false(self):
        us_bad = SIMPLE_US.replace('{}', '{"unterminated":')
        new_content, modified = cuc.update_metadata_block(us_bad, 5, "L")
        self.assertFalse(modified)


class TestMainEndToEnd(unittest.TestCase):
    def _setup_repo(self, tmp_p: Path, content: str) -> Path:
        (tmp_p / ".claude").mkdir()
        us_dir = tmp_p / "workspace" / "output" / "us"
        us_dir.mkdir(parents=True)
        us_path = us_dir / "5-1-Probe.md"
        us_path.write_text(content, encoding="utf-8")
        return us_path

    def test_compute_no_apply(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            us_path = self._setup_repo(tmp_p, SIMPLE_US)
            with mock.patch.object(cuc, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["compute_us_complexity.py", "--us", "5-1"]):
                rc = cuc.main()
            self.assertEqual(rc, 0)
            # File unchanged
            self.assertEqual(us_path.read_text(encoding="utf-8"), SIMPLE_US)

    def test_compute_with_apply_modifies_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            us_path = self._setup_repo(tmp_p, SIMPLE_US)
            with mock.patch.object(cuc, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["compute_us_complexity.py", "--us", "5-1",
                                    "--apply"]):
                rc = cuc.main()
            self.assertEqual(rc, 0)
            content = us_path.read_text(encoding="utf-8")
            self.assertIn('"complexity"', content)
            self.assertIn('"effort_estimate"', content)

    def test_us_not_found_returns_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            with mock.patch.object(cuc, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["compute_us_complexity.py", "--us", "9-9"]):
                rc = cuc.main()
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
