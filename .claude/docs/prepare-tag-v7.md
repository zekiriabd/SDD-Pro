# Runbook — Préparer tag `v7.0.0-rc1`

> Procédure prête-à-l'emploi pour valider et tagger v7.0.0-rc1 après la
> session de fixes 2026-05-20. Toutes les actions ci-dessous sont **côté
> utilisateur** (CLI Claude Code, git, budget API Anthropic).

---

## 1. Commit + push (30 min)

```bash
cd g:/Developement/SDD-Pro

# Vérifier état working tree
git status -s | wc -l                                # devrait être ~90 fichiers

# Option A : 1 méga-commit (rapide)
git add -A
git commit -m "$(cat <<'EOF'
feat(v7.0.0-alpha): consolidation post-audit CTO 2026-05-20

50+ fixes cross-couches :
- R1 cost cap hard-block (preflight_cost_cap.py)
- R2 FEAT_HASH check câblé (preflight.py::_check_feat_hash)
- R3 path normalization dédup (sdd_review.py)
- R4 atomic write helper (sdd_lib/atomic_write.py + build-and-loop §2.bis)
- R5 sweep 8 stubs backward-compat + 2 principes relocés docs/principles/
- Layered Kahn batching strict (validate_us_deps --layered-batches)
- Hooks security strict en CI auto-detect
- Token telemetry config-aware + run_id scope + failure alert
- API gate statuts canoniques (PASS/WARN/FAIL/SKIPPED/INFRA_BLOCKED)
- Spec-compliance gate avant feat-validate
- Anti-cumul bypass (SDD_ALLOW_FORCE env)
- QaFailOnSddFull + SecurityScanEnabled defaults durcis
- BuildLoopMaxCostUsd cap absolu
- Console.db migrations v2 (qa_mutation) + v3 (qa_e2e)
- Mutation testing + Playwright stacks opt-in
- arch.md trim 751→577 (-23%) via phase-a + phase-c sub-docs
- node_modules orphelin 37 MB purgé + .gitignore renforcé

Tests : 782/782 pytest + 79/79 smoke + 0 erreur libs-catalog
Cf. .claude/docs/roadmap-v7-v8.md + .claude/MIGRATION.md v6→v7
EOF
)"

# Option B : commits logiques séparés (recommandé pour PR review)
# Voir section §1.bis pour le découpage

git push origin next
```

### 1.bis Découpage commits (recommandé)

Si tu préfères des commits atomiques pour review :

```bash
# Cleanup
git add node_modules .gitignore
git rm -r --cached node_modules 2>/dev/null
git commit -m "chore: purge node_modules orphelin 37MB + .gitignore renforcé"

# Sweep stubs
git add .claude/rules/ .claude/docs/principles/
git commit -m "refactor(rules): supprime 8 stubs backward-compat + relocate 2 principes"

# Migration refs dans agents/commands/python/stacks
git add .claude/agents/ .claude/commands/ .claude/python/ .claude/loader.yml .claude/stacks/
git commit -m "refactor(refs): migrate Read @.claude/rules/X.md vers fichiers consolidés"

# Hooks + scripts P0 critical fixes
git add .claude/python/sdd_hooks/ .claude/python/sdd_lib/ .claude/python/sdd_scripts/preflight.py .claude/python/sdd_scripts/sdd_review.py .claude/python/sdd_scripts/validate_us_deps.py .claude/python/sdd_scripts/phase_planner.py .claude/python/sdd_scripts/mark_breaking_resolved.py .claude/python/sdd_scripts/sdd_state.py
git commit -m "fix(p0): R1-R5 cost cap + FEAT_HASH + dédup + atomic + bypasses"

# Config + classes erreur + docs
git add .claude/config.base.yml .claude/rules/error-classification.md .claude/rules/build-and-loop.md .claude/rules/quality.md .claude/rules/ownership.md .claude/rules/library-and-stack.md
git commit -m "config(v7.0.0): 15+ flags layered + classes erreur cross-couches"

# Tests + scripts admin
git add .claude/python/tests/ .claude/python/sdd_admin/
git commit -m "test(v7.0.0): +12 tests nouveaux (ownership sync, atomic, dedup, hooks)"

# Docs + roadmap + CHANGELOG
git add .claude/CHANGELOG.md .claude/CLAUDE.md .claude/MIGRATION.md .claude/docs/
git commit -m "docs(v7.0.0): MIGRATION v6→v7 + roadmap-v7-v8 + cache-strategy"

# Templates + stacks opt-in
git add .claude/templates/ .claude/stacks/qa/mutation-testing.* .claude/stacks/qa/playwright.md
git commit -m "feat(v7.0.0): stacks opt-in (mutation, playwright) + CI templates"

# Settings hooks
git add .claude/settings.json
git commit -m "config(hooks): ajout preflight_cost_cap dans PreToolUse.Agent"

# Reports ROI
git add workspace/output/qa/
git commit -m "feat(roi): rapport ROI réel mesuré FEAT 2 (\$23.76, cache 40.8%)"

# Push final
git push origin next
```

---

## 2. PoC ROI variance — 3 runs (~$75 + 2-3h)

**Pré-requis** : commit fait (sinon les fixes ne sont pas actifs lors des runs).

### 2.1 Préparer l'environnement

```bash
# (Option) Cold start : forcer cache à zéro pour mesurer dans le pire cas
rm -rf workspace/output/src/{CMSPrintBack,CMSPrintFront}/   # backup d'abord si critique

# Vérifier config TokenUsageMode = record (fix critique session)
python -c "
import sys; sys.path.insert(0, '.claude/python')
from sdd_lib.layered_config import read_layered_config
print('TokenUsageMode :', read_layered_config().get('TokenUsageMode'))
print('MaxCostPerRun  :', read_layered_config().get('MaxCostPerRun'))
"
# Doit afficher : 'record' et '50.00'
```

### 2.2 Lancer les 3 runs

Choisir une FEAT M (3 US fullstack standard, ex. FEAT 2) :

```bash
# Run 1 — cold cache
/sdd-full 2
sleep 30   # éviter cache prompt 5min cross-run

# Run 2 — partiellement caché
/sdd-full 2 --rebuild-arch
sleep 30

# Run 3 — caché chaud
/sdd-full 2 --rebuild-arch
```

**Coût estimé** : ~$25/run × 3 = **~$75**.
**Wall-clock estimé** : ~30-50 min/run × 3 = **~2-3h**.

### 2.3 Vérifier verdict release

```bash
python -m sdd_admin.run_roi_variance --feat 2

# Output attendu si ELIGIBLE :
#   # SDD_Pro ROI Variance — FEAT 2 (v7.0.0 release-critical)
#   ...
#   ## Verdict release v7.0.0
#   **ELIGIBLE** — toutes métriques sous seuil variance + ≥ 3 runs.
#   Tag v7.0.0 final autorisé (sous réserve revue 2 mainteneurs).
```

Si **NOT_ELIGIBLE** :
- Si variance > 15% : investigue l'outlier (logs `console.db events`)
- Si < 3 runs détectés : relance ceux manquants

---

## 3. Tag v7.0.0-rc1

```bash
# Vérifier branche
git branch --show-current        # doit être 'next'

# Tag annoté
git tag -a v7.0.0-rc1 -m "$(cat <<'EOF'
SDD_Pro v7.0.0-rc1 — release candidate

Critères release validés :
- 782/782 pytest verts
- 79/79 smoke strict
- PoC ROI variance ≤ 15% sur 3 runs FEAT M
- 0 ref orpheline @.claude/rules/<stub>
- Tous risques 🔴 critiques audit CTO 2026-05-20 fermés

Reste avant v7.0.0 final :
- Revue 2 mainteneurs (governance ADR governance-major-*)
- Sortie freeze main 2026-06-18

Cf. .claude/docs/roadmap-v7-v8.md + .claude/MIGRATION.md
EOF
)"

git push origin v7.0.0-rc1
```

---

## 4. Revue 2 mainteneurs post-freeze (2026-06-19)

Politique freeze v6.10.4-LTS (cf. `.claude/VERSIONING.md §4`) :
- `main` gelée jusqu'au 2026-06-18 — interdit MAJOR/MINOR
- `next` v7.0.0-rc1 doit être validée par **2 mainteneurs**
- ADR `governance-major-*` requis pour merge dans main

### Checklist mainteneur

- [ ] Lecture `.claude/CHANGELOG.md` § Unreleased v7.0.0
- [ ] Lecture `.claude/MIGRATION.md` v6→v7
- [ ] Lecture `.claude/docs/roadmap-v7-v8.md`
- [ ] Vérification rapport ROI `workspace/output/qa/roi-variance-feat-2.{md,json}`
- [ ] Vérification 5 ADRs governance-major-* présents dans
      `workspace/output/.sys/.context/adrs/`
- [ ] Run `framework_smoke.py --strict` local + comparaison résultat
- [ ] Approve ou request changes

### Merge dans main

```bash
git checkout main
git merge --no-ff next -m "merge: v7.0.0-rc1 → main (post-freeze, 2 mainteneurs OK)"
git tag -a v7.0.0 -m "SDD_Pro v7.0.0 — final release"
git push origin main v7.0.0
```

---

## 5. Post-tag — v7.1 planning

Items P1 différés (cf. `roadmap-v7-v8.md`) :
- arch.md trim phase 3 (split STEP 12.5)
- STEP numbering refacto cosmétique
- Test units pour `preflight._check_feat_hash` (helper récent)
- Cross-model validation QA (Opus review Sonnet) — gros chantier

Items P2 stratégiques v8 (Q3 2026) :
- 3 combos supplémentaires validés (.NET+vue, python+react, kotlin+vue)
- Mémoire Claude scoped Tech Lead (MCP server-side)
- Console web packagée
- Mutation testing PoC validation réelle sur 1 FEAT

---

*Runbook v7.0.0-alpha, généré 2026-05-20. À mettre à jour à chaque release MAJOR.*
