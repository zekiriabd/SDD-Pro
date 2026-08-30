"""Regressions for the 2026-08-29 db-reverse audit — M2 and m1.

**M2 — drift detection under-reported.** `context_version()` is the cache key AND
the drift key: an unchanged version means "the database has not moved", which
lets the run reuse the architect's cached interpretation and lets
`diff_contexts` stay silent. The facts it hashed described only the SHAPE of
each object — line count, parameters, tables touched, call list, branch count.
Change a threshold inside an existing `IF` and every one of those stays
identical, so a routine whose behaviour had moved produced a byte-identical
context version. The docstring claimed the opposite ("any structural change —
including a body change — changes the version").

**m1 — `NVARCHAR(MAX)` reported as bounded.** SQL Server encodes `(max)` as
`max_length = -1`. `_render_type` excluded `-1` from its membership filter
*before* the branch that renders `(max)` could ever run, so an unbounded column
came back as the bare type name in the artefact a Tech Lead reads to size a
migration — the one place where "unbounded" is the load-bearing fact.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_reverse.db_context import build_context, context_version, diff_contexts  # noqa: E402
from sdd_reverse.db_introspect import build_introspection  # noqa: E402
from sdd_reverse.db_schema_live import _render_type  # noqa: E402
from sdd_reverse.dialects import get_dialect  # noqa: E402

_DIALECT = get_dialect("sqlserver")

# Same shape, same line count, same tables, same branch — one different constant.
_BODY_A = (
    "CREATE PROCEDURE dbo.usp_Remise AS\n"
    "BEGIN\n"
    "    IF @Montant > 1000\n"
    "        UPDATE dbo.Commande SET Remise = 10;\n"
    "END\n"
)
_BODY_B = _BODY_A.replace("> 1000", "> 5000")


def _introspection(body: str) -> dict:
    rows = [("dbo", "usp_Remise", "SQL_STORED_PROCEDURE", body, None, 0)]
    return build_introspection(rows, _DIALECT, server="h", database="Db")


class TestContextVersionCoversTheBody:

    def test_the_two_bodies_really_are_shape_identical(self):
        """Guards the test itself: if the shapes diverged, the assertion below
        would pass for the wrong reason."""
        a = _introspection(_BODY_A)["procedures"][0]
        b = _introspection(_BODY_B)["procedures"][0]
        for field in ("lineCount", "branches", "params", "tablesRead",
                      "tablesWritten", "writeKinds", "callsProcs"):
            assert a[field] == b[field], field

    def test_a_value_only_body_edit_changes_the_context_version(self):
        va = context_version(build_context(_introspection(_BODY_A))["facts"])
        vb = context_version(build_context(_introspection(_BODY_B))["facts"])
        assert va != vb, (
            "a threshold moved from 1000 to 5000 and the context version did "
            "not budge — the architect's cached hypotheses would be reused "
            "against a database whose rules have changed"
        )

    def test_an_unchanged_body_still_reuses_the_context(self):
        """The other half of the contract: this must not become a cache that
        never hits."""
        ctx = build_context(_introspection(_BODY_A), project="Db")
        again = build_context(_introspection(_BODY_A), project="Db", prior=ctx)
        assert again["reuse"]["reused"] is True

    def test_diff_reports_the_object_as_changed_and_to_be_re_analysed(self):
        old = build_context(_introspection(_BODY_A), project="Db")
        new = build_context(_introspection(_BODY_B), project="Db")
        report = diff_contexts(old, new)
        assert report["identical"] is False
        changed = {c["object"]: c["changed"] for c in report["objects"]["changed"]}
        assert "body" in changed.get("dbo.usp_Remise", [])
        assert "dbo.usp_Remise" in report["reAnalysisRequired"]

    def test_body_hash_is_carried_into_the_facts(self):
        facts = build_context(_introspection(_BODY_A))["facts"]
        assert facts["objects"][0]["bodyHash"].startswith("sha256:")


class TestMaxLengthRendering:

    def test_nvarchar_max_is_rendered_as_max_not_as_bounded(self):
        assert _render_type({"data_type": "nvarchar", "max_length": -1}) == "nvarchar(max)"

    def test_varchar_and_varbinary_max_too(self):
        assert _render_type({"data_type": "varchar", "max_length": -1}) == "varchar(max)"
        assert _render_type({"data_type": "varbinary", "max_length": -1}) == "varbinary(max)"

    def test_bounded_unicode_length_is_still_halved(self):
        """SQL Server reports nvarchar(50) as 100 bytes; m1 must not disturb it."""
        assert _render_type({"data_type": "nvarchar", "max_length": 100}) == "nvarchar(50)"

    def test_non_string_types_are_still_left_alone(self):
        assert _render_type({"data_type": "int", "max_length": 4}) == "int"

    def test_precision_types_are_untouched(self):
        assert _render_type(
            {"data_type": "decimal", "max_length": 9, "precision": 18, "scale": 2}
        ) == "decimal(18,2)"
