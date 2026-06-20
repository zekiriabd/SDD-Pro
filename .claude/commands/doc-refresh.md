# /doc-refresh

> ⚠️ **Commande interne v7.0.0** — invoquée auto en fin de pipeline
> (`/sdd-full`, `/dev-run`, `/qa-generate`, `arch` Phase D). Régénère
> `INDEX.md` des ADRs via `sdd_scripts/index_adrs.py` (0 token, ~50 ms,
> idempotent). Préférer un orchestrateur en usage normal ; cette
> commande sert au debug/inspection ciblée.

## Usage

```
/doc-refresh
```

Aucun argument. La commande scanne les ADRs du workspace et régénère
l'index.

## Fichier produit

| Fichier | Description |
|---|---|
| `workspace/output/.sys/.context/adrs/INDEX.md` | Index ADRs (rebuild depuis `Glob workspace/output/.sys/.context/adrs/ADR-*.md`) |

## Quand l'utiliser

- **Manuel** : après édition manuelle d'un ADR pour rafraîchir l'index.
- **Auto** : fin de `/sdd-full`, `/dev-run`, `/qa-generate`, `arch` Phase D.

## STEP 1 — Exécuter le script

```bash
python .claude/python/sdd_scripts/index_adrs.py
```

Ou avec arguments explicites :

```bash
python .claude/python/sdd_scripts/index_adrs.py \
  --adrs-dir workspace/output/.sys/.context/adrs \
  --output workspace/output/.sys/.context/adrs/INDEX.md \
  --template .claude/templates/adrs-index.template.md
```

Le script :
1. Lit `.claude/templates/adrs-index.template.md`
2. Glob `workspace/output/.sys/.context/adrs/ADR-*.md`
3. Parse pour chaque ADR : filename (timestamp ISO + slug), H1 titre,
   `Status:` body field (défaut `Accepted`), `Phase:` body field
   (heuristique slug si absent)
4. Render dans le template avec substitution `{ADRRows}`, `{ADRCount}`,
   `{GeneratedAt}`, `{ProjectName}`
5. Write atomique via `.tmp` + read-back self-check

## STEP 2 — Confirmation

Le script émet **1 ligne** (chat minimal succès) :

```
OK index_adrs — INDEX.md ({N} ADRs) refreshed
```

Si aucun ADR : `OK index_adrs — INDEX.md (0 ADRs, empty) refreshed`.

## Codes d'erreur

| Exit | Classe | Cause |
|---|---|---|
| `0` | — | succès |
| `1` | `[NOT_FOUND]` | template `adrs-index.template.md` manquant ou illisible |
| `2` | `[QA_OUTPUT_INVALID]` | atomic write self-check échec (corruption FS rare) |

## Idempotence stricte

- Aucun état conservé entre runs
- Le fichier `INDEX.md` est overwritten à chaque run
- Peut être ré-invoqué sans risque, en parallèle de tout autre agent
  ou script (l'output ne croise aucune matrice de
  `ownership.md §1`, Partie A, ex-file-ownership.md)

## Coût

- **0 token LLM** ; latence ~50 ms ; aucun appel agent/build/test.
