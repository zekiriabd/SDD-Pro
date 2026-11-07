"""Heredoc bodies are SCANNED by block_env_bypass (audit sécurité 2026-11).

Historique : l'audit 2026-06-07 Sprint 3-5 avait introduit un strip des corps
de heredoc pour éviter un faux positif sur les messages de commit qui
documentent `SDD_ALLOW_FORCE=1`. Mais bash EXÉCUTE un heredoc passé à un
interpréteur (`bash <<EOF … SDD_ALLOW_X=1 … EOF`) : le strip ouvrait un
contournement trivial. Il est retiré ; le prix assumé est qu'un message de
commit en heredoc mentionnant une assignation protégée est refusé —
`git commit -F <fichier>` reste disponible.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))

from sdd_hooks import block_env_bypass as beb  # noqa: E402
from sdd_hooks.block_env_bypass import _matches_bypass  # noqa: E402

PROTECTED_VAR = "SDD_" + "ALLOW_" + "FORCE"


def test_strip_heredocs_helper_is_gone():
    assert not hasattr(beb, "_strip_heredocs")


def test_heredoc_executed_by_bash_is_flagged():
    cmd = f"bash <<'EOF'\n{PROTECTED_VAR}=1 claude /sdd-full 1\nEOF"
    assert _matches_bypass(cmd) is not None


def test_heredoc_commit_message_with_assignment_is_flagged():
    cmd = (
        f"""git commit -m "$(cat <<'EOF'
docs: {PROTECTED_VAR}=1 pour les cas légitimes
EOF
)" """
    )
    assert _matches_bypass(cmd) is not None


def test_heredoc_mentioning_name_without_assignment_is_allowed():
    cmd = f"cat <<'EOF'\nla variable {PROTECTED_VAR} se positionne dans le shell parent\nEOF"
    assert _matches_bypass(cmd) is None


def test_real_export_after_heredoc_still_flagged():
    cmd = f"cat <<'EOF'\ndocs only\nEOF\nexport {PROTECTED_VAR}=1"
    assert _matches_bypass(cmd) is not None


def test_empty_and_clean():
    assert _matches_bypass("") is None
    assert _matches_bypass("ls -la") is None
    assert _matches_bypass("cat <<'EOF'\nhello world\nEOF") is None
