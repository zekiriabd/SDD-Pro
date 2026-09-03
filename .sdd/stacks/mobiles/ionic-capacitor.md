# Tech FEAT: ionic-capacitor (mobile)

> §2.4 (Librairies) regeneree depuis `ionic-capacitor.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id ionic-capacitor`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02 (Ionic 9.0.1 / Capacitor 8.5.1 / Angular 22.1.4 ; toutes les versions résolues contre le registre npm, peer-dependencies croisées vérifiées). Deux contraintes bloquantes ont été identifiées à la construction et sont documentées en §2.3 : le plafond `typescript <6.1.0` imposé par `@ionic/angular-toolkit` 13, et l'obligation d'inscrire les origines WebView (`capacitor://localhost`, `http://localhost`) dans l'allowlist CORS du backend. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `ionic build` ni `npx cap sync` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-ionic-capacitor
Scope: **mobile hybride** — application **Ionic 9 + Capacitor 8** dans UN seul projet `{AppName}/`. L'app est une **SPA Angular exécutée dans la WebView système** (WKWebView iOS / Android WebView) ; Capacitor expose les APIs natives via des plugins. UI + state + navigation + accès natif vivent dans le même `package.json`. Cible Android + iOS (+ PWA en cible optionnelle quasi gratuite). Pas de séparation `{BackendName}` / `{LibName}`.

> **Backend séparé** : ce stack est PUREMENT client. Il consomme une API backend distincte déclarée en `## Active Tech Specs`.
>
> ⚠️ **Le backend DOIT autoriser les origines WebView en CORS** — c'est la cause n°1 d'échec de ce stack, cf. §2.3.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application Ionic Angular packagée par Capacitor** :

- **Ionic 9** : composants UI web (`ion-*`, web components Stencil) au rendu adaptatif iOS / Material
- **Capacitor 8** : runtime natif + plugins (caméra, GPS, push…). Les dossiers `android/` et `ios/` sont des **projets natifs versionnés**, pas des artefacts de build
- **Angular 22** : standalone components, Signals, `inject()`
- **Angular Router** : le routing d'Ionic est le routeur Angular, enrichi par `IonRouterOutlet` (pile de navigation + transitions natives)
- **PWA quasi gratuite** : le même bundle web se déploie en navigateur

Architecture cible (un seul projet) :

```
{AppName}/
├── src/
│   ├── app/
│   │   ├── app.routes.ts       ── routes Angular (+ gardes auth)
│   │   ├── app.component.ts    ── shell (ion-app / ion-router-outlet)
│   │   ├── core/
│   │   │   ├── interceptors/   ── HttpInterceptor auth + erreurs
│   │   │   ├── services/       ── clients API
│   │   │   ├── native/         ── FACADES des plugins Capacitor
│   │   │   └── guards/
│   │   ├── features/{feature}/
│   │   │   ├── pages/          ── pages Ionic (ion-content)
│   │   │   ├── components/
│   │   │   └── store/          ── signalStore (@ngrx/signals)
│   │   └── shared/
│   ├── environments/           ── apiBaseUrl par environnement
│   ├── theme/variables.scss    ── tokens Ionic (CSS custom properties)
│   └── index.html
├── android/ · ios/             ── projets natifs VERSIONNES
├── capacitor.config.ts
├── ionic.config.json
├── angular.json
└── package.json
```

**Différence vs les autres stacks `mobiles/`** :
- Le code **ne s'exécute pas nativement** : c'est du JS dans une WebView. Perf UI plafonnée par le moteur web du device.
- Pas de bridge à compiler comme React Native : Capacitor appelle les plugins via `postMessage`.
- `android/` et `ios/` sont **committés** (l'inverse d'Expo managed) — les plugins y injectent leur configuration.
- La même base de code sert de **PWA** sans travail supplémentaire.

---

## 1.2 Couches

- **Pages** (`features/{f}/pages/`) : un écran = un composant Angular standalone avec `ion-content`.
- **Components** (`features/{f}/components/`) : composants présentationnels réutilisables.
- **Store** (`features/{f}/store/`) : `signalStore` (`@ngrx/signals`) pour l'état de feature.
- **Services** (`core/services/`) : clients API typés (`HttpClient`), mapping vers modèles.
- **Facades natives** (`core/native/`) : **toute** API Capacitor est encapsulée ici. Aucune page n'importe `@capacitor/*` directement (cf. §1.4).
- **Interceptors / Guards** (`core/`) : auth, gestion d'erreurs, gardes de route.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Shell app | `src/app/app.component.ts` (`ion-app` + `ion-router-outlet`) |
| Table de routes | `src/app/app.routes.ts` |
| Page | `src/app/features/{feature}/pages/{name}/{name}.page.ts` |
| Composant | `src/app/features/{feature}/components/{name}/{name}.component.ts` |
| Store de feature | `src/app/features/{feature}/store/{name}.store.ts` |
| Service API | `src/app/core/services/{domain}.service.ts` |
| **Facade native** | `src/app/core/native/{plugin}.facade.ts` |
| Interceptor HTTP | `src/app/core/interceptors/{name}.interceptor.ts` |
| Garde de route | `src/app/core/guards/{name}.guard.ts` |
| Modèle | `src/app/shared/models/{name}.model.ts` |
| Tokens de thème | `src/theme/variables.scss` |
| Config d'environnement | `src/environments/environment.{ts,prod.ts}` |
| Config Capacitor | `capacitor.config.ts` |
| Permissions Android | `android/app/src/main/AndroidManifest.xml` |
| Permissions iOS | `ios/App/App/Info.plist` |
| Test unitaire | `src/app/**/{name}.spec.ts` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Toute API Capacitor passe par une facade** dans `core/native/`. Une page qui importe `@capacitor/camera` directement est intestable en navigateur et casse le `ionic serve`.
- **Chaque facade gère le cas « pas de natif »** : `Capacitor.isNativePlatform()` doit être testé, avec un fallback web ou une erreur explicite. Sinon toute l'app plante en PWA.
- **Composants standalone** (pas de `NgModule`), `inject()` plutôt que l'injection par constructeur.
- **`@ngrx/signals`** pour l'état partagé ; un `signal()` local suffit pour l'état d'un composant. Pas de `BehaviorSubject` fait main comme store.
- **`IonRouterOutlet`, pas `RouterOutlet`** — sinon aucune transition ni pile de navigation native.
- **Listes longues en `ion-virtual-scroll`** / CDK virtual scroll pour > 50 items. Dans une WebView, une longue liste non virtualisée est bien plus punitive qu'en natif.
- **`ion-content` obligatoire** dans chaque page — c'est lui qui gère le scroll et les safe areas.

**Sécurité mobile** — spécificités WebView :
- **Tokens : jamais dans `localStorage`, `sessionStorage`, `IndexedDB` ni `@capacitor/preferences`.** Aucun de ces stockages n'est chiffré, et le contenu de la WebView est lisible sur appareil rooté/jailbreaké. Utiliser la capability `biometric-secure-storage` (Keychain / Keystore).
- **OAuth dans `@capacitor/browser`** (onglet système), **jamais** dans la WebView de l'app : Google refuse cette configuration et elle est non conforme à la RFC 8252.
- **Aucun secret côté client** — les bundles JS sont trivialement lisibles, plus encore qu'un binaire natif.
- **`server.androidScheme: 'https'`** dans `capacitor.config.ts` (défaut Capacitor) — nécessaire pour un contexte sécurisé et les APIs web modernes.
- **`allowNavigation` restreint** dans `capacitor.config.ts` — sans allowlist, la WebView peut naviguer n'importe où.
- **Content-Security-Policy** dans `index.html`.
- **Permissions juste-à-temps** via l'API `requestPermissions()` de chaque plugin.

---

## 1.5 Couches persistantes (locales)

| Type | Lib | Cas d'usage |
|---|---|---|
| Clé-valeur non sensible | `@capacitor/preferences` (CORE) | Préférences UI, thème, dernier écran |
| **Clé-valeur sensible** | `capacitor-native-biometric` (capability `biometric-secure-storage`) | **Tokens JWT, credentials — seul emplacement acceptable** |
| SQLite natif | `@capacitor-community/sqlite` (capability `offline-db`) | Offline-first, gros jeux de données, chiffrement optionnel |
| Fichiers | `@capacitor/filesystem` (capability `filesystem`) | Export, téléchargement, cache disque |

> **Piège propre à l'hybride** : `localStorage` et `IndexedDB` *fonctionnent* dans la WebView, ce qui en fait un choix tentant. Mais leur persistance **n'est pas garantie** — iOS purge les données de WebView des apps peu utilisées, et Android peut les vider sous pression de stockage. Pour toute donnée qui doit survivre, `@capacitor-community/sqlite`.

---

## 1.6 Navigation — Angular Router + IonRouterOutlet

| Cas | Pattern |
|---|---|
| Route simple | `{ path: 'users', loadComponent: () => import('./users.page') }` |
| Onglets | route parente avec `ion-tabs` + routes enfants |
| Paramètre | `{ path: 'users/:id' }` + `input()` binding de route |
| Garde d'auth | `canActivate: [authGuard]` (garde fonctionnelle) |
| Deep link | `appUrlOpen` de `@capacitor/app` → `router.navigateByUrl()` + App Links / Universal Links déclarés côté natif |

**Interdit** : `RouterOutlet` standard à la place d'`IonRouterOutlet`.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-ionic-capacitor`
- **Langage** : TypeScript **6.0.3** (plafonné, cf. §2.3)
- **Runtime** : Ionic 9.0.1 / Capacitor 8.5.1 / Angular 22.1.4
- **Node** : >= 22 LTS
- **Plateformes** : Android API 23+ / iOS 14+ (planchers Capacitor 8)
- **Modèle d'exécution** : SPA dans WebView système (**pas** de compilation natif)
- **Build system** : Angular CLI (web) + Gradle (Android) + Xcode (iOS)
- **Namespace** : `{AppNamespace}` (`appId` de `capacitor.config.ts`)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/package.json`
- **Run web (dev, rechargement à chaud)** : `(cd workspace/src/{AppName} && ionic serve)`
- **Build web** : `(cd workspace/src/{AppName} && ionic build --prod)`
- **Sync natif** : `(cd workspace/src/{AppName} && npx cap sync)` — **après chaque build et chaque ajout de plugin**
- **Run Android** : `npx cap run android` (Android Studio + JDK 21)
- **Run iOS** : `npx cap run ios` (Xcode, macOS uniquement)
- **Live reload sur device** : `ionic cap run android --livereload --external`
- **Ouvrir l'IDE natif** : `npx cap open android` / `npx cap open ios`
- **Icônes / splash** : `npx capacitor-assets generate` (capability `app-icons`)
- **Type-check** : `npx tsc --noEmit`
- **Lint** : `npx ng lint`
- **Tests** : `npx ng test --watch=false --browsers=ChromeHeadless`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && npm install --silent && npx --yes tsc --noEmit && npx ng build --configuration production)
test -f workspace/src/{AppName}/capacitor.config.ts
test -d workspace/src/{AppName}/android
```

- **Smoke Timeout** : 300s (install + build AOT Angular)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/package.json" ]; then

# STEP 1 — Scaffold Ionic Angular (standalone components, sans NgModule)
npx --yes @ionic/cli@7.2.1 start {AppName} blank \
  --type angular \
  --capacitor \
  --no-git \
  --no-deps \
  --project-id {AppName} \
  --package-id {AppNamespace}

# La CLI Ionic cree le dossier dans le repertoire courant : le deplacer sous workspace/src/
mkdir -p workspace/src && mv {AppName} workspace/src/{AppName}
cd workspace/src/{AppName}

# STEP 2 — Pinner TypeScript AVANT le premier install
# @ionic/angular-toolkit 13 declare `typescript >=5.9.0 <6.1.0` : un `npm install`
# qui resoudrait TypeScript 7.x casse le build AOT. Cf. 2.3.
npm install --save-dev typescript@6.0.3

npm install --silent

# STEP 3 — Plugins Capacitor CORE (cf. 2.4.a)
npm install \
  @capacitor/core@8.5.1 \
  @capacitor/app@8.1.1 \
  @capacitor/haptics@8.0.2 \
  @capacitor/keyboard@8.0.5 \
  @capacitor/status-bar@8.0.3 \
  @capacitor/splash-screen@8.0.2 \
  @capacitor/preferences@8.0.1
npm install --save-dev @capacitor/cli@8.5.1

# STEP 4 — Ajouter les plateformes natives (cree android/ et ios/, A VERSIONNER)
npx cap add android
# iOS uniquement sur hote macOS
if [ "$(uname)" = "Darwin" ]; then npx cap add ios; fi

# STEP 5 — Arborescence applicative
mkdir -p \
  src/app/core/{interceptors,services,native,guards} \
  src/app/features \
  src/app/shared/{models,components,utils} \
  src/theme

# STEP 6 — capacitor.config.ts
cat > capacitor.config.ts <<'TS'
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: '{AppNamespace}',
  appName: '{AppName}',
  webDir: 'www',
  server: {
    // Contexte securise obligatoire pour les APIs web modernes
    androidScheme: 'https',
    // Allowlist stricte : sans elle la WebView peut naviguer n'importe ou
    allowNavigation: [],
  },
  plugins: {
    SplashScreen: { launchAutoHide: false },
  },
};

export default config;
TS

# STEP 7 — Build web PUIS sync natif (l'ordre compte : cap sync copie www/)
npx ng build --configuration production
npx cap sync

# STEP 8 — Gate de coherence
npx --yes tsc --noEmit

fi
```

**Contrat post-init** :
- `capacitor.config.ts` existe, `appId` = `{AppNamespace}`, `androidScheme: 'https'`
- `android/` existe et est **versionné** (et `ios/` sur hôte macOS)
- `package.json` pin `typescript` sur la ligne `6.0`
- `npx cap sync` sort 0
- `npx tsc --noEmit` sort 0

---

## 2.3 Contraintes bloquantes (verifiees a la construction)

### 1. TypeScript est plafonné à `<6.1.0`

`@ionic/angular-toolkit` 13.0.0 déclare :

```
"peerDependencies": { "typescript": ">=5.9.0 <6.1.0", "@angular-devkit/core": ">=21.0.0 <23.0.0", ... }
```

TypeScript **7.0.2 est disponible sur npm** et serait retenu par un `npm install typescript@latest`. Il **viole** ce plafond et casse la compilation AOT Angular. Le catalog pin donc **6.0.3**, et le STEP 2 de §2.2.1 installe ce pin **avant** le premier `npm install`.

C'est la même classe de défaut que celle corrigée sur `react-native` au même audit : **la version npm la plus récente n'est pas la version correcte.** Ici c'est un plafond de peer-dependency, là-bas le `bundledNativeModules` d'Expo.

### 2. CORS — origines WebView

Une app Capacitor **n'émet pas** de requêtes depuis `https://{domain}`. Selon la plateforme, l'`Origin` est :

| Plateforme | Origin envoyée au backend |
|---|---|
| iOS (WKWebView) | `capacitor://localhost` |
| Android (WebView, `androidScheme: 'https'`) | `https://localhost` |
| Android (`androidScheme: 'http'`) | `http://localhost` |
| `ionic serve` (dev navigateur) | `http://localhost:8100` |

**Ces quatre origines doivent figurer dans l'allowlist CORS du backend** (cf. `rules/library-and-stack.md` Partie B — la table B.1 y liste déjà le cas mobile `capacitor://` / `ionic://` comme CORS obligatoire). Sans elles : préflight `OPTIONS` rejeté, `fetch` en échec silencieux, logs backend vides. Symptôme classique — l'app marche en `ionic serve` et échoue sur device.

`arch` doit propager ces origines au STEP 4.5.6 de propagation de config, comme il le fait pour les ports 5173 / 4200 des stacks web.

### 3. Contraintes Angular croisées

| Paquet | Contrainte | Conséquence |
|---|---|---|
| `@ionic/angular` 9.0.1 | `@angular/core >=18.0.0` | plancher |
| `@ngrx/signals` 22.0.0 | `@angular/core ^22.0.0` | **fixe la majeure : Angular 22** |
| `@ionic/angular-toolkit` 13.0.0 | `@angular-devkit/* >=21 <23` | Angular 22 compatible |

D'où le pin **Angular 22.1.4** sur tout le stack.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque paquet (registre npm, 2026-09-02) | `ionic build`, `npx cap sync` |
| Peer-dependencies croisées (tables ci-dessus) | Build APK / IPA |
| Cohérence `.md` ↔ `.libs.json` | `ng test` sur un projet généré |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/ionic-capacitor.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id ionic-capacitor`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| @ionic/angular | 9.0.1 | Composants UI Ionic pour Angular (ion-*) — look adaptatif iOS/Material |
| @ionic/core | 9.0.1 | Web components sous-jacents (Stencil) — peer de @ionic/angular |
| ionicons | 8.1.0 | Jeu d'icones officiel Ionic |
| @capacitor/core | 8.5.1 | Runtime Capacitor — pont JS <-> natif |
| @capacitor/cli | 8.5.1 | CLI (sync, copy, open) — devDependency |
| @capacitor/android | 8.5.1 | Projet natif Android (wrapper WebView) |
| @capacitor/ios | 8.5.1 | Projet natif iOS (wrapper WKWebView) |
| @capacitor/app | 8.1.1 | Cycle de vie app + bouton retour Android + deep links (appUrlOpen) |
| @capacitor/haptics | 8.0.2 | Retour haptique — attendu par les composants Ionic |
| @capacitor/keyboard | 8.0.5 | Evenements clavier — sans lui les formulaires sont masques par le clavier iOS |
| @capacitor/status-bar | 8.0.3 | Style de la barre d'etat (indispensable en mode sombre) |
| @capacitor/splash-screen | 8.0.2 | Masque le flash blanc de la WebView au demarrage |
| @capacitor/preferences | 8.0.1 | Cle-valeur NON sensible (NSUserDefaults / SharedPreferences). PAS pour les tokens — cf. capability biometric-secure-storage |
| @angular/core | 22.1.4 |  |
| @angular/common | 22.1.4 |  |
| @angular/forms | 22.1.4 | Peer declare par @ionic/angular 9 |
| @angular/router | 22.1.4 | Peer declare par @ionic/angular 9 — routing des pages Ionic |
| @angular/platform-browser | 22.1.4 |  |
| @angular/compiler | 22.1.4 |  |
| rxjs | 7.8.2 | Peer Angular + @ionic/angular (>=7.5.0) |
| zone.js | 0.16.2 | Peer Angular (>=0.13.0) |
| typescript | 6.0.3 | PIN OBLIGATOIRE sur la ligne 6.0 : @ionic/angular-toolkit 13 declare `typescript >=5.9.0 <6.1.0`. TypeScript 7.x est disponible sur npm mais INTERDIT ici |
| @angular/cli | 22.1.6 | devDependency — build et serve |
| @angular/compiler-cli | 22.1.4 | devDependency — compilation AOT |
| @ionic/angular-toolkit | 13.0.0 | devDependency — schematics Ionic (ng generate page) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| connectivity | @capacitor/network | 8.0.1 | offline, hors.*ligne, connectivite, reseau.*disponible |
| app-metadata | @capacitor/device | 8.0.3 | modele.*appareil, device.*info, os.*version, uuid.*appareil |
| filesystem | @capacitor/filesystem | 8.1.3 | fichier.*local, telechargement, export.*fichier, download |
| camera | @capacitor/camera | 8.2.4 | camera, photo, gallerie, image-picker |
| location | @capacitor/geolocation | 8.2.2 | gps, geolocalisation, position.*utilisateur |
| maps | @capacitor/google-maps | 8.0.1 | maps, carte, marker, google.*maps |
| push | @capacitor/push-notifications | 8.1.2 | push.*notification, notification.*distante, fcm, apns |
| local-notification | @capacitor/local-notifications | 8.3.1 | notification.*locale, rappel, reminder, notification.*planifiee |
| share | @capacitor/share | 8.0.1 | partager, share.*sheet, partage.*natif |
| auth-local | @capacitor/browser | 8.0.4 | oauth, oidc, auth.*navigateur, in-app.*browser |
| clipboard | @capacitor/clipboard | 8.0.1 | presse-papier, clipboard, copier.*coller |
| native-dialogs | @capacitor/action-sheet | 8.1.1 | action.*sheet, menu.*natif |
| native-dialogs | @capacitor/dialog | 8.0.1 | dialogue.*natif, alert.*natif, confirm.*natif |
| native-dialogs | @capacitor/toast | 8.0.1 | toast, message.*bref |
| a11y | @capacitor/screen-reader | 8.0.1 | accessibilite, lecteur.*ecran, voiceover, talkback |
| offline-db | @capacitor-community/sqlite | 8.1.1 | sqlite, offline-first, base.*locale, persistance.*locale |
| barcode | @capacitor-mlkit/barcode-scanning | 8.1.1 | scan.*qr, scan.*barcode, code-barre |
| biometric-secure-storage | capacitor-native-biometric | 4.2.2 | biometric, face-id, touch-id, empreinte, token.*securise |
| state-management | @ngrx/signals | 22.0.0 | state.*global, store, signal.*store, ngrx |
| app-icons | @capacitor/assets | 3.0.5 | icone.*application, splash.*screen, app.*icon |
| ionic-unit-tests | jasmine-core | 7.0.2 | tests.*unitaires, jasmine, karma |
| ionic-unit-tests | karma | 6.4.4 | tests.*unitaires, jasmine, karma |
| ionic-unit-tests | karma-jasmine | 5.1.0 | tests.*unitaires, karma |
| ionic-unit-tests | karma-chrome-launcher | 3.2.0 | tests.*unitaires, karma |
| ionic-unit-tests | karma-coverage | 2.2.1 | coverage, couverture.*tests |
| ionic-unit-tests | @types/jasmine | 6.0.0 | tests.*unitaires, jasmine |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Role | Pattern | Exemple |
|------|---------|---------|
| Page | `{name}.page.ts` → classe `{Name}Page` | `user-detail.page.ts` / `UserDetailPage` |
| Composant | `{name}.component.ts` → `{Name}Component` | `user-card.component.ts` |
| Service API | `{domain}.service.ts` → `{Domain}Service` | `users.service.ts` |
| **Facade native** | `{plugin}.facade.ts` → `{Plugin}Facade` | `camera.facade.ts` / `CameraFacade` |
| Store | `{name}.store.ts` → `{Name}Store` | `users.store.ts` |
| Garde | `{name}.guard.ts` → `{name}Guard` (fonction) | `auth.guard.ts` / `authGuard` |
| Interceptor | `{name}.interceptor.ts` → `{name}Interceptor` | `auth.interceptor.ts` |
| Modèle | `{name}.model.ts` → interface `{Name}` | `user.model.ts` / `User` |
| Test | `{name}.spec.ts` à côté du sujet | `users.service.spec.ts` |

**Conventions de fichier** : `kebab-case` + suffixe de rôle (convention Angular) ; classes en `PascalCase`.

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util`
- `Impl` (pas de convention d'interface/implémentation en Angular)
- Une page sans le suffixe `.page.ts` (elle devient indistinguable d'un composant)
- Un service qui appelle un plugin Capacitor mais s'appelle `.service.ts` — s'il encapsule du natif, c'est `.facade.ts`

---

## 3. Endpoints standard (cote backend separe)

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck (état de connectivité) |
| `POST /api/auth/login` | flow d'authentification |
| `GET /api/me` | utilisateur courant |
| `OPTIONS *` | **préflight CORS — doit répondre 204/200 avec les origines du §2.3** |

Côté app, la base URL vit dans `src/environments/environment{,.prod}.ts` (mécanisme `fileReplacements` d'Angular) :

- **Dev navigateur** : `http://localhost:5000`
- **Dev device Android** : `http://10.0.2.2:5000` (émulateur) ou l'IP LAN de la machine (device réel)
- **Prod** : `https://api.{domain}.com`

---

## 4. Versioning des API consommees

Le backend expose `/api/v1/{domain}`. Côté app : `environment.apiVersion`, envoyé en en-tête par l'interceptor HTTP. À chaque release, valider que le backend déployé supporte cette version.

Particularité hybride : les mises à jour web peuvent être livrées **hors store** via Capacitor Live Updates / Appflow, ce qui découple le cycle de release du client de celui des stores — mais aussi du backend. La `apiVersion` en devient d'autant plus load-bearing.

---

## 5. Interdits projet (ionic-capacitor)

**Architecture** :
- Import direct de `@capacitor/*` dans une page ou un composant — passer par `core/native/*.facade.ts`
- Facade sans garde `Capacitor.isNativePlatform()` — l'app casse en PWA / `ionic serve`
- `RouterOutlet` à la place d'`IonRouterOutlet`
- Page sans `ion-content`
- `NgModule` pour une nouvelle feature — composants standalone uniquement
- `BehaviorSubject` utilisé comme store global — `@ngrx/signals`
- Liste non virtualisée > 50 items
- `document.querySelector` pour manipuler un composant Ionic — utiliser `ViewChild` / les Signals

**Code quality** :
- `any` injustifié
- `subscribe()` sans `takeUntilDestroyed()` — fuite mémoire
- Logique métier dans un template
- `console.log` en production
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- **Token dans `localStorage` / `sessionStorage` / `IndexedDB` / `@capacitor/preferences`** — aucun n'est chiffré. Utiliser la capability `biometric-secure-storage`
- Flow OAuth dans la WebView de l'app — utiliser `@capacitor/browser` (onglet système)
- Secret ou clé d'API dans le bundle JS
- `allowNavigation: ['*']` dans `capacitor.config.ts`
- `androidScheme: 'http'` en production (contexte non sécurisé)
- Absence de Content-Security-Policy dans `index.html`
- `webContentsDebuggingEnabled` laissé actif en release
- Certificate pinning désactivé sur une app bancaire

**Build / packaging** :
- **NE PAS ignorer `android/` et `ios/` dans git** — ici c'est l'inverse d'Expo managed : ce sont des projets natifs versionnés que les plugins configurent
- Committer `node_modules/`, `www/`, `android/build/`, `ios/App/Pods/`, `.angular/`
- Oublier `npx cap sync` après un build ou l'ajout d'un plugin — le device continue de servir l'ancien `www/`
- Laisser `npm install` remonter TypeScript au-delà de `6.0.x` (cf. §2.3)
- Permissions excessives dans `AndroidManifest.xml` / `Info.plist`
- APK release non signé

**Plateformes** :
- Supposer le natif disponible — tester `Capacitor.getPlatform()`
- Ignorer les safe areas (`--ion-safe-area-*`) → contenu sous l'encoche
- Utiliser une API web non supportée par la WebView cible sans repli

---

## 6. Persistance locale — voir §1.5

Stack client → pas de « DB scaffolding » serveur. Offline-first réel : capability `offline-db` (`@capacitor-community/sqlite`). Phase B (DB) d'`arch` : **SKIP**.

---

## 7. Temps reel

- **WebSocket** : `WebSocket` natif du navigateur (aucune lib) — fonctionne tel quel dans la WebView
- **SSE** : `EventSource` natif. ⚠️ Se déconnecte en arrière-plan, quand l'OS suspend la WebView : prévoir la reconnexion sur l'événement `resume` de `@capacitor/app`
- **Push** : capability `push` (`@capacitor/push-notifications`) + APNS (iOS) / FCM (Android) côté backend
- **Notifications locales** : capability `local-notification`

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Équipes web** (Angular / TypeScript) livrant du mobile **sans apprendre de nouvelle plateforme** — c'est son argument décisif
- **Apps orientées formulaires / CRUD / back-office mobile**
- **Mobile + PWA depuis une seule base de code**
- **Réutilisation d'un design system web existant**
- **Time-to-market court** avec une équipe web déjà en place

**NE PAS choisir si** :
- ❌ **Perf UI ou animations exigeantes** — tout passe par une WebView. C'est le plafond structurel du stack. Préférer `flutter` ou du natif.
- ❌ **Le look natif est un critère** — Ionic imite iOS/Material en CSS ; les composants ne sont pas ceux du système
- ❌ **Accès matériel intensif** (BLE custom, NFC bas niveau, traitement d'image temps réel) — chaque appel traverse le pont JS↔natif
- ❌ **Jeux ou rendu graphique** → moteur dédié
- ❌ **Équipe React** → `react-native` ; **équipe .NET** → `maui` ; **équipe Kotlin** → `kotlin-multiplatform`
- ❌ **Contrainte de démarrage à froid forte** — l'initialisation de la WebView s'ajoute au temps de lancement
- ❌ **Politique de sécurité interdisant le code interprété côté client** — le bundle JS est trivialement lisible

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `mobile-ionic-capacitor` + `auth-local` (JWT) + backend `node-express` | 🟡 experimental | jamais validé end-to-end |
| `mobile-ionic-capacitor` + `auth-local` + backend `dotnet-minimalapi` | 🟡 experimental | jamais validé end-to-end |
| `mobile-ionic-capacitor` + `auth-azure-ad` + backend `dotnet-minimalapi` | 🟡 experimental | MSAL via `@capacitor/browser` — à instruire avant engagement |
| `mobile-ionic-capacitor` + `qa-angular-jasmine` | 🟡 experimental | capability `ionic-unit-tests` alignée sur `qa/angular-jasmine.md` |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `mobiles/ionic-capacitor.md` en `## Active Tech Specs` → stack **mobile-only**, pas un frontend web (même si la techno est du web)
2. **Le backend reste déclaré séparément** — les deux projets coexistent sous `workspace/src/`
3. **Créer** `workspace/src/{AppName}/` via `@ionic/cli start` (cf. §2.2.1). ⚠️ La CLI crée le dossier dans le répertoire courant : le STEP 1 le déplace ensuite.
4. **Pinner TypeScript sur `6.0.3` AVANT le premier `npm install`** — sinon la résolution remonte en 7.x et casse le build AOT (§2.3)
5. **CORS — action obligatoire** : ajouter `capacitor://localhost`, `https://localhost`, `http://localhost` et `http://localhost:8100` à l'allowlist CORS du backend au STEP 4.5.6 de propagation de config. **Sans cela, l'app échoue sur device tout en marchant en `ionic serve`** — le mode d'échec le plus coûteux à diagnostiquer sur ce stack.
6. **Injecter** `apiBaseUrl` / `apiVersion` dans `src/environments/environment{,.prod}.ts` depuis `## Active Mobile Config` (convention `MOBILE_API_BASE_URL`)
7. **`## Active UI Specs`** : Ionic **est** le design system. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`. `ui/vuetify` est particulièrement incompatible (Vue).
8. **`android/` et `ios/` sont versionnés** — ne pas les ajouter au `.gitignore` (l'inverse de `react-native` en Expo managed)
9. **`npx cap sync` après le build web** — l'ordre compte, `sync` copie `www/`
10. **Phase B (DB)** : SKIP. La capability `offline-db` ne déclenche pas le scan DB serveur.
11. **Phase C (ADRs)** : créer `ADR-{ts}-stack-mobile-ionic-capacitor.md` documentant Ionic 9 + Capacitor 8 + Angular 22, le plafond TypeScript et la liste des origines CORS.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de « backend interne ». Convention :

- `dev-backend` **ne touche pas** au projet Ionic — il code le backend séparé déclaré en `## Active Tech Specs backend/*`. **Il doit en revanche honorer l'allowlist CORS du §2.3.**
- `dev-frontend` matérialise **tout** le projet Ionic : `src/`, `capacitor.config.ts`, `package.json`

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/src/app/**` | `dev-frontend` |
| `workspace/src/{AppName}/src/theme/**` | `dev-frontend` |
| `workspace/src/{AppName}/src/environments/**` | `arch` (create) + `dev-frontend` (ajout de clés) |
| `workspace/src/{AppName}/capacitor.config.ts` | `arch` (create) + `dev-frontend` (config de plugin) |
| `workspace/src/{AppName}/package.json` | `arch` (create) + `dev-frontend` (deps on-demand) |
| `workspace/src/{AppName}/angular.json` / `tsconfig.json` | `arch` exclusif |
| `workspace/src/{AppName}/android/**` / `ios/**` | `arch` (create via `cap add`) + `dev-frontend` (permissions uniquement) |
| `workspace/src/{AppName}/**/*.spec.ts` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}
npm install --silent
npx --yes tsc --noEmit
npx ng build --configuration production
npx cap sync

test -f capacitor.config.ts
test -f ionic.config.json
test -d android
test -d www
grep -q "\"typescript\": \"6\.0\." package.json          # plafond <6.1 (cf. 2.3)
grep -q "androidScheme: 'https'" capacitor.config.ts     # contexte securise
grep -q "@ionic/angular" package.json
grep -q "@capacitor/core" package.json
echo "smoke OK"
```

Smoke complet sur device / émulateur : `npx cap run android` — l'app doit démarrer sans écran blanc et joindre `GET /api/health`. **Un écran blanc au lancement est presque toujours (a) un `cap sync` oublié, soit (b) un rejet CORS** (§2.3).
