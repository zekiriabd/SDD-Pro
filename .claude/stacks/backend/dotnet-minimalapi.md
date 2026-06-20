# Tech FEAT: minimalapi (backend)

> §2.4 (Librairies) régénérée depuis `dotnet-minimalapi.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id dotnet-minimalapi`).

Status: Stable
Validation: 🟢 reference (validated combo — dotnet-minimalapi + blazor + radzen + azure-ad + dotnet-xunit + blazor-bunit)
Tech FEAT ID: tech-minimalapi
Scope: backend uniquement (API, logique metier, persistance)

---

## 1. Architecture

> **Pattern d'architecture** : ce stack suit l'**architecture canonique** definie dans
> `.claude/stacks/archi/{ArchiPattern}.md` (defaut `MVC` si `## Active Architecture Pattern`
> absent du `stack.md`). Section §1 ci-dessous ne decrit QUE les overrides .NET-specific.

### 1.1 Pattern applicatif (.NET Minimal API idioms)

Pour `ArchiPattern: MVC` (defaut), suit `archi/mvc.md` avec idioms ASP.NET Core 10 Minimal API :
- **Endpoint** = method statique mappee via `MapGroup("/api/v1/...")` dans `Program.cs` (pas de classe Controller — Minimal API delivere les handlers statiques)
- **Service** = interface `I{Name}Service` + impl concrete enregistree via `AddScoped<,>()` dans `Program.cs`
- **AutoMapper** centralise via `Profile` classes pour mapping Entity ↔ DTO
- **DTO** immuables (records C# 9+ `public record XxxOutput(...)` ou classes avec `init`)
- **`ApiResponse<T>`** wrapper standard (status, data, queryTime, mappingTime, errors) defini dans projet `{LibName}` partage
- **EF Core Database-First** : entites generees via `dotnet ef dbcontext scaffold`, jamais modifiees manuellement (classes partielles sinon)
- **ProblemDetails** RFC 7807 via middleware global pour toute exception non geree

Pour `ArchiPattern: DDD` → voir `archi/ddd.md` (Aggregates + UseCases via MediatR — capability `cqrs`).
Pour `ArchiPattern: microservice` → voir `archi/microservice.md` (Polly + OpenTelemetry + Refit en CORE).

### 1.3 Mapping couche → repertoire (override .NET)

| Couche canonique (archi/mvc.md §3) | Path .NET Minimal API |
|---|---|
| Endpoint | `workspace/output/src/{BackendName}/Endpoints/` (static methods, `MapGroup`) |
| Service (interface) | `workspace/output/src/{BackendName}/Services/Interfaces/` |
| Service (implementation) | `workspace/output/src/{BackendName}/Services/` |
| Mapper | `workspace/output/src/{BackendName}/Mappers/` (AutoMapper `Profile`) |
| Entity | `workspace/output/src/{BackendName}/Entities/` (`@Entity`-like — EF Core scaffolde) |
| DbContext | `workspace/output/src/{BackendName}/Entities/DBcontext/` |
| Input DTO | `workspace/output/src/{LibName}/Inputs/` |
| Output DTO | `workspace/output/src/{LibName}/Outputs/` |
| Model DTO | `workspace/output/src/{LibName}/Models/` |
| Validators FluentValidation | `workspace/output/src/{BackendName}/Validators/` |
| Middleware | `workspace/output/src/{BackendName}/Middleware/` |
| App entry | `workspace/output/src/{BackendName}/Program.cs` |
| Ressources multilingue | `workspace/output/src/{BackendName}/Resources/` (`.resx`) |
| Project (API) | `workspace/output/src/{BackendName}/{BackendName}.csproj` |
| Project (Lib partagee) | `workspace/output/src/{LibName}/{LibName}.csproj` |
| Solution | `workspace/output/src/{AppName}.sln` |

### 1.4 Override principes (.NET-specific)

Herites de `archi/mvc.md §4`. **Ajouts** .NET :
- **Constructor injection primary** (C# 12 syntax : `public class XxxService(IRepo r, IMapper m) { ... }`)
- **DTOs immuables** via `record` C# 9+ ou classes avec `init` setters
- **EF Core scaffolding incremental** : `dotnet ef dbcontext scaffold` avec `--no-onconfiguring --force`, JAMAIS regen depuis zero
- **AutoMapper Profile** : un Profile par domaine metier (`UsersProfile : Profile`)
- **FluentValidation** pour validation Input DTOs (registered via `AddValidatorsFromAssembly`)
- **Async Task<T>** partout (jamais `.Result`, `.Wait()`, `void` async hors event handlers)
- **ProblemDetails Microsoft** uniquement pour reponses d'erreur (RFC 7807)
- **Pas de `dynamic` ni `object`** injustifie dans signatures publiques

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
# Auto-genere depuis dotnet-minimalapi.libs.json -- ne pas editer (utiliser sync_stack_md.py).
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore --version 9.0.4
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore.Design --version 9.0.4
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.EntityFrameworkCore.Tools --version 9.0.4
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.AspNetCore.OpenApi --version 9.0.4
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package AutoMapper --version 16.1.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Serilog.AspNetCore --version 9.0.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Serilog.Sinks.Console --version 6.1.1
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Swashbuckle.AspNetCore --version 9.0.4
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Swashbuckle.AspNetCore.Annotations --version 9.0.4
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

# capability: email
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package MailKit --version 4.8.0
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package MimeKit --version 4.8.0

# capability: auth-local
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package BCrypt.Net-Next --version 4.0.3
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package Microsoft.AspNetCore.Authentication.JwtBearer --version 9.0.4
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

> Source de verite : `.claude/stacks/backend/dotnet-minimalapi.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id dotnet-minimalapi`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Microsoft.EntityFrameworkCore | 9.0.4 |  |
| Microsoft.EntityFrameworkCore.Design | 9.0.4 |  |
| Microsoft.EntityFrameworkCore.Tools | 9.0.4 |  |
| Microsoft.AspNetCore.OpenApi | 9.0.4 |  |
| AutoMapper | 16.1.1 |  |
| Serilog.AspNetCore | 9.0.0 |  |
| Serilog.Sinks.Console | 6.1.1 |  |
| Swashbuckle.AspNetCore | 9.0.4 |  |
| Swashbuckle.AspNetCore.Annotations | 9.0.4 |  |
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

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| excel | EPPlus | 7.5.3 | excel, \.xlsx, export.*excel, import.*excel, tableur |
| excel | ClosedXML (alt) | 0.104.2 | excel, \.xlsx, export.*excel, import.*excel, tableur |
| pdf | QuestPDF | 2024.12.3 | pdf, \.pdf, export.*pdf, generer.*pdf, imprim |
| pdf | itext7 (alt) | 9.0.0 | pdf, \.pdf, export.*pdf, generer.*pdf, imprim |
| cqrs | MediatR | 12.4.1 | cqrs, mediatr, command.*handler, query.*handler |
| redis-cache | StackExchange.Redis | 2.8.16 | redis, cache distribu, distributed cache |
| redis-cache | Microsoft.Extensions.Caching.StackExchangeRedis | 9.0.0 | redis, cache distribu, distributed cache |
| fast-mapping | Mapster | 7.4.0 | mapster, mapping perf, high.?performance.*mapp |
| email | MailKit | 4.8.0 | smtp, envoi.*email, envoi.*courriel, send.*email, email.*notification, notification.*par.*email, mail.*confirmation, verifier.*email |
| email | MimeKit | 4.8.0 | smtp, envoi.*email, envoi.*courriel, send.*email, email.*notification, notification.*par.*email, mail.*confirmation, verifier.*email |
| auth-local | BCrypt.Net-Next | 4.0.3 | bcrypt, password.*hash, hash.*password, motdepasse.*hash, mot.*passe.*hash, auth-local, password_hash, verify.*password, connexion.*mot.*passe, inscription, register.*user |
| auth-local | Microsoft.AspNetCore.Authentication.JwtBearer | 9.0.4 | jwt, jsonwebtoken, bearer.*token, auth-local, issue.*token, verify.*token, validate.*token, jwt.*authent, token.*authent, authorize.*attribute, \[Authorize\] |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| sqlserver | `Microsoft.EntityFrameworkCore.SqlServer` | 9.0.4 | runtime |
| postgres | `Npgsql.EntityFrameworkCore.PostgreSQL` | 9.0.4 | runtime |
| postgresql | `Npgsql.EntityFrameworkCore.PostgreSQL` | 9.0.4 | runtime |
| mysql | `Pomelo.EntityFrameworkCore.MySql` | 9.0.0 | runtime |
| mariadb | `Pomelo.EntityFrameworkCore.MySql` | 9.0.0 | runtime |
| sqlite | `Microsoft.EntityFrameworkCore.Sqlite` | 9.0.4 | runtime |
| oracle | `Oracle.EntityFrameworkCore` | 9.23.60 | runtime |
| mongodb | `MongoDB.EntityFrameworkCore` | 9.0.0 | runtime |
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
verifier la signature exacte (anti-pattern `[FRONTEND_BACKEND_CONTRACT_GAP]`).

---

## 3. Base de donnees

- **Moteur** : déterminé par `DatabaseType` dans `## Active Database` de
  `workspace/input/stack/stack.md` (cf. §3.0 matrice).
- **Acces** : Entity Framework Core, approche Database-First, scaffolding
  incremental.
- **Migrations** : `dotnet ef dbcontext scaffold` en mode continuation.
- **DbContext** : `OperationsDbContext` dans
  `workspace/output/src/{BackendName}/Entities/DBcontext/`.
- **Strategie de scaffolding** : verifier les entites existantes, generer
  uniquement les tables manquantes, etendre le DbContext avec les
  nouveaux `DbSet`, conserver les configurations existantes.
- **Source des valeurs DB** (depuis 2026-05-14) : bloc
  `## Active Database` de `stack.md` (cles `DatabaseType`, `DB_HOST`,
  `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`). Le Tech Lead renseigne
  ces valeurs en env vars. L'agent `arch` Phase A STEP 4.5 :
  1. Installe **uniquement le driver EF Core matchant `DatabaseType`**
     (cf. §3.0) — pas les autres.
  2. Génère le bloc d'assemblage `ConnectionStrings:Default` depuis les
     env vars `DB_*` dans `Program.cs` (cf. §5.1).
- La chaine de connexion est assemblée au boot dans `Program.cs` puis
  lue via `IConfiguration` (`builder.Configuration.GetConnectionString("Default")`).
  Aucune valeur en dur dans `appsettings.json`, aucun secret commit.

### 3.0 Matrice DatabaseType → Driver EF Core (sélection arch STEP 4)

**Source canonique** : `dotnet-minimalapi.libs.json` `dbDrivers` (catalogue
machine, lu par arch). Tableau de référence humain ci-dessous, à jour
2026-05-22 (post-mortem version mismatch NU1608 → MissingMethodException
runtime ; pin actuel EF Core 9.0.4 aligné avec Npgsql.EF 9.0.4 — cf. audit
CRIT-6 closure 2026-06-07 et `libs.json` changelog "revert 10.0.0→9.0.4" pour
compat Npgsql 9.x preview) :

| `DatabaseType` | Package NuGet à installer | `Use{X}` extension | Version |
|---|---|---|---:|
| `sqlserver` | `Microsoft.EntityFrameworkCore.SqlServer` | `UseSqlServer` | 9.0.4 |
| `postgres` / `postgresql` | `Npgsql.EntityFrameworkCore.PostgreSQL` | `UseNpgsql` | 9.0.4 |
| `mysql` | `Pomelo.EntityFrameworkCore.MySql` | `UseMySql` | 9.0.0 |
| `mariadb` | `Pomelo.EntityFrameworkCore.MySql` | `UseMySql` | 9.0.0 |
| `sqlite` | `Microsoft.EntityFrameworkCore.Sqlite` | `UseSqlite` | 9.0.4 |
| `oracle` | `Oracle.EntityFrameworkCore` | `UseOracle` | 9.23.60 |
| `mongodb` | `MongoDB.EntityFrameworkCore` | `UseMongoDB` | 9.0.0 |
| `none` | (aucun — pas de DbContext scaffold) | — | — |

> **Règle load-bearing v7.0.0** : `Microsoft.EntityFrameworkCore` et
> `Microsoft.EntityFrameworkCore.Design`/`Tools` sont pinnés **9.0.4**
> (LCD compatible avec tous les drivers ci-dessus). Tant que
> `Npgsql.EntityFrameworkCore.PostgreSQL` n'a pas de release stable 10.x,
> ne PAS bumper EF Core à 10.x — déclenche `NU1608` warning + `MissingMethodException`
> runtime au premier accès `DbSet`. Cf. post-mortem CMSPrint 2026-05-22.

**Anti-pattern (corrigé 2026-05-22)** :
- ❌ `core[]` contenait `Microsoft.EntityFrameworkCore.SqlServer` hardcodé,
  installé même pour `DatabaseType: postgres`. Pollution csproj + risque
  de drift de driver.
- ✅ `core[]` ne contient désormais que `Microsoft.EntityFrameworkCore` +
  `Design` + `Tools`. Le driver spécifique vient de `dbDrivers[DatabaseType]`.

### 3.1 Procédure arch STEP 4 — installation conditionnelle driver

```bash
# 1. Lire DatabaseType depuis stack.md ## Active Database
DB_TYPE=$(grep -oE 'DatabaseType:\s*\S+' workspace/input/stack/stack.md | awk '{print tolower($2)}')

# 2. Lookup dans dbDrivers du libs.json
DRIVER_MODULE=$(jq -r ".dbDrivers.\"$DB_TYPE\".module" .claude/stacks/backend/dotnet-minimalapi.libs.json)
DRIVER_VERSION_REF=$(jq -r ".dbDrivers.\"$DB_TYPE\".ref" .claude/stacks/backend/dotnet-minimalapi.libs.json)
DRIVER_VERSION=$(jq -r ".versions.\"$DRIVER_VERSION_REF\"" .claude/stacks/backend/dotnet-minimalapi.libs.json)

# 3. Si DB_TYPE == "none" → SKIP (pas de driver). Sinon installer.
if [ "$DB_TYPE" != "none" ] && [ -n "$DRIVER_MODULE" ]; then
  dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj \
    package "$DRIVER_MODULE" --version "$DRIVER_VERSION"
fi
```

**Idempotent** : `dotnet add package` no-op si version déjà présente.

### 3.1 Commandes de scaffolding EF Core

Lire `DatabaseType` dans `workspace/input/stack/stack.md ## Active Database`
et executer la commande correspondante. **Toutes les valeurs de
connexion proviennent exclusivement du bloc `## Active Database` de
stack.md — jamais d'env vars, jamais en dur.**

Resoudre les placeholders `{BackendName}`, `{BackendNamespace}` depuis
`## Project Config` avant d'executer.

Le scaffolding EF Core ci-dessous est invoque par `arch` Phase B avec
la connection string composee en RAM par le bridge `_bridge.csproj`
(cf. `agents/arch.md §8`). Les valeurs DB_* dans les exemples bash
ci-dessous representent les **valeurs lues depuis `## Active Database`
et injectees en argument du process**, pas des env vars du shell.

#### SQLServer (`DatabaseType: sqlserver`)

```bash
# Prerequis : Microsoft.EntityFrameworkCore.SqlServer deja declare en §2.4
# v6.1 hardening : Encrypt=True + TrustServerCertificate=False par defaut.
# Pour dev local avec certificat self-signed, ajouter
# `DB_TRUST_SERVER_CERT: true` dans le bloc ## Active Database de stack.md ;
# arch propagera Encrypt + TrustServerCertificate dans la connection string.
TRUST_CERT="${DB_TRUST_SERVER_CERT:-false}"  # valeur lue depuis ## Active Database par arch
CONN="Server=${DB_HOST},${DB_PORT};Database=${DB_NAME};User Id=${DB_USER};Password=${DB_PASSWORD};Encrypt=True;TrustServerCertificate=${TRUST_CERT};"

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

## 5.1 Connection string — env var binding runtime (depuis 2026-05-22)

> **BREAKING change 2026-05-22** : la règle « aucune lecture
> `Environment.GetEnvironmentVariable` » v6.x est révoquée pour
> `appsettings.json`-vs-secrets. Pattern correct = `appsettings.json`
> avec `ConnectionStrings:Default = ""` (placeholder vide) + binding
> runtime dans `Program.cs` qui assemble la connection string depuis les
> env vars `DB_*` déclarées en `## Active Database` de stack.md.
>
> Motif : la scaffolding `arch` v6.x écrivait `Password=cmsprint.` en
> littéral dans `appsettings.json`, créant un `[SEC_SECRET_HARDCODED]`
> critique même si `workspace/output/` est gitignored (leak via dev
> machine, template partagé, screenshot debug).

La chaine de connexion est **assemblée au boot dans `Program.cs`**
depuis les env vars `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` /
`DB_PASSWORD` qui correspondent exactement aux clés déclarées en
`## Active Database` de `stack.md`. arch génère le bloc d'assemblage
au scaffolding ; `appsettings.json` reste vide de secrets.

Pattern canonique (`Program.cs`) — env var binding au boot :

```csharp
// === Pont env-var → IConfiguration (arch génère ce bloc au scaffolding) ===
static string ReadEnv(string key, string fallback = "") =>
    (Environment.GetEnvironmentVariable(key) ?? fallback).Trim().Trim('"');

var dbHost = ReadEnv("DB_HOST", "127.0.0.1");
var dbPort = ReadEnv("DB_PORT", "5432");
var dbName = ReadEnv("DB_NAME");
var dbUser = ReadEnv("DB_USER", "postgres");
var dbPwd  = ReadEnv("DB_PASSWORD");
if (!string.IsNullOrEmpty(dbHost) && !string.IsNullOrEmpty(dbName))
{
    builder.Configuration["ConnectionStrings:Default"] =
        $"Host={dbHost};Port={dbPort};Database={dbName};Username={dbUser};Password={dbPwd}";
}

// Lecture (le pont ci-dessus a peuplé la clé)
var connectionString = builder.Configuration.GetConnectionString("Default")
    ?? throw new InvalidOperationException(
        "ConnectionStrings:Default missing. Verifier les env vars DB_* (cf. ## Active Database de stack.md).");

// Selon DatabaseType (lu via builder.Configuration["Database:Type"])
var dbType = builder.Configuration["Database:Type"]?.ToLowerInvariant() ?? "sqlserver";
builder.Services.AddDbContext<OperationsDbContext>(o => dbType switch
{
    "sqlserver" => o.UseSqlServer(connectionString),
    "postgres" or "postgresql" => o.UseNpgsql(connectionString),
    "mysql" => o.UseMySql(connectionString, ServerVersion.AutoDetect(connectionString)),
    "sqlite" => o.UseSqlite(connectionString),
    _ => throw new InvalidOperationException($"DatabaseType inconnu : {dbType}")
});
```

### 5.1.0 Anti-pattern bloquant — clé `ConnectionStrings:Default` (LITTÉRAL, post-mortem 2026-05-14)

**Symptôme runtime** : au démarrage, l'app crash avec :
```
System.InvalidOperationException: ConnectionStrings:{XXX} missing in appsettings.json
   at Program.<Main>$(String[] args)
```

**Cause racine** : l'agent dev-backend a dévié et écrit
`GetConnectionString("NounouJobDb")` (ou `"{ProjectName}Db"`,
`"{AppName}"`, etc.) au lieu de la convention canonique `"Default"`.
Le `appsettings.json` produit par arch contient bien la clé `Default`
(cf. §5.1.1 Format), donc `GetConnectionString("NounouJobDb")` retourne
`null` → `throw` à `var connectionString = ... ?? throw`.

**Règle stricte (load-bearing)** :

| Élément | Valeur autorisée | Anti-pattern |
|---|---|---|
| Argument `GetConnectionString(...)` | `"Default"` (LITTÉRAL) | `"{AppName}"`, `"{BackendName}"`, `"{ProjectName}Db"`, `"{DbName}"`, tout token dérivé |
| Clé dans `appsettings.json` | `ConnectionStrings.Default` (LITTÉRAL) | toute autre clé |
| Message d'erreur du `??` | référence `ConnectionStrings:Default` LITTÉRAL | référence à un autre nom |

**Pattern correct (à reproduire à l'identique)** :
```csharp
var connectionString = builder.Configuration.GetConnectionString("Default")
    ?? throw new InvalidOperationException(
        "ConnectionStrings:Default missing in appsettings.json. " +
        "Verifier ## Active Database de stack.md et relancer /arch-init.");
```

**Anti-pattern à grep en STEP build** (dev-backend STEP 8) :
```bash
grep -rnE 'GetConnectionString\("(?!Default")' workspace/output/src/{BackendName}/ && \
  echo "[STACK_DERIVE_VIOLATION] GetConnectionString avec clé != Default"
```

Toute occurrence ≠ `"Default"` → STOP + ERROR avant build :
```
ERROR: dev-backend {n}-{m} — clé ConnectionStrings non canonique
CAUSE: [DERIVE_VIOLATION] GetConnectionString("{XXX}") au lieu de GetConnectionString("Default") dans Program.cs:{L}
       arch écrit la clé "Default" dans appsettings.json (cf. dotnet-minimalapi.md §5.1.0/§5.1.1)
FIX: remplacer "{XXX}" par "Default" (LITTÉRAL) dans Program.cs et dans le message d'erreur du ??
```

**Pourquoi pas de paramétrage** : la clé `Default` est volontairement
fixe pour garantir l'idempotence cross-agent et cross-FEAT. Si un projet
nécessite plusieurs DBs (multi-tenant), créer des clés additionnelles
`ConnectionStrings.Tenant1`, `ConnectionStrings.Tenant2` SANS toucher à
`Default` (qui reste la DB principale).

---

### 5.1.1 Format `appsettings.json` produit par arch

Référence canonique (arch Phase A STEP 4.5 écrit ce fichier depuis
`## Active Database` + `## Active Auth Specs`). Une seule section auth
est écrite selon le profil détecté en STEP 2.ter.3 (cf. `agents/arch.md`).

**Profil auth = `azure-ad`** :
```json
{
  "ConnectionStrings": {
    "Default": "Server={DB_HOST},{DB_PORT};Database={DB_NAME};User Id={DB_USER};Password={DB_PASSWORD};Encrypt=True;TrustServerCertificate=False;"
  },
  "Database": {
    "Type": "sqlserver"
  },
  "AzureAd": {
    "Instance": "https://login.microsoftonline.com/",
    "TenantId": "{AZ_TENANTID}",
    "ClientId": "{AZ_CLIENTID}",
    "Domain": "{AZ_DOMAIN}",
    "CallbackPath": "{AZ_BE_CALLBACKPATH}",
    "ValidAudiences": ["{AZ_AUDIENCES split,strip}"]
  },
  "Logging": { "LogLevel": { "Default": "Information" } }
}
```

**Profil auth = `auth-local`** (depuis 2026-05-14) :
```json
{
  "ConnectionStrings": {
    "Default": "Server={DB_HOST},{DB_PORT};Database={DB_NAME};User Id={DB_USER};Password={DB_PASSWORD};Encrypt=True;TrustServerCertificate=False;"
  },
  "Database": {
    "Type": "sqlserver"
  },
  "Jwt": {
    "Secret": "{AUTH_JWT_SECRET}",
    "Issuer": "{AUTH_JWT_ISSUER}",
    "Audience": "{AUTH_JWT_AUDIENCE}",
    "ExpirationMinutes": {AUTH_JWT_EXPIRATION}
  },
  "Logging": { "LogLevel": { "Default": "Information" } }
}
```

Le code applicatif lit la section `Jwt` via `IConfiguration` :
```csharp
var jwt = builder.Configuration.GetSection("Jwt");
var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(
    jwt["Secret"] ?? throw new InvalidOperationException(
        "Jwt:Secret missing in appsettings.json. " +
        "Verifier ## Active Auth Specs (AUTH_JWT_SECRET) et relancer /arch-init.")));

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options => options.TokenValidationParameters = new TokenValidationParameters {
        ValidateIssuer = true,           ValidIssuer = jwt["Issuer"],
        ValidateAudience = true,         ValidAudience = jwt["Audience"],
        ValidateLifetime = true,
        IssuerSigningKey = key,          ValidateIssuerSigningKey = true,
    });
```

Pour la génération du token (`/auth/login`) :
```csharp
var expMin = builder.Configuration.GetValue<int>("Jwt:ExpirationMinutes");
var token = new JwtSecurityToken(
    issuer:    jwt["Issuer"],
    audience:  jwt["Audience"],
    claims:    [ new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()), ... ],
    expires:   DateTime.UtcNow.AddMinutes(expMin),
    signingCredentials: new SigningCredentials(key, SecurityAlgorithms.HmacSha256));
```

Anti-patterns rejetés (`[DERIVE_VIOLATION]`) :
```csharp
// INTERDIT — lecture env var
var secret = Environment.GetEnvironmentVariable("AUTH_JWT_SECRET");

// INTERDIT — secret hardcodé
var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes("hardcoded-secret"));

// INTERDIT — durée hardcodée
expires: DateTime.UtcNow.AddHours(1);
```

La construction de la chaîne de connexion (`Server=...;...`) est faite
**par arch côté builder** (`SqlConnectionStringBuilder` /
`NpgsqlConnectionStringBuilder` / etc. selon `DatabaseType` du bloc
`## Active Database`) puis sérialisée dans `appsettings.json`.

### 5.1.2 v6.1 hardening — Encrypt + TrustServerCertificate

- Encrypt=True forcé dans la connection string générée par arch.
- TrustServerCertificate=False par défaut. Override possible via clé
  `DB_TRUST_SERVER_CERT: true` dans `## Active Database` (dev local
  uniquement, jamais en prod). Arch refuse cette clé si
  `ASPNETCORE_ENVIRONMENT=Production` détecté (override Project Config).

Anti-patterns rejetés :
```csharp
// INTERDIT — lecture env var (depuis 2026-05-14)
var conn = Environment.GetEnvironmentVariable("DB_PASSWORD");

// INTERDIT — construction runtime hors arch
var builder = new SqlConnectionStringBuilder { DataSource = "..." };  // [DERIVE_VIOLATION]

// INTERDIT — concaténation littérale (forbidden-scan)
var conn = $"Server={host};Password={pwd};";
```

### 5.bis Envoi d'email — SmtpClient interdit, MailKit obligatoire (v6.1)

Microsoft a déprécié `System.Net.Mail.SmtpClient` depuis .NET 5 ("obsolete,
do not use") et la documentation officielle recommande **MailKit** comme
remplaçant. SDD_Pro applique cette recommandation strictement.

**Interdit** :
```csharp
// INTERDIT - System.Net.Mail.SmtpClient deprecie depuis .NET 5
using System.Net.Mail;
using var smtp = new SmtpClient("smtp.example.com");
await smtp.SendMailAsync(new MailMessage(...));   // [STACK_LIBRARY_MISSING]
```

**Obligatoire** (MailKit + MimeKit, capability `email` on-demand §2.4.b) :
```csharp
using MailKit.Net.Smtp;
using MimeKit;

var message = new MimeMessage();
message.From.Add(new MailboxAddress("App", "noreply@example.com"));
message.To.Add(new MailboxAddress("User", "user@example.com"));
message.Subject = "Reset password";
message.Body = new TextPart("html") { Text = "<p>...</p>" };

using var smtp = new SmtpClient();   // MailKit.Net.Smtp.SmtpClient, PAS System.Net.Mail
await smtp.ConnectAsync(host, port, SecureSocketOptions.StartTlsWhenAvailable);
await smtp.AuthenticateAsync(user, password);
await smtp.SendAsync(message);
await smtp.DisconnectAsync(true);
```

Activation : ajouter `## Capabilities Override` dans `## Project Config`
si trigger US ne suffit pas :
```yaml
Capabilities: email   # force install MailKit + MimeKit au bootstrap arch
```

---

## 6. Multilingue
Parametre de requete optionnel `langue`. Traductions dans
`workspace/output/src/{BackendName}/Resources/` (fichiers `.resx`), resolution via
`IStringLocalizer` / `IHtmlLocalizer`.

---

## 6.bis Security headers HSTS + X-Frame-Options + X-Content-Type-Options (depuis 2026-05-22)

**Bloc obligatoire dans le scaffold `Program.cs`** — couvre les classes
`[SEC_HEADERS_MISSING]` (security-reviewer A05/CWE-693). Ajouter entre
`builder.Services.Add*` et `var app = builder.Build();` :

```csharp
// --- HSTS hardening (SEC: A05/CWE-693) ---
builder.Services.AddHsts(options =>
{
    options.Preload = true;
    options.IncludeSubDomains = true;
    options.MaxAge = TimeSpan.FromDays(365);
});
```

Puis dans le pipeline HTTP (juste après `var app = builder.Build();`) :

```csharp
// --- Security headers middleware (SEC: A05/CWE-693) ---
app.Use(async (ctx, next) =>
{
    ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
    ctx.Response.Headers["X-Frame-Options"] = "DENY";
    ctx.Response.Headers["Referrer-Policy"] = "no-referrer";
    await next();
});

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}
else
{
    app.UseHsts();   // Strict-Transport-Security en prod uniquement (browsers cachent l'header → dev = risque)
}
```

**Justification** : sans ces headers, `security-reviewer` flag
`[SEC_HEADERS_MISSING]` à chaque scaffold. Coût marginal : ~10 lignes
dans Program.cs, zéro impact runtime. Doit être généré par arch comme
partie du Program.cs initial.

## 7. CORS
Conforme a `.claude/rules/library-and-stack.md §2.1`. Policy `Spa` avec origins **explicites**
lus depuis la configuration (`Cors:AllowedOrigins`, CSV) ; fallback
`http://localhost:5173` (port Vite par defaut pour React, ajuster si le stack
frontend utilise un autre port — Vue 5173, Angular 4200, Next 3000).

```csharp
// Program.cs
var allowedOrigins = builder.Configuration["Cors:AllowedOrigins"]?
    .Split(',', StringSplitOptions.RemoveEmptyEntries)
    ?? new[] { "http://localhost:5173" };

builder.Services.AddCors(options => options.AddPolicy("Spa", policy =>
    policy.WithOrigins(allowedOrigins)
          .AllowAnyHeader()
          .AllowAnyMethod()
          .AllowCredentials()));

// ... apres UseRouting, AVANT UseAuthentication / UseAuthorization
app.UseCors("Spa");
```

`appsettings.Development.json` (genere par arch) :
```json
{
  "Cors": {
    "AllowedOrigins": "http://localhost:5173,http://localhost:4173"
  }
}
```

Override via env var `Cors__AllowedOrigins=http://localhost:5173,https://staging.example.com`.

**Interdits formellement** (declenche `[SEC_CORS_PERMISSIVE]` du security-reviewer) :
- `AllowAnyOrigin()` (wildcard incompatible avec `AllowCredentials()` per W3C spec)
- `WithOrigins("*")`
- Annotation `[EnableCors]` ad-hoc sur controllers (fragmente la policy)
- Origins hardcodees dans Program.cs (doit venir de config)

Durcissement staging / prod : remplacer le fallback localhost par les origins
production reelles, jamais de wildcard. Cf. `rules/library-and-stack.md §4` (anti-patterns) +
`rules/library-and-stack.md §5` (verification dev-backend STEP build).

---

## 8. URLs de developpement

**Source autoritaire** : `workspace/output/src/{BackendName}/Properties/launchSettings.json`
(produit par `dotnet new webapi` lors du bootstrap arch). Lire `profiles.http.applicationUrl`
ET `profiles.https.applicationUrl` pour obtenir les ports effectifs du projet.

Ports par défaut du scaffolding `.NET 10 minimal API` (déterministes mais peuvent
varier si l'utilisateur a régénéré le projet) :

| Profil | URL canonique | Usage |
|---|---|---|
| `http`  | `http://localhost:5143`  | dev sans cert, proxy Vite, curl/Postman |
| `https` | `https://localhost:7239` | dev avec `dotnet dev-certs https --trust` |
| OpenAPI/Swagger | `{base}/swagger` (les deux profils) | UI explore endpoints |

**Anti-pattern bloquant (post-mortem 2026-05-14)** : ne JAMAIS hardcoder
`44328`, `5000`, `5099`, `8080` ou tout autre port "convention historique"
dans le code, les configs frontend, ou les MD. Toujours lire le port effectif
depuis `launchSettings.json` (autorité unique).

Tout désalignement entre `launchSettings.json` et la config frontend (proxy
Vite, `VITE_API_BASE_URL`, `Api:BaseAddress`) → 500 / proxy error silencieux.
Cf. `.claude/stacks/frontend/react.md §5` pour le grep côté frontend.

### 8.1 Injection env vars canoniques dans `launchSettings.json` (arch STEP 3, depuis 2026-05-22)

`launchSettings.json` est chargé par `dotnet run` **avant** la résolution
`Environment.GetEnvironmentVariable` — ses `environmentVariables`
**overrident le shell parent**. Cette propriété est load-bearing pour
neutraliser un shell utilisateur pollué (post-mortem AADSTS50011
CMSPrint 2026-05-22 : un `AZ_FE_CALLBACKPATH=/login-callback` hérité
d'un ancien projet React dans le profil PowerShell faisait échouer
le bootstrap MSAL Blazor).

**Arch STEP 3 (.NET backend)** doit injecter dans **chaque profil** de
`Properties/launchSettings.json` les env vars dont la valeur canonique
est **dépendante du stack frontend actif** (et non du shell utilisateur) :

```json
"environmentVariables": {
  "ASPNETCORE_ENVIRONMENT": "Development",
  "AZ_BE_CALLBACKPATH": "/signin-oidc",
  "AZ_FE_CALLBACKPATH": "/authentication/login-callback"
}
```

| Env var | Valeur canonique | Source |
|---|---|---|
| `AZ_BE_CALLBACKPATH` | `/signin-oidc` (web flow OIDC backend) | `auth/azure-ad.md §1` |
| `AZ_FE_CALLBACKPATH` (frontend = Blazor WASM) | `/authentication/login-callback` | `auth/azure-ad.md §2.quart` |
| `AZ_FE_CALLBACKPATH` (frontend = React/Vue/Angular MSAL.js) | `/authentication/login-callback` (depuis convention universelle SDD_Pro v6.x) | `auth/azure-ad.md §2.ter` |

**Pas dans `appsettings.json`** : ces clés ne sont pas du config "produit"
(elles sont des valeurs de bootstrap pré-config), elles vivent dans
l'env. `launchSettings.json` est l'endroit déterministe pour les figer
dev-side. Production : `.env.production` géré par ops (out of scope arch).

**Pas dans `.env.example`** : `.env.example` documente les env vars
**utilisateur** (DB connection, secrets Azure AD GUID), pas les valeurs
canoniques framework. Garder la séparation : `launchSettings.json` =
valeurs canoniques, `.env.local` = secrets/overrides utilisateur.

---

## 9. Interdits projet (backend)

- Secrets, cles d'API, mots de passe en dur dans le code C# (sources `.cs`)
- Chaines de connexion litterales en dur dans le code C# (cle/valeur ou URI)
- Hotes litteraux (`localhost`, IP) lies au host BDD dans un Service
- Lecture de credentials BDD via `Environment.GetEnvironmentVariable` ou
  fichier `.env` (depuis 2026-05-14, lecture exclusive via `IConfiguration`
  qui charge `appsettings.json` peuple par arch — cf. §5.1)
- Logique metier dans les Entities ou les Endpoints
- Mapping manuel dans Endpoints ou Services
- Modification manuelle des Entities generees par EF (classes partielles sinon)
- Suppression automatique d'entites EF existantes
- Regeneration complete des Entities depuis zero
- Ecrasement d'un DbSet existant du DbContext lors d'une mise a jour de scaffolding
- Exception brute exposee au client (toujours `ProblemDetails`)
- Log de la chaine de connexion complete ou du mot de passe DB (cle DB_PASSWORD)
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
elles n'autorisent JAMAIS l'expansion de scope au-dela de la task / FEAT /
stack (voir `.claude/rules/library-and-stack.md`). Toute librairie
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

Arch Phase A lit `## Active Database: DatabaseType` puis installe le
provider correspondant via `dotnet add package` :
```bash
dotnet add workspace/output/src/{BackendName}/{BackendName}.csproj package <Provider>
```

### 8.2 Connection String Pattern (composition côté arch, depuis 2026-05-14)

La connection string est **composée par l'agent `arch` Phase A — STEP
4.5** à partir des valeurs `DB_HOST/PORT/NAME/USER/PASSWORD` du bloc
`## Active Database` de `stack.md`, puis **sérialisée dans
`appsettings.json` section `ConnectionStrings.Default`**. Le code
applicatif (`Program.cs`) lit cette valeur via
`builder.Configuration.GetConnectionString("Default")` (cf. §5.1).

| DatabaseType  | Builder utilisé par arch                          | Propriétés mappées depuis ## Active Database |
|---------------|---------------------------------------------------|----------------------------------------------|
| `sqlserver`   | `Microsoft.Data.SqlClient.SqlConnectionStringBuilder` | DataSource=`{DB_HOST},{DB_PORT}`, InitialCatalog=`{DB_NAME}`, UserID=`{DB_USER}`, Password=`{DB_PASSWORD}`, **Encrypt=true** (v6.1), **TrustServerCertificate=false** par défaut (opt-in via `DB_TRUST_SERVER_CERT: true` dans `## Active Database` en dev local uniquement) |
| `postgres`    | `Npgsql.NpgsqlConnectionStringBuilder`            | Host=`{DB_HOST}`, Port=`{DB_PORT}`, Database=`{DB_NAME}`, Username=`{DB_USER}`, Password=`{DB_PASSWORD}` |
| `mysql`       | `MySqlConnector.MySqlConnectionStringBuilder`     | Server=`{DB_HOST}`, Port=`{DB_PORT}`, Database=`{DB_NAME}`, UserID=`{DB_USER}`, Password=`{DB_PASSWORD}` |
| `sqlite`      | `Microsoft.Data.Sqlite.SqliteConnectionStringBuilder` | DataSource=`{DB_NAME}` (chemin fichier — DB_HOST/PORT/USER/PASSWORD ignorées) |

Aucune concaténation littérale `$"Server=...;..."` autorisée — viole
le scan forbidden-pattern (depuis 2026-05-14, env_rules.md est obsolète
mais le pattern de scan reste pour bloquer les secrets hardcodés).

Côté **code applicatif** (`Program.cs`) — lecture seule :
```csharp
// Pattern canonique depuis 2026-05-14 : IConfiguration only
var connectionString = builder.Configuration.GetConnectionString("Default")
    ?? throw new InvalidOperationException(
        "ConnectionStrings:Default missing in appsettings.json — verifier ## Active Database de stack.md et relancer /arch-init");

var dbType = builder.Configuration["Database:Type"]?.ToLowerInvariant() ?? "sqlserver";
builder.Services.AddDbContext<AppDbContext>(o => dbType switch
{
    "sqlserver" => o.UseSqlServer(connectionString),
    "postgres" or "postgresql" => o.UseNpgsql(connectionString),
    "mysql" => o.UseMySql(connectionString, ServerVersion.AutoDetect(connectionString)),
    "sqlite" => o.UseSqlite(connectionString),
    _ => throw new InvalidOperationException($"DatabaseType inconnu : {dbType}")
});
```

Côté **arch** (composition runtime, ne génère pas de code applicatif) :
arch invoque le builder approprié en RAM (cas SqlServer ci-dessous) :
```csharp
// _bridge.csproj ou Program.cs interne d'arch — JAMAIS dans le code applicatif
var sqlBuilder = new SqlConnectionStringBuilder
{
    DataSource             = $"{db_config["DB_HOST"]},{db_config["DB_PORT"]}",
    InitialCatalog         = db_config["DB_NAME"],
    UserID                 = db_config["DB_USER"],
    Password               = db_config["DB_PASSWORD"],
    Encrypt                = true,
    TrustServerCertificate = db_config.GetValueOrDefault("DB_TRUST_SERVER_CERT") == "true"
};
// puis File.WriteAllText("appsettings.json", json) avec ConnectionStrings.Default = sqlBuilder.ConnectionString
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
