"""Tests for sdd_scripts.detect_capabilities — §2.4.b ON-DEMAND lib gating."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import detect_capabilities as dc  # noqa: E402


SAMPLE_LIBS_JSON = {
    "stackId": "dotnet-minimalapi",
    "category": "backend",
    "schemaVersion": 1,
    "buildSystem": "dotnet",
    "manifest": {},
    "versions": {"epplus": "7.4.0", "questpdf": "2024.10.0"},
    "core": [],
    "onDemand": [
        {
            "id": "EPPlus",
            "module": "EPPlus",
            "versionRef": "epplus",
            "rationale": "Excel export",
            "installCommand": "dotnet add package EPPlus",
            "license": "Polyform-NC",
            "capability": "excel",
            "triggers": [r"\bexcel\b", r"\b\.xlsx\b", r"export.*excel"],
        },
        {
            "id": "QuestPDF",
            "module": "QuestPDF",
            "versionRef": "questpdf",
            "rationale": "PDF generation",
            "installCommand": "dotnet add package QuestPDF",
            "license": "MIT",
            "capability": "pdf",
            "triggers": [r"\bpdf\b", r"\b\.pdf\b"],
        },
    ],
    "plugins": [],
}


class TestSafeRead(unittest.TestCase):
    def test_empty_path_returns_empty(self):
        self.assertEqual(dc.safe_read(""), "")

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            self.assertEqual(dc.safe_read(str(Path(tmp) / "nope.md")), "")

    def test_reads_existing_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            f = Path(tmp) / "x.md"
            f.write_text("hello", encoding="utf-8")
            self.assertEqual(dc.safe_read(str(f)), "hello")


class TestLoadOndemandFromLibsJson(unittest.TestCase):
    def _setup(self, tmp_p: Path) -> Path:
        stack_dir = tmp_p / ".claude" / "stacks" / "backend"
        stack_dir.mkdir(parents=True)
        libs = stack_dir / "dotnet-minimalapi.libs.json"
        libs.write_text(json.dumps(SAMPLE_LIBS_JSON), encoding="utf-8")
        return libs

    def test_loads_capabilities(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            libs = self._setup(tmp_p)
            caps = dc.load_ondemand_from_libs_json(str(libs))
            self.assertEqual(len(caps), 2)
            names = sorted(c["name"] for c in caps)
            self.assertEqual(names, ["excel", "pdf"])

    def test_resolves_md_to_libs_json(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup(tmp_p)
            md_path = (tmp_p / ".claude" / "stacks" / "backend"
                       / "dotnet-minimalapi.md")
            md_path.write_text("# stack doc", encoding="utf-8")
            caps = dc.load_ondemand_from_libs_json(str(md_path))
            self.assertEqual(len(caps), 2)

    def test_missing_libs_returns_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            caps = dc.load_ondemand_from_libs_json(
                str(Path(tmp) / "nope.libs.json"))
            self.assertEqual(caps, [])

    def test_malformed_json_returns_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            libs = tmp_p / "bad.libs.json"
            libs.write_text("not json {{", encoding="utf-8")
            self.assertEqual(dc.load_ondemand_from_libs_json(str(libs)), [])

    def test_resolves_version_from_ref(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            libs = self._setup(tmp_p)
            caps = dc.load_ondemand_from_libs_json(str(libs))
            excel = next(c for c in caps if c["name"] == "excel")
            self.assertEqual(excel["version"], "7.4.0")


class TestParseOverrides(unittest.TestCase):
    def test_capabilities_line(self):
        config = "## Project Config\nCapabilities: excel, pdf, redis\n"
        forced, overrides = dc.parse_overrides(config)
        self.assertEqual(forced, ["excel", "pdf", "redis"])
        self.assertEqual(overrides, {})

    def test_capabilities_empty(self):
        config = "## Project Config\nQAMode: full\n"
        forced, overrides = dc.parse_overrides(config)
        self.assertEqual(forced, [])
        self.assertEqual(overrides, {})

    def test_capabilities_lowercase_normalized(self):
        config = "Capabilities: EXCEL, Pdf\n"
        forced, _ = dc.parse_overrides(config)
        self.assertEqual(forced, ["excel", "pdf"])

    def test_override_map(self):
        # NB: existing regex only catches the first line of the override block
        # (no `re.MULTILINE` repetition). This test pins documented behavior.
        config = ("## Project Config\nCapabilities: excel\n\n"
                  "## Capabilities Override\n  excel: ClosedXML\n")
        forced, overrides = dc.parse_overrides(config)
        self.assertEqual(forced, ["excel"])
        self.assertEqual(overrides, {"excel": "ClosedXML"})


class TestMainIntegration(unittest.TestCase):
    def _setup(self, tmp_p: Path, us_text: str, config_text: str,
               project_text: str = "") -> dict[str, str]:
        (tmp_p / ".claude" / "stacks" / "backend").mkdir(parents=True)
        libs = (tmp_p / ".claude" / "stacks" / "backend"
                / "dotnet-minimalapi.libs.json")
        libs.write_text(json.dumps(SAMPLE_LIBS_JSON), encoding="utf-8")

        us = tmp_p / "us.md"
        us.write_text(us_text, encoding="utf-8")

        config = tmp_p / "stack.md"
        config.write_text(config_text, encoding="utf-8")

        paths = {
            "us": str(us),
            "stack": str(libs),
            "config": str(config),
        }
        if project_text:
            proj = tmp_p / "App.csproj"
            proj.write_text(project_text, encoding="utf-8")
            paths["project"] = str(proj)
        return paths

    def _run(self, paths: dict[str, str]) -> dict:
        args = [
            "detect_capabilities.py",
            "--us-path", paths["us"],
            "--stack-path", paths["stack"],
            "--project-config", paths["config"],
        ]
        if "project" in paths:
            args.extend(["--project-file", paths["project"]])
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", args), redirect_stdout(buf):
            rc = dc.main()
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())

    def test_us_with_excel_keyword_triggers(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            paths = self._setup(
                Path(tmp),
                us_text="Export Excel des transactions",
                config_text="## Project Config\nQAMode: full\n",
            )
            out = self._run(paths)
            excel = next(c for c in out["capabilities"]
                         if c["capability"] == "excel")
            self.assertEqual(excel["status"], "TRIGGERED-AUTO")
            self.assertTrue(excel["install_required"])

    def test_us_without_trigger_skipped(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            paths = self._setup(
                Path(tmp),
                us_text="Afficher la liste des bébés",
                config_text="## Project Config\n",
            )
            out = self._run(paths)
            for cap in out["capabilities"]:
                self.assertEqual(cap["status"], "SKIPPED-NO-TRIGGER")

    def test_forced_via_config(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            paths = self._setup(
                Path(tmp),
                us_text="rien de spécial",
                config_text="## Project Config\nCapabilities: excel\n",
            )
            out = self._run(paths)
            excel = next(c for c in out["capabilities"]
                         if c["capability"] == "excel")
            self.assertEqual(excel["status"], "TRIGGERED-FORCED")
            self.assertTrue(excel["forced_via_config"])

    def test_override_applied(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            paths = self._setup(
                Path(tmp),
                us_text="Export Excel",
                config_text=("## Project Config\n\n"
                             "## Capabilities Override\n"
                             "  excel: ClosedXML\n"),
            )
            out = self._run(paths)
            excel = next(c for c in out["capabilities"]
                         if c["capability"] == "excel")
            self.assertEqual(excel["lib"], "ClosedXML")
            self.assertEqual(excel["lib_default"], "EPPlus")
            self.assertTrue(excel["override_applied"])

    def test_lib_already_present_use_existing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            paths = self._setup(
                Path(tmp),
                us_text="Export Excel",
                config_text="## Project Config\n",
                project_text='<PackageReference Include="EPPlus" Version="7.0" />',
            )
            out = self._run(paths)
            excel = next(c for c in out["capabilities"]
                         if c["capability"] == "excel")
            self.assertEqual(excel["status"], "USE-EXISTING")
            self.assertFalse(excel["install_required"])


if __name__ == "__main__":
    unittest.main()
