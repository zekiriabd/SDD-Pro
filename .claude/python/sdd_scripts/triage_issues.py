#!/usr/bin/env python3
"""SDD_Pro: deterministic back/front/shared routing for quality issues.

Given a file path under `workspace/output/src/`, classifies it as belonging
to the backend project, frontend project, shared lib, or unknown. Used by
`/sdd-review` to dispatch findings to the right agent (dev-backend vs
dev-frontend) and to compute owner-level summaries in the consolidated
report.

Pure deterministic — 0 LLM, 0 network, ~0 ms per call.

Reads `## Project Config` of `workspace/input/stack/stack.md` to resolve
`AppName` (frontend), `BackendName` (backend), `LibName` (shared, optional).

Usage (CLI, mostly for debug/audit):
    python triage_issues.py --path "workspace/output/src/CMSPrintFront/src/pages/LoginPage.tsx"
    python triage_issues.py --classify-batch issues.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdd_lib.project_config import read_project_config  # noqa: E402
from sdd_lib.exit_codes import FAIL_FAST, SUCCESS  # noqa: E402

Owner = Literal["backend", "frontend", "shared", "unknown"]


@dataclass(frozen=True)
class ProjectNames:
    app_name: str | None       # frontend project name (a.k.a. FrontendName alias)
    backend_name: str | None
    lib_name: str | None       # shared lib (when LibStrategy=shared)


def load_project_names(root: Path | None = None) -> ProjectNames:
    """Resolve project names from stack.md `## Project Config`."""
    cfg = read_project_config(
        root,
        keys=("AppName", "BackendName", "LibName"),
    )
    return ProjectNames(
        app_name=cfg.get("AppName") or None,
        backend_name=cfg.get("BackendName") or None,
        lib_name=cfg.get("LibName") or None,
    )


def _normalize(path: str) -> str:
    """Normalize OS-specific separators and leading repo-root if any."""
    p = path.replace("\\", "/").strip()
    # Strip leading absolute repo prefix if accidentally included.
    marker = "workspace/output/src/"
    idx = p.find(marker)
    if idx > 0:
        p = p[idx:]
    return p


def classify_path(path: str, names: ProjectNames) -> Owner:
    """Classify a file path under workspace/output/src/ as backend/frontend/shared.

    Rules (ordered, first match wins):
    - path startswith `workspace/output/src/{BackendName}/` → backend
    - path startswith `workspace/output/src/{AppName}/`     → frontend
    - path startswith `workspace/output/src/{LibName}/`     → shared
    - any other location under workspace/output/src/        → unknown
    """
    p = _normalize(path)
    if not p.startswith("workspace/output/src/"):
        return "unknown"

    tail = p[len("workspace/output/src/"):]
    head = tail.split("/", 1)[0] if "/" in tail else tail

    if names.backend_name and head == names.backend_name:
        return "backend"
    if names.app_name and head == names.app_name:
        return "frontend"
    if names.lib_name and head == names.lib_name:
        return "shared"
    return "unknown"


def classify_batch(
    issues: list[dict],
    names: ProjectNames,
    path_key: str = "file_path",
) -> dict[str, list[dict]]:
    """Group a list of issue dicts by owner (backend|frontend|shared|unknown).

    Each issue dict must expose `path_key` (default 'file_path').
    Returns a dict with 4 keys, each mapping to the list of issues.
    """
    buckets: dict[str, list[dict]] = {
        "backend": [],
        "frontend": [],
        "shared": [],
        "unknown": [],
    }
    for issue in issues:
        fp = issue.get(path_key) or ""
        owner = classify_path(fp, names) if fp else "unknown"
        buckets[owner].append(issue)
    return buckets


def summarize_buckets(buckets: dict[str, list[dict]]) -> dict[str, int]:
    """Count issues per owner, return {owner: count}."""
    return {owner: len(items) for owner, items in buckets.items()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_single(path: str) -> int:
    names = load_project_names()
    owner = classify_path(path, names)
    print(json.dumps({"path": path, "owner": owner, "names": {
        "app_name": names.app_name,
        "backend_name": names.backend_name,
        "lib_name": names.lib_name,
    }}, indent=2))
    return SUCCESS
def _cli_batch(input_path: str) -> int:
    names = load_project_names()
    issues = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if not isinstance(issues, list):
        print("ERROR: input must be a JSON array of issue objects", file=sys.stderr)
        return FAIL_FAST
    buckets = classify_batch(issues, names)
    summary = summarize_buckets(buckets)
    print(json.dumps({"summary": summary, "buckets": buckets}, indent=2))
    return SUCCESS
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--path", help="single path to classify")
    g.add_argument("--classify-batch", help="path to a JSON array of issues")
    args = p.parse_args(argv)

    if args.path:
        return _cli_single(args.path)
    return _cli_batch(args.classify_batch)


if __name__ == "__main__":
    sys.exit(main())
