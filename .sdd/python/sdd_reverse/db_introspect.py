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

import hashlib
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


def fetch_param_rows(conn, dialect: Dialect) -> list[tuple]:
    """Run the dialect's OPTIONAL catalog parameter query (read-only).

    Returns rows in PARAM_ROW order, or [] if the dialect declares no params
    query (its params are already fully recoverable from the body header).
    """
    if not dialect.params_query:
        return []
    assert_readonly(dialect.params_query)
    cur = conn.cursor()
    cur.execute(dialect.params_query)
    rows = [tuple(r) for r in cur.fetchall()]
    cur.close()
    return rows


def _params_by_fq(rows: list[tuple]) -> dict[str, list[dict[str, Any]]]:
    """Group PARAM_ROW rows into the same `{name, type, output}` shape the
    body-header regex (`sql_body_analyzer._params_from_header`) already
    produces, keyed by lowercased `schema.routine`, ordinal-ordered.
    """
    from sdd_reverse.dialects.base import PARAM_ROW
    col = {c: i for i, c in enumerate(PARAM_ROW)}
    by_fq: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for row in rows:
        fq = f"{row[col['schema']]}.{row[col['routine']]}".lower()
        mode = str(row[col["mode"]] or "").upper()
        by_fq.setdefault(fq, []).append((
            int(row[col["ordinal"]] or 0),
            {
                "name": str(row[col["name"]]),
                "type": str(row[col["type"]] or ""),
                "output": mode in ("OUT", "INOUT"),
            },
        ))
    return {fq: [p for _, p in sorted(entries)] for fq, entries in by_fq.items()}


# --------------------------------------------------------------------------- #
# Analysis + snapshot layer (PURE — offline-testable)
# --------------------------------------------------------------------------- #

def _snapshot_content(body: str) -> str:
    """Exactly the bytes `write_snapshot` will put on disk for this body."""
    return body if body.endswith("\n") else body + "\n"


def body_hash(body: str) -> str:
    """sha256 of the routine body, or '' when there is none (encrypted object).

    Same construction as `build_proc_us._snapshot_hash` (which hashes the
    snapshot file), so the two agree on what "the body changed" means.

    Load-bearing for M2 (audit 2026-08-29): `context_version()` hashes the FACTS,
    and the facts used to describe only the SHAPE of a body — line count,
    parameters, tables, calls, branch count. Editing a threshold inside an
    existing `IF` changed the behaviour of the database without changing any of
    those, so the context version stayed identical and `diff_contexts` reported
    no drift on a routine whose meaning had moved.
    """
    if not body:
        return ""
    digest = hashlib.sha256(_snapshot_content(body).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def _norm_fq(ident: str) -> str:
    if not ident:
        return ""
    return ident.strip().strip("[]`\"").strip().lower()


def attach_catalog_calls(model: dict[str, Any]) -> dict[str, Any]:
    """Project the catalog-sourced object→object edges onto each routine record.

    C2 (audit 2026-08-29). `merge_catalog_dependencies` folds the engine's own
    dependency catalog into `model["dependencyGraph"]` — authoritative data that
    resolves synonyms, renames and cross-schema references the body regex cannot.
    But `plan_waves` orders on the ROUTINE records, not on that graph, so the
    catalog data was collected and then discarded for the one purpose it is best
    at. This projects it back where the planner will see it, as `catalogCalls`.

    Only edges whose BOTH ends are routines in this model are kept: a dependency
    on a table is already covered by `tablesRead`/`tablesWritten` and would add a
    node the wave planner has no business ordering.
    """
    graph = model.get("dependencyGraph") or {}
    by_norm = {_norm_fq(str(p.get("fqName"))): str(p.get("fqName"))
               for p in model.get("procedures") or []}
    per_src: dict[str, set[str]] = {}
    for edge in graph.get("edges") or []:
        if "catalog" not in str(edge.get("source", "")):
            continue
        src, dst = _norm_fq(str(edge.get("from"))), _norm_fq(str(edge.get("to")))
        if src == dst or src not in by_norm or dst not in by_norm:
            continue
        per_src.setdefault(src, set()).add(by_norm[dst])
    for p in model.get("procedures") or []:
        names = sorted(per_src.get(_norm_fq(str(p.get("fqName"))), ()))
        if names:
            p["catalogCalls"] = names
        else:
            p.pop("catalogCalls", None)
    return model


def build_introspection(
    rows: list[tuple],
    dialect: Dialect,
    *,
    server: str,
    database: str,
    lang_cap: str = "high",
    proc: str | None = None,
    param_rows: list[tuple] | None = None,
) -> dict[str, Any]:
    """Turn catalog rows into the introspection model (no secrets, no connection).

    `param_rows` (audit 2026-08-29 m2, optional) — catalog-sourced PARAM_ROW
    rows, used to OVERRIDE the body-header-parsed params for a routine when
    the dialect's own catalog is the only place they are recoverable (e.g.
    MySQL, whose `ROUTINE_DEFINITION` never includes the signature). Absent or
    empty is a no-op: the body-derived `params` stands as before.
    """
    col = {c: i for i, c in enumerate(ROUTINE_COLUMNS)}
    catalog_params = _params_by_fq(param_rows) if param_rows else {}
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
        # Catalog params (when the dialect declares a params_query) override
        # the body-header regex BEFORE complexity/confidence scoring, so a
        # MySQL routine with a wide signature is still weighed on real param
        # count instead of the 0 the body text can never reveal.
        params = catalog_params.get(fq.lower())
        if params is not None:
            signals["params"] = params
        else:
            params = signals["params"]
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
            "params": params,
            "tablesRead": signals["tablesRead"],
            "tablesWritten": signals["tablesWritten"],
            # Which statement touched each table. `sql_body_analyzer` has always
            # computed it; it used to be dropped here, which is why the CRUD
            # matrix downstream could only say "written", never C vs U vs D.
            "writeKinds": signals.get("writeKinds", {}),
            "callsProcs": signals["calls"],
            # C1 — keyword-less invocations (PL/SQL `pkg.proc(…)`, scalar
            # functions inside an expression). Kept apart from `callsProcs`
            # because it is a heuristic: consumers resolve it against the real
            # object set and drop what does not match, so it can only add a true
            # edge, never a phantom unresolved callee.
            "callsInferred": signals.get("callsInferred", []),
            "branches": signals["branches"],
            "raises": signals["raises"],
            "hasTransaction": signals["hasTransaction"],
            "hasTryCatch": signals["hasTryCatch"],
            "dynamicSql": signals["dynamicSql"],
            "cursors": signals["cursors"],
            # M2 — content, not just shape. See `body_hash`.
            "bodyHash": body_hash(body),
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
    param_rows: list[tuple] = []
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
        # m2 (audit 2026-08-29) — catalog-sourced params for dialects whose body
        # text never carries the signature (MySQL). Same whole-DB-only, same
        # best-effort discipline as the dependency query above.
        if not proc and dialect.params_query:
            try:
                param_rows = fetch_param_rows(conn, dialect)
            except Exception:  # pragma: no cover - best effort
                param_rows = []
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
        rows, dialect, server=cfg.host, database=cfg.name, lang_cap=lang_cap, proc=proc,
        param_rows=param_rows,
    )
    if filter_report.get("active"):
        model["objectFilter"] = filter_report
    if dep_rows:
        from sdd_reverse.dialects.base import DEPENDENCY_COLUMNS
        from sdd_reverse.sql_dependency_graph import merge_catalog_dependencies
        merge_catalog_dependencies(model["dependencyGraph"], dep_rows, DEPENDENCY_COLUMNS)
        # C2 — project those authoritative edges back onto the routine records,
        # which is the shape `plan_waves` consumes. Without this the catalog was
        # read, guarded, merged into a graph, and then ignored for ordering.
        attach_catalog_calls(model)
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
