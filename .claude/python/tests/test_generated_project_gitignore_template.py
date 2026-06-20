"""Checks for the generated-project .gitignore template."""
from __future__ import annotations

from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "generated-project.gitignore.template"
)


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
