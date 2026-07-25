# Mode: Document-code — retro-documentation from a repo

> Produce a C4 from an existing codebase. The skill scans, presents findings, then dialogues to fill in the ambiguities.

## When to use

- The user points to a repo path (local or GitHub), pastes code, or says *"document my codebase"*
- Concrete artifacts exist to analyze (source code, config files, manifests…)
- The goal is to reflect reality, not to imagine a possible future

## Step 1 — Quick framing

Max 3 questions if information is missing:

1. Scope of the repo: whole monorepo, or a subfolder?
2. Expected levels (Context + Container usually suffice — Component only if the user asks)?
3. Output format and destination — see [`SKILL.md`](SKILL.md) *Common contract*.

## Step 2 — Codebase scan

**Delegation rule**: for a repo > ~50 files or an unfamiliar stack, **delegate the scan to a sub-agent** via the `Agent` tool with `subagent_type: Explore`. Goal: keep the main context free for dialogue with the user.

Prompt to give the Explore agent:

> Inventory of the repository from a C4 Container angle. List:
> (1) deployable services/processes (Docker services, entrypoints, apps) with their technology;
> (2) datastores (DB, cache, queue) with their technology;
> (3) external dependencies (Stripe, Auth0, SendGrid, third-party APIs…);
> (4) communication flows between these elements (HTTP clients, DB clients, publish/subscribe) with the protocol when identifiable.
> Report as structured lists, no prose. Flag anything ambiguous or inferred explicitly.

For a smaller repo, do the scan directly with `Glob` / `Grep` / `Read`.

### Typical sources to read

| Type | Files to examine |
|---|---|
| Overview | `README*`, `ARCHITECTURE.md`, `docs/` |
| Orchestration | `docker-compose.yml`, `Procfile`, k8s/Helm manifests, `serverless.yml` |
| Build/languages | `package.json`, `pom.xml`, `pyproject.toml`, `requirements.txt`, `go.mod`, `Gemfile`, `Cargo.toml` |
| Runtime | `Dockerfile`(s), startup scripts (`start.sh`, `entrypoint.sh`) |
| Data | Migrations (`db/migrations/`, `alembic/`, Prisma schema…), SQL schemas |
| Messaging | Kafka/Rabbit/Pub-Sub config, topic/queue declarations |
| Secrets/config | `.env.example`, `config/` (secrets masked) |
| Integrations | Grep for HTTP clients, third-party SDKs (`stripe`, `twilio`, `sendgrid`, `auth0`…) |

### Identification rules

- Service deployed independently → a `Container`
- DB / cache → `ContainerDb`; brokers/queues → `ContainerQueue`
- External dependency (SaaS, third-party API) → `System_Ext`
- Major subpackages/modules of a container → candidate `Component` (level 3, on demand)

## Step 3 — Present the findings

Show the user what the scan found, as raw lists:
- **Candidate containers** (with technology)
- **External dependencies** identified
- **Flows identified** (with protocol when known)
- **Doubtful or implicit flows** (to confirm)
- **Ambiguities** (a service doing multiple things, uncertain technology…)

Ask: *"Does this breakdown match what you had in mind? Anything missing?"*

## Step 4 — Dialogue-driven enrichment

For each unknown or ambiguity, ask by batches of 3-5 (common dialogue rule). Answers feed the model. If the user doesn't know, it stays in **Assumptions**, not in the diagram.

## Step 5 — Draft, iterate, finalize

Produce Context + Container in the chosen format. Iterate on user feedback. Run the [`review-checklist.md`](review-checklist.md). Deliver to the chosen destination.

**Assumptions**: anything inferred from code without explicit confirmation (*"we deduce PostgreSQL from migrations in `db/migrations/`"*) goes into the *Assumptions* section of the document, never silently into the diagram.

## Tools to use per step

| Step | Tool | Usage |
|---|---|---|
| 1 | — | Dialogue |
| 2 (large repo) | `Agent` with `subagent_type: Explore` | Delegated scan |
| 2 (small repo) | `Glob`, `Grep`, `Read` | Direct scan |
| 3-4 | — | Dialogue |
| 5 delivery | `Write` / `mcp__notion__*` / `mcp__linear__save_document` / etc. | Per destination |

## Links

- ← Back: [`SKILL.md`](SKILL.md)
- Deliverable template: [`level-template.md`](level-template.md)
- Filled-out examples: [`examples/`](examples/)
- Detailed Mermaid syntax: [`mermaid-c4-syntax.md`](mermaid-c4-syntax.md)
- Review checklist: [`review-checklist.md`](review-checklist.md)
- If the user then wants to evolve the produced C4: [`mode-update.md`](mode-update.md)
