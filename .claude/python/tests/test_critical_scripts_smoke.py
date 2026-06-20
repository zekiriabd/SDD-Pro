"""Smoke tests for 6 critical scripts previously without any test coverage.

Audit consolidé 2026-06-07 Sprint 2 — Sprint 2 last action P1. Per audit R2:M9,
22 scripts were sans test direct. This module adds *minimal smoke coverage*
(import + --help exit 0) for the 5 most critical, plus the new
validate_libs_versions_in_md.py from this sprint.

Pourquoi smoke uniquement : ces 6 scripts représentent ~2 800 LOC totales.
Une couverture intégration profonde dépasse le scope Sprint 2 (3-4 jours
seuls). Le smoke test attrape les régressions catastrophiques (import
broken par refactor, argparse cassé, sys.path régression) sans paier le
coût d'une suite intégration complète — qui viendra en v7.1.

Covered :
  - sdd_admin/framework_smoke.py     — le smoke runner du framework (763 LOC)
  - sdd_admin/statusline.py          — Claude Code statusline (405 LOC)
  - sdd_admin/validate_templates.py  — validateur templates
  - sdd_admin/validate_libs_catalog.py  — validateur .libs.json
  - sdd_admin/validate_libs_versions_in_md.py — cross-check .md ↔ .libs.json (NEW Sprint 2)
  - sdd_scripts/query_console_db.py  — API humaine lecture console.db (377 LOC)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / ".claude" / "python"


def _run_script_help(script_relpath: str) -> subprocess.CompletedProcess:
    """Run `python {script} --help` and return CompletedProcess.

    Exit 0 expected. Captures stdout+stderr to verify argparse output.
    """
    script_path = REPO_ROOT / ".claude" / "python" / script_relpath
    assert script_path.is_file(), f"script not found: {script_path}"
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    import os
    env.update(os.environ)
    # Pass --help. Use a short timeout — --help should be instant.
    return subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True, text=True, timeout=15,
        cwd=str(REPO_ROOT), env=env, encoding="utf-8", errors="replace",
    )


def _can_import_module(module_path: str) -> tuple[bool, str]:
    """Try `import module_path` in a subprocess. Returns (ok, stderr)."""
    code = f"import sys; sys.path.insert(0, r'{PYTHON_DIR}'); import {module_path}"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=10,
        cwd=str(REPO_ROOT), encoding="utf-8", errors="replace",
    )
    return (proc.returncode == 0, proc.stderr)


@pytest.mark.smoke
class TestCriticalScriptsImport:
    """Each of the 6 scripts must import without exception."""

    def test_framework_smoke_imports(self):
        ok, err = _can_import_module("sdd_admin.framework_smoke")
        assert ok, f"framework_smoke import failed:\n{err}"

    def test_statusline_imports(self):
        ok, err = _can_import_module("sdd_admin.statusline")
        assert ok, f"statusline import failed:\n{err}"

    def test_validate_templates_imports(self):
        ok, err = _can_import_module("sdd_admin.validate_templates")
        assert ok, f"validate_templates import failed:\n{err}"

    def test_validate_libs_catalog_imports(self):
        ok, err = _can_import_module("sdd_admin.validate_libs_catalog")
        assert ok, f"validate_libs_catalog import failed:\n{err}"

    def test_validate_libs_versions_in_md_imports(self):
        ok, err = _can_import_module("sdd_admin.validate_libs_versions_in_md")
        assert ok, f"validate_libs_versions_in_md import failed:\n{err}"

    def test_query_console_db_imports(self):
        ok, err = _can_import_module("sdd_scripts.query_console_db")
        assert ok, f"query_console_db import failed:\n{err}"


@pytest.mark.smoke
class TestCriticalScriptsHelp:
    """Each script's --help must exit 0 and print usage to stdout."""

    def test_validate_templates_help(self):
        result = _run_script_help("sdd_admin/validate_templates.py")
        assert result.returncode == 0, f"--help exit {result.returncode}:\n{result.stderr}"
        assert "usage:" in result.stdout.lower()

    def test_validate_libs_catalog_help(self):
        result = _run_script_help("sdd_admin/validate_libs_catalog.py")
        assert result.returncode == 0, f"--help exit {result.returncode}:\n{result.stderr}"
        assert "usage:" in result.stdout.lower()

    def test_validate_libs_versions_in_md_help(self):
        result = _run_script_help("sdd_admin/validate_libs_versions_in_md.py")
        assert result.returncode == 0, f"--help exit {result.returncode}:\n{result.stderr}"
        assert "usage:" in result.stdout.lower()
        # New script — verify it advertises the cross-check intent
        assert "libs" in result.stdout.lower()

    def test_query_console_db_help(self):
        result = _run_script_help("sdd_scripts/query_console_db.py")
        assert result.returncode == 0, f"--help exit {result.returncode}:\n{result.stderr}"
        assert "usage:" in result.stdout.lower()


@pytest.mark.smoke
class TestValidateLibsVersionsInMd:
    """Functional smoke for the new Sprint 2 cross-check validator.

    Verifies _versions_compatible() handles the documented cases without
    needing real .md/.libs.json files (those are tested by running the
    full script in framework_smoke).
    """

    def test_versions_compatible_exact_match(self):
        sys.path.insert(0, str(PYTHON_DIR))
        from sdd_admin.validate_libs_versions_in_md import _versions_compatible
        assert _versions_compatible("2.0.21", "2.0.21")

    def test_versions_compatible_wildcard_dotx(self):
        sys.path.insert(0, str(PYTHON_DIR))
        from sdd_admin.validate_libs_versions_in_md import _versions_compatible
        assert _versions_compatible("4.0.x", "4.0.5")
        assert _versions_compatible("3.3.x", "3.3.0")

    def test_versions_compatible_prefix_match(self):
        sys.path.insert(0, str(PYTHON_DIR))
        from sdd_admin.validate_libs_versions_in_md import _versions_compatible
        assert _versions_compatible("3.3", "3.3.5")

    def test_versions_compatible_lower_bound_plus(self):
        sys.path.insert(0, str(PYTHON_DIR))
        from sdd_admin.validate_libs_versions_in_md import _versions_compatible
        # 4.0+ accepts 4.0.x same minor base
        assert _versions_compatible("4.0+", "4.0.5")
        assert _versions_compatible("4.0+", "4.0.0")

    def test_versions_incompatible_different_major(self):
        sys.path.insert(0, str(PYTHON_DIR))
        from sdd_admin.validate_libs_versions_in_md import _versions_compatible
        # The famous CRIT-2 case: doc Spring Boot 4.0.x vs libs 3.3.5 — INCOMPAT
        assert not _versions_compatible("4.0.x", "3.3.5")
        # CRIT-3 case: doc Radzen 10.2.3 vs libs 5.5.7
        assert not _versions_compatible("10.2.3", "5.5.7")
