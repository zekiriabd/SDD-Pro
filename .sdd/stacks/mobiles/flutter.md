# Tech FEAT: flutter (mobile)

> §2.4 (Librairies) regeneree depuis `flutter.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id flutter`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02 (toolchain Flutter 3.47.2 / Dart 3.13.2 stable du 2026-08-27 ; chaque version du catalog résolue contre l'API pub.dev, contraintes inter-paquets vérifiées : famille Riverpod co-versionnée sur `riverpod: 3.4.2`, plancher `freezed >=3.13.0` compatible avec le Dart embarqué, `go_router 18` exigeant `flutter >=3.44.0`). **Jamais exécuté end-to-end via `/sdd-full`** : aucun `flutter build apk` ni `flutter test` n'a tourné en CI (SDK Flutter absent de l'environnement). Validation runtime à programmer — cf. §2.3. Non supporté commercialement en l'état.
Tech FEAT ID: tech-flutter
Scope: **mobile cross-platform** — application **Flutter 3.47** dans UN seul projet `{AppName}/`. Single codebase Dart compilé AOT en ARM natif, rendu par le moteur **Impeller**. UI + state + navigation + accès APIs natives + auth vivent dans le même `pubspec.yaml`. Cible Android + iOS (+ Web / desktop en cibles optionnelles). Pas de séparation `{BackendName}` / `{LibName}`.

> **Backend séparé** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte déclarée en `## Active Tech Specs` (ex. `backend/dotnet-minimalapi.md`, `backend/python-fastapi.md`). Pour une app sans backend propre → Backend-as-a-Service (Supabase, Firebase, Appwrite) configuré via `--dart-define`.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application Flutter** cible Android + iOS :

- **Riverpod 3** (state management + injection de dépendances) — providers générés par annotation `@riverpod`, typés à la compilation
- **go_router 18** (routing déclaratif officiel) — deep links, redirections de garde auth, routes typées
- **Dio** (client HTTP) — interceptors auth/retry/log, timeouts, annulation
- **Freezed** (modèles immuables + unions scellées) pour les états UI et les DTOs
- **Impeller** : moteur de rendu par défaut (Skia est le fallback legacy)
- **Dart 3.13** : `sealed class`, pattern matching exhaustif, records, null-safety stricte

Architecture cible (un seul projet Flutter) :

```
{AppName}/
├── lib/
│   ├── main.dart              ── bootstrap + ProviderScope
│   ├── app.dart               ── MaterialApp.router + thème
│   ├── core/
│   │   ├── router/            ── GoRouter + gardes d'auth
│   │   ├── network/           ── Dio + interceptors
│   │   ├── storage/           ── SecureStorage / SharedPreferences
│   │   ├── theme/             ── ColorScheme, TextTheme, tokens
│   │   └── error/             ── Failure, exception -> Failure
│   ├── features/
│   │   └── {feature}/
│   │       ├── domain/        ── entités Freezed + interfaces de repository
│   │       ├── data/          ── DTOs, datasources, impl de repository
│   │       └── presentation/  ── écrans, widgets, providers
│   └── shared/                ── widgets et utilitaires transverses
├── test/                      ── tests unitaires + widget
├── integration_test/          ── tests d'intégration (SDK)
├── assets/                    ── images, fonts, i18n
├── android/ · ios/            ── projets natifs (permissions, signature)
├── pubspec.yaml
├── analysis_options.yaml
└── build.yaml                 ── config du codegen
```

**Différence vs `mobiles/react-native.md`** :
- Pas de bridge JS ni de bundler — Dart est compilé **AOT** en code machine ARM
- Le rendu ne délègue pas aux widgets natifs : Flutter dessine chaque pixel (Impeller) → rendu identique sur les deux OS, mais rien n'est « natif » visuellement par défaut
- Pas de Metro / hot reload JS : hot reload Dart VM en debug, AOT en release
- Un seul langage (Dart) sans TypeScript ni couche de types séparée

---

## 1.2 Couches

- **Domain** (`features/{f}/domain/`) : entités Freezed, interfaces de repository, use cases. **Aucun import Flutter** — Dart pur, testable sans widget tree.
- **Data** (`features/{f}/data/`) : DTOs `json_serializable`, datasources (Dio, Drift), implémentations de repository. Traduit toute exception en `Failure`.
- **Presentation** (`features/{f}/presentation/`) : écrans, widgets, providers Riverpod. Ne connaît que le domain.
- **Core** (`core/`) : router, réseau, stockage, thème, erreurs — transverse.
- **Shared** (`shared/`) : widgets réutilisables et helpers purs.

Règle de dépendance : `presentation → domain ← data`. Le domain ne dépend de rien.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas** (ils peuvent décrire le backend séparé consommé, pas la structure du projet Flutter). Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path |
|---|---|
| Entrypoint | `lib/main.dart` (`runApp(ProviderScope(child: App()))`) |
| App shell | `lib/app.dart` (`MaterialApp.router`) |
| Route table | `lib/core/router/app_router.dart` |
| Écran | `lib/features/{feature}/presentation/screens/{name}_screen.dart` |
| Widget de feature | `lib/features/{feature}/presentation/widgets/{name}.dart` |
| Provider Riverpod | `lib/features/{feature}/presentation/providers/{name}_provider.dart` |
| Entité domain | `lib/features/{feature}/domain/entities/{name}.dart` |
| Interface repository | `lib/features/{feature}/domain/repositories/{name}_repository.dart` |
| Use case | `lib/features/{feature}/domain/usecases/{verb}_{name}.dart` |
| DTO | `lib/features/{feature}/data/models/{name}_dto.dart` |
| Datasource | `lib/features/{feature}/data/datasources/{name}_remote_datasource.dart` |
| Impl repository | `lib/features/{feature}/data/repositories/{name}_repository_impl.dart` |
| Client HTTP | `lib/core/network/dio_client.dart` |
| Tokens de thème | `lib/core/theme/app_theme.dart` |
| Widget partagé | `lib/shared/widgets/{name}.dart` |
| Test unitaire / widget | `test/{mirror du chemin lib}_test.dart` |
| Test d'intégration | `integration_test/{flow}_test.dart` |
| Assets | `assets/{images,fonts,i18n}/` |
| Manifeste projet | `pubspec.yaml` |
| Lints | `analysis_options.yaml` |
| Config codegen | `build.yaml` |
| Permissions Android | `android/app/src/main/AndroidManifest.xml` |
| Permissions iOS | `ios/Runner/Info.plist` |

---

## 1.4 Principes non negociables

**Architecture** :
- **Riverpod uniquement** pour le state applicatif. `setState` reste permis pour un état **purement local** à un widget (champ de saisie, animation). Jamais `InheritedWidget` à la main.
- **Riverpod OU BLoC, jamais les deux** dans le même projet (la capability `state-management-alt` est exclusive de `flutter_riverpod`).
- **Le domain n'importe pas `package:flutter`** — s'il faut un `BuildContext` dans une entité, la couche est mal découpée.
- **Toute réponse API passe par un DTO** puis est mappée vers une entité domain. Jamais de `Map<String, dynamic>` au-delà de la couche data.
- **Toute exception est traduite en `Failure`** dans la couche data. La présentation ne voit jamais de `DioException`.
- **Routes déclarées dans go_router**, jamais de `Navigator.push(MaterialPageRoute(...))` ad-hoc — sinon les deep links et les gardes d'auth sont contournés.
- **`const` sur tout widget qui peut l'être** — c'est la première optimisation de rebuild de Flutter.
- **Listes longues en `ListView.builder`** (ou `SliverList`), jamais `ListView(children: [...])` pour > 50 items : la seconde forme construit tous les enfants d'un coup.
- **Codegen commité** : les `*.freezed.dart` / `*.g.dart` sont versionnés (cf. §5) pour que le build ne dépende pas d'un `build_runner` réussi en CI.

**Sécurité mobile** :
- **Tokens JWT / OAuth dans `flutter_secure_storage`** (Keychain iOS, Keystore Android) — JAMAIS `shared_preferences`, qui écrit en clair dans un plist / XML lisible sur appareil rooté.
- **Aucun secret côté client** — toute clé sensible passe par le backend proxy déclaré en `## Active Tech Specs`.
- **`--dart-define` pour la config d'environnement**, jamais de constante en dur dans le code. Attention : `--dart-define` n'est **pas** un mécanisme de secret (les valeurs sont dans le binaire) — uniquement pour des URLs et des flags.
- **Permissions juste-à-temps** via `permission_handler`, jamais au démarrage.
- **Certificate pinning** pour les apps sensibles : `badCertificateCallback` sur le `HttpClient` de Dio.

---

## 1.5 Couches persistantes (locales)

Ce stack est CLIENT mobile — la persistance « base de données » réelle vit côté backend. En local :

| Type | Lib | Cas d'usage |
|---|---|---|
| Clé-valeur non sensible | `shared_preferences` (CORE) | Préférences UI, thème, dernier écran |
| Clé-valeur sensible | `flutter_secure_storage` (CORE) | Tokens JWT, credentials, code PIN |
| SQLite typé (offline-first) | `drift` + `sqlite3` (capability `offline-db`) | Apps offline-first, gros jeux de données |
| Fichiers | `path_provider` (capability `offline-db`) | Résout le répertoire documents / cache |

**Mode par défaut** : `shared_preferences` + `flutter_secure_storage`. Suffisant pour la majorité des apps.

> **Piège fermé au montage du catalog** : `sqlite3_flutter_libs` est **mort**. Sa dernière version publiée est `0.6.0+eol`, dont la description est littéralement « Not used anymore, update to version 3.x of package:sqlite3 instead ». Le catalog déclare donc `sqlite3` 3.5.2 (qui embarque désormais les bibliothèques natives), et **pas** l'ancien paquet — c'est exactement le genre de dépendance fantôme que l'audit `mobiles/` du 2026-09-02 a éliminé sur les autres stacks.

---

## 1.6 Navigation — go_router

`go_router` est le routeur officiel maintenu par l'équipe Flutter. Il est retenu sans alternative dans ce stack.

| Cas | Pattern |
|---|---|
| Route simple | `GoRoute(path: '/users', builder: ...)` |
| Route imbriquée + bottom nav | `StatefulShellRoute.indexedStack` |
| Paramètre de route | `GoRoute(path: '/users/:id')` + `state.pathParameters['id']` |
| Garde d'authentification | `redirect:` au niveau du `GoRouter`, alimenté par un provider Riverpod d'auth |
| Deep link | déclaré dans `AndroidManifest.xml` (App Links) + `Info.plist` (Universal Links) |

**Interdit** : `Navigator.push` direct pour une route nommée du router — contourne les gardes et casse les deep links.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-flutter`
- **Langage** : Dart 3.13.2 (null-safety stricte, `sealed`, records, pattern matching)
- **Runtime / SDK** : Flutter **3.47.2** (canal `stable`, publié le 2026-08-27)
- **Contrainte SDK du projet** : `environment.sdk: ^3.13.0` (cf. §2.3)
- **Moteur de rendu** : Impeller
- **Plateformes** : Android API 24+ (Android 7.0) / iOS 15.0+
- **Build system** : Flutter CLI (Gradle sous Android, Xcode sous iOS)
- **Package manager** : `pub` (`flutter pub add` → `pubspec.yaml`)
- **Namespace** : `{AppNamespace}` (`applicationId` Android, `PRODUCT_BUNDLE_IDENTIFIER` iOS)

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/pubspec.yaml`
- **Run dev (hot reload)** : `(cd workspace/src/{AppName} && flutter run)`
- **Run Android** : `(cd workspace/src/{AppName} && flutter run -d android)` — nécessite Android Studio + JDK 17
- **Run iOS** : `(cd workspace/src/{AppName} && flutter run -d ios)` — nécessite Xcode (macOS uniquement)
- **Build APK / AAB** : `flutter build apk --release` / `flutter build appbundle --release`
- **Build IPA** : `flutter build ipa --release` (macOS + certificat Apple Developer)
- **Codegen** : `dart run build_runner build --delete-conflicting-outputs`
- **Codegen (watch)** : `dart run build_runner watch --delete-conflicting-outputs`
- **Audit toolchain** : `flutter doctor -v` — **gate obligatoire** avant tout build
- **Tests** : `flutter test` (unitaires + widget) / `flutter test integration_test` (E2E)
- **Lint / analyse** : `flutter analyze --fatal-infos`
- **Format** : `dart format --set-exit-if-changed lib test`
- **Deps obsolètes** : `flutter pub outdated`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && flutter pub get && dart run build_runner build --delete-conflicting-outputs && flutter analyze --fatal-infos)
test -f workspace/src/{AppName}/pubspec.yaml
test -f workspace/src/{AppName}/lib/main.dart
```

- **Smoke Timeout** : 300s (`pub get` + codegen + analyse ; le codegen Dart est lent au premier passage)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/pubspec.yaml" ]; then

# STEP 0 — Gate toolchain (echoue tot plutot que tard)
flutter --version
flutter doctor -v

# STEP 1 — Scaffold du projet
flutter create \
  --org {AppNamespace} \
  --project-name {AppName} \
  --platforms android,ios \
  --template app \
  workspace/src/{AppName}

cd workspace/src/{AppName}

# STEP 2 — Dependances CORE runtime (cf. 2.4.a)
flutter pub add \
  flutter_riverpod:3.4.2 \
  riverpod_annotation:4.0.6 \
  go_router:18.0.0 \
  dio:5.11.0 \
  freezed_annotation:3.1.0 \
  json_annotation:4.12.0 \
  flutter_secure_storage:11.0.0 \
  shared_preferences:2.5.5 \
  intl:0.20.3 \
  logger:2.7.0 \
  collection:1.19.1

# STEP 3 — Dependances CORE de developpement (codegen, lints, mocks)
flutter pub add --dev \
  build_runner:2.16.1 \
  freezed:4.0.1 \
  json_serializable:6.14.1 \
  riverpod_generator:4.0.8 \
  riverpod_lint:3.1.8 \
  custom_lint:0.8.1 \
  flutter_lints:6.0.0 \
  mocktail:1.0.5

# STEP 4 — Arborescence Clean Architecture
mkdir -p \
  lib/core/{router,network,storage,theme,error} \
  lib/features \
  lib/shared/{widgets,utils} \
  test/core test/features \
  integration_test \
  assets/{images,fonts,i18n}

# STEP 5 — analysis_options.yaml : lints Flutter + plugin custom_lint (Riverpod)
cat > analysis_options.yaml <<'YAML'
include: package:flutter_lints/flutter.yaml

analyzer:
  plugins:
    - custom_lint
  errors:
    invalid_annotation_target: ignore   # faux positif connu freezed + json_serializable
  exclude:
    - "**/*.freezed.dart"
    - "**/*.g.dart"

linter:
  rules:
    prefer_const_constructors: true
    prefer_const_literals_to_create_immutables: true
    avoid_print: true
    require_trailing_commas: true
YAML

# STEP 6 — build.yaml : options du codegen
cat > build.yaml <<'YAML'
targets:
  $default:
    builders:
      json_serializable:
        options:
          explicit_to_json: true
          field_rename: snake
YAML

# STEP 7 — Le codegen DOIT tourner avant le premier analyze
#          (sans lui, tous les *.freezed.dart / *.g.dart manquent -> analyze rouge)
dart run build_runner build --delete-conflicting-outputs

# STEP 8 — Gate de coherence
flutter analyze --fatal-infos

fi
```

**Contrat post-init** :
- `pubspec.yaml` existe, `environment.sdk` vaut `^3.13.0`
- `lib/main.dart` monte un `ProviderScope`
- `analysis_options.yaml` inclut `flutter_lints` **et** le plugin `custom_lint`
- `dart run build_runner build` sort 0
- `flutter analyze --fatal-infos` sort 0

---

## 2.3 Contraintes de versions et etat de validation

### Contrainte SDK — pourquoi `^3.13.0`

La borne basse ne vient pas de Flutter mais du paquet le plus exigeant du catalog :

| Paquet | Contrainte Dart déclarée |
|---|---|
| `freezed` 4.0.1 | `>=3.13.0 <4.0.0` ← **le plus strict, il fixe la borne** |
| `riverpod_annotation` 4.0.6 | `^3.12.0` |
| `drift` 2.34.4 | `>=3.10.0 <4.0.0` |
| `json_serializable` 6.14.1 | `^3.9.0` |

Flutter 3.47.2 embarque Dart **3.13.2** : la contrainte passe, mais avec **deux patchs de marge**. Conséquence opérationnelle : **ce stack ne peut pas être scaffolde sur un Flutter plus ancien que 3.47** sans rétrograder `freezed`. Le STEP 0 de §2.2.1 vérifie donc la version avant toute autre chose.

`go_router` 18.0.0 impose de son côté `flutter: >=3.44.0` — satisfait.

### Famille Riverpod : co-versionnée

`flutter_riverpod` 3.4.2, `riverpod_annotation` 4.0.6, `riverpod_generator` 4.0.8 et `riverpod_lint` 3.1.8 épinglent tous **`riverpod: 3.4.2`** en dépendance exacte. Les numéros de version majeurs diffèrent d'un paquet à l'autre — c'est normal et volontaire chez l'auteur. **Bumper un seul de ces paquets casse la résolution `pub`.** Ils se bumpent en bloc.

### Paquets fournis par le SDK (absents du catalog)

`flutter_test` et `integration_test` se déclarent `sdk: flutter` dans `pubspec.yaml` et **n'ont pas de version pub**. Ils ne figurent donc pas en §2.4 — ce n'est pas un oubli du catalog. `validate_libs_catalog.py` ne peut pas les vérifier.

```yaml
dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter
```

### Ce qui n'a PAS été validé

Ce stack est `🟡 experimental`, et l'en-tête le dit sans détour :

| Vérifié | Non vérifié |
|---|---|
| Existence et dernière version stable de **chaque** paquet du catalog (API pub.dev, 2026-09-02) | `flutter build apk` / `flutter build ipa` |
| Contraintes SDK et inter-paquets croisées (tableaux ci-dessus) | `flutter test` sur un projet généré |
| Version de la toolchain (canal `stable`, `releases_windows.json`) | `dart run build_runner build` de bout en bout |
| Cohérence `.md` ↔ `.libs.json` (`validate_libs_versions_in_md.py`) | Pipeline `/sdd-full` complet |

Aucune commande Flutter n'a été exécutée : le SDK est absent de l'environnement. **Le premier run réel doit être traité comme un bench**, avec les écarts consignés dans `docs/benchmarks/known-gaps.md`.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/flutter.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id flutter`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| flutter_riverpod | 3.4.2 | State management + DI — defaut SDD_Pro. Compile-safe, testable sans widget tree, remplace Provider/InheritedWidget |
| riverpod_annotation | 4.0.6 | Annotations @riverpod (providers generes, typage exact) |
| go_router | 18.0.0 | Routing declaratif officiel Flutter — deep links, redirections de garde auth, routes typees |
| dio | 5.11.0 | Client HTTP — interceptors (auth, retry, log), timeouts, annulation. Le package `http` du SDK n'a aucun de ces mecanismes |
| freezed_annotation | 3.1.0 | Annotations de modeles immuables + unions scellees (sealed) pour les etats UI |
| json_annotation | 4.12.0 | Annotations (de)serialisation JSON |
| flutter_secure_storage | 11.0.0 | Tokens JWT / secrets (Keychain iOS, Keystore Android) — JAMAIS shared_preferences |
| shared_preferences | 2.5.5 | Preferences NON sensibles (theme, derniere page, flags UI) |
| intl | 0.20.3 | Formatage dates / nombres / devises par locale |
| logger | 2.7.0 | Logs structures — `print()` est interdit (cf. .md 5) |
| collection | 1.19.1 | firstWhereOrNull, groupBy, comparaisons profondes — absents de dart:core |
| build_runner | 2.16.1 | Orchestrateur de codegen (dev_dependency) — requis par freezed, json_serializable et riverpod_generator |
| freezed | 4.0.1 | Generateur des modeles immuables (dev_dependency). Plancher Dart >=3.13.0 : c'est lui qui fixe `environment.sdk` du projet |
| json_serializable | 6.14.1 | Generateur fromJson/toJson (dev_dependency) |
| riverpod_generator | 4.0.8 | Generateur des providers @riverpod (dev_dependency) |
| riverpod_lint | 3.1.8 | Lints Riverpod (dev_dependency) — detecte un ref.watch hors build, un provider non dispose |
| custom_lint | 0.8.1 | Moteur requis par riverpod_lint (dev_dependency) — sans lui les lints Riverpod ne s'executent pas |
| flutter_lints | 6.0.0 | Jeu de lints officiel Flutter (dev_dependency), reference dans analysis_options.yaml |
| mocktail | 1.0.5 | Mocking sans codegen (dev_dependency) — retenu plutot que mockito, qui exige un build_runner par classe mockee |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| offline-db | drift | 2.34.4 | sqlite, offline-first, base.*locale, persistance.*locale, drift |
| offline-db | drift_dev | 2.34.6 | sqlite, offline-first, drift |
| offline-db | sqlite3 | 3.5.2 | sqlite, offline-first, drift |
| offline-db | path_provider | 2.1.6 | sqlite, chemin.*fichier, documents.*directory, stockage.*fichier |
| image-loading | cached_network_image | 4.0.0 | image.*distante, avatar, vignette, cache.*image |
| svg | flutter_svg | 2.3.0 | svg, icone.*vectorielle, vector.*graphics |
| image-picker | image_picker | 1.2.3 | gallerie, choisir.*photo, image-picker |
| camera | camera | 0.12.0+2 | camera, photo, video.*capture |
| location | geolocator | 14.0.3 | gps, geolocalisation, position.*utilisateur |
| maps | google_maps_flutter | 2.18.0 | maps, carte, marker, google.*maps |
| permissions | permission_handler | 13.0.1 | permission, autorisation.*runtime |
| biometric | local_auth | 3.0.2 | biometric, face-id, touch-id, empreinte |
| push | firebase_core | 4.14.0 | push.*notification, fcm, firebase |
| push | firebase_messaging | 16.6.0 | push.*notification, fcm, notification.*distante |
| local-notification | flutter_local_notifications | 22.3.0 | notification.*locale, rappel, reminder, notification.*planifiee |
| sentry | sentry_flutter | 9.28.0 | sentry, error.*tracking, monitoring.*erreurs, crash.*report |
| deep-linking | url_launcher | 6.3.2 | ouvrir.*lien, url.*externe, tel:, mailto |
| webview | webview_flutter | 4.14.1 | webview, embed.*page.*web |
| connectivity | connectivity_plus | 7.3.1 | offline, hors.*ligne, connectivite, reseau.*disponible |
| app-metadata | package_info_plus | 10.2.1 | version.*application, build.*number, a.*propos |
| app-metadata | device_info_plus | 13.2.0 | modele.*appareil, device.*info, os.*version |
| stripe | flutter_stripe | 14.0.0 | stripe, paiement, payment |
| charts | fl_chart | 1.2.0 | chart, graphique, courbe, visualisation.*donnees |
| in-app-logs | talker_flutter (alt) | 5.1.20 | log.*ecran, console.*in-app, talker |
| service-locator | get_it (alt) | 9.2.1 | service.*locator, get_it, injection.*manuelle |
| state-management-alt | flutter_bloc (alt) | 9.1.1 | \bbloc\b, cubit, flutter_bloc |
| state-management-alt | bloc (alt) | 9.2.1 | \bbloc\b, cubit |
| state-management-alt | equatable (alt) | 2.1.0 | \bbloc\b, equatable |
| e2e-tests | patrol | 4.9.0 | tests.*e2e, test.*integration.*natif, patrol |
| strict-lints | very_good_analysis (alt) | 10.3.0 | lint.*strict, analyse.*statique.*stricte, very_good |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Role | Pattern | Exemple |
|------|---------|---------|
| Écran | `{name}_screen.dart` → classe `{Name}Screen` | `user_detail_screen.dart` / `UserDetailScreen` |
| Widget | `{name}.dart` → classe `{Name}` | `user_card.dart` / `UserCard` |
| Provider | `{name}_provider.dart` → fonction `@riverpod {name}` | `user_list_provider.dart` |
| Entité domain | `{name}.dart` → classe Freezed `{Name}` | `user.dart` / `User` |
| DTO | `{name}_dto.dart` → `{Name}Dto` | `user_dto.dart` / `UserDto` |
| Interface repository | `{name}_repository.dart` → `{Name}Repository` | `UserRepository` |
| Impl repository | `{name}_repository_impl.dart` → `{Name}RepositoryImpl` | `UserRepositoryImpl` |
| Datasource | `{name}_remote_datasource.dart` | `UserRemoteDatasource` |
| Use case | `{verb}_{name}.dart` → `{Verb}{Name}` | `fetch_users.dart` / `FetchUsers` |
| Test | miroir du chemin `lib/` + `_test.dart` | `test/features/user/domain/user_test.dart` |

**Conventions de fichier** : `snake_case.dart` **toujours** (règle `file_names` du linter Dart) ; classes en `PascalCase` ; membres privés préfixés `_`.

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util` — nommer par la responsabilité réelle
- `Widget` en suffixe de classe (`UserCardWidget`) → redondant, `UserCard` suffit
- `Model` pour une entité domain — réserver `Dto` à la couche data
- `PascalCase.dart` ou `camelCase.dart` en nom de fichier

---

## 3. Endpoints standard (cote backend separe)

Ce stack est mobile-only — il consomme un backend distinct. Endpoints minimaux attendus :

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck (état de connectivité) |
| `POST /api/auth/login` | flow d'authentification |
| `GET /api/me` | utilisateur courant (après auth) |

Côté app, une seule **base URL**, injectée à la compilation :

- **Dev** : `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000` (`10.0.2.2` = hôte vu depuis l'émulateur Android ; `localhost` sur simulateur iOS)
- **Staging / prod** : `flutter build apk --dart-define=API_BASE_URL=https://api.{domain}.com`
- Lecture : `const String.fromEnvironment('API_BASE_URL')`

> `--dart-define` **n'est pas un coffre à secrets** : les valeurs sont présentes dans le binaire et extractibles. Réservé aux URLs et aux flags.

---

## 4. Versioning des API consommees

Le backend expose `/api/v1/{domain}` (recommandé). Côté mobile : maintenir une **min-supported-api-version** injectée via `--dart-define=API_VERSION=1`. À chaque release, valider que le backend déployé supporte cette version.

---

## 5. Interdits projet (flutter)

**Architecture** :
- `import 'package:flutter/...'` dans `features/*/domain/` — le domain est du Dart pur
- `Map<String, dynamic>` remontant au-delà de la couche data — mapper vers un DTO puis une entité
- `DioException` atteignant la présentation — traduire en `Failure` dans la data
- `Navigator.push(MaterialPageRoute(...))` pour une route du router — utiliser `context.go` / `context.push`
- `ListView(children: [...])` pour > 50 items — utiliser `ListView.builder`
- `setState` pour un état applicatif partagé — c'est le rôle de Riverpod
- `InheritedWidget` écrit à la main
- Livrer `flutter_riverpod` **et** `flutter_bloc` dans le même projet
- `GlobalKey` pour faire communiquer deux widgets — remonter l'état dans un provider

**Code quality** :
- `print()` — utiliser `logger` (la règle `avoid_print` est active)
- `dynamic` injustifié
- `!` (null assertion) sur une valeur non prouvée non-nulle — préférer `?.` / `??` / un `case`
- Widget non-`const` alors qu'il pourrait l'être
- `build()` de plus de 50 lignes — extraire des widgets (et **pas** des méthodes `Widget _buildX()`, qui ne bénéficient pas de la mémoïsation)
- `Future` non attendu sans `unawaited()` explicite
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Token dans `shared_preferences` — utiliser `flutter_secure_storage`
- Secret en dur dans le code ou passé par `--dart-define` en croyant qu'il est protégé
- Log d'un token en clair
- Deep link sans validation de domaine (App Links / Universal Links)
- `badCertificateCallback` renvoyant `true` inconditionnellement — désactive TLS
- WebView chargeant une URL non validée

**Build / packaging** :
- Committer `build/`, `.dart_tool/`, `*.apk`, `*.ipa`, `ios/Pods/`
- **NE PAS** committer les `*.freezed.dart` / `*.g.dart` — ici c'est l'inverse : ils **doivent** être versionnés (le build ne doit pas dépendre d'un `build_runner` réussi en CI)
- `pubspec.lock` absent du dépôt (une **app** verrouille ses versions ; seule une *librairie* l'ignore)
- Contrainte `any` ou `^x.y.z` non pinnée dans `pubspec.yaml` — SDD_Pro pin exact
- Permissions excessives dans `AndroidManifest.xml` / `Info.plist`
- APK release non signé, ou signé avec la clé de debug

**Plateformes** :
- `Platform.isIOS` dispersé — centraliser dans `core/`
- API spécifique iOS appelée sans garde Android
- Dimensions en pixels fixes — utiliser `MediaQuery` / `LayoutBuilder`

---

## 6. Persistance locale — voir §1.5

Stack mobile → pas de « DB scaffolding » serveur. Pour de l'offline-first réel : capability `offline-db` (`drift` + `sqlite3` + `path_provider`). Sinon `shared_preferences` + `flutter_secure_storage` par défaut. Phase B (DB) d'`arch` : **SKIP**.

---

## 7. Temps reel

- **WebSocket** : `WebSocket.connect` de `dart:io` (natif, aucune lib) ou le canal `web_socket_channel` si l'US exige la cible Web
- **SSE** : `Dio` avec `ResponseType.stream` et lecture incrémentale
- **Push** : capability `push` (`firebase_core` + `firebase_messaging`) + configuration APNS (iOS) et FCM (Android) côté backend
- **Notifications locales** : capability `local-notification` (`flutter_local_notifications`) — sans dépendance Firebase

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Apps cross-platform iOS + Android** avec ~99% de code partagé (le taux le plus élevé du catalogue `mobiles/`)
- **UI très personnalisée / animée** — Flutter dessine chaque pixel, rien ne contraint au look système
- **Cohérence pixel-perfect** entre les deux OS
- **Équipes prêtes à investir sur Dart** (langage dédié, réutilisable nulle part ailleurs dans le catalogue SDD_Pro)

**NE PAS choisir si** :
- ❌ L'app doit se **fondre dans le look natif** de chaque OS — Flutter *imite* Material/Cupertino, il ne les utilise pas. Préférer `swiftui` + `kotlin-android`, ou `kotlin-multiplatform`.
- ❌ L'équipe est une équipe **React/TypeScript** — `react-native` réutilise ses compétences, Dart ne les réutilise pas
- ❌ L'équipe est une équipe **.NET** → `maui` ; **web** → `ionic-capacitor`
- ❌ Accès matériel très spécifique (NFC bas niveau, BLE custom, audio pro) — nécessite des platform channels écrits en Kotlin/Swift, ce qui annule le bénéfice du code unique
- ❌ Contrainte de taille d'APK très forte (< 5 Mo) — le moteur Flutter pèse ~7-15 Mo par ABI
- ❌ Besoin de partager la **logique métier** avec un backend JVM existant → `kotlin-multiplatform`
- ❌ Cible principale **web SEO** — Flutter Web rend dans un canvas, indexation faible. Utiliser `fullstack/*`.

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `mobile-flutter` + `auth-local` (JWT) + backend `python-fastapi` | 🟡 experimental | jamais validé end-to-end |
| `mobile-flutter` + `auth-local` + backend `dotnet-minimalapi` | 🟡 experimental | jamais validé end-to-end |
| `mobile-flutter` + `auth-azure-ad` + backend `kotlin-spring-boot` | 🟡 experimental | nécessite un wrapper MSAL Flutter — non catalogué, à instruire avant engagement |
| `mobile-flutter` (Supabase / Firebase, sans backend propre) | 🟡 experimental | prototypes uniquement |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `mobiles/flutter.md` en `## Active Tech Specs` → stack **mobile-only**, pas un frontend web
2. **Le backend reste déclaré séparément** — les deux projets coexistent sous `workspace/src/`
3. **STEP 0 obligatoire** : `flutter --version` doit rapporter **≥ 3.47.0**. En dessous, STOP `CAUSE: [INFRA_BLOCKED]` — `freezed` 4.0.1 exige Dart ≥ 3.13.0 (cf. §2.3). Ne pas rétrograder silencieusement une lib du catalog pour contourner.
4. **Créer** `workspace/src/{AppName}/` via `flutter create` (cf. §2.2.1)
5. **Injecter** `API_BASE_URL` / `API_VERSION` en `--dart-define` depuis `## Active Mobile Config` du `stack.md` (convention `MOBILE_API_BASE_URL`). **Ne pas** générer de fichier `.env` : Flutter n'en lit pas.
6. **`## Active UI Specs`** : aucun design system web n'est compatible. Flutter fournit Material 3 nativement. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`.
7. **Phase B (DB)** : SKIP — pas de DB serveur. La capability `offline-db` ne déclenche pas le scan DB.
8. **Le codegen fait partie du bootstrap** : `dart run build_runner build --delete-conflicting-outputs` **doit** tourner avant le premier `flutter analyze`, sinon tous les `*.freezed.dart` / `*.g.dart` manquent et l'analyse est rouge pour une raison trompeuse.
9. **Phase C (ADRs)** : créer `ADR-{ts}-stack-mobile-flutter.md` documentant Flutter 3.47 + Riverpod 3 + go_router 18 + Clean Architecture, et le choix Riverpod plutôt que BLoC.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de « backend interne ». Convention :

- `dev-backend` **ne touche pas** au projet Flutter — il code le backend séparé déclaré en `## Active Tech Specs backend/*`
- `dev-frontend` matérialise **tout** le projet Flutter : `lib/`, `test/`, `assets/`, `pubspec.yaml`

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `workspace/src/{AppName}/lib/**` | `dev-frontend` |
| `workspace/src/{AppName}/test/**`, `integration_test/**` | `qa` (`dev-frontend` pour les widget tests d'une US) |
| `workspace/src/{AppName}/assets/**` | `dev-frontend` |
| `workspace/src/{AppName}/pubspec.yaml` | `arch` (create) + `dev-frontend` (ajout de deps on-demand) |
| `workspace/src/{AppName}/analysis_options.yaml` | `arch` exclusif |
| `workspace/src/{AppName}/build.yaml` | `arch` exclusif |
| `workspace/src/{AppName}/android/**`, `ios/**` | `arch` (create) + `dev-frontend` (permissions uniquement) |
| `**/*.freezed.dart`, `**/*.g.dart` | **généré** — jamais édité à la main, régénéré par `build_runner` |

**Backend séparé** : même matrice d'ownership que pour son propre stack. Les 2 projets coexistent sous `workspace/src/{BackendName}/` et `workspace/src/{AppName}/`.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

flutter --version | grep -qE "3\.(4[7-9]|[5-9][0-9])\."   # >= 3.47 (cf. 2.3)
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter analyze --fatal-infos

test -f pubspec.yaml
test -f lib/main.dart
test -f analysis_options.yaml
grep -q "sdk: \^3\.13" pubspec.yaml           # contrainte imposee par freezed 4.0.1
grep -q "flutter_riverpod" pubspec.yaml
grep -q "go_router" pubspec.yaml
grep -q "custom_lint" analysis_options.yaml   # sinon les lints Riverpod sont muets

flutter test
echo "smoke OK"
```

Smoke complet sur appareil / émulateur : `flutter run --release` — l'app doit démarrer sans crash et joindre `GET /api/health`.
