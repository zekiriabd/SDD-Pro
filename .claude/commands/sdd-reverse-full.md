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

# /sdd-reverse-full {LegacyProject} [--skip-audit] [--skip-ui] [--skip-review] [--units U-1,U-2,...] [--max-parallel N] [--no-cache] [--sequential]

## Rôle

Pipeline complet reverse engineering Phase 0→4 sur un projet legacy. **Séquence des commandes** sans spawn d'agent direct — chaque commande appelée spawn son propre agent identifiable (séparation responsabilités).

> **Audit 2026-06-09/10** : **--skip-crosscut** **retiré** (C3 — le crosscut
> Librairies + Database est désormais OBLIGATOIRE : sans lui, 21 procédures
> stockées + 53 requêtes + 3 connection strings du run EDI n'existaient dans
> aucune FEAT). **--allow-low** **retiré** (C9 — flag fantôme contredit par le
> validateur ; voie officielle : `check_reverse_feat_for_full.py
> --allow-reverse-low` côté /sdd-full).

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | requis | Sous-dossier `workspace/old/` |
| `--skip-audit` | flag | Saute Phase 2 (tech audit) — accélère, perd l'enrichissement DB schema |
| `--skip-ui` | flag | Saute Phase 4 (UI mockups) — utile si le Tech Lead préfère regénérer l'UI via FEAT seule |
| `--skip-review` | flag | Saute la revue de complétude back (L5, `reverse-completeness-reviewer`) |
| `--units U-N,U-M` | flag | Limite l'extraction (Phase 3 + 4) à un sous-ensemble d'unités. Par défaut : toutes |
| `--max-parallel N` | flag | Borne de parallélisme Phase 3 (défaut 3, range 1-12, aligné `ownership.md §5`) |
| `--no-cache` | flag | Force la ré-extraction de toutes les unités (ignore `extraction-cache.json`, L5) |
| `--sequential` | flag | Force la Phase 3 séquentielle (mode legacy ADV-2, désactive le parallélisme) |
| `--json` | flag | Émet rapport final en JSON |

## Séquence (Phase 0→4, industrialisée L5)

```
STEP 0 — /sdd-reverse-init {LegacyProject}
   └─ bootstrap workspace/old/{P}/.sys/

STEP 1 — /sdd-reverse-inventory {LegacyProject}
   └─ Phase 1 : inventory.json (+ code-graph/data-access/config/dependencies, L0-L1)
   └─ AGENT : reverse-inventory (Sonnet 4.6)

STEP 2 — (si --skip-audit absent)
   └─ /sdd-reverse-audit {LegacyProject}   → tech-audit.md + db-schema.merged.json

STEP 2.5 — PRÉ-ALLOCATION déterministe (L5 — débloque le parallélisme)
   └─ python .claude/python/sdd_reverse_scripts/preallocate_feats.py --project workspace/old/{P}
       └─ fige (n, Name) de TOUTES les unités dans inventory.json (_featAllocations)
       └─ après ce STEP, les extractions Phase 3 sont parallel-safe (cf. rules §8.2)

STEP 3 — Extraction Phase 3 (PARALLÈLE BORNÉ par défaut, L5)
   Pour chaque U-N de inventory.json.units[] (filtré par --units) :
     a. Cache (L5, sauf --no-cache) :
        python .claude/python/sdd_reverse_scripts/update_extraction_cache.py \
            --project workspace/old/{P} --unit {U-N} --check
        └─ exit 0 (HIT) → SKIP l'unité ; exit 1 (MISS) → extraire
     b. Sinon dispatcher /sdd-reverse {U-N}  (SÉQUENCEUR escalier 3a→3b→3c)
        └─ /sdd-reverse-analyze {U-N}  → AGENT reverse-tech-analyst (3a, Opus 4.8) → output/plans/{n}-{Name}.analysis.md
        └─ /sdd-reverse-stories {U-N}  → AGENT reverse-us-writer (3b, Opus 4.8)   → output/us/{n}-{m}-{Name}.md
        └─ /sdd-reverse-feat {U-N}     → AGENT reverse-feat-composer (3c, Opus 4.8) → input/feats/{n}-{Name}.md
           └─ enregistre le cache en fin de 3c (--save, C4)
   Dispatch : par lots de --max-parallel (défaut 3) dans un seul message d'agents.
   Si --sequential OU pré-allocation absente → 1 unité à la fois (mode ADV-2 §8.1).

STEP 3.5 — FEATs transversales (L3 — OBLIGATOIRE depuis l'audit C3 2026-06-09)
   └─ python .claude/python/sdd_reverse_scripts/generate_crosscutting_feats.py --project workspace/old/{P}
       └─ {n}-Libraries.md + {n}-Database.md (déterministe, 0 token)
       └─ porte les procédures stockées, requêtes SQL, connection strings et
          librairies que les FEATs par unité ne structurent pas — sans ce STEP
          la couche données n'existe dans AUCUN artefact consommable.

STEP 3.6 — Revue de complétude back (L5, si --skip-review absent)
   Pour chaque U-N extraite :
     └─ /sdd-reverse-review {U-N}   (commande wrapper — M11 no-spawn §9)
        └─ AGENT : reverse-completeness-reviewer (informational, jamais bloquant)
           └─ signale repositories/services/viewmodels/SQL/procs non capturés
              ([REVERSE_COMPLETENESS_GAP])

STEP 4 — (si --skip-ui absent)
   └─ Pour chaque U-N extraite (kind ∈ {page,form,grid,wizard}) — parallèle borné aussi
       └─ /sdd-reverse-ui {U-N}   → workspace/input/ui/{n}-{m}-{Name}.html
       └─ Skip silencieux si U-N n'a pas de fichier UI evidence (kind api/module)
```

## Reprenabilité

Chaque phase est **atomique et reprenable indépendamment**. Si `/sdd-reverse-full` est interrompu (Ctrl-C, crash, timeout) :
- Phases déjà complétées laissent leurs artefacts sur disque (`inventory.json`, FEAT files, etc.)
- Re-lancer `/sdd-reverse-full` reprend là où on en était (les commandes individuelles sont idempotentes)
- Re-lancer une phase isolée (`/sdd-reverse U-3`) écrase son output sans toucher les autres

## Phase 3 : parallèle borné après pré-allocation (L5)

Depuis L5, `/sdd-reverse-full` exécute la **pré-allocation déterministe** (STEP 2.5)
puis dispatche la Phase 3 en **parallèle borné** (`--max-parallel`, défaut 3) :
chaque unité a un `(n, Name)` figé et écrit un fichier disjoint, sans contention
de lock (cf. `rules/reverse-engineering.md §8.2`). Pour de gros projets (40+ unités)
c'est l'accélération principale vs le séquentiel legacy.

`--sequential` rétablit l'ancien comportement strict (ADV-2 §8.1), utile en debug.
Le cache d'extraction (L5, STEP 3a) skippe les unités inchangées.

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
- Phase 3 parallèle borné **après pré-allocation STEP 2.5** ; séquentielle stricte (ADV-2 §8.1) si `--sequential` ou pré-allocation absente (M13 — doc alignée sur §8.2)
- Crosscut STEP 3.5 non skippable (C3)
- Chaque commande appelée respecte ses propres pré-conditions (vérifie inventory.json présent, etc.)
- Idempotence préservée

Voir `.claude/docs/reverse-engineering-workflow.md` §1 (pipeline 7 phases) + §13.2 (V2 scope).
