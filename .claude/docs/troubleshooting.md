# 🛟 Troubleshooting + FAQ

Common errors, their root cause, and the **exact fix**. SDD_Pro uses a strict error taxonomy : every problem is prefixed with `[CLASS]` so you can `Ctrl+F` your error and find the resolution here.

---

## 🚨 Most common errors (by class)

### `[FEAT_NOT_FOUND]` / `[FEAT_AMBIGUOUS]`

**Symptom** : `/sdd-full 1` or `/us-generate 1` rejects the FEAT.

**Cause** : either no file matches `workspace/input/feats/{n}-*.md`, or multiple files do.

**Fix** :
```bash
# 1. Check what exists
ls workspace/input/feats/
# 2. Either create the missing FEAT
/feat-generate Auth   # creates 1-Auth.md
# 3. Or remove the duplicate(s)
mv workspace/input/feats/1-AuthOld.md workspace/input/feats/_archive/
```

---

### `[STACK_MALFORMED]`

**Symptom** : `/arch-init` or `/sdd-full` STOPs early citing `[STACK_MALFORMED]`.

**Cause** : `workspace/input/stack/stack.md` is missing required sections OR contains placeholders like `{{AppName}}` that weren't rendered.

**Fix** :
```bash
# Re-run bootstrap
python bootstrap.py             # interactive
# OR check the rendered stack.md
grep "{{" workspace/input/stack/stack.md   # should return nothing
```

Required sections : `## Active Tech Specs`, `## Active Database` (if `DatabaseType ≠ none`), `## Active Auth Specs` (if auth needed), `## Project Config`.

---

### `[BUILD_BLOCKING]` / `[BUILD_LOOP_EXHAUSTED]`

**Symptom** : `dev-backend` or `dev-frontend` STOPs after 3 build iterations.

**Cause** :
- `[BUILD_BLOCKING]` = architectural error (DI cycle, layer violation, design break) — not auto-fixable
- `[BUILD_LOOP_EXHAUSTED]` = 3 attempts failed → the agent gives up

**Fix** :
```bash
# 1. Inspect the build log
cat workspace/output/qa/feat-1/build-us-1-2.md
# 2. Fix manually OR refine the US
# 3. Re-run the targeted agent
/dev-backend 1-2     # rebuild this US only
```

**Bypass** : if you accept the partial build, you cannot bypass — you must either fix the code or rewrite the US.

---

### `[BUILD_LOOP_COST_EXCEEDED]`

**Symptom** : `dev-*` STOPs citing $15+ spent on a single US.

**Cause** : a pathological US is consuming Opus tokens beyond the per-US cap.

**Fix** :
```bash
# Option A : raise the cap (decision tracked in git blame)
# Edit workspace/input/stack/stack.md ## Project Config
#   BuildLoopMaxCostUsd: 25.00
# Option B : split the US into smaller pieces
# Option C : one-shot bypass (audit-logged in shell history)
export SDD_DISABLE_COST_CAP=1
/dev-run 1
```

---

### `[COST_CAP_EXCEEDED]`

**Symptom** : `/sdd-full` STOPs citing run-level cost cap ($50 default).

**Cause** : cumulative spend on this run reached `MaxCostPerRun`.

**Fix** :
```bash
# Option A : raise the cap
# Edit workspace/input/stack/stack.md ## Project Config
#   MaxCostPerRun: 100.00
# Option B : let the current run finish, then start fresh
/sdd-status 1                  # check what's done
# Option C : one-shot bypass
export SDD_DISABLE_COST_CAP=1
/sdd-full 1 --resume
```

---

### `[QA_COVERAGE_GAP]`

**Symptom** : `/qa-generate 1` or `/sdd-full 1` ends with 🔴 RED on coverage.

**Cause** : `coverage_lines_pct < CoverageMin` (default 80%) — **or** one of the per-stack coverages is below threshold (v7.0.0+ strict mode).

**Fix** :
```bash
# 1. Inspect which stack is failing
cat workspace/output/qa/feat-1/coverage.json | grep -A 5 stack
# 2. Either add tests in the failing stack's .Tests/ project
# 3. OR lower the threshold (tracked decision)
# Edit workspace/input/stack/stack.md ## Project Config
#   CoverageMin: 70
# 4. OR disable entirely
#   CoverageMin: 0
```

---

### `[QA_TEST_FAILED]`

**Symptom** : `/qa-generate` reports 🔴 RED with N tests failed.

**Cause** : a generated test caught a bug — OR the test itself is broken.

**Fix** :
```bash
# Inspect failing tests
cat workspace/output/qa/feat-1/report.md
# Re-run the tests in your IDE to see the assertion details
# Decide : (a) fix the production code OR (b) fix the test
# Then re-run
/qa-generate 1
```

---

### `[QA_FRAMEWORK_MISSING]`

**Symptom** : `qa` agent can't find the test runner (`dotnet test`, `npm test`, `pytest`...).

**Cause** : the CLI tool isn't installed OR not on PATH.

**Fix** :
```bash
# Verify the runner exists
which dotnet              # or npm, pytest, gradle, etc.
# Install if needed (depends on stack)
# Linux/macOS  : brew install dotnet, apt install dotnet-sdk-8
# Windows      : winget install Microsoft.DotNet.SDK.8
```

---

### `[FILE_OWNERSHIP]` / `[FILE_OWNERSHIP_NESTED]`

**Symptom** : SubagentStop hook reports an agent wrote outside its allowed paths.

**Cause** :
- `[FILE_OWNERSHIP]` = agent wrote where it doesn't own (e.g. `dev-backend` writes in `{AppName}/`)
- `[FILE_OWNERSHIP_NESTED]` = front project created INSIDE backend project (anti-pattern v3.0.1)

**Fix** : This is a framework bug if it happens — open an issue. The audit log gives you the exact path :
```bash
cat workspace/output/.sys/.audit/ownership-violations.log
```

---

### `[LIBNAME_LOCK_HELD]`

**Symptom** : `dev-backend` or `dev-frontend` STOPs because the LibName lock is held.

**Cause** : Another agent (parallel `/dev-run`) is currently writing the same `{LibName}/{Entity}.cs`.

**Fix** :
```bash
# Wait for the other agent to finish, then re-run
/dev-run 1
# OR if the lock is stale (>30 min, agent crashed)
# Stale recovery is automatic — just re-run
```

If multiple `/dev-run` parallel invocations are running, **serialize them** : SDD_Pro is not designed for concurrent same-FEAT runs.

---

### `[STACK_LIBRARY_MISSING]`

**Symptom** : `dev-*` rejects with "needs library X, not in §2.4 of stack".

**Cause** : The agent needs a lib (e.g. EPPlus for Excel) that isn't listed in the active stack's `.libs.json`.

**Fix** :
```bash
# 1. Edit the stack catalog
# Edit .claude/stacks/backend/{active}.libs.json
# Add the lib in `onDemand[]` with capability + triggers regex
# 2. Regenerate the .md §2.4
python .claude/python/sdd_admin/sync_stack_md.py --stack-id dotnet-minimalapi
# 3. Re-run
/dev-backend 1-2
```

---

### `[PLAN_STALE]`

**Symptom** : `/dev-run --plan` rejects with hash mismatch on the plan.

**Cause** : The US was modified AFTER the plan was generated → plan no longer matches.

**Fix** :
```bash
# Re-generate the plan
/dev-plan 1
# Then re-run
/dev-run 1
```

---

### `[FEAT_HASH_MISMATCH]`

**Symptom** : downstream agents reject US files with `Parent FEAT hash: sha256:COMPUTE_REQUIRED`.

**Cause** : `po` agent was invoked OUTSIDE `/us-generate` (e.g. via `Agent: po` debug). The sentinel was never resolved.

**Fix** : Already automated since v7.0.0-alpha. The hook `resolve_po_hash_sentinel` runs at SubagentStop. If still failing :
```bash
# Manual resolution
python .claude/python/sdd_scripts/resolve_us_hash_sentinel.py --auto-detect
```

---

### `[SEC_*]` (security findings RED)

**Symptom** : `/sdd-review` returns 🔴 with one of 8 hard-blocking SEC classes.

**Cause** : Detected pattern matching OWASP Top 10 categories.

**Fix** : **Never bypass.** Read the report :
```bash
cat workspace/output/qa/feat-1/security-scan.md
```
Each finding lists `file:line` + suggested mitigation. Fix the code, then re-run `/sdd-review 1`.

If you believe it's a false positive : open an issue with the file path + finding + your reasoning. **Don't lower `SecurityFailOn`** to bypass — these 8 classes (`[SEC_SQL_INJECTION]`, `[SEC_BROKEN_AUTHZ]`, etc.) are **hard-blocking by design**.

---

### `[CHECKPOINT_HASH_MISMATCH]`

**Symptom** : `/sdd-full --resume` rejects because input hash differs.

**Cause** : You modified a FEAT/US between two runs. The checkpoint can no longer guarantee idempotence.

**Fix** :
```bash
# Either accept re-execution (no --resume)
/sdd-full 1
# OR reset the checkpoint
rm workspace/output/.sys/.state/state-*.json
/sdd-full 1 --resume
```

---

### `[ENV_BYPASS_BLOCKED]`

**Symptom** : `block_env_bypass` hook refuses a Bash command containing `SDD_ALLOW_*=` or `SDD_DISABLE_*=`.

**Cause** : Defense-in-depth — Claude Code is trying to bypass a guardrail mid-session.

**Fix** : Bypass env vars must be set in the **parent shell BEFORE** starting Claude Code :
```bash
# In your terminal, BEFORE claude
export SDD_DISABLE_COST_CAP=1
claude
# Now in Claude Code session
/sdd-full 1                # bypass is honored
```

---

### `[ACCEPTANCE_REPORT_MISSING]` (CI only)

**Symptom** : In CI, the `validate_acceptance_gate` hook DENIES because `acceptance.json` is missing.

**Cause** : The qa agent did not invoke `validate_acceptance.py`. In CI strict mode, this is a hard fail.

**Fix** :
```bash
# Locally
/qa-generate 1                  # invokes validate_acceptance.py
# In CI, ensure qa agent ran AND the script was executed
# OR explicit bypass (audit-logged)
export SDD_ALLOW_ACCEPTANCE_BYPASS=1
```

---

## ❓ FAQ

### Why is `/sdd-full 1` re-running everything when I pass `--resume` ?

Before v7.0.0-alpha, `--resume` only re-read the run ID without routing logic. Since the latest fix (D5), `sdd_state.py resume-target` returns the STEP label of the first non-done phase. If you still see full re-runs, check that the `runs` table in `console.db` has `phases` rows :

```bash
python .claude/python/sdd_scripts/sdd_state.py show-run --run-id <id>
```

---

### Why does `dev-frontend` not run, yet build is green ?

The agent **exits silently** if the US is backend-only (no UI ACs, no HTML mockup). This is by design (cf. `dev-shared-preflight.md`).

Confirm with :
```bash
cat workspace/output/us/1-2-Auth.md | grep -A 3 "## Acceptance Criteria"
```

If you expect frontend work, ensure the US has UI-related ACs or a mockup HTML at `workspace/input/ui/1-2-Auth.html`.

---

### Where does the cost cap data come from ?

From `workspace/output/db/console.db` table `token_usage`. Each agent's actual token consumption is captured by the `record_token_usage` hook (PostToolUse Agent + SubagentStop). If the cap seems wrong, inspect :

```bash
python .claude/python/sdd_admin/verify_telemetry_health.py
sqlite3 workspace/output/db/console.db "SELECT agent, SUM(input_tokens), SUM(output_tokens) FROM token_usage GROUP BY agent;"
```

---

### How do I know if my stack combo is validated ?

Check the entête `Validation:` line of each stack `.md` file :

```bash
head -10 .claude/stacks/backend/dotnet-minimalapi.md
# Look for: Validation: 🟢 reference  OR  🟢 bench-validated runtime  OR  🟡 experimental
```

Or read the consolidated table in [validated-combos.md](validated-combos.md).

---

### Can I run SDD_Pro in CI ?

Yes. Set these env vars in your CI workflow :
```yaml
env:
  CI: true                          # auto-detected by hooks
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  SDD_RUN_ID: ${{ github.run_id }}  # stable scope for telemetry
```

And invoke non-interactively :
```bash
python bootstrap.py --combo c1 --skip-install --auto-init
# Then in claude-code-non-interactive mode
claude --no-interactive "/sdd-full 1"
```

In CI, hooks DENY on missing acceptance reports (strict mode) and cost cap telemetry errors. Set bypass env vars consciously (audit-logged).

---

### How can I add a new agent ?

1. Add the prompt under `.claude/agents/your-agent.md`
2. Add metadata to `.claude/loader.yml`
3. Add to `sdd_hooks/preflight_agent_budget.py::ALLOWED_AGENTS`
4. Add to `sdd_scripts/context_budget.py::CURRENT_AGENTS` + `DEFAULT_BUDGETS`
5. Wire SubagentStop matcher in `settings.json`
6. Create reference card in `docs/agents-reference.md`

Tests :
```bash
python -m pytest .claude/python/tests/test_ownership_matrix_sync.py
python -m pytest .claude/python/tests/test_preflight_agent_budget.py
```

---

### How can I add a new stack ?

See [poc-roi-methodology.md](poc-roi-methodology.md) — the validation bar is real (2 combos must pass `/sdd-full` end-to-end + a FEAT M on each).

Quick start :
```bash
# 1. Add the .md describing layers, libs, conventions
# Path: .claude/stacks/{category}/{stack-id}.md
# 2. Add the .libs.json catalog
# Path: .claude/stacks/{category}/{stack-id}.libs.json
# 3. Validate
python .claude/python/sdd_admin/validate_libs_catalog.py --stack-id your-stack
# 4. Sync §2.4
python .claude/python/sdd_admin/sync_stack_md.py --stack-id your-stack
```

---

### Why does `/sdd-status` show "no run" ?

Either :
- You haven't run `/sdd-full` / `/dev-run` yet on this FEAT.
- The `console.db` was reset (check `workspace/output/db/console.db` exists).
- `sdd_state.py new-run` failed silently (check stderr from your last run).

```bash
ls workspace/output/db/console.db    # should exist
python .claude/python/sdd_scripts/sdd_state.py list-runs --limit 5
```

---

### My console shows `[WARN] telemetry-health verdict=SUSPECT`. Is the framework broken ?

No. This WARN means the `token_usage` table has some incomplete rows (typically `run_id IS NULL` from before a v7.0.0-alpha fix). The framework works ; the cost cap is just operating on slightly noisy data.

To diagnose :
```bash
python .claude/python/sdd_admin/verify_telemetry_health.py
```

---

## 🔧 Extended error reference (audit 2026-06-08 — 25+ additional classes)

This appendix complements §🚨 above with classes encountered less
frequently but documented for completeness. Same format : symptom →
cause → fix.

### `[INVALID_ARG]` (commands / scripts)
**Symptom** : `/dev-backend 1` exits with `INVALID_ARG`.
**Cause** : argument regex `^\d+-\d+(:plan)?$` not matched (you passed `1`
instead of `1-1`).
**Fix** : provide both FEAT number AND US number, e.g. `/dev-backend 1-1`.

### `[INVALID_MODE]`
**Symptom** : `/dev-backend 1-1:plan` exits with `[INVALID_MODE]`.
**Cause** : a `*.back.md` plan already exists for this US — re-running
in `:plan` mode is forbidden (use without `:plan` to consume the
existing plan, or delete it first).
**Fix** : `rm workspace/output/plans/1-1-*.back.md` then retry.

### `[PROJECT_NOT_INIT]`
**Symptom** : `dev-backend` STOPs : "no .csproj / package.json / pyproject.toml found".
**Cause** : `arch` has not yet scaffolded the backend project.
**Fix** : run `/arch-init` first (or just `/dev-run {n}` which orchestrates it).

### `[FORCE_CUMUL_REJECTED]`
**Symptom** : `/sdd-full 1 --force --no-validate` rejected.
**Cause** : ≥ 2 bypass flags cumulated without explicit env auth.
**Fix** : use only one flag at a time, OR `export SDD_ALLOW_FORCE=1` if
you really mean to combine them (audit-logged).

### `[GRANULARITY_VIOLATION]`
**Symptom** : `/us-generate 1` exits with this class.
**Cause** : FEAT split would produce > 10 US (configurable
`UsGranularityHardCap`).
**Fix** : split the FEAT into 2-3 smaller FEATs, OR pass `--allow-large-feat`
(audit-logged).

### `[TRACEABILITY_GAP]`
**Symptom** : `/us-generate` warns about SFD-3 not covered by any US.
**Cause** : the agent could not map SFD-3 to any AC during US generation.
**Fix** : check that SFD-3 is genuinely a need (not a duplicate of SFD-1)
and that at least one AC references it. Adjust FEAT, re-run.

### `[READINESS_NO_GO]`
**Symptom** : `/feat-validate 1` exits NO-GO.
**Cause** : ≥ 1 blocking finding (ACs without Given/When/Then, missing
stacks, etc.).
**Fix** : read the readiness report at `workspace/output/.sys/.validation/1-readiness.md`,
correct each blocking finding listed. **Don't pass --force unless you
know what you're doing** — readiness gate is your safety net.

### `[CONFIG_SECURITY_DOWNGRADE]`
**Symptom** : `read_layered_config` exits with this class.
**Cause** : your project's `stack.md` tries to lower a security policy
(e.g. `CoverageMin: 60`) while the team-level baseline requires `80`.
**Fix** : either accept the team baseline, OR negotiate a team-config
update with your security officer (audit-logged decision).

### `[SCHEMA_MISMATCH]`
**Symptom** : `dev-backend` fails STEP 4.5 with `[SCHEMA_MISMATCH]`.
**Cause** : your US references entity `User.role` but `schema.json` does
not declare `role` on `User`.
**Fix** : update `## Data Model` in the FEAT and re-run `/arch-init` to
regenerate schema, OR remove the `role` reference from the US.

### `[LIBNAME_SIGNATURE_CONFLICT]`
**Symptom** : second `dev-*` agent STOPs : "{LibName}/Models/User.cs exists
with different signature".
**Cause** : `dev-backend US 1-1` and `dev-frontend US 1-2` both want to
define `User` DTO in the shared LibName project, but with incompatible
fields.
**Fix** : harmonize the entity contract upstream — either via
`/dev-plan` review, or by adjusting the US to use a consistent DTO.

### `[LOCK_HELD]`
**Symptom** : `/dev-run` STOPs : "console status lock held by ...".
**Cause** : another `/sdd-full` or console session is updating
`workspace/console/status.json`.
**Fix** : wait 10s (lock TTL), retry. If persistent, check no orphan
process holds `workspace/console/.status.lock` and delete it.

### `[BREAKING_CLEANUP_FAILED]`
**Symptom** : build is green but `dev-*` STOPs at post-build cleanup.
**Cause** : `mark_breaking_resolved.py` failed to edit `CLAUDE.md` (file
permissions, malformed YAML in the BREAKING CHANGES section).
**Fix** : check write perms on the project `CLAUDE.md`, fix the YAML
syntax if needed, re-run `/dev-run {n}` (idempotent).

### `[API_GATE_RED]`
**Symptom** : `/dev-run` STOPs after backend with RED API Gate.
**Cause** : in-memory API tests detected contract mismatch (404 on
documented endpoint, 401 instead of 200, etc.).
**Fix** : open `workspace/output/qa/feat-{n}/api-tests.md`, read which
endpoint failed, fix the backend (re-run `/dev-backend {n}-{m}`).

### `[QA_OWNERSHIP_VIOLATION]`
**Symptom** : `dev-backend` STOPs : "trying to write `*.Tests/...`".
**Cause** : agent confusion — tests are owned by `qa` agent only.
**Fix** : remove test file references from the dev-* plan. Tests are
generated separately by `/qa-generate {n}`.

### `[PLAN_AC_COVERAGE_GAP]`
**Symptom** : `validate_plan.py` exits 2 with this class.
**Cause** : the plan file `## ACs Coverage Summary` table is missing
some AC IDs that the US declares.
**Fix** : re-run `/dev-plan {n}-{m}` (idempotent), or manually edit the
plan to add the missing AC mappings.

### `[US_DEPS_CYCLE]`
**Symptom** : `validate_us_deps.py` exits 3.
**Cause** : US-1-2 depends on US-1-3 which depends on US-1-2 — cycle.
**Fix** : break the cycle in `## Dependencies` sections of the US files.

### `[STATUS_FLIP_FAILED]`
**Symptom** : `set_us_status.py` fails to persist Status: Done.
**Cause** : US frontmatter malformed, `Status:` line not found.
**Fix** : verify the US file has the standard `Status: {value}` line at
the top of the frontmatter block.

### `[REVIEW_REPORT_STALE]` (CRIT-5, 2026-06-07)
**Symptom** : `/sdd-review {n}` prints WARN about stale reports.
**Cause** : an auditor JSON was written before `dev-*` materialized the
latest code — verdict may be a false 🟢.
**Fix** : re-run the relevant auditor (e.g. `Agent: code-reviewer` for
FEAT {n}) then re-run `/sdd-review {n}`.

### `[REVIEW_SOURCES_MISSING]`
**Symptom** : `/sdd-review {n} --ensure-scans` exits 3.
**Cause** : required auditor source (quality / code-review / security /
spec) has 0 rows in console.db for this FEAT.
**Fix** : the error message lists the exact invocations to re-run. Copy-paste them.

### `[UI_TOKEN_VIOLATION]`
**Symptom** : `dev-frontend` STOPs : hardcoded `#2563eb` in component.
**Cause** : agent wrote hex color directly instead of using `bg-primary` /
CSS token.
**Fix** : `dev-frontend` is supposed to catch this automatically. If it
slipped, edit the file manually : declare `--primary: ...` in
`src/index.css` then use `bg-primary` Tailwind class.

### `[UI_FIDELITY_GAP]`
**Symptom** : frontend renders but diverges visibly from mockup.
**Cause** : labels/structure not matching `workspace/input/ui/{n}-{m}-*.html`.
**Fix** : adjust the mockup OR adjust the generated component, then
re-run `/dev-frontend {n}-{m}` (idempotent).

### `[FRONTEND_BACKEND_CONTRACT_GAP]`
**Symptom** : `code-reviewer` flags 🔴 on a frontend that calls a
non-existent backend endpoint.
**Cause** : frontend was generated targeting `POST /api/foo` but backend
doesn't expose this route.
**Fix** : either add the endpoint backend-side (`/dev-backend {n}-{m}`)
or fix the frontend call to match an existing route.

### `[QA_OUTPUT_INVALID]`
**Symptom** : `/qa-generate` fails to persist coverage.json.
**Cause** : test runner produced malformed coverage output (cobertura
XML truncated, lcov empty).
**Fix** : run the test command manually
(e.g. `dotnet test --collect:"XPlat Code Coverage"`) and inspect the raw
output for errors before retrying QA.

### `[QA_PRECONDITION_FAILED]`
**Symptom** : `/qa-generate 1` STOPs : "no production code under
workspace/output/src".
**Cause** : you tried QA before any dev-* matérialisation.
**Fix** : run `/dev-run 1` first.

### `[ADV_PRECONDITION_FAILED]`
**Symptom** : `/sdd-review 1 --adversarial` STOPs.
**Cause** : standard `/sdd-review` has not been run yet (no `review.md`
file).
**Fix** : run `/sdd-review 1` first (produces the baseline), then
`--adversarial`.

### `[DISCOVER_NO_MATCH]`
**Symptom** : `/sdd-discover-stack` STOPs : "no SDD_Pro combo recognized".
**Cause** : your repo has unusual manifest combinations (e.g.
Flutter+Rust) not yet supported.
**Fix** : either adopt one of the 13 supported combos, OR submit a
catalog PR to add your combo to `.claude/stacks/`.

### `[RUNTIME_STS_EXCEPTION]`
**Symptom** : `/arch-init` emits WARN about non-LTS runtime pinned.
**Cause** : someone pinned .NET 9 (STS) or Node 23 (current) in the
stack.
**Fix** : either migrate to LTS (Node 22, .NET 10), OR add explicit ADR
`runtime-sts-prerelease-exceptions` + `RuntimeException:` in Project
Config (audit-logged).

### `[ACCEPTANCE_GATE_FAILED]`
**Symptom** : `/qa-generate` or `SubagentStop` hook DENY with this
class.
**Cause** : project test / lint / build / coverage / smoke / E2E check
failed.
**Fix** : the error message lists exactly which check failed. Fix that
specific check (it's not a `dev-*` retry — it's your build or
config). Bypass : `SDD_ALLOW_ACCEPTANCE_BYPASS=1` (interactive debug
only).

---

## 📞 When in doubt

- **The audit report** : `workspace/output/.sys/.audit/` has structured logs for every hook.
- **Framework smoke** : `python .claude/python/sdd_admin/framework_smoke.py` — quick health check.
- **Open an issue** with : your error class `[XXX]`, the relevant audit log, and your `stack.md` config (redact secrets).

---

## 🔗 See also

- [../rules/error-classification.md](../rules/error-classification.md) — full taxonomy of `[CLASS]` prefixes
- [config-precedence.md](config-precedence.md) — base ← team ← project config layering
- [hooks-and-protections.md](hooks-and-protections.md) — what each hook does
- [orphan-cleanup-policy.md](orphan-cleanup-policy.md) — clean up after failed runs
