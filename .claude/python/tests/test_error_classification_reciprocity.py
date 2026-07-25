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
_DECL_RE = re.compile(r"\[" + _CLASS + r"\]")

_TAXONOMY_FILES = (
    ".claude/rules/error-classification.md",
    ".claude/rules/error-classification-legacy.md",
    ".claude/rules/reverse-engineering.md",
)

_EMITTER_DIRS = (
    ".claude/python/sdd_scripts",
    ".claude/python/sdd_hooks",
    ".claude/python/sdd_lib",
    ".claude/python/sdd_admin",
    ".claude/python/sdd_reverse",
    ".claude/python/sdd_reverse_scripts",
)
_EMITTER_MD_DIRS = (".claude/agents", ".claude/commands")


def _declared_classes() -> set[str]:
    declared: set[str] = set()
    for rel in _TAXONOMY_FILES:
        p = _REPO_ROOT / rel
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
        for cls in _CAUSE_RE.findall(txt):
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
