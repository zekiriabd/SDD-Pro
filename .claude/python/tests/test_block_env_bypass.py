"""Unit tests for sdd_hooks/block_env_bypass.py.

Coverage:
- Matrix of bypass patterns (case, quotes, whitespace, POSIX/PowerShell/Windows)
- Clean commands pass through
- Empty/malformed payload doesn't crash
- Set-Variable / Set-Item / setx variants caught
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from unittest.mock import patch

import pytest

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_hooks import block_env_bypass as beb  # noqa: E402

# Smoke marker (audit CTO 2026-06-07) — env-bypass detection is the last
# defense against SDD_ALLOW_* / SDD_DISABLE_* exports that would unlock
# cost-cap, multistack, untested-combo gates. Regression here = silent
# damage. Gated by `framework_smoke -m smoke`.
pytestmark = pytest.mark.smoke


def _run_with_command(command: str) -> int:
    """Inject a bash payload via stdin and call hook main()."""
    payload = json.dumps({"tool_input": {"command": command}})
    stdin = io.StringIO(payload)
    with patch.object(sys, "stdin", stdin):
        return beb.main()


class TestBlockEnvBypass(unittest.TestCase):
    # ── Should DENY ──
    def test_posix_export_uppercase(self):
        self.assertEqual(_run_with_command("export SDD_ALLOW_FORCE=1"), 2)

    def test_posix_export_mixed_case(self):
        self.assertEqual(_run_with_command("export SdD_AlLoW_FoRCe=1"), 2)

    def test_inline_assignment(self):
        self.assertEqual(_run_with_command("SDD_ALLOW_FORCE=1 some-cmd"), 2)

    def test_inline_assignment_quoted_value(self):
        self.assertEqual(_run_with_command('SDD_ALLOW_FORCE="1" some-cmd'), 2)

    def test_inline_assignment_single_quoted(self):
        self.assertEqual(_run_with_command("SDD_DISABLE_COST_CAP='1' some-cmd"), 2)

    def test_powershell_env(self):
        self.assertEqual(_run_with_command('$env:SDD_ALLOW_FORCE = "1"'), 2)

    def test_powershell_env_no_quotes(self):
        self.assertEqual(_run_with_command("$env:SDD_DISABLE_COST_CAP = 1"), 2)

    def test_setx_windows(self):
        self.assertEqual(_run_with_command("setx SDD_ALLOW_FORCE 1"), 2)

    def test_setx_disable(self):
        self.assertEqual(_run_with_command("setx SDD_DISABLE_COST_CAP 1"), 2)

    def test_set_variable_powershell(self):
        self.assertEqual(_run_with_command('Set-Variable -Name env:SDD_ALLOW_FORCE "1"'), 2)

    def test_nested_in_bash_c(self):
        self.assertEqual(
            _run_with_command("bash -c 'export SDD_ALLOW_FORCE=1 && echo done'"), 2
        )

    def test_after_semicolon(self):
        self.assertEqual(_run_with_command("ls; SDD_ALLOW_FORCE=1 cmd"), 2)

    def test_after_pipe(self):
        # ALLOWED — `&` and `|` are command separators but inline NAME=val
        # after a pipe is still unsetting; matches the bypass regex.
        self.assertEqual(_run_with_command("echo x | SDD_ALLOW_FORCE=1 cmd"), 2)

    # ── Should ALLOW ──
    def test_clean_ls(self):
        self.assertEqual(_run_with_command("ls -la"), 0)

    def test_reading_envvar_ok(self):
        # Reading or printing the var is allowed, only SETTING is blocked.
        self.assertEqual(_run_with_command("echo $SDD_ALLOW_FORCE"), 0)

    def test_unrelated_envvar(self):
        self.assertEqual(_run_with_command("export PATH=/usr/local/bin:$PATH"), 0)

    def test_unrelated_setx(self):
        self.assertEqual(_run_with_command("setx MY_VAR foo"), 0)

    def test_empty_command(self):
        self.assertEqual(_run_with_command(""), 0)

    def test_command_without_assignment(self):
        # Mentioning the var name without `=` is OK
        self.assertEqual(_run_with_command("grep SDD_ALLOW_FORCE settings.json"), 0)

    def test_malformed_payload(self):
        with patch.object(sys, "stdin", io.StringIO("not-json{")):
            rc = beb.main()
        self.assertEqual(rc, 0)  # graceful degradation

    def test_payload_without_command(self):
        with patch.object(sys, "stdin", io.StringIO('{"tool_input": {}}')):
            rc = beb.main()
        self.assertEqual(rc, 0)


class TestSecretMasking(unittest.TestCase):
    """v7.0.1 audit P1 v2 (2026-06-08) — secret masking in audit log.

    `_mask_secrets()` replaces values of PASSWORD/SECRET/TOKEN/KEY-like
    assignments with `***` before they're persisted to env-bypass.jsonl.
    Conservative : key NAME preserved for forensics, only VALUE masked.
    """

    def test_mask_password_unquoted(self):
        out = beb._mask_secrets("export DB_PASSWORD=hunter2 cmd")
        self.assertIn("DB_PASSWORD=***", out)
        self.assertNotIn("hunter2", out)

    def test_mask_token_quoted(self):
        out = beb._mask_secrets('export AUTH_TOKEN="abcd-1234-secret" cmd')
        self.assertIn('AUTH_TOKEN="***"', out)
        self.assertNotIn("abcd-1234-secret", out)

    def test_mask_api_key_mixed_case(self):
        out = beb._mask_secrets("Api_Key=xyz123 cmd")
        self.assertIn("Api_Key=***", out)
        self.assertNotIn("xyz123", out)

    def test_mask_jwt_secret(self):
        out = beb._mask_secrets("AUTH_JWT_SECRET='supersecret' cmd")
        self.assertIn("AUTH_JWT_SECRET='***'", out)
        self.assertNotIn("supersecret", out)

    def test_no_mask_when_no_secret(self):
        out = beb._mask_secrets("export PATH=/usr/bin:$PATH echo hello")
        # PATH is not a secret pattern — preserved
        self.assertIn("PATH=/usr/bin:$PATH", out)

    def test_mask_preserves_sdd_allow(self):
        # SDD_ALLOW_* is the protected name we're auditing — should NOT be masked
        # (we want to see WHICH bypass var was attempted in the audit log).
        out = beb._mask_secrets("SDD_ALLOW_FORCE=1 cmd")
        self.assertIn("SDD_ALLOW_FORCE=1", out)

    def test_mask_multiple_secrets_one_line(self):
        out = beb._mask_secrets(
            "DB_PASSWORD=secret1 AUTH_TOKEN=secret2 SDD_ALLOW_FORCE=1 cmd"
        )
        self.assertIn("DB_PASSWORD=***", out)
        self.assertIn("AUTH_TOKEN=***", out)
        self.assertIn("SDD_ALLOW_FORCE=1", out)  # not masked
        self.assertNotIn("secret1", out)
        self.assertNotIn("secret2", out)


class TestBlockEnvBypassP0V2Vectors(unittest.TestCase):
    """v7.0.1 audit P0 v2 (2026-06-08) — 8 nouveaux vecteurs bypass.

    Audit v2 sécurité a identifié 8 vecteurs non couverts par v7.0.0 :
      1. `env VAR=val cmd` (env-as-prefix POSIX)
      2. `eval "$(echo VAR=val cmd)"` (eval expansion)
      3. `source script.sh` containing VAR=val
      4. `printf 'VAR=val\\n...' | bash`
      5. `IFS=; bash -c "VAR=val cmd"` (IFS hack)
      6. `New-Item env:VAR -Value 1` (PowerShell)
      7. `[Environment]::SetEnvironmentVariable("VAR", "1")` (PowerShell .NET API)
      8. `Set-Item env:VAR 1` (sans -Name, ne matchait pas v1)

    Tous DOIVENT être bloqués (exit 2).
    """

    def test_env_prefix_posix(self):
        # `env VAR=val cmd` — env tool sets var inline for subprocess
        self.assertEqual(_run_with_command("env SDD_ALLOW_FORCE=1 claude /sdd-full 1"), 2)

    def test_env_prefix_with_flags(self):
        # `env -i SDD_ALLOW_FORCE=1 cmd` (with flags)
        self.assertEqual(_run_with_command("env -i SDD_ALLOW_FORCE=1 cmd"), 2)

    def test_eval_with_protected_var(self):
        # eval-based bypass : the eval'd string sets the protected var
        self.assertEqual(
            _run_with_command('eval "SDD_ALLOW_FORCE=1 cmd"'), 2
        )

    def test_eval_with_subshell(self):
        # `eval "$(echo SDD_ALLOW_X=1 cmd)"`
        self.assertEqual(
            _run_with_command('eval "$(echo SDD_ALLOW_FORCE=1 cmd)"'), 2
        )

    def test_printf_pipe_to_eval(self):
        # printf with VAR=val piped to bash/eval
        self.assertEqual(
            _run_with_command("printf 'SDD_ALLOW_FORCE=1\\nclaude\\n'"), 2
        )

    def test_bash_c_with_protected_var(self):
        # `IFS=; bash -c "VAR=val cmd"` — the bash -c branch catches this
        self.assertEqual(
            _run_with_command('IFS=; bash -c "SDD_ALLOW_FORCE=1 claude /sdd-full 1"'), 2
        )

    def test_new_item_env_powershell(self):
        # `New-Item env:VAR -Value 1`
        self.assertEqual(
            _run_with_command("New-Item env:SDD_ALLOW_FORCE -Value 1"), 2
        )

    def test_powershell_dotnet_setenvvar(self):
        # `[Environment]::SetEnvironmentVariable("VAR", "1")`
        self.assertEqual(
            _run_with_command('[Environment]::SetEnvironmentVariable("SDD_ALLOW_FORCE", "1")'),
            2,
        )

    def test_powershell_dotnet_setenvvar_system_prefix(self):
        # `[System.Environment]::SetEnvironmentVariable(...)` (avec prefix System.)
        self.assertEqual(
            _run_with_command('[System.Environment]::SetEnvironmentVariable("SDD_DISABLE_COST_CAP", "1")'),
            2,
        )

    # ── Should still ALLOW (don't false-positive) ──

    def test_env_command_without_protected_var(self):
        # `env` invocation without protected var is OK
        self.assertEqual(_run_with_command("env PATH=/usr/bin echo hello"), 0)

    def test_eval_clean(self):
        # eval without protected var
        self.assertEqual(_run_with_command('eval "echo hello"'), 0)

    def test_printf_clean(self):
        # printf without protected var
        self.assertEqual(_run_with_command("printf 'hello\\n'"), 0)


if __name__ == "__main__":
    unittest.main()
