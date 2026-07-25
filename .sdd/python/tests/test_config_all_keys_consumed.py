"""test_config_all_keys_consumed.py — anti-atrophie config (audit 2026-06-11).

`docs/configuration-reference.md` déclare ~48 clés Project Config. Sans gate,
une clé peut rester documentée alors que plus aucun consommateur ne la lit
(orphan key) — l'utilisateur la règle, rien ne change, confiance perdue.

Ce test parse la table de référence et vérifie que chaque clé apparaît dans
au moins UN consommateur réel :
  - code Python (`.sdd/python/sdd_{lib,scripts,admin,hooks}/`), OU
  - un prompt commande/agent/règle (`.sdd/{commands,agents,rules}/*.md`)
    — les clés lues par `read_layered_config()` au fil d'un flow LLM sont
    des consommateurs légitimes dans ce framework, OU
  - le schéma machine (`templates/project-config.schema.json`).

Une clé absente PARTOUT = orpheline → FAIL avec guidance (retirer de la doc
ou câbler un consommateur). Allowlist explicite pour les exceptions assumées.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from sdd_lib.paths import repo_root, sdd_home

pytestmark = pytest.mark.smoke

_KEY_ROW_RE = re.compile(r"^\|\s*`([A-Za-z][A-Za-z0-9_.:]*)`\s*\|", re.MULTILINE)

#: Clés documentées dont l'absence de consommateur est ASSUMÉE et tracée.
#: Toute entrée ici doit citer sa raison — sinon retirer la clé de la doc.
_ALLOWED_DOC_ONLY: dict[str, str] = {
    # (vide à la création 2026-06-11 — la table était 100 % consommée)
}


def _reference_keys() -> list[str]:
    from sdd_lib.paths import docs_dir as _docs_dir
    doc = _docs_dir(repo_root()) / "configuration-reference.md"
    text = doc.read_text(encoding="utf-8", errors="replace")
    keys = _KEY_ROW_RE.findall(text)
    assert keys, "configuration-reference.md key table not parseable (format drift?)"
    return sorted(set(keys))


def _consumer_corpus() -> str:
    """Concatène tous les consommateurs potentiels (Python + prompts + schéma).

    Le foyer neutre `.sdd/` est SSoT depuis v7.0.2 (migration
    `refactor/sdd-move-common`). `.claude/` reste scanné en fallback
    transitionnel pour capter les artefacts régénérés (façades) qui
    peuvent contenir des mentions de clés côté harnais Claude.
    """
    home = sdd_home()
    chunks: list[str] = []
    for pattern in (
        "python/sdd_lib/**/*.py",
        "python/sdd_scripts/**/*.py",
        "python/sdd_admin/**/*.py",
        "python/sdd_hooks/**/*.py",
        "commands/*.md",
        "agents/*.md",
        "rules/*.md",
        "templates/project-config.schema.json",
        "templates/*.template.md",
        "config.base.yml",
    ):
        for f in home.glob(pattern):
            try:
                chunks.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(chunks)


def test_reference_table_has_expected_volume():
    keys = _reference_keys()
    assert len(keys) >= 40, (
        f"only {len(keys)} keys parsed — la table de configuration-reference.md "
        f"a probablement changé de format, adapter _KEY_ROW_RE"
    )


def test_all_documented_keys_have_a_consumer():
    keys = _reference_keys()
    corpus = _consumer_corpus()
    orphans = [
        k for k in keys
        if k not in _ALLOWED_DOC_ONLY and k not in corpus
    ]
    assert not orphans, (
        "Orphan config keys — documentées dans configuration-reference.md mais "
        f"consommées nulle part (python/commands/agents/rules/schéma) : {orphans}\n"
        "Fix : (1) retirer la clé de la doc, (2) câbler son consommateur, ou "
        "(3) l'ajouter à _ALLOWED_DOC_ONLY avec une raison tracée."
    )


def test_allowlist_entries_are_still_documented():
    """Une entrée d'allowlist qui n'est plus documentée = résidu à purger."""
    keys = set(_reference_keys())
    stale = [k for k in _ALLOWED_DOC_ONLY if k not in keys]
    assert not stale, f"allowlist entries no longer in the reference doc: {stale}"
