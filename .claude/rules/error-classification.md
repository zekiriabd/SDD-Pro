# Règle — Error Classification (vocabulaire d'erreur unifié cross-agent)

## Principe

Tous les agents et scripts SDD_Pro préfixent leurs blocs ERROR avec un
**code `[CLASS]`** dans le `CAUSE:`. Permet à `build_loop`, hooks et
dashboards de classer sans interprétation textuelle.

Source canonique unique — concentre les codes auparavant dispersés
dans `stack-completeness.md`, `file-ownership.md`, `qa-coverage.md`
et inlinés dans les agents (po, dev-*, qa).

---

## 1. Taxonomie des classes d'erreur

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

> **Post-mortem `[ENV_PROPAGATION_FAILED]` (2026-05-11)** : sub-agent
> Bash peut ne pas hériter des env vars du shell parent. Stratégies de
> récupération (préférence décroissante) :
> 1. `.env` projet + lib dotenv natif (`DotNetEnv`/`spring-dotenv`/
>    `python-dotenv`) — découple du shell parent (PRÉFÉRÉ)
> 2. Export explicite par sous-commande (`env DB_HOST=$DB_HOST cmd`)
> 3. Échec total → ERROR, jamais skip silencieux de Phase B (load-bearing
>    pour cohérence entities ↔ DB).

### 1.2 Pipeline (logique framework)

| Préfixe | Usage | Phase |
|---|---|---|
| `[STACK_MALFORMED]` | `stack.md` invalide, section manquante | arch STEP 1 |
| `[SCHEMA_MISMATCH]` | Table/colonne absente de `schema.json` | dev-backend STEP 4.5 |
| `[FEAT_REJECTED]` | FEAT ne respecte pas le format | po STEP 2 |
| `[FEAT_NOT_FOUND]` | Aucun fichier `workspace/input/feats/{n}-*.md` matché | feat-validate, sdd-full STEP 1 |
| `[FEAT_AMBIGUOUS]` | Plusieurs fichiers `workspace/input/feats/{n}-*.md` matchent | feat-validate, sdd-full STEP 1 |
| `[GRANULARITY_VIOLATION]` | > 6 US, anti-pattern détecté | po STEP 5/7 |
| `[TRACEABILITY_GAP]` | SFD/AC/BR/FD non couvert par une US | po STEP 6 |
| `[READINESS_NO_GO]` | `/feat-validate` NO-GO sans `--force` | feat-validate |
| `[PLAN_NOT_FOUND]` | Plan attendu absent | validate_plan.py |
| `[PLAN_UNREADABLE]` | Plan présent mais I/O error | validate_plan.py |
| `[PLAN_NO_FRONTMATTER]` | Plan sans bloc YAML `---` ... `---` | validate_plan.py |
| `[PLAN_FRONTMATTER_INVALID]` | Champ frontmatter invalide (type, valeur) | validate_plan.py |
| `[PLAN_MISSING_REQUIRED_FIELD]` | Champ `us` ou `family` absent | validate_plan.py |
| `[PLAN_FILES_SECTION_MISSING]` | Section `## Files` absente ou vide | validate_plan.py |
| `[PLAN_FILE_ENTRY_INVALID]` | Entrée file sans path/operation/layer/covers_acs | validate_plan.py |
| `[PLAN_AUGMENT_CONTRACT_MISSING]` | operation=augment sans `preserves:`/`adds:` | validate_plan.py |
| `[PLAN_AC_COVERAGE_GAP]` | ACs de l'US absents de `## ACs Coverage Summary` | validate_plan.py (strict) |
| `[PLAN_STALE]` | us-hash mismatch — US modifiée post-plan | validate_plan.py (strict) → STOP, re-`/dev-plan` |
| `[PLAN_INVALID]` | Plan corrompu/illisible/inconsommable (alias générique des cas exit 2 ≠ PLAN_STALE) | validate_plan.py → STOP, re-`/dev-plan` |
| `[PLAN_NOT_STRICT_READY]` | Plan v1 ou manque `## Inline Digest` — strict path indisponible | validate_plan.py (strict) → fallback classic |
| `[PLAN_DIGEST_INSUFFICIENT]` | Info manquante dans `## Inline Digest` du plan (info nécessaire en runtime non capturée) | dev-*-strict STEP 2/5/6 → fallback dev-* (Opus) |
| `[INVALID_ARG]` | Argument CLI invalide (regex `^\d+-\d+(:plan)?$` ou `^\d+$` non matché) | dev-*, sdd-full, dev-run, dev-plan, feat-validate STEP 1 |
| `[INVALID_MODE]` | Mode d'exécution incompatible (`:plan` invoqué alors qu'un plan existe ; suffixe `:plan` sur agent strict ; etc.) | dev-shared.md §1.ter.3, dev-*-strict STEP 0 |
| `[PROJECT_NOT_INIT]` | Fichier projet absent (`.csproj`/`package.json`/`pyproject.toml`/`build.gradle.kts`/`angular.json`) — arch n'a pas tourné | preflight.py B4, dev-*-strict STEP 4 |
| `[PLAN_REVIEW_GATE_SKIPPED]` | Plan-then-review gate bypassé (WARN informationnel) | sdd-full STEP 3.6 |
| `[STACK_SCAFFOLDING_MISSING]` | Arch n'a pas scaffoldé les entities attendues (DB→entities cohérence cassée) | arch Phase B, dev-backend STEP 4.5 |

### 1.3 Contrat (preserves/adds, layers, ownership)

| Préfixe | Usage | Phase |
|---|---|---|
| `[PRESERVES_VIOLATED]` | Identifier `preserves:` retiré après augment | dev-* post-Edit |
| `[ADDS_VIOLATED]` | Identifier `adds:` non présent après écriture | dev-* post-Edit |
| `[LAYER_VIOLATION]` | Code dans couche interdite (ex. business in UI) | dev-* STEP build |
| `[FILE_OWNERSHIP]` | Path interdit par `file-ownership.md §1` | hook SubagentStop |
| `[FILE_OWNERSHIP_NESTED]` | Projet front imbriqué dans back (cf. §1.bis) | arch/dev-* STEP 1.bis |
| `[STATUS_FLIP_FAILED]` | `Status: Done` non persisté sur disque | dev-* post-write |
| `[US_STATUS_INVALID]` | Valeur de status hors 7 valides v6.8 (`Draft\|Ready\|InProgress\|Review\|Done\|Deferred\|Cancelled`) | `set_us_status.py` |
| `[US_STATUS_TRANSITION_INVALID]` | Transition rejetée par le graphe ou sortie d'état terminal sans `--force` | `set_us_status.py` |
| `[US_STATUS_PARSE_ERROR]` | Ligne `Status: {value}` absente/illisible du frontmatter US | `set_us_status.py` |
| `[US_NOT_FOUND]` | Aucun fichier `workspace/output/us/{n}-{m}-*.md` matché (ou ambigu) | `set_us_status.py`, `validate_us_deps.py` et futurs scripts US |
| `[US_DEPS_CYCLE]` | Cycle détecté dans le graphe `## Dependencies` (Tarjan SCC ≥ 2) — bloquant | `validate_us_deps.py` exit 3 |
| `[US_DEPS_MISSING]` | Référence `## Dependencies` vers une US inexistante dans le scope FEAT/repo — bloquant | `validate_us_deps.py` exit 4 |
| `[US_DEPS_ORPHAN]` | US sans dépendant (no incoming edge) — informational (peut être death-code) | `validate_us_deps.py` (exit 0) |
| `[BREAKING_CLEANUP_FAILED]` | `mark_breaking_resolved.py` exit 3 (erreur fichier CLAUDE.md) | dev-* STEP 8.5 / 11.5 |

### 1.4 Build (compile / lint / type) — pilote `build_loop`

| Préfixe | Usage | Comportement |
|---|---|---|
| `[BUILD_CORRECTIBLE]` | Import, typo, override, nullability, DI signature | **itère** (max `BuildLoopMaxIter`) |
| `[BUILD_BLOCKING]` | Erreur architecturale (layer, DI cycle, design break) | **fail-fast** |
| `[BUILD_LOOP_EXHAUSTED]` | Build échec après `BuildLoopMaxIter` itérations (boucle déjà épuisée) | **fail-fast** (terminal) |
| `[DEP_MISSING]` | Package non installé, intervention Tech Lead | fail-fast |
| `[CIRCULAR_DEP]` | Dépendance circulaire entre layers/projets | fail-fast |

**Critique** : `build_loop` NE DOIT PAS itérer sur `[BUILD_BLOCKING]`,
`[BUILD_LOOP_EXHAUSTED]`, `[DEP_MISSING]`, `[CIRCULAR_DEP]` — problèmes
structurels non résolus par retry. `[BUILD_LOOP_EXHAUSTED]` est l'état
terminal émis par dev-* quand `BuildLoopMaxIter` est atteint sans
convergence.

### 1.5 Anti-derive (scope expansion)

| Préfixe | Usage |
|---|---|
| `[DERIVE_VIOLATION]` | Feature non scopée par US/FEAT |
| `[REFACTOR_HORS_SCOPE]` | Rename/move/extract non demandé |
| `[OPTIMIZATION_PROACTIVE]` | HashSet/index/async non déclaré |
| `[UNDECLARED_DECISION]` | Pattern/lib/convention non déclaré dans stack |
| `[STACK_LIBRARY_MISSING]` | Lib hors §2.4 du stack actif |
| `[STACK_LIBRARY_VULNERABLE]` | Lib §2.4 active avec CVE ≥ moderate (vérifié post-install par arch) |
| `[STACK_RUNTIME_NOT_LTS]` | Runtime STS/prerelease pinné en `versions` (.NET 9, Node 23, Java 22, etc.) sans bypass ADR | arch post-install (CVE check), `validate_libs_catalog.py` |
| `[RUNTIME_STS_EXCEPTION]` | WARN-level — bypass STS tracé via ADR `runtime-sts-exception` + `RuntimeException:` Project Config | `validate_libs_catalog.py` |

### 1.6 UI (fidélité HTML mockup → code)

| Préfixe | Usage | Phase |
|---|---|---|
| `[UI_FIDELITY_GAP]` | Libellé/structure HTML absent du markup généré | dev-frontend STEP 11 |
| `[UI_TOKEN_VIOLATION]` | Hex hardcode au lieu de `var(--*)` | dev-frontend post-Edit |
| `[FRONTEND_BACKEND_CONTRACT_GAP]` | Route HTTP vise endpoint backend inexistant | dev-frontend STEP 5 |

### 1.7 QA (tests + coverage + API gate + quality)

| Préfixe | Usage | Phase |
|---|---|---|
| `[QA_TEST_FAILED]` | ≥ 1 test unitaire échoue → RED | qa STEP 5 |
| `[QA_COVERAGE_GAP]` | `coverage_lines_pct < CoverageMin` → RED (depuis v6.1) | qa STEP 6 |
| `[QA_FRAMEWORK_MISSING]` | Test runner CLI absent OU `## Active QA Specs` vide | qa STEP 2/5 |
| `[QA_INIT_FAILED]` | Bootstrap test project échoue | qa STEP 2.5 |
| `[QA_TEST_INVALID]` | Forbidden patterns (sleep, DB réelle, état partagé) | qa STEP 3/4 |
| `[QA_OUTPUT_INVALID]` | `coverage.json`/`quality.json` non-parseable | qa STEP 7 |
| `[QA_PRECONDITION_FAILED]` | FEAT/US/code production absents | qa STEP 0.4 |
| `[QA_OWNERSHIP_VIOLATION]` | dev-* écrit test OU qa écrit code prod | dev-*, qa |
| `[API_GATE_RED]` | API Gate (cf. `backend-first.md`) RED, frontend bloqué | dev-run phase 4c |

Priorité d'émission : `[QA_TEST_FAILED] > [QA_COVERAGE_GAP]` ;
`[API_GATE_RED] > tout autre QA_*`.

### 1.8 Parallélisme (file ownership / locks)

| Préfixe | Usage |
|---|---|
| `[LIBNAME_LOCK_HELD]` | Lock LibName détenu par autre agent (cf. `file-ownership.md §4`) |
| `[LIBNAME_SIGNATURE_CONFLICT]` | DTO/Model partagé, signatures divergentes |
| `[LOCK_HELD]` | Lock générique cross-language (sdd_lib/file_locks.py) — `workspace/console/.status.lock`, etc. Alias générique de `[LIBNAME_LOCK_HELD]` pour contextes non-LibName |

### 1.9 A11Y (accessibility WCAG 2.2 — depuis v6.3.0)

> **v7.0.0** : agent `accessibility-auditor` **retiré**
> (`governance-major-auditors-trim`). Les classes ci-dessous sont
> **conservées comme schéma de mapping** pour la sortie `axe-core` du CI
> du projet généré (ingest futur via `ingest_a11y_axe.py`). Aucune n'est
> émise par un agent SDD_Pro après v6.10.5.

Historique (v6.3.0-v6.10) : émis par `accessibility-auditor` (Haiku 4.5).
Chaque classe porte une **sévérité** ordinale `critical > serious > moderate > minor`
qui pilotait le verdict 🟢/🟡/🔴 contre le seuil `A11yFailOn` du Project Config.

| Préfixe | WCAG | Sévérité | Phase |
|---|---|---|---|
| `[A11Y_MISSING_ALT]` | 1.1.1 | critical | accessibility-auditor STEP 3 |
| `[A11Y_INPUT_NO_LABEL]` | 1.3.1 | critical | accessibility-auditor STEP 3 |
| `[A11Y_BUTTON_NO_LABEL]` | 2.4.6 | serious | accessibility-auditor STEP 3 |
| `[A11Y_TABINDEX_POSITIVE]` | 2.4.3 | serious | accessibility-auditor STEP 3 |
| `[A11Y_HEADING_SKIP]` | 1.3.1 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_LANG_MISSING]` | 3.1.1 | serious | accessibility-auditor STEP 3 |
| `[A11Y_FORM_NO_SUBMIT]` | 3.3.2 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_ROLE_INCOMPLETE]` | 4.1.2 | serious | accessibility-auditor STEP 3 |
| `[A11Y_TARGET_TOO_SMALL]` | 2.5.5 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_STATUS_NO_LIVE]` | 4.1.3 | moderate | accessibility-auditor STEP 3 |
| `[A11Y_SCAN_TOO_LARGE]` | — | (infra) | accessibility-auditor STEP 2 (> 500 fichiers, dépasse budget Haiku) |

**Verdict global** : `🔴 RED` si ∃ issue de sévérité `≥ A11yFailOn`,
sinon `🟡 WARN` si issues présentes (< seuil), sinon `🟢 GREEN`.
Substance opérationnelle : `agents/accessibility-auditor.md §4`.

### 1.10 Code Review (cross-fichier, depuis v6.3.1)

Émis par l'agent `code-reviewer` (Sonnet 4.6). Chaque classe porte une
**sévérité** ordinale `critical > serious > moderate > minor` qui pilote
le verdict 🟢/🟡/🔴 contre le seuil `CodeReviewFailOn` du Project Config.

| Préfixe | Catégorie | Sévérité | Phase |
|---|---|---|---|
| `[REVIEW_SECRETS_HARDCODED]` | sécurité | critical (hard-blocking) | code-reviewer STEP 5.5 |
| `[REVIEW_ANTI_PATTERN_N_PLUS_ONE]` | perf DB | serious | code-reviewer STEP 5.1 |
| `[REVIEW_ANTI_PATTERN_BLOCKING_ASYNC]` | concurrence | serious | code-reviewer STEP 5.1 |
| `[REVIEW_ANTI_PATTERN_SYNC_IO_IN_ASYNC]` | concurrence | serious | code-reviewer STEP 5.1 |
| `[REVIEW_ANTI_PATTERN_KEY_INDEX]` | React stability | moderate | code-reviewer STEP 5.1 |
| `[REVIEW_ANTI_PATTERN_USEEFFECT_NO_DEPS]` | React reactivity | serious | code-reviewer STEP 5.1 |
| `[REVIEW_MISSING_ERROR_HANDLING]` | robustesse | serious | code-reviewer STEP 5.4 |
| `[REVIEW_DUPLICATE_CODE]` | maintenabilité | moderate | code-reviewer STEP 5.4 |
| `[REVIEW_DEEP_NESTING]` | lisibilité | moderate | code-reviewer STEP 5.4 |
| `[REVIEW_CONFUSING_NAMING]` | lisibilité | minor | code-reviewer STEP 5.4 |
| `[REVIEW_ORPHAN_ENDPOINT]` | contract | minor (info) | code-reviewer STEP 5.3 |
| `[REVIEW_NO_TARGETS]` | infra | (bloquant) | code-reviewer STEP 4.3 |

**Classes réutilisées** (déjà définies §1.3 / §1.6) émises aussi par le
reviewer pour ne pas proliférer la taxonomie :
- `[LAYER_VIOLATION]` — DbContext/Repository hors couche autorisée
- `[FRONTEND_BACKEND_CONTRACT_GAP]` — front appelle endpoint backend manquant (hard-blocking par code-reviewer)

**Hard-blocking systématique** (override `CodeReviewFailOn`) : tout
`[REVIEW_SECRETS_HARDCODED]` ou `[FRONTEND_BACKEND_CONTRACT_GAP]` force
le verdict 🔴 RED quelque soit le seuil configuré. Substance opérationnelle :
`agents/code-reviewer.md §7.3`.

**Anti-duplication** : le reviewer **ne refait pas** les checks couverts
par `quality_scan.py` (TODO, magic numbers, console.log, méthodes longues
simples, naming triviaux, hex hardcodé). Cf. matrice `agents/code-reviewer.md §6`.

### 1.11 Security (OWASP Top 10 2021, depuis v6.3.2)

Émis par l'agent `security-reviewer` (Sonnet 4.6, modes `threat-model` +
`scan`). Chaque classe porte une **sévérité** ordinale + une référence
**OWASP** et **CWE** quand applicable. Le verdict 🟢/🟡/🔴 dépend du
seuil `SecurityFailOn` du Project Config, sauf classes hard-blocking.

| Préfixe | OWASP | CWE | Sévérité | Mode |
|---|---|---|---|---|
| `[SEC_SECRET_HARDCODED]` | A02/A07 | CWE-798 | critical (hard-blocking) | scan §5.1 |
| `[SEC_SECRET_DEV_CONFIG]` | A05 | CWE-798 | moderate | scan §5.1 (downgrade pour dev configs) |
| `[SEC_SQL_INJECTION]` | A03 | CWE-89 | critical (hard-blocking) | scan §5.2 |
| `[SEC_COMMAND_INJECTION]` | A03 | CWE-78 | critical (hard-blocking) | scan §5.2 |
| `[SEC_XSS_RISK]` | A03 | CWE-79 | critical (back) / serious (front) | scan §5.3 |
| `[SEC_BROKEN_AUTHZ]` | A01 | CWE-862 | critical (hard-blocking) | scan §5.4 |
| `[SEC_BROKEN_AUTHN]` | A07 | CWE-287 | critical (hard-blocking) | scan §5.4 |
| `[SEC_IDOR]` | A01 | CWE-639 | serious | scan §5.4 |
| `[SEC_CRYPTO_WEAK]` | A02 | CWE-327 | serious | scan §5.5 |
| `[SEC_CRYPTO_NO_SALT]` | A02 | CWE-759 | serious | scan §5.5 |
| `[SEC_RANDOM_INSECURE]` | A02 | CWE-338 | serious | scan §5.5 |
| `[SEC_CORS_PERMISSIVE]` | A05 | CWE-942 | serious | scan §5.6 |
| `[SEC_HEADERS_MISSING]` | A05 | CWE-693 | moderate | scan §5.6 |
| `[SEC_DEV_ENDPOINTS_EXPOSED]` | A05 | CWE-1188 | serious | scan §5.6 |
| `[SEC_JWT_MISCONFIG]` | A07 | CWE-1004 | critical (hard-blocking) | scan §5.7 |
| `[SEC_COOKIE_INSECURE]` | A07 | CWE-614 | serious | scan §5.7 |
| `[SEC_PASSWORD_WEAK_POLICY]` | A07 | CWE-521 | moderate | scan §5.7 |
| `[SEC_DESERIALIZATION_UNSAFE]` | A08 | CWE-502 | critical (hard-blocking) | scan §5.8 |
| `[SEC_LOGGING_SECRETS]` | A09 | CWE-532 | serious | scan §5.9 |
| `[SEC_STACK_TRACE_EXPOSED]` | A09 | CWE-209 | serious | scan §5.9 |
| `[SEC_SSRF_RISK]` | A10 | CWE-918 | critical (hard-blocking) | scan §5.10 |

**Hard-blocking systématique** (8 classes — override `SecurityFailOn`) :
`[SEC_SECRET_HARDCODED]`, `[SEC_SQL_INJECTION]`, `[SEC_COMMAND_INJECTION]`,
`[SEC_BROKEN_AUTHZ]`, `[SEC_BROKEN_AUTHN]`, `[SEC_DESERIALIZATION_UNSAFE]`,
`[SEC_JWT_MISCONFIG]`, `[SEC_SSRF_RISK]`. Substance : `agents/security-reviewer.md §7.3`.

**Coordination avec code-reviewer** : `[REVIEW_SECRETS_HARDCODED]` (§1.10)
est dé-dupliqué par `security-reviewer.md §6` quand `code-review.json`
existe — évite double-rapport sur les mêmes file+line.

**Mode `threat-model`** (pré-dev) émet uniquement des items
**informationnels** (verdict `"informational"`, jamais 🔴/🟡/🟢).
Chaque threat porte une catégorie STRIDE (`Spoofing`/`Tampering`/
`Repudiation`/`InfoDisclosure`/`DoS`/`Elevation`) + control recommandé.

### 1.12 Performance (Core Web Vitals + SLO, depuis v6.4.0)

> **v7.0.0** : agent `performance-auditor` **retiré**
> (`governance-major-auditors-trim`). Les classes ci-dessous sont
> **conservées comme schéma de mapping** pour la sortie Lighthouse CI +
> wrk/k6 du projet généré (ingest futur via `ingest_perf_lighthouse.py`).
> Aucune n'est émise par un agent SDD_Pro après v6.10.5.

Historique (v6.4.0-v6.10) : émis par `performance-auditor` (Sonnet 4.6).
Aucune classe n'est hard-blocking par défaut — la perf est contextuelle
(site marketing tolère 3s LCP, banque non). Le seuil est piloté par
`PerfFailOn` du Project Config. **Exception** : `[PERF_AC_VIOLATION]`
était hard-blocking quand une AC d'US mentionne explicitement une
métrique perf.

| Préfixe | Métrique | Seuil défaut | Sévérité | Phase |
|---|---|---|---|---|
| `[PERF_LCP_TOO_HIGH]` | LCP frontend | > 2500 ms (WCAG AA) | critical | perf-auditor §5.1 |
| `[PERF_CLS_TOO_HIGH]` | CLS | > 0.1 | serious | perf-auditor §5.1 |
| `[PERF_FID_TOO_HIGH]` | FID (legacy) | > 100 ms | serious | perf-auditor §5.1 |
| `[PERF_INP_TOO_HIGH]` | INP (Chrome 125+) | > 200 ms | serious | perf-auditor §5.1 |
| `[PERF_TTFB_TOO_HIGH]` | TTFB backend | > 600 ms | serious | perf-auditor §5.2 |
| `[PERF_API_P95_HIGH]` | API p95 latency | > 300 ms | serious | perf-auditor §5.2 |
| `[PERF_API_P99_HIGH]` | API p99 latency | > 1000 ms | moderate | perf-auditor §5.2 |
| `[PERF_DB_QUERY_P95_HIGH]` | DB query p95 | > 100 ms | moderate | perf-auditor §5.2 |
| `[PERF_BUNDLE_TOO_LARGE]` | JS bundle size | > 250 KB gzipped | serious | perf-auditor §4.1 |
| `[PERF_BUNDLE_LARGE]` | JS bundle size | 500-1500 KB raw | moderate | perf-auditor §4.1 |
| `[PERF_RENDER_BLOCKING]` | scripts sync dans `<head>` | — | serious | perf-auditor §4.2 |
| `[PERF_N_PLUS_ONE_RISK]` | N+1 query (cross-fichier) | — | serious | perf-auditor §4.3 |
| `[PERF_MEMORY_LEAK_SUBSCRIPTION]` | subscriptions sans cleanup | — | moderate | perf-auditor §4.4 |
| `[PERF_LONG_SYNC_LOOP]` | loop sync > 1000 itérations main thread | — | moderate | perf-auditor §4.5 |
| `[PERF_DB_QUERY_NO_INDEX]` | query sur champ non indexé | — | moderate | perf-auditor §4.6 |
| `[PERF_AC_VIOLATION]` | AC d'US explicite non respectée | — | critical (hard-blocking) | perf-auditor §6.3 |

**Coordination avec code-reviewer** : `[PERF_N_PLUS_ONE_RISK]` étend
`[REVIEW_ANTI_PATTERN_N_PLUS_ONE]` (§1.10) avec heuristique cross-fichier
(lazy load dans loop). Si `code-review.json` flag déjà N+1 sur même
file+line, perf-auditor dé-duplique (cf. agent §coord).

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

### 1.14 Tooling & Governance (compact, depuis v7.0.0)

Classes émises par les commandes/scripts **hors pipeline build_loop** —
mono-shot, déterministes, ne déclenchent pas d'itération. Détail
opérationnel dans le script source cité. Aucune classe n'est
hard-blocking par défaut sauf annoté `(bloquant)`.

**Discover** (`/sdd-discover-stack`, `scan_repo.py`, `match_stack_catalog.py`)
— produit `stack.md.candidate`, ne touche pas le moteur :

| Préfixe | Sens | Bloquant |
|---|---|:---:|
| `[SCAN_NO_MANIFESTS]` | Aucun manifest détecté dans le périmètre | WARN |
| `[SCAN_PARSE_ERROR]` | Manifest présent mais illisible | WARN |
| `[DISCOVER_SCAN_FAILED]` | Erreur I/O fatale scan_repo | (bloquant) |
| `[DISCOVER_NO_MATCH]` | Manifests présents mais aucun combo SDD_Pro reconnu | (bloquant) |
| `[DISCOVER_PARTIAL]` | Backend sans frontend (ou inverse) | info |
| `[DISCOVER_AMBIGUOUS]` | ≥ 2 candidats même catégorie | info |
| `[DISCOVER_STACK_EXISTS]` | `stack.md` existe déjà, génération en `.candidate` | info |

**Checkpoint** (`sdd_lib/checkpoint.py`, opt-in via `CheckpointMode`)
— fail-safe : doute = re-exec, pas skip optimiste. Aucune bloquante :

| Préfixe | Sens |
|---|---|
| `[CHECKPOINT_HASH_MISMATCH]` | input_hash recalculé ≠ stocké — phase doit re-exec |
| `[CHECKPOINT_INPUT_MISSING]` | Fichier d'input déclaré disparu |
| `[CHECKPOINT_STATE_UNREADABLE]` | state.json absent/corrompu |

**Governance** (`layered_config.py`, `manage_profile.py`, `validate_inline_rules.py`) :

| Préfixe | Sens | Bloquant |
|---|---|:---:|
| `[CONFIG_SECURITY_DOWNGRADE]` | Project tente de relâcher une policy team (SecurityFailOn↓, CoverageMin↓) | **OUI** |
| `[PROFILE_EXISTS]` / `[PROFILE_NOT_FOUND]` / `[PROFILE_NO_TEAM_CONFIG]` | `/sdd-profile` exit 1 ou 2 | command |
| `[DRIFT_SUSPECTED]` | Inline rule agent .md non-synchro avec `rules/X.md` source | WARN |

**Architecture Review** (agent `arch-reviewer` Sonnet 4.6, read-only ;
verdict 🟢/🟡/🔴 selon `ArchReviewFailOn` ; persiste dans `qa_code_review`) :

| Préfixe | Sévérité |
|---|:---:|
| `[ARCH_PATTERN_VIOLATION]` | serious (MVC/DDD : DbContext dans UI, Aggregate sans Port…) |
| `[ARCH_LAYER_BYPASS]` | serious (étend `[LAYER_VIOLATION]` cross-fichier) |
| `[ARCH_ADR_DRIFT]` | moderate (décision ADR §6 non appliquée) |
| `[ARCH_NAMING_INVALID]` | minor (suffixe `Service`/`Repository`/`UseCase` manquant) |
| `[ARCH_CONSTITUTION_GAP]` | minor (info) (entité du glossaire absente du code) |
| `[ARCH_NO_TARGETS]` | (bloquant runtime) |

Substance : `agents/arch-reviewer.md §5`.

**Review Orchestrator** (`/sdd-review`, `sdd_review.py`) :

| Préfixe | Sens | Bloquant |
|---|---|:---:|
| `[REVIEW_VERDICT_RED]` | Verdict consolidé RED post-agrégation | OUI (exit 1) |
| `[REVIEW_DB_UNREACHABLE]` | `console.db` introuvable / non-lisible | OUI (exit 2) |
| `[REVIEW_SCAN_FAILED]` | `quality_scan.py` re-run échoué | WARN (continue sur DB stale) |

---

### 1.15 Inconnue

| Préfixe | Usage |
|---|---|
| `[UNKNOWN]` | Erreur non classifiable (stderr brut, exception non gérée) |

---

## 2. Format obligatoire

**Chat** (compressé — 1L succès, 2L max erreur) :
```
🔴 {agent} {n}-{m} — {résumé}
CAUSE: [{CLASS}] {détail 1L} → {pointer fichier rapport}
```

**Rapport** (3 lignes, dans `workspace/output/qa/...`, `validation/...`) :
```
ERROR: {feat/us/task or pipeline-step} failed
CAUSE: [{CLASS}] {détail 1L}
FIX: {action 1L}
```

**Exemple `[BUILD_CORRECTIBLE]`** (build_loop itère) :
```
ERROR: dev-backend 1-2 build failed (iter 1/3)
CAUSE: [BUILD_CORRECTIBLE] missing import 'SIM.Backend.Services.IBebeService' in BebesEndpoints.cs:1
FIX: add 'using SIM.Backend.Services;'
```

**Exemple `[BUILD_BLOCKING]`** (fail-fast) :
```
ERROR: dev-frontend 2-1 build failed (iter 1/3)
CAUSE: [BUILD_BLOCKING] business logic detected in Pages/Login.razor (DbContext usage in UI layer)
FIX: move data access to Services/AuthService.cs, inject via DI
```

---

## 3. Comportement `build_loop` selon classe

Une seule classe déclenche une itération `build_loop` :

| Itère ? | Classe(s) | Action |
|:---:|---|---|
| **OUI** (max `BuildLoopMaxIter`) | `[BUILD_CORRECTIBLE]` | Re-dispatch agent avec stderr |
| NON | tout le reste | STOP, ERROR au Tech Lead — voir tableau §3.1 |

### 3.1 Actions sur STOP (classes ne provoquant pas d'itération)

| Famille | Action |
|---|---|
| `[BUILD_BLOCKING]` / `[BUILD_LOOP_EXHAUSTED]` / `[DEP_MISSING]` / `[CIRCULAR_DEP]` | STOP fail-fast. Suggérer Opus fallback OU revoir US/stack sur EXHAUSTED. |
| `[LAYER_VIOLATION]` / `[PRESERVES_VIOLATED]` / `[ADDS_VIOLATED]` | STOP, repenser plan/US |
| `[STACK_LIBRARY_*]` / `[STACK_RUNTIME_NOT_LTS]` | STOP, mettre à jour `.libs.json` puis relancer |
| `[FILE_OWNERSHIP*]` | STOP, corriger le plan ou la matrice ownership |
| `[INVALID_ARG]` / `[INVALID_MODE]` / `[PROJECT_NOT_INIT]` | STOP, corriger l'invocation ou l'amont (`arch`) |
| `[BREAKING_CLEANUP_FAILED]` | STOP narrow, vérifier CLAUDE.md projet |
| `[PLAN_STALE]` / `[PLAN_INVALID]` | STOP, relancer `/dev-plan {n}` |
| `[US_DEPS_CYCLE]` / `[US_DEPS_MISSING]` | STOP, corriger `## Dependencies` puis relancer (idempotent) |
| `[UI_FIDELITY_GAP]` | 1 retry après revue plan, sinon WARN ou STOP selon score |
| `[US_DEPS_ORPHAN]` / `[US_STATUS_*]` / `[CHECKPOINT_*]` / `[DRIFT_SUSPECTED]` | Informational, jamais bloquant |
| `[CONFIG_SECURITY_DOWNGRADE]` | **Bloquant** au moment du `read_layered_config()` |
| Auditors : `[REVIEW_*]` / `[SEC_*]` / `[SPEC_*]` / `[ARCH_*]` / `[A11Y_*]` (héritage) / `[PERF_*]` (héritage) | Rapport seul (`{n}-{kind}.{md,json}`) ; verdict 🟢/🟡/🔴 selon `{Kind}FailOn` du Project Config ; aucun build_loop ; hard-blocking selon table de la sous-section (§1.10-§1.13) ; Tech Lead arbitre |
| `[DISCOVER_*]` / `[SCAN_*]` / `[PROFILE_*]` | Mono-shot, hors pipeline. Bloquant ou info selon classe — cf. §1.14 |
| `[PLAN_NOT_STRICT_READY]` / `[PLAN_DIGEST_INSUFFICIENT]` (héritage v6.2) | Plus utilisé en v7.0.0 (`dev-*-strict` retirés) — toléré en lecture |

---

## 4. Enforcement

- **Agents** retenus en v7.0.0 (po, arch, dev-backend, dev-frontend,
  qa, elicitor, constitutioner, code-reviewer, security-reviewer,
  spec-compliance-reviewer, arch-reviewer) chargent cette règle en
  STEP contexte. Voir `@.claude/loader.yml` pour le mapping détaillé.
  Retirés v7.0.0 (`accessibility-auditor`, `performance-auditor`,
  `dashboard`, `dev-*-strict`) — classes héritage conservées pour ingest
  futur de `axe-core` / Lighthouse CI.
- **Scripts** (`preflight.py`, `validate_readiness.py`,
  `parse_coverage.py`, `quality_scan.py`, `validate_fidelity.py`,
  `validate_augment_contract.py`, `audit_file_ownership.py`,
  `sdd_review.py`, `report_roi.py`) émettent des préfixes `[CLASS]`.
- **Hooks** (`PostToolUse`, `SubagentStop`, `Stop`) lisent les classes
  pour décider (continuer / append warning / STOP).
- Erreur sans préfixe → tolérée (backward-compat) mais traitée
  comme `[UNKNOWN]`.

---

## 5. Règle mentale

**"Pas de bloc ERROR sans préfixe `[CLASS]`. Si rien ne matche → `[UNKNOWN]`."**

Discipline qui permet à `build_loop` de décider mécaniquement, aux
scripts de classer sans LLM, au dashboard de visualiser par cause-racine.
