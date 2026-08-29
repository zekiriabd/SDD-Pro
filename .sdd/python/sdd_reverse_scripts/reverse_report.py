"""reverse_report.py — Markdown synthesis report for a db-reverse run.

Reads inventory.json + all produced User Stories + all produced FEATs and
renders a per-module table showing: objects, tiers, US counts, confidence,
REVERSE-GATE status and open items.  0 token, deterministic — the Tech Lead
runs this after a reverse run to get a single-page decision surface before
launching /sdd-full on the high-confidence FEATs.

CLI:
    python reverse_report.py --project NounouJob [--workspace workspace] [--json]

Output: Markdown to stdout (redirect to workspace/old/{DB}/.sys/reverse-report.md)

Exit codes: 0 OK · 2 inventory missing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent.parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

_CONF_RE = re.compile(r"^confidence:\s*(\w+)\s*$", re.MULTILINE)
_GATE_RE = re.compile(r"<!--\s*REVERSE-GATE:[^-]*allow-sdd-full=(\w+)[^-]*-->")
_US_COUNT_RE = re.compile(r"^#\s+US-\d+", re.MULTILINE)
_AC_RE = re.compile(r"^\s*-\s*\**\s*AC-\d+\s*\**\s*:", re.MULTILINE)
_ANALYZED_RE = re.compile(r"^us-analyzed:\s*(\d+)\s*$", re.MULTILINE)
_TEMPLATED_RE = re.compile(r"^us-templated:\s*(\d+)\s*$", re.MULTILINE)
_TIER_RE = re.compile(r"^tier:\s*(\w+)\s*$", re.MULTILINE)


def _read_feat(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    conf_m = _CONF_RE.search(text)
    gate_m = _GATE_RE.search(text)
    ana_m = _ANALYZED_RE.search(text)
    tpl_m = _TEMPLATED_RE.search(text)
    return {
        "confidence": conf_m.group(1) if conf_m else "unknown",
        "allow_sdd_full": gate_m.group(1) if gate_m else "unknown",
        "us_analyzed": int(ana_m.group(1)) if ana_m else "?",
        "us_templated": int(tpl_m.group(1)) if tpl_m else "?",
    }


def _read_us(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"ac_count": 0}
    return {"ac_count": len(_AC_RE.findall(text))}


def _tier_icon(tier: str) -> str:
    return {"none": "⬜", "fast": "🟢", "balanced": "🟡", "deep": "🔴"}.get(tier, "❓")


def _conf_icon(conf: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🔴", "unknown": "❓"}.get(conf, "❓")


def build_report(project: str, ws: Path) -> dict:
    inv_path = ws / "old" / project / ".sys" / "inventory.json"
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {"error": str(exc)}

    allocs: dict[str, int] = inventory.get("_featAllocations", {})
    db_type = inventory.get("databaseType", "unknown")
    units = inventory.get("units", [])
    us_dir = ws / "us"
    feats_dir = ws / "feats"

    tier_counts: dict[str, int] = {"none": 0, "fast": 0, "balanced": 0, "deep": 0}
    modules: list[dict] = []

    for u in units:
        uid = u["id"]
        n = allocs.get(uid, "?")
        name = u.get("suggestedName", uid)
        procs = u.get("procedures", [])

        obj_tiers: dict[str, int] = {"none": 0, "fast": 0, "balanced": 0, "deep": 0}
        for p in procs:
            t = p.get("tier", "none")
            obj_tiers[t] = obj_tiers.get(t, 0) + 1
            tier_counts[t] = tier_counts.get(t, 0) + 1

        # Collect US
        us_files = sorted(us_dir.glob(f"{n}-*-*.md")) if isinstance(n, int) else []
        total_acs = sum(_read_us(f)["ac_count"] for f in us_files)

        # Collect FEAT
        feat_files = sorted(feats_dir.glob(f"{n}-*.md")) if isinstance(n, int) else []
        feat_data = _read_feat(feat_files[0]) if feat_files else {}

        modules.append({
            "uid": uid,
            "n": n,
            "name": name,
            "objects": len(procs),
            "tiers": obj_tiers,
            "us_count": len(us_files),
            "total_acs": total_acs,
            "feat": feat_data,
            "conf": feat_data.get("confidence", "—"),
            "gate": feat_data.get("allow_sdd_full", "—"),
        })

    return {
        "project": project,
        "db_type": db_type,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "modules": modules,
        "tier_counts": tier_counts,
        "total_objects": sum(tier_counts.values()),
    }


def render_markdown(report: dict) -> str:
    if "error" in report:
        return f"# Rapport reverse — ERREUR\n\n`{report['error']}`\n"

    L: list[str] = []
    L.append(f"# Rapport reverse DB — `{report['project']}` ({report['db_type']})")
    L.append(f"\n> Généré le {report['generated']} · {report['total_objects']} objet(s) SQL")
    L.append("")

    tc = report["tier_counts"]
    tot = report["total_objects"] or 1
    L.append("## Distribution des tiers")
    L.append("")
    L.append(f"| Tier | Objets | % |")
    L.append("|---|---:|---:|")
    for tier in ("deep", "balanced", "fast", "none"):
        count = tc.get(tier, 0)
        L.append(f"| {_tier_icon(tier)} `{tier}` | {count} | {count/tot*100:.0f}% |")
    L.append("")

    # Gate summary
    modules = report["modules"]
    go = sum(1 for m in modules if m["gate"] == "true")
    nogo = sum(1 for m in modules if m["gate"] == "false")
    unknown = len(modules) - go - nogo
    L.append("## Synthèse REVERSE-GATE")
    L.append("")
    L.append(f"- 🟢 **{go}** FEAT(s) prêtes pour `/sdd-full` (`allow-sdd-full=true`)")
    L.append(f"- 🔴 **{nogo}** FEAT(s) bloquées — revue humaine requise")
    if unknown:
        L.append(f"- ❓ **{unknown}** FEAT(s) sans gate détecté (FEAT manquante ou non générée)")
    L.append("")

    L.append("## Par module")
    L.append("")
    L.append("| # | Module | Objets | ⬜none | 🟢fast | 🟡bal | 🔴deep | US | ACs | Conf | GATE |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|")

    for m in sorted(modules, key=lambda x: x["n"] if isinstance(x["n"], int) else 999):
        t = m["tiers"]
        gate_icon = {"true": "✅", "false": "🚫", "—": "❓"}.get(m["gate"], "❓")
        feat_info = m["feat"]
        analyzed = feat_info.get("us_analyzed", "?")
        templated = feat_info.get("us_templated", "?")
        us_detail = f"{m['us_count']}"
        if analyzed != "?" or templated != "?":
            us_detail += f" ({analyzed}↑{templated}⬜)"
        L.append(
            f"| {m['n']} | `{m['name']}` | {m['objects']} "
            f"| {t.get('none',0)} | {t.get('fast',0)} | {t.get('balanced',0)} | {t.get('deep',0)} "
            f"| {us_detail} | {m['total_acs']} "
            f"| {_conf_icon(m['conf'])} `{m['conf']}` | {gate_icon} |"
        )
    L.append("")

    # Blocked FEATs: action required
    blocked = [m for m in modules if m["gate"] == "false"]
    if blocked:
        L.append("## Actions requises (confidence < high)")
        L.append("")
        L.append("Pour chaque FEAT bloquée, après revue humaine :")
        L.append("")
        for m in blocked:
            feat_path = f"workspace/feats/{m['n']}-{m['name']}.md"
            L.append(f"```bash")
            L.append(f"python .sdd/python/sdd_reverse_scripts/promote_confidence.py \\")
            L.append(f'  --feat-path {feat_path} \\')
            L.append(f'  --reason "revue Tech Lead {time.strftime("%Y-%m-%d")}"')
            L.append(f"```")
        L.append("")

    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reverse-DB run synthesis report.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default="workspace")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--output", help="Write report to this file instead of stdout")
    args = ap.parse_args(argv)

    report = build_report(args.project, Path(args.workspace))

    if "error" in report:
        print(f"ERROR: reverse_report — inventory missing\n"
              f"CAUSE: [REVERSE_UNIT_NOT_FOUND] {report['error']}", file=sys.stderr)
        return 2

    if args.as_json:
        out = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        out = render_markdown(report)

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"[REVERSE] Rapport écrit dans {args.output}. (100%)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
