# Audit du module Reverse Engineering — SDD_Pro v7.0.0

> **Date** : 2026-07-24 · **Auteur** : audit IA (ingénierie IA + prompt
> engineering + reverse engineering) · **Périmètre** : les 11 agents reverse,
> les 18 commandes, la rule `reverse-engineering.md`, la couche déterministe
> (`sdd_reverse/` + `sdd_reverse_scripts/`, ~13 100 LOC + ~4 100 LOC de tests),
> le hook `preflight_reverse_gate.py`, et la doc maître.
> **Comparateurs externes** : Reversa (source→spec), ReVA / reverse-engineering-assistant
> (binaire, MCP), Cutter/rizin (binaire, GUI).
> **Méthode** : lecture fichier-par-fichier + agent-par-agent, 3 sous-audits
> parallèles (agents / commandes+rules+docs / scripts), croisés avec l'état de
> l'art externe.

---

## 0. Verdict exécutif

Le module reverse de SDD_Pro est **remarquablement bien gouverné** — au niveau
ou au-dessus de Reversa sur la discipline (taxonomie réciproque `[REVERSE_*]`,
isolation D4 stricte, escalier tracé, anti-hallucination systématique par
evidence `file:line`, sécurité DB read-only exemplaire, ~4 100 LOC de tests).

Sa qualité perçue comme « faible » ne vient **pas** de l'architecture mais de
**trois écarts de couverture et d'ergonomie** qui sautent aux yeux à l'usage :

1. **Profondeur .NET-centrée.** Le graphe métier (L0) n'existe que pour C#/VB.NET.
   Java, PHP, Delphi, VB6, Classic ASP, JS/jQuery sortent en confiance `medium`
   sans cartographie de leur couche service/repository → presque toutes leurs
   FEATs sont bloquées par la REVERSE-GATE.
2. **La boucle humaine ne se ferme jamais toute seule.** Un run « complet »
   `/sdd-reverse-full` **génère** `questions.md` mais ne **ré-ingère** jamais les
   réponses → il faut 2 invocations manuelles + une édition intermédiaire. Or,
   pour le legacy courant (medium), c'est le **seul** chemin vers `high`.
3. **Aucune restitution « humaine » du résultat.** Le module produit des FEATs
   techniques traçables, mais rien qui parle à un décideur non-IT — alors que la
   valeur d'un reverse pour un DSI/gérant, c'est justement *« qu'est-ce que ce
   vieux système fait, en français ? »*. Reversa a une équipe Documentation
   (mini-site HTML) ; SDD_Pro n'avait pas d'équivalent.

Le point (3) est **corrigé par ce même travail** (nouvelle commande `/spec-book`
+ agent `specbook-writer` + générateur `.docx`, cf. §8). Les points (1) et (2)
sont des chantiers priorisés en §7.

**En une phrase** : l'ossature (l'« escalier ») est excellente et correspond
déjà à la vision de l'utilisateur ; ce qui manque, c'est la **largeur**
(langages), la **fermeture de boucle** (humain) et la **restitution**
(cahier des charges) — pas une refonte.

---

## 1. Positionnement vs les outils cités

Point crucial : **deux des trois comparateurs ne jouent pas dans le même sport.**

| Outil | Domaine RE | Entrée | Sortie | Orchestration |
|---|---|---|---|---|
| **SDD_Pro reverse** | **source + BD** → spécification | code legacy, procédures stockées | FEAT/US/mockups/Gherkin **régénérables** par `/sdd-full` | escalier d'agents LLM + scripts déterministes |
| **Reversa** | **source** → spécification | codebase legacy | specs « contrats opérationnels », C4/ERD, ADR rétro, mini-site | 9 équipes d'agents, 5 phases, checkpoints |
| **ReVA** | **binaire** (Ghidra) | exécutables/firmware | compréhension assistée (renommage, types, algos) | serveur MCP, outils granulaires tool-driven |
| **Cutter** | **binaire** (rizin) | exécutables | désassemblage/décompilation, CFG, annotations | GUI + plugins, pas d'IA native |

**Conséquence méthodologique** : comparer SDD_Pro à ReVA/Cutter sur le *périmètre*
n'a pas de sens (binaire ≠ source). Ce qui est transférable de ReVA/Cutter, ce
sont des **principes d'ingénierie**, pas des fonctionnalités (cf. §6). Le vrai
pair-à-pair est **Reversa** — dont SDD_Pro a d'ailleurs déjà emprunté 3 concepts
(paradigm-advisor, parity-inspector, questions-loop, audit 2026-06-12).

---

## 2. Ce que SDD_Pro fait déjà très bien (forces confirmées)

- **L'escalier ascendant (3a analyse → 3b user stories → 3c FEAT)** est la pièce
  la mieux ingénierée. Altitude qui monte, **confidence min-monotone**
  `conf(3c) ≤ conf(3b) ≤ conf(3a)` **enforcée par un script déterministe**
  (`check_ladder_traceability.py`, pas seulement par le LLM). C'est *exactement*
  la vision « escalier » de l'utilisateur, déjà implémentée (ADR
  `governance-major-reverse-spec-ladder`).
- **Traçabilité transitive** `FEAT → US#AC → task T-N → evidence file:line`.
  Chaîne cassée ⇒ item rejeté (fail-safe, pas de faux positif).
- **Anti-hallucination systématique** : rien n'est écrit sans evidence sourcée ;
  « bias toward present » (on ne documente que ce qu'on voit).
- **Isolation D4** : `sdd_reverse/*` n'importe jamais le reste du framework
  (enforcé par `reverse_smoke.py`). Le module est un sous-système autonome.
- **Sécurité DB (db-reverse) exemplaire** : double barrière `readonly_guard`
  + `ApplicationIntent=ReadOnly`, validation au constructeur de dialecte, jamais
  d'exécution de procédure, mot de passe jamais loggé/persisté.
- **Tout-déterministe-quand-possible** : inventaire, crosscut, synthèse (C4/ERD),
  status = scripts 0 token. Le LLM n'intervient que là où il apporte du jugement.
- **Routage complexité** (Sonnet pour unité simple, Opus sinon) = économie réelle
  sur .NET (ADR `governance-reverse-complexity-ladder`).
- **Taxonomie `[REVERSE_*]` réciproque** : 36 classes, aucune sans émetteur
  (règle de réciprocité testée). Gouvernance rare.

---

## 3. Faiblesses classées par sévérité

Sévérité = impact sur la qualité perçue × fréquence d'occurrence en usage réel.

### 3.1 CRITIQUE (dégrade directement la qualité perçue)

| # | Problème | Localisation | Effet |
|---|---|---|---|
| C1 | **Graphe métier .NET-only.** L0 (`code_graph_builder.py`) et unités code L2 ne couvrent que C#/VB.NET. Java/PHP/Delphi/VB6/ASP/JS : détection + SQL inline + seeds UI seulement, **aucune cartographie service/repository**. | `sdd_reverse/code_graph_builder.py:54-58` ; rule §4 | Sur legacy non-.NET (le cas brownfield le plus courant), l'extraction est superficielle → FEATs pauvres. |
| C2 | **Caps de confiance `medium` pour le legacy courant** (php-procedural, vbnet, classic-asp, delphi, jquery, vb6). | `language_signatures.yml:76…` | Presque toutes les FEATs sortent `medium` ⇒ **bloquées** par REVERSE-GATE ⇒ passage forcé par la boucle humaine. |
| C3 | **La boucle humaine ne se ferme pas dans un run.** `/sdd-reverse-full` STEP 5 génère `questions.md` mais n'ingère jamais ; `--ingest` est manuel, hors run, et **seule** voie medium→high. | `sdd-reverse-full.md:135-143` ; `sdd-reverse-questions.md` | Un run « complet » laisse systématiquement le résultat bloqué + exige 2 invocations manuelles. Friction n°1. |
| C4 | **Parseurs UI manquants pour familles pourtant détectées** (Delphi `.dfm`, VB6 `.frm`) : reconnus comme famille UI mais tombent dans la branche HTML générique qui ne matche rien → **maquette vide, silencieusement**. | `ui_template_parser.py:53-55` | Promesse de récupération de maquettes non tenue, sans erreur. |
| C5 | **Comportement client (JS) perdu.** `/sdd-reverse-ui` interdit `<script>`/handlers ; jquery cappé medium. Aucune reconstruction de la logique front interactive. | `reverse-ui-extractor.md:63` | Les validations/interactions front legacy disparaissent du reverse. |

### 3.2 MAJEUR (dette structurelle / robustesse)

| # | Problème | Localisation | Effet |
|---|---|---|---|
| M1 | **Confusion terminologique `{Name}` / `{FeatName}` / `{Module}`** à travers tout l'escalier + loader. Fonctionne car les valeurs coïncident, mais piège de maintenance et de traçabilité. | 3a écrit `plans/{n}-{Name}.analysis.md`, 3b/3c lisent `{n}-{FeatName}` ; loader parle de `{Module}` non défini | Risque de drift silencieux dès qu'une valeur diverge. |
| M2 | **Garde-fous confidence dépendants de la seule discipline LLM.** La montée à `high` via `<!-- human-validated -->` (clarifier) et l'ordre « hash en dernier » (composer) sont load-bearing mais **non enforcés** par un script → contournables silencieusement. | `reverse-clarifier.md:79-82` ; `reverse-feat-composer.md:157` | Le cap monotone (invariant de sûreté) peut être franchi sans trace. |
| M3 | **100 % regex, zéro AST.** Aucun `ast`/tree-sitter/Roslyn. Atténué (masquage commentaires/strings, équilibrage de parenthèses) mais fragile : homonymes, macros, SQL/HTML généré au runtime passent au travers. | toute la couche `sdd_reverse/` | Faux positifs/négatifs d'extraction sur code non trivial. |
| M4 | **Curation DISCARD sans effet.** Le paradigm-advisor classe des unités DISCARD (code mort) mais `/sdd-reverse-full` reste **intégral par défaut** — le code mort est extrait quand même sauf `--units` manuel. | `sdd-reverse-paradigm.md:20-21,64-66` | Effort gaspillé sur du code voué à la poubelle. |
| M5 | **Parité (specs feature exécutables) OFF par défaut** (`--with-parity`), exclue de `--minimal`. C'est la **seule** preuve de non-régression comportementale. | `sdd-reverse-parity.md` | Une migration standard ne produit aucun oracle de parité. |
| M6 | **Asymétrie de rigueur des agents Opus.** `reverse-sql-analyst` et `reverse-ui-extractor` (tous deux Opus) n'ont ni routage complexité, ni écriture atomique, ni gate de validation déterministe — contrairement à 3a/3b/3c. | `reverse-sql-analyst.md` (99 l.) ; `reverse-ui-extractor.md` | Sur-coût Opus non challengé + sorties non validées structurellement. |
| M7 | **Crosscut trop étroit.** Ne couvre que Librairies + Base de données. Aucune FEAT transversale pour CI/CD, build, Dockerfile, jobs planifiés, variables d'environnement (hors connection strings), sécurité/auth transverse, i18n. Cap `_MAX_ITEMS=80`. | `crosscutting_feats.py` | Le « plan d'exécution » du legacy (runbook) n'est pas récupéré. |
| M8 | **Tests legacy et migration de données non exploités.** Les tests existants ne deviennent pas des oracles de parité ; aucun plan de migration de données (ETL, mapping legacy→cible). | (absence) | Deux angles morts opérationnels d'une vraie migration. |

### 3.3 MINEUR (doc / cohérence, corrigeables vite)

| # | Problème | Localisation |
|---|---|---|
| m1 | Numérotation de phase incohérente (paradigm `2.7` vs `2.4` ; questions `3.9` vs `5`). | frontmatters vs `sdd-reverse-full.md` |
| m2 | ADR complexity-ladder corrompu en fin de fichier (résidu `</content></invoke>`). | `ADR-…-complexity-ladder.md` |
| m3 | Référence morte à `reverse-functional-extractor` (décommissionné). | `reverse-inventory.md:56` |
| m4 | Numérotation anti-derive inversée (items 10 avant 9). | `reverse-feat-composer.md:205-206` |
| m5 | Bug de numérotation des STEPs (1,2,3,4,6,7,6 — pas de 5, 6 dupliqué). | `sdd-db-reverse-full.md:48-68` |
| m6 | Table des flags `--skip-*` trompeuse (colonne « Défaut » = « actif »). | `sdd-reverse-full.md:42-49` |
| m7 | Doc maître périmée : §6.1 décrit la REVERSE-GATE comme « opt-in non-enforced » alors que le hook `preflight_reverse_gate.py` l'enforce désormais ; en-tête « 4 agents » alors qu'il y en a 11. | `reverse-engineering-workflow.md` |
| m8 | Comptage d'agents incohérent dans CLAUDE.md §4 (« 11 » puis « 10 »). | `CLAUDE.md §4` |
| m9 | Détection binaire-only confiée au LLM sans script (contraste avec le reste). | `sdd-reverse-init.md` |
| m10 | Seuils/poids empiriques en dur partout (God-class 15/300, confiance 5.0/2.0, fenêtres 600/800 chars, EOL map ~7 packages). | multiple |

---

## 4. Comparaison agent-par-agent (synthèse)

| Agent | Lignes | Modèle | Routing | Validation déterministe | Verdict prompt-eng |
|---|---:|---|:---:|:---:|---|
| reverse-inventory | 92 | Sonnet | non | oui (script) | Bon — réf. morte m3 |
| reverse-tech-auditor | 223 | Sonnet | non | partiel | Dense ; anti-patterns sans evidence obligatoire |
| **reverse-tech-analyst (3a)** | 217 | Opus→Sonnet | oui | oui | **Le plus abouti** |
| reverse-us-writer (3b) | 145 | Sonnet | non | oui (ladder) | Bon ; « 1-5 US » non gardé |
| reverse-feat-composer (3c) | 209 | Opus→Sonnet | oui | oui (max 3) | Riche ; pont /sdd-full = maillon fragile (M2) |
| reverse-completeness-reviewer | 112 | Sonnet | non | oui | Bon ; juge sur du code que 3b/3c n'ont pas vu |
| reverse-ui-extractor | 180 | **Opus** | **non** | **non** | Modèle non justifié (M6), pas de gate |
| reverse-paradigm-advisor | 114 | Sonnet | non | non | Bon ; DISCARD sans effet (M4) |
| reverse-parity-inspector | 103 | Sonnet | non | oui | Propre ; OFF par défaut (M5) |
| reverse-clarifier | 123 | Sonnet | non | oui | Puissant ; exception `high` non gardée (M2) |
| reverse-sql-analyst | 99 | **Opus** | **non** | **non** | **Sous-spécifié** vs sa complexité (M6) |

**Lecture** : la colonne « Validation déterministe » et « Routing » sont les deux
marqueurs de maturité. L'escalier 3a/3b/3c coche tout ; les deux agents Opus
périphériques (UI, SQL) cochent le moins — c'est là que la rigueur doit remonter.

---

## 5. Confrontation à la vision de l'utilisateur

> Vision exprimée : *« un système d'escalier à partir d'un routeur, enrichi par
> les user stories, le plan d'exécution, on récupère les maquettes, et on
> réfléchit pour écrire des specs au format feature. »*

| Étage de la vision | État dans SDD_Pro | Écart |
|---|---|---|
| Routeur en bas de l'escalier | ✅ `complexity_router` / `code_unit_complexity` (route le modèle) | Le routeur route le **modèle**, pas encore un « scoring » de valeur métier par unité. Inopérant hors .NET (C1). |
| Escalier (analyse → US → FEAT) | ✅ 3a→3b→3c, confidence min-monotone déterministe | Aucun — c'est déjà là et solide. |
| Enrichi par les User Stories | ✅ barreau 3b | Nombre d'US non plafonné déterministiquement. |
| **Plan d'exécution** | ⚠️ partiel : crosscut = libs + DB seulement | **Manque** CI/CD, build, jobs, env, runbook (M7). |
| **Récupérer les maquettes** | ⚠️ `/sdd-reverse-ui` sémantique | **Vide** pour Delphi/VB6 (C4), pas de JS (C5), consommation non garantie par dev-frontend. |
| **Specs au format feature** | ✅ FEAT régénérable + pont `/sdd-full` + Gherkin | Gherkin OFF par défaut (M5). |

**Conclusion** : la vision est **implémentée à ~75 %**. Les 25 % manquants sont
exactement les faiblesses C4/C5/M5/M7 ci-dessus. Il ne faut donc **pas**
reconstruire un escalier — il faut **élargir et fermer** l'existant.

---

## 6. Emprunts recommandés aux outils externes

### Depuis **Reversa** (pair direct source→spec)
- **Équipe « Detective » (extraction de connaissance métier)** : Reversa a un
  agent dédié aux règles métier implicites, machines à états, permissions.
  SDD_Pro dérive les règles au fil de l'escalier mais n'a pas d'agent « métier »
  transversal. → *candidat : un barreau/agent d'extraction de state-machines &
  permissions au-dessus de 3a.*
- **Matrices de traçabilité bidirectionnelles** (spec→code **et** code→spec).
  SDD_Pro a le fil ascendant ; ajouter l'index descendant « ce fichier est
  couvert par quelle(s) FEAT(s) » aiderait à visualiser la couverture (rejoint
  completeness-reviewer).
- **Équipe Documentation (mini-site HTML)** : restitution lisible. → **adopté**
  ici sous forme de **cahier des charges `.docx`** (§8), plus adapté à un DSI/gérant.
- **Mode `expresso` (toutes les questions en une interview initiale)** : réduit
  la friction de la boucle humaine (C3). → *candidat pour clore la boucle en 1 run.*
- **Checkpoints `state.json` + reprise** : SDD_Pro s'appuie sur les artefacts
  disque (idempotence), pas de state central — acceptable, mais un index de
  progression par barreau/unité manque (`/sdd-reverse-status` ne le donne pas).

### Depuis **ReVA** (binaire, MCP tool-driven)
- **Outils granulaires + tolérance d'input + « output enrichi qui guide la suite »** :
  principe directement applicable aux scripts déterministes (retourner du
  contexte subsidiaire — cross-refs, namespaces — pour guider l'agent, réduire
  l'hallucination). SDD_Pro le fait déjà partiellement (evidence), à généraliser.
- **Fragmentation contextuelle anti « context rot »** : pertinent pour les
  god-units (déjà mitigé par le cap 40 Reads de 3a).
- **Transport MCP / mode headless** : SDD_Pro est déjà « headless-first ». Un
  serveur MCP exposant l'inventaire (`inventory.json`, `db-schema`) à d'autres
  clients serait un plus d'écosystème, non prioritaire.

### Depuis **Cutter/rizin** (binaire, GUI)
- **Graphes visuels (CFG/callgraph) + navigation** : SDD_Pro rend déjà du C4/ERD
  Mermaid (`reverse_synth.py`). → *étendre la synthèse avec un call-graph/graph de
  dépendances Mermaid par FEAT* renforcerait la lisibilité (angle mort actuel :
  le graphe deps existe en JSON mais n'est pas rendu visuellement par FEAT).
- **Annotations persistantes** : équivalent des `human-validated` markers — déjà
  présent, à sécuriser (M2).

---

## 7. Roadmap priorisée d'améliorations

### P0 — Débloque la qualité perçue (fort ROI, effort modéré)
1. **Fermer la boucle humaine en un run** (C3) : ajouter à `/sdd-reverse-full`
   un mode `--interactive` façon `expresso` qui, après STEP 5, propose l'ingest
   directement (ou une passe unique de questions en amont). Sinon, au minimum,
   documenter/automatiser l'enchaînement generate→(pause humaine)→ingest.
2. **Restitution humaine** (nouveau) : cahier des charges `.docx` — **livré**
   (§8). Le brancher en fin de `/sdd-reverse-full`.
3. **Corriger les faux-silences** (C4) : faire échouer explicitement
   (`[REVERSE_UI_PARSER_MISSING]`) quand une famille UI détectée (Delphi/VB6)
   n'a pas de parseur, au lieu de produire une maquette vide.
4. **Nettoyages doc** (m1-m10) : ~1 journée, supprime le « bruit » qui fait
   paraître le module bâclé (réf. morte, ADR corrompu, numérotations, §6.1 périmé).

### P1 — Élargit la couverture (effort élevé, valeur structurelle)
5. **Graphe métier multi-langage** (C1) : au minimum Java (imports + annotations
   Spring) et PHP (namespaces + use), pour sortir du « .NET-only ». C'est le
   chantier le plus lourd mais le plus impactant.
6. **Relever les caps de confiance** (C2) une fois (5) fait, langue par langue,
   avec preuves de fiabilité — pour désengorger la boucle humaine.
7. **Enforcer les garde-fous confidence** (M2) : script déterministe vérifiant
   que toute montée `high` porte un `human-validated`, et qu'aucun Edit ne suit
   la résolution de hash.
8. **Parité ON par défaut** dans les runs non-minimaux (M5).
9. **Rigueur des agents Opus périphériques** (M6) : routage complexité + écriture
   atomique + gate de validation pour `reverse-ui-extractor` et `reverse-sql-analyst`.

### P2 — Complète le « plan d'exécution » et la restitution
10. **Crosscut élargi** (M7) : FEATs transversales CI/CD, build, jobs, env, sécurité.
11. **Récupération JS client** (C5) : un barreau dédié à la logique front interactive.
12. **Rendu graphes par FEAT** (emprunt Cutter) + **matrice code→spec** (emprunt Reversa).
13. **Extraction métier dédiée** (state-machines, permissions — emprunt Reversa « Detective »).

---

## 8. Livrable de cet audit : le Cahier des charges `.docx`

Pour traiter immédiatement l'angle mort « restitution humaine » (point 2 de la
vision, absent du module), ce travail ajoute un générateur de **cahier des
charges fonctionnel** en Word, lisible par un gérant / décideur **non-IT**.

**Architecture (pattern SDD_Pro : LLM pour le jugement, script pour le rendu)** :

| Composant | Rôle | Fichier |
|---|---|---|
| `DocxBuilder` | Writer OOXML `.docx` **autonome stdlib** (respect `dependencies = []`), sortie byte-déterministe | `sdd_lib/docx_writer.py` |
| `generate_specbook.py` | Assembleur déterministe 0 token : glob des FEATs → `.docx` + miroir `.md` + manifeste ; mode humanisé (cache frais) OU brut (fallback) | `sdd_scripts/generate_specbook.py` |
| `specbook-writer` (agent) | Humanise **une** FEAT (forward OU reverse) en prose métier simple, cache par hash | `agents/specbook-writer.md` |
| `/spec-book` (commande) | Orchestre : détecte les FEATs modifiées (hash) → humanise l'incrément → réassemble | `commands/spec-book.md` |

**Propriétés clés** :
- **Toujours régénérable** : même sans l'étape LLM, le `.docx` est produit en
  mode « brut » (chapitre marqué *à humaniser*) — jamais cassé, jamais vide.
- **Incrémental / idempotent** : humanisation cachée par hash de FEAT ; un
  ré-appel sur projet inchangé ne spawn aucun agent (coût ~0). Répond à
  l'exigence *« à chaque nouvelle feature/analyse, mettre à jour le doc »*.
- **Forward ET reverse** : détecte l'origine reverse (REVERSE-GATE/confidence) et
  ajoute un encart « à valider » quand la confiance < high.
- **Zéro dépendance tierce** : pas de `python-docx`, conforme à la politique du
  framework. Testé (`tests/test_specbook.py` : OOXML valide, déterminisme,
  parsing forward/reverse, modes humanisé/brut/stale/no-feat — 36 tests verts).

**Sortie** : `workspace/docs/cahier-des-charges.docx` (+ `.md` de diff).

> Intégration : `/spec-book` est idempotent et destiné à être appelé en fin de
> `/sdd-full` et `/sdd-reverse-full` (cf. `commands/spec-book.md §Intégration`).

---

## 9. Annexe — Couverture des langages legacy (extrait)

| Techno | Détection | Graphe métier | SQL inline | Parsing UI | Verdict |
|---|---|:---:|:---:|:---:|---|
| C# .NET (WebForms/MVC/API) | high | ✅ | ✅ | ✅ | **Excellent** |
| VB.NET | medium | ✅ (line-based) | ✅ | ✅ | Bon |
| WPF/XAML | high | ✅ MVVM | ✅ | ✅ XAML→HTML | Bon |
| Java EE / Spring | high | ❌ | ✅ | ✅ JSP/JSF | Moyen |
| PHP (Laravel/Symfony/proc.) | ✅ | ❌ | ✅ | ✅ Blade/Twig | Moyen |
| Classic ASP | medium | ❌ | ✅ | partiel | Faible |
| Delphi (.pas/.dfm) | medium | ❌ | ✅ | ❌ (famille détectée, **pas de parseur**) | Faible |
| VB6 (.frm) | medium | ❌ | ✅ | ❌ (**pas de parseur**) | Faible |
| JS / jQuery | medium | ❌ | — | — | Faible |
| Python, Ruby, ColdFusion, COBOL, Oracle Forms, Go, Kotlin, Angular/React/Vue modernes | ❌ | — | — | — | **Non supporté** |

Dialectes db-reverse : **SQL Server** (T-SQL) + **PostgreSQL** (PL/pgSQL)
implémentés ; Oracle/MySQL/DB2 planifiés non implémentés.

---

*Fin de l'audit. Les recommandations P0-P2 sont des propositions ; leur mise en
œuvre relève d'une décision produit (Tech Lead / DSI).*
