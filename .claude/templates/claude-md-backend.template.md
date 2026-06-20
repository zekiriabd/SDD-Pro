---
generated-by: agent arch
generated-at: {ISO-8601 UTC}
stack-md-hash: {sha256-8-chars}
project-type: backend
project-name: {BackendName}
active-stacks:
  - .claude/stacks/backend/{backend-stack-id}.md
  - .claude/stacks/auth/{auth-stack-id}.md     # si auth actif
---

# {BackendName} — Backend Project Context

## Project Config (subset)
- BackendName: {BackendName}
- LibName: {LibName}             # si défini
- AppNamespace: {AppNamespace}
- DatabaseType: {DatabaseType}

## Architecture
{résumé §1.1 + §1.2 du stack backend actif — pattern applicatif, couches}

## Layer → Path Mapping
- Service interface  → Services/Interfaces/
- Service impl       → Services/Implementations/
- DTO                → DTOs/
- Endpoint           → Endpoints/
- Mapper             → Mappers/
- Entity (scaffold)  → Entities/
- Migration          → Migrations/        (si EF Core)
- Config             → Program.cs (augment)

## Build Command
{build command — ex. dotnet build {BackendName}.csproj --nologo}

## Persistence (si DatabaseType ≠ none)
- Driver installé: {driver name from §8.1 du stack}
- Connection string pattern: {builder canonique du langage, cf §8.2}
- **Clé canonique de lecture (LITTÉRAL — anti-derive load-bearing)** :
  - .NET : `builder.Configuration.GetConnectionString("Default")` — argument **EXACTEMENT** `"Default"` (jamais `"{AppName}Db"`, `"{BackendName}Db"`, `"{ProjectName}Db"`, `"NounouJobDb"`, ou tout autre token dérivé)
  - Node : section `db` du config natif (`config.get('db.connection')` / `config.get('db.url')`)
  - Python : section `db_settings` (pydantic-settings)
  - Java/Kotlin : `spring.datasource.url` (Spring) — pas d'alias custom
  - Toute clé non canonique → ERROR `[DERIVE_VIOLATION]` au build (post-mortem 2026-05-14 — cf. stack §5.1.0)
- Scaffolding tool: {outil §8.3}
- Schema source: ../db/schema.json
- Convention extensions custom: partial classes adjacentes (.NET) / src/lib/extensions/ (Node) / entities/db/extensions/ (Python)

## Auth (si stack auth actif)
- Provider: {azure-ad | auth-local | ...}
- Pattern: {résumé §3-4 du stack auth}
- Config keys: section `AzureAd` / `azure.ad.*` / `azure_settings` selon stack backend (peuplée par arch depuis ## Active Auth Specs de stack.md)

## Forbidden patterns (filtrés à la famille backend)
- Pas de connection string littérale en dur dans le code source
- Pas de WeatherForecastService
- Pas de SQL brut hors Repository
- Pas de lecture d'env var (`Environment.GetEnvironmentVariable`, `System.getenv`, `process.env`, `os.environ`) — depuis 2026-05-14, lecture exclusive via le mécanisme de config natif du framework
- {patterns §5 Interdits du stack backend, condensés}

## Config consommée au runtime (peuplée par arch depuis stack.md)
- DB: section `ConnectionStrings.Default` / `spring.datasource.*` / `db` (config) / `db_settings` selon stack — valeurs issues de ## Active Database de stack.md
- Auth: section `AzureAd` / `azure.ad.*` / `azure.ad` (config) / `azure_settings` — valeurs issues de ## Active Auth Specs de stack.md (si auth actif)

## Notes
- Ce fichier est régénéré à chaque /arch-init (hash invalidé sur stack.md change).
- Source de vérité : `.claude/stacks/backend/{id}.md` + `.claude/stacks/auth/{id}.md` (à relire si CLAUDE.md ne suffit pas pour une décision précise).
