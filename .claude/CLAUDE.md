# SDD_Pro v7.0.0-alpha (branche `next`) — FEAT-Driven Development pour Claude Code

> ⛔ **FREEZE 2026-06-18** sur `main` (v6.10.4-LTS). Sur `next` : v7.0.0-alpha
> (auditors-trim, prompts-trim, stacks quarantine). Cf. `@.claude/docs/VERSIONING.md`
> + `@.claude/docs/CHANGELOG.md`.

> Framework SDD strict : FEAT → User Stories → Code (back/front parallèle).
> Lecture sélective, anti-derive, isolation par US et famille.

> **Slim entry point** : 150 lignes max (ADR `governance-major-prompts-trim`).
> Substance déléguée à `@.claude/docs/` et `@.claude/rules/`.

---

## 1. Convention de nommage (CRITIQUE)

Basename `{n}-{m}-{Name}` identique à travers tous les artefacts :

| Artefact | Chemin |
|---|---|
| Mockup HTML | `workspace/input/ui/{n}-{m}-{Name}.html` (optionnel) |
| User Story | `workspace/output/us/{n}-{m}-{Name}.md` |
| Code généré | `workspace/output/src/{AppName\|BackendName\|LibName}/...` |
| Plan technique | `workspace/output/plans/{n}-{m}-{Name}.{back\|front}.md` |

`{Name}` : Capitale initiale, pas d'accents, tirets pour espaces (`Auth`,
`Reset-Password`). Alias `FrontendName` accepté pour `AppName`.

---

## 2. IDs stables dans la FEAT (CRITIQUE)

`## Functional Needs`, `## Functional Deliverables`, `## Business Rules`,
`## Acceptance Criteria` portent des IDs stables `SFD-N`, `FD-N`, `BR-N`,
`AC-N`. Jamais réordonner après génération US. Ajout = `+1`. Retrait =
supprimer ligne ET régénérer les US. `Covers` réfèrent par valeur.

---

## 3. Commandes (12 user-facing + 8 internes [debug])

**User-facing** (orchestrantes, gèrent pré-conditions et idempotence) :

| Commande | Phase | Rôle |
|---|---|---|
| `/sdd-bootstrap` | 0 | Init projet greenfield (génère stack.md + workspace/) |
| `/feat-generate [Nom]` | 1 | Cadrage FEAT + bootstrap constitution |
| `/feat-validate {n} [--json]` | 2.6 | Implementation Readiness Gate |
| `/sdd-full {n}` | 2→5 | Pipeline complet A→Z (strict, prod-ready) |
| `/sdd-poc {n}` | 1→4 | **Pipeline minimaliste POC** (skip US/QA/review/API-gate — FEAT→arch→back→front) |
| `/dev-run {n}` | 4 | Orchestrateur dev (arch+DB → back → API gate → front) |
| `/qa-generate {n}` | 5 | Tests + coverage + quality scan |
| `/sdd-review {n}` | audit | Audit consolidé (style Sonar, bloquant RED) |
| `/sdd-status [{n}]` | diagnostic | État pipeline (read-only) |
| `/sdd-discover-stack` | onboarding | Scan repo brownfield → `stack.md.candidate` |
| `/sdd-serve` | runtime | Backend + front + console parallèle (ex-`/sdd-run`) |
| `/sdd-kill-server` | runtime | Arrête backend + front + console (pendant de `/sdd-serve`) |

**Internes** (8, debug — préférer un orchestrateur) : `/us-generate`,
`/arch-init`, `/dev-plan`, `/dev-backend`, `/dev-frontend`, `/doc-refresh`,
`/feat-deepen`, `/sdd-profile`. Flags `/sdd-full` et `/dev-run` : `--force`,
`--rebuild-arch`, `--resume`, `--manual-gates`, `--plan`, `--max-parallel N`.
Détail : `@.claude/commands/*.md`.

---

## 4. Agents (12)

**Cœur** : `po`, `arch` (Sonnet 4.6) ; `dev-backend`, `dev-frontend` (Opus 4.7).
**Support** : `elicitor`, `constitutioner`, `qa` (Sonnet 4.6).
**Auditors** : `code-reviewer`, `security-reviewer` (scan), `spec-compliance-reviewer`,
`arch-reviewer`, `adversarial-reviewer` (opt-in, informational). Méta-orchestrateur
déterministe : `phase_planner.py`. Retirés v7.0.0 (`a11y`/`perf`/`dashboard`/`*-strict`) :
cf. `@.claude/docs/architecture.md §2-§3`.

---

## 5. Règles & Templates

`.claude/rules/` (8 fichiers, 6 actives + 2 annexes) :
- **5 règles consolidées** : `build-and-loop`, `quality`, `ownership`,
  `library-and-stack`, `error-classification`
- **1 protocole chat** : `output-protocol.md` (1L `[AGENT] résumé (X%)`)
  + statusline `sdd_admin.statusline`
- **1 hoist** : `dev-shared-preflight.md` (STEP 0-1.bis dev-backend/frontend)
- **1 annexe** : `error-classification-legacy.md` (`[A11Y_*]`/`[PERF_*]` ingest CI)

**2 principes** : `.claude/docs/principles/{source-first,us-granularity}.md`.
Templates : `@.claude/docs/conventions.md §14-§15`.

---

## 6. Stacks (34 actifs)

| Catégorie | 🟢 reference | 🟡 experimental |
|---|---|---|
| Backend (4) | `dotnet-minimalapi`, `kotlin-spring-boot` | `python-fastapi`, `node-express` |
| Frontend (4) | `react`, `blazor-webassembly` | `vue`, `angular` |
| UI DS (3) | `shadcn` | `vuetify`, `radzen-blazor` |
| QA (9) | `code-quality`, `dotnet-xunit`, `kotlin-junit` | `node-vitest`, `blazor-bunit`, `python-pytest`, `angular-jasmine`, `mutation-testing` (opt-in), `playwright` (opt-in) |
| Auth (2) | `azure-ad` | `auth-local` |
| Archi (3) | `mvc` | `ddd`, `microservice` |
| Fullstack (6) | — | `angular-universal`, `blazor-server`, `kotlin-mustache`, `next`, `node-react`, `nuxt` |
| Mobiles (3) | — | `kotlin-android`, `maui`, `react-native` |

**Combos validés bout-en-bout : 2** sur ~120 (`dotnet-minimalapi×react×shadcn×dotnet-xunit×azure-ad`,
`kotlin-spring-boot×react×shadcn×kotlin-junit×azure-ad`). 🟡 chargeables mais non validés
end-to-end (risque runtime). Source de vérité = entête `Validation:` ; catalogue machine
`{id}.libs.json` régénéré via `sync_stack_md.py`. Détail : `@.claude/docs/{architecture,validated-combos}.md`.

---

## 7. Conventions strictes

Anti-derive, ERROR 3L disque, idempotence, lecture sélective, parallélisme borné
(`MaxParallel: 3`), plan inline, capabilities core vs on-demand, chat executive 1L
(`@.claude/rules/output-protocol.md`), gates manuels opt-in. Détail : `@.claude/docs/conventions.md §1-§13`.

## 8. Loader manifest

`@.claude/loader.yml` = miroir reads/writes par agent (SSoT, ADR `governance-major-config-ssot`).

---

## 9. Démarrage rapide

0. Greenfield : `python bootstrap.py [--combo c1|c2] [--dry-run]` (ou `/sdd-bootstrap` — détail `python bootstrap.py --help`). Brownfield : `/sdd-discover-stack`.
1. Éditer `workspace/input/stack/stack.md` (secrets DB, tenant Azure AD, ports).
2. `/feat-generate Auth` (3-6 questions). Optionnel : mockups HTML dans `workspace/input/ui/`.
3. `/sdd-full 1` → `/sdd-status [{n}]`. Variantes : `@.claude/docs/quickstart.md`.

---

## 10. Pour aller plus loin

- **Architecture & workflow** : `@.claude/docs/{architecture,workflow,conventions,quickstart}.md`
- **Onboarding** : `@.claude/docs/{glossary,hooks-and-protections,config-precedence}.md`
- **Gouvernance** : `@.claude/docs/{VERSIONING,CHANGELOG,MIGRATION,WORKING-AGREEMENT}.md`
- **ROI & roadmap** : `@.claude/docs/{poc-roi-methodology,roi-baseline,roadmap-v7-v8,scope-reduction-v7-ga,version-notes,cache-strategy,validated-combos,orphan-cleanup-policy}.md`
- **Règles** : `@.claude/rules/` (5 consolidées + 1 hoist + 1 protocole + 1 annexe)
- **Python** : `@.claude/python/README.md`
