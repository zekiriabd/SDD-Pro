# ADR-20260519T120000-governance-major-auditors-trim

- **Status**: Accepted
- **Date**: 2026-05-19
- **Slug**: `governance-major-auditors-trim`
- **Materialized**: 2026-06-06 (audit CR-1 — was cited in CLAUDE.md/CHANGELOG without an ADR file)

## Context

SDD_Pro v6.10 shipped 4 auditor agents that each ran an LLM pass on the
generated code: `accessibility-auditor` (Haiku 4.5), `performance-auditor`
(Sonnet 4.6), `code-reviewer`, `security-reviewer`. The first two
(a11y + perf) regularly produced rapports that the Tech Lead either
ignored (informational) or treated as advisory. The marginal LLM cost
(~1-3 USD per FEAT) was high relative to the action rate.

Independently, the ecosystem matured: `axe-core` (a11y) and Lighthouse CI
(perf) became reliable, deterministic, free-tier-friendly scanners that
emit comparable JSON output.

## Decision

Retire `accessibility-auditor` and `performance-auditor` agents from
v7.0.0. Preserve their error-class taxonomy (`[A11Y_*]` / `[PERF_*]`) for
future ingest scripts (`ingest_axe.py`, `ingest_lighthouse.py`) wiring
into the generated project's CI workflow (`templates/ci-quality.github-actions.yml.template`).

The taxonomy now lives in `rules/error-classification-legacy.md` (a
deliberately separate file so the active `rules/error-classification.md`
stays focused on emitted classes).

## Consequences

- `/sdd-review` aggregation columns `qa_a11y` / `qa_performance` may
  show 0/0 on SDD-only projects until the ingest pipeline is wired.
- LLM cost per FEAT drops ~1-3 USD (informational-rate auditors removed).
- Tech Lead must opt-in to a11y/perf via CI workflow generation
  (`CiTemplatesGeneration: true` in stack.md Project Config).
- No regression in security/correctness — `code-reviewer` and
  `security-reviewer` remain.

## Related

- `rules/error-classification-legacy.md` §1, §2 — preserved taxonomy
- `docs/CHANGELOG.md` v7.0.0-alpha
- ADR `governance-major-prompts-trim` (companion decision)
