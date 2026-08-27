"""Tests des façades Codex + Gemini (Phase 3.1 / 4.1 — transpilation commandes + config).

Vérifie que les adaptateurs non-Claude émettent une couche COMMANDES complète
(slash-commands transpilées) + le fichier de config du harnais, bien formés
(TOML/JSON valides), corps métier préservé (@-includes réécrits), le tout SOUS
`.sdd/.build/` uniquement. La couche AGENTS reste non applicable (sous-agents
émulés au runtime) → NotImplementedError.

Token-free (pure transpilation) ; écrit uniquement sous .sdd/.build/ (nettoyé).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

SDD_HOME = Path(__file__).resolve().parents[2]  # .sdd/
REPO_ROOT = SDD_HOME.parent
if str(SDD_HOME) not in sys.path:
    sys.path.insert(0, str(SDD_HOME))

from harness_build import (  # noqa: E402
    CodexAdapter,
    GeminiAdapter,
    _escape_codex_positionals,
    main,
)

N_COMMANDS = len(list((SDD_HOME / "commands").glob("*.md")))


@pytest.fixture()
def build_dir():
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-cxgm-", dir=build_root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


def test_command_count_is_41():
    # +1 le 2026-08-26 : /sdd-db-context (Phase 0 du reverse base de donnees).
    assert N_COMMANDS == 41


# --------------------------------------------------------------------- #
# Codex — prompts .md + config.toml                                    #
# --------------------------------------------------------------------- #


def test_codex_emits_all_prompts_and_config(build_dir):
    results = CodexAdapter(repo_root=REPO_ROOT, provider="moonshot").emit_commands(build_dir)
    written = [r for r in results if r.ok]
    skipped = {r.agent: r.skipped_reason for r in results if not r.ok}
    assert not skipped, f"skips: {skipped}"
    prompts = list((build_dir / "prompts").glob("*.md"))
    assert len(prompts) == N_COMMANDS
    assert (build_dir / "config.toml").is_file()


def test_codex_config_is_valid_toml_with_provider(build_dir):
    CodexAdapter(repo_root=REPO_ROOT, provider="moonshot").emit_config(build_dir)
    data = tomllib.loads((build_dir / "config.toml").read_text(encoding="utf-8"))
    assert data["model_provider"] == "moonshot"
    assert "moonshot" in data["model_providers"]
    # moonshot -> base_url OpenAI-compat depuis endpoints.openai
    assert "moonshot.ai" in data["model_providers"]["moonshot"]["base_url"]


def test_codex_prompt_preserves_body_and_rewrites_at_includes(build_dir):
    CodexAdapter(repo_root=REPO_ROOT).emit_commands(build_dir)
    text = (build_dir / "prompts" / "sdd-full.md").read_text(encoding="utf-8")
    assert "$ARGUMENTS" in text
    assert "@.claude" not in text            # lazy-includes réécrits
    assert len(text) > 5000                  # corps métier complet embarqué


def test_codex_agents_layer_not_applicable(build_dir):
    with pytest.raises(NotImplementedError):
        CodexAdapter(repo_root=REPO_ROOT).emit_agents(build_dir)


# --------------------------------------------------------------------- #
# Gemini — commands .toml + settings.json                              #
# --------------------------------------------------------------------- #


def test_gemini_emits_all_toml_commands_and_settings(build_dir):
    results = GeminiAdapter(repo_root=REPO_ROOT, provider="google").emit_commands(build_dir)
    skipped = {r.agent: r.skipped_reason for r in results if not r.ok}
    assert not skipped, f"skips: {skipped}"
    tomls = list((build_dir / "commands").glob("*.toml"))
    assert len(tomls) == N_COMMANDS
    assert (build_dir / "settings.json").is_file()


def test_gemini_every_command_is_valid_toml(build_dir):
    """Corps avec code fences / guillemets -> TOML multi-ligne valide (échappement)."""
    GeminiAdapter(repo_root=REPO_ROOT).emit_commands(build_dir)
    for f in (build_dir / "commands").glob("*.toml"):
        data = tomllib.loads(f.read_text(encoding="utf-8"))
        assert "description" in data and "prompt" in data
        assert "{{args}}" in data["prompt"]
        assert "@.claude" not in data["prompt"]


def test_gemini_settings_is_valid_json(build_dir):
    GeminiAdapter(repo_root=REPO_ROOT, provider="google").emit_config(build_dir)
    data = json.loads((build_dir / "settings.json").read_text(encoding="utf-8"))
    assert data["provider"] == "google"
    assert data["model"]["name"]


def test_gemini_agents_layer_not_applicable(build_dir):
    with pytest.raises(NotImplementedError):
        GeminiAdapter(repo_root=REPO_ROOT).emit_agents(build_dir)


# --------------------------------------------------------------------- #
# Sécurité + CLI                                                        #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("adapter_cls", [CodexAdapter, GeminiAdapter])
def test_emit_commands_never_writes_outside_build(adapter_cls):
    from harness_build import BuildSafetyError

    adapter = adapter_cls(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT, SDD_HOME):
        with pytest.raises(BuildSafetyError):
            adapter.emit_commands(forbidden)


@pytest.mark.parametrize(
    ("harness", "provider", "subdir"),
    [("codex", "moonshot", "prompts"), ("gemini-cli", "google", "commands")],
)
def test_cli_commands_layer_succeeds_for_variants(build_dir, harness, provider, subdir):
    rc = main(
        ["--harness", harness, "--commands-only", "--provider", provider, "--out", str(build_dir)]
    )
    assert rc == 0
    assert len(list((build_dir / subdir).glob("*"))) == N_COMMANDS


@pytest.mark.parametrize("harness", ["codex", "gemini-cli"])
def test_cli_agents_layer_still_refused_for_variants(build_dir, harness):
    """Régression : la couche agents reste refusée (rc=2) pour codex/gemini."""
    rc = main(["--harness", harness, "--agents-only", "--out", str(build_dir)])
    assert rc == 2


# --------------------------------------------------------------------- #
# Régression #4 — gate UNTESTED au --deploy                             #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("harness", ["codex", "gemini-cli"])
def test_deploy_untested_combo_refused_without_env(build_dir, monkeypatch, harness):
    """--deploy d'un combo untested (codex/gemini) est refusé (rc=2) sans l'env var.

    Le refus intervient AVANT _deploy_facade → la façade racine n'est jamais
    touchée par ce test (rc=2 retourné après émission dans build_dir seulement).
    """
    monkeypatch.delenv("SDD_ALLOW_UNTESTED_HARNESS", raising=False)
    rc = main(["--harness", harness, "--commands-only", "--out", str(build_dir), "--deploy"])
    assert rc == 2


# --------------------------------------------------------------------- #
# Régression #7 — échappement $1..$9 littéraux pour Codex               #
# --------------------------------------------------------------------- #


def test_escape_codex_positionals_unit():
    """$1..$9 → $$N ; $ARGUMENTS/$0/${..}/lettres/$$ préexistant intacts."""
    assert _escape_codex_positionals("awk '{print $2}'") == "awk '{print $$2}'"
    assert _escape_codex_positionals("default $50") == "default $$50"
    assert _escape_codex_positionals("cap $15 usd") == "cap $$15 usd"
    # Non substituables par Codex → jamais touchés :
    assert _escape_codex_positionals("$ARGUMENTS") == "$ARGUMENTS"
    assert _escape_codex_positionals("awk '{print $NF}'") == "awk '{print $NF}'"
    assert _escape_codex_positionals("${PORT} $PORT $0") == "${PORT} $PORT $0"
    # Idempotent (n'ajoute pas un 3e $ à un $$ déjà présent) :
    assert _escape_codex_positionals(_escape_codex_positionals("$5")) == "$$5"


def test_codex_prompt_escapes_literal_dollars_but_keeps_arguments(build_dir):
    """Le prompt Codex émis n'a plus de $<chiffre> nu, et garde $ARGUMENTS vivant."""
    CodexAdapter(repo_root=REPO_ROOT, provider="moonshot").emit_commands(build_dir)
    text = (build_dir / "prompts" / "sdd-kill-server.md").read_text(encoding="utf-8")
    # $ARGUMENTS injecté reste une vraie substitution (une seule fois, non doublé).
    assert "Arguments: $ARGUMENTS" in text
    assert "$$ARGUMENTS" not in text
    # Champs awk incidents échappés (Codex rendra le littéral $5).
    assert "awk '{print $$5}'" in text
    # Plus aucun $<1-9> nu (précédé d'un caractère non-$) dans le corps.
    assert re.search(r"(?<!\$)\$[1-9]", text) is None


# --------------------------------------------------------------------- #
# Régression #1 — rewrite @.claude/ vers .sdd/ SEULEMENT si la cible existe #
# --------------------------------------------------------------------- #


def test_rewrite_at_includes_only_when_target_exists():
    """@.claude/X → .sdd/X si .sdd/X existe, sinon .claude/X (jamais un .sdd/ mort)."""
    adapter = CodexAdapter(repo_root=REPO_ROOT, provider="moonshot")
    # .sdd/loader.yml existe → réécrit vers le foyer.
    assert adapter._rewrite_at_includes("voir @.sdd/loader.yml") == "voir .sdd/loader.yml"
    # .sdd/rules/ n'est PAS matérialisé → repli .claude/ résolvable (pas .sdd/ mort).
    got = adapter._rewrite_at_includes("charge @.sdd/rules/output-protocol.md")
    assert got == "charge .sdd/rules/output-protocol.md"
    # Le `@` est toujours retiré, jamais conservé.
    assert "@.claude" not in got


def test_no_dead_sdd_refs_in_emitted_commands(build_dir):
    """Aucune façade émise ne doit contenir un chemin repo .sdd/<x> inexistant."""
    CodexAdapter(repo_root=REPO_ROOT, provider="moonshot").emit_commands(build_dir)
    dead: list[str] = []
    for md in (build_dir / "prompts").glob("*.md"):
        text = md.read_text(encoding="utf-8")
        # refs .sdd/ NON précédées de ~ (exclut ~/.sdd home) et non-ellipse.
        for m in re.finditer(r"(?<!~/)(?<![\w~])\.sdd/([A-Za-z0-9_][A-Za-z0-9_./{},-]*)", text):
            rel = m.group(1)
            if "{" in rel or rel.startswith("..."):
                continue  # brace-expansion / ellipse descriptive
            if not (SDD_HOME / rel).exists():
                dead.append(f"{md.name}: .sdd/{rel}")
    assert not dead, f"refs .sdd/ mortes émises : {sorted(set(dead))}"


@pytest.mark.parametrize("adapter_cls", [CodexAdapter, GeminiAdapter])
def test_memory_variant_filters_claude_only_tools(adapter_cls):
    """R9 audit — MemoryVariantAdapter retire les tools Claude-Code-only.

    Sous Codex/Gemini, `Skill` et `AskUserQuestion` n'existent pas au runtime.
    Un agent qui les référence dans son frontmatter lèverait `ToolNotFoundError`
    au spawn. La base Adapter les garde (Claude) ; MemoryVariantAdapter les
    filtre. Vérifié à l'émission Phase 3+ (`emit_agents`) mais le filtre est
    déjà en place sur la base class."""
    adapter = adapter_cls(repo_root=REPO_ROOT, provider="moonshot")
    filtered = adapter._filter_tools_for_harness(
        ["Read", "Write", "Edit", "Skill", "AskUserQuestion", "Bash"]
    )
    assert "Skill" not in filtered
    assert "AskUserQuestion" not in filtered
    assert filtered == ["Read", "Write", "Edit", "Bash"]


def test_claude_adapter_keeps_all_tools():
    """R9 audit — ClaudeAdapter garde tools=Skill,AskUserQuestion (natifs)."""
    from harness_build import ClaudeAdapter  # local import (test-only)
    adapter = ClaudeAdapter(repo_root=REPO_ROOT, provider="anthropic")
    tools = ["Read", "Write", "Skill", "AskUserQuestion", "Bash"]
    assert adapter._filter_tools_for_harness(tools) == tools
