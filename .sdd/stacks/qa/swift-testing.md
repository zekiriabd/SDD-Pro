# QA Stack — Swift Testing + XCUITest + xccov

> §2.4 (Librairies) régénérée depuis `swift-testing.libs.json` — ne pas éditer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id swift-testing`).

Status: Experimental
Validation: 🟡 experimental — Stack QA construit le 2026-09-02 en accompagnement de `mobiles/swiftui`. Chaque paquet résolu contre l'API GitHub Releases. **Jamais exécuté**, et non exécutable depuis l'environnement de construction : `xcodebuild` exige un **hôte macOS avec Xcode**, exactement comme le stack applicatif. Non supporté commercialement en l'état.
QA FEAT ID: swift-testing
Scope: tests unitaires, de vue, snapshot et UI pour le stack `mobiles/swiftui`

---

## 1. Scope

Tests pour applications iOS matérialisées sous `workspace/src/{AppName}/`
avec le stack `mobiles/swiftui.md`.

Quatre niveaux, du moins au plus coûteux :

| Niveau | Runner | Cible | Vitesse |
|---|---|---|---|
| **Unitaire** | **Swift Testing** (toolchain) | services, mappers, ViewModels `@Observable` | ms |
| **Vue** | Swift Testing + `ViewInspector` (capability `view-introspection`) | structure d'une vue SwiftUI | ms |
| **Snapshot** | `swift-snapshot-testing` (capability `snapshot-tests`) | rendu pixel d'une vue | s |
| **UI** | **XCUITest** (SDK) | app complète sur simulateur | min |

> **Prérequis** : **hôte macOS + Xcode 26**. Ce stack QA n'est pas exécutable
> ailleurs — il hérite de la contrainte d'hôte de `mobiles/swiftui.md §2.1`.

---

## 2. Tooling

### 2.1 Test runner — **fourni par la toolchain**

**Swift Testing** est intégré à Swift 6. Aucune dépendance à déclarer :

```swift
import Testing

@Suite("UserService")
struct UserServiceTests {
    @Test("remonte les utilisateurs de l'API")
    func fetchesUsers() async throws { ... }
}
```

`XCTest` (assertions historiques) et `XCUITest` (tests UI) viennent du SDK.
Aucun des trois n'a de coordonnée SwiftPM — c'est pourquoi ils **n'apparaissent
pas** en §2.4, et pourquoi `core` y est **vide** (`metadata.manualInstall: true`
est déclaré dans le catalog pour rendre cette absence explicite plutôt que
suspecte).

> **Swift Testing plutôt que XCTest** pour tout code neuf : `#expect` produit un
> message d'échec qui montre les valeurs, les suites sont des `struct` (donc un
> état neuf par test, sans `setUp`/`tearDown`), et les tests paramétrés
> (`@Test(arguments:)`) remplacent les boucles écrites à la main. XCTest reste
> requis pour XCUITest, qui n'a pas encore d'équivalent.

### 2.2 Coverage tool — **fourni par la toolchain**

```bash
xcodebuild test -scheme {AppName} -enableCodeCoverage YES \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -resultBundlePath TestResults.xcresult

xcrun xccov view --report --json TestResults.xcresult > coverage.json
```

Le coverage est produit par `llvm-cov` via Xcode. Aucune dépendance.
**Le coverage doit être activé sur le scheme** — c'est la seule action
d'installation qui incombe à `arch` pour ce stack (cf. §3).

### 2.3 Mock library — **le langage suffit**

Swift n'a pas de mocking par réflexion (pas d'équivalent de MockK ou Mockito) :
la voie idiomatique est le **protocol witness**. Le stack applicatif l'anticipe
en imposant `protocol {Name}Service` + `Live{Name}Service`
(`mobiles/swiftui.md §2.5`) :

```swift
struct MockUserService: UserService {
    var result: Result<[User], Error> = .success([])
    func fetchAll() async throws -> [User] { try result.get() }
}
```

C'est **plus verbeux** qu'un framework de mocking, et c'est le compromis
assumé : le compilateur vérifie que le mock respecte le contrat. Un mock qui
dérive de son protocole ne compile pas.

Pour le réseau, la capability `http-stubbing` (`Mocker`) intercepte
`URLSession` au niveau `URLProtocol` — c'est le complément direct du choix
`URLSession` du stack applicatif.

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/qa/swift-testing.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id swift-testing`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| snapshot-tests | pointfreeco/swift-snapshot-testing | 1.19.4 | snapshot, regression.*visuelle, test.*rendu, test.*vue |
| view-introspection | nalexn/ViewInspector | 0.10.3 | inspecter.*vue, assertion.*hierarchie, viewinspector, test.*unitaire.*vue |
| diff-assertions | pointfreeco/swift-custom-dump | 1.7.3 | diff.*lisible, comparaison.*structure, custom-dump |
| http-stubbing | WeTransfer/Mocker | 3.0.2 | mock.*http, stub.*reseau, test.*apiclient, mocker |
| http-stubbing | AliSoftware/OHHTTPStubs (alt) | 9.1.0 | ohhttpstubs |
| assertions | Quick/Nimble (alt) | 14.0.0 | nimble, matchers, assertions.*expressives |
| assertions | Quick/Quick (alt) | 7.6.2 | quick, bdd, describe.*it |
<!-- LIBS_CATALOG_END -->

---

## 3. Init Commands (idempotent)

```bash
# STEP 0 — Gate d'hote (identique au stack applicatif)
if [ "$(uname)" != "Darwin" ]; then
  echo "ERROR: qa {AppName} — stack swift-testing non executable"
  echo "CAUSE: [INFRA_BLOCKED] hote $(uname) — Xcode requis (macOS uniquement)"
  echo "FIX: executer la phase QA sur un hote macOS avec Xcode 26+"
  exit 3
fi

APP=workspace/src/{AppName}

# STEP 1 — Arborescence de test (miroir de la source)
mkdir -p "$APP/{AppName}Tests"/{Core,Features,Helpers} \
         "$APP/{AppName}UITests"

# STEP 2 — Aucune librairie a installer (cf. 2.1 / metadata.manualInstall)
#   Le runner et le coverage viennent de la toolchain. La SEULE action
#   d'installation est d'activer le code coverage sur le scheme :
#     Xcode > Scheme > Edit Scheme > Test > Options > Code Coverage : coche
#   Cote fichier, cela correspond a `codeCoverageEnabled = "YES"` dans
#   {AppName}.xcodeproj/xcshareddata/xcschemes/{AppName}.xcscheme

# STEP 3 — Verification
(cd "$APP" && xcodebuild test -scheme {AppName} -enableCodeCoverage YES \
   -destination 'platform=iOS Simulator,name=iPhone 17')
```

---

## 4. Project structure

```
{AppName}/
├── {AppName}/Features/User/Services/UserService.swift
└── {AppName}Tests/Features/User/UserServiceTests.swift      ← miroir

├── {AppName}Tests/
│   ├── Core/
│   │   ├── Network/APIClientTests.swift
│   │   └── Storage/KeychainStoreTests.swift
│   ├── Features/{Feature}/
│   │   ├── {Name}ServiceTests.swift
│   │   └── {Name}ViewModelTests.swift
│   ├── Helpers/
│   │   ├── Mocks/Mock{Name}Service.swift    ── protocol witnesses
│   │   └── Fixtures/{Name}+Fixture.swift    ── donnees de test
│   └── __Snapshots__/                       ── references (capability snapshot-tests)
└── {AppName}UITests/
    └── {Flow}UITests.swift                  ── XCUITest
```

---

## 5. Test patterns

### 5.1 Service (Swift Testing + protocol witness)

```swift
import Testing

@Suite("FetchUsers")
struct FetchUsersTests {
    @Test("remonte la liste du repository")
    func returnsUsers() async throws {
        let service = MockUserService(result: .success([User(id: "1", name: "Ada")]))
        let sut = FetchUsers(service: service)

        let users = try await sut()

        #expect(users.count == 1)
        #expect(users.first?.name == "Ada")
    }

    @Test("propage l'erreur du repository")
    func propagatesError() async {
        let service = MockUserService(result: .failure(APIError.unauthorized))
        let sut = FetchUsers(service: service)

        await #expect(throws: APIError.unauthorized) { try await sut() }
    }
}
```

### 5.2 Test paramétré (remplace les boucles écrites à la main)

```swift
@Test("rejette les emails invalides", arguments: ["", "a@", "@b.com", "a b@c.com"])
func rejectsInvalidEmails(_ input: String) {
    #expect(EmailValidator.validate(input) == false)
}
```

Chaque argument est rapporté comme un cas distinct : l'échec nomme la valeur
fautive, ce qu'une boucle `for` masquerait.

### 5.3 ViewModel `@MainActor`

Le stack applicatif impose `@MainActor` sur les ViewModels
(`mobiles/swiftui.md §1.4`) ; la suite de test doit donc l'être aussi, sinon
Swift 6 refuse de compiler l'accès à l'état.

```swift
@Suite("UserListViewModel")
@MainActor
struct UserListViewModelTests {
    @Test("passe en .loaded apres chargement")
    func loadsUsers() async throws {
        let sut = UserListViewModel(service: MockUserService(result: .success([])))

        await sut.load()

        #expect(sut.state == .loaded([]))
    }
}
```

### 5.4 Snapshot (capability `snapshot-tests`)

```swift
import SnapshotTesting
import XCTest   // snapshot-testing s'appuie sur XCTest

final class UserCardSnapshotTests: XCTestCase {
    func testUserCard() {
        let view = UserCard(user: User(id: "1", name: "Ada"))
        assertSnapshot(of: view, as: .image(layout: .device(config: .iPhone13)))
    }
}
```

> **Fixer explicitement le device et le style** : un snapshot pris sur un
> simulateur puis rejoué sur un autre échoue pour une différence d'échelle,
> pas de code. Fixer aussi le mode clair/sombre et la taille de Dynamic Type.

### 5.5 UI (XCUITest)

```swift
final class LoginUITests: XCTestCase {
    func testLoginFlow() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTesting"]   // permet a l'app de stubber son reseau
        app.launch()

        app.textFields["emailField"].tap()
        app.textFields["emailField"].typeText("ada@example.com")
        app.buttons["loginButton"].tap()

        XCTAssertTrue(app.staticTexts["welcomeLabel"].waitForExistence(timeout: 5))
    }
}
```

> `accessibilityIdentifier` sur chaque élément ciblé — **jamais** de sélection
> par le libellé affiché, qui casse à la première traduction.

---

## 6. Run commands

### 6.1 Test command

```bash
(cd workspace/src/{AppName} && xcodebuild test -scheme {AppName} \
   -destination 'platform=iOS Simulator,name=iPhone 17')

# Cibler une suite
(cd workspace/src/{AppName} && xcodebuild test -scheme {AppName} \
   -destination 'platform=iOS Simulator,name=iPhone 17' \
   -only-testing:{AppName}Tests/FetchUsersTests)

# Exclure les tests UI (lents) de la boucle de dev
(cd workspace/src/{AppName} && xcodebuild test -scheme {AppName} \
   -destination 'platform=iOS Simulator,name=iPhone 17' \
   -skip-testing:{AppName}UITests)
```

### 6.2 Coverage command

```bash
(cd workspace/src/{AppName} && xcodebuild test -scheme {AppName} \
   -enableCodeCoverage YES \
   -destination 'platform=iOS Simulator,name=iPhone 17' \
   -resultBundlePath TestResults.xcresult)

# Rapport global
xcrun xccov view --report TestResults.xcresult

# JSON exploitable pour un seuil
xcrun xccov view --report --json TestResults.xcresult > coverage.json
```

Le rapport `xccov` porte sur les **targets**. Restreindre au target applicatif
`{AppName}` : inclure les targets de test dans le calcul gonfle artificiellement
le taux (le code de test est couvert par construction).

### 6.3 Linter

```bash
(cd workspace/src/{AppName} && swiftlint --strict)
(cd workspace/src/{AppName} && swift-format lint --strict --recursive {AppName})
```

---

## 7. Coverage output format

- **Bundle** : `workspace/src/{AppName}/TestResults.xcresult`
- **Rapport** : `xcrun xccov view --report --json` → JSON
- **Format** : propriétaire Apple — **pas de lcov nativement**
- **Seuil** : cf. `rules/quality.md §A` (verdict 🟢/🟡/🔴)

> **Écart à connaître** : contrairement à `qa/flutter-test` (lcov), `qa/node-vitest`
> (lcov) ou `qa/dotnet-xunit` (cobertura), ce stack ne produit **pas** un format
> standard. Pour l'agréger avec d'autres stacks dans un même tableau de bord, il
> faut convertir le JSON `xccov` — c'est une étape à prévoir, pas un acquis.
> Restreindre le calcul au target `{AppName}` (§6.2).

---

## 8. Naming conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Fichier de test | miroir de la source + `Tests.swift` | `{AppName}Tests/Features/User/UserServiceTests.swift` |
| Suite | `@Suite("{SujetTeste}")` sur une `struct` | `@Suite("FetchUsers")` |
| Cas de test | `@Test("phrase decrivant le comportement")` | `@Test("propage l'erreur du repository")` |
| Mock | `Mock{Protocol}` dans `Helpers/Mocks/` | `MockUserService` |
| Fixture | `{Type}+Fixture.swift` | `User+Fixture.swift` |
| Snapshot | `__Snapshots__/{Suite}/{test}.png` | `__Snapshots__/UserCardSnapshotTests/testUserCard.png` |
| Test UI | `{Flow}UITests.swift` (classe `XCTestCase`) | `LoginUITests.swift` |
| Identifiant d'accessibilité | `{element}{Type}` en camelCase | `emailField`, `loginButton` |

---

## 9. Forbidden patterns

- `XCTest` pour du code neuf non-UI — utiliser Swift Testing (§2.1)
- Suite de test d'un ViewModel `@MainActor` sans `@MainActor` sur la suite — ne compile pas en Swift 6
- `XCTAssertTrue(x == y)` — utiliser `#expect(x == y)`, qui affiche les valeurs
- `!` / `try!` dans un test — utiliser `try #require(...)`, qui échoue proprement
- `sleep()` ou `Thread.sleep` pour attendre — utiliser `await`, ou `waitForExistence(timeout:)` en XCUITest
- Appel réseau réel dans un test unitaire — injecter un mock, ou la capability `http-stubbing`
- Sélection d'un élément XCUITest par son libellé affiché — utiliser `accessibilityIdentifier`
- Snapshot sans device ni style fixés (§5.4) — échec dépendant de la machine
- Référence de snapshot non committée, ou régénérée sans relecture du diff
- Coverage calculé en incluant les targets de test (§6.2)
- `Mockito`/`MockK`-like : aucun framework de mocking par réflexion — utiliser les protocol witnesses (§2.3)
- Test avec `#expect(true)` ou sans assertion
- `.disabled()` sur un test sans ticket référencé en commentaire
- Test dépendant de l'ordre d'exécution — une suite `struct` a un état neuf par test, ne pas contourner avec du `static var`

---

## 10. Rattachement aux stacks applicatifs

| Stack applicatif | Stack QA |
|---|---|
| `mobiles/swiftui` | **`qa/swift-testing`** (ce fichier) |

Ce stack QA n'a de sens que pour `mobiles/swiftui`. Le runner est indissociable
de la toolchain Swift et du SDK Apple.
