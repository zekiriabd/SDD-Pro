<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-stories) — DO NOT EDIT -->
<!-- Phase 3b du workflow reverse — remontée de l'analyse technique 3a en User Stories par capability (barreau moyen de l'escalier). Spawn agent reverse-us-writer, toujours au tier `balanced` (downgrade audité 2026-06-11) ; 3a/3c sont routés par complexité depuis l'ADR governance-reverse-complexity-ladder (2026-06-29). Lit plans/{n}-{FeatName}.analysis.md, écrit us/{n}-{m}-{Name}.md. Consommé par /sdd-reverse-feat (3c). -->
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

# /sdd-reverse-stories {U-N} [--json]

## Rôle

Lancer la **Phase 3b** : remonter l'**analyse technique 3a** d'une marche
d'altitude vers des **User Stories par capability métier**. Une seule unité par invocation.

```
plans/{n}-{FeatName}.analysis.md --[3b /sdd-reverse-stories]--> us/{n}-{m}-{Name}.md
```

Le fil de traçabilité monte : chaque AC d'US pointe vers les tasks `T-N` de
l'analyse (`<!-- covers: T-N -->`). Confidence min-monotone (≤ analyse 3a).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) |
| `--json` | flag | Émet le rapport en JSON |

## Pré-conditions

1. `(n, FeatName)` résolu via `inventory.json._featAllocations[{U-N}]` (3a a tourné). Absent → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
2. `workspace/plans/{n}-{FeatName}.analysis.md` existe (barreau 3a). Absent → ERROR `[REVERSE_UNIT_NOT_FOUND]` + suggérer `/sdd-reverse-analyze {U-N}`.
3. `.sdd/python/sdd_reverse/us.reverse.template.md` présent (ADV-9). Sinon → ERROR `[REVERSE_TEMPLATE_MISSING]`.

## Actions

1. **Résoudre le projet legacy** via `inventory.json._featAllocations`.
2. **Spawn unique** `Agent(reverse-us-writer)` avec args = `{U-N}`.
3. L'agent suit STEP 0 à 5 de `.sdd/agents/reverse-us-writer.md`.
4. Émission ligne chat finale `[REVERSE] {U-N} → {U} US 3b (...). (PROGRESS%)`.

## Sortie

```
workspace/us/{n}-{m}-{Name}.md                  (1 à 5 US par capability)
workspace/old/{P}/.sys/modules/{FeatName}/stories-3b.md    (log décision)
```

## Anti-derive

- **Une seule unité par invocation**.
- L'agent ne lit **PAS le code legacy** — uniquement l'analyse 3a (lecture sélective stricte).
- Remontée d'altitude réelle : AC observables utilisateur, jamais recopie de tasks techniques.
- No-spawn d'agent autre que `reverse-us-writer`.
- Idempotence : re-lancer réécrit les mêmes US (mêmes `n`/`Name`).

Voir `.sdd/docs/reverse-engineering-workflow.md` §Phase 3 + ADR `governance-major-reverse-spec-ladder`.
