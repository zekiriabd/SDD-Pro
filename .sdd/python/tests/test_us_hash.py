"""Tests sdd_lib.us_hash — fraîcheur des plans insensible au statut de l'US (correctif 2026-11-13).

Défaut : set_us_status.py réécrit `Status:` (Ready → InProgress → Review) et rendait les plans
`[PLAN_STALE]` alors que le contenu fonctionnel de l'US n'avait pas changé.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sdd_lib.us_hash import legacy_file_hash, us_content_hash, us_hash_candidates  # noqa: E402

SCRIPT = REPO_ROOT / ".sdd" / "python" / "sdd_scripts" / "validate_plan.py"

US_READY = """# US-1: Login

ID: 1-1-Login
Parent FEAT: 1-Auth
Status: Ready

## Acceptance Criteria
- AC-1: User can login
"""


def _with_status(text: str, status: str) -> str:
    return text.replace("Status: Ready", f"Status: {status}")


def test_status_change_keeps_content_hash() -> None:
    for status in ("Draft", "InProgress", "Review", "Done"):
        assert us_content_hash(_with_status(US_READY, status)) == us_content_hash(US_READY)


def test_functional_change_changes_content_hash() -> None:
    changed = US_READY.replace("User can login", "User can login with MFA")
    assert us_content_hash(changed) != us_content_hash(US_READY)


def test_crlf_status_line_is_neutralised_too() -> None:
    crlf = US_READY.replace("\n", "\r\n")
    assert us_content_hash(_with_status(crlf, "Review")) == us_content_hash(crlf)


def test_candidates_include_legacy_raw_hash() -> None:
    assert us_hash_candidates(US_READY) == (us_content_hash(US_READY), legacy_file_hash(US_READY))


def _plan(us_hash: str) -> str:
    # Plan v2 valide du test historique de validate_plan, avec l'empreinte voulue.
    from test_validate_plan import _v2_plan_with_us_hash  # noqa: PLC0415
    return _v2_plan_with_us_hash(us_hash=us_hash)


def _us(status: str = "Ready") -> str:
    from test_validate_plan import _SAMPLE_US  # noqa: PLC0415
    return _SAMPLE_US.replace("# US 1-2-Login\n", f"# US 1-2-Login\n\nStatus: {status}\n", 1)


def _validate(tmp_path: Path, plan: str, us: str) -> int:
    plan_path = tmp_path / "1-2-Login.back.md"
    us_path = tmp_path / "1-2-Login.md"
    plan_path.write_text(plan, encoding="utf-8")
    us_path.write_text(us, encoding="utf-8", newline="")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--plan-path", str(plan_path), "--us-path", str(us_path), "--json"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), stdin=subprocess.DEVNULL,
    )
    return proc.returncode


def test_plan_stays_fresh_after_status_flip(tmp_path: Path) -> None:
    plan = _plan(us_content_hash(_us("Ready")))
    assert _validate(tmp_path, plan, _us("InProgress")) == 0


def test_legacy_raw_hash_plan_still_fresh_when_us_unchanged(tmp_path: Path) -> None:
    assert _validate(tmp_path, _plan(legacy_file_hash(_us())), _us()) == 0


def test_plan_stale_when_acceptance_criteria_change(tmp_path: Path) -> None:
    plan = _plan(us_content_hash(_us()))
    changed = _us().replace("valid credentials", "valid credentials and MFA")
    assert _validate(tmp_path, plan, changed) == 2
