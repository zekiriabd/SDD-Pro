"""Gardes d'INDEX git — anti-fuite de secrets sous `workspace/` (audit 2026-08-31).

Pourquoi interroger `git ls-files` et pas seulement le texte du `.gitignore` :

  1. **Un `.gitignore` n'a aucun effet rétroactif sur un fichier déjà tracké.**
     `workspace/stack/.env` a été committé par `b97e86c` et n'est sorti de
     l'index qu'en `34ce860` : pendant tout cet intervalle une règle d'ignore
     l'aurait laissé passer sans broncher. Seul l'index dit la vérité.
  2. **Une règle commentée reste une sous-chaîne présente dans le fichier.**
     `test_repo_root_gitignore_covers_sdd_runtime_artifacts` validait
     `"workspace/**" in text` — vrai aussi avec un `#` devant. C'est
     exactement par ce trou que `b97e86c` a pu neutraliser les 7 règles
     `workspace/` en gardant la CI verte (l'assertion est passée en
     ligne-à-ligne dans le module voisin ; ce module-ci ferme l'autre moitié
     en regardant ce qui est RÉELLEMENT versionné).

Le job CI `facade-write-guard` (`.github/workflows/harness-parity.yml`) fait le
pendant côté façades harnais. Ici on couvre les secrets, et en local — la
régression est visible avant le push, pas après.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (REPO_ROOT / ".git").exists(),
    reason="hors checkout git (sdist / tarball) — l'index n'est pas observable",
)

# Aucun fichier de contenu autorisé sous workspace/ : seuls les `.gitkeep` du
# squelette sont versionnés. stack.md a été retiré de l'index le 2026-11-14
# (décision Tech Lead — nom du projet client et chemins locaux, révoque 408c511).
ALLOWED_CONTENT: set[str] = set()

# Familles de fichiers qui portent des secrets par contrat SDD (stack.md §
# Active Database / Auth / SMTP propagé par l'agent `arch`).
SECRET_BEARING_SUFFIXES = (
    "/.env",
    "/app/config.py",
    "/config/default.json",
    "/lib/server/config.ts",
    "/server/config/app-config.ts",
)
SECRET_BEARING_GLOBS = (
    "appsettings*.json",
    "application*.yml",
    "*.pfx",
    "*.pem",
    "*.key",
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        check=True,
    ).stdout


def _tracked_under_workspace() -> list[str]:
    out = _git("ls-files", "--", "workspace")
    return [line.strip() for line in out.splitlines() if line.strip()]


def test_no_secret_bearing_file_tracked_under_workspace():
    """Aucune config applicative peuplée par `arch` ne doit être dans l'index."""
    offenders = []
    for path in _tracked_under_workspace():
        name = path.rsplit("/", 1)[-1]
        if path.endswith(SECRET_BEARING_SUFFIXES) or any(
            Path(name).match(pattern) for pattern in SECRET_BEARING_GLOBS
        ):
            offenders.append(path)
    assert not offenders, (
        "fichiers porteurs de secrets TRACKÉS sous workspace/ : "
        f"{offenders} — `git rm --cached <path>` (le fichier reste sur disque) ; "
        "un ajout au .gitignore seul ne suffit PAS, il n'est pas rétroactif."
    )


def test_only_skeleton_and_stack_md_tracked_under_workspace():
    """Squelette (`.gitkeep`) + stack.md, rien d'autre.

    Garde générique : elle attrape aussi un artefact runtime (FEAT, US, code
    généré, dump SQL, `console.db`) committé par un `git add -A` distrait, pas
    seulement les noms de fichiers connus du test précédent.
    """
    unexpected = [
        path
        for path in _tracked_under_workspace()
        if not path.endswith("/.gitkeep") and path not in ALLOWED_CONTENT
    ]
    assert not unexpected, (
        f"contenu runtime trackés sous workspace/ : {unexpected} — "
        "seuls les .gitkeep du squelette sont versionnés."
    )


def test_stack_md_is_not_tracked():
    """Décision 2026-11-14 : stack.md porte le nom du projet client et des
    chemins locaux — il reste local et ne doit jamais revenir dans l'index."""
    assert "workspace/stack/stack.md" not in _tracked_under_workspace()


def _is_ignored(path: str) -> bool:
    # `check-ignore -q` : rc 0 = ignoré, rc 1 = non ignoré. Fonctionne sur des
    # chemins INEXISTANTS (on teste la règle, pas l'état du disque) — et,
    # contrairement à `-v`, rend rc 1 quand la dernière règle qui matche est
    # une négation.
    rc = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        capture_output=True,
    ).returncode
    assert rc in (0, 1), f"git check-ignore a échoué sur {path} (rc={rc})"
    return rc == 0


@pytest.mark.parametrize(
    "path",
    [
        # Le cas qui a motivé ce module : `!workspace/stack/**` ré-incluait le
        # RÉPERTOIRE entier, donc un .env recréé repartait sur origin.
        "workspace/stack/.env",
        "workspace/stack/secrets.local.json",
        "workspace/db/console.db",
        "workspace/console/status.json",
        "workspace/src/MyApp/.env",
        "workspace/src/MyApp/appsettings.json",
        "workspace/feats/1-Auth.md",
        "workspace/.sys/.audit/tokens.jsonl",
        "workspace/stack/stack.md",
    ],
)
def test_runtime_paths_are_ignored(path: str):
    assert _is_ignored(path), f"{path} DEVRAIT être ignoré par .gitignore"


@pytest.mark.parametrize(
    "path",
    [
        "workspace/stack/.gitkeep",
        "workspace/feats/.gitkeep",
        "workspace/.sys/.audit/.gitkeep",
    ],
)
def test_skeleton_paths_are_not_ignored(path: str):
    assert not _is_ignored(path), (
        f"{path} ne doit PAS être ignoré — sans lui le squelette workspace/ "
        "disparaît du clone et bootstrap.py ne retrouve pas son arborescence."
    )
