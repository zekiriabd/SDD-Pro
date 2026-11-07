"""Tests for sdd_scripts.acquire_libname_lock — concurrency primitives."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
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
    # Audit 2026-11-07 : --lib-path must live under the allowed lock root
    # (workspace/src by default) — tests use the system temp dir as root.
    env = dict(os.environ, SDD_LIBNAME_LOCK_ROOT=str(Path(tempfile.gettempdir()).resolve()))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
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
            lock = locks_dir / "BebeDto.lock"
            lock.write_text("", encoding="ascii")
            # Audit 2026-11-07 : an EMPTY lock younger than the 2 s grace is a
            # winner caught between O_EXCL create and write — age it first.
            old = time.time() - 60
            os.utime(lock, (old, old))
            code, out = run_acquire(lib_path, "BebeDto", "agent-B")
        self.assertEqual(code, 2, out)
        self.assertEqual(out["status"], "ACQUIRED-STALE-OVERRIDE")

    def test_fresh_empty_lock_is_not_stolen(self):
        """Empty lock < grace window -> LOCK-HELD (no theft of a lock in creation)."""
        with TemporaryDirectory() as td:
            lib_path = Path(td)
            locks_dir = lib_path / ".locks"
            locks_dir.mkdir()
            (locks_dir / "BebeDto.lock").write_text("", encoding="ascii")
            code, out = run_acquire(lib_path, "BebeDto", "agent-B")
        self.assertEqual(code, 1, out)
        self.assertEqual(out["status"], "LOCK-HELD")


class TestArgumentValidation(unittest.TestCase):
    def test_entity_traversal_rejected(self):
        with TemporaryDirectory() as td:
            code, out = run_acquire(Path(td), "../../x", "agent-A")
        self.assertEqual(code, 3, out)
        self.assertEqual(out["error_class"], "[LIBNAME_LOCK_INVALID_ARG]")

    def test_agent_id_with_separator_rejected(self):
        with TemporaryDirectory() as td:
            code, out = run_acquire(Path(td), "BebeDto", "a:b")
        self.assertEqual(code, 3, out)

    def test_lib_path_outside_root_rejected(self):
        # Root = system temp ; the repo itself is outside it.
        code, out = run_acquire(Path(__file__).resolve().parent, "BebeDto", "agent-A")
        self.assertEqual(code, 3, out)
        self.assertEqual(out["error_class"], "[LIBNAME_LOCK_INVALID_ARG]")
        self.assertIn("outside the allowed lock root", out["message"])


if __name__ == "__main__":
    unittest.main()
