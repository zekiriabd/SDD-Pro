# SDD_Pro — Validated stack combos (référence canonique)

> Document chargé **à la demande** (`Read @.sdd/docs/validated-combos.md`).
> Crée pour résoudre la critique M3 (audit v7.0.0) :
> *« 16 stacks → ~120 combinaisons possibles, 2 validées bout-en-bout ;
> le risque que le pipeline casse en runtime sur un combo non-PoC est
> explicitement reconnu. Promesse multi-stacks largement théorique. »*
>
> **Objectif** : avant tout `/sdd-full {n}`, savoir en **10 secondes** si
> le combo actif est `validated`, `experimental` ou `untested` — et
> ce que cela implique.

---

## 0. Génération de modèles et historique du catalogue

### 0.1 ⚠️ Badges obtenus sur la génération 4.x — non re-benchés en 5.5

Tous les badges `validated` (C1, C2) et `bench-validated runtime` (C3-C13, bench
2026-06-05) ont été obtenus avec les modèles de **génération 4.x** (tier `deep` =
Opus 4.7 / 4.8, tier `balanced` = Sonnet 4.6). Le 2026-11-07 la façade est passée
à la génération **5.5** (`deep` = `claude-opus-5-5`, `balanced` = `claude-sonnet-5-5`,
`fast` = `claude-haiku-5-5`) et un niveau `effort:` par agent a été introduit
(`medium` pour les agents hors dev-*/arch). **Aucun combo n'a été re-joué sur
cette configuration.** Les badges attestent que les *patterns et librairies* du
combo compilent et servent les ACs ; ils ne garantissent pas que le pipeline
`/sdd-full` produise le même code avec un autre modèle ou un autre effort. Jusqu'à
un nouveau run C1 bout-en-bout, traiter tout combo comme « validé en 4.x ».

### 0.2 Historique du catalogue (déplacé de `CLAUDE.md §6` le 2026-11-07)

Narration retirée du fichier-mémoire (chargé par chaque sous-agent, qui n'en a
aucun usage) et conservée ici à l'identique :

> **Recount 2026-09-02** (quatre batches : `mobiles/` +4 stacks +2 QA,
> `backend/` +3 stacks +1 QA, `fullstack/` +3 stacks, **`desktop/` +7 stacks —
> nouvelle catégorie** ; historique : ajout `mobiles/delphi-fmx`
> 2026-06-21 ; ajout `fullstack/aspnet-mvc-razor` 2026-06-10 ; downgrade
> `mobiles/kotlin-android` 🟢→🟡, audit CTO 2026-06-07) :
> **28 🟢 (validated/bench-validated) + 28 🟡 = 56 total**.
> Validation auto : `python .sdd/python/sdd_admin/framework_smoke.py`, check
> **`stack-md-headers`** (nom corrigé audit 2026-08-29 — il n'existe pas de
> check `stacks-count`). ⚠️ Ce check émet **WARN, pas FAIL**, sur un drift de
> compte : c'est un signal consultatif, pas une barrière dure.

**🟡 (28)** : 26 experimental (`archi/ddd`, `archi/microservice`, `qa/mutation-testing` (opt-in), `qa/playwright` (opt-in), `fullstack/aspnet-mvc-razor`, `mobiles/delphi-fmx`, + les 6 ajouts du batch mobiles 2026-09-02 : `mobiles/flutter`, `mobiles/kotlin-multiplatform`, `mobiles/swiftui`, `mobiles/ionic-capacitor`, `qa/flutter-test`, `qa/swift-testing`, + les 4 ajouts du batch backend 2026-09-02 : `backend/django`, `backend/nestjs`, `backend/laravel`, `qa/php-pest`, + les 3 ajouts du batch fullstack 2026-09-02 : `fullstack/laravel-blade`, `fullstack/symfony-twig`, `fullstack/django-templates`, + les 7 stacks de la nouvelle catégorie `desktop/` : `delphi-vcl`, `wpf`, `qt-cpp`, `electron`, `winforms`, `javafx`, `pyside`) + 1 POC-only (`fullstack/node-react` — console SDD interne, non destiné prod externe) + 1 scaffold-validated (`mobiles/kotlin-android` — APK runtime pending, SDK absent au bench).

> **Batch mobiles 2026-09-02** — le catalogue `mobiles/` passe de 4 à 8 stacks et couvre désormais le top marché : `flutter`, `react-native` (Expo), `kotlin-multiplatform`, `swiftui`, `kotlin-android`, `maui`, `ionic-capacitor`, `delphi-fmx`. Les 4 **nouveaux** sont 🟡 par construction : chaque version de leur `.libs.json` est résolue contre le registre amont (pub.dev, npm, `maven-metadata.xml`, GitHub Releases) et les contraintes inter-paquets sont vérifiées, mais **aucun build runtime n'a été exécuté**. Les 4 **existants** ont été audités au même passage — 12 défauts bloquants corrigés, dont 4 références de paquet ou de version **inexistantes au registre** (`@azure/msal-react-native`, `Plugin.MauiCertPinning`, `Plugin.Fingerprint 3.0.0`, `Plugin.Maui.AppRating 2.0.0`) qui faisaient échouer l'install de leur capability. Détail par stack : §2.3 de chaque `.md`.

> **Batch backend 2026-09-02** — `backend/` passe de 4 à 7 stacks et couvre le top marché : `dotnet-minimalapi`, `node-express`, `kotlin-spring-boot`, `python-fastapi`, `django`, `nestjs`, `laravel`. Les 4 existants ont été rebasés sur les registres amont (leurs catalogs étaient figés en mai-juin 2026) et **3 défauts de cohérence** corrigés : (1) `dotnet-minimalapi` faisait cohabiter EF Core **9** avec des paquets ASP.NET **10** sur un TFM `net10.0` — le pin en 9.x était justifié par « Npgsql.EF 10.x est preview-only », cause disparue ; EF passe en 10.0.11, **sauf pour `mysql`/`mariadb`** où Pomelo n'a aucune 10.x et impose de rester en 9.0.4 ; (2) `node-express` pinnait `@types/express` **5.x** avec `express` **4.x** — le compilateur validait le code contre un autre runtime ; (3) `qa/node-vitest` pinnait `@types/supertest` **6.x** avec `supertest` **7.x**, même classe de défaut. **Aucune montée en majeure** sur les stacks 🟢/bench-validated (Spring Boot reste en 3.5.x face à la 4.1.1, Express en 4.x face à la 5.2.1) : elle invaliderait la validation runtime qui porte leur badge, et ne peut pas être re-jouée ici. Détail et justification : §2.3 de chaque `.md`.

> **Batch fullstack 2026-09-02** — `fullstack/` passe de 7 à 10 stacks et couvre le top marché SSR : `laravel-blade`, `aspnet-mvc-razor`, `symfony-twig`, `next`, `nuxt`, `blazor-server`, `django-templates` (+ `angular-universal`, `kotlin-mustache`, `node-react`). **Le défaut le plus grave de tout l'audit a été trouvé ici** : `blazor-server` **et** `aspnet-mvc-razor` pinnaient `ef-core` en **10.0.6** avec `npgsql-ef` en **9.0.4** — exactement la combinaison du post-mortem DemoApp 2026-05-22 (NU1608 → `MissingMethodException` au premier accès `DbSet`). Le correctif avait été appliqué à `backend/dotnet-minimalapi` le 2026-06-07 et **jamais propagé** : la même faille latente vivait dans deux autres stacks. Corrigé (EF 10.0.11 + Npgsql.EF 10.0.3, désormais stable), avec la contrainte résiduelle Pomelo/MySQL documentée. Autre phantom fermé : `FluentValidation.AspNetCore` **11.10.0** n'existe pas (le paquet compagnon s'arrête à 11.3.1 — la version avait été recopiée depuis le paquet `FluentValidation`). Les **deux WARN `PRERELEASE`** du catalogue sont également fermés : `next-auth` 5.0.0-beta.25 → **4.24.15** (le dist-tag `latest` pointe sur la 4, la ligne 5 est encore en beta) et `nuxt-ui` 3.0.0-alpha.10 → **4.11.0** (désormais stable). `validate_libs_catalog.py` ne remonte plus aucun warning. Détail et justification : §2.3 de chaque `.md`.

> **Batch desktop 2026-09-02 — NOUVELLE CATÉGORIE `desktop/`** (7 stacks) : `delphi-vcl`, `wpf`, `qt-cpp`, `electron`, `winforms`, `javafx`, `pyside`. Ce n'est pas qu'un ajout de fichiers : la catégorie a dû être **câblée dans le framework** — enum `category` du schéma, `preflight.py` (détection `frontendKind=desktop`, exclusivité avec `mobiles/*` et `frontend/*`, globs de fichier-projet `CMakeLists.txt` / `*.sln`), `validate_stack_md_headers.py`, et un quatrième `buildSystem` (`cmake`). **Trois stacks sont Windows-only** (`delphi-vcl`, `wpf`, `winforms`) et portent un gate d'hôte bloquant ; deux portent une **contrainte de licence structurante** (`qt-cpp` : LGPL vs commerciale, avec le piège `Qt6::Charts` qui est en GPL ; `pyside` : PySide6 LGPL retenu **contre** PyQt6 GPL). Pièges de résolution évités et documentés : builds `-ea` de JavaFX sur Maven Central, suffixes `-ci` / `-nblumhardt` / `-g` sur NuGet — tous invisibles aux filtres de prerelease usuels, d'où un filtre **strict** (`^\d+(\.\d+){1,3}$`) appliqué à tout le batch. Détail par stack : §2.3 de chaque `.md`.

**🟢 (28)** : tous les autres (cf. table détaillée + tiers `validated` / `bench-validated` / `scaffold-validated` dans `§1-§2 ci-dessous`).

**Engagement commercial — 13 combos SLA** : 2 `validated` end-to-end (C1, C2) + 11 `bench-validated runtime` (C3-C13). SSoT machine : `@.sdd/templates/combos.json`. Marquage runtime via hook `preflight_stack_combo` (`SDD_ALLOW_UNTESTED_COMBO=1` = bypass audit-loggué). Les stacks 🟡 ne sont **jamais vendus en offre standalone** (pas de SLA sur la dimension isolée). **Exception documentée (GOV-C1, 2026-06-12)** : un *pattern* archi 🟡 peut apparaître **à l'intérieur d'un combo `validated`** dont le run `/sdd-full` bout-en-bout a été vérifié — cas unique **C2** (`archi/ddd`, validé sur workspace réel 2026-05-11 ; cf. `combos.json` C2 `notes`). Le SLA porte sur le **combo** vérifié, pas sur la dimension 🟡 isolée.

Détail tiers, matrice dimensions, 23 combinaisons bench 2026-06-05, cible C3-prod, exceptions `.libs.json` : `@.sdd/docs/validated-combos.md`.

---

---

## 1. Quick reference — combos validés bout-en-bout

### 1.1 Tiers de validation (v7.0.0-alpha)

| Tier | Critère | Garanties |
|:--:|---|---|
| 🟢 **validated** | `/sdd-full {n}` complet (FEAT → US → arch → dev → QA → auditors) bout-en-bout sans intervention humaine non documentée sur ≥ 1 FEAT M | Pipeline entièrement automatisé, gates bloquantes appliquées, audit-trail console.db complet |
| 🟢 **bench-validated runtime** | Code généré (patterns + libs) compile + démarre + sert les ACs ; preuves runtime (curl, build vert, page rendue) | Stack patterns conformes, contrat HTTP source-first respecté ; **pipeline `/sdd-full` partiellement bypassé** (scaffolding manuel mainteneur sur agents non câblés, cf. `docs/benchmarks/known-gaps.md`) |
| 🟡 **experimental** | Spec stack OK + `.libs.json` valide, jamais exécuté | Conformité unitaire ≠ garantie runtime |
| 🟡 **POC-only** | Validé uniquement pour usage interne (console SDD), pas prod externe | Volontairement limité |

### 1.2 Combos « validated » (full pipeline) — 2

| ID | Backend | Frontend | UI DS | QA | Auth | DB | Status | Dernière PoC |
|:---:|---|---|---|---|---|---|:---:|---|
| **C1** | `dotnet-minimalapi` | `react` | `shadcn` | `dotnet-xunit` | `azure-ad` | PostgreSQL | 🟢 validated | 2026-05-07 |
| **C2** | `kotlin-spring-boot` | `react` | `shadcn` | `kotlin-junit` + `node-vitest` | `azure-ad` | PostgreSQL | 🟢 validated | 2026-05-11 (workspace DemoApp) |

### 1.3 Combos « bench-validated runtime » — bench 2026-06-05 (23 combinaisons)

Bench session 2026-06-05T10:13Z → 12:03Z (~4h cumulé), poste Windows mainteneur. Rapport
consolidé : [`workspace/.sys/.bench/BENCH-GLOBAL-REPORT.md`](../../workspace/.sys/.bench/BENCH-GLOBAL-REPORT.md).

#### 1.3.a Cross-origin REST (16 combinaisons : 4 backends × 4 SPA fronts)

| Backend | React :5186 | Blazor WASM :5004 | Vue :5180 | Angular :4200 |
|---|:--:|:--:|:--:|:--:|
| Kotlin Spring Boot 3.3.5 (`:44329` stop) | 🟢 | 🟢 | 🟢 | 🟢 |
| .NET 10 Minimal API (`:44329` subst.) | 🟢 | 🟢 | 🟢 | 🟢 |
| Node Express + TS + Zod (`:44329` subst.) | 🟢 | 🟢 | 🟢 | 🟢 |
| **Python FastAPI + Pydantic (`:44329` actif)** | 🟢 | 🟢 | 🟢 | 🟢 |

**Preuve source-first** : 4 substitutions backend transparentes sur le même port :44329 sans modifier aucun fichier front. Contrat HTTP unique `POST /api/calc {a,b}→{c}` respecté à l'identique par les 4 stacks.

**Latences POST 5+5** : FastAPI 33ms (🏆) < Node 47ms < Kotlin 162ms < .NET cold JIT 237ms.

#### 1.3.b Monolithes fullstack (6 combinaisons)

| FEAT | Stack | Port | Pattern | LOC | Verdict |
|:--:|---|---|---|--:|:--:|
| 7 | Blazor Server SignalR .NET 8 | :44339 | WebSocket streaming HTML diff | 601 | 🟢 |
| 8 | Kotlin Spring + Mustache SSR | :44349 | HTML 100% server-rendered + form POST | **159** | 🟢 |
| 9 | Next.js 15 + Server Actions | :44359 | Server Components + RPC sérialisé | 2017 | 🟢 |
| 10 | Nuxt 4 + Nitro Server Routes | :44369 | File-based REST-like | 11690 | 🟢 |
| 11 | Angular Universal 19 SSR Express | :44379 | SSR initial + hydration client | 16438 | 🟢 |
| 14 | Node-React zero-build Fastify+Babel CDN | :44389 | Zero bundler, transpile in-browser | 1524 | 🟢 |

#### 1.3.c Mobiles natifs (3 stacks)

| FEAT | Stack | Cible runtime | Verdict |
|:--:|---|---|:--:|
| 12 | Kotlin Android Compose + Retrofit | scaffold seul (ANDROID_HOME absent) | 🟡 scaffold |
| 15 | MAUI 9 Windows desktop WinUI3 | runtime build + window 246MB | 🟢 |
| 16 | React Native Expo Web | runtime web :44399 + cross-origin → FastAPI | 🟢 |

#### 1.3.d 5 bugs runtime fixés en bench, inscrits SSoT dans `library-and-stack.md §7`

1. **CORS `localhost` ≠ `127.0.0.1`** — preflight 403 silencieux → allowlist multi-host {localhost, 127.0.0.1} × N ports
2. **`<input type=number>` coerce → state framework cassé** Vue/Angular — `ref<number\|null>` + `.number` modifier
3. **JMustache rejette `null` keys strict** — populer Model avec strings vides + flags `hasX` booléens
4. **`pydantic-core 2.10` no-wheel Py3.14** — pin `pydantic>=2.11`
5. **bUnit `.Change()` ≠ `@bind:event="oninput"`** — utiliser `.Input("value")` avec immediate binding

### 1.4 Combos C3-C13 « bench-validated runtime » (SLA Tier 2)

Les 11 combos C3-C13 (cf. `templates/combos.json`) sont **SLA-éligibles
best-effort** depuis v7.0.0 GA. Top 3 documentés ci-dessous (cf. combos.json
pour la liste complète C3-C13) :

| ID | Backend | Frontend | UI DS | QA | Auth | Bench runtime | Pending |
|:---:|---|---|---|---|---|:---:|:---:|
| **C3** | `node-express` | `react` | `shadcn` | `node-vitest` | `auth-local` | 🟢 | `/sdd-full` complet (Gap 1, `known-gaps.md`) |
| **C4** | `python-fastapi` | `react` | `shadcn` | `python-pytest` + `node-vitest` | `auth-local` | 🟢 | idem |
| **C5** | `dotnet-minimalapi` | `vue` | `vuetify` | `dotnet-xunit` + `node-vitest` | `azure-ad` | 🟢 (subst.) | idem |

**Distinction-clé** : bench runtime ≠ full-pipeline. Le bench prouve que les
**stack patterns** sont conformes (code généré tourne). La promotion en
`validated` end-to-end demande de prouver que **les agents SDD_Pro orchestrent
automatiquement** sans scaffolding manuel — chantier tracé dans
`docs/benchmarks/known-gaps.md` (Gap 1).

**Hors C1-C13 (combos non listés `combos.json`) : aucune garantie SLA.** Le
pipeline peut échouer en runtime de manière non triviale (scaffolding DB,
mapping HTML→DS, capabilities on-demand, conventions stack-specific).

---

## 2. Matrice de couverture — dimensions × statut

> **MAJ audit CTO 2026-06-09 (Major #5 closure)** : tableau aligné sur
> la SSoT `componentLevels` de `templates/combos.json` et sur les en-têtes
> `Validation:` des fichiers `.sdd/stacks/{cat}/*.md`. Plusieurs stacks
> historiquement listés 🟡 sont passés 🟢 bench-validated après le bench
> du 2026-06-05 (`python-pytest`, `angular-jasmine`, `vuetify`, `auth-local`).

| Dimension | 🟢 validated (full pipeline) | 🟢 bench-validated runtime (2026-06-05) | 🟡 experimental | 🔴 untested |
|---|---|---|---|---|
| **Backend** | `dotnet-minimalapi`, `kotlin-spring-boot` | `python-fastapi`, `node-express` | — | — |
| **Frontend** | `react`, `blazor-webassembly` | `vue`, `angular` | — | — |
| **UI DS** | `shadcn`, `radzen-blazor` | `vuetify` | — | — |
| **QA** | `dotnet-xunit`, `kotlin-junit`, `node-vitest`, `blazor-bunit`, `code-quality` | `python-pytest`, `angular-jasmine` | `mutation-testing` (opt-in), `playwright` (opt-in) | — |
| **Auth** | `azure-ad` | `auth-local` | — | — |
| **DB** | PostgreSQL | — | SqlServer (combos non bench) | MySql, MariaDb, Sqlite, Oracle, MongoDb |
| **Archi pattern** | `mvc` | — | `ddd` (combos C2 exercé, PoC formel pending), `microservice` (quarantaine v7) | — |
| **Fullstack** | — | `angular-universal`, `blazor-server`, `kotlin-mustache`, `next`, `nuxt` | `aspnet-mvc-razor` (ajouté 2026-06-10, jamais bench) | `node-react` (🟡 **POC-only** : console SDD interne, hors prod externe) |
| **Mobiles** | — | `maui` (Win desktop), `react-native` (Expo Web) | `kotlin-android` (scaffold-validated, APK runtime pending — SDK absent au bench) | — |

**Recount canonique 2026-06-11** : 28 🟢 (4 backend + 4 frontend + 3 UI + 7 QA + 2 auth + 1 archi + 5 fullstack + 2 mobiles) + 7 🟡 (5 experimental dont `fullstack/aspnet-mvc-razor` ajouté 2026-06-10 + 1 POC-only `fullstack/node-react` + 1 scaffold-validated `mobiles/kotlin-android`, downgradé 🟢→🟡 audit CTO 2026-06-07) = **35 total** (cf. gate `framework_smoke.py` constante `expected_total = 35`).

> Lecture : un stack 🟡 experimental est conforme techniquement (entête
> `Validation:`, `.libs.json` valide, tests stack-level OK) mais **n'a jamais
> été utilisé dans un combo bench runtime**. Un stack 🟢 bench-validated a
> tourné runtime (curl, build vert, AC servies) mais `/sdd-full` end-to-end
> reste partiellement manuel (cf. `docs/benchmarks/known-gaps.md`).

### 2.ter Critères de promotion 🟡 → 🟢 (audit 2026-06-11)

Un stack `🟡 experimental` est promu `🟢 scaffold-validated` puis
`bench-validated` uniquement sur preuve, jamais sur ancienneté :

1. **scaffold-validated** : un `/sdd-full` complet sur une FEAT CRUD simple
   (1-2 US) aboutit build vert + structure conforme `ownership.md §1.bis`.
2. **bench-validated** : run bench runtime (méthodo
   `docs/poc-roi-methodology.md`) — serveur démarre < 30 s nominal, ≥ 4 ACs
   servies via curl/navigateur, gate `code-quality` 🟢.
3. MAJ coordonnée : entête `Validation:` du stack, `combos.json` si combo,
   recount CLAUDE.md §6 + `framework_smoke.expected_total`.

Stacks en attente (état 2026-06-11) : `fullstack/aspnet-mvc-razor`
(critère 1 non exécuté), `mobiles/kotlin-android` (scaffold OK, APK runtime
pending → retour bench-validated au critère 2). Un stack expérimental sans
candidature de promotion ni consommateur après 2 cycles MINOR est candidat
retrait (cf. `docs/orphan-cleanup-policy.md`).

### 2.bis Stacks sans `.libs.json` compagnon — exceptions documentées

**Major #6 audit closure 2026-06-09**. Convention SDD_Pro : tout stack
applicatif (backend / frontend / ui / qa-test-runner / fullstack / mobiles)
a un `.libs.json` compagnon (SSoT install via `arch` Phase A). Exceptions
légitimes (catalogue machine non pertinent) :

| Stack | Catégorie | Raison de l'exception |
|---|---|---|
| `archi/mvc.md` | Pattern architectural | Conceptuel — n'installe aucune lib, librairie consommée via le stack backend actif |
| `archi/ddd.md` | Pattern architectural | Idem — Domain-Driven Design est un pattern, pas un package |
| `archi/microservice.md` | Pattern architectural | Idem — pattern d'organisation cross-services |
| `auth/azure-ad.md` | Protocole d'authentification | Cross-langage (OIDC/OAuth2 + MSAL/JWT) — les libs concrètes vivent dans le `.libs.json` du backend consommateur (`Microsoft.Identity.Web`, `spring-security-oauth2-resource-server`, `python-jose`, etc.) |
| `auth/auth-local.md` | Protocole d'authentification | Idem — JWT HS256 + bcrypt natif, libs portées par le backend (`bcryptjs`, `jjwt`, `passlib`, etc.) |
| `qa/code-quality.md` | Ruleset cross-stack | Sonar-like checks déterministes consommés par `quality_scan.py` (script Python), pas de runtime test framework dédié |

Validation enforcement : `python .sdd/python/sdd_admin/validate_libs_catalog.py`
ignore explicitement ces 6 fichiers via leur catégorie / nom.

---

## 3. Combos prioritaires post-v7.0.0 GA

Plan de validation. **Réordonné 2026-06-05** (décision tracée dans
`CHANGELOG.md` entrée v7.0.0-alpha, section "Décision combo C3-bis cible") :
Node monté en priorité 3 (combo cible commerciale crédible vs BMad/AgentOS
sur écosystème JS).

| ID | Hypothèse | Backend | Frontend | UI DS | QA | Auth | DB | Effort | Statut |
|:---:|---|---|---|---|---|---|---|---|---|
| ~~C3-bis~~ | ~~Fullstack Node monolithe~~ | ~~`fullstack/node-react`~~ | — | — | — | — | — | — | ❌ **RETIRÉ** (audit P3 2026-06-05) : `node-react` marqué `poc-only` (console SDD interne uniquement, pas prod externe). Pour Node prod : voir C-Node-prod ci-dessous. |
| **C-Node-prod** | **Node back-front séparés (cible prod)** | `backend/node-express` (Fastify/Express + TS + Zod + Pino) | `frontend/react` (Vite + TS strict + Tailwind) | `shadcn` | `node-vitest` + `playwright` | `auth-local` | PostgreSQL via Prisma | 3-5 j | 🟡 **bench validé runtime** 2026-06-05 (CalcABCBackNode + CalcABC React, 5+3 tests passed). À promouvoir 🟢 après PoC FEAT M réelle. |
| **C4** | Stack microsoft pur (ex-C3) | `dotnet-minimalapi` | `blazor-webassembly` | `radzen-blazor` | `dotnet-xunit` + `blazor-bunit` | `azure-ad` | SqlServer | 2-3 j | non démarré |
| **C5** | Stack JS séparé back-front | `node-express` | `vue` | `vuetify` | `node-vitest` | `auth-local` | PostgreSQL | 3-4 j | non démarré |
| **C6** | Stack Python | `python-fastapi` | `angular` | (custom Material 3) | `python-pytest` + `angular-jasmine` | `azure-ad` | PostgreSQL | 4-5 j | non démarré |

**Méthodologie** : suivre `docs/poc-roi-methodology.md` — bench S/M/L,
mesurer wall-clock + coût + coverage, publier dans `workspace/.sys/.bench/BENCH-GLOBAL-REPORT.md`.

**Critères d'acceptation combo** :
- ≥ 1 FEAT M (3 US, back+front, AC traçables) bout-en-bout sans bypass
- Coverage ≥ `CoverageMin` (80 % défaut)
- Spec-compliance verdict ≠ RED
- Security-scan verdict ≠ RED
- Build vert sans intervention manuelle
- ROI publié (3 runs, variance ≤ 15 %)

---

## 4. Comment savoir si MON combo est validé

### 4.1 Méthode manuelle (10 secondes)

1. Ouvrir `workspace/stack/stack.md`
2. Lire les blocs `## Active *`
3. Comparer avec §1 ci-dessus :
   - **Tous** les composants (Backend + Frontend + UI + QA + Auth + DB)
     matchent C1 ou C2 → 🟢
   - **Au moins un** composant 🟡 → 🟡 expérimental
   - **Au moins un** composant 🔴 → 🔴 non testé (risque élevé)

### 4.2 Méthode automatisée (script déterministe)

```bash
python .sdd/python/sdd_scripts/validate_stack_combo.py --json
```

Exit codes :

| Exit | Status | Action recommandée |
|:---:|---|---|
| `0` | 🟢 validated | Aucune. Pipeline `/sdd-full` safe. |
| `1` | 🟡 experimental | WARN. Vérifier le PoC ROI méthodologie avant prod. Bypass auto. |
| `2` | 🔴 untested | STOP. Refuser run automatique. Bypass : `SDD_ALLOW_UNTESTED_COMBO=1` env var (audit-loggué). |
| `3` | invalid | `[STACK_COMBO_INVALID]` — combo incohérent (ex. mix back+fullstack). |

Output JSON (extrait) :
```json
{
  "signature": "kotlin-spring-boot+react+shadcn+kotlin-junit+azure-ad+postgres+ddd",
  "matched_combo": "C2",
  "status": "validated",
  "exit_code": 0,
  "components": {
    "backend": {"id": "kotlin-spring-boot", "level": "validated"},
    "frontend": {"id": "react", "level": "validated"},
    "ui": {"id": "shadcn", "level": "validated"},
    "qa": [{"id": "kotlin-junit", "level": "validated"}, {"id": "node-vitest", "level": "validated"}],
    "auth": {"id": "azure-ad", "level": "validated"},
    "db": {"type": "postgres", "level": "validated"},
    "archi": {"id": "ddd", "level": "experimental"}
  },
  "warnings": [
    "Archi pattern 'ddd' is experimental (workspace DemoApp uses it but no formal PoC)"
  ]
}
```

### 4.3 Intégration pipeline

Le script peut être câblé dans :

- **Hook PreToolUse Agent** (`.claude/settings.json`) — bloque les invocations
  Agent si exit ≥ 2 et `SDD_ALLOW_UNTESTED_COMBO` absent.
- **STEP 0.5 de `/sdd-full`** — appel manuel par Tech Lead avant pipeline.
- **CI gate** — block les merges qui changent `stack.md` vers un combo
  non-PoC sans ADR justificatif.

> Pas câblé en hook par défaut (v7.0.0-alpha) — décision discrétionnaire
> du Tech Lead via `.claude/settings.local.json`. Sera décision GA v7.0.0
> selon retours adoption (cf. roadmap v7-v8).

---

## 5. Politique commerciale recommandée

L'audit historique a identifié un désalignement entre la **promesse marketing**
(35 stacks supportés) et la **vérité empirique** (2 combos validés end-to-end +
11 bench-validated). Position retenue v7.0.0 GA :

### 5.1 Position canonique v7.0.0 GA — *« 2 combos validated + 11 bench-validated »*

**Communiquer** : SDD_Pro v7.0 supporte officiellement 13 combos SLA = 2
combos C1/C2 validated end-to-end + 11 combos C3-C13 bench-validated runtime
(best-effort, scaffolding semi-manuel — cf. `known-gaps.md` Gap 1).

**Action immédiate** : renommer le tagline dans README + CLAUDE.md.
Marquer 🟢/🟡/🔴 explicitement dans chaque stack `.md`. Ajouter le
script §4.2 au pipeline preflight.

**Avantage** : honnêteté → confiance utilisateur. Pas de mauvaise
surprise runtime.

**Inconvénient** : positionnement plus modeste, mais défendable
empiriquement.

### 5.2 Option B — *« Multi-stack PoC matrix CI »*

**Investir** : ressources pour valider C3-bis puis C4-C6 (effort 2-5 jours chacun
selon §3). Cible : 5 combos validés à v7.1.0 (C3-bis prioritaire).

**Avantage** : promesse multi-stack tenue.

**Inconvénient** : coût significatif (10-15 jours-homme) sans utilisateur
demandeur identifié.

### 5.3 Option C — *« Quarantaine élargie »* (historique, rollback v7.x)

**Position historique v7.0.0** : déplacer tous les stacks 🔴 / 🟡 jamais
utilisés vers `.sdd/stacks/_drafts/`. Cette quarantaine a été **rollback
en v7.x** (décision tracée dans `CHANGELOG.md` entrée v7.0.0-alpha,
section "Stacks quarantine `_drafts/` rollback") : tous les stacks sont
désormais chargeables sous `.sdd/stacks/{cat}/`. Le statut 🟢/🟡 reste
signalé par le frontmatter `Validation:` de chaque stack.

**Avantage de la nouvelle approche** : surface unique, statut explicite
par stack, plus de mécanisme de filtrage spécial dans les scripts Python.

**Inconvénient** : retour en arrière sur le travail v6.x sur ces stacks.

---

## 6. Risques runtime spécifiques aux combos non-validés

Pour information / mitigation préventive si vous tentez un combo 🟡/🔴 :

| Risque | Probabilité 🟡 | Probabilité 🔴 | Mitigation |
|---|:---:|:---:|---|
| Scaffolding DB échoue (introspection driver/dialect) | Moyenne | Élevée | Tester `arch --rebuild-arch` sur DB de test |
| Mapping HTML→DS partiel (composants exotiques) | Faible | Élevée | Valider mockups simples (table, form, button) d'abord |
| Capabilities on-demand non triggered (regex stack-specific) | Moyenne | Élevée | Lire `.libs.json` `onDemand[].triggers[]` avant FEAT |
| Convention naming endpoints divergente | Faible | Moyenne | Lire `stacks/backend/{id}.md §2.6` (convention URL) |
| Build loop ne converge pas (BUILD_BLOCKING) | Faible | Élevée | Réduire complexité US, splitter en plusieurs FEATs |
| Auth flow stack-specific cassé | Faible | Moyenne | PoC isolé `/feat-generate Auth` d'abord |
| QA fixtures in-memory incompatible | Moyenne | Élevée | Override `IntegrationTestMode: containers` (Docker) |
| CORS préset frontend dev port incorrect | Faible | Faible | `Cors:AllowedOrigins` explicite dans Project Config |

---

## 7. Historique combos validés

| Combo | Tag SDD_Pro | Date | Validateur | Note |
|:---:|---|---|---|---|
| C1 | v6.0.0 | 2026-05-07 | SDD-Pro maintainer | Stack initial du framework |
| C2 | v6.10.4-LTS | 2026-05-11 | SDD-Pro maintainer | Workspace DemoApp (4 FEATs, 10 US, schema PostgreSQL) |
| C3-bis | en cours | 2026-06-05 (décidé) | SDD-Pro maintainer | PoC partiel Demo + console SDD v0.4.0. Cible v7.1 (cf. §3) |
| C4-C6 | `<TBD>` | `<TBD>` | `<TBD>` | Planifiés post-C3-bis validé (cf. §3) |

---

## 8. Pointers

- `@.claude/CLAUDE.md §7` — table stacks (statut `Validation:` par stack)
- `@.sdd/docs/architecture.md §4` — détail des stacks supportés
- `@.sdd/docs/poc-roi-methodology.md` — méthodologie de validation combo
- `@.sdd/python/sdd_scripts/validate_stack_combo.py` — script §4.2
- `CHANGELOG.md` entrée v7.0.0-alpha — décision rollback `_drafts/` v7.x

---

*Document maintenu à chaque nouvelle PoC combo validée. Source de vérité
pour la décision « ce combo est-il safe ? ». Référencé depuis CLAUDE.md §7.*
