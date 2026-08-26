"""M3 (audit 2026-08-25) — completeness review for DB-reverse modules.

`check_feat_completeness` only understood the CODE-reverse unit shape
(`units[].classes` + `dataAccess`). A DB-reverse unit carries
`units[].procedures`, so the checker had nothing to compare and returned a
vacuous "complete" — a green verdict that proved nothing, which is worse than an
absent check because it reads as reassurance.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse_scripts.check_feat_completeness import assess  # noqa: E402


def _unit(procs):
    return {"id": "U-1", "kind": "db-module", "suggestedName": "Contact",
            "procedures": procs}


def _proc(fq, **over):
    base = {"fqName": fq, "routineType": "SQL_STORED_PROCEDURE",
            "evidence": ".sys/proc-snapshot/x.sql:1-10", "tablesWritten": [],
            "tablesRead": [], "raises": [], "encrypted": False}
    base.update(over)
    return base


FEAT_FULL = """\
---
confidence: high
source-unit: U-1
---
# FEAT 1 — Contact

- SFD-2: Permettre de créer via `dbo.usp_Contact_Insert`.
- FD-1: Reproduire `dbo.usp_Contact_Insert` — écrit dbo.Contacts.
- BR-1: `dbo.usp_Contact_Insert` applique des préconditions (RAISERROR).
"""


class TestDbModuleIsActuallyAssessed:
    def test_a_missing_sql_object_is_a_serious_gap(self):
        """The old code returned "complete" here — nothing was compared at all."""
        unit = _unit([_proc("dbo.usp_Contact_Insert"),
                      _proc("dbo.usp_Contact_Purge")])
        report = assess(unit, FEAT_FULL)
        assert report["kind"] == "db-module"
        assert report["verdict"] == "incomplete"
        assert any(g["item"] == "dbo.usp_Contact_Purge"
                   and g["type"] == "sql_object_not_mentioned"
                   for g in report["gaps"])

    def test_fully_documented_module_is_complete(self):
        unit = _unit([_proc("dbo.usp_Contact_Insert",
                            tablesWritten=["dbo.Contacts"], raises=["RAISERROR"])])
        assert assess(unit, FEAT_FULL)["verdict"] == "complete"

    def test_dropped_business_rule_is_serious(self):
        """A RAISERROR with no trace in the FEAT is a lost rule, not a detail."""
        feat = FEAT_FULL.replace(
            "- BR-1: `dbo.usp_Contact_Insert` applique des préconditions (RAISERROR).", "")
        unit = _unit([_proc("dbo.usp_Contact_Insert", raises=["RAISERROR"])])
        report = assess(unit, feat)
        assert report["verdict"] == "incomplete"
        assert any(g["type"] == "raised_rule_not_mentioned" for g in report["gaps"])

    def test_undocumented_written_table_is_moderate(self):
        unit = _unit([_proc("dbo.usp_Contact_Insert",
                            tablesWritten=["dbo.Contacts", "dbo.AuditTrail"],
                            raises=["RAISERROR"])])
        report = assess(unit, FEAT_FULL)
        assert report["verdict"] == "partial"      # moderate only
        gap = next(g for g in report["gaps"]
                   if g["type"] == "written_table_not_mentioned")
        assert gap["item"] == "dbo.AuditTrail"
        assert gap["severity"] == "moderate"

    def test_leaf_name_in_the_feat_counts_as_mentioned(self):
        """Names are qualified since D1; a FEAT citing the leaf is not a gap."""
        unit = _unit([_proc("dbo.usp_Contact_Insert",
                            tablesWritten=["dbo.Contacts"], raises=["RAISERROR"])])
        feat = FEAT_FULL.replace("dbo.Contacts", "Contacts")
        assert assess(unit, feat)["verdict"] == "complete"

    def test_encrypted_object_is_reported_but_not_blamed(self):
        """An irreducible gap must be visible without faking an extraction failure."""
        unit = _unit([_proc("dbo.usp_Contact_Insert", encrypted=True,
                            tablesWritten=["dbo.Contacts"], raises=["RAISERROR"])])
        report = assess(unit, FEAT_FULL)
        assert report["verdict"] == "complete"     # info gaps do not degrade it
        assert any(g["type"] == "encrypted_object" for g in report["gaps"])
        assert report["summary"]["encrypted"] == 1

    def test_absent_object_does_not_cascade_derived_gaps(self):
        """One clear finding beats three restatements of the same omission."""
        unit = _unit([_proc("dbo.usp_Ghost", tablesWritten=["dbo.Ghosts"],
                            raises=["THROW"])])
        types = {g["type"] for g in assess(unit, FEAT_FULL)["gaps"]}
        assert types == {"sql_object_not_mentioned"}

    def test_summary_counts_sql_objects(self):
        unit = _unit([_proc("dbo.a"), _proc("dbo.b"), _proc("dbo.c")])
        assert assess(unit, FEAT_FULL)["summary"]["sqlObjects"] == 3


class TestCodeReverseUnitsAreUnaffected:
    def test_class_based_unit_still_uses_the_code_rubric(self):
        unit = {"id": "U-2", "classes": [
            {"name": "OrderService", "role": "service", "file": "a.cs", "lines": "1-9"}]}
        report = assess(unit, "# FEAT with no mention")
        assert report.get("kind") != "db-module"
        assert any(g["type"] == "class_not_mentioned" for g in report["gaps"])
