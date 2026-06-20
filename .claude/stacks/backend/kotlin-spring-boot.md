# Tech FEAT: kotlin-spring-boot (backend)

> §2.4 (Librairies) régénérée depuis `kotlin-spring-boot.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-spring-boot`).

Status: Stable
Validation: 🟢 reference (validated combo CMS — kotlin-spring-boot + react + shadcn + azure-ad, 2026-05-13)
Tech FEAT ID: tech-kotlin-spring-boot
Scope: backend uniquement (REST API, logique métier, persistance)

---

## 1. Architecture

> **Pattern d'architecture** : ce stack suit l'**architecture canonique** définie dans
> `.claude/stacks/archi/{ArchiPattern}.md` (défaut `MVC` si `## Active Architecture Pattern`
> absent du `stack.md`). Section §1 ci-dessous ne décrit QUE les overrides Kotlin/Spring-specific.

### 1.1 Pattern applicatif (Kotlin/Spring idioms)

Pour `ArchiPattern: MVC` (défaut), suit `archi/mvc.md` avec idioms Spring Boot 3.3 LTS + Kotlin 2.0.21 :
- **Data classes Kotlin** pour DTOs (`val` exclusivement → immuables par construction, `equals/hashCode/toString` auto-générés)
- **Constructor injection** native Kotlin (`class UsersService(val repo: UsersRepository, ...)`)
- **Coroutines** pour I/O async (`suspend fun` + Spring WebFlux optionnel) OU pattern bloquant Spring MVC classique
- **`@RestController`** (Spring stereotype) sur controllers, **`@Service`** sur impls, **`@Repository`** auto via `JpaRepository<T, ID>` extension
- **Mapper** : extension functions Kotlin (`fun Entity.toModel(): Model`) pour mappings simples, MapStruct pour mappings complexes
- **`@RestControllerAdvice`** global pour gestion exceptions → ProblemDetails RFC 7807

Pour `ArchiPattern: DDD` → voir `archi/ddd.md` (Aggregates avec méthodes métier, UseCases via Mediator).
Pour `ArchiPattern: microservice` → voir `archi/microservice.md` (Resilience4j + Micrometer + Spring Cloud).

### 1.3 Mapping couche → répertoire (override Kotlin/Spring)

| Couche canonique (archi/mvc.md §3) | Path Kotlin/Spring-specific |
|---|---|
| Application entry | `src/main/kotlin/{BackendNamespace}/{BackendName}Application.kt` (`@SpringBootApplication`) |
| Controller | `src/main/kotlin/{BackendNamespace}/controller/` |
| Service interface | `src/main/kotlin/{BackendNamespace}/service/` (Kotlin `interface` co-localisée — pas de package `interfaces/` séparé idiomatique) |
| Service impl | `src/main/kotlin/{BackendNamespace}/service/` (même package, classe `@Service`) |
| Repository | `src/main/kotlin/{BackendNamespace}/repository/` (interface `: JpaRepository<T, ID>`) |
| Entity | `src/main/kotlin/{BackendNamespace}/entity/` (`@Entity` JPA) |
| Mapper | `src/main/kotlin/{BackendNamespace}/mapper/` (extension fn ou MapStruct) |
| Input DTO | `src/main/kotlin/{BackendNamespace}/dto/input/` (data classes) |
| Output DTO | `src/main/kotlin/{BackendNamespace}/dto/output/` |
| Model DTO | `src/main/kotlin/{BackendNamespace}/dto/model/` |
| Config | `src/main/kotlin/{BackendNamespace}/config/` (`@Configuration`) |
| Exception classes | `src/main/kotlin/{BackendNamespace}/exception/` |
| GlobalExceptionAdvice | `src/main/kotlin/{BackendNamespace}/advice/` (`@RestControllerAdvice`) |
| Security | `src/main/kotlin/{BackendNamespace}/security/` |
| Application config | `src/main/resources/application.yml` + `application-{profile}.yml` |
| i18n | `src/main/resources/messages/` |
| Migrations Flyway | `src/main/resources/db/migration/` |
| Gradle build | `build.gradle.kts` + `settings.gradle.kts` |

> **Note** : ce stack utilise un mono-projet `{BackendName}/` (pas de `{LibName}` séparé — les DTOs vivent dans `dto/` interne car Kotlin n'a pas de pattern monorepo standard à la Node `pnpm workspaces`).

### 1.4 Override principes (Kotlin-specific)

Hérités de `archi/mvc.md §4`. **Ajouts** Kotlin :
- **Data classes** pour DTOs (`val`, immuables, `equals/hashCode/toString` auto)
- **Constructor injection** uniquement (Kotlin natif via `class A(val x: X)`) — jamais `@Autowired` field
- **Lombok interdit** (Kotlin a déjà l'équivalent natif `data class`, `lateinit`, …)
- **`!!` (force unwrap) interdit** sauf justification écrite — utiliser `?:`, `let`, `requireNotNull`
- **Coroutines** pour I/O async (Spring WebFlux ou `@Async` + `CompletableFuture` selon contexte)
- **Migrations DB via Flyway** (pas de `ddl-auto: create` en prod — Database-First)
- **Logging via SLF4J** : `private val log = LoggerFactory.getLogger(javaClass)` ou `KotlinLogging.logger {}`

---

## 2. Stack

### 2.1 Identité

- **Stack ID** : `back-kotlin-spring`
- **Langage** : Kotlin 2.0.21 (LTS-aligned via Java 21)
- **Runtime** : JDK 21 LTS
- **Framework principal** : Spring Boot 3.3.x LTS (canonique SDD_Pro v7.0.0 — Spring Boot 4 sera évalué en roadmap v8 après stabilisation Spring Security 7)
- **Build tool** : **Gradle 8.10** avec **Kotlin DSL** (`build.gradle.kts`)
- **Package racine** : `{BackendNamespace}` (ex. `com.softwe3.sim`)

### 2.2 Outils

- **Project file** : `workspace/output/src/{BackendName}/build.gradle.kts`
- **Build** : `cd workspace/output/src/{BackendName} && ./gradlew build -x test`
- **Smoke Command** :
  ```bash
  cd workspace/output/src/{BackendName} && ./gradlew bootRun --args='--spring.profiles.active=dev' &
  APP_PID=$!; sleep 30
  curl -sf http://localhost:8080/actuator/health -o /dev/null
  RC=$?; kill $APP_PID 2>/dev/null; wait $APP_PID 2>/dev/null; exit $RC
  ```
- **Smoke Timeout** : 90s (Spring Boot startup + Gradle warmup)
- **Lint / Format** : `./gradlew ktlintCheck` (plugin ktlint) OU
  `./gradlew detekt` (analyse statique)
- **Type-check** : intégré au compile Kotlin
- **Package manager** : Maven Central via Gradle
- **Test** : voir `qa/kotlin-junit.md`

### 2.2.1 Init Commands

```bash
# Idempotent : skip si build.gradle.kts existe déjà

if [ ! -f "workspace/output/src/{BackendName}/build.gradle.kts" ]; then
  # Génération via Spring Initializr Kotlin
  curl -s https://start.spring.io/starter.zip \
    -d type=gradle-project-kotlin \
    -d language=kotlin \
    -d bootVersion=4.0.6 \
    -d baseDir={BackendName} \
    -d groupId={BackendNamespace} \
    -d artifactId={BackendName} \
    -d name={BackendName} \
    -d packageName={BackendNamespace} \
    -d packaging=jar \
    -d javaVersion=21 \
    -d dependencies=web,data-jpa,validation,actuator,security,oauth2-resource-server,flyway-core \
    -o workspace/output/src/{BackendName}.zip

  unzip -q workspace/output/src/{BackendName}.zip -d workspace/output/src/
  rm -f workspace/output/src/{BackendName}.zip
fi

# Créer arborescence des couches
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/controller
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/service
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/repository
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/entity
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/dto/input
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/dto/output
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/dto/model
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/mapper
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/config
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/exception
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/advice
mkdir -p workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/security
mkdir -p workspace/output/src/{BackendName}/src/main/resources/db/migration
mkdir -p workspace/output/src/{BackendName}/src/main/resources/messages

# Build de validation
cd workspace/output/src/{BackendName} && ./gradlew compileKotlin --no-daemon
```

**Contrat post-init** :
- `build.gradle.kts` existe et `./gradlew compileKotlin` passe
- Arborescence des couches créée
- `application.yml` et `application-dev.yml` existent

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis kotlin-spring-boot.libs.json -- ne pas editer (utiliser sync_stack_md.py).
# Gradle managed via build.gradle.kts + gradle/libs.versions.toml.
# Versions auto-derivees de kotlin-spring-boot.libs.json -- regenerer le catalog Gradle
# en cas de bump (cf. gradle/libs.versions.toml).
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis kotlin-spring-boot.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: redis-cache
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("org.springframework.boot:spring-boot-starter-data-redis:")

# capability: sqlserver-flyway
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("org.flywaydb:flyway-sqlserver:10.21.0")
```
<!-- ONDEMAND_PACKAGES_END -->

### 2.2.2 Plugins Gradle obligatoires (`build.gradle.kts`)

```kotlin
plugins {
    id("org.springframework.boot") version "4.0.6"
    id("io.spring.dependency-management") version "1.1.7"
    kotlin("jvm") version "2.3.21"
    kotlin("plugin.spring") version "2.3.21"
    kotlin("plugin.jpa") version "2.3.21"      // no-arg pour @Entity
    id("org.jlleitschuh.gradle.ktlint") version "12.1.1"
    id("io.gitlab.arturbosch.detekt") version "1.23.7"
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

kotlin {
    compilerOptions {
        freeCompilerArgs.addAll("-Xjsr305=strict")
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_21)
    }
}
```

### 2.3 Patterns d'erreurs compilation

Format Gradle/Kotlin : `e: file:///{path}.kt:{line}:{col} {message}`

Codes prioritaires Kotlin :
- `Unresolved reference: ...`
- `Type mismatch: inferred type is ... but ... was expected`
- `Cannot infer type for this parameter`
- `Property must be initialized or be abstract`
- `Null can not be a value of a non-null type`

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/backend/kotlin-spring-boot.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-spring-boot`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| spring-boot-starter-web |  | Web layer (Spring MVC, controllers REST, Jackson JSON) |
| spring-boot-starter-webflux |  | WebClient reactif (clients HTTP sortants vers APIs tierces) |
| spring-boot-starter-actuator |  | Endpoints health/info/metrics (monitoring + readiness probe) |
| spring-boot-starter-security |  | Spring Security core (filtre HTTP, CSRF, password encoder) |
| spring-boot-starter-oauth2-resource-server |  | JWT Bearer validation (Azure AD / OIDC issuers) |
| spring-boot-starter-oauth2-client |  | OAuth2 client flow (utilise par certains scenarios M2M) |
| spring-boot-starter-data-jpa |  | ORM Hibernate + Spring Data repositories (PagingAndSortingRepository, JpaRepository) |
| spring-boot-starter-validation |  | Bean Validation Jakarta (@Valid, @NotBlank, @Email) sur DTOs entrants |
| flyway-core | 10.21.0 | Moteur migrations versionnees V{n}__*.sql + autoconfig Spring (pas de starter dedie). Pin 10.21.0 (compat Spring Boot 3.3.x BOM, Flyway 10 externalise les dialects DB en modules separes). Cf. kotlin-spring-boot.md §4.4 |
| flyway-database-postgresql | 10.21.0 | Module support PostgreSQL Flyway 10+ (externalise depuis flyway-core en 10.x, n'existe PAS en branche 9.x — d'ou la bump). Necessaire si DatabaseType=postgres |
| springdoc-openapi-starter-webmvc-ui | 2.7.0 | OpenAPI 3 + Swagger UI auto-generes depuis controllers (path /swagger custom, cf. §5.6) |
| spring-context |  | DI core (transitive via web, listee explicitement pour clarte) |
| jackson-module-kotlin |  | Serialization Kotlin data classes (sans no-arg constructor) |
| kotlin-reflect | 2.3.21 | Reflection runtime requise par Jackson/Spring (DI Kotlin idiomatique) |
| nimbus-jose-jwt | 9.40 | JWT decoder + JWKS resolver (utilise par JwtDecoder custom Azure AD, cf. auth/azure-ad.md §5.1 Piege 7) |
| spring-boot-starter-test |  | Test scaffolding (JUnit 5 + AssertJ + Mockito + Spring TestContext) |
| spring-boot-starter-webmvc-test |  | MockMvc + @WebMvcTest pour tests controllers slices (utilise par QA API Gate, cf. backend-first.md) |
| spring-security-test |  | @WithMockUser, SecurityMockMvcRequestPostProcessors (auth mockee dans tests) |
| kotest-runner-junit5 | 5.9.1 | Runner Kotest sur JUnit Platform (style DescribeSpec/StringSpec) |
| kotest-assertions-core | 5.9.1 | DSL d'assertions Kotest (`shouldBe`, `shouldThrow`, soft assertions) |
| kotest-extensions-spring | 1.3.0 | Bridge Kotest <-> Spring TestContext (@SpringBootTest dans specs Kotest) |
| mockwebserver | 4.12.0 | Mock HTTP server pour tester les WebClient outgoing (alternatif a WireMock) |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| redis-cache | spring-boot-starter-data-redis |  | redis, cache distribu, distributed cache, session partag |
| sqlserver-flyway | flyway-sqlserver | 10.21.0 | sqlserver, mssql |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| org.jetbrains.kotlin.jvm | 2.3.21 | Compilateur Kotlin/JVM (cible JDK 21) |
| org.jetbrains.kotlin.plugin.spring | 2.3.21 | Genere all-open pour @Component/@Service/@Configuration (Spring proxies) |
| org.jetbrains.kotlin.plugin.jpa | 2.3.21 | Genere no-arg constructor pour @Entity (exigence Hibernate) |
| org.springframework.boot | 4.0.6 | Gere bootRun, bootJar, dependency-management BOM |
| org.jlleitschuh.gradle.ktlint | 14.2.0 | Lint + auto-format Kotlin (tasks ktlintCheck / ktlintFormat) |
| org.flywaydb.flyway | 10.21.0 | Tasks Gradle flywayMigrate / flywayInfo / flywayClean (CLI hors runtime) |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| postgres | `org.postgresql:postgresql` | 42.7.10 | runtime |
| sqlserver | `com.microsoft.sqlserver:mssql-jdbc` | 12.8.1.jre11 | runtime |
<!-- LIBS_CATALOG_END -->

### 2.5 Conventions de nommage

- **Classes / interfaces** : `PascalCase`
- **Fonctions / variables** : `camelCase`
- **Constantes top-level** : `SCREAMING_SNAKE_CASE`
- **Packages** : `lowercase.dotted`
- **Data class properties** : `camelCase`
- **Tests** : `@Test fun \`describe scenario expected\`()` (backticks
  pour lisibilité)

### 2.6 Conventions REST API (load-bearing — anti-divergence cross-US)

> **Pourquoi cette section** : sans contrat URL explicite, deux US qui
> exposent la même ressource (`POST /eans` US 4-2 vs `POST /ean/bulk`
> US 4-3) divergent silencieusement → 404 runtime côté frontend, build
> vert, bug visible seulement à l'usage. Cette règle est **load-bearing**
> et s'applique à `dev-backend`, `dev-frontend` et `qa` (API gate).

#### 2.6.1 Ressources au pluriel, jamais singulier
- ✅ `/api/v1/campagnes`, `/api/v1/eans`, `/api/v1/annonceurs`, `/api/v1/marques`, `/api/v1/users`
- ❌ `/api/v1/campagne`, `/api/v1/ean`, `/api/v1/user`
- Exception unique : ressource singleton (`/api/v1/me` pour l'utilisateur courant authentifié) — à tracer dans un ADR explicite

#### 2.6.2 Verbes HTTP sémantiques, jamais RPC dans l'URL
- ✅ `GET /api/v1/campagnes/{id}`, `POST /api/v1/campagnes`, `DELETE /api/v1/campagnes/{id}`
- ❌ `GET /api/v1/getCampagne/{id}`, `POST /api/v1/createCampagne`, `POST /api/v1/CampagneDelete`
- Pas de verbe dans le path : c'est le verbe HTTP qui porte l'action
- Tolérance pragmatique pour les sous-actions non-CRUD : `POST /api/v1/eans/bulk` (import batch), `GET /api/v1/eans/template` (download asset), `POST /api/v1/orders/{id}/confirm` (transition d'état). Ces patterns sont acceptés s'ils sont **rares** et **documentés** dans la FEAT (BR ou FD).

#### 2.6.3 Préfixe versionné `/api/v{N}/` systématique
- Tous les endpoints applicatifs sous `/api/v1/` (incrémenter à v2 si breaking change)
- Exceptions tolérées (hors `/api/v{N}/`) : `/actuator/**` (Spring), `/swagger`, `/openapi`, `/health`. Toute autre exception → ADR.

#### 2.6.4 Composition de ressources (nesting)
- Quand B appartient à A → `/api/v1/{a-plural}/{aId}/{b-plural}` :
  - `/api/v1/campagnes/{campagneId}/eans` (EAN appartient à une campagne)
  - `/api/v1/users/{userId}/permissions`
- **Cohérence stricte** : le même couple parent/enfant utilise toujours le même pluriel — toute US qui ajoute un endpoint sous cette racine **doit conserver le pluriel exact**.

#### 2.6.5 Status codes par verbe
| Verbe | Succès | Headers obligatoires |
|---|---|---|
| `GET` (liste) | `200` | `Content-Type: application/json` |
| `GET` (item) | `200` ou `404` | — |
| `POST` (create) | **`201`** | **`Location: /api/v1/{ressource}/{id-créé}`** |
| `POST` (action) | `200` ou `201` | — |
| `PUT` (replace) | `200` ou `204` | — |
| `PATCH` (partial) | `200` ou `204` | — |
| `DELETE` | **`204`** (pas de body) | — |
| Erreur client | `400` / `401` / `403` / `404` / `409` / `422` | `Content-Type: application/problem+json` (`ProblemDetail` RFC 7807) |
| Erreur serveur | `500` | idem ProblemDetail |

#### 2.6.6 Snake-case interdit, kebab-case toléré, camelCase interdit dans le path
- ✅ `/api/v1/campagnes`, `/api/v1/order-items`
- ❌ `/api/v1/campagne_list`, `/api/v1/orderItems`
- Pour la longue chaîne de mots : préférer pluriel simple (`/orders`) plutôt que kebab. Kebab uniquement si nécessaire.

#### 2.6.7 Format ERROR sur violation détectée

Pendant la planification ou l'exécution, si un agent dev-* détecte un
chemin qui viole §2.6.1 ou §2.6.4 (singulier vs pluriel incohérent
avec une US précédente) :

```
ERROR: dev-{backend|frontend} {n}-{m} — violation contrat REST
CAUSE: [REST_CONTRACT_VIOLATION] endpoint {verbe} {path} diverge du
       pluriel {/eans} défini par US {n-m'} sibling OU FEAT BR-X
FIX: aligner le path sur {/eans} (cf. stack §2.6.1) OU réviser la FEAT
     si le contrat URL est ambigu
```

`[REST_CONTRACT_VIOLATION]` est non-itérable par `build_loop` → fail-fast,
le Tech Lead corrige le plan/la FEAT manuellement.

#### 2.6.8 Procédure de planification (dev-backend STEP 5)

Avant d'écrire `@RequestMapping(...)` ou `MapGet/MapPost(...)`, l'agent
dev-backend doit :
1. Grep `workspace/output/src/{BackendName}/...` pour repérer les
   endpoints **déjà existants** sur la même racine de ressource
2. Si trouvé → réutiliser **strictement** le même pluriel et la même
   structure de nesting
3. Sinon → suivre §2.6.1 (pluriel) + §2.6.4 (nesting)
4. Si la FEAT parente définit explicitement le contrat URL (BR ou FD)
   → la FEAT **fait foi**, même si elle utilise une convention atypique

Cette procédure est **inlinée dans l'agent dev-backend** ; le présent
§2.6 est la source canonique.

---

## 3. Conventions d'usage (lib clé)

### 3.1 Repository

```kotlin
package {BackendNamespace}.repository

import {BackendNamespace}.entity.User
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.stereotype.Repository

@Repository
interface UserRepository : JpaRepository<User, Long> {
    fun findByEmail(email: String): User?

    @Query("SELECT u FROM User u WHERE u.active = true AND u.role = :role")
    fun findActiveByRole(role: String): List<User>
}
```

### 3.2 Service + DI Kotlin idiomatique

```kotlin
package {BackendNamespace}.service

import {BackendNamespace}.dto.output.UserOutputDto
import {BackendNamespace}.entity.User
import {BackendNamespace}.exception.ResourceNotFoundException
import {BackendNamespace}.mapper.toOutputDto
import {BackendNamespace}.repository.UserRepository
import io.github.oshai.kotlinlogging.KotlinLogging
import org.springframework.stereotype.Service

interface UserService {
    fun findById(id: Long): UserOutputDto
}

@Service
class UserServiceImpl(
    private val userRepository: UserRepository
) : UserService {
    private val log = KotlinLogging.logger {}

    override fun findById(id: Long): UserOutputDto {
        log.debug { "Looking up user $id" }
        return userRepository.findById(id)
            .orElseThrow { ResourceNotFoundException("User $id") }
            .toOutputDto()
    }
}
```

### 3.3 Mapping via extension functions Kotlin

```kotlin
package {BackendNamespace}.mapper

import {BackendNamespace}.dto.input.UserInputDto
import {BackendNamespace}.dto.output.UserOutputDto
import {BackendNamespace}.entity.User

fun User.toOutputDto() = UserOutputDto(
    id = id,
    email = email,
    role = role,
    active = active
)

fun UserInputDto.toEntity() = User(
    email = email,
    passwordHash = passwordHash,
    role = role,
    active = true
)
```

Plus idiomatique que MapStruct pour les cas simples.

### 3.4 DTO comme data class immuable

```kotlin
package {BackendNamespace}.dto.input

import jakarta.validation.constraints.Email
import jakarta.validation.constraints.NotBlank

data class UserInputDto(
    @field:Email val email: String,
    @field:NotBlank val passwordHash: String,
    @field:NotBlank val role: String
)
```

```kotlin
package {BackendNamespace}.dto.output

import java.time.Instant

data class UserOutputDto(
    val id: Long,
    val email: String,
    val role: String,
    val active: Boolean,
    val createdAt: Instant? = null
)
```

### 3.5 Controller Kotlin

```kotlin
package {BackendNamespace}.controller

import {BackendNamespace}.dto.input.UserInputDto
import {BackendNamespace}.dto.output.UserOutputDto
import {BackendNamespace}.service.UserService
import jakarta.validation.Valid
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

@RestController
@RequestMapping("/api/v1/users")  // §2.6.1 pluriel obligatoire, §2.6.3 préfixe /api/v1/
class UserController(
    private val userService: UserService
) {
    @GetMapping("/{id}")
    fun findById(@PathVariable id: Long): ResponseEntity<UserOutputDto> =
        ResponseEntity.ok(userService.findById(id))

    @PostMapping  // §2.6.5 POST create → 201 + Location obligatoires
    fun create(@Valid @RequestBody input: UserInputDto): ResponseEntity<UserOutputDto> {
        val created = userService.create(input)
        val location = URI.create("/api/v1/users/${created.id}")
        return ResponseEntity.created(location).body(created)
    }

    @DeleteMapping("/{id}")  // §2.6.5 DELETE → 204 No Content
    fun delete(@PathVariable id: Long): ResponseEntity<Void> {
        userService.delete(id)
        return ResponseEntity.noContent().build()
    }
}
```

### 3.6 Exception handler global

```kotlin
package {BackendNamespace}.advice

import {BackendNamespace}.exception.ResourceNotFoundException
import org.springframework.http.HttpStatus
import org.springframework.http.ProblemDetail
import org.springframework.web.bind.MethodArgumentNotValidException
import org.springframework.web.bind.annotation.ExceptionHandler
import org.springframework.web.bind.annotation.RestControllerAdvice

@RestControllerAdvice
class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException::class)
    fun handleNotFound(ex: ResourceNotFoundException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.message ?: "Not found").apply {
            title = "Resource not found"
        }

    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidation(ex: MethodArgumentNotValidException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, "Validation failed").apply {
            title = "Validation error"
            setProperty("errors", ex.bindingResult.fieldErrors.map {
                mapOf("field" to it.field, "message" to (it.defaultMessage ?: ""))
            })
        }
}
```

### 3.7 Coroutines (Spring WebFlux ou async)

```kotlin
@Service
class ExternalApiService(
    private val webClient: WebClient
) {
    suspend fun fetchExternal(id: Long): String =
        webClient.get()
            .uri("/external/$id")
            .retrieve()
            .awaitBody()
}
```

---

## 4. Persistence (cross-DatabaseType)

### 4.1 DB Drivers (mêmes que Java Spring Boot)

| DatabaseType | Coordinate Gradle | Version |
|---|---|---|
| `PostgreSQL` | `org.postgresql:postgresql` | 42.7.4 |
| `MySql` | `com.mysql:mysql-connector-j` | 9.1.0 |
| `SqlServer` | `com.microsoft.sqlserver:mssql-jdbc` | 12.8.1.jre11 |
| `Oracle` | `com.oracle.database.jdbc:ojdbc11` | 23.6.0.24.10 |
| `H2` (test) | `com.h2database:h2` | 2.3.232 |

### 4.2 Connection string (`application.yml` peuplé par arch, depuis 2026-05-14)

**Source de vérité** : bloc `## Active Database` de
`workspace/input/stack/stack.md` (clés `DatabaseType`, `DB_HOST`,
`DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`). L'agent `arch` Phase
A — STEP 4.5 lit ces valeurs et écrit `application.yml` avec les
**valeurs littérales** (plus d'interpolation `${DB_*}` env vars).

Exemple `application.yml` généré par arch pour `DatabaseType: postgres` :

```yaml
spring:
  datasource:
    url: jdbc:postgresql://127.0.0.1:5432/CMSPrint    # valeurs littérales depuis ## Active Database
    username: postgres
    password: cmsprint.
    driver-class-name: org.postgresql.Driver
  jpa:
    hibernate:
      ddl-auto: none           # Flyway gère les migrations (cf. §4.4)
    show-sql: false
    open-in-view: false
    properties:
      hibernate:
        dialect: org.hibernate.dialect.PostgreSQLDialect
```

**Mapping `DatabaseType` → URL + dialect** (appliqué par arch) :

| DatabaseType (## Active Database) | URL pattern                                      | driver-class-name                | dialect Hibernate                                  |
|-----------------------------------|--------------------------------------------------|----------------------------------|----------------------------------------------------|
| `postgres` / `postgresql`         | `jdbc:postgresql://{DB_HOST}:{DB_PORT}/{DB_NAME}` | `org.postgresql.Driver`          | `org.hibernate.dialect.PostgreSQLDialect`         |
| `mysql`                           | `jdbc:mysql://{DB_HOST}:{DB_PORT}/{DB_NAME}`     | `com.mysql.cj.jdbc.Driver`       | `org.hibernate.dialect.MySQLDialect`              |
| `sqlserver`                       | `jdbc:sqlserver://{DB_HOST}:{DB_PORT};databaseName={DB_NAME};encrypt=true;trustServerCertificate=false` | `com.microsoft.sqlserver.jdbc.SQLServerDriver` | `org.hibernate.dialect.SQLServerDialect` |
| `oracle`                          | `jdbc:oracle:thin:@{DB_HOST}:{DB_PORT}:{DB_NAME}` | `oracle.jdbc.OracleDriver`       | `org.hibernate.dialect.OracleDialect`             |
| `h2`                              | `jdbc:h2:mem:{DB_NAME};MODE=PostgreSQL`          | `org.h2.Driver`                  | `org.hibernate.dialect.H2Dialect`                 |

**Code applicatif** : ne lit JAMAIS `System.getenv("DB_*")` ni
`@Value("${DB_*}")`. Spring Boot bind automatiquement `spring.datasource.*`
au `DataSource` via auto-configuration — aucun bean custom requis.

### 4.3 Entity Kotlin avec JPA

```kotlin
package {BackendNamespace}.entity

import jakarta.persistence.*
import java.time.Instant

@Entity
@Table(name = "users")
class User(
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long = 0,

    @Column(unique = true, nullable = false)
    var email: String,

    @Column(name = "password_hash", nullable = false)
    var passwordHash: String,

    @Column(nullable = false)
    var role: String,

    @Column(nullable = false)
    var active: Boolean = true,

    @Column(name = "created_at", nullable = false, updatable = false)
    val createdAt: Instant = Instant.now()
)
```

> **Note** : avec `kotlin("plugin.jpa")`, le compilateur génère
> automatiquement le constructeur sans argument requis par JPA.

### 4.4 Migrations Flyway

Toutes les évolutions de schéma passent par des migrations versionnées
sous `src/main/resources/db/migration/` :

```
src/main/resources/db/migration/
├── V1__init_schema.sql
├── V2__add_users_table.sql
└── V3__add_email_index.sql
```

**Convention de nommage** : `V{n}__{description_snake_case}.sql`
(double underscore, numéros monotones). Une migration ne se réécrit
jamais ; corriger via une nouvelle migration `V{n+1}__fix_*.sql`.

**Configuration** (`application.yml`) :
```yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
    baseline-on-migrate: true   # tolère une DB existante (Database-First)
```

**En Database-First (SDD_Pro)** : la Phase B `arch` introspecte la DB
existante en READ-ONLY et scaffolde les entities. Les migrations
Flyway servent uniquement aux évolutions futures pilotées par les US.

#### 4.4.1 Flyway 11+ et SQL Server (post-mortem 2026-05-08)

**Bug** : depuis Flyway 10+, le support SQL Server (Oracle, DB2,
Sybase ASE) est **externalisé** dans des modules payants/séparés
(édition Community/Teams). `flyway-core` seul échoue avec :
```
FlywayException: Unsupported Database: Microsoft SQL Server 16.0
```

**Pattern obligatoire** quand `DatabaseType: SqlServer` est actif :

1. Ajouter `org.flywaydb:flyway-sqlserver` (même version que `flyway-core`) en `runtimeOnly` :
   ```kotlin
   runtimeOnly("org.flywaydb:flyway-sqlserver:${flywayVersion}")
   ```
2. OU si pas de migrations applicatives prévues, **désactiver Flyway** dans `application.yml` :
   ```yaml
   spring:
     flyway:
       enabled: false
   ```

L'agent `arch` choisit selon le contenu de `src/main/resources/db/migration/` :
- Dossier non vide → ajouter `flyway-sqlserver` (capabilité on-demand `sqlserver-flyway` du catalogue libs.json).
- Dossier vide → `spring.flyway.enabled: false` dans `application.yml` généré.

**Symptôme si oublié** : startup échoue après connexion DB, `BeanCreationException flywayInitializer`. Build vert, runtime cassé.

#### 4.4.2 `ddl-auto: validate` vs scaffolding skipped (post-mortem 2026-05-08)

Si la Phase B DB scaffolding d'`arch` est skippée (DB inaccessible au
moment du bootstrap), les entités JPA générées **ne correspondent pas
à un schéma vérifiable**. Spring Boot avec `spring.jpa.hibernate.ddl-auto: validate`
lève alors `SchemaManagementException: missing table [...]`.

**Pattern obligatoire** dans `application.yml` :
```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: none   # safe default ; mettre validate uniquement si arch a réellement scaffoldé contre la DB cible
```

`arch` documente dans `CLAUDE.md` du projet si Phase B a tourné ou
été skippée. Si skippée → `ddl-auto: none` obligatoire.

### 4.5 Scaffolding tool (Database-First, lu par arch §11)

**Outil** : `hibernate-tools` (reverse-engineering JPA depuis le schéma
DB existant) via tâche Gradle dédiée. Alternative : `jOOQ codegen`
(préféré si requêtes typed-SQL). Pour SDD_Pro v6 : option simple +
maintenue → `hibernate-tools`.

**Pattern d'invocation** (idempotent, READ-ONLY sur la base) :

```kotlin
// build.gradle.kts (tâche scaffold dédiée, exécutée par arch hors prod)
// IMPORTANT depuis 2026-05-14 : arch passe les valeurs DB en propriétés
// Gradle (-PdbHost=... -PdbPort=... etc.) issues du bloc ## Active Database
// de stack.md, JAMAIS via System.getenv (les env vars ne sont plus utilisées).
tasks.register("dbScaffold") {
    group = "sdd-pro"
    description = "Reverse-engineer DB schema -> Kotlin JPA entities (READ-ONLY)"
    doLast {
        val dbHost = project.findProperty("dbHost") as? String ?: error("dbHost missing (passé par arch via -PdbHost=...)")
        val dbPort = project.findProperty("dbPort") as? String ?: error("dbPort missing")
        val dbName = project.findProperty("dbName") as? String ?: error("dbName missing")
        val dbUser = project.findProperty("dbUser") as? String ?: error("dbUser missing")
        val dbPass = project.findProperty("dbPass") as? String ?: error("dbPass missing")
        val dbUrl  = "jdbc:postgresql://$dbHost:$dbPort/$dbName"

        // hibernate-tools task (configurée dans buildscript classpath)
        ant.withGroovyBuilder {
            "taskdef"(
                "name"      to "hbm2java",
                "classname" to "org.hibernate.tool.ant.HibernateToolTask",
                "classpath" to configurations["hibernateTools"].asPath
            )
            "hbm2java"(
                "destdir" to "src/main/kotlin",
                "ejb3"    to "true"
            ) {
                "jdbcconfiguration"(
                    "configurationfile" to "$buildDir/hibernate-revtool.cfg.xml",
                    "packagename"       to "{BackendNamespace}.entity",
                    "detectmanytomany"  to "true"
                )
            }
        }
    }
}
```

**Output** : `workspace/output/src/{BackendName}/src/main/kotlin/{BackendNamespace}/entity/*.kt`
(une data class JPA par table).

**Idempotence** : la tâche écrase les fichiers existants. arch détecte
les tables nouvelles vs déjà scaffoldées via `schema.json` (cf. `arch.md
§9-§10`) et n'invoque la tâche que pour les tables manquantes via
`-PtablesToScaffold=Users,Orders,...`.

**Filtres** (cf. arch.md §11.1 `## DB Scaffolding`) : passer
`-PincludeTables` ou `-PexcludeTables` à la tâche Gradle.

**Alternative simplifiée (recommandée si pas de besoin Hibernate avancé)** :
introspection PowerShell directe via `INFORMATION_SCHEMA` (côté arch
script) puis génération Kotlin via template Mustache. Plus rapide et
moins de dépendances. À choisir via ADR au moment du bootstrap projet.

---

## 5. URLs / CORS / Multilingue / Logging / OpenAPI

### 5.1 URLs et versioning

Toutes les ressources REST sont préfixées `/api/v1/` et au pluriel :
`/api/v1/users`, `/api/v1/orders`, `/api/v1/products`. Exceptions :
`/actuator/**`, `/swagger`, `/openapi` (cf. §5.6).

```kotlin
@RestController
@RequestMapping("/api/v1/users")
class UsersController(private val service: UserService) {
    @GetMapping
    fun list(@PageableDefault pageable: Pageable): Page<UserOutput> = ...

    @PostMapping
    fun create(@Valid @RequestBody input: CreateUserInput): ResponseEntity<UserOutput> =
        ResponseEntity.created(URI.create("/api/v1/users/${created.id}")).body(created)
}
```

- `POST` create → `201 Created` + header `Location`
- `DELETE` → `204 No Content`
- Erreurs → `ProblemDetail` RFC 7807 (`application/problem+json`)
  via `@RestControllerAdvice` global

### 5.2 CORS

Cross-Origin obligatoire dès que `{AppName}` (SPA front) et
`{BackendName}` tournent sur des origins distincts. Configurer via
un bean dédié (jamais via `@CrossOrigin` sur les controllers — cf.
`source-first.md` post-mortem CMS-Back 2026-05-11).

```kotlin
@Configuration
class CorsConfig {
    @Bean
    fun corsConfigurationSource(
        @Value("\${app.cors.allowed-origins}") origins: String
    ): CorsConfigurationSource {
        val config = CorsConfiguration().apply {
            allowedOrigins = origins.split(",").map { it.trim() }
            allowedMethods = listOf("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            allowedHeaders = listOf("*")
            exposedHeaders = listOf("Location")
            allowCredentials = true
            maxAge = 3600
        }
        return UrlBasedCorsConfigurationSource().apply {
            registerCorsConfiguration("/**", config)
        }
    }
}
```

```yaml
app:
  cors:
    allowed-origins: ${CORS_ORIGINS}   # ex. https://localhost:5185
```

Activer dans `SecurityConfig` via `http.cors { }`.

### 5.3 Multilingue (i18n)

Messages d'erreur et libellés métier traduits via
`MessageSource` Spring + bundles `src/main/resources/i18n/messages_{fr,en}.properties`.

```kotlin
@Configuration
class I18nConfig : WebMvcConfigurer {
    @Bean
    fun messageSource() = ReloadableResourceBundleMessageSource().apply {
        setBasename("classpath:i18n/messages")
        setDefaultEncoding("UTF-8")
        setUseCodeAsDefaultMessage(true)
    }

    @Bean
    fun localeResolver() = AcceptHeaderLocaleResolver().apply {
        setDefaultLocale(Locale.FRENCH)
        supportedLocales = listOf(Locale.FRENCH, Locale.ENGLISH)
    }
}
```

Locale résolue depuis le header `Accept-Language` envoyé par le
frontend. Pas de stockage session-side de la locale (stateless).

### 5.4 Logging

**`KotlinLogging`** (Slf4j sous le capot) — pas `@Slf4j` Lombok,
pas `LoggerFactory.getLogger(...)` verbeux :

```kotlin
private val log = KotlinLogging.logger {}

// usage
log.info { "User $userId logged in" }
log.error(ex) { "Failed to persist order $orderId" }
```

**Format JSON structuré** en prod (`logback-spring.xml` avec
`logstash-logback-encoder`). Niveaux : `root: INFO`, namespace projet
`DEBUG` en dev, `INFO` en prod.

**Interdits** : `println`, `print`, `System.out`, `System.err`,
`e.printStackTrace()`. Toujours passer par `log.{level} { ... }`.

### 5.5 Gestion d'erreurs globale

```kotlin
@RestControllerAdvice
class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidation(ex: MethodArgumentNotValidException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(BAD_REQUEST, "Validation failed").apply {
            setProperty("errors", ex.bindingResult.fieldErrors.map {
                mapOf("field" to it.field, "message" to it.defaultMessage)
            })
        }

    @ExceptionHandler(EntityNotFoundException::class)
    fun handleNotFound(ex: EntityNotFoundException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(NOT_FOUND, ex.message ?: "Resource not found")
}
```

Tous les contrôleurs renvoient `ProblemDetail` (RFC 7807) — pas de
DTO d'erreur custom.

### 5.6 OpenAPI / Swagger UI (post-mortem 2026-05-08)

**Lib obligatoire CORE** : `org.springdoc:springdoc-openapi-starter-webmvc-ui`
**version minimum 2.7.0** (la 2.6.0 a un bug d'interaction avec Spring
Security 6.4 qui sécurise par défaut le path standard `/v3/api-docs`,
même sous `web.ignoring()`).

**Pattern obligatoire** dans `application.yml` quand Spring Security
est actif (auth/azure-ad ou autre) — utiliser des paths custom pour
contourner le bug springdoc 2.6 et faciliter la whitelist Security :

```yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /swagger
    url: /openapi
```

**Whitelist sécurité obligatoire** : voir `auth/azure-ad.md §5.1
Piège 6` (WebSecurityCustomizer.ignoring sur `/swagger`, `/swagger/**`,
`/openapi`, `/openapi/**`). Le path custom + `WebSecurityCustomizer`
sont indispensables ensemble — utiliser `requestMatchers().permitAll()`
seul ne suffit pas si un `@RestControllerAdvice` global capture
`AuthenticationException`.

**Symptôme si oublié** : `/v3/api-docs` retourne `401 Unauthorized`
avec body vide, alors que `/v3/api-docs/swagger-config` retourne 200.
Diagnostic difficile car le 401 ne vient ni d'un Bearer manquant ni
de la chaîne Spring Security visible.

---

## 6. Interdits projet (backend Kotlin)

- **`!!` (force unwrap)** sauf justification écrite dans un commentaire
- **`@Autowired` field injection** (toujours constructor injection
  Kotlin)
- **`var` sur DTOs** (toujours `val` — immuabilité)
- **`runBlocking`** dans Controllers / Services prod (réservé tests)
- **`println` / `print`** — utiliser `KotlinLogging`
- **Lombok** (Kotlin a déjà l'équivalent natif)
- **`hibernate.ddl-auto: create|update`** en prod (Flyway uniquement)
- **`hibernate.ddl-auto: validate`** quand Phase B DB scaffolding skippée
  (cf. §4.4.2) — utiliser `none`
- **`hibernate.ddl-auto: validate`** sur PostgreSQL Database-First avec
  colonnes `char(N)` (post-mortem 2026-05-21) — Hibernate type-mapper
  signale `bpchar (Types#CHAR)` vs `char(N) (Types#VARCHAR)` même quand
  les colonnes existent et matchent par sémantique. **`none` est le
  défaut sain pour tout projet Database-First** ; n'activer `validate`
  qu'après un cycle de tests d'intégration qui prouve l'absence de
  faux-positifs avec le dialect+driver actuel.
- **`AntPathRequestMatcher`** (Spring Security 6.4+ deprecation, retrait en v7) —
  l'API a été dépréciée à partir de Spring Security 6.4 et est retirée
  en Spring Security 7 (post-mortem 2026-05-21,
  `Unresolved reference 'AntPathRequestMatcher'`). Utiliser des **string
  paths littéraux** dans `requestMatchers(...)` (Spring choisit
  automatiquement `PathPatternRequestMatcher` derrière) :
  ```kotlin
  auth.requestMatchers("/auth/config", "/actuator/health", "/swagger/**")
      .permitAll()
  ```
  Le pattern import + construction explicite `AntPathRequestMatcher("/x")`
  est interdit.
- **Séquence `/**` (deux étoiles) dans un commentaire KDoc** —
  Kotlin supporte les commentaires imbriqués (`/* /* */ */`), donc
  `/api/v1/**` à l'intérieur d'un KDoc `/** ... */` ouvre un niveau
  imbriqué jamais fermé → `error: Syntax error: Unclosed comment` à la
  compilation (post-mortem 2026-05-21). Préférer `/api/v1/[anything]`
  ou `/api/v1/<wildcard>` dans les KDoc. Code applicatif (hors
  commentaire) non concerné.
- **Flyway activé** (`spring.flyway.enabled: true`) sans `flyway-sqlserver`
  module quand DatabaseType=SqlServer (cf. §4.4.1)
- **`springdoc-openapi` < 2.7.0** quand Spring Security actif (cf. §5.6)
- **`/v3/api-docs` comme path OpenAPI** quand Spring Security actif —
  utiliser path custom (cf. §5.6)
- **`open-in-view: true`** (anti-pattern)
- **Secrets en dur** dans `application*.yml` (toujours `${ENV_VAR}`)
- **Logique métier dans Controllers / Repositories**
- **`try/catch` de formatage HTTP** dans Controllers (use
  `@RestControllerAdvice`)
- **N+1 query** non motivée
- **Versions de libs non pinnées** dans `build.gradle.kts`
- **`SNAPSHOT` versions** sauf justification stack
- **`TODO`, `FIXME`, code commenté, placeholders** (`changeme`, `foo`)
- **Endpoint sans `@Valid`** sur DTO d'entrée

---

## 7. Hors scope technique

- Tests unitaires → `qa/kotlin-junit.md`
- E2E, perf, a11y → hors scope SDD_Pro
- DevOps / CI / CD → hors scope SDD_Pro
- Multiplatform Kotlin (KMP) → hors scope (futur)
- GraphQL → hors scope (futur stack)
