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

**Chemin From-Plan Strict (v6.2, opt-in)** : `PlanCacheStrict: true` dans
`## Project Config` active le routing strict — quand un plan v2
strict-ready existe, `/dev-run` STEP 6.0.bis spawn les forks Sonnet 4.6
(`dev-backend-strict`, `dev-frontend-strict`) au lieu d'Opus 4.7 (gain
latence ×3, coût ×5 moins cher). Fallback automatique classic Opus sur
`[PLAN_DIGEST_INSUFFICIENT]`. Recommandé d'invoquer `/sdd-full {n} --plan`
pour garantir une phase `/dev-plan` qui produit les plans v2. Détail :
`@.claude/docs/DESIGN-FROMPLAN-STRICT.md` et `@.claude/MIGRATION.md`
section "v6.1.x → v6.2.0".

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
(`--manual-gates`). Voir STEP 1.bis et la procédure GATE générique en
STEP 1.ter.

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent → demander `Quel est le numéro de la FEAT à exécuter ? (ex. : 1)`.
Si non numérique → ERROR `[INVALID_ARG]`.

---

## STEP 1.quart — Initialiser l'état du run (Phase 0 observability, v6.1)

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

Si `--resume` actif → utiliser plutôt :
```bash
RUN_ID=$(python .claude/python/sdd_scripts/sdd_state.py get-run --feat-number {n} --latest)
```

Stocker `$RUN_ID` pour les appels `set-phase` ultérieurs (STEPs 3, 3.5,
4, 4.5, 4.7). Si la primitive échoue (script absent, FS lecture seule),
émettre un WARNING 1 ligne et continuer (non bloquant — l'observabilité
est best-effort).

---

## STEP 1.tiers — Phase planner (méta-orchestrateur conditionnel, v6.4.1)

Cette commande **n'invoque PAS** elle-même les agents auditor v6.3.x +
v6.4.0 (a11y, code-review, threat-model, security-scan, perf-audit) —
ils sont auto-invoqués depuis `/dev-run` / `/qa-generate` selon leur
mode (cf. agent.md §Intégration pipeline). Mais `/sdd-full` peut
émettre **dès le démarrage** un récap des phases auditor planifiées,
utile pour l'observabilité du run et l'estimation tokens.

Exécuter via Bash (best-effort, non bloquant) :

```bash
PHASE_PLAN=$(python .claude/python/sdd_scripts/phase_planner.py \
  --feat-number {n} --json 2>/dev/null)
```

Parser le JSON et émettre 1 ligne récap :

```
FEAT {n} — auditor phases planifiées : {N_enabled}/{N_total} ({tokens_est} KB est., {tokens_saved} KB évités via skip conditionnel)
  ✓ {phase_name} ({tokens} KB)         # pour chaque phase enabled
  ⊘ {phase_name} : {skip_reason}       # pour chaque phase skipped
```

Si le script échoue (Python absent, parse error) → WARNING 1 ligne et
continuer **sans plan** (les agents auditor tournent quand même selon
leur mode Project Config — le planner est un raccourci, pas une gate).

**Critique** : ce STEP n'**affecte pas** le pipeline. Les décisions
runtime restent prises par les agents eux-mêmes via leur STEP 1.2
(lecture Project Config). Le planner sert à :

1. **Émettre un récap unifié** au démarrage (UX Tech Lead)
2. **Détecter des incohérences précoces** (ex. CodeReviewMode=full
   mais aucun code généré encore — early warning)
3. **Faciliter le debugging** (Tech Lead voit pourquoi telle phase
   n'a pas tourné via `skip_reason` lisible)

State tracking :

```bash
python .claude/python/sdd_scripts/sdd_state.py set-phase \
  --run-id $RUN_ID --phase planning --status pass \
  --payload-json "$PHASE_PLAN"
```

(Non bloquant — emit-event si pertinent, sinon skip silencieux.)

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

**State tracking** : set-phase phase=us-generate (schema payload cf. STEP 1.quart).

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

Sinon, exécuter `/feat-validate {n}`. Stocker `$readiness_decision ∈
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

**State tracking** : set-phase phase=FEAT-validate (schema payload cf. STEP 1.quart).

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
  (STEP 1.ter) avec `phase = afterPlan`, `label-from = "Plans"`,
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
| ERROR clés stack.md manquantes | propager + STOP (planification reste intacte) |
| ERROR arch | propager + STOP |
| Échecs partiels phase 4 | listés par `/dev-run`, → STEP 4.bis |

**State tracking** : set-phase phase=dev-run (schema payload cf. STEP 1.quart). Si arch a tourné, ajouter aussi set-phase phase=arch en amont.

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

**State tracking** : set-phase phase=qa-generate (schema payload cf. STEP 1.quart). Status `skip` si `QAMode ∈ {off, manual}`.

---

## STEP 4.7 — Refresh INDEX ADRs (auto, depuis 2026-05-08 ; réduit en v6.10)

> **v6.10 BREAKING** — les rendus HTML (`dashboard/README.html`,
> `qa/feat-{n}/dashboard.html`) sont **retirés**. Les métriques vivent
> dans `workspace/output/db/console.db` (SQLite SSoT) et le rendu
> graphique est délégué à un consommateur externe (console web
> `workspace/console/`, BI tool, script). Cf. `agents/dashboard.md §STEP 0`
> et `loader.yml §dashboard`.

Invoquer **systématiquement** `Agent: dashboard` (Haiku 4.5) en
fin de pipeline pour régénérer **un seul fichier** :

- `workspace/output/.sys/.context/adrs/INDEX.md` — table-des-matières
  chronologique des ADRs

Coût : ~1-2 k tokens (Haiku), latence < 2 s. Non bloquant : sur échec,
émettre WARNING et continuer vers STEP 5. L'INDEX ADRs est un artefact
de navigation, pas une dépendance fonctionnelle du pipeline.

**State tracking** : set-phase phase=doc-refresh (schema payload cf. STEP 1.quart).

---

## STEP 4.8 — Audit qualité consolidé `/sdd-review` (depuis v6.11.0)

Lire `ReviewMode` dans `## Project Config` (default `full` depuis v6.11.0
— passe à `manual` pour bypass).

| `ReviewMode` | Action |
|---|---|
| `off` | skip silencieusement |
| `manual` | skip (l'utilisateur lance `/sdd-review {n}` manuellement) |
| `read-only` | `/sdd-review {n} --skip-scans` (lecture DB seule, pas de re-scan) |
| `full` (défaut) | `/sdd-review {n}` complet (re-scan quality + agrégation + arch-reviewer si `ArchReviewMode=full`) |

Le pipeline `/sdd-review` :
1. Re-run [`quality_scan.py`](.claude/python/sdd_scripts/quality_scan.py) (refresh `qa_quality`)
2. Spawn `arch-reviewer` agent si `ArchReviewMode: full` (Pattern + Layers + ADRs → `qa_code_review` avec `[ARCH_*]`)
3. Read DB (qa_quality + qa_code_review + qa_security + qa_a11y + qa_performance + qa_spec_compliance)
4. Triage par owner (backend / frontend / shared / unknown) via [`triage_issues.py`](.claude/python/sdd_scripts/triage_issues.py)
5. Compute verdict 🟢/🟡/🔴 contre `ReviewFailOn`
6. Persist `validation_reports(report_type='review')` + emit `workspace/output/qa/feat-{n}/review.md`

**Comportement bloquant** :
- `ReviewFailOnSddFull: true` dans Project Config (défaut `false`) + verdict
  RED → STOP `/sdd-full` avant STEP 5, exit code propagation.
- Sinon → continue vers STEP 5, le verdict est inclus dans le récap.

**State tracking** : set-phase phase=sdd-review (schema payload cf. STEP 1.quart).
Status `skip` si `ReviewMode ∈ {off, manual}`.

Coût marginal : ~30 s (re-scan déterministe) + ~10-18 KB tokens si
`ArchReviewMode: full` (Sonnet 4.6).

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
- BREAKING CHANGES history : `@.claude/CHANGELOG.md`
- Workflow flow ASCII : `@.claude/docs/workflow.md`
