"""Tests for sdd_lib.file_locks — atomic O_EXCL lock primitives.

Covers (introduced in v7.0.0 — was missing despite load-bearing role for
parallel dev-backend × dev-frontend invocations on LibName shared models):

- try_create_exclusive: idempotence + atomicity
- read_lock: parse valid / malformed / missing
- overwrite_lock: stale recovery overwrite
- acquire_with_retry: contention serialization, stale TTL recovery,
  retry budget exhaustion, threaded contention
- release: idempotent no-op when absent
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

# Smoke marker (audit CTO 2026-06-07) — file_locks underpins LibName
# parallel write serialization. Lock contention bugs surface only at
# parallelism ≥ 3 (likely silent under unit-test mono-thread). Gated by
# `framework_smoke -m smoke`.
pytestmark = pytest.mark.smoke

from sdd_lib.file_locks import (  # noqa: E402
    acquire_with_retry,
    overwrite_lock,
    read_lock,
    release,
    try_create_exclusive,
)


class TestTryCreateExclusive(unittest.TestCase):
    def test_creates_when_absent(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            self.assertTrue(try_create_exclusive(lock, "agent-A:123"))
            self.assertTrue(lock.is_file())
            self.assertEqual(lock.read_text(encoding="ascii"), "agent-A:123")

    def test_returns_false_when_exists(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            self.assertTrue(try_create_exclusive(lock, "agent-A:1"))
            # 2nd attempt — must NOT overwrite
            self.assertFalse(try_create_exclusive(lock, "agent-B:2"))
            self.assertEqual(lock.read_text(encoding="ascii"), "agent-A:1")


class TestReadLock(unittest.TestCase):
    def test_returns_none_on_missing(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            self.assertIsNone(read_lock(Path(tmp) / "absent.lock"))

    def test_parses_valid_payload(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            lock.write_text("agent-A:1700000000", encoding="ascii")
            result = read_lock(lock)
            self.assertEqual(result, ("agent-A", 1700000000))

    def test_handles_malformed_timestamp(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            lock.write_text("agent-A:notanumber", encoding="ascii")
            result = read_lock(lock)
            self.assertEqual(result, ("agent-A", 0))

    def test_handles_no_separator(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            lock.write_text("just-agent-name", encoding="ascii")
            result = read_lock(lock)
            self.assertEqual(result, ("just-agent-name", 0))


class TestOverwriteLock(unittest.TestCase):
    def test_replaces_content(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            lock.write_text("old:1", encoding="ascii")
            overwrite_lock(lock, "new:2")
            self.assertEqual(lock.read_text(encoding="ascii"), "new:2")


class TestRelease(unittest.TestCase):
    def test_idempotent_on_missing(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            release(Path(tmp) / "absent.lock")  # must not raise

    def test_removes_existing(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            lock.write_text("x", encoding="ascii")
            release(lock)
            self.assertFalse(lock.exists())


class TestAcquireWithRetry(unittest.TestCase):
    def test_acquires_on_fresh_path(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            acquire_with_retry(lock, payload_prefix="test", retry_count=1)
            self.assertTrue(lock.is_file())
            content = lock.read_text(encoding="ascii")
            self.assertTrue(content.startswith("test:"))
            self.assertEqual(content.count(":"), 2)  # test:pid:ts

    def test_raises_lock_held_on_active_contention(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            # Pre-create a FRESH lock (timestamp = now)
            now_ms = int(time.time() * 1000)
            lock.write_text(f"other:99999:{now_ms}", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, r"\[LOCK_HELD\]"):
                acquire_with_retry(
                    lock,
                    payload_prefix="test",
                    ttl_ms=10000,
                    retry_count=2,
                    backoff_ms=10,
                )

    def test_recovers_stale_lock(self) -> None:
        """Stale lock (ts older than ttl_ms) should be unlinked and reacquired."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            # Stale: timestamp 1 hour ago
            stale_ms = int(time.time() * 1000) - 3_600_000
            lock.write_text(f"crashed:99999:{stale_ms}", encoding="ascii")
            acquire_with_retry(
                lock,
                payload_prefix="recovered",
                ttl_ms=5000,
                retry_count=3,
                backoff_ms=10,
            )
            content = lock.read_text(encoding="ascii")
            self.assertTrue(content.startswith("recovered:"))

    def test_threaded_contention_only_one_winner(self) -> None:
        """N threads racing for the same lock → exactly one acquires."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            winners: list[str] = []
            losers: list[str] = []
            lock_pylist = threading.Lock()

            def worker(name: str) -> None:
                try:
                    acquire_with_retry(
                        lock,
                        payload_prefix=name,
                        ttl_ms=60_000,
                        retry_count=1,  # don't retry — first attempt only
                        backoff_ms=1,
                    )
                    with lock_pylist:
                        winners.append(name)
                except RuntimeError:
                    with lock_pylist:
                        losers.append(name)

            threads = [
                threading.Thread(target=worker, args=(f"t{i}",))
                for i in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            # Exactly one thread should have acquired
            self.assertEqual(len(winners), 1,
                             f"expected 1 winner, got {len(winners)}: {winners}")
            self.assertEqual(len(losers), 7,
                             f"expected 7 losers, got {len(losers)}")

    def test_payload_contains_pid(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lock = Path(tmp) / "x.lock"
            acquire_with_retry(lock, payload_prefix="myagent", retry_count=1)
            content = lock.read_text(encoding="ascii")
            parts = content.split(":")
            self.assertEqual(parts[0], "myagent")
            self.assertEqual(int(parts[1]), os.getpid())
            self.assertGreater(int(parts[2]), 0)


if __name__ == "__main__":
    unittest.main()
