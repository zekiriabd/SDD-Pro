"""test_sdd_reverse_l1_extraction.py — L1 deep technical extraction.

Covers the previously-0% capabilities: inline SQL, stored-procedure calls +
definitions (with params), connection strings (masked), full library/DLL
inventory, ORM field fill.
"""

from __future__ import annotations

import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.config_extractor import (  # noqa: E402
    mask_secrets,
    parse_appsettings_json,
    parse_dotnet_connection_strings,
)
from sdd_reverse.data_access_extractor import (  # noqa: E402
    extract_sql_from_text,
    parse_stored_procedure_defs,
)
from sdd_reverse.dependency_inventory import extract_dependencies, parse_csproj  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "legacy-webforms-minimal"


# --------------------------------------------------------------------------- #
# inline SQL
# --------------------------------------------------------------------------- #

def test_extract_inline_sql_with_tables_and_params():
    text = (FIXTURE / "App_Code" / "DataAccess.cs").read_text(encoding="utf-8")
    queries = extract_sql_from_text(text, "App_Code/DataAccess.cs")
    assert len(queries) == 1
    q = queries[0]
    assert q.verb.upper() == "SELECT"
    assert "Users" in q.tables
    assert set(q.params) == {"u", "p"}
    assert q.line > 0


def test_extract_sql_ignores_non_sql_strings():
    text = 'string msg = "Hello world"; var s = "SELECT 1 FROM T";'
    queries = extract_sql_from_text(text, "x.cs")
    assert len(queries) == 1
    assert queries[0].tables == ["T"]


def test_verbatim_multiline_sql():
    text = 'var sql = @"SELECT a, b\nFROM Orders o\nJOIN Customers c ON c.Id = o.CustomerId";'
    queries = extract_sql_from_text(text, "x.cs")
    assert len(queries) == 1
    assert set(queries[0].tables) == {"Orders", "Customers"}


# --------------------------------------------------------------------------- #
# stored procedures
# --------------------------------------------------------------------------- #

def test_parse_stored_procedure_defs_with_params():
    text = (FIXTURE / "Scripts" / "UserProcs.sql").read_text(encoding="utf-8")
    defs = parse_stored_procedure_defs(text, "Scripts/UserProcs.sql")
    names = {d["name"]: d for d in defs}
    assert "GetUserById" in names
    assert "DeactivateUser" in names
    gp = names["GetUserById"]["params"]
    assert {"@UserId", "@IncludeInactive"} == {p["name"] for p in gp}
    assert any(p["name"] == "@UserId" and p["type"].upper() == "INT" for p in gp)
    # OUTPUT param flagged
    dp = names["DeactivateUser"]["params"]
    assert any(p["name"] == "@Reason" and p["output"] for p in dp)


# --------------------------------------------------------------------------- #
# connection strings + config
# --------------------------------------------------------------------------- #

def test_mask_secrets_keeps_structure():
    cs = "Server=db1;Database=App;User Id=sa;Password=<REDACTED>;"
    masked = mask_secrets(cs)
    assert "Secr3t" not in masked
    assert "Password=***" in masked
    assert "Server=db1" in masked
    assert "Database=App" in masked


def test_parse_dotnet_connection_strings_fixture():
    text = (FIXTURE / "Web.config").read_text(encoding="utf-8")
    cs = parse_dotnet_connection_strings(text, "Web.config")
    assert len(cs) == 1
    assert cs[0]["name"] == "AppDb"
    assert cs[0]["database"] == "HelloWebForms"
    assert cs[0]["provider"] == "System.Data.SqlClient"


def test_parse_appsettings_json_masks_password():
    text = '{ "ConnectionStrings": { "Default": "Server=x;Database=y;Password=abc;" } }'
    cs = parse_appsettings_json(text, "appsettings.json")
    assert len(cs) == 1
    assert cs[0]["server"] == "x"
    assert cs[0]["database"] == "y"
    assert "abc" not in cs[0]["value"]


# --------------------------------------------------------------------------- #
# dependency inventory
# --------------------------------------------------------------------------- #

def test_parse_csproj_packagereference_inline_nested_and_refs():
    text = (FIXTURE / "HelloWebForms.csproj").read_text(encoding="utf-8")
    pk, refs = parse_csproj(text, "HelloWebForms.csproj")
    versions = {p["name"]: p["version"] for p in pk}
    assert versions["Newtonsoft.Json"] == "13.0.3"
    assert versions["log4net"] == "2.0.15"
    # nested <Version>…</Version> form must resolve (regression: borrowed wrong version)
    assert versions["Dapper"] == "2.1.35"
    # assembly reference with HintPath
    hint = {r["name"]: r["hintPath"] for r in refs}
    assert hint["LegacyVendor.Reporting"] == "lib\\LegacyVendor.Reporting.dll"
    assert hint["System.Web"] is None


def test_extract_dependencies_dedup_and_summary():
    dep = extract_dependencies(FIXTURE)
    names = {p["name"] for p in dep["packages"]}
    assert {"Newtonsoft.Json", "log4net", "Dapper"} <= names
    assert dep["summary"]["ecosystems"].get("nuget", 0) >= 3
    assert dep["summary"]["packagesCount"] == len(dep["packages"])


# --------------------------------------------------------------------------- #
# ORM field fill (EF Code-First POCO with no DDL)
# --------------------------------------------------------------------------- #

def test_orm_class_property_registry_fills_fields():
    from sdd_reverse.db_schema_extractor import _class_property_registry
    src = (
        "public class Product {\n"
        "    public int Id { get; set; }\n"
        "    public string Name { get; set; }\n"
        "    public decimal? Price { get; set; }\n"
        "    public void Touch() { }\n"
        "}\n"
    )
    reg = _class_property_registry(src)
    assert "Product" in reg
    fields = {f["name"]: f for f in reg["Product"]}
    assert set(fields) == {"Id", "Name", "Price"}
    assert fields["Id"]["primaryKey"] is True
    assert fields["Price"]["nullable"] is True  # decimal? → nullable
    assert fields["Name"]["type"] == "string"
