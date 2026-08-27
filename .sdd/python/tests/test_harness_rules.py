"""Tests de la couche RULES (Phase 2 multi-harness — surface identité Claude).

(a) MANIFEST — `.sdd/rules-manifest.yaml` liste les 12 rules vivantes, chaque
    entrée porte `name` + `body_source` (-> `.sdd/rules/*.md` existant) +
    `scope` (universal|path-scoped). Aucune rule vivante orpheline.
(b) ROUND-TRIP identité — `ClaudeAdapter.emit_rules` régénère chaque rule sous
    un temp SOUS `.sdd/.build/` ; le contenu régénéré DOIT être byte-identique
    au vivant (post-normalisation CRLF/BOM), pour les 12 rules.
(c) VARIANTES — Codex/Gemini : `emit_rules` lève NotImplementedError (pas de
    mécanisme path-scoped ; inline universelles + pointeurs — non câblé).
(d) SÉCURITÉ + CLI — sortie confinée à .sdd/.build/ ; `--rules-only`.

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
    _load_rules_manifest,
    main,
)

# Bi-racine 2026-07-25 : rules migrées vers .sdd/rules/.
LIVE_RULES_DIR = SDD_HOME / "rules"
MANIFEST = SDD_HOME / "rules-manifest.yaml"
VALID_SCOPES = {"universal", "path-scoped"}


def _normalize(text: str) -> str:
    """BOM retiré + CRLF/CR -> LF (même contrat que harness_diff)."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


@pytest.fixture()
def build_dir():
    """Dossier temp jetable SOUS .sdd/.build/ (jamais .claude/)."""
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-rules-", dir=build_root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


# --------------------------------------------------------------------- #
# (a) Manifest                                                          #
# --------------------------------------------------------------------- #


def test_manifest_present_and_wellformed():
    assert MANIFEST.is_file(), "manifest .sdd/rules-manifest.yaml absent"
    rules = _load_rules_manifest(SDD_HOME)
    # +1 le 2026-08-26 : db-reverse-tsql (socle SQL partage des 5 agents db-reverse).
    assert len(rules) == 12, f"attendu 12 rules, trouvé {len(rules)}"
    for entry in rules:
        assert entry["name"], "entrée sans name"
        assert entry["scope"] in VALID_SCOPES, f"scope invalide: {entry.get('scope')}"
        src = (REPO_ROOT / entry["body_source"]).resolve()
        assert src.is_file(), f"body_source introuvable: {src}"


def test_manifest_covers_every_live_rule():
    """Aucune rule vivante orpheline (parité manifest <-> .sdd/rules/)."""
    live = {p.stem for p in LIVE_RULES_DIR.glob("*.md")}
    manifested = {e["name"] for e in _load_rules_manifest(SDD_HOME)}
    assert manifested == live, (
        f"drift manifest<->vivant — manquantes: {live - manifested} ; "
        f"en trop: {manifested - live}"
    )


def test_manifest_scope_counts():
    """2 universelles (error-classification, output-protocol) + 9 path-scoped."""
    rules = _load_rules_manifest(SDD_HOME)
    universal = {e["name"] for e in rules if e["scope"] == "universal"}
    assert universal == {"error-classification", "output-protocol"}
    assert sum(1 for e in rules if e["scope"] == "path-scoped") == 10


# --------------------------------------------------------------------- #
# (b) Round-trip identité                                              #
# --------------------------------------------------------------------- #


def test_claude_rules_roundtrip_identity(build_dir):
    """Les 12 rules régénérées == vivant (post-normalisation CRLF/BOM)."""
    results = ClaudeAdapter(repo_root=REPO_ROOT).emit_rules(build_dir)
    assert len(results) == 12
    assert all(r.ok for r in results), [r.skipped_reason for r in results if not r.ok]
    for result in results:
        generated = _normalize(result.written.read_text(encoding="utf-8-sig"))
        live = _normalize((LIVE_RULES_DIR / f"{result.agent}.md").read_text(encoding="utf-8-sig"))
        assert generated == live, f"round-trip rule {result.agent!r} non identique au vivant"


def test_emit_rules_only_subset(build_dir):
    results = ClaudeAdapter(repo_root=REPO_ROOT).emit_rules(build_dir, only={"output-protocol"})
    assert len(results) == 1
    assert results[0].agent == "output-protocol"
    assert results[0].ok


# --------------------------------------------------------------------- #
# (c) Variantes — non câblées                                          #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("adapter_cls", [CodexAdapter, GeminiAdapter])
def test_variant_rules_not_implemented(build_dir, adapter_cls):
    with pytest.raises(NotImplementedError):
        adapter_cls(repo_root=REPO_ROOT).emit_rules(build_dir)


# --------------------------------------------------------------------- #
# (d) Sécurité + CLI                                                   #
# --------------------------------------------------------------------- #


def test_emit_rules_never_writes_outside_sdd_build():
    adapter = ClaudeAdapter(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT, SDD_HOME):
        with pytest.raises(BuildSafetyError):
            adapter.emit_rules(forbidden)


def test_cli_rules_only(build_dir):
    rc = main(["--harness", "claude-code", "--rules-only", "--out", str(build_dir)])
    assert rc == 0
    assert (build_dir / "rules" / "output-protocol.md").is_file()
    assert len(list((build_dir / "rules").glob("*.md"))) == 12


def test_cli_rules_layer_refused_for_variant_harnesses(build_dir):
    for harness in ("codex", "gemini-cli"):
        rc = main(["--harness", harness, "--rules-only", "--out", str(build_dir / harness)])
        assert rc == 2, f"{harness}: --rules-only devrait être refusé (rc=2)"
