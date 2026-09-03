# Tech FEAT: swiftui (mobile)

> §2.4 (Librairies) regeneree depuis `swiftui.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id swiftui`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02 (Swift 6.3.3, Xcode 26.6, SDK iOS 26 ; chaque paquet résolu contre l'API GitHub Releases — l'endpoint `/tags`, essayé d'abord, s'est révélé trompeur : il rapportait `firebase-ios-sdk` en 8.15.0 alors que la 12.18.0 est publiée, cf. §2.3). **Jamais exécuté end-to-end via `/sdd-full`**, et il ne peut pas l'être depuis l'environnement courant : compiler ce stack exige un **hôte macOS avec Xcode**, contrainte absolue et non contournable. Non supporté commercialement en l'état.
Tech FEAT ID: tech-swiftui
Scope: **mobile natif iOS** — application **SwiftUI** dans UN seul projet `{AppName}/`. Swift 6.3 en mode langage 6 (concurrence vérifiée par le compilateur), UI déclarative SwiftUI, état par `Observation`, réseau par `URLSession` + `async/await`. UI + state + navigation + accès APIs natives + auth vivent dans le même projet Xcode. **Cible iOS uniquement** (iPadOS / Mac Catalyst / visionOS en cibles optionnelles). Pas de séparation `{BackendName}` / `{LibName}`.

> **Backend séparé** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte déclarée en `## Active Tech Specs`.
>
> ⚠️ **Contrainte d'hôte** : `arch` ne peut ni scaffolder ni valider ce stack depuis Windows ou Linux. Voir §10.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application SwiftUI native** cible iOS 18+ :

- **SwiftUI** : UI déclarative, rendue par les composants du système (ce ne sont **pas** des pixels dessinés comme chez Flutter ou Compose Multiplatform)
- **Observation** (`@Observable`) : état observable depuis Swift 5.9 — remplace `ObservableObject` / `@Published`
- **`async`/`await` + `URLSession`** : réseau natif, sans dépendance
- **Swift 6 language mode** : la sécurité des données concurrentes est **vérifiée à la compilation** (`Sendable`, acteurs). Une course de données devient une erreur de compilation, pas un crash en production.
- **`NavigationStack`** : navigation par pile, pilotée par un chemin typé
- **SwiftData** : persistance locale déclarative (natif, `@Model`)
- **Swift Testing** (`@Test`, `#expect`) : intégré à la toolchain depuis Swift 6

Architecture cible :

```
{AppName}/
├── {AppName}/
│   ├── {AppName}App.swift        ── @main, racine de l'app
│   ├── Core/
│   │   ├── Network/              ── APIClient (URLSession + async/await)
│   │   ├── Storage/              ── Keychain, UserDefaults, SwiftData
│   │   ├── DI/                   ── conteneur Factory
│   │   └── Extensions/
│   ├── Features/
│   │   └── {Feature}/
│   │       ├── Views/            ── vues SwiftUI
│   │       ├── ViewModels/       ── @Observable
│   │       ├── Models/           ── Codable, Sendable
│   │       └── Services/         ── repositories
│   ├── DesignSystem/             ── couleurs, typo, composants
│   ├── Resources/
│   │   ├── Assets.xcassets
│   │   └── Localizable.xcstrings
│   └── Info.plist
├── {AppName}Tests/               ── Swift Testing
├── {AppName}UITests/             ── XCUITest
├── {AppName}.xcodeproj
├── Package.swift                 ── dependances SwiftPM
├── .swiftlint.yml
└── .swift-format
```

**Différence vs les autres stacks `mobiles/`** :
- **C'est le seul stack mono-plateforme du catalogue.** Zéro compromis d'abstraction : chaque API iOS est disponible le jour de sa sortie, sans attendre un binding.
- **Le rendu est celui du système** — pas une imitation. Widgets, App Clips, Live Activities, SharePlay, Apple Watch sont accessibles ; ils ne le sont pas (ou mal) via les stacks cross-platform.
- **Aucun code n'est réutilisable pour Android.** C'est le prix, et il est total.
- Le SDK couvre nativement ce que les autres stacks délèguent à des libs (cf. §2.3), d'où un `core` de **4 paquets** seulement.

---

## 1.2 Couches

- **Views** (`Features/{F}/Views/`) : vues SwiftUI. Sans logique métier — elles lisent un `@Observable` et émettent des intentions.
- **ViewModels** (`Features/{F}/ViewModels/`) : classes `@Observable`, `@MainActor`. Orchestrent les services et exposent l'état de la vue.
- **Models** (`Features/{F}/Models/`) : `struct` `Codable` + `Sendable`. Valeurs immuables.
- **Services** (`Features/{F}/Services/`) : repositories (appels réseau, persistance). Traduisent les erreurs en erreurs de domaine.
- **Core** (`Core/`) : client API, stockage, DI, extensions — transverse.
- **DesignSystem** (`DesignSystem/`) : tokens et composants réutilisables.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Point d'entrée | `{AppName}/{AppName}App.swift` (`@main`) |
| Vue racine | `{AppName}/Features/Root/Views/RootView.swift` |
| Chemin de navigation | `{AppName}/Core/Navigation/AppRoute.swift` (enum `Hashable`) |
| Vue | `{AppName}/Features/{Feature}/Views/{Name}View.swift` |
| ViewModel | `{AppName}/Features/{Feature}/ViewModels/{Name}ViewModel.swift` |
| Modèle | `{AppName}/Features/{Feature}/Models/{Name}.swift` |
| Service / repository | `{AppName}/Features/{Feature}/Services/{Name}Service.swift` |
| Client API | `{AppName}/Core/Network/APIClient.swift` |
| Endpoint | `{AppName}/Core/Network/Endpoints/{Name}Endpoint.swift` |
| Keychain | `{AppName}/Core/Storage/KeychainStore.swift` |
| Modèle SwiftData | `{AppName}/Core/Storage/Models/{Name}Entity.swift` |
| Conteneur DI | `{AppName}/Core/DI/Container+{Feature}.swift` |
| Tokens de design | `{AppName}/DesignSystem/{Colors,Typography,Spacing}.swift` |
| Composant partagé | `{AppName}/DesignSystem/Components/{Name}.swift` |
| Assets | `{AppName}/Resources/Assets.xcassets` |
| Localisation | `{AppName}/Resources/Localizable.xcstrings` |
| Permissions | `{AppName}/Info.plist` (clés `NS*UsageDescription`) |
| Test unitaire | `{AppName}Tests/{Name}Tests.swift` (Swift Testing) |
| Test UI | `{AppName}UITests/{Flow}UITests.swift` (XCUITest) |
| Dépendances SwiftPM | `Package.swift` |

---

## 1.4 Principes non negociables

**Architecture** :
- **`@Observable` uniquement** pour l'état de vue — jamais `ObservableObject` / `@Published`, obsolètes depuis Swift 5.9 et bien moins performants (ils invalident la vue entière plutôt que les propriétés lues).
- **ViewModels en `@MainActor`** — sans quoi Swift 6 refuse de compiler toute mutation d'état depuis un contexte concurrent.
- **`Sendable` sur tout type traversant une frontière de concurrence.** En mode langage 6 c'est vérifié : ne pas contourner par `@unchecked Sendable`.
- **Aucune logique métier dans une `View`** — un `body` contenant une règle métier n'est pas testable.
- **Navigation par chemin typé** (`NavigationStack(path:)` + enum `Hashable`), jamais par une cascade de `NavigationLink` en dur : les deep links deviennent alors impossibles.
- **Réseau par `URLSession` + `async/await`** dans un `APIClient` unique. Ajouter Alamofire est un choix à justifier (§2.3), pas un défaut.
- **`Codable` + `Sendable`** sur tous les DTOs.
- **Listes longues en `List` / `LazyVStack`** — jamais un `VStack` dans un `ScrollView` pour > 50 éléments (tous les enfants seraient construits d'un coup).
- **`Equatable` sur les modèles de vue** — c'est ce qui permet à SwiftUI d'éviter les recalculs de `body`.

**Sécurité mobile** :
- **Tokens JWT / OAuth dans le Keychain** (`KeychainAccess`, CORE) — **jamais** `UserDefaults`, qui est un plist en clair dans le conteneur de l'app.
- **`kSecAttrAccessibleWhenUnlockedThisDeviceOnly`** sur les entrées Keychain sensibles : sinon elles migrent via les sauvegardes iCloud.
- **Aucun secret dans le binaire** — `strings` sur un `.ipa` est trivial. Toute clé sensible passe par le backend proxy.
- **App Transport Security laissée active** — ne pas ajouter `NSAllowsArbitraryLoads` dans `Info.plist`.
- **Permissions juste-à-temps**, chaque clé `NS*UsageDescription` renseignée avec un motif réel (Apple Review rejette les motifs génériques).
- **App Tracking Transparency** (`NSUserTrackingUsageDescription`) si l'IDFA est lu — motif d'un rejet fréquent.
- **Certificate pinning** pour les apps sensibles : `URLSessionDelegate` + `urlSession(_:didReceive:completionHandler:)`.

---

## 1.5 Couches persistantes (locales)

| Type | Lib | Cas d'usage |
|---|---|---|
| Clé-valeur non sensible | `UserDefaults` (**natif**) | Préférences UI, thème, dernier écran |
| **Clé-valeur sensible** | `KeychainAccess` (CORE) | Tokens JWT, credentials, code PIN |
| Persistance déclarative | **SwiftData** (natif, `@Model`) | Défaut pour l'offline-first — aucune dépendance |
| SQL explicite | `GRDB.swift` (capability `offline-db`) | Migrations versionnées, SQL fin, base partagée |
| Fichiers | `FileManager` (**natif**) | Documents, cache disque |

**Mode par défaut** : `UserDefaults` + Keychain + **SwiftData**. SwiftData étant natif, le stack n'a **aucune** dépendance de persistance en `core`.

> **Quand basculer sur GRDB** : SwiftData masque le schéma et ses migrations lourdes sont délicates. Dès que l'US exige des migrations versionnées explicites, des requêtes SQL non exprimables en `#Predicate`, ou une base lisible par un autre outil, prendre la capability `offline-db`.

---

## 1.6 Navigation — NavigationStack + chemin typé

| Cas | Pattern |
|---|---|
| Pile simple | `NavigationStack(path: $path) { ... }` avec `path: [AppRoute]` |
| Destination | `.navigationDestination(for: AppRoute.self) { route in ... }` |
| Onglets | `TabView` contenant un `NavigationStack` **par onglet** (chaque onglet garde sa pile) |
| Modale | `.sheet(item:)` / `.fullScreenCover(item:)` |
| Deep link | `.onOpenURL { url in path = parse(url) }` + Associated Domains pour les Universal Links |
| Retour à la racine | `path.removeAll()` |

**Interdit** : `NavigationLink(destination:)` en dur pour une route métier — le chemin n'est plus programmable, donc les deep links et la restauration d'état sont hors d'atteinte.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-swiftui`
- **Langage** : Swift **6.3.3**, mode langage **6** (concurrence stricte)
- **UI** : SwiftUI (composants système)
- **État** : `Observation` (`@Observable`)
- **Plateforme** : **iOS 18.0+** (cible unique)
- **SDK** : iOS 26
- **IDE / build** : **Xcode 26.6** — obligatoire
- **Hôte** : **macOS uniquement**
- **Package manager** : SwiftPM (`Package.swift` ou Package Dependencies du `.xcodeproj`)
- **Bundle identifier** : `{AppNamespace}`

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/{AppName}.xcodeproj`
- **Résolution des dépendances** : `xcodebuild -resolvePackageDependencies`
- **Build (simulateur)** :
  ```bash
  xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
    -destination 'platform=iOS Simulator,name=iPhone 17' build
  ```
- **Tests** : `xcodebuild test -scheme {AppName} -destination 'platform=iOS Simulator,name=iPhone 17'`
- **Archive / IPA** : `xcodebuild archive` puis `xcodebuild -exportArchive` (certificat Apple Developer requis)
- **Lint** : `swiftlint --strict` (capability `lint`)
- **Format** : `swift-format lint --strict --recursive {AppName}` / `swift-format format -i -r {AppName}`
- **Simulateurs disponibles** : `xcrun simctl list devices available`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && xcodebuild -resolvePackageDependencies -project {AppName}.xcodeproj)
(cd workspace/src/{AppName} && xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
   -destination 'platform=iOS Simulator,name=iPhone 17' build | tail -5)
test -f workspace/src/{AppName}/{AppName}/{AppName}App.swift
```

- **Smoke Timeout** : 600s (résolution SwiftPM + première compilation Xcode)

> ⚠️ **Toutes ces commandes exigent macOS + Xcode.** Sur un autre hôte, `arch` doit émettre `[INFRA_BLOCKED]` — et non un faux vert.

---

## 2.2.1 Init Commands

```bash
if [ ! -d "workspace/src/{AppName}/{AppName}.xcodeproj" ]; then

# STEP 0 — Gate d'hote : bloquant, pas contournable
if [ "$(uname)" != "Darwin" ]; then
  echo "ERROR: arch {AppName} — stack swiftui non scaffoldable"
  echo "CAUSE: [INFRA_BLOCKED] hote $(uname) — Xcode requis (macOS uniquement)"
  echo "FIX: executer le pipeline sur un hote macOS avec Xcode 26+, ou choisir un stack cross-platform (mobiles/flutter, mobiles/react-native)"
  exit 3
fi
xcodebuild -version
swift --version

APP=workspace/src/{AppName}
mkdir -p "$APP"

# STEP 1 — Arborescence applicative
mkdir -p \
  "$APP/{AppName}/Core"/{Network/Endpoints,Storage/Models,DI,Navigation,Extensions} \
  "$APP/{AppName}/Features" \
  "$APP/{AppName}/DesignSystem/Components" \
  "$APP/{AppName}/Resources" \
  "$APP/{AppName}Tests" \
  "$APP/{AppName}UITests"

# STEP 2 — Package.swift : dependances CORE (cf. 2.4.a)
cat > "$APP/Package.swift" <<'SWIFT'
// swift-tools-version: 6.3
import PackageDescription

let package = Package(
    name: "{AppName}Dependencies",
    platforms: [.iOS(.v18)],
    dependencies: [
        .package(url: "https://github.com/apple/swift-collections.git", from: "1.6.0"),
        .package(url: "https://github.com/apple/swift-async-algorithms.git", from: "1.1.5"),
        .package(url: "https://github.com/kishikawakatsumi/KeychainAccess.git", from: "4.2.2"),
        .package(url: "https://github.com/hmlongco/Factory.git", from: "3.3.2"),
    ]
)
SWIFT

# STEP 3 — .swiftlint.yml
cat > "$APP/.swiftlint.yml" <<'YAML'
included:
  - {AppName}
excluded:
  - {AppName}Tests
  - {AppName}UITests
opt_in_rules:
  - empty_count
  - force_unwrapping        # `!` interdit (cf. 5)
  - implicitly_unwrapped_optional
  - redundant_nil_coalescing
  - unowned_variable_capture
line_length:
  warning: 140
  error: 200
type_body_length:
  warning: 300
identifier_name:
  min_length: 2
YAML

# STEP 4 — .swift-format (la version suit la toolchain, cf. 2.3)
cat > "$APP/.swift-format" <<'JSON'
{
  "version": 1,
  "lineLength": 120,
  "indentation": { "spaces": 4 },
  "respectsExistingLineBreaks": true,
  "lineBreakBeforeEachArgument": true
}
JSON

# STEP 5 — Le .xcodeproj n'est PAS generable en ligne de commande
#   Apple ne fournit aucune CLI equivalente a `flutter create` / `ng new` :
#   `xcodebuild` construit un projet, il ne le cree pas. Trois voies possibles,
#   par ordre de preference SDD_Pro :
#     (a) copier le template versionne `.sdd/templates/xcode/{AppName}.xcodeproj`
#         et substituer PRODUCT_NAME / PRODUCT_BUNDLE_IDENTIFIER ;
#     (b) generer via XcodeGen (`xcodegen generate` depuis un project.yml) ;
#     (c) creation manuelle unique par le Tech Lead dans Xcode, puis versionnement.
#   arch retient (a) si le template existe, sinon STOP [INFRA_BLOCKED] avec la
#   consigne (c) — il ne fabrique JAMAIS un project.pbxproj a la main.

# STEP 6 — Resolution des dependances + build de validation
(cd "$APP" && xcodebuild -resolvePackageDependencies -project {AppName}.xcodeproj)
(cd "$APP" && xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
   -destination 'platform=iOS Simulator,name=iPhone 17' build)

fi
```

**Contrat post-init** :
- `{AppName}.xcodeproj` existe et son schéma `{AppName}` construit
- `Package.swift` déclare `swift-tools-version: 6.3` et `platforms: [.iOS(.v18)]`
- `SWIFT_VERSION` = 6 et `SWIFT_STRICT_CONCURRENCY` = `complete` dans les build settings
- `IPHONEOS_DEPLOYMENT_TARGET` = 18.0
- `.swiftlint.yml` et `.swift-format` existent
- `xcodebuild build` sort 0

---

## 2.3 Notes de construction du catalog

### Pourquoi le `core` ne compte que 4 paquets

Ce n'est pas un catalog incomplet : c'est la conséquence de ce que le SDK Apple fournit déjà.

| Besoin | Autres stacks `mobiles/` | Ici |
|---|---|---|
| Client HTTP | `dio`, `ktor`, `axios`, `Refit` | **`URLSession` + `async/await`** (natif) |
| State management | `riverpod`, `zustand`, `koin` | **`Observation`** (natif) |
| Navigation | `go_router`, `expo-router`, `navigation-compose` | **`NavigationStack`** (natif) |
| Persistance locale | `drift`, `sqldelight`, `sqlite-net-pcl` | **`SwiftData`** (natif) |
| DI | `koin`, `hilt`, `get_it` | `@Environment` (natif) + `Factory` pour les services |
| Logs | `logger`, `kermit`, `timber` | **`OSLog`** (natif) |
| Tests | `mocktail`, `mockk`, `xunit` | **`Swift Testing`** (toolchain) |
| Immuabilité / unions | `freezed` | **`struct` + `enum`** (langage) |

Les 4 paquets du `core` comblent des manques réels et précis : structures ordonnées (`swift-collections`), opérateurs `debounce`/`throttle` sur `AsyncSequence` (`swift-async-algorithms`), ergonomie et sûreté du Keychain (`KeychainAccess`), DI compile-safe pour les services (`Factory`).

**Corollaire pour `dev-frontend`** : la règle `[STACK_LIBRARY_MISSING]` s'applique normalement, mais avant de demander l'ajout d'une lib, vérifier la colonne « Ici » ci-dessus. Sur ce stack, la bonne réponse est très souvent une API du SDK.

### Paquets fournis par la toolchain (absents du catalog)

`swift-testing`, `XCTest`, `SwiftData`, `Observation` **n'ont pas de version SwiftPM** : ils sont livrés avec Swift 6 / le SDK iOS. Ils ne figurent donc pas en §2.4 — ce n'est pas un oubli, et `validate_libs_catalog.py` ne peut pas les vérifier. Même situation que `flutter_test` sur `mobiles/flutter.md`.

Corollaire : `swift-format` est pinné sur **603.0.0** parce que sa ligne de version suit la toolchain (603.x ↔ Swift 6.3). Le désynchroniser du compilateur provoque des reformattages en boucle entre développeurs.

### Note de méthode sur la résolution des versions

Les versions ont été résolues via l'API **GitHub Releases** (`/releases/latest`). L'endpoint `/tags`, essayé en premier, s'est révélé **trompeur** : il ne renvoie que les 100 premiers tags dans un ordre non sémantique, ce qui donnait `firebase-ios-sdk` en `8.15.0` alors que la version publiée est `12.18.0`, et `stripe-ios` en `19.4.1` au lieu de `26.9.0`. Toute revalidation doit utiliser `/releases/latest`, en écartant les pré-releases (`siteline/swiftui-introspect` publie par exemple `27.0.0-beta.2`, alors que la dernière stable est `26.0.2`).

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version **stable** de chaque paquet (GitHub Releases, 2026-09-02) | `xcodebuild build` / `test` |
| Version de la toolchain (releases `swiftlang/swift`) | Résolution SwiftPM réelle |
| Xcode / SDK iOS disponibles (images `actions/runner-images`) | Archive / export IPA |
| Cohérence `.md` ↔ `.libs.json` | Pipeline `/sdd-full` complet |

Aucune commande n'a pu être exécutée : l'environnement de construction est Windows. **Le premier run sur macOS doit être traité comme un bench.**

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/swiftui.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id swiftui`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| apple/swift-collections | 1.6.0 | OrderedDictionary / OrderedSet / Deque — absents de la stdlib. Un OrderedDictionary est la structure correcte pour une liste SwiftUI qui doit rester ordonnee ET indexable par identifiant |
| apple/swift-async-algorithms | 1.1.5 | debounce / throttle / combineLatest sur AsyncSequence. Indispensable des qu'un champ de recherche declenche un appel reseau ; il n'y a pas d'equivalent natif |
| kishikawakatsumi/KeychainAccess | 4.2.2 | Wrapper Keychain. L'API brute (SecItemAdd et ses CFDictionary) est verbeuse et facile a mal utiliser — c'est precisement le composant ou une erreur devient une faille |
| hmlongco/Factory | 3.3.2 | Conteneur DI compile-safe et leger. Retenu plutot que Swinject (resolution au runtime) : les dependances manquantes sont detectees a la compilation. @Environment suffit pour l'UI, pas pour injecter un repository dans un @Observable |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| http-client | Alamofire/Alamofire (alt) | 5.12.0 | alamofire, multipart, upload.*progression, retry.*declaratif |
| image-loading | onevcat/Kingfisher | 8.12.0 | image.*distante, avatar, vignette, cache.*image, kingfisher |
| image-loading | kean/Nuke (alt) | 13.2.0 | nuke, pipeline.*image |
| offline-db | groue/GRDB.swift | 7.11.1 | sqlite, offline-first, base.*locale, migration.*locale, grdb |
| offline-db | stephencelis/SQLite.swift (alt) | 0.16.0 | sqlite.swift, requetes.*typees.*sqlite |
| architecture-tca | pointfreeco/swift-composable-architecture | 1.26.2 | composable.*architecture, \btca\b, reducer, architecture.*unidirectionnelle |
| architecture-tca | pointfreeco/swift-dependencies | 1.17.1 | composable.*architecture, \btca\b, swift-dependencies |
| architecture-tca | pointfreeco/swift-sharing (alt) | 2.10.1 | composable.*architecture, \btca\b, swift-sharing |
| snapshot-tests | pointfreeco/swift-snapshot-testing | 1.19.4 | snapshot, regression.*visuelle, test.*rendu, test.*ui.*vue |
| assertions | Quick/Nimble (alt) | 14.0.0 | nimble, matchers, assertions.*expressives |
| sentry | getsentry/sentry-cocoa | 9.26.1 | sentry, error.*tracking, crash.*report, monitoring.*erreurs |
| push | firebase/firebase-ios-sdk | 12.18.0 | push.*notification, fcm, firebase, notification.*distante |
| auth-azure-ad | AzureAD/microsoft-authentication-library-for-objc | 2.15.0 | azure-ad, msal, entra, sso |
| stripe | stripe/stripe-ios | 26.9.0 | stripe, paiement, payment, apple.*pay |
| animations | airbnb/lottie-ios | 4.6.1 | lottie, animation.*apres.*effects, animation.*json |
| uikit-bridge | siteline/swiftui-introspect | 26.0.2 | introspect, uikit.*sous-jacent, personnaliser.*composant.*natif |
| logging | apple/swift-log (alt) | 1.15.0 | swift-log, log.*partage.*backend |
| algorithms | apple/swift-algorithms | 1.2.1 | chunked, permutations, algorithmes.*sequence |
| lint | realm/SwiftLint | 0.65.1 | swiftlint, lint, analyse.*statique |
| lint | swiftlang/swift-format | 603.0.0 | swift-format, formatage, format.*code |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Role | Pattern | Exemple |
|------|---------|---------|
| Point d'entrée | `{AppName}App.swift` → `struct {AppName}App: App` | `MyAppApp.swift` |
| Vue | `{Name}View.swift` → `struct {Name}View: View` | `UserDetailView.swift` |
| ViewModel | `{Name}ViewModel.swift` → `@Observable @MainActor final class {Name}ViewModel` | `UserDetailViewModel.swift` |
| Modèle | `{Name}.swift` → `struct {Name}: Codable, Sendable` | `User.swift` |
| Entité SwiftData | `{Name}Entity.swift` → `@Model final class {Name}Entity` | `UserEntity.swift` |
| Service | `{Name}Service.swift` → `protocol {Name}Service` + `Live{Name}Service` | `UserService.swift` |
| Endpoint | `{Name}Endpoint.swift` → `enum {Name}Endpoint` | `UsersEndpoint.swift` |
| Route | `AppRoute.swift` → `enum AppRoute: Hashable` | — |
| Extension DI | `Container+{Feature}.swift` | `Container+User.swift` |
| Composant de design system | `{Name}.swift` (dans `DesignSystem/Components/`) | `PrimaryButton.swift` |
| Test | `{Name}Tests.swift` → `@Suite struct {Name}Tests` | `UserServiceTests.swift` |
| Test UI | `{Flow}UITests.swift` | `LoginUITests.swift` |

**Conventions de fichier** : `PascalCase.swift` (convention Swift) ; un type principal par fichier, nommé comme le fichier ; extensions dans `{Type}+{Feature}.swift`.

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util` — nommer par la responsabilité
- `Impl` — la convention Swift est `protocol X` + `LiveX` / `MockX`
- `Controller` pour une vue SwiftUI (concept UIKit)
- `ObservableObject` en suffixe (et en type — cf. §5)

---

## 3. Endpoints standard (cote backend separe)

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | flow d'authentification |
| `GET /api/me` | utilisateur courant |

Côté app, la base URL vient d'une **configuration de build** (`.xcconfig`) exposée dans `Info.plist` puis lue via `Bundle.main.object(forInfoDictionaryKey:)` :

- **Dev (simulateur)** : `http://localhost:5000` — le simulateur partage le réseau de l'hôte
- **Dev (device réel)** : IP LAN du Mac
- **Prod** : `https://api.{domain}.com`

> Un `URL` en dur dans le code est un anti-pattern (§5) : il rend impossible la coexistence de schémas Debug / Staging / Release.

---

## 4. Versioning des API consommees

Le backend expose `/api/v1/{domain}`. Côté app : `APIVersion` dans le même `.xcconfig`, envoyé en en-tête par l'`APIClient`. À chaque release, valider que le backend déployé supporte cette version.

Particularité iOS : la revue App Store introduit un délai entre la soumission et la disponibilité, et **les utilisateurs ne mettent pas tous à jour**. Le backend doit donc supporter les `apiVersion` des builds encore installés plus longtemps que sur les autres stacks du catalogue.

---

## 5. Interdits projet (swiftui)

**Architecture** :
- `ObservableObject` / `@Published` — obsolètes depuis Swift 5.9, utiliser `@Observable`
- ViewModel sans `@MainActor`
- `@unchecked Sendable` pour faire taire le compilateur en mode Swift 6
- Logique métier dans un `body` de vue
- `NavigationLink(destination:)` en dur pour une route métier — utiliser un chemin typé
- `VStack` dans `ScrollView` pour > 50 éléments — utiliser `List` / `LazyVStack`
- `DispatchQueue.main.async` en code neuf — utiliser `await MainActor.run` / `@MainActor`
- Combine pour du code neuf — `async/await` + `AsyncSequence`
- `UIViewControllerRepresentable` pour contourner SwiftUI sans justification
- `Task { }` non structuré et non annulé dans une vue — préférer `.task { }`, qui annule à la disparition

**Code quality** :
- **`!` (force unwrap)** — la règle `force_unwrapping` de SwiftLint est activée
- `try!` et `as!`
- Optionnel implicitement déballé (`var x: Foo!`)
- `Any` / `AnyObject` injustifié
- `print()` — utiliser `Logger` (OSLog)
- Fonction de plus de 40 lignes, `body` de plus de 50 lignes — extraire des sous-vues
- `// swiftlint:disable` sans justification en commentaire
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- **Token dans `UserDefaults`** — c'est un plist en clair. Utiliser le Keychain
- Entrée Keychain sans `ThisDeviceOnly` pour un secret sensible (elle migre par iCloud)
- Secret ou clé d'API dans le binaire (`strings` sur un `.ipa` est trivial)
- `NSAllowsArbitraryLoads` dans `Info.plist` (désactive App Transport Security)
- Clé `NS*UsageDescription` absente ou générique → rejet Apple Review
- IDFA lu sans App Tracking Transparency
- Log d'un token en clair
- Universal Link sans Associated Domains vérifié
- Certificate pinning désactivé sur une app bancaire

**Build / packaging** :
- Committer `build/`, `DerivedData/`, `*.xcuserstate`, `.swiftpm/xcode/`
- **NE PAS committer `Package.resolved`** — ici c'est l'inverse : il **doit** être versionné (verrouillage des versions transitives)
- Certificat ou profil de provisioning dans le dépôt
- `SWIFT_STRICT_CONCURRENCY` abaissé sous `complete` pour faire compiler
- `SWIFT_VERSION` sous 6
- `IPHONEOS_DEPLOYMENT_TARGET` modifié sans mise à jour de cette spec
- `project.pbxproj` édité à la main par un agent (format fragile, conflits de merge) — passer par Xcode ou XcodeGen

**Plateforme** :
- API iOS 26 utilisée sans garde `if #available(iOS 26, *)` alors que la cible est 18.0 — **crash à l'exécution sur les OS antérieurs**
- Dimensions en points fixes — utiliser des layouts adaptatifs et respecter Dynamic Type
- Safe areas ignorées
- Dynamic Type et VoiceOver non testés (critères de revue Apple)

---

## 6. Persistance locale — voir §1.5

Stack client → pas de « DB scaffolding » serveur. **SwiftData est natif** : l'offline-first ne coûte aucune dépendance. Pour du SQL explicite : capability `offline-db` (GRDB). Phase B (DB) d'`arch` : **SKIP**.

---

## 7. Temps reel

- **WebSocket** : `URLSessionWebSocketTask` (natif, aucune lib)
- **SSE** : `URLSession.bytes(for:)` + parcours des lignes en `AsyncSequence` (natif)
- **Push** : `UserNotifications` + APNS (natif). La capability `push` (Firebase) n'est nécessaire que si le backend passe **déjà** par FCM — pour de l'APNS pur, tout le SDK Firebase est du poids inutile.
- **Mises à jour en arrière-plan** : `BGTaskScheduler` (natif)

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Apps iOS-only** — ou iOS d'abord, avec un budget Android distinct assumé
- **Qualité d'exécution maximale** : rendu système, respect des Human Interface Guidelines, accessibilité, Dynamic Type
- **Accès immédiat aux nouveautés iOS** — Widgets, Live Activities, App Clips, SharePlay, Apple Watch, visionOS. Aucun stack cross-platform ne les expose correctement.
- **Équipes iOS** existantes
- **Contrainte de taille de binaire** — pas de moteur de rendu embarqué

**NE PAS choisir si** :
- ❌ **Android est nécessaire, même plus tard** — **zéro** code réutilisable. C'est la raison de rejet n°1. Envisager `kotlin-multiplatform` (logique partagée, UI native des deux côtés) ou `flutter`.
- ❌ **Pas d'accès à un hôte macOS + Xcode** — contrainte absolue, y compris en CI
- ❌ **L'équipe n'a pas de compétence Swift/iOS**
- ❌ **Budget pour une seule base de code** couvrant les deux OS
- ❌ **Application interne d'entreprise** avec un parc Android mixte
- ❌ **Time-to-market très court sur deux plateformes** — deux applications natives coûtent deux fois
- ❌ **Réutilisation d'un design system web** → `ionic-capacitor`

> **Composition recommandée** : `swiftui` + `kotlin-android` livrent deux apps natives de qualité maximale, au prix de deux bases de code. `kotlin-multiplatform` est le compromis intermédiaire : logique partagée, UI natives séparées.

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `mobile-swiftui` + `auth-local` (JWT) + backend `dotnet-minimalapi` | 🟡 experimental | jamais validé end-to-end |
| `mobile-swiftui` + `auth-local` + backend `python-fastapi` | 🟡 experimental | jamais validé end-to-end |
| `mobile-swiftui` + `auth-azure-ad` (MSAL iOS) + backend `dotnet-minimalapi` | 🟡 experimental | MSAL objc mature, jamais exercé ici |
| `mobile-swiftui` + `mobile-kotlin-android` (deux apps natives) | 🟡 experimental | nécessite deux `{AppName}` distincts sous `workspace/src/` |

---

## 10. Notes pour l'agent `arch`

1. **STEP 0 — gate d'hôte, bloquant.** Si `uname` ≠ `Darwin`, STOP :
   ```
   ERROR: arch {AppName} — stack swiftui non scaffoldable
   CAUSE: [INFRA_BLOCKED] hote {uname} — Xcode requis (macOS uniquement)
   FIX: executer le pipeline sur un hote macOS avec Xcode 26+, ou choisir mobiles/flutter | mobiles/react-native
   ```
   **Ne pas** produire un scaffolding partiel : un projet Xcode non compilable est plus coûteux qu'une absence de projet.
2. **Détecter** `mobiles/swiftui.md` en `## Active Tech Specs` → stack **mobile-only, mono-plateforme**
3. **Le backend reste déclaré séparément** — les deux projets coexistent sous `workspace/src/`
4. **`.xcodeproj` : pas de génération en ligne de commande.** Apple ne fournit aucune CLI équivalente à `flutter create`. Ordre de préférence : (a) template versionné `.sdd/templates/xcode/`, (b) XcodeGen depuis un `project.yml`, (c) STOP `[INFRA_BLOCKED]` avec consigne de création manuelle par le Tech Lead. **Ne jamais fabriquer un `project.pbxproj` à la main** (format fragile, conflits de merge garantis).
5. **Build settings à imposer** : `SWIFT_VERSION = 6`, `SWIFT_STRICT_CONCURRENCY = complete`, `IPHONEOS_DEPLOYMENT_TARGET = 18.0`, `PRODUCT_BUNDLE_IDENTIFIER = {AppNamespace}`
6. **Injecter** `API_BASE_URL` / `API_VERSION` via un `.xcconfig` référencé dans `Info.plist`, depuis `## Active Mobile Config` (convention `MOBILE_API_BASE_URL`). **Pas** de constante en dur dans le code (§5).
7. **`## Active UI Specs`** : aucun design system web n'est compatible. SwiftUI **est** le design system. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`.
8. **Phase B (DB)** : SKIP — SwiftData est local et natif, la capability `offline-db` ne déclenche pas le scan DB serveur.
9. **`Package.resolved` doit être versionné** (verrouillage transitif) — l'inverse du réflexe « fichier généré ».
10. **Phase C (ADRs)** : créer `ADR-{ts}-stack-mobile-swiftui.md` documentant Swift 6.3 + SwiftUI + Observation, le choix `URLSession` plutôt qu'Alamofire, `SwiftData` plutôt que GRDB, **et la contrainte d'hôte macOS** — qui est une décision d'infrastructure, pas seulement technique.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de « backend interne ». Convention :

- `dev-backend` **ne touche pas** au projet iOS — il code le backend séparé déclaré en `## Active Tech Specs backend/*`
- `dev-frontend` matérialise **tout** le projet iOS : `{AppName}/`, `Package.swift`

**Avant de demander l'ajout d'une lib** (`[STACK_LIBRARY_MISSING]`), consulter la table du §2.3 : sur ce stack, la réponse est très souvent une API du SDK plutôt qu'une dépendance.

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/{AppName}/Features/**` | `dev-frontend` |
| `workspace/src/{AppName}/{AppName}/Core/**` | `dev-frontend` |
| `workspace/src/{AppName}/{AppName}/DesignSystem/**` | `dev-frontend` |
| `workspace/src/{AppName}/{AppName}/Resources/**` | `dev-frontend` |
| `workspace/src/{AppName}/{AppName}/Info.plist` | `arch` (create) + `dev-frontend` (clés de permission) |
| `workspace/src/{AppName}/Package.swift` | `arch` (create) + `dev-frontend` (deps on-demand) |
| `workspace/src/{AppName}/Package.resolved` | **généré** — versionné, jamais édité à la main |
| `workspace/src/{AppName}/*.xcodeproj/**` | `arch` **exclusif** (`project.pbxproj` jamais édité par un agent) |
| `workspace/src/{AppName}/.swiftlint.yml`, `.swift-format` | `arch` exclusif |
| `workspace/src/{AppName}/{AppName}Tests/**`, `{AppName}UITests/**` | `qa` |

---

## 12. Smoke test attendu (post-init arch)

```bash
# Gate d'hote — le reste n'a aucun sens ailleurs
[ "$(uname)" = "Darwin" ] || { echo "SKIP: hote non-macOS"; exit 3; }

cd workspace/src/{AppName}

test -f Package.swift
test -f {AppName}/{AppName}App.swift
test -f .swiftlint.yml
test -d {AppName}.xcodeproj

grep -q "swift-tools-version: 6" Package.swift
grep -q "iOS(.v18)" Package.swift
test -f Package.resolved                                   # doit etre versionne

xcodebuild -resolvePackageDependencies -project {AppName}.xcodeproj

xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
  -destination 'platform=iOS Simulator,name=iPhone 17' build

xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
  -destination 'platform=iOS Simulator,name=iPhone 17' test

# Concurrence stricte + mode langage 6 reellement actifs
xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
  -showBuildSettings | grep -q "SWIFT_STRICT_CONCURRENCY = complete"
xcodebuild -project {AppName}.xcodeproj -scheme {AppName} \
  -showBuildSettings | grep -q "SWIFT_VERSION = 6"

echo "smoke OK"
```
