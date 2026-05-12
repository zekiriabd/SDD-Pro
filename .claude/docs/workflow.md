# SDD_Pro — Workflow détaillé (référence)

> Document chargé **à la demande** (`Read @.claude/docs/workflow.md`).
> Pas en system prompt.

## 1. Vue d'ensemble — 4 phases (5 avec QA)

```
┌─────────────────────────────────────────────────────────────────┐
│                   PHASE 1 — SPEC (humain)                       │
│  /spec-generate   → workspace/input/specs/{n}-{Name}.md                   │
│  [interactif, max 6 questions]                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 2 — US (agent PO)                      │
│  /us-generate {n} → workspace/output/us/{n}-{m}-{Name}.md (1 à 6 fichiers)│
│  [autonome, Sonnet 4.6]                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│       PHASE 2.5 — HTML mockups (humain dépose, optionnel)       │
│  Humain : déposer workspace/input/ui/{n}-{m}-{Name}.html                  │
│  [pas d'agent — l'HTML est lu directement par dev-frontend]     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 3 — ARCH + DB (agent Arch)                   │
│  /arch-init → init solution + projets vides                     │
│             + (si DatabaseType ≠ none) scaffolding Database-First│
│  [autonome, idempotent, READ-ONLY sur la base]                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│       PHASE 4 — CODE (workflow gated, depuis 2026-05-07)        │
│  /dev-run {n} :                                                 │
│    4a. arch + DB (idempotent)                                   │
│    4b. dev-backend ALL US (parallèle bornée par MaxParallel)    │
│    4c. QA API Gate (tests intégration HTTP, in-memory DB)       │
│        ├─ 🟢 GREEN → 4d                                         │
│        └─ 🔴 RED   → STOP, l'humain corrige et relance          │
│    4d. dev-frontend ALL US (parallèle bornée par MaxParallel)   │
│  cf. .claude/rules/backend-first.md                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              PHASE 5 — QA + Quality (agent QA, optionnel)       │
│  /qa-generate {n}     → workspace/output/qa/feat-{n}/...        │
│  (tests unitaires + coverage + quality scan)                    │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Flux complet

```
PHASE 1   /spec-generate {Nom}     → workspace/input/specs/{n}-{Name}.md
                                    + bootstrap workspace/output/context/constitution.md
   ↓
PHASE 1.5 /spec-deepen {n}          → SPEC enrichie + constitution §7
          [--quick]                   agent: elicitor
   ↓
PHASE 2   /us-generate {n}          → workspace/output/us/{n}-{m}-*.md
                                    + extension constitution §3
                                      agent: po
   ↓
PHASE 2.5 [humain dépose HTML]      → workspace/input/ui/{n}-{m}-*.html  (optionnel)
                                      pas d'agent — lecture directe par dev-frontend
   ↓
PHASE 2.6 /spec-validate {n}        → workspace/output/validation/{n}-readiness.md
                                      script: validate-readiness.ps1 (déterministe)
                                      (v6.0 : 100% déterministe, plus d'agent)
                                      Décision: 🟢 GO / 🟡 WARN / 🔴 NO-GO
   ↓
PHASE 2.7 /dev-plan {n}             → workspace/output/plans/{n}-{m}-*.{back,front}.md
          [si WARN/NO-GO + --force,   agents: dev-backend + dev-frontend (mode :plan)
           ou --plan, ou              checkpoint humain : ok | stop | retry
           PlanReviewDefault]
   ↓
PHASE 3   /arch-init                → workspace/output/src/{Apps}/  + ADRs
                                      agent: arch (Phase A bootstrap, B DB, C CLAUDE.md, D ADRs)
   ↓
PHASE 4   /dev-run {n} [--force]    → workspace/output/src/.../*.cs / *.razor / *.ts
          (gated, depuis 2026-05-07)  4a arch+DB → 4b dev-backend ALL → 4c API Gate
                                      → 4d dev-frontend ALL (uniquement si 4c GREEN)
                                      agents: dev-backend, qa (api-tests), dev-frontend

PHASE 5   /qa-generate {n} [--mode M]   → workspace/output/qa/feat-{n}/{report.md, coverage.json, quality.json}
                                      agent: qa + scripts: quality-scan.ps1 + parse-coverage.ps1
                                      (modes : full | tests-only | tests+coverage |
                                       quality-only | api-tests)
```

## 3. Orchestration

- `/us-generate {n}` exécute la phase 2 (US) avec récap des HTML déposés.
- `/dev-run {n}` enchaîne phases 3 → 4 : pré-step `arch` (idempotent,
  inclut le scaffolding DB) **avec short-circuit STEP 4.bis** (depuis
  2026-05-10) qui skippe l'invocation arch quand le bootstrap est
  stable (CLAUDE.md projet présents, `db/schema.json` présent si DB,
  `stack.md` non modifié) ; puis Dev-Backend + Dev-Frontend gated
  back→API gate→front. Forcer arch via `--rebuild-arch`.
- `/sdd-full {n}` = pipeline complet de A à Z (us-generate → spec-validate
  → dev-plan optionnel → arch → dev-run → qa-generate). Sur SPECs
  ≥ 2 (ou re-runs), l'étape arch est typiquement skippée par le
  short-circuit ci-dessus.

## 4. Historique BREAKING CHANGES

### v6.0.0 (token-lean, déterministe, gated)
- **Workflow gated back→API gate→front** (depuis 2026-05-07) : la
  phase 4 de `/dev-run` n'est plus parallèle back+front. Les agents
  s'enchaînent en séquence avec une **API Gate** (tests d'intégration
  HTTP automatisés via `WebApplicationFactory<Program>` + DB
  in-memory) entre les deux. Frontend non généré tant que la gate
  n'est pas 🟢 GREEN. Détail :
  `.claude/rules/backend-first.md`. Anciens default `GatedWorkflow:
  false` (legacy parallèle) disponible pour les projets simples.
- **Convention URL canonique backend** (depuis 2026-05-07) : tout
  endpoint doit suivre `/api/v{N}/{resource-kebab-case-pluriel}`
  (cf. `dotnet-minimalapi.md §2.6`). Pas de `/count`, `/exists` :
  total via `PagedOutput.TotalCount`, existence via 404 du GET by id.
- **Règle frontend strict** : interdiction d'inventer une route
  backend (cf. `responsibilities.md §12`). Avant tout client HTTP,
  l'agent grep le code backend pour vérifier la route + verbe.
- **Suppression de l'agent `validator`** : `/spec-validate` est désormais
  100% déterministe via PowerShell (`validate-readiness.ps1`). Économie
  ~1.4M tokens par `/sdd-full`. La review sémantique (AC vagues,
  ambiguïtés cross-artefact, hypothèses implicites) est désormais à la
  charge du PO humain lors de la relecture de la SPEC.
- **Section §2 « Validations sémantiques » retirée** du
  `readiness.template.md` (le rapport ne contient plus que les
  validations déterministes §1 + §3 erreurs + §4 warnings).
- **4 agents cœur + 2 support** (vs 5 cœur + 2 support en v5) : `po`,
  `arch`, `dev-backend`, `dev-frontend` (cœur) ; `elicitor`, `qa`
  (support).
- **Post-mortem auth/azure-ad (2026-05-07)** : section §5.1 du stack
  durcie avec deux nouveaux patterns :
  - Microsoft.Identity.Web : injecter via `AddInMemoryCollection` dans
    `IConfiguration` AVANT `AddMicrosoftIdentityWebApiAuthentication`
    (anti-pattern : `Configure<MicrosoftIdentityOptions>("AzureAd", …)`
    crée des named options jamais lues par le handler JwtBearer →
    `IDW10106` au runtime).
  - Séparation `AZ_AUDIENCES` (validation tokens entrants côté backend,
    multi-audiences cumulatives) vs `AZ_CLIENTID` (acquisition de
    scope côté SPA, audience unique = cette API). L'endpoint
    `/api/config/auth` ne doit JAMAIS dériver les scopes de
    `AZ_AUDIENCES` (sinon le SPA déclenche le consent admin sur les
    co-applications).

### v5.0.0 (token-lean)
- **Slim CLAUDE.md** : entry point réduit (~150 lignes) ; le détail
  des conventions, architecture, workflow est externalisé en
  `.claude/docs/{architecture,workflow,conventions}.md` chargés à la
  demande.
- **Inline Rules dans dev-* agents** : `responsibilities.md` et
  `stack-completeness.md` ne sont plus lus en STEP 3/4 ; leur substance
  opérationnelle est inlinée dans les agents `dev-backend` et
  `dev-frontend`. `constitution.md` et `INDEX.md` ADRs deviennent des
  reads conditionnels.
- **Détection capabilities externalisée** : `detect-capabilities.ps1`
  (workload déterministe, ~0 token LLM).
- **Audit log `--force`** : `workspace/output/.audit/force-bypass.log`
  trace tout bypass de readiness.

### v4.0.0 (depuis v3.2.0)
- **Suppression de l'agent UI et de la phase 3 (UI)** : les maquettes
  ne sont plus des PNG analysées par un agent intermédiaire mais des
  **fichiers HTML statiques** déposés directement dans
  `workspace/input/ui/{n}-{m}-{Name}.html`. L'agent `dev-frontend` lit l'HTML
  directement et le traduit vers le design system actif via le
  mapping §2 + §7 du stack UI.
- **Suppression de `workspace/output/ui/`** : plus de markdown UI intermédiaire.
- **Suppression de `/ui-generate`** : la commande disparaît.
- **Plus de fidelity pass multimodal** : la fidélité est garantie par
  lecture texte de l'HTML source (libellés, structure, classes,
  couleurs inline).

### Hérité v3
- **Constitution + ADRs** (P2) : `workspace/output/context/constitution.md` +
  `workspace/output/context/adrs/` partagés par tous les agents.
- **Implementation Readiness Gate** (P1) : `/spec-validate {n}` bloque
  `/dev-run` en cas de SPEC trouée. Bypass via `--force`.
- **Élicitation structurée** (P3, optionnelle) : `/spec-deepen {n}`
  enrichit la SPEC via 5 techniques (Pre-mortem, First Principles,
  Red Team, Stakeholder Mapping, Inversion).
