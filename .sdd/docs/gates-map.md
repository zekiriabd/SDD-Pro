# Gates Map — inventaire canonique des points de blocage (v7.0.2)

> **Créé 2026-06-11 (audit consolidé M3)** : un `/sdd-full` nominal traverse
> 12 points de contrôle déclarés — sans vue d'ensemble, chaque évolution
> ajoutait sa gate « par sécurité » (prolifération), et personne ne pouvait
> dire combien bloquent réellement par défaut. Ce document est l'**inventaire
> SSoT** : chaque gate, sa classe, son domaine, son enforcer, son bypass.
> Test anti-rot : `tests/test_gates_map.py` (chaque enforcer cité existe).

## 1. Principe de design (anti-prolifération)

1. **1 domaine de blocage = 1 gate primaire.** Avant d'ajouter une gate,
   vérifier dans la table §2-§4 si le domaine a déjà son owner — si oui,
   étendre la gate existante, ne pas en empiler une nouvelle.
2. **Defense-in-depth = sentinelle obligatoire.** Une gate redondante
   volontaire (filet) DOIT court-circuiter quand la primaire a tranché
   (pattern `SDD_FORCE_CUMUL_OK` STEP 3.6.quart) — jamais de double coût.
3. **Observability ≠ gate.** Un step qui ne peut produire que WARN/info
   (drift, audit log, smoke) n'est pas une gate et ne doit pas en porter
   le vocabulaire.
4. **Tout bypass est audit-loggué.** Pas de gate contournable silencieusement.
5. **Enregistrement ici obligatoire** pour toute nouvelle gate (le test
   anti-rot et cette table sont le registre).

## 2. Gates `/sdd-full` (orchestrateur complet)

| STEP | Domaine | Classe | Enforcer | Bloquant défaut | Bypass (audit-loggué) |
|---|---|---|---|:---:|---|
| 1.bis | Cumul de flags bypass | **primaire** | `sdd_scripts/preflight_force_cumul.py` | ✅ | `SDD_ALLOW_FORCE=1` |
| 3.bis / 3.5.bis / 3.6.c / 4.bis | Validation humaine (US / readiness / plan / code) | **opt-in** (LOT 3) | `sdd_scripts/gate_decide.py` | ❌ (`ManualGates` requis) | `--no-manual-gates` |
| 3.5 | Readiness FEAT↔US↔stack | **primaire** | `sdd_scripts/validate_readiness.py` (`/feat-validate`) | ✅ | `--force` / `--no-validate` |
| 3.6 | Plan-then-review (checkpoint humain) | **primaire** (conditionnel) | procédure 3.6 + `sdd_scripts/gate_decide.py` | ✅ si WARN+force ou `--plan` | `--no-plan-on-warn` |
| 3.6.quart | Cumul de flags bypass | **defense-in-depth** | `sdd_scripts/preflight_force_cumul.py` (sentinelle `SDD_FORCE_CUMUL_OK`) | court-circuité si 1.bis OK | idem 1.bis |
| 4.5 | QA (tests + coverage) | **primaire** | `/qa-generate` + `QaFailOnSddFull` | ❌ (`QAMode: manual` défaut → skip) | `QaFailOnSddFull: false` |
| 4.7 | Spec-compliance post-dev | **primaire** (lecteur pur du rapport Stage A — cf. autorité unique `feat-validate.md §4.5.3`) | `/feat-validate --post-dev` | ✅ | `SpecComplianceRequiredForFeatValidate: false` |
| 4.8 | Review qualité consolidé | **primaire** | `sdd_scripts/sdd_review.py` + `ReviewFailOnSddFull` | ✅ (`ReviewMode: full` défaut) | `ReviewFailOnSddFull: false` |
| 4.9 | Drift inline rules | **observability** (jamais bloquant) | `sdd_scripts/validate_inline_rules.py` | ❌ | n/a |

## 3. Gates `/dev-run` (exécution dev)

| STEP | Domaine | Classe | Enforcer | Bloquant défaut | Bypass |
|---|---|---|---|:---:|---|
| 6.0.bis | Staleness des plans | **primaire** | `sdd_scripts/validate_plan.py` (exit 2 = `[PLAN_STALE]`) | ✅ (si plans présents) | re-`/dev-plan` (pas de bypass) |
| 6.b | API Gate back→front | **primaire** | agent `qa` mode api-tests (`build-and-loop.md` Partie A) | ✅ (`GatedWorkflow: true` défaut) | `GatedWorkflow: false` (audit-log) |
| 6.4.A | Spec-compliance (Stage A, two-stage) | **primaire — PRODUCTEUR du verdict spec** | agent `spec-compliance-reviewer` (`auditor-orchestration.md §3`) | ✅ | `--legacy-auditor-parallel` / `SpecComplianceFailOn` |
| 6.4.B | Qualité (code/security/arch batch) | **primaire** | agents reviewers (`auditor-orchestration.md §4`, ownership `auditor-coordination.md`) | ✅ | `{Kind}FailOn` (hors hard-blocking) |

## 4. Gates hooks automatiques (cross-commandes, Claude Code)

| Hook | Domaine | Classe | Enforcer | Bypass |
|---|---|---|---|---|
| PreToolUse Agent | Coût cumulé par run | **primaire** | `sdd_hooks/preflight_cost_cap.py` | `SDD_DISABLE_COST_CAP=1` |
| PreToolUse Agent | Context budget par agent | **primaire** | `sdd_hooks/preflight_agent_budget.py` | config |
| PostToolUse/SubagentStop Agent | Télémétrie coût réel (`token_usage`, source de `preflight_cost_cap.py`) | **defense-in-depth** (alimente le cap ci-dessus) | `sdd_hooks/record_token_usage.py` | n/a |
| PreToolUse Agent | Séquencement two-stage auditors | **defense-in-depth** (de 6.4.A) | `sdd_hooks/enforce_two_stage_auditor.py` | `AuditorBatchMode: legacy-parallel` |
| PreToolUse Skill | Combo stack hors SLA | **primaire** | `sdd_hooks/preflight_stack_combo.py` | `SDD_ALLOW_UNTESTED_COMBO=1` |
| PreToolUse Edit/Write | TDD test-first | **primaire** (warn interactif / strict CI) | `sdd_hooks/enforce_tdd.py` | `SDD_DISABLE_TDD=1` |
| PreToolUse Bash | Set d'env bypass mid-session | **primaire** | `sdd_hooks/block_env_bypass.py` | aucun |
| PostToolUse Edit/Write | Cohérence stack / contrat augment | **defense-in-depth** | `sdd_hooks/validate_stack_consistency.py`, `sdd_hooks/validate_augment_contract.py` | n/a |
| SubagentStop qa | Acceptance Gate (test/lint/build/coverage/smoke/E2E) | **primaire** | `sdd_hooks/validate_acceptance_gate.py` + `sdd_scripts/validate_acceptance.py` | `SDD_ALLOW_ACCEPTANCE_BYPASS=1` |
| SubagentStop dev-* | File ownership post-hoc | **observability** (log violations) | `sdd_hooks/audit_file_ownership.py` | n/a |
| Stop | Smoke framework | **observability** | `sdd_admin/framework_smoke.py` | n/a |

## 5. Chemin nominal effectif

Sur un `/sdd-full {n}` **par défaut** (sans flags, Project Config défauts),
les gates réellement bloquantes sont **6** — pas 12 :

```
readiness (3.5) → staleness plans (6.0.bis, si plans) → API Gate (6.b)
→ spec Stage A (6.4.A) → quality batch (6.4.B) → review consolidé (4.8)
```

+ les caps continus (coût run, budget agent, combo SLA, acceptance post-qa).
Le reste : 4 gates manuelles opt-in, 1 defense-in-depth court-circuitée,
2 observability, QA 4.5 skippée (`QAMode: manual` défaut).

**Paires assumées (pas des doublons)** :
- 4.7 lit le rapport produit par 6.4.A (lecteur/producteur — autorité unique,
  cf. `feat-validate.md §4.5.3`) ;
- 4.8 agrège la DB sans re-spawner les reviewers de 6.4.B (consolidation,
  pas re-run) ;
- 1.bis / 3.6.quart : primaire + filet sentinelle.

## 6. Pointeurs

- Two-stage auditors : `@.sdd/rules/auditor-orchestration.md`
- Ownership des findings : `@.sdd/rules/auditor-coordination.md`
- API Gate : `@.sdd/rules/build-and-loop.md` Partie A
- Acceptance Gate : `@.sdd/rules/quality.md §C`
- Classes d'erreur des gates : `@.sdd/rules/error-classification.md §1.2, §1.7`
- Anti-rot : `tests/test_gates_map.py` (existence des enforcers cités ici)
