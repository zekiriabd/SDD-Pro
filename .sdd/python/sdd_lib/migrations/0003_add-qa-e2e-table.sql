-- 0003_add-qa-e2e-table.sql
-- v7.0.0 P1 §6.5 — Playwright E2E opt-in storage
-- See stacks/qa/playwright.md and agents/qa.md STEP 8.bis

CREATE TABLE IF NOT EXISTS qa_e2e (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n              INTEGER NOT NULL,
    extracted_at        TEXT    NOT NULL,            -- ISO-8601 UTC
    stack               TEXT,                        -- frontend stack id : react|vue|angular|blazor-wasm
    tool                TEXT,                        -- @playwright/test | Microsoft.Playwright
    tool_version        TEXT,
    browser             TEXT,                        -- chromium | firefox | webkit
    tests_total         INTEGER NOT NULL DEFAULT 0,
    tests_passed        INTEGER NOT NULL DEFAULT 0,
    tests_failed        INTEGER NOT NULL DEFAULT 0,
    tests_skipped       INTEGER NOT NULL DEFAULT 0,
    us_total            INTEGER NOT NULL DEFAULT 0,  -- US with UI ACs (denominator)
    us_covered          INTEGER NOT NULL DEFAULT 0,  -- US with ≥ E2EMinPerUs tests
    min_per_us          INTEGER,                     -- E2EMinPerUs at time of run
    status              TEXT NOT NULL,               -- PASS|WARN|FAIL|SKIPPED|INFRA_BLOCKED
    duration_ms         INTEGER,
    report_path         TEXT                         -- workspace/output/qa/feat-{n}/e2e.json
);

CREATE INDEX IF NOT EXISTS idx_qa_e2e_feat_n ON qa_e2e(feat_n);
CREATE INDEX IF NOT EXISTS idx_qa_e2e_extracted_at ON qa_e2e(extracted_at);
