"""Tests for sdd_lib.checkpoint — input-hash validated phase resumption.

v7.0.1 audit (2026-06-12) — rewritten to seed the SSoT **console.db** (tables
runs + run_phases) instead of the removed `run-*.json` state files. The module
under test was rewritten onto console.db (the old FS-state path was dead since
the v6.10 migration); these tests now exercise the real persistence layer.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import checkpoint as cp
from sdd_lib import console_db


def _make_repo_with_state(
    tmp: Path,
    *,
    feat: int = 1,
    run_id: str = "abc123def456",
    phases: dict | None = None,
    started_at: str = "2026-06-12T10:00:00.000Z",
) -> Path:
    """Seed console.db at tmp/workspace/db/console.db with a run + phases.

    `phases` mirrors the legacy shape: {phase: {"status": ..., "payload": {...}}}.
    """
    (tmp / ".claude").mkdir(exist_ok=True)
    db = tmp / "workspace" / "db" / "console.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    console_db.ensure_initialized(db)
    with console_db.connect(db) as conn:
        console_db.upsert_run(
            conn, run_id=run_id, command="/sdd-full", feat_n=feat,
            feat_name="TestFeat", status="running", started_at=started_at,
        )
        for phase, info in (phases or {}).items():
            console_db.upsert_run_phase(
                conn, run_id=run_id, phase=phase,
                status=info["status"], payload=info.get("payload"),
            )
    return tmp


class TestComputeInputHash(unittest.TestCase):
    def test_deterministic_with_same_inputs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "a.md").write_text("hello", encoding="utf-8")
            (tmp_p / "b.md").write_text("world", encoding="utf-8")

            h1 = cp.compute_input_hash([tmp_p / "a.md", tmp_p / "b.md"], root=tmp_p)
            h2 = cp.compute_input_hash([tmp_p / "a.md", tmp_p / "b.md"], root=tmp_p)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)

    def test_order_independent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "a.md").write_text("A", encoding="utf-8")
            (tmp_p / "b.md").write_text("B", encoding="utf-8")

            h1 = cp.compute_input_hash([tmp_p / "a.md", tmp_p / "b.md"], root=tmp_p)
            h2 = cp.compute_input_hash([tmp_p / "b.md", tmp_p / "a.md"], root=tmp_p)
            self.assertEqual(h1, h2)

    def test_content_change_changes_hash(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            f = tmp_p / "a.md"
            f.write_text("hello", encoding="utf-8")
            h1 = cp.compute_input_hash([f], root=tmp_p)
            f.write_text("HELLO", encoding="utf-8")
            h2 = cp.compute_input_hash([f], root=tmp_p)
            self.assertNotEqual(h1, h2)

    def test_missing_file_uses_sentinel(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "a.md").write_text("hello", encoding="utf-8")
            # absent.md doesn't exist — sentinel marker
            h = cp.compute_input_hash([tmp_p / "a.md", tmp_p / "absent.md"], root=tmp_p)
            self.assertEqual(len(h), 64)
            # Hash should differ from just [a.md] alone
            h_just_a = cp.compute_input_hash([tmp_p / "a.md"], root=tmp_p)
            self.assertNotEqual(h, h_just_a)

    def test_accepts_string_paths(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "a.md").write_text("hello", encoding="utf-8")
            h1 = cp.compute_input_hash([str(tmp_p / "a.md")], root=tmp_p)
            h2 = cp.compute_input_hash([tmp_p / "a.md"], root=tmp_p)
            self.assertEqual(h1, h2)

    def test_relative_paths_resolved_via_root(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "sub").mkdir()
            (tmp_p / "sub" / "a.md").write_text("hello", encoding="utf-8")
            h1 = cp.compute_input_hash(["sub/a.md"], root=tmp_p)
            h2 = cp.compute_input_hash([tmp_p / "sub" / "a.md"], root=tmp_p)
            self.assertEqual(h1, h2)


class TestRecordInputHash(unittest.TestCase):
    def test_records_hash_in_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(
                tmp_p, feat=1, run_id="run-1",
                phases={"us-generate": {"status": "pass", "payload": {}}},
            )
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")

            h = cp.record_input_hash("run-1", "us-generate", ["feat-1.md"], root=tmp_p)
            self.assertEqual(len(h), 64)

            payload = cp.get_phase_payload(1, "us-generate", root=tmp_p)
            self.assertIsNotNone(payload)
            self.assertEqual(payload["input_hash"], h)

    def test_raises_when_phase_row_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            # Run exists but the target phase row does not → record must raise.
            _make_repo_with_state(tmp_p, feat=1, run_id="missing-phase", phases={})
            with self.assertRaises(FileNotFoundError) as ctx:
                cp.record_input_hash("missing-phase", "phase", [], root=tmp_p)
            self.assertIn("CHECKPOINT_STATE_UNREADABLE", str(ctx.exception))

    def test_preserves_existing_payload_fields(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(
                tmp_p, feat=1, run_id="run-2",
                phases={"us-generate": {"status": "pass", "payload": {"existing_field": "kept"}}},
            )
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")

            cp.record_input_hash("run-2", "us-generate", ["feat-1.md"], root=tmp_p)
            payload = cp.get_phase_payload(1, "us-generate", root=tmp_p)
            self.assertEqual(payload["existing_field"], "kept")
            self.assertIn("input_hash", payload)

    def test_record_preserves_phase_status(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(
                tmp_p, feat=1, run_id="run-3",
                phases={"us-generate": {"status": "warn", "payload": {}}},
            )
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            cp.record_input_hash("run-3", "us-generate", ["feat-1.md"], root=tmp_p)
            # status 'warn' must survive the payload merge → resumable with accept_warn
            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p)
            self.assertTrue(resumable, reason)


class TestIsPhaseResumable(unittest.TestCase):
    def test_resumable_when_pass_and_hash_match(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            h = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "pass", "payload": {"input_hash": h}}},
            )

            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p
            )
            self.assertTrue(resumable, reason)
            self.assertEqual(reason, "ok")

    def test_not_resumable_when_hash_mismatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("initial", encoding="utf-8")
            old_hash = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "pass", "payload": {"input_hash": old_hash}}},
            )
            # Simulate post-run modification
            (tmp_p / "feat-1.md").write_text("modified", encoding="utf-8")

            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p
            )
            self.assertFalse(resumable)
            self.assertIn("CHECKPOINT_HASH_MISMATCH", reason)

    def test_not_resumable_when_phase_not_pass(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            h = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "fail", "payload": {"input_hash": h}}},
            )
            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p
            )
            self.assertFalse(resumable)
            self.assertIn("status='fail'", reason)

    def test_warn_accepted_by_default(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            h = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "warn", "payload": {"input_hash": h}}},
            )
            resumable, _ = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p
            )
            self.assertTrue(resumable)

    def test_warn_rejected_when_accept_warn_false(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            h = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "warn", "payload": {"input_hash": h}}},
            )
            resumable, _ = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p, accept_warn=False,
            )
            self.assertFalse(resumable)

    def test_not_resumable_when_no_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", [], root=tmp_p
            )
            self.assertFalse(resumable)
            self.assertIn("CHECKPOINT_STATE_UNREADABLE", reason)

    def test_not_resumable_when_phase_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(tmp_p, feat=1, run_id="r1", phases={})
            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", [], root=tmp_p
            )
            self.assertFalse(resumable)
            self.assertIn("CHECKPOINT_STATE_UNREADABLE", reason)

    def test_not_resumable_when_no_input_hash_legacy(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "pass", "payload": {}}},
            )
            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", [], root=tmp_p
            )
            self.assertFalse(resumable)
            self.assertIn("no recorded", reason)

    def test_not_resumable_when_inputs_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            h = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="r1",
                phases={"us-generate": {"status": "pass", "payload": {"input_hash": h}}},
            )
            (tmp_p / "feat-1.md").unlink()  # input disappeared post-run
            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p
            )
            self.assertFalse(resumable)
            self.assertIn("CHECKPOINT_INPUT_MISSING", reason)

    def test_picks_latest_run_for_feat(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")
            h_match = cp.compute_input_hash([tmp_p / "feat-1.md"], root=tmp_p)

            # Older run with mismatched hash (earlier started_at)
            _make_repo_with_state(
                tmp_p, feat=1, run_id="old",
                started_at="2026-06-12T09:00:00.000Z",
                phases={"us-generate": {"status": "pass", "payload": {"input_hash": "deadbeef"}}},
            )
            # Newer run with matching hash — list_runs orders by started_at DESC → wins
            _make_repo_with_state(
                tmp_p, feat=1, run_id="newer",
                started_at="2026-06-12T11:00:00.000Z",
                phases={"us-generate": {"status": "pass", "payload": {"input_hash": h_match}}},
            )

            resumable, reason = cp.is_phase_resumable(
                1, "us-generate", ["feat-1.md"], root=tmp_p)
            self.assertTrue(resumable, reason)


class TestGetPhasePayload(unittest.TestCase):
    def test_returns_payload(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(
                tmp_p, feat=1, run_id="r1",
                phases={"us-generate": {"status": "pass", "payload": {"foo": 42}}},
            )
            payload = cp.get_phase_payload(1, "us-generate", root=tmp_p)
            self.assertEqual(payload, {"foo": 42})

    def test_returns_none_when_no_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            self.assertIsNone(cp.get_phase_payload(1, "us-generate", root=tmp_p))

    def test_returns_none_when_phase_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(tmp_p, feat=1, run_id="r1", phases={})
            self.assertIsNone(cp.get_phase_payload(1, "us-generate", root=tmp_p))


if __name__ == "__main__":
    unittest.main()
