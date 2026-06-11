"""test_gates_map.py — anti-rot du registre des gates (audit M3, 2026-06-11).

`docs/gates-map.md` est l'inventaire SSoT des points de blocage du pipeline
(règle anti-prolifération : 1 domaine = 1 gate primaire, enregistrement
obligatoire). Ce test garantit que le registre ne pourrit pas :

  1. chaque enforcer Python cité (`sdd_{hooks,scripts,admin}/x.py`) existe ;
  2. chaque règle/commande citée (`*.md` sous rules/ ou commands/) existe ;
  3. les enforcers de gates *primaires* câblés en hook existent aussi dans
     settings.json (un enforcer retiré du wiring sans MAJ de la map = FAIL).
"""
from __future__ import annotations

import json
import re

import pytest

from sdd_lib.paths import repo_root

pytestmark = pytest.mark.smoke

_PY_ENFORCER_RE = re.compile(r"`(sdd_(?:hooks|scripts|admin)/[a-z0-9_]+\.py)`")
_MD_REF_RE = re.compile(r"`@?\.claude/(rules|commands|docs)/([a-z0-9-]+\.md)")


def _gates_map_text() -> str:
    p = repo_root() / ".claude" / "docs" / "gates-map.md"
    assert p.is_file(), "docs/gates-map.md absent — registre des gates supprimé ?"
    return p.read_text(encoding="utf-8", errors="replace")


def test_cited_python_enforcers_exist():
    root = repo_root() / ".claude" / "python"
    text = _gates_map_text()
    cited = sorted(set(_PY_ENFORCER_RE.findall(text)))
    assert len(cited) >= 12, f"parsing suspect — seulement {len(cited)} enforcers cités"
    missing = [c for c in cited if not (root / c).is_file()]
    assert not missing, (
        f"gates-map.md cite des enforcers absents du disque : {missing}\n"
        "Fix : corriger le chemin dans la map OU restaurer le script OU "
        "retirer la gate du registre (décision tracée)."
    )


def test_cited_markdown_refs_exist():
    root = repo_root() / ".claude"
    text = _gates_map_text()
    missing = []
    for sub, name in set(_MD_REF_RE.findall(text)):
        if not (root / sub / name).is_file():
            missing.append(f".claude/{sub}/{name}")
    assert not missing, f"gates-map.md cite des fichiers .md absents : {missing}"


def test_hook_enforcers_still_wired_in_settings():
    """Les enforcers hooks de la map §4 doivent rester câblés dans settings.json."""
    root = repo_root()
    settings = json.loads(
        (root / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    wired = json.dumps(settings.get("hooks", {}))
    text = _gates_map_text()
    # Section §4 uniquement (hooks automatiques)
    sec4 = text.split("## 4.")[1].split("## 5.")[0]
    hook_enforcers = sorted(
        {c for c in _PY_ENFORCER_RE.findall(sec4) if c.startswith("sdd_hooks/")}
    )
    assert hook_enforcers, "section §4 de gates-map.md non parseable"
    # settings.json câble les hooks en notation module (`sdd_hooks.x`),
    # sans extension — matcher le stem.
    unwired = [
        h for h in hook_enforcers
        if h.split("/")[-1].removesuffix(".py") not in wired
    ]
    assert not unwired, (
        f"gates §4 déclarées mais hooks non câblés dans settings.json : {unwired}\n"
        "Fix : recâbler le hook OU retirer la gate de la map (décision tracée)."
    )
