"""Tests for sdd_lib.layered_config — 3-level deep-merge + security guards."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.layered_config import (
    ConfigError,
    _parse_yaml_minimal,
    _severity_idx,
    dump_effective_config,
    read_layered_config,
)


def _make_repo(tmp: Path, *, stack_md: str | None = None, base_yml: str | None = None) -> Path:
    (tmp / ".claude").mkdir()
    (tmp / "workspace" / "input" / "stack").mkdir(parents=True)
    if stack_md is not None:
        (tmp / "workspace" / "input" / "stack" / "stack.md").write_text(stack_md, encoding="utf-8")
    if base_yml is not None:
        (tmp / ".claude" / "config.base.yml").write_text(base_yml, encoding="utf-8")
    return tmp


class TestParseYamlMinimal(unittest.TestCase):
    def test_simple_kv(self):
        text = "Key1: value1\nKey2: value2"
        self.assertEqual(_parse_yaml_minimal(text), {"Key1": "value1", "Key2": "value2"})

    def test_quoted_values(self):
        text = 'Name: "Foo Bar"\nOther: \'baz\''
        self.assertEqual(_parse_yaml_minimal(text), {"Name": "Foo Bar", "Other": "baz"})

    def test_comments(self):
        text = "# this is a comment\nKey: value  # inline comment\n"
        self.assertEqual(_parse_yaml_minimal(text), {"Key": "value"})

    def test_empty_lines_skipped(self):
        text = "\nKey: value\n\n"
        self.assertEqual(_parse_yaml_minimal(text), {"Key": "value"})

    def test_invalid_lines_ignored(self):
        text = "not a key value\nKey: value\n[section]\nOther: ok"
        self.assertEqual(_parse_yaml_minimal(text), {"Key": "value", "Other": "ok"})


class TestSeverityIdx(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(_severity_idx("critical"), 0)
        self.assertEqual(_severity_idx("serious"), 1)
        self.assertEqual(_severity_idx("moderate"), 2)
        self.assertEqual(_severity_idx("minor"), 3)

    def test_unknown_returns_none(self):
        self.assertIsNone(_severity_idx("garbage"))
        self.assertIsNone(_severity_idx(None))  # type: ignore[arg-type]


class TestBackwardCompat(unittest.TestCase):
    """If base.yml + team.yml absent, behavior must == read_project_config."""

    def test_no_base_no_team_returns_project_only(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(tmp_p, stack_md="""# stack
## Project Config
AppName: TestApp
CoverageMin: 80
""")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(tmp_p / "missing.yml")}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["AppName"], "TestApp")
            self.assertEqual(result["CoverageMin"], "80")


class TestLayering(unittest.TestCase):
    def test_base_provides_defaults(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
AppName: ProjectApp
""",
                base_yml="""# base
CoverageMin: 80
SpecComplianceMode: manual
""",
            )
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(tmp_p / "missing.yml")}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["AppName"], "ProjectApp")     # from project
            self.assertEqual(result["CoverageMin"], "80")          # from base
            self.assertEqual(result["SpecComplianceMode"], "manual")  # from base

    def test_project_overrides_base(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
CoverageMin: 90
""",
                base_yml="""CoverageMin: 80
""",
            )
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(tmp_p / "missing.yml")}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["CoverageMin"], "90")  # project wins

    def test_team_overrides_base(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
AppName: ProjectApp
""",
                base_yml="""CoverageMin: 60
""",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("CoverageMin: 80\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["CoverageMin"], "80")  # team overrides base

    def test_full_precedence_chain(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
SpecComplianceMode: full
""",
                base_yml="""SpecComplianceMode: manual
""",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("SpecComplianceMode: full\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                result = read_layered_config(root=tmp_p, include_sources=True)
            self.assertEqual(result["config"]["SpecComplianceMode"], "full")
            self.assertEqual(result["sources"]["SpecComplianceMode"], "project")


class TestSecurityDowngradeGuard(unittest.TestCase):
    def test_project_cannot_relax_team_severity(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
SecurityFailOn: moderate
""",
                base_yml="",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("SecurityFailOn: critical\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                with self.assertRaises(ConfigError) as ctx:
                    read_layered_config(root=tmp_p)
                self.assertIn("CONFIG_SECURITY_DOWNGRADE", ctx.exception.cause)
                self.assertIn("SecurityFailOn", ctx.exception.cause)

    def test_project_can_harden_team_severity(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
SecurityFailOn: critical
""",
                base_yml="",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("SecurityFailOn: serious\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["SecurityFailOn"], "critical")

    def test_project_cannot_relax_coverage_min(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
CoverageMin: 50
""",
                base_yml="",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("CoverageMin: 80\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                with self.assertRaises(ConfigError) as ctx:
                    read_layered_config(root=tmp_p)
                self.assertIn("CoverageMin", ctx.exception.cause)

    def test_project_can_raise_coverage_min(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
CoverageMin: 90
""",
                base_yml="",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("CoverageMin: 80\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["CoverageMin"], "90")

    def test_no_guard_when_team_silent(self):
        """If team doesn't set a security key, project is free to set anything."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
SecurityFailOn: minor
""",
                base_yml="",
            )
            team_path = tmp_p / "team.yml"
            team_path.write_text("Other: x\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(team_path)}):
                result = read_layered_config(root=tmp_p)
            self.assertEqual(result["SecurityFailOn"], "minor")


class TestKeysFilter(unittest.TestCase):
    def test_keys_filter_restricts_output(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
AppName: A
BackendName: B
CoverageMin: 80
""",
                base_yml="",
            )
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(tmp_p / "x.yml")}):
                result = read_layered_config(root=tmp_p, keys=("AppName", "CoverageMin"))
            self.assertEqual(set(result.keys()), {"AppName", "CoverageMin"})


class TestDumpEffectiveConfig(unittest.TestCase):
    def test_dump_writes_audit_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo(
                tmp_p,
                stack_md="""## Project Config
AppName: TestApp
""",
                base_yml="CoverageMin: 80\n",
            )
            out = tmp_p / "audit.yml"
            with mock.patch.dict(os.environ, {"SDD_TEAM_CONFIG": str(tmp_p / "x.yml")}):
                dump_effective_config(out, root=tmp_p)
            content = out.read_text(encoding="utf-8")
            self.assertIn("AppName: TestApp", content)
            self.assertIn("source: project", content)
            self.assertIn("CoverageMin: 80", content)
            self.assertIn("source: base", content)


if __name__ == "__main__":
    unittest.main()
