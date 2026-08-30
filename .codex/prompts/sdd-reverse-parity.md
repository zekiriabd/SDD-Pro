<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-parity) — DO NOT EDIT -->
<!-- Génération des specs de parité comportementale Gherkin (.feature) pour UNE FEAT reverse. Spawn agent reverse-parity-inspector (Sonnet 4.6), validation déterministe validate_parity_features.py. Verdict informational, jamais bloquant. Emprunt Reversa (agent Inspector) — audit comparatif 2026-06-12. -->
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

<!-- @llm-only-flags-file — les flags de /sdd-reverse-parity sont interprétés
     par le LLM (l'agent reverse-parity-inspector) ; la gate déterministe
     validate_parity_features.py a son propre parsing (--feat-path,
     --parity-dir, --json). -->

# /sdd-reverse-parity {n} [--json]

## Rôle

Dériver des AC d'une FEAT reverse des **scénarios Gherkin exécutables** qui
définissent l'équivalence comportementale legacy ↔ application régénérée.
Comble l'angle mort « extraction statique, pas de validation runtime » : après
`/sdd-full`, le runner BDD de la stack `qa/*` peut exécuter ces `.feature`
contre la nouvelle application pour **prouver** la parité.

## Args

| Arg | Type | Description |
|---|---|---|
| `{n}` | requis | Numéro de la FEAT reverse (`workspace/feats/{n}-{FeatName}.md`) |
| `--json` | flag | Émet le verdict en JSON |

## Pré-conditions

1. `workspace/feats/{n}-{FeatName}.md` existe et porte `generated-by: sdd-reverse`.
   Sinon → ERROR `[REVERSE_UNIT_NOT_FOUND]`.
2. ≥ 1 US `workspace/us/{n}-{m}-*.md` existe (escalier 3b a tourné).

## Actions

1. **Spawn unique** `Agent(reverse-parity-inspector)` avec arg = `{n}`. <!-- no-spawn §9 : 1 commande = 1 agent -->
2. L'agent dérive les scénarios (1 `.feature` par US, tags `@AC-N`), écrit
   `parity-map.md`, puis valide via :
   ```bash
   python .sdd/python/sdd_reverse_scripts/validate_parity_features.py \
       --feat-path workspace/feats/{n}-{FeatName}.md \
       --parity-dir workspace/parity/feat-{n} --json
   ```
   (max 3 itérations de correction sur `[REVERSE_PARITY_INVALID]`).

## Sortie

```
workspace/parity/feat-{n}/
├── {m}-{Slug}.feature
└── parity-map.md
```

Couverture (`coverage.verdict`, ASCII) : `complete` | `partial` — **jamais
bloquant** (`[REVERSE_PARITY_COVERAGE_GAP]` informational ; les AC non
dérivables restent listés, jamais comblés par invention).

## Émission chat

```
[REVERSE] Parité FEAT {n} : {S} scénarios, {K}/{N} AC couverts. (PROGRESS%)
```

## Anti-derive

- **Une seule FEAT par invocation**
- No-spawn d'agent autre que `reverse-parity-inspector`
- `.feature` stack-agnostiques (aucune techno cible nommée — step definitions en aval)
- Verdict informational — ne bloque ni Phase 4 ni `/sdd-full`
- Idempotent : relancer écrase `feat-{n}/`

Voir `.sdd/rules/reverse-engineering.md §6` ([REVERSE_PARITY_*]) + `.sdd/agents/reverse-parity-inspector.md`.
