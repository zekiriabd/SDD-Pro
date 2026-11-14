---
name: sdd-full
description: /sdd-full — Pipeline complet de A à Z pour 1 FEAT
---
# /sdd-full — Pipeline complet de A à Z pour 1 FEAT

> **Runner mécanique (lot « orchestration mécanique », 2026-11-07).** Cette
> commande n'est plus un script de 19 STEPs interprété : c'est une **boucle
> stricte** autour de `sdd_full_planner.py`, qui lit l'état RÉEL (console.db
> `runs` / `run_phases` / `events` + disque : US, plans, rapports
> `.sys/.validation/`) et rend la prochaine action exacte. Le détail de chaque
> phase vit dans la commande ou l'agent appelé — **ne pas le recopier ici**.
> L'ordre des phases est en plus garanti par le hook `enforce_phase_order`
> (refus `[PHASE_ORDER_VIOLATION]`) et le parallélisme par `enforce_max_parallel`.

Séquence rendue par le planner (une phase = une action) :

```
us_generate → [gate afterUS] → readiness → [gate afterReadiness] → plan (si déclenché)
→ dev_run (arch → back → API gate → front) → [gate afterCode] → doc_refresh
→ qa → auditor_batch (spec Stage A → quality Stage B) → feat_validate_postdev
→ sdd_review → spec-book (best-effort) → done
```

## Utilisation

```
/sdd-full {n}                            # strict : STOP sur readiness WARN ou NO-GO
/sdd-full {n} --plan                     # plan-review même sur GO (≥ 2 US recommandé)
/sdd-full {n} --force                    # assume WARN/NO-GO (plan-review obligatoire)
/sdd-full {n} --force --no-plan-on-warn  # escape hatch (2 bypass → SDD_ALLOW_FORCE=1)
/sdd-full {n} --no-validate              # bypass readiness (audit-loggué)
/sdd-full {n} --rebuild-arch             # force l'agent arch même si bootstrap stable
/sdd-full {n} --manual-gates[=us,plan]   # gates manuelles (toutes ou sous-ensemble)
/sdd-full {n} --no-manual-gates          # override ManualGates du Project Config
/sdd-full {n} --resume                   # reprise (gate validée, crash) — état = console.db
```

Flags parsés par **argparse** (`sdd_full_planner.py args`) — aucun flag n'est
interprété par le LLM. Surface : `--force`, `--plan`, `--no-plan-on-warn`,
`--no-validate`, `--rebuild-arch`, `--manual-gates`, `--no-manual-gates`,
`--resume`. Le parallélisme se règle via `MaxParallel:` (Project Config),
appliqué par le hook `enforce_max_parallel`.

---

## STEP 0 — Préconditions (une fois)

1. **Parser les flags** (obligatoire) — `{raw}` = argument brut de la commande :

   ```bash
   python .sdd/python/sdd_scripts/sdd_full_planner.py args --input "{raw}"
   ```

   Exit ≠ 0 → STOP, propager stderr (`[INVALID_ARG]` : n absent/non entier,
   flag inconnu, token `--manual-gates` hors `us|readiness|plan|code`).
   La sortie JSON porte `feat_number` et `tags` (csv pour l'étape 2).

2. **Ouvrir le run** (observabilité + état de reprise) :

   ```bash
   # nominal
   python .sdd/python/sdd_scripts/sdd_state.py new-run --feat-number {n} --command "/sdd-full" --tags "{tags}"
   # --resume : réutiliser le dernier run de la FEAT (aucun new-run)
   python .sdd/python/sdd_scripts/sdd_state.py get-run --feat-number {n} --latest
   ```

   Retenir `RUN_ID` et le passer **explicitement** (`--run-id`) aux appels
   suivants : une variable shell ne survit pas d'un appel Bash à l'autre. Sans
   `--run-id`, le planner prend le run `running` le plus récent de la FEAT.

Les autres préconditions sont portées par le planner et rendues comme
`action: stop` : FEAT absente / ambiguë (`[FEAT_NOT_FOUND]`, `[FEAT_AMBIGUOUS]`),
anti-cumul bypass (`[FORCE_CUMUL_REJECTED]`, via `preflight_force_cumul`),
config invalide, run inconnu.

---

## STEP 1 — Boucle (jusqu'à `action ∈ {done, stop}`)

```bash
python .sdd/python/sdd_scripts/sdd_full_planner.py next-action --feat {n} --run-id "$RUN_ID" --json
```

Exécuter **exactement** l'action rendue, puis enregistrer son résultat avec la
commande donnée dans `record_hint`, puis relancer `next-action`. Ne jamais
sauter une action, ne jamais en inventer une, ne jamais réordonner.

| `action` | Exécution | Enregistrement |
|---|---|---|
| `skill` | invoquer `command` (ex. `/us-generate {n}`, `/feat-validate {n} --json`, `/dev-plan {n}`, `/dev-run {n} [--rebuild-arch]`, `/qa-generate {n}`, `/sdd-review {n}`, `/spec-book {n}`) en transmettant `env.SDD_RUN_ID` | `record_hint` — `--verdict` pour readiness (GO/WARN/NO-GO), qa / auditor_batch / sdd_review (GREEN/YELLOW/RED), sinon `--status` |
| `script` | exécuter `command` (Python déterministe, 0 token) ; `exit_map` donne le statut par code retour | `record_hint` (non bloquant si `blocking: false` : exit ≠ 0 → `--status warn`) |
| `procedure` | dérouler `steps` dans l'ordre (two-stage auditors : `@.sdd/rules/auditor-orchestration.md §2-§4`) | `record_hint` avec le verdict consolidé |
| `checkpoint` | afficher `reason` + `plans` + rapport, **attendre** la réponse humaine `ok` / `stop` / `retry` | `ok` → `options.ok` ; `stop` → STOP propre ; `retry` → `options.retry` |
| `gate` | AskUserQuestion 2 options : « Valider manuellement (console, STOP) » → `options.validate` puis STOP ; « Continuer sans valider » → `options.continue` | aucun (la décision vit dans la gate) |
| `stop` | émettre la ligne d'erreur (`error`, `reason`, `fix`, `report`) ; si `resumable` : `/sdd-full {n} --resume` après correction / validation | aucun |
| `script` vérification (`phase_id` ∈ `verify-build`, `verify-tests`, `record-spec`, `record-readiness`) | exécuter `command` (`verify_build.py`, `verify_tests.py --coverage`, `delivery_gate.py record-spec/record-readiness`) — build/tests **réellement exécutés**, preuve signée dans `delivery_evidence` | `record_hint` (`--step … --status pass` si exit 0, `fail` sinon) |
| `done` | exécuter le gate de livraison (STEP 2) **puis** `end_run` (`run_close.py`) puis `recap` | — |

**Échec d'une action** : enregistrer `--status fail` (ou le verdict RED) puis
relancer `next-action` — le planner rend `stop` (`[PHASE_FAILED]`). Les gates
bloquantes (QA RED si `QaFailOnSddFull`, review RED si `ReviewFailOnSddFull`)
sont appliquées par `record --verdict` : RED → `fail` (bloquant) ou `warn`
(bypass Project Config, audit-loggué dans `.sys/.audit/sdd-full-bypass.log`).

Les phases sautées pour une raison mécanique (US déjà présentes, `--no-validate`,
plan-review non déclenchée, `QAMode`/`ReviewMode` `off|manual`,
`SpecComplianceRequiredForFeatValidate: false`) sont **enregistrées `skip` par
le planner lui-même** (`auto_recorded` dans la sortie) — rien à faire.

---

## Règles load-bearing — où elles vivent

| Règle (ex-STEP) | Porteur |
|---|---|
| Parsing des flags (1) | `sdd_full_planner.py args` (argparse) |
| Anti-cumul bypass `[FORCE_CUMUL_REJECTED]` (1.bis, 3.6.quart) | `sdd_full_planner.compute_next_action` → `preflight_force_cumul.evaluate` |
| État du run / `--resume` (1.ter) | console.db `run_phases` lu par `next-action` ; noms canoniques `sdd_state._PIPELINE_PHASES_ORDER` |
| Gates manuelles `afterUS/afterReadiness/afterPlan/afterCode` (1.gates, 1.gate-proc) | planner (`action: gate` / `stop` pending) + `gate_decide.py` + console |
| FEAT Flyway → sentinel + `--rebuild-arch` (2.flyway) | planner (pose `flyway-migrate-requested.flag`, ajoute `--rebuild-arch`) ; exécution : agent `arch` Phase B STEP 8.5, `@.sdd/rules/library-and-stack.md` §C.6 |
| Tableau de décision readiness GO/WARN/NO-GO × `--force` / `--plan` / `--no-plan-on-warn` / `PlanReviewDefault` (3.5) | planner (`_plan_trigger`, stop `[READINESS_WARN]` / `[READINESS_NO_GO]`) |
| Plan-then-review bloquant `[PLAN_REVIEW_GATE_SKIPPED]` + idempotence mtime (3.6) | planner (`checkpoint`, `_plans_fresh`) |
| Audit log `--force` (3.7) | `sdd_full_planner.py record --phase readiness` → `.sys/.audit/force-bypass.log` |
| Arch short-circuit / bootstrap (4) | `/dev-run` → `detect_arch_shortcircuit.py` |
| INDEX ADRs (4.45) | planner (`script` index_adrs.py, non bloquant) |
| QA bloquante `QaFailOnSddFull` (4.5) | `record --verdict` (`status_from_verdict`) |
| Two-stage auditors (ex-`/dev-run` 6.4) | planner (`procedure` auditor_batch) + `@.sdd/rules/auditor-orchestration.md` + hooks `enforce_two_stage_auditor` / `enforce_phase_order` |
| Spec-compliance post-dev lecteur pur (4.7) | planner (`script` `validate_readiness.py --post-dev`, `exit_map`) |
| Review consolidée `ReviewMode` / `ReviewFailOnSddFull` (4.8) | planner + `/sdd-review` |
| Drift inline rules (4.9) | `sdd_full_planner.py recap` (`validate_inline_rules.py`, WARN `[DRIFT_SUSPECTED]`) |
| Récap + faux positif « code absent » (5) | `sdd_full_planner.py recap` (`[FALSE_POSITIVE_COMPLETION]`) |
| Cahier des charges post-pipeline | planner (`skill /spec-book`, best-effort : échec → `warn`) |

Gates hooks automatiques (inventaire SSoT : `@.sdd/docs/gates-map.md`) : coût
par run (`preflight_cost_cap`, `SDD_DISABLE_COST_CAP=1`), combo stack hors SLA
(`preflight_stack_combo`, `SDD_ALLOW_UNTESTED_COMBO=1`), acceptance post-qa
(`validate_acceptance_gate`, `SDD_ALLOW_ACCEPTANCE_BYPASS=1`), ordre des phases
(`enforce_phase_order`, `SDD_ALLOW_PHASE_SKIP=1`), parallélisme
(`enforce_max_parallel`, `SDD_ALLOW_PARALLEL_EXCESS=1`), coût par US
(`BuildLoopMaxCostUsd`). Tous les bypass sont audit-loggués.

Mode From-Plan (plans consommés par dev-*) : `@.sdd/rules/build-and-loop.md §7`.
`PlanCacheStrict` : retiré v7.0.0 (clé tolérée, no-op).

---

## STEP 2 — Récap final

Sur `action: done` :

```bash
# GATE DE LIVRAISON (SSoT @.sdd/docs/delivery-gates.md) — build + tests +
# coverage + spec_compliance + readiness PROUVÉS (delivery_evidence)
python .sdd/python/sdd_scripts/delivery_gate.py authorize --feat-number {n} --workflow sdd-full --run-id "$RUN_ID" --json
# clôture EXPLICITE du run — commande fournie par le planner (champ end_run) ;
# run_close.py re-soumet completed|partial au gate (refus → failed, exit 2)
python .sdd/python/sdd_scripts/run_close.py --run-id "$RUN_ID" --status {completed|partial|failed}
python .sdd/python/sdd_scripts/sdd_full_planner.py recap --run-id "$RUN_ID"
```

**Aucun `[DONE]` (ni `[DONE/WARN]`) si `delivery_gate.py authorize` sort ≠ 0
ou si `run_close.py` sort 2** : émettre
`🔴 [DONE/FAIL] FEAT {n} — [DELIVERY_GATE_BLOCKED] … (pct%)` et clore `failed`.
Les statuts `run_phases` (pass/warn, `buildVerified`, `executed`) ne valent
jamais preuve ; `--force`, WARN, `--no-validate` et `--resume` ne lèvent jamais
ce gate (un run `--no-validate` ne peut pas livrer : readiness requise).

Émettre **un seul bloc final** à partir du recap (phases + verdicts, tokens,
fichiers de code matérialisés, avertissements `[FALSE_POSITIVE_COMPLETION]` /
`[DRIFT_SUSPECTED]`, présence du log `--force`), suivi de `Run trace : {RUN_ID}`.
Sur `action: stop` non `resumable` : exécuter le `end_run` rendu
(`run_close.py … --status failed`). Si `resumable` (gate en attente, readiness
non assumée), le run reste ouvert pour `--resume`. `run_close.py` est
idempotent : aucun run ne reste `running` après un `done` ou un `stop` terminal.

---

## Règles de cette commande

- **Délégation pure** : aucun agent invoqué directement — chaque spawn passe par
  la commande rendue par le planner (two-stage auditors : procédure documentée).
- **Une action à la fois**, enregistrée avant la suivante ; l'état vit en base,
  jamais dans la mémoire du LLM (`--state-inline` est déprécié et ignoré).
- **Idempotente** : relancer `/sdd-full {n}` (ou `--resume`) reprend après la
  dernière phase terminée.
- **Mode strict** : aucun WARN ignoré silencieusement ; tout bypass est tracé.

---

## Chat Output Protocol

> **OBLIGATOIRE (décision Tech Lead 2026-11-13, `output-protocol.md §2.4`)** :
> pendant toute la commande, l'orchestrateur affiche à **chaque** point
> d'avancement le **tableau d'avancement** (Étape | %, mêmes lignes du début à
> la fin, seuls les `%` et l'état changent), **et rien d'autre autour** : ni
> lignes `[AGENT] … (X%)`, ni log d'action, ni récap intermédiaire. Seules
> exceptions sous le tableau : erreur bloquante (§7.2) ou action requise de
> l'utilisateur. Le tableau prime sur la granularité « 1 ligne par update »
> ci-dessous.

> Cette commande applique strictement `@.sdd/rules/output-protocol.md`
> — SSoT non dupliqué ici (format 1L §2, interdits §5, erreurs §7,
> verdict `[DONE]` §9, bypass `SDD_CHAT_VERBOSE=1` §10).

**Spécifique `/sdd-full`** : pipeline complet, plage `0-100%` (champ
`progress_pct` de chaque action), tous les labels §3 (`[ANALYSIS]` → `[DONE]`).
1 update par action exécutée ; chaque sub-agent émet ses propres updates dans
sa plage. Un `stop` s'affiche au format §7.2 avec sa classe (`error`).
