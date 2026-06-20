# Tech FEAT: angular-universal (fullstack)

Status: Experimental
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCAngUniv :44379, Angular 19 SSR Express engine + signals + standalone strict, build browser 100KB + server 568KB en 2.121s, HTML SSR contient "Calc/Angular Universal/Calculate" AVANT JS (preuve runtime SSR), AC-1/2/3 🟢, interactivité 100% client après hydration. Fix bench : `--ssr` rejeté par `ng serve` → retirer flag, auto-détection via angular.json. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-angular-universal
Scope: **fullstack monolithe** — application Angular 19 avec **`@angular/ssr`** (anciennement Angular Universal) dans UN seul projet `{AppName}/`. UI Angular standalone + signals + SSR Express + API routes (server-side `server.ts`) vivent dans le meme processus Node.js. Pas de separation `{BackendName}` / `{AppName}` / `{LibName}`. Modele **SSR vrai** : HTML pre-rendu serveur, hydratation Angular cote client.

> ⚠️ **Naming** : "Angular Universal" est le nom historique (Angular ≤ 16). Depuis Angular 17, le package officiel est `@angular/ssr` integre via `ng add @angular/ssr` — meme concept, API modernisee (Builder esbuild, Standalone bootstrap, Vite dev). Ce stack utilise la version moderne ; le nom du fichier conserve `angular-universal.md` pour la decouvrabilite.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application fullstack monolithique Angular 19 SSR**. Un seul projet `{AppName}/` qui :

- Sert l'**app Angular** SSR-rendered au premier hit (HTML pre-rendu via `@angular/ssr` + Express server)
- Sert les **routes API custom** ajoutees dans `server.ts` (Express handlers) — endpoints REST consommables par le frontend OU par clients tiers
- Hydrate cote client avec la full app Angular (signals, standalone components)
- Gere l'**auth** via MSAL Angular (Azure AD) ou Auth interne (JWT cookies via API)

Architecture cible :

```
Browser
  ├── HTML SSR (premier render Angular cote serveur)
  └── JS bundle Angular (hydratation + navigation cote client)
       │
       ▼
Node.js (Express bootstrappee par @angular/ssr)
  ├── server.ts                  ── point d'entree SSR + API routes custom
  ├── @angular/ssr (Express)     ── SSR engine integre
  ├── /api/*  Express handlers   ── REST endpoints
  └── Services Angular (DI)      ── logique partagee server + client (Universal-safe)
```

**Difference vs combo `backend/python-fastapi` × `frontend/angular`** :
- Un seul projet, un seul `package.json`, un seul `angular.json`
- **Pas de CORS** (meme origine)
- **Pas d'`{LibName}` separe** — types partages via `import` cross-folder
- **Build step obligatoire** (`ng build` produit `dist/{AppName}/browser/` + `dist/{AppName}/server/`)
- **Pas de Vite dev pur** — `ng serve` utilise un dev server custom Angular (esbuild + Vite hybride en v19)

---

## 1.2 Couches

- **Components** (`app/`) : Angular Standalone components (signals par defaut Angular 19). SSR-compatible : eviter `window`/`document` direct, utiliser `inject(PLATFORM_ID)` + `isPlatformBrowser()` quand necessaire.
- **Services** (`app/services/`) : DI scoped (root par defaut). Universal-safe : aucun acces aux APIs navigateur sans garde `isPlatformBrowser`.
- **Routes** (`app/app.routes.ts`) : routing file-less, declare via `provideRouter([...])` dans `app.config.ts`
- **Guards / Resolvers** (`app/guards/`, `app/resolvers/`) : `canActivateFn`, `resolveFn`
- **Interceptors** (`app/interceptors/`) : `HttpInterceptorFn` (functional, Angular 18+)
- **Pipes** (`app/pipes/`) : transformations
- **Server entry** (`server.ts`) : Express bootstrappee par `@angular/ssr`, ajoute les routes API custom AVANT le handler SSR catch-all
- **Server API logic** : helpers dans `server/` (hors path Angular) — services serveur, repositories, schemas Zod

> **Patterns Angular partages** (standalone, signals, HttpClient, control flow `@if`/`@for`) : voir `.claude/stacks/frontend/angular.md §1.1-§1.4` (integralement applicable cote client). Specificite SSR : ajouter le module `provideServerRendering()` dans `app.config.server.ts`.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

| Layer | Path |
|---|---|
| Server entry SSR | `server.ts` (racine projet) |
| Server config Angular | `src/app/app.config.server.ts` |
| Server API helpers | `server/services/`, `server/repositories/`, `server/schemas/`, `server/middleware/` |
| App config | `src/app/app.config.ts` |
| Root component | `src/app/app.component.ts` (+ `.html`, `.scss`) |
| Routes | `src/app/app.routes.ts` |
| Components | `src/app/{domain}/{name}.component.ts` |
| Services | `src/app/services/{name}.service.ts` (Universal-safe) |
| Guards | `src/app/guards/{name}.guard.ts` |
| Resolvers | `src/app/resolvers/{name}.resolver.ts` |
| Interceptors | `src/app/interceptors/{name}.interceptor.ts` |
| Pipes | `src/app/pipes/{name}.pipe.ts` |
| Directives | `src/app/directives/{name}.directive.ts` |
| Schemas Zod | `src/app/schemas/{domain}.ts` (utilisable client + serveur) |
| i18n | `src/locale/messages.{lang}.xlf` (i18n natif Angular) ou `src/assets/i18n/*.json` (ngx-translate) |
| Static assets | `public/` (servi a la racine, copie dans `dist/{AppName}/browser/`) |
| Global styles | `src/styles.scss` |
| Prisma schema | `prisma/schema.prisma` |

**Manifestes** :
- Project file → `workspace/output/src/{AppName}/package.json`
- Angular workspace → `workspace/output/src/{AppName}/angular.json`
- TS config → `tsconfig.json` + `tsconfig.app.json` + `tsconfig.server.json`
- ESLint → `eslint.config.js` (`@angular-eslint/builder`)

---

## 1.4 Principes non negociables

**Architecture Angular SSR** :
- **Standalone components only** — `imports: [...]` dans chaque component, **JAMAIS** `NgModule`
- **Signals first** pour l'etat local (`signal()`, `computed()`, `effect()`)
- **Control flow `@if` / `@for` / `@switch`** (Angular 17+) — pas de `*ngIf`/`*ngFor` (deprecates en favor)
- **`inject()`** prefere a l'injection constructor (Angular 14+)
- **`HttpClient` avec `HttpInterceptorFn`** (functional, pas de classe `HttpInterceptor`)
- **Universal-safety obligatoire** : tout acces a `window`, `document`, `localStorage`, `navigator` DOIT etre garde par `isPlatformBrowser(inject(PLATFORM_ID))`. Sinon erreur runtime en SSR (`ReferenceError: window is not defined`).
- **`TransferState`** pour eviter le double-fetch (SSR + hydration client) — pattern `makeStateKey` + `setState`/`getState`
- **TypeScript strict** + `strictTemplates` dans `angular.json`

**Securite** :
- **Pas d'env var lue dans le code Angular** — Angular est compile, les "env vars" sont des `environment.ts` / `environment.prod.ts` (constantes au build time). Pour secrets dynamiques, passer par le serveur (route API custom dans `server.ts`).
- **CSP strict** via header `Content-Security-Policy` dans Express (`server.ts`) — pas de `'unsafe-inline'` sauf nonce dynamique
- **Cookies auth** : `httpOnly` + `secure` + `sameSite: 'lax'` (gere dans les Express handlers /api/auth/* ou MSAL si Azure AD)

**Patterns partages** : voir `.claude/stacks/frontend/angular.md §1.4` (SOLID, Clean Code, anti-patterns deja documentes — integralement applicable).

---

## 1.5 Couches persistantes

Patterns reconnus : `Entity`, `Entities`, `Repository`, `Repositories`, `Migration`, `Migrations`. Pattern Prisma identique a `.claude/stacks/backend/node-express.md §8` (le serveur SSR est Express). Mode file-based : pattern `node-react.md §6.2`.

---

## 1.6 SSR vs CSR — matrice de decision

Angular SSR rend la **premiere route** demandee par l'utilisateur. Le routing suivant est gere par Angular Router cote client. Choisir SSR vs CSR-only :

| Cas d'usage | Choix | Comment |
|---|---|---|
| App publique orientee SEO (landing, blog, e-commerce) | **SSR universel** | Defaut `@angular/ssr` apres init |
| Back-office interne, dashboard prive auth-gated | **CSR-only** | Retirer `@angular/ssr`, deployer comme SPA classique |
| Page statique sans donnees dynamiques | **Prerender** | `ng build --prerender` produit du HTML statique |
| Page avec contenu time-sensitive (cours bourse) | **SSR + cache short** | Server-side cache TTL court (`Cache-Control: s-maxage=10`) |

Si CSR-only suffit → preferer `.claude/stacks/frontend/angular.md` simple. Ce stack n'a de sens que si SSR est requise.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-angular-universal`
- **Langage** : TypeScript 5.x strict + `strictTemplates`
- **Runtime serveur** : Node.js 22 LTS
- **Framework** : Angular 19 + `@angular/ssr` (Express-based)
- **UI Design System** : Angular Material 19 (defaut) OU shadcn-angular (capability, alpha) OU Tailwind v4 (capability `tailwind`)
- **Namespace** : `{AppNamespace}` (utilise dans imports `@app/...` via path alias)

---

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Build** : `(cd workspace/output/src/{AppName} && npm run build)` — produit `dist/{AppName}/browser/` + `dist/{AppName}/server/`
- **Dev** : `(cd workspace/output/src/{AppName} && npm run dev:ssr)` → `ng serve` avec SSR active
- **Smoke Command** :

```bash
(cd workspace/output/src/{AppName} && npm install --silent && npm run build)
test -d workspace/output/src/{AppName}/dist
test -f workspace/output/src/{AppName}/dist/{AppName}/server/server.mjs
```

- **Smoke Timeout** : 240s (Angular build SSR plus long que SPA)
- **Package manager** : npm
- **Type-check** : integre a `ng build`
- **Lint** : `ng lint` (`@angular-eslint`)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/output/src/{AppName}/package.json" ]; then

# STEP 1 — Bootstrap Angular 19 standalone + strict + SCSS
npx --yes @angular/cli@19 new {AppName} \
  --directory workspace/output/src/{AppName} \
  --routing --style scss --strict \
  --standalone --ssr --package-manager npm \
  --skip-git --skip-install

cd workspace/output/src/{AppName}
npm install --silent

# (Si --ssr a ete oublie, executer separement : ng add @angular/ssr)

# STEP 2 — Installer Angular Material (UI defaut)
npx --yes ng add @angular/material@19 --skip-confirmation \
  --theme=indigo-pink --typography=true --animations=enabled

# STEP 3 — Installer libs CORE (cf. §2.4)
npm install \
  zod@3.24.0 \
  @ngx-translate/core@16.0.4 \
  @ngx-translate/http-loader@16.1.1 \
  @azure/msal-angular@4.0.3 \
  @azure/msal-browser@4.0.0 \
  rxjs@7.8.1

# STEP 4 — Creer arborescence applicative
mkdir -p \
  src/app/services \
  src/app/guards \
  src/app/resolvers \
  src/app/interceptors \
  src/app/pipes \
  src/app/directives \
  src/app/schemas \
  src/assets/i18n \
  server/services \
  server/repositories \
  server/config \
  server/schemas \
  server/middleware

# STEP 5 — Bootstrap environment.ts (rempli par arch depuis stack.md)
cat > src/environments/environment.development.ts <<'TS'
export const environment = {
  production: false,
  apiBase: '/api',
  // valeurs Azure AD / DB chargees server-side via /api/config
};
TS

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/fullstack/angular-universal.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id angular-universal`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| @angular/core | 19.0.0 |  |
| @angular/common | 19.0.0 |  |
| @angular/router | 19.0.0 |  |
| @angular/forms | 19.0.0 |  |
| @angular/platform-browser | 19.0.0 |  |
| @angular/platform-browser-dynamic | 19.0.0 |  |
| @angular/ssr | 19.0.0 | SSR engine (Express) |
| @angular/material | 19.0.0 | UI Design System defaut |
| @angular/cdk | 19.0.0 |  |
| @angular/animations | 19.0.0 |  |
| express | 4.21.2 | Server bootstrappe par @angular/ssr |
| rxjs | 7.8.1 |  |
| zod | 3.24.0 | Validation schemas (server + client) |
| typescript | 5.7.0 |  |
| zone.js | 0.15.0 | Change detection (deprecate progressif vers signals, reste CORE en v19) |
| @ngx-translate/core | 16.0.4 |  |
| @ngx-translate/http-loader | 16.1.1 |  |
| @azure/msal-angular | 4.0.3 | Auth Azure AD (selon ## Active Auth Specs) |
| @azure/msal-browser | 4.0.0 |  |
| eslint | 9.17.0 |  |
| @angular-eslint/builder | 19.0.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| prisma | prisma | 6.1.0 | DatabaseType.*(SqlServer|PostgreSql|MySql|Sqlite), orm, db-first |
| prisma | @prisma/client | 6.1.0 | prisma, orm |
| tailwind | tailwindcss | 4.0.0 | tailwind, atomic.*css |
| tailwind | postcss | 8.5.0 | tailwind |
| signals-store | @ngrx/signals | 19.0.0 | ngrx, store.*signal, state-mgmt |
| http-client | undici | 7.2.0 | appel.*api.*externe |
| excel | exceljs | 4.4.0 | excel, \.xlsx, export.*excel |
| pdf | pdfmake | 0.2.15 | pdf, export.*pdf |
| smtp | nodemailer | 6.9.16 | email, smtp |
| date-utils | date-fns | 4.1.0 | dates.*format |
| charts | ng2-charts | 7.0.0 | graph, chart, visualisation |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — verifies par dev-* STEP 5.0. Toute violation = ERROR.

| Role | Pattern | Exemple |
|------|---------|---------|
| Standalone component | `{name}.component.ts` (+ `.html`, `.scss`) — classe `{Name}Component` | `user-list.component.ts` → `UserListComponent` |
| Service | `{name}.service.ts` — `{Name}Service` decorated `@Injectable({ providedIn: 'root' })` | `auth.service.ts` → `AuthService` |
| Guard | `{name}.guard.ts` exportant `canActivateFn` | `auth.guard.ts` → `authGuard: CanActivateFn` |
| Resolver | `{name}.resolver.ts` exportant `resolveFn` | `user.resolver.ts` → `userResolver: ResolveFn<User>` |
| Interceptor | `{name}.interceptor.ts` exportant `HttpInterceptorFn` | `auth.interceptor.ts` |
| Pipe | `{name}.pipe.ts` — `{Name}Pipe` | `truncate.pipe.ts` → `TruncatePipe` |
| Directive | `{name}.directive.ts` — `{Name}Directive` | `tooltip.directive.ts` → `TooltipDirective` |
| Zod schema | `src/app/schemas/{domain}.ts` exportant `{Domain}{Action}Schema` | `UserCreateSchema` |
| Server API helper | `server/services/{domain}-service.ts` | `users-service.ts` |
| Server route Express | `server.ts` (registre toutes les routes /api/*) ou `server/routes/{domain}.ts` (module separe import dans `server.ts`) | `server/routes/users.ts` |

**Suffixes INTERDITS** :
- `.controller.ts` (server file-based)
- `Dto`, `Request`, `Response` — utiliser Zod schemas + types inferes
- `Manager`, `Util`, `Helper` (sauf `server/utils/`)

**Conventions de fichier** :
- Composants : `kebab-case.component.ts` (classe PascalCase)
- Services / pipes / guards : `kebab-case.service.ts`
- Un fichier = un export principal

---

## 3. Endpoints standard (obligatoires)

Le serveur Express bootstrappe par `@angular/ssr` expose :

| Endpoint | Auth | Role |
|----------|------|------|
| `GET /` | non | Page accueil SSR (Angular component render serveur) |
| `GET /api/health` | non | `{ ok: true, app, version }` (handler Express dans `server.ts`) |
| `GET /api/auth/*` | non | callbacks auth (MSAL ou auth-local JWT) |
| `GET /assets/**` | non | static assets (gere par `@angular/ssr` static handler) |
| `GET /**` (catch-all) | non | SSR Angular (handler `@angular/ssr` en dernier) |

**Important** : les routes `/api/*` doivent etre declarees AVANT le catch-all SSR dans `server.ts`, sinon le SSR engine intercepte tout.

---

## 4. Versioning des API

`/api/v1/{domain}` recommande. Decoupage via modules Express si l'API grossit (`server/routes/{domain}.ts`).

---

## 5. Interdits projet (angular-universal)

**Architecture** :
- `window` / `document` / `localStorage` / `navigator` sans garde `isPlatformBrowser(inject(PLATFORM_ID))`
- `setTimeout` / `setInterval` sans cleanup `OnDestroy` (memory leak SSR si non-garde)
- `NgModule` — Angular 19 = standalone only
- `*ngIf` / `*ngFor` — utiliser `@if` / `@for`
- Constructor injection (`constructor(private svc: MyService)`) en signal-first code → preferer `private svc = inject(MyService)`
- Routes API declarees dans Angular component plutot que dans `server.ts`
- Logique metier dans component → toujours via service
- Lecture DB directe dans component → passer par `/api/*` route Express
- `environment.ts` qui contient un secret runtime (les secrets vivent server-side uniquement)

**Code quality** :
- `console.log` → utiliser un Logger service injecte
- `any` injustifie
- Imports relatifs profonds — utiliser `@app/*` path alias (`tsconfig.json` `paths`)
- `subscribe()` sans `takeUntilDestroyed()` (Angular 16+) ou pattern equivalent → memory leak

**Securite** :
- Pas de XSRF protection sur les POST/PUT/DELETE — utiliser `provideHttpClient(withXsrfConfiguration(...))`
- Pas de CSP header dans `server.ts`
- Cookies sans flags `httpOnly` + `secure` + `sameSite`
- Hardcoded secrets dans `environment.ts` (visible apres build !)

**Bundle** :
- `import 'fs'` ou autre lib Node-only dans un component Angular → casse le build cote browser
- Engager `dist/`, `.angular/`, `node_modules/`, `.env` dans git

---

## 6. Persistance

- **File-based JSON** (default si `DatabaseType: none`) : pattern `node-react.md §6.2` (atomic write + lock dans `server/repositories/`)
- **Prisma** (capability `prisma`) : pattern identique a `.claude/stacks/backend/node-express.md §8.3`
- **DATABASE_URL** stockee dans une config serveur generee par `arch` depuis `## Active Database`, lue UNIQUEMENT dans `server/` — JAMAIS importee dans `src/app/` ni lue via `process.env.DATABASE_URL`

---

## 7. Temps reel

- **SSE** : ajouter une route Express dans `server.ts` :

```ts
// server.ts
server.get('/api/events', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    'Connection': 'keep-alive',
  });
  const interval = setInterval(() => res.write(': ping\n\n'), 25_000);
  req.on('close', () => clearInterval(interval));
});
```

- **WebSocket** : capability `websocket` — utiliser `ws` package directement attache au server Express, ou `socket.io`. Cote client : `WebSocket` natif ou `socket.io-client`.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Apps publiques Angular** orientees SEO (e-commerce, marketing, blog)
- **Migration progressive** depuis Angular SPA legacy (le code Angular existant reste)
- **Equipes Angular** qui veulent SSR sans changer de framework
- **Apps internes** qui ont besoin de pre-rendering pour des audits ou partage de liens

**NE PAS choisir si** :
- ❌ Backend complexe (auth multi-tenant, orchestrations) → `backend/python-fastapi.md` + `frontend/angular.md`
- ❌ Equipe non-Angular → `next.md` (React) ou `nuxt.md` (Vue)
- ❌ Pas besoin SSR (back-office interne) → `frontend/angular.md` simple
- ❌ Performance critique premier render (cold start serverless) — Angular SSR a un cold-start ~500ms-1s
- ❌ Cloudflare Workers / Edge runtime — `@angular/ssr` exige Node.js classique (pas V8 isolate)
- ❌ Streaming SSR / Suspense → React 19 / Next.js mieux outille

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-angular-universal` + Angular Material + `auth-azure-ad` + `qa-angular-jasmine` + `PostgreSql` (Prisma) | 🟡 experimental | jamais valide end-to-end |
| `fullstack-angular-universal` + `tailwind` (capability) + `auth-local` + `qa-angular-jasmine` + `SqlServer` | 🟡 experimental | viable mais non valide |
| `fullstack-angular-universal` + Angular Material + `auth-local` + `qa-angular-jasmine` + `none` (file-based) | 🟡 experimental | prototypes seulement |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` = `fullstack/angular-universal.md` → **ignorer** `BackendName` et `LibName`
2. **Creer** UN seul projet via `ng new --ssr` (cf. §2.2.1)
3. **Composer** `server/config/app-config.ts` depuis `## Active Database` + `## Active Auth Specs` :
   - `databaseUrl` (si Prisma)
   - `authJwtSecret`
   - `azureAd.clientId`, `azureAd.tenantId` (si auth-azure-ad)
4. **`## Active UI Specs`** :
   - Angular Material (defaut implicite) → OK
   - `shadcn` ou `vuetify` → WARNING bloquant (composants React/Vue, incompatibles Angular)
   - `radzen-blazor` → WARNING bloquant (composants Blazor)
5. **Phase B (DB scaffolding)** : meme procedure que `node-express.md §8.3` (Prisma db pull, driver selon DatabaseType)
6. **Phase C (ADRs)** : creer `ADR-{ts}-stack-fullstack-angular-universal.md` documentant Angular 19 + @angular/ssr + Express integre

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : stack lu par **les deux agents** dev-*.

**Convention de repartition** :

- `dev-backend` materialise : `server.ts` (augment routes /api/*), `server/services/`, `server/repositories/`, `server/schemas/`, `server/middleware/`, `prisma/schema.prisma`
- `dev-frontend` materialise : `src/app/**`, `src/styles.scss`, `src/index.html`, `src/main.ts`, `src/main.server.ts`, `src/app/app.config.ts`, `src/app/app.config.server.ts`

**File ownership** (override `file-ownership.md §1`) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/src/app/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/src/styles.scss` | `dev-frontend` |
| `workspace/output/src/{AppName}/src/index.html` | `dev-frontend` |
| `workspace/output/src/{AppName}/src/main.ts` / `main.server.ts` | `arch` (create) + `dev-frontend` (augment providers) |
| `workspace/output/src/{AppName}/server.ts` | `arch` (create initial) + `dev-backend` (augment routes /api/*) |
| `workspace/output/src/{AppName}/server/**` | `dev-backend` |
| `workspace/output/src/{AppName}/src/app/schemas/**` | `dev-backend` (Zod, partages client + serveur) |
| `workspace/output/src/{AppName}/angular.json` | `arch` exclusif |
| `workspace/output/src/{AppName}/prisma/**` | `arch` (create) + `dev-backend` (consommation) |
| `workspace/output/src/{AppName}/server/config/app-config.ts` | `arch` (create exclusif — secrets/config SDD) |

**Cas frontiere `server.ts`** : augmente par dev-backend (routes API). Utiliser lock LibName-equivalent cf. `dev-shared.md §2` quand plusieurs US ajoutent des routes en parallele.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}
npm install --silent
test -f angular.json
test -f server.ts
test -f src/app/app.config.ts
test -f src/app/app.config.server.ts
test -f src/main.ts
test -f src/main.server.ts
grep -q "@angular/core.*19" package.json
grep -q "@angular/ssr" package.json
echo "smoke OK"
```

Smoke complet (~240s) : `npm run build` doit produire `dist/{AppName}/browser/` ET `dist/{AppName}/server/server.mjs`.
