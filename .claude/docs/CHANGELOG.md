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

## [Unreleased] — 2026-06-04 (next branch)

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

## [v6.10.5] — 2026-05-19 (PATCH bug-fix CRIT-1 / CRIT-2 / CRIT-3 / CRIT-4)

### Fixed
- **CRIT-1 — auditors `code-reviewer` et `spec-compliance-reviewer` skippés silencieusement.** Defaults `phase_planner.py` (`CodeReviewMode=manual`, `SpecComplianceMode=manual`) faisaient skip sans signal. Fix scopé Project Config : `workspace/input/stack/stack.md` explicitement `CodeReviewMode/SpecComplianceMode/ArchReviewMode/A11yMode/PerfMode: full`. `arch-reviewer` reste invoqué uniquement par `/sdd-review` (bug framework à corriger post-freeze, cf. ADR `governance-major-auditors-trim`).
- **CRIT-2 — `set_us_status.py` câblé au pipeline.** Le script existait depuis v6.8 (transitions validées, classes `[US_STATUS_*]` formalisées `error-classification.md §1.3`, tests + MCP tool exposés) mais **aucune commande ni agent du pipeline ne l'invoquait** → toutes les US restaient `Status: Draft` post-build, drift garanti entre état réel et état déclaratif, `/sdd-status` non fiable.
  - `commands/feat-validate.md` STEP 5.bis : GO/WARN → flip `Draft → Ready` pour toutes US de la FEAT
  - `commands/dev-plan.md` STEP 4.bis : plan écrit → flip `Ready → InProgress`
  - `commands/dev-run.md` STEP 6.bis : build OK (per-US) → flip `InProgress → Review` ; skip si API Gate RED
  - `agents/qa.md` STEP 10.bis : verdict GREEN → flip `Review → Done` ; YELLOW/RED laisse `Review`
  - Toutes les transitions sont **idempotentes** (même status = no-op exit 0) et **non-bloquantes** (`|| true`).
  - Détection CMSPrint : 9/10 US restaient `Draft` malgré builds verts ; après fix manuel via script, 7×`Done` + 3×`Review` (FEAT 4 régression DDD).
- **CRIT-3 — Verdict QA YELLOW émis à tort sur compile fail de tests préexistants.** `agents/qa.md` STEP 10 documentait RED uniquement sur "≥1 test échoué" — pas explicitement sur `compileTestKotlin`/`tsc --noEmit`/`pytest --collect-only` échec. Alignment avec `qa-coverage.md §4` + `error-classification.md §1.7` : `[QA_TEST_FAILED]` couvre **aussi la compile failure** (un test qui ne compile EST un test échoué). Ajout d'un cas particulier "Régression cross-FEAT par refactoring" avec directive Tech Lead explicite (3 options : corriger signatures, régénérer FEAT antérieure, marquer `@Disabled`). Auto-fix par agent reste hors scope v6.10 (roadmap v7).
- **CRIT-4 — 3 rules narratives jamais Read par les agents propriétaires.**
  - `agents/dev-frontend.md` STEP 4.9 : Read explicite `@.claude/rules/ui-tokens.md` + classe `[UI_TOKEN_VIOLATION]` formalisée dans "Spécifique dev-frontend"
  - `agents/qa.md` STEP 3.10 : Read explicite `@.claude/rules/backend-first.md` (substance inlinée § API Gate, fichier référencé pour fallback cas-limite)
  - `agents/{arch,dev-backend,dev-frontend}.md` § Règles applicables : Read on-demand `@.claude/rules/source-first.md` ajouté (discipline MD-before-code, déclenchement uniquement sur bug récurrent build_loop)

### Notes
- Bug-fix strict PATCH-compatible : aucune nouvelle API, aucun nouveau script, aucun changement de défaut comportemental. Câblage littéral de contrats préexistants + alignment sémantique de verdict.
- Suggéré post-merge : ADR `ADR-20260519T220000-fix-crit-batch-wiring.md` pour traçabilité.
- Hors scope freeze (à reporter MINOR/MAJOR `next`) : `phase_planner.py` ne route pas `arch-reviewer` ; bundle size growth n'a pas de boucle corrective ; auto-fix test signature realignment (test compile failure → qa narrow re-align).

---

## [Unreleased — v7.0.0 proposals] — 2026-05-19 (8 ADRs governance Proposed)

> **8 ADRs `governance-*` Proposed** durant le freeze 2026-05-19. Toutes
> conçues pour merger dans le **même tag `v7.0.0`** post-2026-06-19 afin
> d'imposer **une seule migration utilisateur** (cf. `VERSIONING.md §5`
> max 1 MAJOR / mois).

### Proposed — branche `next` (à approuver par 2 mainteneurs)

- **`ADR-20260519T120000-governance-major-auditors-trim`** — 5 auditors LLM → 1 cœur (`spec-compliance-reviewer`) + 2 réduits (`code-reviewer`, `security-reviewer scan` scope réduit). Kill `accessibility-auditor`, `performance-auditor`, `security-reviewer threat-model`. Remplacement déterministe par `axe-core`, Lighthouse CI, `gitleaks`, `semgrep`. **−45 KB tokens/FEAT (−65 %)**.
- **`ADR-20260519T133000-governance-major-config-ssot`** — pyramide SSoT 4 tiers, `stack.md` = source primaire projet. 7 suppressions BREAKING : `read_project_config` legacy, `ArchitecturePattern:` keyvalue, `## Active App Type`, `AppNamespace`/`BackendNamespace` explicites, `stack.md.candidate`, édition manuelle miroirs Tier 4, banners freeze dupliqués.
- **`ADR-20260519T143000-governance-major-flags-trim`** — 30 keys → **10**, 13 flags CLI → **6**, 4 modes dev-* → **2** (Inline + From-Plan). Combinatoire ×15 plus petite.
- **`ADR-20260519T153000-governance-major-prompts-trim`** — CLAUDE.md slim (519→169 lignes, exécuté), agents `.md` repli rules inlinées −45 %, `error-classification.md` 534 lignes → `sdd_lib/error_classes.py` dict Python. **−110 KB tokens/FEAT (−40 % budget cycle complet)**.
- **`ADR-20260519T163000-governance-major-vocab-consolidation`** — glossaire canonique `docs/glossary.md` (~220 termes, exécuté). 16 alias dépréciés à éliminer en v7 (`derive`→`drift`, `FrontendName`→`AppName`, `reviewer`→`auditor`, etc.).
- **`ADR-20260519T173000-governance-protection-tracing`** — trace ex-post de la migration v6.5+ PowerShell → Python (23 PS → 24 Python, **+1 hook net**, aucune protection nette supprimée). Règle future : toute modification de hook exige un ADR `governance-protection-{slug}`.
- **`ADR-20260519T183000-governance-orphan-cleanup-tool`** — remplacement ciblé du `/sdd-clear` retiré v6.1. `audit_orphans.py` (read-only) + `cleanup_orphans.py` (dry-run + trash 7j + confirm). Slash command `/cleanup-orphans {n}`.
- **`ADR-20260519T193000-governance-roi-poc`** — PoC ROI obligatoire **bloquant** la release v7.0.0. 3 FEATs S/M/L figées, baseline humaine (1 dev senior 150 $/h), 3 runs framework avec variance LLM mesurée. 7 critères de release (wall-clock, $, coverage, AC verified, quality, variance).

### Livré 2026-05-19 (PATCH, partie A de chaque ADR)

- `.claude/docs/VERSIONING.md` — politique SemVer + freeze window active
- `.claude/CLAUDE.md` — slim 519 → 169 lignes (-67 %)
- `.claude/docs/version-notes.md` — archive §10.bis→§10.novies (notes par version)
- `.claude/docs/glossary.md` — 220 termes canoniques en 18 sections
- `.claude/docs/hooks-and-protections.md` — SSoT 5 hooks actifs + mapping 23 PS→Python
- `.claude/docs/orphan-cleanup-policy.md` — politique nettoyage ciblé (jamais mass purge)
- `.claude/docs/poc-roi-methodology.md` — méthodologie 3 FEATs + baseline humaine
- `.claude/docs/roi-baseline.md` — squelette à remplir post-exécution PoC
- 6 fichiers tests unitaires P0 (couverture orchestrateurs critiques 0 % → 90-99 %)

### Fixed (PATCH, post-audit 2026-05-19)

- `framework_smoke.py` : retrait de `dashboard-readme.template.html` et `qa-dashboard.template.html` du tuple `EXPECTED_TEMPLATES`. Ces 2 templates ont été retirés en v6.10.0 (cf. ci-dessous §6.10.4-LTS Retiré) mais le smoke check les réclamait encore → 2 FAIL silencieux sur Stop hook depuis v6.10.0. Smoke désormais 87/87 vert.

### Pour utilisateurs SDD_Pro pendant le freeze

**RIEN ne change sur `main`.** Les 8 ADRs sont Proposed, leur implémentation
attend l'approbation 2 mainteneurs + sortie de freeze 2026-06-19. Aucun
runtime impacté. Les nouveaux docs `.claude/docs/{glossary,hooks-and-protections,
orphan-cleanup-policy,poc-roi-methodology,roi-baseline,version-notes}.md`
sont consultables comme référence dès maintenant.

---

## [6.10.4-LTS] — 2026-05-19 (LTS designation + consolidation v6.10.x)

> **Entrée rétroactive de consolidation** : les bumps v6.10.0 → v6.10.4
> ont été publiés sans entrée CHANGELOG dédiée (drift documentaire qui
> a contribué à motiver la `VERSIONING.md`). Cette entrée les regroupe
> et désigne v6.10.4 comme LTS gelée 30 jours.

### Breaking — v6.10.0 (console DB centralisée)

- **Tous les outputs JSON/JSONL/log de télémétrie retirés du FS** et
  centralisés dans `workspace/output/db/console.db` (SQLite, 24 tables,
  WAL mode). Cf. CLAUDE.md §10.novies pour la liste exhaustive des
  fichiers retirés (`coverage.json`, `quality.json`, `events.jsonl`,
  `token-usage.jsonl`, etc.).
- Templates HTML retirés (`dashboard-readme.template.html`,
  `qa-dashboard.template.html`) — rendu graphique délégué à un
  consommateur externe lisant `console.db`.
- Agent `dashboard` réduit à `INDEX.md` des ADRs uniquement.

### Added — v6.10.0 → v6.10.4

- `sdd_lib/console_db.py` (API helper canonique : `connect()`,
  `ensure_initialized()`, `insert_event()`, `upsert_run()`).
- `sdd_scripts/init_console_db.py`, `query_console_db.py`,
  `ingest_agent_report.py`.
- Refactor 7 writers vers `console.db` (`sdd_state`, `parse_coverage`,
  `quality_scan`, `validate_fidelity`, `context_budget`, `gate_decide`,
  `record_token_usage` hook).
- v6.10.1 : `CoverageMin` rendu explicite obligatoire dans
  `## Project Config` (`[STACK_MALFORMED]` si absent).
- v6.10.2 : alias `FrontendName` accepté pour `AppName` (normalisation
  par `sdd_lib.project_config.normalize_project_aliases()`),
  `AppNamespace`/`BackendNamespace` auto-dérivés.
- v6.10.4 : auto-injection CORS dans config backend par `arch` STEP 4.5.6
  (allowlist explicite, jamais wildcard ; override possible via
  `Cors:AllowedOrigins` Project Config).
- Nouvelle règle `.claude/rules/cors.md` (substance auparavant inlinée
  dans stacks frontend/backend).

### Changed — Versioning policy (méta)

- **`.claude/docs/VERSIONING.md` créé** — politique SemVer stricte + RFC ADR
  obligatoire pour MINOR/MAJOR + cadence cible post-freeze (1
  MINOR/semaine, 1 MAJOR/mois max).
- Banner FREEZE ajouté en tête de ce CHANGELOG.

### Fixed — Drift documentaire

- Le saut v6.9.0 → CLAUDE.md mentionnant v6.10.4 sans entrée CHANGELOG
  intermédiaire est comblé par la présente entrée de consolidation.
  Pour les futures versions, une entrée CHANGELOG dédiée par bump est
  exigée (cf. `VERSIONING.md §3`).

---

## [6.9.0] — 2026-05-17 (MCP server — exposition aux clients tiers, opt-in)

> Sprint MCP livré 100 % (cf. CLAUDE.md §10.octies). **Aucun impact moteur** :
> agents, règles, taxonomie d'erreur, templates et pipeline `/sdd-full`
> byte-identiques. Stdlib pure (0 dépendance externe), protocole
> JSON-RPC 2.0 implémenté à la main (`.claude/python/sdd_mcp/`, ~1000 LOC).

### Added — Phase 1 : tools déterministes (7 wrappers `sdd_scripts/*.py`)

- `sdd_status` (wraps `sdd_state.py list-runs/get-run/show-run`)
- `validate_readiness` + alias `feat_validate` (wraps `validate_readiness.py --json`)
- `set_us_status` (wraps `set_us_status.py` — Edit narrow 1 ligne `Status:`)
- `validate_us_deps` (wraps `validate_us_deps.py --json`)
- `compute_us_complexity` (wraps `compute_us_complexity.py --json`)
- `migrate_us_v1_to_v2` (wraps `migrate_us_v1_to_v2.py --json`, idempotent)

### Added — Phase 2 : tools LLM-driven (7 tools subprocess `claude` CLI)

- `claude_check` (sync, diagnostic 0 LLM)
- `feat_generate`, `us_generate` (sync 1-3 min)
- `sdd_full` (async, retourne `job_id`)
- `get_sdd_full_status`, `cancel_sdd_full`, `list_sdd_full_jobs`

Job state persisté sous `workspace/output/.sys/.mcp-jobs/` — multi-session
visible, cross-platform PID liveness (POSIX `os.kill(pid, 0)` / Windows
`OpenProcess`).

### Added — Phase 3 : distribution multi-transport

- **stdio** (défaut) : `python -m sdd_mcp.server`
- **HTTP opt-in** : `python -m sdd_mcp.server --transport http --port 8765`
  endpoints `POST /mcp` (JSON-RPC), `GET /healthz`, `GET /tools`, auth Bearer
  optionnelle via `SDD_MCP_AUTH_TOKEN`
- **MCPB bundle** : `python -m sdd_mcp.build_mcpb` → `.mcpb` zip Claude Desktop

### Added — Manifest + tests

- `.claude/mcp.json` (manifest client à copier vers `.cursor/mcp.json` /
  Claude Desktop). Protocole MCP `2024-11-05`.
- **98 tests pytest dédiés** (`test_mcp_*.py`) tournant offline grâce à
  `SDD_MCP_FAKE_CLAUDE=1`.

### Changed — Docs livrés renommés

- `docs/PROPOSAL-FROMPLAN-STRICT.md` → `docs/DESIGN-FROMPLAN-STRICT.md`
  (design livré v6.2, plus une proposition)
- `docs/MCP-SERVER-PLAN.md` → `docs/MCP-SERVER.md` (plan livré 100% en v6.9)
- **2 nouvelles rules** : `rules/cors.md`, `rules/ui-tokens.md` (consolidation
  patterns déjà inlinés dans stacks frontend/backend, refs auparavant cassées)

### Configuration

- `SDD_MCP_CLAUDE_BIN` — override path `claude`
- `SDD_MCP_FAKE_CLAUDE=1` — mode test
- `SDD_MCP_AUTH_TOKEN` — Bearer token HTTP

### Pour Claude Code utilisateurs SDD_Pro

**RIEN ne change.** Les slash commands continuent nativement via
`.claude/commands/*.md`. Le serveur MCP est **additif**.

---

## [6.8.0] — 2026-05-17 (US schema v2 + dependency graph — Taskmaster lessons applied)

> Sprint A + B + C cumulés (3 sprints, ~24 j sur 6 sem.). Aucun item à
> risque moteur, zéro surcoût tokens LLM runtime (tout déterministe
> Python), zéro dépendance externe nouvelle, zéro git/CI/MCP/réseau.
> 4 nouveaux scripts, 4 nouveaux test files, 90 nouveaux tests pytest.

### Added — Sprint A : US frontmatter v2

- **`templates/us.template.md`** étendu :
  - Doc inline des 7 statuts valides : `Draft|Ready|InProgress|Review|Done|Deferred|Cancelled` (backward-compat avec `Draft|Done` v6.7).
  - Nouvelle section **`## Metadata`** avec bloc JSON AI-safe (conventions normées : `complexity`, `effort_estimate`, `notes`, `flags`, `custom.*`).
- **`sdd_scripts/set_us_status.py`** : transitions US validées par graphe (Kahn), `--force` bypass tracé en WARN, idempotent same-status, écriture atomique. Exit codes 0/1/2/3/4/5 distincts.
- **`sdd_scripts/compute_us_complexity.py`** : scoring déterministe 1-10 + S/M/L/XL depuis 6 signaux (ACs count, Covers count, AC text log-scaled, mots-clés complexité, deps count, User Story length log-scaled). Calibration vérifiée : compteur trivial = 3 (M), monster batch-async = 10 (XL+split warn). Injection optionnelle dans `## Metadata` JSON via `--apply`.
- **`sdd_scripts/migrate_us_v1_to_v2.py`** : migration idempotente, `--all` / `--us {id}` / `--dry-run`, ajoute `Status: Draft` si absent + `## Metadata` si absent.

### Added — Sprint B : Dependency graph

- **`sdd_scripts/validate_us_deps.py`** : parse `## Dependencies` section, build DAG, **Tarjan SCC** pour cycles, **Kahn** pour topological sort, détection refs manquantes, détection orphelins (informational). Sortie `--json` machine-readable et `--topo` pour `/dev-run`.
- **`commands/dev-run.md` STEP 2.bis** (nouveau) : validation deps + remplacement `US_LIST` par topo order AVANT batching. Backward-compat strict (US legacy sans `## Dependencies` → graphe vide → topo alphabétique = comportement v6.7 byte-identique).
- **`templates/us.template.md`** : doc canonique du format `## Dependencies` (short id `n-m` ou `NONE`).

### Added — Sprint C : Coverage + smoke + release

- **`tests/test_set_us_status.py`** : 22 tests (graphe, regex preservation newline, end-to-end avec mock repo_root).
- **`tests/test_compute_us_complexity.py`** : 18 tests (signaux, score, calibration, metadata injection préservant les clés existantes).
- **`tests/test_migrate_us_v1_to_v2.py`** : 14 tests (idempotence, dry-run, discovery, end-to-end).
- **`tests/test_validate_us_deps.py`** : 36 tests (parse deps, Tarjan SCC, Kahn topo, alphabetic tie-break, missing refs treated as no-op).
- **`tests/test_mark_breaking_resolved.py`** : 7 tests (était à 0% coverage — passe à 88%).
- **`tests/test_detect_capabilities.py`** : 17 tests (était à 0% — passe à ~85%, mocked via direct import).
- **`framework_smoke.py`** : 3 nouveaux checks (`us-template-v2`, `error-classes-v6.8`, `dev-run-deps-gate`) + 4 scripts dans `EXPECTED_PY_SCRIPTS`. Total : 80 checks tous verts.
- **`.coveragerc` + `sitecustomize.py`** : infra pytest-cov pour tracer les subprocess (8 tests legacy `subprocess.run` sont restés invisibles à pytest-cov sans cette config).

### Changed — Taxonomie d'erreur

- **`rules/error-classification.md`** §1.3 enrichie de **7 classes** v6.8 :
  - `[US_STATUS_INVALID]` — valeur hors 7 valides.
  - `[US_STATUS_TRANSITION_INVALID]` — transition rejetée par graphe (ou terminal reopen sans `--force`).
  - `[US_STATUS_PARSE_ERROR]` — ligne `Status:` absente/illisible.
  - `[US_NOT_FOUND]` — US file inexistant.
  - `[US_DEPS_CYCLE]` — Tarjan SCC ≥ 2 (bloquant `/dev-run`).
  - `[US_DEPS_MISSING]` — ref vers US inexistante (bloquant).
  - `[US_DEPS_ORPHAN]` — informational (potentiel death-code).
- §3 build_loop table : aucune des classes v6.8 n'itère build (STOP narrow, Tech Lead corrige les US).

### Métriques

| | v6.7.4 | v6.8.0 |
|---|---|---|
| Tests pytest | 358 | **476** (+118 = +33%) |
| Scripts Python sdd_scripts | 17 | **21** (+4) |
| Classes d'erreur taxonomie | ~110 | **117** (+7) |
| Coverage py (pytest-cov direct, sans subprocess) | 46% | **49%** + 2 scripts 0%→85%+ |
| Framework smoke checks | 77 | **80** (+3) |
| Surcoût tokens LLM runtime | — | **0** |
| Régression | — | **0** |

### Notes coverage

Coverage globale rapportée à 49% par pytest-cov, **mais ce chiffre sous-estime largement la réalité** : 8 fichiers de tests existants invoquent les scripts via `subprocess.run([python, script.py])` au lieu d'importer directement — ces subprocess s'exécutent dans des process Python séparés non instrumentés par pytest-cov sans `COVERAGE_PROCESS_START` + `sitecustomize.py` (ajoutés ici en `.coveragerc` mais pas encore activés en CI car CI hors scope v6.8). Coverage réelle estimée : **~70-75%** quand subprocess intégrés. Dette technique tracée pour v6.9.

### Non implémenté en v6.8 (décisions Tech Lead, mai 2026)

Suite à filtrage explicite "pas de casse moteur, pas git, pas CI, pas de gros consommateur tokens" :

- ❌ **Tags / workstreams multi-contextes** (refonte `paths.py` = risque moteur élevé).
- ❌ **Pipelines déclaratifs** (refactor `/sdd-full` = risque moteur élevé).
- ❌ **Research mode Perplexity** (réseau sortant + récurrent en tokens).
- ❌ **Git worktrees** + **CI GitHub Actions** + **Changesets** (workflow git/CI).
- ❌ **Distribution `pip install sdd-pro`** (packaging + registry = hors scope sans CI).
- ❌ **Site docs hébergé** (déploiement Pages/Netlify = workflow git/CI).

### Backlog v6.9 — livré puis retiré (cf. entrée v6.9.0 ci-dessous et Unreleased en haut)

- ✅ → ❌ **MCP server** : livré 100 % en v6.9.0 puis **retiré v7.0.0-alpha
  (2026-06-04, sweep dead-code C1)** — aucun consommateur effectif.

Autres items du filtrage Taskmaster (tags multi-contexte, pipelines déclaratifs,
Perplexity, worktrees, CI, packaging pip) restent hors scope, à reconsidérer
projet par projet.

---

## [6.7.4] — 2026-05-15 (Migrate parse_coverage.py to layered config — final policy script)

> 5e script migré vers `read_layered_config()`. **Dernière migration
> utile** : les scripts restants (`preflight.py`, `validate_semantic.py`,
> `validate_readiness.py`) lisent des clés d'**identité** (AppName,
> BackendName, DatabaseType, secrets DB/JWT) qui ne doivent **pas** être
> soumises au layering team — chaque projet est l'autorité sur sa propre
> identité.

### Modified
- `sdd_scripts/parse_coverage.py::detect_coverage_min()` : si `stack_md`
  argument == canonical path (`workspace/input/stack/stack.md`), lit
  `CoverageMin` via `read_layered_config()` (= team policy honored).
  Sinon (tests / paths explicites), conserve le comportement v6.6.x
  (regex local sur le fichier passé).

### Pourquoi cette logique conditionnelle
- Les tests passent un path custom (TemporaryDirectory) et attendent
  que `CoverageMin` soit lu depuis CE fichier, pas depuis le repo
  layered config.
- En usage réel, `parse_coverage.py` est invoqué avec le path canonique
  → la layered config kick-in → team peut enforcer `CoverageMin: 90`.

### Scripts NON migrés (par design)
Ces scripts ne sont pas candidats car ils lisent des clés d'identité
projet, pas de policy :
- `preflight.py` — `AppName`, `BackendName` (identité)
- `validate_semantic.py` — `BackendName` (identité)
- `validate_readiness.py` — `DatabaseType`, secrets DB/AUTH (identité + secrets)
- `detect_capabilities.py` — `Capabilities`, overrides (per-project tunables)

### Couverture finale v6.7.4
| Script | Migré ? | Raison |
|---|---|---|
| `phase_planner.py` | ✅ v6.7.3 | Auditor modes (policy) |
| `validate_spec_compliance.py` | ✅ v6.7.3 | SpecComplianceFailOn (policy) |
| `context_budget.py` | ✅ v6.7.3 | Project Config general (mixed) |
| `detect_arch_shortcircuit.py` | ✅ v6.7.3 | Identity (could be policy in future) |
| `parse_coverage.py` | ✅ v6.7.4 | CoverageMin (policy) |
| `preflight.py` | ❌ | Identity only |
| `validate_semantic.py` | ❌ | Identity only |
| `validate_readiness.py` | ❌ | Identity + secrets |
| `detect_capabilities.py` | ❌ | Per-project tunables |

### Non-régression
- 358/358 tests passent
- Tests test_parse_coverage existing préservés (path custom = legacy behavior)
- Comportement byte-identique v6.7.3 si base.yml + team.yml absents

---

## [6.7.3] — 2026-05-15 (Migrate 4 scripts to read_layered_config, opt-in transparent)

> Migration progressive : 4 scripts internes adoptent `read_layered_config()`
> avec fallback automatique vers `read_project_config()` legacy si
> exception. **Backward-compat strict** : si `.claude/config.base.yml`
> et `~/.sdd/config.team.yml` absents, comportement byte-identique v6.7.2.

### Breaking
- Aucun. Try/except wrap garantit le fallback.

### Modified — Scripts migrés (4)
- `sdd_scripts/phase_planner.py` : `read_layered_config()` avec
  propagation explicite des `ConfigError` (`[CONFIG_SECURITY_DOWNGRADE]`)
  + fallback `read_project_config()` sur autres exceptions.
- `sdd_scripts/validate_spec_compliance.py` : prefer layered (pour
  `SpecComplianceFailOn`), fallback legacy.
- `sdd_scripts/context_budget.py` : try layered, fallback legacy.
- `sdd_scripts/detect_arch_shortcircuit.py` : try layered, fallback legacy.

### Pattern de migration appliqué
```python
from sdd_lib.project_config import read_project_config  # legacy fallback
from sdd_lib.layered_config import ConfigError, read_layered_config  # v6.7.3

try:
    config = read_layered_config(root=root, keys=KEYS)
except ConfigError as exc:
    # Security-down violation → propagate as STACK_MALFORMED
    return error_response(exc.cause)
except Exception:
    # Other failures → fallback to legacy read
    config = read_project_config(root=root, keys=KEYS)
```

### Scripts restants à migrer (non v6.7.3)
- `validate_readiness.py` (n'utilise pas Project Config directement)
- `validate_plan.py` (idem)
- `parse_coverage.py` (idem)
- Tous les hooks `sdd_hooks/*.py` (lecture indirecte via env vars)

Migration prévue v6.7.4+ si besoin (le pattern est trivial à appliquer
quand un script découvre qu'il a besoin d'une clé sous gouvernance team).

### Non-régression
- 358/358 tests passent (aucun nouveau test, juste migration interne)
- Si team.yml et base.yml absents → `read_layered_config()` retourne
  exactement le `## Project Config` → comportement byte-identique v6.7.2
- Fallback try/except garantit qu'un bug dans `read_layered_config()` ne
  casse pas les scripts (rétention v6.7.2 behavior)

---

## [6.6.5] — 2026-05-15 (Checkpoint integration in dev-run, opt-in)

> Intégration checkpoint dans `/dev-run` — la phase la plus coûteuse
> du pipeline. Skip optionnel de l'intégralité de dev-run (arch + back +
> front + API Gate + auditors) si tous les inputs (FEAT + US + mockups
> + stack.md) sont inchangés depuis la dernière exécution réussie.

### Modified
- `commands/dev-run.md` : **STEP 1.75** (checkpoint skip si
  `CheckpointMode: resume`) + **STEP 6.6** (record input_hash si
  `CheckpointMode ∈ {record, resume}`).
- Granularité : checkpoint au niveau **dev-run complet**, pas au niveau
  phase interne. Pour la granularité phase, l'idempotence `Status: Done`
  US-level reste source de vérité.

### Inputs hashés pour dev-run
- `workspace/input/feats/{n}-*.md`            (FEAT parent)
- `workspace/output/us/{n}-*.md`              (toutes les US)
- `workspace/input/ui/{n}-*.html`             (mockups si présents)
- `workspace/input/stack/stack.md`            (Project Config + stacks)

### Émissions checkpoint
- `[CHECKPOINT_HASH_MISMATCH]` → US/mockup modifié, re-exécute tout
- `[CHECKPOINT_INPUT_MISSING]` → US supprimée, re-exécute
- `[CHECKPOINT_STATE_UNREADABLE]` → première exécution, pas de skip possible

### Non émis (record skippé) si
- Phase dev a échoué (build_loop exhausted, API Gate RED, auditor RED)
- `CheckpointMode: off` (défaut)

### Non-régression
- Mode `off` (défaut) = STEPs 1.75 + 6.6 skippés = comportement byte-identical v6.6.4
- 358/358 tests passent

---

## [6.6.4] — 2026-05-15 (Checkpoint integration in us-generate, opt-in)

> Extension du pattern v6.6.3 (qa-generate) à `/us-generate`. Skip si
> FEAT et stack.md inchangés depuis la dernière génération US réussie.

### Modified
- `commands/us-generate.md` : **STEP 2.5** (checkpoint skip si
  `CheckpointMode: resume`) + **STEP 3.bis** (record input_hash si
  `CheckpointMode ∈ {record, resume}` ET agent PO a réussi).

### Inputs hashés pour us-generate
- `workspace/input/feats/{n}-*.md`     (FEAT parent)
- `workspace/input/stack/stack.md`     (Project Config + stacks actifs)

### Non-régression
- Mode `off` (défaut) = STEPs skippés = byte-identical v6.6.3
- 358/358 tests passent

### Coverage adoption checkpoint
v6.6.3-5 couvrent les 3 commands principales :
- ✅ `/qa-generate` (v6.6.3)
- ✅ `/us-generate` (v6.6.4)
- ✅ `/dev-run` (v6.6.5)
- ⏸ `/feat-validate`, `/dev-plan`, `/sdd-full` (non couverts, faible ROI :
  exécution rapide, idempotence existante via `Status: Done` et plans)

Tout reste opt-in via `CheckpointMode`.

---

## [6.7.2] — 2026-05-15 (Profile manager — team config snapshots)

> Permet de sauver/charger des snapshots de `~/.sdd/config.team.yml`
> sous forme de profiles nommés. Utile pour orgs maintenant plusieurs
> presets (strict-prod, dev-only, security-hardened, ...). Bascule
> en 1 commande, backup auto avant overwrite.

### Added
- `python/sdd_scripts/manage_profile.py` (~180 LOC) : CLI 5 subcommands
  (export, import, list, delete, show). Validation regex du nom de profile.
  Backup automatique de team.yml en `.bak` avant import.
- `commands/sdd-profile.md` (~100 lignes) : slash command wrapper.
- `tests/test_manage_profile.py` (15 tests) : validation name, export
  (success, missing team config, overwrite refused without --force,
  force overrides), import (creates team.yml, backs up existing, fails
  on missing profile), list (empty + populated), delete, show, main
  dispatch with invalid name.

### Env vars
- `$SDD_PROFILES_DIR` → override `~/.sdd/profiles/` (utile CI/tests)
- `$SDD_TEAM_CONFIG` → override `~/.sdd/config.team.yml` (déjà v6.7.1)

### Usage
```powershell
/sdd-profile export strict-prod        # save current team.yml
/sdd-profile list                      # show all profiles
/sdd-profile import dev-only           # switch to dev-only (backups team.yml.bak)
/sdd-profile show strict-prod          # cat profile content
/sdd-profile delete obsolete           # remove
```

### Non-régression
- 358/358 tests passent
- Ne touche jamais `workspace/`, `.claude/config.base.yml`, code de prod
- Profiles stockés dans `~/.sdd/profiles/` (hors repo)

---

## [6.7.1] — 2026-05-15 (Layered Project Config — base ← team ← project)

> Project Config maintenant lue en **3 couches mergées déterministiquement** :
> 1. `.claude/config.base.yml` (framework defaults, versionné)
> 2. `~/.sdd/config.team.yml` (org/team policy)
> 3. `## Project Config` de stack.md (per-project, override final)
>
> Précédence : project > team > base. Deep-merge (scalars replaced).
> **Backward-compat strict** : si base.yml et team.yml absents,
> comportement byte-identique v6.6.x.

### Breaking
- Aucun. Lib opt-in (`read_layered_config()` nouvelle, `read_project_config()`
  legacy inchangée). Adoption progressive par les scripts.

### Added — Lib
- `sdd_lib/layered_config.py` (~270 LOC) :
  - `read_layered_config(root, keys, include_sources)` — merge 3 layers
  - `dump_effective_config(path, root)` — audit forensic
  - `_parse_yaml_minimal(text)` — flat YAML subset (stdlib pur, pas de pyyaml)
  - `ConfigError` avec `[CONFIG_SECURITY_DOWNGRADE]`
- `.claude/config.base.yml` (~30 clés) : reproduit littéralement les
  défauts v6.6.x — créer ce fichier ne change RIEN au comportement
  parce qu'il ne fait que documenter les défauts déjà encodés.

### Added — Security-down guard
Project **ne peut PAS relâcher** la policy team sur ces clés :
- `SecurityFailOn` / `A11yFailOn` / `CodeReviewFailOn` / `PerfFailOn`
  / `SpecComplianceFailOn` (severity : critical = strictest, minor = laxest)
- `CoverageMin` (numérique, project doit `>=` team)

Violation → `ConfigError([CONFIG_SECURITY_DOWNGRADE])` levée au moment
du `read_layered_config()` → ERROR clair pour le Tech Lead.

Pas de guard inverse : project peut TOUJOURS DURCIR (critical < team value),
team peut tout définir.

### Added — Tests (19 nouveaux)
- `tests/test_layered_config.py` : YAML parser minimal, severity index,
  backward-compat (no base + no team = identical v6.6.x), layering
  (base provides defaults, project overrides base, team overrides base,
  full precedence), security-down guard (severity downgrade rejected,
  hardening accepted, coverage downgrade rejected, no guard when team
  silent), keys filter, dump effective config.

### Source tracking
`read_layered_config(include_sources=True)` retourne :
```python
{
  "config": {"AppName": "MyApp", "CoverageMin": "80", ...},
  "sources": {"AppName": "project", "CoverageMin": "team", ...},
}
```
Permet à `dump_effective_config()` de produire un audit YAML annotant
chaque clé avec sa source (base/team/project).

### Adoption progressive
- Lib disponible, **aucun script existant ne l'utilise encore** en v6.7.1
- `phase_planner.py`, `validate_*.py`, etc. continuent à utiliser
  `read_project_config()` (inchangée)
- Migration prévue v6.7.3+ (un script à la fois, mesure ROI via
  telemetry v6.5.1)

### Non-régression
- 343/343 tests passent (324 baseline + 19 v6.7.1)
- `read_project_config()` legacy 100% inchangée
- `.claude/config.base.yml` créé mais aucun script ne le lit
- Existing scripts byte-identical avec v6.6.x

---

## [6.6.3] — 2026-05-15 (Checkpoint integration in qa-generate, opt-in)

> Première adoption du checkpoint lib (v6.6.2) dans une command. Ajoute
> `CheckpointMode: off | record | resume` au Project Config. Mode `off`
> par défaut → comportement byte-identique v6.6.2.

### Added — Project Config flag
```yaml
## Project Config
CheckpointMode: off     # défaut : skip checkpoint mechanism
# CheckpointMode: record   # capture input_hash en fin de phase (lightweight)
# CheckpointMode: resume   # capture + skip phases résumables (full feature)
```

### Modified
- `commands/qa-generate.md` : nouveau **STEP 1.5** (checkpoint skip
  si `CheckpointMode: resume`) + **STEP 6.bis** (record input_hash
  si `CheckpointMode ∈ {record, resume}`). Mode `off` → les 2 STEPs
  sont skippés, comportement v6.6.2 strict.
- Inputs hashés pour qa-generate : FEAT parent, toutes US de la FEAT, stack.md.

### Pattern d'adoption pour autres commands
Pour étendre v6.6.3 vers `us-generate`, `dev-run`, etc. :
1. Ajouter un STEP au début (post-validation args) qui appelle
   `is_phase_resumable(feat, "phase-name", inputs)` et skippe si OK
2. Ajouter un STEP en fin (post-success) qui appelle
   `record_input_hash(run_id, "phase-name", inputs)`
3. Inputs = liste de paths critiques (FEAT, US, plans, stack.md, etc.)
4. Documenter le STEP avec un fallback `CheckpointMode: off` propre

Reporté v6.6.4+ après mesure ROI sur qa-generate.

### Non-régression
- 324/324 tests passent (pas de nouveau test Python, integration command .md)
- Mode `off` = STEPs skippés = byte-identical v6.6.2
- Aucune modification de la lib `sdd_lib/checkpoint.py`

---

## [6.6.2] — 2026-05-15 (Checkpoint lib for input-hash validated resume, foundation)

> Deuxième brique de la roadmap v6.6. **Lib helper** `sdd_lib/checkpoint.py`
> qui ajoute la validation hash des inputs au mécanisme `--resume`
> existant (`sdd_state.py`). Permet de détecter qu'une US/plan/stack
> a été modifié post-crash et invalide le skip optimiste. **Foundation
> uniquement** — la lib est livrée, aucune command ne l'invoque encore
> en v6.6.2. Adoption progressive prévue v6.6.3+ après mesure ROI via
> telemetry v6.5.1.

### Breaking
- Aucun. Lib additive, ne modifie pas sdd_state.py existant.

### Added — Lib helper
- `sdd_lib/checkpoint.py` (~200 LOC, stdlib pur) : 4 fonctions
  publiques :
  - `compute_input_hash(paths, *, root=None) -> str` : SHA-256 stable
    over concatenated file bytes. Order-independent, missing files
    contribute sentinel `<missing:path>`.
  - `record_input_hash(run_id, phase, input_paths, *, root=None) -> str` :
    computes hash + stores in `state.json` phases.{phase}.payload.input_hash
    via atomic write (tempfile + rename).
  - `is_phase_resumable(feat, phase, input_paths, *, root=None, accept_warn=True) -> tuple[bool, str]` :
    check (1) latest run for FEAT exists, (2) phase status pass/warn,
    (3) stored hash == recomputed hash, (4) inputs still exist.
    Returns `(True, "ok")` or `(False, "[CHECKPOINT_*] reason")`.
  - `get_phase_payload(feat, phase, *, root=None) -> dict | None` :
    read-only access to phase payload (e.g. retrieve plan_validate
    results cached from previous run).

### Added — Tests (22 nouveaux)
- `tests/test_checkpoint.py` :
  - `TestComputeInputHash` (6 tests) : determinism, order-independence,
    content-change detection, missing file sentinel, string-path
    acceptance, relative-path resolution via root.
  - `TestRecordInputHash` (3 tests) : hash stored in state.json,
    raises on missing state, preserves existing payload fields.
  - `TestIsPhaseResumable` (10 tests) : resumable when pass+match,
    not resumable on hash mismatch / phase not pass / missing state /
    missing phase / no input_hash (legacy run) / missing inputs ;
    accept_warn flag ; picks latest run for FEAT.
  - `TestGetPhasePayload` (3 tests).

### Added — Classes d'erreur (`error-classification.md §1.16`)
- `[CHECKPOINT_HASH_MISMATCH]` — info, inputs modifiés post-run
- `[CHECKPOINT_INPUT_MISSING]` — info, un input déclaré n'existe plus
- `[CHECKPOINT_STATE_UNREADABLE]` — info, state.json absent ou corrompu

**Toutes informationnelles, jamais bloquantes**. Le caller doit
ré-exécuter la phase, jamais skipper sur un de ces codes (discipline
fail-safe : doute = re-run).

### Pas d'intégration v6.6.2
- Aucune command (`/sdd-full`, `/dev-run`, `/qa-generate`, etc.) n'invoque
  encore `checkpoint.is_phase_resumable()`. La lib est disponible pour
  adoption progressive en v6.6.3+.
- Le mécanisme `--resume` existant (cf. `sdd-full.md` STEP --resume +
  `sdd_state.py`) **reste intact** : il s'appuie sur le payload de
  state.json sans hash validation.
- Adoption recommandée : ajouter `record_input_hash()` à la fin de
  chaque phase clé (us-generate, dev-run, qa-generate), puis vérifier
  `is_phase_resumable()` au début de `--resume`. Mesurer le ROI sur N
  runs réels avant généralisation.

### Design — Non-régression garantie
- 324/324 tests passent (302 anciens + 22 v6.6.2)
- Aucune modification de `sdd_state.py` (qui reste source de vérité du
  state.json schema)
- Aucune modification des commands (le `--resume` actuel ne change pas)
- Lib utilise atomic write (tempfile + rename) pour modifier state.json
  sans race
- Hashs sont déterministes (mêmes inputs → même digest)

### Usage (pour intégration future)
```python
from sdd_lib.checkpoint import is_phase_resumable, record_input_hash

# Au début de phase us-generate
inputs = [f"workspace/input/feats/{feat}-{name}.md"]
resumable, reason = is_phase_resumable(feat, "us-generate", inputs)
if resumable:
    print(f"[skip] us-generate already done (hash matched)")
    return
# ... run phase ...
record_input_hash(run_id, "us-generate", inputs)
```

### Limitations v6.6.2
- Aucune command n'utilise encore le mécanisme — value tangible uniquement
  après v6.6.3+ qui intégrera dans les commands
- input_hash ne couvre que les **fichiers déclarés** ; un changement
  d'env vars ou de stack.md non listés n'invalide pas (à étendre)
- Pas de TTL — un run de 6 mois reste "resumable" si le hash matche
  encore (acceptable pour SDD, projets typiquement court terme)

---

## [6.6.1] — 2026-05-15 (Stack auto-discovery from existing repos, additive)

> Première brique de la roadmap v6.6 : nouvelle commande
> `/sdd-discover-stack` qui scanne un repo (brownfield ou nouveau) et
> produit `workspace/input/stack/stack.md.candidate` avec les stack-ids
> SDD_Pro candidats détectés automatiquement. Réduit l'onboarding de
> 15-30 min de saisie manuelle à ~2 min. **100 % additif, isolé du
> chemin critique** — la commande ne touche pas au moteur SDD_Pro
> (build_loop, API Gate, phases auditor), n'est jamais invoquée par
> `/sdd-full` ou `/dev-run`.

### Breaking
- Aucun. Nouvelle commande complètement isolée.

### Added — Scripts Python déterministes
- `sdd_scripts/scan_repo.py` (~400 LOC, stdlib pur) : scanner agnostique
  multi-stack. Détecte 8 types de manifests (csproj, package.json,
  pyproject.toml, requirements.txt, build.gradle.kts, build.gradle,
  pom.xml, angular.json, components.json, etc.). Walk récursif borné
  à profondeur 6, skip déterministe de `node_modules/`, `bin/`, `obj/`,
  `dist/`, `target/`, `.venv/`, `workspace/`, etc. Extrait : `languages`,
  `frameworks`, `ui_indicators`, `database_indicators`, `auth_indicators`.
- `sdd_scripts/match_stack_catalog.py` (~270 LOC) : mappeur déterministe
  scan-report → stack-ids SDD_Pro. STACK_RULES déclarative (11 stacks 🟢
  reference + 3 UI design systems). Scoring 0-100 (70% required + 30%
  bonus). Détecte ambiguïtés (≥ 2 candidats même catégorie) et émet
  warnings `[DISCOVER_*]`. Mapping database/auth séparé (SqlServer /
  PostgreSql / MySql / Sqlite / MongoDb ; azure-ad / auth-local).

### Added — Slash command
- `commands/sdd-discover-stack.md` (~200 lignes) : orchestration
  end-to-end. STEP 1 args (`--scope`, `--force`) → STEP 2 pre-check
  stack.md existence → STEP 3 scan → STEP 4 match → STEP 5 décision
  (NO_MATCH bloquant, AMBIGUOUS interactive, standard → continue) →
  STEP 6 complétion Project Config avec `# TODO` markers → STEP 7
  écriture `stack.md.candidate` → STEP 8 émission résumé.

### Added — Tests (44 nouveaux)
- `tests/test_scan_repo.py` (28 tests) : `_match_glob`, parsers
  (csproj, package.json, pyproject.toml), derive functions
  (languages, frameworks, ui, database, auth), intégration full-stack
  .NET+React, empty dir warning, skip de node_modules.
- `tests/test_match_stack_catalog.py` (16 tests) : confidence labels,
  score stack, match full-stack, kotlin-spring, fastapi, blazor,
  no_match warning, partial warning, ambiguous warning, sort by score,
  mapping coverage.

### Added — Configuration
Pas de Project Config nouvelle. La commande est mono-shot, invoquée à
la main par le Tech Lead lors de l'onboarding d'un repo.

### Added — Classes d'erreur (`error-classification.md §1.15`)
- `[SCAN_NO_MANIFESTS]` — info, aucun manifest trouvé
- `[SCAN_PARSE_ERROR]` — WARN, manifest illisible
- `[DISCOVER_SCAN_FAILED]` — bloquant, scan_repo exit ≠ 0
- `[DISCOVER_NO_MATCH]` — bloquant, aucun stack reconnu
- `[DISCOVER_PARTIAL]` — info, backend OU frontend seul (pas les deux)
- `[DISCOVER_AMBIGUOUS]` — info, ≥ 2 candidats même catégorie
- `[DISCOVER_STACK_EXISTS]` — info, stack.md existant → écrit .candidate

### Stacks supportés en v6.6.1 (11 stacks 🟢)
| Backend | Frontend | UI |
|---|---|---|
| dotnet-minimalapi | react | shadcn |
| kotlin-spring-boot | vue | vuetify |
| python-fastapi | angular | radzen-blazor |
| node-express | blazor-webassembly | |

### Design — Non-régression garantie
- Aucune modification du moteur (build_loop, API Gate, phases auditor,
  scripts validate_*, file ownership matrix)
- Commande jamais appelée par `/sdd-full`, `/dev-run`, `/qa-generate`
- Écrit `stack.md.candidate` à côté de `stack.md` (pas d'overwrite sauf
  `--force` explicite)
- 302/302 tests passent (258 anciens + 44 v6.6.1)
- Hors network : scan local uniquement
- Hors LLM : 0 token consommé jusqu'à STEP 5 (entièrement scripté)

### Usage
```powershell
/sdd-discover-stack --scope .
# → workspace/input/stack/stack.md.candidate avec :
#   - Active Tech Specs détectés
#   - Project Config avec # TODO markers pour valeurs à valider
#   - Active Database détectée (SqlServer/PostgreSql/MySql/Sqlite/MongoDb)
#   - Active Auth Specs détectées (azure-ad / auth-local)
```

Brownfield typique :
1. `/sdd-discover-stack` → stack.md.candidate généré
2. Revoir les lignes `# TODO` (AppName, BackendName, secrets DB/JWT)
3. Renommer .candidate → stack.md
4. `/feat-generate AuthFeature`

### Limitations connues
- Pas de mode combo monorepo polyglot (1 backend, 1 frontend max)
- Pas de détection auto de `AppName`/`BackendName` (90% des cas nécessitent ajustement)
- Stacks 🟡 expérimentaux non reconnus en v6.6.1
- Secrets jamais lus depuis `appsettings.json` (sécurité by design)

---

## [6.5.2] — 2026-05-15 (Spec-compliance reviewer "Do not trust the report", opt-in)

> Deuxième brique de la roadmap v6.5. Nouvel agent `spec-compliance-reviewer`
> qui **re-lit indépendamment le code matérialisé** et vérifie pour
> **chaque AC de chaque US** qu'il existe une preuve concrète
> d'implémentation. Pattern « Do not trust the report » hérité de
> superpowers v5.1 — l'agent ignore le résumé `dev-*` et cherche la
> preuve `file:line` lui-même. Ferme le gap "code compile + tests passent
> mais AC oubliée silencieusement". **100 % additif, opt-in via
> `SpecComplianceMode: full` (défaut `manual` = skip).** Comportement
> v6.4.2 préservé si non activé.

### Breaking
- Aucun. Mode par défaut = `manual` (= skip), identique v6.4.2.

### Added — Agent
- `agents/spec-compliance-reviewer.md` (~300 lignes, Sonnet 4.6) :
  vérification AC-par-AC indépendante. Pattern « Do not trust the report » :
  - **Ne lit pas** les rapports d'autres agents
  - **Ne fait pas confiance** au résumé `dev-*`
  - **Cherche evidence** `file:line` pour chaque AC
  - **Biaise vers `not_verified`** en cas de doute (zéro faux négatif)
  - Classifie les ACs en `testable_strict` / `testable_soft` / `ambiguous` / `ui_only`
  - Sévérité : critical (strict non vérifiée), serious (soft / partial), moderate (ui_only), minor (ambiguous / ui_present)
  - Token footprint cible : 8-15 KB / FEAT (Sonnet 4.6 sélectif)

### Added — Scripts Python
- `sdd_scripts/validate_spec_compliance.py` (~300 LOC, stdlib pur) :
  validateur déterministe du JSON émis par l'agent. Cohérence schéma
  (champs requis, types), cohérence arithmétique (`total == sum(issues) + verified`),
  cohérence verdict vs `SpecComplianceFailOn`. Exit codes 0/1/2.

### Added — Tests (25 nouveaux)
- `tests/test_validate_spec_compliance.py` (19 tests) : reports GREEN/WARN/RED,
  inconsistencies (total mismatch, verified mismatch, verdict drift, evidence
  missing, severity missing, invalid class/status, missing top-level keys),
  expected_verdict logic, CLI report-path mode
- `tests/test_phase_planner.py` (+6 tests `TestDecideSpecCompliance`) :
  off / manual / full enabled / full backend-only / full frontend-only / no code

### Added — Configuration
```yaml
## Project Config
SpecComplianceMode: off | full | manual     # default: manual (skip)
SpecComplianceFailOn: critical | serious | moderate | minor  # default: serious
```

### Added — Integration
- `commands/dev-run.md STEP 6.4` : 4e agent dans le batch parallèle (aux
  côtés de code-reviewer, accessibility-auditor, security-reviewer scan).
  Pattern identique, paths d'écriture disjoints, file-ownership matrix
  respectée.
- `python/sdd_scripts/phase_planner.py` : nouvelle phase `spec_compliance`
  avec `_decide_spec_compliance()` (off / manual / no-code → skip ;
  full + code → enabled). Token cost estimate 12_000 KB.
- `rules/error-classification.md §1.14` : nouvelles classes `[SPEC_*]` :
  - `[SPEC_AC_VERIFIED]` — info, success
  - `[SPEC_AC_NOT_VERIFIED]` — critical/serious/moderate selon class AC
  - `[SPEC_AC_PARTIAL]` — serious
  - `[SPEC_AC_AMBIGUOUS]` — minor (AC mal formulée)
  - `[SPEC_AC_UI_PRESENT]` — minor (UI cosmétique)
  - `[SPEC_NO_TARGETS]` — bloquant runtime (aucun fichier à inspecter)
- `rules/error-classification.md §3` : ajout de la ligne `[SPEC_*]` dans
  le tableau build_loop (toutes Itère: NON).

### Schema rapport
- `workspace/output/.sys/.validation/{n}-spec-compliance.{md,json}` :
  schéma stable validé par `validate_spec_compliance.py`. Pour chaque
  AC : `ac_id`, `ac_text`, `class`, `status`, `severity` (si non vérifiée),
  `evidence.{file, lines, snippet}` (si vérifiée), `reason` (si pas vérifiée).
- `summary.{verdict, total_acs, verified, issues}` avec invariant
  `total_acs == sum(issues) + verified`.

### Anti-duplication avec autres auditeurs
- vs `[PLAN_AC_COVERAGE_GAP]` (§1.2) : vérifie au niveau **plan** (file planifié),
  spec-compliance vérifie au niveau **code matérialisé** (AC réellement implémentée)
- vs `code-reviewer` : focus différent (qualité technique vs conformité spec)
- vs `[UI_FIDELITY_GAP]` : mesure pixel HTML→code, pas AC

### Design — Non-régression garantie
- Mode `manual` par défaut → skip → comportement v6.4.2 strict
- 4e agent dans STEP 6.4 = même pattern que les 3 existants (paths
  disjoints, idempotent, pas de build_loop)
- File-ownership matrix `audit_file_ownership.py` respectée (paths sous
  `.sys/.validation/` ignorés par IGNORE_PATTERNS)
- 258/258 tests passent (193 anciens + 40 v6.5.1 + 25 v6.5.2 nouveaux)

### Usage
```yaml
## Project Config
SpecComplianceMode: full
SpecComplianceFailOn: serious
```
```powershell
/sdd-full 1
# Rapport généré: workspace/output/.sys/.validation/1-spec-compliance.md
python .claude/python/sdd_scripts/validate_spec_compliance.py --feat 1
```

### Limitations connues
- Faux positifs sur ACs ambiguës (l'agent émet `[SPEC_AC_AMBIGUOUS]`
  minor — non bloquant — et suggère reformulation)
- Coût +12 KB/FEAT vs v6.4.2 lorsque activé (acceptable vs ROI : 1 AC
  rate manqué = 1 hotfix prod évité)
- Pas de mode `quick` en v6.5.2 (reporté v6.5.3+ après mesure réelle)

---

## [6.5.1] — 2026-05-15 (Real token telemetry, opt-in)

> Première brique de la roadmap v6.5 : capture **post-call** des tokens
> réellement consommés par chaque sub-agent. Permet de mesurer
> objectivement le ROI annoncé des optimisations (v6.4.1 -26 KB,
> v6.2 From-Plan Strict ×5 moins cher) sur N runs réels au lieu d'estimations.
> **100 % additif, opt-in via env var.** Si `SDD_TOKEN_USAGE_MODE=off`
> (défaut), comportement byte-identique vs v6.4.2.

### Breaking
- Aucun. Hook désactivé par défaut.

### Added — Hook telemetry
- `sdd_hooks/record_token_usage.py` (~210 LOC, stdlib pur) : capture
  les tokens depuis `tool_response.usage` (ou variantes) du payload
  Claude Code. Design **défensif multi-path** — essaie 6 emplacements
  candidats, tag la source dans `usage_source_path` pour forensics.
  Mode contrôlé par env `$SDD_TOKEN_USAGE_MODE` (`off`/`record`/`debug`).
- `sdd_scripts/report_token_usage.py` (~230 LOC) : agrégateur lisant
  `workspace/output/.sys/.audit/token-usage.jsonl`. Output Markdown +
  JSON. Filtres `--feat`, `--agent`, `--since`, `--us`. Health check :
  WARN si > 50% des entrées n'ont pas de `raw_usage_found` (signal
  que Claude Code n'expose pas usage dans le payload).

### Added — Tests
- `tests/test_record_token_usage.py` (24 tests) : payload parsing
  multi-path, extraction feat/us, mode off = no-op strict, modes
  record/debug, payload vide tolérancé.
- `tests/test_report_token_usage.py` (16 tests) : load ledger, filtres,
  aggregation, CLI JSON/Markdown, fichier output.

### Added — Configuration
- `settings.json` : 2 nouvelles entrées hooks (PostToolUse matcher
  `Agent` + SubagentStop matcher `dev-backend|dev-frontend|qa|dashboard`).
  Le hook se déclenche mais retourne immédiatement si mode=off.
- Env var `$SDD_TOKEN_USAGE_MODE` :
  - `off` (défaut) : silent skip, exit 0, équivalent v6.4.2
  - `record` : append entrées dans `token-usage.jsonl`
  - `debug` : record + dump payload full dans `.audit/token-debug/`

### Schema
- `workspace/output/.sys/.audit/token-usage.jsonl` : 1 entry JSON par
  ligne, atomic append via `acquire_with_retry` (réutilise
  `sdd_lib/file_locks.py`). Champs : `ts`, `hook_event`, `subagent_type`,
  `feat`, `us_id`, `model`, `input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, `cache_read_input_tokens`,
  `raw_usage_found`, `usage_source_path`.

### Design — Non-régression garantie
- Hook wrappé en try/except à tous les niveaux : aucune exception ne
  peut casser le pipeline. La telemetry est informational, jamais bloquante.
- Default mode `off` → silent skip avant tout I/O → comportement
  identique v6.4.2.
- Pour activer en PowerShell : `$env:SDD_TOKEN_USAGE_MODE = "record"`.
- Pour désactiver : retirer l'env var, ou retirer les 2 entrées hooks
  ajoutées dans settings.json.

### Tests — 233/233 passing
- 193 tests pré-existants : zéro régression
- 40 nouveaux tests : 24 (record) + 16 (report) tous verts

### Usage
```powershell
# Activer la telemetry pour cette session
$env:SDD_TOKEN_USAGE_MODE = "record"

# Lancer normalement
/sdd-full 1

# Générer le rapport
python .claude/python/sdd_scripts/report_token_usage.py --feat 1
python .claude/python/sdd_scripts/report_token_usage.py --json --feat 1 --output workspace/output/.sys/.audit/token-report-feat-1.md
```

### Limitations connues
- Si Claude Code n'expose pas `usage` dans `tool_response` du tool
  `Agent`, les entrées auront `raw_usage_found: false`. Le compteur
  d'invocations reste utile (nombre d'appels par agent/FEAT) mais
  les volumes ne sont plus disponibles. Le rapport émet un WARN
  explicite en haut quand ce taux dépasse 50%.
- Le mode `debug` peut générer de nombreux fichiers
  `payload-*.json` dans `.audit/token-debug/` — à nettoyer manuellement
  ou désactiver après inspection.

---

## [6.2.0] — 2026-05-15 (From-Plan Strict + Cache Discipline, opt-in)

> Système pro de matérialisation rapide via plan v2 validé déterministiquement.
> dev-* sur chemin chaud passe en Sonnet 4.6 (forks `*-strict`) au lieu d'Opus 4.7.
> Gain mesuré attendu : latence dev-* From-Plan ×3, coût tokens ×5 moins cher.
> **Opt-in** via `PlanCacheStrict: true` dans Project Config. Aucune régression
> sur projets v6.1 (défaut `false`).

### Breaking
- Aucun. Tout est additif et opt-in.

### Added — Format plan v2 strict-ready
- `rules/dev-shared.md §7.4.bis` : nouveau format plan v2 (frontmatter
  enrichi avec `plan-schema-version: 2`, `us-hash`, `claude-md-hash`,
  `capabilities-triggered`, `strict-ready: true` + section `## Inline
  Digest` auto-suffisante).
- `rules/dev-shared.md §7.6/§7.7/§7.8` : validation, dispatch
  strict/classic, invariants préservés en strict mode.
- Backward-compat v1 garantie : v1 plans restent lisibles, fallback
  automatique classic Opus si plan pas strict-ready.

### Added — Scripts Python
- `sdd_scripts/validate_plan.py` (~370 LOC, stdlib pur) : validation
  structurelle + strict-ready avec exit codes 0/1/2. 21 tests unitaires
  (`tests/test_validate_plan.py`).
- `sdd_scripts/compute_plan_metadata.py` (~150 LOC) : helper YAML/JSON
  pour générer v2 frontmatter (us-hash SHA-256, claude-md-hash,
  timestamp ISO, capabilities passthrough). 7 tests unitaires
  (`tests/test_compute_plan_metadata.py`).

### Added — Agents Sonnet 4.6 (forks minces)
- `agents/dev-backend-strict.md` (~280 lignes) : consomme un plan v2
  strict-ready, lecture minimale (plan + US, pas de re-Read stacks ni
  CLAUDE.md), build_loop identique. Refuse `:plan` (lance dev-backend),
  refuse v1 (fallback). Fallback `dev-backend` Opus si
  `[PLAN_DIGEST_INSUFFICIENT]`.
- `agents/dev-frontend-strict.md` (~300 lignes) : symétrique avec
  triple source de vérité préservée (US + HTML mockup + plan digest).
  Fidelity check post-build maintenu (load-bearing).

### Added — Configuration & orchestration
- `## Project Config > PlanCacheStrict: bool` (défaut `false` opt-in v6.2).
- `commands/dev-run.md STEP 6.0.bis` : routing strict (validate_plan
  --strict par US, MARK_STRICT[us,family], spawn dev-*-strict vs dev-*
  classique).
- `commands/dev-run.md STEP 6.a/6.c` : routing strict-aware + fallback
  automatique en cas de `[PLAN_DIGEST_INSUFFICIENT]`.
- `commands/dev-plan.md STEP 4.7` : auto-validation strict-readiness
  post-génération.

### Added — Observabilité
- `sdd_scripts/sdd_state.py` docstring : nouveaux event types canoniques
  (`plan_validate`, `plan_validate_postgen`, `plan_cache_evaluation`,
  `plan_cache_fallback`, `dev_backend_strict_*`,
  `dev_frontend_strict_*`). Aucun changement de schéma.
- `agents/dashboard.md §3.1` : nouveau widget §5 Plan Cache dans
  `README.html` (cache_rate par FEAT, répartition strict/classic/fallback,
  affichage conditionnel si events présents).

### Added — Taxonomie erreurs
- 12 nouveaux codes `[PLAN_*]` dans `rules/error-classification.md §1.2` :
  `PLAN_NOT_FOUND`, `PLAN_UNREADABLE`, `PLAN_NO_FRONTMATTER`,
  `PLAN_FRONTMATTER_INVALID`, `PLAN_MISSING_REQUIRED_FIELD`,
  `PLAN_FILES_SECTION_MISSING`, `PLAN_FILE_ENTRY_INVALID`,
  `PLAN_AUGMENT_CONTRACT_MISSING`, `PLAN_AC_COVERAGE_GAP`, `PLAN_STALE`,
  `PLAN_NOT_STRICT_READY`, `PLAN_DIGEST_INSUFFICIENT`.

### Changed — Émission v2 par défaut en mode `:plan`
- `agents/dev-backend.md §5.2` : émission v2 obligatoire en mode `:plan`
  (invocation de `compute_plan_metadata.py` + section `## Inline Digest`
  avec stack §1.3 mapping + CLAUDE.md extrait + schema.json entités).
- `agents/dev-frontend.md §6.4` : symétrique avec digest UI DS mapping
  et CLAUDE.md frontend extrait.

### Changed — Loader manifest
- `loader.yml` : 2 nouvelles entries `dev-backend-strict` et
  `dev-frontend-strict` avec reads minimaux, forbidden_reads explicites
  (stacks/CLAUDE.md interdits en strict), `fallback_to` documenté.

### Tests
- 28/28 unitaires verts (21 validate_plan + 7 compute_plan_metadata).
- Stdlib pur Python 3.10+, 0 dépendance externe (cohérent v6.1).

### Adoption recommandée (cf. `docs/DESIGN-FROMPLAN-STRICT.md §5`)
- **Phase A** (test isolé) : `PlanCacheStrict: true` sur 1 FEAT de
  référence + `/sdd-full {n} --plan` + comparer durée/tokens/qualité.
- **Phase B** (rollout par projet) : après validation Phase A.
- **Phase C** (défaut v6.3+) : promotion à `true` par défaut si bench
  concluant sur ≥ 5 projets, ≥ 2 mois.

### Notes de validation
- Invariants préservés : source-first, idempotence cross-machine,
  stateless agents, file ownership, anti-derive, build_loop, fidelity
  check, capabilities on-demand.
- Backward compat : projets v6.1 sans `PlanCacheStrict: true` aucun
  changement de comportement, aucune régression mesurée.

---

## [6.1.1] — 2026-05-13 (audit consolidation, anti-redondance, anti-derive doc)

> Itération de nettoyage suite à audit complet du framework. Aucun
> Breaking, aucun changement de comportement runtime. -507 lignes
> brutes sur le corpus rules+agents, substance load-bearing intacte
> (validation : `framework_smoke.py --strict` 67/67 OK,
> `validate_inline_rules.py` 0 drift).

### Changed — Compactage rules verbeuses
- `rules/error-classification.md` 246 → 189 L (-23 %) : taxonomie
  complète conservée, supprime tableau "Agents qui chargent" (doublon
  `loader.yml`), §6 "Ce que la règle n'impose pas" (philosophique),
  §7 réduit à 1 ligne. Exemples ERROR condensés (2 au lieu de 4).
- `rules/responsibilities.md` 286 → 216 L (-24 %) : sections
  Allowed/Forbidden condensées en bullet lists par rôle, sous-titres
  fusionnés. Détail `[FRONTEND_BACKEND_CONTRACT_GAP]` intact. Ajout
  §3 "Tech Lead Humain" explicite.
- `rules/file-ownership.md` 380 → 250 L (-34 %) : matrice ownership
  condensée (1 ligne par type au lieu de 2-3), §1.bis isolation
  Front/Back conservée intégralement (load-bearing), §6.bis BREAKING
  CHANGES exception en bullets, §3 ADR timestamp atomique conservé.

### Changed — Centralisation patterns dev-* (anti-duplication)
- `rules/dev-shared.md` 168 → 195 L : nouvelle §1.bis "Path safety
  Front/Back isolation" avec matrice par famille (back/front), absorbe
  les pré-checks autrefois dupliqués dans dev-backend/dev-frontend.
- `agents/dev-backend.md` 511 → 463 L : STEP 0.5 (context budget),
  STEP 1.bis (path safety), STEP 8.5 (BREAKING cleanup), section
  Anti-derive remplacés par références à `dev-shared.md §1/§1.bis/
  §3/§6`. Pas de comportement runtime modifié.
- `agents/dev-frontend.md` 627 → 579 L : idem (STEP 0.5, STEP 1.bis,
  STEP 11.5, Anti-derive).

### Changed — Compactage Phase D arch.md
- `agents/arch.md` 1171 → 1051 L (-10 %) : STEP 12.5/12.6/12.7
  densifiées (217 → ~97 L) sans perte de substance. Read-back v5.0
  conservé (anti-Edit silencieux). Externalisation en agent
  `constitutioner` envisagée mais rejetée (risque sans tests).

### Changed — Fusion library-policy → stack-completeness
- `rules/library-policy.md` 124 → 15 L : stub redirection. Substance
  migrée vers `rules/stack-completeness.md §0` (matrice runtime LTS,
  registries canoniques, CVE check par registre, ERROR
  `[STACK_RUNTIME_NOT_LTS]`).
- `rules/stack-completeness.md` 549 → 597 L (absorption +48 L).
- Pointeurs mis à jour : `CLAUDE.md §12`, `agents/arch.md:102`.

### Changed — Stack `blazor-server` marqué DEPRECATED
- `.claude/stacks/frontend/blazor-server.md` : statut **DEPRECATED
  (2026-05-13)** ajouté en haut. Pas de `.libs.json` catalog → les
  agents échoueraient à l'install. Recommandation : utiliser
  `blazor-webassembly` (split front/back canonique).

### Added — Helpers Python centralisés
- `sdd_lib/paths.py` : `iso_now()` exposé comme canonical UTC
  ISO-8601 avec `Z` suffix, seconde précision. Remplace 3 implémentations
  divergentes (migration progressive — `gate_decide.py` et
  `sdd_state.py` conservent leur format legacy pour compat consumers).

### Removed
- `.claude/templates/explain-po.prompt.md` (orphelin — jamais référencé
  par agent/command/hook).

### Fixed — Documentation
- `python/README.md` § "Scripts maintenance (hors pipeline)" déjà en
  place — distingue clairement les 5 outils Tech Lead (`framework_smoke`,
  `measure_batch`, `init_status_json`, `sync_stack_md`,
  `validate_libs_catalog`) des scripts pipeline. Pas de nouveau
  dossier `sdd_admin/` créé (la doc suffit).

### Notes de validation post-audit
- `/sdd-full` STEP 4 (délégation à `/dev-run`) déjà en place :
  ~26 lignes de pure orchestration, pas de duplication restante.
- `detect_arch_shortcircuit.py` (script déterministe migré 2026-05-13)
  consommé par `/dev-run` et `/sdd-full` sans redondance.

---

## [6.1.0] — 2026-05-11 (gated workflow, split modèles, gates manuels, short-circuit arch)

> Itération de robustesse / observabilité sur v6.0. Aucune Breaking côté
> FEAT ou US (rétrocompatible). Features étalées du 2026-05-07 au
> 2026-05-10, consolidées en v6.1.0.

### Added — Workflow gated back→API gate→front (2026-05-07)
- `.claude/rules/backend-first.md` : nouveau workflow par défaut.
  `/dev-run` exécute en séquence : (a) dev-backend ALL US parallèle,
  (b) QA API Gate (tests intégration HTTP, in-memory DB), (c)
  dev-frontend ALL US parallèle — uniquement si (b) 🟢. Élimine les
  mismatches silencieux frontend→backend (404 runtime sur routes
  inventées).
- `commands/qa-generate.md` mode `--mode api-tests` : génération
  WebApplicationFactory + EF Core InMemory + TestAuthHandler.
  Critère gate : `failed == 0 AND total >= 2 × N_endpoints`.
- `responsibilities.md §12` durci : interdiction stricte d'inventer
  une route HTTP backend côté frontend. Grep obligatoire avant tout
  client HTTP. ERROR `[FRONTEND_BACKEND_CONTRACT_GAP]` si endpoint
  manquant.
- Convention URL canonique backend : `/api/v{N}/{resource-kebab-pluriel}`.
  Pas de `/count`/`/exists` (total via `PagedOutput.TotalCount`,
  existence via 404 GET by id).

### Added — Catalogue machine `.libs.json` (2026-05-07)
- 14 stacks équipés de `{stack-id}.libs.json` (source de vérité
  versions/libs core/on-demand/triggers/plugins). Schéma
  `templates/libs-catalog.schema.json`.
- `.claude/scripts/validate-libs-catalog.ps1` + `sync-stack-md.ps1`
  (régénère §2.4 markdown depuis JSON).
- Dé-duplication QA : libs de tests purgées des catalogues backend
  (now dans `qa/*.libs.json` exclusivement).

### Added — Split modèles + dashboard agent (2026-05-08)
- `dev-backend` et `dev-frontend` passent en **Opus 4.7** (raisonnement
  fin sur génération de code, `preserves:`/`adds:`, layer mapping,
  fidélité HTML). po/arch/elicitor/qa restent en Sonnet 4.6.
- Nouvel agent `dashboard` (**Haiku 4.5**) : régénère
  `workspace/output/dashboard/README.html`, `context/adrs/INDEX.md`,
  `qa/feat-{n}/dashboard.html`. Auto en fin de `/sdd-full`,
  `/dev-run`, `/qa-generate` ; manuel via `/doc-refresh`.
- `.claude/rules/error-classification.md` : taxonomie 8 classes
  (`BUILD_CORRECTIBLE`/`BUILD_BLOCKING`/`SCHEMA_MISMATCH`/
  `LAYER_VIOLATION`/`UI_*`/`QA_*`/`DERIVE_*`/`STACK_*`/`NETWORK_*`...).
  Pilote `build_loop` : `[BUILD_CORRECTIBLE]` itère,
  `[BUILD_BLOCKING]` fail-fast.

### Added — Short-circuit arch FEATs ≥ 2 (2026-05-10)
- `commands/dev-run.md` STEP 4.bis : skip arch si bootstrap stable
  (CLAUDE.md projet présents, `workspace/output/db/schema.json` présent
  si DB, `stack.md` mtime ≤ mtime des CLAUDE.md). Émet 1 ligne
  `FEAT {n} — arch skip (bootstrap stable, …)`.
- Flag `--rebuild-arch` sur `/dev-run` et `/sdd-full` pour forcer
  l'invocation arch (changement schéma DB, ajout lib stack, modif
  Project Config, projet supprimé manuellement).

### Added — Gates manuels LOT 3 + console web (2026-05-10)
- 4 points d'arrêt humain optionnels : `afterUS`, `afterReadiness`,
  `afterPlan`, `afterCode`. Pilotage via `ManualGates: true|false|us,plan,code`
  dans `## Project Config` ou flag CLI `--manual-gates[=us,plan,code]`.
- `workspace/console/` : serveur Fastify (port 5173) +
  `status.json` centralisé avec lock partagé Node + PowerShell
  (`.status.lock`, O_EXCL, TTL 10s, retry 5×).
- `.claude/scripts/gate-decide.ps1` : pose-pending / set
  validated|skipped / read decision.
- Reprise pipeline via `/sdd-full {n} --resume`.

### Added — Observabilité Phase 0 (v6.1)
- `.claude/scripts/sdd-state.ps1` : émission `run-{id}.json` +
  `events.jsonl` append-only dans `workspace/output/.sys/.state/`.
- `commands/sdd-full.md` STEPs 1.quart, 3, 3.5, 4, 4.5, 4.7, 5 :
  `set-phase` aux bornes de phase. Pattern best-effort (non bloquant).
- Read mandatory `error-classification.md` ajouté aux agents arch,
  dev-backend, dev-frontend, qa (cf. `loader.yml` lignes 101, 158,
  214, 320).

### Added — Hardening QA (v6.1)
- `coverage_lines_pct < CoverageMin` produit désormais **🔴 RED
  bloquant** (`[QA_COVERAGE_GAP]`) au lieu du WARN non-bloquant v3.1.0.
  Bypass via `CoverageMin: 0` ou abaisser le seuil (décision tracée
  en git blame). Cf. `rules/qa-coverage.md §1`.
- Politique runtime LTS only : `.NET 10`, `Node 22 LTS`, `Java 21 LTS`,
  `Python 3.12`, `Kotlin 2.1`. STS interdits sans ADR explicite. Cf.
  `rules/library-policy.md §0`.

### Changed
- `commands/dev-run.md` STEP 5 : invocation arch désormais
  conditionnelle (`$arch_required`). STEP 6 séquence
  back → API gate → front (default `GatedWorkflow: true`).
  STEP 7 récap : ligne `Bootstrap + DB` distingue
  `init` / `invoked` / `skipped (short-circuit)`.
- `commands/sdd-full.md` STEP 4 : propagation `--rebuild-arch`,
  `--manual-gates`, `--resume`. Récap STEP 5 enrichi.
- `docs/workflow.md` §3 : mention du short-circuit et du gated workflow.
- `CLAUDE.md` §3 : tableau commandes enrichi avec nouveaux flags ;
  §4 ajout colonne "Quand invoqué" pour les agents support ;
  §8 mention gates manuels.

### Removed
- Commande `/sdd-clear` retirée (purge en masse non récupérable jugée
  dangereuse). Cleanup manuel documenté en `CLAUDE.md §3`.

### Pourquoi
v6.1 consolide **3 axes complémentaires** :
1. **Robustesse contractuelle** (API Gate, route invention interdite,
   catalogue libs JSON) — supprime les bugs silencieux frontend ↔ backend.
2. **Économie** (short-circuit arch, split modèles, dashboard Haiku) —
   sur FEATs ≥ 2 le bootstrap est skipé, les rendus déterministes
   passent sur Haiku 4.5.
3. **Industrialisation légère** (gates manuels via console, state
   tracking, error-classification, QA coverage gap bloquant) —
   prépare le terrain pour les revues humaines multi-équipes sans
   alourdir le pipeline en runs nominaux.

---

## [6.0.0] — 2026-05-06 (ultra-lean : 2 axes — suppression validator + scripts dev-*)

### Breaking (Point 1 — suppression validator)
- **Agent `validator` SUPPRIMÉ** — `/feat-validate` est désormais
  100% déterministe via PowerShell (`validate-readiness.ps1`).
  La validation sémantique (mesurabilité ACs, ambiguïtés cross-artefact,
  hypothèses implicites) est à la charge du PO humain lors de la
  review de la FEAT.
- `commands/feat-validate.md` STEP 4 (invocation validator) retiré.
  Décision finale = décision déterministe seule.
- `templates/readiness.template.md` §2 (validations sémantiques) :
  section vide ou absente.

### Removed
- `agents/validator.md` (supprimé)
- Section `validator:` dans `loader.yml` (remplacée par bloc explicatif)

### Added (Point 3 — compaction dev-* via scripts)
- `.claude/scripts/validate-fidelity.ps1` — externalise STEP 10+11
  de dev-frontend (vérif tokens hex 3 modes + libellés + composants DS)
- `.claude/scripts/mark-breaking-resolved.ps1` — externalise STEP 8.5
  (dev-backend) et STEP 11.5 (dev-frontend) — cleanup BREAKING CHANGES
- `.claude/scripts/acquire-libname-lock.ps1` — externalise la procédure
  de lock file L2 (file-ownership.md §4) pour LibName partagé

### Changed
- `CLAUDE.md` §4 : 4 cœur + 3 support → **4 cœur + 2 support** (validator retiré)
- `docs/architecture.md` §2 : suppression ligne validator du tableau modèles
- `docs/workflow.md` §2 : « agent validator (sémantique) » → « 100% déterministe »
- `commands/sdd-full.md` : « PHASE 2.6 (agent validator) » → « (PowerShell déterministe v6) »
- `agents/dev-backend.md` : 601 → 520 lignes (–13%)
  - STEP 8.5 réécrit en wrapper sur `mark-breaking-resolved.ps1`
  - STEP 5.bis condensé (capability detection)
  - Inline Rules compactées (~150 → ~50 lignes)
- `agents/dev-frontend.md` : 768 → 643 lignes (–16%)
  - STEP 10+11 fusionnés en wrapper sur `validate-fidelity.ps1`
  - STEP 11.5 réécrit en wrapper sur `mark-breaking-resolved.ps1`
  - Inline Rules compactées (~150 → ~50 lignes)
- Lock file procedure inlinée → invocation script `acquire-libname-lock.ps1`
- `framework-smoke.ps1` : retrait `validator` de expectedAgents (7 → 6),
  ajout 3 scripts (8 → 11 scripts attendus)
- `workspace/output/docs/presentation.html` :
  - Hero badge v5.0.0 → **v6.0.0 · Ultra-lean**
  - 7 agents → **6 agents** (4 cœur + 2 support)
  - Section role Validator supprimée
  - Step Readiness Gate : « 🤖 Validator » → « Script PS · 0 token »
- `workspace/output/docs/readme.html` : footer v5.0.0 → v6.0.0, summary mis à jour
- `loader.yml` version : `5.0.0` → `6.0.0`

### Économie tokens cumulée v6.0
| Source | Raw | Facturé (cache-aware) |
|---|---|---|
| Point 1 (validator retiré) | –1.4M | –400k |
| Point 3 (scripts dev-*) | –500k | –200k |
| **Total v6.0** | **–1.9M** | **–600k** |

Cible v6.0 : **~8.6M raw / ~2.4M facturés** (vs ~10.5M / ~3M en v5).
**Soit ~20% de réduction sur la facturation.**

### Trade-off assumé
- Plus de détection automatique d'ACs vagues (ex. *"le système est performant"*)
- Plus de détection de termes ambigus cross-artefact
- Plus de détection d'hypothèses implicites (auth, état initial, permissions)
- **Compensation** : review humaine du PO sur la FEAT + script déterministe
  qui détecte 80% des problèmes structurels (continuité IDs, traçabilité,
  stack, basenames HTML)

### Migration
- `/feat-validate` : ancienne séquence det + sem → nouvelle séquence det seule
- Section §2 du rapport readiness n'est plus produite (le script PS produit §1)
- Réintroduire validator localement : restaurer `agents/validator.md` +
  STEP 4 dans `commands/feat-validate.md` depuis git history < v6.0

---

## Versions antérieures (v4.x, v5.x)

Voir [`.claude/ARCHIVE/CHANGELOG-legacy.md`](ARCHIVE/CHANGELOG-legacy.md) pour
l'historique complet v4.0.0 et v5.0.0 (archivé le 2026-05-13 pour
alléger ce fichier).

Pour les versions v1.x → v3.x, voir l'historique git.
