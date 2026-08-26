"""P0.2 catalog augmentation (audit reverse-db 2026-07-24) — authoritative
object↔object dependency edges from the DB catalog, merged into the body-derived
graph. Offline: dialect query read-only shape + merge logic with synthetic rows.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.dialects import get_dialect  # noqa: E402
from sdd_reverse.dialects.base import DEPENDENCY_COLUMNS  # noqa: E402
from sdd_reverse.readonly_guard import is_readonly  # noqa: E402
from sdd_reverse.sql_dependency_graph import (  # noqa: E402
    build_dependency_graph, merge_catalog_dependencies,
)


def _dep(fs, fn, ts, tn, dt):
    d = {"from_schema": fs, "from_name": fn, "to_schema": ts, "to_name": tn, "dep_type": dt}
    return tuple(d[c] for c in DEPENDENCY_COLUMNS)


class TestDependencyQueryReadOnly(unittest.TestCase):
    def test_every_engine_has_a_readonly_dep_query(self):
        """Audit 2026-08-25: PostgreSQL and MySQL were the two engines left with
        a purely regex-derived object graph. They now read their own catalog —
        `pg_depend`+`pg_rewrite` for PostgreSQL, `VIEW_TABLE_USAGE` for MySQL."""
        for eng in ("sqlserver", "oracle", "postgresql", "mysql"):
            q = get_dialect(eng).dependency_query
            self.assertTrue(q, f"{eng} should declare a dependency_query")
            self.assertTrue(is_readonly(q), f"{eng} dependency_query not read-only")

    def test_dep_queries_return_the_declared_column_contract(self):
        """Each dep query must project the DEPENDENCY_COLUMNS aliases, in order."""
        for eng in ("sqlserver", "oracle", "postgresql", "mysql"):
            q = get_dialect(eng).dependency_query
            for col in DEPENDENCY_COLUMNS:
                self.assertIn(col, q, f"{eng} dependency_query lacks {col!r}")

    def test_mysql_dep_query_is_documented_as_version_dependent(self):
        """VIEW_TABLE_USAGE is MySQL 8.0.13+ only; absence must degrade, not fail.
        The runtime tolerance lives in db_introspect.introspect (try/except)."""
        import inspect

        from sdd_reverse import db_introspect
        src = inspect.getsource(db_introspect.introspect)
        self.assertIn("dep_rows = []", src)  # best-effort fallback preserved


class TestMerge(unittest.TestCase):
    def _base_graph(self):
        objs = [
            {"fqName": "dbo.usp_A", "routineType": "SQL_STORED_PROCEDURE",
             "tablesRead": ["dbo.T1"], "tablesWritten": [], "callsProcs": []},
        ]
        return build_dependency_graph(objs)

    def test_body_edges_carry_source_body(self):
        g = self._base_graph()
        self.assertTrue(all(e.get("source") == "body" for e in g["edges"]))

    def test_catalog_edge_added_with_provenance(self):
        g = self._base_graph()
        rows = [_dep("dbo", "usp_A", "dbo", "T2", "USER_TABLE")]  # new dep not seen by body
        merge_catalog_dependencies(g, rows, DEPENDENCY_COLUMNS)
        cat = [e for e in g["edges"] if e["source"] == "catalog"]
        self.assertEqual(len(cat), 1)
        self.assertEqual((cat[0]["from"], cat[0]["to"], cat[0]["rel"]), ("dbo.usp_A", "dbo.T2", "depends"))
        # T2 node created as a table (dep_type contained TABLE)
        t2 = next(n for n in g["nodes"] if n["id"] == "dbo.T2")
        self.assertEqual(t2["type"], "table")

    def test_no_duplicate_of_body_edge(self):
        g = self._base_graph()
        # Catalog reports the SAME dep the body already found (usp_A → T1).
        rows = [_dep("dbo", "usp_A", "dbo", "T1", "USER_TABLE")]
        before = len(g["edges"])
        merge_catalog_dependencies(g, rows, DEPENDENCY_COLUMNS)
        self.assertEqual(len(g["edges"]), before)  # deduped

    def test_idempotent(self):
        g = self._base_graph()
        rows = [_dep("dbo", "usp_A", "dbo", "T2", "USER_TABLE")]
        merge_catalog_dependencies(g, rows, DEPENDENCY_COLUMNS)
        n1 = len(g["edges"])
        merge_catalog_dependencies(g, rows, DEPENDENCY_COLUMNS)
        self.assertEqual(len(g["edges"]), n1)  # second merge = no-op

    def test_self_dependency_skipped(self):
        g = self._base_graph()
        rows = [_dep("dbo", "usp_A", "dbo", "usp_A", "PROCEDURE")]
        merge_catalog_dependencies(g, rows, DEPENDENCY_COLUMNS)
        self.assertFalse([e for e in g["edges"] if e["source"] == "catalog"])


if __name__ == "__main__":
    unittest.main()
