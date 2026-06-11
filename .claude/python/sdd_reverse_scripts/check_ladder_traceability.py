"""check_ladder_traceability.py — D3 enforcer for the reverse spec-ladder.

ADR governance-major-reverse-spec-ladder. Deterministic (0 token, stdlib only,
D4-isolated — no sdd_lib import). Verifies the traceability chain produced by
the 3-rung ladder for ONE unit :

    FEAT item (input/feats/{n}-{Name}.md)
        --covers--> US AC (output/us/{n}-{m}-{Name}.md)
            --covers--> task T-N (output/plans/{n}-{Name}.analysis.md)
                --evidence--> path:Lx-Ly

Emits [REVERSE_LADDER_TRACEABILITY_GAP] findings. **Informational, never
blocking** (mirrors check_feat_completeness.py) : gaps are reported, never
filled by invention (bias toward not-verified). Exit 0 unless an infra error
(unreadable inventory / missing allocation) occurs (exit 3).

Invocation :
    python .claude/python/sdd_reverse_scripts/check_ladder_traceability.py \
        --project workspace/old/{P} --unit U-3 [--json]
    python .claude/python/sdd_reverse_scripts/check_ladder_traceability.py \
        --feat-path workspace/input/feats/3-Login.md [--json]

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

REPO_ROOT = Path(__file__).resolve().parents[3]

_ITEM_ID_RE = re.compile(r"\*?\*?(SFD|FD|BR|AC)-\d+\*?\*?", re.IGNORECASE)
_COVERS_RE = re.compile(r"<!--\s*covers:\s*([^>]+?)\s*-->", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"<!--\s*evidence:\s*([^>]+?)\s*-->", re.IGNORECASE)
_TASK_ID_RE = re.compile(r"\bT-\d+\b")
_US_AC_REF_RE = re.compile(r"(\d+-\d+)\s*#\s*(AC-\d+)", re.IGNORECASE)


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
    feat = REPO_ROOT / "workspace" / "input" / "feats" / f"{n}-{name}.md"
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


def check(project: Path | None, unit: str | None, feat_path: Path | None) -> dict:
    feat, n, name = _resolve_feat(project, unit, feat_path)
    feats_dir = REPO_ROOT / "workspace" / "input" / "feats"
    us_dir = REPO_ROOT / "workspace" / "output" / "us"
    plans_dir = REPO_ROOT / "workspace" / "output" / "plans"

    feat_text = _read(feat) if feat else None
    analysis_text = _read(plans_dir / f"{n}-{name}.analysis.md")
    us_files = sorted(us_dir.glob(f"{n}-*-{name}.md")) if us_dir.is_dir() else []

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
    us_acs: list[dict] = []
    for f in us_files:
        t = _read(f)
        if t:
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

    verdict = "ladder-complete" if not gaps else ("partial" if len(gaps) <= 3 else "incomplete")
    return {
        "unit": unit, "n": n, "name": name, "artifacts": artifacts,
        "ran": True,
        "counts": {"feat_items": len(feat_items), "us_acs": len(us_acs), "tasks": len(tasks)},
        "verdict": verdict,
        "gap_count": len(gaps),
        "gaps": gaps,
        "class": "[REVERSE_LADDER_TRACEABILITY_GAP]" if gaps else None,
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
            print(f"  counts : {c['feat_items']} FEAT items, {c['us_acs']} US ACs, {c['tasks']} tasks")
            for g in report.get("gaps", [])[:20]:
                print(f"    • {g}")
            if report["gap_count"] > 20:
                print(f"    … +{report['gap_count'] - 20} more")
        else:
            print(f"  {report.get('message')}")

    if not report.get("ran"):
        return 2
    return 0  # informational — gaps never block


if __name__ == "__main__":
    sys.exit(main())
