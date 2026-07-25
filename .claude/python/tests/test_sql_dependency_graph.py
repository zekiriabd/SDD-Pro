"""P0.2 (audit reverse-db 2026-07-24) — object↔object dependency graph +
cohesion clustering + impact analysis, derived deterministically from the
introspection signals (cross-engine, offline).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.sql_dependency_graph import (  # noqa: E402
    build_dependency_graph, cohesion_modules, impact_of, to_mermaid,
)
from sdd_reverse.proc_module_clusterer import cluster  # noqa: E402


def _obj(fq, rtype="SQL_STORED_PROCEDURE", reads=None, writes=None, calls=None):
    return {"fqName": fq, "routineType": rtype,
            "tablesRead": reads or [], "tablesWritten": writes or [],
            "callsProcs": calls or []}


_OBJECTS = [
    _obj("dbo.usp_Order_Create", writes=["dbo.Orders"], reads=["dbo.Customers"], calls=["dbo.usp_Audit"]),
    _obj("dbo.usp_Order_List", reads=["dbo.Orders"]),
    _obj("dbo.vActiveOrders", rtype="VIEW", reads=["dbo.Orders"]),
    _obj("dbo.usp_Audit", writes=["dbo.AuditLog"]),
    _obj("dbo.usp_Invoice_Pay", writes=["dbo.Invoices"], reads=["dbo.Invoices"]),
]


class TestGraph(unittest.TestCase):
    def test_nodes_and_edges(self):
        g = build_dependency_graph(_OBJECTS)
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("dbo.Orders", ids)          # table node
        self.assertIn("dbo.usp_Order_Create", ids)  # object node
        rels = {(e["from"], e["rel"], e["to"]) for e in g["edges"]}
        self.assertIn(("dbo.usp_Order_Create", "writes", "dbo.Orders"), rels)
        self.assertIn(("dbo.usp_Order_List", "reads", "dbo.Orders"), rels)
        # call resolved to a known object (matched by trailing name)
        self.assertIn(("dbo.usp_Order_Create", "calls", "dbo.usp_Audit"), rels)

    def test_stats(self):
        g = build_dependency_graph(_OBJECTS)
        self.assertEqual(g["stats"]["objectCount"], 5)
        self.assertGreaterEqual(g["stats"]["tableCount"], 4)

    def test_external_callee_becomes_external_node(self):
        objs = [_obj("dbo.usp_X", calls=["dbo.usp_NotIntrospected"])]
        g = build_dependency_graph(objs)
        ext = [n for n in g["nodes"] if n["type"] == "external"]
        self.assertEqual(len(ext), 1)


class TestCohesion(unittest.TestCase):
    def test_order_objects_cluster_together(self):
        mods = cohesion_modules(_OBJECTS)
        # The three Orders-touching objects + the audit proc it calls share a component.
        order_mod = mods["dbo.usp_Order_Create"]
        self.assertEqual(mods["dbo.usp_Order_List"], order_mod)
        self.assertEqual(mods["dbo.vActiveOrders"], order_mod)
        self.assertEqual(mods["dbo.usp_Audit"], order_mod)  # linked via call edge
        # Invoice proc is isolated → its own module.
        self.assertNotEqual(mods["dbo.usp_Invoice_Pay"], order_mod)

    def test_module_named_after_dominant_table(self):
        mods = cohesion_modules(_OBJECTS)
        self.assertEqual(mods["dbo.usp_Invoice_Pay"], "Invoice")  # singularised


class TestImpact(unittest.TestCase):
    def test_impact_of_table(self):
        g = build_dependency_graph(_OBJECTS)
        imp = impact_of(g, "dbo.Orders")
        # 3 objects depend on Orders.
        self.assertEqual(
            set(imp["dependents"]),
            {"dbo.usp_Order_Create", "dbo.usp_Order_List", "dbo.vActiveOrders"},
        )


class TestMermaid(unittest.TestCase):
    def test_renders_without_error(self):
        g = build_dependency_graph(_OBJECTS)
        m = to_mermaid(g)
        self.assertTrue(m.startswith("graph LR"))
        self.assertIn("writes", m)


class TestClustererOptIn(unittest.TestCase):
    def test_naming_is_default_unchanged(self):
        routines = [{"name": "usp_Contact_Insert"}, {"name": "usp_Contact_List"}]
        mods = cluster(routines)  # default = naming
        self.assertIn("Contact", mods)

    def test_cohesion_opt_in(self):
        routines = [
            {"name": "sp_a", "signals": {"tablesWritten": ["Orders"], "tablesRead": [], "calls": []}},
            {"name": "sp_b", "signals": {"tablesRead": ["Orders"], "tablesWritten": [], "calls": []}},
            {"name": "sp_c", "signals": {"tablesWritten": ["Payments"], "tablesRead": [], "calls": []}},
        ]
        mods = cluster(routines, use_cohesion=True)
        # sp_a & sp_b share Orders → same module ; sp_c separate.
        module_of = {r["name"]: m for m, rs in mods.items() for r in rs}
        self.assertEqual(module_of["sp_a"], module_of["sp_b"])
        self.assertNotEqual(module_of["sp_a"], module_of["sp_c"])


if __name__ == "__main__":
    unittest.main()
