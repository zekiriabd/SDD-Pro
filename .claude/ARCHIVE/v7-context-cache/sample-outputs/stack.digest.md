# Stack Digest — SDD_Pro v6.10.5 (projet CMS Sprint)

> **Compiled digest** de la stack active déclarée dans `workspace/input/stack/stack.md`.
> Stable cross-FEAT — cacheable Anthropic prompt cache (5 min TTL).
> Régénération recommandée à chaque modification de `stack.md`.
> Généré : 2026-05-19.

---

## Identité projet

| Clé | Valeur |
|---|---|
| `FrontendName` / `AppName` | `CMSPrintFront` |
| `BackendName` | `CMSPrintBack` |
| `AppNamespace` (auto) | `CMSPrintFront` |
| `BackendNamespace` (auto) | `CMSPrintBack` |
| `FrontendLocalPort` | `5185` |
| `BackendLocalPort` | `44328` |
| `LibStrategy` | `openapi-codegen` |

## Project Config (effectif)

```yaml
PlanReviewDefault: true
QAMode: full
CoverageMin: 80
MaxParallel: 4
SecurityScanEnabled: false
PlanCacheStrict: true        # v6.10.5 audit 2026-05-19 — Sonnet From-Plan path actif
# Défauts framework (config.base.yml) :
A11yMode: full ; A11yFailOn: serious
CodeReviewMode: manual ; CodeReviewFailOn: critical
SecurityMode: manual ; SecurityFailOn: critical
PerfMode: full ; PerfFailOn: serious
SpecComplianceMode: manual ; SpecComplianceFailOn: serious
GatedWorkflow: true ; ApiGateRequired: true ; ApiGateMinPerEndpoint: 2
BuildLoopMaxIter: 3
CheckpointMode: off
```

---

## Stacks actifs (AppType auto-détecté = back-front/web)

### Backend — `kotlin-spring-boot` 🟢

- **Runtime** : Kotlin 2.3.21 + Spring Boot 4.0.6 + JDK 21 (LTS).
- **Build** : Gradle Kotlin DSL avec `libs.versions.toml`.
- **Layout v7 DDD** : 1 module Gradle, organisation `presentation / application / domain / infrastructure`.
- **Persistence** : Spring Data JPA + Hibernate, transactions `@Transactional`.
- **Auth** : `spring-security-oauth2-resource-server` (consume JWT Azure AD).
- **Validation** : `spring-boot-starter-validation` (Jakarta Bean Validation).
- **OpenAPI** : `springdoc-openapi-starter-webmvc-ui` 2.x.
- **Mapping** : `MapStruct` ou extension functions Kotlin.
- **Tests** : JUnit 5 + MockMvc + `@DataJpaTest` H2 (cf. stack `qa/kotlin-junit`).

### Frontend — `react` 🟢

- **Runtime** : React 19 + Vite 6 + TypeScript 5.6 + Node 22 (LTS).
- **Routing** : TanStack Router (file-based, code-split).
- **State** : TanStack Query (server state) + Zustand (UI state, optionnel).
- **Forms** : React Hook Form + Zod.
- **Build** : Vite (`vite.config.ts`) + Vitest pour tests unitaires.
- **Lint/Format** : ESLint 9 (flat config) + Prettier 3.
- **Mono-projet** ; pas de Turborepo en CMS Sprint (single-app).
- **Locale** : i18next + react-i18next.

### UI Design System — `shadcn` 🟢

- **Base** : Tailwind CSS v4 + Radix UI primitives (15 onDemand par capability).
- **Tokens** : `src/index.css` HSL space-separated `:root` + `[data-theme="dark"]`.
- **Composants core** (7) : Button, Input, Label, Card, Dialog, Toast, DropdownMenu. Reste à demande via capabilities trigger (DataTable, Form, Calendar, etc.).
- **Theming** : light/dark toggle via `prefers-color-scheme` + localStorage.
- **Anti-pattern** : pas de hex dans composants — tout via `var(--primary)` etc. (cf. `ui-tokens.md`).

### Auth — `azure-ad` 🟢

- **Backend** : Spring Security resource server, JWT validation (signature, issuer, audience, expiration), claim `groups` → policy `Authorization`.
- **Frontend** : `@azure/msal-browser` + `@azure/msal-react`, flow Authorization Code + PKCE.
- **Endpoint public** : `GET /auth/config` retourne tenantId/clientId/audiences/callbackPath (lus des env vars `AZ_*`).
- **CORS** : auto-injecté par arch STEP 4.5.6 (origin `http://localhost:5185` → backend allowlist).
- **Pas de logout backend** : délégué à Azure AD via `/oauth2/v2.0/logout` + MSAL `logoutRedirect`.

### Architecture Pattern — `ddd` 🟡 experimental

- **Couches** : `presentation/` (controllers) → `application/` (handlers + commands + queries + DTOs) → `domain/` (entities + value objects + aggregates) → `infrastructure/` (repositories + mappers + JPA entities).
- **Naming canonique** : `*Controller`, `*Handler`, `*Repository`, `*Mapper`, `*DTO`. Aggregate root = entity racine.
- **Layer-bypass interdit** : Controller → Repository directement = `[ARCH_LAYER_BYPASS]`.
- **DI** : `@Service` (application), `@Repository` (infrastructure), `@Component` rare.
- **WARNING runtime** : `[STACK_EXPERIMENTAL]` émis au preflight (combo DDD non end-to-end validé v6).

### Database — PostgreSQL 16 (depuis stack.md ## Active Database)

- `DatabaseType: postgres`
- Migrations : Flyway 10.x (préféré v7 vs 12.x qui a un NoSuchMethodError Boot 3.5 → conserver 10.20).
- Schéma source de vérité : `workspace/output/db/schema.json` produit par `arch` Phase B.

---

## QA stack actif — `qa/kotlin-junit` 🟢

- Test runner : JUnit 5 + Spring Boot Test.
- Integration HTTP : MockMvc (in-memory).
- DB tests : `@DataJpaTest` H2 in-memory.
- Mocking : MockK + SpringMockK.
- Coverage : JaCoCo (rapport XML → normalisé par `parse_coverage.py`).

---

## Capabilities ON-DEMAND triggers (à activer si keyword US)

| Capability | Trigger keywords | Lib backend | Lib frontend |
|---|---|---|---|
| `excel`     | export excel, xlsx, spreadsheet | Apache POI 5.x | SheetJS / xlsx 0.20 |
| `pdf`       | export pdf, génération pdf      | OpenPDF / iText | jsPDF + html2canvas |
| `redis-cache` | cache redis, distributed cache | Spring Data Redis | — |
| `file-upload` | upload fichier, multipart       | Spring multipart | TanStack Query + FormData |
| `csv-import`  | import csv, parse csv          | Apache Commons CSV / OpenCSV | papaparse |
| `cqrs`        | CQRS, command-query split      | (pattern DDD)   | — |

---

## Combos validés référence

- ✅ `kotlin-spring-boot × react × shadcn × azure-ad × ddd` (CMS Sprint pilote)
- ✅ `dotnet-minimalapi × react × shadcn × azure-ad × mvc` (référence framework)
- 🟡 Autres = expérimental → `[STACK_EXPERIMENTAL]` WARN runtime.

---

*Digest régénérable : à chaque modification de `stack.md`, relancer un futur script `compile_stack_digest.py` (v7) qui lit `stack.md` + les `.md` + `.libs.json` actifs et reconstruit ce fichier.*
