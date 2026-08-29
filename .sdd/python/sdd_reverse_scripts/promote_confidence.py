"""promote_confidence.py — Human-validation gate for reverse-DB FEATs.

After a Tech Lead has reviewed a FEAT that sits at confidence=medium or low,
this script promotes it to confidence=high, unlocks the REVERSE-GATE
(allow-sdd-full=true), and re-stamps the M5 fingerprint so subsequent runs
of build_proc_feats.py recognise it as the authoritative generated version.

The script never invents facts; it is purely a status promotion tool.  The
Tech Lead is responsible for the review quality — the script only records the
decision mechanically.

CLI:
    python promote_confidence.py --feat-path workspace/feats/1-Contrat.md
                                  [--reason "Tech Lead review 2026-08-28"]
                                  [--dry-run]
                                  [--json]

Exit codes: 0 OK · 1 already high · 2 not a reverse FEAT · 3 IO error · 4 dry-run
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

from sdd_reverse.atomic_write_local import atomic_write_text

_FINGERPRINT_KEY = "generated-fingerprint"
_CONF_RE = re.compile(r"^(confidence:\s*)(\w+)\s*$", re.MULTILINE)
_GATE_RE = re.compile(
    r"<!--\s*REVERSE-GATE:\s*confidence=\w+\s*;[^-]*-->", re.MULTILINE
)
_FP_RE = re.compile(rf"^{_FINGERPRINT_KEY}:\s*[0-9a-f]+\s*$", re.MULTILINE)


def _fingerprint(body: str) -> str:
    import hashlib
    stripped = "\n".join(
        line for line in body.splitlines()
        if not line.startswith(f"{_FINGERPRINT_KEY}:")
    )
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:16]


def promote(feat_path: Path, *, reason: str = "", dry_run: bool = False) -> dict:
    try:
        text = feat_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"IO error: {exc}", "code": 3}

    if "generated-by: sdd-reverse" not in text:
        return {
            "ok": False,
            "error": f"{feat_path.name} is not a sdd-reverse FEAT (no 'generated-by: sdd-reverse')",
            "code": 2,
        }

    m = _CONF_RE.search(text)
    if not m:
        return {"ok": False, "error": "No 'confidence:' line found in frontmatter", "code": 3}

    current_conf = m.group(2)
    if current_conf == "high":
        return {"ok": True, "already_high": True, "code": 1}

    # Update frontmatter confidence
    new_text = _CONF_RE.sub(r"\g<1>high", text, count=1)

    # Update REVERSE-GATE comment
    reason_suffix = f" ; promoted={time.strftime('%Y-%m-%d')}"
    if reason:
        reason_suffix += f" ; reason={reason}"
    new_gate = f"<!-- REVERSE-GATE: confidence=high ; allow-sdd-full=true{reason_suffix} -->"
    new_text = _GATE_RE.sub(new_gate, new_text)

    # Re-stamp fingerprint (content changed, old stamp is now stale)
    fp = _fingerprint(new_text)
    if _FP_RE.search(new_text):
        new_text = _FP_RE.sub(f"{_FINGERPRINT_KEY}: {fp}", new_text)
    else:
        # No fingerprint yet — insert after first '---'
        lines = new_text.splitlines()
        if lines and lines[0].strip() == "---":
            lines.insert(1, f"{_FINGERPRINT_KEY}: {fp}")
        new_text = "\n".join(lines)

    if dry_run:
        return {
            "ok": True, "dry_run": True,
            "from": current_conf, "to": "high",
            "path": str(feat_path),
            "code": 4,
        }

    atomic_write_text(feat_path, new_text)
    return {
        "ok": True, "dry_run": False,
        "from": current_conf, "to": "high",
        "path": str(feat_path),
        "code": 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Promote a reverse-DB FEAT from medium/low confidence to high."
    )
    ap.add_argument("--feat-path", required=True, help="Path to the FEAT .md file")
    ap.add_argument("--reason", default="", help="Free-text reason (stored in REVERSE-GATE comment)")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change, do nothing")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    result = promote(Path(args.feat_path), reason=args.reason, dry_run=args.dry_run)

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result["code"] if result["code"] not in (0, 1, 4) else 0

    if not result["ok"]:
        print(f"ERROR: promote_confidence — {result['error']}", file=sys.stderr)
        print(f"CAUSE: [REVERSE_FEAT_VALIDATE_FAILED] {result['error']}", file=sys.stderr)
        return result["code"]

    if result.get("already_high"):
        print(f"[REVERSE] {args.feat_path} est déjà à confidence=high. (0%)")
        return 0

    if result.get("dry_run"):
        print(f"[REVERSE] --dry-run: {args.feat_path} passerait de "
              f"confidence={result['from']} → high. (0%)")
        return 0

    print(f"[REVERSE] Confidence promue : {result['path']} "
          f"{result['from']} → high · REVERSE-GATE unlocked. (100%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
