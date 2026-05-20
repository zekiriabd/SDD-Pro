"""Tests for sdd_scripts.migrate_us_v1_to_v2 — idempotent US schema migration."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import migrate_us_v1_to_v2 as mig  # noqa: E402


US_V1_NO_STATUS_NO_META = """# US-1: Legacy

ID: 1-1-Legacy
Parent FEAT: 1-Test

## User Story
en tant que x
je veux y
afin de z

## Acceptance Criteria
- AC-1: cond
"""


US_V1_HAS_STATUS_NO_META = """# US-1: Legacy

ID: 1-1-Legacy
Parent FEAT: 1-Test
Status: Done

## User Story
en tant que x

## Acceptance Criteria
- AC-1: cond
"""


US_V2_COMPLETE = """# US-1: Modern

ID: 1-1-Modern
Parent FEAT: 1-Test
Status: Draft

## User Story
x

## Acceptance Criteria
- AC-1: cond

## Metadata
```json
{}
```
"""


class TestMigrateContent(unittest.TestCase):
    def test_v1_no_status_no_meta_gets_both(self):
        new, changes = mig.migrate_content(US_V1_NO_STATUS_NO_META)
        self.assertEqual(len(changes), 2)
        self.assertIn("Status: Draft", new)
        self.assertIn("## Metadata", new)
        self.assertIn("```json", new)

    def test_v1_with_status_only_gets_meta(self):
        new, changes = mig.migrate_content(US_V1_HAS_STATUS_NO_META)
        self.assertEqual(len(changes), 1)
        self.assertIn("## Metadata", changes[0])
        # Preserved existing Status
        self.assertIn("Status: Done", new)

    def test_v2_complete_is_no_op(self):
        new, changes = mig.migrate_content(US_V2_COMPLETE)
        self.assertEqual(changes, [])
        self.assertEqual(new, US_V2_COMPLETE)

    def test_status_injected_after_parent_feat(self):
        new, _ = mig.migrate_content(US_V1_NO_STATUS_NO_META)
        lines = new.split("\n")
        parent_idx = next(i for i, l in enumerate(lines) if l.startswith("Parent FEAT:"))
        self.assertEqual(lines[parent_idx + 1], "Status: Draft")

    def test_idempotent_double_apply(self):
        once, _ = mig.migrate_content(US_V1_NO_STATUS_NO_META)
        twice, changes2 = mig.migrate_content(once)
        self.assertEqual(changes2, [])
        self.assertEqual(twice, once)

    def test_existing_content_preserved(self):
        new, _ = mig.migrate_content(US_V1_NO_STATUS_NO_META)
        self.assertIn("en tant que x", new)
        self.assertIn("- AC-1: cond", new)


class TestProcessOne(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            us = tmp_p / "us.md"
            us.write_text(US_V1_NO_STATUS_NO_META, encoding="utf-8")
            result = mig.process_one(us, dry_run=True)
            self.assertEqual(result["status"], "would-migrate")
            self.assertEqual(us.read_text(encoding="utf-8"), US_V1_NO_STATUS_NO_META)

    def test_apply_writes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            us = tmp_p / "us.md"
            us.write_text(US_V1_NO_STATUS_NO_META, encoding="utf-8")
            result = mig.process_one(us, dry_run=False)
            self.assertEqual(result["status"], "migrated")
            after = us.read_text(encoding="utf-8")
            self.assertIn("## Metadata", after)
            self.assertIn("Status: Draft", after)

    def test_skip_already_v2(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            us = tmp_p / "us.md"
            us.write_text(US_V2_COMPLETE, encoding="utf-8")
            result = mig.process_one(us, dry_run=False)
            self.assertEqual(result["status"], "skipped")


class TestDiscoverAndMain(unittest.TestCase):
    def _setup_repo(self, tmp_p: Path, files: dict[str, str]) -> None:
        (tmp_p / ".claude").mkdir()
        us_dir = tmp_p / "workspace" / "output" / "us"
        us_dir.mkdir(parents=True)
        for name, content in files.items():
            (us_dir / name).write_text(content, encoding="utf-8")

    def test_discover_all_us_globs_correctly(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup_repo(tmp_p, {
                "1-1-Auth.md": US_V1_NO_STATUS_NO_META,
                "1-2-Reset.md": US_V2_COMPLETE,
                "README.md": "should be ignored",  # doesn't match {n}-{m}-{name}
            })
            with mock.patch.object(mig, "repo_root", return_value=tmp_p):
                found = mig.discover_all_us()
            names = sorted(p.name for p in found)
            self.assertIn("1-1-Auth.md", names)
            self.assertIn("1-2-Reset.md", names)
            self.assertNotIn("README.md", names)

    def test_main_all_dry_run(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup_repo(tmp_p, {
                "1-1-Auth.md": US_V1_NO_STATUS_NO_META,
                "1-2-Modern.md": US_V2_COMPLETE,
            })
            with mock.patch.object(mig, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["migrate_us_v1_to_v2.py", "--all",
                                    "--dry-run"]):
                rc = mig.main()
            self.assertEqual(rc, 0)
            # Files unchanged
            us_dir = tmp_p / "workspace" / "output" / "us"
            self.assertEqual(
                (us_dir / "1-1-Auth.md").read_text(encoding="utf-8"),
                US_V1_NO_STATUS_NO_META,
            )

    def test_main_all_apply(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            self._setup_repo(tmp_p, {
                "1-1-Auth.md": US_V1_NO_STATUS_NO_META,
            })
            with mock.patch.object(mig, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["migrate_us_v1_to_v2.py", "--all"]):
                rc = mig.main()
            self.assertEqual(rc, 0)
            content = (tmp_p / "workspace" / "output" / "us"
                       / "1-1-Auth.md").read_text(encoding="utf-8")
            self.assertIn("## Metadata", content)

    def test_main_no_us_returns_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            with mock.patch.object(mig, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["migrate_us_v1_to_v2.py", "--all"]):
                rc = mig.main()
            self.assertEqual(rc, 1)

    def test_main_single_us_unknown_returns_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "workspace" / "output" / "us").mkdir(parents=True)
            with mock.patch.object(mig, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["migrate_us_v1_to_v2.py", "--us", "9-9"]):
                rc = mig.main()
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
