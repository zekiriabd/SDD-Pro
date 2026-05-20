# SDD_Pro — Architecture (référence)

> Document de référence chargé **à la demande** (`Read @.claude/docs/architecture.md`).
> Pas en system prompt.

## 1. Vision

Le PO humain rédige une FEAT fonctionnelle. L'UX Designer (humain) dépose
des **mockups HTML statiques** dans `workspace/input/ui/`. Une chaîne de **4
agents** spécialisés (PO, Arch, Dev-Backend, Dev-Frontend) transforme
l'ensemble en :

1. **User Stories structurées** (1 à 6 par FEAT, cible 1-3) — agent PO
2. **Bootstrap solution + projets vides + (si DB) schéma + entities
   scaffoldées** — agent Arch (idempotent, READ-ONLY sur la base)
3. **Code serveur** — agent Dev-Backend (planifie inline depuis l'US)
4. **Code client** — agent Dev-Frontend (planifie inline depuis l'US +
   HTML mockup + stack UI)

Le bootstrap + scaffolding DB est exécuté UNE FOIS par projet. Le code
est ensuite généré en parallèle par Dev-Backend et Dev-Frontend.

## 2. Modèles assignés par agent

| Agent          | Modèle              | Justification                                       |
|----------------|---------------------|-----------------------------------------------------|
| `po`           | `claude-sonnet-4-6` | Découpage logique, traçabilité — pas de multimodal  |
| `arch`         | `claude-sonnet-4-6` | Init solution + projets vides + introspection DB + scaffolding |
| `dev-backend`  | **`claude-opus-4-7`** | Raisonnement fin sur génération code serveur, `preserves:`/`adds:`, layer mapping |
| `dev-frontend` | **`claude-opus-4-7`** | Raisonnement fin sur génération code client + fidélité HTML→DS |
| `dev-backend-strict` (v6.2) | `claude-sonnet-4-6` | Variant rapide : consomme plan v2 strict-ready (digest auto-suffisant), ~3× plus rapide, ~5× moins cher. Opt-in via `PlanCacheStrict: true` |
| `dev-frontend-strict` (v6.2) | `claude-sonnet-4-6` | Idem côté frontend, fidelity check préservé |
| `elicitor`     | `claude-sonnet-4-6` | Élicitation structurée 5 techniques                 |
| `constitutioner` | `claude-sonnet-4-6` | Sub-agent de `arch` Phase D : crée ADRs + maj constitution §1/§4/§6 + INDEX.md |
| `qa`           | `claude-sonnet-4-6` | Génération tests unitaires                          |
| `dashboard`    | `claude-haiku-4-5-20251001` | Rendu HTML déterministe (README + INDEX ADRs + dashboards QA) |
| `accessibility-auditor` (v6.3.0) | `claude-haiku-4-5-20251001` | Scan WCAG 2.2 AA déterministe du markup frontend (greps ciblés, table FIX inline) |
| `code-reviewer` (v6.3.1) | `claude-sonnet-4-6` | Review post-dev cross-fichier : anti-patterns stack, layer violations, contract drift, smells (complémentaire de qa/quality_scan.py) |
| `security-reviewer` (v6.3.2) | `claude-sonnet-4-6` | 2 modes : `threat-model` (pré-dev STRIDE light) + `scan` (post-dev OWASP Top 10 2021, 21 classes `[SEC_*]`, 8 hard-blocking) |
| `performance-auditor` (v6.4.0) | `claude-sonnet-4-6` | Analyses statiques + dynamiques (Lighthouse opt-in) : Core Web Vitals, SLO API, bundle, N+1 cross-fichier, memory leak, DB query. 16 classes `[PERF_*]`. Opt-in via `PerfMode: full`. |

> **Split modèles (depuis 2026-05-08)** : Opus 4.7 sur les agents qui
> génèrent du code applicatif (`dev-backend`, `dev-frontend`) — la
> qualité du code généré justifie le coût supplémentaire (preserves/adds
> contractuels, layer mapping strict, fidélité libellés HTML). Sonnet
> 4.6 sur les agents de transformation déterministe (po, arch, elicitor,
> qa). Haiku 4.5 sur le rendu déterministe (dashboard).
>
> **v6.0** : agent `validator` retiré (économie ~1.4M tokens/run).
> `/feat-validate` est désormais 100% déterministe via Python (`validate_readiness.py` + `validate_semantic.py`).
>
> **v6.2** : forks `dev-backend-strict` + `dev-frontend-strict` (Sonnet 4.6)
> activés via `PlanCacheStrict: true`. Quand un plan v2 strict-ready
> existe (validé par `validate_plan.py --strict`), le routing `/dev-run`
> STEP 6.0.bis spawn ces forks au lieu d'Opus 4.7. Fallback automatique
> classic Opus sur `[PLAN_DIGEST_INSUFFICIENT]`. Cf.
> `@.claude/docs/DESIGN-FROMPLAN-STRICT.md`.

## 3. Agents — lectures et écritures

| Agent          | Lit                                                                  | Écrit                                       |
|----------------|----------------------------------------------------------------------|---------------------------------------------|
| `po`           | `workspace/input/feats/{n}-*.md`, rules, templates                             | `workspace/output/us/{n}-{m}-*.md`                    |
| `arch`         | `workspace/input/stack/stack.md`, stacks actifs (Init Commands §2.2.1, scaffolding §3-§4, connection string §5.1), env vars `DB_*` | `workspace/output/src/...` (projets vides + .sln) ; (si DB) `workspace/output/db/schema.json` + `.md`, entities scaffoldées |
| `dev-backend`  | `workspace/output/us/{n}-{m}-*.md`, `workspace/input/ui/{n}-{m}-*.html` (passif), `workspace/output/src/{BackendName}/CLAUDE.md`, stacks `backend/auth` actifs, `workspace/output/db/schema.json` | `workspace/output/src/{BackendName}/...` (code applicatif) |
| `dev-frontend` | `workspace/output/us/{n}-{m}-*.md`, `workspace/input/ui/{n}-{m}-*.html` (texte direct, source de vérité visuelle), `workspace/output/src/{AppName}/CLAUDE.md`, stacks `frontend/ui` actifs | `workspace/output/src/{AppName}/...` (code applicatif) |
| `qa`           | US + code production (read-only) + ACs                               | `workspace/output/qa/feat-{n}/{report.md, coverage.json, quality.json}` + tests unitaires |
| `constitutioner` | ADRs existants + section §6 constitution.md                        | `workspace/output/.sys/.context/constitution.md` (§1/§4/§6) + `workspace/output/.sys/.context/adrs/INDEX.md` |
| `dashboard`    | ADRs `.md` (Glob `workspace/output/.sys/.context/adrs/ADR-*.md`) + `adrs-index.template.md` | `workspace/output/.sys/.context/adrs/INDEX.md` *uniquement* (v6.10 BREAKING : HTML retirés, métriques dans `console.db`) |
| `accessibility-auditor` (v6.3.0) | markup frontend généré (`.razor/.tsx/.vue/.html`) + Project Config (`A11yMode/Threshold/FailOn`) + error-classification.md | `workspace/output/qa/feat-{n}/a11y-report.{md,json}` |
| `code-reviewer` (v6.3.1) | plan v2 ou fallback convention → code production `src/{BackendName|AppName|LibName}/**` + US passif + Project Config (`CodeReviewMode/FailOn`) + stacks §1.3+§3 actifs + error-classification.md + build-and-loop.md | `workspace/output/.sys/.validation/{n}-code-review.{md,json}` |
| `security-reviewer` (v6.3.2) | mode `threat-model` : constitution §3-§4-§7 + FEAT + US + stack auth + Project Config. Mode `scan` : code production + CLAUDE.md projets + stacks §1.3+§3+§2.4 + plan v2 + `{n}-code-review.json` (dé-dup secrets) | `workspace/output/.sys/.validation/{n}-{threat-model,security-scan}.{md,json}` (2 outputs selon mode) |
| `performance-auditor` (v6.4.0) | code production via plan v2 ou convention + CLAUDE.md projets + stacks §1.3+§3 + package.json + dist/ si présent + `coverage.json` (passif) + `{n}-code-review.json` (dé-dup N+1) + Project Config (`PerfMode/FailOn/Thresholds`) | `workspace/output/qa/feat-{n}/perf-report.{md,json}` + `.lighthouse-raw.json` si dispo |

**Isolation par famille** : `dev-backend` ne lit jamais les stacks
`frontend/ui` ; il lit l'HTML uniquement de manière passive pour
identifier les endpoints/DTOs déclenchés par les formulaires/tables.
`dev-frontend` ne lit jamais les stacks `backend` hors patterns
d'injection auth.

**Isolation par phase** : `arch` initialise les projets et introspecte
la base **une seule fois**.

**Skip silencieux par famille** : si une US est frontend pure,
`dev-backend` exit avec `skipped (frontend-only US)`. Inversement.

**Contrat DB READ-ONLY** : `arch` n'exécute aucun
`INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE/EXECUTE` au-delà de
l'introspection des métadonnées.

## 4. Stacks supportés

Sélectionnés par l'humain dans `workspace/input/stack/stack.md` (sections
`## Active …` + `## Active App Type` v6.7.5+).

### 4.0 Active App Type (v6.7.5+)

Le bloc `## Active App Type` du `stack.md` déclare la **topologie projet** :

| AppType | Modèle | Stacks attendus |
|---|---|---|
| `back-front` (défaut) | Backend séparé + Frontend séparé + UI DS | `backend/*` + `frontend/*` + `ui/*` |
| `fullstack` | Projet unique single-process (UI + API + auth intégrés) | `fullstack/*` |
| `mobile-react-native` | Mobile cross-platform (backend distant séparé) | `mobiles/react-native.md` [+ backend distant `backend/*`] |
| `mobile-maui` | Mobile cross-platform .NET MAUI (backend distant séparé) | `mobiles/maui.md` [+ backend distant `backend/*`] |

Validation déterministe par `preflight.py` au démarrage de chaque agent dev-*. Cohérence `AppType ↔ ## Active Tech Specs` vérifiée :
- `AppType=fullstack` SANS stack fullstack/* → `STACK_NOT_SELECTED`
- `AppType=mobile-react-native` SANS `mobiles/react-native.md` → `STACK_NOT_SELECTED`
- Etc.

**Backend** (1 actif requis pour US à composante backend) :
- `backend/dotnet-minimalapi.md` — .NET 10 Minimal API + EF Core + AutoMapper + Serilog + FluentValidation + Polly
- `backend/node-express.md` — Node.js 22 + Express + Prisma
- `backend/python-fastapi.md` — FastAPI 0.115 + SQLAlchemy 2.x async
- `backend/kotlin-spring-boot.md` — Spring Boot 4.0 + Kotlin 2.3 + JPA + MockK

Capabilities **on-demand** (§2.4.b) : EPPlus/ClosedXML (excel),
QuestPDF/iText7 (pdf), MediatR (cqrs), StackExchange.Redis (redis-cache),
Mapster (fast-mapping), Apache POI (excel Java), iText (pdf Java),
ExcelJS (excel Node), PDFKit (pdf Node), openpyxl (excel Python),
reportlab (pdf Python).

**Frontend** (1 actif requis pour US à composante frontend, AppType=`back-front`) :
- `frontend/blazor-webassembly.md`, `frontend/react.md`,
  `frontend/vue.md`, `frontend/angular.md`

**Fullstack** 🟡 (v6.7.5+, single-project SSR — exclusif d'un combo `backend × frontend`, AppType=`fullstack`) :
- `fullstack/node-react.md` — Fastify 5 + React 18 CDN + Babel-in-browser (zero-build, modèle workspace/console)
- `fullstack/blazor-server.md` — Blazor Server .NET 10 + SignalR + Razor (monolithe Microsoft, réintroduit en `fullstack/`)
- `fullstack/next.md` — Next.js 15 + App Router + RSC + Server Actions + Tailwind v4
- `fullstack/nuxt.md` — Nuxt 3 + Nitro + Vuetify + Pinia
- `fullstack/angular-universal.md` — Angular 19 + @angular/ssr (Express intégré)
- `fullstack/kotlin-mustache.md` — Spring Boot 3.4 + Kotlin + Mustache + HTMX/Alpine.js

**Mobiles** 🟡 (v6.7.5+, mobile cross-platform — backend distant séparé, AppType=`mobile-*`) :
- `mobiles/react-native.md` — Expo SDK 52 + RN 0.76 + Expo Router + NativeWind + Zustand
- `mobiles/maui.md` — .NET MAUI 9 + CommunityToolkit.Mvvm + CommunityToolkit.Maui + sqlite-net-pcl + Refit

**UI Design System** (1 actif requis quand mockup HTML présent) :
- `ui/radzen-blazor.md`, `ui/shadcn.md`, `ui/vuetify.md`

> Chaque stack UI déclare en **§2 Mapping fonctionnel → composant DS**
> ET **§7 Mapping HTML → composant DS (v4)** comment traduire les
> primitives HTML brutes (`<table>`, `<button>`, `<select>`, etc.) vers
> les composants natifs.

**Auth** (optionnel) :
- `auth/azure-ad.md`, `auth/auth-local.md`

**QA** (optionnel) — actif si `## Active QA Specs` non vide :
- `qa/dotnet-xunit.md` — xUnit + Coverlet (.NET backend)
- `qa/blazor-bunit.md` — bUnit + xUnit (Blazor frontend)
- `qa/node-vitest.md` — Vitest + RTL/Vue Test Utils
- `qa/python-pytest.md` — pytest + coverage.py
- `qa/kotlin-junit.md` — JUnit 5 + MockK + JaCoCo
- `qa/angular-jasmine.md` — Jasmine + Karma + istanbul
- `qa/code-quality.md` — sonar-like cross-stack (Python, déterministe)

## 5. État du framework — couvert / hors scope

✅ **Couvert** :
- Phase 1 (FEAT) — interactive, 6 questions max + bootstrap constitution
- Phase 1.5 (élicitation) — `/feat-deepen` agent `elicitor`, 5 techniques
- Phase 2 (US) — découpage 1 à 6 (cible 1-3, warning 4-6) + traçabilité 100%
- Phase 2.5 (HTML mockups) — humain dépose `workspace/input/ui/*.html`
- Phase 2.6 (readiness gate) — `/feat-validate {n}` 🟢 GO / 🟡 WARN / 🔴 NO-GO
- Phase 3 (ARCH + DB) — bootstrap idempotent + scaffolding Database-First + ADRs
- Phase 4 (CODE) — Dev-Backend + Dev-Frontend, plan inline, build loop max 3
- Phase 5 (QA + Quality) — tests unitaires + coverage + quality scan sonar-like
- Phase 5.5 (Accessibility, v6.3.0) — scan WCAG 2.2 AA déterministe via `accessibility-auditor` (Haiku), verdict 🟢/🟡/🔴 selon `A11yFailOn`
- Phase 6.4 (Code Review, v6.3.1) — review cross-fichier post-dev via `code-reviewer` (Sonnet) — anti-patterns stack, layer violations, contract drift, smells. Hard-blocking sur `[REVIEW_SECRETS_HARDCODED]` + `[FRONTEND_BACKEND_CONTRACT_GAP]`.
- Phase 3.5 + 6.5 (Security Review, v6.3.2) — `security-reviewer` (Sonnet) 2 modes : pré-dev threat model STRIDE (informational) + post-dev scan OWASP Top 10 (verdict 🟢/🟡/🔴, 8 classes hard-blocking).
- Phase 7 (Performance Audit, v6.4.0) — `performance-auditor` (Sonnet, opt-in `PerfMode: full`) : analyses statiques + dynamiques (Lighthouse CI). Core Web Vitals (LCP/CLS/INP), SLO API p95/p99, bundle, N+1 cross-fichier, memory leak, DB query index. 16 classes `[PERF_*]`. Hard-blocking sur `[PERF_AC_VIOLATION]` uniquement.
- Templates ops (v6.4.0) — `templates/{runbook,postmortem,slo-sli}.template.md` à instancier par le Tech Lead lors de la mise en prod du projet généré.
- Phase planner (v6.4.1) — script Python déterministe `phase_planner.py` qui décide quelles phases auditor sont enabled/skipped selon Project Config + stacks actifs + état runtime + mentions perf/sec dans ACs. Invoqué par `/sdd-full` STEP 1.tiers (récap unifié au démarrage, non bloquant). Détection automatique override pour ACs explicites (`LCP < 2s` force perf-audit même en mode manual).
- Auto-invoke chain (v6.4.2) — branchement effectif des 5 agents auditor dans le pipeline. `/dev-run` STEP 5.5 (threat-model post-arch) + STEP 6.4 (3 agents en parallèle pré-dashboard : code-review + a11y + security-scan). `/qa-generate` STEP 6.4 (perf-audit post-coverage). Verdict 🔴 RED de code-reviewer/a11y/security-scan → STOP avec rapport et procédure de déblocage.

❌ **Hors scope** :
- DevOps / CI / déploiement (templates ops fournis mais pas d'auto-gen pipeline)
- Migrations EF Core forward/rollback
- Dashboard / observabilité production runtime
- E2E tests (out-of-process Playwright/Cypress — non couvert)
- CVE deps scanning runtime (couvert partiellement par `library-and-stack.md §0` post-install par arch)
- Backend dynamic benchmarking via wrk/k6 (prévu v6.4.0.1 via `perf_bench.py`)
- ~~Enrichissement `dashboard` pour absorber les 6 nouveaux JSON auditor dans `README.html`~~ **OBSOLÈTE v6.10** : les auditors persistent désormais dans `console.db` (tables `qa_code_review`, `qa_security`, `qa_perf`, `qa_a11y`, `qa_spec_compliance`) ; le rendu graphique est délégué à la console web (`workspace/console/`) ou consommateur externe
- Script `perf_bench.py` pour benchmark backend dynamique via wrk/k6 (prévu v6.4.0.1)
