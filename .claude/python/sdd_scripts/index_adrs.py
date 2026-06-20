"""SDD_Pro : regenerate workspace/output/.sys/.context/adrs/INDEX.md.

Deterministic replacement for the ``dashboard`` agent (Haiku 4.5) which
was retired in v7.0.0 — its sole remaining output (the ADRs index) is
mechanical glob + parse + render with no reasoning involved.

Convention :
    ADR filenames follow ``ADR-{YYYYMMDDTHHmmss}-{slug}.md`` with H1
    titre court and an ``Status:`` field in the markdown body (defaults
    to "Accepted").

Sort : alphabetic on filename = chronological (timestamp ISO).

Usage :
    python -m sdd_scripts.index_adrs              # default paths
    python -m sdd_scripts.index_adrs --adrs-dir <p> --output <p>
    python -m sdd_scripts.index_adrs --json       # JSON summary to stdout

Exit codes :
    0 = OK (INDEX.md written, atomic via .tmp)
    1 = template missing or unreadable
    2 = atomic write self-check failed
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_PY_ROOT = Path(__file__).resolve().parent.parent
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402
from sdd_lib.atomic_write import atomic_write_text  # noqa: E402


DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "templates" / "adrs-index.template.md"
)


_TS_RE = re.compile(r"^ADR-(\d{8}T\d{6})(?:-[a-z0-9]+)?-(.+)\.md$")
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(r"^Status:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)


def parse_adr(path: Path) -> dict[str, str]:
    """Extract (filename, title, status, phase, date) from one ADR file.

    Tolerant to missing fields : returns ``"?"`` placeholders.
    """
    filename = path.name
    m = _TS_RE.match(filename)
    if m is None:
        return {
            "filename": filename,
            "title": "(filename does not match ADR convention)",
            "status": "?",
            "phase": "?",
            "date": "?",
        }
    ts = m.group(1)  # YYYYMMDDTHHmmss
    date = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"

    text = ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        # Audit mineur #3 v7.0.0-alpha 2026-06-05 : log instead of silent swallow.
        # Downstream still works (empty `text` → "Accepted" default + filename title),
        # but a stderr trace helps when a real I/O bug occurs in the wild.
        sys.stderr.write(f"WARN index_adrs: cannot read {path}: {e}\n")

    title_match = _H1_RE.search(text)
    title = title_match.group(1).strip() if title_match else m.group(2)

    status_match = _STATUS_RE.search(text)
    status = status_match.group(1).strip() if status_match else "Accepted"

    # Phase inference : crude heuristic based on slug — overridden by an
    # explicit ``Phase:`` field if present (post-v7.0.0 convention).
    phase_match = re.search(r"^Phase:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    if phase_match:
        phase = phase_match.group(1).strip()
    else:
        slug = m.group(2).lower()
        if "governance" in slug or "stack" in slug or "schema" in slug or "auth" in slug:
            phase = "4-ARCH"
        else:
            phase = "5-CODE"

    return {
        "filename": filename,
        "title": title,
        "status": status,
        "phase": phase,
        "date": date,
    }


def render(template: str, adrs: list[dict[str, str]], project_name: str) -> str:
    rows = "\n".join(
        f"| `{a['filename']}` | {a['title']} | {a['status']} | {a['phase']} | {a['date']} |"
        for a in adrs
    ) or "| _(no ADRs yet)_ | | | | |"

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        template
        .replace("{ProjectName}", project_name)
        .replace("{GeneratedAt}", generated_at)
        .replace("{ADRCount}", str(len(adrs)))
        .replace("{ADRRows}", rows)
    )


def write_atomic(path: Path, content: str) -> bool:
    """Write `content` atomically via sdd_lib.atomic_write_text + read-back self-check.

    Delegates the atomic write semantics (`.sddtmp` + fsync + os.replace) to
    `sdd_lib.atomic_write.atomic_write_text` (cf. build-and-loop.md §2.bis).
    Read-back self-check preserved post-write to satisfy exit code 2 contract.
    """
    try:
        atomic_write_text(path, content)
    except OSError:
        return False
    try:
        if path.read_text(encoding="utf-8") != content:
            return False
    except OSError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n", 1)[0])
    p.add_argument("--adrs-dir", type=Path, default=None,
                   help="Directory containing ADR-*.md files")
    p.add_argument("--output", type=Path, default=None,
                   help="Output INDEX.md path")
    p.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE,
                   help="Path to adrs-index.template.md")
    p.add_argument("--project-name", default=None,
                   help="Project name (substituted in template). Defaults "
                        "to the repo root directory name.")
    p.add_argument("--json", action="store_true",
                   help="Print JSON summary to stdout instead of human line")
    args = p.parse_args(argv)

    root = repo_root()
    adrs_dir = args.adrs_dir or (root / "workspace" / "output" / ".sys" / ".context" / "adrs")
    output = args.output or (adrs_dir / "INDEX.md")
    project_name = args.project_name or root.name

    if not args.template.is_file():
        print(f"ERROR: index_adrs — template missing", file=sys.stderr)
        print(f"CAUSE: [NOT_FOUND] {args.template}", file=sys.stderr)
        print(f"FIX: ensure .claude/templates/adrs-index.template.md exists", file=sys.stderr)
        return FAIL_FAST
    template = args.template.read_text(encoding="utf-8")

    adrs: list[dict[str, str]] = []
    if adrs_dir.is_dir():
        for path in sorted(adrs_dir.glob("ADR-*.md")):
            adrs.append(parse_adr(path))

    content = render(template, adrs, project_name)
    ok = write_atomic(output, content)
    if not ok:
        print(f"ERROR: index_adrs — atomic write self-check failed", file=sys.stderr)
        print(f"CAUSE: [QA_OUTPUT_INVALID] {output}.tmp content mismatch", file=sys.stderr)
        return CORRECTIBLE
    if args.json:
        print(json.dumps({
            "output": str(output),
            "adr_count": len(adrs),
            "project_name": project_name,
        }, separators=(",", ":")))
    else:
        msg = f"INDEX.md ({len(adrs)} ADRs"
        if len(adrs) == 0:
            msg += ", empty"
        msg += ") refreshed"
        print(f"OK index_adrs — {msg}")
    return SUCCESS
if __name__ == "__main__":
    raise SystemExit(main())
