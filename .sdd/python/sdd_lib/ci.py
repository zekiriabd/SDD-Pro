"""SSoT CI environment detection (audit CTO 2026-06-07).

Pre-fix, four hooks (`preflight_agent_budget`, `preflight_cost_cap`,
`protect_framework`, `validate_acceptance_gate`) each rolled their own
`_detect_ci()` with the same 9-env-var list. Adding a new CI provider
(Azure DevOps `TF_BUILD` was missed initially) required PRing 4 files.

This module is the single source of truth. The 4 hooks delegate via
``from sdd_lib.ci import is_ci`` instead of duplicating the list.
"""
from __future__ import annotations

import os

#: Common CI env vars set to non-empty / non-falsy values when running under CI.
#: Source : projects observed in the wild + GitHub's `is_ci` runner-detection
#: lookups. New providers should be APPENDED HERE (not duplicated in hooks).
CI_SIGNALS: tuple[str, ...] = (
    "CI",                       # generic, most CIs set this
    "GITHUB_ACTIONS",           # GitHub Actions
    "GITLAB_CI",                # GitLab CI
    "CIRCLECI",                 # CircleCI
    "JENKINS_URL",              # Jenkins
    "BUILDKITE",                # Buildkite
    "TRAVIS",                   # Travis CI (legacy)
    "TF_BUILD",                 # Azure DevOps (added 2026-06-06)
    "BITBUCKET_BUILD_NUMBER",   # Bitbucket Pipelines
)

#: Values that look "set" but actually mean disabled (treated as not-CI).
_FALSY = ("", "0", "false", "no")


def is_ci() -> bool:
    """Return True if any known CI env var is set to a non-falsy value.

    Best-effort detection — false negatives possible if a provider is not
    listed in `CI_SIGNALS`. Add the new env var there.
    """
    for var in CI_SIGNALS:
        v = os.environ.get(var, "").strip().lower()
        if v and v not in _FALSY:
            return True
    return False
