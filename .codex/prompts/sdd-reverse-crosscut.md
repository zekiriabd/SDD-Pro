<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-crosscut) — DO NOT EDIT -->
<!-- Phase 3-bis du workflow reverse — génère les FEATs transversales déterministes (Librairies à installer + Base de données/procédures stockées/connection strings) depuis les artefacts L1. Script pur (0 token, aucun agent spawné). -->
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

# /sdd-reverse-crosscut {LegacyProject} [--feats-dir DIR] [--json]

## Rôle

Émettre les **deux FEATs transversales** (cross-cutting) d'une migration legacy,
**100 % déterministes** (aucun agent LLM, 0 token) à partir des artefacts produits
en Phase 1 :

- `{n}-Libraries.md` — inventaire des **librairies/DLL à installer** (NuGet
  `packages.config` + `.csproj PackageReference` + `Directory.Packages.props` +
  références d'assembly + DLL `bin/` ; npm/maven/pypi/composer) avec evidence.
- `{n}-Database.md` — **schéma** (entités + champs + relations FK), **procédures
  stockées** (nom + paramètres typés + OUTPUT), **connection strings**
  (provider/serveur/base, secrets masqués), avec evidence file:line.

Ce sont des FEATs reverse standard (frontmatter + REVERSE-GATE + 6 sections +
evidence/confidence par item + AC Given/When/Then) — consommables par `/sdd-full`.

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | string requis | Sous-dossier de `workspace/old/` (Phase 1 préalable obligatoire) |
| `--feats-dir DIR` | flag | Override du dossier de sortie (défaut `workspace/feats`) |
| `--json` | flag | Émet le rapport en JSON |

## Pré-conditions

- `workspace/old/{LegacyProject}/.sys/inventory.json` (Phase 1)
- Au moins un de : `dependencies.json`, `db-schema.json`/`db-schema.merged.json`,
  `data-access.json`, `config.json` (tous produits par Phase 1 depuis L1).

Sinon → STOP + ERROR `[REVERSE_NO_SOURCE]` + suggérer `/sdd-reverse-inventory {LegacyProject}`.

## Actions

```bash
python .sdd/python/sdd_reverse_scripts/generate_crosscutting_feats.py \
    --project workspace/old/{LegacyProject} [--feats-dir DIR] [--json]
```

1. Charge `dependencies.json` + `db-schema(.merged).json` + `data-access.json` + `config.json`.
2. Alloue `n` de façon **idempotente** via `inventory.json._featAllocations`
   (clés synthétiques `XC-Libraries` / `XC-Database`) sous `.alloc.lock`.
3. Écrit `{n}-Libraries.md` + `{n}-Database.md` (atomique), met à jour l'inventory.
4. Ligne chat `[REVERSE] Cross-cutting FEATs: …. (100%)`.

## Idempotence

Re-lancer écrase les mêmes fichiers (même `n` réutilisé depuis `_featAllocations`).
Aucune collision avec les FEATs fonctionnelles (Phase 3) : les `n` sont alloués
sur l'espace libre commun.

## Anti-derive

- **Aucun agent spawné** (script déterministe pur).
- Aucune invention : chaque item porte une evidence `file:line` issue des artefacts L1.
- Secrets masqués (`***`) dans les connection strings.

Voir `.sdd/docs/reverse-engineering-workflow.md` §5.6 (artefacts L1) + Annexe A (conformité FEAT).
