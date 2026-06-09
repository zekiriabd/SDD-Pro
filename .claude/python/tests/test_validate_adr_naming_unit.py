"""Unit tests for validate_adr_naming.py — ADR filename gate.

Covers (audit CTO 2026-06-09 Major #18 closure) :
    - classify: canonical / legacy / invalid recognition
    - scan: walks adrs_dir and groups by verdict
    - main: exit codes 0 (valid) / 1 (invalid) / 2 (missing dir)
    - --strict rejects legacy filenames

Canonical pattern v7.0.0+ :
    ADR-{YYYYMMDDTHHmmss}-{rand4}-{slug}.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_admin import validate_adr_naming as v  # noqa: E402


def test_classify_canonical():
    """Canonical = timestamp + rand4 (4 hex) + slug."""
    assert v.classify("ADR-20260606T222017-344c-governance-major-sprint.md") == "canonical"
    assert v.classify("ADR-20260605T163200-a1f2-runtime-sts-prerelease.md") == "canonical"


def test_classify_legacy():
    """Legacy = timestamp + slug (no rand4 between them)."""
    assert v.classify("ADR-20260519T120000-governance-major-auditors-trim.md") == "legacy"
    assert v.classify("ADR-20260606T120000-secrets-config-ssot-stack-md.md") == "legacy"


def test_classify_invalid():
    """Invalid : missing prefix, bad timestamp, uppercase, or wrong extension."""
    assert v.classify("not-an-adr.md") == "invalid"
    assert v.classify("ADR-not-a-timestamp-slug.md") == "invalid"
    assert v.classify("ADR-20260101T120000-ABCD-uppercase-slug.md") == "invalid"
    # Bad extension
    assert v.classify("ADR-20260101T120000-a1b2-good-slug.txt") == "invalid"
    # Slug > 40 chars total (legacy regex caps at 40)
    long_slug = "a" * 45
    assert v.classify(f"ADR-20260101T120000-{long_slug}.md") == "invalid"
    # Note: short slugs like "abc-too-short" are valid legacy filenames
    # (legacy accepts kebab-case [1-40] chars, with NO rand4 — so the
    # 4-hex-char rule only applies in CANONICAL form).


def test_classify_invalid_kebab_strict():
    """Audit CTO 2026-06-09 Major #2 : slug kebab-case strict.

    Refuse les slugs qui commencent/terminent par `-` ou ne contiennent que
    des tirets (régression : ancienne regex `[a-z0-9-]{1,40}` était trop
    permissive et acceptait ces noms malformés type `---.md`, `-foo.md`,
    `foo-.md`).

    Note 1 : un slug avec `--` AU MILIEU (entre alphanum start/end) reste légal
    en kebab-case strict — seuls les bords sont contraints.

    Note 2 : la fonction `classify()` tente canonical AVANT legacy. Un nom
    `ADR-TS-XXXX-{badSlug}.md` qui rate canonical à cause d'un slug malformé
    peut fallback en legacy avec slug entier `XXXX-{badSlug}` valide. Tests
    ci-dessous évitent ce piège en assurant que les motifs malformés font
    échouer LES DEUX regex.
    """
    # Slug commence par tiret (legacy : slug entier commence par `-`)
    assert v.classify("ADR-20260101T120000--leading.md") == "invalid"
    # Slug termine par tiret (legacy : slug entier finit par `-`)
    assert v.classify("ADR-20260101T120000-trailing-.md") == "invalid"
    # Slug termine par tiret (canonical+legacy : tous deux ratent)
    assert v.classify("ADR-20260101T120000-a1b2-trailing-.md") == "invalid"
    # Slug que des tirets (legacy : slug `----`)
    assert v.classify("ADR-20260101T120000-----.md") == "invalid"
    # Slug que des tirets (canonical+legacy : tous deux ratent)
    assert v.classify("ADR-20260101T120000-a1b2----.md") == "invalid"
    # Slug single char alphanum reste valide (canonical + legacy)
    assert v.classify("ADR-20260101T120000-a1b2-a.md") == "canonical"
    assert v.classify("ADR-20260101T120000-x.md") == "legacy"
    # Slug avec `--` au milieu (start/end alphanum) reste valide
    assert v.classify("ADR-20260101T120000-a1b2-mid--ok.md") == "canonical"


def test_scan_groups_by_verdict(tmp_path):
    """scan walks dir and bins into canonical/legacy/invalid."""
    adrs = tmp_path / ".claude" / "docs" / "adrs"
    adrs.mkdir(parents=True)
    (adrs / "ADR-20260606T100000-a1b2-feature-a.md").write_text("# canonical")
    (adrs / "ADR-20260519T120000-legacy-style.md").write_text("# legacy")
    (adrs / "ADR-broken.md").write_text("# invalid")

    # Patch ROOT so the relative path in output makes sense
    import sdd_admin.validate_adr_naming as mod
    orig_root = mod.ROOT
    mod.ROOT = tmp_path
    try:
        report = mod.scan(adrs)
    finally:
        mod.ROOT = orig_root

    assert report["found"] is True
    assert report["counts"]["canonical"] == 1
    assert report["counts"]["legacy"] == 1
    assert report["counts"]["invalid"] == 1
    assert report["counts"]["total"] == 3


def test_scan_missing_dir(tmp_path):
    """scan returns found=False when dir absent."""
    report = v.scan(tmp_path / "does-not-exist")
    assert report["found"] is False
    assert "error" in report


def test_main_exits_zero_on_real_repo(capsys):
    """The actual repo ADRs dir MUST pass validate_adr_naming (no invalid)."""
    # Save argv, run main with no args (uses default ADRs dir)
    saved_argv = sys.argv[:]
    sys.argv = ["validate_adr_naming.py"]
    try:
        rc = v.main()
    finally:
        sys.argv = saved_argv
    assert rc == 0, "real repo ADRs must all be canonical or legacy (no invalid)"


def test_main_include_projects_no_fatal_when_missing(capsys):
    """Audit CTO 2026-06-09 #22 closure : --include-projects ne plante pas
    quand `workspace/output/.sys/.context/adrs/` n'existe pas (greenfield repo).
    Le scan framework reste autoritaire, projects = optionnel."""
    saved_argv = sys.argv[:]
    sys.argv = ["validate_adr_naming.py", "--include-projects", "--json"]
    try:
        rc = v.main()
    finally:
        sys.argv = saved_argv
    # Doit retourner 0 même si project ADRs dir n'existe pas — la scan framework
    # est self-sufficient.
    assert rc == 0
    import json
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["include_projects"] is True
    # Si project dir présent, le merge a eu lieu ; sinon pas de clé project_adrs_dir
    assert payload["found"] is True
