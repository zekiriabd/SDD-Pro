# Audit du reverse engineering **base de données** — SDD_Pro v7.0.0

> **Date** : 2026-07-24 · **Angle** : DBA senior + SQL developer + architecte
> agentique. **Objet** : évaluer la capacité de SDD_Pro à faire du reverse
> engineering **à partir d'une connection string** — extraire tous les objets
> SQL, en analyser la **logique métier**, et produire une **documentation
> métier humaine** (features, user stories, règles de gestion, scénarios,
> cahier des charges) exploitable par un fonctionnel / chef de projet / architecte.
> **Comparateurs** : [SchemaSpy](https://github.com/schemaspy/schemaspy),
> [SchemaCrawler](https://github.com/schemacrawler/schemacrawler),
> [tbls](https://github.com/k1LoW/tbls), et [Cutter](https://github.com/rizinorg/cutter)
> (binaire, déjà traité dans l'audit applicatif).

---

> **Mise à jour 2026-07-24 (P0.1 + 4 dialectes livrés)** :
> 1. **Vues + triggers** introspectés (corps analysé par le même escalier —
>    1 objet SQL = 1 US) : `dialects/*.py`, agent `reverse-sql-analyst`.
> 2. **4 moteurs principaux** couverts : **SQL Server** et **PostgreSQL**
>    (live-validés), **Oracle** (PL/SQL + packages) et **MySQL/MariaDB**
>    (scaffold-validés : requêtes read-only + flux offline testés, runtime live
>    pending — aucun driver/instance au bench). Chaque moteur enumère
>    procédures + fonctions + vues + triggers (+ packages Oracle) en **SELECT
>    pur** (garde-fou `readonly_guard`). Cf. `tests/test_reverse_db_dialects.py`,
>    `tests/test_reverse_db_views_triggers.py`. Les « ❌ » ci-dessous restent
>    pour l'historique ; statut réel = ✅ (voir §7).

## 0. Verdict exécutif

**La brique existe déjà, mais elle est étroite.** SDD_Pro possède un module
`proc-reverse` (`/sdd-proc-reverse-full`, agent `reverse-sql-analyst`, dialectes
SQL Server + PostgreSQL) qui fait ce qu'**aucun** des outils comparés ne fait :
il **lit le corps des procédures stockées et le traduit en logique métier**
(1 procédure = 1 User Story, 1 module = 1 FEAT), avec evidence `file:line`,
confidence, et — depuis le travail du 2026-07-24 — restitution en **cahier des
charges `.docx`** via `/spec-book`. C'est le **différenciateur fort** : SchemaSpy,
SchemaCrawler et tbls sont **structurels** (métadonnées, ERD, dépendances) et
s'arrêtent explicitement au seuil de la sémantique métier.

Mais votre cahier des charges DB demande **plus large** que ce que le module
couvre aujourd'hui :

| Objet SQL demandé | Couvert aujourd'hui ? |
|---|---|
| Procédures stockées | ✅ corps analysé (business logic) |
| Fonctions (scalaires/table) | ✅ corps analysé (`type IN 'FN','IF','TF'`) |
| Tables / colonnes / contraintes / index / FK | ⚠️ **seulement via DDL statique** (`db_schema_extractor`), **pas** en live |
| **Vues (corps)** | ❌ **noms seulement** (`db_schema_extractor` B4, corps non analysé) |
| **Triggers (corps)** | ❌ **noms seulement** |
| **Jobs / agent SQL** | ❌ absent |
| **Packages (Oracle PL/SQL)** | ❌ absent |
| **Séquences / synonymes** | ❌ absent |
| **Linked servers** | ❌ absent |
| **Dépendances objet↔objet** | ✅ **graphe global (P0.2)** — object→table + object→object, impact analysis, Mermaid |
| **Applications consommatrices** | ✅ **corrélation DB↔apps (P0.3)** — `correlate_db_app.py` (db-introspection × data-access) : qui appelle quelle proc / touche quelle table, orphelins, drift |
| Schéma global (ERD) | ⚠️ via `reverse_synth` (ERD Mermaid depuis DDL statique), pas depuis le live |

**En une phrase** : le cœur (escalier + business-logic + cahier des charges) est
là et différenciant ; ce qui manque, c'est **(a)** l'introspection live du
**graphe d'objets complet** (au-delà de proc+fonction), **(b)** l'analyse du
**corps des vues/triggers**, **(c)** le **graphe de dépendances objet↔objet et
objet↔application**, et **(d)** un **rapport structurel visuel** de niveau
SchemaSpy. La roadmap §6 détaille.

---

## 1. Ce qui existe aujourd'hui (état précis, vérifié au code)

Pipeline `proc-reverse` (SSoT : `reverse-proc-engineering.audit.md`) :

1. **Introspection live READ-ONLY** (`db_introspect.py` + `dialects/`) :
   connexion via `stack.md ## Active Database`, `ApplicationIntent=ReadOnly` +
   `READ UNCOMMITTED`, corps récupéré loss-less par `sys.sql_modules.definition`
   (SQL Server) / `pg_get_functiondef` (PostgreSQL). Filtre :
   **`o.type IN ('P','FN','IF','TF')`** — procédures + fonctions uniquement.
   Barrière dure `readonly_guard` (blocklist DDL/DML, SELECT-only), mot de passe
   jamais loggé/persisté. **Sécurité exemplaire.**
2. **Snapshot** `proc-snapshot/{schema}.{name}.sql` (evidence stable, idempotent,
   rejouable offline sans DB).
3. **Analyse de corps** (`sql_body_analyzer.py`, dialect-agnostic, **regex**) :
   params, tables lues/écrites, branches, `RAISERROR`, transactions, SQL
   dynamique, appels, curseurs, tables temp — ancrés en n° de ligne. Route
   simple/complexe.
4. **Escalier** : procédures simples → US **déterministe 0 token** (~70-80 %) ;
   complexes → agent `reverse-sql-analyst` (Opus). Clustering en modules
   (`proc_module_clusterer.py`, heuristique de nommage).
5. **Assemblage** : `build_proc_feats.py` → 1 FEAT/module (rung 2 **déterministe**,
   pas LLM — asymétrie avec l'escalier code où 3c est LLM).
6. **Validation** : `validate_reverse_feat.py` + REVERSE-GATE (confidence < high
   ⇒ `allow-sdd-full=false`).
7. **Restitution humaine** : `/spec-book` → `cahier-des-charges.docx` (langage
   gérant), **fonctionne déjà** sur les FEATs proc-reverse.

Schéma structurel : `db_schema_extractor.py` extrait tables/colonnes/FK/index +
ORM depuis **DDL statique `.sql`** (pas le live) ; vues/triggers = **noms seuls**
(`parseWarnings`). `reverse_synth.py` rend un **ERD Mermaid** depuis ce schéma.

---

## 2. Comparaison avec l'état de l'art

| Critère | **SDD_Pro proc-reverse** | **SchemaSpy** | **SchemaCrawler** | **tbls** | **Cutter** |
|---|---|---|---|---|---|
| Domaine | DB → **spécifications métier** | DB → doc structurelle | DB → doc + lint + diff | DB → doc CI (markdown) | binaire → désassemblage |
| Tables/colonnes/FK/index | ⚠️ DDL statique | ✅ live (JDBC) | ✅ live | ✅ live | n/a |
| Vues (structure) | ❌ noms | ✅ | ✅ | ✅ | n/a |
| **Vues / triggers (corps + logique)** | ❌ | ❌ | ❌ | ❌ | n/a |
| **Procédures (logique métier)** | ✅ **corps → US** | ❌ | ❌ (métadonnées) | ❌ | n/a |
| Relations implicites (sans FK) | ❌ | ✅ (heuristique) | ✅ | partiel | n/a |
| ERD / diagrammes | ⚠️ Mermaid (synth) | ✅ **HTML interactif** | ✅ | ✅ (mermaid/PlantUML) | ✅ CFG/callgraph |
| Graphe de dépendances | ⚠️ tables/proc | ✅ inter-tables | ✅ | ✅ | ✅ |
| Rapport navigable HTML | ❌ | ✅ **fort** | ✅ | ✅ (markdown) | ✅ GUI |
| Lint / diff schéma | ❌ | ❌ | ✅ **fort** | ✅ | n/a |
| Intégration MCP / agentique | ⚠️ (headless, pas de serveur MCP) | ❌ | ✅ **serveur MCP** | ❌ | ✅ MCP (ReVA) |
| **Doc métier humaine (non-IT)** | ✅ **cahier des charges `.docx`** | ❌ | ❌ | ❌ | ❌ |
| SGBD | **SQL Server + PostgreSQL + Oracle + MySQL/MariaDB** (Oracle/MySQL scaffold) | 12+ via JDBC | 30+ | 10+ | n/a |
| Sécurité read-only | ✅ **double barrière** | lecture métadonnées | lecture | lecture | n/a |

**Lecture** : les deux mondes sont **complémentaires, pas concurrents**.
SchemaSpy/SchemaCrawler/tbls dominent la **couverture structurelle** et la
**visualisation** ; SDD_Pro est **seul** à monter jusqu'à la **logique métier
et au cahier des charges humain**. La stratégie gagnante n'est pas de refaire
SchemaSpy, mais d'**emprunter sa couche structurelle** (couverture d'objets +
ERD + relations implicites + rapport HTML) **comme socle L0/L1** de l'escalier
métier existant.

---

## 3. Le différenciateur, à protéger et étendre

Aucun outil open-source comparé n'extrait la logique métier des procédures en
langage humain (confirmé par la recherche : *« most open-source tools focus
primarily on schema documentation rather than deep business logic extraction »*).
SDD_Pro le fait déjà pour procs + fonctions. Deux extensions naturelles à fort
ROI :

1. **Étendre l'escalier aux vues, triggers et fonctions comme aux procédures** :
   une vue métier complexe (jointures + CASE + agrégats) ou un trigger (règles
   d'intégrité, cascades, audit) **portent de la logique métier** au même titre
   qu'une procédure. Le même barreau `reverse-sql-analyst` (déjà multi-dialecte,
   déjà read-only) peut les traiter — il suffit d'élargir le filtre
   d'introspection (`type IN ('P','FN','IF','TF','V','TR')`) et le snapshot.
2. ~~**Corréler objets DB ↔ applications consommatrices**~~ ✅ **LIVRÉ
   2026-07-24 (P0.3)** : `sql_app_correlation.py` + CLI `correlate_db_app.py`
   joignent `db-introspection.json` × `data-access.json` → « quel fichier
   appelle quelle proc / touche quelle table », procédures orphelines (jamais
   appelées) et drift (appels vers une proc absente de la base). Sortie
   `db-app-correlation.{json,md}` (+ Mermaid).

---

## 4. Failles / risques identifiés (spécifiques DB)

### 4.1 CRITIQUE
- **DB1 — Couverture d'objets incomplète en live.** Seuls procs+fonctions sont
  introspectés. Vues/triggers/jobs/packages/séquences/synonymes/linked servers
  absents → un reverse « complet de la couche DB » ne l'est pas. Or beaucoup de
  logique métier vit dans les **vues** (règles de présentation/agrégation) et
  **triggers** (intégrité, cascades, audit).
- **DB2 — Analyse 100 % regex, pas d'AST SQL.** ⚠️ **PARTIELLEMENT ATTÉNUÉ
  2026-07-24 (P1)** : `sql_body_analyzer` masque désormais **commentaires ET
  littéraux de chaîne** avant l'extraction — le SQL construit dynamiquement
  (`SET @sql='INSERT INTO X…'`) ou cité dans un message d'erreur n'est plus
  compté comme une écriture/lecture statique (fin d'une classe majeure de faux
  positifs), tandis que le flag `dynamicSql` continue de baisser la confiance.
  **Reste** : pas d'AST réel — CTE imbriquées, `MERGE`/`PIVOT` complexes,
  résolution d'alias restent best-effort. Un vrai parseur SQL par dialecte est
  l'étape suivante.
- ~~**DB3 — Pas de graphe de dépendances objet↔objet global.**~~ ✅ **LIVRÉ
  2026-07-24 (P0.2)** : `sql_dependency_graph.py` construit un graphe
  object→table (reads/writes) + object→object (calls) **déterministe et
  cross-moteur** (dérivé des signaux d'introspection, 0 requête live
  supplémentaire), persisté dans `db-introspection.json.dependencyGraph`.
  `impact_of(graph, obj)` donne `{dependsOn, dependents}` (analyse d'impact) et
  `to_mermaid()` rend le diagramme. Limite : la résolution des appels est par
  nom (le SQL dynamique reste invisible — cf. DB2).

### 4.2 MAJEUR
- **DB4 — Clustering en modules par heuristique de nommage** (`usp_`, CamelCase).
  ⚠️ **ATTÉNUÉ 2026-07-24 (P0.2)** : `cohesion_modules()` groupe par graphe de
  dépendances (objets partageant des tables / s'appelant) — robuste sans
  convention de nommage. **Opt-in** (`SDD_REVERSE_CLUSTER_COHESION=1`) pour ne
  pas changer le comportement par défaut ; à promouvoir en défaut après
  validation terrain.
- **DB5 — Rung 2 déterministe côté DB vs LLM côté code.** ⚠️ **ADRESSÉ 2026-07-24
  (opt-in)** : nouvel agent `reverse-sql-feat-composer` (Opus, parité avec 3c
  `reverse-feat-composer`) qui synthétise la FEAT module depuis les US d'objets
  SQL (démotion plomberie, narratif transverse, même gate `validate_reverse_feat`).
  **Opt-in** `SDD_REVERSE_FEAT_LLM=1` ; défaut = déterministe `build_proc_feats.py`
  (0 token). Réservé aux modules à forte logique métier.
- ~~**DB6 — Multi-dialecte partiel.**~~ ✅ **LARGEMENT ADRESSÉ 2026-07-24** :
  les **4 moteurs principaux** sont couverts — SQL Server + PostgreSQL
  (live-validés), Oracle (PL/SQL + packages) + MySQL/MariaDB (scaffold-validés,
  runtime live pending). Reste DB2/SQLite en `_PLANNED`. **Caveat** : Oracle et
  MySQL doivent être validés en runtime sur une vraie base (driver + instance)
  avant usage prod — la forme des requêtes et le flux sont testés offline, pas
  le comportement live.
- **DB7 — Pas de rapport structurel visuel** de niveau SchemaSpy (HTML navigable,
  ERD cliquable, anomalies). `reverse_synth` produit un ERD Mermaid statique
  depuis le DDL, pas une exploration interactive depuis le live.
- **DB8 — Cap confidence T-SQL/PL-pgSQL.** SQL dynamique → downgrade `medium` ;
  chiffré (`WITH ENCRYPTION`) → `low`. Beaucoup de procs réelles utilisent du SQL
  dynamique ⇒ FEATs medium ⇒ bloquées par REVERSE-GATE ⇒ boucle humaine (mais
  celle-ci se ferme désormais en 1 run, cf. C3 audit applicatif).

### 4.3 MINEUR / RISQUES OPÉRATIONNELS
- **DB9 — Introspection live vs snapshot DDL désynchronisés.** Le schéma
  structurel vient de fichiers `.sql` (repo), la logique vient du live — les deux
  peuvent diverger (base en avance/retard sur le repo). À réconcilier ou à tracer.
- **DB10 — Sécurité : lecture seule excellente, mais pas de gestion de la
  volumétrie de métadonnées** (base à 5 000 objets → coût LLM et temps ; pas de
  `--sample`/`--schema-filter` documenté au-delà du clustering).
- **DB11 — Secrets dans le corps SQL** (connection strings en dur dans du SQL
  dynamique, comptes de linked servers) : `readonly_guard` protège l'exécution
  mais l'analyse de corps ne masque pas systématiquement les secrets rencontrés
  (à aligner sur `[REVERSE_SECRETS_DETECTED]` du reverse code).

---

## 5. Emprunts recommandés (comment chaque outil améliore SDD_Pro)

### Depuis **SchemaSpy** (le comparateur DB principal cité)
- **Couche structurelle live comme socle L0/L1** : introspecter en live
  l'ensemble tables/colonnes/contraintes/index/FK/vues (métadonnées), au lieu de
  dépendre du DDL statique. Alimente l'escalier métier ET l'ERD.
- **Détection de relations implicites** (FK non déclarées inférées par
  nom/colonne) — précieux pour les bases legacy sans contraintes formelles.
- **Rapport HTML interactif + ERD cliquable + rapport d'anomalies** : à générer
  en complément du `.docx` métier (deux publics : DBA ↔ ERD interactif ; gérant ↔
  cahier des charges).

### Depuis **SchemaCrawler**
- **Lint de schéma + diff** : détecter anti-patterns (tables sans PK, colonnes
  sans type, index redondants) et **diff entre deux introspections** (dérive de
  schéma dans le temps) — utile pour la fiabilité et le suivi de migration.
- **Serveur MCP** : SchemaCrawler expose désormais un serveur MCP. SDD_Pro
  pourrait exposer son introspection (`db-introspection.json`, graphe d'objets)
  via MCP pour que d'autres agents/clients l'interrogent — cohérent avec le
  pattern tool-driven de ReVA.

### Depuis **tbls**
- **Doc CI-friendly + diff en CI** : générer une doc markdown versionnable et
  **faire échouer la CI si le schéma dérive de la doc** — garantit que le cahier
  des charges reste synchrone avec la base (répond à « fiable et cohérente »).

### Depuis **Cutter/ReVA** (binaire, mais principes transférables)
- **Graphe de dépendances visuel** (callgraph d'objets SQL) et **outils
  granulaires tool-driven** exposant du contexte subsidiaire (cross-refs
  d'objets) pour guider l'agent et réduire l'hallucination.

---

## 6. Roadmap DB-reverse priorisée

### P0 — Étendre le périmètre d'objets (cœur de la demande)
1. ~~**Introspection d'objets élargie**~~ ✅ **LIVRÉ 2026-07-24 (SQL Server)** :
   filtre live = `('P','FN','IF','TF','V','TR')`, corps des **vues** et
   **triggers** analysé par le même escalier. Reste : porter à PostgreSQL
   (`pg_views`/`pg_get_viewdef`, `pg_trigger`/`pg_get_triggerdef`) + Oracle.
2. ~~**Graphe de dépendances objet↔objet**~~ ✅ **LIVRÉ 2026-07-24 (P0.2)** :
   graphe dérivé des signaux (cross-moteur) + **augmentation par les catalogues
   authoritatifs** (`sys.sql_expression_dependencies` SQL Server /
   `all_dependencies` Oracle — arêtes `source:"catalog"` fusionnées, résolution
   de noms exacte) + clustering cohésion + `impact_of()` + Mermaid. **Limite
   honnête** : le SQL **dynamique** reste invisible (aucun catalogue ne le trace).
3. ~~**Corrélation objets DB ↔ applications**~~ ✅ **LIVRÉ 2026-07-24 (P0.3)** —
   `correlate_db_app.py`. Reste : lancer automatiquement la corrélation en fin de
   pipeline quand les deux artefacts (DB + code) coexistent.

### P1 — Fiabilité & couverture
4. ~~**Parsing SQL plus robuste** — tokenizer conscient chaînes/commentaires~~
   ✅ **LIVRÉ 2026-07-24 (P1)** : masquage commentaires + littéraux de chaîne
   (`_blank_string_literals`), `tests/test_sql_body_analyzer_masking.py`. Reste :
   parseur SQL par dialecte (AST) pour les cas complexes (CTE/MERGE/alias).
5. ~~**Rung 2 LLM pour la FEAT DB** (DB5)~~ ✅ **LIVRÉ 2026-07-24 (opt-in)** :
   agent `reverse-sql-feat-composer` (`SDD_REVERSE_FEAT_LLM=1`). Reste : le
   promouvoir en défaut pour les modules complexes après validation terrain.
6. **Dialecte Oracle** (DB6) : packages PL/SQL = le gisement de logique métier le
   plus riche non couvert.
7. **Masquage secrets dans les corps SQL** (DB11).

### P2 — Restitution & intégration (emprunts)
8. **Rapport structurel HTML + ERD interactif** (emprunt SchemaSpy) en complément
   du `.docx`.
9. **Lint + diff de schéma en CI** (emprunt SchemaCrawler/tbls) → garantit la
   cohérence doc↔base.
10. **Serveur MCP** exposant l'introspection (emprunt SchemaCrawler/ReVA).

> **Déjà livré (2026-07-24)** : la **documentation cahier des charges** demandée
> (« générer une doc de type cahier des charges dans le répertoire doc ») est
> opérationnelle via `/spec-book` — elle humanise les FEATs proc-reverse
> (features, US, règles de gestion, scénarios) en `.docx` lisible par un
> fonctionnel. Étendre P0 (vues/triggers/graphe) l'enrichira automatiquement,
> puisque le cahier des charges se régénère depuis les FEATs.

---

## 7. Réponse directe à la demande

| Demande | État |
|---|---|
| Se connecter via connection string | ✅ `stack.md ## Active Database` + `db_introspect` (read-only) |
| Récupérer procs, fonctions | ✅ |
| Récupérer vues, triggers, tables, contraintes, index | ✅ **vues + triggers (corps, P0.1 livré, SQL Server)** ; tables/FK/index via DDL statique (live = P0 suite) |
| Packages (Oracle PL/SQL) | ✅ **P0.1 (Oracle, scaffold)** — PACKAGE + PACKAGE BODY via DBMS_METADATA |
| Jobs, séquences, synonymes, linked servers | ❌ — suite P0 / P1 |
| Schéma global (ERD) | ⚠️ Mermaid depuis DDL — **P2.8** pour le live/interactif |
| Reverse détaillé de chaque composant SQL | ✅ procs/fonctions ; ⚠️ reste — **P0.1** |
| Analyser la logique métier des procs/fonctions | ✅ (différenciateur) |
| Dépendances objet↔objet et objet↔application | ✅ **P0.2 (graphe) + P0.3 (corrélation DB↔apps)** |
| Escalade intelligente (comme le reverse code) | ✅ (routage complexité, escalier, confidence min-monotone) |
| Doc métier humaine (features/US/règles/scénarios/cahier des charges) | ✅ **`/spec-book` → `.docx`** |
| Audit de la solution (failles/risques/améliorations/fiabilité) | ✅ **ce document** (§4-§6) |
| Comparaison SchemaSpy / (SchemaCrawler / tbls) / Cutter | ✅ **§2** |

---

**Sources** :
[SchemaSpy](https://github.com/schemaspy/schemaspy) ·
[SchemaCrawler](https://github.com/schemacrawler/schemacrawler) ·
[tbls](https://github.com/k1LoW/tbls) ·
[Cutter](https://github.com/rizinorg/cutter) ·
[SchemaSpy vs SchemaCrawler (DEV)](https://dev.to/sualeh/schemaspy-vs-schemacrawler-which-database-documentation-tool-is-right-for-you-3do9) ·
[DBMS Tools — reverse engineering](https://dbmstools.com/categories/database-diagram-tools)

*Recommandations P0-P2 = propositions ; mise en œuvre = décision produit (DBA / Tech Lead).*
