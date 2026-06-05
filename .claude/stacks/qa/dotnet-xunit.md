# QA Stack — .NET xUnit + Coverlet

> §2.4 (Librairies) régénérée depuis `dotnet-xunit.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id dotnet-xunit`).

Status: Stable
Validation: 🟢 reference (validated combo — dotnet-minimalapi + blazor + radzen + azure-ad)
QA FEAT ID: dotnet-xunit
Scope: tests unitaires backend .NET (ASP.NET Core, Minimal API)

---

## 1. Scope

Tests unitaires pour backends .NET (ASP.NET Core, Minimal API, etc.).
S'applique aux projets `workspace/output/src/{BackendName}/` typés .NET.

Pour les projets Blazor frontend, utiliser `qa/blazor-bunit.md`.

---

## 2. Tooling

### 2.1 Test runner
- **xUnit** (`xunit`, `xunit.runner.visualstudio`)

### 2.2 Coverage tool
- **Coverlet** (`coverlet.collector`) — output Cobertura XML par défaut
- Output natif : `workspace/output/src/{BackendName}.Tests/TestResults/{guid}/coverage.cobertura.xml`

### 2.3 Mock library
- **NSubstitute** (recommandé) ou **Moq**
- Test doubles via DI (les services prod sont enregistrés via interface)

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/dotnet-xunit.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id dotnet-xunit`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| xunit | 2.9.2 |  |
| xunit.runner.visualstudio | 3.0.0 |  |
| Microsoft.NET.Test.Sdk | 17.12.0 |  |
| coverlet.collector | 6.0.2 |  |
| NSubstitute | 5.3.0 |  |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| mocking-alt | Moq (alt) | 4.20.72 | moq |
| fluent-assertions | FluentAssertions | 7.0.0 | fluentassertions, should\(\) |
| api-tests | Microsoft.AspNetCore.Mvc.Testing | 10.0.6 | api.*test, WebApplicationFactory, integration.*http, qa.*api-tests |
| api-tests | Microsoft.EntityFrameworkCore.InMemory | 10.0.6 | api.*test, in-?memory.*db, integration.*http, qa.*api-tests |
<!-- LIBS_CATALOG_END -->

## 3. Init Commands (idempotent)

Si `workspace/output/src/{BackendName}.Tests/` n'existe pas :

```bash
dotnet new xunit -o workspace/output/src/{BackendName}.Tests
dotnet sln workspace/output/src/{AppName}.sln add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj reference workspace/output/src/{BackendName}/{BackendName}.csproj
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis dotnet-xunit.libs.json -- ne pas editer (utiliser sync_stack_md.py).
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package xunit --version 2.9.2
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package xunit.runner.visualstudio --version 3.0.0
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package Microsoft.NET.Test.Sdk --version 17.12.0
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package coverlet.collector --version 6.0.2
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package NSubstitute --version 5.3.0
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis dotnet-xunit.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: mocking-alt
# OU (alt mutuellement exclusif) : dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package Moq --version 4.20.72

# capability: fluent-assertions
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package FluentAssertions --version 7.0.0

# capability: api-tests
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package Microsoft.AspNetCore.Mvc.Testing --version 10.0.6
dotnet add workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj package Microsoft.EntityFrameworkCore.InMemory --version 10.0.6
```
<!-- ONDEMAND_PACKAGES_END -->

Skip si `{BackendName}.Tests.csproj` déjà présent (idempotence).

---

## 4. Project structure

```
workspace/output/src/{BackendName}.Tests/
├── {BackendName}.Tests.csproj
├── Services/
│   └── AuthServiceTests.cs           # 1 fichier par service à tester
├── Endpoints/
│   └── AuthEndpointsTests.cs         # 1 fichier par groupe d'endpoints
├── Validators/
│   └── LoginInputValidatorTests.cs   # 1 fichier par validator
├── Mappers/
│   └── UserMapperTests.cs            # 1 fichier par mapper
└── Fixtures/
    └── DbContextFixture.cs           # Fixtures partagées (in-memory)
```

---

## 5. Test patterns (Arrange / Act / Assert)

### 5.1 Service test (mock dependencies)

```csharp
public class AuthServiceTests
{
    private readonly IUserRepository _userRepo;
    private readonly AuthService _sut;

    public AuthServiceTests()
    {
        _userRepo = Substitute.For<IUserRepository>();
        _sut = new AuthService(_userRepo);
    }

    [Fact]
    public async Task Login_WithValidCredentials_ReturnsToken()
    {
        // Arrange
        var input = new LoginInput("user@test.com", "pass");
        _userRepo.FindByEmailAsync(input.Email)
                 .Returns(new User { Id = 1, Email = input.Email });

        // Act
        var result = await _sut.LoginAsync(input);

        // Assert
        result.Should().NotBeNull();
        result.Token.Should().NotBeNullOrEmpty();
    }
}
```

### 5.2 Endpoint test (WebApplicationFactory)

```csharp
public class AuthEndpointsTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public AuthEndpointsTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task POST_Login_WithInvalidCreds_Returns401()
    {
        // Arrange & Act
        var response = await _client.PostAsJsonAsync("/api/auth/login",
            new { email = "wrong", password = "wrong" });

        // Assert
        response.StatusCode.Should().Be(HttpStatusCode.Unauthorized);
    }
}
```

---

## 6. Run commands

### 6.1 Test command

```bash
dotnet test workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj \
  --collect:"XPlat Code Coverage" \
  --logger "trx;LogFileName=test-results.trx" \
  --results-directory workspace/output/src/{BackendName}.Tests/TestResults
```

### 6.2 Coverage command

Coverlet est activé automatiquement par `--collect:"XPlat Code Coverage"`.
Pas de commande séparée.

### 6.3 Linter (optionnel)

```bash
dotnet format workspace/output/src/{BackendName}.Tests/{BackendName}.Tests.csproj --verify-no-changes
```

---

## 7. Coverage output format

Format : **Cobertura XML**
Path : `workspace/output/src/{BackendName}.Tests/TestResults/{guid}/coverage.cobertura.xml`

Le script `parse_coverage.py` détecte automatiquement ce format et le
parse vers le schéma normalisé.

---

## 8. Naming conventions

- **Classes de test** : `{ClassName}Tests` (ex. `AuthServiceTests`)
- **Méthodes de test** : `{Method}_{Scenario}_{ExpectedResult}`
  - Ex. : `Login_WithValidCredentials_ReturnsToken`
  - Ex. : `RefreshToken_WithExpiredToken_Returns401`

---

## 9. Forbidden patterns dans les tests

- `Thread.Sleep(...)` — utiliser `Task.Delay` ou des fakes de temps
- Connexion à une DB réelle — utiliser EF InMemory ou fixtures
- État partagé entre tests (statique) — chaque test isolé
- `[Fact]` sans body
