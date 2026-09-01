#!/usr/bin/env python3
"""stack_config_api — pont déterministe (0 token) entre `stack.md` et une UI.

Raison d'être
=============
L'extension VSCode (`vscode-extension/`) propose un éditeur formulaire pour
`workspace/stack/stack.md`. Réimplémenter le parseur en TypeScript créerait un
second SSoT qui dériverait du premier au premier ajout de clé — et le hook
`validate_stack_consistency` se battrait contre l'UI. Ce module est donc le
SEUL point d'entrée : l'UI ne fait que sérialiser/désérialiser du JSON.

Trois verbes
============
  read    -> JSON complet (valeurs courantes + schéma + catalogue + combos)
  write   -> applique un patch JSON (stdin) au `stack.md`, chirurgicalement
  catalog -> catalogue des stacks seul (payload léger, pour un refresh d'UI)

Contrat d'écriture (load-bearing)
=================================
`write` fait de l'édition LIGNE À LIGNE sur le texte existant, jamais une
régénération depuis un template : les commentaires du Tech Lead (`# POC test :
pas de prisma`, `# Débloqué en warn le temps de…`) portent la mémoire des
décisions projet et DOIVENT survivre à un aller-retour par l'UI. Un patch ne
touche que les clés qu'il déclare ; tout le reste du fichier est conservé
(BOM et style de fin de ligne inclus).

Usage
=====
    python .sdd/python/sdd_admin/stack_config_api.py read
    python .sdd/python/sdd_admin/stack_config_api.py catalog
    echo '{"projectConfig":{"CoverageMin":"85"}}' | \
        python .sdd/python/sdd_admin/stack_config_api.py write

Classes d'erreur
================
Aucune classe nouvelle : la taxonomie compte deja 193 classes, en ajouter
pour un cas couvert est une derive (`rules/error-classification.md`).
  `[INVALID_ARG]` : patch refuse (valeur hors enumeration, stack hors
                    perimetre de sa section, JSON illisible).
  `[NOT_FOUND]`   : `stack.md` absent alors qu'une ecriture est demandee.
  `[DISK]`        : ecriture impossible (droits, FS plein).

Exit codes
==========
    0 : OK (JSON sur stdout)
    2 : INVALID_INPUT (patch malformé, valeur hors énumération, fichier absent)
    3 : INFRA_ERROR (écriture disque impossible)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))

from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.stack_config import HARNESSES, parse_stack_config  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


EXIT_OK = 0
EXIT_INVALID_INPUT = 2
EXIT_INFRA_ERROR = 3

#: Sections `## Active …` portant une LISTE de chemins `.sdd/stacks/…`.
#: Clé = identifiant côté UI, valeur = (heading, dimensions catalogue autorisées).
LIST_SECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "archi": ("Active Architecture Pattern", ("archi",)),
    "tech": ("Active Tech Specs", ("frontend", "backend", "fullstack", "mobiles")),
    "ui": ("Active UI Specs", ("ui",)),
    "qa": ("Active QA Specs", ("qa",)),
    "auth": ("Active Auth Specs", ("auth",)),
}

#: Sections portant des paires ` - KEY: value` (secrets / connexion).
KV_SECTIONS: dict[str, str] = {
    "auth": "Active Auth Specs",
    "database": "Active Database",
    "smtp": "Active SMTP Server",
}

#: Dimensions du catalogue = sous-répertoires de `.sdd/stacks/`.
CATALOG_DIMENSIONS: tuple[str, ...] = (
    "archi", "auth", "backend", "frontend", "fullstack", "mobiles", "qa", "ui",
)

#: Regroupement des clés Project Config pour l'UI (ordre = ordre d'affichage).
#: Une clé absente de cette table tombe dans le groupe "advanced".
FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "identity": (
        "AppName", "FrontendName", "BackendName", "LibName", "AppNamespace",
        "FrontendLocalPort", "BackendLocalPort", "LibStrategy",
    ),
    "quality": (
        "QAMode", "CoverageMin", "AcceptanceGate", "SecurityScanEnabled",
        "CodeReviewMode", "CodeReviewFailOn", "SecurityMode", "SecurityFailOn",
        "SpecComplianceMode", "SpecComplianceFailOn", "ArchReviewMode",
        "ArchReviewFailOn", "A11yMode", "PerfMode",
    ),
    "budget": (
        "MaxParallel", "MaxCostPerRun", "BuildLoopMaxCostUsd", "BuildLoopMaxIter",
    ),
    "granularity": (
        "UsGranularityTarget", "UsGranularityWarnAt", "UsGranularityHardCap",
        "PlanReviewDefault",
    ),
}

_SECTION_RE = re.compile(r"^##\s+(?P<name>.+?)\s*$")
_PC_KEY_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<val>.*?)\s*$")
_BULLET_PATH_RE = re.compile(r"^\s*-\s*(?P<path>[^\s#][^#]*?\.md)\s*(?:#.*)?$")
_BULLET_KV_RE = re.compile(
    r"^\s*-\s*(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<val>.*?)\s*$"
)


# ───────────────────────────── repo / fichier ──────────────────────────────

def find_repo_root(start: Path | None = None) -> Path:
    """Racine projet = premier parent portant `.sdd/`. Fallback : cwd.

    Ne réutilise pas `sdd_lib.paths.repo_root()` : ce script est appelé par
    l'extension depuis un dossier utilisateur arbitraire, où l'heuristique
    `_looks_like_repo_root` (qui attend aussi `.claude/`) peut échouer avant
    que la façade ne soit matérialisée.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".sdd").is_dir():
            return candidate
    return here


def stack_md_path(root: Path) -> Path:
    return root / "workspace" / "stack" / "stack.md"


def _read_raw(path: Path) -> tuple[str, bool, str]:
    """Retourne (texte LF sans BOM, bom_present, newline d'origine)."""
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n").replace("\r", "\n"), bom, newline


def _restore(text: str, bom: bool, newline: str) -> str:
    out = text.replace("\n", newline) if newline != "\n" else text
    return ("﻿" + out) if bom else out


# ───────────────────────────── découpage sections ──────────────────────────

def _split_lines_by_section(lines: list[str]) -> list[tuple[str | None, int, int]]:
    """Découpe en (nom de section | None pour le préambule, start, end exclus)."""
    spans: list[tuple[str | None, int, int]] = []
    current: str | None = None
    start = 0
    for idx, line in enumerate(lines):
        match = _SECTION_RE.match(line)
        if not match:
            continue
        spans.append((current, start, idx))
        current = match.group("name").strip()
        start = idx + 1
    spans.append((current, start, len(lines)))
    return spans


def _section_span(lines: list[str], heading: str) -> tuple[int, int] | None:
    """(start, end) du CORPS de la section `heading`, casse-insensible."""
    wanted = heading.strip().lower()
    for name, start, end in _split_lines_by_section(lines):
        if name is not None and name.strip().lower() == wanted:
            return start, end
    return None


def _is_active(line: str) -> bool:
    """Ligne porteuse de valeur (ni vide, ni commentaire `#`)."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


# ───────────────────────────────── lecture ─────────────────────────────────

def read_project_config(lines: list[str]) -> dict[str, str]:
    span = _section_span(lines, "Project Config")
    if span is None:
        return {}
    values: dict[str, str] = {}
    for line in lines[span[0]:span[1]]:
        if not _is_active(line) or line.startswith((" ", "\t", "-")):
            continue
        match = _PC_KEY_RE.match(line)
        if match:
            values[match.group("key")] = match.group("val").strip().strip('"').strip("'")
    return values


def read_list_sections(lines: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, (heading, _dims) in LIST_SECTIONS.items():
        span = _section_span(lines, heading)
        paths: list[str] = []
        if span is not None:
            for line in lines[span[0]:span[1]]:
                if not _is_active(line):
                    continue
                match = _BULLET_PATH_RE.match(line)
                if match:
                    paths.append(match.group("path").strip().replace("\\", "/"))
        out[key] = paths
    return out


def read_kv_sections(lines: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for key, heading in KV_SECTIONS.items():
        span = _section_span(lines, heading)
        pairs: dict[str, str] = {}
        if span is not None:
            for line in lines[span[0]:span[1]]:
                if not _is_active(line):
                    continue
                match = _BULLET_KV_RE.match(line)
                if match and not match.group("val").endswith(".md"):
                    raw = match.group("val").strip()
                    pairs[match.group("key")] = raw.strip('"').strip("'")
        out[key] = pairs
    return out


def _stack_header(path: Path) -> dict[str, str]:
    """Extrait `Status:` / `Validation:` / `Scope:` de l'entête d'un stack `.md`.

    Ne lit que les 30 premières lignes : l'entête est un contrat de forme
    (cf. `validate_stack_md_headers.py`), inutile de charger 900 lignes de
    spécification technique pour peupler une liste déroulante.
    """
    header: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8-sig") as handle:
            for _ in range(30):
                line = handle.readline()
                if not line:
                    break
                if line.startswith("# Tech FEAT:") and "title" not in header:
                    header["title"] = line.split(":", 1)[1].strip()
                for field in ("Status", "Validation", "Scope"):
                    prefix = f"{field}:"
                    if line.startswith(prefix):
                        header[field.lower()] = line[len(prefix):].strip()
    except OSError:
        pass
    return header


def _validation_tier(validation: str) -> str:
    """Réduit une ligne `Validation:` libre à un tier machine."""
    low = validation.lower()
    if "\U0001F534" in validation:
        return "unsupported"
    if "\U0001F7E1" in validation or "experimental" in low or "poc-only" in low:
        return "experimental"
    for tier in ("bench-validated", "scaffold-validated", "validated", "reference"):
        if tier in low:
            return tier
    return "unknown" if not validation else "validated"


def build_catalog(root: Path) -> dict[str, list[dict[str, Any]]]:
    catalog: dict[str, list[dict[str, Any]]] = {}
    stacks_root = root / ".sdd" / "stacks"
    for dimension in CATALOG_DIMENSIONS:
        entries: list[dict[str, Any]] = []
        directory = stacks_root / dimension
        if directory.is_dir():
            for md in sorted(directory.glob("*.md")):
                if md.name.upper() == "README.MD":
                    continue
                header = _stack_header(md)
                validation = header.get("validation", "")
                entries.append({
                    "id": md.stem,
                    "dimension": dimension,
                    "path": f".sdd/stacks/{dimension}/{md.name}",
                    "title": header.get("title", md.stem),
                    "status": header.get("status", ""),
                    "validation": validation,
                    "tier": _validation_tier(validation),
                    "scope": header.get("scope", ""),
                })
        catalog[dimension] = entries
    return catalog


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_fields(schema: dict[str, Any], values: dict[str, str]) -> list[dict[str, Any]]:
    """Croise le schéma JSON du Project Config avec les valeurs courantes.

    C'est ce qui rend le formulaire GÉNÉRÉ : ajouter une clé dans
    `project-config.schema.json` la fait apparaître dans l'UI sans toucher au
    TypeScript. Les clés présentes dans stack.md mais absentes du schéma
    (extensions Tech Lead) sont conservées et marquées `known: false`.
    """
    definitions = schema.get("definitions", {})
    properties = schema.get("properties", {})

    def resolve(spec: dict[str, Any]) -> dict[str, Any]:
        ref = spec.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/definitions/"):
            merged = dict(definitions.get(ref.split("/")[-1], {}))
            merged.update({k: v for k, v in spec.items() if k != "$ref"})
            return merged
        return spec

    group_of: dict[str, str] = {}
    for group, keys in FIELD_GROUPS.items():
        for key in keys:
            group_of[key] = group

    fields: list[dict[str, Any]] = []
    for key, raw_spec in properties.items():
        spec = resolve(raw_spec if isinstance(raw_spec, dict) else {})
        fields.append({
            "key": key,
            "type": spec.get("type", "string"),
            "enum": spec.get("enum"),
            "minimum": spec.get("minimum"),
            "maximum": spec.get("maximum"),
            "default": spec.get("default"),
            "description": spec.get("description", ""),
            "group": group_of.get(key, "advanced"),
            "value": values.get(key),
            "present": key in values,
            "known": True,
        })
    for key, value in values.items():
        if key not in properties:
            fields.append({
                "key": key, "type": "string", "enum": None, "default": None,
                "minimum": None, "maximum": None,
                "description": "Clé hors schéma (extension projet) — conservée telle quelle.",
                "group": "advanced", "value": value, "present": True, "known": False,
            })
    order = list(FIELD_GROUPS) + ["advanced"]
    fields.sort(key=lambda f: (order.index(f["group"]), f["key"]))
    return fields


def _yaml_tier_map(path: Path) -> dict[str, str]:
    """Lit le seul bloc `tier_map:` d'un provider YAML (sans dépendance PyYAML).

    Le reste du fichier (pricing, telemetry, capabilities) n'intéresse pas
    l'UI ; un parseur minimal évite d'ajouter une dépendance au socle stdlib.
    """
    tiers: dict[str, str] = {}
    inside = False
    try:
        for line in path.read_text(encoding="utf-8-sig").split("\n"):
            if line.startswith("tier_map:"):
                inside = True
                continue
            if inside:
                if line[:1] not in (" ", "\t"):
                    break
                match = re.match(r"\s+(?P<k>deep|balanced|fast)\s*:\s*(?P<v>\S+)", line)
                if match:
                    tiers[match.group("k")] = match.group("v")
    except OSError:
        pass
    return tiers


def build_read_payload(root: Path, path: Path, *,
                       source_text: str | None = None) -> dict[str, Any]:
    """Payload complet pour l'UI.

    `source_text` non nul = lire ce texte plutot que le disque. L'editeur
    VSCode possede le document et peut porter des modifications non
    sauvegardees ; afficher le disque dans le formulaire pendant que
    l'editeur est sale ferait mentir l'UI a son utilisateur.
    """
    schema = _load_json(root / ".sdd" / "templates" / "project-config.schema.json")
    combos = _load_json(root / ".sdd" / "templates" / "combos.json")
    providers: list[dict[str, Any]] = []
    providers_dir = root / ".sdd" / "providers"
    if providers_dir.is_dir():
        for yaml_file in sorted(providers_dir.glob("*.yaml")):
            providers.append({
                "name": yaml_file.stem,
                "tierMap": _yaml_tier_map(yaml_file),
            })

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "repoRoot": str(root),
        "stackMdPath": "workspace/stack/stack.md",
        "exists": path.is_file(),
        "harnesses": list(HARNESSES),
        "providers": providers,
        "catalog": build_catalog(root),
        "combos": combos,
        "listSections": {k: v[0] for k, v in LIST_SECTIONS.items()},
        "listDimensions": {k: list(v[1]) for k, v in LIST_SECTIONS.items()},
        "kvSections": dict(KV_SECTIONS),
    }
    if source_text is None and not path.is_file():
        payload.update({
            "projectConfig": {},
            "fields": build_fields(schema, {}),
            "activeStacks": {k: [] for k in LIST_SECTIONS},
            "kv": {k: {} for k in KV_SECTIONS},
            "harness": None,
            "warnings": ["stack.md absent — lancer le bootstrap SDD-Pro."],
        })
        return payload

    if source_text is None:
        text, _bom, _nl = _read_raw(path)
    else:
        text = source_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        payload["exists"] = True
    lines = text.split("\n")
    values = read_project_config(lines)

    warnings: list[str] = []
    try:
        cfg = parse_stack_config(text)
        harness = {
            "harness": cfg.harness, "provider": cfg.provider,
            "endpoint": cfg.endpoint, "mode": cfg.mode,
            "tierProviders": dict(cfg.tier_providers),
        }
    except Exception as exc:  # StackConfigError et dérivés
        harness = None
        warnings.append(f"Sections harnais/provider illisibles : {exc}")

    payload.update({
        "projectConfig": values,
        "fields": build_fields(schema, values),
        "activeStacks": read_list_sections(lines),
        "kv": read_kv_sections(lines),
        "harness": harness,
        "warnings": warnings,
    })
    return payload


# ───────────────────────────────── écriture ────────────────────────────────

def _insert_section(lines: list[str], heading: str, body: list[str]) -> tuple[int, int]:
    """Crée `## heading` en fin de fichier et retourne le span de son corps."""
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append("")
    lines.append(f"## {heading}")
    start = len(lines)
    lines.extend(body)
    return start, len(lines)


def _requote(old_raw: str, new_value: str) -> str:
    """Reapplique le style de guillemets de l'ancienne valeur.

    `A11yMode: "off"` doit rester quote apres un passage par l'UI. Le
    parseur du framework (`project_config.parse_kv_block`) accepte les deux
    formes, mais degrader les guillemets ferait apparaitre dans le diff git
    du projet des lignes que l'utilisateur n'a pas touchees.

    Les guillemets sont AJOUTES quand la valeur en a besoin : un `#` non
    protege serait lu comme un commentaire en ligne, et une valeur bordee
    d'espaces perdrait ses bords.
    """
    stripped = old_raw.strip()
    for quote in ('"', "'"):
        if len(stripped) >= 2 and stripped.startswith(quote) and stripped.endswith(quote):
            return f"{quote}{new_value}{quote}"
    if "#" in new_value or new_value != new_value.strip():
        return f'"{new_value}"'
    return new_value


def patch_project_config(lines: list[str], patch: dict[str, str],
                         removed: list[str]) -> list[str]:
    span = _section_span(lines, "Project Config")
    if span is None:
        span = _insert_section(lines, "Project Config", [])
    start, end = span
    changed: list[str] = []

    remaining = dict(patch)
    out_body: list[str] = []
    for line in lines[start:end]:
        match = _PC_KEY_RE.match(line) if (
            _is_active(line) and not line.startswith((" ", "\t", "-"))
        ) else None
        if match is None:
            out_body.append(line)
            continue
        key = match.group("key")
        if key in removed:
            changed.append(f"-{key}")
            continue
        if key in remaining:
            new_value = remaining.pop(key)
            old_raw = match.group("val")
            rendered = _requote(old_raw, new_value)
            if old_raw.strip().strip('"').strip("'") != new_value:
                changed.append(key)
            out_body.append(f"{key}: {rendered}")
            continue
        out_body.append(line)

    if remaining:
        while out_body and not out_body[-1].strip():
            out_body.pop()
        for key, value in remaining.items():
            out_body.append(f"{key}: {_requote('', value)}")
            changed.append(key)
        out_body.append("")

    lines[start:end] = out_body
    return changed


def patch_list_section(lines: list[str], heading: str, paths: list[str]) -> list[str]:
    """Remplace les puces `.md` de la section ; commentaires préservés en tête."""
    span = _section_span(lines, heading)
    if span is None:
        span = _insert_section(lines, heading, [])
    start, end = span
    kept: list[str] = []
    had_any = False
    for line in lines[start:end]:
        if _is_active(line) and _BULLET_PATH_RE.match(line):
            had_any = True
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    lines[start:end] = kept + [f" - {p}" for p in paths] + [""]
    return [heading] if (paths or had_any) else []


def patch_kv_section(lines: list[str], heading: str,
                     pairs: dict[str, str]) -> list[str]:
    span = _section_span(lines, heading)
    if span is None:
        span = _insert_section(lines, heading, [])
    start, end = span
    remaining = dict(pairs)
    changed: list[str] = []
    out_body: list[str] = []
    for line in lines[start:end]:
        match = _BULLET_KV_RE.match(line) if _is_active(line) else None
        if match is None or match.group("val").endswith(".md"):
            out_body.append(line)
            continue
        key = match.group("key")
        if key in remaining:
            new_value = remaining.pop(key)
            old_raw = match.group("val")
            rendered = _requote(old_raw, new_value)
            if old_raw.strip().strip('"').strip("'") != new_value:
                changed.append(key)
            out_body.append(f" - {key}: {rendered}")
        else:
            out_body.append(line)
    if remaining:
        while out_body and not out_body[-1].strip():
            out_body.pop()
        for key, value in remaining.items():
            out_body.append(f" - {key}: {_requote('', value)}")
            changed.append(key)
        out_body.append("")
    lines[start:end] = out_body
    return changed


def _patch_scalar_in_section(lines: list[str], heading: str, key: str,
                             value: str, comments: list[str]) -> bool:
    span = _section_span(lines, heading)
    if span is None:
        span = _insert_section(lines, heading, [*comments, ""])
    start, end = span
    for idx in range(start, end):
        line = lines[idx]
        if not _is_active(line):
            continue
        match = _PC_KEY_RE.match(line)
        if match and match.group("key").lower() == key.lower():
            if match.group("val").strip() == value:
                return False
            lines[idx] = f"{key}: {value}"
            return True
    insert_at = end
    while insert_at > start and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, f"{key}: {value}")
    return True


def patch_harness(lines: list[str], harness: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    if "harness" in harness:
        value = str(harness["harness"])
        if value not in HARNESSES:
            raise ValueError(
                f"harness invalide: {value!r} (attendu: {'|'.join(HARNESSES)})"
            )
        if _patch_scalar_in_section(
            lines, "Active Harness", "Harness", value,
            ["# Ou tourne l'orchestration LLM. Options : " + " | ".join(HARNESSES)],
        ):
            changed.append("Harness")
    if "provider" in harness:
        if _patch_scalar_in_section(
            lines, "Active Model Provider", "Provider", str(harness["provider"]),
            ["# Quel vendeur execute les tokens. Independant du harnais."],
        ):
            changed.append("Provider")
    if "endpoint" in harness:
        if _patch_scalar_in_section(
            lines, "Active Model Provider", "Endpoint", str(harness["endpoint"]), [],
        ):
            changed.append("Endpoint")
    if "mode" in harness:
        if _patch_scalar_in_section(
            lines, "Model Selection", "Mode", str(harness["mode"]),
            ["# static = tier fixe par agent ; dynamic = route par complexite."],
        ):
            changed.append("Mode")
    return changed


def apply_patch(root: Path, path: Path, patch: dict[str, Any], *,
                emit_text: bool = False) -> dict[str, Any]:
    """Applique un patch. Deux modes, selon qui possede le fichier.

    `emit_text=False` (defaut, CLI/CI) : lit le disque, ecrit le disque.
    `emit_text=True` + `patch["sourceText"]` : opere sur le texte fourni et
    RETOURNE le resultat sans toucher au disque. C'est le mode de l'editeur
    VSCode : le document est possede par l'editeur (il peut porter des
    modifications non sauvegardees), et le remplacement passe par un
    `WorkspaceEdit` pour que Ctrl+Z et l'etat "modifie" restent natifs.
    """
    source_text = patch.get("sourceText")
    if source_text is not None:
        raw = str(source_text)
        bom = raw.startswith("\ufeff")
        stripped = raw.lstrip("\ufeff")
        newline = "\r\n" if "\r\n" in stripped else "\n"
        text = stripped.replace("\r\n", "\n").replace("\r", "\n")
    else:
        if not path.is_file():
            raise FileNotFoundError(f"stack.md introuvable: {path}")
        text, bom, newline = _read_raw(path)
    lines = text.split("\n")
    changed: dict[str, list[str]] = {}

    project_config = patch.get("projectConfig") or {}
    removed = list(patch.get("removeKeys") or [])
    if project_config or removed:
        touched = patch_project_config(
            lines, {k: str(v) for k, v in project_config.items()}, removed
        )
        if touched:
            changed["projectConfig"] = touched

    for key, paths in (patch.get("activeStacks") or {}).items():
        if key not in LIST_SECTIONS:
            raise ValueError(f"section de liste inconnue: {key!r}")
        heading, dims = LIST_SECTIONS[key]
        allowed = {f".sdd/stacks/{d}/" for d in dims}
        for candidate in paths:
            if not any(candidate.startswith(prefix) for prefix in allowed):
                raise ValueError(
                    f"{candidate!r} hors perimetre de ## {heading} "
                    f"(attendu: {', '.join(sorted(allowed))}*)"
                )
            if not (root / candidate).is_file():
                raise ValueError(f"stack inexistant sur disque: {candidate!r}")
        touched = patch_list_section(lines, heading, list(paths))
        if touched:
            changed.setdefault("activeStacks", []).append(key)

    for key, pairs in (patch.get("kv") or {}).items():
        if key not in KV_SECTIONS:
            raise ValueError(f"section cle/valeur inconnue: {key!r}")
        touched = patch_kv_section(
            lines, KV_SECTIONS[key], {k: str(v) for k, v in pairs.items()}
        )
        if touched:
            changed.setdefault("kv", []).extend(f"{key}.{t}" for t in touched)

    harness = patch.get("harness")
    if harness:
        touched = patch_harness(lines, harness)
        if touched:
            changed["harness"] = touched

    new_text = "\n".join(lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    # Re-parse avant écriture : un patch qui casserait le parseur du framework
    # ne doit jamais atteindre le disque (l'UI resterait cohérente, le pipeline
    # non — c'est exactement la dérive que ce module existe pour empêcher).
    parse_stack_config(new_text)

    if emit_text:
        return {
            "status": "unchanged" if new_text == text else "ok",
            "changed": changed,
            "path": str(path),
            "text": _restore(new_text, bom, newline),
        }
    if new_text == text:
        return {"status": "unchanged", "changed": {}, "path": str(path)}
    # newline="" : la restauration du style de fin de ligne est deja faite par
    # `_restore`. Laisser Python retraduire les sauts de ligne en os.linesep
    # reconvertirait un stack.md LF en CRLF, et le projet utilisateur verrait
    # ses 87 lignes marquees modifiees dans git pour un seul champ change.
    atomic_write_text(path, _restore(new_text, bom, newline), newline="")
    return {"status": "ok", "changed": changed, "path": str(path)}


# ─────────────────────────────────── CLI ───────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stack_config_api",
        description="Pont JSON lecture/ecriture pour workspace/stack/stack.md",
    )
    parser.add_argument("verb", choices=("read", "write", "catalog"))
    parser.add_argument("--root", help="racine projet (defaut : auto-detectee)")
    parser.add_argument("--stack-md", help="chemin explicite du stack.md")
    parser.add_argument(
        "--source-stdin", action="store_true",
        help="read : lit le texte du stack.md sur stdin au lieu du disque "
             "(mode editeur VSCode, document non sauvegarde)",
    )
    parser.add_argument(
        "--emit-text", action="store_true",
        help="write : retourne le texte resultant au lieu d'ecrire le "
             "fichier (mode editeur VSCode, cf. apply_patch)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else find_repo_root()
    path = Path(args.stack_md).resolve() if args.stack_md else stack_md_path(root)

    try:
        if args.verb == "read":
            source = sys.stdin.read() if args.source_stdin else None
            payload: dict[str, Any] = build_read_payload(
                root, path, source_text=source
            )
        elif args.verb == "catalog":
            payload = {"schemaVersion": 1, "catalog": build_catalog(root)}
        else:
            raw = sys.stdin.read()
            try:
                patch = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError as exc:
                print(
                    "ERROR: patch JSON illisible\n"
                    f"CAUSE: [INVALID_ARG] {exc}\n"
                    "FIX: envoyer un objet JSON valide sur stdin",
                    file=sys.stderr,
                )
                return EXIT_INVALID_INPUT
            payload = apply_patch(root, path, patch, emit_text=args.emit_text)
    except FileNotFoundError as exc:
        print(
            f"ERROR: stack_config_api {args.verb} failed\n"
            f"CAUSE: [NOT_FOUND] {exc}\n"
            "FIX: initialiser le projet (bootstrap SDD-Pro) avant d'ecrire",
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT
    except ValueError as exc:
        print(
            f"ERROR: stack_config_api {args.verb} failed\n"
            f"CAUSE: [INVALID_ARG] {exc}\n"
            "FIX: corriger la valeur cote UI puis reessayer",
            file=sys.stderr,
        )
        return EXIT_INVALID_INPUT
    except OSError as exc:
        print(
            f"ERROR: stack_config_api {args.verb} failed\n"
            f"CAUSE: [DISK] {exc}\n"
            "FIX: verifier les droits d'ecriture sur workspace/stack/",
            file=sys.stderr,
        )
        return EXIT_INFRA_ERROR

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
