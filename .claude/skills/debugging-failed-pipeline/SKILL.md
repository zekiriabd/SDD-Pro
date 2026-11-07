---
name: debugging-failed-pipeline
description: Use when the user reports that an SDDPro pipeline failed, a build errored, tests failed, the API Gate is RED, the spec-compliance gate failed, an auditor returned RED, or any other SDDPro step blocked. Triggers on phrases like "ça plante", "le build échoue", "API gate RED", "/sdd-full failed", "tests failed", "coverage < seuil". Routes to a deterministic diagnostic via /sdd-status + /sdd-help + reading the relevant report rendered on-demand from console.db (query_console_db.py --format md). Refuses to "just fix the code" without first understanding what gate produced the RED.
---

# Skill — Debugging a Failed SDDPro Pipeline

> **Auto-trigger** : pipeline RED détecté ou rapporté par utilisateur.
> **Anti-pattern strict** : ne JAMAIS "réparer le code" sans avoir lu
> le rapport du gate qui a produit le RED. Le rapport contient déjà
> le diagnostic + suggestion FIX (3 lignes `ERROR/CAUSE/FIX` avec
> classe d'erreur préfixée `[CLASS]`).

## Procédure 4 phases (emprunt superpowers systematic-debugging)

### Phase 1 — Investigation racine (avant tout fix)

1. **Lire le message d'erreur** mot à mot. Pas de scan rapide. Pas
   d'hypothèse "je sais ce que c'est". Lire la classe d'erreur entre
   crochets.

2. **Reproduire** : que le Tech Lead relance la commande, ou lire le
   rapport disque (toutes les erreurs sont persistées 3L).

3. **Vérifier les changements récents** :
   ```bash
   git log --oneline -10
   git diff HEAD~1
   ```
   Beaucoup de pipelines RED viennent d'un changement récent
   (stack.md modifié, US éditée sans re-validate, lib ajoutée hors §2.4).

4. **Identifier le gate qui bloque** :
   ```bash
   /sdd-status {n}          # tree ASCII : quel phase est en échec
   /sdd-help {n}            # guidance "what's next" basée sur l'état
   ```

### Phase 2 — Lire le bon rapport

Selon la classe d'erreur dans le chat :

| Classe `[CLASS]` | Rapport à lire | Action FIX |
|---|---|---|
| `[BUILD_CORRECTIBLE]` | stdout build dans chat (3L ERROR) | déjà itéré par `build_loop` (max BuildLoopMaxIter). Si exhausted → lire stack trace. |
| `[BUILD_BLOCKING]` | stdout build_loop dans chat (3L ERROR) | fail-fast — problème structurel (DI cycle, layer violation). Pas de retry. |
| `[QA_TEST_FAILED]` | `query_console_db.py feat-stats --feat {n} --format md` | tests failing → fix code OU fix test. Pas les deux en même temps. |
| `[QA_COVERAGE_GAP]` | `query_console_db.py coverage --feat {n} --format md` | ajouter tests dans `*.Tests/Unit/` (jamais baisser CoverageMin sans tracer). |
| `[API_GATE_RED]` | `query_console_db.py api-gate --feat {n} --format md` | mismatch contrat back↔front. Re-run `/dev-backend {n}-{m}` puis `/qa-generate {n} --mode api-tests`. |
| `[SPEC_AC_NOT_VERIFIED]` (Stage A gate) | `workspace/.sys/.validation/{n}-spec-compliance.md` | AC non implémenté → `/dev-{backend\|frontend} {n}-{m}` sur l'US fautive. |
| `[REVIEW_*]` (code-reviewer Stage B) | `workspace/.sys/.validation/{n}-code-review.md` | issue qualité → fix manuel ou ré-exec dev-* après modif. |
| `[SEC_*]` hard-blocking | `workspace/.sys/.validation/{n}-security-scan.md` | secrets / SQL injection / SSRF → fix immédiat, pas de bypass. |
| `[STACK_LIBRARY_MISSING]` | chat error 3L | Tech Lead arbitre — éditer `.libs.json` puis `sync_stack_md.py`. |
| `[FEAT_HASH_MISMATCH]` | chat error 3L | re-run `/us-generate {n}` (idempotent, recalcule hash). |
| `[PLAN_STALE]` | chat error 3L | re-run `/dev-plan {n}` puis `/dev-run {n}`. |

### Phase 3 — Appliquer le FIX du rapport

Chaque rapport contient une section `FIX:` (1L) avec l'action
exacte. **Suivre ce FIX**, pas inventer un fix créatif.

Si FIX ambigu OU plusieurs options :
- Préférer la commande SDD_Pro idempotente (`/dev-backend {n}-{m}`,
  `/qa-generate {n} --filter X`) sur l'édit manuel
- Édit manuel autorisé sous `workspace/src/` pour bug ponctuel,
  mais Edit-augment (jamais réécriture intégrale)

### Phase 4 — Vérifier (evidence over claims)

Après le fix, **NE PAS** dire "ça devrait marcher". Au lieu de ça :

```bash
# Re-run l'étape qui avait échoué
/dev-run {n}              # OU
/qa-generate {n}          # OU
/sdd-review {n}
```

Lire le verdict (🟢/🟡/🔴) AVANT de déclarer la résolution.
Pattern emprunt superpowers : **verification-before-completion**.

## Red flags — rationalizations à refuser

| Rationalization | Bonne réponse |
|---|---|
| "C'est probablement un problème de config, je vais éditer X" | NON. Lire le rapport d'abord. La classe `[CLASS]` te dit exactement où regarder. |
| "Je vais réécrire l'US pour matcher le code" | NON. L'US est la spec, le code la matérialise. Si gap : fix code, pas spec. |
| "Le test est faux, je vais le supprimer" | NON. QA owne les tests. Si test invalide → fix dev-* code OR document via ADR. |
| "Je vais relancer en boucle jusqu'à que ça passe" | NON. `build_loop` itère 3× max. Au-delà = problème structurel, lire `[BUILD_BLOCKING]`. |
| "Bypass via --force, on verra après" | NON. `--force` est pour Tech Lead expert qui assume. Tracer en chat + commit message. |
| "Je vais skip le QA gate, c'est trop strict" | NON. Baisser `CoverageMin` / `SpecComplianceFailOn` est OK si tracé. Bypass programmatique = régression garantie. |

## Pointeurs

- `@.sdd/rules/error-classification.md` — taxonomie complète 188 classes
- `@.sdd/rules/build-and-loop.md §2` — boucle correction API Gate
- `/sdd-help {n}` — guidance contextuelle
- `/sdd-status {n}` — tree ASCII état FEAT
- `query_console_db.py {dimension} --feat {n} --format md` — rapports humains rendus à la demande depuis `console.db` (2026-07-06 : plus de dossier `qa/`)
- `workspace/.sys/.validation/{n}-*` — JSON auditors transitoires (ingérés puis supprimés)

> **Règle mentale** : "Le rapport contient déjà le diagnostic.
> Lire avant d'agir. Pas de fix créatif sans avoir lu CAUSE + FIX."
