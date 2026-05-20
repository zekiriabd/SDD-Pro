# Audit Framework SDD_Pro v6.1.1 — Analyse complète (HISTORIQUE)

> ⚠️ **AUDIT HISTORIQUE — état du framework au 2026-05-15 (v6.1.1).**
>
> Au moment de la rédaction : 8 agents, 13 slash commands, 20 stacks.
> Aujourd'hui (v6.9.0) : **15 agents, 15 slash commands, 30 stacks (incl. 3 archi),
> MCP server livré**. Voir `@.claude/CHANGELOG.md` pour les évolutions v6.2 → v6.9.
>
> Ce document est conservé comme **référence d'architecture historique**
> (vision, modèles, discipline). Pour un état à jour, lancer un nouvel audit
> via `general-purpose` agent sur `.claude/` + `workspace/`.
>
> Audit exhaustif **du framework**, hors `workspace/output/` (artefacts projet).
> Date : 2026-05-15. Périmètre : `.claude/` + workflow + conventions + machinerie.

---

## 0. TL;DR

- **Vision** : framework Spec-Driven Development strict (FEAT fonctionnelle → User Stories → Code), agent-piloté, déterministe, anti-derive.
- **Surface** : 8 agents, 13 slash commands, 20 stacks (11 🟢 reference + 9 🟡 expérimentaux), 9 règles opérationnelles, 15 templates, ~5 900 LOC Python (stdlib pur 3.10+).
- **Modèles Claude** : Opus 4.7 (dev-*), Sonnet 4.6 (po/arch/qa/elicitor/constitutioner), Haiku 4.5 (dashboard).
- **Workflow** : 4 phases (Cadrage → Planification → Architecture → Code → QA) + gate manuelle v6.1 optionnelle.
- **Discipline structurante** : source-first (MD avant code), lecture sélective, idempotence, parallélisme borné (`MaxParallel: 3`), ownership de fichiers strict.

---

## 1. Vue d'ensemble & positionnement

### 1.1 Mission

Industrialiser le passage **spécification fonctionnelle → application en production** sans dérive, sans `snowflake project`, sans intervention non tracée. Toute décision est :
- **soit codée dans une source MD** (FEAT, US, stack, rule, agent) — reproductible cross-machine,
- **soit dans un ADR atomique** — tracée chronologiquement.

### 1.2 Trois grandes propriétés systémiques

| Propriété | Garantie par |
|---|---|
| **Reproductibilité** | Source-first (`source-first.md`) — code = cible, jamais source ; deux Tech Leads sur deux machines régénèrent un projet identique depuis les mêmes MD. |
| **Anti-derive** | Stack completeness (libs imposées §2.4) ; agents stateless ; lecture sélective stricte ; `[CLASS]` codes erreur unifiés. |
| **Robustesse industrielle** | File ownership matrix ; atomic ADR numbering (timestamp UTC) ; build loop borné ; QA gate API in-memory ; hooks Claude Code de garde-fou. |

### 1.3 Workspace layout

```
SDD_Pro/
├── .claude/                         ← FRAMEWORK (sources)
│   ├── CLAUDE.md                    ← slim entry point (~150L)
│   ├── agents/        (8 .md)       ← prompts agents
│   ├── commands/      (13 .md)      ← slash commands
│   ├── rules/         (9 .md)       ← règles opérationnelles
│   ├── stacks/        (20 .md + .libs.json)
│   ├── templates/     (15 fichiers)
│   ├── docs/          (4 .md)       ← architecture/workflow/conventions/quickstart
│   ├── python/        (~5 900 LOC)  ← scripts + hooks + tests
│   ├── loader.yml                   ← manifest reads/writes par agent
│   └── settings.json                ← permissions + hooks Claude Code
└── workspace/                       ← PROJET (artefacts, hors audit)
    ├── input/{feats,ui,stack}/
    └── output/{us,plans,src,qa,dashboard,.sys}/
```

---

## 2. Workflow & phases du pipeline

### 2.1 Vue macro

```
Phase 1    Cadrage      /feat-generate [Nom]                    → workspace/input/feats/{n}-{Name}.md
Phase 1.5  Élicitation  /feat-deepen {n} [--quick]              → append 5 sections + constitution §7
Phase 2    Planification /us-generate {n}                       → workspace/output/us/{n}-{m}-{Name}.md (×U)
Phase 2.6  Readiness    /feat-validate {n} [--json]             → workspace/output/.sys/.validation/{n}-readiness.md
Phase 3    Architecture /arch-init (auto par /dev-run, /sdd-full) → workspace/output/src/* (projets vides) + db/schema.*
Phase 3.5  Plan-then-review /dev-plan {n}                       → workspace/output/plans/{n}-{m}-*.{back|front}.md
Phase 4    Code         /dev-backend, /dev-frontend, /dev-run   → workspace/output/src/{BackendName|AppName}/*
Phase 4b   API Gate     QA mode api-tests (auto par /dev-run)   → workspace/output/qa/feat-{n}/api-tests.{md,json}
Phase 5    QA           /qa-generate {n}                        → tests unitaires + coverage + quality
Rendu      Doc          /doc-refresh (auto fin pipeline)        → dashboard/README.html + INDEX.md ADRs + QA dashboards
Diagnostic              /sdd-status [{n}]                       → lecture seule, arbre ASCII
```

### 2.2 Orchestration `/sdd-full` (pipeline complet)

```
STEP 1.quart : init state.json + events.jsonl (observabilité, --resume)
STEP 2       : /us-generate
STEP 3.bis   : 🚪 manual gate `afterUS` (opt, --manual-gates=us)
STEP 3.5     : /feat-validate → GO|WARN|NO-GO
STEP 3.5.bis : 🚪 manual gate `afterReadiness`
STEP 3.6     : /dev-plan (conditionnel : --plan OU WARN sans --no-plan-on-warn)
STEP 3.6.bis : 🚪 manual gate `afterPlan`
STEP 3.7     : audit log si --force bypass
STEP 4       : /dev-run {n}
  4.bis      : 🚪 manual gate `afterCode`
  4.5        : /qa-generate {n} (sauf QAMode = off/manual)
  4.7        : /doc-refresh (auto, agent dashboard Haiku 4.5)
STEP 5       : récap consolidé + state.py end-run
```

### 2.3 Orchestration `/dev-run` (backbone exécution, **backend-first gated** v6.1)

```
STEP 1     : valider {n} + flags
STEP 1.5   : check readiness rapport (NO-GO bloque sauf --force)
STEP 2     : lister US à matérialiser
STEP 3     : vérifier stacks actifs
STEP 4     : valider DB/Auth dans stack.md
STEP 4.bis : détecter short-circuit arch (FEATs ≥ 2, mtime cohérent)
STEP 5     : /arch-init (agent arch, conditionnel)
STEP 6     : ⚡ workflow gated (LOAD-BEARING v6.1)
  6.0      : détecter plans existants (From-Plan mode)
  6.a      : dev-backend ×U en batches MaxParallel
  6.b      : qa mode api-tests (HTTP gate in-memory)
  6.c      : dev-frontend ×U en batches SI 6.b GREEN/YELLOW
STEP 6.5   : /doc-refresh auto
STEP 7     : récap final
```

**v6.1 LOAD-BEARING** : back+front **ne tournent plus en parallèle** ; séquence stricte avec API Gate au milieu. Tout mismatch contrat = `4xx/5xx` détecté avant qu'on génère le frontend.

### 2.4 Conventions de nommage cross-fichiers

```
{n}-{m}-{Name}  // basename identique sur TOUS les artefacts d'une US
```

| Artefact | Path |
|---|---|
| Mockup HTML (UX humain) | `workspace/input/ui/{n}-{m}-{Name}.html` (optionnel, passif) |
| User Story | `workspace/output/us/{n}-{m}-{Name}.md` |
| Plan | `workspace/output/plans/{n}-{m}-{Name}.{back\|front}.md` |
| Code | `workspace/output/src/{BackendName\|AppName\|LibName}/...` |

Permet la **lecture sélective** : `dev-frontend 1-2` lit *uniquement* `workspace/output/us/1-2-*.md` + `workspace/input/ui/1-2-*.html`.

### 2.5 IDs stables (critique)

Bullets de `## Functional Needs` et `## Functional Deliverables` portent `SFD-N` et `FD-N`. **Jamais renumérotés** après génération US. Idem `BR-N`, `AC-N`.

---

## 3. Système agentique (8 agents)

### 3.1 Synthèse

| Agent | Modèle | Phase | Rôle | Déclencheur | Parallélisable |
|---|---|---|---|---|---|
| **po** | Sonnet 4.6 | 2 | FEAT → User Stories (cible 1-3, cap 6) | `/us-generate {n}` | Non (1 FEAT) |
| **arch** | Sonnet 4.6 | 3 | Bootstrap projets vides + DB schema + CLAUDE.md per-project | `/arch-init` (auto par /dev-run, /sdd-full) | Non (projet-level) |
| **dev-backend** | Opus 4.7 | 4 | Code serveur 1 US (Services, Endpoints, DTOs, Entities) | `/dev-backend {n}-{m}[:plan]` | OUI (batchs `MaxParallel`) |
| **dev-frontend** | Opus 4.7 | 4 | Code client 1 US + traduction HTML→DS + fidelity check | `/dev-frontend {n}-{m}[:plan]` | OUI (batchs `MaxParallel`) |
| **qa** | Sonnet 4.6 | 5 | Tests unitaires + coverage parse + quality scan + API gate | `/qa-generate {n}` (auto api-tests par /dev-run) | Non (1 FEAT) |
| **elicitor** | Sonnet 4.6 | 1.5 | 5 techniques élicitation (Pre-mortem, Red Team, First Principles, Stakeholder, Inversion) | `/feat-deepen {n} [--quick]` | Non (1 FEAT) |
| **constitutioner** | Sonnet 4.6 | 3.5 | ADRs atomiques + edit constitution §4 §6 §1 | Auto-invoqué par arch STEP 12.5 | Non (sérialisé) |
| **dashboard** | Haiku 4.5 ⭐ | rendu | README.html + INDEX.md ADRs + QA dashboards HTML (déterministe, 0 raisonnement) | Auto fin pipeline + `/doc-refresh` | Idempotent global |

### 3.2 Détail par agent

#### 3.2.1 `po` (Product Owner)

- **Reads** : `workspace/input/feats/{n}-*.md` + `constitution.md` (optionnel).
- **Writes** : `workspace/output/us/{n}-{m}-*.md` (×U) + append `constitution.md §3` (acteurs).
- **STEPs** : 1. context budget → 2. localise FEAT → 3. extrait IDs stables → 4. découpe par flux utilisateur (cible 1-3) → 5. traçabilité 100% (tous SFD/BR/AC/FD couverts) → 6. anti-patterns (refus US techniques/par couche) → 7. écrit US → 8. étend `constitution §3` (procédure hardenée v3.1.3 : placeholder detection + read-back validation) → 9. confirmation 1L.
- **Exit codes critiques** : `[GRANULARITY_VIOLATION]` (>6 US), `[TRACEABILITY_GAP]`, `[STATUS_FLIP_FAILED]`.
- **Inline rules** : `us-granularity.md`, `constitution.md §3`.

#### 3.2.2 `arch` (Architecte)

- **Reads** : `workspace/input/stack/stack.md` + stacks actifs `.claude/stacks/{cat}/*.md` + `.libs.json` catalogues + `constitution.md`.
- **Writes** : projets vides (`{BackendName}.csproj`, `package.json`, etc.) + `.sln` + configs propagées (appsettings.json, application.yml, app/config.py) + `workspace/output/db/{schema.json,schema.md,schema.diff.md}` + entities scaffoldées (Database-First) + `CLAUDE.md` par projet (back/front/lib).
- **STEPs clés** : Phase A (bootstrap projets, idempotent skip si .csproj existe) + Phase B (introspection DB READ-ONLY, connection string en RAM, scaffolding entities) + Phase C (CLAUDE.md per-project + délégation à constitutioner).
- **Particularités** :
  - Strictement READ-ONLY DB.
  - Connection string en RAM (jamais persistée fichier).
  - Versioning schema avec diff.
  - Externalisation ADRs vers `constitutioner` (évite race condition).

#### 3.2.3 `dev-backend` (développeur serveur)

- **Reads** : 1 US (`workspace/output/us/{n}-{m}-*.md`) + `workspace/output/src/{BackendName}/CLAUDE.md` + `workspace/output/db/schema.json` (si présent) + mockup HTML (passif, contexte UI uniquement) + stacks backend + auth actifs.
- **Writes** : Services, Endpoints, DTOs, Mappers, Entities, Program.cs (augment) sous `workspace/output/src/{BackendName}/*`.
- **STEPs clés** :
  1. Preflight HARD-GATE (script `preflight.py` — A1-A4 args, B1-B5 stacks)
  2. Context budget (`context_budget.py`)
  3. Détection mode (Normal / Plan Only `:plan` / From Plan)
  4. Path safety (isolation front/back, cf. `file-ownership.md §1.bis`)
  5. Plan inline OU consommation `.back.md`
  6. Capability detection (`detect_capabilities.py`, grep US/HTML vs triggers regex `.libs.json §onDemand`)
  7. Génération code (create / augment-with-preserves/adds)
  8. Build loop (max `BuildLoopMaxIter`, exit 0 requis ; classes `[BUILD_CORRECTIBLE]` retry, `[BUILD_BLOCKING]` fail-fast)
  9. Cleanup `## BREAKING CHANGES` post-build (`mark_breaking_resolved.py`)
- **Exit silencieux** si US frontend-only.

#### 3.2.4 `dev-frontend` (développeur client)

- **Triple source de vérité** : US (workflow) + HTML mockup (libellés verbatim, structure, couleurs, **texte direct**, pas vision multimodale) + stack UI (mapping vers composants DS).
- **Reads** : 1 US + 1 HTML + CLAUDE.md frontend + stacks ui/auth.
- **Writes** : Pages, Components, Layouts, theme.css, bootstrap HTML sous `workspace/output/src/{AppName}/*`.
- **STEPs spécifiques** :
  - Parse HTML mockup → mapping vers composants DS natifs (jamais copier-coller HTML brut).
  - Fidelity check post-build (`validate_fidelity.py` : libellés exacts, hex tolerance, composants attendus).
  - Assets non-icônes → placeholders `data-ui-asset`.
- **Exit silencieux** si US backend-only.

#### 3.2.5 `qa` (Quality Assurance)

- **Modes** (`QAMode` dans Project Config) : `off | quality-only | tests-only | tests+coverage | full | manual` (défaut).
- **Mode spécial `api-tests`** : invoqué par `/dev-run` STEP 6.b — tests d'intégration HTTP in-memory (WebApplicationFactory + EF InMemory / supertest + Prisma SQLite / httpx.AsyncClient + SQLAlchemy SQLite / MockMvc + H2). Auth JWT mocké (TestAuthHandler). **Jamais Azure AD réel ni DB réelle**.
- **Writes** : tests sous `*.Tests/Api/` ou `Unit/` (ownership exclusif QA, dev-* INTERDITS) + `coverage.json` (parse via `parse_coverage.py`, schéma normalisé cross-stack) + `quality.json` + `report.md`.
- **Critère API Gate** : `gate_passed = (failed == 0) AND (total >= MIN_PER_ENDPOINT × N_endpoints)` avec `MIN_PER_ENDPOINT = 2`.
- **v6.1 hardening** : `coverage_lines_pct < CoverageMin` → **RED bloquant** (auparavant WARN). Bypass = baisser `CoverageMin` ou `CoverageMin: 0`, jamais `--force`.

#### 3.2.6 `elicitor` (Élicitation avancée)

- **5 techniques** : Pre-mortem (FAIL-N), First Principles, Red Team, Stakeholder Mapping (STK-N), Inversion. + Risques (RISK-N), Hypothèses (ASS-N), Cas Limites (EDGE-N).
- **Modes** : interactif (5 séries de 1-2 questions) vs `--quick` (inférence directe).
- **Writes** : append 5 sections fin FEAT + edit `constitution §7`.
- **Footprint** : ~10-15 KB interactif, ~5-8 KB quick.

#### 3.2.7 `constitutioner` (sub-agent d'arch)

- **Délégué par arch** Phase B (évite race condition sur §6 ADRs).
- **Writes** : `workspace/output/.sys/.context/adrs/ADR-{YYYYMMDDTHHmmss}-{slug}.md` (timestamp atomique UTC, en cas de collision `-{rand4}`) + edit constitution `§1` (date), `§4` (stack final), `§6` (ADRs index).
- **Hardening v5.0** : read-back validation obligatoire (placeholder ≠ résiduel, dates cohérentes, dimensions présentes). Bug pvlist v3.1.2 → constitution restée avec `<à compléter>`.

#### 3.2.8 `dashboard` (rendu HTML, Haiku 4.5)

- **Particularité** : **aucun raisonnement**, pure injection template + JSON parsé. Haiku 4.5 (10× moins cher que Sonnet).
- **Writes** : `workspace/output/dashboard/README.html` + `workspace/output/.sys/.context/adrs/INDEX.md` (rebuild from globs) + `workspace/output/qa/feat-{n}/dashboard.html` (par feature).
- **Graceful degradation** : un output manquant ≠ STOP, juste WARN.

---

## 4. Slash commands (13 commandes)

### 4.1 Table de référence

| Commande | Phase | Args | Agent invoqué | Scripts Python | Idempotent |
|---|---|---|---|---|---|
| `/feat-generate [Nom]` | 1 | `Nom?` | — | — | Non (création) |
| `/feat-deepen {n} [--quick]` | 1.5 | `{n}`, `--quick` | `elicitor` | — | Oui (append) |
| `/us-generate {n}` | 2 | `{n}` | `po` | — | Oui |
| `/feat-validate {n} [--json]` | 2.6 | `{n}`, `--json` | — | `validate_readiness.py`, `validate_semantic.py` | Oui |
| `/arch-init` | 3 | — | `arch` | — | Oui (skip si stable) |
| `/dev-plan {n}` | 3.5 | `{n}` | `dev-backend:plan` + `dev-frontend:plan` (×U // borné) | `compact_front_plans.py` | Oui |
| `/dev-backend {n}-{m}[:plan]` | 4 | `{n}-{m}`, `:plan` | `dev-backend` | `preflight.py` (HARD-GATE) | Oui |
| `/dev-frontend {n}-{m}[:plan]` | 4 | `{n}-{m}`, `:plan` | `dev-frontend` | `preflight.py`, `validate_fidelity.py` | Oui |
| `/dev-run {n}` | 3→4 | `{n}`, `--force`, `--max-parallel N`, `--rebuild-arch` | `arch` → `dev-backend` ×U → `qa` (api-tests) → `dev-frontend` ×U → `dashboard` | `detect_arch_shortcircuit.py` | Oui |
| `/sdd-full {n}` | 2→5 | `{n}` + 7 flags | (tous via délégation slash) | `sdd_state.py`, `gate_decide.py` | Oui (`--resume`) |
| `/qa-generate {n}` | 5 | `{n}`, `--mode M`, `--filter` | `qa` | `quality_scan.py`, `parse_coverage.py` | Oui |
| `/sdd-status [{n}]` | diag | `{n}?` | — | — (lecture seule) | Oui |
| `/doc-refresh` | rendu | — | `dashboard` | — | Oui |

### 4.2 Flags critiques de `/sdd-full`

| Flag | Effet |
|---|---|
| `--plan` | Force `/dev-plan` même sur readiness GO (opt-in review) |
| `--force` | Bypass NO-GO readiness → passe par plan-review obligatoirement |
| `--no-plan-on-warn` | Escape hatch (déconseillé) — skip plan-review sur WARN |
| `--no-validate` | Bypass `/feat-validate` (legacy) |
| `--rebuild-arch` | Force agent arch (non short-circuit, chg DB schema, ajout lib) |
| `--manual-gates[=us,readiness,plan,code]` | v6.1 — active 1-4 gates manuels (console web `workspace/console/` ou chat legacy) |
| `--no-manual-gates` | Désactive tous les gates manuels |
| `--resume` | Reprend après gate en attente (status `pending`) |

### 4.3 Détection short-circuit arch (`detect_arch_shortcircuit.py`)

Skip `arch` Phase A+B si **toutes** conditions vraies sur FEAT ≥ 2 :
- projet existe (`*.csproj`/`package.json`/`pyproject.toml`/`build.gradle.kts`)
- `CLAUDE.md` projet existe
- `schema.json` existe (si DB active)
- `mtime` des sources ≤ `mtime` du build artifact
- pas de flag `--rebuild-arch`

---

## 5. Système de stacks (20 stacks + catalogues `.libs.json`)

### 5.1 Inventaire

| Catégorie | Stacks | Validation |
|---|---|---|
| **Backend (4)** | dotnet-minimalapi, kotlin-spring-boot, node-express, python-fastapi | 🟢 dotnet, kotlin / 🟡 node, python |
| **Frontend (4)** | react, blazor-webassembly, angular, vue | 🟢 react, blazor / 🟡 angular, vue |
| **UI Design Systems (3)** | shadcn (React), radzen-blazor (Blazor), vuetify (Vue) | 🟢 shadcn, radzen / 🟡 vuetify |
| **Auth (2)** | azure-ad, auth-local | 🟢 azure-ad / 🟡 auth-local |
| **QA (7)** | dotnet-xunit, blazor-bunit, kotlin-junit, node-vitest, angular-jasmine, python-pytest, code-quality | 🟢 dotnet-xunit, blazor-bunit, kotlin-junit, node-vitest / 🟡 angular-jasmine, python-pytest |

### 5.2 Combos validés end-to-end (🟢 reference)

**Combo 1 — .NET Full Stack** :
- Backend : `dotnet-minimalapi`
- Frontend : `blazor-webassembly`
- UI : `radzen-blazor`
- Auth : `azure-ad`
- QA : `dotnet-xunit` + `blazor-bunit`

**Combo 2 — Kotlin + React + shadcn (CMS)** :
- Backend : `kotlin-spring-boot`
- Frontend : `react`
- UI : `shadcn`
- Auth : `azure-ad`
- QA : `kotlin-junit` + `node-vitest`

> **Aucun combo .NET + React validé** à ce jour. Azure AD reste la seule auth 🟢 référence (2 combos).

### 5.3 Format `.libs.json` (source de vérité machine)

```json
{
  "stackId": "dotnet-minimalapi",
  "category": "backend",
  "schemaVersion": 1,
  "buildSystem": "dotnet",
  "manifest": { "files": ["workspace/output/src/{BackendName}/{BackendName}.csproj"] },
  "versions": { "ef-core": "10.0.6", "automapper": "16.1.1" },
  "dbDrivers": { "sqlserver": { "module": "Microsoft.EntityFrameworkCore.SqlServer", "ref": "ef-core" } },
  "core": [
    { "module": "Microsoft.EntityFrameworkCore", "ref": "ef-core", "rationale": "ORM" }
  ],
  "onDemand": [
    {
      "module": "EPPlus",
      "ref": "epplus",
      "capability": "excel",
      "triggers": ["\\bexcel\\b", "\\.xlsx\\b", "export.*excel"]
    }
  ],
  "plugins": [ ... ]
}
```

- **CORE** : installé inconditionnellement par `arch` Phase A.
- **ON-DEMAND** : installé par `dev-backend` STEP 5.bis si US/HTML matchent un `trigger` regex (script `detect_capabilities.py`).
- **Overrides** Project Config : `Capabilities: excel, pdf` force install, `## Capabilities Override` permet alternative (ex. `excel: closedxml` au lieu de EPPlus).
- **Schéma** : `.claude/templates/libs-catalog.schema.json` (JSON Schema 2020-12).
- **Tools admin** : `validate_libs_catalog.py` (validation schéma), `sync_stack_md.py` (régénère §2.4 du .md depuis JSON).

### 5.4 Sections obligatoires des stack `.md`

| Section | Backend | Frontend | UI | Auth | QA |
|---|---|---|---|---|---|
| §1 Architecture (pattern applicatif + couches) | ✓ | ✓ | — | — | ✓ |
| §1.3 Mapping couche → répertoire | ✓ | ✓ | ✓ | — | ✓ |
| §2.2.1 Init Commands (idempotentes) | ✓ | ✓ | ✓ | — | ✓ |
| §2.4 Librairies (CORE + ON-DEMAND) | ✓ | ✓ | ✓ | — | ✓ |
| §3 Database / Conventions applicatives | ✓ | ✓ | ✓ | — | — |
| §5+ Conventions URLs dev / Auth specs / Anti-patterns | ✓ | ✓ | ✓ | ✓ | ✓ |

### 5.5 Capabilities on-demand fréquentes

| Capability | Triggers regex (extrait) | Libs par stack |
|---|---|---|
| `excel` | `\bexcel\b`, `\.xlsx\b`, `export.*excel` | EPPlus/ClosedXML (.NET), ExcelJS (Node), Openpyxl (Python) |
| `pdf` | `\bpdf\b`, `\.pdf\b`, `generer.*pdf` | QuestPDF/iText7 (.NET), PDFKit (Node), ReportLab (Python) |
| `redis-cache` | `\bredis\b`, `distributed cache` | StackExchange.Redis (.NET), redis-py (Python) |
| `cqrs` | `\bcqrs\b`, `mediatr`, `command.*handler` | MediatR (.NET) |
| `auth-azure-ad` | `azure ad`, `msal`, `sso`, `oauth2.*spa` | MSAL.js + MSAL React (frontend), Microsoft.Identity.Web (.NET), spring-security-oauth2-resource-server (Kotlin) |
| `auth-local` | `auth-local`, `jwt`, `hash.*password` | bcryptjs+jsonwebtoken (Node), passlib+python-jose (Python), MailKit (.NET pour reset email) |
| `email` | `\bsmtp\b`, `mail.*confirmation` | MailKit+MimeKit (.NET, depuis v6.1, remplace SmtpClient deprecated) |

### 5.6 Politique runtime LTS (depuis v6.1, fusion `library-policy.md`)

Stacks utilisent **uniquement runtimes LTS**. STS/prerelease interdites en prod.

| Plateforme | LTS courant | Fin support |
|---|---|---|
| .NET | 10 (Nov 2025) | Nov 2028 |
| Node.js | 22 "Jod" (Oct 2024) | Apr 2027 |
| Java | 21 (Sep 2023) | Sep 2028 |
| Python | 3.12 (Oct 2023) | Oct 2028 |
| Kotlin | 2.1 LTS (2025) | TBD |

Bypass STS = ADR `runtime-sts-exception` + `RuntimeException:` dans Project Config → WARN `[RUNTIME_STS_EXCEPTION]`.

### 5.7 Registries canoniques + CVE check

Forks/mirrors interdits. Registries autorisés : NuGet (api.nuget.org), npm (registry.npmjs.org), PyPI (pypi.org), Maven Central, Gradle plugins portal.

**Post-install vérification** :
- `dotnet list package --vulnerable --include-transitive`
- `npm audit --omit=dev --audit-level=moderate`
- `pip-audit`
- `mvn dependency:check` (OWASP)

---

## 6. Règles (`.claude/rules/`) — 9 règles

| Règle | Rôle | Substance inlinée dans |
|---|---|---|
| **backend-first.md** | Gated workflow (back → API gate → front), v6.1 obligatoire | `commands/dev-run.md`, `agents/qa.md` |
| **constitution.md** | Procédure §1-§8 + ADR timestamp atomique | `agents/po.md` §3, `agents/arch.md`, `agents/constitutioner.md` |
| **dev-shared.md** | Patterns partagés dev-backend/dev-frontend (preflight, path safety, capability detection, plan construction) | `agents/dev-backend.md`, `agents/dev-frontend.md` |
| **error-classification.md** | Taxonomie complète des `[CLASS]` codes (Runtime, Pipeline, Contrat, Build, Anti-derive, UI, QA, Parallélisme) | tous agents + scripts |
| **file-ownership.md** | Matrice ownership + isolation front/back §1.bis + lock LibName §4 | tous agents qui écrivent |
| **qa-coverage.md** | Schéma `coverage.json` cross-stack + seuil bloquant v6.1 | `agents/qa.md` |
| **source-first.md** | "Code = cible, jamais source" → tout bug = trou MD à patcher | mental discipline cross-agent |
| **stack-completeness.md** | Libs hors §2.4 → STOP + ERROR ; capabilities core vs on-demand | `agents/dev-*`, `agents/arch.md` |
| **us-granularity.md** | Cible 1-3 US / WARN 4-6 / cap 6 + anti-patterns (US technique, par couche, fallback) | `agents/po.md` |

### 6.1 Classes erreur unifiées (`error-classification.md`)

Toute erreur préfixe `[CLASS]` dans `CAUSE:` du bloc ERROR 3 lignes. Permet à `build_loop`, hooks et dashboards de décider mécaniquement (pas d'interprétation LLM).

**Catégories principales** :
- **Runtime** : `[NETWORK]`, `[AUTH]`, `[PERMISSION]`, `[NOT_FOUND]`, `[TIMEOUT]`, `[DISK]`, `[ENV_MISSING]`, `[ENV_PROPAGATION_FAILED]`
- **Pipeline** : `[STACK_MALFORMED]`, `[SCHEMA_MISMATCH]`, `[FEAT_REJECTED]`, `[FEAT_NOT_FOUND]`, `[GRANULARITY_VIOLATION]`, `[TRACEABILITY_GAP]`, `[READINESS_NO_GO]`
- **Contrat** : `[PRESERVES_VIOLATED]`, `[ADDS_VIOLATED]`, `[LAYER_VIOLATION]`, `[FILE_OWNERSHIP]`, `[FILE_OWNERSHIP_NESTED]`, `[STATUS_FLIP_FAILED]`
- **Build** : `[BUILD_CORRECTIBLE]` (retry), `[BUILD_BLOCKING]` (fail-fast), `[DEP_MISSING]`, `[CIRCULAR_DEP]`
- **Anti-derive** : `[DERIVE_VIOLATION]`, `[REFACTOR_HORS_SCOPE]`, `[OPTIMIZATION_PROACTIVE]`, `[UNDECLARED_DECISION]`, `[STACK_LIBRARY_MISSING]`, `[STACK_LIBRARY_VULNERABLE]`
- **UI** : `[UI_FIDELITY_GAP]`, `[UI_TOKEN_VIOLATION]`, `[FRONTEND_BACKEND_CONTRACT_GAP]`
- **QA** : `[QA_TEST_FAILED]`, `[QA_COVERAGE_GAP]`, `[QA_FRAMEWORK_MISSING]`, `[QA_INIT_FAILED]`, `[QA_TEST_INVALID]`, `[QA_OUTPUT_INVALID]`, `[QA_PRECONDITION_FAILED]`, `[QA_OWNERSHIP_VIOLATION]`, `[API_GATE_RED]`
- **Parallélisme** : `[LIBNAME_LOCK_HELD]`, `[LIBNAME_SIGNATURE_CONFLICT]`
- **Inconnu** : `[UNKNOWN]`

### 6.2 File ownership matrix (extrait)

| Fichier / répertoire | Owner | Mode |
|---|---|---|
| `workspace/output/src/{BackendName}/**` | `dev-backend` | Edit-augment exclusif |
| `workspace/output/src/{AppName}/**` | `dev-frontend` | Edit-augment exclusif |
| `workspace/output/src/{AppName}.sln` | `arch` | Create + add-project |
| `workspace/output/src/{LibName}/**` | `arch` (création) + `dev-*` (via lock §4) | First-write wins + lock |
| `workspace/output/db/schema.{json,md,diff.md}` | `arch` | Create exclusif |
| `workspace/output/.sys/.context/constitution.md` | Séquentiel (feat-gen → po → arch → elicitor) | Append-only par section |
| `workspace/output/.sys/.context/adrs/ADR-*.md` | Multi-writers | Numérotation atomique timestamp |
| `workspace/output/us/{n}-{m}-*.md` | `po` | Create exclusif |
| `workspace/input/ui/{n}-{m}-*.html` | UX humain | Read-only stricte agents |
| `workspace/console/status.json` | console + sdd-full (via `gate_decide.py`) | Atomic write + lock `.status.lock` (TTL 10s) |
| `workspace/output/dashboard/README.html` | `dashboard` | Create overwrite |

### 6.3 Anti-pattern isolation front/back (§1.bis, post-mortem CMS-Back)

```
✓ workspace/output/src/{BackendName}/         AU MÊME NIVEAU
✓ workspace/output/src/{AppName}/
✓ workspace/output/src/{LibName}/

✗ workspace/output/src/{BackendName}/{AppName}/         INTERDIT
✗ workspace/output/src/{BackendName}/Kotlin/{AppName}/  INTERDIT
✗ workspace/output/src/{BackendName}/front/             INTERDIT
```

Violation → STOP + ERROR `[FILE_OWNERSHIP_NESTED]`.

### 6.4 LibName lock (§4, durci v5.0)

Avant tout Write/Edit sous `{LibName}/` :
1. `mkdir -p workspace/output/src/{LibName}/.locks` puis `set -C; echo > {Entity}.lock`
2. Succès → écrire, puis `rm` du lock
3. Échec → lire AGENT_ID :
   - Même agent → continuer (idempotent)
   - Autre → STOP `[LIBNAME_LOCK_HELD]`
4. Stale lock > 30min → écrasé (recovery)

Conflit signature (post-lock) → STOP `[LIBNAME_SIGNATURE_CONFLICT]`.

---

## 7. Machinerie Python (~5 900 LOC, stdlib pur 3.10+)

### 7.1 Arborescence

```
.claude/python/
├── _hook.py                            ← Launcher cwd-independent (49 LOC)
├── pyproject.toml                      ← name: sdd-pro-tools, deps: pytest (dev)
├── README.md                           ← migration 100% Python terminée
├── sdd_lib/         (6 modules, 277 LOC)   ← helpers partagés
├── sdd_hooks/       (4 hooks, 827 LOC)     ← Claude Code events
├── sdd_scripts/     (15 scripts, 1 887 LOC) ← agent-invoked
├── sdd_admin/       (6 outils, 1 468 LOC)  ← Tech Lead tools (opt-in)
└── tests/           (5 fichiers, ~400 LOC) ← unit tests pytest
```

### 7.2 `sdd_lib/` (helpers partagés)

| Module | Rôle | Exports clés |
|---|---|---|
| `hook_input.py` | Parse stdin JSON hooks + regex fallback | `read_hook_input()`, `get_file_path()`, `get_subagent_type()` |
| `paths.py` | Repo root + normalize cross-platform | `repo_root()`, `normalize()`, `iso_now()`, `iso_now_ms()` |
| `stderr.py` | Format ERROR/CAUSE/FIX canonique | `warn()`, `error_block()` |
| `project_config.py` | Parse `workspace/input/stack/stack.md` sections | `section_body()` |
| `loader_yml.py` | Parse `.claude/loader.yml` blocs reads/writes | (réf architecture) |
| `file_locks.py` | Atomic file locks cross-language Node↔Python | `acquire_with_retry()`, `release()` (TTL 10s, backoff 50ms) |

### 7.3 `sdd_hooks/` (4 hooks Claude Code)

| Hook | Événement | Matcher | Rôle | Bloquant |
|---|---|---|---|---|
| `protect_framework.py` | PreToolUse | Edit\|Write\|MultiEdit | WARN si agent modifie `.claude/*/` | Non |
| `preflight_agent_budget.py` | PreToolUse | Agent | Ledger contexte tokens avant sub-agent (env `SDD_BUDGET_MODE`: off/warn/strict) | exit 2 si strict |
| `validate_augment_contract.py` | PostToolUse | Edit\|Write\|MultiEdit | Vérifie contrats `preserves:`/`adds:` du plan (déterministe, regex YAML + grep file) | **OUI** (exit 2) |
| `audit_file_ownership.py` | SubagentStop | dev-backend\|dev-frontend\|qa\|dashboard | Audit matrice ownership post-dispatch (append-only log) | Non |
| `framework_smoke.py --strict --silent-on-pass` | Stop | (tous) | Smoke test framework + cache 5min | Non |

### 7.4 `sdd_scripts/` (15 scripts agent-invoked)

| Script | Invocateur | Phase | Rôle | Tests |
|---|---|---|---|---|
| `acquire_libname_lock.py` | dev-backend, dev-frontend | 3.5 | Lock entité LibName partagée | ✅ |
| `compact_front_plans.py` | dev-frontend | 4 | Compresse plans inline > 12 KB | ❌ |
| `context_budget.py` | hooks + dev-* | 2 | Ledger tokens reads/writes (JSONL) | ❌ |
| `detect_arch_shortcircuit.py` | /dev-run STEP 4.bis | 3.5 | Détecte si arch peut être skippé | ❌ |
| `detect_capabilities.py` | dev-backend STEP 5.bis | 3 | Match triggers regex `.libs.json §onDemand` vs US/HTML | ❌ |
| `gate_decide.py` | /sdd-full gates + console web | 4 | Atomic read/write `workspace/console/status.json` (cross-lang lock) | ✅ |
| `mark_breaking_resolved.py` | dev-backend STEP 8.5, dev-frontend STEP 11.5 | 4 | Marque `## BREAKING CHANGES — RESOLVED {date}` (⚠ exit 1 = succès, non-standard) | ❌ |
| `parse_coverage.py` | qa STEP 4 | 5 | Parse XML coverage (xunit/pytest/jacoco/opencover) → `coverage.json` normalisé | ✅ |
| `preflight.py` | dev-backend, dev-frontend | 3.5 | HARD-GATE A1-A4 (args) + B1-B5 (stacks/AppName/CLAUDE.md) | ❌ |
| `quality_scan.py` | qa STEP 5 | 5 | Scan statique (TODO, magic numbers, console.log, long methods) | ❌ |
| `sdd_state.py` | /sdd-full | 2 | Génère `workspace/output/.sys/.state/state.jsonl` events log | ❌ |
| `validate_fidelity.py` | dev-frontend STEP 11 | 4 | Extrait libellés HTML, grep markup généré | ❌ |
| `validate_inline_rules.py` | /sdd-status | 5 | Vérifie inlining rules dans agents match source (drift detection) | ❌ |
| `validate_readiness.py` | /feat-validate | 2.6 | 13 tests déterministes (IDs, US↔HTML, stack, DB, auth, complexité, deepen check) | ✅ |
| `validate_semantic.py` | /feat-validate phase 2 | 2.6 | Mots vagues, security gaps, PII, ACs mesurables | ❌ |

### 7.5 `sdd_admin/` (6 outils Tech Lead, opt-in)

| Outil | Rôle | Quand utiliser |
|---|---|---|
| `framework_smoke.py` | Smoke test framework (agents, rules, templates, stacks, scripts) + cache 5min + fingerprint SHA1 | Avant release, après refactor profond |
| `init_status_json.py` | Bootstrap initial `workspace/console/status.json` | 1×/projet (setup console web) |
| `measure_batch.py` | Mesure tokens/durée série de runs → CSV | Audit perf |
| `strip_bom.py` | Nettoie BOM UTF-16 sur fichiers générés | Post-gen si drift encoding |
| `sync_stack_md.py` | Régénère §2.4 du `.md` depuis `.libs.json` | Après édition catalogue |
| `validate_libs_catalog.py` | Valide `.libs.json` vs schéma + cohérence (versionRef, capability/triggers) | Après édition catalogue |

### 7.6 Tests unitaires

| Test | Cible | Couverture |
|---|---|---|
| `test_acquire_libname_lock.py` | `acquire_libname_lock.py` | Lock timeout, concurrent acquire, cleanup |
| `test_gate_decide.py` | `gate_decide.py` | read/pose-pending/set/is-resolved, file sync, JSON output |
| `test_parse_coverage.py` | `parse_coverage.py` | xunit/pytest/jacoco XML parsing, edge cases |
| `test_validate_augment_contract.py` | `validate_augment_contract.py` | YAML block parsing, preserves/adds violation |
| `test_validate_readiness.py` | `validate_readiness.py` | 13 règles validation, ID sequence, traçabilité, stack, DB, auth |

---

## 8. Templates (`.claude/templates/`, 15 fichiers)

| Template | Format | Usage / généré par |
|---|---|---|
| `feat.template.md` | MD | FEAT fonctionnelle — `/feat-generate` |
| `us.template.md` | MD | User Story — agent `po` |
| `adr.template.md` | MD | ADR — agents `arch`, `constitutioner`, `dev-*` |
| `constitution.template.md` | MD | Constitution projet (§1-§8) — `/feat-generate` bootstrap |
| `readiness.template.md` | MD | Rapport Implementation Readiness — `/feat-validate` |
| `risks-assumptions.template.md` | MD | Élicitation 5 techniques — agent `elicitor` |
| `claude-md-backend.template.md` | MD | CLAUDE.md per-project backend — agent `arch` |
| `claude-md-frontend.template.md` | MD | CLAUDE.md per-project frontend — agent `arch` |
| `claude-md-shared-lib.template.md` | MD | CLAUDE.md lib partagée (si `LibStrategy=shared`) — agent `arch` |
| `qa-report.template.md` | MD | QA test report — agent `qa` |
| `qa-dashboard.template.html` | HTML | QA dashboard visual — agent `dashboard` |
| `dashboard-readme.template.html` | HTML | README dashboard projet — agent `dashboard` |
| `adrs-index.template.md` | MD | Index ADRs — agent `dashboard` / `arch` (re-build) |
| `api-tests.template.json` | JSON | Blueprint test suite API gate — agent `qa` mode api-tests |
| `libs-catalog.schema.json` | JSON Schema 2020-12 | Validation `.libs.json` — `validate_libs_catalog.py` |
| `status.schema.json` | JSON Schema | Validation `workspace/console/status.json` — `gate_decide.py` |

---

## 9. Configuration & hooks Claude Code

### 9.1 `settings.json` (permissions globales)

- **Allow** : Read, Write, Edit, Glob, Grep, Skill, Agent, Task, TodoWrite, WebFetch, WebSearch + Bash whitelist (dotnet, npm, python, git, mkdir, etc.).
- **Deny** strictes (3 limites WORKING-AGREEMENT) :
  - `dotnet ef migrations *`, `dotnet ef database *` (DB structurelle interdite)
  - `git push *` (pas de réseau sortant)
  - `rm -rf /*` (sécurité)
- **Default mode** : `acceptEdits`
- **Additional directories** : 6 répertoires (templates, stacks, agents, hooks)
- **Hooks** : 5 enregistrés (cf. §7.3)

### 9.2 Variables d'environnement

| Variable | Usage |
|---|---|
| `CLAUDE_PROJECT_DIR` | Resolve repo root pour hooks (sinon walk-up `.claude/`) |
| `SDD_BUDGET_MODE` | `off` / `warn` (défaut) / `strict` — budget tokens pré-sub-agent |
| `SDD_DISPATCH_START_TS` | Timestamp début sub-agent (utilisé par `audit_file_ownership.py`) |
| `RuntimeException` | Exception STS LTS tracée dans Project Config |

### 9.3 Limites WORKING-AGREEMENT.md

**Pleine autorisation** dans SDD_Pro mais **3 limites strictes** :
1. Pas de modif DB structurelle (migrations interdites)
2. Pas d'accès hors SDD_Pro (filesystem confiné)
3. Pas de réseau sortant non documenté (deny `git push`, etc.)

---

## 10. Conventions & invariants

### 10.1 Anti-derive (cf. `docs/conventions.md §1-§13`)

1. **Format ERROR** 3 lignes obligatoire (`ERROR:` / `CAUSE: [CLASS]` / `FIX:`)
2. **Idempotence** : tout agent doit pouvoir re-run sans effet de bord
3. **Lecture sélective** : globs bornés, jamais `**/*.md` hors contexte
4. **Parallélisme borné** : `MaxParallel: 3` (défaut), range 1-12
5. **Plan inline** : précompilation fichiers dans STEP 5/6 avant Write
6. **CLAUDE.md per-project** : séparation contextes backend/frontend/lib
7. **HTML mockup texte direct** : lecture passive, pas vision multimodale
8. **Capabilities core vs on-demand** : §2.4.a inconditionnel, §2.4.b triggered
9. **Chat output minimal** : 1L succès, 2L max erreur
10. **Gates manuels v6.1** : console web `workspace/console/`, status atomic locks

### 10.2 Source-first discipline (`rules/source-first.md`)

**Code = cible, jamais source.** Tout bug en code = trou dans une source MD. Workflow obligatoire de fix :
1. Identifier la source MD manquante (FEAT, US, plan, stack, agent, rule)
2. Patcher la source MD **AVANT** le code
3. Vérifier propagation cross-source (FEAT + stack + plan + code)

Sans cette discipline, le prochain projet reproduit exactement le bug — les agents ne lisent QUE les MD.

### 10.3 Constitution & ADRs

- **constitution.md** : SSOT projet, sections §1-§8, append-only par phase, écriture séquentielle stricte.
- **ADRs** : `ADR-{YYYYMMDDTHHmmss}-{slug}.md` (timestamp UTC atomique, collision → suffixe `-{rand4}`).
- **Index §6** : reconstruit par `arch` (Phase 4 sérielle) OU `dashboard` post-pipeline. Dev-* INTERDITS d'éditer constitution.
- **ADRs phase 5** : source de vérité = `Glob workspace/output/.sys/.context/adrs/*.md` (l'index suit).

### 10.4 Workflow gated v6.1 (backend-first)

```
arch + DB → dev-backend ALL US → QA API Gate (in-memory) → dev-frontend ALL US
                                       │
                                       └─ 🔴 RED → STOP, humain corrige et relance
```

API Gate = WebApplicationFactory + EF InMemory (.NET) / supertest + Prisma SQLite (Node) / httpx.AsyncClient + SQLAlchemy SQLite (Python) / MockMvc + H2 (Kotlin). Auth JWT mocké. Jamais Azure AD réel ni DB réelle.

`gate_passed = (failed == 0) AND (total >= 2 × N_endpoints)`.

### 10.5 QA coverage hardening v6.1

`coverage_lines_pct < CoverageMin` → **RED bloquant** (`[QA_COVERAGE_GAP]`).
Bypass = baisser `CoverageMin` dans Project Config (git blame trace) ou `CoverageMin: 0` (désactivé). **Jamais** `--force`.

---

## 11. Loader manifest (`.claude/loader.yml`)

Source de vérité unique reads/writes par agent. Sert à :
- Audit du contexte (vérifier qu'un agent ne lit pas hors périmètre)
- Estimation tokens
- Détection drift (script `validate_inline_rules.py`)

Format extrait :
```yaml
agents:
  dev-backend:
    model: opus-4-7
    reads:
      - workspace/output/us/{n}-{m}-*.md
      - workspace/input/ui/{n}-{m}-*.html  # passif
      - workspace/output/src/{BackendName}/CLAUDE.md
      - workspace/output/db/schema.json    # optional
      - .claude/stacks/backend/*.md
      - .claude/stacks/auth/*.md
    writes:
      - workspace/output/src/{BackendName}/Services/**
      - workspace/output/src/{BackendName}/Endpoints/**
      - workspace/output/src/{BackendName}/DTOs/**
      ...
    forbidden_reads:
      - workspace/output/us/{autres}
      - workspace/input/feats/**
      - .claude/stacks/frontend/**
    modes: [normal, plan_only, from_plan]
```

---

## 12. Documentation interne (`.claude/docs/`)

| Fichier | Type | Sections |
|---|---|---|
| `architecture.md` | Référence (`Read @`) | Vision, modèles Claude split, agents reads/writes, stacks, capabilities, phase workflow, tokens economy |
| `workflow.md` | Référence | 4 phases détaillées, sub-phases, BREAKING CHANGES history (v5.0, v6.0, v6.1) |
| `conventions.md` | Référence | §1-§13 anti-derive + §14 rules index + §15 templates list |
| `quickstart.md` | Onboarding | Prérequis, edit stack.md, `/feat-generate`, `/sdd-full`, `/sdd-status` |

Plus métadonnées : `CHANGELOG.md`, `MIGRATION.md`, `WORKING-AGREEMENT.md` à la racine `.claude/`.

---

## 13. Forces & observations

### 13.1 Forces structurelles

✅ **Déterminisme massif** — 19 scripts Python 0-token (validate_readiness, validate_fidelity, parse_coverage, quality_scan, gate_decide, detect_capabilities, etc.). Moins de LLM = moins de variance.

✅ **Source-first invariant** — discipline rare mais load-bearing pour la reproductibilité cross-machine et la non-régression cross-projet.

✅ **Isolation par US** — lecture sélective `workspace/output/us/{n}-{m}-*.md` permet parallélisme sûr sans conflit.

✅ **File ownership matrix** — pré-requis pour le parallélisme borné `MaxParallel: 3`. Locks atomiques sur `{LibName}/` cross-language.

✅ **Backend-first gated workflow v6.1** — élimine 100% des mismatches contrat API/UI qui auraient été silencieux en mode parallèle.

✅ **Modèles spécialisés par rôle** — Opus 4.7 sur dev-* (raisonnement code), Sonnet 4.6 sur po/arch/qa/elicitor (raisonnement structuré), Haiku 4.5 sur dashboard (templating pur). Économie ~10× sur le rendu.

✅ **Stack completeness + LTS only** — fenêtre de sécurité documentée (fin support runtime), CVE check post-install obligatoire, registries canoniques uniquement.

✅ **Constitution + ADRs timestampés** — historicité décisionnelle complète, pas de race sur `§6` grâce à la délégation `constitutioner` + numérotation atomique.

✅ **Hooks Claude Code de garde-fou** — `validate_augment_contract` (bloquant exit 2), `audit_file_ownership` (log post-dispatch), `protect_framework` (warn modif `.claude/`).

### 13.2 Points d'attention / dette technique

⚠️ **Couverture tests Python partielle** — 5 tests sur 15+15 scripts (≈ 16%). `validate_fidelity`, `detect_capabilities`, `quality_scan`, `preflight`, `mark_breaking_resolved` non couverts. Risque drift silencieux.

⚠️ **Exit code non-standard `mark_breaking_resolved.py`** — exit 1 = succès. Documenté mais piège le pattern `cmd || handle_error`. Robustesse cross-caller fragile.

⚠️ **Couplage interne agents ↔ rules** — substance inlinée dans prompts agents (déclaré dans v5.0). `validate_inline_rules.py` détecte drift mais n'est pas auto-invoqué par le pipeline (manuel via `/sdd-status` ou release check).

⚠️ **Aucun combo .NET + React validé** — combos référence couvrent .NET full stack et Kotlin+React, mais pas le mix populaire `.NET API + React SPA`.

⚠️ **`SDD_BUDGET_MODE` défaut `warn`** — garde-fou budget tokens **non bloquant** par défaut. `strict` requis pour enforcement effectif.

⚠️ **Auth `auth-local` 🟡** — seul azure-ad est 🟢 validé. Projets sans Entra ID dépendent d'un stack expérimental.

⚠️ **Console web `workspace/console/`** — manual gates v6.1 dépendent de l'app dev humain (jsx/server.js), pas distribué dans le framework. Couplage soft.

⚠️ **Pas de mécanisme de versioning des stacks** — édition `.libs.json` = écrasement, pas de migration cross-version stack. Risque drift entre projets générés à T0 vs T+6mois.

⚠️ **Cleanup workspace** — `/sdd-clear` retiré en v6.1 (nettoyage manuel intentionnel). Discipline humaine requise pour ne pas accumuler artefacts orphelins entre runs.

### 13.3 Suggestions d'évolution (non implémentées)

À discuter selon priorités Tech Lead :

- **Combo `.NET + React` validation** : produire un projet de référence pour fermer le gap le plus visible.
- **Élargir tests Python** : viser ≥ 60% couverture sur `sdd_scripts/` (cible critique : `preflight`, `detect_capabilities`, `validate_fidelity`).
- **Migration stack versionnée** : ajouter `stackVersion` dans `.libs.json` + script `migrate_stack.py` (régénération entities/configs sur upgrade backend).
- **Auto-validation post-pipeline** : invoquer `validate_inline_rules.py` automatiquement en fin de `/sdd-full` (détection drift entre rules/ source et inlining agents).
- **Memory Claude Code scoped Tech Lead** (cf. discussion ouverte) : ergonomie cross-session sans casser le source-first invariant.
- **Default `SDD_BUDGET_MODE=strict`** : promouvoir la garde-fou budget de warn → strict au prochain palier majeur (v6.2 ou v7.0).
- **Console web packagée** : embarquer `workspace/console/` dans le framework (template + serveur Node minimal) au lieu de dev manuel.
- **Lib auth-local 🟢** : valider un combo référence avec auth-local pour les projets sans Entra ID.

---

## 14. Statistiques

| Dimension | Volume |
|---|---|
| **Agents** | 8 (4 cœur + 4 support) |
| **Modèles Claude** | 3 (Opus 4.7, Sonnet 4.6, Haiku 4.5) |
| **Slash commands** | 13 |
| **Stacks** | 20 (4 BE + 4 FE + 3 UI + 2 Auth + 7 QA) |
| **Stacks 🟢 reference** | 11 |
| **Stacks 🟡 experimental** | 9 |
| **Combos validés** | 2 (.NET full, Kotlin+React+shadcn) |
| **Build systems** | 5 (dotnet, gradle, pnpm, npm, uv) |
| **Capabilities on-demand** | 15+ (excel, pdf, redis, cqrs, email, auth-azure-ad, auth-local, etc.) |
| **Règles opérationnelles** | 9 |
| **Templates** | 15 (.md + .html + .json schema) |
| **Scripts Python** | 29 (15 sdd_scripts + 6 sdd_admin + 4 sdd_hooks + 6 sdd_lib) + 5 tests |
| **LOC Python total** | ~5 900 (stdlib pur 3.10+) |
| **Hooks Claude Code** | 5 (PreToolUse×2, PostToolUse, SubagentStop, Stop) |
| **Classes erreur `[CLASS]`** | 38+ codes unifiés cross-agent |
| **Conventions anti-derive** | 13 (cf. `docs/conventions.md`) |

---

## 15. Conclusion synthétique

SDD_Pro est un framework **mature, hautement déterministe et fortement opinioné**. Son architecture est centrée sur trois invariants load-bearing :

1. **Source-first** : le code n'est jamais une source ; tout bug = trou MD à patcher.
2. **Lecture sélective + parallélisme borné** : chaque agent voit le minimum nécessaire, parallélisation gated par ownership matrix.
3. **Backend-first gated workflow** : API Gate in-memory avant frontend = zéro mismatch contrat silencieux.

L'usage massif de scripts Python déterministes (parse_coverage, validate_readiness, detect_capabilities, gate_decide) réduit la variance LLM aux étapes où le raisonnement structuré apporte réellement de la valeur (élicitation, planification, génération code). Le split de modèles (Opus pour dev-*, Sonnet pour orchestration, Haiku pour rendu) optimise le coût/qualité.

Les **points d'attention principaux** restent : couverture tests Python à élargir, validation d'un combo `.NET+React`, et la question stratégique (en discussion) de l'introduction d'une mémoire Claude **scopée au Tech Lead** sans compromettre le source-first invariant.

---

*Fin de l'audit. Document statique au 2026-05-15, à régénérer si évolution majeure du framework.*
