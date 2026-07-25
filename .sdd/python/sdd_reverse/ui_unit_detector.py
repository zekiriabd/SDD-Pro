"""ui_unit_detector.py — Pre-detect functional units from legacy pages.

Per design doc D2 (chunking fin) :
    - Grid CRUD → 1 unit
    - Form (login, edit) → 1 unit
    - Menu → 1 unit
    - Wizard multi-step → 1 unit
    - Standalone confirm modal → 0 unit

Public API:
    detect_units(pages, scan_result, signatures) -> list[dict]

Output: list of {label, suggestedName, language, kind, evidenceFiles,
                  entities, confidenceEstimate, rationale}

Heuristic-based, conservative (over-merging is preferred to over-splitting —
the reverse extraction ladder can refine later).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import decode_text, normalize_bytes


# Default home-page filename stems recognised across western locales.
# Identifier stays canonical English (`Home`) — only the matching is
# multilingual. The display label is i18n'd separately by
# `_label_from_kind_and_name` (FR by default per D6).
#
# Override via env `SDD_REVERSE_HOME_STEMS` (comma-separated, lowercase).
# Useful if the legacy uses an exotic stem (e.g. `portada.html`,
# `startsida.aspx`, `pagina-inicial.cshtml`). Setting the env var
# REPLACES the defaults — pass them again if you want to keep them.
_DEFAULT_HOME_STEMS: frozenset[str] = frozenset({
    # English
    "default", "index", "home", "main", "start",
    # French
    "accueil", "principal", "principale",
    # Spanish
    "inicio", "principal", "portada",
    # German
    "startseite", "haupt", "hauptseite",
    # Italian
    "principale", "iniziale",
    # Portuguese
    "inicial", "principal",
})


def _home_stems() -> frozenset[str]:
    """Resolve effective home-page stems (env override wins, lowercased)."""
    override = os.environ.get("SDD_REVERSE_HOME_STEMS")
    if not override:
        return _DEFAULT_HOME_STEMS
    custom = {s.strip().lower() for s in override.split(",") if s.strip()}
    return frozenset(custom) if custom else _DEFAULT_HOME_STEMS

# Patterns suggesting CRUD grid (data display + actions)
GRID_PATTERNS = [
    re.compile(r"<asp:GridView\b", re.IGNORECASE),
    re.compile(r"<asp:Repeater\b", re.IGNORECASE),
    re.compile(r"<table\b[^>]*\b(?:datasource|gridview)", re.IGNORECASE),
    re.compile(r"<th:block\s+th:each", re.IGNORECASE),       # Thymeleaf
    re.compile(r"@foreach\s*\(", re.IGNORECASE),              # Razor
    re.compile(r"v-for\b", re.IGNORECASE),                    # Vue
    re.compile(r"ng-repeat\b", re.IGNORECASE),                # AngularJS
    re.compile(r"\.map\s*\(\s*\w+\s*=>", re.IGNORECASE),     # React/JS
    # WPF (2026-06-10)
    re.compile(r"<DataGrid\b", re.IGNORECASE),
    re.compile(r"<ListView\b", re.IGNORECASE),
    re.compile(r"<TreeView\b", re.IGNORECASE),
]

# Patterns suggesting form (login, registration, edit)
FORM_PATTERNS = [
    re.compile(r"<form\b[^>]*method\s*=", re.IGNORECASE),
    re.compile(r"<asp:TextBox\b", re.IGNORECASE),
    re.compile(r"<asp:Button\b[^>]*OnClick\s*=", re.IGNORECASE),
    re.compile(r"<input\s+type\s*=\s*[\"']password[\"']", re.IGNORECASE),
    re.compile(r"@Html\.BeginForm\(", re.IGNORECASE),
    re.compile(r"FormBuilder\b|FormGroup\b", re.IGNORECASE),
    # WPF (2026-06-10) — TextBox/PasswordBox/Button trio = form-like screen
    re.compile(r"<PasswordBox\b", re.IGNORECASE),
    re.compile(r"<Button\b[^>]*\b(?:Click|Command)\s*=", re.IGNORECASE),
]

# Patterns suggesting wizard
WIZARD_PATTERNS = [
    re.compile(r"step[-_]?\d+", re.IGNORECASE),
    re.compile(r"<asp:Wizard\b", re.IGNORECASE),
    re.compile(r"stepIndex|currentStep|wizardStep", re.IGNORECASE),
    # WPF (2026-06-10) — TabControl with explicit tabs OR step-based pages
    re.compile(r"<TabControl\b", re.IGNORECASE),
]

# Patterns suggesting standalone confirm modal (NOT a unit — integrated)
CONFIRM_MODAL_PATTERNS = [
    re.compile(r"confirm.*delete|delete.*confirm", re.IGNORECASE),
    re.compile(r"<asp:Panel\b[^>]*\bid\s*=\s*[\"'][^\"']*confirm", re.IGNORECASE),
]


def _read_normalized(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return decode_text(normalize_bytes(raw))


def _classify_page(content: str, path_str: str = "") -> tuple[str, float]:
    """Return (kind, confidence_score). Bug #5 fix: detect layout/master pages.

    Layout-like files are filtered OUT of unit detection :
        - ASP.NET master pages (`.master` or `<%@ Master %>` directive)
        - WPF App.xaml (entry point, contains Application/Resources only — no screen)
        - WPF .xaml with `<Application` root (== App.xaml in any casing)
        - WPF .xaml with ONLY a `<ResourceDictionary>` root (theme/style file)
    """
    # Bug #5 fix: master pages are layout components, not user-facing pages
    is_master_directive = bool(re.search(r"<%@\s+Master\s+", content, re.IGNORECASE))
    is_master_file = path_str.lower().endswith(".master")
    # WPF layout/entry files — 2026-06-10
    is_wpf_app_xaml = path_str.lower().endswith("app.xaml")
    is_wpf_application_root = bool(re.search(r"<Application\b", content, re.IGNORECASE))
    is_wpf_resource_only = bool(
        re.search(r"<ResourceDictionary\b", content, re.IGNORECASE)
        and not re.search(r"<(Window|Page|UserControl)\b", content, re.IGNORECASE)
    )
    if (
        is_master_directive
        or is_master_file
        or is_wpf_app_xaml
        or is_wpf_application_root
        or is_wpf_resource_only
    ):
        return "layout", 0.0  # score=0 → filtered out of units

    grid_hits = sum(1 for p in GRID_PATTERNS if p.search(content))
    form_hits = sum(1 for p in FORM_PATTERNS if p.search(content))
    wizard_hits = sum(1 for p in WIZARD_PATTERNS if p.search(content))
    confirm_hits = sum(1 for p in CONFIRM_MODAL_PATTERNS if p.search(content))

    # Wizard beats grid/form (more specific)
    if wizard_hits >= 1:
        return "wizard", 1.0 + wizard_hits * 0.5
    # Grid usually displays existing data
    if grid_hits >= 1:
        return "grid", 1.0 + grid_hits * 0.3
    # Form is broad
    if form_hits >= 2:
        return "form", 1.0 + form_hits * 0.2
    # Standalone confirm modal with no other content
    if confirm_hits >= 1 and form_hits == 0 and grid_hits == 0:
        return "confirm-modal", 0.5
    return "page", 0.3


def _suggested_name_from_path(path: str) -> str:
    """Derive a PascalCase Name from a file path.

    Examples:
        Login.aspx          → Login
        users-list.aspx     → UsersList
        admin/edit_user.cshtml → EditUser
        Default.aspx        → Home    (canonical home alias)
        accueil.html        → Home    (FR cognate, P2.10)
        inicio.cshtml       → Home    (ES cognate, P2.10)
        startseite.aspx     → Home    (DE cognate, P2.10)

    The home-page detection is multilingual (cf. ``_home_stems``).
    The returned identifier stays canonical English ``Home`` (used for
    PascalCase component names) — the FR display label ``Accueil`` is
    applied by `_label_from_kind_and_name`. Identifier convention is
    intentionally locale-independent so code generation stays portable.
    """
    p = Path(path)
    stem = p.stem
    if stem.lower() in _home_stems():
        return "Home"
    # split on -, _, spaces; PascalCase
    parts = re.split(r"[-_\s]+", stem)
    return "".join(part.capitalize() for part in parts if part)


def _label_from_kind_and_name(kind: str, name: str) -> str:
    """FR-language label per D6."""
    if name == "Home":
        return "Accueil"
    mapping = {
        "form": f"Formulaire {name}",
        "grid": f"Liste {name}",
        "wizard": f"Assistant {name}",
        "page": f"Page {name}",
    }
    return mapping.get(kind, f"Écran {name}")


def detect_units(
    pages: list[dict[str, Any]],
    project_root: Path,
    signatures: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect functional units from page candidates.

    Args:
        pages: list of {id, path, codeBehindPath, locTotal, ...}
        project_root: workspace/old/{P}/
        signatures: loaded language_signatures.yml dict (for language lookup)
    """
    units: list[dict[str, Any]] = []
    for page in pages:
        page_path = project_root / page["path"]
        content = _read_normalized(page_path)
        if not content.strip():
            continue
        kind, score = _classify_page(content, page["path"])
        if kind in {"confirm-modal", "layout"}:
            # D2 + Bug #5: standalone confirm OR master/layout = 0 unit
            continue
        name = _suggested_name_from_path(page["path"])
        label = _label_from_kind_and_name(kind, name)
        evidence = [page["path"]]
        if page.get("codeBehindPath"):
            evidence.append(page["codeBehindPath"])

        # Confidence estimate from score
        if score >= 1.5:
            conf = "high"
        elif score >= 0.7:
            conf = "medium"
        else:
            conf = "low"

        # Detect language from page extension
        ext = Path(page["path"]).suffix.lower()
        lang_id = "unknown"
        for lang in signatures["languages"]:
            if ext in lang.get("file_extensions", []):
                lang_id = lang["id"]
                break

        units.append({
            "label": label,
            "suggestedName": name,
            "language": lang_id,
            "kind": kind,
            "evidenceFiles": evidence,
            "entities": [],   # entities detection done by db_schema_extractor + agent
            "confidenceEstimate": conf,
            "rationale": f"Page {page['path']} classified as {kind} (score={score:.2f})",
        })
    return units
