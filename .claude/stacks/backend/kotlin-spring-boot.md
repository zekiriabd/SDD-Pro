# Tech Spec: kotlin-spring-boot (backend)

Status: Stable
Tech Spec ID: tech-kotlin-spring-boot
Scope: backend uniquement (REST API, logique métier, persistance)

---

## 1. Architecture

### 1.1 Pattern applicatif

Spring Boot 3.4 + Kotlin 2.0 REST API, idiomatique Kotlin :

```
Controller → Service (interface + impl) → Repository (Spring Data JPA)
                                       → Entity → MapStruct/Manual → DTO
```

Pattern **MVC enrichi** avec immutabilité Kotlin :
- **Data classes** pour DTOs (immuables par défaut, `data class`)
- **Constructor injection** (Kotlin idiomatique)
- **Coroutines** pour code async (`suspend fun`)

### 1.2 Couches

- **Controller** : `@RestController` Kotlin avec data class params
- **Service (interface)** : Kotlin `interface` (pas de package séparé)
- **Service (implémentation)** : Kotlin `class` avec
  `@Service`
- **Repository** : `interface` étendant `JpaRepository<T, ID>`
- **Mapper** : Kotlin extension functions OU MapStruct (au choix par
  cas — extension functions plus idiomatiques pour mappings simples)
- **DTO** : Kotlin **data classes** (`val` exclusivement = immuable)
- **Entity** : `@Entity` JPA Kotlin avec **mutable fields** (JPA
  exigence) ou Kotlin records (limité)
- **Exception handler** : `@RestControllerAdvice` global

### 1.3 Mapping couche → répertoire

```
workspace/output/src/{BackendName}/
├── build.gradle.kts                                   # Gradle Kotlin DSL
├── settings.gradle.kts
├── src/
│   ├── main/
│   │   ├── kotlin/{BackendNamespace}/
│   │   │   ├── {BackendName}Application.kt           # @SpringBootApplication
│   │   │   ├── controller/                           # REST endpoints
│   │   │   ├── service/                              # interfaces + impls
│   │   │   ├── repository/                           # JPA repos
│   │   │   ├── entity/                               # @Entity classes
│   │   │   ├── dto/workspace/input/                            # Input data classes
│   │   │   ├── dto/workspace/output/                           # Output data classes
│   │   │   ├── dto/model/                            # Shared models
│   │   │   ├── mapper/                               # Extension fns / MapStruct
│   │   │   ├── config/                               # @Configuration
│   │   │   ├── exception/                            # Custom exceptions
│   │   │   ├── advice/                               # @RestControllerAdvice
│   │   │   └── security/                             # Spring Security
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-dev.yml
│   │       ├── messages/
│   │       └── db/migration/                         # Flyway scripts
│   └── test/
│       └── kotlin/{BackendNamespace}/
│           └── ...                                    # cf. qa/kotlin-junit.md
```

### 1.4 Principes non négociables

- **Data classes** pour DTOs (`val`, immuables, `equals/hashCode/toString` auto)
- **Constructor injection** uniquement (Kotlin natif via `class A(val x: X)`)
- **Aucune logique métier** dans Controllers / Repositories
- **Mapping** : extension functions OU MapStruct (jamais inline dans
  Controller / Service)
- **Coroutines** pour I/O async (Spring WebFlux ou
  `@Async` + `CompletableFuture` selon contexte)
- **Lombok interdit** (Kotlin a déjà l'équivalent natif)
- **`!!` (force unwrap) interdit** sauf justification écrite — utiliser
  `?:`, `let`, `requireNotNull`
- **Migrations DB via Flyway** (pas de `ddl-auto: create` en prod)
- **Logging via SLF4J** : `private val log = LoggerFactory.getLogger(...)`
  ou `KotlinLogging.logger {}`

---

## 2. Stack

### 2.1 Identité

- **Stack ID** : `back-kotlin-spring`
- **Langage** : Kotlin 2.0.21
- **Runtime** : JDK 21
- **Framework principal** : Spring Boot 3.4.x
- **Build tool** : **Gradle 8.10** avec **Kotlin DSL** (`build.gradle.kts`)
- **Package racine** : `{BackendNamespace}` (ex. `com.sdd-pro.sim`)

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
    -d bootVersion=3.4.0 \
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
# Auto-genere depuis kotlin-spring-boot.libs.json -- ne pas editer (utiliser sync-stack-md.ps1).
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
```
<!-- ONDEMAND_PACKAGES_END -->

### 2.2.2 Plugins Gradle obligatoires (`build.gradle.kts`)

```kotlin
plugins {
    id("org.springframework.boot") version "3.4.0"
    id("io.spring.dependency-management") version "1.1.7"
    kotlin("jvm") version "2.0.21"
    kotlin("plugin.spring") version "2.0.21"
    kotlin("plugin.jpa") version "2.0.21"      // no-arg pour @Entity
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

> Source de verite : `.claude/stacks/backend/kotlin-spring-boot.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/scripts/sync-stack-md.ps1 -StackId kotlin-spring-boot`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| spring-boot-starter-web |  |  |
| spring-boot-starter-webflux |  |  |
| spring-boot-starter-actuator |  |  |
| spring-boot-starter-security |  |  |
| spring-boot-starter-oauth2-resource-server |  |  |
| spring-boot-starter-oauth2-client |  |  |
| spring-boot-starter-data-jpa |  |  |
| spring-boot-starter-flyway |  |  |
| flyway-core | 12.5.0 |  |
| spring-dotenv | 4.0.0 |  |
| spring-context |  |  |
| jackson-module-kotlin |  |  |
| kotlin-reflect | 2.3.21 |  |
| nimbus-jose-jwt | 9.40 |  |
| spring-boot-starter-test |  |  |
| spring-boot-starter-webmvc-test |  |  |
| spring-security-test |  |  |
| kotest-runner-junit5 | 5.9.1 |  |
| kotest-assertions-core | 5.9.1 |  |
| kotest-extensions-spring | 1.3.0 |  |
| mockwebserver | 4.12.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect-capabilities.ps1` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| redis-cache | spring-boot-starter-data-redis |  | \bredis\b, cache distribu, distributed cache, session partag |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| org.jetbrains.kotlin.jvm | 2.3.21 |  |
| org.jetbrains.kotlin.plugin.spring | 2.3.21 |  |
| org.jetbrains.kotlin.plugin.jpa | 2.3.21 |  |
| org.springframework.boot | 4.0.6 |  |
| org.jlleitschuh.gradle.ktlint | 14.2.0 |  |
| org.flywaydb.flyway | 12.5.0 |  |

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
@RequestMapping("/api/v1/users")
class UserController(
    private val userService: UserService
) {
    @GetMapping("/{id}")
    fun findById(@PathVariable id: Long): ResponseEntity<UserOutputDto> =
        ResponseEntity.ok(userService.findById(id))

    @PostMapping
    fun create(@Valid @RequestBody input: UserInputDto): ResponseEntity<UserOutputDto> =
        ResponseEntity.status(HttpStatus.CREATED).body(userService.create(input))
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

### 4.2 Connection string (`application.yml`)

Identique à `java-spring-boot.md §4.2`. Variables d'env : `DB_HOST`,
`DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

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

Identique à `java-spring-boot.md §4.3`.

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
tasks.register("dbScaffold") {
    group = "sdd-pro"
    description = "Reverse-engineer DB schema -> Kotlin JPA entities (READ-ONLY)"
    doLast {
        val dbUrl  = "jdbc:postgresql://${System.getenv("DB_HOST")}:${System.getenv("DB_PORT")}/${System.getenv("DB_NAME")}"
        val dbUser = System.getenv("DB_USER") ?: error("DB_USER missing")
        val dbPass = System.getenv("DB_PASSWORD") ?: error("DB_PASSWORD missing")

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

Identique à `java-spring-boot.md §5-§8` sauf §5.6 ci-dessous spécifique
Spring Boot 3.5+. Différence majeure logging : préféré via
**`KotlinLogging`** (Slf4j sous le capot) plutôt que `@Slf4j` Lombok :

```kotlin
private val log = KotlinLogging.logger {}

// usage
log.info { "User $id logged in" }
```

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
