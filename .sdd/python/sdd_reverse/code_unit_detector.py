"""code_unit_detector.py — Code-driven functional units (L2).

Before L2, a functional unit could only originate from a UI page file, so a
backend-only / API-only legacy (controllers + services + repositories, no
.aspx/.cshtml) produced ZERO units and was invisible to the whole pipeline.

L2 adds two complementary unit sources, derived from the L0 code graph, that
run AFTER the UI-page units and cover what those miss:

    1. Controllers  → one unit per MVC/Web API controller (REST/API surface).
    2. Orphan modules → behavioural classes (service/repository/complex/classic
       with methods) not reachable from any page or controller unit, grouped by
       module (namespace, else top folder). Catches pure backend business
       logic, batch jobs, scheduled tasks, domain services.

Supporting-only types (DTO / entity / interface / enum / pure static helper) do
NOT form a unit on their own — they are carried in via `classes[]` enrichment.

Public API:
    detect_code_units(code_graph, existing_units, *, max_depth=3) -> list[dict]

Returns candidates in the same shape as `ui_unit_detector.detect_units`
(``{label, suggestedName, language, kind, evidenceFiles, entities,
confidenceEstimate, rationale}``) so `enrich_units` + `build_inventory` treat
them uniformly.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sdd_reverse.scan_legacy import decode_text, normalize_bytes

# Roles that make a class "behavioural" enough to anchor a backend module unit.
# `viewmodel` added 2026-06-10 (audit C1/M7) : MVVM VMs carry the business
# logic — an unbound VM must anchor an extractible module, not vanish as DTO.
_BEHAVIOURAL_ROLES = frozenset({"service", "repository", "controller", "complex", "viewmodel"})

# --- CLI / batch entry-point detection (audit 2026-06-10 C2) ------------------
# Legacy .NET apps frequently run dual-mode : WPF/WinForms UI when launched
# bare, headless batch when launched with CLI args (Task Scheduler). Before
# this fix the 47 EDI CLI commands lived in App.xaml.cs and produced ZERO unit.

_ENTRY_POINT_FILENAMES = frozenset({
    "app.xaml.cs", "app.xaml.vb", "program.cs", "program.vb", "main.cs",
})

# Evidence that the entry point actually CONSUMES CLI arguments (every WPF
# App.xaml.cs has `OnStartup(StartupEventArgs e)` — the discriminant is
# reading `e.Args` / `args[...]`, not the signature).
_CLI_ARGS_RE = re.compile(
    r"Environment\.GetCommandLineArgs|\be\.Args\b|\bargs\s*\[|\bargs\.Length\b",
    re.IGNORECASE,
)

# Command tokens dispatched on : case "X": / args[i] == "X" / = "X" Then (VB).
_CLI_COMMAND_TOKEN_RE = re.compile(
    r"""(?:case\s+|==\s*|=\s*|\.Equals\s*\(\s*)"([A-Za-z][\w\-/]{1,40})"
    """,
    re.VERBOSE,
)


def _pascal(token: str) -> str:
    parts = re.split(r"[-_.\s]+", token)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _module_key(cls: dict[str, Any]) -> str:
    """Group key for orphan modules: namespace if present, else top folder."""
    ns = (cls.get("namespace") or "").strip()
    if ns:
        # Drop a trailing technical segment so e.g. `Acme.Billing.Services`
        # and `Acme.Billing.Repositories` group under `Acme.Billing`.
        segs = ns.split(".")
        if len(segs) >= 2 and segs[-1].lower() in (
            "services", "repositories", "repository", "data", "dal", "bll",
            "business", "logic", "core", "domain", "infrastructure",
        ):
            segs = segs[:-1]
        return ".".join(segs)
    file = cls.get("file", "")
    top = file.split("/", 1)[0] if "/" in file else ""
    return top or file


def _module_name(module_key: str) -> str:
    last = module_key.split(".")[-1].split("/")[-1] if module_key else "Module"
    return _pascal(last) or "Module"


def _closure(seed_classes: set[str], adj: dict[str, set[str]], max_depth: int) -> set[str]:
    reached = set(seed_classes)
    frontier = set(seed_classes)
    depth = 0
    while frontier and depth < max_depth:
        nxt: set[str] = set()
        for cn in frontier:
            for ref in adj.get(cn, ()):  # noqa: SIM118
                if ref not in reached:
                    nxt.add(ref)
        reached |= nxt
        frontier = nxt
        depth += 1
    return reached


def _detect_job_units(
    classes: list[dict[str, Any]],
    adj: dict[str, set[str]],
    project_root: Path | None,
    lang: str,
    max_depth: int,
) -> tuple[list[dict[str, Any]], set[str]]:
    """One unit kind=job per CLI/batch entry-point file showing args dispatch.

    Returns (units, class_names_consumed). Requires `project_root` to read the
    entry-point source for CLI evidence — skipped gracefully when absent.
    """
    if project_root is None:
        return [], set()
    units: list[dict[str, Any]] = []
    consumed: set[str] = set()
    seen_files: set[str] = set()
    for c in sorted(classes, key=lambda x: x["name"]):
        file_rel = c["file"]
        if file_rel in seen_files:
            continue
        base = file_rel.rsplit("/", 1)[-1].lower()
        if base not in _ENTRY_POINT_FILENAMES:
            continue
        seen_files.add(file_rel)
        try:
            text = decode_text(normalize_bytes((project_root / file_rel).read_bytes()))
        except OSError:
            continue
        if not _CLI_ARGS_RE.search(text):
            continue  # pure UI bootstrap — no headless mode visible
        tokens = sorted({t for t in _CLI_COMMAND_TOKEN_RE.findall(text)})
        anchor_classes = {cc["name"] for cc in classes if cc["file"] == file_rel}
        closure = _closure(anchor_classes, adj, max_depth)
        consumed |= closure
        suggested = _pascal(Path(file_rel).stem.split(".")[0]) + "Batch"
        token_preview = ", ".join(f"`{t}`" for t in tokens[:15])
        if len(tokens) > 15:
            token_preview += f" … (+{len(tokens) - 15})"
        units.append({
            "label": f"Traitements batch/CLI ({Path(file_rel).name})",
            "suggestedName": suggested,
            "language": lang,
            "kind": "job",
            "evidenceFiles": [file_rel],
            "entities": [],
            "confidenceEstimate": "medium",
            "cliCommands": tokens,
            "rationale": (
                f"Entry-point `{file_rel}` consomme des arguments CLI "
                f"(mode headless/batch dual-mode) — {len(tokens)} commande(s) "
                f"détectée(s){' : ' + token_preview if tokens else ''}."
            ),
        })
    return units, consumed


def detect_code_units(
    code_graph: dict[str, Any],
    existing_units: list[dict[str, Any]],
    *,
    max_depth: int = 3,
    language: str | None = None,
    project_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Detect job + controller + orphan-module units from the code graph."""
    classes = code_graph.get("classes", [])
    if not classes:
        return []

    # (audit 2026-08-29, m6) A `by_name` index used to be built here and never
    # read once: every downstream step works on the class dicts directly
    # (`controllers`, `orphan_behavioural`, `anchor`) or on the `adj` graph
    # below. Removed rather than wired in — and it was worse than merely dead:
    # its `{c["name"]: c}` comprehension was LAST-WINS across partial-class
    # duplicates, the exact defect M18 fixed for `adj` right underneath. Keeping
    # it would have been an ambush for whoever eventually used it.
    # The legitimate name→class registry lives in `code_graph_builder` (first-wins).
    # UNION across partial-class duplicates (audit M18 — was overwritten).
    adj: dict[str, set[str]] = {}
    for c in classes:
        adj.setdefault(c["name"], set()).update(c.get("references", []))
    file_to_classes: dict[str, list[str]] = {}
    for c in classes:
        file_to_classes.setdefault(c["file"], []).append(c["name"])

    lang = language or code_graph.get("language") or "unknown"

    # Classes already covered by UI-page units (their transitive closure).
    page_seed: set[str] = set()
    for u in existing_units:
        for f in (u.get("seedEvidenceFiles") or u.get("evidenceFiles", [])):
            page_seed |= set(file_to_classes.get(f, []))
    covered = _closure(page_seed, adj, max_depth)

    units: list[dict[str, Any]] = []
    used: set[str] = set(covered)

    # 0. CLI/batch entry-point units (C2) — detected FIRST so the headless
    #    dispatch layer anchors its own unit even when some handlers are also
    #    reachable from UI units (dual-mode is the archetypal legacy case).
    job_units, job_consumed = _detect_job_units(
        classes, adj, Path(project_root) if project_root else None, lang, max_depth,
    )
    units.extend(job_units)
    used |= job_consumed

    # 1. Controllers → one unit each (API surface), unless already covered.
    controllers = sorted(
        (c for c in classes if c["role"] == "controller" and c["name"] not in covered),
        key=lambda c: c["name"],
    )
    for c in controllers:
        if c["name"] in used:
            continue
        name = c["name"]
        suggested = _pascal(re.sub(r"Controller$", "", name) or name)
        closure = _closure({name}, adj, max_depth)
        used |= closure
        units.append({
            "label": f"API {suggested}",
            "suggestedName": suggested,
            "language": lang,
            "kind": "api",
            "evidenceFiles": [c["file"]],
            "entities": [],
            "confidenceEstimate": "medium",
            "rationale": f"Controller {name} ({c['file']}) — surface API/MVC, "
                         f"{len(closure)} classe(s) atteinte(s).",
        })

    # 2. Orphan modules → group remaining behavioural classes by module key.
    orphan_behavioural = [
        c for c in classes
        if c["name"] not in used
        and (
            c["role"] in _BEHAVIOURAL_ROLES
            or (c["role"] == "classic" and c.get("methodCount", 0) >= 1)
        )
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in orphan_behavioural:
        groups.setdefault(_module_key(c), []).append(c)

    for mod_key, members in sorted(groups.items()):
        anchor = sorted(members, key=lambda c: (-c.get("methodCount", 0), c["name"]))[0]
        suggested = _module_name(mod_key)
        seed_files = sorted({m["file"] for m in members})
        member_names = {m["name"] for m in members}
        used |= member_names
        roles = sorted({m["role"] for m in members})
        units.append({
            "label": f"Module {suggested}",
            "suggestedName": suggested,
            "language": lang,
            "kind": "module",
            "evidenceFiles": seed_files,
            "entities": [],
            "confidenceEstimate": "medium",
            "rationale": f"Module backend `{mod_key}` — {len(members)} classe(s) "
                         f"métier ({', '.join(roles)}), aucune page UI rattachée. "
                         f"Ancre : {anchor['name']}.",
        })

    return units
