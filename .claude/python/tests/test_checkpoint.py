"""Tests for sdd_lib.checkpoint — input-hash validated phase resumption."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import checkpoint as cp


def _make_repo_with_state(
    tmp: Path,
    *,
    feat: int = 1,
    run_id: str = "abc123def456",
    phases: dict | None = None,
) -> Path:
    """Create a minimal repo layout with a state.json for testing."""
    (tmp / ".claude").mkdir()
    state_dir = tmp / "workspace" / "output" / ".sys" / ".state"
    state_dir.mkdir(parents=True)
    state = {
        "runId": run_id,
        "FeatNumber": feat,
        "FeatName": "TestFeat",
        "command": "/sdd-full",
        "phases": phases or {},
    }
    (state_dir / f"run-{run_id}.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
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
            _make_repo_with_state(tmp_p, run_id="run-1")
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")

            h = cp.record_input_hash("run-1", "us-generate", ["feat-1.md"], root=tmp_p)
            self.assertEqual(len(h), 64)

            state = json.loads((tmp_p / "workspace" / "output" / ".sys" / ".state" / "run-run-1.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phases"]["us-generate"]["payload"]["input_hash"], h)

    def test_raises_when_state_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "workspace" / "output" / ".sys" / ".state").mkdir(parents=True)
            with self.assertRaises(FileNotFoundError) as ctx:
                cp.record_input_hash("missing-run", "phase", [], root=tmp_p)
            self.assertIn("CHECKPOINT_STATE_UNREADABLE", str(ctx.exception))

    def test_preserves_existing_payload_fields(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            _make_repo_with_state(
                tmp_p,
                run_id="run-2",
                phases={"us-generate": {"status": "pass", "payload": {"existing_field": "kept"}}},
            )
            (tmp_p / "feat-1.md").write_text("content", encoding="utf-8")

            cp.record_input_hash("run-2", "us-generate", ["feat-1.md"], root=tmp_p)
            state = json.loads(
                (tmp_p / "workspace" / "output" / ".sys" / ".state" / "run-run-2.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["phases"]["us-generate"]["payload"]["existing_field"], "kept")
            self.assertIn("input_hash", state["phases"]["us-generate"]["payload"])


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
            self.assertIn("absent from state", reason)

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

            # Older run with mismatched hash
            _make_repo_with_state(
                tmp_p,
                feat=1,
                run_id="old",
                phases={"us-generate": {"status": "pass", "payload": {"input_hash": "deadbeef"}}},
            )
            # Newer run with matching hash — should win
            import time
            time.sleep(0.05)
            sd = tmp_p / "workspace" / "output" / ".sys" / ".state"
            (sd / "run-newer.json").write_text(
                json.dumps({
                    "runId": "newer",
                    "FeatNumber": 1,
                    "phases": {"us-generate": {"status": "pass", "payload": {"input_hash": h_match}}},
                }),
                encoding="utf-8",
            )

            resumable, _ = cp.is_phase_resumable(1, "us-generate", ["feat-1.md"], root=tmp_p)
            self.assertTrue(resumable)


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
