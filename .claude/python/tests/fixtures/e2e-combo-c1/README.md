# E2E fixture — combo C1

This directory contains a minimal FEAT used to manually validate the full
`/sdd-full` pipeline on combo C1 (.NET Minimal API + React + shadcn +
dotnet-xunit + Azure AD).

> ⚠️ **Note historique** : auparavant invoqué automatiquement par le
> workflow GitHub Actions `nightly-e2e.yml` (supprimé — ce repo est sur
> Azure DevOps, pas GitHub). La fixture reste utilisable en standalone
> par un Tech Lead pour reproduire un comportement.

## Why a fixture

A real `/sdd-full` run spawns Opus 4.7 agents (dev-backend, dev-frontend,
auditors) which cost real money. The framework's smoke test +
deterministic validators run in ~5 seconds and catch ~80% of regressions
without LLM calls. The full pipeline catches the remaining 20% (prompt
drift, agent contract changes, integration with `arch` bootstrap) but
only when an ANTHROPIC_API_KEY secret is exposed to the workflow with
an explicit budget cap.

## Contents

- **`1-Minimal.md`** : minimal FEAT (1 SFD, 2 FDs, 1 BR, 2 ACs, 1 actor).
  Designed to compile down to ~1 US backend + 1 US frontend, total
  ~$2-3 in Opus tokens.

## Activation

The nightly workflow's `e2e-full-pipeline` job is gated behind two
preconditions :
1. `secrets.ANTHROPIC_API_KEY` exists in the repo settings.
2. The `MaxCostPerRun` config caps the run at $5 (safety margin).

Without the secret, only the deterministic checks run (bootstrap, smoke,
validators, pytest). This is the default state of the public repo.

## Activation by Tech Lead (production)

1. Add `ANTHROPIC_API_KEY` to GitHub repo secrets.
2. Optionally raise `MaxCostPerRun` in the workflow env if the fixture
   grows beyond 1 US.
3. The next nightly run will spawn `/sdd-full 1` against this fixture.

## Maintenance

When SDD_Pro changes break this minimal pipeline, the nightly job goes
RED. Tech Lead investigates :
- regression in `arch` bootstrap → reproduce with `python bootstrap.py
  --combo c1 --skip-install` + manual `/sdd-full 1`
- regression in dev-backend / dev-frontend → inspect generated code under
  `workspace/output/src/HelloApp/`
- regression in QA gate → inspect `workspace/output/qa/feat-1/report.md`
