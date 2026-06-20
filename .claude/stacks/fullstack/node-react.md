# Tech FEAT: node-react (fullstack)

Status: POC-only
Validation: 🟡 POC-only — **utilisé exclusivement par workspace/console SDD interne** (v0.4.0 — Fastify 5 + React 18 CDN + Babel-standalone, 2026-05-16). **NON destiné à un usage production externe** (décision CTO 2026-06-05 audit P3) : pas de bundler, pas de TS natif, pas de pipeline build/lint/Playwright standard. Pour Node/React prod commercial, utiliser combo `backend/node-express` + `frontend/react` (back-front séparés avec Vite + TS strict).
Support: ⚠ Hors périmètre produit (audit C3/m2/m9, 2026-06-06) — usage interne console SDD uniquement, jamais commercialisé. Toute génération `/sdd-full` ciblant ce stack est bloquée par `preflight_stack_combo` (sauf `SDD_ALLOW_UNTESTED_COMBO=1`).
Tech FEAT ID: tech-node-react
Scope: **fullstack monolithe** — backend Node.js + frontend React servis depuis le MEME projet (zero-build, JSX transpilé in-browser via Babel Standalone). Pas de séparation `{BackendName}` / `{AppName}` / `{LibName}`. Modèle SSR-adjacent (le serveur sert l'HTML initial + l'API ; React hydrate côté client).

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application fullstack monolithique Node.js.** Un seul process Fastify sert simultanément :

- Les **endpoints REST** `/api/*` (validation Zod, services métier, persistance)
- Les **fichiers statiques** racine (`index.html`, `app.jsx`, `styles.css`, `data-loader.js`)
- Le **flux SSE** `/api/events` (push temps réel via `EventSource`)
- Optionnellement la **session WebSocket** (si activée, capability `realtime-ws`)

Le navigateur charge **React 18** + **Babel Standalone** via CDN. Le fichier `app.jsx` est servi en tant que `<script type="text/babel">` ; le JSX est compilé **dans le navigateur** au runtime → **zéro build, zéro bundler, zéro étape de transpilation côté CI**. Modèle inspiré directement de `workspace/console/` (cockpit de validation SDD_Pro).

Architecture cible (un seul projet) :

```
Browser
  ├── index.html
  │   ├─ <script src="https://unpkg.com/react@18/...">
  │   ├─ <script src="https://unpkg.com/@babel/standalone/...">
  │   └─ <script type="text/babel" src="app.jsx">
  └── EventSource('/api/events')   ── SSE temps réel
       │
       ▼
Node.js (Fastify)
  ├── @fastify/static  ── sert index.html / app.jsx / styles.css
  ├── Routes /api/*    ── REST endpoints
  ├── Services         ── logique métier
  ├── Repositories     ── I/O FS (JSON store) OU DB (Prisma optionnel)
  └── Broadcaster SSE  ── push events à tous les clients connectés
```

**Différence vs combo `node-express` × `react`** :
- Ici **un seul projet** (`workspace/output/src/{AppName}/`), pas de monorepo, pas de `{BackendName}` ni `{LibName}`
- **Pas de CORS** (même origine)
- **Pas de contract drift** front↔back (même codebase, types partagés via JSDoc ou simple convention)
- **Pas de bundler** côté client (`vite`/`webpack` exclus) — Babel-standalone fait tout au runtime

---

## 1.2 Couches

- **Server** (Node.js Fastify) : routing, validation, logique métier, persistance, SSE — entry point `server.js`
- **Routes** : handlers Fastify (`fastify.get('/api/...', ...)`), un fichier par domaine
- **Services** : logique métier pure (modules ESM), aucun I/O direct
- **Repositories** : I/O fichiers JSON (file-based store) OU Prisma ORM (capability `prisma`)
- **Schemas** : Zod ou Fastify JSON Schema pour validation entrée/sortie
- **Lib** : helpers serveur (atomic-write avec lock, file-watcher, IA explain, markdown filters)
- **Broadcaster** : SSE — `Set<ServerResponse>` + heartbeat 25s + `fs.watch` push
- **Static** : `public/` servi par `@fastify/static`
- **Pages React** (client) : composants top-level d'une URL, montés via routing client-side
- **Components React** (client) : composants réutilisables UI
- **Data loader** (client) : helper vanilla JS pour `fetch('/api/tree')` + cache léger

---

## 1.3 Mapping couche → répertoire

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas à ce stack**. L'agent `arch` lève une ERROR `[STACK_MALFORMED]` si `## Project Config` les déclare avec valeur ≠ `null`.

**Code serveur** :

- Entry server → `workspace/output/src/{AppName}/server.js`
- Routes (API) → `workspace/output/src/{AppName}/routes/` (`{domain}.routes.js`)
- Services → `workspace/output/src/{AppName}/services/`
- Repositories → `workspace/output/src/{AppName}/repositories/`
- Schemas (Zod) → `workspace/output/src/{AppName}/schemas/`
- Lib (helpers serveur) → `workspace/output/src/{AppName}/lib/` (`atomic-write.js`, `markdown-filter.js`, `sse-broadcaster.js`)
- Middleware → `workspace/output/src/{AppName}/middleware/` (auth, error, logger)
- Config → `workspace/output/src/{AppName}/config/default.json` (DB, JWT, SMTP)
- Persistance fichiers (file-based store) → `workspace/output/src/{AppName}/data/` (gitignored)

**Code client (servi par `@fastify/static`)** :

- HTML entry → `workspace/output/src/{AppName}/public/index.html`
- Bootstrap React → `workspace/output/src/{AppName}/public/app.jsx`
- Pages → `workspace/output/src/{AppName}/public/pages/` (un fichier `.jsx` par route, exposé en global ou imports `<script type="module">`)
- Components → `workspace/output/src/{AppName}/public/components/`
- Styles → `workspace/output/src/{AppName}/public/styles.css`
- Data loader (vanilla JS) → `workspace/output/src/{AppName}/public/data-loader.js`
- Assets statiques → `workspace/output/src/{AppName}/public/assets/`

**Manifestes** :

- Project file → `workspace/output/src/{AppName}/package.json`
- ESLint → `workspace/output/src/{AppName}/eslint.config.js`
- Prettier → `workspace/output/src/{AppName}/.prettierrc`
- (optionnel) Prisma schema → `workspace/output/src/{AppName}/prisma/schema.prisma`

---

## 1.4 Principes non négociables

**Architecture monolithe single-project** :
- **Aucun bundler côté client** (`vite`, `webpack`, `parcel`, `esbuild` interdits dans `package.json`)
- **Aucun build step JSX en CI** : la transpilation est intégralement déléguée à `@babel/standalone` chargé en CDN
- **Aucune dépendance `react`/`react-dom` dans `package.json`** : React est chargé exclusivement via CDN (`unpkg`, `jsdelivr`) en mode UMD
- **Aucune logique métier dans les handlers Fastify** → toujours déléguer à un Service
- **Aucun accès FS / DB direct depuis un Service** → toujours via Repository
- **Validation Zod obligatoire** sur tout body POST/PUT — pas de `if (!body.x) throw...`
- **Logging structuré obligatoire** (`fastify.log` JSON, jamais `console.log` en prod)
- **SSE broadcaster centralisé** : un seul `Set<ServerResponse>` + `broadcast()` exporté, jamais d'`req/res` raw dans les services
- **Path traversal protégé** : tout endpoint qui prend un `path` query param doit `resolve()` puis vérifier que le résultat reste sous le répertoire autorisé (cf. `/api/file` console)

**Clean Code** :
- Modules ESM (`"type": "module"` dans `package.json`)
- Fichiers `.js` côté serveur, `.jsx` côté client (JSX uniquement dans `public/`)
- Imports relatifs avec extension `.js` obligatoire (Node ESM strict)
- Pas de TypeScript (sinon → migrer vers `nextjs.md` ou ajouter un build step)
- Pas de magic strings/numbers — constantes nommées

**Client React (Babel-standalone)** :
- Le fichier `app.jsx` est chargé via `<script type="text/babel">` — toute extension JSX hors `public/` est interdite
- Pas de `import` ES modules dans `app.jsx` (Babel-standalone ne les résout pas) — utiliser globales `React`, `ReactDOM` (UMD)
- Composants déclarés en `function ComponentName(props) { ... }` puis exposés via `window.ComponentName` ou agrégés dans `app.jsx`
- Pas de hooks third-party (`react-query`, `react-router`) sauf si chargés via CDN UMD

---

## 1.5 Couches persistantes

Patterns reconnus comme persistants (déclenche `DB_REQUIRED` dans le pipeline si `DatabaseType ≠ none`) :

- `Entity`, `Entities` (Prisma models si capability `prisma` active)
- `Repository`, `Repositories`
- `Migration`, `Migrations`

**Mode par défaut** : file-based store JSON (`data/status.json`, `data/users.json`, …) avec écriture atomique + lock (cf. `lib/atomic-write.js` console). Suffisant pour outils internes, prototypes, dashboards.

**Mode DB** (opt-in via capability `prisma`) : Prisma 6 + driver selon `DatabaseType`. Pattern identique à `node-express.md §8.3`.

---

## 1.6 Contrat API + Documentation Swagger (obligatoire — auto-câblé)

Tout projet généré sur ce stack DOIT exposer Swagger UI sur `/api-docs` et la spec JSON sur `/api-docs.json`.

### Fichiers obligatoires
- `workspace/output/src/{AppName}/lib/swagger-config.js` — exporte `swaggerSpec` (OpenAPI 3.0.3)
- `info.title` = `{AppName} API`
- `components.securitySchemes.bearerAuth` = `{ type: 'http', scheme: 'bearer', bearerFormat: 'JWT' }` (si auth-local active)
- `paths` enrichis à chaque route ajoutée (mode `augment`, `preserves: [swaggerSpec]`, `adds: [path:/api/...]`)

### `server.js` mount obligatoire

```js
import fastifySwagger from '@fastify/swagger';
import fastifySwaggerUi from '@fastify/swagger-ui';
import { swaggerSpec } from './lib/swagger-config.js';

await fastify.register(fastifySwagger, { mode: 'static', specification: { document: swaggerSpec } });
await fastify.register(fastifySwaggerUi, { routePrefix: '/api-docs' });
```

Mount **AVANT** `@fastify/static` pour que `/api-docs` ne soit pas masqué par `index.html`.

### Endpoints exposés
- `GET /` → `public/index.html` (sert l'app React)
- `GET /api-docs` → UI Swagger
- `GET /api-docs.json` → spec OpenAPI JSON
- `GET /api/health` → `{ ok: true, version }`
- `GET /api/events` → SSE stream

---

# 2. Stack

## 2.1 Identité

- **Stack ID** : `fullstack-node-react`
- **Langage** : JavaScript ESM (Node 20+) côté serveur, JSX (transpilé in-browser) côté client
- **Runtime serveur** : Node.js 22 LTS (LTS "Jod", support jusqu'à Apr 2027)
- **Runtime client** : Tout navigateur evergreen (Chrome 100+, Firefox 100+, Safari 15+) — pas d'IE
- **Framework serveur** : Fastify 5.x
- **Framework client** : React 18.3 UMD (chargé via CDN unpkg)
- **Transpileur client** : @babel/standalone 7.x (chargé via CDN)
- **Namespace racine** : `{AppNamespace}` (utilisé uniquement dans les commentaires de header de fichier ; pas de `package.scope`)

---

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Build** : `(cd workspace/output/src/{AppName} && npm install)` — pas de bundle step, seulement install des deps serveur
- **Dev** : `(cd workspace/output/src/{AppName} && node --watch server.js)`
- **Start** : `(cd workspace/output/src/{AppName} && node server.js)`
- **Smoke Command** :

```bash
(cd workspace/output/src/{AppName} && npm install --silent)
test -f workspace/output/src/{AppName}/server.js
test -f workspace/output/src/{AppName}/public/index.html
test -f workspace/output/src/{AppName}/public/app.jsx
node --check workspace/output/src/{AppName}/server.js
```

- **Smoke Timeout** : 60s
- **Package manager** : npm (pas de pnpm/yarn pour rester simple — un seul lockfile)
- **Type-check** : aucun (pas de TS). Optionnel : JSDoc + `// @ts-check` per-file
- **Lint** : ESLint 9 flat config

---

## 2.2.1 Init Commands

```bash
# Garde-fou idempotent
if [ ! -f "workspace/output/src/{AppName}/package.json" ]; then

# STEP 1 — Project init
mkdir -p workspace/output/src/{AppName}/{routes,services,repositories,schemas,lib,middleware,config,data,public/{pages,components,assets}}
cd workspace/output/src/{AppName}
npm init -y

# STEP 2 — package.json patch ESM + scripts + engines
node -e "
  const p = require('./package.json');
  p.type = 'module';
  p.private = true;
  p.engines = { node: '>=22' };
  p.scripts = {
    start: 'node server.js',
    dev: 'node --watch server.js',
    lint: 'eslint .',
    test: 'echo \"tests via qa-node-vitest stack\" && exit 0'
  };
  require('fs').writeFileSync('./package.json', JSON.stringify(p, null, 2));
"

# STEP 3 — Install core deps
npm install \
  fastify@5.2.0 \
  @fastify/static@8.0.4 \
  @fastify/swagger@9.4.0 \
  @fastify/swagger-ui@5.2.0 \
  @fastify/cors@10.0.1 \
  @fastify/helmet@13.0.1 \
  @fastify/rate-limit@10.2.1 \
  @fastify/sensible@6.0.1 \
  pino@9.5.0 \
  pino-pretty@13.0.0 \
  zod@3.24.0 \
  config@3.3.12

# STEP 4 — Install dev deps
npm install --save-dev \
  eslint@9.17.0 \
  @eslint/js@9.17.0

# STEP 5 — Bootstrap index.html (CDN React + Babel)
cat > public/index.html <<'HTML'
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{AppName}</title>
<link rel="stylesheet" href="styles.css"/>
</head>
<body>
<div id="root">Chargement…</div>
<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" crossorigin="anonymous"></script>
<script src="data-loader.js"></script>
<script type="text/babel" src="app.jsx"></script>
</body>
</html>
HTML

# STEP 6 — config/default.json (rempli par arch depuis stack.md)
cat > config/default.json <<'JSON'
{
  "server": { "port": 5173, "host": "127.0.0.1" },
  "db": { "type": "none" },
  "auth": { "jwtSecret": "TO_BE_FILLED_BY_ARCH" }
}
JSON

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/fullstack/node-react.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id node-react`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| fastify | 5.2.0 | Serveur HTTP + routing + plugins |
| @fastify/static | 8.0.4 | Sert public/ (index.html, app.jsx, styles.css) |
| @fastify/swagger | 9.4.0 |  |
| @fastify/swagger-ui | 5.2.0 |  |
| @fastify/cors | 10.0.1 |  |
| @fastify/helmet | 13.0.1 | Security headers (CSP, HSTS) |
| @fastify/rate-limit | 10.2.1 |  |
| @fastify/sensible | 6.0.1 |  |
| pino | 9.5.0 | Logger JSON structure |
| pino-pretty | 13.0.0 |  |
| zod | 3.24.0 | Validation schemas (body/query/params) |
| config | 3.3.12 | Lecture config/default.json peuple par arch |
| eslint | 9.17.0 |  |
| @eslint/js | 9.17.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| anthropic-ai | @anthropic-ai/sdk | 0.40.1 | claude, anthropic, reformulation.*ia, explain.*ia |
| jwt | @fastify/jwt | 9.0.1 | jwt, auth-local, auth-azure-ad |
| auth-local | bcryptjs | 2.4.3 | auth-local, hash.*password, bcrypt |
| prisma | prisma | 6.1.0 | prisma, orm, database.*scaffold, db-first |
| prisma | @prisma/client | 6.1.0 | prisma, orm |
| websocket | @fastify/websocket | 11.0.1 | websocket, ws, realtime.*bidirectional |
| http-client | undici | 7.2.0 | appel.*api.*externe, http-client, fetch.*backend |
| markdown | marked | 14.1.4 | markdown.*render, md.*rendu, marked |
| date-utils | dayjs | 1.11.13 | dates.*format, duree, intervalle.*temps |
| file-upload | @fastify/multipart | 9.0.1 | upload.*fichier, multipart, form-data |
| excel | exceljs | 4.4.0 | excel, \.xlsx, export.*excel |
| pdf | pdfkit | 0.15.2 | pdf, \.pdf, export.*pdf |
| smtp | nodemailer | 6.9.16 | email, smtp, envoi.*mail, notification.*mail |
| compression | @fastify/compress | 8.0.1 | compression, gzip, brotli |
| scheduled-jobs | node-cron | 3.0.3 | scheduled.*job, cron, scheduler, nightly, background.*service, task.*planifi, tache.*planifi |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| sqlserver | `@prisma/client` | 6.1.0 | runtime |
| postgres | `@prisma/client` | 6.1.0 | runtime |
| mysql | `@prisma/client` | 6.1.0 | runtime |
| sqlite | `@prisma/client` | 6.1.0 | runtime |
| mariadb | `@prisma/client` | 6.1.0 | runtime |
<!-- LIBS_CATALOG_END -->

---

### 2.2.2 dev / start scripts (obligatoires dans package.json)

```json
{
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": {
    "start": "node server.js",
    "dev": "node --watch server.js",
    "lint": "eslint .",
    "test": "echo \"tests via qa-node-vitest stack\" && exit 0"
  }
}
```

---

## 2.3 Patterns erreurs runtime (pas de compilation)

Pas de transpilation côté serveur (Node ESM natif) → pas d'erreurs TS. Les erreurs typiques apparaissent au **démarrage** (`node --check server.js` ou `node server.js`).

| Erreur | Signification | Classe build_loop |
|---|---|---|
| `SyntaxError: Cannot use import statement outside a module` | `"type": "module"` manquant dans `package.json` | CORRECTIBLE |
| `ERR_MODULE_NOT_FOUND` | Import sans extension `.js` | CORRECTIBLE |
| `ERR_REQUIRE_ESM` | `require()` sur module ESM | CORRECTIBLE |
| `SyntaxError: Unexpected token` (dans `.jsx`) | JSX importé côté serveur (interdit) | BLOCKING (layer violation) |
| `Cannot find package 'fastify'` | `npm install` non exécuté | CORRECTIBLE (relancer install) |
| `EADDRINUSE` | Port déjà utilisé | BLOCKING (env-level) |
| `FST_ERR_DUPLICATED_ROUTE` | Route enregistrée 2× | CORRECTIBLE (renommer/regrouper) |

Côté **client**, les erreurs JSX sont visibles dans la console browser (`Babel-standalone` les lève). Le pipeline build ne les voit pas — couverture assurée par le smoke test qui charge `/` et vérifie `200`.

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — vérifiés par dev-* STEP 5.0 (naming pre-check). Toute violation = ERROR avant écriture.

| Rôle | Pattern | Exemple |
|------|---------|---------|
| Route file | `{domain}.routes.js` | `tree.routes.js`, `validate.routes.js` |
| Route handler | `register{Domain}Routes(fastify)` (export named) | `registerTreeRoutes` |
| Service | `{domain}Service.js` (camelCase export object) | `treeService.js` exportant `treeService.getTree()` |
| Repository | `{entity}Repository.js` | `statusRepository.js` |
| Schema Zod | `{Domain}{Action}Schema` | `ValidateBodySchema`, `GateDecideBodySchema` |
| Middleware | `{purpose}Middleware.js` | `authMiddleware.js`, `errorMiddleware.js` |
| Lib helper | `kebab-case.js` | `atomic-write.js`, `sse-broadcaster.js` |
| React Page | `{Name}Page.jsx` (PascalCase) | `DashboardPage.jsx` |
| React Component | `{Name}.jsx` (PascalCase) | `Topbar.jsx`, `TreeNode.jsx` |

**Suffixes INTERDITS** :
- `.controller.js` (utiliser `.routes.js` — pattern Fastify, pas Express)
- `Dto`, `Request`, `Response` (utiliser `Schema` pour Zod, `Body`/`Query`/`Params` comme suffixes)
- `Manager`, `Helper`, `Util` (sauf `lib/` pour pure functions)
- `Impl` (pas d'interfaces en JS — le module est l'interface)

**Conventions de fichier** :
- Tous les `.js` serveur en `kebab-case` OU `camelCase`
- Tous les `.jsx` client en `PascalCase` (composants) OU `camelCase` (helpers)
- Un fichier = un export principal nommé conformément à la table
- `index.js` autorisé uniquement pour barrel exports dans `services/`, `repositories/`

---

## 3. Endpoints standard (obligatoires)

Tout projet généré sur ce stack expose AU MINIMUM :

| Endpoint | Auth | Rôle |
|----------|------|------|
| `GET /` | non | Sert `public/index.html` (SPA bootstrap) |
| `GET /api/health` | non | `{ ok: true, app: "{AppName}", version }` |
| `GET /api-docs` | non | UI Swagger interactive |
| `GET /api-docs.json` | non | Spec OpenAPI 3.0 JSON |
| `GET /api/events` | non | SSE stream (heartbeat 25s) |

Les endpoints métier sont déclarés par les FEATs.

---

## 4. Versioning des API

Les endpoints sont préfixés `/api/` (pas de `/api/v1/` obligatoire en mode console — versioning par URL acceptable si SLA stable nécessaire). Pour un projet destiné à des consommateurs externes, **basculer à `/api/v1/...`** via décision Tech Lead + ADR.

---

## 5. Interdits projet (fullstack node-react)

Patterns scannés par dev-* STEP 6 (forbidden content). Toute occurrence rejette le fichier.

**Architecture / data flow** :

- Bundler côté client (`vite`, `webpack`, `parcel`, `esbuild`, `rollup`) dans `package.json`
- `react` / `react-dom` listés dans `dependencies` (interdit — chargement CDN uniquement)
- Fichier `.tsx` (uniquement `.jsx` toléré côté client ; `.ts` interdit côté serveur — utiliser `.js` ESM)
- `import` ES modules dans `app.jsx` (Babel-standalone ne résout pas — utiliser globales `React`, `ReactDOM`)
- Logique métier dans un handler Fastify (déléguer à un Service)
- Accès `fs` / DB direct depuis un Service (passer par Repository)
- Mapping/transformation lourde inline dans une route (extraire dans un mapper)
- `fetch` / `axios` direct depuis un Service métier hors `services/external/`
- Validation manuelle (`if (!body.x) throw...`) — toujours Zod

**Code quality** :

- `console.log` / `console.error` brut → `fastify.log.info/error` (pino)
- `var` — utiliser `const` / `let`
- `==` / `!=` — utiliser `===` / `!==`
- Arrow functions sans `return` explicite quand le corps a > 1 expression
- `eval()`, `new Function()` (sécurité)
- `process.exit()` hors `server.js` startup ou shutdown handler
- Imports relatifs profonds (`../../../`) au-delà de 2 niveaux — utiliser des helpers dans `lib/`
- Variables non utilisées (catch ESLint `no-unused-vars`)
- Code mort, méthodes jamais appelées

**Sécurité** :

- Connection string littérale hors `config/default.json` (jamais en clair dans le code source)
- Secret hardcodé (JWT_SECRET, API_KEY, SMTP password) — toujours via `config.get('...')`
- Token JWT loggé en clair (même en debug)
- Body request loggé sans masquage des champs sensibles (password, token, secret, authorization)
- Endpoint sans auth quand l'AC l'exige
- Path traversal non protégé : tout endpoint qui prend un `path` query/body param DOIT `resolve()` puis vérifier que le résultat reste sous le répertoire autorisé (cf. `/api/file` console `server.js:330-334`)
- CORS `*` en production
- Cookies sans `httpOnly` + `secure` + `sameSite: 'lax'` minimum

**Static / public** :

- Fichier `.env` dans `public/` (exposé au navigateur)
- Secret ou config interne dans `public/` (n'importe quoi servi par `@fastify/static` est public)
- `node_modules/` dans `public/`
- Fichier exécutable serveur (`*.js` non-jsx, `*.ts`) dans `public/`

**Build / packaging** :

- Engager `node_modules/`, `data/`, `.env` dans git
- `package.json` sans `"type": "module"` ou sans `"engines": { "node": ">=22" }`
- Mix de `npm` + `yarn` + `pnpm` lockfiles dans le même projet
- Dépendance `react`/`react-dom` (interdit — CDN only)

---

## 6. Persistance (auto-détectée depuis `## Active Database`)

Le mode de persistance est déterminé **automatiquement** par la valeur de `DatabaseType` du bloc `## Active Database` de `stack.md`. **Aucun fallback silencieux** entre les deux modes — le contrat utilisateur est tenu :

| `DatabaseType` | Mode | Driver / ORM |
|---|---|---|
| `none` | **File-based JSON** (legacy console pattern) | `lib/atomic-write.js` lock+rename |
| `sqlserver` | **Prisma + SQL Server** (auto-activé) | `prisma` + `@prisma/client` 6.1.0 (driver `tedious` bundlé) |
| `postgres` / `postgresql` | **Prisma + PostgreSQL** (auto-activé) | `prisma` + `@prisma/client` 6.1.0 (driver `pg` bundlé) |
| `mysql` / `mariadb` | **Prisma + MySQL** (auto-activé) | `prisma` + `@prisma/client` 6.1.0 (driver `mysql2` bundlé) |
| `sqlite` | **Prisma + SQLite** (auto-activé) | `prisma` + `@prisma/client` 6.1.0 (driver `better-sqlite3` bundlé) |

Quand `DatabaseType ≠ none`, l'agent `arch` **force l'activation de la capability `prisma`** (équivalent à `Capabilities: prisma` en Project Config — voir §10). Aucune capability `prisma` n'est requise dans le Project Config — c'est automatique. Le stack `node-react` ne sait **pas** parler à une DB SQL sans Prisma : si DB déclarée + Prisma absent = ERROR `[STACK_MALFORMED]` côté arch.

### 6.1 Mode file-based JSON (DatabaseType: none)

Pattern legacy de la console SDD_Pro. Adapté aux outils internes / cockpits / POC < 10k lignes de données.

```
workspace/output/src/{AppName}/
├── data/
│   ├── status.json        ← état applicatif principal
│   ├── users.json         ← (si auth-local)
│   └── .locks/            ← fichiers de lock atomic-write (gitignored)
```

Pattern atomic write (`lib/atomic-write.js`) — lock O_EXCL retry, lecture, mutation, write `.tmp`, rename atomique, release :

```js
import { writeFile, rename } from 'node:fs/promises';
export async function withLockedWrite(file, mutator) { /* lock + rename atomique */ }
```

### 6.2 Mode Prisma DB (DatabaseType ∈ {sqlserver, postgres, mysql, sqlite})

Quand `DatabaseType ≠ none`, l'agent `arch` Phase B :

1. **Installe** `prisma` (devDep) + `@prisma/client` (dep) depuis `.libs.json.dbDrivers[$dbtype]` au STEP 4.1
2. **Crée** `prisma/schema.prisma` avec le datasource correspondant au `DatabaseType` (provider + url Prisma `DATABASE_URL`, alimente par `arch` depuis la config native)
3. **Introspecte** la base existante via `npx prisma db pull` (génère le bloc `model` pour chaque table)
4. **Génère** le client TypeScript-flavored via `npx prisma generate` (sortie `node_modules/.prisma/client/`)
5. **Écrit** `lib/db.js` — singleton Prisma client (cf. §6.2.2)
6. **Persiste** le mapping `schema.json` dans `workspace/output/db/` pour consommation par `dev-backend` (mêmes invariants que les autres stacks)

#### 6.2.1 Variables d'environnement

`DATABASE_URL` est construit par `arch` à partir des 5 clés `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` du bloc `## Active Database`, puis stocke dans `config/default.json` sous `db.url`. Format par provider :

| Provider | DATABASE_URL pattern |
|---|---|
| `sqlserver` | `sqlserver://{DB_HOST}:{DB_PORT};database={DB_NAME};user={DB_USER};password={DB_PASSWORD};encrypt=true;trustServerCertificate=true` |
| `postgres` | `postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?schema=public` |
| `mysql` | `mysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}` |
| `sqlite` | `file:./{DB_NAME}.db` |

Le code applicatif **n'utilise pas directement** `DATABASE_URL` — il importe `lib/db.js`. Ce module lit `config.get("db.url")`, passe l'URL a `PrismaClient({ datasources: { db: { url } } })`, puis expose le singleton Prisma. Aucune lecture directe `process.env.DB_*` / `process.env.DATABASE_URL`.

#### 6.2.2 Singleton client (`lib/db.js`)

```js
// lib/db.js — Prisma client singleton (lazy + cached pour HMR / --watch)
import { PrismaClient } from '@prisma/client';
import config from 'config';

const globalForPrisma = globalThis;
const databaseUrl = config.get('db.url');
export const prisma =
  globalForPrisma.__nounouPrisma ||
  new PrismaClient({
    datasources: { db: { url: databaseUrl } },
    log: ['warn', 'error'],
  });

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.__nounouPrisma = prisma;
}
```

#### 6.2.3 Pattern repository

```js
// repositories/userRepository.js
import { prisma } from '../lib/db.js';

export async function findByEmail(email) {
  return prisma.employee.findUnique({ where: { Email: email } });
}

export async function create({ email, passwordHash, telephone }) {
  return prisma.employee.create({
    data: { Email: email, MotdePass: passwordHash, Telephone: telephone },
  });
}
```

#### 6.2.4 Transactions atomiques (FEAT multi-INSERT)

Pour les FEATs qui exigent une transaction (ex. créer un Employeur puis un Contrat liés par FK), utiliser `prisma.$transaction([...])` (sequential operations) ou `prisma.$transaction(async (tx) => { ... })` (interactive, recommandé pour récupérer un `id` retourné par le premier INSERT et l'utiliser dans le second) :

```js
const result = await prisma.$transaction(async (tx) => {
  const emp = await tx.employeur.create({ data: employeurData });
  const ctr = await tx.contrat.create({
    data: { ...contratData, EmployeurId: emp.Id },
  });
  return { employeurId: emp.Id, contratId: ctr.Id };
});
// En cas d'exception dans le bloc, Prisma rollback intégralement.
```

---

## 7. Temps réel — SSE par défaut, WebSocket optionnel

### 7.1 SSE (default)

Server-Sent Events est le pattern temps réel **par défaut** pour ce stack — simple, unidirectionnel (server → client), traverse les proxies sans config.

Endpoint canonique : `GET /api/events`. Pattern complet documenté dans `workspace/console/server.js:649-667`.

```js
// routes/events.routes.js
const sseClients = new Set();

export function broadcast(event) {
  const data = `data: ${JSON.stringify(event)}\n\n`;
  for (const client of sseClients) {
    try { client.write(data); } catch { /* gone */ }
  }
}

export function registerEventsRoutes(fastify) {
  fastify.get('/api/events', (req, reply) => {
    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    sseClients.add(reply.raw);
    const heartbeat = setInterval(() => {
      try { reply.raw.write(': ping\n\n'); } catch { /* gone */ }
    }, 25_000);
    req.raw.on('close', () => {
      clearInterval(heartbeat);
      sseClients.delete(reply.raw);
    });
  });
}
```

Côté client :

```jsx
React.useEffect(() => {
  const es = new EventSource('/api/events');
  es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    // dispatch
  };
  return () => es.close();
}, []);
```

### 7.2 WebSocket (capability `websocket`)

Activé via `@fastify/websocket` si l'US déclenche le trigger `websocket|realtime.*bidirectional`. Cas d'usage : chat, collaboration temps réel, drag-and-drop multi-utilisateur. Au-delà, considérer `nextjs.md` + provider tiers (Pusher, Ably).

---

## 8. Anti-pattern majeur — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Outils internes** (cockpits, dashboards admin, validateurs SDD comme la console)
- **Prototypes** rapides, démos clients, MVP
- **SaaS internes** < 50 utilisateurs concurrents
- **Projets sans pipeline CI build front** (déploiement = `git pull && npm install && pm2 restart`)

**NE PAS choisir ce stack si** :
- ❌ Besoin de SSR vrai (HTML pré-rendu serveur) → `nextjs.md`
- ❌ Besoin de tree-shaking, code-splitting, lazy routes → bundler nécessaire (`backend/node-express.md` + `frontend/react.md`)
- ❌ Besoin TypeScript end-to-end → `backend/node-express.md` + `frontend/react.md` (deux projets)
- ❌ Besoin de tests E2E browser intensifs sur le code client → Babel-in-browser complique le debugging
- ❌ App > 50k LOC ou > 100 composants React → la perte de tree-shaking devient gênante
- ❌ Compliance / audit qui exige des sources vérifiables et signées (CDN unpkg = supply-chain hors contrôle)

---

## 9. Combos validés

| Combo | Status | Source |
|---|---|---|
| `fullstack-node-react` + `auth-local` + `qa-node-vitest` + `none` (file-based) | 🟢 reference | `workspace/console/` v0.4.0 |
| `fullstack-node-react` + `auth-local` + `qa-node-vitest` + `SqlServer` (Prisma) | 🟢 reference | NounouJob POC 2026-05-26 (Prisma auto-activé via `## Active Database`) |
| `fullstack-node-react` + `auth-azure-ad` | 🟡 experimental | viable mais hors scope console |

---

## 10. Notes pour l'agent `arch`

À l'init du projet (Phase A) :

1. **Détecter** que `Active Tech Specs` pointe sur `fullstack/node-react.md` — si OUI, **ignorer** `BackendName` et `LibName` de `## Project Config` (lever WARNING `[STACK_MALFORMED]` non bloquant si déclarés)
2. **Créer** UNE structure `workspace/output/src/{AppName}/` avec layout §1.3
3. **Installer** §2.4.a CORE via §2.2.1
4. **Composer** `config/default.json` depuis `## Active Database` + `## Active Auth Specs` + `## Active SMTP Server` (mêmes clés que `node-express.md §8.2`)
5. **Pas de `Active UI Specs`** attendu — l'UI est ad-hoc CSS dans `public/styles.css`. Si `shadcn` ou `vuetify` est déclaré → WARNING (le stack ne les supporte pas avec Babel-standalone)
6. **Pas de mode `LibStrategy: openapi-codegen`** — pas de package séparé. WARNING si déclaré.

Phase B (DB scaffolding) :

- Si `DatabaseType: none` → skip silencieux (mode file-based JSON, cf. §6.1).
- Si `DatabaseType ∈ {sqlserver, postgres, postgresql, mysql, mariadb, sqlite}` → **force-install la capability `prisma`** (ajoute `prisma` + `@prisma/client` depuis §2.4.b même si `Capabilities:` ne la liste pas), puis exécute la séquence §6.2 :
  1. `npx prisma init --datasource-provider {provider}` (où `{provider}` = `sqlserver` | `postgresql` | `mysql` | `sqlite`)
  2. Écrit `db.url` dans `config/default.json` depuis `stack.md` — cf. §6.2.1 mapping pattern
  3. `npx prisma db pull` pour introspecter la base existante
  4. `npx prisma generate` pour produire le client
  5. Crée `lib/db.js` (singleton client, cf. §6.2.2) si absent — sinon préservé (idempotent)
  6. Persiste `workspace/output/db/schema.json` (mêmes invariants que les autres stacks) à partir du résultat de `prisma db pull`
- Si `DatabaseType ≠ none` mais introspection échoue (DB inaccessible) → STOP + ERROR `[NETWORK]` ou `[AUTH]` selon stderr. **Pas de fallback file-based silencieux** : le contrat utilisateur (DB déclarée = DB utilisée) est tenu strictement.

Phase C (ADRs) : créer `ADR-{ts}-stack-fullstack-node-react.md` documentant le choix monolithe + zero-build.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack est unique en ce qu'il est lu par **les deux agents** dev-* (pas seulement un seul comme les stacks backend/ ou frontend/).

- `dev-backend` matérialise : `server.js`, `routes/`, `services/`, `repositories/`, `schemas/`, `middleware/`, `lib/`, `config/`
- `dev-frontend` matérialise : `public/index.html`, `public/app.jsx`, `public/pages/`, `public/components/`, `public/styles.css`, `public/data-loader.js`

**File ownership** (override `file-ownership.md §1`) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/server.js` | `dev-backend` |
| `workspace/output/src/{AppName}/routes/**` | `dev-backend` |
| `workspace/output/src/{AppName}/services/**` | `dev-backend` |
| `workspace/output/src/{AppName}/repositories/**` | `dev-backend` |
| `workspace/output/src/{AppName}/schemas/**` | `dev-backend` |
| `workspace/output/src/{AppName}/lib/**` | `dev-backend` |
| `workspace/output/src/{AppName}/middleware/**` | `dev-backend` |
| `workspace/output/src/{AppName}/config/**` | `arch` (create) + `dev-backend` (lecture seule) |
| `workspace/output/src/{AppName}/public/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/package.json` | `arch` (create) + `dev-backend` (augment deps) |

**Anti-pattern** : `dev-frontend` ne doit JAMAIS écrire sous un autre dossier que `public/`. `dev-backend` ne doit JAMAIS écrire dans `public/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}
npm install --silent
node --check server.js                     # syntaxe OK
test -f public/index.html                  # bootstrap HTML
test -f public/app.jsx                     # JSX bootstrap
grep -q "type.*module" package.json        # ESM activé
grep -q "react@18" public/index.html       # CDN React pinné
echo "smoke OK"
```

Si toutes les vérifications passent → arch Phase A 🟢 GREEN.
