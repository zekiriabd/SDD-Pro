---
generated-by: agent arch
generated-at: 2026-05-07T22:56:55Z
stack-md-hash: 0094A995
project-type: backend
project-name: simback
active-stacks:
  - .claude/stacks/backend/kotlin-spring-boot.md
  - .claude/stacks/auth/azure-ad.md
---

# simback -- Backend Project Context

## Project Config (subset)
- BackendName: simback
- AppNamespace: simfront
- DatabaseType: SqlServer
- LibStrategy: openapi-codegen

## Architecture
Spring Boot 3.5 + Kotlin 2.2 REST API (idiomatique Kotlin).
Pattern MVC enrichi : Controller -> Service (interface + impl) -> Repository (Spring Data JPA) -> Entity -> Mapper -> DTO.
Data classes pour DTOs (immuables, val exclusivement). Constructor injection. Migrations via Flyway.

## Layer -> Path Mapping
- Controller       -> src/main/kotlin/simfront/controller/
- Service interface -> src/main/kotlin/simfront/service/ (interface + impl dans le meme package)
- Repository       -> src/main/kotlin/simfront/repository/
- Entity (scaffold) -> src/main/kotlin/simfront/entity/
- DTO input        -> src/main/kotlin/simfront/dto/input/
- DTO output       -> src/main/kotlin/simfront/dto/output/
- DTO model        -> src/main/kotlin/simfront/dto/model/
- Mapper           -> src/main/kotlin/simfront/mapper/ (extension functions Kotlin)
- Config           -> src/main/kotlin/simfront/config/
- Exception        -> src/main/kotlin/simfront/exception/
- Advice           -> src/main/kotlin/simfront/advice/ (@RestControllerAdvice)
- Security         -> src/main/kotlin/simfront/security/
- Migration Flyway -> src/main/resources/db/migration/

## Build Command
cd workspace/output/src/simback && ./gradlew compileKotlin

Note: Gradle 9.5.0 + Kotlin 2.2.0 sur JDK 26. JVM target bytecode 21 configure dans build.gradle.kts.

## Persistence
- Driver installe: mssql-jdbc 12.8.1.jre11
- Connection string: jdbc:sqlserver://${DB_HOST}:${DB_PORT};databaseName=${DB_NAME};encrypt=true;trustServerCertificate=true
- Config: src/main/resources/application.yml (variables DB_* via env vars)
- Scaffolding tool: hibernate-tools (reverse-engineering JPA) ou generation manuelle depuis schema.json
- Schema source: workspace/output/db/schema.json (READ-ONLY introspection)
- Note: Phase B DB skipped (reseau SQL Server inaccessible depuis l'environnement de build)

## Auth
- Provider: azure-ad (Spring Security OAuth2 Resource Server)
- Pattern: JWT bearer token valide contre Azure AD
- Env vars: AZURE_ISSUER_URI (configure dans application.yml)

## Forbidden patterns
- !! (force unwrap) sans justification commentee
- @Autowired field injection (toujours constructor injection)
- var sur DTOs (toujours val)
- runBlocking dans Controllers/Services prod
- println/print (utiliser KotlinLogging)
- Lombok
- hibernate.ddl-auto: create|update en prod (Flyway uniquement)
- open-in-view: true
- Secrets en dur dans application*.yml
- Logique metier dans Controllers/Repositories
- try/catch de formatage HTTP dans Controllers (use @RestControllerAdvice)
- Versions de libs non pinnees dans build.gradle.kts
- SNAPSHOT versions
- TODO, FIXME, code commente, placeholders

## Env vars consommees au runtime
- DB: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
- Auth: AZURE_ISSUER_URI

## Notes
- Ce fichier est regenere a chaque /arch-init (hash invalide si stack.md change).
- Source de verite: .claude/stacks/backend/kotlin-spring-boot.md + .claude/stacks/auth/azure-ad.md
- Gradle 9.5.0 requis (Gradle 8.x incompatible avec JDK 26 sur ce poste).
- Kotlin 2.2.0 requis (2.0.x/2.1.x ont un bug JavaVersion.parse() sur JDK 26).
