"""Tests de la couche FICHIERS-MÉMOIRE (Phase 2 multi-harness).

(a) ROUND-TRIP identité — `ClaudeAdapter.emit_memory_file` régénère
    `CLAUDE.md` sous un temp SOUS `.sdd/.build/` depuis le pivot
    `.sdd/entrypoint.md` (`body_source: .sdd/entrypoint-body.md`, lecture
    seule) ; le corps régénéré DOIT être identique au vivant après
    normalisation CRLF/BOM.
(b) VARIANTES — `CodexAdapter` -> `AGENTS.md`, `GeminiAdapter` ->
    `GEMINI.md` : en-tête `# GENERATED FROM .sdd/ — DO NOT EDIT`
    présent, note protection_level (capability-matrix.yml) présente,
    AUCUN `@.claude/` résiduel (refs réécrites `.sdd/...`), non-vacuité.

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

from harness_build import (  # noqa: E402
    BuildSafetyError,
    ClaudeAdapter,
    CodexAdapter,
    GeminiAdapter,
    main,
)
from sdd_lib.harness_diff import parse_frontmatter  # noqa: E402

LIVE_MEMORY = REPO_ROOT / ".claude" / "CLAUDE.md"
PIVOT = SDD_HOME / "entrypoint.md"

GENERATED_HEADER = "# GENERATED FROM .sdd/ — DO NOT EDIT"


def _normalize(text: str) -> str:
    """BOM retiré + CRLF/CR -> LF (même contrat que harness_diff)."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


@pytest.fixture()
def build_dir():
    """Dossier temp jetable SOUS .sdd/.build/ (jamais .claude/)."""
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-memory-", dir=build_root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------------- #
# Pivot .sdd/entrypoint.md                                              #
# --------------------------------------------------------------------- #


def test_entrypoint_pivot_points_to_live_memory():
    """Le pivot déclare body_source = .sdd/entrypoint-body.md + compte des @-refs."""
    assert PIVOT.is_file(), "pivot .sdd/entrypoint.md absent"
    fields, _body = parse_frontmatter(PIVOT.read_text(encoding="utf-8-sig"))
    assert fields.get("schema") == "sdd.memory/v1"
    assert fields.get("body_source") == ".sdd/entrypoint-body.md"
    assert int(fields.get("at_includes_total", 0)) > 0
    assert int(fields.get("at_includes_unique", 0)) > 0


# --------------------------------------------------------------------- #
# (a) Round-trip CLAUDE.md                                              #
# --------------------------------------------------------------------- #


def test_claude_memory_roundtrip_identity(build_dir):
    """CLAUDE.md régénéré == vivant (post-normalisation CRLF/BOM)."""
    target = ClaudeAdapter(repo_root=REPO_ROOT).emit_memory_file(build_dir)
    assert target == build_dir / "CLAUDE.md"
    assert target.is_file()
    generated = _normalize(target.read_text(encoding="utf-8-sig"))
    live = _normalize(LIVE_MEMORY.read_text(encoding="utf-8-sig"))
    assert generated == live, "round-trip mémoire non identique au vivant"


# --------------------------------------------------------------------- #
# (b) Variantes AGENTS.md (codex) + GEMINI.md (gemini-cli)              #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("adapter_cls", "filename", "matrix_key"),
    [(CodexAdapter, "AGENTS.md", "codex"), (GeminiAdapter, "GEMINI.md", "gemini-cli")],
)
def test_memory_variants_generated(build_dir, adapter_cls, filename, matrix_key):
    """Variante : en-tête GENERATED, note protection, 0 `@.claude/`, non vide."""
    target = adapter_cls(repo_root=REPO_ROOT).emit_memory_file(build_dir)
    assert target == build_dir / filename
    content = target.read_text(encoding="utf-8")
    # Non-vacuité : le corps métier complet est embarqué (>> en-tête seul).
    assert len(content) > 5000, f"{filename}: contenu suspicieusement court"
    assert content.startswith(GENERATED_HEADER)
    assert f"Harness: {matrix_key}" in content
    assert "protection_level: B" in content
    # Réécriture des lazy-includes : plus AUCUNE ref `@.claude` résiduelle.
    assert "@.claude" not in content, f"{filename}: ref @.claude résiduelle"
    assert ".sdd/docs/" in content, f"{filename}: réécriture .sdd/ absente"
    # Le corps métier est bien celui de l'entry point vivant.
    assert "SDD_Pro v7.0.0 GA" in content


def test_variants_do_not_rewrite_plain_claude_paths(build_dir):
    """Les mentions littérales `.claude/...` sans `@` restent intactes."""
    live = _normalize(LIVE_MEMORY.read_text(encoding="utf-8-sig"))
    assert ".sdd/rules/" in live.replace("@.claude/", "")  # précondition
    target = CodexAdapter(repo_root=REPO_ROOT).emit_memory_file(build_dir)
    assert ".sdd/rules/" in target.read_text(encoding="utf-8")


# --------------------------------------------------------------------- #
# Sécurité + CLI                                                        #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("adapter_cls", [ClaudeAdapter, CodexAdapter, GeminiAdapter])
def test_emit_memory_never_writes_outside_sdd_build(adapter_cls):
    """Garde-fou : toute sortie hors .sdd/.build/ est refusée."""
    adapter = adapter_cls(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT, SDD_HOME):
        with pytest.raises(BuildSafetyError):
            adapter.emit_memory_file(forbidden)


def test_cli_memory_only_all_harnesses(build_dir):
    """`--memory-only` produit le bon fichier pour chacun des 3 harnais."""
    for harness, filename in (
        ("claude-code", "CLAUDE.md"),
        ("codex", "AGENTS.md"),
        ("gemini-cli", "GEMINI.md"),
    ):
        out = build_dir / harness
        rc = main(["--harness", harness, "--memory-only", "--out", str(out)])
        assert rc == 0, f"{harness}: CLI --memory-only rc={rc}"
        assert (out / filename).is_file()


def test_cli_agents_layer_refused_for_variant_harnesses(build_dir):
    """codex/gemini-cli : couches agents/commandes non transpilées -> rc=2."""
    for harness in ("codex", "gemini-cli"):
        rc = main(["--harness", harness, "--agents-only", "--out", str(build_dir / harness)])
        assert rc == 2, f"{harness}: --agents-only devrait être refusé (rc=2)"
