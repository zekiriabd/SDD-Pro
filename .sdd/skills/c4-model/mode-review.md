# Mode: Review — review or explanation of an existing diagram

> Analyze a C4 diagram provided by the user: checklist-driven critique, or narrative explanation.

## When to use

- The user pastes a diagram (Mermaid, PlantUML, Structurizr DSL, described image, link)
- They want either a **critique** (*"is this good?"*, *"what's wrong?"*, *"review"*), or an **explanation** (*"explain this diagram"*, *"what does this do?"*)

If the user then wants to apply corrections → switch to [`mode-update.md`](mode-update.md).

## Sub-mode: critique

### Step 1 — Load the diagram

- If the diagram is pasted in chat: read directly
- If it's a file path: `Read`
- If it's a verbally described image: use the description

### Step 2 — Run the checklist

Walk through [`review-checklist.md`](review-checklist.md) point by point. For each item, note `✓ ok` / `✗ missing` / `⚠ ambiguous` / `n/a`.

### Step 3 — Group by severity

Present remarks in three groups:

| Level | Definition | Examples |
|---|---|---|
| **Blocking** | C4 rule violated | Missing technology on a Container, "Uses" labels everywhere, mixed levels (Component inside a Container diagram), ambiguous `BiRel` |
| **Important** | Readability / clarity | No legend, no title, relationships without protocol, overly dense diagram |
| **Nice-to-have** | Style / consistency | Sub-optimal visual order, overflowing labels, naming consistency |

### Step 4 — Concrete corrections

For each blocking or important point, **propose the exact correction**:
- Not *"this label is vague"* → *"replace 'Uses' with 'Publishes OrderCreated events via' on the relationship OrderService → EventBus"*
- Not *"technology is missing"* → *"add `"Java, Spring Boot 3"` as the third parameter of Container `api`"*

### Step 5 — Propose application

Ask: *"Do you want me to apply these corrections?"*
- **Yes** → switch to [`mode-update.md`](mode-update.md)
- **No** → deliver the review alone (inline or in a document if requested)

## Sub-mode: explanation

### Step 1 — Identification

From the diagram provided, identify:
- The **level** (Context, Container, Component, Deployment, Dynamic)
- The **scope** (which system, which part)
- The **key elements** and their types

### Step 2 — Structured narration

Narrate the diagram in prose, in this order:

1. **What the diagram tells** — in one sentence
2. **The scope** — system, implicit audience
3. **The main actors/containers** — one by one, with their role
4. **The major flows** — in the order where value flows
5. **Points of attention** — ambiguities, non-obvious decisions visible in the diagram

### Step 3 — Flag gray zones

If the diagram is incomplete or ambiguous, say so: *"The relationship between X and Y has no protocol specified — I can't tell whether it's synchronous HTTP or async."*

### Step 4 — Propose an accompanying document

If the user wants, offer to generate the missing Markdown document (switch to [`mode-update.md`](mode-update.md) to write the doc).

## Tools to use

| Step | Tool | Usage |
|---|---|---|
| Load from file | `Read` | Read the diagram |
| Critique | — | Dialogue + checklist |
| Applying corrections | → switch to `mode-update.md` | |
| Optional review delivery | `Write` / `mcp__*` | If the user wants to persist the review |

## Links

- ← Back: [`SKILL.md`](SKILL.md)
- Review checklist: [`review-checklist.md`](review-checklist.md)
- Mermaid syntax (to validate reviewed diagrams' syntax): [`mermaid-c4-syntax.md`](mermaid-c4-syntax.md)
- If corrections need to be applied: [`mode-update.md`](mode-update.md)
