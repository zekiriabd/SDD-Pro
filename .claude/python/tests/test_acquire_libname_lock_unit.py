"""Unit tests for acquire_libname_lock.py (direct import).

Covers the full state machine of the LibName lock primitive:
acquire / re-entrant / lock-held / stale-override / release.
Companion to the subprocess test_acquire_libname_lock.py.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import acquire_libname_lock as alm  # noqa: E402


@pytest.fixture()
def lib_path(tmp_path):
    p = tmp_path / "Shared"
    p.mkdir()
    return p


def _run(monkeypatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["acquire_libname_lock.py"] + args)
    return alm.main()


def _payload(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip())


# ---------- ERROR — invalid path ----------


def test_lib_path_missing_returns_3(monkeypatch, capsys, tmp_path):
    rc = _run(monkeypatch, [
        "--lib-path", str(tmp_path / "does-not-exist"),
        "--entity", "Foo", "--agent-id", "agent-1",
    ])
    assert rc == 3
    p = _payload(capsys)
    assert p["status"] == "ERROR"
    assert "LibPath not found" in p["message"]


# ---------- ACQUIRE ----------


def test_acquire_creates_lock_file(monkeypatch, capsys, lib_path):
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path),
        "--entity", "Foo", "--agent-id", "dev-backend-1-2",
    ])
    assert rc == 0
    p = _payload(capsys)
    assert p["status"] == "ACQUIRED"
    assert p["entity"] == "Foo"
    assert (lib_path / ".locks" / "Foo.lock").is_file()


def test_acquire_reentrant_same_agent_returns_0(monkeypatch, capsys, lib_path):
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1"])
    capsys.readouterr()
    rc = _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1"])
    assert rc == 0
    p = _payload(capsys)
    assert p["status"] == "RE-ENTRANT"


def test_acquire_held_by_other_agent_returns_1(monkeypatch, capsys, lib_path):
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1"])
    capsys.readouterr()
    rc = _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A2"])
    assert rc == 1
    p = _payload(capsys)
    assert p["status"] == "LOCK-HELD"
    assert p["held_by"] == "A1"
    assert p["error_class"] == "[LIBNAME_LOCK_HELD]"


def test_acquire_stale_lock_overridden_returns_2(monkeypatch, capsys, lib_path):
    # Manually craft a stale lock (timestamp 1 hour ago)
    locks = lib_path / ".locks"
    locks.mkdir()
    stale_ts = int(time.time()) - 3600
    (locks / "Foo.lock").write_text(f"old-agent:{stale_ts}", encoding="utf-8")
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "new-agent",
        "--stale-threshold-seconds", "1800",
    ])
    assert rc == 2
    p = _payload(capsys)
    assert p["status"] == "ACQUIRED-STALE-OVERRIDE"
    assert p["previous_owner"] == "old-agent"


def test_acquire_garbled_lock_treated_as_lock_held(monkeypatch, capsys, lib_path):
    """Garbled lock (parseable as `owner:no-ts`) keeps the lock as held — only
    explicit stale-via-timestamp triggers override. Documents current behavior."""
    locks = lib_path / ".locks"
    locks.mkdir()
    (locks / "Foo.lock").write_text("garbage with no colon", encoding="utf-8")
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "new-agent",
    ])
    # age = 0 (no timestamp parsed) < threshold => LOCK-HELD
    assert rc == 1
    p = _payload(capsys)
    assert p["status"] == "LOCK-HELD"


def test_acquire_fresh_lock_not_stale(monkeypatch, capsys, lib_path):
    """A lock held by another agent for < threshold should NOT be overridden."""
    locks = lib_path / ".locks"
    locks.mkdir()
    fresh_ts = int(time.time())
    (locks / "Bar.lock").write_text(f"other:{fresh_ts}", encoding="utf-8")
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Bar", "--agent-id", "me",
        "--stale-threshold-seconds", "1800",
    ])
    assert rc == 1
    p = _payload(capsys)
    assert p["status"] == "LOCK-HELD"


# ---------- RELEASE ----------


def test_release_when_no_lock_returns_0(monkeypatch, capsys, lib_path):
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1",
        "--release",
    ])
    assert rc == 0
    p = _payload(capsys)
    assert p["status"] == "NO-LOCK"


def test_release_by_owner_succeeds(monkeypatch, capsys, lib_path):
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1"])
    capsys.readouterr()
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1",
        "--release",
    ])
    assert rc == 0
    p = _payload(capsys)
    assert p["status"] == "RELEASED"
    assert not (lib_path / ".locks" / "Foo.lock").exists()


def test_release_by_non_owner_returns_3(monkeypatch, capsys, lib_path):
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "owner"])
    capsys.readouterr()
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "intruder",
        "--release",
    ])
    assert rc == 3
    p = _payload(capsys)
    assert p["status"] == "ERROR"
    assert p["owner"] == "owner"


def test_release_idempotent_double_release(monkeypatch, capsys, lib_path):
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1"])
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1", "--release"])
    capsys.readouterr()
    rc = _run(monkeypatch, [
        "--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1", "--release",
    ])
    assert rc == 0
    p = _payload(capsys)
    assert p["status"] == "NO-LOCK"


def test_acquire_after_release_works(monkeypatch, capsys, lib_path):
    """Acquire → release → acquire should leave the lock cleanly held by the new agent."""
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1"])
    _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A1", "--release"])
    capsys.readouterr()
    rc = _run(monkeypatch, ["--lib-path", str(lib_path), "--entity", "Foo", "--agent-id", "A2"])
    assert rc == 0
    p = _payload(capsys)
    assert p["status"] == "ACQUIRED"
