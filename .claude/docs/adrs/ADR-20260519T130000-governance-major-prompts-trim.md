# ADR-20260519T130000-governance-major-prompts-trim

- **Status**: Accepted
- **Date**: 2026-05-19
- **Slug**: `governance-major-prompts-trim`
- **Materialized**: 2026-06-06 (audit CR-1)

## Context

`CLAUDE.md` (slim entry point loaded into every Claude Code session)
had grown to 250+ lines through accreted history of stack tables,
agent rosters, rule rationales. Every Claude Code invocation paid this
cost. Substance was diluted: the file became hard to scan and hard to
keep current.

## Decision

Cap `CLAUDE.md` at **150 lines**. Push substance to:
- `@.claude/docs/*.md` — long-form architecture/workflow/conventions
- `@.claude/rules/*.md` — operational rules loaded by agents on demand
- `@.claude/loader.yml` — machine-readable reads/writes manifest

Each section of `CLAUDE.md` becomes a 1-paragraph headline + `@-ref`
to the canonical detail file. The Tech Lead reads ~150 lines max at
session start; agents Read the detail files only when they need them.

## Consequences

- Token cost per session reduced by ~3-5 KB on system prompt.
- Risk: split-brain — substance in CLAUDE.md headline contradicts the
  `@-ref` target. Mitigation: `validate_inline_rules.py` (planned)
  detects header drift.
- Editorial discipline: any new content goes to `@.claude/docs/` or
  `@.claude/rules/` first, then a 1-line summary in CLAUDE.md.

## Related

- `CLAUDE.md` (top of file, headline "Slim entry point : 150 lignes max")
- ADR `governance-major-config-ssot` (loader manifest)
- ADR `governance-major-vocab-consolidation` (error class consolidation)
