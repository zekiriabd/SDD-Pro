# Tech FEAT: aspnet-mvc-razor (fullstack)

Status: Experimental
Validation: 🟡 experimental (2026-06-10 — stack initial, jamais bench-validated end-to-end. Pattern canonique ASP.NET Core MVC + Razor Views classique + DevExtreme HtmlHelpers + EF Core Database-First. À promouvoir 🟢 scaffold-validated après un premier `/sdd-full` complet sur une FEAT CRUD simple.)
Tech FEAT ID: tech-aspnet-mvc-razor
Scope: **fullstack monolithe** — application ASP.NET Core MVC .NET 10 dans UN seul projet `{AppName}/`. UI (Razor Views `.cshtml`) + Controllers MVC + Services + EF Core + Auth vivent dans le meme processus ASP.NET Core. Pas de separation `{BackendName}` / `{AppName}` / `{LibName}`. Modele **SSR vrai** : HTML rendu serveur par Razor, **widgets DevExtreme generes serveur** via HtmlHelpers (`@(Html.DevExtreme().DataGrid(...))`), donnees fetched cote serveur via `DataSourceLoader` (DevExtreme.AspNet.Data) sur endpoints JSON Controller. Pas de SPA, pas de bundler JS.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application MVC monolithique ASP.NET Core 10 + Razor + DevExtreme**. Un seul projet `{AppName}/` (un seul deployable IIS / Kestrel / container) qui :

- Sert des **pages HTML** rendues serveur via **Razor** (`*.cshtml` dans `Views/`)
- Expose des **Controllers MVC** (`Controller`) qui retournent `IActionResult` (`View(...)`, `RedirectToAction(...)`, `Json(...)`)
- Expose des **endpoints JSON** (`[HttpGet] [Route("api/...")]`) consommes **uniquement** par les widgets DevExtreme cote client via `DataSourceLoader.Load(...)` (filter/sort/group/page server-side sur `IQueryable<T>`)
- Gere la **persistance** via EF Core Database-First (scaffolding entites depuis schema existant)
- Gere l'**auth** via cookies (default) ou Azure AD (capability `azure-ad`)

Architecture cible :

```
Browser
  ├── HTML render serveur (Razor .cshtml)
  ├── DevExtreme JS client (devextreme.js + theme CSS) — bound aux widgets serveur
  └── XHR JSON vers /api/{domain}/data (DataSourceLoader)
       │
       ▼
ASP.NET Core MVC (.NET 10)
  ├── Controllers MVC      (Controller)        → return View(model)
  ├── Controllers DataApi  (Controller)        → return Json(DataSourceLoader.Load(query, opts))
  ├── Services             (IXxxService)
  ├── Mappers              (AutoMapper Profile, Entity → ViewModel)
  ├── DbContext            (EF Core, Database-First)
  ├── Validators           (FluentValidation, AbstractValidator<TModel>)
  ├── Auth                 (Cookies OR Azure AD via Microsoft.Identity.Web)
  └── Razor Views          (Views/{Domain}/{Action}.cshtml)
       └── @(Html.DevExtreme().DataGrid()...)  — HtmlHelpers serveur
```

**Difference vs `blazor-server`** :
- Pas de SignalR (pas d'UI streaming) — la page se recharge en MVC classique sur POST/redirect, OU le widget DevExtreme client emet un XHR JSON
- Interactivite riche **uniquement** via les widgets DevExtreme (DataGrid, Form, Charts, Scheduler) bound au DataSource server-side
- Modele mental "old school" ASP.NET MVC 5 → directement transposable, idéal pour migrations brownfield

## 1.2 Couches

- **Controllers MVC** (`Controller`) : retournent `IActionResult` (`View(...)`, `RedirectToAction(...)`). Aucune logique metier.
- **Controllers DataApi** (`Controller` annote `[Route("api/{domain}")]`) : retournent `Json(DataSourceLoader.Load(query, options))`. Consommes par les widgets DevExtreme cote client. Aucune logique metier.
- **Services** (`IXxxService` + `XxxService`) : logique metier, transactionnalite via `DbContext.SaveChangesAsync()`.
- **Mappers** (AutoMapper Profile) : Entity → ViewModel. Pas de mapping inline.
- **DbContext** (`AppDbContext : DbContext`) : EF Core Database-First. `OnModelCreating` decrit le mapping.
- **Entities** (`Data/Entities/{Domain}.cs`) : scaffolded depuis DB existante (`dotnet ef dbcontext scaffold ...`)
- **ViewModels** (`Models/{Domain}{Action}ViewModel.cs`) : DTOs vers vue. Validees par FluentValidation.
- **Validators** (`Validators/{Name}Validator.cs`) : FluentValidation `AbstractValidator<TViewModel>`.
- **Razor Views** (`Views/{Domain}/{Action}.cshtml`) : HTML server-rendered + HtmlHelpers DevExtreme.
- **Layout** (`Views/Shared/_Layout.cshtml`) : layout principal (nav, footer, scripts DevExtreme).

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

| Layer | Path |
|---|---|
| Application entry | `workspace/src/{AppName}/Program.cs` |
| Controllers MVC | `workspace/src/{AppName}/Controllers/{Domain}Controller.cs` |
| Controllers DataApi | `workspace/src/{AppName}/Controllers/Api/{Domain}DataController.cs` |
| Service interface | `workspace/src/{AppName}/Services/Interfaces/I{Domain}Service.cs` |
| Service impl | `workspace/src/{AppName}/Services/Implementations/{Domain}Service.cs` |
| ViewModel | `workspace/src/{AppName}/Models/{Domain}{Action}ViewModel.cs` |
| Entity | `workspace/src/{AppName}/Data/Entities/{Domain}.cs` |
| DbContext | `workspace/src/{AppName}/Data/AppDbContext.cs` |
| Mapper (Profile) | `workspace/src/{AppName}/Mappers/{Domain}Profile.cs` |
| Validator | `workspace/src/{AppName}/Validators/{Domain}{Action}Validator.cs` |
| Auth config | `workspace/src/{AppName}/Auth/AuthExtensions.cs` |
| Middleware | `workspace/src/{AppName}/Middleware/{Name}Middleware.cs` |
| Razor View | `workspace/src/{AppName}/Views/{Domain}/{Action}.cshtml` |
| Razor partial | `workspace/src/{AppName}/Views/Shared/_{Name}.cshtml` |
| Layout | `workspace/src/{AppName}/Views/Shared/_Layout.cshtml` |
| ViewImports | `workspace/src/{AppName}/Views/_ViewImports.cshtml` |
| Static wwwroot | `workspace/src/{AppName}/wwwroot/` |
| appsettings | `workspace/src/{AppName}/appsettings.json` (peuple par arch depuis stack.md) |
| Project file | `workspace/src/{AppName}/{AppName}.csproj` |

## 1.4 Principes non negociables

**Architecture MVC + Razor** :
- **Aucune logique metier dans Controller** — toujours via Service. Controller = lire form/route, appeler service, retourner View/Redirect/Json.
- **Aucun acces EF Core direct depuis Controller** — toujours via Service.
- **Aucun acces EF Core direct depuis Razor View** — preparer les donnees dans Controller, passer en `ViewModel`.
- **Aucun mapping inline** — toujours via AutoMapper Profile (`Mappers/{Domain}Profile.cs`).
- **Validation FluentValidation** sur ViewModel + auto-bind ModelState (Controller `if (!ModelState.IsValid) return View(model);`). Pas de validation manuelle inline.
- **Transactions implicites** : `DbContext.SaveChangesAsync()` sur Service. Pour multi-step → `DbContext.Database.BeginTransactionAsync()` au niveau Service.
- **CSRF** : `[ValidateAntiForgeryToken]` OBLIGATOIRE sur tous les POST/PUT/DELETE Controllers MVC. `@Html.AntiForgeryToken()` dans tous les forms Razor.
- **DevExtreme widgets** : preferer aux HtmlHelpers HTML brut (`<input>`, `<select>`, `<table>`) des qu'il y a une interactivite (sort, filter, pagination, validation inline).

**SOLID + Clean Code** : voir `.sdd/stacks/fullstack/blazor-server.md §1.5` (integralement applicable — pattern .NET classique).

**Securite** :
- **Antiforgery token** : pre-config par ASP.NET Core (non desactiver). `services.AddAntiforgery()` + `[ValidateAntiForgeryToken]` sur Controllers.
- **Cookies auth** : `HttpOnly: true`, `SecurePolicy: Always` (prod), `SameSite: Lax`. Gere par `AddAuthentication().AddCookie(...)` defaut.
- **Connection string DB** : dans `appsettings.json` section `ConnectionStrings:Default` peuplee par arch depuis `stack.md`. **JAMAIS** via `Environment.GetEnvironmentVariable("DB_*")` dans le code applicatif (sinon `[SEC_ENV_VAR_FORBIDDEN]`).
- **Razor auto-escape** : `@variable` echappe HTML automatiquement. `@Html.Raw(...)` est INTERDIT sur user input — uniquement pour du HTML genere serveur via helpers controles.
- **DevExtreme `Html.DevExtreme().*.OnClick("function(e) {...}")` ** : si la callback JS interpole une variable C# (`OnClick("alert('" + Model.Name + "')")`), c'est un XSS. Toujours passer par le DataSource ou des attributs data-*.

## 1.5 Persistance

Database-First strict. Identique a `.sdd/stacks/backend/dotnet-minimalapi.md §8` :

- Scaffolding via `dotnet ef dbcontext scaffold "{ConnectionString}" {Provider} -o Data/Entities --context AppDbContext --context-dir Data --use-database-names --no-onconfiguring -f`
- Entites + `AppDbContext` regeneres a chaque change de schema (idempotent, `-f` force overwrite)
- DbContext enregistre via `services.AddDbContext<AppDbContext>(opt => opt.UseSqlServer(connStr))`
- Migrations interdites (Database-First exclusif — toute migration vit dans l'outil DB, jamais EF Migrations)

## 1.6 DevExtreme — pattern de base

**Cote serveur** (Razor) — HtmlHelpers DevExtreme.AspNet.Mvc :

```cshtml
@(Html.DevExtreme().DataGrid<UserListItemViewModel>()
    .ID("usersGrid")
    .DataSource(ds => ds.Mvc()
        .Controller("UsersData")
        .LoadAction("List")
        .Key("Id"))
    .Columns(c => {
        c.AddFor(m => m.UserName);
        c.AddFor(m => m.Email);
        c.AddFor(m => m.CreatedAt).Format("yyyy-MM-dd HH:mm");
    })
    .Paging(p => p.PageSize(25))
    .RemoteOperations(true)   // server-side filter/sort/group/page
    .FilterRow(f => f.Visible(true))
    .ColumnAutoWidth(true)
)
```

**Cote serveur** (Controller DataApi) — `DataSourceLoader` :

```csharp
[Route("api/users")]
public class UsersDataController : Controller
{
    private readonly IUserService _service;
    public UsersDataController(IUserService service) => _service = service;

    [HttpGet("List")]
    public async Task<IActionResult> List(DataSourceLoadOptions loadOptions)
    {
        IQueryable<UserListItemViewModel> query = _service.QueryListItems();
        return Json(await DataSourceLoader.LoadAsync(query, loadOptions));
    }
}
```

`DataSourceLoadOptions` est bind automatiquement depuis la querystring (`?filter=...&sort=...&skip=...&take=...`) emise par le widget DevExtreme. `DataSourceLoader.LoadAsync(IQueryable, opts)` applique filter/sort/group/page **server-side** (translate en SQL via EF Core) → retourne `LoadResult { data, totalCount, groupCount }`.

**Cote layout** (`Views/Shared/_Layout.cshtml`) — assets client DevExtreme :

```cshtml
<link rel="stylesheet" href="~/lib/devextreme/css/dx.light.css" />
<script src="~/lib/devextreme/js/dx.all.js"></script>
```

Les fichiers `dx.light.css` + `dx.all.js` sont servis depuis `wwwroot/lib/devextreme/` (deployes via `libman.json` ou `npm` cote dev, copies au build). Alternative CDN DevExpress autorisee en dev/POC uniquement.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `aspnet-mvc-razor`
- **Langage** : C# 12
- **Runtime** : .NET 10.0 LTS (`net10.0`)
- **Framework principal** : ASP.NET Core MVC 10 (`Microsoft.AspNetCore.Mvc`)
- **Template engine** : Razor (`.cshtml`)
- **UI library** : DevExtreme 25.1.x via DevExtreme.AspNet.Mvc HtmlHelpers
- **Namespace racine** : `{AppNamespace}`

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/{AppName}.csproj`
- **Build** : `dotnet build workspace/src/{AppName}/{AppName}.csproj --nologo` (project-scoped)
- **Run** : `dotnet run --project workspace/src/{AppName}/{AppName}.csproj --urls http://localhost:5099`
- **Smoke Command** : `dotnet run --project workspace/src/{AppName}/{AppName}.csproj --no-build --urls http://localhost:5099 & APP_PID=$!; sleep 5; curl -sf http://localhost:5099/ -o /dev/null; RC=$?; kill $APP_PID 2>/dev/null; wait $APP_PID 2>/dev/null; exit $RC`
- **Smoke Timeout** : 60s
- **Preserves identifier syntax** : `\b<id>\b` (mot entier, sensible a la casse)
- **Lint / Format** : `dotnet format`
- **Type-check** : integre au build
- **Package manager** : NuGet (+ `libman` ou `npm` pour assets client DevExtreme)
- **EF Scaffolding** : `dotnet ef dbcontext scaffold` (depuis Phase B arch)

## 2.2.1 Init Commands (executees par l'agent `arch` Phase A si `project_file` absent)

```bash
if [ ! -f "workspace/src/{AppName}/{AppName}.csproj" ]; then

# STEP 1 — Scaffold du projet ASP.NET Core MVC
# Note: template `mvc` ASP.NET Core est mature et stable, supporte directement net10.0.
dotnet new mvc -n {AppName} -o workspace/src/{AppName} --framework net10.0 --no-restore --auth None --force

# STEP 1b — Cleanup template demo files (Home/Privacy controllers + views demo)
# Suppression via `rm` simples (pas de sed chained — harness Claude Code refuse les
# commandes destructives composees, cf. blazor-server.md STEP 1b/2/2b/2c).
# L'agent `arch` execute (1 appel par fichier) :
#   rm -f workspace/src/{AppName}/Views/Home/Privacy.cshtml
#   (Home/Index.cshtml est conserve mais sera remplace par le Layout final.)

fi  # fin garde-fou idempotent

# STEP 2 — Ajouter les packages CORE (au-dela du template `mvc` de base)
#
# REGLE DE VERSIONING (conforme a .sdd/rules/library-and-stack.md Partie A §0) :
# - Packages a compatibilite validee : pinnes (versions ci-dessous)
# - Microsoft.Identity.Web : NON PINNE (CVE cycle frequent, capability azure-ad)

dotnet add workspace/src/{AppName}/{AppName}.csproj package Microsoft.AspNetCore.Mvc.Razor.RuntimeCompilation --version 10.0.6
dotnet add workspace/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore --version 10.0.6
dotnet add workspace/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore.SqlServer --version 10.0.6
dotnet add workspace/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore.Design --version 10.0.6
dotnet add workspace/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore.Tools --version 10.0.6
dotnet add workspace/src/{AppName}/{AppName}.csproj package AutoMapper --version 16.1.1
dotnet add workspace/src/{AppName}/{AppName}.csproj package FluentValidation.AspNetCore --version 11.10.0
dotnet add workspace/src/{AppName}/{AppName}.csproj package Serilog.AspNetCore --version 10.0.0
dotnet add workspace/src/{AppName}/{AppName}.csproj package Serilog.Sinks.Console --version 6.1.1

# DevExtreme — server-side data + HtmlHelpers Razor
dotnet add workspace/src/{AppName}/{AppName}.csproj package DevExtreme.AspNet.Data --version 5.0.0
dotnet add workspace/src/{AppName}/{AppName}.csproj package DevExtreme.AspNet.Mvc --version 25.1.5

# STEP 3 — Creer arborescence applicative
mkdir -p workspace/src/{AppName}/Controllers/Api
mkdir -p workspace/src/{AppName}/Services/Interfaces
mkdir -p workspace/src/{AppName}/Services/Implementations
mkdir -p workspace/src/{AppName}/Models
mkdir -p workspace/src/{AppName}/Data/Entities
mkdir -p workspace/src/{AppName}/Mappers
mkdir -p workspace/src/{AppName}/Validators
mkdir -p workspace/src/{AppName}/Auth
mkdir -p workspace/src/{AppName}/Middleware
mkdir -p workspace/src/{AppName}/wwwroot/lib/devextreme/css
mkdir -p workspace/src/{AppName}/wwwroot/lib/devextreme/js

# STEP 4 — Bootstrap _ViewImports.cshtml (enregistrement HtmlHelpers DevExtreme)
# L'agent `arch` ecrit via Write/Edit (un seul fichier atomique) :
#
# Views/_ViewImports.cshtml :
#   @using {AppNamespace}
#   @using {AppNamespace}.Models
#   @using DevExtreme.AspNet.Mvc
#   @addTagHelper *, Microsoft.AspNetCore.Mvc.TagHelpers
#   @addTagHelper *, DevExtreme.AspNet.Mvc

# STEP 5 — Augment Program.cs (operation: augment, preserves: AddControllersWithViews,
# MapControllerRoute, UseStaticFiles)
# L'agent `arch` ajoute via Edit :
#   - builder.Services.AddRazorPages().AddRazorRuntimeCompilation();   // hot-reload Views en dev
#   - builder.Services.AddDbContext<AppDbContext>(opt => opt.UseSqlServer(
#       builder.Configuration.GetConnectionString("Default")));
#   - builder.Services.AddAutoMapper(typeof(Program).Assembly);
#   - builder.Services.AddFluentValidationAutoValidation();
#   - builder.Services.AddValidatorsFromAssemblyContaining<Program>();
#   - builder.Host.UseSerilog((ctx, cfg) => cfg.ReadFrom.Configuration(ctx.Configuration).WriteTo.Console());
#   - app.UseSerilogRequestLogging();

# STEP 6 — Restore + build de verification
dotnet restore workspace/src/{AppName}/{AppName}.csproj
dotnet build workspace/src/{AppName}/{AppName}.csproj --nologo

# STEP 7 — Audit vulnerabilites NuGet (library-and-stack.md §0)
vuln_count=$(dotnet list workspace/src/{AppName}/{AppName}.csproj package --vulnerable --include-transitive 2>&1 | grep -c '>')
if [ "$vuln_count" -gt 0 ]; then
  echo "WARN: $vuln_count vulnerable package(s) apres install — voir dotnet list --vulnerable"
  dotnet list workspace/src/{AppName}/{AppName}.csproj package --vulnerable --include-transitive
fi

# STEP 8 — Provisionner assets DevExtreme client (CDN OU libman OU npm — choix DevOps)
# Pour POC initial : CDN unpkg dans _Layout.cshtml (cf. §1.6).
# Pour prod : `libman install devextreme@25.1.5 --destination wwwroot/lib/devextreme`
# (necessite `dotnet tool install -g Microsoft.Web.LibraryManager.Cli`).
```

**Contrat post-init** : `{AppName}.csproj` existe, build vert, `Views/_ViewImports.cshtml` enregistre `@using DevExtreme.AspNet.Mvc`, `Program.cs` enregistre `AppDbContext` + AutoMapper + FluentValidation + Serilog.

## 2.3 Patterns d'erreurs compilation

Format standard .NET : `{file}({line},{col}): error {code}: {message}`.
Codes prioritaires : CS0246, CS0103, CS1061, CS1002, CS1003, CS1513, CS0029, CS0266, CS0161, CS7036.

Codes Razor specifiques : `RZ1006` (tag helper inconnu — generalement `@addTagHelper` manquant pour DevExtreme dans `_ViewImports.cshtml`), `RZ2001` (directive invalide), `RZ3008` (component not found).

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/fullstack/aspnet-mvc-razor.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id aspnet-mvc-razor`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Microsoft.AspNetCore.Mvc.Razor.RuntimeCompilation | 10.0.11 | Hot-reload des vues .cshtml en dev (recompile a la volee, ne pas pin sur ef-core, version aligne ASP.NET Core) |
| Microsoft.EntityFrameworkCore | 10.0.11 | ORM principal |
| Microsoft.EntityFrameworkCore.SqlServer | 10.0.11 | Provider defaut (override via dbDrivers selon DatabaseType) |
| Microsoft.EntityFrameworkCore.Design | 10.0.11 |  |
| Microsoft.EntityFrameworkCore.Tools | 10.0.11 |  |
| AutoMapper | 16.2.0 | Mapping Entity -> ViewModel |
| FluentValidation.AspNetCore | 11.3.1 | Validation declarative cote Controller (auto-binding ModelState) |
| DevExtreme.AspNet.Data | 5.1.0 | DataSourceLoader server-side (filter, sort, group, page sur IQueryable<T>) pour endpoints JSON consommes par les widgets DevExtreme |
| DevExtreme.AspNet.Mvc | 26.1.4 | HtmlHelpers DevExtreme cote Razor: @(Html.DevExtreme().DataGrid()...) — generation widgets server-side |
| Serilog.AspNetCore | 10.0.0 | Logger structure |
| Serilog.Sinks.Console | 6.1.1 |  |
| Microsoft.Extensions.Caching.Memory | 10.0.11 | IMemoryCache integre (pas de package racine, transitif ASP.NET Core) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| db-postgres | Npgsql.EntityFrameworkCore.PostgreSQL | 10.0.3 | DatabaseType.*PostgreSql, postgres |
| db-mysql | Pomelo.EntityFrameworkCore.MySql | 9.0.0 | DatabaseType.*MySql, mysql, mariadb |
| db-sqlite | Microsoft.EntityFrameworkCore.Sqlite | 10.0.11 | DatabaseType.*Sqlite |
| azure-ad | Microsoft.Identity.Web | 4.14.2 | auth-azure-ad, azure.*ad, \bmsal\b, AzureAd |
| azure-ad | Microsoft.Identity.Web.UI | 4.14.2 | auth-azure-ad, azure.*ad |
| openapi | Swashbuckle.AspNetCore | 10.2.3 | swagger, openapi, /api-docs |
| excel | ClosedXML | 0.105.1 | \bexcel\b, \.xlsx\b, export.*excel |
| pdf | QuestPDF | 2026.8.0 | \bpdf\b, \.pdf\b, export.*pdf, generer.*pdf |
| http-client | Microsoft.Extensions.Http.Polly | 10.0.11 | appel.*api.*externe, service.*externe, \bpolly\b, retry.*http |
| smtp | MailKit | 4.17.0 | email, smtp, envoi.*mail, notification.*mail |
| smtp | MimeKit | 4.17.0 | email, smtp |
| logging-file | Serilog.Sinks.File | 7.0.0 | log.*file, log.*rolling, audit.*log |
| redis-cache | StackExchange.Redis | 3.1.31 | \bredis\b, distributed.*cache |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| sqlserver | `Microsoft.EntityFrameworkCore.SqlServer` | 10.0.11 | runtime |
| postgres | `Npgsql.EntityFrameworkCore.PostgreSQL` | 10.0.3 | runtime |
| mysql | `Pomelo.EntityFrameworkCore.MySql` | 9.0.0 | runtime |
| sqlite | `Microsoft.EntityFrameworkCore.Sqlite` | 10.0.11 | runtime |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — verifies par dev-* STEP 5.0. Toute violation = ERROR.

| Role | Pattern | Exemple |
|------|---------|---------|
| Controller MVC | `{Domain}Controller.cs` dans `Controllers/`, herite `Controller` | `UsersController.cs` |
| Controller DataApi (DevExtreme) | `{Domain}DataController.cs` dans `Controllers/Api/`, herite `Controller`, `[Route("api/{domain}")]` | `UsersDataController.cs` |
| Service interface | `I{Domain}Service.cs` dans `Services/Interfaces/` | `IUserService.cs` |
| Service impl | `{Domain}Service.cs` dans `Services/Implementations/`, implemente `I{Domain}Service` | `UserService.cs` |
| Entity | `{Domain}.cs` dans `Data/Entities/` (annote `[Table("...")]`) | `User.cs` |
| ViewModel | `{Domain}{Action}ViewModel.cs` dans `Models/` (PAS de suffixe `Dto`/`Model`) | `UserListItemViewModel.cs`, `UserCreateViewModel.cs` |
| AutoMapper Profile | `{Domain}Profile.cs` dans `Mappers/`, herite `Profile` | `UserProfile.cs` |
| FluentValidation Validator | `{Domain}{Action}Validator.cs` dans `Validators/`, herite `AbstractValidator<{Domain}{Action}ViewModel>` | `UserCreateValidator.cs` |
| Razor View | `Views/{Domain}/{Action}.cshtml` (PascalCase) | `Views/Users/Index.cshtml`, `Views/Users/Create.cshtml` |
| Razor partial | `Views/Shared/_{Name}.cshtml` (prefix underscore) | `_Pagination.cshtml` |

**Suffixes INTERDITS** :
- `Dto`, `Request`, `Response`, `Result` sur ViewModels (utiliser `{Action}ViewModel`)
- `Manager`, `Helper`, `Util` (sauf utilitaires purs strict, sans state injecte)
- `Impl` postfix sur l'interface (l'interface est prefixee `I`, l'impl n'a pas de suffixe)

---

## 3. Endpoints standard (obligatoires)

| Endpoint | Auth | Role | Type |
|----------|------|------|------|
| `GET /` | non | Page accueil (Home/Index.cshtml) | MVC |
| `GET /Account/Login` | non | Page login (si auth-local OU AzureAd avec UI) | MVC |
| `POST /Account/Login` | non | Submit login | MVC (`[ValidateAntiForgeryToken]`) |
| `POST /Account/Logout` | oui | Logout (`[ValidateAntiForgeryToken]`) | MVC |
| `GET /health` | non | Healthcheck ASP.NET Core (`app.MapHealthChecks("/health")`) | REST |

**Swagger / OpenAPI** : capability `openapi` — `Swashbuckle.AspNetCore` → UI sur `/swagger`. Pertinent UNIQUEMENT si l'app expose des endpoints API au-dela des `Controllers/Api/*DataController` DevExtreme (qui ne sont PAS exposes en API publique).

---

## 4. Versioning des API

`/api/{domain}` pour les Controllers DataApi (consommes par widgets DevExtreme — pas d'API publique versionnee). Si l'app expose une vraie API publique : ajouter `/api/v1/{domain}` sur un Controller separe + capability `openapi`.

---

## 5. Interdits projet (aspnet-mvc-razor)

**Architecture** :
- Logique metier dans Controller → toujours via Service
- Acces direct EF Core depuis Controller → toujours via Service
- Acces direct EF Core depuis Razor View — preparer ViewModel dans Controller
- Mapping inline dans Controller / Service → toujours via AutoMapper Profile
- Validation manuelle `if (string.IsNullOrEmpty(model.Email)) ...` → FluentValidation `AbstractValidator<T>`
- `[ValidateAntiForgeryToken]` manquant sur Controller POST/PUT/DELETE
- `@Html.AntiForgeryToken()` manquant dans un `<form method="post">` Razor
- `Html.Raw(user_input)` ou `@Html.Raw(Model.UserComment)` — XSS garanti
- DevExtreme widget bound a un IEnumerable<T> en memoire alors qu'il y a un Service IQueryable<T> (perd le server-side filter/sort/page)
- Loader `DataSourceLoader.Load(query.ToList(), opts)` (force materialisation avant filter) — utiliser `DataSourceLoader.LoadAsync(query, opts)` sur `IQueryable<T>` brut

**Code quality** :
- `Console.WriteLine` → toujours `_logger.LogInformation(...)` (Serilog)
- `object` injustifie dans signatures (utiliser le type concret ou un generic)
- `async void` (sauf event handlers)
- `TODO`, `FIXME` dans le code livre
- Imports stars `using Microsoft.AspNetCore.*` → toujours explicites

**Securite** :
- Cookies sans `HttpOnly` ou sans `Secure` en prod
- Connection string DB en dur hors `appsettings.json` section `ConnectionStrings`
- Secret JWT / Azure AD client_secret en dur (toujours `appsettings.json` section dediee, peuplee par arch depuis `stack.md`)
- Log de body request complet contenant PII (mot de passe, token, email — utiliser `Serilog.Filters.Expressions` pour exclure)
- CORS configure en `AllowAnyOrigin()` (ce stack est monolithe SSR → pas besoin de CORS public ; cf. `library-and-stack.md` Partie B)

**EF Core / ORM** :
- `DbContext.Set<T>().Where(...).ToList()` sans pagination sur table volumineuse — toujours `IQueryable<T>` exposed via Service + `DataSourceLoader` (qui pagine server-side)
- N+1 query (loop de `FindAsync`) — utiliser `Include` ou projection AutoMapper
- `Database.EnsureCreated()` ou Migrations EF → INTERDIT (Database-First exclusif)
- Auto-tracking sur queries read-only — utiliser `.AsNoTracking()` sur GETs

**Razor / Views** :
- Logique conditionnelle complexe dans `.cshtml` — preparer un flag boolean dans ViewModel
- Iteration imbriquee profonde dans Razor — projeter une structure flatten cote AutoMapper
- `@Html.Raw(...)` sur user input → toujours `@Model.UserComment` (auto-escape)
- HTML genere par concatenation de strings cote Service — toujours via partial view + ViewComponent

**Build** :
- Commit `bin/`, `obj/`, `appsettings.Development.json` (avec secrets), `wwwroot/lib/devextreme/` (assets generes)

---

## 6. Persistance

- **Mode EF Core Database-First** : identique a `.sdd/stacks/backend/dotnet-minimalapi.md §8`
- **Driver** selon `DatabaseType` (cf. §2.4.b on-demand)
- **DataSource config** : `ConnectionStrings:Default` dans `appsettings.json` peuple par arch depuis `## Active Database`

---

## 7. DevExtreme — cas d'usage canoniques

| Cas | Widget DevExtreme | Pattern serveur |
|---|---|---|
| Liste paginee/filtrable | `DataGrid` | DataApi Controller + `DataSourceLoader.LoadAsync(query, opts)` |
| Form edit (create/update) | `Form` + `ValidationGroup` | Controller MVC `[HttpPost] [ValidateAntiForgeryToken]` + FluentValidation |
| Dashboard graphique | `Chart`, `PieChart`, `Funnel` | DataApi Controller (donnees agregees server-side) |
| Planning / Agenda | `Scheduler` | DataApi + entites `*Appointment` mapped |
| Tree (hierarchie) | `TreeList` | DataApi + recursive query (CTE SQL ou `DataSourceLoader` group) |
| Upload fichier | `FileUploader` | Controller MVC `[HttpPost] IFormFile` (stockage `wwwroot/uploads/` OU Azure Blob) |
| Selection ressource | `Lookup`, `DropDownBox` | DataApi avec `?searchValue=...` (DataSourceLoader filter) |
| Export Excel cote client | `DataGrid.Export` | Cote client (JS lib `exceljs`) OU server-side via capability `excel` (ClosedXML) |

**Anti-pattern** : recreer manuellement filter/sort/pagination dans un Controller alors que `DataSourceLoader` le fait gratuitement sur `IQueryable<T>`.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Apps d'entreprise CRUD** orientees data-grid (back-office, ERP, GMAO, applications metier)
- **Equipes .NET classiques** habituees a ASP.NET MVC 5 → ASP.NET Core MVC est une transition naturelle
- **Apps brownfield** : migration d'un ASP.NET MVC 5 Framework existant vers .NET 10 sans refonte SPA
- **Apps avec besoins UX riches sans SPA** : DevExtreme couvre 90% des besoins (grids, charts, scheduler, forms)
- **Deploiement IIS / Windows Server** classique (sans Docker obligatoire)

**NE PAS choisir si** :
- ❌ Equipe non DevExpress / pas de licence DevExtreme commerciale → choisir `frontend/react.md` ou autre stack libre
- ❌ UX mobile-first PWA, offline-first → SPA + service workers
- ❌ Animations / interactions JS complexes hors DevExtreme widgets → `frontend/react.md` + `ui/shadcn.md`
- ❌ Serverless (Lambda, Cloud Functions) — ASP.NET Core cold start tolerable mais DevExtreme assets lourds → `node-react.md`
- ❌ Pas de SQL (NoSQL strict) — EF Core supporte mal, choisir un autre ORM ou stack
- ❌ Equipe full-Linux non Windows et pas de licence DevExtreme — choisir stack libre

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `aspnet-mvc-razor` + `auth-local` + `qa-dotnet-xunit` + `SqlServer` | 🟡 experimental | jamais valide end-to-end |
| `aspnet-mvc-razor` + `auth-azure-ad` + `qa-dotnet-xunit` + `SqlServer` | 🟡 experimental | viable (capability azure-ad) |
| `aspnet-mvc-razor` + `auth-local` + `qa-dotnet-xunit` + `PostgreSql` (capability db-postgres) | 🟡 experimental | viable |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` = `fullstack/aspnet-mvc-razor.md` → **ignorer** `BackendName` et `LibName` (WARNING `[STACK_MALFORMED]` si declares)
2. **Creer** UN seul projet via `dotnet new mvc --framework net10.0` (cf. §2.2.1)
3. **Composer** `appsettings.json` depuis `## Active Database` + `## Active Auth Specs` + `## Active SMTP Server`. Materialiser les valeurs **en clair** dans les sections natives ASP.NET (`ConnectionStrings:Default`, `AzureAd:*`, `Smtp:*`) sans substitution `${DB_*}` ni env var runtime (Pattern B `library-and-stack.md §0`).
4. **`## Active UI Specs`** : aucun design system SDD_Pro (Radzen, Vuetify, shadcn) n'est applicable — UI fournie par DevExtreme. Si declare → WARNING bloquant `[STACK_INCOMPAT]`.
5. **Capabilites recommandees** : `azure-ad` (si auth corporate), `excel` + `pdf` (export tres frequent), `redis-cache` (apps multi-instance), `logging-file` (audit prod)
6. **Phase B (DB scaffolding)** : selon `DatabaseType` — `dotnet ef dbcontext scaffold "{connStr}" {Provider} -o Data/Entities --context AppDbContext --context-dir Data --use-database-names --no-onconfiguring -f` (identique a `backend/dotnet-minimalapi.md §8.3`)
7. **Phase C (ADRs)** : creer `ADR-{ts}-stack-aspnet-mvc-razor.md` documentant ASP.NET Core MVC + Razor + DevExtreme + DataSourceLoader pattern
8. **Assets DevExtreme client** : par defaut, CDN unpkg ajoute dans `_Layout.cshtml` (POC rapide). Documenter dans ADR pour migration vers libman / npm cote prod.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack est lu par **les deux agents** dev-* (analogue `kotlin-mustache.md`). Frontiere moins nette : le rendu UI vit cote serveur (Razor + HtmlHelpers DevExtreme).

**Convention de repartition** :

- `dev-backend` materialise : Controllers (MVC + DataApi), Services, AppDbContext, Entities, ViewModels, AutoMapper Profiles, Validators FluentValidation, config (`Program.cs` augment), `appsettings.json` (augment), `{AppName}.csproj` (augment deps on-demand)
- `dev-frontend` materialise : Razor Views (`Views/**/*.cshtml`), Layout (`_Layout.cshtml`), partials, statiques (`wwwroot/css/**`, `wwwroot/js/**`, `wwwroot/images/**`), HtmlHelpers DevExtreme dans les vues

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/Controllers/**` | `dev-backend` |
| `workspace/src/{AppName}/Services/**` | `dev-backend` |
| `workspace/src/{AppName}/Data/**` | `dev-backend` (Entities scaffoldees par arch en Phase B, augment par dev-backend) |
| `workspace/src/{AppName}/Models/**` | `dev-backend` (ViewModels) |
| `workspace/src/{AppName}/Mappers/**` | `dev-backend` |
| `workspace/src/{AppName}/Validators/**` | `dev-backend` |
| `workspace/src/{AppName}/Views/**/*.cshtml` | `dev-frontend` |
| `workspace/src/{AppName}/wwwroot/**` | `dev-frontend` |
| `workspace/src/{AppName}/Program.cs` | `arch` (create) + `dev-backend` (augment) |
| `workspace/src/{AppName}/appsettings.json` | `arch` (create exclusif) |
| `workspace/src/{AppName}/{AppName}.csproj` | `arch` (create) + `dev-backend` (augment deps on-demand) |

**Cas frontiere — ViewModel passe a la vue** : un Controller MVC dans `dev-backend` cree un ViewModel + appelle `return View(viewModel)`. La vue `Views/{Domain}/{Action}.cshtml` cote `dev-frontend` declare `@model {AppNamespace}.Models.{Domain}{Action}ViewModel` et consomme `@Model.PropName`. **Contrat partage** : nom et type du ViewModel + ses proprietes. Toute modification d'un cote DOIT etre synchronisee (equivalent `[FRONTEND_BACKEND_CONTRACT_GAP]`).

**Cas DevExtreme HtmlHelper** : le widget DevExtreme dans la vue Razor (`@(Html.DevExtreme().DataGrid()...)`) reference :
- Un **type ViewModel** (`DataGrid<UserListItemViewModel>`) → owned par `dev-backend`
- Un **Controller DataApi** (`.Controller("UsersData")` + `.LoadAction("List")`) → owned par `dev-backend`

`dev-frontend` cree la vue, mais le contrat de bind (nom Controller + LoadAction + type ViewModel) DOIT correspondre au Controller materialise par `dev-backend`. Le `code-reviewer` flag `[FRONTEND_BACKEND_CONTRACT_GAP]` si le widget reference un Controller/Action inexistant.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}
dotnet build {AppName}.csproj --nologo
test -f {AppName}.csproj
test -f Program.cs
test -f Views/_ViewImports.cshtml
test -f appsettings.json
grep -q "DevExtreme.AspNet.Mvc" {AppName}.csproj
grep -q "DevExtreme.AspNet.Data" {AppName}.csproj
grep -q "Microsoft.EntityFrameworkCore" {AppName}.csproj
grep -q "@addTagHelper \*, DevExtreme.AspNet.Mvc" Views/_ViewImports.cshtml
echo "smoke OK"
```

Smoke complet (~60s) : `dotnet run --project {AppName}.csproj --urls http://localhost:5099` puis `curl -sf http://localhost:5099/` doit retourner 200 (page d'accueil Razor avec assets DevExtreme charges depuis `_Layout.cshtml`).

---

## 13. Pieges runtime documentes

| Bug | Symptome | Cause | Fix |
|---|---|---|---|
| **HtmlHelper DevExtreme rend rien** | `@(Html.DevExtreme().DataGrid()...)` produit du HTML vide en page | `@addTagHelper *, DevExtreme.AspNet.Mvc` absent de `_ViewImports.cshtml` | Verifier la directive (STEP 4 init) |
| **DataSourceLoader 500** | XHR `/api/users/List?filter=...` retourne 500 | `loadOptions` mal bind (querystring custom non parsee) | Verifier signature `[FromQuery] DataSourceLoadOptions loadOptions` |
| **Auto-tracking N+1** | Logs SQL multiplies sur GET liste | DbContext tracke entities en lecture, EF re-fetch chaque relation lazy | `.AsNoTracking()` sur la query exposee au `DataSourceLoader` |
| **CSRF AJAX widget DevExtreme** | POST DevExtreme renvoie 400 antiforgery | Token CSRF non envoye par le widget XHR par defaut | Configurer `ConfigureAntiforgery` pour accepter le header `RequestVerificationToken` OU exempter le DataApi `[IgnoreAntiforgeryToken]` (uniquement endpoints en GET pure) |
| **DevExtreme version mismatch client/server** | Widgets s'affichent cassees ou erreur JS console | `DevExtreme.AspNet.Mvc` (NuGet) version ≠ assets JS (CDN/libman) | Aligner les deux a la version pinnee §2.4.a (`25.1.5` par defaut) |

---

## 14. Source historique

Stack initial 2026-06-10 — modele sur `fullstack/blazor-server.md` (monolithe .NET SSR) + `backend/dotnet-minimalapi.md` (Database-First EF Core + AutoMapper). Pattern DevExtreme + DataSourceLoader = canonical de l'ecosysteme DevExpress pour ASP.NET Core MVC. Pre-requis : licence DevExpress (DevExtreme.AspNet.Data + .Mvc sont libres MIT, mais les assets client DevExtreme JS requierent une licence commerciale au-dela des composants OSS).
