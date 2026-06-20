"""Tests for sdd_lib.console_db — SSoT SQLite layer (v6.10+).

Coverage (introduced in v7.0.0 — was missing despite SSoT status):
- ensure_initialized: fresh init, idempotent re-init
- schema_version table presence and content
- Migration infrastructure (apply_pending_migrations):
    * No-op when current == SCHEMA_VERSION
    * Picks up files matching NNNN_slug.sql convention
    * Skips files with malformed names
    * Skips files targeting versions > SCHEMA_VERSION (future)
    * Applies in ascending order
    * Records each applied version in schema_version
- connect_ro: raises FileNotFoundError on absent DB, succeeds after init
- WAL pragma applied on connect()
- Concurrent writers (threaded): basic non-corruption smoke
"""
from __future__ import annotations

import sys
import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import console_db  # noqa: E402
from sdd_lib.console_db import (  # noqa: E402
    SCHEMA_VERSION,
    apply_pending_migrations,
    connect,
    connect_ro,
    current_schema_version,
    ensure_initialized,
    insert_token_usage,
)


def _fake_repo(tmp: str) -> Path:
    """Create a minimal repo layout with .claude/ so repo_root() resolves."""
    root = Path(tmp)
    (root / ".claude").mkdir()
    return root


class TestEnsureInitialized(unittest.TestCase):
    def test_fresh_init_creates_schema_at_current_version(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    self.assertEqual(current_schema_version(conn), SCHEMA_VERSION)

    def test_idempotent_no_duplicate_rows(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                ensure_initialized()
                ensure_initialized()
                with connect() as conn:
                    n = conn.execute(
                        "SELECT COUNT(*) FROM schema_version"
                    ).fetchone()[0]
                    # v7.0.0 : 1 row per version applied (currently v1 base +
                    # v2 migration). Idempotence guarantee : the count must
                    # NOT grow with repeated ensure_initialized() calls,
                    # which would indicate duplicate inserts. Expected value
                    # is SCHEMA_VERSION (= number of applied versions).
                    self.assertEqual(n, SCHEMA_VERSION)

    def test_creates_token_usage_table(self) -> None:
        """Round-trip : insert + read back proves the schema is functional."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    insert_token_usage(
                        conn,
                        agent="dev-backend",
                        model="claude-opus-4-7",
                        feat_n=1,
                        us_id="1-2",
                        input_tokens=1000,
                        output_tokens=200,
                    )
                with connect() as conn:
                    row = conn.execute(
                        "SELECT agent, feat_n, us_id, input_tokens FROM token_usage"
                    ).fetchone()
                    self.assertEqual(row[0], "dev-backend")
                    self.assertEqual(row[1], 1)
                    self.assertEqual(row[2], "1-2")
                    self.assertEqual(row[3], 1000)

    def test_wal_journal_mode(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    self.assertEqual(mode.lower(), "wal")


class TestConnectRo(unittest.TestCase):
    def test_raises_when_db_absent(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                with self.assertRaises(FileNotFoundError):
                    with connect_ro():
                        pass

    def test_succeeds_after_init(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect_ro() as conn:
                    v = current_schema_version(conn)
                    self.assertEqual(v, SCHEMA_VERSION)


class TestApplyPendingMigrations(unittest.TestCase):
    """Verify the migration mechanism without requiring a real future schema.

    We monkeypatch SCHEMA_VERSION + MIGRATIONS_DIR to a temp dir with synthetic
    migration files, then assert ordering, filtering, and recording behavior.
    """

    def test_noop_when_at_current_version(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()
                with connect() as conn:
                    applied = apply_pending_migrations(conn)
                self.assertEqual(applied, [])

    def test_applies_pending_in_order_and_records_versions(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            migrations_tmp = Path(tmp) / "migrations"
            migrations_tmp.mkdir()

            # Write two synthetic migrations
            (migrations_tmp / "0002_add-test-table.sql").write_text(
                "CREATE TABLE test_v2 (id INTEGER PRIMARY KEY);", encoding="utf-8"
            )
            (migrations_tmp / "0003_add-another-table.sql").write_text(
                "CREATE TABLE test_v3 (id INTEGER PRIMARY KEY);", encoding="utf-8"
            )

            with mock.patch.object(console_db.core, "repo_root", return_value=root), \
                 mock.patch.object(console_db.core, "MIGRATIONS_DIR", migrations_tmp), \
                 mock.patch.object(console_db.core, "SCHEMA_VERSION", 3):
                ensure_initialized()  # fresh init at v1 first
                # ensure_initialized() with SCHEMA_VERSION=3 on a fresh DB
                # loads the v1 schema then applies v2 + v3 migrations.
                with connect() as conn:
                    self.assertEqual(current_schema_version(conn), 3)
                    # Both tables created
                    rows = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name IN ('test_v2', 'test_v3') ORDER BY name"
                    ).fetchall()
                    self.assertEqual([r[0] for r in rows], ["test_v2", "test_v3"])
                    # schema_version has rows for v1, v2, v3
                    versions = [
                        r[0] for r in conn.execute(
                            "SELECT version FROM schema_version ORDER BY version"
                        ).fetchall()
                    ]
                    self.assertEqual(versions, [1, 2, 3])

    def test_skips_files_with_malformed_names(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            migrations_tmp = Path(tmp) / "migrations"
            migrations_tmp.mkdir()

            # Malformed: missing 0-pad / underscore / wrong ext
            (migrations_tmp / "2_bad.sql").write_text("--ignored", encoding="utf-8")
            (migrations_tmp / "0002-not-underscored.sql").write_text("--ignored", encoding="utf-8")
            (migrations_tmp / "notamigration.txt").write_text("--ignored", encoding="utf-8")
            # Valid
            (migrations_tmp / "0002_valid.sql").write_text(
                "CREATE TABLE valid (id INTEGER);", encoding="utf-8"
            )

            with mock.patch.object(console_db.core, "repo_root", return_value=root), \
                 mock.patch.object(console_db.core, "MIGRATIONS_DIR", migrations_tmp), \
                 mock.patch.object(console_db.core, "SCHEMA_VERSION", 2):
                ensure_initialized()
                with connect() as conn:
                    self.assertEqual(current_schema_version(conn), 2)
                    self.assertIsNotNone(conn.execute(
                        "SELECT name FROM sqlite_master WHERE name='valid'"
                    ).fetchone())

    def test_skips_files_beyond_schema_version(self) -> None:
        """A migration file targeting v999 must not be applied when SCHEMA_VERSION=2."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            migrations_tmp = Path(tmp) / "migrations"
            migrations_tmp.mkdir()
            (migrations_tmp / "0002_valid.sql").write_text(
                "CREATE TABLE valid (id INTEGER);", encoding="utf-8"
            )
            (migrations_tmp / "0999_future.sql").write_text(
                "CREATE TABLE future (id INTEGER);", encoding="utf-8"
            )

            with mock.patch.object(console_db.core, "repo_root", return_value=root), \
                 mock.patch.object(console_db.core, "MIGRATIONS_DIR", migrations_tmp), \
                 mock.patch.object(console_db.core, "SCHEMA_VERSION", 2):
                ensure_initialized()
                with connect() as conn:
                    self.assertEqual(current_schema_version(conn), 2)
                    # Future table NOT created
                    self.assertIsNone(conn.execute(
                        "SELECT name FROM sqlite_master WHERE name='future'"
                    ).fetchone())

    def test_db_ahead_of_framework_no_migration_no_crash(self) -> None:
        """DB at v99 (simulating future framework) → warn, no migration, no crash.

        v7.0.0 — uses v99 instead of v3 since SCHEMA_VERSION bumped to 3
        (qa_e2e). The principle (DB > framework = warn-not-crash) unchanged."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()  # init at SCHEMA_VERSION (current)
                # Manually bump to v99 (simulating another checkout's future DB)
                with connect() as conn:
                    conn.execute(
                        "INSERT INTO schema_version(version, applied_at) "
                        "VALUES(99, '2030-01-01T00:00:00.000Z')"
                    )

            # Re-call ensure_initialized — should warn DB ahead, not raise
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()  # MUST NOT raise
                with connect() as conn:
                    self.assertEqual(current_schema_version(conn), 99)


class TestConcurrentWriters(unittest.TestCase):
    """WAL mode should tolerate concurrent insert from multiple threads."""

    def test_threaded_inserts_all_persisted(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = _fake_repo(tmp)
            with mock.patch.object(console_db.core, "repo_root", return_value=root):
                ensure_initialized()

                errors: list[Exception] = []
                lock = threading.Lock()

                def worker(i: int) -> None:
                    try:
                        with connect() as conn:
                            insert_token_usage(
                                conn,
                                agent=f"agent-{i}",
                                model="claude-sonnet-4-6",
                                feat_n=i,
                                us_id=f"{i}-1",
                                input_tokens=100 * i,
                                output_tokens=10 * i,
                            )
                    except Exception as e:  # noqa: BLE001
                        with lock:
                            errors.append(e)

                threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 9)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=10)

                self.assertEqual(errors, [], f"unexpected errors: {errors}")
                with connect_ro() as conn:
                    n = conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0]
                    self.assertEqual(n, 8)


class TestConnectRetryConfig(unittest.TestCase):
    """Security audit 2026-06-06 (LOT 8.5) : `database is locked` retry config
    introduit dans console_db/core.py — vérifier que les constantes sont
    correctement définies + busy_timeout bumpé à 30s."""

    def test_busy_timeout_increased_to_30s(self) -> None:
        from sdd_lib.console_db import core
        self.assertEqual(core._BUSY_TIMEOUT_MS, 30000,
                         "busy_timeout doit être 30s (audit 2026-06-06, was 5s)")

    def test_retry_constants_defined(self) -> None:
        from sdd_lib.console_db import core
        self.assertEqual(core._CONNECT_MAX_RETRY, 3,
                         "3 retries on database-locked errors")
        self.assertEqual(len(core._CONNECT_RETRY_BACKOFF), core._CONNECT_MAX_RETRY,
                         "backoff sequence must match retry count")
        backoff = core._CONNECT_RETRY_BACKOFF
        for i in range(1, len(backoff)):
            self.assertGreater(backoff[i], backoff[i-1],
                               f"backoff[{i}] must be > backoff[{i-1}] (exponential)")


if __name__ == "__main__":
    unittest.main()
