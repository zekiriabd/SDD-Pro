# SDD_Pro — Validated stack combos (référence canonique)

> Document chargé **à la demande** (`Read @.claude/docs/validated-combos.md`).
> Crée pour résoudre la critique M3 (audit v7.0.0) :
> *« 16 stacks → ~120 combinaisons possibles, 2 validées bout-en-bout ;
> le risque que le pipeline casse en runtime sur un combo non-PoC est
> explicitement reconnu. Promesse multi-stacks largement théorique. »*
>
> **Objectif** : avant tout `/sdd-full {n}`, savoir en **10 secondes** si
> le combo actif est `validated`, `experimental` ou `untested` — et
> ce que cela implique.

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
| **C2** | `kotlin-spring-boot` | `react` | `shadcn` | `kotlin-junit` + `node-vitest` | `azure-ad` | PostgreSQL | 🟢 validated | 2026-05-11 (workspace CMSPrint) |

### 1.3 Combos « bench-validated runtime » — bench 2026-06-05 (23 combinaisons)

Bench session 2026-06-05T10:13Z → 12:03Z (~4h cumulé), poste Windows mainteneur. Rapport
consolidé : [`workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`](../../workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md).

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

| Dimension | 🟢 Validé (combo PoC) | 🟡 Expérimental (stack OK, combo jamais testé) | 🔴 Non testé |
|---|---|---|---|
| **Backend** | `dotnet-minimalapi`, `kotlin-spring-boot` | `python-fastapi`, `node-express` | — |
| **Frontend** | `react`, `blazor-webassembly` (combo C1) | `vue`, `angular` | — |
| **UI DS** | `shadcn`, `radzen-blazor` (combo C1) | `vuetify` | — |
| **QA** | `dotnet-xunit`, `kotlin-junit`, `node-vitest`, `blazor-bunit` (combo C1), `code-quality` | `python-pytest`, `angular-jasmine`, `mutation-testing`, `playwright` | — |
| **Auth** | `azure-ad` | `auth-local` | — |
| **DB** | PostgreSQL (via Kotlin + .NET) | SqlServer (via .NET stacks, doc OK) | MySql, MariaDb, Sqlite, Oracle, MongoDb |
| **Archi pattern** | `mvc` (implicite C1) | `ddd` (workspace CMSPrint, non-PoC formel) | `microservice` (en quarantaine v7) |
| **AppType** | `back-front/web` | `fullstack`, `back-front/mobile` | `mobile-{react-native,maui}` (stacks quarantine) |

> Lecture : un stack 🟡 est conforme techniquement (entête `Validation:`,
> `.libs.json` valide, tests stack-level OK) mais **n'a jamais été utilisé
> dans une PoC `/sdd-full` complète**. La conformité unitaire ≠ garantie d'intégration.

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
mesurer wall-clock + coût + coverage, publier dans `workspace/output/qa/bench/BENCH-GLOBAL-REPORT.md`.

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

1. Ouvrir `workspace/input/stack/stack.md`
2. Lire les blocs `## Active *`
3. Comparer avec §1 ci-dessus :
   - **Tous** les composants (Backend + Frontend + UI + QA + Auth + DB)
     matchent C1 ou C2 → 🟢
   - **Au moins un** composant 🟡 → 🟡 expérimental
   - **Au moins un** composant 🔴 → 🔴 non testé (risque élevé)

### 4.2 Méthode automatisée (script déterministe)

```powershell
python .claude/python/sdd_scripts/validate_stack_combo.py --json
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
    "Archi pattern 'ddd' is experimental (workspace CMSPrint uses it but no formal PoC)"
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
(34 stacks supportés) et la **vérité empirique** (2 combos validés end-to-end +
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
utilisés vers `.claude/stacks/_drafts/`. Cette quarantaine a été **rollback
en v7.x** (décision tracée dans `CHANGELOG.md` entrée v7.0.0-alpha,
section "Stacks quarantine `_drafts/` rollback") : tous les stacks sont
désormais chargeables sous `.claude/stacks/{cat}/`. Le statut 🟢/🟡 reste
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
| C1 | v6.0.0 | 2026-05-07 | A. Zekiri | Stack initial du framework |
| C2 | v6.10.4-LTS | 2026-05-11 | A. Zekiri | Workspace CMSPrint (4 FEATs, 10 US, schema PostgreSQL) |
| C3-bis | en cours | 2026-06-05 (décidé) | A. Zekiri | PoC partiel NounouJob + console SDD v0.4.0. Cible v7.1 (cf. §3) |
| C4-C6 | `<TBD>` | `<TBD>` | `<TBD>` | Planifiés post-C3-bis validé (cf. §3) |

---

## 8. Pointers

- `@.claude/CLAUDE.md §7` — table stacks (statut `Validation:` par stack)
- `@.claude/docs/architecture.md §4` — détail des stacks supportés
- `@.claude/docs/poc-roi-methodology.md` — méthodologie de validation combo
- `@.claude/python/sdd_scripts/validate_stack_combo.py` — script §4.2
- `CHANGELOG.md` entrée v7.0.0-alpha — décision rollback `_drafts/` v7.x

---

*Document maintenu à chaque nouvelle PoC combo validée. Source de vérité
pour la décision « ce combo est-il safe ? ». Référencé depuis CLAUDE.md §7.*
