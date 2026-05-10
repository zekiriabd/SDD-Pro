# Tech Spec: minimalapi (backend)

Status: Draft
Tech Spec ID: tech-minimalapi
Scope: backend uniquement (API, logique metier, persistance)

---

## 1. Architecture

### 1.1 Pattern applicatif
Minimal API avec separation stricte :
`Endpoint → Service (via ServiceResolver) → Entity → AutoMapper → DTO → ApiResponse<T>`.
Le wrapper `ApiResponse<T>` porte les metriques de performance (`QueryTime`, `MappingTime`)
et est defini dans le projet librairie partagee `{LibName}`.

### 1.2 Couches

- **Endpoint** : presentation pure (routing, validation d'entree, appel de service). Methodes statiques, mappees dans `Program.cs`.
- **Service** : logique metier. Contrat dans `Services/Interfaces/`, implementation dans `Services/`. Resolution via `ServiceResolver` + DI .NET.
- **Mapper** : profils AutoMapper. Aucun mapping manuel ailleurs.
- **DTO** : structures de transfert (`{LibName}/Inputs`, `{LibName}/Outputs`, `{LibName}/Models`). Immuables.
- **Entity** : modeles persistants generes par EF Core (Database-First). Aucune logique metier.
- **DbContext** : contexte EF Core. Etendu de facon incrementale.

### 1.3 Mapping couche → repertoire
- Endpoint → `workspace/output/src/{BackendName}/Endpoints/`
- Service (interface) → `workspace/output/src/{BackendName}/Services/Interfaces/`
- Service (implementation) → `workspace/output/src/{BackendName}/Services/`
- Mapper → `workspace/output/src/{BackendName}/Mappers/`
- Entity → `workspace/output/src/{BackendName}/Entities/`
- DbContext → `workspace/output/src/{BackendName}/Entities/DBcontext/`
- Input DTO → `workspace/output/src/{LibName}/Inputs/`
- Output DTO → `workspace/output/src/{LibName}/Outputs/`
- Model DTO → `workspace/output/src/{LibName}/Models/`
- Config application → `workspace/output/src/{BackendName}/Program.cs`
- Ressources multilingue `.resx` → `workspace/output/src/{BackendName}/Resources/`
- Project (librairie partagee) → `workspace/output/src/{LibName}/{LibName}.csproj`
- Project (API) → `workspace/output/src/{BackendName}/{BackendName}.csproj`

### 1.4 Principes non negociables
- Aucune logique metier dans les Endpoints.
- Aucune logique metier dans les Entities.
- Aucun mapping manuel dans Endpoints ou Services (centralise dans `Mappers/`).
- DI systematique. Services enregistres dans `Program.cs`.
- Entites generees EF jamais modifiees manuellement (classes partielles sinon).
- Scaffolding EF **incremental** : ne jamais regenerer depuis zero, ne jamais supprimer automatiquement d'entites existantes.
- Gestion des erreurs HTTP via `ProblemDetails` Microsoft uniquement.
- Middleware global centralise pour transformer toute exception non geree en `ProblemDetails` ; pas de `try/catch` de formatage HTTP dans Endpoints ou Services.

---

## 2. Stack

### 2.1 Identite
- **Stack ID** : `back-sim`
- **Langage** : C# 12
- **Runtime** : .NET 10.0 (`net10.0`)
- **Framework principal** : ASP.NET Core 10.0 — Minimal API
- **Namespace racine** : `{BackendNamespace}`

### 2.2 Outils
- **Project file** : `workspace/output/src/{BackendName}/{BackendName}.csproj`
- **Build** : `dotnet build workspace/output/src/{BackendName}/{BackendName}.csproj --nologo` (project-scoped, not solution-wide; allows parallel builds across stacks)
- **Smoke Command** : `dotnet run --project workspace/output/src/{BackendName}/{BackendName}.csproj --no-build --urls http://localhost:5099 & APP_PID=$!; sleep 4; curl -sf http://localhost:5099/api/config/auth -o /dev/null; RC=$?; kill $APP_PID 2>/dev/null; wait $APP_PID 2>/dev/null; exit $RC`
- **Smoke Timeout** : 60s
- **Preserves identifier syntax** : `\b<id>\b` (mot entier, sensible à la casse)
- **Lint / Format** : `dotnet format`
- **Type-check** : integre au build
- **Package manager** : NuGet
- **Test** : hors scope du framework SDD Lite (QA exclu)

### 2.2.1 Init Commands (executes par `init_project.skill.md` si `project_file` absent)

```bash
# Garde-fou idempotent : STEPS 1-3 sont DESTRUCTIVES (`dotnet new --force` ecrase
# Program.cs ; rm -f supprime des fichiers source). Chaque projet est garde
# independamment pour permettre une recuperation partielle (ex. si {LibName} a
# echoue mais {BackendName} a reussi, ne pas rewrite {BackendName}). STEPS 4-9
# (dotnet add reference/package, mkdir -p, restore, build) sont idempotents.

# 1a — Creer {BackendName} (webapi)
if [ ! -f "workspace/output/src/{BackendName}/{BackendName}.csproj" ]; then
dotnet new webapi -n {BackendName} -o workspace/output/src/{BackendName} --framework net10.0 --no-restore --force

# 2 — Supprimer le boilerplate webapi (sous le meme guard que la creation)
rm -f "workspace/output/src/{BackendName}/Controllers/WeatherForecastController.cs"
rm -f "workspace/output/src/{BackendName}/WeatherForecast.cs"
fi  # fin garde {BackendName}

# 1b — Creer {LibName} (classlib)
if [ ! -f "workspace/output/src/{LibName}/{LibName}.csproj" ]; then
dotnet new classlib -n {LibName} -o workspace/output/src/{LibName} --framework net10.0 --no-restore --force

# 3 — Supprimer le boilerplate classlib (sous le meme guard que la creation)
rm -f "workspace/output/src/{LibName}/Class1.cs"
fi  # fin garde {LibName}

# 4 — Reference {LibName} depuis {BackendName}
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj reference workspace/output/src/{LibName}/{LibName}.csproj
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis dotnet-minimalapi.libs.json -- ne pas editer (utiliser sync-stack-md.ps1).
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore --version 10.0.6
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore.SqlServer --version 10.0.6
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore.Design --version 10.0.6
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore.Tools --version 10.0.6
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package AutoMapper --version 16.1.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Serilog.AspNetCore --version 10.0.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Serilog.Sinks.Console --version 6.1.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Swashbuckle.AspNetCore --version 10.1.7
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Swashbuckle.AspNetCore.Annotations --version 10.1.7
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Asp.Versioning.Http --version 8.1.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Asp.Versioning.Mvc.ApiExplorer --version 8.1.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.OpenApi --version 2.4.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.Identity.Web --version 4.9.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package FluentValidation --version 11.11.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package FluentValidation.AspNetCore --version 11.3.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package FluentValidation.DependencyInjectionExtensions --version 11.11.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Polly --version 8.5.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.Extensions.Http.Resilience --version 9.0.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.Extensions.Caching.Memory --version 9.0.0
```
<!-- CORE_PACKAGES_END -->

```bash
# 6 — Packages {LibName} (cross-projet, manuel — hors catalog)
dotnet add workspace/output/src/{LibName}/{LibName}.csproj package AutoMapper --version 16.1.1

# Note Excel + PDF (RETIRES depuis v3.1.3) : installation on-demand uniquement,
# pilotee par dev-backend selon les triggers de l'US courante.
# Voir §2.2.2 (commandes on-demand auto-generees), §2.4.b (catalogue capabilities)
# et agents/dev-backend.md STEP 5.bis (capability detection).
# Forcer l'install au bootstrap : ajouter `Capabilities: excel, pdf` dans
# `## Project Config` de workspace/input/stack/stack.md.

# 7 — Creer l'arborescence des couches {BackendName}
mkdir -p workspace/output/src/{BackendName}/Endpoints
mkdir -p workspace/output/src/{BackendName}/Services/Interfaces
mkdir -p workspace/output/src/{BackendName}/Services
mkdir -p workspace/output/src/{BackendName}/Mappers
mkdir -p workspace/output/src/{BackendName}/Entities/DBcontext
mkdir -p workspace/output/src/{BackendName}/Middleware
mkdir -p workspace/output/src/{BackendName}/Resources
mkdir -p workspace/output/src/{BackendName}/Properties

# 8 — Creer l'arborescence des couches {LibName}
mkdir -p workspace/output/src/{LibName}/Inputs
mkdir -p workspace/output/src/{LibName}/Outputs
mkdir -p workspace/output/src/{LibName}/Models

# 9 — Restaurer + builder les deux projets
dotnet restore workspace/output/src/{BackendName}/{BackendName}.csproj
dotnet restore workspace/output/src/{LibName}/{LibName}.csproj
dotnet build workspace/output/src/{BackendName}/{BackendName}.csproj --nologo
dotnet build workspace/output/src/{LibName}/{LibName}.csproj --nologo
```

**Contrat post-init :**
- `workspace/output/src/{BackendName}/{BackendName}.csproj` DOIT exister et le build DOIT etre vert.
- `workspace/output/src/{LibName}/{LibName}.csproj` DOIT exister et le build DOIT etre vert.
- Les fichiers generes par `dotnet new` conserves (`Program.cs`) seront **augmentes**
  par les agents (operation: augment) avec `preserves:` declarant leurs identifiants
  courants : `builder`, `app`, `MapGet`, `Run`.

### 2.2.2 On-demand install commands (depuis v3.1.3)

Commandes d'installation utilisées **uniquement** par dev-backend en STEP 5.bis
quand un trigger §2.4.b match l'US courante. Format : un bloc bash
par capability, exécuté de manière idempotente (`dotnet add` skippe si
déjà présent). **Choix de lib** (EPPlus vs ClosedXML, QuestPDF vs iText7…) :
voir §2.4.b et `## Capabilities Override` dans le Project Config pour
piloter l'alternative.

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis dotnet-minimalapi.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: excel
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package EPPlus --version 7.5.3
# OU (alt mutuellement exclusif) : dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package ClosedXML --version 0.104.2

# capability: pdf
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package QuestPDF --version 2024.12.3
# OU (alt mutuellement exclusif) : dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package itext7 --version 9.0.0

# capability: cqrs
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package MediatR --version 12.4.1

# capability: redis-cache
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package StackExchange.Redis --version 2.8.16
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.Extensions.Caching.StackExchangeRedis --version 9.0.0

# capability: fast-mapping
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Mapster --version 7.4.0
```
<!-- ONDEMAND_PACKAGES_END -->

**Forçage au bootstrap** : pour pré-installer une capability dès `/arch-init`,
ajouter dans `## Project Config` de `workspace/input/stack/stack.md` :
```
Capabilities: excel, pdf
```
Dans ce cas, arch installera ces libs en Phase A même si aucune US ne les
référence (utile pour les projets dont ces capabilities sont garanties
features futures).

### 2.3 Patterns d'erreurs compilation
Format standard .NET : `{file}({line},{col}): error {code}: {message}`.
Codes prioritaires : CS0246, CS0103, CS1061, CS1002, CS1003, CS1513, CS0029, CS0266, CS0161, CS7036.

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/backend/dotnet-minimalapi.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/scripts/sync-stack-md.ps1 -StackId dotnet-minimalapi`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Microsoft.EntityFrameworkCore | 10.0.6 |  |
| Microsoft.EntityFrameworkCore.SqlServer | 10.0.6 |  |
| Microsoft.EntityFrameworkCore.Design | 10.0.6 |  |
| Microsoft.EntityFrameworkCore.Tools | 10.0.6 |  |
| AutoMapper | 16.1.1 |  |
| Serilog.AspNetCore | 10.0.0 |  |
| Serilog.Sinks.Console | 6.1.1 |  |
| Swashbuckle.AspNetCore | 10.1.7 |  |
| Swashbuckle.AspNetCore.Annotations | 10.1.7 |  |
| Asp.Versioning.Http | 8.1.1 |  |
| Asp.Versioning.Mvc.ApiExplorer | 8.1.1 |  |
| Microsoft.OpenApi | 2.4.1 |  |
| Microsoft.Identity.Web | 4.9.0 |  |
| FluentValidation | 11.11.0 |  |
| FluentValidation.AspNetCore | 11.3.1 |  |
| FluentValidation.DependencyInjectionExtensions | 11.11.0 |  |
| Polly | 8.5.1 |  |
| Microsoft.Extensions.Http.Resilience | 9.0.0 |  |
| Microsoft.Extensions.Caching.Memory | 9.0.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect-capabilities.ps1` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| excel | EPPlus | 7.5.3 | \bexcel\b, \.xlsx\b, export.*excel, import.*excel, tableur |
| excel | ClosedXML (alt) | 0.104.2 | \bexcel\b, \.xlsx\b, export.*excel, import.*excel, tableur |
| pdf | QuestPDF | 2024.12.3 | \bpdf\b, \.pdf\b, export.*pdf, generer.*pdf, imprim |
| pdf | itext7 (alt) | 9.0.0 | \bpdf\b, \.pdf\b, export.*pdf, generer.*pdf, imprim |
| cqrs | MediatR | 12.4.1 | \bcqrs\b, mediatr, command.*handler, query.*handler |
| redis-cache | StackExchange.Redis | 2.8.16 | \bredis\b, cache distribu, distributed cache |
| redis-cache | Microsoft.Extensions.Caching.StackExchangeRedis | 9.0.0 | \bredis\b, cache distribu, distributed cache |
| fast-mapping | Mapster | 7.4.0 | mapster\b, mapping perf, high.?performance.*mapp |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| sqlserver | `Microsoft.EntityFrameworkCore.SqlServer` | 10.0.6 | runtime |
<!-- LIBS_CATALOG_END -->

### 2.5 Conventions de nommage
- Classes / proprietes : `PascalCase`
- Variables / parametres : `camelCase`
- Constantes : `PascalCase`
- Champs prives : `_camelCase`
- Fichiers : `PascalCase.cs`
- Interfaces : `IPascalCase`
- DTO Input : suffixe `InputDto`
- DTO Output : suffixe `OutputDto` ou `OutputLiteDto`
- DTO avec relations : suffixe `LiaisonReadDto`

### 2.6 Conventions URL des endpoints (LOAD-BEARING — front/back contract)

**Format canonique obligatoire** :

```
/api/v{N}/{resource-kebab-case}[/{id:type}][/{sub-resource-kebab-case}]
```

**Regles strictes** :

- **Prefixe** `/api/` toujours. Pas de variante (`/v1/api/...`, `/rest/...`).
- **Versioning** `/v{N}/` toujours present (default `v1`). Mappe via
  `MapGroup("/api/v1").RequireAuthorization()` quand applicable.
- **Resource** en **kebab-case-pluriel** : `points-de-vente`,
  `users`, `referentiels`, `audit-logs`. **Jamais** :
  - `pointsvente` (mots colles)
  - `pointDeVente` (camelCase)
  - `PointsDeVente` (PascalCase)
  - `point-de-vente` (singulier)
- **Id segment** typed : `{id:int}`, `{id:guid}`, etc.
- **Sub-resource** en kebab-case : `/api/v1/points-de-vente/{id:int}/exploitations`.
- **Pas d'endpoint `/count`, `/exists`, `/exists/{id}`** : le total
  est exposé via `PagedOutput.TotalCount` retourne par le GET liste,
  l'existence via `404` du GET by id. Toute exception (besoin d'un
  count sans charger la page) doit faire l'objet d'un ADR.
- **Verbe HTTP standard** : `GET` liste/detail, `POST` create, `PUT`
  update full, `PATCH` update partiel (rare), `DELETE` supprime.
  Aucun verbe custom dans l'URL (`/api/v1/points-de-vente/create`
  INTERDIT — utiliser `POST /api/v1/points-de-vente`).

**Pourquoi load-bearing** : le frontend (Refit, axios, fetch) consomme
ces routes par contrat. Toute deviation cote backend (ex.
`/api/pointsvente` au lieu de `/api/v1/points-de-vente`) provoque des
404 silencieux runtime, build vert mais bug visible seulement a
l'usage. Cette convention est **mecaniquement appliquee par les deux
agents** (`dev-backend` quand il `Map*`, `dev-frontend` quand il
declare son client) — la coherence n'est plus laissee a
l'interpretation de l'US.

**Pattern de mapping canonique** :

```csharp
public static class PointsDeVenteEndpoints
{
    public static void Map(WebApplication app)
    {
        var group = app.MapGroup("/api/v1/points-de-vente")
                       .RequireAuthorization()
                       .WithTags("PointsDeVente");

        group.MapGet("/",            GetPaged);             // liste paginee + TotalCount
        group.MapGet("/{id:int}",    GetById);              // detail
        group.MapPost("/",           Create);
        group.MapPut("/{id:int}",    Update);
        group.MapDelete("/{id:int}", Delete);
    }
}
```

**Anti-pattern (corrige post-mortem 2026-05-07)** :
```csharp
// FAUX — pas de versioning, mots colles, .Map sur app au lieu de groupe
app.MapGet("/api/pointsvente", GetPointsVente);
app.MapGet("/api/pointsvente/{id:int}", GetById);
// ...
```

Cote dev-frontend : avant tout client HTTP, grep le code backend pour
verifier la signature exacte (cf. `responsibilities.md §12`).

---

## 3. Base de donnees

- **Moteur** : Microsoft SQL Server
- **Acces** : Entity Framework Core, approche Database-First, scaffolding incremental
- **Migrations** : `dotnet ef dbcontext scaffold` en mode continuation
- **DbContext** : `OperationsDbContext` dans `workspace/output/src/{BackendName}/Entities/DBcontext/`
- **Strategie de scaffolding** : verifier les entites existantes, generer uniquement les tables manquantes, etendre le DbContext avec les nouveaux `DbSet`, conserver les configurations existantes.
- **Tables initiales** : `point_vente` (liste incrementale).
- **Variables d'environnement requises** (conformes a `.claude/rules/env_rules.md`) :
  `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

La chaine de connexion est construite au runtime a partir de ces variables.
Aucune valeur en dur, aucun fichier de configuration secret. Fail-fast au demarrage.

### 3.1 Commandes de scaffolding EF Core

Lire `DatabaseType` dans `workspace/input/tech/stack.md ## Project Config` et executer
la commande correspondante. **Toutes les valeurs de connexion proviennent
exclusivement des variables d'environnement — jamais en dur.**

Resoudre les placeholders `{BackendName}`, `{BackendNamespace}` depuis
`## Project Config` avant d'executer.

#### SQLServer (`DatabaseType: SQLServer`)

```bash
# Prerequis : Microsoft.EntityFrameworkCore.SqlServer deja declare en §2.4
CONN="Server=${DB_HOST},${DB_PORT};Database=${DB_NAME};User Id=${DB_USER};Password=${DB_PASSWORD};Encrypt=False;TrustServerCertificate=True;"

dotnet ef dbcontext scaffold "$CONN" \
  Microsoft.EntityFrameworkCore.SqlServer \
  --project workspace/output/src/{BackendName}/{BackendName}.csproj \
  --context OperationsDbContext \
  --context-dir Entities/DBcontext \
  --output-dir Entities \
  --namespace {BackendNamespace}.Entities \
  --context-namespace {BackendNamespace}.Entities.DBcontext \
  --no-onconfiguring \
  --force \
  --no-build
```

#### PostgreSQL (`DatabaseType: PostgreSQL`)

```bash
# Prerequis : ajouter le package si absent
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj \
  package Npgsql.EntityFrameworkCore.PostgreSQL --version 9.0.4

CONN="Host=${DB_HOST};Port=${DB_PORT};Database=${DB_NAME};Username=${DB_USER};Password=${DB_PASSWORD};"

dotnet ef dbcontext scaffold "$CONN" \
  Npgsql.EntityFrameworkCore.PostgreSQL \
  --project workspace/output/src/{BackendName}/{BackendName}.csproj \
  --context OperationsDbContext \
  --context-dir Entities/DBcontext \
  --output-dir Entities \
  --namespace {BackendNamespace}.Entities \
  --context-namespace {BackendNamespace}.Entities.DBcontext \
  --no-onconfiguring \
  --force \
  --no-build
```

#### MySQL (`DatabaseType: MySQL`)

```bash
# Prerequis : ajouter le package si absent
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj \
  package Pomelo.EntityFrameworkCore.MySql --version 9.0.0

CONN="Server=${DB_HOST};Port=${DB_PORT};Database=${DB_NAME};Uid=${DB_USER};Pwd=${DB_PASSWORD};"

dotnet ef dbcontext scaffold "$CONN" \
  Pomelo.EntityFrameworkCore.MySql \
  --project workspace/output/src/{BackendName}/{BackendName}.csproj \
  --context OperationsDbContext \
  --context-dir Entities/DBcontext \
  --output-dir Entities \
  --namespace {BackendNamespace}.Entities \
  --context-namespace {BackendNamespace}.Entities.DBcontext \
  --no-onconfiguring \
  --force \
  --no-build
```

**Regles de scaffolding incremental (non negociables) :**
- `--no-onconfiguring` : TOUJOURS. Evite que le mot de passe soit ecrit dans le DbContext genere.
- `--force` : regenere les entites existantes (surcharge). Ne supprime pas les entites de tables hors scope.
- Ne JAMAIS regenerer la totalite du schema depuis zero. Scaffolder uniquement les tables nouvelles ou modifiees.
- Ne JAMAIS supprimer manuellement un fichier Entity genere existant.
- Apres scaffold, verifier que `OperationsDbContext` declare un `DbSet<T>` pour chaque nouvelle entite.
- Les entites generees sont dans `Entities/` — ne pas modifier directement ; utiliser des classes partielles si extension necessaire.

---

## 4. Versioning des API
- Version par defaut : `v1.0`
- Format URL : `/api/v{version}/...`
- Lecteur : `UrlSegmentApiVersionReader`
- Header `api-supported-versions` active dans les reponses.

---

## 5. Swagger + bouton Authorize JWT

Le SwaggerGen DOIT etre configure avec :

- `SecurityDefinition("Bearer")` de type `Http` / scheme `bearer` / `bearerFormat: JWT` / `In: Header`
- `SecurityRequirement` global referencant ce `Bearer`
- `EnableAnnotations()`

Effet : bouton **Authorize** dans l'UI Swagger ; le developpeur y colle un
token obtenu via la pile d'authentification (voir `tech-auth-azure.md`) ;
toutes les requetes partent avec `Authorization: Bearer <token>`.

**Contraintes Microsoft.OpenApi 2.x (vs 1.x)** :

- `using Microsoft.OpenApi;` (le namespace `Microsoft.OpenApi.Models` a disparu en 2.4+).
- `new OpenApiSecuritySchemeReference("Bearer")` (plus d'`OpenApiReference`).
- Valeur de scope : `new List<string>()` (pas `Array.Empty<string>()`).
- `AddSecurityRequirement(Func<OpenApiDocument, OpenApiSecurityRequirement>)` → envelopper dans `_ => new OpenApiSecurityRequirement { ... }`.
- Reference explicite `Microsoft.OpenApi` dans le `.csproj` (non expose publiquement par Swashbuckle 10.x).

Pattern complet **canonique** (post-mortem 2026-05-03 — eviter
`CS0234 Microsoft.OpenApi.Models n'existe pas`) :

```csharp
using Microsoft.OpenApi;          // PAS Microsoft.OpenApi.Models

builder.Services.AddSwaggerGen(options =>
{
    options.EnableAnnotations();
    options.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Name = "Authorization",
        In = ParameterLocation.Header,
        Type = SecuritySchemeType.Http,
        Scheme = "bearer",
        BearerFormat = "JWT"
    });
    options.AddSecurityRequirement(_ => new OpenApiSecurityRequirement
    {
        { new OpenApiSecuritySchemeReference("Bearer"), new List<string>() }
    });
});
```

Anti-patterns rejetes (declenchent CS0234) :
- `new Microsoft.OpenApi.Models.OpenApiSecurityScheme { ... }` (Models n'existe plus)
- `new OpenApiReference { Type = ReferenceType.SecurityScheme, Id = "Bearer" }` (remplace par `OpenApiSecuritySchemeReference`)

Les details de l'audience attendue, du schema de validation et des claims
exploites sont dans `tech-auth-azure.md`.

---

## 5.1 Connection string SQL Server — construction (post-mortem 2026-05-03)

La construction de la chaine de connexion DOIT passer par
`Microsoft.Data.SqlClient.SqlConnectionStringBuilder`. La concatenation
litterale `$"Server={...};User Id={...};Password={...};"` declenche le
pattern forbidden-scan `(server|host)=...;user id=...;password=...` qui
detecte les chaines de connexion en dur et bloque le commit (cf.
`.claude/scripts/validate-batch.ps1 -Mode incremental` + `env_rules.md`).

Pattern canonique :

```csharp
using Microsoft.Data.SqlClient;

string Required(string n) => Environment.GetEnvironmentVariable(n)
    ?? throw new InvalidOperationException($"Missing required environment variable: {n}");

var sqlBuilder = new SqlConnectionStringBuilder
{
    DataSource           = $"{Required("DB_HOST")},{Required("DB_PORT")}",
    InitialCatalog       = Required("DB_NAME"),
    UserID               = Required("DB_USER"),
    Password             = Required("DB_PASSWORD"),
    Encrypt              = false,
    TrustServerCertificate = true
};
var connectionString = sqlBuilder.ConnectionString;

builder.Services.AddDbContext<OperationsDbContext>(o => o.UseSqlServer(connectionString));
```

Aucun litteral `Server=...` n'apparait dans le code source : le builder
serialise la chaine au runtime, le scanner ne matche rien, l'env_rules.md
reste respecte.

Anti-pattern rejete par forbidden-scan :
```csharp
// INTERDIT - declenche [DERIVE_VIOLATION] [env_rules.md]
var connectionString = $"Server={dbHost},{dbPort};Database={dbName};User Id={dbUser};Password={dbPassword};Encrypt=False;TrustServerCertificate=True;";
```

---

## 6. Multilingue
Parametre de requete optionnel `langue`. Traductions dans
`workspace/output/src/{BackendName}/Resources/` (fichiers `.resx`), resolution via
`IStringLocalizer` / `IHtmlLocalizer`.

---

## 7. CORS developpement
Conforme a `.claude/rules/cors.md`. Policy `DevOpen` avec
`AllowAnyOrigin() / AllowAnyMethod() / AllowAnyHeader()`. `app.UseCors("DevOpen")`
**avant** `UseAuthentication()` et `UseAuthorization()`. Pas d'`AllowCredentials`.
Durcissement staging / prod couvert par une future regle de securite.

---

## 8. URLs de developpement
- HTTPS : `https://localhost:44328` (aligne avec `Api:BaseAddress` du frontend → voir `tech-blazor.md`)
- OpenAPI (dev) : `https://localhost:44328/swagger`

`workspace/output/src/{BackendName}/Properties/launchSettings.json` pin cette URL. Tout changement
DOIT etre reporte dans `Api:BaseAddress` du frontend.

---

## 9. Interdits projet (backend)

- Secrets, cles d'API, mots de passe en dur
- Chaines de connexion litterales (cle/valeur ou URI)
- Hotes litteraux (`localhost`, IP) lies au host BDD dans un Service
- Lecture de credentials BDD depuis un fichier (`.env`, `appsettings*.json` secrets, etc.)
- Logique metier dans les Entities ou les Endpoints
- Mapping manuel dans Endpoints ou Services
- Modification manuelle des Entities generees par EF (classes partielles sinon)
- Suppression automatique d'entites EF existantes
- Regeneration complete des Entities depuis zero
- Ecrasement d'un DbSet existant du DbContext lors d'une mise a jour de scaffolding
- Exception brute exposee au client (toujours `ProblemDetails`)
- Log de `DB_PASSWORD` ou de la chaine de connexion complete
- `dynamic` / `object` non justifie
- Appels statiques a des librairies a effet de bord depuis un Service
- `TODO`, `FIXME`, code commente, placeholders (`TBD`, `changeme`, `foo`, `bar`)
- `try/catch` de formatage HTTP dans Endpoints ou Services (role exclusif du middleware global)
- Backend API sans policy CORS `DevOpen` activee avant `UseAuthentication` (voir §7)
- `AddSwaggerGen` sans `SecurityDefinition("Bearer")` + `SecurityRequirement` sur une API protegee
- URL backend `launchSettings.json` differente de `Api:BaseAddress` frontend

---

## 10. Recommended Skills (auto-trigger pendant la generation)

Skills Claude Code disponibles invoquees via le tool `Skill` AVANT
generation quand le trigger matche. Ces skills sont **guidance technique** —
elles n'autorisent JAMAIS l'expansion de scope au-dela de la task / spec /
stack (voir `.claude/rules/stack-completeness.md`). Toute librairie
recommandee par une skill mais non listee en §2.4 reste interdite.

| Trigger (detecte dans la task ou les ACs) | Skill | Phase |
|---|---|---|
| Endpoint multipart / upload de fichier (`IFormFile`, `IFormFileCollection`, `multipart/form-data`) | `dotnet-aspnet:minimal-api-file-upload` | STEP 5 (avant ecriture de l'Endpoint) |
| OpenTelemetry / observability (traces, metrics, logs OTLP) si l'US le demande explicitement | `dotnet-aspnet:configuring-opentelemetry-dotnet` | STEP 5 (avant Program.cs middleware) |

**Interdits** :
- Ne jamais invoquer une skill non listee dans le system des skills Claude Code disponibles.
- Ne jamais ajouter un package NuGet recommande par une skill si absent de §2.4 — le suggerer dans la "Remarque" finale (cf. politique librairies inlined dans `agents/arch.md`) au lieu de l'installer.

---

## 8. Persistence (cross-DatabaseType)

Sections lues par l'agent `arch` (Phase A pour installer le bon
provider, Phase B pour composer la connection string et invoquer le
scaffolding).

### 8.1 DB Drivers — matrice DatabaseType → NuGet Provider

| DatabaseType  | NuGet Provider                                    | Version target |
|---------------|---------------------------------------------------|----------------|
| `SqlServer`   | `Microsoft.EntityFrameworkCore.SqlServer`         | 10.0.6 (pinned) |
| `PostgreSQL`  | `Npgsql.EntityFrameworkCore.PostgreSQL`           | non-pinned (suit CVE) |
| `MySql`       | `Pomelo.EntityFrameworkCore.MySql`                | non-pinned (suit CVE) |
| `Sqlite`      | `Microsoft.EntityFrameworkCore.Sqlite`            | 10.0.6 (pinned) |

Les packages communs `Microsoft.EntityFrameworkCore`,
`Microsoft.EntityFrameworkCore.Design`, `Microsoft.EntityFrameworkCore.Tools`
restent installés quel que soit le DatabaseType (déjà en §2.4).

Arch Phase A lit `## Project Config: DatabaseType` puis installe le
provider correspondant via `dotnet add package` :
```bash
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package <Provider>
```

### 8.2 Connection String Pattern

| DatabaseType  | Builder C# canonique                              | Pattern de référence |
|---------------|---------------------------------------------------|----------------------|
| `SqlServer`   | `Microsoft.Data.SqlClient.SqlConnectionStringBuilder` | DataSource=`{HOST},{PORT}`, InitialCatalog, UserID, Password, Encrypt=false, TrustServerCertificate=true |
| `PostgreSQL`  | `Npgsql.NpgsqlConnectionStringBuilder`            | Host, Port, Database, Username, Password |
| `MySql`       | `MySqlConnector.MySqlConnectionStringBuilder`     | Server, Port, Database, UserID, Password |
| `Sqlite`      | `Microsoft.Data.Sqlite.SqliteConnectionStringBuilder` | DataSource (chemin fichier — autres env vars ignorées) |

Aucune concaténation littérale `$"Server=...;..."` autorisée — viole
le scan forbidden-pattern de `env_rules.md`.

Code template (cas SqlServer — le plus fréquent) :
```csharp
using Microsoft.Data.SqlClient;

string Required(string n) => Environment.GetEnvironmentVariable(n)
    ?? throw new InvalidOperationException($"Missing required environment variable: {n}");

var sqlBuilder = new SqlConnectionStringBuilder
{
    DataSource           = $"{Required("DB_HOST")},{Required("DB_PORT")}",
    InitialCatalog       = Required("DB_NAME"),
    UserID               = Required("DB_USER"),
    Password             = Required("DB_PASSWORD"),
    Encrypt              = false,
    TrustServerCertificate = true
};
var connectionString = sqlBuilder.ConnectionString;
```

Pour PostgreSQL, MySql, Sqlite : substituer le builder ci-dessus par
celui de §8.2 ; les noms de propriétés diffèrent.

### 8.3 Scaffolding tool (Database-First)

Outil canonique : **`dotnet ef dbcontext scaffold`** (toolchain
`Microsoft.EntityFrameworkCore.Design` + `Microsoft.EntityFrameworkCore.Tools`).

Pattern d'invocation par Arch Phase B :
```bash
dotnet ef dbcontext scaffold "<connstr>" <ProviderAssembly> \
  --project workspace/output/src/{BackendName}/{BackendName}.csproj \
  --output-dir Entities \
  --context-dir Entities/DBcontext \
  --context AppDbContext \
  --namespace {AppNamespace}.Entities \
  --context-namespace {AppNamespace}.Entities.DBcontext \
  --use-database-names \
  --no-pluralize \
  --force \
  [--table T1 --table T2 ...]    # si DB Scaffolding Mode=list dans stack.md
```

`<ProviderAssembly>` correspond au provider §8.1 :
- SqlServer : `Microsoft.EntityFrameworkCore.SqlServer`
- PostgreSQL : `Npgsql.EntityFrameworkCore.PostgreSQL`
- MySql : `Pomelo.EntityFrameworkCore.MySql`
- Sqlite : `Microsoft.EntityFrameworkCore.Sqlite`

Le `--force` est incrémental : il écrase uniquement les classes
auto-générées, préserve les `partial class` adjacentes.

---
