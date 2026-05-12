# SDD_Pro — CHANGELOG

Format : [version] — date courte. Sections : `Breaking`, `Added`, `Changed`, `Fixed`, `Removed`.

---

## [6.1.0] — 2026-05-11 (gated workflow, split modèles, gates manuels, short-circuit arch)

> Itération de robustesse / observabilité sur v6.0. Aucune Breaking côté
> SPEC ou US (rétrocompatible). Features étalées du 2026-05-07 au
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

### Added — Short-circuit arch SPECs ≥ 2 (2026-05-10)
- `commands/dev-run.md` STEP 4.bis : skip arch si bootstrap stable
  (CLAUDE.md projet présents, `workspace/output/db/schema.json` présent
  si DB, `stack.md` mtime ≤ mtime des CLAUDE.md). Émet 1 ligne
  `SPEC {n} — arch skip (bootstrap stable, …)`.
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
  `events.jsonl` append-only dans `workspace/output/.state/`.
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
   sur SPECs ≥ 2 le bootstrap est skipé, les rendus déterministes
   passent sur Haiku 4.5.
3. **Industrialisation légère** (gates manuels via console, state
   tracking, error-classification, QA coverage gap bloquant) —
   prépare le terrain pour les revues humaines multi-équipes sans
   alourdir le pipeline en runs nominaux.

---

## [6.0.0] — 2026-05-06 (ultra-lean : 2 axes — suppression validator + scripts dev-*)

### Breaking (Point 1 — suppression validator)
- **Agent `validator` SUPPRIMÉ** — `/spec-validate` est désormais
  100% déterministe via PowerShell (`validate-readiness.ps1`).
  La validation sémantique (mesurabilité ACs, ambiguïtés cross-artefact,
  hypothèses implicites) est à la charge du PO humain lors de la
  review de la SPEC.
- `commands/spec-validate.md` STEP 4 (invocation validator) retiré.
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
- **Compensation** : review humaine du PO sur la SPEC + script déterministe
  qui détecte 80% des problèmes structurels (continuité IDs, traçabilité,
  stack, basenames HTML)

### Migration
- `/spec-validate` : ancienne séquence det + sem → nouvelle séquence det seule
- Section §2 du rapport readiness n'est plus produite (le script PS produit §1)
- Réintroduire validator localement : restaurer `agents/validator.md` +
  STEP 4 dans `commands/spec-validate.md` depuis git history < v6.0

---

## [5.0.0] — 2026-05-06 (token-lean + robustesse)

### Breaking
- Aucun (v5.0 est rétrocompatible v4 — les changements sont internes
  à la mécanique des agents et `loader.yml`).

### Added
- **Inline Rules** dans tous les agents (po, arch, validator, elicitor,
  qa, dev-backend, dev-frontend) — substance opérationnelle de
  `responsibilities.md`, `stack-completeness.md`, `file-ownership.md §1-§2`,
  `qa-ownership.md`, `qa-coverage.md`, `us-granularity.md`,
  `.claude/rules/constitution.md` inlinée pour éviter les Read mandatory.
- **STEP 0 HARD-GATE pre-flight** dans `dev-backend.md` et `dev-frontend.md`
  (Phase A checks sans lecture + Phase B checks après stack.md).
  Variables d'invocation (`PLAN_ONLY`, `{Name}`, `HTML_PATH`) extraites
  en Phase A pour usage immédiat en Phase B / STEPs suivants.
- **STEP 12.6 read-back validation** dans `arch.md` — vérifie que les
  Edits sur constitution.md §4/§6 ont pris effet (modèle copié de
  po STEP 8.5.4, incident historique pvlist).
- **`.claude/docs/`** créé : split du CLAUDE.md monolithique en 3 fichiers
  `architecture.md` / `workflow.md` / `conventions.md` chargés à la demande.
- **`.claude/scripts/measure-batch.ps1`** — parse les session logs Claude Code
  et agrège tokens par commande (instrumentation baseline).
- **`.claude/scripts/detect-capabilities.ps1`** — workload déterministe
  pour la détection des capabilities §2.4.b (remplace ~70 lignes de
  prose LLM dans dev-backend STEP 5.bis).
- **`.claude/scripts/validate-inline-rules.ps1`** — détecte le drift
  mtime entre rule files et inline rules dans les agents.
- **`.claude/rules/library-policy.md`** — politique CVE/origine/version
  extraite de `arch.md` (substance v2.2 préservée, désormais on-demand).
- **`BuildLoopMaxIter`** — paramètre Project Config (default 3, range
  1-10) pour configurer la limite d'itérations du build loop dev-*.
- **`HexToleranceMaxPct`** — paramètre Project Config (default 5, range
  0-20) pour la tolérance RGB euclidienne du fidelity check.
- **Match tolérance + Match primitive DS** dans STEP 10 fidelity check
  de dev-frontend (3 modes : exact, tolérance ±X%, primitive DS).

### Changed
- **`.claude/CLAUDE.md`** : 577 → 198 lignes (slim entry point, le détail
  vit dans `docs/`).
- **`.claude/loader.yml`** : version bumpée 4.0.0 → 5.0.0 ; markers v5.0
  standardisés ; bloc en-tête « Sérialisation des writes constitution.md »
  + bloc « Convention de langue » documenté.
- **STEPs absorbés** dans dev-backend (STEP 2) et dev-frontend (STEPs 2-3) :
  la localisation US et la détection HTML sont absorbées par HARD-GATE
  Phase A. Numérotation STEP 3+ / STEP 4+ conservée pour compat refs.
- **`commands/dev-backend.md` et `dev-frontend.md`** STEPs 2-4 : marqués
  « (délégué à l'agent v5.0) » — plus de duplication des checks avec
  HARD-GATE de l'agent.
- **`workspace/input/stack/stack.md`** : lu UNE FOIS en STEP 0 Phase B (plus de
  Re-Read en STEP 3/4 ni en STEP 5.bis.2) — économie ~3-5k tokens/dispatch.
- **STEP 5.bis dev-backend** : externalisé en script PowerShell
  (`detect-capabilities.ps1`). L'agent invoque + parse JSON, ne fait
  plus la regex matching lui-même.

### Fixed
- C1 — Lecture double de `workspace/input/stack/stack.md` dans dev-backend et
  dev-frontend (HARD-GATE Phase B + STEP 3/4) supprimée.
- C2 — Fiction "lazy load" de constitution.md dans validator
  supprimée (lecture honnêtement systématique « si présent »).
- C3 — Aucune validation read-back après writes constitution.md dans
  arch (ajout STEP 12.6).
- C4 — `HTML_PATH` utilisée en Phase B mais déclarée en STEP 1
  (variable maintenant set explicitement en Phase A check A4).
- W1 — `arch.md` 1004 → 1055 lignes (politique librairies extraite,
  Inline Rules condensées). Reste lourd mais owns la complexité.
- W2 — Inline Rules `us-granularity` enrichie avec les 5 anti-patterns
  détaillés et exemples + clause « Quand Read le fichier complet » sur
  les inline rules sensibles.
- W3 — Drift mtime entre rules et inline rules : détecté par
  `validate-inline-rules.ps1`.
- W4 — Mention « validation fine de l'argument » trompeuse dans
  STEP 0 → renommée en « détection mode From Plan ».
- W5 — Scope QA stack-completeness élargi : tous stacks actifs
  (qa + backend + frontend + ui + auth) au lieu de QA seul.
- W6 — STEP 5.bis externalisé en script (cf. Added).
- W7 — Placeholders STEP 2/3 « (absorbé v5.0) » ajoutés dans dev-*
  pour fluidifier la lecture humaine.
- I1 — `CLAUDE.md` §4 split en 4 cœur + 3 support avec colonnes
  Phase / Quand invoqué.
- I2 — `loader.yml` markers v5.0 standardisés (format unique).
- I3 — Mentions « ~5 KB tokens » obsolètes dans `commands/spec-validate.md`
  retirées. STEPs 2-4 dev-* commands marqués « (délégué à l'agent v5.0) ».
- I4 — `docs/conventions.md` §13 (capabilities) + §14 (rules index) mis
  à jour avec les ajouts v5.0.
- I5 — Sérialisation writes constitution.md documentée en en-tête
  `loader.yml`.
- I6 — Mix FR/EN documenté comme intentionnel (pas un bug).
- I7 — Auto-référence circulaire dans dev-frontend STEP 11.1
  (« depuis STEP 4.1 ») corrigée (« depuis STEP 4 item 2 »).

### Removed
- **Read mandatory** de `responsibilities.md`, `stack-completeness.md`,
  `us-granularity.md`, `qa-ownership.md`, `qa-coverage.md`,
  `file-ownership.md`, `.claude/rules/constitution.md` dans les STEPs
  d'amorce des agents (substance inlinée — économie ~16-25k tokens
  par dispatch dev-* / par invocation des agents support).

### Métriques mesurées
- Baseline v4.0.0 sur pvlist (1 spec, ~5 US) : ~12.2M tokens input,
  ~73k output, 97.4% cache hit.
- Cible v5.0 estimée : ~10.5-11M tokens (–10-15%).
- Mesure réelle v5.0 : à effectuer post-merge.

---

## [4.0.0] — 2026-04-XX (HTML direct, suppression agent UI)

### Breaking
- **Suppression agent UI + Phase 3 UI** : les maquettes ne sont plus
  des PNG analysées par un agent intermédiaire mais des **fichiers
  HTML statiques** déposés dans `workspace/input/ui/{n}-{m}-{Name}.html`. L'agent
  `dev-frontend` lit l'HTML directement et le traduit vers le DS via
  mapping §2 + §7 du stack UI.
- **Suppression `workspace/output/ui/`** : plus de markdown UI intermédiaire.
- **Suppression `/ui-generate`** : commande retirée.

### Added
- Stack UI §7 « Mapping HTML → composant DS » dans chaque
  `.claude/stacks/ui/*.md`.
- Fidelity check text-based (STEP 11) : grep des libellés / structures
  HTML dans le markup généré (remplace fidelity pass vision v3).

### Changed
- `dev-frontend` lit `workspace/input/ui/{n}-{m}-*.html` directement (texte, pas
  vision multimodale).
- Triple source de vérité : HTML mockup (visuel) > Stack UI §2/§7
  (mapping DS) > US (workflow).

---

## Versions antérieures

Voir l'historique git pour les détails v3.x (constitution + ADRs,
readiness gate, élicitation structurée, QA agent, capabilities
on-demand).
