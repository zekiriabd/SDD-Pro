#!/usr/bin/env python3
"""SDD_Pro SubagentStop hook (matcher=po) — defense-in-depth sentinel resolver.

Audit P0-workflow 2026-06-05.

The agent `po` writes US files with the literal sentinel
`Parent FEAT hash: sha256:COMPUTE_REQUIRED` because it lacks the `Bash` tool
and cannot compute a sha256 itself. Historically, the sentinel was resolved
ONLY by the orchestrating command `/us-generate` at its STEP 3.0 (post-step
inline python).

Bug: if `po` is invoked OUTSIDE `/us-generate` — e.g.:
  - direct `Agent: po` from a debug session
  - custom orchestrator script
  - re-invocation by a higher-level tool that bypasses /us-generate
…then the sentinel persists in US files. All downstream agents (dev-*,
auditors, /feat-validate, /sdd-review) then see `sha256:COMPUTE_REQUIRED`,
fail to parse 8 hex chars, and emit `[FEAT_HASH_MISMATCH]`.

This hook closes that gap: it ALWAYS runs when the `po` agent stops,
regardless of the invocation path. It calls the shared script
`sdd_scripts/resolve_us_hash_sentinel.py` in `--auto-detect` mode, which
scans all US files containing the sentinel, infers their FEAT number from
the filename, and patches with the real hash.

Idempotent: if the sentinel was already resolved (normal `/us-generate`
path), this hook does nothing.

Exit codes:
  0 = ALLOW (sentinel resolved OR nothing to do)
  0 = ALLOW (resolver script reports issues — non-blocking, just log warning)

Non-blocking by design: the hook is a safety net, not a gatekeeper. A real
resolution failure (FEAT file genuinely missing) is logged but does not
block the agent termination — the failure will surface downstream with a
clearer error class.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sdd_lib.exit_codes import HOOK_ALLOW  # noqa: E402
from sdd_lib.paths import project_root_for_hook as _resolve_project_root


def main() -> int:
    # Drain stdin to avoid back-pressure on Claude Code's pipe (we don't
    # use the payload — auto-detect mode discovers FEATs by FS scan).
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass

    root = _resolve_project_root()
    script = root / ".claude" / "python" / "sdd_scripts" / "resolve_us_hash_sentinel.py"
    if not script.is_file():
        sys.stderr.write(
            "[resolve-po-hash] WARN: resolve_us_hash_sentinel.py missing — "
            "po sentinel will not be auto-resolved (orchestrator path only).\n"
        )
        return HOOK_ALLOW

    try:
        result = subprocess.run(
            [sys.executable, str(script), "--auto-detect", "--quiet"],
            capture_output=True,
            text=True,
            timeout=10,  # very generous: typical run is < 100ms even for 50 US files
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        sys.stderr.write(f"[resolve-po-hash] WARN: resolver invocation failed: {e}\n")
        return HOOK_ALLOW

    if result.returncode != 0:
        # Non-blocking: log the stderr from the script (already has [CLASS] prefix)
        # but ALLOW the agent termination. Downstream agents will produce a
        # clearer error if the unresolved sentinel actually breaks them.
        tail = (result.stderr or "")[-500:]
        sys.stderr.write(f"[resolve-po-hash] WARN: resolver exit {result.returncode}\n{tail}\n")

    return HOOK_ALLOW


if __name__ == "__main__":
    sys.exit(main())
