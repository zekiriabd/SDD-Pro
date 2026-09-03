# Tech FEAT: react-native (mobile)

> §2.4 (Librairies) regeneree depuis `react-native.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id react-native`).

Status: Experimental
Validation: 🟢 bench-validated runtime — Expo Web (2026-06-05 — CalcABCRN :44399, `create-expo-app` SDK 56 + RN 0.81 + Expo Router, `expo start --web` Metro 13s cold, HTTP 200 / 45KB, `<TextInput>` × 3 + `<Pressable>` Calculate compilés en HTML/CSS via RN-Web, POST → FastAPI :44329 cross-origin 🟢. Cibles iOS/Android natives non testées sans device. Bug fix : :44399 absent de l'allowlist FastAPI → ajouter aux 14 origins. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`. **Rebase catalog 2026-09-02** : le `.libs.json` a été repinné SDK 52 → **SDK 57 / RN 0.86.3** — le bench avait tourné sur SDK 56 alors que le catalog annonçait encore SDK 52, incohérence fermée. 4 bugs bloquants corrigés au passage, cf. §2.3.)
Tech FEAT ID: tech-react-native
Scope: **mobile cross-platform** — application React Native via **Expo SDK 57** dans UN seul projet `{AppName}/`. UI React Native + state + navigation + acces APIs natives + auth vivent dans le meme projet TypeScript. Pas de separation `{BackendName}` / `{LibName}`. Cible iOS + Android (+ Web optionnel via Expo Web).

> **Backend separe** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte declaree en `## Active Tech Specs` (ex. `backend/node-express.md`, `backend/dotnet-minimalapi.md`). Pour un app monolithe sans backend distinct → utiliser un Backend-as-a-Service (Supabase, Firebase, Appwrite) configure via env vars.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application React Native (Expo Managed Workflow)** cible iOS + Android :

- **Expo Router** (file-based routing, alternative moderne a React Navigation) — par defaut depuis Expo SDK 51
- **React Native** 0.86 avec **New Architecture** (Fabric + TurboModules + JSI) — seul mode supporte depuis l'SDK 55, l'ancienne archi est supprimee
- **TypeScript** strict (config etendue de `expo`)
- **State client** : Zustand (top-1 pour cas simples) ; alternative `@tanstack/react-query` pour server state
- **Forms** : React Hook Form + Zod (meme pattern que `.sdd/stacks/frontend/react.md §1.1`)
- **HTTP** : `fetch` natif Expo OU `axios` (capability `http-client`)
- **Styling** : **NativeWind 4.2** (Tailwind compile vers StyleSheet) + design tokens via Tailwind **v3** — NativeWind 4 ne supporte PAS Tailwind v4 (cf. §2.3)
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

**Difference vs `.sdd/stacks/frontend/react.md`** :
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

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas a ce stack** (ils peuvent decrire le backend separe consomme par le mobile, mais pas la structure du projet RN). Arch leve WARNING `[STACK_MALFORMED]` si `LibStrategy` declare en mode `monorepo`.

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
- **New Architecture active** — Fabric + TurboModules. Depuis l'SDK 55 c'est le **seul** mode : le flag `newArchEnabled` n'a plus a etre pose, et `"newArchEnabled": false` fait echouer le build
- **Aucun acces direct API native** depuis un component — toujours via un Expo module ou un hook custom
- **State separe** : `useState` local pour UI, Zustand pour state app-wide, TanStack Query pour server state. PAS de Context API pour state metier (perf degradation re-render).
- **Validation Zod obligatoire** sur :
  - Tout form submit (`useForm({ resolver: zodResolver(Schema) })`)
  - Tout parsing reponse API (`Schema.parse(json)`) — protege contre changement de schema backend silencieux
- **Navigation typed** : Expo Router auto-genere les types des routes (`href` typed). Utiliser `useRouter()` + `router.push('/users/[id]')` plutot que strings.
- **TypeScript strict** (`"strict": true`, `"noUncheckedIndexedAccess": true`)
- **Listes performantes** : `FlatList` ou `FlashList` (capability `flashlist`) pour > 50 items. JAMAIS `map` dans un `ScrollView` pour de longues listes (rendu sync, freeze UI).
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
- **Langage** : TypeScript 6.x strict (version du template `expo-template-default@57`)
- **Runtime** : Expo SDK 57 / React Native 0.86.3 / React 19.2.3
- **Plateformes** : iOS 15.1+ / Android API 24+ (Android 7.0) — planchers Expo SDK 57
- **Build system** : Expo (CLI + EAS Build pour CI/CD natif cloud)
- **Bundler** : Metro (integre Expo)
- **Namespace** : `{AppNamespace}` (utilise dans `app.json.expo.scheme` pour deep linking)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/package.json`
- **Run dev (Metro + simulator)** : `(cd workspace/src/{AppName} && npx expo start)`
- **Run iOS** : `(cd workspace/src/{AppName} && npx expo run:ios)` — necessite Xcode (macOS uniquement)
- **Run Android** : `(cd workspace/src/{AppName} && npx expo run:android)` — necessite Android Studio + JDK 17
- **Build iOS / Android (cloud)** : `(cd workspace/src/{AppName} && eas build --platform [ios|android|all])` — EAS Build (cloud build farm Expo)
- **Audit coherence deps** : `(cd workspace/src/{AppName} && npx expo-doctor)` — **gate obligatoire** : detecte tout ecart entre une version installee et celle attendue par l'SDK (cf. §2.3)
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && npm install --silent && npx --yes tsc --noEmit)
test -f workspace/src/{AppName}/app/_layout.tsx
test -f workspace/src/{AppName}/app.json
```

- **Smoke Timeout** : 180s (install + tsc)
- **Package manager** : npm (compatible Expo, alternatives yarn/pnpm fonctionnent mais moins testees)
- **Type-check** : `npx tsc --noEmit`
- **Lint** : `npx expo lint` (utilise ESLint flat config)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/package.json" ]; then

# STEP 1 — Bootstrap Expo SDK 57 (template TypeScript + Expo Router)
npx --yes create-expo-app@latest workspace/src/{AppName} \
  --template default --no-install

cd workspace/src/{AppName}
npm install --silent

# STEP 2 — Installer NativeWind 4 (Tailwind pour RN)
# ATTENTION : tailwindcss est pinne sur la ligne v3. NativeWind 4 ne supporte
# PAS Tailwind v4 (il faudrait NativeWind 5, encore en preview) — cf. §2.3.
npm install nativewind@4.2.6 tailwindcss@3.4.19
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

# STEP 3 — Installer les libs CORE natives / Expo (cf. §2.4.a)
# `expo install` (et NON `npm install`) : il resout chaque version depuis le
# bundledNativeModules.json de l'SDK installe. C'est la seule commande qui
# garantit un jeu de deps coherent — cf. §2.3.
npx --yes expo install \
  expo-secure-store \
  expo-status-bar \
  expo-system-ui \
  expo-font \
  expo-splash-screen \
  expo-image \
  expo-linking \
  expo-constants \
  expo-localization \
  react-native-reanimated \
  react-native-worklets \
  react-native-gesture-handler \
  react-native-screens \
  react-native-safe-area-context \
  @react-native-async-storage/async-storage

# STEP 4 — Installer les libs CORE pure-JS (pas de code natif -> npm direct)
npm install \
  zustand@5.0.15 \
  @tanstack/react-query@5.102.8 \
  react-hook-form@7.87.0 \
  @hookform/resolvers@5.9.1 \
  zod@4.5.4

# STEP 5 — Creer arborescence applicative
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

# STEP 6 — Patcher app.json avec config par defaut (rempli par arch)
# NB : on ne pose PLUS `newArchEnabled` — depuis l'SDK 55 la New Architecture
# est le seul mode supporte et le flag est ignore (le poser a false casse le build).
node -e "
  const fs = require('fs');
  const cfg = JSON.parse(fs.readFileSync('app.json', 'utf8'));
  cfg.expo.scheme = '{AppNamespace}'.toLowerCase().replace(/\W+/g, '');
  cfg.expo.experiments = cfg.expo.experiments || {};
  cfg.expo.experiments.typedRoutes = true;
  fs.writeFileSync('app.json', JSON.stringify(cfg, null, 2));
"

# STEP 7 — Gate de coherence : doit sortir 0 avant de rendre la main
npx --yes expo-doctor

fi
```

---

## 2.3 Regle de pin des versions (source de verite)

> Cette section existe parce que le catalog a derive deux fois. Elle est
> **normative** : `arch` la respecte avant tout bump de `react-native.libs.json`.

Expo publie, dans chaque version du paquet `expo`, un fichier
`bundledNativeModules.json` qui declare **la version exacte de chaque lib
native attendue par l'SDK**. `npx expo install` lit ce fichier ; `npm install`
l'ignore.

| Nature de la lib | Source de la version | Exemple |
|---|---|---|
| Presente dans `bundledNativeModules.json` | **cette valeur, pas npm latest** | `react-native-gesture-handler` → `2.32.0` (npm latest = `3.2.1`, incompatible) |
| Module `expo-*` | idem (aligne sur le numero d'SDK) | `expo-router` → `57.0.18` |
| Pure-JS, absente du bundle | npm latest stable | `zustand`, `zod`, `@tanstack/react-query` |

Verification : `npx expo-doctor` echoue des qu'une version installee sort de la
plage attendue. **Ce check est un gate**, pas un warning.

### Bugs fermes par l'audit 2026-09-02

| # | Probleme | Correction |
|---|---|---|
| 1 | `@azure/msal-react-native` (capability `auth-azure-ad`) — **le paquet n'existe pas sur npm** (404). Toute US Azure AD echouait a l'install. | Remplace par `react-native-msal` 4.0.4 |
| 2 | `react-native-reanimated` 4.x **exige** le peer `react-native-worklets`, absent du catalog → echec au bundling Metro | `react-native-worklets` 0.10.1 ajoute en CORE |
| 3 | `expo-barcode-scanner` : module **retire d'Expo depuis l'SDK 51**, absent du `bundledNativeModules` | Capability `barcode` fusionnee dans `camera` (`CameraView.onBarcodeScanned` d'`expo-camera`) |
| 4 | Catalog pinne SDK 52 / RN 0.76 alors que l'en-tete `Validation:` documentait un bench sur SDK 56 / RN 0.81 | Rebase complet sur SDK 57 / RN 0.86.3 |

Peers ajoutes par la meme occasion (ils manquaient et cassaient l'install
des capabilities concernees) : `react-native-nitro-modules` (peer de
`react-native-mmkv` 4.x et de `react-native-vision-camera` 5.x),
`react-native-nitro-image` (peer de `vision-camera` 5.x),
`test-renderer` (peer de `@testing-library/react-native` 14.x),
`expo-web-browser` (peer d'`expo-auth-session`).

Modules deprecies retires du catalog : `expo-av` → `expo-video` + `expo-audio`.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/react-native.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id react-native`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| expo | 57.0.19 | SDK Expo 57 (Metro, modules natifs, EAS Build) |
| react | 19.2.3 | Version imposee par l'SDK 57 (bundledNativeModules) |
| react-native | 0.86.3 | Version imposee par l'SDK 57 — PAS npm latest (0.87.x casse l'SDK 57) |
| react-dom | 19.2.3 | Necessaire pour Expo Web optionnel |
| react-native-web | 0.21.2 | Cible Web optionnelle — c'est la cible du bench 2026-06-05 |
| typescript | 6.0.3 | Version du template expo-template-default@57 — TS 7.x pas encore valide par Expo |
| @types/react | 19.2.2 |  |
| expo-router | 57.0.18 | File-based routing — defaut Expo SDK 51+ |
| expo-status-bar | 57.0.1 |  |
| expo-constants | 57.0.17 | Lecture de app.json.expo.extra (apiBaseUrl, apiVersion) |
| expo-linking | 57.0.9 | Deep linking + Universal Links |
| expo-splash-screen | 57.0.8 |  |
| expo-font | 57.0.3 |  |
| expo-image | 57.0.4 | Cache + transformations (remplace RN Image) |
| expo-localization | 57.0.1 |  |
| expo-secure-store | 57.0.3 | Tokens JWT, secrets (Keychain iOS / Keystore Android) |
| expo-system-ui | 57.0.3 | Couleur de fond racine + barre navigation Android (template SDK 57) |
| react-native-screens | 4.26.0 | Peer Expo Router (native screens) |
| react-native-safe-area-context | 5.7.0 | Peer Expo Router (notch / status bar insets) |
| react-native-gesture-handler | 2.32.0 | Peer Expo Router — pin SDK 57 (~2.32), npm latest 3.x incompatible |
| react-native-reanimated | 4.5.1 | Animations natives 60fps. v4 externalise les Worklets (cf. lib suivante) |
| react-native-worklets | 0.10.1 | PEER OBLIGATOIRE de reanimated 4.x — absent du catalog avant l'audit 2026-09-02, le bundling echouait |
| nativewind | 4.2.6 | Tailwind compile vers StyleSheet RN — top-1 styling |
| tailwindcss | 3.4.19 | Peer NativeWind 4 — ligne v3 (tag npm v3-lts) OBLIGATOIRE. Tailwind v4 exige NativeWind 5, encore en preview |
| zustand | 5.0.15 | State manager client — top-1 simple, succede Redux/Context |
| @tanstack/react-query | 5.102.8 | Server state cache — standard de facto |
| react-hook-form | 7.87.0 | Forms — meme stack que frontend/react.md |
| @hookform/resolvers | 5.9.1 | v5 requis pour supporter Zod v4 |
| zod | 4.5.4 | Validation forms + parsing API responses (v4) |
| @react-native-async-storage/async-storage | 2.2.0 | KV storage non sensible — standard RN |
| eslint | 10.9.1 |  |
| eslint-config-expo | 57.0.2 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| http-client | axios | 1.20.0 | \baxios\b, http-client, appel.*api.*externe |
| date-utils | date-fns | 4.4.0 | dates.*format, duree, intervalle.*temps |
| date-utils | dayjs (alt) | 1.11.23 | dayjs, dates.*format |
| icons | @expo/vector-icons | 15.1.1 | icones, icon-set, vector-icons, ionicons, material-icons |
| icons | lucide-react-native (alt) | 1.39.0 | lucide |
| native-ui | @expo/ui | 57.0.15 | composants.*natifs, swiftui, jetpack.*compose, look.*natif |
| forms-ui | react-native-keyboard-controller | 1.21.9 | keyboard.*controller, forms.*native |
| flashlist | @shopify/flash-list | 2.0.2 | grandes.*listes, performance.*list, virtualization |
| nitro | react-native-nitro-modules | 0.37.1 | nitro, mmkv, vision-camera |
| mmkv | react-native-mmkv | 4.3.2 | mmkv, kv.*rapide, performance.*storage |
| offline-db | expo-sqlite | 57.0.2 | sqlite, offline-first, local.*db, persistance.*locale |
| camera | expo-camera | 57.0.4 | camera, photo, scan.*qr, scan.*barcode, code-barre |
| camera | react-native-vision-camera (alt) | 5.2.3 | vision-camera, photo.*haute.*qualite, frame.*processor |
| nitro | react-native-nitro-image (alt) | 0.15.2 | vision-camera |
| image-picker | expo-image-picker | 57.0.15 | gallerie, image-picker, choisir.*photo |
| location | expo-location | 57.0.15 | gps, location, geolocalisation |
| maps | expo-maps | 57.0.2 | maps, carte, marker |
| maps | react-native-maps (alt) | 1.27.2 | react-native-maps, google.*maps |
| maps | @rnmapbox/maps (alt) | 10.3.5 | mapbox, carte.*custom |
| push | expo-notifications | 57.0.16 | push.*notification, notification.*push |
| auth-local | expo-auth-session | 57.0.11 | oauth, auth-local, oidc, pkce |
| auth-local | expo-web-browser | 57.0.2 | oauth, oidc, auth.*navigateur |
| auth-azure-ad | react-native-msal | 4.0.4 | azure-ad, msal, entra, sso |
| biometric | expo-local-authentication | 57.0.2 | biometric, face-id, touch-id, fingerprint |
| sentry | @sentry/react-native | 7.11.0 | sentry, error.*tracking, monitoring.*erreurs |
| i18n | i18next | 26.4.1 | i18n, multi.*langue, traductions |
| i18n | react-i18next | 17.0.13 | i18n, react-i18next |
| stripe | @stripe/stripe-react-native | 0.64.0 | stripe, paiement, payment |
| webview | react-native-webview | 13.16.1 | webview, embed.*page.*web |
| svg | react-native-svg | 15.15.4 | svg, vector.*graphics, lucide |
| media-playback | expo-video | 57.0.3 | video, lecteur.*video, player |
| media-playback | expo-audio | 57.0.4 | audio, son, enregistrement.*audio |
| filesystem | expo-file-system | 57.0.6 | fichier.*local, download, telechargement, cache.*disque |
| connectivity | @react-native-community/netinfo | 12.0.1 | offline, hors.*ligne, connectivite, reseau.*disponible |
| ota-updates | expo-updates | 57.0.20 | ota, eas.*update, mise.*a.*jour.*a.*chaud |
| dev-client | expo-dev-client | 57.0.17 | dev-client, module.*natif.*custom, prebuild |
| dev-client | expo-build-properties | 57.0.16 | build.*properties, minsdk, deployment.*target |
| rn-testing | jest | 30.5.1 | tests.*unitaires.*mobile, jest |
| rn-testing | jest-expo | 57.0.5 | tests.*unitaires.*mobile, jest |
| rn-testing | @testing-library/react-native | 14.0.1 | tests.*composants, testing-library, render.*screen |
| rn-testing | test-renderer | 1.2.0 | testing-library |
| reactive-state | jotai (alt) | 2.20.3 | jotai, atomic.*state |
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
- `expo-barcode-scanner` — module **retire depuis l'SDK 51**, utiliser `expo-camera` (`CameraView.onBarcodeScanned`)
- `expo-av` — **deprecie**, utiliser `expo-video` (video) et `expo-audio` (son)
- `npm install <lib-native>` pour une lib presente dans le `bundledNativeModules` — utiliser `npx expo install` (cf. §2.3)
- Poser `newArchEnabled: false` dans `app.json` — l'ancienne architecture n'existe plus depuis l'SDK 55

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
- **SSE** : `EventSource` natif (polyfill inclus depuis l'Expo SDK 52) ou `react-native-event-source` (capability `sse`)
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
2. **Le backend reste declare separement** dans `## Active Tech Specs` (par ex. `backend/node-express.md`) — les deux co-existent, projets distincts sous `workspace/src/`
3. **Creer** `workspace/src/{AppName}/` via `create-expo-app` (cf. §2.2.1)
4. **Injecter** `app.json.expo.extra.apiBaseUrl` depuis une nouvelle section `## Active Mobile Config` du `stack.md` (a creer si absente — convention `MOBILE_API_BASE_URL`)
5. **`## Active UI Specs`** : aucun design system web n'est compatible. Stack utilise NativeWind (Tailwind) par defaut. Si `shadcn`/`vuetify`/`radzen-blazor` declare → WARNING bloquant `[STACK_INCOMPAT]`. Alternative mobile : `react-native-paper` (Material), `tamagui`, `gluestack-ui` (capabilities futures)
6. **Phase B (DB)** : SKIP — pas de DB locale par defaut (sauf capability `offline-db` qui ne necessite pas le scan DB serveur)
7. **Phase C (ADRs)** : creer `ADR-{ts}-stack-mobile-react-native.md` documentant Expo SDK 57 + Expo Router + NativeWind 4 (et le choix Tailwind v3, cf. §2.3)

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de "backend interne". Convention :

- `dev-backend` **ne touche pas** au projet mobile RN — il code le backend separe declare dans `## Active Tech Specs backend/*`
- `dev-frontend` materialise **tout** le projet RN : `app/`, `src/`, `assets/`, `app.json`, `package.json`, `tsconfig.json`

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/app/**` (routes Expo Router) | `dev-frontend` |
| `workspace/src/{AppName}/src/**` | `dev-frontend` |
| `workspace/src/{AppName}/assets/**` | `dev-frontend` |
| `workspace/src/{AppName}/app.json` | `arch` (create) + `dev-frontend` (augment permissions, plugins, extra) |
| `workspace/src/{AppName}/package.json` | `arch` (create) + `dev-frontend` (augment deps on-demand) |
| `workspace/src/{AppName}/tsconfig.json` | `arch` exclusif |
| `workspace/src/{AppName}/babel.config.js` / `metro.config.js` | `arch` exclusif |
| `workspace/src/{AppName}/tailwind.config.js` | `arch` (create) + `dev-frontend` (augment theme tokens) |

**Backend separe** : meme matrice ownership que pour son propre stack (`backend/node-express.md`, etc.). Les 2 projets co-existent sous `workspace/src/{BackendName}/` et `workspace/src/{AppName}/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}
npm install --silent
npx --yes tsc --noEmit
test -f app/_layout.tsx
test -f app.json
test -f tailwind.config.js
test -f metro.config.js
grep -q "expo.*57" package.json
grep -q "react-native.*0\.86" package.json
grep -q "react-native-worklets" package.json   # peer obligatoire de reanimated 4
npx --yes expo-doctor                          # gate coherence versions SDK
echo "smoke OK"
```

Smoke complet sur device/simulator : `npx expo start --no-dev --minify` puis ouvrir Expo Go ou simulateur — doit afficher l'app sans crash.
