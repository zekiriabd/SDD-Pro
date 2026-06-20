# Tech FEAT: expressapi (backend)

> §2.4 (Librairies) régénérée depuis `node-express.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id node-express`).

Status: Experimental
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCBackNode :44329, Express 4 + TypeScript strict (`noUncheckedIndexedAccess`) + ESM `"type":"module"` + Pino + Zod inline + Swagger §1.6 obligatoire + helmet/cors/compression/rate-limit, ~320 LOC code applicatif, **POST 5+5 latence 47ms (2e plus rapide du bench)**, `/api-docs` Swagger UI + OpenAPI 3.0.3, 400 ProblemDetail Zod, 16/16 curl cross-origin 4 SPA OK, AC-1/2/3/4 🟢. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-expressapi
Scope: backend uniquement (API, logique metier, persistance)

---

# 1. Architecture

> **Pattern d'architecture** : ce stack suit l'**architecture canonique** définie dans
> `.claude/stacks/archi/{ArchiPattern}.md` (défaut `MVC` si `## Active Architecture Pattern`
> absent du `stack.md`). Section §1 ci-dessous ne décrit QUE les overrides Node/Express-specific.

## 1.1 Pattern applicatif (Node/Express idioms)

Pour `ArchiPattern: MVC` (défaut), suit `archi/mvc.md` avec idioms Express :
- Routes via plugin Fastify-like (`registerXxxRoutes(fastify)`) ou Express `router.get()` — pas de classe Controller, fonction handler
- Service = objet ES module avec méthodes async exportées (`export const usersService = { getList, ... }`)
- Repository = wrapper autour de `PrismaClient` ou ORM choisi
- Mapper = plain functions (`mapEntityToOutput(entity): Output`)
- DTO = types TypeScript dans `{LibName}/inputs|outputs|models/` (cf. §1.3) + schemas Zod pour validation runtime
- `ApiResponse<T>` wrapper standard (status, data, queryTime, mappingTime, errors) défini dans `{LibName}/models/ApiResponse.ts`

Pour `ArchiPattern: DDD` → voir `archi/ddd.md` (Aggregates + UseCases).
Pour `ArchiPattern: microservice` → voir `archi/microservice.md` (Polly equivalent + comm patterns).

## 1.3 Mapping couche → répertoire (override Node)

| Couche canonique (archi/mvc.md §3) | Path Node-specific |
|---|---|
| Route / Endpoint | `workspace/output/src/{BackendName}/routes/` (1 fichier par domain, `{domain}.routes.ts`) |
| Controller | `workspace/output/src/{BackendName}/controllers/` |
| Service Interface | `workspace/output/src/{BackendName}/services/interfaces/` (TypeScript `interface`) |
| Service Implementation | `workspace/output/src/{BackendName}/services/` |
| Repository | `workspace/output/src/{BackendName}/repositories/` |
| Mapper | `workspace/output/src/{BackendName}/mappers/` |
| Entity | `workspace/output/src/{BackendName}/entities/` (Prisma model dans `prisma/schema.prisma`) |
| Database | `workspace/output/src/{BackendName}/database/` (Prisma client singleton) |
| Middleware | `workspace/output/src/{BackendName}/middleware/` |
| Logger | `workspace/output/src/{BackendName}/logger/` (Pino setup) |
| Swagger | `workspace/output/src/{BackendName}/swagger/` (cf. §1.6, Express-specific) |
| Input/Output/Model DTO | `workspace/output/src/{LibName}/{inputs,outputs,models}/` |
| App / Server | `workspace/output/src/{BackendName}/{app.ts,server.ts}` |
| Project (API) | `workspace/output/src/{BackendName}/package.json` |
| Project (Lib) | `workspace/output/src/{LibName}/package.json` |

## 1.4 Override principes (Node-specific)

Hérités de `archi/mvc.md §4`. **Ajouts** Node :
- TypeScript strict (`"strict": true, "noUncheckedIndexedAccess": true` dans `tsconfig.json`)
- ESM (`"type": "module"`, imports avec extension `.js`)
- Pas de `require()` — `import` uniquement
- Pino structuré obligatoire (pas de `console.log` même en dev)
- Schemas Zod **inline** avec les Input DTOs (`z.infer<typeof Schema>` = type Input DTO)
- **Documentation Swagger / OpenAPI obligatoire** (Express idiom — cf. §1.6) : `/api-docs` UI + `/api-docs.json` spec

---

## 1.5 Couches persistantes

Patterns reconnus comme persistants (déclenche `DB_REQUIRED` dans le pipeline) :

- `Entity`, `Entities`
- `Repository`, `Repositories`
- `Migration`, `Migrations`

Tout autre layer ne déclenche pas le scan DB.

---

## 1.6 Swagger / OpenAPI (obligatoire — auto-câblé)

Tout projet généré sur ce stack DOIT inclure la documentation Swagger sans demande explicite. Le Backend Agent l'ajoute automatiquement dans la première task qui crée `app.ts`.

### Fichiers obligatoires
- `workspace/output/src/{BackendName}/swagger/swaggerConfig.ts` — exporte `swaggerSpec` (objet OpenAPI 3.0.3)
  - `info.title` = `{AppName} API` (ou `{BackendName} API`)
  - `info.version` = `1.0.0`
  - `components.securitySchemes.bearerAuth` = `{ type: 'http', scheme: 'bearer', bearerFormat: 'JWT' }` (si auth-local active)
  - `components.schemas` = inputs/outputs depuis `workspace/output/src/{LibName}` (mappés depuis les DTOs Zod)
  - `paths` = endpoints documentés enrichis à chaque task qui ajoute un controller (chaque task déclare `swaggerConfig.ts` dans son `Files: augment` avec `preserves: [swaggerSpec]` + `adds: [path:/api/v1/...]`)

### app.ts mount obligatoire
```ts
import swaggerUi from 'swagger-ui-express';
import { swaggerSpec } from './swagger/swaggerConfig';

app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec, { explorer: true }));
app.get('/api-docs.json', (_req, res) => {
  res.setHeader('Content-Type', 'application/json');
  res.send(swaggerSpec);
});
```
Mount AVANT les routes `/api/v1/...` pour que `/api-docs` reste accessible sans auth.

### Endpoints exposés
- `GET /api-docs` — UI Swagger interactive
- `GET /api-docs.json` — FEAT OpenAPI JSON brute

### Génération par feature
Chaque task qui crée un nouveau controller / route DOIT enrichir `swaggerConfig.ts` (operation: augment, preserves: swaggerSpec, adds: les nouveaux paths). La task `app.ts` initiale (foundational, typiquement feat-auth/us-1/task-2) est la SEULE qui crée `swaggerConfig.ts` (operation: create) et qui mount Swagger UI dans `app.ts`.

---

# 2. Stack

## 2.1 Identite

Stack ID : back-exp
Langage : TypeScript
Runtime : Node.js 22+
Framework : Express.js
Namespace racine : `{BackendNamespace}`

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/backend/node-express.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id node-express`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| express | 4.21.2 |  |
| prisma | 6.1.0 |  |
| @prisma/client | 6.1.0 |  |
| pino | 9.5.0 |  |
| pino-http | 10.3.0 |  |
| pino-pretty | 13.0.0 |  |
| zod | 3.24.0 |  |
| swagger-jsdoc | 6.2.8 |  |
| swagger-ui-express | 5.0.1 |  |
| helmet | 8.0.0 |  |
| cors | 2.8.5 |  |
| dotenv | 16.4.7 |  |
| compression | 1.7.5 |  |
| express-rate-limit | 7.4.1 |  |
| typescript | 5.6.3 |  |
| ts-node-dev | 2.0.0 |  |
| tsc-alias | 1.8.10 |  |
| @types/node | 22.10.0 |  |
| @types/express | 5.0.0 |  |
| @types/cors | 2.8.17 |  |
| @types/swagger-jsdoc | 6.0.4 |  |
| @types/swagger-ui-express | 4.1.7 |  |
| eslint | 9.17.0 |  |
| typescript-eslint | 8.18.1 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| uuid-gen | uuid | 11.0.5 | uuid, guid.*genere, id.*aleatoire |
| uuid-gen | @types/uuid | 10.0.0 | uuid, guid.*genere, id.*aleatoire |
| date-utils | dayjs | 1.11.13 | dates.*format, duree, intervalle.*temps |
| auth-local | bcryptjs | 2.4.3 | auth-local, hash.*password, bcrypt |
| auth-local | @types/bcryptjs | 2.4.6 | auth-local, hash.*password, bcrypt |
| jwt | jsonwebtoken | 9.0.2 | jwt, auth-local, auth-azure-ad |
| jwt | @types/jsonwebtoken | 9.0.7 | jwt, auth-local, auth-azure-ad |
| http-client | axios | 1.7.9 | axios, appel.*api.*externe, service.*externe, third.party |
| http-client | axios-retry | 4.5.0 | axios, retry.*http, resilience |
| excel | exceljs | 4.4.0 | excel, \.xlsx, export.*excel, import.*excel, tableur |
| pdf | pdfkit | 0.15.2 | pdf, \.pdf, export.*pdf, generer.*pdf |
| file-upload | multer | 1.4.5-lts.1 | upload.*fichier, multipart, form-data |
| file-upload | @types/multer | 1.4.12 | upload.*fichier, multipart, form-data |
| object-mapping | class-transformer | 0.5.1 | class-transformer, auto.*mapping, dto.*mapping |
| decorator-validation | class-validator (alt) | 0.14.1 | class-validator, decorator.*validation |
<!-- LIBS_CATALOG_END -->

### 2.2 Outils

- **Project file** : `workspace/output/src/{BackendName}/package.json`
- **Build** : `npm --prefix workspace/output/src/{BackendName} run build`
- **Dev** : `npm --prefix workspace/output/src/{BackendName} run dev`
- **Smoke Command** :

```bash
npm --prefix workspace/output/src/{BackendName} run build
test -f workspace/output/src/{BackendName}/dist/server.js
```

- **Package manager** : npm
- **Type-check** : TypeScript

---

### 2.2.1 Init Commands

```bash
# Backend project init
mkdir -p workspace/output/src/{BackendName}
cd workspace/output/src/{BackendName}
npm init -y
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis node-express.libs.json -- ne pas editer (utiliser sync_stack_md.py).
(cd workspace/output/src/{BackendName} && pnpm add \
  express@4.21.2 \
  prisma@6.1.0 \
  @prisma/client@6.1.0 \
  pino@9.5.0 \
  pino-http@10.3.0 \
  pino-pretty@13.0.0 \
  zod@3.24.0 \
  swagger-jsdoc@6.2.8 \
  swagger-ui-express@5.0.1 \
  helmet@8.0.0 \
  cors@2.8.5 \
  dotenv@16.4.7 \
  compression@1.7.5 \
  express-rate-limit@7.4.1 \
  typescript@5.6.3 \
  ts-node-dev@2.0.0 \
  tsc-alias@1.8.10 \
  @types/node@22.10.0 \
  @types/express@5.0.0 \
  @types/cors@2.8.17 \
  @types/swagger-jsdoc@6.0.4 \
  @types/swagger-ui-express@4.1.7 \
  eslint@9.17.0 \
  typescript-eslint@8.18.1)
```
<!-- CORE_PACKAGES_END -->

```bash
cd workspace/output/src/{BackendName}
npx tsc --init --rootDir . --outDir ./dist --esModuleInterop true --resolveJsonModule true --module commonjs --target es2022 --strict true
npx prisma init --datasource-provider sqlserver
mkdir -p swagger
cd ../../..

# Shared library project init (manuel, hors catalog -- uses LibName project)
mkdir -p workspace/output/src/{LibName}
cd workspace/output/src/{LibName}
npm init -y
npm install zod class-transformer class-validator
npm install --save-dev typescript @types/node
npx tsc --init --rootDir . --outDir ./dist --declaration true --module commonjs --target es2022 --strict true
cd ../../..
```

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis node-express.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: uuid-gen
(cd workspace/output/src/{BackendName} && pnpm add uuid@11.0.5 @types/uuid@10.0.0)

# capability: date-utils
(cd workspace/output/src/{BackendName} && pnpm add dayjs@1.11.13)

# capability: auth-local
(cd workspace/output/src/{BackendName} && pnpm add bcryptjs@2.4.3 @types/bcryptjs@2.4.6)

# capability: jwt
(cd workspace/output/src/{BackendName} && pnpm add jsonwebtoken@9.0.2 @types/jsonwebtoken@9.0.7)

# capability: http-client
(cd workspace/output/src/{BackendName} && pnpm add axios@1.7.9 axios-retry@4.5.0)

# capability: excel
(cd workspace/output/src/{BackendName} && pnpm add exceljs@4.4.0)

# capability: pdf
(cd workspace/output/src/{BackendName} && pnpm add pdfkit@0.15.2)

# capability: file-upload
(cd workspace/output/src/{BackendName} && pnpm add multer@1.4.5-lts.1 @types/multer@1.4.12)

# capability: object-mapping
(cd workspace/output/src/{BackendName} && pnpm add class-transformer@0.5.1)

# capability: decorator-validation
# OU (alt) : (cd workspace/output/src/{BackendName} && pnpm add class-validator@0.14.1)
```
<!-- ONDEMAND_PACKAGES_END -->

---

### 2.2.2 dev / start scripts (obligatoires dans package.json)

```json
"scripts": {
  "build": "tsc",
  "start": "node dist/server.js",
  "dev": "ts-node-dev --respawn --transpile-only server.ts"
}
```

---

## 2.4 Patterns erreurs compilation

Format standard TypeScript émis par `tsc` :

```
{file}({line},{col}): error TS{code}: {message}
```

Codes prioritaires reconnus par `build_loop.skill.md` STEP D pour la
classification CORRECTIBLE / BLOCKING :

| Code | Signification | Classe build_loop |
|------|---------------|-------------------|
| TS2307 | Cannot find module / type declaration | CORRECTIBLE (import manquant) |
| TS2304 | Cannot find name | CORRECTIBLE (import / typo) |
| TS2322 | Type assignment incompatible | CORRECTIBLE (cast / shape DTO) |
| TS2345 | Argument type mismatch | CORRECTIBLE |
| TS7006 | Parameter implicitly any | CORRECTIBLE (annotation type) |
| TS2339 | Property does not exist on type | CORRECTIBLE (member missing) |
| TS2554 | Wrong number of arguments | CORRECTIBLE (signature) |
| TS2540 | Cannot assign to read-only property | CORRECTIBLE |
| TS2300 | Duplicate identifier | BLOCKING (collision de scope) |
| TS2451 | Cannot redeclare block-scoped | BLOCKING |
| TS2420 | Class incorrectly implements interface | BLOCKING (contrat cassé) |

Les erreurs ESLint, Prettier ou Prisma ne bloquent pas le build TypeScript
mais sont logguées en STEP D.5 du skill build_loop ; elles n'entrent pas
dans la classification CORRECTIBLE/BLOCKING (warnings only).

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — vérifiés par Backend Agent STEP 5.0 (naming
pre-check). Toute violation = ERROR avant écriture de fichier.

| Rôle | Pattern | Exemple |
|------|---------|---------|
| Controller | `{Entity}Controller` (classe export named) | `BebesController` |
| Service interface | `I{Entity}Service` | `IBebesService` |
| Service impl | `{Entity}Service` (implements `I{Entity}Service`) | `BebesService` |
| Repository interface | `I{Entity}Repository` | `IBebesRepository` |
| Repository impl | `{Entity}Repository` | `BebesRepository` |
| Mapper | `{Entity}Mapper` (classe statique) | `BebesMapper` |
| Entity (Prisma model) | `{Entity}` (singulier, PascalCase, model Prisma) | `Bebe` (`model Bebe { ... }`) |
| Input DTO | `{Entity}{Action}Input` dans `{LibName}/inputs/` | `BebeCreateInput`, `BebeFilterInput` |
| Output DTO | `{Entity}{Action}Output` dans `{LibName}/outputs/` | `BebeListItemOutput`, `BebeDetailOutput` |
| Model DTO | `{Entity}Model` dans `{LibName}/models/` (réponse client) | `BebeModel` |
| Route file | `{entity}.routes.ts` (kebab-case fichier, PascalCase symboles) | `bebes.routes.ts` |
| Middleware | `{purpose}Middleware` (camelCase function ou classe) | `errorMiddleware`, `authMiddleware` |
| Zod schema | `{Entity}{Action}Schema` (suffix `Schema`) | `BebeCreateSchema` |

**Suffixes INTERDITS** (rejet automatique en STEP 5.0.3) :
- `Dto`, `InputDto`, `OutputDto` — utiliser `Input`, `Output`, `Model`
- `Result`, `Response`, `Request` — utiliser `Output` ou `Model`
- `Manager`, `Helper`, `Util` (sauf `utils/` strict pour pure functions)
- `Impl` (l'implémentation porte le nom canonique, l'interface a `I*`)

**Conventions de fichier** :
- Tous les fichiers source en `kebab-case.ts` ou `camelCase.ts` selon le
  pattern listé ci-dessus
- Un fichier = un export principal nommé conformément à la table
- Les barrels (`index.ts`) sont autorisés uniquement dans `services/`,
  `repositories/`, `mappers/`, `entities/` pour re-export

---

## 3. Endpoints standard (obligatoires)

Tout backend Express généré expose AU MINIMUM :

| Endpoint | Auth | Rôle |
|----------|------|------|
| `GET /api-docs` | non | UI Swagger interactive |
| `GET /api-docs.json` | non | FEAT OpenAPI 3.0 JSON |
| `GET /api/v1/health` (optionnel) | non | Liveness probe (si task le demande) |

Les endpoints métier sont déclarés par les features (auth, register, employer, …).

---

## 4. Versioning des API

Tous les endpoints métier sont préfixés `/api/v1/...`. Le versioning est
porté par le préfixe d'URL, pas par un header. Toute task qui déclare un
`Files:` au layer Route MUST inclure le préfixe `/api/v1` dans la
définition de la route.

---

## 5. Interdits projet (backend)

Patterns scannés par Backend Agent STEP 6 (forbidden content). Toute
occurrence rejette le fichier généré et stoppe la task avec ERROR
`[DERIVE_VIOLATION]` ou `[BUILD_BLOCKING]` selon la classe.

**Architecture / data flow** :

- SQL brut (`prisma.$queryRaw`, `prisma.$executeRaw`) hors Repository
- DbContext / Prisma client instancié dans Service ou Controller (toujours injecté via DI)
- Logique métier dans Route ou Controller (déléguer à Service)
- Logique métier dans Entity (les modèles Prisma sont des DTOs DB pures)
- Mapping inline dans Controller / Service (toujours via Mapper dédié)
- Appels HTTP directs (`fetch`, `axios`) hors couche `services/external/` dédiée
- Validation manuelle (`if (!input.field) throw...`) — toujours via Zod schema

**Code quality** :

- `console.log`, `console.error` brut → utiliser `pino` logger structuré
- `any` injustifié dans les types (sauf parsing de payload externe avec cast immédiat)
- `as unknown as T` (double cast) sauf bridge type EF/Prisma documenté
- `// @ts-ignore`, `// @ts-nocheck`, `// @ts-expect-error` sans commentaire justificatif
- `TODO`, `FIXME`, `XXX`, `HACK` dans le code livré
- Imports relatifs profonds (`../../../`) au-delà de 2 niveaux → utiliser path alias
- `eval()`, `new Function()` (sécurité)
- `process.exit()` hors `server.ts` startup ou shutdown handler

**Sécurité (cf. `env_rules.md`, `cors.md`)** :

- Connection string littérale (`postgres://user:pass@host:port/db`) hors `prisma.schema` qui lit `env("DATABASE_URL")`
- Secret hardcodé (JWT_SECRET, API_KEY, OAuth client secret)
- DB credentials hardcodés (host, port, user, password)
- Token JWT loggé en clair (même en debug)
- Body request loggé sans masquage des champs sensibles (password, token, secret)
- Authentification désactivée sur un endpoint sans annotation `@Public()` documentée

**ORM (Prisma)** :

- Utilisation de `findFirst` / `findUnique` sans `select` ou `include` explicite (over-fetch)
- N+1 query (loop de `findUnique` au lieu d'un seul `findMany` avec `where: { in: [...] }`)
- Mutation Prisma sans transaction quand plusieurs tables sont impactées
- `prisma.$disconnect()` en cours d'exécution d'une requête (sauf shutdown handler)
- Migration auto-appliquée en code (`prisma migrate deploy` est un step CI/CD, pas runtime)

**API contract** :

- Endpoint sans documentation Swagger (cf. §1.6 — `swaggerConfig.ts` augment obligatoire)
- Réponse non-wrappée (toute réponse 2xx DOIT être un `ApiResponse<T>` ou `ApiResponse<T[]>`)
- Status code HTTP non standard (utiliser 200, 201, 204, 400, 401, 403, 404, 409, 422, 500)
- Body de POST/PUT non validé par un Zod schema
- Endpoint qui retourne une Entity Prisma directement (toujours mapper vers Output / Model DTO)

**Build / packaging** :

- Engager `node_modules/`, `dist/`, `.env` dans le git
- `package.json` sans `"engines": { "node": ">=22" }`
- Dépendance dev (ex. `@types/*`) déclarée dans `dependencies` au lieu de `devDependencies`
- Mix de `npm` et `yarn` / `pnpm` lockfiles dans le même projet

---

## 8. Persistence (cross-DatabaseType)

Sections lues par l'agent `arch` (Phase A pour installer le bon
driver, Phase B pour composer la config et invoquer le scaffolding).

### 8.1 DB Drivers — matrice DatabaseType → npm package

| DatabaseType  | npm package         | Driver class           |
|---------------|---------------------|------------------------|
| `SqlServer`   | `mssql`             | `mssql.ConnectionPool` |
| `PostgreSQL`  | `pg`                | `pg.Pool`              |
| `MySql`       | `mysql2`            | `mysql2/promise.Pool`  |
| `Sqlite`      | `better-sqlite3`    | (synchronous, file-based) |

Si Prisma est utilisé en plus (recommandé pour le scaffolding §8.3) :
le moteur Prisma télécharge ses propres binaires natifs au moment
du `prisma generate` — pas de driver npm explicite nécessaire pour
les requêtes.

Arch Phase A lit `## Active Database: DatabaseType` puis installe le
driver correspondant :
```bash
cd workspace/output/src/{BackendName} && npm install <package>
```

### 8.2 Connection String Pattern (lecture `config/default.json`, depuis 2026-05-14)

**Source de vérité** : bloc `## Active Database` de
`workspace/input/stack/stack.md`. L'agent `arch` Phase A — STEP 4.5
sérialise les valeurs dans `config/default.json` (npm package `config`,
déjà déclaré dans `node-express.libs.json` `core[]`).

Exemple `config/default.json` produit par arch :
```json
{
  "db": {
    "type": "postgres",
    "host": "127.0.0.1",
    "port": 5432,
    "name": "CMSPrint",
    "user": "postgres",
    "password": "cmsprint."
  }
}
```

**Lecture côté code applicatif** (`src/config/db.ts`) :
```ts
import config from 'config';

export interface DbConfig {
  type: string;
  host: string;
  port: number;
  name: string;
  user: string;
  password: string;
}

export const dbConfig: DbConfig = config.get('db');
// throw si absent — fail-fast au démarrage (npm package config)
```

**Plus de `process.env.DB_*`** (depuis 2026-05-14) : le code applicatif
ne lit JAMAIS `process.env`. La source = fichier `config/default.json`
peuplé par arch.

Pour **Prisma** : la convention `DATABASE_URL` reste utilisable pour
le générateur Prisma (qui exige cette env var pour `prisma db pull /
generate`). Arch passe ce `DATABASE_URL` au process child uniquement
(`spawn` avec `env: {...process.env, DATABASE_URL: ...}`), JAMAIS dans
`.env` du repo. Construction :
```ts
// scripts/build-prisma-url.ts (exécuté UNIQUEMENT par arch / scripts admin, pas par le code applicatif)
import config from 'config';
const db = config.get<DbConfig>('db');
const url = `${db.type}://${encodeURIComponent(db.user)}:${encodeURIComponent(db.password)}@${db.host}:${db.port}/${db.name}`;
// → passé au process child Prisma via env, jamais persisté
```

### 8.3 Scaffolding tool (Database-First)

Outil canonique : **`prisma db pull`** (introspection schema → modèles
Prisma). Alternative : `drizzle-kit introspect`.

Pattern d'invocation par Arch Phase B (Prisma) :
```bash
cd workspace/output/src/{BackendName}

# Init Prisma si absent (idempotent)
[ ! -f prisma/schema.prisma ] && npx prisma init --datasource-provider <provider>

# Composer DATABASE_URL en RAM (variable d'env du process child Prisma uniquement)
# Lue depuis config/default.json peuplé par arch en STEP 4.5, JAMAIS depuis .env
export DATABASE_URL="<url composée à partir de config.db (cf. §8.2)>"

# Introspection (schema.prisma rempli)
npx prisma db pull \
  --schema workspace/output/src/{BackendName}/prisma/schema.prisma \
  [--filter "T1,T2"]              # si DB Scaffolding Mode=list

# Génère le client TypeScript
npx prisma generate
```

`<provider>` selon DatabaseType :
- SqlServer : `sqlserver`
- PostgreSQL : `postgresql`
- MySql : `mysql`
- Sqlite : `sqlite`

Les modèles Prisma générés vivent dans `prisma/schema.prisma` (un
seul fichier — convention Prisma). Pas de classes partielles : les
ajouts custom (validations, helpers) vivent dans `src/lib/extensions/`.

---
