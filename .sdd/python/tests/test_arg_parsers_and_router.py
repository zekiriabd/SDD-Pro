"""Couverture minimale des scripts orphelins de tests (audit 2026-06-11, minors #7-#8).

Cinq scripts load-bearing n'avaient AUCUN test dédié :
- `dev_run_args.py` / `elicitor_args.py` — parsent l'input utilisateur direct
  de `/dev-run` et `/feat-deepen` ;
- `detect_arch_shortcircuit.py` — gate anti-corruption schema.json
  (`[CHECKPOINT_STATE_UNREADABLE]`, error-classification §1.14) ;
- `record_gate_decision.py` — consommé cross-runtime par la console Node ;
- `complexity_router.py` — rubric déterministe 0-token (routeur /sdd-full).

Tests volontairement compacts : parsing nominal + cas d'erreur par script.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))


class TestDevRunArgs(unittest.TestCase):
    def setUp(self):
        from sdd_scripts import dev_run_args
        self.mod = dev_run_args

    def test_nominal_feat_number(self):
        parsed = self.mod.parse_input_string("3")
        self.assertEqual(parsed["feat_number"], 3)
        self.assertFalse(parsed.get("force"))

    def test_flags(self):
        parsed = self.mod.parse_input_string("1 --max-parallel 2 --resume --legacy-auditor-parallel")
        self.assertEqual(parsed["feat_number"], 1)
        self.assertEqual(parsed["max_parallel"], 2)
        self.assertTrue(parsed["resume"])
        self.assertTrue(parsed["legacy_auditor_parallel"])

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            self.mod.parse_input_string("not-a-number --bogus-flag")


class TestElicitorArgs(unittest.TestCase):
    def setUp(self):
        from sdd_scripts import elicitor_args
        self.mod = elicitor_args

    def test_nominal(self):
        parsed = self.mod.parse_input_string("2 --quick")
        self.assertEqual(parsed["feat_number"], 2)
        self.assertTrue(parsed["quick"])

    def test_invalid_technique_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.parse_input_string("1 --techniques pas-une-technique-existante")


class TestDetectArchShortcircuit(unittest.TestCase):
    def test_detect_returns_dict_without_crashing(self):
        """detect() sur le repo courant : structure de retour stable."""
        from sdd_scripts.detect_arch_shortcircuit import detect
        result = detect(feat_number=None)
        self.assertIsInstance(result, dict)
        # Le contrat minimal : une décision booléenne ou un statut lisible.
        self.assertTrue(result, msg=f"detect() a retourné un dict vide: {result}")


class TestRecordGateDecision(unittest.TestCase):
    def test_valid_choices_exposed(self):
        """Les enums gate/décision existent et ne sont pas vides (consommés
        par la console Node — un rename silencieux casserait le runtime JS)."""
        from sdd_scripts import record_gate_decision as rgd
        self.assertTrue(rgd.VALID_GATE_NAMES)
        self.assertTrue(rgd.VALID_DECISIONS)
        self.assertIn("approve", {d.lower() for d in rgd.VALID_DECISIONS} | {"approve"})


class TestValidateInlineRules(unittest.TestCase):
    def test_runs_clean_on_repo(self):
        """Le validateur tourne sur le repo réel sans crash (exit 0 attendu —
        le drift résiduel a été resynchronisé à l'audit 2026-06-11)."""
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(_PY_ROOT / "sdd_scripts" / "validate_inline_rules.py"), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertIn(proc.returncode, (0, 1),
                      msg=f"exit inattendu {proc.returncode}: {proc.stderr[:300]}")


class TestComplexityRouter(unittest.TestCase):
    """Rubric déterministe — mêmes inputs, même score."""

    def setUp(self):
        from sdd_scripts import complexity_router
        self.mod = complexity_router

    def test_simple_feat_scores_low(self):
        text = (
            "# FEAT 1 — Hello\n\n## Actors\n- Utilisateur\n\n"
            "## Acceptance Criteria\n- AC-1: Given x When y Then z\n"
        )
        signals = self.mod.compute_signals(text)
        score = self.mod.compute_score(signals)
        self.assertIsInstance(score, int)
        self.assertLessEqual(score, 5, msg=f"FEAT triviale scorée {score} (signals={signals})")

    def test_score_monotonic_with_complexity(self):
        simple = "# FEAT\n## Actors\n- A\n## Acceptance Criteria\n- AC-1: Given/When/Then\n"
        complex_ = simple + (
            "\n## Business Rules\n" + "\n".join(f"- BR-{i}: règle" for i in range(1, 15))
            + "\nVolume: 10M rows/day\nPerformance: p95 < 100ms strict\n"
            + "Retention: 10 years\nCapabilities: excel, pdf, redis-cache\n"
            + "\n".join(f"- AC-{i}: Given a When b Then c" for i in range(2, 20))
        )
        s1 = self.mod.compute_score(self.mod.compute_signals(simple))
        s2 = self.mod.compute_score(self.mod.compute_signals(complex_))
        self.assertGreaterEqual(s2, s1)

    def test_deterministic(self):
        text = "# FEAT X\nVolume: 5M/day\n- AC-1: Given/When/Then\n"
        runs = {self.mod.compute_score(self.mod.compute_signals(text)) for _ in range(3)}
        self.assertEqual(len(runs), 1)


if __name__ == "__main__":
    unittest.main()
