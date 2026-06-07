# QA Stack — Mutation Testing (opt-in, v7.0.0)

Status: Experimental
Validation: 🟡 experimental (schema opt-in, non actif par défaut)
Support: ⚠ Non supporté commercialement (audit C3, 2026-06-06) — exclu du SLA produit. Voir CLAUDE.md §6 et docs/validated-combos.md.
QA FEAT ID: mutation-testing
Scope: anti auto-confirmation bias (briser le co-écrit IA code+tests)

> **But** : briser l'auto-confirmation bias où la même IA génère code + tests.
> Mutation testing introduit des mutations syntaxiques (`>` → `<`, `+` → `-`,
> `true` → `false`, etc.) dans le code production puis re-run la suite : si
> les tests passent **encore**, c'est qu'ils ne vérifient pas vraiment cette
> ligne (mutant survivant = test inadéquat).

---

## 1. Activation

Project Config (`workspace/input/stack/stack.md`) :

```yaml
MutationTestingMode: off    # off (default) | minimal | full
MutationScoreMin: 60        # % de mutants tués requis (0-100)
MutationTestingTimeoutSec: 600  # cap durée par stack runtime
```

| Mode | Comportement | Coût estimé |
|---|---|---|
| `off` | skip (défaut, byte-identique pre-v7.0.0) | 0 |
| `minimal` | mutation testing sur **services métier** uniquement (≠ DTO/Models/Controllers triviaux) | +5-15 min wall-clock |
| `full` | mutation testing sur tout code production matérialisé | +30-90 min wall-clock |

## 2. Tooling par runtime

| Stack QA | Tool | Install command (Tech Lead, hors `arch`) |
|---|---|---|
| `qa/dotnet-xunit` | [Stryker.NET](https://stryker-mutator.io/docs/stryker-net) | `dotnet tool install -g dotnet-stryker` |
| `qa/node-vitest` | [StrykerJS](https://stryker-mutator.io/docs/stryker-js) | `npm install -D @stryker-mutator/core @stryker-mutator/vitest-runner` |
| `qa/python-pytest` | [mutmut](https://mutmut.readthedocs.io/) | `pip install mutmut` |
| `qa/kotlin-junit` | [Pitest](https://pitest.org/) | Gradle plugin `info.solidsoft.pitest` |
| `qa/angular-jasmine` | StrykerJS (idem Node) | idem |
| `qa/blazor-bunit` | Stryker.NET (idem .NET) | idem |

<!-- LIBS_CATALOG_START -->
### 2.4 Librairies

> Source de verite : `.claude/stacks/qa/mutation-testing.libs.json`. Ne pas editer cette section manuellement -- utiliser `.claude/python/sdd_admin/sync_stack_md.py --stack-id mutation-testing`.

#### 2.4.a Librairies CORE (installees par arch en section 2.2.1, toujours)

| Lib | Version | Role |
|-----|---------|------|

### 2.4.b Librairies ON-DEMAND (installees si l'US declenche)

Triggers (regex case-insensitive) cherches par `detect_capabilities.py` dans l'US + ACs.

| Capability | Lib | Version | Triggers |
|---|---|---|---|
| mutation-testing-dotnet | dotnet-stryker | 4.4.1 | MutationTestingMode\s*:\s*(minimal|full) |
| mutation-testing-node | @stryker-mutator/core | 8.7.1 | MutationTestingMode\s*:\s*(minimal|full) |
| mutation-testing-vitest | @stryker-mutator/vitest-runner | 8.7.1 | MutationTestingMode\s*:\s*(minimal|full) |
| mutation-testing-python | mutmut | 3.3.0 | MutationTestingMode\s*:\s*(minimal|full) |
| mutation-testing-kotlin | gradle-pitest-plugin | 1.15.0 | MutationTestingMode\s*:\s*(minimal|full) |
| mutation-testing-kotlin | pitest-junit5-plugin (alt) | 1.2.1 | MutationTestingMode\s*:\s*(minimal|full) |
<!-- LIBS_CATALOG_END -->

## 3. Critère de passage

```
mutation_score = killed / (killed + survived + timeout + no_coverage)
gate_passed = (mutation_score >= MutationScoreMin / 100)
```

Verdict aligné avec le pattern QA général :
- `PASS` : `mutation_score >= MutationScoreMin`
- `WARN` : `mutation_score < MutationScoreMin` mais ≥ 80 % du seuil
- `FAIL` : `mutation_score < 80 % de MutationScoreMin`
- `SKIPPED` : `MutationTestingMode: off`
- `INFRA_BLOCKED` : tool absent OU timeout dépassé

## 4. Intégration pipeline

Phase 5 (QA) :
- `qa-generate.md` STEP X (nouveau, conditionnel) — si `MutationTestingMode != off`,
  invoque le tool runtime après les tests unitaires. Sortie persistée dans
  `workspace/output/qa/feat-{n}/mutation.json` + table `qa_mutation` de
  `console.db` (schema migration v8).
- `/sdd-review` agrège dans le verdict consolidé (nouvelle source `mutation`).

## 5. Exemples cross-runtime

### 5.1 Stryker.NET (qa/dotnet-xunit)

Configuration `stryker-config.json` à la racine de `{BackendName}.Tests/` :

```json
{
  "stryker-config": {
    "project": "../{BackendName}/{BackendName}.csproj",
    "test-projects": ["{BackendName}.Tests.csproj"],
    "mutate": ["**/Services/**/*.cs", "**/UseCases/**/*.cs", "!**/*.g.cs"],
    "thresholds": { "high": 80, "low": 60, "break": 60 },
    "reporters": ["json", "progress"],
    "concurrency": 4
  }
}
```

Commande lancée par `qa.md` STEP 8.5 :
```bash
cd workspace/output/src/{BackendName}.Tests
dotnet stryker --threshold-break $MUTATION_SCORE_MIN \
               --timeout-ms $((MUTATION_TIMEOUT*1000)) \
               --output ../qa-mutation
```

Sortie : `StrykerOutput/{timestamp}/reports/mutation-report.json` → parsé
vers `workspace/output/qa/feat-{n}/mutation.json`.

### 5.2 StrykerJS (qa/node-vitest)

`stryker.conf.mjs` :
```javascript
export default {
  packageManager: 'npm',
  testRunner: 'vitest',
  mutate: ['src/services/**/*.ts', 'src/use-cases/**/*.ts'],
  thresholds: { high: 80, low: 60, break: 60 },
  reporters: ['json', 'progress'],
  vitest: { configFile: 'vitest.config.ts' },
};
```

### 5.3 mutmut (qa/python-pytest)

`pyproject.toml` :
```toml
[tool.mutmut]
paths_to_mutate = "src/services/,src/use_cases/"
runner = "pytest -x"
tests_dir = "tests/"
```

### 5.4 Pitest (qa/kotlin-junit)

`build.gradle.kts` :
```kotlin
plugins { id("info.solidsoft.pitest") version "1.15.0" }
pitest {
    targetClasses.set(listOf("com.example.services.*", "com.example.usecases.*"))
    mutationThreshold.set(60)
    timestampedReports.set(false)
    outputFormats.set(listOf("XML", "HTML"))
}
```

## 6. Edge cases & pièges connus

| Piège | Symptôme | Solution |
|---|---|---|
| **Mutants équivalents** | Score stagne à ~70 % même avec tests parfaits — certaines mutations produisent un code sémantiquement identique (`x > 0` → `x >= 1` sur entier) | Exclure via `excluded-mutations` config ; ne pas viser 100 % |
| **Timeout par mutant** | `INFRA_BLOCKED` aléatoire | Augmenter `MutationTestingTimeoutSec` ou réduire scope `mutate:` |
| **DTO/Models triviaux** | Score bas artificiellement | Mode `minimal` exclut DTO/Models — privilégier ce mode |
| **Tests d'intégration lents** | Run mutation 10× plus lent que tests unit | Stryker `testRunner: vitest-runner --include 'tests/unit/**'` |
| **CI vs local divergence** | Score différent CI/local | Pin random seed via tool config (Stryker `randomSeed`, Pitest `randomSeed`) |

## 7. Anti-derive

- ❌ Activer `full` en CI sans cap timeout (peut bloquer 1 h+)
- ❌ Mesurer mutation score sans baseline humaine (un score 60 % peut être bon
  OU mauvais selon le domaine — calibrer)
- ❌ Activer sur code généré qui n'a pas atteint coverage 80 % d'abord
  (mutation score sur 20 % de code couvert est trivialement faux)
- ❌ Mutation testing sur tests générés (auto-confirmation bias) — toujours
  mesurer contre tests humains complémentaires
- ❌ Ignorer les mutants équivalents sans audit (ils gonflent le score)

## 8. Statut implémentation

**v7.0.0** : ✅ stack câblé. `qa.md` STEP 8.5 invoque le tool si
`MutationTestingMode != off`, persiste dans `console.db` table
`qa_mutation` (migration `0002_add-qa-mutation-table.sql`).
**Opt-in strict** (`off` par défaut) — aucun coût ajouté tant que le
Tech Lead n'active pas via Project Config.

**Recommandation** : activer `MutationTestingMode: minimal` sur 1 FEAT M
test en local, mesurer wall-clock + mutation score, comparer aux issues
réelles trouvées par les reviewers. Si ≥ 3 bugs réels échappent aux tests
existants mais sont attrapés par mutation → green-light pour câblage.

---

*Source : risk audit 2026-05-20 §6.2 "Auto-confirmation bias QA".*
