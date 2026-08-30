"""test_reverse_audit_2026_08_29.py — regressions for the code-reverse audit.

One class per finding. C1 (evidence resolution) has its own file
(`test_reverse_evidence_resolution.py`); this covers M1, M3, M5 and the
taxonomy count guard M6.
"""
from __future__ import annotations

import importlib
import io
import json
import re
from pathlib import Path

import pytest

dae = importlib.import_module("sdd_reverse.data_access_extractor")
cuc = importlib.import_module("sdd_reverse.code_unit_complexity")
sl = importlib.import_module("sdd_reverse.scan_legacy")
cache = importlib.import_module("sdd_reverse.reverse_cache")

REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# M1 — the complexity router's "dynamic SQL" signal was dead
# --------------------------------------------------------------------------- #

class TestDynamicSqlSignalIsEmitted:
    """`code_unit_complexity` read a `dynamicSql` key nothing on the code side
    ever wrote — the strongest reason to spend a deep pass on a unit (behaviour
    not statically observable) never reached the router."""

    def test_parameterized_literal_is_not_dynamic(self):
        q = dae.extract_sql_from_text(
            'var sql = "SELECT Id FROM Users WHERE Name = @n";', "F.cs")
        assert [x.to_dict()["dynamicSql"] for x in q] == [False]

    def test_literal_to_literal_concat_is_not_dynamic(self):
        """`_merge_concatenated_literals` already folds those into one static string."""
        q = dae.extract_sql_from_text(
            'var sql = "SELECT Id FROM Users " + "WHERE Name = @n";', "F.cs")
        assert [x.to_dict()["dynamicSql"] for x in q] == [False]

    @pytest.mark.parametrize("src,single_quotes", [
        ('var s = "SELECT Id FROM Users WHERE Name = \'" + userName + "\'";', False),
        ('var s = String.Format("SELECT Id FROM Users WHERE Id = {0}", id);', False),
        ('s = "SELECT * FROM T WHERE x=" & xVal', False),
        ('var s = "EXEC sp_executesql @stmt";', False),
        ("$sql = 'SELECT * FROM t WHERE id = ' . $id;", True),
        ('$sql = "SELECT * FROM t WHERE id = $id";', True),
    ])
    def test_runtime_assembled_sql_is_dynamic(self, src, single_quotes):
        q = dae.extract_sql_from_text(src, "F", include_single_quotes=single_quotes)
        assert q, f"no query extracted from {src!r}"
        assert any(x.to_dict()["dynamicSql"] for x in q), src

    def test_proc_call_sites_carry_the_key(self):
        calls = dae._extract_proc_calls(
            'cmd.CommandType = CommandType.StoredProcedure; '
            'cmd.CommandText = "usp_GetUser";', "F.cs")
        assert calls and calls[0]["dynamicSql"] is False

    def test_router_now_receives_a_real_signal(self):
        """End-to-end: an extracted dynamic query flips the unit to the deep tier."""
        queries = [q.to_dict() for q in dae.extract_sql_from_text(
            'var s = "SELECT Id FROM Users WHERE Id = " + id;', "F.cs")]
        unit = {
            "id": "U-1", "kind": "form", "confidenceEstimate": "high",
            "classes": [{"name": "Login", "role": "code-behind"}],
            "dataAccess": {"queries": queries},
        }
        assert cuc.complexity_signals(unit)["dynamic_sql"] is True
        assert cuc.classify_unit(unit) == "complex"
        assert cuc.tier_for(unit, "3a") == cuc.TIER_DEEP


# --------------------------------------------------------------------------- #
# M2 / m5 — routing CLI: right project, real fail-safe, tier vocabulary
# --------------------------------------------------------------------------- #

def _inventory(root: Path, units: list[dict]) -> Path:
    (root / ".sys").mkdir(parents=True, exist_ok=True)
    (root / ".sys" / "inventory.json").write_text(
        json.dumps({"units": units}), encoding="utf-8")
    return root


_SIMPLE = {"id": "U-1", "kind": "form", "confidenceEstimate": "high",
           "classes": [{"name": "L", "role": "code-behind"}],
           "dataAccess": {"queries": [{"tables": ["U"], "dynamicSql": False}]}}


class TestTierRouting:
    def test_tier_vocabulary_matches_the_agent_frontmatter(self):
        assert cuc.tier_for(_SIMPLE, "3a") == "balanced"
        assert cuc.tier_for({"id": "U-2", "kind": "module"}, "3a") == "deep"
        assert cuc.tier_for(_SIMPLE, "3b") == "balanced"
        assert cuc.tier_for(_SIMPLE, "3z") == "deep"  # unknown rung → fail-safe

    def test_routes_against_the_named_project_not_the_first_glob_match(self, tmp_path):
        """The one-liners globbed workspace/old/* and took [0] — always the FIRST
        legacy project, discarding the one the command had just resolved."""
        _inventory(tmp_path / "AAA_Other", [{"id": "U-1", "kind": "module"}])
        _inventory(tmp_path / "ZZZ_Target", [_SIMPLE])
        tier, reason = cuc.route_tier(tmp_path / "ZZZ_Target", "U-1", "3a")
        assert (tier, reason) == ("balanced", None)

    def test_unknown_unit_fails_safe_to_deep(self, tmp_path):
        _inventory(tmp_path / "P", [_SIMPLE])
        tier, reason = cuc.route_tier(tmp_path / "P", "U-99", "3a")
        assert tier == "deep" and "U-99" in reason

    def test_missing_inventory_fails_safe_to_deep(self, tmp_path):
        tier, reason = cuc.route_tier(tmp_path / "nope", "U-1", "3a")
        assert tier == "deep" and "unreadable" in reason

    def test_corrupt_inventory_fails_safe_to_deep(self, tmp_path):
        p = tmp_path / "P"
        (p / ".sys").mkdir(parents=True)
        (p / ".sys" / "inventory.json").write_text("{not json", encoding="utf-8")
        tier, reason = cuc.route_tier(p, "U-1", "3a")
        assert tier == "deep" and "not valid JSON" in reason

    def test_cli_always_prints_a_tier_and_exits_zero(self, tmp_path, capsys):
        """The uncaught IndexError/StopIteration meant a traceback surfaced where
        the caller expected a model — the documented fail-safe did not exist."""
        rc = cuc.main(["--project", str(tmp_path / "gone"), "--unit", "U-1"])
        out = capsys.readouterr()
        assert rc == 0
        assert out.out.strip() == "deep"
        assert "[REVERSE/WARN]" in out.err

    def test_commands_reference_the_wired_cli_not_an_inline_glob(self):
        for name in ("sdd-reverse-analyze", "sdd-reverse-feat"):
            text = (REPO_ROOT / ".sdd" / "commands" / f"{name}.md").read_text(
                encoding="utf-8")
            assert "code_unit_complexity.py" in text, name
            assert "glob.glob" not in text and "__import__('glob')" not in text, name


# --------------------------------------------------------------------------- #
# M3 — under-extraction must not be silent
# --------------------------------------------------------------------------- #

class TestReadIssueAccounting:
    def test_unreadable_file_is_recorded_with_its_class(self, tmp_path):
        sl.reset_read_issues()
        text, kind = sl.read_text_normalized_ex(tmp_path / "ghost.cs")
        assert (text, kind) == ("", "unreadable")
        issues = sl.read_issues()
        assert [i["class"] for i in issues] == [sl.CLASS_FILE_UNREADABLE]

    def test_oversized_file_is_recorded_as_sampled(self, tmp_path):
        big = tmp_path / "dump.sql"
        big.write_bytes(b"SELECT 1;\n" * 500)
        sl.reset_read_issues()
        text, kind = sl.read_text_normalized_ex(big, max_bytes=100)
        assert kind == "sampled" and len(text) == 100
        assert [i["class"] for i in sl.read_issues()] == [sl.CLASS_LARGE_FILE_SAMPLED]

    def test_text_only_door_still_records(self, tmp_path):
        """The 7 extractors call the str-returning form — it must not be a hole."""
        sl.reset_read_issues()
        assert sl.read_text_normalized(tmp_path / "ghost.cs") == ""
        assert len(sl.read_issues()) == 1

    def test_whole_file_read_records_nothing(self, tmp_path):
        f = tmp_path / "a.cs"
        f.write_text("class A {}", encoding="utf-8")
        sl.reset_read_issues()
        assert sl.read_text_normalized_ex(f)[1] is None
        assert sl.read_issues() == []

    def test_issues_are_deduped_per_path_and_kind(self, tmp_path):
        sl.reset_read_issues()
        for _ in range(5):
            sl.read_text_normalized(tmp_path / "ghost.cs")
        assert len(sl.read_issues()) == 1

    def test_summary_is_aggregated_not_one_line_per_file(self, tmp_path):
        sl.reset_read_issues()
        for i in range(4):
            sl.read_text_normalized(tmp_path / f"ghost{i}.cs")
        buf = io.StringIO()
        counts = sl.emit_read_issue_summary(buf)
        assert counts == {"unreadable": 4}
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        assert len(lines) == 1
        assert sl.CLASS_FILE_UNREADABLE in lines[0]

    def test_scan_result_exposes_the_counts(self, tmp_path):
        r = sl.ScanResult(primary_language=None, languages=[], frameworks=[],
                          files_scanned=0, files_skipped=0, duration_ms=0,
                          read_issues=[{"kind": "unreadable"}, {"kind": "sampled"},
                                       {"kind": "sampled"}])
        d = r.to_dict()
        assert (d["filesUnreadable"], d["filesSampled"]) == (1, 2)

    def test_scan_project_resets_and_reports(self, tmp_path):
        """`was_sampled` was computed at scan_legacy.py:523 and never used."""
        sl.reset_read_issues()
        sl._record_read_issue(tmp_path / "stale.cs", "unreadable", "from a previous run")
        sigs = sl.load_signatures(
            REPO_ROOT / ".sdd" / "python" / "sdd_reverse" / "language_signatures.yml")
        (tmp_path / "A.cs").write_text("public class A {}", encoding="utf-8")
        result = sl.scan_project(tmp_path, sigs)
        assert all("stale.cs" not in i["path"] for i in result.read_issues)


# --------------------------------------------------------------------------- #
# M5 — the extraction cache lied on a partially-cleaned workspace
# --------------------------------------------------------------------------- #

def _cached_unit(tmp_path: Path, *, kind: str | None = None):
    project = tmp_path / "old" / "P"
    (project / ".sys").mkdir(parents=True)
    (project / "A.cs").write_text("class A {}", encoding="utf-8")
    unit = {"id": "U-1", "evidenceFiles": ["A.cs"]}
    if kind:
        unit["kind"] = kind
    ws = tmp_path / "ws"
    feats, plans, us = ws / "feats", ws / "plans", ws / "us"
    for d in (feats, plans, us):
        d.mkdir(parents=True)
    (feats / "1-Login.md").write_text("# FEAT", encoding="utf-8")
    (plans / "1-Login.analysis.md").write_text("# Analyse", encoding="utf-8")
    (us / "1-1-Se-Connecter.md").write_text("# US", encoding="utf-8")
    cache.save_unit(project, "U-1", cache.compute_unit_evidence_hash(project, unit),
                    1, "Login")
    return project, unit, feats, plans, us


class TestCacheRequiresTheWholeLadder:
    def test_complete_ladder_is_a_hit(self, tmp_path):
        project, unit, feats, plans, us = _cached_unit(tmp_path)
        assert cache.is_unit_cached(project, unit, feats, plans, us)

    def test_deleting_the_us_dir_forces_re_extraction(self, tmp_path):
        """The documented way to force US regeneration; it used to be swallowed."""
        import shutil
        project, unit, feats, plans, us = _cached_unit(tmp_path)
        shutil.rmtree(us)
        assert not cache.is_unit_cached(project, unit, feats, plans, us)

    def test_emptying_the_us_dir_also_forces_re_extraction(self, tmp_path):
        project, unit, feats, plans, us = _cached_unit(tmp_path)
        for f in us.glob("*.md"):
            f.unlink()
        assert not cache.is_unit_cached(project, unit, feats, plans, us)

    def test_deleting_the_3a_plan_forces_re_extraction(self, tmp_path):
        project, unit, feats, plans, us = _cached_unit(tmp_path)
        (plans / "1-Login.analysis.md").unlink()
        assert not cache.is_unit_cached(project, unit, feats, plans, us)

    def test_db_module_needs_no_3a_plan(self, tmp_path):
        """The DB ladder has 2 rungs by design — requiring a plan would make every
        DB unit a permanent cache miss."""
        project, unit, feats, plans, us = _cached_unit(tmp_path, kind="db-module")
        (plans / "1-Login.analysis.md").unlink()
        assert cache.is_unit_cached(project, unit, feats, plans, us)

    def test_two_argument_callers_keep_the_old_behaviour(self, tmp_path):
        import shutil
        project, unit, feats, plans, us = _cached_unit(tmp_path)
        shutil.rmtree(us)
        shutil.rmtree(plans)
        assert cache.is_unit_cached(project, unit, feats)


# --------------------------------------------------------------------------- #
# M6 — the reverse taxonomy count must match the table it describes
# --------------------------------------------------------------------------- #

RULE = REPO_ROOT / ".sdd" / "rules" / "reverse-engineering.md"
_ROW_RE = re.compile(r"^\|\s*`(\[REVERSE_[A-Z_]+\])`\s*\|", re.MULTILINE)
_STATED_RE = re.compile(r"\*\*(\d+)\s+classes\*\*")


def _declared_classes() -> list[str]:
    return _ROW_RE.findall(RULE.read_text(encoding="utf-8"))


class TestReverseTaxonomyCount:
    """§6.3 asserted "37 classes" over a 40-row table, with nothing guarding it —
    the same drift the forward pipeline pins with test_error_classification_count."""

    def test_no_duplicate_rows(self):
        classes = _declared_classes()
        dupes = {c for c in classes if classes.count(c) > 1}
        assert not dupes, f"duplicate taxonomy rows: {sorted(dupes)}"

    def test_stated_count_matches_the_table(self):
        text = RULE.read_text(encoding="utf-8")
        stated = _STATED_RE.findall(text)
        assert stated, "§6.3 no longer states a class count in **N classes** form"
        actual = len(_declared_classes())
        for s in stated:
            assert int(s) == actual, (
                f"reverse-engineering.md announces {s} classes but the §6 table "
                f"holds {actual} rows — update both together (a class never "
                f"enters the taxonomy without its emitter).")

    def test_the_two_read_issue_classes_are_declared(self):
        classes = _declared_classes()
        assert sl.CLASS_FILE_UNREADABLE in classes
        assert sl.CLASS_LARGE_FILE_SAMPLED in classes
