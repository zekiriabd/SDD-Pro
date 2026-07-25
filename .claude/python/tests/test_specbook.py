"""Tests for the Cahier des charges generator (docx_writer + generate_specbook).

Covers (audit reverse-quality 2026-07-24):
  * DocxBuilder emits a valid, well-formed, Word-openable OOXML ZIP.
  * DocxBuilder output is byte-deterministic (idempotence contract).
  * FEAT parsing lifts the functional sections + reverse metadata.
  * The generator runs in both modes (humanised cache hit / raw fallback) and
    always produces a valid .docx + .md mirror + manifest.
"""
from __future__ import annotations

import sys
import unittest
import zipfile
import xml.dom.minidom as minidom
from pathlib import Path
from tempfile import TemporaryDirectory

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.docx_writer import DocxBuilder  # noqa: E402
from sdd_scripts.generate_specbook import (  # noqa: E402
    feat_hash, parse_feat, main as specbook_main,
)

_FEAT_FWD = """# FEAT: Avoir

FEAT ID: 1-Avoir
Status: Ready

## Context
Suivi des avoirs.

## Actors
- Gérant: consulte

## Functional Needs
- SFD-1: Consulter la fiche
- SFD-2: Piloter les droits

## Business Rules
- BR-1: Pas de suppression si utilisé

## Acceptance Criteria
- AC-1: Given un avoir When ouvert Then montant affiché

## Functional Deliverables
- FD-1: Écran de consultation

## Out of Scope
- Facturation
"""

_FEAT_REV = """# FEAT: Reporting

FEAT ID: 2-Reporting
Status: Draft
<!-- REVERSE-GATE: confidence=medium ; allow-sdd-full=false -->

## Context
Module hérité.

## Functional Needs
- SFD-1: Générer l'état mensuel
"""


def _valid_docx(data: bytes) -> bool:
    import io
    z = zipfile.ZipFile(io.BytesIO(data))
    if z.testzip() is not None:
        return False
    required = {"[Content_Types].xml", "word/document.xml", "word/styles.xml"}
    if not required.issubset(set(z.namelist())):
        return False
    for name in z.namelist():
        if name.endswith((".xml", ".rels")):
            minidom.parseString(z.read(name))  # raises on malformed
    return True


class TestDocxWriter(unittest.TestCase):
    def test_valid_and_wellformed(self):
        d = DocxBuilder()
        d.title("T", subtitle="S")
        d.heading("H1", 1)
        d.paragraph("body ", runs=[("bold", {"bold": True})])
        d.bullet_list(["a", "b"])
        d.number_list(["one", "two"])
        d.table([["h1", "h2"], ["v1", "v2"]], header=True)
        d.callout("note", label="Note")
        d.page_break()
        self.assertTrue(_valid_docx(d.to_bytes()))

    def test_deterministic(self):
        def build():
            d = DocxBuilder()
            d.title("Cahier")
            d.heading("X", 1)
            d.paragraph("même contenu")
            return d.to_bytes()
        self.assertEqual(build(), build())

    def test_xml_escaping(self):
        d = DocxBuilder()
        d.paragraph('a < b & c > d "e"')
        self.assertTrue(_valid_docx(d.to_bytes()))


class TestFeatParsing(unittest.TestCase):
    def test_forward(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "1-Avoir.md"
            p.write_text(_FEAT_FWD, encoding="utf-8")
            spec = parse_feat(p)
            self.assertEqual(spec.feat_id, "1-Avoir")
            self.assertEqual(spec.status, "Ready")
            self.assertFalse(spec.is_reverse)
            self.assertEqual(len(spec.sections["Functional Needs"]), 2)
            self.assertIn("Consulter la fiche", spec.sections["Functional Needs"])

    def test_reverse_metadata(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "2-Reporting.md"
            p.write_text(_FEAT_REV, encoding="utf-8")
            spec = parse_feat(p)
            self.assertTrue(spec.is_reverse)
            self.assertEqual(spec.confidence, "medium")


class TestGeneratorEndToEnd(unittest.TestCase):
    def _setup(self, td: str):
        root = Path(td)
        feats = root / "feats"
        docs = root / "docs"
        feats.mkdir()
        (feats / "1-Avoir.md").write_text(_FEAT_FWD, encoding="utf-8")
        (feats / "2-Reporting.md").write_text(_FEAT_REV, encoding="utf-8")
        return feats, docs

    def test_raw_fallback(self):
        with TemporaryDirectory() as td:
            feats, docs = self._setup(td)
            rc = specbook_main(["--feats-dir", str(feats), "--out-dir", str(docs),
                                "--project", "Démo", "--json"])
            self.assertEqual(rc, 0)
            docx = docs / "cahier-des-charges.docx"
            self.assertTrue(docx.exists())
            self.assertTrue(_valid_docx(docx.read_bytes()))
            self.assertTrue((docs / "cahier-des-charges.md").exists())
            self.assertTrue((docs / ".sys" / "specbook-manifest.json").exists())

    def test_humanised_cache_hit(self):
        with TemporaryDirectory() as td:
            feats, docs = self._setup(td)
            sections = docs / ".sys" / "sections"
            sections.mkdir(parents=True)
            h = feat_hash((feats / "1-Avoir.md").read_text(encoding="utf-8"))
            (sections / "1-Avoir.md").write_text(
                f"---\nfeat_id: 1-Avoir\nfeat_hash: {h}\nsource: forward\n---\n"
                "## Résumé\nUn texte humain clair.\n"
                "## Ce que le système doit permettre\n- Ouvrir la fiche.\n",
                encoding="utf-8",
            )
            rc = specbook_main(["--feats-dir", str(feats), "--out-dir", str(docs), "--json"])
            self.assertEqual(rc, 0)
            import json
            man = json.loads((docs / ".sys" / "specbook-manifest.json").read_text(encoding="utf-8"))
            modes = {m["feat_id"]: m["mode"] for m in man["feats"]}
            self.assertEqual(modes["1-Avoir"], "humanised")
            self.assertEqual(modes["2-Reporting"], "raw")

    def test_stale_cache_falls_back(self):
        with TemporaryDirectory() as td:
            feats, docs = self._setup(td)
            sections = docs / ".sys" / "sections"
            sections.mkdir(parents=True)
            (sections / "1-Avoir.md").write_text(
                "---\nfeat_id: 1-Avoir\nfeat_hash: sha256:STALE\nsource: forward\n---\n"
                "## Résumé\nObsolète.\n", encoding="utf-8",
            )
            rc = specbook_main(["--feats-dir", str(feats), "--out-dir", str(docs), "--json"])
            self.assertEqual(rc, 0)
            import json
            man = json.loads((docs / ".sys" / "specbook-manifest.json").read_text(encoding="utf-8"))
            modes = {m["feat_id"]: m["mode"] for m in man["feats"]}
            self.assertEqual(modes["1-Avoir"], "raw")  # stale hash → fallback

    def test_no_feats(self):
        from sdd_lib.exit_codes import FAIL_FAST
        with TemporaryDirectory() as td:
            rc = specbook_main(["--feats-dir", str(Path(td) / "empty"),
                                "--out-dir", str(Path(td) / "out")])
            self.assertEqual(rc, FAIL_FAST)


if __name__ == "__main__":
    unittest.main()
