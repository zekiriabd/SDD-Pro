# SDD_Pro v7.0.0-alpha (branche `next`) — FEAT-Driven Development pour Claude Code

> ⛔ **FREEZE actif jusqu'au 2026-06-18** sur `main` (v6.10.4-LTS).
> Sur `next` : v7.0.0-alpha en cours (auditors-trim, prompts-trim,
> stacks quarantine, migration infra). Cf. `@.claude/VERSIONING.md §4`
> + `@.claude/CHANGELOG.md` § Unreleased v7.0.0.

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

**8 user-facing** (v7.0.0 — orchestrent le pipeline complet, gèrent
pré-conditions et idempotence) :

| Commande | Phase | Rôle |
|---|---|---|
| `/feat-generate [Nom]` | 1 | Cadrage FEAT + bootstrap constitution |
| `/feat-validate {n} [--json]` | 2.6 | Implementation Readiness Gate |
| `/sdd-full {n}` | 2→5 | Pipeline complet A→Z |
| `/qa-generate {n}` | 5 | Tests + coverage + quality scan |
| `/sdd-review {n} [--ensure-scans] [--fail-on …]` | audit | Audit consolidé (style Sonar, v7.0.0 bloquant RED) |
| `/sdd-status [{n}]` | diagnostic | État pipeline (read-only) |
| `/sdd-discover-stack` | onboarding | Scan repo → `stack.md.candidate` |
| `/sdd-run` | runtime | Lance backend + frontend + console en parallèle |

**9 internes v7.0.0** (invoquées par les commandes orchestrantes
ci-dessus, conservées comme slash commands pour debug/inspection
ciblée ; **utilisateur final : préférer une commande orchestrante**) :

| Commande | Invoquée par | Rôle |
|---|---|---|
| `/us-generate {n}` | `/sdd-full STEP 2` | FEAT → User Stories (agent PO) |
| `/arch-init` | `/dev-run STEP 5` | Bootstrap projet + DB scaffolding |
| `/dev-plan {n}` | `/sdd-full STEP 3.6` | Plans techniques pré-dev |
| `/dev-run {n}` | `/sdd-full STEP 4` | Orchestrateur dev (arch + back + API + front) |
| `/dev-backend {n}-{m}` | `/dev-run STEP 6.a` | Code serveur 1 US |
| `/dev-frontend {n}-{m}` | `/dev-run STEP 6.c` | Code client 1 US |
| `/doc-refresh` | fin pipeline | INDEX.md ADRs (script `index_adrs.py`) |
| `/feat-deepen {n}` | manuel | Élicitation 5 techniques (sera fusionné dans `/feat-generate --deepen` post-v7.0.0) |
| `/sdd-profile {cmd}` | gouvernance | Snapshots config team (script `manage_profile.py`) |

> Flags `/sdd-full` et `/dev-run` : `--force`, `--rebuild-arch`, `--resume`, `--manual-gates`, `--plan`, `--max-parallel N`. Pour la sémantique exhaustive : `@.claude/commands/*.md`.

---

## 4. Agents

**4 cœur** : `po`, `arch` (Sonnet 4.6) ; `dev-backend`, `dev-frontend` (Opus 4.7).
**Support** (3) : `elicitor`, `constitutioner`, `qa` (Sonnet 4.6).
**Auditors** (4 après v7.0.0 trim, Sonnet 4.6) : `code-reviewer`, `security-reviewer` (mode `scan` uniquement), `spec-compliance-reviewer`, `arch-reviewer`.
**Rendering** : `dashboard` (Haiku 4.5) **retiré v7.0.0** — remplacé par script `sdd_scripts/index_adrs.py` (0 token, ~50 ms).

> **Retirés en v7.0.0** (cf. `ADR-20260519T120000-governance-major-auditors-trim`) :
> - `accessibility-auditor` (Haiku 4.5) → remplacé par **axe-core** intégré au CI du projet généré.
> - `performance-auditor` (Sonnet 4.6) → remplacé par **Lighthouse CI** + benchmark wrk/k6 au CI.
> - `security-reviewer` mode `threat-model` → remplacé par **template humain** (`templates/threat-model.template.md`, à instancier par le Tech Lead pré-dev).
> - `dev-backend-strict` / `dev-frontend-strict` → routing strict supprimé (plan v2 + `## Inline Digest` préservés pour review humaine).

> Détail modèles, rôles, phases, isolation reads/writes : `@.claude/docs/architecture.md §2-§3`.
> Tous autonomes (aucune question utilisateur). Ambiguïté → `STOP + ERROR [CLASS]`.
> Méta-orchestrateur : `phase_planner.py` décide quelles auditors tourner par FEAT.
> Notes opérationnelles par version : `@.claude/docs/version-notes.md`.

---

## 5. Règles

**5 règles cross-cutting consolidées v7.0.0** dans `.claude/rules/`
(codex audit Prio 2 — was 11) :

| Nouvelle règle | Substance |
|---|---|
| `build-and-loop.md` | Backend-first gated workflow + Dev-shared patterns (was `backend-first` + `dev-shared`) |
| `quality.md` | QA Coverage seuil + UI Tokens anti-hex (was `qa-coverage` + `ui-tokens`) |
| `ownership.md` | File ownership matrix + Constitution & ADRs governance (was `file-ownership` + `constitution`) |
| `library-and-stack.md` | Stack completeness (libs anti-derive, runtime LTS) + CORS patterns (was `stack-completeness` + `cors`) |
| `error-classification.md` | Vocabulaire d'erreur unifié `[CLASS]` cross-agent (unchanged) |

**8 stubs** préservés (backward-compat des `Read @.claude/rules/X.md`
historiques dans agents) : `backend-first`, `dev-shared`, `qa-coverage`,
`ui-tokens`, `file-ownership`, `constitution`, `stack-completeness`,
`cors`. Chaque stub pointe vers la nouvelle règle consolidée.

**2 principes** déplacés vers `.claude/docs/principles/` : `source-first`
(Tech Lead discipline, non cross-agent), `us-granularity` (mono-agent po).
Stubs aussi conservés dans `rules/`.

> **Migration utilisateur** : les agents continuent de Read les anciens
> paths via stubs (zéro régression). Post-v7.0.0 final, sweep des
> `Read @.claude/rules/X.md` vers les nouveaux paths, puis suppression
> des stubs en v7.1.

Index commenté + détail : `@.claude/docs/conventions.md §14`.

---

## 6. Templates

Liste : `@.claude/docs/conventions.md §15`.

---

## 7. Stacks supportés

**16 stacks actifs + 1 pattern archi** (post-quarantaine v7.0.0) :

| Catégorie | Stacks 🟢 reference | 🟡 Phase 2 (experimental ou non déclaré) |
|---|---|---|
| Backend (4) | `dotnet-minimalapi`, `kotlin-spring-boot` | `python-fastapi`, `node-express` |
| Frontend (4) | `react`, `blazor-webassembly` | `vue`, `angular` |
| UI DS (3) | `shadcn` | `vuetify`, `radzen-blazor` ⚠️ |
| QA (7) | `code-quality` | `dotnet-xunit` ⚠️, `kotlin-junit` ⚠️, `node-vitest` ⚠️, `blazor-bunit` ⚠️, `python-pytest` ⚠️, `angular-jasmine` ⚠️ |
| Auth (2) | `azure-ad` | `auth-local` |
| Archi (1) | `mvc` | — |

> **Quarantaine v7.0.0** — 10 stacks déplacés vers `.claude/stacks/_drafts/` : 6 fullstack (`node-react`, `blazor-server`, `next`, `nuxt`, `angular-universal`, `kotlin-mustache`), 2 mobiles (`react-native`, `maui`), 2 archi (`ddd`, `microservice`). **Non chargés par le framework actif**. Voir `.claude/stacks/_drafts/README.md` pour la procédure de réactivation. ADR `governance-major-stacks-quarantine`.

> **Vérité terrain** : 🟢 = stack avec entête `Validation: 🟢 reference` ET inclus dans un combo validé bout-en-bout. 🟡 = entête `Validation: 🟡 experimental`. ⚠️ = stack **sans entête `Validation:`** (7 cas — drift documentaire à corriger en post-freeze, classés 🟡 par défaut conservateur). La source de vérité reste l'entête `Validation:` de chaque `.claude/stacks/{cat}/{id}.md`.

**AppType auto-détecté** depuis `## Active Tech Specs` (v6.7.7+) : `backend/* + frontend/*` → `back-front/web` ; `+ mobiles/*` → `back-front/mobile` ; `fullstack/*` seul → `fullstack`. Mix interdits → `[STACK_COMBO_INVALID]`.

**Pattern d'archi backend** déclaré dans `## Active Architecture Pattern` (scope `back-front` avec backend uniquement). Défaut MVC.

**Combos validés bout-en-bout : 2** (sur ~120 combinaisons possibles) :
- `dotnet-minimalapi × react × shadcn × dotnet-xunit × azure-ad`
- `kotlin-spring-boot × react × shadcn × kotlin-junit × azure-ad`

Hors ces 2 combos, la composition n'a pas été validée par un PoC complet `/sdd-full` ; le pipeline peut échouer en runtime de manière non triviale. Pour une 3ème combo, exécuter d'abord le PoC ROI méthodologie (cf. `@.claude/docs/poc-roi-methodology.md`).

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
- ~~`@.claude/docs/DESIGN-FROMPLAN-STRICT.md`~~ — retiré v7.0.0 (variants strict supprimés)
- `@.claude/docs/MCP-SERVER.md` — serveur MCP (clients tiers)
- `@.claude/VERSIONING.md` — SemVer + freeze window
- `@.claude/CHANGELOG.md` — historique versions
- `@.claude/MIGRATION.md` — guide migration
- `@.claude/WORKING-AGREEMENT.md` — autorisations + limites
- `@.claude/rules/` — 9 règles cross-cutting (v7.0.0, 2 principes déplacés en `docs/principles/`)
- `@.claude/python/README.md` — scripts utilitaires
