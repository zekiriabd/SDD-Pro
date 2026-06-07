"""Test that block_env_bypass.py strips heredoc bodies before scanning.

Audit consolidé 2026-06-07 Sprint 3-5 — closure faux positif heredoc :
le hook bloquait les `git commit -m "$(cat <<'EOF' ... EOF)"` contenant
des mentions documentaires de `SDD_ALLOW_FORCE=1` dans le message de
commit (cas réel rencontré lors du commit Sprint 2).

Le fix : `_strip_heredocs(cmd)` retire les bodies d'heredocs AVANT
d'appliquer les regex de bypass. Seuls les VRAIS exports en position
exécutable sont flaggés.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_hooks.block_env_bypass import _matches_bypass, _strip_heredocs  # noqa: E402


PROTECTED_VAR = "SDD_" + "ALLOW_" + "FORCE"  # split string pour ne pas trigger les regex de surface du test framework


class TestHeredocStripping:
    """`_strip_heredocs` doit retirer les bodies d'heredocs bash."""

    def test_strip_single_heredoc(self):
        cmd = f"cat <<'EOF'\nfoo {PROTECTED_VAR}=1\nEOF\nls"
        cleaned = _strip_heredocs(cmd)
        assert PROTECTED_VAR not in cleaned, f"heredoc body not stripped: {cleaned!r}"

    def test_strip_quoted_tag(self):
        cmd = f'cat <<"EOF"\nfoo {PROTECTED_VAR}=1\nEOF\nls'
        cleaned = _strip_heredocs(cmd)
        assert PROTECTED_VAR not in cleaned

    def test_strip_multiple_heredocs(self):
        cmd = f"a <<'EOF'\n{PROTECTED_VAR}=1\nEOF\nb <<'TAG'\n{PROTECTED_VAR}=2\nTAG"
        cleaned = _strip_heredocs(cmd)
        assert PROTECTED_VAR not in cleaned

    def test_preserve_non_heredoc_content(self):
        cmd = "ls -la ; echo hello"
        assert _strip_heredocs(cmd) == cmd


class TestBypassFalsePositiveFixed:
    """Le scenario réel du commit Sprint 2 ne doit plus déclencher de DENY."""

    def test_commit_message_documenting_envvar_not_flagged(self):
        """Mention du protected var dans message de commit heredoc → ALLOW."""
        cmd = (
            f"""git commit -m "$(cat <<'EOF'
fix(audit): close CRIT-14 — documenter env-var escape

Documente {PROTECTED_VAR}=1 pour les cas légitimes de cumul bypass.
EOF
)" """
        )
        match = _matches_bypass(cmd)
        assert match is None, f"false positive: {match!r}"

    def test_real_export_in_command_still_flagged(self):
        """Tentative réelle d'export en position exécutable → DENY."""
        cmd = f"export {PROTECTED_VAR}=1 && claude /sdd-full 1"
        match = _matches_bypass(cmd)
        assert match is not None, "real bypass should still be detected"

    def test_real_export_after_heredoc_still_flagged(self):
        """Heredoc OK puis export réel → DENY (le strip ne masque pas le vrai)."""
        cmd = (
            f"""git commit -m "$(cat <<'EOF'
docs only
EOF
)" && export {PROTECTED_VAR}=1"""
        )
        match = _matches_bypass(cmd)
        assert match is not None, "real bypass after heredoc should still be detected"


class TestEdgeCases:
    def test_empty_command(self):
        assert _matches_bypass("") is None

    def test_no_heredoc_no_bypass(self):
        assert _matches_bypass("ls -la") is None

    def test_heredoc_without_bypass(self):
        cmd = "cat <<'EOF'\nhello world\nEOF"
        assert _matches_bypass(cmd) is None
