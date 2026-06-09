# SDD_Pro v7.0.0 GA — FEAT-Driven Development pour Claude Code

> ✅ **v7.0.0 GA tagué 2026-06-07** (audit CTO closure : 20 Critical + 38 Major
> fermés, taxonomie 174 classes, 13 combos SLA). v6.10.4-LTS conservée pour
> projets legacy. Cf. `@.claude/docs/VERSIONING.md` + `@.claude/docs/CHANGELOG.md`.

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

## 3. Commandes (13 user-facing + 8 internes [debug])

**User-facing** (orchestrantes, gèrent pré-conditions et idempotence) :

| Commande | Phase | Rôle |
|---|---|---|
| `/sdd-bootstrap` | 0 | Init projet greenfield (génère stack.md + workspace/) |
| `/feat-generate [Nom]` | 1 | Cadrage FEAT + bootstrap constitution |
| `/feat-validate {n} [--json]` | 2.6 | Implementation Readiness Gate (validation déterministe Python 0-token : IDs FEAT↔US stables, stacks actifs, mockups, AC coverage — GO/NO-GO bloquant) |
| `/sdd-full {n}` | 2→5 | Pipeline complet A→Z (strict, prod-ready) |
| `/sdd-poc {n}` | 1→4 | **Pipeline minimaliste POC** (skip US/QA/review/API-gate — FEAT→arch→back→front) |
| `/dev-run {n}` | 4 | Orchestrateur dev (arch+DB → back → API gate → front) |
| `/qa-generate {n}` | 5 | Tests + coverage + quality scan |
| `/sdd-review {n}` | audit | Audit consolidé (style Sonar, bloquant RED) — two-stage v7.0.0+ |
| `/sdd-status [{n}]` | diagnostic | État pipeline brut (tree ASCII, read-only) |
| `/sdd-help [{n}\|"question"]` | guidance | Aide contextuelle "what's next" (read-only, emprunt bmad-help) |
| `/sdd-discover-stack` | onboarding | Scan repo brownfield → `stack.md.candidate` |
| `/sdd-serve` | runtime | Backend + front + console parallèle (ex-`/sdd-run`) |
| `/sdd-kill-server` | runtime | Arrête backend + front + console (pendant de `/sdd-serve`) |

**Internes** (8, debug — préférer un orchestrateur) : `/us-generate`,
`/arch-init`, `/dev-plan`, `/dev-backend`, `/dev-frontend`, `/doc-refresh`,
`/feat-deepen`, `/sdd-profile`. Flags `/sdd-full` et `/dev-run` : `--force`,
`--rebuild-arch`, `--resume`, `--manual-gates`, `--plan`, `--max-parallel N`.
Détail : `@.claude/commands/*.md`.

---

## 4. Agents (12 LLM + 1 rubric déterministe = 13 .md)

**Cœur** : `po`, `arch` (Sonnet 4.6) ; `dev-backend`, `dev-frontend` (Opus 4.7).
**Support** : `elicitor`, `constitutioner`, `qa`.
**Auditors** : `code-reviewer`, `security-reviewer`, `spec-compliance-reviewer`,
`arch-reviewer`, `adversarial-reviewer` (opt-in, informational).
**Scripts déterministes** (0 token) : `complexity_router.py` (rubric
`docs/rubrics/complexity-router-scoring.md`), `phase_planner.py`.
Détail modèles + retraits v7.0.0 (`a11y`/`perf`/`dashboard`/`*-strict`) :
`@.claude/docs/architecture.md §2-§3`.

---

## 5. Règles & Templates

`.claude/rules/` (9 fichiers, 7 actives + 2 annexes) :
- **5 règles consolidées** : `build-and-loop`, `quality`, `ownership`,
  `library-and-stack`, `error-classification`
- **1 protocole chat** : `output-protocol.md` (1L `[AGENT] résumé (X%)`)
  + statusline `sdd_admin.statusline`
- **1 hoist** : `dev-shared-preflight.md` (STEP 0-1.bis dev-backend/frontend)
- **1 orchestration** : `auditor-orchestration.md` (two-stage gate STEP 6.4 dev-run)
- **1 annexe** : `error-classification-legacy.md` (`[A11Y_*]`/`[PERF_*]` ingest CI)

**2 principes** : `.claude/docs/principles/{source-first,us-granularity}.md`.
Templates : `@.claude/docs/conventions.md §14-§15`.

---

## 6. Stacks (34 actifs — SSoT = entête `Validation:` du `.md`)

> **v7.0.0 GA recount 2026-06-09** (audit CTO Major #5 closure) :
> **29 🟢 (validated/bench-validated/scaffold-validated) + 4 🟡 experimental + 1 🟡 POC-only = 34 total**.
> Validation auto : `python .claude/python/sdd_admin/framework_smoke.py` (gate `stacks-count`).

**🟡 experimental (4)** : `archi/ddd`, `archi/microservice`, `qa/mutation-testing` (opt-in), `qa/playwright` (opt-in).
**🟡 POC-only (1)** : `fullstack/node-react` (console SDD interne — non destiné prod externe).
**🟢 (29)** : tous les autres (cf. table détaillée + tiers `validated` / `bench-validated` / `scaffold-validated` dans `@.claude/docs/validated-combos.md §1-§2`).

**Engagement commercial — 13 combos SLA** : 2 `validated` end-to-end (C1, C2) + 11 `bench-validated runtime` (C3-C13). SSoT machine : `@.claude/templates/combos.json`. Marquage runtime via hook `preflight_stack_combo` (`SDD_ALLOW_UNTESTED_COMBO=1` = bypass audit-loggué). Stacks 🟡 explicitement exclus de tout SLA.

Détail tiers, matrice dimensions, 23 combinaisons bench 2026-06-05, cible C3-prod, exceptions `.libs.json` : `@.claude/docs/validated-combos.md`.

---

## 7. Conventions strictes

Anti-derive, ERROR 3L disque, idempotence, lecture sélective, parallélisme borné
(`MaxParallel: 3`), plan inline, capabilities core vs on-demand, chat executive 1L
(`@.claude/rules/output-protocol.md`), gates manuels opt-in. Détail : `@.claude/docs/conventions.md §1-§13`.

## 8. Loader manifest

`@.claude/loader.yml` = miroir reads/writes par agent (SSoT, ADR `governance-major-config-ssot`).

---

## 9. Démarrage rapide

0. Greenfield : `python bootstrap.py [--combo c1|c2|c3|c4|c5|custom] [--dry-run|--auto-init]` (ou `/sdd-bootstrap` — détail `python bootstrap.py --help`). Brownfield : `/sdd-discover-stack`.
0.bis **Phase 0 Discovery (facultatif, projets > 3 FEATs)** : copier `.claude/templates/product-brief.template.md` ou `prfaq.template.md` dans `workspace/input/discovery/` pour cadrer vision/personas/KPIs avant les FEATs. Anti-derive : si une FEAT proposée ne sert pas une promesse de la Discovery, c'est probablement du scope creep.
1. Éditer `workspace/input/stack/stack.md` (SSoT unique — valeurs en clair `DB_PASSWORD`, `AUTH_JWT_SECRET`, `AZ_TENANTID`, ports ; fichier **gitignored**, arch propage en `appsettings.json` / `application.yml`).
2. `/feat-generate Auth` (3-6 questions). Optionnel : mockups HTML dans `workspace/input/ui/`.
3. `/sdd-full 1` → `/sdd-status [{n}]` (état brut) ou `/sdd-help [{n}]` (guidance "what's next"). **Cookbook 10 min : `@.claude/docs/cookbook.md`**. Variantes complètes : `@.claude/docs/quickstart.md`.

---

## 10. Pour aller plus loin

- **Architecture & workflow** : `@.claude/docs/{architecture,workflow,conventions,quickstart}.md`
- **Onboarding** : `@.claude/docs/{glossary,hooks-and-protections,config-precedence,po-guide,ux-designer-guide}.md`
- **Élicitation** : `@.claude/docs/brainstorming-techniques.md` (bibliothèque 15 techniques v7.0.0+, emprunt BMad)
- **Gouvernance** : `@.claude/docs/{VERSIONING,CHANGELOG,MIGRATION,WORKING-AGREEMENT}.md`
- **Commercial / DSI** : `@.claude/docs/{WHY-SDD-PRO,COMPLIANCE,SLA,KNOWN-LIMITATIONS}.md`
- **ROI & roadmap** : `@.claude/docs/{poc-roi-methodology,roadmap-v7-v8,cache-strategy,validated-combos,orphan-cleanup-policy}.md`
- **Règles** : `@.claude/rules/` (5 consolidées + 1 hoist + 1 protocole + 1 annexe)
- **Skills auto-triggered** (v7.0.0+ emprunt superpowers) : `@.claude/skills/` (`using-sddpro`, `starting-a-new-feat`, `debugging-failed-pipeline`, `test-driven-development`)
- **Invariants manifest** (v7.0.0+ audit P3 E4) : `@.claude/INVARIANTS.yml` — 13 contrats load-bearing (two-stage gate, file ownership, cost cap, schema strict, TDD test-first, etc.) avec pointer vers chaque enforcer (hook/script/smoke test). Test `tests/test_invariants_manifest.py` vérifie que chaque enforcer existe sur disque. Anti-rot manifest : retirer un enforcer sans mettre à jour le manifest = FAIL au smoke.
- **Python** : `@.claude/python/README.md`
