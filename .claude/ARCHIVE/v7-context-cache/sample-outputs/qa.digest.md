# QA Digest — SDD_Pro v6.10.5 (projet CMS Sprint)

> **Compiled digest** : politiques QA + seuils + classes d'erreur + gating.
> Stable cross-FEAT — cacheable Anthropic prompt cache.
> Régénération recommandée à chaque modification `## Project Config` (CoverageMin/FailOn).
> Généré : 2026-05-19.

---

## 1. Modes QA actifs (Project Config effectif)

| Clé | Valeur projet | Défaut framework |
|---|---|---|
| `QAMode` | `full` | `manual` |
| `CoverageMin` | `80` (obligatoire, sans défaut) | `80` (base) |
| `BuildLoopMaxIter` | (héritée base) `3` | `3` |
| `GatedWorkflow` | (héritée base) `true` | `true` |
| `ApiGateRequired` | (héritée base) `true` | `true` |
| `ApiGateMinPerEndpoint` | (héritée base) `2` | `2` |

## 2. Modes auditors actifs

| Auditor | Mode | FailOn | Hard-blocking ? |
|---|---|---|---|
| `accessibility-auditor` | `full` | `serious` | Non (rapport) |
| `code-reviewer` | `manual` | `critical` | Oui : `[REVIEW_SECRETS_HARDCODED]`, `[FRONTEND_BACKEND_CONTRACT_GAP]` |
| `security-reviewer` | `manual` (mode `threat-model` + `scan`) | `critical` | Oui sur 8 classes (cf. §4) |
| `performance-auditor` | `full` | `serious` | Oui : `[PERF_AC_VIOLATION]` |
| `spec-compliance-reviewer` | `manual` | `serious` | Non (cumul) |
| `arch-reviewer` | `manual` | `serious` | Non (rapport) |

**Override projet** : `SecurityScanEnabled: false` dans `stack.md` → mode `scan` désactivé même si SecurityMode=full.

## 3. Pipeline QA (gated workflow backend-first)

```
arch + DB → dev-backend ALL US → ⚙ QA API Gate (in-memory) → dev-frontend ALL US
                                            │
                                            └─ 🔴 RED → STOP, humain corrige
                                            └─ 🟢 GREEN → continue front
                                            └─ 🟡 YELLOW → continue + WARN
```

Tests API Gate (in-memory, jamais DB réelle) :
- 1 happy + 1 négatif min par endpoint (`ApiGateMinPerEndpoint=2`)
- happy : GET 200, POST 201+Location, PUT 200, DELETE 204→GET 404
- négatif : GET id inexistant 404, body invalide 400 ProblemDetails, sans Bearer 401, scope manquant 403

Critère : `gate_passed = (failed == 0) AND (total >= MIN × N_endpoints)`.

## 4. Classes d'erreur QA & sévérités

### `[QA_*]` (déterministe scripts)

| Code | Émis par | Sévérité | Action |
|---|---|---|---|
| `[QA_TEST_FAILED]` | qa STEP 5 (Sonnet) | RED bloquant | re-dev-* ou ajuster tests |
| `[QA_COVERAGE_GAP]` | parse_coverage.py | RED bloquant (v6.1 hardening) | ajouter tests OU baisser CoverageMin |
| `[QA_FRAMEWORK_MISSING]` | qa STEP 2 | RED | installer test runner CLI |
| `[QA_INIT_FAILED]` | qa STEP 2.5 | RED | debug bootstrap test project |
| `[QA_TEST_INVALID]` | qa STEP 3/4 | RED | retirer sleep/DB réelle/état partagé |
| `[QA_OUTPUT_INVALID]` | qa STEP 7 (self-verify) | RED | re-run qa |
| `[QA_PRECONDITION_FAILED]` | qa STEP 0.4 | RED | s'assurer FEAT/US/code production existent |
| `[QA_OWNERSHIP_VIOLATION]` | dev-* ou qa | RED | dev-* n'écrit jamais test, qa n'écrit jamais prod |
| `[API_GATE_RED]` | dev-run phase 4c | RED bloquant | gate RED stoppe frontend |

**Priorité** : `[QA_TEST_FAILED] > [QA_COVERAGE_GAP]` (les deux RED, tests d'abord).

### `[A11Y_*]` (10 codes, accessibility-auditor Haiku 4.5)

Verdict 🟢/🟡/🔴 selon `A11yFailOn=serious` (défaut) : RED dès 1 issue ≥ serious. Codes : `[A11Y_MISSING_ALT]` (critical), `[A11Y_INPUT_NO_LABEL]` (critical), `[A11Y_BUTTON_NO_LABEL]` (serious), `[A11Y_TABINDEX_POSITIVE]` (serious), `[A11Y_LANG_MISSING]` (serious), `[A11Y_ROLE_INCOMPLETE]` (serious), `[A11Y_HEADING_SKIP]` (moderate), `[A11Y_FORM_NO_SUBMIT]` (moderate), `[A11Y_TARGET_TOO_SMALL]` (moderate), `[A11Y_STATUS_NO_LIVE]` (moderate).

**Source** : `.claude/templates/wcag-checklist.json` (externalisé v6.10.5, prep v7).

### `[SEC_*]` (21 codes, security-reviewer Sonnet 4.6)

8 hard-blocking quelque soit `SecurityFailOn` : `[SEC_SECRET_HARDCODED]`, `[SEC_SQL_INJECTION]`, `[SEC_COMMAND_INJECTION]`, `[SEC_BROKEN_AUTHZ]`, `[SEC_BROKEN_AUTHN]`, `[SEC_DESERIALIZATION_UNSAFE]`, `[SEC_JWT_MISCONFIG]`, `[SEC_SSRF_RISK]`. Mappés OWASP Top 10 2021 + CWE.

Mode `threat-model` (pré-dev) émet uniquement items informationnels (STRIDE).

### `[REVIEW_*]` (11 codes, code-reviewer Sonnet 4.6)

Sévérités : critical/serious/moderate/minor. Hard-blocking systématique : `[REVIEW_SECRETS_HARDCODED]`, `[FRONTEND_BACKEND_CONTRACT_GAP]`.

Anti-doublons : `code-reviewer` ne refait pas les checks `quality_scan.py` (TODO/magic numbers/console.log/long methods/naming/hex).

### `[PERF_*]` (16 codes, performance-auditor Sonnet 4.6)

Aucun hard-blocking par défaut sauf `[PERF_AC_VIOLATION]` (quand AC d'US mentionne explicitement métrique perf). Seuils défauts WCV : LCP > 2500ms, CLS > 0.1, FID > 100ms, INP > 200ms.

### `[SPEC_*]` (6 codes, spec-compliance-reviewer Sonnet 4.6)

Biais explicite "bias toward not-verified" : émet `[SPEC_AC_NOT_VERIFIED]` dès qu'hésitation. Faux positifs tolérés, faux négatifs interdits.

### `[ARCH_*]` (6 codes, arch-reviewer Sonnet 4.6)

`[ARCH_LAYER_BYPASS]`, `[ARCH_PATTERN_VIOLATION]`, `[ARCH_NAMING_INVALID]`, `[ARCH_ADR_DRIFT]`, `[ARCH_CONSTITUTION_GAP]`, `[ARCH_NO_TARGETS]`.

## 5. Pipeline scripts déterministes (0 token LLM)

| Script | Output | Persistance |
|---|---|---|
| `quality_scan.py` | TODO/console.log/magic numbers/long methods/hex/naming | table `qa_quality` |
| `parse_coverage.py` | Normalisation cross-stack vers schéma §2 qa-coverage.md | table `qa_coverage` |
| `ingest_agent_report.py` | Parse `*.json` auditors → DB | tables `qa_*` selon type |
| `validate_plan.py --strict` | Strict-ready plan v2 check (0/1/2 exit) | console seul |

## 6. Idempotence outputs QA

- `workspace/output/qa/feat-{n}/{report,api-tests,a11y-report,perf-report,review,...}.{md,json}` overwritten chaque run.
- Pas d'historique disque (historisation = service externe, hors scope SDD_Pro).
- Persistance long-terme : `console.db` (24 tables, 36 index).

---

## 7. Stratégie auditors v7 (planifiée, ADR `v7-prompt-cache-build-loop-static-reviewer`)

- **Conditionnel** :
  - `a11y` → seulement si UI modifiée (frontend touché par dev-frontend)
  - `perf` → seulement si frontend ou bundle impacté
  - `security` → seulement si auth/rôles/upload/secrets touchés
  - `arch-reviewer` → seulement après modification architecture/DB
- **QA de base** systématique (quality_scan + parse_coverage + API Gate) ; scans lourds optionnels.
- **Static reviewer fusion** : `code-reviewer + arch-reviewer → static-reviewer` (−700 L, ADR Fusion 1).

---

*Digest régénérable : à chaque modification `## Project Config` ou MAJ `error-classification.md`, relancer un futur `compile_qa_digest.py` (v7) qui agrège modes + seuils + classes.*
