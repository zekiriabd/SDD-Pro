"""Tests du parseur stack.md (Phase 1.7 — plan §8.3 + §8.bis.2).

Vérifie que `sdd_lib.stack_config` lit les 2 axes (harnais × provider) + la
sélection de modèle depuis un `stack.md`, avec défauts RÉTRO-COMPATIBLES
(absence de section = claude-code / anthropic / static), et compose avec
`model_resolver` (mode + provider par tier).

Exécution : python -m pytest .sdd/python/tests/ -q  (pur, aucune I/O réseau)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

from sdd_lib.model_resolver import resolve_model  # noqa: E402
from sdd_lib.stack_config import (  # noqa: E402
    DEFAULT_HARNESS,
    DEFAULT_MODE,
    DEFAULT_PROVIDER,
    StackConfig,
    StackConfigError,
    load_stack_config,
    parse_stack_config,
)

FULL_STACK = """\
# stack.md — projet démo

## Active Harness
Harness: codex                  # claude-code | codex | antigravity | gemini-cli

## Active Model Provider
Provider: moonshot              # anthropic | openai | google | moonshot
Endpoint: https://proxy.local/v1
ModelTierMap:                   # override par tier — mixage cross-provider
  deep: anthropic
  balanced: moonshot
  fast: moonshot

## Model Selection
Mode: dynamic                   # static | dynamic

## Project Config
CoverageMin: 80
"""


# --------------------------------------------------------------------- #
# Défauts rétro-compatibles                                            #
# --------------------------------------------------------------------- #


def test_empty_text_yields_all_defaults():
    cfg = parse_stack_config("")
    assert cfg.harness == DEFAULT_HARNESS == "claude-code"
    assert cfg.provider == DEFAULT_PROVIDER == "anthropic"
    assert cfg.endpoint == "default"
    assert cfg.mode == DEFAULT_MODE == "static"
    assert cfg.tier_providers == {"deep": "anthropic", "balanced": "anthropic", "fast": "anthropic"}
    assert cfg.is_reference_combo() is True


def test_legacy_stack_without_new_sections_is_reference():
    """Un stack.md legacy (sections métier seules) reste claude-code/anthropic/static."""
    legacy = "## Active Backend\nStack: dotnet\n\n## Project Config\nCoverageMin: 80\n"
    cfg = parse_stack_config(legacy)
    assert (cfg.harness, cfg.provider, cfg.mode) == ("claude-code", "anthropic", "static")
    assert cfg.is_reference_combo() is True


def test_partial_only_harness_keeps_other_defaults():
    cfg = parse_stack_config("## Active Harness\nHarness: gemini-cli\n")
    assert cfg.harness == "gemini-cli"
    assert cfg.provider == "anthropic"  # défaut
    assert cfg.mode == "static"
    assert cfg.is_reference_combo() is False


# --------------------------------------------------------------------- #
# Parsing complet + mixage cross-provider                              #
# --------------------------------------------------------------------- #


def test_full_config_parsed():
    cfg = parse_stack_config(FULL_STACK)
    assert cfg.harness == "codex"
    assert cfg.provider == "moonshot"
    assert cfg.endpoint == "https://proxy.local/v1"
    assert cfg.mode == "dynamic"
    assert cfg.is_reference_combo() is False


def test_model_tier_map_cross_provider_mixing():
    cfg = parse_stack_config(FULL_STACK)
    assert cfg.provider_for_tier("deep") == "anthropic"
    assert cfg.provider_for_tier("balanced") == "moonshot"
    assert cfg.provider_for_tier("fast") == "moonshot"


def test_tier_map_unspecified_tiers_fall_back_to_provider():
    text = (
        "## Active Model Provider\nProvider: openai\nModelTierMap:\n  deep: anthropic\n"
    )
    cfg = parse_stack_config(text)
    assert cfg.provider_for_tier("deep") == "anthropic"   # surchargé
    assert cfg.provider_for_tier("balanced") == "openai"  # retombe sur Provider
    assert cfg.provider_for_tier("fast") == "openai"


def test_inline_comments_are_stripped():
    cfg = parse_stack_config("## Active Harness\nHarness: claude-code   # commentaire\n")
    assert cfg.harness == "claude-code"


def test_keys_and_section_titles_case_insensitive():
    text = "## active harness\nharness: codex\n\n## MODEL SELECTION\nMODE: dynamic\n"
    cfg = parse_stack_config(text)
    assert cfg.harness == "codex"
    assert cfg.mode == "dynamic"


def test_tier_map_block_terminated_by_next_section():
    """Le bloc ModelTierMap s'arrête à la section suivante (pas de fuite)."""
    cfg = parse_stack_config(FULL_STACK)
    # `## Model Selection` et `## Project Config` ne polluent pas le tier_map.
    assert set(cfg.tier_providers) == {"deep", "balanced", "fast"}


# --------------------------------------------------------------------- #
# Validation fail-explicit                                             #
# --------------------------------------------------------------------- #


def test_invalid_harness_raises():
    with pytest.raises(StackConfigError):
        parse_stack_config("## Active Harness\nHarness: bun-cli\n")


def test_invalid_mode_raises():
    with pytest.raises(StackConfigError):
        parse_stack_config("## Model Selection\nMode: turbo\n")


def test_invalid_tier_in_map_raises():
    with pytest.raises(StackConfigError):
        parse_stack_config(
            "## Active Model Provider\nProvider: anthropic\nModelTierMap:\n  ultra: anthropic\n"
        )


def test_provider_for_tier_unknown_tier_raises():
    with pytest.raises(StackConfigError):
        parse_stack_config("").provider_for_tier("ultra")


# --------------------------------------------------------------------- #
# I/O                                                                   #
# --------------------------------------------------------------------- #


def test_load_stack_config_from_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "stack.md"
        p.write_text(FULL_STACK, encoding="utf-8")
        cfg = load_stack_config(p)
        assert cfg.harness == "codex"
        assert cfg.mode == "dynamic"


def test_load_stack_config_missing_file_raises():
    with pytest.raises(StackConfigError):
        load_stack_config(Path("does/not/exist/stack.md"))


# --------------------------------------------------------------------- #
# Composition avec model_resolver (la glu que ce parseur fournit)       #
# --------------------------------------------------------------------- #


def test_composes_with_model_resolver_dynamic_mixing():
    """StackConfig fournit mode + provider par tier ; model_resolver résout le modèle."""
    cfg = parse_stack_config(FULL_STACK)  # mode=dynamic, balanced->moonshot
    bounds = {"tier_default": "deep", "tier_floor": "balanced", "tier_ceiling": "deep"}
    # Simule un work-item de complexité low -> tier candidat fast, clampé à balanced.
    tier_map_moonshot = {"deep": "kimi-k3", "balanced": "kimi-k2.7-code", "fast": "kimi-k2.5"}
    res = resolve_model(bounds, level="low", provider_tier_map=tier_map_moonshot, mode=cfg.mode)
    assert res.tier_final == "balanced"
    # Le provider du tier balanced est moonshot (mixage) -> modèle Kimi balanced.
    assert cfg.provider_for_tier(res.tier_final) == "moonshot"
    assert res.model == "kimi-k2.7-code"
