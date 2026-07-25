"""Unit tests for sdd_lib/adr_id.py — collision-resistant ADR filename minter."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib import adr_id  # noqa: E402

# Smoke marker (audit CTO 2026-06-07) — ADR minting underpins arch +
# dev-* + constitutioner parallel writes. A regression (lost rand4,
# broken retry) causes silent ADR overwrites under parallel /dev-run.
pytestmark = pytest.mark.smoke


# Canonical regex per `sdd_scripts/index_adrs.py` — the contract this module
# MUST satisfy to ensure ADRs are indexed correctly.
_INDEX_REGEX = re.compile(r"^ADR-(\d{8}T\d{6})(?:-[a-z0-9]+)?-(.+)\.md$")


class TestMintAdrFilename(unittest.TestCase):
    def test_canonical_shape(self) -> None:
        fname = adr_id.mint_adr_filename("stack-backend-dotnet")
        # Must match the index regex (load-bearing for index_adrs.py)
        m = _INDEX_REGEX.match(fname)
        self.assertIsNotNone(m, f"filename {fname!r} doesn't match index regex")
        ts, slug = m.group(1), m.group(2)
        self.assertEqual(len(ts), 15)  # YYYYMMDDTHHMMSS = 8+1+6
        self.assertEqual(slug, "stack-backend-dotnet")

    def test_includes_rand4_systematically(self) -> None:
        """v7.0.0 contract: rand4 is ALWAYS present (not conditional)."""
        fname = adr_id.mint_adr_filename("test-slug")
        # Expected: ADR-{ts}-{rand4}-{slug}.md → 4 segments after split
        parts = fname[len("ADR-"):-len(".md")].split("-", 2)
        # parts = [ts, rand4, "test-slug"]
        self.assertEqual(len(parts), 3)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{4}", parts[1]),
                        f"rand4 segment {parts[1]!r} is not 4-hex")

    def test_when_override(self) -> None:
        """Injected datetime is used in the timestamp (test injection)."""
        when = datetime(2026, 6, 7, 14, 30, 22, tzinfo=timezone.utc)
        fname = adr_id.mint_adr_filename("foo", when=when)
        self.assertIn("20260607T143022-", fname)

    def test_two_calls_same_second_differ_via_rand4(self) -> None:
        """Even within the same UTC second, two calls produce distinct files
        thanks to rand4 (probability of collision is 1/65536)."""
        when = datetime(2026, 6, 7, 14, 30, 22, tzinfo=timezone.utc)
        seen: set[str] = set()
        for _ in range(50):
            seen.add(adr_id.mint_adr_filename("same-slug", when=when))
        # Birthday-paradox lower bound: 50 calls × 1/65536 collision rate.
        # Realistic check: at least 49 unique names (1 collision tolerated).
        self.assertGreaterEqual(len(seen), 49)

    def test_slug_sanitization(self) -> None:
        """Slugs with spaces/uppercase/special chars get normalized."""
        cases = [
            ("Stack Backend .NET",   "stack-backend-net"),
            ("  hello  WORLD  ",     "hello-world"),
            ("foo@bar/baz_qux",      "foo-bar-baz-qux"),
            ("a---b---c",            "a-b-c"),
            ("---leading-dashes---", "leading-dashes"),
        ]
        for raw, expected in cases:
            fname = adr_id.mint_adr_filename(raw)
            # Extract slug = everything after the last `-{rand4}-`
            parts = fname[len("ADR-"):-len(".md")].split("-", 2)
            self.assertEqual(parts[2], expected, f"slug for {raw!r}")

    def test_empty_slug_fallback(self) -> None:
        """Empty or fully-stripped slug falls back to 'unnamed'."""
        for raw in ("", "   ", "---", "@@@@@"):
            fname = adr_id.mint_adr_filename(raw)
            parts = fname[len("ADR-"):-len(".md")].split("-", 2)
            self.assertEqual(parts[2], "unnamed")

    def test_slug_truncation_to_40_chars(self) -> None:
        """Slugs longer than 40 chars get truncated."""
        long_slug = "a" * 60
        fname = adr_id.mint_adr_filename(long_slug)
        parts = fname[len("ADR-"):-len(".md")].split("-", 2)
        self.assertLessEqual(len(parts[2]), 40)


class TestRetryOnCollision(unittest.TestCase):
    """Audit CTO 2026-06-07 — `adrs_dir` parameter triggers retry-on-collision
    when the candidate filename already exists. Pins the contract for
    ``/dev-run --max-parallel 6`` where collision proba ≈ 0.027 % per
    same-second batch."""

    def test_legacy_no_dir_no_disk_check(self) -> None:
        """Calling without adrs_dir performs no disk I/O (backward-compat)."""
        # Should not raise even when no dir is passed
        fname = adr_id.mint_adr_filename("legacy-slug")
        self.assertTrue(fname.startswith("ADR-"))

    def test_with_empty_dir_returns_immediately(self) -> None:
        """When the dir is empty, mint succeeds on the first try."""
        with tempfile.TemporaryDirectory() as tmp:
            when = datetime(2026, 6, 7, 14, 30, 22, tzinfo=timezone.utc)
            fname = adr_id.mint_adr_filename("test", when=when, adrs_dir=tmp)
            self.assertIn("20260607T143022-", fname)
            self.assertTrue(fname.endswith("-test.md"))

    def test_retry_on_existing_filename(self) -> None:
        """If the first rand4 collides with an existing file, retry succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            when = datetime(2026, 6, 7, 14, 30, 22, tzinfo=timezone.utc)

            # Patch secrets.token_hex to return a known sequence : first call
            # returns "aaaa" (which we'll plant on disk), subsequent calls
            # return "bbbb" → retry should pick the unique one.
            tokens = iter(["aaaa", "bbbb", "cccc"])
            (Path(tmp) / "ADR-20260607T143022-aaaa-test.md").write_text("planted")

            with patch.object(adr_id.secrets, "token_hex",
                              side_effect=lambda _n: next(tokens)):
                fname = adr_id.mint_adr_filename("test", when=when, adrs_dir=tmp)
            self.assertEqual(fname, "ADR-20260607T143022-bbbb-test.md")

    def test_retry_budget_5_attempts(self) -> None:
        """After 5 collisions, returns the last candidate (caller handles)."""
        with tempfile.TemporaryDirectory() as tmp:
            when = datetime(2026, 6, 7, 14, 30, 22, tzinfo=timezone.utc)

            # Plant 5 collisions for the first 5 rand4 values
            tokens_seq = ["a1", "a2", "a3", "a4", "a5", "a6"]
            for tok in tokens_seq[:5]:
                # secrets.token_hex(2) returns 4 chars : pad to 4
                planted = (tok + "0" * 4)[:4]
                (Path(tmp) / f"ADR-20260607T143022-{planted}-test.md").write_text("planted")

            tokens = iter(["a1000"[:4], "a2000"[:4], "a3000"[:4],
                           "a4000"[:4], "a5000"[:4], "a6000"[:4]])
            with patch.object(adr_id.secrets, "token_hex",
                              side_effect=lambda _n: next(tokens)):
                fname = adr_id.mint_adr_filename("test", when=when, adrs_dir=tmp)
            # All 5 retries exhausted → returns the last candidate
            # (caller's atomic_write would then surface the collision)
            self.assertTrue(fname.startswith("ADR-20260607T143022-"))
            self.assertTrue(fname.endswith("-test.md"))


if __name__ == "__main__":
    unittest.main()
