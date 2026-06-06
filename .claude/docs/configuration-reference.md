# ⚙️ Configuration Reference

All Project Config keys + their layered defaults, ranges, and behaviour. Source of truth : `.claude/config.base.yml` (framework defaults) ← `~/.sdd/config.team.yml` (team overrides) ← `workspace/input/stack/stack.md ## Project Config` (project specific).

> 💡 **Precedence rule** : the **most specific layer wins**. Security thresholds **cannot be lowered** by a project override (cf. [config-precedence.md](config-precedence.md) §4).

---

## 🧭 Quick reference (alphabetical)

| Key | Default | Range / Values | Effect |
|---|---|---|---|
| `A11yFailOn` | `serious` | `info \| minor \| moderate \| serious \| critical` | Threshold for axe-core CI to flag 🔴 (retired, ingest-only) |
| `A11yMode` | `off` | `off \| ingest` | Enable axe-core ingest from CI (no agent) |
| `ApiGateMinPerEndpoint` | `2` | `≥ 1` | Min tests per endpoint at API Gate |
| `ApiGateRequired` | `true` | `true \| false` | If false, API Gate WARN instead of RED |
| `ArchReviewFailOn` | `serious` | `info \| minor \| moderate \| serious \| critical` | Threshold for `arch-reviewer` verdict 🔴 |
| `ArchReviewMode` | `manual` | `off \| manual \| full` | `full` = auto-invoke in `/sdd-review` |
| `BuildLoopMaxCostUsd` | `15.00` | `≥ 0` (USD), `0` disabled | Per-US Opus cap before STOP `[BUILD_LOOP_COST_EXCEEDED]` |
| `BuildLoopMaxIter` | `3` | `≥ 1` | Max correctible build attempts before fail-fast |
| `CheckpointMode` | `off` | `off \| resume` | Input-hash validated resume of partial phases |
| `CiTemplatesGeneration` | `true` | `true \| false` | `arch` generates `.github/workflows/quality.yml` |
| `CodeReviewFailOn` | `critical` | `info \| minor \| moderate \| serious \| critical` | Threshold for `code-reviewer` verdict 🔴 |
| `CodeReviewMode` | `full` | `off \| manual \| full` | `full` = invoked in `/sdd-review` batch |
| `CoverageMin` | **obligatoire** | `0-100` (`0` = disabled) | Min lines coverage (global + per-stack) ; rejet `[QA_COVERAGE_GAP]` |
| `E2EMinPerUs` | `1` | `≥ 0` | Playwright tests minimum per US (if `E2EMode: full`) |
| `E2EMode` | `off` | `off \| full` | Playwright opt-in (stack-aware ingest) |
| `E2ETimeoutSec` | `300` | `≥ 60` | Per-test timeout (seconds) |
| `ElicitorGapMode` | `warn` | `off \| warn \| strict` | If `strict` : un-mapped FAIL-N/EDGE-N → NO-GO |
| `FeatAntiGigoMode` | `warn` | `off \| warn \| strict` | "Garbage In, Garbage Out" detection on FEATs |
| `FeatDeepenMode` | `warn` | `off \| warn \| strict` | `strict` = NO-GO if `/feat-deepen` not run on complex FEATs |
| `FeatDeepenThreshold` | `3` | `0-5` | Complexity score above which `/feat-deepen` is recommended |
| `GatedWorkflow` | `true` | `true \| false` | If false, legacy parallel back/front (deconseille) |
| `LeanReviewersPreset` | `false` | `true \| false` | Lean preset (only `code-reviewer`, others `manual`) |
| `MaxCostPerRun` | `50.00` | `≥ 0` (USD), `0` disabled | Run-level USD cap ; STOP `[COST_CAP_EXCEEDED]` ≥ 100% |
| `MaxParallel` | `3` | `1-12` | Concurrent dev-* invocations (back+front = 2× when both active) |
| `MutationScoreMin` | `60` | `0-100` % | Min mutation kill rate (Stryker etc., opt-in) |
| `MutationTestingMode` | `off` | `off \| full` | Mutation testing opt-in |
| `MutationTestingTimeoutSec` | `600` | `≥ 60` | Per-class timeout (seconds) |
| `PerfFailOn` | `serious` | `info \| minor \| moderate \| serious \| critical` | Threshold for Lighthouse/SLO ingest (retired-agent ingest-only) |
| `PerfMode` | `off` | `off \| ingest` | Lighthouse CI ingest opt-in |
| `PlanCacheStrict` | `false` | DEPRECATED no-op | Was used by retired `dev-*-strict` variants |
| `PlanReviewDefault` | `true` | `true \| false` | Default for `--plan` flag on `/sdd-full` |
| `QaFailOnSddFull` | `true` | `true \| false` | QA 🔴 RED blocks `/sdd-full` post-STEP 4.5 (symmetry with standalone) |
| `QAMode` | `manual` | `off \| quality-only \| tests-only \| tests+coverage \| full \| manual` | What `/qa-generate` runs |
| `ReviewFailOn` | `serious` | `info \| minor \| moderate \| serious \| critical` | Aggregate threshold for `/sdd-review` 🔴 |
| `ReviewFailOnSddFull` | `true` | `true \| false` | `/sdd-review` 🔴 blocks `/sdd-full` |
| `ReviewMode` | `full` | `full \| scans-only \| read-only \| manual \| off` | Master switch for review batch |
| `SecurityFailOn` | `critical` | `info \| minor \| moderate \| serious \| critical` | Threshold for `security-reviewer` verdict 🔴 (override pour 8 classes hard-blocking) |
| `SecurityMode` | `full` | `off \| manual \| full` | `full` = invoked in `/sdd-review` batch |
| `SecurityScanEnabled` | `true` | `true \| false` | Master switch security scan |
| `SecurityThreatModelEnabled` | `false` | DEPRECATED | Retired mode v7.0.0 (template humain `threat-model.template.md`) |
| `SpecComplianceFailOn` | `serious` | `info \| minor \| moderate \| serious \| critical` | Threshold for `spec-compliance-reviewer` verdict 🔴 |
| `SpecComplianceMode` | `full` | `off \| manual \| full` | `full` = invoked in `/sdd-review` batch |
| `SpecComplianceRequiredForFeatValidate` | `true` | `true \| false` | `/feat-validate` requires `spec-compliance.json` if code matérialisé |
| `TokenUsageMode` | `record` | `off \| record \| debug` | `record_token_usage` hook behaviour |
| `UsGranularityHardCap` | `10` | `≥ 3` | Hard cap on US count per FEAT (use `--allow-large-feat` to bypass) |
| `UsGranularityWarnAt` | `6` | `≥ 3` | WARN above this US count (was historical hard cap) |

---

## 📚 Detail by category

### Cost & resource caps

```yaml
## Project Config
MaxCostPerRun: 50.00          # Run-level USD cap (cumulative). 0 = disabled.
BuildLoopMaxCostUsd: 15.00    # Per-US Opus cap before [BUILD_LOOP_COST_EXCEEDED].
BuildLoopMaxIter: 3           # Max correctible build attempts.
MaxParallel: 3                # Concurrent dev-* invocations (1-12).
```

**Trade-offs** :
- Raising `MaxCostPerRun` allows finishing large FEATs but risks runaway cost. Default $50 covers a typical 3-US FEAT with margin.
- Raising `BuildLoopMaxIter` (default 3) rarely helps : 4th iteration usually means architectural error (`[BUILD_BLOCKING]`).
- `MaxParallel` > 3 stresses LibName lock + Anthropic rate limits ; **don't go above 6** without monitoring.

---

### Quality gates

```yaml
## Project Config
QAMode: full                  # tests + coverage + quality scan
CoverageMin: 80               # OBLIGATOIRE — no default
GatedWorkflow: true           # arch → back → API Gate → front (strict)
ApiGateRequired: true         # API Gate RED blocks frontend phase
ApiGateMinPerEndpoint: 2      # min tests per endpoint (1 happy + 1 negative)
```

**Strict v7.0.0+ policy** : `passed = global_pct >= CoverageMin AND every_stack_pct >= CoverageMin`. A 95%/100LOC frontend + 50%/10kLOC backend gives global ~50% → 🔴 RED. Tune `CoverageMin` realistically.

---

### Review thresholds (5 reviewers)

```yaml
## Project Config
# Master switches
CodeReviewMode: full          # off | manual | full
SecurityMode: full
SpecComplianceMode: manual    # opt-in (default off in v6.x, manual in v7.0.0)
ArchReviewMode: manual        # opt-in
ReviewMode: full              # /sdd-review master switch

# Thresholds (severity ranks: info < minor < moderate < serious < critical < blocker)
CodeReviewFailOn: critical    # default — only critical+blocker fail
SecurityFailOn: critical      # + 8 hard-blocking classes override threshold
SpecComplianceFailOn: serious # more strict (AC compliance is load-bearing)
ArchReviewFailOn: serious
ReviewFailOn: serious         # aggregate of all 5

# Block sdd-full on review RED?
ReviewFailOnSddFull: true     # default v7.0.0
QaFailOnSddFull: true         # default v7.0.0 (was false in v6.x)
```

**Security policy** : 8 classes are **hard-blocking** regardless of `SecurityFailOn` :
- `[SEC_SECRET_HARDCODED]`, `[SEC_SQL_INJECTION]`, `[SEC_COMMAND_INJECTION]`
- `[SEC_BROKEN_AUTHZ]`, `[SEC_BROKEN_AUTHN]`
- `[SEC_DESERIALIZATION_UNSAFE]`, `[SEC_JWT_MISCONFIG]`, `[SEC_SSRF_RISK]`

Lowering `SecurityFailOn` to `critical` does NOT bypass these.

---

### Workflow controls

```yaml
## Project Config
PlanReviewDefault: true       # /sdd-full --plan by default
CheckpointMode: off           # off | resume — opt-in idempotent resume
FeatDeepenMode: warn          # off | warn | strict — for complex FEATs
ElicitorGapMode: warn         # off | warn | strict — un-mapped FAIL-N/EDGE-N
FeatAntiGigoMode: warn        # off | warn | strict — anti garbage-in
LeanReviewersPreset: false    # if true → only code-reviewer, others manual
```

**Adoption recommendation** :
- Start with defaults (sane sécurité-first).
- Enable `CheckpointMode: resume` once you're comfortable.
- Set `FeatDeepenMode: strict` for FEATs > 4 US (complex domains).

---

### Opt-in features

```yaml
## Project Config
# Mutation testing (Stryker, mutmut, etc.)
MutationTestingMode: off      # full = enable
MutationScoreMin: 60          # kill rate %
MutationTestingTimeoutSec: 600

# Playwright E2E
E2EMode: off                  # full = enable
E2EMinPerUs: 1
E2ETimeoutSec: 300

# A11y / Perf (retired agents → CI ingest only)
A11yMode: off                 # ingest from axe-core CI
A11yFailOn: serious
PerfMode: off                 # ingest from Lighthouse CI
PerfFailOn: serious
```

---

### CI templates

```yaml
## Project Config
CiTemplatesGeneration: true   # arch generates .github/workflows/quality.yml
```

When `true`, the `arch` agent creates :
- `.github/workflows/quality.yml` (axe-core + Lighthouse + lint + tests)
- `.github/dependabot.yml` (auto-updates pinned LTS)
- `templates/threat-model.template.md` (human security threat model)

Set to `false` if you have your own CI conventions.

---

### Telemetry

```yaml
## Project Config
TokenUsageMode: record        # off | record | debug
```

- `off` : no token telemetry recorded (cost cap inoperative)
- `record` : default — every Agent invocation inserts a row in `token_usage`
- `debug` : verbose stderr logging + record

Disabling means losing `MaxCostPerRun` and `BuildLoopMaxCostUsd` enforcement.

---

## 🔐 Security policy : non-bypassable rules

| Policy | Enforcement |
|---|---|
| `SecurityFailOn` cannot be **lowered** below team default | `[CONFIG_SECURITY_DOWNGRADE]` hard block |
| 8 SEC classes hard-block regardless of threshold | `_review_report.py::HARD_BLOCKING_CLASSES` |
| `SDD_ALLOW_*` / `SDD_DISABLE_*` env vars cannot be set mid-session | `block_env_bypass` hook (66 deny patterns) |
| Cost cap cannot be silently bypassed (telemetry-unavailable → DENY in CI) | `preflight_cost_cap.py` |
| Acceptance gate cannot ALLOW silent in CI when report missing | `validate_acceptance_gate.py::_detect_ci` |

These are intentional. Lowering security is always a **tracked decision** (git blame + ADR).

---

## 🌐 Layered config example

`.claude/config.base.yml` (framework default) :
```yaml
SecurityFailOn: critical
CoverageMin: 80
MaxCostPerRun: 50.00
```

`~/.sdd/config.team.yml` (team policy) :
```yaml
SecurityFailOn: serious   # tighter for security-critical org
CoverageMin: 85           # higher bar
ArchReviewMode: full      # always run arch-reviewer
```

`workspace/input/stack/stack.md` `## Project Config` (project specific) :
```yaml
MaxParallel: 6            # bigger machine
CheckpointMode: resume    # team uses --resume often
# Can override SecurityFailOn UP (more strict) but not DOWN
SecurityFailOn: critical  # ← REJETÉ : team is "serious" → cannot loosen
```

Result : `SecurityFailOn: serious`, `CoverageMin: 85`, `MaxParallel: 6`, `CheckpointMode: resume`.

Detail : [config-precedence.md](config-precedence.md).

---

## 🔧 How to inspect the effective config

```bash
# Show resolved config (after all 3 layers merged)
python .claude/python/sdd_scripts/validate_project_config.py --resolve

# Show one specific key
python -c "
import sys; sys.path.insert(0, '.claude/python')
from sdd_lib.layered_config import read_layered_config
cfg = read_layered_config()
print('CoverageMin:', cfg.get('CoverageMin'))
print('SecurityFailOn:', cfg.get('SecurityFailOn'))
"
```

---

## 🔗 See also

- [config-precedence.md](config-precedence.md) — layered config detail
- [hooks-and-protections.md](hooks-and-protections.md) — what each hook does with these keys
- [troubleshooting.md](troubleshooting.md) — when keys cause errors
- [../rules/quality.md](../rules/quality.md) — coverage policy detail
- [../rules/build-and-loop.md](../rules/build-and-loop.md) — GatedWorkflow + API Gate
