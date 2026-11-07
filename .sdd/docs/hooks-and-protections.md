# SDD_Pro — Hooks & Protections (inventaire canonique)

> **Source de vérité unique** des hooks Claude Code et scripts de protection
> branchés sur le pipeline SDD_Pro. Tout ajout/suppression/renommage de
> protection DOIT mettre à jour ce fichier ET produire un ADR
> `governance-protection-{slug}` (cf. `VERSIONING.md`).
>
> **Révision audit sécurité 2026-11** — ce document décrit ce que chaque hook
> fait *réellement* : quand il bloque (exit 2), quand il ne fait qu'avertir,
> et ce qui reste contournable. Aucune protection heuristique n'est présentée
> comme une barrière absolue.

---

## 0. Ce qu'un hook peut — et ne peut pas — garantir

| Fait (doc Claude Code) | Conséquence |
|---|---|
| `exit 2` = refus ; `exit 1` (ou toute autre valeur) = **non bloquant** | Un hook qui plante en `exit 1` laisse passer l'outil. Depuis 2026-11, `_hook.py` convertit toute exception non gérée en `exit 2` + `CAUSE: [HOOK_CRASH]` (sauf hooks informatifs, §0.2). |
| Timeout par hook : **600 s** par défaut | Un hook qui pend est tué et l'outil passe : **fail-open par construction du harnais**. Les hooks qui lancent un sous-process bornent leur `timeout` et traitent l'expiration en DENY. |
| `PreToolUse` émis dans un sous-agent porte `agent_id` + `agent_type` ; la session principale non | Permet une politique **stricte pour les agents**, **souple pour le Tech Lead** (`sdd_lib.hook_input.is_subagent_call`). |
| `SubagentStop` porte `agent_type`, `agent_id`, `agent_transcript_path` (pas `tool_input`) | `audit_file_ownership` lit enfin le bon champ (avant : jamais exécuté) et attribue les écritures via le transcript. |
| `PostToolUse` / `SubagentStop` `exit 2` | L'action a **déjà eu lieu** : exit 2 renvoie le message à l'agent (qui doit corriger / ne peut pas s'arrêter), il n'annule rien. |
| Une variable positionnée dans le shell d'un outil Bash/PowerShell n'atteint pas le process Claude Code | Les hooks lisent l'environnement du **process Claude Code**. Un `export SDD_X=1` d'agent n'affecte que les scripts lancés depuis ce shell — c'est ce vecteur que `block_env_bypass` ferme. |

### 0.1 Politique de mode commune

| Contexte | Hooks à mode (`protect_framework`, `enforce_tdd`, `block_secret_access`) |
|---|---|
| CI (`sdd_lib.ci.is_ci`) | strict (DENY) |
| Appel émis par un **sous-agent** | strict (DENY) |
| **Session principale** (Tech Lead humain) | warn (stderr, ALLOW) |
| Override | variable d'env dédiée, **uniquement** dans l'environnement du process Claude Code (shell parent ou bloc `env` de `.claude/settings.local.json`) — toute tentative inline est refusée par `block_env_bypass` |

### 0.2 Lanceur `_hook.py` (fail-closed)

* Toute exception non gérée d'un hook → `ERROR / CAUSE: [HOOK_CRASH] / FIX` + **exit 2**.
* Exception : `INFORMATIONAL_HOOKS` = `statusline`, `session_start`,
  `record_token_usage`, `auto_invoke_complexity_router`,
  `resolve_po_hash_sentinel`, `framework_smoke` → WARN + exit 0.
* Racine du dépôt : `CLAUDE_PROJECT_DIR` d'abord ; à défaut, remontée depuis le
  cwd avec le triple marqueur `.sdd/agents` + `.sdd/commands` + `workspace`.
  **Risque résiduel** : sans `CLAUDE_PROJECT_DIR`, lancer Claude Code depuis
  un sous-dossier d'un clone non fiable qui contient son propre `.sdd/` ferait
  exécuter le Python de ce clone.

---

## 1. Hooks — ce qui bloque réellement

Légende : **DENY** = exit 2 ; **WARN** = stderr + exit 0 ; *heuristique* =
détection par motif, contournable par construction.

### 1.1 `protect_framework` — PreToolUse `Edit|Write|MultiEdit|NotebookEdit` **et** `Bash|PowerShell`

| | |
|---|---|
| Script | `.sdd/python/sdd_hooks/protect_framework.py` |
| Périmètre fichier | `FRAMEWORK_OWNED` (`.sdd/**` foyer + façades `.claude/` `.codex/` `.gemini/`, faits db-reverse `workspace/old/*/.sys/db-*.json`) **+ artefacts de gate** `workspace/.sys/.validation/`, `.acceptance/`, `.audit/`, `.state/` |
| Exception artefacts | un agent peut écrire les fichiers que **son** bloc `writes:` de `loader.yml` déclare (rapports d'auditeurs, `{n}-api-tests.json` de qa, sentinels `.state/*.flag` d'arch/dev-*). `acceptance.json` n'est déclaré pour aucun agent : il n'est produit que par `validate_acceptance.py`. |
| Mode shell (*heuristique*) | tokenise la commande (segments `&&` `\|\|` `\|` `;` `&` hors guillemets) et refuse : redirection `>`/`>>` vers un chemin protégé ; `tee`, `cp`, `mv`, `rm`, `mkdir`, `touch`, `Set-Content`, `Add-Content`, `Out-File`, `Copy-Item`, `Move-Item`, `Remove-Item`, `New-Item`… sur un chemin protégé ; `sed -i` / `perl -i` ; `git checkout|restore|clean|reset|rm|mv|stash` sur `.sdd`/`.claude` ; `python -c` / `node -e` / `pwsh -Command` contenant une écriture (`open(..,'w')`, `write_text`, `unlink`, `shutil.`…) et un chemin protégé. |
| Bloque ? | **DENY** : CI, sous-agent. **WARN** : session principale. |
| Bypass | `SDD_PROTECT_FRAMEWORK_MODE=warn\|strict\|off` (env du process Claude Code). `SDD_PROTECT_FRAMEWORK_FAIL_OPEN=1` (debug du hook seulement). |
| Fail-open ? | Non : exception interne → DENY `[HOOK_CRASH]`. |
| Contournable | chemin construit dynamiquement (`D=.sdd; rm -rf $D`), script écrit ailleurs puis exécuté, outil d'écriture non listé. |

### 1.2 `block_env_bypass` — PreToolUse `Bash|PowerShell`

| | |
|---|---|
| Script | `.sdd/python/sdd_hooks/block_env_bypass.py` |
| Noms protégés | `SDD_ALLOW_*`, `SDD_DISABLE_*`, `SDD_BYPASS_*`, `SDD_PROTECT_*`, `SDD_TDD_*`, `SDD_BUDGET_*`, `SDD_TOKEN_USAGE_*`, `SDD_AUDIT_*`, `SDD_PRE_WRITE_LINT_*`, `SDD_HOOK_*`, `SDD_*_MODE`, `SDD_*_STRICT`, `SDD_REPO_ROOT`, `SDD_CONSOLE_DB_PATH`, `CI` |
| Formes détectées (*heuristique*) | POSIX `export`/`declare -x`/inline `NAME=`/`env NAME=`/`unset`/`env -u`, `eval`/`source`/`printf`/`bash -c` ; PowerShell `$env:NAME=`, `${env:NAME}=`, `Set-Item`/`New-Item`/`Remove-Item env:NAME`, `[Environment]::SetEnvironmentVariable` ; Windows `setx`, `set NAME=` ; `os.environ[...]=`, `os.environ.update/setdefault`, `os.putenv`, `process.env.NAME=`, dict `{NAME: …}` en `env=` dans du code inline ; indirection (`V=SDD_X; export $V`). Quotes / backslashes / backticks normalisés avant analyse (`SDD_ALLOW_X"Y"`). **Les heredocs sont analysés** (bash les exécute). |
| Bloque ? | **DENY** toujours (session principale comprise). Journal : `workspace/.sys/.audit/env-bypass.jsonl` (valeurs de secrets masquées). |
| Conséquence assumée | un message de commit en heredoc qui contient une assignation protégée est refusé → `git commit -F fichier`. |
| Contournable | nom construit dynamiquement (base64, `chr()`, concaténation dans un langage tiers), script déposé sur disque puis exécuté. Il n'existe **aucune** règle `permissions.deny` complémentaire. |

### 1.3 `block_secret_access` — PreToolUse `Read|Grep|Glob|Bash|PowerShell` (NOUVEAU 2026-11)

| | |
|---|---|
| Script | `.sdd/python/sdd_hooks/block_secret_access.py` |
| Toujours sensibles | `.env`, `.env.*` (sauf `.example`/`.sample`/`.template`/`.dist`), `**/secrets/**`, `*.pem`, `*.pfx`, `*.p12`, `id_rsa*`, `workspace/.sys/.secrets/**` |
| Sensibles selon contenu | sous `workspace/src/` : `appsettings*.json`, `application*.yml\|yaml\|properties`, `config/default.json` — refus seulement s'ils contiennent une **valeur réelle** (ni vide ni `${VAR}`) sur une clé `*Password`/`*Pwd`/`*Secret`/`*Token`/`*ApiKey`, un `Password=`/`Pwd=` en clair dans une chaîne de connexion ou `user:pass@` dans une URI. (Choix : `arch` doit pouvoir Read puis Edit ces fichiers pour y mettre des placeholders.) |
| Bloque ? | **DENY** `[SECRET_ACCESS_FORBIDDEN]` : sous-agent. **WARN** : session principale. |
| Bypass | `SDD_ALLOW_SECRET_ACCESS=1` (env du process Claude Code). |
| Contournable (*heuristique*) | `grep -r Password workspace/src` sur un répertoire entier, chemin construit dynamiquement, copie préalable sous un autre nom. Clés `*Token`/`*Secret` camelCase : seuil d'entropie (≥ 16 car., ou ≥ 8 avec lettre + chiffre + symbole) pour éviter les faux positifs → un secret court et simple passe. |

### 1.4 `preflight_secret_scan` — PreToolUse `Agent`

| | |
|---|---|
| Rôle | Avant un spawn : si un fichier que l'agent **lira** d'après ses `reads:` `loader.yml` (stack.md ou config générée sous `workspace/src/`) contient un secret réel → **DENY** `[SECRET_ACCESS_FORBIDDEN]`, quel que soit le provider. `.env` avec secrets réels → WARN. Provider non-Anthropic + secrets dans stack.md → WARN `[SECRET_PROVIDER_LEAK_RISK]` (une fois par run). |
| Correctif | `${DB_PASSWORD}` n'est plus pris pour un secret ; la forme liste ` - KEY: valeur` de stack.md est reconnue. |
| Bypass | `SDD_ALLOW_SECRET_IN_CONTEXT=1` (DENY → WARN) ; `SDD_ALLOW_SECRET_TO_PROVIDER=1` (WARN provider). |
| Limite | agents absents de `loader.yml` (built-ins, module reverse) : non bloqués ici — leurs lectures directes passent par `block_secret_access`. |

### 1.5 Télémétrie & coût — `record_token_usage`, `preflight_cost_cap`

| | |
|---|---|
| `record_token_usage` | **Ne s'appuie plus sur `PostToolUse Agent`.** Lit le **transcript JSONL complet** : sur `SubagentStop` (`agent_transcript_path`, coût du sous-agent) et sur `Stop` (transcript de l'orchestrateur). Informatif : crash → exit 0. |
| `preflight_cost_cap` (PreToolUse `Agent`) | Compte **orchestrateur + sous-agents** pour le run. Base illisible / indisponible (`ConsoleDbUnavailable`) → **DENY `[INFRA_BLOCKED]`**. Modèle sans tarif connu → **tarif conservateur + WARN** (plus de DENY en CI). Bypass : `SDD_DISABLE_COST_CAP=1` ou `MaxCostPerRun: 0`. |
| `preflight_agent_budget` (PreToolUse `Agent`) | Budget de contexte par agent (`loader.yml reads:`), `SDD_BUDGET_MODE`. |

> Ces trois hooks relèvent d'un autre lot ; voir leurs docstrings pour le détail.

### 1.6 `enforce_two_stage_auditor` — PreToolUse `Agent`

| | |
|---|---|
| Rôle | Refuse `code-reviewer` / `security-reviewer` / `arch-reviewer` tant que Stage A (`spec-compliance-reviewer`) n'a pas un verdict non-RED < 24 h pour la FEAT. |
| Source du verdict | **recalculé** (plus jamais lu) : depuis `console.db.qa_spec_compliance` (lignes par AC écrites par `ingest_agent_report.py`), seuil `SpecComplianceFailOn` (défaut `serious`) ; repli sur `{n}-spec-compliance.json` en recalculant depuis `us[].acs[]` (`summary.verdict` ignoré). Une AC non vérifiée sans sévérité compte `critical`. |
| Bloque ? | **DENY** : verdict RED, aucun verdict frais, FEAT non extractible du prompt (`[TWO_STAGE_FEAT_UNKNOWN]`), console.db absente/illisible (`[INFRA_BLOCKED]`), payload illisible. |
| Bypass | `AuditorBatchMode: legacy-parallel` ; `SDD_BYPASS_TWO_STAGE=1`. |
| Limite | les statuts AC restent le jugement de l'agent Stage A : le hook garantit l'**ordre** et la **cohérence verdict ↔ AC**, pas la justesse du jugement. |

### 1.7 `validate_acceptance_gate` — SubagentStop `^qa$`

| | |
|---|---|
| Rôle | Lit `workspace/.sys/.acceptance/acceptance.json` produit par `sdd_scripts/validate_acceptance.py` (lancé par qa, STEP 9.bis). Le hook ne relance pas les tests (durée). |
| Bloque ? | **DENY** : rapport absent, périmé (> 24 h), JSON corrompu (`[INFRA_BLOCKED]`), `unresolved`, `fail` en mode strict, verdict inconnu, verdict `bypass` sans `SDD_ALLOW_ACCEPTANCE_BYPASS` dans l'environnement **du hook**. ALLOW : `pass`, `warn`, `skipped`, `fail` en mode non strict. |
| Anti-forge | `acceptance.json` n'est inscriptible par aucun agent (§1.1, fichier + shell). |
| Limite | exit 2 sur `SubagentStop` empêche qa de s'arrêter mais n'annule rien. Un agent qui réécrit le JSON par un moyen non détecté par l'heuristique shell (§1.1) n'est pas arrêté. |

### 1.8 `audit_file_ownership` — SubagentStop (agents de `OWNERSHIP_MATRIX`)

| | |
|---|---|
| Rôle | Vérifie la matrice `ownership.md §1` sur les fichiers **écrits par l'agent** : extraits du transcript (`agent_transcript_path`, tool_use Write/Edit/MultiEdit/NotebookEdit) — attribution exacte même avec agents parallèles. Repli sans transcript : walk de `workspace/` par mtime depuis le début du dispatch (approximatif si agents parallèles). |
| Correctif 2026-11 | le hook lisait `tool_input.subagent_type`, absent de `SubagentStop` → il sortait en ALLOW avant tout scan : la matrice n'était **jamais** appliquée. |
| Bloque ? | **DENY** par défaut (session et CI) : l'agent reçoit la liste et doit corriger avant de s'arrêter. `SDD_AUDIT_OWNERSHIP_MODE=warn` → WARN ; `off` → journal seul (`.sys/.audit/ownership-violations.log`). |
| Limite | écritures faites via Bash/PowerShell absentes du transcript (non auditées si un transcript existe) ; post-hoc : rien n'est annulé. |

### 1.9 `enforce_tdd` — PreToolUse `Edit|Write|MultiEdit`

| | |
|---|---|
| Rôle | Nouveau symbole de production sous `workspace/src/` sans test compagnon → `[TDD_NO_TEST_FIRST]`. Symboles `public`, `internal`, `private`, `protected` et classes sans modificateur (C#), `internal`/`private fun` (Kotlin), etc. Un compagnon **sans aucun cas de test** (`[Fact]`, `[Test]`, `@Test`, `it(`, `test(`, `def test_`) ne compte pas. |
| Bloque ? | **DENY** : CI, sous-agent. **WARN** : session principale. |
| Bypass | `SDD_TDD_MODE=off\|warn\|strict`, `SDD_DISABLE_TDD=1`. |
| Contournable (*heuristique*) | compagnon trouvé par nom (`*{stem}*`) : un test sans rapport portant le même nom suffit ; détection regex des symboles. |

### 1.10 `pre_write_lint` — PreToolUse `Edit|Write|MultiEdit`

| | |
|---|---|
| Garde secrets (2026-11) | Écriture d'une **valeur réelle** sur une clé sensible dans `workspace/stack/stack.md` ou une config générée (`appsettings*.json`, `application*.yml`, `config/default.json`) → **DENY** `[SECRET_ACCESS_FORBIDDEN]`, en session comme en sous-agent, indépendamment de `SDD_DISABLE_PRE_WRITE_LINT`. Bypass : `SDD_ALLOW_SECRET_IN_CONFIG=1`. `.env` n'est pas concerné (c'est l'emplacement prévu des valeurs). |
| Lint motifs interdits | WARN par défaut ; DENY si `SDD_PRE_WRITE_LINT_STRICT=1`. |

### 1.11 `preflight_stack_combo` / `preflight_reverse_gate` — PreToolUse `Skill`

| | |
|---|---|
| Rôle | Avant `/sdd-full`, `/sdd-poc`, `/dev-run` : combo stack validé (`validate_stack_combo.py`) ; FEAT reverse de confiance `high` (`check_reverse_feat_for_full.py`). |
| Bloque ? | **DENY** : combo non testé/invalide, FEAT reverse medium/low, **et désormais** script absent, timeout, `stack.md` illisible (exit 4), code de sortie inattendu, FEAT ambiguë (> 1 fichier) → `[INFRA_BLOCKED]`. ALLOW : combo expérimental (WARN), FEAT pas encore créée, pas de numéro de FEAT. |
| Bypass | `SDD_ALLOW_UNTESTED_COMBO=1` ; `SDD_ALLOW_REVERSE_LOW=1`. |

### 1.12 `validate_augment_contract` — PostToolUse `Edit|Write|MultiEdit`

Contrat `preserves:` / `adds:` du plan. **Write est désormais vérifié** (un
Write qui écrasait un fichier `operation: augment` contournait `preserves:`).
Exit 2 post-hoc : l'agent reçoit `[PRESERVES_VIOLATED]` / `[ADDS_VIOLATED]`,
l'écriture a déjà eu lieu.

### 1.13 Autres hooks (inchangés par ce lot)

| Hook | Événement | Comportement |
|---|---|---|
| `preflight_glob_scope` | PreToolUse `Glob` | Glob non borné : WARN (DENY si `SDD_GLOB_SCOPE_STRICT=1`). |
| `validate_stack_consistency` | PostToolUse `Edit\|Write\|MultiEdit` | Cohérence stack, WARN/STOP post-hoc. |
| `resolve_po_hash_sentinel` | SubagentStop `^po$` | Résolution du sentinel de hash — informatif. |
| `auto_invoke_complexity_router` | PreToolUse `Skill` | Additif, jamais bloquant. |
| `session_start` | SessionStart | Bannière, jamais bloquant. |
| `statusline`, `framework_smoke` | Stop | Informatifs. |
| `enforce_phase_order`, `enforce_max_parallel` | (autre lot) | Voir leurs docstrings. |

---

## 2. Tableau de synthèse

| Hook | Bloque (exit 2) | Mode par défaut | Bypass (env du process Claude Code) | Fail-open restant |
|---|---|---|---|---|
| `_hook.py` (lanceur) | crash → oui | — | — | timeout harnais 600 s ; hooks informatifs |
| `protect_framework` | oui (CI, sous-agent) | warn session principale | `SDD_PROTECT_FRAMEWORK_MODE`, `…_FAIL_OPEN` | heuristique shell |
| `block_env_bypass` | oui, toujours | — | aucun | heuristique (noms dynamiques) |
| `block_secret_access` | oui (sous-agent) | warn session principale | `SDD_ALLOW_SECRET_ACCESS` | heuristique (grep de répertoire, chemins dynamiques) |
| `preflight_secret_scan` | oui (agents `loader.yml`) | — | `SDD_ALLOW_SECRET_IN_CONTEXT` | agents hors `loader.yml` |
| `pre_write_lint` (secrets) | oui | — | `SDD_ALLOW_SECRET_IN_CONFIG` | formats de secret non reconnus |
| `enforce_two_stage_auditor` | oui | — | `SDD_BYPASS_TWO_STAGE`, `legacy-parallel` | jugement AC de l'agent Stage A |
| `validate_acceptance_gate` | oui (post-hoc) | — | `SDD_ALLOW_ACCEPTANCE_BYPASS` | réécriture non détectée du JSON |
| `audit_file_ownership` | oui (post-hoc) | strict | `SDD_AUDIT_OWNERSHIP_MODE` | écritures shell ; repli mtime |
| `enforce_tdd` | oui (CI, sous-agent) | warn session principale | `SDD_TDD_MODE`, `SDD_DISABLE_TDD` | appariement par nom |
| `preflight_stack_combo` | oui | — | `SDD_ALLOW_UNTESTED_COMBO` | — |
| `preflight_reverse_gate` | oui | — | `SDD_ALLOW_REVERSE_LOW` | FEAT non créée / sans numéro |
| `validate_augment_contract` | oui (post-hoc) | — | — | aucun plan = rien à vérifier |

Tous les noms de bypass ci-dessus sont refusés par `block_env_bypass` s'ils
sont positionnés depuis une commande d'agent.

---

## 3. Scripts hors hooks touchés par l'audit 2026-11

| Script | Changement |
|---|---|
| `sdd_reverse_scripts/reverse_proc_introspect.py` | `--conn-str` refuse toute valeur portant un mot de passe (`Password=`, `pwd=`, `?password=`, `user:pass@`, Oracle `user/pass@`) ; `--conn-str -` lit stdin ; variable `SDD_DB_CONN` ; sinon stack.md. |
| `sdd_reverse/db_introspect.py` | Échappement ODBC `{…}` / libpq `'…'` ; MySQL refuse `;` dans une valeur. SQL Server : transaction explicite (`autocommit=False`) **rollbackée** avant fermeture ; `ApplicationIntent=ReadOnly` et `readonly=True` documentés comme **non contraignants** (seul PostgreSQL `set_session(readonly=True)` l'est côté serveur ; la vraie barrière = `readonly_guard` + login moindre privilège). Refus d'un pragma de session → WARN (plus silencieux). |
| `sdd_scripts/server_control.py` | `start` / `register` enregistrent PID, port, image, commande, heure dans `workspace/.sys/.state/serve.pids.json` ; `stop` (et `--port L:P`) ne tue que les PID enregistrés et vérifiés (`tasklist /FI` / `ps`, PID recyclé ignoré) ; sans registre → refus ; `--force-port` = ancien comportement. |
| `sdd_lib/env_placeholders.py` | Seule la forme `${VAR}` est expansée (la forme nue `$VAR` mangeait les `$` des valeurs). |

---

## 4. Politique : tout changement de protection exige un ADR

> **Toute modification du jeu de hooks/protections (ajout, suppression,
> migration, renommage) DOIT être tracée par un ADR
> `governance-protection-{slug}` AVANT le merge sur `main`. Ce fichier DOIT
> être mis à jour dans la même PR.**

---

## 5. Bypass d'urgence (Tech Lead)

* **Un hook précis** : poser sa variable de bypass (§2) dans l'environnement
  du process Claude Code — shell parent avant le lancement, ou bloc `env` de
  `.claude/settings.local.json` (gitignoré). Jamais dans une commande.
* **Désactiver le câblage** : surcharger le groupe de hooks dans
  `.claude/settings.local.json` (à réverter, ou ADR si durable).
* `.claude/settings.json` lui-même est protégé (§1.1) : une modification par
  un agent est refusée.

---

## 6. Historique — migration PowerShell → Python (v6.5+)

Les 23 scripts `.ps1` historiques ont tous un équivalent Python branché
(`.claude/hooks/*.ps1` → `sdd_hooks/*.py`, `.claude/scripts/*.ps1` →
`sdd_scripts/` / `sdd_admin/`). Détail : `.sdd/docs/MIGRATION.md`.

## 7. Pointeurs

- `.claude/settings.json` — câblage actif
- `.sdd/python/sdd_hooks/` — hooks
- `.sdd/python/_hook.py` — lanceur fail-closed
- `.sdd/python/sdd_lib/hook_input.py` — lecture des payloads (sous-agent, SubagentStop)
- `.sdd/docs/gates-map.md` — registre des gates
