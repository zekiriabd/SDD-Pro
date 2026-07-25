# ADR-20260519T150000-governance-major-flags-trim

- **Status**: Accepted
- **Date**: 2026-05-19
- **Slug**: `governance-major-flags-trim`
- **Materialized**: 2026-06-06 (audit CR-1)

## Context

`/sdd-full` and `/dev-run` accumulated 12+ flags over v6.x (`--force`,
`--no-validate`, `--no-plan-on-warn`, `--resume`, `--rebuild-arch`,
`--manual-gates`, `--plan`, `--max-parallel N`, `--mock-auditors`,
`--skip-api-gate`, `--legacy-parallel`, `--auto-init`…). Most were
escape hatches added during specific incidents and never retired.

The bypass-cumul check (`SDD_ALLOW_FORCE=1` required when ≥2 bypass
flags are set) was a hack on top of the hack — fixing the symptom of
flag proliferation rather than the cause.

## Decision

Trim to the 6 supported flags documented in `CLAUDE.md §3` :
`--force`, `--rebuild-arch`, `--resume`, `--manual-gates`, `--plan`,
`--max-parallel N`. The rest are either:
- folded into Project Config (`stack.md`) keys (e.g.
  `GatedWorkflow: false` replaces `--legacy-parallel`),
- removed (e.g. `--mock-auditors` — superseded by `phase_planner.py`
  determining auditor needs),
- kept as legacy aliases with `WARN` audit log on use (e.g.
  `--no-validate` → equivalent to `--force`).

## Consequences

- Smaller surface, easier to document, fewer drift opportunities.
- Some users on v6.x must migrate scripts referencing retired flags.
- The cumul check stays (defense-in-depth) but covers a smaller set.

## Related

- `commands/sdd-full.md`
- `commands/dev-run.md`
- ADR `governance-major-prompts-trim`
