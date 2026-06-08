# /qa-generate — Tests unitaires + Coverage + Quality scan

<!-- @llm-only-flags-file : tous les flags CLI de cette commande slash sont interprétés par Claude. -->

Délègue à l'agent `qa` (Sonnet 4.6) pour générer les tests unitaires
(backend + frontend) d'une FEAT, exécuter le coverage parsing
(Python, 0 token) et le quality scan sonar-like (Python, 0 token).

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
CAUSE: aucun numéro de FEAT fourni
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

## STEP 1.5 — Checkpoint skip (v6.6.3, opt-in)

Si `CheckpointMode: resume` dans Project Config (défaut `off` =
comportement v6.6.2 strict) :

```python
from sdd_lib.checkpoint import is_phase_resumable

inputs = [
    f"workspace/input/feats/{n}-*.md",       # FEAT parent
    f"workspace/output/us/{n}-*.md",         # toutes les US
    "workspace/input/stack/stack.md",        # config + stacks actifs
]
# Glob les patterns vers paths concrets avant l'appel
resumable, reason = is_phase_resumable(
    feat=n, phase="qa-generate", input_paths=resolved_inputs,
)
if resumable:
    print(f"⊘ /qa-generate {n}: skipped (checkpoint hit, reason=ok)")
    # STOP avec succès, ne pas regénérer
```

Si `CheckpointMode ∈ {off, record}` → skip ce STEP, continuer
normalement.

Émissions possibles :
- `[CHECKPOINT_HASH_MISMATCH]` → inputs modifiés post-run, re-exécuter
- `[CHECKPOINT_INPUT_MISSING]` → input absent, re-exécuter
- `[CHECKPOINT_STATE_UNREADABLE]` → pas de state.json antérieur, première exécution

Cf. `error-classification.md §1.16` + `sdd_lib/checkpoint.py`.

---

## STEP 2 — Vérifier les préconditions

### 2.1 FEAT existe

Glob `workspace/input/feats/{n}-*.md`.

- 0 fichier → ERROR :
  ```
  ERROR: /qa-generate — FEAT introuvable
  CAUSE: aucun fichier workspace/input/feats/{n}-*.md
  FIX: créer la FEAT via /feat-generate avant
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
- `api-tests` (depuis 2026-05-07, cf. `rules/build-and-loop.md`) →
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

## STEP 4 — Quality scan (Python, 0 token)

Skip si mode = `tests-only` ou `tests+coverage`.

Exécuter `quality_scan.py` (Python pur, cross-platform) :

```bash
python .claude/python/sdd_scripts/quality_scan.py --feat-number {n}
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

## STEP 5.5 — Schema slices per US (Levier 4 v7.0.x, audit 2026-06-08)

Skip si mode = `quality-only` (l'agent qa ne tourne pas).

Pour chaque US `{n}-{m}-{Name}` de la FEAT, générer un slice du schema
DB restreint aux tables référencées par l'US (+ FK transitive).
L'agent `qa` consomme les slices en priorité pour ses fixtures
in-memory (cf. `loader.yml` qa.reads + `agents/qa.md` §STEP 3.6) et
fallback automatiquement sur le schema complet si aucun slice présent.

```
for {n}-{m}-{Name} in US_LIST :
    python -m sdd_scripts.generate_schema_slice \
        --us-path workspace/output/us/{n}-{m}-{Name}.md
```

| Exit | Sens | Action `/qa-generate` |
|---|---|---|
| `0` | slice écrit `workspace/output/db/schema-slice-{n}-{m}.json` | continue STEP 6 |
| `2` | CORRECTIBLE — pas de schema OU US ne référence aucune entité | continue STEP 6 (qa fallback) |
| `1` | FAIL_FAST — US introuvable ou basename invalide | STOP + ERROR (problème US, pas slice) |
| `3` | INFRA_BLOCKED — disk write failure | WARN, continue STEP 6 (qa fallback) |

Aucune ligne chat émise (déterministe, 0 token LLM, ~50 ms par US).

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
- STEP 8 internes : parse coverage via Python (`parse_coverage.py`)

Modes propagés à l'agent via le mode résolu en STEP 3.

### 6.bis — Ingest api-tests JSON vers console.db (v6.10, si mode=api-tests)

Si `mode == "api-tests"`, l'agent vient d'écrire `api-tests.json`. Le bridge
Python parse, insère dans `qa_api_tests` + `qa_api_endpoints` (console.db)
puis supprime le `.json`. Le `.md` est conservé.

```bash
if [ "$mode" = "api-tests" ]; then
  python .claude/python/sdd_scripts/ingest_agent_report.py --type api-tests --feat {n}
fi
```

Sur exit ≠ 0 → WARN (rapport JSON manquant ou invalide). Non bloquant
pour le pipeline qa-generate (le `.md` reste lisible humainement).

---

---

## STEP 6.bis — Checkpoint record (v6.6.3, opt-in)

Si `CheckpointMode ∈ {record, resume}` (défaut `off` = skip ce STEP) :

```python
from sdd_lib.checkpoint import record_input_hash

record_input_hash(
    run_id=$RUN_ID,                  # from sdd_state.py current run
    phase="qa-generate",
    input_paths=resolved_inputs,     # même liste que STEP 1.5
)
```

Stocke `input_hash` dans `state.json.phases.qa-generate.payload.input_hash`.
Permet à un futur `--resume` (avec `CheckpointMode: resume`) de skip
cette phase si les inputs n'ont pas changé.

Erreur silencieuse si state.json absent → WARN dans stderr,
non bloquant.

---

## STEP 7 — Confirmation et récap (v6.10 : depuis console.db)

Charger les métriques consolidées de la FEAT directement depuis la DB :

```bash
STATS=$(python .claude/python/sdd_scripts/query_console_db.py feat-stats --feat {n})
```

Le JSON `STATS` contient les blocs `api_gate`, `coverage`, `quality`,
`perf`, `a11y`, `security`, `spec`. Calculer la décision globale :

```
si stats.api_gate.tests_failed > 0:               → RED
elif stats.coverage.coverage_passed == false:     → RED  (cf. quality.md §A.3.1 hardening v6.1, ex-qa-coverage.md)
elif stats.quality.errors > 0:                    → YELLOW
else:                                              → GREEN
```

**Acceptance Gate automatique (post-STEP 7, v7.0.0)** : un hook
`SubagentStop` matcher=qa déclenche `sdd_scripts/validate_acceptance.py`
(détection auto Node/.NET/Kotlin/Python → exécute `test`+`lint`+`build`+
`coverage`, et `smoke browser` + `E2E Playwright` pour les projets UI).
Verdict écrit dans `workspace/output/.sys/.acceptance/acceptance.json`.
Bloquant en mode `AcceptanceGate: strict` (default v7.0.0) — classe
`[ACCEPTANCE_GATE_FAILED]`. Bypass : `SDD_ALLOW_ACCEPTANCE_BYPASS=1`
(audit-loggué). Cf. `quality.md §C`.

Émettre **un seul bloc final** :

```
qa-generate {n}-{FeatName} → {GREEN | YELLOW | RED}

Mode           : {mode}
Tests          : {passed}/{total} passants ({skipped} skipped, {failed} échec(s))
Coverage       : {pct}% (seuil {CoverageMin}% — obligatoire) → {pass | gap}
Quality scan   : {errors} errors / {warnings} warnings / {info} info
Linter         : {linter_warnings} warnings

Rapport        : workspace/output/qa/feat-{n}/report.md
Données        : workspace/output/db/console.db (qa_coverage, qa_quality, qa_api_tests)

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
- **Blocage tests rouges sur `/sdd-full`** (depuis v7.0.0, default `QaFailOnSddFull: true`) :
  - `/qa-generate {n}` standalone : exit 1 sur RED, fail-fast (inchangé)
  - `/sdd-full {n}` post-STEP 4.5 : STOP + ERROR `[QA_FAIL_BLOCKING_SDD_FULL]` si QA verdict RED
  - **Bypass** : `QaFailOnSddFull: false` dans `## Project Config` (décision tracée, logged en audit). Avec le bypass, la review est laissée à l'humain et le pipeline continue. Sans bypass, le pipeline s'arrête et l'humain corrige avant de relancer.
  - Détail rationale + format ERROR : `.claude/rules/error-classification.md` `[QA_FAIL_BLOCKING_SDD_FULL]`.

---

## Chat Output Protocol

> Cette commande applique strictement `@.claude/rules/output-protocol.md`.
> Substance non dupliquée — la règle est SSoT.

**Labels canoniques émis** : `[QA]` (cf. output-protocol.md §3)
**Plage de progression couverte** : `78-88%` (cf. output-protocol.md §4)

**Granularité cible** : 3-5 updates (bootstrap test project si absent,
génération tests, run + coverage, quality scan, verdict).

**Interdits stricts** (cf. §5 du protocole) :
- chemins de fichiers internes (`workspace/...`, `.claude/...`)
- listes de tests générés, assertion dumps, xunit/jest verbose logs
- stdout/stderr de bash, SQL queries

**Verdict final** : 1 ligne avec emoji + compteurs métier. Exemple :
`[QA] 47/47 tests passés, coverage 82% ≥ 80%, verdict 🟢. (88%)`.
En cas de RED : `🔴 [QA/FAIL] {feat} — [QA_TEST_FAILED] 3 tests échec →
workspace/output/qa/feat-{n}/report.md. (84%)`.

**Bypass debug** : `SDD_CHAT_VERBOSE=1` → mode legacy verbose (§10).
