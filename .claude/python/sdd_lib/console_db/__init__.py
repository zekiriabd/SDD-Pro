"""SDD_Pro Console DB — helper sub-package for SQLite access (v7.0.0-alpha CRIT-12).

Source de vérité unique pour télémétrie/QA/runs.
Localisation par défaut : workspace/output/db/console.db

Usage minimal :
    from sdd_lib.console_db import connect, insert_event, upsert_run

    with connect() as conn:
        upsert_run(conn, run_id=..., command=..., feat_n=..., status="running")

Pragmas appliqués automatiquement à la connexion :
    - journal_mode = WAL          → lectures concurrentes pendant écritures
    - synchronous  = NORMAL       → bon compromis durabilité/perf en WAL
    - busy_timeout = 5000 ms      → tolère 5s d'attente sur lock
    - foreign_keys = ON

v7.0.0-alpha (audit CRIT-12, 2026-06-04) — éclatement du monolithe 912 L
en sous-modules thématiques :

    core.py  — connexion + pragmas + migrations + ensure_feat_row/ensure_us_row + _jdumps
    runs.py  — runs / phases / events / gates / auditor_runs
    qa.py    — 9 inserts QA + tokens + context_budget + validation_reports

L'API publique reste identique (`from sdd_lib.console_db import X` continue
de fonctionner pour les 26 callers externes), grâce aux re-exports
ci-dessous.
"""
from __future__ import annotations

# v7.0.0-alpha (audit CRIT-12 backward-compat) — re-export `repo_root` and
# `iso_now_ms` at the package top-level. Several existing tests use
# `mock.patch.object(console_db, "repo_root", ...)` ; without this re-export
# they'd raise AttributeError. The actual lookup site for `default_db_path`
# is `sdd_lib.console_db.core.repo_root`, so test mocks should target THAT
# path going forward (the package-level re-export is purely for back-compat
# with tests that pre-date the split).
from sdd_lib.paths import iso_now_ms, repo_root  # noqa: F401  (re-export)

# --- core (connexion, schema, migrations, FEAT/US row helpers) ---
from sdd_lib.console_db.core import (
    AUDITOR_IDS,
    BASE_SCHEMA_VERSION,
    DEFAULT_DB_PATH,
    MIGRATIONS_DIR,
    SCHEMA_SQL_PATH,
    SCHEMA_VERSION,
    _jdumps,
    apply_pending_migrations,
    connect,
    connect_ro,
    current_schema_version,
    default_db_path,
    ensure_feat_row,
    ensure_initialized,
    ensure_us_row,
    load_schema_sql,
)

# --- runs (model d'exécution : runs/phases/events/gates/auditor_runs) ---
from sdd_lib.console_db.runs import (
    auditor_ran,
    get_run,
    get_run_phases,
    insert_event,
    insert_gate,
    list_runs,
    record_auditor_run,
    upsert_run,
    upsert_run_phase,
)

# --- qa (9 inserts QA + telemetry + validation reports) ---
from sdd_lib.console_db.qa import (
    insert_context_budget,
    insert_qa_a11y_batch,
    insert_qa_api_tests,
    insert_qa_code_review_batch,
    insert_qa_coverage,
    insert_qa_performance_batch,
    insert_qa_quality_batch,
    insert_qa_security_batch,
    insert_qa_spec_compliance_batch,
    insert_token_usage,
    insert_validation_report,
    replace_qa_api_tests_for_feat,
    replace_qa_auditor_for_feat,
    replace_qa_coverage_for_feat,
    replace_qa_quality_for_feat,
    replace_validation_reports,
)

__all__ = [
    # core constants
    "AUDITOR_IDS", "BASE_SCHEMA_VERSION", "DEFAULT_DB_PATH",
    "MIGRATIONS_DIR", "SCHEMA_SQL_PATH", "SCHEMA_VERSION",
    # core helpers
    "apply_pending_migrations", "connect", "connect_ro",
    "current_schema_version", "default_db_path", "ensure_feat_row",
    "ensure_initialized", "ensure_us_row", "load_schema_sql",
    # runs
    "auditor_ran", "get_run", "get_run_phases", "insert_event",
    "insert_gate", "list_runs", "record_auditor_run",
    "upsert_run", "upsert_run_phase",
    # qa
    "insert_context_budget", "insert_qa_a11y_batch", "insert_qa_api_tests",
    "insert_qa_code_review_batch", "insert_qa_coverage",
    "insert_qa_performance_batch", "insert_qa_quality_batch",
    "insert_qa_security_batch", "insert_qa_spec_compliance_batch",
    "insert_token_usage", "insert_validation_report",
    "replace_qa_api_tests_for_feat", "replace_qa_auditor_for_feat",
    "replace_qa_coverage_for_feat", "replace_qa_quality_for_feat",
    "replace_validation_reports",
]
