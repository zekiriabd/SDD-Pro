"""Unit tests for sdd_lib/paths.py — repo root + cross-platform helpers."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import paths  # noqa: E402


def _make_fake_repo(root: Path) -> None:
    (root / ".claude" / "agents").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / "workspace").mkdir()


class TestIsoNow(unittest.TestCase):
    def test_format_second_precision(self) -> None:
        ts = paths.iso_now()
        # 2026-06-07T14:30:22Z
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_format_ms_precision(self) -> None:
        ts = paths.iso_now_ms()
        # 2026-06-07T14:30:22.123Z
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class TestNormalize(unittest.TestCase):
    def test_backslash_to_forward_slash(self) -> None:
        self.assertEqual(paths.normalize("foo\\bar\\baz"), "foo/bar/baz")

    def test_mixed_separators(self) -> None:
        self.assertEqual(paths.normalize("a/b\\c/d"), "a/b/c/d")

    def test_already_normalized(self) -> None:
        self.assertEqual(paths.normalize("a/b/c"), "a/b/c")

    def test_accepts_pathlike(self) -> None:
        self.assertEqual(paths.normalize(Path("a") / "b"), "a/b")


class TestLooksLikeRepoRoot(unittest.TestCase):
    def test_strict_check_requires_all_three(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Empty dir → not a root
            self.assertFalse(paths._looks_like_repo_root(root))
            # Only .claude/ → still not a root (strict check)
            (root / ".claude").mkdir()
            self.assertFalse(paths._looks_like_repo_root(root))
            # Add agents/ → still incomplete (no commands/)
            (root / ".claude" / "agents").mkdir()
            self.assertFalse(paths._looks_like_repo_root(root))
            # Add commands/ → still incomplete (no workspace/)
            (root / ".claude" / "commands").mkdir()
            self.assertFalse(paths._looks_like_repo_root(root))
            # Add workspace/ → now it's a root
            (root / "workspace").mkdir()
            self.assertTrue(paths._looks_like_repo_root(root))


class TestRepoRoot(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = os.environ.pop("SDD_REPO_ROOT", None)

    def tearDown(self) -> None:
        if self._old_env is not None:
            os.environ["SDD_REPO_ROOT"] = self._old_env
        else:
            os.environ.pop("SDD_REPO_ROOT", None)

    def test_env_override_honored_even_if_incomplete(self) -> None:
        """SDD_REPO_ROOT is trusted as-is (warn only, no fallback)."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # NOT a fully scaffolded root — but override should still win
            os.environ["SDD_REPO_ROOT"] = str(root)
            resolved = paths.repo_root()
            self.assertEqual(resolved.resolve(), root.resolve())

    def test_env_override_with_valid_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            os.environ["SDD_REPO_ROOT"] = str(root)
            resolved = paths.repo_root()
            self.assertEqual(resolved.resolve(), root.resolve())


class TestRelativeToRoot(unittest.TestCase):
    def test_inside_root_returns_relative(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "workspace" / "output" / "foo.md"
            target.parent.mkdir(parents=True)
            target.touch()
            rel = paths.relative_to_root(target, root=root)
            self.assertEqual(rel, "workspace/output/foo.md")

    def test_outside_root_returns_absolute_normalized(self) -> None:
        """Path outside root falls back to absolute (normalized to forward slashes)."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "repo"
            root.mkdir()
            outside = Path(tmp).resolve() / "elsewhere" / "foo.md"
            outside.parent.mkdir()
            outside.touch()
            rel = paths.relative_to_root(outside, root=root)
            # Should be absolute path with forward slashes (no relative_to root)
            self.assertNotIn("\\", rel)
            self.assertTrue(rel.endswith("/elsewhere/foo.md"))


if __name__ == "__main__":
    unittest.main()
