# Rubric — Reverse Complexity Routing (escalier code 3a/3b/3c)

> **SSoT de la décision de routage** pour l'escalier reverse code-stream.
> ADR `governance-reverse-complexity-ladder` (2026-06-29). Mirror
> exécutable : `.sdd/python/sdd_reverse/code_unit_complexity.py` — garder les
> deux en synchro (test `tests/test_reverse_complexity_routing.py`).

## But

L'escalier (`governance-major-reverse-spec-ladder`) applique 2 passes **Opus**
(3a + 3c) à **toute** unité. Ce rubric classe chaque unité `simple | complex` à
partir des signaux **L0 déjà extraits** (`inventory.json`, 0 token) pour **router
le modèle** : `simple` → escalier full-Sonnet ; `complex` → 3a/3c restent Opus.
3b est Sonnet dans les deux cas.

**Périmètre = modèle uniquement.** La structure (3 barreaux, 3 artefacts, fil D3
`FEAT→US→T-N→evidence`, confidence min-monotone) est **inchangée**. Ce n'est PAS
le collapse structurel (fusion mono-prompt), écarté en V2.

## Règle (défaut MVP — conservateur)

Une unité est **`simple`** si **TOUTES** ces conditions tiennent ; sinon `complex`.

| # | Signal (`inventory.json.units[U-N]`) | Condition `simple` |
|---|---|---|
| 1 | `kind` | ∈ `{form, page, grid, api}` |
| 2 | `classes` (graphe L0) | **non vide** ET `len ≤ 5` |
| 3 | `classes[].role` | aucun rôle `complex` (god-class) |
| 4 | `dataAccess` | pas de SQL dynamique (`dynamicSql`/`dynamic`) |
| 5 | `confidenceEstimate` | `== high` (non dégradé) |

## Fail-safe (load-bearing)

**Tout signal manquant ou ambigu → `complex`.** Le doute coûte un Opus, jamais
une sous-analyse. En particulier :

- **Graphe vide/absent (condition 2)** : les langages **non-.NET** n'ont pas de
  graphe de classes (`code_graph_builder` est .NET-only, cf.
  `rules/reverse-engineering.md §4`). On ne peut donc pas *confirmer* la
  simplicité → ces unités restent `complex` (= Opus) en MVP. Les économies
  s'accumulent sur le legacy **.NET** où le graphe existe. Le routage non-.NET
  est un follow-up explicite (nécessite un signal de profondeur non-.NET).
- `kind` absent, `classes` non-liste, `unit` non-dict → `complex`.

## Calibrage

Les seuils (`SIMPLE_KINDS`, `MAX_CLASSES`, rôle god-class) sont des constantes
documentées dans `code_unit_complexity.py`. À **calibrer sur les legacy réels** :
mesurer le taux `simple/complex` et la qualité comparée Sonnet vs Opus sur un
échantillon avant de relâcher (plus permissif) ou resserrer.

## Effet attendu

| Unité | 3a | 3b | 3c | Coût relatif |
|---|---|---|---|---|
| `complex` (statu quo) | Opus | Sonnet | Opus | ~2.2 Opus-equiv |
| `simple` | Sonnet | Sonnet | Sonnet | ~0.6 Opus-equiv (**~−70 %**) |

Avec ~70-80 % d'unités simples sur un legacy .NET typique → réduction agrégée
majeure du budget Opus reverse, à risque architectural nul (rollback = retirer
le routage, agents inchangés).

## Anti-derive

- 0 token (déterministe, stdlib only, D4-isolé — aucun import `sdd_lib`).
- Ne modifie **jamais** la structure de l'escalier ni les artefacts produits.
- `complex` par défaut : aucune régression possible vs le comportement actuel
  full-Opus (au pire, une unité reste en Opus comme aujourd'hui).
</content>
