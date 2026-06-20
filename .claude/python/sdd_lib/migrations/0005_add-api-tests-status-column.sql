-- 0005_add-api-tests-status-column.sql
-- v7.0.0-alpha audit P3 (2026-06-06) — persist the canonical 5-valued `status`
-- of the API Gate (cf. build-and-loop.md §1.3), not just the legacy boolean
-- `gate_passed`. Without this column, the distinction WARN / SKIPPED /
-- INFRA_BLOCKED was derived at read-time and lost to /dev-run STEP 6.c
-- idempotence (which only saw gate_passed=true and could not tell a SKIPPED
-- "nothing to test" run from a PASS "tests went green" run).
--
-- Values : PASS | WARN | FAIL | SKIPPED | INFRA_BLOCKED  (NULL allowed for
-- legacy rows pre-migration — readers fall back to gate_passed/tests_failed).
--
-- Backward-compat : `gate_passed` is preserved (computed as status ∈
-- {PASS, WARN, SKIPPED}), so legacy callers using query_console_db.py api-gate
-- on the boolean keep working unchanged.

ALTER TABLE qa_api_tests ADD COLUMN status TEXT;

-- Best-effort backfill for existing rows (we don't have the original endpoints
-- count partition between SKIPPED/PASS without re-reading; the conservative
-- mapping below preserves the legacy boolean truth while leaving INFRA_BLOCKED
-- absent — it was never recorded pre-v7.0.0-alpha audit P3).
UPDATE qa_api_tests
   SET status = CASE
       WHEN tests_failed >= 1            THEN 'FAIL'
       WHEN gate_passed = 1 AND tests_total = 0 THEN 'SKIPPED'
       WHEN gate_passed = 1              THEN 'PASS'
       ELSE 'FAIL'
   END
 WHERE status IS NULL;
