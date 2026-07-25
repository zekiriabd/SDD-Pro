# Software architecture diagram review checklist

Normative checklist from Simon Brown, [`c4model.com/diagrams/checklist`](https://c4model.com/diagrams/checklist). Walk through it systematically before delivering a C4 diagram.

> **Editorial principle** (addition specific to this skill, not sourced from c4model.com): a C4 diagram should ideally be understandable **without external narration**. If a checklist item stays unchecked, fix the diagram or complete the Markdown document that accompanies it.

## General (Simon Brown)

- [ ] Does the diagram have a **title**?
- [ ] Do you understand what the diagram **type** is?
- [ ] Do you understand what the diagram **scope** is?
- [ ] Does the diagram have a **key / legend**?

## Elements (Simon Brown)

- [ ] Does every element have a **name**?
- [ ] Do you understand the **type** of every element (level of abstraction: software system, container…)?
- [ ] Do you understand what every element **does**?
- [ ] Where applicable, do you understand the **technology choices** associated with every element?
- [ ] Do you understand the meaning of all **acronyms and abbreviations** used?
- [ ] Do you understand the meaning of all **colors** used?
- [ ] Do you understand the meaning of all **shapes** used?
- [ ] Do you understand the meaning of all **icons** used?
- [ ] Do you understand the meaning of all **border styles** used (solid, dashed…)?
- [ ] Do you understand the meaning of all **element sizes** used (small vs large boxes)?

## Relationships (Simon Brown)

- [ ] Does every line have a **label** describing the intent of the relationship?
- [ ] Does the description **match the direction** of the arrow?
- [ ] Where applicable, do you understand the **technology choices** associated with every relationship (e.g. protocols for inter-process communication)?
- [ ] Do you understand the meaning of all **acronyms and abbreviations** in labels?
- [ ] Do you understand the meaning of all **line colors**?
- [ ] Do you understand the meaning of all **arrow heads**?
- [ ] Do you understand the meaning of all **line styles** (solid, dashed…)?

## Additions specific to this skill (C4-specific)

These points are not in Simon Brown's official checklist but reinforce C4 quality:

- [ ] The diagram respects its **abstraction level** (no Component in a Container diagram, no Container in a Context)
- [ ] **External systems** are present at the Context level
- [ ] Every Container is a **process/runtime deployed independently** (not an internal module)
- [ ] Relationships are **unidirectional** (no `BiRel` — split into two distinct `Rel`s)
- [ ] **Assumptions** stemming from incomplete information are listed in the Markdown document (dedicated section)
- [ ] The **Markdown document** accompanying the diagram is self-standing
- [ ] Relationship labels state a concrete intent — **ban** bare *"Uses"*, *"Calls"*, *"Reads"*. **Prefer** *"Reads account balances from"*, *"Publishes OrderCreated events to"*, *"Sends password reset emails via"*
- [ ] Inter-container relationships state the **protocol/technology** (HTTPS/JSON, gRPC, AMQP, JDBC, SMTP…)

## If an item is unchecked

Two options:
1. **Fix the diagram** (add the title, the technology, the missing label…)
2. **Add the information to the accompanying Markdown document** (elements table, legend, assumptions…)

Never leave an item unchecked "by oversight". If it doesn't apply, state so explicitly (e.g. *"no colors used → item not applicable"*).

## Links

- Normative source: [`c4model.com/diagrams/checklist`](https://c4model.com/diagrams/checklist)
- ← Back to SKILL: [`SKILL.md`](SKILL.md)
