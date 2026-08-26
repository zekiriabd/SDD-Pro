"""Parité des consommateurs de `stack.md` sur la bi-racine (audit 2026-08-25).

Post-mortem : la migration `.claude/` → `.sdd/` avait été appliquée par
substitution littérale, y compris dans les regex qui parsent le `stack.md`
d'un **projet**. Résultat : `sdd_full_planner` (qui passait par le SSoT
`project_config`, bi-racine tolérant) voyait 8 stacks actifs pendant que
`phase_planner`, `preflight`, `validate_readiness` et `validate_stack_combo`
(regex locales `.sdd`-only) en voyaient zéro — `/dev-run` bloqué,
`/feat-validate` NO-GO, sur un `stack.md` parfaitement valide.

Le `stack.md` est un artefact **projet** : il peut légitimement être resté
sur la racine legacy. Ces tests verrouillent l'invariant : *tous* les
consommateurs doivent lire le même ensemble de stacks actifs, quelle que
soit la racine déclarée, et exposer le résultat canonicalisé sur `.sdd/`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PYTHON_ROOT = _HERE.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

from sdd_lib.project_config import (  # noqa: E402
    CANONICAL_STACK_ROOT,
    normalize_stack_path,
    parse_active_stack_ids,
    stack_path_re,
)
from sdd_scripts import preflight, validate_readiness, validate_stack_combo  # noqa: E402
from sdd_scripts import phase_planner  # noqa: E402

_LEGACY_ROOT = ".claude"

_STACK_MD_TMPL = """# Stack

## Active Architecture Pattern
  - {root}/stacks/archi/mvc.md
# - {root}/stacks/archi/ddd.md

## Active Tech Specs
 - {root}/stacks/frontend/react.md
 - {root}/stacks/backend/kotlin-spring-boot.md

## Active UI Specs
 - {root}/stacks/ui/shadcn.md

## Active QA Specs
 - {root}/stacks/qa/node-vitest.md
 - {root}/stacks/qa/kotlin-junit.md

## Active Auth Specs
 - {root}/stacks/auth/azure-ad.md
 - AZ_TENANTID: tid
"""


def _stack_md(root: str) -> str:
    return _STACK_MD_TMPL.format(root=root)


_ROOTS = (CANONICAL_STACK_ROOT, _LEGACY_ROOT)


class TestStackPathSSoT(unittest.TestCase):
    def test_parse_is_root_agnostic(self) -> None:
        parsed = [parse_active_stack_ids(_stack_md(r)) for r in _ROOTS]
        self.assertEqual(parsed[0], parsed[1])
        self.assertEqual(parsed[0]["backend"], ["kotlin-spring-boot"])
        self.assertEqual(parsed[0]["qa"], ["node-vitest", "kotlin-junit"])

    def test_commented_stack_is_inactive(self) -> None:
        for root in _ROOTS:
            with self.subTest(root=root):
                self.assertEqual(parse_active_stack_ids(_stack_md(root))["archi"], ["mvc"])

    def test_first_only_keeps_one_per_category(self) -> None:
        parsed = parse_active_stack_ids(_stack_md(_LEGACY_ROOT), first_only=True)
        self.assertEqual(parsed["qa"], ["node-vitest"])

    def test_normalize_rewrites_legacy_root(self) -> None:
        self.assertEqual(
            normalize_stack_path(f"{_LEGACY_ROOT}/stacks/backend/x.md"),
            f"{CANONICAL_STACK_ROOT}/stacks/backend/x.md",
        )
        # Idempotent + non-stack paths untouched.
        canonical = f"{CANONICAL_STACK_ROOT}/stacks/backend/x.md"
        self.assertEqual(normalize_stack_path(canonical), canonical)
        self.assertEqual(normalize_stack_path("workspace/us/1-1-X.md"), "workspace/us/1-1-X.md")

    def test_anchored_pattern_rejects_prose(self) -> None:
        pattern = stack_path_re("backend")
        self.assertIsNone(pattern.match("voir .sdd/stacks/backend/x.md pour le détail"))
        self.assertIsNotNone(pattern.match(" - .sdd/stacks/backend/x.md"))


class TestConsumerParity(unittest.TestCase):
    """Chaque consommateur doit rendre le même verdict sur les deux racines."""

    def test_phase_planner_active_stacks(self) -> None:
        results = []
        for root in _ROOTS:
            text = _stack_md(root)
            parsed = parse_active_stack_ids(text, first_only=True)
            results.append({k: (parsed.get(k) or [None])[0]
                            for k in ("backend", "frontend", "ui", "auth", "fullstack", "mobiles")})
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["backend"], "kotlin-spring-boot")
        self.assertIsNone(results[0]["fullstack"])

    def test_preflight_get_active_ids(self) -> None:
        ids = [preflight.get_active_ids(_stack_md(r), "backend") for r in _ROOTS]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(ids[0], ["kotlin-spring-boot"])

    def test_validate_stack_combo_parse(self) -> None:
        from sdd_lib.markdown_io import section_body
        for category, expected in (("backend", ["kotlin-spring-boot"]),
                                   ("qa", ["node-vitest", "kotlin-junit"])):
            heading = "Active Tech Specs" if category == "backend" else "Active QA Specs"
            ids = [
                validate_stack_combo._parse_active_stacks(
                    section_body(_stack_md(r), heading), category)
                for r in _ROOTS
            ]
            with self.subTest(category=category):
                self.assertEqual(ids[0], ids[1])
                self.assertEqual(ids[0], expected)

    def test_validate_readiness_auth_detection(self) -> None:
        for root in _ROOTS:
            with self.subTest(root=root):
                text = _stack_md(root)
                self.assertTrue(validate_readiness.has_auth_stack_listed(text))
                # Toujours canonicalisé : la valeur sert à ouvrir le fichier
                # sur disque, et seul `.sdd/stacks/` y existe.
                self.assertEqual(
                    validate_readiness.detect_active_auth_stack(text),
                    f"{CANONICAL_STACK_ROOT}/stacks/auth/azure-ad.md",
                )


class TestNoLocalStackRegex(unittest.TestCase):
    """Grep-gate : aucun consommateur ne ré-implémente le pattern localement.

    Seul `sdd_lib/project_config.py` a le droit de porter le littéral
    `<root>/stacks/` dans une expression régulière. Toute nouvelle regex
    locale rouvrirait la divergence corrigée le 2026-08-25.
    """

    _ALLOWED = frozenset({"sdd_lib/project_config.py"})

    # Le tell d'une regex : le point de `.sdd` / `.claude` y est échappé.
    # Construit sans littéral backslash pour rester lisible.
    _ESCAPED_ROOTS = tuple(
        chr(92) + "." + root + "/stacks/" for root in ("sdd", "claude")
    )
    _RE_CALLS = ("re.compile(", "re.match(", "re.search(",
                 "re.finditer(", "re.fullmatch(")

    @classmethod
    def _is_local_stack_regex(cls, line: str) -> bool:
        # (a) motif régulier échappé, y compris sur une ligne de continuation
        #     d'un `re.compile(` multi-lignes ;
        if any(needle in line for needle in cls._ESCAPED_ROOTS):
            return True
        # (b) appel `re.*` inline dont le motif porte une racine littérale.
        #     Une racine dérivée de `CANONICAL_STACK_ROOT` est légitime :
        #     elle suit le SSoT par construction.
        if not any(call in line for call in cls._RE_CALLS):
            return False
        return any(f"{root}/stacks/" in line for root in (".sdd", ".claude"))

    def test_no_regex_hardcodes_stack_root(self) -> None:
        py_root = _PYTHON_ROOT
        offenders: list[str] = []
        for py in py_root.rglob("*.py"):
            rel = py.relative_to(py_root).as_posix()
            if rel in self._ALLOWED or rel.startswith("tests/") or "__pycache__" in rel:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if self._is_local_stack_regex(line):
                    offenders.append(f"{rel}:{i}  {line.strip()}")
        self.assertFalse(offenders, (
            "Regex locale sur les chemins de stacks détectée. Importer le SSoT "
            "bi-racine `sdd_lib.project_config.stack_path_re` / "
            "`parse_active_stack_ids` au lieu de recompiler le motif.\n\n"
            + "\n".join(offenders)
        ))

    def test_gate_detects_the_2026_08_25_offenders(self) -> None:
        """Le gate doit re-flaguer les motifs exacts corrigés ce jour-là."""
        historical = [
            '_ACTIVE_STACK_RE = re.compile(r"^' + chr(92) + 's*-' + chr(92)
            + r's*\.sdd/stacks/([^/]+)/([^/\s]+)\.md\s*$")',
            r'        r"\.sdd/stacks/(backend|frontend|ui|auth)/([\w-]+)\.md",',
            r'    return re.compile(rf"\.sdd/stacks/{re.escape(category)}/([\w-]+)\.md")',
            r'    m = re.search(r"(?m)^\s*-\s+(\.sdd/stacks/auth/[\w\-]+\.md)\s*$", body)',
        ]
        for line in historical:
            with self.subTest(line=line[:48]):
                self.assertTrue(self._is_local_stack_regex(line))

    def test_gate_ignores_plain_path_literals(self) -> None:
        """Un chemin nu (manifest, tuple de protection) n'est pas une regex."""
        for line in (
            '        {"path": ".sdd/stacks/backend/{active}.md", "cache_layer": "stable"},',
            '    ".sdd/stacks/",',
            '    Path(".sdd/stacks"),',
        ):
            with self.subTest(line=line.strip()[:48]):
                self.assertFalse(self._is_local_stack_regex(line))


if __name__ == "__main__":
    unittest.main()
