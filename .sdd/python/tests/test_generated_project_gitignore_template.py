"""Checks for the generated-project .gitignore template."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))
from sdd_lib.paths import templates_dir  # noqa: E402

# Bi-racine 2026-07-25 : templates migrées vers .sdd/templates/.
TEMPLATE = templates_dir(REPO_ROOT) / "generated-project.gitignore.template"


def test_generated_project_gitignore_template_exists():
    assert TEMPLATE.is_file()


def test_generated_project_gitignore_template_covers_sdd_secret_configs():
    text = TEMPLATE.read_text(encoding="utf-8")
    required = [
        "appsettings.json",
        "src/main/resources/application.yml",
        "config/default.json",
        "lib/server/config.ts",
        "server/config/app-config.ts",
        "app/config.py",
        ".env",
    ]
    missing = [pattern for pattern in required if pattern not in text]
    assert not missing


def test_repo_root_gitignore_covers_sdd_runtime_artifacts():
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    required = [
        "workspace/",
        "workspace/db/",
        "workspace/console/",
        "workspace/stack/",
        "workspace/src/*/.env",
        "workspace/src/*/appsettings*.json",
        "workspace/src/*/config/default.json",
    ]
    missing = [pattern for pattern in required if pattern not in text]
    assert not missing
