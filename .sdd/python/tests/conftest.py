"""pytest auto-discovery: ensure `.sdd/python/` is on sys.path + isolate console.db.

Pytest imports this file before any test collection. It guarantees
that `from sdd_scripts.X import Y` works regardless of pytest's cwd
or invocation mode.

Audit « fiabilité des données et des états » (2026-11-07) — **isolation de
la base runtime** : la suite écrivait dans `workspace/db/console.db`
(`gates` 49 → 56 lignes, `token_usage` +2 après un simple `pytest`), parce que
`gate_decide.py` « mirrorait » dans `connect()` → `default_db_path()` même
quand le test isolait `status.json`. La fixture autouse `_isolate_console_db`
pointe `$SDD_CONSOLE_DB_PATH` (honoré par `sdd_lib.paths.console_db_path`)
vers un fichier sous `tmp_path` pour CHAQUE test — y compris les tests
subprocess, qui héritent de `os.environ`.

Mode `fallback` (`$SDD_CONSOLE_DB_PATH_MODE=fallback`, posé ici) : la
redirection ne s'applique QUE si la résolution par défaut tomberait sur la
base runtime du vrai dépôt. Les tests déjà isolés par un faux repo
(`$SDD_REPO_ROOT`, `repo_root` mocké, `cwd=fake_repo`) gardent leur
`<fake>/workspace/db/console.db` et leurs assertions de chemin. Hors pytest,
la variable seule (mode `override`) gagne toujours.

Garde : `test_console_db_isolation.py` vérifie que `default_db_path()` est
sous tmp pendant les tests ; la fin de session compare mtime/taille de la
base runtime et émet un WARN (pas un FAIL : les hooks d'une session Claude
Code vivante écrivent légitimement dans cette base pendant que pytest tourne).

Même contrat pour la **piste d'audit** `workspace/.sys/.audit/` (audit
2026-11-07 : `pre-write-lint.log` recevait « MyApp/Service.kt »,
`env-bypass.jsonl` des lots de commandes factices) : `$SDD_AUDIT_DIR` en mode
`fallback`, honoré par `sdd_lib.paths.audit_dir_path` — point d'entrée unique
de tous les writers d'audit.
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# Audit encodage (2026-11-07) : sous Windows, un script Python lancé en
# sous-processus écrit sur un pipe dans l'encodage locale (cp1252) sauf s'il
# reconfigure stdout — d'où des sorties mi-UTF-8 mi-cp1252 et des
# `UnicodeDecodeError` dans les threads lecteurs de `subprocess`. Le mode UTF-8
# de Python (PEP 540), hérité par chaque sous-processus via `os.environ`, aligne
# tous les enfants sur UTF-8 — cohérent avec le `encoding="utf-8"` explicite
# des appelants.
os.environ.setdefault("PYTHONUTF8", "1")

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

CONSOLE_DB_ENV = "SDD_CONSOLE_DB_PATH"
CONSOLE_DB_MODE_ENV = "SDD_CONSOLE_DB_PATH_MODE"
AUDIT_DIR_ENV = "SDD_AUDIT_DIR"
AUDIT_DIR_MODE_ENV = "SDD_AUDIT_DIR_MODE"
_RUNTIME_DB = _PY_ROOT.parent.parent / "workspace" / "db" / "console.db"
_RUNTIME_AUDIT = _PY_ROOT.parent.parent / "workspace" / ".sys" / ".audit"


def _db_signature(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _audit_signature(path: Path) -> dict[str, tuple[int, int]]:
    try:
        return {f.name: (f.stat().st_mtime_ns, f.stat().st_size)
                for f in path.iterdir() if f.is_file()}
    except OSError:
        return {}


@pytest.fixture(autouse=True)
def _isolate_console_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Relocate console.db under tmp for every test (autouse, function scope)."""
    db_path = tmp_path / "_sdd_console_db" / "console.db"
    monkeypatch.setenv(CONSOLE_DB_ENV, str(db_path))
    monkeypatch.setenv(CONSOLE_DB_MODE_ENV, "fallback")
    return db_path


@pytest.fixture(autouse=True)
def _isolate_audit_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Relocate `workspace/.sys/.audit/` under tmp for every test (autouse)."""
    audit = tmp_path / "_sdd_audit"
    monkeypatch.setenv(AUDIT_DIR_ENV, str(audit))
    monkeypatch.setenv(AUDIT_DIR_MODE_ENV, "fallback")
    return audit


@pytest.fixture()
def console_db_under_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt-out : laisse `default_db_path()` suivre `$SDD_REPO_ROOT` / repo_root().

    À utiliser par les tests qui assertent le chemin `<fake_repo>/workspace/db/
    console.db`. Le faux repo vit lui-même sous tmp, l'isolation est conservée.
    """
    monkeypatch.delenv(CONSOLE_DB_ENV, raising=False)
    monkeypatch.delenv(CONSOLE_DB_MODE_ENV, raising=False)


@pytest.fixture(scope="session", autouse=True)
def _runtime_console_db_guard():
    """Session-level drift watch on the runtime console.db + audit dir (WARN only)."""
    before = _db_signature(_RUNTIME_DB)
    audit_before = _audit_signature(_RUNTIME_AUDIT)
    yield
    after = _db_signature(_RUNTIME_DB)
    audit_after = _audit_signature(_RUNTIME_AUDIT)
    if os.environ.get("SDD_RUNTIME_DB_GUARD_SILENT") == "1":
        return
    if before != after:
        warnings.warn(
            f"[SDD_RUNTIME_DB_DRIFT] {_RUNTIME_DB} a changé pendant la session "
            f"pytest ({before} → {after}). Soit un test contourne "
            f"${CONSOLE_DB_ENV}, soit un hook Claude Code a écrit en parallèle.",
            stacklevel=1,
        )
    changed = sorted(n for n in set(audit_before) | set(audit_after)
                     if audit_before.get(n) != audit_after.get(n))
    if changed:
        warnings.warn(
            f"[SDD_RUNTIME_AUDIT_DRIFT] {_RUNTIME_AUDIT} a changé pendant la "
            f"session pytest ({', '.join(changed)}). Soit un test contourne "
            f"${AUDIT_DIR_ENV}, soit un hook Claude Code a écrit en parallèle.",
            stacklevel=1,
        )
