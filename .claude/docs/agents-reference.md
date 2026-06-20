# 🤖 Agents Reference

12 specialized AI agents power the SDD_Pro pipeline. Each card lists the role, model, triggers, inputs/outputs, tools and verdicts. **Read this when you need to know "what does agent X do" or "what files does it touch"**.

| Quick legend |
|---|
| 🟢 GREEN / 🟡 WARN / 🔴 RED = canonical verdict palette |
| `model: Sonnet 4.6` = cheaper, fast — used for orchestration + auditors |
| `model: Opus 4.7` = stronger reasoning — used only for `dev-backend` + `dev-frontend` |
| **Hard-blocking** classes force 🔴 RED regardless of severity thresholds |

---

## Core agents (4)

The agents that turn FEAT specs into running code.

### `po`

| Field | Value |
|---|---|
| **Role** | Découpe une FEAT en User Stories structurées (cible 1-3, max 6) avec traçabilité 100% SFD/BR/AC/FD. |
| **Model** | Sonnet 4.6 |
| **Phase** | 2 (US generation) |
| **Triggers** | `/us-generate {n}`, `/sdd-full {n}`, `/feat-generate` (pipeline) |
| **Inputs (Reads)** | `workspace/input/feats/{n}-*.md`, `.claude/templates/us.template.md`, `constitution.md` |
| **Outputs (Writes)** | `workspace/output/us/{n}-{m}-*.md` (1-6 fichiers), `constitution.md §2/§3` (append-only) |
| **Tools** | Read, Write, Edit, Glob, Grep |
| **Verdicts** | ERROR-only — succès = US écrites + traçabilité 100% |
| **Hard-blocking** | `[FEAT_NOT_FOUND]`, `[FEAT_AMBIGUOUS]`, `[GRANULARITY_VIOLATION]`, `[TRACEABILITY_GAP]` |

**One-liner** : Transforme une FEAT en User Stories atomiques avec couverture exhaustive des IDs stables.
**Quand l'invoquer** : automatique via `/sdd-full`. Manuel via `/us-generate {n}` après modification de FEAT.
**Limitation** : ne lit ni stack.md ni mockups HTML — n'estime pas la faisabilité technique.

---

### `arch`

| Field | Value |
|---|---|
| **Role** | Bootstrap projets vides + propagation `stack.md` vers configs natives + scaffolding DB Database-First (READ-ONLY). |
| **Model** | Sonnet 4.6 |
| **Phase** | 3 (bootstrap + DB scaffolding) |
| **Triggers** | `/arch-init`, `/sdd-full {n}`, `/dev-run {n}` |
| **Inputs (Reads)** | `stack.md`, `.claude/stacks/{cat}/{active}.md`, `.claude/templates/adr.template.md`, `constitution.md` |
| **Outputs (Writes)** | `*.sln`, `src/{App,Backend,Lib}Name/`, `db/schema.{json,md,diff.md}`, `Entities/`, `CLAUDE.md` (per-project), ADRs |
| **Tools** | Read, Write, Edit, Glob, Grep, Bash |
| **Verdicts** | ERROR-only — idempotent (skip si projet initialisé) |
| **Hard-blocking** | `[STACK_MALFORMED]`, `[NETWORK]`, `[AUTH]`, `[PERMISSION]`, `[ENV_MISSING]`, `[DEP_MISSING]`, `[STACK_LIBRARY_VULNERABLE]` |

**One-liner** : Prépare l'ossature complète (solution, projets vides, configs, entities DB) avant les dev-*.
**Quand l'invoquer** : automatique via `/sdd-full`/`/dev-run`. Manuel via `/arch-init` ou `/dev-run --rebuild-arch`.
**Limitation** : aucun code applicatif (Pages/Services/Endpoints) — strictement scaffolding.

---

### `dev-backend`

| Field | Value |
|---|---|
| **Role** | Pour UNE US, planifie + génère le code serveur (Services, DTOs, Endpoints, Mappers, Program.cs). |
| **Model** | **Opus 4.7** |
| **Phase** | 4 (génération code serveur, parallèle 1/US) |
| **Triggers** | `/dev-backend {n}-{m}`, `/dev-run {n}`, `/sdd-full {n}` |
| **Inputs (Reads)** | `us/{n}-{m}-*.md`, `ui/{n}-{m}-*.html` (passif), `src/{BackendName}/CLAUDE.md`, `stack.md`, stacks backend/auth |
| **Outputs (Writes)** | `src/{BackendName}/{Services,Endpoints,DTOs,Mappers}/`, `Program.cs` (augment), `plans/{n}-{m}-*.back.md` |
| **Tools** | Read, Write, Edit, Glob, Grep, Bash, Skill |
| **Verdicts** | Build vert (exit 0) OK / `build_loop` itère max `BuildLoopMaxIter` |
| **Hard-blocking** | `[BUILD_BLOCKING]`, `[BUILD_LOOP_EXHAUSTED]`, `[STACK_LIBRARY_MISSING]`, `[FILE_OWNERSHIP_NESTED]`, `[LIBNAME_LOCK_HELD]`, `[QA_OWNERSHIP_VIOLATION]`, `[BUILD_LOOP_COST_EXCEEDED]` |

**One-liner** : Matérialise le code serveur d'UNE US selon le plan inline + stack backend actif.
**Quand l'invoquer** : automatique via `/dev-run`. Manuel via `/dev-backend {n}-{m}` pour fix ciblé.
**Limitation** : exit silencieux si US frontend-only ; n'écrit aucun test (QA hors scope).

---

### `dev-frontend`

| Field | Value |
|---|---|
| **Role** | Pour UNE US + mockup HTML, planifie + génère le code client (Pages, Components, theme.css) via mapping HTML→DS. |
| **Model** | **Opus 4.7** |
| **Phase** | 4 (génération code client, parallèle 1/US, post-API Gate) |
| **Triggers** | `/dev-frontend {n}-{m}`, `/dev-run {n}`, `/sdd-full {n}` |
| **Inputs (Reads)** | `us/{n}-{m}-*.md`, `ui/{n}-{m}-*.html`, `src/{AppName}/CLAUDE.md`, stacks frontend/ui/auth |
| **Outputs (Writes)** | `src/{AppName}/{Pages,Components,Layouts}/`, `theme.css`, `Program.cs`, `plans/{n}-{m}-*.front.md` |
| **Tools** | Read, Write, Edit, Glob, Grep, Bash, Skill |
| **Verdicts** | Build vert + fidelity check post-build (libellés HTML présents dans markup) |
| **Hard-blocking** | `[BUILD_BLOCKING]`, `[UI_FIDELITY_GAP]`, `[UI_TOKEN_VIOLATION]`, `[FRONTEND_BACKEND_CONTRACT_GAP]`, `[FILE_OWNERSHIP_NESTED]` |

**One-liner** : Matérialise le code client d'UNE US en traduisant le HTML mockup vers les primitives du DS actif.
**Quand l'invoquer** : automatique via `/dev-run` après API Gate verte. Manuel pour fix UI ciblé.
**Limitation** : exit silencieux si US backend-only ; HTML traduit (jamais recopié) ; aucun test.

---

## Support agents (3)

The agents that prepare the ground or enrich the spec.

### `elicitor`

| Field | Value |
|---|---|
| **Role** | Enrichit une FEAT via 5 techniques (Pre-mortem, First Principles, Red Team, Stakeholder Mapping, Inversion). |
| **Model** | Sonnet 4.6 |
| **Phase** | 1.5 (élicitation, optionnelle) |
| **Triggers** | `/feat-deepen {n} [--quick]` |
| **Inputs (Reads)** | `workspace/input/feats/{n}-*.md`, `.claude/templates/risks-assumptions.template.md`, `constitution.md` |
| **Outputs (Writes)** | FEAT (append 5 sections : Risques/Hypothèses/Cas Limites/RACI/Modes Défaillance), `constitution.md §7` |
| **Tools** | Read, Write, Edit, Glob, Grep, **AskUserQuestion** (dérogation no-question §3.bis) |
| **Verdicts** | ERROR-only — succès = FEAT enrichie |
| **Hard-blocking** | `[FEAT_NOT_FOUND]`, `[ELICITOR_GAP]` (WARN par défaut, NO-GO si `ElicitorGapMode: strict`) |

**One-liner** : Force le PO à expliciter risques et cas limites avant que les dev-* matérialisent.
**Quand l'invoquer** : manuellement entre `/feat-generate` et `/sdd-full` pour FEATs critiques.
**Limitation** : ne touche ni US ni stack ; les items doivent être mappés sur ACs (boucle elicitor).

---

### `constitutioner`

| Field | Value |
|---|---|
| **Role** | Crée ADRs (timestamp atomique + rand4) + met à jour constitution.md §1/§4/§6 + régénère ADRs INDEX.md. |
| **Model** | Sonnet 4.6 |
| **Phase** | 3.5 (post-arch Phase B, externalisé depuis 2026-05-13) |
| **Triggers** | spawn par `/arch-init STEP 3.5` via sentinel disque `.sys/.state/arch-ready-for-constitutioner.flag` |
| **Inputs (Reads)** | `stack.md`, `constitution.md`, ADRs existants (idempotence), template ADR |
| **Outputs (Writes)** | `adrs/ADR-{timestamp}-{rand4}-{slug}.md`, `constitution.md` (Edit §1/§4/§6), `adrs/INDEX.md` |
| **Tools** | Read, Write, Edit, Glob, Grep, Bash |
| **Verdicts** | ERROR-only — skip silencieux si constitution.md absent |
| **Hard-blocking** | héritage taxonomie `[CLASS]` standard ; ne décide rien (reflète stack.md) |

**One-liner** : Reflète sur disque les décisions actées du stack en ADRs traçables.
**Quand l'invoquer** : automatique post-arch ; jamais manuellement.
**Limitation** : strictement exécutif — n'invente aucune décision, skip si projet pré-SDD_Pro v3.

---

### `qa`

| Field | Value |
|---|---|
| **Role** | Génère tests unitaires (back+front) + parse coverage + quality scan déterministe pour une FEAT. |
| **Model** | Sonnet 4.6 |
| **Phase** | 5 (tests + coverage + quality) |
| **Triggers** | `/qa-generate {n}`, `/sdd-full {n}` |
| **Inputs (Reads)** | `us/{n}-*.md`, `src/{Backend,App,Lib}Name/**` (read-only), stacks QA, `db/schema.json` |
| **Outputs (Writes)** | `*.Tests/`, `__tests__/`, `*.test.ts`, `qa/feat-{n}/{report.md,coverage.json,quality.json}` |
| **Tools** | Read, Write, Edit, Glob, Grep, Bash |
| **Verdicts** | 🟢 GREEN / 🟡 WARN / 🔴 RED selon `coverage_lines_pct >= CoverageMin` + tests passés (per-stack + global) |
| **Hard-blocking** | `[QA_TEST_FAILED]`, `[QA_COVERAGE_GAP]`, `[QA_FRAMEWORK_MISSING]`, `[QA_OWNERSHIP_VIOLATION]`, `[QA_PRECONDITION_FAILED]` |

**One-liner** : Garantit la couverture testée du code généré, sans jamais modifier la production.
**Quand l'invoquer** : automatique via `/sdd-full`. Manuel via `/qa-generate {n}` ou `QAMode: manual`.
**Limitation** : strictement read-only sur code prod ; aucune review LLM "trouve les bugs".

---

## Auditor agents (5)

Cross-file post-dev reviewers — each with a distinct angle. **5 verdicts → consolidated by `/sdd-review`**.

### `code-reviewer`

| Field | Value |
|---|---|
| **Role** | Review cross-fichier post-dev (anti-patterns stack, layer violations, contract drift front↔back, smells). |
| **Model** | Sonnet 4.6 |
| **Phase** | 6.4 batch parallèle (post-dev, pré-qa) |
| **Triggers** | `/sdd-full {n}`, `/sdd-review {n}`, `/dev-run` STEP 6.4 (si `CodeReviewMode: full`) |
| **Inputs (Reads)** | `stack.md`, FEAT+US, CLAUDE.md projets, stacks backend/frontend §1.3, `plans/{n}-*.{back,front}.md`, code `src/**` |
| **Outputs (Writes)** | `.sys/.validation/{n}-code-review.{md,json}` |
| **Tools** | Read, Write, Glob, Grep, Bash |
| **Verdicts** | 🟢 / 🟡 / 🔴 selon `CodeReviewFailOn` (défaut `critical`) |
| **Hard-blocking** | `[FRONTEND_BACKEND_CONTRACT_GAP]` (override systématique RED) |

**One-liner** : Catch les bugs cross-fichier que ni build vert ni `quality_scan.py` ne voient.
**Quand l'invoquer** : automatique via `/sdd-full`/`/sdd-review`. Manuel pour audit ciblé.
**Limitation** : strictement read-only ; ne corrige pas ; ne duplique pas `quality_scan.py` (TODO/magic/console.log).

---

### `security-reviewer`

| Field | Value |
|---|---|
| **Role** | Scan OWASP Top 10 2021 du code généré (secrets, injections, XSS, authz, crypto, CORS, JWT, SSRF). |
| **Model** | Sonnet 4.6 |
| **Phase** | 6.5 batch (mode `scan` post-dev ; mode `threat-model` retiré v7.0.0) |
| **Triggers** | `/sdd-full {n}`, `/sdd-review {n}`, `/dev-run` (si `SecurityMode: full`) |
| **Inputs (Reads)** | `stack.md`, FEAT+US, CLAUDE.md projets, stacks backend/frontend, code `src/**`, `{n}-code-review.json` (dé-dup) |
| **Outputs (Writes)** | `.sys/.validation/{n}-security-scan.{md,json}` |
| **Tools** | Read, Write, Glob, Grep, Bash |
| **Verdicts** | 🟢 / 🟡 / 🔴 selon `SecurityFailOn` (défaut `critical`) + 8 classes hard-blocking |
| **Hard-blocking** | `[SEC_SECRET_HARDCODED]`, `[SEC_SQL_INJECTION]`, `[SEC_COMMAND_INJECTION]`, `[SEC_BROKEN_AUTHZ]`, `[SEC_BROKEN_AUTHN]`, `[SEC_DESERIALIZATION_UNSAFE]`, `[SEC_JWT_MISCONFIG]`, `[SEC_SSRF_RISK]` |

**One-liner** : Vérifie qu'aucune vulnérabilité OWASP critique ne sort en production.
**Quand l'invoquer** : automatique en mode `full`. Manuel pour audit pré-release.
**Limitation** : ne corrige pas ; mode `threat-model` migré vers template humain (`threat-model.template.md`).

---

### `spec-compliance-reviewer`

| Field | Value |
|---|---|
| **Role** | Re-lit le code AC-par-AC pour vérifier que chaque Acceptance Criteria est matérialisée ("Do not trust the report"). |
| **Model** | Sonnet 4.6 |
| **Phase** | 6.4 batch parallèle (post-dev) |
| **Triggers** | `/sdd-full {n}`, `/sdd-review {n}` (si `SpecComplianceMode: full`) |
| **Inputs (Reads)** | `stack.md`, FEAT+US (source ACs), `plans/{n}-*.{back,front}.md`, code `src/**` ; **ne lit jamais** les rapports des autres auditeurs |
| **Outputs (Writes)** | `.sys/.validation/{n}-spec-compliance.{md,json}` |
| **Tools** | Read, Write, Glob, Grep, Bash |
| **Verdicts** | 🟢 / 🟡 / 🔴 selon `SpecComplianceFailOn` (défaut `serious`) ; biais "bias toward not-verified" |
| **Hard-blocking** | `[SPEC_COMPLIANCE_REQUIRED]`, `[SPEC_COMPLIANCE_RED]`, `[SPEC_COMPLIANCE_PARSE_ERROR]` (via `/feat-validate`) |

**One-liner** : Garantit qu'aucune AC déclarée n'est silencieusement oubliée par les dev-*.
**Quand l'invoquer** : automatique en mode `full`. Manuel pour audit d'acceptation finale.
**Limitation** : opt-in (défaut `manual`) ; faux positifs tolérés, faux négatifs interdits.

---

### `arch-reviewer`

| Field | Value |
|---|---|
| **Role** | Audit du code matérialisé contre le pattern d'archi actif (MVC/DDD/microservice), layer mapping §1.3, ADRs §6. |
| **Model** | Sonnet 4.6 |
| **Phase** | 6.4 batch parallèle (post-dev, opt-in) |
| **Triggers** | `/sdd-review {n}` STEP 3.5 (si `ArchReviewMode: full`) |
| **Inputs (Reads)** | `stack.md`, `stacks/archi/{mvc\|ddd\|microservice}.md`, stacks backend/frontend §1.3, `constitution.md §2/§6`, ADRs, plans, code `src/**` |
| **Outputs (Writes)** | `.sys/.validation/{n}-arch-review.{md,json}` |
| **Tools** | Read, Write, Glob, Grep, Bash |
| **Verdicts** | 🟢 / 🟡 / 🔴 selon `ArchReviewFailOn` (défaut `serious`) |
| **Hard-blocking** | `[ARCH_PATTERN_VIOLATION]`, `[ARCH_LAYER_BYPASS]`, `[ARCH_ADR_DRIFT]`, `[ARCH_NAMING_INVALID]`, `[ARCH_NO_TARGETS]` |

**One-liner** : Vérifie que les couches/pattern/ADRs déclarés sont réellement appliqués dans le code.
**Quand l'invoquer** : opt-in via `ArchReviewMode: full`. Manuel pour audit architectural.
**Limitation** : ne duplique pas code-reviewer/security/spec-compliance ; focus pur archi/couches/ADRs.

---

### `adversarial-reviewer`

| Field | Value |
|---|---|
| **Role** | Avocat du diable post-audit — produit 5-10 attaques concrètes (edge cases, hypothèses fragiles, dette masquée, failure modes, UX). |
| **Model** | Sonnet 4.6 |
| **Phase** | 99% (post-agrégation `/sdd-review`, opt-in `--adversarial`) |
| **Triggers** | `/sdd-review {n} --adversarial` (manuel) ou auto si `AdversarialReviewMode: full` |
| **Inputs (Reads)** | `stack.md`, FEAT+US, plans, `qa/feat-{n}/review.md` (précondition), headers des autres `*-review.md`, ≤3 fichiers code ciblés |
| **Outputs (Writes)** | `qa/feat-{n}/adversarial.{md,json}` |
| **Tools** | Read, Write, Glob, Grep, Bash |
| **Verdicts** | **`informational` TOUJOURS** — jamais 🟢/🟡/🔴, jamais bloquant |
| **Hard-blocking** | aucun par design ; émet `[ADV_EDGE_CASE]`, `[ADV_FRAGILE_ASSUMPTION]`, `[ADV_HIDDEN_TECH_DEBT]`, `[ADV_FAILURE_MODE]`, `[ADV_UX_CONFUSION]` ; précondition `[ADV_PRECONDITION_FAILED]` si `/sdd-review` pas tourné |

**One-liner** : "Comment je casserais ça en prod un vendredi à 17h ?" — signal de richesse pour US de remédiation.
**Quand l'invoquer** : manuellement après `/sdd-review` pour FEATs sensibles ; jamais en mode `off`.
**Limitation** : strictement informationnel ; dé-duplique tout finding chevauchant un autre reviewer (§2.5).

---

## 📊 Agent matrix at a glance

| Agent | Phase | Model | Writes code? | Bloquant? | Parallélisable? |
|---|---|---|:---:|:---:|:---:|
| `po` | 2 | Sonnet | ✅ (US) | ✅ | ❌ (1× par FEAT) |
| `elicitor` | 1.5 | Sonnet | ✅ (FEAT append) | 🟡 | ❌ |
| `arch` | 3 | Sonnet | ✅ (scaffold) | ✅ | ❌ |
| `constitutioner` | 3.5 | Sonnet | ✅ (ADRs) | ❌ | ❌ |
| `dev-backend` | 4 | **Opus** | ✅ (code) | ✅ | ✅ (N US) |
| `dev-frontend` | 4 | **Opus** | ✅ (code) | ✅ | ✅ (N US) |
| `qa` | 5 | Sonnet | ✅ (tests) | ✅ | ❌ |
| `code-reviewer` | 6.4 | Sonnet | ❌ (read-only) | conditional | ✅ (batch 4) |
| `security-reviewer` | 6.5 | Sonnet | ❌ | conditional + 8 hard | ✅ |
| `spec-compliance-reviewer` | 6.4 | Sonnet | ❌ | conditional | ✅ |
| `arch-reviewer` | 6.4 | Sonnet | ❌ | conditional | ✅ |
| `adversarial-reviewer` | 99% | Sonnet | ❌ | **NEVER** (informational) | ❌ (post-aggregate) |

---

## 🔗 See also

- [commands-reference.md](commands-reference.md) — which command invokes which agent
- [architecture.md §3](architecture.md) — agents communication model
- [workflow.md](workflow.md) — pipeline phases (FEAT → US → Code → Review)
- [../rules/error-classification.md](../rules/error-classification.md) — full `[CLASS]` taxonomy
- [hooks-and-protections.md](hooks-and-protections.md) — 13 hooks that watch agents
