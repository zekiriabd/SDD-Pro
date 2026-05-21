#!/usr/bin/env python3
"""SDD_Pro SubagentStop hook.

Audits the matrice file-ownership.md §1 after each sub-agent dispatch.
For files modified during the dispatch window, checks the path matches
one of the "Owner" patterns allowed for that agent.

- Detect agent via input JSON (`tool_input.subagent_type`)
- Glob files modified since env $SDD_DISPATCH_START_TS (ISO 8601),
  fallback to last 5 minutes
- Append violations to workspace/output/.sys/.audit/ownership-violations.log
- Silent on chat (minimal-verbosity), Tech Lead consults log post-batch
- Non-blocking (always exit 0)

Migrated from .claude/scripts/audit-file-ownership.ps1 (2026-05-13).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.hook_input import get_subagent_type, read_hook_input  # noqa: E402
from sdd_lib.paths import normalize, repo_root  # noqa: E402
from sdd_lib.stderr import warn  # noqa: E402


# Matrix extracted from file-ownership.md §1 (must stay in sync)
OWNERSHIP_MATRIX: dict[str, list[str]] = {
    "po": [
        r"^workspace/output/us/.+\.md$",
        r"^workspace/output/\.sys/\.context/constitution\.md$",  # append-only §3 §2
    ],
    "arch": [
        r"^workspace/output/src/[^/]+\.sln$",
        r"^workspace/output/src/[^/]+/(\w+\.csproj|package\.json|pyproject\.toml|build\.gradle.*)$",
        r"^workspace/output/src/[^/]+/Entities/.+",
        r"^workspace/output/src/[^/]+/CLAUDE\.md$",
        r"^workspace/output/db/.+",
        r"^workspace/output/\.sys/\.context/(constitution\.md|adrs/.+)$",
    ],
    "dev-backend": [
        r"^workspace/output/src/[^/]+/(Services|Endpoints|DTOs|Mappers|Validators|Controllers)/.+",
        r"^workspace/output/src/[^/]+/Program\.cs$",
        r"^workspace/output/src/[^/]+/Models/.+",
        r"^workspace/output/plans/.+\.back\.md$",
        r"^workspace/output/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "dev-frontend": [
        r"^workspace/output/src/[^/]+/(Pages|Components|Layouts|Auth)/.+",
        r"^workspace/output/src/[^/]+/wwwroot/.+",
        r"^workspace/output/src/[^/]+/Program\.cs$",
        r"^.+\.razor\.css$",
        r"^workspace/output/plans/.+\.front\.md$",
        r"^workspace/output/\.sys/\.context/adrs/ADR-.+\.md$",
    ],
    "qa": [
        r"^workspace/output/src/.+\.Tests/.+",
        r"^workspace/output/src/.+/__tests__/.+",
        r"^workspace/output/src/.+\.(FEAT|test)\.(ts|tsx|js|jsx)$",
        r"^workspace/output/src/.+(Test|FEAT)\.kt$",
        r"^workspace/output/src/.+test_.+\.py$",
        r"^workspace/output/qa/feat-.+/(report\.md|coverage\.json|quality\.json|api-tests\.(json|md))$",
    ],
    # `dashboard` retiré v7.0.0 (governance-major-auditors-trim) — remplacé par
    # script déterministe index_adrs.py. Aucune entrée matrice nécessaire.
    "elicitor": [
        r"^workspace/input/feats/.+\.md$",  # append-only
        r"^workspace/output/\.sys/\.context/constitution\.md$",  # append-only §7
    ],
}

# Paths to ignore during ownership audit
IGNORE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.sys/\.audit/"),
    re.compile(r"\.sys/\.state/"),
    re.compile(r"\.tmp$"),
)


def _parse_cutoff() -> datetime:
    """Return cutoff datetime: env $SDD_DISPATCH_START_TS, marker file, or now-5min.

    v7.0.1 : delegated resolution to sdd_lib/run_id helper which scopes the
    cutoff to the current run's start (run_id marker mtime) when the env
    var is not explicitly set. Final fallback remains now-5min for safety.
    """
    raw = os.environ.get("SDD_DISPATCH_START_TS", "").strip()
    if not raw:
        try:
            from sdd_lib.run_id import get_or_create_dispatch_start_ts
            raw = get_or_create_dispatch_start_ts()
        except Exception:
            return datetime.now(timezone.utc) - timedelta(minutes=5)
    # Accept ISO 8601 with optional 'Z' suffix
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc) - timedelta(minutes=5)


def _iter_modified_files(workspace: Path, cutoff: datetime) -> list[Path]:
    """Walk workspace/ and yield files modified after cutoff."""
    cutoff_ts = cutoff.timestamp()
    out: list[Path] = []
    for path in workspace.rglob("*"):
        try:
            if not path.is_file():
                continue
            if path.stat().st_mtime > cutoff_ts:
                out.append(path)
        except OSError:
            continue
    return out


def main() -> int:
    payload = read_hook_input()
    subagent = get_subagent_type(payload)
    if not subagent or subagent not in OWNERSHIP_MATRIX:
        return 0

    allowed = [re.compile(p) for p in OWNERSHIP_MATRIX[subagent]]

    root = repo_root()
    workspace = root / "workspace"
    if not workspace.is_dir():
        return 0

    cutoff = _parse_cutoff()
    modified = _iter_modified_files(workspace, cutoff)
    if not modified:
        return 0

    violations: list[str] = []
    for f in modified:
        try:
            rel = normalize(f.relative_to(root))
        except ValueError:
            continue

        if any(ign.search(rel) for ign in IGNORE_PATTERNS):
            continue

        if not any(pat.match(rel) for pat in allowed):
            violations.append(rel)

    if not violations:
        return 0

    audit_dir = root / "workspace" / "output" / ".sys" / ".audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_file = audit_dir / "ownership-violations.log"

    timestamp = datetime.now(timezone.utc).isoformat()
    with log_file.open("a", encoding="utf-8") as fh:
        for v in violations:
            fh.write(
                f"{timestamp} [FILE_OWNERSHIP] {subagent} wrote {v} "
                f"(pattern hors matrice ownership.md §1)\n"
            )

    # v7.0.0 audit hardening 2026-05-20 — mode resolution :
    #   - $SDD_AUDIT_OWNERSHIP_MODE = warn|strict|off
    #   - default : 'strict' in CI (any CI env var), 'warn' otherwise
    # strict mode emits visible WARN + exit 0 (still non-blocking : we
    # don't want to fail a SubagentStop event that completed successfully).
    # The strict-vs-warn difference is in stderr verbosity — CI logs surface
    # the violation count immediately, interactive accumulates silently.
    mode = (os.environ.get("SDD_AUDIT_OWNERSHIP_MODE") or "").strip().lower()
    if mode not in ("warn", "strict", "off"):
        ci = any(
            (os.environ.get(v, "").strip().lower() not in ("", "0", "false", "no"))
            for v in (
                "CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI",
                "JENKINS_URL", "BUILDKITE", "TRAVIS", "TF_BUILD",
                "BITBUCKET_BUILD_NUMBER",
            )
        )
        mode = "strict" if ci else "warn"

    if mode != "off":
        msg_level = "ERROR" if mode == "strict" else "WARN"
        warn(
            f"{msg_level} audit-file-ownership : {subagent} a viole la matrice "
            f"ownership.md §1 ({len(violations)} fichier(s) hors perimetre) — "
            f"voir {log_file.relative_to(root).as_posix()}"
        )
        if mode == "strict":
            warn(f"CAUSE: [FILE_OWNERSHIP] cf. log ci-dessus pour la liste")
            warn(f"FIX: (a) corriger le prompt agent ou la matrice ownership.md")
            warn(f"     (b) bypass interactif : export SDD_AUDIT_OWNERSHIP_MODE=warn")

    return 0


if __name__ == "__main__":
    sys.exit(main())
