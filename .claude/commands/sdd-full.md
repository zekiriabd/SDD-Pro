# /sdd-full — Pipeline complet de A à Z pour 1 FEAT

<!-- @llm-only-flags-file : tous les flags CLI de cette commande slash sont interprétés par Claude. -->

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

## ⚡ Orchestrateur Python (pattern recommandé)

> **Mode thin-wrapper** : piloter le pipeline via `sdd_full_planner.py` (33 tests
> verts) au lieu d'interpréter les 19 STEPs ci-dessous. Substance décisionnelle
> en code testable, spawns LLM en Markdown. Les STEPs restent valides comme
> spec step-by-step + backward-compat.

```bash
# 1. Build plan (0 token, ~50ms)
python .claude/python/sdd_scripts/sdd_full_planner.py plan \
  --feat-number {n} --json > workspace/output/.sys/.state/plan-{n}.json

# 2. Init state
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py new-run \
  --feat-number {n} --command "/sdd-full" --tags "$TAGS")

# 3. Boucle next-action jusqu'à action ∈ {done, stop}
while true; do
  STATE='{"completed_phases":[...],"last_status":"...","last_verdict":"...","flags":{...}}'
  DECISION=$(python .claude/python/sdd_scripts/sdd_full_planner.py next-action \
    --plan-json workspace/output/.sys/.state/plan-{n}.json --state-inline "$STATE")
  ACTION=$(echo "$DECISION" | jq -r '.action')
  case "$ACTION" in
    skill)  SKILL=$(echo "$DECISION" | jq -r '.skill') ;;  # tool call Claude
    script) SCRIPT=$(echo "$DECISION" | jq -r '.script'); ARGS=$(echo "$DECISION" | jq -r '.args[]'); python "$SCRIPT" $ARGS ;;
    skip)   ;;  # marker completed et continue
    stop|done) break ;;
  esac
done

# 4. Recap (lit state.json + console.db)
python .claude/python/sdd_scripts/sdd_full_planner.py recap --run-id "$RUN_ID"
```

| Subcmd | Rôle | I/O |
|---|---|---|
| `plan` | Construit le plan exécution | `--feat-number N` → JSON plan |
| `next-action` | Décide phase suivante (action/skill/script/reason) | `--plan-json` + `--state-inline` → JSON |
| `recap` | Récap final tokens + verdicts | `--run-id R` → Markdown ou JSON |

**Garanties** : `dev-backend/qa-api-gate/dev-frontend` coalescées en `/dev-run` ;
`feat-validate WARN` sans `--force` → `stop` auto ; `fail` propage `stop` ;
auto-skip `arch` si bootstrap stable et `us-generate` si US présentes.

> Cible v7.2 : STEPs Markdown re-générés depuis le planner Python pour
> cohérence permanente (roadmap v7.2 — cf. `docs/roadmap-v7-v8.md`,
> ADR à émettre lors du sprint d'implémentation).

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

> **Comprendre la gate anti-cumul (CRIT-14 closure 2026-06-07)** : un seul
> flag de bypass est toléré (`BYPASS_COUNT = 1` → WARN audit-loggué). Le
> cumul de **2 ou plus** parmi `{--force, --no-plan-on-warn, --no-validate}`
> nécessite l'env var `SDD_ALLOW_FORCE=1` (truthy = `1`/`true`/`yes`/`on`,
> case-insensitive). Cas légitime : reprise d'un run NO-GO en mode dégradé
> Tech Lead, après revue manuelle de la FEAT. Usage CLI :
>
> ```bash
> SDD_ALLOW_FORCE=1 claude /sdd-full 1 --force --no-validate
> ```
>
> L'usage du bypass est **tracé dans `workspace/output/.sys/.audit/force-bypass.log`**
> (commande, flags, timestamp, raison libre via `SDD_FORCE_REASON=...`).
> Pour audit DSI : ce log est la preuve de la décision humaine, jamais
> bypass silencieux.

```bash
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

## STEP 1.ter — Initialiser l'état du run (observability)

Émet `state.json` + event log JSONL dans `workspace/output/.sys/.state/`
pour observabilité et reprise. `$TAGS` = flags actifs csv (`force`, `plan`,
`no-plan-on-warn`, `no-validate`, `rebuild-arch`, `manual-gates`, `resume`).

```bash
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py new-run \
  --feat-number {n} --command "/sdd-full" --tags "$TAGS")
```

**Si `--resume`** → reprendre dernier run + skip STEPs déjà passés :

```bash
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py get-run --feat-number {n} --latest)
RESUME_TARGET=$(python .claude/python/sdd_scripts/sdd_state.py resume-target \
  --run-id "$RUN_ID" 2>/dev/null || echo "STEP_2")
echo "RESUME: skipping to $RESUME_TARGET"
```

**Convention routing** : chaque STEP majeur débute par une garde Python
(`should-skip-step --target $RT --current STEP_X` → exit 0=SKIP, 1=RUN).
Labels canoniques dans `_PIPELINE_PHASES_ORDER` de `sdd_state.py`. Hors
pipeline → fallback RUN par sécurité. Échec primitive (script absent, FS
RO) → WARNING 1 ligne + continue (observabilité best-effort).

### Pattern set-phase aux frontières

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase {phase} --status {pass|warn|fail|skip} \
  --payload-json '{"key":value}'
```

| Phase | Statuts | Payload schema |
|---|---|---|
| `us-generate` | pass\|fail | `{"usCount":N}` |
| `FEAT-validate` | pass\|warn\|fail | `{"errors":E,"warnings":W,"decision":"GO|WARN|NO-GO"}` |
| `dev-plan` | pass\|warn\|fail | `{"plansCount":N}` |
| `arch` | pass\|fail | `{"shortCircuited":bool}` |
| `dev-run` | pass\|warn\|fail | `{"backOk":Tb,"frontOk":Tf,"failed":F}` |
| `qa-generate` | pass\|warn\|fail\|skip | `{"decision":"GREEN|YELLOW|RED","coverage":pct,"tests":N}` |
| `doc-refresh` | pass\|warn | `{"htmlPages":N}` |

Payload optionnel mais recommandé (metrics dashboard). STEPs aval réfèrent
"**State tracking** : set-phase phase=X".

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

- Console (`workspace/console/`) : bandeau orange "Validation manuelle"
  avec boutons Valider / Refuser / Continuer.
- Tant que le bandeau n'est pas câblé sur `/api/gate-decide`, le validateur
  édite `status.json` (set `gates.{n}.{phase}.decision = "validated"`) OU
  invoque le CLI :
  ```bash
  python .claude/python/sdd_scripts/gate_decide.py set \
         --feat-num {n} --phase afterUS --decision validated
  ```
  Puis `/sdd-full {n} --resume`.

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

**RÈGLE LOAD-BEARING** : point d'arrêt bloquant. NE JAMAIS invoquer
`/dev-run` sans plans techniques + décision humaine (ou auto explicite).
Sauter ce STEP = générer code sans review = anti-pattern que SDD existe
pour empêcher.

**Déclencheurs** (cf. STEP 3.5) :
- A. WARN/NO-GO + `--force` (sans `--no-plan-on-warn`)
- B. GO + (`--plan` ou `PlanReviewDefault: true`)

**Vérification pré-`/dev-run`** : Glob `workspace/output/plans/{n}-*-*.{back,front}.md`.
Si déclencheur actif ET aucun plan → STOP + ERROR :
```
ERROR: /sdd-full {n} — plan-review gate sauté
CAUSE: [PLAN_REVIEW_GATE_SKIPPED] PlanReviewDefault=true mais aucun plan
FIX: invoquer /dev-plan {n} puis review (ok|stop|retry)
```

### 3.6.a — Idempotence

Si ≥ 1 plan existe ET mtime > mtime readiness.md → plans considérés
"déjà reviewés", direct à 3.6.c. Sinon → 3.6.b.

### 3.6.b — `/dev-plan {n}`

Invoque dev-* en mode `:plan` → écrit `workspace/output/plans/{n}-{m}-{Name}.{back|front}.md`.
Succès → 3.6.c. ERROR → STOP.

### 3.6.c — Checkpoint humain

- **Si `plan ∈ $ManualGates`** → procédure GATE (STEP 1.gate-proc) avec
  `phase=afterPlan`. Console bandeau = interface validation, checkpoint
  chat bypassé.

- **Sinon** (legacy) → prompt chat :

  ```
  🟡 /sdd-full {n} — readiness {GO|WARN|NO-GO}, plans à relire

  Rapport readiness : workspace/output/.sys/.validation/{n}-readiness.md
  Plans : workspace/output/plans/{n}-*-*.{back,front}.md

  Que voulez-vous faire ?
    ok    → /dev-run (plans consommés mode From-Plan)
    stop  → arrêter (plans conservés, reprendre via /dev-run {n})
    retry → relancer /dev-plan {n}
  ```

  Checkpoint **bloquant**, attendre réponse.

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

Filet pour invocations chaînées qui sauteraient le CLI parsing de STEP 1.bis.
Pure-fonction (pas de side-effect), court-circuit si sentinelle déjà set.

```bash
if [ "$SDD_FORCE_CUMUL_OK" = "1" ]; then
  echo "[VALIDATE/SKIP] force-cumul déjà validé STEP 1.bis. (~32%)"
else
  python .claude/python/sdd_scripts/preflight_force_cumul.py \
    $( [ "$FORCE" = "true" ]           && echo --force ) \
    $( [ "$NO_PLAN_ON_WARN" = "true" ] && echo --no-plan-on-warn ) \
    $( [ "$NO_VALIDATE" = "true" ]     && echo --no-validate ) \
    || exit 1  # STOP + ERROR [FORCE_CUMUL_REJECTED]
fi
```

---

## STEP 3.7 — Audit log `--force`

Si `--force` utilisé (quel que soit verdict readiness) : append 1 ligne
dans `workspace/output/.sys/.audit/force-bypass.log` (append-only, audit
Tech Lead/code review/post-mortem). Skip silent sinon.

```bash
mkdir -p workspace/output/.sys/.audit
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) /sdd-full {n}-{FeatName} --force readiness={WARN|NO-GO} {W}W {E}E --no-plan-on-warn={true|false}" >> workspace/output/.sys/.audit/force-bypass.log
```

Récap STEP 5 mentionne la présence du log.

---

## STEP 4 — Phase exécution (`/dev-run {n}`)

Exécute `/dev-run {n}` (validation `## Active Database` / `## Active Auth
Specs` → short-circuit arch ou bootstrap+DB → dev-backend + dev-frontend
gated parallèles bornés). Propage `RUN_ID` via env pour continuité
audit-trail (reprise post-crash sans run_id orphelin).

```bash
export SDD_RUN_ID="$RUN_ID"
if [ "$REBUILD_ARCH" = "true" ]; then /dev-run {n} --rebuild-arch ; else /dev-run {n} ; fi
```

| Sortie | Action |
|---|---|
| Succès | → STEP 4.bis |
| ERROR clés stack.md manquantes / ERROR arch | propager + STOP |
| Échecs partiels phase 4 | listés par `/dev-run`, → STEP 4.bis |

**State tracking** : set-phase phase=dev-run (schema STEP 1.ter). Si arch
a tourné, ajouter set-phase phase=arch en amont.

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

## STEP 4.7 — Spec-compliance gate post-dev

Ré-invoque `/feat-validate {n}` post-`/dev-run` pour activer la spec-compliance
gate (le STEP 3.5 pré-dev la skippe car `HAS_CODE=null`).

```bash
SPEC_REQ=$(python -c "
import sys; sys.path.insert(0, '.claude/python')
from sdd_lib.layered_config import read_layered_config
print(str(read_layered_config().get('SpecComplianceRequiredForFeatValidate', 'true')).lower())
" 2>/dev/null || echo 'true')

if [ "$SPEC_REQ" = "false" ]; then
  echo "[VALIDATE/SKIP] spec-compliance bypass Project Config. (~89%)"
else
  /feat-validate {n} --json --post-dev > /tmp/feat-validate-postdev-{RUN_ID}.json 2>/dev/null
  POSTDEV_EXIT=$?
fi
```

| Exit | Verdict | Comportement |
|---|---|---|
| `0` | GREEN (ou bypass) | → STEP 4.8 |
| `1` | RED (≥ 1 AC critical non vérifiée) | **STOP** + ERROR `[SPEC_COMPLIANCE_RED]` |
| `2` | spec-compliance.json absent | **STOP** + ERROR `[SPEC_COMPLIANCE_REQUIRED]` |

Idempotent (lit `spec-compliance.json` frais si `/dev-run §6.4` vient de
tourner, ~50ms). Bypass : `SpecComplianceRequiredForFeatValidate: false`.

**State tracking** : set-phase phase=feat-validate-postdev.

---

## STEP 4.8 — Audit qualité consolidé `/sdd-review`

Lire `ReviewMode` (`## Project Config`, défaut `full`).

| `ReviewMode` | Action |
|---|---|
| `off` / `manual` | skip |
| `read-only` | `/sdd-review {n} --skip-scans` (lecture DB seule) |
| `full` (défaut) | `/sdd-review {n}` complet (re-scan + agrégation) |

Pipeline `/sdd-review` : re-run `quality_scan.py` → lecture DB (qa_quality
+ qa_code_review + qa_security + qa_a11y + qa_performance + qa_spec_compliance)
→ triage par owner via `triage_issues.py` → verdict 🟢/🟡/🔴 vs `ReviewFailOn`
→ persist `validation_reports(report_type='review')` + emit
`workspace/output/qa/feat-{n}/review.md`. `arch-reviewer` est désormais owned
par `/dev-run §6.4` (fallback ici si invocation standalone).

**Bloquant** : `ReviewFailOnSddFull: true` (défaut v7.0.0) + RED → STOP
avant STEP 5. Bypass : `ReviewFailOnSddFull: false`.

**State tracking** : set-phase phase=sdd-review. Coût : ~30s + ~10-18 KB
tokens si `ArchReviewMode: full`.

---

## STEP 4.9 — Drift detection inline rules

Auto-invoke `validate_inline_rules.py` (déterministe, 0 token) pour détecter
le drift inline ↔ `.claude/rules/`. Best-effort non-bloquant : drift =
`[DRIFT_SUSPECTED]` WARN dans récap.

```bash
python .claude/python/sdd_scripts/validate_inline_rules.py --json \
  > /tmp/sdd-inline-rules-{RUN_ID}.json 2>/dev/null
# Exit : 0=clean, 1=drift (WARN), 2=infra error (skip silent)
```

Propager le compteur de drifts au récap STEP 5
(`Drift inline rules : {N} suspectés → voir /tmp/...`). Auto-invoke
élimine la dette silencieuse (agent inline divergent = résultats
incohérents cross-run).

---

## STEP 5 — Récap consolidé

Finaliser le run avant le récap :

```bash
FINAL_STATUS={success|partial|failed}   # success=tout 🟢, partial=≥1 WARN/SKIP, failed=ERROR
python .claude/python/sdd_scripts/sdd_state.py end-run --run-id $RUN_ID --status $FINAL_STATUS
```

Ajouter `Run trace : $RUN_ID` en pied (utile `--resume` ou requête
`console.db events WHERE run_id = $RUN_ID`).

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

- **Délégation pure** : aucun agent invoqué directement
- **Idempotente** : relancer régénère tout (From-Plan réutilise si mtime cohérent)
- **Checkpoint unique** au STEP 3.6 (conditionnel)
- **Erreur isolée par phase** : échec planification ⊥ échec exécution
- **Mode strict** : aucun WARN ignoré silencieusement
- **Bypass `--force` traçable** : loggé dans récap STEP 5 avec mention « --force assumé »

### Référence détaillée
- Plan-from-Plan mode : `@.claude/CLAUDE.md §11.10`
- BREAKING CHANGES : `@.claude/docs/CHANGELOG.md`
- Workflow ASCII : `@.claude/docs/workflow.md`

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
