# Project Constitution — {ProjectName}

> Document de référence partagé par TOUS les agents (PO, UI, Arch,
> Dev-Backend, Dev-Frontend). Source de vérité unique pour le glossaire
> métier, les conventions, et l'index des décisions architecturales.
>
> **Read-only en phases 2-5** : seuls `/spec-generate` (bootstrap) et
> les agents listés en §6 peuvent étendre ce fichier. Aucun agent ne le
> réécrit intégralement.

---

## 1. Identité du projet

- **Nom** : `{ProjectName}`
- **Version SDD_Pro** : v3
- **Créé le** : {YYYY-MM-DD}
- **Dernière mise à jour** : {YYYY-MM-DD}

---

## 2. Glossaire métier

> Termes spécifiques au domaine, partagés par tous les agents et toutes
> les SPECs. Évite les divergences de vocabulaire entre US, UI, code.

| Terme | Définition |
|---|---|
| `<terme-1>` | <définition courte, 1-2 phrases> |
| `<terme-2>` | <définition courte> |

---

## 3. Acteurs (cumul cross-SPEC)

> Tous les acteurs identifiés dans l'ensemble des SPECs du projet.
> Étendu automatiquement par l'agent PO à chaque `/us-generate {n}`.

| Acteur | Rôle | SPECs concernées |
|---|---|---|
| `<acteur-1>` | <rôle> | `{n1}-{Name}`, `{n2}-{Name}` |

---

## 4. Stack technique retenu

> Cumul des choix `workspace/input/stack/stack.md` au moment du dernier
> `/arch-init`. Voir ADRs §6 pour le rationale.

| Famille | Stack actif | ADR |
|---|---|---|
| Backend | `<stack>` | ADR-XXX |
| Frontend | `<stack>` | ADR-XXX |
| UI Design System | `<stack>` | ADR-XXX |
| Auth | `<stack>` ou `none` | ADR-XXX |
| Database | `<DatabaseType>` ou `none` | ADR-XXX |

---

## 5. Conventions projet

### 5.1 Nommage cross-fichiers
Voir `.claude/CLAUDE.md §3` — convention `{n}-{m}-{Name}` immuable.

### 5.2 IDs stables SPEC
Voir `.claude/CLAUDE.md §4` — `SFD-N`, `BR-N`, `AC-N`, `FD-N`.

### 5.3 Conventions spécifiques au projet
> À étendre au fil des décisions explicites du Tech Lead humain.

- <convention-1> (ex. : "tous les endpoints REST sont en kebab-case")
- <convention-2>

---

## 6. Architecture Decision Records (ADRs)

> Chaque décision technique structurante est tracée dans
> `workspace/output/context/adrs/ADR-{nnn}-{slug}.md`. L'index ci-dessous est
> maintenu par l'agent Arch (Phase C) et par les agents dev-* lors
> d'un choix non couvert par les ADRs existants.

| ADR | Titre | Statut | Phase |
|---|---|---|---|
| ADR-001 | <titre> | Accepted | Arch |

**Statuts possibles** : `Proposed`, `Accepted`, `Deprecated`, `Superseded by ADR-XXX`.

---

## 7. Risques et hypothèses (optionnel — depuis P3)

> Étendu par `/spec-deepen {n}` (technique d'élicitation Pre-mortem +
> Red Team). Vide tant que `/spec-deepen` n'a pas été lancé.

### 7.1 Risques identifiés

- <risque-1> (SPEC : `{n}-{Name}`, sévérité : low/medium/high)

### 7.2 Hypothèses

- <hypothèse-1> (SPEC : `{n}-{Name}`, validation : confirmée/à valider)

---

## 8. Qui écrit dans ce fichier

| Agent / Commande | Sections étendues |
|---|---|
| `/spec-generate` | §1 (init), §2-3 (acteurs+termes de la SPEC créée) |
| Agent `po` | §3 (cumul acteurs), §2 (termes nouveaux) |
| Agent `ui` | §2 (composants partagés découverts) |
| Agent `arch` | §4 (stack final), §6 (ADRs init) |
| Agents `dev-*` | §6 (ADR sur un choix non couvert) |
| `/spec-deepen` (P3) | §7 (risques + hypothèses) |

**Aucun agent** ne réécrit le fichier intégralement. Toutes les
modifications sont **append-only** ou **update-in-place** sur une ligne
de tableau précise.
