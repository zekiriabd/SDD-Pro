# SDD_Pro — Quickstart

> 🇫🇷 [Version française](quickstart.md) — French docs are the canonical source ; this English page mirrors the Quickstart essentials only.
>
> On-demand document (`Read @.claude/docs/quickstart.en.md`).
> Referenced from [.claude/CLAUDE.md](../CLAUDE.md) §10 (slim entry point).

## 0. Automated bootstrap (recommended for a new project)

```bash
python bootstrap.py                # interactive — 5 questions max
python bootstrap.py --combo c1     # one-shot, .NET+React+Azure combo
python bootstrap.py --combo c2     # one-shot, Kotlin+React+Azure combo
python bootstrap.py --dry-run      # preview without writing
```

The bootstrap generates a coherent `stack.md` (43 Project Config keys with safe defaults), creates the `workspace/output/.sys/` structure, installs Python deps, and offers to install console deps.

See [README.en.md](../../README.en.md#-quickstart--new-project) for the detail of the validated combos.

Sections 1-5 below describe **manual configuration** (brownfield / migration of an existing project).

## 1. Select the stack

Edit `workspace/input/stack/stack.md`: activate 1 backend, 1 frontend, 1 UI design system, and optionally 1 auth profile.

Fill in `## Project Config`:
- `AppName`, `BackendName`, `LibName`
- `LibStrategy: shared | openapi-codegen | none` — auto-default based on back/front language match.

## 2. Fill in the stack.md configuration blocks

Since 2026-05-14, no more env vars: the Tech Lead writes values directly into `stack.md`. The `arch` agent propagates them into the application config files (`appsettings.json` / `application.yml` / `config/default.json` / `app/config.py`) during Phase A — STEP 4.5.

### `## Active Database` (if SQL backend)

```yaml
## Active Database
DatabaseType: PostgreSql        # PostgreSql | SqlServer | MySql | Sqlite | none
DB_HOST: 127.0.0.1
DB_PORT: 5432
DB_USER: myapp_dev
DB_PASSWORD: <secret>           # gitignored — local secret
DB_NAME: myapp
```

### `## Active Auth Specs` (azure-ad)

```yaml
## Active Auth Specs
- .claude/stacks/auth/azure-ad.md
- AZ_TENANTID: <tenant-uuid>
- AZ_CLIENTID: <client-uuid>
- AZ_DOMAIN: yourdomain.onmicrosoft.com
- AZ_AUDIENCES: '<client-uuid>'
- AZ_BE_CALLBACKPATH: /signin-oidc
- AZ_FE_CALLBACKPATH: /authentication/login-callback
```

## 3. Create your first FEAT

In Claude Code: `/feat-generate <Name>`. The agent asks 3-6 elicitation questions (objective, actors, business rules, acceptance criteria, NFRs) and writes `workspace/input/feats/{n}-{Name}.md`.

*(Optional)* drop static HTML mockups under `workspace/input/ui/{n}-{m}-{Name}.html` — they are consumed passively by `dev-frontend` to map to design system components (cf. `.claude/stacks/ui/*.md` §2 + §7).

## 4. Run the full pipeline

```
/sdd-full {n}
```

This chains:
1. `/us-generate {n}` — PO agent splits the FEAT into User Stories (1-3 target, hard cap 10).
2. `/feat-validate {n}` — Readiness gate (deterministic, 0 token).
3. *(optional)* `/dev-plan {n}` — Plan-then-review gate (if `--plan` or `PlanReviewDefault: true`).
4. `/dev-run {n}` — arch + DB → dev-backend ALL US → QA API Gate → dev-frontend ALL US.
5. `/qa-generate {n}` — unit tests + coverage + quality scan + auditors (code-review, security, spec-compliance, arch).

Useful flags:
- `--plan` — force plan-review even on GO
- `--force` — bypass readiness NO-GO (audit-logged)
- `--rebuild-arch` — force a re-bootstrap by arch
- `--max-parallel N` — override `MaxParallel` config (1-12)
- `--manual-gates` — enable the 4 manual gates (afterUS/afterReadiness/afterPlan/afterCode)
- `--resume` — pick up where the last run stopped

## 5. Inspect status / verdict

```
/sdd-status               # all FEATs
/sdd-status {n}           # one FEAT
/sdd-review {n}           # SonarQube-style consolidated audit (blocking on RED)
/sdd-serve                # boots backend + frontend + web console in parallel
```

The web console at `http://127.0.0.1:4000` is the cockpit for PO/Tech Lead validation.
