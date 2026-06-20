---
name: using-sddpro
description: Use IMMEDIATELY at session start, before responding to any user message about software development, feature additions, bug fixes, code reviews, or anything that could be done with SDDPro framework commands. Loads the canonical SDDPro pipeline overview, the 13 user-facing commands, and the agent ownership model so subsequent responses route through framework conventions instead of ad-hoc coding.
---

# Skill — Using SDDPro

> **Auto-trigger pattern (emprunt superpowers v5.1)** : ce skill se
> charge au début de chaque session ET dès qu'une intention dev est
> détectée. Coût : ~1 KB context. Bénéfice : Claude propose une
> commande SDD_Pro adaptée au lieu de coder direct.

## Quand ce skill s'active

| Signal utilisateur | Action recommandée |
|---|---|
| "Je veux ajouter une fonctionnalité X" | `/feat-generate X` (cadrage 3-6 questions) |
| "Comment je fais Y ?" | `/sdd-help "Y"` (FAQ contextuelle) |
| "Que fait ce projet ?" | `/sdd-status` (tree ASCII) |
| "Ça plante" / "Mon build échoue" | `/sdd-help {n}` puis lire `workspace/output/qa/feat-{n}/` |
| "Je veux refaire ce code" | Lire l'US source d'abord, jamais re-coder à l'aveugle |
| "Audit le code" | `/sdd-review {n}` (two-stage : spec gate → quality batch) |

## Pipeline canonique à respecter

```
0 (opt)  Discovery (.claude/templates/{product-brief,prfaq}.template.md)
   ↓
1-2      /feat-generate → /us-generate → /feat-validate
   ↓
4        /dev-run (arch+DB → backend → API gate → frontend)
   ↓
5        /qa-generate → /sdd-review (two-stage v7.0.0+)
```

## Conventions load-bearing à ne JAMAIS violer

1. **Source-first** : tout dans `.md` versionnés (FEATs, US, plans,
   ADRs). Pas de mémoire opaque dans le LLM.

2. **File ownership matrix** (`@.claude/rules/ownership.md`) : un seul
   owner par path. Avant tout Write/Edit sous `workspace/output/src/`,
   vérifier qui possède le path.

3. **Two-stage auditor** (v7.0.0+) : `spec-compliance-reviewer` est
   un **gate** (Stage A) qui tourne SEUL. Si 🔴 RED, les 3 autres
   reviewers (code, security, arch) sont skippés — pas de gaspillage
   à reviewer du code qui sera réécrit.

4. **Stack `.md` = SSoT secrets** (gitignored) : DB_PASSWORD, JWT
   secrets, etc. Code lit via `IConfiguration` / `@Value` / `Settings()`.
   **Jamais** `process.env` direct (sinon `[SEC_ENV_VAR_FORBIDDEN]`).

5. **Anti-derive** : refuser scope hors US, lib hors §2.4 du stack,
   refactor non demandé. STOP + ERROR avec préfixe `[CLASS]` (cf.
   `@.claude/rules/error-classification.md`).

## Red flags — rationalizations à refuser

| Rationalization | Bonne réponse |
|---|---|
| "Je vais juste corriger ce bug rapidement sans FEAT" | Pour un bug fix isolé, `/sdd-poc` ou patch direct OK. Pour une vraie évolution, créer FEAT → US → code. |
| "Je connais le code, pas besoin de lire l'US" | Lire toujours l'US avant Edit (AC implicites = bugs). |
| "Pas le temps de faire les tests, on fera après" | QA est dans le pipeline (`/qa-generate`). Pas de "après". |
| "Cette lib n'est pas dans le stack mais elle est bien" | STOP + ERROR `[STACK_LIBRARY_MISSING]`. Tech Lead arbitre. |
| "Je vais corriger le code et le test en même temps" | Lire US d'abord. Si US ambiguë, `/us-generate` régénère. |

## Skill list (skills SDDPro disponibles)

- **using-sddpro** (ce skill) — overview chargé au session start
- **starting-a-new-feat** — auto-trigger sur intentions "nouvelle fonctionnalité"
- **debugging-failed-pipeline** — auto-trigger sur "ça plante", "le pipeline échoue"

## Pointeurs

- `@.claude/CLAUDE.md` — référence framework complète
- `/sdd-help` — guidance contextuelle "what's next"
- `@.claude/docs/quickstart.md` — onboarding 10 min
- `@.claude/docs/cookbook.md` — recettes pratiques

> **Règle mentale** : "Toujours commencer par lire l'état (sdd-help /
> sdd-status), proposer une commande SDD_Pro, JAMAIS coder à l'aveugle."
