"""Tests unitaires du résolveur pur .sdd/python/sdd_lib/model_resolver.py.

Exécution : python -m pytest .sdd/python/tests/test_model_resolver.py -q
Autonome : sys.path bootstrap local, aucune dépendance à .claude/python.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_lib.model_resolver import (  # noqa: E402
    Resolution,
    clamp_tier,
    level_to_tier,
    resolve_model,
)

ANTHROPIC_TIER_MAP = {
    "deep": "claude-opus-4-8",
    "balanced": "claude-sonnet-4-6",
    "fast": "claude-haiku-4-5",
}
DEV_BACKEND = {"tier_default": "deep", "tier_floor": "balanced", "tier_ceiling": "deep"}
SPECBOOK = {"tier_default": "balanced", "tier_floor": "fast", "tier_ceiling": "balanced"}


# --- clamp_tier ---

class TestClampTier:
    def test_respecte_floor(self):
        assert clamp_tier("fast", "balanced", "deep") == "balanced"

    def test_respecte_ceiling(self):
        assert clamp_tier("deep", "fast", "balanced") == "balanced"

    def test_identite_dans_les_bornes(self):
        assert clamp_tier("balanced", "fast", "deep") == "balanced"
        assert clamp_tier("deep", "balanced", "deep") == "deep"

    def test_bornes_incoherentes(self):
        with pytest.raises(ValueError, match="incohérentes"):
            clamp_tier("balanced", "deep", "fast")

    def test_tier_inconnu(self):
        with pytest.raises(ValueError, match="invalide"):
            clamp_tier("turbo", "fast", "deep")


# --- level_to_tier ---

class TestLevelToTier:
    @pytest.mark.parametrize(
        "level,tier", [("low", "fast"), ("medium", "balanced"), ("high", "deep")]
    )
    def test_mapping(self, level, tier):
        assert level_to_tier(level) == tier

    def test_level_inconnu(self):
        with pytest.raises(ValueError, match="niveau de complexité invalide"):
            level_to_tier("critical")


# --- resolve_model : mode static ---

class TestResolveStatic:
    def test_static_utilise_tier_default(self):
        res = resolve_model(DEV_BACKEND, None, ANTHROPIC_TIER_MAP, mode="static")
        assert res == Resolution("deep", "deep", "claude-opus-4-8")

    def test_static_ignore_le_level(self):
        # Même avec level=low, static reste sur tier_default.
        res = resolve_model(DEV_BACKEND, "low", ANTHROPIC_TIER_MAP, mode="static")
        assert res.tier_final == "deep"
        assert res.model == "claude-opus-4-8"

    def test_mode_defaut_est_static(self):
        res = resolve_model(DEV_BACKEND, "low", ANTHROPIC_TIER_MAP)
        assert res.tier_final == "deep"


# --- resolve_model : mode dynamic ---

class TestResolveDynamic:
    def test_low_mappe_balanced_via_clamp_floor(self):
        # low -> candidat fast, clampé au floor balanced (dev-backend).
        res = resolve_model(DEV_BACKEND, "low", ANTHROPIC_TIER_MAP, mode="dynamic")
        assert res == Resolution("fast", "balanced", "claude-sonnet-4-6")

    def test_high_mappe_deep_borne_par_ceiling(self):
        res = resolve_model(DEV_BACKEND, "high", ANTHROPIC_TIER_MAP, mode="dynamic")
        assert res.tier_final == "deep"
        assert res.model == "claude-opus-4-8"

    def test_high_plafonne_par_ceiling_balanced(self):
        # specbook-writer : high -> candidat deep, plafonné balanced.
        res = resolve_model(SPECBOOK, "high", ANTHROPIC_TIER_MAP, mode="dynamic")
        assert res == Resolution("deep", "balanced", "claude-sonnet-4-6")

    def test_low_descend_a_fast_si_floor_fast(self):
        res = resolve_model(SPECBOOK, "low", ANTHROPIC_TIER_MAP, mode="dynamic")
        assert res.tier_final == "fast"
        assert res.model == "claude-haiku-4-5"

    def test_dynamic_sans_level_erreur(self):
        with pytest.raises(ValueError, match="exige un niveau"):
            resolve_model(DEV_BACKEND, None, ANTHROPIC_TIER_MAP, mode="dynamic")


# --- erreurs provider / entrées ---

class TestErreurs:
    def test_provider_absent_erreur_claire(self):
        with pytest.raises(ValueError, match="provider_tier_map absent"):
            resolve_model(DEV_BACKEND, "high", None, mode="dynamic")

    def test_provider_vide_erreur_claire(self):
        with pytest.raises(ValueError, match="provider_tier_map absent"):
            resolve_model(DEV_BACKEND, None, {}, mode="static")

    def test_tier_manquant_dans_tier_map(self):
        with pytest.raises(ValueError, match="sans entrée pour le tier 'fast'"):
            resolve_model(SPECBOOK, "low", {"deep": "x", "balanced": "y"}, mode="dynamic")

    def test_mode_inconnu(self):
        with pytest.raises(ValueError, match="mode invalide"):
            resolve_model(DEV_BACKEND, "low", ANTHROPIC_TIER_MAP, mode="auto")

    def test_bounds_incomplets(self):
        with pytest.raises(ValueError, match="tier_ceiling.*manquante"):
            resolve_model(
                {"tier_default": "deep", "tier_floor": "balanced"},
                None,
                ANTHROPIC_TIER_MAP,
            )
