"""Regressions for the Phase 1/Phase 2 audit findings F-03 and F-05.

F-03 (P0) — `deps_graph_builder` re-derived internal edges from a
namespace+`using` heuristic instead of consuming the type-usage-resolved
`code-graph.json` produced one phase earlier. On namespace-less legacy (the
common WebForms `App_Code/` case) it resolved nothing, so `internalEdges` was
empty and `deadCodeHint` listed the entire application. That list feeds
`reverse-tech-auditor` / `tech-audit.md` and the MIGRATE/DISCARD curation of
`/sdd-reverse-paradigm`.

F-05 (P1) — the four SQL dialects share `.sql` and share evidence patterns, so
a T-SQL file was claimed by all four buckets: artefacts emitted x4, and the
min-monotone confidence cap demoted a pure T-SQL app from `high` to `medium`.
"""

from __future__ import annotations

import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.code_graph_builder import build_code_graph            # noqa: E402
from sdd_reverse.db_schema_extractor import extract_db_schema          # noqa: E402
from sdd_reverse.deps_graph_builder import (                           # noqa: E402
    _edges_from_code_graph,
    _is_entry_point,
    build_deps_graph,
)
from sdd_reverse.paths import language_signatures_path                 # noqa: E402
from sdd_reverse.scan_legacy import load_signatures, scan_project      # noqa: E402


def _scan(root: Path):
    return scan_project(root, load_signatures(language_signatures_path()))


def _write_tree(root: Path, tree: dict[str, str]) -> Path:
    for rel, content in tree.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
# F-03 — internal edges resolved from the code graph
# --------------------------------------------------------------------------- #

# A WebForms app whose App_Code/ declares NO namespace — the exact shape the
# namespace heuristic could not resolve.
_NAMESPACELESS = {
    "App_Code/DataAccess.cs": (
        "using System;\n"
        "using System.Data.SqlClient;\n"
        "\n"
        "public static class DataAccess\n"
        "{\n"
        "    public static int? ValidateUser(string u, string p) { return 1; }\n"
        "}\n"
    ),
    "Login.aspx.cs": (
        "using System;\n"
        "using System.Web.UI;\n"
        "\n"
        "public partial class Login : Page\n"
        "{\n"
        "    protected void btnLogin_Click(object sender, EventArgs e)\n"
        "    {\n"
        '        int? id = DataAccess.ValidateUser("a", "b");\n'
        "    }\n"
        "}\n"
    ),
    "Login.aspx": (
        '<%@ Page Language="C#" CodeFile="Login.aspx.cs" Inherits="Login" %>\n'
        "<html><body><form runat=\"server\"></form></body></html>\n"
    ),
    "Web.config": '<?xml version="1.0"?><configuration><appSettings/></configuration>\n',
}


def test_namespaceless_legacy_still_yields_internal_edges(tmp_path):
    """F-03 : no `namespace` anywhere must NOT mean zero edges."""
    project = _write_tree(tmp_path / "LegacyBilling", _NAMESPACELESS)
    scan = _scan(project)

    # The weak heuristic alone (code_graph=None) resolves nothing here — this is
    # the pre-fix behaviour, pinned so the regression is unmistakable.
    assert build_deps_graph(project, scan)["internalEdges"] == []

    graph = build_deps_graph(project, scan, code_graph=build_code_graph(project, scan))
    edges = graph["internalEdges"]
    assert edges, "code-graph edges must be projected to file level"
    assert {"from": "Login.aspx.cs", "to": "App_Code/DataAccess.cs"} in [
        {"from": e["from"], "to": e["to"]} for e in edges
    ]
    assert graph["internalEdgesTotal"] == len(edges)


def test_namespaceless_legacy_is_not_all_dead_code(tmp_path):
    """F-03 : a live legacy must not be reported as 100% dead code."""
    project = _write_tree(tmp_path / "LegacyBilling", _NAMESPACELESS)
    scan = _scan(project)
    graph = build_deps_graph(project, scan, code_graph=build_code_graph(project, scan))

    source_files = {"App_Code/DataAccess.cs", "Login.aspx.cs"}
    assert not (source_files & set(graph["deadCodeHint"])), graph["deadCodeHint"]


def test_code_behind_is_an_entry_point_not_dead_code():
    """F-03 : `X.aspx.cs` is instantiated from markup, never referenced."""
    for rel in ("Login.aspx.cs", "Views/MainWindow.xaml.vb", "Ctl.ascx.cs",
                "Site.master.cs", "Program.cs", "Login.aspx"):
        assert _is_entry_point(rel), rel
    # Plain business classes stay eligible for the dead-code hint.
    for rel in ("App_Code/DataAccess.cs", "Services/Billing.cs"):
        assert not _is_entry_point(rel), rel


def test_edges_from_code_graph_collapses_same_file_and_duplicates():
    """Class-level edges project to file level: self-file dropped, dupes merged."""
    code_graph = {
        "classes": [
            {"name": "Login", "file": "Login.aspx.cs"},
            {"name": "LoginHelper", "file": "Login.aspx.cs"},   # same file
            {"name": "DataAccess", "file": "App_Code/DataAccess.cs"},
        ],
        "edges": [
            {"from": "Login", "to": "LoginHelper", "kind": "reference"},   # intra-file
            {"from": "Login", "to": "DataAccess", "kind": "reference",
             "evidence": "Login.aspx.cs:7"},
            {"from": "LoginHelper", "to": "DataAccess", "kind": "reference"},  # dup
        ],
    }
    assert _edges_from_code_graph(code_graph) == [{
        "from": "Login.aspx.cs",
        "to": "App_Code/DataAccess.cs",
        "kind": "reference",
        "evidence": "Login.aspx.cs:7",
    }]


def test_edges_from_code_graph_tolerates_garbage():
    for payload in (None, {}, {"classes": None, "edges": None},
                    {"classes": [], "edges": []},
                    {"classes": [{"name": "A"}], "edges": [{"from": "A", "to": "B"}]}):
        assert _edges_from_code_graph(payload) == []


# --------------------------------------------------------------------------- #
# F-05 — SQL dialects are mutually exclusive
# --------------------------------------------------------------------------- #

_TSQL = {
    "Scripts/Schema.sql": (
        "CREATE TABLE Users (\n"
        "    Id INT IDENTITY(1,1) PRIMARY KEY,\n"
        "    Login NVARCHAR(50) NOT NULL\n"
        ");\n"
        "GO\n"
        "CREATE VIEW vw_ActiveUsers AS SELECT Id, Login FROM Users;\n"
        "GO\n"
        "CREATE VIEW vw_UserCount AS SELECT COUNT(*) AS Total FROM Users;\n"
        "GO\n"
        "CREATE VIEW vw_Logins AS SELECT Login FROM Users;\n"
        "GO\n"
        "CREATE TRIGGER trg_UserAudit ON Users AFTER INSERT AS BEGIN SET NOCOUNT ON; END\n"
        "GO\n"
        "CREATE TRIGGER trg_UserDelete ON Users AFTER DELETE AS BEGIN SET NOCOUNT ON; END\n"
        "GO\n"
    ),
    "Scripts/Procs.sql": (
        "CREATE PROCEDURE sp_ValidateUser\n"
        "    @Login NVARCHAR(50)\n"
        "AS\n"
        "BEGIN\n"
        "    SELECT Id FROM Users WHERE Login = @Login;\n"
        "END\n"
        "GO\n"
    ),
}


def test_tsql_project_detects_exactly_one_dialect(tmp_path):
    """F-05 : `CREATE PROCEDURE` matches 4 dialects — only the best one wins."""
    project = _write_tree(tmp_path / "TsqlOnly", _TSQL)
    detected = {lm.id for lm in _scan(project).languages}
    assert detected == {"tsql"}, detected


def test_tsql_project_keeps_its_high_confidence_cap(tmp_path):
    """F-05 : phantom `medium`-capped dialects must not demote a T-SQL app."""
    project = _write_tree(tmp_path / "TsqlOnly", _TSQL)
    caps = {lm.id: lm.confidence_cap for lm in _scan(project).languages}
    assert caps == {"tsql": "high"}, caps


def test_sql_artefacts_are_not_emitted_once_per_dialect(tmp_path):
    """F-05 : 3 views / 2 triggers / deduped warnings — not x4."""
    project = _write_tree(tmp_path / "TsqlOnly", _TSQL)
    schema = extract_db_schema(project, _scan(project))

    assert [v["name"] for v in schema["views"]] == [
        "vw_ActiveUsers", "vw_UserCount", "vw_Logins"]
    assert [t["name"] for t in schema["triggers"]] == [
        "trg_UserAudit", "trg_UserDelete"]
    assert len(schema["parseWarnings"]) == len(set(schema["parseWarnings"]))


def test_each_dialect_still_wins_on_its_own_sources(tmp_path):
    """Exclusivity must select the RIGHT dialect, not merely one dialect."""
    cases = {
        "mysql": (
            "CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY) ENGINE=InnoDB;\n"
            "DELIMITER $$\n"
            "CREATE DEFINER=root@localhost PROCEDURE sp_v() BEGIN SELECT 1; END$$\n"
            "DELIMITER ;\n"
        ),
        "plpgsql": (
            "CREATE TABLE users (id SERIAL PRIMARY KEY);\n"
            "CREATE OR REPLACE FUNCTION f() RETURNS SETOF users AS $x$\n"
            "BEGIN RETURN QUERY SELECT * FROM users; END;\n"
            "$x$ LANGUAGE plpgsql;\n"
        ),
        "plsql": (
            "CREATE OR REPLACE PACKAGE BODY p AS\n"
            "  PROCEDURE v IS BEGIN EXECUTE IMMEDIATE 'SELECT 1 FROM dual';\n"
            "  EXCEPTION WHEN OTHERS THEN NULL; END;\n"
            "END p;\n"
        ),
    }
    for expected, content in cases.items():
        project = _write_tree(tmp_path / expected, {"schema.sql": content})
        detected = {lm.id for lm in _scan(project).languages}
        assert detected == {expected}, (expected, detected)


def test_sql_dialects_all_declare_the_exclusive_group():
    """Anti-rot: a 5th dialect added without the group reintroduces F-05."""
    signatures = load_signatures(language_signatures_path())
    sql_langs = [lang for lang in signatures["languages"]
                 if lang.get("family") == "sql"]
    assert len(sql_langs) >= 4
    for lang in sql_langs:
        assert lang.get("exclusive_group") == "sql-dialect", lang["id"]


# --------------------------------------------------------------------------- #
# F-05 (suite) — the winner must be the RIGHT dialect on realistic sources
#
# The fixtures above carry unmistakable markers (`LANGUAGE plpgsql`,
# `DELIMITER`, `PACKAGE BODY`), so exclusivity alone was enough to pass them.
# The real bench does not: a T-SQL "programmable objects" script is mostly
# `CREATE VIEW` / `CREATE PROCEDURE` / `CREATE FUNCTION`, DDL that all four
# engines share. With flat weights `plpgsql` (1.0 + 1.0) and `mysql` (1.0 + 1.0)
# both outscored `tsql` (1.0 + 0.7) on such a file and one of them won — the tie
# being broken by declaration order, so the confidence cap survived by luck
# rather than by correctness. These cases lock the discriminative weighting.
# --------------------------------------------------------------------------- #

_TSQL_BENCH = {
    # Verbatim shape of workspace/old/LegacyBilling/db/*.sql (gitignored bench).
    "db/01-schema.sql": (
        "CREATE TABLE Customer (\n"
        "    CustomerId   INT IDENTITY(1,1) PRIMARY KEY,\n"
        "    Name         NVARCHAR(200) NOT NULL,\n"
        "    CreditLimit  DECIMAL(18,2) NULL\n"
        ");\n"
        "CREATE TABLE Invoice (\n"
        "    InvoiceId  INT IDENTITY(1,1) PRIMARY KEY,\n"
        "    CustomerId INT NOT NULL REFERENCES Customer(CustomerId)\n"
        ");\n"
    ),
    "db/02-programmable.sql": (
        "CREATE VIEW vw_InvoiceTotals AS\n"
        "SELECT i.InvoiceId, SUM(l.Quantity * l.UnitPrice) AS GrossHT\n"
        "FROM Invoice i LEFT JOIN InvoiceLine l ON l.InvoiceId = i.InvoiceId\n"
        "GROUP BY i.InvoiceId;\n"
        "GO\n"
        "CREATE VIEW vw_CustomerOutstanding AS\n"
        "SELECT c.CustomerId, ISNULL(SUM(t.TotalHT), 0) AS Outstanding\n"
        "FROM Customer c LEFT JOIN vw_InvoiceTotals t ON 1 = 1\n"
        "GROUP BY c.CustomerId;\n"
        "GO\n"
        "CREATE FUNCTION fn_LateDays(@DueDate DATE) RETURNS INT AS\n"
        "BEGIN\n"
        "    RETURN DATEDIFF(DAY, @DueDate, GETDATE());\n"
        "END\n"
        "GO\n"
        "CREATE PROCEDURE sp_CloseInvoice\n"
        "    @InvoiceId INT\n"
        "AS\n"
        "BEGIN\n"
        "    UPDATE Invoice SET Status = 'PAID' WHERE InvoiceId = @InvoiceId;\n"
        "END\n"
        "GO\n"
        "CREATE TRIGGER trg_InvoiceAudit ON Invoice AFTER UPDATE AS BEGIN SELECT 1; END\n"
        "GO\n"
    ),
}


def test_shared_ddl_does_not_hand_a_tsql_file_to_another_dialect(tmp_path):
    """F-05 : `CREATE VIEW/FUNCTION/PROCEDURE` is not dialect evidence.

    Regression on the real bench shape — before the weighting fix, the
    programmable-objects file scored plpgsql 2.0 / mysql 2.0 / tsql 1.7 and was
    attributed to PL/pgSQL, on a script whose `GO`, `GETDATE()` and `@param`
    typing make it T-SQL beyond doubt.
    """
    project = _write_tree(tmp_path / "LegacyBilling", _TSQL_BENCH)
    result = _scan(project)

    assert {lm.id for lm in result.languages} == {"tsql"}
    tsql = result.languages[0]
    assert len(tsql.files) == 2, [f.name for f in tsql.files]
    assert tsql.confidence_cap == "high"


def test_shared_ddl_alone_never_opens_a_dialect_bucket(tmp_path):
    """A dialect must prove itself with EXCLUSIVE evidence, or be absorbed."""
    project = _write_tree(tmp_path / "SharedOnly", {
        "db/objects.sql": (
            "CREATE TABLE t (id INT);\n"
            "CREATE PROCEDURE p AS SELECT 1;\n"
            "CREATE FUNCTION f() RETURNS INT AS BEGIN RETURN 1; END\n"
        ),
    })
    detected = {lm.id for lm in _scan(project).languages}
    # Exactly one bucket, and the file is not lost.
    assert len(detected) == 1, detected
    assert len(_scan(project).languages[0].files) == 1


def test_a_single_phantom_file_cannot_demote_the_project_cap(tmp_path):
    """F-05 fallback: phantom dialects are excluded from the cap computation.

    `confidence_caps_applied` is min-monotone, so one `.sql` file attributed to
    a `medium`-capped engine used to drag a whole SQL Server application down.
    """
    tree = dict(_TSQL_BENCH)
    tree["db/03-misc.sql"] = "CREATE PROCEDURE sp_Misc AS SELECT 1;\n"
    project = _write_tree(tmp_path / "LegacyBilling", tree)

    caps = {lm.id: lm.confidence_cap for lm in _scan(project).languages}
    assert caps == {"tsql": "high"}, caps


def test_polyglot_repository_keeps_both_proven_dialects(tmp_path):
    """Absorption must not over-correct: proven dialects coexist."""
    project = _write_tree(tmp_path / "Polyglot", {
        "pg/schema.sql": (
            "CREATE TABLE users (id SERIAL PRIMARY KEY);\n"
            "CREATE OR REPLACE FUNCTION f() RETURNS SETOF users AS $x$\n"
            "BEGIN RETURN QUERY SELECT * FROM users; END;\n"
            "$x$ LANGUAGE plpgsql;\n"
        ),
        "my/schema.sql": (
            "CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY) ENGINE=InnoDB;\n"
            "DELIMITER $$\n"
            "CREATE DEFINER=root@localhost PROCEDURE sp_v() BEGIN SELECT 1; END$$\n"
        ),
    })
    detected = {lm.id for lm in _scan(project).languages}
    assert detected == {"plpgsql", "mysql"}, detected


def test_every_sql_dialect_declares_discriminative_evidence():
    """Anti-rot: a dialect with only shared DDL can never win an arbitration."""
    signatures = load_signatures(language_signatures_path())
    for lang in signatures["languages"]:
        if lang.get("exclusive_group") != "sql-dialect":
            continue
        discriminative = [ep for ep in lang["evidence_patterns"]
                          if ep.get("discriminative")]
        assert discriminative, lang["id"]
        # The exclusive markers must outweigh the shared DDL, otherwise the
        # arbitration falls back to declaration order (F-05's latent failure).
        shared = [ep for ep in lang["evidence_patterns"]
                  if not ep.get("discriminative")]
        assert min(ep["weight"] for ep in discriminative) > max(
            (ep["weight"] for ep in shared), default=0.0), lang["id"]
