"""Unit tests for sdd_scripts/run_dev_phase.py — deterministic helpers for /dev-run STEP 6."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_scripts import run_dev_phase as rdp  # noqa: E402


class TestChunkUsList(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(rdp.chunk_us_list([], 3), [])

    def test_smaller_than_chunk(self):
        self.assertEqual(rdp.chunk_us_list(["1-1", "1-2"], 3), [["1-1", "1-2"]])

    def test_exact_chunks(self):
        self.assertEqual(
            rdp.chunk_us_list(["1-1", "1-2", "1-3", "1-4"], 2),
            [["1-1", "1-2"], ["1-3", "1-4"]],
        )

    def test_uneven_chunks(self):
        self.assertEqual(
            rdp.chunk_us_list(["1-1", "1-2", "1-3", "1-4", "1-5"], 2),
            [["1-1", "1-2"], ["1-3", "1-4"], ["1-5"]],
        )

    def test_invalid_parallel(self):
        with self.assertRaises(ValueError):
            rdp.chunk_us_list(["1-1"], 0)


class TestListUsForFeat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        (self.root / "workspace" / "output" / "us").mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write_us(self, n, m, name="Foo"):
        (self.root / "workspace" / "output" / "us" / f"{n}-{m}-{name}.md").write_text(
            "# US\n", encoding="utf-8"
        )

    def test_lists_in_order(self):
        self._write_us(1, 3)
        self._write_us(1, 1)
        self._write_us(1, 2)
        result = rdp.list_us_for_feat(self.root, 1)
        self.assertEqual(result, ["1-1", "1-2", "1-3"])

    def test_filters_by_feat_number(self):
        self._write_us(1, 1)
        self._write_us(2, 1, name="Other")
        result = rdp.list_us_for_feat(self.root, 1)
        self.assertEqual(result, ["1-1"])

    def test_no_us_dir(self):
        # Remove the dir
        (self.root / "workspace" / "output" / "us").rmdir()
        self.assertEqual(rdp.list_us_for_feat(self.root, 1), [])


class TestReadMaxParallel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "workspace" / "input" / "stack").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_stack(self, content: str):
        (self.root / "workspace" / "input" / "stack" / "stack.md").write_text(content, encoding="utf-8")

    def test_default_when_no_stack(self):
        self.assertEqual(rdp.read_max_parallel(self.root), 3)

    def test_default_when_no_key(self):
        self._write_stack("# Stack\n\n## Project Config\n")
        self.assertEqual(rdp.read_max_parallel(self.root), 3)

    def test_reads_value(self):
        self._write_stack("# Stack\n\n## Project Config\nMaxParallel: 6\n")
        self.assertEqual(rdp.read_max_parallel(self.root), 6)

    def test_clamps_to_range(self):
        self._write_stack("# Stack\n\n## Project Config\nMaxParallel: 99\n")
        self.assertEqual(rdp.read_max_parallel(self.root), 12)
        self._write_stack("# Stack\n\n## Project Config\nMaxParallel: 0\n")
        self.assertEqual(rdp.read_max_parallel(self.root), 1)

    def test_override(self):
        self.assertEqual(rdp.read_max_parallel(self.root, override=5), 5)
        self.assertEqual(rdp.read_max_parallel(self.root, override=99), 12)


class TestScanPlans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "workspace" / "output" / "plans").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_dir(self):
        result = rdp.scan_plans(self.root, 1)
        self.assertEqual(result, {"back": [], "front": [], "back_count": 0, "front_count": 0})

    def test_detects_both_families(self):
        plans = self.root / "workspace" / "output" / "plans"
        (plans / "1-1-Login.back.md").write_text("", encoding="utf-8")
        (plans / "1-1-Login.front.md").write_text("", encoding="utf-8")
        (plans / "1-2-Logout.back.md").write_text("", encoding="utf-8")
        result = rdp.scan_plans(self.root, 1)
        self.assertEqual(result["back_count"], 2)
        self.assertEqual(result["front_count"], 1)

    def test_filters_by_feat(self):
        plans = self.root / "workspace" / "output" / "plans"
        (plans / "1-1-Login.back.md").write_text("", encoding="utf-8")
        (plans / "2-1-Profile.back.md").write_text("", encoding="utf-8")
        result = rdp.scan_plans(self.root, 1)
        self.assertEqual(result["back_count"], 1)


class TestApiGateVerdict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.qa_dir = self.root / "workspace" / "output" / "qa" / "feat-1"
        self.qa_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_report(self, payload):
        (self.qa_dir / "api-tests.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_no_file_skipped(self):
        verdict = rdp.read_api_gate_verdict(self.root, 1)
        self.assertEqual(verdict["status"], "SKIPPED")
        self.assertTrue(verdict["gate_passed"])

    def test_pass_status(self):
        self._write_report({"summary": {"status": "PASS", "tests_total": 10, "tests_passed": 10}})
        verdict = rdp.read_api_gate_verdict(self.root, 1)
        self.assertEqual(verdict["status"], "PASS")
        self.assertTrue(verdict["gate_passed"])

    def test_fail_status(self):
        self._write_report({"summary": {"status": "FAIL", "tests_failed": 3}})
        verdict = rdp.read_api_gate_verdict(self.root, 1)
        self.assertEqual(verdict["status"], "FAIL")
        self.assertFalse(verdict["gate_passed"])

    def test_infra_blocked(self):
        self._write_report({"summary": {"status": "INFRA_BLOCKED"}})
        verdict = rdp.read_api_gate_verdict(self.root, 1)
        self.assertEqual(verdict["status"], "INFRA_BLOCKED")
        self.assertFalse(verdict["gate_passed"])

    def test_legacy_verdict_fallback(self):
        # status absent → fallback to legacy verdict mapping
        self._write_report({"summary": {"verdict": "RED"}})
        verdict = rdp.read_api_gate_verdict(self.root, 1)
        self.assertEqual(verdict["status"], "FAIL")

    def test_corrupted_json(self):
        (self.qa_dir / "api-tests.json").write_text("not json{", encoding="utf-8")
        verdict = rdp.read_api_gate_verdict(self.root, 1)
        self.assertEqual(verdict["status"], "INFRA_BLOCKED")


class TestDecideAfterApiGate(unittest.TestCase):
    def test_pass_continues(self):
        d = rdp.decide_after_api_gate({"status": "PASS"})
        self.assertTrue(d["should_continue_frontend"])

    def test_warn_continues(self):
        d = rdp.decide_after_api_gate({"status": "WARN"})
        self.assertTrue(d["should_continue_frontend"])

    def test_skipped_continues(self):
        d = rdp.decide_after_api_gate({"status": "SKIPPED"})
        self.assertTrue(d["should_continue_frontend"])

    def test_fail_stops(self):
        d = rdp.decide_after_api_gate({"status": "FAIL"})
        self.assertFalse(d["should_continue_frontend"])

    def test_infra_blocked_stops(self):
        d = rdp.decide_after_api_gate({"status": "INFRA_BLOCKED"})
        self.assertFalse(d["should_continue_frontend"])

    def test_unknown_stops(self):
        d = rdp.decide_after_api_gate({"status": "WEIRD"})
        self.assertFalse(d["should_continue_frontend"])


if __name__ == "__main__":
    unittest.main()
