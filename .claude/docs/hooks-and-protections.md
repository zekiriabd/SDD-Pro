# SDD_Pro — Hooks & Protections (inventaire canonique)

> **Source de vérité unique** des hooks Claude Code et scripts de protection
> branchés sur le pipeline SDD_Pro. Tout ajout/suppression/renommage de
> protection DOIT mettre à jour ce fichier ET produire un ADR
> `governance-protection-{slug}` (cf. `VERSIONING.md` + `ADR-20260519T173000`).

---

## 1. Hooks actifs (16)

Configurés dans `.claude/settings.json` section `hooks`. Tous invoqués via
le wrapper `python -c "...import _hook; _hook.run('sdd_hooks.X')"` qui
détecte automatiquement `CLAUDE_PROJECT_DIR` ou remonte vers `.claude/`
depuis le cwd.

### 1.1 `protect_framework` — PreToolUse Edit|Write|MultiEdit

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Edit\|Write\|MultiEdit` |
| Script | [`.claude/python/sdd_hooks/protect_framework.py`](.claude/python/sdd_hooks/protect_framework.py) |
| LOC | ~50 |
| Rôle | Refuse les écritures dans `.claude/` (sauf top-level whitelist) et dans `workspace/output/.sys/.context/` non-ADR. Garde-fou contre les modifs framework involontaires. |
| Exit codes | 0 = allow, 1 = deny avec message stderr |
| Bypassable ? | NON (hook bloquant), sauf si chemin matche whitelist |

### 1.2 `preflight_agent_budget` — PreToolUse Agent

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Agent` |
| Script | [`.claude/python/sdd_hooks/preflight_agent_budget.py`](.claude/python/sdd_hooks/preflight_agent_budget.py) |
| LOC | ~110 |
| Rôle | Vérifie qu'un sub-agent qui va être spawn ne dépasse pas son `DEFAULT_BUDGETS` (cf. `context_budget.py`). Bloque l'invocation si budget excédé. |
| Exit codes | 0 = allow, 1 = deny (budget exceeded) |
| Lecture | `loader.yml` (reads patterns par agent) |

### 1.3 `validate_augment_contract` — PostToolUse Edit|Write|MultiEdit

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PostToolUse` matcher `Edit\|Write\|MultiEdit` |
| Script | [`.claude/python/sdd_hooks/validate_augment_contract.py`](.claude/python/sdd_hooks/validate_augment_contract.py) |
| LOC | ~140 |
| Rôle | Vérifie que les fichiers édités en mode `operation: augment` (cf. plans) respectent leur contrat `preserves:`/`adds:`. Émet `[PRESERVES_VIOLATED]` ou `[ADDS_VIOLATED]` si drift détecté. |
| Exit codes | 0 = pass, 1 = violation |

### 1.4 `audit_file_ownership` — SubagentStop (13 agents)

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `SubagentStop` matcher `arch\|po\|elicitor\|dev-backend\|dev-frontend\|qa\|code-reviewer\|security-reviewer\|spec-compliance-reviewer\|arch-reviewer\|adversarial-reviewer\|constitutioner\|complexity-router` (étendu v7.0.0+ : ajout `complexity-router` opt-in ; v7.0.0-alpha avait 12 — retirés : `dev-*-strict`, `dashboard`, `accessibility-auditor`, `performance-auditor`) |
| Script | [`.claude/python/sdd_hooks/audit_file_ownership.py`](.claude/python/sdd_hooks/audit_file_ownership.py) |
| LOC | ~150 |
| Rôle | Vérifie la matrice ownership de `rules/ownership.md §1` (Partie A, ex-file-ownership.md) : un agent dev-backend n'a pas écrit dans `{AppName}/`, un agent QA n'a pas écrit en dehors de `*.Tests/`, etc. Émet `[FILE_OWNERSHIP]` ou `[FILE_OWNERSHIP_NESTED]` si violation. |
| Exit codes | 0 = pass, 1 = violation |

### 1.5 `record_token_usage` — PostToolUse Agent + SubagentStop

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PostToolUse` matcher `Agent` + `SubagentStop` (les mêmes agents que 1.4, + matcher `po` séparé) |
| Script | [`.claude/python/sdd_hooks/record_token_usage.py`](.claude/python/sdd_hooks/record_token_usage.py) |
| LOC | ~210 |
| Rôle | Capture les tokens input/output/cache réellement consommés par un sub-agent et insère dans `console.db` table `token_usage`. **Opt-in** via `SDD_TOKEN_USAGE_MODE=record\|debug` (défaut `off` = exit immédiat, aucun effet). |
| Ajouté | v6.5.1 (cf. `MIGRATION.md` lignes 551-613) |

### 1.6 `block_env_bypass` — PreToolUse Bash

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Bash` |
| Script | [`.claude/python/sdd_hooks/block_env_bypass.py`](.claude/python/sdd_hooks/block_env_bypass.py) |
| LOC | ~130 |
| Rôle | Defense-in-depth : refuse toute commande Bash qui exporte/inline une env var `SDD_ALLOW_*`, `SDD_DISABLE_*`, `SDD_ALLOW_FORCE`, etc. Couvre POSIX `export VAR=val`, inline `VAR=val cmd`, PowerShell `$env:`, Windows `setx`, et `bash -c "..."` chained. Empêche un agent d'auto-bypass un gate via env var. |
| Exit codes | 0 = allow, 2 = deny (env bypass detected) |
| Ajouté | v7.0.0-alpha P0 §4 |

### 1.7 `preflight_cost_cap` — PreToolUse Agent

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Agent` (chaîné après `preflight_agent_budget`) |
| Script | [`.claude/python/sdd_hooks/preflight_cost_cap.py`](.claude/python/sdd_hooks/preflight_cost_cap.py) |
| LOC | ~80 |
| Rôle | Vérifie que le coût USD cumulatif de la run en cours (lu depuis `console.db` table `token_usage`) n'atteint pas `MaxCostPerRun` (défaut $50). Si dépassement → STOP avec classe `[COST_CAP_EXCEEDED]`. Bypass : `SDD_DISABLE_COST_CAP=1` (one-shot) OU `MaxCostPerRun: 0` (config désactivée). |
| Exit codes | 0 = allow, 2 = deny (cost cap exceeded) |
| Ajouté | v7.0.0-alpha P0 §4.3 |

### 1.8 `preflight_stack_combo` — PreToolUse Skill

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Skill` |
| Script | [`.claude/python/sdd_hooks/preflight_stack_combo.py`](.claude/python/sdd_hooks/preflight_stack_combo.py) |
| LOC | ~150 |
| Rôle | Avant tout slash-command qui active une combo stack (`/sdd-full`, `/dev-run`, `/sdd-poc`), vérifie que les stacks actifs dans `stack.md` forment une combinaison validée (cf. `docs/validated-combos.md`) ou émet WARN si combo `🟡 experimental`. STOP si stacks malformés OU multi-stacks contradictoires sans `SDD_ALLOW_MULTISTACK=1`. |
| Exit codes | 0 = allow, 2 = deny (combo invalid) |
| Ajouté | v7.0.0-alpha audit MIN-7 |

### 1.9 `validate_stack_consistency` — PostToolUse Edit|Write|MultiEdit

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PostToolUse` matcher `Edit\|Write\|MultiEdit` (chaîné avant `validate_augment_contract`) |
| Script | [`.claude/python/sdd_hooks/validate_stack_consistency.py`](.claude/python/sdd_hooks/validate_stack_consistency.py) |
| LOC | ~170 |
| Rôle | Après chaque écriture, vérifie que les libs/imports introduits restent cohérents avec les stacks actifs (§2.4 catalog + capabilities triggered). Emit `[STACK_LIBRARY_MISSING]` si import vers une lib hors §2.4. |
| Exit codes | 0 = pass, 1 = violation (drift détecté) |

### 1.10 `resolve_po_hash_sentinel` — SubagentStop po (defense-in-depth)

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `SubagentStop` matcher `po` |
| Script | [`.claude/python/sdd_hooks/resolve_po_hash_sentinel.py`](.claude/python/sdd_hooks/resolve_po_hash_sentinel.py) |
| LOC | ~90 |
| Rôle | Filet de sécurité : à chaque arrêt de l'agent `po`, scanne les US contenant le sentinel `Parent FEAT hash: sha256:COMPUTE_REQUIRED` et le résout via `resolve_us_hash_sentinel.py --auto-detect`. Couvre les invocations `Agent: po` hors `/us-generate` où le sentinel persistait (causait `[FEAT_HASH_MISMATCH]` downstream). |
| Exit codes | 0 = ALLOW (idempotent ; non-bloquant même si échec) |
| Ajouté | v7.0.0-alpha audit P0-workflow 2026-06-05 |

### 1.11 `validate_acceptance_gate` — SubagentStop qa

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `SubagentStop` matcher `qa` |
| Script | [`.claude/python/sdd_hooks/validate_acceptance_gate.py`](.claude/python/sdd_hooks/validate_acceptance_gate.py) |
| LOC | ~250 |
| Rôle | Après chaque arrêt de l'agent `qa`, exécute l'acceptance gate sur tous les projets sous `workspace/output/src/*` (cf. `rules/quality.md Partie C`) : `test`, `lint`, `build`, `coverage ≥ seuil`, + smoke browser + E2E Playwright pour projets UI. Émet `[ACCEPTANCE_GATE_FAILED]` si échec. Bypass : `SDD_ALLOW_ACCEPTANCE_BYPASS=1` (audit-loggué). |
| Exit codes | 0 = pass, 1 = gate failed |
| Ajouté | v7.0.0-alpha audit P5 |

### 1.12 `pre_write_lint` — PreToolUse Edit|Write|MultiEdit

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Edit\|Write\|MultiEdit` (chaîné après `protect_framework`) |
| Script | [`.claude/python/sdd_hooks/pre_write_lint.py`](.claude/python/sdd_hooks/pre_write_lint.py) |
| LOC | ~200 |
| Rôle | Enforce les forbidden patterns documentés dans `stack/{cat}/{id}.md` (§Forbidden ou CLAUDE.md projet) **avant** que l'écriture atteigne le disque. Détecte par regex sur le `new_string` / `content` payload : Kotlin `!!` (NPE assertions), Vue `<input type="text">` brut sans validation, console.log/print debug, hex hardcode (`#fff`, `rgba(...)` au lieu de tokens CSS), magic numbers > 100, etc. Skip silencieusement les test paths (`**/test_*.py`, `**/*.test.ts`, `**/*Test.kt`) et les fichiers hors `workspace/output/src/`. |
| Modes | `warn` (défaut — exit 0 + audit log) ; `strict` via `SDD_PRE_WRITE_LINT_STRICT=1` (exit 2 = bloquant) |
| Bypass | `SDD_DISABLE_PRE_WRITE_LINT=1` (audit-loggué, narrow per-session) |
| Exit codes | 0 = allow (warn ou bypass), 2 = deny (strict + violation) |
| Ajouté | v7.0.0-alpha Sprint 1.4 (2026-06-06) ; documenté audit CTO (2026-06-07) |

### 1.13 `preflight_glob_scope` — PreToolUse Glob

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Glob` |
| Script | [`.claude/python/sdd_hooks/preflight_glob_scope.py`](.claude/python/sdd_hooks/preflight_glob_scope.py) |
| LOC | ~120 |
| Rôle | Defense-in-depth anti-token-explosion : refuse les patterns Glob non-bornés (`workspace/output/src/**/*`, `**/*`, `**`) sans contrainte d'extension. Le post-mortem documenté dans `agents/spec-compliance-reviewer.md` (~ligne 178) a tracé un Glob isolé qui a déclenché 1.8M tokens / $35 sur un seul agent reviewer. Le prompt anti-pattern n'a pas suffit à arrêter Sonnet 4.6 — d'où ce garde runtime. Globs scopés (avec sous-dossier ou extension) et globs hors `workspace/output/src/` sont autorisés silencieusement. |
| Modes | `warn` (défaut — exit 0 + audit log + WARN stderr) ; `strict` via `SDD_GLOB_SCOPE_STRICT=1` (exit 2) |
| Bypass | `SDD_DISABLE_GLOB_SCOPE=1` (audit-loggué) |
| Exit codes | 0 = allow (warn ou bypass), 2 = deny (strict + broad) |
| Audit log | `workspace/output/.sys/.audit/glob-scope.jsonl` |
| Ajouté | v7.0.0-alpha audit CTO (2026-06-07) — Sprint 4 #18 |

### 1.14 `session_start` — SessionStart startup|resume|clear|compact

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `SessionStart` matcher `startup\|resume\|clear\|compact` |
| Script | [`.claude/python/sdd_hooks/session_start.py`](.claude/python/sdd_hooks/session_start.py) |
| LOC | ~120 |
| Rôle | Injecte un banner SDDPro statique (2167 bytes full, 203 bytes CI) au démarrage. Cache-friendly v7.0.0+ : byte-identical cross-session → le prompt cache d'Anthropic hit le prefix complet entre `resume`/`compact`. Détail state projet déporté vers `/sdd-help` / `/sdd-status` à la demande. |
| Modes | `full` (défaut interactif) ; `minimal` 1L si `CI=1` env var |
| Bypass | `SDD_DISABLE_SESSION_START=1` (no-op empty context) |
| Exit codes | 0 toujours (defensive, n'échoue jamais une session) |
| Ajouté | v7.0.0+ chantier #4 (2026-06-08) — emprunt superpowers v5.1 |

### 1.15 `enforce_two_stage_auditor` — PreToolUse Agent (v7.0.0+)

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Agent` |
| Script | [`.claude/python/sdd_hooks/enforce_two_stage_auditor.py`](.claude/python/sdd_hooks/enforce_two_stage_auditor.py) |
| LOC | ~180 |
| Rôle | Bloque les agents `code-reviewer`/`security-reviewer`/`arch-reviewer` (Stage B) tant que `spec-compliance-reviewer` (Stage A) n'a pas produit un verdict fresh < 24h dans `qa_spec_compliance` pour la FEAT. Exit 2 + `[TWO_STAGE_GATE_VIOLATION]` si violation. `spec-compliance-reviewer` lui-même et `adversarial-reviewer` (informational) toujours allowed. |
| Modes | `two-stage` (défaut) ; `legacy-parallel` (no-op) via Project Config `AuditorBatchMode: legacy-parallel` |
| Bypass | `SDD_BYPASS_TWO_STAGE=1` (one-shot, audit-loggué) |
| Exit codes | 0 = allow, 2 = deny (gate violation) |
| Ajouté | v7.0.0+ audit P3 B + B.bis (2026-06-08) |

### 1.16 `auto_invoke_complexity_router` — PreToolUse Skill (v7.0.0+)

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PreToolUse` matcher `Skill` (filtre commandes `sdd-full`/`sdd-poc`/`dev-run`) |
| Script | [`.claude/python/sdd_hooks/auto_invoke_complexity_router.py`](.claude/python/sdd_hooks/auto_invoke_complexity_router.py) |
| LOC | ~180 |
| Rôle | Si `ComplexityRouterMode: auto` ET pas de rapport routing < 1h fresh, lance `sdd_scripts/complexity_router.py` en subprocess AVANT que le slash command démarre. Outputs sous `workspace/output/.sys/.routing/{n}-complexity.{json,md}`. **Additif uniquement** : ne bloque jamais. |
| Modes | `auto` (script invoqué) ; `manual` (défaut, no-op) ; `off` (no-op) via Project Config `ComplexityRouterMode` |
| Bypass | `SDD_DISABLE_AUTO_ROUTER=1` ; `ComplexityRouterMode: off\|manual` |
| Exit codes | 0 toujours (additive, n'échoue jamais un slash command) |
| Ajouté | v7.0.0+ audit P3 A + A.bis (2026-06-08) |

---

## 1.bis Tableau de bypass — env vars (v7.0.0+ audit P3 W3 2026-06-08)

Tous les hooks SDDPro supportent un mécanisme de bypass via env var pour les
cas Tech Lead avancés (debug, force, urgence prod). Chaque bypass est
**audit-loggué** (sauf indication contraire). À utiliser en connaissance de cause.

| Env var | Effet | Hook concerné | Audit | Quand l'utiliser |
|---|---|---|---|---|
| `SDD_CONFIG_STRICT=1` | Schéma validation hard fail au lieu de WARN | `layered_config._warn_unknown_keys` | — | CI/CD : forcer FAIL sur clé inconnue |
| `SDD_DISABLE_UNKNOWN_KEY_WARN=1` | Silencer les WARN clés inconnues | `layered_config._warn_unknown_keys` | — | Projet legacy avec clés Tech Lead extensions |
| `SDD_DISABLE_DEPRECATED_CONFIG_WARN=1` | Silencer les WARN clés deprecated | `layered_config._warn_deprecated_keys` | — | Migration v6→v7 en cours |
| `SDD_BYPASS_TWO_STAGE=1` | Allow Stage B sans Stage A passé | `enforce_two_stage_auditor` | ✓ stderr | Urgence : skip spec gate ponctuellement |
| `SDD_DISABLE_AUTO_ROUTER=1` | No-op du auto-invoke router | `auto_invoke_complexity_router` | — | Debug : forcer parcours pipeline standard |
| `SDD_DISABLE_SESSION_START=1` | Banner SDDPro vide à l'init session | `session_start` | — | Tests automatisés, sessions ciblées |
| `SDD_FORCE_PIPELINE=poc\|standard\|full\|critical` | Override score complexity_router | `complexity_router.py` | — | Tech Lead override décision routing |
| `SDD_BUDGET_MODE=strict\|warn\|off` | Mode preflight context budget | `preflight_agent_budget` | ✓ ledger | Default strict en CI, warn en dev |
| `SDD_DISABLE_COST_CAP=1` | Bypass cost cap MaxCostPerRun | `preflight_cost_cap` | ✓ audit log | Urgence : run sans cap (rare) |
| `SDD_PROTECT_FRAMEWORK_MODE=warn\|strict\|off` | Mode protect framework files | `protect_framework` | ✓ stderr | Édition framework légitime |
| `SDD_PRE_WRITE_LINT_STRICT=1` | Pre-write lint en strict (exit 2) | `pre_write_lint` | ✓ audit log | CI/CD : forcer lint hard fail |
| `SDD_DISABLE_PRE_WRITE_LINT=1` | No-op pre-write lint | `pre_write_lint` | — | Debug ponctuel |
| `SDD_GLOB_SCOPE_STRICT=1` | Glob scope guard en strict | `preflight_glob_scope` | ✓ audit log | CI/CD : forcer scope étroit |
| `SDD_DISABLE_GLOB_SCOPE=1` | No-op glob scope guard | `preflight_glob_scope` | — | Audit forensique large |
| `SDD_ALLOW_ACCEPTANCE_BYPASS=1` | Skip acceptance gate (qa) | `validate_acceptance_gate` | ✓ audit log | Debug ponctuel |
| `SDD_ALLOW_MULTISTACK=1` | Allow multi-backend / multi-fullstack | `validate_stack_consistency` | ✓ audit log | Bench / debug |
| `SDD_ALLOW_UNTESTED_COMBO=1` | Bypass combo SLA gate | `preflight_stack_combo` | ✓ audit log | Combo expérimental |

> **Règle Tech Lead** : tous les `SDD_ALLOW_*` et `SDD_DISABLE_*` sont
> **bloqués au runtime** par `block_env_bypass` hook si exportés/inlinés
> via Bash. Ils doivent venir du **shell parent** (avant le start de
> Claude Code) ou de `.claude/settings.local.json` (per-dev, gitignored).
> Cf. §1.6.

---

## 2. Stop hook (smoke check final)

### 2.1 `framework_smoke --strict --silent-on-pass`

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `Stop` (fin de chaque conversation) |
| Script | [`.claude/python/sdd_admin/framework_smoke.py`](.claude/python/sdd_admin/framework_smoke.py) |
| LOC | ~400 |
| Rôle | 80 checks déterministes vérifient l'intégrité du framework : structure des stacks `.libs.json`, schémas templates, cohérence rules/agents, classes d'erreur conformes, présence des scripts critiques, etc. Mode `--strict --silent-on-pass` = silencieux si tout vert, sinon stderr résumé. |
| Exit codes | 0 = pass, 1 = ≥1 check failed |

---

## 3. Mapping migration PS → Python (v6.5+)

> Cette section trace **rétroactivement** la migration v6.5+ de PowerShell
> vers Python pour le support cross-platform (Linux/macOS dev équivalent
> Windows). **Aucune protection supprimée nette** : les 23 fichiers `.ps1`
> ont tous un équivalent Python branché.

### 3.1 Hooks (2 → 2, dossier renommé)

| PowerShell (supprimé) | Python (actif) | Note |
|---|---|---|
| `.claude/hooks/preflight-agent-budget.ps1` | [`sdd_hooks/preflight_agent_budget.py`](.claude/python/sdd_hooks/preflight_agent_budget.py) | dossier renommé `hooks` → `sdd_hooks` |
| `.claude/hooks/protect-framework.ps1` | [`sdd_hooks/protect_framework.py`](.claude/python/sdd_hooks/protect_framework.py) | idem |

### 3.2 Scripts → Hooks (3, promus au statut hook)

| PowerShell (supprimé) | Python (actif) | Trigger |
|---|---|---|
| `.claude/scripts/audit-file-ownership.ps1` | `sdd_hooks/audit_file_ownership.py` | SubagentStop |
| `.claude/scripts/validate-augment-contract.ps1` | `sdd_hooks/validate_augment_contract.py` | PostToolUse Edit |
| `.claude/scripts/record-token-usage.ps1` (n'a jamais existé) | `sdd_hooks/record_token_usage.py` | PostToolUse Agent + SubagentStop (v6.5.1 NOUVEAU) |

### 3.3 Scripts → sdd_scripts/ (CLI internes, 13 migrés)

| PowerShell (supprimé) | Python (actif) |
|---|---|
| `acquire-libname-lock.ps1` | [`sdd_scripts/acquire_libname_lock.py`](.claude/python/sdd_scripts/acquire_libname_lock.py) |
| `compact-front-plans.ps1` | _(retiré v7.0.0-alpha, script supprimé du disque — cassait contrat plan v2 ; cf. `commands/dev-plan.md` historique)_ |
| `context-budget.ps1` | [`sdd_scripts/context_budget.py`](.claude/python/sdd_scripts/context_budget.py) |
| `detect-capabilities.ps1` | [`sdd_scripts/detect_capabilities.py`](.claude/python/sdd_scripts/detect_capabilities.py) |
| `gate-decide.ps1` | [`sdd_scripts/gate_decide.py`](.claude/python/sdd_scripts/gate_decide.py) |
| `mark-breaking-resolved.ps1` | [`sdd_scripts/mark_breaking_resolved.py`](.claude/python/sdd_scripts/mark_breaking_resolved.py) |
| `parse-coverage.ps1` | [`sdd_scripts/parse_coverage.py`](.claude/python/sdd_scripts/parse_coverage.py) |
| `preflight.ps1` | [`sdd_scripts/preflight.py`](.claude/python/sdd_scripts/preflight.py) |
| `quality-scan.ps1` | [`sdd_scripts/quality_scan.py`](.claude/python/sdd_scripts/quality_scan.py) |
| `sdd-state.ps1` | [`sdd_scripts/sdd_state.py`](.claude/python/sdd_scripts/sdd_state.py) |
| `validate-fidelity.ps1` | [`sdd_scripts/validate_fidelity.py`](.claude/python/sdd_scripts/validate_fidelity.py) |
| `validate-inline-rules.ps1` | [`sdd_scripts/validate_inline_rules.py`](.claude/python/sdd_scripts/validate_inline_rules.py) |
| `validate-readiness.ps1` | [`sdd_scripts/validate_readiness.py`](.claude/python/sdd_scripts/validate_readiness.py) |
| `validate-semantic.ps1` | [`sdd_scripts/validate_semantic.py`](.claude/python/sdd_scripts/validate_semantic.py) |

### 3.4 Scripts → sdd_admin/ (outils dev humains, 5 migrés)

| PowerShell (supprimé) | Python (actif) |
|---|---|
| `framework-smoke.ps1` | [`sdd_admin/framework_smoke.py`](.claude/python/sdd_admin/framework_smoke.py) |
| `init-status-json.ps1` | [`sdd_admin/init_status_json.py`](.claude/python/sdd_admin/init_status_json.py) |
| `measure-batch.ps1` | [`sdd_admin/measure_batch.py`](.claude/python/sdd_admin/measure_batch.py) |
| `sync-stack-md.ps1` | [`sdd_admin/sync_stack_md.py`](.claude/python/sdd_admin/sync_stack_md.py) |
| `validate-libs-catalog.ps1` | [`sdd_admin/validate_libs_catalog.py`](.claude/python/sdd_admin/validate_libs_catalog.py) |

### 3.5 Total migration + ajouts v7.0.0-alpha

| Catégorie | PowerShell supprimé | Python actif | Net |
|---|---:|---:|---:|
| Hooks v6.x (dossier `.claude/hooks/` → `sdd_hooks/`) | 2 | 5 | **+3** (3 anciens scripts promus en hooks) |
| Hooks v7.0.0-alpha (ajouts depuis audit P0/P5) | — | 6 | **+6** (`block_env_bypass`, `preflight_cost_cap`, `preflight_stack_combo`, `validate_stack_consistency`, `resolve_po_hash_sentinel`, `validate_acceptance_gate`) |
| Hooks v7.0.0-alpha Sprint 1.4 (lint pre-write) | — | 1 | **+1** (`pre_write_lint`) |
| Hooks v7.0.0-alpha audit CTO (Glob anti-explosion) | — | 1 | **+1** (`preflight_glob_scope`) |
| Scripts CLI (`sdd_scripts/`) | 14 | ~50 (v7.0.0-alpha) | +36 net |
| Scripts admin (`sdd_admin/`) | 5 | ~13 | +8 |
| **Total Python actif v7.0.0-alpha** | **23 PS** | **13 hooks + 50 scripts + 13 admin = 76 fichiers exécutables** | **+53 net** |

**Aucune protection nette supprimée**. La protection v7.0.0-alpha est **strictement plus forte** que v6.10 (8 hooks supplémentaires ; tous activés par défaut sauf `record_token_usage` opt-in et `pre_write_lint` / `preflight_glob_scope` en mode warn par défaut).

---

## 4. Politique : tout changement de protection exige un ADR

À partir de v7.0.0 (cf. `ADR-20260519T173000-governance-protection-tracing`) :

> **Toute modification du jeu de hooks/protections (ajout, suppression,
> migration, renommage) DOIT être tracée par un ADR
> `governance-protection-{slug}` accepté par 2 mainteneurs AVANT le merge
> sur `main`. Le fichier `.claude/docs/hooks-and-protections.md` (présent
> fichier) DOIT être mis à jour dans la même PR.**

Forme rejetée : suppression silencieuse d'un `.ps1`/`.py` hook + renommage
sans cross-référence dans MIGRATION.md.

Audit déterministe (futur) : `audit_hooks_drift.py` qui vérifie la
cohérence entre :
- `.claude/settings.json` section `hooks`
- `.claude/python/sdd_hooks/*.py` (présence du module)
- `.claude/docs/hooks-and-protections.md` (présente section §1)

Exit non-zero si désaccord = bloquant CI v7.

---

## 5. Bypass d'urgence (procédure documentée)

Si un hook bloque légitimement le travail (e.g., faux positif
`protect_framework` sur un chemin nouveau) :

### Bypass session unique (Tech Lead humain)
```powershell
# Désactive tous les hooks pour la session courante
$env:CLAUDE_HOOKS_DISABLED = "1"
```

### Bypass narrow (1 hook spécifique)
Éditer `.claude/settings.local.json` (gitignored) :
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit", "hooks": [] }
    ]
  }
}
```
> ⚠️ `settings.local.json` override `settings.json` mais doit être réverté
> ou commit avec ADR explicatif si la suppression est durable.

### Bypass total (rare, non documenté pour la prod)
Supprimer la section `hooks` de `.claude/settings.json`. Interdit sans
ADR `governance-protection-{slug}` + 2 approbations.

---

## 6. Pointers

- [`.claude/settings.json`](.claude/settings.json) — configuration active
- [`.claude/python/sdd_hooks/`](.claude/python/sdd_hooks/) — 13 hooks Python
- [`.claude/python/sdd_admin/framework_smoke.py`](.claude/python/sdd_admin/framework_smoke.py) — smoke check Stop hook
- [`.claude/python/_hook.py`](.claude/python/_hook.py) — wrapper d'invocation
- [`.claude/docs/MIGRATION.md`](./MIGRATION.md) — guide migration entre versions majeures
- [`.claude/docs/VERSIONING.md`](./VERSIONING.md) — politique SemVer + freeze
- `workspace/output/.sys/.context/adrs/ADR-20260519T173000-governance-protection-tracing.md` — ADR ex-post de la migration v6.5+
