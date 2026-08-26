"""Dynamic module clustering of a DB reverse — profiling, AUTO switch, folding.

Audit 2026-08-25. `proc_module_clusterer` decides the FEAT découpage of an
entire database ("1 module = 1 FEAT"), and three of its pieces shipped with no
test at all:

  * `learn_name_profile` — infers a database's OWN naming structure from
    statistics instead of a hard-coded vocabulary. Get it wrong and it erases a
    real business object (the first version classified `Client` as structural).
  * the AUTO strategy switch — falls back from names to dependency cohesion when
    the names do not group. Get it wrong and either a clean database loses its
    readable module names, or an unstructured one silently produces one FEAT per
    stored procedure.
  * sub-object folding — `ClientAdresse` into `Client`.

They are all pure functions over routine names, so everything here is offline
and deterministic; no database, no driver, no fixtures on disk.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse import proc_module_clusterer as pmc  # noqa: E402
from sdd_reverse.proc_module_clusterer import (  # noqa: E402
    cluster,
    cluster_with_report,
    learn_name_profile,
    parse_routine_name,
)


def _routines(*names, **signals):
    """Routine records in the shape `build_inventory` feeds the clusterer."""
    return [{"name": n, "signals": dict(signals.get(n, {}))} for n in names]


# --------------------------------------------------------------------------- #
# learn_name_profile
# --------------------------------------------------------------------------- #

class TestLearnNameProfile(unittest.TestCase):

    def test_small_corpus_is_not_profiled(self):
        """Below the floor, statistics are noise — say so instead of guessing."""
        profile = learn_name_profile(["usp_Client_Get", "usp_Client_Insert"])
        self.assertFalse(profile["usable"])
        self.assertEqual(profile["structural"], set())
        self.assertEqual(profile["actions"], set())
        self.assertIn("reason", profile["stats"])

    def test_empty_corpus_is_not_profiled(self):
        profile = learn_name_profile([])
        self.assertFalse(profile["usable"])
        self.assertEqual(profile["stats"]["names"], 0)

    def test_discovers_subsystem_markers(self):
        """`BI` is frequent and never the head noun -> structural.

        `SP` / `STP` deliberately do NOT appear here: routine-type markers are
        already in `_NOISE`, and the profiler skips a segment the static
        vocabularies already handle rather than classifying it twice.
        """
        names = [
            "SP_BI_Campgne_Select", "SP_BI_Campgne_DeleteById",
            "SP_BI_Facture_Select", "STP_BI_Facture_Insert",
            "STP_BI_Contact_Select", "STP_BI_Contact_Update",
            "SP_BI_Devis_Select", "SP_BI_Devis_Insert",
            "SP_BI_Avoir_Select", "STP_BI_Avoir_Update",
        ]
        profile = learn_name_profile(names)
        self.assertTrue(profile["usable"])
        self.assertIn("bi", profile["structural"])
        self.assertNotIn("sp", profile["structural"])
        # …and the business objects are NOT classified as structure.
        for obj in ("campgne", "facture", "contact", "devis", "avoir"):
            self.assertNotIn(obj, profile["structural"], obj)
        # Both markers are stripped from the object all the same.
        self.assertEqual(
            parse_routine_name("STP_BI_Facture_Insert", profile)["object"], "Facture")

    def test_dominant_business_object_is_never_classified_structural(self):
        """The regression that motivated the head-noun rule.

        `Client` appears in 100% of these names — frequency alone would flag it
        as structure and rename every module to its qualifier.
        """
        names = [
            "Zq_Client_Select", "Zq_Client_Insert", "Zq_Client_Update",
            "Zq_Client_Delete", "Zq_ClientAdresse_Select",
            "Zq_ClientContact_Insert", "Zq_Client_Liste", "Zq_Client_Compter",
            "Zq_ClientFacture_Select", "Zq_Client_Valider",
        ]
        profile = learn_name_profile(names)
        self.assertTrue(profile["usable"])
        self.assertNotIn("client", profile["structural"])
        # The marker that IS structure is found, in the very same corpus.
        self.assertIn("zq", profile["structural"])
        self.assertEqual(
            parse_routine_name("Zq_Client_Select", profile)["object"], "Client")

    def test_discovers_an_action_word_absent_from_the_verb_dictionary(self):
        """A frequent segment ALWAYS in last position is this database's verb."""
        names = [
            "SP_Client_Zzqry", "SP_Facture_Zzqry", "SP_Contact_Zzqry",
            "SP_Devis_Zzqry", "SP_Avoir_Zzqry", "SP_Commande_Zzqry",
            "SP_Reglement_Zzqry", "SP_Livraison_Zzqry",
        ]
        profile = learn_name_profile(names)
        self.assertIn("zzqry", profile["actions"])
        self.assertNotIn("zzqry", profile["structural"])

    def test_profile_is_deterministic(self):
        names = [f"SP_BI_Obj{i}_Select" for i in range(12)]
        first = learn_name_profile(names)
        second = learn_name_profile(names)
        self.assertEqual(first["structural"], second["structural"])
        self.assertEqual(first["actions"], second["actions"])
        self.assertEqual(first["stats"], second["stats"])

    def test_camelcase_business_term_survives_profiling(self):
        """Segments are split on delimiters only — never on a CamelCase hump.

        `ShopperAds` is one concept; splitting it let `Shopper` look frequent and
        structural, which silently renamed the module to `Ads`.
        """
        names = [
            "SP_API_ShopperAds_Liste", "SP_API_ShopperAds_Insert",
            "SP_API_ShopperAds_Update", "SP_API_ShopperClicks_Liste",
            "SP_API_ShopperClicks_Insert", "SP_API_Facture_Liste",
            "SP_API_Facture_Insert", "SP_API_Contact_Liste",
        ]
        profile = learn_name_profile(names)
        self.assertNotIn("shopperads", profile["structural"])
        self.assertNotIn("shopper", profile["structural"])
        self.assertEqual(
            parse_routine_name("SP_API_ShopperAds_Insert", profile)["object"],
            "ShopperAds",
        )

    def test_profile_changes_how_a_name_is_parsed(self):
        """The point of profiling: the same name parses differently with one."""
        names = [
            "STP_Zx_Client_Select", "STP_Zx_Facture_Select",
            "STP_Zx_Contact_Select", "STP_Zx_Devis_Select",
            "STP_Zx_Avoir_Select", "STP_Zx_Commande_Select",
            "STP_Zx_Reglement_Select", "STP_Zx_Livraison_Select",
        ]
        profile = learn_name_profile(names)
        self.assertIn("zx", profile["structural"])
        without = parse_routine_name("STP_Zx_Client_Select")["object"]
        with_profile = parse_routine_name("STP_Zx_Client_Select", profile)["object"]
        self.assertEqual(with_profile, "Client")
        self.assertNotEqual(without, with_profile)

    def test_stats_expose_the_threshold_actually_applied(self):
        names = [f"Zq_Obj{i}_Select" for i in range(20)]
        stats = learn_name_profile(names)["stats"]
        self.assertEqual(stats["names"], 20)
        self.assertEqual(
            stats["dfThreshold"],
            max(pmc._PROFILE_MIN_DF, round(pmc._PROFILE_DF_RATIO * 20)),
        )
        self.assertIn("zq", stats["structural"])


# --------------------------------------------------------------------------- #
# sub-object folding
# --------------------------------------------------------------------------- #

class TestSubObjectFolding(unittest.TestCase):

    def test_sub_object_folds_into_its_aggregate_root(self):
        routines = _routines(
            "usp_Client_Insert", "usp_Client_Get", "usp_Client_Update",
            "usp_ClientAdresse_Insert", "usp_ClientAdresse_Get",
        )
        modules, report = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(set(modules), {"Client"})
        self.assertEqual(len(modules["Client"]), 5)
        self.assertEqual(report["subObjectMerges"], {"ClientAdresse": "Client"})

    def test_folded_routine_keeps_its_own_object_for_the_us_slug(self):
        """CLAUDE.md §1: two US of one FEAT never share a {Name}."""
        routines = _routines("usp_Client_Get", "usp_ClientAdresse_Get")
        cluster(routines, use_cohesion=False)
        by_name = {r["name"]: r for r in routines}
        self.assertEqual(by_name["usp_Client_Get"]["module"], "Client")
        self.assertEqual(by_name["usp_ClientAdresse_Get"]["module"], "Client")
        self.assertEqual(by_name["usp_Client_Get"]["object"], "Client")
        self.assertEqual(by_name["usp_ClientAdresse_Get"]["object"], "ClientAdresse")

    def test_no_fold_without_the_parent_module(self):
        """A lone sub-object keeps its module — never invent an empty parent."""
        routines = _routines("usp_ClientAdresse_Insert", "usp_ClientAdresse_Get")
        modules, report = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(set(modules), {"ClientAdresse"})
        self.assertEqual(report["subObjectMerges"], {})

    def test_fold_respects_token_boundaries(self):
        """`Clientele` is not a `Client` sub-object — string prefix != token prefix."""
        routines = _routines(
            "usp_Client_Get", "usp_Client_Insert", "usp_Clientele_Get",
        )
        modules, _ = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(set(modules), {"Client", "Clientele"})

    def test_fold_is_prefix_only(self):
        """`AdresseClient` has `Adresse` as head noun — folding it would guess."""
        routines = _routines(
            "usp_Client_Get", "usp_Client_Insert", "usp_AdresseClient_Get",
        )
        modules, _ = cluster_with_report(routines, use_cohesion=False)
        self.assertIn("AdresseClient", modules)
        self.assertEqual(len(modules["Client"]), 2)

    def test_fold_is_transitive_to_the_deepest_root(self):
        routines = _routines(
            "usp_Commande_Get", "usp_Commande_Insert",
            "usp_CommandeLot_Get", "usp_CommandeLot_Insert",
            "usp_CommandeLotBordereau_Get",
        )
        modules, report = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(set(modules), {"Commande"})
        self.assertEqual(len(modules["Commande"]), 5)
        self.assertEqual(set(report["subObjectMerges"].values()), {"Commande"})

    def test_misc_never_absorbs_and_is_never_absorbed(self):
        routines = _routines("usp_Process", "usp_MiscThing_Get", "usp_Run")
        modules, report = cluster_with_report(routines, use_cohesion=False)
        self.assertIn("Misc", modules)
        self.assertIn("MiscThing", modules)
        self.assertEqual(report["subObjectMerges"], {})

    def test_module_name_keeps_its_camelcase_humps(self):
        """The FEAT name is read on disk — `Clientadresse` is a fidelity loss."""
        routines = _routines("usp_ClientAdresse_Get", "usp_ClientAdresse_Insert")
        modules, _ = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(set(modules), {"ClientAdresse"})

    def test_acronym_survives_the_module_name(self):
        routines = _routines("usp_CampgnePV_Select", "usp_CampgnePV_Insert")
        modules, _ = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(set(modules), {"CampgnePV"})


# --------------------------------------------------------------------------- #
# AUTO strategy switch
# --------------------------------------------------------------------------- #

class TestAutoStrategySwitch(unittest.TestCase):

    def test_clean_convention_keeps_the_naming_strategy(self):
        routines = _routines(
            "usp_Client_Insert", "usp_Client_Get", "usp_Client_Update",
            "usp_Facture_Insert", "usp_Facture_Get", "usp_Facture_Valider",
            "usp_Contact_Insert", "usp_Contact_Get", "usp_Contact_Delete",
        )
        modules, report = cluster_with_report(routines)
        self.assertEqual(report["strategy"], "naming")
        self.assertNotIn("degraded", report)
        self.assertEqual(set(modules), {"Client", "Facture", "Contact"})

    def test_small_corpus_never_switches(self):
        """Below the profiling floor, fragmentation describes the sample only."""
        routines = _routines("usp_Alpha_Get", "usp_Beta_Get", "usp_Gamma_Get")
        _, report = cluster_with_report(routines)
        self.assertEqual(report["strategy"], "naming")
        self.assertNotIn("degraded", report)
        self.assertLess(len(routines), pmc._AUTO_MIN_ROUTINES)

    def test_unusable_names_fall_back_to_dependency_cohesion(self):
        """One distinct object per routine, but they all share two tables."""
        shared_a = {"tablesRead": ["dbo.Facture"], "tablesWritten": ["dbo.Facture"]}
        shared_b = {"tablesRead": ["dbo.Client"], "tablesWritten": ["dbo.Client"]}
        names_a = ["usp_Zeta_Run", "usp_Kappa_Run", "usp_Omega_Run", "usp_Sigma_Run"]
        names_b = ["usp_Delta_Run", "usp_Theta_Run", "usp_Lambda_Run", "usp_Iota_Run"]
        signals = {n: shared_a for n in names_a}
        signals.update({n: shared_b for n in names_b})
        routines = _routines(*(names_a + names_b), **signals)
        modules, report = cluster_with_report(routines)
        self.assertEqual(report["strategy"], "cohesion")
        self.assertIn("naming unusable", report["reason"])
        self.assertLess(len(modules), report["modulesByNaming"])
        self.assertGreaterEqual(report["fragmentation"], pmc._AUTO_FRAGMENTATION)

    def test_unusable_names_and_useless_graph_stay_on_naming_but_flagged(self):
        """No shared table, no call: cohesion cannot group either — say so."""
        routines = _routines(*[f"usp_Obj{i}_Run" for i in range(10)])
        modules, report = cluster_with_report(routines)
        self.assertEqual(report["strategy"], "naming")
        self.assertTrue(report["degraded"])
        self.assertEqual(len(modules), 10)

    def test_rejected_cohesion_leaves_naming_annotations_on_the_routines(self):
        """The routines must agree with the modules that are actually returned."""
        routines = _routines(*[f"usp_Obj{i}_Run" for i in range(10)])
        modules, report = cluster_with_report(routines)
        self.assertTrue(report["degraded"])
        for r in routines:
            self.assertIn(r["module"], modules)
            self.assertIn(r["name"], [x["name"] for x in modules[r["module"]]])

    def test_fragmentation_is_measured_after_folding(self):
        """Folding is part of what naming achieves, so it counts toward the switch.

        Five aggregates × (root + sub-object), each a distinct name: 10 modules
        before folding, 5 after — which is exactly AT the 0.50 threshold, so the
        fold alone is not a free pass; the corpus must genuinely group.
        """
        pairs = ["Client", "Facture", "Contact", "Devis", "Avoir"]
        routines = _routines(
            *[f"usp_{p}_Get" for p in pairs],
            *[f"usp_{p}Bordereau_Get" for p in pairs],
        )
        modules, report = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(len(modules), 5)
        self.assertEqual(len(report["subObjectMerges"]), 5)
        self.assertEqual(report["fragmentation"], 0.5)

    def test_forced_cohesion_skips_the_measurement(self):
        routines = _routines("usp_Client_Get", "usp_Client_Insert")
        _, report = cluster_with_report(routines, use_cohesion=True)
        self.assertEqual(report["strategy"], "cohesion")
        self.assertEqual(report["reason"], "forced")

    def test_forced_naming_never_falls_back(self):
        routines = _routines(*[f"usp_Obj{i}_Run" for i in range(10)])
        _, report = cluster_with_report(routines, use_cohesion=False)
        self.assertEqual(report["strategy"], "naming")
        self.assertEqual(report["reason"], "forced")

    def test_report_carries_the_learned_profile_on_both_paths(self):
        names = [f"SP_Obj{i}_Select" for i in range(10)]
        for forced in (True, False, None):
            _, report = cluster_with_report(_routines(*names), use_cohesion=forced)
            self.assertIn("profile", report, f"use_cohesion={forced}")

    def test_every_routine_lands_in_exactly_one_module(self):
        """Traceability over tidiness: nothing is ever dropped."""
        routines = _routines(
            "usp_Client_Get", "usp_ClientAdresse_Get", "usp_Process",
            "usp_Facture_Valider", "usp_Zzz",
        )
        modules, _ = cluster_with_report(routines)
        placed = [r["name"] for members in modules.values() for r in members]
        self.assertCountEqual(placed, [r["name"] for r in routines])


# --------------------------------------------------------------------------- #
# the strategy is VISIBLE (rules/output-protocol.md §6)
# --------------------------------------------------------------------------- #

class TestClusteringIsReportedToTheTechLead(unittest.TestCase):
    """The découpage decision must reach the chat, not just the inventory JSON."""

    def _summary(self, report):
        from sdd_reverse_scripts.reverse_proc_introspect import _clustering_summary
        return _clustering_summary(report)

    def test_naming_strategy_is_named(self):
        line = self._summary({"strategy": "naming", "fragmentation": 0.2,
                              "subObjectMerges": {}})
        self.assertIn("nommage", line)
        self.assertNotIn("cohésion", line)

    def test_cohesion_strategy_says_why_and_shows_the_measure(self):
        line = self._summary({"strategy": "cohesion", "fragmentation": 0.82,
                              "reason": "naming unusable"})
        self.assertIn("cohésion", line)
        self.assertIn("inexploitable", line)
        self.assertIn("0.82", line)

    def test_degraded_naming_is_flagged(self):
        line = self._summary({"strategy": "naming", "fragmentation": 0.9,
                              "degraded": True, "subObjectMerges": {}})
        self.assertIn("dégradé", line)

    def test_sub_object_folds_are_counted_in_the_line(self):
        line = self._summary({"strategy": "naming", "fragmentation": 0.3,
                              "subObjectMerges": {"ClientAdresse": "Client",
                                                  "ClientContact": "Client"}})
        self.assertIn("2 sous-objet(s)", line)

    def test_summary_is_one_line_and_survives_an_empty_report(self):
        for report in ({}, None, {"strategy": "cohesion"}):
            line = self._summary(report)
            self.assertEqual(line.splitlines()[:1], [line])
            self.assertTrue(line.strip())

    def test_end_to_end_the_report_reaches_the_inventory(self):
        """`_clusteringReport` is what the chat line and the audit trail read."""
        from sdd_reverse_scripts.reverse_proc_introspect import build_inventory
        introspection = {
            "languageId": "tsql",
            "databaseType": "SqlServer",
            "procedures": [
                {"id": f"P{i}", "fqName": f"dbo.usp_{obj}_Get", "schema": "dbo",
                 "routineType": "SQL_STORED_PROCEDURE", "confidenceEstimate": "high",
                 "tablesRead": [], "tablesWritten": [], "callsProcs": [],
                 "evidence": "", "snapshotFile": ""}
                for i, obj in enumerate(
                    ["Client", "ClientAdresse", "Facture", "Contact"])
            ],
            "summary": {"proceduresCount": 4, "encryptedCount": 0},
        }
        inv = build_inventory(introspection, project="Db",
                              feats_dir=Path(_PY_ROOT) / "__no_such_dir__")
        report = inv["_clusteringReport"]
        self.assertEqual(report["strategy"], "naming")
        self.assertEqual(report["subObjectMerges"], {"ClientAdresse": "Client"})
        self.assertIn("nommage", self._summary(report))
        # The fold merged two objects into one FEAT…
        names = {u["suggestedName"] for u in inv["units"]}
        self.assertEqual(names, {"Client", "Facture", "Contact"})
        # …and the two US of that FEAT still have distinct {Name} (CLAUDE.md §1).
        client = next(u for u in inv["units"] if u["suggestedName"] == "Client")
        slugs = [p["usName"] for p in client["procedures"]]
        self.assertEqual(len(set(slugs)), 2, slugs)
        self.assertIn("Consulter-ClientAdresse", slugs)


if __name__ == "__main__":
    unittest.main()
