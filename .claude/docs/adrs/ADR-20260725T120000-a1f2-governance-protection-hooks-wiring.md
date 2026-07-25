# ADR-20260725T120000-a1f2 — Câblage du jeu de hooks de protection dans settings.json

- **Statut** : Accepted
- **Date** : 2026-07-25
- **Auteur** : Tech Lead (audit général multi-harnais/multi-provider, 2026-07-25)
- **Phase** : gouvernance (protections runtime)

---

## Context

L'audit général du 2026-07-25 a révélé que `.claude/settings.json` **n'a jamais
comporté de section `hooks`** — y compris au commit initial `919b8ff` (clé unique
`permissions`). Toute la couche de gates par hook documentée dans
`hooks-and-protections.md §1` et `gates-map.md §4` était donc **inerte** sur ce
dépôt : `protect_framework`, `preflight_cost_cap`, `preflight_agent_budget`,
`enforce_tdd`, `block_env_bypass`, `validate_acceptance_gate`,
`audit_file_ownership`, `preflight_stack_combo`, `enforce_two_stage_auditor`,
`validate_stack_consistency`, `validate_augment_contract`, etc. Les 19 modules
existent bien sous `.claude/python/sdd_hooks/`, mais aucun n'était appelé par le
runtime. Le test `test_gates_map.py::test_hook_enforcers_still_wired_in_settings`
échouait en conséquence.

Par ailleurs `settings.json` et `settings.local.json` étaient **pollués** par les
grants de permissions d'un autre projet (`consent-hub-admin`, `SDD-Pro`,
`TarckingMpf` — chemins absolus étrangers dans `allow` et `additionalDirectories`).

La politique `hooks-and-protections.md §4` exige un ADR
`governance-protection-{slug}` pour toute modification du jeu de hooks : le présent
ADR remplit cette exigence.

---

## Decision

1. **Câbler la section `hooks` complète** dans `.claude/settings.json`, conforme à
   `hooks-and-protections.md §1` (16 hooks) + `gates-map.md §4`, plus le hook
   `Stop` `framework_smoke` (§2). Invocation via le wrapper cwd-safe
   `_hook.run('sdd_hooks.X')` (pattern documenté `_hook.py:29`).

   Mapping événement → matcher :
   - **PreToolUse** `Edit|Write|MultiEdit` : `protect_framework`, `pre_write_lint`,
     `enforce_tdd`
   - **PreToolUse** `Bash` : `block_env_bypass`
   - **PreToolUse** `Glob` : `preflight_glob_scope`
   - **PreToolUse** `Agent` : `preflight_agent_budget`, `preflight_cost_cap`,
     `enforce_two_stage_auditor`
   - **PreToolUse** `Skill` : `preflight_stack_combo`, `auto_invoke_complexity_router`
   - **PostToolUse** `Edit|Write|MultiEdit` : `validate_stack_consistency`,
     `validate_augment_contract`
   - **PostToolUse** `Agent` : `record_token_usage` (opt-in, no-op par défaut)
   - **SubagentStop** agents LLM : `audit_file_ownership` (12 agents), `record_token_usage`
   - **SubagentStop** `po` : `resolve_po_hash_sentinel`
   - **SubagentStop** `qa` : `validate_acceptance_gate`
   - **SessionStart** `startup|resume|clear|compact` : `session_start`
   - **Stop** : `sdd_admin.framework_smoke --strict --silent-on-pass`

2. **Nettoyer** `settings.json` et `settings.local.json` de toute permission /
   `additionalDirectories` étrangère au dépôt `sdd-pro`. Sauvegardes conservées en
   `*.pre-hooks-audit.bak`.

3. **Réconciliation doc** : `enforce_tdd` (cité par `gates-map.md §4` et présent sur
   disque) n'était pas listé dans `hooks-and-protections.md §1` aux côtés de
   `pre_write_lint`. Les deux sont désormais câblés ; la mise à jour de l'inventaire
   §1 est un suivi mineur (non bloquant, le SSoT machine est `settings.json`).

---

## Consequences

**Positifs :**
- Les protections runtime (cost cap, budget agent, framework write-guard, TDD,
  acceptance gate, ownership, combo SLA, two-stage auditors) deviennent **actives**
  sur Claude Code — le dépôt passe du niveau « documenté » au niveau « appliqué ».
- `test_gates_map.py` repasse au vert (anti-rot du registre restauré).
- `settings.json` redevient propre et spécifique à ce dépôt.

**Négatifs / dette acceptée :**
- Changement de comportement runtime : les hooks bloquants s'exécutent désormais.
  Mitigation vérifiée avant câblage : `protect_framework` est en mode **warn** en
  interactif (strict uniquement en CI, `is_ci()`), les 10 PreToolUse retournent
  **exit 0** sur entrée bénigne, et `framework_smoke` sort **0** (pass).
- `settings.json` est lui-même dans la liste protégée de `protect_framework` : toute
  édition ultérieure passera par le mode warn (interactif) ou devra se faire hors
  hook (Bash) — comportement voulu (protection du fichier de config).
- Les grants de permissions locaux de l'ancien projet sont perdus (sauvegardés en
  `.bak`) — l'utilisateur re-grantera au besoin sur ce dépôt.

---

## Alternatives considérées

- **Ne rien câbler (statu quo)** : écartée — laisse toute la couche de gates inerte
  et `test_gates_map` rouge, contredit la doc canonique.
- **Câbler sans ADR ni nettoyage** : écartée — violerait `hooks-and-protections.md §4`
  (ADR obligatoire) et laisserait la pollution cross-projet.
- **Câbler uniquement les 10 enforcers §4** (minimum pour le test) : écartée — laisse
  un jeu de hooks partiel vs l'inventaire §1 ; « faire les choses bien » = jeu complet.

---

## Liens

- Inventaire hooks : `.claude/docs/hooks-and-protections.md` (§1, §2, §4)
- Registre gates : `.claude/docs/gates-map.md §4`
- Wrapper d'invocation : `.claude/python/_hook.py`
- Test anti-rot : `.claude/python/tests/test_gates_map.py`
- Sauvegardes pré-nettoyage : `.claude/settings.json.pre-hooks-audit.bak`,
  `.claude/settings.local.json.pre-hooks-audit.bak`
- Audit source : mémoire projet `audit-general-2026-07-25` (#3)
