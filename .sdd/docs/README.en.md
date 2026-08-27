# 📚 SDD_Pro Documentation

> **Spec-driven development, multi-harness** (Claude Code, Codex, Gemini CLI,
> Antigravity) — a multi-agent framework that turns functional specifications into
> production-ready code through **29 specialised agents**, deterministic Python
> orchestration (**80 scripts, 0 tokens**) and **5 quality reviewers**.

This is the documentation hub. Every doc has a purpose and a target audience.
Pick your path below.

> 🇫🇷 **The French documentation is canonical.** English pages live next to their French
> counterparts with an `.en.md` suffix (e.g. `getting-started.en.md`). When an English
> page is missing, read the French one — the technical content (identifiers, `[CLASS]`
> codes, flags) is identical.

---

## 🚀 I want to start using SDD_Pro

| Step | Goal | Doc |
|---|---|---|
| **1** | Understand what SDD_Pro is in 5 min | [getting-started.en.md](getting-started.en.md) |
| **2** | Get a working project in 30 min | [cookbook.md](cookbook.md) |
| **3** | Learn the vocabulary | [glossary.md](glossary.md) |
| **4** | Configure a brownfield repo | [quickstart.md](quickstart.md) |
| **5** | Pick a stack combo | [validated-combos.md](validated-combos.md) |
| **6** | Work under Codex or Gemini CLI | [multi-llm-getting-started.md](multi-llm-getting-started.md) |

---

## 🗄️ I have legacy to recover (reverse engineering)

| Starting point | What it produces | Doc |
|---|---|---|
| **A database** (procedures, functions, views, triggers, jobs) | 1 SQL object = 1 User Story · 1 module = 1 FEAT | [reverse-engineering-workflow.md](reverse-engineering-workflow.md) *(Annex D)* |
| **A legacy codebase** (WebForms, PHP, Delphi, monoliths) | ladder 3a analysis → 3b US → 3c FEAT | [reverse-engineering-workflow.md](reverse-engineering-workflow.md) |
| Recipes per legacy technology | Concrete extraction examples | [reverse-engineering-cookbook/](reverse-engineering-cookbook/index.md) |
| DB module audit decisions | What was arbitrated, and why | [reverse-db-audit-2026-07.md](reverse-db-audit-2026-07.md) |
| Reverse anti-drift rules | `[REVERSE_*]` taxonomy, evidence, confidence | [../rules/reverse-engineering.md](../rules/reverse-engineering.md) |
| Shared SQL expertise base | `MERGE` / `NULL` / atomicity pitfalls, multi-dialect equivalences | [../rules/db-reverse-tsql.md](../rules/db-reverse-tsql.md) |

> ⚠️ **Phase 0 is mandatory** since 2026-08-26: `/sdd-db-context` builds the *Database
> Context* (deterministic facts + architect hypotheses, versioned) **before** any lift
> into User Stories. Without it, a composite object yields a spec that is wrong but
> credible.

---

## 📖 I want to understand the framework deeply

| Topic | Audience | Doc |
|---|---|---|
| Pipeline visualisation (mermaid) | Architect / Tech Lead | [workflow.md](workflow.md) |
| Component model (agents, rules, hooks) | Architect / Tech Lead | [architecture.md](architecture.md) |
| Gate map (who blocks what, when) | Tech Lead | [gates-map.md](gates-map.md) |
| Why these design choices | Everyone | [principles/source-first.md](principles/source-first.md) |
| User story granularity rules | PO / Tech Lead | [principles/us-granularity.md](principles/us-granularity.md) |
| Anti-drift + idempotence + plans | Tech Lead | [conventions.md](conventions.md) |
| Runtime hooks and protections | Tech Lead | [hooks-and-protections.md](hooks-and-protections.md) |

---

## 🔧 I need reference (cards)

| Reference | Purpose | Doc |
|---|---|---|
| **29 agents** (13 forward + 16 reverse) | Role / Model / Inputs / Outputs / Verdicts | [agents-reference.md](agents-reference.md) |
| **41 commands** (13 user-facing + 9 internal + 19 reverse) | Args / Flags / Agents / Outputs | [commands-reference.md](commands-reference.md) |
| **Project Config** | Layered config + defaults + ranges | [configuration-reference.md](configuration-reference.md) |
| **Error classes** | **191 `[CLASS]` prefixes** across 16 families | [../rules/error-classification.md](../rules/error-classification.md) |
| **Load-bearing invariants** | 14 forward + 17 reverse, each with its enforcer | [../INVARIANTS.yml](../INVARIANTS.yml) · [../INVARIANTS.reverse.yml](../INVARIANTS.reverse.yml) |
| **Protection hooks** | The 20 wired hooks (preflight, ownership, cost cap…) | [hooks-and-protections.md](hooks-and-protections.md) |
| **Per-stack prerequisites** | Runtimes, SDKs, drivers | [prerequisites-matrix.md](prerequisites-matrix.md) |

---

## 🛟 I hit an error / have a question

| Situation | Doc |
|---|---|
| Common errors + recovery | [troubleshooting.md](troubleshooting.md) |
| Known runtime pitfalls | [runtime-pitfalls.md](runtime-pitfalls.md) |
| Config precedence (base ← team ← project) | [config-precedence.md](config-precedence.md) |
| Cleaning up orphan files | [orphan-cleanup-policy.md](orphan-cleanup-policy.md) |
| Stack version drift | [validated-combos.md](validated-combos.md) |
| What SDD_Pro does **not** do | [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) |

---

## 💼 I have to decide (CTO / CIO)

| Doc | Purpose |
|---|---|
| [WHY-SDD-PRO.md](WHY-SDD-PRO.md) | Business case and market comparison |
| [SLA.md](SLA.md) | Service commitments (13 combos) |
| [COMPLIANCE.md](COMPLIANCE.md) | Compliance and data handling |
| [poc-roi-methodology.md](poc-roi-methodology.md) | How to validate a new stack |
| [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md) | Acknowledged limits |

---

## 🤝 I want to contribute

| Contribution | Doc |
|---|---|
| Working agreement | [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) |
| Versioning policy | [VERSIONING.md](VERSIONING.md) |
| Adding a new stack | [../stacks/README.md](../stacks/README.md) |
| Architecture decisions | [adrs/](adrs/) |

---

## 📜 History / changelogs

| Doc | Content |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Release notes |
| [MIGRATION.md](MIGRATION.md) | v6 → v7 upgrade guides |
| [adrs/](adrs/) | Architecture Decision Records |
| [roadmap-v7-v8.md](roadmap-v7-v8.md) | What comes next |

---

## 📊 ROI & benchmarks

| Doc | Purpose |
|---|---|
| [poc-roi-methodology.md](poc-roi-methodology.md) | How to validate a new stack |
| [benchmarks/](benchmarks/) | Run reports + known gaps |
| [cache-strategy.md](cache-strategy.md) | Prompt cache plan |

---

## 🏛 Subsystems

| Subsystem | Doc |
|---|---|
| **Arch phases** (A/B/C deep dive) | [arch/phase-a-config-propagation.md](arch/phase-a-config-propagation.md) · [arch/phase-b-db-scaffolding.md](arch/phase-b-db-scaffolding.md) · [arch/phase-c-claude-md-generation.md](arch/phase-c-claude-md-generation.md) |
| **Python codebase** | [../python/README.md](../python/README.md) |
| **Stack catalog** | [../stacks/README.md](../stacks/README.md) |
| **The 12 operational rules** | [../rules/](../rules/) |
| **Multi-harness facades** | [harness-codex.md](harness-codex.md) · [harness-gemini.md](harness-gemini.md) |

---

## ❓ Still lost?

- **New contributor?** Read `getting-started.en.md` + `cookbook.md` (1 hour total).
- **Onboarding a brownfield repo?** Run `/sdd-discover-stack`, then `quickstart.md`.
- **Legacy to recover?** Database → `/sdd-db-context` then `/sdd-db-reverse-full`.
  Source code → `/sdd-reverse-full`.
- **Debugging a failing pipeline?** Open `troubleshooting.md` and grep your error class `[XXX]`.
- **Adding a stack?** Read `poc-roi-methodology.md` first — the validation bar is real.

> 💡 **Tip**: the entry point `.claude/CLAUDE.md` (~150 lines) is a slim index — every
> section links into the docs you see here. If you only ever read 2 files, make them
> `CLAUDE.md` + this one.

---

## 🌐 Translation status

English pages live next to the French ones with an `.en.md` suffix:

| Page | FR | EN |
|---|:---:|:---:|
| README (this page) | ✅ canonical [README.md](README.md) | ✅ |
| Getting Started | ✅ canonical | ✅ [getting-started.en.md](getting-started.en.md) |
| Repository root README | ✅ [../../README.fr.md](../../README.fr.md) | ✅ [../../README.md](../../README.md) |
| All other pages | ✅ canonical | 🟡 read the French version |

> English contributions welcome: add `page.en.md` next to `page.md`, then update this
> table **and** the equivalent one in [README.md](README.md).
