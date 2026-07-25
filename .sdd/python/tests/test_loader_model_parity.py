"""Parité tier loader.yml ↔ frontmatter agents (post-Batch C 2026-07-25).

Post-migration : `.sdd/loader.yml` + `.sdd/agents/*.md` déclarent tous les
deux `model_tier: deep|balanced|fast` (neutral, provider-agnostic). Le
mapping tier -> ID modèle concret est résolu par `sdd_lib.model_resolver`
via `.sdd/providers/{p}.yaml`.

Ce test enforce :
  1. chaque entrée agent de loader.yml porte un champ `model_tier:` ;
  2. sa valeur matche le `model_tier:` du frontmatter de
     `.sdd/agents/{agent}.md` (SSoT pivot neutre) ;
  3. symétriquement pour loader.reverse.yml ↔ agents/reverse-*.md.

Historique : le test comparait auparavant `model: claude-opus-4-8` avec
`model:` du frontmatter — pré-migration. Post-Batch C, l'invariant est
sur le TIER (neutre) plutôt que sur l'ID modèle concret (résolu par
provider). Cf. `.sdd/providers/*.yaml` pour la résolution finale.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

# Bi-racine 2026-07-25 (Phase 1) : python migré vers .sdd/python/, mais
# loader.yml + agents/*.md restent encore sous .claude/ (façade active).
# Le loader.yml opérationnel (avec `model:` en clair) est `.sdd/loader.yml` (post-Batch C 2026-07-25)
# ; `.sdd/loader.yml` est un pivot Phase 1 avec `model_tier:` (généré).
_REPO_ROOT = _PY_ROOT.parent.parent  # <repo>/ (parent of .sdd)
_CLAUDE_DIR = _REPO_ROOT / ".sdd"
_AGENTS_DIR = _CLAUDE_DIR / "agents"

# Entrées top-level de loader.yml qui ne sont pas des agents.
_NON_AGENT_KEYS = {"version", "updated"}

_TOP_KEY_RE = re.compile(r"^([a-z][a-z0-9-]*):\s*$", re.MULTILINE)
# Post-Batch C 2026-07-25 : loader.yml + agents/*.md portent `model_tier:`.
# La regex tolère aussi `model:` pour rétrocompat historique (façades .claude/).
_MODEL_LINE_RE = re.compile(r"^\s{2}model_tier:\s*(\S+)", re.MULTILINE)
_FRONTMATTER_MODEL_RE = re.compile(r"^model_tier:\s*(\S+)", re.MULTILINE)


def _loader_agent_models(loader_path: Path) -> dict[str, str | None]:
    """Map agent_key -> model déclaré dans le loader (None si absent).

    Parser ligne-à-ligne délibéré (pas de yaml.safe_load) : les loaders
    portent des templates `{n}-*` et des commentaires riches — on ne veut
    valider que le couple (clé top-level, premier `model:` du bloc).
    """
    text = loader_path.read_text(encoding="utf-8")
    keys = [(m.group(1), m.start()) for m in _TOP_KEY_RE.finditer(text)]
    out: dict[str, str | None] = {}
    for i, (key, start) in enumerate(keys):
        if key in _NON_AGENT_KEYS:
            continue
        end = keys[i + 1][1] if i + 1 < len(keys) else len(text)
        block = text[start:end]
        m = _MODEL_LINE_RE.search(block)
        out[key] = m.group(1).strip() if m else None
    return out


def _frontmatter_model(agent_md: Path) -> str | None:
    head = agent_md.read_text(encoding="utf-8")[:2000]
    m = _FRONTMATTER_MODEL_RE.search(head)
    return m.group(1).strip() if m else None


class TestForwardLoaderModelParity(unittest.TestCase):
    def setUp(self):
        self.models = _loader_agent_models(_CLAUDE_DIR / "loader.yml")

    def test_every_agent_entry_declares_model(self):
        missing = [a for a, m in self.models.items() if m is None]
        self.assertEqual(missing, [],
                         msg=f"entrées loader.yml sans champ model: {missing}")

    def test_loader_model_matches_agent_frontmatter(self):
        mismatches = []
        for agent, loader_model in self.models.items():
            md = _AGENTS_DIR / f"{agent}.md"
            self.assertTrue(md.is_file(), msg=f"agent .md manquant pour l'entrée loader '{agent}'")
            fm_model = _frontmatter_model(md)
            if fm_model is None:
                mismatches.append(f"{agent}: frontmatter sans model:")
            elif fm_model != loader_model:
                mismatches.append(f"{agent}: loader={loader_model} != frontmatter={fm_model}")
        self.assertEqual(mismatches, [], msg="; ".join(mismatches))

    def test_forward_roster_is_complete(self):
        """Les 12 agents pipeline + l'agent auxiliaire specbook-writer (2026-07-24)
        ont une entrée loader.yml. specbook-writer humanise le Cahier des charges ;
        il est spawnable (donc dans loader pour l'audit budget) mais hors des 12
        agents du pipeline /sdd-full — d'où sa mention distincte ici."""
        expected = {
            "po", "arch", "dev-backend", "dev-frontend", "qa", "elicitor",
            "constitutioner", "code-reviewer", "security-reviewer",
            "spec-compliance-reviewer", "arch-reviewer", "adversarial-reviewer",
            "specbook-writer",
        }
        self.assertEqual(set(self.models), expected)


class TestReverseLoaderModelParity(unittest.TestCase):
    def test_reverse_loader_matches_frontmatters(self):
        # loader.reverse.yml est du YAML standard avec un bloc `agents:` —
        # contrairement à loader.yml (entrées top-level + templates {n}-*).
        import yaml

        doc = yaml.safe_load(
            (_CLAUDE_DIR / "loader.reverse.yml").read_text(encoding="utf-8")
        )
        entries = doc.get("agents") or {}
        agents = {
            a: (spec or {}).get("model_tier") or (spec or {}).get("model")
            for a, spec in entries.items()
            if a.startswith("reverse-")
        }
        self.assertGreaterEqual(len(agents), 7, msg=f"roster reverse incomplet: {sorted(agents)}")
        mismatches = []
        for agent, loader_tier in agents.items():
            md = _AGENTS_DIR / f"{agent}.md"
            if not md.is_file():
                mismatches.append(f"{agent}: .md manquant")
                continue
            fm_tier = _frontmatter_model(md)
            if loader_tier is None:
                mismatches.append(f"{agent}: pas de model_tier: dans loader.reverse.yml")
            elif fm_tier != loader_tier:
                mismatches.append(f"{agent}: loader={loader_tier} != frontmatter={fm_tier}")
        self.assertEqual(mismatches, [], msg="; ".join(mismatches))


if __name__ == "__main__":
    unittest.main()
