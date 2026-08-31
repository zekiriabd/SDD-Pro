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


def _repo_gitignore_rules() -> list[str]:
    """Règles ACTIVES du .gitignore racine (commentaires et blancs retirés).

    Load-bearing : une assertion `pattern in text` reste vraie quand la règle
    porte un `#` devant. C'est par ce trou que `b97e86c` a neutralisé les 7
    règles `workspace/` en gardant la CI verte — les secrets sont devenus
    committables sans qu'aucun test ne rougisse. On ne compare donc que des
    lignes de règle réelles, jamais des sous-chaînes.

    Pendant côté index (un .gitignore n'est pas rétroactif) :
    `test_repo_gitignore_index_guard.py`.
    """
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8-sig")
    return [
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]


def test_repo_root_gitignore_covers_sdd_runtime_artifacts():
    """Le CONTENU runtime de workspace/ reste ignoré (garde anti-fuite)."""
    rules = _repo_gitignore_rules()
    required = [
        "workspace/**",
        "workspace/db/**",
        "workspace/console/**",
        "workspace/src/*/.env",
        "workspace/src/*/appsettings*.json",
        "workspace/src/*/config/default.json",
    ]
    missing = [pattern for pattern in required if pattern not in rules]
    assert not missing, f"règles d'ignore workspace absentes (ou commentées): {missing}"


def test_repo_root_gitignore_keeps_workspace_skeleton_versioned():
    """Squelette workspace/ committé vide (2026-08-30).

    Les 3 ré-inclusions sont load-bearing ET ordonnées : sans `!workspace/**/`
    git ne descend pas dans les répertoires exclus et les `.gitkeep` ne peuvent
    plus être ré-inclus. Elles doivent rester APRÈS les règles d'exclusion.

    La 3e porte sur le FICHIER `stack.md`, jamais sur le répertoire (audit
    2026-08-31) : `!workspace/stack/**` ré-incluait tout `workspace/stack/`,
    donc un `.env` déposé là repartait sur origin au premier `git add -A`.
    """
    rules = _repo_gitignore_rules()
    negations = [
        "!workspace/**/",
        "!workspace/**/.gitkeep",
        "!workspace/stack/stack.md",
    ]
    missing = [pattern for pattern in negations if pattern not in rules]
    assert not missing, f"ré-inclusions workspace absentes (ou commentées): {missing}"
    assert "!workspace/stack/**" not in rules, (
        "négation trop large : `!workspace/stack/**` ré-inclut le RÉPERTOIRE "
        "entier — utiliser `!workspace/stack/stack.md`."
    )
    assert rules.index("workspace/**") < min(rules.index(n) for n in negations)


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
