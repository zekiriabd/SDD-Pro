"""Tests for sdd_scripts.quality_scan — sonar-like deterministic scan.

Targets the pure scan functions (scan_file, is_excluded, line_at,
MAGIC_NUMBER_SKIP). Skips main() which is integration-level (requires
console.db scaffolding) and already exercised by /qa-generate end-to-end.

The pure-function coverage matters because these emit verdicts consumed
by /sdd-review — a regression in detection = false GREEN/RED.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts.quality_scan import (  # noqa: E402
    DEBUG_PATTERNS,
    FORBIDDEN_SDD_ENV_PATTERNS,
    MAGIC_NUMBER_SKIP,
    is_excluded,
    line_at,
    scan_file,
)


class TestLineAt(unittest.TestCase):
    """Byte offset → 1-based line number."""

    def test_first_line_is_1(self):
        self.assertEqual(line_at("hello", 0), 1)
        self.assertEqual(line_at("hello", 4), 1)

    def test_second_line(self):
        self.assertEqual(line_at("a\nb", 2), 2)

    def test_multiline_offset(self):
        text = "line1\nline2\nline3"
        idx = text.index("line3")
        self.assertEqual(line_at(text, idx), 3)

    def test_empty_string(self):
        self.assertEqual(line_at("", 0), 1)


class TestIsExcluded(unittest.TestCase):
    """Exclude bin/obj/node_modules + test patterns."""

    def test_bin_directory_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/App/bin/Debug/App.dll"))

    def test_node_modules_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/App/node_modules/react/index.js"))

    def test_obj_directory_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/Backend/obj/Debug/Foo.obj"))

    def test_tests_subdir_excluded(self):
        """*.Tests/ is QA territory — quality_scan only scans prod code."""
        self.assertTrue(is_excluded("workspace/output/src/Backend.Tests/Services/AuthServiceTests.cs"))

    def test_jest_tests_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/App/__tests__/Login.test.tsx"))

    def test_python_test_files_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/api/test_auth.py"))
        self.assertTrue(is_excluded("workspace/output/src/api/auth_test.py"))

    def test_kotlin_test_files_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/Backend/AuthServiceTest.kt"))

    def test_normal_source_not_excluded(self):
        self.assertFalse(is_excluded("workspace/output/src/Backend/Services/AuthService.cs"))
        self.assertFalse(is_excluded("workspace/output/src/App/Pages/Login.tsx"))

    def test_dist_excluded(self):
        self.assertTrue(is_excluded("workspace/output/src/App/dist/bundle.js"))


class TestMagicNumberSkipList(unittest.TestCase):
    """Common HTTP status / ports / power-of-2 constants are not flagged."""

    def test_http_status_codes_skipped(self):
        for code in ("200", "201", "400", "401", "403", "404", "500", "503"):
            self.assertIsNotNone(MAGIC_NUMBER_SKIP.match(code))

    def test_well_known_ports_skipped(self):
        for port in ("8080", "8443", "3306", "5432", "27017"):
            self.assertIsNotNone(MAGIC_NUMBER_SKIP.match(port))

    def test_powers_of_two_skipped(self):
        for v in ("1000", "1024", "2048", "4096"):
            self.assertIsNotNone(MAGIC_NUMBER_SKIP.match(v))

    def test_arbitrary_magic_number_not_skipped(self):
        self.assertIsNone(MAGIC_NUMBER_SKIP.match("12345"))
        self.assertIsNone(MAGIC_NUMBER_SKIP.match("7"))


class TestScanFileTodos(unittest.TestCase):
    """Detect TODO / FIXME / XXX / HACK markers → severity=error."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scan(self, content: str, rel: str = "src/App/Foo.cs") -> dict:
        f = self.tmp / "f.cs"
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, rel, results)
        return results

    def test_detects_todo(self):
        r = self._scan("// TODO: refactor this\nvar x = 1;")
        self.assertEqual(len(r["errors"]), 1)
        self.assertEqual(r["errors"][0]["tag"], "TODO")
        self.assertEqual(r["errors"][0]["line"], 1)

    def test_detects_fixme(self):
        r = self._scan("\n\n// FIXME: broken contract\n")
        self.assertEqual(len(r["errors"]), 1)
        self.assertEqual(r["errors"][0]["tag"], "FIXME")
        self.assertEqual(r["errors"][0]["line"], 3)

    def test_detects_hack(self):
        r = self._scan("// HACK: temporary workaround")
        self.assertEqual(len(r["errors"]), 1)
        self.assertEqual(r["errors"][0]["tag"], "HACK")

    def test_clean_file_zero_errors(self):
        r = self._scan("public class Foo { public int X => 42; }")
        self.assertEqual(len(r["errors"]), 0)

    def test_message_truncated_to_200_chars(self):
        long = "// TODO: " + "x" * 500
        r = self._scan(long)
        self.assertEqual(len(r["errors"]), 1)
        self.assertLessEqual(len(r["errors"][0]["message"]), 200)


class TestScanFileDebugOutput(unittest.TestCase):
    """Detect console.log / Console.WriteLine / print debug calls → warning."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scan(self, content: str, rel: str = "src/App/Foo.cs") -> dict:
        f = self.tmp / "f.cs"
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, rel, results)
        return results

    def test_detects_console_log(self):
        r = self._scan("console.log('debug')")
        self.assertTrue(any(w["category"] == "debug-output" for w in r["warnings"]))

    def test_detects_csharp_writeline(self):
        r = self._scan("Console.WriteLine(\"x\")")
        self.assertTrue(any(w["tag"] == "cs-debug" for w in r["warnings"]))

    def test_detects_python_print(self):
        r = self._scan("def f():\n    print('debug')\n", rel="src/api/foo.py")
        self.assertTrue(any(w["tag"] == "py-debug" for w in r["warnings"]))

    def test_each_debug_pattern_classified(self):
        """Every DEBUG_PATTERNS entry produces a recognizable tag."""
        seen_tags = set(DEBUG_PATTERNS.values())
        self.assertIn("js-debug", seen_tags)
        self.assertIn("cs-debug", seen_tags)
        self.assertIn("py-debug", seen_tags)


class TestScanFileForbiddenSddEnv(unittest.TestCase):
    """Detect Pattern B violations: SDD config read directly from env vars."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scan(self, content: str, rel: str) -> dict:
        f = self.tmp / Path(rel).name
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, rel, results)
        return results

    def test_patterns_registered(self):
        self.assertGreaterEqual(len(FORBIDDEN_SDD_ENV_PATTERNS), 6)

    def test_detects_dotnet_sdd_env_read(self):
        r = self._scan(
            'var password = Environment.GetEnvironmentVariable("DB_PASSWORD");',
            "workspace/output/src/Backend/Program.cs",
        )
        self.assertTrue(any(e["category"] == "forbidden-sdd-env" for e in r["errors"]))

    def test_detects_node_sdd_env_read(self):
        r = self._scan(
            "const secret = process.env.AUTH_JWT_SECRET;",
            "workspace/output/src/App/server.ts",
        )
        self.assertTrue(any(e["tag"] == "node-sdd-env-read" for e in r["errors"]))

    def test_detects_python_sdd_env_read(self):
        r = self._scan(
            'tenant = os.environ.get("AZ_TENANTID")',
            "workspace/output/src/Api/app/config.py",
        )
        self.assertTrue(any(e["tag"] == "py-sdd-env-read" for e in r["errors"]))

    def test_detects_spring_direct_env_placeholder(self):
        r = self._scan(
            '@Value("${DB_PASSWORD:}") lateinit var password: String',
            "workspace/output/src/Backend/AuthConfig.kt",
        )
        self.assertTrue(any(e["tag"] == "spring-sdd-env-placeholder" for e in r["errors"]))

    def test_allows_runtime_profile_env(self):
        r = self._scan(
            "if (process.env.NODE_ENV !== 'production') console.warn('dev');",
            "workspace/output/src/App/server.ts",
        )
        self.assertFalse(any(e["category"] == "forbidden-sdd-env" for e in r["errors"]))


class TestScanFileHexHardcoded(unittest.TestCase):
    """Detect hex colors hardcoded outside theme.css → warning."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scan(self, content: str, rel: str) -> dict:
        f = self.tmp / "f.css"
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, rel, results)
        return results

    def test_detects_hex_in_component_css(self):
        r = self._scan(".btn { color: #ff0000; }", "src/App/components/Btn.css")
        self.assertTrue(any(w["category"] == "hardcoded-hex" for w in r["warnings"]))

    def test_detects_short_hex(self):
        r = self._scan(".btn { color: #f00; }", "src/App/components/Btn.css")
        self.assertTrue(any(w["category"] == "hardcoded-hex" for w in r["warnings"]))

    def test_skips_theme_css(self):
        """theme.css is the legitimate location for hex tokens."""
        r = self._scan(":root { --primary: #2563eb; }", "src/App/styles/theme.css")
        self.assertFalse(any(w["category"] == "hardcoded-hex" for w in r["warnings"]))

    def test_skips_non_ui_file_types(self):
        """C# / Python files don't get hex scanned (heuristic)."""
        r = self._scan("var color = \"#ff0000\";", "src/Backend/Services/Foo.cs")
        # .cs is not in the hex-scan regex list, so no hex warning
        self.assertFalse(any(w["category"] == "hardcoded-hex" for w in r["warnings"]))


class TestScanFileLongMethod(unittest.TestCase):
    """Detect methods spanning > 50 lines → warning."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_short_method_not_flagged(self):
        content = textwrap.dedent("""\
            public void Foo() {
                int x = 1;
                return;
            }
        """)
        f = self.tmp / "f.cs"
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, "src/App/Foo.cs", results)
        self.assertFalse(any(w["category"] == "long-method" for w in results["warnings"]))

    def test_long_method_flagged(self):
        body_lines = "\n".join("    int x{} = {};".format(i, i) for i in range(60))
        content = f"public void Foo() {{\n{body_lines}\n}}"
        f = self.tmp / "f.cs"
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, "src/App/Foo.cs", results)
        self.assertTrue(any(w["category"] == "long-method" for w in results["warnings"]),
                        "60-line method should trigger long-method warning")


class TestScanFileMagicNumbers(unittest.TestCase):
    """Magic numbers → info severity (heuristic)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scan(self, content: str, rel: str = "src/App/Foo.cs") -> dict:
        f = self.tmp / "f.cs"
        f.write_text(content, encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, rel, results)
        return results

    def test_detects_arbitrary_magic(self):
        r = self._scan("var timeout = 12345;")
        self.assertTrue(any(i["category"] == "magic-number" for i in r["info"]))

    def test_skips_http_status_code(self):
        r = self._scan("if (code == 404) return;")
        self.assertFalse(any(i["category"] == "magic-number" and "404" in i["message"]
                             for i in r["info"]))

    def test_skips_power_of_two(self):
        r = self._scan("var buf = new byte[1024];")
        self.assertFalse(any(i["category"] == "magic-number" and "1024" in i["message"]
                             for i in r["info"]))

    def test_deduplicates_by_file_and_line(self):
        """Same line should not produce multiple magic-number infos."""
        r = self._scan("var x = 12345; var y = 12345;")
        magic = [i for i in r["info"] if i["category"] == "magic-number"]
        # Both occurrences are on line 1 — only one report per (file, line)
        self.assertEqual(len(magic), 1)


class TestScanFileRobustness(unittest.TestCase):
    """Defensive : never raise on edge content."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_file_silent(self):
        f = self.tmp / "f.cs"
        f.write_text("", encoding="utf-8")
        results = {"errors": [], "warnings": [], "info": []}
        scan_file(f, "src/App/Empty.cs", results)
        self.assertEqual(results["errors"], [])
        self.assertEqual(results["warnings"], [])
        self.assertEqual(results["info"], [])

    def test_binary_file_does_not_crash(self):
        """errors='replace' must absorb non-UTF8 bytes."""
        f = self.tmp / "f.cs"
        f.write_bytes(b"\xff\xfe\x00\x00bad")
        results = {"errors": [], "warnings": [], "info": []}
        # Should not raise
        scan_file(f, "src/App/Bin.cs", results)


if __name__ == "__main__":
    unittest.main()
