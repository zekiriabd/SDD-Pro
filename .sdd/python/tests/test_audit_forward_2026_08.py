"""Regression tests for the forward-module audit fixes of 2026-08-29.

One theme runs through all of them: a guard that *looked* active but could
not fire, or a fallback that silently moved in the unsafe direction.

  M4  — façade auto-rebuild triggered only on absence, never on drift.
  M8  — bypass env vars documented as "audit-logged" that logged nothing.
  M9  — malformed numeric config silently WIDENED the cost budget.
  M10 — the console.db mirror of a manual-gate approval failed in silence.
  M11 — a bare `except` around config parsing dropped team security policy;
        FEAT-name ambiguity was resolved by guessing `matches[0]`.
  M12 — review-finding path normalization collided unrelated files.
  m1  — complexity-router volume/retention parsing mis-scored FEATs.
  m2  — long-method scan treated "could not measure" as "is short".
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))

from sdd_admin import rebuild_claude_facade as rcf  # noqa: E402
from sdd_hooks import preflight_cost_cap as pcc  # noqa: E402
from sdd_hooks import protect_framework as pf  # noqa: E402
from sdd_scripts import complexity_router as cr  # noqa: E402
from sdd_scripts import phase_planner as pp  # noqa: E402
from sdd_scripts import quality_scan as qs  # noqa: E402
from sdd_scripts._review_fetch import _normalize_path  # noqa: E402


# ---------------------------------------------------------------------------
# M4 — façade rebuild must trigger on DRIFT, not only on absence
# ---------------------------------------------------------------------------

def _make_facade(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path
    for sub in ("agents", "commands", "rules"):
        (repo / ".sdd" / sub).mkdir(parents=True)
        (repo / ".claude" / sub).mkdir(parents=True)
        (repo / ".sdd" / sub / "x.md").write_text("body\n", encoding="utf-8")
        (repo / ".claude" / sub / "x.md").write_text("body\n", encoding="utf-8")
    (repo / ".sdd" / "CLAUDE.md").write_text("root\n", encoding="utf-8")
    (repo / ".claude" / "CLAUDE.md").write_text("root\n", encoding="utf-8")
    return repo, repo / ".claude"


def _touch_newer(path: Path, reference: Path) -> None:
    ref = reference.stat()
    os.utime(path, ns=(ref.st_atime_ns + 10**9, ref.st_mtime_ns + 10**9))


def test_facade_rebuild_not_needed_when_in_sync(tmp_path):
    repo, claude = _make_facade(tmp_path)
    assert rcf._sources_newer_than_facade(repo, claude) is None
    assert rcf._needs_rebuild(claude, repo) is False


def test_facade_rebuild_triggers_on_source_drift(tmp_path):
    """Regression — an edited `.sdd/` source used to leave the façade stale."""
    repo, claude = _make_facade(tmp_path)
    src = repo / ".sdd" / "rules" / "x.md"
    src.write_text("body EDITED\n", encoding="utf-8")
    _touch_newer(src, claude / "rules" / "x.md")
    reason = rcf._sources_newer_than_facade(repo, claude)
    assert reason and "rules/x.md" in reason
    assert rcf._needs_rebuild(claude, repo) is True
    # And the legacy absence-only check still says "all good" — the bug.
    assert rcf._needs_rebuild(claude) is False


def test_facade_rebuild_triggers_on_missing_single_file(tmp_path):
    repo, claude = _make_facade(tmp_path)
    (claude / "agents" / "x.md").unlink()
    (claude / "agents" / "other.md").write_text("x\n", encoding="utf-8")
    assert rcf._sources_newer_than_facade(repo, claude)
    assert rcf._needs_rebuild(claude, repo) is True


# ---------------------------------------------------------------------------
# M8 — bypasses must leave a visible trace
# ---------------------------------------------------------------------------

def test_cost_cap_bypass_is_logged():
    buf = io.StringIO()
    with patch.dict(os.environ, {"SDD_DISABLE_COST_CAP": "1"}), redirect_stderr(buf):
        assert pcc._resolve_cap() == 0.0
    assert "SDD_DISABLE_COST_CAP" in buf.getvalue()
    assert "BYPASS" in buf.getvalue()


def test_protect_framework_off_is_logged():
    buf = io.StringIO()
    with patch.dict(os.environ, {"SDD_PROTECT_FRAMEWORK_MODE": "off"}), \
            redirect_stderr(buf):
        assert pf._main_inner() == 0
    assert "SDD_PROTECT_FRAMEWORK_MODE=off" in buf.getvalue()


def test_force_pipeline_bypass_preserves_scored_value():
    """`SDD_FORCE_PIPELINE` must not erase the rubric's own verdict."""
    assert cr._FORCE_MAP["poc"] == "small"
    assert cr._FORCE_MAP["critical"] == "critical"


# ---------------------------------------------------------------------------
# M9 — a defensive default must never be WEAKER than the value it replaces
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["5O", "$15", "fifteen", "12,50", "--", "1e"])
def test_malformed_cap_is_loud(bad):
    buf = io.StringIO()
    with redirect_stderr(buf):
        value = pcc._coerce_cap(bad, default=50.0, key="MaxCostPerRun")
    out = buf.getvalue()
    assert value == 50.0
    assert "MaxCostPerRun" in out
    assert bad in out, "the raw invalid value must be shown to the operator"
    assert "[STACK_MALFORMED]" in out


def test_negative_cap_is_rejected_not_treated_as_disabled():
    buf = io.StringIO()
    with redirect_stderr(buf):
        value = pcc._coerce_cap("-1", default=15.0, key="BuildLoopMaxCostUsd")
    assert value == 15.0
    assert "n" in buf.getvalue()  # something was said
    assert "[STACK_MALFORMED]" in buf.getvalue()


@pytest.mark.parametrize("raw,expected", [
    ("25", 25.0), (" 12.5 ", 12.5), (0, 0.0), ("0", 0.0), (None, 50.0), ("", 50.0),
])
def test_valid_cap_values_pass_through_silently(raw, expected):
    buf = io.StringIO()
    with redirect_stderr(buf):
        assert pcc._coerce_cap(raw, default=50.0, key="MaxCostPerRun") == expected
    assert buf.getvalue() == ""


# ---------------------------------------------------------------------------
# M11 — FEAT ambiguity must be refused, not guessed
# ---------------------------------------------------------------------------

def test_phase_planner_refuses_ambiguous_feat(tmp_path):
    """Aligned with `complexity_router`, which already raises on this."""
    feats = tmp_path / "workspace" / "feats"
    feats.mkdir(parents=True)
    (feats / "1-Auth.md").write_text("# a\n", encoding="utf-8")
    (feats / "1-Avoir.md").write_text("# b\n", encoding="utf-8")
    with pytest.raises(pp.FeatAmbiguousError):
        pp._read_feat_file(tmp_path, 1)


def test_phase_planner_reads_unambiguous_feat(tmp_path):
    feats = tmp_path / "workspace" / "feats"
    feats.mkdir(parents=True)
    (feats / "1-Auth.md").write_text("# a\n", encoding="utf-8")
    name, content = pp._read_feat_file(tmp_path, 1)
    assert name == "Auth"
    assert content == "# a\n"


def test_phase_planner_missing_feat_is_not_ambiguous(tmp_path):
    (tmp_path / "workspace" / "feats").mkdir(parents=True)
    assert pp._read_feat_file(tmp_path, 9) == (None, None)


# ---------------------------------------------------------------------------
# M12 — path normalization must not collide unrelated files
# ---------------------------------------------------------------------------

def test_mysrc_does_not_collide_with_src():
    """The exact pair from the audit: `lstrip('./')` + substring `find`."""
    assert _normalize_path("mysrc/Auth.cs") != _normalize_path("src/Auth.cs")
    assert _normalize_path("mysrc/Auth.cs") == "mysrc/auth.cs"
    assert _normalize_path("src/Auth.cs") == "auth.cs"


@pytest.mark.parametrize("a,b", [
    ("./src/Auth.cs", "src/Auth.cs"),
    ("workspace/src/App/Auth.cs", "App/Auth.cs"),
    ("workspace\\src\\App\\Auth.cs", "app/auth.cs"),
])
def test_equivalent_paths_still_converge(a, b):
    assert _normalize_path(a) == _normalize_path(b)


def test_leading_dot_is_not_eaten():
    """`lstrip('./')` ate leading dots — `.sdd/x.py` became `sdd/x.py`."""
    assert _normalize_path(".sdd/x/y.py") == ".sdd/x/y.py"


def test_normalize_path_is_idempotent_and_empty_safe():
    assert _normalize_path(None) == ""
    assert _normalize_path("") == ""
    once = _normalize_path("workspace/src/App/Auth.cs")
    assert _normalize_path(once) == once


# ---------------------------------------------------------------------------
# m1 — complexity router volume / retention parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("volume,high,critical", [
    ("1.5k req/day", False, False),      # was parsed as 15 000 → false "high"
    ("1,5k req/jour", False, False),
    ("9k req/day", False, False),
    ("10k requetes/jour", True, False),
    ("100.000 req/jour", True, True),    # grouped thousands, not 100
    ("1,500,000 req/day", True, True),
    ("2M req/day", True, True),
    ("500 utilisateurs concurrents", True, False),
    ("1 500 req/jour", False, False),
])
def test_volume_parsing(volume, high, critical):
    assert cr._check_volume_high(volume) == (high, critical)


@pytest.mark.parametrize("retention,expected", [
    ("aucun plan de purge", False),   # "plan" contains "an"
    ("avant migration", False),       # "avant" contains "an"
    ("management interne", False),
    ("analytics only", False),
    ("bancaire", False),
    ("5 ans", True),
    ("1 an", True),
    ("2 années", True),
    ("RGPD", True),
    ("7 years", True),
    ("30 jours", False),
    ("6 mois", False),
])
def test_retention_word_boundary(retention, expected):
    assert cr._check_retention_long(retention) is expected


# ---------------------------------------------------------------------------
# m2 — long-method scan must not certify what it could not measure
# ---------------------------------------------------------------------------

def test_short_c_method_resolves():
    src = "public int Foo(){\n  return 1;\n}\n"
    span, resolved = qs._method_span(src, 0, is_python=False)
    assert resolved and span <= qs.LONG_METHOD_THRESHOLD


def test_long_c_method_beyond_old_window_is_measured():
    """A 120-line method used to exhaust the 100-line window and pass."""
    body = "\n".join("  x++;" for _ in range(120))
    src = "public int Foo(){\n" + body + "\n}\n"
    span, resolved = qs._method_span(src, 0, is_python=False)
    assert resolved
    assert span > qs.LONG_METHOD_THRESHOLD


def test_unbalanced_braces_are_unresolved_not_short():
    """`close_line == -1` used to compare `-1 > 50` → False → 'compliant'."""
    body = "\n".join("  x++;" for _ in range(120))
    src = "public int Foo(){\n" + body + "\n"  # never closes
    span, resolved = qs._method_span(src, 0, is_python=False)
    assert resolved is False
    assert span > qs.LONG_METHOD_THRESHOLD


def test_python_methods_are_measured_by_indentation():
    """Brace counting cannot work on Python — every .py method was exempt."""
    body = "\n".join("    x += 1" for _ in range(80))
    src = "def foo():\n" + body + "\n\ndef bar():\n    pass\n"
    span, resolved = qs._method_span(src, 0, is_python=True)
    assert resolved
    assert span > qs.LONG_METHOD_THRESHOLD


def test_short_python_method_is_short():
    src = "def foo():\n    return 1\n\ndef bar():\n    pass\n"
    span, resolved = qs._method_span(src, 0, is_python=True)
    assert resolved and span <= qs.LONG_METHOD_THRESHOLD


def test_python_method_inside_class_uses_its_own_indent():
    body = "\n".join("        x += 1" for _ in range(60))
    src = "class C:\n    def foo(self):\n" + body + "\n    def bar(self):\n        pass\n"
    start = src.index("def foo")
    span, resolved = qs._method_span(src, start, is_python=True)
    assert resolved
    assert span > qs.LONG_METHOD_THRESHOLD


# ---------------------------------------------------------------------------
# M10 — a lost gate-approval mirror write must be visible
# ---------------------------------------------------------------------------

def test_gate_mirror_write_failure_is_visible(tmp_path, monkeypatch):
    """Regression — `except Exception: pass` around the console.db mirror.

    `gates` is the only QUERYABLE record of a manual-gate approval. When the
    mirror insert failed, the approval vanished from the audit trail with
    nobody informed. It stays non-fatal (status.json still holds the
    decision) but it must now say so.
    """
    from sdd_scripts import gate_decide

    (tmp_path / ".claude").mkdir()
    monkeypatch.setenv("SDD_REPO_ROOT", str(tmp_path))
    status_file = tmp_path / "status.json"

    def _boom(*_a, **_kw):
        raise RuntimeError("db locked")

    monkeypatch.setattr(gate_decide, "insert_gate", _boom)
    monkeypatch.setattr(sys, "argv", [
        "gate_decide.py", "set", "--feat-num", "1", "--phase", "afterUS",
        "--decision", "validated", "--answered-by", "tech-lead",
        "--status-file", str(status_file),
    ])
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = gate_decide.main()

    assert rc == 0, "a telemetry failure must not fail the gate"
    out = buf.getvalue()
    assert "mirror console.db" in out
    assert "db locked" in out
    assert "afterUS" in out
    # The decision itself is still persisted where the console UI reads it.
    assert status_file.is_file()
