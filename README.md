# SDD_Pro — Agentic Software Engineering, Industrialized

**The framework that refuses to ship code nobody validated.**

Spec-driven development (FEAT → User Stories → Code), **multi-harness**
(Claude Code, OpenAI Codex, Gemini CLI, Antigravity) — **v7.0.3-dev** (base v7.0.0 GA 2026-06-07).
LTS baseline v6.10.x kept until 2026-12-31.
See [VERSIONING](.sdd/docs/VERSIONING.md) · [CHANGELOG](.sdd/docs/CHANGELOG.md).

> 🇫🇷 [Version française](README.fr.md) — the French page is the canonical reference.
> Main documentation: [.claude/CLAUDE.md](.claude/CLAUDE.md) (French).

---

## The 30-second pitch

Coding assistants start from the code and try to work back to the intent.
SDD_Pro forces the opposite trajectory and **locks it behind deterministic gates**:

```
FEAT (versioned business spec)
  └─ User Stories (stable IDs, traceable acceptance criteria)
       └─ Technical plans (files, layers, preserves/adds contracts)
            └─ Code (backend first → API Gate → frontend)
                 └─ QA + 5 reviewers (code, security, spec, architecture, adversarial)
```

What that changes in practice:

| Without SDD_Pro | With SDD_Pro |
|---|---|
| The spec lives in the prompt and is never re-read | The spec is a file versioned alongside the code |
| The LLM "improvises" outside scope | `[DERIVE_VIOLATION]` → blocking **STOP** |
| The frontend calls an endpoint that doesn't exist | Blocking in-memory **API Gate** between back and front |
| Test coverage is a claim | `CoverageMin`, measured, 🔴 blocking |
| The LLM bill is discovered afterwards | `MaxCostPerRun` (default $50) → hard stop |
| A legacy database stays a black box | **Read-only** DB reverse → readable FEATs |

**The niche**: SDD_Pro **industrialises quality** — the equivalent of *Sonar + Snyk +
ADR governance* applied to a multi-agent pipeline, **on any LLM harness**.

---

## 🚀 Quickstart — new project

**Recommended: use this repo as a [GitHub Template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository).**
Click **"Use this template"** → "Create a new repository" → clone locally → run the
interactive bootstrap:

```bash
# macOS / Linux
python3 bootstrap.py

# Windows (PowerShell or cmd)
python bootstrap.py

# Non-interactive (CI / scripted) — validated combo C1
python bootstrap.py --combo c1 --skip-install
```

The bootstrap:
- asks for the project name + 3-4 questions (stack, database, auth);
- generates `workspace/stack/stack.md` (55 Project Config keys, safe defaults);
- creates the full `workspace/.sys/` directory structure;
- installs the Python dependencies (`pip install -e .sdd/python[dev]`);
- runs a final smoke check.

Available combos:

| Combo | Composition | Status |
|---|---|:---:|
| **C1** | .NET Minimal API + React + shadcn + Azure AD + xUnit | 🟢 validated end-to-end *(recommended)* |
| **C2** | Kotlin Spring Boot + React + shadcn + Azure AD + JUnit | 🟢 validated end-to-end |
| **C3** | Node Express + React + shadcn + local auth | 🟢 bench-validated runtime |
| **C4** | Python FastAPI + React + shadcn + local auth | 🟢 bench-validated runtime |
| **C5** | .NET Minimal API + Vue + Vuetify + Azure AD | 🟢 bench-validated runtime |
| `--combo custom` | manual composition (4 backends × 4 frontends × 3 design systems) | — |

**13 combos** carry an SLA commitment — machine source:
[.sdd/templates/combos.json](.sdd/templates/combos.json), detail in
[validated-combos.md](.sdd/docs/validated-combos.md).

CI mode (no prompts):
```bash
SDD_APP_NAME=MyApp SDD_COMBO=c1 python bootstrap.py --auto-init
```

---

## 🆚 Why SDD_Pro over BMAD / GSD / AgentOS / Superpowers?

| Criterion | SDD_Pro | BMAD | GSD | AgentOS | Superpowers |
|---|:---:|:---:|:---:|:---:|:---:|
| Multi-harness (Claude + Codex + Gemini + Antigravity) | ✅ **native** | ❌ | ❌ | ❌ | ❌ |
| Specialised agents | **29** | ~6 | ~5 | 4 | 8 |
| **Database** reverse engineering (procedures, functions, views, triggers, jobs) | ✅ **native** | ❌ | ❌ | ❌ | ❌ |
| **Legacy code** reverse engineering (legacy → FEAT) | ✅ **native** | ❌ | ❌ | ❌ | ❌ |
| Post-code reviewers (5 angles, adversarial on by default) | **5** ✅ | 1 | 1 | 1 | 2 |
| Strict anti-drift (ownership matrix + blocking STOP) | ✅ | partial | ❌ | partial | partial |
| Machine-readable dependency catalogs (`.libs.json` + CVE + LTS) | ✅ **30** | ❌ | ❌ | ❌ | ❌ |
| Cross-agent error taxonomy (`[CLASS]`) | ✅ **191** | ❌ | ❌ | ❌ | ❌ |
| Load-bearing invariants declared **and tested** | ✅ **31** | ❌ | ❌ | ❌ | ❌ |
| SQLite telemetry + IDE statusline (cost, phase, tokens) | ✅ | ❌ | partial | partial | ❌ |
| Idempotence / resume (checkpoint mode) | ✅ | ❌ | ❌ | partial | ❌ |
| Deterministic zero-token scripts | **80 scripts** | ❌ | ❌ | partial | partial |
| Plugin marketplace (native IDE discovery) | ✅ `plugin.json` | ❌ | ❌ | ❌ | ❌ |

See the [10-minute cookbook](.sdd/docs/cookbook.md) to start, or the
[CTO / CIO case](.sdd/docs/WHY-SDD-PRO.md) to decide.

---

## After bootstrap

1. Fill in the secrets in [workspace/stack/stack.md](workspace/stack/stack.md)
   (database password, Azure AD client ID, ports…) — **this file is gitignored**.
2. In the harness: `/feat-generate <Name>` — answer the 3-6 elicitation questions.
3. *(Optional)* drop HTML mockups under `workspace/ui/{n}-{m}-{Name}.html`.
4. `/sdd-full {n}` — full A→Z pipeline.
5. `/sdd-status [{n}]` — raw state · `/sdd-help [{n}]` — "what's next" guidance.

Already have a repository? `/sdd-discover-stack` detects the stack and produces a
`stack.md.candidate`.

---

## 🗄️ Database reverse engineering — your schema becomes a specification again

> **Your company's business logic is asleep inside your database.**
> Hundreds of stored procedures written over fifteen years, by developers who have long
> since left. No documentation. Nobody dares touch it.
> **SDD_Pro reads it — strictly read-only — and hands you specifications.**

One command, `/sdd-db-reverse-full`, connects using the connection details declared in
`stack.md ## Active Database`, inventories **everything the database knows how to do**,
and produces standard SDD_Pro FEATs — immediately consumable by `/sdd-full` to regenerate
an application on top. Your SQL estate stops being a black box and becomes a readable,
traceable, version-controlled backlog.

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
   └─ READ-ONLY introspection (0 tokens)  ─► SQL bodies + db-schema.json + inventory.json
        └─ Phase 0 — Database Context (/sdd-db-context)
             ├─ 0.A deterministic (0 tokens) : FACTS — CRUD matrix, call graph, waves
             └─ 0.B reverse-db-architect    : HYPOTHESES — glossary, sub-domains, risks
                  └─ Analysis waves: 4 specialised analysts (LLM, bounded parallelism)
                       └─ FEAT composition (deterministic, or LLM on complex modules)
                            └─ REVERSE-GATE ─► /sdd-full
```

### Phase 0 — the database is understood **before** it is carved up

This is the structural addition (2026-08-26). Reading a procedure body in isolation
produces a User Story that is **wrong but credible** as soon as composition is involved:
nested procedures, dynamic SQL, cascading triggers. So `/sdd-db-context` builds a global
understanding **once**, versioned, shared by every analyst:

- **The facts ≠ hypotheses contract.** *Facts* (tables, keys, `CHECK` constraints, CRUD
  matrix, call graph) come from deterministic scripts and **may** become acceptance
  criteria. *Hypotheses* (business glossary, sub-domains, risk areas) come from the
  `reverse-db-architect` agent and **never** may. The separation is **structural**: the
  architect writes a separate file that a script merges into the `hypotheses` branch
  only. It cannot overwrite a fact, even if it tries.
- **A cache that expires honestly.** `contextVersion` is a sha256 of the canonical facts.
  Database unchanged → the interpretation is reused and Phase 0.B is not paid for again.
  Database changed → the stale interpretation is **discarded**, and the report says so:
  an obsolete reading of a database that has moved is worse than no reading at all.
- **Context packs that are computed, not guessed.** No agent reads the whole context.
  Each object gets a bounded pack (default 14,000 bytes) with its contract, **only** the
  tables it touches, what it calls (depth ≤ 2) and its callers. If the budget forces an
  eviction, **the pack says so** — an agent handed a truncated view lowers its confidence
  knowingly.

### Waves: every callee is analysed before its caller

The call graph is resolved, its strongly connected components condensed (Tarjan — self-
calls and mutual recursion are real in T-SQL), then topologically sorted. **Guaranteed
property**: a called object is analysed in a wave strictly earlier than its caller. A
callee name that is missing or ambiguous stays an `unresolvedCallee` — never resolved by
guesswork, because one false edge reorders the entire plan.

Throughput does not suffer: bounded parallelism (`MaxParallel`) applies **inside** a wave;
there is a single barrier between two waves, where the orchestrator — never an agent —
capitalises the summaries produced and regenerates the next packs.

### Four specialists, not one giant prompt

The reverse module ships **16 dedicated agents**, **6 of them SQL experts**. What
justifies a separate agent is **the angle** — never the SQL type in itself:

| Agent | The question it asks the object |
|---|---|
| **`reverse-sql-analyst`** *(procedures)* | which operation, which data effects, which preconditions? |
| **`reverse-sql-function-analyst`** *(functions)* | which reusable business calculation, which edge cases, which default? |
| **`reverse-sql-view-analyst`** *(views)* | which information is exposed, and which **hidden filters** (`WHERE Active = 1`)? |
| **`reverse-sql-trigger-analyst`** *(triggers)* | which event, which rule, which cascade, which transaction rejection? |
| **`reverse-db-architect`** *(Phase 0.B)* | what is this database's business vocabulary, its sub-domains, its risk areas? |
| **`reverse-sql-feat-composer`** *(module synthesis)* | which cross-cutting business FEAT, with the plumbing demoted? |

Shared expertise base: [.sdd/rules/db-reverse-tsql.md](.sdd/rules/db-reverse-tsql.md) —
`MERGE` / `OUTPUT` / `inserted` / `NULL` pitfalls, atomicity, errors turned into negative
acceptance criteria, T-SQL / PL-pgSQL / PL-SQL / MySQL equivalences.

No agent spawns another — the command orchestrates, so **the bill stays predictable**.

### 70–80% of your database costs zero tokens

Before any LLM is called, a **deterministic router** grades every object by what its body
*hides* — dynamic SQL, cursors, recursion, unresolved callees, orchestration, fan-in,
volume — and returns a **tier** (`none` / `fast` / `balanced` / `deep`), never a model
name: resolving that belongs to the active provider.

- **genuinely simple object** (CRUD, no branching, no dynamic SQL, no error handling,
  **and no calls**) → its User Story is generated **mechanically, at zero cost**;
- **object with real business logic** → only then is an agent woken up.

On top: a **per-object cache** (an unchanged body is never re-analysed, so a second run
after an interruption is near-free) and scope guards (`--schema`, `--include`,
`--exclude`, `--limit`) that **always name what they left out** — never a silent
truncation.

> 🔎 **The false green we closed.** Until August 2026 the router weighed branching,
> dynamic SQL, error handling, cursors and volume — **never calls**. A 38-line
> orchestrator with no branching, delegating all of its business rules to six procedures,
> was therefore classified "simple": templated User Story, `high` confidence for lack of
> anything to degrade it, and **passage through the REVERSE-GATE with no human review**.
> Delegating is not being simple. Now any call forces LLM analysis, and an unresolved
> callee or a recursion caps confidence at `medium` — which propagates up to the FEAT and
> triggers review.

### Module clustering is measured, not guessed

It is the most structural decision of the whole reverse: it sets the number of FEATs.
SDD_Pro **profiles your actual naming conventions** (`SP_`, `STP_`, `BI_` prefixes,
in-house verbs) instead of imposing a theoretical one. If the naming is too fragmented to
be usable, the engine **automatically falls back** to dependency-graph cohesion (shared
tables, cross-calls) — and keeps that fallback only if it genuinely groups better. The
chosen strategy, the measured fragmentation and the learned profile are recorded in
`inventory.json` and announced in plain sight:

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

> ⚠️ **Honest caveat**: Phase 0 and wave ordering are validated **offline** (synthetic
> catalogs, topological sort checked against a brute-force reference over 300 random
> graphs). The thresholds — pack depth 2, 14,000-byte budget, 0.50 fragmentation — are
> calibrated on synthetic corpora and will be revisited after the first run against a
> real production database.

### Get started

```bash
# 1. Read-only driver (once)
pip install -e ".sdd/python[reverse-db]"     # + ODBC Driver 18 for SQL Server

# 2. Fill in stack.md ## Active Database (DB_HOST / DB_NAME / DB_USER / DB_PASSWORD,
#    clear values or ${VAR} placeholders resolved from a .env file)
```

```text
/sdd-db-context                               # Phase 0 — understand the database (required)
/sdd-db-context --no-architect                # facts only, 0 tokens
/sdd-db-reverse-full                          # the whole database
/sdd-db-reverse-full --schema dbo --limit 50  # bounded scope (recommended for a first run)
/sdd-db-reverse dbo.usp_Contact_Insert        # a single object, to evaluate without committing
```

**Try it on one module.** You will get a FEAT a Product Owner can read, sourced line by
line, over code nobody understood this morning.

Full details: [reverse-engineering-workflow.md](.sdd/docs/reverse-engineering-workflow.md) ·
[reverse-db-audit-2026-07.md](.sdd/docs/reverse-db-audit-2026-07.md) ·
[rules/reverse-engineering.md](.sdd/rules/reverse-engineering.md)

---

## 🧬 Legacy code reverse engineering — the application too

The same module lifts a legacy **codebase** (WebForms, PHP, Delphi, monoliths…) into
FEATs, through a three-rung "ladder" that refuses to skip altitude:

```
/sdd-reverse-full            # full orchestrator (init → inventory → audit → ladder → UI)
  ├─ 3a  faithful technical analysis  (reverse-tech-analyst)   — photo of the code, file:line evidence
  ├─ 3b  lift into User Stories       (reverse-us-writer)      — business altitude, still traceable
  └─ 3c  FEAT composition            (reverse-feat-composer)  — plumbing demoted
```

Three phases complete the picture: **paradigm gap** (your legacy is event-driven, your
target is a unidirectional SPA — the decision is made consciously), **Gherkin parity
specs** (behavioural equivalence legacy ↔ regenerated becomes executable), and a
**question loop** for the Tech Lead (no answer is ever invented). Details:
[reverse-engineering-workflow.md](.sdd/docs/reverse-engineering-workflow.md).

---

## 📊 Web Console — validation cockpit

A React + Fastify web console centralises all project telemetry (QA, security, coverage,
runs, gates) by reading the SQLite database `workspace/db/console.db`. No `.json` or
`.jsonl` stat file remains on disk — **the database is the single source of truth**.

> ℹ️ `workspace/` is **gitignored** (it holds your secrets and generated code): the
> console ships with the internal distribution, not with a clone of the GitHub template.
> If `workspace/console/package.json` is present, the bootstrap offers to run
> `npm install`.

```bash
cd workspace/console
npm install        # first time only (Fastify + Anthropic SDK)
npm start          # boots at http://127.0.0.1:4000
```

Prerequisites: Node.js ≥ 20 and Python ≥ 3.8 on PATH (used to query `console.db` via the
`sdd_lib` helpers).

### Two main pages

| Page | Purpose |
|---|---|
| **Dashboard** *(default)* | KPI cards (FEATs, API tests, Security, Quality), per-FEAT status grid, SonarQube-style quality audit (Vulnerabilities / Code Smells / Coverage with A→E ratings), 4 native SVG charts, sparklines, persisted dark/light theme. |
| **Features** | 3 views: **PO** (FEAT → US), **technical** (FEAT → US → back/front plans), **UX** (carousel of HTML mockups). **Refresh** button re-scans the filesystem. |

> ℹ️ **Framework docs were removed from the console (2026-06-06)** — the console stays
> dedicated to materialised-project statistics. SDD_Pro's own documentation lives in
> [.sdd/docs/](.sdd/docs/).

### Highlights

- 🎨 **Light / dark theme** with a topbar toggle, persisted in localStorage, following
  `prefers-color-scheme` on first load.
- 📊 **Native SVG charts** (donut, bar stacks, sparklines, gradient progress bars),
  theme-aware — no charting dependency.
- 🛡 **SonarQube-style quality audit**: one row per FEAT with A→E ratings. Cards render
  **only** when the data exists in the database (no placeholders).
- 🔍 **Expandable drill-down**: one click expands 3 tables (critical/serious
  vulnerabilities, code smells, coverage gaps) with file:line, OWASP/CWE, colour-coded
  severities.
- 🛡 **Manual gates**: the `afterUS / afterReadiness / afterPlan / afterCode` phases set
  by `/sdd-full --manual-gates` are resolved from the console, with atomic writes
  protected by a cross-language Python ↔ Node lock.
- 🤖 **AI rephrasing** (opt-in): a "Rephrase with AI" button on FEATs/US/Plans.
- 📡 **Live updates**: SSE (`/api/events`) broadcasts filesystem and status changes — the
  tree updates without a reload.

### Exposed HTTP API

| Endpoint | Description |
|---|---|
| `GET /api/tree` | FEATs → US → plans tree + merged state |
| `GET /api/dashboard` | Aggregate view of all FEATs (5 KPIs + 1 row per FEAT) |
| `GET /api/feat/:n` | FEAT detail (coverage, quality, security, api-tests) |
| `GET /api/feat/:n/details` | Sonar issues (vulns + smells + coverage gaps) |
| `GET /api/audit` | Per-agent token / context aggregate |
| `GET /api/state` | Last run + 30 most recent events |
| `GET /api/gates?feat=N` | Gate history for one FEAT |
| `GET /api/file?path=…` | Raw read of a workspace Markdown file |
| `POST /api/validate` | Records the PO / Tech Lead decision on a US |
| `POST /api/gate-decide` | Resolves an `afterUS / afterReadiness / …` gate |
| `GET /api/events` | Server-Sent Events (filesystem + gate changes) |
| `GET /ui/*` | Serves `workspace/ui/` (HTML mockups with their relative CSS) |

---

## 🔍 What is verifiable (and how to verify it)

SDD_Pro sells on numbers you can recount. Every one of these is derived from the
repository, not from a pitch:

| Item | Count | Recount it |
|---|---:|---|
| Agents (13 forward + 16 reverse) | **29** | `ls .sdd/agents/ \| wc -l` |
| Commands (13 user-facing + 9 internal + 19 reverse) | **41** | `ls .sdd/commands/ \| wc -l` |
| Operational rules | **12** | `ls .sdd/rules/` |
| Auto-triggered skills | **13** | `ls .sdd/skills/` |
| Stacks (28 🟢 + 8 🟡) | **36** | `python .sdd/python/sdd_admin/framework_smoke.py` |
| `.libs.json` dependency catalogs | **30** | `find .sdd/stacks -name "*.libs.json" \| wc -l` |
| Combos under SLA commitment | **13** | [.sdd/templates/combos.json](.sdd/templates/combos.json) |
| `[CLASS]` error classes (16 families) | **191** | [error-classification.md](.sdd/rules/error-classification.md) |
| Project Config keys | **55** | [.sdd/config.base.yml](.sdd/config.base.yml) |
| Load-bearing invariants (14 forward + 17 reverse) | **31** | `INVARIANTS.yml` + `INVARIANTS.reverse.yml` |
| Deterministic scripts (0 tokens) | **80** | `sdd_scripts/` + `sdd_reverse_scripts/` |
| Wired protection hooks | **20** | `ls .sdd/python/sdd_hooks/` |
| Python tests | **2,542** *(175 files)* | `python -m pytest .sdd/python/tests/ -q` |
| Supported LLM providers | **4** | `ls .sdd/providers/` |

```bash
# Full framework check (consistency gates included)
python .sdd/python/sdd_admin/framework_smoke.py

# Test suite
python -m pytest .sdd/python/tests/ -q
```

> The [INVARIANTS.yml](.sdd/INVARIANTS.yml) manifest is the framework's anti-rot device:
> every load-bearing contract (two-stage gate, file ownership, cost cap, TDD test-first…)
> points at its *enforcer* on disk, and a test fails if that enforcer disappears without
> the manifest being updated.

---

## 🏗 Architecture in one paragraph

SDD_Pro orchestrates **29 agents** — 13 on the forward pipeline (PO, arch, dev-backend,
dev-frontend, QA, 5 reviewers, elicitor, constitutioner, specbook-writer) and 16 on the
reverse module (legacy code and databases) — around a **strict file ownership matrix**, a
**layered Project Config** (55 keys, JSON-schema validated), a **deterministic Python
tooling layer** (~58 KLOC, 2,542 tests) and a **hard cost cap** ($50/run by default). The
framework is **source-first**: every decision lives in a `.md` file (FEATs, US, plans,
ADRs) versioned with the code — no hidden state in the LLM context. The pipeline is
**backend-first and gated** (dev-backend ALL US → API Gate → dev-frontend ALL US) to
eliminate silent contract drift between front and back. It is **harness-agnostic**: the
`.sdd/` source layer is compiled into per-harness facades — the same pipeline logic
whether you run Claude Code, Codex, Gemini CLI or Antigravity.

---

## 🗺️ Visual blueprints

Three schematics, one per pipeline — every agent, every gate, every parallel fork drawn
as it actually runs.

### A — Forward pipeline
![Forward pipeline blueprint — FEAT to shipped code](https://i.imgur.com/UkbM1fw.jpeg)

FEAT → User Stories → backend (parallel across User Stories, gated by an in-memory
API Gate) → frontend (parallel) → QA → the two-stage reviewer batch (spec-compliance
alone first, then code / security / architecture in parallel) → an adversarial pass →
a single green / yellow / red verdict.

### B — Reverse engineering: legacy code
![Reverse-engineering blueprint — legacy code to FEAT](https://i.imgur.com/3pzuVfD.jpeg)

Inventory → tech audit and paradigm-gap analysis → the three-rung ladder (faithful
technical read-out → User Stories → FEAT composition, confidence never rising as it
climbs) → mandatory crosscutting FEATs → completeness review → UI mockups → a human
validation loop for anything left unresolved.

### C — Reverse engineering: database
![Reverse-engineering blueprint — database to FEAT](https://i.imgur.com/tgk0721.jpeg)

Database Context (deterministic facts, then an architect's hypotheses on top) →
wave-based dispatch — every stored object analysed only once everything it calls has
already been analysed — through four specialised SQL analysts → FEAT composition →
a dual REVERSE-GATE before anything reaches `/sdd-full`.

---

## 📚 Documentation

### For users

| Doc | Purpose |
|---|---|
| [.claude/CLAUDE.md](.claude/CLAUDE.md) | Slim entry point (~150 lines, index into the detail) — FR |
| [.sdd/docs/getting-started.en.md](.sdd/docs/getting-started.en.md) | First-steps tutorial (30 min) — EN |
| [.sdd/docs/cookbook.md](.sdd/docs/cookbook.md) | Concrete recipes (10 min) |
| [.sdd/docs/quickstart.md](.sdd/docs/quickstart.md) | Step-by-step start + brownfield |
| [.sdd/docs/glossary.md](.sdd/docs/glossary.md) | Framework vocabulary |
| [.sdd/docs/commands-reference.md](.sdd/docs/commands-reference.md) | Command cards (args / flags / outputs) |
| [.sdd/docs/agents-reference.md](.sdd/docs/agents-reference.md) | Agent cards (role / model / I-O / verdicts) |
| [.sdd/docs/configuration-reference.md](.sdd/docs/configuration-reference.md) | Project Config keys |
| [.sdd/docs/troubleshooting.md](.sdd/docs/troubleshooting.md) | Common errors + recovery |

### To decide (CTO / CIO)

| Doc | Purpose |
|---|---|
| [.sdd/docs/WHY-SDD-PRO.md](.sdd/docs/WHY-SDD-PRO.md) | Business case and market comparison |
| [.sdd/docs/SLA.md](.sdd/docs/SLA.md) | Service commitments |
| [.sdd/docs/COMPLIANCE.md](.sdd/docs/COMPLIANCE.md) | Compliance and data handling |
| [.sdd/docs/KNOWN-LIMITATIONS.md](.sdd/docs/KNOWN-LIMITATIONS.md) | What SDD_Pro does **not** do |
| [.sdd/docs/validated-combos.md](.sdd/docs/validated-combos.md) | Validated combination matrix |
| [.sdd/docs/poc-roi-methodology.md](.sdd/docs/poc-roi-methodology.md) | How to validate a new stack |

### To contribute to the framework

| Doc | Purpose |
|---|---|
| [.sdd/docs/architecture.md](.sdd/docs/architecture.md) | Components, agents, stacks |
| [.sdd/docs/workflow.md](.sdd/docs/workflow.md) | Pipeline phases |
| [.sdd/docs/conventions.md](.sdd/docs/conventions.md) | Anti-drift, idempotence, plans |
| [.sdd/loader.yml](.sdd/loader.yml) | Per-agent reads/writes manifest (forward) |
| [.sdd/loader.reverse.yml](.sdd/loader.reverse.yml) | Reverse module manifest |
| [.sdd/rules/](.sdd/rules/) | The 12 operational rules |
| [.sdd/docs/WORKING-AGREEMENT.md](.sdd/docs/WORKING-AGREEMENT.md) | Working agreement |
| [.sdd/docs/adrs/](.sdd/docs/adrs/) | Architecture Decision Records |

Navigation hub: [.sdd/docs/README.en.md](.sdd/docs/README.en.md).

> 🇫🇷 The French documentation is canonical and more exhaustive. Where an English page
> is missing, read the French one — the technical content (identifiers, classes, flags)
> is identical.

---

## 🧱 Technical stack

The framework is written in **Python** (pure stdlib for the engine, pytest for the
tests). **Web console**: Node.js ≥ 20 (Fastify 5 + React 18). **SQLite** (WAL mode) for
centralised telemetry (`workspace/db/console.db`).

No application runtime is imposed on the generated code — SDD_Pro produces code in the
target project's stack.

**Stack catalog** — strict terminology, source of truth = the `Validation:` header of the
`.md` file:

| Status | Definition | Count |
|:---:|---|:---:|
| 🟢 | `validated` (combo validated end-to-end), `bench-validated` (measured runtime) or `scaffold-validated` | **28** |
| 🟡 | `experimental` or `POC-only` — loadable, but **never sold as a standalone offer** | **8** |

**Total: 36 stacks** — Backend (4), Frontend (4), Design systems (3), QA (9), Auth (2),
Architecture patterns (3), Fullstack (7), Mobile (3). Detail:
[validated-combos.md](.sdd/docs/validated-combos.md).

> ⚠️ Outside the combos listed in [combos.json](.sdd/templates/combos.json), a
> multi-stack composition has not been validated by a full PoC: the pipeline may fail at
> runtime in non-trivial ways. The `preflight_stack_combo` hook flags it — the bypass
> (`SDD_ALLOW_UNTESTED_COMBO=1`) exists, but it is audit-logged.

---

## 📄 License & author

Designed and maintained by the **SDD-Pro maintainer** · 2026 — see [LICENSE](LICENSE).
