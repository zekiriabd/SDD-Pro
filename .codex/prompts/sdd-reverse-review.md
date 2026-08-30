<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-review) — DO NOT EDIT -->
<!-- Revue de complétude back (L5) d'UNE FEAT reverse. Spawn agent reverse-completeness-reviewer (Sonnet 4.6) après le check déterministe check_feat_completeness.py. Verdict informational, jamais bloquant. Commande wrapper créée 2026-06-10 (audit M11) pour que /sdd-reverse-full reste un pur séquenceur de commandes (no-spawn §9). -->
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

# /sdd-reverse-review {U-N} [--project {P}] [--json]

## Rôle

Lancer la **revue de complétude back** (L5) sur une FEAT reverse déjà extraite :
confronter son contenu à l'evidence profonde de l'unité (`units[U-N].classes` +
`dataAccess`) et signaler ce que l'extraction a omis (`[REVERSE_COMPLETENESS_GAP]`,
informational).

> **Raison d'être (M11)** : avant cette commande, `/sdd-reverse-full` STEP 3.6
> spawnait `reverse-completeness-reviewer` directement — en violation de sa
> propre règle no-spawn (§9 `rules/reverse-engineering.md` : l'orchestrateur
> séquence des **commandes**, chaque commande spawn son agent identifiable).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Unité dont la FEAT doit être revue |
| `--project {P}` | optionnel | Désambiguïse si plusieurs projets sous `workspace/old/` contiennent `{U-N}` |
| `--json` | flag | Émet le verdict en JSON |

## Pré-conditions

1. `workspace/old/{P}/.sys/inventory.json` existe et contient `units[id={U-N}]`. Sinon → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
2. La FEAT correspondante existe (`_featAllocations[{U-N}]` → `{n}-{FeatName}.md`). Sinon → ERROR `[REVERSE_UNIT_NOT_FOUND]`.

## Actions

1. **Résoudre le projet legacy** (comme `/sdd-reverse`) si `--project` absent.
2. **Spawn unique** `Agent(reverse-completeness-reviewer)` avec args = `{U-N}` + `{P}`.
3. L'agent délègue le calcul à :
   ```bash
   python .sdd/python/sdd_reverse_scripts/check_feat_completeness.py \
       --project workspace/old/{P} --unit {U-N} --json
   ```
   puis juge chaque gap (réel / faux positif) et écrit
   `workspace/old/{P}/.sys/modules/{FeatName}/completeness-review.md`.

## Sortie

```
workspace/old/{P}/.sys/modules/{FeatName}/completeness-review.md
```

Verdicts (`summary.verdict`, ASCII) : `complete` | `partial` | `incomplete` —
**jamais bloquant** (le Tech Lead arbitre ; `incomplete` suggère un
re-`/sdd-reverse {U-N}`).

## Émission chat

```
[REVERSE] Complétude {U-N} : {verdict} ({K} gap(s) confirmé(s)). (PROGRESS%)
```

## Anti-derive

- **Une seule unité par invocation**
- No-spawn d'agent autre que `reverse-completeness-reviewer`
- Verdict informational — ne bloque ni Phase 4 ni `/sdd-full`
- Idempotent : relancer écrase `completeness-review.md`

Voir `.sdd/rules/reverse-engineering.md §6` ([REVERSE_COMPLETENESS_GAP]) + `.sdd/agents/reverse-completeness-reviewer.md`.
