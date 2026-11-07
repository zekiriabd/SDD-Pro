# [Level N] — [Diagram type] — [System or container name]

> **Diagram type**: [System Context | Container | Component | Code]
> **Scope**: [what exactly this diagram shows, in one sentence]
> **Audience**: [who this diagram primarily addresses]

## Overview

[1-3 paragraphs. Set the context: which system / which part of the system we're looking at, why this diagram exists, what story it tells. A reader arriving cold should understand why they're looking at this diagram.]

## Diagram

```mermaid
[Mermaid code of the diagram — title on the first line]
```

## Legend

- **Person / actor**: human user of the system
- **System (in scope)**: the system the diagram is about
- **External system**: out-of-scope system our system interacts with
- **Container** *(level 2+)*: independently deployable application or data store
- **Component** *(level 3)*: logical grouping of classes/functions inside a container
- *[Add here any color/shape/border convention specific to this diagram]*

## Elements

| Element | Type | Technology | Responsibility |
|---|---|---|---|
| *Name* | *Person / System / Container / Component / DB / Queue / Ext* | *e.g. Java 21 + Spring Boot / PostgreSQL 15 / —* | *What the element is responsible for, in one sentence* |
| … | … | … | … |

## Key relationships

| From | To | Intent | Protocol / Technology |
|---|---|---|---|
| *A* | *B* | *e.g. "Publishes OrderCreated events to"* | *e.g. AMQP* |
| … | … | … | … |

## Notable architectural decisions

[Use this section to spell out non-obvious choices that show up on this diagram. Free form, e.g. bullet points. Examples:]

- *Why Kafka was chosen over RabbitMQ for this flow (volume, retention, replay…)*
- *Why the SPA calls the API directly rather than through the Web backend (deployment separation, no SSR required…)*
- *Why this boundary between the two containers (business coupling, release cycle, scalability…)*

## Assumptions

[Use this section when the diagram was generated from partial information. List here, visibly, everything that was guessed, so the reader can confirm or correct.]

- *Assumption 1: component X communicates with Y over HTTPS (not explicitly seen in the code, inferred from the presence of an HTTP client)*
- *Assumption 2: the database is PostgreSQL (deduced from the migration scripts found in `db/migrations/`)*

## Links to other levels

- *↑ [Higher level](./NN-xxx.md) — more abstract view*
- *↓ [Lower level](./NN-xxx.md) — zoom on [container/component]*
- *See also: [other relevant diagram](./NN-xxx.md)*
