"""validate_parity_features.py — gate déterministe des specs de parité Gherkin.

Phase 3.8 (agent reverse-parity-inspector). Deterministic (0 token, stdlib
only, D4-isolated — no sdd_lib import). Pour UNE FEAT reverse, vérifie les
fichiers `.feature` produits sous le parity-dir :

  Structure (bloquant WARN, exit 1 — [REVERSE_PARITY_INVALID]) :
    - >= 1 fichier .feature dans le parity-dir ;
    - chaque fichier porte exactement 1 ligne `Feature:` ;
    - chaque fichier porte >= 1 `Scenario:` / `Scenario Outline:` ;
    - chaque scénario porte >= 1 Given, >= 1 When, >= 1 Then (And/But tolérés) ;
    - chaque scénario porte >= 1 tag `@AC-N` ;
    - chaque tag `@AC-N` référence un AC existant de la FEAT (pas d'orphelin).

  Couverture (informational, exit 0 — [REVERSE_PARITY_COVERAGE_GAP]) :
    - chaque AC-N de la FEAT est couvert par >= 1 scénario ; les gaps sont
      rapportés, JAMAIS comblés par invention (bias toward not-verified §1).

Invocation (canonique par chemin de fichier, C6) :
    python .claude/python/sdd_reverse_scripts/validate_parity_features.py \
        --feat-path workspace/feats/{n}-{Name}.md \
        --parity-dir workspace/parity/feat-{n} [--json]

Exit codes :
    0  structure valide (couverture complete OU partial — informational)
    1  structure invalide ([REVERSE_PARITY_INVALID], WARN — l'agent itère, max 3)
    3  infra/usage (FEAT illisible, parity-dir absent, args invalides)
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

_FEATURE_RE = re.compile(r"^\s*Feature:", re.IGNORECASE)
_SCENARIO_RE = re.compile(r"^\s*Scenario(?:\s+Outline)?:", re.IGNORECASE)
_TAG_AC_RE = re.compile(r"@(AC-\d+)\b", re.IGNORECASE)
_TAG_LINE_RE = re.compile(r"^\s*@")
_STEP_RE = re.compile(r"^\s*(Given|When|Then|And|But)\b", re.IGNORECASE)
# AC IDs de la FEAT : `- AC-1:` / `**AC-1**` / `AC-1 :` en début d'item.
_FEAT_AC_RE = re.compile(r"^\s*[-*]\s*\*{0,2}(AC-\d+)\*{0,2}\s*[:—-]", re.MULTILINE)


def _read(path: Path) -> str | None:
    # utf-8-sig : tolère le BOM (fichiers édités sous Windows/PowerShell) qui
    # casserait sinon le match `^Feature:` en première ligne.
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None


def _feat_acs(feat_text: str) -> list[str]:
    """IDs AC-N déclarés dans la section Acceptance Criteria de la FEAT."""
    # Borne sur la section AC si présente (évite les mentions AC-N en prose).
    m = re.search(r"^##\s*Acceptance Criteria\s*$", feat_text, re.MULTILINE | re.IGNORECASE)
    scope = feat_text
    if m:
        tail = feat_text[m.end():]
        nxt = re.search(r"^##\s+", tail, re.MULTILINE)
        scope = tail[: nxt.start()] if nxt else tail
    seen: list[str] = []
    for ac in _FEAT_AC_RE.findall(scope):
        acu = ac.upper()
        if acu not in seen:
            seen.append(acu)
    return seen


def _parse_feature_file(path: Path) -> tuple[list[dict], list[str]]:
    """Retourne (scenarios[], errors[]) pour UN fichier .feature."""
    text = _read(path)
    errors: list[str] = []
    if text is None:
        return [], [f"{path.name}: unreadable"]
    lines = text.splitlines()

    feature_count = sum(1 for ln in lines if _FEATURE_RE.match(ln))
    if feature_count != 1:
        errors.append(f"{path.name}: {feature_count} `Feature:` line(s) (expected exactly 1)")

    scenarios: list[dict] = []
    pending_tags: list[str] = []
    current: dict | None = None
    for line_no, ln in enumerate(lines, start=1):
        if _TAG_LINE_RE.match(ln):
            pending_tags.extend(t.upper() for t in _TAG_AC_RE.findall(ln))
            continue
        if _SCENARIO_RE.match(ln):
            current = {
                "file": path.name, "line": line_no,
                "title": ln.split(":", 1)[1].strip() if ":" in ln else "",
                "acTags": list(pending_tags),
                "steps": {"given": 0, "when": 0, "then": 0},
            }
            scenarios.append(current)
            pending_tags = []
            continue
        if ln.strip() and not ln.lstrip().startswith("#"):
            pending_tags = []  # les tags ne portent que sur le bloc qui suit
        sm = _STEP_RE.match(ln)
        if sm and current is not None:
            kw = sm.group(1).lower()
            if kw in ("given", "when", "then"):
                current["steps"][kw] += 1

    if not scenarios and feature_count == 1:
        errors.append(f"{path.name}: no `Scenario:` block")
    for sc in scenarios:
        loc = f"{sc['file']}:{sc['line']}"
        if not sc["acTags"]:
            errors.append(f"{loc}: scenario without @AC-N tag")
        for kw in ("given", "when", "then"):
            if sc["steps"][kw] == 0:
                errors.append(f"{loc}: scenario missing `{kw.capitalize()}` step")
    return scenarios, errors


def main(argv: list[str] | None = None) -> int:
    ensure_console_safe()
    parser = argparse.ArgumentParser(description="Validate Gherkin parity specs against a reverse FEAT.")
    parser.add_argument("--feat-path", required=True, help="workspace/feats/{n}-{Name}.md")
    parser.add_argument("--parity-dir", required=True, help="workspace/parity/feat-{n}")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    feat_path = (REPO_ROOT / args.feat_path) if not Path(args.feat_path).is_absolute() else Path(args.feat_path)
    parity_dir = (REPO_ROOT / args.parity_dir) if not Path(args.parity_dir).is_absolute() else Path(args.parity_dir)

    feat_text = _read(feat_path)
    if feat_text is None:
        print(f"ERROR: validate_parity_features — FEAT unreadable\n"
              f"CAUSE: [REVERSE_UNIT_NOT_FOUND] {args.feat_path} absent ou illisible\n"
              f"FIX: vérifier le numéro de FEAT / relancer /sdd-reverse {{U-N}}")
        return 3
    if not parity_dir.is_dir():
        print(f"ERROR: validate_parity_features — parity-dir absent\n"
              f"CAUSE: [REVERSE_PARITY_INVALID] {args.parity_dir} inexistant\n"
              f"FIX: l'agent reverse-parity-inspector doit écrire les .feature avant validation")
        return 3

    acs = _feat_acs(feat_text)
    feature_files = sorted(parity_dir.glob("*.feature"))

    all_scenarios: list[dict] = []
    structure_errors: list[str] = []
    if not feature_files:
        structure_errors.append(f"{parity_dir.name}: no .feature file")
    for f in feature_files:
        scenarios, errors = _parse_feature_file(f)
        all_scenarios.extend(scenarios)
        structure_errors.extend(errors)

    feat_ac_set = set(acs)
    covered: set[str] = set()
    for sc in all_scenarios:
        for tag in sc["acTags"]:
            if tag in feat_ac_set:
                covered.add(tag)
            else:
                structure_errors.append(
                    f"{sc['file']}:{sc['line']}: tag @{tag} references no AC of the FEAT (orphan)"
                )

    coverage_gaps = [ac for ac in acs if ac not in covered]
    coverage_verdict = "complete" if not coverage_gaps else "partial"
    structure_verdict = "valid" if not structure_errors else "invalid"

    payload = {
        "feat": feat_path.name,
        "parityDir": str(parity_dir),
        "files": [f.name for f in feature_files],
        "scenarios": len(all_scenarios),
        "acTotal": len(acs),
        "acCovered": len(covered),
        "structure": {"verdict": structure_verdict, "errors": structure_errors},
        "coverage": {"verdict": coverage_verdict, "gaps": coverage_gaps},
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"parity {feat_path.name}: structure={structure_verdict} "
              f"coverage={coverage_verdict} ({len(covered)}/{len(acs)} AC, "
              f"{len(all_scenarios)} scenario(s))")
        for err in structure_errors:
            print(f"  [REVERSE_PARITY_INVALID] {err}")
        for ac in coverage_gaps:
            print(f"  [REVERSE_PARITY_COVERAGE_GAP] {ac} sans scenario de parite")

    return 1 if structure_errors else 0


if __name__ == "__main__":
    sys.exit(main())
