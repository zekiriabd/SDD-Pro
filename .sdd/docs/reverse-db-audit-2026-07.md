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

> **Contre-audit 2026-08-29 — ce qui était affirmé et ne l'était pas.**
>
> Un audit indépendant a relu le code plutôt que cette documentation. La garantie
> read-only est ressortie comme le point le plus solide du framework (8 sites
> d'exécution SQL, tous gardés, défense en profondeur réelle) ; la **garantie
> d'ordonnancement par vagues**, elle, était fausse sur 3 des 4 moteurs annoncés.
> Corrections appliquées :
>
> | # | Ce qui était affirmé | Ce qui était vrai | Correctif |
> |---|---|---|---|
> | C1 | « tout appelé est analysé avant son appelant » | `CALL spB(1,2)` extrayait l'appelé `sp` (le lookahead `(?!\s*\()` faisait rétro-agir le moteur *à l'intérieur* du nom) ; les appels PL/SQL nus, les fonctions scalaires en expression et les affectations n'étaient extraits dans **aucun** dialecte → appelant et appelé dans la **même** vague | ancrage de fin d'identifiant + canal `callsInferred` (résolu-ou-jeté) ; `db-reverse-tsql.md §2.11` ; tests bout-en-bout par dialecte |
> | C2 | catalogue de dépendances « exploité » | lu, gardé, fusionné dans `dependencyGraph`… puis ignoré par `plan_waves`, qui n'ordonnait que sur le regex — sur Oracle, le seul moteur où le regex ne peut structurellement pas suffire | `attach_catalog_calls` projette les arêtes catalogue sur les objets ; `resolve_calls` les consomme en premier |
> | M2 | « tout changement de corps change la `contextVersion` » | seule la **forme** était hachée : déplacer un seuil dans un `IF` existant laissait la version identique, donc aucune dérive détectée et hypothèses périmées réutilisées | `bodyHash` par objet, entré dans les faits |
> | M1 | PostgreSQL « live-validé » | aucun run réel — contredit par la réserve inscrite dans ce document même | ramené à `scaffold-validated` (cf. §Réserve) |
> | M3 | frontière faits/hypothèses « garantie par construction » | garantie par la whitelist de fusion uniquement ; aucune entrée de matrice d'ownership pour les 6 agents db-reverse | entrées ajoutées + formulation corrigée en décrivant le mécanisme réel |
> | m4 | `reverse_smoke` « valide les constantes read-only des dialectes » | il ne les regardait pas | `check_dialect_queries_readonly` ajouté (14ᵉ check) |
>
> Leçon transverse, valable au-delà de ce module : **les trois affirmations les
> plus fausses étaient les trois plus visibles** — une garantie d'ordre, une
> garantie de version, un label commercial. Un mécanisme qu'on décrit sans le
> tester finit par être décrit à la place d'être vrai.

---

> **Mise à jour 2026-07-24 (P0.1 + 4 dialectes livrés)** :
> 1. **Vues + triggers** introspectés (corps analysé par le même escalier —
>    1 objet SQL = 1 US) : `dialects/*.py`, agent `reverse-sql-analyst`.
> 2. **4 moteurs principaux** couverts : **SQL Server** (live-validé — run réel
>    du 2026-08-27, cf. les post-mortems `EXECUTE AS` et `lineCount` dans
>    `sql_body_analyzer.py`), **PostgreSQL**, **Oracle** (PL/SQL + packages) et
>    **MySQL/MariaDB** (scaffold-validés : requêtes read-only + flux offline
>    testés, runtime live pending — aucun driver/instance au bench).
>    **Correction 2026-08-29 (M1)** : PostgreSQL était annoncé « live-validé »
>    ici et au §7, en contradiction directe avec la réserve non levée inscrite
>    quelques lignes plus bas (« aucun run n'a été fait contre une vraie base »).
>    Aucune trace d'un run PostgreSQL réel n'existe. Statut ramené à
>    **scaffold-validated** tant qu'une preuve n'est pas produite : une
>    validation qu'on ne peut pas montrer n'est pas une validation.
>    Chaque moteur enumère
>    procédures + fonctions + vues + triggers (+ packages Oracle) en **SELECT
>    pur** (garde-fou `readonly_guard`). Cf. `tests/test_reverse_db_dialects.py`,
>    `tests/test_reverse_db_views_triggers.py`. Les « ❌ » ci-dessous restent
>    pour l'historique ; statut réel = ✅ (voir §7).
>
> **Mise à jour 2026-08-25 (C1 structure live + objets de catalogue + clustering)** :
> 1. **Structure relationnelle lue en LIVE** (`db_schema_live.py`) : tables,
>    colonnes, types, PK, FK, index, contraintes CHECK depuis le **catalogue**,
>    plus depuis un DDL `.sql` statique. Produit le **même** contrat
>    `db-schema.json` que `db_schema_extractor` avec `completeness: "live"`, donc
>    l'ERD (`reverse_synth`), les entities et la FEAT transverse « Base de
>    données » fonctionnent inchangés. L'evidence reste `file:line` grâce à un
>    rendu `CREATE TABLE` lisible et **jamais exécuté** sous
>    `.sys/schema-snapshot/`. Les 4 dialectes déclarent les 5 requêtes de
>    structure (`tests/test_reverse_db_schema_live.py`).
> 2. **Objets de catalogue sans corps** : jobs (SQL Agent / pg_cron /
>    DBMS_SCHEDULER / events MySQL), séquences, synonymes, linked servers, types
>    utilisateur — best-effort **par requête** (un `GRANT` refusé sur `msdb`
>    dégrade en avertissement, il n'interrompt pas l'introspection).
> 3. **Clustering en modules** : profilage dynamique du corpus de noms,
>    rattachement des sous-objets (`ClientAdresse` → `Client`) et **bascule
>    automatique** nommage → cohésion du graphe (seuil de fragmentation 0.50).
>    Plus d'opt-in : c'est le défaut, avec deux overrides Tech Lead. Stratégie
>    retenue **affichée en ligne de chat** + tracée dans
>    `inventory.json._clusteringReport` (`tests/test_reverse_db_clustering.py`).
> 4. **Connection string en entrée directe** (`conn_string.py`, `--conn-str`) et
>    **bornage du périmètre** (`object_filter.py` : `--schema` / `--include` /
>    `--exclude` / `--limit`), pour qu'une base de 3000 objets soit exécutable.
>
> **Mise à jour 2026-08-26 (refonte Phase 0 — comprendre avant d'écrire)** :
> le pipeline passait du corps SQL brut à la User Story sans jamais construire de
> représentation partagée du domaine. Quatre défauts s'en suivaient, tous fermés
> ici :
> 1. **Phase 0 obligatoire** (`/sdd-db-context`) — `db-context.json`, SSoT
>    **versionné** (`contextVersion` = sha256 des faits) et **diffable**, en deux
>    rungs : `0.A` déterministe (faits, matrice CRUD C/U/D, graphe d'appels
>    résolu, plan de vagues) puis `0.B` `reverse-db-architect` (hypothèses —
>    glossaire, sous-domaines, rôles, risques, questions ouvertes). Les deux
>    couches vivent dans des branches séparées et l'agent écrit un **fichier
>    distinct** fusionné par script : il ne peut pas écraser un fait. Une base
>    inchangée réutilise l'interprétation ; une base modifiée l'abandonne.
> 2. **Context slicing** — plus aucun agent ne lit la base entière. Chacun reçoit
>    `db-context/packs/{objet}.md` : son corps, la structure des seules tables
>    qu'il touche, le **résumé déjà écrit** de ce qu'il appelle (profondeur 2),
>    ses appelants, les hypothèses le concernant. La règle d'isolation n'est pas
>    relâchée, elle est **redirigée** — et le pack déclare ce qu'il a tronqué.
> 3. **Ordonnancement par vagues** — le dispatch suivait l'ordre d'itération de
>    l'inventaire, donc un appelant pouvait être analysé avant son appelé.
>    Désormais : arêtes `calls` résolues, composantes fortement connexes
>    condensées (Tarjan — la récursion T-SQL est réelle), tri topologique. Le
>    débit ne baisse pas : le parallélisme borné joue **à l'intérieur** d'une
>    vague, avec une seule barrière entre deux vagues, où les résumés sont
>    réinjectés dans `db-context.findings`.
> 4. **Routage conscient de la composition** — `complexity_reasons()` ignorait
>    `callsProcs`. Un orchestrateur de 38 lignes sans branche déléguant sa règle
>    à six procédures sortait « simple », décrit par un template, en `high` : un
>    **faux vert** qui traversait la REVERSE-GATE. Déléguer n'est pas être
>    simple. Un appelé non résolu ou une récursion plafonnent désormais la
>    confidence à `medium`, min-monotone vers le haut.
>
> **Spécialisation** : l'analyste unique devient 4 spécialistes par famille
> (`reverse-sql-analyst` procédures, `-function-`, `-view-`, `-trigger-analyst`),
> parce que l'angle diffère réellement — une opération, un calcul sans effet de
> bord, une projection et ses filtres cachés, un invariant événementiel. Socle
> d'expertise commun factorisé dans `rules/db-reverse-tsql.md`.
>
> **Routage de tier par objet** (`db_tier_router`) : `none` / `fast` /
> `balanced` / `deep` selon ce que le corps *cache*. Le routeur ne connaît aucun
> nom de modèle — un test l'interdit ; la résolution tier → modèle appartient au
> provider actif, donc la même rubrique vaut sur Anthropic, Google, OpenAI et
> Moonshot.
>
> Couverture : `tests/test_db_context.py` (57 tests, hors ligne). Invariants :
> `reverse-db-context-facts-vs-hypotheses`,
> `reverse-db-context-versioned-and-diffable`, `reverse-db-wave-ordering`,
> `reverse-db-call-aware-routing`, `reverse-db-context-slicing`.

> **Réserve, explicite et partiellement levée** : tout ce qui précède est validé
> **hors ligne** (2400 tests, catalogues synthétiques). Seul **SQL Server** a
> depuis été éprouvé contre une vraie base (2026-08-27, base de 118 objets — les
> défauts trouvés à cette occasion sont documentés dans `sql_body_analyzer.py` :
> callee fantôme `AS` sur `EXECUTE AS`, `lineCount` surcompté d'une ligne).
> **PostgreSQL, Oracle et MySQL** n'ont jamais été exécutés contre une instance
> réelle : permissions, volumétrie et versions de moteur restent à éprouver, en
> particulier sur `msdb` (jobs). Ces trois moteurs restent
> **scaffold-validated** — cf. la correction M1 (2026-08-29) en tête de document
> et au §7 DB6, où PostgreSQL était annoncé « live-validé » en contradiction
> avec cette réserve.

## 0. Verdict exécutif

**La brique existe déjà, mais elle est étroite.** SDD_Pro possède un module
`db-reverse` (`/sdd-db-reverse-full`, agent `reverse-sql-analyst`, dialectes
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
| Tables / colonnes / contraintes / index / FK | ✅ **live** depuis le catalogue (`db_schema_live`, C1 2026-08-25) — le DDL statique reste le chemin du reverse *applicatif* |
| **Vues (corps)** | ✅ corps analysé (1 vue = 1 US) |
| **Triggers (corps)** | ✅ corps analysé (1 trigger = 1 US) |
| **Jobs / agent SQL** | ✅ **live** (msdb / pg_cron / DBMS_SCHEDULER / events MySQL), best-effort : un droit refusé dégrade en avertissement |
| **Packages (Oracle PL/SQL)** | ✅ corps analysé |
| **Séquences / synonymes** | ✅ **live** (objets de catalogue, best-effort) |
| **Linked servers** | ✅ **live** (objets de catalogue, best-effort) |
| **Dépendances objet↔objet** | ✅ **graphe global (P0.2)** — object→table + object→object, impact analysis, Mermaid |
| **Applications consommatrices** | ✅ **corrélation DB↔apps (P0.3)** — `correlate_db_app.py` (db-introspection × data-access) : qui appelle quelle proc / touche quelle table, orphelins, drift |
| Schéma global (ERD) | ⚠️ via `reverse_synth` (ERD Mermaid) — alimenté **depuis le live** (C1) ; reste statique, pas d'exploration interactive (cf. DB7) |

**En une phrase** (révisé 2026-08-25) : le cœur (escalier + business-logic +
cahier des charges) est là et différenciant ; **(a)** l'introspection live du
graphe d'objets complet, **(b)** l'analyse du corps des vues/triggers et
**(c)** les graphes de dépendances objet↔objet et objet↔application sont
**livrés** (P0.1 / P0.2 / P0.3 / C1). Ce qui manque réellement, c'est
**(d)** un **rapport structurel visuel** de niveau SchemaSpy, **(e)** le lint /
diff de schéma en CI, **(f)** un serveur MCP — et surtout **(g) la validation
sur une vraie base**, qui n'a pas encore eu lieu. La roadmap §6 détaille.

---

## 1. Ce qui existe aujourd'hui (état précis, vérifié au code)

Pipeline `db-reverse` (SSoT : `reverse-proc-engineering.audit.md`) :

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
   gérant), **fonctionne déjà** sur les FEATs db-reverse.

Schéma structurel — **deux sources, un seul contrat** (`db-schema.json`) :
- reverse **applicatif** (un dépôt legacy est présent) : `db_schema_extractor.py`
  extrait tables/colonnes/FK/index + ORM depuis le **DDL statique `.sql`**
  (`completeness: "basic"`) ;
- reverse **base de données** (on n'a qu'une connection string) :
  `db_schema_live.py` lit la même chose depuis le **catalogue vivant**
  (`completeness: "live"`, C1 2026-08-25), plus les objets de catalogue sans
  corps (jobs, séquences, synonymes, linked servers, types).

`reverse_synth.py` rend un **ERD Mermaid** depuis ce schéma, quelle que soit la
source. Vues et triggers ne sont plus des « noms seuls » : leur corps passe par
l'escalier au même titre qu'une procédure.

---

## 2. Comparaison avec l'état de l'art

| Critère | **SDD_Pro db-reverse** | **SchemaSpy** | **SchemaCrawler** | **tbls** | **Cutter** |
|---|---|---|---|---|---|
| Domaine | DB → **spécifications métier** | DB → doc structurelle | DB → doc + lint + diff | DB → doc CI (markdown) | binaire → désassemblage |
| Tables/colonnes/FK/index | ✅ live (catalogue) | ✅ live (JDBC) | ✅ live | ✅ live | n/a |
| Vues (structure) | ✅ | ✅ | ✅ | ✅ | n/a |
| **Vues / triggers (corps + logique)** | ✅ **corps → US** | ❌ | ❌ | ❌ | n/a |
| **Procédures (logique métier)** | ✅ **corps → US** | ❌ | ❌ (métadonnées) | ❌ | n/a |
| Relations implicites (sans FK) | ❌ | ✅ (heuristique) | ✅ | partiel | n/a |
| ERD / diagrammes | ⚠️ Mermaid (synth, depuis le live) | ✅ **HTML interactif** | ✅ | ✅ (mermaid/PlantUML) | ✅ CFG/callgraph |
| Graphe de dépendances | ✅ objet↔table + objet↔objet + objet↔app | ✅ inter-tables | ✅ | ✅ | ✅ |
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
- ~~**DB1 — Couverture d'objets incomplète en live.**~~ ✅ **FERMÉ 2026-08-25
  (P0.1 + C1)** : les objets **porteurs de corps** (procédures, fonctions, vues,
  triggers, packages Oracle) passent tous par l'escalier — c'est là que vit la
  logique métier des vues (agrégation/présentation) et des triggers (intégrité,
  cascades, audit). Les objets **structurels et sans corps** sont lus dans le
  même passage : tables, colonnes, types, PK/FK, index, contraintes CHECK
  (`db_schema_live`), puis jobs, séquences, synonymes, linked servers et types
  utilisateur (`catalog_object_queries`). **Reste ouvert** : la lecture est
  best-effort par requête — un droit manquant (typiquement `msdb` pour les jobs
  SQL Agent) dégrade le rapport en avertissement au lieu de le faire échouer, et
  ce comportement n'a pas encore été observé sur une vraie base.
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
- ~~**DB4 — Clustering en modules par heuristique de nommage** (`usp_`,
  CamelCase).~~ ✅ **FERMÉ 2026-08-25** — la promotion en défaut annoncée ci-dessus
  a été faite, et l'heuristique fixe a été remplacée par une mesure :
  1. **profilage du corpus** (`learn_name_profile`) : la structure de nommage est
     *inférée* des noms réels (fréquence documentaire × concentration
     positionnelle) au lieu d'être déclarée. Les marqueurs de type/sous-système
     (`SP_`, `STP_`, `BI_`, `Prc`) et les verbes propres à la base sont
     découverts, dans n'importe quelle langue. En dessous de 8 objets, aucun
     profil n'est appris — et le rapport le dit, au lieu de prétendre avoir
     appris quelque chose.
  2. **rattachement des sous-objets** : `ClientAdresse` → module `Client` quand
     `Client` est lui-même un module. Préfixe uniquement, frontières de tokens,
     `Misc` exclu. L'US conserve le nom de **son** objet, donc deux US d'une même
     FEAT ne collisionnent pas (CLAUDE.md §1).
  3. **bascule automatique** : fragmentation (modules/objets) ≥ **0.50** ou un
     objet sur deux sans verbe lisible ⇒ regroupement par **cohésion du graphe**.
     La bascule n'est retenue que si elle regroupe réellement mieux ; sinon le
     nommage est conservé et marqué `degraded` — un aveu, pas un faux positif.
  4. **visible** : stratégie + fragmentation + sous-objets rattachés en ligne de
     chat, et dans `inventory.json._clusteringReport`.

  Overrides Tech Lead : `SDD_REVERSE_CLUSTER_COHESION=1` / `SDD_REVERSE_CLUSTER_NAMING=1`.
  Couverture : `tests/test_reverse_db_clustering.py`. **Reste ouvert** : les
  seuils (0.15 / 0.50) sont calibrés sur des corpus synthétiques ; ils devront
  être revus après le premier run sur une vraie base.
- ~~**DB5 — Rung 2 déterministe côté DB vs LLM côté code.**~~ ✅ **FERMÉ
  2026-08-26** : `reverse-sql-feat-composer` est désormais le **défaut pour les
  modules complexes** (au moins un objet routé `deep`, ou une règle transverse à
  plusieurs objets) ; le déterministe `build_proc_feats.py` reste le défaut pour
  le CRUD. Sa valeur ajoutée est explicite : harmoniser sur le glossaire de
  l'architecte le vocabulaire d'US écrites par des agents indépendants.
  `SDD_REVERSE_FEAT_LLM=1|0` force l'un ou l'autre partout. Historique de
  l'étape opt-in : nouvel agent `reverse-sql-feat-composer` (Opus, parité avec 3c
  `reverse-feat-composer`) qui synthétise la FEAT module depuis les US d'objets
  SQL (démotion plomberie, narratif transverse, même gate `validate_reverse_feat`).
  **Opt-in** `SDD_REVERSE_FEAT_LLM=1` ; défaut = déterministe `build_proc_feats.py`
  (0 token). Réservé aux modules à forte logique métier.
- ~~**DB6 — Multi-dialecte partiel.**~~ ✅ **LARGEMENT ADRESSÉ 2026-07-24** :
  les **4 moteurs principaux** sont couverts — SQL Server (live-validé, run réel
  2026-08-27), PostgreSQL + Oracle (PL/SQL + packages) + MySQL/MariaDB
  (scaffold-validés, runtime live pending). Reste DB2/SQLite en `_PLANNED`.
  **Caveat** : PostgreSQL, Oracle et MySQL doivent être validés en runtime sur
  une vraie base (driver + instance) avant usage prod — la forme des requêtes et
  le flux sont testés offline, pas le comportement live.
  > **M1, audit 2026-08-29** : PostgreSQL figurait ici comme « live-validé ».
  > Ce document déclare pourtant, §Réserve, qu'aucun run n'a jamais été fait
  > contre une vraie base. Les deux affirmations ne pouvaient pas être vraies
  > ensemble ; c'est la réserve qui l'était. Statut corrigé en
  > **scaffold-validated**.
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
3. ~~**Corrélation objets DB ↔ applications**~~ ✅ **LIVRÉ 2026-07-24 (P0.3)**,
   **câblée 2026-08-26** — `correlate_db_app.py` est appelé en fin de
   `/sdd-db-reverse-full` (STEP 7.ter) dès que `data-access.json` existe, avec
   `reverse_synth.py` pour l'ERD et la vue système. Les deux scripts existaient
   et n'étaient invoqués par aucune commande.

### P1 — Fiabilité & couverture
4. ~~**Parsing SQL plus robuste** — tokenizer conscient chaînes/commentaires~~
   ✅ **LIVRÉ 2026-07-24 (P1)** : masquage commentaires + littéraux de chaîne
   (`_blank_string_literals`), `tests/test_sql_body_analyzer_masking.py`. Reste :
   parseur SQL par dialecte (AST) pour les cas complexes (CTE/MERGE/alias).
5. ~~**Rung 2 LLM pour la FEAT DB** (DB5)~~ ✅ **LIVRÉ 2026-07-24 (opt-in)** :
   agent `reverse-sql-feat-composer` (`SDD_REVERSE_FEAT_LLM=1`). Reste : le
   promouvoir en défaut pour les modules complexes après validation terrain.
6. ~~**Dialecte Oracle** (DB6)~~ ✅ **LIVRÉ 2026-07-24** : packages PL/SQL
   (PACKAGE + PACKAGE BODY via DBMS_METADATA) introspectés. **Scaffold-validated**
   — runtime live encore à faire.
7. **Masquage secrets dans les corps SQL** (DB11).
8. ~~**Structure relationnelle live** (tables/colonnes/PK/FK/index/CHECK)~~
   ✅ **LIVRÉ 2026-08-25 (C1)** : `db_schema_live.py`, même contrat
   `db-schema.json`, snapshot `CREATE TABLE` lisible et jamais exécuté pour
   préserver l'evidence `file:line`. Ajoute jobs / séquences / synonymes /
   linked servers / types (best-effort par requête).

### P2 — Restitution & intégration (emprunts)
8. **Rapport structurel HTML + ERD interactif** (emprunt SchemaSpy) en complément
   du `.docx`.
9. **Lint + diff de schéma en CI** (emprunt SchemaCrawler/tbls) → garantit la
   cohérence doc↔base.
10. **Serveur MCP** exposant l'introspection (emprunt SchemaCrawler/ReVA).

> **Déjà livré (2026-07-24)** : la **documentation cahier des charges** demandée
> (« générer une doc de type cahier des charges dans le répertoire doc ») est
> opérationnelle via `/spec-book` — elle humanise les FEATs db-reverse
> (features, US, règles de gestion, scénarios) en `.docx` lisible par un
> fonctionnel. Étendre P0 (vues/triggers/graphe) l'enrichira automatiquement,
> puisque le cahier des charges se régénère depuis les FEATs.

---

## 7. Réponse directe à la demande

| Demande | État |
|---|---|
| Se connecter via connection string | ✅ `stack.md ## Active Database` + `db_introspect` (read-only) |
| Récupérer procs, fonctions | ✅ |
| Récupérer vues, triggers, tables, contraintes, index | ✅ **vues + triggers (corps analysé)** + **tables / colonnes / PK / FK / index / CHECK en live** (C1 2026-08-25) |
| Packages (Oracle PL/SQL) | ✅ **P0.1 (Oracle, scaffold)** — PACKAGE + PACKAGE BODY via DBMS_METADATA |
| Jobs, séquences, synonymes, linked servers | ✅ **live**, best-effort par requête (un droit refusé — `msdb` typiquement — dégrade en avertissement) |
| Schéma global (ERD) | ⚠️ Mermaid **depuis le live** — **P2.8** pour l'interactif |
| Reverse détaillé de chaque composant SQL | ✅ procs, fonctions, vues, triggers, packages Oracle |
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
