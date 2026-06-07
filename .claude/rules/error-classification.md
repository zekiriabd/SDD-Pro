# Règle — Error Classification (vocabulaire d'erreur unifié cross-agent)

## Principe

Tous les agents et scripts SDD_Pro préfixent leurs blocs ERROR avec un
**code `[CLASS]`** dans le `CAUSE:`. Permet à `build_loop`, hooks et
dashboards de classer sans interprétation textuelle.

Source canonique unique — concentre les codes auparavant dispersés
dans `library-and-stack.md`, `ownership.md`, `quality.md`
et inlinés dans les agents (po, dev-*, qa).

> **Note granularité (Sprint 2.4 audit 2026-06-07 ; recount CTO audit
> 2026-06-07 ; clarification méthodologique audit consolidé 2026-06-07)** : **174 classes** recensées dans ce fichier (172 actives + 2 dépréciées).
>
> **Source de vérité** : somme déterministe de la colonne "Classes" du
> quick-ref §0 ci-dessous (`8+25+13+5+7+3+10+3+11+12+23+16+9+22+6+1 = 174`).
> Ce nombre est utilisé dans toute communication commerciale (CLAUDE.md,
> WHY-SDD-PRO.md, getting-started.md, README.md) et enforcé par le test
> `tests/test_error_classification_count.py` (gate CI : tout drift entre
> intro et somme = FAIL).
>
> **Méthodologie de comptage** :
> - Le chiffre 174 compte les **familles déclarées** par section §1.X
>   (chaque entrée de quick-ref agrège plusieurs préfixes apparentés
>   sous une étiquette canonique).
> - Un `grep -oE '\[[A-Z_]+\]'` unique sur ce fichier retourne ~152
>   préfixes distincts (l'écart vient des fusions documentaires comme
>   `[PLAN_INVALID]` qui englobe 7 sous-cas `_UNREADABLE`,
>   `_NO_FRONTMATTER`, etc. — cf. §1.2 fusion 2026-06-07).
> - L'annexe `error-classification-legacy.md` ajoute 27 préfixes
>   héritage (11 `[A11Y_*]` + 16 `[PERF_*]`), réactivés via ingest CI
>   v7.2.0 (`ingest_axe.py`, `ingest_lighthouse.py`). Ces 27 préfixes
>   **ne sont pas comptés** dans le 174 du fichier principal — ils
>   sont émis par des scripts d'ingest CI, pas par des agents SDD_Pro.
> - Le test `tests/test_error_classification_count.py` enforce
>   l'alignement intro ↔ quick-ref §0 ↔ titre `## 0`.
>
> Recount audit CTO 2026-06-07 : §1.7 +1 ([ACCEPTANCE_GATE_FAILED]),
> §1.11 +1 ([SEC_CORS_MISSING]), §1.14 sous-comptait body de -9
> (réconcilié 13→22).
>
> La granularité n'est PAS de la sur-ingénierie — elle est **load-bearing**
> pour 4 systèmes :
> 1. **YAML patterns** (`security_patterns.yaml`, `code_review_patterns.yaml`)
>    — détection par regex par sous-classe
> 2. **Tests enforcement** (`test_security_patterns.py`,
>    `test_code_review_patterns.py`) — alignment YAML ↔ doc
> 3. **Fix dispatcher** (`dispatch_fixes.py`) — chaque sous-classe mappe
>    à une recette de fix précise (ex. `KEY_INDEX` → "stable id from data")
> 4. **Security tooling CWE-level** — parité Snyk/Semgrep/CodeQL exige
>    un CWE par class (e.g. CWE-327 vs 759 vs 338 pour SEC_CRYPTO_*)
>
> Toute fusion exige refactor coordonné des 4 systèmes (sprint dédié
> ~3-5 jours, roadmap v7.2 — cf. `docs/roadmap-v7-v8.md`, ADR à émettre
> lors du sprint d'implémentation). Pour l'instant, navigation rapide
> via §0 ci-dessous.

---

## 0. Quick reference — 16 familles (174 classes)

| # | Famille | Classes | Émetteur principal | Comportement build_loop |
|---|---|---:|---|---|
| §1.1 | **Runtime** (`[NETWORK]`/`[AUTH]`/`[PERMISSION]`/`[NOT_FOUND]`/`[TIMEOUT]`/`[DISK]`/`[ENV_*]`) | 8 | tous | STOP |
| §1.2 | **Pipeline** (`[STACK_MALFORMED]`/`[FEAT_*]`/`[PLAN_*]`/`[READINESS_*]`/`[INVALID_*]`/...) | 25 | po, arch, validate_plan.py | STOP |
| §1.3 | **Contrat ownership** (`[PRESERVES_VIOLATED]`/`[ADDS_VIOLATED]`/`[LAYER_VIOLATION]`/`[FILE_*]`/`[US_*]`) | 13 | dev-*, set_us_status.py | STOP |
| §1.4 | **Build** (`[BUILD_*]`/`[DEP_MISSING]`/`[CIRCULAR_DEP]`) | 5 | dev-* | **ITÈRE** sur `[BUILD_CORRECTIBLE]` uniquement |
| §1.5 | **Anti-derive** (`[DERIVE_VIOLATION]`/`[STACK_LIBRARY_*]`/`[REFACTOR_HORS_SCOPE]`/...) | 7 | dev-* | STOP |
| §1.6 | **UI fidelity** (`[UI_FIDELITY_GAP]`/`[UI_TOKEN_VIOLATION]`/`[FRONTEND_BACKEND_CONTRACT_GAP]`) | 3 | dev-frontend | STOP/retry |
| §1.7 | **QA** (`[QA_TEST_FAILED]`/`[QA_COVERAGE_GAP]`/`[QA_OWNERSHIP_*]`/`[ACCEPTANCE_GATE_FAILED]`/...) | 10 | qa | STOP (RED bloquant) |
| §1.8 | **Parallélisme** (`[LIBNAME_LOCK_HELD]`/`[LOCK_HELD]`/`[LIBNAME_SIGNATURE_CONFLICT]`) | 3 | dev-* | STOP |
| §1.9 | **A11Y** (`[A11Y_*]`) — héritage, réactivé via `ingest_axe.py` | 11 | CI ingest (Lighthouse/axe) | report only |
| §1.10 | **Code Review** (`[REVIEW_*]`) — `code-reviewer` agent | 12 | code-reviewer | report only (verdict 🟢/🟡/🔴) |
| §1.11 | **Security** (`[SEC_*]`) — OWASP Top 10 2021 | 23 | security-reviewer | report only + 8 hard-blocking |
| §1.12 | **Perf** (`[PERF_*]`) — héritage, réactivé via `ingest_lighthouse.py` | 16 | CI ingest | report only |
| §1.13 | **Spec Compliance** (`[SPEC_*]`) — AC-by-AC verification | 9 | spec-compliance-reviewer | report only |
| §1.14 | **Tooling/Governance** (`[SCAN_*]`/`[DISCOVER_*]`/`[CHECKPOINT_*]`/`[CONFIG_*]`/`[PROFILE_*]`/`[DRIFT_*]`/`[ARCH_*]`/`[REVIEW_*]`) | 22 | scripts mono-shot | mostly info, 2 bloquantes |
| §1.15 | **Adversarial** (`[ADV_*]`) — opt-in `/sdd-review --adversarial` | 6 | adversarial-reviewer | informational |
| §1.16 | **Inconnue** (`[UNKNOWN]`) | 1 | fallback | report only |

**Verdict consolidé** (§1.10-1.13) dépend du seuil `{Kind}FailOn` du
Project Config (`info|minor|moderate|serious|critical`). Voir §3.1 pour
le tableau d'actions par famille.

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
| `[FORCE_CUMUL_REJECTED]` | ≥ 2 bypass flags (`--force`, `--no-plan-on-warn`, `--no-validate`) cumulés sans `SDD_ALLOW_FORCE=1` env | sdd-full STEP 3.6.quart (v7.0.0 audit P0 R1) |
| `[COST_CAP_EXCEEDED]` | Cumulative USD cost ≥ `MaxCostPerRun` (default $50) sur le run en cours. Bloquant CI + interactif (v7.0.0 R1 fix). Bypass : `SDD_DISABLE_COST_CAP=1` one-shot OU `MaxCostPerRun: 0` config. | preflight_cost_cap.py (v7.0.0 P0 §4.3) |
| `[BUILD_LOOP_COST_EXCEEDED]` | Cumulative USD spent on build_loop iterations for ONE US ≥ `BuildLoopMaxCostUsd` (default $15) avant que `BuildLoopMaxIter` ne soit atteint. STOP fail-fast — distinguer de `[BUILD_LOOP_EXHAUSTED]` (iter limit) car la cause-racine est cost-pathological pas convergence-pathological. Bypass : `BuildLoopMaxCostUsd: 0` config. | dev-* build_loop (v7.0.0 P1 §6) |
| `[QA_FAIL_BLOCKING_SDD_FULL]` | `/qa-generate` verdict RED + `QaFailOnSddFull: true` (default v7.0.0) → STOP `/sdd-full` post-STEP 4.5. Symétrise le gate avec `/qa-generate` standalone (avant : bloquant standalone, ignoré dans `/sdd-full`). Bypass : `QaFailOnSddFull: false` (audit-log). | sdd-full STEP 4.5 (v7.0.0 audit §6.9) |
| `[FEAT_HASH_MISMATCH]` | Hash sha256 de la FEAT parente diffère de celui inscrit dans une US (`Parent FEAT hash: sha256:...`). FEAT modifiée après génération US → `Covers:` potentiellement obsolète. Fix : re-run `/us-generate {n}` (idempotent). | dev-*, validate_readiness, auditors (v7.0.0 audit §6 P1-11) |
| `[ELICITOR_GAP]` | FEAT contient sections élicitor (FAIL-N, EDGE-N, Red Team) mais ≥ 1 item n'est mappé sur aucune AC d'aucune US. WARN par défaut (`ElicitorGapMode: warn`), `strict` = NO-GO. | po STEP 4 (v7.0.0 audit §6.11 — boucle elicitor) |
| `[PHASE_PLAN_INIT_FAILED]` | `/dev-run` standalone : `phase_planner.py` exit ≠ 0 (FEAT inexistante / Project Config malformé). Bloquant STEP 5.5.1 — sans `$PHASE_PLAN`, STEP 6.4 (auditor batch) ne peut décider quels reviewers spawner. | dev-run STEP 5.5.1 (v7.0.0 audit P2) |
| `[PLAN_NOT_FOUND]` | Plan attendu absent (Glob 0 match dans `workspace/output/plans/`) | validate_plan.py |
| `[PLAN_INVALID]` | Plan structurellement invalide. **Englobe 7 sous-cas** (v7.0.0-alpha Sprint 2.4 — fusion documentaire 2026-06-07) : `_UNREADABLE` I/O error, `_NO_FRONTMATTER` YAML missing, `_FRONTMATTER_INVALID` field type/value, `_MISSING_REQUIRED_FIELD` `us`/`family` absent, `_FILES_SECTION_MISSING` `## Files` empty, `_FILE_ENTRY_INVALID` path/operation/layer missing, `_AUGMENT_CONTRACT_MISSING` augment sans preserves/adds. Le message ERROR détaillera le sous-cas. | validate_plan.py |
| `[PLAN_AC_COVERAGE_GAP]` | ACs de l'US absents de `## ACs Coverage Summary` du plan | validate_plan.py (strict) |
| `[PLAN_STALE]` | us-hash mismatch — US modifiée post-plan, re-`/dev-plan` requis | validate_plan.py (strict) → STOP |
| ~~`[PLAN_NOT_STRICT_READY]`~~ | **DÉPRÉCIÉ v7.0.0** — strict variants supprimés (`governance-major-auditors-trim`). Toléré en lecture des bases console.db legacy. | (n/a) |
| ~~`[PLAN_DIGEST_INSUFFICIENT]`~~ | **DÉPRÉCIÉ v7.0.0** — strict variants supprimés. Toléré en lecture des bases console.db legacy. | (n/a) |
| `[INVALID_ARG]` | Argument CLI invalide (regex `^\d+-\d+(:plan)?$` ou `^\d+$` non matché) | dev-*, sdd-full, dev-run, dev-plan, feat-validate STEP 1 |
| `[INVALID_MODE]` | Mode d'exécution incompatible (`:plan` invoqué alors qu'un plan existe ; etc.) | `build-and-loop.md §1.ter.3` (Partie B) |
| `[PROJECT_NOT_INIT]` | Fichier projet absent (`.csproj`/`package.json`/`pyproject.toml`/`build.gradle.kts`/`angular.json`) — arch n'a pas tourné | preflight.py B4, dev-*-strict STEP 4 |
| `[PLAN_REVIEW_GATE_SKIPPED]` | Plan-then-review gate bypassé (WARN informationnel) | sdd-full STEP 3.6 |
| `[STACK_SCAFFOLDING_MISSING]` | Arch n'a pas scaffoldé les entities attendues (DB→entities cohérence cassée) | arch Phase B, dev-backend STEP 4.5 |

### 1.3 Contrat (preserves/adds, layers, ownership)

| Préfixe | Usage | Phase |
|---|---|---|
| `[PRESERVES_VIOLATED]` | Identifier `preserves:` retiré après augment | dev-* post-Edit |
| `[ADDS_VIOLATED]` | Identifier `adds:` non présent après écriture | dev-* post-Edit |
| `[LAYER_VIOLATION]` | Code dans couche interdite (ex. business in UI) | dev-* STEP build |
| `[FILE_OWNERSHIP]` | Path interdit par `ownership.md §1` (Partie A) | hook SubagentStop |
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
| `[STACK_RUNTIME_NOT_LTS]` | Runtime STS/prerelease pinné en `versions` (.NET 9, Node 23, Java 22, etc.) sans bypass ADR (cf. `docs/adrs/ADR-20260605T163200-runtime-sts-prerelease-exceptions.md` pour la liste exhaustive des bypass autorisés) | arch post-install (CVE check), `validate_libs_catalog.py` |
| `[RUNTIME_STS_EXCEPTION]` | WARN-level — bypass STS tracé via ADR `runtime-sts-prerelease-exceptions` (`docs/adrs/ADR-20260605T163200-runtime-sts-prerelease-exceptions.md`) + `RuntimeException:` Project Config (matrice cas-par-cas dans l'ADR). | `validate_libs_catalog.py` |

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
| `[API_GATE_RED]` | API Gate (cf. `build-and-loop.md §A`) RED, frontend bloqué | dev-run phase 4c |
| `[ACCEPTANCE_GATE_FAILED]` | Acceptance Gate (`validate_acceptance.py`) fail en mode `strict` (`test`/`lint`/`build`/`coverage`/`smoke`/`E2E` KO). Bypass : `SDD_ALLOW_ACCEPTANCE_BYPASS=1`. Cf. `quality.md §C`. | qa STEP 9.bis + hook `SubagentStop` matcher=qa |

Priorité d'émission : `[QA_TEST_FAILED] > [QA_COVERAGE_GAP]` ;
`[API_GATE_RED] > tout autre QA_*`.

### 1.8 Parallélisme (file ownership / locks)

| Préfixe | Usage |
|---|---|
| `[LIBNAME_LOCK_HELD]` | Lock LibName détenu par autre agent (cf. `ownership.md §4`, Partie A) |
| `[LIBNAME_SIGNATURE_CONFLICT]` | DTO/Model partagé, signatures divergentes |
| `[LOCK_HELD]` | Lock générique cross-language (sdd_lib/file_locks.py) — `workspace/console/.status.lock`, etc. Alias générique de `[LIBNAME_LOCK_HELD]` pour contextes non-LibName |

### 1.9 A11Y — agent retiré v7.0.0, classes réactivées via ingest CI v7.2.0

Classes `[A11Y_*]` (11 préfixes canoniques, WCAG 2.2 + fallback
`A11Y_RULE_*` pour les règles axe-core non mappées). Émises par
`accessibility-auditor` (LLM) v6.3.0-v6.10, **agent retiré v7.0.0**
(`governance-major-auditors-trim`).

**Réactivation v7.2.0 (Option B — ingest déterministe)** :
`sdd_scripts/ingest_axe.py` consomme le JSON produit par axe-core CLI
au CI du projet généré (`.github/workflows/quality.yml`), mappe chaque
violation vers un préfixe `[A11Y_*]` via `AXE_RULE_MAP`, calcule le
verdict 🟢/🟡/🔴 contre `--threshold` (défaut `serious`), et persiste
dans `qa_a11y` + `auditor_runs(auditor='a11y')`. **Pas de coût LLM**.

Le schéma complet (tableau préfixes × WCAG × sévérité) reste dans
`@.claude/rules/error-classification-legacy.md §1` (source de vérité).
Lecture par `/sdd-review` via `_review_fetch.py` inchangée
(`SELECT ... FROM qa_a11y ...`).

### 1.10 Code Review (cross-fichier, depuis v6.3.1)

Émis par l'agent `code-reviewer` (Sonnet 4.6). Chaque classe porte une
**sévérité** ordinale `critical > serious > moderate > minor` qui pilote
le verdict 🟢/🟡/🔴 contre le seuil `CodeReviewFailOn` du Project Config.

| Préfixe | Catégorie | Sévérité | Phase |
|---|---|---|---|
| `[REVIEW_SECRETS_HARDCODED]` | sécurité | minor (info) — **owned exclusivement par `security-reviewer` `[SEC_SECRET_HARDCODED]`** (audit P0-doc 2026-06-05) | code-reviewer STEP 5.5 (info uniquement) |
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
`[FRONTEND_BACKEND_CONTRACT_GAP]` force le verdict 🔴 RED quelque soit
le seuil configuré. Substance opérationnelle : `agents/code-reviewer.md §7.3`.

> **v7.0.0-alpha audit P0-doc 2026-06-05** — `[REVIEW_SECRETS_HARDCODED]`
> retiré du hard-blocking code-reviewer. Le scan secrets est désormais
> owned **exclusivement** par `security-reviewer` (classe `[SEC_SECRET_HARDCODED]`
> §1.11, hard-blocking CWE-798). Si code-reviewer rencontre incidemment un
> secret évident, il l'émet en `issues.minor` à titre informationnel avec
> pointeur vers `security-reviewer`. Plus de double-rapport sur les mêmes
> file:line.

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
| `[SEC_ENV_VAR_FORBIDDEN]` | A05 | CWE-1188 | serious | scan §5.11 (audit 2026-06-06) |
| `[SEC_CORS_MISSING]` | A05 | CWE-942 | serious | scan §5.6 (audit 2026-06-07 — backend SPA-facing sans config CORS, cf. `library-and-stack.md §B.5`) |

**Hard-blocking systématique** (8 classes — override `SecurityFailOn`) :
`[SEC_SECRET_HARDCODED]`, `[SEC_SQL_INJECTION]`, `[SEC_COMMAND_INJECTION]`,
`[SEC_BROKEN_AUTHZ]`, `[SEC_BROKEN_AUTHN]`, `[SEC_DESERIALIZATION_UNSAFE]`,
`[SEC_JWT_MISCONFIG]`, `[SEC_SSRF_RISK]`. Substance : `agents/security-reviewer.md §7.3`.

**Audit 2026-06-06 — `[SEC_ENV_VAR_FORBIDDEN]`** : code applicatif lisant
directement les env vars (`Environment.GetEnvironmentVariable("DB_*")`,
`process.env.DB_*`, `os.environ["DB_*"]`, `@Value("${DB_*}")`) pour les clés
provisionnées via `stack.md` (DB, AUTH_JWT, AZ_*, SMTP_*). Contredit Pattern B
(stack.md = SSoT, arch peuple les configs natives en clair). Le code doit
lire la config native (`IConfiguration`, `@Value` sur les clés `spring.datasource.*`,
`config.get('db.password')`, `Settings().db_password`) — jamais les env vars
directement. Cf. `agents/arch.md §STEP 4.5`, `rules/library-and-stack.md §1.0`.

**Coordination avec code-reviewer** : `[REVIEW_SECRETS_HARDCODED]` (§1.10)
est dé-dupliqué par `security-reviewer.md §6` quand `code-review.json`
existe — évite double-rapport sur les mêmes file+line.

**Mode `threat-model`** (pré-dev) émet uniquement des items
**informationnels** (verdict `"informational"`, jamais 🔴/🟡/🟢).
Chaque threat porte une catégorie STRIDE (`Spoofing`/`Tampering`/
`Repudiation`/`InfoDisclosure`/`DoS`/`Elevation`) + control recommandé.

### 1.12 Performance — agent retiré v7.0.0, classes réactivées via ingest CI v7.2.0

Classes `[PERF_*]` (16 préfixes, Core Web Vitals + SLO API) émises par
`performance-auditor` (LLM) v6.4.0-v6.10, **agent retiré v7.0.0**
(`governance-major-auditors-trim`).

**Réactivation v7.2.0 (Option B — ingest déterministe)** :
`sdd_scripts/ingest_lighthouse.py` consomme la sortie de Lighthouse
CI (`.lighthouseci/lhr-*.json`) au CI du projet généré, sélectionne
la run médiane (recommandation lhci), compare les Core Web Vitals
(LCP, CLS, INP/TBT, TTFB) + total payload + render-blocking aux
seuils (`--lcp-ms`/`--cls`/`--inp-ms`/`--ttfb-ms`/`--bundle-kb`,
défauts depuis legacy §2), émet les `[PERF_*]` matchants et persiste
dans `qa_performance` + `auditor_runs(auditor='perf')`. **Pas de
coût LLM**. Préfixes SLO API backend (`[PERF_TTFB_*]`, `[PERF_API_P95_*]`,
`[PERF_DB_QUERY_*]`) restent disponibles pour un ingest wrk/k6 futur
(out-of-scope v7.2.0, schéma `qa_performance.metric` déjà en place).

Le schéma complet (16 préfixes × métrique × seuil × sévérité) reste
dans `@.claude/rules/error-classification-legacy.md §2` (source de
vérité). Lecture par `/sdd-review` inchangée.

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
| `[CHECKPOINT_STATE_UNREADABLE]` | state.json checkpoint OU schema.json arch (depuis v7.0.0 audit P0 R2) absent ou corrompu (JSON unparsable, clé `tables` manquante…). Émis par `detect_arch_shortcircuit.py` quand schema.json présent mais invalide — empêche le fallback "safe arch" silencieux qui propagait la corruption aux dev-*. |

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

### 1.15 Adversarial Review (avocat du diable, depuis v7.2.0 R1)

Émises par l'agent `adversarial-reviewer` (Sonnet 4.6) invoqué par
`/sdd-review --adversarial` (opt-in). **Aucune classe n'est bloquante
par design** — verdict global toujours `informational`. Ces préfixes
existent pour qu'une attaque soit traçable (file:line) et que le Tech
Lead puisse extraire celles qui valent une US de remédiation.

| Préfixe | Angle | Question type |
|---|---|---|
| `[ADV_EDGE_CASE]` | edge_case | Empty/max/unicode/NaN/dates passé-futur/collision IDs |
| `[ADV_FRAGILE_ASSUMPTION]` | fragile_assumption | Ordering implicite, idempotence non vérifiée, lock optimiste absent, TZ mismatch |
| `[ADV_HIDDEN_TECH_DEBT]` | hidden_tech_debt | Catch-swallow, fallback silencieux, magic cross-FEAT, prerelease pin, dead code |
| `[ADV_FAILURE_MODE]` | failure_mode | DB unavailable, partial write, OOM payload, désérialisation bombe, retry storm |
| `[ADV_UX_CONFUSION]` | ux_confusion | Message ambigu, action irréversible sans confirm, loading invisible, log PII leak |
| `[ADV_PRECONDITION_FAILED]` | (infra) | `/sdd-review` n'a pas été exécuté avant `--adversarial` (review.md absent) |

**Anti-duplication** : par règle §2.5 de l'agent, toute attaque qui
chevauche un finding déjà émis par `code-reviewer` / `security-reviewer`
(scan) / `spec-compliance-reviewer` / `arch-reviewer` / `quality_scan.py`
(même file:line ou classe équivalente) est droppée — l'angle adversarial
est strictement complémentaire, jamais redondant.

**Persistance** : `validation_reports(report_type='adversarial', verdict='informational', payload_json={attacks: […]})` via `ingest_agent_report --type adversarial`. **Pas dans `qa_*` tables** (canal séparé du verdict consolidé `/sdd-review`).

---

### 1.16 Inconnue

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
| `[US_DEPS_ORPHAN]` / `[US_STATUS_*]` / `[CHECKPOINT_*]` / `[DRIFT_SUSPECTED]` / `[ADV_*]` (v7.2.0) | Informational, jamais bloquant |
| `[CONFIG_SECURITY_DOWNGRADE]` | **Bloquant** au moment du `read_layered_config()` |
| Auditors : `[REVIEW_*]` / `[SEC_*]` / `[SPEC_*]` / `[ARCH_*]` / `[A11Y_*]` (héritage) / `[PERF_*]` (héritage) | Rapport seul (`{n}-{kind}.{md,json}`) ; verdict 🟢/🟡/🔴 selon `{Kind}FailOn` du Project Config ; aucun build_loop ; hard-blocking selon table de la sous-section (§1.10-§1.13) ; Tech Lead arbitre |
| `[DISCOVER_*]` / `[SCAN_*]` / `[PROFILE_*]` | Mono-shot, hors pipeline. Bloquant ou info selon classe — cf. §1.14 |
| `[PLAN_NOT_STRICT_READY]` / `[PLAN_DIGEST_INSUFFICIENT]` (héritage v6.2) | Plus utilisé en v7.0.0 (`dev-*-strict` retirés) — toléré en lecture |

---

## 4. Enforcement

- **Agents** retenus en v7.0.0+ (po, arch, dev-backend, dev-frontend,
  qa, elicitor, constitutioner, code-reviewer, security-reviewer,
  spec-compliance-reviewer, arch-reviewer, **adversarial-reviewer**
  (R1 v7.2.0)) chargent cette règle en STEP contexte. Voir
  `@.claude/loader.yml` pour le mapping détaillé.
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
