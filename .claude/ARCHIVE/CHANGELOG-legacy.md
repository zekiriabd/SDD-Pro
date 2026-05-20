# SDD_Pro — CHANGELOG legacy (v4.x, v5.x)

> Versions antérieures à v6.0. Archivé le 2026-05-13 depuis `.claude/CHANGELOG.md`
> pour alléger le fichier principal (le framework v6.1+ est rétrocompatible
> v6.0 mais pas v5.x : voir `ARCHIVE/MIGRATION-legacy.md` pour migrer).

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
- I3 — Mentions « ~5 KB tokens » obsolètes dans `commands/feat-validate.md`
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
- Baseline v4.0.0 sur pvlist (1 FEAT, ~5 US) : ~12.2M tokens input,
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
