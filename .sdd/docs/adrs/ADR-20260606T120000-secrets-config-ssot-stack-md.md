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
