-- 0004_add-auditor-runs-table.sql
-- v7.0.0 P0 C3 fix — distinguish "auditor ran with 0 findings" from "auditor
-- did not run" in /sdd-review --ensure-scans.
--
-- Before this migration, fetch_findings() in sdd_review.py inferred source
-- presence from the count of rows in qa_quality / qa_code_review / etc. A
-- clean scan (0 findings) was indistinguishable from a missing scan,
-- producing false-positive [REVIEW_SOURCES_MISSING] on healthy FEATs.
--
-- This table records ONE row per auditor invocation, regardless of findings
-- count. ingest paths (quality_scan.py, ingest_agent_report.py for code/sec/
-- spec/arch JSON, etc.) MUST insert here in addition to the per-finding
-- tables. /sdd-review --ensure-scans then reads source presence from here.

CREATE TABLE IF NOT EXISTS auditor_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feat_n          INTEGER NOT NULL,
    auditor         TEXT    NOT NULL,        -- quality|code-review|security|spec|arch|a11y|perf
    extracted_at    TEXT    NOT NULL,        -- ISO-8601 UTC
    findings_count  INTEGER NOT NULL DEFAULT 0,
    verdict         TEXT,                    -- GREEN|YELLOW|RED|informational|null
    payload_json    TEXT                     -- optional context (run_id, mode, etc.)
);

CREATE INDEX IF NOT EXISTS idx_auditor_runs_feat     ON auditor_runs(feat_n);
CREATE INDEX IF NOT EXISTS idx_auditor_runs_auditor  ON auditor_runs(auditor);
CREATE INDEX IF NOT EXISTS idx_auditor_runs_feat_aud ON auditor_runs(feat_n, auditor);
