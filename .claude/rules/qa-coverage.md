# Règle — QA Coverage (seuil 80%, schéma normalisé)

## Principe

L'agent QA mesure la couverture de tests de chaque feature livrée
contre un seuil déclaré dans `## Project Config` de `workspace/input/stack/stack.md`.
La métrique principale est le **pourcentage de lignes couvertes** sur
le périmètre de la feature courante.

Cette règle est **cross-stack** : elle s'applique de manière identique
que le projet utilise `coverlet` (.NET), `c8` (Node), `coverage.py`
(Python), `JaCoCo` (Kotlin), ou `istanbul` (Angular). La normalisation
se fait au niveau du schéma `coverage.json`.

---

## 1. Configuration projet — `## Project Config`

```markdown
## Project Config
QAMode: full              # off | quality-only | tests-only | tests+coverage | full | manual
CoverageMin: 80           # entier 0-100, défaut 80 (SDD_Pro v3.1.0)
```

| Clé | Défaut | Range | Hors range |
|---|---|---|---|
| `QAMode` | `manual` | `off | quality-only | tests-only | tests+coverage | full | manual` | ERROR `[STACK_MALFORMED]` |
| `CoverageMin` | `80` | `0-100` | ERROR `[STACK_MALFORMED]` |

`CoverageMin: 0` est valide (= seuil désactivé, métrique reportée mais
non bloquante même en WARNING).

**Décision SDD_Pro v3.1.0** : `CoverageMin < 80` produit un **🟡 WARN**
(non bloquant), pas un 🔴 NO-GO. Atteindre 80% pile sur du code généré
LLM est difficile ; ne pas bloquer le pipeline.

---

## 2. Format `coverage.json`

L'agent QA écrit `workspace/output/qa/feat-{n}/coverage.json` :

```json
{
  "spec": "{n}-{SpecName}",
  "extractedAt": "2026-05-05T14:32:18Z",
  "stacks": [
    {
      "stack": "qa-dotnet-xunit",
      "tool": "coverlet",
      "toolVersion": "6.0.2",
      "tests": { "total": 47, "passed": 47, "failed": 0, "skipped": 0 },
      "coverage": {
        "lines":    { "covered": 1234, "total": 1500, "percent": 82.27 },
        "branches": { "covered": 100,  "total": 150,  "percent": 66.67 }
      },
      "files": [
        { "path": "workspace/output/src/SIMBackend/Services/AuthService.cs", "lines_pct": 90.00 }
      ]
    }
  ],
  "summary": {
    "total_tests": 47,
    "passed": 47,
    "failed": 0,
    "skipped": 0,
    "coverage_lines_pct": 82.27,
    "coverage_min": 80,
    "coverage_passed": true
  }
}
```

### 2.1 Champs obligatoires

| Champ | Type | Description |
|---|---|---|
| `spec` | string | `{n}-{SpecName}` |
| `extractedAt` | ISO-8601 UTC | Timestamp de la mesure |
| `stacks[]` | array ≥ 1 | Une entrée par stack QA actif |
| `stacks[].stack` | string | Stack ID (`qa-dotnet-xunit`, etc.) |
| `stacks[].tool` | string | Tool de coverage (`coverlet`, `c8`, `JaCoCo`, …) |
| `stacks[].tests.{total,passed,failed,skipped}` | int | Compteurs de tests |
| `stacks[].coverage.lines.{covered,total,percent}` | nombres | Couverture lignes |
| `summary.total_tests` | int | Σ tests cross-stack |
| `summary.coverage_lines_pct` | float | Couverture globale (moyenne pondérée par LOC totales) |
| `summary.coverage_min` | int | Reflète `CoverageMin` du Project Config |
| `summary.coverage_passed` | bool | `coverage_lines_pct >= coverage_min` |

### 2.2 Champs optionnels

| Champ | Quand présent |
|---|---|
| `stacks[].coverage.branches` | Si le tool supporte branches |
| `stacks[].files[]` | Si le tool fournit le détail per-fichier |

### 2.3 Calcul de `summary.coverage_lines_pct`

Multi-stack : moyenne pondérée par LOC totales :
```
coverage_lines_pct = round(Σ(stack.lines.covered) / Σ(stack.lines.total) × 100, 2)
```

Mono-stack : `coverage_lines_pct = stacks[0].coverage.lines.percent`.

### 2.4 Validation avant écriture

1. JSON parsable
2. Tous les champs §2.1 présents
3. Pour chaque stack, `coverage.lines.percent ≈ covered / total × 100` (tolérance ±0.1)
4. `summary.coverage_passed = (coverage_lines_pct >= coverage_min)`

Toute violation → ERROR `[QA_OUTPUT_INVALID]`. Le fichier coverage.json
N'EST PAS écrit (pas de fichier corrompu).

---

## 3. Règles d'évaluation

### 3.1 Métrique principale

```
summary.coverage_passed = (summary.coverage_lines_pct >= CoverageMin)
```

Si `false` → flag `[QA_COVERAGE_GAP]` en **WARNING** dans le rapport.
Décision globale = `YELLOW` (pas `RED`).

### 3.2 Threshold = 0

`CoverageMin: 0` skip le check (`coverage_passed = true` toujours).
Les autres classes (`[QA_TEST_FAILED]`) peuvent toujours flagger.

---

## 4. Classes d'erreur QA

| Préfixe | Quand l'utiliser |
|---|---|
| `[QA_TEST_FAILED]` | Au moins un test échoue → décision `RED` |
| `[QA_COVERAGE_GAP]` | `coverage_lines_pct < CoverageMin` → décision `YELLOW` |
| `[QA_FRAMEWORK_MISSING]` | Test runner CLI absent OU `## Active QA Specs` vide |
| `[QA_INIT_FAILED]` | Bootstrap test project échoue |
| `[QA_TEST_INVALID]` | Forbidden patterns détectés (sleep, DB réelle, état partagé) |
| `[QA_OUTPUT_INVALID]` | `coverage.json` ou `quality.json` non-parseable au self-verify |
| `[QA_PRECONDITION_FAILED]` | SPEC/US/code production absents |
| `[QA_OWNERSHIP_VIOLATION]` | Voir `qa-ownership.md §6` |

**Ordre de priorité** (une seule classe primaire émise dans la décision globale) :
```
[QA_TEST_FAILED] > [QA_COVERAGE_GAP]
```

---

## 5. Format ERROR — exemples

### `[QA_COVERAGE_GAP]` (WARNING dans le rapport)

```
WARNING: feat 1-Auth — coverage gap
CAUSE: [QA_COVERAGE_GAP] lines coverage 62.45% below threshold 80% (8 files measured)
HINT: ajouter des tests dans workspace/output/src/SIMBackend.Tests/Services/ ciblant AuthService.RefreshToken
```

### `[QA_TEST_FAILED]` (rouge)

```
ERROR: feat 1-Auth — tests failed
CAUSE: [QA_TEST_FAILED] 3 tests failed of 47 total — first failure at AuthServiceTests.cs:84 (Assert.Equal expected:200 actual:401)
FIX: inspect workspace/output/qa/feat-1/report.md, fix code via /dev-run 1 ou ajuster les tests
```

### `[QA_FRAMEWORK_MISSING]` (rouge)

```
ERROR: feat 1-Auth — framework missing
CAUSE: [QA_FRAMEWORK_MISSING] command 'dotnet test' failed (dotnet CLI not in PATH)
FIX: install .NET SDK from https://dot.net OR set dotnet in PATH
```

---

## 6. Invariants

### 6.1 `coverage.json` overwritten chaque run

Pas de merge avec un fichier précédent. Pas d'historique. Le fichier
reflète EXACTEMENT le dernier run. Historisation = service externe
(out of scope).

### 6.2 Écriture atomique

Le fichier est écrit en `.coverage.json.tmp` puis renommé. Cela évite
qu'un kill du process laisse un JSON tronqué.

### 6.3 Encodage et formatting

- UTF-8 sans BOM
- Indentation 2 espaces
- Clés ordonnées selon §2.1 (déterministe pour les diffs)

### 6.4 Timestamps

`extractedAt` en UTC ISO-8601 avec `Z` final.

---

## 7. Enforcement

- **Agent QA** charge cette règle en STEP 3 (chargement contexte)
- **Script `parse-coverage.ps1`** applique le format §2 et le calcul
  §2.3 sans intervention LLM (déterministe, 0 token)
- **Commande `/qa-generate`** propage le statut feature selon §3 + §4

---

## 8. Ce que cette règle n'impose PAS

- **Quel test runner / coverage tool utiliser** — c'est dans le QA
  stack actif (`.claude/stacks/qa/*.md`)
- **Le format intermédiaire produit par le tool** (cobertura XML,
  lcov, json native) — le script `parse-coverage.ps1` parse et
  normalise vers le schéma §2
- **L'historisation** — out of scope
- **L'intégration avec services externes** (Codecov, SonarQube Cloud,
  Coveralls) — hors scope SDD_Pro
