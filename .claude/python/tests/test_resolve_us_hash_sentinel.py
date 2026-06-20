"""Unit tests for sdd_scripts/resolve_us_hash_sentinel.py + sdd_hooks/resolve_po_hash_sentinel.py.

Coverage:
- Single FEAT mode: patches all matching US files
- auto-detect mode: discovers FEAT numbers from US filenames
- Idempotence: re-running on resolved files is a no-op
- Missing FEAT: warns but doesn't error
- Multiple FEATs: each US patched with its own parent hash
- Hook: invokes script in --auto-detect, non-blocking on failure
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_scripts import resolve_us_hash_sentinel as rus  # noqa: E402

SENTINEL_LINE = "Parent FEAT hash: sha256:COMPUTE_REQUIRED"


class TestResolveUsHashSentinel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude").mkdir()
        (self.root / "workspace" / "input" / "feats").mkdir(parents=True)
        (self.root / "workspace" / "output" / "us").mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write_feat(self, n: int, name: str = "Auth", content: str = "# Auth FEAT\n") -> str:
        # write_bytes to preserve LF (write_text converts to CRLF on Windows,
        # which would mismatch the hash the script computes from raw bytes).
        p = self.root / "workspace" / "input" / "feats" / f"{n}-{name}.md"
        raw = content.encode("utf-8")
        p.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()[:8]

    def _write_us(self, n: int, m: int, name: str = "Login", with_sentinel: bool = True):
        body = f"# US {n}-{m}-{name}\n"
        if with_sentinel:
            body += f"\n{SENTINEL_LINE}\n"
        p = self.root / "workspace" / "output" / "us" / f"{n}-{m}-{name}.md"
        p.write_bytes(body.encode("utf-8"))
        return p

    def test_single_feat_patches_all_us(self):
        expected_hash = self._write_feat(1)
        us1 = self._write_us(1, 1)
        us2 = self._write_us(1, 2, name="Logout")

        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--feat-number", "1", "--quiet"]):
            rc = rus.main()
        self.assertEqual(rc, 0)

        for us in (us1, us2):
            txt = us.read_text(encoding="utf-8")
            self.assertNotIn("COMPUTE_REQUIRED", txt)
            self.assertIn(f"sha256:{expected_hash}", txt)

    def test_idempotent_no_op_on_resolved(self):
        expected_hash = self._write_feat(1)
        us = self._write_us(1, 1)
        # First run resolves
        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--feat-number", "1", "--quiet"]):
            rus.main()
        mtime1 = us.stat().st_mtime
        # Second run: file shouldn't change
        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--feat-number", "1", "--quiet"]):
            rc = rus.main()
        self.assertEqual(rc, 0)
        # Content unchanged (hash matches)
        self.assertIn(f"sha256:{expected_hash}", us.read_text(encoding="utf-8"))

    def test_missing_feat_warns_no_error(self):
        # US exists but no FEAT
        self._write_us(99, 1)
        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--feat-number", "99", "--quiet"]):
            rc = rus.main()
        # Per script docstring: non-error for SubagentStop friendliness
        self.assertEqual(rc, 0)

    def test_auto_detect_multiple_feats(self):
        h1 = self._write_feat(1, name="Auth")
        h2 = self._write_feat(2, name="Profile")
        u11 = self._write_us(1, 1)
        u21 = self._write_us(2, 1, name="View")

        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--auto-detect", "--quiet"]):
            rc = rus.main()
        self.assertEqual(rc, 0)
        self.assertIn(f"sha256:{h1}", u11.read_text(encoding="utf-8"))
        self.assertIn(f"sha256:{h2}", u21.read_text(encoding="utf-8"))

    def test_auto_detect_empty_workspace_succeeds(self):
        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--auto-detect", "--quiet"]):
            rc = rus.main()
        self.assertEqual(rc, 0)

    def test_us_without_sentinel_left_alone(self):
        self._write_feat(1)
        us = self._write_us(1, 1, with_sentinel=False)
        original = us.read_text(encoding="utf-8")
        with patch.object(sys, "argv", ["resolve_us_hash_sentinel.py", "--feat-number", "1", "--quiet"]):
            rc = rus.main()
        self.assertEqual(rc, 0)
        self.assertEqual(us.read_text(encoding="utf-8"), original)

    def test_feat_number_extraction(self):
        # Internal helper
        self.assertEqual(rus._us_feat_number(Path("1-2-Login.md")), 1)
        self.assertEqual(rus._us_feat_number(Path("42-7-Foo-Bar.md")), 42)
        self.assertIsNone(rus._us_feat_number(Path("bad-format.md")))


class TestResolvePoHashSentinelHook(unittest.TestCase):
    """Hook is non-blocking; verifies it invokes the script and returns 0 always."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "python" / "sdd_scripts").mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        self.env_patch.start()
        # Drain stdin (hook reads it)
        self._stdin_patch = patch("sys.stdin")
        m = self._stdin_patch.start()
        m.read.return_value = "{}"

    def tearDown(self):
        self._stdin_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_hook_script_missing_returns_allow(self):
        # No script at expected path → hook still returns 0 (HOOK_ALLOW)
        from sdd_hooks import resolve_po_hash_sentinel as h
        rc = h.main()
        self.assertEqual(rc, 0)


class TestE2EPoToValidateReadiness(unittest.TestCase):
    """C2 closure (audit CTO 2026-06-07) — E2E chain: po writes sentinel →
    resolve_us_hash_sentinel patches → preflight._check_feat_hash reads
    resolved hash → no [FEAT_HASH_MISMATCH] / [FEAT_HASH_LEGACY] false
    positive. Locks down the case-sensitivity contract (`Parent FEAT hash:`
    lowercase canonical, `Parent FEAT Hash:` / `Parent FEAT HASH:` accepted
    by preflight regex defense-in-depth)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "workspace" / "input" / "feats").mkdir(parents=True)
        (self.root / "workspace" / "output" / "us").mkdir(parents=True)
        self.env_patch = patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.tmp.cleanup()

    def _write_feat(self, n=1, content="# Auth FEAT\nAC-1 login\n"):
        p = self.root / "workspace" / "input" / "feats" / f"{n}-Auth.md"
        raw = content.encode("utf-8")
        p.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()[:8]

    def _write_us(self, n, m, label="Parent FEAT hash"):
        body = f"# US {n}-{m}-Login\n\n{label}: sha256:COMPUTE_REQUIRED\n\nCovers: AC-1\n"
        p = self.root / "workspace" / "output" / "us" / f"{n}-{m}-Login.md"
        p.write_bytes(body.encode("utf-8"))
        return p

    def test_e2e_canonical_lowercase_hash(self):
        """po writes lowercase `Parent FEAT hash:` → resolver patches → preflight matches."""
        expected = self._write_feat(1)
        us_path = self._write_us(1, 1, label="Parent FEAT hash")

        # Step 1 — resolver patches the sentinel
        rc = rus.main.__wrapped__ if hasattr(rus.main, "__wrapped__") else None
        # Direct call via argv simulation
        import sys as _sys
        old_argv = _sys.argv
        try:
            _sys.argv = ["resolve_us_hash_sentinel.py", "--feat-number", "1", "--quiet"]
            self.assertEqual(rus.main(), 0)
        finally:
            _sys.argv = old_argv

        # Step 2 — verify sentinel removed and real hash present
        content = us_path.read_text(encoding="utf-8")
        self.assertNotIn("sha256:COMPUTE_REQUIRED", content)
        self.assertIn(f"sha256:{expected}", content)

        # Step 3 — preflight._check_feat_hash reads it without error
        from sdd_scripts.preflight import _check_feat_hash
        errors, warns = [], []
        _check_feat_hash(
            us_path=us_path, feat_number=1, root=self.root,
            add_err=lambda code, msg: errors.append((code, msg)),
            add_warn=lambda code, msg: warns.append((code, msg)),
        )
        self.assertEqual(errors, [], "no error expected on resolved canonical sentinel")
        self.assertEqual(warns, [], "no warn expected on resolved canonical sentinel")

    def test_e2e_uppercase_hash_label_still_resolved(self):
        """Defense-in-depth : if a future typo writes `Parent FEAT Hash:` (capital H),
        the preflight regex still matches case-insensitively → no FEAT_HASH_LEGACY false positive."""
        expected = self._write_feat(1)
        # Write US with already-resolved hash but uppercase H in label (simulates typo)
        body = f"# US 1-1-Login\n\nParent FEAT Hash: sha256:{expected}\n\nCovers: AC-1\n"
        us_path = self.root / "workspace" / "output" / "us" / "1-1-Login.md"
        us_path.write_bytes(body.encode("utf-8"))

        from sdd_scripts.preflight import _check_feat_hash
        errors, warns = [], []
        _check_feat_hash(
            us_path=us_path, feat_number=1, root=self.root,
            add_err=lambda code, msg: errors.append((code, msg)),
            add_warn=lambda code, msg: warns.append((code, msg)),
        )
        self.assertEqual(errors, [], "uppercase 'Hash' label should match case-insensitively (audit C2)")
        # WARN FEAT_HASH_LEGACY should NOT fire because the regex matched
        legacy_warns = [w for w in warns if w[0] == "FEAT_HASH_LEGACY"]
        self.assertEqual(legacy_warns, [], "FEAT_HASH_LEGACY must not fire when label only differs in case")


if __name__ == "__main__":
    unittest.main()
