# QA Stack — Flutter Test + Mocktail + coverage natif

> §2.4 (Librairies) régénérée depuis `flutter-test.libs.json` — ne pas éditer manuellement (`python .sdd/python/sdd_admin/sync_stack_md.py --stack-id flutter-test`).

Status: Experimental
Validation: 🟡 experimental — Stack QA construit le 2026-09-02 en accompagnement de `mobiles/flutter`. Chaque paquet résolu contre l'API pub.dev ; deux paquets couramment recommandés ont été **écartés** sur la base de leurs métadonnées (cf. §2.5). **Jamais exécuté** : aucun `flutter test` n'a tourné en CI (SDK Flutter absent de l'environnement). Non supporté commercialement en l'état.
QA FEAT ID: flutter-test
Scope: tests unitaires, widget, golden et E2E pour le stack `mobiles/flutter`

---

## 1. Scope

Tests pour applications Flutter matérialisées sous `workspace/src/{AppName}/`
avec le stack `mobiles/flutter.md`.

Quatre niveaux, du moins au plus coûteux :

| Niveau | Runner | Cible | Vitesse |
|---|---|---|---|
| **Unitaire** | `flutter_test` (SDK) | use cases, repositories, mappers — Dart pur | ms |
| **Widget** | `flutter_test` (SDK) | un widget isolé dans un arbre minimal | ms |
| **Golden** | `alchemist` (capability `golden-tests`) | rendu pixel d'un widget | s |
| **E2E** | `integration_test` (SDK) + `patrol` (capability `e2e-native`) | app complète sur device / émulateur | min |

> **Prérequis** : projet Flutter avec `pubspec.yaml`, SDK Flutter ≥ 3.47
> (contrainte du stack applicatif, cf. `mobiles/flutter.md §2.3`).

---

## 2. Tooling

### 2.1 Test runner — **natif, aucune dépendance**

`flutter_test` est fourni par le SDK. Il se déclare **sans version** :

```yaml
dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter
```

C'est la raison pour laquelle le runner **n'apparaît pas** en §2.4 : il n'a pas
de version pub, donc pas de coordonnée que `validate_libs_catalog.py` puisse
vérifier. Même situation que `swift-testing` sur `qa/swift-testing.md`.

### 2.2 Coverage tool — **natif, aucune dépendance**

```bash
flutter test --coverage      # -> coverage/lcov.info
```

Le format produit est du **lcov** standard, directement consommable par la
chaîne de coverage SDD_Pro (cf. `rules/quality.md §A`). Le paquet `coverage`
(capability `coverage-tooling`) ne sert qu'au **post-traitement** — exclure le
code généré, fusionner plusieurs suites. Il n'est pas nécessaire pour produire
le rapport.

> **Exclusion obligatoire du code généré** : un projet `mobiles/flutter` commite
> ses `*.freezed.dart` et `*.g.dart` (cf. `mobiles/flutter.md §5`). Sans
> filtrage, ils sont comptés dans le dénominateur et **font mécaniquement
> chuter le taux** alors qu'aucune ligne écrite à la main n'est en cause.
> Cf. §6.2.

### 2.3 Mock library

**Mocktail** — sans codegen. Retenu plutôt que `mockito`, qui exige un passage
de `build_runner` par classe mockée : sur un projet qui fait déjà tourner
`build_runner` pour Freezed et Riverpod, ajouter les mocks à cette chaîne
allonge chaque boucle TDD de plusieurs dizaines de secondes.

```dart
class MockUserRepository extends Mock implements UserRepository {}
```

---

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.sdd/stacks/qa/flutter-test.libs.json`. Ne pas editer cette section manuellement -- utiliser `.sdd/python/sdd_admin/sync_stack_md.py --stack-id flutter-test`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|
| mocktail | 1.0.5 | Mocking sans codegen (dev_dependency). Retenu plutot que mockito, qui impose un `build_runner` par classe mockee — friction inacceptable en TDD |

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| golden-tests | alchemist | 0.14.0 | golden, regression.*visuelle, snapshot.*widget, test.*rendu |
| e2e-native | patrol | 4.9.0 | tests.*e2e, test.*permission.*natif, patrol, dialogue.*systeme |
| e2e-native | patrol_finders | 3.6.0 | patrol, finders.*lisibles |
| bloc-testing | bloc_test | 10.0.0 | \bbloc\b, cubit, bloc_test |
| coverage-tooling | coverage | 1.15.1 | coverage.*seuil, exclure.*coverage, fusion.*coverage, lcov |
| dart-only-tests | test (alt) | 1.31.2 | package.*dart.*pur, test.*sans.*flutter |
<!-- LIBS_CATALOG_END -->

---

## 2.5 Paquets ecartes a la construction

Deux paquets reviennent systématiquement dans les recommandations publiques
sur le test Flutter. Leurs métadonnées pub.dev les disqualifient :

| Paquet | Métadonnée relevée (2026-09-02) | Décision |
|---|---|---|
| `golden_toolkit` 0.15.0 | **`isDiscontinued: true`** sur pub.dev | Écarté → `alchemist` |
| `network_image_mock` 2.1.1 | `environment.sdk: >=2.12.0 <3.0.0` | Écarté — **incompatible Dart 3**, ne résoudra jamais sur ce stack |

Pour remplacer `network_image_mock`, la voie supportée est d'injecter un
`HttpClient` factice via `HttpOverrides.runZoned`, ou de passer un
`NetworkImage` déjà résolu — sans dépendance.

---

## 3. Init Commands (idempotent)

```bash
if ! grep -q "flutter_test:" workspace/src/{AppName}/pubspec.yaml; then
  cd workspace/src/{AppName}

  # Runner + E2E : fournis par le SDK, declares SANS version
  flutter pub add --dev flutter_test --sdk flutter
  flutter pub add --dev integration_test --sdk flutter

  # Mocking (cf. 2.4.a)
  flutter pub add --dev mocktail:1.0.5

  # Arborescence de test, miroir de lib/
  mkdir -p test/{core,features} integration_test
fi

# Verification
(cd workspace/src/{AppName} && flutter test --coverage)
```

---

## 4. Project structure

L'arborescence de test **reflète** celle de `lib/` — c'est la convention
Flutter, et elle rend le fichier de test d'une unité trouvable sans recherche.

```
{AppName}/
├── lib/features/user/domain/usecases/fetch_users.dart
└── test/features/user/domain/usecases/fetch_users_test.dart   ← miroir

├── test/
│   ├── core/                    ── tests des services transverses
│   ├── features/{feature}/
│   │   ├── domain/              ── use cases (Dart pur, les plus rapides)
│   │   ├── data/                ── repositories, mappers de DTO
│   │   └── presentation/        ── widget tests + providers
│   └── helpers/
│       ├── test_helpers.dart    ── fakes partages, ProviderContainer
│       └── pump_app.dart        ── wrapper de montage (ProviderScope + MaterialApp)
├── test/goldens/                ── fichiers .png de reference (capability golden-tests)
└── integration_test/
    └── app_test.dart            ── parcours E2E
```

---

## 5. Test patterns

### 5.1 Use case (Dart pur — le plus rapide, à privilégier)

```dart
class MockUserRepository extends Mock implements UserRepository {}

void main() {
  late MockUserRepository repository;
  late FetchUsers useCase;

  setUp(() {
    repository = MockUserRepository();
    useCase = FetchUsers(repository);
  });

  test('remonte la liste renvoyee par le repository', () async {
    when(() => repository.fetchAll())
        .thenAnswer((_) async => const [User(id: '1', name: 'Ada')]);

    final result = await useCase();

    expect(result, hasLength(1));
    verify(() => repository.fetchAll()).called(1);
  });

  test('propage la Failure du repository', () async {
    when(() => repository.fetchAll()).thenThrow(const NetworkFailure());

    expect(useCase.call, throwsA(isA<NetworkFailure>()));
  });
}
```

### 5.2 Widget test avec override Riverpod

`ProviderScope(overrides:)` est le point d'injection : c'est ce qui permet de
tester un écran sans réseau.

```dart
void main() {
  testWidgets('affiche les utilisateurs recus', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          userListProvider.overrideWith((ref) async => const [User(id: '1', name: 'Ada')]),
        ],
        child: const MaterialApp(home: UserListScreen()),
      ),
    );

    // pump() ne suffit pas : le provider est asynchrone.
    await tester.pumpAndSettle();

    expect(find.text('Ada'), findsOneWidget);
  });
}
```

> **Piège le plus fréquent** : utiliser `pump()` au lieu de `pumpAndSettle()`
> après une opération asynchrone. Le test passe par intermittence selon la
> vitesse de la machine — un flake, pas un échec franc.

### 5.3 Golden test (capability `golden-tests`)

```dart
void main() {
  goldenTest(
    'UserCard rendu',
    fileName: 'user_card',
    builder: () => GoldenTestGroup(
      children: [
        GoldenTestScenario(
          name: 'defaut',
          child: const UserCard(user: User(id: '1', name: 'Ada')),
        ),
      ],
    ),
  );
}
```

Régénération des références : `flutter test --update-goldens`.

> Les goldens sont **dépendants de la plateforme** (rendu de police). Alchemist
> sépare les goldens « CI » (police bloc, déterministe) des goldens
> « plateforme ». Committer les goldens CI ; sinon toute machine dont le rendu
> de texte diffère fait échouer la suite.

### 5.4 E2E natif (capability `e2e-native`)

`integration_test` seul ne voit que l'arbre Flutter : il ne peut **pas**
interagir avec une boîte de dialogue de permission, qui est une vue système.
C'est exactement ce que `patrol` ajoute.

```dart
void main() {
  patrolTest('accorde la permission camera puis prend une photo', ($) async {
    await $.pumpWidgetAndSettle(const MyApp());
    await $(#takePhotoButton).tap();

    // Dialogue NATIF — hors de portee d'integration_test
    await $.native.grantPermissionWhenInUse();

    await $(#photoPreview).waitUntilVisible();
  });
}
```

---

## 6. Run commands

### 6.1 Test command

```bash
(cd workspace/src/{AppName} && flutter test)
(cd workspace/src/{AppName} && flutter test test/features/user)   # cible
(cd workspace/src/{AppName} && flutter test --reporter expanded)  # verbeux
```

### 6.2 Coverage command

```bash
(cd workspace/src/{AppName} && flutter test --coverage)

# Exclure le code genere AVANT tout calcul de seuil (cf. 2.2)
(cd workspace/src/{AppName} && dart run coverage:format_coverage \
   --lcov --in=coverage --out=coverage/lcov.info --report-on=lib \
   && lcov --remove coverage/lcov.info \
        '**/*.freezed.dart' '**/*.g.dart' '**/generated/**' \
        -o coverage/lcov.info)
```

Sans le `lcov --remove`, un projet Freezed + Riverpod affiche un taux
artificiellement bas : le code généré pèse souvent 30 à 50 % des lignes de
`lib/` et n'est jamais couvert directement.

### 6.3 E2E command

```bash
(cd workspace/src/{AppName} && flutter test integration_test)         # integration_test seul
(cd workspace/src/{AppName} && patrol test)                           # capability e2e-native
```

### 6.4 Linter

```bash
(cd workspace/src/{AppName} && flutter analyze --fatal-infos)
(cd workspace/src/{AppName} && dart format --set-exit-if-changed lib test)
```

---

## 7. Coverage output format

- **Fichier** : `workspace/src/{AppName}/coverage/lcov.info`
- **Format** : lcov (standard, consommé tel quel par la chaîne SDD_Pro)
- **Seuil** : cf. `rules/quality.md §A` (verdict 🟢/🟡/🔴)
- **Rapport HTML** (optionnel) : `genhtml coverage/lcov.info -o coverage/html`

Le dénominateur **doit** exclure `*.freezed.dart`, `*.g.dart` et `generated/`
(§6.2). Un seuil appliqué sans ce filtrage ne mesure pas la qualité des tests.

---

## 8. Naming conventions

| Rôle | Pattern | Exemple |
|---|---|---|
| Fichier de test | miroir de `lib/` + `_test.dart` | `test/features/user/domain/usecases/fetch_users_test.dart` |
| Groupe | `group('{ClasseSousTest}', ...)` | `group('FetchUsers', ...)` |
| Cas de test | phrase en français décrivant le comportement | `test('propage la Failure du repository', ...)` |
| Mock | `Mock{Type}` | `MockUserRepository` |
| Fake | `Fake{Type}` | `FakeUserRepository` |
| Helper | `test/helpers/{nom}.dart` | `test/helpers/pump_app.dart` |
| Golden | `test/goldens/{widget}.png` | `test/goldens/user_card.png` |
| E2E | `integration_test/{parcours}_test.dart` | `integration_test/login_test.dart` |

---

## 9. Forbidden patterns

- `pump()` au lieu de `pumpAndSettle()` après une opération asynchrone — **cause de flake n°1**
- `await Future.delayed(...)` dans un test pour « attendre » — utiliser `pumpAndSettle` / `fakeAsync`
- Appel réseau réel dans un test unitaire ou widget — injecter un mock via `ProviderScope(overrides:)`
- `mockito` sur ce stack — `mocktail` est le choix retenu (pas de codegen). Ne pas cumuler les deux
- `golden_toolkit` — **discontinued** (§2.5)
- `network_image_mock` — **incompatible Dart 3** (§2.5)
- Golden non committé, ou golden de plateforme committé à la place du golden CI
- `expect(true, true)` ou test sans assertion
- `skip: true` sans ticket référencé en commentaire
- Test dépendant de l'ordre d'exécution ou d'un état partagé — chaque test se monte dans `setUp`
- Coverage mesuré sans exclusion du code généré (§6.2)
- `print()` dans un test — la règle `avoid_print` s'applique aussi à `test/`
- Test E2E utilisé pour ce qu'un test unitaire couvrirait (des minutes contre des millisecondes)

---

## 10. Rattachement aux stacks applicatifs

| Stack applicatif | Stack QA |
|---|---|
| `mobiles/flutter` | **`qa/flutter-test`** (ce fichier) |

Ce stack QA n'a de sens que pour `mobiles/flutter`. Il ne s'applique à aucun
autre stack du catalogue : `flutter_test` est indissociable du SDK Flutter.
