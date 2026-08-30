"""Tests des sous-commandes predicate `*-present` de query_console_db.py.

Audit F-M1 (2026-08-30) : `/sdd-review` STEP 3.0 invoquait
`code-review-present` et `security-present` qui n'existaient PAS dans le
DISPATCH (seuls `arch-review-present` et `spec-compliance-present`
existaient) → le fallback standalone re-spawnait toujours les reviewers.
Ce module pinne le contrat des 2 sous-commandes ajoutées en miroir :

- exit 0 = ≥ 1 finding FRAIS présent (TTL 24h défaut, --max-age-hours 0 = off)
- exit 1 = absent ou stale
- code-review-present lit qa_code_review en EXCLUANT les classes ARCH_*
  (owned par arch-review-present, même table)
- security-present lit qa_security restreint à mode='scan'
  (threat-model pré-dev ne compte pas)

Isolation : même pattern que test_sdd_state_unit.py (SDD_REPO_ROOT env
override vers un fake repo tmp, console.db initialisé à la volée).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.console_db import connect, ensure_initialized  # noqa: E402
from sdd_scripts import query_console_db as qcdb  # noqa: E402


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    """Fake repo + console.db initialisé + FEAT 1 skeleton (FK feats requis)."""
    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    ensure_initialized()
    with connect() as conn:
        conn.execute(
            "INSERT INTO feats(feat_n, name, file_path, ingested_at) "
            "VALUES (1, 'Auth', 'workspace/feats/1-Auth.md', datetime('now'))"
        )
    yield tmp_path


def _seed_code_review(feat: int, issue_class: str, age_modifier: str = "+0 hours") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO qa_code_review(feat_n, extracted_at, issue_class, severity) "
            "VALUES (?, datetime('now', ?), ?, 'serious')",
            (feat, age_modifier, issue_class),
        )


def _seed_security(feat: int, mode: str, age_modifier: str = "+0 hours") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO qa_security(feat_n, mode, extracted_at, issue_class, severity) "
            "VALUES (?, ?, datetime('now', ?), 'SEC_CORS_PERMISSIVE', 'serious')",
            (feat, mode, age_modifier),
        )


# ---------- code-review-present ----------


def test_code_review_present_exit_1_when_empty(fake_repo, capsys):
    rc = qcdb.main(["code-review-present", "--feat", "1"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["present"] is False
    assert payload["count"] == 0


def test_code_review_present_exit_0_with_fresh_finding(fake_repo, capsys):
    _seed_code_review(1, "REVIEW_DUPLICATE_CODE")
    rc = qcdb.main(["code-review-present", "--feat", "1"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["present"] is True
    assert payload["count"] == 1


def test_code_review_present_ignores_arch_findings(fake_repo, capsys):
    """Les rows ARCH_* (arch-reviewer, même table) ne satisfont PAS le
    prédicat code-review — ils appartiennent à arch-review-present."""
    _seed_code_review(1, "ARCH_PATTERN_VIOLATION")
    rc = qcdb.main(["code-review-present", "--feat", "1"])
    assert rc == 1
    capsys.readouterr()
    # ... alors qu'arch-review-present les voit (miroir inverse)
    rc = qcdb.main(["arch-review-present", "--feat", "1"])
    assert rc == 0


def test_code_review_present_ttl_filters_stale(fake_repo, capsys):
    _seed_code_review(1, "REVIEW_DEEP_NESTING", age_modifier="-48 hours")
    rc = qcdb.main(["code-review-present", "--feat", "1"])
    assert rc == 1  # stale (> 24h) → à re-spawner
    capsys.readouterr()
    rc = qcdb.main(["code-review-present", "--feat", "1", "--max-age-hours", "0"])
    assert rc == 0  # TTL désactivé → row acceptée


# ---------- security-present ----------


def test_security_present_exit_1_when_empty(fake_repo, capsys):
    rc = qcdb.main(["security-present", "--feat", "1"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["present"] is False


def test_security_present_exit_0_with_fresh_scan(fake_repo, capsys):
    _seed_security(1, "scan")
    rc = qcdb.main(["security-present", "--feat", "1"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["present"] is True
    assert payload["count"] == 1


def test_security_present_ignores_threat_model_rows(fake_repo, capsys):
    """Le mode threat-model (pré-dev) ne prouve pas qu'un scan post-dev a
    tourné — seul mode='scan' satisfait le prédicat."""
    _seed_security(1, "threat-model")
    rc = qcdb.main(["security-present", "--feat", "1"])
    assert rc == 1


def test_security_present_ttl_filters_stale(fake_repo, capsys):
    _seed_security(1, "scan", age_modifier="-48 hours")
    rc = qcdb.main(["security-present", "--feat", "1"])
    assert rc == 1
    capsys.readouterr()
    rc = qcdb.main(["security-present", "--feat", "1", "--max-age-hours", "0"])
    assert rc == 0


# ---------- dispatch integrity ----------


def test_all_sdd_review_predicates_dispatched():
    """Les 4 sous-commandes invoquées par sdd-review.md doivent exister dans
    DISPATCH et être marquées predicate (exit-code propagé)."""
    for sub in ("arch-review-present", "spec-compliance-present",
                "code-review-present", "security-present"):
        assert sub in qcdb.DISPATCH
        assert sub in qcdb._PREDICATE_SUBCOMMANDS
