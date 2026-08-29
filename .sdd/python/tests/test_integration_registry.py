"""Cliquet du registre d'intégration (audit 2026-08-28, correction #2).

`test_invariants_manifest.py` vérifie qu'un contrat a un enforcer sur disque.
Ce test-ci vérifie la question d'après, que rien ne posait : **ce composant
est-il réellement APPELÉ, et par qui ?**

L'audit a recensé huit briques déterministes de bonne qualité, testées
unitairement, sans aucun appelant — parce que celui qui devait les appeler
était un LLM lisant du Markdown, et qu'un fichier Markdown n'appelle rien.
`.sdd/integration.yml` durcit donc la définition de « fait » :

    implemented + unit-tested        →  implemented + integrated
                                        + exercised + observable

Le mécanisme qui fait tenir ce contrat dans le temps est le **cliquet** :
le nombre de composants non-`integrated` ne peut pas dépasser `debt_ceiling`.
Ajouter une brique non câblée exige alors de modifier le plafond, donc de
rendre la dette visible en revue de code au lieu de la dissoudre dans un
commit.

Ce que ce test refuse :
  - un `module:` déclaré absent du disque ;
  - un `callers:` absent, OU qui ne référence pas réellement le composant
    (le lien déclaré est VÉRIFIÉ, pas cru sur parole) ;
  - un composant `integrated` sans appelant, sans test d'intégration
    existant, ou sans moyen d'observation ;
  - un composant en dette sans `reason`, `owner` et `exit_plan` ;
  - un dépassement du plafond de dette.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

from sdd_lib.config_loader import load_yaml  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402

_VALID_STATUS = {"integrated", "advisory", "orphan", "harness-blocked"}
_DEBT_STATUS = {"advisory", "orphan", "harness-blocked"}


def _registry() -> dict:
    return load_yaml(repo_root() / ".sdd" / "integration.yml")


def _components() -> list[dict]:
    return _registry().get("components") or []


class TestSchema(unittest.TestCase):
    def test_registry_exists_and_declares_the_contract(self) -> None:
        reg = _registry()
        self.assertEqual(
            reg.get("contract"),
            ["implemented", "integrated", "exercised", "observable"],
            "le contrat est le sujet du fichier : il doit être explicite",
        )

    def test_components_are_declared(self) -> None:
        self.assertGreater(len(_components()), 0)

    def test_ids_are_unique(self) -> None:
        ids = [c.get("id") for c in _components()]
        dupes = {i for i in ids if ids.count(i) > 1}
        self.assertFalse(dupes, f"ids dupliqués : {sorted(dupes)}")

    def test_status_is_in_the_closed_vocabulary(self) -> None:
        """Un vocabulaire ouvert permettrait d'inventer un statut pour
        échapper au cliquet."""
        bad = [(c["id"], c.get("status")) for c in _components()
               if c.get("status") not in _VALID_STATUS]
        self.assertFalse(bad, f"statuts hors vocabulaire : {bad}")


class TestDeclarationsMatchDisk(unittest.TestCase):
    def test_every_module_exists(self) -> None:
        root = repo_root()
        missing = [f"{c['id']} → {c['module']}" for c in _components()
                   if not (root / c["module"]).is_file()]
        self.assertFalse(missing, f"modules déclarés absents : {missing}")

    def test_every_caller_exists(self) -> None:
        root = repo_root()
        missing = []
        for c in _components():
            for caller in c.get("callers") or []:
                if not (root / caller).is_file():
                    missing.append(f"{c['id']} → {caller}")
        self.assertFalse(missing, f"appelants déclarés absents : {missing}")

    def test_every_caller_really_references_its_component(self) -> None:
        """Le cœur du test. Déclarer un appelant ne suffit pas : le fichier
        appelant doit réellement nommer le composant. Sans cette vérification,
        le registre deviendrait exactement ce qu'il dénonce — une déclaration
        d'intention qu'aucun mécanisme ne confronte au code.
        """
        root = repo_root()
        broken = []
        for c in _components():
            stem = Path(c["module"]).stem
            symbol = c.get("symbol") or stem
            needles = {stem, symbol}
            for caller in c.get("callers") or []:
                p = root / caller
                if not p.is_file():
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                if not any(n and n in text for n in needles):
                    broken.append(
                        f"{c['id']} : {caller} ne référence ni "
                        f"{' ni '.join(sorted(n for n in needles if n))}"
                    )
        self.assertFalse(broken, "liens déclarés mais absents du code :\n  "
                                 + "\n  ".join(broken))

    def test_every_integration_test_exists(self) -> None:
        root = repo_root()
        missing = [f"{c['id']} → {c['integration_test']}" for c in _components()
                   if c.get("integration_test")
                   and not (root / c["integration_test"]).is_file()]
        self.assertFalse(missing, f"tests d'intégration absents : {missing}")


class TestIntegratedContract(unittest.TestCase):
    """Les quatre propriétés doivent être vraies pour un `integrated`."""

    def _integrated(self) -> list[dict]:
        return [c for c in _components() if c.get("status") == "integrated"]

    def test_integrated_has_at_least_one_caller(self) -> None:
        bad = [c["id"] for c in self._integrated() if not (c.get("callers") or [])]
        self.assertFalse(bad, f"`integrated` sans appelant : {bad}")

    def test_integrated_caller_is_not_only_its_own_test(self) -> None:
        """Un test n'est pas un appelant de production. Se déclarer intégré
        parce qu'un test appelle le module est la forme la plus subtile du
        doc-theater — et c'est le piège dans lequel la première version de ce
        registre est tombée pour `scan_patterns`."""
        bad = []
        for c in self._integrated():
            callers = c.get("callers") or []
            if callers and all("/tests/" in cl for cl in callers):
                bad.append(c["id"])
        self.assertFalse(bad, f"`integrated` dont le seul appelant est un test : {bad}")

    def test_integrated_declares_observability(self) -> None:
        bad = [c["id"] for c in self._integrated() if not c.get("observability")]
        self.assertFalse(bad, f"`integrated` sans moyen d'observation : {bad}")

    def test_integrated_declares_a_trigger(self) -> None:
        bad = [c["id"] for c in self._integrated() if not c.get("trigger")]
        self.assertFalse(bad, f"`integrated` sans déclencheur déclaré : {bad}")


class TestDebtContract(unittest.TestCase):
    def _debt(self) -> list[dict]:
        return [c for c in _components() if c.get("status") in _DEBT_STATUS]

    def test_debt_declares_reason_owner_and_exit_plan(self) -> None:
        """Une dette sans plan de sortie n'est pas une dette, c'est un abandon."""
        bad = []
        for c in self._debt():
            for field in ("reason", "owner", "exit_plan"):
                if not c.get(field):
                    bad.append(f"{c['id']}.{field}")
        self.assertFalse(bad, f"dette incomplètement documentée : {bad}")

    def test_orphan_declares_no_caller(self) -> None:
        """Cohérence interne : `orphan` signifie « aucun appelant ». Un orphan
        qui en déclare un est mal classé, et le cliquet compterait faux."""
        bad = [c["id"] for c in _components()
               if c.get("status") == "orphan" and (c.get("callers") or [])]
        self.assertFalse(bad, f"`orphan` avec un appelant déclaré : {bad}")

    def test_debt_stays_under_the_declared_ceiling(self) -> None:
        """LE cliquet. La dette peut décroître, jamais croître en silence."""
        reg = _registry()
        ceiling = reg.get("debt_ceiling")
        self.assertIsInstance(ceiling, int, "debt_ceiling doit être déclaré")
        debt = self._debt()
        self.assertLessEqual(
            len(debt), ceiling,
            f"{len(debt)} composants non câblés pour un plafond de {ceiling}. "
            f"Câbler, ou assumer la hausse en modifiant `debt_ceiling` "
            f"explicitement : {sorted(c['id'] for c in debt)}",
        )

    def test_ceiling_is_not_slack(self) -> None:
        """Un plafond très au-dessus de la dette réelle ne cliquette plus rien.
        On tolère une marge de 1, pas davantage : le plafond doit être
        redescendu à chaque câblage."""
        reg = _registry()
        debt = len(self._debt())
        self.assertLessEqual(
            reg["debt_ceiling"] - debt, 1,
            f"plafond {reg['debt_ceiling']} pour une dette de {debt} : "
            f"redescendre le plafond, sinon le cliquet ne mord plus",
        )


class TestKnownDebtIsStillDeclared(unittest.TestCase):
    """Les orphelins nommés par l'audit doivent rester dans le registre
    jusqu'à leur câblage — pour qu'un `git grep` sur le nom du composant mène
    à sa dette plutôt qu'au silence."""

    _AUDIT_FINDINGS = (
        "wave-barrier",            # db_context.record_finding — audit P0-4
        "build-loop-trace",        # audit P1-6
        "libname-lock",            # audit P1-5
        "prompt-cache-manifest",   # audit P1 levier 4
        "spawn-agent",             # audit §08
        "pipeline-planner",        # audit P1-9
        "complexity-router",       # audit P2
    )

    def test_every_audited_orphan_is_declared(self) -> None:
        declared = {c["id"] for c in _components()}
        missing = [i for i in self._AUDIT_FINDINGS if i not in declared]
        self.assertFalse(
            missing,
            f"composants signalés par l'audit et absents du registre : {missing}. "
            f"S'ils ont été câblés, les passer à `integrated` ; s'ils ont été "
            f"supprimés, retirer l'entrée ET cette ligne de test.",
        )


class TestRegistryCoversTheAuditedSurface(unittest.TestCase):
    def test_new_pattern_scan_and_journal_are_integrated(self) -> None:
        """Les deux composants livrés par ce lot doivent tenir le contrat
        complet, sinon la correction n'a fait que déplacer le problème."""
        by_id = {c["id"]: c for c in _components()}
        for cid in ("pattern-scan", "agent-journal"):
            self.assertIn(cid, by_id)
            self.assertEqual(by_id[cid]["status"], "integrated", cid)

    def test_pattern_scan_caller_is_the_review_aggregator(self) -> None:
        by_id = {c["id"]: c for c in _components()}
        callers = by_id["pattern-scan"]["callers"]
        self.assertTrue(
            any("sdd_review" in c for c in callers),
            "le scan doit être appelé par l'agrégateur, pas par un prompt",
        )


if __name__ == "__main__":
    unittest.main()
