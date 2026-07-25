"""P0.1 (audit reverse-db 2026-07-24): the live introspection covers views and
triggers, not just procedures/functions. They ride the SAME escalier (body
analysed → 1 SQL object = 1 US).

These tests are offline: they exercise the PURE analysis layer
(`build_introspection`) with synthetic catalog rows, plus assert the SQL Server
dialect query now enumerates V/TR and stays strictly read-only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.db_introspect import build_introspection  # noqa: E402
from sdd_reverse.dialects.base import ROUTINE_COLUMNS  # noqa: E402
from sdd_reverse.dialects import get_dialect  # noqa: E402
from sdd_reverse.readonly_guard import is_readonly  # noqa: E402

_SS = get_dialect("sqlserver")


def _row(schema, name, rtype, definition, modified=None, is_enc=0):
    d = {"schema": schema, "name": name, "routine_type": rtype,
         "definition": definition, "modified": modified, "is_encrypted": is_enc}
    return tuple(d[c] for c in ROUTINE_COLUMNS)


class TestDialectQueryCoversViewsTriggers(unittest.TestCase):
    def test_list_query_includes_view_and_trigger_types(self):
        self.assertIn("'V'", _SS.list_routines_sql)
        self.assertIn("'TR'", _SS.list_routines_sql)

    def test_queries_remain_read_only(self):
        # The Dialect constructor already asserts this, but pin it explicitly.
        self.assertTrue(is_readonly(_SS.list_routines_sql))
        self.assertTrue(is_readonly(_SS.single_routine_sql))


class TestViewTriggerFlowThroughIntrospection(unittest.TestCase):
    def _build(self, rows):
        return build_introspection(rows, _SS, server="host", database="Db", lang_cap="high")

    def test_view_is_analysed_as_read_projection(self):
        view_body = (
            "CREATE VIEW dbo.vActiveClients AS\n"
            "SELECT c.Id, c.Name FROM dbo.Clients c "
            "JOIN dbo.Orders o ON o.ClientId = c.Id WHERE c.Active = 1"
        )
        intro = self._build([_row("dbo", "vActiveClients", "VIEW", view_body)])
        obj = intro["procedures"][0]
        self.assertEqual(obj["routineType"], "VIEW")
        self.assertFalse(obj["encrypted"])
        # A view reads tables and writes none.
        self.assertTrue(obj["tablesRead"])
        self.assertEqual(obj["tablesWritten"], [])

    def test_trigger_flows_through_with_type(self):
        trg_body = (
            "CREATE TRIGGER dbo.trgAuditOrder ON dbo.Orders AFTER INSERT AS\n"
            "BEGIN INSERT INTO dbo.OrderAudit(OrderId) SELECT Id FROM inserted END"
        )
        intro = self._build([_row("dbo", "trgAuditOrder", "SQL_TRIGGER", trg_body)])
        obj = intro["procedures"][0]
        self.assertEqual(obj["routineType"], "SQL_TRIGGER")
        self.assertTrue(obj["tablesWritten"])  # trigger writes the audit table

    def test_encrypted_view_null_definition_flagged_not_guessed(self):
        intro = self._build([_row("dbo", "vSecret", "VIEW", None, is_enc=0)])
        obj = intro["procedures"][0]
        self.assertTrue(obj["encrypted"])          # NULL definition ⇒ encrypted
        self.assertEqual(obj["confidenceEstimate"], "low")

    def test_mixed_batch_all_kinds(self):
        rows = [
            _row("dbo", "usp_Do", "SQL_STORED_PROCEDURE", "CREATE PROC dbo.usp_Do AS SELECT 1"),
            _row("dbo", "fnCalc", "SQL_SCALAR_FUNCTION", "CREATE FUNCTION dbo.fnCalc() RETURNS int AS BEGIN RETURN 1 END"),
            _row("dbo", "vList", "VIEW", "CREATE VIEW dbo.vList AS SELECT * FROM dbo.T"),
            _row("dbo", "trgX", "SQL_TRIGGER", "CREATE TRIGGER dbo.trgX ON dbo.T AFTER UPDATE AS BEGIN SELECT 1 END"),
        ]
        intro = self._build(rows)
        types = {o["routineType"] for o in intro["procedures"]}
        self.assertEqual(types, {"SQL_STORED_PROCEDURE", "SQL_SCALAR_FUNCTION", "VIEW", "SQL_TRIGGER"})
        self.assertEqual(intro["summary"]["proceduresCount"], 4)


if __name__ == "__main__":
    unittest.main()
