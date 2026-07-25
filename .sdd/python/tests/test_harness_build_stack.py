"""Tests du wiring `--stack` de harness_build.py (Phase 1.7 — câblage CLI).

`--stack` dérive harnais + provider depuis un `stack.md` ; les flags explicites
`--harness`/`--provider` priment (chacun sur son axe). Rétro-compat totale :
sans `--stack`, `--harness` reste requis et le provider défaut est anthropic.

Écrit uniquement sous .sdd/.build/ (nettoyé) ; stack.md en tempfile.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

SDD_HOME = Path(__file__).resolve().parents[2]  # .sdd/
if str(SDD_HOME) not in sys.path:
    sys.path.insert(0, str(SDD_HOME))  # pour importer harness_build.py

from harness_build import main  # noqa: E402


@pytest.fixture()
def build_dir():
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-stack-cli-", dir=build_root))
    yield out
    shutil.rmtree(out, ignore_errors=True)


def _write_stack(text: str) -> str:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix="-stack.md", delete=False, encoding="utf-8"
    )
    tmp.write(text)
    tmp.close()
    return tmp.name


def test_stack_derives_harness_and_provider(build_dir, capsys):
    stack = _write_stack(
        "## Active Harness\nHarness: codex\n"
        "## Active Model Provider\nProvider: moonshot\n"
    )
    try:
        rc = main(["--stack", stack, "--memory-only", "--out", str(build_dir)])
    finally:
        Path(stack).unlink(missing_ok=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "harness=codex, provider=moonshot" in out
    assert (build_dir / "AGENTS.md").is_file()  # codex -> AGENTS.md


def test_explicit_harness_overrides_stack(build_dir, capsys):
    stack = _write_stack("## Active Harness\nHarness: codex\n")
    try:
        rc = main(
            ["--stack", stack, "--harness", "claude-code", "--memory-only", "--out", str(build_dir)]
        )
    finally:
        Path(stack).unlink(missing_ok=True)
    assert rc == 0
    assert "harness=claude-code" in capsys.readouterr().out
    assert (build_dir / "CLAUDE.md").is_file()


def test_explicit_provider_overrides_stack(build_dir, capsys):
    stack = _write_stack(
        "## Active Harness\nHarness: claude-code\n"
        "## Active Model Provider\nProvider: moonshot\n"
    )
    try:
        rc = main(
            ["--stack", stack, "--provider", "anthropic", "--memory-only", "--out", str(build_dir)]
        )
    finally:
        Path(stack).unlink(missing_ok=True)
    assert rc == 0
    assert "provider=anthropic" in capsys.readouterr().out


def test_neither_harness_nor_stack_is_rc2(build_dir, capsys):
    rc = main(["--memory-only", "--out", str(build_dir)])
    assert rc == 2
    assert "[INVALID_ARG]" in capsys.readouterr().err


def test_missing_stack_file_is_rc1(build_dir, capsys):
    rc = main(["--stack", "does/not/exist.md", "--memory-only", "--out", str(build_dir)])
    assert rc == 1
    assert "[INVALID_ARG]" in capsys.readouterr().err


def test_stack_harness_without_adapter_is_rc2(build_dir, capsys):
    """antigravity = harnais valide (ADR D1) mais sans adaptateur build -> rc2 clair."""
    stack = _write_stack("## Active Harness\nHarness: antigravity\n")
    try:
        rc = main(["--stack", stack, "--memory-only", "--out", str(build_dir)])
    finally:
        Path(stack).unlink(missing_ok=True)
    assert rc == 2
    err = capsys.readouterr().err
    assert "antigravity" in err
    assert "adaptateur" in err


def test_stack_without_new_sections_defaults_to_claude_anthropic(build_dir, capsys):
    """Un stack.md legacy via --stack retombe sur claude-code/anthropic (rétro-compat)."""
    stack = _write_stack("## Active Backend\nStack: dotnet\n")
    try:
        rc = main(["--stack", stack, "--memory-only", "--out", str(build_dir)])
    finally:
        Path(stack).unlink(missing_ok=True)
    assert rc == 0
    assert "harness=claude-code, provider=anthropic" in capsys.readouterr().out
