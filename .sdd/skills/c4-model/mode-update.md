# Mode: Update — updating an existing C4

> Evolve an existing C4: adding a container, new flow, refactoring, applying corrections from a review.

## When to use

- The user already has a C4 (filesystem, Notion, wiki…) and wants to modify it
- Typical phrasings: *"add container X"*, *"replace Y with Z"*, *"apply the review corrections"*
- Often follows a [`mode-review.md`](mode-review.md)

## Step 1 — Read the existing C4

- Local file → `Read`
- MCP document → equivalent MCP tool (`mcp__notion__*`, `mcp__linear__*`…)
- Pasted in chat → read directly

Note the **format** (Mermaid? Structurizr? PlantUML?) and the **destination** — they must stay consistent unless the user asks for a change.

## Step 2 — Clarify the diff

Ask targeted questions to clarify **what changes**:

- Addition: *"Which type of element do we add (Container, System_Ext, Component)? Its technology? Its relationships with the existing system?"*
- Removal: *"What disappears? The relationships pointing to it as well?"*
- Modification: *"What changes (label, technology, protocol, intent)?"*
- Refactoring: *"Is this a split of a container in two, a merge, a boundary change?"*

The **why** is as important as the what — it goes into the *"Architectural decisions"* section of the document.

## Step 3 — Identify affected levels

| Change type | Typically affected levels |
|---|---|
| New container | Container (always), Component if zoomed |
| New external system | Context + Container |
| New inter-container relationship | Container |
| Technology change | Container (and Component if zoomed) |
| Boundary refactoring | Container + potentially Context |
| Label correction | The level where the label appears |

Update **all** affected levels, not only the lowest one.

## Step 4 — Update decisions and assumptions

If the change alters trade-offs (e.g. *"we switch from REST to gRPC to reduce latency"*), update the **"Architectural decisions"** section of the document with the new rationale.

If new assumptions arise (*"we assume target load stays < 1000 RPS"*), add them to the **"Assumptions"** section.

## Step 5 — Validate and deliver

- **Trivial change** (rename, label correction) → direct `Edit`, no need to re-validate
- **Structural change** (new container, restructure) → present the diff, get validation before writing
- Run the [`review-checklist.md`](review-checklist.md) on the modified levels
- Deliver to the original destination (same tools as at creation time)

## Tools to use per step

| Step | Tool | Usage |
|---|---|---|
| 1 read | `Read` or MCP tool | Load the existing C4 |
| 2-4 | — | Dialogue |
| 5 trivial | `Edit` | Targeted patch |
| 5 structural | `Write` or MCP | Rewrite the affected document |

## Links

- ← Back: [`SKILL.md`](SKILL.md)
- Review checklist: [`review-checklist.md`](review-checklist.md)
- Mermaid syntax: [`mermaid-c4-syntax.md`](mermaid-c4-syntax.md)
- Often follows: [`mode-review.md`](mode-review.md)
