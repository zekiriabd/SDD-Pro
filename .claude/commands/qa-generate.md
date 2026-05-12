# /qa-generate — Tests unitaires + Coverage + Quality scan

Délègue à l'agent `qa` (Sonnet 4.6) pour générer les tests unitaires
(backend + frontend) d'une SPEC, exécuter le coverage parsing
(PowerShell, 0 token) et le quality scan sonar-like (PowerShell,
0 token).

**Usage :**
- `/qa-generate {n}` — pipeline QA complet selon `QAMode` du Project Config
- `/qa-generate {n} --mode {full|tests-only|tests+coverage|quality-only}`
  — override le `QAMode` du Project Config pour cette invocation

**Décisions possibles** :
- 🟢 **GREEN** : tous tests passent + coverage OK + 0 quality error
- 🟡 **YELLOW** : tests passent mais coverage < seuil OU quality errors
- 🔴 **RED** : au moins 1 test échoué

---

## STEP 1 — Valider l'argument

Argument **obligatoire** : `{n}` (entier ≥ 1).

Si absent →
```
ERROR: /qa-generate — argument manquant
CAUSE: aucun numéro de SPEC fourni
FIX: relancer /qa-generate {n} (ex. /qa-generate 1)
```

Si non numérique →
```
ERROR: /qa-generate — argument invalide
CAUSE: "{argument}" n'est pas un entier
FIX: relancer /qa-generate {n}
```

Détecter `--mode {value}` dans les arguments. Stocker `mode_override`
si présent.

---

## STEP 2 — Vérifier les préconditions

### 2.1 SPEC existe

Glob `workspace/input/specs/{n}-*.md`.

- 0 fichier → ERROR :
  ```
  ERROR: /qa-generate — SPEC introuvable
  CAUSE: aucun fichier workspace/input/specs/{n}-*.md
  FIX: créer la SPEC via /spec-generate avant
  ```
- > 1 fichier → ERROR (numérotation invalide).

### 2.2 US existent

Glob `workspace/output/us/{n}-*.md`.

- 0 fichier → ERROR :
  ```
  ERROR: /qa-generate — aucune US trouvée
  CAUSE: [QA_PRECONDITION_FAILED] /us-generate {n} n'a pas tourné
  FIX: lancer /us-generate {n} d'abord
  ```

### 2.3 Code production existe

Vérifier `workspace/output/src/{BackendName}/` et/ou `workspace/output/src/{AppName}/`
existent (au moins un projet).

- Aucun → ERROR :
  ```
  ERROR: /qa-generate — code production absent
  CAUSE: [QA_PRECONDITION_FAILED] aucun code dans workspace/output/src/
  FIX: lancer /dev-run {n} d'abord
  ```

---

## STEP 3 — Résolution du QAMode

Lire `## Project Config` de `workspace/input/stack/stack.md` :
- `QAMode` (default `manual`)
- `CoverageMin` (default `80`)

Résoudre le mode effectif :
- Si `mode_override` (depuis l'argument `--mode`) → utiliser cette valeur
- Sinon → utiliser `QAMode` du Project Config

Modes valides :
- `off` → exit silencieux : `qa-generate {n}: skipped (QAMode=off)`
- `quality-only` → STEP 4 + STEP 5 + STEP 9 (skip 6, 7, 8)
- `tests-only` → STEP 6 + STEP 7 + STEP 9 (skip 4, 5, 8)
- `tests+coverage` → STEP 6 + STEP 7 + STEP 8 + STEP 9 (skip 4, 5)
- `full` → tous les STEP
- `manual` → identique à `full` (legacy compat)
- `api-tests` (depuis 2026-05-07, cf. `rules/backend-first.md`) →
  génère et exécute UNIQUEMENT les tests d'intégration HTTP
  (style Postman) via `WebApplicationFactory<Program>` + DB
  in-memory + auth handler mocké. Sortie :
  `workspace/output/qa/feat-{n}/api-tests.{md,json}`. Pas de tests
  unitaires, pas de coverage parsing, pas de quality scan. Mode
  invoqué automatiquement par `/dev-run` STEP 6.b (API Gate).
  Optionnel : `--filter {endpoint}` pour ne re-tester que les
  endpoints listés (ex. `--filter "GET /api/v1/points-de-vente,POST /api/v1/points-de-vente"`).

Si mode invalide → ERROR `[STACK_MALFORMED]`.

---

## STEP 4 — Quality scan (PowerShell, 0 token)

Skip si mode = `tests-only` ou `tests+coverage`.

Exécuter `quality-scan.ps1` avec fallback `pwsh → powershell` :

```bash
if command -v pwsh >/dev/null 2>&1; then
  PS_BIN=pwsh
else
  PS_BIN=powershell
fi
$PS_BIN -NoProfile -ExecutionPolicy Bypass \
  -File .claude/scripts/quality-scan.ps1 \
  -SpecNumber {n}
```

Sortie : `workspace/output/qa/feat-{n}/quality.json`.

Capturer le code de retour (devrait être 0). Si ≠ 0 → WARNING (non
bloquant).

---

## STEP 5 — Linter / Type checker stack-native (Bash, 0 token)

Skip si mode = `tests-only` ou `tests+coverage`.

Pour chaque QA stack actif (lu depuis `## Active QA Specs`), exécuter
le linter du stack §6 si déclaré. Capturer warnings/errors dans la
section §4 du rapport (STEP 9).

**Non-bloquant** : un linter qui échoue produit un WARNING dans le
rapport.

---

## STEP 6 — Déléguer génération tests à l'agent qa

Skip si mode = `quality-only`.

Invoquer l'agent `qa` :

```
Task → subagent_type: qa
Argument : {n}
```

L'agent gère :
- STEP 2 à 6 internes : préconditions, contexte, init projets test, plan inline tests
- STEP 7 internes : exécution tests via Bash
- STEP 8 internes : parse coverage via PowerShell

Modes propagés à l'agent via le mode résolu en STEP 3.

---

## STEP 6.5 — Refresh dashboard QA (auto, depuis 2026-05-08)

Après écriture de `coverage.json` + `quality.json` + `report.md`,
invoquer `Agent: dashboard` (Haiku 4.5) pour régénérer
`workspace/output/qa/feat-{n}/dashboard.html` (visualisation HTML des
métriques).

Non bloquant : sur échec, WARNING + continuer vers STEP 7.

---

## STEP 7 — Confirmation et récap

Lire `workspace/output/qa/feat-{n}/coverage.json` (si présent) et
`workspace/output/qa/feat-{n}/quality.json` (si présent).

Calculer la décision globale :

```
si tests.failed > 0:                    → RED
elif coverage_passed == false:          → RED   (depuis v6.1 hardening, cf. qa-coverage.md §3.1)
elif quality.errors > 0:                → YELLOW
else:                                   → GREEN
```

Émettre **un seul bloc final** :

```
qa-generate {n}-{SpecName} → {GREEN | YELLOW | RED}

Mode           : {mode}
Tests          : {passed}/{total} passants ({skipped} skipped, {failed} échec(s))
Coverage       : {pct}% (seuil {CoverageMin}%) → {pass | gap}
Quality scan   : {errors} errors / {warnings} warnings / {info} info
Linter         : {linter_warnings} warnings

Rapport        : workspace/output/qa/feat-{n}/report.md
Coverage       : workspace/output/qa/feat-{n}/coverage.json
Quality        : workspace/output/qa/feat-{n}/quality.json

{Si RED ou YELLOW : section rappels}
Prochaine étape :
  - 🟢 GREEN  : feature livrable, tests verts
  - 🟡 YELLOW : review workspace/output/qa/feat-{n}/report.md (coverage gap ou quality errors)
  - 🔴 RED    : 1+ tests échoués → /dev-run {n} pour corriger ou ajuster les tests
```

**Exit code** :
- `GREEN` ou `YELLOW` → exit 0 (succès, /qa-generate n'est pas une gate
  bloquante)
- `RED` → exit 1 (au moins 1 test échoué)

---

## Mode automatique depuis `/sdd-full`

Si invoqué depuis `/sdd-full {n}` (héritage), le mode résolu est
`QAMode` du Project Config. Si `QAMode: off` ou `QAMode: manual`,
`/sdd-full` skippe simplement `/qa-generate`.

Voir `/sdd-full` STEP 5 pour la logique d'invocation auto.

---

## Règles de cette commande

- **Idempotente** : relancer `/qa-generate {n}` régénère les tests + rapports
- **Read-only sur code production** : aucune modification dans
  `workspace/output/src/{App|Backend|Lib}/**` hors patterns test
- **Token-efficient** :
  - quality-only mode : ~3k tokens (juste le rapport, scan déterministe)
  - tests-only mode : ~17-27k tokens (génération tests Sonnet)
  - tests+coverage mode : ~17-27k tokens (coverage parsing gratuit)
  - full mode : ~20-30k tokens (recommandé)
- **Pas de bloquage** sur tests rouges : la commande exit 1 mais le
  pipeline `/sdd-full` continue (la review est laissée à l'humain)
