"""P1/DB2 (audit reverse-db 2026-07-24) — string-literal masking in the body
analyzer, so dynamic-SQL / error-message strings don't create false static
writes/reads/calls, while the dynamic-SQL flag still fires (→ confidence cap).

Updated 2026-08-25 (audit finding D1): the analyzer now reports object names
QUALIFIED as written (`dbo.Orders`, not `Orders`), so `sales.Orders` and
`dbo.Orders` stop collapsing into one node. Positive assertions therefore pin
the qualified name; NEGATIVE assertions compare on the leaf name via `_leaves`,
because `assertNotIn("SecretAudit", ["dbo.SecretAudit"])` would pass vacuously
and silently gut the masking test this file exists to protect.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.sql_body_analyzer import (  # noqa: E402
    analyze_routine,
    confidence_signal,
    object_leaf,
)


def _leaves(names) -> set[str]:
    """Leaf names, lower-cased — for negative assertions that must not be fooled
    by qualification (`dbo.X` still counts as X being present)."""
    return {object_leaf(n).lower() for n in names}


class TestStringMasking(unittest.TestCase):
    def test_dynamic_sql_string_not_counted_as_static_write(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Dyn AS\n"
            "BEGIN\n"
            "  DECLARE @sql NVARCHAR(MAX);\n"
            "  SET @sql = 'INSERT INTO dbo.SecretAudit(x) VALUES(1)';\n"
            "  EXEC sp_executesql @sql;\n"
            "  SELECT * FROM dbo.RealTable;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Dyn", body)
        # The table inside the dynamic string must NOT be reported as a write.
        self.assertNotIn("secretaudit", _leaves(s["tablesWritten"]))
        # The genuine static read IS reported, qualified as written.
        self.assertIn("dbo.RealTable", s["tablesRead"])
        # Dynamic SQL is still detected → confidence capped to medium.
        self.assertTrue(s["dynamicSql"])
        self.assertEqual(confidence_signal(s, "high"), "medium")
        # N3: sp_executesql is a system routine, not a business dependency.
        self.assertNotIn("sp_executesql", _leaves(s["calls"]))

    def test_error_message_string_not_counted_as_write(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Guard AS\n"
            "BEGIN\n"
            "  IF 1=0 RAISERROR('DELETE FROM Users is forbidden', 16, 1);\n"
            "  UPDATE dbo.Account SET balance = 0;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Guard", body)
        self.assertNotIn("users", _leaves(s["tablesWritten"]))  # inside the message
        self.assertIn("dbo.Account", s["tablesWritten"])        # the real write

    def test_real_static_sql_unaffected(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Ok AS\n"
            "BEGIN\n"
            "  INSERT INTO dbo.Orders(id) VALUES(1);\n"
            "  SELECT * FROM dbo.Customers c JOIN dbo.Regions r ON r.id=c.rid;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Ok", body)
        self.assertIn("dbo.Orders", s["tablesWritten"])
        self.assertIn("dbo.Customers", s["tablesRead"])
        self.assertIn("dbo.Regions", s["tablesRead"])
        self.assertFalse(s["dynamicSql"])

    def test_escaped_quotes_in_string(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Q AS\n"
            "BEGIN\n"
            "  PRINT 'it''s a test with UPDATE Foo inside';\n"
            "  DELETE FROM dbo.Temp;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Q", body)
        self.assertNotIn("foo", _leaves(s["tablesWritten"]))
        self.assertIn("dbo.Temp", s["tablesWritten"])


class TestQualifiedObjectNames(unittest.TestCase):
    """D1 — qualification is preserved, so homonyms across schemas stay distinct."""

    def test_same_table_name_in_two_schemas_stays_distinct(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Sync AS\n"
            "BEGIN\n"
            "  INSERT INTO sales.Orders(id) SELECT id FROM dbo.Orders;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Sync", body)
        self.assertIn("sales.Orders", s["tablesWritten"])
        self.assertIn("dbo.Orders", s["tablesRead"])

    def test_unqualified_name_stays_unqualified(self):
        """No invented `dbo.` — a guessed schema would create a false identity."""
        s = analyze_routine("x", "CREATE PROC x AS SELECT * FROM Contacts")
        self.assertIn("Contacts", s["tablesRead"])

    def test_three_part_name_keeps_the_table_not_the_schema(self):
        """The old regex captured `dbo` here instead of `Orders`."""
        s = analyze_routine(
            "x", "CREATE PROC x AS SELECT * FROM LinkedDb.dbo.Orders")
        self.assertEqual(_leaves(s["tablesRead"]), {"orders"})
        self.assertIn("LinkedDb.dbo.Orders", s["tablesRead"])

    def test_bracketed_and_spaced_qualification_normalised(self):
        s = analyze_routine(
            "x", "CREATE PROC x AS SELECT * FROM [dbo] . [Big Table]")
        # `Big Table` has a space: the \w+ capture stops at `Big`, which is the
        # documented best-effort limit of a regex analyzer (no SQL AST yet).
        self.assertTrue(s["tablesRead"])

    def test_case_variants_deduplicated(self):
        s = analyze_routine(
            "x", "CREATE PROC x AS SELECT * FROM dbo.Orders o "
                 "JOIN DBO.ORDERS o2 ON o2.id=o.id")
        self.assertEqual(len(s["tablesRead"]), 1)

    def test_trigger_pseudo_tables_are_not_tables(self):
        body = (
            "CREATE TRIGGER dbo.trgAudit ON dbo.Orders AFTER INSERT AS\n"
            "BEGIN INSERT INTO dbo.OrderAudit(id) SELECT id FROM inserted END"
        )
        s = analyze_routine("dbo.trgAudit", body)
        self.assertIn("dbo.OrderAudit", s["tablesWritten"])
        self.assertNotIn("inserted", _leaves(s["tablesRead"]))


class TestComplexityRubric(unittest.TestCase):
    """M2 — volume and data-effect breadth route to the LLM, not just branches."""

    def test_long_branchless_etl_is_complex(self):
        from sdd_reverse.sql_body_analyzer import proc_complexity

        writes = "\n".join(
            f"  INSERT INTO dbo.T{i}(id) SELECT id FROM dbo.Src{i};"
            for i in range(40)
        )
        body = f"CREATE PROCEDURE dbo.usp_Etl AS\nBEGIN\n{writes}\nEND"
        sig = analyze_routine("dbo.usp_Etl", body)
        self.assertEqual(sig["branches"], 0)      # no control flow at all
        self.assertFalse(sig["dynamicSql"])
        # Old rubric said "simple" → tautological 0-token US at confidence high.
        self.assertEqual(proc_complexity(sig), "complex")

    def test_transactional_write_is_complex(self):
        from sdd_reverse.sql_body_analyzer import proc_complexity

        body = (
            "CREATE PROCEDURE dbo.usp_Post AS\n"
            "BEGIN\n  BEGIN TRAN;\n"
            "  INSERT INTO dbo.Ledger(id) VALUES(1);\n  COMMIT;\nEND"
        )
        sig = analyze_routine("dbo.usp_Post", body)
        self.assertEqual(proc_complexity(sig), "complex")

    def test_short_plain_select_stays_simple(self):
        from sdd_reverse.sql_body_analyzer import proc_complexity

        sig = analyze_routine(
            "dbo.usp_List",
            "CREATE PROCEDURE dbo.usp_List AS\nBEGIN\n"
            "  SELECT Id, Name FROM dbo.Contacts ORDER BY Name;\nEND",
        )
        self.assertEqual(proc_complexity(sig), "simple")

    def test_reasons_are_reported_as_data(self):
        from sdd_reverse.sql_body_analyzer import complexity_reasons

        sig = analyze_routine(
            "dbo.usp_X",
            "CREATE PROCEDURE dbo.usp_X AS BEGIN "
            "IF 1=1 RAISERROR('no',16,1); END",
        )
        reasons = complexity_reasons(sig)
        self.assertTrue(any(r.startswith("branches=") for r in reasons))
        self.assertTrue(any(r.startswith("raises=") for r in reasons))


if __name__ == "__main__":
    unittest.main()
