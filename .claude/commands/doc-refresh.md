# /doc-refresh

> Régénère les artefacts de visualisation SDD_Pro (dashboards HTML +
> index ADRs Markdown) à partir de l'état actuel du workspace.
> **Idempotent**. Invoque l'agent `dashboard` (Haiku 4.5).

## Usage

```
/doc-refresh
```

Aucun argument. La commande lit l'état complet du workspace et
régénère les 3 outputs.

## Fichiers produits

| Fichier | Description |
|---|---|
| `workspace/output/dashboard/README.html` | Vue d'ensemble du projet : SPECs, US par feature, QA scores, ADRs récents |
| `workspace/output/context/adrs/INDEX.md` | Index ADRs (rebuild depuis `Glob workspace/output/context/adrs/ADR-*.md`) |
| `workspace/output/qa/feat-{n}/dashboard.html` | 1 dashboard HTML par feature ayant des artefacts QA (coverage, quality, api-tests) |

## Quand l'utiliser

- **Manuel** : après une édition manuelle d'un US/SPEC/ADR pour
  rafraîchir la visualisation
- **Auto** : invoqué en fin de `/sdd-full`, `/dev-run`, `/qa-generate`
  (cf. wirings dans ces commandes)
- **Auto** : invoqué en fin d'`arch` Phase D (création d'ADRs) pour
  reconstruire l'INDEX.md

## STEP 1 — Invoquer l'agent

```
Agent: dashboard
```

L'agent lit le contexte (`.claude/templates/*`, `.claude/rules/error-classification.md`,
`workspace/output/{us,qa,plans,validation,context}/`) et écrit les 3 outputs.

## STEP 2 — Confirmation

L'agent émet **1 ligne** (`chat-output.md` §1) :

```
✅ dashboard — README.html + INDEX.md (N ADRs) + K feature dashboards refreshed
```

Sur erreur : 2 lignes max avec préfixe `[CLASS]` (cf. `error-classification.md`).

## Idempotence stricte

- Aucun état conservé entre runs
- Les 3 outputs sont overwritten chaque run
- Peut être ré-invoqué sans risque, en parallèle de tout autre agent
  (les outputs ne croisent aucune matrice de `file-ownership.md §1`)

## Coût

- Haiku 4.5 : ~quelques milliers de tokens par run
- Latence : ~2-5 s selon volume workspace
- Aucun appel à un autre agent, aucun build, aucun test
