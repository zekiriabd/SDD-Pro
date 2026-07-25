# Mode: Design — greenfield architecture

> Co-build a new architecture from an idea or a free-form description. Structured 5-phase dialogue with **explicit validation at every phase**.

## When to use

- The user starts from an idea or a free-form description, without existing code or documentation
- Typical phrasings: *"I want to design X"*, *"how should I architect Y"*, *"help me design Z"*, *"I'm starting a new project, how do I structure it?"*
- No artifact to retro-document or review

If the context is ambiguous between design and retro-documentation, ask: *"Greenfield design, or are you starting from something existing?"*

## Cardinal rule

**Never deliver without explicit validation at every phase.** The architecture emerges from dialogue, not from a one-shot.

Exception: the user explicitly asks for a v1 without dialogue (*"just generate a quick draft"*, *"give me a v1, we'll iterate"*). In that case produce with assumptions clearly marked, then propose the review.

## Phase 0 — Framing

Ask framing questions in **a single batch** (max 5). If the user has already answered implicitly, don't re-ask.

1. System name + business intent sentence?
2. Audience for the diagram (tech team, non-tech stakeholder, onboarding, audit…)? → drives the level of detail
3. Which levels are expected (Context only, Context + Container, down to Component)?
4. Output format and destination — see [`SKILL.md`](SKILL.md) section *Common contract > Output format* and *> Destination*. Confirm before producing.
5. Known hard constraints (compliance, perf, legacy to integrate, cloud budget…)?

**Exit**: the user has provided enough material to propose a Context diagram.

## Phase 1 — Context (level 1)

Dialogue:

- **Reformulate the scope**: *"If I understand correctly, system X does Y for Z. Is that right?"*
- **Actors**: *"Who uses this system? External customers, internal employees, automated systems?"*
- **External systems**: *"What do you interact with outside the perimeter (payment, auth, email, ERP, partners…)?"*
- **Main flows**: for each pair, *"Which direction does the data flow, and why?"*

Present a **first draft** (Mermaid + elements table). Ask: *"Does this Context diagram reflect the system? Is any actor or external system missing?"*

**Exit**: explicit agreement before moving to level 2.

## Phase 2 — Container (level 2)

Dialogue:

- **Internal containers**: *"Which processes are deployed independently (web app, API, worker, batch, DB, cache, broker…)?"*
- **Technologies**: for each container, *"Which stack (language/framework), which runtime (VM, container, serverless), which DB?"*
- **Communications**: *"How does A talk to B? Sync (HTTP/gRPC) or async (queue/event)? Which protocol?"*
- **Fuzzy boundaries**: *"Is any service doing too many things? Or two we could merge?"*

Present the Container draft. For each relationship, validate the **intent label** (not "Uses"). Ask: *"Does this breakdown feel right? Any containers missing, misnamed, or misplaced?"*

**Exit**: explicit agreement before delivering or moving to level 3.

## Phase 3 — Component (level 3, on demand)

Don't propose spontaneously. If asked: **one container at a time**, question its internal components (controllers, services, adapters, gateways…). Same cycle: draft → review → iteration → validation.

## Phase 4 — Finalization

1. Run the checklist ([`review-checklist.md`](review-checklist.md)) — call out points that raise questions
2. List **residual assumptions** explicitly — confirm them one by one
3. Deliver to the destination chosen in Phase 0 (tools to use below)
4. Ask: *"Do you consider the architecture finalized, or do you want one more iteration?"*

## Tools to use per phase

| Phase | Tool | Usage |
|---|---|---|
| 0-3 | — | Dialogue + inline diagram generation |
| 4 — local filesystem | `Write` | One document per level, using `level-template.md` |
| 4 — Notion | `mcp__notion__*` | One page per level |
| 4 — Linear | `mcp__linear__save_document` | One document per level |
| 4 — Google Drive | `mcp__*Drive*` | One file per level |
| 4 — inline | — | Rendered in the conversation only |

## Links

- ← Back: [`SKILL.md`](SKILL.md)
- Deliverable template: [`level-template.md`](level-template.md)
- Filled-out examples: [`examples/`](examples/)
- Detailed Mermaid syntax: [`mermaid-c4-syntax.md`](mermaid-c4-syntax.md)
- Review checklist: [`review-checklist.md`](review-checklist.md)
- If the user then wants to evolve the architecture: [`mode-update.md`](mode-update.md)
