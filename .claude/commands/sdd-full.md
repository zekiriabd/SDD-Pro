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
```

**Activation projet** : `PlanReviewDefault: true` dans `## Project Config`
de `workspace/input/stack/stack.md` rend `--plan` actif par défaut.

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent → demander `Quel est le numéro de la SPEC à exécuter ? (ex. : 1)`.
Si non numérique → ERROR `[INVALID_ARG]`.

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
| Succès | continuer STEP 3.5 |
| ERROR | propager + STOP |

---

## STEP 3.5 — Implementation Readiness Gate

Si `--no-validate` → forcer `$readiness_decision = GO`, skip STEP 3.5
et STEP 3.6, aller à STEP 4.

Sinon, exécuter `/spec-validate {n}`. Stocker `$readiness_decision ∈
{GO, WARN, NO-GO}`.

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

---

## STEP 3.6 — Plan-then-review gate

**Déclenchement** (cf. tableau STEP 3.5) :
- A. WARN/NO-GO + `--force` (sans `--no-plan-on-warn`)
- B. GO + (`--plan` ou `PlanReviewDefault: true`)

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

### 3.6.c — Checkpoint humain

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

**Attendre la réponse humaine** — seul checkpoint bloquant du pipeline.

| Réponse | Action |
|---|---|
| `ok` | → STEP 4 (`/dev-run` détecte les plans, mode From-Plan, cf. CLAUDE.md §11.10) |
| `stop` | STOP propre. Reprendre via `/dev-run {n}` ou `/sdd-full {n}` (idempotent) |
| `retry` | relancer 3.6.b puis re-poser la question |
| autre | ré-afficher le prompt sans avancer |

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
usage, append-only, jamais nettoyé par `/sdd-clear` (préservé).

Le récap STEP 5 mentionne la présence du log :
```
Bypass force assumé : oui (cf. workspace/output/.audit/force-bypass.log ligne {N})
```

Skip silencieusement si pas de `--force`.

---

## STEP 4 — Phase exécution (`/dev-run {n}`)

Exécuter intégralement `/dev-run {n}` (validation env vars → arch
bootstrap+DB → dev-backend + dev-frontend parallèles bornés).

| Sortie | Action |
|---|---|
| Succès | → STEP 4.5 |
| ERROR env vars | propager + STOP (planification reste intacte) |
| ERROR arch | propager + STOP |
| Échecs partiels phase 4 | listés par `/dev-run`, → STEP 4.5 |

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

---

## STEP 5 — Récap consolidé

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
