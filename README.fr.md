# SDD_Pro — L'ingénierie logicielle agentique, industrialisée

**Le framework qui refuse de livrer du code que personne n'a validé.**

Développement piloté par la spécification (FEAT → User Stories → Code), **multi-harness**
(Claude Code, OpenAI Codex, Gemini CLI, Antigravity) — **v7.0.3-dev** (base v7.0.0 GA 2026-06-07).
Baseline LTS v6.10.x conservée jusqu'au 2026-12-31.
Cf. [VERSIONING](.sdd/docs/VERSIONING.md) · [CHANGELOG](.sdd/docs/CHANGELOG.md).

> 🌍 [English version](README.md) — 🇫🇷 cette page est la référence canonique.
> Documentation principale : [.claude/CLAUDE.md](.claude/CLAUDE.md)

---

## Le pitch en 30 secondes

Les assistants de code partent du code et essaient de remonter vers l'intention.
SDD_Pro impose la trajectoire inverse et la **verrouille par des portes déterministes** :

```
FEAT (spec métier versionnée)
  └─ User Stories (IDs stables, critères d'acceptation traçables)
       └─ Plans techniques (fichiers, couches, contrats preserves/adds)
            └─ Code (backend d'abord → API Gate → frontend)
                 └─ QA + 5 reviewers (code, sécurité, spec, archi, adversarial)
```

Ce que ça change concrètement :

| Sans SDD_Pro | Avec SDD_Pro |
|---|---|
| La spec vit dans le prompt, jamais relue | La spec est un fichier versionné avec le code |
| Le LLM « improvise » hors périmètre | `[DERIVE_VIOLATION]` → **STOP** bloquant |
| Le front appelle un endpoint qui n'existe pas | **API Gate** in-memory bloquant entre back et front |
| La couverture de tests est déclarative | `CoverageMin` déterministe → 🔴 bloquant |
| La facture LLM se découvre après coup | `MaxCostPerRun` (défaut 50 $) → arrêt net |
| Une base legacy reste une boîte noire | Reverse SGBD **en lecture seule** → FEATs lisibles |

**Le créneau** : SDD_Pro **industrialise la qualité** — l'équivalent d'un
*Sonar + Snyk + gouvernance ADR* appliqué à un pipeline multi-agent, **sur n'importe
quel harness LLM**.

---

## 🚀 Quickstart — nouveau projet

**Option recommandée : utiliser ce repo comme [GitHub Template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository).**
Cliquer sur **« Use this template »** → « Create a new repository » → cloner localement →
lancer le bootstrap interactif :

```bash
# macOS / Linux
python3 bootstrap.py

# Windows (PowerShell ou cmd)
python bootstrap.py

# Non-interactif (CI / scripté) — combo validée C1
python bootstrap.py --combo c1 --skip-install
```

Le bootstrap :
- demande le nom du projet + 3-4 questions (stack, base de données, authentification) ;
- génère `workspace/stack/stack.md` (55 clés Project Config, defaults sûrs) ;
- crée la structure `workspace/.sys/` complète ;
- installe les dépendances Python (`pip install -e .sdd/python[dev]`) ;
- lance un smoke check final.

Combos disponibles :

| Combo | Composition | Statut |
|---|---|:---:|
| **C1** | .NET Minimal API + React + shadcn + Azure AD + xUnit | 🟢 validated end-to-end *(recommandée)* |
| **C2** | Kotlin Spring Boot + React + shadcn + Azure AD + JUnit | 🟢 validated end-to-end |
| **C3** | Node Express + React + shadcn + auth-local | 🟢 bench-validated runtime |
| **C4** | Python FastAPI + React + shadcn + auth-local | 🟢 bench-validated runtime |
| **C5** | .NET Minimal API + Vue + Vuetify + Azure AD | 🟢 bench-validated runtime |
| `--combo custom` | composition manuelle (4 backends × 4 frontends × 3 design systems) | — |

**13 combos** portent un engagement SLA — source machine :
[.sdd/templates/combos.json](.sdd/templates/combos.json), détail
[validated-combos.md](.sdd/docs/validated-combos.md).

Mode CI (sans prompt) :
```bash
SDD_APP_NAME=MyApp SDD_COMBO=c1 python bootstrap.py --auto-init
```

---

## 🆚 Pourquoi SDD_Pro plutôt que BMAD / GSD / AgentOS / Superpowers ?

| Critère | SDD_Pro | BMAD | GSD | AgentOS | Superpowers |
|---|:---:|:---:|:---:|:---:|:---:|
| Multi-harness (Claude + Codex + Gemini + Antigravity) | ✅ **natif** | ❌ | ❌ | ❌ | ❌ |
| Agents spécialisés | **29** | ~6 | ~5 | 4 | 8 |
| Reverse engineering **SGBD** (procédures, fonctions, vues, triggers, jobs) | ✅ **natif** | ❌ | ❌ | ❌ | ❌ |
| Reverse engineering **code legacy** (legacy → FEAT) | ✅ **natif** | ❌ | ❌ | ❌ | ❌ |
| Reviewers post-code (5 angles, adversarial actif par défaut) | **5** ✅ | 1 | 1 | 1 | 2 |
| Anti-derive strict (matrice d'ownership + STOP bloquant) | ✅ | partiel | ❌ | partiel | partiel |
| Catalogues de dépendances machine-readable (`.libs.json` + CVE + LTS) | ✅ **30** | ❌ | ❌ | ❌ | ❌ |
| Taxonomie d'erreurs cross-agent (`[CLASS]`) | ✅ **193** | ❌ | ❌ | ❌ | ❌ |
| Invariants load-bearing déclarés **et testés** | ✅ **31** | ❌ | ❌ | ❌ | ❌ |
| Télémétrie SQLite + statusline IDE (coût, phase, tokens) | ✅ | ❌ | partiel | partiel | ❌ |
| Idempotence / reprise (checkpoint mode) | ✅ | ❌ | ❌ | partiel | ❌ |
| Scripts déterministes 0 token | **80 scripts** | ❌ | ❌ | partiel | partiel |
| Plugin marketplace (découverte IDE native) | ✅ `plugin.json` | ❌ | ❌ | ❌ | ❌ |

Voir le [cookbook 10 min](.sdd/docs/cookbook.md) pour démarrer, ou
l'[argumentaire CTO / DSI](.sdd/docs/WHY-SDD-PRO.md) pour arbitrer.

---

## Démarrage rapide (après bootstrap)

1. Éditer les secrets dans [workspace/stack/stack.md](workspace/stack/stack.md)
   (mot de passe base, client ID Azure AD, ports…) — **fichier gitignored**.
2. Dans le harness : `/feat-generate <Nom>` — répondre aux 3-6 questions d'élicitation.
3. *(Optionnel)* déposer des mockups HTML sous `workspace/ui/{n}-{m}-{Name}.html`.
4. `/sdd-full {n}` — pipeline complet A→Z.
5. `/sdd-status [{n}]` — état brut · `/sdd-help [{n}]` — guidance « what's next ».

Vous avez déjà un dépôt existant ? `/sdd-discover-stack` détecte le stack et produit
un `stack.md.candidate`.

---

## 🗄️ Reverse engineering SGBD — votre base de données redevient une spécification

> **La logique métier de votre entreprise dort dans votre base de données.**
> Des centaines de procédures stockées écrites sur quinze ans, par des développeurs
> qui sont partis. Aucune documentation. Personne n'ose y toucher.
> **SDD_Pro la lit — en lecture seule — et vous rend des spécifications.**

Une seule commande, `/sdd-db-reverse-full`, se connecte avec la chaîne déclarée dans
`stack.md ## Active Database`, inventorie **tout ce que la base sait faire**, et produit
des FEATs SDD_Pro standard — immédiatement consommables par `/sdd-full` pour régénérer
l'application par-dessus. Le patrimoine SQL cesse d'être une boîte noire : il devient
un backlog lisible, tracé et versionné.

### Ce que la machine remonte réellement

| Famille d'objets | Traitement |
|---|---|
| **Procédures stockées** | corps analysé → **1 User Story** |
| **Fonctions** (scalaires, inline, table) | corps analysé → **1 User Story** |
| **Vues** et **triggers** | corps analysé → **1 User Story** |
| **Packages Oracle** (spec + body) | corps analysé → **1 User Story** |
| **Tables, colonnes, types, PK/FK, index, contraintes `CHECK`** | introspection live → `db-schema.json` |
| **Jobs / scheduler, séquences, synonymes, linked servers, types utilisateur** | introspection live → `catalogObjects` |

> 💡 **Ce que les autres outils ratent.** Les contraintes `CHECK` et les **jobs
> planifiés** sont les deux plus gros gisements de règles métier *invisibles depuis
> le code applicatif* : un job porte du comportement nocturne (recalcul, purge,
> import) que rien, dans l'application, ne révèle. SDD_Pro les remonte au même titre
> qu'une procédure.

### Le modèle, en une ligne

**1 objet SQL = 1 User Story · 1 module métier = 1 FEAT.** Pas de fusion, pas
d'invention, pas de résumé qui écrase le détail.

```
stack.md (## Active Database)
   └─ Introspection READ-ONLY (0 token)  ─► corps SQL + db-schema.json + inventory.json
        └─ Phase 0 — Database Context (/sdd-db-context)
             ├─ 0.A déterministe (0 token) : FAITS — CRUD, graphe d'appels, vagues
             └─ 0.B reverse-db-architect  : HYPOTHÈSES — glossaire, sous-domaines, risques
                  └─ Vagues d'analyse : 4 analystes spécialisés (LLM, parallèle borné)
                       └─ Composition des FEATs (déterministe, ou LLM sur module complexe)
                            └─ REVERSE-GATE ─► /sdd-full
```

### Phase 0 — la base est comprise **avant** d'être découpée

C'est la nouveauté structurante (2026-08-26). Lire un corps de procédure isolément
produit une User Story **fausse mais crédible** dès qu'il y a composition : procédure
imbriquée, SQL dynamique, trigger en cascade. `/sdd-db-context` construit donc une
compréhension globale **une seule fois**, versionnée, partagée par tous les analystes :

- **Le contrat faits ≠ hypothèses.** Les *faits* (tables, clés, `CHECK`, matrice CRUD,
  graphe d'appels) viennent de scripts déterministes et peuvent devenir des critères
  d'acceptation. Les *hypothèses* (glossaire métier, sous-domaines, zones à risque)
  viennent de l'agent `reverse-db-architect` et **ne peuvent jamais** en devenir.
  La séparation est **structurelle** : l'architecte écrit un fichier distinct, qu'un
  script fusionne dans la seule branche `hypotheses`. Il ne peut pas écraser un fait,
  même en essayant.
- **Un cache qui périme honnêtement.** `contextVersion` est un sha256 des faits
  canoniques. Base inchangée → l'interprétation est réutilisée, la Phase 0.B n'est pas
  repayée. Base modifiée → l'interprétation périmée est **abandonnée** et le rapport le
  dit : une lecture obsolète d'une base qui a bougé est pire que pas de lecture.
- **Des packs de contexte calculés, pas devinés.** Aucun agent ne lit le contexte
  entier. Chaque objet reçoit un pack borné (défaut 14 000 octets) contenant son
  contrat, **uniquement** les tables qu'il touche, ce qu'il appelle (profondeur ≤ 2) et
  ses appelants. Si le budget force un retrait, **le pack le dit** — l'agent qui a reçu
  une vue tronquée baisse sa confiance en connaissance de cause.

### Les vagues : tout appelé est analysé avant son appelant

Le graphe d'appels est résolu, ses composantes fortement connexes condensées
(Tarjan — l'auto-appel et la récursion mutuelle existent réellement en T-SQL), puis trié
topologiquement. Propriété **garantie** : un objet appelé est analysé dans une vague
strictement antérieure à celle de son appelant. Un nom d'appelé absent ou ambigu reste
`unresolvedCallee` — jamais résolu au hasard, parce qu'un faux arc réordonne tout le plan.

Le débit ne baisse pas : le parallélisme borné (`MaxParallel`) joue **à l'intérieur**
d'une vague ; il n'y a qu'une barrière entre deux vagues, où l'orchestrateur — jamais un
agent — capitalise les résumés produits et régénère les packs suivants.

### Quatre spécialistes, pas un prompt géant

Le module reverse mobilise **16 agents** dédiés, dont **6 experts SQL**. Ce qui justifie
un agent distinct, c'est **l'angle** — jamais le type SQL en soi :

| Agent | Question qu'il pose à l'objet |
|---|---|
| **`reverse-sql-analyst`** *(procédures)* | quelle opération, quels effets sur les données, quelles préconditions ? |
| **`reverse-sql-function-analyst`** *(fonctions)* | quel calcul métier réutilisable, quels cas limites, quelle valeur par défaut ? |
| **`reverse-sql-view-analyst`** *(vues)* | quelle information exposée, et quels **filtres cachés** (`WHERE Actif = 1`) ? |
| **`reverse-sql-trigger-analyst`** *(triggers)* | quel événement, quelle règle, quelle cascade, quel rejet de transaction ? |
| **`reverse-db-architect`** *(Phase 0.B)* | quel est le vocabulaire métier de cette base, ses sous-domaines, ses zones à risque ? |
| **`reverse-sql-feat-composer`** *(synthèse module)* | quelle FEAT métier transverse, plomberie technique démotée ? |

Socle d'expertise partagé : [.sdd/rules/db-reverse-tsql.md](.sdd/rules/db-reverse-tsql.md)
— pièges `MERGE` / `OUTPUT` / `inserted` / `NULL`, atomicité, erreurs converties en
critères d'acceptation négatifs, équivalences T-SQL / PL-pgSQL / PL-SQL / MySQL.

Aucun agent n'en spawne un autre : c'est la commande qui orchestre — **la facture reste
prévisible**.

### 70 à 80 % de votre base ne coûte pas un seul token

Avant d'appeler le moindre LLM, un **routeur déterministe** grade chaque objet selon ce
que son corps *cache* — SQL dynamique, curseur, récursion, appelé non résolu,
orchestration, fan-in, volume — et retourne un **tier** (`none` / `fast` / `balanced` /
`deep`), jamais un nom de modèle : la résolution appartient au provider actif.

- **objet réellement simple** (CRUD sans branche, sans SQL dynamique, sans gestion
  d'erreur, **et sans appel**) → User Story générée **mécaniquement, à coût nul** ;
- **objet à logique métier** → et seulement là, un agent est réveillé.

S'y ajoutent un **cache par objet** (un corps inchangé n'est jamais ré-analysé : un
second run après interruption est quasi gratuit) et des garde-fous de périmètre
(`--schema`, `--include`, `--exclude`, `--limit`) qui **nomment toujours ce qu'ils ont
écarté** — jamais de troncature silencieuse.

> 🔎 **Le faux vert que nous avons fermé.** Jusqu'en août 2026, le routeur pesait les
> branches, le SQL dynamique, les erreurs, les curseurs, le volume — **jamais les
> appels**. Un orchestrateur de 38 lignes sans branche, qui déléguait toute sa règle
> métier à six procédures, était donc classé « simple » : User Story par template,
> confiance `high` faute de quoi que ce soit qui la dégrade, et **passage de la
> REVERSE-GATE sans revue humaine**. Déléguer n'est pas être simple. Désormais, tout
> appel force l'analyse LLM, et un appelé non résolu ou une récursion plafonnent la
> confiance à `medium` — qui remonte jusqu'à la FEAT et déclenche la revue.

### Le découpage en modules est mesuré, pas deviné

C'est la décision la plus structurante du reverse : elle fixe le nombre de FEATs.
SDD_Pro **profile vos conventions de nommage réelles** (préfixes `SP_`, `STP_`, `BI_`,
verbes propres à la maison) au lieu de plaquer une convention théorique. Si le nommage
est trop fragmenté pour être exploitable, le moteur **bascule automatiquement** sur la
cohésion du graphe de dépendances (tables partagées, appels croisés) — et ne retient la
bascule que si elle regroupe réellement mieux. La stratégie retenue, la fragmentation
mesurée et le profil appris sont tracés dans `inventory.json` et annoncés en clair :

```
[REVERSE] DB Facturation → 214 procédure(s) regroupée(s) en 31 module(s)/FEAT
          — regroupement par cohésion — nommage inexploitable (fragmentation 0.82). (Phase 1 OK)
```

### Lecture seule : une garantie d'architecture, pas une promesse

Votre DBA peut dormir. Le moteur n'émet **que** des `SELECT` de catalogue
(`sys.sql_modules`, `sys.procedures`, …) et `OBJECT_DEFINITION`, validés à l'exécution
par un `readonly_guard`. **Jamais** de `DROP` / `DELETE` / `TRUNCATE` / `ALTER` /
`INSERT` / `UPDATE` / `MERGE`, **jamais** d'exécution de procédure — l'interdit est porté
par la classe bloquante `[DB_STRUCTURE_CHANGE_FORBIDDEN]` et l'invariant
`reverse-db-readonly`. Le mot de passe reste en RAM : **jamais loggé, jamais persisté**
dans les artefacts produits. Défense en profondeur recommandée : un login dédié
`GRANT VIEW DEFINITION` + `db_datareader`.

### Rien n'est livré sans être qualifié

- **Traçabilité descendante** : chaque item de FEAT remonte à un critère d'US, qui
  remonte à une ligne de snapshot SQL. Les `evidence:` sont **résolues sur disque** — un
  pointeur mort est un gap, pas un feu vert.
- **Gate de consommation** : une FEAT dont la confiance n'est pas `high` **ne passe pas**
  dans `/sdd-full` (exit 1). Du SQL dynamique ou chiffré impose une revue humaine — le
  forçage existe (`--allow-reverse-low`) mais il est explicite et tracé.
- **Votre travail n'est jamais écrasé** : chaque FEAT porte l'empreinte de son contenu
  généré. Si vous l'avez éditée, un re-run la **préserve** et vous le dit.
- **Idempotence** : re-lancer réutilise les identifiants déjà alloués — pas d'orphelin,
  pas de doublon.

### Moteurs supportés

| Moteur | Statut |
|---|---|
| **SQL Server**, **PostgreSQL** | 🟢 live-validés |
| **Oracle**, **MySQL / MariaDB** | 🟡 scaffold-validés — requêtes read-only et flux hors ligne testés, runtime live à valider sur une base de test avant production |
| DB2, SQLite | reconnus, refusés avec un message explicite |

> ⚠️ **Réserve honnête** : la Phase 0 et l'ordonnancement par vagues sont validés **hors
> ligne** (catalogues synthétiques, tri topologique vérifié contre une référence par
> force brute sur 300 graphes aléatoires). Les seuils — profondeur de pack 2, budget
> 14 000 octets, fragmentation 0.50 — sont calibrés sur corpus synthétiques et seront
> revus après le premier run contre une base réelle de production.

### Démarrer

```bash
# 1. Driver lecture seule (une fois)
pip install -e ".sdd/python[reverse-db]"     # + ODBC Driver 18 pour SQL Server

# 2. Renseigner stack.md ## Active Database (DB_HOST / DB_NAME / DB_USER / DB_PASSWORD,
#    valeurs en clair ou placeholders ${VAR} résolus depuis un .env)
```

```text
/sdd-db-context                               # Phase 0 — comprendre la base (obligatoire)
/sdd-db-context --no-architect                # faits seuls, 0 token
/sdd-db-reverse-full                          # toute la base
/sdd-db-reverse-full --schema dbo --limit 50  # périmètre borné (recommandé au 1er run)
/sdd-db-reverse dbo.usp_Contact_Insert        # un seul objet, pour évaluer sans engager
```

**Essayez sur un seul module.** Vous obtiendrez une FEAT lisible par un PO, sourcée
ligne à ligne, sur du code que plus personne ne comprenait ce matin.

Détail complet : [reverse-engineering-workflow.md](.sdd/docs/reverse-engineering-workflow.md) ·
[reverse-db-audit-2026-07.md](.sdd/docs/reverse-db-audit-2026-07.md) ·
[rules/reverse-engineering.md](.sdd/rules/reverse-engineering.md)

---

## 🧬 Reverse engineering de code legacy — l'application aussi

Le même module remonte un **code source** legacy (WebForms, PHP, Delphi, monolithes…)
vers des FEATs, via un « escalier » à trois barreaux qui refuse de sauter d'altitude :

```
/sdd-reverse-full            # orchestrateur complet (init → inventaire → audit → escalier → UI)
  ├─ 3a  analyse technique fidèle   (reverse-tech-analyst)   — photo du code, evidence fichier:ligne
  ├─ 3b  remontée en User Stories   (reverse-us-writer)      — altitude métier, mais traçable
  └─ 3c  composition de la FEAT     (reverse-feat-composer)  — plomberie démotée
```

Trois phases complètent le tableau : **gap de paradigme** (votre legacy est
event-driven, votre cible est une SPA unidirectionnelle — la décision est rendue
consciente), **specs de parité** Gherkin (l'équivalence de comportement legacy ↔ régénéré
devient exécutable), et **boucle de questions** au Tech Lead (aucune réponse n'est jamais
inventée). Détail : [reverse-engineering-workflow.md](.sdd/docs/reverse-engineering-workflow.md).

---

## 📊 Console web — cockpit de validation

Une console web React + Fastify centralise toute la télémétrie du projet (QA, sécurité,
coverage, runs, gates) en lisant la base SQLite `workspace/db/console.db`. Aucun fichier
`.json` ni `.jsonl` de stats ne subsiste sur le disque — **la base est la source de vérité
unique**.

> ℹ️ `workspace/` est **gitignored** (il contient vos secrets et votre code généré) :
> la console est fournie par la distribution interne, pas par le clone du template
> GitHub. Si `workspace/console/package.json` est présent, le bootstrap propose
> `npm install`.

```bash
cd workspace/console
npm install        # première fois uniquement (Fastify + SDK Anthropic)
npm start          # démarre sur http://127.0.0.1:4000
```

Pré-requis : Node.js ≥ 20 et Python ≥ 3.8 sur le PATH (utilisé pour requêter
`console.db` via les helpers `sdd_lib`).

### Deux pages principales

| Page | Fonction |
|---|---|
| **Dashboard** *(défaut)* | KPI cards (FEATs, Tests API, Sécurité, Quality), grille des statuts par FEAT, audit qualité style SonarQube (Vulnerabilities / Code Smells / Coverage avec ratings A→E), 4 charts SVG natifs, sparklines, thème dark/light persisté. |
| **Features** | 3 vues : **PO** (FEAT → US), **technique** (FEAT → US → plans back/front), **UX** (carrousel des mockups HTML). Bouton **Rafraîchir** qui re-scanne le disque. |

> ℹ️ **Doc framework retirée de la console (2026-06-06)** — la console reste dédiée aux
> statistiques des projets matérialisés. La documentation SDD_Pro vit dans
> [.sdd/docs/](.sdd/docs/).

### Points forts

- 🎨 **Thème light / dark** avec toggle, persisté en localStorage, suit
  `prefers-color-scheme` au premier chargement. Logos adaptatifs.
- 📊 **Charts SVG natifs** (donut, bar stacks, sparklines, gradient progress bars),
  theme-aware — aucune dépendance de charting.
- 🛡 **Audit qualité style SonarQube** : 1 ligne par FEAT avec ratings A→E. Les cartes
  s'affichent **uniquement** si les données existent en base (pas de placeholder).
- 🔍 **Drill-down** : un clic déplie 3 tables (vulnérabilités critical/serious, code
  smells, coverage gaps) avec fichier:ligne, OWASP/CWE, sévérités colorées.
- 🛡 **Gates manuels** : les phases `afterUS / afterReadiness / afterPlan / afterCode`
  posées par `/sdd-full --manual-gates` sont résolues depuis la console, avec écriture
  atomique protégée par un verrou cross-language Python ↔ Node.
- 🤖 **Reformulation IA** (opt-in) : bouton « Reformuler avec IA » sur les FEAT/US/Plans.
- 📡 **Live updates** : SSE (`/api/events`) pousse les changements disque et les
  modifications de statut — l'arbre se met à jour sans rechargement.

### API HTTP exposée

| Endpoint | Description |
|---|---|
| `GET /api/tree` | Arbre FEATs → US → plans + état mergé |
| `GET /api/dashboard` | Vue agrégée toutes FEATs (5 KPIs + 1 ligne par FEAT) |
| `GET /api/feat/:n` | Détail d'une FEAT (coverage, quality, security, api-tests) |
| `GET /api/feat/:n/details` | Issues Sonar (vulns + smells + coverage gaps) |
| `GET /api/audit` | Agrégat tokens / contexte par agent |
| `GET /api/state` | Dernier run + 30 derniers events |
| `GET /api/gates?feat=N` | Historique des gates pour 1 FEAT |
| `GET /api/file?path=…` | Lecture brute d'un fichier Markdown du workspace |
| `POST /api/validate` | Enregistre la décision PO / Tech Lead sur une US |
| `POST /api/gate-decide` | Résout un gate `afterUS / afterReadiness / …` |
| `GET /api/events` | Server-Sent Events (broadcast disque + gates) |
| `GET /ui/*` | Sert `workspace/ui/` (mockups HTML avec leur CSS relatif) |

---

## 🔍 Ce qui est vérifiable (et comment le vérifier)

SDD_Pro se vend sur des chiffres qui se recomptent. Tous ceux-ci sont dérivés du dépôt,
pas d'un argumentaire :

| Élément | Compte | Le recompter |
|---|---:|---|
| Agents (13 forward + 16 reverse) | **29** | `ls .sdd/agents/ \| wc -l` |
| Commandes (13 user-facing + 9 internes + 19 reverse) | **41** | `ls .sdd/commands/ \| wc -l` |
| Règles opérationnelles | **12** | `ls .sdd/rules/` |
| Skills auto-déclenchées | **13** | `ls .sdd/skills/` |
| Stacks (28 🟢 + 8 🟡) | **36** | `python .sdd/python/sdd_admin/framework_smoke.py` |
| Catalogues de dépendances `.libs.json` | **30** | `find .sdd/stacks -name "*.libs.json" \| wc -l` |
| Combos sous engagement SLA | **13** | [.sdd/templates/combos.json](.sdd/templates/combos.json) |
| Classes d'erreur `[CLASS]` (16 familles) | **193** | [error-classification.md](.sdd/rules/error-classification.md) |
| Clés Project Config | **55** | [.sdd/config.base.yml](.sdd/config.base.yml) |
| Invariants load-bearing (14 forward + 17 reverse) | **31** | `INVARIANTS.yml` + `INVARIANTS.reverse.yml` |
| Scripts déterministes (0 token) | **80** | `sdd_scripts/` + `sdd_reverse_scripts/` |
| Hooks de protection câblés | **20** | `ls .sdd/python/sdd_hooks/` |
| Tests Python | **2 542** *(175 fichiers)* | `python -m pytest .sdd/python/tests/ -q` |
| Providers LLM supportés | **4** | `ls .sdd/providers/` |

```bash
# Vérification complète du framework (gates de cohérence inclus)
python .sdd/python/sdd_admin/framework_smoke.py

# Suite de tests
python -m pytest .sdd/python/tests/ -q
```

> Le manifeste [INVARIANTS.yml](.sdd/INVARIANTS.yml) est l'anti-rot du framework :
> chaque contrat porteur (two-stage gate, file ownership, cost cap, TDD test-first…)
> pointe vers son *enforcer* sur disque, et un test échoue si l'enforcer disparaît sans
> que le manifeste soit mis à jour.

---

## 🏗 L'architecture en un paragraphe

SDD_Pro orchestre **29 agents** — 13 sur le pipeline forward (PO, arch, dev-backend,
dev-frontend, QA, 5 reviewers, élicitor, constitutioner, specbook-writer) et 16 sur le
module reverse (code legacy et base de données) — autour d'une **matrice d'ownership de
fichiers stricte**, d'un **Project Config en couches** (55 clés, validé par JSON-schema),
d'une **couche d'outillage Python déterministe** (~58 KLOC, 2 542 tests) et d'un **cap de
coût dur** (50 $ par run par défaut). Le framework est **source-first** : chaque décision
vit dans un fichier `.md` (FEATs, US, plans, ADRs) versionné avec le code — aucun état
caché dans le contexte du LLM. Le pipeline est **backend-first et gated**
(dev-backend toutes US → API Gate → dev-frontend toutes US) pour éliminer le drift
silencieux de contrat entre le front et le back. Enfin, il est **harness-agnostique** :
la couche source `.sdd/` est compilée en façades par harness — même logique de pipeline
sous Claude Code, Codex, Gemini CLI ou Antigravity.

---

## 🗺️ Schémas visuels

Trois schémas, un par pipeline — chaque agent, chaque gate, chaque embranchement
parallèle dessiné tel qu'il tourne réellement.

### A — Pipeline forward
![Schéma du pipeline forward — de la FEAT au code livré](https://i.imgur.com/UkbM1fw.jpeg)

FEAT → User Stories → backend (parallèle par User Story, gaté par un API Gate en
mémoire) → frontend (parallèle) → QA → la revue à deux étages (spec-compliance seule
d'abord, puis code / sécurité / architecture en parallèle) → une passe adversariale →
un verdict unique vert / jaune / rouge.

### B — Reverse engineering : code legacy
![Schéma du reverse engineering — du code legacy à la FEAT](https://i.imgur.com/3pzuVfD.jpeg)

Inventaire → audit technique et analyse de gap de paradigme → l'escalier à trois
barreaux (analyse technique fidèle → User Stories → composition de la FEAT, la
confiance ne remonte jamais en grimpant) → FEATs transversales obligatoires → revue de
complétude → mockups UI → boucle de validation humaine pour ce qui reste ouvert.

### C — Reverse engineering : base de données
![Schéma du reverse engineering — de la base de données à la FEAT](https://i.imgur.com/tgk0721.jpeg)

Database Context (faits déterministes, puis hypothèses de l'architecte par-dessus) →
dispatch par vagues de dépendance — un objet SQL n'est analysé qu'une fois tout ce
qu'il appelle déjà analysé — vers quatre analystes SQL spécialisés → composition de la
FEAT → un double REVERSE-GATE avant toute entrée dans `/sdd-full`.

---

## 📚 Documentation

### Pour les utilisateurs

| Doc | Objet |
|---|---|
| [.claude/CLAUDE.md](.claude/CLAUDE.md) | Entry-point slim (~150 lignes, index vers le détail) |
| [.sdd/docs/getting-started.md](.sdd/docs/getting-started.md) | Tutoriel premiers pas (30 min) |
| [.sdd/docs/cookbook.md](.sdd/docs/cookbook.md) | Recettes concrètes (10 min) |
| [.sdd/docs/quickstart.md](.sdd/docs/quickstart.md) | Démarrage pas à pas + brownfield |
| [.sdd/docs/glossary.md](.sdd/docs/glossary.md) | Vocabulaire du framework |
| [.sdd/docs/commands-reference.md](.sdd/docs/commands-reference.md) | Fiches des commandes (args / flags / sorties) |
| [.sdd/docs/agents-reference.md](.sdd/docs/agents-reference.md) | Fiches des agents (rôle / modèle / I-O / verdicts) |
| [.sdd/docs/configuration-reference.md](.sdd/docs/configuration-reference.md) | Les clés de Project Config |
| [.sdd/docs/troubleshooting.md](.sdd/docs/troubleshooting.md) | Erreurs courantes + récupération |

### Pour décider (CTO / DSI)

| Doc | Objet |
|---|---|
| [.sdd/docs/WHY-SDD-PRO.md](.sdd/docs/WHY-SDD-PRO.md) | Argumentaire et comparatif marché |
| [.sdd/docs/SLA.md](.sdd/docs/SLA.md) | Engagements de service |
| [.sdd/docs/COMPLIANCE.md](.sdd/docs/COMPLIANCE.md) | Conformité et traitement des données |
| [.sdd/docs/KNOWN-LIMITATIONS.md](.sdd/docs/KNOWN-LIMITATIONS.md) | Ce que SDD_Pro ne fait **pas** |
| [.sdd/docs/validated-combos.md](.sdd/docs/validated-combos.md) | Matrice des combinaisons validées |
| [.sdd/docs/poc-roi-methodology.md](.sdd/docs/poc-roi-methodology.md) | Comment valider un nouveau stack |

### Pour contribuer au framework

| Doc | Objet |
|---|---|
| [.sdd/docs/architecture.md](.sdd/docs/architecture.md) | Composants, agents, stacks |
| [.sdd/docs/workflow.md](.sdd/docs/workflow.md) | Les phases du pipeline |
| [.sdd/docs/conventions.md](.sdd/docs/conventions.md) | Anti-derive, idempotence, plans |
| [.sdd/loader.yml](.sdd/loader.yml) | Manifeste reads/writes par agent (forward) |
| [.sdd/loader.reverse.yml](.sdd/loader.reverse.yml) | Manifeste du module reverse |
| [.sdd/rules/](.sdd/rules/) | Les 12 règles opérationnelles |
| [.sdd/docs/WORKING-AGREEMENT.md](.sdd/docs/WORKING-AGREEMENT.md) | Accord de travail |
| [.sdd/docs/adrs/](.sdd/docs/adrs/) | Architecture Decision Records |

Hub de navigation : [.sdd/docs/README.md](.sdd/docs/README.md).

---

## 🧱 Stack technique

Framework écrit en **Python** (stdlib pure pour le moteur, pytest pour les tests).
**Console web** : Node.js ≥ 20 (Fastify 5 + React 18). **SQLite** (mode WAL) pour la
télémétrie centralisée (`workspace/db/console.db`).

Aucun runtime applicatif n'est imposé au code généré — SDD_Pro produit du code dans le
stack du projet cible.

**Catalogue des stacks** — terminologie stricte, source de vérité = entête `Validation:`
du fichier `.md` :

| Statut | Définition | Compte |
|:---:|---|:---:|
| 🟢 | `validated` (combo validée bout-en-bout), `bench-validated` (runtime mesuré) ou `scaffold-validated` | **28** |
| 🟡 | `experimental` ou `POC-only` — chargeable, mais **jamais vendu en offre standalone** | **8** |

**Total : 36 stacks** — Backend (4), Frontend (4), Design systems (3), QA (9), Auth (2),
Patterns d'architecture (3), Fullstack (7), Mobile (3). Détail :
[validated-combos.md](.sdd/docs/validated-combos.md).

> ⚠️ Hors des combos listés dans [combos.json](.sdd/templates/combos.json), une
> composition multi-stacks n'a pas été validée par un PoC complet : le pipeline peut
> échouer en runtime de manière non triviale. Le hook `preflight_stack_combo` le signale
> — le bypass (`SDD_ALLOW_UNTESTED_COMBO=1`) existe, mais il est tracé.

---

## 📄 Licence & auteur

Conçu et maintenu par **SDD-Pro maintainer** · 2026 — voir [LICENSE](LICENSE).
