# SDD_Pro vs 6 frameworks SDD/agentic — Matrice comparative (2026-06-09)

> **Audience** : IA Eng / Prompt Eng / DSI évaluant des frameworks "spec → app".
> **Scope** : 51 dimensions × 7 frameworks. Approche honnête (forces + faiblesses).
> **Méthodo** : ground truth disque post-audit a458645/31bc7e3/audit-2026-06-09-v3
> pour SDD_Pro ; lectures repos OSS publics + docs officielles pour les autres.
> **Périmètre des 6 outils comparés** :
> - **BMAD-Method v5** (Breakthrough Method Agile AI Development — open-source pack agents)
> - **Superpowers v5.1** (Anthropic OSS, skills + practices library)
> - **Spec-Kit** (GitHub spec-driven dev kit, 4 slash-commands)
> - **AgentOS** (Builder.io methodology, standards + 4-phase workflow)
> - **Cursor** (Composer / Agent mode, IDE commercial)
> - **Aider** (Paul Gauthier CLI, multi-LLM)

---

## A. Architecture & Agents

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 1 | Agents distincts | **12 LLM + 1 rubric Python = 13** | 6-10 per pack | ~12 skills/practices | 1 unified | 1 unified + standards | 1 unified (Composer) | 1-2 (architect+editor) |
| 2 | Modèle orchestration | Hybride séquentiel + parallèle (N US) | Séquentiel sharded | Skills auto-trigger | Séquentiel 4 phases | Séquentiel 4 phases | Réactif (1 prompt) | Réactif (chat) |
| 3 | Spécialisation agents | Forte (po/arch/dev-*/qa/5 reviewers) | Forte (analyst/PM/architect/dev/QA/SM) | Moyenne (skills par capability) | Faible | Faible | Aucune | Aucune |
| 4 | Reviewers post-code | **5 angles** (code/security/spec/arch/adversarial) | 1 (QA agent) | 1 (review skill) | 0 | 0 | 0 | 0 |
| 5 | Parallélisme borné | `MaxParallel:3` US fullstack (max 6 dev-* simultanés) | Sériel | Sériel | Sériel | Sériel | n/a | n/a |

## B. Workflow & Pipeline

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 6 | Phases pipeline | 6 (Discovery→FEAT→US→Plan→Arch+DB→Dev→QA→Review) | 4 (Planning→SM stories→Dev→QA) | n/a (skills) | 4 (specify→plan→tasks→implement) | 4 (research→spec→tasks→execute) | 0 (libre) | 0 (libre) |
| 7 | Spec-first enforcement | **Hard gate** `/feat-validate` bloquant + plan-then-review | Story-template obligatoire | Test-first (TDD) | Soft | Soft | Aucun | Aucun |
| 8 | Idempotence / resume | ✅ `--resume`, state-tracking SQLite, checkpoints | ⚠️ partial (sharded MD) | ⚠️ partial | ❌ | ❌ | ❌ | ⚠️ (git commits) |
| 9 | Gates déterministes (0-token) | **55 scripts Python** | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 | Manual gates opt-in | ✅ `--manual-gates` | ❌ | ❌ | ❌ | ❌ | n/a | n/a |

## C. Anti-derive & Boundaries

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 11 | File ownership matrix | **Stricte** (12 agents × paths, STOP) | Conventions soft | Skills boundaries | ❌ | ❌ | ❌ | ❌ |
| 12 | Front/Back isolation | Hard-gate `[FILE_OWNERSHIP_NESTED]` | Soft | ❌ | ❌ | ❌ | ❌ | ❌ |
| 13 | Layer enforcement | `[LAYER_VIOLATION]` + arch-reviewer cross-fichier | Soft (architect agent) | ❌ | ❌ | ❌ | ❌ | ❌ |
| 14 | Library catalog machine | **`.libs.json` + CVE + LTS** (34 stacks) | ❌ | ❌ | ❌ | ⚠️ standards.md user-defined | ❌ | ❌ |
| 15 | Anti-lib hors catalog | STOP `[STACK_LIBRARY_MISSING]` | Soft | ❌ | ❌ | ❌ | ❌ | ❌ |
| 16 | Scope creep detection | `[DERIVE_VIOLATION]`, `[REFACTOR_HORS_SCOPE]`, `[OPTIMIZATION_PROACTIVE]` | Soft (story scope) | ⚠️ skills | ❌ | ❌ | ❌ | ❌ |

## D. Quality & Coverage

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 17 | Test framework imposé | Stack-aware (xUnit/Vitest/pytest/JUnit/Jasmine) | Suggestion | ⚠️ TDD enforced | ❌ | ❌ | ❌ | ❌ |
| 18 | Coverage threshold gate | **Hard `[QA_COVERAGE_GAP]` RED** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 19 | API Gate (in-memory tests) | ✅ back→front sequentialisé sur PASS | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 20 | Acceptance Gate (test+lint+build+smoke+E2E) | ✅ obligatoire v7.0.0 strict | ❌ | ⚠️ TDD | ❌ | ❌ | ❌ | ❌ |
| 21 | Security review OWASP | ✅ 23 classes `[SEC_*]`, 8 hard-blocking | ❌ | ⚠️ skill | ❌ | ❌ | ❌ | ❌ |
| 22 | Spec compliance AC-by-AC | ✅ `spec-compliance-reviewer` bias not-verified | ⚠️ QA agent | ⚠️ "do not trust report" | ❌ | ❌ | ❌ | ❌ |

## E. Cost & Tokens

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 23 | Cost cap par run | ✅ `MaxCostPerRun: $50` bloquant | ❌ | ❌ | ❌ | ❌ | ⚠️ user-side | ⚠️ user-side |
| 24 | Build_loop cost cap | ✅ `$15/US` `[BUILD_LOOP_COST_EXCEEDED]` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 25 | Tokens estimés / FEAT | 150-300k (full /sdd-full, cache-warm ~50% économie) | 200-500k | 50-150k | 30-80k | 50-120k | 5-50k/prompt | 5-30k/prompt |
| 26 | Cache prompt strategy | ✅ documenté (`docs/cache-strategy.md`) | ⚠️ implicite | ⚠️ implicite | ❌ | ❌ | ⚠️ provider-side | ⚠️ provider-side |
| 27 | Determinism 0-LLM | **55 scripts + 17 hooks + complexity-router rubric** | 0 | 0 | 0 | 0 | 0 | 0 |

## F. Error & Telemetry

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 28 | Taxonomie d'erreurs | **188 classes `[CLASS]`** cross-agent | 0 | ⚠️ skills classes | 0 | 0 | 0 | 0 |
| 29 | Telemetry DB | SQLite WAL (`console.db`, cost+gates+audit) | ❌ | ❌ | ❌ | ❌ | ⚠️ proprietary | ❌ |
| 30 | Verdict classification | 🟢/🟡/🔴 + 5 statuts API Gate (PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED) | ⚠️ story status | ⚠️ skills | ❌ | ❌ | ❌ | ❌ |
| 31 | Forensic trail | ADRs + `.audit/` + state ledger + 220+ smoke tests | ⚠️ sharded MD | ❌ | ❌ | ❌ | ❌ | ⚠️ git log |
| 32 | Adversarial review | ✅ opt-in `--adversarial` (6 angles ADV_*) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

## G. Stacks & Templates

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 33 | Stacks validés | **34** (29 🟢 + 4 🟡 exp + 1 🟡 POC) | Pas de catalogue (BYO) | ❌ | ❌ | ⚠️ standards.md user-defined | ❌ | ❌ |
| 34 | Combos SLA garantis | **13** (C1-C13) avec bench bench-validated runtime | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 35 | UI Design System mapping | shadcn / vuetify / radzen-blazor (5 stacks `ui/*`) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| 36 | Auth intégrations | Azure AD + JWT local + OAuth2 + scaffolding | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

## H. Governance & Memory

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 37 | ADRs versionnés | ✅ timestamp UTC + slug + rand4 (anti-collision) | ⚠️ manual MD | ❌ | ⚠️ constitution | ❌ | ❌ | ❌ |
| 38 | Constitution projet | `constitution.md` (glossaire/acteurs/stack/ADRs) | ⚠️ manual | ❌ | ✅ constitution.md | ⚠️ standards/ | ❌ | ❌ |
| 39 | Versioning policy | SemVer + LTS (v6.10.4 + v7.0.0 GA), gel sur main | SemVer | SemVer | ⚠️ | ⚠️ | rolling | rolling |
| 40 | Invariants manifest | ✅ `INVARIANTS.yml` 13 contrats + test anti-rot | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

## I. UX & Tooling

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 41 | IDE support | Claude Code only (lock-in admis) | Multi (Cursor/Windsurf/CC/Cline/Augment) | Claude Code only | Multi (Cursor/CC/Copilot/Windsurf/Gemini CLI) | Multi (Cursor/CC/Cline) | Cursor only | CLI |
| 42 | Slash commands user-facing | **13** + 8 internes debug | ~7 par pack | n/a (skills auto) | 4 | ~5 | n/a | n/a |
| 43 | Skills auto-triggered | 4 (`using-sddpro`, `starting-a-new-feat`, etc.) | ❌ | ✅ 15+ skills | ❌ | ❌ | ❌ | ❌ |
| 44 | Hooks Claude Code | **17 hooks** (preflight/audit/SubagentStop/Stop) | ❌ | ⚠️ partial | ❌ | ❌ | n/a | n/a |
| 45 | Console web (status live) | ✅ `/sdd-serve` (React+Express, port :3000) | ❌ | ❌ | ❌ | ❌ | IDE-native | ❌ |
| 46 | Élicitation guidée | **15 techniques** (Pre-mortem/Red Team/5Whys/SCAMPER…) | 5-10 (analyst/PM agents) | ❌ | ❌ | ⚠️ basique | ❌ | ❌ |
| 47 | Multi-langue docs | FR + EN | EN | EN | EN | EN | EN | EN |

## J. License & Maturité

| # | Dimension | SDD_Pro | BMAD | Superpowers | Spec-Kit | AgentOS | Cursor | Aider |
|---:|---|---|---|---|---|---|---|---|
| 48 | License | Voir LICENSE repo | MIT | Apache 2.0 (Anthropic) | MIT | MIT | Commercial | Apache 2.0 |
| 49 | Maturité | v7.0.0 GA 2026-06-07 (post-58 fixes CTO) | v5+ (active depuis 2024) | v5.1 (active) | 2024-2025 actif | active | GA mass-market | GA |
| 50 | Vendor lock-in | Claude Code (Anthropic) | Faible (multi-IDE) | Claude Code | Faible (multi-IDE) | Faible | Cursor + multi-LLM | Multi-LLM (OpenAI/Claude/Gemini/local) |
| 51 | Communauté / users | Interne SDD-Pro (OSS pending) | ~10k+ stars GitHub | Anthropic-internal + OSS | GitHub-backed, traction | Builder.io community | ~1M+ users | ~30k+ stars |

---

## Lecture rapide

**SDD_Pro gagne sur (créneau différenciant)** :
- Déterminisme : 55 scripts 0-token + 17 hooks (personne d'autre n'en a)
- Reviewers : 5 angles distincts vs 0-1 chez les autres
- Taxonomie : 188 classes `[CLASS]` cross-agent vs 0
- Anti-derive : matrix ownership stricte + STOP automatique (8 hard-blocking security)
- Telemetry : SQLite WAL persisté (cost cap, audit trail, gates)
- Stacks pré-validés : 34 + 13 combos SLA bench-validated
- Governance : ADRs timestamp + INVARIANTS.yml + test anti-rot

**SDD_Pro perd sur (limitations admises)** :
- **Vendor lock-in** Claude Code (Anthropic) — mitigation : 55 scripts Python + 188 classes + 34 stacks restent portables si pivot
- **Tokens absolus** consommés sur pipeline complet (150-300k/FEAT) — compensé par cache-warm ~50% économie et par évitement re-work
- **Courbe d'apprentissage** : 13 commandes + 12 agents + 9 rules + 188 classes à internaliser
- **Maturité** : v7.0.0 GA récent (2026-06-07) — vs Cursor/Aider matures depuis 2-3 ans
- **Communauté** : interne SDD-Pro (OSS en cours d'arbitrage)

**Niche claire** : SDD_Pro est l'équivalent **Sonar + Snyk + ADR governance** appliqué au pipeline LLM. C'est le seul framework de la matrice combinant scripts déterministes + reviewers multi-angles + anti-derive stricte. Les autres sont soit plus généralistes (Cursor, Aider), soit plus légers (Spec-Kit, AgentOS), soit moins disciplinés sur les gates (BMAD, Superpowers).

**Quand choisir SDD_Pro** :
- Équipe/DSI qui industrialise la qualité IA (>3 projets/an, contraintes audit/compliance)
- Contexte régulé (finance, santé, secteur public) où la traçabilité ADR + telemetry compte
- Stack présent dans les 13 combos SLA (sinon → tier bench-validated dégradé)
- Acceptation du lock-in Claude Code

**Quand préférer un concurrent** :
- POC rapide / 1 projet : **Cursor** ou **Aider** (moins de cérémonie)
- Multi-IDE forcé : **BMAD** ou **Spec-Kit**
- Skills réutilisables sans pipeline : **Superpowers**
- Méthodologie sans verrouillage outillage : **AgentOS**

---

> **Pour mettre à jour cette matrice** : refaire un audit "ground truth disque"
> (compteurs scripts/hooks/stacks/classes) puis recroiser docs publiques des
> 6 frameworks. Périodicité recommandée : trimestrielle.
