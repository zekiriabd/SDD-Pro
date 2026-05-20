# /doc-refresh

> Régénère l'**INDEX.md des ADRs** depuis l'état du workspace.
> **Idempotent**. Invoque l'agent `dashboard` (Haiku 4.5).
>
> **v6.10 BREAKING** : les rendus HTML (`dashboard/README.html`,
> `qa/feat-{n}/dashboard.html`) sont **retirés**. Les métriques vivent
> dans `workspace/output/db/console.db` (SQLite SSoT, 24 tables) et le
> rendu graphique est délégué à la console web (`workspace/console/`)
> ou à tout consommateur externe (BI tool, script).

## Usage

```
/doc-refresh
```

Aucun argument. La commande lit les ADRs du workspace et régénère
l'index.

## Fichier produit

| Fichier | Description |
|---|---|
| `workspace/output/.sys/.context/adrs/INDEX.md` | Index ADRs (rebuild depuis `Glob workspace/output/.sys/.context/adrs/ADR-*.md`) |

## Quand l'utiliser

- **Manuel** : après une édition manuelle d'un US/FEAT/ADR pour
  rafraîchir la visualisation
- **Auto** : invoqué en fin de `/sdd-full`, `/dev-run`, `/qa-generate`
  (cf. wirings dans ces commandes)
- **Auto** : invoqué en fin d'`arch` Phase D (création d'ADRs) pour
  reconstruire l'INDEX.md

## STEP 1 — Invoquer l'agent

```
Agent: dashboard
```

L'agent lit `.claude/templates/adrs-index.template.md` +
`.claude/rules/error-classification.md` + `Glob` sur les ADRs
et écrit `workspace/output/.sys/.context/adrs/INDEX.md`.

## STEP 2 — Confirmation

L'agent émet **1 ligne** (chat minimal succès) :

```
✅ dashboard — INDEX.md ({N} ADRs) refreshed
```

Sur erreur : 2 lignes max avec préfixe `[CLASS]` (cf. `error-classification.md`).

## Idempotence stricte

- Aucun état conservé entre runs
- Le fichier `INDEX.md` est overwritten à chaque run
- Peut être ré-invoqué sans risque, en parallèle de tout autre agent
  (l'output ne croise aucune matrice de `file-ownership.md §1`)

## Coût

- Haiku 4.5 : ~quelques milliers de tokens par run
- Latence : ~2-5 s selon volume workspace
- Aucun appel à un autre agent, aucun build, aucun test
