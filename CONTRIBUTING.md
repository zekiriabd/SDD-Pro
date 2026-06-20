# 🤝 Contributing to SDD_Pro

Thanks for your interest! SDD_Pro is a framework that orchestrates AI agents to turn functional specifications into production-ready code. Contributions can range from fixing typos to adding new stacks, agents, or hooks.

This guide covers : **how to set up**, **what to work on**, **how to test**, and **how to submit**.

---

## 📋 Before you start

### Read first

| Doc | Why |
|---|---|
| [.claude/CLAUDE.md](.claude/CLAUDE.md) | 150-line entry point — orient yourself |
| [.claude/docs/getting-started.md](.claude/docs/getting-started.md) | Tutorial — try the framework end-to-end |
| [.claude/docs/architecture.md](.claude/docs/architecture.md) | Component model + mermaid diagrams |
| [.claude/docs/WORKING-AGREEMENT.md](.claude/docs/WORKING-AGREEMENT.md) | Norms (PR size, naming, tests) |
| [.claude/docs/VERSIONING.md](.claude/docs/VERSIONING.md) | SemVer + ADR policy for governance changes |

### Pick the right type of contribution

| I want to | Do this |
|---|---|
| Fix a typo / improve doc | PR directly to `next` branch |
| Fix a bug in a Python script | Add a test, then fix |
| Add a new stack (`backend/`, `frontend/`, `ui/`...) | Follow [poc-roi-methodology.md](.claude/docs/poc-roi-methodology.md) — the bar is real |
| Modify an agent prompt | Discuss in an issue first — agent prompts are load-bearing |
| Change the hooks chain / settings.json | Requires ADR `governance-protection-*` (cf. [WORKING-AGREEMENT.md](.claude/docs/WORKING-AGREEMENT.md)) |
| Modify a rule (`build-and-loop`, `quality`, `ownership`...) | Requires ADR `governance-*` |
| Add a new error class `[CLASS]` | Edit `.claude/rules/error-classification.md` + ensure emitter exists |

---

## 🛠 Setup

### Prerequisites

- **Python ≥ 3.10**
- **Node.js ≥ 20** (for console only)
- **Git** ≥ 2.30
- **Claude Code** installed (`https://claude.com/claude-code`)
- An **Anthropic API key** for testing end-to-end (`export ANTHROPIC_API_KEY=sk-ant-...`)

### Clone + install

```bash
git clone <your-fork-url> sdd-pro-dev
cd sdd-pro-dev
git remote add upstream <upstream-url>

# Install Python dev deps
pip install -e .claude/python[dev]

# Optional : install console deps
cd workspace/console && npm install && cd ../..

# Verify
python .claude/python/sdd_admin/framework_smoke.py
# Expected: OK=88+ / WARN=0-2 / FAIL=0
```

### Branch model

- `main` = `v6.10.4-LTS` (freeze until 2026-06-18, only critical patches)
- `next` = `v7.0.0-alpha` (active development)
- Your work : branch from `next` with prefix :
  - `feat/<scope>-<short-desc>` (new feature)
  - `fix/<scope>-<short-desc>` (bug fix)
  - `docs/<scope>` (docs only)
  - `chore/<scope>` (refactor, cleanup)

Example : `feat/stack-go-fiber`, `fix/cost-cap-windows-race`.

---

## 🧪 Testing

### Run the full suite

```bash
# Pytest (recommended, comprehensive)
python -m pytest .claude/python/tests/ -q

# Subset compatible with stdlib only
python -m unittest discover -s .claude/python/tests -p "test_*.py"

# Framework smoke (deterministic checks)
python .claude/python/sdd_admin/framework_smoke.py
```

**All tests must pass** before submitting a PR. **No exceptions** — even for docs PRs (smoke validates cross-references).

### Add a test when fixing a bug

```python
# .claude/python/tests/test_your_fix.py
import unittest
from sdd_lib.your_module import your_function

class TestYourFix(unittest.TestCase):
    def test_pathological_case_now_handled(self):
        """Regression test for issue #N — your_function silently returned
        wrong value when input was empty."""
        result = your_function("")
        self.assertEqual(result, expected_value)
```

Match the existing test style. Use `unittest` (stdlib) when possible to keep the dev-deps-free subset alive.

### Test agent prompts end-to-end

Modifying an agent `.md` ? Run a real FEAT through it :

```bash
# In Claude Code (a sandbox repo)
/feat-generate TestAuth
/sdd-full 1 --plan
# Inspect workspace/output/qa/feat-1/review.md
```

If it works on combo C1 (.NET + React) AND C2 (Kotlin + React), your change is safe.

---

## 📁 Project structure

```
.claude/
├── CLAUDE.md                  ← entry-point (slim, 150L max)
├── agents/                    ← 12 agent prompts (LLM)
├── commands/                  ← 20 slash command prompts
├── rules/                     ← 5 consolidated rules + 3 annexes
├── stacks/                    ← 34 stack catalogs (.md + .libs.json)
├── docs/                      ← documentation (you're contributing here often)
├── python/
│   ├── sdd_lib/               ← shared library (atomic_write, file_locks, ...)
│   ├── sdd_scripts/           ← runtime scripts (preflight, validate, orchestrate)
│   ├── sdd_hooks/             ← Claude Code hooks (PreToolUse, PostToolUse, etc.)
│   ├── sdd_admin/             ← maintenance scripts (sync, framework_smoke, ...)
│   └── tests/                 ← pytest suite (~1100 tests)
├── templates/                 ← Markdown / YAML templates
├── settings.json              ← Claude Code config (hooks + permissions)
├── loader.yml                 ← agent reads/writes manifest (SSoT)
└── config.base.yml            ← framework defaults (Project Config keys)

workspace/                     ← runtime artifacts (mostly gitignored)
├── input/                     ← user inputs (FEATs, stack.md, mockups)
└── output/                    ← generated artifacts (US, code, reports, DB)
```

---

## ✅ Submission checklist

Before opening a PR :

- [ ] Branch from `next` (not `main`)
- [ ] Title : conventional commit format (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`)
- [ ] All tests pass : `python -m pytest .claude/python/tests/ -q`
- [ ] Framework smoke passes : `python .claude/python/sdd_admin/framework_smoke.py`
- [ ] If you touched a rule / hook / agent → ADR added under `.claude/docs/adrs/`
- [ ] CHANGELOG.md updated (under `[Unreleased — v7.0.0-alpha]`)
- [ ] No secret committed (`stack.md` is gitignored — verify with `git status`)
- [ ] No `print()` left in production scripts (use `sys.stderr.write` or `logging`)
- [ ] No `eval`, `exec`, `shell=True`, `os.system` (security policy)

PR template :
```markdown
## Why
(1-2 sentences — what problem this solves)

## What
(bulleted list of changes)

## How tested
(commands you ran + expected output)

## Risks / breaking
(none / listed here / requires migration)
```

---

## 🚫 Common pitfalls to avoid

### ❌ Don't bypass hooks via `--no-verify`

If `block_env_bypass` or any hook fails on your commit, **read its message** and fix the underlying issue. Never use `git commit --no-verify`.

### ❌ Don't lower security defaults in config.base.yml

`SecurityFailOn`, hard-blocking SEC classes, and cost caps are intentional. Modify only via ADR `governance-security-*` with 2 maintainer approvals.

### ❌ Don't add `os.environ[...]` reads in agent prompts

Pattern B (canonized 2026-06-06) : `stack.md` is the secrets SSoT. `arch` propagates to native configs (`appsettings.json` etc.). Agents read native configs, never env vars directly. Class `[SEC_ENV_VAR_FORBIDDEN]` enforces this.

### ❌ Don't create files under `workspace/output/` outside agents' ownership

Read [`.claude/rules/ownership.md §1`](.claude/rules/ownership.md). Each agent has a strict write path. The `audit_file_ownership` hook will catch you.

### ❌ Don't mock the database in QA tests

Use `InMemoryDatabase` (EF Core), `:memory:` SQLite, or `@DataJpaTest` H2 — but **always the real ORM**. Mocks hide migration bugs (post-mortem 2025-Q4).

### ❌ Don't add a new stack without running the PoC ROI

The validation bar is **2 combos × 1 FEAT M end-to-end**. Read [`poc-roi-methodology.md`](.claude/docs/poc-roi-methodology.md) first. We've already had to mark `fullstack/node-react` as 🟡 POC-only after promising prematurely.

---

## 🎯 Good first issues

If you're new, look for these labels :
- `good-first-issue` — gentle entry
- `docs` — improve documentation
- `cleanup` — refactor / dead code removal
- `test` — add missing tests

Examples of what makes a good first contribution :
- Fix a typo in `.claude/docs/troubleshooting.md`
- Add a new error class to `.claude/rules/error-classification.md` with a regression test
- Improve a mermaid diagram in `architecture.md`
- Add a recipe to `cookbook.md` (your favorite stack combo, gotchas)
- Add a one-pager for an existing stack (e.g. `stacks/backend/python-fastapi.md`)

---

## 🏛 Governance — ADRs

For changes that affect the public API or load-bearing behavior, create an ADR under `.claude/docs/adrs/` :

```bash
# Generate the filename via the helper (collision-safe)
python -c "
import sys; sys.path.insert(0, '.claude/python')
from sdd_lib.adr_id import mint_adr_filename
print(mint_adr_filename('your-decision-slug'))
"
# Example output: ADR-20260606T143022-a1f2-your-decision-slug.md
```

Then write the ADR using the template `.claude/templates/adr.template.md` (Context / Decision / Consequences / Alternatives considered).

The `arch-reviewer` agent + `index_adrs.py` will pick it up automatically.

---

## 📞 Communication

- **Bug reports** → GitHub issues with `bug` label + reproduction
- **Feature ideas** → GitHub issues with `enhancement` label + use case
- **Security** → email maintainer privately (don't open issue) ; see [SECURITY.md](SECURITY.md) if present
- **Questions** → GitHub Discussions
- **Stack additions** → discuss in issue first (validation bar = real)

---

## 🙏 Code of conduct

Be kind. Be technical. Critique code, never people. Disagreement is fine ; rudeness is not.

We've found that the SDD_Pro philosophy ("rules promise, code delivers") works better when contributors hold each other to the same standard. PR reviews are detailed but constructive.

---

## 📜 License

By contributing, you agree your work is licensed under the same terms as the framework (TBD by maintainer — typically MIT or similar permissive).

---

## 🔗 Quick links

- [README.md](README.md) — top-level overview
- [.claude/docs/README.md](.claude/docs/README.md) — docs hub
- [.claude/docs/getting-started.md](.claude/docs/getting-started.md) — tutorial
- [.claude/docs/architecture.md](.claude/docs/architecture.md) — component model
- [.claude/docs/troubleshooting.md](.claude/docs/troubleshooting.md) — common errors

---

Designed and maintained by **Zekiri Abdelali** · 2026
