# Tech FEAT: node-react (fullstack)

Status: Draft  
Validation: 🟡 experimental (validated combo: workspace/console v0.4.0 — Fastify 5 + React 18 CDN + Babel-standalone, 2026-05-16)  
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

> Source de vérité (future) : `.claude/stacks/fullstack/node-react.libs.json`. Ce tableau est édité manuellement tant que le catalogue JSON n'est pas généré — à régénérer via `sync_stack_md.py` une fois `node-react.libs.json` créé.

#### 2.4.a Librairies CORE (installées par arch en §2.2.1, toujours)

| Lib | Version | Rôle |
|-----|---------|------|
| fastify | 5.2.0 | Serveur HTTP + routing + plugins |
| @fastify/static | 8.0.4 | Sert `public/` (index.html, app.jsx, styles.css) |
| @fastify/swagger | 9.4.0 | Génération spec OpenAPI |
| @fastify/swagger-ui | 5.2.0 | UI Swagger sur `/api-docs` |
| @fastify/cors | 10.0.1 | CORS (utile uniquement si front sur autre origine en dev) |
| @fastify/helmet | 13.0.1 | Security headers (CSP, HSTS, X-Frame-Options) |
| @fastify/rate-limit | 10.2.1 | Rate limiting per-IP |
| @fastify/sensible | 6.0.1 | Helpers `reply.notFound()`, `httpErrors.*`, schemas |
| pino | 9.5.0 | Logger JSON structuré |
| pino-pretty | 13.0.0 | Formatter logs dev |
| zod | 3.24.0 | Validation schémas (body/query/params) |
| config | 3.3.12 | Lecture `config/default.json` peuplé par arch |
| eslint | 9.17.0 | Linting flat config |
| @eslint/js | 9.17.0 | Règles ESLint recommandées |

> **React/Babel ne sont PAS dans le `package.json`** — chargés exclusivement via CDN unpkg (`react@18.3.1`, `react-dom@18.3.1`, `@babel/standalone@7.29.0`). Versions pinnées dans `public/index.html`.

#### 2.4.b Librairies ON-DEMAND (installées si l'US déclenche)

Triggers (regex case-insensitive) recherchés par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| anthropic-ai | @anthropic-ai/sdk | 0.40.1 | \\bclaude\\b, anthropic, reformulation.*ia, explain.*ia |
| jwt | @fastify/jwt | 9.0.1 | \\bjwt\\b, auth-local, auth-azure-ad |
| auth-local | bcryptjs | 2.4.3 | auth-local, hash.*password, bcrypt |
| prisma | prisma | 6.1.0 | prisma, orm, database.*scaffold, db-first |
| prisma | @prisma/client | 6.1.0 | prisma, orm |
| websocket | @fastify/websocket | 11.0.1 | websocket, ws, realtime.*bidirectional |
| http-client | undici | 7.2.0 | appel.*api.*externe, http-client, fetch.*backend |
| markdown | marked | 14.1.4 | markdown.*render, \\bmd\\b.*rendu, \\bmarked\\b |
| date-utils | dayjs | 1.11.13 | dates.*format, duree, intervalle.*temps |
| file-upload | @fastify/multipart | 9.0.1 | upload.*fichier, multipart, form-data |
| excel | exceljs | 4.4.0 | \\bexcel\\b, \\.xlsx\\b, export.*excel |
| pdf | pdfkit | 0.15.2 | \\bpdf\\b, \\.pdf\\b, export.*pdf |
| smtp | nodemailer | 6.9.16 | email, smtp, envoi.*mail, notification.*mail |
| smtp | @types/nodemailer | 6.4.17 | email, smtp |
| compression | @fastify/compress | 8.0.1 | compression, gzip, brotli |
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

## 6. Persistance (mode file-based par défaut)

Quand `DatabaseType: none` dans `## Active Database`, le stack utilise un **file-based JSON store** avec écriture atomique + lock (pattern `workspace/console/lib/atomic-write.js`).

### 6.1 Layout

```
workspace/output/src/{AppName}/
├── data/
│   ├── status.json        ← état applicatif principal
│   ├── users.json         ← (si auth-local)
│   └── .locks/            ← fichiers de lock atomic-write (gitignored)
```

### 6.2 Pattern atomic write

```js
// lib/atomic-write.js
import { writeFile, rename } from 'node:fs/promises';
import { join } from 'node:path';

export async function withLockedWrite(file, mutator, agent) {
  const lockFile = join(file + '.lock');
  // 1. Acquire lock (O_EXCL, retry, stale > 10s écrasé)
  // 2. Read current → JSON.parse
  // 3. Apply mutator(current) → new
  // 4. Write new à `${file}.tmp`
  // 5. fs.rename(`${file}.tmp`, file)  ← atomique
  // 6. Release lock
  return updated;
}
```

### 6.3 Mode DB (opt-in capability `prisma`)

Pattern identique à `node-express.md §8` : `prisma db pull` introspection + driver selon `DatabaseType`. Cas d'usage : projet qui dépasse ~10k lignes de données, ou requêtes complexes.

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
| `fullstack-node-react` + `auth-local` + `qa-node-vitest` + `SqlServer` (Prisma) | 🟡 experimental | jamais validé end-to-end |
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

Phase B (DB scaffolding) : invoquée uniquement si `DatabaseType ≠ none` ET capability `prisma` détectée. Sinon skip silencieux.

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
