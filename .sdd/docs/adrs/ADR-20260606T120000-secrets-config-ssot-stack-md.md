# ADR-20260606T120000-secrets-config-ssot-stack-md

- **Status**: Accepted
- **Date**: 2026-06-06
- **Slug**: `secrets-config-ssot-stack-md`

## Context

Pre-2026-06-06, three contradicting patterns coexisted in the framework
for secrets/config propagation:

- **Pattern A** (`stack.md.template` header, `arch.md:335-342`):
  stack.md declares env var **names** (`KEY: ${KEY}`); the generated
  app reads `Environment.GetEnvironmentVariable`, `process.env`,
  `@Value("${KEY}")`, `os.environ`.
- **Pattern B** (`dotnet-minimalapi.md:461`, `blazor-server.md:350`,
  `node-express.md §8.2`, `bootstrap.py:462-503`, `.gitignore:17-21`):
  stack.md contains real values in clear (gitignored). Agent `arch`
  Phase A reads stack.md → populates `appsettings.json` /
  `application.yml` / `config/default.json`. Generated code reads the
  native config (`IConfiguration`, `@Value("${spring.datasource.*}")`).
- **Pattern C** (`next.md:367`, `kotlin-mustache.md:422`): hybrid —
  arch writes a `.env.local` file, code reads `process.env`.

The contradiction was self-evident: `agents/arch.md:46` declared
"jamais d'env vars" and `agents/arch.md:339` declared "🔴 Pattern
obligatoire env-var binding" — 290 lines apart in the same file.

User decision (2026-06-06) : **Pattern B is canonical**.

## Decision

`stack.md` is the **single source of truth** for secrets and config.
It is gitignored, contains values in clear (DB_PASSWORD, AUTH_JWT_SECRET,
AZ_TENANTID, SMTP_*…). Agent `arch` Phase A reads stack.md and
populates the native config of the active stack:

- .NET     → `appsettings.json` (`ConnectionStrings:Default`, `AzureAd:*`, `Jwt:*`)
- Spring   → `application.yml` (`spring.datasource.*`, `auth.jwt.*`)
- Node     → `config/default.json` (`db.*`, `auth.*`)
- Python   → `app/config.py` (`Settings` dataclass with `db_*`, `auth_*`)

The generated application code reads **only** the native config —
never via `Environment.GetEnvironmentVariable`, `process.env.DB_*`,
`os.environ["DB_*"]`, `@Value("${DB_*}")`. New error class
`[SEC_ENV_VAR_FORBIDDEN]` (cf. `error-classification.md §1.11`) flags
violations.

`appsettings.json`, `application.yml`, `config/default.json` generated
by arch MUST be gitignored in the target project (they contain the
clear values copied from stack.md).

## Consequences

- 18 files realigned (template, arch.md, bootstrap.py, CLAUDE.md,
  stacks/fullstack/{next,kotlin-mustache,nuxt,angular-universal}.md,
  stacks/auth/{azure-ad,auth-local}.md, error-classification.md,
  security-reviewer + scan patterns, gitignore template).
- `bootstrap.py` now generates `AUTH_JWT_SECRET` via
  `secrets.token_urlsafe(48)` instead of a literal placeholder
  (eliminates the footgun of placeholder shipped unchanged).
- `code-reviewer` + `security-reviewer` `quality_scan` config must
  exclude stack.md + generated config files from secret-scan to avoid
  false positives.
- The `${KEY}` env-var substitution syntax in `stack.md.template`
  comments is removed.
- Re-bench of fullstack combos (next/nuxt/kotlin-mustache) required
  to confirm the alignment.

## Related

- `templates/stack.md.template` (header rewritten)
- `agents/arch.md` STEP 4.5 (Pattern B canonical)
- `bootstrap.py:render_stack_md` (real secret generation)
- `rules/error-classification.md §1.11` (`[SEC_ENV_VAR_FORBIDDEN]`)
- `rules/library-and-stack.md §1.0` (Pattern B description)

## Amendment 2026-08-31 — stack.md is now TRACKED (partial reversal)

This ADR's premise "it is gitignored" **no longer holds**. Commit `408c511`
(2026-08-30) versioned the `workspace/` skeleton and, with it, made
`workspace/stack/stack.md` a tracked file so a `git clone` restores the
project configuration SSoT. The Pattern B decision itself is unchanged (one
SSoT, `arch` propagates to native config, `[SEC_ENV_VAR_FORBIDDEN]` still
forbids direct env-var reads) — only the confidentiality property is gone.

Consequences for anyone reading this ADR as the canonical reference:

- `stack.md` MUST contain only `${VAR}` placeholders or non-sensitive values.
  A real secret written there ships to `origin` on the first push and must be
  treated as compromised.
- To keep real values locally on a tracked file:
  `git update-index --skip-worktree workspace/stack/stack.md`.
- The rest of `workspace/` stays ignored. The re-inclusion is scoped to the
  single file (`!workspace/stack/stack.md`), not to the directory — a
  directory-wide negation (`!workspace/stack/**`, in force between `408c511`
  and 2026-08-31) made any file dropped in `workspace/stack/` committable,
  including a re-created `.env`.
- Enforcement is an index guard, not a gitignore rule: a `.gitignore` has no
  retroactive effect on an already-tracked file. See
  `.sdd/python/tests/test_repo_gitignore_index_guard.py`.
- `bootstrap.py:render_stack_md` still generates a real `AUTH_JWT_SECRET` via
  `secrets.token_urlsafe(48)`. On a tracked `stack.md` that generated secret
  becomes pushable — do not commit the rendered file.
