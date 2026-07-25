"""config_loader — chargement des YAML du foyer `.sdd/` avec erreurs claires.

Phase 1 (additif) : helpers purs au-dessus de ``paths.py`` + ``yaml.safe_load``.
Deux surfaces :
- ``load_agent_bounds()`` -> dict {agent: {tier_default, tier_floor, tier_ceiling}}
- ``load_provider(name)`` -> dict du descripteur providers/{name}.yaml

Toute absence de fichier/clé lève ``ConfigError`` avec le chemin exact et la
clé manquante — jamais de fallback silencieux (anti-derive).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .paths import agent_bounds_path, providers_dir

__all__ = [
    "ConfigError",
    "load_yaml",
    "load_agent_bounds",
    "get_agent_bounds",
    "load_provider",
    "get_provider_tier_map",
]

_BOUND_KEYS = ("tier_default", "tier_floor", "tier_ceiling")


class ConfigError(ValueError):
    """Erreur de configuration `.sdd/` (fichier absent, YAML invalide, clé manquante)."""


def load_yaml(path: Path) -> dict[str, Any]:
    """Charge un YAML en dict, avec erreurs contextualisées.

    Raises:
        ConfigError: fichier absent, YAML non parseable, ou racine non-mapping.
    """
    if not path.is_file():
        raise ConfigError(f"fichier de configuration introuvable: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML invalide dans {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"racine YAML inattendue dans {path}: mapping requis, "
            f"obtenu {type(data).__name__}"
        )
    return data


def load_agent_bounds(
    env: dict[str, str] | None = None, base: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Charge ``agent-bounds.yaml`` et retourne la table ``agents``.

    Raises:
        ConfigError: fichier absent, clé ``agents`` absente, ou entrée agent
            sans l'une des clés tier_default/tier_floor/tier_ceiling.
    """
    path = agent_bounds_path(env=env, base=base)
    data = load_yaml(path)
    agents = data.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ConfigError(f"clé 'agents' absente ou vide dans {path}")
    for name, bounds in agents.items():
        if not isinstance(bounds, dict):
            raise ConfigError(f"entrée agent {name!r} invalide dans {path} (mapping requis)")
        missing = [k for k in _BOUND_KEYS if k not in bounds]
        if missing:
            raise ConfigError(
                f"entrée agent {name!r} incomplète dans {path}: "
                f"clé(s) manquante(s) {missing}"
            )
    return agents


def get_agent_bounds(
    agent: str, env: dict[str, str] | None = None, base: Path | None = None
) -> dict[str, Any]:
    """Bornes d'UN agent, erreur claire si l'agent n'est pas déclaré."""
    agents = load_agent_bounds(env=env, base=base)
    try:
        return agents[agent]
    except KeyError:
        raise ConfigError(
            f"agent {agent!r} absent de agent-bounds.yaml "
            f"(agents déclarés: {sorted(agents)})"
        ) from None


def load_provider(
    name: str, env: dict[str, str] | None = None, base: Path | None = None
) -> dict[str, Any]:
    """Charge ``providers/{name}.yaml``.

    Raises:
        ConfigError: fichier absent ou clé ``tier_map`` absente/vide.
    """
    path = providers_dir(env=env, base=base) / f"{name}.yaml"
    data = load_yaml(path)
    tier_map = data.get("tier_map")
    if not isinstance(tier_map, dict) or not tier_map:
        raise ConfigError(f"clé 'tier_map' absente ou vide dans {path}")
    return data


def get_provider_tier_map(
    name: str, env: dict[str, str] | None = None, base: Path | None = None
) -> dict[str, str]:
    """Raccourci : la ``tier_map`` (tier -> ID modèle) du provider ``name``."""
    return load_provider(name, env=env, base=base)["tier_map"]
