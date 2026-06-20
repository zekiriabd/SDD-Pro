#!/usr/bin/env python3
"""SDD_Pro: convert a FEAT into a single POC pseudo-US (v7.1+ /sdd-poc).

Used by the `/sdd-poc {n}` command to bypass `/us-generate` and produce
**one** pseudo-User-Story per FEAT (`{n}-1-{FeatName}`) that aggregates
all SFD/BR/AC/FD ids of the parent FEAT. The pseudo-US lets the rest of
the pipeline (arch + dev-backend + dev-frontend) run unchanged — they
read a regular US file at `workspace/output/us/{n}-1-*.md` without
knowing it was auto-generated.

The pseudo-US is **marked explicitly** in its frontmatter via :
    generated-by: feat_to_pseudo_us.py
    poc-mode: true

…so that subsequent `/us-generate {n} --replace-pseudo` can detect and
replace it with real granular US, and so that the rest of SDD_Pro can
distinguish POC mode from full mode in dashboards.

Mockup HTML handling :
  - if `workspace/input/ui/{n}-1-{FeatName}.html` already exists → OK
  - elif `workspace/input/ui/{n}-{FeatName}.html` exists (POC user
    convention) → COPY to `{n}-1-{FeatName}.html` (Windows-safe ;
    symlink fragile)
  - else → no mockup, dev-frontend works without HTML reference

Usage:
    python feat_to_pseudo_us.py --feat-number 1
    python feat_to_pseudo_us.py --feat-number 1 --force        # overwrite real US
    python feat_to_pseudo_us.py --feat-number 1 --json         # machine output
    python feat_to_pseudo_us.py --feat-number 1 --dry-run      # preview only

Exit codes (sdd_lib.exit_codes convention) :
    0  SUCCESS — pseudo-US written (or already up-to-date, idempotent)
    1  FAIL_FAST — FEAT not found / ambiguous / unreadable / non-pseudo US
                    already present without --force
    3  INFRA_BLOCKED — I/O write error, permission denied
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.atomic_write import atomic_write_text  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, INFRA_BLOCKED, SUCCESS  # noqa: E402
from sdd_lib.paths import iso_now, repo_root  # noqa: E402
from sdd_lib.stderr import error_block, warn  # noqa: E402

# Stable IDs in the FEAT (cf. CLAUDE.md §2)
SFD_LINE_RE = re.compile(r"(?m)^- (SFD-\d+):\s*(.+)$")
BR_LINE_RE = re.compile(r"(?m)^- (BR-\d+):\s*(.+)$")
AC_LINE_RE = re.compile(r"(?m)^- (AC-\d+):\s*(.+)$")
FD_LINE_RE = re.compile(r"(?m)^- (FD-\d+):\s*(.+)$")

# Objective section (free text — used for the User Story narrative)
OBJECTIVE_SECTION_RE = re.compile(
    r"(?ms)^## Objective\s*$\r?\n(.*?)(?=^##\s|\Z)"
)
ACTORS_SECTION_RE = re.compile(
    r"(?ms)^## Actors\s*$\r?\n(.*?)(?=^##\s|\Z)"
)
ACTORS_LINE_RE = re.compile(r"(?m)^- ([^:]+?)(?::\s*(.+))?$")

# Detect existing pseudo-US (idempotence + non-overwrite guard)
PSEUDO_US_MARKER_RE = re.compile(
    r"(?m)^generated-by:\s*feat_to_pseudo_us\.py\s*$"
)


def feat_name_to_us_name(feat_basename: str) -> str:
    """Convert FEAT basename to US-style Name (capitalized dash-segments).

    Conventions (CLAUDE.md §1) : Capitale initiale, pas d'accents, tirets
    pour espaces. The FEAT basename is already dash-separated and ascii ;
    we only need to capitalize the first letter of each segment.

    Examples:
        spec-connexion          -> Spec-Connexion
        auth-jwt                -> Auth-Jwt
        reset-password-flow     -> Reset-Password-Flow
        gestion-bebes           -> Gestion-Bebes
    """
    segments = feat_basename.split("-")
    return "-".join(seg[:1].upper() + seg[1:] for seg in segments if seg)


def find_feat_file(root: Path, feat_number: int) -> tuple[Path | None, str | None]:
    """Locate the FEAT file `workspace/input/feats/{N}-*.md`.

    Returns (path, error_code). On success : (Path, None). On error :
    (None, code) where code is FEAT_NOT_FOUND or FEAT_AMBIGUOUS.
    """
    feats_dir = root / "workspace" / "input" / "feats"
    if not feats_dir.is_dir():
        return None, "FEAT_NOT_FOUND"
    matches = sorted(feats_dir.glob(f"{feat_number}-*.md"))
    if not matches:
        return None, "FEAT_NOT_FOUND"
    if len(matches) > 1:
        return None, "FEAT_AMBIGUOUS"
    return matches[0], None


def compute_feat_hash_8(feat_path: Path) -> str:
    """First 8 hex chars of sha256(feat_file_bytes) — matches preflight.py."""
    return hashlib.sha256(feat_path.read_bytes()).hexdigest()[:8]


def extract_feat_data(content: str) -> dict:
    """Pure extraction — returns SFD/BR/AC/FD lists, Objective, Actors."""
    sfd = [(m.group(1), m.group(2).strip()) for m in SFD_LINE_RE.finditer(content)]
    br = [(m.group(1), m.group(2).strip()) for m in BR_LINE_RE.finditer(content)]
    ac = [(m.group(1), m.group(2).strip()) for m in AC_LINE_RE.finditer(content)]
    fd = [(m.group(1), m.group(2).strip()) for m in FD_LINE_RE.finditer(content)]

    objective = ""
    obj_match = OBJECTIVE_SECTION_RE.search(content)
    if obj_match:
        objective = obj_match.group(1).strip()

    actors: list[tuple[str, str]] = []
    actors_match = ACTORS_SECTION_RE.search(content)
    if actors_match:
        for m in ACTORS_LINE_RE.finditer(actors_match.group(1)):
            name = m.group(1).strip()
            desc = (m.group(2) or "").strip()
            if name and not name.startswith("<"):
                actors.append((name, desc))

    return {
        "sfd": sfd,
        "br": br,
        "ac": ac,
        "fd": fd,
        "objective": objective,
        "actors": actors,
    }


def existing_us_files(root: Path, feat_number: int) -> list[Path]:
    """All `{N}-*-*.md` files under workspace/output/us/."""
    us_dir = root / "workspace" / "output" / "us"
    if not us_dir.is_dir():
        return []
    return sorted(us_dir.glob(f"{feat_number}-*.md"))


def is_pseudo_us(path: Path) -> bool:
    """Detect via the `generated-by: feat_to_pseudo_us.py` frontmatter marker."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return False
    return bool(PSEUDO_US_MARKER_RE.search(head))


def derive_user_story_narrative(feat_data: dict, us_name: str) -> str:
    """Compose a 3-line `## User Story` block in French (En tant que / Je veux / Afin de)."""
    # Pick first actor as the persona ; fallback to generic "utilisateur"
    actors = feat_data["actors"]
    if actors:
        first_actor_name, first_actor_desc = actors[0]
        persona = first_actor_name
        if first_actor_desc:
            persona = f"{first_actor_name} ({first_actor_desc})"
    else:
        persona = "utilisateur de la fonctionnalité"

    # Objective is free text — collapse to a single line summary
    objective = feat_data["objective"].replace("\n", " ").strip()
    if not objective:
        objective = f"que la FEAT {us_name} soit complètement implémentée"

    return (
        f"En tant que {persona}\n"
        f"Je veux disposer de l'ensemble des fonctionnalités décrites dans la spec\n"
        f"Afin de : {objective}"
    )


def build_pseudo_us_content(
    feat_number: int,
    feat_basename: str,
    feat_hash_8: str,
    us_name: str,
    feat_data: dict,
) -> str:
    """Render the pseudo-US markdown file."""
    us_id = f"{feat_number}-1"
    us_full_id = f"{feat_number}-1-{us_name}"
    parent_feat = f"{feat_number}-{feat_basename}"
    timestamp = iso_now()

    narrative = derive_user_story_narrative(feat_data, us_name)

    # ACs : verbatim from the FEAT (IDs preserved)
    ac_lines = "\n".join(f"- {ac_id}: {text}" for ac_id, text in feat_data["ac"]) \
        or "- AC-1: (aucune AC déclarée dans la FEAT — réviser la FEAT avant d'implémenter)"

    # Covers : every ID from the FEAT (SFD + BR + AC + FD)
    covers_ids: list[str] = []
    covers_ids.extend(s_id for s_id, _ in feat_data["sfd"])
    covers_ids.extend(b_id for b_id, _ in feat_data["br"])
    covers_ids.extend(a_id for a_id, _ in feat_data["ac"])
    covers_ids.extend(f_id for f_id, _ in feat_data["fd"])
    covers_lines = "\n".join(f"- {cid}" for cid in covers_ids) or "- NONE"

    counters = {
        "sfd": len(feat_data["sfd"]),
        "br": len(feat_data["br"]),
        "ac": len(feat_data["ac"]),
        "fd": len(feat_data["fd"]),
    }
    metadata = {
        "complexity": 10,
        "effort_estimate": "XL",
        "notes": (
            f"POC pseudo-US — aggregates {counters['sfd']} SFD, "
            f"{counters['br']} BR, {counters['ac']} AC, "
            f"{counters['fd']} FD into one implementation unit. "
            "NOT for production granularity."
        ),
        "flags": ["poc-mode"],
    }

    return f"""---
id: {us_id}
name: {us_name}
feat: {parent_feat}
status: Ready
parent-feat-hash: sha256:{feat_hash_8}
generated-by: feat_to_pseudo_us.py
generated-at: {timestamp}
poc-mode: true
---

# US-1: {us_name} (POC pseudo-US)

ID: {us_full_id}
Parent FEAT: {parent_feat}
Parent FEAT hash: sha256:{feat_hash_8}
Status: Ready

> ⚠️ **Pseudo-US POC** — auto-générée par `/sdd-poc` (script
> `feat_to_pseudo_us.py`). Agrège tous les SFD/BR/AC/FD de la FEAT
> parente en une seule unité d'implémentation pour piloter
> dev-backend + dev-frontend sans découpage US.
>
> **NE PAS éditer manuellement.** Pour passer en granularité fine :
> `/us-generate {feat_number} --replace-pseudo` (remplace ce fichier
> par 1-N vraies US), puis `/sdd-full {feat_number}` (pipeline standard).

## User Story

{narrative}

## Acceptance Criteria

{ac_lines}

## Covers

{covers_lines}

## Dependencies

- NONE

## Metadata

```json
{json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True)}
```
"""


def handle_html_mockup(
    root: Path, feat_number: int, feat_basename: str, us_name: str, dry_run: bool
) -> dict:
    """Detect or copy the optional HTML mockup.

    Conventions :
      - canonical : workspace/input/ui/{n}-1-{us_name}.html
      - POC user shortcut : workspace/input/ui/{n}-{feat_basename}.html

    Returns dict {"action": <none|already|copied|none-available>,
                  "src": <path|null>, "dst": <path|null>}.
    """
    ui_dir = root / "workspace" / "input" / "ui"
    if not ui_dir.is_dir():
        return {"action": "none-available", "src": None, "dst": None}

    canonical = ui_dir / f"{feat_number}-1-{us_name}.html"
    shortcut = ui_dir / f"{feat_number}-{feat_basename}.html"

    if canonical.exists():
        return {
            "action": "already",
            "src": str(canonical),
            "dst": str(canonical),
        }

    if shortcut.exists():
        if dry_run:
            return {
                "action": "would-copy",
                "src": str(shortcut),
                "dst": str(canonical),
            }
        try:
            shutil.copyfile(shortcut, canonical)
            return {"action": "copied", "src": str(shortcut), "dst": str(canonical)}
        except OSError as e:
            warn(f"WARN: failed to copy HTML mockup {shortcut} -> {canonical} ({e})")
            return {"action": "copy-failed", "src": str(shortcut), "dst": str(canonical)}

    return {"action": "none-available", "src": None, "dst": None}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert a FEAT into a single POC pseudo-US (used by /sdd-poc).",
    )
    p.add_argument("--feat-number", type=int, required=True, help="FEAT number (e.g. 1)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite even if a non-pseudo US exists for this FEAT",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing files",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON output on stdout",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    result: dict = {
        "feat_number": args.feat_number,
        "action": "unknown",
        "us_path": None,
        "mockup": {},
        "errors": [],
    }

    # 1. Locate FEAT
    feat_path, err = find_feat_file(root, args.feat_number)
    if err == "FEAT_NOT_FOUND":
        error_block(
            f"feat_to_pseudo_us — FEAT {args.feat_number} not found",
            f"[FEAT_NOT_FOUND] no file matching workspace/input/feats/{args.feat_number}-*.md",
            "verify FEAT number (ls workspace/input/feats/) or create one via /feat-generate",
        )
        return FAIL_FAST
    if err == "FEAT_AMBIGUOUS":
        error_block(
            f"feat_to_pseudo_us — FEAT {args.feat_number} ambiguous",
            f"[FEAT_AMBIGUOUS] multiple files match workspace/input/feats/{args.feat_number}-*.md",
            "rename duplicate FEATs so only one matches the number",
        )
        return FAIL_FAST

    assert feat_path is not None
    feat_basename = feat_path.stem.split("-", 1)[1] if "-" in feat_path.stem else feat_path.stem
    us_name = feat_name_to_us_name(feat_basename)
    feat_hash_8 = compute_feat_hash_8(feat_path)

    result["feat_path"] = str(feat_path.relative_to(root))
    result["feat_basename"] = feat_basename
    result["us_name"] = us_name
    result["feat_hash_8"] = feat_hash_8

    # 2. Check existing US files for this FEAT
    existing = existing_us_files(root, args.feat_number)
    target_path = root / "workspace" / "output" / "us" / f"{args.feat_number}-1-{us_name}.md"

    if existing:
        pseudo_match = [p for p in existing if is_pseudo_us(p)]
        non_pseudo = [p for p in existing if p not in pseudo_match]

        if non_pseudo and not args.force:
            paths_list = ", ".join(p.name for p in non_pseudo)
            error_block(
                f"feat_to_pseudo_us — real US already exists for FEAT {args.feat_number}",
                f"[US_ALREADY_EXISTS] {paths_list} — looks like /us-generate has run",
                "use --force to overwrite (will conflict with /us-generate output) OR delete the US files first",
            )
            return FAIL_FAST

        if pseudo_match and len(pseudo_match) == 1 and pseudo_match[0] == target_path:
            # Idempotent check — if content would not change, return early
            try:
                current = target_path.read_text(encoding="utf-8")
                if f"sha256:{feat_hash_8}" in current:
                    result["action"] = "already-up-to-date"
                    result["us_path"] = str(target_path.relative_to(root))
                    result["mockup"] = handle_html_mockup(
                        root, args.feat_number, feat_basename, us_name, args.dry_run
                    )
                    _emit_result(result, args.json)
                    return SUCCESS
            except OSError:
                pass  # fall through to re-write

    # 3. Read FEAT content + extract data
    try:
        feat_content = feat_path.read_text(encoding="utf-8")
    except OSError as e:
        error_block(
            f"feat_to_pseudo_us — cannot read {feat_path}",
            f"[INFRA_BLOCKED] {e}",
            "check file permissions",
        )
        return INFRA_BLOCKED

    feat_data = extract_feat_data(feat_content)
    if not feat_data["ac"]:
        warn(
            f"WARN: FEAT {feat_path.name} has no AC-N lines — pseudo-US will be "
            "minimal. Tech Lead should review the FEAT before running /sdd-poc."
        )

    # 4. Build pseudo-US content
    content = build_pseudo_us_content(
        args.feat_number, feat_basename, feat_hash_8, us_name, feat_data
    )

    # 5. Write (atomic) unless dry-run
    if args.dry_run:
        result["action"] = "would-write"
        result["us_path"] = str(target_path.relative_to(root))
        result["preview_length_bytes"] = len(content.encode("utf-8"))
    else:
        try:
            atomic_write_text(target_path, content)
        except OSError as e:
            error_block(
                f"feat_to_pseudo_us — cannot write {target_path}",
                f"[INFRA_BLOCKED] {e}",
                "check parent directory permissions and free disk space",
            )
            return INFRA_BLOCKED
        result["action"] = "written"
        result["us_path"] = str(target_path.relative_to(root))

    # 6. Handle optional HTML mockup
    result["mockup"] = handle_html_mockup(
        root, args.feat_number, feat_basename, us_name, args.dry_run
    )

    _emit_result(result, args.json)
    return SUCCESS


def _emit_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    action = result["action"]
    us_path = result.get("us_path") or "<unknown>"
    mockup = result.get("mockup", {})
    if action == "written":
        print(f"[OK] pseudo-US written : {us_path}")
    elif action == "would-write":
        bytes_ = result.get("preview_length_bytes", 0)
        print(f"[DRY-RUN] would write {bytes_} bytes -> {us_path}")
    elif action == "already-up-to-date":
        print(f"[SKIP] pseudo-US already up-to-date : {us_path}")
    else:
        print(f"[INFO] action={action} us_path={us_path}")

    if mockup:
        m_action = mockup.get("action")
        if m_action == "copied":
            print(f"[OK] HTML mockup copied : {mockup['src']} -> {mockup['dst']}")
        elif m_action == "would-copy":
            print(f"[DRY-RUN] would copy HTML mockup : {mockup['src']} -> {mockup['dst']}")
        elif m_action == "already":
            print(f"[SKIP] HTML mockup already in place : {mockup['dst']}")
        elif m_action == "copy-failed":
            print(f"[WARN] HTML mockup copy failed : {mockup['src']} -> {mockup['dst']}")
        elif m_action == "none-available":
            print("[INFO] no HTML mockup detected (optional — dev-frontend can run without)")


if __name__ == "__main__":
    sys.exit(main())
