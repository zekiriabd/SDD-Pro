# Tech FEAT: blazor (frontend)

> §2.4 (Librairies) régénérée depuis `blazor-webassembly.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id blazor-webassembly`).

Status: Stable
Validation: 🟢 reference (validated combo — dotnet-minimalapi + blazor + radzen + azure-ad)
Tech FEAT ID: tech-blazor
Scope: frontend uniquement (Blazor WebAssembly)

---

## 1. Architecture

### 1.1 Pattern applicatif
Blazor WebAssembly SPA consommant les APIs backend via des contrats Refit
typés, avec politiques de resilience Polly.

### 1.2 Couches

- **Page** : composant Blazor route via `@page`. Logique UI minimale.
- **Component** : composant reutilisable sans route.
- **Layout** : composant heritant de `LayoutComponentBase`.
- **Service client** : interface Refit + `AuthorizationMessageHandler` + Polly.
- **Auth config** : code MSAL / redirect vers login, integre au routing.
- **Resources** : fichiers `.resx` multilingue.

Les modeles de donnees (DTO, `ApiResponse<T>`) sont partages avec le backend
via le projet `{LibName}` (voir `tech-minimalapi.md`).

### 1.3 Mapping couche → repertoire
- Page → `workspace/output/src/{AppName}/Pages/`
- Component → `workspace/output/src/{AppName}/Components/`
- Layout → `workspace/output/src/{AppName}/Layouts/`
- Service client (Refit) → `workspace/output/src/{AppName}/Services/`
- Auth / MSAL config → `workspace/output/src/{AppName}/Auth/`
- Shared (RedirectToLogin etc.) → `workspace/output/src/{AppName}/Shared/`
- Ressources `.resx` → `workspace/output/src/{AppName}/Resources/`
- Racine statique → `workspace/output/src/{AppName}/wwwroot/`
- Project → `workspace/output/src/{AppName}/{AppName}.csproj`
- Config app → `workspace/output/src/{AppName}/Program.cs`
- Config Razor globale → `workspace/output/src/{AppName}/_Imports.razor`, `workspace/output/src/{AppName}/App.razor`

### 1.4 Principes non negociables
- Aucune logique metier dans les composants au-dela de l'orchestration UI.
- Aucun appel `HttpClient` brut : toujours via un contrat Refit enregistre.
- Aucune politique de retry / circuit breaker ecrite a la main : Polly.
- Aucun `Console.WriteLine` cote navigateur : Serilog.
- Traductions via `IStringLocalizer` + `.resx`, jamais codees en dur dans les composants.

---

## 2. Stack

### 2.1 Identite
- **Stack ID** : `front-blazor-wasm`
- **Langage** : C# 12
- **Runtime** : .NET 10 WebAssembly (le code C# s'execute dans le navigateur)
- **Framework principal** : Blazor WebAssembly
- **Namespace racine** : `{AppNamespace}`

### 2.2 Outils
- **Project file** : `workspace/output/src/{AppName}/{AppName}.csproj`
- **Build** : `dotnet build workspace/output/src/{AppName}/{AppName}.csproj --nologo` (project-scoped, not solution-wide; allows parallel builds across stacks)
- **Smoke Command** : `dotnet publish workspace/output/src/{AppName}/{AppName}.csproj -c Debug --no-build --nologo -o /tmp/sim-fe-smoke && test -f /tmp/sim-fe-smoke/wwwroot/_framework/blazor.boot.json`
- **Smoke Timeout** : 90s
- **Preserves identifier syntax** : `\b<id>\b` (mot entier, sensible à la casse)
- **Lint / Format** : `dotnet format`
- **Type-check** : integre au build
- **Package manager** : NuGet
- **Test** : hors scope du framework SDD Lite (QA exclu)

### 2.2.1 Init Commands (executes par `init_project.skill.md` si `project_file` absent)

```bash
# Garde-fou idempotent : STEPS 1 a 3b sont DESTRUCTIVES (`dotnet new --force` ecrase
# Program.cs, App.razor, _Imports.razor ; mv renomme Layout/ ; rm -f / rm -rf
# suppriment des fichiers ; sed -i modifie NavMenu.razor). Si le csproj existe deja,
# le projet a ete scaffolde et augmente par les agents — re-executer STEPS 1-3b
# effacerait tout le code genere. STEPS 4-8 (dotnet add reference/package, mkdir -p,
# restore, build, audit) sont nativement idempotents et restent hors du guard.
if [ ! -f "workspace/output/src/{AppName}/{AppName}.csproj" ]; then

# STEP 1 — Scaffold du projet Blazor WebAssembly
# Le template `blazorwasm` supporte directement net10.0 dans le SDK dotnet 10
# (contrairement a `blazorserver` plafonne a net7.0). Pas de retarget.
dotnet new blazorwasm -n {AppName} -o workspace/output/src/{AppName} --framework net10.0 --no-restore --force

# STEP 2 — Aligner la convention de repertoires sur §1.3 du stack
# Le template cree `Layout/` mais §1.3 declare `Layouts/` (au pluriel).
# Renomme pour que les agents generant des fichiers Layout tombent au bon endroit.
mv "workspace/output/src/{AppName}/Layout" "workspace/output/src/{AppName}/Layouts"

# STEP 3 — Supprimer le boilerplate demo
# Counter et Weather sont les exemples par defaut du template ; sample-data/ contient
# le payload JSON de demo. Tout cela serait genant pour les agents (CS0234,
# RZ10012, conflit de routes) et ne doit pas survivre a l'init.
rm -f "workspace/output/src/{AppName}/Pages/Counter.razor"
rm -f "workspace/output/src/{AppName}/Pages/Weather.razor"
rm -rf "workspace/output/src/{AppName}/wwwroot/sample-data"

# STEP 3b — Nettoyer NavMenu.razor : retirer les liens vers Counter et Weather
# (restent les liens vers Home et eventuellement les routes ajoutees par les features).
# Substitution multi-ligne simple : on supprime les <div class="nav-item"> qui referencent counter/weather.
sed -i '/href="counter"/,/<\/div>/d' "workspace/output/src/{AppName}/Layouts/NavMenu.razor"
sed -i '/href="weather"/,/<\/div>/d'  "workspace/output/src/{AppName}/Layouts/NavMenu.razor"

# STEP 3c — Injecter le script MSAL dans wwwroot/index.html (post-mortem 2026-05-03)
# Le package Microsoft.Authentication.WebAssembly.Msal expose
# `_content/Microsoft.Authentication.WebAssembly.Msal/AuthenticationService.js` qui
# DOIT etre charge AVANT `_framework/blazor.webassembly.js`. Sans cette ligne, au
# premier rendu d'un composant authentifie le runtime jette
# `Could not find 'AuthenticationService.init'`. Le template `dotnet new blazorwasm`
# ne l'injecte pas (seul `blazorwasm-msal` le fait, mais on ne l'utilise pas ici).
sed -i 's|^\(\s*\)\(<script src="_framework/blazor\.webassembly#\)|\1<script src="_content/Microsoft.Authentication.WebAssembly.Msal/AuthenticationService.js"></script>\n\1\2|' \
  "workspace/output/src/{AppName}/wwwroot/index.html"

# STEP 3d — Creer wwwroot/appsettings.json avec Api:BaseAddress (post-mortem 2026-05-03)
# Sans ce fichier, la SPA appelle des endpoints sur sa propre URL d'hebergement au
# lieu du Backend (cf. agent-frontend.instructions.md STEP 4.6). Aucun secret ici,
# uniquement l'URL de base de l'API. Surcharge ulterieure par feature si besoin.
if [ ! -f "workspace/output/src/{AppName}/wwwroot/appsettings.json" ]; then
cat > "workspace/output/src/{AppName}/wwwroot/appsettings.json" <<'EOF'
{
  "Api": {
    "BaseAddress": "https://localhost:7238/"
  }
}
EOF
fi

# STEP 3e — Injecter les shims JS+CSS des stacks UI actifs (post-mortem 2026-05-03)
# Chaque design system Blazor (Radzen, MudBlazor, Syncfusion, Fluent UI Blazor) ship
# son propre script JS qui DOIT etre charge AVANT `_framework/blazor.webassembly.js`,
# plus son CSS de theme. Sans ces ressources :
# - Radzen : `Could not find 'Radzen.preventArrows'` au premier render
# - MudBlazor : `Could not find 'mudPopover'` au runtime
# - etc.
# On grep `workspace/input/tech/stack.md ## Active UI Specs` (lignes non commentees) et on
# injecte les shims correspondants. Reference par stack : §4.1 du fichier UI.
ACTIVE_UI=$(grep -E '^- \.claude/stacks/ui/' workspace/input/tech/stack.md 2>/dev/null | grep -v '^#' || true)

if echo "$ACTIVE_UI" | grep -q 'radzen-blazor.md'; then
  # Radzen.Blazor.js avant blazor.webassembly.js
  sed -i 's|^\(\s*\)\(<script src="_framework/blazor\.webassembly#\)|\1<script src="_content/Radzen.Blazor/Radzen.Blazor.js"></script>\n\1\2|' \
    "workspace/output/src/{AppName}/wwwroot/index.html"
  # CSS theme Radzen dans <head> (default = material-base ; le projet peut
  # surcharger en augmentant index.html via une feature ulterieure)
  sed -i 's|^\(\s*\)\(<link href="{AppName}\.styles\.css"\)|\1<link rel="stylesheet" href="_content/Radzen.Blazor/css/material-base.css" />\n\1\2|' \
    "workspace/output/src/{AppName}/wwwroot/index.html"
fi

# Pattern repliquable pour MudBlazor (si jamais utilise) :
# if echo "$ACTIVE_UI" | grep -q 'mudblazor.md'; then
#   sed -i 's|^\(\s*\)\(<script src="_framework/blazor\.webassembly#\)|\1<script src="_content/MudBlazor/MudBlazor.min.js"></script>\n\1\2|' \
#     "workspace/output/src/{AppName}/wwwroot/index.html"
# fi

# STEP 3f — Bootstrap auth Azure AD (si auth/azure-ad actif) [post-mortem 2026-05-XX]
# Couvre les 5 pieges canoniques Azure AD documentes dans auth/azure-ad.md §5.2 :
#   - Piege 1 : shim JS MSAL → deja injecte STEP 3c
#   - Piege 2 : Api:BaseAddress → deja cree STEP 3d
#   - Piege 3 : AuthorizationMessageHandler → genere par dev-frontend (Auth/)
#   - Piege 4 : fetch /api/config/auth dans Program.cs → applique par dev-frontend
#               (pattern Program.cs documente dans auth/azure-ad.md §5.2 Piege 4)
#   - Piege 5 : auth globale + page /authentication/{action} + AllowAnonymous →
#               COUVERT ICI (fichiers infrastructure, jamais modifies apres creation)
#
# Le STEP 3f cree les fichiers framework qui ne dependent d'aucune feature :
#   - Pages/Authentication.razor : handler MSAL des callbacks /authentication/{action}
#   - Shared/RedirectToLogin.razor : redirection auto vers MSAL pour pages [Authorize]
#   - _Imports.razor augmente : @attribute [Authorize] global + using Authorization
#
# Les fichiers App.razor et Program.cs ne sont PAS touches ici : ils sont generes
# par dev-frontend selon son plan inline et doivent suivre les patterns canoniques
# de auth/azure-ad.md §5.2 Pieges 4-5.

ACTIVE_AUTH=$(grep -E '^- \.claude/stacks/auth/' workspace/input/stack/stack.md 2>/dev/null | grep -v '^#' || true)

if echo "$ACTIVE_AUTH" | grep -q 'azure-ad.md'; then

# 3f.1 — Pages/Authentication.razor (handler des callbacks MSAL)
# Route /authentication/{action} ou {action} ∈ {login, login-callback, logout, logout-callback}.
# OBLIGATOIRE [AllowAnonymous] sinon boucle infinie de redirection.
if [ ! -f "workspace/output/src/{AppName}/Pages/Authentication.razor" ]; then
cat > "workspace/output/src/{AppName}/Pages/Authentication.razor" <<'EOF'
@page "/authentication/{action}"
@attribute [Microsoft.AspNetCore.Authorization.AllowAnonymous]
@using Microsoft.AspNetCore.Components.WebAssembly.Authentication

<RemoteAuthenticatorView Action="@Action" />

@code {
    [Parameter] public string? Action { get; set; }
}
EOF
fi

# 3f.2 — Shared/RedirectToLogin.razor (declenche MSAL pour les pages [Authorize])
# Compose avec <NotAuthorized><RedirectToLogin/></NotAuthorized> dans App.razor.
if [ ! -f "workspace/output/src/{AppName}/Shared/RedirectToLogin.razor" ]; then
cat > "workspace/output/src/{AppName}/Shared/RedirectToLogin.razor" <<'EOF'
@using Microsoft.AspNetCore.Components.WebAssembly.Authentication
@inject NavigationManager Navigation

@code {
    protected override void OnInitialized()
        => Navigation.NavigateToLogin("authentication/login");
}
EOF
fi

# 3f.3 — _Imports.razor : auth globale + using Authorization
# Idempotent : on n'ajoute la ligne que si absente.
IMPORTS_FILE="workspace/output/src/{AppName}/_Imports.razor"
if [ -f "$IMPORTS_FILE" ]; then
  grep -q 'Microsoft.AspNetCore.Authorization' "$IMPORTS_FILE" || \
    echo "@using Microsoft.AspNetCore.Authorization" >> "$IMPORTS_FILE"
  grep -q '@attribute \[Authorize\]' "$IMPORTS_FILE" || \
    echo -e "\n@attribute [Authorize]" >> "$IMPORTS_FILE"
fi

fi  # fin auth/azure-ad actif

fi  # fin garde-fou idempotent (csproj absent)

# STEP 4 — Reference le projet partage {LibName} (DTOs, ApiResponse<T>)
# Le projet {LibName} doit etre deja scaffolde (assure par dotnet-minimalapi STEP 1).
dotnet add workspace/output/src/{AppName}/{AppName}.csproj reference workspace/output/src/{LibName}/{LibName}.csproj

# STEP 5 — Ajouter les packages declares en §2.4 (au-dela du template blazorwasm de base)
#
# REGLE DE VERSIONING (conforme a la politique librairies inlined dans .claude/agents/arch.md) :
# - Packages avec compatibilite validee a une version specifique : pinnes via .libs.json.
# - Packages a cycle CVE frequent (notamment Microsoft.Authentication.WebAssembly.Msal
#   qui suit le rythme de Microsoft.Identity.Web cote serveur) : NON PINNES —
#   `dotnet add package` sans `--version` resout automatiquement la DERNIERE
#   VERSION STABLE compatible avec le TargetFramework declare (net10.0).
#   Ainsi le framework reste au-dessus des CVE connues.
#   STEP 7 (audit vulnerabilites) valide apres coup qu'aucun NU1902 ne reste.
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis blazor-webassembly.libs.json -- ne pas editer (utiliser sync_stack_md.py).
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.AspNetCore.Components.WebAssembly --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.AspNetCore.Components.WebAssembly.DevServer --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.AspNetCore.Components.WebAssembly.Authentication --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Radzen.Blazor --version 10.2.3
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Refit --version 10.1.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Refit.HttpClientFactory --version 10.1.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Polly.Core --version 8.6.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.Extensions.Http.Polly --version 10.0.6
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Serilog --version 4.3.1
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Serilog.Sinks.BrowserConsole --version 8.0.0
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Blazored.LocalStorage --version 4.5.0
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Blazored.SessionStorage --version 2.4.0
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Blazored.Toast --version 4.2.1
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Blazored.Modal --version 7.3.1
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package FluentValidation --version 11.11.0
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.Extensions.Localization --version 10.0.6
```
<!-- CORE_PACKAGES_END -->

```bash
# Microsoft.Authentication.WebAssembly.Msal : NON PINNE — derniere version stable
# compatible net10. Suit les patches de securite MSAL sans intervention manuelle
# sur le stack FEAT. Equivalent SPA de Microsoft.Identity.Web cote serveur.
# (volontairement hors .libs.json -- pas de --version pour suivre les patches CVE.)
dotnet add workspace/output/src/{AppName}/{AppName}.csproj package Microsoft.Authentication.WebAssembly.Msal

# STEP 6 — Creer les repertoires de couches vides declares en §1.3
# (evite les erreurs de chemin lors de la premiere generation par les agents)
mkdir -p workspace/output/src/{AppName}/Pages
mkdir -p workspace/output/src/{AppName}/Components
mkdir -p workspace/output/src/{AppName}/Layouts
mkdir -p workspace/output/src/{AppName}/Services
mkdir -p workspace/output/src/{AppName}/Auth
mkdir -p workspace/output/src/{AppName}/Shared
mkdir -p workspace/output/src/{AppName}/Resources

# STEP 7 — Restore + build de verification (doit etre vert avant toute generation)
dotnet restore workspace/output/src/{AppName}/{AppName}.csproj
dotnet build workspace/output/src/{AppName}/{AppName}.csproj --nologo

# STEP 8 — Audit vulnerabilites NuGet (cf. politique inlined dans agents/arch.md : 0 warning libs)
# Si au moins une vulnerabilite subsiste malgre les non-pinnings (le registre NuGet
# n'a pas encore publie de version corrigee), la faire remonter au Tech Lead sans
# bloquer le build.
vuln_count=$(dotnet list workspace/output/src/{AppName}/{AppName}.csproj package --vulnerable --include-transitive 2>&1 | grep -c '>')
if [ "$vuln_count" -gt 0 ]; then
  echo "WARN: $vuln_count vulnerable package(s) apres install — voir dotnet list --vulnerable"
  dotnet list workspace/output/src/{AppName}/{AppName}.csproj package --vulnerable --include-transitive
fi
```

**Contrat post-init :** `workspace/output/src/{AppName}/{AppName}.csproj` DOIT exister, le build DOIT etre vert.
Microsoft.Authentication.WebAssembly.Msal est installe en **version flottante latest stable
compatible net10** (pas de `--version` pin) — suit automatiquement les patches CVE MSAL a
chaque init. STEP 8 (audit `dotnet list --vulnerable --include-transitive`) emet un WARN si
au moins une vulnerabilite subsiste (cas rare : registre NuGet pas encore patche pour une
CVE fraiche — decision Tech Lead).

Les fichiers generes par `dotnet new` conserves (`Program.cs`, `App.razor`, `_Imports.razor`,
`Layouts/MainLayout.razor`, `Layouts/NavMenu.razor`, `Pages/Home.razor`, `Pages/NotFound.razor`,
`wwwroot/index.html`) seront **augmentes** par les agents (operation: augment) avec
`preserves:` declarant leurs identifiants courants : `WebAssemblyHostBuilder`, `MainLayout`,
`NavMenu`, `Home`, `NotFound`. La reference projet vers `{LibName}` est etablie a STEP 4
pour exposer `ApiResponse<T>` et les DTOs partages aux services Refit (voir §3.2 sur le
conflit avec `Refit.ApiResponse<T>`).

**Fichiers supplementaires injectes par STEP 3c et STEP 3d** (pas dans le template de base) :
- `wwwroot/index.html` augmente avec
  `<script src="_content/Microsoft.Authentication.WebAssembly.Msal/AuthenticationService.js"></script>`
  AVANT `<script src="_framework/blazor.webassembly.js"></script>`. Sans cette
  ligne, runtime exception `Could not find 'AuthenticationService.init'` au premier rendu d'un
  composant `[Authorize]`. Identifiant `preserves:` pour les augments ulterieurs :
  `AuthenticationService.js`.
- ⚠️ **Syntaxe fingerprint INTERDITE en standalone** (post-mortem 2026-05-22 CMSPrint) :
  ne JAMAIS écrire `_framework/blazor.webassembly#[.{fingerprint}].js`. La substitution du
  placeholder `#[.{fingerprint}]` est faite par `MapStaticAssets()` côté **serveur** (Blazor
  Web App / hosted), pas par Blazor WASM **standalone**. En standalone, le placeholder est
  servi littéralement au navigateur → `404 _framework/blazor.webassembly#[.{fingerprint}].js`
  + `<link rel=preload> has an invalid href value`. Voir §3.5.
- ⚠️ **`<link rel="preload" id="webassembly" />` SANS `href`** : ne PAS conserver le placeholder
  vide injecté par certains templates `dotnet new blazorwasm`. Soit le supprimer (recommandé —
  le runtime Blazor WASM standalone n'en a pas besoin), soit fournir un `href` valide. Sinon
  warning navigateur `<link rel=preload> has an invalid 'href' value` au démarrage.
- `wwwroot/appsettings.json` cree avec `Api:BaseAddress` pointant sur l'URL HTTPS du Backend
  (par defaut `https://localhost:7238/`, alignee sur le profil HTTPS du
  `launchSettings.json` du Backend dotnet-minimalapi). A surcharger par feature si l'URL
  Backend differe. Aucun secret n'y figure (cf. agent-frontend.instructions.md STEP 4.6).

**Fichiers supplementaires injectes par STEP 3f** (uniquement si `auth/azure-ad`
actif sous `## Active Auth Specs`) — bootstrap des Pieges 4-5 documentes dans
`auth/azure-ad.md §5.2` :
- `Pages/Authentication.razor` : handler des callbacks MSAL
  `/authentication/{action}` (login, login-callback, logout, logout-callback) avec
  `@attribute [AllowAnonymous]`. Identifiant `preserves:` : `Authentication`.
- `Shared/RedirectToLogin.razor` : redirection automatique vers MSAL pour les
  pages portant `[Authorize]`, declenchee par `<NotAuthorized>` dans `App.razor`.
  Identifiant `preserves:` : `RedirectToLogin`.
- `_Imports.razor` augmente avec `@using Microsoft.AspNetCore.Authorization` et
  `@attribute [Authorize]` (auth globale — toutes les pages exigent auth par
  defaut, exception explicite via `@attribute [AllowAnonymous]` page par page).
  Identifiants `preserves:` ajoutes : `Microsoft.AspNetCore.Authorization`,
  `Authorize`.

Les fichiers `Program.cs` et `App.razor` ne sont PAS touches par STEP 3f. Ils
sont reecrits / augmentes par `dev-frontend` selon son plan inline qui DOIT
suivre les patterns canoniques de `auth/azure-ad.md §5.2 Piege 4` (bootstrap
fetch `/api/config/auth` avant `AddMsalAuthentication`) et `Piege 5` (wrap avec
`<CascadingAuthenticationState>` + `<AuthorizeRouteView>` + `<NotAuthorized>
<RedirectToLogin/>`).

### 2.3 Patterns d'erreurs compilation
Meme format que `tech-minimalapi.md` §2.3 (C# sur Blazor WASM).
Codes prioritaires : CS0246, CS0103, CS1061, CS1002, CS1003, CS1513, CS0029, CS0266, CS0161, CS7036.

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/frontend/blazor-webassembly.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id blazor-webassembly`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| Microsoft.AspNetCore.Components.WebAssembly | 10.0.6 |  |
| Microsoft.AspNetCore.Components.WebAssembly.DevServer | 10.0.6 |  |
| Microsoft.AspNetCore.Components.WebAssembly.Authentication | 10.0.6 |  |
| Radzen.Blazor | 10.2.3 |  |
| Refit | 10.1.6 |  |
| Refit.HttpClientFactory | 10.1.6 |  |
| Polly.Core | 8.6.6 |  |
| Microsoft.Extensions.Http.Polly | 10.0.6 |  |
| Serilog | 4.3.1 |  |
| Serilog.Sinks.BrowserConsole | 8.0.0 |  |
| Blazored.LocalStorage | 4.5.0 |  |
| Blazored.SessionStorage | 2.4.0 |  |
| Blazored.Toast | 4.2.1 |  |
| Blazored.Modal | 7.3.1 |  |
| FluentValidation | 11.11.0 |  |
| Microsoft.Extensions.Localization | 10.0.6 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| excel-client | ClosedXML | 0.104.2 | excel, \.xlsx, upload.*excel, parse.*excel |
<!-- LIBS_CATALOG_END -->

### 2.5 Conventions de nommage
- Composant : `PascalCase.razor` (+ code-behind optionnel `PascalCase.razor.cs`)
- Page : `PascalCase.razor` dans `Pages/`
- Layout : `PascalCase.razor` dans `Layouts/`
- Service : `PascalCase.cs`, interfaces `IPascalCase.cs`
- Contrat Refit : suffixe `IApiClient` ou `IXxxClient`
- Variables / parametres : `camelCase`
- Fichiers `.resx` : `PascalCase.resx`, `PascalCase.fr.resx`, `PascalCase.en.resx`

---

## 3. Conventions d'usage (lecons figees)

### 3.1 Refit — enregistrement

Utiliser **toujours** l'overload a factory explicite :

```csharp
builder.Services.AddRefitClient<IXxxClient>(_ => new RefitSettings())
```

**Ne jamais** appeler `AddRefitClient<IXxxClient>()` sans argument : l'IL
genere reference un overload absent du runtime Refit 10.x → `ManagedError:
Method not found`.

### 3.2 Refit — attributs sur les contrats

`{LibName}` definit `ApiResponse<T>` qui entre en collision avec
`Refit.ApiResponse<T>`. Dans les contrats Refit :

- **Ne pas** faire `using Refit;` global.
- Prefixer les attributs par leur FQN :

```csharp
[Refit.Get("/api/v1/xxx")]
Task<ApiResponse<T>> GetAsync([Refit.Query] string? langue = null);
```

Sans ca, `CS0104 ApiResponse<> est une reference ambigue`.

### 3.3 Polly — API v8 Core

Utiliser `Polly.Core` 8.x + `Microsoft.Extensions.Http.Polly` 10.x. Helpers
`HttpPolicyExtensions.HandleTransientHttpError()` + `WaitAndRetryAsync` /
`CircuitBreakerAsync` via `using Polly;` + `using Polly.Extensions.Http;`.

### 3.4 Program.cs Blazor WASM — usings obligatoires

Pour que les handlers MSAL injectent `NavigationManager`, ajouter
`using Microsoft.AspNetCore.Components;` en tete de `Program.cs`.

### 3.5 `wwwroot/index.html` — scripts obligatoires

```html
<script src="_content/Microsoft.Authentication.WebAssembly.Msal/AuthenticationService.js"></script>
<script src="_framework/blazor.webassembly.js"></script>
```

L'ordre est imperatif (MSAL avant Blazor WASM). Details auth dans
`auth/azure-ad.md §5`.

**Syntaxe `_framework/blazor.webassembly.js` (sans fingerprint)** est la
forme correcte pour **Blazor WASM standalone**. La forme alternative
`_framework/blazor.webassembly#[.{fingerprint}].js` est exclusive au
**Blazor Web App** (server-rendered) qui utilise `app.MapStaticAssets()`
pour substituer le placeholder. En standalone, `MapStaticAssets` n'est
pas dans le pipeline → le placeholder est servi tel quel → 404 runtime.

**Anti-pattern `<link rel="preload" id="webassembly" />`** : certains
templates `dotnet new blazorwasm` (.NET 10) injectent ce slot vide en
attente d'un `href` rempli par le build. En standalone, le slot reste
vide → warning navigateur `<link rel=preload> has an invalid 'href'
value`. **Supprimer la ligne** au scaffolding (le runtime Blazor WASM
charge `dotnet.wasm` par lui-même sans ce hint preload).

### 3.5.1 `AuthorizationMessageHandler` — URLs autorisees obligatoires (post-mortem 2026-05-03)

Quand le Backend est sur une autre origine que la SPA (cas par defaut SDD :
SPA `https://localhost:5xxx/`, Backend `https://localhost:7238/`),
`AuthorizationMessageHandler.ConfigureHandler(authorizedUrls: ...)` DOIT
inclure les DEUX URLs. Sinon le token Bearer n'est attache QUE pour les appels
sur la BaseUri de la SPA → le Backend rejette en 401 (`Refit.ApiException
Response status code does not indicate success: 401`).

```csharp
public class SimAuthorizationMessageHandler : AuthorizationMessageHandler
{
    public SimAuthorizationMessageHandler(
        IAccessTokenProvider provider,
        NavigationManager navigation,
        SimAuthScopes scopes,
        SimApiBaseAddress apiBase)        // <-- nouvelle dep injectee
        : base(provider, navigation)
    {
        var urls = new List<string> { navigation.BaseUri };
        if (!string.IsNullOrWhiteSpace(apiBase.Value))
            urls.Add(apiBase.Value);       // <-- URL backend AJOUTEE

        ConfigureHandler(
            authorizedUrls: urls.ToArray(),
            scopes: scopes.Values
        );
    }
}
```

Anti-pattern : passer uniquement `navigation.BaseUri` quand le Backend est
sur une autre origine. Le handler ne se plaint pas, le build est vert, et
le bug ne se manifeste qu'au premier appel API en runtime.

### 3.6 Runtime Blazor WASM → cache agressif

Apres upgrade de librairies ou changement d'un contrat Refit, les assemblies
sont mises en cache par le navigateur (IndexedDB + cache HTTP) :

1. DevTools → Application → Storage → **Clear site data** pour l'origine de dev
2. Relancer `dotnet run`
3. Ou : DevTools → Network → **Disable cache** + `Ctrl+F5`

Caveat runtime uniquement, aucune implication sur le code genere.

### 3.7 Scoped CSS — isolation par composant (load-bearing, post-mortem 2026-05-22)

Le mécanisme Blazor « CSS isolé » injecte un **attribut hash unique
`[b-xxxxxxxxxx]` par composant `.razor`** et préfixe automatiquement
chaque selecteur du `.razor.css` adjacent avec ce hash. Conséquence
**load-bearing** :

- Un composant `Foo.razor` ne style **que** son propre markup via
  `Foo.razor.css` adjacent. Le hash `b-xxx` injecté dans le HTML rendu
  ne s'étend **PAS** aux composants enfants `<Bar />` consommés.
- Un `Page.razor.css` ne style **PAS** un composant enfant `<Component />`
  consommé dans `Page.razor` — les classes du composant enfant ont un
  hash différent.

**Règle obligatoire** : les classes CSS consommées par un composant
`Foo.razor` (markup HTML verbatim, classes mockup `.brand`/`.submenu`/
`.btn`/etc.) DOIVENT être déclarées dans `Foo.razor.css` **adjacent**
(même répertoire, même basename). Pas dans le `.razor.css` d'une
page parent, pas dans `wwwroot/css/theme.css` (sauf tokens `:root`).

**Exceptions au scope** :
- `wwwroot/css/theme.css` — global, non scoped : OK pour tokens
  `:root { --pink: ...; }` et règles `body` / `html`.
- `::deep selector { ... }` dans un `.razor.css` — traverse la frontière
  scoped pour atteindre les enfants (utile pour forcer `width: 100%`
  sur les wrappers `.rz-textbox`/`.rz-dropdown` Radzen).
- `MainLayout.razor.css` style le contenu de `MainLayout.razor`
  uniquement ; le `@Body` rendu hérite des règles `body`/tokens
  globaux mais pas des classes scopées du Layout.

**Anti-pattern rejeté** : déclarer dans `Pages/Foo.razor.css` les
classes consommées par `<BarComponent />` enfant
(`.bar-title`, `.bar-field`, …). Résultat runtime : CSS **jamais
appliqué**, composant non stylé, l'agent dev-frontend croit avoir
livré le mockup → écart de fidélité silencieux.

**Vérification dev-frontend** : à la fin du STEP build, pour chaque
classe non-token consommée dans `Components/Foo.razor`, vérifier
qu'elle existe dans `Components/Foo.razor.css` adjacent (pas dans
le CSS d'une page parent). Si écart → réécrire / créer le
`.razor.css` adjacent du composant.

**Coordination avec radzen-blazor §7.0** : la règle « containers HTML
verbatim » impose des classes mockup (`.submenu`, `.brand`, `.btn`,
`.stepper`, …) ; cette règle §3.7 impose **où** déclarer le CSS de
ces classes — toujours dans le `.razor.css` adjacent au composant
qui possède le markup.

---

## 4. Integration back → front

- Modeles partages via `{LibName}` (projet reference par backend et frontend).
- `ApiResponse<T>` : champs `Data`, `QueryTime`, `MappingTime`.
- Format de payload : JSON.
- Versioning : URL `/api/v{version}/...`.
- Erreurs : RFC 7807 `ProblemDetails` cote backend, deserialisees cote frontend.
- Client HTTP : contrats Refit + `IHttpClientFactory` + Polly retry + circuit breaker.
- Authentification : voir `tech-auth-azure.md`.

---

## 5. URLs de developpement
- Frontend dev : `https://localhost:59776` (ou port dev assigne)
- `Api:BaseAddress` (dans `wwwroot/appsettings.json`) DOIT pointer vers l'URL
  backend telle que declaree dans `tech-minimalapi.md` §8.

---

## 6. Interdits projet (frontend)

- Appels `HttpClient` bruts depuis un composant Blazor ou un service frontend → toujours via un contrat Refit
- Politique de retry / timeout / circuit breaker ecrite a la main → utiliser Polly
- `Console.WriteLine` ou `Console.Log` cote Blazor → utiliser Serilog (`Serilog.Sinks.BrowserConsole`)
- Traductions codees en dur dans les composants → utiliser `.resx` via `IStringLocalizer`
- `AddRefitClient<T>()` sans factory explicite (voir §3.1)
- `using Refit;` global dans un contrat exposant `ApiResponse<T>` (voir §3.2)
- Déclarer dans `Pages/Foo.razor.css` les classes consommées par un `<BarComponent />` enfant — scope hash différent, CSS jamais appliqué (voir §3.7). Les classes d'un composant DOIVENT vivre dans son `.razor.css` adjacent.
- `HttpClient` instancie a la main dans un composant
- `wwwroot/index.html` sans `AuthenticationService.js` avant `blazor.webassembly.js` (voir §3.5)
- Valeurs Azure AD (`TenantId`, `ClientId`, `Authority`, `Audience`) en dur dans le code
- `TODO`, `FIXME`, code commente, placeholders (`TBD`, `changeme`, `foo`, `bar`)
