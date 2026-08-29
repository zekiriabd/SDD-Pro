"""Tests du scan déterministe de patterns (audit 2026-08-28, corrections #2 et #6).

Ce que ces tests protègent :

1. **Le rappel.** Un secret AWS en dur DOIT être trouvé, à chaque exécution,
   sans dépendre du rappel d'un LLM sur un contexte chargé. C'est la raison
   d'être du basculement.
2. **L'honnêteté du périmètre.** Le scan ne doit jamais laisser croire qu'il
   couvre les 23 classes du catalogue. Les classes sans regex sont déclarées
   `llm_only`, celles dont les regex sont inexécutables sont déclarées
   `degraded` — la confusion entre les deux masquerait une dette réparable.
3. **Le hard-blocking.** Une classe marquée `hard_blocking` force le rouge
   quel que soit le seuil configuré. Sinon le seuil pourrait neutraliser une
   injection SQL.
4. **L'idempotence.** Relancer un scan remplace ses findings, ne les
   accumule pas — trois runs ne doivent pas tripler le verdict.
5. **Le câblage.** `sdd_review.py` doit réellement appeler le scan. Un
   scanner sans appelant serait la 9ᵉ brique orpheline du framework.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from sdd_lib.console_db import connect, ensure_initialized
from sdd_lib.paths import repo_root
from sdd_scripts import scan_patterns as sp


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestCatalogLoading(unittest.TestCase):
    def test_both_catalogs_load(self) -> None:
        for name in ("security", "code-review"):
            cat = sp.load_catalog(name, repo_root())
            self.assertGreater(len(cat["classes"]), 0, name)
            self.assertEqual(cat["bad_regex"], [], f"{name}: regex non compilable")

    def test_classes_without_regex_are_declared_llm_only(self) -> None:
        """Le catalogue sécurité laisse volontairement 11 classes sans regex
        (BROKEN_AUTHN, IDOR, SSRF…) : elles exigent de comprendre un flux."""
        cat = sp.load_catalog("security", repo_root())
        self.assertIn("[SEC_IDOR]", cat["llm_only"])
        self.assertIn("[SEC_SSRF_RISK]", cat["llm_only"])
        self.assertNotIn("[SEC_SECRET_HARDCODED]", cat["llm_only"])

    def test_anti_pattern_without_requires_is_declared_not_silently_dropped(self) -> None:
        """Les 4 règles CORS déclarent un point d'entrée sans déclarer la
        protection attendue. Les ignorer en silence donnerait un faux vert."""
        cat = sp.load_catalog("security", repo_root())
        classes = {u["class"] for u in cat["skipped_unscannable"]}
        self.assertIn("[SEC_CORS_MISSING]", classes)
        self.assertIn("[SEC_CORS_MISSING]", cat["degraded"])
        # Une classe dégradée n'est PAS une classe llm_only : la distinction
        # sépare une dette réparable d'une limite de nature.
        self.assertNotIn("[SEC_CORS_MISSING]", cat["llm_only"])


class TestDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _scan(self, catalog: str = "security") -> dict:
        return sp.run_catalog(catalog, feat_n=1, scan_root=self.root / "src",
                              repo=self.root, fail_on="critical")

    def test_hardcoded_aws_key_is_always_found(self) -> None:
        _write(self.root, "src/Api/A.cs",
               'class A { const string K = "AKIAIOSFODNN7EXAMPLE"; }')
        r = self._scan()
        classes = {f["issue_class"] for f in r["findings"]}
        self.assertIn("[SEC_SECRET_HARDCODED]", classes)

    def test_hard_blocking_forces_red_whatever_the_threshold(self) -> None:
        """Un seuil laxiste ne doit pas pouvoir neutraliser un secret en dur."""
        _write(self.root, "src/Api/A.cs",
               'class A { const string K = "AKIAIOSFODNN7EXAMPLE"; }')
        r = sp.run_catalog("security", feat_n=1, scan_root=self.root / "src",
                           repo=self.root, fail_on="blocker")
        self.assertEqual(r["verdict"], "RED")
        self.assertTrue(any("hard-blocking" in x for x in r["reasons"]))

    def test_clean_code_is_green(self) -> None:
        _write(self.root, "src/Api/A.cs", "class A { int X() => 1; }")
        self.assertEqual(self._scan()["verdict"], "GREEN")

    def test_no_source_is_green_not_an_error(self) -> None:
        """Absence de code n'est pas un échec de scan."""
        r = self._scan()
        self.assertEqual(r["verdict"], "GREEN")
        self.assertEqual(r["manifest"]["files_scanned"], 0)

    def test_same_class_twice_on_one_line_yields_one_finding(self) -> None:
        """Cas réel : `var md5 = ...MD5.Create()` matche deux fois la regex
        crypto (nom de variable ET appel). Deux lignes en base gonfleraient le
        compte de findings et le verdict autant que le rapport humain."""
        _write(self.root, "src/Api/A.cs",
               "class A { void X(){ var md5 = System.Security.Cryptography.MD5.Create(); } }")
        hits = [f for f in self._scan()["findings"]
                if f["issue_class"] == "[SEC_CRYPTO_WEAK]"]
        self.assertEqual(len(hits), 1)

    def test_two_distinct_classes_on_one_line_stay_two_findings(self) -> None:
        """La déduplication est étroite par conception : un secret en dur DANS
        un appel crypto faible, c'est bien deux problèmes."""
        _write(self.root, "src/Api/A.cs",
               'class A { void X(){ var k="AKIAIOSFODNN7EXAMPLE"; var m=MD5.Create(); } }')
        r = self._scan()
        self.assertGreaterEqual(len({f["issue_class"] for f in r["findings"]}), 2)

    def test_language_scoping_is_respected(self) -> None:
        """Une regex `react` ne doit pas tourner sur du C#."""
        _write(self.root, "src/App/List.tsx",
               "export const L = ({i}) => i.map((x, idx) => <li key={idx}/>);")
        r = sp.run_catalog("code-review", feat_n=1, scan_root=self.root / "src",
                           repo=self.root, fail_on="critical")
        self.assertIn("[REVIEW_ANTI_PATTERN_KEY_INDEX]",
                      {f["issue_class"] for f in r["findings"]})

    def test_build_artifacts_are_excluded_by_path_segment(self) -> None:
        _write(self.root, "src/Api/bin/Gen.cs",
               'class G { const string K = "AKIAIOSFODNN7EXAMPLE"; }')
        self.assertEqual(self._scan()["manifest"]["files_scanned"], 0)

    def test_exclusion_is_segment_anchored_not_substring(self) -> None:
        """Reprise de la correction de quality_scan : `object_mapper.cs` ne
        doit pas être exclu parce que son nom contient « obj »."""
        _write(self.root, "src/Api/object_mapper.cs", "class M {}")
        self.assertEqual(self._scan()["manifest"]["files_scanned"], 1)

    def test_findings_are_sorted_by_descending_severity(self) -> None:
        _write(self.root, "src/Api/A.cs",
               'class A { const string K="AKIAIOSFODNN7EXAMPLE";\n'
               ' void X(){ var m=MD5.Create(); var r=new Random(); } }')
        sev = [sp.SEVERITY_RANK[f["severity"]] for f in self._scan()["findings"]]
        self.assertEqual(sev, sorted(sev, reverse=True))


class TestVerdict(unittest.TestCase):
    def test_no_findings_is_green(self) -> None:
        self.assertEqual(sp.compute_verdict([], "critical"), ("GREEN", []))

    def test_below_threshold_is_warn_not_green(self) -> None:
        """Un finding sous le seuil reste un signal : il ne doit pas
        disparaître dans un vert."""
        v, reasons = sp.compute_verdict(
            [{"issue_class": "[X]", "severity": "minor", "hard_blocking": False}],
            "critical")
        self.assertEqual(v, "WARN")
        self.assertEqual(reasons, [])

    def test_at_threshold_is_red(self) -> None:
        v, _ = sp.compute_verdict(
            [{"issue_class": "[X]", "severity": "serious", "hard_blocking": False}],
            "serious")
        self.assertEqual(v, "RED")


class TestPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.db = self.root / "console.db"
        ensure_initialized(self.db)
        self.findings = [{
            "issue_class": "[SEC_SECRET_HARDCODED]", "severity": "critical",
            "hard_blocking": True, "owasp": "A02", "cwe": "CWE-798",
            "file_path": "src/A.cs", "line": 3, "message": "AWS key",
        }]
        self.manifest = {"scanned_classes": 11, "files_scanned": 1,
                         "llm_only_classes": [], "degraded_classes": [],
                         "skipped_unscannable": []}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rerun_replaces_findings_instead_of_accumulating(self) -> None:
        with connect(self.db) as c:
            for _ in range(3):
                sp.persist(c, catalog_name="security", feat_n=1, verdict="RED",
                           findings=self.findings, manifest=self.manifest)
            n = c.execute(
                "SELECT COUNT(*) FROM qa_security WHERE feat_n=1 AND mode='scan'"
            ).fetchone()[0]
        self.assertEqual(n, 1, "le scan doit être idempotent, pas cumulatif")

    def test_auditor_run_is_recorded_under_its_own_id(self) -> None:
        """Le scan s'enregistre sous `security-scan`, JAMAIS sous `security`.

        `/sdd-review --ensure-scans` bloque (exit 3) si la source `security`
        est absente. Usurper l'id de l'agent aurait satisfait la gate sans que
        le `security-reviewer` ait tourné : les 11 classes que nulle regex ne
        couvre (IDOR, SSRF, BROKEN_AUTHN…) auraient été réputées vérifiées.
        """
        with connect(self.db) as c:
            sp.persist(c, catalog_name="security", feat_n=1, verdict="RED",
                       findings=self.findings, manifest=self.manifest)
            ids = [r[0] for r in c.execute(
                "SELECT auditor FROM auditor_runs WHERE feat_n=1")]
        self.assertEqual(ids, ["security-scan"])
        self.assertNotIn("security", ids)

    def test_deterministic_findings_do_not_prove_the_agent_ran(self) -> None:
        """Symétrie côté lecture : un finding déterministe alimente le verdict
        mais ne vaut pas preuve d'exécution d'un agent."""
        from sdd_scripts._review_fetch import _is_agent_row
        self.assertFalse(_is_agent_row({"detector": "deterministic"}))
        self.assertTrue(_is_agent_row({"detector": "agent"}))
        # base restée en v7 (colonne absente) : comportement d'avant préservé
        self.assertTrue(_is_agent_row({}))

    def test_scan_is_journaled_as_a_script(self) -> None:
        """Le déterministe se journalise comme l'agentique : un coût nul
        mesure ce qu'on a cessé de payer au LLM."""
        from sdd_lib import journal
        with connect(self.db) as c:
            sp.persist(c, catalog_name="security", feat_n=1, verdict="RED",
                       findings=self.findings, manifest=self.manifest)
            rows = journal.entries(c)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "script")
        self.assertEqual(rows[0]["gate_verdict"], "RED")


class TestWiring(unittest.TestCase):
    def test_sdd_review_calls_the_scan(self) -> None:
        """Le test qui empêche ce composant de rejoindre la liste des briques
        implémentées-mais-jamais-appelées."""
        from sdd_scripts import sdd_review
        self.assertIn("run_pattern_scan", inspect.getsource(sdd_review.main))

    def test_scan_helper_passes_no_fail(self) -> None:
        """Un verdict RED n'est pas une panne de scan : laisser l'exit 4
        remonter comme une erreur de sous-processus ferait dire à
        l'agrégateur « infra cassée » là où il y a une faille."""
        from sdd_scripts._review_fetch import run_pattern_scan
        self.assertIn("--no-fail", inspect.getsource(run_pattern_scan))


class TestCli(unittest.TestCase):
    def test_rejects_invalid_feat_number(self) -> None:
        self.assertEqual(sp.main(["--feat-number", "0", "--dry-run"]), 1)

    def test_dry_run_writes_nothing_and_succeeds(self) -> None:
        self.assertIn(sp.main(["--feat-number", "1", "--dry-run",
                               "--catalog", "security"]), (0, 4))


if __name__ == "__main__":
    unittest.main()


class TestNoClobbering(unittest.TestCase):
    """Verrou de la régression du 2026-08-28.

    `scan_patterns` et `ingest_agent_report` partagent `qa_code_review` et
    `qa_security(mode='scan')`. Dans `/sdd-full`, les agents écrivent au STEP
    6.4.B et `/sdd-review` (gate 4.8, BLOQUANTE par défaut) déclenche le scan
    ensuite. Une purge non bornée effaçait donc les findings des reviewers LLM
    avant le calcul du verdict : faux vert sur gate bloquante.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / "console.db"
        ensure_initialized(self.db)
        self.manifest = {"scanned_classes": 5, "files_scanned": 0,
                         "llm_only_classes": [], "degraded_classes": [],
                         "skipped_unscannable": []}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _agent_finding(self, c, table: str) -> None:
        from sdd_lib.console_db import (insert_qa_code_review_batch,
                                        insert_qa_security_batch)
        if table == "qa_code_review":
            insert_qa_code_review_batch(c, feat_n=1, verdict="red", issues=[{
                "issue_class": "[REVIEW_MISSING_ERROR_HANDLING]",
                "severity": "serious", "file_path": "src/A.cs", "line": 10,
                "message": "trouvé par le reviewer LLM"}])
        else:
            insert_qa_security_batch(c, feat_n=1, mode="scan", verdict="red", issues=[{
                "issue_class": "[SEC_IDOR]", "severity": "serious",
                "file_path": "src/A.cs", "line": 20,
                "message": "flux compris par le reviewer LLM"}])

    def test_scan_does_not_erase_code_review_agent_findings(self) -> None:
        with connect(self.db) as c:
            self._agent_finding(c, "qa_code_review")
            sp.persist(c, catalog_name="code-review", feat_n=1, verdict="GREEN",
                       findings=[], manifest=self.manifest)
            kept = c.execute(
                "SELECT COUNT(*) FROM qa_code_review WHERE feat_n=1 AND detector='agent'"
            ).fetchone()[0]
        self.assertEqual(kept, 1, "les findings du reviewer LLM ont été effacés")

    def test_scan_does_not_erase_security_agent_findings(self) -> None:
        with connect(self.db) as c:
            self._agent_finding(c, "qa_security")
            sp.persist(c, catalog_name="security", feat_n=1, verdict="GREEN",
                       findings=[], manifest=self.manifest)
            kept = c.execute(
                "SELECT COUNT(*) FROM qa_security "
                "WHERE feat_n=1 AND mode='scan' AND detector='agent'"
            ).fetchone()[0]
        self.assertEqual(kept, 1)

    def test_agent_ingest_does_not_erase_deterministic_findings(self) -> None:
        """La symétrie compte autant : si l'agent tournait après le scan, il
        ne doit pas davantage effacer le plancher de rappel déterministe."""
        from sdd_lib.console_db import replace_qa_auditor_for_feat
        det = [{"issue_class": "[SEC_SECRET_HARDCODED]", "severity": "critical",
                "hard_blocking": True, "file_path": "src/A.cs", "line": 3,
                "message": "AWS key"}]
        with connect(self.db) as c:
            sp.persist(c, catalog_name="security", feat_n=1, verdict="RED",
                       findings=det, manifest=self.manifest)
            # ce que fait ingest_agent_report
            replace_qa_auditor_for_feat(c, "qa_security", 1, mode="scan",
                                        detector="agent")
            self._agent_finding(c, "qa_security")
            kept = c.execute(
                "SELECT COUNT(*) FROM qa_security "
                "WHERE feat_n=1 AND detector='deterministic'").fetchone()[0]
        self.assertEqual(kept, 1)

    def test_both_detectors_coexist_and_both_feed_the_verdict(self) -> None:
        with connect(self.db) as c:
            self._agent_finding(c, "qa_code_review")
            sp.persist(c, catalog_name="code-review", feat_n=1, verdict="WARN",
                       findings=[{"issue_class": "[REVIEW_ANTI_PATTERN_KEY_INDEX]",
                                  "severity": "moderate", "hard_blocking": False,
                                  "file_path": "src/L.tsx", "line": 2,
                                  "message": "key={index}"}],
                       manifest=self.manifest)
            rows = [tuple(r) for r in c.execute(
                "SELECT detector, COUNT(*) FROM qa_code_review WHERE feat_n=1 "
                "GROUP BY detector ORDER BY detector")]
        self.assertEqual(rows, [("agent", 1), ("deterministic", 1)])

    def test_rerun_is_still_idempotent_per_detector(self) -> None:
        """L'idempotence ne doit pas être perdue en gagnant la coexistence."""
        det = [{"issue_class": "[SEC_SECRET_HARDCODED]", "severity": "critical",
                "hard_blocking": True, "file_path": "src/A.cs", "line": 3,
                "message": "AWS key"}]
        with connect(self.db) as c:
            for _ in range(3):
                sp.persist(c, catalog_name="security", feat_n=1, verdict="RED",
                           findings=det, manifest=self.manifest)
            n = c.execute(
                "SELECT COUNT(*) FROM qa_security "
                "WHERE feat_n=1 AND detector='deterministic'").fetchone()[0]
        self.assertEqual(n, 1)
