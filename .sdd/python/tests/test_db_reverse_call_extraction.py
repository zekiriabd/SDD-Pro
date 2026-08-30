"""test_db_reverse_call_extraction.py — regressions for the audit of 2026-08-29.

Two findings, one guarantee. The db-reverse module promises that a callee is
analysed BEFORE its caller ("wave ordering"), so that a procedure's User Story
can state what the procedures it delegates to actually do. That guarantee rests
entirely on the call graph being right, and the audit found the graph wrong on
three of the four supported engines.

**C1 — callee names truncated or dropped.** `sql_body_analyzer._CALL_RE` closed
its object capture with `(?!\\s*\\()`, a *content* constraint the regex engine
could satisfy by ending the identifier one character early. `CALL spB(1,2)`
therefore yielded the callee `sp`, `PERFORM fnB(1)` yielded `fn`. Worse, three
entire call FORMS were never matched in any dialect: a PL/SQL package call
(`pkg_util.do_thing(1);` — PL/SQL has no `EXEC` keyword at all), a scalar
function in an expression (`SELECT dbo.fnCalcVat(Amount)`), and a function in an
assignment (`v := fn_rate(1)`).

**C2 — the catalog was read and then ignored.** The engine's own dependency
catalog was merged into `dependencyGraph` and never reached `plan_waves`, which
ordered on regex output alone — on Oracle, the one engine where regex extraction
is inherently unreliable.

The first class of test below asserts the *extraction* is right. The second
asserts the *pipeline* is: a real body in, `analyze_routine` → `plan_waves` out,
with nothing hand-injected. That distinction is the point — the pre-existing
suite proved the wave algorithm by feeding it hand-written `callsProcs`, which
is exactly the input C1 showed was wrong.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_reverse.db_introspect import attach_catalog_calls, body_hash  # noqa: E402
from sdd_reverse.db_wave_planner import plan_waves, resolve_calls  # noqa: E402
from sdd_reverse.sql_body_analyzer import analyze_routine  # noqa: E402
from sdd_reverse.sql_dependency_graph import (  # noqa: E402
    build_dependency_graph,
    cohesion_modules,
    merge_catalog_dependencies,
)


def _all_callees(body: str, name: str = "dbo.caller") -> set[str]:
    """Every callee the analyzer found, whichever channel it used.

    `calls` holds keyword-anchored invocations; `callsInferred` holds the
    keyword-less ones. Both feed the graph — the split exists so that a
    heuristic match can never be reported as an *unresolved* callee, not to
    hide it from the reader.
    """
    sig = analyze_routine(name, body)
    return set(sig["calls"]) | set(sig["callsInferred"])


# --------------------------------------------------------------------------- #
# C1 — the five bodies the audit reproduced, one test each
# --------------------------------------------------------------------------- #

class TestCalleeNamesAreNeitherTruncatedNorDropped:

    def test_mysql_call_keeps_the_whole_name(self):
        """`CALL spB(1,2)` used to yield `sp` — the `B` was eaten by backtracking."""
        sig = analyze_routine("spA", "CREATE PROCEDURE spA() BEGIN CALL spB(1,2); END")
        assert sig["calls"] == ["spB"]
        assert "sp" not in sig["calls"]

    def test_postgres_perform_keeps_the_whole_name(self):
        """`PERFORM fnB(1)` used to yield `fn`."""
        body = ("CREATE FUNCTION fnA() RETURNS void AS $$ BEGIN "
                "PERFORM fnB(1); END $$;")
        sig = analyze_routine("fnA", body)
        assert sig["calls"] == ["fnB"]

    def test_tsql_exec_with_parenthesised_args_keeps_the_last_character(self):
        """`EXEC dbo.usp_Child(1)` used to yield `dbo.usp_Chil`."""
        sig = analyze_routine("dbo.spA", "EXEC dbo.usp_Child(1);")
        assert sig["calls"] == ["dbo.usp_Child"]

    def test_plsql_package_call_has_no_keyword_and_was_never_extracted(self):
        """PL/SQL has no `EXEC` inside a block: the call IS `pkg.proc(...)`."""
        body = ("CREATE OR REPLACE PROCEDURE p1(x NUMBER) IS BEGIN "
                "pkg_util.do_thing(1); END;")
        assert "pkg_util.do_thing" in _all_callees(body, "p1")

    def test_plsql_assignment_call_was_never_extracted(self):
        body = ("CREATE OR REPLACE PROCEDURE p2 IS v NUMBER; BEGIN "
                "v := fn_rate(1); END;")
        assert "fn_rate" in _all_callees(body, "p2")

    def test_tsql_scalar_function_inside_a_select_was_never_extracted(self):
        """The formula a procedure delegates to is very often exactly here."""
        body = ("CREATE PROCEDURE dbo.spX AS BEGIN "
                "SELECT dbo.fnCalcVat(Amount) FROM dbo.Orders; END")
        assert "dbo.fnCalcVat" in _all_callees(body, "dbo.spX")


class TestTheOldGuardsStillHold:
    """C1 replaced a lookahead; it must not have reopened what that guarded."""

    def test_dynamic_exec_is_a_flag_not_a_callee(self):
        sig = analyze_routine("dbo.spD", "EXEC(@sql);")
        assert sig["dynamicSql"] is True
        assert sig["calls"] == []
        assert sig["callsInferred"] == []

    def test_execute_as_is_a_security_clause_not_a_call(self):
        """The 2026-08-27 regression: 7 real procedures reported a callee `AS`."""
        body = "CREATE PROCEDURE dbo.spY WITH EXECUTE AS OWNER AS BEGIN SELECT 1; END"
        assert _all_callees(body, "dbo.spY") == set()

    def test_execute_immediate_is_dynamic_sql_not_a_callee_named_immediate(self):
        body = "BEGIN EXECUTE IMMEDIATE 'select 1 from dual'; END;"
        sig = analyze_routine("p", body)
        assert sig["dynamicSql"] is True
        assert "IMMEDIATE" not in [c.upper() for c in sig["calls"]]

    def test_plpgsql_execute_format_is_dynamic_sql(self):
        body = "BEGIN EXECUTE format('select %I', tbl); END"
        sig = analyze_routine("f", body)
        assert sig["dynamicSql"] is True
        assert "format" not in sig["calls"]

    def test_system_routines_are_not_business_dependencies(self):
        sig = analyze_routine("dbo.spS", "EXEC sp_executesql @sql;")
        assert sig["calls"] == []

    def test_builtins_and_keywords_are_not_inferred_calls(self):
        """The inferred scan is permissive by design; the filter is what makes
        it safe. A body full of `ISNULL(`, `CONVERT(`, `varchar(10)` and
        `EXISTS(` must not produce five phantom callees."""
        body = (
            "CREATE PROCEDURE dbo.spZ(@a int) AS BEGIN "
            "IF EXISTS(SELECT 1 FROM dbo.U WHERE Id = CONVERT(varchar(10), @a)) "
            "RAISERROR('x', 16, 1); "
            "SELECT ISNULL(MAX(Total), 0) FROM dbo.Orders; END"
        )
        inferred = analyze_routine("dbo.spZ", body)["callsInferred"]
        for noise in ("EXISTS", "CONVERT", "varchar", "ISNULL", "MAX", "RAISERROR"):
            assert noise.lower() not in {c.lower() for c in inferred}

    def test_create_header_parameters_do_not_make_a_routine_self_recursive(self):
        """`CREATE PROCEDURE dbo.spA(@a int)` reads exactly like a call to
        `dbo.spA`. Taken as one, EVERY routine in the database would be flagged
        recursive — which is why the header is skipped before the inferred scan.
        """
        body = "CREATE PROCEDURE dbo.spA(@a int) AS BEGIN SELECT 1; END"
        assert "dbo.spA" not in _all_callees(body, "dbo.spA")
        plan = plan_waves([_from_body("dbo.spA", body)])
        assert plan["metrics"]["dbo.spA"]["recursive"] is False


# --------------------------------------------------------------------------- #
# C1 end-to-end — real bodies through analyze_routine → plan_waves
# --------------------------------------------------------------------------- #

def _from_body(fq: str, body: str, routine_type: str = "SQL_STORED_PROCEDURE") -> dict:
    """One introspection-shaped object built from a REAL body.

    Nothing is hand-injected: `callsProcs` / `callsInferred` come out of the
    analyzer, which is the half of the pipeline C1 showed was broken. A test
    that writes `callsProcs` by hand proves the wave algorithm and nothing about
    the extraction feeding it.
    """
    sig = analyze_routine(fq, body)
    return {
        "fqName": fq,
        "routineType": routine_type,
        "callsProcs": sig["calls"],
        "callsInferred": sig["callsInferred"],
        "tablesRead": sig["tablesRead"],
        "tablesWritten": sig["tablesWritten"],
    }


# (dialect, caller fq, caller body, callee fq, callee body)
_DIALECT_PAIRS = [
    pytest.param(
        "mysql", "app.spOrder", "CREATE PROCEDURE spOrder() BEGIN CALL spStock(1,2); END",
        "app.spStock", "CREATE PROCEDURE spStock(a INT, b INT) BEGIN SELECT 1; END",
        id="mysql-CALL",
    ),
    pytest.param(
        "postgresql", "public.fn_order",
        "CREATE FUNCTION fn_order() RETURNS void AS $$ BEGIN PERFORM fn_stock(1); END $$;",
        "public.fn_stock",
        "CREATE FUNCTION fn_stock(a int) RETURNS void AS $$ BEGIN NULL; END $$;",
        id="postgresql-PERFORM",
    ),
    pytest.param(
        "oracle", "app.p_order",
        "CREATE OR REPLACE PROCEDURE p_order(x NUMBER) IS BEGIN p_stock(x); END;",
        "app.p_stock",
        "CREATE OR REPLACE PROCEDURE p_stock(x NUMBER) IS BEGIN NULL; END;",
        id="oracle-bare-call",
    ),
    pytest.param(
        "sqlserver", "dbo.usp_Order",
        "CREATE PROCEDURE dbo.usp_Order AS BEGIN "
        "SELECT dbo.fnCalcVat(Amount) FROM dbo.Orders; END",
        "dbo.fnCalcVat",
        "CREATE FUNCTION dbo.fnCalcVat(@a money) RETURNS money AS BEGIN RETURN @a * 0.2 END",
        id="sqlserver-scalar-function-in-expression",
    ),
]


@pytest.mark.parametrize("dialect,caller,caller_body,callee,callee_body", _DIALECT_PAIRS)
def test_callee_is_planned_strictly_before_its_caller(
    dialect, caller, caller_body, callee, callee_body,
):
    """The whole pipeline, per dialect: body text in, wave order out.

    Before C1 every one of these four put caller and callee in the SAME wave —
    the caller was analysed with no idea what it delegates to, which defeats the
    entire purpose of planning by waves.
    """
    objs = [_from_body(caller, caller_body), _from_body(callee, callee_body)]
    plan = plan_waves(objs)
    w = {fq: m["wave"] for fq, m in plan["metrics"].items()}
    assert w[callee] < w[caller], (
        f"[{dialect}] {callee} must be analysed before {caller}; got waves {w}"
    )


@pytest.mark.parametrize("dialect,caller,caller_body,callee,callee_body", _DIALECT_PAIRS)
def test_a_real_call_is_not_reported_as_an_unresolved_callee(
    dialect, caller, caller_body, callee, callee_body,
):
    """An unresolved callee downgrades the caller's confidence. A callee that
    exists and was merely mis-extracted must not cost the caller a downgrade."""
    objs = [_from_body(caller, caller_body), _from_body(callee, callee_body)]
    _, unresolved = resolve_calls(objs)
    assert unresolved == {}, f"[{dialect}] spurious unresolved callees: {unresolved}"


# --------------------------------------------------------------------------- #
# C2 — the catalog is authoritative and now reaches the planner
# --------------------------------------------------------------------------- #

class TestCatalogDependenciesReachTheWavePlanner:

    def test_catalog_edge_orders_a_call_the_regex_cannot_see(self):
        """The Oracle case, stated plainly.

        The caller's body hides its call inside dynamic SQL, so NO text scan can
        find it — `callsProcs` and `callsInferred` are both empty. The engine's
        dependency catalog knows about it. Before C2 that knowledge was merged
        into `dependencyGraph` and dropped on the floor for ordering purposes,
        so the two objects landed in the same wave.
        """
        caller_body = ("CREATE OR REPLACE PROCEDURE p_order IS BEGIN "
                       "EXECUTE IMMEDIATE 'begin app.p_stock(1); end;'; END;")
        caller = _from_body("app.p_order", caller_body)
        callee = _from_body(
            "app.p_stock", "CREATE OR REPLACE PROCEDURE p_stock IS BEGIN NULL; END;")

        # Precondition: the text really is a dead end for the regex.
        assert caller["callsProcs"] == []
        assert caller["callsInferred"] == []
        assert plan_waves([caller, callee])["metrics"]["app.p_order"]["wave"] == 0

        caller["catalogCalls"] = ["app.p_stock"]
        plan = plan_waves([caller, callee])
        w = {fq: m["wave"] for fq, m in plan["metrics"].items()}
        assert w["app.p_stock"] < w["app.p_order"], w

    def test_catalog_resolves_a_bare_name_the_regex_left_ambiguous(self):
        """Two schemas, one bare name. The regex cannot choose — and must not.
        The catalog names the schema, so the caller keeps a resolved edge AND
        stops being reported as having an unresolved callee."""
        objs = [
            {"fqName": "dbo.usp_Do"},
            {"fqName": "sales.usp_Do"},
            {"fqName": "dbo.usp_Caller", "callsProcs": ["usp_Do"],
             "catalogCalls": ["sales.usp_Do"]},
        ]
        edges, unresolved = resolve_calls(objs)
        assert ("dbo.usp_Caller", "sales.usp_Do") in edges
        assert unresolved == {}, "the catalog answered; nothing is unresolved"

    def test_without_catalog_data_an_ambiguous_name_is_still_refused(self):
        """The fallback must stay cautious: catalog absent means no guessing."""
        objs = [
            {"fqName": "dbo.usp_Do"},
            {"fqName": "sales.usp_Do"},
            {"fqName": "dbo.usp_Caller", "callsProcs": ["usp_Do"]},
        ]
        edges, unresolved = resolve_calls(objs)
        assert edges == []
        assert unresolved["dbo.usp_Caller"] == ["usp_Do"]

    def test_inferred_callees_never_produce_an_unresolved_report(self):
        """`INSERT INTO dbo.T (a, b)` is indistinguishable from a call. The
        heuristic channel must therefore be resolve-or-drop: a table name that
        matches no object costs nothing, where an unresolved report would
        downgrade the confidence of nearly every procedure in the database."""
        obj = _from_body(
            "dbo.spW",
            "CREATE PROCEDURE dbo.spW AS BEGIN INSERT INTO dbo.T (A, B) VALUES (1, 2); END")
        assert "dbo.T" in obj["callsInferred"]      # the heuristic did fire
        edges, unresolved = resolve_calls([obj])
        assert edges == [] and unresolved == {}


class TestAttachCatalogCalls:
    """The projection step: graph edges → per-routine `catalogCalls`."""

    def _model(self):
        procs = [
            _from_body("dbo.usp_A", "CREATE PROCEDURE dbo.usp_A AS BEGIN SELECT 1; END"),
            _from_body("dbo.usp_B", "CREATE PROCEDURE dbo.usp_B AS BEGIN SELECT 1; END"),
        ]
        return {"procedures": procs, "dependencyGraph": build_dependency_graph(procs)}

    def test_object_to_object_catalog_edge_becomes_a_catalog_call(self):
        model = self._model()
        merge_catalog_dependencies(
            model["dependencyGraph"],
            [("dbo", "usp_A", "dbo", "usp_B", "SQL_STORED_PROCEDURE")],
            ("from_schema", "from_name", "to_schema", "to_name", "dep_type"),
        )
        attach_catalog_calls(model)
        by_fq = {p["fqName"]: p for p in model["procedures"]}
        assert by_fq["dbo.usp_A"]["catalogCalls"] == ["dbo.usp_B"]
        assert "catalogCalls" not in by_fq["dbo.usp_B"]

    def test_table_dependencies_are_not_projected_as_calls(self):
        """A dependency on a table is already carried by tablesRead/Written and
        is not something the wave planner has any business ordering."""
        model = self._model()
        merge_catalog_dependencies(
            model["dependencyGraph"],
            [("dbo", "usp_A", "dbo", "Orders", "USER_TABLE")],
            ("from_schema", "from_name", "to_schema", "to_name", "dep_type"),
        )
        attach_catalog_calls(model)
        by_fq = {p["fqName"]: p for p in model["procedures"]}
        assert "catalogCalls" not in by_fq["dbo.usp_A"]

    def test_an_edge_known_to_both_sources_is_stamped_catalog_confirmed(self):
        """Where body scan and catalog agree, the catalog is the authority on
        provenance — that stamp is what `attach_catalog_calls` reads."""
        procs = [
            _from_body("dbo.usp_A",
                       "CREATE PROCEDURE dbo.usp_A AS BEGIN EXEC dbo.usp_B; END"),
            _from_body("dbo.usp_B", "CREATE PROCEDURE dbo.usp_B AS BEGIN SELECT 1; END"),
        ]
        model = {"procedures": procs, "dependencyGraph": build_dependency_graph(procs)}
        merge_catalog_dependencies(
            model["dependencyGraph"],
            [("dbo", "usp_A", "dbo", "usp_B", "SQL_STORED_PROCEDURE")],
            ("from_schema", "from_name", "to_schema", "to_name", "dep_type"),
        )
        sources = {e["source"] for e in model["dependencyGraph"]["edges"]
                   if e["to"] == "dbo.usp_B"}
        assert sources == {"body+catalog"}
        attach_catalog_calls(model)
        assert model["procedures"][0]["catalogCalls"] == ["dbo.usp_B"]


# --------------------------------------------------------------------------- #
# m3 — one callee-resolution policy, not two
# --------------------------------------------------------------------------- #

class TestDependencyGraphDoesNotGuess:

    def test_ambiguous_callee_becomes_external_not_an_arbitrary_pick(self):
        objs = [
            {"fqName": "dbo.usp_Do"},
            {"fqName": "sales.usp_Do"},
            {"fqName": "dbo.usp_Caller", "callsProcs": ["usp_Do"]},
        ]
        graph = build_dependency_graph(objs)
        calls = [e for e in graph["edges"] if e["rel"] == "calls"]
        assert len(calls) == 1
        target = calls[0]["to"]
        kinds = {n["id"]: n["type"] for n in graph["nodes"]}
        assert kinds[target] == "external", (
            "an ambiguous bare name must be reported as unresolved, not "
            f"silently attributed to one schema (got {target})"
        )

    def test_unambiguous_callee_still_resolves(self):
        objs = [{"fqName": "dbo.usp_Do"},
                {"fqName": "dbo.usp_Caller", "callsProcs": ["usp_Do"]}]
        graph = build_dependency_graph(objs)
        assert any(e["from"] == "dbo.usp_Caller" and e["to"] == "dbo.usp_Do"
                   for e in graph["edges"])

    def test_cohesion_homonyms_across_schemas_do_not_overwrite_each_other(self):
        """`by_tail` was a plain dict: the second `usp_Do` read replaced the
        first, so every call to the bare name was attributed to whichever one
        happened to be last."""
        objs = [
            {"fqName": "dbo.usp_Do", "tablesRead": ["dbo.A"]},
            {"fqName": "sales.usp_Do", "tablesRead": ["sales.B"]},
            {"fqName": "dbo.usp_Caller", "callsProcs": ["usp_Do"],
             "tablesRead": ["dbo.C"]},
        ]
        modules = cohesion_modules(objs)
        assert modules["dbo.usp_Do"] != modules["sales.usp_Do"], (
            "two objects sharing only a bare name must not be merged into one "
            "module on the strength of an ambiguous call"
        )

    def test_the_same_call_from_two_sources_is_one_edge(self):
        obj = _from_body(
            "dbo.usp_A",
            "CREATE PROCEDURE dbo.usp_A AS BEGIN EXEC dbo.usp_B; "
            "SELECT dbo.usp_B(1); END")
        objs = [obj, {"fqName": "dbo.usp_B"}]
        graph = build_dependency_graph(objs)
        calls = [e for e in graph["edges"]
                 if e["rel"] == "calls" and e["to"] == "dbo.usp_B"]
        assert len(calls) == 1, calls


# --------------------------------------------------------------------------- #
# M2 — the context version must see a body change of the same shape
# --------------------------------------------------------------------------- #

class TestBodyHash:

    def test_same_shape_different_constant_yields_a_different_hash(self):
        a = "CREATE PROCEDURE p AS BEGIN IF @x > 5 SELECT 1; END"
        b = "CREATE PROCEDURE p AS BEGIN IF @x > 7 SELECT 1; END"
        assert analyze_routine("p", a)["lineCount"] == analyze_routine("p", b)["lineCount"]
        assert body_hash(a) != body_hash(b)

    def test_encrypted_body_has_no_hash_rather_than_a_hash_of_nothing(self):
        assert body_hash("") == ""

    def test_hash_is_stable_across_a_trailing_newline(self):
        """`write_snapshot` normalises the trailing newline before writing, so
        the hash must agree with the file it will produce."""
        assert body_hash("SELECT 1") == body_hash("SELECT 1\n")
