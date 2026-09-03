# Tech FEAT: kotlin-multiplatform (mobile)

> §2.4 (Librairies) regeneree depuis `kotlin-multiplatform.libs.json` — ne pas editer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id kotlin-multiplatform`).

Status: Experimental
Validation: 🟡 experimental — Spec stack + `.libs.json` construits et validés le 2026-09-02 (Kotlin 2.4.10, Compose Multiplatform 1.12.0, Ktor 3.5.2, Koin 4.2.2, SQLDelight 2.3.2 ; chaque coordonnée résolue contre le `maven-metadata.xml` de Maven Central — et non contre l'index `search.maven.org`, qui s'est révélé périmé lors de la construction). Trois pièges structurels propres à KMP sont documentés en §2.3 : les **deux** plugins Compose distincts, les artefacts `org.jetbrains.androidx.*` vs `androidx.*`, et l'obligation de déclarer un moteur Ktor **par cible**. **Jamais exécuté end-to-end via `/sdd-full`** : aucun `assembleDebug` ni `linkDebugFrameworkIosArm64` n'a tourné en CI. Non supporté commercialement en l'état.
Tech FEAT ID: tech-kotlin-multiplatform
Scope: **mobile multiplateforme** — application **Kotlin Multiplatform (KMP)** avec UI partagée par **Compose Multiplatform 1.12** dans UN seul projet `{AppName}/`. La logique métier ET l'UI vivent en `commonMain` ; Kotlin compile en JVM/Dalvik pour Android et en binaire natif ARM pour iOS. Cible Android + iOS (+ desktop JVM / Wasm en cibles optionnelles). Pas de séparation `{BackendName}` / `{LibName}`.

> **Backend séparé** : ce stack est PUREMENT client mobile. Il consomme une API backend distincte déclarée en `## Active Tech Specs`. Il a une affinité particulière avec `backend/kotlin-spring-boot.md` : les modèles `@Serializable` et la logique de validation peuvent être **littéralement le même code Kotlin** des deux côtés — c'est l'argument de vente principal du stack.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Projet KMP à UI partagée** cible Android + iOS :

- **`commonMain`** : modèles, use cases, repositories, client HTTP, ViewModels **et écrans Compose** — l'essentiel du code
- **`androidMain` / `iosMain`** : uniquement ce qui ne peut pas être commun (moteur HTTP, driver SQL, Keychain, permissions) via le mécanisme `expect` / `actual`
- **Compose Multiplatform 1.12** : le même arbre `@Composable` rend sur les deux OS (Skia)
- **Ktor 3.5** : client HTTP multiplatform (Retrofit est JVM-only)
- **Koin 4.2** : injection de dépendances multiplatform (Hilt/Dagger sont JVM-only)
- **SQLDelight 2.3** : SQL typé multiplatform (Room est Android-only)

Architecture cible :

```
{AppName}/
├── composeApp/
│   ├── build.gradle.kts        ── cibles KMP + source sets
│   └── src/
│       ├── commonMain/kotlin/{AppNamespace}/
│       │   ├── App.kt          ── racine @Composable + NavHost
│       │   ├── di/             ── modules Koin
│       │   ├── data/
│       │   │   ├── remote/     ── HttpClient Ktor + DTOs
│       │   │   ├── local/      ── requetes SQLDelight, settings
│       │   │   └── repository/ ── impl de repository
│       │   ├── domain/         ── modeles, interfaces, use cases
│       │   └── ui/
│       │       ├── screens/    ── ecrans Compose
│       │       ├── components/
│       │       └── theme/
│       ├── commonMain/composeResources/  ── images, strings, fonts
│       ├── androidMain/kotlin/  ── MainActivity, Application, actual
│       ├── iosMain/kotlin/      ── MainViewController, actual
│       └── commonTest/kotlin/
├── iosApp/                     ── wrapper Xcode (SwiftUI minimal)
│   ├── iosApp/ContentView.swift
│   └── iosApp.xcodeproj
├── gradle/libs.versions.toml
├── settings.gradle.kts
└── build.gradle.kts
```

**Différence vs les autres stacks `mobiles/`** :
- vs `flutter` : Kotlin plutôt que Dart, et le code partagé est **interopérable** avec un backend JVM. Modèle de rendu comparable (Skia dans les deux cas).
- vs `kotlin-android` : même langage et même UI Compose, mais **le code cible aussi iOS**. Le prix : plus aucune dépendance JVM-only (ni Retrofit, ni Room, ni Hilt, ni MockK).
- vs `react-native` : compilation native AOT, pas de moteur JS.
- **KMP autorise le partage partiel** : on peut ne partager que le domain et garder deux UI natives (SwiftUI + Compose). Ce stack retient la variante **UI partagée** ; cf. §8 pour la bascule.

---

## 1.2 Couches

- **Domain** (`commonMain/domain/`) : modèles `@Serializable`, interfaces de repository, use cases. Kotlin pur, zéro dépendance de plateforme.
- **Data** (`commonMain/data/`) : DTOs, `HttpClient` Ktor, requêtes SQLDelight, implémentations de repository. Traduit toute exception en `Result` / erreur de domaine.
- **UI** (`commonMain/ui/`) : écrans Compose, composants, thème, ViewModels multiplatform.
- **DI** (`commonMain/di/`) : modules Koin.
- **Plateforme** (`androidMain/` / `iosMain/`) : implémentations `actual` **uniquement**. Toute logique métier qui atterrit ici est un défaut de conception.

Règle de dépendance : `ui → domain ← data`. Le domain ne dépend de rien.

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas.** Arch lève WARNING `[STACK_MALFORMED]` si `LibStrategy` déclare un mode `monorepo`.

| Layer | Path (sous `composeApp/src/`) |
|---|---|
| Racine app `@Composable` | `commonMain/kotlin/{AppNamespace}/App.kt` |
| Graphe de navigation | `commonMain/kotlin/{AppNamespace}/ui/Navigation.kt` |
| Écran | `commonMain/kotlin/{AppNamespace}/ui/screens/{Name}Screen.kt` |
| Composant | `commonMain/kotlin/{AppNamespace}/ui/components/{Name}.kt` |
| ViewModel | `commonMain/kotlin/{AppNamespace}/ui/screens/{Name}ViewModel.kt` |
| Thème | `commonMain/kotlin/{AppNamespace}/ui/theme/Theme.kt` |
| Modèle domain | `commonMain/kotlin/{AppNamespace}/domain/model/{Name}.kt` |
| Interface repository | `commonMain/kotlin/{AppNamespace}/domain/repository/{Name}Repository.kt` |
| Use case | `commonMain/kotlin/{AppNamespace}/domain/usecase/{Verb}{Name}UseCase.kt` |
| DTO | `commonMain/kotlin/{AppNamespace}/data/remote/dto/{Name}Dto.kt` |
| Client API | `commonMain/kotlin/{AppNamespace}/data/remote/{Name}Api.kt` |
| Impl repository | `commonMain/kotlin/{AppNamespace}/data/repository/{Name}RepositoryImpl.kt` |
| Requêtes SQLDelight | `commonMain/sqldelight/{AppNamespace}/{Name}.sq` |
| Module Koin | `commonMain/kotlin/{AppNamespace}/di/{Name}Module.kt` |
| Déclaration `expect` | `commonMain/kotlin/{AppNamespace}/platform/{Name}.kt` |
| `actual` Android | `androidMain/kotlin/{AppNamespace}/platform/{Name}.android.kt` |
| `actual` iOS | `iosMain/kotlin/{AppNamespace}/platform/{Name}.ios.kt` |
| Activity hôte Android | `androidMain/kotlin/{AppNamespace}/MainActivity.kt` |
| Point d'entrée iOS | `iosMain/kotlin/{AppNamespace}/MainViewController.kt` |
| Ressources partagées | `commonMain/composeResources/{drawable,values,font}/` |
| Test commun | `commonTest/kotlin/{AppNamespace}/{Name}Test.kt` |
| Wrapper Xcode | `../iosApp/iosApp/ContentView.swift` |

---

## 1.4 Principes non negociables

**Architecture** :
- **`commonMain` par défaut.** Un fichier n'atterrit dans `androidMain` / `iosMain` que si l'API n'existe pas en commun. Toute logique métier dans un source set de plateforme est un défaut.
- **`expect` / `actual` réservé aux frontières de plateforme** : Keychain, permissions, `Context`, notifications. Jamais pour du calcul.
- **Aucune dépendance JVM-only en `commonMain`** — c'est l'erreur n°1 en KMP. Interdits en commun : Retrofit, Room, Hilt/Dagger, MockK, Gson/Jackson, `java.time`, `java.io.File`. Le catalog §2.4 ne contient que des équivalents multiplatform.
- **Moteur Ktor déclaré par cible** (cf. §2.3) — sans lui, tout appel HTTP lève au runtime, pas à la compilation.
- **ViewModels via les artefacts `org.jetbrains.androidx.lifecycle`**, pas `androidx.lifecycle` (cf. §2.3).
- **`@Serializable` sur tous les DTOs** — Kotlin/Native n'a pas de reflection, la sérialisation est **obligatoirement** générée à la compilation.
- **Toute erreur remonte en `Result` ou en type d'erreur du domaine** — jamais une exception Ktor jusqu'à l'UI.
- **Listes longues en `LazyColumn`** pour > 50 items.

**Sécurité mobile** :
- **Tokens dans le stockage chiffré de chaque plateforme** via `expect` / `actual` : `EncryptedSharedPreferences` (Android, capability `secure-storage`) et **Keychain** (iOS, via interop `Security.framework` — aucune lib nécessaire). **Jamais** `multiplatform-settings` nu, qui écrit en clair.
- **Aucun secret dans `commonMain`** — il finit dans les deux binaires.
- **Permissions juste-à-temps** via `moko-permissions` (capability `permissions`).
- **Certificate pinning** : à configurer par moteur (OkHttp `CertificatePinner` sur Android, `NSURLSessionDelegate` sur iOS) — donc en `actual`, pas en commun.

---

## 1.5 Couches persistantes (locales)

| Type | Lib | Cas d'usage |
|---|---|---|
| Clé-valeur non sensible | `multiplatform-settings-no-arg` (CORE) | Préférences UI, thème |
| **Clé-valeur sensible** | capability `secure-storage` + `actual` Keychain | Tokens JWT, credentials |
| SQL local | `sqldelight` (capability `offline-db`) | Offline-first, gros jeux de données |

> **Piège KMP** : Room est **Android-only**. La tentation de le mettre en `commonMain` échoue à la résolution des dépendances. SQLDelight est l'équivalent multiplatform — il génère des APIs Kotlin typées depuis des fichiers `.sq`, et exige **un driver par cible** (`android-driver` + `native-driver`), exactement comme Ktor exige un moteur par cible.

---

## 1.6 Navigation — Navigation Compose multiplatform

Le stack retient le port JetBrains de Navigation Compose (`org.jetbrains.androidx.navigation:navigation-compose`), qui suit l'API androidx mais compile en `commonMain`.

| Cas | Pattern |
|---|---|
| Route simple | `NavHost` + `composable<Route.Users>` (routes typées, `@Serializable`) |
| Onglets | `NavHost` imbriqué dans un `Scaffold` + `NavigationBar` |
| Paramètre | `data class` `@Serializable` en route (type-safe, pas de string) |
| Garde d'auth | `LaunchedEffect` sur l'état d'auth + `navController.navigate` |
| Deep link | `navDeepLink` + App Links (Android) / Universal Links (Xcode) |

**Alternative** : `decompose` (capability `navigation-alt`) — navigation par composants avec cycle de vie et état sauvegardé, plus puissante mais structurante. Mutuellement exclusive.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `mobile-kotlin-multiplatform`
- **Langage** : Kotlin 2.4.10 (`expect`/`actual`, coroutines, `@Serializable`)
- **UI** : Compose Multiplatform 1.12.0 (rendu Skia)
- **Cibles Kotlin** : `androidTarget()`, `iosArm64()`, `iosSimulatorArm64()`, `iosX64()`
- **Plateformes** : Android API 24+ / iOS 15.0+
- **Build** : Gradle 8.14.5 (Kotlin DSL) + AGP 8.13.2 + Xcode 26.6 pour le wrapper iOS
- **JDK** : 17
- **Package manager** : Maven Central + Google Maven via Gradle
- **Namespace** : `{AppNamespace}`

---

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/settings.gradle.kts`
- **Build Android (debug)** : `(cd workspace/src/{AppName} && ./gradlew :composeApp:assembleDebug)`
- **Build APK release** : `./gradlew :composeApp:assembleRelease`
- **Framework iOS** : `./gradlew :composeApp:linkDebugFrameworkIosSimulatorArm64` — **macOS uniquement**
- **App iOS** : ouvrir `iosApp/iosApp.xcodeproj` dans Xcode, ou `xcodebuild` — **macOS uniquement**
- **Tests communs** : `./gradlew :composeApp:allTests` (ou `:composeApp:testDebugUnitTest` pour la seule JVM)
- **Vérifier les cibles résolues** : `./gradlew :composeApp:dependencies --configuration commonMainImplementation`
- **Smoke Command** :

```bash
(cd workspace/src/{AppName} && ./gradlew :composeApp:assembleDebug --no-daemon)
test -f workspace/src/{AppName}/composeApp/build.gradle.kts
test -f workspace/src/{AppName}/composeApp/src/commonMain/kotlin/{AppNamespace}/App.kt
```

- **Smoke Timeout** : 600s (première résolution KMP + compilation Kotlin/Native = long)

> ⚠️ **Le smoke ne couvre que la cible Android.** Compiler iOS exige un hôte macOS + Xcode. Sur Windows / Linux, `arch` doit émettre un WARNING explicite plutôt que laisser croire à une validation complète.

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/src/{AppName}/settings.gradle.kts" ]; then
  APP=workspace/src/{AppName}
  NS_PATH=$(echo "{AppNamespace}" | tr '.' '/')

  # STEP 1 — Arborescence des source sets KMP
  mkdir -p \
    "$APP/composeApp/src/commonMain/kotlin/$NS_PATH"/{di,domain/{model,repository,usecase},data/{remote/dto,local,repository},ui/{screens,components,theme},platform} \
    "$APP/composeApp/src/commonMain/composeResources"/{drawable,values} \
    "$APP/composeApp/src/commonMain/sqldelight/$NS_PATH" \
    "$APP/composeApp/src/androidMain/kotlin/$NS_PATH/platform" \
    "$APP/composeApp/src/iosMain/kotlin/$NS_PATH/platform" \
    "$APP/composeApp/src/commonTest/kotlin/$NS_PATH" \
    "$APP/iosApp/iosApp" \
    "$APP/gradle"

  # STEP 2 — settings.gradle.kts (les depots Compose Multiplatform sont requis)
  cat > "$APP/settings.gradle.kts" << 'EOF'
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
        maven("https://maven.pkg.jetbrains.space/public/p/compose/dev")
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven("https://maven.pkg.jetbrains.space/public/p/compose/dev")
    }
}

rootProject.name = "{AppName}"
include(":composeApp")
EOF

  # STEP 3 — build.gradle.kts racine (declaration sans application)
  cat > "$APP/build.gradle.kts" << 'EOF'
plugins {
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.compose.multiplatform) apply false
    alias(libs.plugins.android.application) apply false
}
EOF

  # STEP 4 — composeApp/build.gradle.kts
  cat > "$APP/composeApp/build.gradle.kts" << 'EOF'
plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.android.application)
    // LES DEUX plugins Compose sont requis (cf. 2.3) :
    alias(libs.plugins.kotlin.compose)      // compilateur @Composable (suit Kotlin)
    alias(libs.plugins.compose.multiplatform) // accesseurs compose.* + packaging
    alias(libs.plugins.kotlin.serialization)
}

kotlin {
    androidTarget {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }
    // Les trois cibles iOS : device ARM, simulateur ARM (Apple Silicon), simulateur x64 (Intel)
    iosArm64()
    iosSimulatorArm64()
    iosX64()

    sourceSets {
        commonMain.dependencies {
            // Accesseurs fournis par le plugin org.jetbrains.compose :
            // on ne pin PAS org.jetbrains.compose.material3:material3 a la main (cf. 2.3)
            implementation(compose.runtime)
            implementation(compose.foundation)
            implementation(compose.material3)
            implementation(compose.ui)
            implementation(compose.components.resources)

            implementation(libs.kotlinx.coroutines.core)
            implementation(libs.kotlinx.serialization.json)
            implementation(libs.kotlinx.datetime)

            implementation(libs.ktor.client.core)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.kotlinx.json)
            implementation(libs.ktor.client.logging)

            implementation(libs.koin.core)
            implementation(libs.koin.compose)
            implementation(libs.koin.compose.viewmodel)

            implementation(libs.jb.lifecycle.viewmodel.compose)
            implementation(libs.jb.navigation.compose)
            implementation(libs.jb.savedstate)

            implementation(libs.multiplatform.settings.no.arg)
            implementation(libs.kermit)
        }
        androidMain.dependencies {
            implementation(compose.preview)
            implementation(libs.androidx.activity.compose)
            implementation(libs.androidx.core.ktx)
            implementation(libs.koin.android)
            // MOTEUR Ktor de la cible Android — obligatoire (cf. 2.3)
            implementation(libs.ktor.client.okhttp)
        }
        iosMain.dependencies {
            // MOTEUR Ktor de la cible iOS — obligatoire (cf. 2.3)
            implementation(libs.ktor.client.darwin)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.turbine)
        }
    }
}

android {
    namespace = "{AppNamespace}"
    compileSdk = 36

    defaultConfig {
        applicationId = "{AppNamespace}"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
EOF

  # STEP 5 — gradle.properties (KMP + cache de configuration)
  cat > "$APP/gradle.properties" << 'EOF'
android.useAndroidX=true
android.nonTransitiveRClass=true
kotlin.code.style=official
org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g
org.gradle.caching=true
EOF

  # STEP 6 — gradle/libs.versions.toml genere depuis kotlin-multiplatform.libs.json
  #          (generateur deterministe cote arch : `versions` -> [versions],
  #           `core`/`onDemand` -> [libraries], `plugins` -> [plugins])

  # STEP 7 — Wrapper Gradle pinne
  (cd "$APP" && gradle wrapper --gradle-version 8.14.5 --distribution-type bin)
fi

# STEP 8 — Validation : cible Android uniquement (iOS exige macOS + Xcode)
(cd workspace/src/{AppName} && ./gradlew :composeApp:assembleDebug --no-daemon)
if [ "$(uname)" != "Darwin" ]; then
  echo "WARN: cible iOS non compilee (hote non-macOS) — validation partielle"
fi
```

**Contrat post-init** :
- `settings.gradle.kts` déclare `include(":composeApp")` et le dépôt Compose de JetBrains
- `composeApp/build.gradle.kts` applique **les deux** plugins Compose
- Chaque cible a son moteur Ktor (`okhttp` en `androidMain`, `darwin` en `iosMain`)
- `gradle/libs.versions.toml` expose un alias pour chaque entrée du `.libs.json`
- `./gradlew :composeApp:assembleDebug` sort 0

---

## 2.3 Les trois pieges structurels de KMP

> Ces trois points ne sont pas des préférences de style : chacun produit un échec, et deux d'entre eux **ne se voient pas à la compilation**. Ils sont la raison d'être de cette section.

### 1. Il y a DEUX plugins Compose, et il faut les deux

| Plugin | Version suivie | Rôle |
|---|---|---|
| `org.jetbrains.kotlin.plugin.compose` | **celle de Kotlin** (2.4.10) | Le **compilateur** `@Composable`. Obligatoire depuis Kotlin 2.0+ |
| `org.jetbrains.compose` | **celle de CMP** (1.12.0) | Les accesseurs `compose.runtime` / `compose.material3` / `compose.components.resources`, et le packaging |

Les oublier a des effets distincts : sans le premier, aucun `@Composable` ne compile ; sans le second, les accesseurs `compose.*` du `build.gradle.kts` sont introuvables. C'est le même piège que celui corrigé sur `kotlin-android` au même audit — où `composeOptions { kotlinCompilerExtensionVersion }`, obsolète depuis Kotlin 2.0+, était encore utilisé à la place du plugin.

**Corollaire sur les artefacts UI** : on **ne pin pas** `org.jetbrains.compose.material3:material3` à la main. Cette coordonnée existe et sa dernière version est `1.9.0` — un numéro différent de celui du plugin (`1.12.0`), ce qui invite à croire à une incohérence. L'idiome CMP est de passer par les accesseurs `compose.*`, que le plugin résout pour vous. Le catalog §2.4 ne déclare donc **aucun** artefact `org.jetbrains.compose.*`.

### 2. `org.jetbrains.androidx.*` ≠ `androidx.*`

Pour ViewModel, Navigation et SavedState, il existe **deux familles de coordonnées homonymes** :

| À utiliser en `commonMain` | À NE PAS utiliser en `commonMain` |
|---|---|
| `org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose` | `androidx.lifecycle:lifecycle-viewmodel-compose` |
| `org.jetbrains.androidx.navigation:navigation-compose` | `androidx.navigation:navigation-compose` |
| `org.jetbrains.androidx.savedstate:savedstate` | `androidx.savedstate:savedstate` |

Les secondes sont **Android-only** et ne résolvent pas en `commonMain`. Les APIs sont volontairement identiques, donc la documentation, les exemples et les réflexes issus d'`kotlin-android` mènent droit dans le mur. Leurs numéros de version diffèrent aussi (`org.jetbrains.androidx.navigation` est en 2.9.2 quand `androidx.navigation` est en 2.10.0) — ne pas « harmoniser ».

### 3. Ktor et SQLDelight exigent un artefact PAR CIBLE

Ktor n'a **pas** de moteur par défaut. `ktor-client-core` en `commonMain` compile parfaitement, puis **échoue au runtime** au premier appel. Il faut :

| Source set | Artefact |
|---|---|
| `androidMain` | `io.ktor:ktor-client-okhttp` |
| `iosMain` | `io.ktor:ktor-client-darwin` |

Même schéma pour SQLDelight (capability `offline-db`) : `android-driver` en `androidMain`, `native-driver` en `iosMain`. Et pour Coil 3 (capability `image-loading`), qui n'embarque aucun client HTTP : `coil-network-ktor3` est obligatoire.

**C'est le plus coûteux des trois** : la compilation est verte, le CI est vert, et l'échec n'apparaît qu'à la première requête sur device.

### Note de méthode sur la résolution des versions

Les coordonnées de ce catalog ont été résolues contre `https://repo1.maven.org/maven2/**/maven-metadata.xml`. L'index `search.maven.org/solrsearch` — le réflexe habituel — s'est révélé **périmé** lors de la construction : il rapportait `kotlin-stdlib` en 2.2.0 alors que la 2.4.10 est publiée, et Compose Multiplatform en 1.11.1 au lieu de 1.12.0. Toute revalidation doit utiliser `maven-metadata.xml`, pas l'index de recherche.

### Ce qui n'a PAS été validé

| Vérifié | Non vérifié |
|---|---|
| Existence + dernière version stable de chaque coordonnée (`maven-metadata.xml`, 2026-09-02) | `./gradlew :composeApp:assembleDebug` |
| Cohérence des familles d'artefacts multiplatform (tables ci-dessus) | `linkDebugFrameworkIosArm64` (exige macOS) |
| Cohérence `.md` ↔ `.libs.json` | `./gradlew :composeApp:allTests` |
| — | Pipeline `/sdd-full` complet |

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/kotlin-multiplatform.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id kotlin-multiplatform`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| kotlinx-coroutines-core | 1.11.0 | commonMain — Flow, async, structured concurrency. Socle de tout code partage |
| kotlinx-serialization-json | 1.11.0 | commonMain — (de)serialisation JSON multiplatform (reflection indisponible sur Kotlin/Native) |
| kotlinx-datetime | 0.8.0 | commonMain — `java.time` n'existe pas sur Kotlin/Native ; c'est le seul equivalent multiplatform |
| ktor-client-core | 3.5.2 | commonMain — client HTTP multiplatform (l'equivalent KMP de Retrofit, qui est JVM-only) |
| ktor-client-content-negotiation | 3.5.2 | commonMain — negociation de contenu |
| ktor-serialization-kotlinx-json | 3.5.2 | commonMain — pont Ktor <-> kotlinx.serialization |
| ktor-client-logging | 3.5.2 | commonMain — log des requetes |
| ktor-client-okhttp | 3.5.2 | androidMain — MOTEUR de la cible Android. Ktor n'a pas de moteur par defaut : sans moteur declare par cible, tout appel leve une exception au runtime |
| ktor-client-darwin | 3.5.2 | iosMain — MOTEUR de la cible iOS (NSURLSession). Meme remarque |
| koin-core | 4.2.2 | commonMain — injection de dependances multiplatform (Hilt/Dagger sont JVM-only) |
| koin-compose | 4.2.2 | commonMain — `koinInject()` cote Composable |
| koin-compose-viewmodel | 4.2.2 | commonMain — `koinViewModel()` avec le ViewModel multiplatform |
| koin-android | 4.2.2 | androidMain — demarrage du conteneur depuis l'Application Android |
| lifecycle-viewmodel-compose | 2.11.0 | commonMain — ViewModel MULTIPLATFORM (port JetBrains). NE PAS confondre avec androidx.lifecycle:*, qui est Android-only et ne resout pas en commonMain |
| navigation-compose | 2.9.2 | commonMain — Navigation Compose MULTIPLATFORM (port JetBrains). Meme remarque que ci-dessus vs androidx.navigation |
| savedstate | 1.4.0 | commonMain — sauvegarde d'etat multiplatform, peer de la navigation |
| multiplatform-settings-no-arg | 1.3.0 | commonMain — cle-valeur NON sensible (SharedPreferences sur Android, NSUserDefaults sur iOS) |
| kermit | 2.1.0 | commonMain — logger multiplatform (println n'apparait pas dans les logs iOS) |
| activity-compose | 1.13.0 | androidMain — point d'entree `setContent` de l'Activity hote |
| core-ktx | 1.19.0 | androidMain |
| kotlin-test | 2.4.10 | commonTest — assertions multiplatform |
| kotlinx-coroutines-test | 1.11.0 | commonTest — runTest / TestDispatcher |
| turbine | 1.2.1 | commonTest — assertions sur un Flow dans le temps |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| offline-db | runtime | 2.3.2 | sqlite, offline-first, base.*locale, persistance.*locale, sqldelight |
| offline-db | coroutines-extensions | 2.3.2 | sqlite, offline-first, sqldelight |
| offline-db | android-driver | 2.3.2 | sqlite, offline-first, sqldelight |
| offline-db | native-driver | 2.3.2 | sqlite, offline-first, sqldelight |
| secure-storage | multiplatform-settings | 1.3.0 | token.*securise, secure.*storage, keychain |
| secure-storage | security-crypto | 1.1.0 | token.*securise, secure.*storage, chiffrement.*local |
| image-loading | coil-compose | 3.6.1 | image.*distante, avatar, vignette, coil |
| image-loading | coil-network-ktor3 | 3.6.1 | image.*distante, coil |
| permissions | permissions | 0.20.1 | permission, autorisation.*runtime, camera, gps, notification |
| navigation-alt | decompose (alt) | 3.5.0 | decompose, navigation.*composant, navigation.*avancee |
| navigation-alt | lifecycle (alt) | 2.5.0 | decompose, essenty |
| kmp-assertions | kotest-assertions-core | 6.2.4 | kotest, assertions.*expressives, shouldBe |
| http-mocking | ktor-client-mock | 3.5.2 | mock.*http, test.*client.*api, MockEngine |
| kmp-mocking | mockative | 3.3.2 | mock, stub, mockative |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| org.jetbrains.kotlin.multiplatform | 2.4.10 | Plugin KMP — declare les cibles et les source sets |
| org.jetbrains.kotlin.plugin.compose | 2.4.10 | COMPILATEUR Compose, versionne avec Kotlin. Obligatoire depuis Kotlin 2.0+ et DISTINCT de org.jetbrains.compose ci-dessous — les deux sont requis |
| org.jetbrains.compose | 1.12.0 | Plugin Compose Multiplatform — fournit les accesseurs `compose.runtime` / `compose.material3` / `compose.components.resources` et le packaging desktop. DISTINCT du compilateur ci-dessus |
| org.jetbrains.kotlin.plugin.serialization | 2.4.10 | Genere les serializers @Serializable — indispensable sur Kotlin/Native, ou la reflection n'existe pas |
| com.android.application | 8.13.2 | Cible Android du module composeApp |
| app.cash.sqldelight | 2.3.2 | Genere les APIs typees depuis les fichiers .sq — a appliquer uniquement si la capability offline-db est active |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

| Role | Pattern | Exemple |
|------|---------|---------|
| Écran `@Composable` | `{Name}Screen.kt` → `fun {Name}Screen()` | `UserDetailScreen.kt` |
| ViewModel | `{Name}ViewModel.kt` → `class {Name}ViewModel` | `UserDetailViewModel.kt` |
| Composant | `{Name}.kt` → `fun {Name}()` | `UserCard.kt` |
| Modèle domain | `{Name}.kt` → `data class {Name}` | `User.kt` |
| DTO | `{Name}Dto.kt` → `@Serializable data class {Name}Dto` | `UserDto.kt` |
| Interface repository | `{Name}Repository.kt` | `UserRepository.kt` |
| Impl repository | `{Name}RepositoryImpl.kt` | `UserRepositoryImpl.kt` |
| Use case | `{Verb}{Name}UseCase.kt` | `FetchUsersUseCase.kt` |
| Client API | `{Name}Api.kt` | `UsersApi.kt` |
| Module Koin | `{Name}Module.kt` → `val {name}Module` | `DataModule.kt` |
| Déclaration `expect` | `{Name}.kt` (dans `platform/`) | `SecureStore.kt` |
| **`actual` Android** | `{Name}.android.kt` | `SecureStore.android.kt` |
| **`actual` iOS** | `{Name}.ios.kt` | `SecureStore.ios.kt` |
| Requêtes SQLDelight | `{Name}.sq` | `User.sq` |
| Test | `{Name}Test.kt` dans `commonTest` | `FetchUsersUseCaseTest.kt` |

**Conventions de fichier** : `PascalCase.kt` ; suffixe de plateforme `.android.kt` / `.ios.kt` sur les `actual` (convention forte de l'écosystème KMP — elle rend le source set lisible depuis le nom seul).

**Suffixes INTERDITS** :
- `Manager`, `Helper`, `Util`
- `Activity` / `Fragment` en `commonMain` (concepts Android)
- Un `actual` sans suffixe de plateforme
- `Android` / `IOS` **dans** un nom de type de `commonMain`

---

## 3. Endpoints standard (cote backend separe)

| Endpoint côté backend | Rôle |
|---|---|
| `GET /api/health` | healthcheck |
| `POST /api/auth/login` | flow d'authentification |
| `GET /api/me` | utilisateur courant |

Base URL injectée à la compilation via `BuildConfig` (Android) et un `actual` iOS, exposée derrière un `expect val apiBaseUrl: String` :

- **Dev Android** : `http://10.0.2.2:5000` (émulateur)
- **Dev iOS** : `http://localhost:5000` (simulateur)
- **Prod** : `https://api.{domain}.com`

> **Affinité `backend/kotlin-spring-boot`** : les `data class` `@Serializable` du domain peuvent être partagées littéralement entre le backend Kotlin et `commonMain`. C'est le seul couple du catalogue SDD_Pro où le contrat back↔front peut être garanti **par le compilateur** plutôt que par la discipline — ce qui répond directement au risque de drift décrit dans `rules/library-and-stack.md §6.bis`.

---

## 4. Versioning des API consommees

Le backend expose `/api/v1/{domain}`. Côté app : `apiVersion` en constante de `commonMain`, envoyée en en-tête par un plugin Ktor. À chaque release, valider que le backend déployé supporte cette version.

---

## 5. Interdits projet (kotlin-multiplatform)

**Architecture** :
- Dépendance **JVM-only** en `commonMain` : Retrofit, Room, Hilt/Dagger, MockK, Gson, Jackson, `java.time`, `java.io.File`, `java.util.UUID`
- Artefact `androidx.*` en `commonMain` pour ViewModel / Navigation / SavedState — utiliser `org.jetbrains.androidx.*` (§2.3)
- `ktor-client-core` sans moteur par cible (§2.3) — échec au runtime
- SQLDelight sans driver par cible
- Coil 3 sans `coil-network-ktor3`
- Logique métier dans `androidMain` / `iosMain` — réservés aux `actual`
- `expect` / `actual` pour du calcul pur
- `Context` Android traversant une signature de `commonMain`
- DTO sans `@Serializable` (pas de reflection sur Kotlin/Native)
- Exception Ktor atteignant l'UI — mapper en `Result` / erreur de domaine
- Application des **deux** familles de plugins Compose oubliée (§2.3)

**Code quality** :
- `!!` sur une valeur non prouvée non-nulle
- `runBlocking` en code applicatif (interdit sur le main thread iOS)
- `GlobalScope` — utiliser `viewModelScope`
- `println` pour logger — utiliser Kermit (`println` n'apparaît pas dans les logs iOS)
- `@Composable` de plus de 50 lignes
- `TODO`, `FIXME`, code commenté

**Sécurité** :
- Token dans `multiplatform-settings` nu (non chiffré) — passer par la capability `secure-storage` + Keychain en `actual`
- Secret en dur dans `commonMain` (il finit dans les deux binaires)
- Log d'un token en clair
- Certificate pinning tenté en `commonMain` — il se configure par moteur, donc en `actual`
- Deep link sans validation de domaine

**Build / packaging** :
- Committer `build/`, `.gradle/`, `.kotlin/`, `iosApp/build/`, `local.properties`
- Dépôt Compose de JetBrains absent de `settings.gradle.kts` — la résolution de CMP échoue
- Cible `iosX64()` retirée « parce qu'on est sur Apple Silicon » — elle reste nécessaire aux simulateurs Intel en CI
- Prétendre à une validation iOS depuis un hôte non-macOS
- Wrapper Gradle non pinné

---

## 6. Persistance locale — voir §1.5

Stack client → pas de « DB scaffolding » serveur. Offline-first : capability `offline-db` (SQLDelight + les deux drivers). Phase B (DB) d'`arch` : **SKIP**.

---

## 7. Temps reel

- **WebSocket** : `ktor-client-websockets` (même moteur par cible)
- **SSE** : `ktor-client-core` avec réponse en streaming
- **Push** : APNS (iOS) et FCM (Android) se câblent en `actual` — aucune abstraction commune n'existe côté client. Le backend, lui, ne voit qu'un token d'appareil.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimisé pour :
- **Équipes Kotlin / Android** étendant leur app vers iOS sans repartir de zéro
- **Partage de logique métier avec un backend JVM** (`kotlin-spring-boot`) — modèles et validation littéralement communs
- **Règles métier complexes** à ne pas dupliquer entre deux plateformes
- **Migration progressive** : on peut partager le domain d'abord, l'UI ensuite (ou jamais)

**NE PAS choisir si** :
- ❌ **Aucune compétence Kotlin dans l'équipe** — la courbe KMP (source sets, `expect`/`actual`, résolution Gradle multiplateforme) s'ajoute à celle de Kotlin
- ❌ **Cible iOS uniquement** → `swiftui`. KMP n'apporte rien et coûte cher.
- ❌ **Cible Android uniquement** → `kotlin-android`, qui garde Retrofit / Room / Hilt (interdits ici)
- ❌ **Équipe React** → `react-native` ; **.NET** → `maui` ; **web** → `ionic-capacitor`
- ❌ **L'UI doit être 100 % natif-fidèle sur les deux OS** — Compose Multiplatform rend en Skia sur iOS, ce ne sont pas des vues UIKit. Envisager alors le **KMP à UI non partagée** (domain commun + SwiftUI + Compose), qui n'est pas la variante décrite ici.
- ❌ **Pas d'accès à un hôte macOS** — la cible iOS est incompilable, et donc invérifiable, sans Xcode
- ❌ **Besoin d'un écosystème de bibliothèques très large** — beaucoup de libs Android n'ont pas d'équivalent KMP. Chaque manque se paie en `expect`/`actual` écrit à la main.
- ❌ **Temps de build serré** — la compilation Kotlin/Native est nettement plus lente que celle de la JVM

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `mobile-kotlin-multiplatform` + `auth-local` (JWT) + backend `kotlin-spring-boot` | 🟡 experimental | combo à plus forte affinité (modèles partagés) — jamais validé end-to-end |
| `mobile-kotlin-multiplatform` + `auth-local` + backend `dotnet-minimalapi` | 🟡 experimental | jamais validé end-to-end |
| `mobile-kotlin-multiplatform` + `auth-azure-ad` + backend `kotlin-spring-boot` | 🟡 experimental | MSAL exige un `actual` par plateforme — non catalogué, à instruire |
| `mobile-kotlin-multiplatform` + `qa-kotlin-junit` | 🟡 experimental | `commonTest` tourne sous kotlin-test ; JUnit ne couvre que la cible JVM |

---

## 10. Notes pour l'agent `arch`

1. **Détecter** `mobiles/kotlin-multiplatform.md` en `## Active Tech Specs` → stack **mobile-only**
2. **Le backend reste déclaré séparément**. Si `backend/kotlin-spring-boot.md` est aussi déclaré, le signaler comme combo à forte affinité (modèles `@Serializable` partageables)
3. **STEP 0 — détection de l'hôte** : si `uname` ≠ `Darwin`, émettre un WARNING `[STACK_PARTIAL_TARGET]` — la cible iOS ne sera ni compilée ni validée. **Ne pas** échouer : la cible Android reste pleinement utilisable.
4. **Créer** `workspace/src/{AppName}/` via le scaffolding de §2.2.1 (pas de CLI officielle : le KMP Wizard de JetBrains est un service web, non scriptable)
5. **Dépôt Compose obligatoire** dans `settings.gradle.kts` (`maven.pkg.jetbrains.space/public/p/compose/dev`) — sans lui la résolution de CMP échoue
6. **Générer `gradle/libs.versions.toml`** depuis le `.libs.json` : `versions` → `[versions]`, `core`/`onDemand` → `[libraries]`, `plugins` → `[plugins]`. **Les deux** plugins Compose doivent y figurer (§2.3)
7. **Rattacher chaque lib à son source set** : les `rationale` du catalog nomment explicitement `commonMain` / `androidMain` / `iosMain` / `commonTest`. Tout mettre en `commonMain` casse la résolution.
8. **`## Active UI Specs`** : aucun design system web n'est compatible. CMP fournit Material 3. Si `shadcn` / `vuetify` / `radzen-blazor` est déclaré → WARNING bloquant `[STACK_INCOMPAT]`.
9. **Phase B (DB)** : SKIP. La capability `offline-db` ne déclenche pas le scan DB serveur.
10. **Phase C (ADRs)** : créer `ADR-{ts}-stack-mobile-kotlin-multiplatform.md` documentant Kotlin 2.4 + CMP 1.12 + Ktor + Koin + SQLDelight, le choix « UI partagée » plutôt que « domain seul », et les trois pièges du §2.3.

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack n'a PAS de « backend interne ». Convention :

- `dev-backend` **ne touche pas** au projet KMP — il code le backend séparé déclaré en `## Active Tech Specs backend/*`
- `dev-frontend` matérialise **tout** le projet KMP, y compris les `actual` de plateforme

**File ownership** (override `ownership.md §1 (Partie A)`) :

| Path | Owner |
|---|---|
| `composeApp/src/commonMain/**` | `dev-frontend` |
| `composeApp/src/androidMain/**`, `iosMain/**` | `dev-frontend` (`actual` uniquement) |
| `composeApp/src/commonTest/**` | `qa` |
| `composeApp/src/commonMain/sqldelight/**` | `dev-frontend` |
| `composeApp/src/commonMain/composeResources/**` | `dev-frontend` |
| `composeApp/build.gradle.kts` | `arch` (create) + `dev-frontend` (deps on-demand, rattachées au bon source set) |
| `build.gradle.kts`, `settings.gradle.kts`, `gradle/libs.versions.toml`, `gradle.properties` | `arch` exclusif |
| `iosApp/**` | `arch` (create) + `dev-frontend` (Info.plist, permissions) |

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/src/{AppName}

test -f settings.gradle.kts
test -f composeApp/build.gradle.kts
test -f gradle/libs.versions.toml

# Les DEUX plugins Compose (cf. 2.3)
grep -q "kotlin.compose" composeApp/build.gradle.kts
grep -q "compose.multiplatform" composeApp/build.gradle.kts

# Un moteur Ktor PAR CIBLE (cf. 2.3) — sinon echec au runtime, pas au build
grep -q "ktor.client.okhttp" composeApp/build.gradle.kts
grep -q "ktor.client.darwin" composeApp/build.gradle.kts

# Les artefacts multiplatform, pas leurs homonymes Android-only (cf. 2.3)
grep -q "org.jetbrains.androidx.lifecycle" gradle/libs.versions.toml
grep -q "org.jetbrains.androidx.navigation" gradle/libs.versions.toml

# Depot Compose de JetBrains
grep -q "maven.pkg.jetbrains.space" settings.gradle.kts

./gradlew :composeApp:assembleDebug --no-daemon
./gradlew :composeApp:allTests --no-daemon

# Cible iOS : macOS uniquement
if [ "$(uname)" = "Darwin" ]; then
  ./gradlew :composeApp:linkDebugFrameworkIosSimulatorArm64 --no-daemon
else
  echo "WARN: cible iOS non verifiee (hote non-macOS)"
fi

echo "smoke OK"
```
