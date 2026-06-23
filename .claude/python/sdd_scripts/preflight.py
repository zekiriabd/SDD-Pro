#!/usr/bin/env python3
"""SDD_Pro HARD-GATE pre-flight for dev-backend / dev-frontend (Phase A + B).

Deterministic, 0 token LLM. Externalises checks A1-A4 + B1-B5.

Usage:
    python preflight.py --family backend  --arg "1-2"
    python preflight.py --family frontend --arg "1-2:plan"

Output: single JSON line on stdout.

Exit codes:
    0 = OK (or WARN-only if PlanOnly and project file absent)
    1 = ERROR (at least 1 critical precondition failed)

Migrated from .claude/scripts/preflight.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.markdown_io import section_body  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.project_config import read_stack_md_text  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--family", required=True, choices=["backend", "frontend"])
    p.add_argument("--arg", required=True)
    p.add_argument("--workspace-root", default=None)
    return p.parse_args()


@functools.lru_cache(maxsize=16)
def _stack_id_pattern(category: str) -> re.Pattern[str]:
    """Cache per-category compiled regex (audit mineur #2 v7.0.0-alpha 2026-06-05).

    Was rebuilt on every get_active_ids call ; now compiled once per category.
    LRU cache bounded to 16 entries (more than enough — only ~8 categories exist).
    """
    return re.compile(rf"\.claude/stacks/{re.escape(category)}/([\w-]+)\.md")


def get_active_ids(block: str, category: str) -> list[str]:
    """Extract stack ids referenced under `## Active …` block for a given category.

    Skips lines commented with `#` (after leading whitespace), e.g.
    `# - .claude/stacks/archi/ddd.md`.
    """
    ids: list[str] = []
    pattern = _stack_id_pattern(category)
    for line in block.splitlines():
        # Skip commented lines (leading `#`, ignoring whitespace)
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        m = pattern.search(line)
        if m:
            ids.append(m.group(1))
    return ids


def extract_section(text: str, heading: str) -> str:
    """Extract content between `## {heading}` and next `## ` (or EOF).

    v7.0.0-alpha (audit CRIT-3) : thin adapter over `sdd_lib.markdown_io.section_body`
    that returns ``""`` instead of ``None`` when the section is absent
    (preserves call-site expectations using ``block.strip()`` truth tests).
    Heading is now a plain string (regex-escaped internally) — the legacy
    signature accepting raw regex was unused outside this module.
    """
    return section_body(text, heading) or ""


# v6.7.5 — Active App Type detection (legacy explicit values)
# v6.7.7 — auto-detection from declared stacks (PREFERRED).
# Legacy `mobile-react-native` / `mobile-maui` accepted but translated to
# `back-front` + frontendKind=mobile. Deprecation WARN emitted if explicit
# AppType differs from auto-detected.
VALID_APP_TYPES = {"back-front", "fullstack", "mobile-react-native", "mobile-maui"}
LEGACY_MOBILE_APP_TYPES = {"mobile-react-native", "mobile-maui"}


def get_explicit_app_type(stack_content: str) -> str | None:
    """Read explicit `## Active App Type` / `AppType: <X>` if declared.

    Returns the raw value (validated) or None if absent. Used for
    backward-compat reconciliation with auto-detection (v6.7.7+).
    Invalid value → None (errored upstream by reconcile).
    """
    block = extract_section(stack_content, "Active App Type")
    if not block.strip():
        return None
    m = re.search(r"(?m)^\s*AppType\s*:\s*([\w-]+)", block)
    if m:
        val = m.group(1).strip()
        return val if val in VALID_APP_TYPES else None
    return None


def detect_app_type_auto(
    be_ids: list[str], fe_ids: list[str], fs_ids: list[str], mobile_ids: list[str]
) -> tuple[str, str | None]:
    """Auto-detect (appType, frontendKind) from declared stack categories.

    Rules (v6.7.7+):
      - any fullstack/*  → ("fullstack", None)
      - any mobiles/*    → ("back-front", "mobile")
      - any frontend/*   → ("back-front", "web")
      - backend-only     → ("back-front", None)
      - empty            → ("back-front", None)   # errored downstream

    Mix detection (fullstack + backend/frontend/mobile) → reported by
    validate_stack_combo(). Here we still return fullstack as primary.
    """
    if fs_ids:
        return "fullstack", None
    if mobile_ids:
        return "back-front", "mobile"
    if fe_ids:
        return "back-front", "web"
    return "back-front", None


def validate_stack_combo(
    be_ids: list[str], fe_ids: list[str], fs_ids: list[str], mobile_ids: list[str]
) -> str | None:
    """Validate stack combo coherence. Return hint string if invalid, None otherwise.

    Forbidden mixes (v6.7.7+):
      - fullstack + (backend OR frontend OR mobile) → mutually exclusive
      - mobile + frontend (web) → choose one frontend kind
      - multiple fullstack → max 1
      - multiple mobile → max 1
    """
    if fs_ids and (be_ids or fe_ids or mobile_ids):
        return (
            "stack fullstack/* exclusif — supprimer backend/*, frontend/* "
            "et mobiles/* de ## Active Tech Specs"
        )
    if len(fs_ids) > 1:
        return f"un seul fullstack/* attendu, trouvé : {','.join(fs_ids)}"
    if mobile_ids and fe_ids:
        return (
            "frontend mobile et web déclarés simultanément — choisir un seul "
            "(commenter mobiles/* OU frontend/*)"
        )
    if len(mobile_ids) > 1:
        return f"un seul mobiles/* attendu, trouvé : {','.join(mobile_ids)}"
    return None


# v6.7.6 — Active Architecture Pattern detection
# v6.7.7 — prefer bullet `.md` syntax (consistent with ## Active Tech Specs)
VALID_ARCHI_PATTERNS = {"MVC", "DDD", "microservice"}
ARCHI_FILE_TO_PATTERN = {
    "mvc": "MVC",
    "ddd": "DDD",
    "microservice": "microservice",
}


def get_archi_pattern(stack_content: str) -> tuple[str, bool]:
    """Read `## Active Architecture Pattern` block. Returns (value, was_explicit).

    Two supported syntaxes (v6.7.7+) :

    1. Bullet `.md` (PREFERRED, consistent with other Active sections) :
       ```
       ## Active Architecture Pattern
       - .claude/stacks/archi/mvc.md
       # - .claude/stacks/archi/ddd.md
       ```

    2. Key-value (legacy v6.7.6) :
       ```
       ## Active Architecture Pattern
       ArchitecturePattern: MVC
       ```

    `was_explicit=True` if user declared it (any syntax), False if defaulted.
    Invalid value → returns ("INVALID:<raw>", True) so caller can ERROR.

    Multiple active archi/*.md → returns ("AMBIGUOUS:<csv>", True).

    Scope (v6.7.6+): applique UNIQUEMENT au back-front avec backend/* déclaré.
    Pour fullstack/ et mobiles/, ignoré (les stacks intègrent leur archi).
    """
    block = extract_section(stack_content, "Active Architecture Pattern")
    if not block.strip():
        return "MVC", False

    # Syntax 1: bullet .md (preferred)
    archi_files = get_active_ids(block, "archi")
    if archi_files:
        if len(archi_files) > 1:
            return f"AMBIGUOUS:{','.join(archi_files)}", True
        file_id = archi_files[0]
        if file_id in ARCHI_FILE_TO_PATTERN:
            return ARCHI_FILE_TO_PATTERN[file_id], True
        return f"INVALID:{file_id}", True

    # Syntax 2: key-value (legacy)
    m = re.search(r"(?m)^\s*ArchitecturePattern\s*:\s*(\S+)", block) or re.search(
        r"(?m)^\s*ArchiPattern\s*:\s*(\S+)", block
    )
    if m:
        val = m.group(1).strip()
        if val in VALID_ARCHI_PATTERNS:
            return val, True
        return f"INVALID:{val}", True

    return "MVC", False


# v6.10.5 (audit 2026-05-19) — experimental stack detection
# Two marker formats observed in the catalog :
#   - `Validation: 🟡 experimental [...]` (fullstack/*, mobiles/*, archi/microservice)
#   - YAML in `META:` block: `validation: experimental` (archi/ddd)
EXPERIMENTAL_HEADER_RE = re.compile(
    r"(?im)^(?:Validation\s*:\s*🟡\s*experimental|"
    r"\s+validation\s*:\s*experimental)",
)


def _is_experimental_stack(root: Path, category: str, stack_id: str) -> str | None:
    """Return the experimental tagline (1 line) if the stack `.md` header
    declares experimental status (either format), else None.

    Reads only the first ~40 lines of the .md file for performance.
    """
    path = root / ".claude" / "stacks" / category / f"{stack_id}.md"
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = "".join(fh.readline() for _ in range(40))
    except OSError:
        return None
    m = EXPERIMENTAL_HEADER_RE.search(head)
    if not m:
        return None
    # Capture the rest of the matched line (the "experimental" tagline).
    line_start = head.rfind("\n", 0, m.start()) + 1
    line_end = head.find("\n", m.end())
    tagline = head[line_start:line_end if line_end >= 0 else len(head)].strip()
    return tagline


def _active_archi_id(stack_content: str) -> str | None:
    """Extract the archi stack id (mvc|ddd|microservice) from the
    `## Active Architecture Pattern` block, if exactly one is set."""
    block = extract_section(stack_content, "Active Architecture Pattern")
    if not block or not block.strip():
        return None
    archi_files = get_active_ids(block, "archi")
    if len(archi_files) == 1:
        return archi_files[0]
    return None


def _check_experimental_stacks(
    *,
    root: Path,
    active: dict[str, list[str]],
    add_warn,
) -> None:
    """For each active stack id (per category), check its .md header for
    `Validation: 🟡 experimental` and emit a STACK_EXPERIMENTAL warning.

    `active` keys : backend | frontend | ui | auth | fullstack | mobiles.
    """
    for category, ids in active.items():
        for sid in ids:
            tagline = _is_experimental_stack(root, category, sid)
            if tagline is None:
                continue
            add_warn(
                "STACK_EXPERIMENTAL",
                f"stack actif `{category}/{sid}` marque experimental — "
                f"`{tagline}`. Combo non valide end-to-end SDD_Pro v6 ; "
                f"projets pilotes uniquement, supporte minimal.",
            )


def _check_feat_hash(
    *,
    us_path: Path,
    feat_number: int,
    root: Path,
    add_err,
    add_warn,
) -> None:
    """v7.0.0 audit P0 R2 — Verify FEAT hash inscribed in US frontmatter
    still matches current FEAT content.

    Frontmatter expected (v7.0.0 template) :
        Parent FEAT hash: sha256:{first 8 hex chars of sha256(feat_file)}

    Behavior :
      - Frontmatter absent (pre-v7 US)         → WARN [FEAT_HASH_LEGACY] (non-blocking)
      - FEAT file not found                    → ERR  [FEAT_NOT_FOUND]
      - Hash mismatch                          → ERR  [FEAT_HASH_MISMATCH] (blocking ; Tech Lead re-run /us-generate)
      - Hash match                             → silent OK
    """
    import hashlib

    # Parse Parent FEAT hash from US frontmatter (first ~20 lines)
    try:
        us_head = us_path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return  # Can't read US — A2 will catch it elsewhere
    # Audit C2 closure (2026-06-07) : label `Parent FEAT hash:` matched
    # case-insensitively on the `h` of `hash` (defense-in-depth — canonical
    # form is lowercase per us.template.md + po.md §STEP 8, but accept
    # `Hash`/`HASH` variants to avoid silent FEAT_HASH_LEGACY false
    # positives if a future template typo slips through).
    hash_match = re.search(
        r"^Parent FEAT [Hh][Aa][Ss][Hh]:\s*sha256:([0-9a-fA-F]{6,64})\s*$",
        us_head,
        re.MULTILINE,
    )
    if not hash_match:
        add_warn(
            "FEAT_HASH_LEGACY",
            f"US {us_path.name} sans `Parent FEAT hash:` (US pre-v7.0.0). "
            "Re-run /us-generate pour beneficier de la detection FEAT_HASH_MISMATCH.",
        )
        return

    expected_hash = hash_match.group(1).lower()[:8]

    # Locate FEAT file (glob workspace/input/feats/{n}-*.md)
    feats_dir = root / "workspace" / "input" / "feats"
    feat_files = sorted(feats_dir.glob(f"{feat_number}-*.md")) if feats_dir.is_dir() else []
    if not feat_files:
        add_err(
            "FEAT_NOT_FOUND",
            f"FEAT {feat_number} reference par {us_path.name} mais aucun "
            f"fichier workspace/input/feats/{feat_number}-*.md trouve.",
        )
        return
    if len(feat_files) > 1:
        add_err(
            "FEAT_AMBIGUOUS",
            f"plusieurs fichiers workspace/input/feats/{feat_number}-*.md trouves",
        )
        return

    feat_path = feat_files[0]
    try:
        actual_hash = hashlib.sha256(feat_path.read_bytes()).hexdigest()[:8]
    except OSError as e:
        add_warn(
            "FEAT_HASH_UNREADABLE",
            f"impossible de lire {feat_path.name} pour calculer sha256 ({e})",
        )
        return

    if expected_hash != actual_hash:
        add_err(
            "FEAT_HASH_MISMATCH",
            f"FEAT {feat_path.name} modifiee apres generation US {us_path.name} "
            f"(hash inscrit sha256:{expected_hash} != actuel sha256:{actual_hash}). "
            "Covers: potentiellement obsolete. "
            "FIX: re-run /us-generate {n} (idempotent) pour regenerer les US avec le nouveau hash, "
            "ou revert la modification FEAT.",
        )


def main() -> int:
    args = parse_args()
    root = Path(args.workspace_root).resolve() if args.workspace_root else repo_root()

    result: dict[str, object] = {
        "ok": True,
        "family": args.family,
        "n": None,
        "m": None,
        "planOnly": False,
        "name": None,
        "htmlPath": None,
        "appOrBackendName": None,
        "appType": "back-front",
        "frontendKind": None,        # v6.7.7+ : "web" | "mobile" | null
        "appTypeSource": "default",  # v6.7.7+ : "auto" | "explicit" | "default"
        "archiPattern": None,        # v6.7.7+ : None si appType != back-front
        "archiPatternExplicit": False,
        "activeStacks": {
            "backend": None, "frontend": None, "uiDs": None, "auth": None,
            "fullstack": None, "mobile": None,
        },
        "warnings": [],
        "errors": [],
    }

    def add_err(code: str, hint: str) -> None:
        result["errors"].append({"code": code, "hint": hint})  # type: ignore[union-attr]
        result["ok"] = False

    def add_warn(code: str, hint: str) -> None:
        result["warnings"].append({"code": code, "hint": hint})  # type: ignore[union-attr]

    # A1 — Argument regex
    m = re.match(r"^(\d+)-(\d+)(:plan)?$", args.arg)
    if not m:
        add_err("INVALID_ARG", rf"argument doit matcher ^\d+-\d+(:plan)?$ (recu: {args.arg})")
        print(json.dumps(result, separators=(",", ":")))
        return FAIL_FAST
    result["n"] = int(m.group(1))
    result["m"] = int(m.group(2))
    result["planOnly"] = bool(m.group(3))

    # A2 — US file exists & unique
    us_dir = root / "workspace" / "output" / "us"
    us_files: list[Path] = []
    if us_dir.is_dir():
        us_files = sorted(us_dir.glob(f"{result['n']}-{result['m']}-*.md"))
    if not us_files:
        add_err("US_NOT_FOUND", f"lancer /us-generate {result['n']} pour generer l'US")
    elif len(us_files) > 1:
        add_err(
            "US_AMBIGUOUS",
            f"plusieurs fichiers workspace/output/us/{result['n']}-{result['m']}-*.md trouves, "
            "n'en garder qu'un",
        )
    else:
        m_name = re.match(r"^\d+-\d+-(.+)$", us_files[0].stem)
        if m_name:
            result["name"] = m_name.group(1)

    # A2.bis — FEAT hash check (v7.0.0 audit fix 2026-05-20 — R2 P0)
    # Vérifie que le hash sha256 inscrit dans le frontmatter US
    # (`Parent FEAT hash: sha256:{8 hex}`) correspond toujours au contenu
    # actuel de la FEAT parente. Si mismatch → FEAT modifiée post-`/us-generate`
    # → Covers: potentiellement obsolète, refusé sans `--force`.
    # Bypass : `Parent FEAT hash:` absent du frontmatter (US pre-v7.0.0) →
    # WARN informationnel, non bloquant.
    if us_files and not result["errors"]:
        _check_feat_hash(
            us_path=us_files[0],
            feat_number=int(result["n"]),
            root=root,
            add_err=add_err,
            add_warn=add_warn,
        )

    # A3 — stack.md exists
    stack_path = root / "workspace" / "input" / "stack" / "stack.md"
    if not stack_path.is_file():
        add_err(
            "STACK_MISSING",
            "workspace/input/stack/stack.md absent — projet non initialise. "
            "FIX: lancer `python bootstrap.py` depuis la racine du repo "
            "(interactif, ~5 questions, ~30s). Cf. /sdd-bootstrap pour les options.",
        )
        print(json.dumps(result, separators=(",", ":")))
        return FAIL_FAST

    # A4 — HTML mockup unique (frontend only)
    if args.family == "frontend":
        ui_dir = root / "workspace" / "input" / "ui"
        html_files: list[Path] = []
        if ui_dir.is_dir():
            html_files = sorted(ui_dir.glob(f"{result['n']}-{result['m']}-*.html"))
        if len(html_files) > 1:
            add_err(
                "HTML_AMBIGUOUS",
                f"plusieurs fichiers workspace/input/ui/{result['n']}-{result['m']}-*.html, "
                "n'en garder qu'un",
            )
        elif len(html_files) == 1:
            result["htmlPath"] = normalize(html_files[0])

    # Read stack.md once (cached on (path, mtime_ns) — audit CRIT-2)
    stack_content = read_stack_md_text(root)
    if stack_content is None:
        add_err("STACK_READ_FAILED", "lecture stack.md impossible")
        print(json.dumps(result, separators=(",", ":")))
        return FAIL_FAST

    # A3.bis — stack.md is the raw template (placeholders not substituted)
    # Detect `{{Placeholder}}` patterns leftover from templates/stack.md.template.
    # Symptom of "user copy-pasted the template instead of running bootstrap.py".
    # Fail fast with an actionable pointer rather than a cryptic downstream error.
    if "{{" in stack_content and re.search(r"\{\{[A-Za-z][A-Za-z0-9_]*\}\}", stack_content):
        add_err(
            "STACK_MALFORMED",
            "workspace/input/stack/stack.md contient des placeholders `{{...}}` "
            "non substitues (template brut). "
            "FIX: lancer `python bootstrap.py` depuis la racine du repo pour "
            "rendre le template (interactif, ~5 questions). Cf. /sdd-bootstrap.",
        )
        print(json.dumps(result, separators=(",", ":")))
        return FAIL_FAST

    # B1 — Active Tech Specs / UI Specs / Auth Specs blocks
    tech_block = extract_section(stack_content, "Active Tech Specs")
    ui_block = extract_section(stack_content, "Active UI Specs")
    auth_block = extract_section(stack_content, "Active Auth Specs")

    be_ids = get_active_ids(tech_block, "backend")
    fe_ids = get_active_ids(tech_block, "frontend")
    ui_ids = get_active_ids(ui_block, "ui")
    auth_ids = get_active_ids(auth_block, "auth")
    fs_ids = get_active_ids(tech_block, "fullstack")
    mobile_ids = get_active_ids(tech_block, "mobiles")

    result["activeStacks"] = {
        "backend": ",".join(be_ids),
        "frontend": ",".join(fe_ids),
        "uiDs": ",".join(ui_ids),
        "auth": ",".join(auth_ids),
        "fullstack": ",".join(fs_ids),
        "mobile": ",".join(mobile_ids),
    }

    # B1.alpha — STACK_EXPERIMENTAL detection (v6.10.5, audit 2026-05-19)
    # Emit a WARN for each active stack marked `Validation: 🟡 experimental`
    # (or YAML META `validation: experimental`) in its `.md` header.
    # Mitigates "false advertising" risk : the framework advertises 28+
    # stacks but ~8 are Phase 2 / non-validés end-to-end. Source : audit
    # 2026-05-19 §6.
    archi_id = _active_archi_id(stack_content)
    _check_experimental_stacks(
        root=root,
        active={
            "backend":   be_ids,
            "frontend":  fe_ids,
            "ui":        ui_ids,
            "auth":      auth_ids,
            "fullstack": fs_ids,
            "mobiles":   mobile_ids,
            "archi":     [archi_id] if archi_id else [],
        },
        add_warn=add_warn,
    )

    # B1.bis — AppType auto-detection (v6.7.7+) avec reconcile explicit
    combo_err = validate_stack_combo(be_ids, fe_ids, fs_ids, mobile_ids)
    if combo_err:
        add_err("STACK_COMBO_INVALID", combo_err)

    auto_app_type, auto_frontend_kind = detect_app_type_auto(
        be_ids, fe_ids, fs_ids, mobile_ids
    )
    explicit_app_type = get_explicit_app_type(stack_content)

    if explicit_app_type is None:
        app_type = auto_app_type
        frontend_kind = auto_frontend_kind
        result["appTypeSource"] = "auto" if (be_ids or fe_ids or fs_ids or mobile_ids) else "default"
    else:
        # Legacy mobile-* → translate to back-front + mobile frontend kind
        if explicit_app_type in LEGACY_MOBILE_APP_TYPES:
            app_type = "back-front"
            frontend_kind = "mobile"
            add_warn(
                "APPTYPE_LEGACY_MOBILE",
                f"AppType: {explicit_app_type} déprécié (v6.7.7+) — supprimer "
                f"## Active App Type, le mobile est auto-détecté depuis "
                f"mobiles/*.md dans ## Active Tech Specs",
            )
        elif explicit_app_type != auto_app_type:
            # explicit declared but mismatched with stacks declared → ERROR
            add_err(
                "APPTYPE_MISMATCH",
                f"AppType: {explicit_app_type} explicite incohérent avec "
                f"stacks déclarés (auto-détecté : {auto_app_type}). "
                f"FIX: supprimer ## Active App Type (auto-détection) OU "
                f"aligner stacks avec AppType déclaré",
            )
            app_type = auto_app_type
            frontend_kind = auto_frontend_kind
        else:
            app_type = explicit_app_type
            frontend_kind = auto_frontend_kind
            add_warn(
                "APPTYPE_REDUNDANT",
                "## Active App Type redondant — supprimer le bloc, "
                "AppType est auto-détecté depuis ## Active Tech Specs (v6.7.7+)",
            )
        result["appTypeSource"] = "explicit"

    result["appType"] = app_type
    result["frontendKind"] = frontend_kind

    # B1.ter — ArchitecturePattern (v6.7.6+, scope back-front uniquement)
    archi_pattern_raw, archi_explicit = get_archi_pattern(stack_content)
    result["archiPatternExplicit"] = archi_explicit
    if archi_pattern_raw.startswith("INVALID:"):
        bad_val = archi_pattern_raw[len("INVALID:"):]
        add_err(
            "STACK_MALFORMED",
            f"## Active Architecture Pattern invalide : {bad_val}. "
            f"Valeurs autorisées : .claude/stacks/archi/{{mvc,ddd,microservice}}.md "
            f"(ou legacy `ArchitecturePattern: MVC|DDD|microservice`)",
        )
        result["archiPattern"] = None
    elif archi_pattern_raw.startswith("AMBIGUOUS:"):
        bad_val = archi_pattern_raw[len("AMBIGUOUS:"):]
        add_err(
            "STACK_MALFORMED",
            f"## Active Architecture Pattern ambigu : {bad_val}. "
            f"Choisir UN SEUL pattern (commenter les autres avec `# - `)",
        )
        result["archiPattern"] = None
    elif app_type == "back-front" and be_ids:
        # Apply pattern only when there's a separate backend stack to scaffold
        result["archiPattern"] = archi_pattern_raw
    else:
        # fullstack, mobile-only, frontend-only → pattern ignored
        result["archiPattern"] = None
        if archi_explicit:
            add_warn(
                "ARCHIPATTERN_IGNORED",
                f"## Active Architecture Pattern ignoré (appType={app_type}, "
                f"backend stack absent) — les fullstack/mobiles intègrent leur archi",
            )

    # B1.quater — Validation présence stacks selon famille
    if args.family == "backend":
        if app_type == "fullstack" and not fs_ids:
            add_err(
                "STACK_NOT_SELECTED",
                "aucun stack fullstack/*.md déclaré dans ## Active Tech Specs",
            )
        elif app_type == "back-front" and not be_ids:
            # back-front sans backend = mobile-only (frontend-only project)
            # → exit silencieux du dev-backend (gere en aval par l'agent)
            pass
    elif args.family == "frontend":
        if app_type == "fullstack" and not fs_ids:
            add_err(
                "STACK_NOT_SELECTED",
                "aucun stack fullstack/*.md déclaré dans ## Active Tech Specs",
            )
        elif app_type == "back-front" and not (fe_ids or mobile_ids):
            add_err(
                "STACK_NOT_SELECTED",
                "aucun frontend déclaré : ajouter frontend/*.md (web) ou mobiles/*.md (mobile) dans ## Active Tech Specs",
            )

    # B2 — Project Config field (BackendName or AppName)
    # v6.7.5+ : pour AppType=fullstack, les 2 families partagent AppName (projet unique).
    pc_block = extract_section(stack_content, "Project Config")
    if app_type == "fullstack":
        key_name = "AppName"
    elif app_type in ("mobile-react-native", "mobile-maui") and args.family == "frontend":
        key_name = "AppName"
    else:
        key_name = "BackendName" if args.family == "backend" else "AppName"
    pc_match = re.search(rf"(?m)^\s*{key_name}\s*:\s*(\S+)", pc_block)
    if pc_match:
        result["appOrBackendName"] = pc_match.group(1)
    else:
        add_err("STACK_MALFORMED", f"renseigner {key_name} dans ## Project Config")

    # B3 — Project CLAUDE.md present
    if result["appOrBackendName"]:
        proj_digest = (
            root / "workspace" / "output" / "src"
            / str(result["appOrBackendName"]) / "CLAUDE.md"
        )
        if not proj_digest.is_file():
            hint = f"lancer /dev-run avant /dev-{args.family} (ou bootstrap arch)"
            if result["planOnly"]:
                result["errors"].append(  # type: ignore[union-attr]
                    {"code": "STACK_DIGEST_MISSING_WARN", "hint": f"{hint} (WARN-only en mode :plan)"}
                )
            else:
                add_err("STACK_DIGEST_MISSING", hint)

    # B4 — project file (csproj/package.json/pyproject/build.gradle/angular.json)
    if result["appOrBackendName"]:
        proj_dir = root / "workspace" / "output" / "src" / str(result["appOrBackendName"])
        project_files: list[Path] = []
        if proj_dir.is_dir():
            for pat in ("*.csproj", "package.json", "pyproject.toml", "build.gradle.kts", "angular.json"):
                project_files.extend(proj_dir.glob(pat))
        if not project_files:
            hint = "lancer /dev-run (Phase A bootstrap projets)"
            if result["planOnly"]:
                result["errors"].append(  # type: ignore[union-attr]
                    {"code": "PROJECT_NOT_INIT_WARN", "hint": f"{hint} (WARN-only en mode :plan)"}
                )
            else:
                add_err("PROJECT_NOT_INIT", hint)

    # B5 — UI DS selected if HTML mockup present (frontend, back-front web only)
    # v6.7.5+ : skip pour fullstack/mobile-* (gerent leur UI en interne — NativeWind RN,
    # MAUI Resources/Styles, FMX StyleBook, Mustache CSS custom, Tailwind Next/Nuxt, Material Angular, Radzen Blazor)
    if (
        args.family == "frontend"
        and app_type == "back-front"
        and result.get("frontendKind") != "mobile"
        and result["htmlPath"]
        and not ui_ids
    ):
        add_err(
            "UI_DS_NOT_SELECTED",
            "decommenter un design system (radzen-blazor, shadcn, vuetify)",
        )

    print(json.dumps(result, separators=(",", ":")))
    return SUCCESS if result["ok"] else FAIL_FAST


if __name__ == "__main__":
    sys.exit(main())
