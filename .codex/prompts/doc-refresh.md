<!-- GENERATED FROM .sdd/ (commande /doc-refresh) — DO NOT EDIT -->
<!-- /doc-refresh -->
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

# /doc-refresh

> ⚠️ **Commande interne v7.0.0** — invoquée auto en fin de pipeline
> (`/sdd-full`, `/dev-run`, `/qa-generate`, `arch` Phase D). Régénère
> `INDEX.md` des ADRs via `sdd_scripts/index_adrs.py` (0 token, ~50 ms,
> idempotent). Préférer un orchestrateur en usage normal ; cette
> commande sert au debug/inspection ciblée.

## Usage

```
/doc-refresh
```

Aucun argument. La commande scanne les ADRs du workspace et régénère
l'index.

## Fichier produit

| Fichier | Description |
|---|---|
| `workspace/.sys/.context/adrs/INDEX.md` | Index ADRs (rebuild depuis `Glob workspace/.sys/.context/adrs/ADR-*.md`) |

## Quand l'utiliser

- **Manuel** : après édition manuelle d'un ADR pour rafraîchir l'index.
- **Auto** : fin de `/sdd-full`, `/dev-run`, `/qa-generate`, `arch` Phase D.

## STEP 1 — Exécuter le script

```bash
python .sdd/python/sdd_scripts/index_adrs.py
```

Ou avec arguments explicites :

```bash
python .sdd/python/sdd_scripts/index_adrs.py \
  --adrs-dir workspace/.sys/.context/adrs \
  --output workspace/.sys/.context/adrs/INDEX.md \
  --template .sdd/templates/adrs-index.template.md
```

Le script :
1. Lit `.sdd/templates/adrs-index.template.md`
2. Glob `workspace/.sys/.context/adrs/ADR-*.md`
3. Parse pour chaque ADR : filename (timestamp ISO + slug), H1 titre,
   `Status:` body field (défaut `Accepted`), `Phase:` body field
   (heuristique slug si absent)
4. Render dans le template avec substitution `{ADRRows}`, `{ADRCount}`,
   `{GeneratedAt}`, `{ProjectName}`
5. Write atomique via `.tmp` + read-back self-check

## STEP 2 — Confirmation

Le script émet **1 ligne** (chat minimal succès) :

```
OK index_adrs — INDEX.md ({N} ADRs) refreshed
```

Si aucun ADR : `OK index_adrs — INDEX.md (0 ADRs, empty) refreshed`.

## Codes d'erreur

| Exit | Classe | Cause |
|---|---|---|
| `0` | — | succès |
| `1` | `[NOT_FOUND]` | template `adrs-index.template.md` manquant ou illisible |
| `2` | `[QA_OUTPUT_INVALID]` | atomic write self-check échec (corruption FS rare) |

## Idempotence stricte

- Aucun état conservé entre runs
- Le fichier `INDEX.md` est overwritten à chaque run
- Peut être ré-invoqué sans risque, en parallèle de tout autre agent
  ou script (l'output ne croise aucune matrice de
  `ownership.md §1`, Partie A, ex-file-ownership.md)

## Coût

- **0 token LLM** ; latence ~50 ms ; aucun appel agent/build/test.
