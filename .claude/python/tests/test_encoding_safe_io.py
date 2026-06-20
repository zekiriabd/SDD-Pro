"""Smoke test : prod read_text / write_text calls must specify encoding=.

Audit P3 C5 (2026-06-08) — Windows-safe I/O. Without explicit
`encoding="utf-8"`, Python uses `locale.getpreferredencoding()` which on
Windows defaults to `cp1252` (or other code page). This causes :
  - silent truncation of non-ASCII characters when reading
  - encoding errors when writing French/Unicode content
  - downstream JSON parse failures if the writer used cp1252

Production code under `sdd_admin/`, `sdd_hooks/`, `sdd_lib/`, `sdd_scripts/`
must always use `encoding=...` explicit. Tests are exempted (they create
temp files in same-process, encoding round-trips correctly).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

_PROD_DIRS = ("sdd_admin", "sdd_hooks", "sdd_lib", "sdd_scripts")


def _repo_root() -> Path:
    cwd = Path(__file__).resolve()
    for p in [cwd, *cwd.parents]:
        if (p / ".claude").is_dir():
            return p
    raise RuntimeError("Cannot locate repo root")


def _find_call_args(text: str, start_pos: int) -> str:
    """Extract balanced-paren argument list starting at start_pos (the '(' position)."""
    depth = 0
    for i in range(start_pos, min(len(text), start_pos + 1500)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start_pos:i + 1]
    return text[start_pos:start_pos + 1500]


class TestEncodingSafeIO(unittest.TestCase):
    """All .read_text() and .write_text() calls in prod must have encoding=."""

    def test_no_bare_read_or_write_text_in_prod(self):
        py_root = _repo_root() / ".claude" / "python"
        violations: list[tuple[str, int]] = []

        for sub in _PROD_DIRS:
            d = py_root / sub
            if not d.is_dir():
                continue
            for p in d.rglob("*.py"):
                if "__pycache__" in str(p):
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for m in re.finditer(r"\.(read|write)_text\s*\(", text):
                    line_no = text[:m.start()].count("\n") + 1
                    paren_pos = m.end() - 1
                    call_args = _find_call_args(text, paren_pos)
                    if "encoding" not in call_args:
                        rel = p.relative_to(_repo_root()).as_posix()
                        violations.append((rel, line_no))

        if violations:
            details = "\n".join(f"  - {path}:{ln}" for path, ln in violations)
            self.fail(
                f"\nWindows-unsafe I/O detected — read_text/write_text "
                f"without `encoding=` in prod code :\n{details}\n\n"
                f"Fix : add `encoding=\"utf-8\"` (or `\"utf-8-sig\"` for BOM tolerance) "
                f"to every call. Tests are exempted.\n"
            )


if __name__ == "__main__":
    unittest.main()
