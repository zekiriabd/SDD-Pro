# SDD_Pro — Python scripts (cross-platform)

Migration progressive des hooks et scripts PowerShell vers Python pour
support natif Mac/Linux (en parallèle de Windows).

## Prérequis

- **Python 3.10+** (stdlib uniquement, pas de pip install requis)
- Pas de venv requis (scripts standalone)

```bash
# Vérifier
python --version   # ou python3 --version
# Doit retourner ≥ 3.10
```

## Layout

```
.claude/python/
├── sdd_lib/              # Helpers partagés
│   ├── hook_input.py     # Parse stdin JSON (hooks Claude Code)
│   ├── paths.py          # Repo root + normalize cross-platform
│   ├── stderr.py         # ERROR/CAUSE/FIX formatter
│   ├── project_config.py # Parse workspace/input/stack/stack.md
│   └── loader_yml.py     # Parse .claude/loader.yml `reads:`
├── sdd_hooks/            # 4 hooks Claude Code (PreToolUse, PostToolUse, SubagentStop)
│   ├── protect_framework.py
│   ├── preflight_agent_budget.py
│   ├── validate_augment_contract.py
│   └── audit_file_ownership.py
└── sdd_scripts/          # Scripts agent-invoked (en cours de migration)
    └── context_budget.py
```

## Hooks (déclarés dans `.claude/settings.json`)

| Hook | Trigger | Bloquant ? | Rôle |
|---|---|---|---|
| `protect_framework.py` | PreToolUse `Edit\|Write\|MultiEdit` | non (WARN stderr) | WARN si un agent touche un fichier framework |
| `preflight_agent_budget.py` | PreToolUse `Agent` | selon `$SDD_BUDGET_MODE` | Vérifie le budget tokens avant invocation sub-agent |
| `validate_augment_contract.py` | PostToolUse `Edit\|Write\|MultiEdit` | **oui** (exit 2 sur violation) | Vérifie contrats `preserves:`/`adds:` du plan |
| `audit_file_ownership.py` | SubagentStop | non (log append-only) | Audit matrice `file-ownership.md §1` post-dispatch |

### Variables d'environnement

| Variable | Valeurs | Défaut | Effet |
|---|---|---|---|
| `SDD_BUDGET_MODE` | `off` / `warn` / `strict` | `warn` | `off` = skip silencieux (hook désactivé) ; `warn` = ledger + stderr WARN, exit 0 ; `strict` = bloque l'invocation d'agent (exit 2) si budget dépassé |
| `SDD_USER_EMAIL` | email | (vide) | Identifie le validateur lors des gates manuels (`gate_decide.py set --answered-by`) |

> **Note** : `SDD_BUDGET_MODE=warn` (défaut) signifie que le hook
> `preflight_agent_budget` est **non bloquant**. Pour un garde-fou
> effectif sur le budget tokens, exporter `$env:SDD_BUDGET_MODE=strict`
> dans le shell qui lance Claude Code.

## Migration status — **100% terminée**

| Phase | Status | Scripts | Lignes Python |
|---|---|---|---|
| 1 — Infrastructure `sdd_lib/` | ✅ | 6 modules | 277 |
| 2 — 4 hooks Claude Code + context_budget | ✅ | 5 | 827 |
| 3 — Scripts agent-invoked | ✅ | 8 | 1 887 |
| 4 — Gate/state/validation | ✅ | 5 | 1 396 |
| 5 — Outils humains | ✅ | 5 | 1 468 |
| **TOTAL** | ✅ | **29 fichiers** | **5 855** |

Migration PowerShell → Python **terminée** (2026-05-13) : les dossiers
historiques `.claude/scripts/` et `.claude/hooks/` ont été supprimés ;
seuls les modules Python sous `.claude/python/sdd_scripts/`,
`.claude/python/sdd_hooks/`, `.claude/python/sdd_admin/`,
`.claude/python/sdd_lib/` sont actifs.

### Mapping PowerShell → Python (29 scripts)

| PowerShell `.ps1` | Python `.py` | Phase |
|---|---|---|
| `hooks/protect-framework` | `sdd_hooks/protect_framework` | 2 |
| `hooks/preflight-agent-budget` | `sdd_hooks/preflight_agent_budget` | 2 |
| `scripts/validate-augment-contract` | `sdd_hooks/validate_augment_contract` | 2 |
| `scripts/audit-file-ownership` | `sdd_hooks/audit_file_ownership` | 2 |
| `scripts/context-budget` | `sdd_scripts/context_budget` | 2 |
| `scripts/preflight` | `sdd_scripts/preflight` | 3 |
| `scripts/detect-capabilities` | `sdd_scripts/detect_capabilities` | 3 |
| `scripts/mark-breaking-resolved` | `sdd_scripts/mark_breaking_resolved` | 3 |
| `scripts/acquire-libname-lock` | `sdd_scripts/acquire_libname_lock` | 3 |
| `scripts/compact-front-plans` | _(retiré v7.0.0-alpha — script supprimé)_ | 3 |
| `scripts/validate-fidelity` | `sdd_scripts/validate_fidelity` | 3 |
| `scripts/quality-scan` | `sdd_scripts/quality_scan` | 3 |
| `scripts/parse-coverage` | `sdd_scripts/parse_coverage` | 3 |
| `scripts/init-status-json` | `sdd_admin/init_status_json` | 4 |
| `scripts/sdd-state` | `sdd_scripts/sdd_state` | 4 |
| `scripts/gate-decide` | `sdd_scripts/gate_decide` | 4 |
| `scripts/validate-readiness` | `sdd_scripts/validate_readiness` | 4 |
| `scripts/validate-semantic` | `sdd_scripts/validate_semantic` | 4 |
| `scripts/validate-libs-catalog` | `sdd_admin/validate_libs_catalog` | 5 |
| `scripts/validate-inline-rules` | `sdd_scripts/validate_inline_rules` | 5 |
| `scripts/framework-smoke` | `sdd_admin/framework_smoke` | 5 |
| `scripts/measure-batch` | `sdd_admin/measure_batch` | 5 |
| `scripts/sync-stack-md` | `sdd_admin/sync_stack_md` | 5 |

### Scripts maintenance (hors pipeline) — dossier `sdd_admin/`

Les scripts suivants vivent dans `.claude/python/sdd_admin/` (depuis
2026-05-13, dossier séparé pour clarté). **Outils Tech Lead**, jamais
invoqués par les commandes/agents du pipeline. Ils servent à valider,
mesurer ou synchroniser le framework lui-même :

| Script | Rôle | Quand l'utiliser |
|---|---|---|
| `validate_libs_catalog.py` | Valide les `.libs.json` contre le schéma JSON + cohérence | Après édition d'un catalogue stack |
| `validate_inline_rules.py` | Vérifie que les règles inlinées dans agents/ matchent les rules/ | Après modification d'une règle load-bearing |
| `framework_smoke.py` | Smoke check end-to-end du framework | Avant release / après refactor profond |
| `measure_batch.py` | Mesure tokens/durée d'une série de runs | Audit de performance |
| `init_status_json.py` | Bootstrap initial du `workspace/console/status.json` | Setup console web (1 fois par projet) |
| `sync_stack_md.py` | Régénère §2.4 du `.md` depuis le `.libs.json` | Après mise à jour d'un `.libs.json` |
| `strip_bom.py` | Nettoie le BOM UTF-16/UTF-8 d'un fichier généré | Post-gen si drift encoding |

Ces scripts sont **opt-in humain** — pas de référence depuis
`commands/*.md` ni `agents/*.md` (par design).

### Scripts agent-invoked (pipeline)

Tous les autres scripts dans `sdd_scripts/` sont appelés par les
commandes/agents (preflight, context_budget, detect_capabilities,
validate_readiness, validate_semantic, validate_fidelity, parse_coverage,
quality_scan, mark_breaking_resolved, acquire_libname_lock,
compact_front_plans, sdd_state, gate_decide).

### Scripts From-Plan (v6.2 → v7.0.0)

Deux scripts pour le chemin From-Plan (validation déterministe avant
spawn dev-*) :

> **v7.0.0 change** : le mode "strict" (variants `dev-*-strict` Sonnet)
> a été retiré (governance-major-prompts-trim). Le flag `PlanCacheStrict`
> est désormais **DEPRECATED no-op** — toléré en lecture pour
> backward-compat, mais le routing `/dev-run` STEP 6.0.bis spawn toujours
> `dev-*` Opus 4.7 que `validate_plan.py` retourne 0 (plan v2 avec
> Inline Digest) ou 1 (plan v1 legacy). Seul exit 2 (stale/invalide)
> reste bloquant.

| Script | Rôle | Invocateurs |
|---|---|---|
| `sdd_scripts/validate_plan.py` (~370 LOC, 21 tests) | Validation structurelle + détection staleness (`us-hash` mismatch) d'un plan `.back.md` / `.front.md`. Exit 0 (plan v2 valide), 1 (plan v1 legacy valide), 2 (stale/invalide/corrompu → STOP). Le flag CLI `--strict` est accepté en no-op pour backward-compat. | `dev-run` STEP 6.0.bis (gate staleness), `dev-plan` STEP 5 (post-génération), `sdd-status` (diagnostic) |
| `sdd_scripts/compute_plan_metadata.py` (~150 LOC, 7 tests) | Helper YAML/JSON pour générer le v2 frontmatter (`plan-schema-version: 2`, `us-hash` SHA-256, `claude-md-hash`, `generated-at` ISO, `capabilities-triggered`). | `dev-backend` STEP 5.2 (mode `:plan`), `dev-frontend` STEP 6.4 (mode `:plan`) |

Détail design (archive) : `@.claude/archive/v7-design-superseded/DESIGN-FROMPLAN-STRICT.md`.
Détail format plan v2 : `@.claude/rules/build-and-loop.md §7.4.bis`.

### Conventions

- **CLI args** : `--kebab-case` (équivalent `-CamelCase` PowerShell)
- **Exit codes** : identiques au PS d'origine (0=OK, 1=erreur, 2=block-hook, etc.)
- **JSON output** : `--json` au lieu de `-Json` PowerShell
- **Aucune dépendance externe** : pur stdlib Python 3.10+

### Bascule via agents/commandes

Migration terminée : les agents (`.claude/agents/*.md`), commandes
(`.claude/commands/*.md`), stacks (`.claude/stacks/**/*.md`) et hooks
(`.claude/settings.json`) référencent tous l'invocation Python
canonique :

```bash
python .claude/python/sdd_scripts/context_budget.py --agent po --feat-number {n}
python .claude/python/sdd_admin/sync_stack_md.py --stack-id react
```
