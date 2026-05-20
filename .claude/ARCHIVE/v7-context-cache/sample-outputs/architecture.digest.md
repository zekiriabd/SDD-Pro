# Architecture Digest — SDD_Pro v6.10.5 (projet CMS Sprint)

> **Compiled digest** : constitution + ADRs (16) + pattern actif.
> Stable cross-FEAT — cacheable Anthropic prompt cache.
> Régénération recommandée à chaque nouvel ADR ou MAJ constitution.
> Généré : 2026-05-19.

---

## 1. Identité (constitution §1)

- **ProjectName** : `CMSPrint` (alias `CMSPrintFront` + `CMSPrintBack`)
- **AppType** : `back-front/web` (SPA React + API REST Spring)
- **Architecture pattern** : DDD (4 couches presentation/application/domain/infrastructure)
- **Bounded contexts** : 1 (monolithique) — `CMS Print` (campagnes + EANs + login)

## 2. Glossaire métier (constitution §2 — extrait clés)

| Terme | Définition |
|---|---|
| Campagne | Plan d'impression marketing : nom, période, statut, EANs ciblés |
| EAN | European Article Number (code-barres produit, 13 digits) |
| Grille | Vue tableau structurée des campagnes (sortable, filtrable, paginable) |
| Import CSV | Upload fichier CSV mappant EANs → métadonnées produit |
| Profil utilisateur | Données identité connectée (depuis token Azure AD : email, displayName, groups) |

## 3. Acteurs (constitution §3)

| Acteur | Rôle |
|---|---|
| Utilisateur authentifié (Microsoft) | Consultation campagnes, édition, import CSV |
| Administrateur (groupe AAD `Admin`) | Toutes actions + gestion utilisateurs (hors scope CMS Sprint v1) |
| Service backend (CMSPrintBack) | API REST authentifiée par JWT, propage rôles |
| Service frontend (CMSPrintFront) | SPA React MSAL, consomme API |

## 4. ADRs consolidés (16 décisions)

### Bootstrap arch (Phase 4, 7 ADRs)

| ADR | Décision | Statut |
|---|---|---|
| 20260518T125800-stack-backend-kotlin-spring | Spring Boot 4.0.6 + Kotlin 2.3.21 + JDK 21 | Accepted |
| 20260518T125801-stack-frontend-react-vite | React 19 + Vite 6 + TS 5.6 | Accepted |
| 20260518T125802-ui-design-system-shadcn | shadcn/ui (Radix + Tailwind v4) | Accepted |
| 20260518T125803-auth-azure-ad | Azure AD OIDC + JWT resource server | Accepted |
| 20260518T125804-database-postgres | PostgreSQL 16 (Flyway 10.x migrations) | Accepted |
| 20260518T125805-scaffolding-database-first | Schéma SQL/Flyway = SSoT ; JPA entities scaffold après | Accepted |
| 20260518T125806-architecture-pattern-ddd | DDD 4 couches (presentation/application/domain/infrastructure) | Accepted |

### Governance v7 (9 ADRs préparatoires, branche `next` post-freeze)

| ADR | Décision | Statut |
|---|---|---|
| 20260519T120000-governance-major-auditors-trim | Compression auditors (≤ 250 L chacun) | Proposed |
| 20260519T133000-governance-major-config-ssot | Loader.yml régénéré déterministiquement | Proposed |
| 20260519T143000-governance-major-flags-trim | Réduction flags `/sdd-full` `/dev-run` redondants | Proposed |
| 20260519T153000-governance-major-prompts-trim | CLAUDE.md trim 150 L (mesuré CI) | Proposed |
| 20260519T163000-governance-major-vocab-consolidation | Vocabulaire `[CLASS_*]` consolidé | Proposed |
| 20260519T173000-governance-protection-tracing | Audit trail protection memory rule | Proposed |
| 20260519T183000-governance-orphan-cleanup-tool | Outils `audit_orphans.py` / `cleanup_orphans.py` | Proposed |
| 20260519T193000-governance-roi-poc | Mesure ROI prompts/tokens cross-runs | Proposed |
| 20260519T194600-governance-major-devstar-strict-dry | Fusion 2 DRY dev-*-strict (Option 2A, −330 L) | Proposed |
| 20260519T201227-governance-major-v7-prompt-cache-build-loop-static-reviewer | Consolidé : Prompt cache + Build Sonnet retry + Static reviewer + A11y compress | Proposed |

## 5. Pattern d'archi appliqué (DDD canonique)

```
src/main/kotlin/com/cmsprint/
├── presentation/
│   ├── controllers/         # *Controller.kt (REST endpoints)
│   └── dto/                 # request/response shapes
├── application/
│   ├── handlers/            # *Handler.kt (command + query orchestration)
│   ├── commands/            # *Command.kt (write intents)
│   ├── queries/             # *Query.kt (read intents)
│   ├── dto/                 # internal application DTOs
│   └── mappers/             # domain ↔ DTO MapStruct or extension functions
├── domain/
│   ├── entities/            # rich domain models (no JPA annotations)
│   ├── valueobjects/        # immutable VOs
│   └── aggregates/          # aggregate roots
└── infrastructure/
    ├── repositories/        # *Repository.kt + JPA implementations
    ├── persistence/         # JPA entities (separate from domain)
    └── mappers/             # JPA ↔ domain
```

**Rules layer-bypass** :
- Controller → Handler (jamais Repository directement)
- Handler → Repository OR Domain service (jamais Controller direct)
- Domain → rien d'externe (pas de Spring annotations dans `domain/`)

**Naming canonique** : suffixes `Controller`, `Handler`, `Command`, `Query`, `Repository`, `Mapper`, `Aggregate`. Détection drift via `arch-reviewer`.

## 6. Risques (constitution §7, post-`/feat-deepen`)

| Risque | Mitigation |
|---|---|
| Latence Azure AD discovery (cold start) | Cache OIDC `.well-known/openid-configuration` 1h |
| Désync session frontend / backend | MSAL token refresh proactif + 401 → redirect login |
| CORS oublié en prod | Auto-injection arch + check preflight runtime |
| Import CSV volumineux (> 10 MB) | Stream parsing + chunk insert + progress UI |
| Tests intégration H2 vs PostgreSQL prod | `@DataJpaTest` H2 pour CI + smoke prod-like en staging |

## 7. Patterns interdits transverses

- ❌ Logique métier dans Controller (déplacer en Handler)
- ❌ JPA annotations dans `domain/` (séparer en `infrastructure/persistence/`)
- ❌ `@Autowired field` (préférer constructor injection)
- ❌ Hard-coded URLs / secrets (env vars seulement)
- ❌ Lazy loading par défaut sur grandes collections → `[PERF_N_PLUS_ONE_RISK]`
- ❌ `findAll()` sans pagination → `[PERF_DB_QUERY_NO_INDEX]`

---

*Digest régénérable : à chaque nouvel ADR (`workspace/output/.sys/.context/adrs/ADR-*.md` ajouté) ou modif constitution, relancer un futur `compile_architecture_digest.py` (v7) qui agrège constitution §1-§7 + tous les ADRs + pattern stack actif.*
