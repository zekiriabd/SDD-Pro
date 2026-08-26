"""C2 + C3 + M5 + D4 (audit 2026-08-25) — the rung-1 → rung-2 contract.

Three defects lived between the User Stories and the FEAT of the DB-reverse:

  C2  `build_proc_feats` never opened a US file, so everything the
      `reverse-sql-analyst` agent produced on complex objects was discarded and
      the FEAT stayed a paraphrase of regex signals.
  C3  `## Covers` was never written, so FEAT→US traceability existed nowhere and
      `/feat-validate` — which `/sdd-full` runs at phase 2.6 and which marks SFD
      and FD coverage REQUIRED — was a guaranteed NO-GO on every DB-reverse FEAT.
  M5  A FEAT annotated by a human during the review the REVERSE-GATE demands was
      silently overwritten on the next run.
  D4  DB-reverse US had no `Parent FEAT hash`, so they rode preflight's
      pre-v7.0.0 compatibility path forever and FEAT drift went undetected.

The decisive test is `test_readiness_gate_coverage_is_satisfied`: it calls the
REAL `validate_readiness` helpers, so it proves the gate outcome rather than
approximating it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse import db_introspect as dbi  # noqa: E402
from sdd_reverse.dialects import ROUTINE_COLUMNS, get_dialect  # noqa: E402
from sdd_reverse_scripts import build_proc_feats, build_proc_us  # noqa: E402
from sdd_reverse_scripts import reverse_proc_introspect  # noqa: E402

_SS = get_dialect("sqlserver")

# One trivial object (routed deterministic) + one with real logic (routed LLM).
PROC_LIST = """\
CREATE PROCEDURE dbo.usp_GetContactList AS
BEGIN
    SELECT Id, Name FROM dbo.Contacts ORDER BY Name;
END
"""
PROC_INSERT = """\
CREATE PROCEDURE dbo.usp_Contact_Insert @Name nvarchar(100), @Id int OUTPUT AS
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.Contacts WHERE Name = @Name)
        RAISERROR('Duplicate', 16, 1);
    BEGIN TRAN;
    INSERT INTO dbo.Contacts (Name) VALUES (@Name);
    SET @Id = SCOPE_IDENTITY();
    COMMIT;
END
"""


def _row(schema, name, rtype, definition, modified=None, is_enc=0):
    d = {"schema": schema, "name": name, "routine_type": rtype,
         "definition": definition, "modified": modified, "is_encrypted": is_enc}
    return tuple(d[c] for c in ROUTINE_COLUMNS)


@pytest.fixture()
def pipeline(tmp_path):
    """Run Phase 1 + rung 1 offline, then hand back the workspace."""
    project = "OrdersDb"
    project_root = tmp_path / "old" / project
    project_root.mkdir(parents=True)
    rows = [
        _row("dbo", "usp_GetContactList", "SQL_STORED_PROCEDURE", PROC_LIST),
        _row("dbo", "usp_Contact_Insert", "SQL_STORED_PROCEDURE", PROC_INSERT),
    ]
    model = dbi.build_introspection(rows, _SS, server="h", database=project,
                                   lang_cap="high")
    dbi.write_snapshot(project_root, model)
    assert reverse_proc_introspect.main([
        "--from-introspection", str(project_root / ".sys" / "db-introspection.json"),
        "--project", project, "--workspace", str(tmp_path),
    ]) == 0
    assert build_proc_us.main([
        "--project", project, "--all", "--workspace", str(tmp_path), "--json",
    ]) == 0
    return {"ws": tmp_path, "project": project, "root": project_root}


def _inventory(p):
    return json.loads(
        (p["root"] / ".sys" / "inventory.json").read_text(encoding="utf-8"))


def _simulate_analyst(p):
    """Stand in for `reverse-sql-analyst`: write the US of the complex object.

    Mirrors what the agent produces — a business title, several ACs derived from
    the real branches, and `extraction: analyzed`.
    """
    inv = _inventory(p)
    unit = inv["units"][0]
    n = inv["_featAllocations"][unit["id"]]
    proc = next(x for x in unit["procedures"]
                if x["fqName"] == "dbo.usp_Contact_Insert")
    path = p["ws"] / "us" / f"{n}-{proc['usIndex']}-{proc['usName']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    ev = proc["evidence"]
    path.write_text(
        "---\n"
        f"ID: {n}-{proc['usIndex']}-{proc['usName']}\n"
        f"Parent FEAT: {n}-{unit['suggestedName']}\n"
        f"Parent FEAT hash: {build_proc_feats.HASH_SENTINEL}\n"
        "generated-by: sdd-reverse\n"
        "source-proc: dbo.usp_Contact_Insert\n"
        "language-detected: tsql\n"
        "Confidence: high\n"
        "extraction: analyzed\n"
        "Status: Draft\n"
        "---\n\n"
        "# US-%d: Enregistrer un contact en refusant les doublons de nom\n\n"
        "## Story\n\nEn tant que gestionnaire, je veux enregistrer un contact.\n\n"
        "## Acceptance Criteria\n\n"
        f"- AC-1: Given un nom libre, when on enregistre, then le contact existe. <!-- evidence: {ev} --> <!-- confidence: high -->\n"
        f"- AC-2: Given un nom déjà pris, when on enregistre, then l'opération est refusée. <!-- evidence: {ev} --> <!-- confidence: high -->\n"
        f"- AC-3: Given une erreur en cours, when la transaction échoue, then rien n'est écrit. <!-- evidence: {ev} --> <!-- confidence: high -->\n\n"
        "## Covers\n\n"
        "<!-- back-fill par l'assembleur déterministe (rung 2). -->\n"
        % proc["usIndex"],
        encoding="utf-8")
    return path, unit, n


# --------------------------------------------------------------------------- #
# M2 — routing
# --------------------------------------------------------------------------- #

class TestRouting:
    def test_trivial_object_is_templated_and_complex_one_goes_to_the_llm(self, pipeline):
        inv = _inventory(pipeline)
        by_fq = {p["fqName"]: p for p in inv["units"][0]["procedures"]}
        assert by_fq["dbo.usp_GetContactList"]["complexity"] == "simple"
        assert by_fq["dbo.usp_Contact_Insert"]["complexity"] == "complex"

    def test_routing_reasons_are_recorded_for_audit(self, pipeline):
        inv = _inventory(pipeline)
        insert = next(p for p in inv["units"][0]["procedures"]
                      if p["fqName"] == "dbo.usp_Contact_Insert")
        assert insert["complexityReasons"]
        assert any("branches" in r for r in insert["complexityReasons"])

    def test_templated_us_declares_its_extraction_mode(self, pipeline):
        """M2: `confidence` is about the body; `extraction` about the method."""
        us = list((pipeline["ws"] / "us").glob("*.md"))
        assert us, "the trivial object should have produced a US"
        text = us[0].read_text(encoding="utf-8")
        assert "extraction: templated" in text
        assert "non analysé" in text  # the banner warns the reviewer


# --------------------------------------------------------------------------- #
# M4 — distinctive US names
# --------------------------------------------------------------------------- #

class TestUsNamesAreDistinct:
    def test_two_read_procs_of_one_module_do_not_share_a_name(self, tmp_path):
        rows = [
            _row("dbo", "usp_GetContactById", "P",
                 "CREATE PROC dbo.usp_GetContactById @Id int AS SELECT * FROM dbo.Contacts"),
            _row("dbo", "usp_GetContactList", "P",
                 "CREATE PROC dbo.usp_GetContactList AS SELECT * FROM dbo.Contacts"),
        ]
        model = dbi.build_introspection(rows, _SS, server="h", database="Db")
        inv = reverse_proc_introspect.build_inventory(
            model, project="Db", feats_dir=tmp_path / "feats")
        names = [p["usName"] for p in inv["units"][0]["procedures"]]
        assert len(set(names)) == len(names), f"collision: {names}"

    def test_same_verb_no_qualifier_still_unique(self, tmp_path):
        """`Contact_Insert` and `Contact_Add` are both verb=create, no noise token."""
        rows = [
            _row("dbo", "usp_Contact_Insert", "P",
                 "CREATE PROC dbo.usp_Contact_Insert AS INSERT INTO dbo.Contacts VALUES(1)"),
            _row("dbo", "usp_Contact_Add", "P",
                 "CREATE PROC dbo.usp_Contact_Add AS INSERT INTO dbo.Contacts VALUES(2)"),
        ]
        model = dbi.build_introspection(rows, _SS, server="h", database="Db")
        inv = reverse_proc_introspect.build_inventory(
            model, project="Db", feats_dir=tmp_path / "feats")
        names = [p["usName"] for p in inv["units"][0]["procedures"]]
        assert len(set(names)) == 2, f"collision: {names}"

    def test_names_are_stable_across_reruns(self, tmp_path):
        """Idempotence outranks prettiness: a reversed object keeps its filename."""
        rows = [_row("dbo", "usp_GetContactList", "P",
                     "CREATE PROC dbo.usp_GetContactList AS SELECT 1")]
        model = dbi.build_introspection(rows, _SS, server="h", database="Db")
        first = reverse_proc_introspect.build_inventory(
            model, project="Db", feats_dir=tmp_path / "feats")
        second = reverse_proc_introspect.build_inventory(
            model, project="Db", feats_dir=tmp_path / "feats", prior=first)
        assert (first["units"][0]["procedures"][0]["usName"]
                == second["units"][0]["procedures"][0]["usName"])


# --------------------------------------------------------------------------- #
# C2 — the FEAT reads the User Stories
# --------------------------------------------------------------------------- #

class TestFeatReadsTheUserStories:
    def test_analysed_us_title_reaches_the_feat(self, pipeline):
        """The whole point of paying for the analyst."""
        _us, unit, n = _simulate_analyst(pipeline)
        assert build_proc_feats.main([
            "--project", pipeline["project"], "--all",
            "--workspace", str(pipeline["ws"]),
        ]) == 0
        feat = (pipeline["ws"] / "feats" / f"{n}-{unit['suggestedName']}.md").read_text(encoding="utf-8")
        assert "refusant les doublons de nom" in feat

    def test_feat_records_how_many_us_were_analysed_vs_templated(self, pipeline):
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        feat = next((pipeline["ws"] / "feats").glob("*.md")).read_text(encoding="utf-8")
        assert "us-analyzed: 1" in feat
        assert "us-templated: 1" in feat

    def test_templated_only_feat_warns_in_its_banner(self, pipeline):
        """No analyst run at all → the FEAT must say its content is a template."""
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        feat = next((pipeline["ws"] / "feats").glob("*.md")).read_text(encoding="utf-8")
        assert "gabarits déterministes" in feat

    def test_assembler_still_works_with_no_us_on_disk(self, pipeline):
        """Bootstrap order must not break: FEAT before rung 1 is legitimate."""
        for f in (pipeline["ws"] / "us").glob("*.md"):
            f.unlink()
        assert build_proc_feats.main([
            "--project", pipeline["project"], "--all",
            "--workspace", str(pipeline["ws"]),
        ]) == 0
        assert list((pipeline["ws"] / "feats").glob("*.md"))

    def test_feat_still_passes_the_structural_gate(self, pipeline):
        from sdd_reverse_scripts.validate_reverse_feat import validate_feat
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        for feat in (pipeline["ws"] / "feats").glob("*.md"):
            ok, errors, _w = validate_feat(feat)
            assert ok, f"{feat.name}: {errors}"


# --------------------------------------------------------------------------- #
# C3 — traceability, proven against the real readiness gate
# --------------------------------------------------------------------------- #

class TestCoversBackfill:
    def test_covers_section_is_filled_in_every_us(self, pipeline):
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        for us in (pipeline["ws"] / "us").glob("*.md"):
            text = us.read_text(encoding="utf-8")
            body = text.split("## Covers", 1)[1]
            assert re.search(r"^- SFD-\d+$", body, re.MULTILINE), us.name
            assert re.search(r"^- FD-\d+$", body, re.MULTILINE), us.name

    def test_readiness_gate_coverage_is_satisfied(self, pipeline):
        """THE decisive assertion — uses validate_readiness' own helpers.

        Before the fix every SFD-N and FD-N of the FEAT was orphan, which
        `validate_readiness` reports as a blocking error (`required=True`) and
        therefore `[READINESS_NO_GO]` for `/sdd-full`.
        """
        sys.path.insert(0, str(_PY_ROOT / "sdd_scripts"))
        from sdd_scripts.validate_readiness import get_all_ids, get_covered_ids

        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        feat_path = next((pipeline["ws"] / "feats").glob("*.md"))
        feat = feat_path.read_text(encoding="utf-8")
        all_us = "\n\n".join(p.read_text(encoding="utf-8")
                             for p in sorted((pipeline["ws"] / "us").glob("*.md")))

        for prefix, section in (("SFD", "Functional Needs"),
                                ("FD", "Functional Deliverables")):
            declared = get_all_ids(feat, prefix, section)
            covered = get_covered_ids(all_us, prefix)
            orphans = [d for d in declared if d not in covered]
            assert declared, f"no {prefix} declared — test is not exercising anything"
            assert not orphans, f"{prefix} orphans would block /sdd-full: {orphans}"

    def test_parent_feat_hash_sentinel_is_resolved(self, pipeline):
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        for us in (pipeline["ws"] / "us").glob("*.md"):
            text = us.read_text(encoding="utf-8")
            assert build_proc_feats.HASH_SENTINEL not in text, us.name
            assert re.search(r"^Parent FEAT hash: sha256:[0-9a-f]{8}$",
                             text, re.MULTILINE), us.name

    def test_hash_matches_the_feat_actually_written(self, pipeline):
        import hashlib
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        feat_path = next((pipeline["ws"] / "feats").glob("*.md"))
        expected = hashlib.sha256(feat_path.read_bytes()).hexdigest()[:8]
        us = next((pipeline["ws"] / "us").glob("*.md")).read_text(encoding="utf-8")
        assert f"Parent FEAT hash: sha256:{expected}" in us

    def test_backfill_is_idempotent(self, pipeline):
        _simulate_analyst(pipeline)
        args = ["--project", pipeline["project"], "--all",
                "--workspace", str(pipeline["ws"])]
        build_proc_feats.main(args)
        snapshot = {p.name: p.read_text(encoding="utf-8")
                    for p in (pipeline["ws"] / "us").glob("*.md")}
        build_proc_feats.main(args + ["--force"])
        after = {p.name: p.read_text(encoding="utf-8")
                 for p in (pipeline["ws"] / "us").glob("*.md")}
        assert snapshot == after

    def test_no_covers_flag_leaves_the_us_untouched(self, pipeline):
        _simulate_analyst(pipeline)
        before = {p.name: p.read_text(encoding="utf-8")
                  for p in (pipeline["ws"] / "us").glob("*.md")}
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"]), "--no-covers"])
        after = {p.name: p.read_text(encoding="utf-8")
                 for p in (pipeline["ws"] / "us").glob("*.md")}
        assert before == after


# --------------------------------------------------------------------------- #
# M5 — human review is never clobbered
# --------------------------------------------------------------------------- #

class TestOverwriteGuard:
    def _run(self, pipeline, *extra):
        return build_proc_feats.main(
            ["--project", pipeline["project"], "--all",
             "--workspace", str(pipeline["ws"]), *extra])

    def test_regenerating_an_untouched_feat_is_allowed(self, pipeline):
        self._run(pipeline)
        assert self._run(pipeline) == 0        # no human edit → rewritten freely

    def test_human_edited_feat_is_preserved(self, pipeline):
        self._run(pipeline)
        feat = next((pipeline["ws"] / "feats").glob("*.md"))
        feat.write_text(feat.read_text(encoding="utf-8")
                        + "\n<!-- revue Tech Lead : AC-2 à confirmer -->\n",
                        encoding="utf-8")
        rc = self._run(pipeline)
        assert rc == 4                          # signalled, not silent
        assert "revue Tech Lead" in feat.read_text(encoding="utf-8")

    def test_force_overwrites_a_human_edited_feat(self, pipeline):
        self._run(pipeline)
        feat = next((pipeline["ws"] / "feats").glob("*.md"))
        feat.write_text(feat.read_text(encoding="utf-8") + "\n<!-- revue -->\n",
                        encoding="utf-8")
        assert self._run(pipeline, "--force") == 0
        assert "<!-- revue -->" not in feat.read_text(encoding="utf-8")

    def test_feat_without_fingerprint_is_treated_as_human_owned(self, pipeline, tmp_path):
        """A FEAT written before this guard existed must not be clobbered either."""
        inv = _inventory(pipeline)
        unit = inv["units"][0]
        n = inv["_featAllocations"][unit["id"]]
        feats = pipeline["ws"] / "feats"
        feats.mkdir(parents=True, exist_ok=True)
        legacy = feats / f"{n}-{unit['suggestedName']}.md"
        legacy.write_text("---\nconfidence: high\n---\n# legacy FEAT\n", encoding="utf-8")
        assert self._run(pipeline) == 4
        assert "legacy FEAT" in legacy.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# D3 — object-level cache
# --------------------------------------------------------------------------- #

class TestObjectCache:
    def test_unchanged_object_is_not_re_extracted(self, pipeline):
        out = json.loads(_capture(pipeline))
        assert out["cached"], "second run should reuse the unchanged snapshot"

    def test_changed_object_is_re_extracted(self, pipeline):
        _capture(pipeline)                     # prime the cache
        snap = (pipeline["root"] / ".sys" / "proc-snapshot"
                / "dbo.usp_GetContactList.sql")
        snap.write_text(snap.read_text(encoding="utf-8") + "\n-- touched\n",
                        encoding="utf-8")
        out = json.loads(_capture(pipeline))
        assert out["written"], "a changed body must be re-extracted"

    def test_no_cache_flag_forces_re_extraction(self, pipeline):
        _capture(pipeline)
        out = json.loads(_capture(pipeline, "--no-cache"))
        assert out["written"]
        assert not out["cached"]


def _capture(pipeline, *extra) -> str:
    """Run build_proc_us --json and return its stdout."""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        build_proc_us.main(["--project", pipeline["project"], "--all",
                           "--workspace", str(pipeline["ws"]), "--json", *extra])
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# M3 (residual) — the DB ladder is a 2-rung ladder, and it is verified
# --------------------------------------------------------------------------- #

class TestLadderTraceabilityOnTheDbShape:
    """`check_ladder_traceability.py` used to bail out on a `db-module` unit.

    It looked for a 3a `analysis.md` that the DB path never produces, reported
    "artifacts missing" and returned exit 2 — indistinguishable from "the ladder
    has not been run yet". So the downward half of the DB chain (FEAT item →
    US AC → snapshot evidence) was never checked by anything.
    """

    def _run(self, pipeline, monkeypatch):
        from sdd_reverse_scripts import check_ladder_traceability as clt
        monkeypatch.setattr(clt, "workspace_root", lambda _root: pipeline["ws"])
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        inv = _inventory(pipeline)
        return clt, clt.check(pipeline["root"], inv["units"][0]["id"], None)

    def test_db_unit_is_recognised_and_actually_checked(self, pipeline, monkeypatch):
        _clt, report = self._run(pipeline, monkeypatch)
        assert report["ran"] is True, report.get("message")
        assert report["shape"] == "db-module"
        assert report["counts"]["feat_items"] > 0
        assert report["counts"]["us_acs"] > 0
        assert report["counts"]["tasks"] == 0      # no 3a rung, by design

    def test_feat_items_point_at_real_us_acs(self, pipeline, monkeypatch):
        _clt, report = self._run(pipeline, monkeypatch)
        dangling = [g for g in report["gaps"] if "dangling" in g]
        no_covers = [g for g in report["gaps"] if "no `covers:`" in g]
        assert not dangling, dangling
        assert not no_covers, no_covers

    def test_no_orphan_us_ac(self, pipeline, monkeypatch):
        _clt, report = self._run(pipeline, monkeypatch)
        orphans = [g for g in report["gaps"] if "orphan" in g]
        assert not orphans, orphans

    def test_evidence_is_resolved_on_disk_not_just_present(self, pipeline, monkeypatch):
        """`unknown:1` passed every gate before — a snapshot must actually exist."""
        clt, _ = self._run(pipeline, monkeypatch)
        assert clt._evidence_resolves(pipeline["root"], "unknown:1") is False
        real = next((pipeline["root"] / ".sys" / "proc-snapshot").glob("*.sql"))
        rel = real.relative_to(pipeline["root"]).as_posix()
        assert clt._evidence_resolves(pipeline["root"], f"{rel}:1-12") is True
        assert clt._evidence_resolves(pipeline["root"], ".sys/proc-snapshot/gone.sql:1") is False

    def test_a_stale_snapshot_reference_is_reported(self, pipeline, monkeypatch):
        clt, _ = self._run(pipeline, monkeypatch)
        for snap in (pipeline["root"] / ".sys" / "proc-snapshot").glob("*.sql"):
            snap.unlink()
        inv = _inventory(pipeline)
        report = clt.check(pipeline["root"], inv["units"][0]["id"], None)
        assert any("does not resolve" in g for g in report["gaps"]), report["gaps"]

    def test_verdict_is_informational_never_blocking(self, pipeline, monkeypatch):
        from sdd_reverse_scripts import check_ladder_traceability as clt
        monkeypatch.setattr(clt, "workspace_root", lambda _root: pipeline["ws"])
        _simulate_analyst(pipeline)
        build_proc_feats.main(["--project", pipeline["project"], "--all",
                              "--workspace", str(pipeline["ws"])])
        inv = _inventory(pipeline)
        rc = clt.main(["--project", str(pipeline["root"]),
                       "--unit", inv["units"][0]["id"], "--json"])
        assert rc == 0

    def test_code_shaped_unit_still_takes_the_three_rung_path(self, tmp_path, monkeypatch):
        """The DB branch must not swallow the code reverse it shares a file with."""
        from sdd_reverse_scripts import check_ladder_traceability as clt
        ws = tmp_path / "ws"
        (ws / "feats").mkdir(parents=True)
        (ws / "us").mkdir()
        monkeypatch.setattr(clt, "workspace_root", lambda _root: ws)
        (ws / "feats" / "7-Login.md").write_text(
            "\n".join(["---", "confidence: high", "---", "",
                       "## Functional Needs", "", "- SFD-1: x", ""]),
            encoding="utf-8")
        (ws / "us" / "7-1-Se-Connecter.md").write_text(
            "\n".join(["---", "ID: 7-1-Se-Connecter", "---", "",
                       "## Acceptance Criteria", "", "- AC-1: y", ""]),
            encoding="utf-8")
        report = clt.check(None, None, ws / "feats" / "7-Login.md")
        # No `source-proc:` anywhere → code shape → the missing 3a analysis is a
        # legitimate "not run yet", reported as such.
        assert report.get("shape") != "db-module"
        assert report["ran"] is False
