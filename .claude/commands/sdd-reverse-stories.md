---
description: Phase 3b du workflow reverse — remontée de l'analyse technique 3a en User Stories par capability (barreau moyen de l'escalier). Spawn agent reverse-us-writer (Sonnet 4.6 — downgrade audité 2026-06-11, 3a/3c restent Opus 4.8). Lit plans/{n}-{Name}.analysis.md, écrit us/{n}-{m}-{Name}.md. Consommé par /sdd-reverse-feat (3c).
---
# /sdd-reverse-stories {U-N} [--json]

## Rôle

Lancer la **Phase 3b** : remonter l'**analyse technique 3a** d'une marche
d'altitude vers des **User Stories par capability métier**. Une seule unité par invocation.

```
plans/{n}-{Name}.analysis.md --[3b /sdd-reverse-stories]--> us/{n}-{m}-{Name}.md
```

Le fil de traçabilité monte : chaque AC d'US pointe vers les tasks `T-N` de
l'analyse (`<!-- covers: T-N -->`). Confidence min-monotone (≤ analyse 3a).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) |
| `--json` | flag | Émet le rapport en JSON |

## Pré-conditions

1. `(n, Name)` résolu via `inventory.json._featAllocations[{U-N}]` (3a a tourné). Absent → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
2. `workspace/plans/{n}-{Name}.analysis.md` existe (barreau 3a). Absent → ERROR `[REVERSE_UNIT_NOT_FOUND]` + suggérer `/sdd-reverse-analyze {U-N}`.
3. `.sdd/python/sdd_reverse/us.reverse.template.md` présent (ADV-9). Sinon → ERROR `[REVERSE_TEMPLATE_MISSING]`.

## Actions

1. **Résoudre le projet legacy** via `inventory.json._featAllocations`.
2. **Spawn unique** `Agent(reverse-us-writer)` avec args = `{U-N}`.
3. L'agent suit STEP 0 à 5 de `.claude/agents/reverse-us-writer.md`.
4. Émission ligne chat finale `[REVERSE] {U-N} → {U} US 3b (...). (PROGRESS%)`.

## Sortie

```
workspace/us/{n}-{m}-{Name}.md                  (1 à 5 US par capability)
workspace/old/{P}/.sys/modules/{Name}/stories-3b.md    (log décision)
```

## Anti-derive

- **Une seule unité par invocation**.
- L'agent ne lit **PAS le code legacy** — uniquement l'analyse 3a (lecture sélective stricte).
- Remontée d'altitude réelle : AC observables utilisateur, jamais recopie de tasks techniques.
- No-spawn d'agent autre que `reverse-us-writer`.
- Idempotence : re-lancer réécrit les mêmes US (mêmes `n`/`Name`).

Voir `.sdd/docs/reverse-engineering-workflow.md` §Phase 3 + ADR `governance-major-reverse-spec-ladder`.
