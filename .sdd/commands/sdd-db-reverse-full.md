---
command: sdd-db-reverse-full
phase: db-reverse
description: "Reverse engineering de TOUS les objets SQL exécutables d'une base (lecture seule) — procédures stockées, fonctions, vues et triggers (P0.1 2026-07-24). Introspecte via la connection string de stack.md (## Active Database), regroupe les objets en modules, génère 1 User Story par objet SQL et 1 FEAT par module. Multi-dialecte — SQL Server (live-validé), PostgreSQL + Oracle + MySQL/MariaDB (scaffold-validés, runtime live pending — downgrade PostgreSQL audit 2026-08-29). Ne modifie JAMAIS la base."
loader: .sdd/loader.reverse.yml
---
# /sdd-db-reverse-full [--project DB] [--max-parallel N] [--sequential] [--no-architect] [--json]

## Rôle

Orchestrateur du reverse engineering **base de données → FEATs**. À partir de la
connexion déclarée dans `stack.md ## Active Database`, il lit **toutes** les
procédures stockées en **lecture seule**, les regroupe en modules métier, et
produit des FEATs SDD_Pro standard consommables par `/sdd-full`.

```
stack.md (## Active Database)  ← config + variables d'environnement (${VAR} via .env)
   └─[Phase 1 introspect READ-ONLY]─► proc-snapshot/*.sql + db-introspection.json
        │                              + schema-snapshot/*.sql + db-schema.json + inventory.json
        └─[Phase 0.A déterministe]─► FAITS : CRUD, graphe d'appels, plan de vagues
             └─[Phase 0.B reverse-db-architect]─► HYPOTHÈSES : glossaire, domaines, risques
                  └─► db-context.json (SSoT versionné) + db-context/packs/{objet}.md
                       └─[vagues : feuilles d'abord, spécialistes en parallèle borné]
                       │    proc-analyst · function-analyst · view-analyst · trigger-analyst
                       │    └─► us/{n}-{m}-{Name}.md   (1 objet SQL = 1 US)
                       │         └─ résumé réinjecté dans db-context.findings ─┐
                       │            (barrière de vague, puis vague suivante) ◄─┘
                       └─[rung 2 : synthèse module]─► feats/{n}-{Module}.md  (1 module = 1 FEAT)
                            └─ validate_reverse_feat + check_reverse_feat_for_full
                                 └─► REVERSE-GATE ─► /sdd-full
```

## Modèle (confirmé)

- **1 objet SQL = 1 User Story** · **1 module = 1 FEAT** (objets d'un même objet métier).
- **Comprendre avant d'écrire** : aucune User Story n'est produite avant que la
  Phase 0 ait construit le Database Context. Un analyste ne redécouvre jamais la
  base — il reçoit le slice qui le concerne.
- **Remontée stricte** : la FEAT est composée depuis les US + l'inventaire, jamais en
  relisant le corps SQL. L'assembleur lit réellement les US (titre métier, ACs,
  mode d'extraction) et y écrit en retour `Covers:` + le `Parent FEAT hash`.
- **Faits ≠ hypothèses** : les faits viennent des scripts déterministes et
  peuvent devenir des Acceptance Criteria ; les hypothèses viennent de
  l'architecte et ne le peuvent jamais. La séparation est structurelle.

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
3. `DatabaseType` supporté : **SQL Server** (seul moteur **live-validé** —
   preuves de runs réels), **PostgreSQL**, **Oracle** et **MySQL/MariaDB**
   (scaffold-validés — requêtes read-only et flux hors ligne testés, runtime
   live à valider sur une base de test avant prod ; PostgreSQL était annoncé
   « live-validé » à tort, downgrade audit 2026-08-29 — cf. CLAUDE.md §3).
   DB2 et SQLite sont reconnus mais refusés avec un message explicite.

## Périmètre et coût

> **Décision Tech Lead 2026-08-27 — NE JAMAIS DEMANDER (non négociable).**
> Le périmètre par défaut est **tous les objets de la base**, dispatchés au
> parallélisme `MaxParallel` du Project Config. L'orchestrateur **ne pose aucune
> question de confirmation** sur le périmètre, le coût ou le parallélisme : il
> lance le run complet et se contente de **signaler** ce qu'il observe (nombre
> d'objets par tier, bruit système détecté, plafond de coût configuré).
> Ce qui borne le run, ce sont les **flags explicitement passés par le Tech Lead**
> — jamais une question posée en cours de route.
>
> Rationale : le plafond `[COST_CAP_EXCEEDED]` est une protection *suffisante*, et
> le **cache par objet** rend toute coupure reprenable quasi gratuitement. Demander
> une confirmation n'ajoute donc aucune sécurité — seulement une interruption.
> Corollaire : le bruit système (procédures de diagrammes SSMS `sp_*diagram*`,
> `fn_diagramobjects`, débris de dev) est **analysé comme le reste** puis **signalé
> dans le rapport final** comme supprimable — il n'est jamais l'objet d'une question.

Pour borner explicitement un run sur une base volumineuse :

| Flag | Effet |
|---|---|
| `--schema dbo,sales` | restreint aux schémas cités |
| `--include 'usp_Invoice*'` | ne garde que les objets matchant (glob, répétable) |
| `--exclude 'usp_Debug*'` | écarte les objets matchant |
| `--limit N` | plafonne le nombre d'objets — **nomme ce qu'il a écarté** (pas de troncature silencieuse) |
| `--no-schema` | saute la lecture de structure (tables/colonnes/jobs) |
| `--max-parallel N` | borne du parallélisme **à l'intérieur d'une vague** (1-12, défaut = `MaxParallel` du Project Config) |
| `--sequential` **@llm-only-flag** | une vague par objet — débogage, jamais en production (interprété par l'orchestrateur) |
| `--no-architect` **@llm-only-flag** | s'arrête après la Phase 0.A (faits seuls, aucun coût LLM de Phase 0) — interprété par l'orchestrateur, qui ne spawne alors pas l'architecte |

La reprise repose sur le **cache par objet** : un objet dont le corps est inchangé
et dont l'US existe n'est pas ré-extrait (`--no-cache` pour forcer). C'est ce qui
rend un second run quasi gratuit après une interruption.

## Actions

1. **Phase 1 (déterministe, 0 token)** :
   `python .sdd/python/sdd_reverse_scripts/reverse_proc_introspect.py --full [--project DB]`
   → snapshot + `db-introspection.json` + `inventory.json` (units = modules,
   `(n, Name)` pré-alloués). Erreur DB → STOP avec la classe `[REVERSE_DB_*]`.
   Aussitôt le snapshot écrit, **scanner les secrets codés en dur** (WARN
   informational, jamais bloquant — classe `[REVERSE_SECRETS_DETECTED]`,
   `rules/reverse-engineering.md §6`) :
   ```bash
   python .sdd/python/sdd_reverse_scripts/scan_snapshot_secrets.py --project {DB} [--json]
   ```
   Un corps de procédure legacy porte parfois un mot de passe, une connection
   string ou une clé API en littéral — le snapshot vient de le copier sur
   disque. Le scan pointe la ligne sans jamais logger la valeur ; actions :
   révoquer le credential exposé, suivre les recommandations `.gitignore`
   imprimées, re-provisionner via vault. `--exit-on-found` (CI) rend le exit 1
   sur détection ; en interactif, on continue.
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
1.ter **Phase 0 — Database Context (compréhension avant écriture)** :
   ```bash
   python .sdd/python/sdd_reverse_scripts/db_context_build.py --project workspace/old/{DB}
   ```
   - **0.A déterministe, 0 token** : faits (tables/colonnes/PK/FK/index/CHECK,
     corps d'objets), **matrice CRUD** par objet (C/U/D distingués via
     `writeKinds`, plus seulement « écrit »), **graphe d'appels résolu**, **plan
     de vagues**, `contextVersion` (sha256 des faits) → `db-context.json` +
     l'arbre `db-context/` (aperçu, 1 fiche par table, 1 fiche par objet,
     1 **pack** par objet).
   - **0.B interprétation** : spawn `Agent(reverse-db-architect)` — sauf
     `--no-architect`, et **sauté si le `contextVersion` est inchangé** (une base
     stable ne paie l'architecte qu'une fois). Il lit le *digest*, jamais le
     catalogue brut, et écrit `db-context.hypotheses.json`, fusionné par
     `--merge-hypotheses` dans la seule branche `hypotheses`.
   - Détail complet et usage isolé : `/sdd-db-context`.

2. **Routage par complexité et par tier (0 token, token-efficient)** :
   `python .sdd/python/sdd_reverse_scripts/build_proc_us.py --project DB --all --json`
   - génère **déterministiquement** (0 token LLM) toutes les US des objets
     **triviaux** (CRUD/SELECT court, sans branche, sans appel, sans SQL
     dynamique ni erreur levée) ;
   - retourne `needs_llm` = les objets à analyser, **chacun avec son tier**
     (`db_tier_router`, rubrique déterministe) : `fast` pour une logique courte
     et lisible, `balanced` pour une vraie règle métier, `deep` pour ce qui exige
     de raisonner sur ce qui n'est pas écrit (SQL dynamique, récursion, appelé
     non résolu, orchestration ≥ 2 appels, fan-in élevé).
   - Le tier est un **tier**, jamais un nom de modèle : la résolution appartient
     au provider actif (`.sdd/providers/*.yaml`), donc le même arbitrage vaut sur
     Anthropic, Google, OpenAI ou Moonshot.

   > **Correctif 2026-08-26.** La rubrique ignorait les appels : un orchestrateur
   > de 38 lignes sans branche déléguant sa règle à six procédures était classé
   > « simple », décrit par un template, et sortait en `high` — un faux vert qui
   > traversait la REVERSE-GATE. Déléguer n'est pas être simple.

3. **Cache** : sauter les objets dont le snapshot est inchangé ET dont l'US
   existe (`reverse_cache`/`update_extraction_cache`, fail-safe : doute = ré-extraire).

4. **rung 1 — dispatch PAR VAGUES (le cœur de la refonte)** :
   `db-context.json.executionPlan.waves` ordonne les objets pour que **tout
   appelé résolu soit analysé strictement avant son appelant**.

   Pour chaque vague, dans l'ordre :
   a. dispatcher **en parallèle borné** (`--max-parallel`, défaut `MaxParallel`
      = 3) tous les objets de la vague présents dans `needs_llm`, chacun vers
      **son spécialiste** selon `routineType` :

      | Famille | Agent | Angle |
      |---|---|---|
      | procédure · package Oracle | `reverse-sql-analyst` | une opération — contrat, effets, préconditions (1 package = 1 US) |
      | fonction | `reverse-sql-function-analyst` | un calcul réutilisable sans effet de bord |
      | vue | `reverse-sql-view-analyst` | une projection — et ses filtres implicites |
      | trigger | `reverse-sql-trigger-analyst` | un invariant déclenché par un événement |

      Le champ `agent` de chaque entrée `needs_llm` porte déjà ce verdict —
      l'utiliser tel quel plutôt que re-mapper la famille.

      Chaque agent reçoit `{U-N} --object {fq}` et lit **son pack**, pas la base.
      **Passer le tier calculé à l'étape 2** comme override `model` du spawn
      (`Agent(reverse-sql-*, model=<résolution du tier via le provider actif>)`)
      — sans ce passage, `db_tier_router` calcule un arbitrage par objet que
      rien ne consomme, et chaque spécialiste tourne au tier statique de sa
      définition d'agent quel que soit l'objet (audit 2026-08-29 m7).
   b. **barrière de vague** — un seul appel déterministe (0 token), après que
      tous les agents de la vague `K` ont rendu leur US :
      ```bash
      python .sdd/python/sdd_reverse_scripts/db_context_build.py \
        --project workspace/old/{DB} --close-wave {K}
      ```
      Il inscrit dans `db-context.json.findings` le résumé de chaque objet de
      la vague dont l'US existe, puis régénère **les packs de la vague `K+1`**
      — qui citeront ces résumés au lieu de signaux bruts. Les agents
      n'écrivent que leur US ; la barrière est la seule écriture sur le
      contexte, en une passe atomique, donc le parallélisme intra-vague reste
      sûr sans nouveau verrou.

      Le résumé est **extrait** de l'US, jamais re-généré : un second appel LLM
      pour résumer un texte que le premier vient de produire paierait deux fois
      la même information et ouvrirait un écart entre l'US livrée et le résumé
      que ses appelants vont citer.

      Idempotent (relancer une barrière déjà fermée ne change rien) et honnête :
      un objet sans US est rapporté `skipped` — cas normal, il n'était pas routé
      LLM ou le cache l'a sauté — et une US sans titre ni AC exploitable produit
      un résumé **vide signalé** (`empty`) plutôt qu'une phrase fabriquée.
      Reprise partielle d'une vague : `--record-finding {fq} --from-us {path}`.

      > Audit 2026-08-28 (P0-4) : cette étape n'était pas exécutable. La
      > fonction `record_finding` existait, documentée « called by the
      > orchestrator at a wave barrier » et testée, mais sans appelant ni point
      > d'entrée CLI — la commande demandait une écriture atomique sans fournir
      > l'outil. Le plan de vagues payait donc le prix d'un tri sans en tirer le
      > bénéfice : un appelant lisait `dbo.Stock=U` là où il pouvait lire
      > « lève RAISERROR et n'écrit rien ».

   `--sequential` force une vague par objet (débogage). Une **composante
   récursive** (cycle mutuel ou auto-appel) est confiée d'un bloc à un seul
   agent, avec tous les corps du cycle dans son pack, et sort plafonnée à
   `medium`.

5. **rung 2 — synthèse de module** :
   Le critère décisif est le **nombre d'objets à harmoniser**, pas le tier le plus
   haut du module. Un module d'**un seul objet** n'a par construction aucune règle
   transverse à remonter ni aucun vocabulaire à réconcilier entre US : le rung LLM
   n'y apporte rien, quel que soit son tier.
   - **déterministe, 0 token** (`build_proc_feats.py --project DB --unit {U-N}`) :
     module **mono-objet**, ou module **purement CRUD** (aucun objet au-dessus de
     `fast` et aucun objet routé LLM).
   - **LLM** (spawn `Agent(reverse-sql-feat-composer)`) : module **multi-objets**
     ayant au moins un objet routé LLM — c'est là que se trouvent les règles
     transverses et le vocabulaire à harmoniser sur le glossaire de l'architecte.
     Parallèle borné, FEATs disjointes, **même gate**.
   - **Le verdict par module est émis déterministiquement à l'étape 2** :
     `build_proc_us.py --json` porte `modules[].featComposer:
     "llm"|"deterministic"` (2026-08-30). **Consommer ce champ tel quel** —
     l'orchestrateur ne ré-interprète jamais la règle (3 formulations
     divergentes de ce routage recensées à l'audit 2026-08-29 ; le script est
     désormais l'unique arbitre).
   - `SDD_REVERSE_FEAT_LLM=1` force le LLM partout ; `=0` force le déterministe
     (les deux overrides priment sur `featComposer`).

   > **Correctif 2026-08-27 (run 118 objets, PortailClient_Dev).** La règle
   > précédente — « au moins un objet `deep` » — **inversait** le routage sur une
   > base réelle : elle envoyait au composer LLM 7 modules mono-objet de
   > procédures système SSMS (`sp_*diagram*`, classées `deep` par un faux positif
   > de parsing d'`EXECUTE AS`), et confiait à l'assembleur déterministe les deux
   > plus gros modules métier de la base — `Contact` (15 objets, dont un
   > contournement d'authentification par littéral codé en dur) et `ModeleBrief`
   > (16 objets). Le tier d'un objet mesure la difficulté de **l'analyser** (rung 1) ;
   > il ne mesure pas l'intérêt de **synthétiser** son module (rung 2).

6. **Validation en deux temps** (les deux sont obligatoires) :
   - `validate_reverse_feat.py` sur chaque FEAT — structure (frontmatter, ordre des
     sections, IDs stables, Given/When/Then, evidence + confidence par item) ;
   - `check_reverse_feat_for_full.py --feat-path workspace/feats/{n}-*.md` — **le
     gate de consommation**. `confidence != high` ⇒ `allow-sdd-full=false` ⇒ exit 1,
     revue humaine requise. Forcer explicitement : `--allow-reverse-low`.
     > Audit 2026-08-25 (M1) : ce second appel manquait. Le commentaire
     > `REVERSE-GATE` était écrit dans la FEAT et **rien ne le lisait** — la revue
     > humaine sur du SQL dynamique ou chiffré était donc facultative de fait.

   **Après revue humaine d'une FEAT `medium`/`low`**, la voie sanctionnée de
   promotion est le script dédié — jamais un Edit à la main du frontmatter :
   ```bash
   python .sdd/python/sdd_reverse_scripts/promote_confidence.py \
     --feat-path workspace/feats/{n}-{Module}.md \
     --reason "revue Tech Lead {YYYY-MM-DD}" [--dry-run] [--json]
   ```
   Il passe `confidence: high`, déverrouille la REVERSE-GATE
   (`allow-sdd-full=true`, avec date + raison tracées dans le commentaire) et
   ré-estampille le `generated-fingerprint` (M5) pour que les runs suivants de
   `build_proc_feats.py` reconnaissent la version promue comme autoritative.
   `--allow-reverse-low` reste le bypass **one-shot** (rien n'est promu, la
   FEAT reste bloquée au run suivant) ; `promote_confidence.py` est la décision
   **durable**. Exit 1 = déjà `high`, 2 = pas une FEAT sdd-reverse.
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
7.ter **Vue système et corrélation (informational, déterministe, 0 token)** —
   deux livrables qui existaient déjà et que rien n'appelait :
   - **ERD + vue de contexte** :
     `python .sdd/python/sdd_reverse_scripts/reverse_synth.py --project workspace/old/{DB}`
     rend l'ERD Mermaid et la vue système depuis `db-schema.json` +
     `inventory.json` (jamais depuis les FEATs — lecture seule, sous `.sys/synthesis/`).
   - **Qui consomme quoi** : si un reverse **applicatif** a déjà tourné et qu'un
     `data-access.json` existe,
     `python .sdd/python/sdd_reverse_scripts/correlate_db_app.py
     --introspection workspace/old/{DB}/.sys/db-introspection.json
     --data-access workspace/old/{App}/.sys/data-access.json`
     produit la carte de consommation objet DB ↔ application. C'est ce qui
     répond à « si je change cette procédure, quelle application casse ? ».
   Les deux sont **informational** : ni l'un ni l'autre ne bloque le pipeline, et
   leur absence (pas de reverse applicatif, pas de schéma) est un cas normal.
7.quater **Rapport de synthèse du run (informational, déterministe, 0 token)** :
   ```bash
   python .sdd/python/sdd_reverse_scripts/reverse_report.py --project {DB} \
     --output workspace/old/{DB}/.sys/reverse-report.md
   ```
   Table par module — objets, distribution des tiers, US (analysées ↑ vs
   gabarits ⬜), ACs, confidence, statut REVERSE-GATE — plus, pour chaque FEAT
   bloquée, la commande `promote_confidence.py` prête à copier. C'est la
   **surface de décision une page** du Tech Lead avant de lancer `/sdd-full`
   sur les FEATs à `allow-sdd-full=true`. Jamais bloquant.

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
workspace/old/{DB}/.sys/db-context.json                       (SSoT versionné : faits + plan de vagues + hypothèses + findings)
workspace/old/{DB}/.sys/db-context.digest.json                (digest léger pour l'architecte — seul porteur du contextVersion qu'il lit)
workspace/old/{DB}/.sys/db-context.hypotheses.json            (écrit par l'architecte, fusionné par script)
workspace/old/{DB}/.sys/db-context/_overview.md               (orientation base entière)
workspace/old/{DB}/.sys/db-context/glossary.json              (extrait léger glossaire + sous-domaines + contextVersion, lu par le composer rung 2)
workspace/old/{DB}/.sys/db-context/tables/{table}.md          (1 fiche par table)
workspace/old/{DB}/.sys/db-context/{procedures,functions,views,triggers,packages}/{objet}.md
workspace/old/{DB}/.sys/db-context/packs/{objet}.md           (le slice remis à l'agent qui analyse cet objet)
workspace/old/{DB}/.sys/reverse-report.md                     (synthèse une page du run — 7.quater)
workspace/us/{n}-{m}-{Name}.md                                (1 par objet SQL)
workspace/feats/{n}-{Module}.md                               (1 par module)
```

Le `schema-snapshot` existe pour que chaque colonne porte une evidence `fichier:ligne`
honnête — un catalogue live n'a pas de lignes. C'est de la documentation, jamais
une migration : rien n'est envoyé au serveur.

## Anti-derive

- Lecture seule absolue ; le mot de passe n'est jamais loggé ni persisté.
- **Structure uniquement** dans le contexte partagé : aucune donnée métier,
  aucun identifiant de connexion.
- **Aucun agent ne lit toute la base** : chacun reçoit son pack, borné, qui
  déclare ce qu'il a dû tronquer — un pack tronqué en silence produit une User
  Story confiante et fausse.
- **L'architecte n'écrit pas de faits** : il écrit un fichier séparé, fusionné
  par script dans la seule branche `hypotheses`. Garanti par construction.
- No-spawn d'agent par les agents (la commande séquence/ spawn, pas les agents).
- 1 objet SQL = 1 US, 1 module = 1 FEAT ; pas de fusion, pas d'invention (bias toward present).
- Idempotence : re-run réutilise `(n, Name)` via `_featAllocations`, et un objet
  déjà reversé **conserve son nom d'US** (pas d'orphelin sur disque).
- **Jamais d'écrasement d'une revue humaine** : la FEAT porte l'empreinte de son
  contenu généré (`generated-fingerprint`). Si le fichier sur disque en diverge,
  il est préservé et la commande le signale (exit 4) — `--force` pour écraser.

Voir `.sdd/docs/reverse-proc-engineering.audit.md` + `.sdd/rules/reverse-engineering.md`.
