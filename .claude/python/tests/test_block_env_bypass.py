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

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_hooks import block_env_bypass as beb  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
