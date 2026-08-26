<!-- GENERATED FROM .sdd/ (commande /sdd-db-reverse-full) — DO NOT EDIT -->
<!-- "Reverse engineering de TOUS les objets SQL exécutables d'une base (lecture seule) — procédures stockées, fonctions, vues et triggers (P0.1 2026-07-24). Introspecte via la connection string de stack.md (## Active Database), regroupe les objets en modules, génère 1 User Story par objet SQL et 1 FEAT par module. Multi-dialecte — SQL Server + PostgreSQL (live-validés), Oracle + MySQL/MariaDB (scaffold-validés, runtime live pending). Ne modifie JAMAIS la base." -->
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

# /sdd-db-reverse-full [--project DB] [--json]

## Rôle

Orchestrateur du reverse engineering **base de données → FEATs**. À partir de la
connexion déclarée dans `stack.md ## Active Database`, il lit **toutes** les
procédures stockées en **lecture seule**, les regroupe en modules métier, et
produit des FEATs SDD_Pro standard consommables par `/sdd-full`.

```
stack.md (## Active Database)  ← config + variables d'environnement (${VAR} via .env)
   └─[Phase 1 introspect READ-ONLY]─► .sys/proc-snapshot/*.sql + db-introspection.json
        │                              + .sys/schema-snapshot/*.sql + db-schema.json + inventory.json
        └─[rung 1 : reverse-sql-analyst × module]─► us/{n}-{m}-{Name}.md   (1 objet SQL = 1 US)
             └─[rung 2 : build_proc_feats déterministe]─► feats/{n}-{Module}.md  (1 module = 1 FEAT)
                  └─ validate_reverse_feat + check_reverse_feat_for_full ─► REVERSE-GATE ─► /sdd-full
```

## Modèle (confirmé)

- **1 objet SQL = 1 User Story** · **1 module = 1 FEAT** (objets d'un même objet métier).
- **Remontée stricte** : la FEAT est composée depuis les US + l'inventaire, jamais en
  relisant le corps SQL. L'assembleur lit réellement les US (titre métier, ACs,
  mode d'extraction) et y écrit en retour `Covers:` + le `Parent FEAT hash`.

## Objets couverts

| Famille | Couverture |
|---|---|
| Procédures, fonctions (scalaires / inline / table) | corps analysé → 1 US |
| Vues, triggers | corps analysé → 1 US |
| Packages Oracle (spec + body) | corps analysé → 1 US |
| **Tables, colonnes, types, PK/FK, index, contraintes CHECK** | **introspection live → `db-schema.json` (`completeness: live`)** |
| **Jobs / scheduler, séquences, synonymes, linked servers, types utilisateur** | **introspection live → `catalogObjects`** |

Les contraintes `CHECK` et les jobs sont les deux gisements de règles métier les plus
souvent invisibles aux applications : un job porte du comportement **planifié**
(recalcul nocturne, purge, import) que rien dans le code applicatif ne révèle.

## Garanties lecture seule (non négociable)

Le moteur n'émet **que** des `SELECT` de catalogue (`sys.sql_modules`,
`sys.procedures`, …) + `OBJECT_DEFINITION`, validés par `readonly_guard`. **Jamais**
`DROP`/`DELETE`/`TRUNCATE`/`ALTER`/`INSERT`/`UPDATE`/`MERGE`, **jamais** d'exécution
de procédure. Cf. `[DB_STRUCTURE_CHANGE_FORBIDDEN]` + invariant `reverse-db-readonly`.
Recommandation DBA : login dédié `GRANT VIEW DEFINITION` + `db_datareader` (défense en profondeur).

## Pré-conditions

1. `stack.md` contient `## Active Database` complet (`DatabaseType`, `DB_HOST`,
   `DB_NAME`, +`DB_PORT/DB_USER/DB_PASSWORD`). Les valeurs peuvent être des
   placeholders `${VAR}` résolus depuis un `.env` (cherché à partir de
   l'emplacement de `stack.md` : `workspace/stack/` → `workspace/` → racine repo)
   puis depuis l'environnement réel, qui a priorité. Sinon →
   `[REVERSE_DB_CONFIG_MISSING]`, dont le message liste les chemins `.env` fouillés.
2. Driver lecture seule disponible (`pip install -e .sdd/python[reverse-db]`,
   ODBC Driver 18 pour SQL Server). Sinon → `[REVERSE_DB_UNREACHABLE]`.
3. `DatabaseType` supporté : **SQL Server** et **PostgreSQL** (live-validés),
   **Oracle** et **MySQL/MariaDB** (scaffold-validés — requêtes read-only et flux
   hors ligne testés, runtime live à valider sur une base de test avant prod).
   DB2 et SQLite sont reconnus mais refusés avec un message explicite.

## Périmètre et coût

Sur une base volumineuse, borner le run — sans quoi le plafond de coût global
(`[COST_CAP_EXCEEDED]`) le coupera au milieu :

| Flag | Effet |
|---|---|
| `--schema dbo,sales` | restreint aux schémas cités |
| `--include 'usp_Invoice*'` | ne garde que les objets matchant (glob, répétable) |
| `--exclude 'usp_Debug*'` | écarte les objets matchant |
| `--limit N` | plafonne le nombre d'objets — **nomme ce qu'il a écarté** (pas de troncature silencieuse) |
| `--no-schema` | saute la lecture de structure (tables/colonnes/jobs) |

La reprise repose sur le **cache par objet** : un objet dont le corps est inchangé
et dont l'US existe n'est pas ré-extrait (`--no-cache` pour forcer). C'est ce qui
rend un second run quasi gratuit après une interruption.

## Actions

1. **Phase 1 (déterministe, 0 token)** :
   `python .sdd/python/sdd_reverse_scripts/reverse_proc_introspect.py --full [--project DB]`
   → snapshot + `db-introspection.json` + `inventory.json` (units = modules,
   `(n, Name)` pré-alloués). Erreur DB → STOP avec la classe `[REVERSE_DB_*]`.
1.bis **Découpage en modules — stratégie AUTO** (déterministe, 0 token ; c'est la
   décision la plus structurante du reverse DB : elle fixe le nombre de FEATs) :
   - **profilage du corpus** : la structure de nommage est *mesurée* sur les noms
     réels de la base (fréquence documentaire × position), pas déclarée — les
     marqueurs de type/sous-système (`SP_`, `STP_`, `BI_`, `Prc`) et les verbes
     propres à la base sont découverts. En dessous de 8 objets, aucun profil
     n'est appris (les statistiques ne veulent rien dire) : vocabulaire statique.
   - **rattachement des sous-objets** : `ClientAdresse` → module `Client` **si**
     `Client` est lui-même un module. Préfixe uniquement, frontières de tokens
     (`Clientele` ne fusionne pas), `Misc` n'absorbe jamais. L'US garde le nom de
     **son** objet (`Consulter-ClientAdresse`) — CLAUDE.md §1 interdit deux US
     d'une FEAT partageant le même `{Name}`.
   - **bascule automatique** : si le nommage fragmente (modules/objets ≥ **0.50**)
     ou qu'un objet sur deux n'a pas de verbe lisible, le regroupement bascule sur
     la **cohésion du graphe de dépendances** (tables partagées, appels). La
     bascule n'est retenue que si elle regroupe *réellement* mieux ; sinon le
     nommage est conservé et le rapport le signale (`degraded`).
   - Override Tech Lead : `SDD_REVERSE_CLUSTER_COHESION=1` (toujours cohésion) ou
     `SDD_REVERSE_CLUSTER_NAMING=1` (toujours nommage, sans bascule).
   - Traçabilité : `inventory.json._clusteringReport` (stratégie, fragmentation
     mesurée, profil appris, sous-objets rattachés) + résumé en ligne de chat.
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
6. **Validation en deux temps** (les deux sont obligatoires) :
   - `validate_reverse_feat.py` sur chaque FEAT — structure (frontmatter, ordre des
     sections, IDs stables, Given/When/Then, evidence + confidence par item) ;
   - `check_reverse_feat_for_full.py --feat-path workspace/feats/{n}-*.md` — **le
     gate de consommation**. `confidence != high` ⇒ `allow-sdd-full=false` ⇒ exit 1,
     revue humaine requise. Forcer explicitement : `--allow-reverse-low`.
     > Audit 2026-08-25 (M1) : ce second appel manquait. Le commentaire
     > `REVERSE-GATE` était écrit dans la FEAT et **rien ne le lisait** — la revue
     > humaine sur du SQL dynamique ou chiffré était donc facultative de fait.
7. **Complétude (informational)** : `check_feat_completeness.py --project
   workspace/old/{DB} --unit {U-N}` — confronte la FEAT à ses objets SQL et
   signale un objet non mentionné, une règle `RAISERROR` perdue, une table écrite
   non documentée. Jamais bloquant.
7.bis **Traçabilité de l'escalier (informational)** : `check_ladder_traceability.py
   --project workspace/old/{DB} --unit {U-N}` — vérifie la chaîne descendante
   **FEAT item → US AC → ligne de snapshot**. Le chemin base de données a un
   barreau de moins que le chemin code (pas d'analyse 3a : le corps de l'objet
   SQL *est* l'analyse), et le vérificateur le reconnaît désormais au lieu de
   sortir en « artefacts manquants ». Il résout en plus chaque `evidence:` **sur
   disque** — un `unknown:1` ou un snapshot disparu est un gap, pas un vert.
   Jamais bloquant.
   > Audit 2026-08-25 (M3) : le vérificateur n'itérait que sur `units[].classes`
   > (forme du reverse de code) et rendait un vert vide sur une unité
   > `db-module`, qui porte `units[].procedures`.
8. Ligne chat finale `[REVERSE] DB {DB} → {p} objets SQL, {m} modules/FEAT, {u} US,
   {t} tables. (100%)`. La ligne de Phase 1 porte en plus la **stratégie de
   découpage** retenue, pour qu'elle soit visible sans ouvrir un JSON — p. ex.
   `[REVERSE] DB {DB} → 214 procédure(s) regroupée(s) en 31 module(s)/FEAT —
   regroupement par cohésion — nommage inexploitable (fragmentation 0.82). (Phase 1 OK)`.

## Sortie

```
workspace/old/{DB}/.sys/proc-snapshot/{schema}.{objet}.sql    (corps, lecture seule)
workspace/old/{DB}/.sys/schema-snapshot/{schema}.{table}.sql  (structure rendue lisible, JAMAIS exécutée)
workspace/old/{DB}/.sys/schema-snapshot/_catalog-objects.txt  (jobs, séquences, synonymes…)
workspace/old/{DB}/.sys/db-introspection.json                 (métadonnées + signaux, sans secret)
workspace/old/{DB}/.sys/db-schema.json                        (tables/colonnes/types/PK/FK/index/checks)
workspace/old/{DB}/.sys/inventory.json                        (units=modules, allocations)
workspace/old/{DB}/.sys/proc-extraction-cache.json            (cache par objet)
workspace/us/{n}-{m}-{Name}.md                                (1 par objet SQL)
workspace/feats/{n}-{Module}.md                               (1 par module)
```

Le `schema-snapshot` existe pour que chaque colonne porte une evidence `fichier:ligne`
honnête — un catalogue live n'a pas de lignes. C'est de la documentation, jamais
une migration : rien n'est envoyé au serveur.

## Anti-derive

- Lecture seule absolue ; le mot de passe n'est jamais loggé ni persisté.
- No-spawn d'agent par les agents (la commande séquence/ spawn, pas les agents).
- 1 objet SQL = 1 US, 1 module = 1 FEAT ; pas de fusion, pas d'invention (bias toward present).
- Idempotence : re-run réutilise `(n, Name)` via `_featAllocations`, et un objet
  déjà reversé **conserve son nom d'US** (pas d'orphelin sur disque).
- **Jamais d'écrasement d'une revue humaine** : la FEAT porte l'empreinte de son
  contenu généré (`generated-fingerprint`). Si le fichier sur disque en diverge,
  il est préservé et la commande le signale (exit 4) — `--force` pour écraser.

Voir `.sdd/docs/reverse-proc-engineering.audit.md` + `.sdd/rules/reverse-engineering.md`.
