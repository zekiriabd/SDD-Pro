# QA Stack — Kotlin JUnit 5 + MockK + JaCoCo

> §2.4 (Librairies) régénérée depuis `kotlin-junit.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-junit`).

Status: Stable
Validation: 🟢 reference (validated combo CMS — kotlin-spring-boot + react + shadcn + azure-ad, 2026-05-13)
QA FEAT ID: kotlin-junit
Scope: tests unitaires backend Kotlin (Spring Boot, Ktor)

---

## 1. Scope

Tests unitaires pour backends Kotlin (Spring Boot, Ktor, etc.).
S'applique aux projets `workspace/output/src/{BackendName}/` typés Kotlin.

> **Prérequis** : projet Kotlin avec Gradle (Kotlin DSL `build.gradle.kts`
> recommandé). Les commandes Maven sont possibles mais non documentées
> ici — adapter manuellement.

---

## 2. Tooling

### 2.1 Test runner
- **JUnit 5 (Jupiter)** (`org.junit.jupiter:junit-jupiter`)
- **kotlin-test-junit5** (helpers Kotlin)

### 2.2 Coverage tool
- **JaCoCo** (`jacoco` plugin Gradle)
- Output : `build/reports/jacoco/test/jacocoTestReport.xml`

### 2.3 Mock library
- **MockK** (`io.mockk:mockk`) — Kotlin-first, supporte coroutines
- Alternative : Mockito-Kotlin (moins idiomatique)

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/kotlin-junit.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id kotlin-junit`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| junit-jupiter | 5.11.4 |  |
| kotlin-test-junit5 | 2.3.21 |  |
| mockk | 1.13.13 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| spring-test | spring-boot-starter-test | 4.0.6 | spring, MockMvc, WebTestClient |
| spring-security-test | spring-security-test | 6.4.1 | WithMockUser, spring.*security, auth.*test |
| fluent-assertions | kotest-assertions-core | 5.9.1 | kotest, shouldBe |
| testcontainers | postgresql | 1.20.4 | testcontainers, docker.*test, postgresql.*test |

#### 2.4.c Plugins build-system

| Plugin | Version | Role |
|---|---|---|
| jacoco | built-in-gradle |  |
<!-- LIBS_CATALOG_END -->

## 3. Init Commands (idempotent)

Configuration `build.gradle.kts` (ajouter aux deps + plugins existants) :

```kotlin
plugins {
    kotlin("jvm") version "1.9.+"
    jacoco
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit5:1.9.0")
    testImplementation("io.mockk:mockk:1.13.10")
    // Si Spring Boot
    // testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
    classDirectories.setFrom(
        files(classDirectories.files.map {
            fileTree(it) {
                exclude("**/generated/**", "**/dto/**")
            }
        })
    )
}

jacoco {
    toolVersion = "0.8.11"
}

tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit {
                minimum = "0.80".toBigDecimal()
            }
        }
    }
}
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis kotlin-junit.libs.json -- ne pas editer (utiliser sync_stack_md.py).
# Gradle managed via build.gradle.kts + gradle/libs.versions.toml.
# Versions auto-derivees de kotlin-junit.libs.json -- regenerer le catalog Gradle
# en cas de bump (cf. gradle/libs.versions.toml).
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis kotlin-junit.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: spring-test
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("org.springframework.boot:spring-boot-starter-test:4.0.6")

# capability: spring-security-test
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("org.springframework.security:spring-security-test:6.4.1")

# capability: fluent-assertions
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("io.kotest:kotest-assertions-core:5.9.1")

# capability: testcontainers
# Gradle : ajouter les modules en implementation(...) dans build.gradle.kts
#   implementation("org.testcontainers:postgresql:1.20.4")
```
<!-- ONDEMAND_PACKAGES_END -->

Création du dossier test (idempotent) :

```bash
mkdir -p workspace/output/src/{BackendName}/src/test/kotlin
```

---

## 4. Project structure

```
workspace/output/src/{BackendName}/
├── build.gradle.kts
├── src/
│   ├── main/kotlin/
│   │   └── com/{Org}/{App}/
│   │       ├── service/AuthService.kt
│   │       └── controller/AuthController.kt
│   └── test/kotlin/
│       └── com/{Org}/{App}/
│           ├── service/AuthServiceTest.kt
│           └── controller/AuthControllerTest.kt
```

---

## 5. Test patterns

### 5.1 Service test (MockK)

```kotlin
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Test
import kotlin.test.assertNotNull
import kotlin.test.assertEquals

class AuthServiceTest {
    private val userRepo: UserRepository = mockk()
    private val sut = AuthService(userRepo)

    @Test
    fun `login with valid credentials returns token`() = runBlocking {
        // Arrange
        coEvery { userRepo.findByEmail("user@test.com") } returns User(1, "user@test.com")

        // Act
        val result = sut.login("user@test.com", "pass")

        // Assert
        assertNotNull(result)
        assertNotNull(result.token)
        coVerify(exactly = 1) { userRepo.findByEmail("user@test.com") }
    }
}
```

### 5.2 Spring Boot integration test

```kotlin
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.boot.test.web.client.TestRestTemplate
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.http.HttpStatus
import org.junit.jupiter.api.Test
import kotlin.test.assertEquals

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthControllerIntegrationTest {

    @Autowired
    lateinit var restTemplate: TestRestTemplate

    @Test
    fun `POST login with invalid credentials returns 401`() {
        val response = restTemplate.postForEntity(
            "/api/auth/login",
            mapOf("email" to "wrong", "password" to "wrong"),
            String::class.java
        )
        assertEquals(HttpStatus.UNAUTHORIZED, response.statusCode)
    }
}
```

---

## 6. Run commands

### 6.1 Test command

```bash
cd workspace/output/src/{BackendName}
./gradlew test
```

### 6.2 Coverage command

```bash
cd workspace/output/src/{BackendName}
./gradlew test jacocoTestReport
```

### 6.3 Linter

```bash
cd workspace/output/src/{BackendName}
./gradlew ktlintCheck
# OU
./gradlew detekt
```

---

## 7. Coverage output format

Format : **JaCoCo XML**
Path : `workspace/output/src/{BackendName}/build/reports/jacoco/test/jacocoTestReport.xml`

Le script `parse_coverage.py` parse ce format via `Parse-JaCoCoXml`.

---

## 8. Naming conventions

- Fichiers : `{ClassName}Test.kt` (suffixe `Test`)
- Classes : `{ClassName}Test` ou `{ClassName}FEAT`
- Méthodes : conventions Kotlin permettent les noms en backticks lisibles
  - Ex. : `` `login with valid credentials returns token` ``
  - Alt. : `loginWithValidCredentialsReturnsToken`

---

## 9. Forbidden patterns

- `Thread.sleep(...)` — utiliser `delay()` avec `runBlockingTest` ou
  `kotlinx-coroutines-test`
- Connexion à une vraie DB — utiliser `@DataJpaTest` ou Testcontainers
- État partagé via `companion object` mutable
- `@Disabled` sans raison documentée
