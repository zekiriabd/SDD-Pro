"""Tests for the generate_schema_slice CLI (Levier 4 — sdd_scripts entry point).

Covers arg parsing, out-path derivation from US basename, exit codes,
and disk side-effects via subprocess.run (real CLI invocation).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.generate_schema_slice import _derive_slice_path  # noqa: E402

pytestmark = pytest.mark.smoke


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke the generate_schema_slice CLI as a subprocess."""
    cmd = [sys.executable, "-m", "sdd_scripts.generate_schema_slice", *args]
    import os
    env = {**os.environ, "PYTHONPATH": str(_PY_ROOT), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _make_schema_dict() -> dict:
    return {
        "extracted_at": "2026-06-08T00:00:00Z",
        "database_type": "SqlServer",
        "database_name": "TestDB",
        "tables": [
            {
                "name": "User",
                "primary_key": ["UserId"],
                "columns": [{"name": "UserId", "type": "int", "nullable": False}],
                "foreign_keys": [],
                "indexes": [],
            },
            {
                "name": "Session",
                "primary_key": ["SessionId"],
                "columns": [
                    {"name": "SessionId", "type": "int", "nullable": False},
                    {"name": "UserId", "type": "int", "nullable": False},
                ],
                "foreign_keys": [
                    {"column": "UserId", "ref_table": "User", "ref_column": "UserId"}
                ],
                "indexes": [],
            },
            {
                "name": "Orphan",
                "primary_key": ["OrphanId"],
                "columns": [{"name": "OrphanId", "type": "int", "nullable": False}],
                "foreign_keys": [],
                "indexes": [],
            },
        ],
    }


class TestDeriveSlicePath(unittest.TestCase):
    """Internal helper: derive workspace/output/db/schema-slice-{n}-{m}.json
    from the US filename."""

    def test_simple_basename(self):
        us = Path("workspace/output/us/1-2-Login.md")
        out = _derive_slice_path(us, Path("workspace/output/db"))
        self.assertEqual(out.name, "schema-slice-1-2.json")

    def test_long_name_with_dashes(self):
        us = Path("workspace/output/us/3-1-Reset-Password.md")
        out = _derive_slice_path(us, Path("workspace/output/db"))
        self.assertEqual(out.name, "schema-slice-3-1.json")

    def test_invalid_basename_returns_none(self):
        us = Path("workspace/output/us/not-a-valid-us.md")
        self.assertIsNone(_derive_slice_path(us, Path("workspace/output/db")))


class TestCliEndToEnd(unittest.TestCase):
    """Real subprocess invocation to validate exit codes and file output."""

    def _setup_workspace(self, td: Path, us_content: str) -> tuple[Path, Path]:
        (td / "workspace" / "output" / "db").mkdir(parents=True)
        (td / "workspace" / "output" / "us").mkdir(parents=True)
        schema = td / "workspace" / "output" / "db" / "schema.json"
        schema.write_text(json.dumps(_make_schema_dict()), encoding="utf-8")
        us = td / "workspace" / "output" / "us" / "1-1-Login.md"
        us.write_text(us_content, encoding="utf-8")
        return schema, us

    def test_happy_path_writes_slice(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            schema, us = self._setup_workspace(
                td, "# US 1-1-Login\n\nManage Session and User entities.",
            )
            result = _run_cli(
                ["--us-path", str(us), "--schema-path", str(schema), "--json"],
                cwd=td,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["tables_in_slice"], 2)
            self.assertEqual(payload["tables_in_source"], 3)
            self.assertEqual(sorted(payload["seed_entities"]), ["Session", "User"])
            # The slice file must actually exist
            slice_path = td / "workspace" / "output" / "db" / "schema-slice-1-1.json"
            self.assertTrue(slice_path.is_file())
            sliced = json.loads(slice_path.read_text(encoding="utf-8"))
            self.assertEqual(len(sliced["tables"]), 2)

    def test_no_match_exits_correctible(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            schema, us = self._setup_workspace(
                td, "# US 1-1-Login\n\nNothing about schema tables here.",
            )
            result = _run_cli(
                ["--us-path", str(us), "--schema-path", str(schema)],
                cwd=td,
            )
            # exit 2 = CORRECTIBLE: no entity referenced, agents fallback to full
            self.assertEqual(result.returncode, 2, msg=result.stderr)
            self.assertIn("no entity from schema referenced", result.stderr)
            # And no slice file written
            slice_path = td / "workspace" / "output" / "db" / "schema-slice-1-1.json"
            self.assertFalse(slice_path.exists())

    def test_missing_schema_exits_correctible(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            (td / "workspace" / "output" / "us").mkdir(parents=True)
            us = td / "workspace" / "output" / "us" / "1-1-X.md"
            us.write_text("test", encoding="utf-8")
            result = _run_cli(
                ["--us-path", str(us), "--schema-path", str(td / "missing.json")],
                cwd=td,
            )
            # exit 2 = CORRECTIBLE: no schema, nothing to slice
            self.assertEqual(result.returncode, 2, msg=result.stderr)
            self.assertIn("schema.json not found", result.stderr)

    def test_missing_us_exits_fail_fast(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            (td / "workspace" / "output" / "db").mkdir(parents=True)
            schema = td / "workspace" / "output" / "db" / "schema.json"
            schema.write_text(json.dumps(_make_schema_dict()), encoding="utf-8")
            result = _run_cli(
                ["--us-path", str(td / "no-such-us.md"),
                 "--schema-path", str(schema)],
                cwd=td,
            )
            # exit 1 = FAIL_FAST: invalid arg
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn("US not found", result.stderr)

    def test_invalid_us_basename_exits_fail_fast(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            (td / "workspace" / "output" / "db").mkdir(parents=True)
            (td / "workspace" / "output" / "us").mkdir(parents=True)
            schema = td / "workspace" / "output" / "db" / "schema.json"
            schema.write_text(json.dumps(_make_schema_dict()), encoding="utf-8")
            us = td / "workspace" / "output" / "us" / "bad-name.md"
            us.write_text("# US\n\nMentions User and Session.", encoding="utf-8")
            result = _run_cli(
                ["--us-path", str(us), "--schema-path", str(schema)],
                cwd=td,
            )
            # exit 1 = FAIL_FAST: cannot derive slice path
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            self.assertIn("cannot derive slice path", result.stderr)

    def test_no_fk_closure_flag(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            schema, us = self._setup_workspace(
                td, "# US 1-1-Login\n\nWe only need Session here.",
            )
            result = _run_cli(
                ["--us-path", str(us), "--schema-path", str(schema),
                 "--no-fk-closure", "--json"],
                cwd=td,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            # Without closure: Session only (not User even though FK points to it)
            self.assertEqual(payload["seed_entities"], ["Session"])
            self.assertEqual(payload["transitive_entities"], [])
            self.assertEqual(payload["tables_in_slice"], 1)

    def test_out_override(self):
        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            schema, us = self._setup_workspace(
                td, "# US 1-1-Login\n\nUser entity.",
            )
            custom_out = td / "custom" / "my-slice.json"
            result = _run_cli(
                ["--us-path", str(us), "--schema-path", str(schema),
                 "--out", str(custom_out)],
                cwd=td,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue(custom_out.is_file())
            # And the default-path slice was NOT created
            default = td / "workspace" / "output" / "db" / "schema-slice-1-1.json"
            self.assertFalse(default.exists())


if __name__ == "__main__":
    unittest.main()
