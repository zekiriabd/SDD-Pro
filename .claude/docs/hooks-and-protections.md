# SDD_Pro — Hooks & Protections (inventaire canonique)

> **Source de vérité unique** des hooks Claude Code et scripts de protection
> branchés sur le pipeline SDD_Pro. Tout ajout/suppression/renommage de
> protection DOIT mettre à jour ce fichier ET produire un ADR
> `governance-protection-{slug}` (cf. `VERSIONING.md` + `ADR-20260519T173000`).

---

## 1. Hooks actifs (5)

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

### 1.4 `audit_file_ownership` — SubagentStop dev-*/qa/auditors

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `SubagentStop` matcher `dev-backend\|dev-frontend\|qa\|code-reviewer\|security-reviewer\|spec-compliance-reviewer\|arch-reviewer\|constitutioner` (v7.0.0 — retirés : `dev-*-strict`, `dashboard`, `accessibility-auditor`, `performance-auditor`) |
| Script | [`.claude/python/sdd_hooks/audit_file_ownership.py`](.claude/python/sdd_hooks/audit_file_ownership.py) |
| LOC | ~150 |
| Rôle | Vérifie la matrice ownership de `rules/ownership.md §1` (Partie A, ex-file-ownership.md) : un agent dev-backend n'a pas écrit dans `{AppName}/`, un agent QA n'a pas écrit en dehors de `*.Tests/`, etc. Émet `[FILE_OWNERSHIP]` ou `[FILE_OWNERSHIP_NESTED]` si violation. |
| Exit codes | 0 = pass, 1 = violation |

### 1.5 `record_token_usage` — PostToolUse Agent + SubagentStop

| Champ | Valeur |
|---|---|
| Trigger Claude Code | `PostToolUse` matcher `Agent` + `SubagentStop` (les mêmes agents que 1.4) |
| Script | [`.claude/python/sdd_hooks/record_token_usage.py`](.claude/python/sdd_hooks/record_token_usage.py) |
| LOC | ~210 |
| Rôle | Capture les tokens input/output/cache réellement consommés par un sub-agent et insère dans `console.db` table `token_usage`. **Opt-in** via `SDD_TOKEN_USAGE_MODE=record\|debug` (défaut `off` = exit immédiat, aucun effet). |
| Ajouté | v6.5.1 (cf. `MIGRATION.md` lignes 551-613) |

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
| `compact-front-plans.ps1` | [`sdd_scripts/compact_front_plans.py`](.claude/python/sdd_scripts/compact_front_plans.py) |
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

### 3.5 Total migration

| Catégorie | PowerShell supprimé | Python actif | Net |
|---|---:|---:|---:|
| Hooks (dossier `.claude/hooks/`) | 2 | 5 (dossier `sdd_hooks/`) | **+3** (3 anciens scripts promus en hooks) |
| Scripts CLI | 14 | 14 | 0 |
| Scripts admin | 5 | 5 | 0 |
| Scripts → hooks | 2 | (comptés ci-dessus) | 0 (déplacement) |
| **Nouveau v6.5.1** | — | `record_token_usage.py` | +1 |
| **Total** | **23 PS** | **24 Python** | **+1 hook net** |

**Aucune protection nette supprimée**. La protection v6.5+ est **strictement plus forte** que v6.4 (un hook supplémentaire `record_token_usage`, et 3 anciens scripts CLI passifs sont devenus hooks actifs branchés sur SubagentStop/PostToolUse).

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
- [`.claude/python/sdd_hooks/`](.claude/python/sdd_hooks/) — 5 hooks Python
- [`.claude/python/sdd_admin/framework_smoke.py`](.claude/python/sdd_admin/framework_smoke.py) — smoke check Stop hook
- [`.claude/python/_hook.py`](.claude/python/_hook.py) — wrapper d'invocation
- [`.claude/MIGRATION.md`](.claude/MIGRATION.md) — guide migration entre versions majeures
- [`.claude/VERSIONING.md`](.claude/VERSIONING.md) — politique SemVer + freeze
- `workspace/output/.sys/.context/adrs/ADR-20260519T173000-governance-protection-tracing.md` — ADR ex-post de la migration v6.5+
