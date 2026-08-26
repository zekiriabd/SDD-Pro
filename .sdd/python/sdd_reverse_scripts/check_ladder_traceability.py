"""check_ladder_traceability.py — D3 enforcer for the reverse spec-ladder.

ADR governance-major-reverse-spec-ladder. Deterministic (0 token, stdlib only,
D4-isolated — no sdd_lib import). Verifies the traceability chain produced by
the 3-rung ladder for ONE unit :

    FEAT item (feats/{n}-{Name}.md)
        --covers--> US AC (us/{n}-{m}-{Name}.md)
            --covers--> task T-N (plans/{n}-{Name}.analysis.md)
                --evidence--> path:Lx-Ly

The DATABASE reverse (`/sdd-db-reverse-full`) climbs the same ladder with one
rung fewer — there is no 3a analysis, because the SQL object's own body IS the
analysis. Its chain is checked in the same pass (audit 2026-08-25, finding M3) :

    FEAT item (feats/{n}-{Module}.md)
        --covers--> US AC (us/{n}-{m}-{Name}.md, one US per SQL object)
            --evidence--> .sys/proc-snapshot/{schema}.{object}.sql:Lx-Ly

Running the code-shaped check against a `db-module` unit used to report
"artifacts missing" and stop, which read as "not run yet" rather than "wrong
shape" — the downward half of the DB ladder was simply never verified.

On the DB path the evidence path is additionally resolved ON DISK. The
assembler writes `unknown:1` when it has no evidence, and that value used to
pass every gate; a snapshot that does not exist is now a gap, not a green.

Emits [REVERSE_LADDER_TRACEABILITY_GAP] findings. **Informational, never
blocking** (mirrors check_feat_completeness.py) : gaps are reported, never
filled by invention (bias toward not-verified). Exit 0 unless an infra error
(unreadable inventory / missing allocation) occurs (exit 3).

Invocation :
    python .sdd/python/sdd_reverse_scripts/check_ladder_traceability.py \
        --project workspace/old/{P} --unit U-3 [--json]
    python .sdd/python/sdd_reverse_scripts/check_ladder_traceability.py \
        --feat-path workspace/feats/3-Login.md [--json]

Exit codes :
    0  ran OK (verdict in {ladder-complete, partial, incomplete} — informational)
    2  ladder artifacts missing for the unit (3a/3b not run yet) — informational
    3  infra error (bad args, unreadable inventory, allocation missing)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.paths import workspace_root

REPO_ROOT = Path(__file__).resolve().parents[3]

_ITEM_ID_RE = re.compile(r"\*?\*?(SFD|FD|BR|AC)-\d+\*?\*?", re.IGNORECASE)
_COVERS_RE = re.compile(r"<!--\s*covers:\s*([^>]+?)\s*-->", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"<!--\s*evidence:\s*([^>]+?)\s*-->", re.IGNORECASE)
_TASK_ID_RE = re.compile(r"\bT-\d+\b")
_US_AC_REF_RE = re.compile(r"(\d+-\d+)\s*#\s*(AC-\d+)", re.IGNORECASE)

# Confidence min-monotone (Q3, ADR reverse-spec-ladder).
# Source primaire : ligne header `confidence:`/`Confidence:` en début de ligne
# (frontmatter 3a/3c ; ligne header US 3b depuis l'audit 2026-06-11 M2).
# Fallback : commentaire de provenance `<!-- generated-by: ... confidence: X -->`
# pour les US 3b générées AVANT le fix M2 (template sans ligne Confidence —
# l'enforcement Q3 « US ≤ analyse » / « FEAT ≤ min(US) » était silencieusement
# skippé pour 100 % d'entre elles).
_CONF_RE = re.compile(r"^confidence:\s*(high|medium|low)\b", re.MULTILINE | re.IGNORECASE)
_CONF_COMMENT_RE = re.compile(
    r"<!--[^>]*\bconfidence:\s*(high|medium|low)\b[^>]*-->", re.IGNORECASE
)
_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}

# Confidence cap per language (D1, rule §4). SSoT = language_signatures.yml
# `confidence_cap` — NEVER hardcoded. Parsed line-based (no PyYAML dep on this
# deterministic script): a `- id: <lang>` line opens an entry, a later
# `confidence_cap: <cap>` line (same entry) closes the association.
_LANG_SIG_PATH = (
    Path(__file__).resolve().parents[1] / "sdd_reverse" / "language_signatures.yml"
)
_LANG_ID_RE = re.compile(r"^\s*-\s+id:\s*([A-Za-z0-9_-]+)\s*$")
_LANG_CAP_RE = re.compile(r"^\s*confidence_cap:\s*(high|medium|low)\b", re.IGNORECASE)
_LANG_CAP_CACHE: dict[str, str] | None = None


def _load_language_caps() -> dict[str, str]:
    """Map language id → confidence_cap from language_signatures.yml (best-effort)."""
    global _LANG_CAP_CACHE
    if _LANG_CAP_CACHE is not None:
        return _LANG_CAP_CACHE
    caps: dict[str, str] = {}
    raw = _read(_LANG_SIG_PATH)
    if raw:
        cur: str | None = None
        for line in raw.splitlines():
            m = _LANG_ID_RE.match(line)
            if m:
                cur = m.group(1)
                continue
            if cur is not None:
                cm = _LANG_CAP_RE.match(line)
                if cm:
                    caps[cur] = cm.group(1).lower()
                    cur = None
    _LANG_CAP_CACHE = caps
    return caps


def _load_unit(project: Path | None, unit: str | None) -> dict | None:
    """Load the units[id == unit] dict from inventory.json (best-effort, None on any failure)."""
    if project is None or unit is None:
        return None
    raw = _read(project / ".sys" / "inventory.json")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return next((x for x in (data.get("units") or []) if x.get("id") == unit), None)


def _db_degraded(project: Path | None, entities) -> bool:
    """True if the unit declares entities that are NOT DDL-backed in db-schema.

    Deterministic form of the analyst's `cap_db` (rule §4 / agent 3a STEP 2:
    "cap_db = medium si db-schema vide pour entities de l'unité"). Previously this
    cap lived ONLY in the 3a prompt ("cap_db runtime-only reste prompt-side"), so a
    3a writing `high` on code-deduced entities passed every gate. Now enforced here.
    A unit with NO declared entities is never db-degraded (nothing to back).
    """
    if not entities or project is None:
        return False
    for fn in ("db-schema.merged.json", "db-schema.json"):
        raw = _read(project / ".sys" / fn)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        names = {e.get("name") for e in (data.get("entities") or [])}
        # Degraded if ANY unit entity is absent from the DDL-sourced schema.
        return any(e not in names for e in entities)
    # No db-schema file at all but the unit declares entities → deduced from code.
    return True


def _unit_cap(project: Path | None, unit: str | None) -> tuple[str | None, str | None]:
    """Return (language, effective_cap) for a unit, or (None, None) if unresolved.

    effective_cap = min(confidence_cap[language], unit.confidenceEstimate,
    cap_db) — the deterministic floor of the rule §4 formula. `cap_db` (medium
    when the unit's entities are not DDL-backed) is now enforced here too
    (audit 2026-06-29: was prompt-only). Best-effort: any failure (no inventory,
    no project/unit, unknown language) yields (None, None) so the caller skips
    the check — informational, never breaks.
    """
    u = _load_unit(project, unit)
    if not u:
        return (None, None)
    language = u.get("language")
    cap = _load_language_caps().get(language) if language else None
    if cap is None:
        return (language, None)
    estimate = u.get("confidenceEstimate")
    if estimate in _CONF_ORDER and _CONF_ORDER[estimate] < _CONF_ORDER[cap]:
        cap = estimate  # tighten to the lower of lang-cap and per-unit estimate
    if _db_degraded(project, u.get("entities") or []) and _CONF_ORDER["medium"] < _CONF_ORDER[cap]:
        cap = "medium"  # cap_db: entities deduced from code, not DDL-sourced
    return (language, cap)


def _graph_built(project: Path | None, unit: str | None) -> bool | None:
    """Whether a class graph (L0) was built for the unit.

    True  → units[].classes non-empty (deep extraction available, .NET path).
    False → units[].classes present but empty (graph ran, nothing — non-.NET
            languages where code_graph_builder is unavailable).
    None  → unknown (no inventory / no `classes` key / pre-L0 cache) → no signal.
    """
    u = _load_unit(project, unit)
    if not u:
        return None
    classes = u.get("classes")
    if classes is None:
        return None
    return bool(classes)


def _frontmatter_confidence(text: str | None) -> str | None:
    """Confidence du header (frontmatter/ligne), fallback commentaire provenance."""
    if not text:
        return None
    m = _CONF_RE.search(text[:2000])
    if m:
        return m.group(1).lower()
    m = _CONF_COMMENT_RE.search(text[:2000])
    return m.group(1).lower() if m else None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _resolve_feat(project: Path | None, unit: str | None, feat_path: Path | None) -> tuple[Path | None, str | None, str | None]:
    """Return (feat_path, n, Name) or (None, None, None) with an error string via exception."""
    if feat_path is not None:
        m = re.match(r"(\d+)-(.+)\.md$", feat_path.name)
        if not m:
            raise ValueError(f"feat-path filename not {{n}}-{{Name}}.md: {feat_path.name}")
        return feat_path, m.group(1), m.group(2)
    # resolve via inventory allocation
    inv = project / ".sys" / "inventory.json"
    raw = _read(inv)
    if raw is None:
        raise FileNotFoundError(f"inventory.json unreadable: {inv}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"inventory.json invalid JSON: {e}")
    alloc = (data.get("_featAllocations") or {})
    names = (data.get("_allocatedNames") or {})
    n = alloc.get(unit)
    if n is None:
        raise KeyError(f"_featAllocations[{unit}] absent (3a not run for this unit)")
    # find Name from _allocatedNames (value == unit)
    name = next((k for k, v in names.items() if v == unit), None)
    if name is None:
        raise KeyError(f"_allocatedNames has no entry for {unit}")
    feat = workspace_root(REPO_ROOT) / "feats" / f"{n}-{name}.md"
    return feat, str(n), name


def _iter_item_blocks(text: str, headings: tuple[str, ...], id_re: re.Pattern):
    """Yield (item_id, block_text) for each item under the given section headings.

    An item *block* starts at the line bearing its ID and extends until the next
    item ID or a section boundary. This makes parsing robust to MULTI-LINE items
    where the `<!-- covers/evidence -->` comments sit on a trailing line (the
    realistic agent output format — single-line was a test-only simplification).
    `headings` are matched by prefix on the stripped `## ` line.
    """
    in_section = False
    cur_id: str | None = None
    cur_lines: list[str] = []

    def _matches(line: str) -> bool:
        s = line.strip()
        return any(s == h or s.startswith(h) for h in headings)

    for line in text.splitlines():
        if line.startswith("## "):
            if cur_id is not None:
                yield cur_id, "\n".join(cur_lines)
                cur_id, cur_lines = None, []
            in_section = _matches(line)
            continue
        if not in_section:
            continue
        m = id_re.search(line)
        if m:
            if cur_id is not None:
                yield cur_id, "\n".join(cur_lines)
            cur_id = m.group(0).strip("*")
            cur_lines = [line]
        elif cur_id is not None:
            cur_lines.append(line)
    if cur_id is not None:
        yield cur_id, "\n".join(cur_lines)


_FEAT_SECTIONS = (
    "## Functional Needs", "## Functional Deliverables",
    "## Business Rules", "## Acceptance Criteria",
)


def _parse_feat_items(text: str) -> list[dict]:
    """Each FEAT item (block-aware) under the 4 spec sections, with covers/evidence."""
    items: list[dict] = []
    for item_id, block in _iter_item_blocks(text, _FEAT_SECTIONS, _ITEM_ID_RE):
        covers: list[str] = []
        cm = _COVERS_RE.search(block)
        if cm:
            covers = [f"{a}#{b}" for a, b in _US_AC_REF_RE.findall(cm.group(1))]
        items.append({
            "id": item_id,
            "covers_us": covers,
            "has_evidence": bool(_EVIDENCE_RE.search(block)),
        })
    return items


def _parse_us_acs(text: str) -> list[dict]:
    """US ACs (block-aware) with their covers: T-N refs. Returns [{us_ac, covers_tasks}]."""
    idm = re.search(r"^ID:\s*(\d+-\d+)-", text, re.MULTILINE)
    us_short = idm.group(1) if idm else "?-?"
    acs: list[dict] = []
    ac_id_re = re.compile(r"\bAC-\d+\b")
    for ac_id, block in _iter_item_blocks(text, ("## Acceptance Criteria",), ac_id_re):
        cm = _COVERS_RE.search(block)
        tasks = _TASK_ID_RE.findall(cm.group(1)) if cm else []
        acs.append({"us_ac": f"{us_short}#{ac_id}", "covers_tasks": tasks})
    return acs


def _parse_analysis_tasks(text: str) -> dict[str, bool]:
    """task id -> has_evidence (block-aware, within ## Comportements observés)."""
    tasks: dict[str, bool] = {}
    for task_id, block in _iter_item_blocks(text, ("## Comportements observés",), _TASK_ID_RE):
        tasks[task_id] = bool(_EVIDENCE_RE.search(block))
    return tasks


_SOURCE_PROC_RE = re.compile(r"^source-proc:\s*(\S+)", re.MULTILINE)
_EV_PATH_RE = re.compile(r"^(.*?):[Ll]?\d+(?:\s*-\s*[Ll]?\d+)?$")


def _is_db_ladder(unit_dict: dict | None, us_texts: list) -> bool:
    """True when this unit is a database module (2 rungs), not a code unit (3).

    Two independent signals, because the checker is invoked both ways: with
    `--project/--unit` (the inventory knows) and with `--feat-path` alone (it
    does not, so the US themselves have to say — every DB-reverse US carries the
    SQL object it was derived from).
    """
    if (unit_dict or {}).get("kind") == "db-module":
        return True
    return any(_SOURCE_PROC_RE.search(t) for _, t in us_texts)


def _parse_us_acs_db(text: str) -> list[dict]:
    """US ACs of a DB-reverse US: id + whether the AC carries an evidence ref."""
    idm = re.search(r"^ID:\s*(\d+-\d+)-", text, re.MULTILINE)
    us_short = idm.group(1) if idm else "?-?"
    acs: list[dict] = []
    ac_id_re = re.compile(r"\bAC-\d+\b")
    for ac_id, block in _iter_item_blocks(text, ("## Acceptance Criteria",), ac_id_re):
        em = _EVIDENCE_RE.search(block)
        acs.append({
            "us_ac": f"{us_short}#{ac_id}",
            "evidence": (em.group(1).strip() if em else ""),
        })
    return acs


def _evidence_resolves(project: Path | None, evidence: str) -> bool | None:
    """Does an `path:Lx-Ly` evidence ref point at a file that exists?

    None when it cannot be decided (no project root given). `unknown:1` — the
    assembler's placeholder — never resolves, which is the whole point.
    """
    if not evidence or project is None:
        return None
    ref = evidence.split(",")[0].strip()
    m = _EV_PATH_RE.match(ref)
    path = (m.group(1) if m else ref).strip()
    if not path or path == "unknown":
        return False
    return (project / path).exists()


def _check_db_ladder(
    *, project: Path | None, unit: str | None, n, name,
    feat_text: str, us_texts: list, us_files: list, feat: Path,
) -> dict:
    """FEAT items → US ACs → snapshot evidence, for a `db-module` unit."""
    feat_items = _parse_feat_items(feat_text)
    us_acs: list[dict] = []
    for _, t in us_texts:
        us_acs.extend(_parse_us_acs_db(t))
    us_ac_ids = {a["us_ac"] for a in us_acs}

    gaps: list[str] = []
    covered_us_acs: set[str] = set()

    for it in feat_items:
        if not it["covers_us"]:
            gaps.append(f"FEAT {it['id']}: no `covers:` to any US AC")
        for ref in it["covers_us"]:
            covered_us_acs.add(ref)
            if ref not in us_ac_ids:
                gaps.append(
                    f"FEAT {it['id']}: covers '{ref}' which has no matching US AC (dangling)")
        if not it["has_evidence"]:
            gaps.append(f"FEAT {it['id']}: no `evidence:` comment (rule §3)")

    # The SQL object's body replaces the 3a task rung: an AC that points at no
    # snapshot line is an AC nothing in the database backs.
    for a in us_acs:
        if not a["evidence"]:
            gaps.append(f"US {a['us_ac']}: no `evidence:` to a snapshot line")
        elif _evidence_resolves(project, a["evidence"]) is False:
            gaps.append(
                f"US {a['us_ac']}: evidence '{a['evidence']}' does not resolve "
                f"to a file under the project — placeholder or stale snapshot")
        if a["us_ac"] not in covered_us_acs:
            gaps.append(f"US {a['us_ac']}: orphan — covered by no FEAT item (downward gap)")

    conf_feat = _frontmatter_confidence(feat_text)
    us_confs = [(f.name, _frontmatter_confidence(t)) for f, t in us_texts]
    declared_us = [c for _, c in us_confs if c]
    if conf_feat and declared_us:
        floor = min(declared_us, key=lambda c: _CONF_ORDER[c])
        if _CONF_ORDER[conf_feat] > _CONF_ORDER[floor]:
            gaps.append(
                f"confidence uprank: FEAT ({conf_feat}) > min(US) ({floor}) "
                f"— min-monotone Q3 violated")
    unit_language, unit_cap = _unit_cap(project, unit)
    if unit_cap:
        for fname, c in us_confs:
            if c and _CONF_ORDER[c] > _CONF_ORDER[unit_cap]:
                gaps.append(
                    f"confidence cap: US {fname} ({c}) > cap[{unit_language}] "
                    f"({unit_cap}) — D1 rule §4 violated")

    stale_findings: list[str] = []
    try:
        feat_mtime = feat.stat().st_mtime
        us_mtimes = [f.stat().st_mtime for f in us_files]
        newest_us = max(us_mtimes) if us_mtimes else None
        if newest_us is not None and newest_us > feat_mtime + 1:
            stale_findings.append(
                "the US are newer than the FEAT — re-run build_proc_feats "
                "(upper rung stale)")
    except OSError:
        pass

    verdict = "ladder-complete" if not gaps else ("partial" if len(gaps) <= 3 else "incomplete")
    return {
        "unit": unit, "n": n, "name": name,
        "shape": "db-module",
        "artifacts": {"feat": True, "analysis": None, "us_count": len(us_files)},
        "ran": True,
        "counts": {"feat_items": len(feat_items), "us_acs": len(us_acs), "tasks": 0},
        "confidence": {
            "analysis": None,
            "us": {fname: c for fname, c in us_confs},
            "feat": conf_feat,
            "language": unit_language,
            "language_cap": unit_cap,
        },
        "extraction_depth": "sql-body",
        "verdict": verdict,
        "gap_count": len(gaps),
        "gaps": gaps,
        "class": "[REVERSE_LADDER_TRACEABILITY_GAP]" if gaps else None,
        "stale_findings": stale_findings,
        "stale_class": "[REVERSE_LADDER_STALE]" if stale_findings else None,
    }


def check(project: Path | None, unit: str | None, feat_path: Path | None) -> dict:
    feat, n, name = _resolve_feat(project, unit, feat_path)
    feats_dir = workspace_root(REPO_ROOT) / "feats"
    us_dir = workspace_root(REPO_ROOT) / "us"
    plans_dir = workspace_root(REPO_ROOT) / "plans"

    feat_text = _read(feat) if feat else None
    analysis_text = _read(plans_dir / f"{n}-{name}.analysis.md")
    # US filenames carry per-capability {Name} (decision Tech Lead 2026-06-13) and
    # no longer share the FEAT {Name} — match by the numeric {n}- prefix only
    # (us_short is re-derived from each US `ID:` line in _parse_us_acs).
    us_files = sorted(us_dir.glob(f"{n}-*.md")) if us_dir.is_dir() else []

    us_texts_all: list[tuple[Path, str]] = []
    for f in us_files:
        t = _read(f)
        if t:
            us_texts_all.append((f, t))

    # A database module climbs a 2-rung ladder (no 3a analysis — the SQL body is
    # the analysis). Dispatch BEFORE the artifact check, which would otherwise
    # report a missing `analysis.md` that is not supposed to exist (M3).
    if feat_text and us_texts_all and _is_db_ladder(_load_unit(project, unit), us_texts_all):
        return _check_db_ladder(
            project=project, unit=unit, n=n, name=name, feat_text=feat_text,
            us_texts=us_texts_all, us_files=us_files, feat=feat,
        )

    artifacts = {
        "feat": feat_text is not None,
        "analysis": analysis_text is not None,
        "us_count": len(us_files),
    }
    if not (feat_text and analysis_text and us_files):
        return {
            "unit": unit, "n": n, "name": name, "artifacts": artifacts,
            "verdict": "ladder-incomplete-artifacts",
            "ran": False,
            "message": "ladder artifacts missing (3a analysis / 3b US / 3c FEAT) — run the ladder first",
        }

    feat_items = _parse_feat_items(feat_text)
    us_texts = us_texts_all
    us_acs: list[dict] = []
    for _, t in us_texts:
        us_acs.extend(_parse_us_acs(t))
    tasks = _parse_analysis_tasks(analysis_text)

    us_ac_ids = {a["us_ac"] for a in us_acs}
    covered_tasks: set[str] = set()
    covered_us_acs: set[str] = set()

    gaps: list[str] = []

    # FEAT items → US
    for it in feat_items:
        if not it["covers_us"]:
            gaps.append(f"FEAT {it['id']}: no `covers:` to any US AC")
        for ref in it["covers_us"]:
            covered_us_acs.add(ref)
            if ref not in us_ac_ids:
                gaps.append(f"FEAT {it['id']}: covers '{ref}' which has no matching US AC (dangling)")
        if not it["has_evidence"]:
            gaps.append(f"FEAT {it['id']}: no `evidence:` comment (rule §3)")

    # US ACs → tasks
    for a in us_acs:
        if not a["covers_tasks"]:
            gaps.append(f"US {a['us_ac']}: no `covers:` to any task T-N")
        for tk in a["covers_tasks"]:
            covered_tasks.add(tk)
            if tk not in tasks:
                gaps.append(f"US {a['us_ac']}: covers '{tk}' absent from 3a analysis (dangling)")

    # tasks → evidence + orphan (downward completeness)
    for tk, has_ev in tasks.items():
        if not has_ev:
            gaps.append(f"task {tk}: no `evidence:` comment in 3a analysis")
        if tk not in covered_tasks:
            gaps.append(f"task {tk}: orphan — covered by no US AC (downward gap)")
    for a in us_acs:
        if a["us_ac"] not in covered_us_acs:
            gaps.append(f"US {a['us_ac']}: orphan — covered by no FEAT item (downward gap)")

    # Confidence min-monotone (Q3, ADR reverse-spec-ladder) :
    # confidence(FEAT 3c) ≤ min(confidence(US 3b)) ≤ confidence(analyse 3a).
    # Frontmatter-based ; comparaisons uniquement quand les deux barreaux la
    # déclarent (audit 2026-06-11 — la règle était documentée sans enforcer).
    conf_analysis = _frontmatter_confidence(analysis_text)
    conf_feat = _frontmatter_confidence(feat_text)
    us_confs = [(f.name, _frontmatter_confidence(t)) for f, t in us_texts]

    # Root cap enforcement (D1, rule §4) — audit fix 2026-06-12 (reverse-C2).
    # Monotonicity above only guarantees US ≤ analysis ≤ … *relatively*; nothing
    # checked that the analysis itself respects confidence_cap[language]. A 3a
    # writing `high` on a `medium`-cap language (php-procedural, vbnet, …) used
    # to pass every gate and unlock /sdd-full without review. Now flagged.
    unit_language, unit_cap = _unit_cap(project, unit)
    if conf_analysis and unit_cap and _CONF_ORDER[conf_analysis] > _CONF_ORDER[unit_cap]:
        gaps.append(
            f"confidence cap: analysis ({conf_analysis}) > cap[{unit_language}] "
            f"({unit_cap}) — D1 rule §4 violated (downgrade analysis or fix language)"
        )

    # Extraction-depth signal (audit 2026-06-29) — a `high` confidence asserts
    # reading-reliability, NOT extraction-depth. code_graph_builder is .NET-only;
    # a non-.NET unit whose class graph is empty can be `high` (e.g. java-ee,
    # spring-mvc, php-framework all carry cap=high in rule §4) yet structurally
    # under-extracted. The REVERSE-GATE keys on `confidence==high`, conflating the
    # two — surface it here so a shallow-but-readable FEAT is auditable before it
    # auto-unlocks /sdd-full. Informational; never silently filled.
    graph_built = _graph_built(project, unit)
    if conf_analysis == "high" and graph_built is False:
        gaps.append(
            "extraction-depth: analysis confidence=high but the unit class graph "
            "is empty (non-.NET deep extraction unavailable) — reading-reliable ≠ "
            "extraction-deep; human review recommended before /sdd-full"
        )

    if conf_analysis:
        for fname, c in us_confs:
            if c and _CONF_ORDER[c] > _CONF_ORDER[conf_analysis]:
                gaps.append(
                    f"confidence uprank: US {fname} ({c}) > analysis "
                    f"({conf_analysis}) — min-monotone Q3 violated"
                )
        if conf_feat and _CONF_ORDER[conf_feat] > _CONF_ORDER[conf_analysis]:
            gaps.append(
                f"confidence uprank: FEAT ({conf_feat}) > analysis "
                f"({conf_analysis}) — min-monotone Q3 violated"
            )
    declared_us = [c for _, c in us_confs if c]
    if conf_feat and declared_us:
        floor = min(declared_us, key=lambda c: _CONF_ORDER[c])
        if _CONF_ORDER[conf_feat] > _CONF_ORDER[floor]:
            gaps.append(
                f"confidence uprank: FEAT ({conf_feat}) > min(US) ({floor}) "
                f"— min-monotone Q3 violated"
            )

    # Inter-rung staleness (audit 2026-06-29) — re-wires [REVERSE_LADDER_STALE],
    # the ADR-documented risk whose emitter was purged as dead code (MA-7). A lower
    # rung re-run after the upper rungs leaves them out of sync; the unit-grained
    # extraction cache does NOT catch partial-rung regeneration. mtime-based, like
    # [REVERSE_INVENTORY_STALE]/ADV-1 (established pattern in this module). 1s
    # tolerance avoids false positives on near-simultaneous writes. Reported
    # separately from `gaps` (orthogonal to traceability), informational only.
    stale_findings: list[str] = []
    try:
        a_mtime = (plans_dir / f"{n}-{name}.analysis.md").stat().st_mtime
        feat_mtime = feat.stat().st_mtime
        us_mtimes = [f.stat().st_mtime for f in us_files]
        newest_us = max(us_mtimes) if us_mtimes else None
        if newest_us is not None and a_mtime > newest_us + 1:
            stale_findings.append(
                "3a analysis is newer than the 3b US — re-run /sdd-reverse-stories "
                "then /sdd-reverse-feat (upper rungs stale)"
            )
        if a_mtime > feat_mtime + 1:
            stale_findings.append(
                "3a analysis is newer than the 3c FEAT — re-run /sdd-reverse-feat"
            )
        if newest_us is not None and newest_us > feat_mtime + 1:
            stale_findings.append(
                "3b US are newer than the 3c FEAT — re-run /sdd-reverse-feat"
            )
    except OSError:
        pass

    verdict = "ladder-complete" if not gaps else ("partial" if len(gaps) <= 3 else "incomplete")
    return {
        "unit": unit, "n": n, "name": name, "artifacts": artifacts,
        "ran": True,
        "counts": {"feat_items": len(feat_items), "us_acs": len(us_acs), "tasks": len(tasks)},
        "confidence": {
            "analysis": conf_analysis,
            "us": {fname: c for fname, c in us_confs},
            "feat": conf_feat,
            "language": unit_language,
            "language_cap": unit_cap,
        },
        "extraction_depth": (
            "deep" if graph_built else ("shallow" if graph_built is False else "unknown")
        ),
        "verdict": verdict,
        "gap_count": len(gaps),
        "gaps": gaps,
        "class": "[REVERSE_LADDER_TRACEABILITY_GAP]" if gaps else None,
        "stale_findings": stale_findings,
        "stale_class": "[REVERSE_LADDER_STALE]" if stale_findings else None,
    }


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    p = argparse.ArgumentParser(prog="check_ladder_traceability", description="D3 ladder traceability enforcer (informational).")
    p.add_argument("--project", type=Path)
    p.add_argument("--unit")
    p.add_argument("--feat-path", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.feat_path is None and not (args.project and args.unit):
        print("ERROR: provide --feat-path OR (--project AND --unit)", file=sys.stderr)
        return 3
    try:
        report = check(args.project, args.unit, args.feat_path)
    except (FileNotFoundError, ValueError, KeyError) as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"[INFRA] {e}")
        return 3

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"=== Ladder traceability — {report.get('n')}-{report.get('name')} ({args.unit or 'feat-path'}) ===")
        print(f"  verdict: {report['verdict']}")
        if report.get("ran"):
            c = report["counts"]
            if report.get("shape") == "db-module":
                print(f"  shape  : db-module (2 barreaux — pas d'analyse 3a)")
                print(f"  counts : {c['feat_items']} FEAT items, {c['us_acs']} US ACs")
            else:
                print(f"  counts : {c['feat_items']} FEAT items, {c['us_acs']} US ACs, {c['tasks']} tasks")
            for g in report.get("gaps", [])[:20]:
                print(f"    • {g}")
            if report["gap_count"] > 20:
                print(f"    … +{report['gap_count'] - 20} more")
            stale = report.get("stale_findings", [])
            if stale:
                # Emitter for [REVERSE_LADDER_STALE] (informational, never blocking).
                print(f"  CAUSE: [REVERSE_LADDER_STALE] {len(stale)} rung(s) out of sync")
                for s in stale:
                    print(f"    ⚠ {s}")
        else:
            print(f"  {report.get('message')}")

    if not report.get("ran"):
        return 2
    return 0  # informational — gaps never block


if __name__ == "__main__":
    sys.exit(main())
