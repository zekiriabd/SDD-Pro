"""check_reverse_feat_for_full.py — Opt-in gate before /sdd-full (ADV-6).

Since /sdd-full is intouchable (design doc §3.1), this check is invoked
manually by the Tech Lead as :
    python -m sdd_reverse_scripts.check_reverse_feat_for_full \
        --feat-path workspace/feats/{n}-*.md \
        [--allow-reverse-low]

Exit codes:
    0  FEAT is non-reverse OR (reverse + confidence=high) OR (reverse + low + --allow-reverse-low)
    1  FEAT is reverse + confidence ∈ {medium, low} without --allow-reverse-low

The check reads:
    - <!-- REVERSE-GATE: confidence=... ; allow-sdd-full=... --> (primary)
    - Frontmatter `confidence:` (fallback)
    - Frontmatter `generated-by: sdd-reverse` (presence test)
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

# C6 bootstrap — canonical invocation is by file path, no PYTHONPATH needed.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sdd_reverse.console_safe import ensure_console_safe
from sdd_reverse.feat_structure_spec import REVERSE_GATE_RE, parse_frontmatter


def check_feat(feat_path: Path, allow_low: bool) -> tuple[int, dict]:
    """Return (exit_code, report_dict)."""
    if not feat_path.is_file():
        return 2, {"error": f"File not found: {feat_path}"}

    try:
        content = feat_path.read_text(encoding="utf-8")
    except OSError as e:
        return 2, {"error": f"I/O error: {e}"}

    fm, body = parse_frontmatter(content)
    generated_by = fm.get("generated-by", "")
    is_reverse = generated_by == "sdd-reverse"

    if not is_reverse:
        return 0, {
            "feat_path": str(feat_path),
            "is_reverse": False,
            "confidence": None,
            "allowed": True,
            "reason": "Non-reverse FEAT — no gate applies",
        }

    # Primary: REVERSE-GATE comment
    gate_match = REVERSE_GATE_RE.search(body)
    if gate_match:
        confidence = gate_match.group(1)
        allow_sdd_full = gate_match.group(2) == "true"
    else:
        # Fallback to frontmatter
        confidence = fm.get("confidence", "unknown")
        allow_sdd_full = confidence == "high"

    if allow_sdd_full:
        return 0, {
            "feat_path": str(feat_path),
            "is_reverse": True,
            "confidence": confidence,
            "allowed": True,
            "reason": "Reverse FEAT with confidence=high — allowed",
        }

    if allow_low:
        return 0, {
            "feat_path": str(feat_path),
            "is_reverse": True,
            "confidence": confidence,
            "allowed": True,
            "reason": f"Reverse FEAT confidence={confidence} but --allow-reverse-low passed",
        }

    return 1, {
        "feat_path": str(feat_path),
        "is_reverse": True,
        "confidence": confidence,
        "allowed": False,
        "reason": (
            f"Reverse FEAT with confidence={confidence}. "
            f"Human review required before /sdd-full. "
            f"Override with --allow-reverse-low."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_reverse_feat_for_full",
        description="Opt-in gate before /sdd-full on reverse-generated FEATs (ADV-6).",
    )
    parser.add_argument(
        "--feat-path", required=True,
        help="Path or glob to FEAT (e.g. workspace/feats/7-*.md)",
    )
    parser.add_argument(
        "--allow-reverse-low", action="store_true",
        help="Allow /sdd-full on reverse FEAT with confidence != high (audit-logged)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    ensure_console_safe()

    # Resolve glob if needed (single FEAT expected)
    matches = sorted(glob.glob(args.feat_path))
    if not matches:
        print(f"ERROR: No FEAT matched {args.feat_path}", file=sys.stderr)
        return 2
    if len(matches) > 1:
        print(f"ERROR: Multiple FEATs matched {args.feat_path}: {matches}", file=sys.stderr)
        return 2

    feat_path = Path(matches[0])
    code, report = check_feat(feat_path, args.allow_reverse_low)

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        # ASCII markers (M10 — Windows cp1252 console compat)
        icon = "[GO]" if code == 0 else "[NO-GO]"
        print(f"{icon} [REVERSE-GATE] {feat_path.name} - {report['reason']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
