"""Test de ROUND-TRIP identité — Phase 2 du plan multi-harness.

Pour chacun des 13 agents FORWARD (pivots `.sdd/agents/*.agent.yaml` hors
`reverse-*`), régénère le `.md` Claude Code via `ClaudeAdapter` dans un
dossier temporaire SOUS `.sdd/.build/` (jamais `.claude/`), puis vérifie
via `sdd_lib.harness_diff` l'ÉGALITÉ SÉMANTIQUE avec le
`.claude/agents/{name}.md` vivant :

- frontmatter : {name, description, model, tools} comparés par VALEUR
  (ordre des clés non significatif, `tools` normalisé en liste) ;
- corps markdown : égalité stricte après normalisation des fins de ligne.

ÉCART CONNU byte-identité vs sémantique (accepté au stade proof-of-concept) :
- l'ordre des clés du frontmatter régénéré peut différer du vivant ;
- les commentaires inline du frontmatter vivant sont perdus (ex.
  `specbook-writer` porte `model: claude-sonnet-4-6   # ...` — la valeur
  est préservée, le commentaire non) ;
- CRLF vs LF.
La byte-identité stricte est un durcissement Phase 2 ultérieur.

Note parser : 5 agents vivants (adversarial-reviewer, arch, arch-reviewer,
qa, security-reviewer) ont une description contenant `: ` — frontmatter
NON parseable en YAML strict mais accepté par Claude Code. harness_diff
utilise donc un parser line-based tolérant, appliqué aux deux côtés.

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

from harness_build import ClaudeAdapter  # noqa: E402
from sdd_lib.harness_diff import diff_agent_files  # noqa: E402

LIVE_AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

# Les 13 agents forward = pivots hors module reverse (reverse-*).
FORWARD_AGENTS = sorted(
    p.name.replace(".md", "")
    for p in (SDD_HOME / "agents").glob("*.md")
    if not p.name.startswith("reverse-")
)


def test_forward_agent_count_is_13():
    """Verrou de périmètre : la couche forward compte exactement 13 pivots."""
    assert len(FORWARD_AGENTS) == 13, f"attendu 13 agents forward, trouvé {FORWARD_AGENTS}"


@pytest.fixture(scope="module")
def build_dir():
    """Régénère les 13 agents forward dans un temp SOUS .sdd/.build/ (jetable)."""
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-identity-", dir=build_root))
    results = ClaudeAdapter(repo_root=REPO_ROOT).emit_agents(out, only=set(FORWARD_AGENTS))
    skipped = {r.agent: r.skipped_reason for r in results if not r.ok}
    assert not skipped, f"émission incomplète (skips motivés): {skipped}"
    assert len(results) == len(FORWARD_AGENTS)
    yield out
    shutil.rmtree(out, ignore_errors=True)


@pytest.mark.parametrize("agent", FORWARD_AGENTS)
def test_agent_roundtrip_semantic_identity(build_dir, agent):
    """Régénéré vs vivant : frontmatter sémantiquement égal + corps identique."""
    generated = build_dir / "agents" / f"{agent}.md"
    live = LIVE_AGENTS_DIR / f"{agent}.md"
    assert generated.is_file(), f"{agent}: fichier régénéré absent"
    assert live.is_file(), f"{agent}: agent vivant absent de .claude/agents/"
    report = diff_agent_files(generated, live)
    assert report.identical, f"{agent}: round-trip non sémantique — {report.summary()}"


def test_roundtrip_rate_is_measured(build_dir):
    """Mesure agrégée du taux de round-trip (rapport lisible en cas de gap)."""
    reports = {
        agent: diff_agent_files(
            build_dir / "agents" / f"{agent}.md", LIVE_AGENTS_DIR / f"{agent}.md"
        )
        for agent in FORWARD_AGENTS
    }
    identical = [a for a, r in reports.items() if r.identical]
    divergent = {a: r.summary() for a, r in reports.items() if not r.identical}
    rate = f"{len(identical)}/{len(FORWARD_AGENTS)}"
    assert not divergent, f"taux de round-trip sémantique {rate} — écarts: {divergent}"


def test_build_never_writes_outside_sdd_build():
    """Garde-fou sécurité : toute sortie hors .sdd/.build/ est refusée."""
    from harness_build import BuildSafetyError

    adapter = ClaudeAdapter(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT / "workspace", SDD_HOME / "agents"):
        with pytest.raises(BuildSafetyError):
            adapter.emit_agents(forbidden)
