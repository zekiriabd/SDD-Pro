"""sdd_lib.console_db.core — connection, pragmas, schema migrations, row helpers.

v7.0.0-alpha (audit CRIT-12, 2026-06-04) — extracted from the previous
monolithic `console_db.py` (912 L → split in 3 thematic sub-modules).

Audit « fiabilité des données et des états » (2026-11-07) :
  - ``default_db_path()`` honore ``$SDD_CONSOLE_DB_PATH`` (via
    ``sdd_lib.paths.console_db_path``) → la suite pytest n'écrit plus dans
    la base runtime.
  - Migrations **atomiques et idempotentes** : chaque migration (et le
    chargement du schéma de base) s'exécute dans une transaction
    ``BEGIN IMMEDIATE`` qui contient AUSSI l'insertion ``schema_version`` ;
    tout ``ALTER TABLE … ADD COLUMN`` est gardé par ``PRAGMA table_info``
    (rejeu concurrent → no-op, plus jamais ``duplicate column name``).
  - ``ensure_initialized()`` est sérialisé par ``BEGIN IMMEDIATE`` + retry
    sur ``database is locked`` ; il marque aussi ``stale`` tout run resté
    ``running`` sans activité depuis > 24 h (migration de données légère).
  - ``connect_ro()`` ne retombe plus silencieusement sur ``immutable=1``
    (lectures périmées pour le cost cap) : échec explicite
    ``ConsoleDbUnavailable`` (classable ``[INFRA_BLOCKED]``). Le fallback
    immutable reste disponible derrière ``allow_stale=True`` (rapports).

Public API (re-exported via `sdd_lib.console_db.__init__`) :
    SCHEMA_VERSION, BASE_SCHEMA_VERSION, DEFAULT_DB_PATH,
    SCHEMA_SQL_PATH, MIGRATIONS_DIR, AUDITOR_IDS,
    STALE_RUN_AFTER_SECONDS, ConsoleDbUnavailable,
    default_db_path, connect, connect_ro,
    load_schema_sql, current_schema_version, apply_pending_migrations,
    ensure_initialized, mark_stale_runs, ensure_feat_row, ensure_us_row,
    _jdumps (semi-private — shared across runs.py + qa.py)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from sdd_lib.paths import console_db_path, iso_now_ms, repo_root

SCHEMA_VERSION = 9  # v7.0.0+ : v2 +qa_mutation, v3 +qa_e2e, v4 +auditor_runs (C3 fix), v5 +qa_api_tests.status (P3), v6 +build_loop_traces (audit CTO 2026-06-09 Bug #16 — migration 0006 stranded), v7 +agent_journal (audit 2026-08-28 correction #5 — traçabilité/replay), v8 +qa_*.detector (audit 2026-08-28 — anti-clobbering agent vs déterministe), v9 +delivery_evidence (audit 2026-11-07 — preuves de livraison HMAC, gates bloquantes)
# BASE_SCHEMA_VERSION is the version represented by ``console_db_schema.sql``
# itself (the "v1" full snapshot). When ``SCHEMA_VERSION`` exceeds it, the
# difference is bridged by forward migrations under ``migrations/``.
BASE_SCHEMA_VERSION = 1

# Schema + migrations live one level UP — at sdd_lib/ root, not inside
# the console_db/ sub-package. Adjusted in CRIT-12 to keep the legacy
# layout untouched (no SQL file moved).
_SDD_LIB_DIR = Path(__file__).resolve().parent.parent
SCHEMA_SQL_PATH = _SDD_LIB_DIR / "console_db_schema.sql"
MIGRATIONS_DIR = _SDD_LIB_DIR / "migrations"
_MIGRATION_FILE_RE = re.compile(r"^(\d{4})_[a-z0-9-]+\.sql$")

# Canonical auditor IDs — must match ENSURE_SCANS_REQUIRED_DEFAULT +
# ENSURE_SCANS_OPTIONAL in sdd_review.py.
AUDITOR_IDS = ("quality", "code-review", "security", "spec", "arch", "a11y", "perf")

#: A run still ``running`` with no activity (``updated_at``/``started_at``)
#: for longer than this is flagged ``stale`` by ``ensure_initialized()``.
STALE_RUN_AFTER_SECONDS = 24 * 3600


class ConsoleDbUnavailable(sqlite3.OperationalError):
    """console.db exists but cannot be opened for a *fresh* read.

    Raised by ``connect_ro()`` (default ``allow_stale=False``) instead of the
    former silent ``immutable=1`` fallback, which ignored the WAL and served
    stale rows to gate readers (``preflight_cost_cap``). Subclass of
    ``sqlite3.OperationalError`` so existing ``except sqlite3.Error`` /
    ``except Exception`` handlers keep working ; callers should classify it
    ``[INFRA_BLOCKED]`` (never treat the absence of data as « 0 cost »).
    """


def default_db_path() -> Path:
    """Resolve the console.db path.

    ``$SDD_CONSOLE_DB_PATH`` (absolute) wins ; otherwise
    ``workspace/db/console.db`` relative to the repo root. The ``repo_root``
    lookup stays in this module so tests may keep patching
    ``sdd_lib.console_db.core.repo_root``.
    """
    return console_db_path(repo_root())


DEFAULT_DB_PATH = default_db_path()


# Security audit 2026-06-06 — `database is locked` observed under parallel
# preflight hooks (≥2 agents spawned simultanément). busy_timeout 5s ne suffit
# pas quand plusieurs writers font INSERT en cascade. Bump à 30s + retry
# explicite avec backoff sur OperationalError pour les rares cas restants.
_BUSY_TIMEOUT_MS = 30000  # 30s — laisse SQLite WAL absorber la contention
_CONNECT_MAX_RETRY = 3
_CONNECT_RETRY_BACKOFF = (0.25, 0.5, 1.0)  # seconds

#: Retry budget for ``BEGIN IMMEDIATE`` in ``ensure_initialized`` (on top of
#: ``busy_timeout``) — covers the rare « database is locked » that escapes
#: SQLite's own wait when N hooks initialise a fresh DB simultaneously.
_TXN_MAX_RETRY = 5
_TXN_RETRY_BACKOFF_S = 0.2


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")


def _apply_pragmas_ro(conn: sqlite3.Connection) -> None:
    """Read-only pragmas: skip journal_mode mutation (read-only TX cannot ALTER
    the journal mode), but still set query_only as a defense-in-depth and a
    timeout to coexist with writers in WAL mode."""
    conn.execute("PRAGMA query_only = ON")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")


def _is_locked_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with pragmas applied, commit on success, rollback on exception.

    Retries up to 3× with exponential backoff on `database is locked` **during
    the open + pragma phase only** — the phase where parallel preflight hooks
    contend on the initial WAL setup. Once the connection is yielded, the
    `with` body and `commit()` are NOT retried (retrying a body with side
    effects would be unsafe, and a second `yield` from a `@contextmanager`
    generator raises `RuntimeError: generator didn't stop`). Commit-time lock
    contention is absorbed by `PRAGMA busy_timeout = 30s` (see `_apply_pragmas`).
    Final failure raises the underlying OperationalError so callers can decide
    (skip telemetry vs abort run).

    v7.0.1 audit fix (2026-06-12) — the previous implementation wrapped
    `yield conn` inside the retry loop, so any lock at commit/body time looped
    back to a second `yield` → `RuntimeError("generator didn't stop after
    throw()")` instead of a retry. The yield is now OUTSIDE the retry loop.
    """
    db_path = Path(db_path) if db_path is not None else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Phase 1 — open + pragmas, retried on transient "database is locked".
    conn: sqlite3.Connection | None = None
    for attempt in range(_CONNECT_MAX_RETRY):
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            _apply_pragmas(conn)
            break  # opened successfully → leave the retry loop
        except sqlite3.OperationalError as e:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                conn = None
            if not _is_locked_error(e) or attempt >= _CONNECT_MAX_RETRY - 1:
                raise
            time.sleep(_CONNECT_RETRY_BACKOFF[attempt])
    assert conn is not None  # loop either breaks with a live conn or raises

    # Phase 2 — single use; commit on success, rollback on any exception.
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


@contextmanager
def connect_ro(
    db_path: Path | str | None = None,
    *,
    allow_stale: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Read-only connection — safe on read-only filesystems / sandboxes.

    Unlike ``connect()``:
    - Opens via URI with ``mode=ro`` (no implicit CREATE).
    - Does NOT mkdir the parent directory (no write to FS).
    - Does NOT issue ``PRAGMA journal_mode=WAL`` (which requires writing the
      ``-wal``/``-shm`` files; harmless on RW DBs, but breaks on RO mounts).
    - Does NOT call ``ensure_initialized()`` — caller responsibility.
    - Raises a clear ``FileNotFoundError`` if the DB does not exist.

    Used by pure readers : ``report_token_usage.py``, ``query_console_db.py``,
    and the Node-side ``/api/audit`` / ``/api/state`` via the same convention.

    v7.0.0-alpha (2026-05-21) — telemetry trust fix :
      - URI built via ``Path.as_uri()`` instead of ad-hoc ``file:{posix}``
        for cross-platform compliance (Windows drive letters need 3 slashes :
        ``file:///G:/path``, not ``file:G:/path``).

    Audit fiabilité 2026-11-07 — ``allow_stale`` :
      - ``allow_stale=False`` (défaut, lecteurs de **gate** : cost cap,
        readiness…) : sur ``OperationalError: unable to open database file``
        (WAL ``-shm``/``-wal`` tenus par un writer sous Windows, parent RO),
        lève ``ConsoleDbUnavailable`` — **jamais** de lecture périmée qui
        ferait passer un cap à 0 $. L'appelant classe ``[INFRA_BLOCKED]``.
      - ``allow_stale=True`` (rapports, dashboards) : retombe sur
        ``immutable=1`` (SQLite ignore le journal → snapshot potentiellement
        périmé, mais lisible) avec un WARN stderr explicite.
    """
    db_path = Path(db_path) if db_path is not None else default_db_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"console.db not found at {db_path} — run /sdd-full or "
            f"init_console_db.py to bootstrap before opening in read-only mode."
        )

    base_uri = db_path.as_uri()  # portable, RFC-compliant (file:///path)
    uri_ro = f"{base_uri}?mode=ro"
    try:
        conn = sqlite3.connect(uri_ro, uri=True)
    except sqlite3.OperationalError as e:
        if "unable to open database file" not in str(e).lower():
            raise
        if not allow_stale:
            raise ConsoleDbUnavailable(
                f"[INFRA_BLOCKED] console.db at {db_path} cannot be opened for a "
                f"fresh read ({e}) — refusing the immutable=1 fallback (stale "
                f"WAL snapshot). Retry, or pass allow_stale=True for a report."
            ) from e
        print(
            f"WARN sdd_lib.console_db: {db_path} unreadable ({e}) — falling back "
            "to immutable=1 (allow_stale=True) : rows may be STALE (WAL ignored).",
            file=sys.stderr,
        )
        uri_immut = f"{base_uri}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri_immut, uri=True)

    conn.row_factory = sqlite3.Row
    try:
        _apply_pragmas_ro(conn)
        yield conn
    finally:
        conn.close()


def load_schema_sql() -> str:
    return SCHEMA_SQL_PATH.read_text(encoding="utf-8")


def current_schema_version(conn: sqlite3.Connection) -> int | None:
    """Return current schema_version row, or None if table is missing or empty."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return None
    row = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _list_pending_migrations(current: int) -> list[tuple[int, Path]]:
    """Return ``(target_version, sql_path)`` pairs to apply, sorted ascending.

    Filters files matching the canonical naming ``NNNN_slug.sql`` whose target
    version is strictly greater than ``current`` AND ≤ ``SCHEMA_VERSION``.
    See ``migrations/README.md`` for the convention.
    """
    if not MIGRATIONS_DIR.is_dir():
        return []
    pending: list[tuple[int, Path]] = []
    for sql_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = _MIGRATION_FILE_RE.match(sql_path.name)
        if m is None:
            continue
        target = int(m.group(1))
        if target <= current or target > SCHEMA_VERSION:
            continue
        pending.append((target, sql_path))
    return pending


# ---------------------------------------------------------------------------
# SQL script execution inside an explicit transaction
# ---------------------------------------------------------------------------
# ``executescript()`` issues a COMMIT before running and leaves nothing to
# join a transaction with, so the schema_version INSERT used to be a *second*
# transaction : a crash (or a concurrent writer) between the two left a DB
# migrated but unversioned → rejeu → ``duplicate column name``. We split the
# script ourselves (``sqlite3.complete_statement`` respects strings / trigger
# bodies) and run every statement on the SAME connection inside a single
# ``BEGIN IMMEDIATE``.

_SQL_LINE_COMMENT_RE = re.compile(r"^\s*--.*$", re.MULTILINE)
_ADD_COLUMN_RE = re.compile(
    r"^\s*ALTER\s+TABLE\s+[\"'`\[]?(?P<table>\w+)[\"'`\]]?\s+ADD\s+(?:COLUMN\s+)?"
    r"[\"'`\[]?(?P<column>\w+)[\"'`\]]?",
    re.IGNORECASE,
)


def split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into complete statements (comments stripped).

    Uses ``sqlite3.complete_statement`` as the oracle so ``;`` inside string
    literals or ``CREATE TRIGGER … BEGIN … END;`` bodies never splits early.
    """
    statements: list[str] = []
    buf = ""
    for chunk in sql.split(";"):
        buf += chunk + ";"
        if sqlite3.complete_statement(buf):
            cleaned = _SQL_LINE_COMMENT_RE.sub("", buf).strip()
            if cleaned.rstrip(";").strip():
                statements.append(cleaned)
            buf = ""
    tail = _SQL_LINE_COMMENT_RE.sub("", buf).strip().rstrip(";").strip()
    if tail:
        statements.append(tail + ";")
    return statements


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(r[1]).lower() == column.lower() for r in rows)


def _execute_script_guarded(conn: sqlite3.Connection, sql: str) -> int:
    """Execute ``sql`` statement by statement on ``conn`` (caller owns the TXN).

    ``ALTER TABLE t ADD COLUMN c`` is skipped when ``c`` already exists
    (``PRAGMA table_info`` guard) — makes every migration idempotent under
    concurrent replay. Returns the number of statements executed.
    """
    executed = 0
    for stmt in split_sql_statements(sql):
        m = _ADD_COLUMN_RE.match(stmt)
        if m and _column_exists(conn, m.group("table"), m.group("column")):
            continue
        conn.execute(stmt)
        executed += 1
    return executed


def _begin_immediate(conn: sqlite3.Connection) -> None:
    """``BEGIN IMMEDIATE`` with retry on « database is locked »."""
    if conn.in_transaction:
        return
    last: sqlite3.OperationalError | None = None
    for attempt in range(_TXN_MAX_RETRY):
        try:
            conn.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as e:
            if not _is_locked_error(e):
                raise
            last = e
            time.sleep(_TXN_RETRY_BACKOFF_S * (attempt + 1))
    assert last is not None
    raise last


def _apply_one_migration(conn: sqlite3.Connection, target: int, sql_path: Path) -> bool:
    """Apply one migration atomically. Returns False if already applied.

    The version check is re-done INSIDE the ``BEGIN IMMEDIATE`` so two
    writers racing on the same file serialise : the second one sees the row
    inserted by the first and skips.
    """
    sql = sql_path.read_text(encoding="utf-8")
    _begin_immediate(conn)
    try:
        already = conn.execute(
            "SELECT 1 FROM schema_version WHERE version = ?", (target,)
        ).fetchone()
        if already is not None:
            conn.execute("COMMIT")
            return False
        _execute_script_guarded(conn, sql)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(?, ?)",
            (target, iso_now_ms()),
        )
        conn.execute("COMMIT")
        return True
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise


def apply_pending_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply all migrations strictly newer than the current schema version.

    Each migration file runs inside its own explicit ``BEGIN IMMEDIATE``
    transaction **together with** its ``schema_version`` row (atomic : either
    both land or neither). ``ALTER TABLE … ADD COLUMN`` statements are
    guarded by ``PRAGMA table_info`` → idempotent under concurrent replay.
    Forward-only — no down-migration.

    Returns the list of applied target versions (empty if none).
    """
    current = current_schema_version(conn) or 0
    applied: list[int] = []
    for target, sql_path in _list_pending_migrations(current):
        if _apply_one_migration(conn, target, sql_path):
            applied.append(target)
    return applied


def _stale_cutoff_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=STALE_RUN_AFTER_SECONDS)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def mark_stale_runs(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """Flag ``running`` runs idle for > ``STALE_RUN_AFTER_SECONDS`` as ``stale``.

    Idempotent data migration (audit 2026-11-07 : 8 runs ``command='hook'``
    restés ``running`` pour toujours). Activity = ``updated_at`` (fallback
    ``started_at``). ISO-8601 UTC strings compare lexicographically.
    Returns the number of rows updated.
    """
    has_runs = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'"
    ).fetchone()
    if has_runs is None:
        return 0
    cutoff = _stale_cutoff_iso(now)
    cur = conn.execute(
        """
        UPDATE runs
           SET status = 'stale', updated_at = ?
         WHERE status = 'running'
           AND COALESCE(updated_at, started_at) < ?
        """,
        (iso_now_ms(), cutoff),
    )
    return cur.rowcount if cur.rowcount is not None and cur.rowcount > 0 else 0


def ensure_initialized(db_path: Path | str | None = None) -> None:
    """Initialize the DB lazily if it does not yet exist, or migrate it.

    Allows writer scripts to be safe even if /sdd-full has not run init_console_db
    explicitly. Idempotent: no-op if the DB is already at SCHEMA_VERSION.

    Serialisation (audit 2026-11-07) : the fresh-schema load runs under one
    ``BEGIN IMMEDIATE`` (schema + ``schema_version`` v1 in the same TXN) and
    every migration under its own ; concurrent initialisers block on the
    SQLite write lock (``busy_timeout`` 30 s + retry) and re-check the
    version inside the transaction, so replay is a no-op.

    Cases:
    - ``current is None`` → fresh DB, load full ``console_db_schema.sql`` (v1).
    - ``current < SCHEMA_VERSION`` → apply pending migrations from
      ``sdd_lib/migrations/`` (see README.md there).
    - ``current == SCHEMA_VERSION`` → no-op (apart from the stale-run sweep).
    - ``current > SCHEMA_VERSION`` → DB ahead of framework (likely another
      checkout), emit WARN to stderr and continue (read-side will still work
      for known tables).
    """
    with connect(db_path) as conn:
        v = current_schema_version(conn)
        if v is None:
            _begin_immediate(conn)
            try:
                # Re-check inside the write lock : a concurrent initialiser
                # may have loaded the schema while we waited.
                v = current_schema_version(conn)
                if v is None:
                    _execute_script_guarded(conn, load_schema_sql())
                    conn.execute(
                        "INSERT OR IGNORE INTO schema_version(version, applied_at) "
                        "VALUES(?, ?)",
                        (BASE_SCHEMA_VERSION, iso_now_ms()),
                    )
                    v = BASE_SCHEMA_VERSION
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        if v > SCHEMA_VERSION:
            print(
                f"WARN sdd_lib.console_db: DB schema v{v} ahead of framework "
                f"SCHEMA_VERSION={SCHEMA_VERSION} — no migration applied",
                file=sys.stderr,
            )
            return
        if v < SCHEMA_VERSION:
            applied = apply_pending_migrations(conn)
            if applied:
                print(
                    f"sdd_lib.console_db: applied migrations {applied} "
                    f"(v{v} → v{SCHEMA_VERSION})",
                    file=sys.stderr,
                )
        # Light data migration — idempotent, cheap (indexed-ish scan on a
        # small table). Runs on every init so abandoned runs never stay
        # ``running`` forever (audit 2026-11-07).
        stale = mark_stale_runs(conn)
        if stale:
            print(
                f"sdd_lib.console_db: {stale} run(s) sans activité depuis "
                f"> {STALE_RUN_AFTER_SECONDS // 3600} h marqué(s) 'stale'",
                file=sys.stderr,
            )


def _jdumps(obj: Any) -> str | None:
    """JSON-serialize ``obj`` to a compact string, or ``None`` when ``obj`` is None.

    Semi-private helper shared across runs.py + qa.py — exposed via the
    sub-package `__init__` to keep the 8 cross-domain callers happy
    (gates, runs, auditor_runs, qa_api_tests, validation_reports).
    """
    if obj is None:
        return None
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def ensure_feat_row(
    conn: sqlite3.Connection,
    *,
    feat_n: int,
    name: str | None = None,
    file_path: str | None = None,
) -> None:
    """Ensure a minimal `feats` row exists (FK target for qa_* tables).

    Used by writers that arrive before a full metadata ingest has run. Idempotent:
    leaves an existing row untouched. Caller is responsible for richer metadata
    via a dedicated ingest path (see future ingest_metadata.py)."""
    conn.execute(
        """
        INSERT OR IGNORE INTO feats(feat_n, name, file_path, ingested_at)
        VALUES(?, ?, ?, ?)
        """,
        (feat_n, name or f"feat-{feat_n}", file_path or "", iso_now_ms()),
    )


def ensure_us_row(
    conn: sqlite3.Connection,
    *,
    us_id: str,
    feat_n: int,
    n: int | None = None,
    m: int | None = None,
    name: str | None = None,
    file_path: str | None = None,
) -> None:
    """Ensure a minimal `us` row exists. Idempotent INSERT OR IGNORE."""
    if n is None or m is None:
        # parse "n-m-..." or "n-m"
        parts = us_id.split("-", 2)
        if len(parts) >= 2:
            try:
                n = int(parts[0]) if n is None else n
                m = int(parts[1]) if m is None else m
            except ValueError:
                n = n or 0
                m = m or 0
    ensure_feat_row(conn, feat_n=feat_n)
    conn.execute(
        """
        INSERT OR IGNORE INTO us(us_id, feat_n, n, m, name, file_path, ingested_at)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (us_id, feat_n, n or 0, m or 0, name or us_id, file_path or "", iso_now_ms()),
    )
