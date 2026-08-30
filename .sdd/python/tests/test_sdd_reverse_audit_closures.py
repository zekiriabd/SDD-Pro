"""Tests des fermetures de l'audit consolidé reverse 2026-06-10.

Couvre les findings P0-P3 :
    C1  — enrich_units seede via les références markup (MVVM DataContext) +
          convention {Name}ViewModel ;
    C2  — unités kind=job pour les entry-points CLI/batch (App.xaml.cs) ;
    C4  — cache d'extraction câblé (update_extraction_cache --save/--check) ;
    C5  — file_locks_local : acquisition atomique O_CREAT|O_EXCL ;
    C7  — parsing VB.NET (Class…End Class) ;
    C8  — DDL SSMS bracketés + FK ALTER TABLE + parseWarnings ;
    C10 — détection secrets/clés privées ;
    M1  — nom de SP situé APRÈS CommandType.StoredProcedure ;
    M2  — SQL concaténé multi-littéraux + StringBuilder ;
    M3  — littéraux single-quote (PHP) ;
    M17 — _detect_eol honore versions_before ;
    M18 — excluded_paths YAML appliqués + decode_text cp1252 ;
    rôle viewmodel (classification MVVM behavioural).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd_reverse.class_role_classifier import ClassInfo, classify_role
from sdd_reverse.code_graph_builder import (
    enrich_units,
    parse_source_classes_vb,
)
from sdd_reverse.code_unit_detector import detect_code_units
from sdd_reverse.data_access_extractor import (
    _extract_proc_calls,
    extract_sql_from_text,
)
from sdd_reverse.db_schema_extractor import _parse_sql_ddl
from sdd_reverse.deps_graph_builder import _detect_eol
from sdd_reverse.scan_legacy import _lang_excludes_path, decode_text


# ---------------------------------------------------------------------------
# Rôle viewmodel (C1 racine — VMs classées dto → 0 % extrait)
# ---------------------------------------------------------------------------

def _ci(name: str, *, methods: int = 0, props: int = 0, file: str = "X.cs",
        kind: str = "class", **kw) -> ClassInfo:
    return ClassInfo(name=name, kind=kind, file=file,
                     method_count=methods, property_count=props, **kw)


def test_viewmodel_with_behaviour_is_viewmodel_role() -> None:
    ci = _ci("MainViewModel", methods=5, props=8)
    assert classify_role(ci) == "viewmodel"


def test_viewmodel_without_methods_stays_dto() -> None:
    ci = _ci("FilterViewModel", methods=0, props=4)
    assert classify_role(ci) == "dto"


def test_viewmodel_touching_sql_is_repository() -> None:
    # Data-access fidelity stays load-bearing — SQL wins over the VM suffix.
    ci = _ci("ImportViewModel", methods=3)
    ci.touches_sql = True
    assert classify_role(ci) == "repository"


# ---------------------------------------------------------------------------
# C1 — enrich_units : seeding markup + convention MVVM
# ---------------------------------------------------------------------------

def _wpf_project(tmp_path: Path) -> Path:
    root = tmp_path / "legacy"
    (root / "Views").mkdir(parents=True)
    (root / "ViewModels").mkdir()
    (root / "Views" / "MainWindow.xaml").write_text(
        '<Window x:Class="App.Views.MainWindow" '
        'DataContext="{Binding Main, Source={StaticResource Locator}}">'
        "<Button Command=\"{Binding GoCommand}\"/></Window>",
        encoding="utf-8",
    )
    (root / "Views" / "MainWindow.xaml.cs").write_text(
        "namespace App.Views { public partial class MainWindow : Window { "
        "public MainWindow() { InitializeComponent(); } } }",
        encoding="utf-8",
    )
    (root / "ViewModels" / "MainViewModel.cs").write_text(
        "namespace App.ViewModels { public class MainViewModel { "
        "public void Go() { } } }",
        encoding="utf-8",
    )
    return root


def _graph_for(root: Path) -> dict:
    from sdd_reverse.code_graph_builder import parse_source_classes
    classes = []
    for f in root.rglob("*.cs"):
        rel = f.relative_to(root).as_posix()
        classes.extend(parse_source_classes(rel, f.read_text(encoding="utf-8")))
    by_name = {c.name for c in classes}
    for c in classes:
        c.references = sorted(
            other for other in by_name
            if other != c.name and other in (c._body or "")
        )
        c.role = classify_role(c)
    return {"classes": [c.to_public_dict() for c in classes]}


def test_enrich_units_reaches_viewmodel_via_mvvm_convention(tmp_path: Path) -> None:
    root = _wpf_project(tmp_path)
    graph = _graph_for(root)
    unit = {
        "label": "Liste MainWindow",
        "evidenceFiles": ["Views/MainWindow.xaml", "Views/MainWindow.xaml.cs"],
    }
    enrich_units([unit], graph, project_root=root)
    # Avant C1 : evidence restait [xaml, xaml.cs] (VM invisible).
    assert "ViewModels/MainViewModel.cs" in unit["evidenceFiles"]
    assert any(c["name"] == "MainViewModel" for c in unit["classes"])


def test_enrich_units_reaches_class_named_in_markup(tmp_path: Path) -> None:
    root = _wpf_project(tmp_path)
    # Direct DataContext element naming the VM class
    (root / "Views" / "Other.xaml").write_text(
        '<Window x:Class="App.Views.Other"><Window.DataContext>'
        "<vm:MainViewModel/></Window.DataContext></Window>",
        encoding="utf-8",
    )
    graph = _graph_for(root)
    unit = {"label": "Page Other", "evidenceFiles": ["Views/Other.xaml"]}
    enrich_units([unit], graph, project_root=root)
    assert "ViewModels/MainViewModel.cs" in unit["evidenceFiles"]


def test_enrich_units_locator_is_sink_and_cap_keeps_closest(tmp_path: Path) -> None:
    """Run EDI feedback (2026-06-11) :
    1. le ViewModelLocator ne doit PAS être traversé (il référence tous les
       VMs → god-unit) — seuls les VMs liés au seed sont résolus ;
    2. le cap d'evidence garde les classes les plus PROCHES (BFS), pas les
       premières par ordre alphabétique."""
    root = tmp_path / "legacy"
    (root / "Views").mkdir(parents=True)
    (root / "ViewModels").mkdir()
    (root / "Views" / "FooWindow.xaml").write_text(
        '<Window x:Class="App.Views.FooWindow" '
        'DataContext="{Binding Foo, Source={StaticResource Locator}}"/>',
        encoding="utf-8",
    )
    (root / "ViewModels" / "ViewModelLocator.cs").write_text(
        "namespace App { public class ViewModelLocator {\n"
        "  public FooViewModel Foo => new FooViewModel();\n"
        "  public BarViewModel Bar => new BarViewModel();\n"
        "} }",
        encoding="utf-8",
    )
    (root / "ViewModels" / "FooViewModel.cs").write_text(
        "namespace App { public class FooViewModel { public void Go() { } } }",
        encoding="utf-8",
    )
    (root / "ViewModels" / "BarViewModel.cs").write_text(
        "namespace App { public class BarViewModel { public void Run() { "
        "var s = new SqlCommand(\"SELECT * FROM Autres\"); } } }",
        encoding="utf-8",
    )
    graph = _graph_for(root)
    unit = {"label": "Page Foo", "evidenceFiles": ["Views/FooWindow.xaml"]}
    enrich_units([unit], graph, project_root=root)
    names = {c["name"] for c in unit["classes"]}
    # Le VM lié au seed est atteint via la résolution locator ciblée…
    assert "FooViewModel" in names
    # …mais PAS le reste de l'app via la traversée du locator.
    assert "BarViewModel" not in names

    # Cap : avec max_added_files=1, c'est le collaborateur DIRECT (depth 0,
    # FooViewModel) qui survit — pas BarViewModel (alphabétiquement premier).
    unit2 = {"label": "Page Foo 2", "evidenceFiles": ["Views/FooWindow.xaml"]}
    enrich_units([unit2], graph, project_root=root, max_added_files=1)
    assert unit2["evidenceFiles"] == ["Views/FooWindow.xaml", "ViewModels/FooViewModel.cs"]


# ---------------------------------------------------------------------------
# C2 — unités kind=job (CLI/batch dual-mode)
# ---------------------------------------------------------------------------

def test_detect_code_units_creates_job_unit_for_cli_entrypoint(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "App.xaml.cs").write_text(
        "namespace App { public partial class App : Application {\n"
        "  protected override void OnStartup(StartupEventArgs e) {\n"
        "    if (e.Args.Length > 0) { switch (e.Args[0]) {\n"
        '      case "import-edi": RunImport(); break;\n'
        '      case "purge": RunPurge(); break;\n'
        "    } } }\n"
        "  private void RunImport() { }\n"
        "  private void RunPurge() { }\n"
        "} }",
        encoding="utf-8",
    )
    from sdd_reverse.code_graph_builder import parse_source_classes
    classes = parse_source_classes("App.xaml.cs", (root / "App.xaml.cs").read_text(encoding="utf-8"))
    for c in classes:
        c.role = classify_role(c)
    graph = {"classes": [c.to_public_dict() for c in classes]}

    units = detect_code_units(graph, [], language="csharp", project_root=root)
    jobs = [u for u in units if u["kind"] == "job"]
    assert len(jobs) == 1
    assert sorted(jobs[0]["cliCommands"]) == ["import-edi", "purge"]
    assert "App.xaml.cs" in jobs[0]["evidenceFiles"]


def test_detect_code_units_no_job_unit_for_pure_ui_bootstrap(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "App.xaml.cs").write_text(
        "namespace App { public partial class App : Application { "
        "protected override void OnStartup(StartupEventArgs e) { base.OnStartup(e); } } }",
        encoding="utf-8",
    )
    from sdd_reverse.code_graph_builder import parse_source_classes
    classes = parse_source_classes("App.xaml.cs", (root / "App.xaml.cs").read_text(encoding="utf-8"))
    graph = {"classes": [c.to_public_dict() for c in classes]}
    units = detect_code_units(graph, [], language="csharp", project_root=root)
    assert not [u for u in units if u["kind"] == "job"]


# ---------------------------------------------------------------------------
# C4 — cache d'extraction câblé
# ---------------------------------------------------------------------------

def test_update_extraction_cache_save_then_check(tmp_path: Path) -> None:
    from sdd_reverse_scripts.update_extraction_cache import main as cache_main

    project = tmp_path / "old" / "P"
    (project / ".sys").mkdir(parents=True)
    (project / "Login.aspx").write_text("<%@ Page %>", encoding="utf-8")
    inv = {
        "schemaVersion": 1,
        "units": [{"id": "U-1", "evidenceFiles": ["Login.aspx"]}],
        "_featAllocations": {}, "_allocatedNames": {},
    }
    (project / ".sys" / "inventory.json").write_text(json.dumps(inv), encoding="utf-8")
    feats = tmp_path / "feats"
    feats.mkdir()
    (feats / "1-Login.md").write_text("# FEAT", encoding="utf-8")
    # M5 (audit 2026-08-29) : un HIT exige désormais l'ESCALIER COMPLET sur
    # disque (FEAT + plan 3a + >= 1 US 3b), pas la seule FEAT — la fixture
    # représente donc une extraction réellement terminée.
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "1-Login.analysis.md").write_text("# Analyse", encoding="utf-8")
    us = tmp_path / "us"
    us.mkdir()
    (us / "1-1-Se-Connecter.md").write_text("# US", encoding="utf-8")

    # MISS avant save
    assert cache_main(["--project", str(project), "--unit", "U-1",
                       "--check", "--feats-dir", str(feats)]) == 1
    # SAVE
    assert cache_main(["--project", str(project), "--unit", "U-1",
                       "--save", "--n", "1", "--name", "Login",
                       "--feats-dir", str(feats)]) == 0
    # HIT
    assert cache_main(["--project", str(project), "--unit", "U-1",
                       "--check", "--feats-dir", str(feats)]) == 0
    # Évidence modifiée → MISS (hash invalidé)
    (project / "Login.aspx").write_text("<%@ Page %> <!-- changed -->", encoding="utf-8")
    assert cache_main(["--project", str(project), "--unit", "U-1",
                       "--check", "--feats-dir", str(feats)]) == 1


# ---------------------------------------------------------------------------
# C5 — lock O_EXCL atomique
# ---------------------------------------------------------------------------

def test_acquire_lock_uses_o_excl_single_winner(tmp_path: Path) -> None:
    """Two sequential acquires by different agents : second MUST get LOCK_HELD."""
    from sdd_reverse.file_locks_local import acquire_lock, release_lock

    lock = tmp_path / ".alloc.lock"
    assert acquire_lock(lock, "agent-A", ttl=1800) == 0
    assert acquire_lock(lock, "agent-B", ttl=1800) == 1   # held, NOT stolen
    assert acquire_lock(lock, "agent-A", ttl=1800) == 0   # re-entrant
    assert release_lock(lock, "agent-A") == 0
    assert acquire_lock(lock, "agent-B", ttl=1800) == 0   # free now
    release_lock(lock, "agent-B")


def test_acquire_lock_concurrent_o_excl_race(tmp_path: Path) -> None:
    """Parallel acquires : exactly ONE winner (TOCTOU closed by O_EXCL)."""
    import threading

    from sdd_reverse.file_locks_local import acquire_lock

    lock = tmp_path / ".alloc.lock"
    results: list[int] = []
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        results.append(acquire_lock(lock, f"agent-{i}", ttl=1800))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(0) == 1, f"expected exactly 1 winner, got {results}"
    assert results.count(1) == 7


# ---------------------------------------------------------------------------
# C7 — VB.NET parsing
# ---------------------------------------------------------------------------

def test_parse_source_classes_vb_basic() -> None:
    src = """Imports System
Namespace Legacy.Web
    Public Class LoginPage
        Inherits System.Web.UI.Page

        Public Sub Page_Load(ByVal sender As Object, ByVal e As EventArgs)
            Dim cmd As New SqlCommand("SELECT * FROM Users WHERE Login = @l")
        End Sub

        Public Function CheckUser(login As String) As Boolean
            Return True
        End Function
    End Class

    Public Module Helpers
        Public Sub Log(msg As String)
        End Sub
    End Module
End Namespace
"""
    classes = parse_source_classes_vb("Login.aspx.vb", src)
    by_name = {c.name: c for c in classes}
    assert "LoginPage" in by_name
    assert by_name["LoginPage"].method_count == 2
    assert "Page" in by_name["LoginPage"].base_types
    assert by_name["LoginPage"].namespace == "Legacy.Web"
    assert by_name["LoginPage"].touches_sql is True
    assert "Helpers" in by_name
    assert by_name["Helpers"].is_static is True


# ---------------------------------------------------------------------------
# C8 — DDL SSMS bracketés + ALTER TABLE FK + parseWarnings
# ---------------------------------------------------------------------------

_SSMS_DDL = """
CREATE TABLE [dbo].[Commandes](
    [Id] [int] IDENTITY(1,1) NOT NULL,
    [Libelle] [nvarchar](100) NOT NULL,
    [Montant] [decimal](18, 2) NULL,
    [FkClient] [int] NOT NULL,
 CONSTRAINT [PK_Commandes] PRIMARY KEY CLUSTERED ([Id] ASC)
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Commandes]  WITH CHECK ADD  CONSTRAINT [FK_Commandes_Clients] FOREIGN KEY([FkClient])
REFERENCES [dbo].[Clients] ([Id])
GO
"""


def test_parse_sql_ddl_ssms_bracketed_columns() -> None:
    warns: list[str] = []
    ents, rels = _parse_sql_ddl(_SSMS_DDL, "db/script.sql", warns)
    assert len(ents) == 1
    fields = {f["name"]: f for f in ents[0]["fields"]}
    assert set(fields) == {"Id", "Libelle", "Montant", "FkClient"}
    assert fields["Id"]["identity"] is True
    assert fields["Libelle"]["type"] == "nvarchar(100)"
    assert fields["Montant"]["nullable"] is True
    assert warns == []


def test_parse_sql_ddl_alter_table_fk() -> None:
    _, rels = _parse_sql_ddl(_SSMS_DDL, "db/script.sql", [])
    assert len(rels) == 1
    fk = rels[0]
    assert fk["name"] == "FK_Commandes_Clients"
    assert fk["from"] == {"entity": "Commandes", "field": "FkClient"}
    assert fk["to"] == {"entity": "Clients", "field": "Id"}


def test_parse_sql_ddl_unparsed_column_is_logged() -> None:
    ddl = "CREATE TABLE T (\n  ??? garbage line,\n  Id int NOT NULL\n)"
    warns: list[str] = []
    ents, _ = _parse_sql_ddl(ddl, "x.sql", warns)
    assert len(ents) == 1
    assert len(warns) == 1
    assert "garbage" in warns[0]


# ---------------------------------------------------------------------------
# M1 / M2 / M3 — data access
# ---------------------------------------------------------------------------

def test_proc_name_after_storedprocedure_marker() -> None:
    cs = (
        "cmd.CommandType = CommandType.StoredProcedure;\n"
        'cmd.CommandText = "usp_ImportCommandes";\n'
        'cmd.Parameters.AddWithValue("@d", d);\n'
    )
    calls = _extract_proc_calls(cs, "VM.cs")
    assert [c["name"] for c in calls if c["via"] == "CommandType.StoredProcedure"] == ["usp_ImportCommandes"]


def test_sql_concatenated_fragments_keep_tables() -> None:
    cs = (
        'string sql = "SELECT c.Id " +\n'
        '             "FROM Commandes c " +\n'
        '             "JOIN Clients cl ON cl.Id = c.FkClient";\n'
    )
    qs = extract_sql_from_text(cs, "X.cs")
    assert len(qs) == 1
    assert set(qs[0].tables) == {"Commandes", "Clients"}


def test_sql_stringbuilder_chain_merged() -> None:
    cs = (
        'sb.Append("UPDATE Lignes ");\n'
        'sb.Append("SET Qte = @q WHERE Id = @id");\n'
    )
    qs = extract_sql_from_text(cs, "X.cs")
    assert len(qs) == 1
    assert qs[0].verb == "UPDATE"
    assert qs[0].tables == ["Lignes"]


def test_sql_single_quote_literals_php() -> None:
    php = "<?php $sql = 'SELECT * FROM utilisateurs WHERE id = :id';"
    qs = extract_sql_from_text(php, "x.php", include_single_quotes=True)
    assert len(qs) == 1
    assert qs[0].tables == ["utilisateurs"]


# ---------------------------------------------------------------------------
# M17 — EOL versions_before
# ---------------------------------------------------------------------------

def test_detect_eol_respects_versions_before() -> None:
    # Newtonsoft 13.0.3 >= bound 13.0.0 → NOT EOL (faux positif systémique avant fix)
    is_eol, _, _ = _detect_eol("Newtonsoft.Json", "13.0.3")
    assert is_eol is False
    # 12.0.1 < 13.0.0 → EOL
    is_eol, _, reason = _detect_eol("Newtonsoft.Json", "12.0.1")
    assert is_eol is True
    # Maven key now matchable
    is_eol, _, _ = _detect_eol("commons-collections:commons-collections", "3.2.1")
    assert is_eol is True
    is_eol, _, _ = _detect_eol("commons-collections:commons-collections", "3.2.2")
    assert is_eol is False


# ---------------------------------------------------------------------------
# M18 — excluded_paths + decode_text
# ---------------------------------------------------------------------------

def test_lang_excludes_path_dir_and_suffix() -> None:
    lang = {"excluded_paths": ["vendor/", ".min.js"]}
    assert _lang_excludes_path(lang, ("vendor", "lib.php"), "lib.php") is True
    assert _lang_excludes_path(lang, ("js",), "jquery.min.js") is True
    assert _lang_excludes_path(lang, ("src",), "app.js") is False


def test_decode_text_cp1252_fallback() -> None:
    # "Libellé" in cp1252 — invalid UTF-8 byte 0xE9
    raw = "Libellé commandé".encode("cp1252")
    assert decode_text(raw) == "Libellé commandé"
    # Valid UTF-8 passes through unchanged
    assert decode_text("évolution".encode("utf-8")) == "évolution"


# ---------------------------------------------------------------------------
# C10 — secrets / clés privées
# ---------------------------------------------------------------------------

def test_detect_secret_files(tmp_path: Path) -> None:
    from sdd_reverse_scripts.reverse_inventory import _detect_secret_files

    root = tmp_path / "legacy"
    (root / "Fichiers").mkdir(parents=True)
    (root / "Fichiers" / "PrivateKey_Prod.ppk").write_text("PuTTY-User-Key-File-2", encoding="utf-8")
    (root / "Fichiers" / "id_rsa-ITM_Prod").write_text("-----BEGIN RSA PRIVATE KEY-----", encoding="utf-8")
    (root / "Fichiers" / "cert.pem").write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    (root / "Fichiers" / "notes.txt").write_text("rien", encoding="utf-8")

    found = _detect_secret_files(root)
    paths = {f["path"] for f in found}
    assert "Fichiers/PrivateKey_Prod.ppk" in paths
    assert "Fichiers/id_rsa-ITM_Prod" in paths
    assert "Fichiers/cert.pem" in paths
    assert "Fichiers/notes.txt" not in paths
    pem = next(f for f in found if f["path"].endswith("cert.pem"))
    assert "PRIVATE" in pem["type"]


# ---------------------------------------------------------------------------
# Couverture des gates 0 % (audit §3) — reverse_audit / merge / check_for_full
# ---------------------------------------------------------------------------

def test_check_reverse_feat_for_full_gate(tmp_path: Path) -> None:
    from sdd_reverse_scripts.check_reverse_feat_for_full import check_feat

    feat = tmp_path / "7-Legacy.md"
    feat.write_text(
        "---\ngenerated-by: sdd-reverse\nconfidence: low\n---\n"
        "<!-- REVERSE-GATE: confidence=low ; allow-sdd-full=false -->\n",
        encoding="utf-8",
    )
    code, report = check_feat(feat, allow_low=False)
    assert code == 1 and report["allowed"] is False
    code, report = check_feat(feat, allow_low=True)
    assert code == 0 and report["allowed"] is True
    # Non-reverse FEAT : gate inopérante
    plain = tmp_path / "1-Auth.md"
    plain.write_text("---\nowner: po\n---\n# FEAT 1", encoding="utf-8")
    code, report = check_feat(plain, allow_low=False)
    assert code == 0 and report["is_reverse"] is False


def test_merge_db_schema_basic_union(tmp_path: Path) -> None:
    from sdd_reverse.merge_db_schema import merge_schemas

    base = {
        "schemaVersion": 1,
        "entities": [{"name": "Commandes", "table": "Commandes",
                      "fields": [{"name": "Id", "type": "int", "primaryKey": True,
                                  "identity": True, "nullable": False, "default": None}],
                      "evidence": ["db.sql:1-5"]}],
        "relations": [],
    }
    enrichment = {
        "schemaVersion": 1,
        "enrichmentDate": "2026-06-10T00:00:00Z",
        "addedRelations": [{
            "name": "FK_Commandes_Clients",
            "from": {"entity": "Commandes", "field": "FkClient"},
            "to": {"entity": "Commandes", "field": "Id"},
            "type": "many-to-one",
            "evidence": "VM.cs:42",
        }],
        "addedIndexes": [], "addedConstraints": [], "addedFields": [],
    }
    merged, conflicts = merge_schemas(base, enrichment, set())
    assert len(merged["relations"]) == 1
    assert conflicts == []


def test_merge_db_schema_observed_entities_channel(tmp_path: Path) -> None:
    """C3 : entités/FKs DÉDUITES par le tech-auditor → merged avec deduced=true.

    Les deux formes d'item sont acceptées (`name`+`fields` canonique,
    `entity`+`observedFields` telle qu'émise par l'agent sur le run EDI)."""
    from sdd_reverse.merge_db_schema import merge_schemas

    base = {"schemaVersion": 1, "entities": [], "relations": []}
    enrichment = {
        "schemaVersion": 1,
        "addedRelations": [], "addedIndexes": [], "addedConstraints": [],
        "addedFields": [],
        "observedEntitiesNotInBase": [
            {"entity": "PlayerEcran", "observedFields": ["Id", "Fk_PvDpPlayer"],
             "evidence": "VM.cs:380"},
            {"name": "PvDpPlayer", "fields": [], "evidence": ["VM.cs:384"]},
        ],
        "observedRelationsNotInBase": [
            {"name": "FK_obs", "from": {"entity": "PlayerEcran", "field": "Fk_PvDpPlayer"},
             "to": {"entity": "PvDpPlayer", "field": "Id"}, "type": "many-to-one",
             "evidence": "VM.cs:384"},
            {"name": "FK_bad", "from": {"entity": "Inconnue", "field": "x"},
             "to": {"entity": "PvDpPlayer", "field": "Id"}, "type": "many-to-one",
             "evidence": "VM.cs:1"},
        ],
    }
    merged, conflicts = merge_schemas(base, enrichment, set())
    names = {e["name"] for e in merged["entities"]}
    assert names == {"PlayerEcran", "PvDpPlayer"}
    assert all(e["deduced"] for e in merged["entities"])
    pe = next(e for e in merged["entities"] if e["name"] == "PlayerEcran")
    assert {f["name"] for f in pe["fields"]} == {"Id", "Fk_PvDpPlayer"}
    assert len(merged["relations"]) == 1 and merged["relations"][0]["deduced"]
    # Relation invalide → conflit informational, jamais silencieux ni fatal
    assert any(c["class"] == "REVERSE_ENRICHMENT_INVALID" for c in conflicts)


def test_reverse_audit_cli_end_to_end(tmp_path: Path) -> None:
    from sdd_reverse_scripts.reverse_audit import main as audit_main

    project = tmp_path / "old" / "P"
    (project / ".sys").mkdir(parents=True)
    (project / "Login.aspx").write_text('<%@ Page CodeBehind="Login.aspx.cs" %>', encoding="utf-8")
    (project / "Login.aspx.cs").write_text(
        "using System; namespace L { public partial class Login : Page { } }",
        encoding="utf-8",
    )
    (project / ".sys" / "inventory.json").write_text(json.dumps({
        "schemaVersion": 1, "project": "P", "units": [],
        "_featAllocations": {}, "_allocatedNames": {},
    }), encoding="utf-8")
    (project / ".sys" / "db-schema.json").write_text(json.dumps({
        "schemaVersion": 1, "project": "P", "entities": [], "relations": [],
    }), encoding="utf-8")

    rc = audit_main(["--project", str(project), "--json"])
    assert rc == 0
    assert (project / ".sys" / "deps-graph.json").is_file()
    assert (project / ".sys" / "db-schema.enrichment.json").is_file()
    assert (project / ".sys" / "db-schema.merged.json").is_file()
