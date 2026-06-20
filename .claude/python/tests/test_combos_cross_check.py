"""Cross-check tests for `.claude/templates/combos.json` SSoT.

v7.0.0-alpha (audit CRIT-6, 2026-06-04) — kills drift between :
  - `.claude/templates/combos.json`               (machine SSoT)
  - `.claude/stacks/{cat}/{stack-id}.md`          (human SSoT — `Validation:` header)
  - `sdd_scripts/match_stack_catalog.STACK_RULES` (brownfield discovery)

A test failure here means the framework's three views diverged ; the
**fix is always in `combos.json` + matching `.md` header**, never in
the test.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".claude" / "python"))

from sdd_lib.combos import (  # noqa: E402
    get_component_levels,
    get_validated_combos,
    load_combos,
)


_VALIDATION_HEADER_RE = re.compile(
    r"^\s*Validation:\s*([🟢🟡🔴])\s*([\w-]+)",
    re.MULTILINE,
)

# Sprint 2 closure (audit consolidé 2026-06-07) — mapping enrichi pour le
# tier `bench-validated` introduit par CRIT-11 (combos.json levelPriority).
# Le mot-clé après l'emoji est désormais load-bearing pour distinguer
# `🟢 reference` (validated) de `🟢 bench` (bench-validated).
_HEADER_TO_LEVEL = {
    ("🟢", "reference"):          "validated",
    ("🟢", "validated"):          "validated",
    ("🟢", "bench"):              "bench-validated",
    ("🟢", "bench-validated"):    "bench-validated",
    ("🟡", "experimental"):       "experimental",
    ("🟡", "scaffold-validated"): "scaffold-validated",
    ("🟡", "scaffold"):           "scaffold-validated",
    ("🟡", "POC"):                "poc-only",
    ("🟡", "poc-only"):           "poc-only",
    ("🔴", "untested"):           "untested",
}

# Fallback emoji-only (backward-compat — utilisé si le mot-clé n'est pas mappé)
_EMOJI_TO_LEVEL = {
    "🟢": "validated",
    "🟡": "experimental",
    "🔴": "untested",
}

# Stack categories where a 1:1 .md ↔ combos.json mapping is enforced.
# `db` and `archi` are config-level (not standalone `.claude/stacks/db/` dir
# in the framework today) — they're excluded from the .md cross-check.
_MD_BACKED_CATEGORIES = {"backend", "frontend", "ui", "qa", "auth"}


def _read_validation_header(stack_md: Path) -> str | None:
    """Return the level (validated/experimental/untested) declared in the
    `Validation: 🟢 ...` header of a stack .md, or None if absent/malformed.
    """
    try:
        text = stack_md.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _VALIDATION_HEADER_RE.search(text)
    if m is None:
        return None
    emoji = m.group(1)
    keyword = m.group(2)
    # Try the enriched (emoji, keyword) mapping first ; fall back to emoji-only.
    return _HEADER_TO_LEVEL.get((emoji, keyword)) or _EMOJI_TO_LEVEL.get(emoji)


class TestCombosJsonIntegrity(unittest.TestCase):
    """combos.json must be loadable and structurally sound."""

    def test_load_combos_succeeds(self):
        payload = load_combos()
        self.assertIn("combos", payload)
        self.assertIn("componentLevels", payload)
        self.assertIn("levelPriority", payload)
        self.assertGreaterEqual(payload.get("schemaVersion", 0), 1)

    def test_combos_have_required_fields(self):
        for combo in get_validated_combos():
            for field in ("id", "label", "backend", "frontend", "ui",
                          "qa", "auth", "db", "archi"):
                self.assertIn(field, combo, f"combo {combo.get('id')} missing {field}")
            self.assertIsInstance(combo["qa"], list,
                                  f"combo {combo['id']} qa must be a JSON array")

    def test_combo_components_exist_in_levels(self):
        """Every stack referenced by a combo must be declared in componentLevels."""
        levels = get_component_levels()
        for combo in get_validated_combos():
            for category, key in (("backend", "backend"), ("frontend", "frontend"),
                                  ("ui", "ui"), ("auth", "auth"),
                                  ("db", "db"), ("archi", "archi")):
                value = combo[key]
                self.assertIn(
                    value, levels.get(category, {}),
                    f"combo {combo['id']} references {category}={value!r} "
                    f"not in componentLevels.{category}",
                )
            for qa_id in combo["qa"]:
                self.assertIn(
                    qa_id, levels.get("qa", {}),
                    f"combo {combo['id']} references qa={qa_id!r} "
                    f"not in componentLevels.qa",
                )


class TestStackMdCrossCheck(unittest.TestCase):
    """For each category declared in combos.json, each stack_id MUST :
      (a) have a matching `.claude/stacks/{cat}/{stack_id}.md` file ;
      (b) declare the same validation level in its `Validation:` header.

    **Drift résolu 2026-06-06 (security audit)** : les 3 drifts hérités
    (blazor-webassembly, radzen-blazor, blazor-bunit) + 4 drifts bench-validated
    (python-fastapi, node-express, vue, angular) sont désormais alignés en
    combos.json sur la réalité 🟢 des .md headers. `_KNOWN_DRIFT` est vide —
    toute future divergence est une régression à corriger, pas à accepter.
    """

    # stack_id -> (combos.json level, .md header level)
    _KNOWN_DRIFT: dict[str, tuple[str, str]] = {}

    def test_componentlevels_match_md_headers(self):
        levels = get_component_levels()
        unexpected_drifts: list[str] = []
        for category, stacks in levels.items():
            if category not in _MD_BACKED_CATEGORIES:
                continue
            stacks_dir = REPO_ROOT / ".claude" / "stacks" / category
            if not stacks_dir.is_dir():
                unexpected_drifts.append(
                    f"stacks dir missing for category {category!r}: {stacks_dir}")
                continue
            for stack_id, declared_level in stacks.items():
                md_file = stacks_dir / f"{stack_id}.md"
                if not md_file.is_file():
                    unexpected_drifts.append(
                        f"componentLevels.{category}.{stack_id} declared "
                        f"but {md_file.relative_to(REPO_ROOT)} missing"
                    )
                    continue
                md_level = _read_validation_header(md_file)
                if md_level is None:
                    unexpected_drifts.append(
                        f"{md_file.relative_to(REPO_ROOT)} has no parseable "
                        f"`Validation:` header"
                    )
                    continue
                if md_level == declared_level:
                    continue
                # Cross-check against known pre-existing drift.
                expected = self._KNOWN_DRIFT.get(stack_id)
                if expected == (declared_level, md_level):
                    continue  # known, documented — pass.
                unexpected_drifts.append(
                    f"DRIFT {category}.{stack_id} : combos.json says "
                    f"{declared_level!r}, .md header says {md_level!r}"
                )
        self.assertFalse(
            unexpected_drifts,
            "Unexpected drift between combos.json and stack .md headers "
            "(known drifts are tracked in TestStackMdCrossCheck._KNOWN_DRIFT):\n  - "
            + "\n  - ".join(unexpected_drifts),
        )


class TestStackRulesCrossCheck(unittest.TestCase):
    """Every stack_id in `match_stack_catalog.STACK_RULES` MUST be
    declared in `combos.json::componentLevels[category]`. Otherwise
    brownfield discovery emits a `validation_level` of 'untested'
    (fallback) when the stack is actually 🟢/🟡 elsewhere.
    """

    def test_stackrules_keys_in_componentlevels(self):
        # Import lazily to avoid circular setup during test discovery.
        from sdd_scripts.match_stack_catalog import STACK_RULES  # noqa: E402
        levels = get_component_levels()
        missing: list[str] = []
        for stack_id, rules in STACK_RULES.items():
            cat = rules["category"]
            if stack_id not in levels.get(cat, {}):
                missing.append(f"STACK_RULES.{stack_id} (category={cat}) "
                               f"not in componentLevels.{cat}")
        self.assertFalse(missing, "STACK_RULES ↔ combos.json drift:\n  - "
                         + "\n  - ".join(missing))


if __name__ == "__main__":
    unittest.main()
