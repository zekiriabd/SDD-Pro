# ADR-20260629T120000-7c3a-governance-reverse-complexity-ladder

- **Status**: Accepted (Tech Lead 2026-06-29 — D2 = routage de modèle ; D1 = seuil
  MVP par défaut ; collapse structurel différé en V2 opt-in)
- **Date**: 2026-06-29
- **Materialized**: 2026-06-29 — `code_unit_complexity.py` + rubrique +
  routage dans `/sdd-reverse-analyze` et `/sdd-reverse-feat` + tests (12) verts
- **Slug**: `governance-reverse-complexity-ladder`
- **Phase**: reverse-engineering (Phase 3 — escalier `code → FEAT`)
- **Relates-to**: `governance-major-reverse-spec-ladder` (l'escalier 3a/3b/3c
  que cet ADR raffine, sans le remplacer)

---

## Context

L'escalier reverse (ADR `governance-major-reverse-spec-ladder`) applique **le
même traitement uniforme** à **toutes** les unités : 3 barreaux, dont **2 en
Opus** (3a `reverse-tech-analyst` lit le code ; 3c `reverse-feat-composer`
compose la FEAT), 3b `reverse-us-writer` étant déjà en Sonnet.

L'audit 2026-06-29 a relevé que ce coût est indifférent à la **complexité réelle
de l'unité** : un formulaire CRUD à 2 classes (`Login.aspx` + son service) subit
exactement les mêmes 2 invocations Opus qu'une god-class de 1 200 lignes avec SQL
dynamique. Sur un legacy à longue traîne de petites unités (le cas dominant en
brownfield), l'essentiel du budget Opus part sur des unités triviales où Opus
n'apporte rien de mesurable.

**Précédent maison déterminant** : le stream db-reverse a **déjà** résolu ce
problème. `build_proc_us.py` qualifie chaque procédure par des signaux
déterministes (branches / SQL dynamique / erreurs / curseurs) et génère les
procs triviales **sans LLM** (~70-80 % d'une base typique = CRUD pur). Cet ADR
**porte ce principe — le routage par complexité — vers le stream code**, sans
réinventer ni l'escalier ni la gouvernance.

Contrainte non négociable : la décision `governance-major-reverse-spec-ladder` a
écarté le mono-saut `reverse-functional-extractor` précisément parce qu'un seul
prompt mélangeant analyse / capability / composition faisait **baver l'altitude
technique dans la FEAT métier**. Tout routage doit donc **préserver** la
séparation d'altitude, le fil de traçabilité D3 (`FEAT → US AC → task T-N →
file:line`) et la confidence min-monotone.

---

## Decision

Introduire un **classifieur de complexité déterministe** (0 token) et **router le
choix de modèle** des barreaux 3a et 3c en fonction. **La structure de l'escalier
ne change pas** — 3 barreaux, 3 artefacts, D3 et monotonie intacts ; seul le
**modèle** varie.

### D1 — Classifieur déterministe `code_unit_complexity(unit) → "simple" | "complex"`

Réutilise les signaux **L0 déjà extraits** dans `inventory.json` (aucune nouvelle
extraction, 0 token). Une unité est `simple` **si TOUTES** ces conditions tiennent :

| Signal | Seuil `simple` (défaut MVP, calibrable) |
|---|---|
| `unit.kind` | ∈ `{form, page, grid, api}` (exclut `wizard`, `module`, `job`) |
| nb de classes atteintes (`len(unit.classes)`) | **non vide** ET ≤ 5 |
| rôle `complex` (god-class) parmi `unit.classes[].role` | absent |
| SQL dynamique dans `unit.dataAccess` | absent |
| dégradation de confidence (`confidenceEstimate != high`) | absente |

Sinon → `complex`. Tout signal manquant / ambigu → **`complex`** (fail-safe :
le doute coûte un Opus, jamais une sous-analyse). **Cas du graphe vide** : un
graphe de classes vide/absent (langages non-.NET, où `code_graph_builder` est
indisponible) ne permet pas de *confirmer* la simplicité → ces unités restent
`complex` (= Opus) en MVP. Les économies portent donc sur le legacy **.NET** ;
le routage non-.NET est un follow-up explicite. La rubrique vit dans
`docs/rubrics/reverse-complexity-routing.md` (SSoT, miroir de
`complexity-router-scoring.md`) ; les seuils sont des constantes documentées,
surchargables ultérieurement par config (hors MVP).

### D2 — Routage du modèle (structure inchangée)

| Unité | 3a tech-analyst | 3b us-writer | 3c feat-composer |
|---|---|---|---|
| **`complex`** (statu quo) | **Opus 4.8** | Sonnet 4.6 | **Opus 4.8** |
| **`simple`** (nouveau) | **Sonnet 4.6** | Sonnet 4.6 | **Sonnet 4.6** |

Le routage est appliqué par les **commandes** (`/sdd-reverse-analyze`,
`/sdd-reverse-feat`) au moment du spawn (override de modèle), pas par une
frontmatter d'agent figée — l'agent reste identique, seul son modèle d'exécution
change. Le no-spawn (§9) est préservé : ce sont toujours les commandes qui
spawnent un agent unique chacune.

### D3 — Invariants préservés (pourquoi ce n'est PAS un retour au mono-saut)

- **3 barreaux, 3 artefacts** (`.analysis.md`, `us/*.md`, `feats/*.md`) →
  `check_ladder_traceability.py`, `reverse-completeness-reviewer`, parité, et le
  pont `/sdd-full` (§10) consomment exactement les mêmes entrées qu'aujourd'hui.
- **Séparation d'altitude maintenue** : 3b/3c gardent leurs `forbidden_reads` sur
  le code legacy. On ne fusionne **rien** ; on baisse seulement le modèle là où
  l'écart d'altitude est faible **par définition** (c'est ce qui rend l'unité
  `simple`).
- **D3 + confidence min-monotone** inchangés (enforcés par le même script).

---

## Consequences

**Positifs :**
- Coût Opus par unité `simple` : `Opus + Sonnet + Opus` → `Sonnet ×3`
  (~−70 % par unité simple, ordre de grandeur). Avec ~70-80 % d'unités simples
  sur un legacy typique → réduction agrégée majeure du budget Opus reverse.
- Risque architectural **nul** : aucune modification de structure, D3 et
  monotonie enforcés par le script existant, mono-saut **non** réintroduit.
- A/B trivial : comparer FEAT `simple` en Sonnet vs Opus sur un workspace réel ;
  rollback = retirer le routage (les agents sont inchangés).
- Cohérence interne : le stream code adopte le pattern déjà éprouvé du stream
  db-reverse.

**Négatifs / dette acceptée :**
- Le classifieur introduit un seuil à **calibrer sur les legacy réels** (le défaut
  MVP est conservateur — il préfère sur-classer en `complex`).
- Un faux négatif (unité complexe classée `simple`) dégrade la qualité de SA
  FEAT, pas du run : mitigé par le fail-safe (doute → `complex`) et rattrapable
  par re-run ciblé en Opus.
- Une rubrique de plus à garder en cohérence avec les champs L0 d'`inventory.json`.

---

## Alternatives considérées

- **Collapse structurel : 1 passe Sonnet fusionnée (analyse+US+FEAT) pour les
  unités simples** — écartée en MVP. Économie maximale (1 spawn) mais
  **réintroduit le mono-prompt** que `governance-major-reverse-spec-ladder` a
  décommissionné (risque de bave d'altitude, même atténué sur unité simple) et
  casserait la production des 3 artefacts attendus en aval. Conservée comme
  **option V2 opt-in** si le routage de modèle (D2) s'avère insuffisant — à
  décider sur données, pas a priori.
- **2 barreaux (analyse → FEAT, skip US) pour les simples** — écartée : casse le
  fil D3 `FEAT → US → T-N` (déjà rejetée par l'ADR parent pour la même raison).
- **Garder l'escalier full-Opus partout** — statu quo écarté : c'est précisément
  le gaspillage que l'audit a chiffré.
- **Router via le `complexity_router.py` forward existant** — écartée : ce rubric
  score une FEAT pour le pipeline forward (US/arch), pas une unité legacy ; les
  signaux d'entrée diffèrent (L0 `classes`/`dataAccess` vs FEAT). Un classifieur
  reverse dédié est plus simple et isolé (D4).

---

## Liens

- ADR parent : `governance-major-reverse-spec-ladder`
- Audit source : conversation audit reverse 2026-06-29 (recommandation P1
  « back-port du routage par complexité »)
- Précédent : `.sdd/python/sdd_reverse_scripts/build_proc_us.py` (routage
  déterministe db-reverse)
- Implémentation prévue (post-validation) :
  - `.sdd/python/sdd_reverse/code_unit_complexity.py` (classifieur, nouveau)
  - `docs/rubrics/reverse-complexity-routing.md` (rubrique SSoT, nouveau)
  - `.claude/commands/sdd-reverse-analyze.md` + `sdd-reverse-feat.md` (override
    de modèle au spawn selon la classe)
  - `.sdd/rules/reverse-engineering.md` (§ routage, additif)
  - tests : `tests/test_reverse_complexity_routing.py`
- Règle : `.sdd/rules/reverse-engineering.md`
- Loader : `.claude/loader.reverse.yml`
