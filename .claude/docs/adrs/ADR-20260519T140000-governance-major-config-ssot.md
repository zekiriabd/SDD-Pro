# ADR-20260519T140000-governance-major-config-ssot

- **Status**: Accepted
- **Date**: 2026-05-19
- **Slug**: `governance-major-config-ssot`
- **Materialized**: 2026-06-06 (audit CR-1)

## Context

Pre-v7.0.0, each agent prompt declared its own `Read:` / `Write:`
header listing the paths it touches. These declarations drifted from
the actual Read/Write tool calls (no enforcement), and the `SubagentStop`
hook had its own list of permitted writes per agent — yet another source.

Three places to update when an agent learned a new file → three places
that diverged in practice.

## Decision

Single Source of Truth: `.claude/loader.yml` declares, per agent:
- `reads:` — file globs the agent is expected to Read
- `writes:` — file globs the agent is allowed to Write
- `forbidden_writes:` — explicit denylist for paths the agent must
  never touch (e.g. `dev-backend` must not write under `workspace/output/src/{AppName}/`)
- `modes:` — agent invocation modes (e.g. `qa.modes = {full, manual, off}`)

Agents reference `@.claude/loader.yml` in their preamble rather than
inlining their footprint. The `SubagentStop` hook reads `loader.yml`
to enforce `forbidden_writes` at the FS level.

## Consequences

- One file to update per agent capability change.
- `validate_inline_rules.py` (planned) cross-checks loader.yml ↔
  agent prompts for declared paths.
- New agents must register in `loader.yml` to get write permission via
  the SubagentStop hook — security improvement (deny-by-default).

## Related

- `.claude/loader.yml`
- `.claude/python/sdd_hooks/audit_file_ownership.py`
- ADR `governance-major-prompts-trim` (companion decision)
