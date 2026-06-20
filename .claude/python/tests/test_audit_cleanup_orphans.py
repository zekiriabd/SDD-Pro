"""Tests for audit_orphans.py and cleanup_orphans.py (v7.0.0)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# Make sdd_scripts importable
_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_admin import audit_orphans, cleanup_orphans  # noqa: E402


def _make_fake_project(root: Path) -> None:
    """Create a minimal SDD_Pro layout under `root`."""
    (root / ".claude").mkdir()
    (root / "workspace" / "input" / "feats").mkdir(parents=True)
    (root / "workspace" / "output" / "us").mkdir(parents=True)
    (root / "workspace" / "output" / "plans").mkdir(parents=True)
    (root / "workspace" / "output" / "qa").mkdir(parents=True)


class TestAuditOrphans(unittest.TestCase):
    def test_clean_workspace_returns_zero_orphans(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            (root / "workspace" / "input" / "feats" / "1-Auth.md").write_text("# FEAT")
            (root / "workspace" / "output" / "us" / "1-1-Login.md").write_text("# US")
            (root / "workspace" / "output" / "plans" / "1-1-Login.back.md").write_text("# Plan")
            orphans = audit_orphans.find_orphans(root)
            self.assertEqual(sum(len(v) for v in orphans.values()), 0)

    def test_us_orphan_detected_when_feat_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            # No FEAT, but US present
            (root / "workspace" / "output" / "us" / "1-1-Login.md").write_text("# US")
            orphans = audit_orphans.find_orphans(root)
            self.assertEqual(len(orphans["us_orphans"]), 1)
            self.assertEqual(orphans["us_orphans"][0]["us"], "1-1")
            # direct_orphans aggregates the absent FEAT
            self.assertEqual(len(orphans["direct_orphans"]), 1)

    def test_plan_orphan_detected_when_us_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            (root / "workspace" / "input" / "feats" / "1-Auth.md").write_text("# FEAT")
            # Plan exists but no US
            (root / "workspace" / "output" / "plans" / "1-2-Reset.back.md").write_text("# Plan")
            orphans = audit_orphans.find_orphans(root)
            self.assertEqual(len(orphans["plan_orphans"]), 1)
            self.assertEqual(orphans["plan_orphans"][0]["us"], "1-2")

    def test_qa_orphan_detected_when_feat_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            qa_dir = root / "workspace" / "output" / "qa" / "feat-99"
            qa_dir.mkdir()
            (qa_dir / "report.md").write_text("# QA")
            orphans = audit_orphans.find_orphans(root)
            self.assertEqual(len(orphans["qa_orphans"]), 1)
            self.assertEqual(orphans["qa_orphans"][0]["feat"], 99)

    def test_feat_filter_restricts_scope(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            (root / "workspace" / "output" / "us" / "1-1-A.md").write_text("# US")
            (root / "workspace" / "output" / "us" / "2-1-B.md").write_text("# US")
            orphans = audit_orphans.find_orphans(root, feat_filter=1)
            us_n_values = {o["feat"] for o in orphans["us_orphans"]}
            self.assertEqual(us_n_values, {1})

    def test_main_returns_fail_fast_on_orphans(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            (root / "workspace" / "output" / "us" / "5-1-Orphan.md").write_text("# US")
            exit_code = audit_orphans.main(["--root", str(root)])
            self.assertEqual(exit_code, 1)  # FAIL_FAST = orphans detected

    def test_main_returns_success_when_clean(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            exit_code = audit_orphans.main(["--root", str(root)])
            self.assertEqual(exit_code, 0)

    def test_main_json_output_is_parseable(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            (root / "workspace" / "output" / "us" / "3-1-X.md").write_text("# US")
            from io import StringIO
            buf = StringIO()
            with patch("sys.stdout", buf):
                audit_orphans.main(["--root", str(root), "--json"])
            data = json.loads(buf.getvalue())
            self.assertIn("orphans", data)
            self.assertEqual(len(data["orphans"]["us_orphans"]), 1)


class TestCleanupOrphans(unittest.TestCase):
    def test_protected_path_detection(self) -> None:
        self.assertTrue(cleanup_orphans._is_protected("workspace/input/feats/1-A.md"))
        self.assertTrue(cleanup_orphans._is_protected("workspace/console/server.js"))
        self.assertTrue(cleanup_orphans._is_protected("workspace/output/.sys/.context/constitution.md"))
        self.assertTrue(cleanup_orphans._is_protected("workspace/output/db/console.db"))
        self.assertTrue(cleanup_orphans._is_protected("workspace/output/.sys/.trash/old/file.md"))
        self.assertTrue(cleanup_orphans._is_protected("../etc/passwd"))  # paranoid out-of-scope
        # Safe to delete (genuine orphan):
        self.assertFalse(cleanup_orphans._is_protected("workspace/output/us/1-1-X.md"))
        self.assertFalse(cleanup_orphans._is_protected("workspace/output/plans/1-2-Y.back.md"))
        self.assertFalse(cleanup_orphans._is_protected("workspace/output/qa/feat-5/report.md"))

    def test_dry_run_does_not_modify_fs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_fake_project(root)
            orphan = root / "workspace" / "output" / "us" / "7-1-Orphan.md"
            orphan.write_text("# Orphan US")
            exit_code = cleanup_orphans.main(["--root", str(root), "--dry-run"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(orphan.exists(), "Dry-run should NOT delete files")

    def test_collect_target_paths(self) -> None:
        orphans = {
            "us_orphans": [{"path": "workspace/output/us/1-1-X.md", "feat": 1}],
            "plan_orphans": [{"path": "workspace/output/plans/1-1-X.back.md", "feat": 1}],
            "qa_orphans": [],
            "direct_orphans": [{"feat": 1, "reason": "absent"}],  # no path key
        }
        paths = cleanup_orphans._collect_target_paths(orphans)
        self.assertEqual(len(paths), 2)


if __name__ == "__main__":
    unittest.main()
