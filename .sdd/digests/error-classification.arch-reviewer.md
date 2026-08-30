# Error Classification — digest for `arch-reviewer`
> **GENERATED — do not edit.** Slice of `@.claude/rules/error-classification.md` for the `arch-reviewer` agent (audit 2026-06-12, block 5). Regenerate via `python .sdd/python/sdd_admin/sync_error_class_digests.py`.
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
| `[REVIEW_SOURCES_MISSING]` | Sources de review absentes (code matérialisé / rapports auditors introuvables au démarrage de `/sdd-review`) | WARN |

**Two-stage auditor gate** (`auditor-orchestration.md §4.1-§4.2`, appliqué
par les orchestrateurs `/sdd-full` et `/dev-run` STEP 6.4) :

| Préfixe | Sens | Bloquant |
|---|---|:---:|
| `[AUDITOR_RUNTIME_ERROR]` | Verdict JSON d'un auditor illisible au moment où l'orchestrateur two-stage lit `summary.verdict` (`workspace/.sys/.validation/{n}-{kind}.json` absent — agent STOP runtime, ou `.json` supprimé faute de `--keep-json` à l'ingest, cf. FWD-C1 audit 2026-06-12). Gate stricte : verdict forcé `🔴 RED`, jamais de fallback silencieux. | OUI — **exception `arch-reviewer`** : WARN seulement (jamais hard-blocking par design, `ArchReviewFailOn: serious` défaut) |

**Hooks préflight & gates runtime** (PreToolUse/SubagentStop — déclarés ici
pour la réciprocité émetteurs↔taxonomie, audit 2026-06-12) :

| Préfixe | Sens | Bloquant |
|---|---|:---:|
| `[STACK_COMBO_INVALID]` | Combo stack (back+front+ui+auth) invalide | OUI (`validate_stack_combo.py` exit 3, hook `preflight_stack_combo`) |
| `[STACK_COMBO_UNTESTED]` | Combo non testé sans `SDD_ALLOW_UNTESTED_COMBO=1` | OUI (hook `preflight_stack_combo`) |
| `[STACK_MULTI_INCOHERENT]` | Stacks multiples incohérents détectés post-write | WARN (`validate_stack_consistency.py`) |
| `[FRAMEWORK_PROTECTED]` | Tentative d'écriture sur un fichier framework protégé (`.claude/**`) | OUI (hook `protect_framework`) |
| `[ENV_BYPASS_BLOCKED]` | Tentative de bypass d'une protection via env var interdite | OUI (hook `block_env_bypass`) |
| `[GLOB_SCOPE_TOO_BROAD]` | Glob non borné (token explosion) | WARN (strict via `SDD_GLOB_SCOPE_STRICT=1`, hook `preflight_glob_scope`) |
| `[TELEMETRY_UNAVAILABLE]` | `console.db` télémétrie indisponible au precheck coût | info, fail-open (hook `preflight_cost_cap`) |
| `[PRICING_UNKNOWN]` | Modèle sans pricing connu (ni canonical `pricing.py` ni provider YAML, `model` NULL inclus) — coût cappé sur `FALLBACK_PRICING` Sonnet, risque under-count 5×. **Périmètre du blocage = les agents du registre SDD** (`.sdd/agents/*.md`, projection du loader) ; un usage attribué à un subagent hors registre (built-ins du harnais) est compté dans le total mais rapporté en WARN, jamais bloquant (audit C-1 2026-08-30). Un usage non attribué (`unknown`, nom d'événement de hook) reste fail-closed. | OUI en CI, WARN interactif (hook `preflight_cost_cap`, audit R2 2026-07-26). Bypass : `SDD_ALLOW_UNKNOWN_PRICING=1` |
| `[SECRET_PROVIDER_LEAK_RISK]` | Secrets détectés dans `workspace/stack/stack.md` alors que provider actif est non-Anthropic (retention par défaut : OpenAI 30j, Google 55j, Moonshot inconnu) | WARN (jamais bloquant — hook `preflight_secret_scan`, audit R5 2026-07-26). Bypass : `SDD_ALLOW_SECRET_TO_PROVIDER=1` |
| `[AGENT_REMOVED_V7]` | Spawn d'un agent retiré en v7.0.0 (a11y/perf/dashboard/*-strict) | OUI (hook `preflight_agent_budget`) |
| `[BUDGET_PRECHECK_TIMEOUT]` | Timeout du precheck budget agent | info, fail-open (hook `preflight_agent_budget`) |
| `[PACK_UNUSABLE]` | Pack de contexte déclaré dans `loader.yml` (`reads:`) mais inutilisable : absent ou périmé (empreinte des sources changée). Une **ERREUR, pas un warning** — un pack manquant pèse 0 octet et produirait un vert trompeur sur un agent privé de contexte de stack. FIX : `python -m sdd_scripts.build_context_pack --agent {agent}` (le hook `preflight_agent_budget` reconstruit le pack avant chaque spawn). | OUI (gate `context_budget.py`, audit 2026-08-28) |

> Réciprocité enforced par `tests/test_error_classification_reciprocity.py` :
> toute classe émise en `CAUSE: [X]` DOIT figurer dans cette taxonomie.

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
