# Tech FEAT: auth-local

Status: Bench-validated
Validation: 🟢 bench (bench 2026-06-05 runtime PASS sur combos C3/C4/C5/C6/C10/C11/C12/C13 — JWT HS256 + bcrypt natif ; pipeline /sdd-full end-to-end pending v7.1)
Support: 🟢 Supporté best-effort (SLA Tier 2, cf. SLA.md §1.1) — pas de garantie idempotence /sdd-full. Promu de experimental le 2026-06-07 (audit Sprint 2 CRIT-11 closure).
Tech FEAT ID: tech-auth-local
Scope: authentification et autorisation locale via login / password + JWT — independant de toute stack ou langage. Chaque implementation (backend, SPA, monolithe, mobile) doit appliquer ces regles selon sa technologie.

---

## 1. Principe universel

- Authentification via identifiant utilisateur (email ou login) + mot de passe.
- Les comptes utilisateurs sont stockes dans une base de donnees applicative.
- Les mots de passe sont **toujours stockes sous forme de hash securise**.
- Aucun mot de passe en clair n’est jamais stocke, transmis ou logge.
- Authentification reussie → generation d’un **token JWT signe**.
- Le JWT est utilise comme **source unique de verite** pour :
  - l’identite
  - les informations utilisateur
  - les droits (roles, permissions si presentes)

- Utilisation d’un mecanisme standard :
  - Backend : generation et validation JWT
  - Frontend / client : stockage securise + envoi du token
  - Monolithe : session serveur ou JWT interne

- **Toutes les configurations proviennent du bloc `## Active Auth Specs`
  de `workspace/input/stack/stack.md`** (renseigne par le Tech Lead),
  propage par l'agent `arch` Phase A — STEP 4.5 vers les fichiers de
  configuration applicatifs natifs du framework backend (depuis
  2026-05-14) : `appsettings.json` section `Jwt` (.NET),
  `application.yml` section `auth.jwt` (Spring), `config/default.json`
  section `jwt` (Node), `app/config.py` classe `JwtSettings` (Python).
  Cf. §2 ci-dessous.
- Aucune logique dependante d’un framework specifique ne doit etre supposee.

---

## 2. Variables de configuration

**Modele depuis 2026-05-14** : les valeurs sont declarees dans le bloc
`## Active Auth Specs` de `workspace/input/stack/stack.md` (renseigne
par le Tech Lead). L'agent `arch` Phase A — STEP 4.5 les propage dans
les fichiers de configuration natifs du framework backend (et lit le
fichier en runtime pour validation). L'application **n'utilise plus
de variables d'environnement** ; elle lit son `IConfiguration` /
`application.yml` / `config/default.json` / `app/config.py` standard.

L'application doit s'arreter au boot si une cle est absente dans le
fichier de config (fail-fast classique du framework).

### Cles de configuration obligatoires (sous `## Active Auth Specs`)

- AUTH_JWT_SECRET : cle secrete utilisee pour signer les tokens JWT
  (HMAC-SHA256 minimum, **256 bits = 32 caracteres min**)
- AUTH_JWT_ISSUER : emetteur du token (claim `iss`)
- AUTH_JWT_AUDIENCE : audience du token (claim `aud`)
- AUTH_JWT_EXPIRATION : duree de validite (en **minutes**, entier
  positif ; ex. `4` = 4 minutes, `60` = 1 heure). Une valeur unique
  par stack auth — la duree par defaut s'applique a tous les tokens
  emis sauf override explicite documente dans le code.

### Cles recommandees (sous `## Active Auth Specs`, optionnelles)

- AUTH_HASH_ALGO : algorithme de hash (defaut : `argon2id`)
- AUTH_HASH_ITERATIONS : facteur de cout (selon algo)
- AUTH_HASH_MEMORY : memoire (argon2, en KB)
- AUTH_HASH_PARALLELISM : parallelisme (argon2)
- AUTH_SALT_LENGTH : taille du sel (octets)

### Exemple de bloc `## Active Auth Specs` (auth-local)

```markdown
## Active Auth Specs
 - .claude/stacks/auth/auth-local.md
 - AUTH_JWT_AUDIENCE:NounouJob
 - AUTH_JWT_EXPIRATION:60
 - AUTH_JWT_ISSUER:NounouJobBack
 - AUTH_JWT_SECRET:NounouJobSuperSecretKey@2024!XYZ789AbcDef012345678
```

### Contraintes

- aucune valeur ne doit etre hardcodee dans le code applicatif
- toutes proviennent du bloc `## Active Auth Specs` de stack.md
- valeurs differentes par environnement (dev/test/prod) : le Tech
  Lead change `stack.md` puis relance `/arch-init` (idempotent)
- aucun `.env` projet, aucun `Environment.GetEnvironmentVariable`,
  aucun `System.getenv`, aucun `process.env`, aucun `os.environ`
  cote code applicatif ni cote arch (cf. `agents/arch.md §4.5.4`)

### 2.1 Mapping AUTH_JWT_* → fichier de configuration par stack backend

L'agent `arch` Phase A — STEP 4.5 ecrit ces sections dans le fichier
de config natif du framework. Le code applicatif lit **exclusivement**
via l'API standard du framework (`IConfiguration`, `@Value`, `config`
npm, pydantic-settings).

| Stack backend         | Fichier cible                                                            | Section / classe       |
|-----------------------|--------------------------------------------------------------------------|------------------------|
| `dotnet-minimalapi`   | `workspace/output/src/{BackendName}/appsettings.json`                    | `Jwt` (JSON object)    |
| `kotlin-spring-boot`  | `workspace/output/src/{BackendName}/src/main/resources/application.yml`  | `auth.jwt` (YAML)      |
| `node-express`        | `workspace/output/src/{BackendName}/config/default.json`                 | `jwt` (JSON object)    |
| `python-fastapi`      | `workspace/output/src/{BackendName}/app/config.py`                       | `JwtSettings` (pydantic)|

#### A. `dotnet-minimalapi` → `appsettings.json` section `Jwt`

```json
{
  "Jwt": {
    "Secret": "{AUTH_JWT_SECRET}",
    "Issuer": "{AUTH_JWT_ISSUER}",
    "Audience": "{AUTH_JWT_AUDIENCE}",
    "ExpirationMinutes": {AUTH_JWT_EXPIRATION}
  }
}
```

Le code lit via `IConfiguration` :
```csharp
var jwtSection = builder.Configuration.GetSection("Jwt");
var secret    = jwtSection["Secret"]    ?? throw new InvalidOperationException("Jwt:Secret missing in appsettings.json");
var issuer    = jwtSection["Issuer"]    ?? throw new InvalidOperationException("Jwt:Issuer missing");
var audience  = jwtSection["Audience"]  ?? throw new InvalidOperationException("Jwt:Audience missing");
var expMin    = jwtSection.GetValue<int>("ExpirationMinutes");

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options => {
        options.TokenValidationParameters = new TokenValidationParameters {
            ValidateIssuer = true, ValidIssuer = issuer,
            ValidateAudience = true, ValidAudience = audience,
            ValidateLifetime = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret)),
            ValidateIssuerSigningKey = true,
        };
    });
```

#### B. `kotlin-spring-boot` → `application.yml` section `auth.jwt`

```yaml
auth:
  jwt:
    secret: "{AUTH_JWT_SECRET}"
    issuer: "{AUTH_JWT_ISSUER}"
    audience: "{AUTH_JWT_AUDIENCE}"
    expiration-minutes: {AUTH_JWT_EXPIRATION}
```

Le code lit via `@ConfigurationProperties(prefix = "auth.jwt")` ou
`@Value("\${auth.jwt.secret}")`.

#### C. `node-express` → `config/default.json` section `jwt`

```json
{
  "jwt": {
    "secret": "{AUTH_JWT_SECRET}",
    "issuer": "{AUTH_JWT_ISSUER}",
    "audience": "{AUTH_JWT_AUDIENCE}",
    "expirationMinutes": {AUTH_JWT_EXPIRATION}
  }
}
```

Le code lit via `config.get("jwt.secret")` (package `config` npm,
declare dans `node-express.libs.json`).

#### D. `python-fastapi` → `app/config.py` classe `JwtSettings`

```python
from pydantic_settings import BaseSettings

class JwtSettings(BaseSettings):
    secret: str = "{AUTH_JWT_SECRET}"
    issuer: str = "{AUTH_JWT_ISSUER}"
    audience: str = "{AUTH_JWT_AUDIENCE}"
    expiration_minutes: int = {AUTH_JWT_EXPIRATION}

jwt_settings = JwtSettings()
```

Le code importe `from app.config import jwt_settings` et utilise
`jwt_settings.secret`, etc.

### 2.2 Cote frontend (SPA) — AUTH_JWT_* NE SONT PAS exposes

**Securite critique** : `AUTH_JWT_SECRET` est une **cle de signature
serveur** ; elle ne doit JAMAIS apparaitre dans :
- un fichier de config frontend public (`VITE_*`, `REACT_APP_*`, `NG_*`
  ou equivalent compile-time) contenant une cle `AUTH_JWT_*`
- un fichier `appsettings.json` cote Blazor WASM (lu cote client)
- un bundle JS livre au navigateur
- une reponse d'endpoint `/auth/config` ou similaire

Le frontend (SPA) :
- envoie `{login, password}` a `POST /api/auth/login`
- recoit le JWT (cookie `httpOnly` recommande, ou body JSON selon profil
  §7.2.b)
- attache le token aux requetes suivantes (cookie automatique OU
  `Authorization: Bearer <token>` selon strategie de stockage)
- **ne valide jamais la signature** du JWT cote client (lecture passive
  du `exp` via `jwt-decode` autorisee pour pre-refresh)

Le frontend n'a donc **aucun besoin** des cles `AUTH_JWT_*`. La seule
configuration publique attendue est l'URL backend (`VITE_API_BASE_URL`
ou equivalent), produite selon le stack frontend actif §5 et jamais
confondue avec les secrets `stack.md`.

---

## 3. Hash des mots de passe (CRITIQUE — cross-langage)

### 3.1 Algorithmes autorises (ordre de preference)

- argon2id (recommande)
- bcrypt
- pbkdf2 (HMAC-SHA256 minimum)

### 3.2 Format du hash (OBLIGATOIRE)

Le hash stocke doit etre auto-descriptif et contenir :

- algorithme
- parametres (cout, iterations, etc.)
- sel (salt)
- hash final

Format standard recommande (type PHC string) :

$argon2id$v=19$m=65536,t=3,p=2$<salt>$<hash>

- $argon2id → algorithme utilisé
- v=19 → version d’Argon2
- m=65536 → mémoire (64 MB)
- t=3 → nombre d’itérations
- p=2 → parallélisme
- <salt> → sel (aléatoire, encodé en base64)
- <hash> → résultat du hash (base64)

Ce format garantit la portabilite entre :

- .NET
- Java (Spring)
- Node.js
- Python
- Go
- autres

---

### 3.3 Regles universelles

- chaque mot de passe a un salt unique
- le salt est genere aleatoirement
- le hash inclut le salt (pas stocke a part sauf si format compatible)
- comparaison via fonction securisee (constant-time)

### Interdits

- SHA256 seul
- MD5 / SHA1
- hash sans salt
- comparaison simple (==)

---

### 3.4 Verification du mot de passe

- utiliser la librairie standard du langage
- ne jamais reimplementer l’algo
- parser automatiquement le format du hash
- comparer via fonction fournie par la lib

---

## 4. Validation du token (universel)

Tout composant recevant un token doit verifier :

- signature valide (cle lue dans `Jwt:Secret` / `auth.jwt.secret` /
  `jwt.secret` / `jwt_settings.secret` selon stack — cf. §2.1)
- issuer valide (claim `iss` == `Jwt:Issuer`)
- audience valide (claim `aud` == `Jwt:Audience`)
- expiration valide (claim `exp` non depasse)
- structure JWT correcte

Regles :

- toute requete sans token → 401
- token invalide → 401
- token valide sans droits → 403

Logs (dev) :

- generation token
- validation token
- echec auth
- acces refuse

---

## 5. Authentification utilisateur

### 5.1 Source des identifiants

Base de donnees applicative uniquement :

- email ou login
- password_hash

---

### 5.2 Processus de login

1. recuperer utilisateur par login/email
2. verifier existence
3. verifier mot de passe via hash
4. si valide → generer JWT
5. sinon → erreur generique (ne pas reveler si user existe)

---

### 5.3 Generation du token

Le JWT contient :

- sub : userId
- login/email
- roles (si existants)
- iat / exp
- issuer / audience

Contraintes :

- aucune donnee sensible (mot de passe, hash)
- expiration obligatoire (lue depuis `Jwt:ExpirationMinutes` /
  `auth.jwt.expiration-minutes` / `jwt.expirationMinutes` /
  `jwt_settings.expiration_minutes` selon stack)
- signature via la cle lue dans la config (jamais hardcodee, jamais
  lue depuis `Environment.GetEnvironmentVariable`/`process.env`/etc.)

---

## 6. Autorisation

### 6.1 Source des droits

- roles stockes en base
- permissions associees

---

### 6.2 Mapping

- aucun mapping en dur
- configurable dynamiquement
- resolu au login ou via service

Si aucun role :

- mode degrade (authentifie uniquement)

---

### 6.3 Enforcement

- backend = source de verite
- frontend = UX uniquement
- verification serveur obligatoire

---

## 7. Integration par type d’application

### 7.1 Backend (API)

- endpoint /auth/login :
  - input : login + password
  - output : JWT

- middleware obligatoire pour :
  - verification JWT
  - injection user context

- endpoints proteges :
  - exigent JWT valide

---

### 7.2 Frontend / client (SPA, mobile)

- formulaire login obligatoire
- appel HTTPS vers backend

#### 7.2.a Layout des pages d'authentification (OBLIGATOIRE)

Toutes les pages d'authentification suivantes utilisent un **layout
dédié, vide, totalement découplé du layout principal de l'application** :

- `/login` (connexion)
- `/register` (création de compte)
- `/forgot-password` (mot de passe oublié)
- `/reset-password` (réinitialisation)
- `/login-callback`, `/logout-callback` (si flow OIDC ou retour SSO)
- toute page exposée à un utilisateur **non authentifié**

**Contraintes** :

- **JAMAIS** de rendu de menu principal, sidebar, navigation applicative,
  user-menu, breadcrumb, ou tout composant qui suppose un utilisateur
  connecté
- Le layout d'auth est un **fichier dédié** (ex. Blazor : `AuthLayout.razor` ;
  React : `AuthLayout.tsx` ; Vue : `AuthLayout.vue` ; Angular : `auth-layout.component.ts`),
  pas une variante conditionnelle (`@if (isAuthPage) { ... }`) du layout principal
- Le layout d'auth est **par défaut entièrement vide** (uniquement
  `<main>{children}</main>` ou équivalent + reset CSS minimal). Le PO/UX
  décide explicitement par US ultérieure d'ajouter header/footer/branding —
  jamais par dérive du dev
- Le routing déclare explicitement quel layout chaque page utilise.
  Anti-pattern : laisser le layout par défaut s'appliquer aux pages d'auth
  par oubli de configuration

**Pourquoi cette règle** : un menu principal sur une page de login
révèle des entrées de navigation à un utilisateur non authentifié
(information leak), peut afficher des données utilisateur stale, peut
référencer l'utilisateur courant côté JS (crash si non connecté), et
brouille l'UX (l'utilisateur croit être déjà connecté). Un layout vide
est un **invariant de sécurité**, pas une préférence UX.

**Mapping par stack frontend** :

| Stack frontend       | Layout d'auth attendu | Routing |
|----------------------|----------------------|---------|
| `blazor-webassembly` | `Layouts/AuthLayout.razor` (vide) | `@layout AuthLayout` en tête de page |
| `react`              | `src/layouts/AuthLayout.tsx`     | `<Route element={<AuthLayout/>}><Route .../></Route>` |
| `vue`                | `src/layouts/AuthLayout.vue`     | `meta: { layout: 'auth' }` ou route nested |
| `angular`            | `src/app/layouts/auth-layout/`   | `loadChildren` ou route group |

#### 7.2.b Stockage du token JWT (durci par profil)

Stockage selon le **profil d'exécution** déclaré (`development` /
`staging` / `production`) :

| Profil      | Stockage autorisé | Stockage interdit |
|-------------|-------------------|-------------------|
| development | memory, sessionStorage (avec WARNING), cookie httpOnly | localStorage en clair |
| staging     | memory, cookie httpOnly+Secure+SameSite=Strict | localStorage, sessionStorage en clair |
| **production** | **cookie httpOnly+Secure+SameSite=Strict UNIQUEMENT** | **localStorage / sessionStorage interdits absolument (XSS exfiltration)** |

Le frontend détecte le profil via `import.meta.env.MODE` (Vite),
`process.env.NODE_ENV` (CRA/Next), `environment.production` (Angular),
ou équivalent. Le code de stockage **doit branche-or** sur ce flag et
faire échouer le build (ou émettre un ERROR runtime) si une stratégie
JS storage est sélectionnée en production.

Anti-pattern strict (déclenche `[BUILD_BLOCKING]` côté QA si détecté) :
```js
// INTERDIT en prod — XSS exfiltration en 1 ligne
localStorage.setItem('jwt', token);
sessionStorage.setItem('jwt', token);
```

Pattern recommandé : le backend dépose le JWT dans un cookie
`HttpOnly; Secure; SameSite=Strict; Path=/` à la réponse `/auth/login`.
Le client ne manipule jamais le token directement ; chaque appel API
le porte automatiquement via le cookie.

#### 7.2.c Règles transverses (toutes plateformes)

- aucun stockage brut non protégé
- aucun log du token (`console.log(token)`, `Console.WriteLine(jwt)`,
  `logger.info(token)` — tous interdits)
- ajout automatique via interceptor HTTP (cf. conventions de chaque
  stack frontend, anti-pattern `[FRONTEND_BACKEND_CONTRACT_GAP]`)
- aucun decodage manuel du JWT côté client (utiliser une lib comme
  `jwt-decode`, et UNIQUEMENT pour lire `exp` afin de pré-rafraîchir —
  jamais pour faire confiance au contenu, qui n'est pas vérifié côté client)

---

### 7.3 Application monolithique

- login via formulaire interne
- session serveur OU JWT interne

Comportements :

- non authentifie → redirect login
- authentifie sans droits → 403

---

## 8. Comportements attendus

- utilisateur non authentifie :
  - aucun acces
  - redirect login

- utilisateur authentifie :
  - recoit JWT
  - acces selon droits

- utilisateur non autorise :
  - 403
  - pas de redirect login

- token expire :
  - 401
  - re-auth obligatoire

---

## 9. Symptomes courants

- login refuse :
  - mauvais password
  - hash incompatible

- token invalide :
  - secret incorrect
  - mauvaise config issuer/audience

- acces refuse :
  - roles insuffisants

- API refuse :
  - token absent
  - token non attache

---

## 10. Interdits projet

- mot de passe en clair
- hash faible ou custom
- JWT sans expiration
- secret en dur
- stockage non securise du token
- logique securite frontend uniquement
- duplication auth
- exposition hash/password
- absence validation serveur

---

## 11. Hors scope

- MFA
- federation externe
- SSO
- rotation automatique des cles JWT
- audit avancé
- gestion sessions distribuees
- RBAC dynamique avancé
