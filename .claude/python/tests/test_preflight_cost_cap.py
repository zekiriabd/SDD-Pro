"""Tests for sdd_hooks.preflight_cost_cap — PreToolUse.Agent USD cap gate.

Mix of :
  - In-process helpers (pricing math, env-driven cap resolution).
  - Subprocess lifecycle (stdin JSON → exit code), with a fully isolated
    tmp $SDD_REPO_ROOT + initialized console.db so we can seed
    token_usage rows that push cumulative cost above the cap.

The hook v7.0.0 R1 fix is the key invariant under test : at >= 100% of cap,
HARD BLOCK in all contexts (no more CI-only blocking). Bypass strictly via
$SDD_DISABLE_COST_CAP or MaxCostPerRun=0 config.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.pricing import PRICING  # noqa: E402

HOOK = _PY_ROOT / "sdd_hooks" / "preflight_cost_cap.py"

CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    for k in ("SDD_DISABLE_COST_CAP", "SDD_RUN_ID", "SDD_REPO_ROOT"):
        env.pop(k, None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


def _run_hook(payload: dict, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        env=_clean_env(env_extra),
        capture_output=True,
        text=True,
        check=False,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Synthetic SDD repo skeleton matching sdd_lib.paths._looks_like_repo_root."""
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "workspace").mkdir()
    return tmp_path


def _seed_token_usage(repo: Path, run_id: str, input_tokens: int, output_tokens: int,
                      model: str = "claude-opus-4-7"):
    """Insert a token_usage row in console.db at the given run_id scope.

    Schema constraint: token_usage.run_id FK -> runs(run_id). We must first
    upsert the corresponding runs row, otherwise insertion fails with
    sqlite3.IntegrityError (FOREIGN KEY constraint failed).
    """
    # Lazy import (ensures sys.path is set by conftest first)
    from sdd_lib import console_db

    db_path = repo / "workspace" / "output" / "db" / "console.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["SDD_REPO_ROOT"] = str(repo)
    try:
        console_db.ensure_initialized(db_path)
        with console_db.connect(db_path) as conn:
            # Parent run row required by FK constraint
            console_db.upsert_run(
                conn,
                run_id=run_id,
                command="/test",
                status="running",
            )
            console_db.insert_token_usage(
                conn,
                agent="dev-backend",
                model=model,
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
    finally:
        os.environ.pop("SDD_REPO_ROOT", None)


# ============================================================================
# In-process : pricing sanity + env-driven cap resolution
# ============================================================================

class TestPricingTable(unittest.TestCase):
    """The hook reads from sdd_lib.pricing — verify the table is well-formed."""

    def test_opus_priced_correctly(self):
        p = PRICING["claude-opus-4-7"]
        self.assertEqual(p["input"], 15.00)
        self.assertEqual(p["output"], 75.00)

    def test_cache_creation_is_125x_input(self):
        """Anthropic convention : cache_creation = input * 1.25."""
        for model, p in PRICING.items():
            self.assertAlmostEqual(p["cache_creation"], p["input"] * 1.25,
                                   places=2,
                                   msg=f"{model} cache_creation mismatch")

    def test_cache_read_is_10pct_input(self):
        """Anthropic convention : cache_read = input * 0.10."""
        for model, p in PRICING.items():
            self.assertAlmostEqual(p["cache_read"], p["input"] * 0.10,
                                   places=2,
                                   msg=f"{model} cache_read mismatch")


# ============================================================================
# Subprocess : full hook lifecycle
# ============================================================================

class TestCostCapDisabled(unittest.TestCase):
    """Disabled cap paths : explicit bypass must allow without DB lookup."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_disable_env_var_skips_check(self):
        """SDD_DISABLE_COST_CAP=1 → cap=0 → exit 0 immediately."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_DISABLE_COST_CAP": "1",
        })
        self.assertEqual(r.returncode, 0)
        # No emission expected
        self.assertNotIn("[COST_CAP_EXCEEDED]", r.stderr)

    def test_empty_payload_exits_zero(self):
        r = _run_hook({}, {"SDD_REPO_ROOT": str(self.repo)})
        self.assertEqual(r.returncode, 0)

    def test_missing_subagent_exits_zero(self):
        """Hook only meaningful for Agent invocations."""
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        r = _run_hook(payload, {"SDD_REPO_ROOT": str(self.repo)})
        self.assertEqual(r.returncode, 0)


class TestCostCapBelowThreshold(unittest.TestCase):
    """Below 80% : no emission. Between 80-100% : WARN but allow."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_db_no_emission(self):
        """No console.db → cost = 0 → exit 0, no warning."""
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": "test-run-empty",
        })
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("[COST_CAP_EXCEEDED]", r.stderr)

    def test_low_cost_passes_without_warning(self):
        """1k input + 100 output tokens Opus ≈ $0.0225, far below $50 cap."""
        run_id = "test-run-low"
        _seed_token_usage(self.repo, run_id, input_tokens=1000, output_tokens=100)

        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": run_id,
        })
        self.assertEqual(r.returncode, 0, f"STDERR={r.stderr}")
        self.assertNotIn("[COST_CAP_EXCEEDED]", r.stderr)


class TestCostCapBlocking(unittest.TestCase):
    """At >= 100% : HARD BLOCK always (v7.0.0 R1 fix — no CI exception).

    Opus pricing: $15/M input + $75/M output. To exceed $50 cap with
    1 row, we need a big enough call. We seed 3M input + 100k output =
    $15 * 3 + $75 * 0.1 = $45 + $7.5 = $52.5 → > $50.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_above_cap_blocks_in_interactive(self):
        """Was the legacy interactive bypass — now blocks per R1 fix."""
        run_id = "test-run-over-cap"
        _seed_token_usage(self.repo, run_id,
                          input_tokens=3_000_000, output_tokens=100_000)

        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        # No CI vars, no SDD_BUDGET_MODE override → previous behavior would WARN-only
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": run_id,
        })
        self.assertEqual(r.returncode, 2,
                         f"Expected DENY (R1 fix), got {r.returncode}\nSTDERR={r.stderr}")
        self.assertIn("[COST_CAP_EXCEEDED]", r.stderr)

    def test_above_cap_blocks_in_ci(self):
        """CI context → also blocks (same code path)."""
        run_id = "test-run-over-cap-ci"
        _seed_token_usage(self.repo, run_id,
                          input_tokens=3_000_000, output_tokens=100_000)

        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": run_id,
            "CI": "true",
        })
        self.assertEqual(r.returncode, 2)
        self.assertIn("[COST_CAP_EXCEEDED]", r.stderr)

    def test_error_message_mentions_actual_amount(self):
        """Stderr line must include $cost / $cap for operator clarity."""
        run_id = "test-run-msg"
        _seed_token_usage(self.repo, run_id,
                          input_tokens=4_000_000, output_tokens=0)
        # $15 * 4 = $60 > $50

        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "po"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": run_id,
        })
        self.assertEqual(r.returncode, 2)
        # Must surface dollar amounts and the FIX hint
        self.assertIn("$", r.stderr)
        self.assertIn("FIX", r.stderr)

    def test_bypass_env_var_overrides_blocking(self):
        """SDD_DISABLE_COST_CAP=1 short-circuits before DB lookup, even over cap."""
        run_id = "test-run-bypass"
        _seed_token_usage(self.repo, run_id,
                          input_tokens=10_000_000, output_tokens=0)

        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": run_id,
            "SDD_DISABLE_COST_CAP": "1",
        })
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("[COST_CAP_EXCEEDED]", r.stderr)


class TestCostCapRunIdScoping(unittest.TestCase):
    """Confirm cost is scoped to the current run (no crosstalk between runs)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_other_run_cost_does_not_leak(self):
        """Token usage on run-A should not block agent invocation in run-B."""
        # Seed an over-cap cost on run-A
        _seed_token_usage(self.repo, "run-A",
                          input_tokens=10_000_000, output_tokens=0)

        # Invoke for run-B — fresh, should pass
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        r = _run_hook(payload, {
            "SDD_REPO_ROOT": str(self.repo),
            "SDD_RUN_ID": "run-B",
        })
        self.assertEqual(r.returncode, 0,
                         f"Run-B must not see run-A's cost; STDERR={r.stderr}")


if __name__ == "__main__":
    unittest.main()
