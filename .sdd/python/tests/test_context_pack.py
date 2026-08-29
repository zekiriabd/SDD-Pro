"""Tests du Context Engineering Layer (audit 2026-08-28, correction #4).

Ce que ces tests protègent, et pourquoi c'est dans cet ordre :

1. **Le biais vers la conservation.** Un retrait erroné dégrade la génération
   EN SILENCE ; un octet de trop se voit dans le budget. Donc : une section
   `needed` n'est jamais retirée, une section marquée par son auteur
   (« load-bearing », « CRITIQUE ») n'est jamais retirée quel que soit le
   rôle, et un rôle inconnu ne retire rien.
2. **La granularité au niveau `###`.** Le premier jet découpait aux `##` et ne
   retirait que 5 % du volume : `kotlin-spring-boot.md` porte 7 sections `##`
   pour 30 sous-sections `###`. La mesure a invalidé le choix de conception ;
   ce test empêche la régression.
3. **L'honnêteté de la comptabilité.** Le manifeste et les marqueurs de source
   font partie de ce que l'agent lit. Les exclure produirait un gain flatteur
   et une gate de budget fausse. Un pack peut légitimement GROSSIR.
4. **La stabilité du préfixe.** À contenu égal, un pack doit être
   byte-identique d'un spawn à l'autre — c'est le seul levier de cache dont le
   framework dispose sous Claude Code.
5. **L'auto-description.** L'agent doit savoir ce qu'il n'a pas vu.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sdd_lib import context_pack as cp
from sdd_lib.paths import repo_root

_STACK = """---
name: demo
---
# Stack Demo

Préambule porteur de l'identité.

## 1. Architecture

Couches applicatives.

### 1.3 Mapping couche → répertoire

Le mapping.

## 2. Stack

### 2.2.1 Init Commands

Les commandes d'init.

### 2.4 Librairies

Le catalogue.

## 3. Conventions d'usage

### 3.4 Formulaires

React Hook Form.

### 3.6 Hooks React

Usage standard.

## 11. Styling

Tailwind.

## 13. Performance

### 13.1 Waterfalls réseau (CRITIQUE)

Anti-pattern majeur.
"""


class TestSplitting(unittest.TestCase):
    def test_splits_at_h3_not_only_h2(self) -> None:
        titles = [s.title for s in cp.split_sections(_STACK)]
        self.assertIn("2. Stack", titles)
        self.assertIn("2.2.1 Init Commands", titles)
        self.assertIn("3.6 Hooks React", titles)

    def test_preamble_is_isolated_and_named(self) -> None:
        first = cp.split_sections(_STACK)[0]
        self.assertEqual(first.title, "__preamble__")
        self.assertIn("Préambule", first.body)

    def test_h3_carries_its_h2_parent(self) -> None:
        """Sans le parent, les 24 `###` de react.md seraient tous neutres."""
        by_title = {s.title: s for s in cp.split_sections(_STACK)}
        self.assertEqual(by_title["3.6 Hooks React"].parent, "3. Conventions d'usage")
        self.assertEqual(by_title["2. Stack"].parent, "")

    def test_real_stacks_have_more_h3_than_h2(self) -> None:
        """Justification mesurée du découpage au niveau `###`."""
        text = (repo_root() / ".sdd/stacks/backend/kotlin-spring-boot.md").read_text(
            encoding="utf-8")
        units = cp.split_sections(text)
        h2 = sum(1 for u in units if u.level == 2)
        h3 = sum(1 for u in units if u.level == 3)
        self.assertGreater(h3, h2, "le découpage `##` seul serait quasi inopérant")


class TestClassification(unittest.TestCase):
    def test_preamble_is_always_needed(self) -> None:
        for role in cp.ROLES:
            self.assertEqual(cp.classify(role, "__preamble__"), "needed")

    def test_author_marker_protects_for_every_role(self) -> None:
        """Une décision de packing ne doit pas écraser une décision d'auteur.
        Découvert en auditant les retraits réels : `arch` écartait
        « 2.6 Conventions REST API (load-bearing) » et
        « 13.1 Waterfalls réseau (CRITIQUE) »."""
        for title in ("13.1 Waterfalls réseau (CRITIQUE)",
                      "2.6 Conventions REST API (load-bearing — anti-divergence)",
                      "5. Setup obligatoire"):
            for role in cp.ROLES:
                self.assertEqual(cp.classify(role, title), "needed",
                                 f"{role} / {title}")

    def test_needed_wins_over_unneeded_at_the_same_level(self) -> None:
        """Cas réel : « 5. URLs / CORS / Multilingue / Logging / OpenAPI »
        est requis côté backend (url, cors) et inutile côté arch
        (multilingue). Une section fourre-tout se conserve."""
        title = "5. URLs / CORS / Multilingue / Logging / OpenAPI"
        self.assertEqual(cp.classify("backend", title), "needed")

    def test_own_title_beats_parent(self) -> None:
        self.assertEqual(
            cp.classify("arch", "2.2.1 Init Commands", "2. Stack"), "needed")

    def test_parent_decides_when_own_title_is_silent(self) -> None:
        self.assertEqual(
            cp.classify("arch", "3.6 Hooks React", "3. Conventions d'usage"),
            "unneeded")

    def test_accent_insensitive(self) -> None:
        self.assertEqual(cp.classify("backend", "11. Accessibilité et UX"),
                         cp.classify("backend", "11. Accessibilite et UX"))

    def test_unknown_agent_falls_back_to_conservative_role(self) -> None:
        self.assertEqual(cp.role_for_agent("some-new-agent"), "spec")
        self.assertEqual(cp.classify("spec", "11. Styling"), "neutral")


class TestSlicing(unittest.TestCase):
    def test_arch_drops_usage_conventions_keeps_init(self) -> None:
        text, man = cp.slice_markdown(_STACK, "arch")
        self.assertIn("Init Commands", text)
        self.assertNotIn("React Hook Form", text)
        self.assertIn("Le catalogue", text)

    def test_frontend_keeps_what_arch_drops(self) -> None:
        text, _ = cp.slice_markdown(_STACK, "frontend")
        self.assertIn("React Hook Form", text)
        self.assertIn("Tailwind", text)

    def test_author_protected_section_survives_every_role(self) -> None:
        for role in cp.ROLES:
            text, _ = cp.slice_markdown(_STACK, role)
            self.assertIn("Anti-pattern majeur", text, role)

    def test_manifest_declares_every_removal_with_a_reason(self) -> None:
        _, man = cp.slice_markdown(_STACK, "arch")
        self.assertTrue(man["sections_dropped"])
        for d in man["sections_dropped"]:
            self.assertTrue(d["reason"])
            self.assertGreater(d["bytes"], 0)

    def test_budget_pressure_drops_neutral_largest_first(self) -> None:
        """Maximiser l'économie par section sacrifiée minimise le nombre de
        sections sacrifiées."""
        big = _STACK + "\n## 20. Divers\n\n" + ("x" * 4000) + "\n"
        _, man = cp.slice_markdown(big, "spec", budget_bytes=1500)
        dropped = [d["title"] for d in man["sections_dropped"]]
        self.assertIn("20. Divers", dropped)

    def test_needed_sections_survive_even_over_budget(self) -> None:
        """Un pack hors budget est signalé, jamais amputé de l'essentiel."""
        _, man = cp.slice_markdown(_STACK, "arch", budget_bytes=10)
        self.assertTrue(man["over_budget"])
        dropped = {d["title"] for d in man["sections_dropped"]}
        self.assertNotIn("13.1 Waterfalls réseau (CRITIQUE)", dropped)


class TestPack(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        (self.root / ".sdd/stacks/frontend").mkdir(parents=True)
        (self.root / ".sdd/stacks/frontend/demo.md").write_text(_STACK, encoding="utf-8")
        (self.root / "us").mkdir()
        (self.root / "us/1-1-Login.md").write_text("# US-1\n## Styling\nne pas trancher",
                                                   encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _sources(self) -> list[cp.PackSource]:
        return [
            cp.PackSource(path="us/1-1-Login.md", stability="artifact", sliceable=False),
            cp.PackSource(path=".sdd/stacks/frontend/demo.md", stability="stack"),
        ]

    def test_sources_are_ordered_most_stable_first(self) -> None:
        """Le seul levier de cache disponible : un préfixe invariant."""
        _, man = cp.build_pack("arch", self._sources(), root=self.root)
        order = [s["path"] for s in man["sources"]]
        self.assertLess(order.index(".sdd/stacks/frontend/demo.md"),
                        order.index("us/1-1-Login.md"))

    def test_pack_is_byte_identical_across_builds(self) -> None:
        a, _ = cp.build_pack("arch", self._sources(), root=self.root)
        b, _ = cp.build_pack("arch", self._sources(), root=self.root)
        self.assertEqual(a, b)

    def test_non_sliceable_source_is_never_cut(self) -> None:
        """Trancher dans une US n'est pas du packing, c'est de la mutilation."""
        text, _ = cp.build_pack("arch", self._sources(), root=self.root)
        self.assertIn("ne pas trancher", text)

    def test_bytes_after_counts_the_manifest_itself(self) -> None:
        """Exclure l'entête donnerait un gain flatteur et une gate fausse."""
        text, man = cp.build_pack("arch", self._sources(), root=self.root)
        self.assertEqual(man["bytes_after"], len(text))

    def test_pack_may_legitimately_grow(self) -> None:
        """Quand rien n'est retirable, le manifeste coûte : `reduction_pct`
        doit pouvoir être négatif plutôt que de maquiller une perte en gain."""
        src = [cp.PackSource(path=".sdd/stacks/frontend/demo.md")]
        _, man = cp.build_pack("spec", src, root=self.root)
        self.assertLess(man["reduction_pct"], 0)

    def test_manifest_header_warns_the_agent_about_removals(self) -> None:
        """L'agent doit abaisser sa confiance en connaissance de cause plutôt
        que d'affirmer sur ce qu'il n'a pas lu."""
        text, _ = cp.build_pack("arch", self._sources(), root=self.root)
        self.assertIn("n'invente pas ce qui a été retiré", text)
        self.assertIn("Sections retirées", text)

    def test_missing_source_is_declared_not_swallowed(self) -> None:
        src = [cp.PackSource(path="absent/nowhere.md")]
        text, man = cp.build_pack("arch", src, root=self.root)
        self.assertEqual(man["missing_sources"], ["absent/nowhere.md"])
        self.assertIn("absentes du disque", text)

    def test_tight_budget_starves_no_source(self) -> None:
        """Le budget est réparti au prorata de la taille, pas premier arrivé
        premier servi — sinon la dernière source de la liste sortirait vide
        selon le seul ordre d'itération, et l'agent perdrait un stack entier
        sans que rien ne le distingue d'un stack absent."""
        big = _STACK + "\n## 30. Gros\n\n" + ("y" * 8000) + "\n"
        (self.root / ".sdd/stacks/frontend/big.md").write_text(big, encoding="utf-8")
        src = [cp.PackSource(path=".sdd/stacks/frontend/demo.md"),
               cp.PackSource(path=".sdd/stacks/frontend/big.md")]
        _, man = cp.build_pack("spec", src, budget_bytes=4000, root=self.root)
        after = {s["path"]: s["bytes_after"] for s in man["sources"]}
        self.assertEqual(len(after), 2)
        for path, size in after.items():
            self.assertGreater(size, 0, f"{path} affamée à zéro")

    def test_larger_source_receives_a_larger_share(self) -> None:
        """La part est proportionnelle : sous une pression de budget qui
        laisse de la marge, la grosse source conserve davantage que la
        petite au lieu d'être rabotée à égalité."""
        big = _STACK + "\n## 30. Gros\n\n" + ("y" * 8000) + "\n"
        (self.root / ".sdd/stacks/frontend/big.md").write_text(big, encoding="utf-8")
        src = [cp.PackSource(path=".sdd/stacks/frontend/demo.md"),
               cp.PackSource(path=".sdd/stacks/frontend/big.md")]
        _, man = cp.build_pack("spec", src, budget_bytes=20_000, root=self.root)
        after = {s["path"]: s["bytes_after"] for s in man["sources"]}
        self.assertGreater(after[".sdd/stacks/frontend/big.md"],
                           after[".sdd/stacks/frontend/demo.md"])


class TestRealStacksIntegration(unittest.TestCase):
    def test_arch_pack_fits_its_budget_on_the_real_repo(self) -> None:
        """Le correctif de P0-1 : `arch` dépassait son budget (188 034 o >
        180 000) sur un workspace vide, et la gate est bloquante."""
        from sdd_scripts.build_context_pack import build_for_agent
        from sdd_scripts.context_budget import DEFAULT_BUDGETS
        man = build_for_agent("arch", repo_root(), write=False)
        if man.get("error"):
            self.skipTest("stack.md absent — rien à packer")
        self.assertLess(man["bytes_after"], DEFAULT_BUDGETS["arch"],
                        "le pack arch doit tenir dans son budget")

    def test_no_author_protected_section_is_ever_dropped_on_real_stacks(self) -> None:
        """Le garde-fou vérifié sur le corpus réel, pas sur une fixture."""
        from sdd_scripts.build_context_pack import build_for_agent, PACKABLE_AGENTS
        markers = ("load-bearing", "critique", "obligatoire", "interdit")
        for agent in PACKABLE_AGENTS:
            man = build_for_agent(agent, repo_root(), write=False)
            if man.get("error"):
                continue
            for s in man["sources"]:
                for d in s["sections_dropped"]:
                    low = d["title"].lower()
                    self.assertFalse(
                        any(mk in low for mk in markers),
                        f"{agent} retire une section marquée auteur : {d['title']}")


if __name__ == "__main__":
    unittest.main()


class TestFingerprint(unittest.TestCase):
    """L'empreinte est la seule chose qui empêche un pack périmé de nourrir un
    agent en silence, une fois le pack substitué aux stacks dans loader.yml."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        (self.root / ".sdd/stacks/frontend").mkdir(parents=True)
        self.stack = self.root / ".sdd/stacks/frontend/demo.md"
        self.stack.write_text(_STACK, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _src(self):
        return [cp.PackSource(path=".sdd/stacks/frontend/demo.md")]

    def test_build_and_standalone_agree(self) -> None:
        """Deux définitions divergentes de l'empreinte rendraient tout pack
        éternellement « périmé ». Une seule fonction, un seul résultat."""
        _, man = cp.build_pack("arch", self._src(), root=self.root)
        self.assertEqual(man["sourcesFingerprint"],
                         cp.fingerprint_of(self._src(), root=self.root))

    def test_fingerprint_is_exposed_in_the_pack_header(self) -> None:
        text, man = cp.build_pack("arch", self._src(), root=self.root)
        self.assertIn(man["sourcesFingerprint"], text)

    def test_source_change_changes_the_fingerprint(self) -> None:
        before = cp.fingerprint_of(self._src(), root=self.root)
        self.stack.write_text(_STACK + "\n## 40. Nouveau\n\nx\n", encoding="utf-8")
        self.assertNotEqual(before, cp.fingerprint_of(self._src(), root=self.root))

    def test_missing_source_participates_in_the_fingerprint(self) -> None:
        """Sinon l'apparition d'un fichier annoncé mais absent passerait pour
        un jeu de sources inchangé."""
        base = self._src()
        absent = base + [cp.PackSource(path=".sdd/stacks/frontend/ghost.md")]
        self.assertNotEqual(cp.fingerprint_of(base, root=self.root),
                            cp.fingerprint_of(absent, root=self.root))

    def test_crlf_does_not_change_the_fingerprint(self) -> None:
        """Un clone Windows ne doit pas invalider tous les packs du dépôt."""
        lf = cp.fingerprint_of(self._src(), root=self.root)
        self.stack.write_bytes(_STACK.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(lf, cp.fingerprint_of(self._src(), root=self.root))


class TestPackLifecycleOnTheRealRepo(unittest.TestCase):
    """Le cycle complet tel qu'il tourne en pipeline : le hook construit, la
    gate mesure, et refuse ce qui est douteux."""

    def test_arch_pack_round_trips_and_is_fresh(self) -> None:
        from sdd_scripts.build_context_pack import (
            build_for_agent, manifest_path, pack_is_fresh, pack_path)
        from sdd_lib.paths import repo_root
        root = repo_root()
        man = build_for_agent("arch", root, write=True)
        if man.get("error"):
            self.skipTest("stack.md absent")
        self.assertTrue(pack_path("arch", root).is_file())
        self.assertTrue(manifest_path("arch", root).is_file())
        fresh, reason = pack_is_fresh("arch", root)
        self.assertTrue(fresh, reason)

    def test_pack_is_not_its_own_source(self) -> None:
        """Sinon l'empreinte changerait à chaque reconstruction et la gate
        crierait [PACK_UNUSABLE] sur un pack fraîchement écrit."""
        from sdd_scripts.build_context_pack import resolve_sources
        from sdd_lib.paths import repo_root
        sources, _ = resolve_sources("arch", repo_root())
        self.assertFalse(any("/.sys/.context/packs/" in s.path for s in sources))

    def test_deleting_the_pack_makes_it_unfresh(self) -> None:
        from sdd_scripts.build_context_pack import (
            build_for_agent, pack_is_fresh, pack_path)
        from sdd_lib.paths import repo_root
        root = repo_root()
        if build_for_agent("arch", root, write=True).get("error"):
            self.skipTest("stack.md absent")
        try:
            pack_path("arch", root).unlink()
            fresh, reason = pack_is_fresh("arch", root)
            self.assertFalse(fresh)
            self.assertIn("absent", reason)
        finally:
            build_for_agent("arch", root, write=True)

    def test_arch_gate_passes_with_the_pack(self) -> None:
        """Fermeture du P0-1, vérifiée sur le dépôt réel : la gate refusait
        arch (188 034 o > 180 000) sur un workspace vide."""
        import subprocess
        import sys as _sys
        from sdd_scripts.build_context_pack import build_for_agent
        from sdd_lib.paths import repo_root
        root = repo_root()
        if build_for_agent("arch", root, write=True).get("error"):
            self.skipTest("stack.md absent")
        r = subprocess.run(
            [_sys.executable, "-m", "sdd_scripts.context_budget",
             "--agent", "arch", "--feat-number", "1", "--json"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parent.parent))
        self.assertEqual(r.returncode, 0,
                         f"la gate arch doit passer avec le pack : {r.stdout} {r.stderr}")

    def test_gate_refuses_a_missing_pack_loudly(self) -> None:
        """La contrepartie de la bascule. Un pack absent pèse 0 octet : sans ce
        refus, il produirait un vert éclatant sur un agent privé de contexte."""
        import subprocess
        import sys as _sys
        from sdd_scripts.build_context_pack import build_for_agent, pack_path
        from sdd_lib.paths import repo_root
        root = repo_root()
        if build_for_agent("arch", root, write=True).get("error"):
            self.skipTest("stack.md absent")
        try:
            pack_path("arch", root).unlink()
            r = subprocess.run(
                [_sys.executable, "-m", "sdd_scripts.context_budget",
                 "--agent", "arch", "--feat-number", "1"],
                capture_output=True, text=True,
                cwd=str(Path(__file__).resolve().parent.parent))
            self.assertNotEqual(r.returncode, 0, "un pack absent doit faire échouer la gate")
            self.assertIn("PACK_UNUSABLE", r.stdout + r.stderr)
        finally:
            build_for_agent("arch", root, write=True)

    def test_hook_builds_the_pack_before_a_spawn(self) -> None:
        """Le producteur garanti : sans lui, la bascule du loader laisserait
        l'agent sans contexte de stack au premier run."""
        from sdd_hooks.preflight_agent_budget import _ensure_context_pack
        from sdd_scripts.build_context_pack import pack_is_fresh, pack_path
        from sdd_lib.paths import repo_root
        root = repo_root()
        pack_path("arch", root).unlink(missing_ok=True)
        self.assertFalse(pack_is_fresh("arch", root)[0])
        _ensure_context_pack("arch")
        fresh, reason = pack_is_fresh("arch", root)
        self.assertTrue(fresh, reason)

    def test_hook_is_a_noop_for_a_non_packable_agent(self) -> None:
        from sdd_hooks.preflight_agent_budget import _ensure_context_pack
        _ensure_context_pack("po")  # ne doit ni lever ni écrire
