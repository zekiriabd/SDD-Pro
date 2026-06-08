---
name: test-driven-development
description: Use whenever the agent is about to write production code (a new function, class, endpoint, method, or component) to enforce the RED-GREEN-REFACTOR cycle (emprunt Superpowers v5.1). NO production code without a failing test first. Triggers on intentions to write code into workspace/output/src/, *.cs/*.ts/*.py/*.kt files, or any creation of a method/class/function/endpoint. If the agent realizes it has already written production code without a test, the skill mandates deleting that code and restarting with RED-GREEN-REFACTOR. Non-negotiable for SDDPro v7.0.0+ test-first contract.
---

# Skill — Test-Driven Development (RED-GREEN-REFACTOR)

> **Emprunt direct Superpowers v5.1** : "NO PRODUCTION CODE WITHOUT A
> FAILING TEST FIRST. Delete code written before tests — start over."
> Ce skill matérialise le contrat **test-first** au niveau du pipeline
> SDD_Pro, complémentaire au QA agent (qui RUN les tests) et à l'API
> Gate (qui les vérifie post-hoc).

## L'invariant non-négociable

```
RED   → écrire UN test qui échoue (et le faire échouer pour la bonne raison)
GREEN → écrire le code MINIMAL pour le passer
REFACTOR → améliorer code + tests tant que tests restent verts
```

**Aucune** ligne de code de production sans un test écrit **avant** qui
le justifie. Si l'agent réalise qu'il a écrit du code sans test : **supprimer
le code**, écrire le test, recommencer en RED.

## Quand ce skill s'active

| Intention détectée | Action TDD |
|---|---|
| "Écris une fonction qui …" | Skill bloque → "écris d'abord le test qui définit le contrat" |
| "Ajoute un endpoint POST /api/foo" | Skill bloque → "écris d'abord le test d'intégration HTTP du happy path" |
| "Crée une classe `UserService`" | Skill bloque → "écris d'abord 1 test du method principal" |
| Création fichier `*.cs|*.ts|*.py|*.kt` sous `workspace/output/src/` sans test correspondant sous `*.Tests/` ou `__tests__/` | Skill flag → demande le test d'abord |
| "Je vais refactor X" | Skill ALLOWS (refactor = test reste vert ; pas de nouveau contrat) |
| "Je vais corriger un bug" | Skill **exige un test de régression rouge AVANT le fix** |

## Le cycle complet (étapes)

### 1. RED — écrire le test rouge

- Identifier l'unité minimale à tester (1 behavior, pas N)
- Écrire le test dans le bon répertoire :
  - .NET : `workspace/output/src/{BackendName}.Tests/Unit/`
  - Node/TS : `__tests__/` ou `*.test.ts` à côté
  - Python : `tests/test_*.py`
  - Kotlin : `src/test/kotlin/`
- **Lancer le test, vérifier qu'il échoue** — et qu'il échoue pour la
  bonne raison (assertion failure, pas import error / syntax error)
- Si le test passe immédiatement → soit le code existe déjà, soit le
  test ne teste rien. STOP, repenser.

### 2. GREEN — écrire le code minimal

- Écrire le **strict minimum** pour faire passer le test
- Pas de features bonus, pas de optimisation prématurée, pas de
  "tant que j'y suis"
- Lancer le test, vérifier qu'il passe
- Si d'autres tests cassent → la GREEN est cassée, fix d'abord

### 3. REFACTOR — améliorer sans casser

- Renommer pour la lisibilité
- Extraire pour la réutilisation (DRY justifié)
- Lancer tous les tests après chaque modif
- Si un test casse → revert immédiat

### 4. COMMIT (ou checkpoint)

- 1 test + 1 fix = 1 commit
- Message : "test+code: <behavior>" ou "fix: <bug> (+ regression test)"
- Préserve la traçabilité RED → GREEN → REFACTOR

## Anti-patterns refusés

| Rationalization | Réponse TDD |
|---|---|
| "Je vais tester après, c'est plus rapide" | **NON.** Code écrit avant test = supprimer + recommencer. Test après-coup passe sans avoir prouvé quoi que ce soit (tu n'as jamais vu RED). |
| "Le code est trivial, pas besoin de test" | **NON.** Trivial = test trivial = 30 secondes à écrire. Si trivial, ce n'est pas une perte de temps. Si vraiment trivial (1 ligne `return x + 1`), tolérance OK. |
| "J'ai déjà testé manuellement" | **NON.** Test manuel = pas de regression. Si tu casses le code dans 3 mois, rien ne l'attrape. |
| "Je connais le code, pas besoin" | **NON.** Le futur toi ne connaîtra plus dans 6 mois. |
| "Je vais juste refactor, c'est sûr" | **OUI** — si tests existants couvrent le behavior. Si pas de test sur cette unité → écrire test d'abord (test de **caractérisation** : capturer le behavior actuel). |
| "Je vais commit le test et le fix en même temps après avoir tout codé" | **NON.** Le séquencement (RED puis GREEN) est la valeur. Sans le RED visible, tu n'as jamais validé que le test attrape la régression. |
| "Le coverage est déjà à 80%, ça suffit" | **NON.** Coverage = lignes touchées, pas behaviors testés. Le seuil `CoverageMin` est un **plancher**, pas une autorisation à skipper les tests pour les nouvelles features. |

## Tests de régression (sur bug fix)

Quand un bug est rapporté :

1. **Écrire le test qui reproduit le bug** — doit échouer (RED prouve la bug)
2. **Vérifier qu'il échoue** — log de l'output rouge
3. **Fixer le code** — minimal change pour passer le test
4. **Vérifier que le test passe** (GREEN)
5. **(Optional) Refactor**

Si tu fixes le bug AVANT le test : tu n'as JAMAIS prouvé que ton test
attrape la régression. Tu pourrais ne tester rien. **Toujours RED first.**

## Intégration SDD_Pro

| Composant | Rôle vs TDD |
|---|---|
| `dev-backend` / `dev-frontend` | Produit le code prod ; doit créer les tests **avant** (ou supprimer + recommencer) |
| `qa` agent | Génère / complète les tests post-dev — ne remplace PAS TDD préventif |
| API Gate | Vérifie tests d'intégration HTTP — pas un substitut au TDD unitaire |
| Coverage (`CoverageMin`) | Plancher quantitatif — n'enforce pas le test-first |
| **Ce skill** | Enforce le test-first au moment de la création du code |

## Pointeurs

- `@.claude/rules/quality.md §A` — coverage threshold
- `@.claude/rules/build-and-loop.md §A` — API Gate (tests d'intégration HTTP)
- `@.claude/agents/qa.md` — agent QA post-dev
- `@.claude/python/sdd_hooks/enforce_tdd.py` — hook PreToolUse Write qui détecte
  écriture code prod sans test associé (audit P3 TDD 2026-06-08)
- **Origine** : Superpowers v5.1 `test-driven-development` skill (Jesse Vincent
  et al., 2025). Adopté par SDD_Pro v7.0.0+.

> **Règle mentale** : "Si je peux écrire le code, je peux écrire le test
> qui le justifie. Si je ne peux pas écrire le test, je ne comprends pas
> ce que je dois faire. STOP, clarifier le behavior d'abord."
