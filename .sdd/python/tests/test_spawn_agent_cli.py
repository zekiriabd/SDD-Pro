"""Unit tests for sdd_scripts/spawn_agent_cli.py (audit R4, 2026-07-26)."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

# `sdd_scripts` package is loaded via runtime path insert; add the sdd_scripts
# subfolder to the module search path so `spawn_agent_cli` imports cleanly.
_SCRIPTS_ROOT = _PYTHON_ROOT / "sdd_scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import spawn_agent_cli  # noqa: E402


class TestParser(unittest.TestCase):
    def test_help_ok(self):
        p = spawn_agent_cli.build_parser()
        self.assertIsNotNone(p)
        # Verify required flags are declared.
        # We inspect the parser actions rather than run the CLI.
        dests = {a.dest for a in p._actions}
        for expected in ("agent", "task", "task_file", "harness",
                         "provider", "tier", "schema_file", "timeout_s"):
            self.assertIn(expected, dests, f"missing --{expected} flag")

    def test_mutual_exclusion_task_vs_task_file(self):
        p = spawn_agent_cli.build_parser()
        # argparse will exit(2) on wrong usage; use SystemExit context.
        with self.assertRaises(SystemExit):
            p.parse_args(["--agent", "po"])  # neither --task nor --task-file


class TestResolveDefaultsFromStackMd(unittest.TestCase):
    """When stack.md is absent or unreadable, defaults must be safe."""

    def test_absent_stack_md_returns_reference_defaults(self):
        # Point to a temp dir with NO stack.md → falls back to defaults.
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"SDD_REPO_ROOT": tmp}, clear=False):
                harness, provider = spawn_agent_cli._resolve_defaults_from_stack_md()
        self.assertEqual((harness, provider), ("claude-code", "anthropic"))


class TestAgentPromptLoading(unittest.TestCase):
    def test_missing_agent_exits_infra_blocked(self):
        with self.assertRaises(SystemExit) as ctx:
            spawn_agent_cli._load_agent_prompt("no-such-agent-xyz-12345")
        self.assertEqual(ctx.exception.code, 3)  # INFRA_BLOCKED

    def test_real_agent_loads(self):
        # The po agent is guaranteed present in the SSoT.
        content = spawn_agent_cli._load_agent_prompt("po")
        self.assertGreater(len(content), 100)  # non-trivial size


class TestMainWithInjectedRunner(unittest.TestCase):
    """End-to-end test with an injected runner (offline, no CLI/token)."""

    def test_main_success_with_fake_runner(self):
        # Patch spawn_agent's default runner path : we craft a fake runner
        # that always returns a valid JSON matching the default schema.
        from sdd_lib.spawn_agent import RunResult

        def fake_runner(argv, timeout_s, cwd):
            return RunResult(exit_code=0, stdout='{"result": "OK from fake runner"}')

        # Instead of monkey-patching the runner through CLI (which uses
        # cfg.runner=None by default), we call the underlying library
        # directly to prove the wiring is well-formed. This is what a
        # future integration test would exercise via subprocess.
        from sdd_lib.spawn_agent import spawn_agent, SpawnConfig, AgentSpec

        result = spawn_agent(
            AgentSpec(
                system_prompt="You are a test agent.",
                task="say OK",
                output_schema={"type": "object", "required": ["result"],
                               "properties": {"result": {"type": "string"}}},
                label="unit-test",
            ),
            SpawnConfig(harness="codex", runner=fake_runner),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["parsed"], {"result": "OK from fake runner"})

    def test_main_writes_json_to_stdout(self):
        # Wire the CLI to a synthetic environment : the agent file must
        # exist, the runner returns valid JSON. This tests the *wiring*
        # (CLI → library → JSON output), not the LLM behavior.
        from sdd_lib.spawn_agent import RunResult

        def fake_runner(argv, timeout_s, cwd):
            return RunResult(
                exit_code=0,
                stdout='{"result": "hello", "notes": "wired"}',
            )

        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            with mock.patch(
                "sdd_lib.spawn_agent._default_runner", side_effect=fake_runner,
            ):
                rc = spawn_agent_cli.main([
                    "--agent", "po",
                    "--task", "trivial test",
                    "--harness", "codex",
                    "--provider", "anthropic",  # cheat : anthropic tier_map for the model resolver
                    "--timeout-s", "10",
                ])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["parsed"], {"result": "hello", "notes": "wired"})
        self.assertEqual(payload["agent"], "po")
        self.assertEqual(payload["harness"], "codex")


if __name__ == "__main__":
    unittest.main()
