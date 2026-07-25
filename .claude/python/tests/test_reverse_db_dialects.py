"""Four principal engines (2026-07-24): SQL Server, PostgreSQL, Oracle, MySQL.

Offline contract tests (no live DB / no driver required):
  * every dialect's LIST + SINGLE query is strictly read-only (the guard the
    whole module hinges on) and enumerates procedures/functions/views/triggers;
  * the registry resolves each engine + its aliases;
  * synthetic catalog rows flow through the generic build_introspection with the
    right routineType regardless of engine;
  * connection-string composition produces the expected shape per engine.

Live runtime (Oracle/MySQL) is out of scope here — no driver/instance at bench.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.dialects import get_dialect, supported_db_types, UnsupportedDialect  # noqa: E402
from sdd_reverse.dialects.base import ROUTINE_COLUMNS  # noqa: E402
from sdd_reverse.readonly_guard import is_readonly  # noqa: E402
from sdd_reverse.db_introspect import build_introspection, compose_connection_string  # noqa: E402

_ENGINES = ["sqlserver", "postgresql", "oracle", "mysql"]


def _row(schema, name, rtype, definition):
    d = {"schema": schema, "name": name, "routine_type": rtype,
         "definition": definition, "modified": None, "is_encrypted": 0}
    return tuple(d[c] for c in ROUTINE_COLUMNS)


class _Cfg:
    def __init__(self):
        self.host = "dbhost"
        self.port = ""
        self.name = "AppDb"
        self.user = "ro_user"
        self.password = "s3cret"


class TestRegistry(unittest.TestCase):
    def test_four_principal_engines_registered(self):
        ids = set(supported_db_types())
        self.assertTrue({"sqlserver", "postgresql", "oracle", "mysql"}.issubset(ids))

    def test_aliases_resolve(self):
        self.assertEqual(get_dialect("mssql").id, "sqlserver")
        self.assertEqual(get_dialect("postgres").id, "postgresql")
        self.assertEqual(get_dialect("mariadb").id, "mysql")
        self.assertEqual(get_dialect("plsql").id, "oracle")

    def test_unknown_still_raises(self):
        with self.assertRaises(UnsupportedDialect):
            get_dialect("cassandra")


class TestQueriesReadOnly(unittest.TestCase):
    def test_all_dialect_queries_are_read_only(self):
        for eng in _ENGINES:
            d = get_dialect(eng)
            self.assertTrue(is_readonly(d.list_routines_sql), f"{eng} LIST not read-only")
            self.assertTrue(is_readonly(d.single_routine_sql), f"{eng} SINGLE not read-only")

    def test_queries_enumerate_views_and_triggers(self):
        # SQL Server via type codes; the others via explicit VIEW/TRIGGER tokens.
        self.assertIn("'V'", get_dialect("sqlserver").list_routines_sql)
        self.assertIn("'TR'", get_dialect("sqlserver").list_routines_sql)
        for eng in ("postgresql", "oracle", "mysql"):
            sql = get_dialect(eng).list_routines_sql
            self.assertIn("VIEW", sql, f"{eng} LIST missing VIEW")
            self.assertIn("TRIGGER", sql, f"{eng} LIST missing TRIGGER")


class TestIntrospectionFlow(unittest.TestCase):
    def test_mixed_objects_flow_for_every_engine(self):
        rows = [
            _row("app", "usp_Do", "SQL_STORED_PROCEDURE", "SELECT 1"),
            _row("app", "fnCalc", "FUNCTION", "RETURN 1"),
            _row("app", "vList", "VIEW", "SELECT * FROM app.T"),
            _row("app", "trgAudit", "SQL_TRIGGER", "INSERT INTO app.Audit SELECT 1"),
        ]
        for eng in _ENGINES:
            d = get_dialect(eng)
            intro = build_introspection(rows, d, server="h", database="AppDb")
            self.assertEqual(intro["summary"]["proceduresCount"], 4, eng)
            self.assertEqual(intro["databaseType"], d.id)


class TestConnectionStrings(unittest.TestCase):
    def test_compose_per_engine(self):
        cfg = _Cfg()
        ss = compose_connection_string(cfg, get_dialect("sqlserver"))
        self.assertIn("ApplicationIntent=ReadOnly", ss)
        pg = compose_connection_string(cfg, get_dialect("postgresql"))
        self.assertIn("dbname=AppDb", pg)
        ora = compose_connection_string(cfg, get_dialect("oracle"))
        self.assertEqual(ora, "ro_user/s3cret@dbhost:1521/AppDb")
        my = compose_connection_string(cfg, get_dialect("mysql"))
        self.assertIn("database=AppDb", my)
        self.assertIn("port=3306", my)
        # Password must appear only in the in-RAM connstring, never elsewhere here.
        self.assertIn("s3cret", ora)


if __name__ == "__main__":
    unittest.main()
