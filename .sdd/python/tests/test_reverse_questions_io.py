"""C3 (audit reverse-quality 2026-07-24) — close the human loop in one run.

reverse_questions_io.py gives the orchestrator a deterministic surface to
(a) list still-open questions and (b) write one answer back atomically, so the
interactive close-loop mode never free-hands the markdown structure.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse_scripts.reverse_questions_io import (  # noqa: E402
    parse_blocks, list_open, set_answer,
)

_QMD = """# Questions reverse — LegacyApp

<!-- QUESTIONS: total=3 ; critical=1 ; generated=2026-07-24 -->

## Q-1 — Plafond avoir

- **Source** : FEAT 1-Avoir#BR-2
- **Constat** : seuil 1000 inféré
- **Impact** : critical — fiabilité FEAT
- **Question** : Le plafond est-il 1000 EUR ?
- **Réponse** :
- **Statut** : ouverte

## Q-2 — Titre écran

- **Source** : completeness-review U-2
- **Constat** : titre ambigu
- **Impact** : minor — cosmétique
- **Question** : "Avoirs" ou "Mes avoirs" ?
- **Réponse** :
- **Statut** : ouverte

## Q-3 — Déjà répondu

- **Source** : FEAT 2-X#AC-1
- **Impact** : moderate — x
- **Question** : Déjà traité ?
- **Réponse** : Oui, confirmé.
- **Statut** : ingérée (2026-07-20)
"""


class TestParse(unittest.TestCase):
    def test_parse_blocks_count_and_fields(self):
        blocks = parse_blocks(_QMD)
        self.assertEqual([b["id"] for b in blocks], ["Q-1", "Q-2", "Q-3"])
        q1 = blocks[0]
        self.assertEqual(q1["impact"], "critical")
        self.assertEqual(q1["question"], "Le plafond est-il 1000 EUR ?")
        self.assertEqual(q1["reponse"], "")

    def test_list_open_excludes_answered_and_sorts_by_impact(self):
        openq = list_open(_QMD)
        # Q-3 answered+ingérée → excluded ; critical before minor.
        self.assertEqual([q["id"] for q in openq], ["Q-1", "Q-2"])
        self.assertEqual(openq[0]["impact"], "critical")


class TestSetAnswer(unittest.TestCase):
    def test_set_answer_fills_reponse(self):
        new, msg = set_answer(_QMD, "Q-1", "Oui, 1000 EUR TTC.")
        self.assertIn("Q-1 answered", msg)
        # Only Q-1's Réponse is filled; Q-2 still open.
        self.assertEqual([q["id"] for q in list_open(new)], ["Q-2"])
        b1 = next(b for b in parse_blocks(new) if b["id"] == "Q-1")
        self.assertEqual(b1["reponse"], "Oui, 1000 EUR TTC.")

    def test_set_answer_collapses_newlines(self):
        new, _ = set_answer(_QMD, "Q-2", "Ligne un\nligne deux")
        b = next(x for x in parse_blocks(new) if x["id"] == "Q-2")
        self.assertEqual(b["reponse"], "Ligne un ligne deux")

    def test_set_answer_unknown_id(self):
        new, msg = set_answer(_QMD, "Q-9", "x")
        self.assertIsNone(new)
        self.assertIn("not found", msg)

    def test_does_not_touch_other_blocks(self):
        new, _ = set_answer(_QMD, "Q-1", "réponse")
        b3 = next(b for b in parse_blocks(new) if b["id"] == "Q-3")
        self.assertEqual(b3["reponse"], "Oui, confirmé.")  # untouched


class TestCli(unittest.TestCase):
    def test_cli_roundtrip(self):
        from sdd_reverse_scripts.reverse_questions_io import main
        with TemporaryDirectory() as td:
            p = Path(td) / "questions.md"
            p.write_text(_QMD, encoding="utf-8")
            self.assertEqual(main([str(p), "--list-open", "--json"]), 0)
            self.assertEqual(main([str(p), "--set-answer", "Q-1", "--text", "ok"]), 0)
            self.assertEqual(main([str(p), "--set-answer", "Q-9", "--text", "x"]), 1)


if __name__ == "__main__":
    unittest.main()
