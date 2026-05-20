# arch — Phase A, STEP 4.5 : Propagation `## Active Database` + `## Active Auth Specs` vers configs applicatives

> **Sous-doc extrait** de `agents/arch.md` STEP 4.5 (v7.0.0 trim, 2026-05-20)
> pour alléger le prompt root de l'agent. Référencé via `Read @.claude/docs/arch/phase-a-config-propagation.md`.

**Bloquant avant STEP 5/6** : sans configs valides, build backend
échoue (Spring eager init datasource, .NET appsettings load au boot).

Étape **idempotente** : Edit (ou create) le fichier config natif,
injectant `db_config` + `auth_config` (STEP 2.ter).

## 4.5.1 Mapping stack → fichier de configuration

| Stack backend | Fichier cible | Format |
|---|---|---|
| `dotnet-minimalapi`  | `workspace/output/src/{BackendName}/appsettings.json` | JSON |
| `kotlin-spring-boot` | `workspace/output/src/{BackendName}/src/main/resources/application.yml` | YAML |
| `node-express`       | `workspace/output/src/{BackendName}/config/default.json` | JSON |
| `python-fastapi`     | `workspace/output/src/{BackendName}/app/config.py` | Python (pydantic-settings) |

Création si absent (`mkdir -p` implicite). Re-run : Edit narrow sur
sections owned uniquement :
- DB : `ConnectionStrings.Default`, `Database`, `Db`, `db`, `spring.datasource`, `spring.jpa`
- Auth `azure-ad` : `AzureAd`, `azure.ad`, `azure`
- Auth `auth-local` : `Jwt`, `auth.jwt`, `jwt`, classe `JwtSettings`
- **CORS** (depuis v6.10.4, cf. §4.5.6) : `Cors`, `cors`, `app.cors`, classe `CorsSettings`

Autres sections (logging custom, beans custom hors policy CORS) préservées.
Switch profil auth → supprimer ancien + écrire nouveau (évite double chargement
= crash Spring/.NET).

## 4.5.2 Structure canonique par stack

Sections requises (DB toujours présente ; auth présente UNIQUEMENT si
`auth_profile != null` ; profils `azure-ad`/`auth-local` mutuellement
exclusifs cf. STEP 2.ter.3).

| Stack | DB | Auth `azure-ad` | Auth `auth-local` | Détail |
|---|---|---|---|---|
| `dotnet-minimalapi` | `ConnectionStrings.Default` + `Database.Type` | `AzureAd.{Instance,TenantId,ClientId,Domain,CallbackPath,ValidAudiences[]}` | `Jwt.{Secret,Issuer,Audience,ExpirationMinutes}` | `dotnet-minimalapi.md §5.1 §8.2` |
| `kotlin-spring-boot` | `spring.datasource.{url,username,password,driver-class-name}` + `spring.jpa.properties.hibernate.dialect` | `azure.ad.{tenant-id,client-id,domain,audiences,backend-callback-path,frontend-callback-path}` (+ optionnels `frontend-client-id`, `backend-client-id`) | `auth.jwt.{secret,issuer,audience,expiration-minutes}` | `kotlin-spring-boot.md §5.1 §8.2` |
| `node-express` | `db.{type,host,port,name,user,password}` | `azure.ad.{tenantId,clientId,domain,audiences[],backendCallbackPath,frontendCallbackPath}` | `jwt.{secret,issuer,audience,expirationMinutes}` | `node-express.md §5.1 §8.2` |
| `python-fastapi` | classe `DBSettings(BaseSettings)` champs `type,host,port,name,user,password` | classe `AzureADSettings` champs `tenant_id,client_id,domain,audiences[],backend_callback_path,frontend_callback_path` | classe `JwtSettings` champs `secret,issuer,audience,expiration_minutes` | `python-fastapi.md §5.1 §8.2` |

**Substitutions** :
- Valeurs DB depuis `db_config` (STEP 2.ter). Connection strings /
  URLs JDBC composées selon `DatabaseType` cf. §8.2 du stack.
- Valeurs auth depuis `auth_config` selon `auth_profile`.
- `AZ_AUDIENCES` : split virgule + strip quotes/espaces (liste).
- `azure.ad.frontend-client-id`/`backend-client-id` (Spring) : fallback
  `auth_config.AZ_CLIENTID` si non fournis.
- Sections logging/JPA/préservées si fichier déjà présent.

**Templates détaillés** : chaque stack documente le format complet en
`§5.1` (config natif applicatif) et `§8.2` (composition connection
string). Arch lit le pattern, génère le fichier, n'invente rien.

## 4.5.3 Idempotence (re-run)

- Fichier cible existe : Read, parser format natif (JSON / YAML /
  Python AST), Edit narrow sections owned (cf. §4.5.1). Autres préservées.
- Fichier cible absent : Create avec contenu canonique §4.5.2 (valeurs
  par défaut framework pour Logging, JPA, etc.).
- Aucun secret loggé. Hash sha256-8 du fichier noté dans récap STEP 13
  (optionnel).

## 4.5.4 Anti-derive (intra-step)

- ❌ Lecture `Environment.GetEnvironmentVariable`, `System.getenv`,
  `process.env`, `os.environ` côté arch — SSOT = stack.md.
- ❌ Écriture `.env` projet (sauf dotenv-natif explicite — pas en v6.1.3).
- ❌ Écriture DB/Auth dans autre fichier que cible canonique §4.5.1
  (pas de duplication dans `Program.cs`, `SecurityConfig.kt`, etc.).
- ✅ Connection string Phase B (STEP 8) : RAM uniquement, jamais
  réécrite dans config (Spring/.NET/Node/Python reconstruisent depuis
  leurs propriétés natives).

## 4.5.5 Validation post-écriture

Vérifier syntaxe :
- JSON → `Test-Json` (PowerShell) ou `json.loads`
- YAML → `python -c "import yaml; yaml.safe_load(open(sys.argv[1]))"`
- Python → `python -c "import ast; ast.parse(open(sys.argv[1]).read())"`

Échec → ERROR `[STACK_MALFORMED]` + STOP avant STEP 5.

## 4.5.6 Propagation CORS origins (depuis v6.10.4)

**But** : injecter automatiquement l'origin du frontend dev dans la config
backend, en accord avec `.claude/rules/library-and-stack.md` (allowlist explicite, jamais
de wildcard).

**Skip silencieux** si `appType ≠ back-front` OU `frontendKind ≠ web`
(fullstack/mobile/backend-only → pas de SPA cross-origin à autoriser).

### Matrice frontend stack → port dev par défaut

| Frontend stack | Port | Origin par défaut |
|---|---:|---|
| `frontend/react`              | 5173 | `http://localhost:5173` (Vite) |
| `frontend/vue`                | 5173 | `http://localhost:5173` (Vite) |
| `frontend/angular`            | 4200 | `http://localhost:4200` |
| `frontend/blazor-webassembly` | 5097 | `http://localhost:5097` (varie scaffold) |
| `mobiles/*`                   | —    | (skip) |
| `fullstack/*`                 | —    | (skip — même origin que backend) |

**Override** : si `Cors:AllowedOrigins` (ou alias `CorsAllowedOrigins`) est
explicitement présent dans `## Project Config` de `stack.md`, arch préserve la
valeur utilisateur (**User-set wins**) sans la modifier.

### Cible par stack backend

| Backend | Fichier | Clé / forme | Type valeur |
|---|---|---|---|
| `dotnet-minimalapi` | `appsettings.Development.json` | `Cors:AllowedOrigins` | string CSV |
| `kotlin-spring-boot` | `application.yml` | `app.cors.allowed-origins` | string CSV |
| `node-express` | `config/default.json` | `cors.allowedOrigins` | array |
| `python-fastapi` | `app/config.py` | classe `CorsSettings.allowed_origins` | `list[str]` (default factory) |

### Exemples canoniques post-injection

**.NET `appsettings.Development.json`** (DEV uniquement, `appsettings.json` prod-clean) :
```json
{ "Cors": { "AllowedOrigins": "http://localhost:5173" } }
```

**Spring `application.yml`** :
```yaml
app:
  cors:
    allowed-origins: http://localhost:5173
```

**Node `config/default.json`** :
```json
{ "cors": { "allowedOrigins": ["http://localhost:5173"], "allowCredentials": true } }
```

**FastAPI `app/config.py`** :
```python
from pydantic import Field
from pydantic_settings import BaseSettings

class CorsSettings(BaseSettings):
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    allow_credentials: bool = True
    model_config = {"env_prefix": "CORS_"}
```

### Algorithme

1. Détection du frontend stack actif depuis `## Active Tech Specs` (parsé STEP 2).
   Si `frontend/*` absent ou `mobiles/*` ou `fullstack/*` → SKIP silencieux.
2. Lookup port dev dans la matrice.
3. Lecture `## Project Config` : si `Cors:AllowedOrigins` présent → User-set wins ;
   sinon → défaut matrice.
4. Edit narrow du fichier config backend (§4.5.1) pour injecter la clé.
   Préserver autres sections (DB, Auth, logging).
5. Re-run idempotent : valeur identique → no-op.

### Anti-derive

- ❌ Jamais d'injection `*` / `AllowAnyOrigin()` même au scaffold (cf.
  `rules/library-and-stack.md §4`).
- ❌ Jamais d'écriture des origins **prod** côté arch — uniquement dev locales.
  Override prod = responsabilité ops via env var (`Cors__AllowedOrigins`,
  `CORS_ALLOWED_ORIGINS`, `APP_CORS_ALLOWED_ORIGINS`).
- ❌ Jamais de scan `launchSettings.json` côté frontend pour deviner un port
  custom. Si non-standard, Tech Lead pose `Cors:AllowedOrigins` explicitement
  dans `stack.md`.

### Validation post-injection

Identique §4.5.5 (syntaxe JSON / YAML / Python), plus :
- Grep défensif post-write : si la valeur contient `*` ou `AllowAnyOrigin` →
  ERROR `[STACK_MALFORMED]` + STOP.
