---
description: Phase 3.7 — couche de synthèse système (vue au-dessus de l'escalier 3a→3b→3c). Rend C4 (contexte/conteneurs/composants), ERD complet et soul.md à partir des SEULS artefacts déterministes (inventory.json, deps-graph.json, db-schema.merged.json). Lecture seule, aucun agent spawné, écrit uniquement sous .sys/synthesis/ (jamais feats/). Déterministe (0 token), non-cassant pour le pipeline existant.
---
# /sdd-reverse-synth {LegacyProject} [--doc-level essentiel|complet|detaille] [--only c4,erd,soul] [--json]

## Rôle

Produire la **vue système** que l'escalier `3a→3b→3c` ne produit pas : diagrammes
**C4**, **ERD complet** et **soul.md** (synthèse exécutive). C'est un **nouvel
étage au-dessus de 3c** : un consommateur **en lecture seule** des artefacts
déterministes déjà présents, qui **ne touche ni à l'escalier, ni au contrat
FEAT**.

> **Pare-feu (non-cassant)** : tous les artefacts sont écrits sous
> `workspace/old/{P}/.sys/synthesis/` — **jamais** sous `workspace/feats/`.
> `/sdd-full` ne voit donc jamais un C4/ERD comme une FEAT à coder.

## Args

| Arg | Type | Description |
|---|---|---|
| `{LegacyProject}` | string requis | Sous-dossier de `workspace/old/` |
| `--doc-level` | `essentiel\|complet\|detaille` (défaut `complet`) | Bouton d'économie de contexte. `essentiel` = C4-contexte + ERD + soul. `complet` = + C4 conteneurs/composants. `detaille` = + table de détail par composant. |
| `--only` | liste parmi `c4,erd,soul` | Régénère seulement les catégories listées (les autres ne sont pas touchées) |
| `--json` | flag | Rapport JSON sur stdout |

## Pré-conditions

1. `workspace/old/{P}/.sys/inventory.json` présent et `schemaVersion == 1`
   (sinon → STOP `[REVERSE_NO_SOURCE]` / `[REVERSE_INVENTORY_SCHEMA_STALE]`).
2. Recommandé : `/sdd-reverse-audit` exécuté avant (produit `deps-graph.json`
   → C4 plus riche, et `db-schema.merged.json` → ERD enrichi). **Dégradation
   gracieuse** si absents : le C4 se limite au contexte, l'ERD à la base.

## Actions (no-spawn — script déterministe)

Invoque le script déterministe, **aucun agent** :

```bash
python .sdd/python/sdd_reverse_scripts/reverse_synth.py --project workspace/old/{LegacyProject} [--doc-level ...] [--only ...] [--json]
```

Le script :
1. Charge `inventory.json` (requis), `deps-graph.json` et `db-schema.merged.json`
   (ou `db-schema.json`) si présents.
2. Nettoie les sorties **gérées** de chaque catégorie régénérée (idempotence :
   repasser à un `--doc-level` inférieur n'y laisse pas d'artefact périmé).
3. Rend, sous `.sys/synthesis/`, selon le doc-level : `c4-context.md`,
   `c4-containers.md`, `c4-components.md`, `erd-complete.md`, `soul.md`.
4. Écrit `manifest.json` (enregistrement d'observabilité **dérivé** — quels
   artefacts, depuis quelles sources, répartition de confiance).
5. Émet la ligne chat finale :
   `[REVERSE] Synthèse ({doc-level}) : {fichiers} [confiance high=.. medium=.. low=..]. (100%)`

## Sortie

```
workspace/old/{LegacyProject}/.sys/synthesis/
├── c4-context.md         # toujours (Mermaid graph TB)
├── c4-containers.md      # complet|detaille
├── c4-components.md      # complet|detaille
├── erd-complete.md       # si un schéma DB existe (Mermaid erDiagram)
├── soul.md               # toujours (synthèse exécutive)
└── manifest.json         # observabilité (dérivé, non SSoT)
```

## Discipline confiance / traçabilité

Chaque énoncé porte sa confiance dans l'enum reverse strict `{high, medium, low}` :
- **C4** : relations issues des arêtes parsées de `deps-graph.json` → `high`.
- **ERD** : entités/relations du DDL → `high` ; déduites du code (`deduced`) → `medium`.
- **soul.md** : objectif **inféré** → `medium` ; entités centrales rankées par
  degré entrant de FK ; contraintes (EOL, cycles) = faits observés. **Aucun
  git-mining, aucune décision « fondatrice » inventée** (lacune assumée).

## Anti-derive

- **No-spawn** : aucun agent (déterministe pur, 0 token).
- **Lecture seule** sur les artefacts ; **aucune** lecture du code legacy
  (l'isolation d'altitude de l'escalier est préservée — seul 3a lit le code).
- **Écriture confinée** à `.sys/synthesis/` ; jamais `feats/`.
- N'altère **jamais** l'escalier `3a/3b/3c` ni les FEAT existantes.

## Idempotence

Re-lancer écrase les sorties (atomic write) et nettoie les artefacts périmés de
chaque catégorie régénérée. Les U-N et les FEAT ne sont pas touchés.

> **Option ultérieure (hors cœur déterministe)** : un agent narratif
> `reverse-soul` / `reverse-architect` pourra enrichir `soul.md` et le C4 d'un
> texte explicatif. Volontairement **non inclus** ici pour préserver la
> reproductibilité et le coût zéro-token.

Voir `.sdd/docs/reverse-engineering-workflow.md` (couche de synthèse, Phase 3.7).
