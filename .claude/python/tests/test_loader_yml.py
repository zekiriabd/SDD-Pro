"""v7.0.0 P1 — tests for sdd_lib/loader_yml.parse_agent_section.

Cover both legacy scalar form and v7.0.0 inline-dict form, plus the
edge cases the audit flagged (mixed scalar/dict in the same section,
quoted paths, paths containing `{n}/{m}/{Project}` placeholders, items
with trailing comments, blank lines, sections at agent-level matched
against the wrong agent).

Regression contract :
- The audit P0 commit 2026-05-20 fixed dict-form extraction (previous
  regex returned the full `{ path: ..., cache_layer: ... }` literal as
  one string).
- _ITEM_RE = ^\\s{4}- ... requires EXACTLY 4 spaces of indent. Any
  entry indented deeper (6+ spaces under a sub-section) is dropped
  silently. test_six_space_indent_dropped_documents_known_limit
  documents that intentional limit.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.loader_yml import parse_agent_section  # noqa: E402


def _write_loader(root: Path, content: str) -> None:
    loader_dir = root / ".claude"
    loader_dir.mkdir(parents=True, exist_ok=True)
    (loader_dir / "loader.yml").write_text(textwrap.dedent(content), encoding="utf-8")


class TestLoaderYmlScalar(unittest.TestCase):
    def test_pure_scalar_list(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - workspace/input/feats/{n}-*.md
                    - .claude/templates/us.template.md
                  writes:
                    - workspace/output/us/{n}-{m}-*.md
            """)
            self.assertEqual(
                parse_agent_section("po", "reads", root=root),
                [
                    "workspace/input/feats/{n}-*.md",
                    ".claude/templates/us.template.md",
                ],
            )
            self.assertEqual(
                parse_agent_section("po", "writes", root=root),
                ["workspace/output/us/{n}-{m}-*.md"],
            )

    def test_scalar_with_trailing_comment(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                arch:
                  reads:
                    - workspace/input/stack/stack.md           # mandatory
                    - .claude/templates/adr.template.md  # v3 — nécessaire
            """)
            self.assertEqual(
                parse_agent_section("arch", "reads", root=root),
                [
                    "workspace/input/stack/stack.md",
                    ".claude/templates/adr.template.md",
                ],
            )

    def test_quoted_scalar(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - "workspace/input/feats/{n}-*.md"
                    - 'path/with/quotes.md'
            """)
            self.assertEqual(
                parse_agent_section("po", "reads", root=root),
                [
                    "workspace/input/feats/{n}-*.md",
                    "path/with/quotes.md",
                ],
            )


class TestLoaderYmlDictForm(unittest.TestCase):
    """v7.0.0+ inline-flow dict form: { path: ..., cache_layer: ... }."""

    def test_pure_dict_list(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                dev-backend:
                  reads:
                    - { path: workspace/output/us/{n}-{m}-*.md, cache_layer: volatile }
                    - { path: workspace/input/ui/{n}-{m}-*.html, cache_layer: volatile }
                    - { path: workspace/output/src/{Project}/CLAUDE.md, cache_layer: semi }
            """)
            self.assertEqual(
                parse_agent_section("dev-backend", "reads", root=root),
                [
                    "workspace/output/us/{n}-{m}-*.md",
                    "workspace/input/ui/{n}-{m}-*.html",
                    "workspace/output/src/{Project}/CLAUDE.md",
                ],
            )

    def test_mixed_scalar_and_dict(self) -> None:
        """Audit P0 regression: both forms must coexist in the same section."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                code-reviewer:
                  reads:
                    - workspace/input/stack/stack.md
                    - { path: .claude/rules/error-classification.md, cache_layer: stable }
                    - .claude/rules/build-and-loop.md
                    - { path: workspace/output/us/{n}-*.md, cache_layer: volatile }
                    - workspace/input/feats/{n}-*.md
            """)
            self.assertEqual(
                parse_agent_section("code-reviewer", "reads", root=root),
                [
                    "workspace/input/stack/stack.md",
                    ".claude/rules/error-classification.md",
                    ".claude/rules/build-and-loop.md",
                    "workspace/output/us/{n}-*.md",
                    "workspace/input/feats/{n}-*.md",
                ],
            )

    def test_dict_with_quoted_path(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                dev-backend:
                  reads:
                    - { path: "workspace/output/us/{n}-{m}-*.md", cache_layer: volatile }
                    - { path: 'workspace/input/ui/{n}-{m}-*.html', cache_layer: volatile }
            """)
            self.assertEqual(
                parse_agent_section("dev-backend", "reads", root=root),
                [
                    "workspace/output/us/{n}-{m}-*.md",
                    "workspace/input/ui/{n}-{m}-*.html",
                ],
            )

    def test_dict_path_only_no_extra_keys(self) -> None:
        """Dict form with only `path:` (no cache_layer)."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                arch:
                  reads:
                    - { path: workspace/input/stack/stack.md }
            """)
            self.assertEqual(
                parse_agent_section("arch", "reads", root=root),
                ["workspace/input/stack/stack.md"],
            )

    def test_malformed_dict_skipped_silently(self) -> None:
        """A `{` opener without a parseable `path:` is skipped, not crashed on."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - { not_a_path: foo, cache_layer: stable }
                    - workspace/input/feats/{n}-*.md
            """)
            # Malformed dict dropped; valid scalar survives.
            self.assertEqual(
                parse_agent_section("po", "reads", root=root),
                ["workspace/input/feats/{n}-*.md"],
            )


class TestLoaderYmlAgentScoping(unittest.TestCase):
    def test_returns_only_target_agent_section(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - workspace/input/feats/{n}-*.md
                arch:
                  reads:
                    - workspace/input/stack/stack.md
                    - { path: .claude/templates/adr.template.md, cache_layer: stable }
            """)
            self.assertEqual(
                parse_agent_section("po", "reads", root=root),
                ["workspace/input/feats/{n}-*.md"],
            )
            self.assertEqual(
                parse_agent_section("arch", "reads", root=root),
                [
                    "workspace/input/stack/stack.md",
                    ".claude/templates/adr.template.md",
                ],
            )

    def test_unknown_agent_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - workspace/input/feats/{n}-*.md
            """)
            self.assertEqual(
                parse_agent_section("nonexistent-agent", "reads", root=root),
                [],
            )

    def test_missing_section_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - workspace/input/feats/{n}-*.md
            """)
            self.assertEqual(
                parse_agent_section("po", "writes", root=root),
                [],
            )

    def test_missing_loader_file_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            # No loader.yml created.
            self.assertEqual(
                parse_agent_section("po", "reads", root=root),
                [],
            )


class TestLoaderYmlEdgeCases(unittest.TestCase):
    def test_forbidden_reads_section(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                arch:
                  reads:
                    - workspace/input/stack/stack.md
                  forbidden_reads:
                    - workspace/input/feats/
                    - workspace/output/us/
            """)
            self.assertEqual(
                parse_agent_section("arch", "forbidden_reads", root=root),
                ["workspace/input/feats/", "workspace/output/us/"],
            )

    def test_six_space_indent_dropped_documents_known_limit(self) -> None:
        """_ITEM_RE matches EXACTLY 4 spaces indent — deeper nesting is dropped.

        This is a known parser limitation, not a regression. If future
        loader.yml schema introduces sub-sections (e.g. reads_env: under
        reads:), the regex needs widening — this test will fail and
        force a conscious update.
        """
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                arch:
                  reads:
                    - workspace/input/stack/stack.md
                      - nested_at_6_spaces.md
            """)
            # Only the 4-space entry is captured; the 6-space line is dropped.
            self.assertEqual(
                parse_agent_section("arch", "reads", root=root),
                ["workspace/input/stack/stack.md"],
            )

    def test_blank_lines_between_items(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _write_loader(root, """\
                po:
                  reads:
                    - workspace/input/feats/{n}-*.md

                    - .claude/templates/us.template.md
            """)
            self.assertEqual(
                parse_agent_section("po", "reads", root=root),
                [
                    "workspace/input/feats/{n}-*.md",
                    ".claude/templates/us.template.md",
                ],
            )


if __name__ == "__main__":
    unittest.main()
