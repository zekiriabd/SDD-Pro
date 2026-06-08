# Règle — Auditor Orchestration (Two-stage gate, v7.0.1)

> **v7.0.1 audit REFACTOR-4 hoist 2026-06-08** : substance opérationnelle extraite
> de `commands/dev-run.md §STEP 6.4` (~190 lignes de scripts inline) pour
> permettre une lecture isolée par les agents auditors et économiser ~8-10 KB
> par invocation `/dev-run`. `dev-run.md` conserve uniquement le pointer + le
> rationale séquentiel (pourquoi 6.4 après 6.c, où on est dans la pipeline).
>
> **Périmètre** : règle lue par `dev-run.md`/`sdd-full.md` au STEP 6.4 quand
> `AuditorBatchMode != "off"`. Pas lue par les agents auditors eux-mêmes
> (ils ont leur propre prompt agent).

## TOC

- §1 — Principe two-stage (Stage A spec-compliance gate, Stage B quality batch)
- §2 — STEP 6.4.0 Lecture phase plan (commune A + B)
- §3 — STEP 6.4.A Stage 1 : spec-compliance gate
- §4 — STEP 6.4.B Stage 2 : quality batch parallèle (3 auditors max)
- §5 — Verdict consolidé + state tracking
- §6 — Anti-derive
- §7 — Mode legacy-parallel (fallback v6.x)

---

## 1. Principe two-stage (v7.0.0+, emprunt superpowers v5.1)

Avant v7.0.0 : les 4 auditors (code-reviewer, security-reviewer,
spec-compliance-reviewer, arch-reviewer) tournaient **en parallèle dans un
seul batch**. Problème : si la spec n'est pas respectée, le code va être
réécrit, et les findings code/security/arch deviennent obsolètes.

Après v7.0.0 : **spec-compliance tourne SEUL en Stage A** (gate), puis si
🟢/🟡 les 3 autres auditors tournent en parallèle en Stage B. Économie
typique sur spec RED : **3 invocations Sonnet 4.6** (~9-15 KB context chacune).

```
Stage A : spec-compliance-reviewer (SEUL — gate strict)
          │
          ├─ 🟢/🟡 → Stage B
          └─ 🔴   → STOP (économie 3 invocations Sonnet)

Stage B (parallèle, 3 max) :
          ├─ code-reviewer
          ├─ security-reviewer
          └─ arch-reviewer (si ArchReviewMode=full)
```

---

## 2. STEP 6.4.0 — Lecture du phase plan (commune Stage A + Stage B)

```python
# RE-READ phase plan depuis disque (shell var $PHASE_PLAN STEP 5.5 ne survit
# pas aux tool-call boundaries — chaque Bash = subshell indépendant).
import json, pathlib
plan_path = pathlib.Path(f"workspace/output/.sys/.state/phase-plan-{n}.json")
if not plan_path.is_file():
    STOP + ERROR("[PHASE_PLAN_INIT_FAILED] state file missing",
                 f"FIX: re-run STEP 5.5 OR phase_planner.py --feat {n}")
phase_plan = json.loads(plan_path.read_text(encoding="utf-8"))
phases = phase_plan.get("phases", {})

# Hard-fail si phase_planner.py JSON malformé (sinon reviewers skip silencieux).
# RUPT-4 : phases est dict Python → mapping `phases["X"]`, PAS attribute access.
if not phases or not all(k in phases for k in ("code_review", "security_scan", "spec_compliance")):
    STOP + ERROR("[PHASE_PLAN_INIT_FAILED] phases dict unusable",
                 f"FIX: rerun phase_planner.py --feat {n} et inspecter output")

arch_review_mode = read_layered_config(keys=("ArchReviewMode",)).get("ArchReviewMode", "manual")
auditor_batch_mode = read_layered_config(keys=("AuditorBatchMode",)).get("AuditorBatchMode", "two-stage")
```

Si **toutes** les phases auditor sont disabled ET `arch_review_mode != "full"`
→ skip intégralement STEP 6.4, passer à STEP 6.5.

---

## 3. STEP 6.4.A — Stage 1 : spec-compliance gate (SEUL)

**Skip Stage A** si :
- `phases["spec_compliance"].enabled == false` (phase_planner désactive — FEAT sans AC testable) → continuer directement Stage B
- `auditor_batch_mode == "legacy-parallel"` → fallback v6.x (cf. §7)

Sinon, spawn UN SEUL agent :

```
Agent: spec-compliance-reviewer
  prompt: "Audit FEAT {n} — verification AC-by-AC (cf. agents/spec-compliance-reviewer.md). Mode gate two-stage."
```

Lire son verdict :

| Verdict path | Champ |
|---|---|
| `workspace/output/.sys/.validation/{n}-spec-compliance.json` | `summary.verdict` |

Fichier absent → `🔴 RED [AUDITOR_RUNTIME_ERROR]` (gate stricte, jamais
de fallback silencieux).

### 3.1 Décision gate

| Verdict spec | Action |
|---|---|
| 🟢 GREEN | → 6.4.B (quality batch) |
| 🟡 WARN | → 6.4.B + propager warning au verdict consolidé final |
| 🔴 RED | STOP — bloc §3.2 (économie de 3 invocations Sonnet) |

### 3.2 Format STOP sur spec RED

```
🔴 /dev-run {n} — spec-compliance gate RED ({N_red} ACs non vérifiées)

Verdict spec-compliance : 🔴 RED ({V}/{T} ACs verified, {NV} not-verified)
Rapport : workspace/output/.sys/.validation/{n}-spec-compliance.md

⊘ code-reviewer / security-reviewer / arch-reviewer : skipped (gate failed)
   Rationale : reviewer le code et son architecture serait gaspilleur tant
   que le code ne respecte pas la spec — il va être réécrit. Économie :
   3 invocations Sonnet 4.6.

Débloquer :
  1. Lire {n}-spec-compliance.md §Findings (ACs not_verified + suggestions)
  2. Corriger (/dev-{backend|frontend} {n}-{m} ou édit manuel)
  3. Relancer /dev-run {n} (idempotent : skip 6.a/6.b/6.c si stables,
     re-run 6.4.A puis 6.4.B)

Bypass : `--legacy-auditor-parallel` (force legacy-parallel 4-batch, audit-loggué)
ou baisser SpecComplianceFailOn en Project Config.
```

---

## 4. STEP 6.4.B — Stage 2 : quality batch parallèle (3 auditors max)

**Précondition** : Stage A 🟢/🟡 OU skip Stage A (phase désactivée OU
mode legacy-parallel).

### 4.1 Construction du batch

```python
BATCH = []
if phases["code_review"].get("enabled"):       BATCH.append(Agent("code-reviewer", args="{n}"))
if phases["security_scan"].get("enabled"):     BATCH.append(Agent("security-reviewer", args="{n}"))
if arch_review_mode == "full":                 BATCH.append(Agent("arch-reviewer", args="{n}"))

# Mode legacy-parallel : re-injecter spec-compliance si Stage A a été skippée
if auditor_batch_mode == "legacy-parallel" and phases["spec_compliance"].get("enabled"):
    BATCH.append(Agent("spec-compliance-reviewer", args="{n}"))
```

Si `BATCH == []` → skip STEP 6.4.B, passer à STEP 6.5.

Sinon dispatcher **en parallèle dans un seul message**. Paths d'écriture
disjoints (cf. `ownership.md §1`).

> `accessibility-auditor` retiré v7.0.0 (`governance-major-auditors-trim`,
> remplacé par axe-core CI). Entrée legacy ignorée silencieusement.

### 4.2 Lecture des verdicts

| Agent | Verdict path | Champ |
|---|---|---|
| code-reviewer | `{n}-code-review.json` | `summary.verdict` |
| security-reviewer | `{n}-security-scan.json` | `summary.verdict` |
| arch-reviewer | `{n}-arch-review.json` | `summary.verdict` |

Tous sous `workspace/output/.sys/.validation/`. Fichier absent (agent STOP
runtime) → `🔴 RED [AUDITOR_RUNTIME_ERROR]`. **Exception arch-reviewer** :
échec runtime → WARN seulement (jamais hard-blocking par design,
`ArchReviewFailOn: serious` défaut).

### 4.3 Verdict consolidé (spec + batch)

`verdict_overall = max_severity({spec_verdict} ∪ {non-skipped batch})`
(🔴 > 🟡 > 🟢).

| Verdict | Action |
|---|---|
| 🟢 GREEN | → STEP 6.5 |
| 🟡 WARN | → STEP 6.5 + log WARN STEP 7 récap |
| 🔴 RED | STOP — bloc §4.4, pas de STEP 6.5 |

### 4.4 Format STOP sur RED

```
🔴 /dev-run {n} — quality batch RED ({N_red} agents en échec)

Verdicts :
  - spec-compliance  : {🟢|🟡} (gate Stage A passé)
  - code-reviewer    : {🟢|🟡|🔴} (blocking: {class si applicable})
  - security-scan    : {🟢|🟡|🔴}
  - arch-reviewer    : {🟢|🟡|⚪ skipped}

Rapports : workspace/output/.sys/.validation/{n}-*.md

Débloquer :
  1. Lire rapports 🔴 (issues critical/serious + suggestions FIX)
  2. Corriger (/dev-{backend|frontend} {n}-{m} ou édit manuel)
  3. Relancer /dev-run {n} (idempotent : skip 6.a/6.b/6.c si stables,
     re-run 6.4.A puis 6.4.B)

Bypass : baisser CodeReviewFailOn / SecurityFailOn en Project Config.
Hard-blocking (secrets, SQL injection, contract drift) non-overridable.
```

### 4.5 Émission succès

```
✓ spec-compliance  : {🟢|🟡} — {V}/{T} ACs verified         (Stage A — gate)
✓ code-reviewer    : {🟢|🟡} — {C}/{S}/{M}/{m} issues        (Stage B)
✓ security-scan    : {🟢|🟡} — {C}/{S}/{M}/{m} issues        (Stage B)
✓ arch-reviewer    : {🟢|🟡} — {P} pattern violations        (Stage B, si ArchReviewMode=full)
FEAT {n} — auditor two-stage {🟢|🟡} (→ STEP 6.5 INDEX ADRs)
```

Agents skippés : `⊘ {agent} : skipped ({reason})`.

---

## 5. State tracking (both stages)

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase auditor_batch --status {pass|warn|fail} \
  --payload-json '{"mode":"two-stage","stage_a":{"spec_compliance":"{v}"},"stage_b":{"code_review":"{v}","security_scan":"{v}","arch_review":"{v|skipped}"}}'
```

> Mode legacy-parallel : `--payload-json '{"mode":"legacy-parallel",...}'`
> (4 agents dans `stage_b`, `stage_a` vide).

---

## 6. Anti-derive

- Agents **idempotents** (relancer écrase rapports)
- **Pas de fallback** sur 🔴 : Tech Lead corrige
- Auditors n'ont **PAS** de `build_loop` (`[REVIEW_*]`/`[SEC_*]`/`[SPEC_*]` "Itère: NON")
- `phase_planner.py` = 0 token LLM
- Stage A gate strict : pas de bypass programmatique (le code DOIT respecter
  la spec avant de mériter une review qualité)
- spec-compliance lit le code indépendamment AC-par-AC (pattern superpowers v5.1)
- Mode `legacy-parallel` réservé compat v6.x — déconseillé (perte économie tokens)

---

## 7. Mode legacy-parallel (fallback v6.x)

Bypass via flag CLI `--legacy-auditor-parallel` ou Project Config
`AuditorBatchMode: legacy-parallel`. Audit-loggué dans
`workspace/output/.sys/.audit/legacy-auditor-parallel.log`.

En mode legacy-parallel :
- Stage A skip (pas de gate spec-compliance pré-batch)
- Stage B inclut spec-compliance dans le batch parallèle (4 agents max)
- Pas d'économie tokens si spec RED (les 3 autres tournent quand même)

Distinct de `--unsequenced` (qui adresse la gate API back/front, pas auditor).

---

## 8. Enforcement

- `commands/dev-run.md §STEP 6.4` : Read par référence au STEP 6.4.
  Substance opérationnelle ICI, pas dans dev-run.md (cf. hoist v7.0.1
  audit REFACTOR-4 2026-06-08).
- Toute évolution du two-stage gate doit être faite ici d'abord, puis
  vérifiée dans `dev-run.md` (qui ne contient plus que le rationale
  séquentiel + le pointer).
