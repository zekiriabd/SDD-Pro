# Tech FEAT: kotlin-android (mobile)

> §2.4 (Librairies) régénérée depuis `kotlin-android.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-android`).

Status: Stable
Validation: 🟡 scaffold-validated (Android 14+ LTS, Kotlin 2.0.21 LTS-aligned via Java 21, Jetpack Compose stable) — bench 2026-06-05 : scaffold OK, runtime non testé end-to-end (SDK Android absent CI). Downgrade depuis 🟢 reference (audit CTO 2026-06-07 : version Kotlin antérieurement annoncée inexistante au registre Maven → pin corrigé sur 2.0.21 dans `.libs.json`)
Tech FEAT ID: tech-kotlin-android
Scope: **application mobile native Android** — application Kotlin Jetpack Compose cible Android 7+ (API 24-36). Un seul projet `{AppName}/` sous `workspace/output/src/`. UI Compose + state + navigation + acces APIs natives vivent dans le même projet Kotlin. Pas de séparation `{BackendName}` / `{LibName}`.

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

**Différence vs `.claude/stacks/frontend/react.md`** :
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
- **Langage** : Kotlin 2.0.21 (LTS-aligned via Java 21)
- **Runtime** : Android SDK Min 24 (Android 7.0), Target 36 (Android 14)
- **Framework principal** : Jetpack Compose UI + Android Gradle Plugin 8.6.1
- **Build tool** : **Gradle 8.10** avec **Kotlin DSL** (`build.gradle.kts`)
- **Package racine** : `{AppNamespace}` (ex. `com.softwe3.mobile`)
- **IDE** : Android Studio 2024.2.1+

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/build.gradle.kts`
- **Build APK debug** : `cd workspace/output/src/{AppName} && ./gradlew assembleDebug`
- **Build APK release** : `cd workspace/output/src/{AppName} && ./gradlew assembleRelease`
- **Unit tests** : `./gradlew testDebugUnitTest`
- **Instrumented tests (Emulator)** : `./gradlew connectedDebugAndroidTest`
- **Smoke Command** (build seulement) :
  ```bash
  cd workspace/output/src/{AppName} && ./gradlew clean assembleDebug --no-daemon
  RC=$?; exit $RC
  ```
- **Smoke Timeout** : 120s (Gradle warmup + build resources)
- **Lint** : `./gradlew lint` (AndroidLint natif)
- **Format** : `./gradlew spotlessApply` (Spotless + ktfmt)
- **Type-check** : intégré au compile Kotlin
- **Package manager** : Maven Central via Gradle
- **Test** : voir `qa/kotlin-android-espresso.md` (voir note v7.0.0)

## 2.2.1 Init Commands

```bash
# Idempotent : skip si build.gradle.kts existe déjà

if [ ! -f "workspace/output/src/{AppName}/build.gradle.kts" ]; then
  # Génération via Android Studio template (ou créé manuellement)
  mkdir -p workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}
  mkdir -p workspace/output/src/{AppName}/app/src/main/res/values
  mkdir -p workspace/output/src/{AppName}/app/src/main/res/drawable
  mkdir -p workspace/output/src/{AppName}/app/src/main/res/mipmap
  
  # Créer l'arborescence des couches
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/presentation/screen"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/presentation/component"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/presentation/viewmodel"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/presentation/navigation"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/presentation/theme"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/domain/model"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/domain/repository"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/domain/usecase"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/remote/api"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/remote/interceptor"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/local/dao"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/local/entity"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/local/database"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/local/preferences"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/data/repository"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/di"
  mkdir -p "workspace/output/src/{AppName}/app/src/main/kotlin/{AppNamespace}/util"
  
  # Créer les fichiers build (scaffolding minimal)
  cat > workspace/output/src/{AppName}/build.gradle.kts << 'EOF'
plugins {
    alias(libs.plugins.kotlin.gradle)
    alias(libs.plugins.android.app)
    alias(libs.plugins.android.kotlin)
    alias(libs.plugins.hilt.android)
    alias(libs.plugins.ksp)
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
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    kotlinOptions {
        jvmTarget = "21"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.15"
    }
}

dependencies {
    // Jetpack Compose
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.navigation)
    
    // Hilt DI
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    
    // Retrofit + OkHttp
    implementation(libs.retrofit)
    implementation(libs.retrofit.json)
    implementation(libs.okhttp)
    implementation(libs.okhttp.interceptor)
    
    // Room
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    
    // Coroutines
    implementation(libs.kotlin.coroutines)
    
    // Datastore
    implementation(libs.datastore)
    
    // Timber
    implementation(libs.timber)
    
    // Testing
    testImplementation(libs.junit)
    testImplementation(libs.mockito)
}
EOF
fi

# Créer gradle/libs.versions.toml depuis kotlin-android.libs.json
# (script déterministe auto-généré par arch)

# Build validation
cd workspace/output/src/{AppName} && ./gradlew compileDebugKotlin --no-daemon
```

**Contrat post-init** :
- `build.gradle.kts` existe et `./gradlew compileDebugKotlin` passe
- Arborescence des couches créée
- `AndroidManifest.xml` existe
- Version catalog `gradle/libs.versions.toml` existe

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
# capability: firebase
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.firebase:firebase-bom:33.7.0")
#   implementation("com.google.firebase:firebase-messaging-ktx:33.7.0")

# capability: room-database
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.room:room-ktx:2.6.1")

# capability: camera
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.camera:camera-core:1.4.0")
#   implementation("androidx.camera:camera-camera2:1.4.0")
#   implementation("androidx.camera:camera-lifecycle:1.4.0")

# capability: permissions
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.accompanist:accompanist-permissions:0.36.0")

# capability: background-jobs
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.work:work-runtime-ktx:2.10.0")

# capability: google-maps
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("com.google.maps.android:maps-compose:6.2.1")

# capability: paging
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("androidx.paging:paging-compose:3.3.4")
```
<!-- ONDEMAND_PACKAGES_END -->

### 2.2.2 Plugins Gradle obligatoires (`build.gradle.kts`)

```kotlin
plugins {
    alias(libs.plugins.kotlin.gradle)              // Compilateur Kotlin
    alias(libs.plugins.android.app)                // Android Gradle Plugin (AGP)
    alias(libs.plugins.android.kotlin)             // Kotlin Multiplatform
    alias(libs.plugins.hilt.android)               // Hilt DI
    alias(libs.plugins.ksp)                        // Kotlin Symbol Processing (annoation processors)
    alias(libs.plugins.spotless)                   // Format (ktfmt)
}

android {
    compileSdk = 36
    minSdk = 24
    targetSdk = 36
    kotlinOptions {
        jvmTarget = "21"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.15"
    }
}
```

## 2.3 Patterns d'erreurs compilation

Format AGP/Kotlin : `{path}.kt:{line}:{col}: error: {message}`

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/mobiles/kotlin-android.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-android`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| kotlin-stdlib | 2.3.21 | Stdlib Kotlin core |
| gradle | 8.6.1 | Android Gradle Plugin (compilateur, packaging APK/AAB, resource merging) |
| ui | 1.7.0 | Jetpack Compose UI foundation (Layout, Modifier, State) |
| material3 | 1.3.1 | Material Design 3 components (Button, Card, TextField, Navigation, etc.) |
| runtime | 1.7.0 | Compose runtime (Recomposition, State, Effect) |
| foundation | 1.7.0 | Foundation layouts (Box, Row, Column, LazyColumn, LazyRow, ScrollState) |
| navigation-compose | 1.7.0 | Navigation Compose (NavController, NavGraph, Routes typées) |
| core-ktx | 1.15.0 | Android core APIs extensions (Context, SharedPreferences, etc.) |
| activity-compose | 1.9.0 | Activity integration with Compose (setContent, LocalContext) |
| lifecycle-runtime-ktx | 2.8.0 | Lifecycle-aware coroutines (lifecycleScope, repeatOnLifecycle) |
| lifecycle-viewmodel-ktx | 2.8.0 | ViewModel lifecycle management (viewModelScope) |
| lifecycle-viewmodel-compose | 2.8.0 | ViewModel integration with Compose (hiltViewModel, collectAsStateWithLifecycle) |
| room-runtime | 2.6.1 | Room persistence library (SQLite ORM avec @Entity, @Dao, @Database) |
| room-ktx | 2.6.1 | Room Kotlin extensions (suspend functions, Flow queries) |
| datastore-preferences | 1.1.1 | DataStore async key-value storage (preference moderne, replacement SharedPreferences) |
| hilt-android | 2.51 | Hilt dependency injection (DI scopes, @Inject, @Module, @HiltViewModel) |
| retrofit | 2.11.0 | Retrofit HTTP client (REST API, declarative, interceptors, suspend fun) |
| converter-kotlinx-serialization | 2.11.0 | Retrofit converter Kotlin Serialization (JSON deserialization) |
| okhttp | 4.12.0 | OkHttp HTTP client core (connection pooling, interceptors, request/response logging) |
| logging-interceptor | 4.12.0 | OkHttp logging interceptor (debug HTTP requests/responses) |
| kotlinx-serialization-json | 1.7.0 | Kotlin Serialization JSON parser (alternative Jackson/GSON, Kotlin-native) |
| timber | 5.0.1 | Timber logging library (wrapper SLF4J-like Android, debug tree plugin) |
| kotlinx-coroutines-android | 2.3.21 | Kotlin Coroutines Android support (Dispatchers.Main) |
| kotlinx-coroutines-core | 2.3.21 | Kotlin Coroutines core (Flow, async, launch, withContext) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| firebase | firebase-bom | 33.7.0 | firebase, cloud messaging, notifications push, fcm |
| firebase | firebase-messaging-ktx | 33.7.0 | firebase, cloud messaging, notifications push |
| room-database | room-ktx | 2.6.1 | room, database local, sqlite persistence, dao |
| camera | camera-core | 1.4.0 | camera, photo capture, video record, image picker |
| camera | camera-camera2 | 1.4.0 | camera, photo capture, video record |
| camera | camera-lifecycle | 1.4.0 | camera |
| permissions | accompanist-permissions | 0.36.0 | permissions runtime, permission compose, permission ui |
| background-jobs | work-runtime-ktx | 2.10.0 | background job, scheduled task, periodic work, workmanager |
| google-maps | maps-compose | 6.2.1 | google maps, maps, location map |
| paging | paging-compose | 3.3.4 | paging, pagination, lazy load, infinite scroll |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| com.android.application | 8.6.1 | Android Application plugin (cible apk/aab, resource packaging, manifest merging) |
| kotlin-android | 2.3.21 | Kotlin Android plugin (compilateur Kotlin/JVM, Kotlin sources integration) |
| com.google.dagger.hilt.android | 2.51 | Hilt plugin (code generation DI, @HiltAndroidApp, @HiltViewModel) |
| com.google.devtools.ksp | 2.3.21-1.0.20 | Kotlin Symbol Processing (KSP compiler plugin pour annotation processors: Hilt, Room, etc.) |
| com.diffplug.spotless | 7.0.0 | Spotless formatter (ktfmt Kotlin formatting, tasks spotlessCheck / spotlessApply) |
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
