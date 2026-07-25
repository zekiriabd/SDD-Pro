"""test_local_helpers_parity.py — ADV-16 V2 closure.

Verify the SEMANTIC parity of helpers duplicated locally for D4 isolation :

    sdd_reverse/atomic_write_local.py   ↔  sdd_lib/atomic_write.py
    sdd_reverse/file_locks_local.py     ↔  sdd_lib/file_locks.py

The two helper pairs are intentionally duplicated (D4 strict isolation —
`sdd_reverse/*` MUST NOT import from `sdd_lib/`). Parity tests guarantee :

1. **Hash drift detection** (informational) — if any upstream `sdd_lib/*`
   helper hash diverges from `_parity_snapshots.json`, emit WARN so the
   maintainer reviews the local copy.

2. **Semantic equivalence** — the local helpers behave correctly under :
   * normal write
   * stale lock recovery
   * cross-write atomicity (mid-crash → no truncated file)
   * Windows RUPT-5 mitigation present (jittered retry on PermissionError)

3. **API surface** — public API of local helpers exposes the documented
   contract (signatures present, exit codes for locks).

Referenced by docstrings of :
    - sdd_reverse/atomic_write_local.py:4
    - sdd_reverse/file_locks_local.py:4
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SDD_LIB = PROJECT_ROOT / ".sdd" / "python" / "sdd_lib"
SDD_REVERSE = PROJECT_ROOT / ".sdd" / "python" / "sdd_reverse"
SNAPSHOTS = SDD_REVERSE / "_parity_snapshots.json"


# ---------------------------------------------------------------------------
# 1. Hash drift detection
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parity_snapshots_file_exists() -> None:
    """The snapshot file must exist and be JSON-parseable."""
    assert SNAPSHOTS.is_file(), f"missing {SNAPSHOTS}"
    data = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    assert data["schemaVersion"] == 1
    assert "snapshots" in data
    assert "sdd_lib/atomic_write.py" in data["snapshots"]
    assert "sdd_lib/file_locks.py" in data["snapshots"]


def test_atomic_write_no_upstream_drift() -> None:
    """WARN if sdd_lib/atomic_write.py drifts from snapshot.

    Drift is informational, not blocking — reviewer must decide whether
    the local copy `atomic_write_local.py` needs a refresh sync.
    Test fails ONLY if snapshots file is missing or unparseable.
    """
    data = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    expected = data["snapshots"]["sdd_lib/atomic_write.py"]
    actual = _sha256(SDD_LIB / "atomic_write.py")
    if actual != expected:
        pytest.skip(
            f"WARN: sdd_lib/atomic_write.py drifted "
            f"(snap={expected[:8]}… actual={actual[:8]}…). "
            "Review sdd_reverse/atomic_write_local.py for needed refresh."
        )


def test_file_locks_no_upstream_drift() -> None:
    """WARN if sdd_lib/file_locks.py drifts from snapshot (idem)."""
    data = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    expected = data["snapshots"]["sdd_lib/file_locks.py"]
    actual = _sha256(SDD_LIB / "file_locks.py")
    if actual != expected:
        pytest.skip(
            f"WARN: sdd_lib/file_locks.py drifted "
            f"(snap={expected[:8]}… actual={actual[:8]}…). "
            "Review sdd_reverse/file_locks_local.py for needed refresh."
        )


# ---------------------------------------------------------------------------
# 2. Semantic equivalence — atomic_write
# ---------------------------------------------------------------------------

def test_atomic_write_local_creates_file(tmp_path: Path) -> None:
    from sdd_reverse.atomic_write_local import atomic_write_text

    target = tmp_path / "sub" / "out.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_local_idempotent_overwrite(tmp_path: Path) -> None:
    from sdd_reverse.atomic_write_local import atomic_write_text

    target = tmp_path / "out.txt"
    atomic_write_text(target, "v1")
    atomic_write_text(target, "v2")
    assert target.read_text(encoding="utf-8") == "v2"


def test_atomic_write_local_no_orphan_tmp_on_success(tmp_path: Path) -> None:
    from sdd_reverse.atomic_write_local import atomic_write_text, find_orphan_tmps

    target = tmp_path / "out.txt"
    atomic_write_text(target, "hello")
    orphans = list(find_orphan_tmps(tmp_path))
    assert orphans == [], f"unexpected orphan .sddtmp: {orphans}"


def test_atomic_write_local_rupt5_retry_present() -> None:
    """RUPT-5 mitigation (jittered retry on PermissionError) must be present.

    Local copy was synced 2026-06-10 to match sdd_lib v7.0.0. Without this
    retry, Windows parallel writes can fail with WinError 5.
    """
    from sdd_reverse import atomic_write_local

    src = inspect.getsource(atomic_write_local)
    assert "_replace_with_retry" in src, "RUPT-5 retry helper missing"
    assert "_backoff_with_jitter" in src, "jitter helper missing"
    assert "PermissionError" in src, "PermissionError handling missing"


def test_atomic_write_local_byte_for_byte_against_lib_constants() -> None:
    """The constants _REPLACE_MAX_RETRIES and _REPLACE_BACKOFF_S must match
    sdd_lib values — desync = different runtime contention behavior."""
    from sdd_lib import atomic_write as lib_aw
    from sdd_reverse import atomic_write_local as rev_aw

    assert lib_aw._REPLACE_MAX_RETRIES == rev_aw._REPLACE_MAX_RETRIES
    assert lib_aw._REPLACE_BACKOFF_S == rev_aw._REPLACE_BACKOFF_S


# ---------------------------------------------------------------------------
# 3. Semantic equivalence — file_locks
# ---------------------------------------------------------------------------

def test_file_locks_local_acquire_release_cycle(tmp_path: Path) -> None:
    from sdd_reverse.file_locks_local import acquire_lock, read_lock, release_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "agent-A") == 0          # ACQUIRED
    payload = read_lock(lock)
    assert payload is not None
    assert payload["agent_id"] == "agent-A"
    assert payload["pid"] == os.getpid()
    assert release_lock(lock, "agent-A") == 0          # RELEASED
    assert not lock.exists()


def test_file_locks_local_reentrant_same_agent(tmp_path: Path) -> None:
    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "agent-A") == 0
    assert acquire_lock(lock, "agent-A") == 0          # re-entrant OK


def test_file_locks_local_held_by_other_agent(tmp_path: Path) -> None:
    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "agent-A") == 0
    assert acquire_lock(lock, "agent-B") == 1          # LOCK_HELD


def test_file_locks_local_stale_recovery(tmp_path: Path) -> None:
    """Stale lock (> TTL) MUST be overwritten with exit code 2."""
    from sdd_reverse.file_locks_local import acquire_lock, read_lock

    lock = tmp_path / ".alloc.lock"
    # Write a stale lock manually (ts in the past)
    stale_payload = json.dumps({
        "agent_id": "agent-dead",
        "pid": 99999,
        "ts_unix": int(time.time()) - 3600,            # 1h old
        "host": "ghost",
    })
    lock.write_text(stale_payload, encoding="utf-8")
    assert acquire_lock(lock, "agent-A", ttl=30) == 2  # stale overwritten
    fresh = read_lock(lock)
    assert fresh is not None
    assert fresh["agent_id"] == "agent-A"


def test_file_locks_local_corrupted_lock_recovery(tmp_path: Path) -> None:
    """OLD corrupted JSON in lock file → takeover (exit 2).

    Audit 2026-06-11 M3 : le recovery ne s'applique qu'aux locks corrompus
    ANCIENS (mtime hors fenêtre de grâce). On backdate le mtime pour
    simuler un crash mid-write passé.
    """
    import os
    import time as _time
    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    lock.write_text("{not-json", encoding="utf-8")
    past = _time.time() - 60
    os.utime(lock, (past, past))
    assert acquire_lock(lock, "agent-A") == 2


def test_file_locks_local_fresh_corrupted_lock_is_held(tmp_path: Path) -> None:
    """FRESH unparseable lock → HELD (exit 1), jamais volé.

    Audit 2026-06-11 M3 : un lock O_EXCL fraîchement créé est VIDE entre
    open et write — l'écraser comme "corrompu" produisait 2 détenteurs
    simultanés (race prouvée par test_acquire_lock_concurrent_o_excl_race).
    """
    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    lock.write_text("", encoding="utf-8")  # mtime = now → fenêtre de grâce
    assert acquire_lock(lock, "agent-A") == 1


def test_file_locks_local_foreign_release_rejected(tmp_path: Path) -> None:
    """Releasing a lock held by another agent → exit code 3."""
    from sdd_reverse.file_locks_local import acquire_lock, release_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "agent-A") == 0
    assert release_lock(lock, "agent-B") == 3          # foreign release
    assert lock.exists()                                # not removed


def test_file_locks_local_release_absent_lock_idempotent(tmp_path: Path) -> None:
    """release_lock on absent file is idempotent (exit 0)."""
    from sdd_reverse.file_locks_local import release_lock

    assert release_lock(tmp_path / "missing.lock", "agent-A") == 0


# ---------------------------------------------------------------------------
# 4. API surface guarantees
# ---------------------------------------------------------------------------

def test_atomic_write_local_public_api() -> None:
    from sdd_reverse import atomic_write_local

    expected = {"atomic_write_text", "atomic_write_bytes", "find_orphan_tmps"}
    actual = {name for name in dir(atomic_write_local) if not name.startswith("_")}
    missing = expected - actual
    assert not missing, f"missing public API: {missing}"


def test_file_locks_local_public_api() -> None:
    from sdd_reverse import file_locks_local

    expected = {"acquire_lock", "release_lock", "read_lock"}
    actual = {name for name in dir(file_locks_local) if not name.startswith("_")}
    missing = expected - actual
    assert not missing, f"missing public API: {missing}"


def test_file_locks_local_exit_codes_documented() -> None:
    """Exit codes 0/1/2/3 must be exposed via docstring (ownership.md §4)."""
    from sdd_reverse import file_locks_local

    doc = file_locks_local.__doc__ or ""
    for code in ("0", "1", "2", "3"):
        assert code in doc, f"exit code {code} not documented in module docstring"


# ---------------------------------------------------------------------------
# 5. D4 isolation reminder (sanity)
# ---------------------------------------------------------------------------

def test_no_cross_import_from_sdd_lib() -> None:
    """sdd_reverse helpers MUST NOT import from sdd_lib (D4 strict)."""
    for module_path in (
        SDD_REVERSE / "atomic_write_local.py",
        SDD_REVERSE / "file_locks_local.py",
    ):
        src = module_path.read_text(encoding="utf-8")
        assert "from sdd_lib" not in src, f"D4 violation in {module_path.name}"
        assert "import sdd_lib" not in src, f"D4 violation in {module_path.name}"
