#!/usr/bin/env python3
"""SDD_Pro v6: Implementation Readiness Gate (deterministic, 0 token).

Usage:
    python validate_readiness.py --feat-number {n}
    python validate_readiness.py --feat-number {n} --json

Output: Section 1 of the readiness report (markdown on stdout), or JSON.

Exit codes:
    0 = all validations pass (or only warnings)
    1 = at least one blocking error (decision NO-GO)

Migrated from .claude/scripts/validate-readiness.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.project_config import read_stack_md_text, section_body  # noqa: E402


VALID_DB_TYPES = (
    "none", "postgres", "sqlserver", "mysql", "sqlite", "oracle", "mariadb",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--feat-number", type=int, required=True)
    p.add_argument("--json", action="store_true")
    # Audit final 2026-06-07 (CRIT-3 closure) : flag `--post-dev` accepté
    # comme no-op signal explicit. Avant ce fix, `/sdd-full` STEP 4.7 invoquait
    # `/feat-validate {n} --json --post-dev` mais argparse rejetait `--post-dev`
    # (unrecognized arguments) → STEP 4.7 = dead branch. Le script auto-détecte
    # déjà le mode post-dev via `find workspace/output/src` (STEP 4.5 logic) ;
    # ce flag est donc un signal documentaire pour forcer le mode quand le code
    # est matérialisé. No-op interne — la détection reste basée sur la présence
    # disque de code matérialisé.
    p.add_argument("--post-dev", action="store_true",
                   help="Signal explicite mode post-dev (no-op : détection auto via présence code matérialisé)")
    return p.parse_args()


class Report:
    """Accumulator for passes / infos / warnings / errors.

    v6.10.5 (audit 2026-05-19) — added INFO level for advisory checks that
    must remain visible but should NOT downgrade the decision to WARN
    (which forces `/sdd-full --force`). Use when the check surfaces a
    legitimate design choice or a context-dependent observation rather
    than a defect (ex.: FEAT-level mockup, /feat-deepen recommended on
    moderately-complex FEAT).
    """

    def __init__(self) -> None:
        self.passes: list[dict[str, str]] = []
        self.infos: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []
        self.errors: list[dict[str, str]] = []

    def add_pass(self, id_: str, msg: str) -> None:
        self.passes.append({"id": id_, "message": msg})

    def add_info(self, id_: str, msg: str) -> None:
        self.infos.append({"id": id_, "message": msg})

    def add_warn(self, id_: str, msg: str) -> None:
        self.warnings.append({"id": id_, "message": msg})

    def add_err(self, id_: str, cause: str, fix: str) -> None:
        self.errors.append({"id": id_, "cause": cause, "fix": fix})

    @property
    def decision(self) -> str:
        if self.errors:
            return "NO-GO"
        if self.warnings:
            return "WARN"
        return "GO"


def read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def find_feat_file(feats_dir: Path, n: int) -> tuple[Path | None, str | None, list[Path]]:
    """Locate the FEAT file `{n}-*.md` ; return (file, name, all_matches)."""
    if not feats_dir.is_dir():
        return None, None, []
    files = sorted(feats_dir.glob(f"{n}-*.md"))
    if not files:
        return None, None, []
    if len(files) > 1:
        return None, None, files
    m = re.match(rf"^{n}-(.+)$", files[0].stem)
    return files[0], m.group(1) if m else None, files


def test_id_sequence(content: str, prefix: str, heading: str) -> dict[str, Any]:
    body = section_body(content, heading)
    if body is None:
        return {"skipped": True}
    ids = [int(m.group(1)) for m in re.finditer(rf"^- {prefix}-(\d+):", body, re.MULTILINE)]
    if not ids:
        return {"empty": True}
    counts: dict[int, int] = {}
    for i in ids:
        counts[i] = counts.get(i, 0) + 1
    duplicates = sorted(k for k, v in counts.items() if v > 1)
    sorted_ids = sorted(ids)
    expected = set(range(1, sorted_ids[-1] + 1))
    missing = sorted(expected - set(sorted_ids))
    return {
        "count":      len(ids),
        "ids":        sorted_ids,
        "duplicates": duplicates,
        "missing":    missing,
        "ok":         not duplicates and not missing,
    }


def get_all_ids(content: str, prefix: str, heading: str) -> list[str]:
    body = section_body(content, heading)
    if body is None:
        return []
    return [f"{prefix}-{m.group(1)}" for m in re.finditer(rf"^- {prefix}-(\d+):", body, re.MULTILINE)]


def get_covered_ids(content: str, prefix: str) -> set[str]:
    return {f"{prefix}-{m.group(1)}" for m in re.finditer(rf"{prefix}-(\d+)", content)}


def count_bullets(content: str, heading: str, id_prefix: str) -> int:
    body = section_body(content, heading)
    if body is None:
        return SUCCESS
    return len(re.findall(rf"(?m)^\s*-\s+{id_prefix}-\d+\s*:", body))


def count_oos_bullets(content: str) -> int:
    body = section_body(content, "Out of Scope")
    if body is None:
        return SUCCESS
    return len(re.findall(r"(?m)^\s*-\s+\S", body))


_DB_KEYS_REQUIRED = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")


def _parse_kv_block(body: str) -> dict[str, str]:
    """Parse `- KEY: VALUE` / `- KEY:VALUE` / `- KEY=VALUE` lines from a section body.

    Skips path-like lines (e.g. `- .claude/stacks/auth/azure-ad.md`).
    Tolerates optional spaces around the separator and surrounding quotes.
    Accepts both `:` (canonical) and `=` (legacy / shell-style) as KV separators.
    """
    result: dict[str, str] = {}
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("-"):
            continue
        s = s[1:].strip()
        if s.startswith(".claude/") or s.startswith("#") or not s:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*[:=]\s*(.*)$", s)
        if not m:
            continue
        result[m.group(1).strip()] = m.group(2).strip()
    return result


def detect_db_type(stack_content: str) -> str:
    """Lookup DatabaseType — priority: `## Active Database` block, fallback Project Config (legacy)."""
    body = section_body(stack_content, "Active Database")
    if body is not None:
        kv = _parse_kv_block(body)
        if "DatabaseType" in kv:
            return kv["DatabaseType"]
    # Legacy fallback (pre-2026-05-14): DatabaseType in ## Project Config
    m = re.search(r"(?im)^\s*DatabaseType\s*:\s*(\S+)", stack_content)
    return m.group(1).strip() if m else ""


def get_active_db_kv(stack_content: str) -> dict[str, str]:
    body = section_body(stack_content, "Active Database")
    return _parse_kv_block(body) if body is not None else {}


def get_active_auth_kv(stack_content: str) -> dict[str, str]:
    body = section_body(stack_content, "Active Auth Specs")
    return _parse_kv_block(body) if body is not None else {}


def has_auth_stack_listed(stack_content: str) -> bool:
    body = section_body(stack_content, "Active Auth Specs")
    if body is None:
        return False
    return bool(re.search(r"(?m)^\s*-\s+\.claude/stacks/auth/", body))


def detect_active_auth_stack(stack_content: str) -> str | None:
    """Return the relative path to the auth stack MD listed in `## Active Auth Specs`.

    Returns e.g. `.claude/stacks/auth/auth-local.md` or `.claude/stacks/auth/azure-ad.md`,
    or None if the section is absent / contains no stack path. The auth stack MD is
    the source of truth for its own required config keys (cf. extract_required_auth_keys).
    """
    body = section_body(stack_content, "Active Auth Specs")
    if body is None:
        return None
    m = re.search(r"(?m)^\s*-\s+(\.claude/stacks/auth/[\w\-]+\.md)\s*$", body)
    return m.group(1) if m else None


def extract_required_auth_keys(auth_stack_content: str) -> list[str]:
    """Parse `### Cles de configuration obligatoires` section of an auth stack MD.

    Each auth stack MD (auth-local.md, azure-ad.md, ...) declares its own required
    config keys under that heading. This makes the readiness validator source-driven:
    no hardcoded AZ_*/AUTH_JWT_*/etc. The validator just reads whatever the active
    auth stack declares.

    Returns the list of keys whose bullet description does NOT contain "optionnel"
    or "optional" (case-insensitive). Returns [] if the section is missing or empty.
    """
    m = re.search(
        r"(?ms)^###\s+Cl[éeè]?s?\s+de\s+configuration\s+obligatoires.*?\n"
        r"(.*?)"
        r"(?=^###\s+|^##\s+|\Z)",
        auth_stack_content,
    )
    if not m:
        return []
    section = m.group(1)

    keys: list[str] = []
    current_key: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_body
        if current_key:
            text = " ".join(current_body).lower()
            if "optionnel" not in text and "optional" not in text:
                keys.append(current_key)
        current_key = None
        current_body = []

    for line in section.splitlines():
        bm = re.match(r"^-\s+([A-Z][A-Z0-9_]+)\s*:(.*)$", line)
        if bm:
            flush()
            current_key = bm.group(1)
            current_body = [bm.group(2)]
            continue
        if current_key is not None and re.match(r"^\s+\S", line):
            current_body.append(line.strip())
            continue
        flush()
    flush()
    return keys


def detect_deepen_run(const_content: str) -> bool:
    m = re.search(r"(?ms)^##\s+7\.\s+Risques.+?(?=^##\s+8\.|\Z)", const_content)
    if not m:
        return False
    section7 = m.group(0)
    real_bullets = re.findall(
        r"(?m)^\s*-\s+(?!\s*(?:<|Etendu par|Vide tant))",
        section7,
    )
    return len(real_bullets) >= 1


def main() -> int:
    args = parse_args()
    root = repo_root()
    feats_dir = root / "workspace" / "input" / "feats"
    us_dir = root / "workspace" / "output" / "us"
    ui_dir = root / "workspace" / "input" / "ui"
    stack_path = root / "workspace" / "input" / "stack" / "stack.md"
    const_path = root / "workspace" / "output" / ".sys" / ".context" / "constitution.md"

    rep = Report()

    # 0. Locate FEAT
    feat_file, feat_name, all_feat_files = find_feat_file(feats_dir, args.feat_number)
    if not all_feat_files:
        rep.add_err(
            "FEAT-MISSING",
            f"Aucun fichier workspace/input/feats/{args.feat_number}-*.md trouve",
            "Creer la FEAT via /feat-generate ou la deposer manuellement",
        )
    elif feat_file is None and len(all_feat_files) > 1:
        rep.add_err(
            "FEAT-DUPLICATE",
            f"Plusieurs fichiers commencent par {args.feat_number}-",
            f"Renommer pour qu'un seul fichier ait le prefixe {args.feat_number}-",
        )

    feat_content = read_text_safe(feat_file) if feat_file else ""

    # 1.1 ID sequence coherence
    if feat_file:
        for prefix, section, required in [
            ("SFD", "Functional Needs", True),
            ("FD",  "Functional Deliverables", True),
            ("BR",  "Business Rules", False),
            ("AC",  "Acceptance Criteria", False),
        ]:
            r = test_id_sequence(feat_content, prefix, section)
            if r.get("skipped"):
                if required:
                    rep.add_err(
                        f"{prefix}-SECTION",
                        f"Section ## {section} absente de la FEAT",
                        f"Ajouter la section ## {section} dans workspace/input/feats/{feat_file.name}",
                    )
                continue
            if r.get("empty"):
                if required:
                    rep.add_warn(f"{prefix}-EMPTY", f"Section ## {section} presente mais vide ou sans IDs {prefix}-N")
                continue
            if r.get("ok"):
                rep.add_pass(f"{prefix}-IDS", f"{prefix}-N : {r['count']} IDs continus, pas de doublons")
            else:
                if r["duplicates"]:
                    rep.add_err(
                        f"{prefix}-DUPLICATE",
                        f"IDs dupliques : {prefix}-{', '.join(str(d) for d in r['duplicates'])}",
                        f"Renumeroter les bullets dupliques dans ## {section}",
                    )
                if r["missing"]:
                    rep.add_warn(
                        f"{prefix}-GAP",
                        f"IDs manquants dans ## {section} : {prefix}-{', '.join(str(d) for d in r['missing'])} "
                        "(numerotation discontinue)",
                    )

    # 1.2 Traceability FEAT -> US
    us_files: list[Path] = []
    if us_dir.is_dir():
        us_files = sorted(us_dir.glob(f"{args.feat_number}-*.md"))

    if feat_file and not us_files:
        rep.add_err(
            "US-MISSING",
            f"Aucune US trouvee (workspace/output/us/{args.feat_number}-*.md)",
            f"Lancer /us-generate {args.feat_number}",
        )
    elif feat_file and us_files:
        all_us_content = "\n\n".join(read_text_safe(f) for f in us_files)
        for prefix, section, required in [
            ("SFD", "Functional Needs", True),
            ("FD",  "Functional Deliverables", True),
            ("BR",  "Business Rules", False),
            ("AC",  "Acceptance Criteria", False),
        ]:
            declared = get_all_ids(feat_content, prefix, section)
            if not declared:
                continue
            covered = get_covered_ids(all_us_content, prefix)
            orphans = [d for d in declared if d not in covered]
            if not orphans:
                rep.add_pass(
                    f"{prefix}-COVERAGE",
                    f"Tous les {prefix}-N de la FEAT sont couverts par au moins une US ({len(declared)} IDs)",
                )
            else:
                msg = f"{prefix} non couverts par les US : {', '.join(orphans)}"
                if required:
                    rep.add_err(
                        f"{prefix}-ORPHAN",
                        msg,
                        "Ajouter ces IDs au Covers d'une US ou completer les ACs",
                    )
                else:
                    rep.add_warn(f"{prefix}-ORPHAN", f"{msg} (non bloquant)")

    # 1.3 Stack coherence
    stack_content = ""
    if not stack_path.is_file():
        rep.add_err(
            "STACK-MISSING",
            "workspace/input/stack/stack.md absent",
            "Creer workspace/input/stack/stack.md avec sections Active Tech Specs / Project Config",
        )
    else:
        # v7.0.0-alpha (audit CRIT-2) : cached mtime-keyed read.
        stack_content = read_stack_md_text(root) or ""
        active_tech_body = section_body(stack_content, "Active Tech Specs") or ""
        # SSoT 2026-06-06 R3 : utiliser stack_validator au lieu de regex locale.
        # Construire dict catégorisé depuis Active Tech Specs (lignes - .claude/stacks/X/Y.md)
        stacks_dict: dict[str, str | None] = {
            "backend": None, "frontend": None, "ui": None, "auth": None,
            "fullstack": None, "mobiles": None,
        }
        for m in re.finditer(r"^\s*-\s*\.claude/stacks/(\w+)/([\w-]+)\.md", active_tech_body, re.MULTILINE):
            cat, stack_id = m.group(1), m.group(2)
            if cat in stacks_dict and stacks_dict[cat] is None:
                stacks_dict[cat] = stack_id

        try:
            from sdd_lib.stack_validator import validate_active_stacks_coherence
            coherence_err = validate_active_stacks_coherence(stacks_dict)
        except ImportError:
            coherence_err = None  # degradation gracieuse

        if coherence_err:
            rep.add_err(
                "STACK-INCOHERENT",
                f"{coherence_err['code']}: {coherence_err['message']}",
                "Corriger workspace/input/stack/stack.md (un seul AppType actif : fullstack OU back+front OU mobile).",
            )
        else:
            has_backend = stacks_dict["backend"] is not None
            has_frontend = stacks_dict["frontend"] is not None
            has_fullstack = stacks_dict["fullstack"] is not None
            has_mobiles = stacks_dict["mobiles"] is not None
            rep.add_pass(
                "STACK-ACTIVE",
                f"Stacks actifs : backend={has_backend}, frontend={has_frontend}, fullstack={has_fullstack}, mobiles={has_mobiles}",
            )

        # v7.0.0-alpha Sprint 1.3 (2026-06-06) — Required Stack validation
        # FEAT declares ## Required Stack ; compare with stacks_dict (extended
        # with ui/qa/auth/archi which aren't in the original 6-cat dict).
        # Mismatch = WARN (not ERR — bench scenarios legitimate, but signal it).
        extended_stacks: dict[str, str | None] = dict(stacks_dict)
        for extra_cat in ("qa", "archi"):
            extended_stacks.setdefault(extra_cat, None)
        # Refresh ui+auth+qa+archi from full stack content (Active UI/QA/Auth/Architecture Specs)
        for cat_header, cat_key in (
            ("Active UI Specs", "ui"),
            ("Active QA Specs", "qa"),
            ("Active Auth Specs", "auth"),
            ("Active Architecture Pattern", "archi"),
        ):
            body = section_body(stack_content, cat_header) or ""
            m = re.search(r"^\s*-\s*\.claude/stacks/(\w+)/([\w-]+)\.md", body, re.MULTILINE)
            if m and extended_stacks.get(cat_key) is None:
                extended_stacks[cat_key] = m.group(2)

        required_body = section_body(feat_content, "Required Stack") or ""
        if required_body.strip():
            required_stacks: dict[str, str] = {}
            for m in re.finditer(r"^\s*-\s*(\w+)\s*:\s*([\w-]+)", required_body, re.MULTILINE):
                cat, sid = m.group(1).strip().lower(), m.group(2).strip().lower()
                if cat in extended_stacks:
                    required_stacks[cat] = sid

            mismatches: list[str] = []
            for cat, sid in required_stacks.items():
                active = extended_stacks.get(cat)
                if sid == "none":
                    if active is not None:
                        mismatches.append(
                            f"{cat}: FEAT exige 'none' mais stack.md active '{active}'"
                        )
                else:
                    if active is None:
                        mismatches.append(
                            f"{cat}: FEAT exige '{sid}' mais aucun stack {cat}/* actif"
                        )
                    elif active != sid:
                        mismatches.append(
                            f"{cat}: FEAT exige '{sid}' mais stack.md active '{active}'"
                        )

            if mismatches:
                rep.add_warn(
                    "REQUIRED-STACK-MISMATCH",
                    "FEAT ## Required Stack ne correspond pas à stack.md ## Active Tech Specs : "
                    + " ; ".join(mismatches) + ". "
                    "Aligner stack.md OU corriger la FEAT (cas bench multi-stack légitime).",
                )
            else:
                rep.add_pass(
                    "REQUIRED-STACK-MATCH",
                    f"FEAT ## Required Stack ({len(required_stacks)} catégories) "
                    f"matche stack.md ## Active Tech Specs",
                )
        else:
            rep.add_info(
                "REQUIRED-STACK-ABSENT",
                "FEAT n'a pas de ## Required Stack — drift stack non détectable "
                "(non bloquant ; ajouter pour FEATs futures)",
            )

        pc_body = section_body(stack_content, "Project Config") or ""
        # v6.10.2: accept either AppName (legacy) or FrontendName (preferred)
        if re.search(r"(?m)(AppName|FrontendName)\s*:\s*\S", pc_body):
            rep.add_pass("PROJECT-CONFIG", "Project Config rempli (AppName/FrontendName defini)")
        else:
            rep.add_err(
                "PROJECT-CONFIG-MISSING",
                "Project Config absent ou AppName/FrontendName non defini",
                "Ajouter ## Project Config avec FrontendName: <NomProjet> (ou AppName: legacy)",
            )

        db_type = detect_db_type(stack_content)
        if db_type:
            if db_type.lower() in VALID_DB_TYPES:
                rep.add_pass("DB-TYPE", f"DatabaseType valide : {db_type}")
            else:
                rep.add_warn(
                    "DB-TYPE-UNKNOWN",
                    f"DatabaseType '{db_type}' non reconnu (attendu : {', '.join(VALID_DB_TYPES)})",
                )
        else:
            rep.add_warn("DB-TYPE-MISSING", "DatabaseType non defini dans ## Active Database de stack.md (assume : none)")

        # Active Database completeness (depuis 2026-05-14)
        if db_type and db_type.lower() != "none":
            db_kv = get_active_db_kv(stack_content)
            missing_db = [k for k in _DB_KEYS_REQUIRED if not db_kv.get(k)]
            if not db_kv:
                rep.add_err(
                    "DB-ACTIVE-MISSING",
                    "Bloc ## Active Database absent ou vide dans stack.md alors que DatabaseType != none",
                    "Ajouter ## Active Database avec les 5 cles DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD",
                )
            elif missing_db:
                rep.add_err(
                    "DB-KEYS-MISSING",
                    f"Cles manquantes ou vides dans ## Active Database : {', '.join(missing_db)}",
                    "Renseigner les valeurs dans workspace/input/stack/stack.md ## Active Database",
                )
            else:
                rep.add_pass("DB-KEYS", "## Active Database complet (5 cles DB_* presentes)")

        # Active Auth Specs completeness (dynamique depuis 2026-05-14 — source de verite =
        # stack auth MD reference dans stack.md, jamais hardcode dans ce script)
        auth_stack_rel = detect_active_auth_stack(stack_content)
        if auth_stack_rel:
            auth_kv = get_active_auth_kv(stack_content)
            auth_stack_path = root / auth_stack_rel
            stack_id = Path(auth_stack_rel).stem
            if not auth_stack_path.is_file():
                rep.add_err(
                    "AUTH-STACK-MISSING",
                    f"Stack auth refere dans ## Active Auth Specs introuvable : {auth_stack_rel}",
                    f"Verifier le chemin dans workspace/input/stack/stack.md ## Active Auth Specs",
                )
            else:
                auth_stack_content = read_text_safe(auth_stack_path)
                required_keys = extract_required_auth_keys(auth_stack_content)
                if not required_keys:
                    rep.add_warn(
                        "AUTH-KEYS-UNDETECTED",
                        f"Impossible d'extraire les cles obligatoires de {auth_stack_rel} - "
                        "verifier la section '### Cles de configuration obligatoires'. "
                        "Validation des cles ## Active Auth Specs sautee.",
                    )
                else:
                    missing_auth = [k for k in required_keys if not auth_kv.get(k)]
                    if missing_auth:
                        rep.add_err(
                            "AUTH-KEYS-MISSING",
                            f"Cles manquantes ou vides dans ## Active Auth Specs ({stack_id}) : "
                            f"{', '.join(missing_auth)}",
                            f"Renseigner les valeurs dans workspace/input/stack/stack.md "
                            f"## Active Auth Specs (cles obligatoires declarees par {auth_stack_rel} : "
                            f"{', '.join(required_keys)})",
                        )
                    else:
                        rep.add_pass(
                            "AUTH-KEYS",
                            f"## Active Auth Specs complet pour {stack_id} "
                            f"({len(required_keys)} cles requises presentes : {', '.join(required_keys)})",
                        )

    # 1.4 US ↔ HTML mockups
    # v6.10.5 (audit 2026-05-19) — distingue 2 cas :
    #   - FEAT-level mockup (stem `{n}-Name.html`, sans `-{m}-`) → INFO :
    #     design exploration légitime couvrant 1+ US. Pratique courante
    #     du UX designer qui livre AVANT le découpage PO.
    #   - US-level orphan (stem `{n}-{m}-Name.html` mais pas d'US matchant)
    #     → WARN : genuine mismatch, à renommer ou retirer.
    html_files: list[Path] = []
    if ui_dir.is_dir():
        html_files = sorted(ui_dir.glob(f"{args.feat_number}-*.html"))
    if html_files and us_files:
        us_basenames = {f.stem for f in us_files}
        us_level_re = re.compile(rf"^{args.feat_number}-\d+-")
        feat_level_orphans: list[str] = []
        us_level_orphans: list[str] = []
        for h in html_files:
            if h.stem in us_basenames:
                continue
            if us_level_re.match(h.stem):
                us_level_orphans.append(h.name)
            else:
                feat_level_orphans.append(h.name)
        if not feat_level_orphans and not us_level_orphans:
            rep.add_pass("HTML-US-MATCH", f"Tous les mockups HTML ({len(html_files)}) ont une US correspondante")
        else:
            if feat_level_orphans:
                rep.add_info(
                    "HTML-FEAT-LEVEL",
                    f"Mockups FEAT-level (non bloquant) : {', '.join(feat_level_orphans)} "
                    f"— design exploration couvrant 1+ US (renommer en `{args.feat_number}-{{m}}-...` si vise 1 US specifique)",
                )
            if us_level_orphans:
                rep.add_warn(
                    "HTML-ORPHAN",
                    f"Mockups US-level sans US correspondante : {', '.join(us_level_orphans)} (renommer ou retirer)",
                )

    # 1.5 Constitution
    const_content = ""
    if const_path.is_file():
        rep.add_pass("CONST-EXISTS", "Constitution presente (workspace/output/.sys/.context/constitution.md)")
        const_content = read_text_safe(const_path)
        if feat_file and feat_name:
            if re.search(re.escape(f"{args.feat_number}-{feat_name}"), const_content):
                rep.add_pass(
                    "CONST-FEAT-LINKED",
                    f"FEAT {args.feat_number}-{feat_name} referencee dans la constitution",
                )
            else:
                rep.add_warn(
                    "CONST-FEAT-NOTLINKED",
                    f"FEAT {args.feat_number}-{feat_name} non referencee dans constitution.md section 3 - "
                    "l'agent PO devrait l'ajouter au prochain run",
                )
    else:
        rep.add_warn(
            "CONST-MISSING",
            "Constitution absente (workspace/output/.sys/.context/constitution.md) - "
            "projet pre-v3 ou /feat-generate non utilise. Non bloquant.",
        )

    # 1.6 feat-deepen complexity check
    if feat_file:
        sfd_count = count_bullets(feat_content, "Functional Needs", "SFD")
        br_count = count_bullets(feat_content, "Business Rules", "BR")
        ac_count = count_bullets(feat_content, "Acceptance Criteria", "AC")
        oos_count = count_oos_bullets(feat_content)
        db_type = detect_db_type(stack_content) if stack_content else ""
        has_db = db_type and db_type != "none"

        score = 0
        reasons: list[str] = []
        if sfd_count >= 10:
            score += 1
            reasons.append(f"{sfd_count} SFD")
        if br_count >= 8:
            score += 1
            reasons.append(f"{br_count} BR")
        if ac_count >= 15:
            score += 1
            reasons.append(f"{ac_count} AC")
        if has_db:
            score += 1
            reasons.append(f"DatabaseType={db_type}")
        if oos_count >= 5:
            score += 1
            reasons.append(f"{oos_count} Out-of-Scope")

        # v7.0.0 (audit 2026-05-20 §6.3) — revert leniency v6.10.5.
        # Threshold lu depuis config layered (FeatDeepenThreshold, default 3).
        # FeatDeepenMode pilote la sévérité : warn (default) ou strict (NO-GO).
        try:
            from sdd_lib.layered_config import read_layered_config
            _cfg = read_layered_config()
            _thresh = int(_cfg.get("FeatDeepenThreshold") or 3)
            _mode = str(_cfg.get("FeatDeepenMode") or "warn").lower()
        except Exception:
            _thresh, _mode = 3, "warn"
        is_complex = score >= _thresh
        deepen_run = detect_deepen_run(const_content) if const_content else False

        if is_complex:
            if deepen_run:
                rep.add_pass(
                    "FEAT-DEEPEN-DONE",
                    f"FEAT complexe (score {score}/5: {', '.join(reasons)}) et /feat-deepen execute "
                    "(constitution §7 peuplee)",
                )
            else:
                # v7.0.0 — sévérité pilotée par FeatDeepenMode
                if _mode == "strict":
                    rep.add_err(
                        "FEAT-DEEPEN-REQUIRED",
                        f"FEAT complexe (score {score}/{_thresh}: {', '.join(reasons)}) sans elicitation",
                        f"executer `/feat-deepen {args.feat_number}` puis relancer "
                        f"/feat-validate (idempotent). Bypass : FeatDeepenMode=warn ou off.",
                    )
                elif _mode == "warn":
                    rep.add_warn(
                        "FEAT-DEEPEN-RECOMMENDED",
                        f"FEAT complexe (score {score}/{_thresh}: {', '.join(reasons)}). "
                        f"`/feat-deepen {args.feat_number}` recommande pour identifier "
                        "risques/hypotheses avant /dev-run.",
                    )
                else:  # off
                    rep.add_info(
                        "FEAT-DEEPEN-RECOMMENDED",
                        f"FEAT complexe (score {score}/{_thresh}). /feat-deepen disponible "
                        "(FeatDeepenMode=off, non bloquant).",
                    )
        else:
            rep.add_pass(
                "FEAT-COMPLEXITY-LOW",
                f"FEAT simple (score {score}/5) - /feat-deepen optionnel",
            )

        # 1.7 v7.0.0 anti-GIGO — quantified goal + non-functional constraints
        # Check that the new structured fields from feat.template.md v7 are
        # filled (not just empty/absent). WARN only — backward-compat with
        # FEATs written pre-v7.0.0. NO-GO bypass via Project Config flag
        # `FeatAntiGigoMode: off`.
        qg_body = section_body(feat_content, "Quantified Goal") or ""
        nfc_body = section_body(feat_content, "Non-Functional Constraints") or ""

        if not qg_body.strip():
            rep.add_warn(
                "FEAT-NO-QUANTIFIED-GOAL",
                "Section `## Quantified Goal` absente (v7.0.0 anti-GIGO). "
                "Une FEAT senior doit declarer Metric/Target/Deadline mesurables. "
                "Ajouter la section ou ecrire `<a preciser>` explicite. Non bloquant (WARN).",
            )
        elif "<a preciser>" in qg_body.lower() or "<à préciser>" in qg_body.lower():
            rep.add_info(
                "FEAT-QUANTIFIED-GOAL-TBD",
                "## Quantified Goal contient `<a preciser>` - la lacune est tracee (OK), "
                "completer avant /dev-run pour eviter GIGO.",
            )

        if not nfc_body.strip():
            rep.add_warn(
                "FEAT-NO-NFC",
                "Section `## Non-Functional Constraints` absente (v7.0.0 anti-GIGO). "
                "Champs requis : Volume, Performance, Retention, Compliance, Integration, "
                "Degraded mode. Ecrire `n/a` explicitement si non applicable.",
            )

    # Output
    decision = rep.decision
    exit_code = FAIL_FAST if rep.errors else SUCCESS

    if args.json:
        result = {
            "spec_number": args.feat_number,
            "spec_name":   feat_name,
            "decision":    decision,
            "errors":      rep.errors,
            "warnings":    rep.warnings,
            "infos":       rep.infos,
            "passes":      rep.passes,
            "timestamp":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("## 1. Validations deterministes (Python)")
        print()
        print(f"**FEAT** : {args.feat_number}-{feat_name}")
        print(f"**Decision deterministe** : {decision}")
        print(f"**Passes** : {len(rep.passes)} | **Infos** : {len(rep.infos)} | "
              f"**Warnings** : {len(rep.warnings)} | **Errors** : {len(rep.errors)}")
        print()
        if rep.passes:
            print("### Validations passees")
            for p in rep.passes:
                print(f"- [PASS] {p['id']} : {p['message']}")
            print()
        if rep.infos:
            print("### Infos (non bloquant)")
            for i in rep.infos:
                print(f"- [INFO] {i['id']} : {i['message']}")
            print()
        if rep.warnings:
            print("### Warnings")
            for w in rep.warnings:
                print(f"- [WARN] {w['id']} : {w['message']}")
            print()
        if rep.errors:
            print("### Erreurs bloquantes")
            for e in rep.errors:
                print(f"- [FAIL] {e['id']}")
                print(f"  - CAUSE : {e['cause']}")
                print(f"  - FIX   : {e['fix']}")
            print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
