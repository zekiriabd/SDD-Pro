"""Tests de cohérence des loaders NEUTRES .sdd/ (Phase 1, sans réseau).

Vérifie la triple cohérence :
  .sdd/loader.yml + .sdd/loader.reverse.yml  (manifestes neutres, model_tier)
  <-> .sdd/agents/*.agent.yaml               (pivots agents)
  <-> .sdd/agent-bounds.yaml                 (SSoT bornes tier_floor/ceiling)

a. bijection agents loaders <-> pivots (pas d'orphelin, ni d'un côté ni de l'autre) ;
b. model_tier loader == model_tier pivot == tier_default bounds ;
c. tout model_tier ∈ {deep, balanced, fast} ;
d. clamp_tier(tier_default, floor, ceiling) == tier_default (bornes cohérentes).

Exécution : python -m pytest .sdd/python/tests/ -q
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_lib.model_resolver import TIERS, clamp_tier  # noqa: E402

SDD_HOME = Path(__file__).resolve().parents[2]
LOADER_FWD = SDD_HOME / "loader.yml"
LOADER_REV = SDD_HOME / "loader.reverse.yml"
AGENTS_DIR = SDD_HOME / "agents"
BOUNDS_PATH = SDD_HOME / "agent-bounds.yaml"

VALID_TIERS = set(TIERS)  # {fast, balanced, deep}


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict), f"{path.name}: racine YAML non-mapping"
    return doc


def _forward_agents() -> dict[str, dict]:
    """Agents du loader forward = entrées top-level portant model_tier
    (les clés méta version/updated/schema/status sont des scalaires)."""
    doc = _load_yaml(LOADER_FWD)
    return {
        name: spec
        for name, spec in doc.items()
        if isinstance(spec, dict) and "model_tier" in spec
    }


def _reverse_agents() -> dict[str, dict]:
    doc = _load_yaml(LOADER_REV)
    agents = doc.get("agents")
    assert isinstance(agents, dict) and agents, "loader.reverse.yml: section agents absente/vide"
    return agents


def _loader_agents() -> dict[str, dict]:
    fwd = _forward_agents()
    rev = _reverse_agents()
    overlap = set(fwd) & set(rev)
    assert not overlap, f"agents déclarés dans les DEUX loaders (interdit): {sorted(overlap)}"
    return {**fwd, **rev}


def _pivots() -> dict[str, dict]:
    files = sorted(AGENTS_DIR.glob("*.agent.yaml"))
    assert files, f"aucun pivot *.agent.yaml sous {AGENTS_DIR}"
    return {f.name.removesuffix(".agent.yaml"): _load_yaml(f) for f in files}


def _bounds() -> dict[str, dict]:
    return _load_yaml(BOUNDS_PATH)["agents"]


# ---------------------------------------------------------------------------
# a. Bijection loaders <-> pivots (pas d'agent orphelin, dans les 2 sens)
# ---------------------------------------------------------------------------

class TestBijectionLoaderPivots:
    def test_chaque_agent_loader_a_son_pivot(self):
        missing = set(_loader_agents()) - set(_pivots())
        assert not missing, f"agents loader sans pivot .sdd/agents/: {sorted(missing)}"

    def test_chaque_pivot_est_dans_un_loader(self):
        orphans = set(_pivots()) - set(_loader_agents())
        assert not orphans, f"pivots sans entrée loader (orphelins): {sorted(orphans)}"

    def test_effectifs_13_forward_12_reverse(self):
        # Photo Phase 1 (2026-07-24) : 13 forward + 12 reverse = 25 = bounds.
        assert len(_forward_agents()) == 13
        assert len(_reverse_agents()) == 12
        assert len(_loader_agents()) == len(_bounds()) == 25

    def test_pivot_name_interne_coherent(self):
        for name, pivot in _pivots().items():
            assert pivot.get("name") == name, (
                f"pivot {name}.agent.yaml: champ name={pivot.get('name')!r} ≠ basename"
            )


# ---------------------------------------------------------------------------
# b. model_tier loader == pivot == tier_default bounds
# ---------------------------------------------------------------------------

class TestTierParity:
    def test_loader_tier_egal_pivot_tier(self):
        pivots = _pivots()
        mismatches = {
            name: (spec["model_tier"], pivots[name].get("model_tier"))
            for name, spec in _loader_agents().items()
            if spec["model_tier"] != pivots[name].get("model_tier")
        }
        assert not mismatches, f"model_tier loader ≠ pivot: {mismatches}"

    def test_loader_tier_egal_bounds_tier_default(self):
        bounds = _bounds()
        missing = set(_loader_agents()) - set(bounds)
        assert not missing, f"agents loader absents de agent-bounds.yaml: {sorted(missing)}"
        mismatches = {
            name: (spec["model_tier"], bounds[name]["tier_default"])
            for name, spec in _loader_agents().items()
            if spec["model_tier"] != bounds[name]["tier_default"]
        }
        assert not mismatches, f"model_tier loader ≠ tier_default bounds: {mismatches}"

    def test_pivot_bornes_egales_bounds(self):
        # Le pivot recopie floor/ceiling/default — agent-bounds.yaml reste la SSoT.
        bounds = _bounds()
        for name, pivot in _pivots().items():
            for key in ("tier_default", "tier_floor", "tier_ceiling"):
                assert pivot.get(key) == bounds[name][key], (
                    f"{name}: {key} pivot={pivot.get(key)!r} ≠ bounds={bounds[name][key]!r}"
                )


# ---------------------------------------------------------------------------
# c. Enum stricte des tiers
# ---------------------------------------------------------------------------

class TestTierEnum:
    def test_model_tier_dans_enum(self):
        bad = {
            name: spec["model_tier"]
            for name, spec in _loader_agents().items()
            if spec["model_tier"] not in VALID_TIERS
        }
        assert not bad, f"model_tier hors enum {sorted(VALID_TIERS)}: {bad}"

    def test_bounds_tiers_dans_enum(self):
        for name, b in _bounds().items():
            for key in ("tier_default", "tier_floor", "tier_ceiling"):
                assert b[key] in VALID_TIERS, f"{name}.{key}={b[key]!r} hors enum"


# ---------------------------------------------------------------------------
# d. tier_default respecte [tier_floor, tier_ceiling] (via clamp_tier)
# ---------------------------------------------------------------------------

class TestBoundsInvariants:
    def test_default_invariant_par_clamp(self):
        # clamp(default, floor, ceiling) == default <=> floor ≤ default ≤ ceiling.
        # clamp_tier lève aussi ValueError si floor > ceiling (bornes incohérentes).
        violations = {}
        for name, b in _bounds().items():
            try:
                clamped = clamp_tier(b["tier_default"], b["tier_floor"], b["tier_ceiling"])
            except ValueError as exc:
                violations[name] = str(exc)
                continue
            if clamped != b["tier_default"]:
                violations[name] = f"default {b['tier_default']} clampé -> {clamped}"
        assert not violations, f"tier_default hors bornes: {violations}"

    def test_pas_de_floor_deep(self):
        # Photo bounds 2026-07-24 : 0 floor=deep (garde contre un lock coûteux involontaire).
        deep_floors = [n for n, b in _bounds().items() if b["tier_floor"] == "deep"]
        assert not deep_floors, f"floor=deep inattendu: {deep_floors}"


# ---------------------------------------------------------------------------
# Sanity structure loaders neutres
# ---------------------------------------------------------------------------

class TestLoaderStructure:
    def test_forward_sans_cle_model_anthropic(self):
        # Le loader neutre ne doit porter AUCUN champ `model:` (IDs concrets
        # = providers/*.yaml uniquement).
        for name, spec in _loader_agents().items():
            assert "model" not in spec, f"{name}: champ `model:` interdit dans le loader neutre"

    def test_reverse_reste_autonome(self):
        doc = _load_yaml(LOADER_REV)
        assert doc.get("extends") is None, "loader.reverse.yml doit rester autonome (extends: null)"
        assert doc.get("manifestType") == "reverse-engineering"

    def test_reads_writes_presents(self):
        for name, spec in _loader_agents().items():
            assert spec.get("reads"), f"{name}: reads absent/vide"
            assert spec.get("writes"), f"{name}: writes absent/vide"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
