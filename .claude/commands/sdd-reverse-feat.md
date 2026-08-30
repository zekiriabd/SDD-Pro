---
description: Phase 3c du workflow reverse — composition de la FEAT métier propre à partir des User Stories 3b (barreau haut de l'escalier). Spawn agent reverse-feat-composer avec modèle routé par complexité (Sonnet 4.6 si unité simple, Opus 4.8 si complexe — ADR governance-reverse-complexity-ladder). Lit us/{n}-{m}-{Name}.md + plans/{n}-{FeatName}.analysis.md, écrit feats/{n}-{FeatName}.md consommable par /sdd-full.
---
# /sdd-reverse-feat {U-N} [--json]

## Rôle

Lancer la **Phase 3c** (barreau du haut) : composer la **FEAT métier propre** à
partir des **User Stories 3b**, plomberie démotée, evidence résolue
transitivement. C'est le **pont** vers `/sdd-full` (Intent A→B).

```
us/{n}-{m}-{Name}.md  --[3c /sdd-reverse-feat]-->  feats/{n}-{FeatName}.md
```

Remplace l'ex-`/sdd-reverse` mono-saut (extracteur décommissionné, ADR reverse-spec-ladder).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) |
| `--json` | flag | Émet le rapport en JSON |

## Pré-conditions

1. `(n, FeatName)` résolu via `inventory.json._featAllocations[{U-N}]` (3a a tourné). Absent → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
2. ≥ 1 US `workspace/us/{n}-{m}-{Name}.md` (3b a tourné). Aucune → ERROR `[REVERSE_UNIT_NOT_FOUND]` + suggérer `/sdd-reverse-stories {U-N}`.
3. `workspace/plans/{n}-{FeatName}.analysis.md` (3a — résolution evidence). Absente → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
4. `.sdd/python/sdd_reverse/feat.reverse.template.md` présent (ADV-9). Sinon → ERROR `[REVERSE_TEMPLATE_MISSING]`.

## Actions

1. **Résoudre le projet legacy** via `inventory.json._featAllocations`. Le nom retenu est `{P}` — **toutes** les étapes suivantes l'utilisent, jamais un re-glob.
2. **Routage de tier (déterministe, ADR `governance-reverse-complexity-ladder`)** —
   sur le projet `{P}` **résolu en 1** :
   ```bash
   python .sdd/python/sdd_reverse/code_unit_complexity.py \
       --project workspace/old/{P} --unit {U-N} --rung 3c
   ```
   → `balanced` si `simple`, `deep` si `complex` (même classifieur que 3a → la
   classe est stable sur tout l'escalier ; rubrique
   `docs/rubrics/reverse-complexity-routing.md`). **Fail-safe câblé** : toute
   erreur imprime `deep` sur stdout + la raison sur stderr, exit 0 — jamais de
   traceback à la place d'un tier.
3. **Spawn unique** `Agent(reverse-feat-composer)` avec args = `{U-N}` ET `model_tier` = le tier routé en 2 (override au spawn, borné par `tier_floor`/`tier_ceiling` de l'agent — agent inchangé, no-spawn préservé).
4. L'agent suit STEP 0 à 6 de `.sdd/agents/reverse-feat-composer.md` (composition + validate_reverse_feat max 3 + check_feat_completeness).
5. Émission ligne chat finale `[REVERSE] {U-N} → FEAT {n}-{FeatName} ({modèle}, ...). (PROGRESS%)`.

## Sortie

```
workspace/feats/{n}-{FeatName}.md                    (FEAT SDD_Pro métier conforme)
workspace/old/{P}/.sys/modules/{FeatName}/feat-3c.md       (log composition)
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

Voir `.sdd/docs/reverse-engineering-workflow.md` §Phase 3 + ADR `governance-major-reverse-spec-ladder`.
