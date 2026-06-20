-- SDD_Pro Console DB — schéma SQLite (current = v1 baseline + migrations 0002..0005)
--
-- Source de vérité unique pour télémétrie/QA/runs.
-- Localisation : workspace/output/db/console.db
-- Pragmas : WAL + synchronous=NORMAL + busy_timeout=5000ms + foreign_keys=ON
--
-- ⚠ STRUCTURE LAYERED (Sprint immédiat 2026-06-07 — clarification audit C3) :
--   1. CE FICHIER = baseline v1 (24 tables core). Appliqué au bootstrap initial.
--   2. MIGRATIONS = `sdd_lib/migrations/000N_*.sql` appliquées séquentiellement
--      pour atteindre l'état courant. Une DB fraîche aujourd'hui contient :
--        - 0002 : table `qa_mutation` (mutation testing)              (déjà inclus baseline)
--        - 0003 : table `qa_e2e`     (Playwright E2E)                 (déjà inclus baseline)
--        - 0004 : table `auditor_runs` (NOT in this file — voir migrations/0004_*.sql)
--        - 0005 : column `qa_api_tests.status` (v7.0.0 canonique 5 statuts)
--   3. Source de vérité runtime = `sdd_lib/console_db/__init__.py`
--      (table `schema_version` + boucle `migrations/000N_*.sql` au open()).
--
-- Si vous ajoutez une nouvelle table/colonne v7+ : **PRÉFÉRER une migration**
-- `000N_*.sql` plutôt que d'éditer ce fichier (préserve backward-compat avec
-- les DBs existantes). Ce fichier reste utile comme :
--   - Documentation lisible humainement de la baseline
--   - Bootstrap rapide pour outils tiers (mais préférer `init_console_db.py`)
--
-- Convention :
--   - timestamps : TEXT ISO-8601 UTC (ex. "2026-05-17T14:32:18Z")
--   - booléens   : INTEGER 0/1
--   - JSON       : TEXT (colonnes suffixées _json)
--   - file paths : TEXT relatifs au repo root, séparateurs /
--
-- Idempotence : tout CREATE est IF NOT EXISTS. La table schema_version
-- pilote les migrations futures (sinon --force-recreate).

-- ============================================================
-- META
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version       INTEGER PRIMARY KEY,
    applied_at    TEXT    NOT NULL
);

-- ============================================================
-- ARTEFACTS SDD (FEAT / US / Plans / ADRs) — métadonnées seulement
-- Le contenu MD reste sur le FS, lu directement par les consommateurs.
-- ============================================================

CREATE TABLE IF NOT EXISTS feats (
    feat_n         INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    file_path      TEXT    NOT NULL,
    status         TEXT,                  -- Draft|Validated|Implemented|...
    actors_json    TEXT,                  -- JSON array
    sfd_count      INTEGER DEFAULT 0,
    br_count       INTEGER DEFAULT 0,
    ac_count       INTEGER DEFAULT 0,
    fd_count       INTEGER DEFAULT 0,
    created_at     TEXT,
    updated_at     TEXT,
    ingested_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS us (
    us_id           TEXT    PRIMARY KEY,    -- {n}-{m}-{Name}
    feat_n          INTEGER NOT NULL,
    n               INTEGER NOT NULL,
    m               INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    file_path       TEXT    NOT NULL,
    status          TEXT,                   -- Draft|Ready|InProgress|Review|Done|Deferred|Cancelled
    complexity      INTEGER,
    effort_estimate TEXT,                   -- S|M|L|XL
    covers_json     TEXT,                   -- JSON array of SFD/BR/AC/FD ids
    deps_json       TEXT,                   -- JSON array of us_id
    ac_count        INTEGER DEFAULT 0,
    created_at      TEXT,
    updated_at      TEXT,
    ingested_at     TEXT    NOT NULL,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id              TEXT    PRIMARY KEY,    -- "{us_id}.{family}"
    us_id                TEXT    NOT NULL,
    family               TEXT    NOT NULL,        -- backend|frontend
    file_path            TEXT    NOT NULL,
    schema_version       INTEGER,                  -- 1 | 2
    strict_ready         INTEGER DEFAULT 0,        -- bool
    us_hash              TEXT,
    capabilities_json    TEXT,
    file_count           INTEGER DEFAULT 0,
    generated_at         TEXT,
    ingested_at          TEXT    NOT NULL,
    FOREIGN KEY (us_id) REFERENCES us(us_id)
);

CREATE TABLE IF NOT EXISTS adrs (
    filename       TEXT    PRIMARY KEY,
    title          TEXT,
    status         TEXT,                  -- Proposed|Accepted|Superseded|Deprecated
    phase          TEXT,                  -- 4-ARCH|5-CODE
    decision_date  TEXT,                  -- YYYY-MM-DD parsé du timestamp filename
    file_path      TEXT    NOT NULL,
    superseded_by  TEXT,
    ingested_at    TEXT    NOT NULL
);

-- ============================================================
-- RUNS / GATES / EVENTS — orchestration & telemetry
-- ============================================================

CREATE TABLE IF NOT EXISTS runs (
    run_id         TEXT    PRIMARY KEY,
    command        TEXT    NOT NULL,       -- /sdd-full, /dev-run, /qa-generate, ...
    feat_n         INTEGER,
    feat_name      TEXT,
    started_at     TEXT    NOT NULL,
    ended_at       TEXT,
    updated_at     TEXT,
    status         TEXT    NOT NULL,       -- running|success|partial|failed|cancelled
    current_phase  TEXT,
    tags_json      TEXT,                   -- ex. ["force", "rebuild-arch"]
    params_json    TEXT,
    error_message  TEXT
);

CREATE TABLE IF NOT EXISTS run_phases (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT    NOT NULL,
    phase          TEXT    NOT NULL,
    started_at     TEXT,
    ended_at       TEXT,
    status         TEXT,                   -- pass|warn|fail|skip|running
    payload_json   TEXT,
    UNIQUE(run_id, phase),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS gates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT,
    feat_n         INTEGER,
    gate_name      TEXT    NOT NULL,       -- us|readiness|plan|code|api|qa
    decided_at     TEXT    NOT NULL,
    decision       TEXT    NOT NULL,       -- pass|fail|wait
    by_user        TEXT,                   -- si manuel (console web)
    payload_json   TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    run_id         TEXT,
    feat_n         INTEGER,
    us_id          TEXT,
    event_type     TEXT    NOT NULL,       -- run.start, phase.start, plan_validate, gate.decide, ...
    agent          TEXT,
    phase          TEXT,
    payload_json   TEXT
);

-- ============================================================
-- QA — résultats normalisés (coverage, quality, api-tests, a11y, code-review, security, perf, spec-compliance)
-- ============================================================

CREATE TABLE IF NOT EXISTS qa_coverage (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n             INTEGER NOT NULL,
    extracted_at       TEXT    NOT NULL,
    stack              TEXT    NOT NULL,    -- qa-dotnet-xunit, qa-node-vitest, ...
    tool               TEXT,                 -- coverlet, c8, JaCoCo, ...
    tool_version       TEXT,
    tests_total        INTEGER DEFAULT 0,
    tests_passed       INTEGER DEFAULT 0,
    tests_failed       INTEGER DEFAULT 0,
    tests_skipped      INTEGER DEFAULT 0,
    lines_covered      INTEGER DEFAULT 0,
    lines_total        INTEGER DEFAULT 0,
    lines_pct          REAL,
    branches_covered   INTEGER,
    branches_total     INTEGER,
    branches_pct       REAL,
    coverage_min       INTEGER,
    coverage_passed    INTEGER DEFAULT 0,    -- bool
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_coverage_files (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    coverage_id    INTEGER NOT NULL,
    file_path      TEXT    NOT NULL,
    lines_pct      REAL,
    FOREIGN KEY (coverage_id) REFERENCES qa_coverage(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_quality (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n         INTEGER NOT NULL,
    extracted_at   TEXT    NOT NULL,
    severity       TEXT,                   -- blocker|critical|major|minor|info
    issue_class    TEXT,                   -- préfixe [CLASS] (cf. error-classification.md)
    rule           TEXT,                   -- ex. "no-todo", "method-too-long"
    file_path      TEXT,
    line           INTEGER,
    message        TEXT,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_api_tests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n            INTEGER NOT NULL,
    extracted_at      TEXT    NOT NULL,
    gate_passed       INTEGER NOT NULL,
    -- status column added in migration 0005 (canonical PASS|WARN|FAIL|SKIPPED|INFRA_BLOCKED, audit P3)
    endpoints_total   INTEGER DEFAULT 0,
    tests_total       INTEGER DEFAULT 0,
    tests_passed      INTEGER DEFAULT 0,
    tests_failed      INTEGER DEFAULT 0,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_api_endpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    api_test_id     INTEGER NOT NULL,
    verb            TEXT    NOT NULL,
    route           TEXT    NOT NULL,
    tests_total     INTEGER DEFAULT 0,
    tests_passed    INTEGER DEFAULT 0,
    tests_failed    INTEGER DEFAULT 0,
    cases_json      TEXT,
    FOREIGN KEY (api_test_id) REFERENCES qa_api_tests(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_a11y (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n         INTEGER NOT NULL,
    extracted_at   TEXT    NOT NULL,
    verdict        TEXT,                   -- green|warn|red
    issue_class    TEXT    NOT NULL,       -- A11Y_MISSING_ALT, A11Y_INPUT_NO_LABEL, ...
    severity       TEXT,                   -- critical|serious|moderate|minor
    wcag           TEXT,                   -- ex. "1.1.1", "2.4.6"
    file_path      TEXT,
    line           INTEGER,
    message        TEXT,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_code_review (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n         INTEGER NOT NULL,
    extracted_at   TEXT    NOT NULL,
    verdict        TEXT,
    issue_class    TEXT    NOT NULL,       -- REVIEW_*, LAYER_VIOLATION, FRONTEND_BACKEND_CONTRACT_GAP
    severity       TEXT,
    file_path      TEXT,
    line           INTEGER,
    message        TEXT,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_security (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n         INTEGER NOT NULL,
    mode           TEXT    NOT NULL,       -- threat-model|scan
    extracted_at   TEXT    NOT NULL,
    verdict        TEXT,                   -- green|warn|red|informational
    issue_class    TEXT    NOT NULL,       -- SEC_*
    severity       TEXT,
    owasp          TEXT,                   -- ex. "A01", "A03"
    cwe            TEXT,                   -- ex. "CWE-89"
    stride         TEXT,                   -- pour mode threat-model
    file_path      TEXT,
    line           INTEGER,
    message        TEXT,
    control        TEXT,                   -- pour threat-model : control recommandé
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_performance (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n         INTEGER NOT NULL,
    extracted_at   TEXT    NOT NULL,
    verdict        TEXT,
    issue_class    TEXT    NOT NULL,       -- PERF_*
    severity       TEXT,
    metric         TEXT,                   -- LCP, CLS, p95, bundle_size, ...
    metric_value   REAL,
    metric_unit    TEXT,                   -- ms, KB, %, ...
    threshold      REAL,
    file_path      TEXT,
    line           INTEGER,
    message        TEXT,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

CREATE TABLE IF NOT EXISTS qa_spec_compliance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n          INTEGER NOT NULL,
    us_id           TEXT    NOT NULL,
    ac_id           TEXT    NOT NULL,       -- AC-1, AC-2, ...
    extracted_at    TEXT    NOT NULL,
    verdict         TEXT,                   -- verified|not_verified|partial|ambiguous|ui_only
    severity        TEXT,
    evidence_file   TEXT,
    evidence_line   INTEGER,
    message         TEXT,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n),
    FOREIGN KEY (us_id)  REFERENCES us(us_id)
);

-- ============================================================
-- TELEMETRY (tokens, context_budget, fidelity, readiness, breaking)
-- ============================================================

CREATE TABLE IF NOT EXISTS token_usage (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                       TEXT    NOT NULL,
    run_id                   TEXT,
    agent                    TEXT    NOT NULL,
    model                    TEXT,
    feat_n                   INTEGER,
    us_id                    TEXT,
    input_tokens             INTEGER DEFAULT 0,
    output_tokens            INTEGER DEFAULT 0,
    cache_creation_tokens    INTEGER DEFAULT 0,
    cache_read_tokens        INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS context_budget (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    agent           TEXT    NOT NULL,
    feat_n          INTEGER,
    us_id           TEXT,
    tokens_used     INTEGER,
    tokens_budget   INTEGER,
    passed          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS validation_reports (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n         INTEGER NOT NULL,
    report_type    TEXT    NOT NULL,       -- readiness|plan-validate|fidelity|augment-contract
    extracted_at   TEXT    NOT NULL,
    verdict        TEXT,                   -- GO|WARN|NO-GO|GREEN|YELLOW|RED|...
    score          INTEGER,
    summary        TEXT,
    payload_json   TEXT,
    file_path      TEXT,
    FOREIGN KEY (feat_n) REFERENCES feats(feat_n)
);

-- breaking_changes : retiré 2026-06-06 audit m11 (zéro consommateur côté code,
-- la résolution BREAKING CHANGES vit dans CLAUDE.md disque via
-- mark_breaking_resolved.py — pas dans console.db). Si recâblage futur :
-- ré-introduire ici + côté mark_breaking_resolved.py + invocation côté
-- dev-* STEP 8/11.5.

-- ============================================================
-- qa_mutation : storage pour mutation testing opt-in (Stryker etc.)
-- Aligné avec migration 0002 — présent ici pour init schema neuf.
-- Consommateur ingest : à câbler v7.1+ (cf. stacks/qa/mutation-testing.md).
-- ============================================================

CREATE TABLE IF NOT EXISTS qa_mutation (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n              INTEGER NOT NULL,
    extracted_at        TEXT    NOT NULL,
    stack               TEXT,
    tool                TEXT,
    tool_version        TEXT,
    mutants_total       INTEGER NOT NULL DEFAULT 0,
    mutants_killed      INTEGER NOT NULL DEFAULT 0,
    mutants_survived    INTEGER NOT NULL DEFAULT 0,
    mutants_timeout     INTEGER NOT NULL DEFAULT 0,
    mutants_no_coverage INTEGER NOT NULL DEFAULT 0,
    mutation_score_pct  REAL,
    score_min_pct       INTEGER,
    status              TEXT    NOT NULL,
    duration_ms         INTEGER,
    report_path         TEXT
);

CREATE INDEX IF NOT EXISTS idx_qa_mutation_feat_n ON qa_mutation(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_mutation_extracted_at ON qa_mutation(extracted_at);

-- ============================================================
-- qa_e2e : storage pour Playwright E2E opt-in
-- Aligné avec migration 0003 — présent ici pour init schema neuf.
-- Consommateur ingest : à câbler v7.1+ (cf. stacks/qa/playwright.md).
-- ============================================================

CREATE TABLE IF NOT EXISTS qa_e2e (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n              INTEGER NOT NULL,
    extracted_at        TEXT    NOT NULL,
    stack               TEXT,
    tool                TEXT,
    tool_version        TEXT,
    browser             TEXT,
    tests_total         INTEGER NOT NULL DEFAULT 0,
    tests_passed        INTEGER NOT NULL DEFAULT 0,
    tests_failed        INTEGER NOT NULL DEFAULT 0,
    tests_skipped       INTEGER NOT NULL DEFAULT 0,
    us_total            INTEGER NOT NULL DEFAULT 0,
    us_covered          INTEGER NOT NULL DEFAULT 0,
    min_per_us          INTEGER,
    status              TEXT    NOT NULL,
    duration_ms         INTEGER,
    report_path         TEXT
);

CREATE INDEX IF NOT EXISTS idx_qa_e2e_feat_n ON qa_e2e(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_e2e_extracted_at ON qa_e2e(extracted_at);

-- ============================================================
-- INDEX
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_us_feat                  ON us(feat_n);
CREATE INDEX IF NOT EXISTS idx_us_status                ON us(status);
CREATE INDEX IF NOT EXISTS idx_plans_us                 ON plans(us_id);
CREATE INDEX IF NOT EXISTS idx_adrs_phase               ON adrs(phase);
CREATE INDEX IF NOT EXISTS idx_adrs_date                ON adrs(decision_date);

CREATE INDEX IF NOT EXISTS idx_runs_feat                ON runs(feat_n);
CREATE INDEX IF NOT EXISTS idx_runs_started             ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_runs_status              ON runs(status);
CREATE INDEX IF NOT EXISTS idx_run_phases_run           ON run_phases(run_id);
CREATE INDEX IF NOT EXISTS idx_gates_run                ON gates(run_id);
CREATE INDEX IF NOT EXISTS idx_gates_feat               ON gates(feat_n);
CREATE INDEX IF NOT EXISTS idx_events_type              ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_feat              ON events(feat_n);
CREATE INDEX IF NOT EXISTS idx_events_run               ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_ts                ON events(ts);

CREATE INDEX IF NOT EXISTS idx_qa_coverage_feat         ON qa_coverage(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_quality_feat          ON qa_quality(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_quality_severity      ON qa_quality(severity);
CREATE INDEX IF NOT EXISTS idx_qa_api_tests_feat        ON qa_api_tests(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_a11y_feat             ON qa_a11y(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_a11y_severity         ON qa_a11y(severity);
CREATE INDEX IF NOT EXISTS idx_qa_code_review_feat      ON qa_code_review(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_code_review_severity  ON qa_code_review(severity);
CREATE INDEX IF NOT EXISTS idx_qa_security_feat         ON qa_security(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_security_severity     ON qa_security(severity);
CREATE INDEX IF NOT EXISTS idx_qa_security_mode         ON qa_security(mode);
CREATE INDEX IF NOT EXISTS idx_qa_performance_feat      ON qa_performance(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_performance_severity  ON qa_performance(severity);
CREATE INDEX IF NOT EXISTS idx_qa_spec_compliance_feat  ON qa_spec_compliance(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_spec_compliance_us    ON qa_spec_compliance(us_id);

CREATE INDEX IF NOT EXISTS idx_token_usage_run          ON token_usage(run_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_agent        ON token_usage(agent);
CREATE INDEX IF NOT EXISTS idx_token_usage_ts           ON token_usage(ts);
CREATE INDEX IF NOT EXISTS idx_context_budget_agent     ON context_budget(agent);
CREATE INDEX IF NOT EXISTS idx_validation_reports_feat  ON validation_reports(feat_n);
CREATE INDEX IF NOT EXISTS idx_validation_reports_type  ON validation_reports(report_type);
