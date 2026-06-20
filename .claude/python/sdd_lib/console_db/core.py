"""sdd_lib.console_db.core — connection, pragmas, schema migrations, row helpers.

v7.0.0-alpha (audit CRIT-12, 2026-06-04) — extracted from the previous
monolithic `console_db.py` (912 L → split in 3 thematic sub-modules).

Public API (re-exported via `sdd_lib.console_db.__init__`) :
    SCHEMA_VERSION, BASE_SCHEMA_VERSION, DEFAULT_DB_PATH,
    SCHEMA_SQL_PATH, MIGRATIONS_DIR, AUDITOR_IDS,
    default_db_path, connect, connect_ro,
    load_schema_sql, current_schema_version, apply_pending_migrations,
    ensure_initialized, ensure_feat_row, ensure_us_row,
    _jdumps (semi-private — shared across runs.py + qa.py)
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sdd_lib.paths import iso_now_ms, repo_root

SCHEMA_VERSION = 5  # v7.0.0 : v2 +qa_mutation, v3 +qa_e2e, v4 +auditor_runs (C3 fix), v5 +qa_api_tests.status (audit P3)
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


def default_db_path() -> Path:
    """Resolve workspace/output/db/console.db relative to the repo root."""
    return repo_root() / "workspace" / "output" / "db" / "console.db"


DEFAULT_DB_PATH = default_db_path()


# Security audit 2026-06-06 — `database is locked` observed under parallel
# preflight hooks (≥2 agents spawned simultanément). busy_timeout 5s ne suffit
# pas quand plusieurs writers font INSERT en cascade. Bump à 30s + retry
# explicite avec backoff sur OperationalError pour les rares cas restants.
_BUSY_TIMEOUT_MS = 30000  # 30s — laisse SQLite WAL absorber la contention
_CONNECT_MAX_RETRY = 3
_CONNECT_RETRY_BACKOFF = (0.25, 0.5, 1.0)  # seconds


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


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with pragmas applied, commit on success, rollback on exception.

    Retries up to 3× with exponential backoff on `database is locked`. Final
    failure raises the underlying OperationalError so callers can decide
    (skip telemetry vs abort run).
    """
    import time
    db_path = Path(db_path) if db_path is not None else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(_CONNECT_MAX_RETRY):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            _apply_pragmas(conn)
            yield conn
            conn.commit()
            return  # finally still runs → conn.close()
        except sqlite3.OperationalError as e:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            if "database is locked" not in str(e).lower():
                raise
            if attempt >= _CONNECT_MAX_RETRY - 1:
                raise
            # Retry : close current conn (finally) puis sleep avant nouvelle tentative
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
        # On arrive ici uniquement après OperationalError "locked" et retry restant
        time.sleep(_CONNECT_RETRY_BACKOFF[attempt])


@contextmanager
def connect_ro(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
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
        ``file:///G:/path``, not ``file:G:/path``). Both worked on most
        Python builds but the ad-hoc form is technically malformed per
        RFC 8089 + breaks on some sandboxed builds.
      - On ``OperationalError: unable to open database file`` (typical
        cause : WAL ``-shm``/``-wal`` files held by a concurrent writer on
        Windows, or RO parent directory), retry with ``immutable=1``
        which bypasses the journal entirely (safe for read-only inspection,
        we explicitly forbid writes via PRAGMA query_only ON).
        Critical for ``preflight_cost_cap`` + ``report_token_usage``
        running while ``/sdd-full`` keeps the DB locked.
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
        # Fallback : immutable=1 means SQLite never touches -wal/-shm,
        # which is exactly what we need when the writer holds them.
        # Safety : immutable=1 implies the DB CANNOT change during this
        # connection's lifetime — readers that need fresh data after a
        # writer commit must reconnect, but that's already the case for
        # WAL-on-Windows lock scenarios.
        if "unable to open database file" not in str(e).lower():
            raise
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


def apply_pending_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply all migrations strictly newer than the current schema version.

    Each migration file is executed inside ``executescript()`` (single
    implicit transaction). On success, a ``schema_version`` row is inserted
    with the target version. Forward-only — no rollback, no down-migration.

    Returns the list of applied target versions (empty if none).
    """
    current = current_schema_version(conn) or 0
    applied: list[int] = []
    for target, sql_path in _list_pending_migrations(current):
        sql = sql_path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (target, iso_now_ms()),
        )
        applied.append(target)
    return applied


def ensure_initialized(db_path: Path | str | None = None) -> None:
    """Initialize the DB lazily if it does not yet exist, or migrate it.

    Allows writer scripts to be safe even if /sdd-full has not run init_console_db
    explicitly. Idempotent: no-op if the DB is already at SCHEMA_VERSION.

    Cases:
    - ``current is None`` → fresh DB, load full ``console_db_schema.sql`` (v1).
    - ``current < SCHEMA_VERSION`` → apply pending migrations from
      ``sdd_lib/migrations/`` (see README.md there).
    - ``current == SCHEMA_VERSION`` → no-op.
    - ``current > SCHEMA_VERSION`` → DB ahead of framework (likely another
      checkout), emit WARN to stderr and continue (read-side will still work
      for known tables).
    """
    with connect(db_path) as conn:
        v = current_schema_version(conn)
        if v == SCHEMA_VERSION:
            return
        if v is None:
            # Fresh DB → load full base schema (v=BASE_SCHEMA_VERSION) then
            # fall through to apply any pending migrations up to SCHEMA_VERSION.
            conn.executescript(load_schema_sql())
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
                (BASE_SCHEMA_VERSION, iso_now_ms()),
            )
            v = BASE_SCHEMA_VERSION
            if v == SCHEMA_VERSION:
                return
        if v > SCHEMA_VERSION:
            print(
                f"WARN sdd_lib.console_db: DB schema v{v} ahead of framework "
                f"SCHEMA_VERSION={SCHEMA_VERSION} — no migration applied",
                file=sys.stderr,
            )
            return
        applied = apply_pending_migrations(conn)
        if applied:
            print(
                f"sdd_lib.console_db: applied migrations {applied} "
                f"(v{v} → v{SCHEMA_VERSION})",
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
