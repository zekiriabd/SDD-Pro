"""test_db_context.py — Phase 0 Database Context of db-reverse (offline).

Covers the deterministic layer introduced by the 2026-08-26 rework:
  - db_wave_planner  : call resolution, SCC condensation, execution waves
  - db_context       : facts (CRUD matrix), contextVersion, reuse, drift diff
  - db_context_slice : per-object context packs, budget trimming
  - sql_body_analyzer: call-aware complexity routing + graph confidence

No database, no driver, no network: every input is a synthetic catalog.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.db_context import (  # noqa: E402
    build_context,
    build_facts,
    context_version,
    diff_contexts,
    merge_architect_output,
    record_finding,
)
from sdd_reverse.db_context_slice import (  # noqa: E402
    build_pack,
    family_of,
    render_overview,
    render_table_card,
    write_context_tree,
)
from sdd_reverse.db_tier_router import (  # noqa: E402
    clamp,
    plan_tiers,
    tier_for,
)
from sdd_reverse.db_wave_planner import (  # noqa: E402
    plan_waves,
    resolve_calls,
    strongly_connected,
)
from sdd_reverse.sql_body_analyzer import (  # noqa: E402
    complexity_reasons,
    confidence_with_graph,
    proc_complexity,
)


# --------------------------------------------------------------------------- #
# Fixtures — a small but representative catalog
# --------------------------------------------------------------------------- #

def _obj(fq, rtype="SQL_STORED_PROCEDURE", **kw):
    schema, name = fq.split(".", 1)
    return {
        "fqName": fq, "schema": schema, "name": name, "routineType": rtype,
        "encrypted": kw.get("encrypted", False), "lineCount": kw.get("lines", 20),
        "params": kw.get("params", []),
        "tablesRead": kw.get("read", []), "tablesWritten": kw.get("written", []),
        "writeKinds": kw.get("kinds", {}), "callsProcs": kw.get("calls", []),
        "branches": kw.get("branches", 0), "cursors": 0,
        "raises": kw.get("raises", []), "hasTransaction": kw.get("txn", False),
        "hasTryCatch": False, "dynamicSql": kw.get("dyn", False),
        "snapshotFile": f".sys/proc-snapshot/{fq}.sql",
        "evidence": f".sys/proc-snapshot/{fq}.sql:L1-{kw.get('lines', 20)}",
        "confidenceEstimate": kw.get("conf", "high"),
    }


def _wide_table_context():
    """Une grosse procédure : 3 tables larges, index, CHECK, clés étrangères.

    Assez volumineuse pour que le budget morde vraiment, ce qui est le seul
    moyen d'observer l'échelle de dégradation plutôt que de la supposer.
    """
    tables = ["dbo.Commande", "dbo.Client", "dbo.Ligne"]

    def entity(q):
        return {
            "qualifiedName": q,
            "name": q.split(".", 1)[1],
            "fields": [
                {"name": f"Colonne_{i}", "type": "nvarchar(200)",
                 "primaryKey": i == 0, "nullable": i % 2 == 0,
                 "default": "(getdate())" if i % 3 == 0 else None}
                for i in range(14)
            ],
        }

    schema = {
        "completeness": "live",
        "entities": [entity(t) for t in tables],
        "relations": [
            {"name": f"FK_Ligne_{i}",
             "from": {"entity": "dbo.Ligne", "field": "CommandeId"},
             "to": {"entity": "dbo.Commande", "field": "Id"}}
            for i in range(3)
        ],
        "indexes": [
            {"table": t, "name": f"IX_{t}_{i}", "columns": [f"Colonne_{i}"],
             "unique": i == 0, "primary": False}
            for t in tables for i in range(4)
        ],
        "checks": [
            {"table": t, "name": f"CK_{t}_Statut",
             "definition": "([Statut] IN (1,2,3))"}
            for t in tables
        ],
    }
    introspection = {
        "schemaVersion": 1, "databaseType": "sqlserver", "languageId": "tsql",
        "database": "SalesDb",
        "procedures": [
            _obj("dbo.usp_Gros", lines=300, read=tables,
                 written=["dbo.Commande"], kinds={"UPDATE": ["dbo.Commande"]},
                 calls=["dbo.usp_A", "dbo.usp_B"]),
            _obj("dbo.usp_A", lines=20),
            _obj("dbo.usp_B", lines=20),
            _obj("dbo.usp_Appelant", lines=20, calls=["dbo.usp_Gros"]),
        ],
    }
    return build_context(introspection, schema, project="SalesDb")


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
            # The orchestrator: short, branchless, one write — "simple" under
            # the pre-2026-08-26 rubric, and the reason this rework exists.
            _obj("dbo.usp_Commande_Valider", lines=38, written=["dbo.Commande"],
                 kinds={"INSERT": ["dbo.Commande"]},
                 calls=["dbo.usp_Stock_Reserve", "dbo.fn_CalcTVA", "ext.usp_Ghost"]),
            _obj("dbo.v_LigneVente", "VIEW", lines=8,
                 read=["dbo.Commande", "dbo.Produit"]),
            _obj("dbo.trg_Commande_Audit", "SQL_TRIGGER", lines=20,
                 written=["dbo.Audit"], kinds={"INSERT": ["dbo.Audit"]}),
        ],
    }


def _entity(q, cols):
    schema, name = q.split(".", 1)
    return {
        "name": name, "table": name, "schema": schema, "qualifiedName": q,
        "evidence": [f".sys/schema-snapshot/{q}.sql:1"],
        "fields": [{"name": c, "type": t, "primaryKey": pk, "nullable": False,
                    "identity": False, "computed": False, "default": None}
                   for c, t, pk in cols],
    }


@pytest.fixture
def schema():
    return {
        "schemaVersion": 1, "completeness": "live", "databaseType": "sqlserver",
        "database": "SalesDb",
        "entities": [
            _entity("dbo.Commande", [("Id", "int", True), ("Total", "decimal(18,2)", False)]),
            _entity("dbo.Stock", [("ProduitId", "int", True), ("Qte", "int", False)]),
            _entity("dbo.Produit", [("Id", "int", True), ("Libelle", "nvarchar(200)", False)]),
            _entity("dbo.Audit", [("Id", "int", True)]),
            _entity("dbo.TauxTVA", [("Code", "char(2)", True), ("Taux", "decimal(5,4)", False)]),
        ],
        "relations": [{"name": "FK_Stock_Produit",
                       "from": {"entity": "dbo.Stock", "field": "ProduitId"},
                       "to": {"entity": "dbo.Produit", "field": "Id"},
                       "type": "many-to-one", "evidence": "catalog"}],
        "indexes": [],
        "checks": [{"name": "CK_Stock_Qte", "table": "dbo.Stock",
                    "definition": "([Qte]>=(0))", "evidence": "catalog"}],
        "views": [], "triggers": [], "catalogObjects": [], "summary": {},
    }


# --------------------------------------------------------------------------- #
# Wave planner
# --------------------------------------------------------------------------- #

class TestWavePlanner:

    def test_callees_are_planned_before_their_callers(self, introspection):
        plan = plan_waves(introspection["procedures"])
        wave_of = {fq: m["wave"] for fq, m in plan["metrics"].items()}
        assert wave_of["dbo.fn_CalcTVA"] < wave_of["dbo.usp_Commande_Valider"]
        assert wave_of["dbo.usp_Stock_Reserve"] < wave_of["dbo.usp_Commande_Valider"]

    def test_unresolved_callee_is_reported_not_invented(self, introspection):
        plan = plan_waves(introspection["procedures"])
        assert plan["unresolvedCallees"]["dbo.usp_Commande_Valider"] == ["ext.usp_Ghost"]
        # It must NOT have become a graph node: a phantom node would silently
        # reorder the plan around an object that does not exist.
        assert "ext.usp_Ghost" not in plan["metrics"]

    def test_ambiguous_bare_name_stays_unresolved(self):
        objs = [_obj("dbo.usp_Do"), _obj("sales.usp_Do"), _obj("dbo.usp_Caller", calls=["usp_Do"])]
        _, unresolved = resolve_calls(objs)
        assert unresolved["dbo.usp_Caller"] == ["usp_Do"]

    def test_unambiguous_bare_name_resolves(self):
        objs = [_obj("dbo.usp_Do"), _obj("dbo.usp_Caller", calls=["usp_Do"])]
        edges, unresolved = resolve_calls(objs)
        assert ("dbo.usp_Caller", "dbo.usp_Do") in edges
        assert unresolved == {}

    def test_mutual_recursion_is_one_component_in_one_wave(self):
        objs = [_obj("dbo.usp_A", calls=["dbo.usp_B"]), _obj("dbo.usp_B", calls=["dbo.usp_A"])]
        plan = plan_waves(objs)
        comp = [c for c in plan["components"] if len(c["members"]) == 2]
        assert comp and comp[0]["recursive"]
        assert plan["metrics"]["dbo.usp_A"]["wave"] == plan["metrics"]["dbo.usp_B"]["wave"]

    def test_self_recursion_is_flagged(self):
        plan = plan_waves([_obj("dbo.usp_Self", calls=["dbo.usp_Self"])])
        assert plan["metrics"]["dbo.usp_Self"]["recursive"] is True

    def test_deep_chain_does_not_blow_the_stack(self):
        chain = [_obj(f"dbo.p{i}", calls=[f"dbo.p{i - 1}"] if i else []) for i in range(400)]
        plan = plan_waves(chain)
        assert plan["metrics"]["dbo.p399"]["wave"] == 399

    def test_fan_in_counts_distinct_callers(self, introspection):
        plan = plan_waves(introspection["procedures"])
        assert plan["metrics"]["dbo.fn_CalcTVA"]["fanIn"] == 1

    def test_strongly_connected_covers_every_node_once(self, introspection):
        objs = introspection["procedures"]
        nodes = [o["fqName"] for o in objs]
        adj = {n: [] for n in nodes}
        comps = strongly_connected(nodes, adj)
        assert sorted(m for c in comps for m in c) == sorted(nodes)


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #

class TestFacts:

    def test_crud_matrix_distinguishes_create_from_update(self, introspection, schema):
        facts = build_facts(introspection, schema)
        assert facts["crud"]["dbo.usp_Commande_Valider"]["dbo.Commande"] == "C"
        assert facts["crud"]["dbo.usp_Stock_Reserve"]["dbo.Stock"] == "U"
        assert facts["crud"]["dbo.usp_Stock_Reserve"]["dbo.Produit"] == "R"

    def test_merge_is_reported_as_all_three_effects(self):
        intro = {"procedures": [_obj("dbo.usp_Merge", written=["dbo.T"],
                                     kinds={"MERGE": ["dbo.T"]})]}
        facts = build_facts(intro, None)
        assert set(facts["crud"]["dbo.usp_Merge"]["dbo.T"]) == set("CUD")

    def test_write_without_verb_degrades_to_W_not_to_a_guess(self):
        intro = {"procedures": [_obj("dbo.usp_Old", written=["dbo.T"], kinds={})]}
        facts = build_facts(intro, None)
        assert facts["crud"]["dbo.usp_Old"]["dbo.T"] == "W"

    def test_table_metrics_identify_pivot_tables(self, introspection, schema):
        facts = build_facts(introspection, schema)
        # Commande is written by the orchestrator and read by the view.
        assert facts["tableMetrics"]["dbo.Commande"]["objects"] == 2
        assert facts["tableMetrics"]["dbo.Commande"]["writers"] == 1
        assert facts["tableMetrics"]["dbo.Commande"]["readers"] == 1

    def test_checks_travel_with_their_table(self, introspection, schema):
        facts = build_facts(introspection, schema)
        stock = next(t for t in facts["tables"] if t["qualifiedName"] == "dbo.Stock")
        assert stock["checks"][0]["definition"] == "([Qte]>=(0))"

    def test_no_credentials_reach_the_context(self, introspection, schema):
        introspection["server"] = "prod-sql-01"
        facts = build_facts(introspection, schema)
        assert "server" not in facts["database"]
        assert "prod-sql-01" not in json.dumps(facts)


# --------------------------------------------------------------------------- #
# Version, reuse and drift
# --------------------------------------------------------------------------- #

class TestVersioning:

    def test_version_is_stable_across_identical_builds(self, introspection, schema):
        a = context_version(build_facts(introspection, schema))
        b = context_version(build_facts(introspection, schema))
        assert a == b and a.startswith("sha256:")

    def test_version_changes_when_a_column_is_added(self, introspection, schema):
        before = context_version(build_facts(introspection, schema))
        schema["entities"][0]["fields"].append(
            {"name": "Remise", "type": "decimal(5,2)", "primaryKey": False,
             "nullable": True, "identity": False, "computed": False, "default": None})
        assert context_version(build_facts(introspection, schema)) != before

    def test_unchanged_database_reuses_the_architect_interpretation(self, introspection, schema):
        first = build_context(introspection, schema, project="SalesDb")
        first = merge_architect_output(first, {"glossary": [{"term": "Commande", "meaning": "…"}]})
        second = build_context(introspection, schema, project="SalesDb", prior=first)
        assert second["reuse"]["reused"] is True
        assert second["hypotheses"]["glossary"][0]["term"] == "Commande"

    def test_changed_database_drops_stale_interpretation(self, introspection, schema):
        first = build_context(introspection, schema, project="SalesDb")
        first = merge_architect_output(first, {"glossary": [{"term": "Commande", "meaning": "…"}]})
        introspection["procedures"][0]["lineCount"] = 999
        second = build_context(introspection, schema, project="SalesDb", prior=first)
        assert second["reuse"]["reused"] is False
        assert second["hypotheses"]["glossary"] == []
        assert second["reuse"]["staleHypotheses"] is True

    def test_architect_cannot_write_facts(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        tampered = merge_architect_output(
            ctx, {"glossary": [], "facts": {"tables": []}, "executionPlan": {}})
        assert tampered["facts"]["summary"]["tables"] == 5
        assert tampered["executionPlan"]["stats"]["objects"] == 5

    def test_diff_names_the_objects_to_re_analyse(self, introspection, schema):
        before = build_context(introspection, schema, project="SalesDb")
        schema["entities"][0]["fields"].append(
            {"name": "Remise", "type": "decimal(5,2)", "primaryKey": False,
             "nullable": True, "identity": False, "computed": False, "default": None})
        introspection["procedures"][1]["callsProcs"] = ["dbo.fn_CalcTVA"]
        after = build_context(introspection, schema, project="SalesDb")
        d = diff_contexts(before, after)
        assert d["identical"] is False
        assert d["tables"]["changed"][0]["columnsAdded"] == ["Remise"]
        assert "dbo.usp_Stock_Reserve" in d["reAnalysisRequired"]

    def test_diff_of_identical_contexts_is_empty(self, introspection, schema):
        a = build_context(introspection, schema, project="SalesDb")
        b = build_context(introspection, schema, project="SalesDb")
        d = diff_contexts(a, b)
        assert d["identical"] is True
        assert d["reAnalysisRequired"] == []


# --------------------------------------------------------------------------- #
# Slicing
# --------------------------------------------------------------------------- #

class TestSlicing:

    def test_pack_carries_callee_context_across_module_boundaries(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        body, report = build_pack(ctx, "dbo.usp_Commande_Valider")
        assert report["trimmed"] == []
        assert "dbo.usp_Stock_Reserve" in body
        assert "dbo.fn_CalcTVA" in body

    def test_pack_prefers_an_already_written_summary_over_raw_signals(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        ctx = record_finding(ctx, "dbo.usp_Stock_Reserve", {
            "summary": "Réserve le stock ou rejette la commande.",
            "businessRules": ["Rejet si quantité insuffisante"],
            "confidence": "high"})
        body, _ = build_pack(ctx, "dbo.usp_Commande_Valider")
        assert "Réserve le stock ou rejette la commande." in body
        assert "Rejet si quantité insuffisante" in body

    def test_pack_declares_what_it_trimmed(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        body, report = build_pack(ctx, "dbo.usp_Commande_Valider", budget=900)
        assert report["trimmed"]
        assert "Pack tronqué" in body

    def test_unresolved_callee_is_marked_in_the_pack(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        body, _ = build_pack(ctx, "dbo.usp_Commande_Valider")
        assert "ext.usp_Ghost" in body and "non résolu" in body

    def test_pack_of_unknown_object_fails_loudly(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        _, report = build_pack(ctx, "dbo.nope")
        assert report["found"] is False

    def test_recursive_cycle_is_announced_as_one_block(self):
        objs = [_obj("dbo.usp_A", calls=["dbo.usp_B"]), _obj("dbo.usp_B", calls=["dbo.usp_A"])]
        ctx = build_context({"procedures": objs}, None, project="X")
        body, _ = build_pack(ctx, "dbo.usp_A")
        assert "Cycle à analyser d'un bloc" in body

    # --- ordre de réduction du pack (audit 2026-08-28) --------------------- #
    #
    # Ce que le pack sacrifie en premier n'est pas un détail d'implémentation :
    # une colonne ou une clé étrangère inconnue rend l'AC faux, alors qu'un
    # appelé non lu laisse un nom et une matrice CRUD exploitables. Ces tests
    # verrouillent cet arbitrage.

    def test_callees_are_given_up_before_table_structure(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        full, _ = build_pack(ctx, "dbo.usp_Commande_Valider", budget=10 ** 9)
        body, report = build_pack(
            ctx, "dbo.usp_Commande_Valider", budget=int(len(full) * 0.8))
        assert "callees" in report["trimmed"]
        assert "Structure des tables touchées" in body

    def test_table_card_degrades_by_steps_instead_of_vanishing(self):
        ctx = _wide_table_context()
        full, _ = build_pack(ctx, "dbo.usp_Gros", budget=10 ** 9)
        body, report = build_pack(ctx, "dbo.usp_Gros", budget=int(len(full) * 0.85))
        # L'ensemble porteur survit : colonnes, PK, clés étrangères, CHECK.
        assert report["tableDetail"] in ("no-index", "keys-only")
        assert "Colonne_0" in body and "## Relations" in body
        assert "Contraintes CHECK" in body
        assert "## Index" not in body           # premier palier retiré

    def test_last_resort_drops_tables_one_at_a_time_writes_last(self):
        ctx = _wide_table_context()
        full, _ = build_pack(ctx, "dbo.usp_Gros", budget=10 ** 9)
        _, report = build_pack(ctx, "dbo.usp_Gros", budget=int(len(full) * 0.55))
        dropped = [t.split(":-", 1)[1] for t in report["trimmed"]
                   if t.startswith("tables:-")]
        assert dropped, "les tables doivent partir une par une, pas en bloc"
        # dbo.Commande est écrite : elle est la dernière à tomber.
        assert dropped[0] != "dbo.Commande"

    def test_dropped_table_is_named_not_silently_missing(self):
        ctx = _wide_table_context()
        full, _ = build_pack(ctx, "dbo.usp_Gros", budget=10 ** 9)
        body, report = build_pack(ctx, "dbo.usp_Gros", budget=int(len(full) * 0.55))
        assert any(t.startswith("tables:-") for t in report["trimmed"])
        assert "n'a PAS été lue" in body

    def test_table_card_on_disk_keeps_full_detail(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        card = render_table_card(ctx, "dbo.Commande")
        assert "Défaut" in card

    def test_family_routing_puts_each_object_in_its_folder(self):
        assert family_of("SQL_SCALAR_FUNCTION") == "functions"
        assert family_of("VIEW") == "views"
        assert family_of("SQL_TRIGGER") == "triggers"
        assert family_of("SQL_STORED_PROCEDURE") == "procedures"

    def test_overview_states_what_it_does_not_know(self, introspection, schema):
        ctx = build_context(introspection, schema, project="SalesDb")
        md = render_overview(ctx)
        assert "n'a pas encore tourné" in md
        assert "Appels non résolus" in md

    def test_tree_layout_is_one_file_per_object(self, introspection, schema, tmp_path):
        ctx = build_context(introspection, schema, project="SalesDb")
        report = write_context_tree(tmp_path, ctx)
        root = tmp_path / ".sys" / "db-context"
        assert (root / "_overview.md").is_file()
        assert (root / "tables" / "dbo.Commande.md").is_file()
        assert (root / "functions" / "dbo.fn_CalcTVA.md").is_file()
        assert (root / "views" / "dbo.v_LigneVente.md").is_file()
        assert (root / "triggers" / "dbo.trg_Commande_Audit.md").is_file()
        assert (root / "packs" / "dbo.usp_Commande_Valider.md").is_file()
        assert report["written"]["tables"] == 5


# --------------------------------------------------------------------------- #
# Routing — the defect this rework exists to close
# --------------------------------------------------------------------------- #

class TestCallAwareRouting:

    ORCHESTRATOR = {
        "lineCount": 38, "branches": 0, "raises": [], "cursors": 0,
        "dynamicSql": False, "tablesWritten": ["dbo.Commande"],
        "params": ["@commandeId INT"], "hasTransaction": False,
        "callsProcs": ["dbo.usp_Stock_Reserve", "dbo.fn_CalcTVA"],
        "unresolvedCallees": [], "recursive": False, "fanIn": 0,
    }
    LEAF = {
        "lineCount": 12, "branches": 0, "raises": [], "cursors": 0,
        "dynamicSql": False, "tablesWritten": [], "params": ["@montant DECIMAL"],
        "hasTransaction": False, "callsProcs": [], "unresolvedCallees": [],
        "recursive": False, "fanIn": 1,
    }

    def test_orchestrator_is_no_longer_classified_simple(self):
        assert proc_complexity(self.ORCHESTRATOR) == "complex"
        assert "calls=2" in complexity_reasons(self.ORCHESTRATOR)

    def test_trivial_leaf_stays_free(self):
        # The token saving of the deterministic path must not regress: a genuine
        # CRUD leaf still costs nothing.
        assert proc_complexity(self.LEAF) == "simple"
        assert complexity_reasons(self.LEAF) == []

    def test_heavily_used_object_earns_an_llm_read(self):
        hub = dict(self.LEAF, fanIn=7)
        assert proc_complexity(hub) == "complex"

    def test_unresolved_callee_downgrades_confidence(self):
        rec = dict(self.ORCHESTRATOR, unresolvedCallees=["ext.usp_Ghost"])
        assert confidence_with_graph("high", rec) == "medium"

    def test_recursion_downgrades_confidence(self):
        assert confidence_with_graph("high", dict(self.LEAF, recursive=True)) == "medium"

    def test_graph_confidence_only_ever_lowers(self):
        assert confidence_with_graph("low", {"unresolvedCallees": ["x"]}) == "low"
        assert confidence_with_graph("high", None) == "high"
        assert confidence_with_graph("high", self.LEAF) == "high"


# --------------------------------------------------------------------------- #
# Model tier routing — a tier, never a model name
# --------------------------------------------------------------------------- #

class TestTierRouting:

    TRIVIAL = {"fqName": "dbo.usp_Get", "lineCount": 9, "branches": 0,
               "params": ["@id INT"], "tablesWritten": [], "callsProcs": []}
    GUARDED = {"fqName": "dbo.usp_Find", "lineCount": 30, "branches": 2,
               "raises": ["RAISERROR"], "params": ["@id INT"],
               "tablesWritten": [], "callsProcs": []}
    RULE = {"fqName": "dbo.usp_Reserve", "lineCount": 90, "branches": 6,
            "raises": ["THROW"], "tablesWritten": ["dbo.Stock"],
            "hasTransaction": True, "params": ["@a", "@b"], "callsProcs": []}
    ORCHESTRATOR = {"fqName": "dbo.usp_Valider", "lineCount": 38, "branches": 0,
                    "tablesWritten": ["dbo.Cmd"], "params": ["@id"],
                    "callsProcs": ["a", "b", "c"], "unresolvedCallees": ["ext.x"]}

    def test_trivial_object_costs_nothing(self):
        assert tier_for(self.TRIVIAL) == ("none", [])

    def test_tier_escalates_with_what_the_body_hides(self):
        assert tier_for(self.GUARDED)[0] == "fast"
        assert tier_for(self.RULE)[0] == "balanced"
        assert tier_for(self.ORCHESTRATOR)[0] == "deep"

    def test_dynamic_sql_always_reaches_the_deep_tier(self):
        rec = dict(self.TRIVIAL, dynamicSql=True)
        tier, reasons = tier_for(rec)
        assert tier == "deep" and "dynamic-sql" in reasons

    def test_encrypted_body_is_never_sent_to_a_model(self):
        tier, reasons = tier_for({"fqName": "dbo.usp_Enc", "encrypted": True})
        assert tier == "none" and reasons == ["encrypted-body"]

    def test_every_tier_decision_states_its_reason(self):
        for rec in (self.GUARDED, self.RULE, self.ORCHESTRATOR):
            tier, reasons = tier_for(rec)
            assert tier != "none" and reasons

    def test_router_never_names_a_model(self):
        # The mapping tier -> model belongs to .sdd/providers/*.yaml. A model
        # name leaking into the router would silently bind db-reverse to one
        # vendor.
        source = Path(PY_ROOT / "sdd_reverse" / "db_tier_router.py").read_text(encoding="utf-8")
        code = "\n".join(l for l in source.splitlines()
                         if not l.strip().startswith("#"))
        code = code.split('"""')[0] + '"""'.join(code.split('"""')[2:])
        for vendor in ("claude-", "gpt-", "gemini-", "kimi-", "o1", "opus", "sonnet", "haiku"):
            assert vendor not in code.lower(), f"model name {vendor!r} leaked into the router"

    def test_clamp_respects_agent_bounds(self):
        assert clamp("deep", "none", "balanced") == "balanced"
        assert clamp("none", "balanced", "deep") == "balanced"
        assert clamp("fast", "none", "deep") == "fast"

    def test_unknown_tier_fails_safe_upward(self):
        # An unrecognised grade must never be treated as "free": that would
        # silently skip an object no one graded.
        assert clamp("wat") == "deep"

    def test_plan_reports_the_cost_shape(self):
        plan = plan_tiers([self.TRIVIAL, self.GUARDED, self.RULE, self.ORCHESTRATOR])
        assert plan["counts"] == {"none": 1, "fast": 1, "balanced": 1, "deep": 1}
        assert plan["stats"]["freeShare"] == 0.25
        assert plan["stats"]["deepShare"] == 0.25

    def test_plan_records_when_a_grade_was_clamped(self):
        plan = plan_tiers([self.ORCHESTRATOR], ceiling="balanced")
        g = plan["grades"]["dbo.usp_Valider"]
        assert g["routedTier"] == "deep" and g["tier"] == "balanced" and g["clamped"]


# --------------------------------------------------------------------------- #
# Dispatch contract — what the orchestrator receives to route on
# --------------------------------------------------------------------------- #

class TestDispatchContract:

    def test_every_family_has_exactly_one_owning_specialist(self):
        from sdd_reverse_scripts.build_proc_us import _AGENT_BY_FAMILY
        assert set(_AGENT_BY_FAMILY) == {"procedures", "functions", "views", "triggers"}
        # No family shares an agent: the angle of analysis is what justifies a
        # separate agent, so two families pointing at one agent would mean one
        # of them is not really specialised.
        assert len(set(_AGENT_BY_FAMILY.values())) == 4

    def test_routine_types_route_to_their_specialist(self):
        from sdd_reverse_scripts.build_proc_us import _AGENT_BY_FAMILY
        cases = {
            "SQL_STORED_PROCEDURE": "reverse-sql-analyst",
            "SQL_SCALAR_FUNCTION": "reverse-sql-function-analyst",
            "SQL_INLINE_TABLE_VALUED_FUNCTION": "reverse-sql-function-analyst",
            "VIEW": "reverse-sql-view-analyst",
            "SQL_TRIGGER": "reverse-sql-trigger-analyst",
        }
        for routine_type, expected in cases.items():
            assert _AGENT_BY_FAMILY[family_of(routine_type)] == expected

    def test_unknown_routine_type_falls_back_to_procedures(self):
        from sdd_reverse_scripts.build_proc_us import _AGENT_BY_FAMILY
        # Fail-safe: an unrecognised catalog type still gets analysed, by the
        # most general specialist, rather than being silently dropped.
        assert _AGENT_BY_FAMILY[family_of("SOMETHING_NEW")] == "reverse-sql-analyst"


# --------------------------------------------------------------------------- #
# End-to-end — the Phase 0 CLI, on disk, offline
# --------------------------------------------------------------------------- #

class TestPhase0EndToEnd:
    """Exercises db_context_build.py the way the orchestrator calls it.

    No database, no driver: the two inputs are the artefacts the read-only
    introspection already wrote. This is the closest offline equivalent to a
    live run — the live validation against a real SQL Server remains open.
    """

    @staticmethod
    def _project(tmp_path, introspection, schema):
        root = tmp_path / "SalesDb"
        (root / ".sys").mkdir(parents=True)
        (root / ".sys" / "db-introspection.json").write_text(
            json.dumps(introspection), encoding="utf-8")
        (root / ".sys" / "db-schema.json").write_text(
            json.dumps(schema), encoding="utf-8")
        return root

    def _run(self, *args):
        from sdd_reverse_scripts.db_context_build import main
        return main(list(args))

    def test_build_writes_context_and_sliced_tree(self, tmp_path, introspection, schema):
        root = self._project(tmp_path, introspection, schema)
        assert self._run("--project", str(root)) == 0
        ctx = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        assert ctx["contextVersion"].startswith("sha256:")
        assert ctx["facts"]["summary"]["objects"] == 5
        assert ctx["executionPlan"]["stats"]["waveCount"] >= 2
        tree = root / ".sys" / "db-context"
        assert (tree / "_overview.md").is_file()
        assert (tree / "packs" / "dbo.usp_Commande_Valider.md").is_file()

    def test_second_run_on_unchanged_database_reuses_the_context(
            self, tmp_path, introspection, schema):
        root = self._project(tmp_path, introspection, schema)
        self._run("--project", str(root))
        first = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        self._run("--project", str(root))
        second = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        assert second["contextVersion"] == first["contextVersion"]
        assert second["reuse"]["reused"] is True

    def test_architect_output_merges_without_touching_facts(
            self, tmp_path, introspection, schema):
        root = self._project(tmp_path, introspection, schema)
        self._run("--project", str(root))
        ctx_path = root / ".sys" / "db-context.json"
        before = json.loads(ctx_path.read_text(encoding="utf-8"))

        hyp_path = root / ".sys" / "db-context.hypotheses.json"
        hyp_path.write_text(json.dumps({
            "contextVersion": before["contextVersion"],
            "glossary": [{"term": "dbo.Commande", "meaning": "Engagement d'achat",
                          "confidence": "medium"}],
            "objectRoles": [{"object": "dbo.usp_Commande_Valider",
                             "role": "orchestrateur", "rationale": "délègue"}],
            "openQuestions": [{"about": "dbo.usp_Commande_Valider",
                               "question": "ext.usp_Ghost est-il encore utilisé ?"}],
            # A hostile architect trying to rewrite the fact layer:
            "facts": {"tables": [], "summary": {"tables": 0}},
            "executionPlan": {"waves": []},
        }, ensure_ascii=False), encoding="utf-8")

        assert self._run("--project", str(root),
                         "--merge-hypotheses", str(hyp_path)) == 0
        after = json.loads(ctx_path.read_text(encoding="utf-8"))
        assert after["facts"] == before["facts"]
        assert after["executionPlan"] == before["executionPlan"]
        assert after["hypotheses"]["glossary"][0]["term"] == "dbo.Commande"

    def test_merged_hypotheses_reach_the_pack_marked_as_such(
            self, tmp_path, introspection, schema):
        root = self._project(tmp_path, introspection, schema)
        self._run("--project", str(root))
        ctx = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        hyp_path = root / ".sys" / "db-context.hypotheses.json"
        hyp_path.write_text(json.dumps({
            "contextVersion": ctx["contextVersion"],
            "objectRoles": [{"object": "dbo.usp_Commande_Valider",
                             "role": "orchestrateur", "rationale": "délègue à 2 objets"}],
        }, ensure_ascii=False), encoding="utf-8")
        self._run("--project", str(root), "--merge-hypotheses", str(hyp_path))
        pack = (root / ".sys" / "db-context" / "packs"
                / "dbo.usp_Commande_Valider.md").read_text(encoding="utf-8")
        assert "kind: hypothesis" in pack
        assert "orchestrateur" in pack

    def test_stale_architect_output_is_refused(self, tmp_path, introspection, schema):
        root = self._project(tmp_path, introspection, schema)
        self._run("--project", str(root))
        hyp_path = root / ".sys" / "db-context.hypotheses.json"
        hyp_path.write_text(json.dumps({
            "contextVersion": "sha256:0000000000000000",
            "glossary": [{"term": "obsolete", "meaning": "lu sur une base d'avant"}],
        }), encoding="utf-8")
        # Attaching a stale reading to fresh facts is worse than having none.
        assert self._run("--project", str(root),
                         "--merge-hypotheses", str(hyp_path)) == 1
        ctx = json.loads((root / ".sys" / "db-context.json").read_text(encoding="utf-8"))
        assert ctx["hypotheses"]["glossary"] == []

    def test_missing_introspection_fails_fast(self, tmp_path):
        empty = tmp_path / "Nothing"
        (empty / ".sys").mkdir(parents=True)
        assert self._run("--project", str(empty)) == 1

    def test_diff_exits_4_on_drift_and_names_what_to_re_analyse(
            self, tmp_path, introspection, schema):
        root = self._project(tmp_path, introspection, schema)
        self._run("--project", str(root))
        previous = tmp_path / "previous.json"
        previous.write_text(
            (root / ".sys" / "db-context.json").read_text(encoding="utf-8"),
            encoding="utf-8")

        # The database moves: a column appears, a procedure gains a call.
        intro = json.loads(
            (root / ".sys" / "db-introspection.json").read_text(encoding="utf-8"))
        for o in intro["procedures"]:
            if o["fqName"] == "dbo.usp_Stock_Reserve":
                o["callsProcs"] = ["dbo.fn_CalcTVA"]
        (root / ".sys" / "db-introspection.json").write_text(
            json.dumps(intro), encoding="utf-8")

        assert self._run("--project", str(root), "--diff-against", str(previous)) == 4
        # ...and an unchanged database reports no drift.
        self._run("--project", str(root))
        current = tmp_path / "current.json"
        current.write_text(
            (root / ".sys" / "db-context.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        assert self._run("--project", str(root), "--diff-against", str(current)) == 0


# --------------------------------------------------------------------------- #
# Regressions found by running against a REAL database (2026-08-27)
# --------------------------------------------------------------------------- #

class TestRealRunRegressions:
    """Defects only a live base surfaced — synthetic catalogs never showed them."""

    def test_execute_as_is_a_security_clause_not_a_call(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        # SQL Server's own SSMS diagram procedures carry `WITH EXECUTE AS 'dbo'`
        # and `execute as caller;`. Both used to yield a phantom callee "AS",
        # which then downgraded confidence and forced an LLM read for nothing.
        for body in ("WITH EXECUTE AS 'dbo' AS BEGIN SELECT 1 END",
                     "execute as caller; SELECT 1",
                     "WITH EXECUTE AS OWNER BEGIN SELECT 1 END",
                     "EXEC AS LOGIN = 'sa'"):
            assert analyze_routine("dbo.x", body)["calls"] == [], body

    def test_real_calls_still_detected_next_to_execute_as(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        cases = {
            "EXEC dbo.usp_Reserve @id;": ["dbo.usp_Reserve"],
            "EXECUTE @rc = dbo.usp_X @a;": ["dbo.usp_X"],
            "WITH EXECUTE AS OWNER BEGIN EXEC dbo.usp_Y END": ["dbo.usp_Y"],
            "execute as caller; EXEC dbo.usp_Z": ["dbo.usp_Z"],
        }
        for body, expected in cases.items():
            assert analyze_routine("dbo.x", body)["calls"] == expected, body

    def test_phantom_callee_would_have_cost_a_tier_and_a_confidence(self):
        # Guards the blast radius, not just the regex: a phantom unresolved
        # callee is not cosmetic — it degrades confidence and buys an LLM.
        from sdd_reverse.sql_body_analyzer import confidence_with_graph
        from sdd_reverse.db_tier_router import tier_for
        phantom = {"fqName": "dbo.sp_creatediagram", "lineCount": 20, "branches": 0,
                   "params": [], "tablesWritten": [], "callsProcs": ["AS"],
                   "unresolvedCallees": ["AS"]}
        clean = dict(phantom, callsProcs=[], unresolvedCallees=[])
        assert confidence_with_graph("high", phantom) == "medium"
        assert confidence_with_graph("high", clean) == "high"
        assert tier_for(phantom)[0] == "deep"
        assert tier_for(clean)[0] == "none"

    def test_bold_acceptance_criteria_are_still_covered(self):
        # `- **AC-1** :` and `- AC-1:` must both reach the FEAT Covers back-fill.
        from sdd_reverse_scripts.build_proc_feats import _AC_ID_RE
        both = ("- AC-1: Given x, when y, then z.\n"
                "- **AC-2** : Given a, when b, then c.\n"
                "-  **AC-3**: Given d, when e, then f.\n")
        assert _AC_ID_RE.findall(both) == ["AC-1", "AC-2", "AC-3"]

    def test_line_count_matches_the_file_on_disk(self):
        # The evidence contract is `file:Lstart-Lend` resolved ON DISK. A
        # lineCount that overcounts by one makes every range point past EOF.
        from sdd_reverse.sql_body_analyzer import analyze_routine
        cases = {"": 0, "SELECT 1": 1, "SELECT 1\n": 1,
                 "a\nb\n": 2, "a\r\nb\r\n": 2, "a\nb": 2, "\n": 1}
        for body, expected in cases.items():
            assert analyze_routine("dbo.x", body)["lineCount"] == expected, repr(body)

    def test_line_count_agrees_with_splitlines_on_any_body(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        for body in ("CREATE PROC p AS\nBEGIN\n  SELECT 1\nEND\n",
                     "CREATE PROC p AS\r\nBEGIN\r\nEND",
                     "-- only a comment\n"):
            assert analyze_routine("dbo.x", body)["lineCount"] == len(body.splitlines())
