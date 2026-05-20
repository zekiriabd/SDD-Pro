# SDD_Pro v6.10.4-LTS — FEAT-Driven Development pour Claude Code

> ⛔ **FREEZE actif jusqu'au 2026-06-18** — voir `@.claude/VERSIONING.md §4`.
> Sur `main` : seuls les bumps PATCH. MAJOR/MINOR vivent sur `next`.

> Framework SDD strict : FEAT fonctionnelle → User Stories → Code
> (back/front en parallèle). Lecture sélective, anti-derive, isolation
> par US et par famille.

> **Slim entry point** : 150 lignes max (mesuré CI, cf.
> `ADR-20260519T153000-governance-major-prompts-trim`). Détails dans
> `@.claude/docs/` :
> - `architecture.md` — vision, agents, stacks
> - `workflow.md` — phases, BREAKING CHANGES
> - `conventions.md` — anti-derive, idempotence, capabilities
> - `version-notes.md` — notes opérationnelles par version

---

## 1. Convention de nommage (CRITIQUE)

Basename `{n}-{m}-{Name}` rigoureusement identique à travers tous les artefacts :

| Artefact | Chemin |
|---|---|
| Mockup HTML | `workspace/input/ui/{n}-{m}-{Name}.html` (optionnel) |
| User Story | `workspace/output/us/{n}-{m}-{Name}.md` |
| Code généré | `workspace/output/src/{AppName\|BackendName\|LibName}/...` (alias `FrontendName` accepté pour `AppName`) |
| Plan technique | `workspace/output/plans/{n}-{m}-{Name}.{back\|front}.md` |

`{Name}` : Capitale initiale, pas d'accents, tirets pour les espaces. Valides : `Auth`, `Reset-Password`, `Menu-Navigation`. Invalides : `auth`, `reset_password`, `Menu Navigation`.

---

## 2. IDs stables dans la FEAT (CRITIQUE)

`## Functional Needs`, `## Functional Deliverables`, `## Business Rules`, `## Acceptance Criteria` portent des IDs explicites stables : `SFD-N`, `FD-N`, `BR-N`, `AC-N`. Jamais réordonner ni renuméroter après génération des US. Ajout = `SFD-N+1`. Retrait = supprimer la ligne et **régénérer les US**. Les `Covers` des US référencent par valeur.

---

## 3. Commandes disponibles

| Commande | Phase | Rôle |
|---|---|---|
| `/feat-generate [Nom]` | 1 | Cadrage FEAT + bootstrap constitution |
| `/feat-deepen {n} [--quick]` | 1.5 | Élicitation (Pre-mortem, Red Team…) |
| `/us-generate {n}` | 2 | FEAT → User Stories (agent PO) |
| `/feat-validate {n} [--json]` | 2.6 | Implementation Readiness Gate |
| `/arch-init` | 3 | Bootstrap arch (auto via `/dev-run`) |
| `/dev-plan {n}` | 3.5 | Plans techniques sans coder |
| `/dev-backend {n}-{m}[:plan]` | 4 | Code serveur d'1 US |
| `/dev-frontend {n}-{m}[:plan]` | 4 | Code client d'1 US |
| `/dev-run {n}` | 3→4 | Orchestrateur (arch+back+front gated) |
| `/sdd-full {n}` | 2→5 | Pipeline complet A→Z |
| `/qa-generate {n}` | 5 | Tests + coverage + quality scan |
| `/sdd-review {n}` | audit | Audit consolidé (style Sonar) |
| `/sdd-status [{n}]` | diagnostic | État pipeline (read-only) |
| `/sdd-discover-stack` | onboarding | Scan repo → `stack.md.candidate` |
| `/sdd-profile {cmd}` | gouvernance | Snapshots team config |
| `/doc-refresh` | rendu | INDEX.md ADRs |

> Flags `/sdd-full` et `/dev-run` : `--force`, `--rebuild-arch`, `--resume`, `--manual-gates`, `--plan`, `--max-parallel N`. Pour la sémantique exhaustive : `@.claude/commands/*.md`.

---

## 4. Agents

**4 cœur** : `po`, `arch` (Sonnet 4.6) ; `dev-backend`, `dev-frontend` (Opus 4.7).
**Support** : `elicitor`, `constitutioner`, `qa` (Sonnet 4.6) ; `dashboard` (Haiku 4.5).
**Auditors** (Sonnet 4.6) : `accessibility-auditor` (Haiku), `code-reviewer`, `security-reviewer`, `performance-auditor`, `spec-compliance-reviewer`, `arch-reviewer`.
**Variants strict v6.2** : `dev-backend-strict`, `dev-frontend-strict` (Sonnet 4.6, opt-in `PlanCacheStrict: true`).

> Détail modèles, rôles, phases, isolation reads/writes : `@.claude/docs/architecture.md §2-§3`.
> Tous autonomes (aucune question utilisateur). Ambiguïté → `STOP + ERROR [CLASS]`.
> Méta-orchestrateur : `phase_planner.py` décide quelles auditors tourner par FEAT.
> Notes opérationnelles par version : `@.claude/docs/version-notes.md`.

---

## 5. Règles

11 règles dans `.claude/rules/` : `backend-first`, `constitution`, `cors`, `dev-shared`, `error-classification`, `file-ownership`, `qa-coverage`, `source-first`, `stack-completeness`, `ui-tokens`, `us-granularity`. Substance des règles critiques inlinée dans les agents (sera dépliée en v7.0.0, cf. `ADR-20260519T153000-governance-major-prompts-trim`).

Index commenté + détail : `@.claude/docs/conventions.md §14`.

---

## 6. Templates

Liste : `@.claude/docs/conventions.md §15`.

---

## 7. Stacks supportés

**28 stacks applicatifs + 3 patterns archi** (table compacte) :

| Catégorie | Stacks 🟢 reference | 🟡 Phase 2 |
|---|---|---|
| Backend (4) | `dotnet-minimalapi`, `kotlin-spring-boot`, `python-fastapi`, `node-express` | — |
| Frontend (4) | `react`, `vue`, `angular`, `blazor-webassembly` | — |
| UI DS (3) | `shadcn`, `vuetify`, `radzen-blazor` | — |
| Fullstack (6) | — | `node-react`, `blazor-server`, `next`, `nuxt`, `angular-universal`, `kotlin-mustache` |
| Mobiles (2) | — | `react-native`, `maui` |
| QA (7) | `dotnet-xunit`, `blazor-bunit`, `node-vitest`, `python-pytest`, `kotlin-junit`, `angular-jasmine`, `code-quality` | — |
| Auth (2) | `auth-local`, `azure-ad` | — |
| Archi (3) | `mvc` | `ddd`, `microservice` |

**AppType auto-détecté** depuis `## Active Tech Specs` (v6.7.7+) : `backend/* + frontend/*` → `back-front/web` ; `+ mobiles/*` → `back-front/mobile` ; `fullstack/*` seul → `fullstack`. Mix interdits → `[STACK_COMBO_INVALID]`.

**Pattern d'archi backend** déclaré dans `## Active Architecture Pattern` (scope `back-front` avec backend uniquement). Défaut MVC.

**Combos validés** : `dotnet-minimalapi × react × shadcn`, `kotlin-spring-boot × react × shadcn`. Hors combos = expérimental.

**Catalogue machine** : chaque stack expose `{id}.libs.json` (versions, libs core/on-demand, triggers). Le `.md` est doc humaine ; §2.4 régénéré via `sync_stack_md.py`.

> Détail combos + capabilities on-demand : `@.claude/docs/architecture.md §4`. Catalogue : `@.claude/rules/stack-completeness.md §1.0`.

---

## 8. Conventions strictes

Anti-derive, format ERROR 3 lignes, idempotence, lecture sélective, parallélisme borné (`MaxParallel: 3`), plan inline, CLAUDE.md par projet, capabilities core vs on-demand, chat output minimal, gates manuels opt-in.

Détail : `@.claude/docs/conventions.md §1-§13`. From-Plan Strict : `@.claude/docs/DESIGN-FROMPLAN-STRICT.md`.

---

## 9. Loader manifest

`@.claude/loader.yml` = miroir consolidé reads/writes par agent. Source de vérité pour audit contexte + estimation tokens. **Régénéré déterministiquement** en v7.0.0 (cf. `ADR-20260519T133000-governance-major-config-ssot.md`).

---

## 10. Démarrage rapide

1. Éditer `workspace/input/stack/stack.md` (`## Project Config`, `## Active Database`, `## Active Auth Specs`).
2. `/feat-generate Auth` — répondre aux 3-6 questions.
3. (Optionnel) déposer mockups HTML dans `workspace/input/ui/`.
4. `/sdd-full 1` — pipeline complet.
5. `/sdd-status [{n}]` — vérifier.

Détail + variantes : `@.claude/docs/quickstart.md`. Notes par version : `@.claude/docs/version-notes.md`.

---

## 11. Working Agreement

Pleine autorisation dans le répertoire SDD_Pro (fichiers, shell, git local). **3 limites** : pas de modif DB structurelle, pas d'accès hors SDD_Pro, pas de réseau sortant non documenté (cf. `.claude/settings.json`).

Contrat : `@.claude/WORKING-AGREEMENT.md`.

---

## 12. Pour aller plus loin

- `@.claude/docs/architecture.md` — vision, agents, stacks
- `@.claude/docs/workflow.md` — phases, flux
- `@.claude/docs/conventions.md` — anti-derive, idempotence
- `@.claude/docs/quickstart.md` — démarrage pas à pas
- `@.claude/docs/version-notes.md` — notes par version
- `@.claude/docs/DESIGN-FROMPLAN-STRICT.md` — design strict
- `@.claude/docs/MCP-SERVER.md` — serveur MCP (clients tiers)
- `@.claude/VERSIONING.md` — SemVer + freeze window
- `@.claude/CHANGELOG.md` — historique versions
- `@.claude/MIGRATION.md` — guide migration
- `@.claude/WORKING-AGREEMENT.md` — autorisations + limites
- `@.claude/rules/` — 11 règles opérationnelles
- `@.claude/python/README.md` — scripts utilitaires
