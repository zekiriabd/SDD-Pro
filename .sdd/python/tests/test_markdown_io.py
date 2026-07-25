"""Unit tests for sdd_lib/markdown_io.py — frontmatter + section parsing SSoT."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import markdown_io  # noqa: E402


class TestParseFrontmatter(unittest.TestCase):
    def test_basic_frontmatter(self) -> None:
        text = "---\nname: foo\nversion: 1.0\n---\n# Body content\n"
        result = markdown_io.parse_frontmatter(text)
        self.assertIsNotNone(result)
        fm, body = result
        self.assertEqual(fm, {"name": "foo", "version": "1.0"})
        self.assertEqual(body, "# Body content\n")

    def test_no_frontmatter_returns_none(self) -> None:
        self.assertIsNone(markdown_io.parse_frontmatter("# Direct H1\nBody"))

    def test_quotes_stripped(self) -> None:
        text = '---\ntitle: "Hello World"\nslug: \'foo-bar\'\n---\n'
        fm, _ = markdown_io.parse_frontmatter(text)
        self.assertEqual(fm["title"], "Hello World")
        self.assertEqual(fm["slug"], "foo-bar")

    def test_comments_and_blanks_skipped(self) -> None:
        text = "---\n# This is a comment\nname: foo\n\n# Another comment\nver: 1.0\n---\n"
        fm, _ = markdown_io.parse_frontmatter(text)
        self.assertEqual(fm, {"name": "foo", "ver": "1.0"})

    def test_idempotent(self) -> None:
        text = "---\nkey: value\n---\nbody"
        r1 = markdown_io.parse_frontmatter(text)
        r2 = markdown_io.parse_frontmatter(text)
        self.assertEqual(r1, r2)

    def test_invalid_keys_skipped(self) -> None:
        """Keys not matching ^[A-Za-z][A-Za-z0-9_-]*$ are dropped."""
        text = "---\nvalid-key: ok\n123invalid: nope\n---\n"
        fm, _ = markdown_io.parse_frontmatter(text)
        self.assertIn("valid-key", fm)
        self.assertNotIn("123invalid", fm)


class TestExtractFrontmatterRaw(unittest.TestCase):
    def test_returns_full_block(self) -> None:
        text = "---\nkey: val\n---\nbody"
        raw = markdown_io.extract_frontmatter_raw(text)
        self.assertTrue(raw.startswith("---\n"))
        self.assertIn("key: val", raw)
        self.assertTrue(raw.endswith("---\n"))

    def test_no_frontmatter_returns_empty(self) -> None:
        self.assertEqual(markdown_io.extract_frontmatter_raw("# No frontmatter"), "")


class TestSectionBody(unittest.TestCase):
    def test_extracts_section_between_headings(self) -> None:
        text = (
            "# Title\n"
            "## Project Config\n"
            "AppName: foo\n"
            "## Active Tech Specs\n"
            "- backend\n"
        )
        body = markdown_io.section_body(text, "Project Config")
        self.assertEqual(body, "AppName: foo\n")

    def test_extracts_last_section_to_eof(self) -> None:
        text = "## First\nA\n## Last\nfinal content"
        body = markdown_io.section_body(text, "Last")
        self.assertEqual(body, "final content")

    def test_missing_section_returns_none(self) -> None:
        text = "## Other\ncontent"
        self.assertIsNone(markdown_io.section_body(text, "Missing"))

    def test_relaxed_whitespace_in_heading(self) -> None:
        """`Project Config` matches `## Project   Config` (collapsed spaces)."""
        text = "## Project   Config\nbody"
        body = markdown_io.section_body(text, "Project Config")
        self.assertEqual(body, "body")

    def test_special_chars_in_heading_escaped(self) -> None:
        """Heading with regex meta-chars is properly escaped."""
        text = "## Heading.with.dots\nbody"
        body = markdown_io.section_body(text, "Heading.with.dots")
        self.assertEqual(body, "body")


class TestSectionBodyStripped(unittest.TestCase):
    def test_strips_whitespace(self) -> None:
        text = "## S\n\n  content  \n\n## Next\n"
        result = markdown_io.section_body_stripped(text, "S")
        self.assertEqual(result, "content")

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(markdown_io.section_body_stripped("## A\nx", "B"))


class TestParseUsFile(unittest.TestCase):
    def test_basic_us_parsing(self) -> None:
        with TemporaryDirectory() as tmp:
            us_file = Path(tmp) / "4-1-Calcul-Vue.md"
            us_file.write_text(
                "# US-1: Calcul-Vue\n"
                "\n"
                "ID: 4-1-Calcul-Vue\n"
                "Status: Ready\n"
                "\n"
                "## Acceptance Criteria\n"
                "- AC-1: foo\n"
                "- AC-2: bar\n"
                "\n"
                "## Covers\n"
                "Covers:\n"
                "- SFD-1\n"
                "- AC-1\n"
                "- BR-2\n",
                encoding="utf-8",
            )
            result = markdown_io.parse_us_file(us_file)
            self.assertEqual(result["us_id"], "4-1")
            self.assertEqual(result["n"], 4)
            self.assertEqual(result["m"], 1)
            self.assertEqual(result["name"], "Calcul-Vue")
            self.assertEqual(result["status"], "Ready")
            self.assertEqual(result["ac_ids"], ["AC-1", "AC-2"])
            self.assertIn("SFD-1", result["covers"])
            self.assertIn("BR-2", result["covers"])

    def test_invalid_filename_returns_empty_dict(self) -> None:
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "not-a-us.md"
            bad.write_text("# stuff", encoding="utf-8")
            self.assertEqual(markdown_io.parse_us_file(bad), {})

    def test_missing_file_returns_empty_dict(self) -> None:
        nonexistent = Path("/nonexistent/4-1-Foo.md")
        self.assertEqual(markdown_io.parse_us_file(nonexistent), {})

    def test_status_default_to_draft(self) -> None:
        with TemporaryDirectory() as tmp:
            us = Path(tmp) / "1-1-Auth.md"
            us.write_text("# US\n\nNo status line\n", encoding="utf-8")
            result = markdown_io.parse_us_file(us)
            self.assertEqual(result["status"], "Draft")

    def test_ac_ids_sorted_and_deduped(self) -> None:
        with TemporaryDirectory() as tmp:
            us = Path(tmp) / "1-1-Foo.md"
            us.write_text(
                "AC-3: third\n"
                "AC-1: first\n"
                "AC-2: second\n"
                "AC-1: dup of first\n",
                encoding="utf-8",
            )
            result = markdown_io.parse_us_file(us)
            self.assertEqual(result["ac_ids"], ["AC-1", "AC-2", "AC-3"])


if __name__ == "__main__":
    unittest.main()
