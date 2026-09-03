# Tech FEAT: nuxt (fullstack)

Status: Experimental
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCNuxt :44369, sur la 3.15.0 de Nuxt + Nitro 2.13.4 + Vite 7 + Vue 3.5, Server Routes `server/api/calc.post.ts` REST-like via `$fetch`, startup Nitro 1059ms + Vite 39ms, POST 5ms, AC-1/2/3 🟢 bug-free (out-of-the-box). Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`. Note : bench original mentionnait une preview Nuxt 4.x mais le pin canonique `.libs.json` reste sur Nuxt 3 LTS — la branche 4 en preview au moment du bench, exclue de CORE par policy runtime LTS only. **MAJ 2026-09-02** : la branche 4 est désormais stable (4.5.2), ce qui lève la raison d'origine — mais le pin reste sur la ligne 3 (`3.21.11`), une montée de majeure invalidant ce bench. Tâche dédiée, cf. §2.3)
Tech FEAT ID: tech-nuxt
Scope: **fullstack monolithe** — application Nuxt 3 dans UN seul projet `{AppName}/`. UI (Vue 3 SFC server-rendered + client-hydrated) + server routes (Nitro `server/api/`) + middleware + auth vivent dans le meme processus Node.js. Pas de separation `{BackendName}` / `{AppName}` / `{LibName}`. Modele **SSR vrai** : HTML pre-rendu serveur par defaut, hydratation universelle cote client.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application fullstack monolithique Nuxt 3 / Nitro**. Un seul projet `{AppName}/` qui :

- Sert les **pages Vue SFC** (`pages/`) — file-based routing, rendus SSR par defaut
- Sert les **server routes Nitro** (`server/api/{route}.ts`) — endpoints REST + serverless-ready (Vercel/Netlify/Cloudflare Workers compatible)
- Expose des **server middleware** (`server/middleware/`) — auth, CORS, security headers
- Gere les **composables** (`composables/`) — logique reactive partagee cote client (hooks Vue)
- Gere l'**auth** via `@sidebase/nuxt-auth` (NextAuth-like pour Nuxt) ou MSAL pour Azure AD

Architecture cible :

```
Browser
  ├── HTML SSR (Vue components rendus serveur)
  └── JS bundle (Vue hydration + interactivite)
       │
       ▼
Nuxt 3 + Nitro (Node 22)
  ├── pages/                     ── file-based routing Vue
  ├── components/                ── Vue SFC components (auto-import)
  ├── composables/               ── hooks reactifs (useFetch, useState…)
  ├── server/
  │   ├── api/*.ts              ── REST endpoints Nitro
  │   ├── routes/*.ts           ── routes serveur custom (SSE, webhooks)
  │   ├── middleware/*.ts       ── server middleware
  │   └── utils/                ── helpers serveur (DB, auth)
  ├── server/services/           ── logique metier
  └── plugins/                   ── plugins Nuxt (cote client + cote serveur)
```

**Difference vs combo `node-express` × `vue`** :
- Un seul projet, un seul `package.json`, un seul `nuxt.config.ts`
- **Pas de CORS** (meme origine)
- **Pas d'`{LibName}` separe** — types partages via simple `import` (auto-import Nuxt sur `types/`, `utils/`, `composables/`)
- **Build step obligatoire** (`nuxt build`) — Nitro + Vite
- **Bundler integre** Vite — jamais a configurer manuellement

---

## 1.2 Couches

- **Pages** (`pages/`) : Vue SFC + file-based routing. SSR par defaut (`<script setup>`). Layout via `definePageMeta({ layout: 'default' })`.
- **Layouts** (`layouts/`) : wrappers reutilisables (header/sidebar/footer)
- **Components** (`components/`) : Vue SFC reutilisables, auto-importes
- **Composables** (`composables/`) : hooks reactifs cote client (`useUserSession`, `useCart`…), auto-importes
- **Server API** (`server/api/{route}.ts`) : endpoints REST type Nitro (`defineEventHandler` exports)
- **Server Routes** (`server/routes/`) : routes custom non-API (SSE stream, webhook avec path explicite)
- **Server Middleware** (`server/middleware/`) : pre-traitement requete (auth, CORS, logger)
- **Server Services** (`server/services/`) : logique metier pure, importable depuis API + middleware
- **Repositories** : Prisma ORM OU file-based JSON store (cf. §6)
- **Schemas Zod** : validation entree (body, query, params)
- **Plugins** (`plugins/`) : initialisation cote client OU cote serveur (i18n, theme, error handler)

> **Patterns Vue partages** (Pinia, VeeValidate, Composition API) : voir `.sdd/stacks/frontend/vue.md §1.1-§1.4` — **applicabilite partielle** : routing remplace par Nuxt file-based, fetching client remplace par `useFetch` / `useAsyncData` natifs Nuxt.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

| Layer | Path |
|---|---|
| Page | `pages/{segment}.vue` ou `pages/{segment}/index.vue` |
| Dynamic route | `pages/{segment}/[id].vue` |
| Layout | `layouts/{name}.vue` (defaut `default.vue`) |
| Component metier | `components/{Domain}/{Name}.vue` |
| Component UI Vuetify | `components/` (auto-import depuis `vuetify`) — cf. `.sdd/stacks/ui/vuetify.md` |
| Composable | `composables/use{Name}.ts` |
| Server API | `server/api/{domain}.{method}.ts` (e.g. `users.get.ts`, `users.post.ts`) |
| Server Route custom | `server/routes/{path}.ts` |
| Server Middleware | `server/middleware/{order-name}.ts` |
| Server Service | `server/services/{domain}.ts` |
| Server Repository | `server/repositories/{domain}.ts` |
| Server Utils | `server/utils/{name}.ts` (auto-import dans `server/`) |
| Schemas Zod | `shared/schemas/{domain}.ts` (partage client + serveur via `shared/`) |
| Auth | `server/utils/auth.ts` + `server/api/auth/[...].ts` |
| Plugins | `plugins/{name}.ts` (suffix `.client.ts` ou `.server.ts` pour cibler) |
| i18n | `i18n.config.ts` + `locales/{locale}.json` |
| Static assets | `public/` (servi a la racine) |
| Public images | `assets/` (transformees par Vite, hash, optimisees) |
| Prisma schema | `prisma/schema.prisma` |
| Global CSS | `assets/css/main.css` |

**Manifestes** :
- Project file → `workspace/src/{AppName}/package.json`
- Nuxt config → `workspace/src/{AppName}/nuxt.config.ts`
- TS config → genere automatiquement par Nuxt (`.nuxt/tsconfig.json`) + override dans `tsconfig.json` racine
- ESLint → `workspace/src/{AppName}/eslint.config.mjs` (`@nuxt/eslint`)
- App entry → `workspace/src/{AppName}/app.vue` (root component avec `<NuxtLayout>` + `<NuxtPage>`)

---

## 1.4 Principes non negociables

**Architecture Nuxt** :
- **Defaut = SSR universel** — toute page rendue serveur puis hydratee cote client. Pour purement statique : `routeRules: { '/blog/**': { prerender: true } }`. Pour purement client : `definePageMeta({ ssr: false })` (rare).
- **`useFetch` / `useAsyncData`** pour le data fetching dans les pages (gere SSR + hydration sans double-fetch)
- **`$fetch`** pour les appels imperatifs (event handlers, composables purs)
- **Aucune logique metier dans `server/api/*.ts`** — deleguer a un Service de `server/services/`
- **Validation Zod obligatoire** sur tout body / query / params via `await readValidatedBody(event, schema.parse)`
- **`useState` SSR-safe** pour partager de l'etat reactif entre composants (jamais `ref()` global qui fuit entre requetes serveur)
- **Composables `useXxx`** : suffix obligatoire (`useUserSession`, `useCart`), auto-importes
- **TypeScript strict** dans `tsconfig.json` (Nuxt 3 active strict par defaut)

**Patterns Vue partages** : SOLID + Clean Code identiques a `.sdd/stacks/frontend/vue.md §1.4`. Specificites Nuxt :
- Pas de `vue-router` (Nuxt file-based)
- Pas de `vite-plugin-vue-devtools` configuration manuelle (integre)
- Auto-import : `ref`, `computed`, `watch`, `useFetch`, composants, composables disponibles sans `import`

**Securite** :
- **`runtimeConfig`** dans `nuxt.config.ts` pour separer **public** (expose au client) vs **private** (server only). Les secrets vivent dans `runtimeConfig.{key}` peuple par `arch` depuis `stack.md`, JAMAIS dans `runtimeConfig.public.{key}` ni dans `process.env.NUXT_*` lu par le code applicatif.
- **CSP** via `nuxt-security` module (capability `security-headers`)
- **Cookies auth** : `httpOnly` + `secure` (prod) + `sameSite: 'lax'` (gere par `@sidebase/nuxt-auth`)

---

## 1.5 Couches persistantes

Patterns reconnus : `Entity`, `Entities`, `Repository`, `Repositories`, `Migration`, `Migrations`. Pattern Prisma identique a `.sdd/stacks/backend/node-express.md §8`.

**Mode par defaut** : file-based JSON store, pattern identique a `node-react.md §6.2`. Bonus Nitro : utiliser `useStorage('data')` (Nitro KV abstraction) pour persistance compatible Cloudflare KV / Vercel KV / Redis sans changer le code.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-nuxt`
- **Langage** : TypeScript 5.x strict
- **Runtime serveur** : Node.js 22 LTS (deployable serverless via Nitro presets)
- **Framework** : Nuxt **3.21.x** (pin `3.21.11`, Nitro engine) — ligne 3 maintenue, cf. §2.3
- **UI lib** : Vue 3.5
- **UI Design System** : Vuetify 3.13 (defaut) — cf. `.sdd/stacks/ui/vuetify.md`. Alternative : Nuxt UI 3 (capability `nuxt-ui`).
- **Styling** : Vuetify themes OU Tailwind v4 si capability `tailwind` declaree
- **Namespace** : `{AppNamespace}` (utilise dans imports `~/components/...`)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/package.json`
- **Build** : `(cd workspace/src/{AppName} && npm run build)` → `nuxt build`
- **Dev** : `(cd workspace/src/{AppName} && npm run dev)` → `nuxt dev` (HMR Vite)
- **Generate** (SSG) : `npm run generate` → `nuxt generate` (output statique pour CDN)
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && npm install --silent && npm run build)
test -d workspace/src/{AppName}/.output
```

- **Smoke Timeout** : 180s
- **Package manager** : npm
- **Type-check** : `nuxt typecheck` (invoque `vue-tsc`)
- **Lint** : `nuxt lint` (`@nuxt/eslint`)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/package.json" ]; then

# STEP 1 — Bootstrap Nuxt 3
npx --yes nuxi@latest init workspace/src/{AppName} --packageManager npm --gitInit false --no-install
cd workspace/src/{AppName}
npm install --silent

# STEP 2 — Installer Vuetify module (UI defaut) — cf. .sdd/stacks/ui/vuetify.md §2.2.1
npx --yes nuxi@latest module add vuetify-nuxt-module

# STEP 3 — Installer libs CORE (cf. §2.4)
npm install \
  zod@3.24.0 \
  vee-validate@4.14.7 \
  @vee-validate/zod@4.14.7 \
  pinia@2.3.0 \
  @pinia/nuxt@0.9.0 \
  @sidebase/nuxt-auth@0.10.0 \
  @nuxtjs/i18n@9.1.0 \
  pino@9.5.0 \
  pino-pretty@13.0.0

# STEP 4 — Modules Nuxt (a ajouter dans nuxt.config.ts)
npx --yes nuxi@latest module add @pinia/nuxt
npx --yes nuxi@latest module add @nuxtjs/i18n
npx --yes nuxi@latest module add @sidebase/nuxt-auth
npx --yes nuxi@latest module add @nuxt/eslint

# STEP 5 — Creer arborescence applicative
mkdir -p \
  pages \
  layouts \
  components \
  composables \
  server/api \
  server/routes \
  server/middleware \
  server/config \
  server/services \
  server/repositories \
  server/utils \
  shared/schemas \
  plugins \
  locales \
  data

# STEP 6 — Bootstrap runtimeConfig prive (rempli par arch depuis stack.md)
cat > server/config/app-config.ts <<'TS'
export const appConfig = {
  authSecret: "",
  databaseUrl: "",
  azureAd: {
    tenantId: "",
    clientId: "",
  },
} as const;
TS

fi
```

---

## 2.3 Politique de version — audit 2026-09-02

Ce stack porte un badge **🟢 bench-validated** : sa validation repose sur un run
runtime daté, exécuté sur une version précise. La règle appliquée à tout le
catalogue lors de cet audit :

| Type de bump | Décision |
|---|---|
| **Patch / minor dans la majeure en place** | appliqué |
| **Majeure** | **non appliqué** — documenté ici, tâche dédiée avec re-bench |

### Ce qui a été bumpé

`nuxt` **3.15.0 → 3.21.11** (dernier patch de la ligne 3), `vuetify` 3.13.3
(ligne 3, aligné sur `ui/vuetify.md`), `pinia` 2.3.1, plus les dépendances
hors framework.

### Ce qui n'a PAS été bumpé

**La 4.5.2 de Nuxt est stable.** L'en-tête `Validation:` de ce stack documentait
déjà un pin volontaire sur la ligne 3 : *« la branche 4 en preview au moment
du bench, exclue de CORE par policy runtime LTS only »*. Cette raison
d'origine **est levée** — la branche 4 n'est plus en preview. Mais le pin
reste, pour l'autre raison : le bench a tourné sur la ligne 3, et Nuxt 4
change la structure de répertoires par défaut (`app/`), la résolution des
imports auto et le comportement de Nitro. Montée = tâche dédiée avec re-bench.

### Correction obligatoire, sans rapport avec les majeures

`nuxt-ui` était pinné en **`3.0.0-alpha.10`** — une **préversion**, interdite
par `rules/library-and-stack.md §5`. C'était le second WARN `PRERELEASE` du
catalogue. La ligne 4 est désormais **stable** : pin **4.11.0**.

> **Piège de registre sur `vuetify-nuxt-module`** : son dist-tag npm `latest`
> pointe sur **`1.0.0-rc.5`**, une préversion. La dernière **stable** est la
> **0.19.5** — c'est elle qui est pinnée. Ne pas « bumper vers latest » sur ce
> paquet sans lire ses dist-tags, sous peine de réintroduire une préversion.

> Le raisonnement complet est développé une fois dans
> `backend/kotlin-spring-boot.md §2.3.1`. Les stacks 🟢 concernés par le même
> arbitrage : `backend/kotlin-spring-boot` (Spring Boot 3.5.x vs 4.1.1),
> `backend/node-express` (Express 4.x vs 5.2.1), `fullstack/kotlin-mustache`,
> `fullstack/next`, `fullstack/nuxt`, `fullstack/angular-universal`.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/fullstack/nuxt.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id nuxt`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| nuxt | 3.21.11 | Framework SSR + Nitro |
| vue | 3.5.42 |  |
| vuetify | 3.13.3 | Design System defaut |
| vuetify-nuxt-module | 0.19.5 | Integration Nuxt + Vuetify SSR-ready |
| typescript | 5.9.3 |  |
| zod | 4.5.4 | Validation schemas |
| vee-validate | 4.15.1 | Forms validation Vue-idiomatic |
| @vee-validate/zod | 4.15.1 |  |
| pinia | 2.3.1 | State store client |
| @pinia/nuxt | 0.11.3 |  |
| @sidebase/nuxt-auth | 0.10.0 | Auth (NextAuth-like pour Nuxt) |
| @nuxtjs/i18n | 9.5.6 |  |
| @nuxt/eslint | 0.7.6 |  |
| pino | 10.3.1 |  |
| pino-pretty | 13.1.3 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| prisma | prisma | 7.10.0 | DatabaseType.*\b(SqlServer|PostgreSql|MySql|Sqlite)\b, orm, db-first |
| prisma | @prisma/client | 7.10.0 | prisma, orm |
| tailwind | @nuxtjs/tailwindcss | 6.14.0 | tailwind, atomic.*css |
| nuxt-ui | @nuxt/ui (alt) | 4.11.0 | nuxt-ui, ui-kit-nuxt |
| auth-azure-ad | @azure/msal-node | 3.8.10 | auth-azure-ad, msal |
| http-client | ofetch | 1.5.1 | appel.*api.*externe |
| excel | exceljs | 4.4.0 | \bexcel\b, \.xlsx\b, export.*excel |
| pdf | pdfkit | 0.20.2 | \bpdf\b, export.*pdf |
| smtp | nodemailer | 6.10.1 | email, smtp |
| date-utils | @vueuse/core | 12.8.2 | date, time, utils.*reactive |
| security-headers | nuxt-security | 2.6.0 | csp, security.*headers, helmet |
| analytics | nuxt-gtag | 3.0.3 | analytics, google.*tag |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Role | Pattern | Exemple |
|------|---------|---------|
| Page | `pages/{segment}.vue` ou `pages/{segment}/index.vue` | `pages/dashboard.vue` |
| Page dynamique | `pages/{segment}/[id].vue` | `pages/users/[id].vue` |
| Layout | `layouts/{name}.vue` | `layouts/default.vue`, `layouts/admin.vue` |
| Component | `components/{Domain}/{Name}.vue` (PascalCase fichier) | `components/User/UserCard.vue` |
| Composable | `composables/use{Name}.ts` | `composables/useUserSession.ts` |
| Server API | `server/api/{domain}.{method}.ts` | `server/api/users.get.ts`, `users.post.ts` |
| Server Route | `server/routes/{path}.ts` | `server/routes/events.ts` (SSE) |
| Server Middleware | `server/middleware/{order}-{name}.ts` | `server/middleware/01-auth.ts` |
| Server Service | `server/services/{domain}Service.ts` | `usersService.ts` |
| Zod schema | `shared/schemas/{domain}.ts` exportant `{Domain}{Action}Schema` | `UserCreateSchema` |

**Suffixes INTERDITS** :
- `.controller.ts` (server file-based)
- `Dto`, `Request`, `Response` — utiliser Zod schemas + types inferes
- `Util`, `Helper`, `Manager` (sauf `server/utils/`)

---

## 3. Endpoints standard (obligatoires)

| Endpoint | Auth | Role |
|----------|------|------|
| `GET /` | non | Page accueil Vue SSR |
| `GET /api/health` | non | `{ ok: true, app, version }` |
| `GET /api/auth/[...]` | non | nuxt-auth callbacks |

Pas de Swagger par defaut — capability `public-api` ajoute `nuxt-openapi-docs-module`.

---

## 4. Versioning des API

`server/api/v1/{domain}.{method}.ts`. Obligatoire si API consommee par client tiers. Optionnel si seul l'UI Nuxt consomme.

---

## 5. Interdits projet (nuxt)

**Architecture** :
- Lecture DB / secret dans un composable cote client (`composables/`) — toujours via `server/services/`
- `ref()` au top-level d'un module serveur (fuit l'etat entre requetes SSR) — utiliser `useState` ou DI
- Logique metier dans `server/api/*.ts` — deleguer a `server/services/`
- `useFetch` avec une URL externe HTTPS sans `{ server: false }` — peut leak token cote client (SSR fetch fait avec headers utilisateur)
- Composable qui appelle directement Prisma — Prisma est server-only, utiliser `$fetch('/api/...')` ou Server Action equivalente
- `runtimeConfig.public.*` qui contient un secret (expose au client !)

**Code quality** :
- `console.log` → `pino` (serveur) ou `useLogger` composable client
- `any` injustifie
- Imports relatifs profonds — utiliser alias `~/components/...` (auto-configure Nuxt)

**Securite** :
- Hardcoded secrets hors `runtimeConfig` prive peuple par `arch` depuis `stack.md`
- Path traversal non protege
- CORS `*` (mais inutile en Nuxt fullstack, meme origine)
- Cookies sans flags secure/httpOnly/sameSite

**Bundle** :
- Import lib serveur (Prisma, fs, …) dans `composables/` ou `components/` → casse le build Vite cote client
- Engager `.output/`, `.nuxt/`, `node_modules/` ou un fichier de config locale contenant des secrets dans git

---

## 6. Persistance

- **File-based JSON** (default si `DatabaseType: none`) : utiliser `useStorage('data')` Nitro KV ou pattern atomic write de `node-react.md §6.2`
- **Prisma** (capability `prisma`) : pattern identique a `.sdd/stacks/backend/node-express.md §8.3`
- **DATABASE_URL** lue depuis `runtimeConfig.databaseUrl` (valeur materialisee par `arch` depuis `## Active Database`, pas depuis `process.env.NUXT_DATABASE_URL`)

---

## 7. Temps reel

- **SSE** : `server/routes/events.ts` avec `sendStream` (h3 helper) :

```ts
// server/routes/events.ts
export default defineEventHandler(async (event) => {
  setResponseHeader(event, 'Content-Type', 'text/event-stream');
  setResponseHeader(event, 'Cache-Control', 'no-cache');
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const interval = setInterval(() => controller.enqueue(encoder.encode(': ping\n\n')), 25_000);
    },
  });
  return sendStream(event, stream);
});
```

- **WebSocket** : Nitro experimental `experimental: { websocket: true }` dans `nuxt.config.ts` + `server/routes/_ws.ts`. Capability `websocket`.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Apps Vue-first** orientees SEO (e-commerce, blog, marketing)
- **Equipes Vue** qui veulent SSR + serverless deploy (Vercel, Netlify, Cloudflare Pages)
- **MVP** avec besoin SSG hybride (`nuxt generate` produit du statique deployable CDN)

**NE PAS choisir si** :
- ❌ Equipe React-only → `next.md`
- ❌ Pas besoin de SSR (back-office interne) → `node-react.md` ou `frontend/vue.md` + `backend/node-express.md`
- ❌ Backend lourd avec orchestrations complexes → `backend/node-express.md` + `frontend/vue.md`
- ❌ WebSocket bidirectionnel intensif → Nuxt experimental, preferer Socket.IO process dedie

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-nuxt` + `vuetify` + `auth-local` + `qa-node-vitest` + `PostgreSql` (Prisma) | 🟡 experimental | jamais valide end-to-end |
| `fullstack-nuxt` + `nuxt-ui` + `auth-azure-ad` + `qa-node-vitest` + `SqlServer` | 🟡 experimental | viable mais non valide |
| `fullstack-nuxt` + `vuetify` + `auth-local` + `qa-node-vitest` + `none` (Nitro KV) | 🟡 experimental | prototypes seulement |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` = `fullstack/nuxt.md` → **ignorer** `BackendName` et `LibName`
2. **Creer** UN seul projet via `nuxi init` (cf. §2.2.1)
3. **Composer** `server/config/app-config.ts` + `runtimeConfig` depuis `## Active Database` + `## Active Auth Specs` :
   - `databaseUrl` (si Prisma)
   - `authSecret` (depuis `AUTH_JWT_SECRET`)
   - `azureAd.tenantId`, `azureAd.clientId` (si auth-azure-ad)
4. **`## Active UI Specs`** : `vuetify` (defaut), `nuxt-ui` (alternative via capability). `shadcn` → WARNING (composants React, incompatibles Vue). `radzen-blazor` → WARNING bloquant
5. **Phase B (DB scaffolding)** : meme procedure que `node-express.md §8.3`
6. **Phase C (ADRs)** : creer `ADR-{ts}-stack-fullstack-nuxt.md` documentant Nuxt 3 + Nitro + Vuetify

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : stack lu par **les deux agents** dev-*.

**Convention de repartition** :

- `dev-backend` materialise : `server/api/`, `server/routes/`, `server/middleware/`, `server/services/`, `server/repositories/`, `server/utils/`, `prisma/schema.prisma`, `shared/schemas/`
- `dev-frontend` materialise : `pages/`, `layouts/`, `components/`, `composables/`, `plugins/`, `app.vue`, `assets/css/`

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/pages/**` | `dev-frontend` |
| `workspace/src/{AppName}/layouts/**` | `dev-frontend` |
| `workspace/src/{AppName}/components/**` | `dev-frontend` |
| `workspace/src/{AppName}/composables/**` | `dev-frontend` |
| `workspace/src/{AppName}/plugins/**` | `dev-frontend` |
| `workspace/src/{AppName}/app.vue` | `dev-frontend` |
| `workspace/src/{AppName}/server/**` | `dev-backend` |
| `workspace/src/{AppName}/shared/schemas/**` | `dev-backend` (Zod, partages) |
| `workspace/src/{AppName}/nuxt.config.ts` | `arch` (create) + `dev-backend` (augment modules) + `dev-frontend` (augment css/components.dirs) |
| `workspace/src/{AppName}/prisma/**` | `arch` (create) + `dev-backend` (consommation) |
| `workspace/src/{AppName}/server/config/app-config.ts` | `arch` (create exclusif — secrets/config SDD) |

**Cas frontiere `nuxt.config.ts`** : touche par les 2 agents (modules cote backend, css/components cote frontend). Utiliser **lock** equivalent LibName cf. `build-and-loop.md §2 (Partie B)`, ou serialiser dans le pipeline.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}
npm install --silent
test -f nuxt.config.ts
test -f app.vue
test -d server
test -d pages
grep -q "nuxt.*3" package.json
echo "smoke OK"
```

Smoke complet (~120s) : `npm run build` doit produire `.output/server/index.mjs`.
