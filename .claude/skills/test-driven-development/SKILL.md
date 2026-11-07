---
name: test-driven-development
description: Use ONLY when the Tech Lead explicitly asks for TDD / RED-GREEN-REFACTOR / test-first on a piece of work, or when the project explicitly opts in with SDD_TDD_MODE=strict. Do NOT trigger in the standard SDDPro pipeline — there, dev-backend and dev-frontend write production code WITHOUT tests (writing tests is forbidden to them, [QA_OWNERSHIP_VIOLATION]) and the qa agent writes the unit tests AFTER development; the verdict comes from the QA coverage gate (CoverageMin in stack.md). Never delete production code because it has no test yet. When CoverageMin < 100 the TDD discipline does not apply at all.
---

# Skill — Test-Driven Development (opt-in, non bloquant)

> **Décision Tech Lead 2026-11-07** : le TDD ne bloque **jamais** le
> développement. L'organisation SDD-Pro est séquentielle :
>
> ```
> backend (dev-backend) → frontend (dev-frontend) → tests unitaires (qa) → verdict QA
> ```
>
> Les tests sont écrits par `qa` **après** le développement. C'est le gate
> QA (couverture vs `CoverageMin`, puis delivery gate `verify_tests
> --coverage`) qui dit si c'est bon ou pas — pas ce skill, pas le hook.

## Règle d'application (selon `CoverageMin` du `stack.md`)

| `CoverageMin` | Hook `enforce_tdd` (défaut) | Ce skill |
|---|---|---|
| **< 100** (ex. 80) | `off` — aucun contrôle | **Ne s'applique pas** |
| **= 100** | `warn` — signal `[TDD_NO_TEST_FIRST]`, jamais de blocage | Ne s'applique pas automatiquement ; la QA tranche |
| `SDD_TDD_MODE=strict` (opt-in humain explicite) | `strict` — bloque | S'applique (cycle ci-dessous) |

## Ce que dev-backend / dev-frontend font (pipeline standard)

- Écrivent le code de production de l'US **sans** écrire de tests.
- Ne suppriment **jamais** du code au motif qu'il n'a pas encore de test.
- Un `WARN [TDD_NO_TEST_FIRST]` éventuel (`CoverageMin = 100`) est
  informatif : il signale à la QA les unités à couvrir en priorité.

## Ce que qa fait

- Génère les tests unitaires **après** le développement (`/qa-generate`).
- Mesure la couverture et la compare à `CoverageMin` → verdict 🟢/🟡/🔴.
- La delivery gate exige des tests réellement exécutés et réussis.

## Cycle RED-GREEN-REFACTOR (uniquement si opt-in explicite)

Quand le Tech Lead demande explicitement du TDD (ou `SDD_TDD_MODE=strict`) :

1. **RED** — écrire UN test qui échoue pour la bonne raison (assertion,
   pas erreur d'import). Répertoires : .NET `workspace/src/{BackendName}.Tests/Unit/`,
   Node/TS `__tests__/` ou `*.test.ts`, Python `tests/test_*.py`,
   Kotlin `src/test/kotlin/`.
2. **GREEN** — écrire le code minimal qui fait passer le test.
3. **REFACTOR** — améliorer en gardant les tests verts.

Dans ce mode, qui écrit le test RED dépend de l'organisation choisie par le
Tech Lead (spawn `qa` en mode test-first avant dev-*, cf.
`@.sdd/docs/delivery-gates.md`) — dev-* n'écrit toujours pas de tests.

## Tests de régression (bug fix)

Recommandé, non bloquant : sur un bug signalé, demander à `qa` un test qui
reproduit le bug, puis corriger. C'est une bonne pratique, pas un gate.

## Pointeurs

- `@.sdd/python/sdd_hooks/enforce_tdd.py` — hook (mode dérivé de `CoverageMin`)
- `@.sdd/rules/quality.md §A` — seuil de couverture
- `@.claude/agents/qa.md` — agent QA post-dev
- **Origine** : Superpowers v5.1 `test-driven-development`, adapté à
  l'organisation séquentielle SDD-Pro (2026-11-07).
