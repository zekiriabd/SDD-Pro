"""Regression for audit finding F-04 (P0, reverse -> forward contract).

The documented handoff is `/sdd-reverse-full` -> `/sdd-full`. The forward
template and the LLM composer both write `- SFD-1: texte`; the deterministic
cross-cutting generator wrote `**SFD-1** — texte`, which the readiness gate
counted as ZERO IDs. The symptom was a WARN nobody reads, but every FD/SFD-keyed
coverage check then ran against an empty set and passed trivially: the
advertised traceability was structurally absent on those FEATs.

Covers the three parts of the fix:
  1. `crosscutting_feats` emits the canonical `- ID-N: ` bullet
  2. `validate_readiness` ID matching tolerates bold (legacy FEATs on disk)
  3. a present-but-ID-less required section is BLOCKING, not a warning
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PY_ROOT = Path(__file__).parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from sdd_reverse.crosscutting_feats import (                     # noqa: E402
    build_database_feat,
    build_libraries_feat,
)
from sdd_scripts.validate_readiness import (                     # noqa: E402
    count_bullets,
    get_all_ids,
    id_line_re,
)
# Aliased: pytest would otherwise collect `test_id_sequence` (a helper of the
# gate, not a test) and fail on its `content` parameter as a missing fixture.
from sdd_scripts.validate_readiness import test_id_sequence as id_sequence  # noqa: E402

# The regex the gate historically required (validate_readiness.py, pre-fix) —
# kept verbatim here so the canonical output is pinned against the ORIGINAL
# contract, not merely against the current, more tolerant matcher.
_CANONICAL_BULLET = r"(?m)^\s*-\s+{prefix}-\d+\s*:"

_SECTIONS = [
    ("SFD", "Functional Needs"),
    ("FD", "Functional Deliverables"),
    ("BR", "Business Rules"),
    ("AC", "Acceptance Criteria"),
]

_DEPS = {
    "packages": [
        {"name": "log4net", "version": "1.2.10", "ecosystem": "nuget",
         "source": "packages.config", "evidence": "packages.config:3"},
        {"name": "Newtonsoft.Json", "version": "13.0.3", "ecosystem": "nuget",
         "source": "packages.config", "evidence": "packages.config:4"},
    ],
    "assemblyReferences": [
        {"name": "System.Web", "hintPath": None, "evidence": "App.csproj:12"},
    ],
    "binaries": [],
}

_DB_SCHEMA = {
    "entities": [
        {"name": "User", "table": "Users",
         "fields": [{"name": "Id", "type": "int"}, {"name": "Login", "type": "nvarchar"}],
         "evidence": ["Scripts/CreateSchema.sql:3"]},
        {"name": "Role", "table": "Roles",
         "fields": [{"name": "Id", "type": "int"}],
         "evidence": ["Scripts/CreateSchema.sql:20"]},
    ],
    "relations": [],
}

_DATA_ACCESS = {
    "storedProcedureDefs": [
        {"name": "sp_ValidateUser",
         "params": [{"name": "@Login", "type": "nvarchar"}],
         "file": "Scripts/UserProcs.sql", "line": 2},
    ],
    "storedProcedureCalls": [],
    "queries": [],
}

_CONFIG = {
    "connectionStrings": [
        {"name": "AppDb", "provider": "System.Data.SqlClient", "server": "localhost",
         "database": "App", "file": "Web.config", "line": 5},
    ],
}


def _crosscutting_feats() -> dict[str, str]:
    return {
        "libraries": build_libraries_feat(
            _DEPS, n=1, name="Librairies", project="LegacyBilling", language="csharp"),
        "database": build_database_feat(
            _DB_SCHEMA, _DATA_ACCESS, _CONFIG,
            n=2, name="Database", project="LegacyBilling", language="csharp"),
    }


# --------------------------------------------------------------------------- #
# 1. The generator emits the canonical bullet
# --------------------------------------------------------------------------- #

def test_crosscutting_feats_match_the_original_gate_regex():
    """Every SFD/FD/BR/AC bullet matches `^\\s*-\\s+ID-N\\s*:` exactly."""
    for label, content in _crosscutting_feats().items():
        for prefix, _section in _SECTIONS:
            hits = re.findall(_CANONICAL_BULLET.format(prefix=prefix), content)
            assert hits, f"{label}: no canonical {prefix}-N bullet"


def test_crosscutting_feats_carry_no_bold_ids():
    """`**SFD-1**` must never come back — it is invisible to the gate."""
    for label, content in _crosscutting_feats().items():
        bold = re.findall(r"\*\*(?:SFD|FD|BR|AC)-\d+\*\*", content)
        assert not bold, f"{label}: bold IDs reintroduced: {bold}"


def test_readiness_gate_counts_the_crosscutting_ids():
    """The gate must see a NON-EMPTY, contiguous ID set on both FEATs."""
    feats = _crosscutting_feats()

    for label, content in feats.items():
        for prefix, section in _SECTIONS:
            seq = id_sequence(content, prefix, section)
            assert not seq.get("skipped"), f"{label}/{prefix}: section missing"
            assert not seq.get("empty"), f"{label}/{prefix}: section renders zero IDs"
            assert seq["ok"], f"{label}/{prefix}: {seq}"
            assert count_bullets(content, section, prefix) == seq["count"]

    # Traceability is only real if the IDs actually enumerate the source items:
    # 2 packages + 1 assembly reference -> FD-1..FD-3.
    assert get_all_ids(feats["libraries"], "FD", "Functional Deliverables") == [
        "FD-1", "FD-2", "FD-3"]
    # 2 entities + 1 stored procedure + 1 connection string -> FD-1..FD-4.
    assert get_all_ids(feats["database"], "FD", "Functional Deliverables") == [
        "FD-1", "FD-2", "FD-3", "FD-4"]


# --------------------------------------------------------------------------- #
# 2. Matching tolerates bold (FEATs already generated on disk)
# --------------------------------------------------------------------------- #

_BOLD_FEAT = """# FEAT 2 - Database

## Functional Needs

**SFD-1** — ancien format gras, sans marqueur de liste.
- **SFD-2** — gras avec marqueur de liste.

## Functional Deliverables

- FD-1: format canonique.

## Business Rules

- BR-1: regle.
"""


def test_bold_ids_are_still_counted():
    """A pre-fix FEAT on disk must not score zero — that hid the defect."""
    seq = id_sequence(_BOLD_FEAT, "SFD", "Functional Needs")
    assert seq["count"] == 2 and seq["ok"], seq
    assert count_bullets(_BOLD_FEAT, "Functional Needs", "SFD") == 2


def test_sfd_lines_are_not_counted_as_fd():
    """`FD` must not match inside `SFD-1` — the prefixes overlap textually."""
    assert count_bullets(_BOLD_FEAT, "Functional Needs", "FD") == 0
    assert get_all_ids(_BOLD_FEAT, "FD", "Functional Deliverables") == ["FD-1"]


def test_prose_mentions_are_not_counted_as_ids():
    """Tolerance must not turn narrative text into phantom IDs."""
    doc = (
        "# FEAT 1\n\n"
        "## Functional Needs\n\n"
        "Le besoin SFD-3 est traite ailleurs, cette phrase n'est pas un bullet.\n\n"
        "## Business Rules\n\n"
        "- BR-1: regle.\n"
    )
    assert id_sequence(doc, "SFD", "Functional Needs") == {"empty": True}
    assert count_bullets(doc, "Functional Needs", "SFD") == 0


def test_id_line_re_requires_a_separator():
    """`SFD-1` alone on a line is not an item — a `:` or dash must follow."""
    assert not id_line_re("SFD").search("SFD-1\n")
    assert id_line_re("SFD").search("- SFD-1: texte\n")
    assert id_line_re("SFD").search("**SFD-1** — texte\n")


# --------------------------------------------------------------------------- #
# 3. A present-but-ID-less required section is blocking
# --------------------------------------------------------------------------- #

def test_empty_required_section_is_blocking_not_a_warning():
    """SFD-EMPTY / FD-EMPTY must be an error: a WARN protected nothing.

    Asserted on the source of `validate_readiness.main` because the branch is
    inline in the CLI: an empty required section calls `add_err`, never
    `add_warn`. A coverage check keyed on an empty ID set passes trivially, so
    this case cannot be allowed to reach GO.
    """
    source = (PY_ROOT / "sdd_scripts" / "validate_readiness.py").read_text(encoding="utf-8")
    empty_branch = source.split('if r.get("empty"):', 1)[1].split('if r.get("ok"):', 1)[0]
    assert 'rep.add_err(' in empty_branch, empty_branch
    assert 'rep.add_warn(' not in empty_branch, empty_branch
    assert '{prefix}-EMPTY' in empty_branch
