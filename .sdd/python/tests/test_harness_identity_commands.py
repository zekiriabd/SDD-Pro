"""Test de ROUND-TRIP identité — couche COMMANDES (Phase 2 multi-harness).

Pour chacune des 40 commandes (pivots `.sdd/commands/*.cmd.yaml`), régénère
le `.md` Claude Code via `ClaudeAdapter.emit_commands` dans un dossier
temporaire SOUS `.sdd/.build/` (jamais `.claude/`), puis vérifie l'ÉGALITÉ
SÉMANTIQUE avec le `.claude/commands/{name}.md` vivant :

- **Commandes AVEC frontmatter** (18 : les `sdd-reverse-*` + `sdd-db-reverse*`,
  champs {command, phase, description, loader}) — frontmatter comparé par
  VALEUR via `sdd_lib.harness_diff.diff_agent_texts` (parser loose, champs
  dynamiques = clés du pivot) + corps identique après normalisation CRLF/BOM.
  Les valeurs sont stockées RAW dans le pivot (guillemets préservés, ex.
  `phase: "0-5"`) — le parser loose voit la MÊME forme des deux côtés.
- **Commandes SANS frontmatter** (22, corps pur — dont `sdd-full` et
  `spec-book` qui ouvrent sur un commentaire `@llm-only-flags-file`) —
  marquées `has_frontmatter: false` dans le pivot ; l'émission est un miroir
  normalisé du vivant, comparé texte à texte après normalisation CRLF/BOM.

ÉCART CONNU byte-identité vs sémantique (accepté, même contrat que les agents) :
- CRLF vs LF et BOM éventuel (normalisés des deux côtés) ;
- ordre des clés frontmatter = ordre du pivot (fidèle au vivant à la
  génération 2026-07-24) ;
- les commentaires PLEINE LIGNE à l'intérieur d'un frontmatter vivant
  seraient perdus (aucune des 40 commandes n'en porte à ce jour).
Aucun skip motivé au moment de la génération : 40/40 attendus identiques.
Si un écart apparaît (drift du vivant), le test échoue avec le taux mesuré
et le détail par commande — on documente/regénère le pivot, on ne bricole
JAMAIS `.claude/`.

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

from harness_build import BuildSafetyError, ClaudeAdapter  # noqa: E402
from sdd_lib.config_loader import load_yaml  # noqa: E402
from sdd_lib.harness_diff import DiffReport, diff_agent_texts  # noqa: E402

LIVE_COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
PIVOTS_DIR = SDD_HOME / "commands"

COMMANDS = sorted(p.name.replace(".md", "") for p in PIVOTS_DIR.glob("*.md"))


def _normalize(text: str) -> str:
    """BOM retiré + CRLF/CR -> LF (même contrat que harness_diff)."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _diff_command(generated: Path, live: Path, pivot: dict) -> DiffReport:
    """Diff sémantique d'UNE commande, selon présence de frontmatter."""
    generated_text = generated.read_text(encoding="utf-8-sig")
    live_text = live.read_text(encoding="utf-8-sig")
    if pivot.get("has_frontmatter"):
        # Champs dynamiques = clés du frontmatter pivot (command/phase/...).
        fields = tuple(pivot.get("frontmatter", {}).keys())
        return diff_agent_texts(
            generated_text,
            live_text,
            generated_path=str(generated),
            live_path=str(live),
            fields=fields,
        )
    # Corps pur : comparaison texte-à-texte normalisée (pas de frontmatter).
    report = DiffReport(generated_path=str(generated), live_path=str(live))
    gen_norm, live_norm = _normalize(generated_text), _normalize(live_text)
    if gen_norm != live_norm:
        report.body_identical = False
        for index, (g, l) in enumerate(
            zip(gen_norm.split("\n"), live_norm.split("\n")), start=1
        ):
            if g != l:
                report.body_first_divergence = f"ligne {index}: généré={g!r} vs vivant={l!r}"
                break
        else:
            report.body_first_divergence = "longueurs différentes"
    return report


def test_command_pivot_count_is_40():
    """Verrou de périmètre : la couche commandes compte exactement 40 pivots."""
    assert len(COMMANDS) == 41, f"attendu 41 pivots commande, trouvé {len(COMMANDS)}"
    live = sorted(p.stem for p in LIVE_COMMANDS_DIR.glob("*.md"))
    assert COMMANDS == live, "pivots .cmd.yaml != commandes vivantes .claude/commands/"


def test_frontmatter_split_is_19_with_22_without():
    """Verrou de forme : 19 commandes avec frontmatter, 22 corps pur.

    +1 le 2026-08-26 : /sdd-db-context (Phase 0 du reverse base de donnees)
    porte une description, comme les autres commandes db-reverse.

    Post-consolidation 2026-07-25 : les pivots vivent dans le frontmatter YAML
    du `.md` unique (fusionné avec le body). `_pivot_from_md` retourne un dict
    équivalent à l'ancien `.cmd.yaml` (contient `has_frontmatter`).
    """
    with_fm = [c for c in COMMANDS if _pivot_from_md(c).get("has_frontmatter")]
    assert len(with_fm) == 19, f"attendu 19 pivots has_frontmatter=true, trouvé {with_fm}"


@pytest.fixture(scope="module")
def build_dir():
    """Régénère les 40 commandes dans un temp SOUS .sdd/.build/ (jetable)."""
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-identity-cmd-", dir=build_root))
    results = ClaudeAdapter(repo_root=REPO_ROOT).emit_commands(out)
    skipped = {r.agent: r.skipped_reason for r in results if not r.ok}
    assert not skipped, f"émission incomplète (skips motivés): {skipped}"
    assert len(results) == len(COMMANDS)
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _pivot_from_md(command: str) -> dict:
    """Extract frontmatter from consolidated `.sdd/commands/{cmd}.md`.

    Format post-consolidation 2026-07-25 : le pivot vit dans le frontmatter
    YAML du .md unique (fusionné avec le body). `has_frontmatter` est
    déduit de la présence des clés (command/phase/description = commande
    reverse avec frontmatter, sinon corps pur).
    """
    import re
    text = (PIVOTS_DIR / f"{command}.md").read_text(encoding="utf-8-sig")
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not m:
        return {"has_frontmatter": False}
    try:
        import yaml
        fm = yaml.safe_load(m.group(1)) or {}
    except ImportError:
        fm = {}
    # Emit-frontmatter for the target file iff we have command/phase (reverse)
    # or the classical name/description keys.
    has_fm = bool(fm.get("command") or fm.get("phase"))
    return {"has_frontmatter": has_fm, "frontmatter": fm if has_fm else {}}


@pytest.mark.parametrize("command", COMMANDS)
def test_command_roundtrip_semantic_identity(build_dir, command):
    """Régénéré vs vivant : frontmatter par valeur + corps identique (norm. CRLF/BOM)."""
    generated = build_dir / "commands" / f"{command}.md"
    live = LIVE_COMMANDS_DIR / f"{command}.md"
    assert generated.is_file(), f"{command}: fichier régénéré absent"
    assert live.is_file(), f"{command}: commande vivante absente de .claude/commands/"
    pivot = _pivot_from_md(command)
    report = _diff_command(generated, live, pivot)
    assert report.identical, f"{command}: round-trip non sémantique — {report.summary()}"


def test_commands_roundtrip_rate_is_measured(build_dir):
    """Mesure agrégée du TAUX de round-trip commandes (rapport lisible)."""
    reports = {
        command: _diff_command(
            build_dir / "commands" / f"{command}.md",
            LIVE_COMMANDS_DIR / f"{command}.md",
            _pivot_from_md(command),
        )
        for command in COMMANDS
    }
    identical = [c for c, r in reports.items() if r.identical]
    divergent = {c: r.summary() for c, r in reports.items() if not r.identical}
    rate = f"{len(identical)}/{len(COMMANDS)}"
    assert not divergent, f"taux de round-trip commandes {rate} — écarts: {divergent}"


def test_emit_commands_never_writes_outside_sdd_build():
    """Garde-fou sécurité : toute sortie hors .sdd/.build/ est refusée."""
    adapter = ClaudeAdapter(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT / "workspace", SDD_HOME / "commands"):
        with pytest.raises(BuildSafetyError):
            adapter.emit_commands(forbidden)


def test_cli_agents_and_commands_combined(tmp_path_factory):
    """--agents-only + --commands-only combinés régénèrent les 2 couches."""
    from harness_build import main

    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-cli-combined-", dir=build_root))
    try:
        rc = main(
            ["--harness", "claude-code", "--agents-only", "--commands-only", "--out", str(out)]
        )
        assert rc == 0
        assert len(list((out / "agents").glob("*.md"))) == 29
        assert len(list((out / "commands").glob("*.md"))) == 41
    finally:
        shutil.rmtree(out, ignore_errors=True)
