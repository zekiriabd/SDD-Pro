# 📚 SDD_Pro Documentation

> **Spec-Driven Development for Claude Code** — a multi-agent framework that turns functional specifications into production-ready code through 12 specialized AI agents, deterministic Python orchestration, and 5 quality reviewers.

This is the documentation hub. Every doc has a purpose and a target audience. Pick your path below.

> 🇫🇷 **Documentation FR is canonical**. EN versions are translations — some pages may fall back to FR until translated. Use the language switcher (top-right) to toggle.

---

## 🚀 I want to start using SDD_Pro

| Step | Goal | Doc |
|---|---|---|
| **1** | Understand what SDD_Pro is in 5 min | [getting-started.md](getting-started.md) |
| **2** | Get a working project in 30 min | [cookbook.md](cookbook.md) |
| **3** | Learn the vocabulary | [glossary.md](glossary.md) |
| **4** | Configure a brownfield repo | [quickstart.md](quickstart.md) |
| **5** | Pick a stack combo | [validated-combos.md](validated-combos.md) |

---

## 📖 I want to understand the framework deeply

| Topic | Audience | Doc |
|---|---|---|
| Pipeline visualization (mermaid) | Architect / Tech Lead | [workflow.md](workflow.md) |
| Component model (agents, rules, hooks) | Architect / Tech Lead | [architecture.md](architecture.md) |
| Why these design choices | All | [principles/source-first.md](principles/source-first.md) |
| User story granularity rules | PO / Tech Lead | [principles/us-granularity.md](principles/us-granularity.md) |
| Anti-derive + idempotence + plans | Tech Lead | [conventions.md](conventions.md) |

---

## 🔧 I need reference (cards)

| Reference | Purpose | Doc |
|---|---|---|
| **13 agents** | Role / Model / Inputs / Outputs / Verdicts | [agents-reference.md](agents-reference.md) |
| **21 commands** | Args / Flags / Agents / Outputs | [commands-reference.md](commands-reference.md) |
| **Project Config (58 keys)** | Layered config + defaults + ranges | [configuration-reference.md](configuration-reference.md) |
| **Error classes** | Taxonomy (174 prefixes `[CLASS]`) | [../rules/error-classification.md](../rules/error-classification.md) |
| **Hooks + protections** | 13 Claude Code hooks wired | [hooks-and-protections.md](hooks-and-protections.md) |

---

## 🛟 I have an error / question

| Situation | Doc |
|---|---|
| Common errors + recovery | [troubleshooting.md](troubleshooting.md) |
| Config precedence (base ← team ← project) | [config-precedence.md](config-precedence.md) |
| Cleanup orphan files | [orphan-cleanup-policy.md](orphan-cleanup-policy.md) |
| Stack version mismatch | [validated-combos.md](validated-combos.md) |

---

## 🤝 I want to contribute

| Contribution | Doc |
|---|---|
| Code / docs / fixes | [../../CONTRIBUTING.md](../../CONTRIBUTING.md) |
| Working agreement | [WORKING-AGREEMENT.md](WORKING-AGREEMENT.md) |
| Versioning policy | [VERSIONING.md](VERSIONING.md) |
| Add a new stack | [../stacks/README.md](../stacks/README.md) |

---

## 📜 I'm reading history / changelogs

| Doc | Content |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | Version-by-version release notes |
| [MIGRATION.md](MIGRATION.md) | v6 → v7 upgrade guides |
| [adrs/](adrs/) | Architecture Decision Records |
| [roadmap-v7-v8.md](roadmap-v7-v8.md) | What's coming next |

---

## 📊 ROI & benchmarks

| Doc | Purpose |
|---|---|
| [poc-roi-methodology.md](poc-roi-methodology.md) | How to validate a new stack |
| [benchmarks/](benchmarks/) | Run reports + known gaps |
| [cache-strategy.md](cache-strategy.md) | Prompt caching plan (v7.1 target) |

---

## 🏛 Subsystems

| Subsystem | Doc |
|---|---|
| **Arch phases** (A/B/C deep dive) | [arch/phase-a-config-propagation.md](arch/phase-a-config-propagation.md), [arch/phase-b-db-scaffolding.md](arch/phase-b-db-scaffolding.md), [arch/phase-c-claude-md-generation.md](arch/phase-c-claude-md-generation.md) |
| **Python codebase** | [../python/README.md](../python/README.md) |
| **Stacks catalog** | [../stacks/README.md](../stacks/README.md) |
| **Rules** (5 consolidated + 3 annexes) | [../rules/](../rules/) |

---

## ❓ Still lost?

- **New contributor?** Read `getting-started.md` + `cookbook.md` (1 hour total).
- **Onboarding a brownfield repo?** Run `/sdd-discover-stack`, then `quickstart.md`.
- **Debugging a failing pipeline?** Open `troubleshooting.md` and grep your error class `[XXX]`.
- **Adding a stack?** Read `poc-roi-methodology.md` first to understand the validation bar.
- **Reviewing an audit report?** Check `architecture.md §3` for who-writes-what.

> 💡 **Tip** : the entry point `.claude/CLAUDE.md` (150 lines) is a slim index — every section there links into the docs you see here. If you only ever read 2 files, make them `CLAUDE.md` + this one.

---

## 🌐 Translation status

| Page | FR | EN |
|---|:---:|:---:|
| README (this page) | ✅ canonical | ✅ |
| Getting Started | ✅ canonical | ✅ |
| Agents Reference | ✅ canonical | ✅ (technical content mostly English-friendly) |
| Commands Reference | ✅ canonical | ✅ (technical content mostly English-friendly) |
| Configuration Reference | ✅ canonical | 🟡 fallback to FR |
| Troubleshooting | ✅ canonical | 🟡 fallback to FR |
| Architecture | ✅ canonical | 🟡 fallback to FR |
| Other pages | ✅ canonical | 🟡 fallback to FR |

> When an EN page is missing, the language switcher gracefully falls back to the FR version (via `fallback_to_default: true` in `mkdocs.yml`). Contributing new EN translations is welcome — add a `page.en.md` next to `page.md`.
