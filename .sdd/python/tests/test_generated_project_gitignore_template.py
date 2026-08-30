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
    """Le CONTENU runtime de workspace/ reste ignoré (garde anti-fuite)."""
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    required = [
        "workspace/**",
        "workspace/db/**",
        "workspace/console/**",
        "workspace/src/*/.env",
        "workspace/src/*/appsettings*.json",
        "workspace/src/*/config/default.json",
    ]
    missing = [pattern for pattern in required if pattern not in text]
    assert not missing


def test_repo_root_gitignore_keeps_workspace_skeleton_versioned():
    """Squelette workspace/ committé vide (2026-08-30).

    Les 3 ré-inclusions sont load-bearing ET ordonnées : sans `!workspace/**/`
    git ne descend pas dans les répertoires exclus et les `.gitkeep` ne peuvent
    plus être ré-inclus. Elles doivent rester APRÈS les règles d'exclusion.
    """
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    negations = ["!workspace/**/", "!workspace/**/.gitkeep", "!workspace/stack/**"]
    missing = [pattern for pattern in negations if pattern not in text]
    assert not missing, f"ré-inclusions workspace absentes: {missing}"
    lines = text.splitlines()
    assert lines.index("workspace/**") < min(lines.index(n) for n in negations)


def test_workspace_skeleton_dirs_have_gitkeep():
    """bootstrap.py crée l'arborescence : elle doit être versionnée vide."""
    expected = [
        ".sys/.audit", ".sys/.cache", ".sys/.context/adrs", ".sys/.routing",
        ".sys/.state", ".sys/.validation", "assets", "console", "db",
        "discovery", "feats", "old", "plans", "qa", "src", "ui", "us",
    ]
    workspace = REPO_ROOT / "workspace"
    missing = [d for d in expected if not (workspace / d / ".gitkeep").is_file()]
    assert not missing, f".gitkeep manquants: {missing}"
