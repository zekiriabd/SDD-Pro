# Gates de livraison — SSoT (2026-11-07)

> Règle : **aucune livraison sans preuve d'exécution réelle**. Une preuve
> n'existe que dans `console.db delivery_evidence` (signée HMAC, clé locale hors
> dépôt), écrite **uniquement** par `verify_build.py`, `verify_tests.py`,
> `delivery_gate.py record-spec` / `record-readiness`. La décision vient
> **uniquement** de `sdd_lib.delivery_gate.authorize_delivery` ; les statuts et
> payloads `run_phases` (`pass`, `warn`, `buildVerified`, `executed`,
> `coverage`…) ne peuvent jamais autoriser — au plus refuser plus tôt.
> Câblage : `sdd_lib/delivery_wiring.py` (fail-closed : module absent / erreur →
> refus). Tests : `tests/test_delivery_gate_wiring.py`.

## 1. Matrice workflow → validations → points de sortie

| Workflow | Preuves requises (`WORKFLOW_REQUIREMENTS`) | Points de sortie gardés (code) | Points de sortie gardés (prompt) |
|---|---|---|---|
| `/sdd-full` | readiness, build, tests, coverage, spec_compliance | `sdd_full_planner.compute_next_action` (étapes `verify-build` après dev_run, `verify-tests` après qa, `record-spec` après spec post-dev, `record-readiness` + gate final avant spec-book/`done`) ; `run_close.py` ; `sdd_state.py end-run` ; `sdd_state.py set-phase sdd_review` (clôture finale) | `sdd-full.md` STEP 2 (`authorize --workflow sdd-full` avant `[DONE]`) |
| `/sdd-poc` | build (**pas de QA imposée**) | run **ouvert par le code** : `feat_to_pseudo_us.py --open-run` (commande `/sdd-poc`, même ouverture que `sdd_state.py new-run`) ; clôture `run_close.py` / `sdd_state.py end-run` (`completed` sans preuve build → `failed`, exit 2) | `sdd-poc.md` STEP 4 (`--open-run`) + STEP 7.5 (`verify_build.py` puis `run_close.py --status completed`) |
| `/dev-run` | readiness, build | `dev_run_args.py --end pass\|warn` (refus → `dev_run=fail`, run `/dev-run` clos `failed`, exit 2) ; clôtures de run | `dev-run.md` STEP 7 |
| `/qa-generate` | build, tests, coverage | clôtures de run `/qa-generate` | `qa-generate.md` STEP 7 |
| `/sdd-review` | build, tests, spec_compliance | verdict final de `sdd_review.py` (GREEN/YELLOW → `authorize_delivery(workflow="sdd-review")` via `delivery_wiring` ; refus ou module absent → verdict final `red`, exit 1, `quality_verdict` garde l'audit, persisté RED) ; clôtures de run `/sdd-review` | `sdd-review.md` STEP 2.9 (`record-spec` avant le verdict) + STEP 3.9 |
| `/sdd-deploy` | build | clôtures de run `/sdd-deploy` (commande à venir) | — |

Règle prompt commune : **aucun `[DONE]` / `[DONE/WARN]` si
`delivery_gate.py authorize` sort ≠ 0** (ou `run_close.py` / `--end` sort 2) →
`🔴 [DONE/FAIL] … [DELIVERY_GATE_BLOCKED]`.

Clôture de run : `completed` / `success` / `partial` d'un run dont `command`
est un workflow ci-dessus → `authorize_delivery` ; refus → `failed` + verdict
`RED` + `error_message [DELIVERY_GATE_BLOCKED]`. `failed` / `cancelled` et runs
hors livraison (`hook`, reverse, `/us-generate`…) : inchangés.

Hook `enforce_phase_order` : statut amont = condition nécessaire, jamais
suffisante. `qa` post-dev, `spec-compliance-reviewer` et reviewers Stage B
exigent la preuve build ; Stage B exige aussi la preuve tests si `qa` est
déclarée pass/warn ; un payload `buildVerified:false` / `executed:false` refuse
même en `warn`. `[DELIVERY_EVIDENCE_MISSING]`, sans bypass. API gate (`qa`
pendant `dev_run=running`) et `/sdd-poc` inchangés.

`qa` TEST-FIRST (TDD RED, lève l'interblocage avec `enforce_tdd` strict) :
prompt portant `test-first` / `--test-first` / `TDD RED`, dev_run ∉
{running, pass, warn} et readiness ∈ {pass, warn} → ALLOW
(`[PHASE_ORDER_TEST_FIRST]`, WARN). N'enregistre aucune phase, ne vaut aucune
preuve ; dès dev_run running/pass/warn le marqueur est ignoré (règle nominale
+ preuve build). Détail : docstring du hook.

Gates manuelles `gate_decide.py` (`afterUS` / `afterReadiness` / `afterPlan` /
`afterCode`) : **revues humaines pré-livraison, sans effet de livraison**.
Une décision `validated` / `skipped` (y compris `afterCode`) ne fait que
débloquer l'étape suivante du planner ; elle ne clôt aucun run, n'écrit aucune
preuve et ne consulte pas `authorize_delivery`. Après `afterCode`, le planner
exige toujours `verify-build` (puis `verify-tests`, `record-spec`,
`record-readiness`) : une validation humaine **s'ajoute** aux preuves, ne les
remplace jamais. Aucun code ajouté côté `gate_decide.py` (rien à garder) ;
non-régression : `test_gate_decide_after_code_*` dans
`tests/test_delivery_gate_wiring.py`.

Relance / `--resume` : une preuve absente ou **périmée** (empreinte des
sources ou des FEAT/US changée) replanifie `verify-*` ; un statut `pass`
antérieur (phase ou étape) n'est jamais réutilisé.

## 2. Inventaire des contournements

**(a) touchent une validation obligatoire de livraison** — peuvent laisser
avancer le pipeline, ne mènent jamais à une livraison (le gate de sortie n'a
aucun paramètre ni variable de contournement ; les variables `SDD_ALLOW_*` /
`SDD_BYPASS_*` présentes sont ignorées et journalisées `delivery-gate.jsonl`) :

| Contournement | Effet conservé | Effet sur la livraison |
|---|---|---|
| `--force` (`/sdd-full`, `/dev-run`) | assume readiness WARN/NO-GO, plan-review | aucun ; sortie bloquée journalisée `.audit/force-bypass.log` (« SANS EFFET sur le gate ») |
| `--no-validate` (`/sdd-full`) | saute `/feat-validate` | **ne peut pas livrer** (readiness requise) → STOP `[DELIVERY_GATE_BLOCKED]` |
| `--no-plan-on-warn`, `SDD_ALLOW_FORCE` (anti-cumul) | sautent plan-review / autorisent le cumul | aucun |
| `--resume` / relance | reprend après les phases passées | verify-* replanifiés si preuve absente/périmée |
| WARN (readiness, QA, review, API gate), `QaFailOnSddFull=false`, `ReviewFailOnSddFull=false` | RED → `warn`, pipeline continue | aucun : preuves tests/spec toujours exigées |
| `QAMode: off\|manual`, `ReviewMode: off\|manual` | phase `skip` | `/sdd-full` : `verify-tests` toujours planifié (bloque sans tests réels) |
| `SpecComplianceRequiredForFeatValidate=false`, `AuditorBatchMode: legacy-parallel`, `SDD_BYPASS_TWO_STAGE`, `--legacy-auditor-parallel`, `/sdd-review --no-spec-gate` | ordre/parallélisme auditeurs | `record-spec` toujours requis (`/sdd-full`, `/sdd-review`) |
| `SDD_ALLOW_ACCEPTANCE_BYPASS` | acceptance gate post-qa | preuves build/tests toujours requises |
| `SDD_ALLOW_PHASE_SKIP` | ordre des phases | ne lève pas `[DELIVERY_EVIDENCE_MISSING]` ni la sortie |
| `--unsequenced`, `SDD_DISABLE_TDD` | séquencement / test-first | aucun |

**(b) sans lien avec la livraison** — inchangés, audit-loggués :
`SDD_ALLOW_UNTESTED_COMBO`, `SDD_ALLOW_UNTESTED_HARNESS`, `SDD_ALLOW_MULTISTACK`,
`SDD_DISABLE_COST_CAP`, `SDD_ALLOW_UNKNOWN_PRICING`, `SDD_ALLOW_PARALLEL_EXCESS`,
`SDD_ALLOW_LARGE_FEAT`, `SDD_ALLOW_REVERSE_LOW`, `SDD_ALLOW_SECRET_*`,
`SDD_ALLOW_ENV_BYPASS`, `SDD_DISABLE_{GLOB_SCOPE,PRE_WRITE_LINT,AUTO_ROUTER,SESSION_START,*_WARN}`,
`--manual-gates` / `--no-manual-gates` (validation humaine en plus, jamais en moins).
