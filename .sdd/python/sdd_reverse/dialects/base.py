"""dialects/base.py — Dialect contract for DB stored-procedure reverse.

A *dialect* is the only DB-engine-specific surface of the db-reverse module.
It carries:
  - the catalog **read** queries to enumerate routines and fetch their bodies
    (all pure `SELECT` — validated by `readonly_guard.is_readonly`);
  - the `language_id` used to look up the confidence cap in
    `language_signatures.yml` (e.g. SQL Server → `tsql`).

The LLM analyst (`reverse-sql-analyst`) and every deterministic helper
(`sql_body_analyzer`, `proc_module_clusterer`) are dialect-AGNOSTIC: they work
on the routine bodies regardless of engine. Adding Postgres/Oracle/MySQL means
adding one `Dialect` here — no change to the agent or the pipeline.

Row contract: `list_routines_sql` / `single_routine_sql` MUST return columns in
the order declared by `ROUTINE_COLUMNS`.

STRUCTURE (audit 2026-08-25, finding C1) — until this pass, a dialect only knew
how to read objects that carry a BODY (procedures, functions, views, triggers).
Tables, columns, datatypes, keys and indexes were never read from a live
catalog: they were guessed by regex from procedure bodies, or parsed from `.sql`
files in a legacy repository that does not exist when the only input is a
connection string. Two optional surfaces close that gap, both pure SELECT:

  - `schema_queries`      : the relational structure (see the *_ROW contracts).
  - `catalog_object_queries`: everything else the catalog knows and that carries
    business meaning without a body — scheduler jobs, sequences, synonyms,
    linked servers, user-defined types.

Both are tuples of `(name, sql)` pairs rather than dicts so a `Dialect` stays a
frozen, hashable value. Every query is validated read-only at construction, and
each is executed INDEPENDENTLY and best-effort: `msdb` or `pg_cron` may be
unreadable for the introspection login, and one missing grant must degrade the
report with a warning, never abort the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Column order every dialect's routine query must return.
ROUTINE_COLUMNS = ("schema", "name", "routine_type", "definition", "modified", "is_encrypted")

# Column order for the OPTIONAL authoritative dependency query (P0.2 catalog
# augmentation, 2026-07-24). Each row = one edge from → to.
DEPENDENCY_COLUMNS = ("from_schema", "from_name", "to_schema", "to_name", "dep_type")

# --------------------------------------------------------------------------- #
# Live structure contracts (C1, audit 2026-08-25)
# --------------------------------------------------------------------------- #

# One row per COLUMN of every user table. `data_type` is the engine's own type
# name — the reverse must report the legacy type, never a normalised guess.
COLUMN_ROW = (
    "schema", "table", "column", "ordinal", "data_type", "max_length",
    "precision", "scale", "is_nullable", "column_default", "is_identity",
    "is_computed", "computed_definition",
)
# One row per column participating in a primary key.
PK_ROW = ("schema", "table", "constraint_name", "column", "ordinal")
# One row per column pair of a foreign key (composite FKs yield several rows).
FK_ROW = (
    "constraint_name", "from_schema", "from_table", "from_column",
    "to_schema", "to_table", "to_column",
)
# One row per column of an index.
INDEX_ROW = (
    "schema", "table", "index_name", "column", "is_unique", "is_primary", "ordinal",
)
# One row per CHECK constraint — these carry business rules in plain SQL.
CHECK_ROW = ("schema", "table", "constraint_name", "definition")
# One row per body-less catalog object (job, sequence, synonym, linked server,
# user type). `detail` is a free-text, engine-specific summary.
CATALOG_OBJECT_ROW = ("kind", "schema", "name", "detail")

# Recognised keys of `Dialect.schema_queries`, mapped to their row contract.
SCHEMA_QUERY_CONTRACTS = {
    "columns": COLUMN_ROW,
    "primary_keys": PK_ROW,
    "foreign_keys": FK_ROW,
    "indexes": INDEX_ROW,
    "checks": CHECK_ROW,
}


@dataclass(frozen=True)
class Dialect:
    id: str               # registry key, e.g. "sqlserver"
    label: str            # human label, e.g. "SQL Server (T-SQL)"
    language_id: str      # confidence_cap lookup in language_signatures.yml
    default_port: int
    driver_hint: str      # how to provision the read-only driver (doc/error aid)
    list_routines_sql: str   # SELECT all routines + bodies (ROUTINE_COLUMNS order)
    single_routine_sql: str  # SELECT one routine, parameterized (schema?, name?)
    dependency_query: str = ""  # OPTIONAL SELECT of authoritative object→object
                                # deps (DEPENDENCY_COLUMNS order). "" = engine has
                                # no usable catalog dep source (graph stays body-derived).
    # C1 — live relational structure. Keys must be in SCHEMA_QUERY_CONTRACTS.
    schema_queries: tuple[tuple[str, str], ...] = field(default=())
    # C1/P2.1 — body-less catalog objects, one query per kind (best-effort).
    catalog_object_queries: tuple[tuple[str, str], ...] = field(default=())

    def __post_init__(self) -> None:
        # Fail loud at construction if a dialect ever ships a non-read query.
        from sdd_reverse.readonly_guard import is_readonly
        queries = [self.list_routines_sql, self.single_routine_sql]
        if self.dependency_query:
            queries.append(self.dependency_query)
        queries += [sql for _, sql in self.schema_queries]
        queries += [sql for _, sql in self.catalog_object_queries]
        for sql in queries:
            if not is_readonly(sql):
                raise ValueError(
                    f"Dialect {self.id!r} declares a non-read-only query: "
                    f"{sql.strip()[:80]!r}"
                )
        unknown = {name for name, _ in self.schema_queries} - set(SCHEMA_QUERY_CONTRACTS)
        if unknown:
            raise ValueError(
                f"Dialect {self.id!r} declares unknown schema queries {sorted(unknown)}; "
                f"expected a subset of {sorted(SCHEMA_QUERY_CONTRACTS)}"
            )

    def schema_query(self, name: str) -> str:
        """The SQL for one named structure query, or '' if the dialect has none."""
        for key, sql in self.schema_queries:
            if key == name:
                return sql
        return ""
