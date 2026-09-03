# Tech FEAT: kotlin-android (mobile)

> §2.4 (Librairies) régénérée depuis `kotlin-android.libs.json` — ne pas éditer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id kotlin-android`).

Status: Stable
Validation: 🟡 scaffold-validated (Android 14+ LTS, Jetpack Compose stable) — bench 2026-06-05 : scaffold OK, runtime non testé end-to-end (SDK Android absent CI). Downgrade depuis 🟢 reference (audit CTO 2026-06-07 : version Kotlin antérieurement annoncée inexistante au registre Maven → pin alors corrigé sur la 2.0.21 dans `.libs.json`). **Audit 2026-09-02** : le stack était en réalité **non-buildable** — 6 défauts bloquants (2 `ref` de version pointant sur la mauvaise ligne de versionnage, `room-compiler` et `hilt-android-compiler` référencés en `ksp()` mais absents du catalog, plugin Compose manquant, bloc `android { }` placé dans le mauvais module Gradle). Toolchain rebasée : Kotlin passé de la 2.0.21 à la **2.4.10**, AGP de la 8.6.1 à la **8.13.2**, Gradle de la 8.10 à la **8.14.5**. Détail et justification dans §2.3.1. Reste 🟡 : toujours aucun `assembleDebug` exécuté en CI.
Tech FEAT ID: tech-kotlin-android
Scope: **application mobile native Android** — application Kotlin Jetpack Compose cible Android 7+ (API 24-36). Un seul projet `{AppName}/` sous `workspace/src/`. UI Compose + state + navigation + acces APIs natives vivent dans le même projet Kotlin. Pas de séparation `{BackendName}` / `{LibName}`.

> **Backend séparé** : ce stack est PUREMENT client mobile native Android. Il consomme une API backend distincte déclarée en `## Active Tech Specs` (ex. `backend/kotlin-spring-boot.md`, `backend/dotnet-minimalapi.md`). Pour un app simple sans backend distinct → utiliser un Backend-as-a-Service (Firebase, Supabase, Appwrite) configuré via env vars.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application Kotlin Jetpack Compose** cible Android 7+ (API 24) → Android 14+ (API 36) :

- **Jetpack Compose** (declarative UI, RemoteComposables pour re-rendering)
- **Kotlin Coroutines + Flow** (state management async, lifecycle-aware)
- **ViewModel + StateFlow** (MVVM pattern, state hoisting)
- **Hilt** (dependency injection, scope de composables)
- **Navigation Compose** (file-based routing implicite via NavController)
- **Retrofit + OkHttp** (HTTP clients, intercepteurs)
- **Room** (SQLite local, repository pattern)
- **Datastore** (preferences key-value async)
- **Material Design 3** (composables Material, theming light/dark)
- **Kotlin idioms** : `data class`, `sealed class`, extension functions

**Architecture cible (MVVM + Clean Architecture layers)** :

```
{AppName}/
├── app/
│   ├── src/main/
│   │   ├── kotlin/{AppNamespace}/
│   │   │   ├── MainActivity.kt                 ── Activity entry point
│   │   │   ├── presentation/
│   │   │   │   ├── screen/                     ── Écrans Compose
│   │   │   │   │   ├── LoginScreen.kt
│   │   │   │   │   ├── HomeScreen.kt
│   │   │   │   │   └── {Feature}Screen.kt
│   │   │   │   ├── component/                  ── Composables réutilisables
│   │   │   │   │   ├── CommonButton.kt
│   │   │   │   │   ├── InputField.kt
│   │   │   │   │   └── {Name}Component.kt
│   │   │   │   ├── viewmodel/                  ── ViewModels (state)
│   │   │   │   │   ├── LoginViewModel.kt
│   │   │   │   │   └── {Feature}ViewModel.kt
│   │   │   │   ├── navigation/
│   │   │   │   │   ├── NavGraph.kt             ── Navigation Compose
│   │   │   │   │   └── AppNavigation.kt
│   │   │   │   └── theme/
│   │   │   │       ├── Theme.kt                ── Material 3 theme
│   │   │   │       ├── Color.kt
│   │   │   │       └── Typography.kt
│   │   │   ├── domain/
│   │   │   │   ├── model/                      ── Entités métier
│   │   │   │   │   ├── User.kt
│   │   │   │   │   └── {Entity}.kt
│   │   │   │   ├── repository/                 ── Interfaces (contracts)
│   │   │   │   │   ├── UserRepository.kt
│   │   │   │   │   └── {Domain}Repository.kt
│   │   │   │   └── usecase/                    ── Logique métier
│   │   │   │       ├── GetUsersUsecase.kt
│   │   │   │       └── {Feature}Usecase.kt
│   │   │   ├── data/
│   │   │   │   ├── remote/                     ── API Retrofit
│   │   │   │   │   ├── api/
│   │   │   │   │   │   ├── ApiService.kt
│   │   │   │   │   │   └── {Domain}Api.kt
│   │   │   │   │   └── interceptor/
│   │   │   │   │       ├── AuthInterceptor.kt
│   │   │   │   │       └── LoggingInterceptor.kt
│   │   │   │   ├── local/                      ── Room + Datastore
│   │   │   │   │   ├── dao/
│   │   │   │   │   │   ├── UserDao.kt
│   │   │   │   │   │   └── {Entity}Dao.kt
│   │   │   │   │   ├── entity/
│   │   │   │   │   │   ├── UserEntity.kt
│   │   │   │   │   │   └── {Entity}Entity.kt
│   │   │   │   │   ├── database/
│   │   │   │   │   │   └── AppDatabase.kt
│   │   │   │   │   └── preferences/
│   │   │   │   │       └── DatastorePreferences.kt
│   │   │   │   └── repository/                 ── Implémentations
│   │   │   │       ├── UserRepositoryImpl.kt
│   │   │   │       └── {Domain}RepositoryImpl.kt
│   │   │   ├── di/                              ── Hilt modules
│   │   │   │   ├── NetworkModule.kt
│   │   │   │   ├── DatabaseModule.kt
│   │   │   │   ├── RepositoryModule.kt
│   │   │   │   └── UseCaseModule.kt
│   │   │   ├── util/
│   │   │   │   ├── Constants.kt
│   │   │   │   ├── Extensions.kt
│   │   │   │   ├── NetworkUtils.kt
│   │   │   │   └── Logger.kt
│   │   │   └── {AppName}Application.kt        ── Application (Hilt init)
│   │   ├── res/
│   │   │   ├── values/
│   │   │   │   └── strings.xml
│   │   │   ├── drawable/
│   │   │   │   └── (vecteurs, images)
│   │   │   └── mipmap/
│   │   │       └── (icons app, splashes)
│   │   └── AndroidManifest.xml
│   ├── build.gradle.kts
│   └── settings.gradle.kts
└── gradle/
    └── libs.versions.toml                      ── Version catalog
```

**Différence vs `.sdd/stacks/frontend/react.md`** :
- Pas de Web Browser — API Android native (Activities, Services, Intents)
- Pas de CSS — UI Compose (Kotlin DSL declarative)
- Pas de routing URL — Navigation Compose + NavGraph
- Pas de bundler — Android Gradle Plugin compile + package APK/AAB
- Accès APIs natives via Android SDK (`Intent`, `PendingIntent`, permissions runtime)
- Storage local persistant via Room (SQLite) et Datastore (key-value async)
- Logging via Timber (wrapper SLF4J-like Android idiom)

---

## 1.2 Couches Clean Architecture

- **Presentation** (`presentation/`) : Composables, ViewModels, state (StateFlow)
- **Domain** (`domain/`) : Entities métier, Repository interfaces, UseCases (zéro dépendance Android)
- **Data** (`data/`) : Remote (Retrofit API), Local (Room DB), Repository impls

Dépendances : Domain ← Data, Domain ← Presentation, Presentation → Domain + Data.

---

## 1.3 Mapping couche → répertoire

| Couche canonique | Path Kotlin/Android-specific |
|---|---|
| Application entry | `src/main/kotlin/{AppNamespace}/{AppName}Application.kt` (`@HiltAndroidApp`) |
| Activity | `src/main/kotlin/{AppNamespace}/MainActivity.kt` (setContent Compose) |
| Composable screen | `src/main/kotlin/{AppNamespace}/presentation/screen/{Feature}Screen.kt` |
| Composable component | `src/main/kotlin/{AppNamespace}/presentation/component/{Name}Component.kt` |
| ViewModel | `src/main/kotlin/{AppNamespace}/presentation/viewmodel/{Feature}ViewModel.kt` |
| Theme (Material 3) | `src/main/kotlin/{AppNamespace}/presentation/theme/Theme.kt` + `Color.kt` + `Typography.kt` |
| Navigation graph | `src/main/kotlin/{AppNamespace}/presentation/navigation/AppNavigation.kt` |
| Entity métier | `src/main/kotlin/{AppNamespace}/domain/model/{Entity}.kt` |
| Repository interface | `src/main/kotlin/{AppNamespace}/domain/repository/{Domain}Repository.kt` |
| UseCase | `src/main/kotlin/{AppNamespace}/domain/usecase/{Feature}Usecase.kt` |
| API Service (Retrofit) | `src/main/kotlin/{AppNamespace}/data/remote/api/{Domain}Api.kt` |
| HTTP Interceptor | `src/main/kotlin/{AppNamespace}/data/remote/interceptor/{Name}Interceptor.kt` |
| DAO (Room) | `src/main/kotlin/{AppNamespace}/data/local/dao/{Entity}Dao.kt` |
| Room Entity | `src/main/kotlin/{AppNamespace}/data/local/entity/{Entity}Entity.kt` |
| Room Database | `src/main/kotlin/{AppNamespace}/data/local/database/AppDatabase.kt` |
| Datastore Preferences | `src/main/kotlin/{AppNamespace}/data/local/preferences/DatastorePreferences.kt` |
| Repository impl | `src/main/kotlin/{AppNamespace}/data/repository/{Domain}RepositoryImpl.kt` |
| Hilt Module (DI) | `src/main/kotlin/{AppNamespace}/di/{Module}Module.kt` |
| Utilities | `src/main/kotlin/{AppNamespace}/util/{Name}.kt` |
| Logger | `src/main/kotlin/{AppNamespace}/util/Logger.kt` |
| Application config | `src/main/AndroidManifest.xml` |
| Resources | `src/main/res/{values,drawable,mipmap}/` |
| Gradle build | `build.gradle.kts` |
| Version catalog | `gradle/libs.versions.toml` |

> **Note** : ce stack utilise un mono-projet `{AppName}/` (pas de `{LibName}` séparé). Shared model DTOs vivent dans `domain/model/` (zéro dépendance Android).

---

## 1.4 Override principes (Kotlin/Android-specific)

- **Data classes** pour Entities (`val`, immuables par construction, `@Entity` JPA Room)
- **Sealed classes** pour ADT (algebraic data types) — état fini (`Success`, `Error`, `Loading`)
- **Extension functions** pour réduction boilerplate
- **Coroutines** pour tout I/O async (Retrofit suspend fun, Room queries, Datastore)
- **StateFlow** pour state reactif lifecycle-aware (souscriptions auto-détruites à onCleared)
- **Dependency Injection via Hilt** — jamais `ServiceLocator` ou singleton manuels
- **Timber** pour logging (wrapper SLF4J-like Android standard)
- **Material Design 3** pour UI (pas custom themes sauf override tokens)
- **Permissions runtime** (API 23+) : déclaration `AndroidManifest.xml` + demande runtime via Accompanist
- **BuildConfig** pour secrets (API keys injected par CI, **jamais** hardcoded)
- **Proguard/R8** minification en release (défaut AGP 8.2+)

---

# 2. Stack

## 2.1 Identité

- **Stack ID** : `mobile-kotlin-android`
- **Langage** : Kotlin 2.4.10
- **Runtime** : Android SDK — minSdk 24 (Android 7.0), compileSdk/targetSdk 36 (Android 16)
- **Framework principal** : Jetpack Compose UI (BOM `2026.08.00`) + Android Gradle Plugin 8.13.2
- **Build tool** : **Gradle 8.14.5** avec **Kotlin DSL** (`build.gradle.kts`) — JDK 17 (toolchain et `jvmTarget`)
- **Package racine** : `{AppNamespace}` (ex. `com.example.mobile`)
- **IDE** : Android Studio (canal stable supportant AGP 8.13)

## 2.2 Outils

- **Project file** : `workspace/src/{AppName}/settings.gradle.kts` (racine du build) + `app/build.gradle.kts` (module applicatif)
- **Build APK debug** : `cd workspace/src/{AppName} && ./gradlew assembleDebug`
- **Build APK release** : `cd workspace/src/{AppName} && ./gradlew assembleRelease`
- **Unit tests** : `./gradlew :app:testDebugUnitTest`
- **Instrumented tests (Emulator)** : `./gradlew :app:connectedDebugAndroidTest` (capability `compose-ui-tests`)
- **Smoke Command** (build seulement) :
  ```bash
  cd workspace/src/{AppName} && ./gradlew clean assembleDebug --no-daemon
  RC=$?; exit $RC
  ```
- **Smoke Timeout** : 120s (Gradle warmup + build resources)
- **Lint** : `./gradlew lint` (AndroidLint natif)
- **Format** : `./gradlew spotlessApply` (Spotless + ktfmt)
- **Type-check** : intégré au compile Kotlin
- **Package manager** : Maven Central via Gradle
- **Test** : voir `qa/kotlin-android-espresso.md` (voir note v7.0.0)

## 2.2.1 Init Commands

> **Layout Gradle** : le projet est un build Gradle multi-modules a un seul
> module applicatif `:app`. Consequence non negociable : le bloc `android { }`
> vit dans **`app/build.gradle.kts`**, jamais dans le `build.gradle.kts`
> racine. Le scaffolding anterieur mettait `android { }` a la racine alors que
> les sources etaient sous `app/src/main/` — configuration invalide, le build
> echouait (corrige 2026-09-02, cf. §2.3).

```bash
# Idempotent : skip si le build racine existe deja

if [ ! -f "workspace/src/{AppName}/settings.gradle.kts" ]; then
  APP=workspace/src/{AppName}

  # STEP 1 — Arborescence Clean Architecture (module :app)
  mkdir -p "$APP/app/src/main/res/values" \
           "$APP/app/src/main/res/drawable" \
           "$APP/app/src/main/res/mipmap" \
           "$APP/app/src/test/kotlin/{AppNamespace}" \
           "$APP/app/src/androidTest/kotlin/{AppNamespace}" \
           "$APP/gradle"

  for layer in \
      presentation/screen presentation/component presentation/viewmodel \
      presentation/navigation presentation/theme \
      domain/model domain/repository domain/usecase \
      data/remote/api data/remote/interceptor \
      data/local/dao data/local/entity data/local/database data/local/preferences \
      data/repository di util ; do
    mkdir -p "$APP/app/src/main/kotlin/{AppNamespace}/$layer"
  done

  # STEP 2 — settings.gradle.kts (declare le module :app + les depots)
  cat > "$APP/settings.gradle.kts" << 'EOF'
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "{AppName}"
include(":app")
EOF

  # STEP 3 — build.gradle.kts RACINE : declare les plugins sans les appliquer
  cat > "$APP/build.gradle.kts" << 'EOF'
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.hilt) apply false
    alias(libs.plugins.spotless)
}
EOF

  # STEP 4 — app/build.gradle.kts : c'est ICI que vit le bloc android { }
  cat > "$APP/app/build.gradle.kts" << 'EOF'
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    // OBLIGATOIRE depuis Kotlin 2.0+ : remplace composeOptions {}
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
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
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
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

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // Les sources vivent sous src/main/kotlin (et non src/main/java)
    sourceSets["main"].kotlin.srcDir("src/main/kotlin")
}

kotlin {
    // `kotlinOptions { }` est deprecie -> bloc compilerOptions
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    // --- Compose : le BOM fixe les versions, les artefacts n'en portent pas
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.runtime)
    implementation(libs.compose.foundation)
    implementation(libs.navigation.compose)

    // --- AndroidX socle
    implementation(libs.core.ktx)
    implementation(libs.activity.compose)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.ktx)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.runtime.compose)

    // --- DI Hilt (le compiler passe par ksp, pas implementation)
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    // --- Reseau
    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging.interceptor)
    implementation(libs.kotlinx.serialization.json)

    // --- Persistance
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    implementation(libs.datastore.preferences)

    // --- Coroutines
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    // --- Observabilite
    implementation(libs.timber)

    // --- Tests JVM
    testImplementation(libs.junit)
    testImplementation(libs.mockk)
    testImplementation(libs.kotlinx.coroutines.test)
}
EOF

  # STEP 5 — gradle/libs.versions.toml genere depuis kotlin-android.libs.json
  # (generateur deterministe cote arch : chaque `ref` du .libs.json devient une
  #  entree [versions], chaque `module` une entree [libraries], chaque `plugins[]`
  #  une entree [plugins]. Les libs SANS version -> pas d'attribut `version.ref`,
  #  elles sont resolues par le BOM.)

  # STEP 6 — gradle.properties (AndroidX + cache de configuration)
  cat > "$APP/gradle.properties" << 'EOF'
android.useAndroidX=true
android.nonTransitiveRClass=true
org.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=768m
org.gradle.caching=true
org.gradle.configuration-cache=true
kotlin.code.style=official
EOF

  # STEP 7 — Wrapper Gradle pinne (cf. versions.gradle du .libs.json)
  (cd "$APP" && gradle wrapper --gradle-version 8.14.5 --distribution-type bin)
fi

# STEP 8 — Validation build
(cd workspace/src/{AppName} && ./gradlew :app:compileDebugKotlin --no-daemon)
```

**Contrat post-init** :
- `settings.gradle.kts` declare `include(":app")`
- `app/build.gradle.kts` porte le bloc `android { }` (et **pas** la racine)
- Le plugin `org.jetbrains.kotlin.plugin.compose` est applique sur `:app`
- `gradle/libs.versions.toml` existe et expose un alias pour **chaque** entree
  du `.libs.json`, y compris `room-compiler` et `hilt-android-compiler`
- `app/src/main/AndroidManifest.xml` existe
- `./gradlew :app:compileDebugKotlin` sort 0

---

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis kotlin-android.libs.json -- ne pas editer (utiliser sync_stack_md.py).
# Gradle managed via build.gradle.kts + gradle/libs.versions.toml.
# Versions auto-derivees de kotlin-android.libs.json -- regenerer le catalog Gradle
# en cas de bump (cf. gradle/libs.versions.toml).
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis kotlin-android.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: compose-tooling
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.compose.ui:ui-tooling:")

# capability: compose-ui-tests
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.compose.ui:ui-test-junit4:")
#   implementation("androidx.test.ext:junit:1.3.0")
#   implementation("androidx.test.espresso:espresso-core:3.7.0")

# capability: flow-testing
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("app.cash.turbine:turbine:1.2.1")

# capability: image-loading
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("io.coil-kt.coil3:coil-compose:3.6.1")
#   implementation("io.coil-kt.coil3:coil-network-okhttp:3.6.1")

# capability: firebase
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.firebase:firebase-bom:34.18.0")
#   implementation("com.google.firebase:firebase-messaging:")

# capability: camera
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.camera:camera-core:1.6.2")
#   implementation("androidx.camera:camera-camera2:1.6.2")
#   implementation("androidx.camera:camera-lifecycle:1.6.2")
#   implementation("androidx.camera:camera-view:1.6.2")

# capability: permissions
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.accompanist:accompanist-permissions:0.37.3")

# capability: background-jobs
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.work:work-runtime-ktx:2.11.2")

# capability: google-maps
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.maps.android:maps-compose:8.5.0")

# capability: location
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.android.gms:play-services-location:21.4.0")

# capability: paging
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.paging:paging-compose:3.5.1")

# capability: splashscreen
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.core:core-splashscreen:1.2.0")

# capability: biometric
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.biometric:biometric:1.1.0")
```
<!-- ONDEMAND_PACKAGES_END -->

### 2.2.2 Plugins Gradle obligatoires (`app/build.gradle.kts`)

```kotlin
plugins {
    alias(libs.plugins.android.application)   // com.android.application (AGP)
    alias(libs.plugins.kotlin.android)        // org.jetbrains.kotlin.android
    alias(libs.plugins.kotlin.compose)        // org.jetbrains.kotlin.plugin.compose
    alias(libs.plugins.kotlin.serialization)  // org.jetbrains.kotlin.plugin.serialization
    alias(libs.plugins.ksp)                   // com.google.devtools.ksp (Room, Hilt)
    alias(libs.plugins.hilt)                  // com.google.dagger.hilt.android
}

android {
    namespace = "{AppNamespace}"
    compileSdk = 36

    // minSdk / targetSdk vivent dans defaultConfig — les poser directement
    // dans `android { }` est une erreur de DSL (ne compile pas).
    defaultConfig {
        minSdk = 24
        targetSdk = 36
    }

    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}
```

> **Trois pieges fermes ici** (cf. §2.3.1) :
> 1. `composeOptions { kotlinCompilerExtensionVersion = ... }` **n'existe plus**.
>    Depuis Kotlin 2.0+ le compilateur Compose est un plugin Gradle
>    (`org.jetbrains.kotlin.plugin.compose`) versionne avec Kotlin.
> 2. `kotlinOptions { jvmTarget = "..." }` est deprecie — utiliser le bloc
>    `kotlin { compilerOptions { } }`.
> 3. `libs.plugins.android.kotlin` etait commente « Kotlin Multiplatform » :
>    ce stack est **Android natif**, pas KMP. Pour du multiplateforme reel,
>    c'est `mobiles/kotlin-multiplatform.md`.

## 2.3 Patterns d'erreurs compilation

Format AGP/Kotlin : `{path}.kt:{line}:{col}: error: {message}`

### 2.3.1 Toolchain et defauts fermes (audit 2026-09-02)

#### Toolchain retenue

| Composant | Version | Pourquoi celle-la |
|---|---|---|
| Kotlin | `2.4.10` | Derniere stable Maven Central |
| AGP | `8.13.2` | **Derniere 8.x**, pas la 9.4.0 — voir encadre ci-dessous |
| Gradle | `8.14.5` | Paire testee avec AGP 8.13 |
| JDK / `jvmTarget` | `17` | Plancher exige par AGP 8.13 et cible universellement supportee par R8/D8, sans desugaring de bibliotheque core |
| compileSdk / targetSdk | `36` | API 36 = Android 16. L'API 37 existe mais demande la ligne AGP 9 |
| minSdk | `24` | Android 7.0 |
| Compose BOM | `2026.08.00` | Fixe `ui` / `material3` / `foundation` / `runtime` d'un seul tenant |

> **Pourquoi AGP 8.13.2 et non 9.4.0.** La ligne 9 est stable (9.4.0 publiee) mais
> change les defauts du DSL. Le scaffolding de §2.2.1 est ecrit et relu pour AGP 8.x,
> et ce stack est `🟡 scaffold-validated` : il n'a pas de bench runtime qui
> permettrait de valider une migration majeure. Bumper AGP en 9.x est donc une
> **tache dediee** (regenerer §2.2.1 + re-valider `assembleDebug`), pas un bump de
> version dans le `.libs.json`.

#### Defauts corriges

Six defauts rendaient ce stack non-buildable en l'etat. Ils partagent une meme
cause : le `.md` referencait des alias que le `.libs.json` ne declarait pas, et
deux `ref` de versions pointaient sur la mauvaise ligne de versionnage.

| # | Defaut | Effet | Correction |
|---|---|---|---|
| 1 | `androidx.navigation:navigation-compose` avait `ref: compose` → resolu en **1.7.0** | Cette version n'existe pas pour cet artefact (ligne `2.x`) → `Could not find` | `ref: androidx-navigation` = `2.10.0` |
| 2 | `kotlinx-coroutines-core` / `-android` avaient `ref: kotlin` → resolu en **2.0.21** | Les coroutines sont en ligne `1.x` → `Could not find` | `ref: coroutines` = `1.11.0` |
| 3 | `androidx.room:room-compiler` **absent** du catalog alors que §2.2.1 faisait `ksp(libs.room.compiler)` | Alias inconnu dans le version catalog → echec de configuration. Et meme sans ca : aucun `@Dao`/`@Database` n'est genere | ajoute en CORE |
| 4 | `com.google.dagger:hilt-android-compiler` **absent**, idem `ksp(libs.hilt.compiler)` | Identique — le graphe DI n'est jamais genere | ajoute en CORE |
| 5 | Plugin `org.jetbrains.kotlin.plugin.compose` **absent** ; le `.md` utilisait `composeOptions { kotlinCompilerExtensionVersion = "1.5.15" }` | Ce bloc n'est plus lu depuis Kotlin 2.0+ → **aucun `@Composable` ne compile** | plugin ajoute ; `composeOptions` retire |
| 6 | `androidx.room:room-ktx` declare **deux fois** (CORE + onDemand `room-database`) | Doublon de resolution, capability trompeuse | garde en CORE seulement |

Defaut structurel corrige au meme passage : le `build.gradle.kts` de §2.2.1
portait le bloc `android { }` **a la racine** du build alors que les sources
etaient sous `app/src/main/`. Un bloc `android { }` ne peut vivre que dans un
module ou le plugin `com.android.application` est applique — la configuration
etait invalide. Le layout est desormais explicite : racine = declaration des
plugins (`apply false`), `app/build.gradle.kts` = bloc `android { }`.

#### Ajouts (manques fonctionnels, pas des bugs)

- `androidx.activity:activity-compose` en CORE — `setContent { }` en venait,
  aucun ecran ne pouvait s'afficher sans.
- `lifecycle-runtime-compose` — `collectAsStateWithLifecycle()`, seule facon
  correcte de consommer un `StateFlow` depuis un `@Composable`.
- `compose-bom` — les artefacts Compose etaient pinnes un a un, a la main.
- Plugin `kotlin.plugin.serialization` — `kotlinx-serialization-json` etait
  declare mais rien ne generait les serializers de `@Serializable`.
- Socle de test en CORE (`junit`, `mockk`, `kotlinx-coroutines-test`) : §2.2.1
  faisait `testImplementation(libs.junit)` sans que le catalog le declare.
  MockK plutot que Mockito : Mockito ne sait pas mocker une classe `final`
  (le defaut en Kotlin) ni une `suspend fun`.
- Capabilities `image-loading` (Coil 3), `compose-ui-tests`, `flow-testing`
  (Turbine), `location`, `splashscreen`, `biometric`.

> Coil 3 se declare en **deux** artefacts : `coil-compose` **et**
> `coil-network-okhttp`. La v3 ne fournit plus de client HTTP par defaut —
> sans le second, tout chargement distant echoue au runtime.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/mobiles/kotlin-android.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id kotlin-android`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| kotlin-stdlib | 2.4.10 | Stdlib Kotlin core |
| compose-bom | 2026.08.00 | BOM Compose — aligne ui / material3 / foundation / runtime sur un train teste ensemble. Les artefacts Compose ci-dessous sont donc declares SANS version (c'est le BOM qui la fixe) |
| ui |  | Jetpack Compose UI foundation (Layout, Modifier, State) — version via compose-bom |
| ui-graphics |  | Primitives graphiques Compose — version via compose-bom |
| ui-tooling-preview |  | Annotation @Preview (le pendant debug ui-tooling est en capability compose-tooling) — version via compose-bom |
| material3 |  | Material Design 3 (Button, Card, TextField, Scaffold) — version via compose-bom |
| runtime |  | Compose runtime (recomposition, State, Effect) — version via compose-bom |
| foundation |  | Layouts fondation (Box, Row, Column, LazyColumn/LazyRow) — version via compose-bom |
| navigation-compose | 2.10.0 | Navigation Compose (NavController, NavGraph, routes typees). VERSION PROPRE : ce module suit la ligne androidx.navigation 2.x, il n'a jamais eu de 1.7.x — le catalog le pointait a tort sur la version Compose (bug corrige 2026-09-02) |
| core-ktx | 1.19.0 | Extensions Kotlin des APIs Android core |
| activity-compose | 1.13.0 | Pont Activity <-> Compose (setContent, LocalContext) — sans lui aucun ecran ne s'affiche |
| lifecycle-runtime-ktx | 2.11.0 | Coroutines lifecycle-aware (lifecycleScope, repeatOnLifecycle) |
| lifecycle-viewmodel-ktx | 2.11.0 | ViewModel + viewModelScope |
| lifecycle-viewmodel-compose | 2.11.0 | viewModel() cote Compose |
| lifecycle-runtime-compose | 2.11.0 | collectAsStateWithLifecycle — la seule facon correcte de consommer un StateFlow depuis un @Composable |
| room-runtime | 2.8.4 | Room (SQLite ORM : @Entity, @Dao, @Database) |
| room-ktx | 2.8.4 | Extensions Kotlin Room (suspend fun, requetes Flow) |
| room-compiler | 2.8.4 | Processeur KSP Room — OBLIGATOIRE, il genere les implementations de @Dao/@Database. Absent du catalog avant l'audit 2026-09-02 alors que le build.gradle.kts de la 2.2.1 faisait deja ksp(libs.room.compiler) : le build echouait sur un alias inconnu |
| datastore-preferences | 1.2.1 | Stockage cle-valeur asynchrone (remplacant moderne de SharedPreferences) |
| hilt-android | 2.60.1 | Injection de dependances (@Inject, @Module, @HiltViewModel) |
| hilt-android-compiler | 2.60.1 | Processeur KSP Hilt — OBLIGATOIRE, il genere le graphe DI. Meme bug que room-compiler : reference par la 2.2.1, absent du catalog (corrige 2026-09-02) |
| retrofit | 3.0.0 | Client HTTP REST declaratif (interfaces suspend) |
| converter-kotlinx-serialization | 3.0.0 | Converter Retrofit <-> kotlinx.serialization |
| okhttp | 5.5.0 | Moteur HTTP (pool de connexions, interceptors) |
| logging-interceptor | 5.5.0 | Log des requetes/reponses en debug |
| kotlinx-serialization-json | 1.11.0 | Parseur JSON Kotlin-native |
| kotlinx-coroutines-core | 1.11.0 | Coroutines (Flow, async, withContext). VERSION PROPRE : ligne 1.x — le catalog la pointait a tort sur la version Kotlin (2.0.21), version qui n'existe pas pour cet artefact (bug corrige 2026-09-02) |
| kotlinx-coroutines-android | 1.11.0 | Dispatchers.Main Android. Meme correction de ref que ci-dessus |
| timber | 5.0.1 | Logger (arbre de debug plugable) |
| junit | 4.13.2 | Tests unitaires JVM (testImplementation) — le stack n'en declarait aucun malgre le testImplementation(libs.junit) de la 2.2.1 |
| mockk | 1.14.11 | Mocking idiomatique Kotlin (objets final/suspend) — remplace Mockito, inadapte a Kotlin |
| kotlinx-coroutines-test | 1.11.0 | runTest + TestDispatcher — indispensable pour tester un ViewModel |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| compose-tooling | ui-tooling |  | preview.*compose, compose.*preview, layout.*inspector |
| compose-ui-tests | ui-test-junit4 |  | tests.*ui, compose.*test, instrumented.*test |
| compose-ui-tests | junit | 1.3.0 | tests.*ui, instrumented.*test, androidtest |
| compose-ui-tests | espresso-core | 3.7.0 | espresso, tests.*ui, instrumented.*test |
| flow-testing | turbine | 1.2.1 | test.*flow, turbine, stateflow.*test |
| image-loading | coil-compose | 3.6.1 | image.*distante, avatar, charger.*image, coil, vignette |
| image-loading | coil-network-okhttp | 3.6.1 | image.*distante, coil |
| firebase | firebase-bom | 34.18.0 | \bfirebase\b, cloud messaging, notifications push, fcm |
| firebase | firebase-messaging |  | \bfirebase\b, cloud messaging, notifications push |
| camera | camera-core | 1.6.2 | \bcamera\b, photo capture, video record |
| camera | camera-camera2 | 1.6.2 | \bcamera\b, photo capture, video record |
| camera | camera-lifecycle | 1.6.2 | \bcamera\b |
| camera | camera-view | 1.6.2 | \bcamera\b, apercu.*camera |
| permissions | accompanist-permissions | 0.37.3 | permissions runtime, permission compose, permission ui |
| background-jobs | work-runtime-ktx | 2.11.2 | background job, scheduled task, periodic work, workmanager |
| google-maps | maps-compose | 8.5.0 | google maps, \bmaps\b, location map |
| location | play-services-location | 21.4.0 | gps, geolocalisation, position.*utilisateur, localisation |
| paging | paging-compose | 3.5.1 | paging, pagination, lazy load, infinite scroll |
| splashscreen | core-splashscreen | 1.2.0 | splash, ecran.*demarrage, splashscreen |
| biometric | biometric | 1.1.0 | biometric, empreinte, fingerprint, face.*unlock |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| com.android.application | 8.13.2 | Plugin application Android (packaging apk/aab, merge manifest/resources) |
| org.jetbrains.kotlin.android | 2.4.10 | Compilateur Kotlin cible Android |
| org.jetbrains.kotlin.plugin.compose | 2.4.10 | Compilateur Compose. OBLIGATOIRE depuis Kotlin 2.0+ : il est versionne avec Kotlin et remplace le bloc `composeOptions { kotlinCompilerExtensionVersion }`, qui n'est plus lu. Absent du catalog avant l'audit 2026-09-02 — aucun @Composable ne compilait |
| org.jetbrains.kotlin.plugin.serialization | 2.4.10 | Genere les serializers pour @Serializable — requis par kotlinx-serialization-json et par le converter Retrofit |
| com.google.devtools.ksp | 2.3.11 | Kotlin Symbol Processing — moteur des processeurs Room et Hilt. Depuis KSP2 le plugin a son propre versionnage (2.3.x), il n'est plus suffixe par la version Kotlin |
| com.google.dagger.hilt.android | 2.60.1 | Plugin Hilt (@HiltAndroidApp, @HiltViewModel) |
| com.diffplug.spotless | 8.10.1 | Formatage ktfmt (taches spotlessCheck / spotlessApply) |
<!-- LIBS_CATALOG_END -->

---

# 3. Conventions de développement (Kotlin/Android idioms)

## 3.1 ViewModels et State Management

```kotlin
@HiltViewModel
class LoginViewModel @Inject constructor(
    private val authUsecase: AuthUsecase
) : ViewModel() {
    private val _uiState = MutableStateFlow<LoginUiState>(LoginUiState.Initial)
    val uiState: StateFlow<LoginUiState> = _uiState.asStateFlow()

    fun login(email: String, password: String) {
        viewModelScope.launch {
            try {
                _uiState.value = LoginUiState.Loading
                authUsecase.login(email, password)
                _uiState.value = LoginUiState.Success
            } catch (e: Exception) {
                _uiState.value = LoginUiState.Error(e.message.orEmpty())
            }
        }
    }
}

sealed class LoginUiState {
    object Initial : LoginUiState()
    object Loading : LoginUiState()
    object Success : LoginUiState()
    data class Error(val message: String) : LoginUiState()
}
```

## 3.2 Composables

```kotlin
@Composable
fun LoginScreen(
    viewModel: LoginViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    
    when (uiState) {
        is LoginUiState.Loading -> LoadingIndicator()
        is LoginUiState.Error -> ErrorMessage((uiState as LoginUiState.Error).message)
        is LoginUiState.Success -> LaunchedEffect(Unit) { /* navigate */ }
        else -> LoginForm(onSubmit = { email, pwd -> viewModel.login(email, pwd) })
    }
}
```

## 3.3 Repository Pattern

```kotlin
class UserRepositoryImpl @Inject constructor(
    private val userApi: UserApi,
    private val userDao: UserDao
) : UserRepository {
    override suspend fun getUsers(): Result<List<User>> = withContext(Dispatchers.IO) {
        return@withContext try {
            val remoteUsers = userApi.getUsers()
            userDao.insertAll(remoteUsers.map { it.toEntity() })
            Result.success(remoteUsers)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
```

## 3.4 Hilt DI Modules

```kotlin
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides
    @Singleton
    fun provideRetrofit(): Retrofit = Retrofit.Builder()
        .baseUrl("https://api.example.com/")
        .client(OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor())
            .build())
        .addConverterFactory(Json.asConverterFactory("application/json".toMediaType()))
        .build()
    
    @Provides
    @Singleton
    fun provideUserApi(retrofit: Retrofit): UserApi = retrofit.create(UserApi::class.java)
}
```

---

# 4. Configuration & Secrets

## 4.1 BuildConfig

API keys et secrets injected par CI (jamais hardcodés) :

```kotlin
// build.gradle.kts
android {
    defaultConfig {
        buildConfigField("String", "API_BASE_URL", "\"https://api.example.com/\"")
        buildConfigField("String", "API_KEY", "\"${System.getenv("API_KEY") ?: "dev"}\"")
    }
}

// Utilisation
val apiBaseUrl = BuildConfig.API_BASE_URL
```

## 4.2 AndroidManifest.xml

Permissions et configuration de base :

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    
    <application
        android:name=".{AppName}Application"
        android:usesCleartextTraffic="false"
        android:icon="@mipmap/ic_launcher">
        
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

---

# 5. API & Logging

## 5.1 Retrofit Setup avec Intercepteurs

```kotlin
val okHttpClient = OkHttpClient.Builder()
    .addInterceptor(AuthInterceptor()) // Ajoute Authorization Bearer token
    .addInterceptor(LoggingInterceptor()) // Logs request/response
    .addInterceptor(HttpLoggingInterceptor().setLevel(HttpLoggingInterceptor.Level.BODY))
    .build()

val retrofit = Retrofit.Builder()
    .baseUrl(BuildConfig.API_BASE_URL)
    .client(okHttpClient)
    .addConverterFactory(Json.asConverterFactory("application/json".toMediaType()))
    .build()
```

## 5.2 Timber Logging

```kotlin
// Application init
Timber.plant(DebugTree()) // Debug logs en dev

// Utilisation
Timber.d("Debug message")
Timber.e(exception, "Error message")
Timber.i("Info message")
```

---

# 6. Testing (voir `qa/kotlin-android-espresso.md`)

> **Note v7.0.0** : Stack QA dédié `qa/kotlin-android-espresso.md` (Instrumented + Unit tests, JUnit 4, Espresso, Mockito). Ce stack mobile ne gère pas la génération des tests — QA seul propriétaire.

---

# 7. Performance & Best Practices

## 7.1 Composition Stability

- Éviter `@Composable` lambdas inline (créent des instances) → utiliser `remember { derivedStateOf }` ou extracted composables
- `LazyColumn` au lieu de `Column` pour listes longues
- `rememberCoroutineScope()` pour event handlers

## 7.2 Memory Leaks

- ViewModels auto-cleared `onCleared()`
- `lifecycleScope` au lieu de `GlobalScope`
- Dé-subscribe Flow via `collectAsStateWithLifecycle()` (lifecycle-aware)

## 7.3 Minification Release

- AGP 8.2+ compile avec R8 par défaut
- ProGuard rules pour libs tierces (ex. Retrofit, Hilt) fournis par les libs
- Tester build release régulièrement

---

# 8. Déploiement

- **Debug APK** : `./gradlew assembleDebug` → `.apk` testable sur émulateur/device
- **Release AAB** : `./gradlew bundleRelease` → `.aab` pour Google Play
- **Signing** : keystore (`release.keystore`) injected en CI, jamais en repo
