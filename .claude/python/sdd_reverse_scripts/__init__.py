"""SDD_Pro Reverse Engineering — CLI scripts (orchestrators).

CLI entry points that wrap the sdd_reverse/ library modules:
- reverse_inventory.py  : Phase 1 (scan + build inventory + detect units)
- reverse_audit.py      : Phase 2 (tech audit, V2)
- reverse_status.py     : diagnostic

Anti-derive: no imports from sdd_lib/, sdd_scripts/, sdd_admin/, sdd_hooks/.
Pure isolation from the main SDD_Pro framework.
"""

__version__ = "0.1.0-mvp"
