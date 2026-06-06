# SDD_Pro — Config Precedence & Diagnostic (référence)

> Document chargé **à la demande** (`Read @.claude/docs/config-precedence.md`).
> Pas en system prompt. Crée pour résoudre la critique M6 (audit v7.0.0) :
> *« comportement runtime dépend simultanément de stack.md, loader.yml,
> .libs.json, settings.json, phase_planner.py et templates ; diagnostiquer
> un bug requiert de croiser ≥ 4 fichiers »*.
>
> **Objectif** : pour toute clé de configuration ou décision runtime,
> répondre en **30 secondes** à *« d'où vient cette valeur ? »*.

---

## 1. Quick reference — précédence globale

**11 sources de configuration** interagissent dans SDD_Pro. Ordre de
précédence du plus FAIBLE au plus FORT :

```
┌─────────────────────────────────────────────────────────────────────┐
│ #1  Code defaults (Python constants : COVERAGE_HARDENING_KEYS, …)   │ ← le plus faible
├─────────────────────────────────────────────────────────────────────┤
│ #2  .claude/config.base.yml         (framework, versionné SDD_Pro)  │
├─────────────────────────────────────────────────────────────────────┤
│ #3  ~/.sdd/config.team.yml          (org/team policy, opt-in)       │
├─────────────────────────────────────────────────────────────────────┤
│ #4  workspace/input/stack/stack.md  (## Project Config, ## Auditors)│
├─────────────────────────────────────────────────────────────────────┤
│ #5  workspace/input/stack/stack.md  (## Active * — selection stacks)│
├─────────────────────────────────────────────────────────────────────┤
│ #6  .claude/stacks/{cat}/{id}.libs.json  (libs/versions par stack)  │
├─────────────────────────────────────────────────────────────────────┤
│ #7  .claude/loader.yml              (reads/writes par agent — gouv) │
├─────────────────────────────────────────────────────────────────────┤
│ #8  .claude/settings.json           (Claude Code harness — hooks)   │
├─────────────────────────────────────────────────────────────────────┤
│ #9  .claude/settings.local.json     (override local, gitignore)     │
├─────────────────────────────────────────────────────────────────────┤
│ #10 Env vars (SDD_*, AZ_*, DB_*, SMTP_*, SDD_DISABLE_*)             │
├─────────────────────────────────────────────────────────────────────┤
│ #11 CLI flags (--force, --plan, --rebuild-arch, --max-parallel)     │ ← le plus fort
└─────────────────────────────────────────────────────────────────────┘
```

**Règle d'or** : pour résoudre la valeur effective d'une clé, lire les
sources **du plus fort (#11) vers le plus faible (#1)** et s'arrêter au
premier hit. Exception : **security hardening** (cf. §3.2 ci-dessous).

---

## 2. Sources détaillées — qui pilote quoi

### 2.1 Project Config (clés business, calque #2/#3/#4)

| Source | Format | Précédence | Géré par |
|---|---|:---:|---|
| `.claude/config.base.yml` | YAML flat | base | versionné SDD_Pro |
| `~/.sdd/config.team.yml` | YAML flat | team override | équipe (opt-in, %USERPROFILE%/.sdd/) |
| `workspace/input/stack/stack.md` `## Project Config` | KV inline `Key: value` | project final | Tech Lead projet |
| `workspace/input/stack/stack.md` `## Auditors` | bloc alias `name: mode/failOn` | project final (depuis v6.10.5) | Tech Lead projet |

**Lecture** : `sdd_lib/layered_config.py` → `read_layered_config()`. Merge
deep, scalaires écrasés, listes remplacées. Bloc `## Auditors` expandu en
12 clés flat ; clés flat dans `## Project Config` gagnent (backward-compat).

**Audit trail** : `dump_effective_config()` produit `config-effective.yml`
avec `# source: base|team|project` par clé.

**Clés gérées (sous-ensemble)** :
- QA : `QAMode`, `CoverageMin`, `QaFailOnSddFull`
- Auditors : `CodeReviewMode/FailOn`, `SecurityMode/FailOn`,
  `SpecComplianceMode/FailOn`, `ArchReviewMode/FailOn`,
  `A11yMode` (no-op v7), `PerfMode` (no-op v7)
- Pipeline : `MaxParallel`, `BuildLoopMaxIter`, `BuildLoopMaxCostUsd`,
  `MaxCostPerRun`, `MaxOpusInflight`
- Workflow : `GatedWorkflow`, `ApiGateRequired`, `ApiGateMinPerEndpoint`,
  `PlanReviewDefault`, `CheckpointMode`
- Identité projet : `AppName/FrontendName`, `BackendName`,
  `FrontendLocalPort`, `BackendLocalPort`, `LibStrategy`
- Gates v7 : `FeatAntiGigoMode`, `FeatDeepenMode/Threshold`,
  `ElicitorGapMode`, `UsGranularityHardCap/WarnAt`,
  `SpecComplianceRequiredForFeatValidate`
- Tests : `MutationTestingMode/ScoreMin/TimeoutSec`,
  `E2EMode/MinPerUs/TimeoutSec`, `IntegrationTestMode`
- Review : `ReviewMode/FailOn/FailOnSddFull`, `LeanReviewersPreset`
- Telemetry : `TokenUsageMode`, `CiTemplatesGeneration`

### 2.2 Sélection de stacks (calque #5)

`workspace/input/stack/stack.md` blocs **liste** (pas KV) :

| Bloc | Rôle | Multi ? |
|---|---|:---:|
| `## Active Architecture Pattern` | Pattern (mvc/ddd/microservice) | NON (1 seul) |
| `## Active Tech Specs` | backend/* + frontend/* OU fullstack/* OU mobiles/* | OUI (par scope) |
| `## Active UI Specs` | ui/* (1 actif si frontend web) | NON (1 seul) |
| `## Active QA Specs` | qa/* (n actifs) | OUI |
| `## Active Auth Specs` | auth/* (1 seul) + env vars `AZ_*`/`AUTH_*` | NON |
| `## Active Database` | `DatabaseType:` + env vars `DB_*` | NON |
| `## Active SMTP Server` | env vars `SMTP_*` (optionnel) | NON |

**Détection AppType (v6.7.7+)** : auto-déduit depuis `## Active Tech Specs` :
- `backend/* + frontend/*` → `back-front/web`
- `+ mobiles/*` → `back-front/mobile`
- `fullstack/*` seul → `fullstack`
- Mix interdits → `[STACK_COMBO_INVALID]`

**Validation** : `preflight.py` au démarrage de chaque agent dev-*.
Détecte aussi `[STACK_NOT_SELECTED]`, `[STACK_COMBO_INVALID]`.

### 2.3 Catalogue libs (calque #6)

`.claude/stacks/{cat}/{stack-id}.libs.json` — un par stack. Schéma :
`.claude/templates/libs-catalog.schema.json` (draft 2020-12).

**Pilote** :
- versions runtime + libs (`versions.kotlin`, `versions.spring-boot`, …)
- libs CORE (§2.4.a — toujours installées par `arch`)
- libs ON-DEMAND (§2.4.b — déclenchées par triggers regex US via
  `detect_capabilities.py`)
- plugins, buildSystem, manifest paths

**Lectures** : `arch` (Phase A install), `dev-*` STEP 5.bis (capabilities),
`validate_libs_catalog.py` (CI hook), `sync_stack_md.py` (régène §2.4 .md).

**Cohérence** : `.md` régénéré déterministiquement depuis `.libs.json`.
Source de vérité = `.libs.json`, jamais le `.md`.

### 2.4 Loader manifest (calque #7)

`.claude/loader.yml` — qui lit/écrit quoi, par agent. **Source de vérité
unique** pour :
- context budget (`context_budget.py` HARD-GATE 10/11 agents)
- audit chevauchements cross-agent
- estimation tokens pré-invocation
- cache layers (`stable | semi | volatile`, cf. `cache-strategy.md`)

**Pilote indirectement** :
- ce qui sera lu par chaque agent → coût tokens estimé
- détection lectures forbidden (cf. `forbidden_reads:`)
- ledger JSONL par run dans `console.db`

### 2.5 Harness Claude Code (calques #8/#9)

| Fichier | Rôle | Git |
|---|---|:---:|
| `.claude/settings.json` | Hooks (PreToolUse, PostToolUse, SubagentStop, Stop, …), permissions | versionné |
| `.claude/settings.local.json` | Override local opérateur (env, permissions ajoutées) | gitignored |

**Pilotent** :
- hooks SDD_Pro : `preflight_cost_cap.py`, `preflight_agent_budget.py`,
  `validate_augment_contract.py`, etc.
- security strict R1-R5 (commit `3d1bd1e`)
- permissions Bash/Read/Write granulaires
- env vars injectées au runtime Claude Code

### 2.6 Env vars (calque #10)

**Trois familles** :

| Préfixe | Source | Exemple | Override |
|---|---|---|---|
| `SDD_*` | Framework | `SDD_DISABLE_COST_CAP=1`, `SDD_TEAM_CONFIG=/path`, `SDD_TOKEN_USAGE_MODE=off`, `SDD_ALLOW_FORCE=1` | One-shot bypass |
| `AZ_*` / `AUTH_*` | Auth | `AZ_TENANTID`, `AZ_CLIENTID`, `AZ_AUDIENCES` | injectées via `## Active Auth Specs` |
| `DB_*` / `SMTP_*` | Infra runtime | `DB_HOST`, `DB_NAME`, `SMTP_USER` | injectées via `## Active Database`/`## Active SMTP Server` |

Les env vars `AZ_*/DB_*/SMTP_*` viennent du `stack.md` (parsées par
preflight + arch) → propagées dans `appsettings.json`/`application.yml`/
etc. par arch Phase B.

Les env vars `SDD_*` sont lues directement par les scripts Python (ex.
`SDD_TEAM_CONFIG` override `~/.sdd/config.team.yml`).

### 2.7 CLI flags (calque #11)

Override le plus fort, audit-loggué dans
`workspace/output/.sys/.audit/force-bypass.log` :

| Flag | Commandes | Effet | Audit |
|---|---|---|:---:|
| `--force` | `/sdd-full`, `/dev-run` | Bypass readiness NO-GO, plan-then-review gate | OUI |
| `--no-validate` | `/sdd-full` | Skip `/feat-validate` | OUI |
| `--no-plan-on-warn` | `/sdd-full` | Skip plan-then-review sur WARN | OUI |
| `--plan` | `/sdd-full`, `/dev-run` | Force génération plans pré-dev | NON |
| `--rebuild-arch` | `/sdd-full`, `/dev-run` | Force re-run arch (skip short-circuit) | NON |
| `--resume` | `/sdd-full`, `/dev-run` | Reprend run interrompu | NON |
| `--manual-gates` | `/sdd-full` | Active gates manuels opt-in | NON |
| `--max-parallel N` | `/dev-run` | Override `MaxParallel` (1-12) | NON |
| `--allow-large-feat` | `/sdd-full` | Bypass `UsGranularityHardCap` | OUI |
| `--ensure-scans` | `/sdd-review` | Force re-run scans avant agrégation | NON |
| `--fail-on {level}` | `/sdd-review` | Override `ReviewFailOn` ponctuel | NON |

**Garde-fou** : `[FORCE_CUMUL_REJECTED]` si ≥ 2 bypass flags cumulés sans
`SDD_ALLOW_FORCE=1` (R1 v7.0.0).

### 2.8 Phase planner (méta-décideur, dérivé)

`phase_planner.py` n'est **PAS une source** mais un **dérivateur** : il
lit calques #2-#5 + l'état runtime du workspace et produit un plan
d'exécution (`enabled/skipped/why` par phase auditor).

Invoqué par `/sdd-full` STEP 1.quart (non bloquant, récap unifié ; renommé depuis 1.tiers lors de l'audit P0-workflow 2026-06-05).

---

## 3. Règles spéciales

### 3.1 AppType — auto-détection (pas de clé manuelle)

L'AppType **n'est pas une clé Project Config**. Il est dérivé par
`preflight.py` depuis `## Active Tech Specs` :

```
backend/* (1) + frontend/* (1) + (optional ui/*) → back-front/web
backend/* (1) + mobiles/* (1)                    → back-front/mobile
fullstack/* (1)                                  → fullstack
mobiles/* (1) [+ optional backend/* distant]     → mobile-{react-native|maui}
```

Toute autre combinaison → `[STACK_COMBO_INVALID]`.

### 3.2 Security hardening — exception à la précédence

**Cas spécial** : un calque haute précédence ne peut PAS **relâcher** la
policy d'un calque plus bas pour ces clés :

```
SecurityFailOn, A11yFailOn, CodeReviewFailOn, PerfFailOn,
SpecComplianceFailOn, CoverageMin
```

Si `team.yml: SecurityFailOn=critical` et `stack.md: SecurityFailOn=minor`
→ `ConfigError [CONFIG_SECURITY_DOWNGRADE]` au load.

**Le projet peut DURCIR (raise), jamais RELÂCHER (lower).** Implémenté
dans `_check_security_down()` (`layered_config.py`).

Ordre sévérité : `critical < serious < moderate < minor` (critical le
plus strict). Pour `CoverageMin` : numérique, projet ≥ team requis.

### 3.3 Clés deprecated v7.0.0 — tolérées en lecture

Trois clés sont **lues mais ignorées** runtime (no-op, conservées pour
backward-compat) :

| Clé | Raison | Remplacement |
|---|---|---|
| `PlanCacheStrict` | `dev-*-strict` retirés (auditors-trim) | aucun (plan v2 conservé pour review humaine) |
| `A11yMode` | `accessibility-auditor` retiré | `axe-core` CI projet généré |
| `PerfMode` | `performance-auditor` retiré | Lighthouse CI + wrk/k6 projet généré |
| `SecurityThreatModelEnabled` | mode `threat-model` retiré | template humain `templates/threat-model.template.md` |

Toute valeur passée pour ces clés sera **silencieusement ignorée**. Pas
d'ERROR, juste no-op. Pour audit-log explicite, voir
`dump_effective_config()` qui marque la source.

### 3.4 Idempotence vs override

Certains scripts sont **idempotents** (re-run sans effet de bord) :
- `arch` : skip short-circuit si bootstrap stable (force via `--rebuild-arch`)
- `dev-*` : skip silencieux si US déjà matérialisée sans drift
- `/feat-generate` : skip création constitution.md si existe

D'autres sont **destructifs** sans flag :
- `/qa-generate` : overwrite `coverage.json` chaque run
- `/sdd-review` : overwrite `code-review.json` chaque run
- `dashboard` (retiré v7.0.0) : régénérait `INDEX.md` (maintenant script `index_adrs.py`)

---

## 4. Arbre de diagnostic — *« d'où vient cette valeur ? »*

```
Question : la clé K a la valeur V au runtime. Pourquoi ?

┌─────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 0 : produire le dump effectif                                 │
│                                                                     │
│  python -c "from sdd_lib.layered_config import dump_effective_config│
│             from pathlib import Path                                │
│             dump_effective_config(Path('config-effective.yml'))"    │
│                                                                     │
│  → ouvre config-effective.yml, cherche `K:` → la ligne porte la     │
│    source : `# source: base | team | project`                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
   source=project        source=team            source=base
        │                     │                     │
        ↓                     ↓                     ↓
  stack.md             ~/.sdd/config.        .claude/config.
  ## Project Config    team.yml              base.yml
  OU ## Auditors       (override équipe)     (framework default)
        │                                          │
        ↓                                          ↓
   « valeur du Tech Lead »            « valeur SDD_Pro défaut »

Question : V vient quand même d'ailleurs (calque non couvert par dump) ?

┌─────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 1 : env var en cours ?                                        │
│                                                                     │
│  echo $env:SDD_*    # PowerShell                                    │
│  echo $env:AZ_* $env:DB_* $env:SMTP_*                               │
│                                                                     │
│  → si SDD_DISABLE_COST_CAP=1, SDD_ALLOW_FORCE=1, SDD_TEAM_CONFIG,   │
│    etc. présent → bypass actif                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 2 : CLI flag passé ?                                          │
│                                                                     │
│  Relire l'invocation : /sdd-full {n} --force --plan …               │
│  + workspace/output/.sys/.audit/force-bypass.log                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 3 : décision dérivée par phase_planner ?                      │
│                                                                     │
│  python .claude/python/sdd_scripts/phase_planner.py \               │
│         --feat-number {n} --json | jq                                │
│                                                                     │
│  → champ "phases.{name}.enabled" + "reason"                         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ ÉTAPE 4 : règle spéciale activée ?                                  │
│                                                                     │
│  - [CONFIG_SECURITY_DOWNGRADE] = projet a tenté de relâcher         │
│  - [STACK_COMBO_INVALID] = ## Active Tech Specs incohérent          │
│  - [STACK_NOT_SELECTED] = stack requis absent                       │
│  - [FORCE_CUMUL_REJECTED] = ≥ 2 flags cumulés sans SDD_ALLOW_FORCE  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ↓
                       VALEUR EFFECTIVE
```

---

## 5. Troubleshooting — bugs courants

### 5.1 *« Mon QA passe coverage 70 % mais le pipeline reste rouge »*

| Vérification | Commande |
|---|---|
| Valeur effective `CoverageMin` | `dump_effective_config()` → cherche `CoverageMin:` |
| Source = `team` ? | `~/.sdd/config.team.yml` impose un plancher |
| Source = `base` ? | `config.base.yml` (défaut `80`) |
| Bypass possible | `CoverageMin: 0` dans `## Project Config` stack.md (tracé git) |

**Cause typique** : `team.yml: CoverageMin=80` et projet a tenté `CoverageMin=70`
→ `[CONFIG_SECURITY_DOWNGRADE]` (numérique : `p < t` rejected, cf. §3.2).

### 5.2 *« Le frontend n'est pas généré alors que j'ai déclaré react »*

| Vérification | Source |
|---|---|
| `## Active Tech Specs` contient `frontend/react.md` ? | `stack.md` calque #5 |
| `## Active UI Specs` contient un `ui/*.md` ? | `stack.md` calque #5 (requis si frontend web) |
| AppType détecté = `back-front/web` ? | `python preflight.py --json` |
| US non frontend-pure ? | check US `Covers:` (si que backend AC, skip silencieux dev-frontend) |
| Gate API verdict = `FAIL` ? | `workspace/output/qa/feat-{n}/api-tests.json` champ `status` |

### 5.3 *« Mon `--force` ne marche pas »*

| Vérification | Source |
|---|---|
| `--force` cumulé avec `--no-validate` ou `--no-plan-on-warn` ? | log `[FORCE_CUMUL_REJECTED]` |
| `SDD_ALLOW_FORCE=1` env var présente ? | PowerShell `$env:SDD_ALLOW_FORCE` |
| Hard-blocking class active ? (`[SEC_SECRET_HARDCODED]`, `[SEC_SQL_INJECTION]`, …) | rapport security-scan |
| `[SPEC_COMPLIANCE_REQUIRED]` activé ? | `SpecComplianceRequiredForFeatValidate: true` v7.0.0 défaut |

### 5.4 *« arch n'installe pas la lib X dont j'ai besoin »*

| Vérification | Source |
|---|---|
| Lib présente dans `core[]` du `.libs.json` ? | `.claude/stacks/{cat}/{id}.libs.json` |
| Lib en `onDemand[]` + trigger US ? | check regex `triggers[]` dans `.libs.json` |
| `Capabilities: {cap}` dans `## Project Config` ? | force install au bootstrap |
| `## Capabilities Override` dans stack.md ? | override la lib par défaut d'une capability |

**Si lib hors `.libs.json`** : STOP `[STACK_LIBRARY_MISSING]` attendu. Ne
JAMAIS éditer manuellement `build.gradle.kts`/`package.json` — éditer
`.libs.json` puis `sync_stack_md.py`.

### 5.5 *« Un auditor que je veux désactiver tourne quand même »*

| Vérification | Source |
|---|---|
| Mode actuel dans dump effectif | `dump_effective_config` → ex. `CodeReviewMode` |
| Bloc `## Auditors` dans stack.md ? | écrasé par clés flat `## Project Config` (backward-compat) |
| `phase_planner.py --json` dit quoi ? | champ `phases.{name}.enabled` + `reason` |
| Stack-conditional override (ex. `[PERF_AC_VIOLATION]`) ? | AC US mentionne LCP/p95 → force enable même en `manual` |

### 5.6 *« Le cost cap se déclenche tout le temps »*

| Vérification | Source |
|---|---|
| `MaxCostPerRun` effectif | dump (`base.yml` défaut `50.00`, projet peut DURCIR uniquement) |
| Bypass one-shot | `SDD_DISABLE_COST_CAP=1` env var |
| Bypass projet | `MaxCostPerRun: 0` dans `## Project Config` (désactivé) |
| Cumul du run en cours | `query_console_db.py --table token_usage --run-id {id}` |

---

## 6. Fichiers — mapping rapide

| Question | Fichier |
|---|---|
| *Quelle valeur de `CoverageMin` ?* | `dump_effective_config()` |
| *Quel stack backend actif ?* | `stack.md` `## Active Tech Specs` |
| *Quelle lib `core` installée par arch ?* | `.claude/stacks/{cat}/{id}.libs.json` `core[]` |
| *Quel agent lit quel fichier ?* | `.claude/loader.yml` `{agent}: reads:` |
| *Quel hook s'exécute sur Bash ?* | `.claude/settings.json` `hooks.PreToolUse.Bash` |
| *Quelle env var override le team config ?* | `SDD_TEAM_CONFIG` |
| *Quels flags ont été utilisés ?* | `workspace/output/.sys/.audit/force-bypass.log` |
| *Quelle phase auditor est enabled ?* | `phase_planner.py --json` |
| *Quel ADR a décidé X ?* | `workspace/output/.sys/.context/adrs/INDEX.md` ou grep adrs/*.md |
| *Pourquoi le pipeline n'a pas tourné Y ?* | `workspace/output/.sys/.state/run-*.json` |

---

## 7. Commande one-shot — diagnostic complet

À reproduire à chaque investigation runtime (≤ 30 sec) :

```powershell
# 1. Dump config effective avec sources
python -c @"
from sdd_lib.layered_config import dump_effective_config
from pathlib import Path
dump_effective_config(Path('workspace/output/.sys/config-effective.yml'))
"@

# 2. Phase planner status
python .claude/python/sdd_scripts/phase_planner.py --feat-number 1 --json > workspace/output/.sys/phase-plan.json

# 3. AppType + stacks détectés
python .claude/python/sdd_scripts/preflight.py --json 2>&1 | Tee-Object workspace/output/.sys/preflight.json

# 4. Env vars SDD_*
Get-ChildItem env: | Where-Object Name -Like 'SDD_*'

# 5. CLI flags du dernier run
Get-Content workspace/output/.sys/.audit/force-bypass.log -Tail 20

# 6. État pipeline
Get-Content workspace/output/.sys/.state/run-*.json | Select-Object -Last 5
```

Les 6 fichiers résultants donnent une image **complète** de l'état config
en moins de 30 secondes — sans avoir à croiser manuellement les 11 sources.

---

## 8. Pointers

- `@.claude/python/sdd_lib/layered_config.py` — implémentation precedence #1-#4
- `@.claude/python/sdd_lib/project_config.py` — parser stack.md (legacy + alias)
- `@.claude/python/sdd_scripts/phase_planner.py` — méta-décideur dérivé
- `@.claude/python/sdd_scripts/preflight.py` — détection AppType + validation stacks
- `@.claude/config.base.yml` — calque #2 (lecture directe)
- `@.claude/loader.yml` — calque #7
- `@.claude/settings.json` — calque #8
- `@.claude/rules/library-and-stack.md` — règles libs (CORE vs on-demand, CVE, LTS)
- `@.claude/docs/architecture.md §4` — stacks supportés + combos validés

---

*Document maintenu à chaque ajout de calque ou de clé. Source de vérité
pour le diagnostic runtime. Référencé depuis CLAUDE.md §12 + architecture.md §1.bis.*
