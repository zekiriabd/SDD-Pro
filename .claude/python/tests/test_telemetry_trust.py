"""Tests for the v7.0.0-alpha telemetry-trust fix (2026-05-21).

Three regressions filed by user :
  1. `connect_ro` raised 'unable to open database file' on Windows when
     WAL -shm/-wal were held by a concurrent writer. Fix : RFC-compliant
     URI via `Path.as_uri()` + retry with `immutable=1` on lock.
  2. `preflight_cost_cap._compute_run_cost` silently returned 0.0 on DB
     error → cap was bypassed every time telemetry failed. Fix :
     distinguish "db absent" (legit) from "db error: ..." (suspect) ;
     main() blocks (HOOK_DENY) on "db error" in CI, WARN+ALLOW interactive.
  3. `verify_telemetry_health` used raw sqlite3.connect, bypassing the
     WAL-safe path. Fix : route through connect_ro.

Each test exercises the failure mode that previously silenced the cap.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import console_db  # noqa: E402

HOOK = _PY_ROOT / "sdd_hooks" / "preflight_cost_cap.py"
VERIFY = _PY_ROOT / "sdd_admin" / "verify_telemetry_health.py"

CI_VARS = (
    "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
    "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
)


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "workspace").mkdir()
    return tmp_path


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in CI_VARS}
    for k in ("SDD_DISABLE_COST_CAP", "SDD_RUN_ID", "SDD_REPO_ROOT", "SDD_BUDGET_MODE"):
        env.pop(k, None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra:
        env.update(extra)
    return env


# ============================================================================
# Fix #1 : connect_ro WAL-safe URI
# ============================================================================

class TestConnectRoUriPortability(unittest.TestCase):
    """`Path.as_uri()` produces RFC 8089 compliant URIs on every platform."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        self.db = self.repo / "workspace" / "output" / "db" / "console.db"

    def tearDown(self):
        self._tmp.cleanup()

    def test_connect_ro_reads_normal_db(self):
        """Sanity check : standard read works on a freshly initialized DB."""
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            console_db.ensure_initialized(self.db)
            with console_db.connect_ro(self.db) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='token_usage'"
                ).fetchall()
                self.assertEqual(len(rows), 1)
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_connect_ro_raises_on_missing_db(self):
        """No silent fallback if the file truly doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            with console_db.connect_ro(self.db) as conn:
                pass

    def test_connect_ro_uri_uses_as_uri(self):
        """The URI must be `file:///...` (3 slashes), not the legacy `file:/...`.

        Inspection at the source level — guards against accidental reversion.
        """
        src = (_PY_ROOT / "sdd_lib" / "console_db" / "core.py").read_text(encoding="utf-8")
        self.assertIn("db_path.as_uri()", src,
                      "connect_ro must use Path.as_uri() (RFC 8089)")
        self.assertNotIn('f"file:{db_path.as_posix()}', src,
                         "ad-hoc URI form was the source of Windows lock failures")

    def test_connect_ro_immutable_fallback_path_present(self):
        """immutable=1 fallback must be present in the code path."""
        src = (_PY_ROOT / "sdd_lib" / "console_db" / "core.py").read_text(encoding="utf-8")
        self.assertIn("immutable=1", src,
                      "connect_ro needs immutable fallback on WAL lock")
        self.assertIn("OperationalError", src)


# ============================================================================
# Fix #2 : preflight_cost_cap distinguishes "db absent" from "db error"
# ============================================================================

class TestComputeRunCostScopes(unittest.TestCase):
    """`_compute_run_cost` must return distinct scope labels per failure mode."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_db_absent_scope_is_legit(self):
        """No console.db → scope='db absent' → ALLOW (fresh checkout case)."""
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            from sdd_hooks.preflight_cost_cap import _compute_run_cost
            cost, calls, scope = _compute_run_cost()
            self.assertEqual(cost, 0.0)
            self.assertEqual(calls, 0)
            self.assertEqual(scope, "db absent")
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_db_corrupt_scope_signals_error(self):
        """Corrupt DB file → scope='db error: ...' → suspect, not legit zero."""
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            # Create a "DB" file that's actually garbage
            db_path = self.repo / "workspace" / "output" / "db" / "console.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_path.write_bytes(b"this is not a sqlite database, surprise!")

            from sdd_hooks.preflight_cost_cap import _compute_run_cost
            cost, calls, scope = _compute_run_cost()
            self.assertEqual(cost, 0.0)
            self.assertTrue(scope.startswith("db error:"),
                            f"Expected 'db error:' prefix, got {scope!r}")
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)


class TestCostCapHookBehaviourOnDbError(unittest.TestCase):
    """The hook itself must NOT silently allow on DB error.

    Previous behaviour : `db error: ...` → cost=0 → cap pretended OK → ALLOW.
    New behaviour : `db error: ...` → DENY in CI, visible ERROR + ALLOW in
    interactive. Bypass strictly via SDD_DISABLE_COST_CAP=1.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))
        # Plant a corrupt DB
        db_path = self.repo / "workspace" / "output" / "db" / "console.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(b"corrupt content " * 50)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_hook(self, env_extra=None):
        import json
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "dev-backend"},
        }
        extra = {"SDD_REPO_ROOT": str(self.repo)}
        if env_extra:
            extra.update(env_extra)
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            env=_clean_env(extra),
            capture_output=True, text=True, check=False,
        )

    def test_corrupt_db_blocks_in_ci(self):
        """CI auto-detect → DENY (exit 2) + [TELEMETRY_UNAVAILABLE]."""
        r = self._run_hook({"CI": "true"})
        self.assertEqual(r.returncode, 2,
                         f"Expected DENY in CI on db error, got {r.returncode}\n"
                         f"STDERR={r.stderr}")
        self.assertIn("[TELEMETRY_UNAVAILABLE]", r.stderr)

    def test_corrupt_db_warns_but_allows_interactive(self):
        """No CI env → ERROR visible + ALLOW (operator awareness)."""
        r = self._run_hook()
        self.assertEqual(r.returncode, 0, f"Expected ALLOW interactive, got {r.returncode}")
        self.assertIn("[TELEMETRY_UNAVAILABLE]", r.stderr)
        self.assertIn("cap is OFF", r.stderr)

    def test_disable_env_overrides_blocking(self):
        """SDD_DISABLE_COST_CAP=1 must bypass even DB errors."""
        r = self._run_hook({"CI": "true", "SDD_DISABLE_COST_CAP": "1"})
        self.assertEqual(r.returncode, 0,
                         f"Expected bypass with SDD_DISABLE_COST_CAP=1, "
                         f"got {r.returncode}\nSTDERR={r.stderr}")
        self.assertNotIn("[TELEMETRY_UNAVAILABLE]", r.stderr)


class TestCostCapAbsentDbAllows(unittest.TestCase):
    """Sanity : 'db absent' is NOT 'db error' — fresh checkout allows."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_db_allows_silently(self):
        import json
        payload = {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "po"},
        }
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            env=_clean_env({"SDD_REPO_ROOT": str(self.repo), "CI": "true"}),
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(r.returncode, 0,
                         f"Fresh repo (no console.db) must allow ; got {r.returncode}\n"
                         f"STDERR={r.stderr}")
        self.assertNotIn("[TELEMETRY_UNAVAILABLE]", r.stderr)


# ============================================================================
# Fix #3 : verify_telemetry_health uses connect_ro
# ============================================================================

class TestVerifyTelemetryHealth(unittest.TestCase):
    """The audit script must survive a WAL-locked DB (uses connect_ro now)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_absent_db_verdict_absent(self):
        r = subprocess.run(
            [sys.executable, str(VERIFY), "--json"],
            env=_clean_env({"SDD_REPO_ROOT": str(self.repo)}),
            capture_output=True, text=True, check=False,
        )
        # ABSENT exits via fail-set "polluted" → not in fail set → OK exit
        self.assertEqual(r.returncode, 0)
        self.assertIn('"verdict": "ABSENT"', r.stdout)

    def test_clean_db_verdict_clean(self):
        import json
        os.environ["SDD_REPO_ROOT"] = str(self.repo)
        try:
            db_path = self.repo / "workspace" / "output" / "db" / "console.db"
            console_db.ensure_initialized(db_path)
        finally:
            os.environ.pop("SDD_REPO_ROOT", None)

        r = subprocess.run(
            [sys.executable, str(VERIFY), "--json"],
            env=_clean_env({"SDD_REPO_ROOT": str(self.repo)}),
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(r.returncode, 0)
        payload = json.loads(r.stdout)
        # Fresh DB has no token_usage rows → verdict CLEAN (or SUSPECT due
        # to the WARN-level "table empty" check). Both acceptable.
        self.assertIn(payload["verdict"], ("CLEAN", "SUSPECT"))

    def test_corrupt_db_verdict_unreadable(self):
        """New verdict UNREADABLE (v7.0.0-alpha) when DB exists but cannot be opened."""
        import json
        db_path = self.repo / "workspace" / "output" / "db" / "console.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(b"garbage")
        r = subprocess.run(
            [sys.executable, str(VERIFY), "--json"],
            env=_clean_env({"SDD_REPO_ROOT": str(self.repo)}),
            capture_output=True, text=True, check=False,
        )
        # UNREADABLE not in fail set (only "polluted") → exit 0
        # But the verdict field signals the operator clearly
        payload = json.loads(r.stdout)
        self.assertEqual(payload["verdict"], "UNREADABLE")


if __name__ == "__main__":
    unittest.main()
