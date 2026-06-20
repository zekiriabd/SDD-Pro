"""Tests for sdd_scripts.acquire_libname_lock — concurrency primitives."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT = Path(__file__).resolve().parent.parent / "sdd_scripts" / "acquire_libname_lock.py"


def run_acquire(lib_path: Path, entity: str, agent_id: str, *,
                release: bool = False, stale_threshold: int | None = None) -> tuple[int, dict]:
    cmd = [
        sys.executable, str(SCRIPT),
        "--lib-path", str(lib_path),
        "--entity", entity,
        "--agent-id", agent_id,
    ]
    if release:
        cmd.append("--release")
    if stale_threshold is not None:
        cmd.extend(["--stale-threshold-seconds", str(stale_threshold)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        payload = {"_raw_stdout": proc.stdout, "_raw_stderr": proc.stderr}
    return proc.returncode, payload


class TestAcquireRelease(unittest.TestCase):
    def test_acquire_creates_lock_file(self):
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            code, out = run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "ACQUIRED")

    def test_re_entrant_same_agent_succeeds(self):
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
            code, out = run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "RE-ENTRANT")

    def test_other_agent_blocked(self):
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
            code, out = run_acquire(lib_path, "BebeDto", "dev-frontend-1-2")
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "LOCK-HELD")
        self.assertEqual(out["error_class"], "[LIBNAME_LOCK_HELD]")
        self.assertEqual(out["held_by"], "dev-backend-1-2")

    def test_release_by_owner(self):
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
            code, out = run_acquire(lib_path, "BebeDto", "dev-backend-1-2", release=True)
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "RELEASED")

    def test_release_by_non_owner_errors(self):
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
            code, out = run_acquire(lib_path, "BebeDto", "dev-frontend-1-2", release=True)
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "ERROR")

    def test_release_when_no_lock_is_idempotent(self):
        with TemporaryDirectory() as td:
            code, out = run_acquire(Path(td), "BebeDto", "dev-backend-1-2", release=True)
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "NO-LOCK")

    def test_acquire_after_release_succeeds(self):
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            run_acquire(lib_path, "BebeDto", "dev-backend-1-2")
            run_acquire(lib_path, "BebeDto", "dev-backend-1-2", release=True)
            code, out = run_acquire(lib_path, "BebeDto", "dev-frontend-1-2")
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "ACQUIRED")

    def test_invalid_libpath_errors(self):
        code, out = run_acquire(Path("/nonexistent/path"), "BebeDto", "dev-backend-1-2")
        self.assertEqual(code, 3)
        self.assertEqual(out["status"], "ERROR")


class TestStaleRecovery(unittest.TestCase):
    def test_old_lock_is_overridden(self):
        """Lock with ts older than threshold -> ACQUIRED-STALE-OVERRIDE (exit 2)."""
        import time
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            locks_dir = lib_path / ".locks"
            locks_dir.mkdir()
            old_ts = int(time.time()) - 10000
            (locks_dir / "BebeDto.lock").write_text(f"agent-A:{old_ts}", encoding="ascii")
            code, out = run_acquire(lib_path, "BebeDto", "agent-B")
        self.assertEqual(code, 2, out)
        self.assertEqual(out["status"], "ACQUIRED-STALE-OVERRIDE")
        self.assertEqual(out["previous_owner"], "agent-A")

    def test_corrupt_lock_is_overridden(self):
        """Unreadable/malformed lock -> ACQUIRED-STALE-OVERRIDE."""
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            locks_dir = lib_path / ".locks"
            locks_dir.mkdir()
            (locks_dir / "BebeDto.lock").write_text("", encoding="ascii")
            code, out = run_acquire(lib_path, "BebeDto", "agent-B")
        self.assertEqual(code, 2, out)
        self.assertEqual(out["status"], "ACQUIRED-STALE-OVERRIDE")


if __name__ == "__main__":
    unittest.main()
