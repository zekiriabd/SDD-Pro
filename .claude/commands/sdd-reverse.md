---
description: Phase 3 du workflow reverse — SÉQUENCEUR de l'escalier ascendant pour UNE unité U-N (3a analyse → 3b user stories → 3c FEAT). Ne spawn AUCUN agent directement (no-spawn §9) — enchaîne /sdd-reverse-analyze + /sdd-reverse-stories + /sdd-reverse-feat. Output final workspace/feats/{n}-{FeatName}.md consommable par /sdd-full.
---
# /sdd-reverse {U-N} [--json]

## Rôle

Lancer la **Phase 3 complète** sur une unité : l'**escalier ascendant** qui
remonte le code legacy jusqu'à une FEAT métier. `/sdd-reverse` est un **séquenceur
de commandes** (no-spawn §9 `rules/reverse-engineering.md`) — il n'invoque aucun
agent directement, il enchaîne les 3 sous-commandes barreau par barreau :

```
/sdd-reverse {U-N}
  ├─ 3a  /sdd-reverse-analyze {U-N}   → plans/{n}-{FeatName}.analysis.md   (reverse-tech-analyst)
  ├─ 3b  /sdd-reverse-stories {U-N}   → us/{n}-{m}-{Name}.md           (reverse-us-writer)
  └─ 3c  /sdd-reverse-feat {U-N}      → feats/{n}-{FeatName}.md             (reverse-feat-composer)
```

> **Décommission (ADR reverse-spec-ladder D2)** : l'ancien `/sdd-reverse`
> mono-saut (agent `reverse-functional-extractor`, code→FEAT en un coup) est
> remplacé par cet escalier. Le saut unique faisait baver l'altitude technique
> dans la FEAT métier — l'escalier sépare l'analyse fidèle (3a) de la remontée
> métier (3b/3c). En mode pré-alloué (L5), plusieurs `/sdd-reverse {U-N}` peuvent
> tourner en parallèle borné (§8.2).

## Args

| Arg | Type | Description |
|---|---|---|
| `{U-N}` | string requis | Identifiant U-N stable (ex. `U-3`) |
| `--json` | flag | Propagé aux 3 sous-commandes (rapports JSON) |

## Pré-conditions

Identiques à `/sdd-reverse-analyze` (3a — premier barreau possède l'allocation) :
`inventory.json` passe gate ADV-23, `units[id={U-N}]` existe, templates présents.
Sinon → ERROR remontée par le barreau concerné (`[REVERSE_*]`).

## Actions (séquence — STOP au premier barreau en échec)

1. **3a** : exécuter `/sdd-reverse-analyze {U-N}`. Échec (`[REVERSE_*]`) → STOP (pas de 3b/3c).
2. **3b** : exécuter `/sdd-reverse-stories {U-N}`. Échec → STOP (pas de 3c).
3. **3c** : exécuter `/sdd-reverse-feat {U-N}`.
4. Émission ligne chat finale `[REVERSE] {U-N} → escalier 3a→3b→3c terminé, FEAT {n}-{FeatName} (confidence={cap}). (PROGRESS%)`.

## Sortie

```
workspace/plans/{n}-{FeatName}.analysis.md         (3a — analyse technique legacy)
workspace/us/{n}-{m}-{Name}.md                 (3b — user stories)
workspace/feats/{n}-{FeatName}.md                   (3c — FEAT métier, pont vers /sdd-full)
workspace/old/{P}/.sys/modules/{FeatName}/{extraction,stories-3b,feat-3c}.md   (logs)
```

## Confidence ≠ high

La confidence est **min-monotone** le long de l'escalier (3c ≤ 3b ≤ 3a). Si la
FEAT finale est `medium|low`, elle porte la bannière + REVERSE-GATE
`allow-sdd-full=false`. Consommation forcée : `check_reverse_feat_for_full.py --allow-reverse-low`.

## Voie d'usage standard

1. `/sdd-reverse-inventory MyLegacy` (Phase 1)
2. `/sdd-reverse U-1` (escalier 3a→3b→3c complet) — ou les 3 sous-commandes séparément pour reprendre barreau par barreau
3. Tech Lead revue Phase 5 (compléter `## Project Config` de la FEAT)
4. `check_reverse_feat_for_full.py --feat-path workspace/feats/1-*.md`
5. `/sdd-full 1`

## Anti-derive

- **Une seule unité par invocation**.
- **No-spawn** : `/sdd-reverse` séquence des COMMANDES, n'invoque aucun agent directement (§9).
- Échec d'un barreau → STOP (pas de barreau suivant sur données incomplètes).
- Idempotence : re-lancer ré-exécute les 3 barreaux (mêmes `n`/`Name` via `_featAllocations`).

Voir `.sdd/docs/reverse-engineering-workflow.md` §Phase 3 + ADR `governance-major-reverse-spec-ladder`.
