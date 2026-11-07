"""Parité des fichiers MÉMOIRE et CONFIG des façades Codex/Gemini (audit 2026-11-07).

Trou trouvé : `.codex/AGENTS.md` et `.gemini/GEMINI.md` annonçaient encore
« 36 stacks » alors que le foyer neutre (`.sdd/entrypoint-body.md`) en
déclare 56 depuis le recount 2026-09-02. `test_harness_facade_parity.py` ne
compare que `.codex/prompts/` et `.gemini/commands/` : il restait vert alors
que la façade décrivait un autre framework que celui du dépôt. Même motif que
l'audit 2026-08-28 — un invariant (`harness-parity`, `severity: critical`)
dont l'enforcer ne couvre qu'une partie de l'énoncé.

Ce test régénère la façade (mémoire + config) sous `.sdd/.build/` — seul
emplacement autorisé par le transpileur — et compare au contenu committé,
octet pour octet après normalisation des fins de ligne (CRLF/CR -> LF, BOM
retiré : `.gitattributes` et l'éditeur peuvent changer l'un ou l'autre sans
changer le sens). L'échec liste TOUS les fichiers en dérive, pas le premier.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

from sdd_lib.paths import repo_root  # noqa: E402

#: harnais -> fichiers mémoire/config produits par le build ET committés
#: (chemin relatif à la sortie du build, chemin relatif à la racine du dépôt).
_FILES = {
    "codex": [
        ("AGENTS.md", Path(".codex") / "AGENTS.md"),
        ("config.toml", Path(".codex") / "config.toml"),
    ],
    "gemini-cli": [
        ("GEMINI.md", Path(".gemini") / "GEMINI.md"),
        ("settings.json", Path(".gemini") / "settings.json"),
    ],
}


def _norm(p: Path) -> str:
    raw = p.read_bytes().decode("utf-8", errors="replace")
    return raw.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _build(harness: str, out: Path) -> subprocess.CompletedProcess:
    # Mêmes flags que la régénération documentée (provider committé : anthropic).
    return subprocess.run(
        [sys.executable, str(repo_root() / ".sdd" / "harness_build.py"),
         "--harness", harness, "--provider", "anthropic",
         "--out", str(out), "--commands-only", "--memory-only"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, cwd=str(repo_root()),
    )


@pytest.fixture()
def build_root():
    root = repo_root() / ".sdd" / ".build"
    root.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-memory-parity-", dir=root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


def test_committed_memory_and_config_match_a_fresh_build(build_root):
    root = repo_root()
    drift: list[str] = []
    for harness, files in sorted(_FILES.items()):
        out = build_root / harness
        proc = _build(harness, out)
        assert proc.returncode == 0, (
            f"harness_build {harness} a échoué :\n{proc.stdout}\n{proc.stderr}")
        for built_rel, committed_rel in files:
            built, committed = out / built_rel, root / committed_rel
            if not built.is_file():
                drift.append(f"{committed_rel.as_posix()} : non produit par le build ({harness})")
            elif not committed.is_file():
                drift.append(f"{committed_rel.as_posix()} : absent de la façade committée")
            elif _norm(built) != _norm(committed):
                drift.append(f"{committed_rel.as_posix()} : contenu dérivé du foyer neutre")
    assert not drift, (
        f"{len(drift)} fichier(s) mémoire/config de façade en dérive :\n  - "
        + "\n  - ".join(drift)
        + "\nRégénérer (sortie sous .sdd/.build/ puis copie dans .codex/ / .gemini/) :\n"
        "  python .sdd/harness_build.py --harness codex --provider anthropic "
        "--out .sdd/.build/codex --commands-only --memory-only\n"
        "  python .sdd/harness_build.py --harness gemini-cli --provider anthropic "
        "--out .sdd/.build/gemini --commands-only --memory-only"
    )
