"""Tests for sdd_admin.measure_cache_hit_rate (Levier 1b monitoring).

Verifies that the script correctly parses Claude Code JSONL session logs,
computes hit/write rates, and degrades gracefully on malformed input.
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_admin.measure_cache_hit_rate import (  # noqa: E402
    CacheStats,
    encode_path_for_claude_logs,
    format_report,
    parse_logs,
)

pytestmark = pytest.mark.smoke


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _turn(input_tokens: int, cache_read: int, cache_create: int,
          output: int = 100, model: str = "claude-opus-4-7",
          ephemeral_5m: int = 0, ephemeral_1h: int = 0) -> dict:
    return {
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create,
                "output_tokens": output,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": ephemeral_5m,
                    "ephemeral_1h_input_tokens": ephemeral_1h,
                },
            },
        },
    }


class TestCacheStats(unittest.TestCase):
    def test_total_input_sums_three_buckets(self):
        s = CacheStats(
            input_tokens=100, cache_read_input_tokens=300,
            cache_creation_input_tokens=200,
        )
        self.assertEqual(s.total_input, 600)

    def test_hit_rate_zero_when_no_input(self):
        self.assertEqual(CacheStats().cache_hit_rate, 0.0)

    def test_hit_rate_computed(self):
        s = CacheStats(input_tokens=100, cache_read_input_tokens=300,
                       cache_creation_input_tokens=200)
        self.assertAlmostEqual(s.cache_hit_rate, 0.5, places=4)
        self.assertAlmostEqual(s.cache_write_rate, 1 / 3, places=4)


class TestEncodePath(unittest.TestCase):
    def test_windows_path_encoded_with_double_dash(self):
        # The double-dash after the drive letter is the observed Claude Code convention
        encoded = encode_path_for_claude_logs(Path("C:\\DEV\\SDD-Pro"))
        self.assertEqual(encoded, "c--DEV-SDD-Pro")

    def test_nested_windows_path(self):
        encoded = encode_path_for_claude_logs(Path("C:\\DEV\\compart\\SDD_Pro"))
        self.assertEqual(encoded, "c--DEV-compart-SDD_Pro")


class TestParseLogs(unittest.TestCase):
    def test_empty_dir_yields_zero_stats(self, tmp_path: Path = None):
        tmp_path = tmp_path or Path(__file__).parent / "_tmp_empty_logs"
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            stats = parse_logs(tmp_path)
            self.assertEqual(stats.turns, 0)
            self.assertEqual(stats.total_input, 0)
        finally:
            if tmp_path.exists():
                for f in tmp_path.iterdir():
                    f.unlink()
                tmp_path.rmdir()

    def test_aggregates_multiple_turns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            _write_jsonl(logs / "session.jsonl", [
                _turn(input_tokens=10, cache_read=500, cache_create=100,
                      ephemeral_5m=100),
                _turn(input_tokens=20, cache_read=700, cache_create=0),
                _turn(input_tokens=15, cache_read=600, cache_create=50,
                      ephemeral_5m=50),
            ])
            stats = parse_logs(logs)
            self.assertEqual(stats.turns, 3)
            self.assertEqual(stats.input_tokens, 45)
            self.assertEqual(stats.cache_read_input_tokens, 1800)
            self.assertEqual(stats.cache_creation_input_tokens, 150)
            self.assertEqual(stats.ephemeral_5m, 150)
            self.assertEqual(stats.ephemeral_1h, 0)
            self.assertAlmostEqual(stats.cache_hit_rate, 1800 / 1995, places=4)

    def test_skips_non_assistant_records(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            _write_jsonl(logs / "mixed.jsonl", [
                {"type": "user", "message": {"content": "hello"}},
                _turn(input_tokens=5, cache_read=200, cache_create=0),
                {"type": "summary", "summary": "compaction"},
            ])
            stats = parse_logs(logs)
            self.assertEqual(stats.turns, 1)
            self.assertEqual(stats.cache_read_input_tokens, 200)

    def test_skips_malformed_lines(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            f = logs / "garbled.jsonl"
            f.write_text(
                "not-json-at-all\n"
                + json.dumps(_turn(input_tokens=1, cache_read=100, cache_create=0))
                + "\n{partial:",
                encoding="utf-8",
            )
            stats = parse_logs(logs)
            self.assertEqual(stats.turns, 1)
            self.assertEqual(stats.cache_read_input_tokens, 100)

    def test_since_epoch_filters_old_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            old = logs / "old.jsonl"
            recent = logs / "recent.jsonl"
            _write_jsonl(old, [_turn(input_tokens=1, cache_read=1000, cache_create=0)])
            _write_jsonl(recent, [_turn(input_tokens=1, cache_read=50, cache_create=0)])
            # Force old.jsonl mtime to 30 days ago
            old_ts = time.time() - 30 * 86400
            import os
            os.utime(old, (old_ts, old_ts))
            cutoff = time.time() - 7 * 86400
            stats = parse_logs(logs, since_epoch=cutoff)
            self.assertEqual(stats.turns, 1)
            self.assertEqual(stats.cache_read_input_tokens, 50)

    def test_per_model_breakdown(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            _write_jsonl(logs / "s.jsonl", [
                _turn(input_tokens=10, cache_read=100, cache_create=0,
                      model="claude-opus-4-7"),
                _turn(input_tokens=20, cache_read=200, cache_create=0,
                      model="claude-sonnet-4-6"),
                _turn(input_tokens=30, cache_read=300, cache_create=0,
                      model="claude-opus-4-7"),
            ])
            stats = parse_logs(logs)
            self.assertIn("claude-opus-4-7", stats.per_model)
            self.assertIn("claude-sonnet-4-6", stats.per_model)
            self.assertEqual(stats.per_model["claude-opus-4-7"]["turns"], 2)
            self.assertEqual(stats.per_model["claude-opus-4-7"]["cache_read"], 400)
            self.assertEqual(stats.per_model["claude-sonnet-4-6"]["turns"], 1)


class TestFormatReport(unittest.TestCase):
    def test_no_turns_message(self):
        out = format_report(CacheStats(), days=7)
        self.assertIn("No assistant turns", out)

    def test_report_contains_key_lines(self):
        s = CacheStats(
            turns=10, input_tokens=200, cache_read_input_tokens=500,
            cache_creation_input_tokens=300, output_tokens=400,
            ephemeral_5m=300, ephemeral_1h=0,
        )
        out = format_report(s, days=7)
        self.assertIn("Cache hit rate (last 7 days, 10 turns)", out)
        self.assertIn("cache_read", out)
        self.assertIn("cache_creation", out)
        self.assertIn("ephemeral_5m", out)
        self.assertIn("ephemeral_1h", out)


if __name__ == "__main__":
    unittest.main()
