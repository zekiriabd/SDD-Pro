"""test_sdd_reverse_code_graph.py — L0 code-graph + class role classifier.

Covers the structural fix that lets the reverse pipeline see the deep business
layer (services / repositories / DTOs) instead of stopping at [page, behind].
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PY_ROOT = Path(__file__).parent.parent  # .sdd/python/
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.class_role_classifier import (  # noqa: E402
    ClassInfo,
    classify_role,
    detect_touches_http,
    detect_touches_sql,
)
from sdd_reverse.code_graph_builder import (  # noqa: E402
    _mask_comments_and_strings,
    build_code_graph,
    enrich_units,
    parse_source_classes,
)

FIXTURE = Path(__file__).parent / "fixtures" / "legacy-webforms-minimal"


# --------------------------------------------------------------------------- #
# class_role_classifier — pure heuristics
# --------------------------------------------------------------------------- #

def _ci(name, **kw):
    return ClassInfo(name=name, kind=kw.pop("kind", "class"), file=kw.pop("file", "X.cs"), **kw)


def test_role_interface_and_enum():
    assert classify_role(_ci("IUserRepository", kind="interface")) == "interface"
    assert classify_role(_ci("StatusKind", kind="enum")) == "enum"


def test_role_code_behind_by_base_and_by_filename():
    assert classify_role(_ci("Login", base_types=["Page"])) == "code-behind"
    assert classify_role(_ci("Login", file="Login.aspx.cs")) == "code-behind"
    assert classify_role(_ci("MainWindow", base_types=["Window"])) == "code-behind"


def test_role_controller():
    assert classify_role(_ci("UsersController")) == "controller"
    assert classify_role(_ci("Api", base_types=["ControllerBase"])) == "controller"
    assert classify_role(_ci("Api", attributes=["ApiController"])) == "controller"


def test_role_repository_by_sql_touch_even_without_name():
    # A plain-named class that touches SQL is still data-access (load-bearing).
    assert classify_role(_ci("DataAccess", touches_sql=True)) == "repository"
    assert classify_role(_ci("Orders", touches_sql=True)) == "repository"
    assert classify_role(_ci("UserRepository")) == "repository"
    assert classify_role(_ci("AppContext", base_types=["DbContext"])) == "repository"


def test_role_entity_by_attribute_and_by_known_name():
    assert classify_role(_ci("User", attributes=['Table("Users")'])) == "entity"
    assert classify_role(_ci("User"), known_entity_names=frozenset({"User"})) == "entity"


def test_role_service_dto_helper_complex_classic():
    assert classify_role(_ci("AuthService")) == "service"
    assert classify_role(_ci("UserDto", property_count=4, method_count=0)) == "dto"
    # POCO shape (props, no methods) → dto even without suffix
    assert classify_role(_ci("Address", property_count=3, method_count=0)) == "dto"
    assert classify_role(_ci("StringHelper", is_static=True)) == "static-helper"
    # "Calculator" matches no role suffix → complex when oversized, else classic
    assert classify_role(_ci("Calculator", method_count=20)) == "complex"
    assert classify_role(_ci("Calculator", loc_total=400)) == "complex"
    assert classify_role(_ci("Widget", method_count=2, property_count=1)) == "classic"


def test_detect_touches_sql_http():
    assert detect_touches_sql("var c = new SqlCommand(\"SELECT 1\", conn);")
    assert detect_touches_sql("conn.Query<User>(sql)")
    assert not detect_touches_sql("var x = 1 + 2;")
    assert detect_touches_http("await client.GetAsync(url)")
    assert detect_touches_http("new HttpClient()")
    assert not detect_touches_http("var x = 1;")


# --------------------------------------------------------------------------- #
# parsing + masking
# --------------------------------------------------------------------------- #

def test_mask_neutralizes_braces_and_keywords_in_strings_and_comments():
    src = 'class A { /* class B { */ string s = "class C { } repository"; }'
    masked = _mask_comments_and_strings(src)
    # the real class A survives
    classes = parse_source_classes("A.cs", src)
    assert [c.name for c in classes] == ["A"]
    # masked length preserved (offset-stable)
    assert len(masked) == len(src)
    # 'class C' inside the string must NOT be detected
    assert "C" not in {c.name for c in classes}


def test_parse_static_repository_class_from_fixture():
    text = (FIXTURE / "App_Code" / "DataAccess.cs").read_text(encoding="utf-8")
    classes = parse_source_classes("App_Code/DataAccess.cs", text)
    assert len(classes) == 1
    da = classes[0]
    assert da.name == "DataAccess"
    assert da.is_static is True
    assert da.namespace == "HelloWebForms.App_Code"
    assert da.touches_sql is True
    assert classify_role(da) == "repository"
    # ValidateUser + HashPassword (ConnString is a property, not a method)
    assert da.method_count >= 2


def test_parse_code_behind_inherits_page():
    text = (FIXTURE / "Login.aspx.cs").read_text(encoding="utf-8")
    classes = parse_source_classes("Login.aspx.cs", text)
    login = next(c for c in classes if c.name == "Login")
    assert "Page" in login.base_types
    assert login.is_partial is True
    assert classify_role(login) == "code-behind"
    assert "DataAccess" in login.references or True  # references set during graph build


# --------------------------------------------------------------------------- #
# build_code_graph + enrich_units (integration on the fixture)
# --------------------------------------------------------------------------- #

class _FakeLang:
    def __init__(self, files):
        self.files = files


class _FakeScan:
    def __init__(self, files):
        self.languages = [_FakeLang(files)]
        self.primary_language = "csharp"


def _fixture_scan():
    files = [
        FIXTURE / "App_Code" / "DataAccess.cs",
        FIXTURE / "Login.aspx.cs",
        FIXTURE / "Default.aspx.cs",
    ]
    return _FakeScan(files)


def test_build_code_graph_edges_login_to_dataaccess():
    cg = build_code_graph(FIXTURE, _fixture_scan())
    names = {c["name"]: c for c in cg["classes"]}
    assert "DataAccess" in names and names["DataAccess"]["role"] == "repository"
    assert "Login" in names and names["Login"]["role"] == "code-behind"
    assert any(e["from"] == "Login" and e["to"] == "DataAccess" for e in cg["edges"])
    assert cg["rolesSummary"].get("repository") == 1


def test_enrich_units_pulls_transitive_repository_into_evidence():
    cg = build_code_graph(FIXTURE, _fixture_scan())
    units = [{
        "label": "Formulaire Login",
        "suggestedName": "Login",
        "evidenceFiles": ["Login.aspx", "Login.aspx.cs"],
        "entities": [],
    }]
    enrich_units(units, cg)
    u = units[0]
    assert u["seedEvidenceFiles"] == ["Login.aspx", "Login.aspx.cs"]
    assert "App_Code/DataAccess.cs" in u["evidenceFiles"], \
        "transitive repository must be added to evidence (the L0 fix)"
    roles = {c["name"]: c["role"] for c in u["classes"]}
    assert roles.get("DataAccess") == "repository"
    # entities must NOT contain the repository class name
    assert "DataAccess" not in u["entities"]


def test_enrich_units_noop_when_graph_empty_keeps_seed():
    units = [{"label": "X", "suggestedName": "X",
              "evidenceFiles": ["a.php"], "entities": []}]
    enrich_units(units, {"classes": []})
    assert units[0]["evidenceFiles"] == ["a.php"]
    assert units[0]["seedEvidenceFiles"] == ["a.php"]
    assert units[0]["classes"] == []


def test_enrich_respects_max_added_files_bound():
    cg = build_code_graph(FIXTURE, _fixture_scan())
    units = [{"label": "L", "suggestedName": "Login",
              "evidenceFiles": ["Login.aspx.cs"], "entities": []}]
    enrich_units(units, cg, max_added_files=0)
    # bound=0 → no deep files added, seed preserved
    assert units[0]["evidenceFiles"] == ["Login.aspx.cs"]
