---
command: sdd-reverse-feat
phase: 3c
description: Phase 3c du workflow reverse — composition de la FEAT métier propre à partir des User Stories 3b (barreau haut de l'escalier). Spawn agent reverse-feat-composer (Opus 4.8). Lit output/us/{n}-{m}-{Name}.md + output/plans/{n}-{Name}.analysis.md, écrit input/feats/{n}-{Name}.md consommable par /sdd-full.
loader: .claude/loader.reverse.yml
---

# /sdd-reverse-feat {U-N} [--json]

## Rôle

Lancer la **Phase 3c** (barreau du haut) : composer la **FEAT métier propre** à
partir des **User Stories 3b**, plomberie démotée, evidence résolue
transitivement. C'est le **pont** vers `/sdd-full` (Intent A→B).

```
output/us/{n}-{m}-{Name}.md  --[3c /sdd-reverse-feat]-->  input/feats/{n}-{Name}.md
```

Remplace l'ex-`/sdd-reverse` mono-saut (extracteur décommissionné, ADR reverse-spec-ladder).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) |
| `--json` | flag | Émet le rapport en JSON |

## Pré-conditions

1. `(n, Name)` résolu via `inventory.json._featAllocations[{U-N}]` (3a a tourné). Absent → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
2. ≥ 1 US `workspace/output/us/{n}-{m}-{Name}.md` (3b a tourné). Aucune → ERROR `[REVERSE_UNIT_NOT_FOUND]` + suggérer `/sdd-reverse-stories {U-N}`.
3. `workspace/output/plans/{n}-{Name}.analysis.md` (3a — résolution evidence). Absente → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
4. `.claude/python/sdd_reverse/feat.reverse.template.md` présent (ADV-9). Sinon → ERROR `[REVERSE_TEMPLATE_MISSING]`.

## Actions

1. **Résoudre le projet legacy** via `inventory.json._featAllocations`.
2. **Spawn unique** `Agent(reverse-feat-composer)` avec args = `{U-N}`.
3. L'agent suit STEP 0 à 6 de `.claude/agents/reverse-feat-composer.md` (composition + validate_reverse_feat max 3 + check_feat_completeness).
4. Émission ligne chat finale `[REVERSE] {U-N} → FEAT {n}-{Name} (...). (PROGRESS%)`.

## Sortie

```
workspace/input/feats/{n}-{Name}.md                    (FEAT SDD_Pro métier conforme)
workspace/old/{P}/.sys/modules/{Name}/feat-3c.md       (log composition)
```

## Confidence ≠ high

Si `confidence: medium|low` (min-monotone depuis 3a/3b, ou validate 3 itérations
échouée), la FEAT est écrite avec bannière + REVERSE-GATE `allow-sdd-full=false`.
Pour la consommer malgré tout : `check_reverse_feat_for_full.py --allow-reverse-low`.

## Anti-derive

- **Une seule unité par invocation**.
- L'agent ne lit **PAS le code legacy** — uniquement les US 3b + l'analyse 3a.
- **Démotion plomberie** : connstring/timeout/mécaniques jamais en `## Business Rules`.
- No-spawn d'agent autre que `reverse-feat-composer`.
- Idempotence : re-lancer réécrit la même FEAT.

Voir `.claude/docs/reverse-engineering-workflow.md` §Phase 3 + ADR `governance-major-reverse-spec-ladder`.
