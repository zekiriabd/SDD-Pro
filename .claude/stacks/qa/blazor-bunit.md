# QA Stack — Blazor bUnit + xUnit + Coverlet

> §2.4 (Librairies) régénérée depuis `blazor-bunit.libs.json` — ne pas éditer manuellement (`python .claude/python/sdd_admin/sync_stack_md.py --stack-id blazor-bunit`).

Status: Stable
Validation: 🟢 reference (validated combo — dotnet-minimalapi + blazor + radzen + azure-ad)
QA FEAT ID: blazor-bunit
Scope: tests unitaires composants Blazor (Server + WebAssembly)

---

## 1. Scope

Tests unitaires de composants Blazor (Server ou WebAssembly).
S'applique aux projets `workspace/output/src/{AppName}/` typés Blazor.

Pour les services / handlers .NET côté frontend, utiliser xUnit
classique au sein du même projet de test.

---

## 2. Tooling

### 2.1 Test runner
- **xUnit** (host des tests)
- **bUnit** (`bunit`, `bunit.web`) — rendu Blazor en mémoire

### 2.2 Coverage tool
- **Coverlet** (`coverlet.collector`)
- Output : Cobertura XML

### 2.3 Mock library
- **NSubstitute** ou **Moq**
- bUnit fournit `TestContext.Services.AddSingleton<...>` pour DI mock

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/blazor-bunit.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id blazor-bunit`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| bunit.web | 1.36.0 |  |
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
<!-- LIBS_CATALOG_END -->

## 3. Init Commands (idempotent)

Si `workspace/output/src/{AppName}.Tests/` n'existe pas :

```bash
dotnet new bunit -o workspace/output/src/{AppName}.Tests
dotnet sln workspace/output/src/{AppName}.sln add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj reference workspace/output/src/{AppName}/{AppName}.csproj
```

<!-- CORE_PACKAGES_START -->
```bash
# Auto-genere depuis blazor-bunit.libs.json -- ne pas editer (utiliser sync_stack_md.py).
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package bunit.web --version 1.36.0
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package xunit --version 2.9.2
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package xunit.runner.visualstudio --version 3.0.0
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package Microsoft.NET.Test.Sdk --version 17.12.0
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package coverlet.collector --version 6.0.2
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package NSubstitute --version 5.3.0
```
<!-- CORE_PACKAGES_END -->

<!-- ONDEMAND_PACKAGES_START -->
```bash
# Auto-genere depuis blazor-bunit.libs.json (on-demand) -- installe par dev-* si l'US declenche un trigger.
# capability: mocking-alt
# OU (alt mutuellement exclusif) : dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package Moq --version 4.20.72

# capability: fluent-assertions
dotnet add workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj package FluentAssertions --version 7.0.0
```
<!-- ONDEMAND_PACKAGES_END -->

> **Note** : si le template `bunit` n'est pas installé localement :
> `dotnet new install bunit.template` puis re-tenter.

---

## 4. Project structure

```
workspace/output/src/{AppName}.Tests/
├── {AppName}.Tests.csproj
├── Pages/
│   └── LoginTests.cs                 # 1 fichier par Page
├── Components/
│   └── HeaderTests.cs                # 1 fichier par Component
├── Layouts/
│   └── MainLayoutTests.cs            # 1 fichier par Layout
└── _Imports.razor                    # imports bunit
```

---

## 5. Test patterns (bUnit)

### 5.1 Component rendering test

```csharp
public class LoginTests : TestContext
{
    [Fact]
    public void Login_RendersEmailAndPasswordFields()
    {
        // Arrange (mock services if needed)
        var authService = Substitute.For<IAuthService>();
        Services.AddSingleton(authService);

        // Act
        var cut = RenderComponent<Login>();

        // Assert
        cut.Find("input[type=email]").Should().NotBeNull();
        cut.Find("input[type=password]").Should().NotBeNull();
        cut.Find("button[type=submit]").TextContent.Should().Be("Se connecter");
    }
}
```

### 5.2 Component event test

```csharp
[Fact]
public async Task Login_OnSubmit_CallsAuthService()
{
    // Arrange
    var authService = Substitute.For<IAuthService>();
    Services.AddSingleton(authService);

    var cut = RenderComponent<Login>();
    cut.Find("input[type=email]").Change("user@test.com");
    cut.Find("input[type=password]").Change("pass");

    // Act
    await cut.Find("form").SubmitAsync();

    // Assert
    await authService.Received(1).LoginAsync(
        Arg.Is<LoginInput>(i => i.Email == "user@test.com")
    );
}
```

---

## 6. Run commands

### 6.1 Test command

```bash
dotnet test workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj \
  --collect:"XPlat Code Coverage" \
  --logger "trx;LogFileName=test-results.trx" \
  --results-directory workspace/output/src/{AppName}.Tests/TestResults
```

### 6.2 Linter

```bash
dotnet format workspace/output/src/{AppName}.Tests/{AppName}.Tests.csproj --verify-no-changes
```

---

## 7. Coverage output format

Format : **Cobertura XML**
Path : `workspace/output/src/{AppName}.Tests/TestResults/{guid}/coverage.cobertura.xml`

---

## 8. Naming conventions

- Classes : `{ComponentName}Tests` (ex. `LoginTests`)
- Méthodes : `{Component}_{Scenario}_{ExpectedResult}`
  - Ex. : `Login_RendersEmailAndPasswordFields`
  - Ex. : `Header_ShowsLogoutButton_WhenAuthenticated`

---

## 9. Forbidden patterns

- `Thread.Sleep` dans les tests — utiliser `WaitForState`/`WaitForAssertion` de bUnit
- Tests avec backend HTTP réel — utiliser `MockHttpMessageHandler`
- Tests qui dépendent de l'ordre d'exécution
