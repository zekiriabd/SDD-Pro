#!/usr/bin/env python3
"""SDD_Pro: compact bulky frontend plans to reduce agent context.

Archives the full plan then replaces the file with a short execution
contract. Reduces tokens/cost/latency when agents re-read plans.

Usage:
    python compact_front_plans.py
        [--plans-dir workspace/output/plans]
        [--archive-dir workspace/output/.sys/.audit/plan-archive]
        [--target-bytes 12000]
        [--dry-run]

Migrated from .claude/scripts/compact-front-plans.ps1 (2026-05-13).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.paths import normalize, repo_root  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--plans-dir", default=None)
    p.add_argument("--archive-dir", default=None)
    p.add_argument("--target-bytes", type=int, default=12000)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def extract_frontmatter(text: str) -> str:
    m = re.match(r"(?s)^---\r?\n(.*?)\r?\n---\r?\n", text)
    return m.group(0) if m else ""


def extract_title(text: str) -> str:
    m = re.search(r"(?m)^#\s+.+$", text)
    return m.group(0) if m else "# Plan technique frontend"


def extract_section(text: str, heading_pattern: str, max_chars: int) -> str:
    m = re.search(rf"(?ms)^##\s+{heading_pattern}.*?(?=^##\s+|\Z)", text)
    if not m:
        return ""
    section = m.group(0).strip()
    if len(section) <= max_chars:
        return section
    return section[:max_chars].rstrip() + (
        "\n\n> Section tronquee par compact_front_plans.py."
    )


def extract_file_rows(text: str) -> str:
    matches = re.findall(r"(?m)^- path:\s*(.+)$", text)
    if not matches:
        return "- Aucun fichier detecte dans le plan original."
    rows = [f"- `{path.strip()}`" for path in matches[:40]]
    return "\n".join(rows)


def extract_key_notes(text: str) -> str:
    notes: list[str] = []
    for line in text.splitlines():
        if re.match(r"^\s*[-*]\s+\*\*(.+?)\*\*", line):
            notes.append(re.sub(r"\s+", " ", line.strip()))
        if len(notes) >= 12:
            break
    if not notes:
        return "- Voir archive complete pour les arbitrages detailles."
    return "\n".join(notes)


def build_compact(raw: str, rel_archive: str) -> str:
    fm = extract_frontmatter(raw)
    title = extract_title(raw)
    limits = extract_section(raw, r"Limites connues.*", 2500)
    files_section = extract_file_rows(raw)
    notes_section = extract_key_notes(raw)
    limits_section = limits if limits else (
        "## Limites connues du plan\n\n"
        "- Non detaillees dans la version compacte ; consulter l'archive complete si necessaire."
    )

    return (
        f"{fm}{title}\n\n"
        "> Plan compacte pour consommation agentique recurrente.\n"
        f"> Archive complete : `{rel_archive}`\n"
        "> Objectif : garder le contrat d'execution, reduire tokens/cout/latence.\n\n"
        "## Contrat d'execution\n\n"
        "- Respecter strictement l'US et le mockup HTML declares dans le frontmatter.\n"
        "- Ne pas relire l'archive complete sauf arbitrage ambigu ou review humaine.\n"
        "- Preserver les fichiers existants mentionnes dans le plan original.\n"
        "- Appliquer les regles stack, ownership, QA ownership et anti-derive du projet.\n\n"
        "## Fichiers a creer ou modifier\n\n"
        f"{files_section}\n\n"
        "## Arbitrages essentiels\n\n"
        f"{notes_section}\n\n"
        f"{limits_section}\n"
    )


def main() -> int:
    args = parse_args()
    root = repo_root()
    plans_dir = Path(args.plans_dir) if args.plans_dir else root / "workspace" / "output" / "plans"
    archive_dir = Path(args.archive_dir) if args.archive_dir else (
        root / "workspace" / "output" / ".sys" / ".audit" / "plan-archive"
    )

    if not plans_dir.is_dir():
        print(f"[SKIP] Plans dir not found: {plans_dir}")
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(plans_dir.glob("*.front.md"))
    summary: list[dict] = []

    for file in files:
        try:
            raw = file.read_text(encoding="utf-8")
        except OSError:
            continue
        old_bytes = len(raw.encode("utf-8"))
        if old_bytes <= args.target_bytes:
            summary.append({
                "file": file.name,
                "oldBytes": old_bytes,
                "newBytes": old_bytes,
                "action": "skip",
            })
            continue

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archive_name = f"{file.stem}.{timestamp}.full.md"
        archive_path = archive_dir / archive_name
        try:
            rel_archive = normalize(archive_path.relative_to(root))
        except ValueError:
            rel_archive = normalize(archive_path)

        compact = build_compact(raw, rel_archive)
        new_bytes = len(compact.encode("utf-8"))
        if new_bytes > args.target_bytes:
            cutoff = max(0, args.target_bytes - 500)
            compact = (
                compact[: min(len(compact), cutoff)].rstrip()
                + "\n\n> Compactage dur applique: consulter l'archive complete pour le detail restant.\n"
            )
            new_bytes = len(compact.encode("utf-8"))

        if not args.dry_run:
            shutil.copy2(file, archive_path)
            file.write_text(compact, encoding="utf-8")

        summary.append({
            "file": file.name,
            "oldBytes": old_bytes,
            "newBytes": new_bytes,
            "action": "compact",
            "archive": rel_archive,
        })

    if summary:
        col_widths = {
            "file": max(len("file"), max(len(s["file"]) for s in summary)),
            "old": max(len("oldBytes"), max(len(str(s["oldBytes"])) for s in summary)),
            "new": max(len("newBytes"), max(len(str(s["newBytes"])) for s in summary)),
            "action": max(len("action"), max(len(s["action"]) for s in summary)),
        }
        header = (
            f"{'file':<{col_widths['file']}}  "
            f"{'oldBytes':>{col_widths['old']}}  "
            f"{'newBytes':>{col_widths['new']}}  "
            f"{'action':<{col_widths['action']}}"
        )
        print(header)
        print("-" * len(header))
        for s in summary:
            print(
                f"{s['file']:<{col_widths['file']}}  "
                f"{s['oldBytes']:>{col_widths['old']}}  "
                f"{s['newBytes']:>{col_widths['new']}}  "
                f"{s['action']:<{col_widths['action']}}"
            )
    else:
        print("(no plans matched)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
