---
us: 1-1-Authentification
family: backend
generated-at: 2026-05-07T00:00:00Z
generated-by: agent dev-backend (mode :plan)
stack-backend: kotlin-spring-boot
stack-auth: azure-ad
---

# Plan technique backend — 1-1-Authentification

## Files

- path: workspace/output/src/simback/src/main/kotlin/simback/config/AzureAdProperties.kt
  operation: create
  layer: Config
  covers_acs: [AC-4, AC-5]

- path: workspace/output/src/simback/src/main/kotlin/simback/security/SecurityConfig.kt
  operation: create
  layer: Config
  covers_acs: [AC-4, AC-5, AC-6, AC-7]

- path: workspace/output/src/simback/src/main/kotlin/simback/config/CorsConfig.kt
  operation: create
  layer: Config
  covers_acs: [AC-6]

- path: workspace/output/src/simback/src/main/kotlin/simback/dto/output/AuthConfigOutputDto.kt
  operation: create
  layer: DTO
  covers_acs: [AC-2]

- path: workspace/output/src/simback/src/main/kotlin/simback/controller/AuthConfigController.kt
  operation: create
  layer: Controller
  covers_acs: [AC-2]

- path: workspace/output/src/simback/src/main/kotlin/simback/advice/GlobalExceptionHandler.kt
  operation: create
  layer: Middleware
  covers_acs: [AC-5, AC-7]

- path: workspace/output/src/simback/src/main/resources/application.yml
  operation: augment
  layer: Config
  preserves: [spring.application.name, spring.datasource, spring.flyway, logging]
  adds: [spring.security.oauth2.resourceserver.jwt, management.endpoints]
  covers_acs: [AC-4, AC-5]

## ACs Coverage Summary

| AC | Files |
|----|-------|
| AC-2 | AuthConfigOutputDto.kt, AuthConfigController.kt |
| AC-4 | AzureAdProperties.kt, SecurityConfig.kt, application.yml |
| AC-5 | SecurityConfig.kt, GlobalExceptionHandler.kt, application.yml |
| AC-6 | SecurityConfig.kt, CorsConfig.kt |
| AC-7 | SecurityConfig.kt, GlobalExceptionHandler.kt |

## Notes

### BackendNamespace

Package racine déduit : `simback` (BackendName = simback, namespace convention = same lowercase).
Tous les fichiers Kotlin utilisent `package simback.{layer}`.

### AzureAdProperties — binding env vars

`AzureAdProperties` est une `@ConfigurationProperties(prefix = "azure.activedirectory")`
data class lisant les valeurs depuis `application.yml`, lui-même peuplé via
interpolation `${AZ_TENANTID}`, `${AZ_CLIENTID}`, etc. (spring-dotenv actif en §2.4.a).
Fail-fast au démarrage si variable manquante (`@NotBlank`).

### SecurityConfig — Spring Security OAuth2 Resource Server

Spring Boot 3.4 + `spring-boot-starter-oauth2-resource-server` (§2.4.a CORE).
Pattern :
- `SecurityFilterChain` déclaré en `@Configuration` Kotlin
- `http.authorizeHttpRequests` : permit `/api/config/auth` (public, exigé §5.1 azure-ad.md)
- Toutes autres routes → `authenticated()`
- `http.oauth2ResourceServer { jwt { } }` — validation JWT via JWKS Azure AD
- Audiences validées via `JwtDecoder` bean surchargé avec `NimbusJwtDecoder` +
  `DelegatingOAuth2TokenValidator` (issuer + audience + expiration)
- Lib utilisée : `nimbus-jose-jwt` (§2.4.a CORE) + `spring-boot-starter-oauth2-resource-server`
- Token expiré → filtre Spring Security retourne 401 avant tout handler → AC-5
- Appel anonyme → 401 → AC-6

### CorsConfig

`WebMvcConfigurer` bean. Origins configurées depuis env var `CORS_ALLOWED_ORIGINS`
(ou wildcard dev). Permet au frontend React d'envoyer le header `Authorization: Bearer`.

### AuthConfigController — endpoint public /api/config/auth

`@RestController`, `@RequestMapping("/api/config/auth")`.
`@GetMapping` sans `@PreAuthorize` → accessible sans token (pattern §5.1 azure-ad.md).
Retourne `AuthConfigOutputDto` construit depuis `AzureAdProperties` :
- `authority` : `${AZ_INSTANCE}/${AZ_TENANTID}`
- `clientId` : `AZ_CLIENTID`
- `scopes` : `["api://AZ_CLIENTID/access_as_user"]` + `AZ_SCOPES`
- `redirectUri` : `AZ_FE_CALLBACKPATH`

### GlobalExceptionHandler

`@RestControllerAdvice` Kotlin. Handlers :
- `AccessDeniedException` → `ProblemDetail` 403 avec message générique (AC-7 : sans fuite)
- `AuthenticationException` → `ProblemDetail` 401
- `JwtValidationException` → `ProblemDetail` 401 (token invalide/expiré — AC-5)
Log dev-only des causes réelles via `KotlinLogging` (niveau DEBUG).

### application.yml — augment

Ajouter sous section `spring` :
```yaml
security:
  oauth2:
    resourceserver:
      jwt:
        issuer-uri: https://login.microsoftonline.com/${AZ_TENANTID}/v2.0
        audiences: ${AZ_AUDIENCES}
```
Et section `azure.activedirectory` pour AzureAdProperties binding.
Conserver toutes les clés existantes (datasource, flyway, logging).

### Libs utilisées (toutes §2.4.a CORE — pas d'install on-demand nécessaire)

- `spring-boot-starter-security` : SecurityFilterChain
- `spring-boot-starter-oauth2-resource-server` : JWT Bearer middleware
- `nimbus-jose-jwt` 9.40 : validation JWT / JWKS
- `spring-dotenv` 4.0.0 : lecture .env → `application.yml` interpolation
- `spring-context` : `@ConfigurationProperties`, `@Configuration`
- `jackson-module-kotlin` : sérialisation AuthConfigOutputDto

Aucune lib on-demand déclenchée (pas de Redis, pas d'Excel, pas de PDF dans l'US).
