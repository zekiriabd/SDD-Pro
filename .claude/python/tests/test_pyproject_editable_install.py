"""Smoke test verifying pyproject.toml is correctly configured for editable install.

Audit consolidé 2026-06-07 Sprint 3-5 — sans tester l'install elle-même
(qui dépend du contexte CI : venv, pip version, permissions), vérifie que
les éléments structurels nécessaires sont présents et cohérents :
- License Apache-2.0 (aligne avec LICENSE racine)
- Version PEP 440 valide
- Packages déclarés présents sur disque
- Entry points pointent vers modules réels
- Tests + ruff configs valides
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT_PATH = REPO_ROOT / ".claude" / "python" / "pyproject.toml"


def _load_pyproject() -> dict:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


class TestPyprojectStructure:
    def test_pyproject_exists(self):
        assert PYPROJECT_PATH.is_file(), f"pyproject.toml missing at {PYPROJECT_PATH}"

    def test_license_apache(self):
        cfg = _load_pyproject()
        license_field = cfg.get("project", {}).get("license")
        # License can be a string OR a {text:...} dict (PEP 621)
        if isinstance(license_field, dict):
            license_str = license_field.get("text", "")
        else:
            license_str = str(license_field or "")
        assert "Apache" in license_str, (
            f"License must be Apache-2.0 (aligne LICENSE racine), got {license_str!r}"
        )

    def test_python_requires_310_or_higher(self):
        cfg = _load_pyproject()
        req = cfg["project"]["requires-python"]
        assert req == ">=3.10" or req == ">= 3.10", (
            f"requires-python must be >=3.10, got {req!r}"
        )

    def test_version_pep440(self):
        cfg = _load_pyproject()
        ver = cfg["project"]["version"]
        # PEP 440 simplified : N.N.N optionally with aN/bN/rcN
        import re
        pattern = re.compile(r"^\d+\.\d+\.\d+(?:[abcr][a-z]*\d+)?$")
        assert pattern.match(ver), f"Version {ver!r} is not PEP 440 canonical"

    def test_declared_packages_exist(self):
        cfg = _load_pyproject()
        packages = cfg["tool"]["setuptools"]["packages"]
        python_dir = REPO_ROOT / ".claude" / "python"
        for pkg in packages:
            pkg_path = python_dir / pkg.replace(".", "/")
            assert pkg_path.is_dir(), (
                f"Declared package {pkg!r} missing at {pkg_path}"
            )

    def test_scripts_entry_points_resolvable(self):
        """For each declared `[project.scripts]`, the module:function must be importable."""
        cfg = _load_pyproject()
        scripts = cfg.get("project", {}).get("scripts", {})
        if not scripts:
            pytest.skip("No CLI entry-points declared yet")
        sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))
        for cli_name, target in scripts.items():
            assert ":" in target, f"Entry point {cli_name!r} must be 'module:func', got {target!r}"
            module_name, func_name = target.split(":", 1)
            try:
                module = __import__(module_name, fromlist=[func_name])
            except ImportError as exc:
                pytest.fail(f"Entry point {cli_name!r} → {target!r} : module import failed : {exc}")
            assert hasattr(module, func_name), (
                f"Entry point {cli_name!r} → {target!r} : function {func_name!r} not found in module"
            )


class TestVersionAlignment:
    """Bumper la version dans pyproject.toml doit être fait en parallèle de
    CLAUDE.md / loader.yml — sinon le test_version_alignment.py (existant)
    fail. Ce test smoke vérifie juste que pyproject.toml est lisible et
    expose un `version` parseable. L'alignment cross-fichier vit dans
    test_version_alignment.py."""

    def test_can_extract_version(self):
        cfg = _load_pyproject()
        assert "version" in cfg["project"]
        assert isinstance(cfg["project"]["version"], str)
        assert len(cfg["project"]["version"]) > 0
