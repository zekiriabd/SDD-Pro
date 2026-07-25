"""C4 fix (audit reverse-quality 2026-07-24): detected-but-unsupported UI
families (Delphi .dfm, VB6 .frm) must return an explicit `parser_unsupported`
error instead of silently running the HTML regex path and yielding an empty
(misleading) structure.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_reverse.ui_template_parser import parse_template  # noqa: E402


class TestUnsupportedUiFamilies(unittest.TestCase):
    def _parse(self, name: str, body: str) -> dict:
        with TemporaryDirectory() as td:
            p = Path(td) / name
            p.write_text(body, encoding="utf-8")
            return parse_template(p)

    def test_delphi_dfm_flags_parser_unsupported(self):
        res = self._parse("MainForm.dfm",
                          "object MainForm: TForm\n  Caption = 'Connexion'\nend\n")
        self.assertEqual(res["error"], "parser_unsupported")
        self.assertEqual(res["parser_missing"], "delphi-dfm")
        # And it does NOT pretend to have parsed controls.
        self.assertEqual(res["elements"], [])
        self.assertEqual(res["forms"], [])

    def test_delphi_pas_flags_parser_unsupported(self):
        res = self._parse("MainForm.pas", "unit MainForm;\ninterface\nend.\n")
        self.assertEqual(res["error"], "parser_unsupported")

    def test_vb6_frm_flags_parser_unsupported(self):
        res = self._parse("Login.frm",
                          'VERSION 5.00\nBegin VB.Form frmLogin\n  Caption = "Login"\nEnd\n')
        self.assertEqual(res["error"], "parser_unsupported")
        self.assertEqual(res["parser_missing"], "vb6-form")

    def test_supported_html_still_parses(self):
        res = self._parse("Page.html",
                          '<html><body><form id="f"><input type="text" id="u"/>'
                          '</form></body></html>')
        self.assertNotIn("error", res)
        self.assertTrue(any(e.get("id") == "u" for e in res["elements"]))


if __name__ == "__main__":
    unittest.main()
