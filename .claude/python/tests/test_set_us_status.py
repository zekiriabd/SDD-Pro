"""Tests for sdd_scripts.set_us_status — US status setter with transitions."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_scripts import set_us_status as sus  # noqa: E402


US_TEMPLATE_V2 = """# US-{m}: {name}

ID: {fid}-{m}-{name}
Parent FEAT: {fid}-Test
Status: {status}

## User Story
en tant que x
je veux y
afin de z

## Acceptance Criteria
- AC-1: cond
"""


def _make_us(tmp: Path, fid: int, m: int, name: str, status: str = "Draft") -> Path:
    us_dir = tmp / "workspace" / "output" / "us"
    us_dir.mkdir(parents=True, exist_ok=True)
    path = us_dir / f"{fid}-{m}-{name}.md"
    path.write_text(
        US_TEMPLATE_V2.format(m=m, name=name, fid=fid, status=status),
        encoding="utf-8",
    )
    return path


class TestTransitionGraph(unittest.TestCase):
    def test_all_seven_statuses_in_graph(self):
        for s in sus.VALID_STATUSES:
            self.assertIn(s, sus.TRANSITIONS, f"{s} missing from TRANSITIONS")

    def test_forward_happy_path(self):
        for cur, nxt in [("Draft", "Ready"), ("Ready", "InProgress"),
                         ("InProgress", "Review"), ("Review", "Done")]:
            ok, _ = sus.is_transition_allowed(cur, nxt, force=False)
            self.assertTrue(ok, f"{cur} -> {nxt} must be allowed")

    def test_cancelled_is_terminal(self):
        ok, _ = sus.is_transition_allowed("Cancelled", "Ready", force=False)
        self.assertFalse(ok)

    def test_any_to_deferred(self):
        for s in ["Draft", "Ready", "InProgress", "Review"]:
            ok, _ = sus.is_transition_allowed(s, "Deferred", force=False)
            self.assertTrue(ok, f"{s} -> Deferred must be allowed")

    def test_force_bypasses_invalid(self):
        ok, _ = sus.is_transition_allowed("Cancelled", "Draft", force=True)
        self.assertTrue(ok)

    def test_same_status_idempotent(self):
        ok, _ = sus.is_transition_allowed("Done", "Done", force=False)
        self.assertTrue(ok)

    def test_unknown_legacy_status_rejected(self):
        ok, reason = sus.is_transition_allowed("InReview", "Done", force=False)
        self.assertFalse(ok)
        self.assertIn("not in v6.8 graph", reason)

    def test_deferred_can_resume_to_ready(self):
        ok, _ = sus.is_transition_allowed("Deferred", "Ready", force=False)
        self.assertTrue(ok)

    def test_done_rework_to_in_progress_allowed(self):
        ok, _ = sus.is_transition_allowed("Done", "InProgress", force=False)
        self.assertTrue(ok)


class TestReadCurrentStatus(unittest.TestCase):
    def test_reads_status(self):
        content = "ID: 1-1-x\nStatus: Ready\n\n## User Story\n"
        self.assertEqual(sus.read_current_status(content), "Ready")

    def test_returns_none_if_absent(self):
        content = "# US-1\nID: 1-1-x\n\n## User Story\n"
        self.assertIsNone(sus.read_current_status(content))

    def test_tolerates_trailing_spaces(self):
        content = "Status: InProgress   \n"
        self.assertEqual(sus.read_current_status(content), "InProgress")


class TestStatusLineRegexPreservesBlankLine(unittest.TestCase):
    """Regression: regex must NOT consume the trailing newline."""

    def test_substitution_preserves_blank_line(self):
        original = "Status: Draft\n\n## User Story\n"
        new_content, n = sus.STATUS_LINE_RE.subn("Status: Ready", original, count=1)
        self.assertEqual(n, 1)
        self.assertEqual(new_content, "Status: Ready\n\n## User Story\n")


class TestResolveUSPathEndToEnd(unittest.TestCase):
    def test_resolve_and_update(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            us_path = _make_us(tmp_p, 1, 2, "Auth", status="Draft")

            with mock.patch.object(sus, "repo_root", return_value=tmp_p):
                resolved = sus.resolve_us_path("1-2")
                self.assertIsNotNone(resolved)
                self.assertEqual(resolved.name, us_path.name)

    def test_unresolvable_returns_none(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            (tmp_p / "workspace" / "output" / "us").mkdir(parents=True)
            with mock.patch.object(sus, "repo_root", return_value=tmp_p):
                self.assertIsNone(sus.resolve_us_path("9-9"))

    def test_bad_id_format_returns_none(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            with mock.patch.object(sus, "repo_root", return_value=tmp_p):
                self.assertIsNone(sus.resolve_us_path("invalid"))
                self.assertIsNone(sus.resolve_us_path("1-2-3"))


class TestMainEndToEnd(unittest.TestCase):
    """Exercise main() with patched argv + repo_root."""

    def test_get_returns_current(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            _make_us(tmp_p, 3, 1, "Status", status="InProgress")
            with mock.patch.object(sus, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["set_us_status.py", "--us", "3-1", "--get"]):
                rc = sus.main()
            self.assertEqual(rc, 0)

    def test_invalid_transition_returns_3(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            _make_us(tmp_p, 3, 1, "Status", status="Draft")
            with mock.patch.object(sus, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["set_us_status.py", "--us", "3-1",
                                    "--status", "Done"]):
                rc = sus.main()
            self.assertEqual(rc, 3)

    def test_us_not_found_returns_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            with mock.patch.object(sus, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["set_us_status.py", "--us", "9-9",
                                    "--status", "Ready"]):
                rc = sus.main()
            self.assertEqual(rc, 1)

    def test_happy_forward_chain(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            us_path = _make_us(tmp_p, 1, 1, "Auth", status="Draft")

            with mock.patch.object(sus, "repo_root", return_value=tmp_p):
                for nxt in ["Ready", "InProgress", "Review", "Done"]:
                    with mock.patch.object(sys, "argv",
                                           ["set_us_status.py", "--us", "1-1",
                                            "--status", nxt]):
                        rc = sus.main()
                    self.assertEqual(rc, 0, f"failed setting {nxt}")
                    self.assertIn(
                        f"Status: {nxt}", us_path.read_text(encoding="utf-8"),
                    )

    def test_terminal_reopen_without_force_fails(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            _make_us(tmp_p, 1, 1, "Auth", status="Done")
            with mock.patch.object(sus, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["set_us_status.py", "--us", "1-1",
                                    "--status", "Cancelled"]):
                rc = sus.main()
            self.assertEqual(rc, 3)

    def test_terminal_reopen_with_force_succeeds(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_p = Path(tmp)
            (tmp_p / ".claude").mkdir()
            _make_us(tmp_p, 1, 1, "Auth", status="Done")
            with mock.patch.object(sus, "repo_root", return_value=tmp_p), \
                 mock.patch.object(sys, "argv",
                                   ["set_us_status.py", "--us", "1-1",
                                    "--status", "Cancelled", "--force"]):
                rc = sus.main()
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
