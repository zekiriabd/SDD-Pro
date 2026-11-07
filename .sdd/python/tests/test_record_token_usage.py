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
    _extract_feat_and_us_from_text,
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


class TestExtractFeatAndUsMisattribution(unittest.TestCase):
    """Audit télémétrie 2026-11-07 : dates et plages lues comme des US (FEAT 84, 201)."""

    KNOWN = ({"15-1", "15-2", "6-3"}, {6, 15})

    def test_dates_are_not_us(self):
        for text in ("audit 2026-11-06", "run 2026-10-10T12:00", "sdd-full 2026-11-07"):
            with self.subTest(text=text):
                self.assertEqual(_extract_feat_and_us_from_text(text), (None, None))

    def test_versions_and_times_are_not_us(self):
        for text in ("v1.2-3", "à 10:10-11"):
            with self.subTest(text=text):
                self.assertEqual(_extract_feat_and_us_from_text(text), (None, None))

    def test_line_range_rejected_when_not_on_disk(self):
        text = "lis les lignes 84-92 du fichier"
        self.assertEqual(_extract_feat_and_us_from_text(text), (84, "84-92"))  # syntaxe seule
        self.assertEqual(_extract_feat_and_us_from_text(text, self.KNOWN), (None, None))

    def test_skips_unknown_candidate_and_falls_back_to_feat(self):
        text = "lines 201-215 then /dev-run 15"
        self.assertEqual(_extract_feat_and_us_from_text(text, self.KNOWN), (15, None))

    def test_unknown_feat_rejected(self):
        self.assertEqual(_extract_feat_and_us_from_text("FEAT 84", self.KNOWN), (None, None))

    def test_real_us_still_found(self):
        for text, expected in (
            ("ts 2026-10-10 puis US 15-1-Consulter-Mes-Donnees", (15, "15-1")),
            ("Lis workspace/us/15-1-Consulter-Mes-Donnees.md", (15, "15-1")),
            ("US 15-2.", (15, "15-2")),
            ("(US 6-3)", (6, "6-3")),
        ):
            with self.subTest(text=text):
                self.assertEqual(_extract_feat_and_us_from_text(text, self.KNOWN), expected)

    def test_known_ids_reads_workspace(self):
        import tempfile
        from sdd_hooks.record_token_usage import _known_ids
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d) / "workspace"
            (ws / "us").mkdir(parents=True)
            (ws / "feats").mkdir()
            (ws / "us" / "15-1-Consulter-Mes-Donnees.md").write_text("x", encoding="utf-8")
            (ws / "feats" / "15-Mes-donnees.md").write_text("x", encoding="utf-8")
            (ws / "us" / "notes.md").write_text("x", encoding="utf-8")
            self.assertEqual(_known_ids(Path(d)), ({"15-1"}, {15}))

    def test_known_ids_none_without_workspace_content(self):
        import tempfile
        from sdd_hooks.record_token_usage import _known_ids
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "workspace").mkdir()
            self.assertIsNone(_known_ids(Path(d)))


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

    def test_post_tool_use_usage_is_no_longer_a_source(self):
        """Audit tokens 2026-11-07 : `tool_response.usage` ne porte que le
        dernier appel API (synchrone) ou rien (asynchrone). Le hook n'écrit
        plus AUCUNE ligne au PostToolUse — la source est le transcript lu au
        SubagentStop (cf. tests/test_transcript_usage.py)."""
        import tempfile
        from sdd_hooks import record_token_usage as mod
        from sdd_lib import console_db

        for tool_response in ({"model": "claude-opus-4-7",
                               "usage": {"input_tokens": 5000, "output_tokens": 800}},
                              {"message": "no usage exposed by Claude Code"}):
            payload = {
                "hook_event_name": "PostToolUse", "tool_name": "Agent",
                "tool_input": {"subagent_type": "dev-backend", "prompt": "1-2-Auth"},
                "tool_response": tool_response,
            }
            mod._MODE_CACHE = None
            with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "record"}, clear=False),                  mock.patch.object(mod, "read_hook_input", return_value=payload),                  tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                tmp_root = Path(tmp)
                (tmp_root / ".claude").mkdir()
                with mock.patch.object(mod, "repo_root", return_value=tmp_root),                      mock.patch.object(console_db.core, "repo_root", return_value=tmp_root):
                    self.assertEqual(mod.main(), 0)
                    db_path = tmp_root / "workspace" / "db" / "console.db"
                    self.assertFalse(db_path.is_file(),
                                     "PostToolUse must not create token_usage rows")

    def test_empty_payload_returns_zero(self):
        from sdd_hooks import record_token_usage as mod

        with mock.patch.dict(os.environ, {"SDD_TOKEN_USAGE_MODE": "record"}, clear=False):
            with mock.patch.object(mod, "read_hook_input", return_value={}):
                rc = mod.main()
                self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
