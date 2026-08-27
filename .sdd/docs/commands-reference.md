# 💻 Commands Reference

**41 slash commands** : **13 user-facing** (the public API) + **9 internes [debug]** (low-level building blocks) + **19 reverse** (legacy code *and* database modules). Use the user-facing ones in everyday workflow ; the internal ones for debugging or surgical fixes.

> Recount at any time: `ls .sdd/commands/ | wc -l`.

| Quick legend |
|---|
| **User-facing** = orchestrating, handles preconditions + idempotence |
| **Interne [debug]** = a single agent invocation, no preconditions checks |
| `{n}` = FEAT number (e.g. `1`) — `{n}-{m}` = US id (e.g. `1-2`) |
| ✅ Idempotent = safe to re-run |

---

## 🚀 User-facing (13)

The 4 macro-orchestrators (`sdd-bootstrap`, `sdd-full`, `sdd-poc`, `sdd-review`) cover 90% of daily use.

### `/sdd-bootstrap`

| Field | Value |
|---|---|
| **Phase** | 0 (init) |
| **Args** | aucun |
| **Flags** | `--combo c1\|c2\|custom`, `--dry-run`, `--skip-install`, `--force` |
| **Agents spawn** | aucun (guide vers `python bootstrap.py`) |
| **Prerequisites** | repo cloné, `bootstrap.py` présent, Python 3.10+ |
| **Idempotent** | ✅ (read-only détection état) |
| **Outputs** | console (greenfield / partial / initialisé / template brut) |

**One-liner** : Détecte l'état d'un projet vierge et guide l'utilisateur vers `python bootstrap.py` pour générer `workspace/stack/stack.md`.

```bash
/sdd-bootstrap                  # détection + guide
/sdd-bootstrap --combo c1       # combo recommandé (auto)
```

**Quand l'utiliser** : Greenfield (repo cloné sans `stack.md`) ou re-init via `--force`. Pour brownfield, utiliser `/sdd-discover-stack`.

---

### `/feat-generate`

| Field | Value |
|---|---|
| **Phase** | 1 (cadrage) |
| **Args** | `[Nom]` (optionnel) |
| **Flags** | aucun |
| **Agents spawn** | aucun (Q/R interactif Claude) |
| **Prerequisites** | `stack.md` rendu (pas de `{{Placeholder}}`) |
| **Idempotent** | ❌ (incrémente `{n}`) |
| **Outputs** | `workspace/feats/{n}-{Name}.md`, `constitution.md §1-§3` bootstrap |

**One-liner** : Crée une FEAT pré-remplie via 2 séries de questions (besoin + cadrage) avec auto-numérotation `{n}`.

```bash
/feat-generate Auth
/feat-generate Reset-Password
```

**Quand l'utiliser** : Démarrer une nouvelle feature fonctionnelle après `/sdd-bootstrap`.

---

### `/feat-validate`

| Field | Value |
|---|---|
| **Phase** | 2.6 (readiness gate) |
| **Args** | `{n}` |
| **Flags** | `--json` (sortie machine pour CI) |
| **Agents spawn** | aucun (100% déterministe Python) |
| **Prerequisites** | FEAT `{n}` existe ; US recommandées |
| **Idempotent** | ✅ |
| **Outputs** | `.sys/.validation/{n}-readiness.md`, exit `0=GO / 0+WARN / 1=NO-GO` |

**One-liner** : Implementation Readiness Gate déterministe (structurel + sémantique) — 0 token, vérifie traçabilité IDs FEAT↔US, stacks actifs, mockups HTML.

```bash
/feat-validate 1
/feat-validate 1 --json  # for CI
```

**Quand l'utiliser** : Avant `/dev-run`/`/sdd-full` pour détecter les trous FEAT en amont (gate bloquante sauf `--force`).

---

### `/sdd-full` ⭐

| Field | Value |
|---|---|
| **Phase** | 2→5 (pipeline complet) |
| **Args** | `{n}` |
| **Flags** | `--force`, `--no-validate`, `--no-plan-on-warn`, `--rebuild-arch`, `--plan`, `--manual-gates[=us,plan,…]`, `--no-manual-gates`, `--resume` |
| **Agents spawn** | chaînage `/us-generate` → `/feat-validate` → (`/dev-plan`) → `/dev-run` → (`/qa-generate`) → (`/sdd-review`) |
| **Prerequisites** | FEAT `{n}` existe, `stack.md` initialisé |
| **Idempotent** | Partiel (skip arch sur FEATs ≥ 2 bootstrap stable) |
| **Outputs** | US, plans (opt-in), code back+front, rapports QA, review consolidé |

**One-liner** : Pipeline strict prod-ready A→Z pour 1 FEAT (US → readiness → plan opt-in → arch+DB → back → API gate → front → QA → review).

```bash
/sdd-full 1                              # voie principale prod
/sdd-full 1 --plan                       # avec review humain plans
/sdd-full 1 --resume                     # reprend depuis le dernier STEP
/sdd-full 1 --manual-gates=us,plan       # gates manuels après US + plan
```

**Quand l'utiliser** : Voie principale FEAT → code prêt-à-livrer. Utiliser `--plan` ≥ 2 US pour review humaine intermédiaire.

---

### `/sdd-poc`

| Field | Value |
|---|---|
| **Phase** | 1→4 (POC minimaliste) |
| **Args** | `{n}` |
| **Flags** | `--with-plans`, `--force`, `--rebuild-arch` |
| **Agents spawn** | `feat_to_pseudo_us.py` → `arch` → `dev-backend` → `dev-frontend` |
| **Prerequisites** | FEAT `{n}` existe, `stack.md` initialisé |
| **Idempotent** | Partiel |
| **Outputs** | pseudo-US `{n}-1-*`, code back+front minimal, bannière "ne pas déployer en prod" |

**One-liner** : Pipeline raccourci POC (saute US/QA/API-gate/review) — FEAT → arch → back → front en 1 seule pseudo-US.

```bash
/sdd-poc 1
```

**Quand l'utiliser** : Prototypes, démos, exemples jetables. Migration POC→prod via `/us-generate {n} --replace-pseudo` puis `/sdd-full`.

---

### `/dev-run`

| Field | Value |
|---|---|
| **Phase** | 4 (dev orchestration) |
| **Args** | `{n}` |
| **Flags** | `--force`, `--max-parallel N` (1-12, default 3), `--rebuild-arch` |
| **Agents spawn** | `arch`, `dev-backend` × N US (parallèle), `qa` (API Gate), `dev-frontend` × N US (parallèle) |
| **Prerequisites** | US générées, `stack.md` initialisé |
| **Idempotent** | ✅ |
| **Outputs** | code `src/{BackendName,AppName,LibName}/`, `schema.json`, ADRs, `api-tests.json` |

**One-liner** : Orchestre Phase 4 : arch+DB → dev-backend ALL US (parallèle) → QA API Gate → dev-frontend ALL US (parallèle), workflow gated séquentiel.

```bash
/dev-run 1
/dev-run 1 --max-parallel 3
/dev-run 1 --rebuild-arch
```

**Quand l'utiliser** : Après `/us-generate` quand on veut piloter Phase 4 sans Phase 5 QA.

---

### `/qa-generate`

| Field | Value |
|---|---|
| **Phase** | 5 (QA) |
| **Args** | `{n}` |
| **Flags** | `--mode {full\|tests-only\|tests+coverage\|quality-only}` |
| **Agents spawn** | `qa` (Sonnet 4.6) |
| **Prerequisites** | FEAT + US + code production matérialisé |
| **Idempotent** | ✅ |
| **Outputs** | `*.Tests/` ; télémétrie QA → `console.db` (`qa_coverage`/`qa_quality`/`qa_api_tests`) ; rapport à la demande `query_console_db.py feat-stats --feat {n} --format md` |

**One-liner** : Génère tests unitaires (back + front), parse coverage (déterministe), exécute quality scan sonar-like ; verdict 🟢/🟡/🔴 vs seuil `CoverageMin`.

```bash
/qa-generate 1
/qa-generate 1 --mode tests-only
```

**Quand l'utiliser** : Après `/dev-run` pour produire le verdict QA bloquant.

---

### `/sdd-review`

| Field | Value |
|---|---|
| **Phase** | audit (post-pipeline) |
| **Args** | `{n}` |
| **Flags** | `--skip-scans`, `--ensure-scans`, `--fail-on {info\|minor\|moderate\|serious\|critical}`, `--json`, `--adversarial` |
| **Agents spawn** | aucun direct (lit `console.db` + re-run `quality_scan.py`) ; `--adversarial` → `adversarial-reviewer` |
| **Prerequisites** | findings auditeurs persistés dans `console.db` |
| **Idempotent** | ✅ |
| **Outputs** | entry `validation_reports` (`console.db`) ; rapport à la demande `query_console_db.py review --feat {n} --format md` ; exit `0/1/3` |

**One-liner** : Audit qualité consolidé style Sonar — agrège tous les findings auditeurs, triage par owner (back/front/shared), verdict 🟢/🟡/🔴.

```bash
/sdd-review 1
/sdd-review 1 --ensure-scans         # re-run scans manquants
/sdd-review 1 --adversarial          # ajoute angle "avocat du diable"
/sdd-review 1 --fail-on serious      # override seuil
```

**Quand l'utiliser** : Après `/sdd-full` pour verdict consolidé bloquant. `--adversarial` pour FEATs sensibles.

---

### `/sdd-status`

| Field | Value |
|---|---|
| **Phase** | diagnostic |
| **Args** | `[{n}]` |
| **Flags** | aucun |
| **Agents spawn** | aucun |
| **Prerequisites** | aucun |
| **Idempotent** | ✅ (read-only strict) |
| **Outputs** | console (tree ASCII : FEATs, US, HTML, ARCH, DB, QA verdict) |

**One-liner** : Diagnostic read-only du pipeline SDD — état FEATs/US/mockups/code/QA en tree compact.

```bash
/sdd-status              # toutes FEATs
/sdd-status 1            # 1 FEAT
```

**Quand l'utiliser** : N'importe quand pour visualiser l'avancement sans risque (0 token, ~50 ms).

---

### `/sdd-help`

| Field | Value |
|---|---|
| **Phase** | guidance |
| **Args** | `[{n}\|"question"]` |
| **Flags** | aucun |
| **Agents spawn** | aucun |
| **Prerequisites** | aucun |
| **Idempotent** | ✅ (read-only strict) |
| **Outputs** | console (guidance contextuelle "what's next") |

**One-liner** : Aide contextuelle read-only — lit l'état du pipeline et suggère la prochaine commande (emprunt bmad-help).

```bash
/sdd-help                 # what's next (global)
/sdd-help 1               # what's next pour la FEAT 1
/sdd-help "comment relancer le backend ?"
```

**Quand l'utiliser** : Quand `/sdd-status` montre où on en est mais qu'on ne sait pas quelle commande lancer ensuite.

---

### `/sdd-discover-stack`

| Field | Value |
|---|---|
| **Phase** | onboarding (brownfield) |
| **Args** | aucun |
| **Flags** | `--scope <path>`, `--force` (overwrite `stack.md` existant) |
| **Agents spawn** | aucun (scripts déterministes) |
| **Prerequisites** | repo à scanner (manifests `package.json`/`csproj`/`pom.xml`/etc.) |
| **Idempotent** | ✅ |
| **Outputs** | `stack.md.candidate` (ou `stack.md` avec `--force`), `.sys/.audit/{scan,match}-report.json` |

**One-liner** : Scanne un repo brownfield, matche les manifests contre le catalogue SDD_Pro, produit un `stack.md.candidate` à arbitrer.

```bash
/sdd-discover-stack
/sdd-discover-stack --scope ./apps/web
```

**Quand l'utiliser** : Onboarding d'un repo existant pré-SDD_Pro.

---

### `/sdd-serve`

| Field | Value |
|---|---|
| **Phase** | runtime |
| **Args** | aucun OU `back`, `front`, `console` (combinables) |
| **Flags** | aucun |
| **Agents spawn** | aucun (lance commandes de run du stack en background) |
| **Prerequisites** | code généré, Project Config lisible |
| **Idempotent** | Partiel (risque double process si ports tenus) |
| **Outputs** | 3 process background (Spring/Vite/Fastify console) |

**One-liner** : Lance backend + frontend + console SDD en parallèle (ex-`/sdd-run` renommée v7.0.0).

```bash
/sdd-serve                # tout
/sdd-serve back front     # uniquement back + front
```

**Quand l'utiliser** : Tester runtime le code généré après `/sdd-full`. Read-only sur le code.

---

### `/sdd-kill-server`

| Field | Value |
|---|---|
| **Phase** | runtime |
| **Args** | aucun OU `back`, `front`, `console` |
| **Flags** | `--port <N>` (kill un port arbitraire) |
| **Agents spawn** | aucun |
| **Prerequisites** | Project Config (lecture ports) |
| **Idempotent** | ✅ |
| **Outputs** | console (1 ligne par port killé / not running) |

**One-liner** : Pendant de `/sdd-serve` — arrête les 3 process runtime via résolution port stack-aware.

```bash
/sdd-kill-server
/sdd-kill-server --port 5185
```

**Quand l'utiliser** : Cleanup après `/sdd-serve`, ou tuer des processes orphelins après crash.

---

## 🔧 Internes [debug] (9)

Building blocks invoked by the user-facing commands. Use these for **targeted debugging** when an orchestrator fails — but prefer the orchestrator for normal flow.

### `/us-generate`

| Field | Value |
|---|---|
| **Phase** | 2 (US) |
| **Args** | `{n}` |
| **Flags** | `--allow-large-feat` (bypass hard cap 10 US) |
| **Agents spawn** | `po` (Sonnet 4.6) |
| **Outputs** | `us/{n}-{m}-{Name}.md` (1-6 fichiers) |

```bash
/us-generate 1
```

**Quand l'utiliser** : Debug isolé du découpage US. Préférer `/sdd-full` en usage normal.

---

### `/arch-init`

| Field | Value |
|---|---|
| **Phase** | 3 (arch) |
| **Args** | aucun |
| **Flags** | aucun |
| **Agents spawn** | `arch` (Sonnet 4.6), puis `constitutioner` si sentinel posé |
| **Outputs** | `src/{BackendName,AppName,LibName}/`, `.sln`, `db/schema.{json,md}`, ADRs |

```bash
/arch-init
```

**Quand l'utiliser** : Debug isolé du bootstrap. Préférer `/dev-run` ou `/sdd-full`.

---

### `/dev-plan`

| Field | Value |
|---|---|
| **Phase** | 2.7 (planning) |
| **Args** | `{n}` |
| **Flags** | aucun |
| **Agents spawn** | `dev-backend` + `dev-frontend` en mode `:plan` (parallèle, par US) |
| **Outputs** | `plans/{n}-{m}-{Name}.{back\|front}.md` |

```bash
/dev-plan 1
```

**Quand l'utiliser** : Valider/éditer le découpage technique avant `/dev-run`.

---

### `/dev-backend`

| Field | Value |
|---|---|
| **Phase** | 4 (dev) |
| **Args** | `{n}-{m}` (1 US) |
| **Flags** | aucun |
| **Agents spawn** | `dev-backend` (**Opus 4.8**) |
| **Outputs** | `src/{BackendName}/`, `{LibName}/` (via lock) |

```bash
/dev-backend 1-3
```

**Quand l'utiliser** : Debug ciblé d'1 US backend.

---

### `/dev-frontend`

| Field | Value |
|---|---|
| **Phase** | 4 (dev) |
| **Args** | `{n}-{m}` (1 US) |
| **Flags** | aucun |
| **Agents spawn** | `dev-frontend` (**Opus 4.8**) |
| **Outputs** | `src/{AppName}/` (Pages, Components, theme.css) |

```bash
/dev-frontend 1-2
```

**Quand l'utiliser** : Debug ciblé d'1 US frontend.

---

### `/feat-deepen`

| Field | Value |
|---|---|
| **Phase** | 1.5 (post-cadrage élicitation) |
| **Args** | `{n}` |
| **Flags** | `--quick` (one-shot inférence, sans Q/R) |
| **Agents spawn** | `elicitor` (Sonnet 4.6) |
| **Outputs** | append FEAT (FAIL/EDGE/RACI/RedTeam sections), `constitution.md §7` |

```bash
/feat-deepen 1
/feat-deepen 1 --quick
```

**Quand l'utiliser** : Après `/feat-generate` pour features critiques, AVANT `/us-generate`.

---

### `/doc-refresh`

| Field | Value |
|---|---|
| **Phase** | debug / fin de pipeline auto |
| **Args** | aucun |
| **Flags** | aucun |
| **Agents spawn** | aucun (`index_adrs.py` déterministe, 0 token, ~50 ms) |
| **Outputs** | `adrs/INDEX.md` |

```bash
/doc-refresh
```

**Quand l'utiliser** : Manuel après édition ADR. Auto en fin de `/sdd-full`, `/dev-run`, `/qa-generate`.

---

### `/sdd-profile`

| Field | Value |
|---|---|
| **Phase** | gouvernance / ops |
| **Args** | `export <name>` / `import <name>` / `list` / `show <name>` / `delete <name>` |
| **Flags** | `--force` (sur `export`) |
| **Agents spawn** | aucun |
| **Outputs** | `~/.sdd/profiles/{name}.yml`, overwrite `~/.sdd/config.team.yml` à l'import |

```bash
/sdd-profile list
/sdd-profile export strict-prod
/sdd-profile import strict-prod
```

**Quand l'utiliser** : Outil ops gouvernance team config. Aucun effet pipeline en cours.

### `/spec-book`

| | |
|---|---|
| **Args** | `{n}` (FEAT number) — optional, all FEATs if omitted |
| **Agent** | `specbook-writer` |
| **Role** | Functional specification book in plain language, for a non-IT reader (manager, sponsor). Vulgarises the technical content without deleting it. |
| **Outputs** | `workspace/docs/` (`.docx` + `.md`), section cache in `workspace/docs/.sys/sections/` |
| **Notes** | Works on forward **and** reverse FEATs. The final `.docx` render is produced by the deterministic script `generate_specbook.py` (0 tokens). |

---

## 🗄️ Reverse engineering (19)

Optional module: turn what you already have into FEATs. Full workflow:
[reverse-engineering-workflow.md](reverse-engineering-workflow.md).

### Database path (3)

| Command | Role |
|---|---|
| `/sdd-db-context` **(Phase 0 — mandatory)** | Builds the versioned *Database Context*: deterministic facts (tables, keys, `CHECK`, CRUD matrix, call graph, wave plan) then interpretation by `reverse-db-architect` (glossary, sub-domains, risks). Produces `db-context.json` + a per-object Markdown tree reused as long as the database has not changed. Flags: `--refresh`, `--no-architect` (facts only, 0 tokens), `--diff-against`, `--json`. |
| `/sdd-db-reverse-full` | Every executable SQL object of the database — procedures, functions, views, triggers (+ Oracle packages). 1 SQL object = 1 User Story, 1 module = 1 FEAT. Scope guards: `--schema`, `--include`, `--exclude`, `--limit`. |
| `/sdd-db-reverse {object}` | A single object, to evaluate the module without committing to a full run. |

Engines: SQL Server + PostgreSQL 🟢 live-validated ; Oracle + MySQL/MariaDB 🟡
scaffold-validated. **Read-only always** — the ban is enforced by `readonly_guard`
and the blocking class `[DB_STRUCTURE_CHANGE_FORBIDDEN]`.

### Legacy code path (16)

| Command | Role |
|---|---|
| `/sdd-reverse-full` | Full orchestrator (phases 0→5), resumable phase by phase |
| `/sdd-reverse {U-N}` | Sequencer for one unit: 3a analysis → 3b User Stories → 3c FEAT |
| `/sdd-reverse-init` | Bootstraps `workspace/old/{Project}/.sys/` |
| `/sdd-reverse-inventory` | Phase 1 — deterministic cartography (blocking for phase 3) |
| `/sdd-reverse-audit` | Phase 2 — architecture / anti-patterns / EOL audit (informational) |
| `/sdd-reverse-paradigm` | Paradigm gap + unit curation (MIGRATE / DISCARD / HUMAN-DECISION) |
| `/sdd-reverse-analyze` | 3a — faithful technical analysis of one unit |
| `/sdd-reverse-stories` | 3b — lift into User Stories |
| `/sdd-reverse-feat` | 3c — business FEAT composition |
| `/sdd-reverse-crosscut` | Cross-cutting deterministic FEATs (libraries, database) — 0 tokens |
| `/sdd-reverse-synth` | System synthesis: C4, full ERD, `soul.md` — deterministic, 0 tokens |
| `/sdd-reverse-parity` | Gherkin parity specs (opt-in, `--with-parity`) |
| `/sdd-reverse-questions` | Human validation loop (`--ingest` to re-inject the answers) |
| `/sdd-reverse-review` | Back completeness review of one reverse FEAT (informational) |
| `/sdd-reverse-ui` | Phase 4 — semantic HTML mockup extraction |
| `/sdd-reverse-status` | Reverse workflow diagnostic (read-only) |

> 🚪 **REVERSE-GATE** — a reverse FEAT whose confidence is not `high` does **not** enter
> `/sdd-full` (exit 1). The override (`--allow-reverse-low`) exists, but it is explicit
> and audit-logged.

---

## 🗺 Decision tree

```
                ┌─ Greenfield repo (vide)
                │      → /sdd-bootstrap
                │
                ├─ Brownfield repo (existant)
                │      → /sdd-discover-stack
                │
                ├─ Nouvelle feature
                │      → /feat-generate Nom
                │      → /feat-deepen N      (opt — features critiques)
                │      → /sdd-full N         (pipeline complet)
                │
                ├─ POC rapide / démo
                │      → /sdd-poc N
                │
                ├─ Audit qualité d'une FEAT existante
                │      → /sdd-review N --ensure-scans
                │      → /sdd-review N --adversarial   (FEATs sensibles)
                │
                ├─ État du projet
                │      → /sdd-status [N]
                │
                ├─ Lancer le code généré
                │      → /sdd-serve
                │      → /sdd-kill-server
                │
                ├─ Base de données legacy à récupérer
                │      → /sdd-db-context            (Phase 0, obligatoire)
                │      → /sdd-db-reverse-full       (--schema / --limit au 1er run)
                │
                ├─ Code source legacy à récupérer
                │      → /sdd-reverse-full
                │
                ├─ Cahier des charges pour un lecteur non-IT
                │      → /spec-book [N]
                │
                └─ Debug ciblé
                       → /dev-backend N-M / /dev-frontend N-M
                       → /qa-generate N
                       → /dev-plan N (review humain)
```

---

## 🔗 See also

- [agents-reference.md](agents-reference.md) — what each agent does
- [configuration-reference.md](configuration-reference.md) — flags' impact on config
- [workflow.md](workflow.md) — pipeline phase order
- [troubleshooting.md](troubleshooting.md) — error class → fix mapping
