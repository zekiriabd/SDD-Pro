"""model_resolver — résolution pure (agent, complexité, provider) -> modèle.

Implémente le flux §8.bis.5 du plan MIGRATION-PLAN-multi-harness-multi-provider :

    niveau (low|medium|high) --level_to_tier--> tier candidat (fast|balanced|deep)
    tier --clamp_tier--> max(tier_floor, min(candidat, tier_ceiling))
    tier --provider_tier_map--> ID modèle concret

Propriétés load-bearing : 0 token (Python pur), déterministe (même entrée ->
même sortie), testable en isolation (aucun import de sdd_lib.paths ni d'I/O).

Statut : scaffolding Phase 0/1 — non encore câblé au pipeline.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple

# Ordre total des tiers (invariant : fast < balanced < deep).
TIERS: tuple[str, ...] = ("fast", "balanced", "deep")
_TIER_RANK: dict[str, int] = {t: i for i, t in enumerate(TIERS)}

# Niveaux de complexité émis par les scoreurs déterministes
# (complexity_router.py / code_unit_complexity.py, réutilisés tels quels).
LEVELS: tuple[str, ...] = ("low", "medium", "high")
_LEVEL_TO_TIER: dict[str, str] = {"low": "fast", "medium": "balanced", "high": "deep"}

MODES: tuple[str, ...] = ("static", "dynamic")


class Resolution(NamedTuple):
    """Résultat de résolution — persistable tel quel dans model-routing.json."""

    tier_candidate: str  # tier avant clamp (tier_default en mode static)
    tier_final: str      # tier après clamp floor/ceiling
    model: str           # ID modèle concret du provider actif


def _check_tier(value: str, label: str) -> str:
    if value not in _TIER_RANK:
        raise ValueError(f"{label} invalide: {value!r} (attendu: {'|'.join(TIERS)})")
    return value


def clamp_tier(candidate: str, floor: str, ceiling: str) -> str:
    """Borne un tier candidat dans [floor, ceiling] (ordre fast<balanced<deep).

    >>> clamp_tier("fast", "balanced", "deep")
    'balanced'
    >>> clamp_tier("deep", "fast", "balanced")
    'balanced'

    Raises:
        ValueError: tier inconnu, ou floor > ceiling (bornes incohérentes).
    """
    _check_tier(candidate, "tier candidat")
    _check_tier(floor, "tier_floor")
    _check_tier(ceiling, "tier_ceiling")
    if _TIER_RANK[floor] > _TIER_RANK[ceiling]:
        raise ValueError(
            f"bornes incohérentes: tier_floor={floor!r} > tier_ceiling={ceiling!r}"
        )
    rank = max(_TIER_RANK[floor], min(_TIER_RANK[candidate], _TIER_RANK[ceiling]))
    return TIERS[rank]


def level_to_tier(level: str) -> str:
    """Mappe un niveau de complexité vers son tier candidat (avant clamp).

    low -> fast, medium -> balanced, high -> deep.

    Raises:
        ValueError: niveau inconnu.
    """
    try:
        return _LEVEL_TO_TIER[level]
    except KeyError:
        raise ValueError(
            f"niveau de complexité invalide: {level!r} (attendu: {'|'.join(LEVELS)})"
        ) from None


def resolve_model(
    agent_bounds: Mapping[str, str],
    level: str | None,
    provider_tier_map: Mapping[str, str] | None,
    mode: str = "static",
) -> Resolution:
    """Résout le modèle concret pour un agent donné.

    Args:
        agent_bounds: bornes de l'agent (entrée de agent-bounds.yaml) —
            clés requises ``tier_default``, ``tier_floor``, ``tier_ceiling``.
        level: niveau de complexité du work-item (``low|medium|high``).
            Ignoré en mode ``static`` (peut être None) ; requis en ``dynamic``.
        provider_tier_map: mapping ``tier -> ID modèle`` du provider actif
            (section ``tier_map`` de providers/{p}.yaml).
        mode: ``static`` (tier_default fixe, défaut) ou ``dynamic``
            (level -> tier candidat, clampé floor/ceiling).

    Returns:
        Resolution(tier_candidate, tier_final, model).

    Raises:
        ValueError: mode inconnu, borne manquante/invalide, level manquant en
            dynamic, provider_tier_map absent ou sans entrée pour le tier final.
    """
    if mode not in MODES:
        raise ValueError(f"mode invalide: {mode!r} (attendu: {'|'.join(MODES)})")

    for key in ("tier_default", "tier_floor", "tier_ceiling"):
        if key not in agent_bounds:
            raise ValueError(f"agent_bounds incomplet: clé {key!r} manquante")

    floor = agent_bounds["tier_floor"]
    ceiling = agent_bounds["tier_ceiling"]

    if mode == "static":
        candidate = _check_tier(agent_bounds["tier_default"], "tier_default")
    else:  # dynamic
        if level is None:
            raise ValueError("mode 'dynamic' exige un niveau de complexité (level)")
        candidate = level_to_tier(level)

    tier_final = clamp_tier(candidate, floor, ceiling)

    if not provider_tier_map:
        raise ValueError(
            "provider_tier_map absent ou vide — provider non résolu "
            "(vérifier stack.md ## Active Model Provider et providers/*.yaml)"
        )
    model = provider_tier_map.get(tier_final)
    if not model:
        raise ValueError(
            f"provider_tier_map sans entrée pour le tier {tier_final!r} "
            f"(tiers déclarés: {sorted(provider_tier_map)})"
        )

    return Resolution(tier_candidate=candidate, tier_final=tier_final, model=model)
