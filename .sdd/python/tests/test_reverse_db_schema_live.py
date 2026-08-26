"""C1 (audit 2026-08-25) — LIVE relational schema introspection.

Before this pass the DB-reverse read only body-bearing objects: tables, columns,
datatypes, keys, indexes and CHECK constraints were never read from a catalog,
and `db-schema.json` was only ever produced by parsing `.sql` files from a
legacy repository — which does not exist when the input is a connection string.

These tests are offline: they exercise the PURE builder with synthetic catalog
rows, and assert that every dialect declares read-only structure queries.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse import db_schema_live as dsl  # noqa: E402
from sdd_reverse.dialects import _REGISTRY, get_dialect  # noqa: E402
from sdd_reverse.dialects.base import SCHEMA_QUERY_CONTRACTS  # noqa: E402
from sdd_reverse.readonly_guard import is_readonly  # noqa: E402

_DIALECTS = {d.id: d for d in _REGISTRY.values()}


def _col(schema, table, name, ordinal, dtype, *, max_length=None, precision=None,
         scale=None, nullable=1, default=None, identity=0, computed=0,
         computed_def=None):
    return (schema, table, name, ordinal, dtype, max_length, precision, scale,
            nullable, default, identity, computed, computed_def)


class TestEveryDialectDeclaresStructureQueries(unittest.TestCase):
    """The gap was engine-wide — no dialect may ship without structure reads."""

    def test_all_four_engines_declare_the_five_structure_queries(self):
        for name, dialect in sorted(_DIALECTS.items()):
            declared = {k for k, _ in dialect.schema_queries}
            self.assertEqual(
                declared, set(SCHEMA_QUERY_CONTRACTS),
                f"{name} is missing structure queries: "
                f"{sorted(set(SCHEMA_QUERY_CONTRACTS) - declared)}",
            )

    def test_all_structure_and_object_queries_are_read_only(self):
        for name, dialect in sorted(_DIALECTS.items()):
            for label, sql in list(dialect.schema_queries) + list(dialect.catalog_object_queries):
                self.assertTrue(
                    is_readonly(sql),
                    f"{name}.{label} is not a pure read: {sql[:80]!r}",
                )

    def test_every_engine_reads_its_scheduler_jobs(self):
        """Jobs were the user's explicit ask and were absent from every engine."""
        for name in ("sqlserver", "oracle", "mysql", "postgresql"):
            kinds = {k for k, _ in _DIALECTS[name].catalog_object_queries}
            self.assertIn("job", kinds, f"{name} does not read scheduler jobs")

    def test_sqlserver_reads_jobs_from_msdb_and_their_steps(self):
        sql = dict(_DIALECTS["sqlserver"].catalog_object_queries)
        self.assertIn("msdb.dbo.sysjobs", sql["job"])
        self.assertIn("sysjobsteps", sql["job_step"])

    def test_postgres_and_mysql_gained_a_dependency_query(self):
        """They were the two engines whose object graph stayed regex-only."""
        self.assertTrue(_DIALECTS["postgresql"].dependency_query)
        self.assertTrue(_DIALECTS["mysql"].dependency_query)

    def test_unknown_schema_query_name_is_refused_at_construction(self):
        from sdd_reverse.dialects.base import Dialect
        with self.assertRaises(ValueError):
            Dialect(id="x", label="x", language_id="tsql", default_port=1,
                    driver_hint="", list_routines_sql="SELECT 1",
                    single_routine_sql="SELECT 1",
                    schema_queries=(("typo_columns", "SELECT 1"),))

    def test_non_read_only_structure_query_is_refused_at_construction(self):
        from sdd_reverse.dialects.base import Dialect
        with self.assertRaises(ValueError):
            Dialect(id="x", label="x", language_id="tsql", default_port=1,
                    driver_hint="", list_routines_sql="SELECT 1",
                    single_routine_sql="SELECT 1",
                    schema_queries=(("columns", "DROP TABLE Clients"),))


class TestBuildLiveSchema(unittest.TestCase):
    def _build(self, **over):
        rows = {
            "columns": over.pop("columns", [
                _col("dbo", "Clients", "Id", 1, "int", identity=1, nullable=0),
                _col("dbo", "Clients", "Name", 2, "nvarchar", max_length=100, nullable=0),
                _col("dbo", "Clients", "Balance", 3, "decimal", precision=12, scale=2),
                _col("dbo", "Orders", "Id", 1, "int", identity=1, nullable=0),
                _col("dbo", "Orders", "ClientId", 2, "int", nullable=0),
            ]),
            "primary_keys": over.pop("primary_keys", [
                ("dbo", "Clients", "PK_Clients", "Id", 1),
                ("dbo", "Orders", "PK_Orders", "Id", 1),
            ]),
            "foreign_keys": over.pop("foreign_keys", [
                ("FK_Orders_Clients", "dbo", "Orders", "ClientId", "dbo", "Clients", "Id"),
            ]),
            "indexes": over.pop("indexes", [
                ("dbo", "Orders", "IX_Orders_ClientId", "ClientId", 0, 0, 1),
                ("dbo", "Clients", "UQ_Clients_Name", "Name", 1, 0, 1),
            ]),
            "checks": over.pop("checks", [
                ("dbo", "Clients", "CK_Clients_Balance", "([Balance]>=(0))"),
            ]),
        }
        rows.update(over.pop("rows", {}))
        return dsl.build_live_schema(
            rows, over.pop("objects", []),
            project="OrdersDb", database="OrdersDb", db_type="sqlserver",
            **over,
        )

    def test_completeness_is_live_not_basic(self):
        """The whole point: downstream can tell a catalog read from a regex parse."""
        self.assertEqual(self._build()["completeness"], "live")

    def test_tables_and_columns_are_extracted(self):
        s = self._build()
        names = {e["qualifiedName"] for e in s["entities"]}
        self.assertEqual(names, {"dbo.Clients", "dbo.Orders"})
        clients = next(e for e in s["entities"] if e["name"] == "Clients")
        self.assertEqual([f["name"] for f in clients["fields"]],
                         ["Id", "Name", "Balance"])

    def test_datatypes_carry_length_and_precision(self):
        """Datatypes were entirely absent from the DB path — this is the fix."""
        clients = next(e for e in self._build()["entities"] if e["name"] == "Clients")
        types = {f["name"]: f["type"] for f in clients["fields"]}
        self.assertEqual(types["Id"], "int")
        # SQL Server reports nvarchar max_length in BYTES (100 → 50 chars).
        self.assertEqual(types["Name"], "nvarchar(50)")
        self.assertEqual(types["Balance"], "decimal(12,2)")

    def test_primary_key_identity_and_nullability(self):
        clients = next(e for e in self._build()["entities"] if e["name"] == "Clients")
        by_name = {f["name"]: f for f in clients["fields"]}
        self.assertTrue(by_name["Id"]["primaryKey"])
        self.assertTrue(by_name["Id"]["identity"])
        self.assertFalse(by_name["Id"]["nullable"])
        self.assertFalse(by_name["Name"]["primaryKey"])
        self.assertTrue(by_name["Balance"]["nullable"])

    def test_relations_are_qualified_both_sides(self):
        rel = self._build()["relations"][0]
        self.assertEqual(rel["name"], "FK_Orders_Clients")
        self.assertEqual(rel["from"], {"entity": "dbo.Orders", "field": "ClientId"})
        self.assertEqual(rel["to"], {"entity": "dbo.Clients", "field": "Id"})

    def test_composite_key_yields_one_relation_per_column_pair(self):
        s = self._build(foreign_keys=[
            ("FK_C", "dbo", "A", "K1", "dbo", "B", "K1"),
            ("FK_C", "dbo", "A", "K2", "dbo", "B", "K2"),
        ])
        self.assertEqual(len(s["relations"]), 2)

    def test_indexes_are_collapsed_per_index_with_ordered_columns(self):
        s = self._build(indexes=[
            ("dbo", "Orders", "IX_Multi", "A", 0, 0, 1),
            ("dbo", "Orders", "IX_Multi", "B", 0, 0, 2),
        ])
        self.assertEqual(len(s["indexes"]), 1)
        self.assertEqual(s["indexes"][0]["columns"], ["A", "B"])
        self.assertFalse(s["indexes"][0]["unique"])

    def test_check_constraints_are_captured_as_business_rules(self):
        s = self._build()
        self.assertEqual(len(s["checks"]), 1)
        self.assertIn("Balance", s["checks"][0]["definition"])
        self.assertEqual(s["checks"][0]["table"], "dbo.Clients")

    def test_computed_column_keeps_its_expression(self):
        s = self._build(columns=[
            _col("dbo", "T", "Total", 1, "decimal", precision=10, scale=2,
                 computed=1, computed_def="([Qty]*[Price])"),
        ])
        f = s["entities"][0]["fields"][0]
        self.assertTrue(f["computed"])
        self.assertEqual(f["computedDefinition"], "([Qty]*[Price])")

    def test_engine_flag_dialects_are_all_understood(self):
        """PG returns 'YES'/'NO', SQL Server 0/1, MySQL '1' — same meaning."""
        for raw, expected in (("YES", True), (1, True), ("1", True), (True, True),
                              ("NO", False), (0, False), (None, False)):
            s = dsl.build_live_schema(
                {"columns": [_col("s", "T", "C", 1, "int", nullable=raw)]},
                [], project="p", database="d", db_type="x")
            self.assertEqual(s["entities"][0]["fields"][0]["nullable"], expected,
                             f"flag {raw!r} misread")

    def test_homonym_tables_across_schemas_are_kept_distinct_and_warned(self):
        s = self._build(columns=[
            _col("dbo", "Orders", "Id", 1, "int"),
            _col("sales", "Orders", "Id", 1, "int"),
        ], primary_keys=[], foreign_keys=[], indexes=[], checks=[])
        self.assertEqual(len(s["entities"]), 2)
        self.assertTrue(any("REVERSE_DB_HOMONYM" in w for w in s["parseWarnings"]))

    def test_partial_catalog_degrades_with_warning_not_crash(self):
        """One denied grant must not abort an otherwise successful run."""
        s = dsl.build_live_schema(
            {"columns": [_col("dbo", "T", "Id", 1, "int")]},
            [], project="p", database="d", db_type="sqlserver",
            warnings=["[REVERSE_DB_SCHEMA_PARTIAL] 'checks' failed: denied"])
        self.assertEqual(len(s["entities"]), 1)
        self.assertEqual(s["checks"], [])
        self.assertTrue(any("denied" in w for w in s["parseWarnings"]))
        self.assertTrue(any("primary_keys" in w for w in s["parseWarnings"]))

    def test_empty_catalog_emits_an_actionable_hint(self):
        s = dsl.build_live_schema({}, [], project="p", database="d", db_type="x")
        self.assertEqual(s["entities"], [])
        self.assertTrue(s["missingPartsHint"])
        self.assertIn("rights", s["missingPartsHint"][0])

    def test_views_and_triggers_come_from_the_analysed_routines(self):
        s = self._build(routines=[
            {"fqName": "dbo.vActive", "routineType": "VIEW", "evidence": "a.sql:1-9"},
            {"fqName": "dbo.trgAudit", "routineType": "SQL_TRIGGER", "evidence": "b.sql:1-5"},
            {"fqName": "dbo.usp_Do", "routineType": "SQL_STORED_PROCEDURE", "evidence": "c.sql:1-3"},
        ])
        self.assertEqual([v["name"] for v in s["views"]], ["dbo.vActive"])
        self.assertEqual([t["name"] for t in s["triggers"]], ["dbo.trgAudit"])

    def test_catalog_objects_are_counted_by_kind(self):
        s = self._build(objects=[
            {"kind": "job", "schema": "msdb", "name": "Nightly", "detail": "enabled=1"},
            {"kind": "job", "schema": "msdb", "name": "Purge", "detail": "enabled=0"},
            {"kind": "sequence", "schema": "dbo", "name": "SeqOrder", "detail": "start=1"},
        ])
        self.assertEqual(s["summary"]["catalogObjectsByKind"],
                         {"job": 2, "sequence": 1})

    def test_summary_counts(self):
        s = self._build()
        self.assertEqual(s["summary"]["tables"], 2)
        self.assertEqual(s["summary"]["columns"], 5)
        self.assertEqual(s["summary"]["relations"], 1)
        self.assertEqual(s["summary"]["checks"], 1)


class TestSnapshotAndEvidence(unittest.TestCase):
    """Evidence must stay `file:line` — a live catalog has no lines, so we
    render a readable snapshot and anchor into it."""

    def _write(self, tmp: Path):
        schema = dsl.build_live_schema(
            {
                "columns": [
                    _col("dbo", "Clients", "Id", 1, "int", identity=1, nullable=0),
                    _col("dbo", "Clients", "Name", 2, "nvarchar", max_length=100),
                ],
                "primary_keys": [("dbo", "Clients", "PK_Clients", "Id", 1)],
                "foreign_keys": [],
                "indexes": [("dbo", "Clients", "UQ_Name", "Name", 1, 0, 1)],
                "checks": [("dbo", "Clients", "CK_Name", "(len([Name])>(0))")],
            },
            [{"kind": "job", "schema": "msdb", "name": "Nightly",
              "detail": "enabled=1 | command=EXEC dbo.usp_Recalc"}],
            project="OrdersDb", database="OrdersDb", db_type="sqlserver")
        return dsl.write_live_schema(tmp, schema)

    def test_snapshot_file_written_and_entity_evidence_points_at_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            schema = self._write(root)
            ent = schema["entities"][0]
            snap = root / ".sys" / "schema-snapshot" / "dbo.Clients.sql"
            self.assertTrue(snap.is_file())
            self.assertEqual(ent["snapshotFile"], ".sys/schema-snapshot/dbo.Clients.sql")
            self.assertRegex(ent["evidence"][0], r"^\.sys/schema-snapshot/.+:1-\d+$")

    def test_each_column_evidence_points_at_its_own_line(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            schema = self._write(root)
            snap = (root / ".sys" / "schema-snapshot" / "dbo.Clients.sql")
            lines = snap.read_text(encoding="utf-8").splitlines()
            for field in schema["entities"][0]["fields"]:
                line_no = int(field["evidence"].rsplit(":", 1)[1])
                self.assertIn(field["name"], lines[line_no - 1],
                              f"{field['name']} evidence points at the wrong line")

    def test_snapshot_documents_keys_indexes_and_checks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root)
            text = (root / ".sys" / "schema-snapshot" / "dbo.Clients.sql").read_text(encoding="utf-8")
            self.assertIn("PRIMARY KEY", text)
            self.assertIn("IDENTITY", text)
            self.assertIn("UNIQUE UQ_Name", text)
            self.assertIn("CK_Name", text)
            self.assertIn("Never executed", text)

    def test_catalog_objects_snapshot_gives_jobs_an_evidence_line(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            schema = self._write(root)
            job = schema["catalogObjects"][0]
            path = root / ".sys" / "schema-snapshot" / "_catalog-objects.txt"
            lines = path.read_text(encoding="utf-8").splitlines()
            line_no = int(job["evidence"].rsplit(":", 1)[1])
            self.assertIn("Nightly", lines[line_no - 1])
            self.assertIn("usp_Recalc", lines[line_no - 1])

    def test_db_schema_json_is_written_and_parseable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write(root)
            data = json.loads((root / ".sys" / "db-schema.json").read_text(encoding="utf-8"))
            self.assertEqual(data["completeness"], "live")
            self.assertEqual(data["summary"]["tables"], 1)

    def test_contract_matches_the_static_extractor(self):
        """reverse_synth / reverse-tech-analyst read this shape — it must not drift."""
        import tempfile
        from sdd_reverse.db_schema_extractor import DB_SCHEMA_VERSION
        with tempfile.TemporaryDirectory() as td:
            schema = self._write(Path(td))
        for key in ("schemaVersion", "project", "extractDate", "source",
                    "completeness", "databaseType", "entities", "relations",
                    "views", "triggers", "indexes", "parseWarnings",
                    "missingPartsHint"):
            self.assertIn(key, schema, f"missing static-extractor key {key!r}")
        self.assertEqual(schema["schemaVersion"], DB_SCHEMA_VERSION)
        for ent in schema["entities"]:
            for key in ("name", "table", "evidence", "fields"):
                self.assertIn(key, ent)
            for field in ent["fields"]:
                for key in ("name", "type", "primaryKey", "identity",
                            "nullable", "default"):
                    self.assertIn(key, field)


if __name__ == "__main__":
    unittest.main()
