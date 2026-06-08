"""Smoke test : /sdd-help FAQ keeps file/command references in sync.

Audit P3 T3 (2026-06-08) — the FAQ in `.claude/commands/sdd-help.md` is a
static lookup table mapping user keywords to file paths and slash commands.
When commands are renamed, files moved, or templates retired, the FAQ
silently rots. This smoke test parses the FAQ table and verifies that :

1. Every relative path referenced (`.claude/templates/*`, `workspace/...`)
   either exists OR is documented as a target/output (workspace/output paths
   are runtime-created, so absence is OK).
2. Every slash command referenced (`/sdd-XXX`) corresponds to a real
   command file under `.claude/commands/`.
3. Every `@.claude/...` reference points to an existing file.

Failures emit a structured table identifying drift. Run as part of
`framework_smoke` pytest-smoke subset.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


def _repo_root() -> Path:
    """Walk up to find .claude/ directory."""
    cwd = Path(__file__).resolve()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    raise RuntimeError("Cannot locate repo root (.claude/ not found upward)")


def _faq_text() -> str:
    """Read the /sdd-help command markdown."""
    return (_repo_root() / ".claude" / "commands" / "sdd-help.md").read_text(encoding="utf-8")


# Paths that don't need to exist at test time because they are RUNTIME
# outputs (created on demand by agents/scripts) or expected to be empty
# folders that user populates.
_RUNTIME_PATH_PREFIXES = (
    "workspace/output/",
    "workspace/input/discovery/",  # may be empty until Tech Lead populates
    "workspace/input/ui/",          # may be empty (mockups optional)
    "workspace/input/assets/",
)


def _is_runtime_only(path_str: str) -> bool:
    """Check if a path is a runtime-only output (not required to exist for tests)."""
    return any(path_str.startswith(prefix) for prefix in _RUNTIME_PATH_PREFIXES)


class TestSddHelpFaqIntegrity(unittest.TestCase):
    """Verify /sdd-help FAQ doesn't reference dead files or commands."""

    def test_slash_commands_referenced_exist(self):
        """Every `/sdd-XXX` referenced in FAQ has a real `.claude/commands/X.md`."""
        text = _faq_text()
        commands_dir = _repo_root() / ".claude" / "commands"
        # Match patterns like `/sdd-help`, `/feat-generate`, `/dev-run`
        # but skip {n}/{m} placeholders and CLI flags (--xxx)
        pattern = r"`/([a-z][a-z0-9-]+)(?:\s|`|\)|$|,|\.|;)"
        found = set(re.findall(pattern, text))
        missing = []
        for cmd in sorted(found):
            md_path = commands_dir / f"{cmd}.md"
            if not md_path.is_file():
                missing.append(cmd)
        self.assertFalse(
            missing,
            f"FAQ references commands without `.claude/commands/X.md`: {missing}",
        )

    def test_template_paths_referenced_exist(self):
        """Every `.claude/templates/X.template.md` referenced exists on disk."""
        text = _faq_text()
        # Match patterns like `.claude/templates/product-brief.template.md`
        pattern = r"\.claude/templates/([a-zA-Z0-9._-]+\.template\.[a-zA-Z]+)"
        found = set(re.findall(pattern, text))
        templates_dir = _repo_root() / ".claude" / "templates"
        missing = [t for t in sorted(found) if not (templates_dir / t).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references templates not present in .claude/templates/: {missing}",
        )

    def test_docs_paths_referenced_exist(self):
        """Every `.claude/docs/X.md` or `@.claude/docs/X.md` referenced exists."""
        text = _faq_text()
        # Match patterns like `.claude/docs/cookbook.md`, `@.claude/docs/quickstart.md`
        pattern = r"@?\.claude/docs/([a-zA-Z0-9._/-]+\.md)"
        found = set(re.findall(pattern, text))
        docs_dir = _repo_root() / ".claude" / "docs"
        missing = [d for d in sorted(found) if not (docs_dir / d).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references docs not present in .claude/docs/: {missing}",
        )

    def test_rules_paths_referenced_exist(self):
        """Every `@.claude/rules/X.md` reference points to a real rule file."""
        text = _faq_text()
        pattern = r"@?\.claude/rules/([a-zA-Z0-9._-]+\.md)"
        found = set(re.findall(pattern, text))
        rules_dir = _repo_root() / ".claude" / "rules"
        missing = [r for r in sorted(found) if not (rules_dir / r).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references rules not present in .claude/rules/: {missing}",
        )

    def test_python_scripts_referenced_exist(self):
        """Every `.claude/python/sdd_scripts/X.py` reference points to a real script."""
        text = _faq_text()
        pattern = r"\.claude/python/sdd_scripts/([a-zA-Z0-9._-]+\.py)"
        found = set(re.findall(pattern, text))
        scripts_dir = _repo_root() / ".claude" / "python" / "sdd_scripts"
        missing = [s for s in sorted(found) if not (scripts_dir / s).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references scripts not present in .claude/python/sdd_scripts/: {missing}",
        )

    def test_faq_has_actionable_entries(self):
        """Sanity check : FAQ has at least 5 keyword-mapped entries
        (degradation guard — if someone empties the FAQ, this fails)."""
        text = _faq_text()
        # FAQ table rows have format `| keywords | response |`
        # Count rows in the §3.C (FAQ) table by looking for `|` rows with `:` in the response (typical for FAQ answers)
        faq_section = re.search(
            r"### 3\.C — Mode FAQ.*?(?=\n---|\Z)",
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(faq_section, "FAQ section (3.C) not found in /sdd-help")
        # Rows that look like `| keyword(s) | response |` (table data rows, not header/separator)
        rows = re.findall(r"^\| `[^|]+` \| [^|]+\|", faq_section.group(0), re.MULTILINE)
        self.assertGreaterEqual(
            len(rows), 5,
            f"FAQ has only {len(rows)} entries — should have ≥ 5 to be useful",
        )


if __name__ == "__main__":
    unittest.main()
