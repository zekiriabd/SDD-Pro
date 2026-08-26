"""deps_graph_builder.py — Build a dependency graph from a scanned legacy.

Phase 2 (audit) script. Detects:
    - Internal edges (file A calls/imports file B inside the project)
    - External dependencies + EOL status (best-effort manifests : packages.config,
      package.json, pom.xml, requirements.txt, composer.json)
    - Naive cycle detection (Tarjan SCC on internal edges)
    - Dead code hints (files in scan_result but no incoming edge)

Internal edges — resolution order (audit F-03, 2026-08-25)
----------------------------------------------------------
Phase 1 already produced ``code-graph.json`` with **type-usage resolved**
class-to-class edges (``code_graph_builder.build_code_graph``). This module
projects those edges down to file level FIRST, then adds its own
namespace+import heuristic as a *supplement* for the families the code graph
does not cover (Java, PHP, JS/TS relative imports).

The namespace heuristic alone was structurally blind on a large share of real
.NET legacy: ``App_Code/*.cs`` in a WebForms application declares no
``namespace``, so ``namespace_to_file`` stayed empty, no edge was ever emitted,
and ``deadCodeHint`` reported *every* file as unreferenced. That list feeds the
``reverse-tech-auditor`` agent, ``tech-audit.md``, the MIGRATE/DISCARD curation
of ``/sdd-reverse-paradigm`` and the C4 component diagram — a Tech Lead was
being told a perfectly live legacy was 100% dead code.

Public API:
    build_deps_graph(project_root, scan_result, code_graph=None) -> dict

Output shape: design doc §5.4.

Best-effort regex parsing — not a static analyzer. Aimed at giving the
tech-auditor LLM seed material to narrate, not at IDE-grade precision.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import ScanResult, decode_text, normalize_bytes, read_text_normalized as _read_text

# Naive EOL deadline map for common ecosystems (informational only)
EOL_HINTS = {
    # .NET — packages with known EOL or critical CVEs (sample)
    "log4net": {"versions_before": "2.0.10", "eol_date": "2014-12-31", "reason": "CVE-2018-1285 + dormant"},
    "Newtonsoft.Json": {"versions_before": "13.0.0", "eol_date": None, "reason": "Replaced by System.Text.Json"},
    "EntityFramework": {"versions_before": "6.5.0", "eol_date": None, "reason": "EF6 maintenance mode, prefer EF Core"},
    # Node — sample
    "moment": {"versions_before": None, "eol_date": "2020-09-15", "reason": "Project in maintenance mode, use date-fns / dayjs"},
    "request": {"versions_before": None, "eol_date": "2020-02-11", "reason": "Deprecated, use axios / undici"},
    # Java — sample. Key = groupId:artifactId (matchable — audit M17 : the old
    # key `commons-collections:3` could never match a parsed Maven name).
    "commons-collections:commons-collections": {"versions_before": "3.2.2", "eol_date": "2015-11-04", "reason": "CVE-2015-7501 RCE"},
    # PHP — sample
    "swiftmailer/swiftmailer": {"versions_before": None, "eol_date": "2021-11-08", "reason": "Use symfony/mailer"},
}

# Manifest parsers
_RE_PACKAGES_CONFIG = re.compile(r'<package\s+id="([^"]+)"\s+version="([^"]+)"', re.IGNORECASE)
_RE_NPM_DEP = re.compile(r'"([^"]+)"\s*:\s*"\^?~?([^"]+)"')
_RE_MAVEN_DEP = re.compile(
    r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>\s*(?:<version>([^<]+)</version>)?",
    re.IGNORECASE | re.DOTALL,
)
_RE_PIP_REQ = re.compile(r"^([A-Za-z0-9_\-.]+)(?:[><=!~]+([0-9.]+))?", re.MULTILINE)
_RE_COMPOSER_DEP = re.compile(r'"([^"]+/[^"]+)"\s*:\s*"\^?~?([^"]+)"')

# Internal edge detection (C# using/import + JS import + Java import + PHP use)
_RE_CSHARP_USING = re.compile(r"^\s*using\s+([A-Za-z_][\w.]+);", re.MULTILINE)
_RE_JS_IMPORT = re.compile(r"""(?:^\s*import\s+.+?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""", re.MULTILINE)
_RE_JAVA_IMPORT = re.compile(r"^\s*import\s+([A-Za-z_][\w.]+);", re.MULTILINE)
_RE_PHP_USE = re.compile(r"^\s*use\s+([A-Za-z_][\w\\]+);", re.MULTILINE)


# _read_text centralise dans scan_legacy (audit 2026-06-11 B5 — cap 5 Mo).


def _parse_packages_config(content: str) -> list[tuple[str, str]]:
    return _RE_PACKAGES_CONFIG.findall(content)


_NPM_DEP_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",        # P3.12 — was missing
    "optionalDependencies",    # P3.12 — was missing
)


def _parse_npm_json(content: str) -> list[tuple[str, str]]:
    """Extract dependencies from package.json across the 4 standard sections.

    P3.12 closure (2026-06-10) — switched from regex slicing (which broke
    on nested objects and silently dropped 3 of the 4 standard npm dep
    sections) to a proper ``json.loads`` parse with regex fallback for
    malformed legacy manifests.

    Reads, in priority order :
        1. ``dependencies``
        2. ``devDependencies``
        3. ``peerDependencies``  (was missing before — breaks lib auditing)
        4. ``optionalDependencies`` (was missing — affects EOL detection)

    Falls back to the old regex-based extraction if JSON parse fails
    (e.g. legacy package.json with trailing commas, JSON5 syntax, BOM).
    """
    deps: list[tuple[str, str]] = []
    seen: set[str] = set()

    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        # Malformed JSON — try regex fallback per section.
        for label in _NPM_DEP_SECTIONS:
            m = re.search(rf'"{label}"\s*:\s*\{{([^}}]*)\}}', content, re.DOTALL)
            if m:
                for name, version in _RE_NPM_DEP.findall(m.group(1)):
                    if name not in seen:
                        seen.add(name)
                        deps.append((name, version))
        return deps

    if not isinstance(data, dict):
        return deps

    for label in _NPM_DEP_SECTIONS:
        section = data.get(label)
        if not isinstance(section, dict):
            continue
        for name, version in section.items():
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            if name in seen:
                continue
            seen.add(name)
            # Strip ^/~ semver markers for downstream EOL match
            cleaned = version.lstrip("^~")
            deps.append((name, cleaned))
    return deps


def _parse_maven_pom(content: str) -> list[tuple[str, str]]:
    return [(f"{g}:{a}", v or "unknown") for g, a, v in _RE_MAVEN_DEP.findall(content)]


def _parse_pip_requirements(content: str) -> list[tuple[str, str]]:
    return [(name, version or "unspecified") for name, version in _RE_PIP_REQ.findall(content)
            if not name.startswith("#")]


def _parse_composer_json(content: str) -> list[tuple[str, str]]:
    """Extract `require` + `require-dev` from composer.json.

    P3.12 closure — symmetric fix with `_parse_npm_json` : prefer
    `json.loads` for nested-safe parsing, fall back to regex for
    malformed legacy manifests.
    """
    deps: list[tuple[str, str]] = []
    seen: set[str] = set()

    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        for label in ("require", "require-dev"):
            m = re.search(rf'"{label}"\s*:\s*\{{([^}}]*)\}}', content, re.DOTALL)
            if m:
                for name, version in _RE_COMPOSER_DEP.findall(m.group(1)):
                    if name not in seen:
                        seen.add(name)
                        deps.append((name, version))
        return deps

    if not isinstance(data, dict):
        return deps

    for label in ("require", "require-dev"):
        section = data.get(label)
        if not isinstance(section, dict):
            continue
        for name, version in section.items():
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            # Skip PHP runtime pseudo-package
            if name.lower() == "php":
                continue
            if name in seen:
                continue
            seen.add(name)
            deps.append((name, version.lstrip("^~")))
    return deps


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """Parse a dotted numeric version prefix ; None when unparseable."""
    m = re.match(r"(\d+(?:\.\d+)*)", (version or "").strip())
    if not m:
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def _detect_eol(name: str, version: str) -> tuple[bool, str | None, str | None]:
    """Return (is_eol, eol_date, reason).

    Audit 2026-06-10 M17 : `versions_before` was IGNORED — every version of a
    hinted package was reported EOL (Newtonsoft.Json 13.0.3 flagged despite the
    hint saying `< 13.0.0`). The bound is now compared ; an unparseable version
    stays flagged (conservative) only when the hint has no version bound.
    """
    hint = EOL_HINTS.get(name)
    if not hint:
        # Try partial match for composer-style "vendor/lib"
        for key, h in EOL_HINTS.items():
            if name.lower() == key.lower() or name.lower().startswith(key.lower() + ":"):
                hint = h
                break
    if not hint:
        return False, None, None
    bound = hint.get("versions_before")
    if bound:
        v = _version_tuple(version)
        b = _version_tuple(bound)
        if v is not None and b is not None and v >= b:
            return False, None, None   # at/above the fixed version — not EOL
    return True, hint.get("eol_date"), hint.get("reason")


def _extract_external_deps(project_root: Path) -> list[dict[str, Any]]:
    """Find and parse common manifests."""
    deps: list[dict[str, Any]] = []
    parsers = [
        ("packages.config", _parse_packages_config),
        ("package.json", _parse_npm_json),
        ("pom.xml", _parse_maven_pom),
        ("requirements.txt", _parse_pip_requirements),
        ("composer.json", _parse_composer_json),
    ]
    for filename, parser in parsers:
        for manifest in project_root.rglob(filename):
            # Skip nested node_modules / vendor
            if any(part in {"node_modules", "vendor", "__pycache__"} for part in manifest.parts):
                continue
            content = _read_text(manifest)
            if not content:
                continue
            rel = str(manifest.relative_to(project_root).as_posix())
            for name, version in parser(content):
                is_eol, eol_date, reason = _detect_eol(name, version)
                entry: dict[str, Any] = {
                    "name": name,
                    "version": version,
                    "eol": is_eol,
                    "evidence": rel,
                }
                if eol_date:
                    entry["eolDate"] = eol_date
                if reason:
                    entry["reason"] = reason
                deps.append(entry)
    return deps


def _edges_from_code_graph(code_graph: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project the Phase 1 class-level code graph down to file-level edges.

    ``code-graph.json`` resolves references by **type usage** (a class name
    appearing in another class body), which does not depend on ``namespace`` /
    ``using`` declarations at all. That makes it the strong resolver, and the
    one to consume first — the result already exists on disk one phase earlier.

    Class-to-class edges collapse to file-to-file: several classes may live in
    the same file (partial classes, nested helpers), so edges internal to a
    single file are dropped and duplicates are merged, keeping the first
    ``evidence`` seen.
    """
    if not isinstance(code_graph, dict):
        return []
    classes = code_graph.get("classes")
    raw_edges = code_graph.get("edges")
    if not isinstance(classes, list) or not isinstance(raw_edges, list):
        return []

    # Simple class name -> declaring file (first declaration wins, mirroring
    # build_code_graph's own `by_name` registry so both agree on collisions).
    class_to_file: dict[str, str] = {}
    for ci in classes:
        if not isinstance(ci, dict):
            continue
        name = ci.get("name")
        rel = ci.get("file")
        if isinstance(name, str) and isinstance(rel, str) and name and rel:
            class_to_file.setdefault(name, rel)

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for e in raw_edges:
        if not isinstance(e, dict):
            continue
        src_name, dst_name = e.get("from"), e.get("to")
        if not isinstance(src_name, str) or not isinstance(dst_name, str):
            continue
        src_file = class_to_file.get(src_name)
        dst_file = class_to_file.get(dst_name)
        if not src_file or not dst_file or src_file == dst_file:
            continue
        key = (src_file, dst_file)
        if key in seen:
            continue
        seen.add(key)
        edge: dict[str, Any] = {"from": src_file, "to": dst_file, "kind": "reference"}
        evidence = e.get("evidence")
        if isinstance(evidence, str) and evidence:
            edge["evidence"] = evidence
        edges.append(edge)
    return edges


def _extract_internal_edges(scan_result: ScanResult, project_root: Path) -> list[dict[str, Any]]:
    """Namespace/import heuristic — SUPPLEMENT to `_edges_from_code_graph`.

    Kept for the families ``code-graph.json`` does not parse (it is .cs/.vb
    only): Java ``import``, PHP ``use``, JS/TS relative ``import``/``require``.
    On .NET it only adds edges the type-usage resolver could not see, and is
    never relied upon as the sole source (audit F-03).
    """
    edges: list[dict[str, Any]] = []
    # Build map: namespace/import-name → file path (simple heuristic for C#/Java)
    namespace_to_file: dict[str, str] = {}
    for lm in scan_result.languages:
        for f in lm.files:
            content = _read_text(f)
            rel = str(f.relative_to(project_root).as_posix())
            ns_match = re.search(r"^\s*namespace\s+([A-Za-z_][\w.]+)", content, re.MULTILINE)
            if ns_match:
                namespace_to_file.setdefault(ns_match.group(1), rel)
            pkg_match = re.search(r"^\s*package\s+([A-Za-z_][\w.]+)", content, re.MULTILINE)
            if pkg_match:
                namespace_to_file.setdefault(pkg_match.group(1), rel)

    for lm in scan_result.languages:
        for f in lm.files:
            content = _read_text(f)
            rel = str(f.relative_to(project_root).as_posix())
            if lm.family == "dotnet":
                for ns in _RE_CSHARP_USING.findall(content):
                    target = namespace_to_file.get(ns)
                    if target and target != rel:
                        edges.append({"from": rel, "to": target, "kind": "using"})
            elif lm.family == "java":
                for ns in _RE_JAVA_IMPORT.findall(content):
                    target = namespace_to_file.get(ns)
                    if target and target != rel:
                        edges.append({"from": rel, "to": target, "kind": "import"})
            elif lm.family == "php":
                for ns in _RE_PHP_USE.findall(content):
                    target = namespace_to_file.get(ns.replace("\\", "."))
                    if target and target != rel:
                        edges.append({"from": rel, "to": target, "kind": "use"})
            elif lm.family == "web":
                for m in _RE_JS_IMPORT.findall(content):
                    target_str = m[0] or m[1]
                    if target_str.startswith("."):
                        # Relative import — resolve heuristically
                        try:
                            resolved = (f.parent / target_str).resolve()
                            if resolved.is_file():
                                edges.append({
                                    "from": rel,
                                    "to": str(resolved.relative_to(project_root).as_posix()),
                                    "kind": "import",
                                })
                        except (OSError, ValueError):
                            continue
    return edges


def _detect_cycles(edges: list[dict[str, Any]]) -> list[list[str]]:
    """Tarjan SCC for non-trivial cycles (size ≥ 2)."""
    adj: dict[str, set[str]] = {}
    nodes: set[str] = set()
    for e in edges:
        nodes.add(e["from"])
        nodes.add(e["to"])
        adj.setdefault(e["from"], set()).add(e["to"])

    index_counter = [0]
    stack: list[str] = []
    lowlinks: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: set[str] = set()
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for succ in adj.get(node, ()):
            if succ not in index:
                strongconnect(succ)
                lowlinks[node] = min(lowlinks[node], lowlinks[succ])
            elif succ in on_stack:
                lowlinks[node] = min(lowlinks[node], index[succ])
        if lowlinks[node] == index[node]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == node:
                    break
            if len(scc) >= 2:
                sccs.append(sorted(scc))

    for n in nodes:
        if n not in index:
            try:
                strongconnect(n)
            except RecursionError:
                # Very large graph — bail out, report empty
                return []
    return sccs


# Markup extensions whose *code-behind* sibling is an entry point, not dead
# code: `Login.aspx.cs` is reached from `Login.aspx`, never from another class.
_CODEBEHIND_MARKUP_SUFFIXES = (
    ".aspx", ".ascx", ".master", ".asmx", ".ashx", ".svc",
    ".cshtml", ".vbhtml", ".xaml", ".asp", ".html",
)

_ENTRY_POINT_SUFFIXES = (
    ".aspx", ".ascx", ".master", ".asmx", ".ashx", ".svc",
    ".cshtml", ".vbhtml", ".jsp", ".jspx", ".php", ".xaml", ".asp",
    "global.asax", "program.cs", "startup.cs", "main.java",
)


def _is_entry_point(rel: str) -> bool:
    """True when a file is reached from outside the code graph.

    Two cases, both of which the pre-F-03 list missed for code-behind:
      * markup / bootstrap files (``Login.aspx``, ``Program.cs``, ``Global.asax``)
      * their code-behind sibling (``Login.aspx.cs``, ``MainWindow.xaml.vb``) —
        the runtime instantiates these from the markup's ``Inherits`` /
        ``CodeFile`` attribute, so no class ever references them and they were
        being reported as dead code on *every* WebForms/WPF legacy.
    """
    low = rel.lower()
    if low.endswith(_ENTRY_POINT_SUFFIXES):
        return True
    # Code-behind: strip the language extension and re-test the markup suffix.
    stem, _, ext = low.rpartition(".")
    if ext in {"cs", "vb", "fs"} and stem.endswith(_CODEBEHIND_MARKUP_SUFFIXES):
        return True
    return False


def _dead_code_hint(scan_result: ScanResult, edges: list[dict[str, Any]], project_root: Path) -> list[str]:
    """Files in scan but no incoming internal edge (best-effort)."""
    incoming: dict[str, int] = {}
    for e in edges:
        incoming[e["to"]] = incoming.get(e["to"], 0) + 1
    hints: list[str] = []
    for lm in scan_result.languages:
        for f in lm.files:
            rel = str(f.relative_to(project_root).as_posix())
            # Entry points, page-level files unlikely to be "dead"
            if _is_entry_point(rel):
                continue
            if incoming.get(rel, 0) == 0 and lm.family in {"dotnet", "java", "php", "web"}:
                hints.append(rel)
    return sorted(hints)[:50]  # bounded list


def _merge_edges(*edge_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Union of edge lists, deduplicated on (from, to); first kind wins."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for edges in edge_lists:
        for e in edges:
            key = (e.get("from", ""), e.get("to", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(e)
    return merged


def build_deps_graph(
    project_root: str | Path,
    scan_result: ScanResult,
    code_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble deps-graph.json per design doc §5.4.

    ``code_graph`` is the Phase 1 ``code-graph.json`` payload. When supplied,
    its type-usage-resolved edges are projected to file level and take
    precedence; the local namespace/import heuristic only supplements them
    (audit F-03). Passing ``None`` keeps the legacy heuristic-only behaviour.
    """
    root = Path(project_root).resolve()
    internal = _merge_edges(
        _edges_from_code_graph(code_graph),
        _extract_internal_edges(scan_result, root),
    )
    external = _extract_external_deps(root)
    cycles = _detect_cycles(internal)
    dead = _dead_code_hint(scan_result, internal, root)
    return {
        "schemaVersion": 1,
        "project": root.name,
        "buildDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "internalEdges": internal[:500],  # bounded
        "internalEdgesTotal": len(internal),
        "externalDeps": external,
        "cyclesDetected": cycles,
        "deadCodeHint": dead,
    }
