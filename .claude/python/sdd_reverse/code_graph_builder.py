"""code_graph_builder.py — Symbol-level code graph for legacy projects (L0).

This is the structural fix for the reverse pipeline's root weakness: before L0
a functional unit's evidence was capped at ``[page, code-behind]`` and the deep
business layer (services, repositories, DTOs, data access) was structurally
invisible to the Phase 3 extractor. The code graph follows the class-reference
chain from each UI entry point into those classes so they can be:

    1. enumerated and role-classified (cf. ``class_role_classifier``)
    2. attached to ``units[].classes`` in inventory.json
    3. added (bounded) to ``units[].evidenceFiles`` so the extractor agent is
       allowed to read them

Scope L0: C# (the dominant legacy case — ASP.NET WebForms/MVC with many
classes). VB.NET is parsed best-effort with the same declaration regex family.
Other languages (Java, PHP) degrade gracefully to an empty graph and are added
in later lots; their units keep the seed evidence unchanged.

Public API:
    parse_source_classes(rel_path, text) -> list[ClassInfo]
    build_code_graph(project_root, scan_result, known_entity_names=None) -> dict
    enrich_units(units, code_graph, *, max_depth=3, max_added_files=30) -> None

``code-graph.json`` shape (design doc §5.5, new in L0):
    {
      "schemaVersion": 1,
      "project": str,
      "buildDate": ISO-8601,
      "language": "csharp" | ...,
      "classes": [ ClassInfo.to_public_dict(), ... ],
      "edges": [ {"from","to","kind":"reference","evidence":"file:line"} ],
      "rolesSummary": { role: count, ... },
      "filesAnalyzed": int
    }
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from sdd_reverse.class_role_classifier import (
    ClassInfo,
    classify_role,
    detect_touches_http,
    detect_touches_sql,
)
from sdd_reverse.scan_legacy import decode_text, normalize_bytes

CODE_GRAPH_SCHEMA_VERSION = 1

# Extensions analyzed for the symbol-level graph (L0 = .NET object code).
_ANALYZED_EXTENSIONS = frozenset({".cs", ".vb"})

# --- declaration regexes (run over comment/string-masked text) ---------------
# Captures: leading modifiers, kind keyword, name (+ optional generics), and the
# base-list up to `{` / `where`. Generics in the name (`Repo<T>`) tolerated.
_RE_TYPE_DECL = re.compile(
    r"(?P<mods>(?:\b(?:public|private|protected|internal|static|abstract|sealed|"
    r"partial|new|unsafe)\b\s+)*)"
    r"(?P<kind>class|interface|enum|struct|record)\s+"
    r"(?P<name>[A-Za-z_]\w*)"
    r"(?:\s*<[^>]*>)?"                                  # optional type params
    r"(?P<bases>\s*:\s*[^{]+?)?"                        # optional base list
    r"\s*(?:where\b[^{]*)?\{",                          # optional generic constraints
    re.MULTILINE,
)

_RE_NAMESPACE = re.compile(r"\bnamespace\s+([A-Za-z_][\w.]*)", re.MULTILINE)

# Method-like signature within a class body (masked text). Excludes control-flow
# keywords that share the `kw (...)` shape.
_RE_METHOD = re.compile(
    r"(?:\b(?:public|private|protected|internal|static|virtual|override|async|"
    r"sealed|abstract|extern|new|partial|unsafe)\b\s+)*"
    r"[\w<>\[\],\.\?]+\s+"                              # return type
    r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:\{|=>|where\b)",
)
_CONTROL_KEYWORDS = frozenset({
    "if", "for", "foreach", "while", "switch", "using", "lock", "catch",
    "fixed", "return", "do", "else", "get", "set", "add", "remove",
})

# Auto / full property within a class body (masked text).
_RE_PROPERTY = re.compile(
    r"(?:\b(?:public|private|protected|internal|static|virtual|override|new)\b\s+)+"
    r"[\w<>\[\],\.\?]+\s+[A-Za-z_]\w*\s*\{\s*get",
)


def _mask_comments_and_strings(text: str) -> str:
    """Replace C#/VB comment + string/char literal interiors with spaces.

    Preserves length and newline positions so byte/line offsets computed on the
    masked text map 1:1 back onto the original. Prevents braces, class names and
    keywords *inside* comments or string literals from corrupting structural
    detection (e.g. a SQL string containing `class` or `{`).
    """
    out = list(text)
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # Line comment // ... (C#) — keep newline
        if c == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        # Block comment /* ... */
        if c == "/" and nxt == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
            continue
        # VB line comment ' ...
        if c == "'" and not _looks_like_csharp_char_literal(text, i):
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        # Verbatim / interpolated string @"..." or $"..." or "..."
        if c == '"':
            # detect verbatim (preceded by @) → "" is an escaped quote
            verbatim = i > 0 and text[i - 1] in ("@",)
            out[i] = " "
            i += 1
            while i < n:
                if text[i] == '"':
                    if verbatim and i + 1 < n and text[i + 1] == '"':
                        out[i] = out[i + 1] = " "
                        i += 2
                        continue
                    if not verbatim:
                        # Escaped iff preceded by an ODD number of backslashes.
                        # (`"\\"` ends the string — the backslash is itself
                        # escaped. Run EDI 2026-06-10 : the naive `text[i-1]
                        # == "\\"` check made the masker eat the rest of the
                        # file after a `"\\"` path literal, truncating every
                        # class below it to 1 line.)
                        k = i - 1
                        nb = 0
                        while k >= 0 and text[k] == "\\":
                            nb += 1
                            k -= 1
                        if nb % 2 == 1:
                            out[i] = " "
                            i += 1
                            continue
                    out[i] = " "
                    i += 1
                    break
                if not verbatim and text[i] == "\n":
                    # Non-verbatim C# strings cannot span lines — resync
                    # defensively instead of swallowing the file.
                    break
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        # Char literal 'x'
        if c == "'":
            out[i] = " "
            i += 1
            while i < n and text[i] != "'":
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def _looks_like_csharp_char_literal(text: str, i: int) -> bool:
    """Heuristic: is the quote at `i` a C# char literal `'x'` rather than VB comment?

    We only need to avoid treating `'a'` as a VB comment in C# files. If a
    closing `'` appears within the next 3 chars, treat as char literal.
    """
    return bool(re.match(r"'(?:\\.|[^'\\])'", text[i:i + 4]))


def _line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _simple_type_name(qualified: str) -> str:
    """`System.Web.UI.Page` → `Page`; `IRepository<User>` → `IRepository`."""
    base = qualified.strip().split("<", 1)[0].strip()
    return base.rsplit(".", 1)[-1].strip()


def _extract_leading_attributes(text: str, decl_start: int) -> list[str]:
    """Collect consecutive `[Attr...]` lines immediately before a declaration."""
    # Walk backwards over the lines preceding decl_start.
    head = text[:decl_start]
    lines = head.splitlines()
    attrs: list[str] = []
    for line in reversed(lines):
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            # strip brackets, keep names like ApiController / Table("x")
            attrs.append(s[1:-1].strip())
            continue
        break
    return list(reversed(attrs))


def parse_source_classes(rel_path: str, text: str) -> list[ClassInfo]:
    """Parse one .cs/.vb file into ClassInfo records (structural, best-effort)."""
    masked = _mask_comments_and_strings(text)
    classes: list[ClassInfo] = []

    # Pre-compute namespace spans (offset → namespace name). Simple model: the
    # last `namespace X` declared before a class applies.
    ns_marks = [(m.start(), m.group(1)) for m in _RE_NAMESPACE.finditer(masked)]

    def ns_for(offset: int) -> str:
        ns = ""
        for pos, name in ns_marks:
            if pos < offset:
                ns = name
            else:
                break
        return ns

    for m in _RE_TYPE_DECL.finditer(masked):
        name = m.group("name")
        kind = m.group("kind")
        mods = (m.group("mods") or "").lower()
        bases_raw = m.group("bases") or ""
        decl_start = m.start()

        # Find matching closing brace for the class body via depth walk on masked.
        open_brace = masked.find("{", m.end() - 1)
        if open_brace == -1:
            continue
        depth = 0
        end = open_brace
        for idx in range(open_brace, len(masked)):
            ch = masked[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        body_masked = masked[open_brace:end + 1]
        body_original = text[open_brace:end + 1]

        base_types = []
        if bases_raw:
            for part in bases_raw.strip().lstrip(":").split(","):
                sn = _simple_type_name(part)
                if sn:
                    base_types.append(sn)

        # Method count (exclude control-flow false positives).
        method_names = [
            mm.group("name") for mm in _RE_METHOD.finditer(body_masked)
            if mm.group("name") not in _CONTROL_KEYWORDS
        ]
        method_count = len(method_names)
        property_count = len(_RE_PROPERTY.findall(body_masked))

        loc_total = sum(1 for ln in body_original.splitlines() if ln.strip())

        ci = ClassInfo(
            name=name,
            kind=kind,
            file=rel_path,
            namespace=ns_for(decl_start),
            base_types=base_types,
            attributes=_extract_leading_attributes(text, decl_start),
            is_static="static" in mods,
            is_partial="partial" in mods,
            is_abstract="abstract" in mods,
            method_count=method_count,
            property_count=property_count,
            loc_total=loc_total,
            line_start=_line_of_offset(text, decl_start),
            line_end=_line_of_offset(text, end),
            touches_sql=detect_touches_sql(body_original),
            touches_http=detect_touches_http(body_original),
        )
        ci._body = body_masked  # masked → references won't match names in strings
        classes.append(ci)

    return classes


# --- VB.NET structural parsing (audit 2026-06-10 C7) -------------------------
# VB has no braces : the C# `_RE_TYPE_DECL` (which requires `{`) never matched,
# so `.vb` in `_ANALYZED_EXTENSIONS` was unreachable dead code and a VB.NET
# legacy produced an EMPTY graph silently. Best-effort line-based parsing of
# `Class … End Class` (+ Module/Interface/Enum/Structure).

_RE_VB_TYPE_DECL = re.compile(
    r"^[ \t]*(?P<mods>(?:(?:Public|Private|Protected|Friend|Shared|Partial|"
    r"MustInherit|NotInheritable)\s+)*)"
    r"(?P<kind>Class|Interface|Enum|Structure|Module)\s+(?P<name>[A-Za-z_]\w*)",
    re.IGNORECASE | re.MULTILINE,
)
_RE_VB_NAMESPACE = re.compile(r"^[ \t]*Namespace\s+([A-Za-z_][\w.]*)", re.IGNORECASE | re.MULTILINE)
_RE_VB_INHERITS = re.compile(r"^[ \t]*(?:Inherits|Implements)\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_RE_VB_METHOD = re.compile(
    r"^[ \t]*(?:(?:Public|Private|Protected|Friend|Shared|Overrides|Overridable|"
    r"MustOverride|Async|Partial)\s+)*(?:Sub|Function)\s+(?P<name>[A-Za-z_]\w*)\s*\(",
    re.IGNORECASE | re.MULTILINE,
)
_RE_VB_PROPERTY = re.compile(
    r"^[ \t]*(?:(?:Public|Private|Protected|Friend|Shared|ReadOnly|WriteOnly)\s+)*"
    r"Property\s+[A-Za-z_]\w*",
    re.IGNORECASE | re.MULTILINE,
)

_VB_KIND_MAP = {
    "class": "class", "interface": "interface", "enum": "enum",
    "structure": "struct", "module": "class",
}


def parse_source_classes_vb(rel_path: str, text: str) -> list[ClassInfo]:
    """Parse one .vb file into ClassInfo records (line-based, best-effort)."""
    masked = _mask_comments_and_strings(text)
    classes: list[ClassInfo] = []

    ns_marks = [(m.start(), m.group(1)) for m in _RE_VB_NAMESPACE.finditer(masked)]

    def ns_for(offset: int) -> str:
        ns = ""
        for pos, name in ns_marks:
            if pos < offset:
                ns = name
            else:
                break
        return ns

    lines = masked.splitlines(keepends=True)
    # Precompute line start offsets for offset↔line mapping.
    offsets: list[int] = []
    acc = 0
    for ln in lines:
        offsets.append(acc)
        acc += len(ln)

    for m in _RE_VB_TYPE_DECL.finditer(masked):
        kind_kw = m.group("kind").lower()
        name = m.group("name")
        mods = (m.group("mods") or "").lower()
        decl_start = m.start()
        decl_line_idx = masked.count("\n", 0, decl_start)

        # Walk forward line by line, matching `End {kind}` at depth 0 (nested
        # same-kind declarations tracked naively).
        depth = 1
        end_line_idx = decl_line_idx
        end_kw = re.compile(rf"^[ \t]*End\s+{kind_kw}\b", re.IGNORECASE)
        nest_kw = re.compile(
            rf"^[ \t]*(?:(?:Public|Private|Protected|Friend|Shared|Partial|"
            rf"MustInherit|NotInheritable)\s+)*{kind_kw}\s+[A-Za-z_]", re.IGNORECASE)
        for idx in range(decl_line_idx + 1, len(lines)):
            line = lines[idx]
            if nest_kw.match(line):
                depth += 1
            elif end_kw.match(line):
                depth -= 1
                if depth == 0:
                    end_line_idx = idx
                    break
        else:
            end_line_idx = len(lines) - 1

        body_start = offsets[decl_line_idx]
        body_end = (offsets[end_line_idx] + len(lines[end_line_idx])
                    if end_line_idx < len(lines) else len(masked))
        body_masked = masked[body_start:body_end]
        body_original = text[body_start:body_end]

        base_types = []
        for bm in _RE_VB_INHERITS.finditer(body_masked):
            for part in bm.group(1).split(","):
                sn = _simple_type_name(part)
                if sn:
                    base_types.append(sn)

        method_names = [mm.group("name") for mm in _RE_VB_METHOD.finditer(body_masked)]
        property_count = len(_RE_VB_PROPERTY.findall(body_masked))
        loc_total = sum(1 for ln in body_original.splitlines() if ln.strip())

        ci = ClassInfo(
            name=name,
            kind=_VB_KIND_MAP.get(kind_kw, "class"),
            file=rel_path,
            namespace=ns_for(decl_start),
            base_types=base_types,
            attributes=[],
            is_static=(kind_kw == "module"),
            is_partial="partial" in mods,
            is_abstract="mustinherit" in mods,
            method_count=len(method_names),
            property_count=property_count,
            loc_total=loc_total,
            line_start=decl_line_idx + 1,
            line_end=end_line_idx + 1,
            touches_sql=detect_touches_sql(body_original),
            touches_http=detect_touches_http(body_original),
        )
        ci._body = body_masked
        classes.append(ci)

    return classes


def build_code_graph(
    project_root: str | Path,
    scan_result: Any,
    known_entity_names: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Parse all analyzed source files into a project-wide class graph.

    Returns the serializable code-graph.json dict. Empty (but well-formed) when
    no analyzable source is present (non-.NET legacy in L0).
    """
    root = Path(project_root).resolve()
    known_entity_names = known_entity_names or frozenset()

    # Collect analyzable files from the scan result (already filtered/normalized).
    files: list[Path] = []
    seen: set[str] = set()
    for lm in getattr(scan_result, "languages", []):
        for f in lm.files:
            if f.suffix.lower() in _ANALYZED_EXTENSIONS:
                key = str(f)
                if key not in seen:
                    seen.add(key)
                    files.append(f)

    all_classes: list[ClassInfo] = []
    for f in files:
        try:
            text = decode_text(normalize_bytes(f.read_bytes()))
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        if f.suffix.lower() == ".vb":
            all_classes.extend(parse_source_classes_vb(rel, text))   # C7
        else:
            all_classes.extend(parse_source_classes(rel, text))

    # Registry: simple name → ClassInfo (first declaration wins on collision).
    by_name: dict[str, ClassInfo] = {}
    for ci in all_classes:
        by_name.setdefault(ci.name, ci)

    known_names = set(by_name.keys())
    edges: list[dict[str, Any]] = []

    # Reference edges: for each class, find which OTHER known class names appear
    # in its (masked) body. Coarse but sufficient for evidence enrichment.
    for ci in all_classes:
        body = ci._body or ""
        local_refs: set[str] = set()
        for other in known_names:
            if other == ci.name:
                continue
            # word-boundary match; require the name to appear as an identifier.
            mm = re.search(r"\b" + re.escape(other) + r"\b", body)
            if mm:
                local_refs.add(other)
                line = ci.line_start + body.count("\n", 0, mm.start())
                edges.append({
                    "from": ci.name,
                    "to": other,
                    "kind": "reference",
                    "evidence": f"{ci.file}:{line}",
                })
        ci.references = sorted(local_refs)
        ci.role = classify_role(ci, known_entity_names)

    roles_summary: dict[str, int] = {}
    for ci in all_classes:
        roles_summary[ci.role] = roles_summary.get(ci.role, 0) + 1

    return {
        "schemaVersion": CODE_GRAPH_SCHEMA_VERSION,
        "project": root.name,
        "buildDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "language": getattr(scan_result, "primary_language", None),
        "classes": [ci.to_public_dict() for ci in all_classes],
        "edges": edges,
        "rolesSummary": roles_summary,
        "filesAnalyzed": len(files),
    }


# Markup extensions whose seed files are scanned for class-name references
# (audit 2026-06-10 C1 : in MVVM the XAML names the ViewModel via DataContext /
# ViewModelLocator binding — a *textual* reference, never a C# declaration, so
# the declared-classes-only seeding left the whole VM/business layer invisible).
_MARKUP_SEED_EXTENSIONS = frozenset({
    ".xaml", ".aspx", ".ascx", ".master", ".cshtml", ".vbhtml",
    ".jsp", ".jspx", ".xhtml", ".php",
})

# View-class suffixes used by the MVVM naming-convention fallback
# (`MainWindow` → `MainViewModel` / `MainWindowViewModel`).
_VIEW_CLASS_SUFFIXES = ("Window", "View", "Page", "UserControl", "Form", "Dialog", "Control")

_IDENTIFIER_RE = re.compile(r"[A-Za-z_]\w*")


def _markup_seed_classes(
    seed_files: list[str],
    project_root: Path | None,
    known_names: set[str],
) -> set[str]:
    """Known class names textually referenced in the unit's markup seed files.

    Catches `<local:FooViewModel/>`, `x:Class=`, `DataContext="{Binding ...}"`
    resource keys, `<asp:ObjectDataSource TypeName=...>`, etc. Implemented as
    identifier-set intersection (O(text + names)), not per-name regex.
    """
    if project_root is None:
        return set()
    root = Path(project_root)
    found: set[str] = set()
    for rel in seed_files:
        if Path(rel).suffix.lower() not in _MARKUP_SEED_EXTENSIONS:
            continue
        try:
            raw = (root / rel).read_bytes()
        except OSError:
            continue
        text = decode_text(normalize_bytes(raw))
        found |= set(_IDENTIFIER_RE.findall(text)) & known_names
    return found


# ViewModelLocator resolution (audit C1, run EDI 2026-06-10) : the dominant
# MVVM-Light binding form is `DataContext="{Binding Prop, Source={StaticResource
# Locator}}"` — neither the VM class name nor the naming convention appears in
# the markup. We resolve `Prop` through the locator class's property map.
_LOCATOR_BINDING_RE = re.compile(
    r"\{Binding\s+(\w+)\s*,\s*Source=\{StaticResource\s+\w*[Ll]ocator\}",
)
_LOCATOR_PROPERTY_RE = re.compile(
    r"(?:public|internal)\s+(?:static\s+)?([A-Z]\w*)\s+(\w+)\s*(?:=>|\{\s*get)",
)


def _build_locator_property_map(
    classes: list[dict[str, Any]], project_root: Path | None,
) -> dict[str, str]:
    """property name → VM class name, from every `*Locator` class file."""
    if project_root is None:
        return {}
    out: dict[str, str] = {}
    seen_files: set[str] = set()
    for c in classes:
        if "locator" not in c["name"].lower() or c["file"] in seen_files:
            continue
        seen_files.add(c["file"])
        try:
            text = decode_text(normalize_bytes((Path(project_root) / c["file"]).read_bytes()))
        except OSError:
            continue
        for type_name, prop_name in _LOCATOR_PROPERTY_RE.findall(text):
            out[prop_name] = type_name
    return out


def _locator_bound_classes(
    seed_files: list[str],
    project_root: Path | None,
    locator_map: dict[str, str],
    known_names: set[str],
) -> set[str]:
    """Resolve `{Binding X, Source={StaticResource Locator}}` → VM classes."""
    if project_root is None or not locator_map:
        return set()
    root = Path(project_root)
    found: set[str] = set()
    for rel in seed_files:
        if Path(rel).suffix.lower() not in _MARKUP_SEED_EXTENSIONS:
            continue
        try:
            text = decode_text(normalize_bytes((root / rel).read_bytes()))
        except OSError:
            continue
        for prop in _LOCATOR_BINDING_RE.findall(text):
            cls = locator_map.get(prop)
            if cls and cls in known_names:
                found.add(cls)
    return found


def _mvvm_convention_classes(seed_class_names: set[str], known_names: set[str]) -> set[str]:
    """MVVM convention fallback : `FooWindow`/`FooView` → `Foo[Window]ViewModel`.

    Covers ViewModelLocator bindings (`{Binding Main, Source={StaticResource
    Locator}}`) where the VM class name never appears in the XAML text.
    """
    out: set[str] = set()
    for n in seed_class_names:
        stems = {n}
        for suf in _VIEW_CLASS_SUFFIXES:
            if n.endswith(suf) and len(n) > len(suf):
                stems.add(n[: -len(suf)])
        for stem in stems:
            for cand in (stem + "ViewModel", stem + "VM"):
                if cand in known_names:
                    out.add(cand)
    return out


def enrich_units(
    units: list[dict[str, Any]],
    code_graph: dict[str, Any],
    *,
    max_depth: int = 3,
    max_added_files: int = 30,
    project_root: str | Path | None = None,
) -> None:
    """Enrich each unit in-place with transitive evidence + class metadata.

    For each unit:
      - ``seedEvidenceFiles`` records the original [page, code-behind] (provenance;
        the U-N fingerprint is computed from this, NOT from the enriched set, so
        graph-walk changes never destabilise U-N IDs).
      - the graph-walk frontier is seeded from THREE sources (audit C1) :
            1. classes *declared* in the seed files (code-behind),
            2. known classes *textually referenced* in markup seed files
               (XAML DataContext / `<local:Vm/>` / asp: TypeName bindings),
            3. MVVM naming convention (`FooWindow` → `FooViewModel`) for
               locator-style bindings that never name the VM in markup.
      - the class reference graph is walked up to ``max_depth`` hops,
        collecting reached classes' files.
      - ``evidenceFiles`` is extended (bounded by ``max_added_files``) with those
        files — these are the deep services/repositories/DTOs the extractor was
        previously forbidden to read.
      - ``classes`` lists every reached class with its role + flags.
      - ``entities`` is derived from reached repository/entity classes.
    """
    classes = code_graph.get("classes", [])
    if not classes:
        # Non-.NET legacy or empty graph — keep seed evidence, annotate provenance.
        for u in units:
            u.setdefault("seedEvidenceFiles", list(u.get("evidenceFiles", [])))
            u.setdefault("classes", [])
        return

    by_name: dict[str, dict[str, Any]] = {}
    file_to_classes: dict[str, list[dict[str, Any]]] = {}
    for c in classes:
        by_name.setdefault(c["name"], c)
        file_to_classes.setdefault(c["file"], []).append(c)

    # Adjacency: class name → referenced class names. UNION across duplicate
    # declarations (partial classes) — audit 2026-06-10 M18 : assignment
    # overwrote the first partial's references with the last one's.
    # Locator classes are SINKS (no outgoing edges) : a ViewModelLocator
    # references every VM of the app by design — traversing through it turns
    # every unit into a god-unit (run EDI : un simple dialog agrégait 30
    # classes comportementales via `ViewModelLocator.Main`). Les VMs liés au
    # SEED restent atteints via `_locator_bound_classes` (résolution ciblée).
    adj: dict[str, set[str]] = {}
    for c in classes:
        if "locator" in c["name"].lower():
            adj.setdefault(c["name"], set())
            continue
        adj.setdefault(c["name"], set()).update(c.get("references", []))

    known_names = set(by_name.keys())
    root = Path(project_root) if project_root else None
    locator_map = _build_locator_property_map(classes, root)

    for u in units:
        seed = list(u.get("evidenceFiles", []))
        u["seedEvidenceFiles"] = seed

        # Seed classes = declared in seed files + referenced in markup seeds
        # + locator-bound VMs + MVVM convention candidates (C1).
        frontier: set[str] = set()
        for f in seed:
            for c in file_to_classes.get(f, []):
                frontier.add(c["name"])
        frontier |= _markup_seed_classes(seed, root, known_names)
        frontier |= _locator_bound_classes(seed, root, locator_map, known_names)
        frontier |= _mvvm_convention_classes(frontier, known_names)

        # Track BFS depth per class : the evidence cap below keeps the
        # CLOSEST classes first (run EDI : alphabetical ordering pushed the
        # unit's own locator-bound ViewModel beyond the 30-file cap while
        # keeping distant transitive classes).
        depth_of: dict[str, int] = {cn: 0 for cn in frontier}
        reached: set[str] = set(frontier)
        depth = 0
        while frontier and depth < max_depth:
            nxt: set[str] = set()
            for cname in frontier:
                for ref in adj.get(cname, ()):  # noqa: SIM118
                    if ref not in reached:
                        nxt.add(ref)
            for cn in nxt:
                depth_of.setdefault(cn, depth + 1)
            reached |= nxt
            frontier = nxt
            depth += 1

        # Files of reached classes, excluding seed files already present.
        # Ordered by (BFS depth, name) so the cap never evicts the unit's
        # direct collaborators in favour of remote transitive ones.
        added: list[str] = []
        for cname in sorted(reached, key=lambda cn: (depth_of.get(cn, 99), cn)):
            if len(added) >= max_added_files:
                break
            c = by_name.get(cname)
            if not c:
                continue
            cf = c["file"]
            if cf not in seed and cf not in added:
                added.append(cf)

        u["evidenceFiles"] = seed + added

        # Attach role-classified class metadata for the reached set.
        unit_classes = []
        derived_entities: set[str] = set()
        for cname in sorted(reached):
            c = by_name.get(cname)
            if not c:
                continue
            unit_classes.append({
                "name": c["name"],
                "role": c["role"],
                "file": c["file"],
                "lines": c.get("lines", ""),
                "methodCount": c.get("methodCount", 0),
                "touchesSql": c.get("touchesSql", False),
                "touchesHttp": c.get("touchesHttp", False),
            })
            # Only entity-role classes are domain entities. Repositories are
            # data-access gateways, captured in `classes`, NOT entities.
            if c["role"] == "entity":
                derived_entities.add(c["name"])
        u["classes"] = unit_classes

        # Merge derived entities with any pre-existing (e.g. db_schema linkage).
        existing_entities = set(u.get("entities") or [])
        u["entities"] = sorted(existing_entities | derived_entities)
