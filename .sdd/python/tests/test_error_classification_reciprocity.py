"""Reciprocity gate: every error class EMITTED must be DECLARED in the taxonomy.

Audit 2026-06-12 (block 3) — the forward taxonomy had ~14 classes emitted in
the canonical `CAUSE: [CLASS]` format by scripts/hooks/prompts but absent from
`error-classification.md` (the SSoT). `build_loop`/hooks/dashboards would treat
them as `[UNKNOWN]`, and the headline "classes" count was wrong by
under-declaration. The reverse module already enforces this reciprocity
(`reverse-engineering.md §6.3`: "aucune classe sans émetteur"); this test gives
the FORWARD side the symmetric guard — but in the other direction: no emitter
without a declaration.

Scope = the canonical machine contract only: a class written on a `CAUSE:`
line (error-classification.md §2). The `[BRACKET]` convention is overloaded
(chat labels in output-protocol, hook stderr diagnostic tags, doc sub-case
markers); restricting to `CAUSE: [X]` isolates the subset that `build_loop`
and the audit log actually consume, with zero false positives.

Extension audit M6 2026-08-30 : le scan couvre aussi (a) le format VERDICT
`🔴 RED [X]` (gates two-stage — avait raté [AUDITOR_RUNTIME_ERROR]),
(b) les codes JSON structurés `"code": "X"` des scripts Python (avait raté
[PACK_UNUSABLE]), et (c) le foyer neutre `.sdd/{agents,commands,rules}` en
plus des façades `.claude/`. Les sous-codes JSON internes connus sont
ratchetés dans `_KNOWN_JSON_SUBCODES`.

If this test fails: a `CAUSE: [NEW_CLASS]` was added without declaring it.
Per the framework's own rule ("ajouter la classe ICI d'abord"), add a row to
the matching `error-classification.md §1.X` table (and bump the §0 counts —
`test_error_classification_count.py` enforces those), THEN wire the emitter.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

_PY_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PY_ROOT.parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

_CLASS = r"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"
_CAUSE_RE = re.compile(r"CAUSE:\s*\[" + _CLASS + r"\]")
# Extension audit M6 2026-08-30 : les gates two-stage émettent leur classe en
# format VERDICT (`🔴 RED [AUDITOR_RUNTIME_ERROR]`), pas en `CAUSE: [X]` — le
# scan CAUSE-only avait raté [AUDITOR_RUNTIME_ERROR] et [PACK_UNUSABLE].
_VERDICT_RE = re.compile(r"🔴\s*RED\s*\[" + _CLASS + r"\]")
# Codes émis par les scripts en JSON structuré (`"code": "X"`) — même contrat
# machine que CAUSE:, autre canal (ex. context_budget.py → [PACK_UNUSABLE]).
_JSON_CODE_RE = re.compile(r"\"code\":\s*\"" + _CLASS + r"\"")
_DECL_RE = re.compile(r"\[" + _CLASS + r"\]")

# Bi-racine 2026-07-25 : rules déplacées sous `.sdd/rules/` (Phase 1).
# Les noms de fichier restent les mêmes ; on utilise `rules_dir()` pour
# résoudre la racine.
from sdd_lib.paths import rules_dir  # noqa: E402
_TAXONOMY_FILES = (
    "error-classification.md",
    "error-classification-legacy.md",
    "reverse-engineering.md",
)

_EMITTER_DIRS = (
    ".sdd/python/sdd_scripts",
    ".sdd/python/sdd_hooks",
    ".sdd/python/sdd_lib",
    ".sdd/python/sdd_admin",
    ".sdd/python/sdd_reverse",
    ".sdd/python/sdd_reverse_scripts",
)
_EMITTER_MD_DIRS = (
    ".claude/agents",
    ".claude/commands",
    # Extension audit M6 2026-08-30 — le foyer neutre est le SSoT (les façades
    # .claude/.codex/.gemini en sont régénérées) et les RULES émettent aussi
    # des classes (gate two-stage dans auditor-orchestration.md).
    ".sdd/agents",
    ".sdd/commands",
    ".sdd/rules",
)

# Faux positifs connus du scan étendu (exemples pédagogiques, placeholders de
# format, jamais des émissions réelles). Y ajouter une entrée exige de
# vérifier que le `[X]` matché n'est PAS une classe réellement émise.
_SCAN_EXCLUSIONS: set[str] = set()

# Ratchet (audit M6 2026-08-30) — sous-codes internes émis en JSON structuré
# (`"code": "X"`) par des scripts mono-shot, comme DÉTAIL de champ dans leur
# payload : ils ne sont PAS des classes `[CLASS]` au sens du contrat
# error-classification.md §2 (jamais rendus en `CAUSE: [X]`, jamais consommés
# par build_loop). Suivis ici pour que tout NOUVEAU code JSON non déclaré
# fasse échouer le test ([PACK_UNUSABLE], même canal, EST déclaré §1.14).
# Retirer une entrée le jour où le code est promu en classe taxonomie.
_KNOWN_JSON_SUBCODES: frozenset[str] = frozenset({
    # validate_project_config.py — validation par clé du ## Project Config
    "TYPE_MISMATCH", "ENUM_VIOLATION", "BELOW_MINIMUM", "ABOVE_MAXIMUM",
    "UNKNOWN_KEY",
    # context_budget.py — détail de la gate de budget (l'agrégat visible est
    # l'exit code de la gate ; PACK_UNUSABLE, lui, est déclaré)
    "BUDGET_EXCEEDED", "UNBOUNDED_GLOB", "READ_MISSING", "PACK_PROJECTION",
    # preflight.py — variantes WARN-only du mode :plan
    "PROJECT_NOT_INIT_WARN", "STACK_DIGEST_MISSING_WARN",
    # sdd_full_planner.py — erreur de parse Project Config remontée au planner
    "PROJECT_CONFIG_INVALID",
})


def _declared_classes() -> set[str]:
    declared: set[str] = set()
    _rules = rules_dir(_REPO_ROOT)
    for filename in _TAXONOMY_FILES:
        p = _rules / filename
        if p.is_file():
            declared |= set(_DECL_RE.findall(p.read_text(encoding="utf-8")))
    return declared


def _emitted_classes() -> dict[str, set[str]]:
    emitted: dict[str, set[str]] = {}
    files: list[Path] = []
    for d in _EMITTER_DIRS:
        files += list((_REPO_ROOT / d).rglob("*.py"))
    for d in _EMITTER_MD_DIRS:
        files += list((_REPO_ROOT / d).glob("*.md"))
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8")
        except OSError:
            continue
        found: set[str] = set(_CAUSE_RE.findall(txt))
        found |= set(_VERDICT_RE.findall(txt))
        if f.suffix == ".py":
            found |= set(_JSON_CODE_RE.findall(txt)) - _KNOWN_JSON_SUBCODES
        for cls in found - _SCAN_EXCLUSIONS:
            emitted.setdefault(cls, set()).add(f.name)
    return emitted


def test_every_cause_emitted_class_is_declared():
    declared = _declared_classes()
    emitted = _emitted_classes()
    orphans = {c: sorted(fs) for c, fs in emitted.items() if c not in declared}
    assert not orphans, (
        "Error classes emitted in `CAUSE: [CLASS]` but ABSENT from the taxonomy "
        "(error-classification.md / -legacy.md / reverse-engineering.md). Declare "
        "each before wiring its emitter:\n"
        + "\n".join(f"  [{c}] <- {fs}" for c, fs in sorted(orphans.items()))
    )


def test_emitted_set_is_non_trivial():
    """Guard against a regex/path regression silently emptying the scan."""
    assert len(_emitted_classes()) >= 20, (
        "CAUSE-scan found suspiciously few classes — regex or emitter dirs broke"
    )
