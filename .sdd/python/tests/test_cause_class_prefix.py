"""Every `CAUSE:` line in an agent/command prompt must carry a `[CLASS]`.

Audit M1 (2026-08-29). `rules/error-classification.md §5` states the rule as a
hard invariant — *"Pas de bloc ERROR sans préfixe `[CLASS]`. Si rien ne matche
→ `[UNKNOWN]`."* — but nothing enforced it, and roughly half the forward
prompts violated it. `build_loop`, the hooks and the console dashboards all
classify by that prefix; an unprefixed `CAUSE:` degrades silently to
`[UNKNOWN]` and the run loses its cause-root.

`test_error_classification_reciprocity.py` already checks the other
direction (a class that is *emitted* must exist in the taxonomy). This file
closes the loop: a cause that is emitted must be *classed at all*.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SDD_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = SDD_ROOT / "agents"
COMMANDS_DIR = SDD_ROOT / "commands"

#: A `CAUSE:` line at the start of a line (possibly indented). Prose that
#: merely *mentions* `CAUSE:` mid-sentence is not an emission and is ignored.
_CAUSE_LINE = re.compile(r"^\s*CAUSE:\s*(?P<rest>.*)$")

#: Accepted prefixes: a real class `[SOME_CLASS]`, or the documented template
#: placeholder `[{CLASS}]` used in the report-format examples of the auditor
#: agents (those are format specimens, not emissions).
_CLASSED = re.compile(r"^\[(?:[A-Z][A-Z0-9_]*|\{CLASS\})\]")

#: Frozen list of the `CAUSE:` lines still missing a class after the M1 pass.
#:
#: These live in command files that were outside the scope of the audit
#: remediation branch (`.sdd/commands/{dev-backend,dev-frontend,feat-deepen,
#: feat-generate,sdd-kill-server}.md`). The allowlist is a **ratchet**: the
#: set may only shrink. Adding a new unclassed CAUSE anywhere fails this test;
#: fixing one of these requires deleting its entry here.
KNOWN_UNCLASSED: frozenset[tuple[str, int]] = frozenset({
    # Emptied 2026-08-30 — the 6 remaining unclassed CAUSE: lines (all
    # simple [INVALID_ARG]/[FEAT_NOT_FOUND]/[FEAT_REJECTED] cases) were
    # classed as a follow-up to the 2026-08-29 audit's M1 fix. Left empty
    # rather than removed so the ratchet's own self-check keeps exercising
    # the "stale entry" path.
})


def _scan() -> list[tuple[str, int, str]]:
    offenders: list[tuple[str, int, str]] = []
    for directory in (AGENTS_DIR, COMMANDS_DIR):
        if not directory.is_dir():
            continue
        for md in sorted(directory.glob("*.md")):
            rel = f"{directory.name}/{md.name}"
            text = md.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                m = _CAUSE_LINE.match(line)
                if not m:
                    continue
                rest = m.group("rest").strip()
                if not rest:
                    continue
                if _CLASSED.match(rest):
                    continue
                offenders.append((rel, lineno, rest[:110]))
    return offenders


def test_no_new_unclassed_cause_lines():
    offenders = _scan()
    unexpected = [o for o in offenders if (o[0], o[1]) not in KNOWN_UNCLASSED]
    assert not unexpected, (
        "CAUSE: line(s) with no [CLASS] prefix — see "
        "rules/error-classification.md §5. Pick the matching class from the "
        "taxonomy (or [UNKNOWN] as an absolute last resort):\n  "
        + "\n  ".join(f"{f}:{n}  CAUSE: {t}" for f, n, t in unexpected)
    )


def test_allowlist_does_not_rot():
    """A fixed entry must be removed from KNOWN_UNCLASSED, not left to rot."""
    offenders = {(f, n) for f, n, _ in _scan()}
    stale = sorted(KNOWN_UNCLASSED - offenders)
    assert not stale, (
        "KNOWN_UNCLASSED lists line(s) that are now classed (or moved). "
        "Delete them from the allowlist so the ratchet keeps its teeth:\n  "
        + "\n  ".join(f"{f}:{n}" for f, n in stale)
    )


@pytest.mark.parametrize("agent", [
    "po", "arch", "dev-backend", "dev-frontend", "qa", "elicitor",
])
def test_forward_core_agents_are_fully_classed(agent):
    """The forward core is expected to be 100% classed after the M1 pass."""
    md = AGENTS_DIR / f"{agent}.md"
    if not md.is_file():
        pytest.skip(f"{agent}.md absent")
    bad = [
        (n, t) for f, n, t in _scan() if f == f"agents/{md.name}"
    ]
    assert not bad, f"agents/{md.name} has unclassed CAUSE line(s): {bad}"
