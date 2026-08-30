# Error Classification — digest for `dev-backend`
> **GENERATED — do not edit.** Slice of `@.claude/rules/error-classification.md` for the `dev-backend` agent (audit 2026-06-12, block 5). Regenerate via `python .sdd/python/sdd_admin/sync_error_class_digests.py`.
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
### 1.2 Pipeline (logique framework)

| Préfixe | Usage | Phase |
|---|---|---|
| `[STACK_MALFORMED]` | `stack.md` invalide, section manquante | arch STEP 1 |
| `[SCHEMA_MISMATCH]` | Table/colonne absente de `schema.json` | arch Phase B (échec `flyway migrate`), dev-backend STEP 5 (plan/DTOs sur le schema chargé au STEP 3) |
| `[FEAT_REJECTED]` | FEAT ne respecte pas le format | po STEP 2 |
| `[FEAT_NOT_FOUND]` | Aucun fichier `workspace/feats/{n}-*.md` matché | feat-validate, sdd-full STEP 1 |
| `[FEAT_AMBIGUOUS]` | Plusieurs fichiers `workspace/feats/{n}-*.md` matchent | feat-validate, sdd-full STEP 1 |
| `[GRANULARITY_VIOLATION]` | > 6 US, anti-pattern détecté | po STEP 5/7 |
| `[TRACEABILITY_GAP]` | SFD/AC/BR/FD non couvert par une US | po STEP 6 |
| `[READINESS_NO_GO]` | `/feat-validate` NO-GO sans `--force` | feat-validate |
| `[FORCE_CUMUL_REJECTED]` | ≥ 2 bypass flags (`--force`, `--no-plan-on-warn`, `--no-validate`) cumulés sans `SDD_ALLOW_FORCE=1` env | sdd-full STEP 3.6.quart (v7.0.0 audit P0 R1) |
| `[COST_CAP_EXCEEDED]` | Cumulative USD cost ≥ `MaxCostPerRun` (default $50) sur le run en cours. Bloquant CI + interactif (v7.0.0 R1 fix). Bypass : `SDD_DISABLE_COST_CAP=1` one-shot OU `MaxCostPerRun: 0` config. | preflight_cost_cap.py (v7.0.0 P0 §4.3) |
| `[BUILD_LOOP_COST_EXCEEDED]` | Cumulative USD spent on build_loop iterations for ONE US ≥ `BuildLoopMaxCostUsd` (default $15) avant que `BuildLoopMaxIter` ne soit atteint. STOP fail-fast — distinguer de `[BUILD_LOOP_EXHAUSTED]` (iter limit) car la cause-racine est cost-pathological pas convergence-pathological. Bypass : `BuildLoopMaxCostUsd: 0` config. | hook `preflight_cost_cap.py` (HOOK_DENY au spawn dev-backend/dev-frontend ; v7.0.0 P1 §6) |
| `[QA_FAIL_BLOCKING_SDD_FULL]` | `/qa-generate` verdict RED + `QaFailOnSddFull: true` (default v7.0.0) → STOP `/sdd-full` post-STEP 4.5. Symétrise le gate avec `/qa-generate` standalone (avant : bloquant standalone, ignoré dans `/sdd-full`). Bypass : `QaFailOnSddFull: false` (audit-log). | sdd-full STEP 4.5 (v7.0.0 audit §6.9) |
| `[FEAT_HASH_MISMATCH]` | Hash sha256 de la FEAT parente diffère de celui inscrit dans une US (`Parent FEAT hash: sha256:...`). FEAT modifiée après génération US → `Covers:` potentiellement obsolète. Fix : re-run `/us-generate {n}` (idempotent). | dev-*, validate_readiness, auditors (v7.0.0 audit §6 P1-11) |
| `[ELICITOR_GAP]` | FEAT contient sections élicitor (FAIL-N, EDGE-N, Red Team) mais ≥ 1 item n'est mappé sur aucune AC d'aucune US. WARN par défaut (`ElicitorGapMode: warn`), `strict` = NO-GO. | po STEP 4 (v7.0.0 audit §6.11 — boucle elicitor) |
| `[PHASE_PLAN_INIT_FAILED]` | `/dev-run` standalone : `phase_planner.py` exit ≠ 0 (FEAT inexistante / Project Config malformé). Bloquant STEP 5.5.1 — sans `$PHASE_PLAN`, STEP 6.4 (auditor batch) ne peut décider quels reviewers spawner. | dev-run STEP 5.5.1 (v7.0.0 audit P2) |
| `[PLAN_NOT_FOUND]` | Plan attendu absent (Glob 0 match dans `workspace/plans/`) | validate_plan.py |
| `[PLAN_INVALID]` | Plan structurellement invalide. **Englobe 7 sous-cas** (v7.0.0-alpha Sprint 2.4 — fusion documentaire 2026-06-07) : `_UNREADABLE` I/O error, `_NO_FRONTMATTER` YAML missing, `_FRONTMATTER_INVALID` field type/value, `_MISSING_REQUIRED_FIELD` `us`/`family` absent, `_FILES_SECTION_MISSING` `## Files` empty, `_FILE_ENTRY_INVALID` path/operation/layer missing, `_AUGMENT_CONTRACT_MISSING` augment sans preserves/adds. Le message ERROR détaillera le sous-cas. | validate_plan.py |
| `[PLAN_AC_COVERAGE_GAP]` | ACs de l'US absents de `## ACs Coverage Summary` du plan | validate_plan.py (**always-on** depuis audit M5 2026-08-29 — auparavant sous `--strict`, donc jamais atteint) |
| `[PLAN_STALE]` | us-hash mismatch — US modifiée post-plan, re-`/dev-plan` requis | validate_plan.py (always-on) → STOP |
| ~~`[PLAN_NOT_STRICT_READY]`~~ | **DÉPRÉCIÉ v7.0.0, code SUPPRIMÉ 2026-08-29 (audit M5)** — les variants `dev-*-strict` avaient disparu (`governance-major-auditors-trim`) mais `validate_strict()` survivait, rendant l'exit 1 inatteignable dans toute invocation documentée. Chemin retiré ; `--strict` reste un no-op CLI. Toléré en lecture des bases console.db legacy. | (n/a) |
| ~~`[PLAN_DIGEST_INSUFFICIENT]`~~ | **DÉPRÉCIÉ v7.0.0** — strict variants supprimés. Toléré en lecture des bases console.db legacy. | (n/a) |
| `[INVALID_ARG]` | Argument CLI invalide (regex `^\d+-\d+(:plan)?$` ou `^\d+$` non matché) | dev-*, sdd-full, dev-run, dev-plan, feat-validate STEP 1 |
| `[INVALID_MODE]` | Mode d'exécution incompatible (`:plan` invoqué alors qu'un plan existe ; etc.) | `build-and-loop.md §1.ter.3` (Partie B) |
| `[PROJECT_NOT_INIT]` | Fichier projet absent (`.csproj`/`package.json`/`pyproject.toml`/`build.gradle.kts`/`angular.json`) — arch n'a pas tourné | preflight.py B4, dev-*-strict STEP 4 |
| `[PLAN_REVIEW_GATE_SKIPPED]` | Plan-then-review gate bypassé (WARN informationnel) | sdd-full STEP 3.6 |
| `[STACK_SCAFFOLDING_MISSING]` | Arch n'a pas scaffoldé les entities attendues (DB→entities cohérence cassée) | arch Phase B, dev-backend STEP 5 (entities attendues au plan, schema chargé au STEP 3) |
| `[POC_OVERWRITE_REAL_US]` | `/sdd-poc` refuse d'écraser des US réelles pré-existantes par des pseudo-US POC (garde anti-perte) | sdd-poc.md STEP US |
| `[PO_HASH_PLACEHOLDER]` | Placeholder `Parent FEAT hash: sha256:PENDING` non résolu dans une US après génération (sentinel à résoudre par `resolve_po_hash_sentinel`/`resolve_us_hash_sentinel`) | po.md, us-generate.md, hook `SubagentStop` matcher=po |
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
| `[US_NOT_FOUND]` | Aucun fichier `workspace/us/{n}-{m}-*.md` matché (ou ambigu) | `set_us_status.py`, `validate_us_deps.py` et futurs scripts US |
| `[US_DEPS_CYCLE]` | Cycle détecté dans le graphe `## Dependencies` (Tarjan SCC ≥ 2) — bloquant | `validate_us_deps.py` exit 3 |
| `[US_DEPS_MISSING]` | Référence `## Dependencies` vers une US inexistante dans le scope FEAT/repo — bloquant | `validate_us_deps.py` exit 4 |
| `[US_DEPS_ORPHAN]` | US sans dépendant (no incoming edge) — informational (peut être death-code) | `validate_us_deps.py` (exit 0) |
| `[BREAKING_CLEANUP_FAILED]` | `mark_breaking_resolved.py` exit 3 (erreur fichier CLAUDE.md) | dev-* STEP 8.5 / 11.5 |
| `[DB_STRUCTURE_CHANGE_FORBIDDEN]` | Tentative (par un agent) de **modifier la structure d'une base de données existante** : DDL `DROP`/`ALTER`/`TRUNCATE`/`CREATE TABLE` sur base déjà provisionnée, `DELETE` de masse (sans `WHERE` ciblé), application de migration (`dotnet ef database update`, `Migrate()`, `EnsureCreated()` au runtime contre une base existante), ou tout SQL destructif. **STOP + escalade Tech Lead humain** — l'agent émet le DDL souhaité dans `workspace/db/migration-pending.sql` (jamais exécuté) et s'arrête. La création du **schéma initial d'un projet greenfield** (base neuve vide) reste permise via le scaffolding Database-First READ-ONLY d'arch ; ce qui est interdit, c'est de toucher la **structure d'une base existante**. DML classique (`SELECT`/`INSERT`/`UPDATE`) autorisé. **Exception unique (2026-06-30)** : une FEAT dont le nom de fichier contient « Flyway » autorise `flyway migrate` orchestré par `/sdd-full`/`/sdd-poc` (mécanisme de migration sanctionné, idempotent via `flyway_schema_history`) — cf. `library-and-stack.md §C.6`. Échec runner Flyway → `[INFRA_BLOCKED]` ; échec migrate → `[SCHEMA_MISMATCH]`. Cf. `library-and-stack.md §C`. | arch (Phase B), dev-* (migrations / code de démarrage) |
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

> ⚠️ **Famille à discrétion LLM — aucun émetteur déterministe** (audit M2,
> 2026-08-29). Aucun script, hook ou scan ne détecte ces classes : elles ne
> sont émises que si un agent (dev-*, arch) juge lui-même qu'il sort du scope
> et l'écrit dans son bloc ERROR. Ce tableau documente donc un **vocabulaire
> partagé**, pas une garantie d'application automatique — ne pas le lire
> comme un garde-fou outillé. Le ratchet
> `tests/test_error_class_emitters.py::KNOWN_UNEMITTED` suit l'écart ; y
> retirer une entrée le jour où un détecteur est écrit.

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
### 1.8 Parallélisme (file ownership / locks)

| Préfixe | Usage |
|---|---|
| `[LIBNAME_LOCK_HELD]` | Lock LibName détenu par autre agent (cf. `ownership.md §4`, Partie A) |
| `[LIBNAME_SIGNATURE_CONFLICT]` | DTO/Model partagé, signatures divergentes |
| `[LOCK_HELD]` | Lock générique cross-language (sdd_lib/file_locks.py) — `workspace/console/.status.lock`, etc. Alias générique de `[LIBNAME_LOCK_HELD]` pour contextes non-LibName |
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
