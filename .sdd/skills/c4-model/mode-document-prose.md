# Mode: Document-prose — retro-documentation from prose

> Produce a C4 from a textual description (README, ADR, spec, meeting transcript, Slack thread, email).

## When to use

- The user provides free-form text describing a system: README, ADR, functional spec, interview transcript, Slack/email thread summarizing an architecture
- No code to scan — the source of truth is the prose
- The goal is to structure what the text describes, not to invent beyond it

If the prose points to a repo, switch to **Document-code** ([`mode-document-code.md`](mode-document-code.md)) after extracting what's in the prose.

## Step 1 — Extraction

Read the prose (pasted in chat, or via `Read` if a path is provided). Extract:

| Category | Signals in prose |
|---|---|
| System and scope | *"the X portal"*, *"the Y platform"* |
| Actors mentioned | *"customers"*, *"support agents"*, *"admins"* |
| External systems | *"via Stripe"*, *"push into Salesforce"*, *"notifications via Twilio"* |
| Candidate containers | *"the frontend"*, *"the API"*, *"the worker"*, *"the database"* |
| Technologies | *"in Node"*, *"Postgres"*, *"RabbitMQ queue"* |
| Explicit flows | *"the frontend calls the API"*, *"the worker consumes events from the queue"* |

Anything ambiguous or absent goes into a "**gaps to fill**" list.

## Step 2 — Validation + gap-filling

Present the findings to the user in **two columns**:
- **What we understood** (reformulated from the prose)
- **What's missing** (explicit gaps)

For each gap, ask by batches of 3-5 (common dialogue rule). **Invent nothing.** If the user doesn't know, it stays in the *Assumptions* section of the document.

## Step 3 — Draft, iterate, finalize

Same cycle as the other modes:
1. Initial draft (Context + Container most often)
2. Dialogue-driven review, iteration
3. Run the [`review-checklist.md`](review-checklist.md)
4. Deliver to the chosen destination

## Tools to use per step

| Step | Tool | Usage |
|---|---|---|
| 1 | `Read` (if a path is provided), direct reading otherwise | Extraction |
| 2-3 | — | Dialogue |
| 3 delivery | `Write` / `mcp__notion__*` / `mcp__linear__save_document` / etc. | Per destination |

## Links

- ← Back: [`SKILL.md`](SKILL.md)
- Deliverable template: [`level-template.md`](level-template.md)
- Filled-out examples: [`examples/`](examples/)
- Detailed Mermaid syntax: [`mermaid-c4-syntax.md`](mermaid-c4-syntax.md)
- Review checklist: [`review-checklist.md`](review-checklist.md)
- If the prose points to a repo: [`mode-document-code.md`](mode-document-code.md)
