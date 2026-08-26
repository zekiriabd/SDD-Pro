---
title: Reverse Engineering « Procédures Stockées » — Audit d'impact & design
status: MVP implémenté (2026-06-29) — déterministe + agent + 2 commandes, ~30 tests verts, smoke 13/13
version: 0.2.0
created: 2026-06-29
author: Audit IA + expertise SQL/T-SQL
scope: nouveau sous-flux reverse (DB live → FEAT/US) cohabitant avec le module reverse existant, sans casser l'isolation D4
relates_to:
  - .sdd/docs/reverse-engineering-workflow.md   # design doc maître reverse (source-files)
  - .sdd/rules/reverse-engineering.md            # anti-derive + taxonomie [REVERSE_*]
  - .sdd/docs/arch/phase-b-db-scaffolding.md     # précédent introspection DB live READ-ONLY
  - .sdd/rules/library-and-stack.md §C           # règle DB READ-ONLY + [DB_STRUCTURE_CHANGE_FORBIDDEN]
---

# Audit — Reverse Engineering depuis les procédures stockées

> **Demande** : ajouter un second moteur de reverse engineering qui, à partir
> d'une **connection string** (clés DB déjà présentes dans `stack.md`), lit les
> **procédures stockées** d'une base SQL Server (T-SQL) en **lecture seule** et
> en dérive des **User Stories** et des **FEATs** — par procédure
> (`/sdd-reverse-proc {ProcName}`) ou pour toute la base (`--all` / `full`).
> Conceptuellement multi-SGBD, MVP = SQL Server.

---

## 0. Verdict de l'audit (TL;DR)

**Faisable, à impact maîtrisé — à condition de NE PAS réinventer le pipeline.**

Trois décisions structurent tout le reste :

1. **Découpler l'introspection live de l'analyse.** La seule surface réellement
   nouvelle et risquée est *« se connecter à une base vivante »*. Isolez-la dans
   **un seul adaptateur d'introspection** qui produit un **snapshot T-SQL sur
   disque**. Tout l'aval (analyse → US → FEAT) **réutilise l'escalier reverse
   existant** (3a→3b→3c). Blast radius minimal, idempotence et evidence `file:line`
   préservées.

2. **Le répertoire `proc/` est un répertoire de SNAPSHOT, pas un nouveau
   workspace.** Il contient le dump `.sql` (1 fichier par procédure) + les
   métadonnées catalogue. Ce n'est pas un dossier « à remplir à la main » : c'est
   la *source* de cette saveur de reverse, l'équivalent de `workspace/old/{P}/`
   pour le code.

3. **La règle « jamais modifier la base » existe déjà** et porte un nom :
   `[DB_STRUCTURE_CHANGE_FORBIDDEN]` (`error-classification.md §1.3`), doublée du
   précédent **introspection live READ-ONLY** d'`arch` Phase B
   (`phase-b-db-scaffolding.md`). On l'étend, on ne l'invente pas.

**Pourquoi le snapshot sur disque est non négociable (argument SQL + framework) :**
le contrat anti-hallucination du reverse (`reverse-engineering.md §3`) exige que
**chaque** item de FEAT (SFD/FD/BR/AC) porte `<!-- evidence: path:Lstart-Lend -->`.
Une ligne de catalogue SQL vivante **n'a pas de `file:line`**. Dumper
`OBJECT_DEFINITION` dans `proc/dbo.usp_X.sql` donne une evidence stable, citable,
re-vérifiable et diff-able entre deux runs — sans le snapshot, le module violerait
son propre invariant `reverse-evidence-required`.

---

## 1. Ce qui existe déjà (à réutiliser, pas à recréer)

L'audit du code a établi que **~80 % de la plomberie est déjà là**. Le module
reverse actuel est fortement gouverné et isolé (D4).

| Brique existante | Fichier | Réutilisable tel quel ? |
|---|---|---|
| Workspace reverse `workspace/old/{P}/.sys/` | `reverse-engineering-workflow.md §2` | ✅ une base = un « projet » legacy |
| Allocation d'unités `U-N` + idempotence + lock + `_featAllocations` | `inventory_builder.py`, `preallocate_feats.py` | ✅ unité = grappe de procs |
| **Escalier 3a→3b→3c** (analyse → US → FEAT) | `reverse-tech-analyst` / `reverse-us-writer` / `reverse-feat-composer` | ✅ 3b/3c inchangés ; **3a à spécialiser T-SQL** |
| Extraction T-SQL **statique** (CREATE PROC, params, EXEC, tables) | `data_access_extractor.py` (`parse_stored_procedure_defs`) | ⚠️ base utile mais **trop superficielle** (noms+params, pas le corps) |
| FEAT transversale « Base de données » déterministe | `crosscutting_feats.py::build_database_feat` | ✅ déjà liste procs comme FD — point d'extension naturel |
| Cap de confiance `tsql = high` | `language_signatures.yml` | ✅ déjà présent |
| Validation FEAT reverse 0-token | `validate_reverse_feat.py` | ✅ inchangé |
| Pont reverse → `/sdd-full` (REVERSE-GATE, hash, Covers) | `reverse-engineering.md §10` | ✅ inchangé |
| Taxonomie `[REVERSE_*]` + label chat `[REVERSE]` + smoke | `reverse-engineering.md §6/§7`, `reverse_smoke.py` | ✅ à étendre (réciprocité) |
| **Précédent introspection DB live READ-ONLY** | `arch.md` STEP 8-11 / `phase-b-db-scaffolding.md` | ✅✅ **patron à copier** (voir §4) |
| Convention clés DB en clair dans `stack.md` (`DB_HOST/PORT/NAME/USER/PASSWORD`) | `loader.yml:203-207`, `arch.md:27` | ✅ source de la connexion |

> **Constat clé** : le reverse actuel sait déjà *nommer* les procédures (depuis
> les fichiers `.sql` du code source), mais il **n'analyse jamais le corps T-SQL**
> pour en extraire de la logique métier. C'est exactement le « delta » que ce
> nouveau moteur apporte — y compris pour les procs déjà présentes en source.

---

## 2. La décision centrale : Live vs Snapshot

### Option A — Analyse directe sur la base vivante (ce que la demande décrit littéralement)
`/sdd-reverse-proc X` → connexion → lecture catalogue → l'agent analyse en RAM.

**Problèmes :** pas de `file:line` (viole `reverse-evidence-required`) ; non
idempotent (la base bouge) ; non re-jouable hors connexion ; surface live couplée
à l'analyse LLM (coûteux, fragile) ; dépendance driver dans le chemin chaud.

### Option B — Snapshot-first (RECOMMANDÉ)
`/sdd-reverse-proc X --introspect` → connexion **read-only** → dump `proc/*.sql`
+ `db-introspection.json` → **déconnexion** → l'escalier analyse le snapshot
**hors-ligne**.

**Bénéfices :** evidence `file:line` réelle (ligne du corps de proc) ; idempotent
(re-analyse sans re-connecter) ; surface live réduite à **un script**, auditable,
testable hors DB via fixtures `.sql` ; réutilise tout l'aval existant ; respecte
la philosophie zéro-dépendance (le driver ne charge que pendant l'introspection,
en extra opt-in).

> **Recommandation : Option B.** C'est aussi ce que fait `arch` Phase B
> (introspection RAM → écrit `schema.json` sur disque → le reste du pipeline lit
> le fichier, jamais la base).

---

## 3. Le répertoire `proc/` — quoi mettre dedans

Une base introspectée est traitée comme **un projet legacy** sous la convention
existante. Pas de nouveau workspace racine — on réutilise `workspace/old/`.

```
workspace/old/{DbProject}/                 # ex. workspace/old/OrdersDb/
├── proc/                                   # ← LE répertoire demandé : snapshot T-SQL READ-ONLY
│   ├── dbo.usp_Order_Create.sql            # 1 fichier = OBJECT_DEFINITION d'1 proc (lossless)
│   ├── dbo.usp_Order_Cancel.sql
│   ├── sales.usp_Invoice_Post.sql          # nom = {schema}.{proc}.sql (évite collisions cross-schema)
│   └── _manifest.json                      # liste procs + checksum + date dump (stabilité U-N)
├── functions/                              # (optionnel) UDF scalaires/TVF — même traitement
├── views/                                  # (optionnel) vues — logique de lecture
└── .sys/                                   # artefacts reverse — RÉUTILISÉS tels quels
    ├── db-introspection.json               # NOUVEAU : métadonnées catalogue (voir §3.1)
    ├── inventory.json                      # unités U-N = grappes de procs
    ├── db-schema.json                      # tables touchées par les procs
    └── modules/{Grappe}/extraction.md
```

**Règles du dossier `proc/` :**
- **Lecture seule en aval** : écrit *uniquement* par l'adaptateur d'introspection.
- **Un fichier = une proc**, nommé `{schema}.{proc}.sql`, contenu = définition
  brute non tronquée (`sys.sql_modules.definition`, **jamais** `sp_helptext` qui
  chunke à 4000 car. et casse l'indentation).
- **Snapshot immuable** entre run d'introspection et génération de FEAT (même
  contrat que `workspace/old/{P}/` figé, design doc §3.2).
- `_manifest.json` porte le `checksum` par proc → réutilise le cache reverse
  (`reverse_cache.py`) : ne re-analyser que les procs modifiées depuis le dernier dump.

### 3.1 `db-introspection.json` (nouveau, déterministe)

Produit par le seul script live. Tout le reste est dérivé hors-ligne.

```json
{
  "schemaVersion": 1,
  "databaseType": "SqlServer",
  "server": "SQLPRD01",            "database": "OrdersDb",   // secrets jamais inclus
  "introspectDate": "2026-06-29T10:00:00Z",
  "procedures": [
    {
      "id": "SP-1",
      "schema": "dbo", "name": "usp_Order_Create",
      "snapshotFile": "proc/dbo.usp_Order_Create.sql",
      "lineCount": 142,
      "params": [
        {"name": "@CustomerId", "type": "int", "output": false},
        {"name": "@OrderId", "type": "int", "output": true}
      ],
      "encrypted": false,
      "tablesRead":   ["Customers", "Products"],
      "tablesWritten":["Orders", "OrderLines"],
      "callsProcs":   ["dbo.usp_Inventory_Reserve"],
      "dynamicSql":   false,
      "hasTransaction": true,
      "raises":       ["RAISERROR", "THROW"],
      "modifiedDate": "2025-11-03T08:12:00Z"
    }
  ],
  "callGraph": [ {"from": "dbo.usp_Order_Create", "to": "dbo.usp_Inventory_Reserve"} ],
  "secretsDetected": false
}
```

---

## 4. Pipeline cible (réutilisation maximale de l'escalier)

```
Phase 0  [humain]  : renseigner ## Active Database dans stack.md (déjà la convention)
Phase 1L [LIVE]    : /sdd-reverse-proc-introspect   ← SEULE étape connectée, READ-ONLY
                     → workspace/old/{Db}/proc/*.sql + .sys/db-introspection.json
                     → déconnexion immédiate
Phase 1  [scan]    : /sdd-reverse-inventory (réutilisé, source = proc/ au lieu de code)
                     → inventory.json : units U-N = GRAPPES de procs (voir §5)
Phase 2  [opt]     : /sdd-reverse-audit (anti-patterns T-SQL : NOLOCK, dynamic SQL, xp_cmdshell…)
Phase 3a [analyse] : reverse-proc-analyst (NOUVEAU, ou mode T-SQL de reverse-tech-analyst)
                     → plans/{n}-{Name}.analysis.md (corps T-SQL → comportement)
Phase 3b [US]      : reverse-us-writer   (INCHANGÉ)
Phase 3c [FEAT]    : reverse-feat-composer (INCHANGÉ)
Phase 3-bis        : crosscutting_feats « Base de données » (étendu : tables+procs introspectées)
Phase 5/6          : revue Tech Lead → /sdd-full {n}  (INCHANGÉ, via REVERSE-GATE)
```

**Patron d'introspection (copié d'`arch` Phase B) — choix du driver :**

| Stratégie | Dépendance | Verdict |
|---|---|---|
| **`pyodbc` en extra opt-in** `[reverse-db]` | ODBC Driver 18 (OS) + pip extra | ✅ **recommandé** — cross-platform, calque le précédent extra `reverse=[PyYAML]` du `pyproject.toml` |
| `Invoke-Sqlcmd` (module PowerShell SqlServer) | Windows + module | ✅ fallback pragmatique (l'utilisateur est sous Windows + SQL Server) |
| **Runtime bridge** généré dans le langage du stack (comme arch) | aucune (réutilise le SDK du stack) | ✅ si un stack backend est déjà choisi ; ❌ inutilisable en reverse « base seule » |
| `sqlcmd` brut en subprocess | mssql-tools | ⚠️ formatage multiligne `nvarchar(max)` pénible pour dumper les corps |

> **Reco** : `pyodbc` extra opt-in par défaut (cohérent avec la philosophie
> zéro-dep : un user forward n'installe rien ; un user db-reverse fait
> `pip install -e .sdd/python[reverse-db]`), fallback `Invoke-Sqlcmd`.

---

## 5. Granularité & clustering (l'erreur à éviter en priorité)

**Anti-pattern fatal : 1 proc = 1 FEAT.** Une base de 400 procs produirait 400
FEATs ingérables. Une FEAT = *intention utilisateur cohérente* (design doc §1).

**Heuristique de grappe (déterministe, dans `inventory_builder` étendu) — unité U-N = grappe :**
1. **Préfixe de nommage** : `usp_Order_Create`, `usp_Order_Cancel`,
   `usp_Order_Get` → famille `Order` (convention `verb_object` ou `object_verb`).
2. **Empreinte de tables** : procs écrivant le même cœur de tables → même domaine.
3. **Graphe d'appels** : `A EXEC B` → A et B dans la même grappe.
4. Procs orphelines (aucun signal) → grappe « par schéma » en dernier recours.

Mapping : **1 grappe → 1 unité U-N → 1 FEAT** ; **1 proc → 1+ User Story**
(capability). Identique au mapping page→FEAT / capability→US existant.

> **État réel au 2026-08-25 — ce paragraphe décrit l'intention, pas
> l'implémentation.** Ce qui a été livré est plus large, et vit dans
> `sdd_reverse/proc_module_clusterer.py` (pas `inventory_builder`), avec
> `sdd_reverse/sql_dependency_graph.py::cohesion_modules` pour la cohésion.
> Trois écarts à connaître avant de raisonner sur ce §5 :
>
> 1. **Le mapping final est `1 objet SQL = 1 US`** (pas « 1+ »), et un objet SQL
>    n'est pas seulement une procédure : fonctions, vues, triggers et packages
>    Oracle passent par le même escalier.
> 2. **Le point 1 (« préfixe de nommage ») n'est plus une liste fixe.** La
>    structure de nommage est **mesurée** sur le corpus réel de la base
>    (`learn_name_profile` : fréquence documentaire × concentration
>    positionnelle) : les marqueurs de type/sous-système et les verbes propres à
>    la base sont découverts, dans n'importe quelle langue, au lieu d'être
>    déclarés. En dessous de 8 objets, aucun profil n'est appris. S'y ajoute le
>    **rattachement des sous-objets** (`ClientAdresse` → `Client`), qui n'était
>    pas prévu ici et qui est ce qui empêche l'aggregate d'être éclaté en deux
>    FEATs.
> 3. **Les points 2-3 ne sont plus un repli, mais une stratégie concurrente,
>    choisie automatiquement.** Si le nommage fragmente (modules/objets ≥ 0.50)
>    ou qu'un objet sur deux n'a pas de verbe lisible, le regroupement bascule sur
>    la cohésion du graphe — et n'est retenu que s'il regroupe réellement mieux.
>    La stratégie effectivement appliquée est affichée en ligne de chat et tracée
>    dans `inventory.json._clusteringReport`.
>
> Overrides : `SDD_REVERSE_CLUSTER_COHESION=1` / `SDD_REVERSE_CLUSTER_NAMING=1`.
> Couverture : `tests/test_reverse_db_clustering.py`. Détail et statut :
> `reverse-db-audit-2026-07.md` (finding DB4, fermé).

`/sdd-reverse-proc {ProcName}` (mode 1 proc) reste possible : il résout la grappe
contenant `{ProcName}` et génère/met à jour la FEAT correspondante (idempotent).

---

## 6. Profondeur d'analyse T-SQL (la valeur ajoutée — section expert SQL)

L'extracteur actuel (`data_access_extractor.py`) ne lit **que** noms + params. Le
corps T-SQL contient la logique métier. Signaux à extraire (déterministe en 1L,
puis élevés en BR/AC par l'analyste 3a — **bias toward present**, evidence = ligne
du `.sql` dumpé) :

| Signal T-SQL | Dérive vers | Exemple |
|---|---|---|
| Params + défauts + `OUTPUT` / `RETURN` / result set | **Contrat / FD** | « l'OP retourne `@OrderId` (OUTPUT) » |
| `FROM`/`JOIN` (lecture) vs `INSERT/UPDATE/DELETE/MERGE` (écriture) | **Effets de données** | « écrit Orders + OrderLines (atomique) » |
| `IF` / `CASE` / `WHILE` (flux) | **Business Rules** | « si stock < qté → branche annulation » |
| `IF EXISTS(...)` / `RAISERROR` / `THROW` | **Préconditions → AC négatifs** | « rejet si client inexistant » |
| `BEGIN TRAN`/`COMMIT`/`ROLLBACK` + `TRY/CATCH` + `XACT_ABORT` | **Règle d'atomicité (AC)** | « tout-ou-rien sur échec ligne » |
| `EXEC dbo.autre_proc` | **Dépendance (graphe, traçabilité)** | rattache à la grappe |
| **`sp_executesql` / `EXEC(@sql)` (SQL dynamique)** | **Downgrade confiance** | intent non statiquement visible → `medium` |
| Curseurs / tables temp / `#temp` | Note de complexité | — |
| `sp_send_dbmail`, `xp_cmdshell`, serveurs liés, SQLCLR | **Drapeau sécurité / effet de bord** | relayé en audit |
| `WITH (NOLOCK)`, niveaux d'isolation | Note comportementale | — |

**Confiance (réutilise `language_signatures.yml`)** : `tsql = high` par défaut,
mais **downgrade à `medium`** sur procs à SQL dynamique dominant (le comportement
réel n'est pas déductible du texte → `bias toward not-verified`). Mécanique de cap
déjà en place (`check_ladder_traceability.py`), zéro nouveau code de gouvernance.

---

## 7. Lecture seule — garanties (section expert SQL + gouvernance)

La règle existe : `[DB_STRUCTURE_CHANGE_FORBIDDEN]` (STOP, escalade) +
`library-and-stack.md §C` (introspection `INFORMATION_SCHEMA` autorisée, tout DDL/DML
interdit). Application au db-reverse :

1. **Surface SQL émise — liste blanche stricte** (l'adaptateur n'a aucun chemin de
   code produisant autre chose) :
   - `SELECT` sur `sys.sql_modules`, `sys.procedures`, `sys.parameters`,
     `sys.objects`, `sys.sql_expression_dependencies`, `INFORMATION_SCHEMA.ROUTINES`
   - `OBJECT_DEFINITION(OBJECT_ID(@n))` (lossless ; **pas** `sp_helptext`)
2. **Source du corps** : `sys.sql_modules.definition`. Procs `WITH ENCRYPTION` →
   `definition = NULL` → `[REVERSE_PROC_ENCRYPTED]`, skip + log (jamais
   d'inférence).
3. **Permissions minimales recommandées** (à documenter pour le DBA) : login dédié
   `GRANT VIEW DEFINITION` + `db_datareader` (lecture métadonnées seule). Le module
   **n'exige pas** un login RO mais ne doit jamais en dépendre pour sa sûreté.
4. **Connexion** : `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED` (ne bloque
   pas la prod) ; jamais d'ouverture de transaction en écriture ;
   `ApplicationIntent=ReadOnly` optionnel (utile en Availability Group).
5. **Secret** : connexion composée **en RAM** depuis `stack.md`, jamais loggée,
   jamais écrite dans `db-introspection.json` (calque garde-fous arch STEP 8).
6. **Invariant nouveau** (`INVARIANTS.reverse.yml`) : `reverse-db-readonly` —
   l'adaptateur ne contient aucun token DDL/DML ; vérifié par grep de test +
   `reverse_smoke`.

---

## 8. Connection string depuis `stack.md`

Réutilise **exactement** la convention forward : section `## Active Database` de
`stack.md` avec `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD`
(`loader.yml:203-207`, `arch.md` STEP 8). Le db-reverse lit ces 5 clés, compose
la chaîne en RAM, introspect, déconnecte.

**Nuance d'isolation D4 à arbitrer** : `stack.md` est aujourd'hui lu par les
agents *forward*. Le faire lire par le module reverse est cohérent (même fichier
SSoT) mais doit être déclaré dans `loader.reverse.yml` (reads du nouvel agent /
script). Pas de copie de secret ; lecture seule.

---

## 9. Carte d'impact — fichiers créés / touchés

### Créations (autorisées par D4 — *nouveaux* fichiers)
| Fichier | Rôle |
|---|---|
| `sdd_reverse/db_introspect.py` | adaptateur live READ-ONLY (liste blanche SQL) |
| `sdd_reverse/dialects/sqlserver.py` | requêtes catalogue T-SQL (seam multi-SGBD) |
| `sdd_reverse/proc_unit_clusterer.py` | grappes de procs (§5) — **livré sous le nom `proc_module_clusterer.py`** |
| `sdd_reverse/tsql_body_analyzer.py` | signaux déterministes du corps (§6) — **livré sous le nom `sql_body_analyzer.py`** (multi-dialecte, pas T-SQL seul) |
| `sdd_reverse_scripts/reverse_proc_introspect.py` | CLI Phase 1L |
| `.claude/agents/reverse-proc-analyst.md` | 3a spécialisé T-SQL (ou mode de `reverse-tech-analyst`) |
| `.claude/commands/sdd-reverse-proc.md` (+ `-introspect`) | commandes user-facing |
| `.sdd/python/sdd_reverse/proc.reverse.template.md` | template analyse proc (isolé, ADV-9) |
| tests `tests/test_sdd_reverse_proc_*.py` | fixtures `.sql` (hors-ligne, pas de DB en CI) |

### Modifications de gouvernance (fichiers existants — *additions* uniquement)
| Fichier | Nature | Test impacté |
|---|---|---|
| `loader.reverse.yml` | + agent + commande(s) + reads `stack.md` | manifest mirror |
| `rules/reverse-engineering.md §6/§6.3` | + classes `[REVERSE_DB_*]` + émetteurs | réciprocité `[REVERSE_*]` |
| `INVARIANTS.reverse.yml` | + `reverse-db-readonly`, + snapshot-evidence | `reverse_smoke` |
| `reverse_smoke.py` | + checks (read-only, snapshot, no-spawn) | smoke count (13→N) |
| `crosscutting_feats.py::build_database_feat` | brancher procs introspectées | `test_l3_crosscutting` |
| `pyproject.toml` | + extra opt-in `reverse-db = ["pyodbc"]` | aucun (extra) |
| `CLAUDE.md §3/§4` | recompte commandes/agents reverse | — |
| `docs/reverse-engineering-workflow.md` | section « saveur DB » | — |

> **Bonne nouvelle gouvernance** : les classes `[REVERSE_*]` vivent dans
> `reverse-engineering.md §6` (taxonomie *séparée*), **pas** dans le compte des
> 189 de `error-classification.md` → le test `test_error_classification_count.py`
> n'est **pas** impacté. Seule la réciprocité `[REVERSE_*]` (émetteur ↔ taxonomie)
> doit rester alignée.

### Label chat
Aucun nouveau label : `[REVERSE]` (output-protocol §3, liste fermée) couvre déjà
tous les agents/commandes reverse. ✅

---

## 10. Nouvelles classes `[REVERSE_*]` (avec émetteur — règle de réciprocité)

À ajouter **ensemble** (classe + émetteur), sinon code mort (cf. purge MA-7) :

| Classe | Bloquant | Émetteur |
|---|:--:|---|
| `[REVERSE_DB_UNREACHABLE]` | OUI | `reverse_proc_introspect.py` (timeout/firewall) |
| `[REVERSE_DB_AUTH_FAILED]` | OUI | idem (login invalide / droits insuffisants) |
| `[REVERSE_DB_CONFIG_MISSING]` | OUI | `## Active Database` absent/incomplet de `stack.md` |
| `[REVERSE_PROC_ENCRYPTED]` | NON (info) | `db_introspect.py` (`definition = NULL`) |
| `[REVERSE_PROC_NOT_FOUND]` | OUI | `/sdd-reverse-proc {X}` avec X absent du catalogue |
| `[REVERSE_DB_READONLY_VIOLATION]` | OUI | garde liste-blanche (statement non-SELECT tenté) |
| `[REVERSE_DYNAMIC_SQL_DOMINANT]` | NON (info) | `tsql_body_analyzer.py` → downgrade confiance |

> Réciprocité enforced ; chaque ajout = ligne dans §6 + §6.3 + un test.

---

## 11. Phasage MVP recommandé

- **MVP (SQL Server only)** : Phase 1L introspection (`pyodbc` extra) + snapshot
  `proc/` + `db-introspection.json` + clustering déterministe + extension de la
  FEAT crosscut « Base de données » (déterministe, 0 token, livrable immédiat).
  → *Déjà utile sans LLM* : on obtient une FEAT DB complète et fidèle.
- **V2** : `reverse-proc-analyst` (3a T-SQL) + escalier 3b/3c → FEATs/US métier
  par grappe ; cap de confiance + downgrade SQL dynamique.
- **V3** : multi-SGBD (PL/pgSQL via `pg_proc`, PL/SQL via `ALL_SOURCE`, MySQL
  routines) — le seam `dialects/` est posé dès le MVP ; ajouter caps
  `plpgsql`/`plsql` dans `language_signatures.yml`.

---

## 12. Risques & décisions ouvertes (pour le Tech Lead)

1. **Driver** : `pyodbc` extra opt-in (reco) vs `Invoke-Sqlcmd` vs runtime-bridge
   à la arch ? → impacte la portabilité CI.
2. **Granularité de grappe** : la convention de nommage des procs de *votre* base
   (préfixe `usp_`, schéma métier ?) conditionne la qualité du clustering — à
   calibrer sur un échantillon réel.
3. **Procs sans logique métier** (CRUD pur, reporting) : démotion en « plomberie »
   (comme l'escalier démote déjà la plomberie) ou exclusion ? Reco : démotion, pas
   exclusion (traçabilité).
4. **Volume** : cap d'items (`_MAX_ITEMS=80`) déjà présent dans la FEAT crosscut ;
   prévoir pagination/log de troncature pour les très grosses bases.
5. **`stack.md` lu par le reverse** : valider l'entorse D4 (lecture seule d'un
   fichier forward) — cohérent mais à acter.
6. **SQL dynamique / SQLCLR / linked servers** : zones de confiance faible
   assumées et signalées, jamais devinées.

---

## 13. Conclusion

Le coût réel n'est pas « un second moteur de reverse » mais **un adaptateur
d'introspection read-only + un analyste T-SQL spécialisé**, branchés sur un
escalier et une gouvernance déjà éprouvés. En suivant l'Option B (snapshot-first)
et en copiant le patron READ-ONLY d'`arch` Phase B, l'impact reste **additif et
isolé** (D4 respecté, zéro édition destructive, evidence `file:line` préservée).
Le `proc/` que vous imaginiez est correct : c'est le **snapshot T-SQL**, source de
vérité hors-ligne de cette saveur de reverse.
