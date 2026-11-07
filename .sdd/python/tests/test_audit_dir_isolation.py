"""Isolation de la piste d'audit `workspace/.sys/.audit/` (audit 2026-11-07).

Pré-fix, la suite pytest écrivait dans la piste d'audit de PRODUCTION :
`pre-write-lint.log` (« workspace/src/MyApp/Service.kt »), `env-bypass.jsonl`
(lots de commandes factices). Contrat épinglé ici :
  - `audit_dir_path()` honore `$SDD_AUDIT_DIR` (override / fallback) ;
  - le conftest redirige la piste d'audit réelle vers tmp pour chaque test ;
  - un hook lancé en subprocess (env hérité) écrit sous tmp, jamais dans le dépôt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import paths  # noqa: E402

REPO_ROOT = _PY_ROOT.parent.parent


def test_runtime_audit_dir_redirected_under_tmp(_isolate_audit_dir: Path):
    resolved = paths.audit_dir_path(REPO_ROOT)
    assert resolved == _isolate_audit_dir.resolve()
    assert resolved != paths.runtime_audit_dir()


def test_fallback_keeps_fake_repo_audit_dir(tmp_path: Path):
    fake = tmp_path / "fake_repo"
    (fake / "workspace").mkdir(parents=True)
    assert paths.audit_dir_path(fake) == fake / "workspace" / ".sys" / ".audit"


def test_workspace_argument(tmp_path: Path):
    ws = tmp_path / "ws"
    assert paths.audit_dir_path(workspace=ws) == ws / ".sys" / ".audit"


def test_override_mode_always_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "elsewhere"
    monkeypatch.setenv(paths.AUDIT_DIR_ENV, str(target))
    monkeypatch.setenv(paths.AUDIT_DIR_MODE_ENV, "override")
    fake = tmp_path / "fake_repo"
    (fake / "workspace").mkdir(parents=True)
    assert paths.audit_dir_path(fake) == target.resolve()


def test_unset_env_resolves_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(paths.AUDIT_DIR_ENV, raising=False)
    monkeypatch.delenv(paths.AUDIT_DIR_MODE_ENV, raising=False)
    assert paths.audit_dir_path(REPO_ROOT) == paths.workspace_root(REPO_ROOT) / ".sys" / ".audit"


def test_hook_subprocess_writes_under_tmp(_isolate_audit_dir: Path):
    """pre_write_lint lancé depuis le vrai dépôt : le log atterrit sous tmp."""
    runtime_log = REPO_ROOT / "workspace" / ".sys" / ".audit" / "pre-write-lint.log"
    before = runtime_log.stat().st_size if runtime_log.exists() else None
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "workspace/src/MyApp/Service.kt",
            "content": "val x = something!!",
        },
    }
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    subprocess.run(
        [sys.executable, str(_PY_ROOT / "sdd_hooks" / "pre_write_lint.py")],
        input=json.dumps(payload), env=env, cwd=REPO_ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30,
    )
    after = runtime_log.stat().st_size if runtime_log.exists() else None
    assert after == before, "le hook a écrit dans la piste d'audit de production"
    assert (_isolate_audit_dir / "pre-write-lint.log").exists()
