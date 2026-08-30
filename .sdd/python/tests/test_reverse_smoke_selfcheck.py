"""test_reverse_smoke_selfcheck.py — anti-rot for the reverse smoke registry.

Audit 2026-06-11 (MA-8). Mirror of `tests/test_invariants_manifest.py` for the
reverse-engineering workflow. Guards against two silent drifts :

1. **Registry count drift** — `reverse_smoke._ALL_CHECKS` must hold the
   expected number of checks (14). The doc/manifest historically said "11" ;
   if a check is added/removed without updating the pinned count, this fails.

2. **Manifest ↔ registry mapping** — every `invariants[].id` declared in
   `.sdd/INVARIANTS.reverse.yml` whose `enforcer` is `reverse_smoke.py`
   must correspond to a check in `_ALL_CHECKS` (matched by the `CheckResult.name`
   the check returns). Same for `drift_checks[].id`. Invariants enforced by a
   *different* file (validate_reverse_feat.py, check_ladder_traceability.py) and
   the `deepening_contracts[]` (enforced by dedicated pytest suites) are
   explicitly out of scope and documented as such.

The test is deliberately tolerant of layout changes : it skips gracefully when
the module or manifest is absent / unparseable rather than hard-failing on an
unrelated refactor.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

# `.claude/python` is on sys.path via tests/conftest.py
try:
    from sdd_reverse_scripts import reverse_smoke
except Exception as exc:  # pragma: no cover - layout guard
    reverse_smoke = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

_EXPECTED_CHECK_COUNT = 14

# `.sdd/python/tests/` → parents[3] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _REPO_ROOT / ".sdd" / "INVARIANTS.reverse.yml"
_SMOKE_ENFORCER_SUFFIX = "reverse_smoke.py"


def _require_module():
    if reverse_smoke is None:
        pytest.skip(f"sdd_reverse_scripts.reverse_smoke not importable: {_IMPORT_ERROR}")


# ---------------------------------------------------------------------------
# 1. Registry count
# ---------------------------------------------------------------------------

def test_all_checks_count_matches_expected() -> None:
    """`_ALL_CHECKS` must hold exactly the pinned number of checks (14)."""
    _require_module()
    actual = len(reverse_smoke._ALL_CHECKS)
    assert actual == _EXPECTED_CHECK_COUNT, (
        f"reverse_smoke._ALL_CHECKS has {actual} checks, expected "
        f"{_EXPECTED_CHECK_COUNT}. If this is intentional, update "
        f"_EXPECTED_CHECK_COUNT here AND in reverse_smoke.py, plus any "
        f"'N-check' mentions in INVARIANTS.reverse.yml / "
        f"docs/reverse-engineering-workflow.md."
    )


def test_internal_expected_count_pin_is_consistent() -> None:
    """reverse_smoke pins its own count constant ; keep it in sync with us."""
    _require_module()
    internal = getattr(reverse_smoke, "_EXPECTED_CHECK_COUNT", None)
    if internal is None:
        pytest.skip("reverse_smoke exposes no _EXPECTED_CHECK_COUNT constant")
    assert internal == _EXPECTED_CHECK_COUNT, (
        f"reverse_smoke._EXPECTED_CHECK_COUNT={internal} != test pin "
        f"{_EXPECTED_CHECK_COUNT}"
    )


def test_all_checks_are_callables() -> None:
    _require_module()
    for check in reverse_smoke._ALL_CHECKS:
        assert callable(check), f"non-callable entry in _ALL_CHECKS: {check!r}"


# ---------------------------------------------------------------------------
# 2. Manifest ↔ registry mapping
# ---------------------------------------------------------------------------

def _registry_check_names() -> set[str]:
    """Collect the CheckResult.name each registered check returns.

    Checks are read-only filesystem probes (no side effects), so invoking
    them here is safe. We tolerate individual check failures (an unrelated
    environment issue should not break the mapping assertion).
    """
    names: set[str] = set()
    for check in reverse_smoke._ALL_CHECKS:
        try:
            result = check()
            names.add(result.name)
        except Exception:  # pragma: no cover - robustness
            # Fall back to function name heuristic so the mapping still works.
            names.add(getattr(check, "__name__", "").removeprefix("check_"))
    return names


def _parse_manifest_sections() -> dict[str, list[dict[str, str]]]:
    """Minimal hand-rolled parser (no PyYAML runtime dep, same convention as
    test_invariants_manifest.py). Returns {section_name: [{id, enforcer, ...}]}
    for the top-level list sections `invariants`, `drift_checks`,
    `deepening_contracts`.
    """
    text = _MANIFEST.read_text(encoding="utf-8")
    sections: dict[str, list[dict[str, str]]] = {
        "invariants": [],
        "drift_checks": [],
        "deepening_contracts": [],
    }
    current_section: str | None = None
    current_item: dict[str, str] | None = None
    in_block_scalar = False

    for line in text.splitlines():
        # Top-level section header e.g. `invariants:` / `drift_checks:`
        m_sec = re.match(r"^([A-Za-z_][\w]*):\s*$", line)
        if m_sec and m_sec.group(1) in sections:
            if current_item is not None and current_section is not None:
                sections[current_section].append(current_item)
                current_item = None
            current_section = m_sec.group(1)
            in_block_scalar = False
            continue
        # A different top-level key ends any current section
        if re.match(r"^[A-Za-z_][\w]*:\s*", line) and not line.startswith(" "):
            if current_item is not None and current_section is not None:
                sections[current_section].append(current_item)
                current_item = None
            current_section = None
            in_block_scalar = False
            continue
        if current_section is None:
            continue
        # New list item `  - id: foo`
        m_id = re.match(r"^\s*-\s*id:\s*(.+?)\s*$", line)
        if m_id:
            if current_item is not None:
                sections[current_section].append(current_item)
            current_item = {"id": m_id.group(1).strip().strip('"').strip("'")}
            in_block_scalar = False
            continue
        if current_item is None:
            continue
        # `    enforcer: path` (single line)
        m_enf = re.match(r"^\s+enforcer:\s*(.+?)\s*$", line)
        if m_enf:
            current_item["enforcer"] = m_enf.group(1).strip()
            in_block_scalar = False
            continue
    if current_item is not None and current_section is not None:
        sections[current_section].append(current_item)
    return sections


def test_manifest_present_and_parseable() -> None:
    if not _MANIFEST.is_file():
        pytest.skip(f"INVARIANTS.reverse.yml not found at {_MANIFEST}")
    sections = _parse_manifest_sections()
    assert sections["invariants"], "no invariants[] parsed (parser/layout drift?)"


def test_smoke_enforced_invariants_map_to_a_check() -> None:
    """Every invariant/drift_check whose enforcer is reverse_smoke.py must have
    a corresponding check in _ALL_CHECKS (matched by CheckResult.name)."""
    _require_module()
    if not _MANIFEST.is_file():
        pytest.skip(f"INVARIANTS.reverse.yml not found at {_MANIFEST}")

    sections = _parse_manifest_sections()
    registry_names = _registry_check_names()

    unmapped: list[str] = []
    smoke_enforced_ids: list[str] = []
    for section_name in ("invariants", "drift_checks"):
        for item in sections[section_name]:
            enforcer = item.get("enforcer", "")
            if not enforcer.endswith(_SMOKE_ENFORCER_SUFFIX):
                # Enforced elsewhere (validate_reverse_feat.py,
                # check_ladder_traceability.py) — out of scope for this map.
                continue
            inv_id = item["id"]
            smoke_enforced_ids.append(inv_id)
            if inv_id not in registry_names:
                unmapped.append(f"{section_name}[{inv_id}]")

    assert smoke_enforced_ids, (
        "no smoke-enforced invariants parsed — parser or manifest drift"
    )
    assert not unmapped, (
        "INVARIANTS.reverse.yml declares these as enforced by reverse_smoke.py "
        f"but no check in _ALL_CHECKS returns a matching CheckResult.name:\n  "
        + "\n  ".join(unmapped)
        + "\n\nFix options:\n"
        "  1. Add the missing check_* function to _ALL_CHECKS\n"
        "  2. Point the invariant's enforcer to the correct file\n"
        "  3. Make the check return CheckResult(name=<invariant-id>, ...)\n"
        f"\n(registry CheckResult.name values seen: {sorted(registry_names)})"
    )


def test_deepening_contracts_are_not_smoke_enforced() -> None:
    """deepening_contracts[] are enforced by dedicated pytest suites, never by
    reverse_smoke — documents the boundary so they are not expected in
    _ALL_CHECKS."""
    if not _MANIFEST.is_file():
        pytest.skip(f"INVARIANTS.reverse.yml not found at {_MANIFEST}")
    sections = _parse_manifest_sections()
    if not sections["deepening_contracts"]:
        pytest.skip("no deepening_contracts[] section present")
    smoke_enforced = [
        item["id"]
        for item in sections["deepening_contracts"]
        if item.get("enforcer", "").endswith(_SMOKE_ENFORCER_SUFFIX)
    ]
    assert not smoke_enforced, (
        "deepening_contracts must be enforced by pytest suites, not "
        f"reverse_smoke.py: {smoke_enforced}"
    )


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
