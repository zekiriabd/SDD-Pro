"""Unit tests for gate_decide.py — atomic read/write of status.json gates.

Coverage:
- iso_now() returns canonical UTC ISO-8601 with Z suffix
- read action: pending|validated|skipped|none
- pose-pending: sets decision=pending + askedAt
- set: sets decision + answeredAt + answeredBy
- is-resolved: exit 0 if validated|skipped, exit 1 otherwise
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "gate_decide.py"


def run_script(args: list[str], status_file: Path) -> subprocess.CompletedProcess:
    """Invoke gate_decide.py with given args + --status-file override."""
    cmd = [sys.executable, str(SCRIPT)] + args + ["--status-file", str(status_file)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)


def init_status(path: Path) -> None:
    """Write a minimal valid status.json."""
    path.write_text(
        json.dumps({"version": 1, "gates": {}}, indent=2),
        encoding="utf-8",
    )


class TestGateDecide(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.status_path = Path(self.tmp.name) / "status.json"
        init_status(self.status_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_read_none_when_gate_absent(self) -> None:
        result = run_script(
            ["read", "--feat-num", "1", "--phase", "afterUS"],
            self.status_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "none")

    def test_pose_pending_creates_gate(self) -> None:
        result = run_script(
            ["pose-pending", "--feat-num", "1", "--phase", "afterUS"],
            self.status_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.status_path.read_text(encoding="utf-8"))
        gate = data["gates"]["1"]["afterUS"]
        self.assertEqual(gate["decision"], "pending")
        self.assertIn("askedAt", gate)
        # iso_now canonical format check
        self.assertRegex(gate["askedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_read_pending_after_pose(self) -> None:
        run_script(
            ["pose-pending", "--feat-num", "1", "--phase", "afterUS"],
            self.status_path,
        )
        result = run_script(
            ["read", "--feat-num", "1", "--phase", "afterUS"],
            self.status_path,
        )
        self.assertEqual(result.stdout.strip(), "pending")

    def test_set_validated(self) -> None:
        run_script(
            ["pose-pending", "--feat-num", "1", "--phase", "afterPlan"],
            self.status_path,
        )
        result = run_script(
            [
                "set", "--feat-num", "1", "--phase", "afterPlan",
                "--decision", "validated", "--answered-by", "test@local",
            ],
            self.status_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.status_path.read_text(encoding="utf-8"))
        gate = data["gates"]["1"]["afterPlan"]
        self.assertEqual(gate["decision"], "validated")
        self.assertEqual(gate["answeredBy"], "test@local")
        self.assertIn("answeredAt", gate)

    def test_is_resolved_exits_0_when_validated(self) -> None:
        run_script(
            ["pose-pending", "--feat-num", "2", "--phase", "afterCode"],
            self.status_path,
        )
        run_script(
            ["set", "--feat-num", "2", "--phase", "afterCode",
             "--decision", "validated", "--answered-by", "user@x"],
            self.status_path,
        )
        result = run_script(
            ["is-resolved", "--feat-num", "2", "--phase", "afterCode"],
            self.status_path,
        )
        self.assertEqual(result.returncode, 0)

    def test_is_resolved_exits_1_when_pending(self) -> None:
        run_script(
            ["pose-pending", "--feat-num", "3", "--phase", "afterReadiness"],
            self.status_path,
        )
        result = run_script(
            ["is-resolved", "--feat-num", "3", "--phase", "afterReadiness"],
            self.status_path,
        )
        self.assertEqual(result.returncode, 1)

    def test_iso_now_format(self) -> None:
        """Direct unit test of the canonical iso_now() helper."""
        sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))
        from sdd_lib.paths import iso_now
        ts = iso_now()
        # Format: YYYY-MM-DDTHH:MM:SSZ
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


if __name__ == "__main__":
    unittest.main()
