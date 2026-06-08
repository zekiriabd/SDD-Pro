"""Tests for sdd_hooks.record_token_usage — defensive payload parsing."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks.record_token_usage import (
    USAGE_FIELDS,
    _extract_feat_and_us,
    _find_model,
    _find_usage,
    _hook_event_name,
)


class TestFindUsage(unittest.TestCase):
    def test_finds_usage_at_tool_response_usage(self):
        payload = {
            "tool_response": {
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 50,
                    "cache_read_input_tokens": 300,
                }
            }
        }
        usage, path = _find_usage(payload)
        self.assertIsNotNone(usage)
        self.assertEqual(path, "tool_response.usage")
        self.assertEqual(usage["input_tokens"], 1000)

    def test_finds_usage_at_tool_response_message_usage(self):
        payload = {
            "tool_response": {
                "message": {
                    "usage": {"input_tokens": 42, "output_tokens": 7}
                }
            }
        }
        usage, path = _find_usage(payload)
        self.assertIsNotNone(usage)
        self.assertEqual(path, "tool_response.message.usage")
        self.assertEqual(usage["input_tokens"], 42)

    def test_finds_usage_at_root(self):
        payload = {"usage": {"input_tokens": 1, "output_tokens": 2}}
        usage, path = _find_usage(payload)
        self.assertIsNotNone(usage)
        self.assertEqual(path, "usage")

    def test_returns_none_when_no_usage(self):
        payload = {"tool_response": {"message": "hello"}}
        usage, path = _find_usage(payload)
        self.assertIsNone(usage)
        self.assertIsNone(path)

    def test_ignores_usage_dict_without_known_fields(self):
        payload = {"usage": {"unrelated_field": 1}}
        usage, path = _find_usage(payload)
        self.assertIsNone(usage)

    def test_first_candidate_wins(self):
        payload = {
            "tool_response": {"usage": {"input_tokens": 100}},
            "usage": {"input_tokens": 999},
        }
        usage, path = _find_usage(payload)
        self.assertEqual(path, "tool_response.usage")
        self.assertEqual(usage["input_tokens"], 100)


class TestFindModel(unittest.TestCase):
    def test_finds_model_at_tool_response(self):
        payload = {"tool_response": {"model": "claude-opus-4-7"}}
        self.assertEqual(_find_model(payload), "claude-opus-4-7")

    def test_finds_model_at_tool_response_message(self):
        payload = {"tool_response": {"message": {"model": "claude-sonnet-4-6"}}}
        self.assertEqual(_find_model(payload), "claude-sonnet-4-6")

    def test_finds_model_at_root(self):
        payload = {"model": "claude-haiku-4-5"}
        self.assertEqual(_find_model(payload), "claude-haiku-4-5")

    def test_returns_none_when_missing(self):
        self.assertIsNone(_find_model({"tool_response": {}}))

    def test_ignores_non_string(self):
        self.assertIsNone(_find_model({"model": 123}))

    def test_strips_whitespace(self):
        self.assertEqual(_find_model({"model": "  claude-opus  "}), "claude-opus")


class TestExtractFeatAndUs(unittest.TestCase):
    def test_extracts_us_id(self):
        payload = {"tool_input": {"prompt": "dispatch dev-backend on 1-2-Auth"}}
        feat, us_id = _extract_feat_and_us(payload)
        self.assertEqual(feat, 1)
        self.assertEqual(us_id, "1-2")

    def test_extracts_feat_only(self):
        payload = {"tool_input": {"prompt": "running /sdd-full 3 for new feature"}}
        feat, us_id = _extract_feat_and_us(payload)
        self.assertEqual(feat, 3)
        self.assertIsNone(us_id)

    def test_returns_none_when_no_match(self):
        payload = {"tool_input": {"prompt": "no numeric context here"}}
        feat, us_id = _extract_feat_and_us(payload)
        self.assertIsNone(feat)
        self.assertIsNone(us_id)

    def test_uses_description_when_prompt_empty(self):
        payload = {"tool_input": {"prompt": "", "description": "us-generate 5"}}
        feat, us_id = _extract_feat_and_us(payload)
        self.assertEqual(feat, 5)

    def test_handles_missing_tool_input(self):
        feat, us_id = _extract_feat_and_us({})
        self.assertIsNone(feat)
        self.assertIsNone(us_id)


class TestHookEventName(unittest.TestCase):
    def test_explicit_hook_event_name_post_tool_use_with_tool_name(self):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Agent"}
        self.assertEqual(_hook_event_name(payload), "PostToolUse.Agent")

    def test_explicit_subagent_stop(self):
        payload = {"hook_event_name": "SubagentStop"}
        self.assertEqual(_hook_event_name(payload), "SubagentStop")

    def test_fallback_post_tool_use_via_tool_response(self):
        payload = {"tool_response": {"foo": "bar"}}
        self.assertEqual(_hook_event_name(payload), "PostToolUse.Agent")

    def test_fallback_subagent_stop_when_no_indicator(self):
        payload = {"unrelated": "field"}
        self.assertEqual(_hook_event_name(payload), "SubagentStop")


class TestMainBehaviour(unittest.TestCase):
    """Black-box test of main(): verify mode=off is a strict no-op.

    v7.0.1 audit P2 perf — _resolve_mode() is now memoized via _MODE_CACHE
    and lazy-imports layered_config. Each test must reset the cache to
    avoid cross-test leakage.
    """

    def setUp(self) -> None:
        from sdd_hooks import record_token_usage as mod
        mod._MODE_CACHE = None

    def test_mode_off_is_noop(self):
        from sdd_hooks import record_token_usage as mod

        with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "off"}, clear=False):
            with mock.patch.object(mod, "read_hook_input") as mock_read:
                rc = mod.main()
                self.assertEqual(rc, 0)
                mock_read.assert_not_called()

    def test_unknown_mode_is_noop(self):
        """v7.0.0 : env unknown value falls through to layered config.
        With config also returning unknown/off, mode resolves to 'off' and
        read_hook_input must not be called.

        v7.0.1 : layered_config is now lazy-imported inside _resolve_mode,
        so we patch at the source module (sdd_lib.layered_config) rather
        than at record_token_usage module attribute (which no longer holds
        a reference at module load time).
        """
        from sdd_hooks import record_token_usage as mod

        with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "garbage"}, clear=False):
            with mock.patch(
                "sdd_lib.layered_config.read_layered_config",
                return_value={"TokenUsageMode": "off"},
            ):
                with mock.patch.object(mod, "read_hook_input") as mock_read:
                    rc = mod.main()
                    self.assertEqual(rc, 0)
                    mock_read.assert_not_called()

    def test_record_mode_writes_db_row(self):
        """v6.10: hook now writes to console.db (token_usage table)."""
        import sqlite3
        import tempfile
        from sdd_hooks import record_token_usage as mod
        from sdd_lib import console_db

        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "dev-backend",
                "prompt": "implement 1-2-Auth backend",
            },
            "tool_response": {
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 5000,
                    "output_tokens": 800,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 2000,
                },
            },
        }

        with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "record"}, clear=False):
            with mock.patch.object(mod, "read_hook_input", return_value=payload):
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                    tmp_root = Path(tmp)
                    (tmp_root / ".claude").mkdir()
                    # Patch repo_root in BOTH modules so default_db_path() resolves
                    # to the temp directory.
                    with mock.patch.object(mod, "repo_root", return_value=tmp_root), \
                         mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                        rc = mod.main()
                        self.assertEqual(rc, 0)

                        db_path = tmp_root / "workspace" / "output" / "db" / "console.db"
                        self.assertTrue(db_path.is_file(),
                                        f"console.db should exist at {db_path}")
                        conn = sqlite3.connect(str(db_path))
                        conn.row_factory = sqlite3.Row
                        try:
                            row = conn.execute(
                                "SELECT * FROM token_usage ORDER BY id DESC LIMIT 1"
                            ).fetchone()
                        finally:
                            conn.close()
                        self.assertIsNotNone(row, "token_usage should contain one row")
                        self.assertEqual(row["agent"], "dev-backend")
                        self.assertEqual(row["model"], "claude-opus-4-7")
                        self.assertEqual(row["input_tokens"], 5000)
                        self.assertEqual(row["output_tokens"], 800)
                        self.assertEqual(row["cache_creation_tokens"], 100)
                        self.assertEqual(row["cache_read_tokens"], 2000)
                        self.assertEqual(row["feat_n"], 1)
                        self.assertEqual(row["us_id"], "1-2")

    def test_record_mode_handles_missing_usage(self):
        """v6.10: missing usage still inserts a DB row with zeros."""
        import sqlite3
        import tempfile
        from sdd_hooks import record_token_usage as mod
        from sdd_lib import console_db

        payload = {
            "tool_input": {"subagent_type": "po", "prompt": "us-generate 1"},
            "tool_response": {"message": "no usage exposed by Claude Code"},
        }

        with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "record"}, clear=False):
            with mock.patch.object(mod, "read_hook_input", return_value=payload):
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                    tmp_root = Path(tmp)
                    (tmp_root / ".claude").mkdir()
                    with mock.patch.object(mod, "repo_root", return_value=tmp_root), \
                         mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                        rc = mod.main()
                        self.assertEqual(rc, 0)

                        db_path = tmp_root / "workspace" / "output" / "db" / "console.db"
                        self.assertTrue(db_path.is_file())
                        conn = sqlite3.connect(str(db_path))
                        conn.row_factory = sqlite3.Row
                        try:
                            row = conn.execute(
                                "SELECT * FROM token_usage ORDER BY id DESC LIMIT 1"
                            ).fetchone()
                        finally:
                            conn.close()
                        self.assertIsNotNone(row)
                        self.assertEqual(row["input_tokens"], 0)
                        self.assertEqual(row["output_tokens"], 0)
                        self.assertEqual(row["cache_creation_tokens"], 0)
                        self.assertEqual(row["cache_read_tokens"], 0)

    def test_empty_payload_returns_zero(self):
        from sdd_hooks import record_token_usage as mod

        with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "record"}, clear=False):
            with mock.patch.object(mod, "read_hook_input", return_value={}):
                rc = mod.main()
                self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
