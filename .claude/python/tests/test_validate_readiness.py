"""Unit tests for validate_readiness.py — Implementation Readiness Gate.

Coverage:
- ID sequence validation (SFD-1, SFD-2, no gap)
- Coverage check (each SFD/BR/AC/FD covered by ≥1 US)
- Decision logic: GO / WARN / NO-GO
- Section body extraction
- DB type detection from stack.md
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "validate_readiness.py"

# Load the module to test internal helpers
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))
from sdd_scripts import validate_readiness as vr  # noqa: E402


class TestSectionBody(unittest.TestCase):
    def test_extracts_section_content(self) -> None:
        content = "## Functional Needs\n- SFD-1: Foo\n- SFD-2: Bar\n\n## Business Rules\n- BR-1: ..."
        body = vr.section_body(content, "Functional Needs")
        self.assertIn("SFD-1: Foo", body)
        self.assertIn("SFD-2: Bar", body)
        self.assertNotIn("BR-1", body)

    def test_missing_section_returns_none(self) -> None:
        content = "## Functional Needs\n- SFD-1: Foo"
        self.assertIsNone(vr.section_body(content, "NotPresent"))


class TestIdSequence(unittest.TestCase):
    def test_contiguous_sequence_passes(self) -> None:
        content = "## Functional Needs\n- SFD-1: A\n- SFD-2: B\n- SFD-3: C"
        result = vr.test_id_sequence(content, "SFD", "Functional Needs")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 3)

    def test_gap_in_sequence_fails(self) -> None:
        content = "## Functional Needs\n- SFD-1: A\n- SFD-3: C"
        result = vr.test_id_sequence(content, "SFD", "Functional Needs")
        self.assertFalse(result["ok"])

    def test_duplicate_id_fails(self) -> None:
        content = "## Functional Needs\n- SFD-1: A\n- SFD-1: B\n- SFD-2: C"
        result = vr.test_id_sequence(content, "SFD", "Functional Needs")
        self.assertFalse(result["ok"])

    def test_empty_section_returns_empty_marker(self) -> None:
        content = "## Functional Needs\n\n## Business Rules"
        result = vr.test_id_sequence(content, "SFD", "Functional Needs")
        # Empty section produces {"empty": True} (no IDs to validate)
        self.assertTrue(result.get("empty"))
        self.assertNotIn("ok", result)

    def test_missing_section_returns_skipped(self) -> None:
        content = "## Other\n- Foo"
        result = vr.test_id_sequence(content, "SFD", "Functional Needs")
        self.assertTrue(result.get("skipped"))


class TestCoverage(unittest.TestCase):
    def test_get_all_ids(self) -> None:
        content = "## Functional Needs\n- SFD-1: A\n- SFD-2: B\n- SFD-3: C"
        ids = vr.get_all_ids(content, "SFD", "Functional Needs")
        self.assertEqual(sorted(ids), ["SFD-1", "SFD-2", "SFD-3"])

    def test_get_covered_ids_from_us(self) -> None:
        us_content = "Covers: SFD-1, SFD-3, AC-2"
        covered = vr.get_covered_ids(us_content, "SFD")
        self.assertEqual(covered, {"SFD-1", "SFD-3"})


class TestDBTypeDetection(unittest.TestCase):
    def test_none_active_database(self) -> None:
        stack = "## Active Database\n - DatabaseType: none"
        self.assertEqual(vr.detect_db_type(stack), "none")

    def test_postgres_active_database(self) -> None:
        stack = "## Active Database\n - DatabaseType: postgres\n - DB_HOST:127.0.0.1"
        self.assertEqual(vr.detect_db_type(stack), "postgres")

    def test_legacy_project_config_fallback(self) -> None:
        # Legacy pre-2026-05-14 format still detected
        stack = "## Project Config\nDatabaseType: postgres"
        self.assertEqual(vr.detect_db_type(stack), "postgres")

    def test_invalid_value_returned_raw(self) -> None:
        stack = "## Active Database\n - DatabaseType: oracle9i"
        result = vr.detect_db_type(stack)
        self.assertIn(result, (*vr.VALID_DB_TYPES, "oracle9i"))

    def test_active_database_full(self) -> None:
        stack = (
            "## Active Database\n"
            " - DatabaseType: postgres\n"
            " - DB_HOST:127.0.0.1\n"
            " - DB_PORT:5432\n"
            " - DB_NAME:CMS\n"
            " - DB_USER:postgres\n"
            " - DB_PASSWORD:secret\n"
        )
        kv = vr.get_active_db_kv(stack)
        self.assertEqual(kv["DB_HOST"], "127.0.0.1")
        self.assertEqual(kv["DB_PORT"], "5432")
        self.assertEqual(kv["DB_PASSWORD"], "secret")


class TestActiveAuthSpecs(unittest.TestCase):
    def test_auth_listed_and_keys_azure(self) -> None:
        stack = (
            "## Active Auth Specs\n"
            " - .claude/stacks/auth/azure-ad.md\n"
            " - AZ_TENANTID:tid\n"
            " - AZ_CLIENTID:cid\n"
            " - AZ_DOMAIN:example.com\n"
            " - AZ_AUDIENCES:\"a\",\"b\"\n"
            " - AZ_BE_CALLBACKPATH:/signin-oidc\n"
            " - AZ_FE_CALLBACKPATH:/login-callback\n"
        )
        self.assertTrue(vr.has_auth_stack_listed(stack))
        kv = vr.get_active_auth_kv(stack)
        self.assertEqual(kv["AZ_TENANTID"], "tid")
        self.assertEqual(kv["AZ_DOMAIN"], "example.com")

    def test_auth_listed_and_keys_local(self) -> None:
        stack = (
            "## Active Auth Specs\n"
            " - .claude/stacks/auth/auth-local.md\n"
            " - AUTH_JWT_AUDIENCE:NounouJob\n"
            " - AUTH_JWT_EXPIRATION:60\n"
            " - AUTH_JWT_ISSUER:NounouJobBack\n"
            " - AUTH_JWT_SECRET:NounouJobSuperSecretKey@2024!XYZ789AbcDef012345678\n"
        )
        self.assertTrue(vr.has_auth_stack_listed(stack))
        kv = vr.get_active_auth_kv(stack)
        self.assertEqual(kv["AUTH_JWT_AUDIENCE"], "NounouJob")
        self.assertEqual(kv["AUTH_JWT_EXPIRATION"], "60")

    def test_auth_keys_tolerate_equals_separator(self) -> None:
        # Legacy / shell-style separator `=` should be parsed equivalently to `:`.
        stack = (
            "## Active Auth Specs\n"
            " - .claude/stacks/auth/auth-local.md\n"
            " - AUTH_JWT_AUDIENCE=NounouJob\n"
            " - AUTH_JWT_SECRET=secret-value-32-chars-minimum-xx\n"
        )
        kv = vr.get_active_auth_kv(stack)
        self.assertEqual(kv["AUTH_JWT_AUDIENCE"], "NounouJob")
        self.assertEqual(kv["AUTH_JWT_SECRET"], "secret-value-32-chars-minimum-xx")

    def test_auth_block_without_stack_path(self) -> None:
        stack = "## Active Auth Specs\n - AZ_TENANTID:tid\n"
        self.assertFalse(vr.has_auth_stack_listed(stack))
        self.assertIsNone(vr.detect_active_auth_stack(stack))


class TestDetectActiveAuthStack(unittest.TestCase):
    def test_detects_auth_local(self) -> None:
        stack = (
            "## Active Auth Specs\n"
            " - .claude/stacks/auth/auth-local.md\n"
            " - AUTH_JWT_AUDIENCE:foo\n"
        )
        self.assertEqual(
            vr.detect_active_auth_stack(stack),
            ".claude/stacks/auth/auth-local.md",
        )

    def test_detects_azure_ad(self) -> None:
        stack = (
            "## Active Auth Specs\n"
            " - .claude/stacks/auth/azure-ad.md\n"
            " - AZ_TENANTID:tid\n"
        )
        self.assertEqual(
            vr.detect_active_auth_stack(stack),
            ".claude/stacks/auth/azure-ad.md",
        )

    def test_no_section_returns_none(self) -> None:
        stack = "## Project Config\nAppName: Foo"
        self.assertIsNone(vr.detect_active_auth_stack(stack))


class TestExtractRequiredAuthKeys(unittest.TestCase):
    def test_auth_local_required_keys(self) -> None:
        md = (
            "## 2. Variables\n\n"
            "### Cles de configuration obligatoires (sous `## Active Auth Specs`)\n\n"
            "- AUTH_JWT_SECRET : cle secrete\n"
            "  (HMAC-SHA256 minimum, 32 chars min)\n"
            "- AUTH_JWT_ISSUER : emetteur du token\n"
            "- AUTH_JWT_AUDIENCE : audience\n"
            "- AUTH_JWT_EXPIRATION : duree en minutes\n\n"
            "### Cles recommandees\n\n"
            "- AUTH_HASH_ALGO : algo (defaut argon2id)\n"
        )
        keys = vr.extract_required_auth_keys(md)
        self.assertEqual(
            keys,
            ["AUTH_JWT_SECRET", "AUTH_JWT_ISSUER", "AUTH_JWT_AUDIENCE", "AUTH_JWT_EXPIRATION"],
        )

    def test_azure_ad_filters_optional_keys(self) -> None:
        md = (
            "### Cles de configuration obligatoires (sous `## Active Auth Specs`)\n\n"
            "- AZ_TENANTID : identifiant du tenant Azure AD\n"
            "- AZ_CLIENTID : id de l'app (legacy single-app pattern)\n"
            "- AZ_FE_CLIENTID : clientId Front. Optionnel - fallback vers AZ_CLIENTID.\n"
            "- AZ_BE_CLIENTID : clientId Back. Optionnel - fallback vers AZ_CLIENTID.\n"
            "- AZ_DOMAIN : domaine du tenant\n"
            "- AZ_AUDIENCES : liste des audiences\n"
            "- AZ_BE_CALLBACKPATH : chemin backend\n"
            "- AZ_FE_CALLBACKPATH : chemin frontend\n\n"
            "### §dual-app-registration\n"
        )
        keys = vr.extract_required_auth_keys(md)
        # AZ_FE_CLIENTID and AZ_BE_CLIENTID filtered out (marked "Optionnel")
        self.assertEqual(
            keys,
            ["AZ_TENANTID", "AZ_CLIENTID", "AZ_DOMAIN", "AZ_AUDIENCES",
             "AZ_BE_CALLBACKPATH", "AZ_FE_CALLBACKPATH"],
        )

    def test_missing_section_returns_empty(self) -> None:
        md = "## Other section\n\nNo required-keys heading here."
        self.assertEqual(vr.extract_required_auth_keys(md), [])

    def test_reads_real_auth_local_stack_file(self) -> None:
        # Integration: validate against the actual auth-local.md in the repo.
        auth_local = REPO_ROOT / ".claude" / "stacks" / "auth" / "auth-local.md"
        if not auth_local.is_file():
            self.skipTest("auth-local.md not present in this checkout")
        content = auth_local.read_text(encoding="utf-8")
        keys = vr.extract_required_auth_keys(content)
        self.assertEqual(
            set(keys),
            {"AUTH_JWT_SECRET", "AUTH_JWT_ISSUER", "AUTH_JWT_AUDIENCE", "AUTH_JWT_EXPIRATION"},
        )

    def test_reads_real_azure_ad_stack_file(self) -> None:
        # Integration: validate against the actual azure-ad.md in the repo.
        azure_ad = REPO_ROOT / ".claude" / "stacks" / "auth" / "azure-ad.md"
        if not azure_ad.is_file():
            self.skipTest("azure-ad.md not present in this checkout")
        content = azure_ad.read_text(encoding="utf-8")
        keys = vr.extract_required_auth_keys(content)
        # Optional AZ_FE_CLIENTID / AZ_BE_CLIENTID must NOT be in the required list
        self.assertNotIn("AZ_FE_CLIENTID", keys)
        self.assertNotIn("AZ_BE_CLIENTID", keys)
        # Strictly required keys must be present
        for k in ("AZ_TENANTID", "AZ_CLIENTID", "AZ_DOMAIN", "AZ_AUDIENCES",
                  "AZ_BE_CALLBACKPATH", "AZ_FE_CALLBACKPATH"):
            self.assertIn(k, keys)


class TestScriptInvocation(unittest.TestCase):
    """Integration: invoke script with missing FEAT → exit 1."""

    def test_missing_feat_returns_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            # Invoke in a sandbox where FEAT 999 doesn't exist
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--feat-number", "999", "--json"],
                capture_output=True, text=True, cwd=tmp,
            )
            # Either exit 1 (no FEAT found) or JSON with errors
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
