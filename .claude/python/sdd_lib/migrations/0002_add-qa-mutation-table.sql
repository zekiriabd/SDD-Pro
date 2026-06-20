-- 0002_add-qa-mutation-table.sql
-- v7.0.0 P0 §6.2 — mutation testing opt-in storage
-- See stacks/qa/mutation-testing.md and agents/qa.md STEP 8.5

CREATE TABLE IF NOT EXISTS qa_mutation (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n              INTEGER NOT NULL,
    extracted_at        TEXT    NOT NULL,            -- ISO-8601 UTC
    stack               TEXT,                        -- qa-dotnet-xunit | qa-node-vitest | ...
    tool                TEXT,                        -- stryker.net | stryker-js | mutmut | pitest
    tool_version        TEXT,
    mutants_total       INTEGER NOT NULL DEFAULT 0,
    mutants_killed      INTEGER NOT NULL DEFAULT 0,
    mutants_survived    INTEGER NOT NULL DEFAULT 0,
    mutants_timeout     INTEGER NOT NULL DEFAULT 0,
    mutants_no_coverage INTEGER NOT NULL DEFAULT 0,
    mutation_score_pct  REAL,                        -- 0..100
    score_min_pct       INTEGER,                     -- MutationScoreMin at time of run
    status              TEXT NOT NULL,               -- PASS|WARN|FAIL|SKIPPED|INFRA_BLOCKED
    duration_ms         INTEGER,
    report_path         TEXT                         -- workspace/output/qa/feat-{n}/mutation.json
);

CREATE INDEX IF NOT EXISTS idx_qa_mutation_feat_n ON qa_mutation(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_mutation_extracted_at ON qa_mutation(extracted_at);
