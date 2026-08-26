"""db_introspect.py — Live, READ-ONLY stored-procedure introspection adapter.

The ONLY component that touches a live database. It connects, reads routine
definitions from the catalog (every statement passes `readonly_guard`), writes a
machine snapshot under `.sys/`, then disconnects. It never issues DDL/DML, never
runs the procedures, never logs the password, never persists the connection
string.

Design for testability + zero-dep philosophy:
  - the connection layer (`connect`, `fetch_rows`) lazily imports `pyodbc`
    (opt-in extra `reverse-db`); absent → clear `[REVERSE_DB_UNREACHABLE]`.
  - the analysis + snapshot layer (`build_introspection`, `write_snapshot`) is
    PURE: it takes routine rows (tuples in `ROUTINE_COLUMNS` order) and runs
    fully offline, so the whole pipeline is unit-tested without a database.

Snapshot layout (internal, machine-managed — NOT a user-facing `proc/` dir):
    workspace/old/{Db}/.sys/proc-snapshot/{schema}.{name}.sql   # lossless body
    workspace/old/{Db}/.sys/db-introspection.json               # metadata + signals

Evidence (for the FEAT/US anti-hallucination contract) points into the snapshot:
    <!-- evidence: .sys/proc-snapshot/dbo.usp_X.sql:L1-L142 -->

Public API:
    compose_connection_string(cfg, dialect) -> str          # in RAM only
    connect(conn_str)                                        # lazy pyodbc
    fetch_rows(conn, dialect, proc=None) -> list[tuple]
    build_introspection(rows, dialect, *, server, database, lang_cap="high", proc=None) -> dict
    write_snapshot(project_root, introspection) -> dict     # adds snapshotFile + evidence
    introspect(cfg, project_root, *, proc=None, lang_cap="high") -> dict   # full live flow
    class ReverseDbError(Exception)                          # .error_class
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text
from sdd_reverse.dialects import ROUTINE_COLUMNS, Dialect
from sdd_reverse.readonly_guard import assert_readonly, assert_session_pragma
from sdd_reverse.sql_body_analyzer import analyze_routine, confidence_signal
from sdd_reverse.sql_dependency_graph import build_dependency_graph

SCHEMA_VERSION = 1
_SNAPSHOT_DIR = "proc-snapshot"
_INTROSPECTION_NAME = "db-introspection.json"


class ReverseDbError(Exception):
    """DB-side failure carrying a `[REVERSE_*]` class for chat/log surfacing."""

    def __init__(self, message: str, error_class: str) -> None:
        super().__init__(message)
        self.error_class = error_class


# --------------------------------------------------------------------------- #
# Connection layer (live — lazy driver)
# --------------------------------------------------------------------------- #

def compose_connection_string(cfg: Any, dialect: Dialect) -> str:
    """Build a connection string in RAM. Never logged, never persisted.

    Read-only intent is signalled where the driver supports it (defence in
    depth) — the guard, not the connection, is the real read-only authority.
    """
    port = cfg.port or str(dialect.default_port)
    if dialect.id == "sqlserver":
        server = f"{cfg.host},{port}" if cfg.host else cfg.host
        parts = [
            "DRIVER={ODBC Driver 18 for SQL Server}",
            f"SERVER={server}",
            f"DATABASE={cfg.name}",
            "Encrypt=yes",
            "TrustServerCertificate=yes",
            "ApplicationIntent=ReadOnly",
            "Connection Timeout=10",
        ]
        if cfg.user:
            parts += [f"UID={cfg.user}", f"PWD={cfg.password}"]
        else:
            parts.append("Trusted_Connection=yes")
        return ";".join(parts) + ";"
    if dialect.id == "postgresql":
        # libpq DSN (psycopg2/psycopg accept this). connect_timeout fast-fails.
        parts = [
            f"host={cfg.host}",
            f"port={port}",
            f"dbname={cfg.name}",
            "connect_timeout=10",
        ]
        if cfg.user:
            parts.append(f"user={cfg.user}")
        if cfg.password:
            parts.append(f"password={cfg.password}")
        return " ".join(parts)
    if dialect.id == "oracle":
        # python-oracledb easy-connect: user/password@host:port/service.
        cred = f"{cfg.user}/{cfg.password}@" if cfg.user else ""
        return f"{cred}{cfg.host}:{port}/{cfg.name}"
    if dialect.id == "mysql":
        # Semicolon DSN parsed by _connect_mysql into connector kwargs.
        parts = [f"host={cfg.host}", f"port={port}", f"database={cfg.name}"]
        if cfg.user:
            parts.append(f"user={cfg.user}")
        if cfg.password:
            parts.append(f"password={cfg.password}")
        return ";".join(parts)
    raise ReverseDbError(
        f"[REVERSE_DB_CONFIG_MISSING] no connection builder for dialect {dialect.id!r}",
        "[REVERSE_DB_CONFIG_MISSING]",
    )


def connect(conn_str: str, dialect: Dialect):  # noqa: ANN201 — driver Connection (lazy)
    """Open a read-only connection with the dialect's driver (lazy import)."""
    if dialect.id == "sqlserver":
        return _connect_pyodbc(conn_str)
    if dialect.id == "postgresql":
        return _connect_psycopg(conn_str)
    if dialect.id == "oracle":
        return _connect_oracledb(conn_str)
    if dialect.id == "mysql":
        return _connect_mysql(conn_str)
    raise ReverseDbError(
        f"[REVERSE_DB_CONFIG_MISSING] no driver for dialect {dialect.id!r}",
        "[REVERSE_DB_CONFIG_MISSING]",
    )


def _connect_pyodbc(conn_str: str):  # noqa: ANN202
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        raise ReverseDbError(
            "[REVERSE_DB_UNREACHABLE] pyodbc not installed — "
            "`pip install -e .sdd/python[reverse-db]` (needs ODBC Driver 18)",
            "[REVERSE_DB_UNREACHABLE]",
        ) from exc
    try:
        conn = pyodbc.connect(conn_str, readonly=True, timeout=10)
    except pyodbc.Error as exc:  # type: ignore[attr-defined]
        msg = str(exc)
        klass = "[REVERSE_DB_AUTH_FAILED]" if _looks_like_auth(msg) else "[REVERSE_DB_UNREACHABLE]"
        raise ReverseDbError(f"{klass} {msg[:160]}", klass) from exc
    _harden_session(conn, "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
    return conn


def _connect_psycopg(conn_str: str):  # noqa: ANN202
    try:
        import psycopg2 as driver  # type: ignore
    except ImportError:
        try:
            import psycopg as driver  # type: ignore
        except ImportError as exc:
            raise ReverseDbError(
                "[REVERSE_DB_UNREACHABLE] psycopg2/psycopg not installed — "
                "`pip install -e .sdd/python[reverse-db]`",
                "[REVERSE_DB_UNREACHABLE]",
            ) from exc
    try:
        conn = driver.connect(conn_str)
    except Exception as exc:
        msg = str(exc)
        klass = "[REVERSE_DB_AUTH_FAILED]" if _looks_like_auth(msg) else "[REVERSE_DB_UNREACHABLE]"
        raise ReverseDbError(f"{klass} {msg[:160]}", klass) from exc
    # Defence in depth: whole session refuses writes.
    try:
        conn.set_session(readonly=True, autocommit=True)
    except Exception:  # pragma: no cover - best effort
        pass
    return conn


def _connect_oracledb(conn_str: str):  # noqa: ANN202
    try:
        import oracledb  # type: ignore
    except ImportError as exc:
        raise ReverseDbError(
            "[REVERSE_DB_UNREACHABLE] python-oracledb not installed — "
            "`pip install -e .sdd/python[reverse-db]`",
            "[REVERSE_DB_UNREACHABLE]",
        ) from exc
    try:
        conn = oracledb.connect(conn_str)  # thin mode, no Oracle client needed
    except Exception as exc:  # oracledb.Error hierarchy
        msg = str(exc)
        klass = "[REVERSE_DB_AUTH_FAILED]" if _looks_like_auth(msg) else "[REVERSE_DB_UNREACHABLE]"
        raise ReverseDbError(f"{klass} {msg[:160]}", klass) from exc
    # Defence in depth: read-only transaction for the whole session.
    _harden_session(conn, "SET TRANSACTION READ ONLY")
    return conn


def _connect_mysql(conn_str: str):  # noqa: ANN202
    kv = dict(
        part.split("=", 1) for part in conn_str.split(";") if "=" in part
    )
    if "port" in kv:
        try:
            kv["port"] = int(kv["port"])
        except ValueError:
            kv.pop("port")
    driver = None
    try:
        import mysql.connector as driver  # type: ignore
    except ImportError:
        try:
            import pymysql as driver  # type: ignore
        except ImportError as exc:
            raise ReverseDbError(
                "[REVERSE_DB_UNREACHABLE] mysql-connector-python / PyMySQL not installed — "
                "`pip install -e .sdd/python[reverse-db]`",
                "[REVERSE_DB_UNREACHABLE]",
            ) from exc
    try:
        conn = driver.connect(**kv)
    except Exception as exc:
        msg = str(exc)
        klass = "[REVERSE_DB_AUTH_FAILED]" if _looks_like_auth(msg) else "[REVERSE_DB_UNREACHABLE]"
        raise ReverseDbError(f"{klass} {msg[:160]}", klass) from exc
    # Defence in depth: read-only session (best effort — ignore if unsupported).
    _harden_session(conn, "SET SESSION TRANSACTION READ ONLY")
    return conn


def _harden_session(conn, pragma: str) -> None:
    """Issue one whitelisted session pragma, best effort (N1, audit 2026-08-25).

    Goes through `assert_session_pragma` so NO statement reaches a cursor without
    passing a guard — the invariant `reverse-db-readonly` claims exactly that, and
    these three `SET TRANSACTION ...` calls used to bypass it entirely.
    A pragma the engine rejects (unsupported syntax, insufficient right) is
    non-fatal: the read-only guarantee rests on the guard, not on the pragma.
    """
    assert_session_pragma(pragma)
    try:
        conn.cursor().execute(pragma)
    except Exception:  # pragma: no cover - best effort, engine-dependent
        pass


def _looks_like_auth(msg: str) -> bool:
    m = msg.lower()
    return any(s in m for s in (
        "login failed", "28000", "18456", "permission", "authentication",
        "password authentication failed", "role", "no password supplied",
    ))


def fetch_rows(conn, dialect: Dialect, proc: str | None = None) -> list[tuple]:
    """Run the guarded catalog query and return rows in ROUTINE_COLUMNS order."""
    cur = conn.cursor()
    if proc:
        schema, _, name = proc.rpartition(".")
        sql = dialect.single_routine_sql
        assert_readonly(sql)                 # hard barrier before execution
        cur.execute(sql, (name or proc, schema, schema))
    else:
        sql = dialect.list_routines_sql
        assert_readonly(sql)
        cur.execute(sql)
    rows = [tuple(r) for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_dependency_rows(conn, dialect: Dialect) -> list[tuple]:
    """Run the dialect's OPTIONAL authoritative dependency query (read-only).

    Returns rows in DEPENDENCY_COLUMNS order, or [] if the dialect declares no
    dependency query. The query passes the same hard read-only barrier.
    """
    if not dialect.dependency_query:
        return []
    assert_readonly(dialect.dependency_query)
    cur = conn.cursor()
    cur.execute(dialect.dependency_query)
    rows = [tuple(r) for r in cur.fetchall()]
    cur.close()
    return rows


# --------------------------------------------------------------------------- #
# Analysis + snapshot layer (PURE — offline-testable)
# --------------------------------------------------------------------------- #

def build_introspection(
    rows: list[tuple],
    dialect: Dialect,
    *,
    server: str,
    database: str,
    lang_cap: str = "high",
    proc: str | None = None,
) -> dict[str, Any]:
    """Turn catalog rows into the introspection model (no secrets, no connection)."""
    col = {c: i for i, c in enumerate(ROUTINE_COLUMNS)}
    procedures: list[dict[str, Any]] = []
    call_graph: list[dict[str, str]] = []
    encrypted: list[str] = []

    for i, row in enumerate(rows, start=1):
        schema = str(row[col["schema"]] or "dbo")
        name = str(row[col["name"]])
        rtype = str(row[col["routine_type"]] or "")
        definition = row[col["definition"]]
        modified = row[col["modified"]]
        is_enc = bool(row[col["is_encrypted"]]) or definition is None
        body = "" if is_enc else str(definition)
        fq = f"{schema}.{name}"

        signals = analyze_routine(fq, body)
        conf = "low" if is_enc else confidence_signal(signals, lang_cap)
        if is_enc:
            encrypted.append(fq)

        for callee in signals.get("calls", []):
            call_graph.append({"from": fq, "to": callee})

        procedures.append({
            "id": f"SP-{i}",
            "schema": schema,
            "name": name,
            "fqName": fq,
            "routineType": rtype,
            "encrypted": is_enc,
            "lineCount": signals["lineCount"],
            "params": signals["params"],
            "tablesRead": signals["tablesRead"],
            "tablesWritten": signals["tablesWritten"],
            "callsProcs": signals["calls"],
            "branches": signals["branches"],
            "raises": signals["raises"],
            "hasTransaction": signals["hasTransaction"],
            "hasTryCatch": signals["hasTryCatch"],
            "dynamicSql": signals["dynamicSql"],
            "cursors": signals["cursors"],
            "confidenceEstimate": conf,
            "modified": str(modified) if modified is not None else None,
            "_body": body,           # consumed by write_snapshot, stripped after
        })

    return {
        "schemaVersion": SCHEMA_VERSION,
        "databaseType": dialect.id,
        "languageId": dialect.language_id,
        "server": server,           # host only — never the password/connstring
        "database": database,
        "procFilter": proc,
        "introspectDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "procedures": procedures,
        "callGraph": call_graph,
        # P0.2 (2026-07-24) — object↔object dependency graph derived from the
        # body-analysis signals (cross-engine, deterministic). Powers impact
        # analysis + cohesion clustering. Additive; callGraph kept for compat.
        "dependencyGraph": build_dependency_graph(procedures),
        "encryptedProcedures": encrypted,
        "summary": {
            "proceduresCount": len(procedures),
            "encryptedCount": len(encrypted),
        },
    }


def write_snapshot(project_root: str | Path, introspection: dict[str, Any]) -> dict[str, Any]:
    """Write one .sql per routine + db-introspection.json under .sys/.

    Each procedure gains `snapshotFile` (relative to project_root) and `evidence`
    (`<file>:L1-L{lineCount}`) so downstream FEAT/US items satisfy the
    anti-hallucination evidence contract. `_body` is removed from the JSON.
    """
    root = Path(project_root).resolve()
    snap_dir = root / ".sys" / _SNAPSHOT_DIR

    for proc in introspection["procedures"]:
        fname = f"{proc['schema']}.{proc['name']}.sql"
        rel = f".sys/{_SNAPSHOT_DIR}/{fname}"
        lc = max(1, proc.get("lineCount", 1))
        # Merge-safe: a procedure carried over from a prior introspection has no
        # `_body` (already on disk) — keep its existing snapshot + metadata,
        # NEVER overwrite it with an empty/placeholder file.
        if "_body" not in proc:
            proc.setdefault("snapshotFile", rel)
            proc.setdefault("evidence", f"{rel}:1-{lc}")
            continue
        body = proc.pop("_body", "")
        content = body if body.endswith("\n") else body + "\n"
        if not body:
            content = (
                f"-- [REVERSE_PROC_ENCRYPTED] {proc['fqName']} : "
                f"definition unavailable (WITH ENCRYPTION or VIEW DEFINITION denied).\n"
            )
        atomic_write_text(snap_dir / fname, content)
        proc["snapshotFile"] = rel
        # Evidence must match validate_reverse_feat EVIDENCE_COMMENT_RE: path:NN-NN
        # (plain digits, no "L" prefix — feat_structure_spec.EVIDENCE_COMMENT_RE).
        proc["evidence"] = f"{rel}:1-{lc}"

    introspection_path = root / ".sys" / _INTROSPECTION_NAME
    atomic_write_text(
        introspection_path,
        json.dumps(introspection, indent=2, ensure_ascii=False) + "\n",
    )
    return introspection


def merge_introspection(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge a freshly-introspected (single-proc) model into a prior model.

    Incremental workflow: reversing one more procedure of the same object must
    GROW the database snapshot, not overwrite it. Procedures are keyed by
    fqName (new replaces old); SP ids are re-sequenced; call graph + encrypted
    lists are unioned; the summary is recomputed. Both inputs are post-snapshot
    (procedures carry snapshotFile/evidence, no _body).
    """
    by_fq: dict[str, dict] = {p["fqName"]: p for p in existing.get("procedures", [])}
    for p in new.get("procedures", []):
        by_fq[p["fqName"]] = p          # new wins
    procedures = sorted(by_fq.values(), key=lambda p: p["fqName"].lower())
    for i, p in enumerate(procedures, start=1):
        p["id"] = f"SP-{i}"

    call_graph = {(e["from"], e["to"]) for e in existing.get("callGraph", [])}
    call_graph |= {(e["from"], e["to"]) for e in new.get("callGraph", [])}
    encrypted = sorted({*existing.get("encryptedProcedures", []),
                        *new.get("encryptedProcedures", [])})

    merged = dict(new)               # keep new's databaseType/languageId/server/db
    merged["procedures"] = procedures
    merged["callGraph"] = [{"from": a, "to": b} for a, b in sorted(call_graph)]
    # P0.2 — recompute the dependency graph from the merged object set.
    merged["dependencyGraph"] = build_dependency_graph(procedures)
    merged["encryptedProcedures"] = encrypted
    merged["procFilter"] = None      # the snapshot now spans more than one proc
    merged["summary"] = {
        "proceduresCount": len(procedures),
        "encryptedCount": len(encrypted),
    }
    return merged


def introspect(
    cfg: Any, project_root: str | Path, *, proc: str | None = None, lang_cap: str = "high",
    with_schema: bool = True, obj_filter: Any = None,
) -> dict[str, Any]:
    """Full live flow: connect → guarded fetch → analyse → snapshot → disconnect.

    `with_schema` (C1, audit 2026-08-25) additionally reads the LIVE relational
    structure (tables/columns/datatypes/keys/indexes/checks) and the body-less
    catalog objects (jobs, sequences, synonyms, linked servers, user types), and
    writes `db-schema.json` with `completeness: "live"`. Whole-database runs only:
    a single-object run (`--proc`) must not pay for a full catalog sweep, and
    would produce a schema unrelated to the object asked for.
    """
    from sdd_reverse.dialects import get_dialect
    dialect = get_dialect(cfg.db_type)
    conn_str = compose_connection_string(cfg, dialect)
    conn = connect(conn_str, dialect)
    dep_rows: list[tuple] = []
    schema_rows: dict[str, list[tuple]] = {}
    catalog_objects: list[dict[str, Any]] = []
    schema_warnings: list[str] = []
    try:
        rows = fetch_rows(conn, dialect, proc=proc)
        # P0.2 catalog augmentation — authoritative object↔object deps, whole-DB
        # only (skipped for a single-proc run). Best-effort: a permission error
        # or unsupported catalog leaves the body-derived graph intact.
        if not proc and dialect.dependency_query:
            try:
                dep_rows = fetch_dependency_rows(conn, dialect)
            except Exception:  # pragma: no cover - best effort
                dep_rows = []
        if not proc and with_schema:
            from sdd_reverse import db_schema_live as dsl
            schema_rows, w1 = dsl.fetch_structure(conn, dialect)
            catalog_objects, w2 = dsl.fetch_catalog_objects(conn, dialect)
            schema_warnings = w1 + w2
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass
    if proc and not rows:
        raise ReverseDbError(
            f"[REVERSE_PROC_NOT_FOUND] {proc!r} not found in {cfg.name}",
            "[REVERSE_PROC_NOT_FOUND]",
        )
    # M6 — bound the scope AFTER the fetch, so the guarded SQL stays constant.
    filter_report: dict[str, Any] = {"active": False}
    if obj_filter is not None and getattr(obj_filter, "is_active", False):
        rows, filter_report = obj_filter.apply(rows, ROUTINE_COLUMNS)

    model = build_introspection(
        rows, dialect, server=cfg.host, database=cfg.name, lang_cap=lang_cap, proc=proc
    )
    if filter_report.get("active"):
        model["objectFilter"] = filter_report
    if dep_rows:
        from sdd_reverse.dialects.base import DEPENDENCY_COLUMNS
        from sdd_reverse.sql_dependency_graph import merge_catalog_dependencies
        merge_catalog_dependencies(model["dependencyGraph"], dep_rows, DEPENDENCY_COLUMNS)
    model = write_snapshot(project_root, model)

    # C1 — live structure written alongside, in the SAME contract the static
    # extractor emits, so reverse_synth / reverse-tech-analyst need no change.
    # `routines` is passed post-snapshot so views/triggers carry real evidence.
    if schema_rows or catalog_objects or schema_warnings:
        from sdd_reverse import db_schema_live as dsl
        schema = dsl.build_live_schema(
            schema_rows, catalog_objects,
            project=Path(project_root).name, database=cfg.name,
            db_type=dialect.id, routines=model.get("procedures"),
            warnings=schema_warnings,
        )
        dsl.write_live_schema(project_root, schema)
        model["schemaSummary"] = schema.get("summary", {})
        model["schemaCompleteness"] = schema.get("completeness")
    return model
