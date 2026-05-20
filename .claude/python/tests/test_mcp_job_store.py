"""Unit tests for sdd_mcp.job_store — persistent async job state."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
_PY_ROOT = REPO_ROOT / ".claude" / "python"
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_mcp import job_store  # noqa: E402


def _make_fake_repo(root: Path) -> None:
    (root / ".claude").mkdir(parents=True, exist_ok=True)


class TestJobIdAndPaths(unittest.TestCase):
    def test_new_job_id_is_hex(self) -> None:
        jid = job_store.new_job_id()
        self.assertEqual(len(jid), 12)
        int(jid, 16)  # raises if not hex

    def test_new_job_ids_are_unique(self) -> None:
        ids = {job_store.new_job_id() for _ in range(50)}
        self.assertEqual(len(ids), 50)

    def test_paths_under_workspace(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            sp = job_store.state_path("abc", root)
            self.assertTrue(sp.parent.is_dir())
            self.assertTrue(str(sp).endswith("abc.json"))


class TestWriteReadState(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            state = job_store.JobState(
                job_id="aaaa",
                command="/sdd-full 1",
                feat_number=1,
                status="running",
                pid=42,
                stdout_path=str(root / "out"),
                stderr_path=str(root / "err"),
            )
            job_store.write_state(state, root)
            loaded = job_store.read_state("aaaa", root)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.command, "/sdd-full 1")
            self.assertEqual(loaded.status, "running")
            self.assertEqual(loaded.pid, 42)

    def test_read_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            self.assertIsNone(job_store.read_state("ghost", root))


class TestListJobs(unittest.TestCase):
    def test_list_sorted_desc_by_started_at(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            s1 = job_store.JobState(
                job_id="aaa", command="/sdd-full 1", feat_number=1, status="success",
                started_at="2026-05-17T10:00:00.000Z",
            )
            s2 = job_store.JobState(
                job_id="bbb", command="/sdd-full 2", feat_number=2, status="running",
                started_at="2026-05-17T11:00:00.000Z",
            )
            job_store.write_state(s1, root)
            job_store.write_state(s2, root)
            jobs = job_store.list_jobs(root)
            self.assertEqual([j.job_id for j in jobs], ["bbb", "aaa"])


class TestFinalize(unittest.TestCase):
    def test_finalize_success(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            state = job_store.JobState(
                job_id="x1", command="/sdd-full 1", feat_number=1, status="running",
            )
            job_store.write_state(state, root)
            job_store.finalize(state, exit_code=0, duration_ms=1234, root=root)
            loaded = job_store.read_state("x1", root)
            assert loaded is not None
            self.assertEqual(loaded.status, "success")
            self.assertEqual(loaded.exit_code, 0)
            self.assertEqual(loaded.duration_ms, 1234)
            self.assertIsNotNone(loaded.ended_at)

    def test_finalize_failure(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            state = job_store.JobState(
                job_id="x2", command="/sdd-full 1", feat_number=1, status="running",
            )
            job_store.write_state(state, root)
            job_store.finalize(state, exit_code=2, duration_ms=500, root=root)
            loaded = job_store.read_state("x2", root)
            assert loaded is not None
            self.assertEqual(loaded.status, "failed")
            self.assertEqual(loaded.exit_code, 2)

    def test_finalize_timeout(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            _make_fake_repo(root)
            state = job_store.JobState(
                job_id="x3", command="/sdd-full 1", feat_number=1, status="running",
            )
            job_store.write_state(state, root)
            job_store.finalize(state, exit_code=124, duration_ms=999, timed_out=True, root=root)
            loaded = job_store.read_state("x3", root)
            assert loaded is not None
            self.assertEqual(loaded.status, "timeout")


class TestTailText(unittest.TestCase):
    def test_tail_returns_last_n_bytes(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".log") as f:
            f.write("HEADER\n" + "X" * 200 + "TAIL")
            path = Path(f.name)
        try:
            tail = job_store.tail_text(path, max_bytes=4)
            self.assertEqual(tail, "TAIL")
        finally:
            path.unlink()

    def test_tail_on_missing_file_empty(self) -> None:
        self.assertEqual(job_store.tail_text(Path("/no/such/file.log")), "")


class TestPidLiveness(unittest.TestCase):
    def test_negative_pid_dead(self) -> None:
        self.assertFalse(job_store._is_pid_alive(-1))
        self.assertFalse(job_store._is_pid_alive(0))

    def test_self_pid_alive(self) -> None:
        import os
        self.assertTrue(job_store._is_pid_alive(os.getpid()))


if __name__ == "__main__":
    unittest.main()
