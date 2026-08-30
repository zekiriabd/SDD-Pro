"""test_subagent_matcher_sync.py — sync SubagentStop matchers ↔ hooks Python.

Audit P-M2 (2026-08-30) : le matcher SubagentStop de `.claude/settings.json`
listait 12 agents forward non ancrés et AUCUN agent reverse, alors que
OWNERSHIP_MATRIX (`sdd_hooks/audit_file_ownership.py`) couvre les 6 agents
db-reverse et qu'INVARIANTS.yml (`reverse-db-context-facts-vs-hypotheses`)
déclare cette couverture. Pire : en regex non ancrée, `po` matchait
`reverse-sql-feat-composer` par sous-chaîne (« com**po**ser ») → le hook
`resolve_po_hash_sentinel` se déclenchait à tort, et `arch` matchait
`reverse-db-architect`.

Ce module pinne le contrat corrigé :

  1. le matcher du hook `audit_file_ownership` couvre EXACTEMENT les agents
     d'OWNERSHIP_MATRIX (le hook no-op sur tout autre agent — main() retourne
     HOOK_ALLOW si `subagent not in _COMPILED_OWNERSHIP`, donc tout agent
     hors matrice dans le matcher serait du câblage mort) ;
  2. `resolve_po_hash_sentinel` ne se déclenche QUE pour `po` ;
  3. `validate_acceptance_gate` ne se déclenche QUE pour `qa` ;
  4. aucun agent existant (`.sdd/agents/*.md`) ne matche par accident un
     matcher qui ne le concerne pas (régression du cas po/composer).

Sémantique matcher simulée : Claude Code applique le matcher comme une
regex NON ancrée sur le subagent_type → `re.search`. Un groupe sans clé
`matcher` se déclenche pour tous les agents.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_hooks.audit_file_ownership import OWNERSHIP_MATRIX  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

_SETTINGS_PATH = repo_root() / ".claude" / "settings.json"
_AGENTS_DIR = repo_root() / ".sdd" / "agents"


def _subagent_stop_groups() -> list[dict]:
    data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    return data["hooks"]["SubagentStop"]


def _groups_running(script_stem: str) -> list[dict]:
    """Groups whose hook commands invoke `sdd_hooks.<script_stem>`."""
    out = []
    for group in _subagent_stop_groups():
        commands = " ".join(h.get("command", "") for h in group.get("hooks", []))
        if f"sdd_hooks.{script_stem}" in commands:
            out.append(group)
    return out


def _matcher_fires(matcher: str | None, agent: str) -> bool:
    """Simulate the harness matcher semantics (unanchored regex search)."""
    if matcher is None:
        return True  # no matcher key = fires for every subagent
    return re.search(matcher, agent) is not None


def _existing_agents() -> frozenset[str]:
    return frozenset(p.stem for p in _AGENTS_DIR.glob("*.md"))


class TestOwnershipMatcherSync(unittest.TestCase):
    """Matcher du hook audit_file_ownership ↔ OWNERSHIP_MATRIX."""

    def setUp(self) -> None:
        groups = _groups_running("audit_file_ownership")
        self.assertEqual(
            len(groups), 1,
            "audit_file_ownership doit être câblé dans exactement 1 groupe "
            f"SubagentStop (trouvé {len(groups)})",
        )
        self.matcher = groups[0].get("matcher")

    def test_every_matrix_agent_is_matched(self):
        """Chaque agent d'OWNERSHIP_MATRIX déclenche le hook ownership."""
        missing = [a for a in OWNERSHIP_MATRIX if not _matcher_fires(self.matcher, a)]
        self.assertEqual(
            missing, [],
            "Agents d'OWNERSHIP_MATRIX non couverts par le matcher SubagentStop "
            f"du hook ownership : {missing} — l'audit ne tournera jamais pour eux "
            "(INVARIANTS.yml reverse-db-context-facts-vs-hypotheses)",
        )

    def test_no_agent_outside_matrix_is_matched(self):
        """Le hook no-op sur les agents hors matrice → les matcher = câblage mort.

        main() retourne HOOK_ALLOW quand `subagent not in _COMPILED_OWNERSHIP` :
        un agent matché sans entrée matrice n'est pas audité, il coûte juste un
        spawn python inutile ET masque le vrai périmètre du gate.
        """
        extra = [
            a for a in sorted(_existing_agents())
            if a not in OWNERSHIP_MATRIX and _matcher_fires(self.matcher, a)
        ]
        self.assertEqual(
            extra, [],
            f"Agents matchés par le matcher ownership sans entrée OWNERSHIP_MATRIX : {extra}",
        )


class TestSingleAgentMatchers(unittest.TestCase):
    """Les hooks mono-agent (po, qa) ne matchent que leur agent — ancrage."""

    def _assert_exclusive(self, script_stem: str, expected_agent: str) -> None:
        groups = _groups_running(script_stem)
        self.assertEqual(
            len(groups), 1,
            f"{script_stem} doit être câblé dans exactement 1 groupe SubagentStop",
        )
        matcher = groups[0].get("matcher")
        self.assertIsNotNone(
            matcher, f"le groupe {script_stem} doit porter un matcher explicite"
        )
        self.assertTrue(
            _matcher_fires(matcher, expected_agent),
            f"le matcher {matcher!r} ne matche plus {expected_agent!r}",
        )
        accidental = [
            a for a in sorted(_existing_agents())
            if a != expected_agent and _matcher_fires(matcher, a)
        ]
        self.assertEqual(
            accidental, [],
            f"matcher {matcher!r} ({script_stem}) matche par accident : {accidental}",
        )

    def test_resolve_po_hash_sentinel_only_po(self):
        self._assert_exclusive("resolve_po_hash_sentinel", "po")

    def test_validate_acceptance_gate_only_qa(self):
        self._assert_exclusive("validate_acceptance_gate", "qa")

    def test_regression_po_does_not_match_composer(self):
        """Pin explicite du bug d'origine : `po` non ancré matchait
        `reverse-sql-feat-composer` (« com**po**ser ») par sous-chaîne."""
        groups = _groups_running("resolve_po_hash_sentinel")
        matcher = groups[0].get("matcher")
        self.assertFalse(
            _matcher_fires(matcher, "reverse-sql-feat-composer"),
            "resolve_po_hash_sentinel se déclencherait pour reverse-sql-feat-composer",
        )
        self.assertFalse(
            _matcher_fires(matcher, "reverse-feat-composer"),
            "resolve_po_hash_sentinel se déclencherait pour reverse-feat-composer",
        )


class TestMatchersAgainstRealAgents(unittest.TestCase):
    """Garde générale : tout matcher SubagentStop explicite reste cohérent
    avec les agents réellement présents sur disque."""

    #: périmètre attendu par script (None = tous les agents sont légitimes)
    EXPECTED_SCOPE: dict[str, frozenset[str] | None] = {
        "audit_file_ownership": frozenset(OWNERSHIP_MATRIX),
        "resolve_po_hash_sentinel": frozenset({"po"}),
        "validate_acceptance_gate": frozenset({"qa"}),
        "record_token_usage": None,  # télémétrie générique : tous agents OK
    }

    def test_every_subagent_stop_hook_has_declared_scope(self):
        """Tout nouveau hook SubagentStop doit déclarer son périmètre ici —
        sinon ce test ne peut pas le vérifier (anti-rot)."""
        undeclared = []
        for group in _subagent_stop_groups():
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                m = re.search(r"sdd_hooks\.([a-z0-9_]+)", cmd)
                if m and m.group(1) not in self.EXPECTED_SCOPE:
                    undeclared.append(m.group(1))
        self.assertEqual(
            undeclared, [],
            "Hooks SubagentStop sans périmètre déclaré dans EXPECTED_SCOPE : "
            f"{undeclared} — ajouter l'entrée (ou None si tous-agents)",
        )

    def test_no_accidental_match_on_any_existing_agent(self):
        violations = []
        agents = sorted(_existing_agents())
        for group in _subagent_stop_groups():
            matcher = group.get("matcher")
            for hook in group.get("hooks", []):
                m = re.search(r"sdd_hooks\.([a-z0-9_]+)", hook.get("command", ""))
                if not m:
                    continue
                scope = self.EXPECTED_SCOPE.get(m.group(1))
                if scope is None:
                    continue
                for agent in agents:
                    if _matcher_fires(matcher, agent) and agent not in scope:
                        violations.append(f"{m.group(1)} ← {agent}")
        self.assertEqual(
            violations, [],
            f"Déclenchements SubagentStop accidentels (hook ← agent) : {violations}",
        )


if __name__ == "__main__":
    unittest.main()
