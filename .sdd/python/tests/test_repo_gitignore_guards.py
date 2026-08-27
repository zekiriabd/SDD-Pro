"""Guard : les protections `.gitignore` du repo framework sont ACTIVES.

Pourquoi ce fichier existe
--------------------------
`test_generated_project_gitignore_template.py::test_repo_root_gitignore_covers_sdd_runtime_artifacts`
vérifiait déjà la présence des règles `workspace/**` — mais par simple
`pattern in text`. Un `#` en tête de ligne conserve la sous-chaîne : la
règle devient inerte alors que le test reste vert. C'est exactement ce qui
s'est produit (les 7 règles `workspace/` ont été commentées, et
`workspace/stack/{.env,stack.md}` — porteurs de `DB_PASSWORD`,
`SMTP_PASSWORD`, `AZ_CLIENTID` par contrat CLAUDE.md §9 — sont devenus
suivis par git).

Ce module ferme les deux trous :
  1. les règles doivent être ACTIVES (parsing ligne à ligne, commentaires exclus) ;
  2. `git` lui-même doit confirmer qu'aucun chemin porteur de secret ni
     aucune façade générée n'est suivi (source de vérité > texte du fichier).

Le contrôle (2) double le job CI `facade-write-guard`
(`.github/workflows/harness-parity.yml`) côté pytest, pour que la
régression soit visible en local avant le push.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GITIGNORE = REPO_ROOT / ".gitignore"

# Règles de confinement du workspace runtime. `workspace/**` (et non
# `workspace/`) est requis : une exclusion de RÉPERTOIRE interdit toute
# ré-inclusion ultérieure d'un fichier qu'il contient (cf. gitignore(5),
# « It is not possible to re-include a file if a parent directory of that
# file is excluded »), ce qui rendrait impossible le squelette `.gitkeep`.
REQUIRED_WORKSPACE_RULES = (
    "workspace/**",
    "workspace/db/",
    "workspace/console/",
    "workspace/stack/",
    "workspace/src/*/.env",
    "workspace/src/*/appsettings*.json",
    "workspace/src/*/config/default.json",
)

# Façades générées par harness_build.py — jamais commitées (INVARIANTS.yml
# invariant #14 « harness-parity », job CI `facade-write-guard`).
REQUIRED_FACADE_RULES = (
    ".claude/agents/",
    ".claude/commands/",
    ".claude/rules/",
    ".claude/CLAUDE.md",
)

# Chemins qui ne doivent JAMAIS apparaître dans l'index git.
FORBIDDEN_TRACKED_PATHS = (
    "workspace/stack/stack.md",   # DB_PASSWORD / SMTP_PASSWORD / AZ_CLIENTID
    "workspace/stack/.env",       # idem, format dotenv
    ".claude/CLAUDE.md",          # façade générée
    ".claude/agents",
    ".claude/commands",
    ".claude/rules",
)


def _active_rules() -> set[str]:
    """Règles réellement appliquées : hors commentaires et lignes vides."""
    lines = GITIGNORE.read_text(encoding="utf-8-sig").splitlines()
    return {
        stripped
        for raw in lines
        if (stripped := raw.strip()) and not stripped.startswith("#")
    }


@pytest.mark.smoke
@pytest.mark.parametrize("rule", REQUIRED_WORKSPACE_RULES)
def test_workspace_rule_is_active(rule: str) -> None:
    """Chaque règle `workspace/` est présente ET non commentée."""
    active = _active_rules()
    assert rule in active, (
        f"[GITIGNORE_RULE_INACTIVE] `{rule}` absente ou commentee dans .gitignore. "
        "Le workspace runtime porte des secrets en clair (CLAUDE.md §9) : "
        "commenter cette regle les expose au prochain `git add -A`."
    )


@pytest.mark.smoke
@pytest.mark.parametrize("rule", REQUIRED_FACADE_RULES)
def test_facade_rule_is_active(rule: str) -> None:
    """Chaque règle de façade générée est présente ET non commentée."""
    active = _active_rules()
    assert rule in active, (
        f"[GITIGNORE_RULE_INACTIVE] `{rule}` absente ou commentee dans .gitignore. "
        "Les facades sont regenerees par harness_build.py (invariant #14) ; "
        "les committer casse le job CI `facade-write-guard`."
    )


@pytest.mark.smoke
def test_no_secret_bearing_or_generated_path_is_tracked() -> None:
    """`git ls-files` ne doit renvoyer aucun de ces chemins.

    Contrôle de dernier recours : `.gitignore` n'a aucun effet sur un
    fichier DÉJÀ suivi. Seul l'index fait foi.
    """
    if shutil.which("git") is None:  # pragma: no cover - env sans git
        pytest.skip("git not available")
    res = subprocess.run(
        ["git", "ls-files", "--", *FORBIDDEN_TRACKED_PATHS],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:  # pragma: no cover - hors dépôt git (tarball)
        pytest.skip(f"not a git work tree: {res.stderr.strip()}")
    tracked = [line for line in res.stdout.splitlines() if line.strip()]
    assert not tracked, (
        "[TRACKED_FORBIDDEN_PATH] chemins suivis par git alors qu'ils sont "
        f"gitignores : {tracked}. FIX : `git rm --cached <path>` "
        "(un .gitignore n'a aucun effet retroactif sur un fichier deja suivi)."
    )
