# Règle — QA Ownership

## Principe

L'**agent QA** est le **propriétaire exclusif** des fichiers de test du
projet (tests unitaires uniquement). Aucun autre agent (PO, Arch,
dev-backend, dev-frontend, elicitor) ne peut générer, augmenter,
modifier ou supprimer un fichier de test.

Symétriquement, l'agent QA **NE PEUT PAS** modifier le code de
production sous `workspace/output/src/{App|Backend|Frontend|*Lib}/`. Il le lit en
**read-only**, écrit ses propres tests dans des projets adjacents
(`*.Tests/`, `__tests__/`, etc.), et produit ses rapports.

Cette règle est le pendant SDD_Pro de `qa-ownership.md` SDD_Lite.

---

## 1. Patterns de fichiers de test (propriété exclusive QA)

Quel que soit le langage / framework, ces patterns appartiennent à
l'agent QA :

| Convention | Exemples |
|---|---|
| `*.Tests/**/*` | Projet xUnit / NUnit / MSTest / bUnit (.NET) |
| `**/__tests__/**` | Vitest / Jest (Node) |
| `**/*.spec.ts` `*.spec.tsx` `*.spec.js` `*.spec.jsx` | Jasmine (Angular) / Jest |
| `**/*.test.ts` `*.test.tsx` `*.test.js` `*.test.jsx` | Vitest / Jest |
| `**/*Tests.cs` | xUnit / NUnit hors projet `*.Tests` |
| `**/test_*.py` `**/*_test.py` | pytest / unittest |
| `**/*Test.kt` `**/*Spec.kt` | JUnit 5 / Kotest (Kotlin) |
| `**/src/test/kotlin/**` | Convention Gradle Kotlin |

Tout fichier dont le chemin matche l'un de ces patterns est **propriété
exclusive** de l'agent QA.

---

## 2. Scope autorisé — Agent QA

### 2.1 Création et augmentation de fichiers de test

- **Créer** un projet de test adjacent au code production (ex.
  `workspace/output/src/{BackendName}.Tests/` pour .NET, `__tests__/` pour Node)
- **Créer** des fichiers individuels matchant les patterns du §1
- **Augmenter** un fichier de test existant (régénération idempotente)
- **Configurer** le harness (`vitest.config.ts`, `xunit.runner.json`,
  `pytest.ini`, `coverlet.runsettings`, `karma.conf.js`,
  `build.gradle.kts` test deps) — fichiers dédiés aux tests

### 2.2 Lecture du code de production

L'agent QA **lit** `workspace/output/src/` en read-only. Il N'OUVRE JAMAIS Write
/ Edit sur ces fichiers (hors patterns §1). Lit aussi :
- `workspace/input/specs/{n}-*.md` (SPEC pour ACs)
- `workspace/output/us/{n}-*.md` (US ciblées)
- `workspace/input/ui/{n}-*.html` (mockup HTML si présent, passif)
- `workspace/output/db/schema.json` (pour fixtures de test si DB)
- `workspace/output/context/constitution.md` (passif, glossaire)

### 2.3 Exécution de commandes

- **Test commands** déclarées en §6 du QA stack actif
- **Coverage commands** déclarées en §6 du QA stack actif
- **Init commands** déclarées en §3 du QA stack actif (bootstrap test
  project)
- Scripts PowerShell `parse-coverage.ps1` et `quality-scan.ps1`

### 2.4 Écriture des artefacts QA

Sous `workspace/output/qa/feat-{n}/` :
- `report.md` — rapport consolidé (humain)
- `coverage.json` — métriques normalisées (cf. `qa-coverage.md §2`)
- `quality.json` — résultats du quality scan (sonar-like)

---

## 3. Scope interdit — Agent QA

### 3.1 Modifier le code de production

Aucun Write / Edit / MultiEdit sur `workspace/output/src/{App|Backend|Frontend|*Lib}/**`
HORS des patterns §1.

**Exception unique** : créer le dossier d'un projet de test adjacent
(ex. `dotnet new xunit -o workspace/output/src/{BackendName}.Tests`). Cette
création est autorisée car le dossier `*.Tests/` est intrinsèquement
propriété QA.

### 3.2 Auto-correction de défauts détectés

Si un test échoue à cause d'un bug dans le code production, l'agent QA
N'A PAS LE DROIT de le corriger lui-même. Il :
1. Reporte l'échec dans `report.md` avec classe `[QA_TEST_FAILED]`
2. Marque la décision globale `RED`
3. Le Tech Lead décide de re-dispatcher la task vers dev-backend ou
   dev-frontend (hors scope QA)

### 3.3 Générer du code métier

Aucune classe métier, aucun service, aucun composant UI. Les helpers
de test (fixtures, mocks, factories, builders) sont autorisés
**uniquement dans le projet de test**, jamais dans le code production.

### 3.4 Modifier la SPEC, les US, les mockups HTML

Read-only strict sur `workspace/input/specs/`, `workspace/output/us/`, `workspace/input/ui/`. Si une
AC est mal formulée, le signaler dans `report.md §recommandations`.

### 3.5 Modifier `constitution.md`, ADRs, schema DB

Read-only strict sur `workspace/output/context/`, `workspace/output/db/`.

---

## 4. Scope interdit — Tous les autres agents

### 4.1 Patterns de fichiers interdits

Les agents `po`, `arch`, `dev-backend`, `dev-frontend`, `elicitor`
ne peuvent **ni `create` ni `augment`** aucun fichier matchant les
patterns §1.

### 4.2 Détection au scan forbidden content

Pour les agents dev-* (qui sont le risque principal de violation), au
STEP forbidden content de leur prompt :

```
Pour chaque fichier que l'agent s'apprête à écrire :
  Si path match l'un des patterns de qa-ownership.md §1 :
    STOP + ERROR
    CAUSE: [QA_OWNERSHIP_VIOLATION] tentative de création/augmentation
           d'un fichier de test ({path})
    FIX: l'agent QA générera les tests via /qa-generate {n}
```

### 4.3 Pas de code production "testable artificiellement"

Les agents dev-* ne doivent pas introduire dans le code production :
- Du code mort destiné à être testable (`internal` exposés en
  `InternalsVisibleTo` non déclaré, classes `partial` ouvertes pour mock)
- Des deps de test (`Moq`, `xUnit`, `Vitest`, `@testing-library/*`)
  dans les `*.csproj` / `package.json` du code production. Ces deps
  vivent **exclusivement** dans les projets de test.

Un code correctement architecturé (DI, contrats explicites, inversion
de dépendances) est nativement testable sans artifice.

---

## 5. Trigger d'invocation de l'agent QA

| Valeur `QAMode` | Comportement `/sdd-full` |
|---|---|
| `off` | Agent QA JAMAIS invoqué. `/sdd-full` saute la phase 6. |
| `quality-only` | `/sdd-full` invoque `/qa-generate {n}` après `/dev-run`. Agent skippe STEP 6 (génération tests) et STEP 7-8 (run tests + coverage). |
| `tests-only` | Idem mais skip STEP 4 (quality scan) et STEP 8 (coverage). |
| `tests+coverage` | Idem mais skip STEP 4 (quality scan). |
| `full` (recommandé) | Tous les STEP exécutés. |

`QAMode` absent → équivalent `manual` = `/sdd-full` ne déclenche pas
QA, l'utilisateur lance `/qa-generate {n}` quand il veut.

**Décision SDD_Pro v3.1.0** : `/sdd-full` invoque automatiquement
`/qa-generate {n}` pour TOUS les modes ≠ `off` ET ≠ `manual`.

---

## 6. Format ERROR — exemples

### `[QA_OWNERSHIP_VIOLATION]` (côté dev-*)

```
ERROR: dev-backend 1-1 — violation ownership QA
CAUSE: [QA_OWNERSHIP_VIOLATION] tentative de création de workspace/output/src/SIMBackend.Tests/AuthServiceTests.cs
FIX: retirer ce fichier du plan ; l'agent QA le générera via /qa-generate 1
```

### `[QA_OWNERSHIP_VIOLATION]` (côté QA)

```
ERROR: agent qa — violation ownership prod code
CAUSE: [QA_OWNERSHIP_VIOLATION] tentative de modification de workspace/output/src/SIMBackend/Services/AuthService.cs
FIX: agent QA est read-only sur le code production ; corriger le scan
```

---

## 7. Enforcement

- **Agent QA** charge cette règle en STEP 3
- **Agents `dev-backend` et `dev-frontend`** chargent cette règle en
  STEP 3 (lecture passive — pour appliquer §4 au scan forbidden content)
- **Commande `/sdd-full`** charge cette règle pour appliquer §5 (trigger
  conditionnel selon `QAMode`)

---

## 8. Philosophie

Un agent = une responsabilité, pas de chevauchement, zéro scope creep :

- **Cohérent** : dev-* génèrent du code métier. QA génère des tests.
  Aucun ne fait les deux.
- **Anti-derive** : un dev-backend qui se mettrait à générer "un petit
  test rapide" introduirait un scope-creep que `responsibilities.md`
  interdit.
- **Auditable** : le propriétaire d'un fichier est déterminé par son
  chemin (matching pattern §1).
- **Réversible** : l'agent QA est opt-in (`QAMode: off | manual | …`).
  Un projet sans QA reste 100% fonctionnel sans l'agent QA.

**Règle mentale** : *"Si je suis dev-* et que j'ai envie d'écrire un
`[Fact]` ou un `it('should...')`, j'ai franchi la ligne. STOP."*
