"""Tests for sdd_scripts.report_roi — ROI aggregation per FEAT.

Coverage :
- Empty DB → graceful no-content output
- FEAT not found → exit 2
- Single FEAT with full data (runs + tokens + coverage + spec compliance)
- Cost calculation with pricing table : Opus, Sonnet, Haiku, unknown model
- Markdown rendering shape (table headers, totals line)
- JSON output shape
- Token-not-recorded warning surfaced
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import console_db  # noqa: E402
from sdd_lib.console_db import (  # noqa: E402
    connect,
    ensure_initialized,
    insert_token_usage,
)
from sdd_scripts.report_roi import (  # noqa: E402
    collect_feat_data,
    main,
    model_cost,
    render_markdown,
)


def _fake_repo(tmp: str) -> Path:
    root = Path(tmp)
    (root / ".claude").mkdir()
    return root


def _seed_run(conn, feat_n: int, started: str, ended: str,
              status: str = "success", command: str = "/sdd-full",
              run_id: str | None = None) -> str:
    rid = run_id or f"run-{feat_n}-{started[:19]}"
    conn.execute(
        "INSERT INTO runs(run_id, command, feat_n, started_at, ended_at, status) "
        "VALUES(?,?,?,?,?,?)",
        (rid, command, feat_n, started, ended, status),
    )
    return rid


def _seed_feat(conn, feat_n: int, name: str = "test-feat") -> None:
    """FK precondition for qa_coverage / qa_* tables (schema cf. feats table)."""
    conn.execute(
        "INSERT OR IGNORE INTO feats(feat_n, name, file_path, "
        "status, ingested_at) VALUES(?,?,?,?,?)",
        (feat_n, name, f"workspace/input/feats/{feat_n}-{name}.md",
         "Validated", "2026-05-20T00:00:00.000Z"),
    )


def _seed_coverage(conn, feat_n: int, *, pct: float, total: int,
                   passed: int, failed: int, gate: bool) -> None:
    _seed_feat(conn, feat_n)
    conn.execute(
        "INSERT INTO qa_coverage(feat_n, extracted_at, stack, "
        "lines_pct, tests_total, tests_passed, tests_failed, "
        "coverage_passed) VALUES(?,?,?,?,?,?,?,?)",
        (feat_n, "2026-05-20T08:00:00.000Z", "qa-test",
         pct, total, passed, failed, 1 if gate else 0),
    )


class TestModelCost(unittest.TestCase):
    def test_opus_pricing(self) -> None:
        # 100k input + 10k output on Opus 4.7
        c = model_cost("claude-opus-4-7", 100_000, 10_000, 0, 0)
        # 100k * 15 / 1M + 10k * 75 / 1M = 1.5 + 0.75 = 2.25
        self.assertAlmostEqual(c, 2.25, places=2)

    def test_sonnet_pricing(self) -> None:
        c = model_cost("claude-sonnet-4-6", 100_000, 10_000, 0, 0)
        # 100k * 3 / 1M + 10k * 15 / 1M = 0.3 + 0.15 = 0.45
        self.assertAlmostEqual(c, 0.45, places=2)

    def test_haiku_pricing(self) -> None:
        c = model_cost("claude-haiku-4-5", 100_000, 10_000, 0, 0)
        # 0.1 + 0.05 = 0.15
        self.assertAlmostEqual(c, 0.15, places=2)

    def test_unknown_model_falls_back_to_sonnet(self) -> None:
        c = model_cost("claude-future-99", 100_000, 10_000, 0, 0)
        self.assertAlmostEqual(c, 0.45, places=2)

    def test_none_model_falls_back(self) -> None:
        c = model_cost(None, 1_000_000, 0, 0, 0)
        # 1M * 3 / 1M = 3.0
        self.assertAlmostEqual(c, 3.0, places=2)

    def test_cache_creation_billed(self) -> None:
        # Cache creation is 1.25/M on Sonnet
        c = model_cost("claude-sonnet-4-6", 0, 0, 1_000_000, 0)
        self.assertAlmostEqual(c, 3.75, places=2)

    def test_cache_read_billed_separately(self) -> None:
        # Cache read on Sonnet is 0.30/M
        c = model_cost("claude-sonnet-4-6", 0, 0, 0, 1_000_000)
        self.assertAlmostEqual(c, 0.30, places=2)


class TestCollectFeatData(unittest.TestCase):
    def test_empty_feat_no_runs_no_coverage(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    data = collect_feat_data(conn, 99)
            self.assertEqual(data["run_count"], 0)
            self.assertEqual(data["wall_clock_ms"], 0)
            self.assertFalse(data["tokens_recorded"])
            self.assertIsNone(data["coverage"])

    def test_single_run_with_tokens(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    _seed_run(conn, 1,
                              "2026-05-20T08:00:00.000Z",
                              "2026-05-20T08:30:00.000Z",
                              status="success")
                    insert_token_usage(
                        conn, agent="dev-backend", model="claude-opus-4-7",
                        feat_n=1, us_id="1-1",
                        input_tokens=100_000, output_tokens=10_000,
                        cache_creation_tokens=20_000, cache_read_tokens=50_000,
                    )
                    insert_token_usage(
                        conn, agent="po", model="claude-sonnet-4-6",
                        feat_n=1, us_id=None,
                        input_tokens=5_000, output_tokens=2_000,
                    )
                with connect() as conn:
                    data = collect_feat_data(conn, 1)
            self.assertEqual(data["run_count"], 1)
            # 30 minutes = 1800 s = 1_800_000 ms
            self.assertEqual(data["wall_clock_ms"], 1_800_000)
            self.assertTrue(data["tokens_recorded"])
            self.assertEqual(data["tokens"]["input"], 105_000)
            self.assertEqual(data["tokens"]["output"], 12_000)
            self.assertEqual(data["tokens"]["cache_creation"], 20_000)
            self.assertEqual(data["tokens"]["cache_read"], 50_000)
            # billed = input + output + cache_creation (cache_read excluded)
            self.assertEqual(data["tokens"]["billed_total"], 137_000)
            # cost = Opus(100k/10k/20k cc/50k cr) + Sonnet(5k/2k)
            #      = 1.5 + 0.75 + 0.375 + 0.075 + 0.015 + 0.030
            #      = ~2.745
            self.assertGreater(data["cost_usd"], 2.5)
            self.assertLess(data["cost_usd"], 3.0)

    def test_rework_detection(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    _seed_run(conn, 1,
                              "2026-05-20T08:00:00.000Z",
                              "2026-05-20T08:30:00.000Z",
                              run_id="r1")
                    _seed_run(conn, 1,
                              "2026-05-20T09:00:00.000Z",
                              "2026-05-20T09:45:00.000Z",
                              run_id="r2")
                    _seed_run(conn, 1,
                              "2026-05-20T10:00:00.000Z",
                              "2026-05-20T10:50:00.000Z",
                              run_id="r3")
                with connect() as conn:
                    data = collect_feat_data(conn, 1)
            self.assertEqual(data["run_count"], 3)
            # 3 sdd-full runs successful → 2 reworks, rework_rate = 2/3
            self.assertEqual(data["rework"], 2)
            self.assertAlmostEqual(data["rework_rate"], 2 / 3, places=2)
            self.assertEqual(data["failed_runs"], 0)

    def test_phase_timing_aggregation(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    _seed_run(conn, 7,
                              "2026-05-20T08:00:00.000Z",
                              "2026-05-20T09:00:00.000Z",
                              run_id="rA")
                    # 2 phases : dev (30 min, pass) + qa (15 min, fail)
                    conn.execute(
                        "INSERT INTO run_phases(run_id, phase, started_at, "
                        "ended_at, status) VALUES(?,?,?,?,?)",
                        ("rA", "dev",
                         "2026-05-20T08:00:00.000Z",
                         "2026-05-20T08:30:00.000Z", "pass"),
                    )
                    conn.execute(
                        "INSERT INTO run_phases(run_id, phase, started_at, "
                        "ended_at, status) VALUES(?,?,?,?,?)",
                        ("rA", "qa",
                         "2026-05-20T08:30:00.000Z",
                         "2026-05-20T08:45:00.000Z", "fail"),
                    )
                with connect() as conn:
                    data = collect_feat_data(conn, 7)
            phases = data["phases"]
            self.assertEqual(len(phases), 2)
            # Sorted by total_ms descending → dev (30m) first, qa (15m) second
            self.assertEqual(phases[0]["phase"], "dev")
            self.assertEqual(phases[0]["total_ms"], 1_800_000)
            self.assertEqual(phases[0]["pass_count"], 1)
            self.assertEqual(phases[0]["fail_count"], 0)
            self.assertEqual(phases[1]["phase"], "qa")
            self.assertEqual(phases[1]["total_ms"], 900_000)
            self.assertEqual(phases[1]["fail_count"], 1)

    def test_coverage_aggregation(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    _seed_coverage(conn, 1, pct=82.5, total=47,
                                   passed=45, failed=2, gate=True)
                with connect() as conn:
                    data = collect_feat_data(conn, 1)
            self.assertIsNotNone(data["coverage"])
            self.assertEqual(data["coverage"]["lines_pct"], 82.5)
            self.assertEqual(data["coverage"]["tests_total"], 47)
            self.assertTrue(data["coverage"]["gate_passed"])


class TestRenderMarkdown(unittest.TestCase):
    def test_renders_summary_table(self) -> None:
        payloads = [{
            "feat_n": 1, "run_count": 1, "wall_clock_ms": 1_800_000,
            "tokens": {"input": 100, "output": 10, "cache_creation": 0,
                       "cache_read": 0, "billed_total": 110, "agent_calls": 1},
            "tokens_by_agent": [{
                "agent": "dev-backend", "model": "claude-opus-4-7",
                "calls": 1, "input_tokens": 100, "output_tokens": 10,
                "cache_creation_tokens": 0, "cache_read_tokens": 0,
                "cost_usd": 0.0024,
            }],
            "tokens_recorded": True,
            "cost_usd": 0.0024,
            "context_budget": {"tokens_used_estimated": 0, "checks": 0,
                               "budget_failures": 0},
            "coverage": {"lines_pct": 82.5, "tests_total": 47,
                         "tests_passed": 45, "tests_failed": 2,
                         "gate_passed": True},
            "spec_compliance": {"verified": 5, "not_verified": 0, "partial": 0,
                                "total_acs": 5, "verification_rate_pct": 100.0},
            "issues": {"critical": 0, "serious": 1, "moderate": 2,
                       "minor": 3, "info": 4},
            "rework": 0,
            "rework_rate": 0.0,
            "failed_runs": 0,
            "phases": [],
            "runs": [],
        }]
        md = render_markdown(payloads)
        self.assertIn("# SDD_Pro ROI Report", md)
        self.assertIn("| FEAT | Runs", md)
        self.assertIn("82.5%", md)
        self.assertIn("100.0%", md)
        # Per-agent table
        self.assertIn("FEAT 1 -- tokens by agent", md)
        self.assertIn("claude-opus-4-7", md)

    def test_warning_when_tokens_not_recorded(self) -> None:
        payloads = [{
            "feat_n": 2, "run_count": 1, "wall_clock_ms": 0,
            "tokens": {"input": 0, "output": 0, "cache_creation": 0,
                       "cache_read": 0, "billed_total": 0, "agent_calls": 0},
            "tokens_by_agent": [],
            "tokens_recorded": False,
            "cost_usd": 0,
            "context_budget": {"tokens_used_estimated": 100_000, "checks": 5,
                               "budget_failures": 1},
            "coverage": None,
            "spec_compliance": None,
            "issues": {"critical": 0, "serious": 0, "moderate": 0,
                       "minor": 0, "info": 0},
            "rework": 0,
            "rework_rate": 0.0,
            "failed_runs": 0,
            "phases": [],
            "runs": [],
        }]
        md = render_markdown(payloads)
        self.assertIn("WARN : token_usage not recorded", md)
        self.assertIn("TokenUsageMode: record", md)


class TestCli(unittest.TestCase):
    def test_main_all_empty_db_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                try:
                    rc = main(["--all"])
                finally:
                    sys.stdout = old_stdout
            self.assertEqual(rc, 0)

    def test_main_feat_unknown_returns_2(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                old_err = sys.stderr
                sys.stderr = StringIO()
                try:
                    rc = main(["--feat", "999"])
                finally:
                    sys.stderr = old_err
            self.assertEqual(rc, 2)

    def test_main_json_output(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    _seed_run(conn, 1,
                              "2026-05-20T08:00:00.000Z",
                              "2026-05-20T08:30:00.000Z")
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                try:
                    rc = main(["--feat", "1", "--json"])
                    output = sys.stdout.getvalue()
                finally:
                    sys.stdout = old_stdout
            self.assertEqual(rc, 0)
            payload = json.loads(output)
            self.assertIn("feats", payload)
            self.assertEqual(len(payload["feats"]), 1)
            self.assertEqual(payload["feats"][0]["feat_n"], 1)


if __name__ == "__main__":
    unittest.main()
