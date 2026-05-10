# Tech Spec: blazorserver (monolithe)

Status: Draft
Tech Spec ID: tech-blazorserver
Scope: application Blazor Server .NET 10 — monolithe UI + logique metier + acces donnees

---

## 1. Architecture

### 1.1 Pattern global
Application monolithique Blazor Server. Pas de separation frontend/backend : l'UI, la logique metier, l'acces aux donnees et l'authentification vivent dans le meme processus ASP.NET Core. Organisation modulaire par domaine fonctionnel.

### 1.2 Pattern applicatif
MVC + MVVM hybride via code-behind :
`Page (.razor) → Code-behind (.razor.cs) → Service → Mapper → Entity → DbContext → SQL Server`.
Aucun acces direct BDD depuis l'UI. Aucun mapping manuel hors des Mappers AutoMapper.

### 1.3 Couches

- **UI** : Pages + Components + Layouts. Responsabilite = presentation. Depend de : Services.
- **Services** : logique metier. Contrat dans `Services/Interfaces/`, implementation dans `Services/Implementations/`. Depend de : Mappers, DbContext.
- **Mappers** : profils AutoMapper (Entity → Model). Depend de : Entities, Models.
- **Data** : Entities + DbContext. Acces EF Core uniquement.
- **Middleware** : gestion globale des exceptions, transformation en reponse UI coherente.

### 1.4 Mapping couche → repertoire

- Page → `workspace/output/src/{AppName}/Pages/`
- Component → `workspace/output/src/{AppName}/Components/`
- Layout → `workspace/output/src/{AppName}/Shared/`
- Service (interface) → `workspace/output/src/{AppName}/Services/Interfaces/`
- Service (implementation) → `workspace/output/src/{AppName}/Services/Implementations/`
- Model → `workspace/output/src/{AppName}/Models/`
- Entity → `workspace/output/src/{AppName}/Data/Entities/`
- DbContext → `workspace/output/src/{AppName}/Data/DBcontext/`
- Mapper → `workspace/output/src/{AppName}/Mappers/`
- Middleware → `workspace/output/src/{AppName}/Middleware/`
- Auth → `workspace/output/src/{AppName}/Auth/`
- Config application → `workspace/output/src/{AppName}/Program.cs`
- Racine Razor → `workspace/output/src/{AppName}/App.razor`, `workspace/output/src/{AppName}/_Imports.razor`
- Ressources `.resx` → `workspace/output/src/{AppName}/Resources/`
- Statique web → `workspace/output/src/{AppName}/wwwroot/`
- Project file → `workspace/output/src/{AppName}/{AppName}.csproj`

### 1.5 Principes non negociables

**SOLID — appliques obligatoirement a chaque classe generee :**
- **S — Single Responsibility** : chaque classe a une seule raison de changer. Un Service ne fait pas de mapping ; un Mapper ne fait pas de logique metier ; une Page ne fait pas d'appel BDD.
- **O — Open/Closed** : etendre par nouveaux services / interfaces, ne pas modifier les implementations existantes pour ajouter un comportement.
- **L — Liskov** : toute implementation d'un `IXxxService` peut remplacer une autre sans briser les appelants.
- **I — Interface Segregation** : `IXxxService` expose UNIQUEMENT les methodes utilisees par ses consommateurs. Pas de methode generique fourre-tout.
- **D — Dependency Inversion** : les Pages/Components dependent de `IXxxService` (abstraction), jamais de `XxxService` (concret). Les Services dependent de `IDbContextFactory` (abstraction), jamais de `AppDbContext` directement injecte.

**Clean Code — regles appliquees a chaque fichier genere :**
- Methodes courtes : une methode = une action. Si une methode depasse ~20 lignes, la decomposer.
- Noms explicites : le nom d'une variable / methode / classe doit se comprendre sans commentaire.
- Pas de "magic numbers" / "magic strings" : toute constante metier est nommee.
- Pas de code mort : pas de methode jamais appelee, pas de parametre jamais utilise.
- Pas de duplication : si le meme bloc apparait 2 fois → methode privee ou helper.

**Regles architecturales :**
- Aucune logique metier dans Pages ou Components. La logique UI vit dans le code-behind `.razor.cs`.
- Aucun acces DbContext direct depuis l'UI → toujours via un Service injecte.
- Aucun mapping manuel dans Pages, Components ou Services → AutoMapper centralise dans les Mappers.
- DI systematique pour tout acces externe (DbContext, HttpClient, IStringLocalizer, services metier).
- Entites EF Core jamais modifiees manuellement (classes partielles sinon).
- Services retournent des Models, jamais des Entities.
- `try/catch` de formatage UI interdit dans Pages et Services — role exclusif du middleware global.
- Multilingue via `IStringLocalizer` + `.resx`, jamais en dur dans les composants.
- **Lifecycle navigation** : `NavigationManager.NavigateTo(...)` DOIT etre appele dans `OnAfterRender(bool firstRender)` avec garde `if (firstRender)`, ou dans un event handler utilisateur. **Jamais** dans `OnInitialized` / `OnInitializedAsync` / `OnParametersSet` — Blazor Server .NET 8+ leve `NavigationException` depuis ces cycles. Cette contrainte s'applique a toute redirection conditionnelle automatique (page de garde, composant `RedirectToLogin`, page `Index` qui redirige vers un menu par defaut).
- **Infos utilisateur** : pour tout acces aux donnees de l'utilisateur courant (identifiant, nom, email, groupes), passer par le service scoped `UserAd` (voir `tech-auth-azure.md` §5.3). Pas d'acces direct a `AuthenticationStateProvider` dans le code-behind hors du point de chargement initial ; pas de lecture ad-hoc de claims eparpillee dans les composants.

---

## 2. Stack

### 2.1 Identite
- **Stack ID** : `app-blazor-server`
- **Langage** : C# 12
- **Runtime** : .NET 10.0 (`net10.0`)
- **Framework principal** : ASP.NET Core 10.0 — Blazor Server
- **Namespace racine** : `{AppNamespace}`

### 2.2 Outils
- **Project file** : `workspace/output/src/{AppName}/{AppName}.csproj`
- **Build** : `dotnet build workspace/output/src/{AppName}/{AppName}.csproj --nologo` (project-scoped, jamais solution-wide ; autorise les builds paralleles entre stacks)
- **Smoke Command** : `dotnet run --project workspace/output/src/{AppName}/{AppName}.csproj --no-build --urls http://localhost:5099 & APP_PID=$!; sleep 4; curl -sf http://localhost:5099/ -o /dev/null; RC=$?; kill $APP_PID 2>/dev/null; wait $APP_PID 2>/dev/null; exit $RC`
- **Smoke Timeout** : 60s
- **Preserves identifier syntax** : `\b<id>\b` (mot entier, sensible a la casse)
- **Lint / Format** : `dotnet format`
- **Type-check** : integre au build
- **Package manager** : NuGet
- **Test** : hors scope du framework SDD Lite

### 2.2.1 Init Commands (executes par `init_project.skill.md` si `project_file` absent)

```bash
# Garde-fou idempotent : STEPS 1 a 2c sont DESTRUCTIVES (`dotnet new --force` ecrase
# Program.cs, App.razor, _Host.cshtml ; rm -f / rm -rf suppriment des fichiers ;
# sed -i les modifie). Si le csproj existe deja, le projet a deja ete scaffolde
# et augmente par les agents — re-executer STEPS 1-2c effacerait tout le code
# genere. STEPS 3-6 (dotnet add package, mkdir -p, restore, build, audit) sont
# nativement idempotents et restent hors du guard.
if [ ! -f "workspace/output/src/{AppName}/{AppName}.csproj" ]; then

# STEP 1 — Scaffold du projet Blazor Server
# Note: le template blazorserver plafonne a net6.0 dans dotnet SDK 10.0.2xx. On scaffold en net6.0
# puis on retarget le csproj vers net10.0 — l'architecture legacy Blazor Server (Razor Pages + SignalR
# hub + _Host.cshtml) reste pleinement supportee en net10. Cette approche preserve les identifiants
# Program.cs attendus (AddRazorPages, AddServerSideBlazor, MapBlazorHub, MapFallbackToPage).
dotnet new blazorserver -n {AppName} -o workspace/output/src/{AppName} --framework net6.0 --no-restore --force

# STEP 1b/2/2b/2c — Cleanup template demo files + retarget net10.
# IMPORTANT (v2.21.6) : ces edits NE SONT PAS faits via `sed -i` / `rm -rf` en bash.
# Le harness Claude Code refuse les commandes destructives composees (sed inline +
# rm chained) et bloque le pipeline (post-mortem 2026-05-02 Demo).
# A la place, l'agent orchestrant `init_project.skill.md` execute les edits via les
# tools natifs Read + Edit + Write (atomiques, granulaires, prompt-able un par un)
# et les suppressions via `rm` simples (un fichier par appel). La sequence requise :
#
#   a) Edit  workspace/output/src/{AppName}/{AppName}.csproj
#        old_string: <TargetFramework>net6.0</TargetFramework>
#        new_string: <TargetFramework>net10.0</TargetFramework>
#   b) Edit  workspace/output/src/{AppName}/Program.cs
#        retire `using {AppNamespace}.Data;`
#        retire la ligne `builder.Services.AddSingleton<WeatherForecastService>();`
#   c) Edit  workspace/output/src/{AppName}/Pages/Index.razor
#        retire la ligne `<SurveyPrompt Title="..." />`
#   d) Bash  rm -f workspace/output/src/{AppName}/Pages/Counter.razor       (un appel)
#   e) Bash  rm -f workspace/output/src/{AppName}/Pages/FetchData.razor     (un appel)
#   f) Bash  rm -f workspace/output/src/{AppName}/Shared/SurveyPrompt.razor (un appel)
#   g) Bash  rm workspace/output/src/{AppName}/Data/WeatherForecast.cs workspace/output/src/{AppName}/Data/WeatherForecastService.cs && rmdir workspace/output/src/{AppName}/Data
#
# STEP 3+ ci-dessous (dotnet add package, mkdir, restore, build, audit) restent
# nativement idempotents et tournent en bash sans probleme.

fi  # fin garde-fou idempotent (csproj absent)

# STEP 3 — Ajouter les packages declares en §2.4 (au-dela du template blazorserver de base)
#
# REGLE DE VERSIONING (conforme a la politique librairies inlined dans .claude/agents/arch.md) :
# - Packages avec compatibilite validee a une version specifique : pinnes.
# - Packages a cycle CVE frequent (notamment Microsoft.Identity.Web qui emet
#   regulierement des advisories NU1902) : NON PINNES — `dotnet add package`
#   sans `--version` resout automatiquement la DERNIERE VERSION STABLE
#   compatible avec le TargetFramework declare (net10.0 apres STEP 1b).
#   Ainsi le framework ne se periment pas et reste au-dessus des CVE connues.
#   STEP 6 (audit vulnerabilites) valide apres coup qu'aucun NU1902 ne reste.

dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore.SqlServer --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore.Design --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.EntityFrameworkCore.Tools --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package AutoMapper --version 16.1.1
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Radzen.Blazor --version 10.2.3
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Serilog.AspNetCore --version 10.0.0
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Serilog.Sinks.Console --version 6.1.1

# Microsoft.Identity.Web : NON PINNE — derniere version stable compatible net10.
# Corrige automatiquement CVE GHSA-rpq8-q44m-2rpg (present dans 3.x) et toute
# CVE future sans intervention manuelle sur le stack spec.
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.Identity.Web
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.Identity.Web.UI

# STEP 4 — Creer les repertoires de couches vides (evite les erreurs de chemin lors de la premiere generation)
mkdir -p workspace/output/src/{AppName}/Services/Interfaces
mkdir -p workspace/output/src/{AppName}/Services/Implementations
mkdir -p workspace/output/src/{AppName}/Models
mkdir -p workspace/output/src/{AppName}/Data/Entities
mkdir -p workspace/output/src/{AppName}/Data/DBcontext
mkdir -p workspace/output/src/{AppName}/Mappers
mkdir -p workspace/output/src/{AppName}/Middleware
mkdir -p workspace/output/src/{AppName}/Auth
mkdir -p workspace/output/src/{AppName}/Resources

# STEP 5 — Restore + build de verification (doit etre vert avant toute generation)
dotnet restore workspace/output/src/{AppName}/{AppName}.csproj
dotnet build workspace/output/src/{AppName}/{AppName}.csproj --nologo

# STEP 6 — Audit vulnerabilites NuGet (cf. politique inlined dans agents/arch.md : 0 warning libs)
# Si au moins une vulnerabilite subsiste malgre les non-pinnings (le registre NuGet
# n'a pas encore publie de version corrigee), la faire remonter au Tech Lead sans
# bloquer le build — il decidera d'un lockfile ou d'un package override.
vuln_count=$(dotnet list workspace/output/src/{AppName}/{AppName}.csproj package --vulnerable --include-transitive 2>&1 | grep -c '>')
if [ "$vuln_count" -gt 0 ]; then
  echo "WARN: $vuln_count vulnerable package(s) apres install — voir dotnet list --vulnerable"
  dotnet list workspace/output/src/{AppName}/{AppName}.csproj package --vulnerable --include-transitive
fi
```

**Contrat post-init :** `workspace/output/src/{AppName}/{AppName}.csproj` DOIT exister, le build DOIT etre vert.
Microsoft.Identity.Web + Microsoft.Identity.Web.UI sont installes en **version flottante latest
stable compatible net10** (pas de `--version` pin) — resout automatiquement CVE GHSA-rpq8-q44m-2rpg
et toute vulnerabilite future a la prochaine init. STEP 6 (audit `dotnet list --vulnerable
--include-transitive`) emet un WARN si au moins une vulnerabilite subsiste (cas rare :
registre NuGet pas encore patche pour une CVE fraiche — decision Tech Lead).

Les fichiers generes par `dotnet new` conserves (`Program.cs`, `App.razor`, `Shared/MainLayout.razor`,
`Pages/Index.razor`, `_Host.cshtml`) seront **augmentes** par les agents (operation: augment) avec
`preserves:` declarant leurs identifiants courants : `AddRazorPages`, `AddServerSideBlazor`,
`MapBlazorHub`, `MapFallbackToPage`.

**Historique du fix init harness-friendly (v2.21.6, 2026-05-02)** : la version
precedente du STEP 1b/2/2b/2c utilisait `sed -i` + `rm -rf` chaines dans une
unique commande bash. Le harness Claude Code refuse ce pattern (commande
destructive composee non auditeable) et le pipeline `/dev-code` bloquait
sur `init_project.skill.md` avec une denial Permission cote bash. Fix : les
edits de fichiers passent par Read+Edit (atomiques, granulaires) et les
suppressions par des appels `rm` simples un fichier a la fois. Aucun changement
fonctionnel sur le projet genere — meme post-condition (`{AppName}.csproj`
existe, build vert, demo files supprimes).

**Historique du fix net10 (v2.9 → v2.10)** : le template `blazorserver` est plafonne a net7.0 dans
le SDK dotnet 10+ (`--framework net10.0` rejete avec "template supports only net6.0/net7.0/
netcoreapp3.1"). STEP 1 scaffold donc en net7.0 ; STEP 1b retarget via `sed` vers net10.0.
L'architecture legacy Blazor Server (Razor Pages + SignalR hub + `_Host.cshtml`) reste pleinement
supportee en net10 — les APIs `AddRazorPages`, `AddServerSideBlazor`, `MapBlazorHub`,
`MapFallbackToPage` ne sont PAS deprecues. Cette approche preserve integralement le contrat
d'augmentation declare par les tasks generees par la Specification Agent, contrairement au
template moderne `dotnet new blazor --interactivity Server` qui utilise `AddRazorComponents` +
`MapRazorComponents` + `AddInteractiveServerRenderMode` — APIs differentes, preserves list
invalidee, regeneration complete des tasks exigee.

### 2.3 Patterns d'erreurs compilation
Format standard .NET : `{file}({line},{col}): error {code}: {message}`.
Codes prioritaires : CS0246, CS0103, CS1061, CS1002, CS1003, CS1513, CS0029, CS0266, CS0161, CS7036.

### 2.4 Librairies

Appliquer `la politique librairies inlined dans .claude/agents/arch.md` (derniere version stable compatible .NET 10).

| Nom | Version | Role |
|-----|---------|------|
| Microsoft.AspNetCore.Components.Web | 10.0.6 | Runtime Blazor Server |
| Microsoft.EntityFrameworkCore | 10.0.6 | ORM principal |
| Microsoft.EntityFrameworkCore.SqlServer | 10.0.6 | Provider SQL Server |
| Microsoft.EntityFrameworkCore.Design | 10.0.6 | Conception / scaffolding |
| Microsoft.EntityFrameworkCore.Tools | 10.0.6 | Outils `dotnet ef` |
| AutoMapper | 16.1.1 | Mapping Entity → Model |
| Radzen.Blazor | 10.2.3 | Composants UI Material |
| Serilog.AspNetCore | 10.0.0 | Logging structure |
| Serilog.Sinks.Console | 6.1.1 | Sink console |

Les dependances Azure AD sont declarees dans `tech-auth-azure.md`.

### 2.5 Conventions de nommage
- Classes / proprietes : `PascalCase`
- Variables / parametres : `camelCase`
- Constantes : `PascalCase`
- Champs prives : `_camelCase`
- Fichiers : `PascalCase.cs`
- Interfaces : `IPascalCase`
- Pages : `PascalCase.razor` + code-behind obligatoire `PascalCase.razor.cs` + CSS isole `PascalCase.razor.css`
- Components : `PascalCase.razor` (fichier unique autorise ; code-behind optionnel)
- Layouts : `PascalCase.razor` dans `Shared/`, herite de `LayoutComponentBase`

**Convention OBLIGATOIRE de nommage des artefacts metier** :
Nom de fichier / classe = `{NomEntite}` + **UN SEUL suffixe fonctionnel** (deux mots max au total).
Ne jamais accumuler plusieurs suffixes (`PointVenteListItemOutputDto` = INTERDIT).

| Artefact | Suffixe | Exemple |
|---|---|---|
| Model de lecture / edition | `Model` | `PointVenteModel` |
| Item de liste (projection legere) | `ListItemModel` | `PointVenteListItemModel` |
| Filtre de recherche | `Filter` | `PointVenteFilter` |
| Resultat pagine | `ListPage` | `PointVenteListPage` |
| Service — interface | `I{Entite}Service` | `IPointVenteService` |
| Service — implementation | `{Entite}Service` | `PointVenteService` |
| Profil AutoMapper | `{Entite}Mapper` | `PointVenteMappingProfile` |
| Entity EF Core | nom table en PascalCase | `PointVente` |

**INTERDIT dans le contexte Blazor Server monolithe** (ces suffixes appartiennent au stack API) :
`Dto`, `InputDto`, `OutputDto`, `OutputLiteDto`, `LiaisonReadDto`, `Response`, `Request`, `Result`.
Tout fichier genere avec un de ces suffixes = violation de convention = erreur de generation.

---

## 3. Structure obligatoire des Pages

Chaque Page DOIT etre composee de trois fichiers co-localises dans le meme repertoire :

- `NomPage.razor` — HTML Razor + composants + binding. Aucune logique metier.
- `NomPage.razor.cs` — code-behind : logique UI, appels services, gestion d'etat. Aucun acces BDD direct.
- `NomPage.razor.css` — CSS scope par composant.

Organisation par module fonctionnel : `Pages/PointsVente/PointVenteList.razor(+cs+css)`, `Pages/PointsVente/PointVenteEdit.razor(+cs+css)`, etc.

Les Components reutilisables vivent sous `Components/` (fichier unique `.razor` suffisant).

---

## 4. Base de donnees

- **Moteur** : Microsoft SQL Server
- **Acces** : Entity Framework Core, approche Database-First, scaffolding incremental
- **Migrations** : `dotnet ef dbcontext scaffold` en mode continuation (ne jamais regenerer depuis zero, ne jamais supprimer des entites existantes)
- **DbContext** : `AppDbContext` dans `workspace/output/src/{AppName}/Data/DBcontext/`
- **Strategie de scaffolding** : verifier les entites existantes, generer uniquement les tables manquantes, etendre le DbContext avec les nouveaux `DbSet`, conserver les configurations existantes
- **Tables initiales** : `point_vente` (liste incrementale)
- **Variables d'environnement requises** (conformes a `.claude/rules/env_rules.md`) : `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

### 4.1 Commandes de scaffolding EF Core

Lire `DatabaseType` dans `workspace/input/tech/stack.md ## Project Config` et executer
la commande correspondante. **Toutes les valeurs de connexion proviennent
exclusivement des variables d'environnement — jamais en dur.**

Resoudre les placeholders `{AppName}`, `{AppNamespace}` depuis
`## Project Config` avant d'executer.

#### SQLServer (`DatabaseType: SQLServer`)

```bash
# Prerequis : Microsoft.EntityFrameworkCore.SqlServer deja declare en §2.4
CONN="Server=${DB_HOST},${DB_PORT};Database=${DB_NAME};User Id=${DB_USER};Password=${DB_PASSWORD};Encrypt=False;TrustServerCertificate=True;"

dotnet ef dbcontext scaffold "$CONN" \
  Microsoft.EntityFrameworkCore.SqlServer \
  --project workspace/output/src/{AppName}/{AppName}.csproj \
  --context AppDbContext \
  --context-dir Data/DBcontext \
  --output-dir Data/Entities \
  --namespace {AppNamespace}.Data.Entities \
  --context-namespace {AppNamespace}.Data.DBcontext \
  --no-onconfiguring \
  --force \
  --no-build
```

#### PostgreSQL (`DatabaseType: PostgreSQL`)

```bash
# Prerequis : ajouter le package si absent
dotnet add workspace/output/src/{AppName}/{AppName}.csproj \
  package Npgsql.EntityFrameworkCore.PostgreSQL --version 9.0.4

CONN="Host=${DB_HOST};Port=${DB_PORT};Database=${DB_NAME};Username=${DB_USER};Password=${DB_PASSWORD};"

dotnet ef dbcontext scaffold "$CONN" \
  Npgsql.EntityFrameworkCore.PostgreSQL \
  --project workspace/output/src/{AppName}/{AppName}.csproj \
  --context AppDbContext \
  --context-dir Data/DBcontext \
  --output-dir Data/Entities \
  --namespace {AppNamespace}.Data.Entities \
  --context-namespace {AppNamespace}.Data.DBcontext \
  --no-onconfiguring \
  --force \
  --no-build
```

#### MySQL (`DatabaseType: MySQL`)

```bash
# Prerequis : ajouter le package si absent
dotnet add workspace/output/src/{AppName}/{AppName}.csproj \
  package Pomelo.EntityFrameworkCore.MySql --version 9.0.0

CONN="Server=${DB_HOST};Port=${DB_PORT};Database=${DB_NAME};Uid=${DB_USER};Pwd=${DB_PASSWORD};"

dotnet ef dbcontext scaffold "$CONN" \
  Pomelo.EntityFrameworkCore.MySql \
  --project workspace/output/src/{AppName}/{AppName}.csproj \
  --context AppDbContext \
  --context-dir Data/DBcontext \
  --output-dir Data/Entities \
  --namespace {AppNamespace}.Data.Entities \
  --context-namespace {AppNamespace}.Data.DBcontext \
  --no-onconfiguring \
  --force \
  --no-build
```

**Regles de scaffolding incremental (non negociables) :**
- `--no-onconfiguring` : TOUJOURS. Evite que le mot de passe soit ecrit dans `AppDbContext` genere.
- `--force` : regenere les entites existantes. Ne supprime pas les entites hors scope.
- Ne JAMAIS regenerer la totalite du schema depuis zero.
- Ne JAMAIS supprimer manuellement un fichier Entity genere existant.
- Apres scaffold, verifier que `AppDbContext` declare un `DbSet<T>` pour chaque nouvelle entite.
- Les entites generees (`Data/Entities/`) ne sont jamais editees manuellement — utiliser des classes partielles.

**Pattern typage d'entite obligatoire (EF Core Database-First)** :

- Le type CLR de chaque propriete d'entite DOIT correspondre exactement au type SQL de la colonne source. En Database-First, ne JAMAIS deviner le type ni defaulter a `string?` : inspecter le schema de la table cible (ex. via `sp_columns`, `INFORMATION_SCHEMA.COLUMNS`, ou un `dotnet ef dbcontext scaffold` initial) avant d'ecrire l'entite a la main.
- Correspondance stricte SQL Server → CLR :
  - `INT` / `INT NOT NULL` → `int` / `int?`
  - `BIGINT` → `long` / `long?`
  - `DECIMAL(p,s)` / `NUMERIC` → `decimal` / `decimal?`
  - `FLOAT` → `double` / `double?`
  - `REAL` → `float` / `float?`
  - `BIT` → `bool` / `bool?`
  - `DATETIME2` / `DATETIME` → `DateTime` / `DateTime?`
  - `DATE` → `DateOnly` / `DateOnly?`
  - `UNIQUEIDENTIFIER` → `Guid` / `Guid?`
  - `VARCHAR` / `NVARCHAR` → `string` / `string?` (+ `[MaxLength]`)
- **Convention DB legacy (bases historiques courantes)** : les colonnes `actif`, `is_*`, `has_*`, `enabled`, `flag_*` et autres booleens metier sont typiquement stockes en `INT` (0/1), **PAS** en `BIT`. Une entite qui declare `bool` sur une colonne `INT` leve `InvalidCastException: Unable to cast object of type 'System.Int32' to type 'System.Boolean'` au premier `SqlDataReader.GetBoolean(i)`. Regle : toujours inspecter le schema reel avant de choisir entre `bool` et `int` ; ne pas presumer `BIT` sur la base du nom ou de la semantique.
- **Pattern d'adaptation int → bool au niveau projection** : quand l'entite declare `int` (conforme DB) mais le DTO / UI attendent `bool` (semantique metier), convertir dans la projection LINQ via `Actif = pv.Actif == 1` (traduit en SQL `CASE WHEN pv.actif = 1 THEN 1 ELSE 0 END` sans round-trip client). Les comparaisons dans les sous-requetes (`.Any(... && pe.Actif == 1)`) utilisent la forme int. Cote ecriture, les services assignent des litteraux int (`entity.Actif = 1`, `pv.Actif = 0`), jamais `true` / `false`.
- Symptomes d'un mismatch :
  - `SqlException: Conversion failed when converting the varchar value '...' to data type int` → la propriete est declaree `string?` mais la colonne est `INT`.
  - `InvalidCastException: Unable to cast object of type 'System.Int32' to type 'System.Decimal'` a `SqlDataReader.GetDecimal` → la propriete est declaree `decimal?` mais la colonne est `INT`.
  - `InvalidCastException: Unable to cast object of type 'System.String' to type 'System.Guid'` → propriete `Guid?` sur colonne `VARCHAR`.
- Pour une table de reference (ex. `reference_lookup` avec une cle numerique `numero_label INT` + une colonne d'affichage `valeur_label VARCHAR`), la **cle de jointure** est la colonne numerique, la **colonne d'affichage** est la varchar. La FK dans la table metier pointe vers la cle numerique. Le LINQ JOIN DOIT cibler la cle numerique (`on pv.FkRef equals rl.NumeroLabel`) et NON la colonne d'affichage (`on pv.FkRef equals rl.ValeurLabel`). La colonne d'affichage ne sert qu'au `select` final de projection.

**Pattern UI pour les listes de reference (Blazor Server + Radzen)** :

- Les DTOs d'option d'un dropdown portent `Id` au type natif de la cle (int si FK vers table de reference), et `Label` en `string` pour l'affichage.
- Les `Filter` / `Model` de formulaire portent les FKs au meme type natif (int / int?), JAMAIS en string.
- RadzenDropDown : `ValueProperty="Id"`, `TextProperty="Label"` ; le `@bind-Value` cible une propriete du Filter / Model au bon type.
- Une liste d'options extraite d'une colonne free-text (ex. pays en varchar non normalise) utilise un service dedie `GetXxxAsync(): Task<IReadOnlyList<string>>` (DISTINCT + ORDER BY cote DB) et un dropdown avec `TValue="string"` sans `ValueProperty`.

**Pattern DbContext obligatoire (Blazor Server)** :

- Enregistrement : `builder.Services.AddDbContextFactory<AppDbContext>(options => options.UseSqlServer(...))`. **Jamais** `AddDbContext<>` seul en Blazor Server : le DbContext scope vit pour toute la duree du circuit SignalR (~= toute la session utilisateur) et sera partage entre tous les appels concurrents (Task.WhenAll, charges paralleles depuis un composant) → `InvalidOperationException: A second operation was started on this context instance before a previous operation completed`.
- Injection dans les Services : `IDbContextFactory<AppDbContext> dbFactory`. Chaque methode cree son propre DbContext via `await using var db = await _dbFactory.CreateDbContextAsync()`. Aucun field `_db` de type `AppDbContext` partage entre methodes.
- Helpers qui prennent un DbContext : passer `AppDbContext` en parametre (methode static ou privee sur la meme classe) plutot que de creer un nouveau DbContext a l'interieur — chaque call chain d'une methode publique partage UN DbContext local.
- Effet : `Task.WhenAll(4 reads)` devient legal cote consommateur car chaque read obtient son propre DbContext.

**Patterns LINQ obligatoires (EF Core 10 translation)** :

- **LEFT JOIN** : utiliser une sous-requete correlee `.Where(...).Select(x => x.Prop).FirstOrDefault()` pour les champs optionnels (ex. libelle depuis une table de reference nullable). **Jamais** le pattern `join ... into grp + from x in grp.DefaultIfEmpty() + (x != null → x.Prop : null)` : EF Core ne traduit pas cette composition quand elle est combinee avec `OrderBy` ou une autre projection en aval → exception `The LINQ expression could not be translated`.
- **Projection de liste** : projeter dans la requete EF vers un **type anonyme**, puis materialiser vers un record / DTO cote client apres `ToListAsync()`. Ne jamais ecrire `select new XxxRecord(...)` (positionnel) si la requete porte ensuite un `OrderBy` par propriete : EF re-projette tout le record dans le `OrderBy` et casse la traduction SQL.
- **Exploite / exists** : sous-requete `.Any(...)` inline est supportee dans la projection, a condition que la projection soit un type anonyme (pas un record positionnel).
- **Count + Skip/Take** : evaluer `CountAsync()` sur la requete avec anonyme projete, puis `Skip/Take/ToListAsync()` sur la meme requete ; ne pas re-construire la requete entre-temps.

La chaine de connexion est construite au runtime a partir de ces variables. Aucune valeur en dur, aucun fichier de configuration secret. Fail-fast au demarrage si une variable manque.

---

## 5. Interdits projet (blazorserver)

- Secrets, cles d'API, mots de passe en dur
- Chaines de connexion litterales (cle/valeur ou URI)
- Hotes litteraux (`localhost`, IP) lies au host BDD dans un Service
- Lecture de credentials BDD depuis un fichier (`.env`, `appsettings*.json` secrets, etc.)
- Logique metier dans une Page ou un Component
- Acces `DbContext` direct depuis une Page ou un Component → toujours via un Service
- Mapping manuel dans Pages, Components ou Services (centralise dans Mappers AutoMapper)
- Modification manuelle des Entities generees par EF (classes partielles sinon)
- Suppression automatique d'entites EF existantes
- Regeneration complete des Entities depuis zero
- Ecrasement d'un DbSet existant du DbContext lors d'une mise a jour de scaffolding
- Services retournant des Entities (toujours des Models)
- Instanciation manuelle d'un service (`new UserService()`) → toujours via DI (`AddScoped<IUserService, UserService>`)
- `Console.WriteLine` ou `Console.Log` → utiliser Serilog
- Traductions codees en dur dans les composants → utiliser `.resx` via `IStringLocalizer<Resource>`
- **Fichier `.resx` par composant** (`PointVenteList.fr.resx`, `AppHeader.fr.resx`, etc.) → INTERDIT. Un SEUL fichier partage `Resource.resx` + `.{culture}.resx` accompagne d'une classe marker `Resource.cs`, injecte via `IStringLocalizer<Resource>` dans tous les composants (voir §7)
- `IStringLocalizer<T>` avec `T` = classe de composant (`IStringLocalizer<PointVenteList>`) → INTERDIT. `T` = toujours `Resource` (marker class unique). Le framework .NET cherche le fichier ressource qui matche le type, donc un type par composant force un fichier par composant.
- Exception brute exposee a l'UI (toujours interceptee par le middleware global)
- Log de `DB_PASSWORD` ou de la chaine de connexion complete
- `dynamic` / `object` non justifie
- Appels statiques a des librairies a effet de bord depuis un Service
- Page sans code-behind (`.razor.cs` obligatoire pour toute Page ; les Components sont exemptes)
- CSS global ciblant les classes d'une Page → toujours isole via `.razor.css`
- Valeurs Azure AD (`TenantId`, `ClientId`, `Authority`, `Domain`) en dur dans le code
- `NavigationManager.NavigateTo(...)` dans `OnInitialized` / `OnInitializedAsync` / `OnParametersSet` / `OnParametersSetAsync` → leve `NavigationException` en Blazor Server .NET 8+. Utiliser `OnAfterRender(firstRender)` ou un event handler.
- **`<a href="...">` pour la navigation interne Blazor** → INTERDIT. Cause un rechargement complet de la page (SPA cassee, perte de l'etat SignalR). Utiliser `<NavLink href="...">` (natif Blazor, ajoute la classe CSS `active` automatiquement) ou `<RadzenLink Path="...">` (design system Radzen). Exception unique : les liens externes (https://...) peuvent utiliser `<a href target="_blank">`.
- **Nommage non conforme** : generer un fichier avec un suffixe non liste dans §2.5 (`Dto`, `InputDto`, `OutputDto`, `Result`, `Response`, `Request`, `LiaisonReadDto`, `OutputLiteDto`) → INTERDIT dans le contexte Blazor Server monolithe. Tout ecart = erreur de generation.
- **SOLID violation** : generer un Service qui retourne des Entities au lieu de Models (violation S + D), une Page qui contient de la logique metier (violation S), un constructeur qui instancie ses dependances avec `new` au lieu de DI (violation D) → INTERDIT.
- Requete EF Core projetant `select new XxxRecord(a, b, c, ...)` (record positionnel) suivie d'un `OrderBy(r => r.Prop)` ou d'un `CountAsync()` → casse la traduction SQL. Projeter vers un type anonyme dans la requete, materialiser en record cote client apres `ToListAsync()`.
- `AddDbContext<AppDbContext>` en Blazor Server → le DbContext scope est partage sur toute la duree du circuit SignalR et ne supporte pas les operations concurrentes. Utiliser `AddDbContextFactory<AppDbContext>` et injecter `IDbContextFactory<AppDbContext>` dans les Services (voir §4 pattern DbContext).
- Field `private readonly AppDbContext _db` dans un Service cote Blazor Server → impose un DbContext partage entre toutes les methodes du service, retombe dans le bug concurrent des que deux methodes sont appelees en parallele. Chaque methode cree son propre DbContext via la factory.
- LEFT JOIN via `join ... into grp + from x in grp.DefaultIfEmpty() + (x != null → x.Prop : null)` → non traduit par EF Core 10 en composition avec OrderBy. Utiliser une sous-requete correlee `.Where(...).Select(x => x.Prop).FirstOrDefault()`.
- Propriete d'entite scaffolde avec un type CLR qui ne correspond pas au type SQL de la colonne source → provoque `SqlException: Conversion failed` (varchar vs int), `InvalidCastException` (int vs decimal, string vs Guid, etc.) a la premiere lecture. Verifier le schema de la table cible avant d'ecrire l'entite a la main (voir §4 pattern typage d'entite).
- JOIN sur une table de reference via la colonne d'affichage (varchar) au lieu de la cle numerique (int) → genere `Conversion failed` au runtime. Le JOIN DOIT cibler la cle de la table de reference ; la colonne d'affichage ne sert qu'au `select` de projection.
- Modele de formulaire / filtre declarant une reference FK en `string` alors que la FK est numerique → l'UI passe la valeur affichee (label) au service, qui ne correspond pas a la cle numerique attendue par le JOIN.
- Propriete `decimal?` sur colonne `INT`, ou `int?` sur colonne `DECIMAL`, ou tout autre mismatch de precision numerique → genere `InvalidCastException` au `SqlDataReader.Get{Decimal|Int32|...}(i)`. Chaque propriete numerique DOIT refleter le type exact de la colonne (int / long / decimal / float / double), pas une estimation.
- Propriete `bool` sur colonne `INT` (convention DB legacy courante : `actif`, `is_*`, `has_*`, `enabled` stockes en `0/1 INT` et non en `BIT`) → `InvalidCastException: Int32 → Boolean` au premier read. L'entite DOIT declarer `int` ; la conversion vers `bool` se fait dans la projection LINQ (`Actif = pv.Actif == 1`) et les litteraux d'ecriture sont `0` / `1`, jamais `true` / `false`.
- Lecture directe de claims (`authState.User.FindFirst(...)`) eparpillee dans plusieurs composants au lieu de passer par le service scoped `UserAd` (voir `tech-auth-azure.md` §5.3)
- `TODO`, `FIXME`, code commente, placeholders (`TBD`, `changeme`, `foo`, `bar`)

---

## 6. Authentification

L'authentification Azure AD suit `tech-auth-azure.md` §5.3 (integration Blazor Server : OIDC cookie + `AddMicrosoftIdentityWebApp`, flow redirect-based, pas de MSAL popup, pas de JWT Bearer). Le middleware d'auth est branche dans `Program.cs`, les pages protegees utilisent `[Authorize]` ou `<AuthorizeView>` selon granularite.

---

## 7. Multilingue

### 7.1 Pattern obligatoire : UNE SEULE ressource partagee

La convention .NET standard est **UN fichier ressource partage** pour tous
les libelles de l'application, **pas un fichier par composant**. Mauvaise
pratique interdite (voir §5) : creer `PointVenteList.fr.resx`,
`AppHeader.fr.resx`, `UserPopup.fr.resx` — un par composant.

Structure correcte dans `workspace/output/src/{AppName}/Resources/` :

```
workspace/output/src/{AppName}/Resources/
+-- Resource.cs          # classe marker vide
+-- Resource.resx        # default (langue principale = francais)
+-- Resource.fr.resx     # francais (facultatif si francais = default)
+-- Resource.en.resx     # anglais
+-- Resource.es.resx     # espagnol
```

**Marker class** `Resources/Resource.cs` :

```csharp
namespace {AppNamespace}.Resources;

// Marker class for IStringLocalizer<Resource>.
// All application string resources live in the accompanying Resource.*.resx files.
public sealed class Resource { }
```

### 7.2 Enregistrement dans `Program.cs`

```csharp
builder.Services.AddLocalization(options => options.ResourcesPath = "Resources");

// Middleware de culture (entre UseRouting et UseAuthentication)
var supportedCultures = new[] { "fr", "en", "es" };
var localizationOptions = new RequestLocalizationOptions()
    .SetDefaultCulture(supportedCultures[0])
    .AddSupportedCultures(supportedCultures)
    .AddSupportedUICultures(supportedCultures);
app.UseRequestLocalization(localizationOptions);
```

### 7.3 Consommation dans les composants

TOUS les composants injectent `IStringLocalizer<Resource>` → **jamais** `IStringLocalizer<NomDuComposant>`.

```razor
@using {AppNamespace}.Resources
@inject IStringLocalizer<Resource> L

<RadzenButton Text="@L["PointVente.Action.Create"]" />
```

Ou en code-behind :

```csharp
[Inject] protected IStringLocalizer<Resource> L { get; set; } = default!;
```

### 7.4 Convention de nommage des cles

Cles namespacees par domaine fonctionnel dans l'unique `Resource.resx` :

- `Menu.PointsVente`, `Menu.Perimetres`, `Menu.Redevances`
- `PointVente.List.Title`, `PointVente.Action.Create`, `PointVente.Action.Export`
- `PointVente.Column.IdPdv`, `PointVente.Column.Enseigne`
- `Common.Reset`, `Common.Cancel`, `Common.Save`
- `Validation.Required`, `Validation.FormatInvalide`

### 7.5 Changement de langue

Le parametre de requete optionnel `?culture=fr|en|es` force la culture courante via le middleware `UseRequestLocalization`. Un composant de selection de langue peut aussi appeler une action serveur qui redefinit le cookie `.AspNetCore.Culture` pour persister le choix.

---

## 8. Templates de code obligatoires (first-shot delivery)

Les patterns ci-dessous ont ete valides en execution reelle. Le Developer Agent
DOIT les repliquer (en adaptant noms de domaines / entites / services) au lieu
de reinventer un equivalent. Toute deviation DOIT etre justifiee par une AC du
task qui explique pourquoi le template standard ne s'applique pas.

### 9.1 Template `Program.cs` → bootstrap monolithe complet

```csharp
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Identity.Web;
using Microsoft.Identity.Web.UI;
using Microsoft.EntityFrameworkCore;
using Serilog;
using {AppNamespace}.Auth;
using {AppNamespace}.Data.DBcontext;
using {AppNamespace}.Middleware;
using Radzen;

Log.Logger = new LoggerConfiguration().WriteTo.Console().CreateBootstrapLogger();

try
{
    var builder = WebApplication.CreateBuilder(args);

    builder.Host.UseSerilog((ctx, services, cfg) =>
        cfg.ReadFrom.Configuration(ctx.Configuration).WriteTo.Console());

    AzureAdConfigBinder.BindFromEnvironment(builder.Configuration);

    var connectionString = BuildConnectionString();

    // Blazor Server: AddDbContextFactory, jamais AddDbContext. Voir §4.
    builder.Services.AddDbContextFactory<AppDbContext>(options =>
        options.UseSqlServer(connectionString));

    builder.Services.AddAuthentication(OpenIdConnectDefaults.AuthenticationScheme)
        .AddMicrosoftIdentityWebApp(builder.Configuration.GetSection("AzureAd"));

    builder.Services.AddControllersWithViews().AddMicrosoftIdentityUI();

    AddAuthorizationPolicies(builder.Services, builder.Configuration);

    builder.Services.AddCascadingAuthenticationState();
    builder.Services.AddScoped<UserAd>();

    builder.Services.AddRazorPages();
    builder.Services.AddServerSideBlazor();
    builder.Services.AddAutoMapper(cfg => cfg.AddMaps(typeof(Program).Assembly));
    builder.Services.AddRadzenComponents();

    // Localisation : UNE SEULE ressource partagee Resource.
    builder.Services.AddLocalization(options => options.ResourcesPath = "Resources");

    // Registrer ici les services metier (scoped) :
    // RegisterXxxServices(builder.Services);

    var app = builder.Build();

    if (!app.Environment.IsDevelopment())
    {
        app.UseExceptionHandler("/Error");
        app.UseHsts();
    }

    app.UseHttpsRedirection();
    app.UseStaticFiles();
    app.UseMiddleware<GlobalExceptionMiddleware>();

    app.UseRouting();

    // Culture avant auth pour que les messages auth soient localises.
    var supportedCultures = new[] { "fr", "en", "es" };
    app.UseRequestLocalization(new RequestLocalizationOptions()
        .SetDefaultCulture(supportedCultures[0])
        .AddSupportedCultures(supportedCultures)
        .AddSupportedUICultures(supportedCultures));

    app.UseAuthentication();
    app.UseAuthorization();

    app.MapControllers();
    app.MapBlazorHub();
    app.MapFallbackToPage("/_Host");

    app.Run();
}
catch (Exception ex) when (ex is not HostAbortedException)
{
    Log.Fatal(ex, "Application terminated unexpectedly");
}
finally
{
    Log.CloseAndFlush();
}

static string RequireEnv(string name)
{
    var v = Environment.GetEnvironmentVariable(name);
    if (string.IsNullOrWhiteSpace(v))
        throw new InvalidOperationException($"Missing required environment variable: {name}");
    return v;
}

static string BuildConnectionString()
{
    var dbName = RequireEnv("DB_NAME");
    var dbUser = RequireEnv("DB_USER");
    var dbPassword = RequireEnv("DB_PASSWORD");
    var dbHost = RequireEnv("DB_HOST");
    var dbPort = RequireEnv("DB_PORT");
    return $"Server={dbHost},{dbPort};Database={dbName};User Id={dbUser};Password={dbPassword};TrustServerCertificate=True;";
}

static void AddAuthorizationPolicies(IServiceCollection services, IConfiguration configuration)
{
    services.AddAuthorization(opt =>
    {
        // FallbackPolicy: default-deny. Toutes routes non-[AllowAnonymous] requierent auth.
        opt.FallbackPolicy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build();

        var groups = configuration.GetSection("Authorization:Groups").Get<Dictionary<string, string>>() ?? new();
        foreach (var (name, guid) in groups)
        {
            // Guard obligatoire : placeholders vides degradent vers "authentifie seul" pour eviter un loop d'autorisation.
            if (string.IsNullOrWhiteSpace(guid))
                opt.AddPolicy(name, p => p.RequireAuthenticatedUser());
            else
                opt.AddPolicy(name, p => p.RequireClaim("groups", guid));
        }
    });
}
```

### 9.2 Template Service → pattern `IDbContextFactory` + LINQ safe

Toute methode qui touche la BDD suit ce squelette. Le field `_dbFactory` est
le SEUL point d'acces ; chaque methode cree son propre `DbContext` local.

```csharp
using AutoMapper;
using Microsoft.EntityFrameworkCore;
using {AppNamespace}.Data.DBcontext;

namespace {AppNamespace}.Services.Implementations;

public sealed class XxxService : IXxxService
{
    private readonly IDbContextFactory<AppDbContext> _dbFactory;
    private readonly IMapper _mapper;

    public XxxService(IDbContextFactory<AppDbContext> dbFactory, IMapper mapper)
    {
        _dbFactory = dbFactory;
        _mapper = mapper;
    }

    public async Task<XxxListPage> GetListAsync(XxxFilter filter)
    {
        await using var db = await _dbFactory.CreateDbContextAsync();

        // 1) Projection vers TYPE ANONYME (pas record positionnel).
        // 2) LEFT JOIN via sous-requete correlee (.Where(...).Select(...).FirstOrDefault()).
        // 3) EXISTS via .Any() inline.
        var query =
            from a in db.TableA
            join b in db.TableB on a.FkB equals b.Id
            select new
            {
                a.Id,
                BLibelle = b.Libelle ?? string.Empty,
                OptionalC = db.TableC
                    .Where(c => c.Fk == a.Id)
                    .Select(c => c.Label)
                    .FirstOrDefault(),
                HasSomething = db.TableD.Any(d => d.FkA == a.Id && d.Actif)
            };

        // Filtres dynamiques appliques avant Skip/Take.
        if (filter.Xxx.HasValue)
            query = query.Where(r => r.Id == filter.Xxx.Value);

        // OrderBy sur proprietes du type anonyme (jamais sur un record).
        query = query.OrderBy(r => r.Id);

        var totalCount = await query.CountAsync();

        var pageSize = filter.PageSize > 0 → filter.PageSize : 20;
        var page = filter.Page > 0 → filter.Page : 1;

        var rows = await query
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync();

        // Materialisation cote client vers DTO/Model.
        var items = _mapper.Map<List<XxxListItemDto>>(rows);

        return new XxxListPage { Items = items, TotalCount = totalCount, Page = page, PageSize = pageSize };
    }

    // Helper prive static : partage un DbContext passe par la methode appelante.
    // PAS de creation de DbContext a l'interieur d'un helper.
    private static Task<bool> ValidateXxx(AppDbContext db, string value, int groupId)
    {
        return db.TableC.AnyAsync(c => c.GroupId == groupId && c.Label == value);
    }
}
```

### 9.3 Template Page Razor → trio `.razor` + `.razor.cs` + `.razor.css`

**`Pages/Xxx/XxxList.razor`** (vue, pas de logique metier) :

```razor
@page "/xxx"
@attribute [Authorize(Policy = AuthorizationPolicies.XxxLecture)]
@inherits XxxListBase

<PageTitle>@L["Xxx.List.Title"]</PageTitle>

<RadzenDataGrid TItem="XxxListItemDto"
                Data="@PageResult?.Items"
                Count="@(PageResult?.TotalCount ?? 0)"
                IsLoading="@IsLoading"
                AllowPaging="true"
                PageSize="@Filter.PageSize"
                LoadData="@OnLoadData">
    <Columns>
        <RadzenDataGridColumn TItem="XxxListItemDto" Property="Id" Title="@L["Xxx.Id"]" />
        <!-- autres colonnes -->
    </Columns>
</RadzenDataGrid>
```

**`Pages/Xxx/XxxList.razor.cs`** (code-behind, delegue aux services, ZERO logique metier, ZERO LINQ, ZERO DbContext) :

```csharp
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.Localization;
using {AppNamespace}.Models;
using {AppNamespace}.Services.Interfaces;
using Radzen;

namespace {AppNamespace}.Pages.Xxx;

public class XxxListBase : ComponentBase
{
    [Inject] protected IXxxService XxxService { get; set; } = default!;
    [Inject] protected IStringLocalizer<Resource> L { get; set; } = default!;

    protected XxxFilter Filter { get; set; } = new();
    protected XxxListPage? PageResult { get; set; }
    protected bool IsLoading { get; set; }

    // Chaque reference list obtient son propre DbContext via factory → Task.WhenAll OK.
    protected override async Task OnInitializedAsync()
    {
        await Task.WhenAll(LoadRef1Async(), LoadRef2Async());
    }

    protected async Task OnLoadData(LoadDataArgs args)
    {
        IsLoading = true;
        Filter.Page = args.Skip.HasValue && Filter.PageSize > 0
            → (args.Skip.Value / Filter.PageSize) + 1
            : 1;
        if (args.Sorts?.Any() == true)
        {
            var s = args.Sorts.First();
            Filter.SortColumn = s.Property;
            Filter.SortDescending = s.SortOrder == SortOrder.Descending;
        }
        PageResult = await XxxService.GetListAsync(Filter);
        IsLoading = false;
    }

    private async Task LoadRef1Async() { /* await XxxService.GetRef1Async(); */ }
    private async Task LoadRef2Async() { /* await XxxService.GetRef2Async(); */ }
}
```

**`Pages/Xxx/XxxList.razor.css`** (CSS scope, pas de global) :

```css
.xxx-list {
    padding: 1rem;
}
```

### 9.4 Template composant redirection auth → `Shared/RedirectToLogin.razor`

```razor
@namespace {AppNamespace}.Shared
@inject NavigationManager NavigationManager

@code {
    // OnAfterRender(firstRender) OBLIGATOIRE. OnInitialized leve NavigationException.
    protected override void OnAfterRender(bool firstRender)
    {
        if (firstRender)
        {
            NavigationManager.NavigateTo("/MicrosoftIdentity/Account/SignIn", forceLoad: true);
        }
    }
}
```

### 9.5 Template routeur → `App.razor`

```razor
<Router AppAssembly="@typeof(App).Assembly">
    <Found Context="routeData">
        <AuthorizeRouteView RouteData="@routeData" DefaultLayout="@typeof(Shared.MainLayout)">
            <NotAuthorized Context="authContext">
                @* DISCRIMINATION OBLIGATOIRE : sans ca = loop infini pour utilisateur authentifie hors groupe *@
                @if (authContext.User.Identity?.IsAuthenticated != true)
                {
                    <RedirectToLogin />
                }
                else
                {
                    <LayoutView Layout="@typeof(Shared.MainLayout)">
                        <p role="alert">Acces refuse : votre compte n'appartient pas au groupe requis pour cette page.</p>
                    </LayoutView>
                }
            </NotAuthorized>
        </AuthorizeRouteView>
        <FocusOnNavigate RouteData="@routeData" Selector="h1" />
    </Found>
    <NotFound>
        <PageTitle>Not found</PageTitle>
        <LayoutView Layout="@typeof(Shared.MainLayout)">
            <p role="alert">Sorry, there's nothing at this address.</p>
        </LayoutView>
    </NotFound>
</Router>
```

### 9.6 Template `appsettings.json`

Placeholders vides obligatoires pour `Authorization:Groups`. Aucun GUID de
production. La section `AzureAd` reste ABSENTE (alimentee via env vars, §2).

```json
{
  "Logging": { "LogLevel": { "Default": "Information", "Microsoft.AspNetCore": "Warning" } },
  "Serilog": { "MinimumLevel": { "Default": "Information", "Override": { "Microsoft": "Warning", "System": "Warning" } } },
  "AllowedHosts": "*",
  "Authorization": {
    "Groups": {
      "XxxLecture": "",
      "XxxEcriture": ""
    }
  }
}
```

### 9.7 Pattern de resolution des infos utilisateur

Pour tout besoin de lire le nom, l'email ou les groupes de l'utilisateur
courant, passer par `UserAd` (defini dans `tech-auth-azure.md` §5.3). Le
code-behind suit ce squelette :

```csharp
[Inject] private UserAd User { get; set; } = default!;
[Inject] private AuthenticationStateProvider AuthState { get; set; } = default!;

protected override async Task OnInitializedAsync()
{
    await User.EnsureLoadedAsync(AuthState);
    // Utiliser User.Name, User.Email, User.Groups, User.IsInGroup("<guid>") partout
}
```

PAS d'acces direct a `authState.User.FindFirst(...)` dans les composants.

---

## 9. Hors scope technique

- Pas de separation frontend/backend (monolithe par conception)
- Pas de client SPA (Blazor WASM / React / Vue) → UI 100% rendue serveur via SignalR
- Pas d'API REST publique consommee par un client tiers
- Pas de cache distribue
- Pas de microservices
- Pas de Server-Sent Events custom (SignalR hub gere par Blazor Server)

