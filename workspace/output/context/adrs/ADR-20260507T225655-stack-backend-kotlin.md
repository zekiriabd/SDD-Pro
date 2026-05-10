# ADR-20260507T225655 -- Backend stack -- Kotlin Spring Boot

- **Statut** : Accepted
- **Date** : 2026-05-07
- **Auteur** : arch
- **Phase** : 4-ARCH

---

## Context

Le projet simback requiert une API REST backend capable de s'integrer a SQL Server et Azure AD. Le Tech Lead a selectionne `kotlin-spring-boot` dans workspace/input/stack/stack.md pour beneficier du tooling Spring Data JPA natif, de la securite OAuth2 Resource Server et de l'expressivite Kotlin (data classes, coroutines, extension functions).

---

## Decision

Le backend est implemente avec Kotlin 2.2.0 + Spring Boot 3.5.0 (stack `backend/kotlin-spring-boot.md`). Build system: Gradle 9.5.0 (requis pour JDK 26 disponible sur ce poste -- Gradle 8.x incompatible). JVM target bytecode: 21.

---

## Consequences

**Positifs :**
- Data classes Kotlin pour DTOs (immutabilite native, equals/hashCode/toString auto).
- Constructor injection idiomatique, pas de @Autowired.
- Spring Data JPA + Flyway pour la persistance type-safe.
- OAuth2 Resource Server integre pour Azure AD JWT validation.

**Negatifs / dette acceptee :**
- Kotlin 2.0.x/2.1.x incompatibles avec JDK 26 (bug JavaVersion.parse). Kotlin 2.2.0 minimum requis.
- Gradle 9.5.0 requis au lieu de 8.x specifie dans le stack (adaptation environnement JDK 26).

---

## Alternatives considerees

- NONE -- impose par workspace/input/stack/stack.md (## Active Tech Specs).

---

## Liens

- Stack : `.claude/stacks/backend/kotlin-spring-boot.md`
