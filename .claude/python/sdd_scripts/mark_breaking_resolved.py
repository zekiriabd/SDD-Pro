#!/usr/bin/env python3
"""SDD_Pro: mark BREAKING CHANGES sections as RESOLVED post-build.

Externalises dev-backend STEP 8.5 / dev-frontend STEP 11.5 logic.

Searches the project's `CLAUDE.md` for a `## BREAKING CHANGES` section,
checks coherence with files modified by the current US, marks it
`## BREAKING CHANGES — RESOLVED {YYYY-MM-DD}` with a status block.

Usage:
    python mark_breaking_resolved.py \\
        --claude-md workspace/output/src/AppName/CLAUDE.md \\
        --modified-files "Pages/Bebes.razor,Components/BebeForm.razor" \\
        --build-command "dotnet build" \\
        [--dry-run]

Exit codes:
    0  Section absent or already RESOLVED → silent skip
    1  Section present, marked RESOLVED successfully
    2  Section present but no coherence with modified files → skip
    3  Error (file missing, parse failure)

Migrated from .claude/scripts/mark-breaking-resolved.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.stderr import warn  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--claude-md", required=True)
    p.add_argument("--modified-files", required=True,
                   help="Comma-separated list of files modified by current US")
    p.add_argument("--build-command", default="dotnet build")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.claude_md)

    if not path.is_file():
        warn(f"ERROR: CLAUDE.md not found: {args.claude_md}")
        return 3

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        warn(f"ERROR: read failed: {e}")
        return 3

    h2_re = re.compile(r"(?m)^##\s+BREAKING\s+CHANGES\s*$")
    h2_resolved_re = re.compile(r"(?m)^##\s+BREAKING\s+CHANGES\s+—\s+RESOLVED")

    if not h2_re.search(content):
        if h2_resolved_re.search(content):
            print("[SKIP] Section BREAKING CHANGES déjà marquée RESOLVED")
        else:
            print("[SKIP] Aucune section BREAKING CHANGES dans le CLAUDE.md")
        return 0

    # Extract section body
    section_re = re.compile(
        r"(?ms)^##\s+BREAKING\s+CHANGES\s*$\r?\n(.*?)(?=^##\s|\Z)"
    )
    m_section = section_re.search(content)
    if not m_section:
        print(
            "ERROR: Impossible d'extraire le contenu de la section BREAKING CHANGES",
            file=sys.stderr,
        )
        return 3
    section_body = m_section.group(1)

    # Check coherence with modified files
    modified_list = [f.strip() for f in args.modified_files.split(",") if f.strip()]
    coherent = False
    matching: list[str] = []
    for f in modified_list:
        short = os.path.basename(f)
        if re.search(re.escape(short), section_body):
            coherent = True
            matching.append(short)
        elif re.search(re.escape(f), section_body):
            coherent = True
            matching.append(f)

    if not coherent:
        print(
            "[SKIP] Section BREAKING CHANGES présente mais aucun fichier modifié par "
            "cette US n'est mentionné — laisser l'autre US la résoudre"
        )
        return 2

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resolved_header = f"## BREAKING CHANGES — RESOLVED {today}"
    encart = (
        f"> **Statut** : ✅ RESOLU — `{args.build_command}` passe (0 erreur).\n"
        f"> Archive historique. Suppression au prochain ``/arch-init``.\n\n"
    )

    new_content = h2_re.sub(resolved_header + "\r\n" + encart, content, count=1)

    if args.dry_run:
        print(f"[DRY-RUN] Marquerait RESOLVED — fichiers concordants : {', '.join(matching)}")
        return 1

    # Atomic write via .tmp + rename
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(new_content, encoding="utf-8", newline="")
    tmp_path.replace(path)

    print(f"[OK] Section BREAKING CHANGES marquée RESOLVED ({today})")
    print(f"      Fichiers concordants : {', '.join(matching)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
