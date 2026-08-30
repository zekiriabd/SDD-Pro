"""Unit tests for validate_plan.py — From-Plan Strict gate (v6.2).

Coverage:
- Frontmatter parsing (well-formed, missing, corrupted)
- Structural validation (## Files entries, augment contract)
- Strict mode (schema version, ## Inline Digest, us-hash, AC coverage)
- Staleness detection (us-hash mismatch)
- Exit code semantics (0 = ready/valid, 1 = not_strict_ready, 2 = invalid/stale)
- CLI invocation (subprocess + JSON output)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".sdd" / "python" / "sdd_scripts" / "validate_plan.py"

sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))
from sdd_scripts import validate_plan as vp  # noqa: E402


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Sample plan fixtures
# ---------------------------------------------------------------------------

V1_LEGACY_PLAN = """---
us: 1-2-Login
family: backend
generated-at: 2026-05-10T14:32:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot
---

# Plan technique backend — 1-2-Login

## Files

- path: src/main/kotlin/auth/AuthService.kt
  operation: create
  layer: Service
  covers_acs: [AC-1, AC-2]

- path: src/main/kotlin/auth/AuthController.kt
  operation: create
  layer: Controller
  covers_acs: [AC-1]

## ACs Coverage Summary
| AC | Files |
|----|-------|
| AC-1 | src/main/kotlin/auth/AuthService.kt, src/main/kotlin/auth/AuthController.kt |
| AC-2 | src/main/kotlin/auth/AuthService.kt |
"""


_SAMPLE_US = """# US 1-2-Login

## Covers
- SFD-1
- BR-2

## Acceptance Criteria

- AC-1: User can login with valid credentials
- AC-2: User receives JWT on successful login
"""


def _v2_plan_with_us_hash(us_hash: str | None = None) -> str:
    actual_hash = us_hash if us_hash is not None else _sha256(_SAMPLE_US)
    return f"""---
us: 1-2-Login
family: backend
generated-at: 2026-05-10T14:32:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot
plan-schema-version: 2
us-hash: sha256:{actual_hash}
capabilities-triggered: auth-azure-ad
strict-ready: true
---

# Plan technique backend — 1-2-Login

## Files

- path: src/main/kotlin/auth/AuthService.kt
  operation: create
  layer: Service
  covers_acs: [AC-1, AC-2]

- path: src/main/kotlin/auth/AuthController.kt
  operation: create
  layer: Controller
  covers_acs: [AC-1]

## ACs Coverage Summary
| AC | Files |
|----|-------|
| AC-1 | src/main/kotlin/auth/AuthService.kt, src/main/kotlin/auth/AuthController.kt |
| AC-2 | src/main/kotlin/auth/AuthService.kt |

## Inline Digest

### Stack §1.3 mapping (kotlin-spring-boot)
- Service → src/main/kotlin/{{app}}/service/
- Controller → src/main/kotlin/{{app}}/controller/

### CLAUDE.md backend (extrait pertinent)
- AppNamespace : com.acme.cms
- Entities scaffoldées : User, Session
"""


V2_MISSING_DIGEST = """---
us: 1-2-Login
family: backend
generated-at: 2026-05-10T14:32:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot
plan-schema-version: 2
us-hash: sha256:abc123
---

# Plan technique backend — 1-2-Login

## Files

- path: src/main/kotlin/auth/AuthService.kt
  operation: create
  layer: Service
  covers_acs: [AC-1]

## ACs Coverage Summary
| AC | Files |
|----|-------|
| AC-1 | src/main/kotlin/auth/AuthService.kt |
"""


PLAN_NO_FRONTMATTER = """# Plan technique backend — 1-2-Login

## Files

- path: src/foo.cs
  operation: create
  layer: Service
  covers_acs: [AC-1]
"""


PLAN_AUGMENT_MISSING_CONTRACT = """---
us: 1-2-Login
family: backend
plan-schema-version: 2
---

# Plan technique backend — 1-2-Login

## Files

- path: src/Program.cs
  operation: augment
  layer: Bootstrap
  covers_acs: [AC-1]
"""


PLAN_FILES_SECTION_MISSING = """---
us: 1-2-Login
family: backend
plan-schema-version: 2
---

# Plan technique backend — 1-2-Login

## Notes
(no Files section)
"""


# ---------------------------------------------------------------------------
# Helper: write fixtures to tempdir and invoke validator
# ---------------------------------------------------------------------------


class _PlanFixture:
    """Context manager producing a tempdir with plan + (optionally) US."""

    def __init__(self, plan_content: str, us_content: str | None = None):
        self.plan_content = plan_content
        self.us_content = us_content
        self.tmp: tempfile.TemporaryDirectory[str] | None = None
        self.plan_path: Path | None = None
        self.us_path: Path | None = None

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.plan_path = root / "plan.back.md"
        self.plan_path.write_text(self.plan_content, encoding="utf-8")
        if self.us_content is not None:
            self.us_path = root / "us.md"
            self.us_path.write_text(self.us_content, encoding="utf-8")
        return self

    def __exit__(self, *exc):
        if self.tmp is not None:
            self.tmp.cleanup()


# ---------------------------------------------------------------------------
# Unit tests — internal helpers
# ---------------------------------------------------------------------------


class TestFrontmatterParsing(unittest.TestCase):
    def test_parses_well_formed_frontmatter(self) -> None:
        parsed = vp.parse_frontmatter(V1_LEGACY_PLAN)
        self.assertIsNotNone(parsed)
        fm, body = parsed
        self.assertEqual(fm["us"], "1-2-Login")
        self.assertEqual(fm["family"], "backend")
        self.assertEqual(fm["stack-backend"], "kotlin-spring-boot")
        self.assertIn("# Plan technique backend", body)
        self.assertNotIn("---", body[:5])  # body starts after closing ---

    def test_missing_frontmatter_returns_none(self) -> None:
        self.assertIsNone(vp.parse_frontmatter(PLAN_NO_FRONTMATTER))

    def test_quoted_values_stripped(self) -> None:
        text = '---\nkey: "quoted value"\n---\n\nbody\n'
        parsed = vp.parse_frontmatter(text)
        self.assertIsNotNone(parsed)
        fm, _ = parsed
        self.assertEqual(fm["key"], "quoted value")


class TestFilesSectionParsing(unittest.TestCase):
    def test_parses_two_create_entries(self) -> None:
        parsed = vp.parse_frontmatter(V1_LEGACY_PLAN)
        self.assertIsNotNone(parsed)
        _, body = parsed
        entries = vp.parse_files_section(body)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].path, "src/main/kotlin/auth/AuthService.kt")
        self.assertEqual(entries[0].operation, "create")
        self.assertEqual(entries[0].layer, "Service")
        self.assertEqual(entries[0].covers_acs, ["AC-1", "AC-2"])

    def test_missing_files_section_returns_empty(self) -> None:
        parsed = vp.parse_frontmatter(PLAN_FILES_SECTION_MISSING)
        self.assertIsNotNone(parsed)
        _, body = parsed
        self.assertEqual(vp.parse_files_section(body), [])

    def test_augment_with_preserves_and_adds(self) -> None:
        plan = (
            "---\nus: 1-1-Foo\nfamily: backend\n---\n\n"
            "## Files\n\n"
            "- path: src/Program.cs\n"
            "  operation: augment\n"
            "  layer: Bootstrap\n"
            "  preserves: [Existing.Configure]\n"
            "  adds: [New.AddAuth]\n"
            "  covers_acs: [AC-1]\n"
        )
        parsed = vp.parse_frontmatter(plan)
        self.assertIsNotNone(parsed)
        _, body = parsed
        entries = vp.parse_files_section(body)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].operation, "augment")
        self.assertEqual(entries[0].preserves, ["Existing.Configure"])
        self.assertEqual(entries[0].adds, ["New.AddAuth"])


class TestInlineListParsing(unittest.TestCase):
    def test_inline_brackets(self) -> None:
        self.assertEqual(vp.parse_inline_list("[a, b, c]"), ["a", "b", "c"])

    def test_no_brackets(self) -> None:
        self.assertEqual(vp.parse_inline_list("a, b, c"), ["a", "b", "c"])

    def test_empty_brackets(self) -> None:
        self.assertEqual(vp.parse_inline_list("[]"), [])

    def test_single_value(self) -> None:
        self.assertEqual(vp.parse_inline_list("[only]"), ["only"])


class TestAcCoverageParsing(unittest.TestCase):
    def test_parses_table(self) -> None:
        parsed = vp.parse_frontmatter(V1_LEGACY_PLAN)
        _, body = parsed  # type: ignore[misc]
        coverage = vp.parse_ac_coverage(body)
        self.assertIn("AC-1", coverage)
        self.assertIn("AC-2", coverage)
        self.assertEqual(len(coverage["AC-1"]), 2)

    def test_us_acs_extraction(self) -> None:
        acs = vp.extract_us_acs(_SAMPLE_US)
        self.assertEqual(acs, ["AC-1", "AC-2"])


# ---------------------------------------------------------------------------
# Integration tests — full validator runs via subprocess
# ---------------------------------------------------------------------------


class TestValidatorIntegration(unittest.TestCase):
    """End-to-end tests invoking the script via subprocess."""

    def _run(self, plan_path: Path, *, strict: bool = False,
             us_path: Path | None = None) -> tuple[int, dict[str, object]]:
        args = [sys.executable, str(SCRIPT), "--plan-path", str(plan_path), "--json"]
        if strict:
            args.append("--strict")
        if us_path is not None:
            args.extend(["--us-path", str(us_path)])
        result = subprocess.run(args, capture_output=True, text=True)
        # JSON on stdout; errors on stderr (3-line ERROR/CAUSE/FIX)
        payload: dict[str, object] = {}
        if result.stdout.strip():
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        return result.returncode, payload

    def test_v1_plan_valid_without_strict(self) -> None:
        """Test 1: V1 legacy plan, no --strict → exit 0 valid."""
        with _PlanFixture(V1_LEGACY_PLAN) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path, strict=False)
            self.assertEqual(code, 0)
            self.assertEqual(payload["result"], "valid")
            self.assertEqual(payload["files_count"], 2)

    def test_v1_plan_with_legacy_strict_flag_is_still_exit_0(self) -> None:
        """Audit M5 (2026-08-29) — `--strict` is a retired no-op.

        This test previously asserted `exit 1` / `result=not_strict_ready`,
        the strict-readiness verdict that gated the `dev-*-strict` agents.
        Those agents were deleted in v7.0.0, so no documented caller passes
        `--strict` and exit 1 was unreachable in production. Strict mode is
        now retired rather than resurrected: the flag stays accepted (an old
        script must not crash) but changes nothing.
        """
        with _PlanFixture(V1_LEGACY_PLAN) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path, strict=True)
            self.assertEqual(code, 0)
            self.assertEqual(payload["result"], "valid")

    def test_legacy_strict_flag_changes_nothing(self) -> None:
        """`--strict` and no-flag must produce byte-identical verdicts."""
        with _PlanFixture(V1_LEGACY_PLAN) as fix:
            assert fix.plan_path
            code_plain, payload_plain = self._run(fix.plan_path, strict=False)
            code_strict, payload_strict = self._run(fix.plan_path, strict=True)
        self.assertEqual(code_plain, code_strict)
        payload_plain.pop("strict_mode", None)
        payload_strict.pop("strict_mode", None)
        self.assertEqual(payload_plain, payload_strict)

    def test_v2_plan_valid(self) -> None:
        """Test 3: V2 plan with matching us-hash + ## Inline Digest → exit 0."""
        v2_plan = _v2_plan_with_us_hash()
        with _PlanFixture(v2_plan, us_content=_SAMPLE_US) as fix:
            assert fix.plan_path and fix.us_path
            code, payload = self._run(fix.plan_path, us_path=fix.us_path)
            self.assertEqual(code, 0, msg=f"errors: {payload.get('errors')}")
            self.assertEqual(payload["result"], "valid")
            self.assertTrue(payload["us_hash_match"])
            self.assertTrue(payload["inline_digest_present"])

    def test_exit_code_1_is_unreachable(self) -> None:
        """Audit M5 — no input may produce exit 1 any more.

        `dev-plan.md` published an exit-1 row that could never occur. The
        row is gone; this locks the contract so it cannot silently return.
        """
        cases = [
            (V1_LEGACY_PLAN, False),
            (V1_LEGACY_PLAN, True),
            (V2_MISSING_DIGEST, False),
            (V2_MISSING_DIGEST, True),
            (_v2_plan_with_us_hash(), False),
        ]
        for content, strict in cases:
            with _PlanFixture(content) as fix:
                assert fix.plan_path
                code, _ = self._run(fix.plan_path, strict=strict)
            self.assertNotEqual(code, 1, f"exit 1 resurfaced (strict={strict})")

    def test_v2_plan_stale_us_hash(self) -> None:
        """Test 4: V2 plan with stale us-hash → exit 2 invalid (PLAN_STALE)."""
        v2_plan = _v2_plan_with_us_hash(us_hash="0" * 64)
        with _PlanFixture(v2_plan, us_content=_SAMPLE_US) as fix:
            assert fix.plan_path and fix.us_path
            code, payload = self._run(fix.plan_path, strict=True, us_path=fix.us_path)
            self.assertEqual(code, 2)
            self.assertEqual(payload["result"], "invalid")
            self.assertFalse(payload["us_hash_match"])
            err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
            self.assertIn("PLAN_STALE", err_codes)

    def test_v2_plan_stale_us_hash_without_strict(self) -> None:
        """Regression for the 2026-06-12 audit fix (M3).

        The staleness check used to live only inside validate_strict(), so a
        stale plan passed exit 0 on the `/dev-run` code path (which invokes the
        validator WITHOUT --strict and expects exit 2 → [PLAN_STALE]). It must
        now be caught regardless of --strict.
        """
        v2_plan = _v2_plan_with_us_hash(us_hash="0" * 64)
        with _PlanFixture(v2_plan, us_content=_SAMPLE_US) as fix:
            assert fix.plan_path and fix.us_path
            code, payload = self._run(fix.plan_path, strict=False, us_path=fix.us_path)
            self.assertEqual(code, 2, "stale plan must be exit 2 even without --strict")
            err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
            self.assertIn("PLAN_STALE", err_codes)
            self.assertFalse(payload["us_hash_match"])

    def test_v2_plan_fresh_us_hash_without_strict_not_stale(self) -> None:
        """Counterpart: a plan whose us-hash matches must NOT be flagged stale."""
        import hashlib
        fresh = hashlib.sha256(_SAMPLE_US.encode("utf-8")).hexdigest()
        v2_plan = _v2_plan_with_us_hash(us_hash=fresh)
        with _PlanFixture(v2_plan, us_content=_SAMPLE_US) as fix:
            assert fix.plan_path and fix.us_path
            code, payload = self._run(fix.plan_path, strict=False, us_path=fix.us_path)
            self.assertIn(code, (0, 1), "fresh plan must not be stale")
            err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
            self.assertNotIn("PLAN_STALE", err_codes)

    def test_plan_no_frontmatter(self) -> None:
        """Test 5: Plan without frontmatter → exit 2 invalid."""
        with _PlanFixture(PLAN_NO_FRONTMATTER) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path, strict=False)
            self.assertEqual(code, 2)
            self.assertEqual(payload["result"], "invalid")
            err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
            self.assertIn("PLAN_NO_FRONTMATTER", err_codes)

    def test_v2_plan_missing_inline_digest_is_a_warning(self) -> None:
        """Test 6: V2 plan without ## Inline Digest → exit 0 + WARN.

        Audit M5 — a missing digest was a *strict-readiness* concern, not a
        correctness one. With strict mode retired it becomes a non-blocking
        warning; the plan stays usable by dev-* in From-Plan classic mode
        (which is exactly what `build-and-loop.md §7.6` already said about
        the old exit 1).
        """
        with _PlanFixture(V2_MISSING_DIGEST) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path)
            self.assertEqual(code, 0)
            self.assertEqual(payload["result"], "valid")
            self.assertFalse(payload["inline_digest_present"])
            warn_codes = [w["code"] for w in payload["warnings"]]  # type: ignore[index]
            self.assertIn("PLAN_DIGEST_ABSENT", warn_codes)

    # --- Audit M6 (2026-08-29) — staleness-unknown must not look fresh ----

    def test_staleness_unverifiable_when_us_path_absent(self) -> None:
        """A declared us-hash with no --us-path must WARN, not pass silently.

        Regression : `validate_staleness` used to `return` bare in this
        branch, so a caller reading exit 0 could not distinguish "provably
        in sync" from "nobody could check". Staleness-unknown must never
        look identical to staleness-confirmed-fresh.
        """
        v2_plan = _v2_plan_with_us_hash()
        with _PlanFixture(v2_plan) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path)  # no --us-path
        self.assertEqual(code, 0, "unverifiable staleness stays non-blocking")
        self.assertIsNone(payload["us_hash_match"])
        warn_codes = [w["code"] for w in payload["warnings"]]  # type: ignore[index]
        self.assertIn("PLAN_STALENESS_UNVERIFIABLE", warn_codes)

    def test_staleness_unverifiable_when_us_file_missing(self) -> None:
        v2_plan = _v2_plan_with_us_hash()
        with _PlanFixture(v2_plan) as fix:
            assert fix.plan_path
            ghost = fix.plan_path.parent / "no-such-us.md"
            code, payload = self._run(fix.plan_path, us_path=ghost)
        self.assertEqual(code, 0)
        self.assertIsNone(payload["us_hash_match"])
        warn_codes = [w["code"] for w in payload["warnings"]]  # type: ignore[index]
        self.assertIn("PLAN_STALENESS_UNVERIFIABLE", warn_codes)

    def test_v1_plan_without_us_hash_warns_unverifiable(self) -> None:
        with _PlanFixture(V1_LEGACY_PLAN) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path)
        self.assertEqual(code, 0)
        warn_codes = [w["code"] for w in payload["warnings"]]  # type: ignore[index]
        self.assertIn("PLAN_STALENESS_UNVERIFIABLE", warn_codes)

    def test_verified_fresh_plan_has_no_unverifiable_warning(self) -> None:
        """The contrast case: a genuinely verified plan must NOT warn."""
        v2_plan = _v2_plan_with_us_hash()
        with _PlanFixture(v2_plan, us_content=_SAMPLE_US) as fix:
            assert fix.plan_path and fix.us_path
            code, payload = self._run(fix.plan_path, us_path=fix.us_path)
        self.assertEqual(code, 0)
        self.assertTrue(payload["us_hash_match"])
        warn_codes = [w["code"] for w in payload["warnings"]]  # type: ignore[index]
        self.assertNotIn("PLAN_STALENESS_UNVERIFIABLE", warn_codes)

    def test_augment_missing_contract(self) -> None:
        """Test 7: augment file without preserves/adds → exit 2 invalid."""
        with _PlanFixture(PLAN_AUGMENT_MISSING_CONTRACT) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path, strict=False)
            self.assertEqual(code, 2)
            err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
            self.assertIn("PLAN_AUGMENT_CONTRACT_MISSING", err_codes)

    def test_files_section_missing(self) -> None:
        """Test 8: Plan without ## Files section → exit 2 invalid."""
        with _PlanFixture(PLAN_FILES_SECTION_MISSING) as fix:
            assert fix.plan_path
            code, payload = self._run(fix.plan_path, strict=False)
            self.assertEqual(code, 2)
            err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
            self.assertIn("PLAN_FILES_SECTION_MISSING", err_codes)

    def test_plan_not_found(self) -> None:
        """Test 9: Plan path doesn't exist → exit 2 invalid PLAN_NOT_FOUND."""
        code, payload = self._run(Path("/nonexistent/plan.back.md"))
        self.assertEqual(code, 2)
        err_codes = [e["code"] for e in payload["errors"]]  # type: ignore[index]
        self.assertIn("PLAN_NOT_FOUND", err_codes)


if __name__ == "__main__":
    unittest.main()
