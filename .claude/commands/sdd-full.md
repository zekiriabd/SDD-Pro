# /sdd-full — Pipeline complet de A à Z pour 1 FEAT

Enchaîne **toutes les phases** du pipeline SDD pour la FEAT `{n}` :

```
PHASE 2    — US generation         (agent po, via /us-generate)
PHASE 2.5  — HTML mockups          (humain — workspace/input/ui/, pas d'agent)
PHASE 2.6  — Readiness gate        (PowerShell déterministe v6, via /feat-validate)
PHASE 2.7  — Plan-then-review gate (mode :plan, via /dev-plan, conditionnel)
PHASE 3    — ARCH + DB             (agent arch, via /dev-run)
PHASE 4    — CODE back+front       (agents dev-*, via /dev-run, parallèle)
PHASE 5    — QA + Quality          (agent qa, via /qa-generate, conditionnel)
```

**Délégation pure** : `/sdd-full` n'invoque AUCUN agent directement —
elle chaîne `/us-generate` → `/feat-validate` → (`/dev-plan`) →
`/dev-run` → (`/qa-generate`).

**Checkpoint humain** : un seul, au STEP 3.6 (review des plans), et
uniquement si readiness ≠ GO ou si `--plan` activé.

---

## ⚡ Orchestrateur Python (Sprint 2.5 — v7.0.0-alpha 2026-06-07)

> **Mode thin-wrapper recommandé** (depuis v7.0.0-alpha Sprint 2.5) :
> au lieu de suivre les 19 STEPs ci-dessous comme pseudo-code Markdown,
> Claude peut piloter le pipeline via 3 appels Python déterministes.
> Substance décisionnelle = code testable (28 tests verts), spawns LLM
> restent en Markdown.

### Pattern d'usage simplifié

```bash
# 1. Construire le plan complet (0 token LLM, ~50 ms)
python .claude/python/sdd_scripts/sdd_full_planner.py plan \
  --feat-number {n} --json > workspace/output/.sys/.state/plan-{n}.json

# 2. Init state + run_id
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py new-run \
  --feat-number {n} --command "/sdd-full" --tags "$TAGS")

# 3. Boucle d'orchestration jusqu'à action == "done" ou "stop"
while true; do
  # State courant (à enrichir au fil des phases)
  STATE='{"completed_phases":[...],"last_status":"...","last_verdict":"...","flags":{...}}'

  DECISION=$(python .claude/python/sdd_scripts/sdd_full_planner.py next-action \
    --plan-json workspace/output/.sys/.state/plan-{n}.json \
    --state-inline "$STATE")
  ACTION=$(echo "$DECISION" | jq -r '.action')

  case "$ACTION" in
    skill)
      # Claude exécute la Skill (us-generate, dev-run, qa-generate, etc.)
      SKILL=$(echo "$DECISION" | jq -r '.skill')
      # …Skill invocation (Claude tool call)…
      ;;
    script)
      # Script déterministe (sdd-review, etc.)
      SCRIPT=$(echo "$DECISION" | jq -r '.script')
      ARGS=$(echo "$DECISION" | jq -r '.args[]')
      python "$SCRIPT" $ARGS
      ;;
    skip)
      # Phase skippée par le plan — marquer completed et continuer
      ;;
    stop|done)
      break
      ;;
  esac

  # Update state : ajouter la phase à completed_phases, capturer verdict
done

# 4. Recap final (déterministe — lit state.json + console.db)
python .claude/python/sdd_scripts/sdd_full_planner.py recap --run-id "$RUN_ID"
```

### Subcommands `sdd_full_planner.py`

| Subcmd | Rôle | Input | Output |
|---|---|---|---|
| `plan` | Construit le plan exécution (phases à pending/skip/blocked) | `--feat-number N` | JSON plan |
| `next-action` | Décide quoi faire ensuite selon state + plan | `--plan-json` + `--state-inline` | JSON decision (`action`/`skill`/`script`/`reason`) |
| `recap` | Récap final (read state + tokens + verdicts) | `--run-id R` | Markdown rendu (ou `--json`) |

**Garanties** :
- Action `dev-backend`/`qa-api-gate`/`dev-frontend` → coalescée en un seul `/dev-run`
  (le orchestrateur dev-run interne gère la séquence back→gate→front)
- Action `feat-validate` WARN sans `--force` → automatiquement → action `stop`
- Phase `fail` propage `stop` immédiat (sauf si flag override explicite)
- Plan auto-skip arch quand bootstrap stable (`detect_arch_shortcircuit`)
- Plan auto-skip us-generate quand US déjà présentes

> **Statut** (audit CTO 2026-06-07) : le module `sdd_full_planner.py` est
> **livré et testé** (33 tests pytest verts, P0 false-positive completion
> guard câblé). Il est désormais le **pattern recommandé** pour piloter
> `/sdd-full` — la substance décisionnelle est testable, les spawns LLM
> restent en Markdown.
>
> Le pseudo-bash des STEPs 1-5 ci-dessous reste **valide** comme spec
> step-by-step (référence humaine + backward-compat). À horizon v7.2.0,
> les STEPs Markdown seront re-générés depuis le planner Python pour
> garantir cohérence permanente (ADR `governance-major-orchestrator-python`,
> cf. `docs/adrs/ADR-20260606T222017-344c-governance-major-sprint-...`).

---

## Utilisation

```
/sdd-full {n}                          # bloque sur WARN ou NO-GO (mode strict)
/sdd-full {n} --plan                   # plan-review opt-in même sur GO (recommandé ≥ 2 US)
/sdd-full {n} --force                  # assume WARN/NO-GO (passe par plan-review)
/sdd-full {n} --force --no-plan-on-warn  # escape hatch agressif (skip plan-review)
/sdd-full {n} --no-validate            # legacy : bypass complet readiness
/sdd-full {n} --rebuild-arch           # force l'invocation arch même si bootstrap stable
/sdd-full {n} --manual-gates           # active les 4 gates de validation manuelle (LOT 3)
/sdd-full {n} --manual-gates=us,plan   # active uniquement un sous-ensemble
/sdd-full {n} --no-manual-gates        # désactive (override Project Config)
/sdd-full {n} --resume                 # reprise après gate validé depuis la console
```

> **Comportement par défaut sur FEATs ≥ 2 (depuis 2026-05-10)** :
> `/sdd-full N` (avec `N ≥ 2`) ne ré-invoque PAS l'agent arch quand
> les artefacts de bootstrap sont stables (CLAUDE.md projet présents,
> `schema.json` présent si DB, `stack.md` non modifié). Le pipeline
> exécute uniquement PO → readiness → dev → QA. Cf.
> `commands/dev-run.md §STEP 4.bis`. Pour forcer un re-bootstrap
> (changement DB schéma, ajout lib stack, modif Project Config) :
> passer `--rebuild-arch`.

**Activation projet** : `PlanReviewDefault: true` dans `## Project Config`
de `workspace/input/stack/stack.md` rend `--plan` actif par défaut.

**Gates automatiques (hooks Claude Code)** — fire silencieusement sans
configuration, bypass uniquement par env var (audit-loggué) :

| Gate hook | Script | Bloquant | Bypass env var |
|---|---|:---:|---|
| Cost cap par run | `sdd_hooks/preflight_cost_cap.py` | ✅ ($USD ≥ `MaxCostPerRun`, default $50) | `SDD_DISABLE_COST_CAP=1` |
| Stack combo non listé | `sdd_hooks/preflight_stack_combo.py` | ✅ (combo absent des 13 SLA) | `SDD_ALLOW_UNTESTED_COMBO=1` |
| Acceptance Gate post-qa | `sdd_hooks/validate_acceptance_gate.py` + `sdd_scripts/validate_acceptance.py` | ✅ en mode `strict` (test/lint/build/coverage/smoke/E2E) | `SDD_ALLOW_ACCEPTANCE_BYPASS=1` |
| Cost cap par US build_loop | dev-* internal | ✅ ($USD ≥ `BuildLoopMaxCostUsd`, default $15) | `BuildLoopMaxCostUsd: 0` config |
| Force-cumul anti-bypass | `sdd_hooks/preflight_force_cumul.py` | ✅ (≥ 2 bypass flags cumulés) | `SDD_ALLOW_FORCE=1` |

Cf. `error-classification.md §1.2` pour les classes `[COST_CAP_EXCEEDED]`,
`[BUILD_LOOP_COST_EXCEEDED]`, `[ACCEPTANCE_GATE_FAILED]`,
`[FORCE_CUMUL_REJECTED]`.

**Chemin From-Plan Strict (RETIRÉ v7.0.0)** : les variants
`dev-backend-strict` et `dev-frontend-strict` (Sonnet 4.6, v6.2-v6.10) ont
été supprimés (`ADR-20260519T120000-governance-major-auditors-trim`). La
clé `PlanCacheStrict: true` reste **tolérée en lecture** dans
`## Project Config` mais devient **no-op runtime**. Le plan v2 schema
(`## Inline Digest`) est **préservé** pour review humaine — il n'oriente
plus vers un agent alternatif. Tous les plans (v1 et v2) sont matérialisés
par les agents canoniques Opus 4.7. Invoquer `/sdd-full {n} --plan` si
revue humaine du plan désirée avant matérialisation.

**Gates manuels (LOT 3, depuis 2026-05-10)** : 4 points d'arrêt
optionnels où l'humain valide via la console
([workspace/console/](workspace/console/)) avant que le pipeline n'enchaîne :

| Gate | Insertion | Phase status.json | Validateur attendu |
|---|---|---|---|
| `afterUS`        | après `/us-generate`        | `gates.{n}.afterUS`        | PO Humain |
| `afterReadiness` | après `/feat-validate`      | `gates.{n}.afterReadiness` | PO Humain |
| `afterPlan`      | après `/dev-plan` (mode :plan) | `gates.{n}.afterPlan`   | Tech Lead / Architecte |
| `afterCode`      | après `/dev-run`            | `gates.{n}.afterCode`      | Équipe (back/front) |

Activation par `## Project Config` (`ManualGates: true`) ou flag CLI
(`--manual-gates`). Voir STEP 1.gates et la procédure GATE générique en
STEP 1.gate-proc.

> **v7.0.0-alpha (audit P0-workflow 2026-06-05)** — la numérotation
> historique avait deux STEP `1.bis` distincts (anti-cumul + résolution
> des gates manuels) et `1.ter`/`1.tiers`/`1.quart` dans le désordre.
> Renumérotation : `1.bis` reste l'anti-cumul (hard-gate), `1.ter` =
> init state.json, `1.quart` = phase planner placeholder, `1.gates` =
> résolution `$ManualGates`, `1.gate-proc` = définition procédure GATE.

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent → demander `Quel est le numéro de la FEAT à exécuter ? (ex. : 1)`.
Si non numérique → ERROR `[INVALID_ARG]`.

---

## STEP 1.bis — HARD-GATE anti-cumul bypass (v7.0.0-alpha, audit CRIT-10)

**Bloquant AVANT tout coût LLM.** Pré-CRIT-10, cette gate vivait à
STEP 3.6.quart — après que STEP 3.5 / STEP 3.6 ait déjà déclenché la
génération de plans techniques (jusqu'à ~30-60 KB tokens Opus 4.7 par
plan × N US). Si `BYPASS_COUNT >= 2` sans `SDD_ALLOW_FORCE=1`, ces
plans étaient générés pour rien. Désormais le check primaire est ici,
juste après le parsing des flags, **avant toute autre phase**.

Exécuter le script déterministe (0 token LLM, ~50 ms) :

```bash
python .claude/python/sdd_scripts/preflight_force_cumul.py \
  $( [ "$FORCE" = "true" ]            && echo --force ) \
  $( [ "$NO_PLAN_ON_WARN" = "true" ]  && echo --no-plan-on-warn ) \
  $( [ "$NO_VALIDATE" = "true" ]      && echo --no-validate )
```

| Exit | Action |
|:-:|---|
| 0 | continuer STEP 1.ter + **`export SDD_FORCE_CUMUL_OK=1`** (sentinelle court-circuit M9 closure) |
| 1 | **STOP** + ERROR `[FORCE_CUMUL_REJECTED]` déjà émis par le script sur stderr |

```bash
# Audit M9 closure 2026-06-07 — export sentinelle pour court-circuit STEP 3.6.quart
if [ "$CUMUL_EXIT_STEP_1_BIS" = "0" ]; then
  export SDD_FORCE_CUMUL_OK=1
fi
```

Le script reproduit fidèlement la logique documentée historiquement à
STEP 3.6.quart (mêmes seuils, même env var, même format ERROR). STEP
3.6.quart est conservé en mode **defense-in-depth** (cf. ci-dessous)
pour les invocations qui contourneraient ce STEP 1.bis (chaînage
inline par un assistant Claude qui spawne directement les sous-commandes
sans repasser par la CLI).

---

## STEP 1.ter — Initialiser l'état du run (Phase 0 observability, v6.1)

Cette commande émet désormais un **state.json par run** et un **event log
JSONL** dans `workspace/output/.sys/.state/`, pour observabilité et reprise.
Adoption progressive : un seul call de chaque primitive aux frontières de
phase, sans réécriture de la commande.

Construire `$TAGS` (séparé par virgules) à partir des flags actifs :
`force`, `plan`, `no-plan-on-warn`, `no-validate`, `rebuild-arch`,
`manual-gates`, `resume`.

Exécuter via Bash :

```bash
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py new-run \
  --feat-number {n} --command "/sdd-full" --tags "$TAGS")
```

Si `--resume` actif → reprendre le dernier run + détecter la phase d'arrêt
pour skipper les STEPs déjà passés (audit 2026-06-06 D5 — vrai routing
post-resume, pas juste récupération d'ID).

```bash
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py get-run --feat-number {n} --latest)

# Inspecter les phases du run précédent pour déterminer le point de reprise.
# Le show-run retourne un JSON avec phases.{us_generate,arch,dev_run,qa,sdd_review}.status
# parmi {pending,running,pass,warn,fail,skip}. La prochaine phase à exécuter
# est la première qui n'est PAS dans {pass, warn, skip}.
RESUME_STATE=$(python .claude/python/sdd_scripts/sdd_state.py show-run --run-id "$RUN_ID" 2>/dev/null)

# Calcul du STEP de reprise (déterministe, pas LLM). Convention :
#   us_generate=pass   -> skip STEP 2 (us-generate)
#   us_generate+arch=pass -> skip jusqu'au STEP 4.5 (dev-run)
#   us_generate+arch+dev_run=pass -> skip jusqu'au STEP 5 (qa)
#   us_generate+arch+dev_run+qa=pass -> skip jusqu'au STEP 5.5 (sdd-review)
# Calculé par sdd_state.py resume-target (audit D5 fix) :
RESUME_TARGET=$(python .claude/python/sdd_scripts/sdd_state.py resume-target \
  --run-id "$RUN_ID" 2>/dev/null || echo "STEP_2")
echo "RESUME: skipping to $RESUME_TARGET"
```

**Convention de routing post-resume** : chaque STEP majeur (2, 2.6, 2.7,
3.5, 4, 5, 5.5) débute par une garde Python (audit CTO 2026-06-07 — le
bash `[ "$RT" > "STEP_X" ]` antérieur était (a) une redirection vers
fichier nommé `STEP_X`, (b) lex-compare faux sur `STEP_2.6` vs `STEP_10`).

```bash
# Exit 0 = SKIP, Exit 1 = RUN. Gate déterministe sur l'ordre canonique
# défini par _PIPELINE_PHASES_ORDER dans sdd_state.py.
if python .claude/python/sdd_scripts/sdd_state.py should-skip-step \
     --target "$RESUME_TARGET" --current "STEP_X" ; then
    echo "[RESUME] skipping STEP X (already done in run $RUN_ID)"
    continue   # passer au STEP suivant
fi
```

Ce garde rend `--resume` vraiment opérationnel (sinon le pipeline relance
tout, idempotent mais coûteux LLM). Cf. `sdd_state.py resume-target` qui
calcule la cible, `should-skip-step` qui gate. Si `--target` ou `--current`
sont hors pipeline canonique, la gate retombe en RUN (exit 1) par sécurité.

Stocker `$RUN_ID` pour les appels `set-phase` ultérieurs (STEPs 3, 3.5,
4, 4.5, 4.7). Si la primitive échoue (script absent, FS lecture seule),
émettre un WARNING 1 ligne et continuer (non bloquant — l'observabilité
est best-effort).

---

### Pattern à propager aux STEPs suivants

À la fin de chaque phase majeure, ajouter un one-liner :

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase {phase} --status {pass|warn|fail|skip} \
  --payload-json '{"key":value}'
```

**Phases et schémas payload attendus** (cibles des references "State tracking" dans les STEPs aval) :

| Phase | Status possibles | Payload-json schema |
|---|---|---|
| `us-generate` | pass\|fail | `{"usCount":N}` |
| `FEAT-validate` | pass\|warn\|fail | `{"errors":E,"warnings":W,"decision":"GO|WARN|NO-GO"}` |
| `dev-plan` | pass\|warn\|fail | `{"plansCount":N}` |
| `arch` | pass\|fail | `{"shortCircuited":bool}` |
| `dev-run` | pass\|warn\|fail | `{"backOk":Tb,"frontOk":Tf,"failed":F}` |
| `qa-generate` | pass\|warn\|fail\|skip | `{"decision":"GREEN|YELLOW|RED","coverage":pct,"tests":N}` |
| `doc-refresh` | pass\|warn | `{"htmlPages":N}` |

Payload optionnel mais recommandé (metrics utiles pour le dashboard).
Les STEPs aval référencent ce tableau via "**State tracking** : set-phase phase=X".

---

## STEP 1.gates — Résoudre `$ManualGates` (LOT 3)

Calculer la liste des gates actifs `$ManualGates` (Set ⊆ {us, readiness, plan, code}) :

1. Si `--no-manual-gates` présent → `$ManualGates = ∅` (override total).
2. Sinon, si `--manual-gates` présent (ou `--manual-gates=...`) :
   - Sans valeur → `$ManualGates = {us, readiness, plan, code}` (les 4)
   - Avec valeur (`=us,plan`) → parser la liste séparée par virgules
3. Sinon, lire `ManualGates` dans `## Project Config` de `workspace/input/stack/stack.md` :
   - `ManualGates: true` → 4 gates
   - `ManualGates: false` (ou absent) → ∅
   - `ManualGates: us,plan,code` → liste explicite

**Anti-derive** : tout autre token que `us|readiness|plan|code` → ERROR
`[INVALID_ARG]` (CAUSE / FIX).

---

## STEP 1.gate-proc — Procédure GATE générique (LOT 3)

Cette procédure est invoquée par chaque STEP de gate (3.bis, 3.5.bis,
3.6.bis, 4.bis). Elle est paramétrée par `(n, phase, label-from, label-to)`.

### Algorithme

```
1. Lire la décision actuelle :
   $decision = $(python .claude/python/sdd_scripts/gate_decide.py read \
                        --feat-num {n} --phase {phase})

2. Si $decision == "validated" OR "skipped" :
   → gate déjà tranché, skip silencieusement (idempotence). Ne rien afficher.

3. Si $decision == "pending" :
   - Si --resume présent : ré-évaluer après court délai (le validateur peut
     avoir cliqué dans la console). Boucler max 1 fois ; sinon → STOP.
   - Sinon → STOP propre, format chat :
     ```
     🟡 /sdd-full {n} — gate {phase} en attente
     Ouvrir http://127.0.0.1:5173 pour valider, puis : /sdd-full {n} --resume
     ```

4. Si $decision == "none" (premier passage) :
   AskUserQuestion 2 options :
     - "Valider manuellement (ouvrir la console, STOP)"
     - "Continuer sans valider"

   Si "Valider" :
     - python .claude/python/sdd_scripts/gate_decide.py pose-pending \
              --feat-num {n} --phase {phase}
     - STOP propre (même format que cas 3)

   Si "Continuer" :
     - python .claude/python/sdd_scripts/gate_decide.py set \
              --feat-num {n} --phase {phase} --decision skipped \
              --answered-by "$SDD_USER_EMAIL"
     - continuer le pipeline (1 ligne :
       `→ gate {phase} : continuer sans valider (skipped)`)
```

### Comportement console pendant un STOP "pending"

- La console (`workspace/console/`) montre un bandeau orange "Validation
  manuelle" avec 3 boutons : Valider / Refuser / Continuer (LOT 2)
- Le clic Valider POST `/api/validate` côté US/plans, mais **pas le
  gate lui-même**. Pour résoudre le gate, l'utilisateur doit cliquer le
  bouton spécifique du bandeau qui appelle `gate_decide.py set
  --decision validated` (LOT 3 future itération via API).

> **Note transitoire LOT 3** : tant que le bouton bandeau "Valider et
> continuer" n'est pas câblé sur `/api/gate-decide`, le validateur peut :
> - éditer `workspace/console/status.json` à la main (set `gates.{n}.{phase}.decision = "validated"`)
> - OU appeler le script en CLI :
>   ```
>   python .claude/python/sdd_scripts/gate_decide.py set \
>          --feat-num {n} --phase afterUS --decision validated
>   ```
> Puis `/sdd-full {n} --resume`.

---

## STEP 2 — Vérifier la FEAT

Glob `workspace/input/feats/{n}-*.md`.
- 0 fichier → ERROR `[FEAT_NOT_FOUND]` (créer via `/feat-generate`)
- > 1 fichier → ERROR `[FEAT_AMBIGUOUS]` (renommer)
- 1 fichier → OK, stocker `{FeatName}`, émettre :
  ```
  FEAT {n}-{FeatName} — pipeline complet démarré (phases 2 → 5)
  ```

---

## STEP 3 — Phase planification (`/us-generate {n}`)

Exécuter intégralement `/us-generate {n}`.

| Sortie | Action |
|---|---|
| Succès | continuer STEP 3.bis |
| ERROR | propager + STOP |

**State tracking** : set-phase phase=us-generate (schema payload cf. STEP 1.ter).

---

## STEP 3.bis — Gate manuel `afterUS` (LOT 3, conditionnel)

**Déclencheur** : `us ∈ $ManualGates` (cf. STEP 1.gates).

Invoquer la procédure GATE (STEP 1.gate-proc) avec :
- `phase = afterUS`
- `label-from = "PO"`
- `label-to = "Validation readiness"`

Si gate non actif → skip directement vers STEP 3.5.

---

## STEP 3.5 — Implementation Readiness Gate

Si `--no-validate` → forcer `$readiness_decision = GO`, skip STEP 3.5
et STEP 3.6, aller à STEP 4.

Sinon, exécuter `/feat-validate {n}`. Stocker `$readiness_decision ∈
{GO, WARN, NO-GO}`.

**Si `readiness ∈ $ManualGates`** (LOT 3), invoquer la procédure GATE
(STEP 1.gate-proc) avec `phase = afterReadiness`, `label-from = "Readiness"`,
`label-to = "Plans techniques"` **avant** d'appliquer le tableau de
décision ci-dessous. Si le gate impose un STOP, l'utilisateur reprend
via `/sdd-full {n} --resume` après validation.

### Tableau de décision

| Décision | `--plan` ou `PlanReviewDefault` | `--force` | `--no-plan-on-warn` | Action |
|---|---|---|---|---|
| GO    | absent  | -      | -    | → STEP 4 directement |
| GO    | présent | -      | -    | → STEP 3.6 (plan-review opt-in) |
| WARN  | -       | absent | -    | **STOP** (mode strict v3.1.2) |
| WARN  | -       | présent | absent  | → STEP 3.6 (plan-review obligatoire) |
| WARN  | -       | présent | présent | → STEP 4 directement (escape hatch) |
| NO-GO | -       | absent | -    | **STOP** |
| NO-GO | -       | présent | -   | → STEP 3.6 (plan-review assumé) |
| ERROR `/feat-validate` | -      | -      | -    | propager + STOP |

### Format STOP sur WARN/NO-GO

```
{🟡|🔴} /sdd-full {n} — bloqué par /feat-validate ({WARN non assumé | NO-GO})

Rapport : workspace/output/.sys/.validation/{n}-readiness.md ({W} warnings, {E} errors)

Pour débloquer (au choix) :
  - corriger les {warnings|erreurs} listé(e)s dans le rapport §{2|3}
    puis relancer /sdd-full {n}
  - assumer le risque : /sdd-full {n} --force
    → continue avec STEP 3.6 plan-then-review
  - escape hatch (déconseillé) : /sdd-full {n} --force --no-plan-on-warn
    → continue sans plan-review
```

**State tracking** : set-phase phase=FEAT-validate (schema payload cf. STEP 1.ter).

---

## STEP 3.6 — Plan-then-review gate

**RÈGLE LOAD-BEARING (depuis 2026-05-12)** : ce STEP est un point
d'arrêt **bloquant** dès que l'un des déclencheurs ci-dessous est
actif. L'orchestrateur (commande `/sdd-full` OU assistant Claude
qui chaîne les commandes inline) NE DOIT JAMAIS invoquer `/dev-run`
sans avoir produit les plans techniques `workspace/output/plans/{n}-*-*.{back,front}.md`
au préalable et obtenu la décision humaine (ou la décision auto en
mode autonome explicite). Sauter ce STEP = générer du code sans
review = exactement l'anti-pattern que le framework SDD existe pour
empêcher.

**Déclenchement** (cf. tableau STEP 3.5) :
- A. WARN/NO-GO + `--force` (sans `--no-plan-on-warn`)
- B. GO + (`--plan` ou `PlanReviewDefault: true`)

**Vérification pré-`/dev-run`** : avant de lancer STEP 4 (`/dev-run`),
toujours `Glob workspace/output/plans/{n}-*-*.{back,front}.md`. Si
PlanReviewDefault=true ou `--plan` ou `--force` est actif ET aucun
plan n'est trouvé → STOP + ERROR `[PLAN_REVIEW_GATE_SKIPPED]` :
```
ERROR: /sdd-full {n} — plan-review gate sauté
CAUSE: [PLAN_REVIEW_GATE_SKIPPED] PlanReviewDefault=true mais aucun plan dans workspace/output/plans/
FIX: invoquer /dev-plan {n} avant /dev-run {n}, puis review (ok|stop|retry)
```

### 3.6.a — Idempotence

Glob `workspace/output/plans/{n}-*-*.{back,front}.md`.
- ≥ 1 plan existe ET son mtime > mtime de `workspace/output/.sys/.validation/{n}-readiness.md`
  → plans considérés "déjà reviewés", aller directement à 3.6.c
- Sinon → 3.6.b

### 3.6.b — Exécuter `/dev-plan {n}`

`/dev-plan {n}` invoque dev-* en mode `:plan` → écrit
`workspace/output/plans/{n}-{m}-{Name}.{back|front}.md` (sans coder).

| Sortie | Action |
|---|---|
| Succès | → 3.6.c |
| ERROR | propager + STOP |

### 3.6.c — Checkpoint humain (LEGACY ou GATE LOT 3)

**Branchement** :

- **Si `plan ∈ $ManualGates`** (LOT 3) → invoquer la procédure GATE
  (STEP 1.gate-proc) avec `phase = afterPlan`, `label-from = "Plans"`,
  `label-to = "Développement"`. Le bandeau de la console
  ([workspace/console/](workspace/console/)) sert d'interface de
  validation. Le checkpoint chat ci-dessous est **bypassé**.

- **Sinon** (legacy, `plan ∉ $ManualGates`) → afficher le prompt chat
  classique :

  ```
  🟡 /sdd-full {n} — readiness {GO|WARN|NO-GO}, plans à relire

  Rapport readiness : workspace/output/.sys/.validation/{n}-readiness.md ({W} warnings)
  Plans :
    - workspace/output/plans/{n}-1-{Name}.back.md
    - workspace/output/plans/{n}-1-{Name}.front.md
    - ...

  Que voulez-vous faire ?
    ok    → continuer vers /dev-run (plans consommés en mode From-Plan)
    stop  → arrêter (plans + readiness conservés ; reprendre via /dev-run {n})
    retry → relancer /dev-plan {n} (régénère, écrase les éditions humaines)
  ```

  **Attendre la réponse humaine** — checkpoint bloquant.

  | Réponse | Action |
  |---|---|
  | `ok` | → STEP 4 (`/dev-run` détecte les plans, mode From-Plan, cf. CLAUDE.md §11.10) |
  | `stop` | STOP propre. Reprendre via `/dev-run {n}` ou `/sdd-full {n}` (idempotent) |
  | `retry` | relancer 3.6.b puis re-poser la question |
  | autre | ré-afficher le prompt sans avancer |

> **Pas de doublon** : exactement UN des deux mécanismes s'exécute
> selon `$ManualGates`. C'est l'articulation propre exigée au LOT 3.

---

## STEP 3.6.quart — Anti-cumul bypass (defense-in-depth)

> **No-op idempotent prouvé** (audit M9 closure 2026-06-07) : ce STEP 3.6.quart est conservé comme **filet de sécurité** pour les invocations chaînées qui sauteraient le CLI parsing du STEP 1.bis. La preuve d'idempotence repose sur :
>
> 1. **Inputs identiques** : `preflight_force_cumul.py` ne lit que les flags CLI `$FORCE`/`$NO_PLAN_ON_WARN`/`$NO_VALIDATE` + env var `SDD_ALLOW_FORCE` — aucune mutation entre STEP 1.bis (juste après parse args) et STEP 3.6.quart (post-STEP 3.6 plans). Les variables shell ne sont pas mutées par les STEPs intermédiaires.
> 2. **Comportement déterministe** : le script est pure-fonction (no FS read/write, no DB, no network) — même input = même output, exit 0 ou 1.
> 3. **Skip court-circuit** : si la sentinelle `SDD_FORCE_CUMUL_OK=1` est déjà exportée par STEP 1.bis (succès), STEP 3.6.quart court-circuite l'invocation Python (~10ms saved par run).

```bash
# Court-circuit idempotent — STEP 1.bis a déjà validé
if [ "$SDD_FORCE_CUMUL_OK" = "1" ]; then
  echo "[VALIDATE/SKIP] force-cumul defense-in-depth already validated at STEP 1.bis. (~32%)"
else
  python .claude/python/sdd_scripts/preflight_force_cumul.py \
    $( [ "$FORCE" = "true" ]            && echo --force ) \
    $( [ "$NO_PLAN_ON_WARN" = "true" ]  && echo --no-plan-on-warn ) \
    $( [ "$NO_VALIDATE" = "true" ]      && echo --no-validate )
  CUMUL_EXIT=$?
  if [ "$CUMUL_EXIT" -ne 0 ]; then
    exit 1  # STOP + ERROR [FORCE_CUMUL_REJECTED] (cf. STEP 1.bis ERROR format)
  fi
fi
```

Exit 1 → STOP + ERROR `[FORCE_CUMUL_REJECTED]`.

> **À noter** : STEP 1.bis doit `export SDD_FORCE_CUMUL_OK=1` après succès pour activer le court-circuit ci-dessus. Si cette ligne d'export est absente (incident sub-shell mort), STEP 3.6.quart re-invoque le script normalement → comportement legacy préservé.

---

## STEP 3.7 — Audit log (depuis v5.0, si `--force` utilisé)

**Déclencheur** : si `--force` a été passé sur cette invocation
(quel que soit le verdict readiness — WARN ou NO-GO).

**Action** : append 1 ligne dans `workspace/output/.sys/.audit/force-bypass.log`
(crée le fichier si absent) :

```bash
mkdir -p workspace/output/.sys/.audit
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) /sdd-full {n}-{FeatName} --force readiness={WARN|NO-GO} {W} warnings {E} errors --no-plan-on-warn={true|false}" >> workspace/output/.sys/.audit/force-bypass.log
```

**Pourquoi** : le bypass `--force` est légitime mais doit être
auditable (pour Tech Lead, code review, post-mortem). Une ligne par
usage, append-only. Préservé sur toute purge manuelle de `workspace/output/`.

Le récap STEP 5 mentionne la présence du log :
```
Bypass force assumé : oui (cf. workspace/output/.sys/.audit/force-bypass.log ligne {N})
```

Skip silencieusement si pas de `--force`.

---

## STEP 4 — Phase exécution (`/dev-run {n}`)

Exécuter intégralement `/dev-run {n}` (validation blocs `## Active
Database` / `## Active Auth Specs` de stack.md → short-circuit arch
ou bootstrap+DB → dev-backend + dev-frontend gated/parallèles bornés).

**Propagation des flags + run_id (audit M7 closure 2026-06-07)** :
```bash
# Toujours propager le RUN_ID actuel via env var SDD_RUN_ID pour que
# /dev-run puisse (a) reprendre proprement après crash en STEP 4 sans
# re-créer un nouveau run_id orphelin, (b) écrire ses set-phase sous le
# même run_id que les phases STEP 2/3 amont (continuité audit-trail).
export SDD_RUN_ID="$RUN_ID"

# Propagation flag --rebuild-arch si présent
if [ "$REBUILD_ARCH" = "true" ]; then
  /dev-run {n} --rebuild-arch
else
  /dev-run {n}
fi
```
Sinon, invocation simple `/dev-run {n}` — qui décidera lui-même via
son STEP 4.bis si arch est requis.

> **v7.0.1 (audit M7)** : avant ce fix, `/sdd-full` n'exportait pas `SDD_RUN_ID` → si STEP 4 crashait mid-flight (kill -9, OOM, panne réseau), un redémarrage `/dev-run` standalone créait un **nouveau** run_id orphelin et toutes les set-phase ultérieures étaient découplées du run /sdd-full parent. Résultat : audit-trail fragmenté, resume cassé. Le `sdd_state.py new-run` détecte désormais `SDD_RUN_ID` env var et **reprend l'existant** au lieu de créer un nouveau (idempotent).

| Sortie | Action |
|---|---|
| Succès | → STEP 4.bis |
| ERROR clés stack.md manquantes | propager + STOP (planification reste intacte) |
| ERROR arch | propager + STOP |
| Échecs partiels phase 4 | listés par `/dev-run`, → STEP 4.bis |

**State tracking** : set-phase phase=dev-run (schema payload cf. STEP 1.ter). Si arch a tourné, ajouter aussi set-phase phase=arch en amont.

---

## STEP 4.bis — Gate manuel `afterCode` (LOT 3, conditionnel)

**Déclencheur** : `code ∈ $ManualGates` (cf. STEP 1.gates).

Invoquer la procédure GATE (STEP 1.gate-proc) avec :
- `phase = afterCode`
- `label-from = "Dev"`
- `label-to = "QA"`

Permet à l'équipe de revoir le code généré (`workspace/output/src/`)
avant le scan QA. Si gate non actif → skip directement vers STEP 4.5.

---

## STEP 4.45 — Refresh INDEX ADRs (déplacé depuis 4.7 — audit P0-workflow 2026-06-05)

> **v7.0.0-alpha (audit P0-workflow 2026-06-05)** — historiquement ce
> STEP était numéroté 4.7 (après QA gate). Conséquence : si STEP 4.5
> aboutissait à un STOP `[QA_FAIL_BLOCKING_SDD_FULL]`, l'INDEX ADRs
> n'était **jamais** rafraîchi — donc les ADRs créés en phase 4 (par
> `arch` / `dev-*`) restaient orphelins dans `INDEX.md`. Drift
> documentaire à chaque pipeline RED. Déplacé en 4.45 (avant la QA
> gate) pour exécution inconditionnelle. Ne dépend d'aucun résultat
> QA — c'est un simple scan FS + write INDEX.md.

Exécuter **systématiquement** (avant tout STOP/gate aval) :

```bash
python .claude/python/sdd_scripts/index_adrs.py
```

Régénère **un seul fichier** : `workspace/output/.sys/.context/adrs/INDEX.md`
(table-des-matières chronologique des ADRs créés par arch + dev-*).

Coût : **0 token**, latence < 100 ms. Non bloquant : sur exit ≠ 0,
émettre WARNING et continuer vers STEP 4.5. L'INDEX ADRs est un
artefact de navigation, pas une dépendance fonctionnelle du pipeline.

**State tracking** : set-phase phase=doc-refresh (schema payload cf. STEP 1.ter).

---

## STEP 4.5 — QA + Quality (auto-invoke conditionnel)

Lire `QAMode` dans `## Project Config` (default `manual`).

| `QAMode` | Action |
|---|---|
| `off` | skip silencieusement |
| `manual` | skip (l'utilisateur lance `/qa-generate` manuellement) |
| `full`, `tests-only`, `tests+coverage`, `quality-only` | exécuter `/qa-generate {n}` |

### Gate : bloquant ou non ? (v7.0.0 audit §6.9)

Lire `QaFailOnSddFull` dans `## Project Config` (défaut `true` v7.0.0,
flippé depuis `false` historique pour fixer l'asymétrie).

| Verdict `/qa-generate` | `QaFailOnSddFull: true` (défaut) | `QaFailOnSddFull: false` (legacy) |
|---|---|---|
| `GREEN` | continuer STEP 4.8 | continuer STEP 4.8 |
| `YELLOW` | continuer STEP 4.8 + WARN récap | continuer STEP 4.8 + WARN récap |
| `RED` | **STOP** + ERROR `[QA_FAIL_BLOCKING_SDD_FULL]` (exit 1) | continuer STEP 4.8 + WARN récap (bypass audit-log) |

**Format ERROR** :
```
ERROR: /sdd-full {n} — QA verdict RED bloquant
CAUSE: [QA_FAIL_BLOCKING_SDD_FULL] {classes /qa-generate, e.g. QA_TEST_FAILED ou QA_COVERAGE_GAP}
FIX: corriger les tests/coverage via /dev-run {n} (idempotent), puis re-run /sdd-full {n}
     OU baisser CoverageMin / QaFailOnSddFull dans Project Config (décision tracée)
```

GREEN/YELLOW/RED sont également propagés au récap STEP 5.

**State tracking** : set-phase phase=qa-generate (schema payload cf. STEP 1.ter). Status `skip` si `QAMode ∈ {off, manual}`.

---

## STEP 4.7 — Spec-compliance gate post-dev (v7.0.1, audit C3 closure 2026-06-07)

> **v7.0.1 (audit C3 closure)** : ce STEP avait été planifié v7.2.0 sous ADR `governance-sdd-full-spec-gate-post-dev` mais avancé à v7.0.1 suite à l'audit CTO. **Avant ce fix**, `feat-validate` invoqué en STEP 3.5 (pré-dev) skippait silencieusement la spec-compliance gate (`HAS_CODE=null`) et **jamais réinvoqué** post-dev → la valeur ajoutée de spec-compliance était silencieusement contournée dans le flow `/sdd-full` nominal.

**Action** : ré-invoquer `/feat-validate {n}` **post-`/dev-run`** pour activer la spec-compliance gate maintenant que le code est matérialisé.

```bash
# Lire SpecComplianceRequiredForFeatValidate (défaut true v7.0.0)
SPEC_REQ=$(python -c "
import sys; sys.path.insert(0, '.claude/python')
from sdd_lib.layered_config import read_layered_config
cfg = read_layered_config()
print(str(cfg.get('SpecComplianceRequiredForFeatValidate', 'true')).lower())
" 2>/dev/null || echo 'true')

if [ "$SPEC_REQ" = "false" ]; then
  echo "[VALIDATE/SKIP] spec-compliance gate bypassed via Project Config. (~89%)"
else
  # Re-invoquer /feat-validate — cette fois HAS_CODE != null → gate active
  /feat-validate {n} --json --post-dev > /tmp/feat-validate-postdev-{RUN_ID}.json 2>/dev/null
  POSTDEV_EXIT=$?
fi
```

**Mapping exit code → comportement** (symétrique STEP 4.5 QA gate) :

| Exit | Verdict | Comportement |
|---|---|---|
| `0` | spec-compliance GREEN (ou skipped via bypass) | continuer STEP 4.8 |
| `1` | spec-compliance RED (≥ 1 AC critical non vérifiée) | **STOP** + ERROR `[SPEC_COMPLIANCE_RED]` (cf. error-classification.md §1.13) |
| `2` | spec-compliance.json absent | **STOP** + ERROR `[SPEC_COMPLIANCE_REQUIRED]` (`/dev-run §6.4` aurait dû spawner spec-compliance-reviewer — incident infra) |

**Bypass explicite** : `SpecComplianceRequiredForFeatValidate: false` dans `## Project Config` → continuer même sur findings, verdict inclus au récap.

**Idempotence** : si `spec-compliance.json` déjà frais (<1h, ce qui est le cas car `/dev-run §6.4` vient juste de tourner), `/feat-validate` lit le fichier existant — pas de re-spawn d'agent. Coût marginal : ~50ms (lecture JSON + parsing déterministe).

**State tracking** : set-phase phase=feat-validate-postdev. Status `skip` si bypass.

---

## STEP 4.8 — Audit qualité consolidé `/sdd-review` (depuis v6.11.0)

Lire `ReviewMode` dans `## Project Config` (default `full` depuis v6.11.0
— passe à `manual` pour bypass).

| `ReviewMode` | Action |
|---|---|
| `off` | skip silencieusement |
| `manual` | skip (l'utilisateur lance `/sdd-review {n}` manuellement) |
| `read-only` | `/sdd-review {n} --skip-scans` (lecture DB seule, pas de re-scan) |
| `full` (défaut) | `/sdd-review {n}` complet (re-scan quality + agrégation) |

> **v7.0.0-alpha (audit CRIT-4)** : `arch-reviewer` n'est **plus**
> spawné par `/sdd-review §3.0` quand l'invocation arrive depuis
> `/sdd-full §4.8` — il a déjà tourné en parallèle dans
> `/dev-run §6.4` (cf. `commands/dev-run.md §6.4.1`). `/sdd-review`
> reste en charge du **fallback standalone** (invocation directe
> `/sdd-review {n}` sans `/dev-run` préalable). Économie ~10-15K
> tokens + ~20s sur un pipeline `/sdd-full` complet.

Le pipeline `/sdd-review` :
1. Re-run [`quality_scan.py`](.claude/python/sdd_scripts/quality_scan.py) (refresh `qa_quality`)
2. ~~Spawn `arch-reviewer` agent~~ — désormais owned by `/dev-run §6.4`
   (fallback uniquement si invocation standalone, cf. `commands/sdd-review.md §3.0`)
3. Read DB (qa_quality + qa_code_review + qa_security + qa_a11y + qa_performance + qa_spec_compliance)
4. Triage par owner (backend / frontend / shared / unknown) via [`triage_issues.py`](.claude/python/sdd_scripts/triage_issues.py)
5. Compute verdict 🟢/🟡/🔴 contre `ReviewFailOn`
6. Persist `validation_reports(report_type='review')` + emit `workspace/output/qa/feat-{n}/review.md`

**Comportement bloquant** (v7.0.0 — codex audit P0 #9) :
- `ReviewFailOnSddFull: true` dans Project Config (**défaut `true` depuis v7.0.0**,
  flippé depuis `false` en v6.11.0) + verdict RED → STOP `/sdd-full` avant
  STEP 5, exit code propagation.
- Bypass explicite : `ReviewFailOnSddFull: false` dans `## Project Config`
  de `stack.md` → continue vers STEP 5 même sur RED, le verdict est inclus
  dans le récap.

**State tracking** : set-phase phase=sdd-review (schema payload cf. STEP 1.ter).
Status `skip` si `ReviewMode ∈ {off, manual}`.

Coût marginal : ~30 s (re-scan déterministe) + ~10-18 KB tokens si
`ArchReviewMode: full` (Sonnet 4.6).

---

## STEP 4.9 — Drift detection inline rules (v7.0.0 audit hardening, 2026-05-20)

**Auto-invoke** `validate_inline_rules.py` (déterministe, 0 token) pour
détecter le drift entre la substance inlinée dans les prompts agents et
les fichiers source de `.claude/rules/`. Tourne **systématiquement** en
fin de pipeline (avant STEP 5 récap) — best-effort non-bloquant : un
drift détecté émet `[DRIFT_SUSPECTED]` WARN dans le récap, ne fait pas
échouer le run.

```bash
python .claude/python/sdd_scripts/validate_inline_rules.py --json \
  > /tmp/sdd-inline-rules-{RUN_ID}.json 2>/dev/null
# Exit code informationnel :
#   0 = aucun drift
#   1 = drift détecté (WARN dans récap, non bloquant)
#   2 = erreur infra (script absent / illisible — silently skip)
```

Lire le JSON et propager le compteur de drifts dans le récap STEP 5
(`Drift inline rules : {N} suspectés → voir /tmp/...`).

**Pourquoi ici** : avant v7.0.0, ce check était manuel (`/sdd-status` ou
release check). Le rendre auto-invoké élimine la dette silencieuse — un
agent dont l'inline diverge de la source MD donne des résultats
incohérents cross-run.

---

## STEP 5 — Récap consolidé

**State tracking (v6.1)** : avant d'émettre le récap, finaliser le run :

```bash
FINAL_STATUS={success|partial|failed}   # success si tout 🟢, partial si ≥1 WARN/SKIP, failed si ERROR
python .claude/python/sdd_scripts/sdd_state.py end-run \
  --run-id $RUN_ID --status $FINAL_STATUS
```

Le récap textuel ci-dessous peut ajouter une ligne `Run trace : $RUN_ID`
en pied (utile pour `--resume` futur ou pour requêter
`workspace/output/db/console.db` table `events` à des fins de
diagnostic — v6.10 : `SELECT * FROM events WHERE run_id = $RUN_ID`).

Émettre **un seul bloc final** :

```
✅ /sdd-full {n}-{FeatName} — pipeline complet terminé

PLANIFICATION (phases 2-2.7) :
  US               : {U} fichiers
  Mockups HTML     : {H} fichiers
  Readiness gate   : {🟢 GO | 🟡 WARN ({W}, --force assumé) | 🔴 NO-GO (--force assumé)}
  Plan-then-review : {skipped | reviewed-opt-in ({P} plans) | reviewed-strict ({P} plans) | bypassed (--no-plan-on-warn)}

EXÉCUTION (phases 3-4) :
  Bootstrap + DB   : {init|skipped} ({N_tables tables} | DB skipped)
  Backend          : {Tb_ok}/{U} ({Tb_skip} skipped, {F_back} échec(s))
  Frontend         : {Tf_ok}/{U} ({Tf_skip} skipped, {F_front} échec(s))

QA (phase 5) :
  {Si off/manual : "skipped ({raison})"}
  Mode             : {mode}
  Tests            : {qa_passed}/{qa_total}
  Coverage         : {qa_pct}% (seuil {CoverageMin}%) → {pass|gap}
  Quality          : {qa_errors} errors / {qa_warnings} warnings
  Décision         : {🟢 GREEN | 🟡 YELLOW | 🔴 RED}

Audit qualité consolidé /sdd-review (phase 4.8) :
  {Si off/manual : "skipped ({raison})"}
  Sources agrégées : {S} (quality, code-review, security, a11y, perf, spec, arch)
  Findings total   : {N} ({T} ≥ {ReviewFailOn})
  Triage owner     : backend={B} · frontend={F} · shared={Sh} · unknown={U}
  Top class        : {top_class_1} ({n1}), {top_class_2} ({n2}), …
  Verdict          : {🟢 GREEN | 🟡 YELLOW | 🔴 RED}
  Rapport          : workspace/output/qa/feat-{n}/review.md

Échecs (phase 4) — si présents :
  - dev-{backend|frontend} {n}-{m}-{Name} : {raison condensée}

Prochaine étape :
  - inspecter le code dans workspace/output/src/
  - relancer /dev-run {n} pour réessayer les échecs (idempotent)
  - /sdd-status {n} pour confirmer l'état complet
```

Si succès complet sans accroc :
```
✅ /sdd-full {n}-{FeatName} — {U} US, {H} mockups HTML, code dans workspace/output/src/
```

---

## Règles de cette commande

- **Délégation pure** : aucun agent invoqué directement.
- **Idempotente** : relancer régénère tout (mode From-Plan réutilise les
  plans si mtime cohérent).
- **Checkpoint unique** au STEP 3.6 (conditionnel).
- **Erreur isolée par phase** : échec planification ⊥ échec exécution.
- **Mode strict (v3.1.2)** : aucun WARN ignoré silencieusement.
- **Bypass `--force` traçable (v5.0)** : tout usage de `--force` est
  loggé en gros dans le récap STEP 5 (`Readiness gate` ligne) avec
  mention « --force assumé ».

### Référence détaillée
- Plan-from-Plan mode : `@.claude/CLAUDE.md §11.10`
- BREAKING CHANGES history : `@.claude/docs/CHANGELOG.md`
- Workflow flow ASCII : `@.claude/docs/workflow.md`

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[ANALYSIS]`, `[PO]`, `[VALIDATE]`,
`[PLAN]`, `[ARCH]`, `[CONSTITUTION]`, `[DEV-BACKEND]`, `[DEV-FRONTEND]`,
`[QA]`, `[CODE-REVIEW]`, `[SPEC-REVIEW]`, `[ARCH-REVIEW]`, `[ADV-REVIEW]`,
`[SECURITY]`, `[DONE]` (pipeline complet — cf. §3)
**Plage de progression couverte** : `0-100%` (cf. output-protocol.md §4)

**Granularité cible** : 1 update par phase orchestrée (typiquement
12-15 updates pour un pipeline FEAT M). L'orchestrateur émet des
transitions de phase (`[PO] ...` → `[ARCH] ...`) ; chaque sub-agent
émet ses propres updates dans sa plage.

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- listes d'US/fichiers détaillées (compteurs métier OK)
- audit logs (`legacy-parallel.log`, etc.)
- récap "Readiness gate" en mode verbose si pas de `--force`

**Verdict final** : 1 ligne `[DONE]` (🟢 GREEN), `[DONE/WARN]` (🟡)
ou `[DONE/FAIL]` (🔴) avec compteurs métier + pointeur fichier rapport
(cf. §9.1). Pas de "next steps" après le verdict (cf. §9.3).

**Erreurs intermédiaires** : chat 1L avec classe `[CLASS]` + pointeur
fichier rapport (cf. §7.2). Format 3L disque préservé.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
