"""P0.3 (audit reverse-db 2026-07-24) — correlate DB objects ↔ consuming apps.

Joins db-introspection.json × data-access.json deterministically:
  * which files call which DB proc / touch which table,
  * orphan DB procedures (never called),
  * app calls to procedures absent from the DB (drift).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.sql_app_correlation import correlate, to_mermaid  # noqa: E402
from sdd_reverse_scripts.correlate_db_app import main as corr_main  # noqa: E402

_INTRO = {
    "database": "AppDb", "databaseType": "sqlserver",
    "procedures": [
        {"fqName": "dbo.usp_Order_Create", "routineType": "SQL_STORED_PROCEDURE",
         "tablesRead": [], "tablesWritten": ["dbo.Orders"]},
        {"fqName": "dbo.usp_Order_List", "routineType": "SQL_STORED_PROCEDURE",
         "tablesRead": ["dbo.Orders"], "tablesWritten": []},
        {"fqName": "dbo.usp_NeverCalled", "routineType": "SQL_STORED_PROCEDURE",
         "tablesRead": [], "tablesWritten": []},
    ],
}
_DATA_ACCESS = {
    "project": "WebApp",
    "queries": [
        {"verb": "SELECT", "tables": ["dbo.Orders"], "file": "Web/Orders.cs", "line": 10},
        {"verb": "SELECT", "tables": ["dbo.Customers"], "file": "Web/Cust.cs", "line": 5},
    ],
    "storedProcedureCalls": [
        {"name": "usp_Order_Create", "file": "Web/Orders.cs", "line": 20, "via": "EXEC"},
        {"name": "usp_Order_Create", "file": "Api/OrderSvc.cs", "line": 30, "via": "EXEC"},
        {"name": "usp_Ghost", "file": "Web/Legacy.cs", "line": 99, "via": "EXEC"},
    ],
}


class TestCorrelate(unittest.TestCase):
    def setUp(self):
        self.c = correlate(_INTRO, _DATA_ACCESS)

    def test_object_consumers(self):
        oc = self.c["objectConsumers"]
        self.assertIn("dbo.usp_Order_Create", oc)
        self.assertEqual(oc["dbo.usp_Order_Create"]["callCount"], 2)
        self.assertEqual(
            oc["dbo.usp_Order_Create"]["calledByFiles"],
            ["Api/OrderSvc.cs", "Web/Orders.cs"],  # sorted
        )

    def test_table_consumers(self):
        tc = self.c["tableConsumers"]
        self.assertIn("dbo.Orders", tc)
        self.assertEqual(tc["dbo.Orders"]["accessedByFiles"], ["Web/Orders.cs"])

    def test_orphan_procedures(self):
        # usp_NeverCalled + usp_Order_List (not in any call) are orphan.
        self.assertIn("dbo.usp_NeverCalled", self.c["orphanDbProcedures"])
        self.assertIn("dbo.usp_Order_List", self.c["orphanDbProcedures"])
        self.assertNotIn("dbo.usp_Order_Create", self.c["orphanDbProcedures"])

    def test_missing_procedures_drift(self):
        self.assertIn("usp_Ghost", self.c["missingProcedures"])
        self.assertEqual(self.c["missingProcedures"]["usp_Ghost"], ["Web/Legacy.cs"])

    def test_summary(self):
        s = self.c["summary"]
        self.assertEqual(s["dbObjects"], 3)
        self.assertEqual(s["consumedObjects"], 1)
        self.assertEqual(s["missingProcedures"], 1)

    def test_mermaid(self):
        m = to_mermaid(self.c)
        self.assertTrue(m.startswith("graph LR"))
        self.assertIn("calls", m)


class TestCli(unittest.TestCase):
    def test_cli_writes_outputs(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            ip = root / "db-introspection.json"
            dp = root / "data-access.json"
            ip.write_text(json.dumps(_INTRO), encoding="utf-8")
            dp.write_text(json.dumps(_DATA_ACCESS), encoding="utf-8")
            rc = corr_main(["--introspection", str(ip), "--data-access", str(dp), "--json"])
            self.assertEqual(rc, 0)
            self.assertTrue((root / "db-app-correlation.json").exists())
            md = (root / "db-app-correlation.md").read_text(encoding="utf-8")
            self.assertIn("usp_Order_Create", md)
            self.assertIn("```mermaid", md)

    def test_cli_missing_input(self):
        with TemporaryDirectory() as td:
            rc = corr_main(["--introspection", str(Path(td) / "nope.json"),
                            "--data-access", str(Path(td) / "also.json")])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
