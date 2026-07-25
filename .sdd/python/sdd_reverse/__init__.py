"""sdd_reverse — Reverse engineering module for SDD_Pro v7.0.0+.

Isolated module: no imports from sdd_lib, sdd_scripts, sdd_admin, sdd_hooks.
All shared helpers are duplicated locally (file_locks_local, atomic_write_local)
with parity tests against originals.

See .sdd/docs/reverse-engineering-workflow.md (Draft v0.4.1) for the design.
"""

__version__ = "0.1.0-mvp"
