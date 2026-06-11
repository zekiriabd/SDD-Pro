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
    ".xaml": "wpf",  # WPF XAML (2026-06-10 — Windows desktop UI support)
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

# === L4: grid columns + data-binding + extra controls ===
# Full grid element (open..close) so its <Columns> can be parsed.
_RE_ASP_GRID_BLOCK = re.compile(
    r"<asp:(GridView|DataGrid|ListView|Repeater)\b([^>]*)>(.*?)</asp:\1>",
    re.IGNORECASE | re.DOTALL,
)
_RE_BOUNDFIELD = re.compile(r"<asp:BoundField\b([^>/]*)/?>", re.IGNORECASE)
_RE_TEMPLATEFIELD = re.compile(r"<asp:TemplateField\b([^>]*)>", re.IGNORECASE)
_RE_GRID_FIELD_OTHER = re.compile(
    r"<asp:(ButtonField|HyperLinkField|CheckBoxField|CommandField|ImageField)\b([^>/]*)/?>",
    re.IGNORECASE,
)
# Data-binding expressions: Eval("X") / Bind("X") (WebForms), @Model.X / @item.X (Razor),
# {{ x }} (Thymeleaf/Vue light).
_RE_EVAL_BIND = re.compile(r"(?:Eval|Bind)\(\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_RE_RAZOR_BIND = re.compile(r"@(?:Model|item)\.([A-Za-z_]\w*)")

# Extra ASP / HTML form controls (the form is amputated without these).
_RE_ASP_DROPDOWN = re.compile(r"<asp:(DropDownList|ListBox)\b([^>]*?)(?:/>|>(.*?)</asp:\1>)", re.IGNORECASE | re.DOTALL)
_RE_ASP_CHECKBOX = re.compile(r"<asp:(CheckBox|CheckBoxList)\b([^>/]*)/?>", re.IGNORECASE)
_RE_ASP_RADIO = re.compile(r"<asp:(RadioButton|RadioButtonList)\b([^>/]*)/?>", re.IGNORECASE)
_RE_ASP_HYPERLINK = re.compile(r"<asp:HyperLink\b([^>/]*?)(?:/>|>([^<]*)</asp:HyperLink>)", re.IGNORECASE)
_RE_ASP_IMAGE = re.compile(r"<asp:Image\b([^>/]*)/?>", re.IGNORECASE)
_RE_SELECT_HTML = re.compile(r"<select\b([^>]*)>(.*?)</select>", re.IGNORECASE | re.DOTALL)
_RE_OPTION_HTML = re.compile(r"<option\b([^>]*)>([^<]*)</option>", re.IGNORECASE)
_RE_TEXTAREA_HTML = re.compile(r"<textarea\b([^>]*)>(.*?)</textarea>", re.IGNORECASE | re.DOTALL)

# === WPF XAML controls (2026-06-10 — Windows desktop UI support) ===
# Root containers — at most 1 per file, defines the screen
_RE_WPF_ROOT = re.compile(
    r"<(Window|Page|UserControl)\b([^>]*)>", re.IGNORECASE,
)
# Title attribute on Window (the "screen title")
_RE_WPF_TITLE = re.compile(
    r'<Window\b[^>]*\bTitle="([^"]*)"', re.IGNORECASE,
)

# Text-bearing primitives — TextBlock = read-only, Label = with target binding
_RE_WPF_TEXTBLOCK = re.compile(
    r"<TextBlock\b([^>/]*?)(?:/>|>([^<]*)</TextBlock>)", re.IGNORECASE | re.DOTALL,
)
_RE_WPF_LABEL = re.compile(
    r"<Label\b([^>/]*?)(?:/>|>([^<]*)</Label>)", re.IGNORECASE | re.DOTALL,
)

# Input primitives
_RE_WPF_TEXTBOX = re.compile(r"<TextBox\b([^>/]*)/?>", re.IGNORECASE)
_RE_WPF_PASSWORDBOX = re.compile(r"<PasswordBox\b([^>/]*)/?>", re.IGNORECASE)
_RE_WPF_CHECKBOX = re.compile(
    r"<CheckBox\b([^>/]*?)(?:/>|>([^<]*)</CheckBox>)", re.IGNORECASE | re.DOTALL,
)
_RE_WPF_RADIOBUTTON = re.compile(
    r"<RadioButton\b([^>/]*?)(?:/>|>([^<]*)</RadioButton>)", re.IGNORECASE | re.DOTALL,
)
_RE_WPF_COMBOBOX = re.compile(r"<ComboBox\b([^>/]*)/?>", re.IGNORECASE)

# Action primitives.
# Audit 2026-06-10 M18 : the content group was `[^<]*` — a Button with NESTED
# content (`<Button><StackPanel><Image/><TextBlock Text="Valider"/></StackPanel>
# </Button>`, the icon+text pattern) did not match AT ALL and vanished from the
# mockup. Content is now `.*?` (non-greedy) and the label is recovered from
# inner Text= attributes + bare text via `_wpf_inner_text`.
_RE_WPF_BUTTON = re.compile(
    r"<Button\b([^>/]*?)(?:/>|>(.*?)</Button>)", re.IGNORECASE | re.DOTALL,
)

_RE_XML_TAG = re.compile(r"<[^>]+>")
_RE_INNER_TEXT_ATTR = re.compile(r'Text="([^"]+)"')


def _wpf_inner_text(inner: str) -> str:
    """Recover a human label from nested XAML content (icon+text buttons)."""
    parts = list(_RE_INNER_TEXT_ATTR.findall(inner))
    bare = _RE_XML_TAG.sub(" ", inner).strip()
    if bare:
        parts.append(bare)
    return " ".join(p.strip() for p in parts if p.strip())
_RE_WPF_HYPERLINK = re.compile(
    r"<Hyperlink\b([^>/]*?)(?:/>|>([^<]*)</Hyperlink>)", re.IGNORECASE | re.DOTALL,
)

# Data display primitives
_RE_WPF_DATAGRID = re.compile(r"<DataGrid\b([^>/]*)/?>", re.IGNORECASE)
_RE_WPF_LISTVIEW = re.compile(r"<(ListView|ListBox|ItemsControl)\b([^>/]*)/?>", re.IGNORECASE)
_RE_WPF_TREEVIEW = re.compile(r"<TreeView\b([^>/]*)/?>", re.IGNORECASE)

# Image
_RE_WPF_IMAGE = re.compile(r"<Image\b([^>/]*)/?>", re.IGNORECASE)

# Layout containers (informational — kept for completeness, mapped to div+class)
_RE_WPF_GRID = re.compile(r"<Grid\b([^>/]*)>", re.IGNORECASE)
_RE_WPF_STACKPANEL = re.compile(r"<StackPanel\b([^>/]*)>", re.IGNORECASE)
_RE_WPF_DOCKPANEL = re.compile(r"<DockPanel\b([^>/]*)>", re.IGNORECASE)
_RE_WPF_CANVAS = re.compile(r"<Canvas\b([^>/]*)>", re.IGNORECASE)
_RE_WPF_WRAPPANEL = re.compile(r"<WrapPanel\b([^>/]*)>", re.IGNORECASE)

# === Attribute extraction ===
# Three variants handled (P1.8 closure 2026-06-10) :
#   1. double-quoted : id="txtFoo"
#   2. single-quoted : id='txtFoo'
#   3. unquoted      : id=txtFoo  (HTML5 attribute syntax)
#   4. boolean       : disabled / readonly / required   (no value)
_RE_ATTR_QUOTED = re.compile(r'(\w+(?:[-:]\w+)?)\s*=\s*"([^"]*)"')
_RE_ATTR_SQUOTED = re.compile(r"(\w+(?:[-:]\w+)?)\s*=\s*'([^']*)'")
_RE_ATTR_UNQUOTED = re.compile(r'(\w+(?:[-:]\w+)?)\s*=\s*([^\s"\'>=`]+)')
_RE_ATTR_BOOLEAN = re.compile(r'(?:^|\s)(\w+(?:[-:]\w+)?)(?=\s|$|/?>)')

# Boolean HTML5 attributes whose presence alone is meaningful
_HTML5_BOOLEAN_ATTRS = frozenset({
    "disabled", "readonly", "required", "checked", "selected", "autofocus",
    "multiple", "open", "hidden", "novalidate", "autoplay", "controls",
    "loop", "muted", "default", "reversed",
})


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
    """Parse HTML attributes — handles quoted, unquoted, and boolean forms.

    Order of precedence (first match wins per attribute name) :
        1. double-quoted ``id="x"``
        2. single-quoted ``id='x'``
        3. unquoted      ``id=x``        (HTML5)
        4. boolean       ``disabled``    (value="" sentinel for presence)
    """
    out: dict[str, str] = {}
    # 1+2: quoted variants
    for k, v in _RE_ATTR_QUOTED.findall(attr_str):
        out.setdefault(k, v)
    for k, v in _RE_ATTR_SQUOTED.findall(attr_str):
        out.setdefault(k, v)
    # 3: unquoted (only consider tokens NOT already captured)
    # Strip already-matched ranges to avoid catching the value as a new attr
    residual = _RE_ATTR_QUOTED.sub("", attr_str)
    residual = _RE_ATTR_SQUOTED.sub("", residual)
    for k, v in _RE_ATTR_UNQUOTED.findall(residual):
        out.setdefault(k, v)
    # 4: boolean HTML5 attrs (presence-only)
    residual_bool = _RE_ATTR_UNQUOTED.sub("", residual)
    for k in _RE_ATTR_BOOLEAN.findall(residual_bool):
        if k.lower() in _HTML5_BOOLEAN_ATTRS:
            out.setdefault(k, "")
    return out


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


def _strip_xaml_namespace_prefix(attr_str: str) -> str:
    """Drop XAML namespace prefixes (`x:Name="..."`) so `_parse_attrs` finds
    the bare local name. ``x:Name`` is the canonical XAML identifier — we
    rewrite it to ``Name`` to align with WPF property semantics.
    """
    return re.sub(r"\bx:([A-Z]\w+)", r"\1", attr_str)


def _parse_xaml_attrs(attr_str: str) -> dict[str, str]:
    """Wrap `_parse_attrs` with XAML-specific namespace normalisation.

    XAML attributes use mixed casing (TitleCase) and namespace prefixes
    (``x:Name``, ``x:Key``). The downstream consumer expects plain
    PascalCase keys without the ``x:`` prefix.
    """
    return _parse_attrs(_strip_xaml_namespace_prefix(attr_str))


def _parse_xaml_template(content: str, source_path: Path) -> dict[str, Any]:
    """Parse a WPF XAML template into the same shape as `parse_template`.

    XAML-to-HTML mapping (semantic, not pixel-perfect — same doctrine as
    ASPX/JSP parsers) :

    | XAML                | HTML5 equivalent              |
    |---------------------|-------------------------------|
    | Window / Page / UserControl | root  (1 "form" record) |
    | TextBox             | <input type="text">           |
    | PasswordBox         | <input type="password">       |
    | CheckBox            | <input type="checkbox">       |
    | RadioButton         | <input type="radio">          |
    | ComboBox            | <select>                      |
    | Button              | <button>                      |
    | Hyperlink           | <a>                           |
    | TextBlock / Label   | <label>                       |
    | DataGrid / ListView | <table>  (kind=grid)          |
    | TreeView            | <ul>     (kind=grid)          |
    | Image               | <img>                         |

    Layout containers (Grid, StackPanel, DockPanel, Canvas, WrapPanel) are
    intentionally NOT mapped at this layer — the downstream HTML mockup
    flattens visual hierarchy into semantic blocks. The agent
    reverse-ui-extractor decides the final layout strategy per design
    system.
    """
    # Root window/page = single "form" record (XAML has no <form>)
    root_id = ""
    root_kind = "Window"
    root_match = _RE_WPF_ROOT.search(content)
    if root_match:
        root_kind = root_match.group(1)
        root_attrs = _parse_xaml_attrs(root_match.group(2))
        # Prefer x:Name, fall back to Name
        root_id = root_attrs.get("Name", "")

    title_m = _RE_WPF_TITLE.search(content)
    title = title_m.group(1).strip() if title_m else None

    forms: list[dict[str, Any]] = []
    if root_match:
        forms.append({
            "id": root_id,
            "method": "post",        # WPF has no HTTP method; report "post" for symmetry
            "action": "",
            "wpf_root": root_kind,   # "Window" / "Page" / "UserControl"
        })

    labels_by_for: dict[str, str] = {}
    # WPF Label with Target binding (most explicit association)
    for m in _RE_WPF_LABEL.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        # `Target="{Binding ElementName=txtFoo}"` — extract `ElementName`
        target = attrs.get("Target", "")
        tm = re.search(r"ElementName\s*=\s*(\w+)", target)
        if tm:
            text = attrs.get("Content", "") or (m.group(2) or "")
            labels_by_for[tm.group(1)] = text.strip()
    # TextBlock proximity association is heuristic — handled by downstream agent

    elements: list[dict[str, Any]] = []

    for m in _RE_WPF_TEXTBOX.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        elements.append({
            "kind": "input",
            "type": "text",
            "id": attrs.get("Name", ""),
            "name": attrs.get("Name", ""),
            "value": attrs.get("Text", ""),
            "placeholder": attrs.get("PlaceholderText", attrs.get("Tag", "")),
            "wpf_control": "TextBox",
        })

    for m in _RE_WPF_PASSWORDBOX.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        elements.append({
            "kind": "input",
            "type": "password",
            "id": attrs.get("Name", ""),
            "name": attrs.get("Name", ""),
            "value": "",  # PasswordBox value not in XAML at design-time
            "wpf_control": "PasswordBox",
        })

    for m in _RE_WPF_CHECKBOX.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        text = attrs.get("Content", "") or (m.group(2) or "")
        elements.append({
            "kind": "input",
            "type": "checkbox",
            "id": attrs.get("Name", ""),
            "label": text.strip(),
            "checked": attrs.get("IsChecked", "").lower() == "true",
            "wpf_control": "CheckBox",
        })

    for m in _RE_WPF_RADIOBUTTON.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        text = attrs.get("Content", "") or (m.group(2) or "")
        elements.append({
            "kind": "input",
            "type": "radio",
            "id": attrs.get("Name", ""),
            "label": text.strip(),
            "group": attrs.get("GroupName", ""),
            "checked": attrs.get("IsChecked", "").lower() == "true",
            "wpf_control": "RadioButton",
        })

    for m in _RE_WPF_COMBOBOX.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        elements.append({
            "kind": "select",
            "id": attrs.get("Name", ""),
            "items_source": attrs.get("ItemsSource", ""),
            "wpf_control": "ComboBox",
        })

    for m in _RE_WPF_BUTTON.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        text = attrs.get("Content", "") or _wpf_inner_text(m.group(2) or "")
        elements.append({
            "kind": "button",
            "id": attrs.get("Name", ""),
            "text": text.strip(),
            "on_click": attrs.get("Click", ""),
            "command": attrs.get("Command", ""),  # MVVM-style binding
            "wpf_control": "Button",
        })

    # TextBlock — semantic <span>/<p> in HTML; non-input
    for m in _RE_WPF_TEXTBLOCK.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        text = attrs.get("Text", "") or (m.group(2) or "")
        if text.strip():
            elements.append({
                "kind": "text",
                "id": attrs.get("Name", ""),
                "text": text.strip(),
                "wpf_control": "TextBlock",
            })

    _associate_labels(elements, labels_by_for)

    # Links — Hyperlink (XAML inline link)
    links: list[dict[str, str]] = []
    for m in _RE_WPF_HYPERLINK.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        text = (m.group(2) or "").strip()
        href = attrs.get("NavigateUri", "") or attrs.get("Command", "")
        if href or text:
            links.append({"href": href, "text": text})

    # Grids — DataGrid / ListView / ListBox / ItemsControl
    grids: list[dict[str, Any]] = []
    for m in _RE_WPF_DATAGRID.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        grids.append({
            "kind": "DataGrid",
            "id": attrs.get("Name", ""),
            "items_source": attrs.get("ItemsSource", ""),
            "wpf_control": "DataGrid",
        })
    for m in _RE_WPF_LISTVIEW.finditer(content):
        control = m.group(1)
        attrs = _parse_xaml_attrs(m.group(2))
        grids.append({
            "kind": control,
            "id": attrs.get("Name", ""),
            "items_source": attrs.get("ItemsSource", ""),
            "wpf_control": control,
        })
    for m in _RE_WPF_TREEVIEW.finditer(content):
        attrs = _parse_xaml_attrs(m.group(1))
        grids.append({
            "kind": "TreeView",
            "id": attrs.get("Name", ""),
            "items_source": attrs.get("ItemsSource", ""),
            "wpf_control": "TreeView",
        })

    return {
        "schemaVersion": 1,
        "source_path": str(source_path),
        "template_family": "wpf",
        "title": title,
        "forms": forms,
        "elements": elements,
        "links": links,
        "grids": grids,
        "bindings": [],
        "navTargets": [],
    }


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

    # 2026-06-10 — WPF XAML branch (parses to the same output shape)
    if family == "wpf":
        return _parse_xaml_template(content, p)

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
            "post_back_url": attrs.get("PostBackUrl", ""),
            "asp_control": "asp:Button",
        })

    # L4 — ASP DropDownList / ListBox (with options)
    for m in _RE_ASP_DROPDOWN.finditer(content):
        control = m.group(1)
        attrs = _parse_attrs(m.group(2))
        inner = m.group(3) or ""
        options = [
            {"value": _parse_attrs(om.group(1)).get("Value", ""), "text": om.group(2).strip()}
            for om in re.finditer(r"<asp:ListItem\b([^>]*)>([^<]*)</asp:ListItem>", inner, re.IGNORECASE)
        ] + [
            {"value": _parse_attrs(om.group(1)).get("Value", ""), "text": ""}
            for om in re.finditer(r"<asp:ListItem\b([^>/]*)/>", inner, re.IGNORECASE)
        ]
        elements.append({
            "kind": "select",
            "id": attrs.get("ID", ""),
            "options": options,
            "asp_control": f"asp:{control}",
        })

    # L4 — HTML <select>
    for m in _RE_SELECT_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        options = [
            {"value": _parse_attrs(om.group(1)).get("value", ""), "text": om.group(2).strip()}
            for om in _RE_OPTION_HTML.finditer(m.group(2))
        ]
        elements.append({"kind": "select", "id": attrs.get("id", ""),
                         "name": attrs.get("name", ""), "options": options})

    # L4 — checkboxes / radios (ASP)
    for m in _RE_ASP_CHECKBOX.finditer(content):
        attrs = _parse_attrs(m.group(2))
        elements.append({"kind": "checkbox", "id": attrs.get("ID", ""),
                         "text": attrs.get("Text", ""), "asp_control": f"asp:{m.group(1)}"})
    for m in _RE_ASP_RADIO.finditer(content):
        attrs = _parse_attrs(m.group(2))
        elements.append({"kind": "radio", "id": attrs.get("ID", ""),
                         "text": attrs.get("Text", ""), "asp_control": f"asp:{m.group(1)}"})

    # L4 — textarea
    for m in _RE_TEXTAREA_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        elements.append({"kind": "textarea", "id": attrs.get("id", ""),
                         "name": attrs.get("name", ""), "value": m.group(2).strip()})

    # L4 — images (asp:Image)
    for m in _RE_ASP_IMAGE.finditer(content):
        attrs = _parse_attrs(m.group(1))
        elements.append({"kind": "image", "id": attrs.get("ID", ""),
                         "src": attrs.get("ImageUrl", ""), "alt": attrs.get("AlternateText", "")})

    _associate_labels(elements, labels_by_for)

    # Links (+ asp:HyperLink) — also feed nav targets
    links: list[dict[str, str]] = []
    for m in _RE_LINK_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        href = attrs.get("href", "")
        text = m.group(2).strip()
        if href:
            links.append({"href": href, "text": text})
    for m in _RE_ASP_HYPERLINK.finditer(content):
        attrs = _parse_attrs(m.group(1))
        href = attrs.get("NavigateUrl", "")
        text = attrs.get("Text", "") or (m.group(2) or "").strip()
        if href:
            links.append({"href": href, "text": text})

    # L4 — navigation targets (links + button PostBackUrl) for the screen-flow graph
    nav_targets = sorted({l["href"] for l in links if l["href"] and not l["href"].startswith("#")})
    for el in elements:
        pbu = el.get("post_back_url")
        if pbu:
            nav_targets.append(pbu)

    # Grids — now WITH columns + data-binding fields (L4)
    grids: list[dict[str, Any]] = []
    bindings: list[str] = []
    # HTML tables (only flag those with a class/id suggesting data display)
    for m in _RE_TABLE_HTML.finditer(content):
        attrs = _parse_attrs(m.group(1))
        if any(k in (attrs.get("class", "") + attrs.get("id", "")).lower()
               for k in ("grid", "data", "table-striped", "datatable")):
            grids.append({"kind": "html-table", "id": attrs.get("id", ""), "columns": []})
    # ASP grids WITH columns (block form first)
    grid_ids_with_block: set[str] = set()
    for m in _RE_ASP_GRID_BLOCK.finditer(content):
        control = m.group(1)
        attrs = _parse_attrs(m.group(2))
        inner = m.group(3) or ""
        columns = _extract_grid_columns(inner)
        gid = attrs.get("ID", "")
        grid_ids_with_block.add(gid)
        grids.append({
            "kind": f"asp:{control}",
            "id": gid,
            "data_source": attrs.get("DataSourceID", ""),
            "columns": columns,
        })
        bindings.extend(c["dataField"] for c in columns if c.get("dataField"))
        bindings.extend(_RE_EVAL_BIND.findall(inner))
    # Self-closing / data-bound-in-code grids (no inner block) — open-tag fallback
    for m in _RE_ASP_GRIDVIEW.finditer(content):
        control = m.group(1)
        attrs = _parse_attrs(m.group(2))
        gid = attrs.get("ID", "")
        if gid in grid_ids_with_block:
            continue
        grids.append({
            "kind": f"asp:{control}",
            "id": gid,
            "data_source": attrs.get("DataSourceID", ""),
            "columns": [],
        })

    # Data-binding fields across the whole template (Eval/Bind + Razor @Model.X)
    bindings.extend(_RE_EVAL_BIND.findall(content))
    bindings.extend(_RE_RAZOR_BIND.findall(content))
    bindings = sorted(set(b for b in bindings if b))

    return {
        "schemaVersion": 1,
        "source_path": str(p),
        "template_family": family,
        "title": title,
        "forms": forms,
        "elements": elements,
        "links": links,
        "grids": grids,
        "bindings": bindings,
        "navTargets": sorted(set(nav_targets)),
    }


def _extract_grid_columns(grid_inner: str) -> list[dict[str, str]]:
    """Parse <Columns> of an ASP grid into [{header, dataField}] (L4)."""
    columns: list[dict[str, str]] = []
    for m in _RE_BOUNDFIELD.finditer(grid_inner):
        attrs = _parse_attrs(m.group(1))
        columns.append({
            "header": attrs.get("HeaderText", attrs.get("DataField", "")),
            "dataField": attrs.get("DataField", ""),
            "kind": "BoundField",
        })
    for m in _RE_TEMPLATEFIELD.finditer(grid_inner):
        attrs = _parse_attrs(m.group(1))
        columns.append({
            "header": attrs.get("HeaderText", ""),
            "dataField": "",
            "kind": "TemplateField",
        })
    for m in _RE_GRID_FIELD_OTHER.finditer(grid_inner):
        kind = m.group(1)
        attrs = _parse_attrs(m.group(2))
        columns.append({
            "header": attrs.get("HeaderText", attrs.get("Text", kind)),
            "dataField": attrs.get("DataField", attrs.get("DataNavigateUrlFields", "")),
            "kind": kind,
        })
    return columns
