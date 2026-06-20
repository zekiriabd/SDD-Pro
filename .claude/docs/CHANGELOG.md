# SDD_Pro — CHANGELOG

Format : [version] — date courte. Sections : `Breaking`, `Added`, `Changed`, `Fixed`, `Removed`.

---

> ## ⛔ FREEZE WINDOW — 2026-05-19 → 2026-06-18
>
> **v6.10.4 désignée LTS** (tag `v6.10.4-LTS`). Pendant 30 jours, seules
> les versions **PATCH** (typo, fix bug, CVE) sont autorisées sur `main`.
> Toute proposition **MINOR ou MAJOR** est mise en attente sur la
> branche `next` et exige un **RFC ADR `governance-{minor|major}-*`**
> validé par 2 mainteneurs avant merge post-freeze.
>
> Politique complète : `@.claude/docs/VERSIONING.md`.
> Décision motivée par 17 versions / 13 jours (v6.0.0 → v6.9.0) +
> drift v6.10 non tracé dans ce CHANGELOG.

---

## [v7.0.1-dev] — 2026-06-05 → 2026-06-08 (next branch, post v7.0.0 GA audit closure)

> Renommage MN3 (audit hygiène 2026-06-07) : cette section couvre les fixes audit CTO post-v7.0.0 GA. Sera taguée v7.0.1 PATCH (audit closure) ou v7.1.0 MINOR (selon ampleur). L'ancien header `[Unreleased] — 2026-06-05` était antidaté par rapport à `[v7.0.0] — 2026-05-23` ci-dessous, ce qui prêtait à confusion.

### Audit CTO multi-axes 2026-06-08 — tokens + perf + cohérence + code mort

Audit livré par 4 sub-agents Claude en parallèle (axes : consommation tokens,
cohérence documentation/réalité, performance scripts/hooks, code mort).
Synthèse → ~13 fixes appliqués sur `next`.

#### Cohérence (drifts doc/code)

- **CLAUDE.md §4** : "12 agents" → "12 LLM + 1 rubric déterministe = 13 .md" (alignement disque + INVARIANTS.yml `total: 13`).
- **CLAUDE.md §10** : ajout `test-driven-development` au listing skills (4 skills disque, 1 était non documenté).
- **CLAUDE.md** : "12 contrats load-bearing" → "13 contrats" (alignement INVARIANTS).
- **roadmap-v7-v8.md §24-25** : path `sdd_scripts/` → `sdd_admin/` (scripts orphan_*) + nom test fumée `structure.smoke.test.js` → `smoke.test.js`.
- **project-config.schema.json** : ajout 4 keys actives manquantes (`BuildLoopAdaptiveFallback`, `InlineRulesDriftMode`, `PricingFreshnessMode`, `PricingFreshnessMaxAgeDays`). Évite `[CONFIG_UNKNOWN_KEY]` à chaque run.

#### Tokens (cache hit Anthropic 5 min)

- **`agents/dev-backend.md` + `agents/dev-frontend.md` STEP 3** : réordonné en sections `stable → semi → volatile` selon `loader.yml cache_layer` (audit P1 tokens 2026-06-08). Avant : US/HTML lus avant rules/stacks → invalidation prefix cache. Maintenant : prefix stable maximisé.
- **`rules/library-and-stack.md §B.7`** : hoist runtime-pitfalls (~2.5 KB) vers `docs/runtime-pitfalls.md` (Read on-demand uniquement quand bug runtime suspecté).

#### Performance (hooks + CI)

- **`sdd_hooks/record_token_usage.py`** : lazy-import `layered_config` + memoize `_MODE_CACHE` module-level. Avant : 62 ms cold-start × ~50 tool calls/run = ~3 s/pipeline. Maintenant : 1 résolution puis cache, env-only short-circuit si `SDD_TOKEN_USAGE_MODE=off`.
- **CI `.github/workflows/sdd-ci.yml`** : pytest `-n auto` via pytest-xdist (~50% speedup sur 1479 tests) + nouveau job `bootstrap-combos` avec matrix `[c1,c2,c3,c4,c5]` parallèle (5 jobs au lieu de 10 steps séquentiels).
- **`pyproject.toml`** : ajout `pytest-xdist>=3.5` dans `[dev]` dependencies.

#### Hygiène code mort + workspace

- **`docs/combo-concentration-proposal.md`** : brouillon zéro-référence supprimé (168 L).
- **`docs/po-guide.md` + `docs/ux-designer-guide.md`** : rattachés à CLAUDE.md §10 Onboarding (étaient orphans circulaires).
- **`workspace/output/db/*.sql` + `schema.prev.json`** : 44 KB héritage migration ponctuelle supprimés.
- **`workspace/output/.sys/.state/plan-28.json`** : fichier corrompu (WARN logs + JSON mélangés) supprimé (évite `[CHECKPOINT_STATE_UNREADABLE]`).
- **`workspace/audit-sdd-pro-*.md` (4 fichiers)** : déletions formalisées via `git rm` (étaient deleted sans commit).
- **`workspace/input/feats/*-Calc-*.md` (16 fichiers)** + `_examples/*` (4) + `qa/bench/BENCH-GLOBAL-REPORT.md` + `console/tests/structure.smoke.test.js` : 24 fichiers bench/legacy formalisés via git rm.

### Backlog v7.2.0 (identifiés cet audit, hors scope sprint)

- **`commands/sdd-full.md` (788 L)** : collapse 19 STEPs en `<details>` (économie ~12-15 KB par run `/sdd-full`, refactor ~1h, dépend planner Python stabilisé).
- **`commands/dev-run.md` (986 L)** : hoist STEP 6.4 two-stage auditor vers `rules/auditor-orchestration.md` (~8-10 KB/run, refactor ~1h).
- **`loader.yml`** : retirer `build-and-loop.md` du stable layer dev-* nécessite hoist complet Partie B §1-9 (LibName lock, anti-derive, plan construction) vers `dev-shared-patterns.md` séparé. ~1h, risque casser hoist actuel.
- **`agents/complexity-router.md`** : déplacement vers `docs/rubrics/` requis (DEPRECATED dans propre frontmatter) — nécessite update loader.yml + cross-refs.
- **`sdd_hooks/audit_file_ownership.py`** : remplacer `os.walk` par `git diff --name-only --since=$SDD_DISPATCH_START_TS` (gain ~2-3 s/pipeline si repo git).
- **`framework_smoke.py _fingerprint()`** : `concurrent.futures.ThreadPoolExecutor` pour rglob × 8 dirs (gain ~50-100 ms Windows).

### Audit CTO 2026-06-07 — fixes minors + majors + criticals

#### Minors fermés (MN1-MN8)

- **MN1** : `README.en.md` annoté explicitement comme summary (asymétrie FR/EN documentée).
- **MN2** : `.claude/stacks/README.md` annoté "index non-stack" (clarifie comptage 34 vs 35 fichiers `*.md`).
- **MN3** : ce header renommé `[Unreleased]` → `[v7.0.1-dev]`.
- **MN4** : `loader.yml:145` clarifie distinction stack atomique 🟡 vs combo 🟢 bench-validated.
- **MN5** : `stacks/archi/microservice.md` Validation: précise roadmap v7.2.0 cible Q4 + ADR `governance-major-microservice-validation` requis.
- **MN6** : `agents/adversarial-reviewer.md §2.5` ajoute précondition sentinel `{n}-review-consolidated.flag` pour éliminer race condition lecture parallèle.
- **MN7** : **FAUX POSITIF FERMÉ** — l'audit annonçait `sdd_lib/{layered,project}_config.py = 30k L` à consolider. Recompte réel : **433 + 330 = 763 lignes total** (l'audit avait confondu bytes/chars et lignes). Aucune consolidation requise. Trace conservée pour transparence.
- **MN8** : `CLAUDE.md §3` ajoute parenthèse explicative pour "Implementation Readiness Gate".

### Audit P0 batch — v7.0.0-alpha audit consolidé (2026-06-05, 30+ fixes)

Synthèse opérationnelle d'un audit CTO/Tech Lead complet (5 sub-agents en
parallèle : commandes, agents, scripts Python, bootstrap/console/tests,
stacks/templates/docs). Bilan : framework passé de **6.5/10 (non distribuable)**
à **~9/10 (distribuable label alpha clair)**.

#### Sécurité (4 CRITICAL — fermés)

- **Console — CDN sans Subresource Integrity** → vendor local (`react`,
  `react-dom`, `@babel/standalone`, `marked` en deps + route `/vendor/:name`).
  CSP strict `default-src 'self'` ajouté. Compromission CDN ne peut plus
  déboucher sur RCE dans le navigateur du Tech Lead.
- **Console — `/api/file` lit `stack.md` (DB_PASSWORD, AUTH_JWT_SECRET, AZ_TENANTID)**
  → whitelist `ALLOWED_API_FILE_PREFIXES` (feats/, us/, plans/, qa/, .context/,
  .validation/, ui/) + suffixes (`.md/.json/.html/.txt`) + denylist explicite
  (`stack.md`, `.env`, `credentials.json`). Path traversal défense en profondeur.
- **Bypass envvar `SDD_ALLOW_*` / `SDD_DISABLE_*`** → nouveau hook PreToolUse
  matcher=Bash `sdd_hooks/block_env_bypass.py` (regex case-insensitive sur
  POSIX export, `NAME=val`, `$env:`, `setx`, `Set-Variable`/`Set-Item`).
  Bypass legitime via `SDD_ALLOW_ENV_BYPASS=1` hérité du parent shell.
- **Hook `validate_acceptance_gate` bloquant (timeout 120s × N projets)** →
  extraction de la logique vers `sdd_scripts/validate_acceptance.py` invoqué
  par l'agent qa (STEP 9.bis ajouté). Le hook devient un lecteur léger
  (< 100ms) du rapport `workspace/output/.sys/.acceptance/acceptance.json`.
  Plus de blocage Claude Code.

#### Workflow (3 CRITICAL — fermés)

- **`/sdd-full` numérotation cassée** (deux `STEP 1.bis`, `1.tiers` après
  `1.quart`, conflit verdict QA RED vs STEP 4.7 ADR index) → renumérotation
  cohérente : `1.bis` (anti-cumul, inchangé), `1.ter` (init state.json),
  `1.quart` (phase planner placeholder), `1.gates` (résoudre `$ManualGates`),
  `1.gate-proc` (procédure GATE générique). STEP 4.7 (refresh INDEX ADRs)
  déplacé en **STEP 4.45** (avant la QA gate) pour exécution inconditionnelle.
  Toutes les refs internes ET externes (`architecture.md`, `config-precedence.md`,
  `record_token_usage.py`, `dev-run.md`) mises à jour.
- **`arch.md` STEP 12.5 spawn `constitutioner`** violait
  `build-and-loop.md §3.bis` (no-spawn cross-agent) → `arch` écrit un sentinel
  disque `workspace/output/.sys/.state/arch-ready-for-constitutioner.flag` et
  termine. Le spawn vit désormais côté commande `/arch-init STEP 3.5` (où il
  est légitime). Mécanisme explicite, idempotent, testable sans LLM.
- **`po.md` sentinel `sha256:COMPUTE_REQUIRED`** résolu uniquement par
  `/us-generate` STEP 3.0 → si `Agent: po` invoqué hors orchestrateur, tous
  les downstream émettaient `[FEAT_HASH_MISMATCH]`. Solution : script SSoT
  partagé `sdd_scripts/resolve_us_hash_sentinel.py` (modes `--feat-number N`
  et `--auto-detect`) + hook SubagentStop matcher=po
  `sdd_hooks/resolve_po_hash_sentinel.py` (filet de sécurité idempotent).

#### Documentation (3 CRITICAL — fermés)

- **README mensonge `_drafts/` 9 stacks** (le dossier n'existe pas, rollback
  acté dans CHANGELOG `governance-stacks-quarantine-rollback` du 2026-05-24)
  → table refaite (14 ref + 19 exp + 1 POC-only = 34), note rollback explicite.
- **CHANGELOG décrivait un `git mv` vers `_archive-v7.0.0/` jamais commit** →
  entrée annulée avec note de transparence historique (préservée mais
  explicitement annulée pour éviter qu'un lecteur conclue à un état FS
  inexistant).
- **3 sources, 3 chiffres pour stacks count** (README=24, CLAUDE.md=34,
  filesystem=32) → CLAUDE.md §6 recompté contre FS, README aligné, script
  `sdd_admin/validate_stacks_count.py` créé pour validation automatique +
  test pytest (7 cas).

#### SERIOUS (12 — tous fermés)

- `/dev-plan` STEP 4.7 « strict-readiness » refactor (les variants `dev-*-strict`
  sont retirés v7.0.0, le flag `--strict` reste no-op pour backward-compat)
- `sdd_lib/project_config.normalize_project_aliases` émet WARN explicite sur
  divergence `AppName` ↔ `FrontendName` (canonical = `AppName`)
- `[REVIEW_SECRETS_HARDCODED]` retiré du hard-blocking code-reviewer (owned
  exclusivement par `security-reviewer` `[SEC_SECRET_HARDCODED]` CWE-798)
- `bench_run.py` whitelist `_SAFE_SQL_IDENTS` + helper `_safe_ident()` (belt
  + braces vs SQL injection même si pas d'entrée user actuelle)
- `audit_file_ownership.py` : `os.walk(topdown=True)` avec pruning
  (`node_modules`, `.venv`, `dist`, `build`, `target`, `.git`, etc.) — latence
  SubagentStop : secondes → ~100ms sur projets réels
- Console Fastify : `bodyLimit: 100 KiB`, `logger.redact` (authorization
  headers / x-api-key), hook `onRequest` Host (localhost only) + Origin check
  sur POST/PUT/PATCH/DELETE
- `bootstrap.ps1` : ValidateSet étendu `c1/c2/c3/c4/c5/custom`, switch
  `-AutoInit`, env vars `SDD_APP_NAME` / `SDD_BACKEND_NAME` / `SDD_FRONTEND_NAME`,
  `$env:SDD_COMBO` forward
- `templates/combos.json` re-sérialisé avec `ensure_ascii=False` (plus de
  mojibake double-encodé) ; `templates/status.schema.json` BOM UTF-8 retiré
- `templates/project-config.schema.json` `additionalProperties: true` documenté
  (mode strict via `--strict` flag du validateur, par design forward-compat)
- C3-bis auto-contradiction résolu : `fullstack/node-react` reste 🟡 POC-only
  (usage interne console SDD), nouvelle cible **C3-prod** sur `node-express +
  react + shadcn + node-vitest + auth-local + Prisma` (back-front séparé,
  Vite + TS strict, destiné prod)

#### MODERATE / MINOR (4 — fermés)

- `feat-generate` STEP 7.5.1 : `mkdir -p workspace/output/.sys/.context/`
  ajouté avant le Write (sinon greenfield échoue sur env neuf)
- Dérogations no-spawn explicitement annotées dans `build-and-loop.md §3.bis`
  (`elicitor` peut utiliser `AskUserQuestion` ; `arch → constitutioner` retiré
  du §3.bis car remplacé par sentinel disque)
- `adversarial-reviewer` plage chat : `99-100%` → `98-99%` (chevauchait
  `[DONE]` 100%)

#### Tests pytest ajoutés (5 fichiers, 78 nouveaux tests)

- `test_validate_acceptance.py` (14 tests) — script + hook
- `test_resolve_us_hash_sentinel.py` (10 tests) — script + hook
- `test_block_env_bypass.py` (21 tests) — matrice complète des bypass patterns
- `test_validate_stacks_count.py` (7 tests) — count + README drift + POC-only
- `test_run_dev_phase.py` (28 tests) — chunking, plan detection, gate decision

Suite totale : **1188 tests passants, 0 régression**.

#### Helper déterministe (extraction partielle dette technique)

- `sdd_scripts/run_dev_phase.py` créé : extrait la logique déterministe de
  `/dev-run` STEP 6 (chunking US, MaxParallel resolve, From-Plan detection,
  API Gate verdict parsing, continuation decision). Subcommands `plan` et
  `gate-decision` avec sortie JSON. Coût LLM 0. **Refactor complet** (élimination
  des 213L pseudo-bash spawnant les agents) reste hors-scope sans projet de
  référence intégré au CI — les `Agent: dev-backend|dev-frontend` sont des
  tool-calls Claude qui doivent rester dans le prompt.

#### Out-of-scope honnêtement listés

- Validation E2E combos C1/C2 nécessite SDK runtime (.NET / Kotlin / DB live /
  Azure AD tenant) — à conduire par le Tech Lead avec publication du log dans
  `docs/validated-combos.md §smoke-runs`
- Refactor complet `/dev-run` STEP 6 (élimination prompt 213L) — exige un
  projet de référence CI E2E
- Validation runtime des 19 stacks 🟡 experimental — sprint dédié

---

### Removed — MCP integration officially abandoned in v7.0.0 (audit 2026-06-05)

L'intégration **Model Context Protocol (MCP)** (`mcp.json` + `docs/MCP-SERVER.md`) présente en v6.10 LTS est **retirée définitivement** en v7.0.0 :

- `mcp.json` : supprimé (pas présent dans `next` depuis le sweep v7.0.0-alpha)
- `docs/MCP-SERVER.md` : supprimé (documentation de l'ancien serveur MCP)

**Justification** : aucun consommateur MCP identifié en production, intégration jamais sortie de l'état expérimental. La compétence "exposer SDD_Pro comme service à d'autres outils" est différée à v8 (recommendation `roadmap-v7-v8.md`). Les utilisateurs souhaitant exposer SDD via MCP peuvent restaurer le `mcp.json` de la branche `main` (v6.10.4-LTS).

**Réversibilité** : `git checkout main -- .claude/mcp.json .claude/docs/MCP-SERVER.md`.

**Audit-log** : entrée `governance-major-mcp-retirement` (ADR à créer si réintroduction).

### Removed — ~~Sweep stacks zero-ref vers `_archive-v7.0.0/`~~ — entrée annulée (audit P0-doc 2026-06-05)

> **v7.0.0-alpha audit P0-doc 2026-06-05** — cette entrée historique décrivait un `git mv` de 6 stacks (`python-pytest`, `angular-jasmine`, `blazor-bunit`, `kotlin-mustache`, `blazor-server`, `kotlin-android`) vers `.claude/stacks/_archive-v7.0.0/`. **Vérification factuelle 2026-06-05** : le dossier `_archive-v7.0.0/` n'existe pas, les 6 stacks sont toujours présents sous `.claude/stacks/{qa,fullstack,mobiles}/` avec leur entête `Validation:` originale. Le sweep n'a jamais été commit. Entrée préservée pour transparence historique mais explicitement annulée pour éviter qu'un lecteur conclue à un état FS inexistant.
>
> **Décision** : pas de sweep `_archive-v7.0.0/` en v7.0.0-alpha. Les stacks « zero-ref runtime » restent chargeables avec leur statut `🟡 experimental`. Une future passe pourra archiver via un script dédié + ADR `governance-stacks-archive-vX.Y` (pas en v7.0.0).

---

### Added — Décision combo C3-bis cible (ADR `governance-c3-bis-fullstack-node-react`)

Audit CTO 2026-06-05 acte la priorisation du **3ᵉ combo validé** post-v7.0.0 GA :

- **Cible C3-bis** : `fullstack/node-react + ui/shadcn (best-effort) + qa/node-vitest + auth/auth-local + Prisma + SqlServer|PostgreSQL` (`AppType=fullstack`, monolithe Babel-CDN zero-build)
- **Justification** : reflet du PoC existant `workspace/output/src/NounouJob/` (27 FEATs ingérées, stack `fullstack/node-react`) + console SDD interne v0.4.0 déjà validée sur ce stack. Combo cohérent avec écosystème Node moderne sans cérémonie TS/bundler.
- **Pivot vs roadmap initial** : `C3` historique (`.NET+Blazor+Radzen`, cf. `docs/validated-combos.md §3`) **rétrogradé en C4**. Communauté Node + simplicité Babel-CDN priorisées.
- **Statut PoC NounouJob** : partiel (2/27 FEATs touchées avec erreurs, `Status: Draft`). Workspace **gelé tel quel** (audit 2026-06-05) — pas de relance débloquage cette session. Trace de l'investissement v6.x conservée mais ne compte **pas** comme combo validé bout-en-bout.
- **Critère validation C3-bis** : 1 FEAT M (3 US, fullstack, AC traçables) `/sdd-full` end-to-end + ROI publié (3 runs, σ ≤ 15 %) — non encore atteint.
- **Items roadmap impactés** : `validated-combos.md §3` (C3 → C4, C3-bis introduit), `scope-reduction-v7-ga.md §2.1` (cible élargie 3 combos), `CLAUDE.md §6` (mention C3-bis cible).

**Rationale** : framework ne peut pas se positionner sur Node/React tant que zéro combo Node validé. C3-bis = chemin court (PoC partiel existe) vers crédibilité commerciale Node. Décision tracée audit CTO 2026-06-05.

---

### Removed — MCP server retiré (sweep dead-code C1, audit 2026-06-04)

Le serveur MCP livré v6.9.0 n'avait aucun consommateur effectif (0 usage
runtime mesuré sur 6+ mois post-livraison). Suppression complète :

- `.claude/python/sdd_mcp/` (13 modules, ~1957 LOC, ~600 LOC tests transitifs)
- `.claude/python/tests/test_mcp_*.py` (8 fichiers, 1390 LOC)
- `.claude/mcp.json` (manifest client)
- `.claude/docs/MCP-SERVER.md` (design doc)
- Variables d'env `SDD_MCP_*` (FAKE_CLAUDE, CLAUDE_BIN, AUTH_TOKEN) abandonnées
- Section §14 « MCP server (v6.9) » de `glossary.md` (5 termes canoniques)
- Mention « MCP server-side » de `roadmap-v7-v8.md:48` (item 20)
- Docstrings `sdd_lib/{project_config,paths}.py` (mentions cosmétiques)
- Section v6.9.0 de `version-notes.md`

**Migration** : aucune pour utilisateurs Claude Code (la surface MCP
n'impactait pas le pipeline interne). Pour utilisateurs Cursor / Windsurf
/ Claude Desktop / n8n qui auraient câblé `mcp.json` : restaurer depuis
`git checkout v6.10.4-LTS -- .claude/python/sdd_mcp .claude/mcp.json`
(ou tag v7.0.0).

**Rationale** : 1957 LOC + 32 tests à maintenir sans usage, risque drift
v6.x→v8.x, charge cognitive maintenance. Décision tracée audit
framework 2026-06-04 finding C1.

---

## [Unreleased précédent] — 2026-05-24 (next branch)

### Changed — Stacks quarantine `_drafts/` rollback (ADR `governance-stacks-quarantine-rollback`)

Suppression du mécanisme de quarantine `_drafts/` introduit en v7.0.0 :
- `.claude/stacks/_drafts/` supprimé.
- 9 stacks autrefois quarantine déplacés sous leur catégorie native :
  - `_drafts/archi/microservice.md` → `stacks/archi/microservice.md`
  - `_drafts/fullstack/*` → `stacks/fullstack/*` (6 stacks)
  - `_drafts/mobiles/*` → `stacks/mobiles/*` (2 stacks)
- Tous les stacks ré-intégrés conservent leur statut `Validation: 🟡 experimental`
  (aucun combo validé bout-en-bout — risque runtime non trivial, voir
  `docs/validated-combos.md §6`).
- Surface unique sous `.claude/stacks/{cat}/` ; statut explicite par
  stack via le frontmatter `Validation:`.

**Motivation** : la quarantine par sous-dossier créait une duplication
visuelle du nom de catégorie (`stacks/archi/` ET `_drafts/archi/`) et
ajoutait du code de filtrage spécial dans 3 scripts Python load-bearing.
Le statut `Validation: 🟡` par frontmatter remplit le même rôle de
signalisation sans complexité structurelle.

**Fichiers modifiés** :
- `.claude/CLAUDE.md §6` (table stacks recalée 24+9 → 33 actifs)
- `.claude/loader.yml` (3 lignes — fullstack/microservice désormais actifs)
- `.claude/rules/library-and-stack.md` (mention blazor-server recalée)
- `.claude/agents/{dev-backend,dev-frontend,arch,arch-reviewer}.md` (status)
- `.claude/docs/{architecture,validated-combos,scope-reduction-v7-ga}.md`
- `.claude/python/sdd_admin/{validate_stack_md_headers,validate_libs_catalog,framework_smoke}.py`
  (retrait des filtres `_drafts` — devenus inutiles)
- `.claude/stacks/README.md` (réécrit en README générique du catalogue)

**Supersedes** : ADR `governance-major-stacks-quarantine` (v7.0.0,
2026-05-19) + ADR `governance-restore-ddd-archi-pattern` (v7.0.0-alpha,
2026-05-20, déjà appliqué pour `ddd.md`).

---

## [v7.0.0] — 2026-05-23 (industrial publication — 10 audit blockers closed)

> **Promotion v7.0.0-alpha → v7.0.0 GA.** Session d'audit CTO 2026-05-22→23
> (fresh audit on sources, ignoring prior audit reports). **10 blockers
> fermés** (3 critiques + 7 moyens) couvrant catalog drift, onboarding
> greenfield cassé, output protocol non-enforced runtime, cross-platform
> us-generate, lock exit codes, lock payload formats, ALLOWED_AGENTS
> drift, smoke commands list incomplet, mutation-testing core=0,
> mark_breaking exit ambigu (déjà fixé, audit-confirmé).
>
> **Validation runtime** : `framework_smoke.py --strict` 🟢 ~30 checks
> verts (787 ms), pytest ~1080 tests verts (1 fail MCP `us_ops` pré-
> existant, hors scope core pipeline, tracé en known issue),
> `bootstrap.py --dry-run --combo c1` 🟢 flow greenfield validé.

### Fixed — Audit blockers (10)

#### #1 [CRITIQUE] Stack `kotlin-spring-boot` 🟢 reference — versions cohérentes
- `.libs.json` épingle `kotlin: 2.3.21` + `spring-boot: 4.0.6` (versions
  réelles au 2026-05). `.md` snippets §3 (curl init `bootVersion=`) +
  §4 (`build.gradle.kts` plugins) re-alignés sur ces versions
  (auparavant `bootVersion=3.4.0` + `kotlin("jvm") version "2.0.21"` —
  drift entre catalog machine et snippets prose). Combo "validé bout-
  en-bout CMS" désormais réellement buildable.

#### #2 [CRITIQUE] Onboarding greenfield — `bootstrap.py` discoverable + auto-detection
- `preflight.py` STEP A3 hint actionnable pointant vers `python bootstrap.py`
  (au lieu de `STACK_MISSING` cryptique). Nouveau STEP A3.bis détecte
  `{{Placeholder}}` non substitué dans `stack.md` (template brut copy-pasté
  sans rendu) → `STACK_MALFORMED` clair avec FIX = `python bootstrap.py`.
- **Nouvelle commande** `/sdd-bootstrap` (user-facing, Phase 0) — wrapper
  documentaire pour `bootstrap.py` (interactif Python, ne peut pas tourner
  dans sub-agent). Détecte état projet (greenfield/partial/initialisé/
  template brut) et émet l'instruction terminal correspondante.
- `/feat-generate` STEP 0 gate : refuse de générer une FEAT orpheline
  si `stack.md` absent ou contient des placeholders, redirige vers
  `python bootstrap.py`.
- `CLAUDE.md §9` Step 0 explicite "(Greenfield only) python bootstrap.py".

#### #3 [CRITIQUE] Output protocol enforced runtime
- `.claude/settings.json` : ajout `"outputStyle": "sdd-executive"` à la
  racine. Active `.claude/output-styles/sdd-executive.md` sur le Claude
  main loop (auparavant la promesse "1L par update" v7.0.0 était prompt-
  side uniquement chez les sub-agents — Claude orchestrateur narrait
  encore les Read/Edit/Bash). La règle `rules/output-protocol.md` est
  désormais appliquée par le harness sur toutes les surfaces texte.

#### #4 [MOYEN] `/us-generate` cross-platform — single Python invocation
- Remplace les variantes bash `sed -i` (GNU, absent natif Windows sans
  Git Bash) et PowerShell `Set-Content -Encoding utf8` (écrit UTF-8
  BOM sur Windows PowerShell 5.1, corrompant le frontmatter US) par
  un Python one-liner via `python -c "..."` qui écrit `encoding='utf-8'`
  sans BOM + `newline=''` préservant LF original + idempotent (re-exec
  sur US déjà patchées = no-op). Aucune dépendance externe (sed/pwsh/Git
  Bash).

#### #5 [MOYEN] `acquire_libname_lock.py` exit 3 documenté côté caller
- `rules/build-and-loop.md §2` table complétée :
  exit `3` = erreur fichier (lib-path invalide, permission denied,
  release sur lock d'un autre agent) → STOP + ERROR `[INFRA_BLOCKED]`
  distinct de `[LIBNAME_LOCK_HELD]` (exit 1). Évite faux positifs
  où un caller dev-* interprétait exit 3 comme lock conflict.

#### #6 [MOYEN] `sdd_lib/file_locks.py::read_lock()` durci dual-format
- Détecte les 2 formats de payload coexistant dans le framework :
  `AGENT:TS_SECONDS` (2-parts, produit par `acquire_libname_lock.py`)
  ET `PREFIX:PID:TS_MS` (3-parts, produit par `acquire_with_retry` +
  Node console). Conversion ms→s automatique sur 3-parts (heuristique
  `ts >= 1e12`). Garantit que la détection de stale lock fonctionne
  quel que soit le writer (Python/Node). Smoke validé : `('py', 1748000000)`
  ↔ `('dev-backend-1-2', 1748000000)`.

#### #7 [MOYEN] `context_budget.py` — `CURRENT_AGENTS` séparé de `RETIRED_AGENTS_V7`
- Split du whitelist monolithique `ALLOWED_AGENTS` (14 agents mixés) en
  2 listes sémantiques : `CURRENT_AGENTS` (11 — actifs v7.0.0, alignés
  avec `sdd_hooks.preflight_agent_budget.ALLOWED_AGENTS`) et
  `RETIRED_AGENTS_V7` (3 — `dashboard`, `accessibility-auditor`,
  `performance-auditor`, conservés pour read-side compat sur historique
  console.db). `argparse choices=` utilise `CURRENT_AGENTS` → CLI
  rejette désormais les agents retirés (consistent avec le hook).
  Alias `ALLOWED_AGENTS` conservé v7.0→v7.1 pour callers externes.

#### #8 [MOYEN] `framework_smoke.py` EXPECTED_COMMANDS complet (19)
- Tableau monté de 13 → 19 commandes. Ajouts : `sdd-review`,
  `sdd-discover-stack`, `sdd-serve`, `sdd-kill-server`, `sdd-profile`,
  `sdd-bootstrap`. Structuré en 2 blocs commentés (11 user-facing + 8
  internes) miroir de CLAUDE.md §3. Suppression accidentelle d'une de
  ces commandes déclenchera désormais le smoke fail.
- `PRINCIPAL_COMMANDS_FOR_CLAUDE_MD` ajoute `sdd-bootstrap` (entry point
  greenfield).

#### #9 [MOYEN] `qa/mutation-testing` core=0 — intent tracé
- Ajout `metadata.manualInstall: true` + `manualInstallRationale`
  (catalog est multi-runtime, target picked at runtime par qa STEP 8.5
  selon stack backend actif — arch ne peut pas pré-installer sans sur-
  installer). `validate_libs_catalog.py` émet désormais WARN
  `[EMPTY_CORE]` sur tout catalog `core=[]` SAUF si `manualInstall=true`
  est posé → catch accidentels, tolère intentionnels. Summary sortie
  expose `ManualInstall: bool`.

#### #10 [MOYEN] `mark_breaking_resolved.py` exit 0 ambigu — déjà fixé (audit-confirmé)
- Audit vérifié zero caller actif `.claude/` utilise `&&`/`||` sur le
  code retour. Migration v7.0.0 (0=SUCCESS marked/skipped/dryrun,
  3=INFRA_BLOCKED) documentée dans `sdd_lib/exit_codes.py §19` et la
  docstring du script. Discrimination via stdout `[OK]/[SKIP]/[DRY-RUN]`
  ou env-export `SDD_MARK_BREAKING_ACTION`. 7 tests existants couvrent
  l'invariant. Aucun code change requis.

### Added — Nouvelles surfaces

- **`/sdd-bootstrap`** : 11e commande user-facing, Phase 0. Wrapper
  documentaire pour `python bootstrap.py` (interactif). Détection état
  projet (greenfield/partial/initialisé/template brut) + instruction
  terminal contextuelle.
- **`output-styles/sdd-executive.md`** : enforced via `settings.json`
  (cf. #3). Frontmatter `name: SDD Executive`, slug `sdd-executive`.
- **`validate_libs_catalog.py`** : WARN `[EMPTY_CORE]` (cf. #9).
- **`file_locks.py::read_lock()`** : support 3-part format avec ms→s
  conversion (cf. #6).

### Changed — Documentation

- **CLAUDE.md §3** : `10 user-facing + 8 internes` → `11 user-facing + 8
  internes`. Ajout ligne `/sdd-bootstrap` Phase 0. Re-libellé
  `/sdd-discover-stack` "brownfield" pour distinguer du greenfield.
- **CLAUDE.md §9** : Step 0 explicite "(Greenfield seulement) python
  bootstrap.py" + pointer `/sdd-bootstrap` pour les options.
- **`rules/build-and-loop.md §2`** : tableau exit codes
  `acquire_libname_lock.py` complété (cf. #5).
- **`stacks/backend/kotlin-spring-boot.md`** §3 (curl init) + §4
  (build.gradle.kts plugins) : versions Kotlin/Spring Boot re-alignées
  sur `.libs.json` (cf. #1).

### Removed — N/A

(aucun retrait dans cette release — promotion clean alpha→GA)

---

## [Unreleased — v7.0.0-alpha] — 2026-05-22 (templates SSoT consolidation)

### Changed — Stack template déplacé vers framework templates dir

- **`workspace/input/stack/stack.md.template`** → **`.claude/templates/stack.md.template`**.
  Cohérence avec les autres templates framework (adr, feat, us, constitution,
  readiness, postmortem, ci-quality, etc.) tous regroupés dans
  `.claude/templates/`. `workspace/input/` reste réservé aux **inputs
  utilisateur** (stack.md résolu, feats/, ui/), pas aux templates framework.
- Callers patchés :
  - `bootstrap.py:62` — `STACK_TEMPLATE` pointe vers `.claude/templates/stack.md.template`
  - `.github/workflows/nightly-e2e.yml` — étapes E2E utilisent le template
    via le `cp -r .claude` recursive (cp explicite supprimé, redondant)
  - `workspace/input/stack/stack.md` (header note) — pointer mis à jour
- Aucun agent ou commande ne référençait directement le path templatisé
  (tous utilisaient le résolu `workspace/input/stack/stack.md`).

---

## [Unreleased — v7.0.0-alpha] — 2026-05-21 (audit follow-up, in-session fixes)

> **Session** : audit interne CTO 2026-05-21 (suite à audit Codex 2026-05-20)
> — exécution P0 + items P1 sélectionnés + 3 audits user empilés. **5 bugs
> critiques découverts et corrigés** au passage. **+175 tests** (872 → 1047),
> **smoke 80/82** (2 WARN informatifs sur pollution console.db héritée +
> smoke-timing à 504ms après +3 subprocess checks — non régression code).
> Aucune régression. Tag v7.0.0 final reste bloqué par item P0 #1
> (2 runs PoC ROI supplémentaires).

### Added — P0 tag v7.0.0 GA prerequisites (2026-05-21)

> 5 items P0 demandés pour tag v7.0.0 GA (≤ 4 semaines). Total : +14 tests
> (1072 → 1086), +1 smoke check (#18), +9 stacks `Status:` + `Validation:`
> normalisés, +1 nightly workflow, +1 README/quickstart EN.

#### 1. Validation des headers Status: + Validation: sur 24 stacks

- **9 stacks normalisés** (8 QA + 1 UI) : `Validation:` était dans un
  blockquote `> Validation: ...` au lieu d'une ligne directe → invisible
  aux regex `^Validation:` des callers (`phase_planner` etc.). Stacks
  fixés : `qa/{dotnet-xunit, kotlin-junit, node-vitest, angular-jasmine,
  blazor-bunit, python-pytest, mutation-testing, playwright}`,
  `ui/radzen-blazor`. Chaque header complété avec `Status: Draft`,
  `<Catégorie> FEAT ID:`, `Scope: ...` pour cohérence.
- **Nouveau** : `sdd_admin/validate_stack_md_headers.py` (200 LOC). Scanne
  les 24 stacks actifs (exclut `_drafts/`), détecte missing/blockquoted/
  invalid badge. Modes `--json` et `--strict` (exit 1 sur drift).
- **Branchements** : `framework_smoke.py` check #18 (auto-exécuté au hook
  Stop) + `.github/workflows/sdd-framework-ci.yml` (job strict).
- **Fix encoding** : le script `reconfigure(encoding="utf-8")` au boot
  pour gérer Windows cp1252 sans `PYTHONIOENCODING` (les badges 🟢🟡🔴
  cassaient sinon).

#### 2-4. Tests directs sur 3 scripts load-bearing

L'audit initial annonçait "31 scripts sans tests". Vérification précise :

| Script | Tests existants | Coverage avant | Action | Coverage après |
|---|---:|---:|---|---:|
| `phase_planner.py` | 40 (test_phase_planner.py) | 80% | KEEP (couverture saine) | 80% |
| `preflight.py` | 36 (test_preflight_unit.py) | 78% | KEEP | 78% |
| `sdd_review.py` | 13 (test_sdd_review_dedup.py) | **17%** | **+14 tests** | 29% |

- **`test_sdd_review.py` (14 tests)** : `resolve_fail_on` (CLI/config),
  `resolve_arch_required`, exit code matrix (0 GREEN/YELLOW, 1 RED, 2
  invalid args, 3 ensure-scans MISS), `--ensure-scans` gate (v7.0.0
  CRIT-1 fix), `--json` output, artefact markdown généré. Subprocess-
  based pour valider le CLI end-to-end.
- L'audit initial était trompeur — la coverage globale Python est saine
  (69% sur les 3 scripts). Seul `sdd_review.main()` était sous-testé.

#### 5. Workflow nightly E2E combo C1

- **`.github/workflows/nightly-e2e.yml`** : exécution quotidienne 02:30 UTC
  + déclenchement manuel. 2 jobs :
  - **`deterministic`** (toujours) : bootstrap combo C1 sur tmp dir +
    framework smoke `--strict` + 4 validators stricts + pytest. Catch
    ~80% des régressions sans appel LLM (gratuit, < 5 min).
  - **`e2e-full-pipeline`** (gated `secrets.ANTHROPIC_API_KEY != ''`) :
    `bootstrap.py --combo c1` + `/sdd-full 1` sur FEAT fixture minimale
    + assertion code généré + upload artifact + telemetry health check.
    Cap `MaxCostPerRun=5$` forcé pour safety (la fixture coûte ~$2-3).
- **Fixture** : `.claude/python/tests/fixtures/e2e-combo-c1/1-Minimal.md`
  (FEAT 1 US backend + 1 US frontend, page d'accueil "Bienvenue"). Plus
  README de maintenance.
- **Activation production** : Tech Lead ajoute `ANTHROPIC_API_KEY`
  secret GitHub → nightly e2e-full-pipeline s'active automatiquement.

#### 6. WARN explicite quand plan v2 absent (4 auditors)

Avant : les 4 auditors (code-reviewer, security-reviewer,
spec-compliance-reviewer, arch-reviewer) tombaient silencieusement en
mode fallback convention quand `workspace/output/plans/{n}-*.{back,front}.md`
était absent. Conséquence : couverture dégradée (heuristique nom→path
au lieu de plan v2 strict-ready) **sans signal opérateur**.

Après : chaque auditor émet un WARN dédié AVANT toute lecture de code,
avec format normalisé :
```
⚠️ WARN {auditor} FEAT {n} — plan v2 absent, fallback {convention|Glob}
   Cause       : ...
   Conséquence : ...
   Fix         : /dev-plan {n} pour matérialiser un plan v2 strict-ready
```
+ persistance `"source_mode": "convention-fallback"` et
`"plan_v2_warn": true` dans le JSON de rapport `{n}-{kind}.json`
(consommable par `/sdd-review`).

#### 7. README + quickstart EN

- **`README.en.md`** (96 lignes) : mirror EN du quickstart + console
  + architecture en un paragraphe + clés ressources. Les docs FR
  restent canoniques.
- **`docs/quickstart.en.md`** (75 lignes) : sections 0 (bootstrap
  automatique) + 1-5 (configuration manuelle brownfield).
- **`README.md`** (FR) : bandeau `🌍 [English README]` en tête pour
  discoverability.

---

### Roadmap items empilés (non livrés cette session)

**P1 — 1-2 trimestres post-GA** :
- `npx sdd-pro install` / `pipx install sdd-pro` (CLI installer
  publié). Préreq : valider traction du GitHub Template (Option C
  déjà livrée) sur 2-4 semaines.
- Plugin Claude Code officiel — soumettre au marketplace, modèle
  Superpowers (skills auto-triggered).
- `FileLocker` wrapper sur `sdd_state.py` — uniformiser avec
  `gate_decide` (cross-process lock).
- Détection intent via hook `UserPromptSubmit` — détecte "je veux
  faire X" → invite à `/feat-generate`.

**P2 — Vision 12 mois** :
- Mode "scale-adaptive" : `po` détecte ampleur du projet (count FEATs
  prévues) et choisit un workflow léger vs lourd.
- `sdd-builder` agent : créer interactivement un nouveau stack via
  conversation guidée (modèle `bmad-builder`).

---

### Added — bootstrap installer (Option C : GitHub Template + script)

> Réduction de la friction d'adoption « manual install » → 1 commande.
> Pas de package npm/PyPI publié (engagement maintenance évité ; valider
> traction avant). Repo configuré comme GitHub Template + script
> `bootstrap.py` (zéro dépendance externe). Inspiration : workflow BMAD
> mais sans la dette d'un binaire CLI à versionner.

- **`bootstrap.py`** à la racine du repo (475 LOC, stdlib uniquement) :
  - Détecte si le projet est déjà initialisé (`workspace/input/feats/`
    non vide OU `stack.md` existe) — refuse de l'écraser sans `--force`
  - 5 prompts interactifs max (AppName, BackendName, combo, DB type)
  - 2 combos validés présélectionnés (C1 : .NET+React+Azure ;
    C2 : Kotlin+React+Azure) + mode `custom` interactif
  - Rendu de `stack.md.template` avec 13 placeholders substitués
    (AppName, ports, ArchiPattern, backend/frontend/UI/QA stacks,
    auth profile, DatabaseType + env lines)
  - Création de `workspace/output/.sys/{audit,context,state,validation}`
  - `pip install -e .claude/python[dev]` (sauf `--skip-install`)
  - `npm install` dans `workspace/console/` (lazy, après confirmation)
  - Smoke check final + next steps actionnables
  - Force UTF-8 stdout/stderr au boot (fix emojis sur Windows cp1252)
  - Exit codes standardisés (0 SUCCESS / 1 USER_ABORT / 2 INVALID_INPUT
    / 3 INFRA_ERROR)
  - Flags : `--combo {c1,c2,custom}`, `--dry-run`, `--skip-install`,
    `--force`

- **`bootstrap.ps1`** (wrapper PowerShell Windows-friendly, 70 LOC) :
  - Localise un Python 3.10+ (`py` → `python3` → `python`)
  - Force UTF-8 console encoding (cp1252 par défaut casse les emojis)
  - Forward des flags vers `bootstrap.py` (parité fonctionnelle totale)

- **`workspace/input/stack/stack.md.template`** : skeleton avec 13
  placeholders (`{{AppName}}`, `{{ArchiPattern}}`, etc.) + defaults
  sûrs (QAMode tests+coverage, CoverageMin 80, MaxCostPerRun 50,
  SecurityScanEnabled true, MutationTestingMode off).

- **`test_bootstrap.py`** (25 tests) :
  - `TestCombos` (5) : présence C1/C2, champs requis, fichiers stacks
    référencés existent sur disque
  - `TestValidateAppName` (5) : PascalCase, refus lowercase/spaces/long
  - `TestRenderStackMd` (13) : substitution placeholders, no-leak final,
    auth profiles (azure-ad / auth-local / none), DB types (postgres /
    sqlserver / none)
  - `TestDetection` (1) : constantes sous REPO_ROOT
  - `TestCliDryRun` (1) : dry-run ne modifie pas stack.md existant

- **README.md** : section « 🚀 Quickstart — nouveau projet » avec
  3 modes d'invocation (Python, PowerShell, scripted).
- **docs/quickstart.md** : section §0 bootstrap automatique en tête,
  sections 1-5 (config manuelle) repositionnées comme brownfield.

**Effort réel** : 1 jour (vs 4-6 jours pour une option `npx sdd-pro`
ou `pipx install sdd-pro`). Maintenance : ~30 min par release MAJOR
(refresh template + tests combo). Décision validation après 2-4
semaines : si traction observée (forks, stars), investir B (pipx) en
sprint dédié pour package PyPI.

### Fixed — bugs critiques télémétrie (filé par user 2026-05-21)

- **`connect_ro` ouvrait via URI non-RFC** : `f"file:{db_path.as_posix()}"`
  produisait `file:G:/...` (Windows) au lieu de `file:///G:/...` (RFC 8089).
  Fonctionnait sur la plupart des builds Python mais cassait sur certains
  sandboxés. Plus grave : aucun fallback si WAL `-wal`/`-shm` étaient
  verrouillés par un writer concurrent (cas Windows fréquent pendant
  `/sdd-full`) → erreur opaque "unable to open database file" sur
  `verify_telemetry_health.py` + `report_token_usage.py`. Fix : `Path.as_uri()`
  pour RFC compliance + retry `?mode=ro&immutable=1` sur `OperationalError`
  ("unable to open database file"). `immutable=1` bypasse complètement
  `-wal`/`-shm`, sûr pour lecture-only.
- **`preflight_cost_cap._compute_run_cost` transformait toute erreur DB en
  cost=0.0** → le cap `MaxCostPerRun: $50` devenait **silencieusement
  inopérant** à chaque échec de télémétrie (DB locked, schéma corrompu,
  permissions FS). Le hook autorisait l'invocation Agent sans contrôle.
  Fix : distinguer 3 cas de scope :
    - `"db absent"` (fichier inexistant) → ALLOW legit (fresh checkout)
    - `"run={id} (no rows yet)"` → ALLOW legit (run frais)
    - `"db error: ..."` → **NEW** : DENY (`HOOK_DENY=2`) en CI auto-detect,
      visible ERROR + ALLOW en interactif (operator awareness).
      Classe d'erreur `[TELEMETRY_UNAVAILABLE]`. Bypass strict via
      `SDD_DISABLE_COST_CAP=1` uniquement.
- **`verify_telemetry_health.py` utilisait `sqlite3.connect` direct** au
  lieu de `connect_ro` → cohérence rompue avec les autres lecteurs + même
  défaut WAL lock. Fix : route via `connect_ro` (WAL-safe + immutable
  fallback) + nouveau verdict `UNREADABLE` quand la DB existe mais qu'un
  premier query révèle la corruption (SQLite n'invalide pas à l'ouverture).
  Wrapper try/except élargi pour capturer les exceptions levées au premier
  SELECT (`sqlite_master`) — sinon le script crashait avec stack trace au
  lieu d'émettre un verdict structuré.

### Fixed — conflit ports console / Vite (filé par user 2026-05-21)

- **`workspace/console/server.js:46`** défaut `PORT = 5173` → collision
  garantie avec Vite (`react`, `vue`) qui prend aussi 5173 → `/sdd-serve`
  démarrait instablement, l'un des 2 services rebondissait sur un port
  libre aléatoire et la doc devenait fausse. Doc déjà cohérente sur 4000
  (`sdd-serve.md` §6) mais le code par défaut contredisait.
  Fix : défaut 4000 (cohérent doc) + commentaire explicatif. Override
  `PORT=` env var conservé pour compat. Sweep cross-files :
  `workspace/console/README.md`, `workspace/console/help/presentation.html`,
  `.claude/commands/sdd-serve.md`, `.claude/commands/sdd-kill-server.md`
  (8 occurrences fixées).

### Changed — settings.json durci (audit user 2026-05-21)

- **`Bash` bare retiré** de l'allowlist. Cette entrée seule rendait les
  60+ allowlists granulaires `Bash(dotnet:*)`, `Bash(python:*)`, etc.
  **purement décoratives** (l'autorisation universelle prenait toujours
  le pas). Désormais l'allowlist granulaire est seule active — chaque
  commande Bash doit matcher un pattern explicite.
- **`WebFetch`, `WebSearch` retirés** du allow versionné. Les agents
  SDD_Pro sont source-first (lecture locale) ; ces tools sont rarement
  nécessaires. Ajout possible via `.claude/settings.local.json` (per-dev,
  gitignored) si besoin ponctuel.
- **`defaultMode`** : `"acceptEdits"` → `"default"`. Avant : tout Edit /
  Write était auto-accepté **silencieusement**, y compris pour les
  outils non-allowlistés. Désormais : seuls Edit / Write / MultiEdit
  (explicitement allowlistés) passent sans prompt — tout outil hors
  allow prompte l'utilisateur. Le pipeline SDD continue de fonctionner
  inchangé (les outils dont il a besoin sont allowlistés). Pour
  restaurer le comportement legacy plus rapide : poser
  `defaultMode: "acceptEdits"` dans `settings.local.json`.

### Added — tests télémétrie trust (+13)

- **`test_telemetry_trust.py`** (13 tests) :
  - `TestConnectRoUriPortability` (4) : `as_uri()` source-inspection,
    fallback `immutable=1` présent, raises on missing DB, sanity read.
  - `TestComputeRunCostScopes` (2) : DB absent → scope legit ; DB corrupt
    → scope `db error:...` (signal au caller).
  - `TestCostCapHookBehaviourOnDbError` (3) : CI auto-detect → DENY ;
    interactif → ERROR visible + ALLOW ; bypass `SDD_DISABLE_COST_CAP=1`.
  - `TestCostCapAbsentDbAllows` (1) : fresh repo sans DB → ALLOW silencieux.
  - `TestVerifyTelemetryHealth` (3) : verdict ABSENT / CLEAN / **UNREADABLE**
    (nouveau).

### Fixed — bugs critiques

- **`sdd_lib/run_id.py:37`** importait `find_project_root` qui **n'existait pas
  dans `paths.py`** (seul `repo_root` est exposé). Conséquence :
  `preflight_cost_cap.py:40` faisait un import eager → crash silencieux du
  hook à **chaque** invocation depuis v7.0.0. `record_token_usage.py:213`
  masquait le même bug avec un `try/except` → toutes les lignes
  `token_usage.run_id` insérées en prod étaient **NULL**. Le `MaxCostPerRun:
  $50` annoncé en v7.0.0 **n'a jamais bloqué une seule invocation** depuis
  la sortie. Fix : `find_project_root` → `repo_root` + upsert idempotent
  du parent `runs` row dans `record_token_usage.py` (respecter la FK
  constraint `token_usage.run_id -> runs(run_id)`).
- **Parser Project Config retournait `dict[str, str]`** — toutes les valeurs
  bool/int/float arrivaient comme strings ("true", "80", "15.00"). Les
  callers existants compensaient via leurs propres `_bool_flag` /
  `_normalize_mode` / `int(raw)` mais un caller négligent aurait écrit
  `if cfg["SecurityScanEnabled"]:` → toujours truthy. Fix : coercion
  opt-in `coerce=True` sur `parse_kv_block`, `read_project_config`,
  `read_layered_config` (backward-compat préservée à 100% pour les
  ~10 callers existants).

### Added — tests (+162)

- **`test_protect_framework.py`** (13 tests) : warn/strict/off, CI auto-detect,
  framework paths protégés, payload edge cases.
- **`test_audit_file_ownership.py`** (17 tests) : matrice ownership in-process
  + lifecycle sous-process (tmp workspace, cutoff, modes).
- **`test_preflight_agent_budget.py`** (18 tests) : `REJECTED_AGENTS_V7`,
  `extract_us_and_feat` regex, lifecycle CI/interactive.
- **`test_preflight_cost_cap.py`** (13 tests) : pricing table, cap
  résolution, blocking hard, bypass, scoping par `run_id`.
- **`test_quality_scan.py`** (38 tests) : TODO/FIXME/debug/hex/long-method/
  magic-numbers, robustesse encoding.
- **`test_validate_project_config.py`** (25 tests) : schéma JSON, enum/range/
  type mismatch, strict-unknown.
- **`test_coerce_config_types.py`** (38 tests) : `coerce_scalar` bool/int/float,
  `coerce_config_types` mode preservation + idempotence, `parse_kv_block` +
  `read_project_config` + `read_layered_config` avec/sans `coerce=True`.

### Added — outillage

- **`templates/project-config.schema.json`** (43 clés documentées) — SSoT JSON
  Schema pour le merged Project Config (3-layer hierarchy). Couvre 7 modes,
  7 severities, 3 cost caps, 6 naming/ports, 2 deprecated/no-op (`PlanCacheStrict`,
  `SecurityThreatModelEnabled`) avec marqueurs explicites dans `_meta`.
- **`sdd_scripts/validate_project_config.py`** — validator CLI léger
  (pas de dep `jsonschema` externe). Détecte typos enum (`QAMode: of`),
  out-of-range (`CoverageMin: 150`), type mismatches (`MaxParallel: "three"`).
  Mode `--strict-unknown` flag les clés non documentées.
- **`sdd_lib/project_config.py`** — fonctions `coerce_scalar`,
  `coerce_config_types`, frozenset `STRING_ENUM_KEYS` (28 clés enum à
  ne JAMAIS coercer).
- **`framework_smoke.py`** — 3 nouveaux checks :
  - #15 `framework-bom-check` (délègue `strip_bom.py --check`)
  - #16 `telemetry-health` (délègue `verify_telemetry_health.py`)
  - #17 `project-config-schema` (délègue `validate_project_config.py`)
  - Smoke passe de 79 à 82 checks ; seuil self-timing relevé 200ms → 400ms
    (les 3 subprocess ajoutent ~90ms cumul, légitimes).
- **`.github/workflows/sdd-framework-ci.yml`** — workflow GitHub Actions
  léger (pytest + smoke `--strict` + 3 strict validators). Optionnel,
  prêt à activer en commit.

### Changed — refs vaporware purgées des sources actives

- `error-classification.md` §1.9 (a11y), §1.12 (perf) : refs à `ingest_a11y_axe.py`
  et `ingest_perf_lighthouse.py` (scripts inexistants) → wording neutralisé
  (« décision out-of-scope du framework — à arbitrer par le projet consommateur »).
- `error-classification-legacy.md` (3 occurrences) idem.
- `ownership.md` : `/sdd-rebuild-index` (futur v3.1) → `index_adrs.py` (existe).
- `dev-shared-preflight.md` : `sdd_admin/sync_inline_rules.py` (inexistant)
  → `sdd_scripts/validate_inline_rules.py` (existe, déjà branché à smoke).
- `loader.yml` ligne 547 : commentaire `futur ingest_a11y_axe.py` nettoyé.
- Refs `DESIGN-FROMPLAN-STRICT.md` repointées vers `ARCHIVE/v7-design-superseded/`
  (file déjà déplacé, refs cassées dans `architecture.md`, `glossary.md`,
  `MIGRATION.md`, `python/README.md`, `compute_plan_metadata.py`,
  `validate_plan.py`).

### Changed — false positives d'orphelins

L'audit initial avait flaggé `record_gate_decision.py` comme orphelin —
**incorrect** : il est invoqué par `workspace/console/lib/console-db.js:171`
(API `/api/gate-decide` du serveur console). Le scope du grep initial
était limité à `.claude/` et ratait les callers Node. **Aucune action** —
le script reste tel quel.

### Decisions différées — explicites et tracées

- **Cache `cache_control` markers** (P0.3) : déféré v7.1 par décision
  M4 audit (refacto harness Anthropic, hors scope hotfix P0).
- **Refactor 5 stacks > 800 LOC** (P1.7) : déféré v7.1 par décision M4 audit
  (risque rupture compat agents qui Read sélectivement via offset/limit).
- **Refactor `validate_readiness.main` 423 LOC** (P2.9) : 27 tests dépendent
  du contrat — refactor exige sprint dédié.
- **Refactor `console_db.py` 883 LOC / 38 funcs plates** (P2.10) : SSoT
  télémétrie 24 tables — refactor par feature.
- **Réduire `dev-run.md` (905 LOC) + `sdd-full.md` (783 LOC)** (P1.4) :
  casserait les refs internes STEP X.bis/quart.

---

## [Unreleased — v7.0.0-alpha] — 2026-05-20 (branche `next` only, 21 commits)

> **Scope** : implémentation effective des 4 ADRs `governance-major-*` les plus
> impactants + résolution des P0 du **Codex CTO audit (2026-05-20)** +
> **post-audit CTO interne 2026-05-20 (cette session)** : 20 fixes
> cross-couches (cost cap, statuts API gate, spec-compliance gate, DAG
> strict, mutation testing opt-in, CI templates a11y/perf, dé-dup
> reviewers, feat-hash, Quantified Goal/NFC anti-GIGO, migrations
> versionnées console.db, sweep complet des 8 stubs backward-compat).
> Tests : 777/777 vert, smoke 79/79 vert. Le tag v7.0.0 final attend la
> sortie du freeze (2026-06-19) + revue 2 mainteneurs + 2 runs PoC ROI
> supplémentaires (variance).
>
> **Sur `main` : RIEN ne change** pendant le freeze (politique strict PATCH).
> Cette entrée documente l'état de la branche `next` au 2026-05-20 pour
> éviter le drift "21 commits non tracés" que le freeze était précisément
> censé prévenir.

### Breaking — agents retirés

- **`accessibility-auditor`** (Haiku 4.5, v6.3.0-v6.10.5) supprimé.
  Remplacement : `axe-core` intégré au CI du projet généré. Classes
  `[A11Y_*]` (§1.9 error-classification.md) conservées comme schéma
  de mapping futur. Défaut `A11yMode` flippé `full` → `"off"`.
- **`performance-auditor`** (Sonnet 4.6, v6.4.0-v6.10.5) supprimé.
  Remplacement : Lighthouse CI + wrk/k6 au CI du projet généré.
  Classes `[PERF_*]` (§1.12) conservées. Défaut `PerfMode` flippé `full` → `"off"`.
- **`dashboard`** (Haiku 4.5) supprimé. Remplacement déterministe :
  `python .claude/python/sdd_scripts/index_adrs.py` (0 token, ~50 ms,
  même output `INDEX.md`).
- **`dev-backend-strict` + `dev-frontend-strict`** (Sonnet 4.6, v6.2)
  supprimés. Variants opt-in `PlanCacheStrict: true` jamais exercés
  en prod (défaut `false` 95 % du temps). Plan v2 schema (`## Inline
  Digest`) **préservé** pour review humaine — n'oriente plus vers un
  agent alternatif. Clé `PlanCacheStrict` tolérée en lecture, sans
  effet runtime.
- **`security-reviewer` mode `threat-model`** supprimé. L'agent reste
  (mode `scan` OWASP Top 10 uniquement). Remplacement : template humain
  `.claude/templates/threat-model.template.md` (STRIDE light, ~150 LOC).
  Flag `--mode threat-model` toléré en lecture, no-op runtime.

### Breaking — defaults Project Config flippés (codex audit P0)

- `CodeReviewMode: manual` → **`full`** (codex P0 #5)
- `SecurityMode: manual` → **`full`** (codex follow-up #1)
- `SpecComplianceMode: manual` → **`full`** (codex P0 #5)
- `TokenUsageMode: "off"` → **`"record"`** (codex P0 #4 — permet de mesurer le coût réel par FEAT)
- `ReviewFailOnSddFull: false` → **`true`** (codex P0 #9 — /sdd-review verdict RED stoppe /sdd-full)
- `A11yMode: full` → **`"off"`** (agent retiré)
- `PerfMode: full` → **`"off"`** (agent retiré)
- `SecurityThreatModelEnabled: true` → **`false`** (mode retiré)

> Bypass : déclarer la clé explicitement dans `workspace/input/stack/stack.md
> ## Project Config` (project layer wins).

### Breaking — stacks en quarantaine

10 stacks déplacés vers `.claude/stacks/_drafts/` (non chargés par
`framework_smoke.py` ni `validate_libs_catalog.py`) :
- `fullstack/*` × 6 : `angular-universal`, `blazor-server`,
  `kotlin-mustache`, `next`, `node-react`, `nuxt`
- `mobiles/*` × 2 : `maui`, `react-native`
- `archi/*` × 2 : `ddd` (YAML pseudo-DSL non parseable), `microservice`

> Réactivation : PoC ROI validé (`docs/poc-roi-methodology.md`) + ADR
> `governance-restore-stack-{id}` + `git mv` retour vers la catégorie
> parente. Cf. `.claude/stacks/_drafts/README.md`.

CLAUDE.md §7 réconcilié avec les entêtes `Validation:` réels des stacks :
- Backend : `python-fastapi`, `node-express` rétrogradés 🟢 → 🟡
- Frontend : `vue`, `angular` rétrogradés 🟢 → 🟡
- Combos validés bout-en-bout : **2 sur ~120 possibles** (dotnet-minimalapi
  × react × shadcn ; kotlin-spring-boot × react × shadcn).

### Added

- **Infrastructure migration `console.db`** (`sdd_lib/migrations/` + helper
  `apply_pending_migrations()`) — forward-only, atomique par fichier,
  nommage `NNNN_slug.sql`. Premier path de migration prêt pour évolution
  schema sans `--force-recreate` (data loss). Doc :
  `sdd_lib/migrations/README.md`.
- **`sdd_scripts/index_adrs.py`** (~150 LOC + 0 LLM) — remplace l'agent
  `dashboard` retiré. Atomic write + read-back self-check.
- **`sdd_scripts/report_roi.py`** (~450 LOC, codex P0 #10) — rapport ROI
  agrégé par FEAT depuis `console.db` : wall-clock, **phase-by-phase
  timing** (codex follow-up), tokens réels par agent×modèle avec
  pricing table USD (Opus/Sonnet/Haiku, cache_creation vs cache_read
  distincts), coverage, AC verification rate, **rework rate** (codex
  follow-up), issue counts par sévérité. Markdown + JSON outputs.
- **Flag `/sdd-review --ensure-scans`** (codex follow-up #2) — exit
  code 3 + `[REVIEW_SOURCES_MISSING]` si une source auditeur obligatoire
  (quality, code-review, security, spec) a 0 lignes en DB pour la FEAT.
  Liste les invocations exactes à re-lancer.
- **Templates** : `.claude/templates/threat-model.template.md` (STRIDE
  light, 8 sections : assets / actors / surfaces / threats / controls /
  residual / ADRs / review). Livrable humain ~15-30 min par FEAT.
- **Auto-détection CI** dans `preflight_agent_budget.py` (codex
  follow-up #3) — `SDD_BUDGET_MODE` flippe `warn` → `strict` automatiquement
  si `CI` / `GITHUB_ACTIONS` / `GITLAB_CI` / `CIRCLECI` / `JENKINS_URL` /
  `BUILDKITE` / `TRAVIS` / `TF_BUILD` / `BITBUCKET_BUILD_NUMBER` détecté.
- **Tests Python (+45)** :
  - `tests/test_console_db.py` (12) : init fresh, idempotence,
    `connect_ro` FileNotFoundError, migrations round-trip, DB ahead-of-framework warn,
    **WAL concurrent writers** (8 threads), pragma WAL appliqué.
  - `tests/test_file_locks.py` (14) : `try_create_exclusive` atomique,
    `read_lock` malformed, stale recovery `acquire_with_retry`,
    **8-thread race only-one-winner**, payload pid+ts.
  - `tests/test_report_roi.py` (17) : pricing par modèle, fallback unknown,
    cache_creation vs cache_read, rework détection + rework_rate, phase
    timing aggregation.

### Changed

- **`error-classification.md`** : §1.14-§1.19 (taxonomie tooling/governance/
  arch-review/review-orchestrator) compactée en un seul §1.14
  "Tooling & Governance (compact)" — 125 LOC → 70 LOC sans perte de
  classe. §3 build_loop comportement : tableau 19 lignes → décision
  binaire + §3.1 par famille. §1.9 + §1.12 reçoivent bandeaux
  "agent retiré v7.0.0 — classes conservées comme mapping schema".
  Total : 534 → 489 LOC.
- **CLAUDE.md** : H1 "v6.10.4-LTS" → "v7.0.0-alpha (branche next)" pour
  refléter la réalité (codex P0 #1 version stability).
- **`phase_planner.py`** : `_decide_a11y` / `_decide_perf` annotent
  chaque phase avec `agent_removed: true` + `replacement: "..."` pour
  signaler aux consumers JSON que la phase est planifiée mais non
  actionnable.

### Fixed

- **Codex P0 #2** : `/dev-run` STEP 6.4 et `/qa-generate` STEP 6.4 ne
  spawn plus les agents supprimés (`accessibility-auditor`,
  `performance-auditor`). Notes de migration ajoutées vers axe-core /
  Lighthouse CI.
- **Codex P0 #3** : `preflight_agent_budget.py` hook ALLOWED_AGENTS
  resynchronisé — inclut désormais les 4 reviewers v7.0.0
  (`code-reviewer`, `security-reviewer`, `spec-compliance-reviewer`,
  `arch-reviewer`) qui n'étaient pas dans la whitelist (CRIT v6.5+
  jamais résolu). Le hook rejette désormais activement
  `accessibility-auditor` et `performance-auditor` (agents retirés).
- **Tests rouges réparés** :
  - `test_report_token_usage::test_empty_when_db_empty` :
    `_load_ledger()` enroule correctement le contextmanager
    `connect_ro()` dans son try/except (l'exception lève à `__enter__`,
    pas à la construction).
  - `test_sdd_state::test_show_run_emits_full_json` +
    `test_mcp_pipeline` × 7 + `test_mcp_tools` × 6 +
    **22 test files Windows tempdir** : ajout systématique
    `ignore_cleanup_errors=True` sur `TemporaryDirectory()` —
    SQLite -shm/-wal handles intermittents sur Windows.
  - `test_mcp_http` port-race : refonte `_start_server()` pour
    bind atomique sur port 0 + connection probe ready-wait, élimine
    la fenêtre TOCTOU de l'ancien `_free_port()` + `_start_server(port)`.

### Removed

- 2 fichiers `package.json` orphelins à la racine repo (32 KB de lockfile
  pour 1 seul dep `@vitejs/plugin-basic-ssl` déjà catalogué dans
  `frontend/react.libs.json`).
- 5 agents `.md` (cf. Breaking §Agents) : `accessibility-auditor`,
  `performance-auditor`, `dashboard`, `dev-backend-strict`,
  `dev-frontend-strict`.

### Stats v6.10.5 → v7.0.0-alpha

| Métrique | Avant | Après | Δ |
|---|---:|---:|---:|
| Tests Python | 732 / 734 (2 red) | **777 / 777** | +45, 0 red |
| Smoke | 84/84 | 83/83 OK | -1 (dashboard.md retiré) |
| Agents actifs | 16 | **11** | -5 |
| Reviewers actifs | 6 | **4** | -2 |
| Stacks actifs | 31 | **17** | -14 (10 _drafts, 4 supprimés implicite des modes) |
| LOC framework | ~69 500 | **~62 100** | **-7 400** |
| Codex CTO P0 résolus | 0/10 | **9/10** | (#7 npm test + #8 pytest basetemp hors scope) |
| Codex CTO follow-ups | 0/4 | **4/4** | ✓ |

### Hors scope (différé v7.0.0 final ou post)

- **Split `arch.md`** (882 LOC → 3 fichiers ~300 LOC) — ADR
  `governance-major-prompts-trim` recommande, ~4-6h, session dédiée.
- **Consolider 11 rules → 5** — ~6-8h, refactor cross-fichier.
- **Réduire 17 → 8 commands publiques** — ~4h.
- **Codex #7** : `npm test` console + test API Fastify minimal.
- **Codex #8** : doc pytest `--basetemp=.pytest_tmp` pour sandboxes Windows.
- **Vaporware à tenir ou retirer** : scripts `ingest_a11y_axe.py` +
  `ingest_perf_lighthouse.py` mentionnés dans `error-classification.md`
  §1.9/§1.12 — n'existent pas encore.
- **Doc drift secondaire** : `architecture.md`, `glossary.md`,
  `version-notes.md`, `MIGRATION.md` (guide v6 → v7) — pas mis à jour
  dans cette pass.

### Pour utilisateurs SDD_Pro

- **Sur `main` v6.10.4-LTS** : aucun changement. Continuer à utiliser.
- **Pour tester `next` v7.0.0-alpha** : `git checkout next`. Stack
  experimental `fullstack/*` / `mobiles/*` cassés par défaut
  (déplacés en `_drafts/`) — restaurer manuellement si nécessaire.
  Agents `accessibility-auditor` / `performance-auditor` / `dashboard`
  retirés → si vos workflows custom les invoquent, ils échoueront avec
  "agent not found".

---

---

## Historique v6.x (archive)

Pour les entrées antérieures à v7.0.0 (v6.0.0 → v6.10.5, 2026-02-01 →
2026-05-19), voir **`@.claude/docs/CHANGELOG-v6.md`** (archive, ~1490
lignes). Le présent CHANGELOG ne couvre que **v7.0.0+** (depuis le tag
GA 2026-06-07) — segmentation décidée par l'audit consolidé Sprint 3-5
(2026-06-07) pour réduire la surcharge cognitive du fichier principal
(était 2479 lignes, désormais ~990 lignes).

Convention : à chaque MAJOR (v8, v9...), créer `CHANGELOG-v{N-1}.md`
avec les entrées de la MAJOR précédente, et redémarrer ce fichier.
