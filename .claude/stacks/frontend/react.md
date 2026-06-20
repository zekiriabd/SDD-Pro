# Tech FEAT: react (frontend)

> §2.4 (Librairies) régénérée depuis `react.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id react`).

Status: Stable
Validation: 🟢 reference (validated combo CMS — kotlin-spring-boot + react + shadcn + azure-ad, 2026-05-13)
Tech FEAT ID: tech-react
Scope: frontend uniquement (React SPA)

---

## 1. Architecture

### 1.1 Pattern applicatif
React SPA consommant les APIs backend via **TanStack Query** (server
state cache + retry + invalidation). Routing **TanStack Router**
file-based avec generation auto du routeTree par plugin Vite. Forms
via **React Hook Form + Zod** (validation type-safe inferee des
schemas). Internationalisation **i18next + react-i18next** (FR/EN).
Monorepo orchestre par **Turborepo** avec versions centralisees via
**pnpm workspaces `catalog:` protocol**.

Architecture standard :

Route → Page → Component → Hook (useQuery / useMutation) → API client → Backend

Les modeles de donnees (DTO, `ApiResponse<T>`) sont partages avec le
backend via un package `{LibName}` du monorepo lorsque disponible
(ex. `packages/contracts/` consomme par `apps/web/`).

---

### 1.2 Couches

- **Route** : fichier sous `src/routes/` (file-based TanStack Router) ; le `routeTree.gen.ts` est genere par `@tanstack/router-plugin` au build et au dev.
- **Page** : composant rendu par une route, sous `src/pages/` (vue principale d'une URL).
- **Component metier** : composant reutilisable applicatif, sous `src/components/`.
- **Component UI** : primitives shadcn/ui style new-york, sous `src/components/ui/` (generes par `npx shadcn@latest add`).
- **Layout** : wrapper global (header/sidebar/footer) sous `src/layouts/`, monte via `<Outlet />` TanStack Router.
- **Hook (server state)** : `useXxxQuery` / `useXxxMutation` encapsulant `@tanstack/react-query`, sous `src/hooks/`.
- **API client** : fetch typed depuis `src/api/` (1 client par domaine, contrat partage avec backend via `{LibName}`).
- **Form** : `useForm({ resolver: zodResolver(schema) })` collocates avec la page/component qui l'utilise. Schema Zod sous `src/schemas/`.
- **Auth** : configuration MSAL React (provider) + hooks d'acces token, sous `src/auth/`.
- **i18n** : fichiers de traduction sous `src/i18n/{lang}/`, init de i18next dans `src/i18n/index.ts`.

---

### 1.3 Mapping couche → repertoire

Convention Vite + pnpm workspaces 2026 : tout sous
`workspace/output/src/{AppName}/apps/web/src/` sauf les fichiers de
config racine du workspace et de l'app. Path aliases `@/*` → `./src/*`
(vite.config.ts + tsconfig.json) imposes pour permettre les imports
shadcn `@/components/ui/...`.

**Code applicatif** (sous `apps/web/src/`) :

- Route (file-based) → `workspace/output/src/{AppName}/apps/web/src/routes/`
- Route tree genere → `workspace/output/src/{AppName}/apps/web/src/routeTree.gen.ts` (auto, jamais main-edit)
- Page → `workspace/output/src/{AppName}/apps/web/src/pages/`
- Component metier → `workspace/output/src/{AppName}/apps/web/src/components/`
- **Component UI shadcn** → `workspace/output/src/{AppName}/apps/web/src/components/ui/` (genere par `npx shadcn@latest add <component>`, jamais main-edit)
- Layout → `workspace/output/src/{AppName}/apps/web/src/layouts/`
- Hook (TanStack Query wrappers) → `workspace/output/src/{AppName}/apps/web/src/hooks/`
- API client → `workspace/output/src/{AppName}/apps/web/src/api/`
- Schema Zod → `workspace/output/src/{AppName}/apps/web/src/schemas/`
- Auth → `workspace/output/src/{AppName}/apps/web/src/auth/`
- **Lib (shadcn helpers)** → `workspace/output/src/{AppName}/apps/web/src/lib/` (contient `utils.ts` avec `cn()`)
- Utils metier → `workspace/output/src/{AppName}/apps/web/src/utils/`
- i18n → `workspace/output/src/{AppName}/apps/web/src/i18n/` (`{lang}/translation.json` + `index.ts`)
- Assets → `workspace/output/src/{AppName}/apps/web/src/assets/`

**Entry points** :

- Root → `workspace/output/src/{AppName}/apps/web/src/main.tsx`
- App → `workspace/output/src/{AppName}/apps/web/src/App.tsx` (monte `RouterProvider` + `QueryClientProvider` + `I18nextProvider`)
- Global CSS (Tailwind v4 `@theme` + tokens shadcn) → `workspace/output/src/{AppName}/apps/web/src/index.css`

**Contrats partages cross-package** (monorepo) :

- DTOs / contrats API → `workspace/output/src/{AppName}/packages/{LibName}/src/` (consomme par l'app via `import { ... } from '@{AppName}/{LibName}'`)

**Config racine workspace** (jamais sous src/) :

- pnpm workspace + version catalog → `workspace/output/src/{AppName}/pnpm-workspace.yaml`
- Turbo task graph → `workspace/output/src/{AppName}/turbo.json`
- Workspace root manifest → `workspace/output/src/{AppName}/package.json` (private, `"workspaces"` pnpm uniquement)

**Config app** (sous `apps/web/`) :

- App manifest → `workspace/output/src/{AppName}/apps/web/package.json` (depend de `catalog:`)
- Vite config → `workspace/output/src/{AppName}/apps/web/vite.config.ts` (plugins `@vitejs/plugin-react`, `@tailwindcss/vite`, `@tanstack/router-plugin`)
- TS config → `workspace/output/src/{AppName}/apps/web/tsconfig.json` + `tsconfig.app.json`
- Tailwind v4 → directement dans `index.css` (`@import "tailwindcss"; @theme { ... }`) — plus de `tailwind.config.ts` ni `postcss.config.js`
- shadcn manifest → `workspace/output/src/{AppName}/apps/web/components.json` (style: "new-york")

---

### 1.4 Principes non negociables

- Aucune logique metier dans composants UI.
- Aucun appel HTTP direct depuis composants.
- Tous appels via services.
- Retry jamais manuel.
- Retry via TanStack Query.
- Aucun console.log brut.
- Logging structure obligatoire.
- Traductions jamais codees en dur.
- Toujours utiliser i18next.
- Toujours utiliser hooks React.
- Aucun state global hors store.
- Lazy loading obligatoire.
- DTO strictement typés.

---

## 2. Stack

### 2.1 Identite

- **Stack ID** : `front-react`
- **Langage** : TypeScript
- **Runtime** : Node.js 22+
- **Framework principal** : React 19+
- **Build tool** : Vite
- **Namespace racine** : `{AppNamespace}`

---

### 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Build** : `npm --prefix workspace/output/src/{AppName} run build`
- **Dev** : `npm --prefix workspace/output/src/{AppName} run dev`
- **Preview** : `npm --prefix workspace/output/src/{AppName} run preview`
- **Smoke Command** :

```bash
npm --prefix workspace/output/src/{AppName} run build
test -f workspace/output/src/{AppName}/dist/index.html
```

- **Package manager** : npm
- **Lint** : ESLint
- **Format** : Prettier
- **Type-check** : TypeScript

---

### 2.2.1 Init Commands

Setup canonique React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui
(version 2026, conforme officiel `npx shadcn@latest init`).

```bash
# 1. Vite + React TS scaffolding
mkdir -p workspace/output/src
cd workspace/output/src
npm create vite@latest {AppName} -- --template react-ts
cd {AppName}
npm install

# 2. TypeScript path aliases (requis par shadcn pour @/components/ui)
#    Remplacer tsconfig.json + tsconfig.app.json compilerOptions.paths :
#      "baseUrl": ".",
#      "paths": { "@/*": ["./src/*"] }
#    Et vite.config.ts : ajouter `resolve: { alias: { "@": path.resolve(__dirname, "./src") } }`
#    + import path from "path" + import "@types/node"
npm install --save-dev @types/node

# 3. Tailwind v4 (CSS-first, plus simple que v3)
npm install tailwindcss @tailwindcss/vite

# 4. shadcn/ui CLI init (genere components.json, src/lib/utils.ts,
#    src/index.css avec tokens shadcn, configure tailwind.config si v3)
#    Flags: -d default theme (Slate, neutral), -y skip prompts
npx shadcn@latest init -d -y

# 5. Components shadcn de base (couvre 80% des UI courantes)
#    Chaque add pulle automatiquement les @radix-ui/* deps necessaires
npx shadcn@latest add button card input label textarea select checkbox switch \
    form dialog dropdown-menu badge avatar tabs tooltip toast skeleton \
    alert progress separator

# 6-7. Packages applicatifs (versions pinned via react.libs.json)
#    Variante pnpm workspaces + Turborepo (recommandee) : voir manifest.versionCatalogPath.
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis react.libs.json -- ne pas editer (utiliser sync_stack_md.py).
(cd workspace/output/src/{AppName} && pnpm add \
  react@19.0.0 \
  react-dom@19.0.0 \
  @types/react@19.0.2 \
  @types/react-dom@19.0.2 \
  vite@6.0.5 \
  @vitejs/plugin-react@4.3.4 \
  typescript@5.7.2 \
  tailwindcss@4.0.0 \
  @tailwindcss/vite@4.0.0 \
  tailwind-merge@2.5.5 \
  clsx@2.1.1 \
  class-variance-authority@0.7.1 \
  lucide-react@0.468.0 \
  @tanstack/react-query@5.62.7 \
  @tanstack/react-query-devtools@5.62.7 \
  react-router-dom@7.15.0 \
  react-hook-form@7.54.1 \
  zod@3.24.1 \
  @hookform/resolvers@3.10.0 \
  i18next@24.1.0 \
  react-i18next@15.2.0 \
  i18next-browser-languagedetector@8.0.2 \
  turbo@2.3.3 \
  eslint@9.17.0 \
  typescript-eslint@8.18.1)
```
<!-- CORE_PACKAGES_END -->

```bash
# 8. Verification finale
cd workspace/output/src/{AppName}
npm run build  # doit passer sans erreur de resolution d'import
```

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis react.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: i18n-http-loading
(cd workspace/output/src/{AppName} && pnpm add i18next-http-backend@3.0.1)

# capability: auth-azure-ad
(cd workspace/output/src/{AppName} && pnpm add @azure/msal-browser@5.10.1 @azure/msal-react@5.4.1)

# capability: data-grid
(cd workspace/output/src/{AppName} && pnpm add @tanstack/react-table@8.20.5)

# capability: csv-client
(cd workspace/output/src/{AppName} && pnpm add papaparse@5.4.1 @types/papaparse@5.3.15)

# capability: router-tanstack
(cd workspace/output/src/{AppName} && pnpm add @tanstack/react-router@1.166.0 @tanstack/router-plugin@1.166.0)

# capability: dev-https
(cd workspace/output/src/{AppName} && pnpm add @vitejs/plugin-basic-ssl@2.0.0)
```
<!-- ONDEMAND_PACKAGES_END -->

**Note Tailwind v4 vs v3** : `shadcn@latest init` detecte automatiquement
la version installee. v4 est preferee (CSS-first config, pas de
`postcss.config.js` ni `tailwind.config.ts` requis ; les tokens shadcn
vivent dans `src/index.css` via `@theme`). Si v3 est imposee par une
contrainte projet, le CLI bascule sur la config classique
`tailwind.config.ts` + `postcss.config.js`.

**Idempotence** : si `package.json` existe deja, sauter STEP 1. Si
`components.json` existe deja, sauter STEP 4. Le STEP 5 (`shadcn add`)
re-genere uniquement si le component manque (idempotent par design).

---

### 2.3 Patterns erreurs compilation

Format standard TypeScript :

error TSxxxx: message

Codes prioritaires :

- TS2307
- TS2322
- TS7006
- TS2339
- TS2554

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/frontend/react.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id react`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| react | 19.0.0 |  |
| react-dom | 19.0.0 |  |
| @types/react | 19.0.2 |  |
| @types/react-dom | 19.0.2 |  |
| vite | 6.0.5 |  |
| @vitejs/plugin-react | 4.3.4 |  |
| typescript | 5.7.2 |  |
| tailwindcss | 4.0.0 |  |
| @tailwindcss/vite | 4.0.0 |  |
| tailwind-merge | 2.5.5 |  |
| clsx | 2.1.1 |  |
| class-variance-authority | 0.7.1 |  |
| lucide-react | 0.468.0 |  |
| @tanstack/react-query | 5.62.7 |  |
| @tanstack/react-query-devtools | 5.62.7 |  |
| react-router-dom | 7.15.0 |  |
| react-hook-form | 7.54.1 |  |
| zod | 3.24.1 |  |
| @hookform/resolvers | 3.10.0 |  |
| i18next | 24.1.0 |  |
| react-i18next | 15.2.0 |  |
| i18next-browser-languagedetector | 8.0.2 |  |
| turbo | 2.3.3 |  |
| eslint | 9.17.0 |  |
| typescript-eslint | 8.18.1 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| i18n-http-loading | i18next-http-backend | 3.0.1 | traductions.*serveur, i18n.*lazy, load.*translations.*remote |
| auth-azure-ad | @azure/msal-browser | 5.10.1 | azure ad, msal, single sign-on, sso, oauth2.*spa, @azure/msal |
| auth-azure-ad | @azure/msal-react | 5.4.1 | azure ad, msal, single sign-on, sso, oauth2.*spa, @azure/msal |
| data-grid | @tanstack/react-table | 8.20.5 | datagrid, data grid, tanstack.*table, react-table, tableau.*colonnes, grille.*filtre |
| csv-client | papaparse | 5.4.1 | csv.*client, export.*csv.*frontend, papaparse, blob.*csv, csv.*download.*navigateur |
| csv-client | @types/papaparse | 5.3.15 | csv.*client, export.*csv.*frontend, papaparse, blob.*csv, csv.*download.*navigateur |
| router-tanstack | @tanstack/react-router | 1.166.0 | tanstack.*router, @tanstack/react-router, file-based.*routing, routes/__root, routeTree.gen |
| router-tanstack | @tanstack/router-plugin | 1.166.0 | tanstack.*router, @tanstack/react-router, file-based.*routing, routes/__root, routeTree.gen |
| dev-https | @vitejs/plugin-basic-ssl | 2.0.0 | https.*dev, basic-ssl, https.*localhost, azure ad.*spa, msal.*redirect.*localhost, vite.*https |
<!-- LIBS_CATALOG_END -->

## 3. Conventions d'usage

### 3.1 API client — fetch typed centralise (plus d'Axios)

Profil 2026 : appeler les APIs via un module typed dans `src/api/`,
avec `fetch` natif (pas de dependance Axios). Le wrapping `useQuery` /
`useMutation` (TanStack Query) gere retry, cache, backoff. Le seul
role du module API client est :

- composer l'URL (`import.meta.env.VITE_API_BASE_URL`)
- attacher le header `Authorization: Bearer <token>` (via auth provider
  actif, ex. MSAL pour azure-ad)
- decoder JSON + valider la forme via Zod (optional mais recommande)
- mapper 4xx/5xx vers une exception typee

Fichier : `apps/web/src/api/httpClient.ts` — fonction
`apiFetch<TResponse>(input, init)` re-utilisee par tous les domaines.

Interdits :
- `axios` (retire du stack au profit du fetch natif + TanStack Query)
- `fetch` direct dans un composant (toujours via `apiFetch`)
- Instanciation HTTP client dans un component / hook UI

---

### 3.2 TanStack Query — server state

Tous les appels backend passent par un hook colocate dans
`src/hooks/{domain}/useXxxQuery.ts` ou `useXxxMutation.ts` :

```ts
export function usePointsDeVenteQuery(page: number, pageSize: number) {
  return useQuery({
    queryKey: ['pointsDeVente', { page, pageSize }],
    queryFn:  ({ signal }) => apiFetch<PagedOutput<PointDeVenteDto>>(
      `/api/v1/points-de-vente?page=${page}&pageSize=${pageSize}`,
      { signal }
    )
  });
}
```

Retry, cache (staleTime, gcTime), invalidation : configures
globalement dans `QueryClient` au mount de l'app, surcharges au cas
par cas dans le hook.

Aucun `useState + useEffect + fetch` pour appeler une API. Si le hook
n'est pas idempotent par construction → `useMutation` (POST/PUT/DELETE).

---

### 3.3 TanStack Router — routing file-based type-safe

- **Definition** : un fichier par route sous `src/routes/` (convention
  file-based). Le plugin `@tanstack/router-plugin` regenere
  `routeTree.gen.ts` au dev/build — ce fichier ne doit JAMAIS etre
  edite manuellement.
- **Layouts** : route parent rend `<Outlet />` ; routes enfants
  héritent.
- **Lazy loading** : convention `_layout.tsx` + `index.lazy.tsx`
  (route splitting automatique).
- **Type safety** : params, search params, loaders typed end-to-end —
  `Link`, `useNavigate`, `useParams`, `useSearch` derivent les types
  depuis `routeTree.gen.ts`.

Aucun `react-router-dom`. Aucun routing imperatif via
`window.location`.

#### Piège — Parent route sans `<Outlet />` (post-mortem 2026-05-12, cmsfront)

**Bug** : convention dot-syntax `parent.tsx` + `parent.child.tsx` (ex.
`campagnes.tsx` + `campagnes.creation.tsx`) crée automatiquement une
relation parent-enfant dans le routeTree. **Le composant de `parent.tsx`
DOIT rendre `<Outlet/>`** pour que les enfants apparaissent. Si la route
parent rend directement un composant de page (sans Outlet), naviguer
vers `/parent/child` affiche la page parent au lieu du child.

**Symptôme** : `https://{host}/campagnes/creation` montre la liste des
campagnes (parent) au lieu du formulaire de création (child). Build vert,
aucun warning au compile.

**Pattern correct (3 routes — layout + index + child)** :

```tsx
// src/routes/campagnes.tsx — LAYOUT (Outlet pass-through, aucune UI)
import { createFileRoute, Outlet } from "@tanstack/react-router"

function CampagnesLayoutComponent() {
  return <Outlet />
}

export const Route = createFileRoute("/campagnes")({
  component: CampagnesLayoutComponent,
})
```

```tsx
// src/routes/campagnes.index.tsx — INDEX (rendu sur /campagnes exact)
import { createFileRoute } from "@tanstack/react-router"
import { CampagnesListePage } from "@/pages/CampagnesListePage"

export const Route = createFileRoute("/campagnes/")({
  component: CampagnesListePage,
})
```

```tsx
// src/routes/campagnes.creation.tsx — CHILD (rendu sur /campagnes/creation)
export const Route = createFileRoute("/campagnes/creation")({
  component: CampagneCreationPage,
})
```

**Anti-pattern** :

```tsx
// ❌ campagnes.tsx avec composant direct + enfants présents → child masqué
export const Route = createFileRoute("/campagnes")({
  component: CampagnesListePage,   // ← rendu sans Outlet, enfants ignorés
})
// + sibling campagnes.creation.tsx → /campagnes/creation rend CampagnesListePage
```

**Règle de planification (dev-frontend STEP 5)** : dès qu'une US génère
un route fichier `{parent}.{child}.tsx` à côté d'un `{parent}.tsx`
existant, **renommer le composant parent en layout `<Outlet/>`** et créer
un `{parent}.index.tsx` séparé pour la route exacte. Ne JAMAIS laisser
`{parent}.tsx` avec un composant de page direct ET un fichier child sibling.

**Anti-pattern grep checklist** :
```bash
# Pour chaque parent.tsx ayant un sibling parent.{child}.tsx :
# verifier que parent.tsx contient bien `<Outlet`
grep -L "<Outlet" workspace/output/src/{AppName}/src/routes/{parent}.tsx
# → 0 ligne attendue (le fichier doit contenir Outlet)
```

**Format ERROR si violation détectée** :
```
ERROR: dev-frontend {n}-{m} — parent route sans Outlet
CAUSE: [ROUTING_PARENT_NO_OUTLET] routes/{parent}.tsx a des enfants
       (routes/{parent}.{child}.tsx siblings) mais ne rend pas <Outlet/>
       → les child routes seront masquées par le parent au runtime.
FIX: split en 3 fichiers : {parent}.tsx (layout = <Outlet/>),
     {parent}.index.tsx (rendu /parent), {parent}.{child}.tsx (rendu /parent/child).
```

---

### 3.4 React Hook Form + Zod — formulaires

Pattern unique pour tout formulaire :

```ts
const schema = z.object({
  nom:        z.string().min(1, 'Nom requis'),
  surface:    z.number().int().nonnegative()
});
type FormValues = z.infer<typeof schema>;

const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
  resolver: zodResolver(schema),
  defaultValues: { nom: '', surface: 0 }
});
```

- Le schema Zod est la **source unique** des regles de validation
  cote client (le backend FluentValidation reste source de verite
  serveur — duplication assumee, on ne suppose JAMAIS).
- Schemas sous `src/schemas/{domain}.ts`, importables aussi par les
  hooks de mutation (validation pre-call optionnelle).
- Aucun `useState` de champ par champ ; aucun handler `onChange`
  manuel ; aucun validateur `regex` inline.

---

### 3.5 i18next + react-i18next — internationalisation

- Init dans `src/i18n/index.ts` (charge `LanguageDetector` + ressources).
- Fichiers de traduction : `src/i18n/{lang}/translation.json` (FR + EN
  par defaut, etendre via fichier additionnel).
- Usage : `const { t } = useTranslation();` puis `t('key.path')`.
- Cle i18n obligatoire pour TOUTE chaine UI affichee. Aucun string
  litteral hardcode dans les composants.
- Pluriel + interpolation natifs (`t('items', { count })`).

---

### 3.6 Hooks React — usage standard

Hooks de base (`useState`, `useEffect`, `useMemo`, `useCallback`,
`useRef`, `useId`) + hooks React 19 (`use`, `useOptimistic`,
`useActionState`) selon besoin. Custom hooks dans `src/hooks/`,
nommes `useXxx`.

`useEffect` reste reserve aux side-effects synchronises avec un
DOM/timer/subscription externe — JAMAIS pour declencher un appel API
(c'est `useQuery` qui le fait).

---

### 3.7 Error Boundaries

Boundary global au niveau App (capture des erreurs render). Boundary
local optionnel sur sections critiques (route detail) pour eviter
qu'une erreur isole ne casse toute l'app.

Fichier : `apps/web/src/components/ErrorBoundary.tsx`.

---

### 3.8 Caching navigateur

TanStack Query gere : cache, retry (default 3 avec backoff exponentiel),
invalidation par `queryKey`, refetch on focus/reconnect (opt-in).

Aucune gestion manuelle (`localStorage`/`sessionStorage` pour cache
data). Le storage navigateur sert uniquement aux preferences UI
(theme, langue) et aux artefacts auth (geres par le provider auth).

---

## 4. Integration back -> front

- **Payload** : JSON, DTOs partages via package monorepo `{LibName}`
  (ex. `import type { PointDeVenteDto } from '@{AppName}/contracts'`).
- **Versioning API** : `/api/v{N}/...` (cf. `dotnet-minimalapi.md §2.6`
  cote backend).
- **Errors** : RFC 7807 `ProblemDetails` decode par `apiFetch` et
  remonte sous forme d'exception typee.
- **Client HTTP** : `fetch` natif via `apiFetch` (cf. §3.1) + TanStack
  Query (cf. §3.2). Pas d'Axios.
- **Auth** : provider declare dans `workspace/input/stack/stack.md
  ## Active Auth Specs` (ex. `auth-local`, `azure-ad`, `oauth2`). Le
  stack auth actif fournit le composant provider racine, le hook
  d'acces token consomme par `apiFetch`, et les flows login/logout.
  Voir `.claude/stacks/auth/*.md`.

---

## 5. URLs de developpement

Frontend dev :

http://localhost:5173

Backend (port lu dynamiquement) :

Le port backend dev est **autoritairement défini par le stack backend actif**. Pour
`dotnet-minimalapi` (cf. `.claude/stacks/backend/dotnet-minimalapi.md §URLs de
développement`) :

| Profil launchSettings.json | URL |
|---|---|
| `http`  | `http://localhost:5143`  |
| `https` | `https://localhost:7239` (+ fallback HTTP 5143) |

Pour `node-express`, `python-fastapi`, `kotlin-spring-boot` : voir le `## URLs de
développement` de chaque stack backend.

**Anti-pattern bloquant (post-mortem 2026-05-14)** : aucun port backend ne doit
être hardcodé dans le frontend en dehors de la convention ci-dessous. Tout port
inventé (`5000`, `5099`, `8080` sans alignement stack) → 500 / proxy error
silencieux.

Configuration API — **DEUX patterns mutuellement exclusifs** :

**Pattern A — Proxy Vite** (recommandé, dev only, pas de CORS dev) :
```typescript
// vite.config.ts
import basicSsl from "@vitejs/plugin-basic-ssl"  // HTTPS dev (auth Azure AD)
export default defineConfig({
  plugins: [react(), basicSsl()],   // ← basicSsl pour matcher Azure AD HTTPS Redirect URI
  server: {
    port: 5173,
    https: {},                       // active HTTPS via basic-ssl
    proxy: {
      // ⚠️ POST-MORTEM 2026-05-21 — Slash final OBLIGATOIRE sur chaque préfixe.
      // Sans slash, Vite fait du prefix-match → '/api' capture aussi '/apis'
      // ou '/auth' capture '/authentication/login-callback' (route SPA MSAL).
      // Le slash final force le match strict des sous-chemins seulement.
      "/api/":  {
        target: "https://localhost:5143",  // ← port backend HTTPS du stack actif (LITTÉRAL)
        changeOrigin: true,
        secure: false,                     // accepte cert self-signed dev
      },
      // Si auth/azure-ad actif : proxy aussi /auth/ vers backend pour /auth/config.
      "/auth/": {
        target: "https://localhost:5143",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
```
Côté code applicatif : appeler `fetch("/api/auth/login")` (chemin relatif). Pas
de `VITE_API_BASE_URL` nécessaire en dev. En prod : `nginx`/`Caddy` rewrite ou
même origine.

**Pattern B — Variable d'env `VITE_API_BASE_URL`** :
```
# .env (dev)
VITE_API_BASE_URL=http://localhost:5143
```
Côté code applicatif : `fetch(\`\${import.meta.env.VITE_API_BASE_URL}/api/auth/login\`)`.
Pas de proxy Vite. Backend doit déclarer CORS pour `http://localhost:5173` (cf.
stack backend §CORS).

**Anti-pattern à grep en STEP build** (dev-frontend STEP 9) :
```bash
grep -nE 'target:\s*"http://localhost:(5000|5099|8000|8080|3000)"' workspace/output/src/{AppName}/vite.config.ts && \
  echo "[STACK_DERIVE_VIOLATION] proxy target hors stack backend actif"
```

Format ERROR :
```
ERROR: dev-frontend {n}-{m} — proxy Vite target invalide
CAUSE: [DERIVE_VIOLATION] vite.config.ts proxy target "{XXX}" ne correspond pas au port backend dev du stack actif
       (dotnet-minimalapi : 5143 HTTP / 7239 HTTPS ; cf. launchSettings.json)
FIX: 1. lire le port HTTP depuis workspace/output/src/{BackendName}/Properties/launchSettings.json (profil http.applicationUrl)
     2. mettre target: "http://localhost:{port}" dans vite.config.ts
     3. relancer le dev server Vite
```

---

### 5.bis Coercion ID au boundary API (anti-mismatch back↔front)

**Post-mortem 2026-05-21** : un backend Kotlin/Spring expose un DTO
`AnnonceurLookupResponse(id: Int)` → JSON `{"id": 5}`. Le frontend
typé `id: string` provoque alors :
- `Array.some(a => a.id === watchedValue)` → `5 === "5"` strict → **false**
- shadcn `<Select value={field.value}>` reçoit un number mais form RHF
  stocke string → re-render boucle inf ou "Valeur indisponible" affichée
- Zod schema `fkXxx: z.string().regex(/^[guid]/)` rejette tout entier-as-string

**Convention canonique** : **coercer les ID en `string` au boundary
fetch** (juste après `apiFetch` et avant retour) :

```typescript
// src/api/annonceursApi.ts
export async function getAnnonceurs(): Promise<AnnonceurLookupDto[]> {
  const data = await apiFetch<Array<{ id: number | string; libelle: string }>>(
    '/api/v1/annonceurs',
    ...
  )
  // ← coerce id au boundary (idempotent si déjà string)
  return data.map(a => ({ id: String(a.id), libelle: a.libelle }))
}
```

**Côté Zod schema** : adapter le regex à la réalité du backend
(`^\d+$` pour ID entier serial, `^[0-9a-f]{8}-...` pour UUID).
Pas de regex GUID par défaut sans vérification.

**Anti-pattern** : laisser `id: number` traverser jusqu'au form RHF.
Le contrat React state + DOM value est **toujours string** ;
laisser un `number` dedans crée des `===` strict qui échouent
silencieusement.

---

## 6. State Management

Profil 2026 : pas de store global generique. Le state est decoupe par
nature :

- **Server state** (donnees provenant du backend) → TanStack Query
  (cache automatique, invalidation, retry). Voir §3.2.
- **URL state** (filtres, pagination, onglet actif persistable dans
  l'URL) → search params TanStack Router (`Route.useSearch()` typed).
- **Form state** → React Hook Form (`useForm`). Voir §3.4.
- **Local UI state** (open/close de menu, hover, focus) → `useState`
  colocate dans le composant.
- **Auth state** → fourni par le provider auth (MSAL, etc.), expose
  via hook (`useAuth()`). Voir §3.1 / §3.4 du stack auth actif.
- **Settings persistent** (theme, langue) → `localStorage` + petit
  hook `useLocalStorage` ou `useStoredState` (3 cles max).

Pas de store global type Zustand/Redux/Pinia. Si un besoin de state
global complexe emerge sur une feature → le justifier dans un ADR
avant d'ajouter une lib.

---

## 7. Multilingue

Gestion via :

i18next.

Structure :

i18n/

fr.json
en.json

Langue :

?langue=fr

---

## 8. Authentification

Pas de provider auth fixe dans ce stack. L'integration est decouplee :
le stack auth actif declare dans `workspace/input/tech/stack.md ## Active Auth Specs`
fournit le provider, les flows login/logout, et le wiring Bearer token.

Patterns supportes (selon `## Active Auth Specs`) :

- **auth-local** — formulaire credentials → POST `/api/auth/login` →
  JWT stocke (httpOnly cookie ou Authorization header) → context React
- **azure-ad** — MSAL React popup/redirect → token cache MSAL → context
- **oauth2** — flow PKCE → token endpoint → storage securise → context
- **cognito** — Amplify Auth ou amazon-cognito-identity-js

**Contrats croises (tous providers)** :

- Token transmis sur chaque requete API via `apiFetch` (cf. §3.1) :
  `Authorization: Bearer {token}` (le token est lu depuis le provider auth
  actif — `useAuth().token` ou equivalent MSAL)
- Refresh transparent (gere par le SDK auth, ex. MSAL renew silencieux ;
  401 retourne par `apiFetch` → relance via `useAuth().refresh()` puis retry)
- Provider expose un context React `useAuth()` avec `{ user, login, logout, token }`
- Composant `<ProtectedRoute>` route guard standard sur les pages metier
- Logout = clear context + clear token storage + redirect `/login`

---

## 9. Layout System

Layouts obligatoires.

Structure :

layouts/

MainLayout.tsx
AuthLayout.tsx

---

## 10. Forms

Gestion via :

React Hook Form.

Validation via :

Zod.

Jamais validation manuelle.

---

## 11. Styling

**Tailwind CSS est OBLIGATOIRE** pour ce stack. Le projet shadcn/ui en
depend integralement (toutes les primitives shadcn sont stylisees via
Tailwind utility classes + CSS variables).

Hierarchie de styling :

1. **Tokens globaux** (`src/index.css`) — variables CSS shadcn
   (`--background`, `--foreground`, `--primary`, etc.) injectees par
   `shadcn init`. Surcharge possible via `.claude/rules/quality.md §3`
   pour matcher la fidelite design-FEAT.md §8.
2. **Utility classes Tailwind** sur les composants — preferred path.
   Ex : `className="flex gap-4 px-6 py-4 rounded-lg bg-card"`.
3. **`cn()` helper** (`src/lib/utils.ts`, genere par `shadcn init`) pour
   composer des classes conditionnelles + resoudre les conflits.
   Ex : `cn("base-class", isActive && "bg-primary", className)`.
4. **CSS isole** (`*.module.css`) — uniquement pour cas exceptionnels
   non-couvrables par Tailwind (animations complexes, selecteurs
   parents/sibling avances). Privilegier Tailwind d'abord.

Structure :

- `src/index.css` — directives Tailwind + tokens shadcn (genere par CLI)
- `src/lib/utils.ts` — `cn()` helper (genere par CLI)
- `src/components/ui/` — primitives shadcn (genere par `shadcn add`)
- `src/styles/` — CSS isole exceptionnel uniquement

**Interdits styling** :

- Hex hardcode dans les composants → utiliser `bg-primary`, `text-foreground`, etc.
- `style={{ ... }}` inline → utiliser className + cn()
- CSS-in-JS (styled-components, emotion) → out of scope, conflit avec Tailwind
- Classes Tailwind dupliquees / conflictuelles non resolues par `cn()`

---

## 12. Logging

Logging structure obligatoire.

Logger :

utils/logger.ts

Logs obligatoires :

- HTTP errors
- UI errors
- Auth events

Interdits :

console.log

---

## 13. Performance

Optimisations obligatoires :

- React.memo
- useMemo
- useCallback

Lazy loading obligatoire :

React.lazy

---

## 14. SEO / Meta

Gestion meta via :

React Helmet.

---

## 15. Structure finale projet (monorepo pnpm + Turborepo)

```
workspace/output/
└── src/
    └── {AppName}/                         # racine workspace (monorepo)
        ├── pnpm-workspace.yaml             # workspaces + catalog: versions
        ├── turbo.json                      # task graph (build, dev, lint, test)
        ├── package.json                    # private root, gere les scripts globaux
        ├── apps/
        │   └── web/                        # app frontend (consomme catalog:)
        │       ├── package.json
        │       ├── vite.config.ts          # plugins: react, tailwindcss, tanstack-router
        │       ├── tsconfig.json + tsconfig.app.json + tsconfig.node.json
        │       ├── components.json         # shadcn manifest (style: new-york)
        │       ├── .env                    # VITE_API_BASE_URL=http://localhost:5099
        │       ├── index.html              # entry HTML Vite
        │       ├── public/                 # assets statiques
        │       └── src/
        │           ├── main.tsx            # bootstrap React + Router + Query + i18n providers
        │           ├── App.tsx             # composition providers + RouterProvider
        │           ├── routeTree.gen.ts    # GENERE par @tanstack/router-plugin (READ-ONLY)
        │           ├── index.css           # @import "tailwindcss"; @theme { ... } v4
        │           ├── routes/             # file-based routes TanStack
        │           ├── pages/              # vues principales (rendues par routes)
        │           ├── layouts/            # MainLayout, AuthLayout (Outlet)
        │           ├── components/         # composants metier
        │           │   └── ui/             # primitives shadcn (genere, READ-ONLY)
        │           ├── api/
        │           │   └── httpClient.ts   # apiFetch<T>() — fetch typed + auth Bearer
        │           ├── hooks/              # useXxxQuery / useXxxMutation (TanStack Query)
        │           ├── schemas/            # schemas Zod par domaine
        │           ├── auth/               # provider auth (selon stack auth actif)
        │           ├── lib/
        │           │   └── utils.ts        # cn() helper (genere par shadcn init)
        │           ├── utils/              # utils metier (logger, formatters, ...)
        │           ├── i18n/               # fr/translation.json, en/, index.ts
        │           └── assets/             # images, fonts (statiques)
        └── packages/
            └── {LibName}/                  # contrats partages (DTOs, types backend<->front)
                ├── package.json
                └── src/
                    └── index.ts            # exports types & schemas Zod partages
```

Note : pas de `tailwind.config.ts` ni `postcss.config.js` (Tailwind v4 :
config CSS-first via `@theme` dans `index.css`). Pas de `router.tsx`
manuel (TanStack Router en file-based). Pas de `services/` Axios ni
`store/` Zustand (cf. §3.1, §6).

---

## 16. Commandes runtime

Toutes les commandes utilisent `--prefix workspace/output/src/{AppName}` pour respecter
l'invariant SDD "Per-stack project-scoped build" — pas de `cd` requis, pas
d'ambiguïté sur le `package.json` ciblé quand plusieurs stacks coexistent
sous `workspace/output/src/`.

Dev :

npm --prefix workspace/output/src/{AppName} run dev

Build :

npm --prefix workspace/output/src/{AppName} run build

Preview :

npm --prefix workspace/output/src/{AppName} run preview

Smoke :

npm --prefix workspace/output/src/{AppName} run build

---

## 17. Interdits projet (frontend)

**Architecture / data flow** :

- `fetch` direct dans composants (toujours via `apiFetch` + `useQuery`/`useMutation`)
- Axios (retire du stack — cf. §3.1)
- Zustand / Redux / store global generique (cf. §6 — pas de store global, decouper par nature de state)
- `react-router-dom` (utiliser TanStack Router file-based)
- Retry manuel (gere par TanStack Query)
- Logique metier dans UI / composants (toujours dans hooks/services)
- Traduction en dur (toujours via i18next, cf. §3.5)
- Validation manuelle (toujours via Zod + react-hook-form, cf. §3.4)
- Duplication de logique HTTP

**Code quality** :

- `console.log` brut (utiliser `utils/logger.ts` structure)
- `TODO`, `FIXME` dans le code livre
- Hardcoded API URL (utiliser `import.meta.env.VITE_API_BASE_URL`)
- Hardcoded token / secret
- `any` injustifie dans les types

**Styling / UI design system (shadcn)** :

- Hex hardcode dans les composants → utiliser tokens Tailwind/shadcn
  (`bg-primary`, `text-foreground`, etc.) ou `var(--color-*)`
- `style={{ ... }}` inline → utiliser className + `cn()`
- Edition manuelle des fichiers `src/components/ui/*` generes par
  `shadcn add` (sont READ-ONLY, regenerer via CLI si surcharge necessaire)
- **Mix de design systems** : importer un autre kit UI (`@mui/*`,
  `react-bootstrap`, `antd`, `chakra-ui`) en parallele de shadcn → un
  seul design system actif par projet (declaration dans `## Active UI Specs`)
- Recreer un primitive shadcn deja disponible (Button, Card, Input, etc.)
  manuellement dans `src/components/` au lieu de `npx shadcn add`
- CSS-in-JS (styled-components, emotion) — incompatible avec Tailwind utility-first

**Build / packaging** :

- Imports relatifs profonds `../../../` au-dela de 2 niveaux → utiliser alias `@/`
- Edition manuelle de `components.json` apres `shadcn init` (regenerer si besoin)
- Engager `node_modules/`, `dist/`, `.env` dans le git

# FIN FEAT
