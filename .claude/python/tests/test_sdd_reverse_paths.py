"""test_sdd_reverse_paths.py — P1.7 closure : robust path resolution.

Verifies the 3-mode discovery of `sdd_reverse_dir()` :
    1. SDD_REVERSE_DATA_DIR env var (highest precedence)
    2. Package-relative (default)
    3. Repo-root walk fallback (lowest precedence)

Also verifies that each typed helper raises a clear FileNotFoundError
when its target file is missing (no silent return of bogus paths).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdd_reverse import paths as p


def test_sdd_reverse_dir_default_resolves() -> None:
    """Default mode (package-relative) must locate sdd_reverse/."""
    d = p.sdd_reverse_dir()
    assert d.is_dir()
    assert d.name == "sdd_reverse"


def test_language_signatures_path_default() -> None:
    """language_signatures.yml must be reachable via default resolution."""
    sig = p.language_signatures_path()
    assert sig.is_file()
    assert sig.name == "language_signatures.yml"


def test_feat_reverse_template_path_default() -> None:
    """feat.reverse.template.md (ADV-9 isolated copy) must be present."""
    tpl = p.feat_reverse_template_path()
    assert tpl.is_file()
    assert tpl.name == "feat.reverse.template.md"


def test_parity_snapshots_path_default() -> None:
    """_parity_snapshots.json must be present (ADV-16)."""
    snap = p.parity_snapshots_path()
    assert snap.is_file()
    assert snap.name == "_parity_snapshots.json"


def test_env_var_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SDD_REVERSE_DATA_DIR override takes precedence over package-relative."""
    # Build a fake sdd_reverse dir
    fake = tmp_path / "fake_reverse"
    fake.mkdir()
    monkeypatch.setenv("SDD_REVERSE_DATA_DIR", str(fake))
    resolved = p.sdd_reverse_dir()
    assert resolved == fake.resolve()


def test_env_var_pointing_to_missing_dir_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If env var points to a non-existent directory, helper falls back."""
    monkeypatch.setenv("SDD_REVERSE_DATA_DIR", str(tmp_path / "missing"))
    resolved = p.sdd_reverse_dir()
    # Falls back to package-relative — which DOES exist
    assert resolved.is_dir()
    assert resolved.name == "sdd_reverse"


def test_language_signatures_path_raises_when_target_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If env-overridden dir has no language_signatures.yml → FileNotFoundError."""
    fake = tmp_path / "fake"
    fake.mkdir()
    monkeypatch.setenv("SDD_REVERSE_DATA_DIR", str(fake))
    with pytest.raises(FileNotFoundError, match="language_signatures.yml"):
        p.language_signatures_path()


def test_feat_template_path_raises_when_target_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    monkeypatch.setenv("SDD_REVERSE_DATA_DIR", str(fake))
    with pytest.raises(FileNotFoundError, match="feat.reverse.template.md"):
        p.feat_reverse_template_path()


def test_parity_snapshots_path_raises_when_target_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "fake"
    fake.mkdir()
    monkeypatch.setenv("SDD_REVERSE_DATA_DIR", str(fake))
    with pytest.raises(FileNotFoundError, match="_parity_snapshots.json"):
        p.parity_snapshots_path()
