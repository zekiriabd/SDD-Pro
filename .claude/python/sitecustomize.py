"""Site-wide hook to enable coverage tracking in subprocesses.

Activated only when env var COVERAGE_PROCESS_START is set. Several
test files invoke sdd_scripts/* via subprocess.run([...python, script])
rather than direct import; without this hook those subprocess calls
don't contribute to pytest-cov totals.

Reference: https://coverage.readthedocs.io/en/latest/subprocess.html
"""
import os

if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage  # type: ignore[import-not-found]
        coverage.process_startup()
    except ImportError:
        # coverage not installed -> noop, framework still works.
        pass
