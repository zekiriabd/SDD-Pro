"""Unit tests for sdd_scripts.conformance_run (audit M7 2026-07-26).

Le script `conformance_run.py` (951 LOC) était sans un seul test unitaire —
951 lignes de parsing subprocess + logique verdict + rendu markdown/json
sans couverture. Ce fichier verrouille les fonctions pures + les
dataclasses + le comportement E2E dry-run (chemin le plus important —
c'est le mode par défaut du CLI).

Périmètre couvert :
- Constantes SSoT (REFERENCE_COMBO, DEFAULT_COMBOS, KNOWN_HARNESSES,
  KNOWN_PROVIDERS, DEFAULT_TIMEOUT_S) — anti-régression contre drift.
- Parsing CLI : _parse_combo_arg (3 séparateurs, erreurs).
- Sélection combos : _select_combos.
- Agrégation verdict : _aggregate_verdict (5 chemins × strict on/off).
- Stack.md dispatch : _synth_stack_md, _rewrite_stack_dispatch.
- Vérif adapter : _check_harness_adapter (Claude/Codex/Gemini/Antigravity/inconnu).
- Dataclasses : ComboResult (label property), RunReport.to_json.
- Main E2E dry-run : combo unique, verdict PASS, JSON schéma valide, exit 0.

Hors périmètre (délibéré) :
- _validate_combo_live : nécessite API keys + subprocess (out-of-scope
  unit test, testable en intégration).
- _invoke_bootstrap_dry : subprocess.run (idem).
- _check_harness_cli : dépend de shutil.which (env-dependent, brittle).
- _render_markdown_report : rendu texte cosmétique, faible risque.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

from sdd_lib.exit_codes import SUCCESS, FAIL_FAST, CORRECTIBLE, INFRA_BLOCKED  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_scripts import conformance_run as cr  # noqa: E402


pytestmark = pytest.mark.smoke


# --- Constantes SSoT --------------------------------------------------------


def test_reference_combo_is_claude_anthropic() -> None:
    assert cr.REFERENCE_COMBO == ("claude-code", "anthropic")


def test_default_combos_covers_5_pairs() -> None:
    assert len(cr.DEFAULT_COMBOS) == 5
    assert cr.REFERENCE_COMBO in cr.DEFAULT_COMBOS


def test_default_combos_are_valid_tuples() -> None:
    """Chaque combo est (harness, provider) avec valeurs dans les enums SSoT."""
    for h, p in cr.DEFAULT_COMBOS:
        assert h in cr.KNOWN_HARNESSES, f"harness {h!r} pas dans KNOWN_HARNESSES"
        assert p in cr.KNOWN_PROVIDERS, f"provider {p!r} pas dans KNOWN_PROVIDERS"


def test_known_harnesses_matches_capability_matrix() -> None:
    """4 harnesses attendus : claude-code, codex, gemini-cli, antigravity."""
    assert set(cr.KNOWN_HARNESSES) == {"claude-code", "codex", "gemini-cli", "antigravity"}


def test_known_providers_matches_yamls() -> None:
    """4 providers attendus : les YAMLs .sdd/providers/*.yaml existants."""
    assert set(cr.KNOWN_PROVIDERS) == {"anthropic", "openai", "google", "moonshot"}


def test_default_timeout_is_30_min() -> None:
    assert cr.DEFAULT_TIMEOUT_S == 30 * 60.0


def test_default_feat_fixture_name() -> None:
    assert cr.DEFAULT_FEAT_FIXTURE_NAME == "1-CalcABC.md"


# --- _parse_combo_arg -------------------------------------------------------


def test_parse_combo_arg_colon_separator() -> None:
    assert cr._parse_combo_arg("codex:openai") == ("codex", "openai")


def test_parse_combo_arg_x_separator() -> None:
    assert cr._parse_combo_arg("gemini-cli×google") == ("gemini-cli", "google")


def test_parse_combo_arg_ascii_x_separator() -> None:
    assert cr._parse_combo_arg("codex×moonshot") == ("codex", "moonshot")


def test_parse_combo_arg_strips_whitespace() -> None:
    assert cr._parse_combo_arg("  codex : openai  ") == ("codex", "openai")


def test_parse_combo_arg_rejects_no_separator() -> None:
    """`+` n'est pas un séparateur reconnu (ni `:` ni `×` ni `x`).

    Note piège : les tokens `codex-openai` ou `harness_provider` contiennent
    `x`/`e`/... et matchent le séparateur ASCII `x` — le rejeter proprement
    exige un raw *sans* aucun caractère parmi `:×x`.
    """
    import argparse
    with pytest.raises(argparse.ArgumentTypeError, match="combo invalide"):
        cr._parse_combo_arg("aaa+bbb")


# --- _select_combos ---------------------------------------------------------


def test_select_combos_none_returns_defaults() -> None:
    assert cr._select_combos(None) == list(cr.DEFAULT_COMBOS)


def test_select_combos_empty_returns_defaults() -> None:
    """Falsy list also falls through to defaults."""
    assert cr._select_combos([]) == list(cr.DEFAULT_COMBOS)


def test_select_combos_explicit_overrides_defaults() -> None:
    override = [("codex", "openai"), ("gemini-cli", "google")]
    assert cr._select_combos(override) == override


# --- _aggregate_verdict -----------------------------------------------------


def _mk(verdict: str) -> cr.ComboResult:
    return cr.ComboResult(
        harness="claude-code", provider="anthropic",
        verdict=verdict, class_code="[X]",
    )


def test_aggregate_all_pass_is_success() -> None:
    assert cr._aggregate_verdict([_mk("PASS"), _mk("PASS")], strict=False) == ("PASS", SUCCESS)


def test_aggregate_empty_is_pass() -> None:
    """No combos processed → still PASS (vacuous truth)."""
    assert cr._aggregate_verdict([], strict=False) == ("PASS", SUCCESS)


def test_aggregate_one_drift_lax_is_correctible_warn() -> None:
    combos = [_mk("PASS"), _mk("DRIFT")]
    assert cr._aggregate_verdict(combos, strict=False) == ("DRIFT", CORRECTIBLE)


def test_aggregate_one_drift_strict_is_fail_fast() -> None:
    combos = [_mk("PASS"), _mk("DRIFT")]
    assert cr._aggregate_verdict(combos, strict=True) == ("FAIL", FAIL_FAST)


def test_aggregate_infra_blocked_wins_over_drift() -> None:
    """INFRA_BLOCKED prime sur DRIFT (both present → INFRA_BLOCKED verdict)."""
    combos = [_mk("DRIFT"), _mk("INFRA_BLOCKED")]
    assert cr._aggregate_verdict(combos, strict=False) == ("FAIL", INFRA_BLOCKED)


def test_aggregate_fail_wins_over_all() -> None:
    """FAIL config prime sur tout (exit FAIL_FAST)."""
    combos = [_mk("PASS"), _mk("DRIFT"), _mk("INFRA_BLOCKED"), _mk("FAIL")]
    assert cr._aggregate_verdict(combos, strict=False) == ("FAIL", FAIL_FAST)


# --- _synth_stack_md --------------------------------------------------------


def test_synth_stack_md_contains_2_active_sections() -> None:
    stack = cr._synth_stack_md(harness="codex", provider="openai")
    assert "## Active Harness" in stack
    assert "## Active Model Provider" in stack
    assert "Harness: codex" in stack
    assert "Provider: openai" in stack


def test_synth_stack_md_is_parseable_by_stack_config() -> None:
    """Le stack synthétisé doit être consommable par parse_stack_config."""
    from sdd_lib.stack_config import parse_stack_config
    stack = cr._synth_stack_md(harness="gemini-cli", provider="google")
    cfg = parse_stack_config(stack)
    assert cfg.harness == "gemini-cli"
    assert cfg.provider == "google"


# --- _rewrite_stack_dispatch ------------------------------------------------


def test_rewrite_replaces_existing_harness_line() -> None:
    src = (
        "# Project Stack\n\n"
        "## Active Harness\n"
        "Harness: claude-code\n\n"
        "## Active Model Provider\n"
        "Provider: anthropic\n"
    )
    result = cr._rewrite_stack_dispatch(src, harness="codex", provider="openai")
    assert "Harness: codex" in result
    assert "Provider: openai" in result
    assert "Harness: claude-code" not in result
    assert "Provider: anthropic" not in result


def test_rewrite_prepends_missing_sections() -> None:
    src = "# Project Stack (no active sections)\n\nSome content\n"
    result = cr._rewrite_stack_dispatch(src, harness="codex", provider="openai")
    assert "## Active Harness" in result
    assert "## Active Model Provider" in result
    # Original content preserved
    assert "Some content" in result


def test_rewrite_is_idempotent_when_target_matches() -> None:
    """Réécrire avec les valeurs déjà en place ne casse rien."""
    src = (
        "## Active Harness\n"
        "Harness: codex\n\n"
        "## Active Model Provider\n"
        "Provider: openai\n"
    )
    once = cr._rewrite_stack_dispatch(src, harness="codex", provider="openai")
    twice = cr._rewrite_stack_dispatch(once, harness="codex", provider="openai")
    assert once == twice


# --- _check_harness_adapter -------------------------------------------------


def test_check_harness_adapter_claude_ok() -> None:
    ok, note = cr._check_harness_adapter("claude-code", repo_root())
    assert ok is True
    assert "ClaudeAdapter" in note


def test_check_harness_adapter_codex_ok() -> None:
    ok, note = cr._check_harness_adapter("codex", repo_root())
    assert ok is True
    assert "CodexAdapter" in note


def test_check_harness_adapter_gemini_ok() -> None:
    ok, note = cr._check_harness_adapter("gemini-cli", repo_root())
    assert ok is True
    assert "GeminiAdapter" in note


def test_check_harness_adapter_antigravity_ok() -> None:
    ok, note = cr._check_harness_adapter("antigravity", repo_root())
    assert ok is True
    assert "AntigravityAdapter" in note


def test_check_harness_adapter_unknown_harness() -> None:
    ok, note = cr._check_harness_adapter("azure-openai", repo_root())
    assert ok is False
    assert "inconnu" in note.lower()


def test_check_harness_adapter_missing_harness_build(tmp_path: Path) -> None:
    """Un root sans .sdd/harness_build.py → False + note explicite."""
    (tmp_path / ".sdd").mkdir()
    ok, note = cr._check_harness_adapter("claude-code", tmp_path)
    assert ok is False
    assert "absent" in note


# --- Dataclass ComboResult --------------------------------------------------


def test_combo_result_label_property() -> None:
    r = cr.ComboResult(
        harness="codex", provider="openai",
        verdict="PASS", class_code="[X]",
    )
    assert r.label == "codex × openai"


def test_combo_result_default_fields() -> None:
    """duration_s / is_reference / checks / notes ont des defaults."""
    r = cr.ComboResult(
        harness="claude-code", provider="anthropic",
        verdict="PASS", class_code="[X]",
    )
    assert r.duration_s == 0.0
    assert r.is_reference is False
    assert r.checks == []
    assert r.notes == ""


# --- Dataclass RunReport ----------------------------------------------------


def test_run_report_to_json_shape_valid() -> None:
    r1 = cr.ComboResult(
        harness="claude-code", provider="anthropic",
        verdict="PASS", class_code="[CONFORMANCE_PASS]",
        duration_s=0.05, is_reference=True,
    )
    report = cr.RunReport(
        mode="dry-run",
        started_at="2026-07-26T10:00:00+00:00",
        finished_at="2026-07-26T10:00:01+00:00",
        duration_s=1.0,
        combos=[r1],
        feat_fixture="/tmp/1-CalcABC.md",
        stack_fixture="/tmp/stack.md.fixture",
        reference_combo="claude-code × anthropic",
        verdict="PASS",
        exit_code=0,
    )
    js = report.to_json()
    parsed = json.loads(js)
    assert parsed["schema"] == "sdd.conformance/v1"
    assert parsed["mode"] == "dry-run"
    assert parsed["verdict"] == "PASS"
    assert parsed["exit_code"] == 0
    assert len(parsed["combos"]) == 1
    assert parsed["combos"][0]["harness"] == "claude-code"
    assert parsed["combos"][0]["is_reference"] is True


def test_run_report_to_json_rounds_duration_3_decimals() -> None:
    """duration_s arrondi à 3 décimales dans le JSON output."""
    report = cr.RunReport(
        mode="dry-run",
        started_at="X", finished_at="Y", duration_s=1.23456789,
        combos=[], feat_fixture="/tmp/f", stack_fixture="/tmp/s",
        reference_combo="X × Y", verdict="PASS", exit_code=0,
    )
    parsed = json.loads(report.to_json())
    assert parsed["duration_s"] == 1.235


# --- Main E2E dry-run -------------------------------------------------------


def test_main_dry_run_default_returns_pass_exit_0(tmp_path: Path, capsys) -> None:
    """Le CLI par défaut (dry-run, 5 combos) sort PASS+exit 0 sur ce repo.

    Test load-bearing : c'est le mode utilisé par `python conformance_run.py`
    sans args, référencé dans docs/multi-llm-getting-started.md.
    """
    out_root = tmp_path / "out"
    exit_code = cr.main(["--dry-run", "--output-root", str(out_root)])
    assert exit_code == SUCCESS

    # Rapport JSON existe et est valide
    json_reports = list(out_root.rglob("report.json"))
    assert len(json_reports) == 1
    report = json.loads(json_reports[0].read_text(encoding="utf-8"))
    assert report["schema"] == "sdd.conformance/v1"
    assert report["verdict"] == "PASS"
    assert report["mode"] == "dry-run"
    assert len(report["combos"]) == 5


def test_main_dry_run_single_combo(tmp_path: Path) -> None:
    """--combo restricts to 1 pair."""
    out_root = tmp_path / "out"
    exit_code = cr.main([
        "--dry-run", "--combo", "codex:openai",
        "--output-root", str(out_root),
    ])
    assert exit_code == SUCCESS
    report = json.loads((next(out_root.rglob("report.json"))).read_text(encoding="utf-8"))
    assert len(report["combos"]) == 1
    assert report["combos"][0]["harness"] == "codex"
    assert report["combos"][0]["provider"] == "openai"
