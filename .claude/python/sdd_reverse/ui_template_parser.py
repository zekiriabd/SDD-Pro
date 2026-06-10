"""ui_template_parser.py — Pre-extract semantic structure from legacy templates.

Phase 4 (UI) prerequisite. Feeds the reverse-ui-extractor agent with
a tree of identifiable UI elements (forms, inputs, buttons, grids,
labels, links) translated from various template families.

Public API:
    parse_template(file_path) -> dict

Output:
    {
        "schemaVersion": 1,
        "source_path": "Login.aspx",
        "template_family": "aspx" | "cshtml" | "jsp" | "blade" | "html",
        "title": "Connexion",
        "forms": [{"id": "form1", "method": "post", "action": "..."}],
        "elements": [
            {"kind": "input", "type": "text", "id": "txtUsername", "label": "Nom d'utilisateur :"},
            {"kind": "input", "type": "password", "id": "txtPassword", "label": "Mot de passe :"},
            {"kind": "button", "id": "btnLogin", "text": "Se connecter", "on_click": "btnLogin_Click"},
            ...
        ],
        "links": [{"href": "Default.aspx", "text": "Accueil"}],
        "grids": [{"id": "GridView1", "kind": "asp:GridView"}],
    }

Best-effort regex parsing — NOT a real HTML parser (to keep zero deps).
The agent re-reads the file if it needs precision.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import normalize_bytes

# === Template family detection ===
_FAMILY_BY_EXT = {
    ".aspx": "aspx",
    ".ascx": "aspx",
    ".master": "aspx",
    ".cshtml": "cshtml",
    ".vbhtml": "cshtml",
    ".jsp": "jsp",
    ".jspx": "jsp",
    ".xhtml": "jsf",
    ".blade.php": "blade",
    ".twig": "twig",
    ".html": "html",
    ".htm": "html",
    ".pas": "delphi-dfm",  # via companion .dfm
    ".dfm": "delphi-dfm",
    ".frm": "vb6-form",
}

# === Common elements ===
_RE_TITLE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE | re.DOTALL)
_RE_FORM = re.compile(r"<form\b([^>]*)>", re.IGNORECASE)
_RE_INPUT_HTML = re.compile(r"<input\b([^>]*)/?>", re.IGNORECASE)
_RE_BUTTON_HTML = re.compile(r"<button\b([^>]*)>([^<]*)</button>", re.IGNORECASE | re.DOTALL)
_RE_LABEL_HTML = re.compile(r"<label\b([^>]*)>([^<]*)</label>", re.IGNORECASE | re.DOTALL)
_RE_LINK_HTML = re.compile(r"<a\b([^>]*)>([^<]+)</a>", re.IGNORECASE | re.DOTALL)
_RE_TABLE_HTML = re.compile(r"<table\b([^>]*)>", re.IGNORECASE)

# === ASP server controls ===
_RE_ASP_TEXTBOX = re.compile(r"<asp:TextBox\b([^>/]*)/?>", re.IGNORECASE)
_RE_ASP_BUTTON = re.compile(r"<asp:(?:Button|LinkButton)\b([^>/]*)/?>", re.IGNORECASE)
_RE_ASP_LABEL = re.compile(r"<asp:Label\b([^>/]*?)(?:/>|>([^<]*)</asp:Label>)", re.IGNORECASE)
_RE_ASP_GRIDVIEW = re.compile(r"<asp:(GridView|Repeater|ListView|DataGrid)\b([^>/]*)/?>", re.IGNORECASE)

# === Attribute extraction ===
_RE_ATTR = re.compile(r'(\w+(?:[-:]\w+)?)\s*=\s*[\"\']([^\"\']*)[\"\']')


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return normalize_bytes(raw).decode("utf-8", errors="replace")


def _detect_family(file_path: Path) -> str:
    """Detect template family from filename suffix (multi-ext-aware)."""
    name = file_path.name.lower()
    if name.endswith(".blade.php"):
        return "blade"
    return _FAMILY_BY_EXT.get(file_path.suffix.lower(), "unknown")


def _parse_attrs(attr_str: str) -> dict[str, str]:
    return {k: v for k, v in _RE_ATTR.findall(attr_str)}


def _strip_comments(content: str, family: str) -> str:
    """Remove HTML/ASPX/Razor comments to avoid scanning commented-out code."""
    # HTML
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    if family in {"aspx", "cshtml"}:
        # ASPX server-side comments
        content = re.sub(r"<%--.*?--%>", "", content, flags=re.DOTALL)
    if family == "cshtml":
        # Razor @* ... *@
        content = re.sub(r"@\*.*?\*@", "", content, flags=re.DOTALL)
    return content


def _associate_labels(elements: list[dict[str, Any]],
                       labels_by_for: dict[str, str]) -> None:
    """Best-effort: attach a `label` field to inputs/buttons that have
    a <label for="..."> or asp:Label AssociatedControlID matching their id."""
    for el in elements:
        eid = el.get("id")
        if eid and eid in labels_by_for:
            el["label"] = labels_by_for[eid].strip()


def parse_template(file_path: str | Path) -> dict[str, Any]:
    """Parse a single template file."""
    p = Path(file_path)
    family = _detect_family(p)
    content = _read_text(p)
    if not content:
        return {
            "schemaVersion": 1,
            "source_path": str(p),
            "template_family": family,
            "title": None,
            "forms": [],
            "elements": [],
            "links": [],
            "grids": [],
            "error": "unreadable",
        }
    content = _strip_comments(content, family)

    title_m = _RE_TITLE.search(content)
    title = title_m.group(1).strip() if title_m else None

    forms: list[dict[str, Any]] = []
    for m in _RE_FORM.finditer(content):
        attrs = _parse_attrs(m.group(1))
        forms.append({
            "id": attrs.get("id", ""),
            "method": attrs.get("method", "get").lower(),
            "action": attrs.get("action", ""),
        })

    # Collect labels first for association
    labels_by_for: dict[str, str] = {}
    for m in _RE_LABEL_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        target = attrs.get("for") or attrs.get("AssociatedControlID", "")
        if target:
            labels_by_for[target] = m.group(2).strip()
    # ASP labels with AssociatedControlID
    for m in _RE_ASP_LABEL.finditer(content):
        attrs = _parse_attrs(m.group(1))
        target = attrs.get("AssociatedControlID", "")
        if target:
            text = attrs.get("Text", "") or (m.group(2) or "")
            labels_by_for[target] = text.strip()

    elements: list[dict[str, Any]] = []

    # HTML inputs
    for m in _RE_INPUT_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        elements.append({
            "kind": "input",
            "type": attrs.get("type", "text").lower(),
            "id": attrs.get("id", ""),
            "name": attrs.get("name", ""),
            "value": attrs.get("value", ""),
            "placeholder": attrs.get("placeholder", ""),
        })

    # ASP TextBox
    for m in _RE_ASP_TEXTBOX.finditer(content):
        attrs = _parse_attrs(m.group(1))
        elements.append({
            "kind": "input",
            "type": attrs.get("TextMode", "text").lower(),
            "id": attrs.get("ID", ""),
            "name": attrs.get("ID", ""),
            "value": attrs.get("Text", ""),
            "asp_control": "asp:TextBox",
        })

    # HTML buttons
    for m in _RE_BUTTON_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        elements.append({
            "kind": "button",
            "id": attrs.get("id", ""),
            "type": attrs.get("type", "submit").lower(),
            "text": m.group(2).strip(),
        })

    # ASP Button / LinkButton
    for m in _RE_ASP_BUTTON.finditer(content):
        attrs = _parse_attrs(m.group(1))
        elements.append({
            "kind": "button",
            "id": attrs.get("ID", ""),
            "text": attrs.get("Text", ""),
            "on_click": attrs.get("OnClick", ""),
            "asp_control": "asp:Button",
        })

    _associate_labels(elements, labels_by_for)

    # Links
    links: list[dict[str, str]] = []
    for m in _RE_LINK_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        href = attrs.get("href", "")
        text = m.group(2).strip()
        if href:
            links.append({"href": href, "text": text})

    # Grids
    grids: list[dict[str, Any]] = []
    # HTML tables (only flag those with a class/id suggesting data display)
    for m in _RE_TABLE_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        if any(k in (attrs.get("class", "") + attrs.get("id", "")).lower()
               for k in ("grid", "data", "table-striped", "datatable")):
            grids.append({"kind": "html-table", "id": attrs.get("id", "")})
    # ASP grids
    for m in _RE_ASP_GRIDVIEW.finditer(content):
        control = m.group(1)
        attrs = _parse_attrs(m.group(2))
        grids.append({
            "kind": f"asp:{control}",
            "id": attrs.get("ID", ""),
            "data_source": attrs.get("DataSourceID", ""),
        })

    return {
        "schemaVersion": 1,
        "source_path": str(p),
        "template_family": family,
        "title": title,
        "forms": forms,
        "elements": elements,
        "links": links,
        "grids": grids,
    }
