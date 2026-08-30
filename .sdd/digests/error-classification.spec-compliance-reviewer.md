# Error Classification — digest for `spec-compliance-reviewer`
> **GENERATED — do not edit.** Slice of `@.claude/rules/error-classification.md` for the `spec-compliance-reviewer` agent (audit 2026-06-12, block 5). Regenerate via `python .sdd/python/sdd_admin/sync_error_class_digests.py`.
>
> Contains the §0 quick-ref (full 16-family map) + this agent's families + the universal format/loop sections. For a class OUTSIDE this slice, §0 names its family — Read the full file on-demand (rule `build-and-loop.md §8`).
## 0. Quick reference — 16 familles (193 classes)

| # | Famille | Classes | Émetteur principal | Comportement build_loop |
|---|---|---:|---|---|
| §1.1 | **Runtime** (`[NETWORK]`/`[AUTH]`/`[PERMISSION]`/`[NOT_FOUND]`/`[TIMEOUT]`/`[DISK]`/`[ENV_*]`/`[INFRA_BLOCKED]`) | 9 | tous | STOP |
| §1.2 | **Pipeline** (`[STACK_MALFORMED]`/`[FEAT_*]`/`[PLAN_*]`/`[READINESS_*]`/`[INVALID_*]`/`[POC_*]`/`[PO_HASH_*]`/...) | 27 | po, arch, validate_plan.py | STOP |
| §1.3 | **Contrat ownership** (`[PRESERVES_VIOLATED]`/`[ADDS_VIOLATED]`/`[LAYER_VIOLATION]`/`[FILE_*]`/`[US_*]`/`[DB_STRUCTURE_CHANGE_FORBIDDEN]`) | 14 | dev-*, arch, set_us_status.py | STOP |
| §1.4 | **Build** (`[BUILD_*]`/`[DEP_MISSING]`/`[CIRCULAR_DEP]`) | 5 | dev-* | **ITÈRE** sur `[BUILD_CORRECTIBLE]` uniquement |
| §1.5 | **Anti-derive** (`[DERIVE_VIOLATION]`/`[STACK_LIBRARY_*]`/`[REFACTOR_HORS_SCOPE]`/...) | 7 | dev-* | STOP |
| §1.6 | **UI fidelity** (`[UI_FIDELITY_GAP]`/`[UI_TOKEN_VIOLATION]`/`[FRONTEND_BACKEND_CONTRACT_GAP]`) | 3 | dev-frontend | STOP/retry |
| §1.7 | **QA** (`[QA_TEST_FAILED]`/`[QA_COVERAGE_GAP]`/`[QA_OWNERSHIP_*]`/`[ACCEPTANCE_GATE_FAILED]`/`[ACCEPTANCE_REPORT_MISSING]`/...) | 11 | qa | STOP (RED bloquant) |
| §1.8 | **Parallélisme** (`[LIBNAME_LOCK_HELD]`/`[LOCK_HELD]`/`[LIBNAME_SIGNATURE_CONFLICT]`) | 3 | dev-* | STOP |
| §1.9 | **A11Y** (`[A11Y_*]`) — héritage, réactivé via `ingest_axe.py` | 11 | CI ingest (Lighthouse/axe) | report only |
| §1.10 | **Code Review** (`[REVIEW_*]`) — `code-reviewer` agent | 12 | code-reviewer | report only (verdict 🟢/🟡/🔴) |
| §1.11 | **Security** (`[SEC_*]`) — OWASP Top 10 2021 | 23 | security-reviewer | report only + 8 hard-blocking |
| §1.12 | **Perf** (`[PERF_*]`) — héritage, réactivé via `ingest_lighthouse.py` | 16 | CI ingest | report only |
| §1.13 | **Spec Compliance** (`[SPEC_*]`) — AC-by-AC verification | 9 | spec-compliance-reviewer | report only |
| §1.14 | **Tooling/Governance** (`[SCAN_*]`/`[DISCOVER_*]`/`[CHECKPOINT_*]`/`[CONFIG_*]`/`[PROFILE_*]`/`[DRIFT_*]`/`[ARCH_*]`/`[REVIEW_*]`/`[AUDITOR_RUNTIME_ERROR]`/`[STACK_COMBO_*]`/`[FRAMEWORK_PROTECTED]`/`[ENV_BYPASS_BLOCKED]`/`[PRICING_UNKNOWN]`/`[SECRET_PROVIDER_LEAK_RISK]`/`[PACK_UNUSABLE]`/hooks préflight) | 36 | scripts mono-shot + hooks | mostly info, qq. bloquantes |
| §1.15 | **Adversarial** (`[ADV_*]`) — opt-out (actif par défaut, `--no-adversarial` pour skip) | 6 | adversarial-reviewer | informational |
| §1.16 | **Inconnue** (`[UNKNOWN]`) | 1 | fallback | report only |

**Verdict consolidé** (§1.10-1.13) dépend du seuil `{Kind}FailOn` du
Project Config (`info|minor|moderate|serious|critical`). Voir §3.1 pour
le tableau d'actions par famille.

---

## 1. Familles pertinentes
### 1.1 Runtime (env, infra, dépendances)

| Préfixe | Usage | Phase |
|---|---|---|
| `[NETWORK]` | Timeout, firewall, VPN, service unreachable | DB scan, smoke, package fetch |
| `[AUTH]` | Login failed, expired token, invalid credentials | DB scan, gh, npm publish |
| `[PERMISSION]` | Droits insuffisants, FS read-only, sudo required | DB scan, FS write, init |
| `[NOT_FOUND]` | Database / file / package / endpoint absent | Tous |
| `[TIMEOUT]` | Smoke timeout, build_loop timeout, command timeout | Smoke, build, init |
| `[DISK]` | No space left, disk full, FS error | File write |
| `[ENV_MISSING]` | Env var requise absente | DB env vars, secrets |
| `[ENV_PROPAGATION_FAILED]` | Env vars shell parent invisibles dans sub-agent Bash | arch Phase B via tool `Agent` |
| `[INFRA_BLOCKED]` | Échec d'infrastructure générique (test runner absent, env de test cassé, disk, sentinel illisible) — distinct d'une régression code : « je n'ai pas pu exécuter », pas « le code est cassé ». Émis transversalement (`complexity_router.py`, `protect_framework.py`, `validate_acceptance.py`, `resolve_us_hash_sentinel.py`, `/sdd-bootstrap`). | tous (mono-shot) |

> **Post-mortem `[ENV_PROPAGATION_FAILED]` (2026-05-11)** : sub-agent
> Bash peut ne pas hériter des env vars du shell parent. Stratégies de
> récupération (préférence décroissante) :
> 1. `.env` projet + lib dotenv natif (`DotNetEnv`/`spring-dotenv`/
>    `python-dotenv`) — découple du shell parent (PRÉFÉRÉ)
> 2. Export explicite par sous-commande (`env DB_HOST=$DB_HOST cmd`)
> 3. Échec total → ERROR, jamais skip silencieux de Phase B (load-bearing
>    pour cohérence entities ↔ DB).
### 1.13 Spec Compliance (AC-by-AC verification, depuis v6.5.2)

Émis par l'agent `spec-compliance-reviewer` (Sonnet 4.6, v6.5.2). Vérifie
que chaque AC de chaque US est implémentée dans le code matérialisé,
indépendamment du rapport `dev-*` (pattern « Do not trust the report »
hérité de superpowers v5.1). Verdict 🟢/🟡/🔴 selon seuil
`SpecComplianceFailOn`. Aucune classe hard-blocking par défaut — c'est
l'addition cumulée d'ACs non vérifiées qui fait basculer le verdict.

| Préfixe | Sévérité | Phase |
|---|---|---|
| `[SPEC_AC_VERIFIED]` | info (✅) | spec-compliance §6.3 |
| `[SPEC_AC_NOT_VERIFIED]` | **critical** si AC testable_strict, **serious** si testable_soft, **moderate** si ui_only | spec-compliance §6.3 |
| `[SPEC_AC_PARTIAL]` | serious | spec-compliance §6.3 |
| `[SPEC_AC_AMBIGUOUS]` | minor (info, AC mal formulée) | spec-compliance §6.1 |
| `[SPEC_AC_UI_PRESENT]` | minor (info, présence cosmétique) | spec-compliance §6.2 |
| `[SPEC_NO_TARGETS]` | (bloquant runtime) | spec-compliance §5.3 |
| `[SPEC_COMPLIANCE_REQUIRED]` | **critical** (bloquant) | feat-validate STEP 4.5.3 (v7.0.0 — code matérialisé sans rapport spec-compliance.json) |
| `[SPEC_COMPLIANCE_RED]` | **critical** (bloquant) | feat-validate STEP 4.5.4 (v7.0.0 — verdict spec-compliance RED) |
| `[SPEC_COMPLIANCE_PARSE_ERROR]` | **critical** (bloquant) | feat-validate STEP 4.5.4 (spec-compliance.json corrompu/illisible) |

**Biais explicite « bias toward not-verified »** : l'agent émet
`[SPEC_AC_NOT_VERIFIED]` dès qu'il hésite entre verified et not-verified.
Faux positifs tolérés, faux négatifs interdits. Cf. agent §6.4.

**Coordination avec autres auditeurs** :
- Pas de duplication avec `[PLAN_AC_COVERAGE_GAP]` (§1.2) qui vérifie au
  niveau **plan** ; spec-compliance vérifie au niveau **code matérialisé**
- Pas de duplication avec `code-reviewer` (qui ignore les ACs et focus sur la qualité technique)
- Pas de duplication avec `[UI_FIDELITY_GAP]` (§1.6) qui mesure la fidélité pixel HTML→code

**Anti-duplication avec dev-* report** : par design, l'agent **ne lit pas**
les rapports `dev-*` ni les résumés conversation — relit le code
indépendamment.

---
### 1.16 Inconnue

| Préfixe | Usage |
|---|---|
| `[UNKNOWN]` | Erreur non classifiable (stderr brut, exception non gérée) |

---
## 2. Format obligatoire

**Noyau universel déplacé** (audit tokens 2026-08-30) : le format canonique —
chat 1L (`🔴 [AGENT/FAIL] … [CLASS] …`) et rapport 3L disque
(`ERROR / CAUSE / FIX`) avec exemple `[BUILD_CORRECTIBLE]` — est porté par
**`output-protocol.md §7`** (§7.2 chat, §7.3 disque + exemple, §7.5 noyau),
rule inconditionnelle auto-injectée dans tout contexte. Rappel du squelette
rapport (persisté en base `console.db` ou stderr ; ex-`workspace/qa/...`,
`.sys/.validation/...`) :
```
ERROR: {feat/us/task or pipeline-step} failed
CAUSE: [{CLASS}] {détail 1L}
FIX: {action 1L}
```
`[BUILD_CORRECTIBLE]` itère, `[BUILD_BLOCKING]` fail-fast — comportements §1.4,
décision mécanique §3.

---
## 3. Comportement `build_loop` selon classe

Une seule classe déclenche une itération `build_loop` :

| Itère ? | Classe(s) | Action |
|:---:|---|---|
| **OUI** (max `BuildLoopMaxIter`) | `[BUILD_CORRECTIBLE]` | Re-dispatch agent avec stderr |
| NON | tout le reste | STOP, ERROR au Tech Lead — voir tableau §3.1 |
## 5. Règle mentale

**"Pas de bloc ERROR sans préfixe `[CLASS]`. Si rien ne matche → `[UNKNOWN]`."**

Reprise verbatim dans `output-protocol.md §7.5` (canal universel — auto-injecté
partout). Discipline qui permet à `build_loop` de décider mécaniquement, aux
scripts de classer sans LLM, au dashboard de visualiser par cause-racine.
