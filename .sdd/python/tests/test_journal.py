"""Tests du journal d'exécution agentique (audit 2026-08-28, correction #5).

Ce que ces tests protègent, par ordre d'importance :

1. **L'append-only.** Aucune API d'update. Une correction est une nouvelle
   entrée reliée par `retry_of`. Un journal réinscriptible ne prouve rien.
2. **La provenance du prix.** `pricing_source` doit dire la vérité, et
   `cost_confidence` doit basculer en `lower-bound` dès qu'un seul appel est
   tarifé au repli. C'est la garantie qui empêche d'arbitrer un budget sur un
   total qui mélange des tarifs Opus réels et des tarifs Sonnet de repli.
3. **Le replay.** Une étape n'est rejouable que si une exécution ANTÉRIEURE,
   `ok`, au même triplet (agent, context_hash, inputs_hash), a produit une
   sortie. Toute autre définition transformerait le cache en source d'erreur.
4. **La normalisation des hashes.** CRLF vs LF ne doit pas invalider un
   replay — sinon le mécanisme ne survit pas à un clone sous Windows.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdd_lib import journal
from sdd_lib.console_db import connect, ensure_initialized


class _DbCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.db = self.root / "console.db"
        ensure_initialized(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class TestHashing(unittest.TestCase):
    def test_crlf_and_lf_hash_identically(self) -> None:
        """Sans ça, un clone Windows casse tout replay (autocrlf)."""
        self.assertEqual(
            journal.content_hash("a\r\nb\r\n"),
            journal.content_hash("a\nb\n"),
        )

    def test_trailing_whitespace_ignored(self) -> None:
        self.assertEqual(journal.content_hash("x"), journal.content_hash("x   \n\n"))

    def test_none_is_hashable(self) -> None:
        self.assertEqual(journal.content_hash(None), journal.content_hash(""))

    def test_inputs_hash_is_order_insensitive(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            root = Path(d)
            (root / "a.md").write_text("A", encoding="utf-8")
            (root / "b.md").write_text("B", encoding="utf-8")
            h1 = journal.inputs_hash(["a.md", "b.md"], root=root)
            h2 = journal.inputs_hash(["b.md", "a.md"], root=root)
            self.assertEqual(h1, h2)

    def test_missing_input_is_a_fact_not_an_error(self) -> None:
        """« l'agent a tourné SANS le schéma » doit se distinguer de
        « l'agent a tourné AVEC un autre schéma »."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            root = Path(d)
            (root / "a.md").write_text("A", encoding="utf-8")
            absent = journal.inputs_hash(["a.md", "schema.json"], root=root)
            (root / "schema.json").write_text("{}", encoding="utf-8")
            present = journal.inputs_hash(["a.md", "schema.json"], root=root)
            self.assertNotEqual(absent, present)


class TestCost(unittest.TestCase):
    def test_known_model_is_flagged_known(self) -> None:
        cost, src = journal.compute_cost("claude-sonnet-4-6", input_tokens=1_000_000)
        self.assertEqual(src, "known")
        self.assertAlmostEqual(cost, 3.0, places=4)

    def test_unknown_model_is_flagged_fallback_not_known(self) -> None:
        """Le cœur de la correction : un prix de repli ne doit JAMAIS se
        présenter comme un prix réel."""
        cost, src = journal.compute_cost("claude-nonexistent-9", input_tokens=1_000_000)
        self.assertEqual(src, "fallback")
        self.assertIsNotNone(cost)

    def test_no_model_yields_no_cost(self) -> None:
        """Inventer un coût à partir de rien est pire que de ne rien inscrire."""
        cost, src = journal.compute_cost(None, input_tokens=1_000_000)
        self.assertEqual(src, "unknown")
        self.assertIsNone(cost)

    def test_context_window_suffix_resolves_to_base_pricing(self) -> None:
        a, _ = journal.compute_cost("claude-opus-4-8", input_tokens=1_000)
        b, _ = journal.compute_cost("claude-opus-4-8[1m]", input_tokens=1_000)
        self.assertEqual(a, b)


class TestRecord(_DbCase):
    def test_record_returns_id_and_assigns_sequence(self) -> None:
        with connect(self.db) as c:
            i1 = journal.record(c, agent="po", run_id="r1", outcome="ok")
            i2 = journal.record(c, agent="arch", run_id="r1", outcome="ok")
            rows = journal.entries(c, run_id="r1")
        self.assertLess(i1, i2)
        self.assertEqual([r["seq"] for r in rows], [1, 2])

    def test_module_exposes_no_update_api(self) -> None:
        """Append-only : la garantie est structurelle, pas une convention."""
        forbidden = [n for n in dir(journal)
                     if any(k in n.lower() for k in ("update", "delete", "purge"))]
        self.assertEqual(forbidden, [])

    def test_unknown_outcome_is_normalized(self) -> None:
        """Un vocabulaire ouvert rendrait les agrégats illisibles."""
        with connect(self.db) as c:
            journal.record(c, agent="x", outcome="probably-fine")
            self.assertEqual(journal.entries(c)[0]["outcome"], "unknown")

    def test_cost_is_computed_with_its_provenance(self) -> None:
        with connect(self.db) as c:
            journal.record(c, agent="dev-backend", model="claude-opus-4-8",
                           input_tokens=100_000, outcome="ok")
            r = journal.entries(c)[0]
        self.assertEqual(r["pricing_source"], "known")
        self.assertAlmostEqual(r["cost_usd"], 1.5, places=3)

    def test_script_kind_records_zero_cost_as_information(self) -> None:
        """Un scan déterministe coûte 0 — et ce 0 mesure ce qu'on a cessé de
        payer au LLM. Il doit donc être journalisé, pas omis."""
        with connect(self.db) as c:
            journal.record(c, agent="scan_patterns", kind="script", outcome="ok")
            r = journal.entries(c)[0]
        self.assertEqual(r["kind"], "script")
        self.assertEqual(r["pricing_source"], "unknown")


class TestSummarize(_DbCase):
    def test_single_fallback_call_downgrades_confidence_to_lower_bound(self) -> None:
        with connect(self.db) as c:
            journal.record(c, agent="po", run_id="r", model="claude-sonnet-4-6",
                           input_tokens=1000, outcome="ok")
            journal.record(c, agent="dev", run_id="r", model="claude-unknown-1",
                           input_tokens=1000, outcome="ok")
            s = journal.summarize(c, run_id="r")
        self.assertEqual(s["cost_confidence"], "lower-bound")
        self.assertEqual(s["total"]["fallback_priced_calls"], 1)

    def test_all_known_yields_exact_confidence(self) -> None:
        with connect(self.db) as c:
            journal.record(c, agent="po", run_id="r", model="claude-sonnet-4-6",
                           input_tokens=1000, outcome="ok")
            s = journal.summarize(c, run_id="r")
        self.assertEqual(s["cost_confidence"], "exact")

    def test_empty_scope_is_none_not_exact(self) -> None:
        with connect(self.db) as c:
            s = journal.summarize(c, run_id="absent")
        self.assertEqual(s["cost_confidence"], "none")

    def test_retries_are_counted(self) -> None:
        with connect(self.db) as c:
            first = journal.record(c, agent="dev", run_id="r", outcome="fail")
            journal.record(c, agent="dev", run_id="r", attempt=2,
                           retry_of=first, outcome="ok")
            s = journal.summarize(c, run_id="r")
        self.assertEqual(s["total"]["retries"], 1)
        self.assertEqual(s["total"]["failed"], 1)


class TestReplayPlan(_DbCase):
    def _seed_ok(self, c, run: str, agent: str = "po", *, output: bool = True) -> None:
        journal.record(c, agent=agent, run_id=run, model="claude-sonnet-4-6",
                       context_hash="c" * 64, inputs_hash_="i" * 64,
                       output_hash=("o" * 64) if output else None,
                       input_tokens=1000, outcome="ok")

    def test_identical_prior_ok_run_is_replayable(self) -> None:
        with connect(self.db) as c:
            self._seed_ok(c, "r1")
            self._seed_ok(c, "r2")
            p = journal.replay_plan(c, "r2")
        self.assertEqual(p["cacheable_steps"], 1)

    def test_missing_context_hash_is_never_replayable(self) -> None:
        """L'absence de hash signale un spawn dont on ne maîtrise pas
        l'entrée — le traiter comme un hit serait servir du faux."""
        with connect(self.db) as c:
            self._seed_ok(c, "r1")
            journal.record(c, agent="po", run_id="r2", outcome="ok")
            p = journal.replay_plan(c, "r2")
        self.assertEqual(p["cacheable_steps"], 0)
        self.assertIn("pas de hash", p["steps"][0]["reason"])

    def test_prior_run_without_output_is_not_replayable(self) -> None:
        with connect(self.db) as c:
            self._seed_ok(c, "r1", output=False)
            self._seed_ok(c, "r2")
            p = journal.replay_plan(c, "r2")
        self.assertEqual(p["cacheable_steps"], 0)

    def test_prior_failed_run_is_not_replayable(self) -> None:
        with connect(self.db) as c:
            journal.record(c, agent="po", run_id="r1", context_hash="c" * 64,
                           inputs_hash_="i" * 64, output_hash="o" * 64, outcome="fail")
            self._seed_ok(c, "r2")
            p = journal.replay_plan(c, "r2")
        self.assertEqual(p["cacheable_steps"], 0)

    def test_different_agent_same_hashes_is_not_replayable(self) -> None:
        with connect(self.db) as c:
            self._seed_ok(c, "r1", agent="po")
            self._seed_ok(c, "r2", agent="arch")
            p = journal.replay_plan(c, "r2")
        self.assertEqual(p["cacheable_steps"], 0)


class TestBlobs(_DbCase):
    def test_blob_is_deduplicated_by_content(self) -> None:
        ref1, h1 = journal.store_blob("même contenu", "context", root=self.root)
        ref2, h2 = journal.store_blob("même contenu", "context", root=self.root)
        self.assertEqual(h1, h2)
        self.assertEqual(ref1, ref2)

    def test_verify_distinguishes_missing_from_corrupt(self) -> None:
        """Un blob purgé (rétention) n'est pas un problème d'intégrité ;
        un blob dont le hash a bougé, si."""
        ref, h = journal.store_blob("payload", "output", root=self.root)
        with connect(self.db) as c:
            journal.record(c, agent="po", output_hash=h, blob_ref=ref, outcome="ok")
            v = journal.verify_blobs(c, root=self.root)
            self.assertTrue(v["ok"], v)

            (self.root / ref).write_text("altéré", encoding="utf-8")
            v = journal.verify_blobs(c, root=self.root)
            self.assertEqual(v["corrupt"], [ref])
            self.assertEqual(v["missing"], [])

            (self.root / ref).unlink()
            v = journal.verify_blobs(c, root=self.root)
            self.assertEqual(v["missing"], [ref])
            self.assertEqual(v["corrupt"], [])


class TestHookIntegration(unittest.TestCase):
    def test_token_usage_hook_calls_the_journal(self) -> None:
        """Le hook est l'appelant réel du journal : sans lui, le composant
        rejoindrait la liste des briques non câblées."""
        import inspect
        from sdd_hooks import record_token_usage
        self.assertTrue(hasattr(record_token_usage, "_record_journal_entry"))
        src = inspect.getsource(record_token_usage)
        self.assertIn("_record_journal_entry(conn, entry, run_id)", src)

    def test_hook_marks_posttooluse_outcome_unknown_not_ok(self) -> None:
        """Un tool qui rend la main ne prouve pas que l'agent a réussi.
        Écrire `ok` partout ferait du compteur d'échecs une décoration."""
        import inspect
        from sdd_hooks import record_token_usage
        src = inspect.getsource(record_token_usage._record_journal_entry)
        self.assertIn('"ok" if hook_event.startswith("SubagentStop") else "unknown"', src)


if __name__ == "__main__":
    unittest.main()
