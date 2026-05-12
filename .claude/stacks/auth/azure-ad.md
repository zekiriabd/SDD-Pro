# Tech Spec: auth-azure

Status: Draft  
Tech Spec ID: tech-auth-azure  
Scope: authentification et autorisation Azure AD — independant de toute stack ou langage. Chaque implementation (backend, SPA, monolithe) doit appliquer ces regles selon sa technologie.

---

## 1. Principe universel

- Authentification via Azure AD (Microsoft Entra ID) contre un tenant unique.
- Une seule App Registration partagee entre tous les composants (frontend, backend).
- Aucun secret applicatif cote client (pas de ClientSecret).
- Utilisation des flux standards Microsoft :
  - SPA : Authorization Code + PKCE
  - Backend : validation JWT (Bearer token)
  - Monolithe : OpenID Connect + session
- Toutes les configurations proviennent des variables d’environnement (§2).
- Le token JWT est la source unique de verite pour :
  - l’identite
  - les groupes
  - les droits
- Aucune logique specifique a un framework ne doit etre supposee (React, .NET, Spring, etc.).

---

## 2. Variables d’environnement

Chargees au demarrage. L’application doit s’arreter si une variable est absente.

### Variables obligatoires

- AZ_TENANTID : identifiant du tenant Azure AD
- AZ_CLIENTID : identifiant de l’application enregistree (frontend OU API selon contexte)
- AZ_DOMAIN : domaine du tenant
- AZ_AUDIENCES : liste des audiences acceptees par le backend (separees
  par virgule). **Format strict** : GUIDs (ou `api://{guid}`) separes par
  une seule virgule, **sans guillemets, sans espaces**. Inclure les deux
  formes `api://{guid},{guid}` par App Reg pour etre robuste au flag
  `accessTokenAcceptedVersion` du manifest (v1 emet `aud=api://{guid}`,
  v2 emet `aud={guid}`). Exemple valide pour 2 App Reg :
  `api://<REDACTED>-...,<REDACTED>-...,api://<REDACTED>-...,<REDACTED>-...`.
  Voir Piege 7 (§3) pour le binding Spring robuste aux quotes parasites
  Windows.
- AZ_BE_CALLBACKPATH : chemin de retour backend (ex: /signin-oidc)
- AZ_FE_CALLBACKPATH : chemin de retour frontend (ex: /auth/callback)

### Variables optionnelles (recommandees pour multi-stack)

- AZ_INSTANCE : URL de base (defaut = https://login.microsoftonline.com/)
- AZ_AUTHORITY : override complet si necessaire
- AZ_SCOPES : scopes supplementaires (separes par espace)
- AZ_LOG_LEVEL : niveau de log (debug/info/warn/error)

### Regles strictes

- Toutes ces valeurs doivent etre injectees via environnement (env, .env, secrets manager, etc.).
- Aucune valeur Azure AD ne doit etre hardcodee.
- Les librairies d’authentification doivent lire ces variables dynamiquement.

### Piege App Registration : plateforme Web vs Single-page application (post-mortem 2026-05-08)

**Bug** : reutiliser une App Registration Azure AD existante (creee
pour un backend .NET, .NET MVC ou Java/Kotlin server-side) pour un
nouveau frontend SPA (React, Vue, Angular, Blazor WASM) sans ajouter
la plateforme **Single-page application**.

**Erreur Azure AD** :
```
AADSTS50011: The redirect URI 'http://localhost:{port}/login-callback'
specified in the request does not match the redirect URIs configured
for the application '{ClientId}'.
```

**Cause** : Azure AD distingue deux plateformes mutuellement exclusives
sur les redirect URIs :

| Plateforme | Flow | Client | Utilise par |
|---|---|---|---|
| **Web** | Authorization Code (avec ClientSecret) | Confidential | .NET (`AddMicrosoftIdentityWebApp`), Spring Boot OIDC server-side, Java MVC |
| **Single-page application** | Authorization Code + PKCE (sans secret) | Public | React + MSAL, Vue + MSAL, Angular + MSAL, Blazor WASM |

**Une URI declaree sous "Web" n'est PAS valide pour un SPA**, meme si
le path est identique (`/login-callback`). Azure AD rejette en
AADSTS50011.

**Pattern obligatoire** : dans Azure Portal → App registrations →
{app} → **Authentication** :

1. Si l'app est partagee entre backend (.NET/Spring) et frontend (SPA) :
   - Plateforme **Web** : redirect URIs du backend (callback OIDC)
   - Plateforme **Single-page application** : redirect URIs du SPA
   - Les deux plateformes coexistent, pas de conflit
2. Si l'app est nouvelle pour un SPA seulement :
   - Plateforme **Single-page application** uniquement
3. Eviter de cocher "Implicit grant" (legacy, deprecated par Microsoft
   pour SPA) — PKCE seul suffit

**Verification rapide** apres ajout de la plateforme SPA :
- Sous "Web" : presence de "Front-channel logout URL", "Implicit grant
  and hybrid flows" → c'est l'ancien flow .NET
- Sous "Single-page application" : juste la liste des Redirect URIs,
  pas de ClientSecret requis → c'est le flow PKCE pour SPA

**Symptome si oublie** : login redirect Azure OK, ecran login Microsoft
affiche, login OK, MAIS au callback → AADSTS50011 immediat. Le SPA
ne demarre jamais. Build vert, code OK, runtime cassee par config
portail.

### Piege Windows + Git Bash (MSYS path conversion, post-mortem 2026-05-08)

**Bug** : sur Windows, lancer Git Bash (MSYS2) et faire :
```bash
export AZ_FE_CALLBACKPATH=/login-callback
```
mange la valeur en `C:/Program Files/Git/login-callback` car MSYS2
convertit automatiquement les chemins Unix-style commencant par `/`
en chemins Windows quand ils sont passes en parametre. Le backend
expose alors `redirectUri: "C:/Program Files/Git/login-callback"`
via `/api/config/auth` → MSAL plante au callback (URL invalide).

**Pattern obligatoire** sur Windows : definir les variables
d'environnement contenant des paths Unix-style **via PowerShell** ou
via `setx`, **pas via export Git Bash** :
```powershell
# PowerShell — pas de conversion MSYS
[System.Environment]::SetEnvironmentVariable('AZ_FE_CALLBACKPATH', '/login-callback', 'User')
[System.Environment]::SetEnvironmentVariable('AZ_BE_CALLBACKPATH', '/signin-oidc', 'User')
```
Ou en CMD : `setx AZ_FE_CALLBACKPATH "/login-callback"`.

**Workaround Git Bash** : doubler le slash initial pour bypasser MSYS :
```bash
export AZ_FE_CALLBACKPATH=//login-callback   # MSYS ne touche pas
```
(MSAL/Spring traitent `//login-callback` comme `/login-callback`.)

**Symptome** : le `/api/config/auth` du backend retourne un
`redirectUri` contenant `C:/Program Files/...`. MSAL throw au callback
sur SPA. A verifier des le premier run :
```bash
curl http://localhost:8080/api/config/auth
```
Aucun `C:/`, `C:\`, `\\` dans la reponse.

### Valeurs derivees (jamais en dur)

- Instance : ${AZ_INSTANCE} ou https://login.microsoftonline.com/
- Authority : ${AZ_INSTANCE}/${AZ_TENANTID}
- Scope API :
  - api://${AZ_CLIENTID}/access_as_user
  - + scopes definis dans AZ_SCOPES

---

## 3. Validation du token (universel)

Tout composant recevant un token doit verifier automatiquement via une librairie standard :

- Signature valide (via JWKS Azure AD)
- Issuer valide :
  - https://login.microsoftonline.com/{tenant}/v2.0
  - accepter v1.0 et v2.0 si necessaire
- Audience valide :
  - AZ_CLIENTID
  - api://AZ_CLIENTID
  - valeurs declarees dans AZ_AUDIENCES
  - les audiences sont cumulatives (jamais remplacees)
- Expiration valide (exp)
- Non utilisation de validation manuelle (toujours via middleware/lib officielle)

### Logs (dev uniquement)

- echec validation token
- audience invalide
- issuer invalide
- acces refuse

---

## 4. Autorisation par groupes

### 4.1 Source des droits

Les droits sont determines uniquement par :

- claim `groups`
- ou claim `roles`

Aucune base locale de roles/permissions n’est autorisee.

---

### 4.2 Mapping des droits

Le mapping est externe au code (config, JSON, env, DB config).

Regles :

- aucun mapping en dur
- modifiable sans redeploiement
- si mapping absent :
  - mode degrade (authentifie uniquement)
  - aucune erreur technique visible

---

### 4.3 Cas des groupes volumineux (IMPORTANT multi-stack)

Si le token ne contient pas `groups` mais :

- `_claim_names` ou `hasgroups`

Alors :

- l’application doit supporter la recuperation des groupes via Microsoft Graph
- OU fonctionner en mode degrade si non configure

---

### 4.4 Enforcement

- Le backend est toujours la source de verite
- Le frontend ne fait que masquer (UX)
- Toute verification critique doit etre cote serveur

---

## 5. Integration par type d’application

### 5.1 Backend (API)

- Authentification via Bearer token (Authorization: Bearer)
- Middleware obligatoire (pas de validation manuelle)
- Toute requete sans token → 401
- Token invalide → 401
- Token valide sans droit → 403

### Endpoint de configuration

Un endpoint public DOIT exister (ex: `/auth/config`) :

Contenu minimum :

- authority
- clientId
- scopes
- redirectUri (frontend)

Contraintes :

- accessible sans auth
- aucune donnee sensible
- utilise par tous les frontends (React, Angular, Blazor, etc.)

### Backend wiring — Microsoft.Identity.Web : injecter via IConfiguration, JAMAIS via named options (post-mortem 2026-05-07)

`AddMicrosoftIdentityWebApiAuthentication(configuration, "AzureAd")`
lit la section `"AzureAd"` de `IConfiguration` au moment de la
construction du JwtBearer handler (scheme par defaut `"Bearer"`). Les
options effectives sont stockees sous le **nom de scheme JwtBearer**,
pas sous le nom de section `"AzureAd"`.

**Anti-pattern (bug)** :
```csharp
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration, "AzureAd");

// FAUX — configure des named options sous la cle "AzureAd",
// jamais lues par le handler JwtBearer
builder.Services.Configure<MicrosoftIdentityOptions>("AzureAd", options =>
{
    options.TenantId = Environment.GetEnvironmentVariable("AZ_TENANTID");
    options.ClientId = Environment.GetEnvironmentVariable("AZ_CLIENTID");
    // ...
});
```

Symptome : `IDW10106: The 'ClientId' option must be provided.` au 1er
appel d'un endpoint (meme `[AllowAnonymous]`, car `UseAuthentication`
construit les options avant le routing). Build vert, startup vert,
plantage runtime au 1er hit.

**Pattern obligatoire** : injecter les valeurs des env vars dans la
section `"AzureAd"` de `IConfiguration` AVANT
`AddMicrosoftIdentityWebApiAuthentication`, via `AddInMemoryCollection` :

```csharp
string Required(string n) => Environment.GetEnvironmentVariable(n)
    ?? throw new InvalidOperationException($"Missing required environment variable: {n}");

var azureAdConfig = new Dictionary<string, string?>
{
    ["AzureAd:Instance"]     = Environment.GetEnvironmentVariable("AZ_INSTANCE") ?? "https://login.microsoftonline.com/",
    ["AzureAd:TenantId"]     = Required("AZ_TENANTID"),
    ["AzureAd:ClientId"]     = Required("AZ_CLIENTID"),
    ["AzureAd:Domain"]       = Environment.GetEnvironmentVariable("AZ_DOMAIN"),
    ["AzureAd:CallbackPath"] = Environment.GetEnvironmentVariable("AZ_BE_CALLBACKPATH") ?? "/signin-oidc",
};
var audiences = (Environment.GetEnvironmentVariable("AZ_AUDIENCES") ?? "")
    .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
for (int i = 0; i < audiences.Length; i++)
    azureAdConfig[$"AzureAd:ValidAudiences:{i}"] = audiences[i];

builder.Configuration.AddInMemoryCollection(azureAdConfig);

// Lit IConfiguration["AzureAd:*"] et configure le handler JwtBearer correctement
builder.Services.AddMicrosoftIdentityWebApiAuthentication(builder.Configuration, "AzureAd");
```

**Pourquoi** :
- `Configure<TOptions>(name, ...)` cree des **named options** ; le
  handler JwtBearer ne les lit jamais.
- `IConfiguration` est la **seule source** que
  `AddMicrosoftIdentityWebApiAuthentication` consomme.
- Aucune valeur Azure AD ne doit figurer dans `appsettings.json` (les
  secrets/identifiants restent en env vars). `AddInMemoryCollection`
  fait le pont env vars → `IConfiguration` sans persister sur disque.

| Stack backend | Pattern wiring | Ne JAMAIS |
|---|---|---|
| .NET (Microsoft.Identity.Web) | `AddInMemoryCollection` puis `AddMicrosoftIdentityWebApiAuthentication(cfg, "AzureAd")` | `Configure<MicrosoftIdentityOptions>("AzureAd", ...)` apres |
| Spring Boot (Java/Kotlin) | `application.yml` `azure.activedirectory.*` peuple via `${ENV_VAR}` interpolation | Hardcoder les valeurs |
| Node.js (passport-azure-ad) | Builder de strategie : passer un objet config construit depuis `process.env.*` | Mutation de strategie post-`use(...)` |

#### Piege 6 — Whitelist Swagger UI / OpenAPI (Spring Boot, post-mortem 2026-05-08)

Quand `auth/azure-ad` est actif sur un backend Spring Boot et que
`springdoc-openapi-starter-webmvc-ui` est inclus, les paths Swagger
DOIVENT etre whitelistes via `WebSecurityCustomizer.ignoring()`
(bypass complet de la chaine), PAS via `requestMatchers().permitAll()`
seul. Et le path OpenAPI DOIT etre custom (`/openapi`) — le path
standard `/v3/api-docs` reste protege par springdoc 2.6 meme avec
ignoring (bug springdoc + Spring Security 6.4).

**Pattern obligatoire** dans `SecurityConfig.kt` :
```kotlin
@Bean
fun webSecurityCustomizer(): WebSecurityCustomizer = WebSecurityCustomizer { web ->
    web.ignoring().requestMatchers(
        "/swagger",
        "/swagger/**",
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/openapi",
        "/openapi/**",
        "/openapi.yaml"
    )
}
```

Combine a `springdoc.api-docs.path: /openapi` + `springdoc.swagger-ui.path: /swagger`
dans `application.yml` (cf. `backend/kotlin-spring-boot.md §5.6`).

**Symptome si oublie** : `/v3/api-docs` ou `/swagger-ui.html` retourne
`401 Unauthorized` body vide. `requestMatchers("/v3/**").permitAll()`
ne suffit PAS. La cause exacte vient de l'interaction springdoc 2.6 +
`@RestControllerAdvice` capturant `AuthenticationException` — solution :
upgrade springdoc >= 2.7.0 + path custom + `WebSecurityCustomizer.ignoring`.

**Test de non-regression** : un appel HTTP sur n'importe quel endpoint
(meme `[AllowAnonymous]`) au demarrage doit retourner 200/401, jamais
500 IDW10106. Si IDW10106 → l'env var est bien lue MAIS jamais
appliquee aux options du handler.

#### Piege 7 — AZ_AUDIENCES binding fragile cote Spring (post-mortem 2026-05-12)

**Bug** : Spring Boot bind
`spring.security.oauth2.resourceserver.jwt.audiences: ${AZ_AUDIENCES}`
dans une `List<String>` en splittant sur la virgule **sans stripper les
guillemets ni les espaces**. Sur Windows, l'utilisateur tape
typiquement dans System Properties / `setx` une valeur du genre
`"guid1", "guid2"` (par mimetisme avec les conventions PowerShell / CSV) — la
liste effective devient `["\"guid1\"", " \"guid2\""]`. Le `aud` du JWT (sans
guillemets, sans espace) ne matche aucune entree → **tous les appels
authentifies retournent 401 silencieusement**, sans log Spring expliquant
le rejet (le validateur audience echoue avant le filter chain qui logge).

**Symptome** : login MSAL passe cote front, token visible dans
`sessionStorage.cms.accessToken`, mais `GET /api/v1/{ressource}` repond
401 systematiquement. Aucun log backend hors le 401 lui-meme.

**Fix obligatoire — `JwtDecoder` custom + parite .NET (audiences ET issuer)**.

Trois ecarts entre Spring resource server natif et Microsoft.Identity.Web
sont corriges en un seul bean :
1. `AZ_AUDIENCES` lu directement via `@Value` (evite le piege
   relaxed-binding `AZ_AUDIENCES` → `az.audiences` et non `az.audiences-raw`).
2. Auto-inclusion de `AZ_CLIENTID` + `api://{AZ_CLIENTID}` en audiences
   valides (`Audiences` .NET est additif, Spring natif est exhaustif).
3. Auto-acceptation des **deux issuers** Azure AD : v2
   (`login.microsoftonline.com/{tid}/v2.0`) ET v1
   (`sts.windows.net/{tid}/`). Le manifest Azure App Reg controle la
   version emise via `accessTokenAcceptedVersion` (default historique
   = `1` -> tokens v1 -> `iss=sts.windows.net/...`). Sans ce dual-issuer,
   tous les tokens v1 sont rejetes par Spring avec
   `"The iss claim is not valid"` (parite avec .NET MS.Identity.Web
   IssuerValidator multi-tenant).

```kotlin
// SecurityConfig.kt — bean JwtDecoder + helper buildAudiences
@Bean
fun jwtDecoder(
    @Value("\${spring.security.oauth2.resourceserver.jwt.issuer-uri}") issuerUri: String,
    @Value("\${AZ_TENANTID:}") tenantId: String,
    @Value("\${AZ_CLIENTID:}") clientId: String,
    @Value("\${AZ_AUDIENCES:}") audiencesRaw: String,
): JwtDecoder {
    // JwtDecoders.fromIssuerLocation hit le OIDC discovery v2 pour les JWKS
    // (clefs publiques) — meme JWKS valide pour tokens v1 et v2.
    val decoder = JwtDecoders.fromIssuerLocation(issuerUri) as NimbusJwtDecoder
    val audiences = buildAudiences(clientId, audiencesRaw)
    require(audiences.isNotEmpty()) {
        "Audiences vide : AZ_CLIENTID='$clientId' et AZ_AUDIENCES='$audiencesRaw'."
    }
    val tid = tenantId.trim().trim('"').trim('\'').trim()
    require(tid.isNotBlank()) { "AZ_TENANTID vide" }
    val validIssuers = setOf(
        "https://login.microsoftonline.com/$tid/v2.0",
        "https://sts.windows.net/$tid/",
    )
    val issValidator = JwtClaimValidator<String>(JwtClaimNames.ISS) { iss ->
        iss != null && iss in validIssuers
    }
    val audValidator = JwtClaimValidator<List<String>>(JwtClaimNames.AUD) { tokenAud ->
        tokenAud != null && tokenAud.any { it in audiences }
    }
    decoder.setJwtValidator(DelegatingOAuth2TokenValidator(
        JwtTimestampValidator(), // built-in : exp + nbf
        issValidator,
        audValidator,
    ))
    return decoder
}

// Parite Microsoft.Identity.Web : auto-inclusion implicite de
// AZ_CLIENTID + api://{AZ_CLIENTID} (couvre v1 aud=api://{cid} ET v2
// aud={cid}), plus liste AZ_AUDIENCES explicite (audiences additionnelles).
// Strip quotes parasites Windows (setx tape "guid1","guid2") + espaces + vides.
private fun buildAudiences(clientId: String, audiencesRaw: String): List<String> {
    val cid = clientId.trim().trim('"').trim('\'').trim()
    val implicit = if (cid.isBlank()) emptyList() else listOf(cid, "api://$cid")
    val explicit = audiencesRaw.split(",")
        .map { it.trim().trim('"').trim('\'').trim() }
        .filter { it.isNotBlank() }
    return (implicit + explicit).distinct()
}
```

**Parite Microsoft.Identity.Web** : en .NET (`AddMicrosoftIdentityWebApi`),
`Audiences` du `appsettings.json` est **additive** : `ClientId` et
`api://{ClientId}` sont valides automatiquement, `Audiences` ajoute des
audiences supplementaires (cas multi-tenant, scope partage entre apps).
Spring resource server natif est **exhaustif** (rien implicite) — cette
implementation reproduit la semantique .NET pour eviter aux equipes
qui migrent un backend .NET → Kotlin de devoir repeter le ClientId dans
AZ_AUDIENCES. Resultat : `AZ_AUDIENCES` ne contient QUE les audiences
**additionnelles** (autres App Reg dont l'API accepte les tokens).

```yaml
# application.yml — retirer "audiences:" sous jwt: (delegate au bean)
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.microsoftonline.com/${AZ_TENANTID}/v2.0
```

**Pourquoi cette forme** :
- `@Value("\${AZ_AUDIENCES:}")` lit l'env var **directement**. Tentative
  initiale via `@ConfigurationProperties(prefix="az")` + champ
  `audiencesRaw` echoue silencieusement : Spring mappe `AZ_AUDIENCES` →
  `az.audiences` (relaxed binding camelCase ne devine pas le suffixe
  `-raw`). `@Value` court-circuite cette ambiguite.
- `JwtDecoder` custom = on contourne completement le binding fragile de
  `spring.security.oauth2.resourceserver.jwt.audiences` (List<String>).
- `parseAudiences()` est testable unitairement (un test JUnit suffit
  pour les variantes `"a", "b"`, `'a','b'`, `a,b`, `a , b`, etc.).
- `JwtClaimValidator<List<String>>` accepte la forme array de la
  claim `aud` (specifiee par RFC 7519 §4.1.3, certains tokens emettent
  `aud=[...]` au lieu de scalaire).
- `require(audiences.isNotEmpty())` fail-fast au demarrage si l'env var
  est vide ou mal formee — pas de surprise 401 silencieux en prod. Le
  message inclut la valeur brute recue pour diagnostic immediat.

**Anti-pattern rejette** :
- ❌ Conserver `spring.security.oauth2.resourceserver.jwt.audiences:
  ${AZ_AUDIENCES}` sans le bean custom (vulnerable aux quotes)
- ❌ Strip cote env var uniquement (fragile : depend de qui declare la
  variable — Windows GUI, ansible, docker-compose, .env CI peuvent tous
  rajouter des quotes)

**Trigger pour dev-backend** : des qu'`auth/azure-ad` est actif sur un
stack Spring Boot (Kotlin ou Java), generer `AzureAdAudienceProperties`
+ `JwtDecoder` bean. Ne pas attendre qu'un humain debug un 401.

---

### 5.2 Frontend (SPA)

- Utilisation OBLIGATOIRE d’une librairie officielle :
  - MSAL ou equivalent compatible OAuth2/OIDC
- Flux : Authorization Code + PKCE
- Initialisation via fetch de l’endpoint backend `/api/config/auth`
  AVANT initialisation de MSAL (cf. Piege 4 ci-dessous). Aucune valeur
  Azure AD hardcodee dans le frontend, aucune dans `appsettings.json`
  ou equivalent — seul l’endpoint backend est source de verite a
  l’execution.

### Regles strictes

- aucun formulaire de login custom
- aucune gestion manuelle des tokens
- aucun stockage manuel (localStorage/sessionStorage interdit sauf via lib)
- aucun decodage manuel du JWT
- tous les appels API doivent passer par un client HTTP intercepte (interceptor)

### Compatibilite multi-framework

- React : utiliser MSAL + interceptor (fetch/axios)
- Angular : utiliser MSAL Angular guard/interceptor
- Blazor : utiliser Microsoft.Identity.Web
- autres : respecter OIDC standard + PKCE

### Integration Patterns par stack (BINDING — post-mortem 2026-05-03)

Trois pieges integration recurrents quand Azure AD est combine avec un SPA
+ un Backend separe. Chaque pattern doit etre applique **systematiquement**
au moment de la generation du code de la feature qui introduit l'auth.

#### Piege 1 — JS shim a charger dans le bootstrap SPA (sinon runtime exception)

| Stack frontend | Fichier a augmenter | Ligne a injecter |
|---|---|---|
| Blazor WebAssembly (`front-blazor-wasm`) | `wwwroot/index.html` | `<script src="_content/Microsoft.Authentication.WebAssembly.Msal/AuthenticationService.js"></script>` AVANT `<script src="_framework/blazor.webassembly.*.js">` |
| React + MSAL.js | `src/main.tsx` ou `index.html` | `import { PublicClientApplication } from "@azure/msal-browser"` (npm) — chargement automatique |
| Vue 3 + MSAL.js | `src/main.ts` | Idem React |
| Angular | `app.module.ts` | `MsalModule.forRoot(...)` — gere par MSAL Angular |

Symptome si manquant en Blazor WASM : `Could not find 'AuthenticationService.init'`
au premier rendu d'un composant `[Authorize]`.

#### Piege 2 — Runtime config `Api:BaseAddress` cote SPA

Le Frontend doit savoir ou est le Backend. Sans config, il appelle des
endpoints sur sa propre origine et echoue silencieusement (404/CORS).

| Stack frontend | Fichier de config runtime | Cle | Valeur typique dev |
|---|---|---|---|
| Blazor WebAssembly | `wwwroot/appsettings.json` | `Api:BaseAddress` | URL HTTPS Backend (alignee `launchSettings.json`) |
| React | `public/runtime-config.json` | `apiBaseUrl` | Idem |
| Vue 3 | `public/runtime-config.json` | `apiBaseUrl` | Idem |
| Angular | `src/assets/runtime-config.json` | `apiBaseUrl` | Idem |

Aucun secret dans ce fichier — uniquement l'URL. Les valeurs Azure AD
(tenantId, clientId, audiences, scopes) sont exposees au SPA via
l'endpoint Backend `/api/config/auth` (cf. §5.1 Endpoint de configuration).

#### Piege 3 — URL filter du `AuthorizationMessageHandler` / interceptor

Le composant qui injecte automatiquement le `Authorization: Bearer <token>`
sur les appels HTTP sortants DOIT etre configure pour couvrir les DEUX
origines (SPA + Backend), pas seulement la BaseUri du SPA.

| Stack frontend | Composant | URLs a inclure |
|---|---|---|
| Blazor WASM | `AuthorizationMessageHandler.ConfigureHandler(authorizedUrls: ...)` | `[navigation.BaseUri, apiBaseUrl]` |
| React + Axios | Axios interceptor `request.use(...)` | matching sur `apiBaseUrl` ou instance Axios dediee API |
| Vue 3 + Axios | Idem React | Idem |
| Angular | `HttpInterceptor` | `req.url.startsWith(apiBaseUrl)` |

Symptome si oublie : tous les appels API partent SANS token → Backend
rejette en `401 Unauthorized` (visible dans Refit / fetch / axios), build
vert mais runtime cassee.

Pattern Blazor WASM canonique :
```csharp
public class SimAuthorizationMessageHandler : AuthorizationMessageHandler
{
    public SimAuthorizationMessageHandler(
        IAccessTokenProvider provider,
        NavigationManager navigation,
        SimAuthScopes scopes,
        SimApiBaseAddress apiBase)
        : base(provider, navigation)
    {
        var urls = new List<string> { navigation.BaseUri };
        if (!string.IsNullOrWhiteSpace(apiBase.Value))
            urls.Add(apiBase.Value);
        ConfigureHandler(authorizedUrls: urls.ToArray(), scopes: scopes.Values);
    }
}
```

#### Piege 4 — Bootstrap MSAL avant que IConfiguration soit peuplee (post-mortem 2026-05-XX)

`AddMsalAuthentication(...)` lit `IConfiguration["AzureAd:Authority"]`
et `IConfiguration["AzureAd:ClientId"]` **synchroniquement** pendant
le bootstrap. Si ces cles sont vides au moment de l'appel, MSAL fait
`new URL("")` → exception runtime avant meme le premier rendu :

```
Microsoft.JSInterop.JSException: Failed to construct 'URL': Invalid URL
TypeError: Invalid URL
    at new qr (AuthenticationService.js)
    at Ur.init (AuthenticationService.js)
```

**Cause** : le `wwwroot/appsettings.json` (ou equivalent) contient des
placeholders `Authority: ""`, `ClientId: ""` — l'agent suppose que
l'endpoint backend `/api/config/auth` les peuplera "magiquement". Or
aucun mecanisme automatique ne fait ce fetch avant `AddMsalAuthentication`.

**Pattern obligatoire** : fetch `/api/config/auth` AVANT MSAL et patch
`builder.Configuration` en RAM. Aucune valeur Azure AD ne doit jamais
figurer dans `appsettings.json` (eviter de generer des chaines vides
qui font croire a une config valide).

| Stack frontend | Position du fetch | Cible du patch                                |
|----------------|-------------------|-----------------------------------------------|
| Blazor WASM    | Avant `AddMsalAuthentication` dans `Program.cs` (apres `WebAssemblyHostBuilder.CreateDefault`) | `builder.Configuration["AzureAd:Authority"]`, `["AzureAd:ClientId"]` |
| React + MSAL.js | Avant `new PublicClientApplication(config)` dans `main.tsx` | objet `Configuration` MSAL (`auth.authority`, `auth.clientId`) |
| Vue 3 + MSAL.js | Avant `app.use(msalPlugin)` dans `main.ts`   | Idem React                                     |
| Angular        | `APP_INITIALIZER` provider dans `app.module.ts` qui fetch et appelle `MsalModule.forRoot(...)` dynamiquement | factory MSAL                                   |

Pattern Blazor WASM canonique (`Program.cs`) :
```csharp
using System.Net.Http.Json;

var builder = WebAssemblyHostBuilder.CreateDefault(args);
builder.RootComponents.Add<App>("#app");
builder.RootComponents.Add<HeadOutlet>("head::after");

var apiBaseAddress = builder.Configuration["Api:BaseAddress"]
                     ?? builder.HostEnvironment.BaseAddress;

// Bootstrap fetch — DOIT etre fait AVANT AddMsalAuthentication
using var bootstrapHttp = new HttpClient { BaseAddress = new Uri(apiBaseAddress) };
var authConfig = await bootstrapHttp.GetFromJsonAsync<AuthConfigModel>("api/config/auth")
    ?? throw new InvalidOperationException(
        $"Endpoint /api/config/auth indisponible. Verifier que le backend tourne sur {apiBaseAddress} " +
        "et que les variables AZ_TENANTID, AZ_CLIENTID, AZ_DOMAIN sont definies.");

builder.Configuration["AzureAd:Authority"] = authConfig.Authority;
builder.Configuration["AzureAd:ClientId"]  = authConfig.ClientId;

builder.Services.AddSingleton(new SimAuthScopes { Values = authConfig.Scopes });
builder.Services.AddTransient<SimAuthorizationMessageHandler>();

builder.Services.AddMsalAuthentication(options =>
{
    builder.Configuration.Bind("AzureAd", options.ProviderOptions.Authentication);
    foreach (var scope in authConfig.Scopes)
        options.ProviderOptions.DefaultAccessTokenScopes.Add(scope);
});

await builder.Build().RunAsync();
```

**Contraintes runtime** :
- Le backend (`SIM.Api`) DOIT tourner sur `Api:BaseAddress` AVANT que le
  frontend ne demarre. Sinon l'`InvalidOperationException` ci-dessus
  signale clairement la cause (pas de plantage MSAL obscur).
- Configurer le profil multi-projet de l'IDE pour demarrer le backend
  en premier (`launchSettings.json` `Order` ou tasks Visual Studio).

**Symptome** si Piege 4 ignore : exception MSAL `Failed to construct
'URL': Invalid URL` au tout premier rendu. Le build est vert, les
`appsettings.json` "ressemble" a une config valide (cles presentes
mais valeurs vides) — d'ou le diagnostic difficile.

#### Piege 5 — Routes auth + activation de l'auth globale (post-mortem 2026-05-XX)

`AddMsalAuthentication` configure le client MSAL mais NE force PAS la
redirection vers Azure AD. Sans configuration explicite, les pages
sont publiques par defaut et MSAL n'est jamais invoque. Symptome
typique : la page d'accueil (`/`) s'affiche normalement (ex.
`<h1>Hello, world!</h1>`) sans redirection vers le login Azure AD.

**Trois elements obligatoires manquent souvent ensemble** :

1. **Auth globale activee** au niveau du projet
2. **Page handler des callbacks MSAL** sur la route `/authentication/{action}`
3. **Marquage `[AllowAnonymous]`** explicite sur la page handler (sinon
   boucle infinie de redirection : login → handler → "non auth" → login)

| Stack frontend | Element 1 (auth globale)                                      | Element 2 (handler callback) | Element 3 (anonymous) |
|----------------|---------------------------------------------------------------|------------------------------|------------------------|
| Blazor WASM    | `@attribute [Authorize]` dans `_Imports.razor`                | `Pages/Authentication.razor` avec `<RemoteAuthenticatorView Action="@Action" />` | `@attribute [AllowAnonymous]` dans `Authentication.razor` |
| React + MSAL.js | `<MsalAuthenticationTemplate interactionType={Redirect}>` **monte directement dans `main.tsx`** entre `<MsalProvider>` et `<RouterProvider>` (cf. §5.2 React Pattern canonique) | MSAL gere le callback via redirect URI configure (pas de composant explicite necessaire en SPA) | Route publique pour `/auth/callback` (handler MSAL declenche au mount) |
| Vue 3 + MSAL.js | Guard `router.beforeEach` qui appelle `acquireTokenRedirect` | Composant `Callback.vue` sur `/auth/callback` | Route `meta.requiresAuth: false` |
| Angular        | `MsalGuard` dans `canActivate` global                         | Route `/auth/callback` avec `MsalRedirectComponent` | Pas de `MsalGuard` sur cette route |

**Pattern React canonique (post-mortem 2026-05-08)** :

L'erreur recurrente sur React : monter `<MsalProvider>` direct sans
`<MsalAuthenticationTemplate>` autour. Resultat : MSAL est instancie
mais le redirect Azure AD n'est jamais declenche, l'utilisateur reste
non-auth, tous les appels API partent sans Bearer → 401 silencieux.

`src/main.tsx` (ordre obligatoire) :
```tsx
import { type PublicClientApplication, InteractionType } from '@azure/msal-browser'
import { MsalProvider, MsalAuthenticationTemplate } from '@azure/msal-react'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MsalProvider instance={msalInstance}>
      <MsalAuthenticationTemplate interactionType={InteractionType.Redirect}>
        <QueryClientProvider client={queryClient}>
          <I18nextProvider i18n={i18n}>
            <RouterProvider router={router} />
          </I18nextProvider>
        </QueryClientProvider>
      </MsalAuthenticationTemplate>
    </MsalProvider>
  </StrictMode>,
)
```

**Anti-patterns** :
- ❌ Sortir `<MsalAuthenticationTemplate>` dans un composant
  `<AuthProvider>` qui appelle `useLocation()` de `@tanstack/react-router`
  : ce hook exige d'etre **dans** `<RouterProvider>`. Si `<AuthProvider>`
  enveloppe `<RouterProvider>`, `useLocation()` plante. Si `<AuthProvider>`
  est dans `<RouterProvider>`, le guard MSAL ne s'applique qu'aux
  composants enfants — l'init de `<RouterProvider>` declenche deja
  les loaders/queries qui appellent l'API → 401 avant login.
- ❌ Compter sur un loader TanStack Router pour declencher le login :
  `MsalAuthenticationTemplate` doit etre **outside** des loaders.
- ❌ Placer le template dans une layout-route : meme effet (loaders
  parents s'executent avant).

**Symptome si oublie** : `GET /api/v1/...` retourne `401 Unauthorized`,
DevTools Network ne montre **aucun header Authorization**, sessionStorage
vide (pas de cle MSAL). La page d'accueil s'affiche normalement et
les calls API echouent en silence.

**Pattern Blazor WASM canonique** :

`_Imports.razor` (auth globale) :
```razor
@using Microsoft.AspNetCore.Authorization

@attribute [Authorize]
```

`Pages/Authentication.razor` (handler callback) :
```razor
@page "/authentication/{action}"
@attribute [Microsoft.AspNetCore.Authorization.AllowAnonymous]
@using Microsoft.AspNetCore.Components.WebAssembly.Authentication

<RemoteAuthenticatorView Action="@Action" />

@code {
    [Parameter] public string? Action { get; set; }
}
```

`App.razor` (deja documente — wrap MSAL avec `RedirectToLogin`) :
```razor
<CascadingAuthenticationState>
    <Router AppAssembly="@typeof(App).Assembly">
        <Found Context="routeData">
            <AuthorizeRouteView RouteData="@routeData" DefaultLayout="@typeof(MainLayout)">
                <NotAuthorized>
                    <RedirectToLogin />
                </NotAuthorized>
            </AuthorizeRouteView>
        </Found>
    </Router>
</CascadingAuthenticationState>
```

`Shared/RedirectToLogin.razor` :
```razor
@inject NavigationManager Navigation

@code {
    protected override void OnInitialized()
        => Navigation.NavigateToLogin("authentication/login");
}
```

**Flow runtime attendu** :
1. User arrive sur `/` → `Home.razor` herite `[Authorize]` global
2. `<AuthorizeRouteView>` voit non-auth → render `<RedirectToLogin/>`
3. `Navigation.NavigateToLogin("authentication/login")` → route prise par `Authentication.razor`
4. `<RemoteAuthenticatorView Action="login">` declenche MSAL → redirect Azure AD
5. Azure AD authentifie → callback `/authentication/login-callback` → meme page (`Authentication.razor`), MSAL stocke le token
6. Retour `/` avec auth OK → `Home.razor` s'affiche

**Symptomes** si Piege 5 ignore :
- Pas de `[Authorize]` global → pages publiques, jamais de redirect (l'app demarre normalement, "Hello world" s'affiche)
- Pas de `Authentication.razor` → route 404 quand `RedirectToLogin` redirige, MSAL ne peut pas finaliser
- Pas de `[AllowAnonymous]` sur `Authentication.razor` → boucle infinie de redirection (la page de callback est elle-meme protegee)

**Pages publiques explicites** : si une page doit rester publique
malgre l'auth globale (ex. page "About", page de demonstration sans
donnees), ajouter explicitement :
```razor
@attribute [AllowAnonymous]
```

**Bootstrap automatique des fichiers infrastructure (Blazor WASM)** :
les 3 fichiers framework du Piege 5 ne sont PAS la responsabilite de
`dev-frontend` :
- `Pages/Authentication.razor`
- `Shared/RedirectToLogin.razor`
- `_Imports.razor` augmentation (`@attribute [Authorize]`)

Ils sont produits **une seule fois** par `arch` lors de l'init projet
via `frontend/blazor-webassembly.md §2.2.1 STEP 3f` (conditionnel :
uniquement si `auth/azure-ad` actif sous `## Active Auth Specs`).

Lors d'une feature, `dev-frontend` doit :
- **Preserver** ces 3 fichiers tels quels (jamais les modifier).
- Les inclure dans la liste `preserves:` des `_Imports.razor` augments
  (preserves : `Authorize`, `Microsoft.AspNetCore.Authorization`).
- Pour `App.razor` et `Program.cs` (touches par feature) : appliquer
  les patterns Piege 4 et Piege 5 ci-dessus.

`dev-frontend` ne planifie PAS ces 3 fichiers dans son plan inline sauf
si la feature elle-meme modifie leur contenu (cas rare — typiquement
jamais).

---

### 5.2.6 Déconnexion (Logout) — AUCUN CODE MÉTIER À ÉCRIRE

**Principe** : la déconnexion est **entièrement déléguée à Azure AD**. Il
n'y a **aucun endpoint backend de logout** à coder, **aucune logique
métier** côté backend, **aucune invalidation de session serveur** (les
SPA n'ont pas de session serveur).

#### Backend (API REST + JWT Bearer) — 0 ligne de code

- Pas d'endpoint `/auth/logout`, pas de `SignOutAsync`, pas de
  blacklist de tokens. Le JWT est stateless et expire de lui-même
  (`exp` claim, typiquement 1h).
- Si une feature mentionne « logout backend », il s'agit d'un
  **anti-pattern** — STOP + ERROR `[DERIVE_VIOLATION]` côté agent
  `dev-backend`.

#### Frontend SPA (React / Vue / Angular / Blazor WASM) — 1 ligne MSAL

| Stack | API logout | Effet |
|---|---|---|
| React + MSAL.js | `msalInstance.logoutRedirect({ postLogoutRedirectUri })` | Clear cache MSAL local + redirect Azure AD `/oauth2/v2.0/logout` + retour `postLogoutRedirectUri` |
| Vue 3 + MSAL.js | Idem React | Idem |
| Angular + MSAL Angular | `msalService.logoutRedirect({ postLogoutRedirectUri })` | Idem |
| Blazor WASM | `NavigationManager.NavigateToLogout("authentication/logout")` + `RemoteAuthenticatorView Action="logout"` | Idem (handler déjà bootstrapé par arch — cf. §5.2 Piege 5) |

**Configuration unique requise** : `postLogoutRedirectUri` doit être
déclaré **dans l'App Registration Azure AD** (portail → Authentication
→ Single-page application → Redirect URIs) et passé à MSAL au moment
de l'appel `logoutRedirect`.

**Anti-patterns** :
- ❌ Implémenter un endpoint `/api/logout` côté backend → inutile (JWT stateless)
- ❌ Effacer `localStorage`/`sessionStorage` manuellement → MSAL fait ça via `logoutRedirect`
- ❌ Décoder le JWT pour invalider une « session » côté serveur → pas de session
- ❌ Maintenir une « liste noire » de tokens → coûteux et inutile (TTL court suffit)

**Pour SDD_Pro — agents dev-\* doivent skip toute US `*-Deconnexion`** :
si une SPEC liste explicitement la déconnexion comme livrable, c'est
purement de la **configuration** (1 ligne MSAL côté frontend, 0 ligne
backend). Le PO ne doit normalement pas générer d'US dédiée — si
généré, l'US se résume à un bouton qui appelle `logoutRedirect()`.

#### Cas particulier — Blazor Server / ASP.NET MVC cookie (5.3)

Ces stacks **ne sont PAS des SPA**. La déconnexion utilise une session
serveur (cookie) et nécessite l'endpoint auto-mappé
`/MicrosoftIdentity/Account/SignOut` fourni par `Microsoft.Identity.Web`.
**Ce code est généré par la lib elle-même, pas par dev-backend**.

---

### 5.2.7 Conventions SPA + Azure AD — anti-patterns récurrents (post-mortem 2026-05-11)

> **Pourquoi cette section** : sur le projet `cms-front` v6.1, 5 anti-patterns
> identiques ont été produits par `dev-frontend` en l'absence d'orientation
> explicite. Ce paragraphe codifie la convention pour empêcher la
> reproduction. **Load-bearing pour tout SPA avec auth=azure-ad.**

#### 5.2.7.1 Endpoint `/auth/config` — OBLIGATOIRE côté backend

Dès que `auth/azure-ad` est actif ET qu'un stack backend (`kotlin-spring-boot`,
`dotnet-minimalapi`, `python-fastapi`, `node-express`) est actif, le backend
**DOIT** exposer `GET /auth/config` (route publique, hors filtre JWT) qui
retourne :

```json
{ "authority": "https://login.microsoftonline.com/{AZ_TENANTID}",
  "clientId": "{AZ_CLIENTID}",
  "scopes": ["api://{AZ_CLIENTID}/access_as_user"],
  "redirectUri": "{AZ_FE_CALLBACKPATH}" }
```

> **CRITIQUE — scope FE singleton, dérivé de `AZ_CLIENTID` (jamais `AZ_AUDIENCES`)**.
> MSAL.js v3 exige que tous les scopes d'un `loginPopup`/`acquireToken`
> appartiennent à **UN SEUL resource**. Construire `scopes` à partir de
> `AZ_AUDIENCES` (multi-valeurs, ex. `"guid1","guid2"`) produit deux
> `api://{guid}/access_as_user` de resources différents → MSAL construit
> une URL OAuth malformée → Azure répond `AADSTS900971 No reply address
> provided` (variante observée 2026-05-12 sur cms-front React + MSAL
> 3.27) ou `AADSTS28000 invalid_scope`. Le scope FE est **toujours**
> `api://${AZ_CLIENTID}/access_as_user` (le resource de l'app cliente
> elle-même). `AZ_AUDIENCES` reste utilisé **côté backend uniquement**
> dans `spring.security.oauth2.resourceserver.jwt.audiences` (§3) pour
> accepter des JWT émis pour plusieurs apps. Si un second resource est
> nécessaire côté FE, faire un `acquireTokenSilent({ scopes: ["api://{other}/access_as_user"] })`
> **séparé** — jamais un combo dans le `loginPopup` initial.

Cet endpoint est **scope arch** (Phase A bootstrap si stack backend + auth
azure-ad actifs) **OU** scope `dev-backend` de l'US auth fondatrice (US 1-1
typique). **Anti-pattern récurrent** : aucune US ne le matérialise, le
frontend lit `VITE_AZ_*` directement → cassé.

#### 5.2.7.2 Frontend MSAL — `VITE_AZ_*` INTERDIT

Vite ne propage **que** les vars préfixées `VITE_` au navigateur. L'agent
`dev-frontend` NE DOIT JAMAIS faire :

```ts
// ❌ ANTI-PATTERN — variable indéfinie à runtime
const clientId = import.meta.env.VITE_AZ_CLIENTID
```

À la place, **fetch `/auth/config` au bootstrap** puis initialise MSAL :

```ts
// ✅ Pattern canonique (cf. §5.2 Piege 4)
async function bootstrap() {
  const cfg = await fetch("/auth/config").then(r => r.json())
  const msal = new PublicClientApplication({ auth: { clientId: cfg.clientId, authority: cfg.authority, ... }})
  await msal.initialize()
  // render <MsalProvider instance={msal}>...
}
```

Format ERROR si violation détectée par hook ou self-check :
```
ERROR: dev-frontend {n}-{m} — anti-pattern MSAL config
CAUSE: [DERIVE_VIOLATION] lecture directe de VITE_AZ_CLIENTID / VITE_AZ_TENANTID
       — Vite ne propage pas AZ_* sans préfixe VITE_, et le SPEC azure-ad §5.2.7.1
       impose la fetch de /auth/config
FIX: bootstrap async via /auth/config, instance MSAL créée APRÈS résolution
```

#### 5.2.7.3 Mode popup vs redirect

**Default obligatoire** : `loginPopup()` / `logoutPopup()` — pas
`loginRedirect`. Justification : le SPA ne perd jamais son état, le retour
Azure AD est transitoire, le DX est meilleur. Exception : mobile (envisager
redirect si popup bloqué). À tracer dans un ADR si dérive.

#### 5.2.7.3.bis Redirect URI MSAL — composition runtime obligatoire (post-mortem 2026-05-11)

L'App Registration Azure AD enregistre une **URI complète** dans
`Authentication → Single-page application → Redirect URIs`, typiquement :
- Dev : `http://localhost:5173/login-callback`
- Prod : `https://app.exemple.com/login-callback`

Le path partagé entre dev/prod (`/login-callback` ici) est exporté côté env
backend sous `AZ_FE_CALLBACKPATH`. **Le frontend DOIT composer l'URI complète
runtime** :

```ts
// ✅ Pattern canonique
const cfg = await fetch("/auth/config").then(r => r.json())
const msal = new PublicClientApplication({
  auth: {
    clientId: cfg.clientId,
    authority: cfg.authority,
    redirectUri: window.location.origin + cfg.redirectUri, // ← composition runtime
    postLogoutRedirectUri: window.location.origin + "/login",
  },
  ...
})
```

```ts
// ❌ ANTI-PATTERN — Azure rejette avec AADSTS900971 / AADSTS50011
redirectUri: window.location.origin                       // path manquant
redirectUri: cfg.redirectUri                              // origin manquant (URI relative)
redirectUri: "http://localhost:5173/login-callback"       // hardcode (cassé en prod)
```

**Format ERROR si détecté** :
```
ERROR: dev-frontend {n}-{m} — redirectUri MSAL incomplet
CAUSE: [DERIVE_VIOLATION] redirectUri = window.location.origin (sans path) — Azure
       AD attend une URI complète enregistrée dans l'App Registration. Symptôme
       AADSTS900971 "No reply address provided" ou AADSTS50011 "redirect URI mismatch"
FIX: composer redirectUri = window.location.origin + cfg.redirectUri (cf. azure-ad.md §5.2.7.3.bis)
```

**Côté backend AuthConfigController** : `redirectUri` retourné par `/auth/config`
DOIT être un path commençant par `/` (jamais une URL complète, jamais vide).
Le strip Git Bash MSYS (§2.102) garantit ce format.

---

#### 5.2.7.4 Route `/login` publique + autonome

Toute application SPA avec `auth/azure-ad` actif **DOIT** définir :

- **Route `/login`** : composant `LoginPage` rendu **sans** le `MainLayout`
  (page autonome, branding centré, bouton "Se connecter avec Microsoft")
- Si un mockup HTML `1-1-Connexion.html` (ou équivalent basename US 1-1) est
  présent dans `workspace/input/ui/`, il **fait foi** pour le visuel
- Si aucun mockup → page minimaliste générique (logo + bouton) sans MainLayout

#### 5.2.7.5 Auth guard global dans `__root.tsx`

Le composant racine du router doit appliquer :

```tsx
// ✅ Pattern canonique
const PUBLIC = new Set(["/login"])
function RootComponent() {
  const isAuth = useIsAuthenticated()
  const location = useLocation()
  const isPublic = PUBLIC.has(location.pathname)
  if (!isPublic && !isAuth) return <Navigate to="/login" />
  if (isPublic) return <Outlet />
  return <MainLayout><Outlet /></MainLayout>
}
```

Effet : `/login` rendue sans menu, toutes les autres routes wrappées dans
`MainLayout` (menu global SPEC `2-Menu`).

#### 5.2.7.6 Token sessionStorage — clé partagée

Convention nommage : la clé `sessionStorage` du token Bearer est nommée
`{slug-projet}.accessToken` (ex. `cms.accessToken`). Cette même clé est
lue par `httpClient.ts` (US `3-1` typique) et **DOIT** être écrite par
`LoginPage` après `loginPopup` :

```ts
const result = await msal.loginPopup(request)
if (result.accessToken) sessionStorage.setItem("cms.accessToken", result.accessToken)
```

À nettoyer dans le bouton Déconnexion du MainLayout :
```ts
sessionStorage.removeItem("cms.accessToken")
await msal.logoutPopup({...})
```

#### 5.2.7.7 Route racine `/` — redirect auth-aware

Le bootstrap définit la route `/` (index) avec une `beforeLoad` qui :
- Si user authentifié (MSAL `getAllAccounts().length > 0`) → `redirect /campagnes` (ou page d'accueil par défaut documentée dans la SPEC)
- Sinon → `redirect /login`

**Anti-pattern récurrent** : oublier de définir `/` → TanStack Router rend
"Not Found" sur l'URL racine. Le PO doit toujours déclarer une **page d'accueil
authentifiée par défaut** dans la SPEC (typiquement la 1ère feature post-login).

#### 5.2.7.10 HTTPS obligatoire en dev (post-mortem 2026-05-11)

Azure AD refuse les Redirect URIs non-HTTPS sauf `http://localhost` strict (sans
port custom HTTPS-attendu). Quand l'App Registration enregistre une URI
`https://localhost:{port-custom}/login-callback`, l'environnement de dev DOIT
servir le SPA et le backend en HTTPS sur ces ports exacts.

##### Configuration Vite (frontend)

```ts
// vite.config.ts
import basicSsl from "@vitejs/plugin-basic-ssl"
// ...
export default defineConfig({
  plugins: [react(), tailwindcss(), basicSsl()],
  server: {
    https: {},   // active via plugin basic-ssl (cert auto-signé en cache)
    port: 5185,  // doit matcher l'App Registration
    strictPort: true,
  },
  preview: { https: {}, port: 5185 },
})
```

Lib à ajouter : `@vitejs/plugin-basic-ssl` (capability `dev-https` du
catalogue `react.libs.json` `onDemand`).

##### Configuration Spring Boot (backend)

```yaml
# src/main/resources/application.yml
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

Keystore généré une fois côté projet via `keytool` (script idempotent dans
`scripts/generate-dev-keystore.{ps1,sh}`) :

```bash
keytool -genkeypair -alias backend -keyalg RSA -keysize 2048 \
  -storetype PKCS12 -keystore src/main/resources/keystore.p12 \
  -validity 3650 -dname "CN=localhost,OU=Dev,O=cms,L=Paris,C=FR" \
  -storepass changeit -keypass changeit \
  -ext "san=dns:localhost,ip:127.0.0.1"
```

Le keystore `src/main/resources/keystore.p12` est ajouté au `.gitignore`
projet (le password est `changeit`, donc à ne JAMAIS commiter même en dev).

##### Variables d'environnement supplémentaires

```env
# workspace/output/src/cms-front/apps/web/.env.local
VITE_API_BASE_URL=https://localhost:44328
```

```env
# système (PowerShell setx ou .env backend)
APP_CORS_ALLOWED_ORIGINS=https://localhost:5185
```

##### Acceptation du certificat auto-signé

L'utilisateur visite **une fois** `https://localhost:5185/` puis
`https://localhost:44328/auth/config` dans son navigateur et clique
"Avancé → Procéder vers localhost (non sécurisé)". Sinon le SPA ne peut
fetch le backend (NET::ERR_CERT_AUTHORITY_INVALID).

##### Anti-pattern

- ❌ App Registration liste `https://localhost:5185` mais SPA sert HTTP sur :5173 → `AADSTS900971`
- ❌ Cert auto-signé non accepté → `TypeError: Failed to fetch` (CORS apparent mais c'est en fait TLS refusé silencieusement)
- ❌ Mixed content : SPA HTTPS + backend HTTP → navigateur bloque

---

#### 5.2.7.9 CORS — config OBLIGATOIRE côté backend (dev + prod)

Tout SPA hébergé sur un origin différent du backend (cas standard en dev :
`http://localhost:5173` ↔ `http://localhost:8080`) requiert une config CORS
explicite côté backend, sinon **toute requête `fetch` échoue silencieusement
avec `TypeError: Failed to fetch`** dans le navigateur (la pré-flight OPTIONS
ne reçoit pas les headers `Access-Control-Allow-*`).

**Symptômes** :
- Page front blanche avec error boundary "Backend indisponible"
- DevTools Console : `Access to fetch at 'http://localhost:8080/auth/config'
  from origin 'http://localhost:5173' has been blocked by CORS policy`
- Backend logs : aucun signe (la pré-flight OPTIONS n'arrive même pas)

**Fix obligatoire — bean `CorsConfigurationSource` côté Spring Security** :

```kotlin
// workspace/output/src/{BackendName}/src/main/kotlin/.../config/CorsConfig.kt
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
        return UrlBasedCorsConfigurationSource().apply {
            registerCorsConfiguration("/**", config)
        }
    }
}
```

**ET** brancher `cors()` dans `SecurityFilterChain` (sinon le bean est ignoré) :

```kotlin
http.cors { } // active la CorsConfigurationSource bean
   .csrf { it.disable() }
   ...
```

**Default des origins** : `http://localhost:5173` (Vite dev) + `http://localhost:4173`
(Vite preview). En prod : variable d'environnement `APP_CORS_ALLOWED_ORIGINS`
(CSV) configurée par l'opérateur.

**Pour les stacks non-Kotlin** :
| Stack backend | Pattern CORS |
|---|---|
| `dotnet-minimalapi` | `services.AddCors(o => o.AddDefaultPolicy(b => b.WithOrigins(...).AllowAnyMethod().AllowAnyHeader().AllowCredentials()))` + `app.UseCors()` |
| `python-fastapi` | `app.add_middleware(CORSMiddleware, allow_origins=[...], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` |
| `node-express` | `app.use(cors({ origin: [...], credentials: true }))` |

**Alternative dev only — Vite proxy** (évite CORS en redirigeant /api et /auth
vers le backend depuis le même origin) :

```ts
// vite.config.ts
export default defineConfig({
  server: { proxy: {
    "/api": "http://localhost:8080",
    "/auth": "http://localhost:8080",
  }}
})
```

À utiliser **uniquement en dev** ; prod requiert CORS backend ou même-origin.

**Anti-pattern** : oublier `cors()` dans `SecurityFilterChain` → bean
`CorsConfigurationSource` présent mais ignoré → comportement aléatoire.

---

#### 5.2.7.8 Anti-récap (à grep en self-check dev-frontend)

- ❌ `import.meta.env.VITE_AZ_*` dans le code applicatif
- ❌ `new PublicClientApplication({ auth: { clientId: "<litéral>" }})` (hardcode)
- ❌ Routes protégées définies sans guard dans `__root.tsx`
- ❌ `MainLayout` enveloppant `/login`
- ❌ Token Bearer attendu par `httpClient` mais jamais écrit en sessionStorage par `LoginPage`
- ❌ Pas de route `/` index → "Not Found" runtime

---

### 5.3 Application monolithique

- Authentification via OpenID Connect (redirect)
- Session geree serveur (cookie securise)
- Token jamais expose au navigateur

Comportements :

- non authentifie → redirect login
- authentifie sans droit → 403 (pas de loop)

---

## 6. Comportements attendus

- utilisateur non authentifie :
  - aucun acces
  - redirection vers Azure AD

- utilisateur authentifie :
  - acces selon droits
  - session maintenue (silent refresh si SPA)

- utilisateur non autorise :
  - message acces refuse (403)
  - jamais redirige vers login

---

## 7. Symptomes courants

- acces refuse :
  - groupe manquant
  - roles absents

- erreur auth :
  - mauvaise authority
  - audience incorrecte
  - mauvaise config env

- boucle login :
  - mauvaise gestion redirect URI
  - etat auth mal gere

- API refuse :
  - token absent
  - token non attache automatiquement
  - scope invalide

- groupes absents :
  - token trop volumineux → utiliser Graph

---

## 8. Interdits projet

- valeurs Azure AD hardcodees
- ClientSecret cote frontend
- validation JWT manuelle
- stockage manuel du token
- parsing manuel du JWT
- mapping groupes en dur
- logique securite uniquement frontend
- appel API sans token
- duplication logique auth
- login interne custom
- stockage credentials utilisateur

---

## 9. Hors scope

- MFA (gere par Azure AD)
- federation externe
- gestion utilisateurs
- reset password
- audit logs
- gestion avancee des groupes volumineux (Graph avancé)