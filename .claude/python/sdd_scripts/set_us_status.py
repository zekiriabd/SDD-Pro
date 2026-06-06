#!/usr/bin/env python3
"""SDD_Pro: set User Story Status with transition validation (v6.8+).

Updates the `Status: {value}` line of workspace/output/us/{n}-{m}-*.md
after validating that the requested transition is allowed.

Usage:
    python set_us_status.py --us 1-2 --status InProgress
    python set_us_status.py --us 1-2 --status Done [--force]
    python set_us_status.py --us 1-2 --get
    python set_us_status.py --list-statuses

Valid statuses (7):
    Draft        Initial state (after /us-generate)
    Ready        Plan generated, ready to materialize (after /dev-plan or /feat-validate GO)
    InProgress   dev-backend or dev-frontend running
    Review       Code generated, awaiting QA / code-review verdict
    Done         All gates passed (terminal happy path)
    Deferred     Postponed (resumable to Ready)
    Cancelled    Abandoned (terminal)

Legacy compatibility:
    `Status: Draft` and `Status: Done` from v6.7- continue to work identically.

Valid transitions:
    Draft       -> Ready, Deferred, Cancelled
    Ready       -> InProgress, Draft (back), Deferred, Cancelled
    InProgress  -> Review, Ready (back), Done, Deferred, Cancelled
    Review      -> Done, InProgress (back), Deferred, Cancelled
    Done        -> InProgress (rework, --force required)
    Deferred    -> Ready, Cancelled
    Cancelled   -> (terminal, --force to reopen)

Same-status (idempotent): exit 0, no-op.

Exit codes (legacy granular convention — preserved by design, see sdd_lib/exit_codes.py docstring §"Cas hors convention"):
    0  Success (status set, or already at target, or --get/--list-statuses) — = SUCCESS
    1  US file not found ([US_NOT_FOUND]) — = FAIL_FAST
    2  Status value invalid ([US_STATUS_INVALID]) — distinct from FAIL_FAST for [CLASS] granularity
    3  Transition invalid ([US_STATUS_TRANSITION_INVALID]) — distinct from INFRA_BLOCKED for [CLASS] granularity
    4  US parse error — no `Status:` line ([US_STATUS_PARSE_ERROR])
    5  I/O error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sdd_lib.paths import repo_root  # noqa: E402
from sdd_lib.stderr import error_block, warn  # noqa: E402
from sdd_lib.atomic_write import atomic_write_text  # noqa: E402


VALID_STATUSES: tuple[str, ...] = (
    "Draft",
    "Ready",
    "InProgress",
    "Review",
    "Done",
    "Deferred",
    "Cancelled",
)

# Transition graph : key -> set of allowed next statuses.
# Same-status transition is always allowed (idempotent no-op handled separately).
TRANSITIONS: dict[str, frozenset[str]] = {
    "Draft": frozenset({"Ready", "Deferred", "Cancelled"}),
    "Ready": frozenset({"InProgress", "Draft", "Deferred", "Cancelled"}),
    "InProgress": frozenset({"Review", "Ready", "Done", "Deferred", "Cancelled"}),
    "Review": frozenset({"Done", "InProgress", "Deferred", "Cancelled"}),
    "Done": frozenset({"InProgress"}),  # rework (warn but allowed without force on the forward chain)
    "Deferred": frozenset({"Ready", "Cancelled"}),
    "Cancelled": frozenset(),  # terminal, --force required
}

# Statuses that require --force to LEAVE (terminal states reopen).
TERMINAL_REOPEN_FORCED: frozenset[str] = frozenset({"Done", "Cancelled"})

US_ID_RE = re.compile(r"^\d+-\d+$")
STATUS_LINE_RE = re.compile(r"(?m)^Status:[ \t]*([A-Za-z]+)[ \t]*$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Set or read User Story Status (v6.8+).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--us",
        help="US short id, e.g. '1-2' (will be matched against workspace/output/us/1-2-*.md)",
    )
    p.add_argument(
        "--status",
        choices=VALID_STATUSES,
        help="Target status (one of: " + ", ".join(VALID_STATUSES) + ")",
    )
    p.add_argument(
        "--get",
        action="store_true",
        help="Print current Status: of --us and exit (no write)",
    )
    p.add_argument(
        "--list-statuses",
        action="store_true",
        help="Print valid statuses (one per line) and exit",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Bypass transition validation (use for legacy migration or terminal reopen)",
    )
    return p.parse_args()


def resolve_us_path(us_id: str) -> Path | None:
    """Resolve workspace/output/us/{us_id}-*.md from short id.

    Returns the matched path, or None if absent / ambiguous.
    """
    if not US_ID_RE.match(us_id):
        return None
    us_dir = repo_root() / "workspace" / "output" / "us"
    matches = sorted(us_dir.glob(f"{us_id}-*.md"))
    if len(matches) != 1:
        return None
    return matches[0]


def read_current_status(content: str) -> str | None:
    m = STATUS_LINE_RE.search(content)
    return m.group(1) if m else None


def is_transition_allowed(current: str, target: str, *, force: bool) -> tuple[bool, str]:
    """Return (allowed, reason_if_blocked)."""
    if force:
        return True, ""
    if current == target:
        return True, ""  # idempotent
    if current not in TRANSITIONS:
        # Unknown legacy status — allow only Ready/InProgress forward, else need force.
        return False, f"current status {current!r} not in v6.8 graph (use --force)"
    allowed = TRANSITIONS[current]
    if target in allowed:
        return True, ""
    return False, (
        f"{current} -> {target} not allowed "
        f"(allowed from {current}: {sorted(allowed) or 'none — terminal'})"
    )


def write_status_atomic(path: Path, new_content: str) -> None:
    """Atomic write via sdd_lib.atomic_write_text (cf. build-and-loop.md §2.bis)."""
    atomic_write_text(path, new_content, newline="\n")


def main() -> int:
    args = parse_args()

    if args.list_statuses:
        for s in VALID_STATUSES:
            print(s)
        return 0

    if not args.us:
        error_block(
            "set_us_status — missing --us",
            "[INVALID_ARG] either --list-statuses or --us must be provided",
            "set_us_status.py --us 1-2 --status InProgress",
        )
        return 2

    us_path = resolve_us_path(args.us)
    if us_path is None:
        error_block(
            f"set_us_status — US {args.us} not found",
            f"[US_NOT_FOUND] no unique match for workspace/output/us/{args.us}-*.md",
            "verify --us format ({n}-{m}) and that /us-generate has run",
        )
        return 1

    try:
        content = us_path.read_text(encoding="utf-8")
    except OSError as e:
        error_block(
            f"set_us_status — read failed: {us_path}",
            f"[IO] {e}",
            "check file permissions",
        )
        return 5

    current = read_current_status(content)
    if current is None:
        error_block(
            f"set_us_status — no Status: line in {us_path.name}",
            "[US_STATUS_PARSE_ERROR] expected `Status: {value}` near top of US",
            "regenerate US via /us-generate or add Status: Draft manually",
        )
        return 4

    if args.get:
        print(current)
        return 0

    if args.status is None:
        error_block(
            "set_us_status — missing --status",
            "[INVALID_ARG] --status required when not using --get / --list-statuses",
            "set_us_status.py --us 1-2 --status InProgress",
        )
        return 2

    target = args.status

    # Idempotent same-status no-op.
    if current == target:
        print(f"[OK] {us_path.name}: Status already {target} (no-op)")
        return 0

    # Special-case terminal reopen without --force.
    if current in TERMINAL_REOPEN_FORCED and not args.force:
        if not (current == "Done" and target == "InProgress"):
            error_block(
                f"set_us_status — {args.us} terminal state ({current})",
                f"[US_STATUS_TRANSITION_INVALID] leaving {current} requires --force",
                f"set_us_status.py --us {args.us} --status {target} --force",
            )
            return 3

    allowed, reason = is_transition_allowed(current, target, force=args.force)
    if not allowed:
        error_block(
            f"set_us_status — {args.us} transition rejected",
            f"[US_STATUS_TRANSITION_INVALID] {reason}",
            f"either choose a valid next state OR use --force (set_us_status.py --us {args.us} --status {target} --force)",
        )
        return 3

    new_content, n_subs = STATUS_LINE_RE.subn(f"Status: {target}", content, count=1)
    if n_subs != 1:
        error_block(
            f"set_us_status — failed to substitute Status: line in {us_path.name}",
            "[US_STATUS_PARSE_ERROR] regex matched read but not write — file mutated between read/write?",
            "rerun (race) or inspect the US file manually",
        )
        return 4

    try:
        write_status_atomic(us_path, new_content)
    except OSError as e:
        error_block(
            f"set_us_status — write failed: {us_path}",
            f"[IO] {e}",
            "check file permissions / free disk space",
        )
        return 5

    if args.force and not is_transition_allowed(current, target, force=False)[0]:
        warn(f"[WARN] forced transition {current} -> {target} on {us_path.name}")
    print(f"[OK] {us_path.name}: Status {current} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
