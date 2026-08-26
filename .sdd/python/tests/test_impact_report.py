"""Tests du rapport d'impact (Phase 2.5 — plan multi-harness §7.3, ADR D5).

Vérifie que `sdd_lib.impact_report` construit un rapport honnête par combo
harnais × provider depuis les SSoT `.sdd/capability-matrix.yml` +
`.sdd/providers/{p}.yaml`, et que `harness_build.py` l'imprime + le persiste
sur CHAQUE build sans jamais échouer une transpilation.

Exécution : python -m pytest .sdd/python/tests/ -q
Lecture seule sur .claude/** ; écrit uniquement sous .sdd/.build/ (nettoyé).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

SDD_HOME = Path(__file__).resolve().parents[2]  # .sdd/
REPO_ROOT = SDD_HOME.parent
if str(SDD_HOME) not in sys.path:
    sys.path.insert(0, str(SDD_HOME))  # pour importer harness_build.py

from harness_build import main  # noqa: E402
from sdd_lib.config_loader import ConfigError  # noqa: E402
from sdd_lib.impact_report import (  # noqa: E402
    ALLOW_UNTESTED_ENV,
    MECHANISM_LABELS,
    build_impact_report,
    untested_gate_ok,
)


@pytest.fixture()
def build_dir():
    """Dossier temp jetable SOUS .sdd/.build/ (jamais .claude/)."""
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-impact-", dir=build_root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------------- #
# Construction du rapport                                               #
# --------------------------------------------------------------------- #


def test_reference_combo_is_level_a_and_tested():
    """claude-code × anthropic = référence : niveau A, 7 mécanismes natifs, non UNTESTED."""
    report = build_impact_report("claude-code", "anthropic")
    assert report.protection_level == "A"
    assert report.is_reference is True
    assert report.untested is False
    counts = report.mechanism_counts()
    assert counts["native"] == len(MECHANISM_LABELS) == 7
    assert counts["emulated"] == counts["ci_fallback"] == counts["unsupported"] == 0
    # Aucun ⚠ de niveau mécanisme (tous natifs) ; ne reste que
    # l'avertissement provider de fidélité unknown.
    assert not any(
        label in w for w in report.warnings for label in MECHANISM_LABELS.values()
    )
    assert len(report.warnings) == 1  # fidélité seulement


def test_codex_moonshot_is_untested_level_b_with_warnings():
    """codex × moonshot : niveau B, UNTESTED, comptes mécanismes exacts + ⚠."""
    report = build_impact_report("codex", "moonshot")
    assert report.protection_level == "B"
    assert report.is_reference is False
    assert report.untested is True
    counts = report.mechanism_counts()
    # subagent_spawn/skills_autotrigger/slash_commands=emulated (3),
    # runtime_hooks=ci_fallback (1), at_include=unsupported (1),
    # deterministic_python/mcp=native (2).
    assert counts == {"native": 2, "emulated": 3, "ci_fallback": 1, "unsupported": 1}
    assert sum(counts.values()) == 7
    # Un ⚠ par mécanisme non natif (5) + fidélité = 6 avertissements.
    assert len(report.warnings) == 6


@pytest.mark.parametrize("provider", ["anthropic", "openai", "google", "moonshot"])
def test_all_providers_loadable(provider):
    """Les 4 providers du foyer sont lisibles par le rapport (fail-explicit sinon)."""
    report = build_impact_report("gemini-cli", provider)
    assert report.provider == provider
    # Aucun provider n'a encore de fidélité 'high' (aucun conformance run) →
    # tout combo non-référence est UNTESTED.
    assert report.untested is True


def test_unknown_harness_raises():
    with pytest.raises(ConfigError):
        build_impact_report("does-not-exist", "anthropic")


def test_unknown_provider_raises():
    with pytest.raises(ConfigError):
        build_impact_report("claude-code", "does-not-exist")


def test_render_is_ascii_safe():
    """render() (stdout) ne contient AUCUN glyphe hors cp1252 (⚠/✅/emoji)."""
    for harness, provider in (("claude-code", "anthropic"), ("codex", "moonshot")):
        text = build_impact_report(harness, provider).render()
        text.encode("cp1252")  # lève UnicodeEncodeError si un glyphe non-cp1252 fuit
        assert "HARNESS BUILD REPORT" in text
        assert "Niveau de protection global" in text


def test_markdown_contains_required_sections():
    md = build_impact_report("codex", "moonshot").to_markdown()
    assert "# Rapport d'impact" in md
    assert "## Mécanismes" in md
    assert "UNTESTED" in md
    assert ALLOW_UNTESTED_ENV in md
    for label in MECHANISM_LABELS.values():
        assert label in md


# --------------------------------------------------------------------- #
# Gate UNTESTED (consommateur pipeline, pas le build)                   #
# --------------------------------------------------------------------- #


def test_gate_reference_always_ok():
    report = build_impact_report("claude-code", "anthropic")
    assert untested_gate_ok(report, env={}) is True


def test_gate_untested_blocks_without_env():
    report = build_impact_report("codex", "moonshot")
    assert untested_gate_ok(report, env={}) is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_gate_untested_bypassed_with_env(value):
    report = build_impact_report("codex", "moonshot")
    assert untested_gate_ok(report, env={ALLOW_UNTESTED_ENV: value}) is True


# --------------------------------------------------------------------- #
# Intégration CLI harness_build.py — le rapport ne bloque JAMAIS         #
# --------------------------------------------------------------------- #


def test_cli_prints_and_persists_report_reference(build_dir, capsys):
    """Build de référence : rc=0, rapport imprimé + persisté harness-impact.md."""
    rc = main(["--harness", "claude-code", "--memory-only", "--out", str(build_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "HARNESS BUILD REPORT" in out
    assert "[REFERENCE]" in out
    assert (build_dir / "harness-impact.md").is_file()


def test_cli_untested_combo_still_succeeds(build_dir, capsys):
    """codex × moonshot (UNTESTED) : le build reste non bloquant (rc=0)."""
    rc = main(
        ["--harness", "codex", "--memory-only", "--provider", "moonshot", "--out", str(build_dir)]
    )
    assert rc == 0, "le rapport d'impact ne doit JAMAIS faire échouer une transpilation"
    out = capsys.readouterr().out
    assert "[UNTESTED]" in out
    assert (build_dir / "harness-impact.md").is_file()


def test_cli_default_provider_is_anthropic(build_dir, capsys):
    """Sans --provider, le défaut anthropic est utilisé (rétrocompat)."""
    main(["--harness", "claude-code", "--memory-only", "--out", str(build_dir)])
    assert "provider=anthropic" in capsys.readouterr().out
