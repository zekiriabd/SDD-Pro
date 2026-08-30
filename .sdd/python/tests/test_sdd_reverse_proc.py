"""test_sdd_reverse_proc.py — DB stored-procedure reverse (offline, no database).

Covers the deterministic core of the db-reverse flavor:
  - readonly_guard       : the hard read-only barrier
  - dialects             : registry + read-only catalog queries
  - sql_body_analyzer    : signal extraction + confidence downgrade
  - proc_module_clusterer: procs → business modules (1 module = 1 FEAT)
  - stack_db_config      : connection params from stack.md (masked)
  - db_introspect        : pure build_introspection + write_snapshot (synthetic rows)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse import db_introspect as dbi  # noqa: E402
from sdd_reverse.dialects import (  # noqa: E402
    ROUTINE_COLUMNS,
    UnsupportedDialect,
    get_dialect,
    supported_db_types,
)
from sdd_reverse.proc_module_clusterer import cluster, parse_routine_name  # noqa: E402
from sdd_reverse.readonly_guard import (  # noqa: E402
    ReadOnlyViolation,
    assert_readonly,
    is_readonly,
)
from sdd_reverse.sql_body_analyzer import (  # noqa: E402
    analyze_routine,
    confidence_signal,
    proc_complexity,
)
from sdd_reverse.stack_db_config import StackConfigError, read_db_config  # noqa: E402

# --------------------------------------------------------------------------- #
# Sample T-SQL bodies
# --------------------------------------------------------------------------- #

PROC_INSERT = """\
CREATE PROCEDURE dbo.usp_Contact_Insert
    @Name nvarchar(100),
    @Email nvarchar(200),
    @ContactId int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM Contacts WHERE Email = @Email)
        RAISERROR('Duplicate email', 16, 1);
    BEGIN TRAN;
    INSERT INTO Contacts (Name, Email) VALUES (@Name, @Email);
    SET @ContactId = SCOPE_IDENTITY();
    COMMIT;
END
"""

PROC_DYNAMIC = """\
CREATE PROCEDURE dbo.usp_Report_Run @filter nvarchar(max) AS
BEGIN
    DECLARE @sql nvarchar(max) = N'SELECT * FROM Sales WHERE ' + @filter;
    EXEC sp_executesql @sql;
END
"""


# --------------------------------------------------------------------------- #
# readonly_guard
# --------------------------------------------------------------------------- #

def test_guard_accepts_catalog_select():
    assert is_readonly("SELECT name FROM sys.procedures")
    assert is_readonly(
        "SELECT m.definition FROM sys.sql_modules m JOIN sys.objects o "
        "ON o.object_id = m.object_id"
    )


@pytest.mark.parametrize("sql", [
    "DROP TABLE Users",
    "DELETE FROM Orders",
    "TRUNCATE TABLE Logs",
    "UPDATE Users SET x = 1",
    "INSERT INTO T VALUES (1)",
    "ALTER PROCEDURE dbo.x AS SELECT 1",
    "EXEC dbo.usp_Delete_Everything",
    "SELECT * INTO #tmp FROM sys.objects",     # materialises a table
    "SELECT 1; DROP TABLE T",                  # statement batching
    "CREATE PROCEDURE foo AS SELECT 1",
])
def test_guard_rejects_mutations(sql):
    assert not is_readonly(sql)
    with pytest.raises(ReadOnlyViolation):
        assert_readonly(sql)


def test_guard_ignores_comment_tokens():
    assert is_readonly("SELECT 1 -- DROP TABLE T\nFROM sys.objects")


# --------------------------------------------------------------------------- #
# dialects
# --------------------------------------------------------------------------- #

def test_sqlserver_dialect_queries_are_readonly():
    d = get_dialect("SqlServer")
    assert d.language_id == "tsql"
    assert is_readonly(d.list_routines_sql)
    assert is_readonly(d.single_routine_sql)
    assert "sqlserver" in supported_db_types()


def test_postgresql_dialect_queries_are_readonly():
    d = get_dialect("PostgreSQL")
    assert d.language_id == "plpgsql"
    assert is_readonly(d.list_routines_sql)
    assert is_readonly(d.single_routine_sql)
    assert get_dialect("postgres").id == "postgresql"


def test_dialect_aliases_and_unsupported():
    assert get_dialect("mssql").id == "sqlserver"
    # Oracle + MySQL are now implemented (4 principal engines, 2026-07-24).
    assert get_dialect("Oracle").id == "oracle"
    assert get_dialect("MySQL").id == "mysql"
    with pytest.raises(UnsupportedDialect):
        get_dialect("db2")             # planned, not yet implemented
    with pytest.raises(UnsupportedDialect):
        get_dialect("cassandra")       # unknown


# --------------------------------------------------------------------------- #
# sql_body_analyzer
# --------------------------------------------------------------------------- #

def test_analyze_insert_proc():
    sig = analyze_routine("dbo.usp_Contact_Insert", PROC_INSERT)
    assert "Contacts" in sig["tablesWritten"]
    assert sig["branches"] >= 1
    assert "RAISERROR" in sig["raises"]
    assert sig["hasTransaction"] is True
    assert sig["dynamicSql"] is False
    names = {p["name"] for p in sig["params"]}
    assert {"@Name", "@Email", "@ContactId"} <= names
    assert any(p["name"] == "@ContactId" and p["output"] for p in sig["params"])
    assert confidence_signal(sig, "high") == "high"


def test_analyze_dynamic_sql_downgrades():
    sig = analyze_routine("dbo.usp_Report_Run", PROC_DYNAMIC)
    assert sig["dynamicSql"] is True
    assert confidence_signal(sig, "high") == "medium"


def test_encrypted_body_confidence_low():
    sig = analyze_routine("dbo.usp_Secret", "")
    assert confidence_signal(sig, "high") == "low"


# --------------------------------------------------------------------------- #
# proc_module_clusterer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,verb,obj", [
    ("usp_Contact_Insert", "create", "Contact"),
    ("usp_Contact_Delete", "delete", "Contact"),
    ("usp_GetContactList", "read", "Contact"),
    ("sp_UpdateOrder", "update", "Order"),
    ("usp_Order_Create", "create", "Order"),
])
def test_parse_routine_name(raw, verb, obj):
    p = parse_routine_name(raw)
    assert p["verb"] == verb
    assert p["object"] == obj


def test_cluster_groups_by_module():
    routines = [
        {"name": "usp_Contact_Insert"},
        {"name": "usp_Contact_Delete"},
        {"name": "usp_GetContactList"},
        {"name": "usp_Order_Create"},
        {"name": "usp_UpdateOrder"},
    ]
    modules = cluster(routines)
    assert set(modules) == {"Contact", "Order"}
    assert len(modules["Contact"]) == 3
    assert len(modules["Order"]) == 2


def test_cluster_fallback_to_written_table():
    # verb-only name → no derivable object → fall back to the written table
    routines = [{"name": "usp_Process", "signals": {"tablesWritten": ["Invoices"]}}]
    modules = cluster(routines)
    assert "Invoice" in modules     # singularised from Invoices


# --------------------------------------------------------------------------- #
# stack_db_config
# --------------------------------------------------------------------------- #

STACK_MD = """\
# Stack

## Active Database

- DatabaseType: SqlServer
- DB_HOST: sqlprd01
- DB_PORT: 1433
- DB_NAME: OrdersDb
- DB_USER: reverse_reader
- DB_PASSWORD: s3cr3t!

## Active Backend

- BackendName: Api
"""


def test_read_db_config_and_mask(tmp_path):
    sp = tmp_path / "stack.md"
    sp.write_text(STACK_MD, encoding="utf-8")
    cfg = read_db_config(sp)
    cfg.require_complete()
    assert cfg.db_type == "SqlServer"
    assert cfg.host == "sqlprd01"
    assert cfg.name == "OrdersDb"
    assert cfg.password == "s3cr3t!"
    masked = cfg.masked()
    assert "s3cr3t" not in masked
    assert "***" in masked


def test_read_db_config_missing_section(tmp_path):
    sp = tmp_path / "stack.md"
    sp.write_text("# Stack\n\n## Active Backend\n- BackendName: Api\n", encoding="utf-8")
    with pytest.raises(StackConfigError):
        read_db_config(sp)


def test_require_complete_missing_keys(tmp_path):
    sp = tmp_path / "stack.md"
    sp.write_text("## Active Database\n- DatabaseType: SqlServer\n", encoding="utf-8")
    cfg = read_db_config(sp)
    with pytest.raises(StackConfigError):
        cfg.require_complete()


STACK_MD_ENV = """\
## Active Database
 - DatabaseType: PostgreSQL
 - DB_HOST: ${DB_HOST}
 - DB_PORT: ${DB_PORT}
 - DB_NAME: ${DB_NAME}
 - DB_USER: ${DB_USER}
 - DB_PASSWORD: ${DB_PASSWORD}
"""


def test_env_var_placeholders_resolved(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "CMSPrint")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", "cmsprint.")
    sp = tmp_path / "stack.md"
    sp.write_text(STACK_MD_ENV, encoding="utf-8")
    cfg = read_db_config(sp)
    cfg.require_complete()
    assert cfg.host == "127.0.0.1"
    assert cfg.name == "CMSPrint"
    assert cfg.password == "cmsprint."
    assert "cmsprint" not in cfg.masked()


def test_env_var_placeholder_unset_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_DOES_NOT_EXIST_XYZ", raising=False)
    sp = tmp_path / "stack.md"
    sp.write_text("## Active Database\n- DB_HOST: ${DB_DOES_NOT_EXIST_XYZ}\n", encoding="utf-8")
    with pytest.raises(StackConfigError):
        read_db_config(sp)


# --------------------------------------------------------------------------- #
# db_introspect — pure build + snapshot (synthetic rows, no DB)
# --------------------------------------------------------------------------- #

def _row(schema, name, rtype, definition, encrypted=False):
    # tuple in ROUTINE_COLUMNS order
    assert ROUTINE_COLUMNS == ("schema", "name", "routine_type", "definition", "modified", "is_encrypted")
    return (schema, name, rtype, definition, "2025-11-03", 1 if encrypted else 0)


def test_build_and_snapshot(tmp_path):
    d = get_dialect("SqlServer")
    rows = [
        _row("dbo", "usp_Contact_Insert", "SQL_STORED_PROCEDURE", PROC_INSERT),
        _row("dbo", "usp_Report_Run", "SQL_STORED_PROCEDURE", PROC_DYNAMIC),
        _row("dbo", "usp_Secret", "SQL_STORED_PROCEDURE", None, encrypted=True),
    ]
    model = dbi.build_introspection(
        rows, d, server="sqlprd01", database="OrdersDb", lang_cap="high"
    )
    assert model["summary"]["proceduresCount"] == 3
    assert model["summary"]["encryptedCount"] == 1
    assert "password" not in json.dumps(model).lower()  # no secret leaked

    written = dbi.write_snapshot(tmp_path, model)
    snap_dir = tmp_path / ".sys" / "proc-snapshot"
    assert (snap_dir / "dbo.usp_Contact_Insert.sql").is_file()
    assert (tmp_path / ".sys" / "db-introspection.json").is_file()

    p0 = written["procedures"][0]
    assert p0["evidence"].startswith(".sys/proc-snapshot/dbo.usp_Contact_Insert.sql:1-")
    from sdd_reverse.feat_structure_spec import EVIDENCE_COMMENT_RE
    assert EVIDENCE_COMMENT_RE.search(f"<!-- evidence: {p0['evidence']} -->")
    assert "_body" not in p0  # stripped after snapshot

    enc = next(p for p in written["procedures"] if p["name"] == "usp_Secret")
    assert enc["encrypted"] is True
    body = (snap_dir / "dbo.usp_Secret.sql").read_text(encoding="utf-8")
    assert "[REVERSE_PROC_ENCRYPTED]" in body


def test_callgraph_built():
    """Audit 2026-08-25 (D1): the edge TARGET is now qualified like the source.

    It used to be `{"from": "dbo.usp_A", "to": "usp_B"}` — a target that could
    never match a node, since every node is keyed by `fqName` (`dbo.usp_B`).
    Qualifying the capture made the graph actually connect.
    """
    d = get_dialect("SqlServer")
    body = "CREATE PROCEDURE dbo.usp_A AS BEGIN EXEC dbo.usp_B; END"
    model = dbi.build_introspection(
        [_row("dbo", "usp_A", "P", body)], d, server="h", database="db"
    )
    assert {"from": "dbo.usp_A", "to": "dbo.usp_B"} in model["callGraph"]


def test_callgraph_target_shape_matches_node_keys():
    """An edge must be resolvable against the procedures' own fqName keys."""
    d = get_dialect("SqlServer")
    rows = [
        _row("dbo", "usp_A", "P", "CREATE PROCEDURE dbo.usp_A AS BEGIN EXEC dbo.usp_B; END"),
        _row("dbo", "usp_B", "P", "CREATE PROCEDURE dbo.usp_B AS BEGIN SELECT 1; END"),
    ]
    model = dbi.build_introspection(rows, d, server="h", database="db")
    node_keys = {p["fqName"] for p in model["procedures"]}
    targets = {e["to"] for e in model["callGraph"]}
    assert targets <= node_keys, f"unresolvable edge targets: {targets - node_keys}"


def test_system_routine_calls_are_not_dependencies():
    """N3: `EXEC sp_executesql @sql` is not a business edge."""
    d = get_dialect("SqlServer")
    body = ("CREATE PROCEDURE dbo.usp_Dyn AS BEGIN "
            "EXEC sp_executesql @sql; EXEC dbo.usp_Real; END")
    model = dbi.build_introspection(
        [_row("dbo", "usp_Dyn", "P", body)], d, server="h", database="db"
    )
    targets = {e["to"] for e in model["callGraph"]}
    assert "dbo.usp_Real" in targets
    assert not any("executesql" in t.lower() for t in targets)


# --------------------------------------------------------------------------- #
# End-to-end deterministic chain (no DB): introspection → inventory → FEAT,
# and the generated FEATs MUST pass the real validate_reverse_feat validator.
# --------------------------------------------------------------------------- #

PROC_DELETE = """\
CREATE PROCEDURE dbo.usp_Contact_Delete @ContactId int AS
BEGIN
    DELETE FROM Contacts WHERE Id = @ContactId;
END
"""
PROC_LIST = """\
CREATE PROCEDURE dbo.usp_GetContactList AS
BEGIN
    SELECT Id, Name, Email FROM Contacts ORDER BY Name;
END
"""
PROC_ORDER = """\
CREATE PROCEDURE dbo.usp_Order_Create @CustomerId int, @OrderId int OUTPUT AS
BEGIN
    BEGIN TRAN;
    INSERT INTO Orders (CustomerId) VALUES (@CustomerId);
    SET @OrderId = SCOPE_IDENTITY();
    COMMIT;
END
"""


def test_full_chain_offline_feats_validate(tmp_path):
    from sdd_reverse_scripts import build_proc_feats, reverse_proc_introspect
    from sdd_reverse_scripts.validate_reverse_feat import validate_feat

    d = get_dialect("SqlServer")
    rows = [
        _row("dbo", "usp_Contact_Insert", "SQL_STORED_PROCEDURE", PROC_INSERT),
        _row("dbo", "usp_Contact_Delete", "SQL_STORED_PROCEDURE", PROC_DELETE),
        _row("dbo", "usp_GetContactList", "SQL_STORED_PROCEDURE", PROC_LIST),
        _row("dbo", "usp_Order_Create", "SQL_STORED_PROCEDURE", PROC_ORDER),
    ]
    project = "OrdersDb"
    project_root = tmp_path / "old" / project
    project_root.mkdir(parents=True)
    model = dbi.build_introspection(rows, d, server="sqlprd01", database=project, lang_cap="high")
    dbi.write_snapshot(project_root, model)
    intro_json = project_root / ".sys" / "db-introspection.json"

    rc = reverse_proc_introspect.main(
        ["--from-introspection", str(intro_json), "--project", project, "--workspace", str(tmp_path)]
    )
    assert rc == 0
    inventory = json.loads((project_root / ".sys" / "inventory.json").read_text(encoding="utf-8"))
    mods = {u["suggestedName"] for u in inventory["units"]}
    assert "Contact" in mods and "Order" in mods
    contact = next(u for u in inventory["units"] if u["suggestedName"] == "Contact")
    assert len(contact["procedures"]) == 3   # 1 proc = 1 US

    rc = build_proc_feats.main(["--project", project, "--all", "--workspace", str(tmp_path)])
    assert rc == 0

    feats = list((tmp_path / "feats").glob("*.md"))
    assert len(feats) == 2
    for feat in feats:
        ok, errors, _warns = validate_feat(feat)
        assert ok, f"{feat.name} failed validation: {errors}"


# --------------------------------------------------------------------------- #
# Complexity routing (token efficiency) + deterministic 0-token US
# --------------------------------------------------------------------------- #

def test_proc_complexity_routing():
    assert proc_complexity(analyze_routine("x", PROC_LIST)) == "simple"     # plain SELECT
    assert proc_complexity(analyze_routine("x", PROC_INSERT)) == "complex"  # IF EXISTS + RAISERROR
    assert proc_complexity(analyze_routine("x", PROC_DYNAMIC)) == "complex" # dynamic SQL
    assert proc_complexity({"encrypted": True}) == "simple"                 # body unreadable → deterministic


def test_build_proc_us_routes_simple_vs_complex(tmp_path, capsys):
    from sdd_reverse_scripts import build_proc_us, reverse_proc_introspect

    d = get_dialect("SqlServer")
    rows = [
        _row("dbo", "usp_Contact_Insert", "P", PROC_INSERT),   # complex (branch + raise)
        _row("dbo", "usp_GetContactList", "P", PROC_LIST),     # simple (plain SELECT)
    ]
    project = "OrdersDb"
    project_root = tmp_path / "old" / project
    project_root.mkdir(parents=True)
    model = dbi.build_introspection(rows, d, server="h", database=project, lang_cap="high")
    dbi.write_snapshot(project_root, model)
    reverse_proc_introspect.main(
        ["--from-introspection", str(project_root / ".sys" / "db-introspection.json"),
         "--project", project, "--workspace", str(tmp_path)]
    )
    capsys.readouterr()

    rc = build_proc_us.main(["--project", project, "--all", "--workspace", str(tmp_path), "--json"])
    assert rc == 0
    # the simple SELECT proc got a deterministic US; the complex one is routed to the LLM
    us_files = [p.name for p in (tmp_path / "us").glob("*.md")]
    assert any("Consulter-Contact" in f for f in us_files)
    assert not any("Creer-Contact" in f for f in us_files)

    out = json.loads(capsys.readouterr().out)
    # Mineur 2 (2026-08-30) : needs_llm porte le chemin RÉEL du pack (règle
    # _safe du slicer), jamais le fqName brut interpolé.
    entry = next(e for e in out["needs_llm"] if e["proc"] == "dbo.usp_Contact_Insert")
    assert entry["pack"] == ".sys/db-context/packs/dbo.usp_Contact_Insert.md"
    # D-M4 (2026-08-30) : le verdict de routage rung 2 est émis par le script,
    # par module — multi-objets + ≥1 objet routé LLM ⇒ composer LLM.
    contact = next(m for m in out["modules"] if m["module"] == "Contact")
    assert contact["objects"] == 2
    assert contact["llmRouted"] == 1
    assert contact["featComposer"] == "llm"


# --------------------------------------------------------------------------- #
# Incremental merge — a second proc of the same object GROWS the same FEAT
# --------------------------------------------------------------------------- #

def test_incremental_merge_grows_module_stable(tmp_path):
    from sdd_reverse_scripts.reverse_proc_introspect import build_inventory

    d = get_dialect("SqlServer")
    project_root = tmp_path / "old" / "OrdersDb"
    project_root.mkdir(parents=True)
    feats = tmp_path / "feats"

    # First proc of module Contact → FEAT n=1, U-1, usIndex 1
    model_a = dbi.build_introspection(
        [_row("dbo", "usp_Contact_Insert", "P", PROC_INSERT)], d, server="h", database="OrdersDb")
    dbi.write_snapshot(project_root, model_a)
    inv_a = build_inventory(model_a, project="OrdersDb", feats_dir=feats, prior=None)
    contact_a = next(u for u in inv_a["units"] if u["suggestedName"] == "Contact")
    assert inv_a["_featAllocations"][contact_a["id"]] == 1
    assert len(contact_a["procedures"]) == 1
    insert_idx = contact_a["procedures"][0]["usIndex"]

    # Second proc of the SAME object → MERGE, must reuse n=1/U-1 and grow to 2 US
    model_b = dbi.build_introspection(
        [_row("dbo", "usp_Contact_Delete", "P", PROC_DELETE)], d, server="h", database="OrdersDb")
    dbi.write_snapshot(project_root, model_b)
    merged = dbi.merge_introspection(model_a, model_b)
    assert merged["summary"]["proceduresCount"] == 2

    inv_b = build_inventory(merged, project="OrdersDb", feats_dir=feats, prior=inv_a)
    contact_b = next(u for u in inv_b["units"] if u["suggestedName"] == "Contact")
    assert contact_b["id"] == contact_a["id"]                       # stable U-id
    assert inv_b["_featAllocations"][contact_b["id"]] == 1          # stable FEAT number
    assert len(contact_b["procedures"]) == 2                        # GREW, not clobbered
    fqs = {p["fqName"] for p in contact_b["procedures"]}
    assert fqs == {"dbo.usp_Contact_Insert", "dbo.usp_Contact_Delete"}
    # the original proc keeps its usIndex; the new one gets a distinct one
    by_fq = {p["fqName"]: p["usIndex"] for p in contact_b["procedures"]}
    assert by_fq["dbo.usp_Contact_Insert"] == insert_idx
    assert by_fq["dbo.usp_Contact_Delete"] != insert_idx

    # merge-safe snapshot: re-writing keeps the existing .sql bodies intact
    dbi.write_snapshot(project_root, merged)
    insert_sql = (project_root / ".sys" / "proc-snapshot" / "dbo.usp_Contact_Insert.sql").read_text(encoding="utf-8")
    assert "INSERT INTO Contacts" in insert_sql
