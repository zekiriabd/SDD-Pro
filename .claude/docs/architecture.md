# SDD_Pro — Architecture (référence)

> Document de référence chargé **à la demande** (`Read @.claude/docs/architecture.md`).
> Pas en system prompt.

## 1. Vision

Le PO humain rédige une SPEC fonctionnelle. L'UX Designer (humain) dépose
des **mockups HTML statiques** dans `workspace/input/ui/`. Une chaîne de **4
agents** spécialisés (PO, Arch, Dev-Backend, Dev-Frontend) transforme
l'ensemble en :

1. **User Stories structurées** (1 à 6 par SPEC, cible 1-3) — agent PO
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
| `elicitor`     | `claude-sonnet-4-6` | Élicitation structurée 5 techniques                 |
| `qa`           | `claude-sonnet-4-6` | Génération tests unitaires                          |
| `dashboard`    | `claude-haiku-4-5-20251001` | Rendu HTML déterministe (README + INDEX ADRs + dashboards QA) |

> **Split modèles (depuis 2026-05-08)** : Opus 4.7 sur les agents qui
> génèrent du code applicatif (`dev-backend`, `dev-frontend`) — la
> qualité du code généré justifie le coût supplémentaire (preserves/adds
> contractuels, layer mapping strict, fidélité libellés HTML). Sonnet
> 4.6 sur les agents de transformation déterministe (po, arch, elicitor,
> qa). Haiku 4.5 sur le rendu déterministe (dashboard).
>
> **v6.0** : agent `validator` retiré (économie ~1.4M tokens/run).
> `/spec-validate` est désormais 100% déterministe via PowerShell.

## 3. Agents — lectures et écritures

| Agent          | Lit                                                                  | Écrit                                       |
|----------------|----------------------------------------------------------------------|---------------------------------------------|
| `po`           | `workspace/input/specs/{n}-*.md`, rules, templates                             | `workspace/output/us/{n}-{m}-*.md`                    |
| `arch`         | `workspace/input/stack/stack.md`, stacks actifs (Init Commands §2.2.1, scaffolding §3-§4, connection string §5.1), env vars `DB_*` | `workspace/output/src/...` (projets vides + .sln) ; (si DB) `workspace/output/db/schema.json` + `.md`, entities scaffoldées |
| `dev-backend`  | `workspace/output/us/{n}-{m}-*.md`, `workspace/input/ui/{n}-{m}-*.html` (passif), `workspace/output/src/{BackendName}/CLAUDE.md`, stacks `backend/auth` actifs, `workspace/output/db/schema.json` | `workspace/output/src/{BackendName}/...` (code applicatif) |
| `dev-frontend` | `workspace/output/us/{n}-{m}-*.md`, `workspace/input/ui/{n}-{m}-*.html` (texte direct, source de vérité visuelle), `workspace/output/src/{AppName}/CLAUDE.md`, stacks `frontend/ui` actifs | `workspace/output/src/{AppName}/...` (code applicatif) |
| `qa`           | US + code production (read-only) + ACs                               | `workspace/output/qa/feat-{n}/{report.md, coverage.json, quality.json}` + tests unitaires |

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
`## Active …`).

**Backend** (1 actif requis pour US à composante backend) :
- `backend/dotnet-minimalapi.md` — .NET 10 Minimal API + EF Core + AutoMapper + Serilog + FluentValidation + Polly
- `backend/node-express.md` — Node.js 22 + Express + Prisma
- `backend/python-fastapi.md` — FastAPI 0.115 + SQLAlchemy 2.x async
- `backend/java-spring-boot.md` — Spring Boot 3.4 + JPA + MapStruct + Lombok
- `backend/kotlin-spring-boot.md` — Spring Boot 3.4 + Kotlin 2.0 + JPA + MockK

Capabilities **on-demand** (§2.4.b) : EPPlus/ClosedXML (excel),
QuestPDF/iText7 (pdf), MediatR (cqrs), StackExchange.Redis (redis-cache),
Mapster (fast-mapping), Apache POI (excel Java), iText (pdf Java),
ExcelJS (excel Node), PDFKit (pdf Node), openpyxl (excel Python),
reportlab (pdf Python).

**Frontend** (1 actif requis pour US à composante frontend) :
- `frontend/blazor-server.md`, `frontend/blazor-webassembly.md`,
  `frontend/react.md`, `frontend/vue.md`, `frontend/angular.md`

**UI Design System** (1 actif requis quand mockup HTML présent) :
- `ui/radzen-blazor.md`, `ui/shadcn.md`, `ui/vuetify.md`

> Chaque stack UI déclare en **§2 Mapping fonctionnel → composant DS**
> ET **§7 Mapping HTML → composant DS (v4)** comment traduire les
> primitives HTML brutes (`<table>`, `<button>`, `<select>`, etc.) vers
> les composants natifs.

**Auth** (optionnel) :
- `auth/azure-ad.md`, `auth/auth-auth0.md`, `auth/auth-keycloak.md`,
  `auth/auth-local.md`

**QA** (optionnel) — actif si `## Active QA Specs` non vide :
- `qa/dotnet-xunit.md` — xUnit + Coverlet (.NET backend)
- `qa/blazor-bunit.md` — bUnit + xUnit (Blazor frontend)
- `qa/node-vitest.md` — Vitest + RTL/Vue Test Utils
- `qa/python-pytest.md` — pytest + coverage.py
- `qa/kotlin-junit.md` — JUnit 5 + MockK + JaCoCo
- `qa/angular-jasmine.md` — Jasmine + Karma + istanbul
- `qa/code-quality.md` — sonar-like cross-stack (PowerShell, 0 token)

## 5. État du framework — couvert / hors scope

✅ **Couvert** :
- Phase 1 (SPEC) — interactive, 6 questions max + bootstrap constitution
- Phase 1.5 (élicitation) — `/spec-deepen` agent `elicitor`, 5 techniques
- Phase 2 (US) — découpage 1 à 6 (cible 1-3, warning 4-6) + traçabilité 100%
- Phase 2.5 (HTML mockups) — humain dépose `workspace/input/ui/*.html`
- Phase 2.6 (readiness gate) — `/spec-validate {n}` 🟢 GO / 🟡 WARN / 🔴 NO-GO
- Phase 3 (ARCH + DB) — bootstrap idempotent + scaffolding Database-First + ADRs
- Phase 4 (CODE) — Dev-Backend + Dev-Frontend, plan inline, build loop max 3
- Phase 5 (QA + Quality) — tests unitaires + coverage + quality scan sonar-like

❌ **Hors scope** :
- DevOps / CI / déploiement
- Migrations EF Core forward/rollback
- Dashboard / observabilité
- E2E tests, perf, accessibility
- Code review LLM-heavy
