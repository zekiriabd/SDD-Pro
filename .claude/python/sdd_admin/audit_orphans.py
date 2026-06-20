"""Detect orphan artifacts in workspace/output/ (read-only).

v7.0.0 (audit 2026-06-05) — première implémentation effective des
scripts spec'd dans `docs/orphan-cleanup-policy.md`.

Un artefact est "orphan" quand sa source FEAT/US a été renommée ou
supprimée mais que les dérivés (US md, plans, code généré) sont
restés sur disque. Diff basenames `{n}-{m}-{Name}` entre :

- Source  : workspace/input/feats/{n}-*.md   (FEATs Tech Lead-owned)
- Source  : workspace/output/us/{n}-{m}-*.md (US PO-generated)
- Dérivés : workspace/output/plans/{n}-{m}-*.{back,front}.md
            workspace/output/qa/feat-{n}/
            (code généré sous workspace/output/src/{App,Backend,Lib}Name/
             non couvert ici — détection cross-fichier difficile sans
             marqueur ` // generated-by-us: ` dans les sources, à câbler v7.1+)

Usage :
    python audit_orphans.py [--feat N] [--root PATH] [--json]

Exit codes (cf. sdd_lib.exit_codes) :
    0 = SUCCESS (clean, aucun orphelin détecté)
    1 = FAIL_FAST (orphelins détectés — informational, pas une erreur de config)
    3 = INFRA_BLOCKED (workspace inaccessible, FS error)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Path bootstrap pour permettre l'invocation directe (python audit_orphans.py)
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402

# Basename d'une US/plan/feat : `{n}-{m}-Name` ou `{n}-Name`.
_US_BASENAME_RE = re.compile(r"^(\d+)-(\d+)-(.+)$")
_FEAT_BASENAME_RE = re.compile(r"^(\d+)-(.+)$")
_PLAN_SUFFIX_RE = re.compile(r"\.(back|front)$")


def _safe_iterdir(p: Path) -> list[Path]:
    """List dir contents safely (returns [] if not exists)."""
    try:
        return list(p.iterdir()) if p.is_dir() else []
    except (OSError, PermissionError):
        return []


def list_feats(root: Path) -> set[int]:
    """FEAT numbers présents sous workspace/input/feats/."""
    feats_dir = root / "workspace" / "input" / "feats"
    out: set[int] = set()
    for f in _safe_iterdir(feats_dir):
        if not f.is_file() or f.suffix != ".md":
            continue
        m = _FEAT_BASENAME_RE.match(f.stem)
        if m:
            out.add(int(m.group(1)))
    return out


def list_us_keys(root: Path) -> set[tuple[int, int]]:
    """Identités US `(n, m)` présentes sous workspace/output/us/."""
    us_dir = root / "workspace" / "output" / "us"
    out: set[tuple[int, int]] = set()
    for f in _safe_iterdir(us_dir):
        if not f.is_file() or f.suffix != ".md":
            continue
        m = _US_BASENAME_RE.match(f.stem)
        if m:
            out.add((int(m.group(1)), int(m.group(2))))
    return out


def find_orphans(
    root: Path, feat_filter: int | None = None
) -> dict[str, list[dict]]:
    """Identifier les orphelins par catégorie.

    Args:
        root: racine du repo SDD_Pro
        feat_filter: si non-None, ne considère que la FEAT N
    Returns:
        dict avec 4 clés : `us_orphans`, `plan_orphans`, `qa_orphans`,
        `direct_orphans` (FEAT supprimée mais US/plans/qa restants).
    """
    feats = list_feats(root)
    us_keys = list_us_keys(root)

    orphans: dict[str, list[dict]] = {
        "us_orphans": [],
        "plan_orphans": [],
        "qa_orphans": [],
        "direct_orphans": [],
    }

    # 1) US orphan = US sur disque dont la FEAT parente n'existe plus
    for n, m in sorted(us_keys):
        if feat_filter is not None and n != feat_filter:
            continue
        if n not in feats:
            us_dir = root / "workspace" / "output" / "us"
            for f in _safe_iterdir(us_dir):
                if f.stem.startswith(f"{n}-{m}-"):
                    orphans["us_orphans"].append(
                        {"path": str(f.relative_to(root)), "feat": n, "us": f"{n}-{m}"}
                    )

    # 2) Plan orphan = plan sur disque sans US correspondant
    plans_dir = root / "workspace" / "output" / "plans"
    for f in _safe_iterdir(plans_dir):
        if not f.is_file() or f.suffix != ".md":
            continue
        stem = f.stem  # ex: `1-2-Login.back`
        # Strip `.back` / `.front` suffix to get US basename
        clean_stem = _PLAN_SUFFIX_RE.sub("", stem)
        m = _US_BASENAME_RE.match(clean_stem)
        if not m:
            continue
        n_str, m_str, _ = m.groups()
        n_int, m_int = int(n_str), int(m_str)
        if feat_filter is not None and n_int != feat_filter:
            continue
        if (n_int, m_int) not in us_keys:
            orphans["plan_orphans"].append(
                {"path": str(f.relative_to(root)), "feat": n_int, "us": f"{n_int}-{m_int}"}
            )

    # 3) QA orphan = workspace/output/qa/feat-N/ pour FEAT N inexistante
    qa_dir = root / "workspace" / "output" / "qa"
    for d in _safe_iterdir(qa_dir):
        if not d.is_dir() or not d.name.startswith("feat-"):
            continue
        try:
            n_int = int(d.name.removeprefix("feat-"))
        except ValueError:
            continue
        if feat_filter is not None and n_int != feat_filter:
            continue
        if n_int not in feats:
            orphans["qa_orphans"].append(
                {"path": str(d.relative_to(root)), "feat": n_int}
            )

    # 4) Direct orphan = FEAT supprimée → tout dérivé (us/plans/qa) est listé
    #    (déjà couvert ci-dessus, mais on agrège un compteur par feat-n absente)
    absent_feats = {n for (n, _) in us_keys if n not in feats}
    for n in sorted(absent_feats):
        if feat_filter is not None and n != feat_filter:
            continue
        orphans["direct_orphans"].append({"feat": n, "reason": "FEAT supprimée, dérivés résiduels"})

    return orphans


def format_text_report(orphans: dict[str, list[dict]]) -> str:
    """Render a human-readable text report."""
    lines: list[str] = []
    total = sum(len(v) for v in orphans.values())
    lines.append(f"=== audit_orphans report (total findings: {total}) ===\n")

    for category, items in orphans.items():
        if not items:
            lines.append(f"[{category}] : 0 orphan")
            continue
        lines.append(f"[{category}] : {len(items)} orphan(s)")
        for entry in items:
            if "path" in entry:
                lines.append(f"  - {entry['path']}  (FEAT {entry.get('feat', '?')})")
            else:
                lines.append(f"  - FEAT {entry.get('feat', '?')} : {entry.get('reason', '')}")
        lines.append("")
    if total == 0:
        lines.append("\n✅ Aucun orphelin détecté.")
    else:
        lines.append(
            f"\nℹ️  Pour supprimer (avec backup .trash/) : "
            f"python .claude/python/sdd_admin/cleanup_orphans.py [--feat N] [--yes]"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect orphan artifacts (US/plans/qa) in workspace/output/"
    )
    parser.add_argument("--feat", type=int, default=None,
                        help="Restrict to FEAT N (default: scan all)")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of human-readable text")
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    if not root.exists() or not (root / ".claude").is_dir():
        print(f"ERROR: {root} is not a SDD_Pro project root (.claude/ missing)",
              file=sys.stderr)
        return INFRA_BLOCKED

    try:
        orphans = find_orphans(root, feat_filter=args.feat)
    except OSError as e:
        print(f"ERROR: filesystem error during scan: {e}", file=sys.stderr)
        return INFRA_BLOCKED

    if args.json:
        print(json.dumps({"orphans": orphans, "root": str(root)}, indent=2))
    else:
        print(format_text_report(orphans))

    total = sum(len(v) for v in orphans.values())
    return FAIL_FAST if total > 0 else SUCCESS


if __name__ == "__main__":
    sys.exit(main())
