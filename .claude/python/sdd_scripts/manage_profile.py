#!/usr/bin/env python3
"""SDD_Pro profile manager — export/import/list/delete team config profiles.

Profiles are saved snapshots of `~/.sdd/config.team.yml`. Useful for orgs
maintaining multiple policy presets (strict-prod, dev-only, security-hardened, ...).

Profile storage:
    ~/.sdd/profiles/{name}.yml     (or %USERPROFILE%/.sdd/profiles/ on Windows)

Honors env var $SDD_PROFILES_DIR override for tests.

Subcommands:
    export <name>           Save current ~/.sdd/config.team.yml as profile <name>
    import <name>           Load profile <name> as current team.yml
    list                    List all profiles + active team.yml (if any)
    delete <name>           Remove profile <name>
    show <name>             Print profile <name> content

Exit codes:
    0 : success
    1 : I/O error (file not found, permission denied, etc.)
    2 : misuse (invalid args, profile already exists for export without --force)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.exit_codes import CORRECTIBLE, FAIL_FAST, SUCCESS  # noqa: E402

import argparse
import os
import re
import shutil
import sys
from pathlib import Path


VALID_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$")


def profiles_dir() -> Path:
    """Default: ~/.sdd/profiles/. Overridable via $SDD_PROFILES_DIR."""
    override = os.environ.get("SDD_PROFILES_DIR")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~")) / ".sdd" / "profiles"


def team_config_path() -> Path:
    """Default: ~/.sdd/config.team.yml. Overridable via $SDD_TEAM_CONFIG."""
    override = os.environ.get("SDD_TEAM_CONFIG")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~")) / ".sdd" / "config.team.yml"


def validate_profile_name(name: str) -> None:
    if not VALID_PROFILE_NAME_RE.match(name):
        raise ValueError(
            f"invalid profile name '{name}' (must match [A-Za-z0-9_][A-Za-z0-9_.-]{{0,63}})"
        )


def cmd_export(name: str, *, force: bool = False) -> int:
    validate_profile_name(name)
    src = team_config_path()
    if not src.is_file():
        sys.stderr.write(
            f"ERROR: cannot export — team config absent\n"
            f"CAUSE: [PROFILE_NO_TEAM_CONFIG] {src} not found\n"
            f"FIX: create ~/.sdd/config.team.yml first (or set $SDD_TEAM_CONFIG)\n"
        )
        return FAIL_FAST
    dst_dir = profiles_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{name}.yml"
    if dst.exists() and not force:
        sys.stderr.write(
            f"ERROR: profile '{name}' already exists\n"
            f"CAUSE: [PROFILE_EXISTS] {dst}\n"
            f"FIX: use --force to overwrite, or pick another name\n"
        )
        return CORRECTIBLE
    shutil.copy2(src, dst)
    sys.stdout.write(f"✓ profile '{name}' exported → {dst}\n")
    return SUCCESS
def cmd_import(name: str, *, force: bool = False) -> int:
    validate_profile_name(name)
    src = profiles_dir() / f"{name}.yml"
    if not src.is_file():
        sys.stderr.write(
            f"ERROR: profile '{name}' not found\n"
            f"CAUSE: [PROFILE_NOT_FOUND] {src}\n"
            f"FIX: check available profiles via 'manage_profile.py list'\n"
        )
        return FAIL_FAST
    dst = team_config_path()
    if dst.exists() and not force:
        # Backup before overwrite
        backup = dst.with_suffix(dst.suffix + ".bak")
        shutil.copy2(dst, backup)
        sys.stdout.write(f"  ↻ existing team config backed up → {backup}\n")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    sys.stdout.write(f"✓ profile '{name}' loaded → {dst}\n")
    sys.stdout.write(
        "  Note: re-run /sdd-full or any SDD command to apply the new layered config.\n"
    )
    return SUCCESS
def cmd_list() -> int:
    pd = profiles_dir()
    active = team_config_path()
    if not pd.is_dir():
        sys.stdout.write(f"No profiles dir at {pd}\n")
    else:
        profiles = sorted(p.stem for p in pd.glob("*.yml"))
        if not profiles:
            sys.stdout.write(f"No profiles found in {pd}\n")
        else:
            sys.stdout.write(f"Profiles in {pd}:\n")
            for p in profiles:
                sys.stdout.write(f"  - {p}\n")

    if active.is_file():
        sys.stdout.write(f"\nActive team config: {active}\n")
    else:
        sys.stdout.write(f"\nNo active team config (looked at {active})\n")
    return SUCCESS
def cmd_delete(name: str) -> int:
    validate_profile_name(name)
    path = profiles_dir() / f"{name}.yml"
    if not path.is_file():
        sys.stderr.write(
            f"ERROR: profile '{name}' not found\n"
            f"CAUSE: [PROFILE_NOT_FOUND] {path}\n"
            f"FIX: check available profiles via 'manage_profile.py list'\n"
        )
        return FAIL_FAST
    path.unlink()
    sys.stdout.write(f"✓ profile '{name}' deleted\n")
    return SUCCESS
def cmd_show(name: str) -> int:
    validate_profile_name(name)
    path = profiles_dir() / f"{name}.yml"
    if not path.is_file():
        sys.stderr.write(
            f"ERROR: profile '{name}' not found\n"
            f"CAUSE: [PROFILE_NOT_FOUND] {path}\n"
            f"FIX: check available profiles via 'manage_profile.py list'\n"
        )
        return FAIL_FAST
    sys.stdout.write(path.read_text(encoding="utf-8"))
    if not sys.stdout.isatty():
        return SUCCESS
    sys.stdout.write("\n")
    return SUCCESS
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manage_profile",
        description="SDD_Pro profile manager (team.yml snapshots)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="Save current team.yml as profile")
    p_exp.add_argument("name")
    p_exp.add_argument("--force", action="store_true", help="overwrite existing profile")

    p_imp = sub.add_parser("import", help="Load profile as team.yml")
    p_imp.add_argument("name")
    p_imp.add_argument("--force", action="store_true", help="skip backup of existing team.yml")

    sub.add_parser("list", help="List profiles + active team config")

    p_del = sub.add_parser("delete", help="Remove a profile")
    p_del.add_argument("name")

    p_show = sub.add_parser("show", help="Print profile content")
    p_show.add_argument("name")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "export":
            return cmd_export(args.name, force=args.force)
        if args.cmd == "import":
            return cmd_import(args.name, force=args.force)
        if args.cmd == "list":
            return cmd_list()
        if args.cmd == "delete":
            return cmd_delete(args.name)
        if args.cmd == "show":
            return cmd_show(args.name)
    except ValueError as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return CORRECTIBLE
    except OSError as e:
        sys.stderr.write(f"ERROR: I/O failure: {e}\n")
        return FAIL_FAST
    return CORRECTIBLE
if __name__ == "__main__":
    sys.exit(main())
