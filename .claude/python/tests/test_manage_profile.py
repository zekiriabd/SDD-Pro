"""Tests for sdd_scripts.manage_profile — profile export/import/list/delete."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.manage_profile import (
    cmd_delete,
    cmd_export,
    cmd_import,
    cmd_list,
    cmd_show,
    main,
    validate_profile_name,
)


def _setup_env(tmp: Path) -> dict[str, str]:
    return {
        "SDD_PROFILES_DIR": str(tmp / "profiles"),
        "SDD_TEAM_CONFIG": str(tmp / "team.yml"),
    }


class TestValidateProfileName(unittest.TestCase):
    def test_valid(self):
        for n in ("strict-prod", "dev_only", "preset.1", "AbcDef-123"):
            validate_profile_name(n)  # should not raise

    def test_invalid(self):
        for n in ("with space", "../escape", "trailing/", "", "$bad"):
            with self.assertRaises(ValueError):
                validate_profile_name(n)


class TestExport(unittest.TestCase):
    def test_export_creates_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "team.yml").write_text("Key: value\n", encoding="utf-8")
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    rc = cmd_export("strict-prod")
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            self.assertTrue((tmp_p / "profiles" / "strict-prod.yml").is_file())

    def test_export_fails_when_no_team_config(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stderr = StringIO()
                try:
                    rc = cmd_export("foo")
                finally:
                    sys.stderr = sys.__stderr__
            self.assertEqual(rc, 1)

    def test_export_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "team.yml").write_text("Key: value\n", encoding="utf-8")
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                sys.stderr = StringIO()
                try:
                    cmd_export("p1")
                    rc = cmd_export("p1")  # second export → must refuse
                finally:
                    sys.stdout = sys.__stdout__
                    sys.stderr = sys.__stderr__
            self.assertEqual(rc, 2)

    def test_export_force_overwrites(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "team.yml").write_text("Key: v1\n", encoding="utf-8")
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    cmd_export("p1")
                    (tmp_p / "team.yml").write_text("Key: v2\n", encoding="utf-8")
                    rc = cmd_export("p1", force=True)
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            content = (tmp_p / "profiles" / "p1.yml").read_text(encoding="utf-8")
            self.assertIn("v2", content)


class TestImport(unittest.TestCase):
    def test_import_creates_team_yml(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            profile_dir = tmp_p / "profiles"
            profile_dir.mkdir()
            (profile_dir / "strict.yml").write_text("CoverageMin: 90\n", encoding="utf-8")

            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    rc = cmd_import("strict")
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            self.assertEqual(
                (tmp_p / "team.yml").read_text(encoding="utf-8").strip(),
                "CoverageMin: 90",
            )

    def test_import_backs_up_existing_team(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            profile_dir = tmp_p / "profiles"
            profile_dir.mkdir()
            (profile_dir / "strict.yml").write_text("CoverageMin: 90\n", encoding="utf-8")
            (tmp_p / "team.yml").write_text("CoverageMin: 60\n", encoding="utf-8")

            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    rc = cmd_import("strict")
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            self.assertTrue((tmp_p / "team.yml.bak").is_file())
            self.assertIn("60", (tmp_p / "team.yml.bak").read_text(encoding="utf-8"))

    def test_import_fails_when_profile_absent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stderr = StringIO()
                try:
                    rc = cmd_import("ghost")
                finally:
                    sys.stderr = sys.__stderr__
            self.assertEqual(rc, 1)


class TestList(unittest.TestCase):
    def test_list_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    rc = cmd_list()
                    out = sys.stdout.getvalue()
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            self.assertIn("No profiles", out)

    def test_list_shows_profiles_and_active(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            pd = tmp_p / "profiles"
            pd.mkdir()
            (pd / "alpha.yml").write_text("x: 1", encoding="utf-8")
            (pd / "beta.yml").write_text("x: 2", encoding="utf-8")
            (tmp_p / "team.yml").write_text("active: true", encoding="utf-8")

            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    cmd_list()
                    out = sys.stdout.getvalue()
                finally:
                    sys.stdout = sys.__stdout__
            self.assertIn("alpha", out)
            self.assertIn("beta", out)
            self.assertIn("Active team config", out)


class TestDelete(unittest.TestCase):
    def test_delete_removes_profile(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            pd = tmp_p / "profiles"
            pd.mkdir()
            (pd / "old.yml").write_text("x: 1", encoding="utf-8")
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    rc = cmd_delete("old")
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            self.assertFalse((pd / "old.yml").exists())

    def test_delete_missing_returns_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stderr = StringIO()
                try:
                    rc = cmd_delete("ghost")
                finally:
                    sys.stderr = sys.__stderr__
            self.assertEqual(rc, 1)


class TestShow(unittest.TestCase):
    def test_show_prints_content(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            pd = tmp_p / "profiles"
            pd.mkdir()
            (pd / "config.yml").write_text("CoverageMin: 90\n", encoding="utf-8")
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stdout = StringIO()
                try:
                    rc = cmd_show("config")
                    out = sys.stdout.getvalue()
                finally:
                    sys.stdout = sys.__stdout__
            self.assertEqual(rc, 0)
            self.assertIn("CoverageMin: 90", out)


class TestMainDispatch(unittest.TestCase):
    def test_main_invalid_name_returns_2(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "team.yml").write_text("x: 1", encoding="utf-8")
            with mock.patch.dict(os.environ, _setup_env(tmp_p)):
                sys.stderr = StringIO()
                try:
                    rc = main(["export", "../escape"])
                finally:
                    sys.stderr = sys.__stderr__
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
