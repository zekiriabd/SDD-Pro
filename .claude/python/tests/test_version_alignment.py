"""Cross-surface version alignment test (audit CTO 2026-06-07).

Pre-fix : Python package was `0.1.0` while framework was `7.0.0-alpha`.
External users `pip install sdd-pro-tools==0.1.0` were confused about
maturity vs the v7 marketing surface.

This test pins the alignment :
  - sdd_lib.__version__              (PEP 440 form, e.g. "7.0.0a0")
  - sdd_lib.__framework_version__    (human form, e.g. "7.0.0-alpha")
  - pyproject.toml [project].version (must equal __version__)
  - loader.yml `version`             (must equal __framework_version__)
  - CLAUDE.md `v{X}` headline mention (informational — not enforced strictly
    because the entry-point doc can carry a "current branch" tag)

Failing test = drift between Python package version and framework DSL.
Bump rule : bump ALL four surfaces in the same PR. PEP 440 mapping
(`-alpha` → `aN`, `-beta.N` → `bN`, `-rc.N` → `rcN`) is enforced too.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

import sdd_lib  # noqa: E402

pytestmark = pytest.mark.smoke

_REPO = _PY_ROOT.parent.parent  # .claude/python/ → .claude/ → repo
_PYPROJECT = _PY_ROOT / "pyproject.toml"
_LOADER_YML = _REPO / ".claude" / "loader.yml"


def _read_pyproject_version() -> str:
    """Extract [project] version = "..." from pyproject.toml."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    # Match within the [project] section only
    proj_re = re.compile(
        r"\[project\][^\[]+?^version\s*=\s*\"([^\"]+)\"",
        re.MULTILINE | re.DOTALL,
    )
    m = proj_re.search(text)
    if m is None:
        raise AssertionError(f"Could not locate [project] version in {_PYPROJECT}")
    return m.group(1)


def _read_loader_yml_version() -> str:
    """Extract `version: "..."` (or unquoted) from loader.yml top-level."""
    text = _LOADER_YML.read_text(encoding="utf-8-sig")  # strip BOM
    m = re.search(r"^version:\s*\"?([^\"\n]+?)\"?\s*$", text, re.MULTILINE)
    if m is None:
        raise AssertionError(f"Could not locate version in {_LOADER_YML}")
    return m.group(1).strip()


def _pep440_to_human(pep: str) -> str:
    """Map PEP 440 form to the human-readable framework form.

    Examples :
      7.0.0a0   → 7.0.0-alpha
      7.0.0a1   → 7.0.0-alpha   (the framework drops the alpha iteration —
                                  collapses all alphas under one banner)
      7.0.0b1   → 7.0.0-beta.1
      7.0.0rc2  → 7.0.0-rc.2
      7.1.0     → 7.1.0
    """
    m = re.match(r"^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$", pep)
    if m is None:
        return pep  # unknown form, return as-is
    base, kind, num = m.group(1), m.group(2), m.group(3)
    if kind is None:
        return base
    if kind == "a":
        return f"{base}-alpha"  # framework collapses all alphas under -alpha
    if kind == "b":
        return f"{base}-beta.{num}"
    if kind == "rc":
        return f"{base}-rc.{num}"
    return pep


class TestVersionAlignment(unittest.TestCase):
    def test_sdd_lib_exports_both_versions(self):
        self.assertTrue(hasattr(sdd_lib, "__version__"),
                        "sdd_lib must export __version__")
        self.assertTrue(hasattr(sdd_lib, "__framework_version__"),
                        "sdd_lib must export __framework_version__")
        self.assertIsInstance(sdd_lib.__version__, str)
        self.assertIsInstance(sdd_lib.__framework_version__, str)

    def test_pyproject_matches_sdd_lib_version(self):
        pyproject_v = _read_pyproject_version()
        self.assertEqual(
            pyproject_v, sdd_lib.__version__,
            f"pyproject.toml [project] version='{pyproject_v}' does not match "
            f"sdd_lib.__version__='{sdd_lib.__version__}' — bump both together",
        )

    def test_loader_yml_matches_framework_version(self):
        loader_v = _read_loader_yml_version()
        self.assertEqual(
            loader_v, sdd_lib.__framework_version__,
            f"loader.yml version='{loader_v}' does not match "
            f"sdd_lib.__framework_version__='{sdd_lib.__framework_version__}' "
            f"— bump both together",
        )

    def test_pep440_to_framework_mapping_consistent(self):
        """The two version surfaces must encode the same release."""
        mapped = _pep440_to_human(sdd_lib.__version__)
        self.assertEqual(
            mapped, sdd_lib.__framework_version__,
            f"PEP 440 form '{sdd_lib.__version__}' maps to '{mapped}' but "
            f"__framework_version__='{sdd_lib.__framework_version__}'. "
            f"Adjust the alphabet mapping or the suffix.",
        )

    def test_version_starts_with_major_7(self):
        """Sanity : we're on v7.x ; if this fails, someone bumped major
        without updating the test (and probably the marketing surface too)."""
        self.assertTrue(
            sdd_lib.__version__.startswith("7."),
            f"Major version is no longer 7 (got '{sdd_lib.__version__}'). "
            f"Update this test + CLAUDE.md §1 + docs/VERSIONING.md.",
        )


if __name__ == "__main__":
    unittest.main()
