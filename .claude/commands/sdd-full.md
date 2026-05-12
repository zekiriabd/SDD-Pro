# /sdd-full — Pipeline complet de A à Z pour 1 SPEC

Enchaîne **toutes les phases** du pipeline SDD pour la SPEC `{n}` :

```
PHASE 2    — US generation         (agent po, via /us-generate)
PHASE 2.5  — HTML mockups          (humain — workspace/input/ui/, pas d'agent)
PHASE 2.6  — Readiness gate        (PowerShell déterministe v6, via /spec-validate)
PHASE 2.7  — Plan-then-review gate (mode :plan, via /dev-plan, conditionnel)
PHASE 3    — ARCH + DB             (agent arch, via /dev-run)
PHASE 4    — CODE back+front       (agents dev-*, via /dev-run, parallèle)
PHASE 5    — QA + Quality          (agent qa, via /qa-generate, conditionnel)
```

**Délégation pure** : `/sdd-full` n'invoque AUCUN agent directement —
elle chaîne `/us-generate` → `/spec-validate` → (`/dev-plan`) →
`/dev-run` → (`/qa-generate`).

**Checkpoint humain** : un seul, au STEP 3.6 (review des plans), et
uniquement si readiness ≠ GO ou si `--plan` activé.

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

> **Comportement par défaut sur SPECs ≥ 2 (depuis 2026-05-10)** :
> `/sdd-full N` (avec `N ≥ 2`) ne ré-invoque PAS l'agent arch quand
> les artefacts de bootstrap sont stables (CLAUDE.md projet présents,
> `schema.json` présent si DB, `stack.md` non modifié). Le pipeline
> exécute uniquement PO → readiness → dev → QA. Cf.
> `commands/dev-run.md §STEP 4.bis`. Pour forcer un re-bootstrap
> (changement DB schéma, ajout lib stack, modif Project Config) :
> passer `--rebuild-arch`.

**Activation projet** : `PlanReviewDefault: true` dans `## Project Config`
de `workspace/input/stack/stack.md` rend `--plan` actif par défaut.

**Gates manuels (LOT 3, depuis 2026-05-10)** : 4 points d'arrêt
optionnels où l'humain valide via la console
([workspace/console/](workspace/console/)) avant que le pipeline n'enchaîne :

| Gate | Insertion | Phase status.json | Validateur attendu |
|---|---|---|---|
| `afterUS`        | après `/us-generate`        | `gates.{n}.afterUS`        | PO Humain |
| `afterReadiness` | après `/spec-validate`      | `gates.{n}.afterReadiness` | PO Humain |
| `afterPlan`      | après `/dev-plan` (mode :plan) | `gates.{n}.afterPlan`   | Tech Lead / Architecte |
| `afterCode`      | après `/dev-run`            | `gates.{n}.afterCode`      | Équipe (back/front) |

Activation par `## Project Config` (`ManualGates: true`) ou flag CLI
(`--manual-gates`). Voir STEP 1.bis et la procédure GATE générique en
STEP 1.ter.

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent → demander `Quel est le numéro de la SPEC à exécuter ? (ex. : 1)`.
Si non numérique → ERROR `[INVALID_ARG]`.

---

## STEP 1.quart — Initialiser l'état du run (Phase 0 observability, v6.1)

Cette commande émet désormais un **state.json par run** et un **event log
JSONL** dans `workspace/output/.state/`, pour observabilité et reprise.
Adoption progressive : un seul call de chaque primitive aux frontières de
phase, sans réécriture de la commande.

Construire `$TAGS` (séparé par virgules) à partir des flags actifs :
`force`, `plan`, `no-plan-on-warn`, `no-validate`, `rebuild-arch`,
`manual-gates`, `resume`.

Exécuter via Bash :

```bash
if command -v pwsh >/dev/null 2>&1; then PS_BIN=pwsh; else PS_BIN=powershell; fi
RUN_ID=$($PS_BIN -NoProfile -ExecutionPolicy Bypass `
  -File .claude/scripts/sdd-state.ps1 -Action new-run `
  -SpecNumber {n} -Command "/sdd-full" -Tags "$TAGS")
```

Si `--resume` actif → utiliser plutôt :
```bash
RUN_ID=$($PS_BIN -File .claude/scripts/sdd-state.ps1 -Action get-run -SpecNumber {n} -Latest)
```

Stocker `$RUN_ID` pour les appels `set-phase` ultérieurs (STEPs 3, 3.5,
4, 4.5, 4.7). Si la primitive échoue (script absent, FS lecture seule),
émettre un WARNING 1 ligne et continuer (non bloquant — l'observabilité
est best-effort).

### Pattern à propager aux STEPs suivants

À la fin de chaque phase majeure, ajouter un one-liner :

```bash
$PS_BIN -File .claude/scripts/sdd-state.ps1 -Action set-phase `
  -RunId $RUN_ID -Phase {phase} -Status {pass|warn|fail|skip} `
  -PayloadJson '{"key":value}'
```

Où `{phase}` ∈ { `us-generate`, `spec-validate`, `dev-plan`, `dev-run`,
`qa-generate`, `doc-refresh` }. Payload optionnel mais recommandé
(metrics utiles pour le dashboard futur).

---

## STEP 1.bis — Résoudre `$ManualGates` (LOT 3)

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

## STEP 1.ter — Procédure GATE générique (LOT 3)

Cette procédure est invoquée par chaque STEP de gate (3.bis, 3.5.bis,
3.6.bis, 4.bis). Elle est paramétrée par `(n, phase, label-from, label-to)`.

### Algorithme

```
1. Lire la décision actuelle :
   $decision = powershell -EP Bypass -File .claude/scripts/gate-decide.ps1 \
                          -Action read -SpecNum {n} -Phase {phase}

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
     - powershell -EP Bypass -File .claude/scripts/gate-decide.ps1 \
                  -Action pose-pending -SpecNum {n} -Phase {phase}
     - STOP propre (même format que cas 3)

   Si "Continuer" :
     - powershell -EP Bypass -File .claude/scripts/gate-decide.ps1 \
                  -Action set -SpecNum {n} -Phase {phase} -Decision skipped \
                  -AnsweredBy "$env:SDD_USER_EMAIL"
     - continuer le pipeline (1 ligne :
       `→ gate {phase} : continuer sans valider (skipped)`)
```

### Comportement console pendant un STOP "pending"

- La console (`workspace/console/`) montre un bandeau orange "Validation
  manuelle" avec 3 boutons : Valider / Refuser / Continuer (LOT 2)
- Le clic Valider POST `/api/validate` côté US/plans, mais **pas le
  gate lui-même**. Pour résoudre le gate, l'utilisateur doit cliquer le
  bouton spécifique du bandeau qui appelle `gate-decide.ps1 -Action set
  -Decision validated` (LOT 3 future itération via API).

> **Note transitoire LOT 3** : tant que le bouton bandeau "Valider et
> continuer" n'est pas câblé sur `/api/gate-decide`, le validateur peut :
> - éditer `workspace/console/status.json` à la main (set `gates.{n}.{phase}.decision = "validated"`)
> - OU appeler le script en CLI :
>   ```
>   powershell -EP Bypass -File .claude/scripts/gate-decide.ps1 \
>              -Action set -SpecNum {n} -Phase afterUS -Decision validated
>   ```
> Puis `/sdd-full {n} --resume`.

---

## STEP 2 — Vérifier la SPEC

Glob `workspace/input/specs/{n}-*.md`.
- 0 fichier → ERROR `[SPEC_NOT_FOUND]` (créer via `/spec-generate`)
- > 1 fichier → ERROR `[SPEC_AMBIGUOUS]` (renommer)
- 1 fichier → OK, stocker `{SpecName}`, émettre :
  ```
  SPEC {n}-{SpecName} — pipeline complet démarré (phases 2 → 5)
  ```

---

## STEP 3 — Phase planification (`/us-generate {n}`)

Exécuter intégralement `/us-generate {n}`.

| Sortie | Action |
|---|---|
| Succès | continuer STEP 3.bis |
| ERROR | propager + STOP |

**State tracking (v6.1, optionnel)** : après l'exécution, appeler
`set-phase -Phase us-generate -Status pass -PayloadJson '{"usCount":N}'`
(succès) ou `-Status fail` (ERROR). Cf. STEP 1.quart pour le pattern.

---

## STEP 3.bis — Gate manuel `afterUS` (LOT 3, conditionnel)

**Déclencheur** : `us ∈ $ManualGates` (cf. STEP 1.bis).

Invoquer la procédure GATE (STEP 1.ter) avec :
- `phase = afterUS`
- `label-from = "PO"`
- `label-to = "Validation readiness"`

Si gate non actif → skip directement vers STEP 3.5.

---

## STEP 3.5 — Implementation Readiness Gate

Si `--no-validate` → forcer `$readiness_decision = GO`, skip STEP 3.5
et STEP 3.6, aller à STEP 4.

Sinon, exécuter `/spec-validate {n}`. Stocker `$readiness_decision ∈
{GO, WARN, NO-GO}`.

**Si `readiness ∈ $ManualGates`** (LOT 3), invoquer la procédure GATE
(STEP 1.ter) avec `phase = afterReadiness`, `label-from = "Readiness"`,
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
| ERROR `/spec-validate` | -      | -      | -    | propager + STOP |

### Format STOP sur WARN/NO-GO

```
{🟡|🔴} /sdd-full {n} — bloqué par /spec-validate ({WARN non assumé | NO-GO})

Rapport : workspace/output/validation/{n}-readiness.md ({W} warnings, {E} errors)

Pour débloquer (au choix) :
  - corriger les {warnings|erreurs} listé(e)s dans le rapport §{2|3}
    puis relancer /sdd-full {n}
  - assumer le risque : /sdd-full {n} --force
    → continue avec STEP 3.6 plan-then-review
  - escape hatch (déconseillé) : /sdd-full {n} --force --no-plan-on-warn
    → continue sans plan-review
```

**State tracking (v6.1)** : `set-phase -Phase spec-validate -Status {pass|warn|fail} -PayloadJson '{"errors":E,"warnings":W,"decision":"GO|WARN|NO-GO"}'`.

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
- ≥ 1 plan existe ET son mtime > mtime de `workspace/output/validation/{n}-readiness.md`
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
  (STEP 1.ter) avec `phase = afterPlan`, `label-from = "Plans"`,
  `label-to = "Développement"`. Le bandeau de la console
  ([workspace/console/](workspace/console/)) sert d'interface de
  validation. Le checkpoint chat ci-dessous est **bypassé**.

- **Sinon** (legacy, `plan ∉ $ManualGates`) → afficher le prompt chat
  classique :

  ```
  🟡 /sdd-full {n} — readiness {GO|WARN|NO-GO}, plans à relire

  Rapport readiness : workspace/output/validation/{n}-readiness.md ({W} warnings)
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

## STEP 3.7 — Audit log (depuis v5.0, si `--force` utilisé)

**Déclencheur** : si `--force` a été passé sur cette invocation
(quel que soit le verdict readiness — WARN ou NO-GO).

**Action** : append 1 ligne dans `workspace/output/.audit/force-bypass.log`
(crée le fichier si absent) :

```bash
mkdir -p workspace/output/.audit
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) /sdd-full {n}-{SpecName} --force readiness={WARN|NO-GO} {W} warnings {E} errors --no-plan-on-warn={true|false}" >> workspace/output/.audit/force-bypass.log
```

**Pourquoi** : le bypass `--force` est légitime mais doit être
auditable (pour Tech Lead, code review, post-mortem). Une ligne par
usage, append-only. Préservé sur toute purge manuelle de `workspace/output/`.

Le récap STEP 5 mentionne la présence du log :
```
Bypass force assumé : oui (cf. workspace/output/.audit/force-bypass.log ligne {N})
```

Skip silencieusement si pas de `--force`.

---

## STEP 4 — Phase exécution (`/dev-run {n}`)

Exécuter intégralement `/dev-run {n}` (validation env vars →
short-circuit arch ou bootstrap+DB → dev-backend + dev-frontend
gated/parallèles bornés).

**Propagation des flags** : si `/sdd-full` a reçu `--rebuild-arch`,
passer le flag à `/dev-run` :
```
/dev-run {n} --rebuild-arch
```
Sinon, invocation simple `/dev-run {n}` — qui décidera lui-même via
son STEP 4.bis si arch est requis.

| Sortie | Action |
|---|---|
| Succès | → STEP 4.bis |
| ERROR env vars | propager + STOP (planification reste intacte) |
| ERROR arch | propager + STOP |
| Échecs partiels phase 4 | listés par `/dev-run`, → STEP 4.bis |

**State tracking (v6.1)** : `set-phase -Phase dev-run -Status {pass|warn|fail} -PayloadJson '{"backOk":Tb,"frontOk":Tf,"failed":F}'`. Si arch a tourné, ajouter aussi `set-phase -Phase arch -Status pass` avant.

---

## STEP 4.bis — Gate manuel `afterCode` (LOT 3, conditionnel)

**Déclencheur** : `code ∈ $ManualGates` (cf. STEP 1.bis).

Invoquer la procédure GATE (STEP 1.ter) avec :
- `phase = afterCode`
- `label-from = "Dev"`
- `label-to = "QA"`

Permet à l'équipe de revoir le code généré (`workspace/output/src/`)
avant le scan QA. Si gate non actif → skip directement vers STEP 4.5.

---

## STEP 4.5 — QA + Quality (auto-invoke conditionnel)

Lire `QAMode` dans `## Project Config` (default `manual`).

| `QAMode` | Action |
|---|---|
| `off` | skip silencieusement |
| `manual` | skip (l'utilisateur lance `/qa-generate` manuellement) |
| `full`, `tests-only`, `tests+coverage`, `quality-only` | exécuter `/qa-generate {n}` |

`/qa-generate` n'est jamais bloquant pour `/sdd-full`. GREEN/YELLOW/RED
sont propagés au récap STEP 5.

**State tracking (v6.1)** : `set-phase -Phase qa-generate -Status {pass|warn|fail|skip} -PayloadJson '{"decision":"GREEN|YELLOW|RED","coverage":pct,"tests":N}'`. Status `skip` si `QAMode ∈ {off, manual}`.

---

## STEP 4.7 — Refresh dashboards (auto, depuis 2026-05-08)

Invoquer **systématiquement** `Agent: dashboard` (Haiku 4.5) en
fin de pipeline pour régénérer :

- `workspace/output/dashboard/README.html`
- `workspace/output/context/adrs/INDEX.md`
- `workspace/output/qa/feat-{n}/dashboard.html` (si artefacts QA présents)

Coût : ~quelques k tokens (Haiku), latence ~2-5 s. Non bloquant : sur
échec, émettre WARNING (non-bloquant) et continuer vers STEP 5. Le
dashboard est un artefact de visualisation, pas une dépendance
fonctionnelle du pipeline.

**State tracking (v6.1)** : `set-phase -Phase doc-refresh -Status {pass|warn} -PayloadJson '{"htmlPages":N}'`.

---

## STEP 5 — Récap consolidé

**State tracking (v6.1)** : avant d'émettre le récap, finaliser le run :

```bash
FINAL_STATUS={success|partial|failed}   # success si tout 🟢, partial si ≥1 WARN/SKIP, failed si ERROR
$PS_BIN -File .claude/scripts/sdd-state.ps1 -Action end-run `
  -RunId $RUN_ID -Status $FINAL_STATUS
```

Le récap textuel ci-dessous peut ajouter une ligne `Run trace : $RUN_ID`
en pied (utile pour `--resume` futur ou pour ouvrir
`workspace/output/.state/events.jsonl` à des fins de diagnostic).

Émettre **un seul bloc final** :

```
✅ /sdd-full {n}-{SpecName} — pipeline complet terminé

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

Échecs (phase 4) — si présents :
  - dev-{backend|frontend} {n}-{m}-{Name} : {raison condensée}

Prochaine étape :
  - inspecter le code dans workspace/output/src/
  - relancer /dev-run {n} pour réessayer les échecs (idempotent)
  - /sdd-status {n} pour confirmer l'état complet
```

Si succès complet sans accroc :
```
✅ /sdd-full {n}-{SpecName} — {U} US, {H} mockups HTML, code dans workspace/output/src/
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
- BREAKING CHANGES history : `@.claude/CHANGELOG.md`
- Workflow flow ASCII : `@.claude/docs/workflow.md`
