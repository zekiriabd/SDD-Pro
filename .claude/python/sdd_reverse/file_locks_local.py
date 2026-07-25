"""file_locks_local.py — Cross-platform file lock (ADV-2 closure).

INDEPENDENT lock implementation for the reverse module (D4 strict isolation —
sdd_reverse/* must never depend on the sdd_lib package). This is NOT a
byte-for-byte copy of the sdd_lib file_locks helper : the contracts
DELIBERATELY diverge. This module exposes a JSON-payload lock
({agent_id, pid, ts_unix, host}), a 30s TTL, opportunistic psutil liveness,
and the acquire_lock/release_lock/read_lock exit-code API below. The sdd_lib
file_locks helper uses a different surface (try_create_exclusive / tuple
returns) and is not reproduced here.

Semantic tests (acquire/release cycle, stale recovery, foreign release, etc.)
live in tests/test_local_helpers_parity.py. The "parity" tracked for this file
is drift-AWARENESS only (informational hash watch in _parity_snapshots.json),
NOT API equivalence — see that file's `_note`.

Public API:
    acquire_lock(lock_path, agent_id, ttl=30) -> int  # exit code
    release_lock(lock_path, agent_id) -> int          # exit code
    read_lock(lock_path) -> dict | None

Exit codes (mirror ownership.md §4 / build-and-loop.md §2):
    0  : ACQUIRED (creation or re-entrant same agent) | RELEASED
    1  : LOCK_HELD by other agent
    2  : stale lock (>ttl seconds) OR corrupted lock OVERWRITTEN — continue
    3  : I/O error (bad path, permission denied, foreign release)

ADV-10 mitigations:
    - psutil is OPTIONAL — if missing, fallback to TTL-only (no hard dep)
    - Windows PID recycling: TTL stays the authority, pid is opportunistic
    - host field included to short-circuit cross-machine confusion
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

from sdd_reverse.atomic_write_local import atomic_write_text

DEFAULT_TTL_SECONDS = 30

# Fenêtre de grâce avant de traiter un lock illisible comme « corrompu »
# (audit 2026-06-11 M3) : un lock O_EXCL fraîchement créé est VIDE pendant
# quelques ms (entre open et write). 2 s couvre largement ce write + les
# pauses de scheduling, sans retarder significativement un vrai recovery.
_CORRUPT_GRACE_SECONDS = 2.0


def _takeover(p: Path, payload: str) -> int:
    """Remplace un lock existant (stale TTL / pid mort / corrompu ancien).

    Audit 2026-06-11 (race stale-takeover) : l'ancien chemin écrasait via
    atomic_write_text → N prétendants détectant le même lock stale
    retournaient TOUS exit 2 (N « détenteurs »). Ici : unlink + re-création
    O_EXCL — un seul prétendant gagne, les autres reçoivent 1 (LOCK_HELD).
    Fenêtre résiduelle théorique (unlink d'un lock recréé entre read et
    unlink) bornée par la grâce mtime du caller — acceptable vs l'ancien
    écrasement systématique.
    """
    try:
        p.unlink()
    except FileNotFoundError:
        pass  # un autre prétendant a déjà unlinked — on tente la re-création
    except OSError:
        return 3
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return 1  # un autre prétendant a gagné le takeover
    except OSError:
        return 3
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return 2

# psutil is optional (ADV-10) — keep dependency soft.
try:
    import psutil  # type: ignore[import-not-found]

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _host() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def _is_pid_alive(pid: int) -> bool | None:
    """Return True/False if known, None if cannot check (no psutil)."""
    if not _HAS_PSUTIL:
        return None
    try:
        return psutil.pid_exists(pid)  # type: ignore[no-any-return]
    except Exception:
        return None


def read_lock(lock_path: str | Path) -> dict[str, Any] | None:
    """Read lock content; return None if absent or unreadable."""
    p = Path(lock_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def acquire_lock(
    lock_path: str | Path,
    agent_id: str,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> int:
    """Try to acquire `lock_path` for `agent_id`.

    Returns:
        0 : ACQUIRED (creation or re-entrant same agent)
        1 : LOCK_HELD by another agent (< TTL, OR pid alive on same host)
        2 : stale/corrupted lock overwritten — caller can continue
        3 : I/O error
    """
    p = Path(lock_path)
    now = int(time.time())
    pid = os.getpid()
    host = _host()
    payload = json.dumps(
        {"agent_id": agent_id, "pid": pid, "ts_unix": now, "host": host},
        ensure_ascii=False,
    )

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 3

    # Fast path — atomic O_CREAT|O_EXCL creation (audit 2026-06-10 C5 : the
    # previous read-then-write acquisition was a TOCTOU race — two processes
    # could both observe "no lock" and both believe they acquired it. O_EXCL
    # restores the exclusion guarantee of the original sdd_lib/file_locks.py).
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        pass  # lock exists — fall through to the decision tree below
    except OSError:
        return 3
    else:
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return 0

    existing = read_lock(p)
    if existing is None:
        # Present but unparseable. Two very different cases (audit 2026-06-11 M3) :
        # (a) un GAGNANT entre son os.open(O_EXCL) et son os.write — le fichier
        #     est frais et vide ; l'écraser ici = 2 détenteurs simultanés
        #     (race prouvée par test_acquire_lock_concurrent_o_excl_race flaky) ;
        # (b) crash mid-write ancien — lock réellement corrompu, recovery légitime.
        # Discrimination par mtime : dans la fenêtre de grâce → HELD, pas de vol.
        try:
            age_s = time.time() - p.stat().st_mtime
        except OSError:
            return 1  # lock disparu/instatable entre-temps — ne jamais voler, retry caller
        if age_s < _CORRUPT_GRACE_SECONDS:
            return 1
        return _takeover(p, payload)

    # Existing lock found — decide.
    existing_agent = existing.get("agent_id", "")
    existing_ts = int(existing.get("ts_unix", 0))
    existing_pid = int(existing.get("pid", 0))
    existing_host = existing.get("host", "")
    age = now - existing_ts

    # Re-entrant : same agent_id wins.
    if existing_agent == agent_id:
        try:
            atomic_write_text(p, payload)  # refresh ts
            return 0
        except OSError:
            return 3

    # Stale by TTL : takeover exclusif (un seul prétendant gagne).
    if age >= ttl:
        return _takeover(p, payload)

    # Within TTL but pid check : only if same host AND psutil available.
    if existing_host == host:
        alive = _is_pid_alive(existing_pid)
        if alive is False:
            # Pid dead on same host — takeover even before TTL.
            return _takeover(p, payload)
        # alive is True OR None (no psutil) → fall through to LOCK_HELD.

    return 1


def release_lock(lock_path: str | Path, agent_id: str) -> int:
    """Release lock if held by `agent_id`.

    Returns:
        0 : RELEASED (or already absent — idempotent)
        3 : foreign release attempt OR I/O error
    """
    p = Path(lock_path)
    existing = read_lock(p)
    if existing is None:
        return 0 if not p.exists() else 3
    if existing.get("agent_id") != agent_id:
        return 3
    try:
        p.unlink()
        return 0
    except OSError:
        return 3
