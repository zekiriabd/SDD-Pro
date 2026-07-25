"""P1/DB2 (audit reverse-db 2026-07-24) — string-literal masking in the body
analyzer, so dynamic-SQL / error-message strings don't create false static
writes/reads/calls, while the dynamic-SQL flag still fires (→ confidence cap).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.sql_body_analyzer import analyze_routine, confidence_signal  # noqa: E402


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
        self.assertNotIn("SecretAudit", s["tablesWritten"])
        # The genuine static read IS reported.
        self.assertIn("RealTable", s["tablesRead"])
        # Dynamic SQL is still detected → confidence capped to medium.
        self.assertTrue(s["dynamicSql"])
        self.assertEqual(confidence_signal(s, "high"), "medium")

    def test_error_message_string_not_counted_as_write(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Guard AS\n"
            "BEGIN\n"
            "  IF 1=0 RAISERROR('DELETE FROM Users is forbidden', 16, 1);\n"
            "  UPDATE dbo.Account SET balance = 0;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Guard", body)
        self.assertNotIn("Users", s["tablesWritten"])   # was inside the message
        self.assertIn("Account", s["tablesWritten"])     # the real write

    def test_real_static_sql_unaffected(self):
        body = (
            "CREATE PROCEDURE dbo.usp_Ok AS\n"
            "BEGIN\n"
            "  INSERT INTO dbo.Orders(id) VALUES(1);\n"
            "  SELECT * FROM dbo.Customers c JOIN dbo.Regions r ON r.id=c.rid;\n"
            "END"
        )
        s = analyze_routine("dbo.usp_Ok", body)
        self.assertIn("Orders", s["tablesWritten"])
        self.assertIn("Customers", s["tablesRead"])
        self.assertIn("Regions", s["tablesRead"])
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
        self.assertNotIn("Foo", s["tablesWritten"])
        self.assertIn("Temp", s["tablesWritten"])


if __name__ == "__main__":
    unittest.main()
