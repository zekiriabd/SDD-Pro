# Error Classification — digest for `dev-frontend`
> **GENERATED — do not edit.** Slice of `@.claude/rules/error-classification.md` for the `dev-frontend` agent (audit 2026-06-12, block 5). Regenerate via `python .sdd/python/sdd_admin/sync_error_class_digests.py`.
>
> Contains the §0 quick-ref (full 16-family map) + this agent's families + the universal format/loop sections. For a class OUTSIDE this slice, §0 names its family — Read the full file on-demand (rule `build-and-loop.md §8`).
## 0. Quick reference — 16 familles (191 classes)

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
| §1.14 | **Tooling/Governance** (`[SCAN_*]`/`[DISCOVER_*]`/`[CHECKPOINT_*]`/`[CONFIG_*]`/`[PROFILE_*]`/`[DRIFT_*]`/`[ARCH_*]`/`[REVIEW_*]`/`[STACK_COMBO_*]`/`[FRAMEWORK_PROTECTED]`/`[ENV_BYPASS_BLOCKED]`/`[PRICING_UNKNOWN]`/`[SECRET_PROVIDER_LEAK_RISK]`/hooks préflight) | 34 | scripts mono-shot + hooks | mostly info, qq. bloquantes |
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

**Chat** (compressé — 1L succès, 2L max erreur) :
```
🔴 {agent} {n}-{m} — {résumé}
CAUSE: [{CLASS}] {détail 1L} → {pointer fichier rapport}
```

**Rapport** (3 lignes, persisté en base `console.db` ou stderr ; ex-`workspace/qa/...`, `.sys/.validation/...`) :
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
## 5. Règle mentale

**"Pas de bloc ERROR sans préfixe `[CLASS]`. Si rien ne matche → `[UNKNOWN]`."**

Discipline qui permet à `build_loop` de décider mécaniquement, aux
scripts de classer sans LLM, au dashboard de visualiser par cause-racine.
