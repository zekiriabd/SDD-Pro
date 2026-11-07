"""sdd_review — échecs de lecture config jamais silencieux (audit 2026-11-07).

Avant : `except Exception: return <défaut>` dans resolve_fail_on /
resolve_arch_required / resolve_auditor_batch_mode → verdict calculé contre
`ReviewFailOn=serious` sans aucune trace si `read_layered_config` plantait.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_scripts import sdd_review  # noqa: E402
from sdd_lib.layered_config import ConfigError  # noqa: E402


def _boom(*_a, **_k):
    raise OSError("disk unreadable")


def _patch_reader(side_effect):
    return mock.patch("sdd_lib.layered_config.read_layered_config", side_effect=side_effect)


def test_fail_on_read_failure_raises_explicitly():
    with _patch_reader(_boom):
        with pytest.raises(sdd_review.ConfigReadFailed) as ei:
            sdd_review.resolve_fail_on(None)
    assert "ReviewFailOn" in str(ei.value) and "disk unreadable" in str(ei.value)


def test_fail_on_cli_value_bypasses_config():
    with _patch_reader(_boom):
        assert sdd_review.resolve_fail_on("critical") == "critical"


def test_fail_on_policy_error_still_surfaces():
    err = ConfigError("e", "[CONFIG_SECURITY_DOWNGRADE] x", "f")
    with _patch_reader(err):
        with pytest.raises(ConfigError):
            sdd_review.resolve_fail_on(None)


def test_fail_on_invalid_value_warns(capsys):
    with _patch_reader(lambda **_k: {"ReviewFailOn": "garbage"}):
        assert sdd_review.resolve_fail_on(None) == "serious"
    assert "[CONFIG_INVALID_VALUE]" in capsys.readouterr().err


def test_fail_on_absent_key_is_documented_default_without_noise(capsys):
    with _patch_reader(lambda **_k: {}):
        assert sdd_review.resolve_fail_on(None) == "serious"
    assert capsys.readouterr().err == ""


def test_arch_required_read_failure_is_logged(capsys):
    with _patch_reader(_boom):
        assert sdd_review.resolve_arch_required() is False
    assert "[CONFIG_READ_FAILED]" in capsys.readouterr().err


def test_batch_mode_read_failure_is_logged(capsys):
    with _patch_reader(_boom):
        assert sdd_review.resolve_auditor_batch_mode() == "two-stage"
    assert "[CONFIG_READ_FAILED]" in capsys.readouterr().err


def test_main_exits_2_with_3l_error_on_config_read_failure(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sdd_review.py", "--feat-number", "1", "--skip-scans"])
    with _patch_reader(_boom):
        rc = sdd_review.main()
    err = capsys.readouterr().err
    assert rc == 2
    assert "ERROR: /sdd-review FEAT 1" in err
    assert "CAUSE: [CONFIG_READ_FAILED]" in err
    assert "FIX:" in err
