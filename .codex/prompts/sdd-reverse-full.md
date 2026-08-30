<!-- GENERATED FROM .sdd/ (commande /sdd-reverse-full) — DO NOT EDIT -->
<!-- 'Orchestrateur COMPLET du reverse engineering (Phase 0→5). Séquence init + inventory + audit + paradigm + extraction (escalier 3a→3b→3c) + crosscut + review + synth + UI + questions + status — tous PAR DÉFAUT (décision Tech Lead 2026-06-13), opt-out via --skip-* / --minimal. SEULE exception : la parité (Phase 3.8) est opt-in via --with-parity (et ses artefacts vont dans workspace/parity/, jamais dans qa/). N''EST PAS UN AGENT — séquenceur de commandes (no-spawn rule §9 rules/reverse-engineering.md). Reprenable phase par phase.' -->
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

<!-- @llm-only-flags-file — tous les flags de /sdd-reverse-full sont
     interprétés par le LLM orchestrateur. Cette commande n'a pas de script
     Python dédié : elle invoque les sous-commandes (/sdd-reverse-init,
     /sdd-reverse-inventory, etc.) qui chacune ont leur propre parsing. -->

# /sdd-reverse-full {LegacyProject} [--minimal] [--skip-audit] [--skip-paradigm] [--skip-synth] [--with-parity] [--skip-ui] [--skip-review] [--skip-questions] [--interactive] [--skip-status] [--synth-level essentiel|complet|detaille] [--units U-1,U-2,...] [--max-parallel N] [--no-cache] [--sequential] [--json]

## Rôle

Pipeline **complet** de reverse engineering Phase 0→5 sur un projet legacy.
**Séquence des commandes** sans spawn d'agent direct — chaque commande appelée
spawn son propre agent identifiable (séparation responsabilités).

> **Refonte 2026-06-13 (décision Tech Lead) — quasi-tout par défaut, SAUF parité.**
> Avant cette date, `--with-paradigm` / `--with-parity` / `--with-questions` /
> `--with-synth` étaient tous opt-in. Désormais **audit + paradigm + synth +
> review + UI + questions + status s'exécutent par défaut** (opt-out `--skip-*`
> ou `--minimal`). **Exception : la parité (Phase 3.8) reste opt-in via
> `--with-parity`** (décision Tech Lead 2026-06-13 — non désirée par défaut, et
> ses `.feature` vont dans `workspace/parity/`, JAMAIS dans `qa/` qui est
> réservé aux tests). Les anciens flags `--with-paradigm|synth|questions` restent
> acceptés en alias no-op (rétro-compat) ; `--with-parity` est, lui, fonctionnel.

> **Audit 2026-06-09/10** : **--skip-crosscut** **retiré** (C3 — le crosscut
> Librairies + Database est OBLIGATOIRE, jamais skippable). **--allow-low**
> **retiré** (C9 — voie officielle : `check_reverse_feat_for_full.py
> --allow-reverse-low` côté /sdd-full).

## Args

| Arg | Type | Défaut | Description |
|---|---|---|---|
| `{LegacyProject}` | requis | — | Sous-dossier `workspace/old/` |
| `--minimal` | flag | off | Mode lean : équivaut à `--skip-paradigm --skip-synth --skip-questions`. Garde le cœur (init+inventory+audit+extraction+crosscut+review+UI+status). Pour un run rapide / itératif |
| `--skip-audit` | flag | off (phase active) | Saute Phase 2 (tech audit) — perd l'enrichissement DB schema |
| `--skip-paradigm` | flag | off (phase active) | Saute Phase 2.7 (gap paradigme + curation MIGRATE/DISCARD/HUMAN-DECISION) |
| `--skip-synth` | flag | off (phase active) | Saute Phase 3.7 (synthèse système : C4 + ERD + soul.md, déterministe) |
| `--with-parity` | flag | **off** | **Opt-in** (décision Tech Lead 2026-06-13 — parité exclue par défaut) : active Phase 3.8 (specs Gherkin de parité comportementale → `workspace/parity/`, jamais dans `qa/`) |
| `--skip-ui` | flag | off (phase active) | Saute Phase 4 (génération des interfaces / mockups HTML) |
| `--skip-review` | flag | off (phase active) | Saute Phase 3.6 (revue de complétude back, `reverse-completeness-reviewer`) |
| `--skip-questions` | flag | off (phase active) | Saute Phase 3.9 (génération `questions.md` — boucle de validation humaine) |
| `--interactive` | flag | off | **Ferme la boucle humaine dans le run** (C3) : à Phase 3.9, pose les questions ouvertes en session + ingère les réponses, au lieu de s'arrêter sur `questions.md`. Sans effet en batch/CI (dégrade en génération seule) |
| `--skip-status` | flag | off (phase active) | Saute le diagnostic final `/sdd-reverse-status` |
| `--synth-level` | `essentiel\|complet\|detaille` | `complet` | Niveau de synthèse passé à `/sdd-reverse-synth` (ignoré si `--skip-synth`) |
| `--units U-N,U-M` | flag | toutes | Limite l'extraction (Phase 3 + 4 + parité) à un sous-ensemble d'unités |
| `--max-parallel N` | flag | 3 | Borne de parallélisme Phase 3 (range 1-12, aligné `ownership.md §5`) |
| `--no-cache` | flag | off | Force la ré-extraction de toutes les unités (ignore `extraction-cache.json`, L5) |
| `--sequential` | flag | off | Force la Phase 3 séquentielle (mode legacy ADV-2, désactive le parallélisme) |
| `--json` | flag | off | Émet le rapport final en JSON |
| ~~`--with-audit\|paradigm\|synth\|parity\|questions`~~ | alias no-op | — | **Déprécié** : ces phases sont actives par défaut. Acceptés sans effet (rétro-compat) |

> **Note coût** : le run complet est volontairement exhaustif (paradigme +
> parité + synthèse + UI + questions par-dessus l'extraction). Pour un projet
> à beaucoup d'unités, `--minimal` ou `--units` borne la dépense ; `--max-parallel`
> et le cache d'extraction (L5) accélèrent les ré-exécutions.

## Séquence (Phase 0→5 — tout actif par défaut)

> **Numérotation phase-based, pas séquentielle** : les numéros de STEP reprennent
> les numéros de PHASE du workflow reverse (2.5 pré-allocation, 3.5 crosscut, 3.9
> questions…), donc ils ne sont pas monotones à la lecture. Ordre d'exécution réel :
> 0 → 1 → 2 → 2.7 → 2.5 → 3 → 3.5 → 3.6 → 3.7 → 3.8 → 4 → 3.9 → 5 → 5.bis.

```
STEP 0 — /sdd-reverse-init {LegacyProject}
   └─ bootstrap workspace/old/{P}/.sys/

STEP 1 — /sdd-reverse-inventory {LegacyProject}
   └─ Phase 1 : inventory.json (+ code-graph/data-access/config/dependencies, L0-L1)
   └─ AGENT : reverse-inventory (tier `balanced`)

STEP 2 — Tech audit (SAUF --skip-audit)
   └─ /sdd-reverse-audit {LegacyProject}   → tech-audit.md + db-schema.merged.json
   └─ AGENT : reverse-tech-auditor (tier `balanced`)

STEP 2.7 — Gap paradigme + curation (SAUF --skip-paradigm)
   └─ /sdd-reverse-paradigm {LegacyProject}
   └─ AGENT : reverse-paradigm-advisor (tier `balanced`)
   └─ paradigm-decision.md (gap legacy↔cible, Décision: PENDING) + curation.md
      (MIGRATE/DISCARD/HUMAN-DECISION — informational, jamais destructif ;
      verdicts MIGRATE → suggestion --units pour un run ciblé)

STEP 2.5 — PRÉ-ALLOCATION déterministe (L5 — débloque le parallélisme)
   └─ python .sdd/python/sdd_reverse_scripts/preallocate_feats.py --project workspace/old/{P}
       └─ fige (n, Name) de TOUTES les unités dans inventory.json (_featAllocations)
       └─ après ce STEP, les extractions Phase 3 sont parallel-safe (cf. rules §8.2)

STEP 3 — Extraction Phase 3 (PARALLÈLE BORNÉ par défaut, L5)
   Pour chaque U-N de inventory.json.units[] (filtré par --units) :
     a. Cache (L5, sauf --no-cache) :
        python .sdd/python/sdd_reverse_scripts/update_extraction_cache.py \
            --project workspace/old/{P} --unit {U-N} --check
        └─ exit 0 (HIT) → SKIP l'unité ; exit 1 (MISS) → extraire
     b. Sinon dispatcher /sdd-reverse {U-N}  (SÉQUENCEUR escalier 3a→3b→3c)
        └─ /sdd-reverse-analyze {U-N}  → AGENT reverse-tech-analyst (3a, tier routé par complexité) → plans/{n}-{FeatName}.analysis.md
        └─ /sdd-reverse-stories {U-N}  → AGENT reverse-us-writer (3b, tier `balanced`) → us/{n}-{m}-{Name}.md
        └─ /sdd-reverse-feat {U-N}     → AGENT reverse-feat-composer (3c, tier routé par complexité) → feats/{n}-{FeatName}.md
           └─ enregistre le cache en fin de 3c (--save, C4)
   Dispatch : par lots de --max-parallel (défaut 3) dans un seul message d'agents.
   Si --sequential OU pré-allocation absente → 1 unité à la fois (mode ADV-2 §8.1).

STEP 3.5 — FEATs transversales (L3 — OBLIGATOIRE, jamais skippable, audit C3)
   └─ python .sdd/python/sdd_reverse_scripts/generate_crosscutting_feats.py --project workspace/old/{P}
       └─ {n}-Libraries.md + {n}-Database.md (déterministe, 0 token)
       └─ porte les procédures stockées, requêtes SQL, connection strings et
          librairies que les FEATs par unité ne structurent pas.

STEP 3.6 — Revue de complétude back (SAUF --skip-review)
   Pour chaque U-N extraite :
     └─ /sdd-reverse-review {U-N}   (commande wrapper — M11 no-spawn §9)
        └─ AGENT : reverse-completeness-reviewer (informational, jamais bloquant)
           └─ signale repositories/services/viewmodels/SQL/procs non capturés
              ([REVERSE_COMPLETENESS_GAP])

STEP 3.7 — Synthèse système (SAUF --skip-synth)
   └─ /sdd-reverse-synth {LegacyProject} [--doc-level {--synth-level}]
       └─ C4 (contexte/conteneurs/composants) + ERD complet + soul.md
       └─ no-spawn, 0 token, lecture seule sur .sys/*.json ; écrit UNIQUEMENT
          sous .sys/synthesis/ (jamais feats/ — invisible à /sdd-full)

STEP 3.8 — Specs de parité comportementale (SI --with-parity — opt-in, off par défaut)
   Pour chaque FEAT {n} extraite (filtré par --units) :
     └─ /sdd-reverse-parity {n}   → AGENT reverse-parity-inspector (tier `balanced`)
        └─ workspace/parity/feat-{n}/*.feature + parity-map.md
        └─ gate déterministe validate_parity_features.py (structure WARN,
           couverture informational [REVERSE_PARITY_COVERAGE_GAP])

STEP 4 — Génération des interfaces / UI (SAUF --skip-ui)
   Pour chaque U-N extraite (kind ∈ {page,form,grid,wizard}) — parallèle borné :
     └─ /sdd-reverse-ui {U-N}   → workspace/ui/{n}-{m}-{Name}.html
        └─ AGENT : reverse-ui-extractor (tier `deep`)
        └─ Skip silencieux si U-N n'a pas de fichier UI evidence (kind api/module)

STEP 3.9 — Boucle de validation humaine (SAUF --skip-questions)
   └─ /sdd-reverse-questions {LegacyProject}   (mode generate)
   └─ AGENT : reverse-clarifier (tier `balanced`)
   └─ consolide les gaps (complétude 3.6, traçabilité, items medium/low,
      AC non dérivables 3.8, curation HUMAN-DECISION 2.7) en
      workspace/old/{P}/.sys/questions.md (Q-N stables)
   └─ SANS --interactive (défaut, batch/CI) : STOP propre. Le Tech Lead répond
      aux Q-N puis lance /sdd-reverse-questions {P} --ingest hors run (§10).
   └─ AVEC --interactive (clôture C3, session interactive) : enchaîne
      /sdd-reverse-questions {P} --interactive → pose les Q-N ouvertes
      (AskUserQuestion) + écrit les réponses (reverse_questions_io) + --ingest.
      La boucle se ferme DANS le run ; les FEATs clarifiées montent en `high`.

STEP 5 — Diagnostic final (SAUF --skip-status)
   └─ /sdd-reverse-status {LegacyProject}
       └─ état des phases + liste FEATs reverse ([REV]/[REV⚠️]) + gaps en suspens
          (questions.md non remplies, curation PENDING, confidence < high)
       └─ read-only, déterministe, jamais bloquant — clôture le run par un
          récapitulatif actionnable.

STEP 5.bis — Cahier des charges (best-effort, jamais bloquant)
   └─ /spec-book
       └─ (ré)humanise les FEATs reverse nouvellement produites puis réassemble
          workspace/docs/cahier-des-charges.docx (langage gérant, non-IT).
       └─ idempotent + incrémental (cache par hash) ; échec = WARN, n'interrompt
          pas le run. Les FEATs reverse confidence < high sont marquées « à valider ».
```

## Mode `--minimal`

`--minimal` = `--skip-paradigm --skip-synth --skip-questions` (la parité est déjà off par défaut — opt-in via `--with-parity`).
Conserve : init + inventory + audit + extraction (escalier) + crosscut + review
+ UI + status. C'est l'ancien comportement « extraction-only enrichi », utile
pour un premier passage rapide ou une itération ciblée. Les `--skip-*` explicites
se cumulent avec `--minimal`.

## Reprenabilité

Chaque phase est **atomique et reprenable indépendamment**. Si `/sdd-reverse-full`
est interrompu (Ctrl-C, crash, timeout) :
- Les phases déjà complétées laissent leurs artefacts sur disque.
- Re-lancer `/sdd-reverse-full` reprend là où on en était (commandes idempotentes ;
  le cache d'extraction L5 skippe les unités inchangées).
- Re-lancer une phase isolée (`/sdd-reverse U-3`, `/sdd-reverse-ui U-3`, etc.)
  écrase son output sans toucher les autres.

## Phase 3 : parallèle borné après pré-allocation (L5)

Depuis L5, la **pré-allocation déterministe** (STEP 2.5) fige `(n, FeatName)` puis la
Phase 3 dispatche en **parallèle borné** (`--max-parallel`, défaut 3) : chaque
unité écrit un fichier disjoint, sans contention de lock (`rules/reverse-engineering.md §8.2`).
`--sequential` rétablit le comportement strict (ADV-2 §8.1), utile en debug.

## No-spawn d'agent direct (§9 règle)

`/sdd-reverse-full` n'a **PAS** d'agent dédié. C'est un séquenceur qui invoque les
sous-commandes ; chacune spawn son propre agent. Traçabilité : 1 invocation
utilisateur = 1 chaîne de commandes claire.

## Émission chat

Label `[REVERSE]` strict (table fermée `output-protocol.md §3` — seuls les
suffixes /FIXING /SKIP /WARN /FAIL sont admis, jamais `/FULL`) :

```
[REVERSE] Phase 0 OK (init). (3%)
[REVERSE] Phase 1 OK : {N} unités, {M} entités. (12%)
[REVERSE] Phase 2 OK : {anti-patterns} anti-patterns, {eol} EOL. (20%)        # sauf --skip-audit
[REVERSE] Phase 2.7 OK : gap paradigme documenté, {k} unités curées. (26%)    # sauf --skip-paradigm
[REVERSE] Phase 3 (U-1/U-{N})... (40%)
[REVERSE] Phase 3 OK : {N} FEATs générées. (58%)
[REVERSE] Phase 3.5 OK : crosscut Libraries + Database. (62%)
[REVERSE] Phase 3.6 OK : complétude {complete/partial} sur {N} unités. (68%)  # sauf --skip-review
[REVERSE] Phase 3.7 OK : synthèse {synth-level} (C4 + ERD + soul). (74%)       # sauf --skip-synth
[REVERSE] Phase 3.8 OK : specs de parité sur {N} FEATs. (82%)                  # SI --with-parity (opt-in)
[REVERSE] Phase 4 OK : {M} interfaces (mockups HTML). (90%)                    # sauf --skip-ui
[REVERSE] Phase 3.9 OK : questions.md généré ({Q} questions à remplir). (96%)    # sauf --skip-questions
[REVERSE] {LegacyProject} → {N} FEATs reverse + {M} UI ; {gaps} à arbiter. (100%)
```

## Sortie

Toutes les sorties des commandes individuelles, agrégées :

```
workspace/old/{LegacyProject}/.sys/
├── inventory.{md,json}                       (Phase 1)
├── db-schema.{json,md}                       (Phase 1)
├── db-schema.enrichment.json                 (Phase 2, sauf --skip-audit)
├── db-schema.merged.json                     (Phase 2)
├── tech-audit.md                             (Phase 2)
├── deps-graph.json                           (Phase 2)
├── language-detected.json                    (Phase 1)
├── paradigm-decision.md, curation.md         (Phase 2.7, sauf --skip-paradigm)
├── questions.md                              (Phase 3.9, sauf --skip-questions)
├── modules/{Name}/extraction.md              (Phase 3, log par unité)
└── synthesis/                                (Phase 3.7, sauf --skip-synth)
    ├── c4-context.md, c4-containers.md, c4-components.md
    ├── erd-complete.md
    ├── soul.md
    └── manifest.json

workspace/feats/
├── {n}-{FeatName}.md                             (Phase 3, N fichiers)
└── {n}-{Libraries,Database}.md               (Phase 3.5, crosscut obligatoire)

workspace/ui/
└── {n}-{m}-{Name}.html                       (Phase 4, ≤5N fichiers, sauf --skip-ui)

workspace/parity/feat-{n}/
├── *.feature                                 (Phase 3.8, SI --with-parity ; jamais dans qa/)
└── parity-map.md
```

## Anti-derive

- **No-spawn d'agent** : `/sdd-reverse-full` ne spawn aucun agent, séquence uniquement des commandes
- **Quasi-tout actif par défaut** : opt-out explicite (`--skip-*` / `--minimal`). **Exception : la parité (3.8) est opt-in** (`--with-parity`) et n'écrit **jamais** dans `qa/` (réservé aux tests) — décision Tech Lead 2026-06-13
- Phase 3 parallèle borné **après pré-allocation STEP 2.5** ; séquentielle stricte (ADV-2 §8.1) si `--sequential` ou pré-allocation absente
- Crosscut STEP 3.5 non skippable (C3)
- Phase 3.9 `--ingest` (ré-injection des réponses) reste **manuelle** : le run génère `questions.md`, l'humain répond et ré-injecte ensuite (jamais d'invention de réponse)
- Chaque commande appelée respecte ses propres pré-conditions (vérifie inventory.json présent, etc.)
- Idempotence préservée

Voir `.sdd/docs/reverse-engineering-workflow.md` §1 (pipeline 7 phases) + §13.2 (V2 scope).
