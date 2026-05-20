# QA Stack — Mutation Testing (opt-in, v7.0.0)

> **Validation** : 🟡 experimental — schema opt-in, non actif par défaut.
> **But** : briser l'auto-confirmation bias où la même IA génère code + tests.
> Mutation testing introduit des mutations syntaxiques (`>` → `<`, `+` → `-`,
> `true` → `false`, etc.) dans le code production puis re-run la suite : si
> les tests passent **encore**, c'est qu'ils ne vérifient pas vraiment cette
> ligne (mutant survivant = test inadéquat).

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

## 5. Anti-derive

- ❌ Activer `full` en CI sans cap timeout (peut bloquer 1 h+)
- ❌ Mesurer mutation score sans baseline humaine (un score 60 % peut être bon
  OU mauvais selon le domaine — calibrer)
- ❌ Activer sur code généré qui n'a pas atteint coverage 80 % d'abord
  (mutation score sur 20 % de code couvert est trivialement faux)

## 6. Statut implémentation

**v7.0.0** : stack documenté, **infrastructure pas encore câblée** dans
`qa.md` ni `qa-generate.md`. À implémenter en v7.1 si validation PoC sur
1 FEAT M démontre la valeur. Tracé via ADR `governance-mutation-testing-poc`.

**Recommandation** : activer `MutationTestingMode: minimal` sur 1 FEAT M
test en local, mesurer wall-clock + mutation score, comparer aux issues
réelles trouvées par les reviewers. Si ≥ 3 bugs réels échappent aux tests
existants mais sont attrapés par mutation → green-light pour câblage.

---

*Source : risk audit 2026-05-20 §6.2 "Auto-confirmation bias QA".*
