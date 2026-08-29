"""Tests de la barrière de vague du reverse DB (audit 2026-08-28, P0-4).

Ce que ces tests protègent, par ordre d'importance :

1. **Le bénéfice réel du plan de vagues.** Le seul test qui compte vraiment
   est celui qui vérifie qu'un appelant, APRÈS la barrière, lit la RÈGLE
   MÉTIER de son appelé là où il lisait « pas encore analysé » avant. Sans
   cette propriété, l'ordonnancement par vagues coûte un tri pour rien.
2. **Le déterminisme.** Le résumé est extrait de l'User Story, jamais
   re-généré. Deux exécutions produisent le même finding, et le finding
   ne peut pas diverger de l'US livrée.
3. **L'honnêteté.** Une US absente est un cas normal (`skipped`), pas une
   erreur. Une US sans contenu exploitable produit un résumé VIDE signalé
   (`empty`), jamais une phrase fabriquée.
4. **La portée de la régénération.** Seuls les packs de la vague suivante
   sont réécrits — sur 118 objets réels, l'alternative est de réécrire des
   centaines de fiches inchangées à chaque barrière.
"""
from __future__ import annotations

import json

import pytest

from sdd_reverse import wave_barrier as wb
from sdd_reverse.db_context import build_context


# --------------------------------------------------------------------------- #
# Fixtures — même forme que test_db_context.py (introspection déjà écrite par
# le scan read-only ; aucune base, aucun driver).
# --------------------------------------------------------------------------- #

def _obj(fq, rtype="SQL_STORED_PROCEDURE", **kw):
    schema, name = fq.split(".", 1)
    return {
        "fqName": fq, "schema": schema, "name": name, "routineType": rtype,
        "encrypted": False, "lineCount": kw.get("lines", 20),
        "params": kw.get("params", []),
        "tablesRead": kw.get("read", []), "tablesWritten": kw.get("written", []),
        "writeKinds": kw.get("kinds", {}), "callsProcs": kw.get("calls", []),
        "branches": kw.get("branches", 0), "cursors": 0,
        "raises": kw.get("raises", []), "hasTransaction": kw.get("txn", False),
        "hasTryCatch": False, "dynamicSql": False,
        "snapshotFile": f".sys/proc-snapshot/{fq}.sql",
        "evidence": f".sys/proc-snapshot/{fq}.sql:L1-{kw.get('lines', 20)}",
        "confidenceEstimate": "high",
    }


@pytest.fixture
def introspection():
    return {
        "schemaVersion": 1, "databaseType": "sqlserver", "languageId": "tsql",
        "database": "SalesDb",
        "procedures": [
            _obj("dbo.fn_CalcTVA", "SQL_SCALAR_FUNCTION", lines=12,
                 read=["dbo.TauxTVA"], params=["@montant DECIMAL"]),
            _obj("dbo.usp_Stock_Reserve", lines=90, written=["dbo.Stock"],
                 kinds={"UPDATE": ["dbo.Stock"]}, read=["dbo.Produit"],
                 branches=4, raises=["RAISERROR"], txn=True),
            _obj("dbo.usp_Commande_Valider", lines=38, written=["dbo.Commande"],
                 kinds={"INSERT": ["dbo.Commande"]},
                 calls=["dbo.usp_Stock_Reserve", "dbo.fn_CalcTVA"]),
        ],
    }


@pytest.fixture
def context(introspection):
    return build_context(introspection, None, project="SalesDb")


_US_RESERVE = """---
ID: 1-2-Reserver-Stock
Parent FEAT: 1-Stock
generated-by: sdd-reverse
source-proc: dbo.usp_Stock_Reserve
Confidence: high
Status: Draft
---

# US-2: Réserver le stock d'un produit pour une commande

## Story

En tant que **moteur de commande**, je veux **réserver la quantité demandée**,
afin de **garantir qu'elle ne sera pas vendue deux fois**.

## Acceptance Criteria

- AC-1: Given un stock suffisant, when la procédure est appelée, then la
  quantité réservée est décrémentée de dbo.Stock dans une transaction.
  <!-- evidence: .sys/proc-snapshot/dbo.usp_Stock_Reserve.sql:12-30 --> <!-- confidence: high -->
- AC-2: Given un stock insuffisant, when la procédure est appelée, then elle
  lève RAISERROR et n'écrit rien.
  <!-- evidence: .sys/proc-snapshot/dbo.usp_Stock_Reserve.sql:31-38 --> <!-- confidence: high -->

## Data Effects (plomberie démotée)

- Lit : dbo.Produit
- Écrit : dbo.Stock
- Paramètres : @produitId INT, @qte INT
- Transaction : oui · SQL dynamique : non
"""

_US_TVA = """---
ID: 1-1-Calculer-TVA
Parent FEAT: 1-Facturation
generated-by: sdd-reverse
source-proc: dbo.fn_CalcTVA
Confidence: medium
Status: Draft
---

# US-1: Calculer la TVA applicable à un montant

## Acceptance Criteria

- AC-1: Given un montant positif, when la fonction est appelée, then elle
  retourne le montant multiplié par le taux courant de dbo.TauxTVA.
  <!-- evidence: .sys/proc-snapshot/dbo.fn_CalcTVA.sql:1-12 --> <!-- confidence: medium -->
"""


def _write_us(us_dir, *pairs):
    us_dir.mkdir(parents=True, exist_ok=True)
    for name, body in pairs:
        (us_dir / name).write_text(body, encoding="utf-8")
    return wb.index_us_by_object(us_dir)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

class TestFindingExtraction:
    def test_summary_comes_from_the_title(self):
        f = wb.finding_from_us(_US_RESERVE)
        assert f["summary"] == "Réserver le stock d'un produit pour une commande"

    def test_falls_back_to_the_story_when_no_title(self):
        text = _US_RESERVE.replace("# US-2: Réserver le stock d'un produit pour une commande", "")
        f = wb.finding_from_us(text)
        assert f["summary"] == "réserver la quantité demandée"

    def test_business_rules_come_from_acceptance_criteria(self):
        """Le template d'objet SQL n'a pas de section « Business Rules » : la
        règle de gestion vit dans les AC, une par branche observable."""
        f = wb.finding_from_us(_US_RESERVE)
        assert len(f["businessRules"]) == 2
        assert "transaction" in f["businessRules"][0]
        assert "RAISERROR" in f["businessRules"][1]

    def test_evidence_comments_are_stripped_from_rules(self):
        """L'evidence est précieuse DANS l'US, parasite dans un résumé cité par
        un appelant qui n'a pas à la re-vérifier."""
        f = wb.finding_from_us(_US_RESERVE)
        for rule in f["businessRules"]:
            assert "evidence:" not in rule
            assert "confidence:" not in rule
            assert "<!--" not in rule

    def test_confidence_is_read_from_the_frontmatter(self):
        assert wb.finding_from_us(_US_RESERVE)["confidence"] == "high"
        assert wb.finding_from_us(_US_TVA)["confidence"] == "medium"

    def test_contract_captures_the_parameters_line(self):
        f = wb.finding_from_us(_US_RESERVE)
        assert "@produitId" in f["contract"]

    def test_long_summary_is_truncated_on_a_word(self):
        """Un pack porte plusieurs appelés ; un paragraphe entier ferait
        exploser le budget que db_context_slice s'échine à tenir."""
        long_title = "# US-9: " + ("mot " * 200)
        f = wb.finding_from_us(long_title)
        assert len(f["summary"]) <= wb.SUMMARY_MAX
        assert f["summary"].endswith("…")

    def test_empty_us_yields_an_empty_summary_not_an_invention(self):
        f = wb.finding_from_us("---\nsource-proc: dbo.x\n---\n\nrien ici\n")
        assert f["summary"] == ""
        assert f["businessRules"] == []

    def test_extraction_is_deterministic(self):
        """Le résumé est extrait, jamais re-généré : deux appels donnent le
        même finding, et il ne peut pas diverger de l'US livrée."""
        assert wb.finding_from_us(_US_RESERVE) == wb.finding_from_us(_US_RESERVE)


class TestUsIndex:
    def test_indexes_on_source_proc_not_on_filename(self, tmp_path):
        """Le basename porte un slug de capability qui n'a aucune raison de
        ressembler au nom de l'objet SQL."""
        idx = _write_us(tmp_path / "us", ("1-2-Reserver-Stock.md", _US_RESERVE))
        assert "dbo.usp_stock_reserve" in idx
        assert idx["dbo.usp_stock_reserve"].name == "1-2-Reserver-Stock.md"

    def test_us_without_source_proc_is_ignored(self, tmp_path):
        idx = _write_us(tmp_path / "us",
                        ("1-9-Autre.md", "---\nID: 1-9-Autre\n---\n# US-9: forward\n"))
        assert idx == {}

    def test_missing_directory_is_not_an_error(self, tmp_path):
        assert wb.index_us_by_object(tmp_path / "absent") == {}


# --------------------------------------------------------------------------- #
# Barrière
# --------------------------------------------------------------------------- #

class TestCloseWave:
    def test_wave_zero_holds_the_leaves(self, context):
        """Les feuilles du graphe — ici la fonction et la procédure de stock,
        qui n'appellent rien — précèdent leur appelant."""
        w0 = {o.lower() for o in wb.wave_members(context, 0)}
        assert "dbo.fn_calctva" in w0
        assert "dbo.usp_commande_valider" not in w0

    def test_records_findings_for_analysed_objects(self, context, tmp_path):
        idx = _write_us(tmp_path / "us",
                        ("1-1-Calculer-TVA.md", _US_TVA),
                        ("1-2-Reserver-Stock.md", _US_RESERVE))
        ctx, report = wb.close_wave(context, 0, idx)
        assert report["stats"]["recorded"] == 2
        assert set(ctx["findings"]) == {"dbo.fn_CalcTVA", "dbo.usp_Stock_Reserve"}

    def test_missing_us_is_skipped_not_failed(self, context, tmp_path):
        """Cas NORMAL : l'objet n'était pas routé LLM, ou le cache l'a sauté."""
        idx = _write_us(tmp_path / "us", ("1-1-Calculer-TVA.md", _US_TVA))
        _, report = wb.close_wave(context, 0, idx)
        assert report["stats"]["recorded"] == 1
        assert [s["object"] for s in report["skipped"]] == ["dbo.usp_Stock_Reserve"]
        assert "aucune User Story" in report["skipped"][0]["reason"]

    def test_unexploitable_us_is_recorded_and_flagged(self, context, tmp_path):
        """« analysé, rien d'exploitable » vaut mieux qu'une phrase inventée,
        et mieux qu'un silence."""
        hollow = "---\nsource-proc: dbo.fn_CalcTVA\nConfidence: low\n---\n\nvide\n"
        idx = _write_us(tmp_path / "us", ("1-1-Vide.md", hollow))
        ctx, report = wb.close_wave(context, 0, idx)
        assert report["empty"] == ["dbo.fn_CalcTVA"]
        assert "dbo.fn_CalcTVA" in ctx["findings"]
        assert ctx["findings"]["dbo.fn_CalcTVA"]["summary"] == ""

    def test_finding_carries_the_resolved_callees(self, context, tmp_path):
        """Pour que le pack d'un appelant sache ce que son appelé délègue à son
        tour, sans re-parcourir le graphe."""
        us = _US_RESERVE.replace("dbo.usp_Stock_Reserve", "dbo.usp_Commande_Valider")
        idx = _write_us(tmp_path / "us", ("1-3-Valider.md", us))
        wave = next(i for i in range(4)
                    if "dbo.usp_Commande_Valider" in wb.wave_members(context, i))
        ctx, _ = wb.close_wave(context, wave, idx)
        callees = ctx["findings"]["dbo.usp_Commande_Valider"]["callees"]
        assert "dbo.fn_CalcTVA" in callees

    def test_is_idempotent(self, context, tmp_path):
        idx = _write_us(tmp_path / "us", ("1-1-Calculer-TVA.md", _US_TVA))
        once, _ = wb.close_wave(context, 0, idx)
        twice, _ = wb.close_wave(once, 0, idx)
        assert once["findings"] == twice["findings"]

    def test_out_of_range_wave_is_empty_not_an_error(self, context, tmp_path):
        idx = _write_us(tmp_path / "us", ("1-1-Calculer-TVA.md", _US_TVA))
        _, report = wb.close_wave(context, 99, idx)
        assert report["stats"] == {"members": 0, "recorded": 0, "skipped": 0, "empty": 0}

    def test_only_filter_restricts_to_named_objects(self, context, tmp_path):
        idx = _write_us(tmp_path / "us",
                        ("1-1-Calculer-TVA.md", _US_TVA),
                        ("1-2-Reserver-Stock.md", _US_RESERVE))
        ctx, report = wb.close_wave(context, 0, idx, only=["dbo.fn_CalcTVA"])
        assert report["recorded"] == ["dbo.fn_CalcTVA"]
        assert "dbo.usp_Stock_Reserve" not in ctx["findings"]


# --------------------------------------------------------------------------- #
# LE test qui justifie tout le mécanisme
# --------------------------------------------------------------------------- #

class TestCallerActuallyLearnsFromItsCallees:
    def test_caller_pack_gains_the_callee_business_rule(self, context, tmp_path):
        """Le seul test qui compte vraiment.

        AVANT la barrière, le pack de `usp_Commande_Valider` décrit ses appelés
        par « pas encore analysé » et une matrice CRUD. APRÈS, il porte leur
        règle métier. C'est exactement ce que le plan de vagues promettait et
        que personne n'exécutait.
        """
        from sdd_reverse.db_context_slice import build_pack

        before, _ = build_pack(context, "dbo.usp_Commande_Valider")
        assert "pas encore analysé" in before
        assert "RAISERROR" not in before

        idx = _write_us(tmp_path / "us",
                        ("1-1-Calculer-TVA.md", _US_TVA),
                        ("1-2-Reserver-Stock.md", _US_RESERVE))
        ctx, _ = wb.close_wave(context, 0, idx)

        after, _ = build_pack(ctx, "dbo.usp_Commande_Valider")
        assert "Réserver le stock" in after
        assert "RAISERROR" in after, "la règle négative de l'appelé doit remonter"
        assert "Calculer la TVA" in after

    def test_callee_confidence_is_visible_to_the_caller(self, context, tmp_path):
        """Un appelant doit pouvoir plafonner sa propre confiance sur celle de
        ce qu'il délègue."""
        from sdd_reverse.db_context_slice import build_pack
        idx = _write_us(tmp_path / "us", ("1-1-Calculer-TVA.md", _US_TVA))
        ctx, _ = wb.close_wave(context, 0, idx)
        after, _ = build_pack(ctx, "dbo.usp_Commande_Valider")
        assert "confidence: medium" in after


# --------------------------------------------------------------------------- #
# CLI — le point d'entrée qui manquait
# --------------------------------------------------------------------------- #

class TestCli:
    @staticmethod
    def _project(tmp_path, introspection):
        root = tmp_path / "SalesDb"
        (root / ".sys").mkdir(parents=True)
        (root / ".sys" / "db-introspection.json").write_text(
            json.dumps(introspection), encoding="utf-8")
        return root

    def _run(self, *args):
        from sdd_reverse_scripts.db_context_build import main
        return main(list(args))

    def test_close_wave_writes_findings_and_regenerates_next_packs(
            self, tmp_path, introspection):
        root = self._project(tmp_path, introspection)
        us_dir = tmp_path / "us"
        _write_us(us_dir, ("1-1-Calculer-TVA.md", _US_TVA),
                  ("1-2-Reserver-Stock.md", _US_RESERVE))

        assert self._run("--project", str(root)) == 0
        assert self._run("--project", str(root), "--close-wave", "0",
                         "--us-dir", str(us_dir)) == 0

        ctx = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        assert "dbo.usp_Stock_Reserve" in ctx["findings"]

        pack = (root / ".sys" / "db-context" / "packs"
                / "dbo.usp_Commande_Valider.md").read_text(encoding="utf-8")
        assert "Réserver le stock" in pack

    def test_record_finding_requires_from_us(self, tmp_path, introspection):
        root = self._project(tmp_path, introspection)
        assert self._run("--project", str(root)) == 0
        assert self._run("--project", str(root),
                         "--record-finding", "dbo.fn_CalcTVA") == 1

    def test_record_finding_handles_one_object(self, tmp_path, introspection):
        root = self._project(tmp_path, introspection)
        us_dir = tmp_path / "us"
        _write_us(us_dir, ("1-2-Reserver-Stock.md", _US_RESERVE))
        assert self._run("--project", str(root)) == 0
        assert self._run("--project", str(root),
                         "--record-finding", "dbo.usp_Stock_Reserve",
                         "--from-us", str(us_dir / "1-2-Reserver-Stock.md")) == 0
        ctx = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        assert list(ctx["findings"]) == ["dbo.usp_Stock_Reserve"]

    def test_unknown_object_is_rejected(self, tmp_path, introspection):
        root = self._project(tmp_path, introspection)
        us_dir = tmp_path / "us"
        _write_us(us_dir, ("1-2-Reserver-Stock.md", _US_RESERVE))
        assert self._run("--project", str(root)) == 0
        assert self._run("--project", str(root),
                         "--record-finding", "dbo.usp_Inexistante",
                         "--from-us", str(us_dir / "1-2-Reserver-Stock.md")) == 1

    def test_last_wave_barrier_has_nothing_to_regenerate(self, tmp_path, introspection):
        """Fermer la dernière vague n'est pas une erreur : il n'y a simplement
        pas de vague suivante à nourrir."""
        root = self._project(tmp_path, introspection)
        us_dir = tmp_path / "us"
        _write_us(us_dir, ("1-2-Reserver-Stock.md", _US_RESERVE))
        assert self._run("--project", str(root)) == 0
        ctx = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        last = len(ctx["executionPlan"]["waves"]) - 1
        assert self._run("--project", str(root), "--close-wave", str(last),
                         "--us-dir", str(us_dir)) == 0
