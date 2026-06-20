# Tech FEAT: kotlin-mustache (fullstack)

Status: Experimental
Validation: 🟢 bench-validated runtime (2026-06-05 — CalcABCMustache :44349, Spring Boot 3.4.1 (bumped depuis 3.3.5 du bench original) + JMustache, monolithe SSR classique form POST reload, 159 LOC le plus compact du bench, AC-1/2/3 🟢. Bug fix appliqué : JMustache rejette `null` keys → populer Model avec strings vides + flags `hasX` booléens. Pattern documenté `library-and-stack.md §7.3`. Pipeline `/sdd-full` complet pas encore validé end-to-end — scaffolding manuel mainteneur, cf. `docs/benchmarks/known-gaps.md`)
Tech FEAT ID: tech-kotlin-mustache
Scope: **fullstack monolithe** — application Spring Boot 3.x (Kotlin) avec **templates Mustache** rendus serveur dans UN seul projet `{AppName}/`. UI HTML server-rendered + Controllers + Services + Spring Data JPA + Spring Security vivent dans le meme JAR. Pas de separation `{BackendName}` / `{AppName}` / `{LibName}`. Modele **SSR classique JVM** : HTML genere serveur (FreeMarker-like via Mustache), interactivite optionnelle via HTMX ou Alpine.js (capabilities) — pas de JS bundler, pas de SPA.

---

# 1. Architecture

## 1.1 Pattern applicatif

**Application fullstack monolithique Spring Boot Kotlin + Mustache**. Un seul projet `{AppName}/` (un seul JAR a deployer) qui :

- Sert des **pages HTML** rendues serveur via **`spring-boot-starter-mustache`** (`*.mustache` dans `templates/`)
- Expose des **Controllers** Spring MVC qui retournent des `Model` + nom de template (rendu serveur)
- Expose optionnellement des **REST endpoints** (`@RestController` sur `/api/*`) pour HTMX / Alpine / fetch ad-hoc
- Gere la **persistance** via Spring Data JPA (Hibernate) + Database-First scaffolding
- Gere l'**auth** via Spring Security (form login OU OAuth2 selon `## Active Auth Specs`)

Architecture cible :

```
Browser
  ├── HTML render serveur (templates Mustache)
  └── Interactivite optionnelle (HTMX hx-* attributes OU Alpine x-* attributes)
       │
       ▼
Spring Boot 3.x (Kotlin, JVM 21)
  ├── Controllers MVC  (@Controller) → return "users/list" + Model
  ├── Controllers REST (@RestController) → return JSON [optionnel, HTMX-compatible]
  ├── Services         (@Service)
  ├── Repositories     (Spring Data JPA, @Repository)
  ├── Entities         (@Entity JPA)
  ├── Security         (Spring Security configuration)
  └── Templates Mustache (resources/templates/*.mustache)
```

**Difference vs combo `backend/kotlin-spring-boot` × `frontend/react`** :
- Un seul JAR a deployer (pas de SPA build separe)
- **Pas de CORS** (meme origine)
- **Pas de `{LibName}` separe** — Models DTO et Entities cohabitent dans le meme package
- **Pas de bundler JS** (esbuild/webpack/Vite interdits) — interactivite via HTMX (server-fragment swap) OU Alpine (mini reactif inline)
- **Stack 100% JVM** — pas de Node.js dans le pipeline
- **Premiere page rendue en <100ms** (pas d'hydration JS, pas de download bundle)

---

## 1.2 Couches

- **Controllers MVC** (`@Controller`) : retournent `String` (nom de template) + injectent `Model` pour passer les donnees au template. Aucune logique metier.
- **Controllers REST** (`@RestController`, capability `htmx`) : retournent fragments HTML ou JSON pour appels HTMX/fetch
- **Services** (`@Service`) : logique metier, transactionalite (`@Transactional`)
- **Repositories** (Spring Data JPA, interface qui etend `JpaRepository<T, ID>`)
- **Entities** (`@Entity` JPA, Database-First scaffolding via `jpa-entity-generator` ou `hibernate-tools`)
- **Models** (DTOs vers vue, sans JPA) : data classes Kotlin
- **Mappers** : extension functions Kotlin (`Entity.toModel()`)
- **Security** (`SecurityFilterChain` bean) : auth + autorisation
- **Templates Mustache** (`resources/templates/*.mustache`) : HTML server-rendered, syntaxe `{{var}}`, `{{#list}}...{{/list}}`, `{{> partial}}`
- **Static** (`resources/static/`) : CSS, images, HTMX/Alpine scripts via CDN ou bundled

> **Patterns Spring partages** (services, repositories, validation, security, OpenAPI) : voir `.claude/stacks/backend/kotlin-spring-boot.md §1-§5` (integralement applicable hors couche View — ici Mustache au lieu de REST controllers seulement).

---

## 1.3 Mapping couche → repertoire

Un seul projet sous `workspace/output/src/{AppName}/`. **Convention single-project — `{BackendName}` et `{LibName}` ne s'appliquent pas**. Arch leve WARNING `[STACK_MALFORMED]` si declares avec valeur non null.

**Code Kotlin** (sous `workspace/output/src/{AppName}/src/main/kotlin/{AppNamespace}/`) :

| Layer | Path |
|---|---|
| Application entry | `Application.kt` (avec `@SpringBootApplication`) |
| Controllers MVC | `controllers/web/{Domain}Controller.kt` |
| Controllers REST (HTMX/JSON) | `controllers/api/{Domain}ApiController.kt` |
| Services | `services/{Domain}Service.kt` (+ interface optionnelle `{Domain}ServiceImpl.kt`) |
| Repositories | `repositories/{Domain}Repository.kt` (interface JPA) |
| Entities | `entities/{Domain}.kt` |
| Models / DTOs | `models/{Domain}{Action}Model.kt` |
| Mappers (extension fn) | `mappers/{Domain}Mappers.kt` |
| Security config | `config/SecurityConfig.kt` |
| OpenAPI config (capability) | `config/OpenApiConfig.kt` |
| Exception handler global | `config/GlobalExceptionHandler.kt` (annoté `@ControllerAdvice`) |
| Validators custom | `validators/{Name}Validator.kt` |

**Resources** (sous `workspace/output/src/{AppName}/src/main/resources/`) :

| Layer | Path |
|---|---|
| Templates Mustache | `templates/{domain}/{name}.mustache` |
| Partials Mustache | `templates/partials/_{name}.mustache` |
| Layout principal | `templates/layouts/_main.mustache` (inclusion via `{{> layouts/_main}}`) |
| Static CSS | `static/css/main.css` |
| Static JS (HTMX/Alpine) | `static/js/{name}.js` (ou via CDN dans `_main.mustache`) |
| Static images | `static/img/` |
| i18n | `messages.properties` + `messages_{lang}.properties` |
| Config Spring | `application.yml` (peuple par arch depuis stack.md) |
| Hibernate DDL (Database-First) | `db/migration/` (Flyway si capability `flyway`) |

**Manifestes** :
- Project file → `workspace/output/src/{AppName}/build.gradle.kts`
- Settings → `workspace/output/src/{AppName}/settings.gradle.kts`
- Gradle wrapper → `workspace/output/src/{AppName}/gradlew` + `gradle/wrapper/`

---

## 1.4 Principes non negociables

**Architecture Spring MVC + Mustache** :
- **Aucune logique metier dans Controllers** — deleguer aux Services. Controller MVC = lire `Model`, appeler service, retourner nom template.
- **Aucun acces JPA direct depuis Controller ou Template** — toujours via Service → Repository
- **Aucun mapping inline dans Controller** — toujours via `mappers/` (extension functions Kotlin `Entity.toModel()`)
- **Mustache logic-less** : pas de calcul dans le template (le langage Mustache est volontairement logic-less). Toute donnee derivee est calculee cote Kotlin et passee dans le `Model`.
- **Validation Bean Validation** (`@Valid`, `@NotBlank`, `@Email`, …) sur les inputs de Controller — pas de validation manuelle
- **Transactions** : `@Transactional` sur les methodes Service qui ecrivent — pas dans les Controllers
- **HTMX (capability)** : preferer aux endpoints REST + JS custom. Pattern : Controller retourne fragment HTML (template partial), HTMX swap via `hx-target`.
- **Alpine.js (capability)** : reserver aux interactivites client purement reactives (toggle, dropdowns) qui ne valent pas un aller-retour serveur

**Patterns Spring partages** : voir `.claude/stacks/backend/kotlin-spring-boot.md §1.4` (SOLID, Clean Code, anti-patterns inhérents Spring deja documentes — integralement applicable).

**Securite** :
- **CSRF token obligatoire** sur tous les POST/PUT/DELETE (formulaires HTML) — Spring Security l'ajoute par defaut, NE PAS desactiver
- **Auth declarative** via `SecurityFilterChain` — pas de `@PreAuthorize` ad-hoc disperses sans config centrale
- **Mustache auto-escape** : par defaut Mustache echappe les variables (`{{var}}` = HTML-escaped). `{{{var}}}` (triple brace) = raw HTML — utiliser UNIQUEMENT pour du HTML genere par le serveur (jamais user input)
- **Cookies** : `httpOnly` + `secure` (prod) + `sameSite: Lax` — gere par Spring Security par defaut

---

## 1.5 Couches persistantes

Patterns reconnus : `Entity`, `Entities`, `Repository`, `Repositories`, `Migration`, `Migrations`. Approche **Database-First** identique a `.claude/stacks/backend/kotlin-spring-boot.md §8` :

- Drivers JPA/Hibernate selon `DatabaseType`
- Scaffolding entities via Hibernate Tools OU `jpa-entity-generator` Gradle plugin
- DbContext = `AppDataSource` + `EntityManagerFactory` configures via `application.yml`

---

## 1.6 Interactivite client — matrice de decision

Quand est-ce qu'on a besoin de plus que du HTML statique render serveur ?

| Cas | Choix | Pattern |
|---|---|---|
| Form submit classique (POST + redirect) | **MVC Controller pur** | Spring MVC `@PostMapping`, return `"redirect:/users"` |
| Update partiel de la page (filtre liste, pagination, modal) | **HTMX (capability)** | `<button hx-get="/users/list?page=2" hx-target="#users-table">` + Controller retourne fragment template |
| Toggle UI pur (open/close menu, validation visuelle inline) | **Alpine.js (capability)** | `<div x-data="{ open: false }"><button @click="open = !open">...</button></div>` |
| Reactivity complexe (forms multi-step, drag&drop, WYSIWYG) | **❌ pas ce stack** | Choisir `frontend/react.md` + `backend/kotlin-spring-boot.md` |
| Real-time (chat, notifications push) | **WebSocket / SSE** | Spring `WebFlux` ou Spring `WebSocket` (capability `websocket`) |

**Anti-pattern majeur** : importer jQuery / React / Vue / Angular pour faire quelques toggles → c'est ce que HTMX + Alpine resolvent dans 95% des cas. Si vraiment besoin d'une SPA, sortir de ce stack.

---

# 2. Stack

## 2.1 Identite

- **Stack ID** : `fullstack-kotlin-mustache`
- **Langage** : Kotlin 2.1.x
- **Runtime** : JVM 21 LTS (Temurin/Adoptium recommande)
- **Framework** : Spring Boot 3.4.x
- **Template engine** : Mustache (logic-less) via `spring-boot-starter-mustache`
- **Build system** : Gradle 8.x avec Kotlin DSL (`build.gradle.kts`)
- **Namespace** : `{AppNamespace}` (package racine Kotlin)

---

## 2.2 Outils

- **Project file** : `workspace/output/src/{AppName}/build.gradle.kts`
- **Build** : `(cd workspace/output/src/{AppName} && ./gradlew build -x test --quiet)`
- **Run** : `(cd workspace/output/src/{AppName} && ./gradlew bootRun)`
- **JAR executable** : `(cd workspace/output/src/{AppName} && ./gradlew bootJar)` → `build/libs/{AppName}-{version}.jar`
- **Smoke Command** :

```bash
(cd workspace/output/src/{AppName} && ./gradlew compileKotlin --quiet)
test -d workspace/output/src/{AppName}/build/classes
```

- **Smoke Timeout** : 180s (Gradle premiere build ~60s, build incremental ~5-15s)
- **Package manager** : Gradle (jamais Maven sur ce stack)
- **Type-check** : integre a `compileKotlin`
- **Lint** : `ktlint` (capability `code-quality`)

---

## 2.2.1 Init Commands

```bash
if [ ! -f "workspace/output/src/{AppName}/build.gradle.kts" ]; then

# STEP 1 — Bootstrap via Spring Initializr CLI
# (alternative : appel HTTPS curl https://start.spring.io)
mkdir -p workspace/output/src/{AppName}
cd workspace/output/src/{AppName}

curl -s https://start.spring.io/starter.zip \
  -d type=gradle-project-kotlin \
  -d language=kotlin \
  -d bootVersion=3.4.1 \
  -d baseDir=. \
  -d groupId={AppNamespace} \
  -d artifactId={AppName} \
  -d name={AppName} \
  -d packageName={AppNamespace} \
  -d packaging=jar \
  -d javaVersion=21 \
  -d dependencies=web,mustache,data-jpa,validation,security,actuator \
  -o starter.zip

unzip -o starter.zip -d .
rm starter.zip

# STEP 2 — Creer arborescence applicative
PKG_PATH=$(echo "{AppNamespace}" | tr '.' '/')
mkdir -p \
  src/main/kotlin/${PKG_PATH}/controllers/web \
  src/main/kotlin/${PKG_PATH}/controllers/api \
  src/main/kotlin/${PKG_PATH}/services \
  src/main/kotlin/${PKG_PATH}/repositories \
  src/main/kotlin/${PKG_PATH}/entities \
  src/main/kotlin/${PKG_PATH}/models \
  src/main/kotlin/${PKG_PATH}/mappers \
  src/main/kotlin/${PKG_PATH}/config \
  src/main/kotlin/${PKG_PATH}/validators \
  src/main/resources/templates/layouts \
  src/main/resources/templates/partials \
  src/main/resources/static/css \
  src/main/resources/static/js \
  src/main/resources/static/img \
  src/main/resources/db/migration

# STEP 3 — Bootstrap application.yml (rempli par arch depuis stack.md)
cat > src/main/resources/application.yml <<'YAML'
spring:
  application:
    name: {AppName}
  datasource:
    # url, username, password peuples par arch depuis ## Active Database
    driver-class-name: org.postgresql.Driver
  jpa:
    hibernate:
      ddl-auto: validate           # Database-First : pas de regen schema
    properties:
      hibernate.dialect: org.hibernate.dialect.PostgreSQLDialect
  mustache:
    suffix: .mustache
    cache: true                    # mettre false en dev
  security:
    user:
      name: admin                  # auth-local : a remplacer par UserDetailsService

server:
  port: 8080
  servlet:
    context-path: /
YAML

# STEP 4 — Bootstrap template layout principal
cat > src/main/resources/templates/layouts/_main.mustache <<'MUSTACHE'
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{{title}} — {AppName}</title>
<link rel="stylesheet" href="/css/main.css"/>
</head>
<body>
  <header>{{> partials/_header}}</header>
  <main>{{$content}}{{/content}}</main>
  <footer>{{> partials/_footer}}</footer>
</body>
</html>
MUSTACHE

# STEP 5 — Premiere build (verifie compileKotlin)
./gradlew compileKotlin --quiet || true

fi
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/fullstack/kotlin-mustache.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-mustache`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| spring-boot-starter-web | 3.4.1 | Spring MVC + Tomcat embedded |
| spring-boot-starter-mustache | 3.4.1 | Template engine Mustache |
| spring-boot-starter-data-jpa | 3.4.1 | Spring Data JPA + Hibernate |
| spring-boot-starter-validation | 3.4.1 | Bean Validation (Jakarta) |
| spring-boot-starter-security | 3.4.1 | Spring Security |
| spring-boot-starter-actuator | 3.4.1 | /actuator/health, metrics |
| jackson-module-kotlin | 2.18.2 | JSON Kotlin-aware |
| kotlinx-coroutines-core | 1.10.1 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| db-postgres | postgresql | 42.7.4 | DatabaseType.*PostgreSql, postgres |
| db-mysql | mysql-connector-j | 9.1.0 | DatabaseType.*MySql, mysql, mariadb |
| db-sqlserver | mssql-jdbc | 12.8.1.jre11 | DatabaseType.*SqlServer |
| db-sqlite | sqlite-jdbc | 3.47.1.0 | DatabaseType.*Sqlite |
| htmx | htmx.org | 2.0.4 | htmx, partial.*reload, server.*fragment |
| alpine | alpinejs | 3.14.8 | alpine, alpine\.js, mini.*reactive |
| flyway | flyway-core | 11.1.0 | flyway, migrations, db.*versionning |
| openapi | springdoc-openapi-starter-webmvc-ui | 2.7.0 | swagger, openapi, /api-docs |
| jwt | jjwt-api | 0.12.6 | jwt, auth-local |
| azure-ad | spring-cloud-azure-starter-active-directory | 5.18.0 | auth-azure-ad, msal, azure-ad |
| excel | poi-ooxml | 5.4.0 | excel, \.xlsx, export.*excel |
| pdf | itext | 4.0.5 | pdf, export.*pdf |
| smtp | spring-boot-starter-mail | 3.4.1 | email, smtp, envoi.*mail |
| caffeine-cache | caffeine | 3.2.0 | cache, performance, memoization |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| org.jetbrains.kotlin.jvm | 2.1.0 | Plugin Kotlin JVM |
| org.jetbrains.kotlin.plugin.spring | 2.1.0 | Compiler open des classes Spring |
| org.jetbrains.kotlin.plugin.jpa | 2.1.0 | Compiler no-arg pour entities JPA |
| org.springframework.boot | 3.4.1 | Spring Boot Gradle plugin (bootJar) |
| io.spring.dependency-management |  | BOM management Spring Boot |
| org.jlleitschuh.gradle.ktlint | 12.1.2 | Lint Kotlin (capability code-quality) |

#### 2.4.d DB Drivers (selectionne par arch selon DatabaseType)

| DatabaseType | Module | Version | Scope |
|---|---|---|---|
| postgres | `org.postgresql:postgresql` | 42.7.4 | runtime |
| mysql | `com.mysql:mysql-connector-j` | 9.1.0 | runtime |
| sqlserver | `com.microsoft.sqlserver:mssql-jdbc` | 12.8.1.jre11 | runtime |
| sqlite | `org.xerial:sqlite-jdbc` | 3.47.1.0 | runtime |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Naming Conventions

Patterns OBLIGATOIRES — verifies par dev-* STEP 5.0. Toute violation = ERROR.

| Role | Pattern | Exemple |
|------|---------|---------|
| Controller MVC | `{Domain}Controller.kt` dans `controllers/web/`, annote `@Controller` | `UsersController.kt` |
| Controller REST/HTMX | `{Domain}ApiController.kt` dans `controllers/api/`, annote `@RestController` ou `@Controller` (selon retour HTML/JSON) | `UsersApiController.kt` |
| Service interface | `{Domain}Service.kt` (interface) | `UsersService.kt` |
| Service impl | `{Domain}ServiceImpl.kt` (classe `@Service`) | `UsersServiceImpl.kt` |
| Repository | `{Domain}Repository.kt` (interface, etend `JpaRepository<T, ID>`) | `UsersRepository : JpaRepository<UserEntity, Long>` |
| Entity | `{Domain}Entity.kt` (annote `@Entity @Table(name = "users")`) | `UserEntity.kt` |
| Model (DTO) | `{Domain}{Action}Model.kt` (data class Kotlin) | `UserListItemModel`, `UserDetailModel` |
| Mapper (extension fn) | `{Domain}Mappers.kt` (fichier) — fonctions `fun UserEntity.toListItemModel(): UserListItemModel` | `UsersMappers.kt` |
| Template Mustache | `{domain}/{name}.mustache` (kebab-case) | `users/list.mustache`, `users/detail.mustache` |
| Template partial | `partials/_{name}.mustache` (prefix underscore) | `partials/_header.mustache` |
| Template layout | `layouts/_{name}.mustache` | `layouts/_main.mustache` |

**Suffixes INTERDITS** :
- `Dto`, `Request`, `Response`, `Result` (utiliser `Model`)
- `Manager`, `Helper`, `Util` (sauf `utils/` strict pour pure functions sans state)
- `Impl` postfix sur l'interface (l'interface n'a pas de suffixe ; l'implementation l'a)

**Conventions de fichier** :
- Kotlin : `PascalCase.kt` pour les classes, `kebab-case.kt` accepte pour les fichiers de fonctions top-level
- Templates : `kebab-case.mustache`, partials prefixes `_`
- CSS / JS / images : `kebab-case`

---

## 3. Endpoints standard (obligatoires)

| Endpoint | Auth | Role | Type |
|----------|------|------|------|
| `GET /` | non | Page accueil (template `index.mustache`) | MVC |
| `GET /login` | non | Page login Spring Security | MVC |
| `POST /login` | non | Submit form login | MVC (gere par Spring Security) |
| `POST /logout` | oui | Logout | MVC |
| `GET /actuator/health` | non (selon config) | Healthcheck Spring Boot Actuator | REST |

**Swagger / OpenAPI** : optionnel (capability `openapi`). Si declare → ajouter `springdoc-openapi-starter-webmvc-ui` → UI disponible sur `/swagger-ui.html` + JSON sur `/v3/api-docs`. Pertinent uniquement si l'app expose une API REST consommable.

---

## 4. Versioning des API

`/api/v1/{domain}` pour les controllers REST. Pas applicable aux controllers MVC (URL = routing UI).

---

## 5. Interdits projet (kotlin-mustache)

**Architecture** :
- Logique metier dans Controller → toujours via Service
- Acces direct JPA Repository depuis Controller → toujours via Service
- Acces direct JPA depuis Mustache (`{{#users.findAll}}`) → preparer les donnees dans Controller, passer en Model
- `EntityManager.createNativeQuery("SELECT ...")` hors Repository
- Mapping inline dans Controller / Service → toujours via extension functions Kotlin (`Entity.toModel()`)
- Validation manuelle `if (form.email.isEmpty()) ...` → toujours `@Valid` + Bean Validation
- Template Mustache avec `{{{var}}}` (triple brace = raw HTML) pour du user input → XSS garanti

**Code quality** :
- `println` / `System.out.println` → utiliser SLF4J `private val log = LoggerFactory.getLogger(javaClass)` (Kotlin idiom)
- `Any?` injustifie dans signatures
- `lateinit var` dans Service injecte → utiliser `val` + injection constructor
- `TODO()`, `FIXME` dans le code livre
- Imports stars `import org.springframework.*` → toujours explicites

**Securite** :
- CSRF desactive (`csrf().disable()`) en prod sans justification
- `permitAll()` global sans whitelist precise
- Connection string DB en dur hors section `spring.datasource` peuplee par `arch` depuis `stack.md`
- Secret JWT / API key en dur hors section native `application.yml` peuplee par `arch` depuis `stack.md`
- Log de mots de passe / tokens / body request complet

**JPA / ORM** :
- `Entity.findAll()` sans pagination sur table volumineuse — utiliser `Pageable`
- N+1 query (loop de `findById`) — utiliser `@EntityGraph` ou `@Query` avec JOIN FETCH
- `@Transactional` sur un Controller — toujours sur les Services (couche transactionnelle metier)
- `cascade = CascadeType.ALL` par defaut sur les relations — etre explicite par operation
- Auto DDL `ddl-auto: update` en prod (Database-First → toujours `validate` ou `none`)

**Templates Mustache** :
- Logique conditionnelle complexe dans template — preparer un flag boolean dans le Model cote Controller
- Iteration imbriquee profonde (> 2 niveaux) — flatten cote Kotlin
- `{{{var}}}` sur user input → toujours `{{var}}` (auto-escape)
- HTML genere par concatenation de strings cote Service → utiliser un partial Mustache

**Build** :
- Engager `build/`, `.gradle/`, `out/`, `.env`, `application-prod.yml` (avec secrets) dans git
- Pas de `wrapper-validation` GitHub Action pour valider `gradle-wrapper.jar`

---

## 6. Persistance

- **Mode JPA** (defaut quand `DatabaseType ≠ none`) : Spring Data JPA + Hibernate Database-First. Pattern identique a `.claude/stacks/backend/kotlin-spring-boot.md §8.3`
- **Driver** selon `DatabaseType` (cf. §2.4.b on-demand)
- **DataSource config** : `spring.datasource.url` / `username` / `password` dans `application.yml` peuple par arch depuis `## Active Database`. **JAMAIS** via `${DB_HOST}` / env var runtime dans le code applicatif.

> File-based JSON store n'a pas vraiment de sens dans cet ecosysteme JVM — preferer SQLite (capability `db-sqlite`) qui reste un fichier mais offre le confort SQL + JPA.

---

## 7. Temps reel

- **SSE** : `@GetMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)` retourne `SseEmitter` ou `Flux<ServerSentEvent>` (avec WebFlux). Pattern Spring natif :

```kotlin
@RestController
class EventsController {
    @GetMapping("/api/events", produces = ["text/event-stream"])
    fun events(): SseEmitter {
        val emitter = SseEmitter(0L)
        // ... push depuis un service (Sinks<T> Reactor recommande)
        return emitter
    }
}
```

- **WebSocket** : capability `websocket` — `spring-boot-starter-websocket` + STOMP. Cote client : Mustache + `stompjs` via CDN.
- **HTMX SSE extension** : combo elegant — HTMX `hx-ext="sse"` consomme un endpoint SSE Spring directement dans le template. Pas de JS custom necessaire.

---

## 8. Anti-pattern — quand NE PAS choisir ce stack

Ce stack est optimise pour :
- **Apps d'entreprise** orientees CRUD (back-office, ERP leger, applications RH/finance)
- **Equipes JVM** sans competences React/Vue/Angular
- **Apps internes** sans besoin d'UX riche (CRUD list/detail/edit suffit)
- **Deploiement on-premise JVM** (Tomcat, JAR direct, Kubernetes JVM)
- **Apps avec contraintes de SEO sur du contenu serveur** (premiere page rapide, HTML brut)

**NE PAS choisir si** :
- ❌ UX riche / SPA-like avec navigation client fluide → `backend/kotlin-spring-boot.md` + `frontend/react.md` ou `vue.md`
- ❌ Mobile-first PWA → SPA dediee + API REST
- ❌ Deploiement serverless (Lambda, Cloud Functions) — JVM cold start > 1s, JIT mauvais ROI → `node-react.md` ou `next.md`
- ❌ Application offline-first → SPA + service workers
- ❌ Pas de competences JVM dans l'equipe → autre stack
- ❌ Pages avec animations / interactions JavaScript complexes → SPA

---

## 9. Combos valides

| Combo | Status | Source |
|---|---|---|
| `fullstack-kotlin-mustache` + `auth-local` + `qa-kotlin-junit` + `PostgreSql` + `htmx` (capability) | 🟡 experimental | jamais valide end-to-end |
| `fullstack-kotlin-mustache` + `auth-azure-ad` + `qa-kotlin-junit` + `SqlServer` + `htmx` | 🟡 experimental | viable |
| `fullstack-kotlin-mustache` + `auth-local` + `qa-kotlin-junit` + `Sqlite` (sans HTMX) | 🟡 experimental | proto, CRUD basique |

---

## 10. Notes pour l'agent `arch`

1. **Detecter** `## Active Tech Specs` = `fullstack/kotlin-mustache.md` → **ignorer** `BackendName` et `LibName` (WARNING `[STACK_MALFORMED]` si declares)
2. **Creer** UN seul projet via Spring Initializr CLI (cf. §2.2.1)
3. **Composer** `application.yml` depuis `## Active Database` + `## Active Auth Specs` + `## Active SMTP Server` (si declare). Materialiser les valeurs dans les sections natives Spring (`spring.datasource`, `auth.jwt`, `azure.ad`, `mail`), sans substitution `${DB_*}` ni export env runtime.
4. **`## Active UI Specs`** : aucun design system n'est applicable (pas de React/Vue/Blazor). Si declare → WARNING bloquant `[STACK_INCOMPAT]`. CSS custom dans `static/css/` + composants Mustache.
5. **Capabilites recommandees** : `htmx` + `alpine` pour interactivite minimaliste. Si l'US contient "filtre dynamique", "modal", "pagination ajax" → trigger `htmx` automatiquement.
6. **Phase B (DB scaffolding)** : selon `DatabaseType` — pattern Database-First identique a `kotlin-spring-boot.md §8.3` (jpa-entity-generator OU hibernate-tools)
7. **Phase C (ADRs)** : creer `ADR-{ts}-stack-fullstack-kotlin-mustache.md` documentant Spring Boot 3.4 + Kotlin + Mustache + (eventuellement HTMX)

---

## 11. Notes pour les agents `dev-backend` / `dev-frontend`

⚠️ **Important** : ce stack est lu par **les deux agents** dev-* MAIS la frontiere est moins nette qu'en `next.md` ou `nuxt.md` — le rendu UI vit cote serveur (templates Mustache).

**Convention de repartition** :

- `dev-backend` materialise : Controllers (MVC + REST), Services, Repositories, Entities, Models, Mappers, config, validators, `application.yml` (augment), `build.gradle.kts` (augment deps)
- `dev-frontend` materialise : Templates Mustache (`templates/**/*.mustache`), CSS (`static/css/**`), JS HTMX/Alpine (`static/js/**`), images (`static/img/**`), i18n `messages.properties`

**File ownership** (override `file-ownership.md §1`) :

| Path | Owner |
|---|---|
| `workspace/output/src/{AppName}/src/main/kotlin/**` | `dev-backend` |
| `workspace/output/src/{AppName}/src/main/resources/templates/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/src/main/resources/static/**` | `dev-frontend` |
| `workspace/output/src/{AppName}/src/main/resources/messages*.properties` | `dev-frontend` (libelles UI multilingues) |
| `workspace/output/src/{AppName}/src/main/resources/application.yml` | `arch` (create) + `dev-backend` (augment sections) |
| `workspace/output/src/{AppName}/src/main/resources/db/migration/**` | `arch` (Phase B scaffolding) + `dev-backend` (migrations Flyway si capability) |
| `workspace/output/src/{AppName}/build.gradle.kts` | `arch` (create) + `dev-backend` (augment dependencies on-demand) |
| `workspace/output/src/{AppName}/src/main/resources/application.yml` | `arch` (create exclusif config initiale) + `dev-backend` (augment sections non secretes) |

**Cas frontiere — modeles passes aux templates** : un Controller MVC dans `dev-backend` cree un Model (DTO data class Kotlin) puis appelle `model.addAttribute("users", users)` + return `"users/list"`. Le template `templates/users/list.mustache` cote `dev-frontend` consomme `{{#users}}{{name}}{{/users}}`. **Contrat partage** : nom de la cle (`"users"`) + structure du Model. Toute modification d'un cote DOIT etre synchronisee de l'autre — equivalent du "frontend-backend contract" mais intra-projet.

---

## 12. Smoke test attendu (post-init arch)

```bash
cd workspace/output/src/{AppName}
./gradlew compileKotlin --quiet
test -f build.gradle.kts
test -f src/main/resources/application.yml
test -f src/main/resources/templates/layouts/_main.mustache
grep -q "spring-boot-starter-mustache" build.gradle.kts
grep -q "spring-boot-starter-data-jpa" build.gradle.kts
echo "smoke OK"
```

Smoke complet (~180s) : `./gradlew bootJar` doit produire `build/libs/{AppName}-*.jar` sans erreur. Run optionnel : `./gradlew bootRun` puis `curl -sf http://localhost:8080/actuator/health` doit retourner `{"status":"UP"}`.
