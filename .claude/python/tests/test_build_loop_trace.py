"""Unit tests for sdd_lib.build_loop_trace (T2.6 audit 2026-06-08).

Covers convergence detection on a temp console.db :
- record_iter persists with auto streak computation
- should_stop_for_convergence returns False on first iter
- streak increments when same [CLASS] repeats
- streak resets when [CLASS] changes
- converged=True clears the streak signal
- get_loop_stats aggregates correctly
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))


def _make_temp_db_with_schema(tmpdir: Path) -> Path:
    """Create workspace/output/db/console.db with migrations applied."""
    db_dir = tmpdir / "workspace" / "output" / "db"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "console.db"

    schema_sql = (_PY_ROOT / "sdd_lib" / "console_db_schema.sql").read_text(encoding="utf-8")
    mig_path = _PY_ROOT / "sdd_lib" / "migrations" / "0006_add-build-loop-traces-table.sql"
    mig_sql = mig_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql)
    conn.executescript(mig_sql)
    conn.commit()
    conn.close()
    return db_path


class TestBuildLoopTrace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        # Strict repo layout for repo_root() to honor the override silently
        (self.root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
        (self.root / "workspace").mkdir(parents=True, exist_ok=True)
        _make_temp_db_with_schema(self.root)
        self.env_patch = patch.dict(os.environ, {"SDD_REPO_ROOT": str(self.root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_first_iter_no_convergence_signal(self):
        from sdd_lib.build_loop_trace import record_iter, should_stop_for_convergence
        rowid = record_iter(
            run_id="run-1", feat_n=1, us_id="1-1", agent="dev-backend",
            iter=1, error_class_after="[BUILD_CORRECTIBLE]", converged=False,
        )
        self.assertIsNotNone(rowid)
        # First iter, no streak yet (streak=1, threshold=2)
        self.assertFalse(should_stop_for_convergence(
            us_id="1-1", agent="dev-backend", streak_threshold=2))

    def test_same_class_twice_triggers_stop(self):
        from sdd_lib.build_loop_trace import record_iter, should_stop_for_convergence
        for i in (1, 2):
            record_iter(
                run_id="run-1", feat_n=1, us_id="1-1", agent="dev-backend",
                iter=i, error_class_after="[BUILD_CORRECTIBLE]", converged=False,
            )
        self.assertTrue(should_stop_for_convergence(
            us_id="1-1", agent="dev-backend", streak_threshold=2))

    def test_class_change_resets_streak(self):
        from sdd_lib.build_loop_trace import record_iter, should_stop_for_convergence
        record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                    iter=1, error_class_after="[BUILD_CORRECTIBLE]", converged=False)
        record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                    iter=2, error_class_after="[LAYER_VIOLATION]", converged=False)
        # Streak reset to 1 (different class)
        self.assertFalse(should_stop_for_convergence(
            us_id="1-1", agent="dev-backend", streak_threshold=2))

    def test_converged_clears_stop_signal(self):
        from sdd_lib.build_loop_trace import record_iter, should_stop_for_convergence
        for i in (1, 2):
            record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                        iter=i, error_class_after="[BUILD_CORRECTIBLE]", converged=False)
        # Now iter 3 converges
        record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                    iter=3, error_class_after=None, converged=True)
        self.assertFalse(should_stop_for_convergence(
            us_id="1-1", agent="dev-backend", streak_threshold=2))

    def test_get_loop_stats_aggregates(self):
        from sdd_lib.build_loop_trace import record_iter, get_loop_stats
        # 2 loops same FEAT, 1 converges, 1 stuck
        for i in (1, 2):
            record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                        iter=i, error_class_after="[BUILD_CORRECTIBLE]", converged=False)
        record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                    iter=3, converged=True)
        for i in (1, 2):
            record_iter(run_id="r", feat_n=1, us_id="1-2", agent="dev-backend",
                        iter=i, error_class_after="[LAYER_VIOLATION]", converged=False)

        stats = get_loop_stats(feat_n=1)
        self.assertTrue(stats["available"])
        self.assertEqual(stats["total_loops"], 2)  # (1-1, dev-backend), (1-2, dev-backend)
        self.assertEqual(stats["convergence_events"], 1)
        self.assertGreaterEqual(stats["max_streak"], 2)
        self.assertGreaterEqual(stats["total_iters"], 5)

    def test_per_us_isolation(self):
        """Streak on 1-1 should not affect 1-2."""
        from sdd_lib.build_loop_trace import record_iter, should_stop_for_convergence
        for i in (1, 2):
            record_iter(run_id="r", feat_n=1, us_id="1-1", agent="dev-backend",
                        iter=i, error_class_after="[BUILD_CORRECTIBLE]", converged=False)
        self.assertTrue(should_stop_for_convergence(us_id="1-1", agent="dev-backend"))
        self.assertFalse(should_stop_for_convergence(us_id="1-2", agent="dev-backend"))


if __name__ == "__main__":
    unittest.main()
