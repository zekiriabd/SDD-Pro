"""Unit tests for validate_fidelity.py — STEP 10 (hex) + STEP 11 (labels + components).

Coverage:
- PASS : tous tokens hex exacts dans CSS + tous labels trouvés + composants DS présents
- WARN : token toléré (distance RGB < 5%) ou quelques labels manquants
- FAIL : token absent OU 6+ labels manquants OU composant DS attendu absent
- MATCH-OVERRIDE : annotation HTML `ui-fidelity-override:hex-XXXXXX` bypass
- Edge : HTML inexistant / generated_dir inexistant → exit 2
- Pures : hex_to_rgb, rgb_distance_pct
- DS components : <table> sans DataGrid/Table → MISSING
- JSON output : --json produit summary + tokens + labels + components
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".claude" / "python" / "sdd_scripts" / "validate_fidelity.py"

sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))
from sdd_scripts.validate_fidelity import hex_to_rgb, rgb_distance_pct  # noqa: E402


def _run(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT)] + args
    return subprocess.run(cmd, capture_output=True, text=True)


class TestPureFunctions(unittest.TestCase):
    def test_hex_to_rgb_black(self) -> None:
        self.assertEqual(hex_to_rgb("000000"), (0, 0, 0))

    def test_hex_to_rgb_white(self) -> None:
        self.assertEqual(hex_to_rgb("ffffff"), (255, 255, 255))

    def test_hex_to_rgb_mid_gray(self) -> None:
        self.assertEqual(hex_to_rgb("808080"), (128, 128, 128))

    def test_rgb_distance_identical_is_zero(self) -> None:
        self.assertEqual(rgb_distance_pct((128, 128, 128), (128, 128, 128)), 0.0)

    def test_rgb_distance_max_is_100(self) -> None:
        self.assertAlmostEqual(
            rgb_distance_pct((0, 0, 0), (255, 255, 255)),
            100.0,
            places=2,
        )

    def test_rgb_distance_close_is_small(self) -> None:
        # #444444 vs #454545 → distance < 1%
        self.assertLess(rgb_distance_pct((0x44, 0x44, 0x44), (0x45, 0x45, 0x45)), 1.0)


class TestFidelityIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.html_path = self.root / "1-2-Bebes.html"
        self.gen_dir = self.root / "generated"
        self.gen_dir.mkdir()
        self.theme_path = self.gen_dir / "theme.css"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_html(self, content: str) -> None:
        self.html_path.write_text(content, encoding="utf-8")

    def _write_css(self, content: str) -> None:
        self.theme_path.write_text(content, encoding="utf-8")

    def _write_render(self, filename: str, content: str) -> None:
        (self.gen_dir / filename).write_text(content, encoding="utf-8")

    def _invoke(self, *extra: str) -> subprocess.CompletedProcess:
        return _run([
            "--html-path", str(self.html_path),
            "--generated-dir", str(self.gen_dir),
            "--theme-path", str(self.theme_path),
            "--json",
            *extra,
        ])

    # ---- exit code semantics ----

    def test_pass_all_exact_matches(self) -> None:
        self._write_html("""<html><body>
          <header>Title</header>
          <button style="color:#3366cc">Connexion</button>
          <p>Bienvenue sur la plateforme</p>
        </body></html>""")
        self._write_css(":root { --primary: #3366cc; }")
        # Labels présents + composant button matché
        self._write_render("Login.razor", """
          <h1>Title</h1>
          <RadzenButton Text="Connexion" />
          <p>Bienvenue sur la plateforme</p>
        """)
        result = self._invoke()
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout}\nstderr={result.stderr}")
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["decision"], "PASS")
        self.assertEqual(report["summary"]["hex_missing"], 0)

    def test_fail_when_hex_missing(self) -> None:
        self._write_html("""<html><body>
          <p>Bienvenue ici</p>
          <span style="color:#ff00ff">important</span>
        </body></html>""")
        self._write_css(":root { --primary: #336699; }")  # ne match pas #ff00ff
        self._write_render("Page.razor", "<p>Bienvenue ici</p>")
        result = self._invoke()
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["decision"], "FAIL")
        self.assertGreaterEqual(report["summary"]["hex_missing"], 1)

    def test_warn_when_hex_tolerated(self) -> None:
        # HTML: #444444 ; CSS: #454545 → distance < 5%
        self._write_html("""<html><body>
          <p>Bienvenue sur la plateforme</p>
          <span style="color:#444444">texte gris</span>
        </body></html>""")
        self._write_css(":root { --gray: #454545; }")
        self._write_render("Page.razor", "<p>Bienvenue sur la plateforme</p>")
        result = self._invoke()
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["decision"], "WARN")
        self.assertEqual(report["summary"]["hex_tolerated"], 1)

    def test_override_annotation_bypasses(self) -> None:
        # HTML déclare override → status MATCH-OVERRIDE (pas missing)
        self._write_html("""<html><body>
          <!-- ui-fidelity-override: hex-aabbcc justifié design system -->
          <span style="color:#aabbcc">texte</span>
          <p>Bienvenue sur la plateforme</p>
        </body></html>""")
        self._write_css(":root { --primary: #000000; }")  # ne contient PAS #aabbcc
        self._write_render("Page.razor", "<p>Bienvenue sur la plateforme</p>")
        result = self._invoke()
        report = json.loads(result.stdout)
        token = next(t for t in report["tokens"] if t["hex"] == "#aabbcc")
        self.assertEqual(token["status"], "MATCH-OVERRIDE")
        # Pas de FAIL puisque pas MISSING (modulo autres checks)
        self.assertNotEqual(report["summary"]["decision"], "FAIL")

    def test_fail_when_table_without_datagrid(self) -> None:
        # HTML contient <table> structurel mais rendu sans RadzenDataGrid/<Table>/v-data-table
        self._write_html("""<html><body>
          <table>
            <thead><tr><th>Nom</th></tr></thead>
            <tbody><tr><td>Bebe1</td></tr></tbody>
          </table>
          <p>Liste des bebes a gerer aujourd hui</p>
        </body></html>""")
        self._write_css("")
        # Render sans aucun DS table-component
        self._write_render("Page.razor", """
          <div>Liste des bebes a gerer aujourd hui</div>
          <p>Nom</p>
        """)
        result = self._invoke()
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        comps = report["components"]
        table_comp = next((c for c in comps if c["html_tag"] == "table"), None)
        self.assertIsNotNone(table_comp)
        self.assertEqual(table_comp["status"], "MISSING")

    def test_fail_when_too_many_labels_missing(self) -> None:
        # 7 labels HTML uniques (>4 chars), aucun n'apparaît dans render
        self._write_html("""<html><body>
          <h1>Premier titre tres clair</h1>
          <h2>Deuxieme titre lisible</h2>
          <p>Troisieme paragraphe distinct</p>
          <p>Quatrieme phrase importante</p>
          <p>Cinquieme element textuel</p>
          <p>Sixieme contenu different</p>
          <p>Septieme ligne supplementaire</p>
        </body></html>""")
        self._write_css("")
        # Render quasi vide
        self._write_render("Page.razor", "<div>Hello world</div>")
        result = self._invoke()
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertGreaterEqual(report["summary"]["labels_missing"], 6)

    def test_warn_when_few_labels_missing(self) -> None:
        # 2-3 labels missing, aucun token missing → WARN
        self._write_html("""<html><body>
          <h1>Titre principal lisible</h1>
          <p>Sous titre secondaire</p>
          <p>Texte fourni present</p>
        </body></html>""")
        self._write_css("")
        # Render contient seulement 1 label sur 3
        self._write_render("Page.razor", "<h1>Texte fourni present</h1>")
        result = self._invoke()
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["decision"], "WARN")

    # ---- edge cases ----

    def test_missing_html_path_returns_2(self) -> None:
        result = _run([
            "--html-path", str(self.root / "ghost.html"),
            "--generated-dir", str(self.gen_dir),
            "--json",
        ])
        self.assertEqual(result.returncode, 2)

    def test_missing_generated_dir_returns_2(self) -> None:
        self._write_html("<html></html>")
        result = _run([
            "--html-path", str(self.html_path),
            "--generated-dir", str(self.root / "ghost_dir"),
            "--json",
        ])
        self.assertEqual(result.returncode, 2)

    def test_json_output_has_required_keys(self) -> None:
        self._write_html("<html><body><p>Bienvenue sur la plateforme</p></body></html>")
        self._write_css("")
        self._write_render("Page.razor", "<p>Bienvenue sur la plateforme</p>")
        result = self._invoke()
        report = json.loads(result.stdout)
        self.assertIn("summary", report)
        self.assertIn("tokens", report)
        self.assertIn("labels", report)
        self.assertIn("components", report)
        self.assertIn("decision", report["summary"])

    def test_hex_tolerance_zero_disables_tolerance(self) -> None:
        # Avec --hex-tolerance-max-pct 0, #454545 ne tolère pas #444444
        self._write_html("""<html><body>
          <p>Bienvenue sur la plateforme</p>
          <span style="color:#444444">x</span>
        </body></html>""")
        self._write_css(":root { --c: #454545; }")
        self._write_render("Page.razor", "<p>Bienvenue sur la plateforme</p>")
        result = self._invoke("--hex-tolerance-max-pct", "0")
        # 0 tolerance → MISSING → FAIL
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["hex_missing"], 1)


if __name__ == "__main__":
    unittest.main()
