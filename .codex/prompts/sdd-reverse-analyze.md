<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-analyze) — DO NOT EDIT -->
<!-- Phase 3a du workflow reverse — analyse technique fidèle d'UNE unité U-N (barreau bas de l'escalier reverse). Spawn agent reverse-tech-analyst avec modèle routé par complexité (Sonnet 4.6 si unité simple, Opus 4.8 si complexe — ADR governance-reverse-complexity-ladder). Output workspace/plans/{n}-{FeatName}.analysis.md, consommé par /sdd-reverse-stories (3b). -->
<!-- ============================================================ -->
<!-- IMPORTANT — SPAWN SEMANTICS UNDER CODEX (audit R10 2026-07-26) -->
<!-- Toute mention `Task tool (subagent_type=X)`, `Agent(X)`, ou    -->
<!-- « spawn agent X » dans le corps ci-dessous est une INSTRUCTION -->
<!-- Claude-Code-native. Sous Codex/Gemini, ces spawns ne sont PAS  -->
<!-- des tools disponibles ; l'émulation passe par la CLI wrapper : -->
<!--                                                                -->
<!--   python .sdd/python/sdd_scripts/spawn_agent_cli.py \         -->
<!--       --agent <name>                                           -->
<!--       --task-file <path>   (ou --task "...")                 -->
<!--       [--harness codex|gemini-cli|claude-code]                 -->
<!--       [--provider openai|google|anthropic|moonshot]            -->
<!--       [--tier deep|balanced|fast]                              -->
<!--       [--schema-file <path.json>]                              -->
<!--                                                                -->
<!-- Le wrapper renvoie du JSON canonique sur stdout : { ok,        -->
<!-- parsed, raw, error_class, schema_errors, attempts, ... }.      -->
<!-- Voir .sdd/python/sdd_lib/spawn_agent.py (isolation cwd,        -->
<!-- parallélisme borné à MaxParallel, retry-on-schema-fail).       -->
<!-- Sub-agents intra-session Claude = 0 tokens ; ici = tokens du   -->
<!-- LLM cible directement + coût réseau.                           -->
<!-- ============================================================ -->
<!-- Arguments SDD passés via $ARGUMENTS (ex. numéro de FEAT). -->

Arguments: $ARGUMENTS

# /sdd-reverse-analyze {U-N} [--json]

## Rôle

Lancer la **Phase 3a** (premier barreau de l'escalier reverse) : transformer une
unité fonctionnelle (Phase 1) en **analyse technique legacy** — photo fidèle du
code, sans interprétation métier. Une seule unité par invocation.

```
code source --[3a /sdd-reverse-analyze]--> plans/{n}-{FeatName}.analysis.md
            --[3b /sdd-reverse-stories]--> us/{n}-{m}-{Name}.md
            --[3c /sdd-reverse-feat]------> feats/{n}-{FeatName}.md
```

En mode pré-alloué (L5, `preallocate_feats` exécuté), plusieurs invocations
peuvent tourner **en parallèle borné** (§8.2 `rules/reverse-engineering.md`) ;
sans pré-allocation, séquentiel strict (ADV-2 §8.1). 3a possède l'allocation
`(n, FeatName)` que 3b/3c réutilisent.

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) — résolu via `inventory.json.units[]` |
| `--json` | flag | Émet le rapport d'analyse en JSON |

## Pré-conditions

1. `workspace/old/{P}/.sys/inventory.json` existe ET passe gate ADV-23
   (`schemaVersion == 1`, `_allocatedNames` + `_featAllocations` présents).
   Sinon → ERROR `[REVERSE_INVENTORY_SCHEMA_STALE]` + suggérer `/sdd-reverse-inventory --refresh`.
2. `units[id="{U-N}"]` existe. Sinon → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
3. `.sdd/python/sdd_reverse/analysis.reverse.template.md` présent (ADV-9). Sinon → ERROR `[REVERSE_TEMPLATE_MISSING]`.
4. (Mode legacy uniquement) Lock `workspace/feats/.alloc.lock` libre OU stale > 30 min (TTL 1800s). Sinon → ERROR `[REVERSE_LOCK_HELD]`. En mode pré-alloué, aucun lock (C5).

## Actions

1. **Résoudre le projet legacy** : lire `workspace/old/*/.sys/inventory.json` pour trouver lequel contient `units[id={U-N}]`. Plusieurs matchs → ERROR ambiguïté, demander `--project {P}`. Le nom retenu est `{P}` — **toutes** les étapes suivantes l'utilisent, jamais un re-glob.
2. **Routage de tier (déterministe, ADR `governance-reverse-complexity-ladder`)** —
   sur le projet `{P}` **résolu en 1** :
   ```bash
   python .sdd/python/sdd_reverse/code_unit_complexity.py \
       --project workspace/old/{P} --unit {U-N} --rung 3a
   ```
   → imprime `balanced` si l'unité est `simple`, `deep` si `complex` (rubrique
   `docs/rubrics/reverse-complexity-routing.md`). **Fail-safe câblé** : toute
   erreur (inventory absent/illisible, `{U-N}` inconnu) imprime `deep` sur stdout
   ET la raison sur stderr, exit 0 — le doute coûte une passe `deep`, jamais un
   traceback ni une sous-analyse.
3. **Spawn unique** `Agent(reverse-tech-analyst)` avec args = `{U-N}` ET `model_tier` = le tier routé en 2 (override au spawn, borné par `tier_floor`/`tier_ceiling` de l'agent — l'agent est inchangé, seul son tier d'exécution varie ; no-spawn préservé).
4. L'agent suit STEP 0 à 7 de `.sdd/agents/reverse-tech-analyst.md`.
5. Émission ligne chat finale `[REVERSE] {U-N} → analyse 3a {n}-{FeatName} ({modèle}, ...). (PROGRESS%)`.

## Sortie

```
workspace/plans/{n}-{FeatName}.analysis.md          (analyse technique legacy)
workspace/old/{P}/.sys/modules/{FeatName}/extraction.md    (log décision)
workspace/old/{P}/.sys/inventory.json                  (update _featAllocations + _allocatedNames — mode legacy)
```

## Voie d'usage standard (escalier complet)

1. `/sdd-reverse-inventory MyLegacy` (Phase 1)
2. `/sdd-reverse-analyze U-1` (3a) → analyse technique
3. `/sdd-reverse-stories U-1` (3b) → user stories
4. `/sdd-reverse-feat U-1` (3c) → FEAT métier
5. (ou `/sdd-reverse U-1` qui séquence 3a→3b→3c, ou `/sdd-reverse-full` pour tout le pipeline)

## Anti-derive

- **Une seule unité par invocation** — jamais batch.
- 3a décrit le **mécanique observé**, jamais l'intention métier (réservée 3b/3c).
- Plomberie (connstring, timeouts) démotée dans `## Accès données`, jamais en règle métier.
- No-spawn d'agent autre que `reverse-tech-analyst`.
- Idempotence : re-lancer réécrit la même analyse (mêmes `n`/`Name` via `_featAllocations`).

Voir `.sdd/docs/reverse-engineering-workflow.md` §Phase 3 + ADR `governance-major-reverse-spec-ladder`.
