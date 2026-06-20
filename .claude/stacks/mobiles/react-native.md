# Tech FEAT: react-native (mobile)

> §2.4 (Librairies) regeneree depuis `react-native.libs.json` — ne pas editer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id react-native`).

Status: Experimental
Validation: 🟢 bench-validated runtime — Expo Web (2026-06-05 — CalcABCRN :44399, `create-expo-app` SDK 56 + RN 0.81 + Expo Router, `expo start --web` Metro 13s cold, HTTP 200 / 45KB, `<TextInput>` × 3 + `<Pressable>` Calculate compilés en HTML/CSS via RN-Web, POST → FastAPI :44329 cross-origin 🟢. Cibles iOS/Android natives non testées sans device. Bug fix : :44399 absent de l'allowlist FastAPI → ajouter aux 14 origins. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-react-native
Scope: **mobile cross-platform** — application React Native via **Expo SDK 52** dans UN seul projet `{AppName}/`. UI React Native + state + navigation + acces APIs natives + auth vivent dans le meme projet TypeScript. Pas de separation `{BackendName}` / `{LibName}`. Cible iOS + Android (+ Web optionnel via Expo Web).

> **Backend separe** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte declaree en `## Active Tech Specs` (ex. `backend/node-express.md`, `backend/dotnet-minimalapi.md`). Pour un app monolithe sans backend distinct → utiliser un Backend-as-a-Service (Supabase, Firebase, Appwrite) configure via env vars.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application React Native (Expo Managed Workflow)** cible iOS + Android :

- **Expo Router** (file-based routing, alternative moderne a React Navigation) — par defaut depuis Expo SDK 51
- **React Native** 0.76+ avec **New Architecture** active (Fabric renderer + TurboModules + JSI) — perf native, GC reduit
- **TypeScript** strict (config etendue de `expo`)
- **State client** : Zustand (top-1 pour cas simples) ; alternative `@tanstack/react-query` pour server state
- **Forms** : React Hook Form + Zod (meme pattern que `.claude/stacks/frontend/react.md §1.1`)
- **HTTP** : `fetch` natif Expo OU `axios` (capability `http-client`)
- **Styling** : **NativeWind 4** (Tailwind compile vers StyleSheet) + design tokens via Tailwind v3 (compatible NativeWind)
- **Storage** : `@react-native-async-storage/async-storage` (cles non sensibles) + `expo-secure-store` (tokens JWT, secrets)

Architecture cible (un seul projet Expo) :

```
{AppName}/
├── app/                       ── Expo Router (file-based)
│   ├── _layout.tsx           ── Root layout (Providers React Query, Zustand, etc.)
│   ├── (tabs)/               ── Bottom tab navigation
│   │   ├── _layout.tsx
│   │   ├── index.tsx         ── Home screen
│   │   └── settings.tsx
│   ├── (auth)/               ── Auth flow (login, signup)
│   └── [id].tsx              ── Dynamic route
├── src/
│   ├── components/           ── React Native components reutilisables
│   ├── hooks/                ── Custom hooks (useAuth, useUserSession)
│   ├── services/             ── API clients, services metier
│   ├── stores/               ── Zustand stores (state client)
│   ├── schemas/              ── Zod schemas (validation forms + parsing API)
│   ├── lib/                  ── helpers (cn, dates, formatters)
│   └── theme/                ── Tokens + Tailwind config
├── assets/                    ── images, fonts, sons
├── app.json                   ── Expo config (build, permissions, splash, icons)
├── package.json
└── tsconfig.json
```

**Difference vs `.claude/stacks/frontend/react.md`** :
- Pas de DOM — UI primitives sont `View`, `Text`, `ScrollView`, `Pressable`, `Image` (pas `div`/`span`/`button`)
- Pas de CSS classique — styles via NativeWind (`className="bg-blue-500"`) ou StyleSheet API
- Pas de routing `react-router-dom` — Expo Router file-based (`app/`)
- Pas de bundler manuel — Metro bundler integre Expo
- Acces APIs natives via Expo modules (`expo-camera`, `expo-location`, `expo-notifications`, etc.)

---

## 1.2 Couches

- **Screens** (`app/{segment}.tsx`) : ecrans top-level associes a une route Expo Router. Component React qui consomme hooks + services.
- **Layouts** (`app/{segment}/_layout.tsx`) : wrappers de navigation (Stack, Tabs, Drawer)
- **Components** (`src/components/`) : composants reutilisables (Button, Card, ListItem)
- **Hooks** (`src/hooks/`) : `useAuth`, `useUserSession`, `useApi` — encapsulent logique reactive
- **Services** (`src/services/`) : clients API typed (`fetchUsers`, `createUser`), parsing Zod + retry + error handling
- **Stores** (`src/stores/`) : Zustand stores (`useAuthStore`, `useUiStore`)
- **Schemas Zod** (`src/schemas/`) : validation forms + parsing reponses API
- **Lib** (`src/lib/`) : helpers pures (`cn`, `formatDate`, `truncate`)
- **Theme** (`src/theme/`) : design tokens (couleurs, typo, spacing) — NativeWind / Tailwind

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas a ce stack** (ils peuvent decrire le backend separe consomme par le mobile, mais pas la structure du projet RN). Arch leve WARNING `[STACK_MALFORMED]` si `LibStrategy` declare en mode `monorepo`.

| Layer | Path |
|---|---|
| App entry (Expo Router) | `app/_layout.tsx` (Providers globaux) |
| Screen / route | `app/{segment}.tsx` ou `app/{segment}/index.tsx` |
| Layout segment | `app/{segment}/_layout.tsx` |
| Dynamic route | `app/{segment}/[id].tsx` |
| Modal route | `app/{segment}/(modal)/{name}.tsx` |
| Group (no URL segment) | `app/(tabs)/...` ou `app/(auth)/...` |
| Component metier | `src/components/{Domain}/{Name}.tsx` |
| Component UI primitif | `src/components/ui/{Name}.tsx` (Button, Card, Input…) |
| Hook | `src/hooks/use{Name}.ts` |
| Service / API client | `src/services/{domain}Service.ts` |
| Zustand store | `src/stores/use{Domain}Store.ts` |
| Zod schema | `src/schemas/{domain}.ts` exportant `{Domain}{Action}Schema` |
| Lib helper | `src/lib/{name}.ts` |
| Theme tokens | `src/theme/tokens.ts` + `tailwind.config.js` |
| Static assets | `assets/{images,fonts,sounds}/` |
| Native config | `app.json` (Expo) — permissions, icons, splash, plugins |
| Project file | `package.json` |
| TS config | `tsconfig.json` (extends `expo/tsconfig.base`) |
| Babel config | `babel.config.js` (NativeWind preset) |
| Metro config | `metro.config.js` (NativeWind PostCSS-like resolver) |
| ESLint | `eslint.config.mjs` |

---

## 1.4 Principes non negociables

**Architecture Expo Router + RN** :
- **Defaut Expo Managed Workflow** — pas de `npm run prebuild` ni d'ejection sauf necessite documentee. Si besoin code natif custom → migrer vers **Expo Dev Client** (capability `dev-client`), pas **ejection complete**.
- **New Architecture active** (`"newArchEnabled": true` dans `app.json`) — Fabric + TurboModules par defaut Expo SDK 52
- **Aucun acces direct API native** depuis un component — toujours via un Expo module ou un hook custom
- **State separe** : `useState` local pour UI, Zustand pour state app-wide, TanStack Query pour server state. PAS de Context API pour state metier (perf degradation re-render).
- **Validation Zod obligatoire** sur :
  - Tout form submit (`useForm({ resolver: zodResolver(Schema) })`)
  - Tout parsing reponse API (`Schema.parse(json)`) — protege contre changement de schema backend silencieux
- **Navigation typed** : Expo Router auto-genere les types des routes (`href` typed). Utiliser `useRouter()` + `router.push('/users/[id]')` plutot que strings.
- **TypeScript strict** (`"strict": true`, `"noUncheckedIndexedAccess": true`)
- **Listes performantes** : `FlatList` ou `FlashList` (capability `shopify-flashlist`) pour > 50 items. JAMAIS `map` dans un `ScrollView` pour de longues listes (rendu sync, freeze UI).
- **Memo + useCallback** sur composants avec callbacks dans listes — sinon re-render integral a chaque scroll/key change.

**Securite mobile-specific** :
- **Tokens JWT / OAuth** dans `expo-secure-store` (Keychain iOS, Android Keystore) — JAMAIS dans `AsyncStorage` (texte clair, accessible via root/jailbreak)
- **Pas de secret client-side** — toute API key sensible passe par un backend proxy (cf. `## Active Tech Specs` backend)
- **Permissions runtime** : demander juste-a-temps (`expo-camera` au moment d'ouvrir la camera, pas au demarrage)
- **Certificate pinning** (capability `cert-pinning`) pour apps bancaires/sensibles
- **Deep links signes** : utiliser `expo-linking` avec validation domain (Universal Links iOS / App Links Android)

---

## 1.5 Couches persistantes (locales)

Ce stack est CLIENT mobile — la persistance "base de donnees" reelle vit cote backend. En local, options :

| Type | Lib | Cas d'usage |
|---|---|---|
| Key-value non sensible | `@react-native-async-storage/async-storage` | Preferences UI, last screen, cache leger |
| Key-value sensible | `expo-secure-store` | Tokens JWT, credentials, PIN code |
| Key-value rapide (perf critique) | `react-native-mmkv` (capability `mmkv`) | Cache rapide, sessions tres frequentes |
| Cache reactif (server state) | `@tanstack/react-query` (persistance via plugin) | API responses, retry logic |
| SQLite local (offline-first) | `expo-sqlite` (capability `offline-db`) | Apps offline-first, gros datasets |
| Sync DB (CRDT) | `WatermelonDB` ou `legend-state` (capability `offline-sync`) | Apps avec sync conflit-free |

**Mode par defaut** : AsyncStorage + SecureStore. Suffisant pour 90% des apps.

---

## 1.6 Navigation — Expo Router vs React Navigation

**Defaut SDD_Pro = Expo Router** (file-based, plus moderne). React Navigation reste accessible via les hooks bas niveau exposes par Expo Router (`useNavigation`, `useRoute` continuent de fonctionner — Expo Router est build sur React Navigation).

| Cas | Choix | Pourquoi |
|---|---|---|
| Nouveau projet | **Expo Router** | File-based, type-safe routes, deep linking natif |
| Migration projet legacy | React Navigation pur (capability `react-navigation-legacy`) | Eviter de tout reecrire |
| App avec navigation complexe (multi-stack imbrique) | Expo Router | Layouts composables `(tabs)/(modal)` |

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-react-native`
- **Langage** : TypeScript 5.x strict
- **Runtime** : Expo SDK 52 / React Native 0.76 / React 19
- **Plateformes** : iOS 13.4+ / Android API 24+ (Android 7.0)
- **Build system** : Expo (CLI + EAS Build pour CI/CD natif cloud)
- **Bundler** : Metro (integre Expo)
- **Namespace** : `{AppNamespace}` (utilise dans `app.json.expo.scheme` pour deep linking)

---

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/package.json`
- **Run dev (Metro + simulator)** : `(cd workspace/output/src/{AppName} && npx expo start)`
- **Run iOS** : `(cd workspace/output/src/{AppName} && npx expo run:ios)` — necessite Xcode (macOS uniquement)
- **Run Android** : `(cd workspace/output/src/{AppName} && npx expo run:android)` — necessite Android Studio + JDK 17
- **Build iOS / Android (cloud)** : `(cd workspace/output/src/{AppName} && eas build --platform [ios|android|all])` — EAS Build (cloud build farm Expo)
- **Smoke Command** :

```bash
(cd workspace/output/src/{AppName} && npm install --silent && npx --yes tsc --noEmit)
test -f workspace/output/src/{AppName}/app/_layout.tsx
test -f workspace/output/src/{AppName}/app.json
```

- **Smoke Timeout** : 180s (install + tsc)
- **Package manager** : npm (compatible Expo, alternatives yarn/pnpm fonctionnent mais moins testees)
- **Type-check** : `npx tsc --noEmit`
- **Lint** : `npx expo lint` (utilise ESLint flat config)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/output/src/{AppName}/package.json" ]; then

# STEP 1 — Bootstrap Expo SDK 52 (template TypeScript + Expo Router)
npx --yes create-expo-app@latest workspace/output/src/{AppName} \
  --template default --no-install

cd workspace/output/src/{AppName}
npm install --silent

# STEP 2 — Installer NativeWind 4 (Tailwind pour RN)
npm install nativewind@4.1.23 tailwindcss@3.4.17
npx --yes tailwindcss init

# Configurer babel.config.js et metro.config.js (cf. https://www.nativewind.dev/getting-started)
cat > babel.config.js <<'BABEL'
module.exports = function (api) {
  api.cache(true);
  return { presets: [["babel-preset-expo", { jsxImportSource: "nativewind" }], "nativewind/babel"] };
};
BABEL

cat > metro.config.js <<'METRO'
const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const config = getDefaultConfig(__dirname, { isCSSEnabled: true });
module.exports = withNativeWind(config, { input: "./global.css" });
METRO

cat > global.css <<'CSS'
@tailwind base;
@tailwind components;
@tailwind utilities;
CSS

# STEP 3 — Installer libs CORE (cf. §2.4)
npx --yes expo install \
  zustand \
  @tanstack/react-query \
  react-hook-form \
  @hookform/resolvers \
  zod \
  @react-native-async-storage/async-storage \
  expo-secure-store \
  expo-status-bar \
  expo-font \
  expo-splash-screen \
  expo-image \
  expo-linking \
  expo-constants \
  expo-localization

# STEP 4 — Creer arborescence applicative
mkdir -p \
  app/'(tabs)' \
  app/'(auth)' \
  src/components/ui \
  src/hooks \
  src/services \
  src/stores \
  src/schemas \
  src/lib \
  src/theme \
  assets/images \
  assets/fonts

# STEP 5 — Patcher app.json avec config par defaut (rempli par arch)
node -e "
  const fs = require('fs');
  const cfg = JSON.parse(fs.readFileSync('app.json', 'utf8'));
  cfg.expo.scheme = '{AppNamespace}'.toLowerCase().replace(/\W+/g, '');
  cfg.expo.newArchEnabled = true;
  cfg.expo.experiments = cfg.expo.experiments || {};
  cfg.expo.experiments.typedRoutes = true;
  fs.writeFileSync('app.json', JSON.stringify(cfg, null, 2));
"

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/mobiles/react-native.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id react-native`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| expo | 52.0.20 | SDK Expo (Metro, modules natifs, EAS Build) |
| react | 19.0.0 |  |
| react-native | 0.76.5 |  |
| react-dom | 19.0.0 | Necessaire pour Expo Web optionnel |
| typescript | 5.7.2 |  |
| @types/react | 19.0.2 |  |
| expo-router | 4.0.15 | File-based routing — defaut Expo SDK 51+ |
| expo-status-bar | 2.0.0 |  |
| expo-constants | 17.0.3 |  |
| expo-linking | 7.0.3 | Deep linking + Universal Links |
| expo-splash-screen | 0.29.18 |  |
| expo-font | 13.0.1 |  |
| expo-image | 2.0.3 | Cache + transformations (remplace RN Image) |
| expo-localization | 16.0.0 |  |
| expo-secure-store | 14.0.1 | Tokens JWT, secrets (Keychain iOS / Keystore Android) |
| react-native-screens | 4.4.0 | Peer Expo Router (native screens) |
| react-native-safe-area-context | 5.0.0 | Peer Expo Router (notch / status bar insets) |
| react-native-gesture-handler | 2.21.2 | Peer Expo Router (gestures natifs) |
| react-native-reanimated | 3.16.7 | Animations natives 60fps, peer plusieurs libs |
| nativewind | 4.1.23 | Tailwind compile vers StyleSheet RN — top-1 styling 2024-2025 |
| tailwindcss | 3.4.17 | Peer NativeWind — v3 obligatoire (v4 incompat RN) |
| zustand | 5.0.2 | State manager client — top-1 simple, succede Redux/Context |
| @tanstack/react-query | 5.62.7 | Server state cache — standard de facto |
| react-hook-form | 7.54.2 | Forms — meme stack que web/react.md |
| @hookform/resolvers | 3.10.0 |  |
| zod | 3.24.1 | Validation forms + parsing API responses |
| @react-native-async-storage/async-storage | 2.1.0 | KV storage non sensible — standard RN |
| eslint | 9.17.0 |  |
| eslint-config-expo | 8.0.1 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| http-client | axios | 1.7.9 | axios, http-client, appel.*api.*externe |
| date-utils | date-fns | 4.1.0 | dates.*format, duree, intervalle.*temps |
| date-utils | dayjs (alt) | 1.11.13 | dayjs, dates.*format |
| icons | lucide-react-native | 0.469.0 | icones, icon-set, lucide |
| icons | @expo/vector-icons (alt) | 14.0.4 | icones, vector-icons, ionicons, material-icons |
| forms-ui | react-native-keyboard-controller | 1.16.0 | keyboard.*controller, forms.*native |
| flashlist | @shopify/flash-list | 1.7.3 | grandes.*listes, performance.*list, virtualization |
| mmkv | react-native-mmkv | 3.1.0 | mmkv, kv.*rapide, performance.*storage |
| offline-db | expo-sqlite | 15.0.4 | sqlite, offline-first, local.*db, persistance.*locale |
| camera | expo-camera | 16.0.7 | camera, scan.*qr, photo |
| camera | react-native-vision-camera (alt) | 4.6.1 | vision-camera, photo.*haute.*qualite, video |
| barcode | expo-barcode-scanner | 13.0.1 | scan.*barcode, scan.*qr, code-barre |
| image-picker | expo-image-picker | 16.0.4 | gallerie, image-picker, choisir.*photo |
| location | expo-location | 18.0.4 | gps, location, geolocalisation |
| maps | react-native-maps | 1.20.1 | maps, carte, marker, google.*maps |
| maps | @rnmapbox/maps (alt) | 10.1.34 | mapbox, carte.*custom |
| push | expo-notifications | 0.29.11 | push.*notification, notification.*push |
| auth-azure-ad | @azure/msal-react-native | 1.0.0 | azure-ad, msal, sso |
| auth-local | expo-auth-session | 6.0.2 | oauth, auth-local, oidc |
| biometric | expo-local-authentication | 15.0.2 | biometric, face-id, touch-id, fingerprint |
| sentry | @sentry/react-native | 6.4.0 | sentry, error.*tracking, monitoring.*erreurs |
| i18n | i18next | 24.1.2 | i18n, multi.*langue, traductions |
| i18n | react-i18next | 15.4.0 | i18n, react-i18next |
| stripe | @stripe/stripe-react-native | 0.41.0 | stripe, paiement, payment |
| webview | react-native-webview | 13.13.1 | webview, embed.*page.*web |
| svg | react-native-svg | 15.10.2 | svg, vector.*graphics |
| reactive-state | jotai (alt) | 2.11.0 | jotai, atomic.*state |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Role | Pattern | Exemple |
|------|---------|---------|
| Screen Expo Router | `app/{segment}.tsx` ou `app/{segment}/index.tsx` | `app/dashboard.tsx`, `app/(tabs)/index.tsx` |
| Layout | `app/{segment}/_layout.tsx` | `app/(tabs)/_layout.tsx` |
| Dynamic route | `app/{segment}/[id].tsx` | `app/users/[id].tsx` |
| Component | `src/components/{Domain}/{Name}.tsx` (PascalCase) | `src/components/User/UserCard.tsx` |
| Component UI primitif | `src/components/ui/{Name}.tsx` | `src/components/ui/Button.tsx` |
| Hook | `src/hooks/use{Name}.ts` | `src/hooks/useAuth.ts` |
| Service | `src/services/{domain}Service.ts` | `src/services/usersService.ts` |
| Zustand store | `src/stores/use{Domain}Store.ts` | `src/stores/useAuthStore.ts` |
| Zod schema | `src/schemas/{domain}.ts` exportant `{Domain}{Action}Schema` | `UserCreateSchema` |

**Suffixes INTERDITS** :
- `.controller.ts` (file-based)
- `Dto`, `Request`, `Response` — utiliser Zod schemas + `z.infer<typeof Schema>`
- `Manager`, `Helper`, `Util` (sauf `src/lib/` strict)
- `Component` suffix sur fichier `.tsx` (`UserCardComponent.tsx`) → redondant, juste `UserCard.tsx`

**Conventions de fichier** :
- Routes (`app/`) : `kebab-case.tsx` ou `[param].tsx` ou `(group)/`
- Components : `PascalCase.tsx`
- Hooks : `camelCase.ts` (prefix `use`)
- Tout autre : `camelCase.ts`

---

## 3. Endpoints standard (cote backend separe)

Ce stack est mobile-only — il consomme un backend distinct. Les endpoints minimaux attendus :

| Endpoint cote backend | Role |
|---|---|
| `GET /api/health` | healthcheck (status connectivite) |
| `POST /api/auth/login` ou `/api/auth/[...]` | flow auth |
| `GET /api/me` | user courant (apres auth) |

Cote app : un seul **base URL** configure en runtime via :
- **Dev** : `http://192.168.x.x:5000` (IP locale du Mac/PC qui sert le backend) — accessible depuis simulator/emulator
- **Staging/Prod** : `https://api.{domain}.com` injecte via `app.json.expo.extra.apiBaseUrl` (lu via `Constants.expoConfig.extra.apiBaseUrl`)

---

## 4. Versioning des API consommees

Le backend expose `/api/v1/{domain}` (recommande). Cote mobile : maintenir une **min-supported-api-version** dans `app.json.expo.extra.apiVersion`. A chaque release mobile, valider que le backend deploye supporte cette version.

---

## 5. Interdits projet (react-native)

**Architecture** :
- Acces direct API native (Java/Kotlin/Swift/Obj-C) sans Expo module — utiliser `expo-modules-core` si module custom necessaire
- `map()` dans un `ScrollView` pour > 50 items — utiliser `FlatList` ou `FlashList`
- Context API pour state metier app-wide — utiliser Zustand
- Token JWT dans `AsyncStorage` — utiliser `expo-secure-store`
- API key sensible (Stripe secret, ...) dans le code client — toujours via backend proxy
- `console.log` en prod — utiliser `__DEV__` guard ou Sentry
- `setTimeout` / `setInterval` sans cleanup `useEffect` return — memory leak
- `Image` (RN core) pour images critiques — preferer `expo-image` (cache + perf)
- `react-native-vector-icons` — preferer `@expo/vector-icons` (gere par Expo, pas de linking manuel)

**Code quality** :
- `any` injustifie
- Imports relatifs profonds (`../../../`) — utiliser path aliases (`@/components/...`)
- Inline styles non memoizes dans listes (re-render integral)
- Hooks appeles conditionnellement (regle des hooks)
- `useEffect` sans deps array (re-execute chaque render)
- `useState` pour donnees derivees (utiliser `useMemo` ou compute inline)

**Securite** :
- Secret hardcode dans `app.json` ou `package.json`
- Token loggue en clair
- Deep link sans validation domaine (deep link hijacking)
- WebView sans `originWhitelist` strict
- `dangerouslySetInnerHTML` (interdit en RN, mais piege RN-web)
- Certificate pinning desactive sur app bancaire/sensible

**Build / packaging** :
- Engager `node_modules/`, `.expo/`, `dist/`, `ios/`, `android/` (si Expo Managed) dans git
- `package.json` sans `"engines": { "node": ">=22" }`
- Mix `npm` + `yarn` + `pnpm` lockfiles
- Permissions excessives dans `app.json` (demander juste-a-temps, declarer le strict minimum)
- App Tracking Transparency (iOS 14.5+) sans message explicatif (rejection Apple Review)

**Plateformes** :
- Conditionnel `Platform.OS === 'ios'` disperse — extraire dans helpers `src/lib/platform.ts`
- API specific iOS appelee sans garde sur Android (crash silencieux)
- Layout fixe en pixels (`width: 320`) — utiliser `Dimensions` ou `useWindowDimensions` + responsive

---

## 6. Persistance locale — voir §1.5

Stack mobile → pas de "DB scaffolding" classique. Pour offline-first reel : capability `offline-db` (`expo-sqlite`) ou `offline-sync` (WatermelonDB). Sinon, AsyncStorage + SecureStore par defaut.

---

## 7. Temps reel

Pattern client mobile :
- **SSE** : utiliser `react-native-event-source` (capability `sse`) ou `EventSource` natif (Expo SDK 52+ inclut polyfill)
- **WebSocket** : `WebSocket` natif RN OU `socket.io-client` (capability `socketio`)
- **Push notifications** : `expo-notifications` (capability `push`) + setup APNS (iOS) + FCM (Android) cote backend

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Apps cross-platform iOS + Android** avec 90% de code partage
- **Equipes React** (sweet spot — competences re-utilisables)
- **MVP rapides** (Expo Managed Workflow, OTA updates via EAS Update)
- **Apps avec logique riche cote client** (offline-first, complex state, animations)

**NE PAS choisir si** :
- ❌ Performance graphique extreme requise (jeux, AR/VR) → Unity / Unreal / Swift+Metal / Kotlin+Vulkan
- ❌ Acces materiel tres specifique (NFC bas niveau, BLE custom, Bluetooth audio professionnel) → natif iOS/Android
- ❌ App single-platform (iOS only ou Android only) sans roadmap multi → natif (SwiftUI / Jetpack Compose) pour utiliser au mieux la plateforme
- ❌ Equipe sans aucune competence React/JS → courbe d'apprentissage non justifiee
- ❌ App embarquee sur device IoT (TV box, watch sans support officiel) → autre stack
- ❌ Besoin de tres petite taille APK/IPA (< 5MB) — RN/Expo runtime base ~25-50MB

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `mobile-react-native` + `auth-local` (JWT) + backend `node-express` + `qa-node-vitest` (pour services) | 🟡 experimental | jamais valide end-to-end |
| `mobile-react-native` + `auth-azure-ad` (MSAL) + backend `dotnet-minimalapi` + `qa-node-vitest` | 🟡 experimental | viable, MSAL RN mature |
| `mobile-react-native` (Expo + Supabase, capability `supabase`) + `qa-node-vitest` | 🟡 experimental | prototypes, pas de backend custom |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` contient `mobiles/react-native.md` → reconnaitre comme stack **mobile-only**, pas un frontend web standard
2. **Le backend reste declare separement** dans `## Active Tech Specs` (par ex. `backend/node-express.md`) — les deux co-existent, projets distincts sous `workspace/output/src/`
3. **Creer** `workspace/output/src/{AppName}/` via `create-expo-app` (cf. §2.2.1)
4. **Injecter** `app.json.expo.extra.apiBaseUrl` depuis une nouvelle section `## Active Mobile Config` du `stack.md` (a creer si absente — convention `MOBILE_API_BASE_URL`)
5. **`## Active UI Specs`** : aucun design system web n'est compatible. Stack utilise NativeWind (Tailwind) par defaut. Si `shadcn`/`vuetify`/`radzen-blazor` declare → WARNING bloquant `[STACK_INCOMPAT]`. Alternative mobile : `react-native-paper` (Material), `tamagui`, `gluestack-ui` (capabilities futures)
6. **Phase B (DB)** : SKIP — pas de DB locale par defaut (sauf capability `offline-db` qui ne necessite pas le scan DB serveur)
7. **Phase C (ADRs)** : creer `ADR-{ts}-stack-mobile-react-native.md` documentant Expo SDK 52 + Expo Router + NativeWind

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de "backend interne". Convention :

- `dev-backend` **ne touche pas** au projet mobile RN — il code le backend separe declare dans `## Active Tech Specs backend/*`
- `dev-frontend` materialise **tout** le projet RN : `app/`, `src/`, `assets/`, `app.json`, `package.json`, `tsconfig.json`

**File ownership** (override `file-ownership.md §1`) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/app/**` (routes Expo Router) | `dev-frontend` |
| `workspace/output/src/{AppName}/src/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/assets/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/app.json` | `arch` (create) + `dev-frontend` (augment permissions, plugins, extra) |
| `workspace/output/src/{AppName}/package.json` | `arch` (create) + `dev-frontend` (augment deps on-demand) |
| `workspace/output/src/{AppName}/tsconfig.json` | `arch` exclusif |
| `workspace/output/src/{AppName}/babel.config.js` / `metro.config.js` | `arch` exclusif |
| `workspace/output/src/{AppName}/tailwind.config.js` | `arch` (create) + `dev-frontend` (augment theme tokens) |

**Backend separe** : meme matrice ownership que pour son propre stack (`backend/node-express.md`, etc.). Les 2 projets co-existent sous `workspace/output/src/{BackendName}/` et `workspace/output/src/{AppName}/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}
npm install --silent
npx --yes tsc --noEmit
test -f app/_layout.tsx
test -f app.json
test -f tailwind.config.js
test -f metro.config.js
grep -q "\"newArchEnabled\": true" app.json
grep -q "expo.*~?52" package.json
grep -q "react-native.*0\\.76" package.json
echo "smoke OK"
```

Smoke complet sur device/simulator : `npx expo start --no-dev --minify` puis ouvrir Expo Go ou simulateur — doit afficher l'app sans crash.
