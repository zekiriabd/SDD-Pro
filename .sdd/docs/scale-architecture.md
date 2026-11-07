# Passage à l'échelle — état réel, verrous posés, et ce qu'il manque pour N agents

> Rédigé après l'audit du 2026-11-07 (quatre lots : hooks, tokens/coûts,
> architecture, code Python) et la campagne de correction qui a suivi.
> Ce document dit ce que le framework **fait** à l'exécution, pas ce que
> sa prose annonce. Il est la référence pour toute discussion « 1000 agents ».

## 1. Ce que l'audit a établi (avant correction)

| Promesse | Réalité mesurée le 2026-11-07 |
|---|---|
| `MaxParallel: 3` borne le parallélisme | Aucun hook ne le lisait ; consigne de prompt uniquement |
| `MaxCostPerRun` coupe un run trop cher | `token_usage` contenait 65 tokens d'entrée pour un run réel ≈ 100 $ ; cap jamais déclenchable |
| Matrice d'ownership enforcée | `audit_file_ownership` lisait `tool_input.subagent_type`, champ absent du payload `SubagentStop` : jamais exécuté |
| Hooks « strict » | Tous en `warn` hors `CI=1` ; dispatcher `_hook.py` fail-open sur crash |
| Orchestration déterministe | `sdd-full.md` 855 lignes interprétées par le LLM ; planner Python nourri par un `--state-inline` sérialisé par le modèle |
| Un run = un état | 8 runs en `running` jamais clos ; `status.json` annoncé source et absent du disque ; run-id partagé avec TTL 3 h |
| Verrous d'écriture | `file_locks` posés **par consigne** ; `atomic_write` avec nom de tmp déterministe |

## 2. Verrous mécaniques posés par la campagne du 2026-11-07

Ces mécanismes sont des hooks (exit 2 = refus) ou des scripts, pas des phrases
de prompt. Chaque ligne cite son enforcer ; `INVARIANTS.yml` les référence.

| Invariant | Enforcer | Comportement |
|---|---|---|
| Parallélisme borné | `sdd_hooks/enforce_max_parallel.py` (PreToolUse `Agent`, PostToolUse `Agent`, `SubagentStop`) | Compte les sous-agents SDD en vol pour la session ; refuse le spawn n°`MaxParallel+1` (`[MAX_PARALLEL_EXCEEDED]`) ; entrée en vol > 2 h = périmée |
| Ordre des phases | `sdd_hooks/enforce_phase_order.py` (PreToolUse `Agent`) | Refuse `dev-*` sans readiness, `qa` sans dev_run, reviewers sans qa ; FEAT non identifiable = refus ; base illisible = refus |
| Coût réel | `sdd_hooks/record_token_usage.py` (SubagentStop + Stop) + `preflight_cost_cap.py` | Usage sommé sur **tous les tours** depuis le transcript JSONL (`agent_transcript_path`) ; orchestrateur compté sur `Stop` ; cap = DENY réel |
| Ownership | `sdd_hooks/audit_file_ownership.py` (SubagentStop) | Lit `agent_type` ; DENY sur violation |
| Framework et artefacts de gate | `sdd_hooks/protect_framework.py` (PreToolUse `Edit|Write|MultiEdit|NotebookEdit` + `Bash|PowerShell`) | Strict pour tout appel de sous-agent (`agent_id`/`agent_type` présents) ; `.sys/.validation`, `.sys/.acceptance`, `.sys/.audit`, `.sys/.state` interdits en écriture aux agents |
| Secrets | `sdd_hooks/block_secret_access.py` (PreToolUse `Read|Grep|Glob|Bash|PowerShell`) | Un sous-agent ne lit ni `.env*` ni les configs générées contenant des valeurs réelles |
| Fail-closed | `.sdd/python/_hook.py` | Crash d'un hook de gate = exit 2 ; seuls les hooks informatifs restent exit 0 |
| Un run = une session | `sdd_lib/run_id.py` | Marker par `session_id`, clôture explicite `run_end()` ; plus de TTL 3 h |
| Base d'état | `sdd_lib/console_db` | Migrations transactionnelles idempotentes ; lecteurs de gate sans fallback `immutable` ; tests isolés via `SDD_CONSOLE_DB_PATH` |
| Écritures concurrentes | `sdd_lib/atomic_write.py`, `file_locks.py` | Tmp unique par writer ; reprise de lock stale avec grâce mtime |

## 3. Ce que cela permet, honnêtement

- **1 orchestrateur, ≤ `MaxParallel` sous-agents** : c'est le périmètre où les
  verrous ci-dessus sont testés. Le coût est mesuré, l'ordre des phases est
  imposé, les écritures framework et secrets sont refusées aux agents.
- **Plusieurs sessions Claude Code sur le même workspace** : possible pour des
  FEATs différentes (run-id par session, SQLite WAL + `busy_timeout`). Deux
  sessions sur la **même** FEAT ne sont pas arbitrées : la seconde doit être
  refusée par l'opérateur. Aucun hook ne l'impose aujourd'hui.

## 4. Ce qu'il manque pour 100 à 1000 agents

Le modèle d'exécution de Claude Code est : une session = un contexte LLM qui
appelle le tool `Agent`. Il n'existe ni file de tâches, ni worker, ni
planificateur hors du modèle. Pour dépasser quelques dizaines d'agents, il
faut sortir l'orchestration du LLM :

1. **Orchestrateur hors-LLM** : un processus (Python) qui lit `console.db`,
   calcule la prochaine action (`sdd_full_planner.py next-action` est déjà
   mécanique), et **lance** les agents via le Claude Agent SDK ou `claude -p`
   (`sdd_lib/spawn_agent.py` est le point de départ, encore non câblé au
   pipeline). Le tool `Agent` d'une session interactive n'est pas un
   ordonnanceur.
2. **File de tâches transactionnelle** : une table `tasks` (feat, us, phase,
   état, worker, lease, tentative) avec prise de bail atomique (`BEGIN
   IMMEDIATE`). SQLite tient jusqu'à quelques dizaines de workers sur une même
   machine ; au-delà, PostgreSQL.
3. **Isolation par worktree** : un worktree git par (FEAT, US) pour les agents
   dev, fusion par le worker de fin de phase. Sans cela, les écritures
   croisées sur `Program.cs`, `theme.css`, `constitution.md §6` restent un
   risque que seuls les locks par consigne couvrent.
4. **Budget par run réellement appliqué par l'orchestrateur**, pas par un hook
   de session : le hook `preflight_cost_cap` protège une session ; l'orchestrateur
   doit refuser de prendre un bail quand le budget du run est atteint.
5. **Observabilité** : `agent_journal` doit porter `inputs_hash` / `output_hash`
   pour rejouer ou dédupliquer un travail ; aujourd'hui ces colonnes sont vides.

Ordre de grandeur : un `/sdd-full` à 3 US coûte 100 à 250 $ (mesuré sur la
génération 4.x, ≈ 30 % de moins en 5.5). 1000 agents en parallèle sans
file de tâches ni budget central n'est pas un objectif atteignable ; 1000
**exécutions** d'agents réparties sur des runs bornés, avec l'architecture
du §4, l'est.

## 5. Pointeurs

- `.sdd/INVARIANTS.yml` — un enforcer par invariant, vérifié par
  `tests/test_invariants_manifest.py`
- `.sdd/docs/hooks-and-protections.md` — table hook → bloque ? / bypass ? / fail-open ?
- `.sdd/docs/cache-strategy.md` — télémétrie réelle (transcripts), plus de chiffres « dernier tour »
- `.sdd/docs/KNOWN-LIMITATIONS.md §3.4` — `console.db` non distribué
