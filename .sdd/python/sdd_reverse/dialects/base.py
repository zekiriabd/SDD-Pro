"""dialects/base.py — Dialect contract for DB stored-procedure reverse.

A *dialect* is the only DB-engine-specific surface of the proc-reverse module.
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
"""

from __future__ import annotations

from dataclasses import dataclass

# Column order every dialect's routine query must return.
ROUTINE_COLUMNS = ("schema", "name", "routine_type", "definition", "modified", "is_encrypted")

# Column order for the OPTIONAL authoritative dependency query (P0.2 catalog
# augmentation, 2026-07-24). Each row = one edge from → to.
DEPENDENCY_COLUMNS = ("from_schema", "from_name", "to_schema", "to_name", "dep_type")


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

    def __post_init__(self) -> None:
        # Fail loud at construction if a dialect ever ships a non-read query.
        from sdd_reverse.readonly_guard import is_readonly
        queries = [self.list_routines_sql, self.single_routine_sql]
        if self.dependency_query:
            queries.append(self.dependency_query)
        for sql in queries:
            if not is_readonly(sql):
                raise ValueError(
                    f"Dialect {self.id!r} declares a non-read-only query: "
                    f"{sql.strip()[:80]!r}"
                )
