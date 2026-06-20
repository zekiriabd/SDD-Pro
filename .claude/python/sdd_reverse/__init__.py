"""SDD_Pro Reverse Engineering — Python library module.

Workflow reverse engineering pour SDD_Pro v7.0.0+. Isole legacy code analysis
des modules existants (sdd_lib/, sdd_scripts/, sdd_admin/, sdd_hooks/).

Modules:
- scan_legacy        : detection langage/framework via language_signatures.yml
- inventory_builder  : modules, pages, LOC, entry points, exclusions
- ui_unit_detector   : pre-detection unites fonctionnelles (GridView, FormView, Menu, ...)

Voir .claude/docs/reverse-engineering-workflow.md pour la spec complete.

Anti-derive: aucun import depuis sdd_lib/, sdd_scripts/, sdd_admin/, sdd_hooks/
(isolation stricte, cf. .claude/docs/reverse-engineering-master-prompt.md SS3.1).
"""

__version__ = "0.1.0-mvp"
