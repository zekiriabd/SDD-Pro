"""Test d'intégration Phase 1 — bout-en-bout SANS réseau, sur les VRAIS fichiers.

Chaîne testée : paths.py (SDD_HOME) -> config_loader (agent-bounds.yaml +
providers/moonshot.yaml réels) -> model_resolver.resolve_model.

Exécution : python -m pytest .sdd/python/tests/ -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_lib import paths  # noqa: E402
from sdd_lib.config_loader import (  # noqa: E402
    ConfigError,
    get_agent_bounds,
    get_provider_tier_map,
    load_agent_bounds,
    load_provider,
)
from sdd_lib.model_resolver import resolve_model  # noqa: E402

# Racine .sdd réelle du repo (tests/ -> python/ -> .sdd/), injectée via SDD_HOME
# simulé (env dict) — aucune dépendance au cwd, zéro monkeypatch os.environ.
SDD_HOME_REAL = Path(__file__).resolve().parents[2]
ENV = {"SDD_HOME": str(SDD_HOME_REAL)}


# --- paths.py (SDD_HOME-aware, pur) ---

class TestPaths:
    def test_sdd_home_lit_env(self):
        assert paths.sdd_home(env=ENV) == SDD_HOME_REAL

    def test_sdd_home_defaut_dot_sdd_sous_base(self, tmp_path):
        assert paths.sdd_home(env={}, base=tmp_path) == (tmp_path / ".sdd").resolve()

    def test_resolve_et_helpers(self):
        assert paths.resolve("providers", "moonshot.yaml", env=ENV) == (
            SDD_HOME_REAL / "providers" / "moonshot.yaml"
        )
        assert paths.providers_dir(env=ENV) == SDD_HOME_REAL / "providers"
        assert paths.agents_dir(env=ENV) == SDD_HOME_REAL / "agents"
        assert paths.agent_bounds_path(env=ENV) == SDD_HOME_REAL / "agent-bounds.yaml"


# --- config_loader sur les VRAIS fichiers ---

class TestConfigLoader:
    def test_agent_bounds_reels_25_agents_complets(self):
        agents = load_agent_bounds(env=ENV)
        assert len(agents) == 29
        for bounds in agents.values():
            assert {"tier_default", "tier_floor", "tier_ceiling"} <= set(bounds)

    def test_moonshot_reel_tier_map_complete(self):
        provider = load_provider("moonshot", env=ENV)
        assert provider["name"] == "moonshot"
        assert set(provider["tier_map"]) == {"deep", "balanced", "fast"}

    def test_provider_inconnu_erreur_claire(self):
        with pytest.raises(ConfigError, match="introuvable"):
            load_provider("nonexistent-provider", env=ENV)

    def test_agent_inconnu_erreur_claire(self):
        with pytest.raises(ConfigError, match="absent de agent-bounds"):
            get_agent_bounds("agent-fantome", env=ENV)


# --- Intégration bout-en-bout : bounds réels + moonshot réel + resolve_model ---

class TestPhase1EndToEnd:
    @pytest.fixture(scope="class")
    def kimi(self):
        return get_provider_tier_map("moonshot", env=ENV)

    def test_dev_backend_low_jamais_sous_balanced(self, kimi):
        # dev-backend / low : candidat fast, clampé au floor balanced -> Kimi coding.
        res = resolve_model(
            get_agent_bounds("dev-backend", env=ENV), "low", kimi, mode="dynamic"
        )
        assert res.tier_candidate == "fast"
        assert res.tier_final == "balanced"
        assert res.model == "kimi-k2.7-code"
        assert res.model.startswith("kimi-")

    def test_security_reviewer_low_jamais_fast(self, kimi):
        # Garde-fou D4 : 8 classes [SEC_*] hard-blocking -> floor balanced.
        res = resolve_model(
            get_agent_bounds("security-reviewer", env=ENV), "low", kimi, mode="dynamic"
        )
        assert res.tier_final != "fast"
        assert res.tier_final == "balanced"
        assert res.model == "kimi-k2.7-code"

    def test_elicitor_high_plafonne_balanced(self, kimi):
        # Arbitrage Tech Lead 2026-07-24 : elicitor ceiling balanced (latence).
        res = resolve_model(
            get_agent_bounds("elicitor", env=ENV), "high", kimi, mode="dynamic"
        )
        assert res.tier_candidate == "deep"
        assert res.tier_final == "balanced"
        assert res.model == "kimi-k2.7-code"

    def test_constitutioner_low_descend_a_fast(self, kimi):
        # Floor fast confirmé 2026-07-24 (tâche éditoriale bornée).
        res = resolve_model(
            get_agent_bounds("constitutioner", env=ENV), "low", kimi, mode="dynamic"
        )
        assert res.tier_final == "fast"
        assert res.model == "kimi-k2.5"

    def test_dev_backend_static_reste_deep(self, kimi):
        # Mode static (défaut GA) : tier_default deep -> kimi-k3.
        res = resolve_model(get_agent_bounds("dev-backend", env=ENV), None, kimi)
        assert res.tier_final == "deep"
        assert res.model == "kimi-k3"
