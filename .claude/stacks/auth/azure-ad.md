# Tech FEAT: auth-azure

Status: Stable
Validation: 🟢 reference (validated dans 2 combos — dotnet+blazor+radzen 2026-05 et kotlin+react+shadcn 2026-05-13)
Tech FEAT ID: tech-auth-azure
Scope: authentification et autorisation Azure AD — independant de toute stack ou langage. Chaque implementation (backend, SPA, monolithe) doit appliquer ces regles selon sa technologie.

---

## 1. Principe universel

- Auth via Azure AD (Microsoft Entra ID), tenant unique.
- App Registration partagée frontend+backend (legacy single-app) OU
  dual-app dédiée (cf. §2.dual-app, recommandé prod).
- Aucun ClientSecret côté client.
- Flux Microsoft standards :
  - SPA : Authorization Code + PKCE
  - Backend : validation JWT (Bearer token)
  - Monolithe : OpenID Connect + session
- **Config exclusive depuis `## Active Auth Specs` de
  `workspace/input/stack/stack.md`**, propagée par `arch` Phase A STEP
  4.5 vers les configs natives :
  - `appsettings.json` section `AzureAd` (.NET)
  - `application.yml` section `azure.ad` (Spring)
  - `config/default.json` section `azure.ad` (Node)
  - `app/config.py` classe `AzureADSettings` (Python)
- Token JWT = source unique de vérité (identité, groupes, droits).
- Logique framework-spécifique non supposée.

---

## 2. Variables de configuration

Valeurs déclarées dans `## Active Auth Specs` de `stack.md`. `arch`
STEP 4.5 propage vers les configs natives. **Pas d'env vars** : l'app
lit `IConfiguration` / `application.yml` / `config/default.json` /
`app/config.py`. Boot fail-fast si clé absente.

### Cles de configuration obligatoires (sous `## Active Auth Specs`)

- AZ_TENANTID : tenant Azure AD
- AZ_CLIENTID : App Reg legacy single-app (FE=BE). **Préféré** : dual-app
  `AZ_FE_CLIENTID` + `AZ_BE_CLIENTID` (cf. §dual-app)
- AZ_FE_CLIENTID : clientId App Reg FRONTEND (SPA public client, lu par
  MSAL.js). Optionnel, fallback `AZ_CLIENTID`.
- AZ_BE_CLIENTID : clientId App Reg BACKEND (resource server, scope
  target + audience). Optionnel, fallback `AZ_CLIENTID`.
- AZ_DOMAIN : domaine tenant
- AZ_AUDIENCES : audiences acceptées par le backend (CSV strict, sans
  guillemets ni espaces). Format : GUIDs ou `api://{guid}`, virgule
  unique. Inclure les 2 formes par App Reg (robuste à
  `accessTokenAcceptedVersion` v1=`api://{guid}` vs v2=`{guid}`).
  Exemple : `api://{guid1},{guid1},api://{guid2},{guid2}`.
- AZ_BE_CALLBACKPATH : retour backend (ex. `/signin-oidc`)
- AZ_FE_CALLBACKPATH : retour frontend. **Canonical pour tous SPAs
  (React/Vue/Angular/Blazor) : `/authentication/login-callback`**
  (convention Microsoft.Identity.Web/Blazor — adoptée comme défaut
  cross-stack par SDD_Pro depuis 2026-05-21 pour éviter le piège
  AADSTS50011 quand la valeur ne matche pas l'URI enregistrée
  côté Azure AD App Registration).

  ⚠️ **Anti-pattern post-mortem 2026-05-21** : `/login-callback`
  (sans préfixe `authentication/`) NE doit PAS être utilisé pour les
  raisons suivantes :
  1. Collision **Vite proxy** `/auth` (prefix-match) sur React — le path
     `/auth/config` (proxy backend) et `/auth-callback` peuvent piéger
     `/authentication/login-callback` si la règle proxy n'est pas
     `/auth/` (slash final strict). Path `/authentication/...` évite
     l'ambiguïté car ne commence pas par `/auth/`.
  2. Convention **Azure AD App Reg** : les Redirect URIs sont
     case-sensitive ET exact-match. Un projet qui migre de Blazor
     (`/authentication/login-callback`) vers React n'a plus à
     ré-enregistrer l'URI dans Azure AD si la même convention est
     utilisée — réduit la friction multi-stack.

### Variables optionnelles

| Clé | Défaut |
|---|---|
| `AZ_INSTANCE` | `https://login.microsoftonline.com/` |
| `AZ_AUTHORITY` | override complet si nécessaire |
| `AZ_SCOPES` | scopes additionnels (séparés espace) |
| `AZ_LOG_LEVEL` | `debug/info/warn/error` |

### Règles strictes

- Toutes valeurs dans `## Active Auth Specs` de `stack.md`, propagées par `arch` STEP 4.5
- Aucun hardcoding Azure AD dans le code (`.cs`/`.kt`/`.py`/`.ts`)
- Lecture via mécanismes natifs framework : `IConfiguration["AzureAd:*"]`,
  `@Value("${azure.ad.*}")`, `config.get("azure.ad")`, `azure_settings.*`
- **Env var binding runtime INTERDIT** (Pattern B 2026-06-06) : `stack.md` =
  SSoT gitignored, `arch` propage en config native. Lecture directe
  `AZ_*`/`DB_*`/`AUTH_*`/`SMTP_*` via `process.env`/`os.environ`/
  `Environment.GetEnvironmentVariable`/`@Value("${AZ_*}")` = `[SEC_ENV_VAR_FORBIDDEN]`
- Secrets jamais commités : `workspace/output/` gitignored, rotation prod
  via secret manager hors repo

### §2.bis — Propagation stack.md → config native (load-bearing)

`arch` Phase A STEP 4.5 = seul pont autorisé : lit `stack.md`, valide les
clés, écrit la section native attendue par le framework. Le runtime consomme
uniquement la config native.

```csharp
// .NET — appsettings.json peuplé par arch
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration, "AzureAd");
```

```yaml
# Spring Boot — application.yml peuplé par arch
azure:
  ad:
    tenant-id: "{AZ_TENANTID}"
    client-id: "{AZ_BE_CLIENTID}"
    frontend-client-id: "{AZ_FE_CLIENTID}"
    callback-path: "/signin-oidc"
```

```python
# FastAPI — app/config.py généré par arch
class AzureADSettings:
    tenant_id = "{AZ_TENANTID}"
    client_id = "{AZ_BE_CLIENTID}"
azure_settings = AzureADSettings()
```

```
# Express — config/default.json généré par arch, lu via config.get("azure.ad")
```

### §2.ter — Règle actuelle (post Pattern B)

- `AZ_FE_CALLBACKPATH` + `AZ_BE_CALLBACKPATH` vivent dans `stack.md`
- `arch` propage en config native (`appsettings.json`, `application.yml`,
  `config/default.json`, `app/config.py`)
- Code applicatif lit la config native ; lecture shell directe AZ_* =
  `[SEC_ENV_VAR_FORBIDDEN]`
- `AZ_FE_CALLBACKPATH` = `/authentication/login-callback` (convention SPA
  universelle) sauf ADR explicite

### §dual-app — Pattern canonique 2 App Reg

**Recommandé prod** : front SPA + back API en **2 App Registrations
distinctes** (équivalent .NET Blazor WASM + ASP.NET Web API).

| Élément | Front SPA App Reg | Back API App Reg |
|---|---|---|
| Type plateforme | Single-page application | Web (sans secret si JWT seul) |
| ClientId | `AZ_FE_CLIENTID` | `AZ_BE_CLIENTID` |
| Redirect URIs | `https://{host}/{AZ_FE_CALLBACKPATH}` | n/a (resource server) |
| Token `aud` | n/a | `api://{AZ_BE_CLIENTID}` ou `{AZ_BE_CLIENTID}` |
| Scope exposé | n/a | `api://{AZ_BE_CLIENTID}/access_as_user` |
| Pré-autorisation | pré-autoriser `AZ_FE_CLIENTID` | — |

**Flow** : MSAL.js (`clientId = AZ_FE_CLIENTID`) → demande scope
`api://{AZ_BE_CLIENTID}/access_as_user` → Azure délivre JWT
(`aud = api://{AZ_BE_CLIENTID}`) → backend valide via `JwtDecoder`.

**Mapping Spring** : `AuthConfigController` distingue `frontend-client-id`
(MSAL.js bootstrap) vs `backend-client-id` (scope target) :

```kotlin
@RestController @RequestMapping("/auth")
class AuthConfigController(
    @Value("\${azure.ad.frontend-client-id:\${azure.ad.client-id:}}") private val frontendClientId: String,
    @Value("\${azure.ad.backend-client-id:\${azure.ad.client-id:}}") private val backendClientId: String,
    // ...
) {
    @GetMapping("/config")
    fun getConfig() = AuthConfigDto(
        clientId = frontendClientId,
        scopes   = listOf("api://$backendClientId/access_as_user"),
        authority = "$inst$tid",
    )
}
```

**Fallback single-app** : seul `AZ_CLIENTID` défini → Spring résout
`${azure.ad.frontend-client-id:${azure.ad.client-id:}}` et
`backend-client-id` vers la même valeur → comportement legacy FE=BE
inchangé (back-compat).

**Anti-pattern** : `@Value("\${AZ_CLIENTID:}")` direct env var (lecture
unique → cassé si front ≠ back en Azure).

**Format ERROR dual-app mal configuré** :
```
ERROR: backend Spring — audience JWT rejetée
CAUSE: [AUTH_AUDIENCE_MISMATCH] token aud='api://{guid_be}' mais azure.ad.backend-client-id='{guid_legacy}' (audience implicit = api://{guid_legacy})
FIX: ajouter AZ_BE_CLIENTID dans ## Active Auth Specs (valeur = clientId réel App Reg backend), relancer /arch-init, redémarrer backend
```

### §setup-app-reg — Plateformes App Registration

**2 plateformes mutuellement exclusives sur les redirect URIs** :

| Plateforme | Flow | Client | Utilisé par |
|---|---|---|---|
| **Web** | Authorization Code + ClientSecret | Confidential | .NET `AddMicrosoftIdentityWebApp`, Spring OIDC server, Java MVC |
| **SPA** | Authorization Code + PKCE (sans secret) | Public | React/Vue/Angular + MSAL, Blazor WASM |

Configuration Azure Portal (App Reg → Authentication) :
1. Backend + SPA partagés → activer **les 2 plateformes**, pas de conflit
2. SPA seul → plateforme **SPA uniquement**
3. Éviter "Implicit grant" (deprecated, PKCE suffit)

URI sous "Web" → **NON valide pour SPA** même path identique → `AADSTS50011`.

**Règle architecturale — frontend-owned redirectUri** (post-mortem
2026-05-12) : le `redirectUri` du SPA est une concern FRONTEND, pas
backend. Backend N'EST PAS source de vérité pour le path de callback :

```ts
// src/auth/msalConfig.ts — pattern correct
const FE_CALLBACK_PATH = "/authentication/login-callback"

const msalConfiguration: Configuration = {
  auth: {
    clientId: cfg.clientId,
    authority: cfg.authority,
    redirectUri: window.location.origin + FE_CALLBACK_PATH, // ← front-owned, path canonique stack.md
    // PAS : window.location.origin + cfg.redirectUri (backend)
  },
}
```

`/auth/config` ne retourne PAS `redirectUri` (DTO :
`{authority, clientId, scopes}`). Si exigé → `null`/vide.
`/login-callback` = route SPA publique (`PUBLIC_ROUTES` root guard,
MSAL intercepte `#code=...` via `handleRedirectPromise()`).

**Format ERROR violation** :
```
ERROR: dev-frontend {n}-{m} — redirectUri pris du backend
CAUSE: [SECURITY_CALLBACK_FROM_BACKEND] cfg.redirectUri lu depuis /auth/config (path mangling shell, mauvaise SOC)
FIX: utiliser FE_CALLBACK_PATH front canonique, retirer redirectUri du DTO backend, créer route /authentication/login-callback publique
```

**Grep checklist (STEP build)** :
```bash
grep -RE "cfg\.redirectUri|response.*redirectUri" workspace/output/src/{AppName}/src/
# → 0 match attendu
```

### Valeurs dérivées (jamais en dur)

- Instance : `${AZ_INSTANCE}` ou `https://login.microsoftonline.com/`
- Authority : `${AZ_INSTANCE}/${AZ_TENANTID}`
- Scope API : `api://${AZ_BE_CLIENTID}/access_as_user` + `AZ_SCOPES`

---

## 3. Validation du token (universel)

Tout composant recevant un token vérifie via lib standard :
- Signature valide (via JWKS Azure AD)
- Issuer : `https://login.microsoftonline.com/{tenant}/v2.0` (accepter v1.0 + v2.0)
- Audience : `AZ_BE_CLIENTID`, `api://AZ_BE_CLIENTID`, valeurs `AZ_AUDIENCES` (cumulatives)
- Expiration `exp` valide
- Pas de validation manuelle (toujours middleware/lib officielle)

Logs (dev uniquement) : échec validation, audience invalide, issuer invalide, accès refusé.

---

## 4. Autorisation par groupes

- **Source des droits** : claim `groups` ou `roles` uniquement. Aucune base locale roles/permissions autorisée.
- **Mapping** : externe au code (config, JSON, env, DB config). Aucun mapping en dur, modifiable sans redéploiement. Absent → mode dégradé (authentifié uniquement), aucune erreur technique visible.
- **Groupes volumineux** : token sans `groups` mais avec `_claim_names`/`hasgroups` → app supporte récupération via Microsoft Graph OU mode dégradé.
- **Enforcement** : backend = source de vérité, frontend masque (UX seulement). Vérifications critiques toujours côté serveur.

---

## 5. Intégration par type d'application

### 5.1 Backend (API)

- Auth via Bearer token (`Authorization: Bearer`)
- Middleware obligatoire, pas de validation manuelle
- Sans token → 401, token invalide → 401, token sans droit → 403

**Endpoint `/auth/config`** (public, hors filtre JWT) : `{authority, clientId, scopes}`.
Utilisé par tous les frontends (cf. §dual-app pour distinction FE/BE clientId).

#### 5.1.1 Wiring par stack

| Stack backend | Pattern wiring | Jamais |
|---|---|---|
| .NET (Microsoft.Identity.Web) | `AzureAd` dans `appsettings.json` + `AddMicrosoftIdentityWebApiAuthentication(cfg, "AzureAd")` | `Environment.GetEnvironmentVariable("AZ_*")`, `AddInMemoryCollection` env, `Configure<MicrosoftIdentityOptions>("AzureAd", ...)` |
| Spring Boot (Java/Kotlin) | `azure.ad.*` dans `application.yml` + bean `JwtDecoder` custom (cf. §5.1.3) | `System.getenv("AZ_*")`, `@Value("${AZ_*}")` direct env, `spring.security.oauth2.resourceserver.jwt.audiences: ${AZ_AUDIENCES}` (binding fragile) |
| Node.js | `azure.ad` dans `config/default.json` + `config.get("azure.ad")` | `process.env.AZ_*` |
| Python (FastAPI) | classe `AzureADSettings` dans `app/config.py` + import `azure_settings` | `os.environ["AZ_*"]` direct |

**Pattern .NET (Program.cs)** :
```csharp
// IConfiguration peuplé par le pont env-var → §2.bis :
//   "AzureAd": { "Instance", "TenantId", "ClientId", "Domain", "CallbackPath", "ValidAudiences" }
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration, "AzureAd");
```

**Anti-pattern .NET (pré-2026-05-14)** : `Configure<MicrosoftIdentityOptions>("AzureAd", o => o.ClientId = Environment.GetEnvironmentVariable(...))`
→ named options non lues par le handler `JwtBearer` → `IDW10106: The 'ClientId' option must be provided` au 1er appel endpoint.

#### 5.1.1.bis DI lifetime — `IAuthorizationHandler` doit être Scoped (post-mortem 2026-05-22)

Si l'AuthorizationHandler consomme un service Scoped (typiquement
`IGroupsClaimReader` qui lit le `HttpContext.User`), il **DOIT** être
enregistré en `AddScoped`, **JAMAIS** `AddSingleton`. ASP.NET DI valide
au boot que le graphe n'a pas de capture Scoped-dans-Singleton et plante
le démarrage sinon :

```
System.InvalidOperationException: Error while validating the service descriptor
'ServiceType: IAuthorizationHandler Lifetime: Singleton ImplementationType: GroupAuthorizationHandler':
Cannot consume scoped service 'IGroupsClaimReader' from singleton 'IAuthorizationHandler'.
```

Pattern canonique (`Program.cs`) :
```csharp
builder.Services.AddScoped<IGroupsClaimReader, GroupsClaimReader>();
// IAuthorizationHandler doit être Scoped — consomme IGroupsClaimReader (Scoped, lit HttpContext).
builder.Services.AddScoped<IAuthorizationHandler, GroupAuthorizationHandler>();
```

**Anti-pattern bloquant** :
```csharp
builder.Services.AddSingleton<IAuthorizationHandler, GroupAuthorizationHandler>(); // ❌
```
→ Backend ne démarre pas, exit 1 immédiat. Symptôme : `dotnet run` se
termine avec exit code non-zero avant même de logguer "Now listening".

**Règle générale** : tout `IAuthorizationHandler` custom dans Microsoft.Identity.Web
est Scoped par défaut. N'utiliser Singleton que si le handler est totalement
stateless ET ne dépend que de Singleton/Transient services.

#### 5.1.2 Piege Swagger UI whitelist (Spring Boot)

Avec `springdoc-openapi-starter-webmvc-ui`, paths Swagger doivent être
whitelistés via `WebSecurityCustomizer.ignoring()` (bypass complet),
PAS `requestMatchers().permitAll()` seul. Path OpenAPI DOIT être
custom `/openapi` (`/v3/api-docs` reste protégé même avec ignoring —
bug springdoc 2.6 + Spring Security 6.4).

```kotlin
@Bean
fun webSecurityCustomizer() = WebSecurityCustomizer { web ->
    web.ignoring().requestMatchers(
        "/swagger", "/swagger/**", "/swagger-ui.html", "/swagger-ui/**",
        "/openapi", "/openapi/**", "/openapi.yaml"
    )
}
```

Combiné à `springdoc.api-docs.path: /openapi` + `springdoc.swagger-ui.path: /swagger`
dans `application.yml` (cf. `backend/kotlin-spring-boot.md §5.6`).
Springdoc ≥ 2.7.0 requis.

#### 5.1.3 Piege AZ_AUDIENCES binding fragile (Spring) — JwtDecoder custom

**Bug** : Spring bind `spring.security.oauth2.resourceserver.jwt.audiences: ${AZ_AUDIENCES}`
en `List<String>` sans stripper quotes/espaces. Sur Windows
(setx/PowerShell), valeur `"guid1", "guid2"` produit
`["\"guid1\"", " \"guid2\""]` → aucun match `aud` JWT → **401
silencieux** sans log Spring.

**Symptôme** : login MSAL OK, token en sessionStorage, `GET /api/v1/*` →
401 systématique, aucun log backend hors 401.

**Fix — JwtDecoder custom (parité Microsoft.Identity.Web)** : 3 écarts
corrigés en un bean :
1. `AZ_AUDIENCES` lu via `@Value("\${azure.ad.audiences:}")` (évite
   relaxed-binding `AZ_AUDIENCES` → `az.audiences` ≠ `az.audiences-raw`)
2. Auto-inclusion `AZ_BE_CLIENTID` + `api://{AZ_BE_CLIENTID}` (parité .NET additif)
3. Auto-acceptation **dual-issuer** v2 (`login.microsoftonline.com/{tid}/v2.0`)
   ET v1 (`sts.windows.net/{tid}/`) — manifest Azure
   `accessTokenAcceptedVersion=1` produit tokens v1

```kotlin
// SecurityConfig.kt
@Bean
fun jwtDecoder(
    @Value("\${spring.security.oauth2.resourceserver.jwt.issuer-uri}") issuerUri: String,
    @Value("\${azure.ad.tenant-id:}") tenantId: String,
    @Value("\${azure.ad.backend-client-id:\${azure.ad.client-id:}}") clientId: String,
    @Value("\${azure.ad.audiences:}") audiencesRaw: String,
): JwtDecoder {
    val decoder = JwtDecoders.fromIssuerLocation(issuerUri) as NimbusJwtDecoder
    val audiences = buildAudiences(clientId, audiencesRaw)
    require(audiences.isNotEmpty()) {
        "Audiences vide : client-id='$clientId' audiences='$audiencesRaw' (cf. ## Active Auth Specs)"
    }
    val tid = tenantId.trim().trim('"').trim('\'').trim()
    require(tid.isNotBlank()) { "azure.ad.tenant-id vide" }
    val validIssuers = setOf(
        "https://login.microsoftonline.com/$tid/v2.0",
        "https://sts.windows.net/$tid/",
    )
    decoder.setJwtValidator(DelegatingOAuth2TokenValidator(
        JwtTimestampValidator(),
        JwtClaimValidator<String>(JwtClaimNames.ISS) { iss -> iss != null && iss in validIssuers },
        JwtClaimValidator<List<String>>(JwtClaimNames.AUD) { aud -> aud != null && aud.any { it in audiences } },
    ))
    return decoder
}

// Parité MS.Identity.Web : auto-inclusion AZ_BE_CLIENTID + api://{AZ_BE_CLIENTID}
// (couvre v1 aud=api://{cid} ET v2 aud={cid}), + AZ_AUDIENCES additionnelles.
// Strip quotes Windows + espaces + vides.
private fun buildAudiences(clientId: String, audiencesRaw: String): List<String> {
    val cid = clientId.trim().trim('"').trim('\'').trim()
    val implicit = if (cid.isBlank()) emptyList() else listOf(cid, "api://$cid")
    val explicit = audiencesRaw.split(",")
        .map { it.trim().trim('"').trim('\'').trim() }
        .filter { it.isNotBlank() }
    return (implicit + explicit).distinct()
}
```

`application.yml` (peuplé par arch) : **retirer `audiences:` sous
`jwt:`** (délégué au bean). Valeurs `azure.ad.*` littérales injectées
depuis `## Active Auth Specs`.

**Trigger dev-backend** : `auth/azure-ad` actif sur Spring Boot → générer
`JwtDecoder` bean systématiquement (pas d'attente debug humain 401).

---

### 5.2 Frontend (SPA)

- Lib officielle OBLIGATOIRE : MSAL ou équivalent OAuth2/OIDC
- Flux : Authorization Code + PKCE
- Initialisation via fetch `/auth/config` AVANT MSAL (cf. §5.2.4).
  Aucune valeur Azure AD hardcodée frontend ni dans `appsettings.json`.

**Règles strictes** : aucun formulaire login custom, aucune gestion
manuelle tokens, aucun stockage manuel (localStorage/sessionStorage
interdit sauf via lib), aucun décodage manuel JWT, tous appels API via
interceptor HTTP.

**Compatibilité multi-framework** :
- React/Vue : MSAL + interceptor (fetch/axios)
- Angular : MSAL Angular guard/interceptor
- Blazor : Microsoft.Identity.Web
- Autres : OIDC + PKCE standard

#### 5.2.1 Piege JS shim bootstrap (sinon runtime exception)

| Stack frontend | Fichier | Ligne à injecter |
|---|---|---|
| Blazor WASM | `wwwroot/index.html` | `<script src="_content/Microsoft.Authentication.WebAssembly.Msal/AuthenticationService.js"></script>` AVANT `blazor.webassembly.*.js` |
| React + MSAL.js | `src/main.tsx` | `import { PublicClientApplication } from "@azure/msal-browser"` (npm auto) |
| Vue 3 + MSAL.js | `src/main.ts` | Idem React |
| Angular | `app.module.ts` | `MsalModule.forRoot(...)` (géré par MSAL Angular) |

Symptôme Blazor WASM manquant : `Could not find 'AuthenticationService.init'`
au 1er rendu `[Authorize]`.

#### 5.2.2 Piege runtime config `Api:BaseAddress`

Sans config, SPA appelle sur sa propre origine → 404/CORS silencieux.

| Stack | Fichier | Clé | Valeur typique |
|---|---|---|---|
| Blazor WASM | `wwwroot/appsettings.json` | `Api:BaseAddress` | URL HTTPS Backend |
| React | `public/runtime-config.json` | `apiBaseUrl` | Idem |
| Vue 3 | `public/runtime-config.json` | `apiBaseUrl` | Idem |
| Angular | `src/assets/runtime-config.json` | `apiBaseUrl` | Idem |

Pas de secret (URL uniquement). Valeurs Azure AD via `/auth/config` (§5.1).

#### 5.2.3 Piege URL filter interceptor (Bearer injection)

Composant injectant `Authorization: Bearer <token>` doit couvrir les
DEUX origines (SPA + Backend), pas seulement BaseUri SPA.

| Stack | Composant | URLs |
|---|---|---|
| Blazor WASM | `AuthorizationMessageHandler.ConfigureHandler(authorizedUrls)` | `[navigation.BaseUri, apiBaseUrl]` |
| React + Axios | Axios `request.use(...)` | match `apiBaseUrl` ou instance dédiée |
| Vue 3 + Axios | Idem React | Idem |
| Angular | `HttpInterceptor` | `req.url.startsWith(apiBaseUrl)` |

Symptôme oubli : tous appels API sans token → 401 silencieux, runtime cassé.

#### 5.2.4 Piege bootstrap MSAL avant IConfiguration peuplée

`AddMsalAuthentication(...)` lit `IConfiguration["AzureAd:Authority"]`
**synchroniquement** au bootstrap. Clés vides → `new URL("")` →
`Microsoft.JSInterop.JSException: Failed to construct 'URL': Invalid URL`
avant 1er rendu.

**Pattern obligatoire** : fetch `/auth/config` AVANT MSAL et patch
`Configuration` en RAM. Aucune valeur Azure AD dans `appsettings.json`.

| Stack | Position du fetch | Cible du patch |
|---|---|---|
| Blazor WASM | Avant `AddMsalAuthentication` dans `Program.cs` | `builder.Configuration["AzureAd:Authority"|"AzureAd:ClientId"]` |
| React + MSAL.js | Avant `new PublicClientApplication(config)` dans `main.tsx` | objet `Configuration` MSAL (`auth.authority`, `auth.clientId`) |
| Vue 3 + MSAL.js | Avant `app.use(msalPlugin)` dans `main.ts` | Idem React |
| Angular | `APP_INITIALIZER` qui fetch puis `MsalModule.forRoot(...)` dynamiquement | factory MSAL |

**Pattern Blazor WASM** (`Program.cs`) :
```csharp
var apiBaseAddress = builder.Configuration["Api:BaseAddress"] ?? builder.HostEnvironment.BaseAddress;
using var bootstrapHttp = new HttpClient { BaseAddress = new Uri(apiBaseAddress) };
var authConfig = await bootstrapHttp.GetFromJsonAsync<AuthConfigModel>("auth/config")
    ?? throw new InvalidOperationException($"Endpoint /auth/config indisponible sur {apiBaseAddress}");
builder.Configuration["AzureAd:Authority"] = authConfig.Authority;
builder.Configuration["AzureAd:ClientId"]  = authConfig.ClientId;
builder.Services.AddSingleton(new SimAuthScopes { Values = authConfig.Scopes });
builder.Services.AddTransient<SimAuthorizationMessageHandler>();
builder.Services.AddMsalAuthentication(options => {
    builder.Configuration.Bind("AzureAd", options.ProviderOptions.Authentication);
    foreach (var scope in authConfig.Scopes)
        options.ProviderOptions.DefaultAccessTokenScopes.Add(scope);
});
```

Contrainte : backend DOIT tourner sur `Api:BaseAddress` AVANT démarrage
frontend (IDE multi-projet : `launchSettings.json` `Order`).

#### 5.2.5 Piege routes auth + activation auth globale

`AddMsalAuthentication` ne force PAS la redirection. Sans config
explicite, MSAL jamais invoqué, `/` s'affiche sans redirect login.

**3 éléments obligatoires souvent manquants ensemble** :

| Stack | Auth globale | Handler callback | Anonymous |
|---|---|---|---|
| Blazor WASM | `@attribute [Authorize]` dans `_Imports.razor` | `Pages/Authentication.razor` avec `<RemoteAuthenticatorView Action="@Action" />` | `@attribute [AllowAnonymous]` sur `Authentication.razor` |
| React + MSAL.js | `<MsalAuthenticationTemplate interactionType={Redirect}>` dans `main.tsx` (entre `<MsalProvider>` et `<RouterProvider>`) | callback géré via redirect URI configuré (pas de composant explicite) | Route publique pour `/login-callback` |
| Vue 3 + MSAL.js | Guard `router.beforeEach` appelant `acquireTokenRedirect` | `Callback.vue` sur `/auth/callback` | Route `meta.requiresAuth: false` |
| Angular | `MsalGuard` dans `canActivate` global | Route `/auth/callback` avec `MsalRedirectComponent` | Pas de `MsalGuard` sur cette route |

**Pattern React canonique** (ordre obligatoire — `MsalAuthenticationTemplate`
AVANT `RouterProvider`, sinon loaders/queries init API avant login → 401 silencieux) :

```tsx
// src/main.tsx
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MsalProvider instance={msalInstance}>
      <MsalAuthenticationTemplate interactionType={InteractionType.Redirect}>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </MsalAuthenticationTemplate>
    </MsalProvider>
  </StrictMode>,
)
```

Anti-patterns React : (1) sortir `<MsalAuthenticationTemplate>` dans
`<AuthProvider>` utilisant `useLocation()` — hook exige d'être DANS
`<RouterProvider>`. (2) compter sur loader TanStack Router pour login.
(3) Template dans layout-route (loaders parents avant).

**Pattern Blazor WASM** :
- `_Imports.razor` : `@attribute [Authorize]` (auth globale)
- `Pages/Authentication.razor` : `@page "/authentication/{action}"` + `@attribute [AllowAnonymous]` + `<RemoteAuthenticatorView Action="@Action" />`
- `App.razor` : `<CascadingAuthenticationState>` + `<AuthorizeRouteView>` avec `<NotAuthorized><RedirectToLogin/></NotAuthorized>`
- `Shared/RedirectToLogin.razor` : `Navigation.NavigateToLogin("authentication/login")` dans `OnInitialized`

**Bootstrap automatique Blazor WASM** : ces 3 fichiers framework
(`Authentication.razor`, `RedirectToLogin.razor`, `_Imports.razor`
augment) sont produits **une seule fois** par `arch` Phase A
(`frontend/blazor-webassembly.md §2.2.1 STEP 3f`, conditionnel
`auth/azure-ad` actif). `dev-frontend` **preserve** (jamais modifier),
inclut dans `preserves:` des `_Imports.razor` augments, ne planifie
pas dans son plan inline (sauf cas rare).

**Pages publiques explicites** (malgré auth globale) :
```razor
@attribute [AllowAnonymous]
```

Symptômes oubli : sans `[Authorize]` global → pages publiques jamais de
redirect. Sans `Authentication.razor` → 404 callback, MSAL ne finalise pas.
Sans `[AllowAnonymous]` handler → boucle infinie redirection.

---

### 5.2.6 Déconnexion (Logout) — AUCUN CODE MÉTIER À ÉCRIRE

**Principe** : déconnexion **entièrement déléguée à Azure AD**. Aucun
endpoint backend logout, aucune logique métier serveur, aucune
invalidation session (SPA stateless).

**Backend (API REST + JWT) — 0 ligne** :
- Pas d'endpoint `/auth/logout`, pas de `SignOutAsync`, pas de blacklist
- JWT stateless, expire de lui-même (`exp` claim, typiquement 1h)
- Feature mentionne « logout backend » → anti-pattern → STOP + ERROR `[DERIVE_VIOLATION]`

**Frontend SPA — 1 ligne MSAL** :

| Stack | API logout |
|---|---|
| React + MSAL.js | `msalInstance.logoutRedirect({ postLogoutRedirectUri })` |
| Vue 3 + MSAL.js | Idem React |
| Angular + MSAL Angular | `msalService.logoutRedirect({ postLogoutRedirectUri })` |
| Blazor WASM | `NavigationManager.NavigateToLogout("authentication/logout")` (handler bootstrap par arch) |

Effet : clear cache MSAL local + redirect Azure AD `/oauth2/v2.0/logout`
+ retour `postLogoutRedirectUri` (déclaré dans App Reg → Authentication
→ SPA → Redirect URIs).

**Anti-patterns** : endpoint `/api/logout` backend, effacer
localStorage/sessionStorage manuellement, décoder JWT pour invalider
session, blacklist tokens.

**Pour SDD_Pro** : agents dev-* skip US `*-Deconnexion` (config pure,
1 ligne front, 0 backend). US dédiée déconseillée par PO.

**Cas particulier Blazor Server / ASP.NET MVC cookie** (5.3) : pas SPA,
endpoint auto-mappé `/MicrosoftIdentity/Account/SignOut` fourni par
`Microsoft.Identity.Web` (code lib, pas dev-backend).

---

### 5.2.7 Conventions SPA + Azure AD — anti-patterns récurrents

> **Load-bearing** pour tout SPA avec `auth=azure-ad`. Post-mortem
> `cms-front` v6.1 : 5 anti-patterns produits sans orientation explicite.

#### 5.2.7.1 Endpoint `/auth/config` — OBLIGATOIRE backend

Si `auth/azure-ad` + backend actifs → exposer `GET /auth/config`
(public, hors filtre JWT) :

```json
{ "authority": "https://login.microsoftonline.com/{AZ_TENANTID}",
  "clientId": "{AZ_FE_CLIENTID}",
  "scopes": ["api://{AZ_BE_CLIENTID}/access_as_user"] }
```

> **CRITIQUE — scope FE singleton, dérivé `AZ_BE_CLIENTID` (jamais
> `AZ_AUDIENCES`)**. MSAL.js v3 exige tous scopes d'un
> `loginPopup`/`acquireToken` sur **UN SEUL resource**. `AZ_AUDIENCES`
> multi-valeurs → 2 `api://{guid}/access_as_user` resources distincts
> → URL OAuth malformée → `AADSTS900971`/`AADSTS28000`. Scope FE =
> **toujours** `api://${AZ_BE_CLIENTID}/access_as_user`. `AZ_AUDIENCES`
> reste backend uniquement (§3). 2nd resource FE → `acquireTokenSilent`
> séparé, jamais combo `loginPopup` initial.

Scope arch Phase A (si backend + auth-azure-ad actifs) OU dev-backend
US auth fondatrice (US 1-1 typique). Anti-pattern récurrent : aucune US
ne matérialise, frontend lit `VITE_AZ_*` → cassé.

#### 5.2.7.2 Frontend MSAL — `VITE_AZ_*` INTERDIT

Vite ne propage **que** `VITE_*` au navigateur. `dev-frontend` NE DOIT
JAMAIS faire `import.meta.env.VITE_AZ_CLIENTID`. À la place : fetch
`/auth/config` au bootstrap puis init MSAL (cf. §5.2.4).

```
ERROR: dev-frontend {n}-{m} — anti-pattern MSAL config
CAUSE: [DERIVE_VIOLATION] lecture directe VITE_AZ_CLIENTID/VITE_AZ_TENANTID — Vite ne propage pas AZ_* sans préfixe VITE_, §5.2.7.1 impose fetch /auth/config
FIX: bootstrap async via /auth/config, instance MSAL créée APRÈS résolution
```

#### 5.2.7.3 Mode popup vs redirect

**Default** : `loginPopup()` / `logoutPopup()` (pas redirect). SPA
préserve son état, retour Azure transitoire, meilleur DX. Exception :
mobile (popup bloqué → redirect). Tracer ADR si dérive.

#### 5.2.7.3.bis Redirect URI MSAL — composition runtime obligatoire

App Reg enregistre URI complète :
- Dev : `http://localhost:5173/login-callback`
- Prod : `https://app.exemple.com/login-callback`

Path partagé (`/login-callback`) → `AZ_FE_CALLBACKPATH`. **Frontend
compose runtime** :

```ts
// ✅ Pattern canonique
redirectUri: window.location.origin + cfg.redirectUri
postLogoutRedirectUri: window.location.origin + "/login"

// ❌ Anti-patterns (Azure rejette AADSTS900971/AADSTS50011)
redirectUri: window.location.origin                  // path manquant
redirectUri: cfg.redirectUri                         // origin manquant
redirectUri: "http://localhost:5173/login-callback"  // hardcode (cassé prod)
```

Backend `/auth/config` : `redirectUri` retourné DOIT être un path
commençant par `/` (jamais URL complète, jamais vide).

#### 5.2.7.3.ter `navigateToLoginRequestUrl: false` OBLIGATOIRE (post-mortem 2026-05-22, CMSPrint)

**Symptôme** : auth Azure OK, callback consommé, utilisateur **renvoyé en
boucle sur `/login`** au lieu de home.

**Cause** : MSAL défaut `navigateToLoginRequestUrl: true` replay l'URL d'origine
du login (= `/login` lui-même) → `LoginCallbackPage` jamais rendue.

**Pattern canonique** :
```ts
const msalConfig: Configuration = {
  auth: {
    clientId, authority, redirectUri,
    postLogoutRedirectUri: window.location.origin,
    navigateToLoginRequestUrl: false,  // OBLIGATOIRE
  },
  cache: { cacheLocation: "sessionStorage", storeAuthStateInCookie: false },
}
```

Anti-patterns : `true` ou omis (= true par défaut) ; compter sur replay MSAL.

**Validation** : `grep "navigateToLoginRequestUrl.*false" src/auth/msalConfig.ts
|| ERROR [MSAL_NAVIGATE_DEFAULT]`

#### 5.2.7.4 Route `/login` publique + autonome

Toute SPA avec `auth/azure-ad` actif **DOIT** définir :
- Route `/login` : composant `LoginPage` rendu **sans** `MainLayout`
  (page autonome, branding centré, bouton "Se connecter avec Microsoft")
- Mockup HTML `1-1-Connexion.html` présent dans `workspace/input/ui/`
  → fait foi pour le visuel
- Sinon → page minimaliste générique (logo + bouton) sans MainLayout

#### 5.2.7.5 Auth guard global dans `__root.tsx`

```tsx
const PUBLIC = new Set(["/login", "/authentication/login-callback"])
const HOME_AFTER_LOGIN = "/campagnes"  // ou page d'accueil métier

function RootComponent() {
  const isAuth = useIsAuthenticated()
  const location = useLocation()
  const isPublic = PUBLIC.has(location.pathname)

  if (!isAuth && !isPublic) return <Navigate to="/login" />
  // Garde anti-loop : auth + bookmark /login → home
  if (isAuth && location.pathname === "/login") return <Navigate to={HOME_AFTER_LOGIN} />
  if (isPublic) return <Outlet />  // login, callback : outlet nu sans MainLayout
  return <MainLayout><Outlet /></MainLayout>
}
```

`/login` sans menu, autres routes wrappées `MainLayout`. Callback traverse
le guard (sinon `handleRedirectPromise` jamais appelé).

#### 5.2.7.6 Token sessionStorage — clé partagée

Clé `sessionStorage` du token Bearer nommée `{slug-projet}.accessToken`
(ex. `cms.accessToken`). Lue par `httpClient.ts` (US `3-1` typique) et
**DOIT** être écrite par `LoginPage` après `loginPopup` :

```ts
const result = await msal.loginPopup(request)
if (result.accessToken) sessionStorage.setItem("cms.accessToken", result.accessToken)
```

Nettoyage dans bouton Déconnexion MainLayout :
```ts
sessionStorage.removeItem("cms.accessToken")
await msal.logoutPopup({...})
```

#### 5.2.7.7 Route racine `/` — redirect auth-aware

`/` (index) avec `beforeLoad` :
- User auth (`getAllAccounts().length > 0`) → `redirect /campagnes` (ou page d'accueil FEAT)
- Sinon → `redirect /login`

Anti-pattern récurrent : oublier `/` → TanStack Router rend "Not Found"
sur URL racine. PO doit toujours déclarer une page d'accueil authentifiée
par défaut (typiquement 1ère feature post-login).

#### 5.2.7.8 Anti-récap (grep en self-check dev-frontend)

- ❌ `import.meta.env.VITE_AZ_*` dans code applicatif
- ❌ `new PublicClientApplication({ auth: { clientId: "<litéral>" }})` (hardcode)
- ❌ Routes protégées sans guard dans `__root.tsx`
- ❌ `MainLayout` enveloppant `/login`
- ❌ Token Bearer attendu par `httpClient` mais jamais écrit en sessionStorage par `LoginPage`
- ❌ Pas de route `/` index → "Not Found" runtime
- ❌ `navigateToLoginRequestUrl: true` (défaut MSAL) ou clé absente — loop /login post-auth (§5.2.7.3.ter)
- ❌ Guard `__root.tsx` qui n'auto-redirige PAS un utilisateur auth déjà sur `/login` vers la home (§5.2.7.5)

#### 5.2.7.9 CORS — config OBLIGATOIRE backend (dev + prod)

SPA sur origin ≠ backend (typique dev `:5173` ↔ `:8080`) → config CORS
explicite obligatoire. Sinon **toute `fetch` échoue silencieusement
avec `TypeError: Failed to fetch`** (préflight OPTIONS sans
`Access-Control-Allow-*`).

Symptômes : page blanche error boundary, DevTools `blocked by CORS
policy`, backend logs vides (préflight n'arrive pas).

**Fix Spring Security** :
```kotlin
@Configuration
class CorsConfig(
    @Value("\${APP_CORS_ALLOWED_ORIGINS:http://localhost:5173,http://localhost:4173}")
    private val allowedOriginsCsv: String,
) {
    @Bean
    fun corsConfigurationSource(): CorsConfigurationSource {
        val config = CorsConfiguration().apply {
            allowedOrigins = allowedOriginsCsv.split(",").map { it.trim() }
            allowedMethods = listOf("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            allowedHeaders = listOf("*")
            exposedHeaders = listOf("Location", "Content-Disposition")
            allowCredentials = true
            maxAge = 3600
        }
        return UrlBasedCorsConfigurationSource().apply { registerCorsConfiguration("/**", config) }
    }
}
```

**ET** brancher `http.cors { }` dans `SecurityFilterChain` (sinon bean ignoré).

**Stacks non-Kotlin** :
| Stack backend | Pattern CORS |
|---|---|
| `dotnet-minimalapi` | `services.AddCors(o => o.AddDefaultPolicy(b => b.WithOrigins(...).AllowAnyMethod().AllowAnyHeader().AllowCredentials()))` + `app.UseCors()` |
| `python-fastapi` | `app.add_middleware(CORSMiddleware, allow_origins=[...], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` |
| `node-express` | `app.use(cors({ origin: [...], credentials: true }))` |

**Alternative dev only — Vite proxy** (évite CORS, redirige `/api` et
`/auth/` vers backend depuis même origin) :
```ts
server: {
  proxy: {
    "/api/":  { target: "https://localhost:44328", changeOrigin: true, secure: false },
    // ⚠️ POST-MORTEM 2026-05-21 — Slash final OBLIGATOIRE sur '/auth/' :
    // sans slash, le prefix-match capture aussi '/authentication/login-callback'
    // (route SPA MSAL callback) → proxy vers backend → 401 Spring Security →
    // Azure AD redirect échoue silencieusement. Le slash final force le match
    // strict de '/auth/config' uniquement.
    "/auth/": { target: "https://localhost:44328", changeOrigin: true, secure: false },
  }
}
```
À utiliser **uniquement en dev** ; prod requiert CORS backend ou même-origin.

Anti-pattern : oublier `cors()` dans `SecurityFilterChain` → bean
présent mais ignoré → comportement aléatoire.

#### 5.2.7.10 HTTPS obligatoire en dev

Azure AD refuse Redirect URIs non-HTTPS sauf `http://localhost` strict.
URI `https://localhost:{port}/login-callback` → SPA + backend HTTPS sur
ports exacts.

**Vite (frontend)** :
```ts
import basicSsl from "@vitejs/plugin-basic-ssl"
export default defineConfig({
  plugins: [react(), basicSsl()],
  server:  { https: {}, port: 5185, strictPort: true },
  preview: { https: {}, port: 5185 },
})
```
Lib : `@vitejs/plugin-basic-ssl` (capability `dev-https` du catalogue
`react.libs.json` `onDemand`).

**Spring Boot (backend)** :
```yaml
server:
  port: 44328
  ssl:
    enabled: true
    key-store: classpath:keystore.p12
    key-store-password: changeit
    key-store-type: PKCS12
    key-alias: backend
    key-password: changeit
```

Keystore via script idempotent (`scripts/generate-dev-keystore.{ps1,sh}`) :
```bash
keytool -genkeypair -alias backend -keyalg RSA -keysize 2048 \
  -storetype PKCS12 -keystore src/main/resources/keystore.p12 \
  -validity 3650 -dname "CN=localhost,OU=Dev,O=cms,L=Paris,C=FR" \
  -storepass changeit -keypass changeit -ext "san=dns:localhost,ip:127.0.0.1"
```

`keystore.p12` → `.gitignore` (jamais committer).

**Config dev** : l'URL API publique du frontend et
`APP_CORS_ALLOWED_ORIGINS=https://localhost:5185` sont declarees dans
`stack.md`, puis propagees par `arch` vers la config native du frontend
et du backend.

**Acceptation cert auto-signé** : user visite **une fois**
`https://localhost:5185/` puis `https://localhost:44328/auth/config` →
"Avancé → Procéder vers localhost". Sinon SPA fetch backend →
`NET::ERR_CERT_AUTHORITY_INVALID`.

**Anti-patterns** : App Reg `https://localhost:5185` mais SPA HTTP
`:5173` → `AADSTS900971` ; cert non accepté → `TypeError: Failed to
fetch` ; mixed content (SPA HTTPS + backend HTTP) → navigateur bloque.

---

### 5.3 Application monolithique

- Auth via OpenID Connect (redirect), session serveur (cookie sécurisé, token jamais exposé navigateur)
- Non auth → redirect login. Auth sans droit → 403 (pas de loop).

---

## 6. Comportements attendus

- Non auth → aucun accès, redirect Azure AD
- Auth → accès selon droits, session maintenue (silent refresh SPA)
- Non autorisé → 403 message, jamais redirect login

## 7. Symptômes courants

- Accès refusé : groupe manquant, roles absents
- Erreur auth : authority/audience invalide, config env
- Boucle login : redirect URI / état auth mal gérés
- API refuse : token absent/non-attaché, scope invalide
- Groupes absents : token trop volumineux → utiliser Graph

## 8. Interdits projet

- Valeurs Azure AD hardcodées, ClientSecret frontend
- Validation JWT manuelle, stockage/parsing manuel token
- Mapping groupes en dur, logique sécurité uniquement frontend
- Appel API sans token, duplication logique auth, login interne custom
- Stockage credentials utilisateur

## 9. Hors scope

MFA, fédération externe, gestion utilisateurs.
