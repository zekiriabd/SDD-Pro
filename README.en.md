# SDD_Pro

FEAT-driven development framework — **multi-harness** (Claude Code, OpenAI Codex, Gemini CLI, Antigravity) — **v7.0.3-dev** (base v7.0.0 GA 2026-06-07). LTS baseline v6.10.x kept until 2026-12-31. See [VERSIONING](.sdd/docs/VERSIONING.md) · [CHANGELOG](.sdd/docs/CHANGELOG.md).

> **New in v7.0.3-dev**: parallel audit (code + security + arch reviewers run simultaneously),
> adversarial reviewer active by default (use `--no-adversarial` to skip), IDE statusline showing
> current phase + cost + tokens, `plugin.json` marketplace manifest, Haiku tier for mechanical
> agents (constitutioner, elicitor).

> ⚠ **This English page is a summary, not a translation.** It covers Quickstart + Console essentials only (~10 sections vs ~17 in the French canonical README). For exhaustive docs (architecture, agents, rules, stacks, governance, ROI, roadmap), use the French source.
>
> 🗄️ **Sitting on a legacy database rather than a greenfield project?** SDD_Pro reads your stored procedures, functions, views, triggers and jobs **read-only** and returns them as workable specifications — [see Database reverse engineering](#-database-reverse-engineering--your-schema-becomes-a-specification-again).

> 🇫🇷 [Version française (canonical, complete)](README.md) — Main documentation: [.claude/CLAUDE.md](.claude/CLAUDE.md) (French).

---

## 🚀 Quickstart — new project

**Recommended: use this repo as a [GitHub Template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository).** Click **"Use this template"** → "Create a new repository" → clone locally → run the interactive bootstrap:

```bash
# macOS / Linux
python3 bootstrap.py

# Windows (PowerShell or cmd)
python bootstrap.py

# Non-interactive (CI / scripted) — uses validated combo C1
python bootstrap.py --combo c1 --skip-install
```

The bootstrap:
- Asks the project name + 3-4 questions (stack, DB, auth)
- Generates `workspace/stack/stack.md` (43 Project Config keys, safe defaults)
- Creates the full `workspace/.sys/` directory structure
- Installs Python deps (`pip install -e .sdd/python[dev]`)
- Offers to install the console deps (`npm install` in `workspace/console/`)
- Runs a final smoke check

Validated end-to-end combos:
- **C1**: .NET Minimal API + React + shadcn + Azure AD + xUnit (recommended)
- **C2**: Kotlin Spring Boot + React + shadcn + Azure AD + JUnit
- `--combo custom`: manual composition (4 backends × 4 frontends × 3 UI systems)

---

## After bootstrap

1. Edit secrets in [workspace/stack/stack.md](workspace/stack/stack.md) (DB password, Azure AD client ID, etc.) — this file is gitignored.
2. In Claude Code: `/feat-generate <Name>` — answer the 3-6 elicitation questions.
3. *(Optional)* drop HTML mockups under `workspace/ui/{n}-{m}-{Name}.html`.
4. `/sdd-full {n}` — full pipeline (PO → arch → dev-back → API gate → dev-front → QA → reviewers).
5. `/sdd-status [{n}]` — diagnostic.

---

## 🗄️ Database reverse engineering — your schema becomes a specification again

> **Your company's business logic is asleep inside your database.**
> Hundreds of stored procedures written over fifteen years, by developers who
> have long since left. No documentation. Nobody dares touch it.
> **SDD_Pro reads it — strictly read-only — and hands you specifications.**

One command, `/sdd-db-reverse-full`, connects using the connection string declared in
`stack.md ## Active Database`, inventories **everything the database knows how to do**,
and produces standard SDD_Pro FEATs — immediately consumable by `/sdd-full` to
regenerate an application on top. Your SQL estate stops being a black box and becomes
a readable, traceable, version-controlled backlog.

### What is actually extracted

| Object family | Treatment |
|---|---|
| **Stored procedures** | body analysed → **1 User Story** |
| **Functions** (scalar, inline, table-valued) | body analysed → **1 User Story** |
| **Views** and **triggers** | body analysed → **1 User Story** |
| **Oracle packages** (spec + body) | body analysed → **1 User Story** |
| **Tables, columns, types, PK/FK, indexes, `CHECK` constraints** | live introspection → `db-schema.json` |
| **Jobs / scheduler, sequences, synonyms, linked servers, user types** | live introspection → `catalogObjects` |

> 💡 **What other tools miss.** `CHECK` constraints and **scheduled jobs** are the two
> largest reservoirs of business rules that are *invisible from application code*: a job
> carries night-time behaviour (recalculation, purge, import) that nothing in the app
> reveals. SDD_Pro surfaces them alongside procedures.

### The model, in one line

**1 SQL object = 1 User Story · 1 business module = 1 FEAT.** No merging, no invention,
no summary that flattens the detail away.

```
stack.md (## Active Database)
   └─ Phase 1 — READ-ONLY introspection (0 tokens)
        ├─ SQL body snapshots + db-schema.json + inventory.json
        └─ clustering into business modules (AUTO strategy, measured on YOUR object names)
             └─ Rung 1 — reverse-sql-analyst × module (LLM, bounded parallelism)
                  └─ Rung 2 — FEAT composition (deterministic, or LLM opt-in)
                       └─ REVERSE-GATE ─► /sdd-full
```

### A team of specialised agents, not one giant prompt

The reverse module ships **12 dedicated agents**, **2 of them SQL experts** on the
database path — each with a locked read scope and a single mandate:

| Agent | Mandate |
|---|---|
| **`reverse-sql-analyst`** *(rung 1)* | Multi-dialect expert (T-SQL, PL/pgSQL, PL/SQL, MySQL/PSM, SQL PL). Reads a module's bodies and derives one User Story per object: observed behaviour, acceptance criteria drawn from the real control flow, `file:line` evidence, confidence capped per language. |
| **`reverse-sql-feat-composer`** *(rung 2, opt-in)* | Synthesises a module's business FEAT: cross-cutting narrative, technical plumbing demoted. Worth it for logic-heavy modules — plain CRUD is served fine by the deterministic assembler. |
| **`reverse-completeness-reviewer`** | Confronts the produced FEAT with the raw inventory and **states what the extraction missed**. Informational verdict, never complacent. |
| **`reverse-clarifier`** | Turns grey areas into structured questions for the Tech Lead, then feeds the answers back into the FEATs. No answer is ever invented. |

Agents run with **bounded parallelism** (`MaxParallel`, default 3) over disjoint writes.
No agent spawns another — the command orchestrates, so the bill stays predictable.

### 70–80% of your database costs zero tokens

This is the economic core of the module. Before any LLM is called, a **deterministic
router** classifies every object:

- **simple object** (CRUD / SELECT, no branching, no dynamic SQL, no error handling)
  → its User Story is generated **mechanically, at zero cost**;
- **complex object** (real business logic) → only then is an agent woken up.

On top of that: a **per-object cache** (an unchanged body is never re-analysed, so a
second run after an interruption is near-free) and scope guards (`--schema`,
`--include`, `--exclude`, `--limit`) that **always name what they left out** — never a
silent truncation.

### Module clustering is measured, not guessed

It is the most structural decision of the whole reverse: it sets the number of FEATs.
SDD_Pro **profiles your actual naming conventions** (`SP_`, `STP_`, `BI_` prefixes,
in-house verbs) instead of imposing a theoretical one. If the naming is too fragmented
to be usable, the engine **automatically falls back** to dependency-graph cohesion
(shared tables, cross-calls) — and keeps that fallback only if it genuinely groups
better. The chosen strategy, the measured fragmentation and the learned profile are
recorded in `inventory.json` and announced in plain sight:

```
[REVERSE] DB Billing → 214 procedure(s) grouped into 31 module(s)/FEAT
          — cohesion clustering — naming unusable (fragmentation 0.82). (Phase 1 OK)
```

### Read-only is an architectural guarantee, not a promise

Your DBA can sleep. The engine emits **only** catalog `SELECT`s (`sys.sql_modules`,
`sys.procedures`, …) and `OBJECT_DEFINITION`, validated at runtime by a `readonly_guard`.
**Never** `DROP` / `DELETE` / `TRUNCATE` / `ALTER` / `INSERT` / `UPDATE` / `MERGE`,
**never** a procedure execution — the ban is carried by the blocking
`[DB_STRUCTURE_CHANGE_FORBIDDEN]` class and the `reverse-db-readonly` invariant. The
password stays in RAM: **never logged, never persisted** into the produced artefacts.
Defence-in-depth recommendation: a dedicated login with `GRANT VIEW DEFINITION` +
`db_datareader`.

### Nothing ships unqualified

- **Downward traceability**: every FEAT item traces to a User Story criterion, which
  traces to a line of SQL snapshot. `evidence:` pointers are **resolved on disk** — a
  dead pointer is a gap, not a green light.
- **Consumption gate**: a FEAT whose confidence is not `high` **does not enter**
  `/sdd-full` (exit 1). Dynamic or encrypted SQL forces human review — the override
  exists (`--allow-reverse-low`) but it is explicit and audit-logged.
- **Your edits are never overwritten**: each FEAT carries a fingerprint of its generated
  content. If you edited it, a re-run **preserves** it and tells you so.
- **Idempotent**: re-running reuses already-allocated identifiers — no orphans, no
  duplicates.

### Supported engines

| Engine | Status |
|---|---|
| **SQL Server**, **PostgreSQL** | 🟢 live-validated |
| **Oracle**, **MySQL / MariaDB** | 🟡 scaffold-validated — read-only queries and offline flow tested; live runtime still to be validated on a test database before production |
| DB2, SQLite | recognised, refused with an explicit message |

### Get started

```bash
# 1. Read-only driver (once)
pip install -e ".sdd/python[reverse-db]"     # + ODBC Driver 18 for SQL Server

# 2. Fill in stack.md ## Active Database (DB_HOST / DB_NAME / DB_USER / DB_PASSWORD,
#    clear values or ${VAR} placeholders resolved from a .env file)
```

```text
/sdd-db-reverse-full                          # the whole database
/sdd-db-reverse-full --schema dbo --limit 50  # bounded scope (recommended for a first run)
/sdd-db-reverse dbo.usp_Contact_Insert        # a single object, to evaluate without committing
```

**Try it on one module.** You will get a FEAT a Product Owner can read, sourced line by
line, over code nobody understood this morning.

Full details: [.sdd/docs/reverse-engineering-workflow.md](.sdd/docs/reverse-engineering-workflow.md) ·
[.sdd/docs/reverse-db-audit-2026-07.md](.sdd/docs/reverse-db-audit-2026-07.md) ·
[.sdd/rules/reverse-engineering.md](.sdd/rules/reverse-engineering.md)

---

## Web Console — validation cockpit

Since **v6.10**, a React + Fastify web console centralises all project telemetry (QA, security, coverage, runs, gates) by reading the SQLite `workspace/db/console.db`. No `.json` or `.jsonl` stat file remains on the FS — the DB is the single source of truth.

### Launch the console

```bash
cd workspace/console
npm install        # first time only (Fastify + Anthropic SDK)
npm start          # boots at http://127.0.0.1:4000
```

Prereqs: Node.js ≥ 20 and Python ≥ 3.8 on PATH (used to query `console.db` via the `sdd_lib` helpers).

### Three main pages

| Page | URL | Purpose |
|---|---|---|
| **Dashboard** *(default)* | `/` | KPI cards (FEATs, API Tests, Security, Quality), per-FEAT status grid, SonarQube-style quality audit (Vulnerabilities / Code Smells / Coverage with A→E ratings), 4 modern charts, sparklines, persisted dark/light theme. |
| **Features** *(ex-SDD Jira)* | `/` then Features tab | 3 views: **PO view** (FEAT → US), **Technical view** (FEAT → US → back/front plans), **UX view** (carousel of HTML mockups per FEAT). Header with **Refresh** button that re-scans the FS. |
| **Documentation** | topbar dropdown | **Functional** and **Technical** pages served inline (HTML body extracted, restyled with the site's native theme). |

### Highlights

- 🎨 **Light / dark theme** with topbar toggle, persisted in localStorage, follows `prefers-color-scheme` on first load.
- 📊 **Native SVG charts** (donut, bar stacks, sparklines, gradient progress bars) — indigo/cyan/amber/red/emerald/violet palette, theme-aware.
- 🛡 **SonarQube-style Quality Audit section**: 1 line per FEAT with A→E ratings.
- 🔍 **Expandable drill-down**: 1-click expands 3 tables (critical/serious vulns, code smells, coverage gaps).
- 🖼 **UX carousel view**: HTML mockups served via static `/ui/*` route.
- 🛡 **Manual gates**: `afterUS / afterReadiness / afterPlan / afterCode` phases set by `/sdd-full --manual-gates` are resolved from the console (POST `/api/gate-decide`).
- 🤖 **AI rephrasing** (LOT 4, opt-in): "Rephrase with AI" button on FEATs/US/Plans, uses the Anthropic SDK to produce a PO-friendly version.
- 📡 **Live updates**: SSE (`/api/events`) broadcasts FS changes and `status.json` modifications.

### Exposed HTTP API

| Endpoint | Description |
|---|---|
| `GET /api/tree` | FEATs → US → plans tree + `status.json` merged |
| `GET /api/dashboard` | Aggregate view of all FEATs (5 KPIs + 1 row per FEAT) |
| `GET /api/feat/:n` | FEAT detail (coverage, quality, security, api-tests) |
| `GET /api/feat/:n/details` | Sonar issues (vulns + smells + coverage gaps) |
| `GET /api/audit` | Per-agent token / context aggregate |
| `GET /api/state` | Last run + 30 most recent events |
| `GET /api/gates?feat=N` | Gates history for 1 FEAT |
| `POST /api/validate` | Records PO/Tech Lead decision on a US/Task |
| `POST /api/gate-decide` | Resolves an `afterUS/afterReadiness/...` gate |
| `GET /api/events` | Server-Sent Events (broadcasts FS + gates changes) |

---

## Architecture in one paragraph

SDD_Pro orchestrates **25 agents** — 13 forward-pipeline (PO, arch, dev-backend, dev-frontend, QA, 5 reviewers, elicitor, constitutioner, specbook-writer) plus 12 reverse-engineering agents (optional legacy→spec module) — around a **strict file ownership matrix**, a **layered Project Config** (43 keys, JSON-schema validated), a **deterministic Python tooling layer** (~20 KLOC, 1700+ tests, framework smoke), and a **hard cost/budget cap** ($50/run by default). The framework is **source-first**: every decision lives in `.md` files (FEATs, US, plans, ADRs) versioned with the code — no hidden state in the LLM context. The pipeline is **gated backend-first** (dev-backend ALL US → API Gate → dev-frontend ALL US) to avoid silent contract drift between front and back. Harness-agnostic: the `.sdd/` source layer is compiled to per-harness facades by `harness_build.py` — same pipeline logic whether you run Claude Code, Codex, or Gemini CLI.

---

## Key resources

- [.claude/CLAUDE.md](.claude/CLAUDE.md) — framework overview (FR, ~150 lines)
- [.sdd/docs/quickstart.md](.sdd/docs/quickstart.md) — full quickstart (FR)
- [.sdd/docs/getting-started.en.md](.sdd/docs/getting-started.en.md) — full getting started (EN, this English mirror)
- [.sdd/docs/architecture.md](.sdd/docs/architecture.md) — architecture (FR)
- [.sdd/docs/validated-combos.md](.sdd/docs/validated-combos.md) — validated stack combinations
- [.sdd/docs/VERSIONING.md](.sdd/docs/VERSIONING.md) — versioning policy
- [.sdd/docs/CHANGELOG.md](.sdd/docs/CHANGELOG.md) — release notes
- [.sdd/docs/MIGRATION.md](.sdd/docs/MIGRATION.md) — migration guides
