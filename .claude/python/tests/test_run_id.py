"""Unit tests for sdd_lib/run_id.py — stable run_id resolution for hooks."""
from __future__ import annotations

import os
import re
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import run_id  # noqa: E402


_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{4}$")


def _make_fake_repo(root: Path) -> None:
    """Build a minimal repo layout that satisfies _looks_like_repo_root()."""
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "workspace").mkdir()


class TestRunIdGeneration(unittest.TestCase):
    def test_generate_run_id_shape(self) -> None:
        rid = run_id._generate_run_id()
        self.assertRegex(rid, _RUN_ID_RE)

    def test_two_generated_ids_differ(self) -> None:
        a, b = run_id._generate_run_id(), run_id._generate_run_id()
        # Even if same second, rand4 disambiguates (>99.998% probability).
        self.assertNotEqual(a, b)


class TestGetOrCreateRunId(unittest.TestCase):
    def setUp(self) -> None:
        # Clear any env that might leak from CI
        self._old_env = {
            k: os.environ.pop(k, None)
            for k in ("SDD_RUN_ID", "SDD_REPO_ROOT")
        }

    def tearDown(self) -> None:
        for k, v in self._old_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_env_var_wins_when_set(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            os.environ["SDD_RUN_ID"] = "custom-pinned-id"
            try:
                self.assertEqual(run_id.get_or_create_run_id(), "custom-pinned-id")
            finally:
                os.environ.pop("SDD_RUN_ID", None)
                os.environ.pop("SDD_REPO_ROOT", None)

    def test_fresh_call_creates_marker(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            try:
                rid = run_id.get_or_create_run_id()
                self.assertRegex(rid, _RUN_ID_RE)
                marker = root / "workspace" / "output" / ".sys" / ".state" / "run-id.current"
                self.assertTrue(marker.exists())
                self.assertEqual(marker.read_text(encoding="utf-8").strip(), rid)
            finally:
                os.environ.pop("SDD_REPO_ROOT", None)

    def test_subsequent_call_returns_cached(self) -> None:
        """Within TTL, second call returns the marker content."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            try:
                first = run_id.get_or_create_run_id()
                second = run_id.get_or_create_run_id()
                self.assertEqual(first, second)
            finally:
                os.environ.pop("SDD_REPO_ROOT", None)

    def test_force_new_overrides_marker(self) -> None:
        """force_new=True bypasses env + marker, generates fresh id."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            os.environ["SDD_RUN_ID"] = "should-be-ignored"
            try:
                first = run_id.get_or_create_run_id()  # uses env
                self.assertEqual(first, "should-be-ignored")
                second = run_id.get_or_create_run_id(force_new=True)
                self.assertNotEqual(first, second)
                self.assertRegex(second, _RUN_ID_RE)
            finally:
                os.environ.pop("SDD_RUN_ID", None)
                os.environ.pop("SDD_REPO_ROOT", None)

    def test_force_new_updates_marker(self) -> None:
        """After force_new, the marker reflects the new id (not the cached)."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            try:
                run_id.get_or_create_run_id()  # populate marker
                forced = run_id.get_or_create_run_id(force_new=True)
                marker = root / "workspace" / "output" / ".sys" / ".state" / "run-id.current"
                self.assertEqual(marker.read_text(encoding="utf-8").strip(), forced)
            finally:
                os.environ.pop("SDD_REPO_ROOT", None)


class TestGetOrCreateDispatchStartTs(unittest.TestCase):
    def test_env_var_wins(self) -> None:
        os.environ["SDD_DISPATCH_START_TS"] = "2026-06-07T12:00:00Z"
        try:
            self.assertEqual(
                run_id.get_or_create_dispatch_start_ts(),
                "2026-06-07T12:00:00Z",
            )
        finally:
            os.environ.pop("SDD_DISPATCH_START_TS", None)

    def test_fallback_to_iso_now(self) -> None:
        """Without env or marker, falls back to UTC now (ISO-8601 with Z)."""
        os.environ.pop("SDD_DISPATCH_START_TS", None)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            try:
                ts = run_id.get_or_create_dispatch_start_ts()
                # ISO-8601 UTC with Z : 2026-06-07T14:30:22Z
                self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            finally:
                os.environ.pop("SDD_REPO_ROOT", None)


if __name__ == "__main__":
    unittest.main()
