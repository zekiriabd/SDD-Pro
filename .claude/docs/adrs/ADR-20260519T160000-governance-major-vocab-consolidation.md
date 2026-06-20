# ADR-20260519T160000-governance-major-vocab-consolidation

- **Status**: Accepted
- **Date**: 2026-05-19
- **Slug**: `governance-major-vocab-consolidation`
- **Materialized**: 2026-06-06 (audit CR-1)

## Context

Pre-v7.0.0, error classes (`[CLASS]` prefixes) were declared inline in
each agent's prompt. Drift accumulated: `code-reviewer` knew about
`[REVIEW_*]`, `security-reviewer` had `[SEC_*]`, dev-* used
`[BUILD_*]` + `[STACK_*]`, etc. — no single source. A new auditor
agent had no way to discover the existing taxonomy.

Simultaneously, the build_loop heuristic (which classes itère vs
fail-fast vs WARN) was scattered across hooks, scripts, and prompts.

## Decision

`rules/error-classification.md` becomes the single source of truth
for **all** `[CLASS]` prefixes, with mandatory columns:
- Class name
- OWASP/CWE mapping (when applicable)
- Severity (`info | minor | moderate | serious | critical`)
- Phase d'émission
- Hard-blocking? (override `*FailOn` config)

`build_loop` behavior (§3, §3.1) lives in the same file. Legacy
classes (`[A11Y_*]`, `[PERF_*]`) move to `error-classification-legacy.md`
since the emitter agents were retired.

## Consequences

- One file to grep for "what is class X" — across all agents.
- New agents reference `error-classification.md` rather than inventing
  classes locally.
- Drift detection possible: `validate_inline_rules.py` (planned) can
  diff agent prompts vs the canonical table.

## Related

- `rules/error-classification.md`
- `rules/error-classification-legacy.md`
- ADR `governance-major-auditors-trim` (parent decision)
