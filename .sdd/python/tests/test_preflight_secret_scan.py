"""Unit tests for sdd_hooks/preflight_secret_scan.py (audit R5, 2026-07-26)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_hooks import preflight_secret_scan as psc  # noqa: E402


class TestReadActiveProvider(unittest.TestCase):
    def _make(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        try:
            f.write(content)
        finally:
            f.close()
        self.addCleanup(lambda: os.unlink(f.name))
        return Path(f.name)

    def test_openai_provider(self):
        p = self._make("## Active Model Provider\nProvider: openai\n")
        self.assertEqual(psc._read_active_provider(p), "openai")

    def test_missing_section_returns_none(self):
        p = self._make("## Something Else\nfoo: bar\n")
        self.assertIsNone(psc._read_active_provider(p))

    def test_case_normalization(self):
        p = self._make("## Active Model Provider\nProvider: Google\n")
        self.assertEqual(psc._read_active_provider(p), "google")

    def test_anthropic_default(self):
        p = self._make("## Active Model Provider\nProvider: anthropic\n")
        self.assertEqual(psc._read_active_provider(p), "anthropic")


class TestStackHasSecrets(unittest.TestCase):
    def _make(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        )
        try:
            f.write(content)
        finally:
            f.close()
        self.addCleanup(lambda: os.unlink(f.name))
        return Path(f.name)

    def test_finds_db_password(self):
        p = self._make("DB_PASSWORD=supersecret\n")
        self.assertIn("DB_PASSWORD", psc._stack_has_secrets(p))

    def test_finds_jwt_and_db(self):
        p = self._make("DB_PASSWORD=x\nAUTH_JWT_SECRET=y\n")
        s = psc._stack_has_secrets(p)
        self.assertIn("DB_PASSWORD", s)
        self.assertIn("AUTH_JWT_SECRET", s)

    def test_ignores_placeholder_values(self):
        p = self._make("DB_PASSWORD=TODO\nAUTH_JWT_SECRET=<REPLACE_ME>\n")
        self.assertEqual(psc._stack_has_secrets(p), ())

    def test_ignores_empty_values(self):
        # Regex requires \S so empty values never match.
        p = self._make("DB_PASSWORD=\nAUTH_JWT_SECRET=  \n")
        self.assertEqual(psc._stack_has_secrets(p), ())

    def test_ignores_angle_placeholders(self):
        p = self._make("DB_PASSWORD=<db-password-here>\n")
        self.assertEqual(psc._stack_has_secrets(p), ())

    def test_yaml_style_assignment(self):
        p = self._make("DB_PASSWORD: realsecret\n")
        self.assertIn("DB_PASSWORD", psc._stack_has_secrets(p))

    def test_no_secrets_returns_empty(self):
        p = self._make("## Random\nfoo=bar\n")
        self.assertEqual(psc._stack_has_secrets(p), ())


class TestLeakRiskProvidersRegistry(unittest.TestCase):
    def test_openai_google_moonshot_are_risk(self):
        for p in ("openai", "google", "moonshot"):
            self.assertIn(p, psc._LEAK_RISK_PROVIDERS)

    def test_anthropic_is_not_risk(self):
        # Anthropic = reference contract of SDD_Pro.
        self.assertNotIn("anthropic", psc._LEAK_RISK_PROVIDERS)


class TestSecretKeysRegistry(unittest.TestCase):
    def test_stack_md_canonical_keys_listed(self):
        # These are the keys documented in CLAUDE.md §9 and
        # library-and-stack.md §B. Any drift = regression.
        for key in ("DB_PASSWORD", "AUTH_JWT_SECRET", "AZ_CLIENTSECRET",
                    "SMTP_PASSWORD"):
            self.assertIn(key, psc._SECRET_KEYS)


class TestMainBypass(unittest.TestCase):
    """Bypass env var must short-circuit the hook."""

    def test_bypass_env_var_returns_allow(self):
        prev = os.environ.get("SDD_ALLOW_SECRET_TO_PROVIDER")
        try:
            os.environ["SDD_ALLOW_SECRET_TO_PROVIDER"] = "1"
            # No payload on stdin — read_hook_input returns None → ALLOW.
            with mock.patch("sdd_hooks.preflight_secret_scan.read_hook_input",
                            return_value=None):
                rc = psc.main()
            self.assertEqual(rc, 0)
        finally:
            if prev is None:
                os.environ.pop("SDD_ALLOW_SECRET_TO_PROVIDER", None)
            else:
                os.environ["SDD_ALLOW_SECRET_TO_PROVIDER"] = prev


class TestMainAllowsOnSafeCombo(unittest.TestCase):
    def test_no_stack_md_allows(self):
        with mock.patch("sdd_hooks.preflight_secret_scan._resolve_stack_md",
                        return_value=None):
            with mock.patch("sdd_hooks.preflight_secret_scan.read_hook_input",
                            return_value={"tool_input": {"subagent_type": "po"}}):
                with mock.patch(
                    "sdd_hooks.preflight_secret_scan.get_subagent_type",
                    return_value="po",
                ):
                    rc = psc.main()
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
