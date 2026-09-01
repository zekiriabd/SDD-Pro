"""Tests du pont UI <-> stack.md (`sdd_admin.stack_config_api`).

Ce que ces tests protègent
==========================
Le contrat load-bearing de l'éditeur formulaire VSCode : un aller-retour par
l'UI ne doit JAMAIS reformater le `stack.md`. Les commentaires du Tech Lead
portent la mémoire des décisions projet ("Débloqué en warn le temps de…") ;
une régénération depuis template les effacerait silencieusement, et le Tech
Lead perdrait le pourquoi de sa propre configuration.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".sdd" / "python"))

from sdd_admin import stack_config_api as api  # noqa: E402

SCRIPT = REPO_ROOT / ".sdd" / "python" / "sdd_admin" / "stack_config_api.py"

MINIMAL_STACK = """# Project Stack

## Project Config
AppName: Demo
# décision du 2026-01-01 : coverage abaissée le temps de la migration
CoverageMin: 70
QAMode: full

## Active Architecture Pattern
 - .sdd/stacks/archi/mvc.md

## Active Tech Specs
# combo C1
 - .sdd/stacks/frontend/react.md

## Active UI Specs
 - .sdd/stacks/ui/shadcn.md

## Active QA Specs

## Active Auth Specs
 - .sdd/stacks/auth/azure-ad.md
 - AZ_TENANTID: ${AZ_TENANTID}

## Active Database
 - DatabaseType: postgres
 - DB_HOST: localhost
"""


@pytest.fixture
def stack_md(tmp_path: Path) -> Path:
    path = tmp_path / "workspace" / "stack" / "stack.md"
    path.parent.mkdir(parents=True)
    path.write_text(MINIMAL_STACK, encoding="utf-8", newline="")
    return path


def _write(stack_md: Path, patch: dict) -> dict:
    return api.apply_patch(REPO_ROOT, stack_md, patch)


# ─────────────────────────────────── read ──────────────────────────────────

class TestRead:
    def test_project_config_ignores_commented_keys(self, stack_md: Path) -> None:
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        assert payload["projectConfig"]["CoverageMin"] == "70"
        # `# Capabilities: prisma` style — un commentaire n'est pas une valeur
        assert "décision" not in json.dumps(payload["projectConfig"])

    def test_list_and_kv_sections_are_split(self, stack_md: Path) -> None:
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        assert payload["activeStacks"]["tech"] == [".sdd/stacks/frontend/react.md"]
        # ## Active Auth Specs porte À LA FOIS un chemin .md et des secrets :
        # le chemin va dans activeStacks, les paires dans kv, jamais l'inverse.
        assert payload["activeStacks"]["auth"] == [".sdd/stacks/auth/azure-ad.md"]
        assert payload["kv"]["auth"] == {"AZ_TENANTID": "${AZ_TENANTID}"}
        assert payload["kv"]["database"]["DatabaseType"] == "postgres"

    def test_harness_defaults_when_sections_absent(self, stack_md: Path) -> None:
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        assert payload["harness"]["harness"] == "claude-code"
        assert payload["harness"]["provider"] == "anthropic"

    def test_fields_are_generated_from_schema(self, stack_md: Path) -> None:
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        by_key = {f["key"]: f for f in payload["fields"]}
        assert by_key["QAMode"]["enum"], "QAMode doit exposer son énumération"
        assert by_key["CoverageMin"]["value"] == "70"
        assert by_key["CoverageMin"]["present"] is True
        # une clé du schéma absente du fichier reste proposée, non renseignée
        assert by_key["MaxParallel"]["present"] is False

    def test_missing_file_yields_warning_not_crash(self, tmp_path: Path) -> None:
        payload = api.build_read_payload(REPO_ROOT, tmp_path / "absent.md")
        assert payload["exists"] is False
        assert payload["warnings"]
        assert payload["fields"], "le formulaire reste affichable avant bootstrap"

    def test_catalog_covers_every_dimension(self) -> None:
        catalog = api.build_catalog(REPO_ROOT)
        assert set(catalog) == set(api.CATALOG_DIMENSIONS)
        entries = [e for v in catalog.values() for e in v]
        assert len(entries) >= 30, "catalogue de stacks quasi vide — glob cassé ?"
        assert all(e["path"].endswith(".md") for e in entries)
        assert {e["tier"] for e in entries} <= {
            "validated", "bench-validated", "scaffold-validated",
            "reference", "experimental", "unsupported", "unknown",
        }


# ────────────────────────────────── write ──────────────────────────────────

class TestWrite:
    def test_comments_and_untouched_keys_survive(self, stack_md: Path) -> None:
        before = stack_md.read_text(encoding="utf-8")
        _write(stack_md, {"projectConfig": {"CoverageMin": "85"}})
        after = stack_md.read_text(encoding="utf-8")
        assert "# décision du 2026-01-01" in after
        assert "# combo C1" in after
        assert "CoverageMin: 85" in after
        assert "AppName: Demo" in after
        # une seule ligne change
        diff = [
            (a, b) for a, b in zip(before.split("\n"), after.split("\n")) if a != b
        ]
        assert diff == [("CoverageMin: 70", "CoverageMin: 85")]

    def test_new_key_appended_to_project_config(self, stack_md: Path) -> None:
        _write(stack_md, {"projectConfig": {"MaxParallel": "3"}})
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        assert payload["projectConfig"]["MaxParallel"] == "3"
        # appendue DANS la section, pas en fin de fichier
        text = stack_md.read_text(encoding="utf-8")
        assert text.index("MaxParallel: 3") < text.index("## Active Architecture")

    def test_remove_keys_drops_the_line(self, stack_md: Path) -> None:
        _write(stack_md, {"removeKeys": ["QAMode"]})
        assert "QAMode" not in api.build_read_payload(
            REPO_ROOT, stack_md
        )["projectConfig"]

    def test_unchanged_patch_does_not_touch_disk(self, stack_md: Path) -> None:
        result = _write(stack_md, {"projectConfig": {"CoverageMin": "70"}})
        assert result["status"] == "unchanged"

    def test_list_section_replaced_comments_kept(self, stack_md: Path) -> None:
        _write(stack_md, {"activeStacks": {"tech": [
            ".sdd/stacks/frontend/angular.md",
            ".sdd/stacks/backend/dotnet-minimalapi.md",
        ]}})
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        assert payload["activeStacks"]["tech"] == [
            ".sdd/stacks/frontend/angular.md",
            ".sdd/stacks/backend/dotnet-minimalapi.md",
        ]
        assert "# combo C1" in stack_md.read_text(encoding="utf-8")

    def test_empty_list_clears_section(self, stack_md: Path) -> None:
        _write(stack_md, {"activeStacks": {"ui": []}})
        assert api.build_read_payload(REPO_ROOT, stack_md)["activeStacks"]["ui"] == []

    def test_kv_upsert_preserves_other_pairs(self, stack_md: Path) -> None:
        _write(stack_md, {"kv": {"database": {"DB_NAME": "demo"}}})
        db = api.build_read_payload(REPO_ROOT, stack_md)["kv"]["database"]
        assert db == {"DatabaseType": "postgres", "DB_HOST": "localhost",
                      "DB_NAME": "demo"}

    def test_harness_sections_created_then_updated(self, stack_md: Path) -> None:
        _write(stack_md, {"harness": {"harness": "codex", "provider": "openai",
                                      "mode": "dynamic"}})
        payload = api.build_read_payload(REPO_ROOT, stack_md)
        assert payload["harness"] == {
            "harness": "codex", "provider": "openai", "endpoint": "default",
            "mode": "dynamic",
            "tierProviders": {"deep": "openai", "balanced": "openai",
                              "fast": "openai"},
        }
        # second passage : mise à jour en place, pas de section dupliquée
        _write(stack_md, {"harness": {"harness": "gemini-cli"}})
        text = stack_md.read_text(encoding="utf-8")
        assert text.count("## Active Harness") == 1
        assert api.build_read_payload(
            REPO_ROOT, stack_md
        )["harness"]["harness"] == "gemini-cli"

    def test_tier_map_override_is_preserved_on_read(self, stack_md: Path) -> None:
        stack_md.write_text(
            stack_md.read_text(encoding="utf-8")
            + "\n## Active Model Provider\nProvider: anthropic\nModelTierMap:\n"
              "  fast: moonshot\n",
            encoding="utf-8", newline="",
        )
        harness = api.build_read_payload(REPO_ROOT, stack_md)["harness"]
        assert harness["tierProviders"]["fast"] == "moonshot"
        assert harness["tierProviders"]["deep"] == "anthropic"

    def test_line_endings_preserved_crlf(self, tmp_path: Path) -> None:
        path = tmp_path / "stack.md"
        path.write_text(MINIMAL_STACK.replace("\n", "\r\n"), encoding="utf-8",
                        newline="")
        _write(path, {"projectConfig": {"CoverageMin": "85"}})
        raw = path.read_bytes()
        assert b"\r\n" in raw
        assert raw.count(b"\n") == raw.count(b"\r\n"), "LF orphelin introduit"

    def test_bom_preserved(self, tmp_path: Path) -> None:
        path = tmp_path / "stack.md"
        path.write_bytes(b"\xef\xbb\xbf" + MINIMAL_STACK.encode("utf-8"))
        _write(path, {"projectConfig": {"CoverageMin": "85"}})
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")


# ───────────────────────────────── refus ───────────────────────────────────

class TestRejections:
    def test_unknown_harness_refused(self, stack_md: Path) -> None:
        with pytest.raises(ValueError, match="harness invalide"):
            _write(stack_md, {"harness": {"harness": "chatgpt-web"}})

    def test_stack_outside_section_scope_refused(self, stack_md: Path) -> None:
        # un stack QA n'a rien à faire dans ## Active UI Specs
        with pytest.raises(ValueError, match="hors perimetre"):
            _write(stack_md, {"activeStacks": {
                "ui": [".sdd/stacks/qa/code-quality.md"]}})

    def test_nonexistent_stack_refused(self, stack_md: Path) -> None:
        with pytest.raises(ValueError, match="inexistant sur disque"):
            _write(stack_md, {"activeStacks": {
                "ui": [".sdd/stacks/ui/does-not-exist.md"]}})

    def test_unknown_section_refused(self, stack_md: Path) -> None:
        with pytest.raises(ValueError, match="section de liste inconnue"):
            _write(stack_md, {"activeStacks": {"backend": []}})

    def test_write_on_missing_file_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _write(tmp_path / "absent.md", {"projectConfig": {"A": "b"}})

    def test_failed_patch_leaves_file_untouched(self, stack_md: Path) -> None:
        before = stack_md.read_bytes()
        with pytest.raises(ValueError):
            _write(stack_md, {
                "projectConfig": {"CoverageMin": "85"},
                "harness": {"harness": "nope"},
            })
        assert stack_md.read_bytes() == before, "écriture partielle = stack corrompu"


# ─────────────────────────────────── CLI ───────────────────────────────────

class TestCli:
    def _run(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=stdin, capture_output=True, text=True, encoding="utf-8",
            cwd=str(REPO_ROOT),
        )

    def test_read_emits_valid_json(self, stack_md: Path) -> None:
        proc = self._run("read", "--stack-md", str(stack_md))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["schemaVersion"] == 1

    def test_catalog_verb_is_light(self) -> None:
        proc = self._run("catalog")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert set(payload) == {"schemaVersion", "catalog"}

    def test_write_verb_reads_stdin(self, stack_md: Path) -> None:
        proc = self._run("write", "--stack-md", str(stack_md),
                         stdin='{"projectConfig":{"CoverageMin":"91"}}')
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["status"] == "ok"
        assert "CoverageMin: 91" in stack_md.read_text(encoding="utf-8")

    def test_malformed_json_exits_invalid_input(self, stack_md: Path) -> None:
        proc = self._run("write", "--stack-md", str(stack_md), stdin="{nope")
        assert proc.returncode == api.EXIT_INVALID_INPUT
        # format ERROR 3L disque (output-protocol.md §7.3)
        assert proc.stderr.startswith("ERROR:")
        assert "CAUSE: [INVALID_ARG]" in proc.stderr
        assert "FIX:" in proc.stderr


class TestEmitTextMode:
    """Mode editeur VSCode : le document est possede par l'editeur."""

    def test_source_text_wins_over_disk(self, stack_md: Path) -> None:
        result = api.apply_patch(
            REPO_ROOT, stack_md,
            {"projectConfig": {"CoverageMin": "99"},
             "sourceText": "# Project Stack\n\n## Project Config\nCoverageMin: 1\n"},
            emit_text=True,
        )
        assert result["text"] == (
            "# Project Stack\n\n## Project Config\nCoverageMin: 99\n"
        )
        # le disque n'a pas bouge : c'est l'editeur qui appliquera le texte
        assert "CoverageMin: 70" in stack_md.read_text(encoding="utf-8")

    def test_emit_text_preserves_crlf_of_source(self, stack_md: Path) -> None:
        source = "# Project Stack\r\n\r\n## Project Config\r\nCoverageMin: 1\r\n"
        result = api.apply_patch(
            REPO_ROOT, stack_md,
            {"projectConfig": {"CoverageMin": "2"}, "sourceText": source},
            emit_text=True,
        )
        assert "\r\n" in result["text"]
        assert "\n" not in result["text"].replace("\r\n", "")

    def test_emit_text_reports_unchanged(self, stack_md: Path) -> None:
        source = "# Project Stack\n\n## Project Config\nCoverageMin: 1\n"
        result = api.apply_patch(
            REPO_ROOT, stack_md,
            {"projectConfig": {"CoverageMin": "1"}, "sourceText": source},
            emit_text=True,
        )
        assert result["status"] == "unchanged"
        assert result["text"] == source

    def test_emit_text_works_without_file_on_disk(self, tmp_path: Path) -> None:
        # un stack.md jamais sauvegarde (nouveau projet) doit rester editable
        result = api.apply_patch(
            REPO_ROOT, tmp_path / "absent.md",
            {"projectConfig": {"AppName": "Demo"},
             "sourceText": "# Project Stack\n\n## Project Config\n"},
            emit_text=True,
        )
        assert "AppName: Demo" in result["text"]


class TestQuoteStyle:
    """Le style de guillemets est un choix du Tech Lead, pas du formulaire."""

    def test_existing_quotes_are_kept(self, stack_md: Path) -> None:
        stack_md.write_text(
            '# Project Stack\n\n## Project Config\nA11yMode: "off"\n',
            encoding="utf-8", newline="",
        )
        _write(stack_md, {"projectConfig": {"A11yMode": "manual"}})
        assert 'A11yMode: "manual"' in stack_md.read_text(encoding="utf-8")

    def test_single_quotes_are_kept(self, stack_md: Path) -> None:
        stack_md.write_text(
            "# Project Stack\n\n## Project Config\nPerfMode: 'off'\n",
            encoding="utf-8", newline="",
        )
        _write(stack_md, {"projectConfig": {"PerfMode": "full"}})
        assert "PerfMode: 'full'" in stack_md.read_text(encoding="utf-8")

    def test_unquoted_stays_unquoted(self, stack_md: Path) -> None:
        _write(stack_md, {"projectConfig": {"QAMode": "tests-only"}})
        assert "QAMode: tests-only" in stack_md.read_text(encoding="utf-8")

    def test_hash_forces_quoting(self, stack_md: Path) -> None:
        # sans guillemets, `#` serait lu comme un commentaire en ligne et la
        # valeur serait tronquee au prochain chargement
        _write(stack_md, {"kv": {"database": {"DB_PASSWORD": "p@ss#1"}}})
        text = stack_md.read_text(encoding="utf-8")
        assert 'DB_PASSWORD: "p@ss#1"' in text
        assert api.build_read_payload(
            REPO_ROOT, stack_md
        )["kv"]["database"]["DB_PASSWORD"] == "p@ss#1"
