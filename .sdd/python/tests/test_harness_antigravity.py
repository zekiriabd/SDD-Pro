"""Tests de la façade Antigravity (transpilation commandes + config).

Vérifie que l'adaptateur AntigravityAdapter émet une couche COMMANDES complète
(slash-commands transpilées) + le fichier de config du harnais (settings.json),
bien formés (TOML/JSON valides), corps métier préservé (@-includes réécrits),
le tout SOUS `.sdd/.build/` uniquement.

Token-free (pure transpilation) ; écrit uniquement sous .sdd/.build/ (nettoyé).
"""

from __future__ import annotations

import json
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
    AntigravityAdapter,
    BuildSafetyError,
    main,
)

N_COMMANDS = len(list((SDD_HOME / "commands").glob("*.md")))


@pytest.fixture()
def build_dir():
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-ag-", dir=build_root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


def test_antigravity_emits_all_toml_commands_and_settings(build_dir):
    results = AntigravityAdapter(repo_root=REPO_ROOT, provider="google").emit_commands(build_dir)
    skipped = {r.agent: r.skipped_reason for r in results if not r.ok}
    assert not skipped, f"skips: {skipped}"
    tomls = list((build_dir / "commands").glob("*.toml"))
    assert len(tomls) == N_COMMANDS
    assert (build_dir / "settings.json").is_file()


def test_antigravity_every_command_is_valid_toml(build_dir):
    AntigravityAdapter(repo_root=REPO_ROOT).emit_commands(build_dir)
    for f in (build_dir / "commands").glob("*.toml"):
        data = tomllib.loads(f.read_text(encoding="utf-8"))
        assert "description" in data and "prompt" in data
        assert "{{args}}" in data["prompt"]
        assert "@.claude" not in data["prompt"]


def test_antigravity_settings_is_valid_json(build_dir):
    AntigravityAdapter(repo_root=REPO_ROOT, provider="google").emit_config(build_dir)
    data = json.loads((build_dir / "settings.json").read_text(encoding="utf-8"))
    assert data["harness"] == "antigravity"
    assert data["provider"] == "google"
    assert data["model"]["name"] == "gemini-2.5-flash"


def test_antigravity_agents_layer_not_applicable(build_dir):
    with pytest.raises(NotImplementedError):
        AntigravityAdapter(repo_root=REPO_ROOT).emit_agents(build_dir)


def test_antigravity_never_writes_outside_build():
    adapter = AntigravityAdapter(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT, SDD_HOME):
        with pytest.raises(BuildSafetyError):
            adapter.emit_commands(forbidden)


def test_cli_commands_layer_succeeds_for_antigravity(build_dir):
    rc = main(
        ["--harness", "antigravity", "--commands-only", "--provider", "google", "--out", str(build_dir)]
    )
    assert rc == 0
    assert len(list((build_dir / "commands").glob("*"))) == N_COMMANDS
