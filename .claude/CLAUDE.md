# SDD_Pro v7.0.0-alpha (branche `next`) — FEAT-Driven Development pour Claude Code

> ⛔ **FREEZE 2026-06-18** sur `main` (v6.10.4-LTS). Sur `next` : v7.0.0-alpha
> (auditors-trim, prompts-trim, stacks quarantine). Cf. `@.claude/VERSIONING.md`
> + `@.claude/CHANGELOG.md`.

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

## 3. Commandes (10 user-facing + 8 internes [debug])

**User-facing** (orchestrantes, gèrent pré-conditions et idempotence) :

| Commande | Phase | Rôle |
|---|---|---|
| `/feat-generate [Nom]` | 1 | Cadrage FEAT + bootstrap constitution |
| `/feat-validate {n} [--json]` | 2.6 | Implementation Readiness Gate |
| `/sdd-full {n}` | 2→5 | Pipeline complet A→Z |
| `/dev-run {n}` | 4 | Orchestrateur dev (arch+DB → back → API gate → front) |
| `/qa-generate {n}` | 5 | Tests + coverage + quality scan |
| `/sdd-review {n}` | audit | Audit consolidé (style Sonar, bloquant RED) |
| `/sdd-status [{n}]` | diagnostic | État pipeline (read-only) |
| `/sdd-discover-stack` | onboarding | Scan repo → `stack.md.candidate` |
| `/sdd-serve` | runtime | Backend + front + console parallèle (ex-`/sdd-run`) |
| `/sdd-kill-server` | runtime | Arrête backend + front + console (pendant de `/sdd-serve`) |

**Internes** (8, debug/inspection — préférer une commande orchestrante,
ces commandes sont stables mais réservées au troubleshooting ciblé) :
`/us-generate`, `/arch-init`, `/dev-plan`, `/dev-backend`, `/dev-frontend`,
`/doc-refresh`, `/feat-deepen`, `/sdd-profile`.

> Flags `/sdd-full` et `/dev-run` : `--force`, `--rebuild-arch`, `--resume`,
> `--manual-gates`, `--plan`, `--max-parallel N`. Détail : `@.claude/commands/*.md`.

---

## 4. Agents (11)

**Cœur** : `po`, `arch` (Sonnet 4.6) ; `dev-backend`, `dev-frontend` (Opus 4.7).
**Support** : `elicitor`, `constitutioner`, `qa` (Sonnet 4.6).
**Auditors** : `code-reviewer`, `security-reviewer` (mode `scan`),
`spec-compliance-reviewer`, `arch-reviewer` (Sonnet 4.6).

> Retirés v7.0.0 : `accessibility-auditor` (→ axe-core CI), `performance-auditor`
> (→ Lighthouse CI + wrk/k6), `dashboard` (→ `index_adrs.py`), variants
> `*-strict`. Méta-orchestrateur : `phase_planner.py`. Détail :
> `@.claude/docs/architecture.md §2-§3`.

---

## 5. Règles & Templates

`.claude/rules/` (7 fichiers, 5 actives + 2 annexes) :
- **5 règles consolidées v7.0.0** : `build-and-loop`, `quality`,
  `ownership`, `library-and-stack`, `error-classification`
- **1 hoist cross-agent** : `dev-shared-preflight.md` (STEP 0-1.bis
  partagés dev-backend / dev-frontend)
- **1 stub héritage** : `error-classification-legacy.md` (préfixes
  `[A11Y_*]`/`[PERF_*]` archivés pour ingest CI futur — axe-core,
  Lighthouse)

**2 principes** dans `.claude/docs/principles/` : `source-first`,
`us-granularity`. Templates : `@.claude/docs/conventions.md §14-§15`.

---

## 6. Stacks (24 actifs + 9 drafts)

| Catégorie | 🟢 reference | 🟡 experimental |
|---|---|---|
| Backend (4) | `dotnet-minimalapi`, `kotlin-spring-boot` | `python-fastapi`, `node-express` |
| Frontend (4) | `react`, `blazor-webassembly` | `vue`, `angular` |
| UI DS (3) | `shadcn` | `vuetify`, `radzen-blazor` |
| QA (9) | `code-quality`, `dotnet-xunit`, `kotlin-junit` | `node-vitest`, `blazor-bunit`, `python-pytest`, `angular-jasmine`, `mutation-testing` (opt-in), `playwright` (opt-in) |
| Auth (2) | `azure-ad` | `auth-local` |
| Archi (2) | `mvc` | `ddd` |

**9 drafts** dans `.claude/stacks/_drafts/` (6 fullstack, 2 mobiles, 1 archi
`microservice` — non chargés). **Combos validés bout-en-bout : 2** sur ~120
(`dotnet-minimalapi×react×shadcn×dotnet-xunit×azure-ad`,
`kotlin-spring-boot×react×shadcn×kotlin-junit×azure-ad`).

> Source de vérité = entête `Validation:` de chaque stack. AppType
> auto-détecté depuis `## Active Tech Specs`. Catalogue machine
> `{id}.libs.json` régénéré via `sync_stack_md.py`. Détail combos,
> capabilities, drafts : `@.claude/docs/architecture.md §4` +
> `@.claude/docs/validated-combos.md`.

---

## 7. Conventions strictes

Anti-derive, format ERROR 3 lignes, idempotence, lecture sélective,
parallélisme borné (`MaxParallel: 3`), plan inline, CLAUDE.md par projet,
capabilities core vs on-demand, chat output minimal, gates manuels opt-in.
Détail : `@.claude/docs/conventions.md §1-§13`.

---

## 8. Loader manifest

`@.claude/loader.yml` = miroir consolidé reads/writes par agent. Régénéré
déterministiquement v7.0.0 (ADR `governance-major-config-ssot`).

---

## 9. Démarrage rapide

1. Éditer `workspace/input/stack/stack.md` (`## Project Config`,
   `## Active Database`, `## Active Auth Specs`).
2. `/feat-generate Auth` — répondre aux 3-6 questions.
3. (Optionnel) déposer mockups HTML dans `workspace/input/ui/`.
4. `/sdd-full 1` — pipeline complet.
5. `/sdd-status [{n}]` — vérifier.

Variantes : `@.claude/docs/quickstart.md`.

---

## 10. Pour aller plus loin

- `@.claude/docs/` — architecture, workflow, conventions, quickstart,
  version-notes, MCP-SERVER, validated-combos, roadmap-v7-v8,
  orphan-cleanup-policy (ADR `governance-orphan-cleanup-tool`),
  principles/
- `@.claude/rules/` — 5 règles cross-cutting + 1 hoist preflight + 1 stub héritage
- `@.claude/VERSIONING.md`, `@.claude/CHANGELOG.md`, `@.claude/MIGRATION.md`,
  `@.claude/WORKING-AGREEMENT.md` (pleine autorisation SDD_Pro, 3 limites),
  `@.claude/python/README.md`
