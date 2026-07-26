<!-- GENERATED FROM .sdd/ (commande /sdd-proc-reverse-full) — DO NOT EDIT -->
<!-- "Reverse engineering de TOUS les objets SQL exécutables d'une base (lecture seule) — procédures stockées, fonctions, vues et triggers (P0.1 2026-07-24). Introspecte via la connection string de stack.md (## Active Database), regroupe les objets en modules, génère 1 User Story par objet SQL et 1 FEAT par module. Multi-dialecte (SQL Server complet ; PostgreSQL procs/fonctions). Ne modifie JAMAIS la base." -->
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

# /sdd-proc-reverse-full [--project DB] [--json]

## Rôle

Orchestrateur du reverse engineering **base de données → FEATs**. À partir de la
connexion déclarée dans `stack.md ## Active Database`, il lit **toutes** les
procédures stockées en **lecture seule**, les regroupe en modules métier, et
produit des FEATs SDD_Pro standard consommables par `/sdd-full`.

```
stack.md (## Active Database)
   └─[Phase 1 introspect READ-ONLY]─► .sys/proc-snapshot/*.sql + db-introspection.json + inventory.json
        └─[rung 1 : reverse-sql-analyst × module]─► us/{n}-{m}-{Name}.md   (1 proc = 1 US)
             └─[rung 2 : build_proc_feats déterministe]─► feats/{n}-{Module}.md  (1 module = 1 FEAT)
                  └─ validate_reverse_feat ─► REVERSE-GATE ─► /sdd-full
```

## Modèle (confirmé)

- **1 procédure = 1 User Story** · **1 module = 1 FEAT** (procédures d'un même objet métier).
- **Remontée stricte** : la FEAT est composée depuis les US, jamais en relisant le corps T-SQL.

## Garanties lecture seule (non négociable)

Le moteur n'émet **que** des `SELECT` de catalogue (`sys.sql_modules`,
`sys.procedures`, …) + `OBJECT_DEFINITION`, validés par `readonly_guard`. **Jamais**
`DROP`/`DELETE`/`TRUNCATE`/`ALTER`/`INSERT`/`UPDATE`/`MERGE`, **jamais** d'exécution
de procédure. Cf. `[DB_STRUCTURE_CHANGE_FORBIDDEN]` + invariant `reverse-db-readonly`.
Recommandation DBA : login dédié `GRANT VIEW DEFINITION` + `db_datareader` (défense en profondeur).

## Pré-conditions

1. `stack.md` contient `## Active Database` complet (`DatabaseType`, `DB_HOST`,
   `DB_NAME`, +`DB_PORT/DB_USER/DB_PASSWORD`). Sinon → `[REVERSE_DB_CONFIG_MISSING]`.
2. Driver lecture seule disponible (`pip install -e .sdd/python[reverse-db]`,
   ODBC Driver 18 pour SQL Server). Sinon → `[REVERSE_DB_UNREACHABLE]`.
3. `DatabaseType` supporté (MVP : SQL Server ; Postgres/Oracle/MySQL = roadmap).

## Actions

1. **Phase 1 (déterministe, 0 token)** :
   `python .sdd/python/sdd_reverse_scripts/reverse_proc_introspect.py --full [--project DB]`
   → snapshot + `db-introspection.json` + `inventory.json` (units = modules,
   `(n, Name)` pré-alloués). Erreur DB → STOP avec la classe `[REVERSE_DB_*]`.
2. **Routage par complexité (0 token, token-efficient)** :
   `python .sdd/python/sdd_reverse_scripts/build_proc_us.py --project DB --all --json`
   - génère **déterministiquement** (0 token LLM) toutes les US des procédures
     **simples** (CRUD/SELECT sans branche/SQL dynamique/erreur) — ~70-80 % d'une base typique ;
   - retourne `needs_llm` = la liste des procédures **complexes** (logique métier).
3. **Cache** : sauter les procédures dont le snapshot est inchangé ET dont l'US
   existe (`reverse_cache`/`update_extraction_cache`, fail-safe : doute = ré-extraire).
4. **rung 1 (LLM, ciblé)** : pour chaque entrée de `needs_llm` **uniquement**, spawn
   `Agent(reverse-sql-analyst)` avec `{U-N} --proc {fq}`. **Parallèle borné**
   (`MaxParallel`, défaut 3 — pré-allocation faite, écritures US disjointes, parallel-safe §8.2).
   Les procédures simples ne consomment **aucun token**.
5. **rung 2 (composition des FEAT modules)** :
   - **Défaut (déterministe, 0 token)** :
     `python .sdd/python/sdd_reverse_scripts/build_proc_feats.py --project DB --all`
     → 1 FEAT par module (remontée depuis les US + inventaire), confidence min-monotone.
   - **Opt-in LLM (`SDD_REVERSE_FEAT_LLM=1`)** : pour chaque module, spawn
     `Agent(reverse-sql-feat-composer)` avec `{U-N}` → FEAT métier synthétisée
     (démotion plomberie, narratif transverse, parité avec l'escalier code 3c).
     Parallèle borné (`MaxParallel`, FEATs disjointes). Même gate
     `validate_reverse_feat.py`. À réserver aux modules à forte logique métier
     (le déterministe suffit pour du CRUD).
6. **Validation** : `validate_reverse_feat.py` sur chaque FEAT ; `confidence != high`
   → REVERSE-GATE `allow-sdd-full=false` (revue humaine).
7. Ligne chat finale `[REVERSE] DB {DB} → {p} procédures, {m} modules/FEAT, {u} US. (100%)`.

## Sortie

```
workspace/old/{DB}/.sys/proc-snapshot/{schema}.{proc}.sql   (snapshot lecture seule, interne)
workspace/old/{DB}/.sys/db-introspection.json               (métadonnées + signaux, sans secret)
workspace/old/{DB}/.sys/inventory.json                      (units=modules, allocations)
workspace/us/{n}-{m}-{Name}.md                       (1 par procédure)
workspace/feats/{n}-{Module}.md                       (1 par module)
```

## Anti-derive

- Lecture seule absolue ; le mot de passe n'est jamais loggé ni persisté.
- No-spawn d'agent par les agents (la commande séquence/ spawn, pas les agents).
- 1 proc = 1 US, 1 module = 1 FEAT ; pas de fusion, pas d'invention (bias toward present).
- Idempotence : re-run réutilise `(n, Name)` via `_featAllocations`.

Voir `.sdd/docs/reverse-proc-engineering.audit.md` + `.sdd/rules/reverse-engineering.md`.
