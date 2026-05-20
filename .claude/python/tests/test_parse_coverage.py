"""Tests for sdd_scripts.parse_coverage — multi-format parsers + helpers."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.parse_coverage import (
    _round2,
    detect_coverage_min,
    find_feat_name,
    parse_cobertura,
    parse_istanbul,
    parse_jacoco,
    parse_lcov,
)


COBERTURA_XML = """<?xml version="1.0"?>
<coverage lines-covered="80" lines-valid="100" branches-covered="15" branches-valid="20">
  <packages>
    <package name="SimBackend.Services">
      <classes>
        <class filename="Services/AuthService.cs" line-rate="0.85" />
        <class filename="Services/PdvService.cs" line-rate="0.70" />
      </classes>
    </package>
  </packages>
</coverage>
"""

LCOV_INFO = """TN:
SF:src/auth/login.ts
LF:50
LH:45
end_of_record
TN:
SF:src/pdv/list.ts
LF:30
LH:18
end_of_record
"""

JACOCO_XML = """<?xml version="1.0"?>
<report>
  <counter type="LINE" missed="20" covered="80"/>
  <counter type="BRANCH" missed="5" covered="15"/>
  <package name="com/example">
    <sourcefile name="AuthService.kt">
      <counter type="LINE" missed="5" covered="45"/>
    </sourcefile>
    <sourcefile name="PdvController.kt">
      <counter type="LINE" missed="10" covered="20"/>
    </sourcefile>
  </package>
</report>
"""

ISTANBUL_JSON = {
    "total": {
        "lines": {"covered": 120, "total": 150, "pct": 80.0},
        "branches": {"covered": 30, "total": 40, "pct": 75.0},
    },
    "src/auth.ts":   {"lines": {"covered": 90, "total": 100, "pct": 90.0}},
    "src/pdv.ts":    {"lines": {"covered": 30, "total": 50, "pct": 60.0}},
}


class TestRound2(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(_round2(80, 100), 80.0)
        self.assertEqual(_round2(2, 3), 66.67)

    def test_zero_denominator(self):
        self.assertEqual(_round2(5, 0), 0.0)
        self.assertEqual(_round2(0, 0), 0.0)


class TestCobertura(unittest.TestCase):
    def test_parses_lines_and_branches(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "coverage.cobertura.xml"
            f.write_text(COBERTURA_XML, encoding="utf-8")
            result = parse_cobertura(f)
        self.assertEqual(result["covered"], 80)
        self.assertEqual(result["total"], 100)
        self.assertEqual(result["bcovered"], 15)
        self.assertEqual(result["btotal"], 20)
        self.assertEqual(len(result["files"]), 2)
        names = [f["path"] for f in result["files"]]
        self.assertIn("Services/AuthService.cs", names)
        # 0.85 → 85.0
        auth = next(f for f in result["files"] if f["path"] == "Services/AuthService.cs")
        self.assertEqual(auth["lines_pct"], 85.0)


class TestLcov(unittest.TestCase):
    def test_aggregates_multiple_records(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "lcov.info"
            f.write_text(LCOV_INFO, encoding="utf-8")
            result = parse_lcov(f)
        self.assertEqual(result["covered"], 63)  # 45+18
        self.assertEqual(result["total"], 80)    # 50+30
        self.assertEqual(len(result["files"]), 2)
        login = next(f for f in result["files"] if "login" in f["path"])
        self.assertEqual(login["lines_pct"], 90.0)

    def test_missing_file_returns_zero(self):
        result = parse_lcov(Path("/nonexistent/lcov.info"))
        self.assertEqual(result["covered"], 0)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["files"], [])


class TestJacoco(unittest.TestCase):
    def test_parses_line_and_branch_counters(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "jacoco.xml"
            f.write_text(JACOCO_XML, encoding="utf-8")
            result = parse_jacoco(f)
        self.assertEqual(result["covered"], 80)
        self.assertEqual(result["total"], 100)  # missed + covered
        self.assertEqual(result["bcovered"], 15)
        self.assertEqual(result["btotal"], 20)
        self.assertEqual(len(result["files"]), 2)
        auth = next(f for f in result["files"] if "AuthService" in f["path"])
        self.assertEqual(auth["lines_pct"], 90.0)  # 45/(5+45)
        self.assertEqual(auth["path"], "com/example/AuthService.kt")


class TestIstanbul(unittest.TestCase):
    def test_uses_total_block(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "coverage-summary.json"
            f.write_text(json.dumps(ISTANBUL_JSON), encoding="utf-8")
            result = parse_istanbul(f)
        self.assertEqual(result["covered"], 120)
        self.assertEqual(result["total"], 150)
        self.assertEqual(len(result["files"]), 2)
        auth = next(f for f in result["files"] if "auth" in f["path"])
        self.assertEqual(auth["lines_pct"], 90.0)

    def test_malformed_returns_zero(self):
        with TemporaryDirectory() as td:
            f = Path(td) / "broken.json"
            f.write_text("{not valid json", encoding="utf-8")
            result = parse_istanbul(f)
        self.assertEqual(result["covered"], 0)
        self.assertEqual(result["total"], 0)


class TestDetectCoverageMin(unittest.TestCase):
    def test_reads_from_stack_md(self):
        with TemporaryDirectory() as td:
            stack = Path(td) / "stack.md"
            stack.write_text(
                "## Project Config\nCoverageMin: 75\nQAMode: full\n",
                encoding="utf-8",
            )
            self.assertEqual(detect_coverage_min(stack, default=80), 75)

    def test_falls_back_to_default(self):
        with TemporaryDirectory() as td:
            stack = Path(td) / "stack.md"
            stack.write_text("## Project Config\nQAMode: full\n", encoding="utf-8")
            self.assertEqual(detect_coverage_min(stack, default=80), 80)

    def test_missing_file_returns_default(self):
        self.assertEqual(detect_coverage_min(Path("/nope/stack.md"), default=70), 70)


class TestFindFeatName(unittest.TestCase):
    def test_finds_matching_feat(self):
        with TemporaryDirectory() as td:
            feats_dir = Path(td)
            (feats_dir / "1-Auth.md").write_text("x", encoding="utf-8")
            (feats_dir / "2-PDV.md").write_text("x", encoding="utf-8")
            self.assertEqual(find_feat_name(feats_dir, 1), "Auth")
            self.assertEqual(find_feat_name(feats_dir, 2), "PDV")

    def test_no_match_returns_none(self):
        with TemporaryDirectory() as td:
            self.assertIsNone(find_feat_name(Path(td), 99))


if __name__ == "__main__":
    unittest.main()
