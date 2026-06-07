"""SDD_Pro shared helpers for hooks and scripts.

Pure Python 3.10+ stdlib, no external dependencies.

Version policy (audit CTO 2026-06-07) :
    Python package version is lock-stepped with the framework DSL version.
    The two surfaces share the same major.minor digits ; only the "alpha"
    suffix is encoded differently (PEP 440 `aN` vs human-readable `-alpha`).

    Surfaces :
      - this `__version__`     = PEP 440 canonical (e.g. "7.0.0a0")
      - `__framework_version__` = human-readable mirror (e.g. "7.0.0-alpha")
      - pyproject.toml `version` = same as `__version__`
      - loader.yml `version`     = same as `__framework_version__`

    Bumping :
      - Any framework bump (DSL surface change) MUST bump both. Tested
        in `tests/test_version_alignment.py`.
"""

#: PEP 440 canonical version of the Python package shipping hooks + scripts.
#: Must equal `pyproject.toml [project] version`.
__version__ = "7.0.0"

#: Human-readable framework DSL version (mirror of `loader.yml` `version` field).
#: GA tagged 2026-06-07 (cf. CLAUDE.md + VERSIONING.md).
__framework_version__ = "7.0.0"
