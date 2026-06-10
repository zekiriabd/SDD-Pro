---
command: sdd-reverse-full
phase: "1-4"
description: Orchestrateur Phase 1→4 reverse engineering. Séquence /sdd-reverse-init + /sdd-reverse-inventory + (/sdd-reverse-audit) + /sdd-reverse pour chaque U-N + (/sdd-reverse-ui pour chaque U-N). N'EST PAS UN AGENT — c'est un séquenceur de commandes (no-spawn rule §9 rules/reverse-engineering.md). Reprenable phase par phase.
loader: .claude/loader.reverse.yml
---

<!-- @llm-only-flags-file — tous les flags de /sdd-reverse-full sont
     interprétés par le LLM orchestrateur. Cette commande n'a pas de script
     Python dédié : elle invoque les sous-commandes (/sdd-reverse-init,
     /sdd-reverse-inventory, etc.) qui chacune ont leur propre parsing. -->

# /sdd-reverse-full {LegacyProject} [--skip-audit] [--skip-ui] [--units U-1,U-2,...] [--allow-low]

## Rôle

Pipeline complet reverse engineering Phase 0→4 sur un projet legacy. **Séquence des commandes** sans spawn d'agent direct — chaque commande appelée spawn son propre agent identifiable (séparation responsabilités).

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | requis | Sous-dossier `workspace/old/` |
| `--skip-audit` | flag | Saute Phase 2 (tech audit) — accélère, perd l'enrichissement DB schema |
| `--skip-ui` | flag | Saute Phase 4 (UI mockups) — utile si le Tech Lead préfère regénérer l'UI via FEAT seule |
| `--units U-N,U-M` | flag | Limite l'extraction (Phase 3 + 4) à un sous-ensemble d'unités. Par défaut : toutes les unités détectées |
| `--allow-low` | flag | ADV-6 : autorise FEATs `confidence: low` sans bannière bloquante. Audit-loggué. |
| `--json` | flag | Émet rapport final en JSON |

## Séquence (Phase 0→4)

```
STEP 0 — /sdd-reverse-init {LegacyProject}
   └─ bootstrap workspace/old/{P}/.sys/

STEP 1 — /sdd-reverse-inventory {LegacyProject}
   └─ Phase 1 : inventory.json + db-schema.json + language-detected.json
   └─ AGENT : reverse-inventory (Sonnet 4.6)

STEP 2 — (si --skip-audit absent)
   └─ /sdd-reverse-audit {LegacyProject}
       └─ Phase 2 : tech-audit.md + deps-graph.json + db-schema.merged.json
       └─ AGENT : reverse-tech-auditor (Sonnet 4.6)

STEP 3 — Pour CHAQUE U-N de inventory.json.units[] (séquentiel, jamais parallèle, ADV-2)
   └─ /sdd-reverse {U-N} [--allow-low]
       └─ Phase 3 : workspace/input/feats/{n}-{Name}.md
       └─ AGENT : reverse-functional-extractor (Opus 4.8)
       └─ Filtré par --units si présent

STEP 4 — (si --skip-ui absent)
   └─ Pour chaque U-N traitée en STEP 3
       └─ /sdd-reverse-ui {U-N}
           └─ Phase 4 : workspace/input/ui/{n}-{m}-{Name}.html
           └─ AGENT : reverse-ui-extractor (Opus 4.8)
           └─ Skip silencieux si U-N n'a pas de fichier UI evidence
```

## Reprenabilité

Chaque phase est **atomique et reprenable indépendamment**. Si `/sdd-reverse-full` est interrompu (Ctrl-C, crash, timeout) :
- Phases déjà complétées laissent leurs artefacts sur disque (`inventory.json`, FEAT files, etc.)
- Re-lancer `/sdd-reverse-full` reprend là où on en était (les commandes individuelles sont idempotentes)
- Re-lancer une phase isolée (`/sdd-reverse U-3`) écrase son output sans toucher les autres

## Phase 3 séquentielle stricte (ADV-2)

`/sdd-reverse-full` séquence Phase 3 unité par unité. Jamais en parallèle (le lock `.alloc.lock` empêcherait de toute façon). Pour de gros projets (10+ unités), cette séquence peut durer longtemps — préférer alors lancer manuellement quelques unités prioritaires d'abord.

## No-spawn d'agent direct (§9 règle)

`/sdd-reverse-full` n'a **PAS** d'agent dédié. C'est un script orchestrateur qui invoque les 5 autres commandes. Chaque commande spawn son propre agent. Traçabilité préservée : 1 invocation utilisateur visible = 1 chaîne de commandes claire.

## Émission chat

```
[REVERSE/FULL] Phase 0 OK (init). (3%)
[REVERSE/FULL] Phase 1 OK : {N} unités, {M} entités. (15%)
[REVERSE/FULL] Phase 2 OK : {anti-patterns} anti-patterns, {eol} EOL. (28%)
[REVERSE/FULL] Phase 3 (U-1/U-{N})... (45%)
[REVERSE/FULL] Phase 3 OK : {N} FEATs générées. (70%)
[REVERSE/FULL] Phase 4 OK : {M} mockups UI. (90%)
[REVERSE/FULL] {LegacyProject} → {N} FEATs reverse prêtes pour /sdd-full. (100%)
```

## Sortie

Toutes les sorties des commandes individuelles, agrégées :

```
workspace/old/{LegacyProject}/.sys/
├── inventory.{md,json}                       (Phase 1)
├── db-schema.{json,md}                       (Phase 1)
├── db-schema.enrichment.json                 (Phase 2, si --skip-audit absent)
├── db-schema.merged.json                     (Phase 2)
├── tech-audit.md                             (Phase 2)
├── deps-graph.json                           (Phase 2)
├── language-detected.json                    (Phase 1)
└── modules/{Name}/extraction.md              (Phase 3, log par unité)

workspace/input/feats/
└── {n}-{Name}.md                             (Phase 3, N fichiers)

workspace/input/ui/
└── {n}-{m}-{Name}.html                       (Phase 4, ≤5N fichiers, si --skip-ui absent)
```

## Anti-derive

- **No-spawn d'agent** : `/sdd-reverse-full` ne spawn aucun agent, séquence uniquement des commandes
- Phase 3 strictement séquentielle (ADV-2)
- Chaque commande appelée respecte ses propres pré-conditions (vérifie inventory.json présent, etc.)
- Idempotence préservée

Voir `.claude/docs/reverse-engineering-workflow.md` §1 (pipeline 7 phases) + §13.2 (V2 scope).
