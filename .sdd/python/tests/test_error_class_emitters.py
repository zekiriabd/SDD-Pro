"""Reciprocity, other direction: every DECLARED class should have an EMITTER.

Audit M2 (2026-08-29). `test_error_classification_reciprocity.py` guards
"emitted ⇒ declared". Nothing guarded "declared ⇒ emitted", and the audit
found a family of classes that exist only on paper — most of the §1.5
*anti-derive* family among them. A taxonomy row with no emitter reads, to
anyone browsing `error-classification.md`, as an automatic guard that does
not exist.

What counts as an emitter
-------------------------
Deliberately broad: the class token appearing anywhere under
`.sdd/python/**` (`.py` / `.yaml` / `.json`, tests excluded),
`.sdd/agents/*.md` or `.sdd/commands/*.md`. A class can legitimately be
emitted through a YAML pattern id (`security_patterns.yaml`), a Python
constant (`set_us_status.py`), or a prompt instruction — not just a literal
`CAUSE: [X]` line. Narrowing to `CAUSE:` would report ~114 false positives.

Why an allowlist rather than a red test
---------------------------------------
Building deterministic detectors for the orphan classes is product work with
real false-positive risk (see the §1.5 note in `error-classification.md`), so
this pass does not attempt it. The allowlist is a **ratchet**: it may only
shrink. A newly declared class with no emitter fails immediately, and an
orphan that gains an emitter must be removed from the list. The gap stays
visible in code and in the taxonomy doc, instead of being quietly implied
away.
"""
from __future__ import annotations

import re
from pathlib import Path

SDD_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = SDD_ROOT / "rules" / "error-classification.md"

_CLASS_TOKEN = r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+"
_DECL_RE = re.compile(r"\[(" + _CLASS_TOKEN + r")\]")
_TOKEN_RE = re.compile(r"\b" + _CLASS_TOKEN + r"\b")

_EMITTER_PY_SUFFIXES = frozenset({".py", ".yaml", ".yml", ".json"})
_EMITTER_MD_DIRS = ("agents", "commands")

#: Classes declared in the taxonomy with no emitter anywhere in the codebase.
#:
#: RATCHET — this set may only SHRINK. Frozen 2026-08-29 (audit M2).
#: The §1.5 *anti-derive* cluster (DERIVE_VIOLATION, REFACTOR_HORS_SCOPE,
#: OPTIMIZATION_PROACTIVE, UNDECLARED_DECISION) is LLM-discretion only — it is
#: enforced by agent judgement in the prompts, never by a deterministic
#: detector. That is now stated in `error-classification.md §1.5` so the doc
#: stops implying automatic enforcement it does not have.
KNOWN_UNEMITTED: frozenset[str] = frozenset({
    # §1.5 anti-derive — LLM-discretion only, no deterministic detector
    "DERIVE_VIOLATION",
    "REFACTOR_HORS_SCOPE",
    "OPTIMIZATION_PROACTIVE",
    "UNDECLARED_DECISION",
    "STACK_RUNTIME_NOT_LTS",
    "RUNTIME_STS_EXCEPTION",
    # contract / build classes documented but never emitted
    # (CIRCULAR_DEP retiré du ratchet 2026-08-30 — désormais référencé par les
    #  prompts dev-backend.md/dev-frontend.md §build_loop, émission LLM-side)
    "BREAKING_CLEANUP_FAILED",
    "ENV_PROPAGATION_FAILED",
    "LIBNAME_SIGNATURE_CONFLICT",
    "STACK_SCAFFOLDING_MISSING",
    # tooling / review classes documented but never emitted
    "DISCOVER_STACK_EXISTS",
    "REVIEW_DB_UNREACHABLE",
    "REVIEW_SCAN_FAILED",
    # deprecated v7.0.0 (*-strict removal) — kept for legacy console.db reads
    "PLAN_DIGEST_INSUFFICIENT",
})


def _declared_classes() -> set[str]:
    return set(_DECL_RE.findall(TAXONOMY.read_text(encoding="utf-8")))


def _emitter_tokens() -> set[str]:
    tokens: set[str] = set()
    py_root = SDD_ROOT / "python"
    if py_root.is_dir():
        for path in py_root.rglob("*"):
            if path.suffix not in _EMITTER_PY_SUFFIXES:
                continue
            parts = path.parts
            if "__pycache__" in parts or "tests" in parts:
                continue
            try:
                tokens |= set(_TOKEN_RE.findall(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    for dirname in _EMITTER_MD_DIRS:
        d = SDD_ROOT / dirname
        if not d.is_dir():
            continue
        for md in d.glob("*.md"):
            try:
                tokens |= set(_TOKEN_RE.findall(md.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    return tokens


def _orphans() -> set[str]:
    return _declared_classes() - _emitter_tokens()


def test_no_new_declared_class_without_emitter():
    unexpected = sorted(_orphans() - KNOWN_UNEMITTED)
    assert not unexpected, (
        "Class(es) declared in error-classification.md with NO emitter "
        "anywhere in .sdd/python, .sdd/agents or .sdd/commands. A taxonomy "
        "row with no emitter advertises enforcement that does not exist — "
        "either wire the emitter, or document the class as discretionary:\n  "
        + "\n  ".join(unexpected)
    )


def test_unemitted_allowlist_does_not_rot():
    """An orphan that gained an emitter must leave the allowlist."""
    stale = sorted(KNOWN_UNEMITTED - _orphans())
    assert not stale, (
        "KNOWN_UNEMITTED lists class(es) that now HAVE an emitter. Remove "
        "them so the ratchet keeps its teeth:\n  " + "\n  ".join(stale)
    )


def test_declared_set_is_non_trivial():
    """Guard against a path/regex regression silently emptying the scan."""
    assert len(_declared_classes()) >= 100
    assert len(_emitter_tokens()) >= 100


def test_anti_derive_family_is_documented_as_discretionary():
    """§1.5 must say plainly that it has no deterministic emitter (audit M2)."""
    text = TAXONOMY.read_text(encoding="utf-8")
    idx = text.find("### 1.5 Anti-derive")
    assert idx != -1, "§1.5 Anti-derive heading not found"
    section = text[idx: idx + 1500].lower()
    assert "aucun émetteur déterministe" in section or "no deterministic emitter" in section, (
        "§1.5 Anti-derive must carry an explicit note that the family is "
        "LLM-discretion only, with no deterministic emitter — otherwise the "
        "table implies automatic enforcement that does not exist."
    )
