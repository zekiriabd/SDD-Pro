"""Couche SKILLS de la façade Claude Code (audit tokens 2026-11-06, run FEAT 15).

Trou trouvé : `skills-manifest.yaml` déclarait `claude-code: native-autotrigger`
mais le répertoire skills de la façade Claude n'existait pas. Claude Code ne découvre les skills que
sous `<claude_dir>/skills/<name>/SKILL.md` — les 13 skills SDD (owned +
vendored) vivaient dans `.sdd/skills/` et n'étaient donc JAMAIS chargés.

Ce test enforce :
  1. `ClaudeAdapter.emit_skills` émet une arborescence par entrée du manifest
     (SKILL.md + fichiers annexes copiés tels quels, `__pycache__` exclus) ;
  2. la façade committée (`<claude>/skills/`) est byte-identique à `.sdd/skills/`
     pour chaque skill du manifest (parité harness, même logique que
     agents/commands/rules) ;
  3. la couche est refusée pour les harnais variants (codex / gemini-cli),
     comme les rules.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .sdd/python

SDD_HOME = Path(__file__).resolve().parents[2]  # .sdd/
REPO_ROOT = SDD_HOME.parent
if str(SDD_HOME) not in sys.path:
    sys.path.insert(0, str(SDD_HOME))

from harness_build import ClaudeAdapter, CodexAdapter, GeminiAdapter, _load_skills_manifest  # noqa: E402

LIVE_SKILLS_DIR = REPO_ROOT / ".claude" / "skills"


def _skill_files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for p in root.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


@pytest.fixture(scope="module")
def manifest() -> list[dict]:
    return _load_skills_manifest(SDD_HOME)


@pytest.fixture(scope="module")
def build_dir():
    build_root = SDD_HOME / ".build"
    build_root.mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix="pytest-skills-", dir=build_root))
    results = ClaudeAdapter(repo_root=REPO_ROOT).emit_skills(out)
    skipped = {r.agent: r.skipped_reason for r in results if not r.ok}
    assert not skipped, f"émission skills incomplète: {skipped}"
    yield out, results
    shutil.rmtree(out, ignore_errors=True)


def test_manifest_lists_13_skills(manifest):
    assert len(manifest) == 13, [e.get("name") for e in manifest]
    for entry in manifest:
        src = REPO_ROOT / str(entry["source"])
        assert (src / "SKILL.md").is_file(), f"{entry['name']}: SKILL.md absent de {src}"


def test_emit_skills_copies_every_tree_verbatim(build_dir, manifest):
    out, results = build_dir
    assert len(results) == len(manifest)
    for entry in manifest:
        name = entry["name"]
        src = REPO_ROOT / str(entry["source"])
        dst = out / "skills" / name
        assert (dst / "SKILL.md").is_file(), f"{name}: SKILL.md non émis"
        assert _skill_files(src) == _skill_files(dst), f"{name}: arborescence émise ≠ source"


def test_committed_facade_skills_match_sources(manifest):
    """`<claude>/skills/<name>/` = copie exacte de `.sdd/skills/<name>/` (parité)."""
    assert LIVE_SKILLS_DIR.is_dir(), (
        "façade skills absente — régénérer : python .sdd/python/sdd_admin/rebuild_claude_facade.py --force"
    )
    divergent = []
    for entry in manifest:
        name = entry["name"]
        src = REPO_ROOT / str(entry["source"])
        live = LIVE_SKILLS_DIR / name
        if not (live / "SKILL.md").is_file():
            divergent.append(f"{name}: absent de la façade")
            continue
        if _skill_files(src) != _skill_files(live):
            divergent.append(f"{name}: façade ≠ source")
    assert not divergent, divergent


@pytest.mark.parametrize("adapter_cls", [CodexAdapter, GeminiAdapter])
def test_variant_skills_not_implemented(adapter_cls, build_dir):
    out, _ = build_dir
    with pytest.raises(NotImplementedError):
        adapter_cls(repo_root=REPO_ROOT).emit_skills(out)


def test_emit_skills_never_writes_outside_sdd_build():
    from harness_build import BuildSafetyError

    adapter = ClaudeAdapter(repo_root=REPO_ROOT)
    for forbidden in (REPO_ROOT / ".claude", REPO_ROOT / "workspace", SDD_HOME / "skills"):
        with pytest.raises(BuildSafetyError):
            adapter.emit_skills(forbidden)
