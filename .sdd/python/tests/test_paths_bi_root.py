"""Bi-racine tests — MIGRATION-PLAN Phase 1 (2026-07-25).

Vérifie que `sdd_lib.paths` accepte à la fois le layout `.sdd/` (foyer
neutre, cible) et `.claude/` (façade legacy, en attente de génération)
comme repo root valide, et que les helpers sémantiques (`sdd_home`,
`rules_dir`, etc.) préfèrent `.sdd/` si présent.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import paths  # noqa: E402


def _make_sdd_repo(root: Path) -> None:
    (root / ".sdd" / "agents").mkdir(parents=True)
    (root / ".sdd" / "commands").mkdir(parents=True)
    (root / "workspace").mkdir()


def _make_claude_repo(root: Path) -> None:
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "workspace").mkdir()


def _make_dual_repo(root: Path) -> None:
    (root / ".sdd" / "agents").mkdir(parents=True)
    (root / ".sdd" / "commands").mkdir(parents=True)
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "workspace").mkdir()


class TestLooksLikeRepoRootBiRoot(unittest.TestCase):
    def test_sdd_only_layout_accepted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_sdd_repo(root)
            self.assertTrue(paths._looks_like_repo_root(root))

    def test_claude_only_layout_still_accepted(self) -> None:
        """Backwards compat : the legacy .claude/-only layout remains valid."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_claude_repo(root)
            self.assertTrue(paths._looks_like_repo_root(root))

    def test_dual_layout_accepted(self) -> None:
        """Transitional bi-racine : both dirs present is OK."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            self.assertTrue(paths._looks_like_repo_root(root))

    def test_sdd_partial_layout_rejected(self) -> None:
        """.sdd/ without commands/ is not sufficient."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sdd" / "agents").mkdir(parents=True)
            (root / "workspace").mkdir()
            # Missing .sdd/commands/ → reject
            self.assertFalse(paths._looks_like_repo_root(root))

    def test_neither_layout_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace").mkdir()
            self.assertFalse(paths._looks_like_repo_root(root))


class TestSddHome(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = os.environ.pop("SDD_HOME", None)

    def tearDown(self) -> None:
        if self._old_env is not None:
            os.environ["SDD_HOME"] = self._old_env
        else:
            os.environ.pop("SDD_HOME", None)

    def test_env_override_wins(self) -> None:
        with TemporaryDirectory() as tmp:
            override = Path(tmp) / "custom-sdd"
            override.mkdir()
            os.environ["SDD_HOME"] = str(override)
            self.assertEqual(paths.sdd_home().resolve(), override.resolve())

    def test_prefers_sdd_dir_when_present(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            resolved = paths.sdd_home(repo_root_path=root)
            self.assertEqual(resolved, root / ".sdd")

    def test_falls_back_to_claude_when_sdd_absent(self) -> None:
        """Transitional fallback : if `.sdd/` doesn't exist yet, use `.claude/`."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_claude_repo(root)
            resolved = paths.sdd_home(repo_root_path=root)
            self.assertEqual(resolved, root / ".claude")


class TestClaudeHome(unittest.TestCase):
    def test_always_returns_claude_subdir(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            self.assertEqual(paths.claude_home(repo_root_path=root), root / ".claude")

    def test_returns_claude_subdir_even_when_missing(self) -> None:
        """`.claude/` may not exist yet after Phase 2 build — path is still resolvable."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(paths.claude_home(repo_root_path=root), root / ".claude")


class TestSemanticHelpers(unittest.TestCase):
    """Vérifie les 8 helpers sémantiques (rules_dir, stacks_dir, ...).

    Contrat commun : préfère `.sdd/<sub>/` s'il existe, sinon retombe sur
    `.claude/<sub>/`. Le fallback est granulaire (par sous-répertoire) pour
    tolérer une migration partielle — ex. `.sdd/agents/` existe déjà mais
    `.sdd/rules/` pas encore.
    """

    def test_rules_dir_prefers_sdd(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".sdd" / "rules").mkdir()
            (root / ".claude" / "rules").mkdir()
            self.assertEqual(paths.rules_dir(repo_root_path=root), root / ".sdd" / "rules")

    def test_rules_dir_falls_back_to_claude(self) -> None:
        """Rules pas encore migrées : `.sdd/rules/` absent → `.claude/rules/`."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".claude" / "rules").mkdir()
            # No .sdd/rules/ — should fall back to .claude/
            self.assertEqual(paths.rules_dir(repo_root_path=root), root / ".claude" / "rules")

    def test_templates_dir_bi_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".sdd" / "templates").mkdir()
            self.assertEqual(paths.templates_dir(repo_root_path=root), root / ".sdd" / "templates")

    def test_stacks_dir_bi_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".sdd" / "stacks").mkdir()
            self.assertEqual(paths.stacks_dir(repo_root_path=root), root / ".sdd" / "stacks")

    def test_skills_dir_falls_back_to_claude(self) -> None:
        """Skills pas encore migrées : `.sdd/skills/` absent → `.claude/skills/`."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".claude" / "skills").mkdir()
            self.assertEqual(paths.skills_dir(repo_root_path=root), root / ".claude" / "skills")

    def test_agents_dir_prefers_sdd(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            # Both .sdd/agents/ and .claude/agents/ exist (from _make_dual_repo)
            self.assertEqual(paths.agents_dir(repo_root_path=root), root / ".sdd" / "agents")

    def test_commands_dir_prefers_sdd(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            self.assertEqual(paths.commands_dir(repo_root_path=root), root / ".sdd" / "commands")

    def test_python_dir_falls_back_to_claude(self) -> None:
        """Python pas encore migré (331 fichiers) : `.sdd/python/` partiel, `.claude/python/` autoritaire."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".sdd" / "python").mkdir()
            # No .sdd/python/ subdir → fall back
            self.assertEqual(paths.python_dir(repo_root_path=root), root / ".sdd" / "python")

    def test_docs_dir_bi_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_dual_repo(root)
            (root / ".sdd" / "docs").mkdir()
            (root / ".claude" / "docs").mkdir()
            # .sdd/docs/ exists → preferred
            self.assertEqual(paths.docs_dir(repo_root_path=root), root / ".sdd" / "docs")


class TestSddHomeOnRealRepo(unittest.TestCase):
    """Smoke test on the real repo — sdd_home() must not raise and must
    point to an existing directory."""

    def test_sdd_home_on_real_repo(self) -> None:
        home = paths.sdd_home()
        self.assertTrue(home.is_dir(), f"sdd_home() returned non-existent {home}")
        # In transitional state, it must be either .sdd/ or .claude/
        self.assertIn(home.name, (".sdd", ".claude"))

    def test_semantic_helpers_return_real_dirs(self) -> None:
        for helper_name in ("agents_dir", "commands_dir", "templates_dir", "stacks_dir"):
            with self.subTest(helper=helper_name):
                helper = getattr(paths, helper_name)
                d = helper()
                self.assertTrue(d.is_dir(), f"{helper_name}() returned non-existent {d}")


if __name__ == "__main__":
    unittest.main()
