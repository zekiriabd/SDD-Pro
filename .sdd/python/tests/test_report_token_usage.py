"""Tests for sdd_scripts.report_token_usage — aggregation + filters."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.report_token_usage import (
    _load_ledger,
    _passes_filters,
    _total_tokens,
    aggregate,
    main,
)


def _make_entry(
    feat: int | None = 1,
    us_id: str | None = "1-2",
    agent: str = "dev-backend",
    input_t: int = 1000,
    output_t: int = 200,
    cache_creation: int = 50,
    cache_read: int = 100,
    found: bool = True,
    ts: str = "2026-05-15T10:00:00.000Z",
) -> dict:
    return {
        "ts": ts,
        "hook_event": "PostToolUse.Agent",
        "subagent_type": agent,
        "feat": feat,
        "us_id": us_id,
        "model": "claude-opus-4-7",
        "input_tokens": input_t if found else None,
        "output_tokens": output_t if found else None,
        "cache_creation_input_tokens": cache_creation if found else None,
        "cache_read_input_tokens": cache_read if found else None,
        "raw_usage_found": found,
        "usage_source_path": "tool_response.usage" if found else None,
    }


class TestLoadLedger(unittest.TestCase):
    """v6.10: _load_ledger now reads from console.db (token_usage table)
    instead of a JSONL file. The path argument is accepted but ignored."""

    def test_empty_when_db_empty(self):
        """Use a temp repo so the DB is fresh and empty."""
        from unittest import mock
        from sdd_lib import console_db

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_root = Path(tmp)
            (tmp_root / ".claude").mkdir()
            with mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                self.assertEqual(_load_ledger(), [])

    def test_loads_db_rows(self):
        """Insert two rows into token_usage and verify _load_ledger returns
        them with the legacy entry shape (subagent_type, feat, …)."""
        from unittest import mock
        from sdd_lib import console_db
        from sdd_lib.console_db import connect, ensure_initialized, insert_token_usage

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_root = Path(tmp)
            (tmp_root / ".claude").mkdir()
            with mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                ensure_initialized()
                with connect() as conn:
                    insert_token_usage(
                        conn, agent="dev-backend", model="claude-opus-4-7",
                        feat_n=1, us_id="1-2",
                        input_tokens=1000, output_tokens=200,
                        cache_creation_tokens=50, cache_read_tokens=100,
                    )
                    insert_token_usage(
                        conn, agent="qa", model="claude-sonnet-4-6",
                        feat_n=2, us_id=None,
                        input_tokens=500, output_tokens=80,
                    )
                entries = _load_ledger()
                self.assertEqual(len(entries), 2)
                # Mapping: agent → subagent_type, feat_n → feat
                self.assertEqual(entries[0]["subagent_type"], "dev-backend")
                self.assertEqual(entries[0]["feat"], 1)
                self.assertEqual(entries[1]["subagent_type"], "qa")
                self.assertEqual(entries[1]["feat"], 2)
                # raw_usage_found inferred from token presence
                self.assertTrue(entries[0]["raw_usage_found"])


class TestFilters(unittest.TestCase):
    def test_feat_filter(self):
        entry = _make_entry(feat=1)
        self.assertTrue(_passes_filters(entry, feat=1, agent=None, since=None, us_id=None))
        self.assertFalse(_passes_filters(entry, feat=2, agent=None, since=None, us_id=None))

    def test_agent_filter(self):
        entry = _make_entry(agent="qa")
        self.assertTrue(_passes_filters(entry, feat=None, agent="qa", since=None, us_id=None))
        self.assertFalse(_passes_filters(entry, feat=None, agent="po", since=None, us_id=None))

    def test_since_filter(self):
        entry = _make_entry(ts="2026-05-15T10:00:00.000Z")
        self.assertTrue(
            _passes_filters(entry, feat=None, agent=None, since="2026-05-15T09:00:00Z", us_id=None)
        )
        self.assertFalse(
            _passes_filters(entry, feat=None, agent=None, since="2026-05-15T11:00:00Z", us_id=None)
        )

    def test_us_filter(self):
        entry = _make_entry(us_id="1-2")
        self.assertTrue(_passes_filters(entry, feat=None, agent=None, since=None, us_id="1-2"))
        self.assertFalse(_passes_filters(entry, feat=None, agent=None, since=None, us_id="1-3"))


class TestAggregate(unittest.TestCase):
    def test_global_totals(self):
        entries = [
            _make_entry(agent="dev-backend", input_t=1000, output_t=100),
            _make_entry(agent="dev-frontend", input_t=2000, output_t=300),
            _make_entry(agent="dev-backend", input_t=500, output_t=50),
        ]
        agg = aggregate(entries)
        g = agg["global"]
        self.assertEqual(g["calls"], 3)
        self.assertEqual(g["input_tokens"], 3500)
        self.assertEqual(g["output_tokens"], 450)

    def test_by_agent_grouping(self):
        entries = [
            _make_entry(agent="dev-backend", input_t=1000),
            _make_entry(agent="dev-frontend", input_t=2000),
            _make_entry(agent="dev-backend", input_t=500),
        ]
        agg = aggregate(entries)
        self.assertEqual(agg["by_agent"]["dev-backend"]["calls"], 2)
        self.assertEqual(agg["by_agent"]["dev-backend"]["input_tokens"], 1500)
        self.assertEqual(agg["by_agent"]["dev-frontend"]["calls"], 1)

    def test_by_feat_grouping(self):
        entries = [
            _make_entry(feat=1, input_t=1000),
            _make_entry(feat=2, input_t=2000),
            _make_entry(feat=None, input_t=500),
        ]
        agg = aggregate(entries)
        self.assertEqual(agg["by_feat"]["feat-1"]["calls"], 1)
        self.assertEqual(agg["by_feat"]["feat-2"]["calls"], 1)
        self.assertEqual(agg["by_feat"]["(no-feat)"]["calls"], 1)

    def test_missing_usage_counted_separately(self):
        entries = [
            _make_entry(found=True, input_t=1000),
            _make_entry(found=False),
            _make_entry(found=False),
        ]
        agg = aggregate(entries)
        g = agg["global"]
        self.assertEqual(g["calls"], 3)
        self.assertEqual(g["missing_usage"], 2)
        # only the one with usage contributes tokens
        self.assertEqual(g["input_tokens"], 1000)

    def test_total_tokens_excludes_cache_read(self):
        bucket = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 30,
            "cache_read_input_tokens": 999,  # not counted in billing total
            "calls": 1,
            "missing_usage": 0,
        }
        self.assertEqual(_total_tokens(bucket), 180)


class TestCli(unittest.TestCase):
    def test_main_no_ledger_returns_zero(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            ledger = Path(tmp) / "absent.jsonl"
            # capture stdout
            from io import StringIO
            old = sys.stdout
            sys.stdout = StringIO()
            try:
                rc = main(["--ledger", str(ledger)])
                self.assertEqual(rc, 0)
            finally:
                sys.stdout = old

    def test_main_json_output(self):
        from unittest import mock
        from sdd_lib import console_db
        from sdd_lib.console_db import connect, ensure_initialized, insert_token_usage

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_root = Path(tmp)
            (tmp_root / ".claude").mkdir()
            with mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                ensure_initialized()
                with connect() as conn:
                    insert_token_usage(
                        conn, agent="dev-backend", model="claude-opus-4-7",
                        feat_n=1, us_id="1-2",
                        input_tokens=1000, output_tokens=200,
                    )

                from io import StringIO
                old = sys.stdout
                sys.stdout = StringIO()
                try:
                    rc = main(["--json"])
                    output = sys.stdout.getvalue()
                finally:
                    sys.stdout = old
            self.assertEqual(rc, 0)
            payload = json.loads(output)
            self.assertIn("global", payload)
            self.assertEqual(payload["entry_count"], 1)

    def test_main_writes_output_file(self):
        from unittest import mock
        from sdd_lib import console_db
        from sdd_lib.console_db import connect, ensure_initialized, insert_token_usage

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_root = Path(tmp)
            (tmp_root / ".claude").mkdir()
            with mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                ensure_initialized()
                with connect() as conn:
                    insert_token_usage(
                        conn, agent="dev-backend", model="claude-opus-4-7",
                        feat_n=1, us_id="1-2",
                        input_tokens=1000, output_tokens=200,
                    )

                out_md = tmp_root / "out.md"
                from io import StringIO
                sys.stdout = StringIO()
                try:
                    rc = main(["--output", str(out_md)])
                finally:
                    sys.stdout = sys.__stdout__
                self.assertEqual(rc, 0)
                self.assertTrue(out_md.is_file())
                content = out_md.read_text(encoding="utf-8")
                self.assertIn("Token usage report", content)


if __name__ == "__main__":
    unittest.main()
