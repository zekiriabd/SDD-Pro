# Tech FEAT: next (fullstack)

Status: Experimental
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCNextJS :44359, Next 15 App Router + Server Components + Server Actions `'use server'`, Zod inline + RHF côté client, startup 2.6s, GET / 200 13363 bytes (compile JIT 3.2s 1ère req), AC-1/2/3 🟢. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-next
Scope: **fullstack monolithe** — application Next.js 15 (App Router) dans UN seul projet `{AppName}/`. UI (React Server Components + Client Components) + API routes + Server Actions + auth vivent dans le meme processus Node.js. Pas de separation `{BackendName}` / `{AppName}` / `{LibName}`. Modele **SSR vrai** : HTML pre-rendu serveur par defaut, hydratation selective cote client.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application fullstack monolithique Next.js**. Un seul projet `{AppName}/` qui :

- Sert les **React Server Components** (RSC, defaut Next 13+) — rendus exclusivement cote serveur, jamais envoyes au browser en tant que JS
- Sert les **Client Components** (`'use client'`) — hydrates cote browser pour interactivite
- Expose des **Route Handlers** (`app/api/{route}/route.ts`) — endpoints REST classiques
- Expose des **Server Actions** (`'use server'`) — fonctions async appelees directement depuis les composants client, alternative type-safe a fetch+API route
- Gere l'**auth** via NextAuth.js (defaut) ou MSAL (Azure AD)

Architecture cible :

```
Browser
  ├── HTML SSR (Server Components)  ── pre-rendu serveur
  └── JS bundle (Client Components) ── hydratation selective
       │
       ▼
Next.js 15 (Node 22)
  ├── App Router (file-based)
  │   ├── app/page.tsx          ── Server Component (defaut)
  │   ├── app/*/page.tsx        ── routes pages
  │   ├── app/api/*/route.ts    ── REST endpoints
  │   └── app/actions/*.ts      ── Server Actions ('use server')
  ├── Services (lib/server/)    ── logique metier
  ├── Repositories              ── Prisma OU file-based JSON
  └── Middleware (middleware.ts) ── auth gate, i18n, headers
```

**Difference vs combo `node-express` × `react`** :
- Ici **un seul projet**, un seul `package.json`, un seul `next.config.js`
- **Pas de CORS** (meme origine pour API et UI)
- **Pas d'`{LibName}` separe** — types partages via simple `import` cross-folder
- **Build step obligatoire** (`next build`) — contrairement a `node-react.md` (Babel-in-browser)
- **Bundler integre** — Turbopack / Webpack 5 derriere `next` (jamais a configurer manuellement)

---

## 1.2 Couches

- **Server Components** (RSC) : composants async qui rendent serveur uniquement (lecture DB, secrets, gros payloads). Defaut Next.js App Router.
- **Client Components** (`'use client'`) : interactivite (forms, useState, event handlers). Hydrates cote browser.
- **Route Handlers** : endpoints REST type Fastify (`route.ts` avec `GET`/`POST`/`PUT`/`DELETE` exports)
- **Server Actions** : fonctions async appelees depuis Client Components (form actions, mutations) — alternative a `fetch('/api/...')`
- **Services** : logique metier pure, importable depuis Server Components ET Route Handlers (`lib/server/services/`)
- **Repositories** : I/O Prisma OU file-based JSON store (cf. §6)
- **Schemas Zod** : validation entree (body / formData / searchParams)
- **Middleware** : `middleware.ts` racine — auth gate, i18n, security headers
- **Layouts** : `layout.tsx` par segment (header/sidebar/footer composables via slots)
- **Loading / Error UI** : `loading.tsx`, `error.tsx`, `not-found.tsx` par segment

> **Patterns React partages** (forms, hooks, query) : voir `.claude/stacks/frontend/react.md §1.1-§1.4` — **applicabilite limitee** : TanStack Query est inutile pour les Server Components (utiliser `async/await` direct dans le composant), TanStack Router est remplace par App Router file-based.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

**Code applicatif** (sous `workspace/output/src/{AppName}/`) :

| Layer | Path |
|---|---|
| Root layout | `app/layout.tsx` (HTML wrapper global) |
| Page route | `app/{segment}/page.tsx` (Server Component par defaut) |
| Client component | `app/{segment}/{Component}.client.tsx` ou marque par `'use client'` directive |
| Route Handler (API) | `app/api/{domain}/route.ts` (exports GET/POST/PUT/DELETE) |
| Server Action | `app/actions/{domain}.ts` (top-level `'use server'`) |
| Layout segment | `app/{segment}/layout.tsx` |
| Loading | `app/{segment}/loading.tsx` |
| Error boundary | `app/{segment}/error.tsx` |
| Middleware racine | `middleware.ts` |
| Services metier | `lib/server/services/{domain}.ts` |
| Repositories | `lib/server/repositories/{domain}.ts` |
| Schemas Zod | `lib/schemas/{domain}.ts` (partage server + client) |
| Auth | `lib/server/auth.ts` (NextAuth config) + `app/api/auth/[...nextauth]/route.ts` |
| Lib helpers (cn, dates) | `lib/utils.ts` |
| Components shadcn UI | `components/ui/` (genere par `npx shadcn@latest add`) |
| Components metier | `components/{Domain}/` |
| i18n | `lib/i18n/` + `messages/{locale}.json` (next-intl) |
| Static assets | `public/` (servi a la racine) |
| Prisma schema | `prisma/schema.prisma` |
| Global CSS | `app/globals.css` (Tailwind v4 `@import "tailwindcss";`) |

**Manifestes** :
- Project file → `workspace/output/src/{AppName}/package.json`
- Next config → `workspace/output/src/{AppName}/next.config.mjs`
- TS config → `workspace/output/src/{AppName}/tsconfig.json`
- Tailwind v4 → directement dans `globals.css` (`@theme` block)
- shadcn manifest → `workspace/output/src/{AppName}/components.json`
- ESLint → `workspace/output/src/{AppName}/eslint.config.mjs`

---

## 1.4 Principes non negociables

**Architecture App Router** :
- **Defaut = Server Component** — `'use client'` UNIQUEMENT pour composants qui ont besoin de `useState`, `useEffect`, event handlers, refs DOM, hooks navigateur
- **Aucune lecture DB / secrets** dans un Client Component — passer par Server Component ou Server Action
- **Aucune logique metier dans `route.ts`** — deleguer a un Service de `lib/server/services/`
- **Server Actions** preferees aux Route Handlers pour les mutations declenchees depuis l'UI (form submit, button click) — type-safe end-to-end, pas de fetch+JSON+revalidation manuelle
- **Route Handlers** reserves aux : webhooks externes, endpoints REST consommes par mobile, exports binaires (PDF/Excel), public API
- **Validation Zod obligatoire** sur tout body / formData / searchParams — pas de `if (!body.x) throw...`
- **`fetch()` cache strategy explicite** dans les Server Components : `{ cache: 'no-store' }` pour temps reel, `{ next: { revalidate: 60 } }` pour cache ISR
- **TypeScript strict** (`"strict": true`, `"noUncheckedIndexedAccess": true`)

**Patterns React partages** : SOLID + Clean Code identiques a `.claude/stacks/frontend/react.md §1.4`. Specificites Next.js :
- Pas de `react-router` (App Router file-based)
- Pas de `react-query` cote Server Components (utiliser `async/await` direct)
- `useFormState` / `useFormStatus` pour les Server Actions

**Securite** :
- **Aucune env var sensible exposee a `NEXT_PUBLIC_*`** (preface qui rend la var visible cote client — RESERVEE aux configs non sensibles, jamais a JWT/API key)
- **CSP strict** dans `next.config.mjs` (`headers()`) — pas de `'unsafe-inline'` sauf nonce dynamique
- **Cookies auth** : `httpOnly` + `secure` (prod) + `sameSite: 'lax'` minimum (gere par NextAuth par defaut)

---

## 1.5 Couches persistantes

Patterns reconnus (declenche `DB_REQUIRED` si `DatabaseType ≠ none`) : `Entity`, `Entities`, `Repository`, `Repositories`, `Migration`, `Migrations`. Pattern identique a `.claude/stacks/backend/node-express.md §8` — Prisma 6 + driver selon `DatabaseType`.

**Mode par defaut** : file-based JSON store (`data/*.json`) avec atomic write + lock — pattern identique a `node-react.md §6.2`.

---

## 1.6 Server Actions vs Route Handlers — matrice de decision

| Cas d'usage | Choix | Raison |
|---|---|---|
| Form submit depuis Client Component (CRUD) | **Server Action** | Type-safe end-to-end, validation cote serveur, revalidation auto via `revalidatePath`/`revalidateTag` |
| Webhook externe (Stripe, GitHub, etc.) | **Route Handler** | URL stable, signature verification, pas d'origine Next |
| Export binaire (PDF, Excel, CSV download) | **Route Handler** | `Response` avec `Content-Type` custom + `Content-Disposition` |
| API consommee par mobile / partenaire tiers | **Route Handler** | Contrat REST stable, OpenAPI documentable |
| SSE / streaming | **Route Handler** | `Response` avec `ReadableStream` |
| Mutation declenchee depuis Server Component | **Server Action importee** | Pas de fetch, appel direct |
| Lecture (read) | **Server Component** | Lecture directe via service, pas besoin de Route Handler du tout |

**Anti-pattern majeur** : creer un Route Handler `POST /api/create-x` consomme uniquement par un Client Component du meme projet → c'est une Server Action deguisee, en moins type-safe. Utiliser Server Actions.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-next`
- **Langage** : TypeScript 5.x strict
- **Runtime serveur** : Node.js 22 LTS
- **Framework** : Next.js 15.x (App Router)
- **UI** : React 19 + shadcn/ui (cf. `.claude/stacks/ui/shadcn.md`)
- **Styling** : Tailwind CSS v4
- **Namespace** : `{AppNamespace}` (utilise dans path alias `@/*`)

---

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Build** : `(cd workspace/output/src/{AppName} && npm run build)` — invoque `next build` (RSC + bundling + type-check + lint)
- **Dev** : `(cd workspace/output/src/{AppName} && npm run dev)` — Turbopack
- **Start** : `(cd workspace/output/src/{AppName} && npm start)` — `next start`
- **Smoke Command** :

```bash
(cd workspace/output/src/{AppName} && npm install --silent && npm run build)
test -d workspace/output/src/{AppName}/.next
```

- **Smoke Timeout** : 180s (Next.js build inclut RSC compilation + bundling)
- **Package manager** : npm
- **Type-check** : integre a `next build`
- **Lint** : `next lint` (ESLint flat config)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/output/src/{AppName}/package.json" ]; then

# STEP 1 — Bootstrap Next.js 15 (App Router + TS + Tailwind v4 + ESLint + path alias)
npx --yes create-next-app@15 workspace/output/src/{AppName} \
  --ts --app --tailwind --eslint --src-dir false \
  --import-alias "@/*" --use-npm --no-turbopack --skip-install

cd workspace/output/src/{AppName}
npm install --silent

# STEP 2 — Installer shadcn/ui (style new-york) — reference .claude/stacks/ui/shadcn.md §2.2.1
npx --yes shadcn@latest init -d --style new-york --base-color slate

# STEP 3 — Installer libs CORE (cf. §2.4)
npm install \
  zod@3.24.0 \
  react-hook-form@7.54.2 \
  @hookform/resolvers@3.10.0 \
  next-auth@5.0.0-beta.25 \
  @next/env@15.1.0 \
  pino@9.5.0 \
  pino-pretty@13.0.0 \
  next-intl@3.26.0

# STEP 4 — Creer arborescence applicative
mkdir -p \
  app/api \
  app/actions \
  lib/server/services \
  lib/server/repositories \
  lib/schemas \
  components/ui \
  data \
  messages

# STEP 5 — Bootstrap config serveur par defaut (rempli par arch depuis stack.md)
cat > lib/server/config.ts <<'TS'
import 'server-only';

export const serverConfig = {
  databaseUrl: "",
  nextAuthSecret: "",
  nextAuthUrl: "http://localhost:3000",
  azureAd: {
    tenantId: "",
    clientId: "",
  },
} as const;
TS

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/fullstack/next.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id next`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| next | 15.1.0 | Framework App Router + RSC + Server Actions |
| react | 19.0.0 | UI lib compatible RSC |
| react-dom | 19.0.0 |  |
| @types/react | 19.0.2 |  |
| @types/react-dom | 19.0.2 |  |
| @types/node | 22.10.0 |  |
| typescript | 5.7.0 |  |
| tailwindcss | 4.0.0 |  |
| @tailwindcss/postcss | 4.0.0 |  |
| postcss | 8.5.0 |  |
| zod | 3.24.0 | Validation schemas (server + client) |
| react-hook-form | 7.54.2 |  |
| @hookform/resolvers | 3.10.0 |  |
| next-auth | 5.0.0-beta.25 | Auth (NextAuth v5 / Auth.js) |
| next-intl | 3.26.0 | i18n |
| pino | 9.5.0 |  |
| pino-pretty | 13.0.0 |  |
| eslint | 9.17.0 |  |
| eslint-config-next | 15.1.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| prisma | prisma | 6.1.0 | DatabaseType.*(SqlServer|PostgreSql|MySql|Sqlite), orm, db-first |
| prisma | @prisma/client | 6.1.0 | prisma, orm |
| auth-azure-ad | @azure/msal-node | 3.1.0 | auth-azure-ad, msal |
| jwt | jose | 5.9.6 | jwt, auth-local |
| http-client | undici | 7.2.0 | appel.*api.*externe, http-client |
| excel | exceljs | 4.4.0 | excel, \.xlsx, export.*excel |
| pdf | @react-pdf/renderer | 4.1.5 | pdf, export.*pdf |
| smtp | nodemailer | 6.9.16 | email, smtp, envoi.*mail |
| date-utils | date-fns | 4.1.0 | dates.*format, duree, intervalle.*temps |
| state-mgmt | zustand | 5.0.2 | global.*state, store, zustand |
| analytics | @vercel/analytics | 1.4.1 | analytics, telemetry.*ui |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — verifies par dev-* STEP 5.0. Toute violation = ERROR avant ecriture.

| Role | Pattern | Exemple |
|------|---------|---------|
| Page | `app/{segment}/page.tsx` (Server Component) | `app/dashboard/page.tsx` |
| Layout | `app/{segment}/layout.tsx` | `app/dashboard/layout.tsx` |
| Client Component | `{Component}.client.tsx` OU directive `'use client'` en tete | `Topbar.client.tsx` |
| Server Component | `{Component}.tsx` (sans directive `'use client'`) | `UserCard.tsx` |
| Route Handler | `app/api/{domain}/route.ts` (exports GET/POST/PUT/DELETE) | `app/api/users/route.ts` |
| Server Action | `app/actions/{domain}.ts` (top `'use server'`) ou inline dans Server Component | `app/actions/users.ts` |
| Service | `lib/server/services/{domain}.ts` exportant `{domain}Service` | `lib/server/services/users.ts` |
| Repository | `lib/server/repositories/{domain}.ts` | `lib/server/repositories/users.ts` |
| Zod schema | `lib/schemas/{domain}.ts` exportant `{Domain}{Action}Schema` | `UserCreateSchema` |

**Suffixes INTERDITS** :
- `.controller.ts` (App Router est file-based, pas de controller)
- `Dto`, `Request`, `Response` — utiliser `Schema` pour Zod, types inferes `z.infer<typeof Schema>`
- `Util`, `Helper`, `Manager` (sauf `lib/utils.ts` strict pour pure functions)

---

## 3. Endpoints standard (obligatoires)

| Endpoint | Auth | Role |
|----------|------|------|
| `GET /` | non | Page accueil (RSC) |
| `GET /api/health` | non | `{ ok: true, app, version }` (Route Handler) |
| `GET /api/auth/[...nextauth]` | non | NextAuth callback (si auth-local OU azure-ad) |

Pas de Swagger obligatoire par defaut (les Server Actions et RSC n'ont pas d'API publique). **Si capability `public-api`** est declaree → ajouter `next-swagger-doc` + Swagger UI sur `/api-docs`.

---

## 4. Versioning des API

Versioning par segment App Router : `app/api/v1/{domain}/route.ts`. **Obligatoire** si l'API est consommee par client tiers (mobile, partenaire). Optionnel si Server Actions only.

---

## 5. Interdits projet (next)

**Architecture** :
- Lecture DB directe dans un Client Component
- Secret / env var sensible expose via `NEXT_PUBLIC_*` (visible cote browser)
- `useState` / `useEffect` dans un Server Component (compile error mais a noter)
- `async` Client Component (compile error — RSC only peut etre async)
- Server Action declaree dans un fichier sans `'use server'`
- Route Handler qui appelle directement Prisma sans passer par un Service
- `fetch` sans `cache` strategy explicite dans un Server Component (defaut Next 15 = `no-store`, mais expliciter)
- `import 'server-only'` manquant dans un module qui contient secrets / DB queries (garde-fou anti-fuite client)

**Code quality** (heritages de `.claude/stacks/frontend/react.md §5`) :
- `console.log` → `pino` (server) ou structured log custom (client)
- `any` injustifie, `as unknown as T` double cast
- `@ts-ignore` sans justification
- `TODO`, `FIXME` dans le code livre
- Imports relatifs profonds — utiliser path alias `@/...`

**Securite** :
- CSP `unsafe-inline` sans nonce
- Cookies sans `httpOnly` + `secure` + `sameSite`
- Hardcoded secrets hors config serveur generee par `arch` depuis `stack.md`
- Validation manuelle a la place de Zod
- Path traversal non protege (resolve + scope check) dans les Route Handlers qui prennent un `path`

**Bundle** :
- Import d'une lib serveur dans un Client Component (alourdit le bundle JS)
- Pas de `'use server'` sur une fonction async destinee a etre appelee depuis le client
- Engager `.next/`, `node_modules/` ou un fichier de config locale contenant des secrets dans git

---

## 6. Persistance — voir patterns partages

- **File-based JSON** (default si `DatabaseType: none`) : pattern identique a `node-react.md §6.2` (atomic write + lock)
- **Prisma** (capability `prisma`) : pattern identique a `.claude/stacks/backend/node-express.md §8.3` (commandes scaffolding `prisma db pull`)
- **Connection string** : composee par arch depuis `## Active Database` et injectee dans `lib/server/config.ts` (server-only). Lecture cote code via `serverConfig.databaseUrl`, jamais via `process.env.DATABASE_URL`.

---

## 7. Temps reel

- **SSE** : Route Handler avec `ReadableStream`. Pattern :

```ts
// app/api/events/route.ts
export const dynamic = 'force-dynamic';
export async function GET() {
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      const interval = setInterval(() => {
        controller.enqueue(encoder.encode(': ping\n\n'));
      }, 25_000);
    },
  });
  return new Response(stream, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache, no-transform' },
  });
}
```

- **WebSocket** : Next.js n'expose pas nativement de WebSocket server. Capability `websocket` necessite : (a) deployer un process Node separe (Socket.IO), ou (b) Server externe (Pusher, Ably). Hors scope pour ce stack.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Apps SaaS B2C** orientees SEO (landing pages, marketing, blog)
- **Dashboards** avec mix de pages publiques et privees
- **MVP** rapide avec deploy Vercel / Netlify / Node container
- **Equipes** familieres React et qui veulent TypeScript end-to-end

**NE PAS choisir ce stack si** :
- ❌ Besoin **zero-build** (pas de CI/CD frontend) → `node-react.md`
- ❌ Backend lourd avec logique metier 80% > UI 20% → `backend/dotnet-minimalapi.md` + `frontend/react.md` (mieux scale)
- ❌ Multi-tenancy avec besoins fins de routing custom → Next.js middleware peut le faire mais devient complexe
- ❌ Vous voulez Vue / Angular cote client → `nuxt.md` / `angular-universal.md`
- ❌ App offline-first PWA avec service workers complexes → faisable mais Next n'est pas optimise pour
- ❌ Application desktop / mobile native → Tauri / Capacitor / React Native plutot

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-next` + `shadcn` + `auth-local` + `qa-node-vitest` + `PostgreSql` (Prisma) | 🟡 experimental | jamais valide end-to-end |
| `fullstack-next` + `shadcn` + `auth-azure-ad` + `qa-node-vitest` + `SqlServer` | 🟡 experimental | viable mais non valide |
| `fullstack-next` + `shadcn` + `auth-local` + `qa-node-vitest` + `none` (file-based) | 🟡 experimental | prototypes seulement |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` = `fullstack/next.md` → **ignorer** `BackendName` et `LibName` (WARNING `[STACK_MALFORMED]` si declares)
2. **Creer** UN seul projet `workspace/output/src/{AppName}/` via `create-next-app` (cf. §2.2.1)
3. **Composer** `lib/server/config.ts` depuis `## Active Database` + `## Active Auth Specs` :
   - `databaseUrl` (si Prisma) — format selon `DatabaseType`
   - `nextAuthSecret` (depuis `AUTH_JWT_SECRET`)
   - `nextAuthUrl` (depuis `## Project Config`)
   - `azureAd.clientId`, `azureAd.tenantId` (si auth-azure-ad)
4. **`## Active UI Specs`** : seul `shadcn` est compatible (composants React 19 RSC-ready). `vuetify` ou `radzen-blazor` → WARNING bloquant `[STACK_INCOMPAT]`
5. **Phase B (DB scaffolding)** : invoquee si `DatabaseType ≠ none` ET capability `prisma` matchee — meme procedure que `node-express.md §8.3` (`prisma db pull`)
6. **Phase C (ADRs)** : creer `ADR-{ts}-stack-fullstack-next.md` documentant App Router + RSC + Server Actions

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack est lu par **les deux agents** dev-*.

**Convention de repartition** :

- `dev-backend` materialise : `app/api/`, `app/actions/`, `lib/server/`, `lib/schemas/`, `middleware.ts`, `prisma/schema.prisma`
- `dev-frontend` materialise : `app/{segment}/page.tsx`, `app/{segment}/layout.tsx`, `app/{segment}/loading.tsx`, `components/`, `app/globals.css`

**Cas frontiere — Server Components** : `app/{segment}/page.tsx` est un **Server Component** qui appelle un Service serveur. Ownership = `dev-frontend` (couche presentation), mais le Service appele appartient a `dev-backend`. **Convention** : `dev-frontend` peut **importer** `{}Service` depuis `lib/server/services/`, mais ne peut **jamais editer** un fichier sous `lib/server/`.

**File ownership** (override `file-ownership.md §1`) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/app/{segment}/page.tsx` | `dev-frontend` |
| `workspace/output/src/{AppName}/app/{segment}/layout.tsx` | `dev-frontend` |
| `workspace/output/src/{AppName}/app/{segment}/{Component}.client.tsx` | `dev-frontend` |
| `workspace/output/src/{AppName}/app/{segment}/loading.tsx` / `error.tsx` | `dev-frontend` |
| `workspace/output/src/{AppName}/app/api/**` | `dev-backend` |
| `workspace/output/src/{AppName}/app/actions/**` | `dev-backend` |
| `workspace/output/src/{AppName}/lib/server/**` | `dev-backend` |
| `workspace/output/src/{AppName}/lib/schemas/**` | `dev-backend` (Zod schemas, partages) |
| `workspace/output/src/{AppName}/lib/utils.ts` | `dev-frontend` (cn, helpers UI) |
| `workspace/output/src/{AppName}/middleware.ts` | `dev-backend` |
| `workspace/output/src/{AppName}/components/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/app/globals.css` | `dev-frontend` |
| `workspace/output/src/{AppName}/prisma/**` | `arch` (create) + `dev-backend` (consommation) |
| `workspace/output/src/{AppName}/package.json` | `arch` (create) + `dev-backend` (augment deps) |
| `workspace/output/src/{AppName}/lib/server/config.ts` | `arch` (create exclusif — secrets/config SDD) |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}
npm install --silent
npx --yes tsc --noEmit              # type-check sans build
test -f next.config.mjs
test -f app/layout.tsx
test -f app/page.tsx
grep -q "next.*15" package.json
echo "smoke OK"
```

Smoke complet (~120s) : `npm run build` doit produire `.next/` sans erreur.
