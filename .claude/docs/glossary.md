# SDD_Pro — Glossaire canonique

> **Source de vérité unique** du vocabulaire SDD_Pro (2026-05-19).
> Toute documentation framework (agents, rules, commands, docs/) doit
> utiliser les termes canoniques de ce glossaire. Les **alias dépréciés**
> seront retirés en v7.0.0 (cf. `ADR-20260519T163000-governance-major-vocab-consolidation`).
>
> Convention de langue : identifiants techniques en **anglais** (US, AC,
> SFD, FD, BR, ADR, classes d'erreur `[CATEGORY_*]`) ; documentation
> Tech Lead en **français**. Cf. `loader.yml` §"Convention de langue".

---

## 1. Artefacts métier

| Terme canonique | Définition | Source | Aliases dépréciés |
|---|---|---|---|
| **FEAT** | Spécification fonctionnelle d'une feature, fichier `workspace/input/feats/{n}-{Name}.md`. Porte les sections Functional Needs, Business Rules, Acceptance Criteria, Functional Deliverables, Actors, etc. | `templates/feat.template.md` | `feature`, `spec` |
| **US** (User Story) | Découpe d'une FEAT en flux utilisateur. `workspace/output/us/{n}-{m}-{Name}.md`. 1-6 par FEAT max (cf. `docs/principles/us-granularity.md`). | `templates/us.template.md` | `story`, `user-story` |
| **SFD-N** | *Specifiable Functional Deliverable* — ID stable d'une ligne `## Functional Needs` dans une FEAT. | `rules/ownership.md (Partie B §2)` | `Need-N`, `FN-N` |
| **FD-N** | *Functional Deliverable* — ID stable d'une ligne `## Functional Deliverables` dans une FEAT. | idem | `Deliverable-N` |
| **BR-N** | *Business Rule* — ID stable d'une ligne `## Business Rules` dans une FEAT. | idem | `Rule-N` |
| **AC-N** | *Acceptance Criterion* — ID stable d'une ligne `## Acceptance Criteria` dans une FEAT ou une US. | idem | `Criterion-N`, `Test-N` |
| **AC-UI-N** | AC spécifique à l'interface utilisateur (Given/When/Then orienté écran). | `agents/dev-frontend.md` | — |
| **ADR** | *Architecture Decision Record* — fichier atomique `workspace/output/.sys/.context/adrs/ADR-{ts}-{slug}.md` traçant 1 décision structurante. | `rules/ownership.md (Partie B §4)` | `decision-record` |
| **Mockup** | Maquette HTML statique déposée manuellement par UX Designer sous `workspace/input/ui/{n}-{m}-{Name}.html`. Lecture passive uniquement. | `CLAUDE.md §1` | `wireframe`, `HTML UI` |
| **Plan technique** | Frontmatter YAML + section `## Files` listant les fichiers à matérialiser pour 1 US. `workspace/output/plans/{n}-{m}-{Name}.{back\|front}.md`. | `rules/build-and-loop.md §7` | `tech-plan` |
| **Covers** | Champ d'une US qui référence les SFD/BR/AC/FD couverts dans la FEAT parente. | `docs/principles/us-granularity.md §5` | — |

---

## 2. Naming projet (à scaffolder)

| Terme canonique | Définition | Source | Aliases |
|---|---|---|---|
| **AppName** | Nom du projet frontend (ou fullstack). Littéral, case-sensitive. Token canonique du framework. | `stack.md ## Project Config` | `FrontendName` (alias actif, normalisé par `sdd_lib.project_config.normalize_project_aliases()` — cf. `ownership.md §1.bis`) |
| **BackendName** | Nom du projet backend. | idem | — |
| **LibName** | Nom du projet shared lib (DTOs cross-langage, opt-in via `LibStrategy: shared`). | idem | — |
| **AppNamespace** | Auto-dérivé de `AppName` depuis v6.10.2 (plus explicite). | auto | retiré en v7 |
| **BackendNamespace** | Auto-dérivé de `BackendName`. | auto | retiré en v7 |

---

## 3. Modes d'exécution

| Terme canonique | Définition | v7.0.0 |
|---|---|---|
| **Inline** | Mode dev-* par défaut : agent planifie inline + matérialise dans la même invocation. Modèle Opus 4.7. | conservé |
| **From-Plan** | Mode dev-* déclenché par présence d'un plan v1 ou v2 dans `workspace/output/plans/`. Modèle Opus 4.7 (les variants `dev-*-strict` Sonnet ont été supprimés v7.0.0, cf. `architecture.md §2-3` et `governance-major-auditors-trim`). | conservé (devient default si plan présent) |
| **Plan Only** | Génère uniquement le plan, ne matérialise pas le code. Invoqué par `/dev-plan {n}` (préféré) ou `:plan` suffix (déprécié v7). | `:plan` suffix retiré |
| **From-Plan Classic** | Variante Opus 4.7 de From-Plan (legacy v6). | **supprimé v7** |
| **Plan Only** vs **`:plan` suffix** | 2 façons d'invoquer la même chose. | suffix supprimé |

---

## 4. Gates (vérifications bloquantes)

| Terme canonique | Définition | Phase | Bloquant ? |
|---|---|---|---|
| **Readiness Gate** | Validation déterministe FEAT avant pipeline, `script validate_readiness.py`. Invoqué par `/feat-validate`. | 2.6 | oui (NO-GO → STOP) |
| **Plan-then-Review Gate** | Pause humaine après `/dev-plan` (avant `/dev-run`). Toujours actif en v7 (`PlanReviewDefault` retiré). | 3.5→4 | oui par défaut |
| **API Gate** | Tests intégration HTTP après dev-backend, avant dev-frontend (in-memory only, jamais DB réelle). Cf. `rules/build-and-loop.md`. | 4c | oui (RED bloque frontend) |
| **Manual Gate** | Pause interactive opt-in via `--manual-gates`. Affichée dans `workspace/console/`. | configurable | opt-in |
| **Coverage Gate** | Seuil `CoverageMin` du Project Config. Coverage < seuil → 🔴 RED `[QA_COVERAGE_GAP]`. | 5 | oui |
| **Audit Gate** | Verdict consolidé des auditors post-dev (parallèle dans `/dev-run` STEP 6.4). | 5 | oui sur 🔴 |

Forme rejetée : `gate` (générique) sans qualificatif → toujours préfixer.

---

## 5. Pipeline & phases

| Terme canonique | Définition | Source |
|---|---|---|
| **Pipeline** | Séquence des 5 phases SDD_Pro de FEAT → code livrable. | `CLAUDE.md §3` |
| **Phase** | Étape macro du pipeline (1=FEAT, 2=US, 3=Arch, 4=Dev, 5=QA). | `docs/workflow.md` |
| **STEP** | Étape interne d'un agent (e.g., dev-backend STEP 5.bis = capability detection). Toujours en majuscules dans la doc. | `agents/*.md` |
| **Batch** | Groupe d'US traitées en parallèle dans `/dev-run` (`MaxParallel: 3` US fullstack par batch). | `commands/dev-run.md` |
| **build_loop** | Boucle de correction post-build d'un agent dev-* sur erreurs `[BUILD_CORRECTIBLE]`. Max `BuildLoopMaxIter` itérations (défaut 3). | `rules/error-classification.md §3` |
| **preflight** | Validation HARD-GATE déterministe en amont de chaque agent dev-* (script `preflight.py`). | `rules/build-and-loop.md §1.bis` |
| **phase_planner** | Meta-orchestrateur déterministe qui décide quels auditors tourner par FEAT (script `phase_planner.py`). | `CLAUDE.md §4` |
| **run** | 1 exécution d'une commande slash (id `run_id` 12 chars hex). Persisté en `console.db` table `runs`. | `agents/sdd_state.py` |
| **invocation** | 1 appel d'un sub-agent dans un run. | informel |
| **event** | Entrée du log de runs, persisté en `console.db` table `events`. | `agents/sdd_state.py` |

---

## 6. Configuration

| Terme canonique | Définition | Hiérarchie |
|---|---|---|
| **Project Config** | Bloc `## Project Config` de `stack.md`. ~10 clés en v7. | per-projet, override final |
| **`config.team.yml`** | Policy team `~/.sdd/config.team.yml`. | per-machine |
| **`config.base.yml`** | Défauts framework `.claude/config.base.yml`. | framework |
| **Layered config** | Lecture mergée des 3 couches (project > team > base). Réalisée par `read_layered_config()`. | v6.7.1+ |
| **Active * Specs** | Sections `## Active Tech/UI/QA/Auth Specs` + `## Active Database` + `## Active Architecture Pattern` de `stack.md`. Sélection des stacks. | per-projet |
| **Capabilities** | Features opt-in mappées à des libs `onDemand` des `.libs.json` (e.g., `excel`, `pdf`, `redis-cache`). | `## Project Config Capabilities` |
| **Triggers** | Regex case-insensitive dans `.libs.json` qui matchent les ACs d'une US pour activer une capability. | `library-and-stack.md §1.bis` |
| **Profile** | Snapshot de `config.team.yml` sous `~/.sdd/profiles/{name}.yml`. Côté Tech Lead. | `/sdd-profile` |

---

## 7. Agents (taxonomie)

> **13 agents** en v7.0.0+ (sweep 2026-05-20 : `accessibility-auditor`,
> `performance-auditor`, `dashboard`, `dev-backend-strict`, `dev-frontend-strict`
> retirés ; `adversarial-reviewer` ajouté ; `complexity-router` ajouté
> v7.0.0+ opt-in). Tous **autonomes** (jamais de question utilisateur)
> sauf `elicitor` (dérogation `/feat-deepen`).

| Agent | Modèle | Rôle | Phase |
|---|---|---|---|
| `po` (Product Owner) | Sonnet 4.6 | FEAT → User Stories | 2 |
| `arch` (Architect) | Sonnet 4.6 | Bootstrap arch + DB + scaffolding | 3 |
| `dev-backend` | Opus 4.7 | Code serveur 1 US | 4 |
| `dev-frontend` | Opus 4.7 | Code client 1 US | 4 |
| `qa` | Sonnet 4.6 | Tests + coverage + quality scan | 5 |
| `elicitor` | Sonnet 4.6 | Élicitation FEAT (Pre-mortem, Red Team, etc.) | 1.5 |
| `constitutioner` | Sonnet 4.6 | Maintien `constitution.md` post-arch | 4 |
| `complexity-router` | Haiku 4.5 | Routage POC vs full vs critical (opt-in v7.0.0+) | 0 (pré-pipeline) |
| `adversarial-reviewer` | Sonnet 4.6 | Avocat du diable post-review (opt-in v7.2.0+) | 5+ |
| ~~`dashboard`~~ | — | **RETIRÉ v7.0.0** — INDEX.md généré par `index_adrs.py` (déterministe) |
| ~~`accessibility-auditor`~~ | — | **RETIRÉ v7.0.0** — remplacé par `axe-core` au CI projet |
| `code-reviewer` | Sonnet 4.6 | Review cross-fichier anti-patterns | 5 |
| `security-reviewer` | Sonnet 4.6 | Scan OWASP Top 10 (mode `scan`). Mode `threat-model` retiré v7.0.0 → template humain | 5 |
| ~~`performance-auditor`~~ | — | **RETIRÉ v7.0.0** — remplacé par Lighthouse CI + wrk/k6 au CI projet |
| `spec-compliance-reviewer` | Sonnet 4.6 | Vérification AC-par-AC du code livré | 5 |
| `arch-reviewer` | Sonnet 4.6 | Conformité pattern d'archi (MVC/DDD) | 5 |
| ~~`dev-backend-strict`, `dev-frontend-strict`~~ | — | **RETIRÉ v7.0.0** — variants Sonnet supprimés, `PlanCacheStrict` est DEPRECATED no-op |

**Terminologie cross-agents** :
- **Auditor** : agent post-dev qui produit un rapport sans modifier le code (accessibility, code, security, performance, spec-compliance, arch).
- **Reviewer** : synonyme d'auditor (à fusionner en v7 — garder **auditor**).
- **Scanner** : sous-mode d'un auditor (e.g., `security-reviewer --mode scan`). N'est pas un type d'agent en soi.

---

## 8. Concepts opérationnels

| Terme canonique | Définition | Source |
|---|---|---|
| **Anti-derive** | Discipline qui interdit aux agents de générer du code/des fichiers hors du scope explicite de l'US/FEAT. | `docs/conventions.md §1` |
| **Drift** | Divergence entre 2 sources qui devraient être synchronisées (e.g., `loader.yml` vs agents `.md`). | informel |
| **Load-bearing** | Mécanisme load-bearing = strictement nécessaire pour la robustesse industrielle ; sa violation casse silencieusement le système. | `rules/ownership.md` |
| **Scaffolding** | Bootstrap projet (csproj/package.json/etc.) + entities + structure directory par agent `arch` Phase A/B. | `agents/arch.md` |
| **SSoT** | *Single Source of Truth* — fichier ou table unique faisant autorité sur un concept. | informel |
| **Source-first discipline** | Tout bug code = trou dans MD source ; patcher SPEC/US/plan/stack MD AVANT le code. | `docs/principles/source-first.md` |
| **Backend-first gated workflow** | dev-backend → API Gate → dev-frontend (jamais en parallèle depuis 2026-05-07). | `rules/build-and-loop.md` |
| **File ownership** | Matrice qui désigne UN propriétaire unique par fichier pour éviter race conditions parallèles. | `rules/ownership.md §1` |
| **Lib lock** | Verrou atomique par entité pour le projet shared `LibName` (procédure `acquire_libname_lock.py`). | `rules/ownership.md §4` |
| **Idempotence** | Une commande relancée 2× avec mêmes inputs produit le même résultat sans effet de bord cumulé. | `docs/conventions.md §2` |
| **Selective read** | Lecture sélective : un agent ne lit que les artefacts strictement nécessaires à son US (1 fichier US, pas la FEAT entière). | `CLAUDE.md §1` |
| **Strict mode** | (retiré v7.0.0) Variant Sonnet 4.6 des dev-* qui consommait un plan v2 strict-ready. Tous les plans (v1 et v2) sont désormais matérialisés par les agents canoniques Opus 4.7. | `archive/v7-design-superseded/DESIGN-FROMPLAN-STRICT.md` |
| **Constitution** | Fichier `workspace/output/.sys/.context/constitution.md` partagé entre agents pour cohérence sémantique cross-FEAT (glossaire local, acteurs, ADRs index). | `rules/ownership.md (Partie B)` |
| **Checkpoint** | Mécanisme de reprise post-crash via hashing input des phases. | v6.6.2+ |

---

## 9. Telemetry & runtime

| Terme canonique | Définition | Localisation |
|---|---|---|
| **Token telemetry** | Capture post-call des tokens consommés par sub-agent. | `console.db` table `token_usage` |
| **Context budget** | Estimation pré-call de la taille (KB) lue par un agent. Comparée à `DEFAULT_BUDGETS` par `context_budget.py`. | `console.db` table `context_budget` |
| **Ledger** | Historique append-only (utilisé pour event log + token usage avant v6.10). | retiré v6.10 (tout en DB) |
| **console.db** | SQLite WAL central, 24 tables, source de vérité runtime depuis v6.10. | `workspace/output/db/console.db` |
| **status.json** | Fichier `workspace/console/status.json` (gates UI). Reste un dual-write avec `console.db` table `gates`. | console UI |

---

## 10. QA & verdicts

| Terme canonique | Définition | Échelle |
|---|---|---|
| **Verdict** | Décision finale d'un agent QA/auditor : 🟢 GREEN, 🟡 WARN, 🔴 RED. | tri-valeur |
| **Severity** | Sévérité d'une issue : `critical > serious > moderate > minor > info` (+ `blocker` pour cas terminal). | 5-6 niveaux |
| **Hard-blocking** | Classe d'erreur qui force 🔴 RED quel que soit `*FailOn` configuré (e.g., `[SEC_SQL_INJECTION]`). | 8 classes SEC + 2 REVIEW + 1 PERF |
| **FailOn threshold** | Seuil de sévérité qui transforme un verdict en 🔴 RED. Configurable par auditor (`*FailOn` keys). | sera unifié en `AuditorsFailOn` v7 |
| **Threshold** | Synonyme de FailOn (à fusionner v7 — garder **FailOn**). | — |
| **Quality scan** | Analyse déterministe Sonar-like par `quality_scan.py`. | `console.db` table `qa_quality` |
| **API Gate verdict** | Résultat des tests intégration HTTP (cf. §4 Gates). | `console.db` table `qa_api_tests` |

Formes rejetées (à éliminer v7) : `status` (ambigu — `Status:` est un champ frontmatter US), `result`, `outcome`.

---

## 11. Erreurs (classes d'erreur)

Format canonique : `[CATEGORY_SUBCATEGORY]` (UPPER_SNAKE_CASE).

**~110 classes** définies dans `rules/error-classification.md`. Catégories principales :

| Préfixe | Domaine | Exemples |
|---|---|---|
| `[BUILD_*]` | Compilation / lint / type | `BUILD_CORRECTIBLE`, `BUILD_BLOCKING`, `BUILD_LOOP_EXHAUSTED` |
| `[STACK_*]` | Configuration stack | `STACK_MALFORMED`, `STACK_LIBRARY_MISSING`, `STACK_COMBO_INVALID` |
| `[QA_*]` | Tests + coverage | `QA_TEST_FAILED`, `QA_COVERAGE_GAP`, `QA_FRAMEWORK_MISSING` |
| `[SEC_*]` | Sécurité OWASP | `SEC_SQL_INJECTION`, `SEC_BROKEN_AUTHZ`, `SEC_JWT_MISCONFIG` |
| `[A11Y_*]` | Accessibilité WCAG | `A11Y_MISSING_ALT`, `A11Y_INPUT_NO_LABEL`, `A11Y_HEADING_SKIP` |
| `[PERF_*]` | Performance | `PERF_LCP_TOO_HIGH`, `PERF_API_P95_HIGH`, `PERF_BUNDLE_TOO_LARGE` |
| `[REVIEW_*]` | Code review | `REVIEW_SECRETS_HARDCODED`, `REVIEW_ANTI_PATTERN_N_PLUS_ONE` |
| `[ARCH_*]` | Pattern d'archi | `ARCH_PATTERN_VIOLATION`, `ARCH_LAYER_BYPASS`, `ARCH_ADR_DRIFT` |
| `[SPEC_*]` | Spec compliance | `SPEC_AC_NOT_VERIFIED`, `SPEC_AC_PARTIAL` |
| `[FILE_*]` | File ownership | `FILE_OWNERSHIP`, `FILE_OWNERSHIP_NESTED` |
| `[US_*]` | User Story state | `US_STATUS_INVALID`, `US_DEPS_CYCLE`, `US_DEPS_MISSING` |
| `[PLAN_*]` | Plan validation | `PLAN_STALE`, `PLAN_INVALID`, `PLAN_NOT_STRICT_READY` |
| `[CONFIG_*]` | Config layered | `CONFIG_SECURITY_DOWNGRADE` |
| `[NETWORK]`, `[AUTH]`, `[PERMISSION]`, `[NOT_FOUND]`, `[TIMEOUT]`, `[DISK]`, `[ENV_MISSING]` | Runtime/infra | génériques |
| `[UNKNOWN]` | Erreur non classifiable | fallback |

> v7.0.0 : `rules/error-classification.md` → `sdd_lib/error_classes.py` (dict Python). Cf. `ADR-20260519T153000-governance-major-prompts-trim §3`.

---

## 12. Storage layout

| Path | Rôle | Hand-edited ? |
|---|---|---|
| `workspace/input/feats/{n}-*.md` | FEATs (entrée Tech Lead) | ✅ |
| `workspace/input/ui/{n}-{m}-*.html` | Mockups UX | ✅ (UX) |
| `workspace/input/stack/stack.md` | **SSoT primaire projet** (v7) | ✅ |
| `workspace/output/us/*.md` | User Stories générées | ❌ (agent po) |
| `workspace/output/plans/*.md` | Plans techniques | ❌ (agent dev-*) |
| `workspace/output/src/{Project}/...` | Code applicatif généré | ❌ (agent dev-*) |
| `workspace/output/db/console.db` | SQLite runtime SSoT | ❌ (machine) |
| `workspace/output/.sys/.context/constitution.md` | Glossaire projet + ADRs index | ❌ (agents) |
| `workspace/output/.sys/.context/adrs/*.md` | ADRs atomiques | ❌ (agents append) |
| `workspace/output/.sys/.validation/{n}-*.{md,json}` | Rapports validation/auditors | ❌ (auditors) |
| `workspace/output/qa/feat-{n}/*` | Reports QA (markdown lisible humain) | ❌ (qa + auditors) |
| `workspace/console/` | UI status + index | dev humain |

---

## 13. Stack categories

| Catégorie | Path | Compte v6.10 |
|---|---|---|
| **backend** | `.claude/stacks/backend/*.md` | 4 🟢 |
| **frontend** | `.claude/stacks/frontend/*.md` | 4 🟢 |
| **ui** | `.claude/stacks/ui/*.md` | 3 🟢 |
| **fullstack** | `.claude/stacks/fullstack/*.md` | 6 🟡 |
| **mobiles** | `.claude/stacks/mobiles/*.md` | 2 🟡 |
| **qa** | `.claude/stacks/qa/*.md` | 7 🟢 |
| **auth** | `.claude/stacks/auth/*.md` | 2 🟢 |
| **archi** | `.claude/stacks/archi/*.md` | 1 🟢 + 2 🟡 |

| Validation marker | Sens |
|---|---|
| 🟢 reference | Combo end-to-end validé |
| 🟡 Phase 2 | Disponible mais expérimental |

**Combos validés** : `dotnet-minimalapi × react × shadcn`, `kotlin-spring-boot × react × shadcn`.

---

## 15. Roles

| Rôle canonique | Définition |
|---|---|
| **Tech Lead** | Humain qui pilote SDD_Pro. Édite stack.md, FEATs, arbitre les `STOP + ERROR`, exécute les commandes slash. Unique vraie autorité hors agents. |
| **Product Owner (PO)** | Rôle parfois cité comme synonyme du Tech Lead en phase 2. **À ne pas confondre** avec l'agent `po` (qui s'appelle ainsi par historique mais sert l'auteur de la FEAT). |
| **UX Designer** | Humain qui dépose les mockups HTML statiques. Aucun outil SDD_Pro côté UX (lecture passive). |
| **Mainteneur** | Approbateur d'ADR governance-* (cf. `VERSIONING.md §6` : 2 approbations requises pour MAJOR/MINOR post-freeze). |

---

## 16. Aliases dépréciés (consolidation v7.0.0)

Liste des termes à éliminer en v7.0.0 — préférer la forme canonique de la colonne droite.

| Forme à éliminer | Remplacement canonique | Source ADR |
|---|---|---|
| `derive` (substantif) | **drift** | vocab-consolidation |
| `FrontendName` (raw) | **AppName** (token canonique) — `FrontendName` reste accepté comme alias et normalisé par `sdd_lib.project_config.normalize_project_aliases()` ; à privilégier dans `stack.md` pour distinguer du backend (cf. `ownership.md §1.bis`) | config-ssot |
| `reviewer`, `scanner` (générique) | **auditor** | vocab-consolidation |
| `verdict` vs `status` vs `result` | **verdict** (qa/auditors), **Status:** (US frontmatter) | vocab-consolidation |
| `phase` vs `step` (minuscule) | **Phase** (macro pipeline), **STEP** (intra-agent) | vocab-consolidation |
| `gate` (sans qualificatif) | toujours préfixer : **API Gate**, **Readiness Gate**, **Manual Gate**, etc. | vocab-consolidation |
| `library`, `package` | **lib** | vocab-consolidation |
| `wireframe`, `HTML UI` | **mockup** | vocab-consolidation |
| `invocation`, `call` (agent) | **run** (1 exécution slash command) ou **invocation** (sub-agent dans 1 run) — disambigué | vocab-consolidation |
| `level`, `criticality` | **severity** | vocab-consolidation |
| `source de vérité`, `canonical` | **SSoT** | vocab-consolidation |
| `From-Plan Classic` | **From-Plan** (mode unique, Sonnet) | flags-trim |
| `:plan` suffix dev-* | `/dev-plan {n}-{m}` | flags-trim |
| `## Active App Type` block | auto-détection | config-ssot |
| `AppNamespace:`, `BackendNamespace:` explicites | auto-dérivés | config-ssot |
| `ArchitecturePattern: X` keyvalue | bullet `- .claude/stacks/archi/x.md` | config-ssot |
| `threshold` (sauf `CoverageMin`, `A11yThreshold`) | **FailOn** | flags-trim |

---

## 17. Pointers

- `@.claude/CLAUDE.md` — entrée slim (170 lignes)
- `@.claude/docs/architecture.md` — vision agents/stacks
- `@.claude/docs/workflow.md` — détail phases
- `@.claude/docs/conventions.md` — anti-derive, idempotence, parallélisme
- `@.claude/docs/CHANGELOG.md` — notes par version (consolidé 2026-06-06)
- `@.claude/rules/` — 9 règles opérationnelles
- `@.claude/docs/VERSIONING.md` — politique SemVer + freeze
- `ADR-20260519T120000-governance-major-auditors-trim.md`
- `ADR-20260519T133000-governance-major-config-ssot.md`
- `ADR-20260519T143000-governance-major-flags-trim.md`
- `ADR-20260519T153000-governance-major-prompts-trim.md`
- `ADR-20260519T163000-governance-major-vocab-consolidation.md` *(à écrire ci-après)*

---

## 18. Maintenance

**Règle** : tout nouvel agent / rule / command / stack ajouté DOIT mettre à jour ce glossaire (sections §7, §11, §13 selon nature) et **ne PAS inventer** de nouveau terme synonyme d'un terme existant. Audit : `audit_vocab_drift.py` (à créer v7) qui grep le code/docs pour les formes dépréciées.

**Cible v7.0.0** : ce glossaire devient un **livre fermé** (~220 termes max). Tout nouveau terme exige un ADR `governance-vocab-{slug}` justifiant l'ajout.
