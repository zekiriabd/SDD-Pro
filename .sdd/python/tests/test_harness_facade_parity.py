"""Parité des façades COMMITÉES avec le foyer neutre (audit 2026-08-28).

Trou trouvé en régénérant les façades après une édition de commande : six
fichiers de `.codex/prompts/` et l'ensemble de `.gemini/commands/` ont changé
alors qu'une seule commande avait été touchée. La régénération n'introduisait
pas de bug — elle **corrigeait une dérive préexistante**. Exemple mesuré :

    .codex/prompts/sdd-full.md
    -  PHASE 2.6 — Readiness gate (PowerShell déterministe v6, …)
    +  PHASE 2.6 — Readiness gate (Python déterministe v6, …)

La façade Codex décrivait encore un enforcer PowerShell remplacé par du Python
depuis plusieurs versions.

Pourquoi rien ne l'avait vu
---------------------------

`INVARIANTS.yml` déclare l'invariant `harness-parity` : « les façades
`.claude/`, `.codex/`, `.gemini/` = régénérations byte-identiques de `.sdd/`
HEAD ». Mais `test_harness_identity_commands.py` compare les **pivots** aux
commandes vivantes de `.claude/commands/` uniquement — les deux autres façades
n'étaient confrontées à rien. L'invariant existait, son enforcer ne couvrait
qu'un tiers de son périmètre.

C'est exactement le motif que le manifeste d'invariants existe pour empêcher :
un contrat déclaré, un enforcer nommé, et une couverture réelle plus étroite
que l'énoncé. Un invariant partiellement vérifié se comporte comme un
invariant non vérifié sur la partie qu'il ne couvre pas.

Ce que ce test vérifie
---------------------

Pour chaque harnais, il régénère la façade dans un répertoire temporaire et la
compare, fichier par fichier, à celle qui est committée. Comparaison
**normalisée sur les fins de ligne** : `.gitattributes` impose CRLF au dépôt
tandis que le transpileur écrit en LF, et un test qui échouerait sur ce seul
motif serait ignoré au bout de deux exécutions — donc inutile.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

from sdd_lib.paths import repo_root  # noqa: E402


#: harnais -> (sous-répertoire de sortie du build, sous-répertoire de la façade)
_HARNESSES = {
    "codex": ("prompts", Path(".codex") / "prompts"),
    "gemini-cli": ("commands", Path(".gemini") / "commands"),
}


def _norm(p: Path) -> str:
    """Contenu normalisé : fins de ligne unifiées, espaces de fin retirés."""
    raw = p.read_text(encoding="utf-8", errors="replace")
    return raw.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _build(harness: str, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(repo_root() / ".sdd" / "harness_build.py"),
         "--harness", harness, "--provider", "anthropic",
         "--out", str(out), "--commands-only", "--memory-only"],
        capture_output=True, text=True, timeout=300, cwd=str(repo_root()),
    )


@pytest.mark.parametrize("harness", sorted(_HARNESSES))
def test_committed_facade_matches_a_fresh_build(harness):
    """La façade committée est-elle bien la régénération du foyer neutre ?

    Le build n'écrit que sous `.sdd/.build/` (garde du transpileur), donc la
    sortie est comparée depuis là plutôt que depuis un tmp_path.
    """
    root = repo_root()
    sub, facade_rel = _HARNESSES[harness]
    out = root / ".sdd" / ".build" / f"parity-test-{harness}"
    proc = _build(harness, out)
    assert proc.returncode == 0, (
        f"harness_build {harness} a échoué :\n{proc.stdout}\n{proc.stderr}")

    built_dir, facade_dir = out / sub, root / facade_rel
    if not built_dir.is_dir():
        pytest.skip(f"{harness} : aucune sortie sous {sub}/")
    assert facade_dir.is_dir(), f"façade absente : {facade_rel}"

    built = {p.name: p for p in built_dir.iterdir() if p.is_file()}
    committed = {p.name: p for p in facade_dir.iterdir() if p.is_file()}

    missing = sorted(set(built) - set(committed))
    assert not missing, (
        f"{harness} : {len(missing)} fichier(s) produits par le build et absents "
        f"de la façade committée : {missing[:8]}")

    drifted = [name for name in sorted(built)
               if _norm(built[name]) != _norm(committed[name])]
    assert not drifted, (
        f"{harness} : {len(drifted)} fichier(s) de la façade ont dérivé du foyer "
        f"neutre : {drifted[:8]}. Régénérer :\n"
        f"  python .sdd/harness_build.py --harness {harness} --provider anthropic "
        f"--out .sdd/.build/{harness} --commands-only --memory-only\n"
        f"puis recopier la sortie dans {facade_rel}/")


def test_claude_facade_matches_a_fresh_build():
    """Même contrôle pour la façade de référence — agents, commandes et rules.

    Elle était déjà couverte indirectement (les pivots sont comparés aux
    commandes vivantes), mais pas par une comparaison directe build ↔ committé,
    et rien ne couvrait les agents ni les rules.
    """
    root = repo_root()
    out = root / ".sdd" / ".build" / "parity-test-claude"
    proc = subprocess.run(
        [sys.executable, str(root / ".sdd" / "harness_build.py"),
         "--harness", "claude-code", "--provider", "anthropic",
         "--out", str(out), "--agents-only", "--commands-only",
         "--memory-only", "--rules-only"],
        capture_output=True, text=True, timeout=300, cwd=str(root))
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    drifted: list[str] = []
    for sub in ("agents", "commands", "rules"):
        built_dir, facade_dir = out / sub, root / ".claude" / sub
        if not built_dir.is_dir() or not facade_dir.is_dir():
            continue
        for p in built_dir.iterdir():
            if not p.is_file():
                continue
            live = facade_dir / p.name
            if not live.is_file() or _norm(p) != _norm(live):
                drifted.append(f"{sub}/{p.name}")
    assert not drifted, (
        f"{len(drifted)} fichier(s) de .claude/ ont dérivé du foyer neutre : "
        f"{drifted[:10]}. Régénérer avec harness_build.py puis recopier.")
