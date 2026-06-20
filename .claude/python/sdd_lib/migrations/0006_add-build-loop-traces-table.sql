-- 0006_add-build-loop-traces-table.sql
-- Audit T2.6 (2026-06-08) — Anthropic AI Engineering recommendation #6 :
-- instrument build_loop to detect convergence failure (same [CLASS] twice
-- in a row = LLM tourne en rond → STOP immédiat, ne pas attendre
-- BuildLoopMaxIter).
--
-- Sans cette table, build_loop est aveugle : il itère N fois puis émet
-- [BUILD_LOOP_EXHAUSTED] sans diagnostic post-mortem. Avec elle, on a
-- une trace fine pour mesurer (a) le taux de convergence réel, (b) les
-- classes d'erreur les plus pathologiques, (c) les agents qui tournent
-- en rond le plus souvent.
--
-- Lecture : exploitable via report_roi.py + dashboards / sdd-status.

CREATE TABLE IF NOT EXISTS build_loop_traces (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               TEXT,                       -- FK runs.id (nullable si standalone)
    feat_n               INTEGER,                    -- pour filtrage rapide
    us_id                TEXT,                       -- {n}-{m} (ex. "1-2")
    agent                TEXT NOT NULL,              -- dev-backend | dev-frontend
    iter                 INTEGER NOT NULL,           -- 1..BuildLoopMaxIter
    error_class_before   TEXT,                       -- [CLASS] avant fix (NULL si iter 1 + premier echec)
    error_class_after    TEXT,                       -- [CLASS] apres fix tentative (NULL si succes)
    fix_strategy         TEXT,                       -- libre : "add using" | "fix DI" | etc.
    converged            INTEGER NOT NULL DEFAULT 0, -- 1 si exit code 0 apres iter
    same_class_streak    INTEGER NOT NULL DEFAULT 0, -- nb iter consecutives meme [CLASS] = signal pathologique
    ts                   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    duration_ms          INTEGER,
    notes                TEXT
);

CREATE INDEX IF NOT EXISTS idx_build_loop_traces_run         ON build_loop_traces(run_id);
CREATE INDEX IF NOT EXISTS idx_build_loop_traces_feat        ON build_loop_traces(feat_n);
CREATE INDEX IF NOT EXISTS idx_build_loop_traces_agent       ON build_loop_traces(agent);
CREATE INDEX IF NOT EXISTS idx_build_loop_traces_us          ON build_loop_traces(us_id);
CREATE INDEX IF NOT EXISTS idx_build_loop_traces_class       ON build_loop_traces(error_class_after);
CREATE INDEX IF NOT EXISTS idx_build_loop_traces_streak      ON build_loop_traces(same_class_streak);
