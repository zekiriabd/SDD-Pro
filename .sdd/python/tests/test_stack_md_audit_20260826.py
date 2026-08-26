"""Regressions de l'audit `stack.md` du 2026-08-26.

Chaque test epingle un defaut CONSTATE (et reproduit) avant correction :

B1  `read_stack_md_text` levait un `UnicodeDecodeError` NON attrape sur un
    `stack.md` re-sauve en cp1252 (fichier gitignored, edite a la main, sous
    Windows, avec des commentaires accentues) - cassant d'un coup les ~27
    appelants de `read_project_config` / `get_active_stack_paths`, avec une
    traceback brute donc sans prefixe `[CLASS]`.

B2  Le hook `validate_stack_consistency` exigeait `^\\s+-\\s+` la ou le parseur
    canonique accepte `^\\s*-\\s*` : un `stack.md` ecrit sans indentation etait
    vu multi-backend par le pipeline et VIDE par le hook, qui validait donc un
    fichier incoherent.

B3  `AcceptanceGate` etait load-bearing (gate bloquante
    `[ACCEPTANCE_GATE_FAILED]`) mais absente de `project-config.schema.json` et
    de `config.base.yml` : WARN `[CONFIG_UNKNOWN_KEY]` permanent, ConfigError
    dure sous `SDD_CONFIG_STRICT=1`, et defaut `strict` code en dur donc hors
    de portee de la team policy.

A4  Les sous-cles pointees `AcceptanceGate.RequireE2E` / `.SmokeTimeout` /
    `.MinCoverage` etaient inatteignables : les deux regex de cle excluaient le
    `.`, rendant mortes les branches de `validate_acceptance._acceptance_config`.

A1  `UsGranularityTarget` etait declaree au schema + au template avec ZERO
    lecteur (ni base.yml, ni po.md, ni Python).

C4  `SecurityThreatModelEnabled` etait documentee DEPRECATED mais absente de
    `_DEPRECATED_CONFIG_KEYS` : no-op strictement MUET.

C5  `[ENV_MISSING]` / `[CONFIG_DEPRECATED_KEY]` / `[CONFIG_UNKNOWN_KEY]`
    etaient reemis a l'identique a chaque appel (~20+ par run `/sdd-full`),
    contre `output-protocol.md` section 5.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib import env_placeholders, layered_config, project_config
from sdd_lib.project_config import parse_active_stack_ids, parse_kv_block
from sdd_hooks import validate_stack_consistency as hook

_REPO_ROOT = _PY_ROOT.parent.parent

pytestmark = pytest.mark.smoke


def _write_stack(tmp_path: Path, body: str, *, encoding: str = "utf-8") -> Path:
    """Ecrit un stack.md dans une racine projet FIDELE.

    `config.base.yml` et `project-config.schema.json` sont copies depuis le
    vrai repo : sans eux `_load_schema_known_keys` retombe en fail-safe (aucune
    validation) et les tests de WARN passeraient a vide.
    """
    d = tmp_path / "workspace" / "stack"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "stack.md"
    p.write_bytes(body.encode(encoding))

    sdd = tmp_path / ".sdd" / "templates"
    sdd.mkdir(parents=True, exist_ok=True)
    src_sdd = _REPO_ROOT / ".sdd"
    (tmp_path / ".sdd" / "config.base.yml").write_bytes(
        (src_sdd / "config.base.yml").read_bytes()
    )
    (sdd / "project-config.schema.json").write_bytes(
        (src_sdd / "templates" / "project-config.schema.json").read_bytes()
    )

    project_config._read_text_cached.cache_clear()
    layered_config.reset_config_warn_cache()
    layered_config._SCHEMA_KEYS_CACHE = None
    env_placeholders.reset_env_warn_cache()
    return p


# ---------------------------------------------------------------------------
# B1 - encodage
# ---------------------------------------------------------------------------
class TestB1Encoding:
    def test_cp1252_stack_md_does_not_crash(self, tmp_path):
        """cp1252 + accents : lecture degradee, JAMAIS UnicodeDecodeError."""
        _write_stack(
            tmp_path,
            "# Project Stack\n\n## Project Config\n"
            "# Sélectivité désactivée\n"
            "AppName: MonApp\n",
            encoding="cp1252",
        )
        text = project_config.read_stack_md_text(tmp_path)
        assert text is not None, "un stack.md cp1252 ne doit pas etre vu comme absent"
        assert project_config.read_project_config(tmp_path).get("AppName") == "MonApp"

    def test_bom_is_stripped(self, tmp_path):
        """utf-8-sig : le BOM ne doit pas polluer la 1re ligne."""
        _write_stack(tmp_path, "﻿## Project Config\nAppName: MonApp\n")
        text = project_config.read_stack_md_text(tmp_path)
        assert not text.startswith("﻿")
        assert project_config.read_project_config(tmp_path).get("AppName") == "MonApp"


# ---------------------------------------------------------------------------
# B2 - hook de coherence vs parseur canonique
# ---------------------------------------------------------------------------
_UNINDENTED = (
    "# Project Stack\n\n## Active Tech Specs\n"
    "- .sdd/stacks/backend/node-express.md\n"
    "- .sdd/stacks/backend/python-fastapi.md\n"
    "- .sdd/stacks/frontend/react.md\n"
)
_INDENTED = (
    "# Project Stack\n\n## Active Tech Specs\n"
    " - .sdd/stacks/backend/node-express.md\n"
    " - .sdd/stacks/backend/python-fastapi.md\n"
)


class TestB2HookBlindSpot:
    @pytest.mark.parametrize(
        "body", [_UNINDENTED, _INDENTED], ids=["sans-indent", "avec-indent"]
    )
    def test_multi_backend_is_seen(self, tmp_path, body):
        p = _write_stack(tmp_path, body)
        active = hook._parse_active_stacks(p)
        assert len(active["backend"]) == 2
        errors = hook._check_coherence(active)
        assert any("backend multi-actif" in e for e in errors)

    def test_hook_and_canonical_parser_agree(self, tmp_path):
        """Le hook ne doit JAMAIS voir moins de stacks que le pipeline."""
        p = _write_stack(tmp_path, _UNINDENTED)
        canonical = parse_active_stack_ids(p.read_text(encoding="utf-8"))
        seen = {k: v for k, v in hook._parse_active_stacks(p).items() if v}
        assert seen == canonical

    def test_coherent_stack_still_passes(self, tmp_path):
        p = _write_stack(
            tmp_path,
            "## Active Tech Specs\n"
            " - .sdd/stacks/backend/node-express.md\n"
            " - .sdd/stacks/frontend/react.md\n",
        )
        assert hook._check_coherence(hook._parse_active_stacks(p)) == []


# ---------------------------------------------------------------------------
# A4 - cles pointees
# ---------------------------------------------------------------------------
class TestA4DottedKeys:
    def test_dotted_keys_survive_parse_kv_block(self):
        got = parse_kv_block(
            "AcceptanceGate: strict\n"
            "AcceptanceGate.RequireE2E: false\n"
            "AcceptanceGate.SmokeTimeout: 30\n"
            "AcceptanceGate.MinCoverage: 70\n"
        )
        assert got == {
            "AcceptanceGate": "strict",
            "AcceptanceGate.RequireE2E": "false",
            "AcceptanceGate.SmokeTimeout": "30",
            "AcceptanceGate.MinCoverage": "70",
        }

    def test_dotted_keys_survive_yaml_layer(self):
        got = layered_config._parse_yaml_minimal(
            "AcceptanceGate: warn\nAcceptanceGate.MinCoverage: 65\n"
        )
        assert got["AcceptanceGate.MinCoverage"] == "65"

    def test_acceptance_config_reads_the_dotted_keys(self, tmp_path):
        """La branche non-defaut de _acceptance_config devient atteignable."""
        from sdd_scripts import validate_acceptance

        _write_stack(
            tmp_path,
            "## Project Config\n"
            "AcceptanceGate: warn\n"
            "AcceptanceGate.RequireE2E: false\n"
            "AcceptanceGate.SmokeTimeout: 42\n"
            "AcceptanceGate.MinCoverage: 55\n",
        )
        cfg = validate_acceptance._read_acceptance_config(tmp_path)
        assert cfg["mode"] == "warn"
        assert cfg["require_e2e"] == "false"
        assert cfg["smoke_timeout"] == "42"
        assert cfg["min_coverage"] == "55"


# ---------------------------------------------------------------------------
# B3 / A1 - cles enregistrees aux 4 SSoT
# ---------------------------------------------------------------------------
_SCHEMA = json.loads(
    (_REPO_ROOT / ".sdd" / "templates" / "project-config.schema.json").read_text(
        encoding="utf-8"
    )
)
_BASE_TEXT = (_REPO_ROOT / ".sdd" / "config.base.yml").read_text(encoding="utf-8")
_DOC_TEXT = (_REPO_ROOT / ".sdd" / "docs" / "configuration-reference.md").read_text(
    encoding="utf-8"
)

_MUST_BE_REGISTERED = (
    "AcceptanceGate",
    "AcceptanceGate.RequireE2E",
    "AcceptanceGate.SmokeTimeout",
    "AcceptanceGate.MinCoverage",
    "UsGranularityTarget",
)


class TestB3Registration:
    @pytest.mark.parametrize("key", _MUST_BE_REGISTERED)
    def test_key_in_schema(self, key):
        assert key in _SCHEMA["properties"], (
            f"{key} absente du schema -> WARN [CONFIG_UNKNOWN_KEY] permanent"
        )

    @pytest.mark.parametrize("key", _MUST_BE_REGISTERED)
    def test_key_in_base_config(self, key):
        assert f"\n{key}:" in _BASE_TEXT, (
            f"{key} absente de config.base.yml -> defaut hors team policy"
        )

    @pytest.mark.parametrize("key", _MUST_BE_REGISTERED)
    def test_key_documented(self, key):
        assert f"`{key}`" in _DOC_TEXT, f"{key} absente de configuration-reference.md"

    def test_no_unknown_key_warn_on_acceptance_gate(self, tmp_path, capsys):
        """Poser AcceptanceGate ne doit plus produire de WARN inconnu."""
        _write_stack(tmp_path, "## Project Config\nAcceptanceGate: warn\n")
        layered_config.reset_config_warn_cache()
        layered_config._SCHEMA_KEYS_CACHE = None
        layered_config.read_layered_config(root=tmp_path)
        assert "CONFIG_UNKNOWN_KEY" not in capsys.readouterr().err

    def test_strict_mode_accepts_acceptance_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SDD_CONFIG_STRICT", "1")
        _write_stack(tmp_path, "## Project Config\nAcceptanceGate: strict\n")
        layered_config.reset_config_warn_cache()
        layered_config._SCHEMA_KEYS_CACHE = None
        cfg = layered_config.read_layered_config(root=tmp_path)  # ne doit pas lever
        assert cfg["AcceptanceGate"] == "strict"

    def test_us_granularity_target_is_wired(self):
        """A1 : la cle doit avoir au moins un consommateur reel."""
        po = (_REPO_ROOT / ".sdd" / "agents" / "po.md").read_text(encoding="utf-8")
        assert "UsGranularityTarget" in po


# ---------------------------------------------------------------------------
# C4 - depreciation muette
# ---------------------------------------------------------------------------
class TestC4DeprecatedKeys:
    def test_security_threat_model_enabled_is_declared_deprecated(self):
        assert "SecurityThreatModelEnabled" in layered_config._DEPRECATED_CONFIG_KEYS

    def test_all_documented_deprecated_keys_do_warn(self):
        """Toute cle marquee DEPRECATED dans la doc doit warner, pas se taire."""
        for line in _DOC_TEXT.splitlines():
            if "DEPRECATED" not in line or not line.startswith("| `"):
                continue
            key = line.split("`")[1]
            assert key in layered_config._DEPRECATED_CONFIG_KEYS, (
                f"{key} est documentee DEPRECATED mais absente de "
                f"_DEPRECATED_CONFIG_KEYS -> no-op muet"
            )


# ---------------------------------------------------------------------------
# C5 - dedupe des WARN
# ---------------------------------------------------------------------------
class TestC5WarnDedupe:
    def test_env_missing_warned_once(self, tmp_path, capsys, monkeypatch):
        monkeypatch.delenv("SDD_UNSET_PORT", raising=False)
        _write_stack(
            tmp_path, "## Project Config\nFrontendLocalPort: ${SDD_UNSET_PORT}\n"
        )
        env_placeholders.reset_env_warn_cache()
        for _ in range(4):
            project_config.read_project_config(tmp_path)
        err = capsys.readouterr().err
        assert err.count("[ENV_MISSING]") == 1, (
            f"attendu 1 WARN, obtenu {err.count('[ENV_MISSING]')}"
        )

    def test_deprecated_key_warned_once(self, tmp_path, capsys):
        _write_stack(tmp_path, "## Project Config\nPlanCacheStrict: true\n")
        layered_config.reset_config_warn_cache()
        layered_config._SCHEMA_KEYS_CACHE = None
        for _ in range(4):
            layered_config.read_layered_config(root=tmp_path)
        assert capsys.readouterr().err.count("[CONFIG_DEPRECATED_KEY]") == 1

    def test_unknown_key_warned_once(self, tmp_path, capsys):
        _write_stack(tmp_path, "## Project Config\nRewiewMode: full\n")
        layered_config.reset_config_warn_cache()
        layered_config._SCHEMA_KEYS_CACHE = None
        for _ in range(4):
            layered_config.read_layered_config(root=tmp_path)
        assert capsys.readouterr().err.count("[CONFIG_UNKNOWN_KEY]") == 1


# ---------------------------------------------------------------------------
# A3 - doc morte supprimee
# ---------------------------------------------------------------------------
def test_stack_sections_proposed_is_gone():
    """Le brouillon affirmait 'PAS appliquee' alors que le template les portait."""
    assert not (_REPO_ROOT / ".sdd" / "stack-sections.proposed.md").exists()
    tmpl = (_REPO_ROOT / ".sdd" / "templates" / "stack.md.template").read_text(
        encoding="utf-8"
    )
    for section in ("## Active Harness", "## Active Model Provider", "## Model Selection"):
        assert section in tmpl
