"""SDD_Pro Reverse Engineering — UI functional unit detector.

Pre-detection of functional units inside pages (grid CRUD, form, menu, wizard,
filter panel, modal, etc.) via deterministic pattern matching.

Output schema: see docs/reverse-engineering-workflow.md SS2.4 (units-candidates.json).

This module produces FEAT-candidate units; the LLM agent reverse-inventory
arbitrates ambiguous cases (merge/split) downstream.

Pure deterministic Python. No imports from sdd_lib/.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pattern → (unit_type, label_template, confidence_hint)
# Patterns are regex (case-insensitive) searched per-page content.
UNIT_PATTERNS: list[dict[str, Any]] = [
    # ASP.NET WebForms server controls
    {
        "id": "aspx-gridview",
        "regex": r"<asp:GridView\b[^>]*",
        "type": "grid-crud",
        "label_template": "Grille {entity}",
        "evidence_pattern": "asp:GridView with OnRowEditing/OnRowDeleting",
        "confidence_hint": "high",
    },
    {
        "id": "aspx-formview",
        "regex": r"<asp:FormView\b[^>]*|<asp:DetailsView\b[^>]*",
        "type": "form-edit",
        "label_template": "Édition fiche {entity}",
        "evidence_pattern": "asp:FormView / asp:DetailsView",
        "confidence_hint": "high",
    },
    {
        "id": "aspx-repeater",
        "regex": r"<asp:Repeater\b[^>]*",
        "type": "custom-list",
        "label_template": "Liste {entity}",
        "evidence_pattern": "asp:Repeater with item template",
        "confidence_hint": "medium",
    },
    {
        "id": "aspx-wizard",
        "regex": r"<asp:Wizard\b[^>]*",
        "type": "wizard",
        "label_template": "Assistant {entity}",
        "evidence_pattern": "asp:Wizard multi-step",
        "confidence_hint": "high",
    },
    {
        "id": "aspx-menu",
        "regex": r"<asp:Menu\b[^>]*|<asp:SiteMapPath\b[^>]*|<asp:TreeView\b[^>]*",
        "type": "navigation-menu",
        "label_template": "Menu navigation",
        "evidence_pattern": "asp:Menu / SiteMapPath / TreeView",
        "confidence_hint": "high",
    },
    {
        "id": "aspx-login",
        "regex": r"<asp:Login\b[^>]*",
        "type": "form-login",
        "label_template": "Formulaire d'authentification",
        "evidence_pattern": "asp:Login control",
        "confidence_hint": "high",
    },
    {
        "id": "aspx-filter-panel",
        "regex": r"<asp:DropDownList\b[^>]*.*?<asp:TextBox\b[^>]*.*?<asp:Button\b[^>]*OnClick",
        "type": "filter-panel",
        "label_template": "Panneau de filtres",
        "evidence_pattern": "Combinaison DropDownList + TextBox + Button OnClick",
        "confidence_hint": "medium",
    },
    {
        "id": "aspx-modal-popup",
        "regex": r"<ajaxToolkit:ModalPopupExtender\b|<asp:Panel\b[^>]*Modal",
        "type": "modal-action",
        "label_template": "Boîte de dialogue modale",
        "evidence_pattern": "ModalPopupExtender / Modal Panel",
        "confidence_hint": "medium",
    },
    # MVC / Razor patterns
    {
        "id": "mvc-form-post",
        "regex": r"@using\s*\(\s*Html\.BeginForm|@Html\.BeginForm\s*\(",
        "type": "form-submit",
        "label_template": "Formulaire de soumission",
        "evidence_pattern": "Html.BeginForm helper",
        "confidence_hint": "high",
    },
    {
        "id": "mvc-partial",
        "regex": r"@Html\.Partial\s*\(|<partial\s+name=",
        "type": "partial-component",
        "label_template": "Composant partial",
        "evidence_pattern": "@Html.Partial / <partial>",
        "confidence_hint": "medium",
    },
    # Generic HTML form patterns (covers PHP, JSP, static HTML)
    {
        "id": "html-form-login",
        "regex": r"<form\b[^>]*>.*?<input[^>]*type=[\"']password[\"']",
        "type": "form-login",
        "label_template": "Formulaire d'authentification",
        "evidence_pattern": "<form> with password input",
        "confidence_hint": "high",
    },
    {
        "id": "html-form-generic",
        "regex": r"<form\b[^>]*method=[\"']post[\"']",
        "type": "form-submit",
        "label_template": "Formulaire (POST)",
        "evidence_pattern": "<form method=post>",
        "confidence_hint": "medium",
    },
    {
        "id": "html-table-data",
        "regex": r"<table\b[^>]*(?:id=[\"']?(?:data|grid|results))",
        "type": "data-table",
        "label_template": "Tableau de données",
        "evidence_pattern": "<table id=data/grid/results>",
        "confidence_hint": "medium",
    },
    # jQuery DataTables / plugin signals
    {
        "id": "jquery-datatable",
        "regex": r"\$\([^)]*\)\.DataTable\s*\(",
        "type": "grid-crud",
        "label_template": "Grille DataTables",
        "evidence_pattern": "jQuery DataTable() init",
        "confidence_hint": "medium",
    },
    # Java JSP patterns
    {
        "id": "jsp-form",
        "regex": r"<jsp:useBean|<form\s+action=",
        "type": "form-submit",
        "label_template": "Formulaire JSP",
        "evidence_pattern": "jsp:useBean or HTML form",
        "confidence_hint": "medium",
    },
    # PHP form patterns
    {
        "id": "php-post-handler",
        "regex": r"\$_POST\[[\"'](?:submit|action|login)[\"']\]|if\s*\(\s*\$_SERVER\[[\"']REQUEST_METHOD[\"']\]\s*==\s*[\"']POST[\"']",
        "type": "form-submit",
        "label_template": "Handler POST",
        "evidence_pattern": "$_POST handler",
        "confidence_hint": "medium",
    },
]


def _read_text_safe(path: Path, max_bytes: int = 65536) -> str:
    """Read file content (UTF-8 best-effort, capped at 64KB for unit detection)."""
    try:
        size = min(path.stat().st_size, max_bytes)
        with path.open("rb") as f:
            raw = f.read(size)
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
    except OSError:
        pass
    return ""


def _find_match_lines(content: str, pattern: str) -> list[tuple[int, int]]:
    """Return [(start_line, end_line)] for all regex matches in content."""
    matches: list[tuple[int, int]] = []
    try:
        regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    except re.error:
        return []
    for m in regex.finditer(content):
        start_offset = m.start()
        end_offset = m.end()
        start_line = content[:start_offset].count("\n") + 1
        end_line = content[:end_offset].count("\n") + 1
        # Cap match span at 60 lines (avoid spans that swallow whole page on DOTALL)
        if end_line - start_line > 60:
            end_line = start_line + 60
        matches.append((start_line, end_line))
    return matches


def _guess_entity(page_path: str) -> str:
    """Guess entity name from page path: Customers/List.aspx → Customers."""
    p = Path(page_path)
    # Use parent folder if not root
    if str(p.parent) not in (".", ""):
        return p.parent.name
    # Else use stem stripped of suffixes
    stem = p.stem
    for suffix in ("List", "Edit", "View", "Details", "Form", "Detail", "Add", "New"):
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return stem[: -len(suffix)]
    return stem


def _code_behind_evidence(
    page: dict[str, Any],
    project_path: Path,
    line_hints: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    """Best-effort: list code-behind methods that look related (RowEditing, OnClick, etc.)."""
    if not page.get("code_behind"):
        return []
    cb_path = project_path / page["code_behind"]
    if not cb_path.is_file():
        return []
    content = _read_text_safe(cb_path)
    if not content:
        return []
    # Detect handler-like method names
    methods = []
    for match in re.finditer(
        r"(?:public|private|protected)\s+(?:async\s+)?(?:void|Task|[\w<>]+)\s+(\w+(?:RowEditing|RowDeleting|Click|Load|Submit|Authenticate|BindGrid))\b",
        content,
        re.IGNORECASE,
    ):
        methods.append(match.group(1))
    if not methods:
        return []
    return [{
        "file": page["code_behind"],
        "methods": sorted(set(methods))[:8],
    }]


def detect_units_in_page(
    page: dict[str, Any],
    project_path: Path,
    next_unit_seq: int,
) -> list[dict[str, Any]]:
    """Apply UNIT_PATTERNS to a page, return list of candidate units."""
    full_path = project_path / page["path"]
    if not full_path.is_file():
        return []
    content = _read_text_safe(full_path)
    if not content:
        return []

    entity = _guess_entity(page["path"])
    units: list[dict[str, Any]] = []
    seq = next_unit_seq

    for pattern_def in UNIT_PATTERNS:
        matches = _find_match_lines(content, pattern_def["regex"])
        if not matches:
            continue
        start_line, end_line = matches[0]
        evidence = [{
            "file": page["path"],
            "lines": f"{start_line}-{end_line}",
            "pattern": pattern_def["evidence_pattern"],
        }]
        cb_evidence = _code_behind_evidence(page, project_path, matches)

        units.append({
            "id": f"unit-{seq:03d}",
            "page_id": page["id"],
            "page_path": page["path"],
            "type": pattern_def["type"],
            "label_proposed": pattern_def["label_template"].format(entity=entity),
            "evidence": evidence,
            "code_behind_evidence": cb_evidence,
            "merge_hint": None,
            "split_hint": None,
            "confidence_hint": pattern_def["confidence_hint"],
            "pattern_id": pattern_def["id"],
        })
        seq += 1

    return units


def detect_all_units(
    pages: list[dict[str, Any]],
    project_path: Path,
) -> dict[str, Any]:
    """Iterate over all pages, return units-candidates.json dict."""
    project_path = project_path.resolve()
    all_units: list[dict[str, Any]] = []
    seq = 1

    for page in pages:
        page_units = detect_units_in_page(page, project_path, seq)
        all_units.extend(page_units)
        seq += len(page_units)

    # Detect potential merge hints (heuristic):
    # If unit "filter-panel" and "grid-crud" share same page → merge hint
    _annotate_merge_hints(all_units)

    return {
        "schema_version": 1,
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "units": all_units,
    }


def _annotate_merge_hints(units: list[dict[str, Any]]) -> None:
    """Detect candidate merges between units on the same page."""
    by_page: dict[str, list[dict]] = {}
    for u in units:
        by_page.setdefault(u["page_id"], []).append(u)

    for page_units in by_page.values():
        if len(page_units) < 2:
            continue
        types_present = {u["type"]: u["id"] for u in page_units}
        # Filter-panel + grid-crud on same page → propose merge
        if "filter-panel" in types_present and "grid-crud" in types_present:
            filter_id = types_present["filter-panel"]
            grid_id = types_present["grid-crud"]
            for u in page_units:
                if u["id"] == filter_id:
                    u["merge_hint"] = f"{grid_id} (filtres = pré-flux du grid CRUD)"
