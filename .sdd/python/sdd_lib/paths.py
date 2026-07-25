"""paths — résolution des chemins du foyer neutre `.sdd/` (SDD_HOME-aware).

VERSION NEUVE Phase 1 (plan MIGRATION-PLAN-multi-harness-multi-provider §5) :
indépendante du `paths.py` historique de `.claude/python/sdd_lib/` — AUCUN
import croisé, aucune I/O implicite, fonctions pures et testables.

Contrat (ADR harness-and-provider-abstraction, D2) :
- la racine du moteur est donnée par l'env var ``SDD_HOME`` ;
- à défaut, le répertoire ``.sdd`` relatif au cwd (ou à ``base`` fourni).

Aucune fonction ne vérifie l'existence sur disque (résolution pure) — les
loaders (config_loader.py) portent les erreurs "fichier absent".
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "SDD_HOME_ENV",
    "sdd_home",
    "resolve",
    "providers_dir",
    "agents_dir",
    "agent_bounds_path",
    "capability_matrix_path",
]

SDD_HOME_ENV = "SDD_HOME"
_DEFAULT_DIRNAME = ".sdd"


def sdd_home(env: dict[str, str] | None = None, base: Path | None = None) -> Path:
    """Racine du foyer neutre.

    Args:
        env: mapping d'environnement (défaut ``os.environ``) — injectable
            pour les tests, zéro monkeypatch requis.
        base: base de résolution du défaut ``.sdd`` (défaut ``Path.cwd()``).
            Ignorée si ``SDD_HOME`` est défini et non vide.

    Returns:
        Path absolu de la racine ``.sdd`` (ou de ``SDD_HOME``).
    """
    environ = os.environ if env is None else env
    raw = environ.get(SDD_HOME_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    root = Path.cwd() if base is None else Path(base)
    return (root / _DEFAULT_DIRNAME).resolve()


def resolve(*parts: str, env: dict[str, str] | None = None, base: Path | None = None) -> Path:
    """Chemin sous la racine SDD_HOME : ``resolve("providers", "moonshot.yaml")``."""
    return sdd_home(env=env, base=base).joinpath(*parts)


def providers_dir(env: dict[str, str] | None = None, base: Path | None = None) -> Path:
    """Répertoire des descripteurs provider (``providers/*.yaml``)."""
    return resolve("providers", env=env, base=base)


def agents_dir(env: dict[str, str] | None = None, base: Path | None = None) -> Path:
    """Répertoire des pivots agents (``agents/*.agent.yaml``)."""
    return resolve("agents", env=env, base=base)


def agent_bounds_path(env: dict[str, str] | None = None, base: Path | None = None) -> Path:
    """Fichier des bornes de tier par agent (``agent-bounds.yaml``)."""
    return resolve("agent-bounds.yaml", env=env, base=base)


def capability_matrix_path(env: dict[str, str] | None = None, base: Path | None = None) -> Path:
    """Matrice harnais × mécanismes (``capability-matrix.yml``, SSoT du rapport d'impact)."""
    return resolve("capability-matrix.yml", env=env, base=base)
