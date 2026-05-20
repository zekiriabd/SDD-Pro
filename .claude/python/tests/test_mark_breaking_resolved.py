"""Tests for sdd_scripts.mark_breaking_resolved — BREAKING CHANGES cleanup."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import mark_breaking_resolved as mbr  # noqa: E402


CLAUDE_MD_WITH_BREAKING = """# Project CLAUDE.md

Some preamble.

## BREAKING CHANGES

The following files were impacted:
- Pages/Bebes.razor (refactor)
- Components/BebeForm.razor

Action required: rerun /dev-run 1.

## Layer Mapping

Backend → Services → Repositories.
"""


CLAUDE_MD_RESOLVED = """# Project CLAUDE.md

## BREAKING CHANGES — RESOLVED 2026-05-10

> **Statut** : ✅ RESOLU — `dotnet build` passe (0 erreur).

## Layer Mapping
"""


CLAUDE_MD_NO_BREAKING = """# Project CLAUDE.md

## Layer Mapping

Backend → Services → Repositories.
"""


class TestMainPaths(unittest.TestCase):
    def _run(self, *args: str) -> int:
        with mock.patch.object(sys, "argv",
                               ["mark_breaking_resolved.py", *args]):
            return mbr.main()

    def test_file_not_found_returns_3(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            missing = Path(tmp) / "nope.md"
            rc = self._run(
                "--claude-md", str(missing),
                "--modified-files", "Foo.cs",
                "--build-command", "dotnet build",
            )
            self.assertEqual(rc, 3)

    def test_no_breaking_section_returns_0(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cm = Path(tmp) / "CLAUDE.md"
            cm.write_text(CLAUDE_MD_NO_BREAKING, encoding="utf-8")
            rc = self._run(
                "--claude-md", str(cm),
                "--modified-files", "Foo.cs",
                "--build-command", "dotnet build",
            )
            self.assertEqual(rc, 0)
            self.assertEqual(cm.read_text(encoding="utf-8"),
                             CLAUDE_MD_NO_BREAKING)

    def test_already_resolved_returns_0(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cm = Path(tmp) / "CLAUDE.md"
            cm.write_text(CLAUDE_MD_RESOLVED, encoding="utf-8")
            rc = self._run(
                "--claude-md", str(cm),
                "--modified-files", "Foo.cs",
                "--build-command", "dotnet build",
            )
            self.assertEqual(rc, 0)

    def test_coherent_files_marks_resolved(self):
        """v7.0.0 — was returning 1 (= success in legacy semantics), now returns 0
        (sdd_lib/exit_codes.py SUCCESS convention). Stdout '[OK]' prefix indicates action."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cm = Path(tmp) / "CLAUDE.md"
            cm.write_text(CLAUDE_MD_WITH_BREAKING, encoding="utf-8")
            rc = self._run(
                "--claude-md", str(cm),
                "--modified-files", "Pages/Bebes.razor,Components/BebeForm.razor",
                "--build-command", "dotnet build",
            )
            self.assertEqual(rc, 0)
            after = cm.read_text(encoding="utf-8")
            self.assertIn("BREAKING CHANGES — RESOLVED", after)
            self.assertIn("RESOLU", after)
            self.assertIn("dotnet build", after)

    def test_no_coherence_returns_0_skip(self):
        """v7.0.0 — was returning 2 (skip-incoherent), now returns 0 (skip is a
        valid SUCCESS outcome). File unchanged. Stdout '[SKIP]' prefix indicates."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cm = Path(tmp) / "CLAUDE.md"
            cm.write_text(CLAUDE_MD_WITH_BREAKING, encoding="utf-8")
            rc = self._run(
                "--claude-md", str(cm),
                "--modified-files", "OtherFile.cs",  # not in section
                "--build-command", "dotnet build",
            )
            self.assertEqual(rc, 0)
            # File not modified.
            self.assertEqual(cm.read_text(encoding="utf-8"),
                             CLAUDE_MD_WITH_BREAKING)

    def test_basename_match_coherent(self):
        """Modified files passed with path but section mentions basename only."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cm = Path(tmp) / "CLAUDE.md"
            cm.write_text(CLAUDE_MD_WITH_BREAKING, encoding="utf-8")
            rc = self._run(
                "--claude-md", str(cm),
                "--modified-files", "src/Pages/Bebes.razor",  # full path
                "--build-command", "dotnet build",
            )
            self.assertEqual(rc, 0)

    def test_dry_run_does_not_write(self):
        """v7.0.0 — was 1, now 0 (SUCCESS — dry-run is informational not error)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cm = Path(tmp) / "CLAUDE.md"
            original = CLAUDE_MD_WITH_BREAKING
            cm.write_text(original, encoding="utf-8")
            rc = self._run(
                "--claude-md", str(cm),
                "--modified-files", "Pages/Bebes.razor",
                "--build-command", "dotnet build",
                "--dry-run",
            )
            self.assertEqual(rc, 0)
            self.assertEqual(cm.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
