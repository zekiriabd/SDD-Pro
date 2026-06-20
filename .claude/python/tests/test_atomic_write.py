"""v7.0.0 P1 R4 — tests for sdd_lib/atomic_write.py.

Verify atomic_write_text + find_orphan_tmps semantics :
  - target file written correctly
  - .sddtmp removed on success
  - parent dir created if absent
  - idempotent re-write
  - orphan detection
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.atomic_write import (  # noqa: E402
    DEFAULT_TMP_SUFFIX,
    atomic_write_bytes,
    atomic_write_text,
    find_orphan_tmps,
)

# Smoke marker (audit CTO 2026-06-07) — atomic_write is load-bearing for
# parallel dev-backend × dev-frontend writes on LibName shared models +
# CLAUDE.md cleanup. A regression (truncated rename, lost fsync) corrupts
# user code silently. Gated by `framework_smoke -m smoke`.
pytestmark = pytest.mark.smoke


class TestAtomicWriteText(unittest.TestCase):
    def test_writes_file_correctly(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / "Entity.cs"
            atomic_write_text(p, "public class Foo { }")
            self.assertTrue(p.exists())
            self.assertEqual(p.read_text(encoding="utf-8"), "public class Foo { }")

    def test_creates_parent_dir_if_absent(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / "nested" / "deep" / "Entity.cs"
            self.assertFalse(p.parent.exists())
            atomic_write_text(p, "x")
            self.assertTrue(p.exists())

    def test_no_orphan_tmp_after_success(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / "Entity.cs"
            atomic_write_text(p, "content")
            tmps = list(Path(tmp).glob(f"*{DEFAULT_TMP_SUFFIX}"))
            self.assertEqual(tmps, [])

    def test_idempotent_rewrite(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / "Entity.cs"
            atomic_write_text(p, "v1")
            atomic_write_text(p, "v2")
            self.assertEqual(p.read_text(encoding="utf-8"), "v2")

    def test_utf8_encoding_default(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / "Entity.cs"
            content = "// éàü☃"
            atomic_write_text(p, content)
            self.assertEqual(p.read_text(encoding="utf-8"), content)


class TestAtomicWriteBytes(unittest.TestCase):
    def test_binary_write(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / "asset.bin"
            atomic_write_bytes(p, b"\x00\x01\x02\xff")
            self.assertEqual(p.read_bytes(), b"\x00\x01\x02\xff")


class TestFindOrphanTmps(unittest.TestCase):
    def test_empty_when_no_orphans(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            (Path(tmp) / "file.cs").write_text("ok")
            self.assertEqual(list(find_orphan_tmps(tmp)), [])

    def test_detects_orphan_tmp(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orphan = Path(tmp) / "Entity.cs.sddtmp"
            orphan.write_text("partial content")
            found = list(find_orphan_tmps(tmp))
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].name, "Entity.cs.sddtmp")

    def test_detects_orphan_recursively(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            nested = Path(tmp) / "deep" / "nested"
            nested.mkdir(parents=True)
            orphan = nested / "Foo.cs.sddtmp"
            orphan.write_text("x")
            found = list(find_orphan_tmps(tmp))
            self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main()
