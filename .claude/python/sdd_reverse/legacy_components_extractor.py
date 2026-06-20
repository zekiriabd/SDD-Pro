"""SDD_Pro Reverse Engineering Phase 4 — Legacy components extractor (library).

Heuristic parser : analyzes captured HTML to detect common UI patterns and
emits a markdown table at workspace/input/ui/_legacy-style/components-inventory.md
matching design doc §5.3.

Detected components :
- Grid / DataTable : <table> with >= 5 rows or class contains datatable/grid/table
- Form CRUD       : <form> with >= 3 <input>/<select> + submit button
- Navigation menu : <nav> or <ul> with >= 3 links inside <header> / master
- Modal / Dialog  : <div> with class containing modal/dialog/popup or aria-modal=true
- Pagination      : <ul>/<nav> with class containing pagination/pager
- Filter panel    : <div> with >= 2 inputs + button "Rechercher|Search|Filter"

Pure stdlib (html.parser). No bs4, no lxml. Fully testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


# --------------------------------------------------------------- thresholds


GRID_MIN_ROWS = 5
FORM_MIN_INPUTS = 3
NAV_MIN_LINKS = 3
FILTER_MIN_INPUTS = 2

GRID_CLASS_PATTERN = re.compile(r"\b(datatable|grid|table-grid|gridview)\b", re.I)
MODAL_CLASS_PATTERN = re.compile(r"\b(modal|dialog|popup)\b", re.I)
PAGINATION_CLASS_PATTERN = re.compile(r"\b(pagination|pager|page-numbers)\b", re.I)
FILTER_BUTTON_LABEL = re.compile(
    r"^\s*(rechercher|recherche|chercher|search|filter|filtrer|appliquer)\s*$",
    re.I,
)


# ------------------------------------------------------------- data types


@dataclass
class DetectedComponent:
    """A single UI pattern detected on a page."""

    kind: str  # 'grid', 'form', 'nav', 'modal', 'pagination', 'filter'
    label: str  # Human-readable label
    suggestion: str  # DS moderne suggestion (shadcn/Radzen mapping)
    occurrences: int = 1


@dataclass
class PageInventory:
    """All components detected for ONE page (= one unit)."""

    unit_id: str
    page_path: str  # e.g. "/Default.aspx"
    components: list[DetectedComponent] = field(default_factory=list)


@dataclass
class GlobalInventory:
    """Aggregated inventory across all pages of a project."""

    pages: list[PageInventory] = field(default_factory=list)

    def aggregate_by_kind(self) -> dict[str, dict]:
        """Return {kind: {label, suggestion, total_occurrences, pages: [unit_ids]}}."""
        by_kind: dict[str, dict] = {}
        for page in self.pages:
            for comp in page.components:
                bucket = by_kind.setdefault(
                    comp.kind,
                    {
                        "label": comp.label,
                        "suggestion": comp.suggestion,
                        "total_occurrences": 0,
                        "pages": [],
                    },
                )
                bucket["total_occurrences"] += comp.occurrences
                if page.page_path not in bucket["pages"]:
                    bucket["pages"].append(page.page_path)
        return by_kind


# ---------------------------------------------------------- HTML parser


class _ComponentParser(HTMLParser):
    """Stateful HTML traversal collecting structural signals.

    We deliberately avoid building a full DOM tree (stdlib html.parser is
    streaming). Instead, we track nesting via a small element stack and
    accumulate counts/classes that are inspected lazily at the end.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # Element stack as (tag, attrs_dict, child_counts)
        self._stack: list[dict] = []
        # Completed elements list — populated when closing tag matches
        self.elements: list[dict] = []
        # Buffer for text inside the currently-most-nested button-like element
        self._current_button_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        frame = {
            "tag": tag,
            "attrs": attrs_dict,
            "child_counts": {
                "tr": 0, "input": 0, "select": 0, "textarea": 0,
                "a": 0, "button": 0,
            },
            "button_text_parts": [],  # accumulator if tag is button
            "filter_button_label_matched": False,
        }
        self._stack.append(frame)

        # Bubble up child counts to ALL ancestors (depth-arbitrary)
        if self._stack:
            for ancestor in self._stack[:-1]:
                if tag in ancestor["child_counts"]:
                    ancestor["child_counts"][tag] += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        while self._stack:
            frame = self._stack.pop()
            if frame["tag"] == tag:
                # Persist completed element
                self.elements.append(frame)
                # If this was a button, propagate "filter button" flag up to parent
                if frame["tag"] in ("button", "input"):
                    text = "".join(frame["button_text_parts"]).strip()
                    value_attr = frame["attrs"].get("value", "")
                    label_text = text or value_attr
                    if FILTER_BUTTON_LABEL.match(label_text):
                        for ancestor in self._stack:
                            ancestor["filter_button_label_matched"] = True
                break
            else:
                # Unmatched : tolerant (malformed HTML)
                self.elements.append(frame)

    def handle_data(self, data: str) -> None:
        # Accumulate text only into the innermost button-like element
        for frame in reversed(self._stack):
            if frame["tag"] in ("button", "input"):
                frame["button_text_parts"].append(data)
                break


# ---------------------------------------------------------- detection


def detect_components_in_html(html: str) -> list[DetectedComponent]:
    """Run heuristics on a single HTML string. Returns the list of detections."""
    parser = _ComponentParser()
    parser.feed(html)
    parser.close()

    detections: list[DetectedComponent] = []

    # Index elements by tag for cheap scan
    by_tag: dict[str, list[dict]] = {}
    for el in parser.elements:
        by_tag.setdefault(el["tag"], []).append(el)

    # 1. Grids / DataTables : <table> with >= GRID_MIN_ROWS or class match
    for table in by_tag.get("table", []):
        tr_count = table["child_counts"]["tr"]
        cls = table["attrs"].get("class", "")
        if tr_count >= GRID_MIN_ROWS or GRID_CLASS_PATTERN.search(cls):
            detections.append(
                DetectedComponent(
                    kind="grid",
                    label=_label_grid(table),
                    suggestion="<Table> shadcn / <DataTable> Radzen",
                )
            )

    # 2. Forms CRUD : <form> with >= FORM_MIN_INPUTS form controls
    for form in by_tag.get("form", []):
        input_count = (
            form["child_counts"]["input"]
            + form["child_counts"]["select"]
            + form["child_counts"]["textarea"]
        )
        button_count = form["child_counts"]["button"]
        if input_count >= FORM_MIN_INPUTS and button_count >= 1:
            detections.append(
                DetectedComponent(
                    kind="form",
                    label="Formulaire CRUD",
                    suggestion="<Form> + <Field> shadcn",
                )
            )

    # 3. Navigation menus : <nav> with >= NAV_MIN_LINKS
    for nav in by_tag.get("nav", []):
        link_count = nav["child_counts"]["a"]
        if link_count >= NAV_MIN_LINKS:
            detections.append(
                DetectedComponent(
                    kind="nav",
                    label="Menu de navigation",
                    suggestion="<NavigationMenu> shadcn / <Sidebar>",
                )
            )

    # 4. Modals / Dialogs : <div> with class matching pattern OR aria-modal=true
    for div in by_tag.get("div", []):
        cls = div["attrs"].get("class", "")
        aria_modal = div["attrs"].get("aria-modal", "").lower()
        if MODAL_CLASS_PATTERN.search(cls) or aria_modal == "true":
            detections.append(
                DetectedComponent(
                    kind="modal",
                    label="Modal / Dialog",
                    suggestion="<Dialog> shadcn",
                )
            )

    # 5. Pagination : <ul>/<nav>/<div> with class match
    for tag_name in ("ul", "nav", "div"):
        for el in by_tag.get(tag_name, []):
            cls = el["attrs"].get("class", "")
            if PAGINATION_CLASS_PATTERN.search(cls):
                detections.append(
                    DetectedComponent(
                        kind="pagination",
                        label="Pagination",
                        suggestion="<Pagination> shadcn",
                    )
                )

    # 6. Filter panel : <div> or <form> with >= FILTER_MIN_INPUTS + filter button
    for tag_name in ("div", "form", "section"):
        for el in by_tag.get(tag_name, []):
            input_count = (
                el["child_counts"]["input"]
                + el["child_counts"]["select"]
            )
            if (
                input_count >= FILTER_MIN_INPUTS
                and el.get("filter_button_label_matched")
            ):
                detections.append(
                    DetectedComponent(
                        kind="filter",
                        label="Filtres / Recherche",
                        suggestion="<Card> + champs shadcn",
                    )
                )

    return _deduplicate(detections)


def _deduplicate(detections: list[DetectedComponent]) -> list[DetectedComponent]:
    """Collapse multiple detections of the same kind into a single one with occurrences."""
    by_kind: dict[str, DetectedComponent] = {}
    for d in detections:
        if d.kind in by_kind:
            by_kind[d.kind].occurrences += d.occurrences
        else:
            by_kind[d.kind] = DetectedComponent(
                kind=d.kind, label=d.label, suggestion=d.suggestion,
                occurrences=d.occurrences,
            )
    return list(by_kind.values())


def _label_grid(table_frame: dict) -> str:
    """Build a label for a detected grid : use id/class if present, else generic."""
    table_id = table_frame["attrs"].get("id", "")
    if table_id:
        return f"Grille ({table_id})"
    return "Grille / DataTable"


# ---------------------------------------------------------- markdown emit


def emit_inventory_markdown(
    inventory: GlobalInventory,
    *,
    project_name: str = "",
    extraction_date: str = "",
) -> str:
    """Render the global inventory as components-inventory.md per design doc §5.3."""
    lines: list[str] = []
    lines.append(f"# Composants UI legacy detectes — {project_name or 'projet'}")
    lines.append("")
    if extraction_date:
        lines.append(f"> Reference designer pour mapping vers DS moderne (capture runtime du {extraction_date})")
        lines.append("")

    aggregated = inventory.aggregate_by_kind()
    if not aggregated:
        lines.append("_Aucun composant detecte._")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Composant legacy | Occurrences | Pages | Suggestion DS moderne |")
    lines.append("|---|---|---|---|")

    # Sort by total_occurrences DESC for readability
    sorted_kinds = sorted(
        aggregated.items(),
        key=lambda kv: -kv[1]["total_occurrences"],
    )
    for kind, info in sorted_kinds:
        pages_str = ", ".join(info["pages"][:5])
        if len(info["pages"]) > 5:
            pages_str += f" (+{len(info['pages']) - 5})"
        lines.append(
            f"| {info['label']} | {info['total_occurrences']} | {pages_str} | {info['suggestion']} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------- persistence


def write_components_inventory(
    inventory: GlobalInventory,
    target_path: Path,
    *,
    project_name: str = "",
    extraction_date: str = "",
) -> None:
    """Atomic write of components-inventory.md."""
    md = emit_inventory_markdown(
        inventory,
        project_name=project_name,
        extraction_date=extraction_date,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = target_path.with_suffix(target_path.suffix + ".sddtmp")
    tmp.write_text(md, encoding="utf-8")
    tmp.replace(target_path)


# ---------------------------------------------------------- entry helper


def build_inventory_from_captures(
    captures: Iterable[tuple[str, str, str]],
) -> GlobalInventory:
    """Build a GlobalInventory from an iterable of (unit_id, page_path, html).

    Convenience for the orchestrator (/sdd-reverse-ui) which holds the captures
    in memory.
    """
    inv = GlobalInventory()
    for unit_id, page_path, html in captures:
        components = detect_components_in_html(html)
        inv.pages.append(
            PageInventory(
                unit_id=unit_id,
                page_path=page_path,
                components=components,
            )
        )
    return inv
