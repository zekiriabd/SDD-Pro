# SDD_Pro — Python engine (cross-platform)

> Engine déterministe pour SDD_Pro v7.0.0+. Tous les hooks Claude Code,
> scripts agent-invoked, validateurs, ingest CI et outils Tech Lead sont
> en Python pur (stdlib uniquement — pas de pip install requis pour le
> runtime nominal).

## Prérequis

- **Python 3.10+** (stdlib uniquement pour le runtime nominal — pas de
  dépendance pip pour exécuter le pipeline)
- Optionnel : **pytest + pytest-cov** pour exécuter la suite de tests
  (`pip install pytest pytest-cov`)

```bash
python --version   # ou python3 — doit être ≥ 3.10
```

## Installation — éditable (recommandé Sprint 3-5 audit closure 2026-06-07)

Avant le Sprint 3-5, chaque script avait son propre `sys.path.insert(0, ...)`
hack (~69 occurrences + 215 `noqa: E402`) pour pouvoir importer `sdd_lib`
sans installation. Cela fonctionnait mais cassait IDE-completion, mypy
cross-package, et coûtait quelques ms par invocation.

**Workflow recommandé v7.0.2+** — installer en mode éditable :

```bash
# Depuis la racine du repo SDD_Pro
pip install -e .claude/python
```

Cela rend les packages `sdd_lib`, `sdd_scripts`, `sdd_hooks`, `sdd_admin`
importables nativement (pas de sys.path hack côté caller). Les scripts
continuent à fonctionner avec les anciens callers (`python .claude/python/sdd_scripts/X.py`)
ET avec la nouvelle CLI entry-point (`sdd-smoke` directement après install).

### Vérification install

```bash
python -c "import sdd_lib.paths ; print(sdd_lib.paths.iso_now())"
sdd-smoke   # CLI entry-point installé par pip install -e .
```

### Migration progressive (out-of-scope Sprint 3-5)

Le retrait des 69 `sys.path.insert` + 215 `noqa: E402` est planifié
**v7.1 progressif** (1 fichier touché = 1 cleanup, pas de big-bang).
La double-compat est assurée : ces hacks deviennent no-op quand le
package est déjà sur `sys.path` via `pip install -e .`.

## Layout (refresh 2026-06-07 audit consolidé Sprint 2)

```
.claude/python/
├── sdd_lib/              # 21 modules helpers partagés (paths, exit_codes,
│                         #   atomic_write, file_locks, project_config,
│                         #   layered_config, console_db/, migrations/...)
├── sdd_hooks/            # 13 hooks Claude Code (cf. tableau ci-dessous)
├── sdd_scripts/          # 50 scripts agent-invoked / CLI pipeline
├── sdd_admin/            # 15 outils Tech Lead (smoke, sync, validateurs)
├── tests/                # 88 fichiers test pytest
├── _hook.py              # Bootstrap loader cwd-independent pour settings.json
├── sitecustomize.py      # Auto-import de .claude/python/ sur sys.path
└── pyproject.toml        # Config pytest + ruff + mypy + coverage
```

**Compteurs réels au 2026-06-07** : 50 scripts + 13 hooks + 15 admin + 21 lib =
**99 modules `.py` actifs** + 88 tests. Pour vérifier en live :

```bash
echo "scripts: $(ls .claude/python/sdd_scripts/*.py | grep -v __init__ | wc -l)"
echo "hooks:   $(ls .claude/python/sdd_hooks/*.py | grep -v __init__ | wc -l)"
echo "admin:   $(ls .claude/python/sdd_admin/*.py | grep -v __init__ | wc -l)"
echo "lib:     $(find .claude/python/sdd_lib -name '*.py' | grep -v __init__ | wc -l)"
echo "tests:   $(ls .claude/python/tests/test_*.py | wc -l)"
```

## Exit codes (cf. `sdd_lib/exit_codes.py` — SSoT v7.0.0)

Convention canonique unifiée pour tous les scripts `sdd_scripts/` et `sdd_admin/` :

| Exit | Constante | Sens | Comportement caller attendu |
|---:|---|---|---|
| `0` | `SUCCESS` | operation completed, side-effects applied | continue |
| `1` | `FAIL_FAST` | erreur bloquante non-correctible (config, contrat) | STOP + ERROR |
| `2` | `CORRECTIBLE` | erreur récupérable par retry/edit (build, lint) | retry `BuildLoopMaxIter` |
| `3` | `INFRA_BLOCKED` | outil/DB/réseau down (pas une régression code) | STOP + ERROR différent |

**Protocole hooks Claude Code distinct** (`sdd_hooks/` uniquement) :

| Exit | Constante | Sens |
|---:|---|---|
| `0` | `HOOK_ALLOW` | allow (continuer normalement) |
| `2` | `HOOK_DENY` | deny/block (afficher stderr à l'utilisateur, bloquer l'action) |

> ⚠️ Ne pas confondre `CORRECTIBLE = 2` (SDD scripts) avec `HOOK_DENY = 2`
> (hooks Claude Code) — sémantiques totalement différentes selon le contexte
> d'invocation. Les hooks utilisent exclusivement `HOOK_ALLOW`/`HOOK_DENY`.

**Dérogations granulaires documentées** (exit 4/5 préservés par design pour
classification d'erreur fine — cf. docstring `exit_codes.py` §"Cas hors convention") :
- `mark_breaking_resolved.py` : ✅ MIGRÉ v7.0.0 conforme (0=SUCCESS, 3=INFRA)
- `validate_us_deps.py` : 3=cycle, 4=missing ref, 5=infra
- `set_us_status.py` : 1-5 granulaire (US_NOT_FOUND, US_STATUS_INVALID, ...)
- `sdd_review.py` : 2=invalid arg, 3=sources missing
- `phase_planner.py` : 2=STACK_MALFORMED
- `bench_run.py` : 4=snapshot-before unreadable (audit Sprint 2 closure)
- `ingest_axe.py` / `ingest_lighthouse.py` : 4=verdict RED sans `--no-fail`
- `compute_us_complexity.py` : 5=I/O error sur écriture metadata
- `migrate_us_v1_to_v2.py` : 5=migration partielle (≥ 1 file en erreur)

## Hooks Claude Code (13 — déclarés dans `.claude/settings.json`)

| Hook | Trigger | Bloquant ? | Rôle |
|---|---|---|---|
| `protect_framework.py` | PreToolUse `Edit\|Write\|MultiEdit` | non (WARN stderr) | WARN si un agent touche un fichier framework |
| `pre_write_lint.py` | PreToolUse `Write\|Edit` | non (WARN) | Détection précoce BOM/encoding/EOF avant write |
| `preflight_agent_budget.py` | PreToolUse `Agent` | selon `$SDD_BUDGET_MODE` | Vérifie le budget tokens avant invocation sub-agent |
| `preflight_cost_cap.py` | PreToolUse `Agent` | oui (`[COST_CAP_EXCEEDED]` ≥ MaxCostPerRun) | Bloque le run si cumul USD dépasse cap |
| `preflight_glob_scope.py` | PreToolUse `Glob\|Grep` | non (WARN) | Détection patterns Glob trop larges (scope drift) |
| `preflight_stack_combo.py` | PreToolUse `Agent` | oui si combo non listé SLA sans `SDD_ALLOW_UNTESTED_COMBO=1` | Vérifie que le combo actif appartient aux 13 SLA |
| `validate_augment_contract.py` | PostToolUse `Edit\|Write\|MultiEdit` | **oui** (exit 2 sur violation) | Vérifie contrats `preserves:`/`adds:` du plan |
| `validate_stack_consistency.py` | PostToolUse `Write` (sur `.libs.json`) | oui sur drift | Cross-check `.md` ↔ `.libs.json` à l'édition |
| `validate_acceptance_gate.py` | SubagentStop matcher=`qa` | oui (`[ACCEPTANCE_GATE_FAILED]` mode strict) | Test/lint/build/coverage/smoke/E2E gate |
| `block_env_bypass.py` | PreToolUse `Bash` | oui si `export SDD_*=1` détecté sans audit-log | Empêche bypass silencieux env vars |
| `record_token_usage.py` | PostToolUse `Agent` | non | Ingest `<usage>` Anthropic API → console.db token_usage |
| `resolve_po_hash_sentinel.py` | SubagentStop matcher=`po` | non | Résout `COMPUTE_REQUIRED` sentinel posé par agent `po` |
| `audit_file_ownership.py` | SubagentStop | non (log append-only) | Audit matrice `ownership.md §1` post-dispatch |

### Variables d'environnement runtime

| Variable | Valeurs | Défaut | Effet |
|---|---|---|---|
| `SDD_BUDGET_MODE` | `off` / `warn` / `strict` | `warn` | `off` = hook désactivé ; `warn` = ledger + stderr WARN, exit 0 ; `strict` = bloque l'invocation d'agent (exit 2) si budget dépassé |
| `SDD_USER_EMAIL` | email | (vide) | Identifie le validateur lors des gates manuels (`gate_decide.py set --answered-by`) |
| `SDD_REPO_ROOT` | absolute path | (auto-detect) | Override repo root pour CI/tests/multi-repo (honoré inconditionnellement, cf. `paths.repo_root()`) |
| `SDD_ALLOW_FORCE` | `1`/`true`/`yes`/`on` | (off) | Autorise cumul ≥ 2 bypass flags `/sdd-full` (cf. `commands/sdd-full.md §1.bis`) |
| `SDD_ALLOW_UNTESTED_COMBO` | `1`/`true` | (off) | Permet l'invocation d'un combo non listé dans les 13 SLA (audit-loggué) |
| `SDD_ALLOW_ACCEPTANCE_BYPASS` | `1` | (off) | Skip acceptance gate finale (debug uniquement, audit-loggué) |
| `SDD_DISABLE_COST_CAP` | `1` | (off) | Désactive le hard cap `MaxCostPerRun` (debug, audit-loggué) |
| `SDD_FORCE_REASON` | texte libre | (vide) | Raison du bypass tracée dans `workspace/output/.sys/.audit/force-bypass.log` |

## Outils Tech Lead — `sdd_admin/` (15 scripts)

Outils opt-in humain, jamais invoqués par le pipeline. À utiliser sur
édition manuelle du framework, audit ou debug :

| Script | Rôle | Quand l'utiliser |
|---|---|---|
| `framework_smoke.py` | Smoke check end-to-end du framework (88+ checks) | Avant release / après refactor profond |
| `validate_libs_catalog.py` | Valide les `.libs.json` contre le schéma JSON + cohérence | Après édition d'un catalogue stack |
| `validate_stack_md_headers.py` | Vérifie headers `Validation:` des `.md` stacks | Après ajout/downgrade d'un stack |
| `validate_inline_rules.py` | Vérifie que les règles inlinées dans agents/ matchent les rules/ SSoT | Après modification d'une règle load-bearing |
| `validate_templates.py` | Vérifie l'intégrité des `templates/*.template.md` | Après édition template |
| `sync_stack_md.py` | Régénère §2.4 du `.md` depuis le `.libs.json` | Après mise à jour d'un `.libs.json` |
| `measure_batch.py` | Mesure tokens/durée d'une série de runs | Audit de performance |
| `init_status_json.py` | Bootstrap initial du `workspace/console/status.json` | Setup console web (1 fois par projet) |
| `verify_telemetry_health.py` | Diagnose `console.db` (intégrité, schéma, drift) | Si smoke émet `telemetry-health SUSPECT` |
| `strip_bom.py` | Nettoie le BOM UTF-16/UTF-8 d'un fichier généré | Post-gen si drift encoding |
| `rotate_audit_logs.py` | Rotate `force-bypass.log` / `legacy-parallel.log` | Maintenance ops (à wirer en `Stop` hook v7.1) |
| `audit_orphans.py` | Détecte artefacts orphelins (US/plans/qa) sous `workspace/output/` | Audit nettoyage post-run |
| `cleanup_orphans.py` | Supprime orphelins détectés avec backup `.trash/` | Suite de `audit_orphans` |
| `cache_manifest.py` | Extrait/exporte JSON du manifest cache (forward-looking v7.1) | Audit cache strategy |
| `migrate_exit_codes.py` | Refactor one-shot historique (migration achevée v7.0.0) | (archive) |

## Scripts agent-invoked — `sdd_scripts/` (50 scripts)

Invoqués par les commandes/agents du pipeline. Liste non-exhaustive
des plus critiques :

- **Preflight** : `preflight.py` (HARD-GATE), `preflight_force_cumul.py`, `context_budget.py`
- **Détection** : `detect_capabilities.py`, `detect_arch_shortcircuit.py`
- **Validateurs** : `validate_readiness.py`, `validate_plan.py`, `validate_semantic.py`,
  `validate_fidelity.py`, `validate_acceptance.py`, `validate_spec_compliance.py`,
  `validate_us_deps.py`, `validate_stack_combo.py`, `validate_project_config.py`
- **State / gates** : `sdd_state.py`, `gate_decide.py`, `record_gate_decision.py`
- **Pipeline orchestration** : `sdd_full_planner.py`, `phase_planner.py`, `run_dev_phase.py`
- **Plans** : `compute_plan_metadata.py`, `dispatch_fixes.py` (dormant v7.2)
- **Ingest** : `ingest_axe.py`, `ingest_lighthouse.py`, `ingest_agent_report.py`,
  `ingest_feats_us.py`, `ingest_plans.py`
- **DB / observability** : `init_console_db.py`, `query_console_db.py`,
  `report_roi.py`, `report_token_usage.py`
- **QA / coverage** : `parse_coverage.py`, `quality_scan.py`
- **Review** : `sdd_review.py`, `_review_fetch.py`, `_review_report.py`,
  `triage_issues.py`
- **Bench** : `bench_run.py` (opt-in mainteneur)
- **Discover** (brownfield) : `scan_repo.py`, `match_stack_catalog.py`
- **Profile** : `manage_profile.py`
- **US** : `set_us_status.py`, `compute_us_complexity.py`, `feat_to_pseudo_us.py`,
  `migrate_us_v1_to_v2.py`
- **Locks** : `acquire_libname_lock.py`
- **Resolve** : `resolve_us_hash_sentinel.py`
- **Cleanup** : `mark_breaking_resolved.py`

Liste détaillée par script : `git ls-files .claude/python/sdd_scripts/*.py`.

## Tests (88 fichiers pytest)

```bash
# Suite complète
python -m pytest .claude/python/tests/ -v

# Smoke uniquement (sous-ensemble enforcement load-bearing)
python -m pytest .claude/python/tests/ -m smoke

# Coverage avec seuil (config dans pyproject.toml — fail_under = 60)
python -m pytest --cov=sdd_lib --cov=sdd_scripts --cov=sdd_admin --cov=sdd_hooks

# Smoke runner end-to-end (non-pytest, gate CI)
python .claude/python/sdd_admin/framework_smoke.py
```

**Gaps connus** (audit Sprint 2 2026-06-07 — `roadmap` v7.1) : 22 scripts
encore sans test direct, dont 5 critiques visés v7.0.1 (`framework_smoke`,
`statusline`, `validate_templates`, `validate_libs_catalog`, `query_console_db`).

## Conventions

- **CLI args** : `--kebab-case` (Python argparse standard)
- **JSON output** : flag `--json` pour mode machine (caller bash, CI parse)
- **Atomic writes** : `sdd_lib.atomic_write.atomic_write_text` pour tout fichier
  partagé entre agents (anti-corruption crash mid-write — `rules/build-and-loop.md §2.bis`)
- **Path resolution** : `sdd_lib.paths.repo_root()` SSoT (jamais re-implémenter,
  cf. post-mortem 2026-05-21 — bug `.claude/.claude/` archive)
- **ISO timestamps** : `sdd_lib.paths.iso_now()` / `iso_now_ms()` SSoT
- **Type hints** : 100% sur fonctions publiques (`from __future__ import annotations`)
- **Aucune dépendance externe** runtime : pur stdlib Python 3.10+

## Bascule via agents/commandes

Tous les agents (`.claude/agents/*.md`), commandes (`.claude/commands/*.md`),
stacks (`.claude/stacks/**/*.md`) et hooks (`.claude/settings.json`)
référencent l'invocation Python canonique :

```bash
python .claude/python/sdd_scripts/context_budget.py --agent po --feat-number {n}
python .claude/python/sdd_admin/sync_stack_md.py --stack-id react
python .claude/python/sdd_scripts/validate_plan.py --plan-path {path} --us-path {path} --json
```

## Pour aller plus loin

- `sdd_lib/exit_codes.py` — convention exit codes complète + dérogations
- `sdd_lib/paths.py` — `repo_root()`, `iso_now()`, `iso_now_ms()`, `normalize()`
- `sdd_lib/atomic_write.py` — write atomique anti-corruption
- `sdd_lib/file_locks.py` — locks O_EXCL cross-platform
- `sdd_lib/console_db/` — schéma SQLite + helpers query
- `sdd_lib/markdown_io.py` — parse_frontmatter SSoT
- `sdd_lib/combos.py` — chargement combos.json
- `pyproject.toml` — config pytest + ruff + mypy + coverage
- `.claude/rules/error-classification.md §1.4` — taxonomie `[BUILD_*]` exit codes
