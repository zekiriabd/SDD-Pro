# Tech FEAT: vue (frontend)

> §2.4 (Librairies) régénérée depuis `vue.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id vue`).

Status: Stable
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCVue :5180, Vue 3.5.35 + Vite 5 + TS strict + Composition API, 1568 LOC, 4/4 curl cross-origin sur Kotlin/.NET/Node/Python backends OK, AC-1/2/3 🟢. Bug fix critique : `<input type=number>` + `v-model` coerce DOM string → number → état `ref<string>` cassé silencieusement → bouton bloqué. Convention `ref<number\|null>(null)` + `v-model.number` modifier inscrite dans `library-and-stack.md §7.2`. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-vue
Scope: frontend uniquement (Vue 3 SPA + TypeScript)

---

## 1. Architecture

### 1.1 Pattern applicatif

Vue 3 SPA en **Composition API** (`<script setup>`) avec TypeScript,
consommant les APIs backend via clients HTTP Axios centralisés et
TanStack Query Vue (cache, retry, backoff).

```
View (Page) → Component → Layout → Composable → Service → HTTP Client → API
```

State global via **Pinia**. i18n via **vue-i18n**. Routing via **Vue
Router 4**. Validation via **VeeValidate + Zod**. Forms via VeeValidate
ou Vuetify natif (selon UI DS actif).

### 1.2 Couches

- **Page (View)** : routée via Vue Router, fichier `.vue`
- **Component** : composant UI réutilisable, `.vue`
- **Layout** : wrapper structurel (`DefaultLayout.vue`, `AuthLayout.vue`)
- **Composable** : logique réutilisable (`useAuth`, `useDebounce`)
- **Service** : appel API typé (services par domaine, pas par endpoint)
- **HTTP Client** : Axios instance configurée (interceptors, baseURL,
  auth token)
- **Store** : Pinia store par domaine (auth, user, ...)
- **Query** : TanStack Query Vue pour fetch/cache/retry
- **Auth** : MSAL Browser (Azure AD) ou OIDC client générique
- **i18n** : vue-i18n composable
- **Router** : Vue Router 4 avec lazy-loading des routes

### 1.3 Mapping couche → répertoire

```
workspace/output/src/{AppName}/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.ts                              # bootstrap app
│   ├── App.vue                              # root component
│   ├── router/
│   │   └── index.ts                         # Vue Router config
│   ├── pages/                               # Vue views (routées)
│   ├── components/                          # composants UI
│   ├── layouts/                             # wrappers layout
│   ├── composables/                         # composables Vue (useX)
│   ├── stores/                              # Pinia stores
│   ├── services/                            # services API (par domaine)
│   ├── api/
│   │   ├── http.ts                          # Axios instance
│   │   └── types.ts                         # types réponse API
│   ├── auth/
│   │   ├── msal.ts                          # MSAL config
│   │   └── guards.ts                        # navigation guards
│   ├── i18n/
│   │   ├── index.ts                         # i18n setup
│   │   └── locales/
│   │       ├── fr.json
│   │       └── en.json
│   ├── utils/                               # helpers
│   ├── types/                               # types globaux
│   └── assets/                              # images, fonts, css
├── public/
│   └── favicon.ico
└── dist/                                    # output build (généré)
```

### 1.4 Principes non négociables

- **Composition API** uniquement (pas d'Options API)
- **`<script setup>`** + **TypeScript** strict
- Aucune logique métier dans composants UI (composables ou services)
- Aucun appel HTTP direct depuis composants (toujours via services)
- Retry jamais manuel — TanStack Query
- `console.log` interdit en prod — utiliser logger structuré (§9)
- Traductions jamais codées en dur — toujours `t('key')`
- Aucun state global hors Pinia
- Lazy loading obligatoire (`defineAsyncComponent`, `import()` dans
  routes)
- DTOs strictement typés (TypeScript) via `interface` ou `type`
- Pas de `any` non motivé (préférer `unknown`)
- Validation des forms via VeeValidate + Zod
- Pas de mutation directe de props (toujours via émissions ou v-model)

---

## 2. Stack

### 2.1 Identité

- **Stack ID** : `front-vue`
- **Langage** : TypeScript 5.6+
- **Runtime** : Node.js 22 LTS
- **Framework principal** : Vue 3.5.x
- **Build tool** : Vite 5.4.x
- **Namespace racine** : `{AppNamespace}` (paths via alias `@/`)

### 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Build** : `cd workspace/output/src/{AppName} && npm run build`
- **Dev** : `cd workspace/output/src/{AppName} && npm run dev`
- **Preview** : `cd workspace/output/src/{AppName} && npm run preview`
- **Type-check** : `cd workspace/output/src/{AppName} && npm run type-check`
- **Lint** : `cd workspace/output/src/{AppName} && npm run lint`
- **Smoke Command** :
  ```bash
  cd workspace/output/src/{AppName}
  npm run build
  test -f dist/index.html && echo "build OK"
  ```
- **Smoke Timeout** : 90s
- **Package manager** : npm (yarn / pnpm tolérés)

### 2.2.1 Init Commands (idempotent)

```bash
# Skip si package.json existe déjà
if [ ! -f "workspace/output/src/{AppName}/package.json" ]; then
  npm create vue@latest workspace/output/src/{AppName} -- \
    --typescript --jsx --router --pinia --vitest --eslint-with-prettier --no-tests
fi
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis vue.libs.json -- ne pas editer (utiliser sync_stack_md.py).
(cd workspace/output/src/{AppName} && npm install \
  vue@3.5.13 \
  vue-router@4.5.0 \
  pinia@2.3.0 \
  @tanstack/vue-query@5.62.7 \
  vue-i18n@10.0.5 \
  vee-validate@4.15.0 \
  @vee-validate/zod@4.15.0 \
  zod@3.24.0 \
  @vueuse/core@11.3.0 \
  loglevel@1.9.2 \
  loglevel-plugin-prefix@0.8.4 \
  vite@6.0.5 \
  @vitejs/plugin-vue@5.2.1 \
  vue-tsc@2.1.10 \
  typescript@5.6.3 \
  @types/node@22.10.0 \
  prettier@3.4.2 \
  eslint@9.16.0 \
  @vue/eslint-config-typescript@14.1.4 \
  @vue/eslint-config-prettier@10.1.0)
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis vue.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: auth-azure-ad
(cd workspace/output/src/{AppName} && npm install @azure/msal-browser@3.27.0)

# capability: date-utils
(cd workspace/output/src/{AppName} && npm install date-fns@4.1.0)

# capability: excel-client
(cd workspace/output/src/{AppName} && npm install xlsx@0.18.5)

# capability: pdf-client
(cd workspace/output/src/{AppName} && npm install jspdf@2.5.2 jspdf-autotable@3.8.4)
```
<!-- ONDEMAND_PACKAGES_END -->

### 2.2.2 Scripts `package.json` obligatoires

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview --port 4173",
    "type-check": "vue-tsc --noEmit",
    "lint": "eslint . --max-warnings 0",
    "format": "prettier --write src/"
  }
}
```

### 2.3 Patterns d'erreurs compilation

Format Vite + vue-tsc : `{file}:{line}:{col} - error TS{code}: {message}`

Codes prioritaires :
- TS2304 : Cannot find name '...'
- TS2339 : Property '...' does not exist on type
- TS2322 : Type '...' is not assignable to type '...'
- TS2531 : Object is possibly 'null'
- TS7006 : Parameter '...' implicitly has an 'any' type

Erreurs spécifiques Vue :
- Vue compile-error : `<script setup>` syntaxe incorrecte
- Vue runtime-warning : prop type mismatch

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/frontend/vue.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id vue`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| vue | 3.5.35 |  |
| vue-router | 4.5.0 |  |
| pinia | 2.3.0 |  |
| @tanstack/vue-query | 5.62.7 |  |
| vue-i18n | 10.0.5 |  |
| vee-validate | 4.15.0 |  |
| @vee-validate/zod | 4.15.0 |  |
| zod | 3.24.0 |  |
| @vueuse/core | 11.3.0 |  |
| loglevel | 1.9.2 |  |
| loglevel-plugin-prefix | 0.8.4 |  |
| vite | 6.0.5 |  |
| @vitejs/plugin-vue | 5.2.1 |  |
| vue-tsc | 2.1.10 |  |
| typescript | 5.6.3 |  |
| @types/node | 22.10.0 |  |
| prettier | 3.4.2 |  |
| eslint | 9.16.0 |  |
| @vue/eslint-config-typescript | 14.1.4 |  |
| @vue/eslint-config-prettier | 10.1.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| auth-azure-ad | @azure/msal-browser | 3.27.0 | azure.ad, msal, tech-auth-azure |
| date-utils | date-fns | 4.1.0 | dates.*format, duree, intervalle.*temps |
| excel-client | xlsx | 0.18.5 | excel, \.xlsx, import.*excel, export.*excel |
| pdf-client | jspdf | 2.5.2 | pdf, \.pdf, export.*pdf, imprim |
| pdf-client | jspdf-autotable | 3.8.4 | pdf, \.pdf, export.*pdf, imprim |
<!-- LIBS_CATALOG_END -->

### 2.5 Conventions de nommage

- **Composants Vue** : `PascalCase.vue` (ex. `UserCard.vue`)
- **Composables** : `useCamelCase.ts` (ex. `useAuth.ts`)
- **Stores Pinia** : `camelCase.ts` (ex. `authStore.ts`)
- **Services** : `{domain}Service.ts` (ex. `userService.ts`)
- **Pages** : `PascalCase.vue` (ex. `LoginPage.vue`)
- **Layouts** : `{Name}Layout.vue` (ex. `DefaultLayout.vue`)
- **Types / interfaces** : `PascalCase` (ex. `UserDto`, `interface IUser`)
- **Constantes** : `SCREAMING_SNAKE_CASE`
- **Variables / fonctions** : `camelCase`

---

## 3. Conventions d'usage

### 3.1 Axios — configuration

`src/api/http.ts` :
```typescript
import axios, { type AxiosInstance } from 'axios'
import { useAuthStore } from '@/stores/authStore'

export const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' }
})

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
    }
    return Promise.reject(error)
  }
)
```

### 3.2 TanStack Query Vue — fetch + cache

`src/composables/useUsers.ts` :
```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { userService } from '@/services/userService'

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => userService.list(),
    staleTime: 5 * 60_000
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: userService.create,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] })
  })
}
```

### 3.3 Service — appel API typé

`src/services/userService.ts` :
```typescript
import { http } from '@/api/http'
import type { UserDto, CreateUserDto } from '@/types/user'

export const userService = {
  async list(): Promise<UserDto[]> {
    const { data } = await http.get<UserDto[]>('/api/v1/users')
    return data
  },

  async create(input: CreateUserDto): Promise<UserDto> {
    const { data } = await http.post<UserDto>('/api/v1/users', input)
    return data
  },

  async findById(id: number): Promise<UserDto> {
    const { data } = await http.get<UserDto>(`/api/v1/users/${id}`)
    return data
  }
}
```

### 3.4 Pinia — store typé

`src/stores/authStore.ts` :
```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserDto } from '@/types/user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<UserDto | null>(null)
  const isAuthenticated = computed(() => token.value !== null)

  function login(t: string, u: UserDto) {
    token.value = t
    user.value = u
  }

  function logout() {
    token.value = null
    user.value = null
  }

  return { token, user, isAuthenticated, login, logout }
})
```

### 3.5 Vue Router — lazy + guards

`src/router/index.ts` :
```typescript
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      children: [
        { path: '', component: () => import('@/pages/HomePage.vue') },
        {
          path: 'users',
          component: () => import('@/pages/UsersPage.vue'),
          meta: { requiresAuth: true }
        }
      ]
    },
    {
      path: '/login',
      component: () => import('@/pages/LoginPage.vue')
    }
  ]
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    next('/login')
  } else {
    next()
  }
})

export default router
```

### 3.6 Forms — VeeValidate + Zod

```vue
<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'

const schema = toTypedSchema(z.object({
  email: z.string().email('Email invalide'),
  password: z.string().min(8, 'Min 8 caractères')
}))

const { handleSubmit, errors, defineField } = useForm({
  validationSchema: schema
})

const [email, emailAttrs] = defineField('email')
const [password, passwordAttrs] = defineField('password')

const onSubmit = handleSubmit(async (values) => {
  // ... appel service login
})
</script>

<template>
  <form @submit.prevent="onSubmit">
    <input v-model="email" v-bind="emailAttrs" type="email" />
    <span v-if="errors.email">{{ errors.email }}</span>
    <input v-model="password" v-bind="passwordAttrs" type="password" />
    <span v-if="errors.password">{{ errors.password }}</span>
    <button type="submit">Login</button>
  </form>
</template>
```

### 3.7 i18n

`src/i18n/index.ts` :
```typescript
import { createI18n } from 'vue-i18n'
import fr from './locales/fr.json'
import en from './locales/en.json'

export const i18n = createI18n({
  legacy: false,
  locale: navigator.language.split('-')[0] || 'fr',
  fallbackLocale: 'fr',
  messages: { fr, en }
})
```

Dans un composant :
```vue
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t, locale } = useI18n()
</script>

<template>
  <h1>{{ t('home.title') }}</h1>
  <button @click="locale = 'en'">EN</button>
</template>
```

---

## 4. Intégration back → front

### 4.1 Variables d'environnement (`.env.development`)

```
VITE_API_BASE_URL=https://localhost:44328
VITE_AZURE_CLIENT_ID=
VITE_AZURE_TENANT_ID=
```

Conformes à `.claude/rules/env_rules.md`. Les variables `VITE_*` sont
**publiquement exposées** côté navigateur — ne jamais y mettre de
secret.

### 4.2 CORS

Le backend doit avoir une policy CORS `DevOpen` (cf. `.claude/rules/library-and-stack.md`).

### 4.3 Types partagés DTO ↔ Backend

Si le backend expose un fichier OpenAPI :
```bash
npx openapi-typescript https://localhost:44328/v3/api-docs -o src/types/api.ts
```

Sinon, types maintenus à la main dans `src/types/` avec convention
identique au backend.

---

## 5. URLs de développement

- HTTP : `http://localhost:5173` (Vite default)
- HTTPS : `https://localhost:5173` (si configuré dans `vite.config.ts`)

---

## 6. State Management

### 6.1 Pinia (préféré)

Pour state global cross-composants : auth, user profile, app-level UI
state (theme, sidebar collapsed).

### 6.2 Composables locaux

Pour state lié à une feature : `useUserList`, `useCart`. Plus léger
qu'un store, suffisant pour la plupart des cas.

### 6.3 TanStack Query Vue

Pour state **server-side** (cache des réponses API). Évite Pinia pour
cacher des données serveur — c'est le rôle de TanStack Query.

---

## 7. Multilingue

- Format : JSON par locale dans `src/i18n/locales/`
- Convention de clé : `feature.section.element`
  - Ex. : `auth.login.button`, `users.list.empty`
- Pluralisation : Vue I18n built-in (`t('items.count', count)`)
- Format dates : `date-fns` avec import locale (`fr`, `enUS`, etc.)
- Format nombres : `Intl.NumberFormat`

---

## 8. Authentification

Si `## Active Auth Specs` = Azure AD :

`src/auth/msal.ts` :
```typescript
import { PublicClientApplication, type Configuration } from '@azure/msal-browser'

const config: Configuration = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID}`,
    redirectUri: window.location.origin
  },
  cache: {
    cacheLocation: 'sessionStorage'
  }
}

export const msalInstance = new PublicClientApplication(config)
```

---

## 9. Logging

`src/utils/logger.ts` :
```typescript
import log from 'loglevel'
import prefix from 'loglevel-plugin-prefix'

prefix.reg(log)
log.setLevel(import.meta.env.PROD ? 'warn' : 'debug')
prefix.apply(log, {
  template: '[%t] %l (%n):',
  timestampFormatter: (date) => date.toISOString()
})

export default log
```

Usage :
```typescript
import log from '@/utils/logger'
log.info('User logged in', { userId: 42 })
log.warn('API timeout, retrying...')
log.error('Failed to load users', err)
```

---

## 10. Performance

- **Lazy loading routes** : obligatoire (`() => import(...)`)
- **Lazy loading components** : `defineAsyncComponent`
- **Virtual scrolling** pour listes > 1000 items (`@tanstack/vue-virtual`)
- **Image optimization** : Vite `vite-imagetools` ou plugin équivalent
- **Code splitting** : Vite auto via `rollupOptions.output.manualChunks`

---

## 11. Styling

- **CSS scoped** : `<style scoped>` dans chaque composant Vue
- **CSS variables** : tokens dans `src/assets/theme.css`
- **UI design system** : selon `## Active UI Specs` (Vuetify, ...)
  - Si Vuetify actif : voir `.claude/stacks/ui/vuetify.md`
  - Sinon : Tailwind, UnoCSS, ou CSS pur

---

## 12. Caching navigateur

`vite.config.ts` :
```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]'
      }
    }
  }
})
```

Hash dans nom de fichier → cache navigateur agressif possible.

---

## 13. Interdits projet (frontend Vue)

- **Options API** (toujours Composition API + `<script setup>`)
- **JavaScript pur** sans TypeScript
- **`any`** non motivé (préférer `unknown`)
- **Logique métier dans composants** (déléguer à composables / services)
- **Appels HTTP directs depuis composants** (toujours via services)
- **Retry manuel** (TanStack Query)
- **`console.log` / `console.error`** en prod (logger structuré)
- **State global hors Pinia**
- **Mutation directe de props** dans un composant enfant
- **Watcher non motivé** sur ref (préférer `computed`)
- **Hex hardcodé hors `theme.css`** (cf. `rules/quality.md`)
- **Texte hardcodé** dans templates (toujours `t('key')`)
- **Lazy loading absent** sur routes
- **Imports cycliques** entre stores
- **`v-html`** sans sanitization (XSS)
- **Versions de libs non pinnées** dans `package.json`

---

## 14. Recommended Skills

- `vue-3-composition-api` (si plugin disponible) — guidance idiomatique
- `vite-build-optimization` — bundle analysis et tuning

---

## 15. Hors scope technique

- Tests unitaires → `qa/node-vitest.md`
- E2E (Playwright, Cypress) → futur
- SSR / Nuxt → hors scope (futur stack `nuxt.md` séparé)
- PWA / Service Workers → hors scope SDD_Pro
- Mobile (Vue Native, Quasar) → hors scope
