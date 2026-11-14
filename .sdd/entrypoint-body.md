# SDD_Pro v7.0.0 GA — FEAT-Driven Development pour Claude Code

> ✅ **v7.0.0 GA — désignation datée du 2026-06-07** (audit CTO closure :
> 20 Critical + 38 Major fermés, taxonomie 193 classes, 13 combos SLA).
> v6.10.4-LTS conservée pour projets legacy. Cf. `@.sdd/docs/VERSIONING.md` +
> `@.sdd/docs/CHANGELOG.md`.
>
> ⚠️ **Aucun tag git n'existe pour cette version** (`git tag --list` vide,
> vérifié audit 2026-08-29). La version est portée par la documentation et le
> CHANGELOG, pas par une référence git — ne pas s'appuyer sur `git describe`
> ni sur un checkout `v7.0.0` dans un script ou un pipeline CI.

> Framework SDD strict : FEAT → User Stories → Code (back/front parallèle).
> Lecture sélective, anti-derive, isolation par US et famille.

> **Slim entry point** : budget cible ~155 lignes (ADR
> `governance-major-prompts-trim`) — **réel après trim 2026-11-07 : 237 lignes /
> 16 Ko** (était 257 lignes / 23 Ko ; narration des batches stacks déplacée dans
> `validated-combos.md §0.2`). Budget non atteint : les sections restantes portent
> des cross-références qu'une coupe à l'aveugle casserait.

---

## 1. Convention de nommage (CRITIQUE)

Basename `{n}-{m}-{Name}` identique à travers tous les artefacts :

| Artefact | Chemin |
|---|---|
| FEAT | `workspace/feats/{n}-{FeatName}.md` |
| Mockup HTML | `workspace/ui/{n}-{m}-{Name}.html` (optionnel) |
| User Story | `workspace/us/{n}-{m}-{Name}.md` |
| Code généré | `workspace/src/{AppName\|BackendName\|LibName}/...` |
| Plan technique | `workspace/plans/{n}-{m}-{Name}.{back\|front}.md` |

`{Name}` : Capitale initiale, pas d'accents, tirets pour espaces (`Auth`,
`Reset-Password`). Alias `FrontendName` accepté pour `AppName`.

> **`{FeatName}` ≠ `{Name}` (CRITIQUE — audit nommage 2026-06-16)** : la FEAT
> `{n}-{FeatName}.md` porte le nom de la **famille** (ex. `1-Avoir`). Mais le
> `{Name}` des artefacts à 3 segments (`{n}-{m}-{Name}` : US, mockup, plan)
> est un **slug de capability DISTINCTIF par US** — verbe d'action + objet
> métier dérivé du titre de l'US, jamais le nom de la FEAT répété. Deux US
> d'une même FEAT ne partagent **JAMAIS** le même `{Name}`.
> - ✅ `1-1-Consulter-Fiche-Avoir.md`, `1-2-Piloter-Acces-Actions.md` (distinctifs)
> - ❌ `1-1-Avoir.md`, `1-2-Avoir.md` (nom de FEAT répété — anti-pattern, le
>   sens distinctif ne doit PAS vivre uniquement dans le titre in-file)
>
> La ligne `ID: {n}-{m}-{Name}` à l'intérieur de l'US **doit** matcher le
> basename ; la ligne `Parent FEAT: {n}-{FeatName}` pointe vers la FEAT
> (nom de famille). La console (`workspace/console`) affiche le titre in-file
> `# US-{m}: …` mais l'arborescence disque doit rester lisible **sans ouvrir
> les fichiers** — d'où le slug distinctif obligatoire.

> **FEAT de migration Flyway (`{FeatName}` contient « Flyway », 2026-06-30)** :
> un nom de fichier FEAT matchant `(?i)flyway` (ex. `2-Flyway-Migration.md`)
> déclenche, à **chaque** `/sdd-full` ou `/sdd-poc`, l'exécution de `flyway
> migrate` PUIS le re-scaffolding DB par arch (Phase B STEP 8.5). C'est la
> **seule** dérogation à `[DB_STRUCTURE_CHANGE_FORBIDDEN]` (mécanisme de
> migration sanctionné, idempotent via `flyway_schema_history`). SSoT :
> `@.sdd/rules/library-and-stack.md §C.6`.

---

## 2. IDs stables dans la FEAT (CRITIQUE)

`## Functional Needs`, `## Functional Deliverables`, `## Business Rules`,
`## Acceptance Criteria` portent des IDs stables `SFD-N`, `FD-N`, `BR-N`,
`AC-N`. Jamais réordonner après génération US. Ajout = `+1`. Retrait =
supprimer ligne ET régénérer les US. `Covers` réfèrent par valeur.

---

## 3. Commandes (41 : 13 user-facing + 9 internes [debug] + 19 reverse)

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

**Internes** (9, debug — préférer un orchestrateur) : `/us-generate`,
`/arch-init`, `/dev-plan`, `/dev-backend`, `/dev-frontend`, `/doc-refresh`,
`/feat-deepen`, `/sdd-profile`, `/spec-book`. Flags `/sdd-full` : `--force`,
`--rebuild-arch`, `--resume`, `--manual-gates`, `--no-manual-gates`,
`--manual-gates=us,plan`, `--plan`, `--no-plan-on-warn`, `--no-validate`
(le parallélisme se règle via `MaxParallel:` en Project Config — pas de flag
`--max-parallel` sur `/sdd-full`, audit 2026-06-11 M8). Flags `/dev-run` : `--rebuild-arch`, `--resume`,
`--max-parallel N`, `--unsequenced`, `--legacy-auditor-parallel`.
⚠️ `--no-validate`, `--unsequenced`, `--legacy-auditor-parallel`
**désactivent des protections** (bypass audit-loggués). Détail : `@.sdd/commands/*.md`.

**Reverse engineering** (19, module optionnel legacy→FEAT) : `/sdd-reverse-full`
(orchestrateur), `/sdd-reverse {U-N}`, `/sdd-reverse-{init,inventory,audit,analyze,stories,feat,crosscut,review,ui,status,synth}`,
+ 3 phases optionnelles emprunt Reversa (2026-06-12) : `/sdd-reverse-paradigm`
(gap paradigme + curation), `/sdd-reverse-parity` (specs Gherkin de parité),
`/sdd-reverse-questions` (boucle validation humaine, `--ingest`)
+ 3 db-reverse (**base de données → FEAT**, lecture seule via
`stack.md ## Active Database`) : `/sdd-db-context` (**Phase 0 obligatoire**
2026-08-26 — Database Context versionné : faits déterministes puis
interprétation par `reverse-db-architect`, packs de contexte par objet),
`/sdd-db-reverse-full` (tous les objets SQL) et `/sdd-db-reverse {objet}`
(un objet) — **procédures + fonctions + vues + triggers** (+ packages Oracle),
1 objet SQL = 1 US, 1 module = 1 FEAT. Dispatch **par vagues de dépendance**
(tout appelé analysé avant son appelant) vers les 4 analystes spécialisés.
4 moteurs (2026-07-24 ; **downgrade PostgreSQL audit 2026-08-29**) : SQL Server
(live-validé — preuves de runs réels), PostgreSQL + Oracle + MySQL/MariaDB
(scaffold-validés, runtime live pending). PostgreSQL était annoncé
« live-validé » à tort : l'audit du module db-reverse porte une réserve
explicite jamais levée — aucun run n'a jamais été exécuté contre une base
PostgreSQL réelle. SSoT : `@.sdd/docs/reverse-engineering-workflow.md`
+ `@.sdd/docs/reverse-db-audit-2026-07.md`
+ `@.sdd/docs/reverse-proc-engineering.audit.md` + `@.sdd/rules/reverse-engineering.md`.

---

## 4. Agents (29 : 13 LLM forward + 16 reverse, + 1 rubric déterministe)

**Cœur** : `po`, `arch` (tier `balanced`, Sonnet 5.5) ; `dev-backend`, `dev-frontend`
(tier `deep`, Opus 5.5). Modèle = `model_tier` résolu par `providers/*.yaml` ;
`effort:` par agent (`high` : dev-*, arch, 3 reverse ; `medium` : le reste).
**Support** : `elicitor`, `constitutioner`, `qa`, `specbook-writer` (vulgarise
FEAT en langage humain, cache `workspace/docs/.sys/sections/`).
**Auditors** : `code-reviewer`, `security-reviewer`, `spec-compliance-reviewer`,
`arch-reviewer`, `adversarial-reviewer` (opt-out — actif par défaut, informational).
**Reverse** (16, manifest autonome `loader.reverse.yml`) : `reverse-inventory`,
`reverse-tech-auditor`, `reverse-tech-analyst`, `reverse-us-writer`,
`reverse-feat-composer`, `reverse-ui-extractor`, `reverse-completeness-reviewer`,
`reverse-paradigm-advisor`, `reverse-parity-inspector`, `reverse-clarifier`,
`reverse-sql-analyst` (db-reverse : spécialiste procédures stockées),
`reverse-sql-function-analyst`, `reverse-sql-view-analyst`,
`reverse-sql-trigger-analyst` (spécialistes par famille d'objet SQL, 2026-08-26),
`reverse-db-architect` (Phase 0.B : interprétation de la base — hypothèses
uniquement, jamais de faits), `reverse-sql-feat-composer` (synthèse métier d'un
module ; défaut pour les modules complexes depuis 2026-08-26).
**Scripts déterministes** (0 token) : `complexity_router.py` (rubric
`docs/rubrics/complexity-router-scoring.md`), `phase_planner.py`.
Détail modèles + retraits v7.0.0 (`a11y`/`perf`/`dashboard`/`*-strict`) :
`@.sdd/docs/architecture.md §2-§3`.

---

## 5. Règles & Templates

`.sdd/rules/` (12 fichiers) :
- **5 règles consolidées** : `build-and-loop`, `quality`, `ownership`,
  `library-and-stack`, `error-classification`
- **1 protocole chat** : `output-protocol.md` (1L `[AGENT] résumé (X%)`)
  + statusline `sdd_admin.statusline`
- **1 hoist** : `dev-shared-preflight.md` (STEP 0-1.bis dev-backend/frontend)
- **2 orchestration auditors** : `auditor-orchestration.md` (two-stage gate)
  + `auditor-coordination.md` (matrice ownership findings, SSoT anti-doublon)
- **1 annexe** : `error-classification-legacy.md` (`[A11Y_*]`/`[PERF_*]` ingest CI)
- **1 module reverse** : `reverse-engineering.md` (anti-derive + taxonomie `[REVERSE_*]`)
- **1 socle SQL** : `db-reverse-tsql.md` (sémantique partagée des 5 agents du reverse
  base de données — pièges `MERGE`/`OUTPUT`/`inserted`/`NULL`, atomicité, erreurs →
  AC négatifs, équivalences T-SQL / PL-pgSQL / PL-SQL / MySQL)

**2 principes** : `.sdd/docs/principles/{source-first,us-granularity}.md`.
Templates : `@.sdd/docs/conventions.md §14-§15`.

> **Chargement paresseux** : 11 des 12 rules portent une frontmatter `paths:` et ne
> s'auto-injectent qu'au contact de leur périmètre ; seule `output-protocol.md` est
> inconditionnelle (elle porte aussi le noyau error-classification §7.3/§7.5 ; la
> taxonomie complète passe par les digests `.sdd/digests/`). `build-and-loop.md` et
> `dev-shared-preflight.md` ne sont jamais auto-injectées (Read borné explicite).
> **Fixe mesuré par sous-agent** (2026-11-07) : ce fichier ~16 Ko + `output-protocol`
> 15 Ko ≈ 31 Ko, **plus** les Reads de STEP contexte de chaque agent (rules par
> section, digest, stacks par section) et les rules path-scoped injectées au contact
> de `workspace/src/**` (`ownership` 26 Ko, `library-and-stack` 35 Ko, `quality` 20 Ko).
> Vérification : `/memory` dans une session fraîche.

---

## 6. Stacks (56 actifs — SSoT = entête `Validation:` du `.md`)

**28 🟢 (validated / bench-validated) + 28 🟡 = 56** (recount 2026-09-02). Liste
des 🟡, historique des batches 2026-09-02 (mobiles, backend, fullstack, nouvelle
catégorie `desktop/`) et tiers : `@.sdd/docs/validated-combos.md §0-§2`. Check
`stack-md-headers` de `framework_smoke.py` = WARN (pas FAIL) sur drift de compte.

**13 combos SLA** : C1-C2 `validated`, C3-C13 `bench-validated runtime` (SSoT
`@.sdd/templates/combos.json`, hook `preflight_stack_combo`, bypass audit-loggué
`SDD_ALLOW_UNTESTED_COMBO=1`). Un stack 🟡 n'est jamais vendu seul (exception
GOV-C1 : `archi/ddd` dans C2). ⚠️ Badges obtenus sur la génération de modèles
4.x — **non re-benchés en 5.5** (`validated-combos.md §0.1`).

---

## 7. Conventions strictes

Anti-derive, ERROR 3L disque, idempotence, lecture sélective, parallélisme borné
(`MaxParallel: 3`), plan inline, capabilities core vs on-demand, chat executive 1L
(`@.sdd/rules/output-protocol.md`) — **en pipeline, tableau d'avancement obligatoire à chaque étape, seul (§2.4)**, gates manuels opt-in. Détail : `@.sdd/docs/conventions.md §1-§13`.

## 8. Loader manifest

`@.sdd/loader.yml` = miroir reads/writes par agent (SSoT, ADR `governance-major-config-ssot`).

---

## 9. Démarrage rapide

0. Greenfield : `python bootstrap.py [--combo c1|c2|c3|c4|c5|custom] [--dry-run|--auto-init]` (ou `/sdd-bootstrap` — détail `python bootstrap.py --help`). Brownfield : `/sdd-discover-stack`.
0.bis **Phase 0 Discovery (facultatif, projets > 3 FEATs)** : copier `.sdd/templates/product-brief.template.md` ou `prfaq.template.md` dans `workspace/discovery/` pour cadrer vision/personas/KPIs avant les FEATs. Anti-derive : si une FEAT proposée ne sert pas une promesse de la Discovery, c'est probablement du scope creep.
1. Éditer `workspace/stack/stack.md` (SSoT unique — valeurs en clair `DB_PASSWORD`, `AUTH_JWT_SECRET`, `AZ_TENANTID`, ports ; arch propage en `appsettings.json` / `application.yml`). ⚠️ **Le fichier est VERSIONNÉ depuis 2026-08-30** (`.gitignore` : `!workspace/stack/stack.md` — il voyage avec le repo comme SSoT projet) : n'y écrire que des placeholders `${VAR}`, tout secret réel part sur `origin` au premier push. Le reste de `workspace/` reste gitignored.
2. `/feat-generate Auth` (3-6 questions). Optionnel : mockups HTML dans `workspace/ui/`.
3. `/sdd-full 1` → `/sdd-status [{n}]` (état brut) ou `/sdd-help [{n}]` (guidance "what's next"). **Cookbook 10 min : `@.sdd/docs/cookbook.md`**. Variantes complètes : `@.sdd/docs/quickstart.md`.

---

## 10. Pour aller plus loin

- **Architecture & workflow** : `@.sdd/docs/{architecture,workflow,conventions,quickstart,gates-map}.md`
- **Onboarding** : `@.sdd/docs/{glossary,hooks-and-protections,config-precedence,po-guide,ux-designer-guide}.md`
- **Élicitation** : `@.sdd/docs/brainstorming-techniques.md` (bibliothèque 15 techniques v7.0.0+, emprunt BMad)
- **Gouvernance** : `@.sdd/docs/{VERSIONING,CHANGELOG,MIGRATION,WORKING-AGREEMENT}.md`
- **Commercial / DSI** : `@.sdd/docs/{WHY-SDD-PRO,COMPLIANCE,SLA,KNOWN-LIMITATIONS}.md`
- **ROI & roadmap** : `@.sdd/docs/{poc-roi-methodology,roadmap-v7-v8,cache-strategy,validated-combos,orphan-cleanup-policy}.md`
- **Règles** : `@.sdd/rules/` (5 consolidées + 1 protocole + 1 hoist + 2 orchestration auditors + 1 annexe + 1 module reverse + 1 socle SQL — cf. §5)
- **Skills auto-triggered** (v7.0.0+ emprunt superpowers) : `@.sdd/skills/`, émis vers
  `.claude/skills/` par `harness_build.py --skills-only` (2026-11-07) — 13 skills (`using-sddpro`, `starting-a-new-feat`, `starting-a-reverse-eng`, `debugging-failed-pipeline`, `test-driven-development`, `frontend-design`, `webapp-testing`, `a11y-local`, `sarif-parsing`, `semgrep`, `codeql`, `insecure-defaults`, `c4-model`) — inventaire complet dans `@.sdd/skills-manifest.yaml`.
- **Invariants manifest** (v7.0.0+ audit P3 E4) : `@.sdd/INVARIANTS.yml` — 20 contrats load-bearing (two-stage gate, file ownership, cost cap, schema strict, TDD test-first, harness-parity, etc.) avec pointer vers chaque enforcer (hook/script/smoke test). Test `tests/test_invariants_manifest.py` vérifie que chaque enforcer existe sur disque. Anti-rot manifest : retirer un enforcer sans mettre à jour le manifest = FAIL au smoke.
- **Multi-harness / multi-provider** (réel, testé, **volontairement gaté** — documenté ici depuis l'audit 2026-08-29 : le système existait sans aucune mention dans cette page) : `.sdd/harness_build.py` transpile le foyer neutre `.sdd/` vers 4 adaptateurs — `claude-code` (façade `.claude/`, la seule utilisée au quotidien), `codex` (`.codex/prompts/`), `gemini-cli` (`.gemini/commands/`), `antigravity`. Providers déclarés dans `.sdd/providers/*.yaml` (`anthropic`, `openai`, `google`, `moonshot` : `tier_map`, `pricing`, rétention télémétrie). Tout combo harnais/provider non-Claude/Anthropic est marqué **`COMBO UNTESTED`** et bloqué par le hook `preflight_stack_combo` (bypass audit-loggué `SDD_ALLOW_UNTESTED_COMBO=1`) — présence ≠ support. Parité façade ↔ foyer enforcée par `tests/test_harness_facade_parity.py` (invariant `harness-parity`, `severity: critical`).
- **Python** : `@.sdd/python/README.md`
