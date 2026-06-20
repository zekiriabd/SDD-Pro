# SDD_Pro

FEAT-driven development framework for Claude Code — `next` branch: **v7.0.0 GA tagged 2026-06-07** (see [.claude/docs/VERSIONING.md](.claude/docs/VERSIONING.md)). `main` branch: v6.10.4-LTS (freeze active until 2026-06-18).

> ⚠ **This English page is a summary, not a translation.** It covers Quickstart + Console essentials only (~10 sections vs ~17 in the French canonical README). For exhaustive docs (architecture, agents, rules, stacks, governance, ROI, roadmap), use the French source.
>
> 🇫🇷 [Version française (canonical, complete)](README.md) — Main documentation: [.claude/CLAUDE.md](.claude/CLAUDE.md) (French).

---

## 🚀 Quickstart — new project

**Recommended: use this repo as a [GitHub Template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository).** Click **"Use this template"** → "Create a new repository" → clone locally → run the interactive bootstrap:

```bash
# macOS / Linux
python3 bootstrap.py

# Windows (PowerShell)
.\bootstrap.ps1

# Non-interactive (CI / scripted) — uses validated combo C1
python bootstrap.py --combo c1 --skip-install
```

The bootstrap:
- Asks the project name + 3-4 questions (stack, DB, auth)
- Generates `workspace/input/stack/stack.md` (43 Project Config keys, safe defaults)
- Creates the full `workspace/output/.sys/` directory structure
- Installs Python deps (`pip install -e .claude/python[dev]`)
- Offers to install the console deps (`npm install` in `workspace/console/`)
- Runs a final smoke check

Validated end-to-end combos:
- **C1**: .NET Minimal API + React + shadcn + Azure AD + xUnit (recommended)
- **C2**: Kotlin Spring Boot + React + shadcn + Azure AD + JUnit
- `--combo custom`: manual composition (4 backends × 4 frontends × 3 UI systems)

---

## After bootstrap

1. Edit secrets in [workspace/input/stack/stack.md](workspace/input/stack/stack.md) (DB password, Azure AD client ID, etc.) — this file is gitignored.
2. In Claude Code: `/feat-generate <Name>` — answer the 3-6 elicitation questions.
3. *(Optional)* drop HTML mockups under `workspace/input/ui/{n}-{m}-{Name}.html`.
4. `/sdd-full {n}` — full pipeline (PO → arch → dev-back → API gate → dev-front → QA → reviewers).
5. `/sdd-status [{n}]` — diagnostic.

---

## Web Console — validation cockpit

Since **v6.10**, a React + Fastify web console centralises all project telemetry (QA, security, coverage, runs, gates) by reading the SQLite `workspace/output/db/console.db`. No `.json` or `.jsonl` stat file remains on the FS — the DB is the single source of truth.

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

SDD_Pro orchestrates **12 Claude Code agents** (PO, arch, dev-backend, dev-frontend, QA, 5 reviewers, elicitor, constitutioner) around a **strict file ownership matrix**, a **layered Project Config** (43 keys, JSON-schema validated), a **deterministic Python tooling layer** (~20 KLOC, 1072 tests, framework smoke), and an **opt-in cost/budget cap** ($50/run by default, hard-blocking past threshold). The framework is **source-first**: every decision lives in `.md` files (FEATs, US, plans, ADRs) versioned with the code — no hidden state in the LLM context. The pipeline is **gated backend-first** (dev-backend ALL US → API Gate → dev-frontend ALL US) to avoid silent contract drift between front and back.

---

## Key resources

- [.claude/CLAUDE.md](.claude/CLAUDE.md) — framework overview (FR, ~150 lines)
- [.claude/docs/quickstart.md](.claude/docs/quickstart.md) — full quickstart (FR)
- [.claude/docs/getting-started.en.md](.claude/docs/getting-started.en.md) — full getting started (EN, this English mirror)
- [.claude/docs/architecture.md](.claude/docs/architecture.md) — architecture (FR)
- [.claude/docs/validated-combos.md](.claude/docs/validated-combos.md) — validated stack combinations
- [.claude/docs/VERSIONING.md](.claude/docs/VERSIONING.md) — versioning policy
- [.claude/docs/CHANGELOG.md](.claude/docs/CHANGELOG.md) — release notes
- [.claude/docs/MIGRATION.md](.claude/docs/MIGRATION.md) — migration guides
