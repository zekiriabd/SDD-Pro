"""Regression tests for the reverse-DB fixes (audit 2026-08-28).

Covers all 6 bugs/gaps fixed in build_proc_feats.py, db_tier_router.py and
sql_body_analyzer.py — independent of any database connection (0 live calls).
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINGERPRINT_KEY = "generated-fingerprint"


def _fp(body: str) -> str:
    stripped = "\n".join(
        line for line in body.splitlines()
        if not line.startswith(_FINGERPRINT_KEY + ":")
    )
    return hashlib.sha256(stripped.encode()).hexdigest()[:16]


def _make_feat(us_analyzed: int, us_templated: int, *, with_fp: bool = True) -> str:
    body = textwrap.dedent(f"""\
        ---
        generated-by: sdd-reverse
        us-analyzed: {us_analyzed}
        us-templated: {us_templated}
        ---
        # FEAT
        """)
    if with_fp:
        fp = _fp(body)
        body = body.replace("---\n", f"---\n{_FINGERPRINT_KEY}: {fp}\n", 1)
    return body


# ===========================================================================
# BUG-2 — human_edited() should NOT block regeneration of an empty FEAT
# ===========================================================================

class TestBug2FingerprintGuard:

    def test_empty_feat_not_treated_as_human_edited(self, tmp_path):
        """A FEAT stamped with us-analyzed:0 and us-templated:0 must be
        regeneratable even though it has a valid fingerprint."""
        from sdd_reverse_scripts.build_proc_feats import human_edited
        feat = tmp_path / "feat.md"
        feat.write_text(_make_feat(0, 0), encoding="utf-8")
        assert human_edited(feat) is False, (
            "Empty FEAT (0+0) should NOT be treated as human-edited")

    def test_nonempty_feat_with_matching_fp_not_regenerated(self, tmp_path):
        """A FEAT with real US content and a valid fingerprint must be protected."""
        from sdd_reverse_scripts.build_proc_feats import human_edited
        feat = tmp_path / "feat.md"
        feat.write_text(_make_feat(3, 1), encoding="utf-8")
        assert human_edited(feat) is False, (
            "Real FEAT with matching fingerprint must stay protected")

    def test_human_edited_feat_detected(self, tmp_path):
        """Changing the content after stamp must be detected."""
        from sdd_reverse_scripts.build_proc_feats import human_edited
        body = _make_feat(2, 0)
        feat = tmp_path / "feat.md"
        feat.write_text(body, encoding="utf-8")
        # Simulate human edit
        feat.write_text(body + "\n## Extra section added by human\n", encoding="utf-8")
        assert human_edited(feat) is True, (
            "A FEAT modified after stamping must be detected as human-edited")

    def test_feat_without_fingerprint_treated_as_human_owned(self, tmp_path):
        """A FEAT with no fingerprint is treated as human-owned (pre-M5 or LLM-assembled)."""
        from sdd_reverse_scripts.build_proc_feats import human_edited
        feat = tmp_path / "feat.md"
        feat.write_text(_make_feat(0, 0, with_fp=False), encoding="utf-8")
        assert human_edited(feat) is True, (
            "A FEAT with no fingerprint must be treated as human-owned")


# ===========================================================================
# BUG-1 — _fix_parent_feat corrects wrong parent-feat in US files
# ===========================================================================

class TestBug1ParentFeat:

    def _write_us(self, path: Path, parent: str) -> None:
        path.write_text(
            f"---\nid: 1-1-Test\nparent-feat: {parent}\n---\n# US-1: Test\n",
            encoding="utf-8",
        )

    def test_fixes_wrong_parent_feat(self, tmp_path):
        from sdd_reverse_scripts.build_proc_feats import _fix_parent_feat
        us = tmp_path / "1-1-Test.md"
        self._write_us(us, "1-NounouJob")
        us_index = {"dbo.usp_Test": {"path": us}}
        fixed = _fix_parent_feat(us_index, 1, "Contrat")
        assert len(fixed) == 1
        text = us.read_text(encoding="utf-8")
        assert "parent-feat: 1-Contrat" in text
        assert "1-NounouJob" not in text

    def test_does_not_touch_correct_parent_feat(self, tmp_path):
        from sdd_reverse_scripts.build_proc_feats import _fix_parent_feat
        us = tmp_path / "1-1-Test.md"
        self._write_us(us, "1-Contrat")
        original_mtime = us.stat().st_mtime_ns
        us_index = {"dbo.usp_Test": {"path": us}}
        fixed = _fix_parent_feat(us_index, 1, "Contrat")
        assert fixed == [], "No fix needed when parent-feat is already correct"
        # File must not have been written (mtime unchanged)
        assert us.stat().st_mtime_ns == original_mtime

    def test_fixes_capital_form(self, tmp_path):
        """Also handles the 'Parent FEAT: ...' body form written by some agents."""
        from sdd_reverse_scripts.build_proc_feats import _fix_parent_feat
        us = tmp_path / "1-1-Test.md"
        us.write_text("Parent FEAT: 1-WrongName\n", encoding="utf-8")
        us_index = {"dbo.usp_Test": {"path": us}}
        fixed = _fix_parent_feat(us_index, 1, "Contrat")
        assert len(fixed) == 1
        text = us.read_text(encoding="utf-8")
        assert "1-Contrat" in text


# ===========================================================================
# BUG-3 — AC uses US title when available (not "le résultat attendu est retourné")
# ===========================================================================

class TestBug3AcContent:

    def _make_proc(self, fq_name: str, tables_written: list[str] | None = None) -> dict:
        return {
            "fqName": fq_name,
            "usIndex": 1,
            "usName": "Test",
            "verb": "compute",
            "tablesWritten": tables_written or [],
            "tablesRead": [],
            "routineType": "SQL_SCALAR_FUNCTION",
            "evidence": ".sys/proc-snapshot/dbo.fn_Test.sql:1-20",
            "confidence": "high",
            "raises": [],
            "hasTransaction": False,
        }

    def test_ac_uses_us_title_when_available(self, tmp_path):
        from sdd_reverse_scripts.build_proc_feats import build_module_feat
        proc = self._make_proc("dbo.fn_CalculerAge")
        unit = {
            "id": "U-1",
            "suggestedName": "FnCalculerAge",
            "language": "tsql",
            "confidenceEstimate": "high",
            "procedures": [proc],
        }
        us_index = {
            "dbo.fn_CalculerAge": {
                "path": tmp_path / "1-1-Test.md",
                "title": "Calculer l'âge d'un bébé à partir de sa date de naissance",
                "acIds": ["AC-1"],
                "acCount": 1,
                "extraction": "analyzed",
            }
        }
        feat, _ = build_module_feat(unit, n=1, project="TestDb",
                                     db_type="sqlserver", us_index=us_index)
        assert "Calculer l'âge d'un bébé" in feat, (
            "AC should use the LLM-produced US title")
        assert "résultat attendu est retourné" not in feat, (
            "Trivial placeholder AC must not appear when US title is available")

    def test_ac_uses_type_hint_when_no_title(self):
        from sdd_reverse_scripts.build_proc_feats import build_module_feat
        proc = self._make_proc("dbo.fn_NoTitle")
        unit = {
            "id": "U-1",
            "suggestedName": "FnNoTitle",
            "language": "tsql",
            "confidenceEstimate": "high",
            "procedures": [proc],
        }
        feat, _ = build_module_feat(unit, n=1, project="TestDb",
                                     db_type="sqlserver", us_index={})
        assert "fonction" in feat.lower(), (
            "AC should contain type-aware language when US title is unavailable")
        assert "résultat attendu est retourné" not in feat, (
            "Generic placeholder must still be replaced by type-aware phrase")


# ===========================================================================
# GAP-3 — legacy-sources must be a valid YAML list, not a directory string
# ===========================================================================

class TestGap3LegacySources:

    def _build_feat_text(self, evidence_values: list[str]) -> str:
        from sdd_reverse_scripts.build_proc_feats import build_module_feat
        procs = [
            {
                "fqName": f"dbo.usp_{i}",
                "usIndex": i,
                "usName": f"Proc{i}",
                "verb": "create",
                "tablesWritten": [],
                "tablesRead": [],
                "routineType": "procedure",
                "evidence": ev,
                "confidence": "high",
                "raises": [],
                "hasTransaction": False,
            }
            for i, ev in enumerate(evidence_values, start=1)
        ]
        unit = {
            "id": "U-1",
            "suggestedName": "Test",
            "language": "tsql",
            "confidenceEstimate": "high",
            "procedures": procs,
        }
        feat, _ = build_module_feat(unit, n=1, project="TestDb",
                                     db_type="sqlserver", us_index={})
        return feat

    def test_sources_populated_correctly(self):
        feat = self._build_feat_text(
            [".sys/proc-snapshot/dbo.usp_1.sql:1", ".sys/proc-snapshot/dbo.usp_2.sql:1"]
        )
        m = re.search(r"^legacy-sources:\s*(.+)$", feat, re.MULTILINE)
        assert m, "legacy-sources line must be present in frontmatter"
        assert ".sys/proc-snapshot" in m.group(1)
        assert "(.sys/proc-snapshot)" not in m.group(1), (
            "Must not produce invalid directory string fallback")

    def test_sources_empty_list_when_no_evidence(self):
        """When no proc has evidence, legacy-sources must be an empty list, not a dir string."""
        feat = self._build_feat_text([""])  # empty evidence
        m = re.search(r"^legacy-sources:\s*(.+)$", feat, re.MULTILINE)
        assert m
        assert "(.sys/proc-snapshot)" not in m.group(1), (
            "Empty evidence must not produce directory string fallback")


# ===========================================================================
# R8/GAP-4 — tier routing: params≥4 with zero logic must stay at tier=none
# ===========================================================================

class TestR8TierRouting:

    def test_params4_no_logic_stays_none(self):
        from sdd_reverse.db_tier_router import tier_for
        rec = {
            "fqName": "dbo.usp_CreateReservation",
            "lineCount": 12,
            "branches": 0,
            "raises": [],
            "callsProcs": [],
            "tablesWritten": ["Reservation"],
            "tablesRead": [],
            "params": ["@UserId", "@RoomId", "@CheckIn", "@CheckOut"],
        }
        tier, reasons = tier_for(rec)
        assert tier == "none", (
            f"Simple 4-param INSERT (no logic) must be tier=none, got {tier!r} ({reasons})")

    def test_params4_with_branches_upgrades(self):
        from sdd_reverse.db_tier_router import tier_for
        rec = {
            "fqName": "dbo.usp_ValidateAndCreate",
            "lineCount": 30,
            "branches": 2,
            "raises": ["THROW"],
            "callsProcs": [],
            "tablesWritten": ["Reservation"],
            "params": ["@UserId", "@RoomId", "@CheckIn", "@CheckOut", "@Force"],
        }
        tier, _ = tier_for(rec)
        assert tier in ("fast", "balanced", "deep"), (
            f"Proc with branches + raises must be above none, got {tier!r}")

    def test_params7_no_logic_stays_none(self):
        from sdd_reverse.db_tier_router import tier_for
        rec = {
            "fqName": "dbo.usp_BulkInsert",
            "lineCount": 8,
            "branches": 0,
            "raises": [],
            "callsProcs": [],
            "tablesWritten": ["Orders"],
            "params": [f"@p{i}" for i in range(7)],
        }
        tier, reasons = tier_for(rec)
        assert tier == "none", (
            f"7-param INSERT with zero logic must be tier=none, got {tier!r} ({reasons})")


# ===========================================================================
# BUG-2 barrier — build_proc_feats exits 5 when LLM-routed US are missing
# ===========================================================================

class TestBug2OrchestrationBarrier:

    def _make_inventory(self, tier: str, tmp_path: Path) -> Path:
        inv = {
            "databaseType": "sqlserver",
            "_featAllocations": {"U-1": 1},
            "units": [{
                "id": "U-1",
                "suggestedName": "Test",
                "language": "tsql",
                "confidenceEstimate": "high",
                "procedures": [{
                    "fqName": "dbo.usp_Test",
                    "usIndex": 1,
                    "usName": "Test",
                    "tier": tier,
                    "verb": "create",
                    "tablesWritten": [],
                    "tablesRead": [],
                    "routineType": "procedure",
                    "evidence": ".sys/proc-snapshot/dbo.usp_Test.sql:1",
                    "confidence": "high",
                    "raises": [],
                    "hasTransaction": False,
                }],
            }],
        }
        inv_dir = tmp_path / "old" / "TestDb" / ".sys"
        inv_dir.mkdir(parents=True)
        inv_path = inv_dir / "inventory.json"
        inv_path.write_text(json.dumps(inv), encoding="utf-8")
        (tmp_path / "feats").mkdir()
        (tmp_path / "us").mkdir()
        return tmp_path

    def test_barrier_blocks_when_llm_us_missing(self, tmp_path):
        from sdd_reverse_scripts.build_proc_feats import main
        ws = self._make_inventory("fast", tmp_path)
        # No US file created → barrier should block
        rc = main(["--project", "TestDb", "--workspace", str(ws), "--all"])
        assert rc == 5, f"Expected exit 5 (barrier), got {rc}"

    def test_barrier_passes_when_tier_none(self, tmp_path):
        from sdd_reverse_scripts.build_proc_feats import main
        ws = self._make_inventory("none", tmp_path)
        # No US needed for tier=none → should assemble normally (exit 0)
        rc = main(["--project", "TestDb", "--workspace", str(ws), "--all"])
        assert rc == 0, f"Expected exit 0 (tier=none skips barrier), got {rc}"

    def test_force_bypasses_barrier(self, tmp_path):
        from sdd_reverse_scripts.build_proc_feats import main
        ws = self._make_inventory("fast", tmp_path)
        # --force skips the barrier check
        rc = main(["--project", "TestDb", "--workspace", str(ws), "--all", "--force"])
        assert rc == 0, f"Expected exit 0 with --force, got {rc}"


# ===========================================================================
# sql_body_analyzer — MERGE_DELETE + OUTPUT contract signals
# ===========================================================================

class TestSqlBodyAnalyzerSignals:

    def test_merge_delete_by_source_detected(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        body = textwrap.dedent("""\
            MERGE INTO dbo.Products AS tgt
            USING #staged AS src ON tgt.Id = src.Id
            WHEN MATCHED THEN UPDATE SET tgt.Price = src.Price
            WHEN NOT MATCHED BY TARGET THEN INSERT (Id, Price) VALUES (src.Id, src.Price)
            WHEN NOT MATCHED BY SOURCE THEN DELETE;
        """)
        result = analyze_routine("dbo.usp_SyncProducts", body)
        assert result.get("mergeDeleteBySource") is True, (
            "WHEN NOT MATCHED BY SOURCE THEN DELETE must set mergeDeleteBySource=True")
        assert "MERGE_DELETE" in result.get("writeKinds", {}), (
            "MERGE_DELETE must appear in writeKinds when mass-delete branch is present")

    def test_output_contract_detected(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        body = textwrap.dedent("""\
            INSERT INTO dbo.Orders (UserId, Amount)
            OUTPUT inserted.Id, inserted.CreatedAt
            VALUES (@UserId, @Amount);
        """)
        result = analyze_routine("dbo.usp_CreateOrder", body)
        assert result.get("outputContract") is True, (
            "OUTPUT without INTO must set outputContract=True (result set returned to caller)")

    def test_output_into_not_flagged_as_contract(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        body = textwrap.dedent("""\
            DECLARE @ids TABLE (Id INT);
            INSERT INTO dbo.Orders (UserId)
            OUTPUT inserted.Id INTO @ids
            VALUES (@UserId);
        """)
        result = analyze_routine("dbo.usp_InsertWithLog", body)
        assert result.get("outputContract") is False, (
            "OUTPUT...INTO @t is plumbing, not a contract — must not set outputContract=True")

    def test_merge_without_delete_branch_no_flag(self):
        from sdd_reverse.sql_body_analyzer import analyze_routine
        body = textwrap.dedent("""\
            MERGE INTO dbo.Clients AS tgt
            USING #src AS src ON tgt.Id = src.Id
            WHEN MATCHED THEN UPDATE SET tgt.Name = src.Name
            WHEN NOT MATCHED BY TARGET THEN INSERT (Id, Name) VALUES (src.Id, src.Name);
        """)
        result = analyze_routine("dbo.usp_UpsertClient", body)
        assert result.get("mergeDeleteBySource") is False, (
            "MERGE without BY SOURCE DELETE branch must not set mergeDeleteBySource")
