"""Smoke test : /sdd-help FAQ keeps file/command references in sync.

Audit P3 T3 (2026-06-08) — the FAQ in `.claude/commands/sdd-help.md` is a
static lookup table mapping user keywords to file paths and slash commands.
When commands are renamed, files moved, or templates retired, the FAQ
silently rots. This smoke test parses the FAQ table and verifies that :

1. Every relative path referenced (`.sdd/templates/*`, `workspace/...`)
   either exists OR is documented as a target/output (workspace paths
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


from sdd_lib.paths import repo_root as _repo_root  # noqa: E402  (SSoT — conso audit 2026-06-11, ex-copies locales)


def _faq_text() -> str:
    """Read the /sdd-help command markdown."""
    return (_repo_root() / ".claude" / "commands" / "sdd-help.md").read_text(encoding="utf-8")


# Paths that don't need to exist at test time because they are RUNTIME
# outputs (created on demand by agents/scripts) or expected to be empty
# folders that user populates.
_RUNTIME_PATH_PREFIXES = (
    "workspace/",
    "workspace/discovery/",  # may be empty until Tech Lead populates
    "workspace/ui/",          # may be empty (mockups optional)
    "workspace/assets/",
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
        """Every `.sdd/templates/X.template.md` referenced exists on disk."""
        text = _faq_text()
        # Match patterns like `.sdd/templates/product-brief.template.md`
        pattern = r"\.sdd/templates/([a-zA-Z0-9._-]+\.template\.[a-zA-Z]+)"
        found = set(re.findall(pattern, text))
        from sdd_lib.paths import templates_dir as _templates_dir
        templates_dir = _templates_dir(_repo_root())
        missing = [t for t in sorted(found) if not (templates_dir / t).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references templates not present in .sdd/templates/: {missing}",
        )

    def test_docs_paths_referenced_exist(self):
        """Every `.sdd/docs/X.md` or `@.sdd/docs/X.md` referenced exists."""
        text = _faq_text()
        # Match patterns like `.sdd/docs/cookbook.md`, `@.sdd/docs/quickstart.md`
        pattern = r"@?\.sdd/docs/([a-zA-Z0-9._/-]+\.md)"
        found = set(re.findall(pattern, text))
        from sdd_lib.paths import docs_dir as _docs_dir
        docs_dir = _docs_dir(_repo_root())
        missing = [d for d in sorted(found) if not (docs_dir / d).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references docs not present in .sdd/docs/: {missing}",
        )

    def test_rules_paths_referenced_exist(self):
        """Every `@.sdd/rules/X.md` (or legacy `@.claude/rules/X.md`) reference points to a real rule file.

        Bi-racine 2026-07-25 (Phase 1) : rules migrées `.claude/rules/` →
        `.sdd/rules/`. Le pattern accepte les deux formes ; `rules_dir()`
        résout la racine réelle.
        """
        from sdd_lib.paths import rules_dir as _rules_dir
        text = _faq_text()
        pattern = r"@?\.(?:claude|sdd)/rules/([a-zA-Z0-9._-]+\.md)"
        found = set(re.findall(pattern, text))
        rules_d = _rules_dir(_repo_root())
        missing = [r for r in sorted(found) if not (rules_d / r).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references rules not present in {rules_d}: {missing}",
        )

    def test_python_scripts_referenced_exist(self):
        """Every `.sdd/python/sdd_scripts/X.py` reference points to a real script."""
        text = _faq_text()
        pattern = r"\.sdd/python/sdd_scripts/([a-zA-Z0-9._-]+\.py)"
        found = set(re.findall(pattern, text))
        scripts_dir = _repo_root() / ".sdd" / "python" / "sdd_scripts"
        missing = [s for s in sorted(found) if not (scripts_dir / s).is_file()]
        self.assertFalse(
            missing,
            f"FAQ references scripts not present in .sdd/python/sdd_scripts/: {missing}",
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
