# /doc-refresh

> Régénère l'**INDEX.md des ADRs** depuis l'état du workspace.
> **Idempotent**. Exécution déterministe via `index_adrs.py` (v7.0.0).
>
> **v7.0.0 BREAKING** : l'agent `dashboard` (Haiku 4.5) a été **retiré**.
> Sa seule responsabilité restante (générer `INDEX.md` des ADRs) est
> 100 % mécanique (glob + parse frontmatter + render template) et ne
> justifiait pas une invocation LLM. Le script Python
> `sdd_scripts/index_adrs.py` le remplace : 0 token, ~50 ms.
>
> **v6.10 BREAKING (préservé)** : les rendus HTML
> (`dashboard/README.html`, `qa/feat-{n}/dashboard.html`) restent retirés.
> Les métriques vivent dans `workspace/output/db/console.db` (SQLite
> SSoT, 24 tables) et le rendu graphique est délégué à la console web
> (`workspace/console/`) ou à tout consommateur externe.

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

- **Manuel** : après une édition manuelle d'un ADR pour rafraîchir l'index
- **Auto** : invoqué en fin de `/sdd-full`, `/dev-run`, `/qa-generate`
  (cf. wirings dans ces commandes — désormais via Bash, plus via Agent)
- **Auto** : invoqué en fin d'`arch` Phase D (création d'ADRs) pour
  reconstruire l'INDEX.md

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
  `file-ownership.md §1`)

## Coût

- **0 token LLM** (était Haiku 4.5 ~3k tokens en v6.10)
- Latence : ~50 ms
- Aucun appel à un autre agent, aucun build, aucun test

## Migration depuis l'agent `dashboard`

Les callers historiques (`/sdd-full`, `/dev-run`, `/qa-generate`,
`agents/arch.md` Phase D) qui invoquaient `Agent(dashboard, ...)`
doivent désormais lancer le script via Bash. Substance équivalente,
verdict idempotent identique, sortie chat identique au préfixe près
(`OK index_adrs —` vs `✅ dashboard —`).
