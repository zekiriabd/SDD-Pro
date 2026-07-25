"""Tests for sdd_hooks.preflight_reverse_gate — REVERSE-GATE before /sdd-full.

Audit M1-reverse (2026-06-12): a reverse-generated FEAT with confidence !=
high used to reach /sdd-full with no automatic obstacle. This hook enforces
the gate. Tests monkeypatch the project-root resolver + stdin reader so they
run against a tmp workspace (avoids the Windows reparse-point rejection of
tmp dirs by project_root_for_hook).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_hooks import preflight_reverse_gate as gate  # noqa: E402
from sdd_lib.exit_codes import HOOK_ALLOW, HOOK_DENY  # noqa: E402

_REVERSE_HIGH = (
    "---\ngenerated-by: sdd-reverse\nconfidence: high\n---\n"
    "<!-- REVERSE-GATE: confidence=high ; allow-sdd-full=true -->\n# FEAT\n"
)
_REVERSE_MED = (
    "---\ngenerated-by: sdd-reverse\nconfidence: medium\n---\n"
    "<!-- REVERSE-GATE: confidence=medium ; allow-sdd-full=false -->\n# FEAT\n"
)
_REVERSE_LOW = (
    "---\ngenerated-by: sdd-reverse\nconfidence: low\n---\n"
    "<!-- REVERSE-GATE: confidence=low ; allow-sdd-full=false -->\n# FEAT\n"
)
_FORWARD = "---\ngenerated-by: feat-generate\n---\n# FEAT\n"


def _setup(tmp_path: Path, feats: dict[str, str]) -> Path:
    """Create workspace/feats/{name}.md and the script the hook calls."""
    fdir = tmp_path / "workspace" / "feats"
    fdir.mkdir(parents=True)
    for name, body in feats.items():
        (fdir / name).write_text(body, encoding="utf-8")
    return tmp_path


def _run(monkeypatch, tmp_path: Path, skill: str, args: str,
         env: dict[str, str] | None = None) -> int:
    monkeypatch.setattr(gate, "_resolve_project_root", lambda: tmp_path)
    monkeypatch.setattr(gate, "read_hook_input",
                        lambda: {"tool_input": {"skill": skill, "args": args}})
    # The hook resolves its delegate script under the REAL repo (where this
    # test lives), so check_reverse_feat_for_full.py is found. Point CWD there
    # is unnecessary: the script path is built from _resolve_project_root, so
    # we must also place the script under tmp — instead, symlink/copy is heavy.
    # Simpler: the hook builds `root/.claude/python/sdd_reverse_scripts/...`;
    # create a thin pointer dir under tmp that re-uses the real script.
    real_script = _PY_ROOT / "sdd_reverse_scripts" / "check_reverse_feat_for_full.py"
    dest = tmp_path / ".claude" / "python" / "sdd_reverse_scripts"
    dest.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude" / "python" / "sdd_reverse").mkdir(parents=True, exist_ok=True)
    # Copy the whole sdd_reverse package + script so the subprocess imports work.
    import shutil
    if not (dest / "check_reverse_feat_for_full.py").exists():
        shutil.copytree(_PY_ROOT / "sdd_reverse",
                        tmp_path / ".claude" / "python" / "sdd_reverse",
                        dirs_exist_ok=True)
        shutil.copytree(_PY_ROOT / "sdd_reverse_scripts", dest, dirs_exist_ok=True)
    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
    else:
        monkeypatch.delenv("SDD_ALLOW_REVERSE_LOW", raising=False)
    return gate.main()


def test_non_pipeline_skill_is_noop(monkeypatch, tmp_path):
    _setup(tmp_path, {"2-X.md": _REVERSE_LOW})
    assert _run(monkeypatch, tmp_path, "feat-validate", "2") == HOOK_ALLOW


def test_reverse_high_allowed(monkeypatch, tmp_path):
    _setup(tmp_path, {"1-X.md": _REVERSE_HIGH})
    assert _run(monkeypatch, tmp_path, "sdd-full", "1") == HOOK_ALLOW


def test_reverse_medium_blocked(monkeypatch, tmp_path):
    _setup(tmp_path, {"2-X.md": _REVERSE_MED})
    assert _run(monkeypatch, tmp_path, "sdd-full", "2") == HOOK_DENY


def test_reverse_low_blocked(monkeypatch, tmp_path):
    _setup(tmp_path, {"3-X.md": _REVERSE_LOW})
    assert _run(monkeypatch, tmp_path, "dev-run", "3") == HOOK_DENY


def test_reverse_low_bypass_allows(monkeypatch, tmp_path):
    _setup(tmp_path, {"3-X.md": _REVERSE_LOW})
    assert _run(monkeypatch, tmp_path, "sdd-full", "3",
                env={"SDD_ALLOW_REVERSE_LOW": "1"}) == HOOK_ALLOW


def test_forward_feat_allowed(monkeypatch, tmp_path):
    _setup(tmp_path, {"4-X.md": _FORWARD})
    assert _run(monkeypatch, tmp_path, "sdd-full", "4") == HOOK_ALLOW


def test_feat_not_found_fail_open(monkeypatch, tmp_path):
    _setup(tmp_path, {"1-X.md": _REVERSE_LOW})
    assert _run(monkeypatch, tmp_path, "sdd-full", "9") == HOOK_ALLOW


def test_no_feat_number_in_args_fail_open(monkeypatch, tmp_path):
    _setup(tmp_path, {"1-X.md": _REVERSE_LOW})
    assert _run(monkeypatch, tmp_path, "sdd-full", "") == HOOK_ALLOW
