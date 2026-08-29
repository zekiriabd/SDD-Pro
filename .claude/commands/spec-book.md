---
name: spec-book
description: /spec-book — Cahier des charges fonctionnel (.docx + .md)
---
<!-- @llm-only-flags-file — les flags de /spec-book (--assemble) sont interprétés
     par Claude à l'orchestration ; seul le script generate_specbook.py porte de
     vrais flags argparse (--feats-dir/--out-dir/--project/--json/--print-hash),
     déclarés dans les blocs de code ci-dessous. -->

# /spec-book — Cahier des charges fonctionnel (.docx + .md)

> Génère / met à jour le **cahier des charges** du projet : un document Word
> décrivant **toutes** les fonctionnalités (FEATs) en **langage humain simple**,
> lisible par un gérant ou un décideur non-technique. Régénéré à chaque nouvelle
> fonctionnalité ou analyse. Sortie : `workspace/docs/cahier-des-charges.docx`
> (+ miroir `.md` pour diff/review).
>
> Deux moitiés (pattern SDD_Pro) : l'agent `specbook-writer` (LLM) rédige la
> prose humaine par FEAT ; le script déterministe `generate_specbook.py`
> (0 token) assemble le `.docx`. Le document est **toujours** régénérable même
> si l'étape LLM n'a pas tourné (mode brut « à humaniser »).

## Usage

```
/spec-book              # tout le projet (humanise les FEATs nouvelles/modifiées)
/spec-book {n}          # (ré)humanise uniquement la FEAT {n}, puis réassemble
/spec-book --assemble   # réassemble seulement (0 token, pas d'agent LLM)
```

## Pré-conditions

- Au moins une FEAT sous `workspace/feats/{n}-*.md`. Sinon
  `[FEAT_NOT_FOUND]` → suggérer `/feat-generate`.
- Dossier de sortie `workspace/docs/` (créé automatiquement).

## STEP 1 — Détecter ce qui doit être (ré)humanisé

Lire le manifeste précédent s'il existe :
`workspace/docs/.sys/specbook-manifest.json`. Pour chaque FEAT
`workspace/feats/*.md`, comparer son hash courant
(`generate_specbook.py --print-hash <feat>`) au `hash` du manifeste **et** à la
présence d'une section fraîche `workspace/docs/.sys/sections/{feat-id}.md`.

Est « à humaniser » toute FEAT dont : la section cache est absente, OU son
`feat_hash` diffère du hash courant (FEAT modifiée depuis), OU `--assemble`
n'est pas passé et `{n}` la cible explicitement.

`--assemble` → sauter le STEP 2 (aucun agent).

## STEP 2 — Rédiger les sections humaines (agent, borné)

Pour chaque FEAT à humaniser, spawn l'agent `specbook-writer` (Sonnet 4.6) avec
l'identifiant de FEAT. Parallélisme borné (`MaxParallel`, défaut 3) — les
sections sont des fichiers disjoints (`sections/{feat-id}.md`), donc parallèle-safe.
Chaque agent écrit sa section vulgarisée en cache. Une FEAT inchangée est
**sautée** (économie de tokens — c'est le mécanisme « mise à jour incrémentale »).

## STEP 3 — Assembler le document (déterministe, 0 token)

```bash
python .sdd/python/sdd_scripts/generate_specbook.py \
  --feats-dir workspace/feats \
  --out-dir workspace/docs \
  --project "<nom du projet>" --json
```

Le script relit **toutes** les FEATs + les sections en cache fraîches, et écrit :

| Fichier | Rôle |
|---|---|
| `workspace/docs/cahier-des-charges.docx` | Livrable Word (langage gérant) |
| `workspace/docs/cahier-des-charges.md` | Miroir markdown (diff / review) |
| `workspace/docs/.sys/specbook-manifest.json` | hash + mode par FEAT (drive STEP 1) |

Les FEATs sans section fraîche sont rendues en **mode brut** (spécification
reprise telle quelle, chapitre marqué « à humaniser ») — le document reste
valide et complet.

## STEP 4 — Rendu chat

Une ligne exécutive :

```
[SPECBOOK] Cahier des charges — {N} fonctionnalités, {H} humanisées ({R} à humaniser) → workspace/docs/cahier-des-charges.docx. (100%)
```

## Intégration pipeline (mise à jour automatique)

Ce document doit refléter **la globalité des features à tout moment**. Appeler
`/spec-book` (idempotent, incrémental) :

- en fin de `/sdd-full {n}` (nouvelle FEAT réalisée) ;
- en fin de `/sdd-reverse-full` (nouvelle analyse legacy → FEATs) ;
- après tout `/feat-generate` (nouvelle spécification) ou édition de FEAT.

Comme l'assemblage est déterministe et que l'humanisation est cachée par hash,
un ré-appel sur un projet inchangé coûte ~0 (aucun agent spawné, réassemblage
en quelques ms).

## Erreurs

Format `[CLASS]` (cf. `@.sdd/rules/error-classification.md`). Principales :
`[FEAT_NOT_FOUND]` (aucune FEAT), `[DISK]` (dossier non inscriptible).
Jamais bloquant pour le pipeline appelant (best-effort en fin de run).
